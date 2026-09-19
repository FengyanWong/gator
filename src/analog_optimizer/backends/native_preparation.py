"""One Virtuoso owner prepares actual candidates for isolated Spectre workers.

The manager exposes local IPC only. Its queue runs the complete CDF/readback/
native export transaction on one owning thread; simulator workers never attach
to Virtuoso. There is no parameter enumeration or candidate cache.
"""
from concurrent.futures import Future
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
import importlib.metadata
import math
import multiprocessing
from multiprocessing.managers import BaseManager
import os
from pathlib import Path
import queue
import tempfile
import threading
from time import perf_counter
from uuid import uuid4

from .backend import BackendNotConnected, UnsupportedCapability
from .provenance import content_hash, profile_contract
from .virtuoso_bridge import VirtuosoBridgeBackend, digest, parameter_rows, write_json

MAX_SPECTRE_WORKERS = 4


def validate_workers(value):
    if type(value) is not int or not 1 <= value <= MAX_SPECTRE_WORKERS:
        raise ValueError('max_workers must be an integer between 1 and 4')
    return value


@dataclass(frozen=True)
class BridgePreparationFactory:
    config: object
    circuit: object

    def __call__(self):
        return VirtuosoBridgeBackend(self.config, self.circuit)


class PreparationService:
    """All backend operations, including restoration, use the same owner thread."""
    def __init__(self, factory, timeout_seconds=300):
        self.factory, self.timeout_seconds = factory, timeout_seconds
        self._queue = queue.Queue(maxsize=MAX_SPECTRE_WORKERS + 1)
        self._ready, self._closed = Future(), None
        self._guard = threading.Lock()
        self._failure = None
        self._thread = threading.Thread(target=self._serve, daemon=True, name='virtuoso-preparation')
        self._thread.start()

    def _serve(self):
        backend = None
        prepared = 0
        try:
            backend = self.factory()
            backend.connect()
            initial = backend.read_parameters()
            self._ready.set_result(dict(pid=os.getpid(), initial_parameters=initial,
                profile_sha256=profile_contract(backend.circuit),
                config_sha256=content_hash(asdict(backend.config)), session_dir=str(backend.session_dir)))
            while True:
                operation, args, future = self._queue.get()
                if operation == 'close':
                    try:
                        backend.close()
                        future.set_result(dict(state='restored', prepared_candidates=prepared,
                                               pid=os.getpid(), session_dir=str(backend.session_dir)))
                    except BaseException as exc:
                        future.set_exception(exc)
                    return
                try:
                    if self._failure is not None:
                        raise RuntimeError('Preparation service stopped after a failed candidate') from self._failure
                    parameters, root, condition, candidate_id, submitted = args
                    # One transaction: no other lane can interleave a write or export.
                    backend.validate_condition(condition)
                    backend.circuit.validate_assignment(parameters)
                    started = perf_counter()
                    backend.set_parameters(parameters)
                    applied = backend.read_parameters()
                    if applied.keys() != parameters.keys() or any(
                            not math.isclose(applied[k], v, rel_tol=1e-8, abs_tol=1e-24)
                            for k, v in parameters.items()):
                        raise ValueError('CDF readback differs from requested candidate')
                    artifact = backend.generate_netlist(root, condition=condition)
                    _, verified, metadata = backend._exports.pop(artifact.job_id)
                    if applied != verified:
                        raise ValueError('Native export differs from CDF readback')
                    metadata.update(candidate_id=candidate_id, preparation_pid=os.getpid(),
                        queue_wait_seconds=started - submitted,
                        proposed_parameters=parameter_rows(parameters),
                        preparation_seconds=perf_counter() - started,
                        preparation='actual-candidate-cdf-native-export', cache_hit=False)
                    write_json(artifact.path.parent / 'manifest.json', metadata)
                    prepared += 1
                    future.set_result((artifact, applied, metadata))
                except BaseException as exc:
                    self._failure = exc
                    future.set_exception(exc)
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            self._failure = exc
        finally:
            if backend is not None:
                try:
                    backend.close()
                except BaseException as exc:
                    self._failure = exc

    def baseline(self):
        return self._ready.result(timeout=self.timeout_seconds)

    def prepare(self, parameters, root, condition, candidate_id):
        self.baseline()
        future = Future()
        with self._guard:
            if self._closed is not None:
                raise RuntimeError('Preparation service is closing')
            if self._failure is not None:
                raise RuntimeError('Preparation service stopped after a failed candidate') from self._failure
            self._queue.put(('prepare', (deepcopy(parameters), Path(root), condition, candidate_id, perf_counter()), future),
                            timeout=self.timeout_seconds)
        try:
            return future.result(timeout=self.timeout_seconds)
        except BaseException as exc:
            self._failure = exc  # Never retry or prepare further candidates after uncertain completion.
            raise

    def close(self):
        # A failed connect already executes close on the owning thread.
        self.baseline()
        with self._guard:
            if self._closed is None:
                self._closed = Future()
                self._queue.put(('close', (), self._closed), timeout=self.timeout_seconds)
        return self._closed.result(timeout=self.timeout_seconds)


class PreparationManager(BaseManager):
    pass


PreparationManager.register('PreparationService', PreparationService, exposed=('baseline', 'prepare', 'close'))


@contextmanager
def preparation_session(config, circuit, limits, report):
    """Keep the dedicated schematic owner alive until all Spectre lanes close."""
    address = str(Path(tempfile.gettempdir()) / ('gator-preparation-' + uuid4().hex + '.sock'))
    manager = PreparationManager(address=address, ctx=multiprocessing.get_context('spawn'))
    service = None
    original = None
    manager.start()
    try:
        service = manager.PreparationService(BridgePreparationFactory(config, circuit), limits.operation_seconds)
        report['preparation'] = service.baseline()
        # Tuple-key dictionaries are kept in IPC, not JSON reports.
        report['preparation']['initial_parameters'] = parameter_rows(report['preparation']['initial_parameters'])
        yield service
    except BaseException as exc:
        original = exc
        raise
    finally:
        try:
            if service is not None:
                report['preparation_restoration'] = service.close()
        except BaseException as exc:
            report.update(passed=False, preparation_restoration=dict(state='recovery_required', error=str(exc)))
            if original is None:
                raise
            original.cleanup_error = str(exc)
        finally:
            manager.shutdown()


class NativeCandidateBackend(VirtuosoBridgeBackend):
    """Lane-local simulator and immutable exports; CDF operations use the service."""
    def __init__(self, config, circuit, preparation):
        super().__init__(config, circuit)
        self.preparation = preparation
        self._active = False
        self._parameters = circuit.validate_readback(circuit.reference)

    def connect(self):
        if self._active:
            self._require_connection()
            return
        from virtuoso_bridge.env import get_runtime_env_file, set_runtime_env_file, load_vb_env
        from virtuoso_bridge.profile import resolve_profile
        self.bridge_version = importlib.metadata.version('virtuoso-bridge')
        if self.bridge_version != '0.8.0':
            raise RuntimeError('This adapter requires verified bridge 0.8.0')
        baseline = self.preparation.baseline()
        if (baseline['config_sha256'] != content_hash(asdict(self.config))
                or baseline['profile_sha256'] != profile_contract(self.circuit)
                or baseline['initial_parameters'] != self._parameters):
            raise ValueError('Preparation service profile/baseline mismatch')
        self._prior_env, self._prior_runtime = self._vb_env(), get_runtime_env_file()
        try:
            set_runtime_env_file(self.config.env_file.resolve())
            load_vb_env()
            if resolve_profile(self.config.profile) != self.config.profile:
                raise RuntimeError('Explicit bridge profile required')
            self._env_hash, self._bound_env = digest(self.config.env_file), self._vb_env()
            self._thread, self._pid = threading.get_ident(), os.getpid()
            self._active = True
        except BaseException:
            self._env_after_attach = self._vb_env()
            self.close()
            raise
        self._env_after_attach = self._vb_env()

    def _require_connection(self):
        if not self._active:
            raise BackendNotConnected('Native candidate backend is not connected')
        if (threading.get_ident(), os.getpid()) != (self._thread, self._pid):
            raise RuntimeError('Native backend must stay in its owning worker process/thread')
        if digest(self.config.env_file) != self._env_hash or self._vb_env() != self._bound_env:
            raise RuntimeError('Bridge configuration changed during an active worker')
        if getattr(self, 'bridge_version', None) == '0.8.0':
            from virtuoso_bridge.env import get_runtime_env_file
            if get_runtime_env_file() != self.config.env_file.resolve():
                raise RuntimeError('Runtime bridge environment binding changed')

    def validate_condition(self, condition):
        condition = condition or self.nominal_condition()
        self.circuit.validate_condition(condition)
        if condition != self.nominal_condition():
            raise UnsupportedCapability('Native parallel training is nominal-only')

    def prepare_candidate(self, work_root, parameters, *, condition=None, candidate_id):
        self._require_connection()
        condition = condition or self.nominal_condition()
        self.validate_condition(condition)
        self.circuit.validate_assignment(parameters)
        artifact, applied, metadata = self.preparation.prepare(parameters, str(work_root), condition, candidate_id)
        if (metadata['candidate_id'] != candidate_id or artifact.condition != condition
                or applied.keys() != parameters.keys()
                or any(not math.isclose(applied[k], v, rel_tol=1e-8, abs_tol=1e-24) for k, v in parameters.items())
                or digest(artifact.path) != artifact.sha256):
            raise ValueError('Prepared candidate identity/parameters/hash mismatch')
        # At most one export is needed by a lane. Records own historical artifacts.
        self._exports = {artifact.job_id: (artifact, dict(applied), metadata)}
        self._parameters = dict(applied)
        self.timings = dict(metadata['timings'], queue_wait=metadata['queue_wait_seconds'])
        self.get_circuit_graph(artifact)
        return artifact, dict(applied)

    def set_parameters(self, parameters):
        raise UnsupportedCapability('Use atomic prepare_candidate for the complete assignment')

    def generate_netlist(self, work_root, *, condition=None):
        raise UnsupportedCapability('Use atomic prepare_candidate for the complete assignment')

    def read_parameters(self):
        self._require_connection()
        return dict(self._parameters)

    def restore(self):
        self._require_connection()
        # This resets only the lane. The session owner restores the schematic once.
        self._parameters = self.circuit.validate_readback(self.circuit.reference)
        self._op = None

    def close(self):
        self._active = False
        self._exports.clear()
        super().close()
