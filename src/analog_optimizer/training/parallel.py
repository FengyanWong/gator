"""Bounded synchronous rounds of independent environments, one central learner.

Each lane owns one spawned process and at most one Spectre job at a time. Only
the parent runs the actor, writes replay, and updates SAC. Results are admitted
in stable lane order after the entire round finishes, regardless of job speed.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
from time import perf_counter

from .collect import random_proposal, timed_update
from .replay import Transition
from .workers import OwnedWorker, WorkerLimits, append_history
from .recovery import parallel_state
from .runner import LaunchBudget
from analog_optimizer.measurements.specs import RewardSettings

_ENV = None


def _open(factory, lane, recorder=None):
    global _ENV
    if _ENV is not None:
        raise RuntimeError('Worker already owns an environment')
    if recorder is not None:
        from dataclasses import replace
        recorder = replace(recorder, worker_id=str(lane))
    create_recorded = getattr(factory, 'create_recorded', None)
    _ENV = create_recorded(lane, recorder) if recorder is not None and callable(create_recorded) else factory(lane)
    if recorder is not None and _ENV.recorder is not recorder:
        # Compatibility for external factories that do not implement the hook.
        _ENV.recorder = recorder
        recorder.bind(_ENV._reference_graph, _ENV.evaluator.specs,
                           dict(max_steps=_ENV.max_steps, timeout_seconds=_ENV.timeout_seconds,
                                stop_on_success=_ENV.stop_on_success, config_sha256=_ENV.config_sha256))
    _ENV.__enter__()
    return dict(pid=os.getpid(), directory=str(_ENV.directory), origin=_ENV.expected_origin,
                group_ids=_ENV.mapper.group_ids, step_launches=len(_ENV.planned_conditions))


def _reset(allowance=1):
    _ENV.authorize_launches(allowance)
    return _ENV.reset()


def _step(proposal, policy_version=None, phase='training', allowance=1):
    _ENV.authorize_launches(allowance)
    if _ENV.recorder is not None:
        _ENV.recorder.policy_version, _ENV.recorder.phase = policy_version, phase
    return _ENV.step(proposal)


def _close():
    if _ENV is None:
        return dict(state='not_opened', simulation_calls=0)
    record = dict(state='unknown', simulation_calls=_ENV.simulation_calls)
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
class NativeEnvironmentFactory:
    """Picklable configuration; create backend and environment in the worker."""
    config: object
    profile: object
    specs: tuple
    output: Path
    max_steps: int
    timeout_seconds: float = 120.0
    reference_metrics: dict | None = None
    preparation: object = None
    reward_settings: RewardSettings = field(default_factory=RewardSettings)
    condition_policy: str = 'off'
    corners: tuple = ()
    condition_jobs: int = 2              # a candidate's corner jobs two at a time where the backend allows (2026-09-30)

    @contextmanager
    def preparation_context(self, limits, report):
        from analog_optimizer.backends.native_preparation import preparation_session
        with preparation_session(self.config, self.profile, limits, report) as service:
            yield replace(self, preparation=service)

    def __call__(self, lane):
        return self.create_recorded(lane, None)

    def create_recorded(self, lane, recorder):
        from analog_optimizer.backends.native_preparation import NativeCandidateBackend
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        backend = NativeCandidateBackend(self.config, self.profile, self.preparation)
        env = CircuitSizingEnv(backend, self.profile.optimization_graph(), self.specs,
                               self.output / f'worker-{lane}', max_steps=self.max_steps,
                               timeout_seconds=self.timeout_seconds, stop_on_success=False, recorder=recorder,
                               reward_settings=self.reward_settings, condition_policy=self.condition_policy, corners=self.corners,
                               condition_jobs=self.condition_jobs)
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
                              episodes, warmup=8, batch_size=8, report=None, progress=None,
                              recorder=None, checkpoints=None, update_recorder=None, limits=None,
                              completed_before=0, calls_before=0, max_simulation_calls=None):
    """Collect a fixed episode budget with bounded processes and no auto-retry.

    A failed round is fully drained; eligible peers are admitted, infrastructure
    failures are excluded, all workers are closed, then the error is raised.
    Checkpoints follow complete, successfully admitted rounds; resume starts fresh episodes.
    """
    for name, value, minimum in [('max_workers', max_workers, 1), ('episodes', episodes, 1),
                                 ('warmup', warmup, 0), ('batch_size', batch_size, 1)]:
        if type(value) is not int or value < minimum:
            raise ValueError(f'{name} must be an integer >= {minimum}')
    from analog_optimizer.backends.native_preparation import validate_workers
    validate_workers(max_workers)
    if replay.origin != learner.experiment['origin']:
        raise ValueError('Learner and replay origins differ')
    limits = limits or WorkerLimits()
    history_limit = limits.history_limit if recorder is not None else None
    count = min(max_workers, episodes)
    report = report if report is not None else {}
    if getattr(factory, 'condition_policy', 'off') != 'off' and max_simulation_calls is None:
        raise ValueError('Robust collection requires a finite global launch ceiling')
    root = getattr(factory, 'output', None)
    budget = LaunchBudget(max_simulation_calls, consumed=calls_before,
                          journal=None if root is None else Path(root) / 'collector-launch-budget.json')
    report.update(max_workers=max_workers, worker_count=count, requested_episodes=episodes,
                  completed_episodes=0, simulation_calls=0, peak_in_flight=0,
                  stages=[], resets=[], stages_count=0, resets_count=0, workers=[], restorations=[], errors=[],
                  unfinished_workers=[], worker_shutdown=[], dispatch_attempts=0, call_count_kind='confirmed',
                  scheduling='synchronous rounds; stable lane-order replay; parent-only learner',
                  automatic_retries=0)
    started = perf_counter()
    pools = []
    primary_error = None
    calls = {lane: 0 for lane in range(count)}
    active = {}
    preparation_stack = ExitStack()

    def failed(lane, operation, exc):
        if lane in budget.holds:
            allowance = budget.holds[lane]
            budget.finish(lane, allowance, uncertain=allowance)
        report['errors'].append(dict(lane=lane, operation=operation, type=type(exc).__name__, message=str(exc)))
        report['unfinished_workers'].append(dict(lane=lane, operation=operation,
            state='unconfirmed', recovery='inspect owned job/workspace; no automatic retry or deletion'))
        report['call_count_kind'] = 'confirmed_lower_bound'

    try:
        prepare_context = getattr(factory, 'preparation_context', None)
        if callable(prepare_context):
            factory = preparation_stack.enter_context(prepare_context(limits, report))
        # Separate single-process executors pin each stateful environment to its
        # owner. A shared process pool cannot guarantee state/worker affinity.
        for lane in range(count):
            pools.append(OwnedWorker(lane, limits))
        pending = [pool.submit(_open, factory, lane, recorder) for lane, pool in enumerate(pools)]
        opened = []
        for lane, future in enumerate(pending):
            try:
                info = future.result()
                opened.append(info)
                report['workers'].append(info)
                if info['origin'] != replay.origin:
                    raise ValueError('Worker origin differs from learner/replay')
            except BaseException as exc:
                primary_error = primary_error or exc
                failed(lane, 'open', exc)
        if primary_error:
            raise primary_error
        next_episode = 0
        while next_episode < episodes:
            lanes = [lane for lane in range(min(count, episodes - next_episode)) if budget.reserve(lane, 1)]
            if not lanes:
                report['stop_reason'] = 'launch_budget_exhausted'
                break
            episode_ids = {lane: next_episode + lane for lane in lanes}
            next_episode += len(lanes)
            active = {lane: dict(operation='reset', episode=episode_ids[lane]) for lane in lanes}
            resets = {lane: pools[lane].submit(_reset) for lane in lanes}
            report['peak_in_flight'] = max(report['peak_in_flight'], len(resets))
            observations = {}
            for lane, future in resets.items():
                report['dispatch_attempts'] += 1
                try:
                    obs, info = future.result()
                    budget.finish(lane, info['simulation_calls'] - calls[lane], uncertain=info.get('uncertain_calls', 0))
                    active.pop(lane, None)
                    calls[lane] = info['simulation_calls']
                    report['simulation_calls'] = sum(calls.values())
                    append_history(report, 'resets', dict(lane=lane, episode=episode_ids[lane], **info), history_limit)
                    if obs is None or info['terminated'] or info['truncated'] or not info['evaluation_valid']:
                        raise RuntimeError(f'Worker {lane} reset failed: {info["record_path"]}')
                    observations[lane] = obs
                except BaseException as exc:
                    primary_error = primary_error or exc
                    failed(lane, 'reset', exc)
            if primary_error:
                raise primary_error
            while observations:
                lanes = [lane for lane in sorted(observations) if budget.reserve(lane, opened[lane]['step_launches'])]
                for lane in set(observations) - set(lanes):
                    del observations[lane]
                if not lanes:
                    report['stop_reason'] = 'launch_budget_exhausted'
                    next_episode = episodes
                    break
                random_count = min(len(lanes), max(0, warmup - replay.insertions))
                proposals = {lane: random_proposal(rng, opened[lane]['group_ids']) for lane in lanes[:random_count]}
                policy_lanes = lanes[random_count:]
                policy_version = learner.updates
                inference_started = perf_counter()
                if policy_lanes:
                    proposals.update(zip(policy_lanes, learner.act([observations[lane] for lane in policy_lanes])))
                inference_seconds = perf_counter() - inference_started
                sampling_started = perf_counter()
                active = {lane: dict(operation='step', episode=episode_ids[lane], proposal=proposals[lane]) for lane in lanes}
                pending = {lane: pools[lane].submit(_step, proposals[lane], policy_version,
                                                  'random_exploration' if lane in lanes[:random_count] else 'training',
                                                  opened[lane]['step_launches'])
                           for lane in lanes}
                report['peak_in_flight'] = max(report['peak_in_flight'], len(pending))
                results = {}
                for lane, future in pending.items():
                    report['dispatch_attempts'] += 1
                    try:
                        results[lane] = future.result()
                        budget.finish(lane, results[lane][4]['simulation_calls'] - calls[lane],
                                      uncertain=results[lane][4].get('uncertain_calls', 0))
                        active.pop(lane, None)
                        calls[lane] = results[lane][4]['simulation_calls']
                        report['simulation_calls'] = sum(calls.values())
                    except BaseException as exc:
                        primary_error = primary_error or exc
                        failed(lane, 'step', exc)
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
                    append_history(report, 'stages', stage, history_limit)
                    if info['replay_eligible']:
                        try:
                            transition = Transition.from_step(observations[lane], proposals[lane], step)
                            replay.add(transition)
                            if len(replay) >= batch_size:
                                stage['update'], stage['update_seconds'] = timed_update(learner, replay, batch_size)
                                if update_recorder is not None:
                                    update_recorder.add(stage['update'])
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
                if primary_error:
                    raise primary_error
                if checkpoints is not None:
                    checkpoints.maybe_save(learner, replay, replay.insertions,
                        run_state=parallel_state(rng, report, completed_before=completed_before,
                                                 calls_before=calls_before))
                if progress is not None:
                    progress(report)
    except BaseException as exc:
        primary_error = exc
        report['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
    finally:
        closing = []
        for lane, pool in enumerate(pools):
            try:
                closing.append((lane, pool.submit(_close, timeout=limits.shutdown_seconds)))
            except BaseException as exc:
                primary_error = primary_error or exc
                failed(lane, 'close', exc)
        for lane, future in closing:
            try:
                restored = future.result()
                report['restorations'].append(restored)
                calls[lane] = restored['simulation_calls']
            except BaseException as exc:
                primary_error = primary_error or exc
                failed(lane, 'close', exc)
        for lane, pool in enumerate(pools):
            try:
                stopped = pool.shutdown()
                report['worker_shutdown'].append(stopped)
                if stopped['state'] == 'still_alive':
                    raise RuntimeError(f'Worker {lane} did not stop')
            except BaseException as exc:
                primary_error = primary_error or exc
                failed(lane, 'shutdown', exc)
        try:
            preparation_stack.close()
        except BaseException as exc:
            primary_error = primary_error or exc
            report['errors'].append(dict(operation='preparation_close', type=type(exc).__name__, message=str(exc)))
        report['simulation_calls'] = sum(calls.values())
        report['launch_budget'] = budget.snapshot()
        report['candidate_evaluations'] = budget.candidates
        if len(report['restorations']) == len(pools) and not active and not budget.uncertain:
            report['call_count_kind'] = 'confirmed'
        report['unconfirmed_operations'] = [dict(lane=lane, **info) for lane, info in active.items()]
        report.update(elapsed_seconds=perf_counter() - started, replay_size=len(replay),
                      training_updates=learner.updates, passed=primary_error is None)
    if primary_error:
        raise primary_error
    return report
