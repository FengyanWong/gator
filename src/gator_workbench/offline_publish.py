"""Expose offline weights as a model-only run with explicit historical cost."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from . import OUTPUT_LAYOUT_VERSION, checkpoints, families
from .layout import RunLayout
from .pretrain import identity
from .runs import vocabulary_record
from .storage.atomic import read_json, write_json
from .storage.dataset import RawDataset
from .vocabulary import write_run_vocabulary


def publish(training_dir, output_root, *, label, review):
    """A recorded human/experiment review is required; publication is never a transfer claim."""
    source, root = Path(training_dir), Path(output_root)
    request, pool, status = (read_json(source / f'{name}.json') for name in ('request', 'pool', 'status'))
    if status['state'] != 'trained_unqualified' or status['updates'] != request['updates']:
        raise ValueError('Offline training has not finished')
    if not review or not review.get('allow_planned_probes') or not review.get('reason'):
        raise ValueError('Publication requires a recorded diagnostic review')
    if identity(request) != pool['request_sha256']:
        raise ValueError('Offline request changed')
    point = checkpoints.resolve_checkpoint(source, 'latest')
    problems = checkpoints.verify_files(point)
    if problems:
        raise ValueError(f'Checkpoint integrity failure: {problems}')
    meta = checkpoints.read_metadata(point)
    if (meta['task_definition_hash'] != pool['request_sha256'] or
            meta['counters']['learner_updates'] != status['updates'] or
            identity(meta['contract']['spec_schema']) != identity(pool['spec_schema'])):
        raise ValueError('Checkpoint does not match the completed offline request')
    if pool['origin'] == 'synthetic':
        root = root / 'mock'
    run_id, now = meta['run_id'], datetime.now(timezone.utc).isoformat()
    experiment_id = pool['request_sha256'][:12]
    experiment = root / f'offline-network__{experiment_id}'
    directory = experiment / 'runs' / 'general' / f'offline__seed{request["seed"]}__{run_id[:12]}'
    directory.mkdir(parents=True, exist_ok=False)
    layout = RunLayout(directory)
    layout.create()
    shutil.copytree(point, layout.checkpoints / point.name)
    for name in ('latest.json', 'best_policy.json'):
        shutil.copyfile(source / 'checkpoints' / name, layout.checkpoints / name)
    for name in ('request', 'pool', 'spec_registry', 'validation'):
        shutil.copyfile(source / f'{name}.json', directory / f'{name}.json')
    if (source / 'qualification.json').exists():
        shutil.copyfile(source / 'qualification.json', directory / 'qualification.json')
    write_json(directory / 'diagnostic_review.json', review)
    # The component list the weights were built with, kept as a run keeps it (record 7.319): without it the model
    # chooser read a family-list model as one of the standard list and refused it. The family list is kept without a
    # PDK's mapping - a pool may hold several PDKs, and a run that loads the model maps its own task's.
    built_with = (meta['contract'].get('feature_schema') or {}).get('version', '').partition('+')[0]
    listed = families.FamilyList(families.block_for(None)) if built_with == families.VERSION else None
    write_run_vocabulary(directory, listed)
    mock = pool['origin'] == 'synthetic'
    manifest = dict(layout_version=OUTPUT_LAYOUT_VERSION, run_id=run_id, task_id=meta['task_id'],
        task_name=label, model_label=label, task_definition_hash=meta['task_definition_hash'],
        config_sha256=pool['request_sha256'], experiment_id=experiment_id, experiment_name='offline-network',
        run_kind='offline_pretraining', mode='scratch', provenance='mock' if mock else 'real', mock=mock,
        state='completed', created_utc=now, circuit=dict(task_key=meta['task_id'], circuit_class='multi_task'),
        seeds=dict(target_seed=request['seed'], pretrain_seed=request['seed']), research=dict(split='train'),
        pretraining=dict(sources=pool['sources'], source_evaluations=pool['source_evaluations'],
                         split_sha256=pool['split_sha256'], review=review),
        architecture=dict(network=meta['contract']['model_config'], sac=meta['contract']['sac_config'],
                          spec_schema=pool['spec_schema'], vocabulary=vocabulary_record(listed)),
        budgets=dict(max_evaluations=0, max_spectre_launches=0), parent=None,
        segments=[dict(segment=1, entry='offline', ended_utc=now, end_state='completed',
                       active_seconds=status['elapsed_seconds'])],
        notes=['Offline training on recorded data. No target circuit or new simulations. Weights-only transfer.'])
    write_json(layout.manifest, manifest)
    # This is deliberately an offline config, not a fabricated configuration of one source circuit.
    write_json(layout.effective_config, dict(format='gator-offline-config-v1', request=request,
        run=dict(network=meta['contract']['model_config'], advanced=meta['contract']['sac_config']), targets=[]))
    write_json(layout.summary, dict(run_id=run_id, state='completed',
        totals=dict(candidate_evaluations_charged=0, spectre_launches=0, gradient_updates=status['updates']),
        target_task_cost=dict(evaluations_charged=0, spectre_launches=0),
        source_model_cost=dict(status='known', evaluations_charged=pool['source_evaluations']),
        output=dict(resumability='weights_only'), first_feasible_eval_count=None))
    write_json(layout.status, dict(run_id=run_id, mode='scratch', mock=mock, state='completed',
        stop_reason='offline_update_budget', budget=dict(charged=0, launches=0), heartbeat_utc=now,
        paths=layout.subpaths()))
    write_json(experiment / 'experiment.json', dict(experiment_id=experiment_id, experiment_name='offline-network',
        origin=pool['origin'], runs=[dict(run_id=run_id, run_dir=str(directory))]))
    dataset = RawDataset(layout.data)
    dataset.close()
    return layout
