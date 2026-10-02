"""Single-worker adapter over the verified bridge 0.8.0 public APIs.

The first circuit profile supports only the GPDK045 OTA input-pair width.
No SSH transport, daemon, Spectre runner or PSF reader is reimplemented here.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
from time import perf_counter
from uuid import uuid4

from .backend import (BackendNotConnected, NetlistArtifact, SimulationRequest,
                      SimulationResult, SimulationStatus, UnsupportedCapability, VirtuosoBackend)
from .gpdk045 import Gpdk045OtaProfile, GEOMETRY, equal, number, set_gpdk_mos
from .conditions import PVTCorner, SimulationCondition, finite_number
from analog_optimizer.measurements.opamp import analyze


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + '\n')
    temporary.replace(path)


def parameter_rows(parameters):
    return [{'device': d, 'parameter': p, 'value': value} for (d, p), value in sorted(parameters.items())]


# A candidate's condition jobs may run side by side on helper threads of the backend's owning thread (2026-09-30). Such
# a helper carries its owner's token here, and only run_simulation accepts it: every call that touches the Virtuoso
# session still demands the owning thread itself.
_delegation = threading.local()
_capture = threading.local()
_capture_install = threading.Lock()


def delegated_owner():
    """(thread id, pid) of the owner this helper thread runs a simulation for, else None."""
    return getattr(_delegation, 'owner', None)


class _ThreadRoutedStream:
    """Stands in for sys.stdout / sys.stderr: a thread that captures writes to its own log, every other thread to the
    stream this one replaced. contextlib.redirect_stdout swaps the process-wide stream, which two simulations running
    side by side would mix into each other's logs."""
    def __init__(self, original, name):
        self._original, self._name = original, name

    def write(self, text):
        return (getattr(_capture, self._name, None) or self._original).write(text)

    def flush(self):
        (getattr(_capture, self._name, None) or self._original).flush()

    def __getattr__(self, item):
        return getattr(self._original, item)


@contextmanager
def _captured(log):
    """This thread's stdout and stderr go to `log` while inside; other threads keep theirs."""
    with _capture_install:
        for name in ('stdout', 'stderr'):
            if not isinstance(getattr(sys, name), _ThreadRoutedStream):
                setattr(sys, name, _ThreadRoutedStream(getattr(sys, name), name))
    before = getattr(_capture, 'stdout', None), getattr(_capture, 'stderr', None)
    _capture.stdout = _capture.stderr = log
    try:
        yield
    finally:
        _capture.stdout, _capture.stderr = before


def build_deck_header(structure, model_file, section='tt', *, temperature_c=27.0):
    if not model_file.startswith('/') or any(c in model_file for c in '\n\r"'):
        raise ValueError('Model file must be an absolute Spectre-host path')
    if not re.fullmatch(r'[A-Za-z_]\w*', section):
        raise ValueError('Invalid model section')
    if re.search(r'^\s*(include|ahdl_include|simulator|global)\b', structure, re.M):
        raise ValueError('Expected structure-only export')
    if not finite_number(temperature_c) or temperature_c <= -273.15:
        raise ValueError('Invalid simulation temperature')
    return ('simulator lang=spectre\nglobal 0\n'
            + f'include "{model_file}" section={section}\n' + structure + '\n'
            + f'simulatorOptions options reltol=1e-5 vabstol=1e-8 iabstol=1e-13 temp={temperature_c:.12g} tnom=27\n')


def build_deck(structure, model_file, section='tt', *, temperature_c=27.0):
    return (build_deck_header(structure, model_file, section, temperature_c=temperature_c)
            + 'dcOp dc\ndcOpInfo info what=oppoint where=rawfile\n'
            + 'ac ac start=10 stop=1G dec=60\n'
            + 'save VOUT VINP VINN VDD VBIAS XU1.NTAIL XU1.NLOAD VDD:p\n'
            + 'saveOptions options save=allpub\n')


@dataclass(frozen=True)
class BridgeConfig:
    env_file: Path
    library: str
    creation_receipt: Path
    state_root: Path
    model_file: str
    section: str = 'tt'
    profile: str | None = None


class VirtuosoBridgeBackend(VirtuosoBackend):
    """Own a client, serialize project workers, and restore initial widths on close.

    Every cooperating process must use the same state_root. This advisory lock
    cannot lock out manual GUI edits or unrelated bridge scripts. Use a dedicated
    Cadence session, and do not manipulate it while this backend is connected.
    """
    _process_lock = threading.Lock()
    # Condition jobs of one candidate at a time: this is the verified single-owner adapter. A lane backend
    # (native_preparation.NativeCandidateBackend) may allow more; the environment then runs them through `delegated`.
    concurrent_condition_jobs = 1

    def __init__(self, config: BridgeConfig, circuit: Gpdk045OtaProfile):
        self.config, self.circuit = config, circuit
        self.client = None
        self._lock_file = None
        self._owns_process_lock = False
        self._dirty = False
        self._exports = {}
        self._simulator_lock = threading.Lock()      # the per-evaluation recording workspaces run_simulation hands out
        self._op = None
        self.timings = {}
        self._netlist_ready = False                  # OCEAN set up for this testbench (`_export_netlist`)

    def _attach(self):
        from virtuoso_bridge import VirtuosoClient
        from virtuoso_bridge.env import get_runtime_env_file, set_runtime_env_file
        from virtuoso_bridge.profile import resolve_profile
        from virtuoso_bridge.transport.tunnel import SSHClient
        self.bridge_version = importlib.metadata.version('virtuoso-bridge')
        if self.bridge_version != '0.8.0':
            raise RuntimeError('This adapter requires verified bridge 0.8.0; review before upgrading')
        self._prior_env, self._prior_runtime = self._vb_env(), get_runtime_env_file()
        try:
            set_runtime_env_file(self.config.env_file.resolve())
            if resolve_profile(self.config.profile) != self.config.profile:
                raise RuntimeError('Implicit bridge profile binding detected; configure it explicitly')
            if not SSHClient.is_running(self.config.profile):
                raise RuntimeError('Existing bridge tunnel required; automatic startup is disabled')
            return VirtuosoClient.from_env(timeout=30, log_to_ciw=False, profile=self.config.profile)
        finally:
            self._env_after_attach = self._vb_env()

    def connect(self):
        if self.client is not None:
            self._require_connection()
            return
        if not self._process_lock.acquire(blocking=False):
            raise RuntimeError('Another project backend owns this process')
        self._owns_process_lock = True
        started = perf_counter()
        try:
            self.config.state_root.mkdir(parents=True, exist_ok=True)
            self._lock_file = (self.config.state_root / 'session.lock').open('a+')
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            receipt = json.loads(self.config.creation_receipt.read_text())
            for key, expected in [('library', self.config.library),
                                  ('core_cell', self.circuit.design['core_cell']),
                                  ('testbench_cell', self.circuit.design['testbench_cell']),
                                  ('config', self.circuit.design)]:
                if receipt[key] != expected:
                    raise ValueError('Creation receipt does not match the selected test circuit')
            build_deck('', self.config.model_file, self.config.section)
            self._env_hash = digest(self.config.env_file)
            self.client = self._attach()
            self._thread = threading.get_ident()
            self._bound_env = self._vb_env()
            self._check_windows()
            self._initial = self._read_snapshot()
            self._initial_parameters = self.circuit.validate_readback(self._initial)
            self._verify_restored(self._initial, self.circuit.reference)
            self._current = deepcopy(self._initial)
            self.session_id = uuid4().hex
            self.session_dir = self.config.state_root / self.session_id
            self.session_dir.mkdir()
            write_json(self.session_dir / 'initial.json', self._initial)
            self.timings['connect'] = perf_counter() - started
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _vb_env():
        return {k: v for k, v in os.environ.items() if k.startswith('VB_')}

    def delegated(self, call):
        """`call` wrapped to run on a helper thread of this backend's owner - a candidate's condition jobs side by side.
        Inside it run_simulation accepts the helper as the owner; nothing else does."""
        owner = (self._thread, os.getpid())

        def run(*args, **kwargs):
            _delegation.owner = owner
            try:
                return call(*args, **kwargs)
            finally:
                _delegation.owner = None
        return run

    def _delegated_here(self):
        return delegated_owner() is not None and delegated_owner() == (getattr(self, '_thread', None), os.getpid())

    def _require_connection(self, *, delegable=False):
        if self.client is None:
            raise BackendNotConnected('Call connect() before using the real backend')
        if threading.get_ident() != self._thread and not (delegable and self._delegated_here()):
            raise RuntimeError('Use the backend only from its owning thread')
        if digest(self.config.env_file) != self._env_hash or self._vb_env() != self._bound_env:
            raise RuntimeError('Bridge configuration changed during an active session')
        if self.bridge_version == '0.8.0':
            from virtuoso_bridge.env import get_runtime_env_file
            if get_runtime_env_file() != self.config.env_file.resolve():
                raise RuntimeError('Runtime bridge environment binding changed')

    def _check_windows(self):
        conflicts = [w.get('name', '') for w in self.client.list_windows()
                     if any(s in w.get('name', '').lower() for s in
                            ('maestro', 'assembler', 'explorer', 'analog design'))]
        if conflicts:
            raise RuntimeError('Active ADE/Maestro window conflicts with OCEAN export: ' + '; '.join(conflicts))

    def _read_snapshot(self):
        return self.client.schematic.read(self.config.library, self.circuit.design['core_cell'],
                                          include_positions=True, param_filters=None)

    def read_parameters(self):
        self._require_connection()
        return self.circuit.validate_readback(self._read_snapshot())

    def written_parameters(self):
        """The values the last `set_parameters` read back right after writing them, without reading the cell again: a
        second whole-cell read straight after that one added nothing (record 7.137, user decision of 2026-10-01)."""
        self._require_connection()
        return self.circuit.validate_readback(self._current)

    def written_snapshot(self):
        """The whole readback of the last `set_parameters` (record 7.140: what a netlist is built from)."""
        self._require_connection()
        return deepcopy(self._current)

    def read_cdf_snapshot(self):
        """Return a verified full snapshot of the current native candidate."""
        self._require_connection()
        snapshot = self._read_snapshot()
        self._verify_restored(snapshot, self._current)
        return deepcopy(snapshot)

    def _write_widths(self, parameters):
        for device, parameter in self.circuit.writable_keys:
            name = device.split('/')[1]
            length = self.circuit.instances(self._initial)[name]['params']['l']
            set_gpdk_mos(self.client, self.config.library, self.circuit.design['core_cell'],
                         name, format(parameters[device, parameter], '.12g'), length)

    def _verify_restored(self, snapshot, reference):
        self.circuit.validate_readback(snapshot)
        a, b = self.circuit.instances(snapshot), self.circuit.instances(reference)
        for name in {device.split('/')[1] for device, _ in self.circuit.writable_keys}:
            for key in ('w', 'fw', 'l', 'm', 'fingers') + GEOMETRY:
                if not equal(number(a[name]['params'][key]), number(b[name]['params'][key])):
                    raise RuntimeError(f'Restoration mismatch: {name}.{key}')

    def set_parameters(self, parameters):
        self._require_connection()
        self.circuit.validate_assignment(parameters)
        self._check_windows()
        before = self._read_snapshot()
        previous = self.circuit.validate_readback(before)
        self._verify_restored(before, self._current)
        journal = self.session_dir / ('update-' + uuid4().hex + '.json')
        record = {'status': 'pending', 'proposed_parameters': parameter_rows(parameters), 'before': before}
        write_json(journal, record)
        self._dirty = True  # Set before the first remote mutation, including uncertain failures.
        self._op = None
        started = perf_counter()
        try:
            self._write_widths(parameters)
            after = self._read_snapshot()
            record['attempted_readback'] = after
            self.circuit.verify_transition(before, after, parameters)
            self._current = deepcopy(after)
            record.update(status='applied', after=after,
                          applied_parameters=parameter_rows(self.circuit.validate_readback(after)))
        except BaseException as exc:
            record.update(status='update_failed', error=str(exc))
            try:
                self._write_widths(previous)
                after = self._read_snapshot()
                self._verify_restored(after, before)
                self._current = deepcopy(after)
                record.update(status='rolled_back', after=after)
            except BaseException as rollback:
                record.update(status='recovery_required', recovery_error=str(rollback))
                raise RuntimeError(f'Parameter update and restoration failed; inspect {journal}') from rollback
            raise
        finally:
            record['elapsed_seconds'] = perf_counter() - started
            self.timings['parameter_update'] = record['elapsed_seconds']
            write_json(journal, record)

    def restore(self):
        self._require_connection()
        if not self._dirty:
            return
        record = {'status': 'pending'}
        write_json(self.session_dir / 'restoration.json', record)
        try:
            self._write_widths(self._initial_parameters)
            snapshot = self._read_snapshot()
            self._verify_restored(snapshot, self._initial)
            self._current = deepcopy(snapshot)
            self._dirty = False
            self._op = None
            record.update(status='restored', readback=snapshot)
        except BaseException as exc:
            record.update(status='recovery_required', error=str(exc))
            raise
        finally:
            write_json(self.session_dir / 'restoration.json', record)

    def nominal_condition(self):
        return SimulationCondition(self.circuit.nominal_corner)

    def validate_condition(self, condition):
        self.circuit.validate_condition(condition or self.nominal_condition())

    def _skill(self, text, timeout=120):
        answer = self.client.execute_skill(text, timeout=timeout)
        if not answer.ok:
            raise RuntimeError('SKILL failed: ' + ('; '.join(str(e) for e in answer.errors or []) or str(answer.output)))
        text = (answer.output or '').strip()
        if len(text) >= 2 and text[0] == text[-1] == '"':
            return bytes(text[1:-1], 'utf-8').decode('unicode_escape')
        return text

    def _export_netlist(self, output_dir):
        """Virtuoso's own netlister, its package downloaded into `output_dir`. The bridge's export sets OCEAN up again on
        every call (simulator, design, a library refresh): 0.27 s per export where `createNetlist` alone takes 0.18 s
        (record 7.140). A client that can run SKILL and download files therefore sets OCEAN up once and then only
        netlists (record 7.142, user decision of 2026-10-02); when the netlist it returns is not this testbench's -
        something else set OCEAN to another design meanwhile - it sets up again. A task measured inside the Virtuoso
        session shares OCEAN with that measurement and keeps the bridge's export, as does a client without those calls."""
        library, testbench = self.config.library, self.circuit.design['testbench_cell']
        if (getattr(self.circuit, 'measures_in_virtuoso', False) or not callable(getattr(self.client, 'execute_skill', None))
                or not callable(getattr(self.client, 'download_file', None))):
            return self.client.schematic.export_netlist(library, testbench, output_dir, timeout=120)
        for _ in range(2):
            if not self._netlist_ready:
                self._skill(f"progn(simulator('spectre) design({json.dumps(library)} {json.dumps(testbench)} \"schematic\" \"r\") t)")
                self._netlist_ready = True
            source = self._skill('let((r) r = createNetlist(?recreateAll t ?display nil) when(r simplifyFilename(r)))')
            if source.startswith('/') and f'/{testbench}/' in source:
                break
            self._netlist_ready = False
        else:
            raise RuntimeError(f'createNetlist did not netlist {library}/{testbench}: {source!r}')
        result = self.client.download_file(source.rsplit('/', 1)[0], output_dir, timeout=120, recursive=True)
        if not (output_dir / 'input.scs').is_file() or not (output_dir / 'netlist').is_file():
            raise RuntimeError(f'The netlist package did not download: {result}')
        return {'input_file': str(output_dir / 'input.scs')}

    def generate_netlist(self, work_root, *, condition=None, just_written=False, built=None):
        # Preflight unsupported MC/voltage requests before any remote operation.
        if condition is None:
            corner = self.circuit.nominal_corner
            if self.config.section != corner.model_section:
                corner = PVTCorner('configured_corner', self.config.section, corner.temperature_c, corner.supply_v)
                condition = SimulationCondition(corner, 'pvt_validation')
            else:
                condition = self.nominal_condition()
        self.validate_condition(condition)
        self._require_connection()
        if just_written:
            # Straight after `set_parameters`, which checked the windows and read the cell before and after its write in
            # the same transaction: the cell is that readback. The export is still checked against it, and the read after
            # the export still proves the cell holds it (record 7.137, user decision of 2026-10-01).
            started = perf_counter()
            snapshot = deepcopy(self._current)
        else:
            self._check_windows()
            started = perf_counter()
            snapshot = self._read_snapshot()
            self._verify_restored(snapshot, self._current)
        job_id = uuid4().hex
        directory = Path(work_root).resolve() / job_id
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / 'readback.json', snapshot)
        if built is not None:
            # The netlist built from the write's readback (record 7.142): no export, and nothing done in Virtuoso since
            # that readback, so nothing to read again. It is held to the cell exactly as an export is.
            if not just_written:
                raise ValueError('A built netlist follows the readback of its own write')
            structure = directory / 'package' / 'netlist'
            structure.parent.mkdir()
            structure.write_text(built)
            parameters = self.circuit.validate_export(structure, snapshot)
        else:
            with (directory / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
                exported = self._export_netlist(directory / 'package')
            structure = Path(exported['input_file']).parent / 'netlist'
            parameters = self.circuit.validate_export(structure, snapshot)
            self._verify_restored(self._read_snapshot(), snapshot)
        original_structure = structure
        prepared = self.circuit.structure_for_condition(structure.read_text(), condition)
        # Keep the raw export as evidence; the graph reflects the executed supply.
        structure = directory / 'conditioned_structure.scs'
        structure.write_text(prepared)
        deck = directory / getattr(self.circuit, 'deck_name', 'opamp.scs')
        corner = condition.corner
        builder = getattr(self.circuit, 'build_deck', build_deck)
        deck.write_text(builder(prepared, self.config.model_file, corner.model_section,
                               temperature_c=corner.temperature_c))
        self.timings['netlisting'] = perf_counter() - started
        artifact = NetlistArtifact(deck, job_id, digest(deck), 'real', condition)
        metadata = {'job_id': job_id, 'origin': 'real', 'bridge_version': self.bridge_version,
                    'library': self.config.library, 'cell': self.circuit.design['testbench_cell'],
                    'section': corner.model_section, 'temperature_c': corner.temperature_c,
                    'supply_v': corner.supply_v, 'condition': asdict(condition),
                    'condition_fingerprint': condition.fingerprint, 'model_file': self.config.model_file,
                    'original_structure_path': str(original_structure.resolve()),
                    'original_structure_sha256': digest(original_structure),
                    'netlist_source': 'built from the readback' if built is not None else 'native export',
                    'source_sha256': digest(structure), 'executed_sha256': artifact.sha256,
                    'structure_path': str(structure.resolve()),
                    'applied_parameters': parameter_rows(parameters), 'timings': dict(self.timings),
                    'files': {str(p.relative_to(directory)): digest(p) for p in directory.rglob('*') if p.is_file()}}
        if hasattr(self.circuit, 'analysis_settings'):
            metadata['analysis_settings'] = self.circuit.analysis_settings
        write_json(directory / 'manifest.json', metadata)
        self._exports[job_id] = (artifact, deepcopy(parameters), metadata)
        return artifact

    def derive_condition_artifact(self, base, work_root, *, condition):
        self.validate_condition(condition)
        self._require_connection()
        saved, parameters, metadata = self._exports.get(base.job_id, (None, None, None))
        if saved != base or base.origin != 'real' or base.condition != self.nominal_condition():
            raise ValueError('Derivation requires this candidate\'s registered nominal export')
        if condition.purpose != 'pvt_training' or condition.monte_carlo is not None:
            raise UnsupportedCapability('Derived candidate decks require a deterministic training condition')
        if digest(base.path) != base.sha256:
            raise ValueError('Nominal deck changed before derivation')
        original = Path(metadata['original_structure_path'])
        if digest(original) != metadata['original_structure_sha256']:
            raise ValueError('Original native export changed before derivation')
        self.circuit.validate_assignment(parameters)
        prepared = self.circuit.structure_for_condition(original.read_text(), condition)
        job_id = uuid4().hex
        directory = Path(work_root).resolve() / job_id
        directory.mkdir(parents=True, exist_ok=False)
        structure = directory / 'conditioned_structure.scs'
        structure.write_text(prepared)
        deck = directory / getattr(self.circuit, 'deck_name', 'opamp.scs')
        corner = condition.corner
        builder = getattr(self.circuit, 'build_deck', build_deck)
        deck.write_text(builder(prepared, self.config.model_file, corner.model_section, temperature_c=corner.temperature_c))
        artifact = NetlistArtifact(deck, job_id, digest(deck), 'real', condition)
        derived = dict(metadata, job_id=job_id, derived_from_export_job_id=base.job_id,
                       section=corner.model_section, temperature_c=corner.temperature_c, supply_v=corner.supply_v,
                       condition=asdict(condition), condition_fingerprint=condition.fingerprint,
                       source_sha256=digest(structure), executed_sha256=artifact.sha256,
                       structure_path=str(structure),
                       files={p.name: digest(p) for p in (structure, deck)})
        write_json(directory / 'manifest.json', derived)
        self._exports[job_id] = (artifact, deepcopy(parameters), derived)
        return artifact

    def get_circuit_graph(self, artifact):
        self._require_connection()
        saved, _, metadata = self._exports.get(artifact.job_id, (None, None, None))
        if saved != artifact or digest(artifact.path) != artifact.sha256:
            raise ValueError('Unknown or modified netlist artifact')
        structure = Path(metadata['structure_path'])
        if digest(structure) != metadata['source_sha256']:
            raise ValueError('Exported structure changed after validation')
        graph = self.circuit.optimization_graph(structure)
        graph.metadata['simulation_condition'] = asdict(artifact.condition)
        return graph

    def _raw_format(self):
        """The Spectre results format asked for. A circuit measured inside the Virtuoso session (OCEAN,
        `measures_in_virtuoso`) never reads its results here, so it keeps Spectre's own binary format and the bridge skips
        parsing the downloaded text (user decision of 2026-09-30: about 0.45 s of a Maestro-measured evaluation)."""
        return None if getattr(self.circuit, 'measures_in_virtuoso', False) else 'psfascii'

    def _new_simulator(self, work_dir, timeout):
        if getattr(self, '_recording_scratch', None) is not None:
            if self._recording_scratch_used:
                from analog_optimizer.recording.remote import BridgeScratch
                recorder, eval_id = self._recording_binding
                self._recording_scratch = BridgeScratch(recorder, eval_id, profile=self.config.profile)
                self._recording_workspaces.append(self._recording_scratch)
            self._recording_scratch_used = True
            return self._recording_scratch.simulator(work_dir, math.ceil(timeout), output_format=self._raw_format())
        from virtuoso_bridge.spectre.runner import SpectreSimulator
        return SpectreSimulator.from_env(work_dir=work_dir, timeout=math.ceil(timeout),
                                        output_format=self._raw_format(), spectre_args=[], keep_remote_files=True,
                                        profile=self.config.profile)

    def prepare_recording(self, recorder, eval_id):
        from analog_optimizer.recording.remote import BridgeScratch
        self._recording_scratch = BridgeScratch(recorder, eval_id, profile=self.config.profile)
        self._recording_binding = (recorder, eval_id)
        self._recording_scratch_used = False
        self._recording_workspaces = [self._recording_scratch]

    def finish_recording(self, receipt):
        if getattr(self, '_recording_scratch', None) is not None:
            for workspace in self._recording_workspaces:
                workspace.cleanup(receipt)
            self._recording_workspaces = []
            self._recording_scratch = None

    def run_simulation(self, request: SimulationRequest):
        condition = request.condition or request.netlist.condition
        self.validate_condition(condition)
        # A helper thread of the owner may run this (condition jobs side by side, `delegated`): it touches no Virtuoso
        # session, only this candidate's exports, a fresh job folder and a simulator of its own.
        self._require_connection(delegable=True)
        owner_thread = not self._delegated_here()
        if request.analysis:
            raise UnsupportedCapability('Only the analyses prepared by the circuit profile are supported')
        artifact, applied, metadata = self._exports.get(request.netlist.job_id, (None, None, None))
        if artifact != request.netlist or artifact is None or digest(artifact.path) != artifact.sha256:
            raise ValueError('Unknown or modified netlist artifact')
        if request.parameters and (request.parameters.keys() != applied.keys() or
                                   any(not equal(v, applied[k]) for k, v in request.parameters.items())):
            raise ValueError('Requested parameters differ from the values verified in this export')
        if owner_thread:                               # side by side, each result carries its own operating points
            self._op = None
        started = perf_counter()
        job_id = uuid4().hex
        job = Path(request.work_root).resolve() / job_id
        job.mkdir(parents=True, exist_ok=False)
        deck = job / getattr(self.circuit, 'deck_name', 'opamp.scs')
        deck.write_bytes(artifact.path.read_bytes())
        if digest(deck) != artifact.sha256:
            raise ValueError('Netlist changed while preparing the simulation')
        manifest = {**metadata, 'job_id': job_id, 'export_job_id': artifact.job_id,
                    'proposed_parameters': parameter_rows(request.parameters),
                    'required_metrics': request.required_metrics, 'timeout_seconds': request.timeout_seconds}
        write_json(job / 'manifest.json', manifest)
        metrics, units, validity = {}, {}, {}
        evaluated, retryable = False, False
        status, reason = SimulationStatus.BACKEND_ERROR, 'unclassified_bridge_failure'
        invocations, error_summary, operating_points = None, '', None
        try:
            with self._simulator_lock:
                simulator = self._new_simulator(job / 'results', request.timeout_seconds)
            with (job / 'bridge.log').open('w') as log, _captured(log):
                raw = simulator.run_simulation(deck)  # Never pass sizing assignments as bridge params.
            # An intended command is not proof of execution: Bridge also returns
            # it when upload/transport fails before launching Spectre.
            error_summary = '\n'.join(map(str, raw.errors))[-16384:]
            write_json(job / 'bridge_result.json', {**manifest, 'status': raw.status.value,
                       'errors': raw.errors, 'metadata': raw.metadata})
            if not raw.ok:
                # The upstream diagnostic string alone is insufficient to blame a candidate.
                status, reason = SimulationStatus.BACKEND_ERROR, 'bridge_reported_failure'
            else:
                try:
                    analyzer = getattr(self.circuit, 'analyze', analyze)
                    measured = analyzer(job, result_name='bridge_result.json', mos_names=self.circuit.mos_names)
                    metrics, units, validity = (measured[k] for k in ('metrics', 'metric_units', 'metric_validity'))
                    operating_points = measured['operating_points']
                    for key in request.required_metrics:
                        metrics.setdefault(key, None)
                        units.setdefault(key, 'unspecified')
                        validity.setdefault(key, False)
                    evaluated = True
                    required = request.required_metrics or tuple(metrics)
                    if not required or not all(validity[k] for k in required):
                        raise ValueError('A required metric is missing or invalid')
                    if owner_thread:
                        self._op = operating_points
                    status, reason = SimulationStatus.OK, 'validated_spectre_completion'
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    status, reason = SimulationStatus.MEASUREMENT_ERROR, 'measurement_validation_failed'
                    write_json(job / 'measurement_error.json', {'error': str(exc)})
        except TimeoutError as exc:
            error_summary = str(exc)
            status, reason, retryable = SimulationStatus.TIMEOUT, 'python_timeout', True
            write_json(job / 'exception.json', {'type': type(exc).__name__, 'error': str(exc)})
        except Exception as exc:
            error_summary = str(exc)
            write_json(job / 'exception.json', {'type': type(exc).__name__, 'error': str(exc)})
        elapsed = perf_counter() - started
        simulator_version = None
        log_path = job / 'results' / 'spectre.out'
        if log_path.is_file():
            with log_path.open(errors='replace') as stream:
                header = stream.read(8192)
            version = re.search(r'(?im)^\s*(?:Spectre\s+.*?\s+)?Version\s+([^\r\n]+)', header)
            if version:
                simulator_version = version.group(1).strip()
            if re.search(r'(?i)Spectre.*Circuit Simulator', header):
                invocations = 1
        result = SimulationResult(job_id, 'virtuoso_bridge', 'real', status, reason, retryable,
                                  evaluated, metrics, units, validity, applied, job, elapsed, condition,
                                  simulator_invocations=invocations, error_summary=error_summary,
                                  simulator_version=simulator_version, operating_points=operating_points)
        serialized = asdict(result)
        serialized['applied_parameters'] = parameter_rows(applied)
        serialized['netlist_sha256'] = artifact.sha256
        write_json(job / 'result.json', serialized)
        return result

    def get_operating_points(self):
        self._require_connection()
        if self._op is None:
            raise UnsupportedCapability('No validated operating points from the latest evaluation')
        return deepcopy(self._op)

    def close(self):
        try:
            if self.client is not None and self._dirty:
                self.restore()
        finally:
            try:
                if self.client is not None:
                    self.client.close()  # Upstream close preserves the shared tunnel; never call stop().
            finally:
                self.client = None
                if hasattr(self, '_prior_env'):
                    from virtuoso_bridge.env import get_runtime_env_file, set_runtime_env_file
                    if get_runtime_env_file() == self.config.env_file.resolve():
                        set_runtime_env_file(self._prior_runtime)
                    # Do not overwrite an unrelated caller's subsequent environment changes.
                    for key in self._prior_env.keys() | self._env_after_attach.keys():
                        if os.environ.get(key) == self._env_after_attach.get(key):
                            if key in self._prior_env:
                                os.environ[key] = self._prior_env[key]
                            else:
                                os.environ.pop(key, None)
                    del self._prior_env
                if self._lock_file is not None:
                    self._lock_file.close()
                    self._lock_file = None
                if self._owns_process_lock:
                    self._process_lock.release()
                    self._owns_process_lock = False
