"""Records 7.280 and 7.281, on the toy backend's MOCK runs.

7.280 changes no result: a save point every 200 evaluations and the data tables written every 64 by default, the scheduler
woken by a lane's result instead of looking every 50 ms, and what each evaluation's stages took kept in logs/timings.jsonl.
7.281 is a switch, off by default: a lane gets its next design before the learner updates of the result it brought. The
number of updates and what every save point holds stay those of a run without it; only which policy proposed a design
changes."""
from concurrent.futures import Future
import json
import threading
import time
from types import SimpleNamespace

from gator_workbench import schema
from gator_workbench.engine import RunEngine
from gator_workbench.storage import read_json
from helpers import execute, make_config, rows


# ---- 7.280 ---------------------------------------------------------------------------------------------------------------
def test_the_new_output_defaults():
    output = schema.OutputSettings()
    assert output.checkpoint_every_evaluations == 200 and output.flush_every_evaluations == 64


def test_the_scheduler_is_woken_by_a_lane_result():
    future = Future()
    engine = SimpleNamespace(lane_state=dict(a=dict(busy=dict(handle=SimpleNamespace(_future=future)))))
    lane = SimpleNamespace(lane_id='a')
    started = time.monotonic()
    RunEngine._wait_for_a_lane(engine, [lane], 0.05)                       # nothing finished: the whole wait
    assert time.monotonic() - started >= 0.04
    threading.Timer(0.02, lambda: future.set_result('done')).start()
    started = time.monotonic()
    RunEngine._wait_for_a_lane(engine, [lane], 5.0)                        # woken by the result, not after 5 s
    assert time.monotonic() - started < 2.0
    odd = SimpleNamespace(lane_state=dict(a=dict(busy=dict(handle=object()))))
    started = time.monotonic()
    RunEngine._wait_for_a_lane(odd, [lane], 0.05)                          # a handle without a future: a plain sleep
    assert time.monotonic() - started >= 0.04


def evaluation_values(layout):
    keep = ('evaluation_id', 'reward', 'valid', 'all_hard_constraints_satisfied', 'normalized_constraint_violation', 'phase',
            'action_source', 'policy_version')
    ordered = sorted(rows(layout, 'evaluations'), key=lambda row: row['commit_seq'])
    return [tuple(row[k] for k in keep[1:]) for row in ordered]


def test_the_timings_of_each_evaluation_are_kept_and_the_table_writes_change_no_result(tmp_path):
    small, large = tmp_path / 'small', tmp_path / 'large'
    layout_small, state_small = execute(make_config(small, run=dict(max_evaluations=24), output=dict(flush_every_evaluations=4)), small)
    layout_large, state_large = execute(make_config(large, run=dict(max_evaluations=24), output=dict(flush_every_evaluations=64)), large)
    assert state_small == state_large == 'completed'
    assert evaluation_values(layout_small) == evaluation_values(layout_large)              # the same run, other part sizes
    lines = [json.loads(line) for line in (layout_large.logs / 'timings.jsonl').read_text().splitlines()]
    evaluations = {row['evaluation_id'] for row in rows(layout_large, 'evaluations')}
    assert lines and {line['evaluation_id'] for line in lines} <= evaluations
    assert all(isinstance(line['seconds'], dict) and line['seconds'] and line['worker_id'] for line in lines)


# ---- 7.281 ---------------------------------------------------------------------------------------------------------------
def learner_facts(layout):
    """The cumulative update count of every learner_updates row, and of every save point {evaluations: updates} - after
    checking that each save point holds every update the results it covers triggered (the rows say which: evaluations_collected)."""
    updates = sorted(rows(layout, 'learner_updates'), key=lambda row: row['cumulative_updates'])
    points = {}
    for folder in (layout.run_dir / 'checkpoints').iterdir():
        meta = read_json(folder / 'metadata.json', default=None) if folder.is_dir() else None
        if meta:
            covered, learned = meta['counters']['evaluations_committed'], meta['counters']['learner_updates']
            assert learned == sum(1 for row in updates if row['evaluations_collected'] <= covered), (covered, learned)
            points[covered] = learned
    return [row['cumulative_updates'] for row in updates], points


def test_learning_after_the_dispatch_keeps_every_update_and_every_save_point(tmp_path):
    def run(folder, switch, concurrency):
        config = make_config(folder, run=dict(max_evaluations=30, concurrency=concurrency),
                             advanced=dict(updates_per_transition=3, update_after_dispatch=switch),
                             output=dict(checkpoint_every_evaluations=10))
        return execute(config, folder)
    for concurrency in (1, 2):
        off, state_off = run(tmp_path / f'off{concurrency}', False, concurrency)
        on, state_on = run(tmp_path / f'on{concurrency}', True, concurrency)
        assert state_off == state_on == 'completed'
        counts_off, points_off = learner_facts(off)
        counts_on, points_on = learner_facts(on)
        assert counts_on == counts_off and counts_on                       # every update made, and its row recorded
        if concurrency == 1:                                               # one lane: the same results arrive at the same time
            assert points_on == points_off and points_on
        events = [json.loads(line)['event'] for line in (on.logs / 'events.jsonl').read_text().splitlines()]
        assert 'learner_update_rows_unrecorded' not in events
        assert read_json(on.manifest)['architecture']['sac']['update_after_dispatch'] is True


def test_the_switch_keeps_the_hashes_of_configurations_without_it(tmp_path):
    config = make_config(tmp_path)
    raw = config.model_dump(mode='json')
    del raw['run']['advanced']['update_after_dispatch']
    assert schema.config_hash(config) == schema.config_hash(raw)                          # off: hashed as absent
    switched = make_config(tmp_path, advanced=dict(update_after_dispatch=True))
    assert schema.config_hash(switched) != schema.config_hash(config)
    assert schema.task_definition_hash(switched) == schema.task_definition_hash(config)   # never a different task
