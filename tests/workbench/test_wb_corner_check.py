"""Corner check (status record 7.62): a finished run's best designs simulated again at the five fixed corners.

MOCK runs go through the whole path, the detached worker included. The REAL path runs against a fake adapter that
records every call: no Virtuoso, no Spectre, no budget."""
import json
import math
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from analog_optimizer.backends.backend import SimulationStatus

from gator_workbench import corner_check as cc
from gator_workbench.api import create_app
from gator_workbench.engine import RunLock
from gator_workbench.storage.atomic import read_json, write_json
from helpers import execute, make_config

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.
pytestmark = pytest.mark.xdist_group('test_wb_corner_check')

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


def test_no_registered_task_can_be_checked_at_corners_now():
    """Only built-in profiles accepted the corners, and the last of them, the OTA7, was removed on 2026-09-30 (record
    7.128), with the tests of the real check that used it."""
    assert cc.checkable_real_tasks() == ()
    assert cc._unsupported('real:x', 'nominal only').endswith('Circuits that can: none.')


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
