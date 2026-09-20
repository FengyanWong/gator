"""Offline strict-requalification tests. Generated evidence is explicitly test-only."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from analog_optimizer.backends.backend import NetlistArtifact, SimulationResult, SimulationStatus
ROOT = Path(__file__).resolve().parents[1]
# Kept outside the analog_optimizer package so its source digest, and saved checkpoints, stay valid.
spec = importlib.util.spec_from_file_location('vco_requalification_test', ROOT/'examples/vco_requalification.py')
requalification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(requalification)
AGREEMENT_LIMITS, build_plan, compare, execute, freeze_plan, load_profile, validate_frozen_plan = (
    getattr(requalification, name) for name in ('AGREEMENT_LIMITS', 'build_plan', 'compare', 'execute',
                                                 'freeze_plan', 'load_profile', 'validate_frozen_plan'))
FAST, STRICT = (load_profile(ROOT, mode) for mode in ('fast', 'reference'))
UNITS = {s['metric_id']: s['unit'] for s in
         json.loads((ROOT/'configs/m6_real_cross_category.json').read_text())['classes']['vco']['specs']['test']}
BASE, A, B, C = (1e-6, 1e-6, 1e-6), (1.08e-6, 1.03e-6, 1.04e-6), (1.1e-6, 1e-6, 1e-6), (1.085e-6, 1.05e-6, 1.07e-6)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


def rows(widths):
    return [dict(device=f'XU1/MS{i}', parameter='w', value=w) for i, w in enumerate(widths, 1)]


def metrics(frequency=177e6, power=27.5e-6):
    return dict(vco_frequency_hz=frequency, vco_frequency_low_hz=85e6, vco_frequency_high_hz=285e6,
        vco_tuning_gain_hz_per_v=1e9, vco_tuning_fraction=1.13, supply_power_w=power, vco_minimum_swing_v=.9,
        vco_max_period_spread=1e-5, vco_max_window_drift=1e-7, vco_startup_detection_s=1.1e-7, vco_duty_cycle=.58)


FAST_METRICS = {BASE: metrics(171e6, 26.5e-6), A: metrics(177.5e6), B: metrics(175.02e6, 27.2e-6), C: metrics(179.8e6, 27.9e-6)}


def make_pilot(tmp_path, runs):
    """Artificial files exercise validation; these never certify a real run."""
    run = tmp_path/'pilot'
    write(run/'report.json', dict(completed=True, origin='real', plan_sha256='offline-test-plan'))
    write(run/'audit.json', dict(passed=True, plan_sha256='offline-test-plan'))
    test_runs = []
    for method, seed, candidates in runs:
        records = []
        for call, widths in enumerate(candidates, 1):
            values = FAST_METRICS[widths]
            success = 175e6 <= values['vco_frequency_hz'] <= 180e6
            job = run/'vco/simulations'/f'{method}-{seed}-{call}'
            write(job/'bridge_result.json', dict(analysis_settings=FAST.analysis_settings,
                executed_sha256=f'fast-deck-{widths!r}', source_sha256=f'source-{widths!r}',
                applied_parameters=rows(widths), library='OFFLINE_TEST', cell='tb_vco_m6_v1',
                model_file='/offline-test/model.scs', condition=dict(purpose='nominal')))
            record = run/'vco/candidates'/f'{method}-{seed}-{call}.json'
            write(record, dict(success=success, status='ok', origin='real', state='completed', evaluation_valid=True,
                cache_hit=False, applied_parameters=rows(widths), artifact_directory=str(job),
                netlist_sha256=f'fast-deck-{widths!r}', metrics=values, metric_units=UNITS))
            records.append((str(record), success, widths))
        first = next((i for i, r in enumerate(records, 1) if r[1]), None)
        best = records[first-1][2] if first else candidates[0]
        test_runs.append(dict(circuit_class='vco', partition='test', origin='real', method=method, seed=seed,
            records=[r[0] for r in records], success=first is not None, first_feasible_call=first,
            best_metrics=FAST_METRICS[best], best_parameters=rows(best)))
    write(run/'vco/report.json', dict(completed=True, origin='real', unexecuted_test_runs=[], test_runs=test_runs))
    reference = tmp_path/'strict/verification.json'
    write(reference, dict(passed=True, origin='real', timestep_scale=1., analysis_settings=STRICT.analysis_settings,
        full_snapshot_restored=True, stages=[dict(name='baseline', status='ok', evaluation_valid=True,
            parameters=rows(BASE), metrics=FAST_METRICS[BASE], netlist_sha256=f'strict-deck-{BASE!r}')]))
    return run, reference


@pytest.fixture
def pilot(tmp_path):
    return make_pilot(tmp_path, [('gt_adapt', 17, (BASE, BASE, A)), ('mlp_adapt', 17, (BASE, A)),
                                 ('gt_scratch', 29, (B, BASE, BASE, BASE, C)), ('gt_frozen', 17, (BASE, BASE))])


class StrictStub:
    """Deterministic reference-mode responses; never a real simulator."""
    def __init__(self, response=lambda widths, call: (FAST_METRICS[widths], SimulationStatus.OK, 1), drift=False):
        self.widths, self.response, self.calls, self.restored, self.drift = BASE, response, 0, False, drift

    def read_cdf_snapshot(self):
        return dict(widths=list(self.widths))

    def set_parameters(self, assignment):
        self.widths = tuple(assignment[(f'XU1/MS{i}', 'w')] for i in (1, 2, 3))

    def generate_netlist(self, work_root):
        path = Path(work_root)/f'{self.calls}.scs'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(repr(self.widths))
        return NetlistArtifact(path, f'export-{self.calls}', f'strict-deck-{self.widths!r}', 'real')

    def run_simulation(self, request):
        self.calls += 1
        job = Path(request.work_root)/f'job-{self.calls}'
        write(job/'bridge_result.json', dict(source_sha256=f'source-{self.widths!r}',
                                              analysis_settings=STRICT.analysis_settings))
        values, status, invocations = self.response(self.widths, self.calls)
        return SimulationResult(job_id=f'job-{self.calls}', backend_kind='offline-stub', origin='real', status=status,
            reason_code='offline_stub', retryable=False, candidate_evaluated=bool(values), metrics=values,
            metric_units=UNITS if values else {}, metric_validity={k: True for k in values},
            applied_parameters=dict(request.parameters), artifact_directory=job, elapsed_seconds=1.,
            simulator_invocations=invocations)

    def restore(self):
        self.restored = True
        self.widths = A if self.drift else BASE


def test_plan_collects_unique_first_feasible_designs_with_every_claim(pilot):
    plan = build_plan(ROOT, *pilot)
    assert [d['parameters'] for d in plan['designs']] == [rows(A), rows(B)]
    assert plan['designs'][0]['claims'] == [dict(method='gt_adapt', seed=17, call=3, first_feasible=True),
                                            dict(method='mlp_adapt', seed=17, call=2, first_feasible=True)]
    assert plan['stages'] == ['baseline', 'design-01', 'design-02', 'restored']
    assert plan['planned_calls'] == plan['call_cap'] == 4 and plan['claims'] == 3
    assert (plan['training_updates'], plan['automatic_retries'], plan['cache_hits']) == (0, 0, 0)
    assert plan['strict_settings'] == STRICT.analysis_settings != plan['fast_settings'] == FAST.analysis_settings
    assert build_plan(ROOT, *pilot) == plan
    complete = build_plan(ROOT, *pilot, scope='feasible')
    assert [d['parameters'] for d in complete['designs']] == [rows(A), rows(C), rows(B)]
    assert complete['designs'][1]['claims'] == [dict(method='gt_scratch', seed=29, call=5, first_feasible=False)]
    assert complete['sha256'] != plan['sha256']


@pytest.mark.parametrize('damage,message', [
    (lambda run, fold: write(run/'audit.json', dict(passed=False, plan_sha256='offline-test-plan')), 'independent audit'),
    (lambda run, fold: fold['test_runs'][3].update(success=True), 'Run success differs'),
    (lambda run, fold: fold['test_runs'][0].update(best_parameters=rows(B)), 'not the first feasible'),
    (lambda run, fold: fold['test_runs'][0]['records'].__setitem__(0, str(run.parent/'outside.json')), 'escapes'),
    (lambda run, fold: fold.update(unexecuted_test_runs=['gt_adapt']), 'Completed real pilot'),
    (lambda run, fold: fold['test_runs'][0].update(circuit_class='ldo'), 'Unexpected held-out run')])
def test_plan_rejects_unaudited_inconsistent_or_escaping_evidence(pilot, damage, message):
    run, reference = pilot
    write(run.parent/'outside.json', dict(success=False))
    fold = json.loads((run/'vco/report.json').read_text())
    damage(run, fold)
    write(run/'vco/report.json', fold)
    with pytest.raises(ValueError, match=message):
        build_plan(ROOT, run, reference)


@pytest.mark.parametrize('edit,message', [
    (lambda record, bridge: bridge.update(analysis_settings=STRICT.analysis_settings), 'Fast execution evidence'),
    (lambda record, bridge: bridge.update(executed_sha256='another-deck'), 'Fast execution evidence'),
    (lambda record, bridge: record.update(cache_hit=True), 'Invalid feasible candidate'),
    (lambda record, bridge: bridge.update(source_sha256='another-source'), 'different fast evidence')])
def test_plan_rejects_inconsistent_fast_execution_evidence(pilot, edit, message):
    run, reference = pilot
    record_path = run/'vco/candidates/mlp_adapt-17-2.json'
    record = json.loads(record_path.read_text())
    bridge_path = Path(record['artifact_directory'])/'bridge_result.json'
    bridge = json.loads(bridge_path.read_text())
    edit(record, bridge)
    write(record_path, record); write(bridge_path, bridge)
    with pytest.raises(ValueError, match=message):
        build_plan(ROOT, run, reference)


def test_plan_requires_grid_widths_and_qualified_strict_baseline(tmp_path):
    off_grid = (1.0801e-6, 1.03e-6, 1.04e-6)
    FAST_METRICS[off_grid] = metrics()
    try:
        with pytest.raises(ValueError, match='bounds or CDF-compatible grid'):
            build_plan(ROOT, *make_pilot(tmp_path/'grid', [('gt_adapt', 17, (off_grid,))]))
    finally:
        del FAST_METRICS[off_grid]
    run, reference = make_pilot(tmp_path/'baseline', [('gt_adapt', 17, (A,))])
    saved = json.loads(reference.read_text())
    write(reference, dict(saved, analysis_settings=FAST.analysis_settings))
    with pytest.raises(ValueError, match='strict baseline evidence'):
        build_plan(ROOT, run, reference)
    write(reference, saved)
    with pytest.raises(ValueError, match='No feasible VCO design'):
        build_plan(ROOT, *make_pilot(tmp_path/'none', [('gt_frozen', 17, (BASE,))]))


def test_frozen_plan_refuses_overwrite_tampering_and_evidence_drift(pilot, tmp_path):
    run, reference = pilot
    plan, path = build_plan(ROOT, run, reference), tmp_path/'frozen/plan.json'
    assert freeze_plan(path, plan) == plan['sha256'] and validate_frozen_plan(ROOT, path) == plan
    with pytest.raises(ValueError, match='Refusing to overwrite'):
        freeze_plan(path, plan)
    tampered = tmp_path/'tampered.json'
    write(tampered, dict(plan, call_cap=plan['call_cap']+10))
    with pytest.raises(ValueError, match='digest mismatch'):
        validate_frozen_plan(ROOT, tampered)
    fold = json.loads((run/'vco/report.json').read_text())
    fold['test_runs'] = fold['test_runs'][:1]
    write(run/'vco/report.json', fold)
    with pytest.raises(ValueError, match='no longer matches'):
        validate_frozen_plan(ROOT, path)


def test_limits_are_the_ones_frozen_for_the_fast_policy():
    sys.path.insert(0, str(ROOT/'examples'))
    try:
        spec = importlib.util.spec_from_file_location('vco_runtime_limits_test', ROOT/'examples/compare_vco_runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
    finally:
        sys.path.remove(str(ROOT/'examples'))
    assert runtime.LIMITS == AGREEMENT_LIMITS


def test_execution_counts_every_call_checks_both_baselines_and_restores(pilot, tmp_path):
    plan, backend, seen = build_plan(ROOT, *pilot), StrictStub(), []
    report = execute(plan, backend, STRICT, tmp_path/'out', protected=lambda: seen.append(1) or dict(ota='unchanged'),
                     metadata=dict(session_dir='offline'))
    assert report['passed'] and report['calls_attempted'] == report['confirmed_invocations'] == backend.calls == 4
    assert [s['name'] for s in report['stages']] == plan['stages'] and backend.restored and len(seen) == 2
    assert report['full_snapshot_restored'] and report['protected_circuits_unchanged'] and report['training_updates'] == 0
    assert [s['test_success'] for s in report['stages']] == [False, True, True, False]
    assert report['session_dir'] == 'offline' and report['plan_sha256'] == plan['sha256']
    saved = json.loads((tmp_path/'out/verification.json').read_text())
    assert saved == json.loads(json.dumps(report))
    assert json.loads((tmp_path/'out/before.json').read_text()) == json.loads((tmp_path/'out/after.json').read_text())
    with pytest.raises(ValueError, match='Strict numerical policy'):
        execute(plan, StrictStub(), FAST, tmp_path/'fast')


@pytest.mark.parametrize('response,error,calls', [
    (lambda w, call: (metrics(171.1e6, 26.5e-6), SimulationStatus.OK, 1), 'Baseline metrics differ', 1),
    (lambda w, call: (FAST_METRICS[w], SimulationStatus.OK, None if call == 2 else 1), 'Uncertain simulator invocation', 2),
    (lambda w, call: ({}, SimulationStatus.TIMEOUT, 1) if call == 2 else (FAST_METRICS[w], SimulationStatus.OK, 1),
     'Strict execution failed', 2),
    (lambda w, call: ({}, SimulationStatus.MEASUREMENT_ERROR, 1) if call == 4 else (FAST_METRICS[w], SimulationStatus.OK, 1),
     'Strict baseline failed', 4)])
def test_execution_stops_without_retry_and_still_restores(pilot, tmp_path, response, error, calls):
    plan, backend = build_plan(ROOT, *pilot), StrictStub(response)
    with pytest.raises(RuntimeError, match=error):
        execute(plan, backend, STRICT, tmp_path/'out')
    saved = json.loads((tmp_path/'out/verification.json').read_text())
    assert backend.calls == saved['calls_attempted'] == calls and backend.restored
    assert not saved['passed'] and saved['full_snapshot_restored'] and saved['error']


def test_execution_rejects_a_changed_budget_and_failed_restoration(pilot, tmp_path):
    plan = build_plan(ROOT, *pilot)
    backend = StrictStub()
    with pytest.raises(ValueError, match='frozen budget'):
        execute(dict(plan, call_cap=3), backend, STRICT, tmp_path/'cap')
    with pytest.raises(ValueError, match='frozen budget'):
        execute(dict(plan, stages=plan['stages'][:-1]), backend, STRICT, tmp_path/'stages')
    assert backend.calls == 0
    with pytest.raises(RuntimeError, match='restoration failed'):
        execute(plan, StrictStub(drift=True), STRICT, tmp_path/'drift')
    assert not json.loads((tmp_path/'drift/verification.json').read_text())['passed']


def strict_response(overrides):
    def response(widths, call):
        if widths in overrides:
            return overrides[widths]
        return FAST_METRICS[widths], SimulationStatus.OK, 1
    return response


def test_comparison_separates_policy_agreement_from_lost_feasibility(pilot, tmp_path):
    plan = build_plan(ROOT, *pilot, scope='feasible')
    # B sits 0.011% above the floor; a 0.017% strict shift stays inside the 0.1% agreement limit.
    backend = StrictStub(strict_response({B: (metrics(174.99e6, 27.2e-6), SimulationStatus.OK, 1)}))
    report = compare(plan, execute(plan, backend, STRICT, tmp_path/'out'))
    assert report['passed'] and report['fast_policy_agreement_passed'] and report['new_simulator_calls'] == 0
    assert report['designs'] == report['strict_valid_designs'] == 3 and report['strict_confirmed_designs'] == 2
    assert report['unconfirmed_designs'] == ['design-03']
    assert report['maximum_differences']['vco_frequency_hz'] == pytest.approx(.03e6/174.99e6)
    runs = {(r['method'], r['seed']): r for r in report['runs']}
    assert runs[('gt_adapt', 17)]['first_feasible_confirmed'] and runs[('gt_adapt', 17)]['strict_success']
    lost = runs[('gt_scratch', 29)]
    assert not lost['first_feasible_confirmed'] and lost['strict_success'] and lost['first_strict_feasible_call'] == 5
    assert (lost['requalified_candidates'], lost['strict_confirmed_candidates']) == (2, 1)
    assert report['methods']['gt_scratch'] == dict(fast_successes=1, first_feasible_confirmed=0, strict_successes=1)


def test_best_scope_never_rescores_a_run(pilot, tmp_path):
    plan = build_plan(ROOT, *pilot)
    backend = StrictStub(strict_response({B: (metrics(174.99e6, 27.2e-6), SimulationStatus.OK, 1)}))
    report = compare(plan, execute(plan, backend, STRICT, tmp_path/'out'))
    lost = next(r for r in report['runs'] if r['method'] == 'gt_scratch')
    assert report['passed'] and lost['first_feasible_confirmed'] is False and lost['strict_success'] is None
    assert report['methods']['gt_scratch']['strict_successes'] is None


def test_comparison_fails_on_policy_disagreement_or_invalid_strict_run(pilot, tmp_path):
    plan = build_plan(ROOT, *pilot)
    shifted = StrictStub(strict_response({A: (metrics(177.5e6*1.002), SimulationStatus.OK, 1)}))
    report = compare(plan, execute(plan, shifted, STRICT, tmp_path/'shifted'))
    assert not report['passed'] and report['strict_confirmed_designs'] == 2
    assert not report['comparisons'][0]['comparisons']['vco_frequency_hz']['passed']
    invalid = StrictStub(strict_response({A: ({}, SimulationStatus.MEASUREMENT_ERROR, 1)}))
    verification = execute(plan, invalid, STRICT, tmp_path/'invalid')
    assert verification['passed'] and verification['stages'][1]['status'] == 'measurement_error'
    report = compare(plan, verification)
    assert not report['passed'] and report['unconfirmed_designs'] == ['design-01']
    assert report['strict_valid_designs'] == 1 and report['comparisons'][0]['comparisons'] is None


@pytest.mark.parametrize('damage,message', [
    (lambda v: v.update(plan_sha256='another-plan'), 'complete execution'),
    (lambda v: v.update(passed=False), 'complete execution'),
    (lambda v: v['stages'].pop(), 'complete execution'),
    (lambda v: v['stages'][1].update(parameters=rows(B)), 'Executed widths differ'),
    (lambda v: v['stages'][1].update(test_success=False), 'Saved strict feasibility differs'),
    (lambda v: write(Path(v['stages'][1]['job'])/'bridge_result.json',
                     dict(source_sha256='another-source', analysis_settings=STRICT.analysis_settings)), 'Physical netlists differ'),
    (lambda v: write(Path(v['stages'][1]['job'])/'bridge_result.json',
                     dict(source_sha256=f'source-{A!r}', analysis_settings=FAST.analysis_settings)), 'another numerical policy')])
def test_comparison_rejects_foreign_incomplete_or_altered_verification(pilot, tmp_path, damage, message):
    plan = build_plan(ROOT, *pilot)
    verification = deepcopy(execute(plan, StrictStub(), STRICT, tmp_path/'out'))
    damage(verification)
    with pytest.raises(ValueError, match=message):
        compare(plan, verification)
