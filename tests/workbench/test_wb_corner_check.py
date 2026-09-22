"""Corner check (status record 7.62): a finished run's best designs simulated again at the five fixed corners.

MOCK runs go through the whole path, the detached worker included. The REAL path runs against a fake adapter that
records every call: no Virtuoso, no Spectre, no budget."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from analog_optimizer.backends.backend import NetlistArtifact, SimulationResult, SimulationStatus
from analog_optimizer.measurements.specs import SpecificationEvaluator

from gator_workbench import corner_check as cc, schema, tasks
from gator_workbench.api import create_app
from gator_workbench.compile import compile_task
from gator_workbench.engine import RunLock
from gator_workbench.storage.atomic import read_json, write_json
from helpers import execute, make_config

CORNERS = ('nominal', 'ss_hot_low', 'ff_cold_high', 'fs_nominal', 'sf_nominal')


@pytest.fixture(scope='module')
def finished(tmp_path_factory):
    """One finished MOCK run with several feasible designs (threshold 0.9), shared by the read-only tests."""
    root = tmp_path_factory.mktemp('corner-run')
    layout, state = execute(make_config(root, threshold=0.9, run=dict(max_evaluations=30)), root)
    assert state == 'completed'
    return root, layout


def fingerprint(directory):
    return {p.relative_to(directory).as_posix(): p.stat().st_size for p in Path(directory).rglob('*')
            if p.is_file() and 'corner_checks' not in p.parts}


# ------------------------------------------------------------------------------------------------ the plan (free)
def test_plan_picks_the_safest_distinct_feasible_designs(finished):
    _, layout = finished
    plan = cc.plan(layout.run_dir)
    assert plan['supported'] and plan['mock'] and plan['notice'] == cc.MOCK_NOTICE
    assert [c['id'] for c in plan['corners']] == list(CORNERS)
    assert plan['corners'][1]['label'] == 'SS, 125 °C, 0.9 V'
    assert len(plan['designs']) == 3 and plan['simulations'] == 15
    margins = [d['min_margin'] for d in plan['designs']]
    assert margins == sorted(margins, reverse=True) and all(m >= 0 for m in margins)
    assert all(d['tightest_spec'] == 'score' for d in plan['designs'])
    keys = {tuple((a['device'], a['parameter'], a['value']) for a in d['assignment']) for d in plan['designs']}
    assert len(keys) == 3, 'identical widths are counted once'
    assert plan['counts']['feasible'] >= plan['counts']['distinct'] >= 3
    # the margin is the distance to the limit over the spec's scale: score >= 0.9 with scale 1
    first = plan['designs'][0]
    assert math.isclose(first['min_margin'], first['spec_values']['score'] - 0.9, rel_tol=1e-9)


def test_plan_with_fewer_designs_costs_fewer_simulations(finished):
    _, layout = finished
    plan = cc.plan(layout.run_dir, designs=1)
    assert len(plan['designs']) == 1 and plan['simulations'] == 5
    assert cc.plan(layout.run_dir, designs=7)['limit'] == cc.MAX_DESIGNS


def test_a_run_without_a_feasible_design_has_nothing_to_check(tmp_path):
    layout, _ = execute(make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=6)), tmp_path)
    plan = cc.plan(layout.run_dir)
    assert not plan['supported'] and plan['code'] == 'no_feasible_design' and plan['simulations'] == 0
    with pytest.raises(cc.CheckRefused) as refused:
        cc.prepare(layout.run_dir, designs=3)
    assert refused.value.code == 'no_feasible_design'
    assert not (layout.run_dir / cc.CHECK_DIR).exists(), 'a refusal creates nothing'


def test_a_working_run_is_not_checked(tmp_path):
    layout, _ = execute(make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=6)), tmp_path)
    lock = RunLock(layout.control / 'run.lock')
    lock.acquire()
    try:
        write_json(layout.status, dict(read_json(layout.status), state='running'))
        plan = cc.plan(layout.run_dir)
        assert not plan['supported'] and plan['code'] == 'run_working'
    finally:
        lock.release()


def test_only_profiles_that_accept_the_corners_can_be_checked():
    assert cc.checkable_real_tasks() == ('real:gpdk045_ota5', 'real:gpdk045_ota7')
    corners = cc.screening_corners()[0]
    for name in ('gpdk045_ldo', 'gpdk045_vco'):
        problem = cc._corner_problem(tasks._verified_profile(name), corners)
        assert problem and 'nominal' in problem
        text = cc._unsupported(f'real:{name}', problem)
        assert 'normal condition only' in text and 'real:gpdk045_ota5, real:gpdk045_ota7' in text


# ------------------------------------------------------------------------------------------------ a MOCK check
def test_mock_check_simulates_every_design_at_every_corner_and_grades_it(tmp_path):
    layout, _ = execute(make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=30)), tmp_path)
    before = fingerprint(layout.run_dir)
    plan = cc.plan(layout.run_dir)
    directory = cc.prepare(layout.run_dir, designs=3, expected=[d['evaluation_id'] for d in plan['designs']],
                           simulations=plan['simulations'])
    request = read_json(directory / 'request.json')
    assert request['authorization'] == dict(real_simulation=False, authorized_simulations=None)
    assert read_json(directory / 'status.json')['state'] == 'starting'
    assert cc.execute(directory) == 'completed'

    status = cc.check_status(layout.run_dir, directory.name)
    assert status['status']['state'] == 'completed' and not status['alive']
    assert status['status']['done'] == status['status']['started'] == 15
    results = status['results']
    assert [(r['design'], r['corner']) for r in results] == [(d, c) for d in range(3) for c in CORNERS]
    assert all(r['condition']['purpose'] == 'pvt_validation' for r in results)
    # MOCK physics: the optimum moves per corner, so a corner's score differs from the nominal one
    for design in range(3):
        scores = {r['corner']: r['metrics']['score'] for r in results if r['design'] == design}
        assert scores['nominal'] == pytest.approx(plan['designs'][design]['spec_values']['score'], rel=1e-9)
        assert len({round(v, 12) for v in scores.values()}) == 5
    summary = status['summary']
    for entry in summary['designs']:
        states = [r['state'] for r in results if r['evaluation_id'] == entry['evaluation_id']]
        assert entry['corner_states'] == dict(zip(CORNERS, states))
        assert entry['disposition'] == ('rejected' if 'failed' in states else 'accepted')
        assert entry['pass_rate'] == states.count('passed') / 5
        assert entry['nominal_repeat'] == dict(matches=True, differences=[])
        worst = entry['worst_case_metrics']['score']
        assert worst['value'] == min(r['metrics']['score'] for r in results if r['evaluation_id'] == entry['evaluation_id'])
        assert worst['valid_corner_count'] == 5 and worst['complete']
    failing = [r for r in results if r['state'] == 'failed']
    assert all(r['failing'][0]['metric_id'] == 'score' and r['failing'][0]['value'] < 0.9 for r in failing)
    assert sum(summary['verdicts'].values()) == 3
    assert summary['budget'] == dict(authorized=None, simulations=15, started=15, completed=15, simulator_invocations=None)
    assert cc.list_checks(layout.run_dir)[0]['check_id'] == directory.name
    assert fingerprint(layout.run_dir) == before, 'the run itself is never touched'


def test_a_stop_before_the_first_simulation_leaves_everything_inconclusive(tmp_path):
    layout, _ = execute(make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=12)), tmp_path)
    directory = cc.prepare(layout.run_dir, designs=1)
    write_json(directory / 'control' / 'stop.json', dict(command='stop'))
    assert cc.execute(directory) == 'stopped'
    status = cc.check_status(layout.run_dir, directory.name)
    assert status['results'] == [] and status['summary']['verdicts'] == dict(accepted=0, rejected=0, inconclusive=1)
    with pytest.raises(cc.CheckRefused) as refused:
        cc.request_stop(layout.run_dir, directory.name)
    assert refused.value.code == 'not_running'


def test_an_unknown_corner_makes_a_design_inconclusive_never_failed(tmp_path, monkeypatch):
    from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
    layout, _ = execute(make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=12)), tmp_path)
    original, calls = SyntheticSizingBackend.run_simulation, []

    def flaky(self, request):
        calls.append(1)
        result = original(self, request)
        if len(calls) == 2:           # the ss corner of the only design: a timeout, not a design verdict
            from dataclasses import replace
            return replace(result, status=SimulationStatus.TIMEOUT, candidate_evaluated=False, metrics={})
        return result
    monkeypatch.setattr(SyntheticSizingBackend, 'run_simulation', flaky)
    directory = cc.prepare(layout.run_dir, designs=1)
    assert cc.execute(directory) == 'completed'
    status = cc.check_status(layout.run_dir, directory.name)
    assert [r['state'] for r in status['results']][1] == 'unknown'
    entry = status['summary']['designs'][0]
    assert entry['unknown_corners'] == ['ss_hot_low'] and entry['pass_rate'] is None and entry['robust_score'] is None
    assert entry['disposition'] in ('inconclusive', 'rejected')        # rejected only by a corner that DID fail
    assert entry['disposition'] == ('rejected' if entry['failed_corners'] else 'inconclusive')


def test_a_changed_plan_or_count_is_refused(finished):
    _, layout = finished
    with pytest.raises(cc.CheckRefused) as refused:
        cc.prepare(layout.run_dir, designs=3, expected=['someone-else'])
    assert refused.value.code == 'plan_changed'
    with pytest.raises(cc.CheckRefused) as refused:
        cc.prepare(layout.run_dir, designs=3, simulations=14)
    assert refused.value.code == 'plan_changed'
    with pytest.raises(cc.CheckRefused):
        cc.check_directory(layout.run_dir, '../../etc')


# ------------------------------------------------------------------------------------------------ the REAL path, faked
class FakeAdapter:
    """VirtuosoBridgeBackend's surface as the check uses it. script: {simulation number: status}; widths: the cell."""
    calls, script, fail_readback, instances = [], {}, False, []

    def __init__(self, config, circuit):
        self.circuit, self.cell, self.simulations, self.session_dir = circuit, None, 0, Path('/fake/journal')
        FakeAdapter.instances.append(self)

    def connect(self):
        FakeAdapter.calls.append(('connect',))
        self.cell = {key: 4.4e-6 for key in self.circuit.writable_keys}
        self.initial = dict(self.cell)

    def read_parameters(self):
        FakeAdapter.calls.append(('read',))
        return dict(self.cell)

    def set_parameters(self, parameters):
        FakeAdapter.calls.append(('write', parameters[('XU1/M1', 'w')]))
        self.cell = dict(parameters)

    def generate_netlist(self, work_root, *, condition=None):
        FakeAdapter.calls.append(('export', condition.corner.id, condition.purpose))
        path = Path(work_root) / f'deck-{len(FakeAdapter.calls)}.scs'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(condition)))
        return NetlistArtifact(path, path.stem, 'sha', 'real', condition)

    def run_simulation(self, request):
        self.simulations += 1
        FakeAdapter.calls.append(('simulate', request.condition.corner.id))
        status = FakeAdapter.script.get(self.simulations, SimulationStatus.OK)
        corner, width = request.condition.corner, request.parameters[('XU1/M1', 'w')]
        metrics = dict(gain_db_at_start=30.0, unity_gain_hz=4.0e6 * (0.8 if corner.id == 'ss_hot_low' and width < 4.1e-6 else 1),
                       phase_margin_estimate_deg=91.0, supply_power_w=1.5e-6 * corner.supply_v, output_dc_v=0.5,
                       unity_downward_crossings=1.0)
        ok = status == SimulationStatus.OK
        directory = Path(request.work_root) / f'job-{self.simulations}'
        directory.mkdir(parents=True, exist_ok=True)
        return SimulationResult(directory.name, 'fake', 'real', status, 'fake', not ok, ok, metrics if ok else {},
                                FakeAdapter.units, {k: True for k in metrics} if ok else {}, dict(request.parameters),
                                directory, 0.01, request.condition, simulator_invocations=1)

    def restore(self):
        FakeAdapter.calls.append(('restore',))
        self.cell = dict(self.initial)
        if FakeAdapter.fail_readback:
            self.cell[('XU1/M1', 'w')] = 4.0e-6

    def close(self):
        FakeAdapter.calls.append(('close',))


def real_context():
    raw = dict(tasks.real_starter_config('real:gpdk045_ota5'), run=dict(max_evaluations=5, seed=1))
    config = schema.WorkbenchConfig.model_validate(raw)
    profile = tasks._verified_profile('gpdk045_ota5')
    compiled = compile_task(config, profile.optimization_graph())
    corners, nominal, post = cc.screening_corners(profile)
    FakeAdapter.units = {s.metric_id: s.unit for s in compiled.specs}
    return SimpleNamespace(config=config, compiled=compiled, profile=profile, corners=corners, nominal=nominal, post=post,
                           evaluator=SpecificationEvaluator(compiled.specs), expected_keys=set(profile.writable_keys),
                           task_key='real:gpdk045_ota5', mock=False, origin='real')


@pytest.fixture
def real_check(tmp_path, monkeypatch):
    """A check folder of a real OTA5 run with two designs (4.0 um fails the ss corner, 4.2 um passes everything)."""
    context = real_context()
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    write_json(run_dir / 'run_manifest.json', dict(run_id='r1', mock=False, task_definition_hash='h'))
    designs = [dict(evaluation_id=f'e{i}', reward=0.0, min_margin=0.1, tightest_spec='unity_gain_hz',
                    spec_values=dict(gain_db_at_start=30.0, unity_gain_hz=4.0e6),
                    assignment=[dict(device=d, parameter=p, value=width) for d, p in sorted(context.profile.writable_keys)])
               for i, width in enumerate((4.0e-6, 4.2e-6))]
    directory = run_dir / cc.CHECK_DIR / '20260922T000000Z-0000abcd'
    write_json(directory / 'request.json', dict(
        check_id=directory.name, run_id='r1', run_dir=str(run_dir), task_key='real:gpdk045_ota5', mock=False,
        task_definition_hash='h', corners=[cc.corner_record(c) for c in context.corners], designs=designs,
        simulations=10, authorization=dict(real_simulation=True, authorized_simulations=10)))
    write_json(directory / 'status.json', dict(state='starting'))
    monkeypatch.setattr(cc, 'Context', lambda layout, manifest, allow_real=False: context)
    monkeypatch.setattr(cc.Worker, '_bridge_parts', lambda self: (None, context.profile))
    monkeypatch.setattr('analog_optimizer.backends.virtuoso_bridge.VirtuosoBridgeBackend', FakeAdapter)
    FakeAdapter.calls, FakeAdapter.script, FakeAdapter.fail_readback, FakeAdapter.instances = [], {}, False, []
    return run_dir, directory


def test_real_check_writes_each_design_once_simulates_each_corner_and_restores(real_check):
    run_dir, directory = real_check
    assert cc.execute(directory, allow_real=True) == 'completed'
    calls = FakeAdapter.calls
    assert calls[:3] == [('connect',), ('read',), ('write', 4.0e-6)]
    per_design = [('export', c, 'pvt_validation') for c in CORNERS]
    exports = [c for c in calls if c[0] == 'export']
    assert exports == per_design * 2
    assert [c for c in calls if c[0] == 'write'] == [('write', 4.0e-6), ('write', 4.2e-6)]
    assert calls[-3:] == [('restore',), ('read',), ('close',)]
    status = cc.check_status(run_dir, directory.name)
    summary = status['summary']
    assert [d['disposition'] for d in summary['designs']] == ['rejected', 'accepted']
    assert summary['designs'][0]['corner_states']['ss_hot_low'] == 'failed'
    failing = status['results'][1]['failing'][0]
    assert failing['metric_id'] == 'unity_gain_hz' and failing['value'] == pytest.approx(3.2e6)
    # the measured power follows the corner's supply (1.1 V at ff) and the worst case names its corner
    assert summary['designs'][1]['worst_case_metrics']['supply_power_w']['corner_id'] == 'ff_cold_high'
    assert summary['restoration']['state'] == 'restored' and status['status']['state'] == 'completed'
    assert summary['budget'] == dict(authorized=10, simulations=10, started=10, completed=10, simulator_invocations=10)


def test_real_check_needs_the_authorization_and_touches_nothing_without_it(real_check):
    run_dir, directory = real_check
    assert cc.execute(directory, allow_real=False) == 'failed'
    assert FakeAdapter.calls == []
    assert cc.check_status(run_dir, directory.name)['status']['error']['code'] == 'real_authorization_required'


def test_two_infrastructure_failures_in_a_row_stop_the_check_and_restore_the_cell(real_check):
    run_dir, directory = real_check
    FakeAdapter.script = {3: SimulationStatus.TIMEOUT, 4: SimulationStatus.BACKEND_ERROR}
    assert cc.execute(directory, allow_real=True) == 'failed'
    assert len([c for c in FakeAdapter.calls if c[0] == 'simulate']) == 4, 'no budget spent after the second failure'
    status = cc.check_status(run_dir, directory.name)
    assert status['status']['error']['code'] == 'infrastructure'
    assert FakeAdapter.calls[-3:] == [('restore',), ('read',), ('close',)]
    summary = status['summary']
    assert summary['restoration']['state'] == 'restored'
    # design 1 already FAILED at ss before the link broke: one confirmed failure rejects, unknowns do not rescue it
    assert [d['disposition'] for d in summary['designs']] == ['rejected', 'inconclusive']
    assert summary['designs'][0]['unknown_corners'] == ['ff_cold_high', 'fs_nominal', 'sf_nominal']
    assert summary['designs'][1]['unknown_corners'] == list(CORNERS) and summary['designs'][1]['pass_rate'] is None
    assert summary['budget']['started'] == 4


def test_a_restoration_that_does_not_read_back_is_reported_loudly(real_check):
    run_dir, directory = real_check
    FakeAdapter.fail_readback = True
    assert cc.execute(directory, allow_real=True) == 'failed'
    restoration = cc.check_status(run_dir, directory.name)['summary']['restoration']
    assert restoration['state'] == 'recovery_required' and restoration['journal'] == '/fake/journal'


def test_an_adapter_exception_still_restores(real_check, monkeypatch):
    run_dir, directory = real_check

    def broken(self, work_root, *, condition=None):
        raise RuntimeError('Active ADE/Maestro window conflicts with OCEAN export')
    monkeypatch.setattr(FakeAdapter, 'generate_netlist', broken)
    assert cc.execute(directory, allow_real=True) == 'failed'
    status = cc.check_status(run_dir, directory.name)
    assert 'Maestro' in status['status']['error']['message'] and status['results'] == []
    assert status['summary']['restoration']['state'] == 'restored'
    assert status['summary']['budget']['started'] == 0


# ------------------------------------------------------------------------------------------------ HTTP + detached worker
def test_api_plan_start_status_and_stop(finished):
    root, layout = finished
    client = TestClient(create_app(extra_output_roots=[str(root)], serve_frontend=False, auto_check_on_start=False))
    run_dir = str(layout.run_dir)
    plan = client.get('/api/runs/corner-check/plan', params=dict(run_dir=run_dir, designs=2)).json()
    assert plan['supported'] and plan['simulations'] == 10
    refused = client.post('/api/runs/corner-check/start', json=dict(run_dir=run_dir, designs=2, expected_designs=['x']))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'plan_changed'
    started = client.post('/api/runs/corner-check/start', json=dict(
        run_dir=run_dir, designs=2, expected_designs=[d['evaluation_id'] for d in plan['designs']], simulations=10)).json()
    assert started['simulations'] == 10 and started['mock'] is True
    deadline, status = time.time() + 120, None
    while time.time() < deadline:
        status = client.get('/api/runs/corner-check/status', params=dict(run_dir=run_dir, check_id=started['check_id'])).json()
        if not status['alive'] and status['status']['state'] not in cc.LIVE:
            break
        time.sleep(0.3)
    assert status['status']['state'] == 'completed', status
    assert len(status['results']) == 10 and sum(status['summary']['verdicts'].values()) == 2
    listed = client.get('/api/runs/corner-check/plan', params=dict(run_dir=run_dir)).json()['checks']
    assert listed[0]['check_id'] == started['check_id'] and listed[0]['state'] == 'completed'
    stop = client.post('/api/runs/corner-check/stop', json=dict(run_dir=run_dir, check_id=started['check_id']))
    assert stop.status_code == 409 and stop.json()['detail']['code'] == 'not_running'
    assert client.get('/api/runs/corner-check/status', params=dict(run_dir=run_dir, check_id='x')).status_code == 400
    missing = client.get('/api/runs/corner-check/status', params=dict(run_dir=run_dir, check_id='20200101T000000Z-00000000'))
    assert missing.status_code == 404
    assert client.post('/api/runs/corner-check/stop', json=dict(run_dir=run_dir, check_id='../x')).status_code == 422
