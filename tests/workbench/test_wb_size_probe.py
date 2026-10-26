"""A probe that measures the sizes (record 7.308): a Probes row with result_source "size_estimate" is not simulated - its
formula over the widths the task varies is worked out in the lane and added to the simulation result as a result of its
own. MOCK backend only; no Virtuoso, no Spectre."""
from dataclasses import dataclass
import math

import pytest

from gator_workbench import compile as comp, schema, spec_descriptors, spec_equations as se, task_save, tasks
from gator_workbench.profiles import ProfileError
from gator_workbench.storage import DatasetReader
from gator_workbench.storage.atomic import read_jsonl
from gator_workbench.validation import validate
from helpers import execute, make_config

CELL_WIDTH = '0.253u + 0.288u * larger(fingers("mn*", 400n), fingers("DUT/mp*", 630n))'      # plan-transfer-experiment 6.2.1


def codes(report, *levels):
    """Return validation issue codes at the requested severities."""
    return [i.code for i in report.issues if i.level in levels]


def size_probe(measurement_id, source_name, signal, unit='um'):
    """Build a size-estimate probe row for a selected parameter signal."""
    return dict(measurement_id=measurement_id, analysis='other', result_source='size_estimate', source_name=source_name,
                signal=signal, unit=unit)


def spec(metric_id, equation, **fields):
    """Build an upper-bound size spec with optional field overrides."""
    return dict(dict(metric_id=metric_id, equation=equation, unit='um', constraint='<=', upper=1e9, normalization_scale=1.0,
                     basis='test'), **fields)


def mock(tmp_path, *, specs=(), probes=(), **kwargs):
    """Add the supplied size probes and specs to a synthetic-run configuration."""
    def add(raw):
        """Append the requested probe and target rows to the fixture configuration."""
        raw['measurements'] += list(probes)
        raw['targets'] += list(specs)
    return make_config(tmp_path, mutate=add, **kwargs)


def check(config):
    """Validate size probes against the loaded task's graph and provided metrics."""
    runtime = tasks.load_task(config.circuit)
    return validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))


def flip_flop(outputs_n=260, outputs_p=390, gate=(145, 215), inverter=(145, 215)):
    """The 32 widths of the library's flip-flop, in m, keyed as a candidate's parameters are."""
    widths = {}
    for n in ('20', '21', '25', '26', '30', '35', '36', '37', '40', '45', '46', '50', '51', '55', '56', '57'):
        wn, wp = ((outputs_n, outputs_p) if n in ('55', '57') else gate if n in ('45', '46') else inverter if n == '56' else (145, 215))
        widths[(f'DUT/mn{n}', 'w')], widths[(f'DUT/mp{n}', 'w')] = wn * 1e-9, wp * 1e-9
        widths[(f'DUT/mn{n}', 'l')] = 45e-9                                # a length is not a width
    return widths


# ------------------------------------------------------------------------------- the formula itself
def test_a_size_formula_is_read_off_its_form_and_never_executed():
    assert se.parse_size_formula(CELL_WIDTH) == (('mn*', 'DUT/mp*'), None)
    assert se.parse_size_formula('width("m[np]2?") / count("*")')[0] == ('m[np]2?', '*')
    for text in ('fingers(mn, 400n)', 'm_power + width("mn*")', 'larger(1, 2)', 'abs(width("mn*"))', 'width("mn*").real',
                 '__import__("os").system("true")', 'width("mn*") > 1', 'fingers("mn*")', 'width("a", "b")', 'width("mn*" , )x', '',
                 '"mn*"', '1e999 * width("mn*")', 'width("' + 'x' * 400 + '")'):
        patterns, why = se.parse_size_formula(text)
        assert patterns is None and why, text


@pytest.mark.parametrize('formula', ["width('*')", "count('mn*')", "fingers('mn*', 400n)", "width('0')",
                                     'width("mn*" "mp*")', 'width(r"mn*")', 'width("""mn*""")', r'width("\x30")'])
def test_size_patterns_with_unsupported_quoting_are_validation_errors(tmp_path, formula):
    patterns, why = se.parse_size_formula(formula)
    assert patterns is None and why
    assert se.size_value(formula, flip_flop()) is None
    config = mock(tmp_path, probes=[size_probe('m_bad', 'bad_m', formula)], specs=[spec('bad_spec', 'm_bad')])
    assert 'size_formula_rejected' in codes(check(config), 'error')


def test_a_single_quoted_size_pattern_gets_a_validation_report_from_the_api(tmp_path):
    from fastapi.testclient import TestClient
    from helpers import workbench_app
    config = mock(tmp_path, probes=[size_probe('m_bad', 'bad_m', "width('*')")], specs=[spec('bad_spec', 'm_bad')])
    with TestClient(workbench_app(tmp_path), raise_server_exceptions=False) as client:
        answer = client.post('/api/config/validate', json=dict(config=config.model_dump(mode='json')))
    assert answer.status_code == 200
    assert answer.json()['blocks_run']
    assert any(i['code'] == 'size_formula_rejected' for i in answer.json()['issues'])


def test_the_flip_flops_cell_width_is_counted_in_gate_columns():
    x1 = se.instance_widths(flip_flop())
    assert len(x1) == 32                                                     # the lengths are not counted
    assert se.size_value('fingers("mn*", 400n)', x1) == 16 and se.size_value('fingers("mp*", 630n)', x1) == 16
    assert se.size_value(CELL_WIDTH, x1) == pytest.approx(0.253e-6 + 0.288e-6 * 16)
    x4 = se.instance_widths(flip_flop(1040, 1560, gate=(410, 620), inverter=(260, 390)))
    # NMOS: the two outputs fold into three fingers each and the slave gate's two series transistors into two each
    # (16 + 2 x 2 + 2 x 1 = 22); PMOS: only the outputs fold (16 + 2 x 2 = 20). The fuller row sets the width.
    assert se.size_value('fingers("mn*", 400n)', x4) == 22 and se.size_value('fingers("mp*", 630n)', x4) == 20
    assert se.size_value(CELL_WIDTH, x4) == pytest.approx(0.253e-6 + 0.288e-6 * 22)
    assert se.size_value('width("DUT/mn5[57]")', x1) == pytest.approx(520e-9)        # a pattern on the path or on its last part
    assert se.size_value('count("mn*") + count("DUT/mp*")', x1) == 32
    assert se.size_value('smaller(width("mn20"), width("mp20"))', x1) == pytest.approx(145e-9)
    # a width exactly on the limit is one finger; one grid step more is two
    assert se.size_value('fingers("mn20", 145n)', x1) == 1 and se.size_value('fingers("mn20", 140n)', x1) == 2


def test_a_value_that_cannot_be_worked_out_is_invalid_never_a_number():
    x1 = se.instance_widths(flip_flop())
    for text in ('fingers("zz*", 400n)', 'width("mn*") / 0', 'fingers("mn*", 0)', 'fingers("mn*", -1n)', 'count("mn*") ** 99999', 'nonsense('):
        assert se.size_value(text, x1) is None, text
    assert se.size_value(CELL_WIDTH, {}) is None                             # no varied width at all


# ------------------------------------------------------------------------------- in a configuration
def widths_of(config):
    """Return instance paths of optimized width rows."""
    return [p.instance_path for p in config.parameters if p.parameter_name == 'w' and p.optimized]


def test_a_size_probe_is_checked_like_the_rest_of_the_rows(tmp_path):
    base = make_config(tmp_path)
    last = widths_of(base)[0].rsplit('/', 1)[-1]
    good = mock(tmp_path, probes=[size_probe('m_wsum', 'width_sum_m', 'width("*")')], specs=[spec('width_sum_m', 'm_wsum')])
    assert not codes(check(good), 'error', 'blocker')
    by_name = mock(tmp_path, probes=[size_probe('m_one', 'one_width_m', f'width("{last}")')], specs=[spec('one_width_m', 'm_one')])
    assert not codes(check(by_name), 'error', 'blocker')
    cases = [(size_probe('m_bad', 'bad_m', 'width(mn)'), 'size_formula_rejected'),
             (size_probe('m_bad', 'bad_m', 'width("no_such_instance_*")'), 'size_pattern_matches_nothing'),
             (dict(size_probe('m_bad', 'bad_m', 'width("*")'), source_name=None), 'missing_source_name'),
             (size_probe('m_bad', 'score', 'width("*")'), 'size_probe_name_is_a_result')]
    for row, code in cases:
        config = mock(tmp_path, probes=[row], specs=[spec('bad_spec', 'm_bad')])
        assert code in codes(check(config), 'error'), code


def test_a_configuration_without_a_size_probe_is_what_it_was(tmp_path):
    plain = comp.compile_task(make_config(tmp_path), tasks.load_task(make_config(tmp_path).circuit).base_graph).plan
    assert plain.sizes == () and plain.request_names(('score',)) == ('score',)

    class Backend:
        """A passthrough backend used to detect unnecessary wrapping."""
        def run_simulation(self, request):
            return request
    backend = Backend()
    assert plain.wrap(backend) is backend and 'run_simulation' not in vars(backend)


def test_a_task_measures_one_way_and_a_size_probe_stands_beside_it(tmp_path):
    sized = mock(tmp_path, probes=[size_probe('m_wsum', 'width_sum_m', 'width("*")')], specs=[spec('width_sum_m', 'm_wsum')])
    maestro = sized.model_copy(update=dict(measurements=[
        m if m.result_source == 'size_estimate' else m.model_copy(update=dict(result_source='ade_output')) for m in sized.measurements]))
    assert task_save.measurement_kind(maestro) == task_save.MAESTRO           # as the same rows without the size probe
    only = sized.model_copy(update=dict(measurements=[m for m in sized.measurements if m.result_source == 'size_estimate']))
    with pytest.raises(ProfileError, match='only size estimates'):
        task_save.measurement_kind(only)


def test_the_network_is_told_such_a_spec_has_no_simulator_expression(tmp_path):
    sized = mock(tmp_path, probes=[size_probe('m_wsum', 'width_sum_m', 'width("*")')], specs=[spec('width_sum_m', 'm_wsum')])
    described = spec_descriptors.describe_specs(sized, bench=spec_descriptors.Bench())
    row = dict(zip(spec_descriptors.DESCRIPTOR_COLUMNS, described['width_sum_m']))
    assert row['signal_no_expression'] == 1.0 and row['analysis_other'] == 1.0


# ------------------------------------------------------------------------------- inside a lane
@dataclass(frozen=True)
class Result:                                         # the fields SpecPlan.extend reads, as in backends.backend.SimulationResult
    """The simulation-result fields required by size-spec extension."""
    metrics: dict
    metric_units: dict
    metric_validity: dict
    status: str = 'ok'
    candidate_evaluated: bool = True


def plan_for(tmp_path, specs, probes):
    """Compile the fixture's probes and specs into a size-evaluation plan."""
    return comp.compile_task(mock(tmp_path, specs=specs, probes=probes),
                             tasks.load_task(make_config(tmp_path).circuit).base_graph).plan


def test_the_lane_adds_the_size_result_as_a_result_of_its_own(tmp_path):
    plan = plan_for(tmp_path, [spec('cell_width_m', 'm_cell'), spec('twice', 'm_cell * 2', hard=False)],
                    [size_probe('m_cell', 'cell_width_m', CELL_WIDTH)])
    assert plan.sizes == (('cell_width_m', CELL_WIDTH, 'm'),)
    assert plan.injected == ('twice',)                          # the spec that IS the size probe is a result, not a computed spec
    # the simulator is never asked for it, neither directly nor through a spec that reads it
    assert plan.request_names(('score', 'cell_width_m', 'twice')) == ('score',)
    extended = plan.extend(Result({'score': 0.9}, {'score': 'fixture'}, {'score': True}), flip_flop())
    width = 0.253e-6 + 0.288e-6 * 16
    assert extended.metrics['cell_width_m'] == pytest.approx(width) and extended.metrics['twice'] == pytest.approx(2 * width)
    assert extended.metric_units['cell_width_m'] == 'm' and extended.metric_validity['cell_width_m'] is True
    assert extended.metrics['score'] == 0.9
    # without the candidate's sizes the value is invalid, and so is the spec computed from it - never a number
    blind = plan.extend(Result({'score': 0.9}, {'score': 'fixture'}, {'score': True}))
    assert blind.metrics['cell_width_m'] is None and blind.metric_validity['cell_width_m'] is False
    assert blind.metrics['twice'] is None and blind.metric_validity['twice'] is False
    with pytest.raises(ValueError, match='rename'):
        plan.extend(Result({'score': 0.9, 'cell_width_m': 1.0}, {}, {'score': True}), flip_flop())


def test_a_wrapped_backend_hands_the_candidates_own_sizes_to_the_formula(tmp_path):
    plan = plan_for(tmp_path, [spec('cell_width_m', 'm_cell')], [size_probe('m_cell', 'cell_width_m', CELL_WIDTH)])
    asked = []

    @dataclass(frozen=True)
    class Request:
        """A simulation request stand-in carrying required metrics and candidate sizes."""
        required_metrics: tuple
        parameters: dict

    class Backend:
        """A simulator stand-in returning only a valid fixture score."""
        def run_simulation(self, request):
            """Record requested metrics and return the score before size formulas are added."""
            asked.append(request.required_metrics)
            return Result({'score': 0.9}, {'score': 'fixture'}, {'score': True})
    backend = plan.wrap(Backend())
    small = backend.run_simulation(Request(('score', 'cell_width_m'), flip_flop()))
    large = backend.run_simulation(Request(('score', 'cell_width_m'), flip_flop(1040, 1560, gate=(410, 620), inverter=(260, 390))))
    assert asked == [('score',), ('score',)]
    assert small.metrics['cell_width_m'] == pytest.approx(0.253e-6 + 0.288e-6 * 16)
    assert large.metrics['cell_width_m'] == pytest.approx(0.253e-6 + 0.288e-6 * 22)


def test_a_run_scores_judges_and_records_the_size_probe(tmp_path):
    """End to end on the stand-in task: the sum of the varied widths is a Specs row with a limit some designs miss."""
    probe_run = mock(tmp_path / 'probe', probes=[size_probe('m_wsum', 'width_sum_m', 'width("*")')],
                     specs=[spec('width_sum_m', 'm_wsum')], threshold=-1.0, run=dict(max_evaluations=14))
    layout, state = execute(probe_run, tmp_path / 'probe')
    assert state == 'completed'
    reader = DatasetReader(layout.data)
    sums = {}
    for row in reader.rows('parameters'):
        if row['parameter_name'] == 'w':
            sums[row['evaluation_id']] = sums.get(row['evaluation_id'], 0.0) + row['executed_value']
    recorded = {r['evaluation_id']: r for r in reader.rows('metrics')
                if r['metric_name'] == 'width_sum_m' and r['aggregation_level'] == 'aggregate'}
    assert len(recorded) == 14 and all(r['measurement_id'] == 'm_wsum' and r['valid'] for r in recorded.values())
    for evaluation_id, row in recorded.items():
        assert math.isclose(row['raw_value'], sums[evaluation_id], rel_tol=1e-9)             # recorded in metres, as every length
    # now with a limit between two of the sums that run saw (the same seed: the same designs): the reward's view and the
    # independent check agree on every design
    distinct = sorted(set(round(v, 12) for v in sums.values()))
    assert len(distinct) > 1
    middle = (distinct[len(distinct) // 2 - 1] + distinct[len(distinct) // 2]) / 2            # in metres
    config = mock(tmp_path / 'limit', probes=[size_probe('m_wsum', 'width_sum_m', 'width("*")')],
                  specs=[spec('width_sum_m', 'm_wsum', upper=middle * 1e6)], threshold=-1.0, run=dict(max_evaluations=14))
    layout, state = execute(config, tmp_path / 'limit')
    assert state == 'completed'
    reader = DatasetReader(layout.data)
    events = read_jsonl(layout.logs / 'events.jsonl')
    assert events and not [e for e in events if e.get('event') == 'feasibility_disagreement']
    rows = {r['evaluation_id']: r for r in reader.rows('metrics')
            if r['metric_name'] == 'width_sum_m' and r['aggregation_level'] == 'aggregate'}
    judged = [e for e in reader.rows('evaluations') if e['valid'] and e['env_success'] is not None]
    assert judged and all(e['env_success'] == e['all_hard_constraints_satisfied'] for e in judged)
    assert all(e['all_hard_constraints_satisfied'] == (rows[e['evaluation_id']]['raw_value'] <= middle) for e in judged)
    assert {e['all_hard_constraints_satisfied'] for e in judged} == {True, False}          # the size really decided something
