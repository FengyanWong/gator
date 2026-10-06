"""The run window's "Can continue" and the Run status tab's Continue (record 7.215): a run whose folder no longer holds
its save point - record 7.213's viewing copies of recorded runs, deleted save points - says "no" and offers nothing to
continue from, whatever its summary wrote when it came to rest. Files only: no run is started."""
import json
import shutil

from fastapi.testclient import TestClient

from gator_workbench import runs
from gator_workbench.api import create_app
from helpers import roots_for

POINT = 'ckpt-000800-final'


def fabricate(root, name, *, resumability='full_state', save=True, summary=True, state='completed'):
    run = root / 'mock' / 'exp__0123456789ab' / 'runs' / 'task' / name
    run.mkdir(parents=True)
    (run / 'run_manifest.json').write_text(json.dumps(dict(mock=True, experiment_name='exp', experiment_id='0123456789ab',
                                                           run_id=name[-12:], created_utc='2026-10-05T18:00:00+00:00')))
    (run / 'status.json').write_text(json.dumps(dict(state=state)))
    if summary:
        (run / 'run_summary.json').write_text(json.dumps(dict(output=dict(resumability=resumability, completeness='complete',
                                                                          latest_checkpoint=POINT if save else None))))
    if save:
        (run / 'checkpoints' / POINT).mkdir(parents=True)
        (run / 'checkpoints' / POINT / 'metadata.json').write_text(json.dumps(dict(checkpoint_id=POINT, restoration_capability=resumability)))
        (run / 'checkpoints' / 'latest.json').write_text(json.dumps(dict(checkpoint_id=POINT)))
    return run


def rows(root):
    return {row['run_id']: row['resumability'] for row in runs.list_runs(roots_for(root), root)}


def test_a_run_that_holds_its_save_point_says_what_the_summary_says(tmp_path):
    whole = fabricate(tmp_path, 'scratch__seed0__aaaaaaaaaaaa')
    fabricate(tmp_path, 'scratch__seed0__bbbbbbbbbbbb', resumability='weights_only')
    assert rows(tmp_path) == {'aaaaaaaaaaaa': 'full_state', 'bbbbbbbbbbbb': 'weights_only'}
    assert runs.save_point(whole) == POINT


def test_a_copy_without_its_save_points_cannot_continue(tmp_path):
    """The summary of the run it was copied from says full_state; the copy's folder holds no checkpoints/ at all."""
    copy = fabricate(tmp_path, 'scratch__seed0__cccccccccccc', save=False)
    (copy / 'run_summary.json').write_text(json.dumps(dict(output=dict(resumability='full_state', latest_checkpoint=POINT))))
    assert rows(tmp_path) == {'cccccccccccc': 'none'} and runs.save_point(copy) is None


def test_a_deleted_save_point_is_none_although_the_pointer_remains(tmp_path):
    run = fabricate(tmp_path, 'scratch__seed0__dddddddddddd')
    shutil.rmtree(run / 'checkpoints' / POINT)                       # latest.json still names it
    assert rows(tmp_path) == {'dddddddddddd': 'none'} and runs.save_point(run) is None
    (run / 'checkpoints' / 'latest.json').write_text('{not json')    # a damaged pointer is no save point either
    assert runs.save_point(run) is None


def test_no_summary_and_none_stay_as_they_are(tmp_path):
    fabricate(tmp_path, 'scratch__seed0__eeeeeeeeeeee', summary=False, state='running')   # a working run: no summary yet
    fabricate(tmp_path, 'scratch__seed0__ffffffffffff', resumability='none', save=False)
    assert rows(tmp_path) == {'eeeeeeeeeeee': None, 'ffffffffffff': 'none'}


def test_the_status_answer_names_the_save_point_continue_would_use(tmp_path):
    whole = fabricate(tmp_path, 'scratch__seed0__aaaaaaaaaaaa', state='stopped')
    copy = fabricate(tmp_path, 'scratch__seed0__cccccccccccc', save=False, state='stopped')
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))
    status = lambda run: client.get('/api/runs/status', params=dict(run_dir=str(run))).json()
    assert status(whole)['save_point'] == POINT and status(copy)['save_point'] is None
    listed = {row['run_id']: row['resumability'] for row in client.get('/api/runs', params=dict(output_root=str(tmp_path))).json()['runs']}
    assert listed == {'aaaaaaaaaaaa': 'full_state', 'cccccccccccc': 'none'}


def test_a_save_point_of_older_optimizer_code_reads_model_only(tmp_path):
    """Record 7.221: Continue (an exact resume) needs the optimizer source its save point was written by. A full save
    point of another source digest reads "model only" in the run list and 'older' in the status; fine-tune and frozen
    still load it (checkpoints.check_compatibility only warns about the digest there)."""
    from analog_optimizer.training.sac import source_digest
    current = fabricate(tmp_path, 'scratch__seed0__aaaaaaaaaaaa', state='stopped')
    older = fabricate(tmp_path, 'scratch__seed0__bbbbbbbbbbbb', state='stopped')
    copy = fabricate(tmp_path, 'scratch__seed0__cccccccccccc', save=False, state='stopped')
    for run, digest in ((current, source_digest()), (older, '0' * 64)):
        metadata = run / 'checkpoints' / POINT / 'metadata.json'
        metadata.write_text(json.dumps(dict(json.loads(metadata.read_text()), contract=dict(code_sha256=digest))))
    assert rows(tmp_path) == {'aaaaaaaaaaaa': 'full_state', 'bbbbbbbbbbbb': 'weights_only', 'cccccccccccc': 'none'}
    assert runs.save_point_code(current) == 'current' and runs.save_point_code(older) == 'older'
    assert runs.save_point_code(copy) is None
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))
    status = lambda run: client.get('/api/runs/status', params=dict(run_dir=str(run))).json()
    assert [status(run)['save_point_code'] for run in (current, older, copy)] == ['current', 'older', None]
