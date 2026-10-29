"""The fixed one-evaluation baseline launched when a task is saved for the first time.

The saved task supplies the circuit and rows. Training controls on the page cannot turn
this into training, transfer, calibration, a retry, or more than one simulator launch.
"""
from types import SimpleNamespace
from pathlib import Path
from threading import Lock

from .. import runs, schema, session_routing, tasks, units
from ..security import redact
from ..storage.atomic import read_json, write_json

_LOCK = Lock()
FILE = 'baseline_launch.json'


def _directory(task_key):
    from .. import profiles, ngspice_tasks  # lazy: profiles and ngspice_tasks import the optimizer (torch)
    kind, _, name = task_key.partition(':')
    entry = profiles.profile_entry(name) if kind == 'real' else (
        ngspice_tasks.list_tasks() if kind == 'ngspice' else {}).get(name)
    if entry is None:
        raise ValueError('Choose a saved circuit task for its baseline.')
    return Path(entry['directory'])


def status(task_key):
    """Read the saved baseline setup and refresh its state from the associated run when present."""
    try:
        result = read_json(_directory(task_key) / FILE, default=None)
    except ValueError:
        return None
    if result and result.get('run_dir'):
        current = runs.run_status(result['run_dir'])
        result = dict(result, state=current.get('state'), worker_alive=current.get('worker_alive'),
                      reason=current.get('error'), failed=(current.get('budget') or {}).get('failed', 0))
    return result


def configuration(task_key, *, profile_id=None, output_root=None):
    """Build a single-evaluation nominal baseline configuration from the saved task."""
    starter = tasks.starter_config(task_key)
    if task_key.startswith('ngspice:'):
        # The imported deck stays unchanged. A current source is fixed in that deck;
        # the SAC-compatible graph cannot expose its current as an action group.
        starter = dict(starter, parameters=[p for p in starter.get('parameters', [])
            if not (p.get('parameter_name') == 'dc' and units.canonical_unit(p.get('unit', '1')) == 'A')])
    # A newly imported ngspice deck has no optimization specs yet. Check only that
    # its measurements exist: x - x == 0 for every finite result, with no invented
    # circuit performance target. These checks belong to this run, never the task.
    if not starter.get('targets'):
        starter = dict(starter, targets=[dict(metric_id=f'baseline_{i}',
            equation=f'{row["measurement_id"]} - {row["measurement_id"]}',
            unit=row.get('unit') or '1', constraint='>=', lower=0, normalization_scale=1)
            for i, row in enumerate(starter.get('measurements', [])) if row.get('enabled', True)])
    return schema.WorkbenchConfig.model_validate(dict(starter,
        run=dict(mode='scratch', seed=0, concurrency=1, max_evaluations=1,
                 max_spectre_launches=1, max_retries=0, connection_profile_id=profile_id,
                 conditions=dict(policy='off'), stop_at_first_feasible=False),
        output=dict(output_root=output_root, experiment_name='task-baselines',
                    save_checkpoints=False, save_replay_snapshots=False,
                    save_transition_archive=False, save_learner_updates=False)))


def after_save(context, made, *, profile_id=None, output_root=None, session=None):
    """Save is the authorization for one baseline. A blocked launch never undoes a saved task.

    Also replace an invalidated reference after an in-place circuit/setup update;
    a specs-only save retaining its reference does not launch anything.
    `session`: the Virtuoso session the save chose (record 7.351), handed to its baseline - or let go when none starts.
    """
    if not made.get('created') and made.get('baseline_kept', True):
        session_routing.finished(session)
        return
    made['baseline'] = start(context, made['task_key'], profile_id=profile_id, output_root=output_root, session=session)


def start(context, task_key, *, profile_id=None, output_root=None, session=None):
    """Fixed baseline, also used to retry a failed/blocked creation baseline. Concurrent presses reuse the live run."""
    with _LOCK:
        return _start(context, task_key, profile_id=profile_id, output_root=output_root, session=session)


def _start(context, task_key, *, profile_id, output_root, session=None):
    try:
        previous = status(task_key)
        if previous and previous.get('worker_alive'):
            session_routing.finished(session)
            return previous
        from .run_routes import start_run  # lazy: in the try: a failure of the import is handled with the rest
        config = configuration(task_key, profile_id=profile_id, output_root=output_root)
        # Creation authorizes one bounded attempt. A probe's unknown result may be
        # resolved by that attempt; known connection/readiness failures still block.
        body = SimpleNamespace(authorize_real_simulation=True, acknowledge_unknown_connection=True,
            automatic_baseline=True)
        started = start_run(context, config, body, baseline_only=True, session=session)
        result = dict(state='started', **started)
    except Exception as exc:
        session_routing.finished(session)                  # not handed to a worker: it goes back (again: no harm)
        detail = getattr(exc, 'detail', None)
        reason = detail.get('message') if isinstance(detail, dict) else str(exc)
        if isinstance(detail, dict):
            issues = (detail.get('report') or {}).get('issues', [])
            problems = [i['message'] for i in issues if i.get('level') in ('error', 'blocker')]
            if problems:
                reason = f'{reason}: ' + '; '.join(problems)
        result = dict(state='blocked', reason=redact(reason or str(exc), 1200))
    try:
        write_json(_directory(task_key) / FILE, result)
    except (ValueError, OSError):
        pass                       # the save response still reports the launch or refusal
    return result
