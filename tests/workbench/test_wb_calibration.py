"""Calibration with the baseline run (record 7.197): a "Baseline simulation" asked for it goes on with random
designs, and proposes a Scale per Specs row and the Initial alpha from them. MOCK backend only; nothing is applied by a run."""
import json
import statistics
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import baseline_reference, calibration, profiles, runs
from gator_workbench.storage import read_json
from gator_workbench.storage.atomic import write_json
from helpers import make_config, roots_for, rows, run_prepared, summary, workbench_app
from helpers import probe, wait_for

COMPRESSED = dict(violation_shape='compressed', worst_spec_share=0.5)


def four_rows(root, **reward):
    """Four Specs rows in four units, one of them the objective. The calibration's arithmetic needs no simulator."""
    def mutate(raw):
        raw['targets'] = [dict(metric_id='gain_db', equation='m_score', unit='dB', constraint='>=', lower=52.0),
                          dict(metric_id='ugf_hz', equation='m_score', unit='MHz', constraint='>=', lower=100.0),
                          dict(metric_id='power_w', equation='m_score', unit='uW', constraint='<=', upper=150.0, direction_after_feasible='minimize'),
                          dict(metric_id='vout_v', equation='m_score', unit='V', constraint='interval', lower=0.7, upper=1.2)]
        raw['run']['reward'] = dict(COMPRESSED, **reward)
    return make_config(root, mutate=mutate)


def one_row(root, *, scale=None, **reward):
    def mutate(raw):
        raw['targets'][0]['normalization_scale'] = scale
        raw['run']['reward'] = dict(COMPRESSED, **reward)
    return make_config(root, mutate=mutate)


def recorded(config, table, *, rewards=None):
    """The rows a run would have recorded for random designs measuring `table` ({Specs ID: canonical values, None = no
    value}), with the reward the reward code gives each design (or `rewards`)."""
    count = len(next(iter(table.values())))
    evaluations = [dict(evaluation_id=f'e{i}', dispatch_index=i + 2, action_source=calibration.RANDOM_SOURCE, status='ok', reward=None,
                        all_hard_constraints_satisfied=False) for i in range(count)]
    metric_rows = [dict(evaluation_id=f'e{i}', metric_name=name, raw_value=values[i], valid=values[i] is not None)
                   for name, values in table.items() for i in range(count)]
    measured = {f'e{i}': {name: values[i] for name, values in table.items() if values[i] is not None} for i in range(count)}
    for evaluation, reward in zip(evaluations, rewards or calibration._rewards(config, evaluations, measured)):
        evaluation['reward'] = reward
    baseline = dict(evaluation_id='b', dispatch_index=1, action_source='reset', status='ok', reward=None, all_hard_constraints_satisfied=False)
    return [baseline, *evaluations], metric_rows


# ------------------------------------------------------------------------------- the arithmetic
def test_a_scale_is_the_median_miss_of_the_designs_that_miss_the_row_in_the_rows_own_unit(tmp_path):
    config = four_rows(tmp_path)
    evaluations, metric_rows = recorded(config, dict(
        gain_db=[40.0] * 8 + [46.0] * 8 + [50.0] * 4 + [60.0] * 12,             # misses 12, 6, 2 dB: the median of 20 is 6
        ugf_hz=[30e6] * 16 + [150e6] * 16,                                       # 70 MHz short, in the canonical Hz
        power_w=[200e-6] * 16 + [100e-6] * 16,                                   # the objective row
        vout_v=[1.25] * 4 + [0.9] * 28))                                         # 4 of 32 miss it
    result = calibration.calibrate(config, evaluations, metric_rows)
    by_id = {row['metric_id']: row for row in result['rows']}
    assert result['status'] == 'calibrated' and result['designs'] == dict(simulated=32, scored=32, passing=0)
    assert by_id['gain_db']['proposed_scale'] == 6.0 and by_id['gain_db']['misses'] == 20 and by_id['gain_db']['measured'] == 32
    assert by_id['gain_db']['scale_used'] == 52.0 and by_id['gain_db']['scale_stated'] is None       # the empty box = the size of the limit
    assert by_id['ugf_hz']['proposed_scale'] == 70.0 and by_id['ugf_hz']['unit'] == 'MHz' and by_id['ugf_hz']['median_miss'] == pytest.approx(70.0)
    # the objective row: its Scale also measures the objective bonus, so nothing is proposed although half the designs miss it
    assert by_id['power_w']['proposed_scale'] is None and 'objective' in by_id['power_w']['note'] and by_id['power_w']['median_miss'] == pytest.approx(50.0)
    # a window few designs miss (28 of 32 are inside it), its Scale wider than half of it: half the window (record 7.217)
    assert by_id['vout_v']['proposed_scale'] == 0.25 and by_id['vout_v']['limited'] == 'window' and by_id['vout_v']['half_window'] == 0.25
    assert by_id['vout_v']['note'].startswith('4 of 32 random designs miss this row') and 'Half the window is proposed' in by_id['vout_v']['note']
    assert by_id['vout_v']['median_miss'] == pytest.approx(0.05) and by_id['gain_db']['half_window'] is None
    assert calibration.sentence(result).startswith('Calibration from 32 scored random designs (32 simulated): a Scale proposed for 3 of 4 Specs rows, ')
    assert result['rule']['version'] == calibration.RULE == 3


def test_the_initial_alpha_is_a_tenth_of_the_reward_spread_under_the_proposed_scales(tmp_path):
    """One row, compressed shape, share 0.5, no bonus: the reward of a design is -d / (1 + d) with d = miss / Scale."""
    config = one_row(tmp_path, scale=1.0)
    evaluations, metric_rows = recorded(config, dict(score=[0.85] * 8 + [0.65] * 8 + [1.0] * 8))      # misses 0.1 and 0.3, 8 pass
    result = calibration.calibrate(config, evaluations, metric_rows)
    row, alpha = result['rows'][0], result['initial_alpha']
    assert row['proposed_scale'] == 0.2 and row['scale_stated'] == 1.0 and result['reward_check'] == dict(designs=24, reproduced=24)
    with_proposal = [-0.5 / 1.5] * 8 + [-1.5 / 2.5] * 8 + [0.0] * 8                 # d = 0.5 and 1.5 with the Scale 0.2
    assert alpha['reward_sd'] == pytest.approx(statistics.stdev(with_proposal), rel=1e-6)
    assert alpha['proposed'] == 0.025 and alpha['used'] == config.run.advanced.initial_alpha
    as_run = [-0.1 / 1.1] * 8 + [-0.3 / 1.3] * 8 + [0.0] * 8                         # ... and with the Scale 1 the run had
    assert alpha['reward_sd_used'] == pytest.approx(statistics.stdev(as_run), rel=1e-6)


def window_rows(root, *, scale=None, objective='none'):
    """The output window of an LDO, 1.18 to 1.22 V (half its width: 0.02 V), beside a gain row and the objective."""
    def mutate(raw):
        raw['targets'] = [dict(metric_id='vout_v', equation='m_score', unit='V', constraint='interval', lower=1.18, upper=1.22,
                               normalization_scale=scale, direction_after_feasible=objective),
                          dict(metric_id='gain_db', equation='m_score', unit='dB', constraint='>=', lower=52.0),
                          dict(metric_id='power_w', equation='m_score', unit='uW', constraint='<=', upper=150.0,
                               direction_after_feasible='none' if objective != 'none' else 'minimize')]
        raw['run']['reward'] = dict(COMPRESSED)
    return make_config(root, mutate=mutate)


def test_a_window_most_designs_are_inside_gets_at_most_half_its_width(tmp_path):
    """Record 7.217. A design inside a window has at most half its width of room, and the margin bonus follows the row with
    the least room measured in its Scale: a wider Scale on a window holds the margin bonus of the whole task small. A
    window most random designs MISS keeps the typical miss - it has to be found first."""
    others = dict(gain_db=[40.0] * 16 + [60.0] * 16, power_w=[100e-6] * 32)
    def vout(config, values):
        rows_ = calibration.calibrate(config, *recorded(config, dict(vout_v=values, **others)))['rows']
        return next(row for row in rows_ if row['metric_id'] == 'vout_v')
    empty = window_rows(tmp_path)                                                       # empty box = 1.22, the upper limit
    # half of the designs are inside, the others miss by 0.3 V - far more than half the window: half the window, an exact number
    far = vout(empty, [1.52] * 16 + [1.2] * 16)
    assert far['proposed_scale'] == 0.02 and far['limited'] == 'window' and far['median_miss'] == pytest.approx(0.3)
    assert far['note'].startswith('The typical miss is 300 mV, more than half the window, and 16 of 32 random designs are inside it.')
    assert far['half_window'] == 0.02 and far['scale_used'] == 1.22
    # most designs MISS the window: its Scale is their typical miss, and the note says what that costs the margin bonus
    hard = vout(empty, [1.52] * 24 + [1.2] * 8)
    assert hard['proposed_scale'] == 0.3 and hard['limited'] is None
    assert hard['note'].startswith('24 of 32 random designs miss this window, so its Scale is their typical miss: the search has to find the window first.')
    assert 'wider than half the window (20 mV)' in hard['note'] and 'at most 0.067 of a Scale clear' in hard['note']
    # a typical miss inside half the window is the proposal, as on any row
    near = vout(empty, [1.235] * 16 + [1.2] * 16)
    assert near['proposed_scale'] == 0.015 and near['limited'] is None and near['note'] is None
    # few designs miss it and the Scale is wider than half the window: half the window, said with what the Scale in use does
    few = vout(empty, [1.52] * 2 + [1.2] * 30)
    assert few['proposed_scale'] == 0.02 and few['limited'] == 'window' and few['misses'] == 2
    assert few['note'].startswith('2 of 32 random designs miss this row: too few to name a typical miss. Half the window is proposed: with the Scale in use (1.22 V)')
    assert 'counts as 0.016 of a Scale away from its limits' in few['note']
    # ... but a Scale already inside half the window stays, and so does the row that carries the objective
    typed = vout(window_rows(tmp_path, scale=0.01), [1.52] * 2 + [1.2] * 30)
    assert typed['proposed_scale'] is None and typed['note'].endswith('Its Scale stays as it is.') and typed['scale_stated'] == 0.01
    objective = vout(window_rows(tmp_path, objective='minimize'), [1.52] * 16 + [1.2] * 16)
    assert objective['proposed_scale'] is None and 'objective' in objective['note']
    # a row with one limit that few designs miss keeps its Scale, as before
    config = window_rows(tmp_path)
    rows_ = calibration.calibrate(config, *recorded(config, dict(vout_v=[1.52] * 16 + [1.2] * 16, gain_db=[40.0] * 2 + [60.0] * 30, power_w=[100e-6] * 32)))['rows']
    gain = next(row for row in rows_ if row['metric_id'] == 'gain_db')
    assert gain['proposed_scale'] is None and gain['note'] == '2 of 32 random designs miss this row: too few to name a typical miss. Its Scale stays as it is.'


def test_the_initial_alpha_is_proposed_only_when_it_differs_by_a_factor_of_two(tmp_path):
    """Record 7.217. The estimate here is 0.025 (the test above): a value in use within a factor of 2 of it stays."""
    table = dict(score=[0.85] * 8 + [0.65] * 8 + [1.0] * 8)
    def alpha(in_use, **reward):
        config = one_row(tmp_path, scale=1.0, **reward)
        config.run.advanced.initial_alpha = in_use
        return calibration.calibrate(config, *recorded(config, table))
    for close in (0.02, 0.04, 0.013):
        result = alpha(close)
        assert result['initial_alpha']['proposed'] is None and result['initial_alpha']['estimate'] == 0.025, close
        assert result['initial_alpha']['note'] == f'Not proposed: the estimate is 0.025 (0.1 x the reward spread), within a factor of 2 of the {close:g} in use. The value in use stays.'
        assert result['status'] == 'calibrated' and result['rows'][0]['proposed_scale'] == 0.2       # the Scale is still proposed
        assert calibration.sentence(result).endswith('a Scale proposed for 1 of 1 Specs rows, no Initial alpha. Nothing is applied by the run.')
    for far in (0.0125, 0.05, 0.2, 0.001):                                              # a factor of 2 or more, either way
        result = alpha(far)
        assert result['initial_alpha']['proposed'] == result['initial_alpha']['estimate'] == 0.025 and result['initial_alpha']['note'] is None, far
    # nothing to change at all: no Scale (the capped shape proposes none) and a close Initial alpha
    estimate = alpha(0.2, violation_shape='capped')['initial_alpha']['estimate']
    nothing = alpha(estimate * 1.5, violation_shape='capped')
    assert nothing['status'] == 'not_calibrated' and nothing['initial_alpha']['proposed'] is None
    assert nothing['reason'].startswith('The random designs give nothing to change: no Scale is proposed for a Specs row, and the Initial alpha in use')
    assert calibration.sentence(nothing).startswith('Calibration: nothing proposed. The random designs give nothing to change')


def test_a_proposal_stays_within_a_hundredth_and_ten_times_the_size_of_the_limit(tmp_path):
    config = one_row(tmp_path)                                                         # empty box = 0.95, the size of the limit
    far = calibration.calibrate(config, *recorded(config, dict(score=[-19.05] * 16 + [1.0] * 8)))['rows'][0]      # misses of 20
    assert far['proposed_scale'] == 9.5 and far['limited'] == 'high' and far['median_miss'] == pytest.approx(20.0) and 'kept within' in far['note']
    near = calibration.calibrate(config, *recorded(config, dict(score=[0.949] * 16 + [1.0] * 8)))['rows'][0]      # misses of 0.001
    assert near['proposed_scale'] == 0.0095 and near['limited'] == 'low'


def test_what_cannot_be_named_is_not_proposed(tmp_path):
    # the capped shape: a typical miss at 1 would sit on the cap, so no Scale - the Initial alpha still follows the reward spread
    capped = one_row(tmp_path, violation_shape='capped')
    result = calibration.calibrate(capped, *recorded(capped, dict(score=[0.85] * 8 + [0.65] * 8 + [1.0] * 8)))
    assert result['rows'][0]['proposed_scale'] is None and result['rows'][0]['median_miss'] == pytest.approx(0.2)
    assert 'capped' in result['scale_note'] and result['status'] == 'calibrated' and result['initial_alpha']['proposed'] is not None
    assert result['initial_alpha']['reward_sd'] == pytest.approx(result['initial_alpha']['reward_sd_used'])
    # fewer than 16 scored designs: nothing at all
    config = one_row(tmp_path)
    few = calibration.calibrate(config, *recorded(config, dict(score=[0.85] * 15)))
    assert few['status'] == 'not_calibrated' and few['rows'] == [] and few['reason'].startswith('15 of the 15 random designs gave a reward; at least 16')
    # every design the same reward: no spread to follow
    flat = calibration.calibrate(config, *recorded(config, dict(score=[0.85] * 20)))
    assert flat['rows'][0]['proposed_scale'] == 0.1 and flat['initial_alpha']['proposed'] is None and 'does not differ' in flat['initial_alpha']['note']
    # recorded rewards the reward code cannot give again: the scales are proposed, the Initial alpha is not
    table = dict(score=[0.85] * 8 + [0.65] * 8 + [1.0] * 8)
    odd = calibration.calibrate(config, *recorded(config, table, rewards=[-0.5] * 24))
    assert odd['rows'][0]['proposed_scale'] == 0.2 and odd['initial_alpha']['proposed'] is None
    assert odd['reward_check']['reproduced'] < 24 and 'could not be worked out again' in odd['initial_alpha']['note']
    # designs that measured nothing are counted, not guessed
    holes = calibration.calibrate(config, *recorded(config, dict(score=[0.85] * 10 + [0.65] * 10 + [None] * 6)))
    assert holes['designs'] == dict(simulated=26, scored=20, passing=0) and holes['rows'][0]['measured'] == 20


def test_the_baseline_run_is_prepared_for_random_designs_only(tmp_path):
    config = make_config(tmp_path, run=dict(concurrency=3, stop_at_first_feasible=True, max_consecutive_failures=5))
    request = calibration.prepare(config, 64)
    run, adv = config.run, config.run.advanced
    assert request == dict(designs=64, lanes=3, evaluations=67) and run.max_evaluations == 67
    assert (adv.warmup_transitions, adv.episode_length, adv.update_every, adv.episode_terminates_on_success) == (64, 64, 65, False)
    assert run.stop_at_first_feasible is False and run.max_consecutive_failures == 67


# ------------------------------------------------------------------------------- the run
def calibration_run(root, designs, *, lanes=1, scripts=None, delays=None, reward=COMPRESSED):
    config = make_config(root, run=dict(concurrency=lanes, reward=reward)).model_copy(deep=True)
    config.run.max_evaluations, config.output.save_checkpoints = 1, False
    request = calibration.prepare(config, designs)
    layout, manifest = runs.prepare_run(config, roots_for(root))
    manifest.update(run_kind='baseline_preflight', calibration=request)
    write_json(layout.manifest, manifest)
    return layout, run_prepared(layout, scripts=scripts, delays=delays)


def test_a_baseline_run_asked_to_calibrate_simulates_random_designs_and_writes_its_proposals(tmp_path):
    layout, state = calibration_run(tmp_path, 24)
    evaluations = rows(layout, 'evaluations', ['phase', 'action_source', 'dispatch_index', 'reward'])
    assert state == 'completed' and summary(layout)['stop_reason'] == 'budget_exhausted'
    assert [(e['phase'], e['action_source']) for e in sorted(evaluations, key=lambda e: e['dispatch_index'])] == [('baseline', 'reset')] + [('warmup', 'random_warmup')] * 24
    assert read_json(layout.status)['learner_updates'] == 0 and rows(layout, 'learner_updates') == []      # nothing is learned from them
    result = read_json(layout.run_dir / calibration.FILE)
    assert result['status'] == 'calibrated' and result['designs'] == dict(simulated=24, scored=24, passing=result['designs']['passing'], requested=24)
    assert result['reward_check'] == dict(designs=24, reproduced=24)            # the reward code gives the recorded rewards again
    assert result['rows'][0]['metric_id'] == 'score' and result['task_key'] == 'synthetic:gpdk045_ota5' and result['run_state'] == 'completed'
    manifest = read_json(layout.manifest)
    assert any(note.startswith('Calibration from 24 scored random designs') for note in manifest['notes'])
    events = [json.loads(line) for line in (layout.logs / 'events.jsonl').read_text().splitlines()]
    assert [e['status'] for e in events if e['event'] == 'calibration'] == ['calibrated']
    assert calibration.FILE in {f['path'] for f in read_json(layout.artifact_manifest)['files']}


def test_a_result_written_under_an_older_rule_is_worked_out_again_when_read(tmp_path):
    """Record 7.217: the random designs of a finished Baseline simulation are simulated and paid for; when the rule changes,
    its proposals are worked out again from the run's tables for the page - the run's own file stays as the run wrote it."""
    layout, _ = calibration_run(tmp_path, 24)
    file, manifest = layout.run_dir / calibration.FILE, read_json(layout.manifest)
    written = read_json(file)
    assert written['rule']['version'] == calibration.RULE and calibration.current(layout.run_dir, manifest) == written     # today's rule: the file
    old = json.loads(json.dumps(written))
    del old['rule']['version']                                                        # as a run of record 7.197 wrote it
    old['initial_alpha'].update(proposed=0.0123, note='from the older rule')
    file.write_text(json.dumps(old))
    calibration._AGAIN.clear()
    again = calibration.current(layout.run_dir, manifest)
    assert again['recalculated'] == dict(from_rule=1, to_rule=calibration.RULE) and again['rule']['version'] == calibration.RULE
    assert again['initial_alpha'] == written['initial_alpha'] and again['rows'] == written['rows'] and again['designs'] == written['designs']
    assert again['created_utc'] == old['created_utc'] and read_json(file) == old       # nothing is written into the run's folder
    assert calibration.current(layout.run_dir, manifest) is again                      # worked out once per backend process
    # ... and so is one of the unreleased rule 2 (six Baseline simulations of 2026-10-05 were recorded under it)
    file.write_text(json.dumps(dict(old, rule=dict(written['rule'], version=2))))
    calibration._AGAIN.clear()
    assert calibration.current(layout.run_dir, manifest)['recalculated'] == dict(from_rule=2, to_rule=calibration.RULE)
    file.write_text(json.dumps(old))
    # tables that cannot be read: what the run said stands
    calibration._AGAIN.clear()
    assert calibration.current(tmp_path / 'no-such-run', manifest) is None
    (tmp_path / 'bare').mkdir()
    (tmp_path / 'bare' / calibration.FILE).write_text(json.dumps(old))
    assert calibration.current(tmp_path / 'bare', manifest) == old


def test_no_lane_starts_before_the_baseline_is_in_and_the_rest_follows_a_valid_one(tmp_path):
    layout, state = calibration_run(tmp_path, 18, lanes=3, delays={'0': 0.05})
    evaluations = sorted(rows(layout, 'evaluations', ['phase', 'action_source', 'dispatch_index', 'started_at', 'completed_at']), key=lambda e: e['dispatch_index'])
    assert state == 'completed' and len(evaluations) == 3 + 18
    assert evaluations[0]['phase'] == 'baseline' and all(e['started_at'] >= evaluations[0]['completed_at'] for e in evaluations[1:])
    phases = [e['phase'] for e in evaluations]
    assert phases.count('baseline') == 1 and phases.count('episode_reset') == 2 and phases.count('warmup') == 18


def test_an_invalid_baseline_ends_the_run_before_any_random_design(tmp_path):
    layout, state = calibration_run(tmp_path, 24, lanes=2, scripts={'0': {1: 'invalid_design'}})
    evaluations = rows(layout, 'evaluations', ['phase', 'valid'])
    assert state == 'completed' and summary(layout)['stop_reason'] == 'baseline_invalid'
    assert [(e['phase'], e['valid']) for e in evaluations] == [('baseline', False)]                 # one evaluation, as without the calibration
    result = read_json(layout.run_dir / calibration.FILE)
    assert result['status'] == 'not_calibrated' and result['designs']['simulated'] == 0
    assert result['reason'] == 'The starting design gave no valid result, so no random design was simulated.'


def test_a_stopped_calibration_run_can_still_give_the_reference(tmp_path, monkeypatch):
    """Stopped by the user among the random designs, the baseline evaluation is as finished as that of a run of one."""
    entry = dict(directory=str(tmp_path), saved_utc=None)
    monkeypatch.setattr(profiles, 'list_profiles', lambda: dict(demo=entry))
    monkeypatch.setattr(baseline_reference, 'profile_entry', lambda name: dict(demo=entry).get(name))        # one task's entry (7.279)
    monkeypatch.setattr(baseline_reference, 'reference_metrics', lambda name: None)
    monkeypatch.setattr(baseline_reference, '_run_outlived_the_task', lambda entry, manifest: None)
    asked = []
    monkeypatch.setattr(baseline_reference, 'record_reference', lambda name, run_dir: asked.append(name) or dict(metrics={}))
    manifest = dict(run_kind='baseline_preflight', mock=False, circuit=dict(task_key='real:demo'), state='stopped', run_id='r1')
    refused = profiles.adopt_baseline_run(tmp_path, manifest=manifest)
    assert refused['recorded'] is False and 'ended as stopped' in refused['note'] and not asked        # a plain baseline run: as before
    assert profiles.adopt_baseline_run(tmp_path, manifest=dict(manifest, calibration=dict(designs=64)))['recorded'] is True and asked == ['demo']
    failed = profiles.adopt_baseline_run(tmp_path, manifest=dict(manifest, calibration=dict(designs=64), state='failed'))
    assert failed['recorded'] is False and 'ended as failed' in failed['note']


# ------------------------------------------------------------------------------- the routes
@pytest.fixture
def client(tmp_path):
    return TestClient(workbench_app(tmp_path, monitor=probe(tmp_path), auto_check_on_start=True))


def test_the_start_route_takes_the_calibration_with_the_baseline_only(client, tmp_path):
    raw = make_config(tmp_path, run=dict(reward=COMPRESSED)).model_dump(mode='json')
    started = client.post('/api/runs/start', json=dict(config=raw, baseline_only=True, calibration_designs=20)).json()
    status = wait_for(client, started['run_dir'])
    assert status['state'] == 'completed' and status['summary']['totals']['candidate_evaluations_charged'] == 21
    assert status['calibration']['request'] == dict(designs=20, lanes=1, evaluations=21)
    assert status['calibration']['result']['status'] == 'calibrated' and status['calibration']['result']['designs']['simulated'] == 20
    manifest = json.loads((Path(started['run_dir']) / 'run_manifest.json').read_text())
    assert manifest['run_kind'] == 'baseline_preflight' and any(note.startswith('With calibration: after the baseline, 20 random designs') for note in manifest['notes'])
    # without it: the run of one evaluation it always was, and no calibration in its status
    plain = client.post('/api/runs/start', json=dict(config=raw, baseline_only=True)).json()
    status = wait_for(client, plain['run_dir'])
    assert status['summary']['totals']['candidate_evaluations_charged'] == 1 and status['calibration'] is None
    assert not (Path(plain['run_dir']) / calibration.FILE).exists()
    # not with an optimization run, and not above the limit
    refused = client.post('/api/runs/start', json=dict(config=raw, calibration_designs=20))
    assert refused.status_code == 400 and 'Baseline simulation' in refused.json()['detail']['message']
    assert client.post('/api/runs/start', json=dict(config=raw, baseline_only=True, calibration_designs=501)).status_code == 422


@pytest.mark.parametrize('lanes', [1, 3])
def test_calibration_only_counts_only_random_designs_even_after_invalid_results(tmp_path, lanes):
    config = make_config(tmp_path, run=dict(concurrency=lanes, reward=COMPRESSED))
    request = calibration.prepare(config, 24, random_only=True)
    config.output.save_checkpoints = False
    layout, manifest = runs.prepare_run(config, roots_for(tmp_path))
    manifest.update(run_kind='calibration', calibration=request)
    write_json(layout.manifest, manifest)
    assert run_prepared(layout, scripts={'0': {1: 'invalid_design'}}) == 'completed'
    evaluations = rows(layout, 'evaluations', ['phase', 'action_source', 'valid', 'reward'])
    assert len(evaluations) == 24 and any(not e['valid'] for e in evaluations)
    assert {(e['phase'], e['action_source']) for e in evaluations} == {('warmup', 'random_warmup')}
    assert all(e['reward'] is not None for e in evaluations if e['valid'])
    assert read_json(layout.status)['learner_updates'] == 0
    assert rows(layout, 'transitions') == [] and rows(layout, 'learner_updates') == []
    assert read_json(layout.run_dir / calibration.FILE)['designs']['simulated'] == 24


def test_calibration_route_has_no_baseline_and_does_not_load_the_selected_model(client, tmp_path):
    raw = make_config(tmp_path, run=dict(reward=COMPRESSED)).model_dump(mode='json')
    raw['run'].update(mode='fine_tune', model_source=dict(run_dir='/no/such/model'))
    started = client.post('/api/runs/start', json=dict(config=raw, calibration_only=True, calibration_designs=20))
    assert started.status_code == 200, started.text
    directory = started.json()['run_dir']
    status = wait_for(client, directory)
    assert status['state'] == 'completed', status
    assert status['summary']['totals']['candidate_evaluations_charged'] == 20
    assert status['calibration']['request'] == dict(designs=20, lanes=1, evaluations=20, random_only=True)
    assert status['calibration']['result']['reward_check']['reproduced'] == 20
    assert read_json(Path(directory) / 'run_manifest.json')['run_kind'] == 'calibration'
    assert client.post('/api/runs/start', json=dict(config=raw, calibration_only=True)).status_code == 400
    assert client.post('/api/runs/start', json=dict(config=raw, calibration_only=True, baseline_only=True,
                                                  calibration_designs=20)).status_code == 400
