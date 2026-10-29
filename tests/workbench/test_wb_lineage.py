"""Relationships, the backend half (record 7.264; plan docs/plan-frontend-run-workflow.md, "Relationships and history:
data"): the run list and the status route pass on where a run's model came from, as its manifest recorded it - the
parent run and save point of a fine-tune, the template network of a new model, an offline model's recorded source runs.
MOCK runs in-process; nothing is inferred from names or folder paths."""
import json

from fastapi.testclient import TestClient

from gator_workbench import runs
from gator_workbench.storage.atomic import read_json
from helpers import execute, make_config, roots_for, workbench_app


def rows_by_dir(root):
    """Index listed run records by their run directories."""
    return {row['run_dir']: row for row in runs.list_runs(roots_for(root), root)}


def test_a_new_model_a_fine_tune_of_it_and_their_status(tmp_path):
    first, _ = execute(make_config(tmp_path, run=dict(max_evaluations=6)), tmp_path)
    network = read_json(first.effective_config)['run']['network']
    tuned_config = make_config(tmp_path, run=dict(max_evaluations=6, mode='fine_tune', network=network))
    tuned_config.run.model_source.run_dir = str(first.run_dir)
    tuned, _ = execute(tuned_config, tmp_path)
    rows = rows_by_dir(tmp_path)
    new, child = rows[str(first.run_dir)], rows[str(tuned.run_dir)]
    assert new['parent'] is None and new['run_kind'] == 'optimization' and new['encoder'] == 'graph_transformer'
    assert new['pretraining_sources'] is None
    point = child['parent']['checkpoint_id']
    assert child['parent']['run_dir'] == str(first.run_dir) and child['parent']['relation'] == 'fine_tune' and point.startswith('ckpt-')
    assert child['parent']['run_id'] == new['run_id'] and child['mode'] == 'fine_tune'
    client = TestClient(workbench_app(tmp_path))
    status = client.get('/api/runs/status', params=dict(run_dir=str(tuned.run_dir))).json()['manifest']
    assert status['parent'] == child['parent'] and status['run_kind'] == 'optimization' and status['encoder'] == 'graph_transformer'
    assert status['pretraining'] is None and status['task_definition_hash'] == child['task_definition_hash'] and status['created_utc']
    # the saved-model list is built from the run rows: it carries the same lineage
    models = {m['run_dir']: m for m in client.get('/api/runs/models', params=dict(output_root=str(tmp_path))).json()['models']}
    assert models[str(tuned.run_dir)]['parent'] == child['parent'] and models[str(first.run_dir)]['encoder'] == 'graph_transformer'


def test_an_offline_model_names_how_many_recorded_runs_it_learned_from(tmp_path):
    run = tmp_path / 'offline-network__0123456789ab' / 'runs' / 'general' / 'offline__seed0__0123456789ab'
    run.mkdir(parents=True)
    sources = [dict(run_dir=f'/recorded/run{i}', run_id=f'r{i}', task=f'real:t{i}', archive_sha256='x', evaluations=800 + i,
                    eligible=700, excluded=0, relabeled=0) for i in range(3)]
    (run / 'run_manifest.json').write_text(json.dumps(dict(
        run_id='offline-0123', run_kind='offline_pretraining', mode='scratch', mock=False, created_utc='2026-10-06T10:00:00+00:00',
        parent=None, experiment_name='offline-network', experiment_id='0123456789ab', model_label='general',
        architecture=dict(network=dict(encoder_type='graph_transformer')),
        pretraining=dict(sources=sources, source_evaluations=2403, split_sha256='y', review={}))))
    (run / 'status.json').write_text(json.dumps(dict(state='completed')))
    row = rows_by_dir(tmp_path)[str(run)]
    assert row['run_kind'] == 'offline_pretraining' and row['pretraining_sources'] == 3 and row['parent'] is None
    client = TestClient(workbench_app(tmp_path))
    status = client.get('/api/runs/status', params=dict(run_dir=str(run))).json()['manifest']
    assert status['pretraining']['source_evaluations'] == 2403
    assert status['pretraining']['sources'] == [dict(run_dir=s['run_dir'], run_id=s['run_id'], task=s['task'], evaluations=s['evaluations'])
                                                for s in sources]
