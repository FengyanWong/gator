"""All model responses and simulation results in this module are synthetic."""
import json

import pytest

from analog_optimizer.search import FakeClient
from gator_workbench import runs, schema, tasks
from gator_workbench.engine import RunEngine
from gator_workbench.compile import compile_task
from gator_workbench.storage import read_json
from gator_workbench.storage.atomic import write_json
from analog_optimizer.parameters import ActionMapper
from helpers import make_config, roots_for, rows


def configure(tmp_path, method, *, budget=14, **settings):
    config = make_config(tmp_path, run=dict(max_evaluations=budget))
    config.run.search = schema.SearchSettings(method=method, provider='codex', max_llm_calls=8,
        warm_start_count=4, initial_sac_updates=3, candidates_per_call=2, **settings)
    config.run.advanced.batch_size = 4
    config.run.advanced.warmup_transitions = 20
    config.run.advanced.episode_length = 30
    return config


def client_for(config):
    graph = compile_task(config, tasks.load_task(config.circuit).base_graph).graph
    mapper = ActionMapper(graph)
    return FakeClient([dict(analysis='Synthetic fixture', notes=[], candidates=[dict(
        values=mapper.legalize(dict.fromkeys(mapper.group_ids, z)).group_values,
        rationale='Synthetic fixture') for z in (start, start + .05)])
        for start in (-.9, -.7, -.5, -.3, -.1, .1, .3, .5)])


def execute_search(config, tmp_path, client=None):
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    task = tasks.load_task(config.circuit)
    engine = RunEngine(layout.run_dir, task=task, llm_client=client or client_for(config),
                       lock=runs.take_lock(layout.run_dir))
    result = engine.run()
    assert read_json(layout.status)['state'] != 'failed', read_json(layout.status)
    return layout, engine


def test_warmstart_real_learner_handover(tmp_path):
    layout, engine = execute_search(configure(tmp_path, 'llm_warmstart'), tmp_path)
    evaluations = rows(layout, 'evaluations')
    steps = [r for r in evaluations if r['action_source'] != 'reset']
    assert [r['action_source'] for r in steps[:4]] == ['llm_proposal'] * 4
    assert all(r['action_source'] == 'sac_policy' for r in steps[4:])
    assert steps[4]['policy_version'] == 3
    assert engine.search.schedule.admitted == 4 and engine.search.schedule.trained == 3
    initial = [r for r in rows(layout, 'learner_updates') if r['update_phase'] == 'initial']
    assert len(initial) == 3 and all(r['evaluations_collected'] == 5 for r in initial)
    calls = {r['call_id'] for r in rows(layout, 'llm_calls')}
    assert all(r['llm_call_id'] in calls for r in steps[:4])


@pytest.mark.parametrize('mode', ['scratch', 'fine_tune'])
def test_initial_updates_change_weights_before_first_policy_action(tmp_path, mode):
    import math
    from gator_workbench.checkpoints import weight_digest
    config = configure(tmp_path, 'llm_warmstart')
    if mode == 'fine_tune':
        source, _ = execute_search(config.model_copy(deep=True), tmp_path)
        config.run.mode = mode
        config.run.model_source.run_dir = str(source.run_dir)
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    seen = {}
    class TracedEngine(RunEngine):
        def _initial_update(self):
            seen.setdefault('before', weight_digest(self.learner))
            super()._initial_update()
            seen['after'] = weight_digest(self.learner)
    engine = TracedEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert engine.run() == 'completed', read_json(layout.status)
    assert seen['before'] != seen['after']
    initial = [r for r in rows(layout, 'learner_updates') if r['update_phase']=='initial']
    assert len(initial)==3
    assert all(math.isfinite(r[k]) for r in initial for k in ('critic_loss','actor_loss','alpha'))


def test_llm_crash_receipts_recover_results_newer_than_checkpoint(tmp_path):
    config = configure(tmp_path, 'llm', budget=9)
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    class OlderCheckpoint(RunEngine):
        def _checkpoint(self, kind):
            if kind=='fixture': return super()._checkpoint(kind)
            self.checkpoint_due=False
        def _commit(self, *args):
            super()._commit(*args)
            if self.ledger.completed==2: self._checkpoint('fixture')
            if self.ledger.completed==5:
                write_json(self.layout.control/'command.json',dict(id='pause',command='pause'))
    first = OlderCheckpoint(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert first.run()=='paused'
    saved = read_json(layout.run_dir/'checkpoints/latest.json')
    assert saved['commit_seq'] < first.dataset.last_seq
    restored = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    restored.run.mode='resume'
    restored.run.model_source.run_dir=str(layout.run_dir)
    client=client_for(config)
    client.replies=client.replies[first.search.calls:]
    resumed, second=execute_search(restored,tmp_path,client)
    assert len(rows(resumed,'evaluations'))==9
    assert sum(r['action_source']=='reset' for r in rows(resumed,'evaluations'))==1
    assert len(second.search.history)==9 and second.search.calls==4


def test_llm_only_never_builds_a_learner(tmp_path, monkeypatch):
    monkeypatch.setattr('gator_workbench.modes.build', lambda *a, **kw: pytest.fail('LLM only built SAC'))
    layout, engine = execute_search(configure(tmp_path, 'llm', budget=7), tmp_path)
    evaluations = rows(layout, 'evaluations')
    assert [r['action_source'] for r in evaluations] == ['reset'] + ['llm_proposal'] * 6
    assert engine.learner is engine.replay is None
    assert not rows(layout, 'learner_updates')
    assert all(not r['replay_admitted'] for r in rows(layout, 'transitions'))
    assert read_json(layout.run_dir / 'checkpoints/latest.json')['restoration_capability'] == 'search_state'
    assert not list((layout.run_dir / 'checkpoints').glob('*/model_weights.pt'))


def test_warmstart_receipt_without_archive_recollects_missing_replay(tmp_path):
    config = configure(tmp_path, 'llm_warmstart', budget=14)
    config.output.save_transition_archive = False
    config.output.save_replay_snapshots = True
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))

    class Crash(RunEngine):
        def _checkpoint(self, kind):
            if kind == 'fixture':
                return super()._checkpoint(kind)
            self.checkpoint_due = False

        def _commit(self, *args):
            super()._commit(*args)
            if self.ledger.completed == 2:
                self._checkpoint('fixture')
            if self.search.schedule.admitted >= 4:
                raise RuntimeError('fixture crash after warm start')

    first = Crash(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert first.run() == 'failed'
    restored = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    restored.run.mode = 'resume'
    restored.run.model_source.run_dir = str(layout.run_dir)
    client = client_for(config)
    client.replies = client.replies[first.search.calls:]
    resumed, engine = execute_search(restored, tmp_path, client)
    assert engine.search.schedule.admitted == 4 and engine.search.schedule.trained == 3
    assert len(rows(resumed, 'evaluations')) == 14
    from gator_workbench.storage.atomic import read_jsonl
    events = read_jsonl(resumed.logs / 'events.jsonl')
    recovery = next(e['warm_start_replay_recovery'] for e in events if 'warm_start_replay_recovery' in e)
    assert recovery['admitted_before'] == 4 and recovery['admitted_recovered'] == 1
    assert any(e['action_source'] == 'sac_policy' for e in rows(resumed, 'evaluations'))


@pytest.mark.parametrize('diagnostic,hidden', [
    ('api_key=fixture-secret ' + 'long diagnostic ' * 12000, 'fixture-secret'),
    ('License checkout failed at fixture-host:5280 /private/simulator/log', 'fixture-host'),
])
def test_failure_context_is_redacted_and_bounded_before_model_history(tmp_path, diagnostic, hidden):
    from analog_optimizer.search.llm import build_context
    config = configure(tmp_path, 'llm', budget=3)
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))

    class DiagnosticEngine(RunEngine):
        def _commit(self, lane, busy, result):
            result = dict(result, exception=dict(type='RuntimeError', message=diagnostic))
            return super()._commit(lane, busy, result)

    engine = DiagnosticEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    engine.run()
    history = engine.search.history
    assert history and all(len(row['failure']) < 350 for row in history)
    prompt = build_context(dict(circuit={}, groups=[], specs=[], budget={}, phase='llm_search',
                                rescue={}, hints=[], notes=[], history=history))
    assert hidden not in prompt
    assert history[0]['evaluation_id'] in prompt


def test_warmstart_failure_falls_back_only_until_W(tmp_path):
    layout, engine = execute_search(configure(tmp_path, 'llm_warmstart'), tmp_path,
                                    FakeClient([RuntimeError('fixture_timeout')]))
    steps = [r for r in rows(layout, 'evaluations') if r['action_source'] != 'reset']
    assert [r['action_source'] for r in steps[:4]] == ['random_warmup'] * 4
    assert all(r['action_source'] == 'sac_policy' for r in steps[4:])
    assert engine.search.schedule.degraded == 'fixture_timeout'


def test_default_search_keeps_historical_hash(tmp_path):
    config = make_config(tmp_path)
    old = config.model_dump(mode='json')
    old['run'].pop('search')
    assert schema.config_hash(config) == schema.config_hash(old)


@pytest.mark.parametrize('command', ['pause', 'stop', 'cancel'])
@pytest.mark.parametrize('method', ['llm', 'llm_warmstart'])
def test_controls_cancel_pending_ai_without_new_evaluations(tmp_path, command, method):
    import threading
    config = configure(tmp_path, method)
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    class WaitingClient:
        cancelled = threading.Event()

        def complete(self, prompt, schema, *, on_event=None):
            write_json(layout.control / 'command.json', dict(id='test', command=command))
            assert self.cancelled.wait(10), 'Engine did not cancel the pending model call'
            raise RuntimeError('cancelled')

        def cancel(self):
            self.cancelled.set()
    engine = RunEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=WaitingClient())
    assert engine.run() == dict(pause='paused', stop='stopped', cancel='cancelled')[command]
    assert len(rows(layout, 'evaluations')) == 1
    calls = rows(layout, 'llm_calls')
    assert len(calls) == 1 and calls[0]['status'] == 'cancelled'


@pytest.mark.parametrize('command', ['pause', 'stop', 'cancel'])
def test_controls_interrupt_initial_learning_before_another_update(tmp_path, command):
    config = configure(tmp_path, 'llm_warmstart')
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    class ControlledEngine(RunEngine):
        def _poll_control(self):
            if self.search and self.search.schedule.phase=='initial_learning' and self.search.schedule.trained==1:
                write_json(self.layout.control/'command.json', dict(id='initial-control', command=command))
            super()._poll_control()
    engine = ControlledEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert engine.run() == dict(pause='paused', stop='stopped', cancel='cancelled')[command]
    assert engine.learner.updates == engine.search.schedule.trained == 1
    assert len(rows(layout,'learner_updates')) == 1
    assert not any(r['action_source']=='sac_policy' for r in rows(layout,'evaluations'))


def test_llm_resume_keeps_one_baseline_and_queue(tmp_path):
    config = configure(tmp_path, 'llm', budget=7)
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    class PauseEngine(RunEngine):
        def _commit(self, *args):
            super()._commit(*args)
            if self.ledger.completed == 2:
                write_json(self.layout.control / 'command.json', dict(id='pause', command='pause'))
    first = PauseEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert first.run() == 'paused'
    assert first.search.queue
    restored = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    restored.run.mode = 'resume'
    restored.run.model_source.run_dir = str(layout.run_dir)
    new_client = client_for(config)
    new_client.replies.pop(0)  # the first batch is already durable, including its queued second design
    resumed, second = execute_search(restored, tmp_path, new_client)
    assert resumed.run_dir == layout.run_dir
    assert [r['action_source'] for r in rows(resumed, 'evaluations')] == ['reset'] + ['llm_proposal'] * 6
    assert second.search.calls == 3


def test_rescue_keeps_sac_running_and_learning_while_ai_waits(tmp_path):
    import threading
    config = configure(tmp_path, 'sac_llm_rescue', budget=20, rescue_stagnation_evaluations=1, rescue_max_rounds=1)
    config.run.advanced.warmup_transitions = 4
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    released = threading.Event()
    base = client_for(config)
    captured = {}
    class DelayedClient:
        def complete(self, prompt, schema, *, on_event=None):
            captured.update(evaluations=engine.ledger.completed, updates=engine.learner.updates)
            assert released.wait(15), 'SAC stopped while waiting for AI'
            return base.complete(prompt, schema)

        def cancel(self):
            released.set()
    class RescueEngine(RunEngine):
        def _prepare(self):
            super()._prepare()
            self.search.schedule.best = (1, 1e6)  # controlled reference: every policy step stalls

        def _commit(self, *args):
            super()._commit(*args)
            if captured and self.ledger.completed >= captured['evaluations'] + 2:
                assert self.learner.updates > captured['updates']
                released.set()
    engine = RescueEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=DelayedClient())
    assert engine.run() == 'completed', read_json(layout.status)
    results = rows(layout, 'evaluations')
    assert any(r['action_source'] == 'llm_proposal' for r in results)
    assert len(results) == 20 and engine.search.schedule.rounds == 1
    assert sum(r['action_source'] == 'random_warmup' for r in results) == 4


@pytest.mark.parametrize('method', ['llm_warmstart', 'llm', 'sac_llm_rescue'])
def test_fake_then_replay_reproduces_scheduler_and_learning(tmp_path, monkeypatch, method):
    from itertools import count
    from uuid import UUID
    from analog_optimizer.search import ReplayClient
    import gator_workbench.budget as budget_module
    config = configure(tmp_path, method, budget=18, rescue_stagnation_evaluations=1)
    config.run.advanced.warmup_transitions = 4

    class ControlledEngine(RunEngine):
        def _prepare(self):
            super()._prepare()
            if method == 'sac_llm_rescue':
                self.search.schedule.best = (1, 1e6)

    def run(directory, client):
        sequence = count(1)
        monkeypatch.setattr(budget_module, 'uuid4', lambda: UUID(int=next(sequence)))
        local = config.model_copy(deep=True)
        local.output.output_root = str(directory)
        layout, _ = runs.prepare_run(local, roots_for(directory))
        engine = ControlledEngine(layout.run_dir, task=tasks.load_task(local.circuit), llm_client=client)
        assert engine.run() == 'completed', read_json(layout.status)
        return layout, engine

    first, engine = run(tmp_path / 'first', client_for(config))
    entries = []
    for record in sorted(first.run_dir.glob('llm/calls/*/record.json'), key=lambda p: read_json(p)['started_at']):
        data = read_json(record)
        entries.append(dict(data, reply=read_json(record.parent / 'response.json')))
    assert entries
    replay = ReplayClient(entries)
    second, other = run(tmp_path / 'second', replay)
    assert len(replay.prompts) == len(entries)
    assert engine.search.schedule.state_dict() == other.search.schedule.state_dict()
    columns = ['evaluation_id', 'action_source', 'phase', 'policy_version', 'reward', 'normalized_constraint_violation']
    assert [[r[c] for c in columns] for r in rows(first, 'evaluations')] == [[r[c] for c in columns] for r in rows(second, 'evaluations')]
    columns = ['update_index', 'update_phase', 'critic_loss', 'actor_loss', 'alpha']
    # Include every numeric learner field and its phase; omit time and identity metadata.
    def updates(layout):
        return [{k: v for k, v in r.items() if isinstance(v, (float, int)) and 'seconds' not in k
                 or k == 'update_phase'} for r in rows(layout, 'learner_updates')]
    assert updates(first) == updates(second)


@pytest.mark.parametrize('pause_phase', ['llm_warmup', 'initial_learning', 'search'])
def test_warmstart_resume_preserves_phase_and_weights(tmp_path, pause_phase):
    import torch
    config = configure(tmp_path, 'llm_warmstart', budget=14)
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    class PausedEngine(RunEngine):
        def _poll_control(self):
            phase = self.search.schedule.phase if self.search else None
            ready = self.search and (self.search.schedule.admitted >= 2 if phase == 'llm_warmup'
                    else self.search.schedule.trained >= 1)
            if phase == pause_phase and ready and not self.requested:
                write_json(self.layout.control / 'command.json', dict(id='pause', command='pause'))
            super()._poll_control()
    first = PausedEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert first.run() == 'paused'
    completed_calls = first.search.calls
    restored = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    restored.run.mode = 'resume'
    restored.run.model_source.run_dir = str(layout.run_dir)
    client = client_for(config)
    client.replies = client.replies[completed_calls:]
    resumed, second = execute_search(restored, tmp_path, client)
    assert second.search.schedule.admitted == 4 and second.search.schedule.trained == 3
    initial = [r for r in rows(resumed, 'learner_updates') if r['update_phase'] == 'initial']
    assert len(initial) == 3
    assert all(r['policy_version'] >= 3 for r in rows(resumed, 'evaluations') if r['action_source'] == 'sac_policy')


@pytest.mark.parametrize('concurrency,budget', [(3, 16), (2, 3)])
def test_warmstart_parallel_slots_and_insufficient_budget(tmp_path, concurrency, budget):
    config = configure(tmp_path, 'llm_warmstart', budget=budget)
    config.run.concurrency = concurrency
    layout, engine = execute_search(config, tmp_path)
    assert len(rows(layout, 'evaluations')) == budget
    assert engine.search.schedule.admitted <= 4
    if budget < 5:
        assert engine.search.schedule.phase == 'llm_warmup'
        assert not rows(layout, 'learner_updates')
    else:
        assert engine.search.schedule.admitted == 4
        assert engine.search.schedule.trained == 3


@pytest.mark.parametrize('failure', [RuntimeError('timeout'), RuntimeError('refusal'), {'bad': True}])
def test_llm_only_failure_stops_without_fallback(tmp_path, failure):
    config = configure(tmp_path, 'llm')
    client = FakeClient([failure, failure])
    layout, engine = execute_search(config, tmp_path, client)
    assert [r['action_source'] for r in rows(layout, 'evaluations')] == ['reset']
    assert engine.search.calls in (1, 2)
    assert not rows(layout, 'learner_updates')


def test_call_ceiling_counts_repair(tmp_path):
    config = configure(tmp_path, 'llm')
    config.run.search.max_llm_calls = 1
    layout, engine = execute_search(config, tmp_path, FakeClient([{'bad': True}, {'bad': True}]))
    assert engine.search.calls == 1
    assert len(rows(layout, 'llm_calls')) == 1
    assert len(rows(layout, 'evaluations')) == 1


def test_unknown_claude_cost_prevents_repair_and_is_not_reported_as_zero(tmp_path):
    config=configure(tmp_path,'llm')
    config.run.search.provider='claude_code'
    config.run.search.max_llm_notional_usd=1
    layout, engine=execute_search(config,tmp_path,FakeClient([{'bad':True},{'bad':True}]))
    assert engine.search.calls==1
    assert engine.search.status()['notional_cost_usd'] is None
    assert rows(layout,'llm_calls')[0]['notional_cost_usd'] is None


def test_rescue_without_stall_matches_plain_sac(tmp_path):
    config=configure(tmp_path,'sac_llm_rescue',budget=12,rescue_stagnation_evaluations=1000)
    config.run.advanced.warmup_transitions=4
    first,engine=execute_search(config,tmp_path)
    config.run.search=schema.SearchSettings()
    other,control=execute_search(config,tmp_path)
    keys=('action_source','phase','policy_version','reward')
    assert [[r[k] for k in keys] for r in rows(first,'evaluations')]==[[r[k] for k in keys] for r in rows(other,'evaluations')]
    assert not rows(first,'llm_calls') and engine.learner.updates==control.learner.updates


def test_rescue_resume_retains_round_queue_and_call_budget(tmp_path):
    config = configure(tmp_path, 'sac_llm_rescue', budget=20,
                       rescue_stagnation_evaluations=1, rescue_max_rounds=1)
    config.run.advanced.warmup_transitions = 4
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    class PausedRescue(RunEngine):
        def _prepare(self):
            super()._prepare()
            self.search.schedule.best = (1, 1e6)

        def _commit(self, *args):
            super()._commit(*args)
            if self.search.source_counts['llm_proposal'] == 1:
                write_json(self.layout.control/'command.json', dict(id='pause', command='pause'))
    first = PausedRescue(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client_for(config))
    assert first.run() == 'paused'
    assert first.search.calls == first.search.schedule.rounds == 1 and len(first.search.queue) == 1
    updates = first.learner.updates
    restored = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    restored.run.mode = 'resume'
    restored.run.model_source.run_dir = str(layout.run_dir)
    client = FakeClient([])
    resumed, second = execute_search(restored, tmp_path, client)
    assert second.search.calls == second.search.schedule.rounds == 1 and not client.prompts
    assert second.search.source_counts['llm_proposal'] == 2
    assert second.learner.updates > updates
    assert len(rows(resumed, 'evaluations')) == 20 and len(rows(resumed, 'llm_calls')) == 1


@pytest.mark.parametrize('arm', ['matched_random', 'matched_seeded'])
def test_benchmark_controls_share_handover_without_provider(tmp_path, monkeypatch, arm):
    import importlib.util
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / 'examples'))
    spec = importlib.util.spec_from_file_location('benchmark_llm_sizing', Path(__file__).parents[2] / 'examples/benchmark_llm_sizing.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr('gator_workbench.agents.sizing.SizingCliClient', lambda *a, **kw: pytest.fail('Control instantiated a provider'))
    result = module.run_arm(configure(tmp_path, 'llm_warmstart'), arm, tmp_path)
    assert result['state'] == 'completed'
    assert result['initial_updates'] == 3 and result['online_updates'] > 0
    assert result['llm_calls'] == 0 and result['notional_cost_usd'] is None
    assert result['source_counts']['seeded_warmup' if arm == 'matched_seeded' else 'random_warmup'] == 4
