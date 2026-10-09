"""Optimizer fixes of review round 5 (2026-09-30, one digest step): the top grid point stays inside its bounds, a corner
summary survives a "Missing value = failed" spec, and three copies / one fsync that cost time but changed nothing."""
from concurrent.futures import Future, TimeoutError
from dataclasses import replace
import io
import math
import random

import pytest
import torch

from analog_optimizer.evaluation.corners import summarize_corners
from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
from analog_optimizer.training.workers import DeadlineFuture

import test_corner_summary as corner


def group(lower, upper, step, value=None):
    return ParameterGroup('g', 'width', 'm', lower if value is None else value, lower, upper,
                          (ParameterBinding('M1', 'w'),), step=step)


def old_project(g, value):
    """ParameterGroup.project before the clamp."""
    value = min(g.upper, max(g.lower, value))
    index = min(math.floor((g.upper - g.lower) / g.step + 1e-12), max(0, math.floor((value - g.lower) / g.step + 0.5)))
    return g.lower + index * g.step


def test_the_top_grid_point_of_a_range_typed_in_decimals_is_the_upper_bound():
    g = group(1.84e-6, 42.38e-6, 0.02e-6)
    assert old_project(g, g.upper) > g.upper                     # the old top: 4.2380000000000004e-05
    top = g.project(g.upper)
    assert top == g.upper and g.lower <= top <= g.upper
    replace(g, value=top).validate()                             # the group accepts its own top value


def test_every_other_projection_is_bitwise_what_it_was():
    rng = random.Random(20260930)
    for _ in range(20000):
        step = rng.choice([0.005, 0.01, 0.02, 0.05, 0.1]) * 1e-6
        lower = round(rng.uniform(0.2, 5) / (step * 1e6)) * step
        upper = float(f'{(lower + step * rng.randint(10, 3000)) * 1e6:.4f}') * 1e-6
        g = group(lower, upper, step)
        value = rng.uniform(lower - step, upper + step)
        old, new = old_project(g, value), g.project(value)
        assert new == old if old <= upper else new == upper


@pytest.mark.parametrize('gone', ['none', 'absent'])
def test_a_missing_value_counted_as_failure_fails_its_corner_without_breaking_the_summary(gone):
    specs = [replace(corner.SPECS[0], missing_is_failure=True), *corner.SPECS[1:]]
    candidate = corner.design()
    results = []
    for c in corner.CORNERS:
        result = corner.result(candidate, c)
        if c.model_section == 'ss':
            metrics, units, validity = dict(result.metrics), dict(result.metric_units), dict(result.metric_validity)
            if gone == 'none':
                metrics['gain'], validity['gain'] = None, False
            else:
                del metrics['gain'], units['gain'], validity['gain']
            result = replace(result, metrics=metrics, metric_units=units, metric_validity=validity)
        results.append(result)
    summary = summarize_corners(candidate, corner.CORNERS, tuple(results), specs)   # raised TypeError / KeyError
    assert summary.failed_corners == 1 and summary.passed_corners == len(corner.CORNERS) - 1
    assert summary.disposition == 'rejected'
    assert summary.worst_case_metrics['gain']['valid_corner_count'] == len(corner.CORNERS) - 1


class LateFuture:
    """A job that finishes just after the deadline's wait gave up."""
    def __init__(self, value):
        self.value, self.waits = value, 0

    def result(self, timeout=None):
        if timeout is not None and self.waits == 0:
            self.waits += 1
            raise TimeoutError()
        return self.value

    def done(self):
        return self.waits > 0


def test_a_result_that_arrives_right_after_the_wait_gives_up_is_returned():
    assert DeadlineFuture(LateFuture('ready'), 60, 'late').result() == 'ready'      # re-raised the timeout before


def test_a_job_that_itself_timed_out_still_raises_its_own_error():
    future = Future()
    future.set_exception(TimeoutError('the job timed out'))
    with pytest.raises(TimeoutError, match='the job timed out'):
        DeadlineFuture(future, 60, 'own').result()


def test_a_journal_can_skip_the_fsync_and_stays_atomic(tmp_path, monkeypatch):
    from analog_optimizer.envs import sizing
    calls = []
    monkeypatch.setattr(sizing.os, 'fsync', lambda fd: calls.append(fd))
    sizing.write_record(tmp_path / 'a.json', {'x': 1})
    sizing.write_record(tmp_path / 'b.json', {'x': 2}, durable=False)
    assert len(calls) == 1 and (tmp_path / 'b.json').read_text() == '{\n  "x": 2\n}\n'
    assert not list(tmp_path.glob('*.tmp'))


def test_a_synthetic_environment_skips_the_fsync_and_a_real_one_does_not(monkeypatch):
    from analog_optimizer.envs import sizing
    seen = []
    monkeypatch.setattr(sizing, 'write_record', lambda path, value, **options: seen.append(options))
    for origin in ('synthetic', 'real'):
        env = object.__new__(sizing.CircuitSizingEnv)
        env.expected_origin = origin
        env._record('journal.json', {})
    assert seen == [dict(durable=False), {}]


def test_a_mapper_that_reads_the_graph_as_it_is_legalizes_the_same(opamp):
    from analog_optimizer.parameters.actions import ActionMapper
    rng = random.Random(7)
    copied, shared = ActionMapper(opamp), ActionMapper(opamp, copy=False)
    for _ in range(200):
        proposal = {g: rng.uniform(-1, 1) for g in copied.group_ids}
        assert copied.legalize(proposal) == shared.legalize(proposal)
    assert shared._graph is opamp and copied._graph is not opamp


def test_the_replay_checkpoint_bytes_do_not_depend_on_the_copy():
    from analog_optimizer.training.replay import ReplayBuffer
    replay = ReplayBuffer(8, origin='synthetic')
    replay._items = [{'a': [1, 2.5, 'x'], 'b': {'c': (3, 4)}}, {'a': [5], 'b': {}}]
    copied, direct = io.BytesIO(), io.BytesIO()
    torch.save(dict(replay=replay.state_dict()), copied)
    torch.save(dict(replay=replay.state_dict(copy=False)), direct)
    assert copied.getvalue() == direct.getvalue()
    assert replay.state_dict()['items'] is not replay._items and replay.state_dict(copy=False)['items'] is replay._items


def test_a_batch_keeps_its_own_source_metadata(opamp):
    from analog_optimizer.models.inputs import batch_observations
    from research_support import observation
    opamp_observation = observation(opamp)
    batch = batch_observations([opamp_observation])
    metadata = batch.graph.graph_metadata[0]
    metadata.source_metadata['changed_by_the_batch'] = True
    again = batch_observations([opamp_observation]).graph.graph_metadata[0]
    assert 'changed_by_the_batch' not in again.source_metadata
