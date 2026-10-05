"""Rows older than the saved task (record 7.203): Save task refuses to undo what was saved since until the user answers
"Save anyway", and the check points to Reload saved values. On 2026-10-05 a page holding mscr_ldo2_rgcn's rows from
before a save stored them over it twice and took out the Scale 6 that save had added (record 7.194). FAKE bridge
processes and the recorded ring-oscillator export only - no Virtuoso, no simulation."""
import pytest
from fastapi.testclient import TestClient

from gator_workbench import consistency, profiles, schema, task_saving, tasks
from gator_workbench.api import create_app
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from test_wb_api import probe
from test_wb_task_save import FREQUENCY_PROBE, FREQUENCY_SPEC, config, copy_reader, ready, save

LOOSE = dict(FREQUENCY_SPEC, normalization_scale=2e8)          # what revision 2 saves: another Scale


@pytest.fixture(autouse=True)
def _no_save_yet(monkeypatch):
    monkeypatch.setattr(task_saving, '_running', None)
    monkeypatch.setattr(task_saving, '_last', None)
    monkeypatch.setattr(task_saving, '_took', {})


def two_revisions(tmp_path):
    """real:ring_osc saved twice: revision 1 with Scale 1e9, revision 2 with Scale 2e8."""
    ready(tmp_path)
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9))
    assert save(tmp_path, cfg=config(specs=[LOOSE]), task='ring_osc')['revision'] == 2


def saved_rows(revision=1):
    """The Parameters rows as revision `revision` saved them (Save task puts them on the grid): what a page holds."""
    return consistency.revision_file('ring_osc', revision)['parameters']


def page(specs=(FREQUENCY_SPEC,), probes=(FREQUENCY_PROBE,)):
    """The page's configuration of the saved task: its saved Parameters rows, these Probes and Specs."""
    return schema.WorkbenchConfig.model_validate(dict(
        circuit=dict(source='registered_task', task_id='real:ring_osc'), parameters=saved_rows(), measurements=list(probes),
        targets=list(specs), run=dict(max_evaluations=5)))


def cfg(specs=(FREQUENCY_SPEC,)):
    """What Save task is sent: the saved Parameters rows and these Specs."""
    return config(specs=list(specs), rows=saved_rows())


def test_rows_of_an_earlier_revision_would_undo_what_was_saved_since(tmp_path):
    two_revisions(tmp_path)
    saved = profiles.task_file('ring_osc')
    undone = consistency.undone_by_saving(page(), 'ring_osc', saved)       # exactly revision 1's rows: told without a base
    assert (undone['base'], undone['current']) == (1, 2)
    assert undone['items'] == [dict(section='targets', row='osc_frequency_hz', change='field', field='normalization_scale',
                                    saved=2e8, here=1e9, unit='Hz')]
    assert consistency.describe_undone('ring_osc', undone) == (
        "real:ring_osc was saved again after these rows were loaded: it is revision 2 now, the rows here are revision 1's. "
        'Saving them would undo what was saved since: Specs osc_frequency_hz: normalization_scale 200 MHz saved, 1 GHz here.')
    assert consistency.undone_by_saving(page(specs=[LOOSE]), 'ring_osc', saved) is None          # the saved rows
    # An edit of the user's own on top of revision 1: without the revision the rows came from nothing can be told;
    # with it, only what was saved since is named - not the user's own change.
    mine = dict(FREQUENCY_SPEC, lower=1.2e9)
    assert consistency.undone_by_saving(page(specs=[mine]), 'ring_osc', saved) is None
    named = consistency.undone_by_saving(page(specs=[mine]), 'ring_osc', saved, base=1)
    assert [(i['field'], i['saved'], i['here']) for i in named['items']] == [('normalization_scale', 2e8, 1e9)]
    assert consistency.undone_by_saving(page(specs=[dict(LOOSE, lower=1.2e9)]), 'ring_osc', saved, base=1) is None   # holds it
    assert consistency.undone_by_saving(page(specs=[mine]), 'ring_osc', saved, base=2) is None    # from the saved revision


def test_rows_added_or_removed_since_are_named(tmp_path):
    two_revisions(tmp_path)
    second = dict(FREQUENCY_SPEC, metric_id='osc_frequency_low_hz', constraint='<=', lower=None, upper=1.5e9)
    assert save(tmp_path, cfg=cfg([LOOSE, second]), task='ring_osc')['revision'] == 3
    saved = profiles.task_file('ring_osc')
    undone = consistency.undone_by_saving(page(specs=[LOOSE]), 'ring_osc', saved)          # revision 2's rows: lack the new row
    assert undone['base'] == 2 and undone['items'] == [dict(section='targets', row='osc_frequency_low_hz', change='removed')]
    assert consistency.undone_lines(undone) == ['Specs osc_frequency_low_hz is saved but not here']
    assert save(tmp_path, cfg=cfg([LOOSE]), task='ring_osc', replace_newer=True)['revision'] == 4   # taken out again
    saved = profiles.task_file('ring_osc')
    back = consistency.undone_by_saving(page(specs=[LOOSE, second]), 'ring_osc', saved)    # revision 3's rows: still have it
    assert back['base'] == 3 and back['items'] == [dict(section='targets', row='osc_frequency_low_hz', change='back')]
    assert consistency.undone_lines(back) == ['Specs osc_frequency_low_hz was taken out of the saved task but is still here']


def test_save_task_refuses_older_rows_before_any_step_until_the_user_says_save_anyway(tmp_path):
    two_revisions(tmp_path)
    folder = profiles.profile_dir('ring_osc')
    files = lambda: {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    before, heard = files(), []
    with pytest.raises(profiles.NewerSaved) as refusal:                    # revision 1's rows: told from the rows themselves
        save(tmp_path, cfg=cfg(), task='ring_osc', progress=lambda step, steps: heard.append(step))
    assert refusal.value.detail_extra['undone']['items'][0]['field'] == 'normalization_scale'
    assert 'revision 2 now' in str(refusal.value) and str(refusal.value).endswith('Press Reload saved values to take the saved rows, or save anyway.')
    assert heard == [] and files() == before                                # refused before Virtuoso or any file
    # Rows that hold what was saved since, with an edit of the user's own: saved as usual.
    assert save(tmp_path, cfg=cfg([dict(LOOSE, lower=1.2e9)]), task='ring_osc', base_revision=1)['revision'] == 3
    # "Save anyway": the older rows replace what was saved since.
    made = save(tmp_path, cfg=cfg(), task='ring_osc', replace_newer=True)
    assert made['revision'] == 4 and profiles.task_file('ring_osc')['specs'][0]['normalization_scale'] == 1e9


def test_the_page_is_asked_and_told_through_the_routes(tmp_path, monkeypatch):
    two_revisions(tmp_path)
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    real = profiles.save_task
    monkeypatch.setattr(profiles, 'save_task', lambda *a, **k: real(*a, **dict(k, commands=dict(read=copy_reader(tmp_path)))))
    old = page().model_dump(mode='json')
    body = dict(profile_id='lab', name='ring_osc', task='ring_osc', config=old, base_revision=1)
    refused = client.post('/api/virtuoso/task/save', json=body)
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'saved_task_newer'
    detail = refused.json()['detail']
    assert (detail['undone']['base'], detail['undone']['current']) == (1, 2) and 'Saving them would undo' in detail['message']
    assert client.get('/api/tasks/saving').json()['last']['problem']['code'] == 'saved_task_newer'
    # The check while editing says it too and points to Reload saved values - told from the rows, or from the page's note.
    for extra in (dict(), dict(rows_from=1)):
        [issue] = [i for i in client.post('/api/config/validate', json=dict(config=old, **extra)).json()['issues'] if i['code'] == 'task_not_saved']
        assert ('These rows are older than the saved task: it was saved again (revision 2) after they were loaded (revision 1). '
                'Press Reload saved values') in issue['message']
    edited = page(specs=[dict(FREQUENCY_SPEC, lower=1.2e9)]).model_dump(mode='json')    # an own edit: the page's note decides
    [plain] = [i for i in client.post('/api/config/validate', json=dict(config=edited)).json()['issues'] if i['code'] == 'task_not_saved']
    assert plain['message'].endswith(consistency.FIX_ROWS)
    [named] = [i for i in client.post('/api/config/validate', json=dict(config=edited, rows_from=1)).json()['issues']
               if i['code'] == 'task_not_saved']
    assert 'older than the saved task' in named['message']
    assert client.get('/api/tasks/starter', params=dict(task_key='real:ring_osc')).json()['revision'] == 2   # the page notes it
    assert 'revision' not in tasks.starter_config('real:ring_osc')         # the configuration itself stays a configuration
    saved = client.post('/api/virtuoso/task/save', json=dict(body, replace_newer=True))
    assert saved.status_code == 200 and saved.json()['revision'] == 3
