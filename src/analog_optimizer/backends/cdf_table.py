"""Finite, export-verified GPDK045 CDF table and immutable Python netlists.

Only the existing matched input-pair width is supported. No geometry formula is
inferred: every row comes from actual CDF callbacks and a matching native export.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
from time import perf_counter
from uuid import uuid4

from .backend import BackendNotConnected, NetlistArtifact, UnsupportedCapability
from .gpdk045 import GEOMETRY, number, equal
from .virtuoso_bridge import VirtuosoBridgeBackend, build_deck, digest, write_json, parameter_rows

SCHEMA = 'gpdk045-cdf-table-v1'


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()


def profile_contract(profile):
    return content_hash(dict(design=profile.design, reference=profile.reference,
                             mapping=asdict(profile.parser.config), conditions=profile.condition_config,
                             graph=asdict(profile.graph), bounds=profile.width_bounds, step=profile.width_step))


def width_grid(profile):
    low, high, step = map(lambda x: Decimal(str(x)), (*profile.width_bounds, profile.width_step))
    count = (high - low) / step
    if count != int(count) or count > 10000:
        raise ValueError('Finite CDF table requires an exact grid of at most 10001 values')
    return [float(low + i * step) for i in range(int(count) + 1)]


def render_structure(template, snapshot, profile):
    """Replace explicit numeric fields on exactly M1/M2, preserving all syntax.

    This is a deliberately narrow editor for the verified OTA export, not a
    general Spectre netlister. The parser subsequently validates the whole deck.
    """
    profile.validate_readback(snapshot)
    instances = profile.instances(snapshot)
    for name in ('M1', 'M2'):
        # Split logical lines explicitly so continuation handling cannot touch
        # another device.
        lines = template.splitlines(keepends=True)
        matches = [i for i, line in enumerate(lines) if re.match(r'^\s*' + name + r'\s+\(', line)]
        if len(matches) != 1:
            raise ValueError(f'Expected one template statement for {name}')
        start = end = matches[0]
        while lines[end].rstrip().endswith('\\'):
            end += 1
            if end >= len(lines):
                raise ValueError('Unterminated template continuation')
        statement = ''.join(lines[start:end + 1])
        params = instances[name]['params']
        for key in ('w',) + GEOMETRY:
            value = number(params[key])
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'Invalid CDF field {name}.{key}')
            token = r'(\b' + key + r'\s*=\s*)(?:\([^()\n]*\)|[^\s\\]+)'
            statement, count = re.subn(token, lambda m: m[1] + format(value, '.15g'), statement)
            if count != 1:
                raise ValueError(f'Expected one explicit template field {name}.{key}')
        lines[start:end + 1] = [statement]
        template = ''.join(lines)
    return template


def structures_equal(profile, a, b):
    """Compare complete semantic graphs, including every exported parameter."""
    x, y = profile.parser.parse_text(a), profile.parser.parse_text(b)
    x.validate()
    y.validate()
    devices = lambda g: sorted((d.id, d.kind, d.model_ref, d.terminals) for d in g.devices)
    if (devices(x), x.nets, x.connections) != (devices(y), y.nets, y.connections):
        return False
    if x.parameters.keys() != y.parameters.keys():
        return False
    for device, params in x.parameters.items():
        if params.keys() != y.parameters[device].keys():
            return False
        for key, p in params.items():
            q = y.parameters[device][key]
            if p.valid != q.valid or (not equal(p.value, q.value) if p.valid else p.raw != q.raw):
                return False
    return True


# Run on the Spectre host. Only the aggregate digest leaves that host; no PDK
# source is copied. Lock files are transient and not part of a PDK version.
_FINGERPRINT_SCRIPT = '''import hashlib,json,os,sys
root=os.path.realpath(sys.argv[1])
if not os.path.isdir(root): raise RuntimeError("PDK root does not exist")
h=hashlib.sha256(); count=0
paths=[]
for base,dirs,files in os.walk(root):
 for name in files:
  p=os.path.join(base,name)
  if os.path.isfile(p) and not any(x in name for x in (".cdslck", ".lock")): paths.append(p)
for p in sorted(paths):
 h.update(os.path.relpath(p,root).encode("utf-8")+b"\\0")
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(1048576),b""): h.update(block)
 count+=1
if not count: raise RuntimeError("Empty PDK root")
print(json.dumps({"root":str(root),"sha256":h.hexdigest(),"files":count}))
'''


def pdk_fingerprint(root, *, profile=None):
    """Hash the explicitly selected PDK tree on the configured Spectre host."""
    from virtuoso_bridge.transport.remote_roles import remote_host_roles_from_os
    from virtuoso_bridge.transport.tunnel import SSHClient
    roles = remote_host_roles_from_os(profile)
    if roles.spectre_host in ('localhost', '127.0.0.1', '::1'):
        result = subprocess.run(['python3', '-c', _FINGERPRINT_SCRIPT, str(root)],
                                capture_output=True, text=True, timeout=120, check=True)
    else:
        if not SSHClient.is_running(profile):
            raise RuntimeError('Existing bridge tunnel required for PDK provenance check')
        client = SSHClient.from_env(profile=profile)
        runner = client.spectre_runner
        if runner is None:
            raise RuntimeError('Spectre-host SSH runner unavailable')
        arguments = ' -c ' + shlex.quote(_FINGERPRINT_SCRIPT) + ' ' + shlex.quote(str(root))
        command = ('if command -v python3 >/dev/null 2>&1; then python3' + arguments +
                   '; else python' + arguments + '; fi')
        result = runner.run_command(command, timeout=120)
        if result.returncode != 0:
            raise RuntimeError('Spectre-host PDK fingerprint failed: ' + result.stderr)
    return json.loads(result.stdout)


def build_cdf_table(backend, destination, *, pdk, progress=None, verify_pdk=None):
    """Caller owns the exclusive real backend context; restore before publishing.

    All widths receive CDF readback AND native-export comparison, with zero
    Spectre calls. Incomplete/failed builds never publish a usable table.json.
    """
    if not Path(backend.config.model_file).is_relative_to(pdk['root']):
        raise ValueError('Model file must be inside the fingerprinted PDK root')
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    profile = backend.circuit
    started = perf_counter()
    report = dict(schema=SCHEMA, state='building', rows_completed=0, simulation_calls=0)
    write_json(destination / 'preparation.json', report)
    rows = []
    try:
        baseline = backend.generate_netlist(destination / 'reference')
        metadata = json.loads((baseline.path.parent / 'manifest.json').read_text())
        template = Path(metadata['structure_path']).read_text()
        (destination / 'template.scs').write_text(template)
        for index, width in enumerate(width_grid(profile)):
            backend.set_parameters(profile.assignments(width))
            snapshot = backend.read_cdf_snapshot()
            native = backend.generate_netlist(destination / 'native-exports')
            native_meta = json.loads((native.path.parent / 'manifest.json').read_text())
            native_text = Path(native_meta['structure_path']).read_text()
            rendered = render_structure(template, snapshot, profile)
            row_path = destination / f'row-{index:04d}.scs'
            row_path.write_text(rendered)
            profile.validate_export(row_path, snapshot)
            if not structures_equal(profile, rendered, native_text):
                raise ValueError(f'Python template differs from native export at width {width}')
            rows.append(dict(index=index, width=width, snapshot=snapshot,
                             structure_sha256=digest(row_path), native_sha256=digest(Path(native_meta['structure_path'])),
                             native_structure=str(Path(native_meta['structure_path']).relative_to(destination))))
            report['rows_completed'] = len(rows)
            write_json(destination / 'preparation.json', report)
            if progress is not None:
                progress(len(rows), len(width_grid(profile)))
        backend.restore()
        restored = backend.read_cdf_snapshot()
        profile.validate_export(destination / 'template.scs', restored)
        if verify_pdk is not None and verify_pdk() != pdk:
            raise ValueError('PDK files changed during table preparation')
        payload = dict(schema=SCHEMA, origin='real', profile_sha256=profile_contract(profile),
                       model_file=backend.config.model_file, pdk=pdk, bridge_version=backend.bridge_version,
                       library=backend.config.library, template_sha256=digest(destination / 'template.scs'),
                       width_bounds=profile.width_bounds, width_step=profile.width_step,
                       condition=asdict(backend.nominal_condition()), rows=rows,
                       validation='all rows compared with native Virtuoso exports', restored=True)
        payload['sha256'] = content_hash(payload)
        write_json(destination / 'table.json', payload)
        report.update(state='complete', table_sha256=payload['sha256'], restored=True)
    except BaseException as exc:
        report.update(state='failed', exception_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report['elapsed_seconds'] = perf_counter() - started
        write_json(destination / 'preparation.json', report)
    return destination / 'table.json'


class CdfTable:
    def __init__(self, path, profile, *, model_file):
        self.path = Path(path).resolve()
        self.data = json.loads(self.path.read_text())
        payload = {k: v for k, v in self.data.items() if k != 'sha256'}
        if content_hash(payload) != self.data.get('sha256'):
            raise ValueError('CDF table content hash mismatch')
        if (self.data['schema'] != SCHEMA or self.data['origin'] != 'real' or not self.data['restored']
                or self.data['profile_sha256'] != profile_contract(profile)
                or self.data['model_file'] != model_file):
            raise ValueError('CDF table profile/model/schema mismatch')
        self.template = self.path.with_name('template.scs').read_text()
        if digest(self.path.with_name('template.scs')) != self.data['template_sha256']:
            raise ValueError('CDF template hash mismatch')
        widths = width_grid(profile)
        if len(self.data['rows']) != len(widths):
            raise ValueError('Incomplete CDF width table')
        self.profile = profile
        for index, (width, row) in enumerate(zip(widths, self.data['rows'])):
            if row['index'] != index or row['width'] != width:
                raise ValueError('CDF table grid/index mismatch')
            values = profile.validate_readback(row['snapshot'])
            if any(not equal(v, width) for v in values.values()):
                raise ValueError('CDF row width/readback mismatch')
            rendered = render_structure(self.template, row['snapshot'], profile)
            if hashlib.sha256(rendered.encode()).hexdigest() != row['structure_sha256']:
                raise ValueError('CDF row rendering differs from the verified template')

    def lookup(self, parameters):
        self.profile.validate_assignment(parameters)
        width = next(iter(parameters.values()))
        index = round((width - self.profile.width_bounds[0]) / self.profile.width_step)
        row = self.data['rows'][index]
        if not equal(row['width'], width):
            raise ValueError('Requested width is absent from the CDF table')
        return deepcopy(row)


class CdfTableBackend(VirtuosoBridgeBackend):
    """Process-owned standalone Spectre backend. Never attaches to Virtuoso.

    Reuses the existing verified Spectre execution, PSF validation and metrics.
    Each worker must live in its own process: upstream environment configuration
    and stdout redirection are process-global.
    """
    def __init__(self, config, circuit, table_path):
        super().__init__(config, circuit)
        self.table = CdfTable(table_path, circuit, model_file=config.model_file)
        if self.table.data['library'] != config.library:
            raise ValueError('CDF table library mismatch')
        self._active = False
        self._parameters = circuit.validate_readback(circuit.reference)

    def connect(self):
        if self._active:
            self._require_connection()
            return
        import importlib.metadata
        from virtuoso_bridge.env import get_runtime_env_file, set_runtime_env_file, load_vb_env
        from virtuoso_bridge.profile import resolve_profile
        self.bridge_version = importlib.metadata.version('virtuoso-bridge')
        if self.bridge_version != self.table.data['bridge_version'] or self.bridge_version != '0.8.0':
            raise ValueError('CDF table bridge version mismatch')
        self._prior_env, self._prior_runtime = self._vb_env(), get_runtime_env_file()
        try:
            set_runtime_env_file(self.config.env_file.resolve())
            load_vb_env()
            if resolve_profile(self.config.profile) != self.config.profile:
                raise RuntimeError('Explicit bridge profile required')
            self._env_after_attach = self._vb_env()
            if pdk_fingerprint(self.table.data['pdk']['root'], profile=self.config.profile) != self.table.data['pdk']:
                raise ValueError('PDK files changed since CDF table preparation; rebuild the table')
            self._env_hash = digest(self.config.env_file)
            self._bound_env = self._vb_env()
            self._thread, self._pid = threading.get_ident(), os.getpid()
            self._active = True
        except BaseException:
            self._env_after_attach = self._vb_env()
            self.close()
            raise

    def _require_connection(self):
        if not self._active:
            raise BackendNotConnected('CDF table backend is not connected')
        if (threading.get_ident(), os.getpid()) != (self._thread, self._pid):
            raise RuntimeError('CDF backend must stay in its owning worker process/thread')
        if digest(self.config.env_file) != self._env_hash or self._vb_env() != self._bound_env:
            raise RuntimeError('Bridge configuration changed during an active worker')

    def validate_condition(self, condition):
        condition = condition or self.nominal_condition()
        self.circuit.validate_condition(condition)
        if condition != self.nominal_condition():
            raise UnsupportedCapability('Finite CDF training table is nominal-only')

    def set_parameters(self, parameters):
        self._require_connection()
        self.table.lookup(parameters)
        self._parameters = dict(parameters)

    def read_parameters(self):
        self._require_connection()
        return dict(self._parameters)

    def restore(self):
        self._require_connection()
        self._parameters = self.circuit.validate_readback(self.circuit.reference)

    def generate_netlist(self, work_root, *, condition=None):
        self._require_connection()
        self.validate_condition(condition)
        condition = self.nominal_condition()
        row = self.table.lookup(self._parameters)
        directory = Path(work_root).resolve() / uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        structure = directory / 'structure.scs'
        structure.write_text(render_structure(self.table.template, row['snapshot'], self.circuit))
        if digest(structure) != row['structure_sha256']:
            raise ValueError('Prepared structure differs from verified CDF row')
        self.circuit.validate_export(structure, row['snapshot'])
        deck = directory / 'opamp.scs'
        corner = condition.corner
        deck.write_text(build_deck(structure.read_text(), self.config.model_file, corner.model_section,
                                   temperature_c=corner.temperature_c))
        artifact = NetlistArtifact(deck, directory.name, digest(deck), 'real', condition)
        metadata = dict(job_id=artifact.job_id, origin='real', backend='cdf-table-python-template',
                        table_sha256=self.table.data['sha256'], table_row=row['index'],
                        worker_pid=os.getpid(), model_file=self.config.model_file,
                        section=corner.model_section, temperature_c=corner.temperature_c,
                        condition=asdict(condition), structure_path=str(structure), source_sha256=digest(structure),
                        executed_sha256=artifact.sha256, applied_parameters=parameter_rows(self._parameters))
        write_json(directory / 'manifest.json', metadata)
        self._exports[artifact.job_id] = (artifact, dict(self._parameters), metadata)
        return artifact

    def close(self):
        # No schematic restoration or Virtuoso calls: only process-local state.
        self._active = False
        super().close()
