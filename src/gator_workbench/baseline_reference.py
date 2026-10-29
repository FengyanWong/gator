"""A saved task's real baseline: a finished Baseline simulation (or a calibration's baseline evaluation) of the task
becomes its recorded reference, by itself once the run ends (record 7.78) or when the task is loaded and a baseline
made before is found; a reference is never replaced.

Moved from profiles.py by the refactoring (docs/plan-refactoring.md); profiles.py re-exports every name.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from . import recipes, run_index
from .circuit_types import MAESTRO
from .layout import find_runs
from .profile_store import FILES, ProfileError, profile_entry, reference_metrics
from .storage.atomic import UNREADABLE, read_json_quiet, sha256_file as _sha256, write_json
from .storage.dataset import utcnow


# ---------------------------------------------------------------------------------- the first real baseline
def record_reference(name, run_dir) -> dict:
    """The REAL baseline of a finished run of `real:<name>` becomes the profile's reference: from then on every
    worker's first evaluation is compared with it (`NativeEnvironmentFactory.reference_metrics`), as for the four
    verified profiles. Taken from the run's own tables - the raw backend metrics of the evaluation with phase
    `baseline` - and only when that evaluation is real, came from a simulation and every metric of the recipe is
    there and valid. An existing reference is never replaced: a reference that moves is not a reference."""
    from .storage.dataset import DatasetReader  # lazy: tests patch storage.dataset.DatasetReader
    entry = profile_entry(name)
    if entry is None:
        raise ProfileError(f'Unknown generated profile {name!r}')
    directory, run_dir = Path(entry['directory']), Path(run_dir)
    target = directory / FILES['reference']
    if target.exists():
        raise ProfileError(f'real:{name} already has a recorded baseline; it is never replaced. To start over, delete the task and save it again.')
    try:
        config = json.loads((run_dir / 'effective_config.json').read_text())
        manifest = json.loads((run_dir / 'run_manifest.json').read_text())
    except (OSError, ValueError):
        raise ProfileError('Not a finished run directory')
    if (config.get('circuit') or {}).get('task_id') != f'real:{name}' or manifest.get('mock'):
        raise ProfileError(f'That run did not simulate real:{name}')
    # ---- Select the real baseline and require complete recipe metrics before writing a reference.
    reader = DatasetReader(run_dir / 'data')
    baselines = [row for row in reader.rows('evaluations', ['evaluation_id', 'phase', 'provenance', 'result_source', 'completed_at'])
                 if row['phase'] == 'baseline' and row['provenance'] == 'real' and row['result_source'] == 'simulation']
    if not baselines:
        raise ProfileError('That run holds no real baseline simulation')
    evaluation = baselines[0]['evaluation_id']
    # The simulator's own results are the per-condition rows (a spec computed by a formula has no measurement_id either).
    raw = {row['metric_name']: row for row in reader.rows('metrics', ['evaluation_id', 'measurement_id', 'metric_name', 'raw_value', 'unit',
                                                                      'valid', 'aggregation_level'])
           if row['evaluation_id'] == evaluation and row['measurement_id'] is None and row['aggregation_level'] == 'condition'}
    # A task measured by Maestro names its own results (its outputs; `recipes.provided_metrics` has none for it) - found
    # on the user's first real baseline, 2026-09-24: with the recipe's empty tuple every Maestro baseline was "unexpected".
    expected = list(entry.get('provided_metrics') or ()) if entry.get('recipe') == MAESTRO else list(recipes.provided_metrics(entry['recipe']))
    if not expected:
        raise ProfileError(f'real:{name} names no result to record (its provided_metrics are empty)')
    problems = [metric for metric in expected if metric not in raw or not raw[metric]['valid'] or raw[metric]['raw_value'] is None]
    if problems or set(raw) != set(expected):
        raise ProfileError('The baseline of that run is not a complete, valid measurement '
                           f'(missing or invalid: {", ".join(problems) or "unexpected metrics " + ", ".join(sorted(set(raw) - set(expected)))})')
    reference = dict(origin='real', profile=name, run_dir=str(run_dir), run_id=manifest.get('run_id'), evaluation_id=evaluation,
                     completed_at=str(baselines[0]['completed_at']), recorded_utc=utcnow().isoformat(),
                     metrics={metric: raw[metric]['raw_value'] for metric in expected},
                     metric_units={metric: raw[metric]['unit'] for metric in expected},
                     note='Raw backend metrics of the baseline evaluation, read from the run\'s metrics table.')
    write_json(target, reference)
    write_json(directory / FILES['entry'], dict({k: v for k, v in entry.items() if k not in ('directory', 'baseline_attempt')},
                                                status='baseline recorded: one real simulation of the recorded sizes',
                                                baseline_recorded_utc=reference['recorded_utc']))
    return reference


def latest_baseline_run(name, run_dirs):
    """The newest run among `run_dirs` whose baseline can become the reference of real:<name>, or None."""
    for run_dir in run_dirs:
        config = read_json_quiet(Path(run_dir) / 'effective_config.json', UNREADABLE)
        if config is UNREADABLE:
            continue
        if (config.get('circuit') or {}).get('task_id') == f'real:{name}':
            return str(run_dir)
    return None


# ---------------------------------------------------------------------------------- a finished Baseline simulation records itself
BASELINE_KIND = 'baseline_preflight'                 # run_kind of the header's "Baseline simulation" (api/app.py `_start`)


def _run_outlived_the_task(entry, manifest) -> str | None:
    """Why a run cannot be the reference of the task as it is NOW, or None. A task saved again after the run (its cell,
    its parameters, its Maestro setup: `write_setup_on` keeps the reference only when no baseline part changed) is not
    the task that run simulated, so an older run's baseline would describe a task that no longer exists."""
    circuit = manifest.get('circuit') or {}
    directory = Path(entry['directory'])
    try:
        current = dict(netlist_sha256=_sha256(directory / FILES['structure']), parser_config_sha256=_sha256(directory / FILES['mapping']))
    except OSError:
        return 'the task files cannot be read'
    if any(circuit.get(key) != value for key, value in current.items()):
        return 'the task was saved again after that run (its cell or its parameters differ)'
    saved, created = entry.get('saved_utc'), manifest.get('created_utc')
    try:
        if saved and created and datetime.fromisoformat(created) < datetime.fromisoformat(saved):
            return 'the task was saved again after that run'
    except ValueError:
        pass
    return None


def adopt_baseline_run(run_dir, manifest=None) -> dict | None:
    """A finished "Baseline simulation" of a generated task becomes the task's reference BY ITSELF - until record
    7.78 (2026-09-24) "Record the baseline run as reference" was a press of its own, and after the user's first real
    baseline the Project column still said "no real baseline yet". The worker calls this at the end of such a run
    (engine.py `_adopt_baseline`); for a run made before that, `adopt_latest_baseline` does it when the task is loaded.

    None when the run is not one to record (an optimization run, a MOCK run, a built-in circuit): nothing to say.
    Otherwise dict(recorded, name, note) - the note is the sentence for the run's manifest. A refused measurement
    (incomplete, invalid) is kept in the task's entry as `baseline_attempt`, so the column can say why the task still
    has no baseline; a run the task has outlived is left alone. A reference is never replaced."""
    run_dir = Path(run_dir)
    if manifest is None:
        manifest = read_json_quiet(run_dir / 'run_manifest.json', UNREADABLE)
        if manifest is UNREADABLE:
            return None
    task_key = (manifest.get('circuit') or {}).get('task_key') or ''
    if manifest.get('run_kind') != BASELINE_KIND or manifest.get('mock') or not task_key.startswith('real:'):
        return None
    name = task_key[len('real:'):]
    entry = profile_entry(name)
    if entry is None:
        return None
    # A run asked to calibrate (record 7.197) goes on after its baseline with random designs: stopped by the user among
    # them, its baseline evaluation is as finished as that of a run of one evaluation (`record_reference` looks at it).
    if manifest.get('state') != 'completed' and not (manifest.get('state') == 'stopped' and manifest.get('calibration')):
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: the run ended as {manifest.get("state")}.')
    if reference_metrics(name) is not None:
        return dict(recorded=False, name=name, note=f'{task_key} already has a recorded baseline; it is never replaced.')
    outlived = _run_outlived_the_task(entry, manifest)
    if outlived:
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: {outlived}.')
    attempt = entry.get('baseline_attempt') or {}
    if attempt.get('run_id') and attempt.get('run_id') == manifest.get('run_id'):      # tried before: the answer has not changed
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: {attempt["reason"]}', attempt=attempt)
    try:
        reference = record_reference(name, run_dir)
    except ProfileError as exc:
        attempt = dict(run_id=manifest.get('run_id'), run_dir=str(run_dir), reason=str(exc),
                       ended_utc=((manifest.get('segments') or [{}])[-1]).get('ended_utc') or manifest.get('created_utc'))
        write_json(Path(entry['directory']) / FILES['entry'], dict({k: v for k, v in entry.items() if k != 'directory'}, baseline_attempt=attempt))
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: {exc}', attempt=attempt)
    return dict(recorded=True, name=name, reference=reference,
                note=f'Recorded as the reference of {task_key}: every later run compares its first evaluation with this result.')


def adopt_latest_baseline(name, data_root) -> dict | None:
    """The newest completed Baseline simulation of real:<name> under the output root becomes its reference - for
    a run made before such runs recorded themselves. Called when a generated task without a reference is loaded
    (api/app.py `circuit_load`); reads the run manifests only, one small file per run, and never once a reference
    exists. Only the newest completed one is tried: a refusal is remembered in the entry and said in the column.
    The manifests come from the run list's cache, read many runs at a time (record 7.279: every manifest was read
    on each such load, 2.3 s instead of 0.2 s)."""
    import copy
    newest = None
    found = find_runs(data_root, manifest=False)
    for run_dir, facts in zip(found, run_index.read_many(run_index.run_facts, found)):
        if facts is None:                          # no readable manifest
            continue
        manifest = facts['manifest']
        if (manifest.get('run_kind') == BASELINE_KIND and manifest.get('state') == 'completed' and not manifest.get('mock')
                and (manifest.get('circuit') or {}).get('task_key') == f'real:{name}'
                and (newest is None or (manifest.get('created_utc') or '') > newest[0])):
            newest = (manifest.get('created_utc') or '', run_dir, manifest)
    if newest is None:
        return None
    outcome = adopt_baseline_run(newest[1], manifest=copy.deepcopy(newest[2]))       # the cache's own stays as read
    return outcome if outcome and outcome['recorded'] else None
