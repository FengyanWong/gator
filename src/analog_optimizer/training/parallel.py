"""Bounded synchronous rounds of independent environments, one central learner.

Each lane owns one spawned process and at most one Spectre job at a time. Only
the parent runs the actor, writes replay, and updates SAC. Results are admitted
in stable lane order after the entire round finishes, regardless of job speed.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import multiprocessing
import os
from pathlib import Path
from time import perf_counter

from .replay import Transition

_ENV = None


def _open(factory, lane):
    global _ENV
    if _ENV is not None:
        raise RuntimeError('Worker already owns an environment')
    _ENV = factory(lane)
    _ENV.__enter__()
    return dict(pid=os.getpid(), directory=str(_ENV.directory), origin=_ENV.expected_origin,
                group_ids=_ENV.mapper.group_ids)


def _reset():
    return _ENV.reset()


def _step(proposal):
    return _ENV.step(proposal)


def _close():
    if _ENV is None:
        return dict(state='not_opened', simulation_calls=0)
    try:
        _ENV.close()
    finally:
        import json
        path = _ENV.directory / 'restoration.json'
        # If close raises, the parent still receives that exception, and the
        # recovery journal remains accessible through the worker directory.
        if path.exists():
            record = json.loads(path.read_text())
    return dict(record, directory=str(_ENV.directory), pid=os.getpid())


@dataclass(frozen=True)
class TableEnvironmentFactory:
    """Picklable configuration; create backend and environment in the worker."""
    config: object
    profile: object
    table_path: Path
    specs: tuple
    output: Path
    max_steps: int
    timeout_seconds: float = 120.0
    reference_metrics: dict | None = None

    def __call__(self, lane):
        from analog_optimizer.backends.cdf_table import CdfTableBackend
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        backend = CdfTableBackend(self.config, self.profile, self.table_path)
        env = CircuitSizingEnv(backend, self.profile.optimization_graph(), self.specs,
                               self.output / f'worker-{lane}', max_steps=self.max_steps,
                               timeout_seconds=self.timeout_seconds, stop_on_success=False)
        if self.reference_metrics is not None:
            original_reset = env.reset
            def checked_reset():
                import math
                obs, info = original_reset()
                if obs is not None and info['evaluation_valid']:
                    reference = self.reference_metrics
                    if obs.metrics.keys() != reference.keys() or any(
                        not ((a is None and reference[k] is None) or
                             (a is not None and reference[k] is not None and
                              math.isclose(a, reference[k], rel_tol=1e-6, abs_tol=1e-12)))
                        for k, a in obs.metrics.items()):
                        raise RuntimeError('Worker baseline differs from verified real measurements')
                return obs, info
            env.reset = checked_reset
        return env


def collect_parallel_episodes(factory, learner, replay, rng, *, max_workers,
                              episodes, warmup=8, batch_size=8, report=None, progress=None):
    """Collect a fixed episode budget with bounded processes and no auto-retry.

    A failed round is fully drained; eligible peers are admitted, infrastructure
    failures are excluded, all workers are closed, then the error is raised.
    Checkpoints are taken by the caller at completed-run boundaries only.
    """
    for name, value, minimum in [('max_workers', max_workers, 1), ('episodes', episodes, 1),
                                 ('warmup', warmup, 0), ('batch_size', batch_size, 1)]:
        if type(value) is not int or value < minimum:
            raise ValueError(f'{name} must be an integer >= {minimum}')
    if replay.origin != learner.experiment['origin']:
        raise ValueError('Learner and replay origins differ')
    count = min(max_workers, episodes)
    report = report if report is not None else {}
    report.update(max_workers=max_workers, worker_count=count, requested_episodes=episodes,
                  completed_episodes=0, simulation_calls=0, peak_in_flight=0,
                  stages=[], resets=[], workers=[], restorations=[], errors=[],
                  scheduling='synchronous rounds; stable lane-order replay; parent-only learner',
                  automatic_retries=0)
    started = perf_counter()
    pools = []
    primary_error = None
    try:
        # Separate single-process executors pin each stateful environment to its
        # owner. A shared process pool cannot guarantee state/worker affinity.
        for _ in range(count):
            pools.append(ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')))
        pending = [pool.submit(_open, factory, lane) for lane, pool in enumerate(pools)]
        opened = []
        for future in pending:
            try:
                info = future.result()
                opened.append(info)
                report['workers'].append(info)
                if info['origin'] != replay.origin:
                    raise ValueError('Worker origin differs from learner/replay')
            except BaseException as exc:
                primary_error = primary_error or exc
        if primary_error:
            raise primary_error
        next_episode = 0
        while next_episode < episodes:
            lanes = list(range(min(count, episodes - next_episode)))
            episode_ids = {lane: next_episode + lane for lane in lanes}
            next_episode += len(lanes)
            resets = {lane: pools[lane].submit(_reset) for lane in lanes}
            report['peak_in_flight'] = max(report['peak_in_flight'], len(resets))
            observations = {}
            for lane, future in resets.items():
                report['simulation_calls'] += 1
                try:
                    obs, info = future.result()
                    report['resets'].append(dict(lane=lane, episode=episode_ids[lane], **info))
                    if obs is None or info['terminated'] or info['truncated'] or not info['evaluation_valid']:
                        raise RuntimeError(f'Worker {lane} reset failed: {info["record_path"]}')
                    observations[lane] = obs
                except BaseException as exc:
                    primary_error = primary_error or exc
            if primary_error:
                raise primary_error
            while observations:
                lanes = sorted(observations)
                random_count = min(len(lanes), max(0, warmup - replay.insertions))
                proposals = {lane: {group: rng.uniform(-1, 1) for group in opened[lane]['group_ids']}
                             for lane in lanes[:random_count]}
                policy_lanes = lanes[random_count:]
                policy_version = learner.updates
                inference_started = perf_counter()
                if policy_lanes:
                    proposals.update(zip(policy_lanes, learner.act([observations[lane] for lane in policy_lanes])))
                inference_seconds = perf_counter() - inference_started
                sampling_started = perf_counter()
                pending = {lane: pools[lane].submit(_step, proposals[lane]) for lane in lanes}
                report['peak_in_flight'] = max(report['peak_in_flight'], len(pending))
                results = {}
                for lane, future in pending.items():
                    report['simulation_calls'] += 1
                    try:
                        results[lane] = future.result()
                    except BaseException as exc:
                        primary_error = primary_error or exc
                sampling_seconds = perf_counter() - sampling_started
                for lane, step in results.items():
                    info = step[4]
                    stage = dict(lane=lane, episode=episode_ids[lane], proposal=proposals[lane],
                                 action_source='random_warmup' if lane in lanes[:random_count] else 'sac_policy',
                                 policy_version=policy_version, candidate_id=info['candidate_id'],
                                 record_path=info['record_path'], job_id=info['job_id'],
                                 reward=step[1], success=info['success'], status=info['status'],
                                 replay_eligible=info['replay_eligible'], update=None,
                                 round_inference_seconds=inference_seconds,
                                 round_sampling_seconds=sampling_seconds)
                    report['stages'].append(stage)
                    if info['replay_eligible']:
                        try:
                            transition = Transition.from_step(observations[lane], proposals[lane], step)
                            replay.add(transition)
                            if len(replay) >= batch_size:
                                update_started = perf_counter()
                                stage['update'] = learner.update(replay.sample(batch_size))
                                stage['update_seconds'] = perf_counter() - update_started
                        except BaseException as exc:
                            primary_error = primary_error or exc
                    else:
                        primary_error = primary_error or RuntimeError(
                            f'Worker {lane} returned an ineligible transition: {info["record_path"]}')
                    if step[2] or step[3]:
                        del observations[lane]
                        if step[2] and not step[3]:
                            report['completed_episodes'] += 1
                    else:
                        observations[lane] = step[0]
                if progress is not None:
                    progress(report)
                if primary_error:
                    raise primary_error
    except BaseException as exc:
        primary_error = exc
        report['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
    finally:
        closing = []
        for pool in pools:
            try:
                closing.append(pool.submit(_close))
            except BaseException as exc:
                primary_error = primary_error or exc
                report['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
        for future in closing:
            try:
                report['restorations'].append(future.result())
            except BaseException as exc:
                primary_error = primary_error or exc
                report['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
        for pool in pools:
            pool.shutdown(wait=True, cancel_futures=True)
        if len(report['restorations']) == len(pools):
            report['simulation_calls'] = sum(r['simulation_calls'] for r in report['restorations'])
        report.update(elapsed_seconds=perf_counter() - started, replay_size=len(replay),
                      training_updates=learner.updates, passed=primary_error is None)
    if primary_error:
        raise primary_error
    return report
