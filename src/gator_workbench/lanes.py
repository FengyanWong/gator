"""Evaluation lanes: isolated owners of one EXISTING ``CircuitSizingEnv`` each.

A lane runs at most one simulation job at a time, so ``concurrency`` lanes means
``concurrency`` independent jobs (not threads inside one job). Lanes never write
data tables; they return attempt results to the scheduler, the single writer.

* ``ThreadLane``  - one dedicated thread per environment (the environment enforces
  same-thread ownership). Used for the pure-Python analytic mock backend.
* ``ProcessLane`` - the optimizer's own spawned ``OwnedWorker`` process, with its
  operation deadlines and bounded shutdown. Used for real backends.

A retry re-runs the SAME legalized action through the environment's evaluation
routine without consuming another episode step, so it remains one evaluation with an
additional job attempt. The environment itself still performs no automatic retries.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import threading


def _now():
    return datetime.now(timezone.utc).isoformat()


def _mtime(path):
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


SCRATCH_FOLDERS = ('exports', 'simulations')     # an environment's export packages and per-job simulation folders


def link_scratch(directory, root):
    """Make an environment's scratch folders links into `root` (record 7.149). The environment creates them only when
    it first uses them, so a fresh one has neither; a folder that cannot be linked stays where it is."""
    directory = Path(directory)
    for name in SCRATCH_FOLDERS:
        link = directory / name
        if link.exists() or link.is_symlink():
            continue
        target = Path(root) / directory.name / name
        try:
            target.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pass


def unlink_scratch(directory):
    """Remove the links `link_scratch` made (not what they point to: the run removes its scratch as a whole)."""
    for name in SCRATCH_FOLDERS:
        link = Path(directory) / name
        if link.is_symlink():
            link.unlink()


class ScratchLinked:
    """An environment factory whose environments keep their simulator scratch on the local disk, under `root`
    (`layout.local_scratch`). Each environment's own folder - launch journals, candidate records, restoration record -
    stays where the factory puts it. Picklable whenever `factory` is: a process lane builds its environment itself."""

    def __init__(self, factory, root):
        self.factory, self.root = factory, str(root)

    def __call__(self, lane_id):
        env = self.factory(lane_id)
        link_scratch(env.directory, self.root)
        return env


class _EnvDriver:
    """Runs inside the lane (thread or worker process) and owns the environment."""
    def __init__(self, factory, lane_id):
        self.env = factory(lane_id)
        self.env.__enter__()
        self.lane_id = lane_id
        self._journal = Path(self.env.directory) / 'candidates'
        self._seen = set()
        self._last = None          # ('reset', None) | ('step', LegalizedAction)

    def describe(self):
        env = self.env
        return dict(lane_id=self.lane_id, directory=str(env.directory), origin=env.expected_origin,
                    group_ids=list(env.mapper.group_ids), max_steps=env.max_steps,
                    step_launches=len(env.planned_conditions),
                    config_sha256=env.config_sha256, supports_retry=hasattr(env, '_evaluate'),
                    supports_reset_reuse=hasattr(env, 'reset_reused'))

    def _new_records(self):
        """The journal files this lane has not read yet. With waveform retention "all" the per-candidate journals are
        never removed, and stat-ing EVERY one of them on every lane operation was quadratic over a run (measured: 150
        evaluations -> 94 ms per call, projected minutes on the 9p mount at a thousand). Only the names that are new are
        stat-ed and read now."""
        records = []
        if not self._journal.is_dir():
            return records
        try:
            names = [entry.name for entry in os.scandir(self._journal)]
        except OSError:
            return records
        fresh = [name for name in names
                 if name.endswith('.json') and not name.endswith('.tmp') and name not in self._seen]
        for name in sorted(fresh, key=lambda name: _mtime(self._journal / name)):
            self._seen.add(name)
            try:
                records.append(json.loads((self._journal / name).read_text()))
            except (OSError, json.JSONDecodeError):
                pass
        return records

    def run(self, op, proposal=None, allowance=1, stop_file=None):
        env = self.env
        if op == 'continue':
            # Absolute sizing actions need no simulator state from the previous process.
            # Restore the logical episode only; this operation performs no evaluation.
            env._require_connection()
            env.steps, env.episode = proposal['steps'], proposal['episode']
            env.max_steps = proposal['max_steps']
            env._recording_observation = proposal['observation']
            env._done = False
            return dict(ok=True)
        calls_before, started = env.simulation_calls, _now()
        result = dict(op=op, lane_id=self.lane_id, started_at=started, ok=False, step=None, exception=None,
                      episode=None, episode_step=None)
        try:
            env.authorize_launches(allowance, stop_file=stop_file)
            if op == 'reset':
                observation, info = env.reset()
                self._last = ('reset', None)
                step = (observation, None, info['terminated'], info['truncated'], info)
            elif op == 'reset_reused':                     # the engine's every-5th-reset rule (2026-09-30): nothing runs
                observation, info = env.reset_reused()
                self._last = None                          # so there is nothing to retry either
                step = (observation, None, info['terminated'], info['truncated'], info)
            elif op == 'step':
                action = env.mapper.legalize(proposal)      # invalid input costs nothing, as in env.step
                self._last = ('step', action)
                step = env.step(proposal)
            elif op == 'retry':
                if self._last is None:
                    raise RuntimeError('Nothing to retry')
                env._require_connection()
                kind, action = self._last
                step = env._evaluate(action, reset=kind == 'reset')
                if kind == 'reset':
                    observation, _, _, _, info = step
                    step = (observation, None, info['terminated'], info['truncated'], info)
            else:
                raise ValueError(f'Unknown lane operation {op!r}')
            result.update(ok=True, step=step)
        except BaseException as exc:                       # reported to the scheduler, never swallowed
            result['exception'] = dict(type=type(exc).__name__, message=str(exc)[:4000],
                                       cleanup_error=getattr(exc, 'cleanup_error', None))
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                result['interrupted'] = True
        records = self._new_records()
        result.update(ended_at=_now(), launches=env.simulation_calls - calls_before, records=records,
                      record=records[-1] if records else None, episode=env.episode, episode_step=env.steps)
        return result

    def close(self):
        outcome = dict(lane_id=self.lane_id, state='unknown', simulation_calls=self.env.simulation_calls)
        try:
            self.env.close()
        finally:
            path = Path(self.env.directory) / 'restoration.json'
            if path.exists():
                try:
                    outcome.update(json.loads(path.read_text()))
                except (OSError, json.JSONDecodeError):
                    pass
        return outcome


class _Handle:
    def __init__(self, future):
        self._future = future

    def done(self):
        return self._future.done()

    def result(self):
        return self._future.result()


class ThreadLane:
    kind = 'thread'

    def __init__(self, lane_id, factory):
        self.lane_id = str(lane_id)
        self._commands = queue.Queue()
        self._ready = Future()
        self._thread = threading.Thread(target=self._serve, args=(factory,), name=f'gator-lane-{lane_id}',
                                        daemon=True)
        self._thread.start()
        self.info = self._ready.result()

    def _serve(self, factory):
        try:
            driver = _EnvDriver(factory, self.lane_id)
            self._ready.set_result(driver.describe())
        except BaseException as exc:
            self._ready.set_exception(exc)
            return
        while True:
            item = self._commands.get()
            if item is None:
                return
            (op, proposal, allowance, stop_file), future = item
            try:
                future.set_result(driver.close() if op == 'close' else driver.run(op, proposal, allowance, stop_file))
            except BaseException as exc:
                future.set_exception(exc)
            if op == 'close':
                return

    def submit(self, op, proposal=None, *, allowance=1, stop_file=None):
        future = Future()
        self._commands.put(((op, proposal, allowance, stop_file), future))
        return _Handle(future)

    def close(self, timeout=30.0):
        if not self._thread.is_alive():
            return dict(lane_id=self.lane_id, state='already_closed')
        outcome = self.submit('close')._future.result(timeout=timeout)
        self._thread.join(timeout)
        return outcome


# ---- worker-process side (module level so that spawn can import it) -------------------------
_DRIVER = None


def _process_open(factory, lane_id):
    global _DRIVER
    if _DRIVER is not None:
        raise RuntimeError('Worker already owns an environment')
    _DRIVER = _EnvDriver(factory, lane_id)
    return _DRIVER.describe()


def _process_run(op, proposal=None, allowance=1, stop_file=None):
    return _DRIVER.run(op, proposal, allowance, stop_file)


def _process_close():
    if _DRIVER is None:
        return dict(state='not_opened', simulation_calls=0)
    return _DRIVER.close()


class ProcessLane:
    kind = 'process'

    def __init__(self, lane_id, factory, limits=None):
        from analog_optimizer.training.workers import OwnedWorker, WorkerLimits
        self.lane_id = str(lane_id)
        self.limits = limits or WorkerLimits()
        self._worker = OwnedWorker(self.lane_id, self.limits)
        try:
            self.info = self._worker.submit(_process_open, factory, self.lane_id).result()
        except BaseException:
            self._worker.shutdown()
            raise

    def submit(self, op, proposal=None, *, allowance=1, stop_file=None):
        return self._worker.submit(_process_run, op, proposal, allowance, stop_file)

    def close(self, timeout=None):
        outcome = dict(lane_id=self.lane_id, state='unknown')
        try:
            outcome = self._worker.submit(_process_close, timeout=timeout or self.limits.shutdown_seconds).result()
        finally:
            outcome['shutdown'] = self._worker.shutdown()   # terminates only this owned Python child
        return outcome


def open_lanes(factory, count, *, use_processes, limits=None):
    """Open the run's lanes side by side. Each builds its own environment, a real lane in a process of its own (about 2 s),
    so one after another a 4-lane run waited 8.7 s before its first evaluation (record 7.136). They come back in index
    order; if one fails to open, every lane that did open is closed and the failure of the lowest index is raised."""
    def open_one(index):
        return ProcessLane(index, factory, limits) if use_processes else ThreadLane(index, factory)

    futures = []
    try:
        with ThreadPoolExecutor(max_workers=max(count, 1), thread_name_prefix='gator-lane-open') as pool:
            futures = [pool.submit(open_one, index) for index in range(count)]
        failure = next((future.exception() for future in futures if future.exception() is not None), None)
        if failure is not None:
            raise failure
    except BaseException:
        for future in futures:
            if future.done() and not future.cancelled() and future.exception() is None:
                try:
                    future.result().close()
                except BaseException:
                    pass
        raise
    return [future.result() for future in futures]
