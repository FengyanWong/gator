"""Run-owned asynchronous sizing. Only the engine thread writes raw tables.

The proposer validates physical designs; this layer owns authorization, process
cancellation, durable call evidence, hints and handover state.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import queue
import math
import threading
import time
from uuid import uuid4

from analog_optimizer.parameters import ActionMapper
from analog_optimizer.search import Candidate, LlmProposer, SearchSchedule, ReplayClient
from analog_optimizer.search.llm import CallRecord, digest, encoded

from .storage.atomic import JsonlAppender, read_json, read_jsonl, write_json, temporary_path, publish
from .storage.dataset import utcnow
from .security import redact


def failure_summary(text, failure_type=None):
    """Bound failure context and withhold license-server output from the sizing model."""
    from .connection import INFRASTRUCTURE_PATTERNS
    license_text = dict(INFRASTRUCTURE_PATTERNS)['license_unavailable']
    if text and (failure_type == 'license_unavailable' or license_text.search(str(text))):
        return 'license failure (text withheld)'
    return redact(text, 300)


class SearchStopped(RuntimeError):
    pass


class RecordedClient:
    def __init__(self, owner, delegate):
        self.owner, self.delegate = owner, delegate

    def complete(self, prompt, schema, *, on_event=None):
        owner, settings = self.owner, self.owner.settings
        if owner.cancelled.is_set():
            raise SearchStopped('cancelled')
        if owner.error and owner.error.startswith('cost_unknown'):
            raise SearchStopped(owner.error)
        if owner.calls >= settings.max_llm_calls:
            raise SearchStopped('call_ceiling')
        if settings.max_llm_notional_usd is not None and owner.cost >= settings.max_llm_notional_usd:
            raise SearchStopped('cost_ceiling')
        owner.calls += 1
        call_id, started = uuid4().hex, time.monotonic()
        record = CallRecord(call_id, method=settings.method, provider=settings.provider or '',
                            model=settings.model or '', effort=settings.effort or '', started_at=utcnow().isoformat(),
                            prompt_sha256=digest(prompt), repair=owner.batch_attempt > 0,
                            request_position=owner.request_position, hints_included=owner.hints_used)
        owner.batch_attempt += 1
        data = dict(record.as_dict(), round=owner.schedule.rounds if settings.method == 'sac_llm_rescue' else None)
        directory = owner.root / 'calls' / call_id
        directory.mkdir(parents=True, exist_ok=True)
        temporary = temporary_path(directory / 'prompt.txt')
        temporary.write_text(prompt)
        publish(temporary, directory / 'prompt.txt')
        write_json(directory / 'record.json', data)
        owner.events.put(dict(type='call_started', call_id=call_id, method=settings.method,
                              call_number=owner.calls, phase=owner.schedule.phase))
        try:
            if hasattr(self.delegate, 'prepare_call'):
                self.delegate.prepare_call(call_id, None if settings.max_llm_notional_usd is None
                                           else settings.max_llm_notional_usd - owner.cost)
            response = self.delegate.complete(prompt, schema, on_event=lambda e: owner.events.put(dict(e, call_id=call_id)))
            if owner.cancelled.is_set():
                raise SearchStopped('cancelled')
            output = response.get('output', response) if isinstance(response, dict) else response
            audit = response.get('audit', {}) if isinstance(response, dict) and 'output' in response else {}
            usage = audit.get('usage') or {}
            data.update(input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'),
                        cache_read_tokens=usage.get('cache_read_input_tokens', usage.get('cached_input_tokens')),
                        cache_write_tokens=usage.get('cache_creation_input_tokens'),
                        notional_cost_usd=audit.get('total_cost_usd'), reply_sha256=digest(encoded(output)), status='received')
            cost = data['notional_cost_usd']
            if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
                cost = data['notional_cost_usd'] = None
            if cost is not None:
                owner.cost += cost
            elif settings.provider == 'claude_code':
                owner.error = 'cost_unknown: cannot authorize another call inside the notional ceiling'
            write_json(directory / 'response.json', output)
            return dict(output=output, call_id=call_id)
        except Exception as exc:
            audit = (getattr(exc, 'extra', {}) or {}).get('audit') or {}
            usage = audit.get('usage') or {}
            data.update(input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'),
                        cache_read_tokens=usage.get('cache_read_input_tokens'),
                        cache_write_tokens=usage.get('cache_creation_input_tokens'))
            cost = audit.get('total_cost_usd')
            if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
                data['notional_cost_usd'] = cost
                owner.cost += cost
            elif settings.provider == 'claude_code':
                owner.error = 'cost_unknown: cannot authorize another call inside the notional ceiling'
            data['status'] = 'cancelled' if owner.cancelled.is_set() else getattr(exc, 'code', str(exc))[:120]
            write_json(directory / 'response.json', dict(error=data['status']))
            raise
        finally:
            data.update(ended_at=utcnow().isoformat(), latency_seconds=time.monotonic() - started)
            write_json(directory / 'record.json', data)
            if data['status'] != 'received':
                owner.records.put(deepcopy(data))

    def validated(self, response, validation):
        owner = self.owner
        call_id = response['call_id']
        path = owner.root / 'calls' / call_id / 'record.json'
        data = read_json(path)
        for key in ('status', 'returned', 'accepted', 'rejected', 'notes_kept', 'notes_dropped'):
            data[key] = validation[key]
        write_json(path, data)
        owner.records.put(data)
        owner.events.put(dict(type='reply', call_id=call_id, output=response['output'],
                              accepted=validation['accepted'], rejected=validation['rejected']))


class SearchSession:
    def __init__(self, engine, client=None, restored=None, seed_proposer=None):
        self.engine, self.settings = engine, engine.config.run.search
        self.root = engine.layout.run_dir / 'llm'
        self.root.mkdir(exist_ok=True)
        self.live = JsonlAppender(self.root / 'live.jsonl')
        self.events, self.records = queue.Queue(), queue.Queue()
        self.cancelled = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gator-sizing')
        self.future, self.queue, self.history = None, [], []
        self.replay_release = None
        self.mapper = ActionMapper(engine.compiled.graph)
        adv = engine.config.run.advanced
        self.schedule = SearchSchedule(self.settings.method,
            warm_count=self.settings.warm_start_count or max(8, adv.batch_size, adv.warmup_transitions),
            initial_updates=self.settings.initial_sac_updates,
            stall_window=self.settings.rescue_stagnation_evaluations, max_rounds=self.settings.rescue_max_rounds)
        self.calls, self.cost, self.hints_read, self.hints_used, self.batch_attempt = 0, 0., 0, 0, 0
        self.source_counts, self.error, self.request_position = Counter(), None, 0
        self.wait_seconds, self._waiting_since = 0., None
        self.seed_proposer = seed_proposer
        if client is None and seed_proposer is None:
            from .agents.sizing import SizingCliClient
            client = SizingCliClient(engine.run_id, self.settings)
        self.client = client
        self.proposer = LlmProposer(self.mapper, RecordedClient(self, client))
        if restored:
            self.schedule = SearchSchedule(**restored['schedule'])
            self.queue = [Candidate(**v) for v in restored['queue']]
            self.history = [dict(row, failure=failure_summary(row.get('failure'))) for row in restored['history']]
            self.source_counts.update(restored['source_counts'])
            self.hints_read = restored['hints_read']
            self.proposer.notes = restored['notes']
            self.error = restored.get('error')
            self.wait_seconds = restored.get('wait_seconds', 0.)
        # Calls are charged before external execution, including a call interrupted after the last checkpoint.
        records = [read_json(p) for p in sorted((self.root / 'calls').glob('*/record.json'))]
        self.calls = len(records)
        self.cost = sum(r.get('notional_cost_usd') or 0 for r in records)
        if self.settings.provider == 'claude_code' and any(r.get('notional_cost_usd') is None for r in records):
            self.error = 'cost_unknown: cannot authorize another call inside the notional ceiling'
        for record in records:
            if record['status'] in ('pending', 'received'):
                record.update(status='interrupted', ended_at=utcnow().isoformat())
            self.records.put(record)
        if restored:
            # Completed batches may be newer than a learner checkpoint. Never pay
            # for them again or re-evaluate a design dispatched before a crash.
            consumed = Counter(r.get('llm_call_id') for r in read_jsonl(
                engine.layout.data / '_journal' / 'dispatch.jsonl'))
            batches = sorted((read_json(p) for p in (self.root / 'batches').glob('*.json')),
                             key=lambda b: b['position'])
            if batches:
                self.queue = []
                for batch in batches:
                    candidates = [Candidate(**v) for v in batch['candidates']]
                    for call_id in dict.fromkeys(c.metadata.get('call_id') for c in candidates):
                        group = [c for c in candidates if c.metadata.get('call_id') == call_id]
                        self.queue.extend(group[consumed[call_id]:])
                self.proposer.notes = batches[-1]['notes']
                self.hints_read = max(self.hints_read, batches[-1]['hints_read'])
            if self.schedule.method == 'sac_llm_rescue':
                self.schedule.rounds = max([self.schedule.rounds] + [r.get('round') or 0 for r in records])
                self.schedule.round_pending = bool(self.queue)

    def pending_designs(self):
        # A reused reset (engine op `reset_reused`) is no design either: it launches nothing (2026-09-30).
        return sum(bool(s['busy'] and s['busy']['op'] not in ('reset', 'reset_reused')) for s in self.engine.lane_state.values())

    def position(self):
        # Dispatch and completion are distinct events. A reply arriving while a
        # simulation is in flight must not move ahead of that dispatch in replay.
        return self.engine.ledger.charged + self.engine.counters['completion_index']

    def can_call(self):
        s = self.schedule
        return (not self.error and not self.cancelled.is_set() and self.calls < self.settings.max_llm_calls
                and (self.settings.max_llm_notional_usd is None or self.cost < self.settings.max_llm_notional_usd)
                and (s.method == 'llm' or s.method == 'llm_warmstart' and s.phase == 'llm_warmup'
                     and s.available_seeds(self.pending_designs() + len(self.queue)) > 0
                     or s.method == 'sac_llm_rescue' and s.rounds < s.max_rounds))

    def state_dict(self):
        return dict(schedule=self.schedule.state_dict(), queue=[asdict(c) for c in self.queue],
                    history=self.history, source_counts=dict(self.source_counts), hints_read=self.hints_read,
                    notes=self.proposer.notes, error=self.error, wait_seconds=self.waiting_seconds())

    def account_wait(self, waiting):
        now = time.monotonic()
        if self._waiting_since is not None:
            self.wait_seconds += now - self._waiting_since
        self._waiting_since = now if waiting else None

    def waiting_seconds(self):
        return self.wait_seconds + (time.monotonic()-self._waiting_since if self._waiting_since is not None else 0.)

    def status(self):
        hints = len(read_jsonl(self.engine.layout.control / 'llm_hints.jsonl'))
        return dict(phase=self.schedule.phase, pending=self.future is not None,
                    calls=self.calls, max_calls=self.settings.max_llm_calls, notional_cost_usd=self.cost if
                    self.settings.provider == 'claude_code' and not (self.error or '').startswith('cost_unknown') else None,
                    queued=len(self.queue), waiting_seconds=self.waiting_seconds(),
                    max_notional_usd=self.settings.max_llm_notional_usd, error=self.error,
                    hints_available=self.settings.hints_allowed and self.can_call(), hint_count=hints,
                    hints_included=self.hints_read, steered=hints > 0,
                    source_counts=dict(self.source_counts), **self.schedule.state_dict())

    def _context(self):
        engine = self.engine
        hints = read_jsonl(engine.layout.control / 'llm_hints.jsonl')
        unread = hints[self.hints_read:] if self.settings.hints_allowed else []
        self.hints_read += len(unread)
        self.hints_used = len(unread)
        graph = engine.compiled.graph
        connections = {}
        for c in graph.connections:
            connections.setdefault(c.device_id, {})[c.terminal] = c.net_id
        # Lossless column dictionaries keep large, repeated testbench instances
        # within the prompt bound without dropping connectivity or initial sizes.
        nets = sorted(n.id for n in graph.nets)
        net_index = {name: i for i, name in enumerate(nets)}
        types, type_index, devices = [], {}, []
        for device in graph.devices:
            parameters = graph.parameters[device.id]
            keys = tuple(sorted(k for k, v in parameters.items() if v.valid))
            signature = (device.kind, tuple(device.terminals), keys)
            if signature not in type_index:
                type_index[signature] = len(types)
                types.append(dict(kind=device.kind, terminals=device.terminals, initial_size_keys_SI=keys))
            devices.append([device.id, type_index[signature],
                [net_index[connections[device.id][terminal]] for terminal in device.terminals],
                [parameters[key].value for key in keys]])
        circuit = dict(nets=nets, device_types=types,
                       device_columns=['id', 'device_type_index', 'net_indices_in_terminal_order', 'initial_size_values_SI'],
                       devices=devices, group_member_columns=['device_index', 'parameter', 'ratio'])
        device_index = {device.id: i for i, device in enumerate(graph.devices)}
        groups = [dict(id=g.id, unit=g.unit, lower=g.lower, upper=g.upper, scale=g.scale,
                       step=g.step, initial=g.value,
                       members=[[device_index[m.device_id], m.parameter, m.ratio] for m in g.members]) for g in self.mapper.groups]
        targets = {t.metric_id: t for t in engine.config.targets}
        specs = [dict(t, equation=targets[t['metric_id']].equation,
                      judged_at='nominal' if targets[t['metric_id']].nominal_only else 'all configured conditions')
                 for t in engine.compiled.targets]
        return dict(circuit=circuit, groups=groups, specs=specs,
                    history=deepcopy(self.history), phase=self.schedule.phase,
                    budget={key: value for key, value in engine.ledger.snapshot().items()
                            if key not in ('first_feasible', 'first_nominal_feasible')},
                    rescue=self.schedule.state_dict(), hints=unread,
                    queued_values=[c.metadata.get('values', {}) for c in self.queue])

    def tick(self):
        engine = self.engine
        while not self.events.empty():
            self.live.append(dict(self.events.get_nowait(), utc=utcnow().isoformat()))
        released = self.replay_release is None or self.position() >= self.replay_release or self.cancelled.is_set()
        if self.future is not None and self.future.done() and released:
            try:
                candidates = self.future.result()
                if candidates and not self.seed_proposer:
                    write_json(self.root / 'batches' / (uuid4().hex + '.json'), dict(
                        position=self.position(), candidates=[asdict(c) for c in candidates],
                        notes=self.proposer.notes, hints_read=self.hints_read))
                self.queue.extend(candidates)
                if not self.queue and not self.cancelled.is_set():
                    self.error = 'invalid_output_after_repair'
            except Exception as exc:
                if not self.cancelled.is_set():
                    self.error = getattr(exc, 'code', str(exc))[:500]
            self.future = None
        while not self.records.empty() and released and self.future is None:
            record = self.records.get_nowait()
            if record.get('release_position') is None:
                record['release_position'] = self.position()
            path = self.root / 'calls' / record['call_id'] / 'record.json'
            write_json(path, record)
            fields = ('call_id', 'method', 'provider', 'model', 'effort', 'prompt_sha256', 'reply_sha256', 'status',
                      'started_at', 'ended_at', 'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens',
                      'returned', 'accepted', 'notes_kept', 'notes_dropped', 'hints_included', 'request_position',
                      'release_position', 'round', 'notional_cost_usd', 'latency_seconds', 'repair')
            row = dict(run_id=engine.run_id, **{key: record.get(key) for key in fields},
                       record_path=str(path.relative_to(engine.layout.run_dir)), rejected_json=encoded(record.get('rejected', [])))
            engine.dataset.append_auxiliary(record['call_id'], {'llm_calls': [row]})
            self.live.append(dict(type='call_finished', call_id=record['call_id'], status=record['status'],
                                  utc=utcnow().isoformat()))
        s = self.schedule
        pending = self.pending_designs()
        llm_pending = any(state['busy'] and state['busy'].get('llm_call_id') for state in engine.lane_state.values())
        if s.round_pending and not self.future and not self.queue and not llm_pending:
            s.finish_round()
            if self.error and not self.error.startswith('cost_unknown'):
                self.error = None  # a failed round requires a fresh window; it does not disable rescue forever
        if engine.stop_reason or self.cancelled.is_set():
            return
        if s.method == 'llm_warmstart' and self.error:
            s.degraded = self.error
        if self.future or self.queue:
            return
        due = s.rescue_due() if s.method == 'sac_llm_rescue' else (
            (s.method == 'llm' or s.phase == 'llm_warmup') and not pending and bool(self.history)
            and not any(state['busy'] for state in engine.lane_state.values()))
        if not due:
            return
        if not self.can_call() and not self.seed_proposer:
            if s.method == 'llm':
                engine.stop_reason = 'llm_' + (self.error or 'ceiling')
            elif s.method == 'llm_warmstart':
                s.degraded = self.error or 'call_or_cost_ceiling'
            return
        if s.method == 'sac_llm_rescue':
            s.start_round()
        n = self.settings.candidates_per_call
        if s.method == 'llm_warmstart':
            n = min(n, s.available_seeds(pending))
        n = min(n, max(0, engine.config.run.max_evaluations - engine.ledger.charged))
        if n < 1:
            return
        self.request_position, self.batch_attempt = self.position(), 0
        if isinstance(self.client, ReplayClient):
            if self.client.next_position is not None and self.client.next_position != self.request_position:
                raise ValueError('The run diverged: replay request position differs')
            self.replay_release = self.client.next_release
        context = self._context()
        proposer = self.seed_proposer or self.proposer
        self.future = self.pool.submit(proposer.propose, n, context)

    def choose(self):
        """None means wait; an empty Candidate means ordinary SAC may proceed."""
        s = self.schedule
        if s.method == 'llm_warmstart' and s.phase == 'initial_learning':
            return None
        if s.method == 'llm_warmstart' and s.phase == 'llm_warmup' and not s.available_seeds(self.pending_designs()):
            return None
        if self.queue:
            return self.queue.pop(0)
        if s.method == 'llm' or s.method == 'llm_warmstart' and s.phase == 'llm_warmup' and not s.degraded:
            return None
        if s.method == 'llm_warmstart' and s.phase == 'llm_warmup':
            return Candidate({g: self.engine.rng.uniform(-1, 1) for g in self.mapper.group_ids}, 'random_warmup')
        return Candidate({}, 'sac')

    def replay_barrier(self):
        """Only replay waits for local decoding at the recorded scheduler boundary."""
        return (self.future is not None and self.replay_release is not None
                and self.position() >= self.replay_release and not self.cancelled.is_set())

    def observe(self, result, call_id):
        self.history.append(result)
        self.proposer.observe(result)
        self.schedule.observe(result)
        self.source_counts[result['source']] += 1
        if call_id:
            self.live.append(dict(type='outcome', call_id=call_id, utc=utcnow().isoformat(), **result))

    def cancel(self):
        self.cancelled.set()
        if callable(getattr(self.client, 'cancel', None)):
            self.client.cancel()

    def close(self):
        self.account_wait(False)
        self.cancel()
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.tick()
        if self.engine.requested != 'pause':
            for candidate in self.queue:
                self.live.append(dict(type='unused', call_id=candidate.metadata.get('call_id'),
                                      values=candidate.metadata.get('values'), reason=self.engine.stop_reason))
        self.live.close()
