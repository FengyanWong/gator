"""Parameters, Probes and Specs lost fourteen columns on 2026-09-26 (record 7.92, user decision "delete them with the
migration"): name, target_kind, candidates (with the discrete value_type), relation and expression of a Parameters row;
function, window, at_frequency_hz, integration_band_hz, branch_direction, loop_definition, crossover, on_failure and
validity of a Probes row. No run ever read them, and for several the only other value was a run blocker. A configuration
written with them still loads (the schema's before-validators keep what they meant and refuse what the run refused, in
plain words), both hashes are unchanged for it (schema._hashed), and normalization_scale may now be left empty.
On 2026-09-29 (record 7.105, the same decision) the Probes' conditions and aggregation followed: a run refused anything
but [nominal] / nominal_only, and since reward v2 the test conditions are the run's and each spec's."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gator_workbench import compile as comp, consistency, schema
from helpers import make_config
from test_wb_schema_validation import check, issues

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'old_format_config.json').read_text())
RETIRED = {'parameters': schema.RETIRED_PARAMETER_FIELDS, 'measurements': schema.RETIRED_MEASUREMENT_FIELDS}
G7_TASK_HASH = '5f181ef30c4ba6b5a1663871f07d48c9ed976334b6b8babd9870a7157c8a978a'    # docs/decisions.md, record 7.88


def test_an_old_configuration_loads_without_the_retired_fields():
    raw = FIXTURE['raw']
    for section, retired in RETIRED.items():
        assert all(set(retired) <= set(row) for row in raw[section])          # the fixture states every retired field
    dumped = schema.WorkbenchConfig.model_validate(raw).model_dump(mode='json')
    for section, retired in RETIRED.items():
        assert all(not (set(retired) & set(row)) for row in dumped[section])
        assert not (set(retired) & {c['name'] for c in schema.editor_columns(section)})


def test_both_hashes_of_an_old_configuration_are_unchanged(tmp_path):
    """Pinned with the code of the day before: the same task, the same configuration version."""
    raw = FIXTURE['raw']
    config = schema.WorkbenchConfig.model_validate(raw)
    assert schema.task_definition_hash(config) == FIXTURE['pins']['task'] == G7_TASK_HASH
    assert schema.config_hash(config) == FIXTURE['pins']['config'] == schema.config_hash(raw)   # the raw dict, keys and all
    assert schema.task_definition_hash(make_config(tmp_path)) == G7_TASK_HASH                  # the MOCK starter of today


@pytest.mark.parametrize('row, refusal', [
    (dict(target_kind='design_variable'), 'design_variable'),
    (dict(relation='expression', expression='leader**2'), 'not a constant times the leader'),
    (dict(value_type='discrete', candidates=[1e-6, 2e-6, 5e-6]), 'not a uniform grid'),
])
def test_what_never_ran_is_refused_in_plain_words(tmp_path, row, refusal):
    with pytest.raises(ValidationError) as caught:
        make_config(tmp_path, mutate=lambda raw: raw['parameters'][1].update(row))
    [error] = schema.describe_errors(caught.value)
    assert error['path'] == 'parameters[1]' and error['code'] == 'schema'
    assert 'no longer offered' in error['message'] and refusal in error['message']
    assert not error['message'].startswith('Value error')


def test_what_still_means_something_is_kept(tmp_path):
    def mutate(raw):
        raw['parameters'][1].update(relation='expression', expression='2*leader', name='the width',
                                    target_kind='instance_parameter')
    follower = make_config(tmp_path, mutate=mutate).parameters[1]
    assert follower.ratio == pytest.approx(2) and not hasattr(follower, 'name')         # the ratio it always ran as
    config = make_config(tmp_path, mutate=lambda raw: raw['parameters'][0].update(
        value_type='discrete', candidates=[1e-6, 2e-6, 3e-6, 4e-6], lower=None, upper=None, step=None, scale='linear'))
    grid = config.parameters[0]
    assert (grid.lower, grid.upper, grid.step) == pytest.approx((1e-6, 4e-6, 1e-6)) and grid.value_type == 'continuous'
    assert schema.linear_ratio('leader/4') == pytest.approx(0.25)
    assert all(schema.linear_ratio(text) is None for text in ('leader + 1e-6', 'leader**2', '-leader',
                                                              '__import__("os").system("x")'))     # never evaluated as code
    report, runtime = check(config)
    assert not report.blocks_run
    group = comp.compile_task(config, runtime.base_graph).graph.parameter_groups[0]
    assert (group.lower, group.upper, group.step) == pytest.approx((1e-6, 4e-6, 1e-6))


def test_probe_fields_that_never_ran_are_dropped(tmp_path):
    probe = dict(function='frequency', window=dict(start=1e-9, stop=2e-9, unit='s'), at_frequency_hz=1e6,
                 integration_band_hz=[10, 1e6], branch_direction='into_source_positive', loop_definition='stb',
                 crossover='first_unity_gain_downward', on_failure='feasible', validity=[dict(kind='min', value=None)])
    config = make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(probe))
    assert not (set(probe) & set(config.measurements[0].model_dump(mode='json')))
    report, _ = check(config)
    assert not report.blocks_run and 'generic_extraction_not_wired' not in issues(report, 'blocker')


def test_probe_conditions_and_aggregation_are_dropped_whatever_they_say(tmp_path):
    """Another value than [nominal] / nominal_only blocked every run (`nominal_only_backend`), so it never ran either."""
    probe = dict(conditions=['nominal', 'ss_125c'], aggregation='worst_case')
    config = make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(probe))
    assert not (set(probe) & set(config.measurements[0].model_dump(mode='json')))
    report, _ = check(config)
    assert not report.blocks_run and 'nominal_only_backend' not in issues(report, 'blocker')
    same = make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(conditions=['nominal'],
                                                                                   aggregation='nominal_only'))
    assert schema.task_definition_hash(same) == G7_TASK_HASH                  # stated at their defaults: the same task


def test_editor_columns_say_what_is_shown_on_request_and_what_is_hidden():
    """Review of 2026-10-03: the Parameters' value_type, step, scale and ratio step back behind "More columns"; initial_value
    (never filled in a saved task) and result_source (the task's one way of measuring) are not shown - the rows keep them.
    The Specs' target and tolerance and the Probes' expression were retired."""
    by = {section: {c['name']: c for c in schema.editor_columns(section)} for section in schema.SECTIONS}
    assert [n for n, c in by['targets'].items() if c['advanced']] == ['missing_is_failure', 'margin_sides', 'soft_weight', 'active', 'basis']
    assert [n for n, c in by['parameters'].items() if c['advanced']] == ['value_type', 'step', 'scale', 'ratio']
    assert [n for s in by for n, c in by[s].items() if c['hidden']] == ['initial_value', 'result_source']
    assert not any(c['advanced'] for c in by['measurements'].values())
    assert list(by['parameters']) == ['variable_id', 'instance_path', 'parameter_name', 'initial_value', 'unit', 'optimized',
                                      'value_type', 'lower', 'upper', 'step', 'scale', 'binding_group', 'ratio', 'notes']
    assert list(by['measurements']) == ['measurement_id', 'analysis', 'result_source', 'source_name', 'signal', 'unit', 'notes']
    assert 'target' not in by['targets'] and 'tolerance' not in by['targets']


def test_normalization_scale_defaults_to_the_size_of_the_threshold(tmp_path):
    config = make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(normalization_scale=None))
    target = config.targets[0]
    assert target.normalization_scale is None
    report, runtime = check(config)
    assert not report.blocks_run
    assert comp.compile_task(config, runtime.base_graph).specs[0].scale == pytest.approx(0.95)    # the >= 0.95 of the starter
    assert comp.normalization_scale(target) == pytest.approx(0.95)
    assert comp.normalization_scale(target.model_copy(update=dict(lower=0.0))) == 1.0
    assert comp.normalization_scale(target.model_copy(update=dict(normalization_scale=2.5))) == 2.5
    with pytest.raises(ValidationError):
        make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(normalization_scale=0))


def test_the_consistency_check_reads_a_task_saved_with_the_retired_keys_as_the_same_rows():
    raw = FIXTURE['raw']
    config = schema.WorkbenchConfig.model_validate(raw)
    saved = dict(parameters=raw['parameters'], probes=raw['measurements'], specs=raw['targets'])
    assert consistency.row_differences(config, saved) == {}
