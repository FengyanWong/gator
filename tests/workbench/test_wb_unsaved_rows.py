"""Rows not saved in the task, row by row (record 7.222, user: "In the parameter probe and spec windows, highlight the rows
that are unsaved"): validation names the editors' rows that differ from the saved task's file - compared as the check
before every run compares them - and the page's editors mark them (frontend/scripts/unsaved_rows_check.mjs). FAKE check
processes and the recorded ring-oscillator export only - no Virtuoso, no simulation."""
from fastapi.testclient import TestClient

from gator_workbench import schema, tasks
from gator_workbench.api import create_app
from gator_workbench.validation import validate
from helpers import MOCK_TASK, bridge_is_importable, roots_for  # noqa: F401 - an imported fixture belongs to this module
from test_wb_api import probe
from test_wb_consistency import saved_ring

SAME = dict(added=[], removed=[], changed={}, reordered=False)


def test_the_saved_rows_mark_nothing(tmp_path):
    cfg = saved_ring(tmp_path)
    assert validate(cfg).unsaved_rows == dict(revision=1, sections=dict(parameters=SAME, measurements=SAME, targets=SAME))


def test_each_changed_new_and_deleted_row_is_named_with_its_saved_values(tmp_path):
    cfg = saved_ring(tmp_path)
    edited = cfg.model_copy(deep=True)
    spec, row = edited.targets[0], edited.parameters[0]
    saved_lower, saved_upper = spec.lower, row.upper
    spec.lower, row.upper = 1.3e9, row.upper + 0.2
    edited.parameters.append(row.model_copy(update=dict(variable_id='w_new')))
    probes = [probe.measurement_id for probe in edited.measurements]
    edited.measurements = []
    unsaved = validate(edited).unsaved_rows['sections']
    assert unsaved['targets'] == dict(SAME, changed={spec.metric_id: dict(fields=dict(lower=saved_lower), unit='Hz')})
    assert unsaved['parameters'] == dict(SAME, added=['w_new'], changed={row.variable_id: dict(fields=dict(upper=saved_upper), unit=row.unit)})
    assert unsaved['measurements'] == dict(SAME, removed=probes)


def test_a_field_given_its_default_is_not_a_change_and_another_order_is_said(tmp_path):
    cfg = saved_ring(tmp_path)
    stated = cfg.model_copy(deep=True)
    for spec in stated.targets:
        spec.hard = True                                    # what a row that does not state it means (the cell shows it ticked)
    assert validate(stated).unsaved_rows['sections']['targets'] == SAME
    turned = cfg.model_copy(deep=True)
    turned.parameters = turned.parameters[::-1]
    assert len(turned.parameters) > 1 and validate(turned).unsaved_rows['sections']['parameters'] == dict(SAME, reordered=True)
    assert [i['code'] for i in validate(turned).as_dict()['issues'] if i['code'] == 'task_not_saved'] == ['task_not_saved']


def test_rows_are_marked_in_every_run_mode_and_only_for_a_saved_task(tmp_path):
    cfg = saved_ring(tmp_path)
    resumed = cfg.model_copy(deep=True)
    resumed.run.mode = 'resume'
    resumed.targets[0].lower = 1.3e9
    report = validate(resumed)
    assert list(report.unsaved_rows['sections']['targets']['changed']) == [resumed.targets[0].metric_id]
    assert not [i for i in report.as_dict()['issues'] if i['code'] == 'task_not_saved']        # a resume runs its own rows
    assert 'unsaved_rows' not in report.as_dict()                                            # for the page's editors only
    mock = schema.WorkbenchConfig.model_validate(dict(tasks.starter_config(MOCK_TASK), run=dict(max_evaluations=3)))
    assert validate(mock).unsaved_rows is None


def test_the_page_gets_them_with_its_validation(tmp_path):
    cfg = saved_ring(tmp_path)
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    edited = cfg.model_copy(deep=True)
    edited.targets[0].lower = 1.3e9
    answer = client.post('/api/config/validate', json=dict(config=edited.model_dump(mode='json'))).json()
    assert answer['unsaved_rows']['revision'] == 1
    assert answer['unsaved_rows']['sections']['targets']['changed'] == {edited.targets[0].metric_id: dict(fields=dict(lower=1.1e9), unit='Hz')}
    assert client.post('/api/config/validate', json=dict(config=cfg.model_dump(mode='json'))).json()['unsaved_rows']['sections']['targets'] == SAME
    mock = schema.WorkbenchConfig.model_validate(dict(tasks.starter_config(MOCK_TASK), run=dict(max_evaluations=3)))
    assert client.post('/api/config/validate', json=dict(config=mock.model_dump(mode='json'))).json()['unsaved_rows'] is None
