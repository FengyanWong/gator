"""An experiment folder's registry of its runs (experiment.json) and its split manifest (split_manifest.json),
updated as each run is created; the data dictionary written beside them.

Moved from runs.py by the refactoring (docs/plan-refactoring.md); runs.py re-exports both names.
"""
from __future__ import annotations

from pathlib import Path

from . import OUTPUT_LAYOUT_VERSION
from .run_definitions import RunRejected
from .run_lock import RunLock
from .storage.atomic import read_json, write_json
from .storage.dataset import write_data_dictionary


def register_in_experiment(experiment_dir, manifest, compiled, task, created):
    """Add the run to the experiment's run list and split manifest; raise RunRejected if the lock is busy."""
    experiment_dir = Path(experiment_dir)
    lock = RunLock(experiment_dir / '.experiment.lock')
    import time
    for _ in range(200):
        try:
            lock.acquire(patience=0)            # this loop is its own patience (10 s)
            break
        except RuntimeError:
            time.sleep(0.05)
    else:
        # It used to fall through and do the read-modify-write anyway: two starts within the same seconds then lost one
        # run from experiment.json and split_manifest.json, silently (review of 2026-09-23). Refusing a start is the
        # lesser harm - nothing has been created yet, and the user can simply press Start again.
        raise RunRejected(f'Another run is being registered in {experiment_dir} right now (10 s). Nothing was created; '
                          'start it again in a moment.', code='experiment_busy')
    try:
        if created or not (experiment_dir / 'data_dictionary.json').exists():
            write_data_dictionary(experiment_dir / 'data_dictionary.json')
        experiment = read_json(experiment_dir / 'experiment.json', default=None) or dict(
            layout_version=OUTPUT_LAYOUT_VERSION, experiment_id=manifest['experiment_id'],
            experiment_name=manifest['experiment_name'], created_utc=manifest['created_utc'], mock=manifest['mock'],
            mock_notice=manifest['mock_notice'], runs=[])
        experiment['runs'].append(dict(run_id=manifest['run_id'], task_id=manifest['task_id'], mode=manifest['mode'],
                                       seed=manifest['seeds']['target_seed'],
                                       relative_run_dir=manifest['output']['relative_run_dir'],
                                       created_utc=manifest['created_utc']))
        write_json(experiment_dir / 'experiment.json', experiment)
        _update_split_manifest(experiment_dir, manifest, compiled, task)
    finally:
        lock.release()


def _update_split_manifest(experiment_dir, manifest, compiled, task):
    path = Path(experiment_dir) / 'split_manifest.json'
    split = read_json(path, default=None) or dict(layout_version=OUTPUT_LAYOUT_VERSION, tasks=[], overlap_warnings=[])
    entry = dict(task_id=manifest['task_id'], task_name=manifest['task_name'], role=manifest['split'],
                 generalization_level=manifest['generalization_level'], circuit_class=task.circuit.get('circuit_class'),
                 topology_id=task.circuit.get('topology_id'), netlist_sha256=task.circuit.get('netlist_sha256'),
                 specification=[dict(metric_id=t['metric_id'], lower=t['lower'], upper=t['upper'], hard=t['hard'])
                                for t in compiled.targets if t['active']],
                 variable_ranges=[dict(variable_id=v['variable_id'], lower=v['lower'], upper=v['upper'], unit=v['unit'])
                                  for v in compiled.variables if v['optimized']],
                 initial_values=manifest['initial_dimensions'],
                 training_sources=manifest['research']['training_sources'],
                 runs=[manifest['run_id']])
    existing = next((t for t in split['tasks'] if t['task_id'] == entry['task_id'] and t['role'] == entry['role']),
        None)
    if existing:
        existing['runs'].append(manifest['run_id'])
    else:
        split['tasks'].append(entry)
    warnings = []
    tasks = split['tasks']
    for i, first in enumerate(tasks):
        for second in tasks[i + 1:]:
            if first['role'] == second['role'] or 'unspecified' in (first['role'], second['role']):
                continue
            same_netlist = first['netlist_sha256'] and first['netlist_sha256'] == second['netlist_sha256']
            same_spec = first['specification'] == second['specification']
            if same_netlist and same_spec:
                warnings.append(
                    f"{first['task_id']} ({first['role']}) and {second['task_id']} ({second['role']}) share the "
                                'same netlist AND specification: identical task across partitions.')
            elif same_netlist and 'unseen_topology' in (first['generalization_level'], second['generalization_level']):
                warnings.append(
                    f"{first['task_id']} and {second['task_id']} share a netlist but one is labelled unseen_topology.")
            if (second['generalization_level'] == 'unseen_circuit_class'
                    and second['circuit_class'] in (second['training_sources'] or [])):
                warnings.append(
                    f"{second['task_id']}: unseen_circuit_class but its class is listed in training_sources.")
    split['overlap_warnings'] = sorted(set(warnings))
    split['counts'] = {role: sum(1 for t in tasks if t['role'] == role)
                       for role in ('train', 'validation', 'test', 'unspecified')}
    split['limitations'] = ('Overlap checks compare netlist hashes and specifications. A differing hash does NOT prove '
                            'the absence of leakage: renamed or reordered copies of one topology hash differently. Use '
                            'analog_optimizer.evaluation.transfer.same_topology for an exact isomorphism check.')
    write_json(path, split)


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_register_in_experiment = register_in_experiment
