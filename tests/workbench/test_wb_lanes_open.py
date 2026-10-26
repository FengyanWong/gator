"""A run's lanes open side by side (record 7.137): a real lane builds its environment in a process of its own, about 2 s,
and one after another a 4-lane run waited 8.7 s before its first evaluation (record 7.136). Fake environments; no
simulator."""
import threading
import time
from types import SimpleNamespace

import pytest

from gator_workbench.lanes import open_lanes

EVENTS = []


class SlowEnv:
    """Takes `delay` seconds to build, as a real lane's environment does, and remembers when."""
    def __init__(self, lane, delay=0.5, fail=False):
        """Record delayed lane construction and optionally fail before the environment opens."""
        start = time.monotonic()
        time.sleep(delay)
        EVENTS.append(('built', lane, start, time.monotonic()))
        if fail:
            raise RuntimeError(f'lane {lane} cannot open')
        self.lane, self.directory, self.expected_origin = lane, f'/fixture/worker-{lane}', 'synthetic'
        self.mapper, self.max_steps, self.planned_conditions = SimpleNamespace(group_ids=['g']), 4, [None]
        self.config_sha256, self.simulation_calls = 'fixture', 0

    def __enter__(self):
        return self

    def close(self):
        EVENTS.append(('closed', self.lane, None, None))


def test_lanes_open_side_by_side_and_come_back_in_index_order():
    EVENTS.clear()
    lanes = open_lanes(lambda lane: SlowEnv(lane), 4, use_processes=False)
    try:
        assert [lane.lane_id for lane in lanes] == ['0', '1', '2', '3']
        assert [lane.info['directory'] for lane in lanes] == [f'/fixture/worker-{i}' for i in range(4)]
        built = [event for event in EVENTS if event[0] == 'built']
        assert max(start for *_, start, _ in built) < min(end for *_, end in built)      # every one began before any ended
    finally:
        for lane in lanes:
            lane.close()


def test_a_lane_that_cannot_open_closes_the_others_and_its_failure_is_raised():
    EVENTS.clear()
    with pytest.raises(RuntimeError, match='lane 2 cannot open'):
        open_lanes(lambda lane: SlowEnv(lane, fail=lane in ('2', '3')), 4, use_processes=False)
    assert sorted(lane for kind, lane, *_ in EVENTS if kind == 'closed') == ['0', '1']    # the two that opened, closed
    assert not [t for t in threading.enumerate() if t.name.startswith('gator-lane-open')]


def test_one_lane_and_no_lanes():
    EVENTS.clear()
    lanes = open_lanes(lambda lane: SlowEnv(lane, delay=0), 1, use_processes=False)
    assert [lane.lane_id for lane in lanes] == ['0']
    lanes[0].close()
    assert open_lanes(lambda lane: SlowEnv(lane), 0, use_processes=False) == []


def test_worker_process_lanes_open_side_by_side_in_a_run(tmp_path):
    """The path a real run takes: each lane a spawned worker process (here around the scripted test backend)."""
    from helpers import execute, make_config, rows
    config = make_config(tmp_path, run=dict(max_evaluations=6, concurrency=2))
    layout, state = execute(config, tmp_path, delays={'0': 0.05, '1': 0.05}, use_processes=True)
    assert state == 'completed'
    assert {row['worker_id'] for row in rows(layout, 'evaluations')} == {'0', '1'}


def test_a_real_task_may_run_as_many_lanes_as_the_optimizer_allows():
    """Record 7.143: the task limit is the optimizer's own MAX_SPECTRE_WORKERS (4 until then)."""
    from analog_optimizer.backends.native_preparation import MAX_SPECTRE_WORKERS
    from gator_workbench.tasks import REAL_LANES
    assert REAL_LANES == MAX_SPECTRE_WORKERS == 6
