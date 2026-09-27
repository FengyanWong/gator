"""The ngspice evaluation backend: the optimizer's backend contract over a deck that ngspice runs.

``NgspiceBackend`` implements ``analog_optimizer.backends.backend.VirtuosoBackend`` (the abstraction every
backend of the optimizer speaks, despite its name) for an ngspice netlist task (``ngspice_tasks``):

* the deck of each candidate = the task's netlist with the candidate's sizes written into their own tokens
  (``ngspice_netlist.deck_text``), saved in the job's folder and re-read to prove the write (``get_circuit_graph``);
* the simulation = ONE ``ngspice -b`` process per evaluation, on this machine (the deck's folder is the working
  directory; relative ``.include`` paths were made absolute) or on another machine through ``ssh`` (the deck goes
  in on stdin into a ``mktemp -d`` folder that the same command removes; paths in the deck are that machine's);
* the results = the ``<name> = <value>`` lines ngspice prints for ``.meas`` statements and ``print`` commands,
  read for the names the task knows (``ngspice_netlist.read_results``). A measurement ngspice reports as failed
  is missing, never a number; a solver failure (timestep too small, singular matrix...) is a NONCONVERGED design
  that was evaluated; a deck error, a missing program or a broken ssh link is an infrastructure failure that
  evaluated nothing.

Origin ``real``: these are circuit simulations, not the analytic toy (``synthetic``). They cost no license and no
Virtuoso budget, but they are counted, authorized and recorded exactly as real evaluations are, so a run's data is
never mistaken for mock data. The nominal condition is what the deck states: its temperature (``.temp`` /
``.option temp``, else 27 C) and its largest DC voltage source (the supply), recorded with every evaluation.

The ssh destination and the program come from the operator's connection file (``ngspice_link`` validates both
patterns before anything runs) and are passed as argv entries, never through a shell on this machine.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from time import perf_counter
from uuid import uuid4

from analog_optimizer.backends.backend import (BackendNotConnected, NetlistArtifact, SimulationResult, SimulationStatus,
                                               UnsupportedCapability, VirtuosoBackend)
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.measurements.specs import RewardSettings

from . import ngspice_netlist
from .ngspice_link import PROGRAM, SSH_HOST, ssh_argv

BACKEND_KIND = 'ngspice-batch-v1'
LOCAL_CONCURRENCY = max(1, min(8, (os.cpu_count() or 2) // 2))     # ngspice jobs on this machine at once
SSH_CONCURRENCY = 4                                                 # ssh sessions at once
SSH_COMMAND_SECONDS = 20                                            # on top of the simulation timeout: connect + copy
VERSION = re.compile(r'ngspice-(\d+(?:\.\d+)*)')
TEMPERATURE = re.compile(r'(?im)^\s*\.(?:temp\s+([-+0-9.eE]+)|options?\b.*?\btemp\s*=\s*([-+0-9.eE]+))')


class NgspiceLinkError(ValueError):
    """The connection settings cannot run ngspice (wrong kind, an invalid program or host)."""


@dataclass(frozen=True)
class NgspiceLink:
    """How ngspice is reached: the settings of an ngspice connection profile, validated."""
    kind: str                    # ngspice_local | ngspice_ssh
    program: str = 'ngspice'
    ssh_host: str | None = None

    @classmethod
    def from_settings(cls, settings) -> 'NgspiceLink':
        settings = settings or {}
        kind = settings.get('kind')
        if kind not in ('ngspice_local', 'ngspice_ssh'):
            raise NgspiceLinkError(f'the connection is {str(kind)[:40]!r}, not an ngspice connection')
        program = settings.get('ngspice_bin') or 'ngspice'
        if not isinstance(program, str) or not PROGRAM.match(program):
            raise NgspiceLinkError('"ngspice_bin" of the connection is not a plain program name or path')
        host = settings.get('ssh_host')
        if kind == 'ngspice_ssh' and (not isinstance(host, str) or not SSH_HOST.match(host)):
            raise NgspiceLinkError('"ssh_host" of the connection is not a Host name or user@host')
        return cls(kind, program, host if kind == 'ngspice_ssh' else None)

    @property
    def remote(self) -> bool:
        return self.kind == 'ngspice_ssh'

    @property
    def max_concurrency(self) -> int:
        return SSH_CONCURRENCY if self.remote else LOCAL_CONCURRENCY

    @property
    def label(self) -> str:
        return 'ngspice over SSH' if self.remote else 'ngspice on this machine'


def remote_run_command(program):
    """One fixed remote command: the deck arrives on stdin into a temporary folder that is removed again, whatever
    the outcome. `program` passed PROGRAM, so it needs no quoting."""
    return (f'd=$(mktemp -d) && cat > "$d/deck.cir" && cd "$d" && {program} -b deck.cir; s=$?; cd / ; rm -rf "$d"; exit $s')


class RealRunner:
    """The processes of a run. argv arrays only; no shell on this machine. `timeout` ends a job that hangs."""
    def local(self, program, deck: Path, timeout):
        located = shutil.which(program) if not os.path.isabs(program) else program
        if not located or not os.access(located, os.X_OK):
            raise FileNotFoundError(f'`{program}` is not an executable on the PATH of the run worker')
        done = subprocess.run([located, '-b', deck.name], capture_output=True, text=True, timeout=timeout, shell=False,
                              cwd=str(deck.parent), stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout or '', done.stderr or ''

    def remote(self, host, program, deck_text, timeout):
        if not shutil.which('ssh'):
            raise FileNotFoundError('no `ssh` on the PATH of the run worker')
        done = subprocess.run(ssh_argv(host, remote_run_command(program)), input=deck_text, capture_output=True, text=True,
                              timeout=timeout + SSH_COMMAND_SECONDS, shell=False)
        return done.returncode, done.stdout or '', done.stderr or ''


def deck_condition(text) -> SimulationCondition:
    """The nominal condition a deck states: its temperature and its largest DC voltage source."""
    temperature = 27.0
    match = TEMPERATURE.search(text)
    if match:
        try:
            temperature = float(match.group(1) or match.group(2))
        except ValueError:
            pass
    supply = 0.0
    for line in text.splitlines():
        words = line.split()
        if not words or words[0][:1].lower() != 'v':
            continue
        values = [w for w in words[3:] if ngspice_netlist.number(w) is not None]
        lowered = [w.lower() for w in words]
        if 'dc' in lowered and lowered.index('dc') + 1 < len(words):
            value = ngspice_netlist.number(words[lowered.index('dc') + 1])
        else:
            value = ngspice_netlist.number(values[0]) if values else None
        if value is not None:
            supply = max(supply, abs(value))
    return SimulationCondition(PVTCorner('nominal', 'nominal', temperature, supply if supply > 0 else 1.0))


class NgspiceBackend(VirtuosoBackend):
    """One deck, one connection; sizes set and read back through the deck's own tokens."""
    def __init__(self, text, graph, link: NgspiceLink, *, units=None, device_kinds=None, include_root=None,
                 circuit_id='ngspice', runner=None, source='<task>'):
        graph.validate()
        self.text, self.link, self.units = text, link, dict(units or {})
        self.device_kinds, self.include_root, self.circuit_id, self.source = dict(device_kinds or {}), include_root, circuit_id, source
        self.parsed = ngspice_netlist.parse_text(text, source=source, circuit_id=circuit_id, device_kinds=self.device_kinds,
                                                include_root=include_root)
        self.graph = deepcopy(graph)
        self.condition = deck_condition(text)
        self.runner = runner or RealRunner()
        self.initial = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
        self.parameters, self.exports = dict(self.initial), {}
        self.connected, self.calls, self.version = False, 0, None
        self.timings = {}
        for key in self.initial:
            if key not in self.parsed.by_source:
                raise ValueError(f'{key[0]}.{key[1]} is not a value this netlist can write')

    # ---------------------------------------------------------------- the contract
    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def _check(self):
        if not self.connected:
            raise BackendNotConnected('ngspice backend is not connected')

    def nominal_condition(self):
        return self.condition

    def validate_condition(self, condition):
        if condition is not None and condition != self.condition:
            raise UnsupportedCapability('The ngspice backend runs the deck as written: only its own nominal condition')

    def restore(self):
        self._check()
        self.parameters = dict(self.initial)

    def read_parameters(self):
        self._check()
        return dict(self.parameters)

    def set_parameters(self, parameters):
        self._check()
        if parameters.keys() != self.initial.keys() or not all(math.isfinite(v) for v in parameters.values()):
            raise ValueError('Unexpected ngspice parameter assignment')
        self.parameters = dict(parameters)

    def deck(self, parameters=None) -> str:
        """The deck for `parameters` (default: the current ones)."""
        assignments = dict(self.parameters if parameters is None else parameters)
        text, _ = ngspice_netlist.deck_text(self.parsed, assignments, include_root=self.include_root,
                                            absolute_includes=not self.link.remote)
        return text

    def generate_netlist(self, work_root, *, condition=None):
        self._check()
        self.validate_condition(condition)
        started = perf_counter()
        job_id = uuid4().hex
        directory = Path(work_root) / job_id
        directory.mkdir(parents=True)
        path = directory / 'deck.cir'
        path.write_text(self.deck(), encoding='utf8')
        artifact = NetlistArtifact(path, job_id, hashlib.sha256(path.read_bytes()).hexdigest(), 'real', self.condition)
        self.exports[job_id] = (artifact, dict(self.parameters))
        self.timings['netlisting'] = perf_counter() - started
        return artifact

    def get_circuit_graph(self, artifact):
        """The written deck read again: the same circuit, the new values - proof that the write landed."""
        self._check()
        saved, values = self.exports[artifact.job_id]
        if artifact != saved or hashlib.sha256(artifact.path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError('ngspice deck identity changed')
        again = ngspice_netlist.parse_text(artifact.path.read_text(encoding='utf8'), source=self.source, circuit_id=self.circuit_id,
                                           device_kinds=self.device_kinds, include_root=self.include_root, scan_includes=False)
        graph = deepcopy(self.graph)
        for i, group in enumerate(graph.parameter_groups):
            if not group.mutable:
                continue
            for member in group.members:
                old = graph.parameters[member.device_id][member.parameter]
                key = (member.device_id, old.source_name or member.parameter)
                read = again.graph.parameters.get(member.device_id, {}).get(member.parameter)
                if read is None or not read.valid or not math.isclose(read.value, values[key], rel_tol=1e-9, abs_tol=1e-30):
                    raise ValueError(f'{member.device_id}.{member.parameter} did not read back from the written deck')
                graph.parameters[member.device_id][member.parameter] = replace(old, value=read.value, raw=read.raw)
            graph.parameter_groups[i] = replace(group, value=values[key] / member.ratio)
        graph.validate()
        return graph

    def run_simulation(self, request):
        self._check()
        self.validate_condition(request.condition)
        started = perf_counter()
        exported = self.exports[request.netlist.job_id][1]
        if request.parameters != exported:
            raise ValueError('ngspice request parameters differ from the export')
        directory = request.work_root / uuid4().hex
        directory.mkdir(parents=True)
        deck = request.netlist.path
        wanted = list(dict.fromkeys([*self.parsed.result_names, *request.required_metrics]))
        self.calls += 1
        status, reason, retryable, evaluated, invocations = SimulationStatus.OK, 'ngspice_batch', False, True, 1
        code, out, err = None, '', ''
        try:
            if self.link.remote:
                code, out, err = self.runner.remote(self.link.ssh_host, self.link.program, deck.read_text(encoding='utf8'),
                                                    request.timeout_seconds)
            else:
                code, out, err = self.runner.local(self.link.program, deck, request.timeout_seconds)
        except subprocess.TimeoutExpired:
            status, reason, retryable, evaluated, invocations = SimulationStatus.TIMEOUT, 'ngspice_timeout', True, False, 1
        except FileNotFoundError as exc:
            status, reason, retryable, evaluated, invocations = SimulationStatus.TRANSPORT_ERROR, 'program_not_found', True, False, 0
            err = str(exc)
        except OSError as exc:
            status, reason, retryable, evaluated, invocations = SimulationStatus.TRANSPORT_ERROR, 'launch_failed', True, False, 0
            err = f'{type(exc).__name__}: {exc}'
        (directory / 'ngspice.log').write_text(f'# exit code: {code}\n# stdout:\n{out}\n# stderr:\n{err}\n', encoding='utf8')
        version = VERSION.search(out + '\n' + err)
        self.version = version.group(1) if version else self.version
        found = ngspice_netlist.read_results(out, wanted) if status == SimulationStatus.OK else {}
        summary = ''
        if status == SimulationStatus.OK:
            if self.link.remote and code == 255:
                status, reason, retryable, evaluated, invocations = SimulationStatus.TRANSPORT_ERROR, 'ssh_failed', True, False, 0
                summary = _scrub(_last_line(err) or 'ssh ended with exit code 255', self.link.ssh_host)
            elif code in (126, 127) and self.link.remote:
                status, reason, retryable, evaluated, invocations = SimulationStatus.TRANSPORT_ERROR, 'program_not_found', True, False, 0
                summary = _scrub(_last_line(err) or f'exit code {code}', self.link.ssh_host)
            else:
                failure, evidence = ngspice_netlist.classify_failure(out, err, code)
                if failure == 'nonconverged':
                    status, reason, evaluated = SimulationStatus.NONCONVERGED, 'ngspice_nonconverged', True
                    summary = evidence
                elif failure == 'deck_error':
                    status, reason, evaluated = SimulationStatus.BACKEND_ERROR, 'ngspice_deck_error', False
                    summary = evidence
                elif failure == 'measurement_error' and not found:
                    status, reason = SimulationStatus.MEASUREMENT_ERROR, 'ngspice_measurement_failed'
                    summary = evidence
                elif not found and wanted:
                    status, reason = SimulationStatus.MEASUREMENT_ERROR, 'no_results_printed'
                    summary = 'ngspice printed none of the results the task reads: ' + ', '.join(wanted[:8])
        metrics = {name: found.get(name) for name in wanted}
        units = {name: self.units.get(name) or self.parsed.units.get(name) or '1' for name in wanted}
        validity = {name: name in found for name in wanted}
        return SimulationResult(directory.name, BACKEND_KIND, 'real', status, reason, retryable, evaluated, metrics, units,
                                validity, dict(exported), directory, perf_counter() - started, condition=self.condition,
                                simulator_invocations=invocations, error_summary=summary[:400],
                                simulator_version=f'ngspice-{self.version}' if self.version else None)


def _last_line(text):
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    return lines[-1] if lines else ''


def _scrub(text, host):
    """The ssh destination never leaves in an error summary."""
    for secret in sorted({part for part in [host, *str(host or '').split('@')] if part}, key=len, reverse=True):
        text = text.replace(secret, '<ssh host>')
    return text


@dataclass(frozen=True)
class NgspiceEnvFactory:
    """Picklable: builds the optimizer's environment around an NgspiceBackend inside a lane (a worker process)."""
    text: str
    graph: object                    # the compiled graph: the configured parameter groups over the task's circuit
    specs: tuple
    link: NgspiceLink
    work_root: str
    max_steps: int
    timeout_seconds: float
    stop_on_success: bool
    units: dict                      # result name -> the unit the configuration declares for it (canonical)
    device_kinds: dict
    include_root: str | None
    circuit_id: str
    source: str
    plan: object = None              # spec_equations.SpecPlan: computed specs added to every result
    reward_settings: RewardSettings = field(default_factory=RewardSettings)

    def __call__(self, lane):
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        backend = NgspiceBackend(self.text, self.graph, self.link, units=self.units, device_kinds=self.device_kinds,
                                 include_root=self.include_root, circuit_id=self.circuit_id, source=self.source)
        if self.plan is not None:
            self.plan.wrap(backend)
        return CircuitSizingEnv(backend, self.graph, self.specs, Path(self.work_root) / f'worker-{lane}',
                                max_steps=self.max_steps, timeout_seconds=self.timeout_seconds,
                                stop_on_success=self.stop_on_success, expected_origin='real',
                                reward_settings=self.reward_settings)
