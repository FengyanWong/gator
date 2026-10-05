"""Each spec is an equation over the probes (gator_workbench.spec_equations): one value per spec, the same for the reward,
the network's goal input, the independent pass/fail check and the tables. MOCK backend only; no Virtuoso, no Spectre."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import copy
import json
import math
from pathlib import Path

import pytest

from gator_workbench import compile as comp, schema, spec_equations as se, tasks
from gator_workbench.storage import DatasetReader, read_json
from gator_workbench.storage.atomic import read_jsonl
from gator_workbench.validation import validate
from helpers import execute, make_config

OTA_RESULTS = {'score', 'unity_gain_hz', 'bandwidth_3db_hz', 'supply_power_w'}


def codes(report, *levels):
    return [i.code for i in report.issues if i.level in levels]


def probe(measurement_id, source_name, unit='fixture'):
    return dict(measurement_id=measurement_id, analysis='other', result_source='backend_profile', source_name=source_name, unit=unit)


def spec(metric_id, equation, **fields):
    return dict(dict(metric_id=metric_id, equation=equation, unit='fixture', constraint='>=', lower=0.5,
                     normalization_scale=1.0, basis='test'), **fields)


def mock(tmp_path, *, specs=(), probes=(), **kwargs):
    def add(raw):
        raw['measurements'] += list(probes)
        raw['targets'] += list(specs)
    return make_config(tmp_path, mutate=add, **kwargs)


def check(config, provided=None):
    runtime = tasks.load_task(config.circuit)
    return validate(config, graph=runtime.base_graph,
                    provided_metrics=set(runtime.provided_metrics) if provided is None else provided)


# ------------------------------------------------------------------------------- the equation itself
def test_an_equation_is_read_off_its_form_and_never_executed():
    assert se.parse('m_supply_power_w / m_osc_frequency_hz') == (['m_supply_power_w', 'm_osc_frequency_hz'], None)
    assert se.parse('2u * (m_a - 1k) ** 2') == (['m_a'], None)                         # SI suffixes, as in the netlists
    # judged by form: a trial evaluation with every symbol at 1.0 would divide by zero here
    assert se.parse('(m_f1 - m_f0) / (m_v1 - m_v0)')[0] == ['m_f1', 'm_f0', 'm_v1', 'm_v0']
    for text in ('abs(m_a)', 'm_a.real', '__import__("os").system("true")', 'm_a if 1 else 2', 'm_a > 1', '"m_a"', '', '  ', 'm_a +',
                 '1e999 * m_a', 'x' * 600):
        names, why = se.parse(text)
        assert names is None and why, text


def test_a_failed_operation_or_a_missing_probe_is_invalid_never_a_number():
    values = {'m_a': 2.0, 'm_b': 0.0}
    assert se.evaluate('m_a / 4', values.get) == 0.5
    assert se.evaluate('m_a / m_b', values.get) is None                                # division by zero
    assert se.evaluate('m_a * m_c', values.get) is None                                # m_c missing
    assert se.evaluate('m_a ** 1000', values.get) is None                              # beyond the evaluator's exponent limit


# ------------------------------------------------------------------------------- old configurations
# Written by the code of commit c3b9691, the last before Specs had equations (see its `made_with`), with the two hashes that
# code computed. It replaces an "old" configuration rebuilt from a NEW dump, which every later schema field broke again.
PRE_EQUATIONS = json.loads((Path(__file__).parent / 'fixtures' / 'pre_equations_config.json').read_text())


def test_a_configuration_from_before_equations_loads_and_keeps_both_hashes():
    raw, pins = PRE_EQUATIONS['raw'], PRE_EQUATIONS['pins']
    assert 'measurement_id' in raw['targets'][0] and 'equation' not in raw['targets'][0]      # the old form, as saved then
    config = schema.WorkbenchConfig.model_validate(raw)
    assert config.targets[0].equation == 'm_score'                                            # its one probe is the equation
    today = copy.deepcopy(raw)
    for row in today['targets']:
        row['equation'] = row.pop('measurement_id')
    assert schema.WorkbenchConfig.model_validate(today) == config                             # both keys mean the same
    # the hashes an old run, checkpoint, approval or proposal recorded are the hashes computed now
    assert schema.task_definition_hash(config) == pins['task']
    assert schema.config_hash(config) == pins['config'] == schema.config_hash(raw)            # the raw dict, keys and all
    # both keys: the equation wins; a formula is hashed as itself
    both = schema.PerformanceTarget.model_validate(dict(raw['targets'][0], equation='m_score * 2'))
    assert both.equation == 'm_score * 2'
    formula = config.model_copy(update=dict(targets=[both]))
    assert schema.task_definition_hash(formula) != schema.task_definition_hash(config)
    assert 'measurement_id' not in schema.PerformanceTarget.model_json_schema()['properties']
    assert [c['name'] for c in schema.editor_columns('targets')][:2] == ['metric_id', 'equation']


# ------------------------------------------------------------------------------- validation
def test_every_starter_is_still_valid_and_its_specs_are_their_own_results(tmp_path):
    # the helper's own run settings are the schema defaults with a budget of 20, which static validation names since
    # record 7.183 (values and a budget with which soft actor-critic does not learn): they are no fault of the starter
    config = make_config(tmp_path)
    report = check(config)
    assert not report.blocks_run and set(codes(report, 'warning')) == {'sac_values_random_search', 'budget_below_sac_learning'}
    compiled = comp.compile_task(config, tasks.load_task(config.circuit).base_graph)
    assert compiled.plan.injected == () and compiled.spec_schema.version == 'spec-input-v1'      # nothing added: same network input
    assert compiled.targets[0]['equation'] == compiled.targets[0]['probe'] == 'm_score'


@pytest.mark.parametrize('equation, code', [
    ('m_nope * 2', 'equation_unknown_probe'),
    ('abs(m_score)', 'equation_rejected'),
    ('3 * 4', 'equation_without_probe'),
])
def test_equation_errors(tmp_path, equation, code):
    assert code in codes(check(mock(tmp_path, specs=[spec('extra', equation)])), 'error')


def test_a_formula_warns_that_its_unit_is_unchecked_and_one_probe_is_checked(tmp_path):
    report = check(mock(tmp_path, specs=[spec('score_sq', 'm_score ** 2')]))
    assert 'equation_unit_unchecked' in codes(report, 'warning') and not report.blocks_run
    report = check(mock(tmp_path, specs=[spec('score_again', 'm_score', unit='dB')]))
    assert 'target_unit_mismatch' in codes(report, 'error')


def test_a_spec_may_carry_a_result_name_only_when_it_is_that_result(tmp_path):
    """The gap found on 2026-09-21: `unity_gain_hz` pointed at a probe reading `bandwidth_3db_hz` passed validation, while
    the reward read `unity_gain_hz` and the pass/fail check read the bandwidth."""
    probes = [probe('m_ugb', 'unity_gain_hz', 'Hz'), probe('m_bw', 'bandwidth_3db_hz', 'Hz')]
    wrong = mock(tmp_path, probes=probes, specs=[spec('unity_gain_hz', 'm_bw', unit='Hz', lower=1e6, normalization_scale=1e6)])
    assert 'spec_name_is_a_result' in codes(check(wrong, OTA_RESULTS), 'error')
    right = mock(tmp_path, probes=probes, specs=[spec('unity_gain_hz', 'm_ugb', unit='Hz', lower=1e6, normalization_scale=1e6),
                                                 spec('bandwidth', 'm_bw', unit='Hz', lower=1e5, normalization_scale=1e5)])
    report = check(right, OTA_RESULTS)
    assert 'spec_name_is_a_result' not in codes(report, 'error') and 'spec_name_is_a_probe' not in codes(report, 'error')
    named_like_a_probe = mock(tmp_path, specs=[spec('m_score', 'm_score * 2')])
    assert 'spec_name_is_a_probe' in codes(check(named_like_a_probe), 'error')


def test_a_new_spec_name_extends_the_registry_unless_one_is_configured(tmp_path):
    config = mock(tmp_path, specs=[spec('score_sq', 'm_score ** 2')])
    assert 'spec_adds_registry_entry' in codes(check(config), 'info')
    configured = mock(tmp_path, specs=[spec('score_sq', 'm_score ** 2')],
                      advanced=dict(spec_registry=[dict(metric_id='score', unit='fixture', reference=1.0)]))
    assert 'metric_not_in_registry' in codes(check(configured), 'blocker')


def test_a_probe_no_equation_uses_is_reported_and_one_used_inside_a_formula_is_not(tmp_path):
    extra = probe('m_twice', 'score')
    report = check(mock(tmp_path, probes=[extra]))
    assert 'unused_measurement' in codes(report, 'warning')
    report = check(mock(tmp_path, probes=[extra], specs=[spec('ratio', 'm_twice / m_score')]))
    assert 'unused_measurement' not in codes(report, 'warning')


def test_a_probe_id_with_a_dot_works_as_a_whole_equation(tmp_path):
    def dotted(raw):
        raw['measurements'][0]['measurement_id'] = 'm.score'
        raw['targets'][0]['equation'] = 'm.score'
    config = make_config(tmp_path, mutate=dotted)
    assert not check(config).blocks_run
    assert comp.compile_task(config, tasks.load_task(config.circuit).base_graph).plan.injected == ()


# ------------------------------------------------------------------------------- the registry the network reads
def test_a_computed_spec_gets_a_registry_entry_sized_by_what_it_computes_not_by_its_limits(tmp_path):
    def with_power(raw, lower):
        raw['measurements'] += [probe('m_ugb', 'unity_gain_hz', 'Hz'), probe('m_power', 'supply_power_w', 'W')]
        raw['targets'].append(spec('hz_per_watt', 'm_ugb / m_power', unit='Hz', lower=lower, normalization_scale=1e12))
    base = schema.WorkbenchConfig.model_validate(tasks.starter_config('synthetic:gpdk045_ota5') | dict(run=dict(max_evaluations=5)))
    schemas = []
    for lower in (1e11, 3e12):
        raw = base.model_dump(mode='json')
        with_power(raw, lower)
        schemas.append(comp.build_spec_schema(schema.WorkbenchConfig.model_validate(raw)))
    first, second = schemas
    assert first == second                                               # a changed limit keeps saved models loadable
    assert first.version == comp.build_spec_schema(base).version + se.REGISTRY_SUFFIX   # the registry's name, suffixed
    assert first.metrics[:7] == comp.build_spec_schema(base).metrics     # the known entries keep their places
    name, unit, reference = first.metrics[-1]
    assert (name, unit) == ('hz_per_watt', 'Hz') and math.isclose(reference, 1e6 / 1e-6)   # default registry: 1 MHz / 1 uW


# ------------------------------------------------------------------------------- inside a lane
@dataclass(frozen=True)
class Result:                                         # the fields SpecPlan.extend reads, as in backends.backend.SimulationResult
    metrics: dict
    metric_units: dict
    metric_validity: dict
    status: str = 'ok'
    candidate_evaluated: bool = True


def plan_for(tmp_path, specs, probes=()):
    return comp.compile_task(mock(tmp_path, specs=specs, probes=probes),
                             tasks.load_task(make_config(tmp_path).circuit).base_graph).plan


def test_a_result_gets_the_computed_specs_and_nothing_it_measured_changes(tmp_path):
    plan = plan_for(tmp_path, [spec('score_sq', 'm_score ** 2'), spec('half', 'm_score / 2', hard=False)])
    assert plan.injected == ('score_sq', 'half')
    extended = plan.extend(Result({'score': 0.9}, {'score': 'fixture'}, {'score': True}))
    assert extended.metrics == {'score': 0.9, 'score_sq': pytest.approx(0.81), 'half': 0.45}
    assert extended.metric_units['score_sq'] == 'fixture' and extended.metric_validity['score_sq'] is True
    invalid = plan.extend(Result({'score': None}, {'score': 'fixture'}, {'score': False}))
    assert invalid.metrics['score_sq'] is None and invalid.metric_validity['score_sq'] is False
    failed = plan.extend(Result({'score': 0.9}, {'score': 'fixture'}, {'score': True}, status='timeout'))
    assert failed.metric_validity['half'] is False
    with pytest.raises(ValueError, match='rename'):
        plan.extend(Result({'score': 0.9, 'half': 1.0}, {}, {'score': True, 'half': True}))
    # a request insists on the results a computed hard spec reads, not on names the simulator never returns
    assert plan.request_names(('score', 'score_sq')) == ('score',)


def test_a_missing_probe_blanks_only_the_specs_that_read_it(tmp_path):
    """A completed simulation with one probe missing (measurement_error) keeps every computed spec whose probes were
    measured, so "Missing value = failed" fails only the spec that really lacks its value (record 7.112)."""
    from types import SimpleNamespace
    from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
    plan = plan_for(tmp_path, [spec('score_sq', 'm_score ** 2'), spec('other_x2', 'm_other * 2')],
                    probes=[probe('m_other', 'other')])
    result = Result({'score': 0.9, 'other': None}, {'score': 'fixture', 'other': 'fixture'},
                    {'score': True, 'other': False}, status='measurement_error')
    extended = plan.extend(result)
    assert extended.metrics['score_sq'] == pytest.approx(0.81) and extended.metric_validity['score_sq'] is True
    assert extended.metrics['other_x2'] is None and extended.metric_validity['other_x2'] is False
    flagged = [MetricSpec('score_sq', 'fixture', 'max', 1.0, upper=1.0, missing_is_failure=True),
               MetricSpec('other_x2', 'fixture', 'max', 1.0, upper=1.0, missing_is_failure=True)]
    row = SimpleNamespace(condition=None, status='measurement_error', candidate_evaluated=True, job_id='fixture',
                          metrics=extended.metrics, metric_units=extended.metric_units,
                          metric_validity=extended.metric_validity)
    evaluation = SpecificationEvaluator(flagged).evaluate_conditions((row,))
    assert evaluation.valid and evaluation.violations == {'score_sq': 0.0, 'other_x2': 1.0}
    # an infrastructure failure, or a simulation that never judged the candidate, still computes nothing
    assert plan.extend(replace(result, status='timeout')).metrics['score_sq'] is None
    assert plan.extend(replace(result, candidate_evaluated=False)).metrics['score_sq'] is None


def test_wrapping_a_backend_that_needs_nothing_leaves_it_alone(tmp_path):
    class Backend:
        def run_simulation(self, request):
            return request
    backend = Backend()
    assert plan_for(tmp_path, []).wrap(backend) is backend and 'run_simulation' not in vars(backend)


@dataclass(frozen=True)
class FakeInner:
    reference_metrics: dict | None
    measured: dict
    preparation: object = None

    def create_recorded(self, lane, recorder):
        assert self.reference_metrics is None             # the wrapper keeps the check itself, on the simulator's results
        measured = self.measured

        class Env:
            backend = type('B', (), {'run_simulation': lambda self, request: request})()

            def reset(self):
                return type('Obs', (), {'metrics': dict(measured)})(), {'evaluation_valid': True}
        return Env()

    @contextmanager
    def preparation_context(self, limits, report):
        yield replace(self, preparation='service')


def test_the_real_factory_keeps_its_baseline_check_on_the_simulator_results(tmp_path):
    plan = plan_for(tmp_path, [spec('score_sq', 'm_score ** 2')])
    same = se.EquationNativeFactory(FakeInner({'score': 0.5}, {'score': 0.5 * (1 + 5e-7), 'score_sq': 0.25}), plan)
    same(0).reset()                                        # the computed value is not compared: rounding would only be stricter
    moved = se.EquationNativeFactory(FakeInner({'score': 0.5}, {'score': 0.6, 'score_sq': 0.36}), plan)
    with pytest.raises(RuntimeError, match='baseline differs'):
        moved(0).reset()
    with same.preparation_context(None, {}) as prepared:
        assert isinstance(prepared, se.EquationNativeFactory) and prepared.inner.preparation == 'service'


def test_a_formula_spec_at_a_training_corner_is_marked_not_passed_off_as_a_result(tmp_path):
    """Training corners run only on the real OTA7, so this calls the engine's row builder directly with the conditions as the
    environment records them (`record['condition_results']`): the lane added the formula's value to each corner's result.
    That value is recorded as the corner's value of the formula, aggregation = equation (7.114); the simulator's own
    results stay unmarked."""
    from types import SimpleNamespace
    from gator_workbench.engine import RunEngine
    config = mock(tmp_path, specs=[spec('score_sq', 'm_score ** 2', lower=0.8)])
    compiled = comp.compile_task(config, tasks.load_task(config.circuit).base_graph)
    condition = lambda corner, score: dict(condition=dict(corner=dict(id=corner)), status='ok', reason_code='ok',
                                           metrics={'score': score, 'score_sq': score ** 2},
                                           metric_units={'score': 'fixture', 'score_sq': 'fixture'},
                                           metric_validity={'score': True, 'score_sq': True})
    rows = RunEngine._metric_rows(SimpleNamespace(run_id='r', config=config, compiled=compiled), 'e1', {'score': 0.95},
                                  {'score': True}, {'score': 'fixture'}, {'m_score': 0.95}, {'score': 0.95, 'score_sq': 0.9025},
                                  [], 'ok', [condition('nominal', 0.95), condition('ss', 0.85)])
    at_corner = {r['metric_name']: r for r in rows if r['condition'] == 'ss'}
    assert set(at_corner) == {'score', 'score_sq'}
    assert at_corner['score']['aggregation'] is None and at_corner['score_sq']['aggregation'] == 'equation'
    assert all(r['aggregation_level'] == 'condition' and r['measurement_id'] is None for r in at_corner.values())
    assert at_corner['score_sq']['raw_value'] == pytest.approx(0.7225) and at_corner['score_sq']['satisfied'] is False
    # nominal: the simulator's own result only, unmarked; the formula has its aggregate row, as before
    assert [(r['metric_name'], r['aggregation']) for r in rows if r['condition'] == 'nominal'] == [('score', None)]
    assert [r['aggregation'] for r in rows if r['metric_name'] == 'score_sq' and r['aggregation_level'] == 'aggregate'] == ['equation']


# ------------------------------------------------------------------------------- a whole run
def test_a_run_scores_and_judges_the_equation_and_records_it(tmp_path):
    # the toy score's own limit always holds, so pass/fail is decided by the formula alone (scores span ~0.74-0.97)
    config = mock(tmp_path, specs=[spec('score_sq', 'm_score ** 2', lower=0.8)], threshold=-1.0, run=dict(max_evaluations=14))
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    reader = DatasetReader(layout.data)
    metrics = reader.rows('metrics')
    raw = {(r['evaluation_id']): r for r in metrics if r['aggregation_level'] == 'condition' and r['metric_name'] == 'score'}
    computed = [r for r in metrics if r['metric_name'] == 'score_sq']
    assert len(computed) == 14 and all(r['aggregation_level'] == 'aggregate' for r in computed)
    probes = [r for r in metrics if r['aggregation_level'] == 'aggregate' and r['measurement_id'] is not None]
    assert probes and all(r['aggregation'] == 'nominal_only' for r in probes)    # as while Probes had the column (record 7.105)
    assert all(r['measurement_id'] is None and r['aggregation'] == 'equation' and r['threshold_lower'] == 0.8 for r in computed)
    for row in computed:
        assert math.isclose(row['raw_value'], raw[row['evaluation_id']]['raw_value'] ** 2, rel_tol=1e-12)
        assert row['satisfied'] == (row['raw_value'] >= 0.8)
    assert not [r for r in metrics if r['aggregation_level'] == 'condition' and r['metric_name'] == 'score_sq']
    # the spec whose equation is one probe keeps the row it always had
    score_rows = [r for r in metrics if r['metric_name'] == 'score' and r['aggregation_level'] == 'aggregate']
    assert len(score_rows) == 14 and {r['measurement_id'] for r in score_rows} == {'m_score'}
    # the environment's success (the reward's view) and the independent check never disagree
    events = read_jsonl(layout.logs / 'events.jsonl')
    assert events and not [e for e in events if e.get('event') == 'feasibility_disagreement']
    evaluations = reader.rows('evaluations')
    judged = [e for e in evaluations if e['valid'] and e['env_success'] is not None]
    assert judged and all(e['env_success'] == e['all_hard_constraints_satisfied'] for e in judged)
    squared = {r['evaluation_id']: r['raw_value'] for r in computed}
    assert all(e['all_hard_constraints_satisfied'] == (squared[e['evaluation_id']] >= 0.8) for e in evaluations if e['valid'])
    assert {e['all_hard_constraints_satisfied'] for e in judged} == {True, False}      # the formula really decided something
    manifest = read_json(layout.manifest)
    assert manifest['architecture']['spec_schema']['metrics'][-1] == ['score_sq', 'fixture', 1.0]
    assert [t['equation'] for t in manifest['definitions']['targets']] == ['m_score', 'm_score ** 2']
