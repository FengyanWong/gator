"""Owned spawned workers with submission deadlines and bounded shutdown.

Only these Python children are terminated. Remote simulator jobs are never
assumed stopped after a lost worker; callers retain their recovery records.
"""
from concurrent.futures import Future, TimeoutError
from dataclasses import dataclass
import math
import multiprocessing
import queue
import threading
from time import monotonic, sleep
import traceback


@dataclass(frozen=True)
class WorkerLimits:
    operation_seconds: float = 300.0
    shutdown_seconds: float = 10.0
    history_limit: int = 100

    def __post_init__(self):
        for value in (self.operation_seconds, self.shutdown_seconds):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError('Worker deadlines must be finite and positive')
        if type(self.history_limit) is not int or self.history_limit < 0:
            raise ValueError('history_limit must be a nonnegative integer')


class WorkerTimeout(TimeoutError):
    pass


_CONNECTION = None


def worker_progress(value):
    """Activity at completed benchmark operations, never a timer masking a hang."""
    if _CONNECTION is not None:
        _CONNECTION.send(('progress', value))


def _serve(connection):
    global _CONNECTION
    _CONNECTION = connection
    try:
        while True:
            command = connection.recv()
            if command is None:
                return
            function, args, kwargs = command
            try:
                result = function(*args, **kwargs)
                connection.send((True, result))
            except BaseException as exc:
                connection.send((False, (type(exc).__name__, str(exc), traceback.format_exc())))
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


class DeadlineFuture:
    def __init__(self, future, seconds, description, heartbeat=False):
        self.future, self.seconds, self.description = future, seconds, description
        self.heartbeat = heartbeat
        self.started = monotonic()
        self.future.last_activity = self.started
        self.future.progress = None

    def result(self):
        while True:
            remaining = self.remaining()
            try:
                return self.future.result(timeout=max(0., min(.1, remaining)))
            except TimeoutError as exc:
                if self.future.done():  # finished right after the wait gave up: its own result, or its own exception
                    return self.future.result()
                if remaining <= 0:
                    raise WorkerTimeout(f'Worker deadline exceeded: {self.description}; last progress={self.future.progress}') from exc

    def done(self):
        return self.future.done()

    def remaining(self):
        start = self.future.last_activity if self.heartbeat else self.started
        return start + self.seconds - monotonic()


def wait_workers(pending):
    """Watch every lane's deadline, even while another lane keeps making progress."""
    waiting = dict(pending)
    while waiting:
        ready = [key for key, future in waiting.items() if future.done() or future.remaining() <= 0]
        if not ready:
            sleep(.02)
        for key in ready:
            yield key, waiting.pop(key)


class OwnedWorker:
    """One sequential process; daemon I/O thread keeps pipe sends off the caller."""
    def __init__(self, lane, limits=None):
        self.lane, self.limits = lane, limits or WorkerLimits()
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_serve, args=(child,), name=f'gator-worker-{lane}')
        self.process.start()
        child.close()
        self.commands = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(target=self._exchange, daemon=True)
        self.thread.start()

    def _exchange(self):
        while True:
            item = self.commands.get()
            if item is None:
                try:
                    self.connection.send(None)
                except (OSError, EOFError):
                    pass
                return
            command, future = item
            try:
                self.connection.send(command)
                while True:
                    ok, value = self.connection.recv()
                    if ok != 'progress':
                        break
                    future.last_activity, future.progress = monotonic(), value
                if not ok:
                    name, message, trace = value
                    raise RuntimeError(f'{name}: {message}\n{trace}')
                future.set_result(value)
            except BaseException as exc:
                future.set_exception(exc)

    def submit(self, function, *args, timeout=None, heartbeat=False, **kwargs):
        if self.closed or not self.process.is_alive():
            raise RuntimeError(f'Worker {self.lane} is closed or dead')
        future = Future()
        seconds = self.limits.operation_seconds if timeout is None else timeout
        result = DeadlineFuture(future, seconds, f'lane={self.lane}, operation={function.__name__}', heartbeat)
        self.commands.put(((function, args, kwargs), future))
        return result

    def shutdown(self):
        if self.closed:
            return dict(lane=self.lane, state='already_closed')
        self.closed = True
        self.commands.put(None)
        self.process.join(self.limits.shutdown_seconds)
        forced = self.process.is_alive()
        if forced:
            self.process.terminate()
            self.process.join(self.limits.shutdown_seconds)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(self.limits.shutdown_seconds)
        alive = self.process.is_alive()
        self.connection.close()
        result = dict(lane=self.lane, pid=self.process.pid, forced=forced,
                      state='still_alive' if alive else 'terminated' if forced else 'closed',
                      exitcode=self.process.exitcode)
        if not alive:
            self.process.close()
        return result


def append_history(report, key, value, limit):
    report[key + '_count'] = report.get(key + '_count', 0) + 1
    report[key].append(value)
    if limit is not None:
        del report[key][:max(0, len(report[key]) - limit)]
