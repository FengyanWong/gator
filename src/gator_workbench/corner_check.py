"""Corner check of a finished run: its best designs simulated again at the five fixed corners.

In plain words: after an optimization run, the designs that met every spec at the normal condition are simulated again
at four more conditions - slow transistors, 125 C and 0.9 V; fast, -40 C and 1.1 V; the two mixed process corners - and
once more at the normal one. A design is ACCEPTED only when it meets every spec at all five, one failed corner REJECTS
it, and a corner that could not be judged (no result, a measurement or connection error) leaves it INCONCLUSIVE; that is
never blamed on the design. Nothing of it goes back into learning.

Used unchanged from the optimizer (src/analog_optimizer/ is not touched):
* the corners and their limits: configs/gpdk045_conditions.json, checked by the circuit profile's validate_condition;
* preparing a corner: the profile's structure_for_condition (the supply) and the deck's model section and temperature;
* the grading: analog_optimizer.evaluation.corners.summarize_corners (docs/pvt-mc-interfaces.md, M3).

Decided here:
* WHICH designs: feasible recorded designs, plus the real task reference even if nominal fails; identical executed widths
  counted once, the SAFEST first: the largest smallest spec margin (distance to the nearest limit / that spec's scale).
  The optimizer's select_top_designs ranks by reward, which is 0 for every feasible design, and breaks that tie by a
  random candidate ID;
* WHERE it runs: a detached process like a run's worker (``python -m gator_workbench.corner_check``), so a page reload
  or a backend restart never cuts it in half. Its files: <run>/corner_checks/<check_id>/;
* REAL: the verified single-worker adapter (VirtuosoBridgeBackend) writes one design's widths into the cell, then per
  corner exports and simulates with that corner's model section, temperature and supply. At the end - also after a
  failure - the recorded widths are written back and read back. Only circuits whose profile accepts the corners take
  part (today the two op-amps); every other circuit is refused with the reason before anything starts. Two
  infrastructure failures in a row (timeout, transport, license, simulator) stop the check, so budget is not spent on a
  broken link;
* MOCK: the analytic toy backend with its optimum moved per corner (MOCK_CORNER_SHIFT) - plumbing for the zero-cost
  task, not a model of any process.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import signal
from uuid import uuid4

from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus, UnsupportedCapability
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.evaluation.corners import NominalDesign, summarize_corners
from analog_optimizer.measurements.specs import SpecificationEvaluator

from . import tasks
from .compile import CompileError, compile_task
from .engine import INFRASTRUCTURE_FAILURES as INFRASTRUCTURE, RunLock
from .layout import RunLayout
from .paths import repo_root
from .schema import WorkbenchConfig, task_definition_hash
from .security import redact
from .storage.atomic import JsonlAppender, read_json, read_jsonl, write_json
from .storage.dataset import DatasetReader

CHECK_DIR = 'corner_checks'
MAX_DESIGNS = 3
LIVE = ('starting', 'running', 'stopping')
MAX_INFRASTRUCTURE_FAILURES = 2          # in a row: the link is broken, not the design
CHECK_ID = re.compile(r'^\d{8}T\d{6}Z-[0-9a-f]{8}$')
CONDITIONS_FILE = 'configs/gpdk045_conditions.json'
BRIDGE_STATE = 'artifacts/local/bridge-state'       # tasks.py: every real task's adapter state root and session lock
# MOCK only: the toy optimum of every parameter kind moves by this much (normalized units) at each corner, so that a
# design near the edge of its nominal acceptance can fail one. Plumbing for the free task, not a model of a process.
MOCK_CORNER_SHIFT = {'nominal': 0.0, 'ss_hot_low': 0.35, 'ff_cold_high': -0.35, 'fs_nominal': 0.15, 'sf_nominal': -0.15}
MOCK_NOTICE = ('MOCK: the toy score has its optimum moved at each corner. This exercises the corner check; it says '
               'nothing about a circuit.')
SELECTION_RULE = ('The real task reference is also available even when nominal fails. Recorded designs that met every hard spec at the normal condition; identical widths counted once; the safest '
                  'first - the largest smallest spec margin (distance to the nearest limit divided by that spec\'s scale); '
                  'ties: the earlier evaluation.')
REAL_AUTHORIZATION = ('A corner check of a real circuit runs real Spectre simulations and writes each design\'s widths '
                      'into the cell (restored afterwards). It needs your explicit authorization.')


class CheckRefused(ValueError):
    """Nothing was created or started; the message says why in plain words."""
    def __init__(self, message, *, code='refused', report=None):
        super().__init__(message)
        self.code, self.report = code, report


def iso(value=None):
    return (value or datetime.now(timezone.utc)).isoformat()


# ================================================================================ corners and circuits
def screening_corners(profile=None):
    """(corners, nominal corner, post-validation settings) - the profile's own configuration, or the project file."""
    config = (profile.condition_config if profile is not None
              else json.loads((repo_root() / CONDITIONS_FILE).read_text()))
    return (tuple(PVTCorner(**c) for c in config['screening_corners']), PVTCorner(**config['nominal']),
            dict(config.get('post_validation') or {}))


def corner_record(corner) -> dict:
    return dict(asdict(corner), label=f'{corner.model_section.upper()}, {corner.temperature_c:g} °C, {corner.supply_v:g} V')


def _real_profile(task_key):
    """The circuit profile object of a real task, from local files only (no connection)."""
    name = task_key.partition(':')[2]
    if str(task_key).startswith('ngspice:'):
        raise CheckRefused('Corner checks simulate through the Virtuoso profiles: an ngspice netlist task has none yet.',
                           code='unsupported_task')
    if name in tasks.offered_real_profiles():
        return tasks._verified_profile(name)
    from . import profiles
    if name not in profiles.list_profiles():
        raise CheckRefused(f'{task_key} is no longer registered, so its designs cannot be simulated again.',
                           code='task_blocked')
    return profiles.load_profile(name)


def _corner_problem(profile, corners):
    """None when the profile prepares every corner, else its own reason."""
    for corner in corners:
        try:
            profile.validate_condition(SimulationCondition(corner, 'pvt_validation'))
        except (UnsupportedCapability, ValueError) as exc:
            return str(exc)
    return None


@lru_cache(maxsize=1)
def checkable_real_tasks() -> tuple:
    """The registered real tasks whose profile accepts the corners (built-ins only; local files, cached per process)."""
    found = []
    for name in tasks.offered_real_profiles():
        try:
            profile = tasks._verified_profile(name)
            if _corner_problem(profile, screening_corners(profile)[0]) is None:
                found.append(f'real:{name}')
        except Exception:
            continue
    return tuple(found)


def _unsupported(task_key, problem) -> str:
    listed = ', '.join(checkable_real_tasks()) or 'none'
    return (f'{task_key} is qualified at its normal condition only, so its designs cannot be checked at corners yet '
            f'(the profile says: {problem}). Circuits that can: {listed}, and the MOCK task.')


class Context:
    """Everything a check needs from its run, loaded from the run's own files."""
    def __init__(self, layout, manifest, *, allow_real=False):
        self.layout, self.manifest = layout, manifest
        self.config = WorkbenchConfig.model_validate(read_json(layout.effective_config))
        self.mock = bool(manifest.get('mock'))
        self.task_key = (manifest.get('circuit') or {}).get('task_key') or self.config.circuit.task_id or ''
        try:
            self.task = tasks.load_task(self.config.circuit, allow_real=allow_real and not self.mock,
                                        profile_id=self.config.run.connection_profile_id)
        except tasks.TaskBlocked as exc:
            raise CheckRefused(f"This run's circuit cannot be loaded here: {exc}", code='task_blocked')
        if self.task.mock != self.mock:
            raise CheckRefused('The run manifest and its task disagree about mock and real.', code='provenance')
        try:
            self.compiled = compile_task(self.config, self.task.base_graph)
        except CompileError as exc:
            raise CheckRefused(f"This run's configuration no longer compiles: {exc}", code='compile')
        self.profile = None if self.mock else _real_profile(self.task_key)
        self.corners, self.nominal, self.post = screening_corners(self.profile)
        if self.profile is not None:
            problem = _corner_problem(self.profile, self.corners)
            if problem is not None:
                raise CheckRefused(_unsupported(self.task_key, problem), code='corners_unsupported')
        self.evaluator = SpecificationEvaluator(self.compiled.specs)
        graph = self.compiled.graph
        self.expected_keys = (set(self.profile.writable_keys) if self.profile is not None else set(
            graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})))

    @property
    def origin(self):
        return 'synthetic' if self.mock else 'real'

    def source_name(self, instance_path, parameter_name):
        value = self.compiled.graph.parameters.get(instance_path, {}).get(parameter_name)
        return None if value is None else (value.source_name or parameter_name)


# ================================================================================ which designs
def _margin(target, value):
    """Distance to the nearest limit in units of the spec's scale: >= 0 inside, < 0 outside."""
    from analog_optimizer.measurements.specs import spec_margin
    return spec_margin(target['lower'], target['upper'], target['scale'], value, target.get('margin_sides', 'both'))


def candidates(context: Context):
    """(ranked distinct feasible designs, counts). Read-only: the run's evaluations, parameters and metrics tables."""
    reader = DatasetReader(context.layout.data)
    evaluations = reader.rows('evaluations', ['evaluation_id', 'completion_index', 'reward', 'valid',
                                              'all_hard_constraints_satisfied', 'status'])
    widths, values = {}, {}
    for row in reader.rows('parameters', ['evaluation_id', 'variable_id', 'instance_path', 'parameter_name', 'unit',
                                          'executed_value']):
        widths.setdefault(row['evaluation_id'], []).append(row)
    for row in reader.rows('metrics', ['evaluation_id', 'metric_name', 'raw_value', 'aggregation_level']):
        if row['aggregation_level'] == 'aggregate':
            values.setdefault(row['evaluation_id'], {})[row['metric_name']] = row['raw_value']
    hard = [t for t in context.compiled.targets if t['active'] and t['hard']]
    seen, ranked, feasible, skipped = set(), [], 0, []
    for row in sorted(evaluations, key=lambda r: (r['completion_index'] is None, r['completion_index'] or 0)):
        if not (row['valid'] and row['all_hard_constraints_satisfied'] and row['status'] == 'ok'):
            continue
        feasible += 1
        rows = [r for r in widths.get(row['evaluation_id'], []) if r['executed_value'] is not None]
        assignment = {}
        for r in rows:
            name = context.source_name(r['instance_path'], r['parameter_name'])
            if name is not None:
                assignment[r['instance_path'], name] = float(r['executed_value'])
        if set(assignment) != context.expected_keys or not all(math.isfinite(v) for v in assignment.values()):
            skipped.append(row['evaluation_id'])
            continue
        key = tuple(sorted((k, float(f'{v:.12g}')) for k, v in assignment.items()))
        if key in seen:
            continue
        seen.add(key)
        spec_values = values.get(row['evaluation_id'], {})
        margins = {t['metric_id']: _margin(t, spec_values[t['metric_id']]) for t in hard
                   if spec_values.get(t['metric_id']) is not None}
        if len(margins) != len(hard) or row['reward'] is None or not math.isfinite(row['reward']):
            skipped.append(row['evaluation_id'])
            continue
        tightest = min(margins, key=margins.get) if margins else None
        ranked.append(dict(evaluation_id=row['evaluation_id'], completion_index=row['completion_index'],
                           reward=row['reward'], min_margin=None if tightest is None else margins[tightest],
                           tightest_spec=tightest, spec_values=spec_values,
                           widths=[dict(variable_id=r['variable_id'], instance_path=r['instance_path'],
                                        parameter_name=r['parameter_name'], value=r['executed_value'], unit=r['unit'])
                                   for r in rows],
                           assignment=[dict(device=d, parameter=p, value=v) for (d, p), v in sorted(assignment.items())]))
    ranked.sort(key=lambda d: (-(d['min_margin'] if d['min_margin'] is not None else math.inf),
                               d['completion_index'] or 0))
    # A reference check diagnoses unreachable targets even when no search design passes nominal.
    if not context.mock:
        reference = reference_candidate(context)
        key = tuple(sorted(((a['device'], a['parameter']), float(f"{a['value']:.12g}")) for a in reference['assignment']))
        if key not in seen:
            ranked.append(reference)
    return ranked, dict(evaluations=len(evaluations), feasible=feasible, distinct=len(ranked), skipped=skipped)


def reference_candidate(context):
    graph = context.compiled.graph
    values = {g.id: g.value for g in graph.parameter_groups if g.mutable}
    assignment = graph.assignments(values)
    assignment = {(d, context.source_name(d, p) or p): v for (d, p), v in assignment.items()}
    if set(assignment) != context.expected_keys:
        raise CheckRefused('The reference does not specify exactly the writable parameters.', code='reference_parameters')
    return dict(evaluation_id='task_reference', label='Task reference (nominal feasibility not required)',
                completion_index=None, reward=None, min_margin=None, tightest_spec=None, spec_values={},
                widths=[dict(variable_id=m['variable_id'], instance_path=m['instance_path'],
                             parameter_name=m['parameter_name'], unit=v['unit'],
                             value=graph.parameters[m['instance_path']][m['parameter_name']].value)
                        for v in context.compiled.variables for m in v['members']],
                assignment=[dict(device=d, parameter=p, value=v) for (d, p), v in sorted(assignment.items())])


# ================================================================================ the plan (free)
def plan(run_dir, *, designs=MAX_DESIGNS) -> dict:
    """What a check of this run would do and cost. Local files only: nothing is contacted, written or started."""
    from .runs import run_status
    designs = max(1, min(MAX_DESIGNS, int(designs)))
    layout = RunLayout(Path(run_dir))
    manifest = read_json(layout.manifest)
    mock = bool(manifest.get('mock'))
    answer = dict(run_dir=str(layout.run_dir), run_id=manifest.get('run_id'),
                  task_key=(manifest.get('circuit') or {}).get('task_key'), mock=mock, supported=False, reason=None,
                  code=None, corners=[], designs=[], counts=None, simulations=0, limit=designs, max_designs=MAX_DESIGNS,
                  selection_rule=SELECTION_RULE, notice=MOCK_NOTICE if mock else None, checks=list_checks(layout.run_dir))
    if run_status(layout.run_dir).get('worker_alive'):
        return dict(answer, code='run_working',
                    reason='The run is still working. Check its designs once it has finished or is paused.')
    try:
        context = Context(layout, manifest)
    except CheckRefused as exc:
        return dict(answer, reason=str(exc), code=exc.code)
    ranked, counts = candidates(context)
    chosen = ranked[:designs]
    answer.update(corners=[corner_record(c) for c in context.corners], counts=counts, designs=chosen,
                  simulations=len(chosen) * len(context.corners))
    if not chosen:
        return dict(answer, code='no_feasible_design',
                    reason='This run has no design that met every hard spec at the normal condition, so there is '
                           'nothing to check at corners.')
    return dict(answer, supported=True)


# ================================================================================ starting one
def bridge_busy() -> bool:
    """A real run or real check holds the adapter's session lock (the same file every real task uses)."""
    return RunLock.held(repo_root() / BRIDGE_STATE / 'session.lock')


def live_checks(run_dir) -> list:
    return [c for c in list_checks(run_dir) if c['alive']]


def prepare(run_dir, *, designs, expected=None, simulations=None, allow_real=False, acknowledge_unknown=False,
            monitor=None):
    """Checks, the connection gate for a real circuit, then the check's folder with its request. Returns the folder.
    Refuses (CheckRefused, or runs.RunRejected from the gate) before anything is created."""
    proposal = plan(run_dir, designs=designs)
    if not proposal['supported']:
        raise CheckRefused(proposal['reason'], code=proposal['code'] or 'unsupported')
    chosen = proposal['designs']
    if expected is not None and [d['evaluation_id'] for d in chosen] != list(expected):
        raise CheckRefused('The designs to check changed since the page read them. Read the plan again and look.',
                           code='plan_changed')
    if simulations is not None and simulations != proposal['simulations']:
        raise CheckRefused(f"The check needs {proposal['simulations']} simulations, not {simulations}. Read the plan "
                           'again and look.', code='plan_changed')
    # "Is one already running?" and the worker's own lock used to be two separate calls with the API in between, so two
    # presses could both pass and two workers then size the SAME Virtuoso cell - the loser restoring against sizes the
    # winner had already overwritten (review of 2026-09-23). This run-scoped lock is held from here until `launch` has
    # the worker's lock, so the second press sees the first check.
    start = _start_lock(run_dir)
    try:
        if live_checks(run_dir):
            raise CheckRefused('A corner check of this run is already running.', code='already_running')
        return _prepared(run_dir, proposal, chosen, allow_real=allow_real, acknowledge_unknown=acknowledge_unknown,
                         monitor=monitor)
    except BaseException:
        _release_start(run_dir)
        raise


def _start_lock(run_dir):
    """One start at a time per run. Held by `prepare` and handed to `launch`, which releases it once the check's own
    worker lock is taken."""
    key = str(Path(run_dir).resolve())
    if key in _STARTING:
        raise CheckRefused('A corner check of this run is being started right now.', code='already_starting')
    lock = RunLock(Path(run_dir) / CHECK_DIR / 'control' / 'start.lock')
    try:
        lock.acquire()
    except RuntimeError:
        raise CheckRefused('A corner check of this run is being started right now.', code='already_starting')
    _STARTING[key] = lock
    return lock


def _release_start(run_dir):
    lock = _STARTING.pop(str(Path(run_dir).resolve()), None)
    if lock is not None:
        lock.release()


_STARTING = {}


def _prepared(run_dir, proposal, chosen, *, allow_real, acknowledge_unknown, monitor):
    from .runs import connection_gate
    layout = RunLayout(Path(run_dir))
    manifest = read_json(layout.manifest)
    gate = None
    if not proposal['mock']:
        if not allow_real:
            raise CheckRefused(REAL_AUTHORIZATION, code='real_authorization_required',
                               report=dict(simulations=proposal['simulations'], task_key=proposal['task_key']))
        if bridge_busy():
            raise CheckRefused('Virtuoso is in use by a real run or another corner check. Try again when it has '
                               'finished.', code='virtuoso_busy')
        context = Context(layout, manifest, allow_real=True)
        gate = connection_gate(context.task, context.config, monitor, acknowledge_unknown=acknowledge_unknown)
    check_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = layout.run_dir / CHECK_DIR / check_id
    directory.mkdir(parents=True, exist_ok=False)
    real = not proposal['mock']
    request = dict(version='corner-check-v1', check_id=check_id, run_id=proposal['run_id'], run_dir=str(layout.run_dir),
                   task_key=proposal['task_key'], mock=proposal['mock'], created_utc=iso(),
                   task_definition_hash=manifest.get('task_definition_hash'), corners=proposal['corners'],
                   designs=chosen, simulations=proposal['simulations'], counts=proposal['counts'],
                   selection_rule=SELECTION_RULE,
                   authorization=dict(real_simulation=real, authorized_simulations=proposal['simulations'] if real else None),
                   connection_gate=gate, notice=proposal['notice'],
                   notes=['Post-validation only: nothing of this check enters the run, its replay or its model.'])
    write_json(directory / 'request.json', request)
    write_json(directory / 'status.json', dict(state='starting', check_id=check_id, done=0, started=0,
                                               total=proposal['simulations'], created_utc=request['created_utc']))
    return directory


def launch(directory, *, allow_real=False) -> int:
    """The detached worker (own session, lock handed over as for a run). Never launched by tests or at import.
    The run's start lock, taken in `prepare`, is released once this check's own lock is held: from then on a second
    press sees a live check."""
    directory = Path(directory)
    lock = RunLock(directory / 'control' / 'check.lock')
    try:
        lock.acquire()
    except BaseException:
        _release_start(directory.parent.parent)
        raise
    _release_start(directory.parent.parent)
    from .runs import spawn_detached
    return spawn_detached('corner_check', ['--check-dir', str(directory)] + (['--allow-real'] if allow_real else []),
                          lock, directory / 'worker.log')


def request_stop(run_dir, check_id) -> dict:
    directory = check_directory(run_dir, check_id)
    if not RunLock.held(directory / 'control' / 'check.lock'):
        raise CheckRefused('This corner check is not running.', code='not_running')
    record = dict(id=uuid4().hex, command='stop', issued_utc=iso())
    write_json(directory / 'control' / 'stop.json', record)
    return record


# ================================================================================ reading
def check_directory(run_dir, check_id) -> Path:
    if not CHECK_ID.match(check_id or ''):
        raise CheckRefused('Not a corner check identifier.', code='bad_id')
    directory = Path(run_dir) / CHECK_DIR / check_id
    if not (directory / 'request.json').is_file():
        raise FileNotFoundError(check_id)
    return directory


def _state(directory, status):
    alive = RunLock.held(directory / 'control' / 'check.lock')
    if status.get('state') in LIVE and not alive:
        status = dict(status, state='interrupted',
                      note='The check process ended without finishing. Simulations it recorded are kept. For a real '
                           'circuit, look at the cell: the last design\'s widths may still be in it (the adapter\'s '
                           'journal in artifacts/local/bridge-state says what was written).')
    return alive, status


def list_checks(run_dir) -> list:
    root = Path(run_dir) / CHECK_DIR
    rows = []
    if root.is_dir():
        for directory in sorted(root.iterdir(), reverse=True):
            if not CHECK_ID.match(directory.name) or not (directory / 'request.json').is_file():
                continue
            request = read_json(directory / 'request.json', default={}) or {}
            alive, status = _state(directory, read_json(directory / 'status.json', default={}) or {})
            summary = read_json(directory / 'summary.json', default=None) or {}
            rows.append(dict(check_id=directory.name, created_utc=request.get('created_utc'), state=status.get('state'),
                             alive=alive, done=status.get('done', 0), total=request.get('simulations'),
                             mock=request.get('mock'), verdicts=summary.get('verdicts')))
    return rows


def check_status(run_dir, check_id) -> dict:
    directory = check_directory(run_dir, check_id)
    request = read_json(directory / 'request.json')
    alive, status = _state(directory, read_json(directory / 'status.json', default={}) or {})
    return dict(check_id=check_id, alive=alive, status=status, request=request,
                results=read_jsonl(directory / 'results.jsonl'),
                summary=read_json(directory / 'summary.json', default=None))


# ================================================================================ the worker
def _clean(result, evaluator):
    """Metrics a spec may use: finite, valid numbers from an evaluated OK simulation, else None (as the environment)."""
    metrics, validity = {}, {}
    for name in set(result.metrics) | set(evaluator.required_metrics):
        value = result.metrics.get(name)
        ok = (result.status == SimulationStatus.OK and result.candidate_evaluated
              and result.metric_validity.get(name) is True and isinstance(value, (int, float))
              and not isinstance(value, bool) and math.isfinite(value))
        metrics[name], validity[name] = (float(value) if ok else None), ok
    return replace(result, metrics=metrics, metric_validity=validity)


def grade(result, evaluator, targets):
    """(state, evaluation, failing specs) of one corner - the same rule as summarize_corners."""
    evaluation = evaluator.evaluate(result.metrics, result.metric_units, result.metric_validity)
    failing = []
    if result.status == SimulationStatus.OK and result.candidate_evaluated and evaluation.valid:
        state = 'passed' if evaluation.success else 'failed'
        for t in targets:
            value = result.metrics.get(t['metric_id'])
            if t['active'] and t['hard'] and value is not None:
                margin = _margin(dict(t, margin_sides='both'), value)
                if margin < 0:
                    failing.append(dict(metric_id=t['metric_id'], value=value, unit=t['unit'], lower=t['lower'],
                                        upper=t['upper'], violation=-margin))
        failing.sort(key=lambda f: -f['violation'])
    elif result.status in (SimulationStatus.INVALID_DESIGN, SimulationStatus.NONCONVERGED) and result.candidate_evaluated:
        state = 'failed'
    else:
        state = 'unknown'
    return state, evaluation, failing


class Worker:
    def __init__(self, directory, *, allow_real=False):
        self.directory = Path(directory)
        self.request = read_json(self.directory / 'request.json')
        self.layout = RunLayout(Path(self.request['run_dir']))
        self.allow_real = allow_real
        self.results, self.records = [], []
        self.started = self.done = self.invocations = 0
        self.error = self.restoration = None
        self.stop_requested = False
        self.status = read_json(self.directory / 'status.json', default={}) or {}

    # ---------------------------------------------------------------- bookkeeping
    def _write_status(self, state, **extra):
        self.status.update(state=state, check_id=self.request['check_id'], done=self.done, started=self.started,
                           total=self.request['simulations'], heartbeat_utc=iso(), pid=os.getpid(), **extra)
        write_json(self.directory / 'status.json', self.status)

    def _stop_wanted(self):
        if not self.stop_requested and (self.directory / 'control' / 'stop.json').is_file():
            self.stop_requested = True
            self._write_status('stopping')
        return self.stop_requested

    def _record(self, design_index, design, corner, condition, result, started_utc):
        result = _clean(result, self.context.evaluator)
        state, evaluation, failing = grade(result, self.context.evaluator, self.context.compiled.targets)
        self.results.append((design_index, result))
        self.done += 1
        if result.simulator_invocations:
            self.invocations += result.simulator_invocations
        artifact = Path(result.artifact_directory)
        record = dict(index=self.done, design=design_index, evaluation_id=design['evaluation_id'], corner=corner.id,
                      condition=asdict(condition), state=state, status=result.status.value,
                      reason_code=result.reason_code, candidate_evaluated=result.candidate_evaluated,
                      metrics=result.metrics, metric_units=dict(result.metric_units),
                      metric_validity=dict(result.metric_validity),
                      violations=evaluation.violations, evaluation_errors=evaluation.errors, failing=failing,
                      job_id=result.job_id, elapsed_seconds=result.elapsed_seconds,
                      simulator_invocations=result.simulator_invocations,
                      error_summary=redact(result.error_summary or '', 2000) or None,
                      artifact_directory=(str(artifact.relative_to(self.directory))
                                          if self.directory in artifact.parents else str(artifact)),
                      started_utc=started_utc, ended_utc=iso())
        self.appender.append(record)
        self.records.append(record)
        self._write_status('stopping' if self.stop_requested else 'running',
                           current=dict(design=design_index, corner=corner.id))
        return result

    # ---------------------------------------------------------------- the check
    def run(self) -> str:
        final = 'failed'
        self.appender = JsonlAppender(self.directory / 'results.jsonl')
        try:
            self._write_status('running', started_utc=iso())
            manifest = read_json(self.layout.manifest)
            if bool(manifest.get('mock')) != bool(self.request['mock']):
                raise CheckRefused('The run manifest and the check disagree about mock and real.', code='provenance')
            if not self.request['mock'] and not self.allow_real:
                raise CheckRefused(REAL_AUTHORIZATION, code='real_authorization_required')
            if manifest.get('task_definition_hash') != self.request.get('task_definition_hash'):
                raise CheckRefused('The run changed since the check was requested.', code='plan_changed')
            self.context = Context(self.layout, manifest, allow_real=not self.request['mock'])
            if [corner_record(c) for c in self.context.corners] != self.request['corners']:
                raise CheckRefused('The corners differ from the ones that were authorized.', code='plan_changed')
            self.designs = [(d, {(a['device'], a['parameter']): float(a['value']) for a in d['assignment']})
                            for d in self.request['designs']]
            if len(self.designs) * len(self.context.corners) != self.request['simulations']:
                raise CheckRefused('The number of simulations differs from the authorized one.', code='plan_changed')
            for design, assignment in self.designs:
                if set(assignment) != self.context.expected_keys:
                    raise CheckRefused(f"Design {design['evaluation_id']} does not write exactly the circuit's sizes.",
                                       code='plan_changed')
                if self.context.profile is not None:
                    self.context.profile.validate_assignment(assignment)
            (self._run_mock if self.request['mock'] else self._run_real)()
            final = 'stopped' if self.stop_requested and self.done < self.request['simulations'] else (
                'failed' if self.error else 'completed')
        except CheckRefused as exc:
            self.error = dict(code=exc.code, message=str(exc))
        except BaseException as exc:
            self.error = dict(code='exception', message=redact(f'{type(exc).__name__}: {exc}', 2000))
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                final = 'stopped'
        finally:
            self.appender.close()
            summary = self._summary(final)
            write_json(self.directory / 'summary.json', summary)
            if self.restoration and self.restoration.get('state') == 'recovery_required':
                final = 'failed'
            self._write_status(final, ended_utc=iso(), error=self.error, restoration=self.restoration,
                               verdicts=summary.get('verdicts'))
        return final

    def _in_order(self):
        for index, (design, assignment) in enumerate(self.designs):
            yield index, design, assignment

    def _required(self):
        return self.context.evaluator.required_metrics

    def _run_mock(self):
        from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
        from .tasks import MOCK_TARGETS
        graph, plan_, work = self.context.compiled.graph, self.context.compiled.plan, self.directory / 'work'
        kinds = {g.parameter_kind for g in graph.parameter_groups if g.mutable}
        timeout = self.context.config.run.advanced.simulation_timeout_seconds
        for index, design, assignment in self._in_order():
            for corner in self.context.corners:
                if self._stop_wanted():
                    return
                shift = MOCK_CORNER_SHIFT.get(corner.id, 0.0)
                backend = plan_.wrap(SyntheticSizingBackend(graph, targets={
                    k: max(-1.0, min(1.0, MOCK_TARGETS[k] + shift)) for k in kinds}))
                condition = SimulationCondition(corner, 'pvt_validation')
                started_utc = iso()
                backend.connect()
                try:
                    backend.set_parameters(dict(assignment))
                    artifact = backend.generate_netlist(work / 'exports')
                    self.started += 1
                    result = backend.run_simulation(SimulationRequest(artifact, work / 'simulations', self._required(),
                                                                      timeout, dict(assignment)))
                finally:
                    backend.close()
                self._record(index, design, corner, condition, replace(result, condition=condition), started_utc)

    def _bridge_parts(self):
        """(BridgeConfig, profile) - assembled exactly as tasks._real_runtime / generated_bridge_config do."""
        from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
        name = self.context.task_key.partition(':')[2]
        if name in tasks.REAL_PROFILES:
            connection = tasks.real_bindings(tasks._profile_settings(self.context.config.run.connection_profile_id)[1], name)
            config = BridgeConfig(Path(connection['env_file']).resolve(), connection['library'],
                                  Path(connection['creation_receipt']).resolve(), (repo_root() / BRIDGE_STATE).resolve(),
                                  connection['model_file'], profile=connection.get('profile'))
            return config, self.context.profile
        config, profile, _ = tasks.generated_bridge_config(name, self.context.config.run.connection_profile_id)
        return config, profile

    def _run_real(self):
        from .cdf_write import backend_class              # a task that writes by the PDK's form writes the same way here
        config, profile = self._bridge_parts()
        backend = self.context.compiled.plan.wrap(backend_class(profile)(config, profile))
        work = self.directory / 'work'
        timeout = self.context.config.run.advanced.simulation_timeout_seconds
        connected, initial, failures = False, None, 0
        try:
            backend.connect()
            connected = True
            initial = backend.read_parameters()
            for index, design, assignment in self._in_order():
                if self._stop_wanted():
                    break
                backend.set_parameters(dict(assignment))
                for corner in self.context.corners:
                    if self._stop_wanted():
                        break
                    condition = SimulationCondition(corner, 'pvt_validation')
                    started_utc = iso()
                    artifact = backend.generate_netlist(work / 'exports', condition=condition)
                    self.started += 1                                 # charged: the simulation is launched now
                    result = backend.run_simulation(SimulationRequest(artifact, work / 'simulations', self._required(),
                                                                      timeout, dict(assignment), condition=condition))
                    self._record(index, design, corner, condition, result, started_utc)
                    failures = failures + 1 if result.status.value in INFRASTRUCTURE else 0
                    if failures >= MAX_INFRASTRUCTURE_FAILURES:
                        self.error = dict(code='infrastructure', message=(
                            f'{failures} simulations in a row failed for a reason outside the design '
                            f'({result.status.value}: {redact(result.error_summary or result.reason_code, 300)}). '
                            'The check stopped so that no more budget is spent; the cell was restored.'))
                        return
        except BaseException as exc:
            self.error = dict(code='exception', message=redact(f'{type(exc).__name__}: {exc}', 2000))
        finally:
            self.restoration = self._restore(backend, connected, initial)

    def _restore(self, backend, connected, initial):
        """Write the recorded widths back and read them back - as the environment does when it closes."""
        record = dict(state='not_connected')
        try:
            if connected:
                backend.restore()
                actual = backend.read_parameters()
                same = initial is not None and actual.keys() == initial.keys() and all(
                    math.isclose(actual[k], v, rel_tol=1e-8, abs_tol=1e-24) for k, v in initial.items())
                record = dict(state='restored' if same else 'recovery_required',
                              parameters=[dict(device=d, parameter=p, value=v) for (d, p), v in sorted(actual.items())])
                if not same:
                    record['error'] = 'The widths read back after restoring differ from the ones recorded at the start.'
        except BaseException as exc:
            record = dict(state='recovery_required', error=redact(f'{type(exc).__name__}: {exc}', 2000))
        finally:
            try:
                backend.close()
            except BaseException as exc:
                record.setdefault('close_error', redact(f'{type(exc).__name__}: {exc}', 1000))
                if record['state'] == 'restored':
                    record['state'] = 'recovery_required'
        if record['state'] == 'recovery_required':
            session = getattr(backend, 'session_dir', None)
            record['journal'] = str(session) if session else None
        return record

    # ---------------------------------------------------------------- the verdicts
    def _summary(self, final) -> dict:
        context = getattr(self, 'context', None)
        summary = dict(check_id=self.request['check_id'], run_id=self.request['run_id'], task_key=self.request['task_key'],
                       mock=self.request['mock'], state=final, finished_utc=iso(), designs=[], verdicts=None,
                       budget=dict(authorized=self.request['authorization'].get('authorized_simulations'),
                                   simulations=self.request['simulations'], started=self.started, completed=self.done,
                                   simulator_invocations=self.invocations if not self.request['mock'] else None),
                       restoration=self.restoration, error=self.error,
                       grading='analog_optimizer.evaluation.corners.summarize_corners: every corner must pass every '
                               'required spec; one failed corner rejects a design; an unknown corner leaves it '
                               'inconclusive; robust_score = nominal reward - lambda x failed corners (ranking only)')
        if context is None or not getattr(self, 'designs', None):
            return summary
        lam = float(context.post.get('lambda_failed', 1.0))
        nominal = SimulationCondition(context.nominal)
        verdicts = dict(accepted=0, rejected=0, inconclusive=0)
        problem = task_definition_hash(context.config)
        for index, (design, assignment) in enumerate(self.designs):
            results = tuple(r for i, r in self.results if i == index)
            try:
                nominal_reward = design['reward']
                if nominal_reward is None:
                    measured = next((r for r in results if r.condition.corner.id == context.nominal.id), None)
                    if measured is None:
                        raise ValueError('No measured nominal result for the reference')
                    nominal_reward = context.evaluator.evaluate(measured.metrics, measured.metric_units, measured.metric_validity).reward
                    if nominal_reward is None:
                        raise ValueError('The reference nominal result is unavailable')
                entry = NominalDesign(design['evaluation_id'], problem, float(nominal_reward),
                                      tuple((d, p, v) for (d, p), v in sorted(assignment.items())), nominal, context.origin)
                outcome = summarize_corners(entry, context.corners, results, context.compiled.specs, lambda_failed=lam)
            except ValueError as exc:                      # a result that is not this design's: never graded
                summary['designs'].append(dict(evaluation_id=design['evaluation_id'], rank=index + 1,
                                               disposition='inconclusive', grading_error=redact(str(exc), 500)))
                verdicts['inconclusive'] += 1
                continue
            verdicts[outcome.disposition] += 1
            repeat = self._nominal_repeat(design, index)
            summary['designs'].append(dict(
                evaluation_id=design['evaluation_id'], rank=index + 1, disposition=outcome.disposition,
                complete=outcome.complete, passed_corners=outcome.passed_corners, failed_corners=outcome.failed_corners,
                unknown_corners=list(outcome.unknown_corners), pass_rate=outcome.pass_rate,
                robust_score=outcome.robust_score, worst_case_metrics=outcome.worst_case_metrics,
                corner_states={cid: detail['state'] for cid, detail in outcome.corner_details.items()},
                nominal_repeat=repeat, min_margin=design.get('min_margin'), tightest_spec=design.get('tightest_spec')))
        summary['verdicts'] = verdicts
        return summary

    def _nominal_repeat(self, design, index):
        """The nominal corner simulated again: the same spec values as the run recorded for this design?"""
        record = next((r for r in self.records if r['design'] == index and r['corner'] == self.context.nominal.id), None)
        if record is None:
            return dict(matches=None, differences=[])
        differences = []
        for name, before in (design.get('spec_values') or {}).items():
            after = record['metrics'].get(name)
            if before is None or after is None:
                continue
            if not math.isclose(before, after, rel_tol=1e-6, abs_tol=1e-12):
                differences.append(dict(metric_id=name, run=before, check=after))
        return dict(matches=not differences, differences=differences)


def execute(directory, *, allow_real=False, lock_fd=None) -> str:
    """The whole check in THIS process (the detached worker calls it; tests call it directly)."""
    directory = Path(directory)
    path = directory / 'control' / 'check.lock'
    lock = RunLock.adopt(path, lock_fd) if lock_fd is not None else RunLock(path)
    if not lock.held_here:
        lock.acquire()
    try:
        return Worker(directory, allow_real=allow_real).run()
    finally:
        lock.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Corner check worker: python -m gator_workbench.corner_check')
    parser.add_argument('--check-dir', type=Path, required=True)
    parser.add_argument('--allow-real', action='store_true',
                        help='Permit real Spectre simulations (explicit user authorization only)')
    parser.add_argument('--lock-fd', type=int, help='Inherited, already-locked check lock descriptor')
    args = parser.parse_args(argv)
    directory = args.check_dir.resolve()

    def request_stop(signum, _frame):
        # The same safe sequence as the Stop button: the simulation in flight ends, then the cell is restored.
        write_json(directory / 'control' / 'stop.json', dict(id=uuid4().hex, command='stop', issued_utc=iso(),
                                                             signal=signum))
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    state = execute(directory, allow_real=args.allow_real, lock_fd=args.lock_fd)
    print(f'CORNER CHECK {args.check_dir.name} ended: {state}', flush=True)
    return 0 if state in ('completed', 'stopped') else 1


if __name__ == '__main__':
    raise SystemExit(main())
