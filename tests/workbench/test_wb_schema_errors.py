"""A configuration the schema rejects is explained field by field, in plain words, at the row it concerns; and every
registered task starts from rows the schema accepts (user report 2026-09-21, status record 7.56: choosing the MOCK task
synthetic:vco gave three Parameters rows the ID pattern rejects - stage_a_width__stage_a/pull_up - and the page showed
pydantic's list as JSON; that task is gone since 7.59, the rule stays). Local files and the MOCK task only."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gator_workbench import compile as comp, schema, tasks, validation
from gator_workbench.api import create_app
from helpers import MOCK_TASK
from test_wb_api import probe

SYNTHETIC = [f'synthetic:{name}' for name in sorted(tasks.SYNTHETIC_FIXTURES)]
OLD_IDS = ['input_pair_width__XU1/M2', 'mirror_pair_width__XU1/M4']


def as_config(raw):
    return schema.WorkbenchConfig.model_validate(dict(raw, run=dict(raw.get('run') or {}, max_evaluations=20)))


def old_rows():
    """The MOCK task's starter as the rule was before 7.56: every follower's ID kept the / of its device."""
    raw = tasks.starter_config(MOCK_TASK)
    for row in raw['parameters']:
        if row.get('binding_group'):
            row['variable_id'] = f"{row['binding_group']}__{row['instance_path']}"
    return raw


@pytest.mark.parametrize('task', SYNTHETIC)
def test_every_mock_task_starts_from_rows_the_schema_and_the_validation_accept(task):
    config = as_config(tasks.starter_config(task))
    runtime = tasks.load_task(config.circuit)
    report = validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
    assert [(i.level, i.code, i.path) for i in report.issues if i.level in ('error', 'blocker')] == []
    comp.compile_task(config, runtime.base_graph)


@pytest.mark.parametrize('task', [f'real:{name}' for name in sorted(tasks.offered_real_profiles())])
def test_every_verified_task_starts_from_rows_the_schema_accepts(task):
    as_config(tasks.starter_config(task))          # their full validation: test_wb_real_starter


def test_a_follower_id_takes_no_character_an_id_cannot_hold():
    raw = tasks.starter_config(MOCK_TASK)
    assert [row['variable_id'] for row in raw['parameters']] == [
        'input_pair_width', 'input_pair_width__XU1_M2', 'mirror_pair_width', 'mirror_pair_width__XU1_M4', 'tail_width']
    follower = raw['parameters'][1]
    assert (follower['instance_path'], follower['binding_group']) == ('XU1/M2', 'input_pair_width')        # the device stays exact
    assert tasks._member_variable_id('stage_a_width', 'stage_a/pull_up') == 'stage_a_width__stage_a_pull_up'  # the 7.56 report
    assert tasks._member_variable_id('g', 'I0/M<0> x') == 'g__I0_M_0__x'


def test_the_rejected_ids_are_named_row_by_row_in_plain_words():
    with pytest.raises(ValidationError) as caught:
        schema.WorkbenchConfig.model_validate(dict(old_rows(), run=dict(max_evaluations=20)))
    errors = schema.describe_errors(caught.value)
    assert [(e['path'], e['code']) for e in errors] == [(f'parameters[{n}].variable_id', 'invalid_id') for n in (1, 3)]
    first = errors[0]
    assert first['message'].startswith('"input_pair_width__XU1/M2" cannot be an ID: it contains "/".')
    assert 'for example input_pair_width__XU1_M2' in first['message'] and 'binding_group' in first['message']
    assert 'pattern' not in first['message'] and 'String should match pattern' in first['technical']


def test_other_rejections_read_plainly_too():
    raw = tasks.starter_config(MOCK_TASK)
    raw['parameters'][0]['lower'] = 'abc'
    raw['parameters'][0]['bogus'] = 1
    raw['parameters'][2]['variable_id'] = '1st M<0>'
    raw['targets'][0].update(constraint='between', normalization_scale=0)
    del raw['targets'][0]['unit']
    raw['measurements'].append(dict(raw['measurements'][0], measurement_id='m/x'))
    raw['run']['max_evaluations'] = 1.5
    with pytest.raises(ValidationError) as caught:
        schema.WorkbenchConfig.model_validate(raw)
    said = {e['path']: (e['code'], e['message']) for e in schema.describe_errors(caught.value)}
    assert said['parameters[0].lower'] == ('schema', 'lower needs a number (it is "abc").')
    assert said['parameters[0].bogus'] == ('schema', 'bogus is not a field of this part of the configuration: remove it.')
    assert said['parameters[2].variable_id'][0] == 'invalid_id'
    assert 'it contains a space, "<", ">" and it starts with "1"' in said['parameters[2].variable_id'][1]
    assert 'for example _1st_M_0_' in said['parameters[2].variable_id'][1]
    assert said['targets[0].unit'] == ('schema', 'unit is missing: this field needs a value.')
    assert said['targets[0].constraint'][1] == "constraint must be one of '>=', '<=', 'interval' or 'target' (it is \"between\")."
    assert said['targets[0].normalization_scale'][1] == 'normalization_scale must be greater than 0 (it is 0).'
    assert 'Specs equations that use it need the new ID too' in said['measurements[1].measurement_id'][1]
    assert said['run.max_evaluations'][1] == 'max_evaluations needs a whole number (it is 1.5).'


def test_the_validation_endpoint_answers_a_rejection_field_by_field(tmp_path):
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    response = client.post('/api/config/validate', json=dict(config=dict(old_rows(), run=dict(max_evaluations=20))))
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['message'] == 'The configuration does not match the schema'
    assert [(e['path'], e['code']) for e in detail['errors']] == [(f'parameters[{n}].variable_id', 'invalid_id') for n in (1, 3)]
    assert all(set(e) == {'path', 'code', 'message', 'technical'} for e in detail['errors'])
    assert OLD_IDS[1] in detail['errors'][1]['message'] and 'mirror_pair_width__XU1_M4' in detail['errors'][1]['message']
    fixed = client.post('/api/config/validate', json=dict(config=dict(tasks.starter_config(MOCK_TASK), run=dict(max_evaluations=20))))
    assert fixed.status_code == 200 and fixed.json()['blocks_run'] is False, json.dumps(fixed.json()['issues'])
