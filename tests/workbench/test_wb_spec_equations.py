"""Each spec is an equation over the probes (gator_workbench.spec_equations): one value per spec, the same for the reward,
the network's goal input, the independent pass/fail check and the tables. MOCK backend only; no Virtuoso, no Spectre."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import copy
import hashlib
import math

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
def _old_hash(data, keys=None):
    data = {k: data[k] for k in keys} if keys else data
    return hashlib.sha256(schema.canonical_json(data).encode('utf8')).hexdigest()


def test_a_configuration_from_before_equations_loads_and_keeps_both_hashes(tmp_path):
    raw = tasks.starter_config('synthetic:gpdk045_ota5')
    new = schema.WorkbenchConfig.model_validate(dict(raw, run=dict(max_evaluations=5)))
    legacy_dump = new.model_dump(mode='json')
    for row in legacy_dump['targets']:                                                   # exactly what the old schema dumped
        row['measurement_id'] = row.pop('equation')
    del legacy_dump['run']['network']['vocabulary']              # added later (7.54); the old schema had no such field
    for row in legacy_dump['targets']:
        row.pop('missing_is_failure', None)                  # reward v2.1 fields did not exist in that old dump
        row.pop('margin_sides', None)
        row.pop('nominal_only', None)                            # added 2026-09-26 (reward v2); the old schema had no such field
    del legacy_dump['run']['reward'], legacy_dump['run']['conditions']          # reward v2 run fields: the old schema had none
    del legacy_dump['run']['network']['operating_points']
    del legacy_dump['run']['advanced']['alpha_learning_rate']
    for row in legacy_dump['parameters']:                        # the columns retired on 2026-09-26 (7.92), at their defaults
        row.update(copy.deepcopy(schema.RETIRED_PARAMETER_FIELDS))
    for row in legacy_dump['measurements']:
        row.update(copy.deepcopy(schema.RETIRED_MEASUREMENT_FIELDS))
    old = schema.WorkbenchConfig.model_validate(legacy_dump)
    assert old.targets[0].equation == 'm_score' and old == new
    # the hashes an old run, checkpoint, approval or proposal recorded are the hashes computed now
    assert schema.config_hash(new) == _old_hash(legacy_dump)
    assert schema.task_definition_hash(new) == _old_hash(legacy_dump, ('circuit', 'parameters', 'targets', 'measurements'))
    assert schema.config_hash(legacy_dump) == schema.config_hash(new)
    # both keys: the equation wins; a formula is hashed as itself
    both = schema.PerformanceTarget.model_validate(dict(legacy_dump['targets'][0], equation='m_score * 2'))
    assert both.equation == 'm_score * 2'
    formula = new.model_copy(update=dict(targets=[both]))
    assert schema.task_definition_hash(formula) != schema.task_definition_hash(new)
    assert 'measurement_id' not in schema.PerformanceTarget.model_json_schema()['properties']
    assert [c['name'] for c in schema.editor_columns('targets')][:2] == ['metric_id', 'equation']


# ------------------------------------------------------------------------------- validation
def test_every_starter_is_still_valid_and_its_specs_are_their_own_results(tmp_path):
    config = make_config(tmp_path)
    report = check(config)
    assert not report.blocks_run and not codes(report, 'warning')
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
