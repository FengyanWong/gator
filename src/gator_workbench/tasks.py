"""Task providers: what circuit is optimized and which EXISTING backend evaluates it.

* ``synthetic:*`` tasks use the optimizer's explicit analytic toy backend
  (``SyntheticSizingBackend``). They are MOCK: origin=synthetic, provenance=mock, their
  ``score`` is not a circuit metric, and their data is confined to the mock output root.
  There is ONE (status record 7.59): ``synthetic:gpdk045_ota5``, a real circuit's netlist
  on that toy backend. The four toy-fixture tasks it replaced are ``REMOVED_MOCK_TASKS``.
* ``netlist`` sources are parsed by the existing Spectre-subset parser. The repository
  has no generic real simulator runner for an arbitrary imported netlist, so real
  evaluation of such a task is reported as a blocker; mock evaluation is available and
  labelled as such.
* ``real:*`` tasks describe the verified GPDK045 bridge profiles. They are only
  runnable when the backend interpreter can import ``virtuoso_bridge`` and the operator
  supplied a connection file. Otherwise the precise blocker and the interface contract
  are returned. Nothing falls back to mock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

from .paths import local_settings_dir, repo_root

# Normalized toy optimum per parameter kind for the analytic mock objective. Arbitrary by
# construction: the mock backend checks plumbing, never electrical behaviour.
MOCK_TARGETS = {'w': 0.4, 'l': -0.2, 'm': 0.0, 'nf': 0.0, 'r': 0.3, 'c': -0.3, 'ind': 0.1, 'dc': 0.2}

# The ONE MOCK task (user decision 2026-09-22, status record 7.59): the free analytic toy backend on a REAL circuit - the
# GPDK045 OTA5 netlist and device mapping that real:gpdk045_ota5 is verified on, with the mapping's three width groups
# (input pair, mirror pair, tail) as its Parameters rows. It runs the whole workbench with no Virtuoso and no Spectre; its
# `score` is still not a circuit metric, and a model it trains can never load into a real run (runs: mock_isolation). The
# four toy-fixture tasks it replaced stay loadable nowhere; their files stay for the optimizer package's own tests.
SYNTHETIC_FIXTURES = {
    'gpdk045_ota5': dict(netlist='examples/circuits/gpdk045_ota5.scs', config='configs/gpdk045_opamp.json',
                         circuit_class='opamp', pdk_id='gpdk045',
                         description='MOCK: the real GPDK045 OTA5 circuit (the netlist real:gpdk045_ota5 runs) on the free '
                                     'analytic toy backend - no Virtuoso, no Spectre. Its score is not a circuit result.'),
}
# What an entry that names no PDK / description gets (a circuit a test registers for itself, e.g. test_wb_pdk's demo).
MOCK_PDK, MOCK_DESCRIPTION = 'synthetic-fixture', 'MOCK: the analytic toy backend on a fixture netlist. Its score is not a circuit result.'
REMOVED_MOCK_TASKS = ('synthetic:opamp', 'synthetic:opamp_two_stage', 'synthetic:ldo', 'synthetic:vco')
MOCK_TASK_REMOVED = ('{task} no longer exists: the workbench has one MOCK task now, synthetic:gpdk045_ota5 - the real OTA5 '
                     'circuit on the free toy backend. Choose it under "Task".')

REAL_PROFILES = {
    'gpdk045_ota5': dict(profile='analog_optimizer.backends.gpdk045:Gpdk045OtaProfile', circuit_class='opamp',
                         design='configs/gpdk045_opamp_design.json', mapping='configs/gpdk045_opamp.json',
                         structure='examples/circuits/gpdk045_ota5.scs',
                         readback='examples/circuits/gpdk045_ota5.cdf.json'),
    'gpdk045_ota7': dict(profile='analog_optimizer.backends.gpdk045_two_stage', circuit_class='opamp',
                         design='configs/gpdk045_ota7_design.json', mapping='configs/gpdk045_ota7.json',
                         structure='examples/circuits/gpdk045_ota7.scs',
                         readback='examples/circuits/gpdk045_ota7.cdf.json'),
    'gpdk045_ldo': dict(profile='analog_optimizer.backends.gpdk045_ldo', circuit_class='ldo',
                        design='configs/gpdk045_ldo_design.json', mapping='configs/gpdk045_ldo.json',
                        structure='examples/circuits/gpdk045_ldo.scs',
                        readback='examples/circuits/gpdk045_ldo.cdf.json'),
    'gpdk045_vco': dict(profile='analog_optimizer.backends.gpdk045_vco', circuit_class='vco',
                        design='configs/gpdk045_vco_design.json', mapping='configs/gpdk045_vco.json',
                        structure='examples/circuits/gpdk045_vco.scs',
                        readback='examples/circuits/gpdk045_vco.cdf.json'),
}

# The TARGETS OF RECORD of the verified circuits: the frozen specification files of the real experiments, as (file, keys
# down to the list of specs). Pilot goals near each circuit's measured baseline - not product specifications. They are what
# the Specs tab shows when such a task is chosen (starter_config); `train` is the partition a run from scratch belongs to.
REAL_TARGETS_OF_RECORD = {
    'gpdk045_ota5': ('configs/m6_real_cross_category.json', 'classes', 'opamp', 'specs', 'train'),
    'gpdk045_ota7': ('configs/gpdk045_ota7_transfer.json', 'specs'),
    'gpdk045_ldo': ('configs/m6_real_cross_category.json', 'classes', 'ldo', 'specs', 'train'),
    'gpdk045_vco': ('configs/m6_real_cross_category.json', 'classes', 'vco', 'specs', 'train'),
}
# The LDO and VCO results are not in the optimizer's default result registry (score + the op-amp results) and the UI has no
# editor for the registry, so a target on them could not even be stated. These two tasks bring the registry of record of
# the real cross-category experiment, the way a generated profile brings its own (profiles.task_spec_registry). The OTA
# tasks stay on the default registry: their models, the MOCK tasks' and earlier workbench runs' remain interchangeable.
REAL_REGISTRY_OF_RECORD = {'gpdk045_ldo': 'configs/m6_real_cross_category.json',
                           'gpdk045_vco': 'configs/m6_real_cross_category.json'}
# Which analysis of the circuit profiles produces a result: the label on its Probes row. Everything else is a DC operating
# point, except that an oscillator's results all come from its transient run.
RESULT_ANALYSIS = dict.fromkeys(('gain_db_at_start', 'gain_reference_hz', 'bandwidth_3db_hz', 'unity_gain_hz',
                                 'phase_margin_estimate_deg', 'unity_downward_crossings', 'ldo_psrr_1khz_db'), 'ac')
RESULT_ANALYSIS.update(dict.fromkeys(('ldo_step_deviation_v', 'ldo_step_final_shift_v', 'ldo_step_tail_ripple_v'), 'tran'))

REAL_INTERFACE_CONTRACT = dict(
    environment_factory='analog_optimizer.training.parallel.NativeEnvironmentFactory(config, profile, specs, output, '
                        'max_steps, timeout_seconds, reference_metrics)',
    bridge_config='analog_optimizer.backends.virtuoso_bridge.BridgeConfig(env_file, library, creation_receipt, '
                  'state_root, model_file, section, profile)',
    connection_file=str(Path('configs/local/workbench/bridge_connection.json')),
    connection_file_format='{"active": "<id>", "profiles": {"<id>": {...keys below...}}}',
    connection_file_keys=['env_file', 'library', 'model_file', 'profile (optional)', 'bridge_site_packages (optional)',
                          'circuits: {"<task name, e.g. gpdk045_ota5>": {"creation_receipt": ..., '
                          '"reference_measurements": ...}}',
                          'creation_receipt + reference_measurements at the top level (older single-circuit form; used '
                          'only for a circuit without its own "circuits" entry)'],
    requirements=['virtuoso-bridge 0.8.0 importable by the backend interpreter',
                  'an ALREADY RUNNING bridge tunnel (automatic startup is disabled by the adapter)',
                  'a dedicated Virtuoso session; no ADE/Maestro window open on the design',
                  'verified real baseline measurements for the selected profile'],
    max_concurrency=4,
    note='Native CDF preparation is serialized by the existing preparation service; only Spectre runs in parallel.')


REAL_AUTHORIZATION_REQUIRED = ('Real Virtuoso/Spectre execution requires an explicit user action with an authorized budget; '
                               'it is never started implicitly.')


class TaskBlocked(RuntimeError):
    """The task cannot be evaluated here. Carries the blocker; never replaced by mock data."""
    def __init__(self, message, *, contract=None):
        super().__init__(message)
        self.contract = contract


@dataclass
class TaskRuntime:
    task_key: str
    origin: str                        # 'synthetic' | 'real'
    base_graph: object
    provided_metrics: tuple
    circuit: dict                      # class, pdk, hashes, source files
    netlist_text: str | None
    netlist_path: str | None
    parser_config_path: str | None
    env_factory_builder: object        # callable(compiled, work_root, run_settings) -> picklable env factory
    max_concurrency: int = 64
    supports_threads: bool = False
    notes: list = field(default_factory=list)
    authorized: bool = True            # False = a real task loaded to be SHOWN and validated only: it cannot execute
    reference_metrics: dict | None = None   # verified REAL results of the INITIAL design: {metric: {value, unit}}; None if unknown

    @property
    def mock(self) -> bool:
        return self.origin == 'synthetic'


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_netlist(netlist_path, parser_config_path, *, top=None):
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    config = ParserConfig.from_file(parser_config_path)
    graph = SpectreParser(config).parse_file(netlist_path, top=top)
    # The workbench configuration owns the variable definition; drop file-declared groups so
    # "equal initial values" or a fixture default can never silently become a binding.
    graph.parameter_groups = []
    return graph


@dataclass(frozen=True)
class SyntheticEnvFactory:
    """Picklable: builds the EXISTING environment + analytic toy backend inside a lane."""
    graph: object
    specs: tuple
    targets: dict
    work_root: str
    max_steps: int
    timeout_seconds: float
    stop_on_success: bool
    plan: object = None               # spec_equations.SpecPlan: the specs computed from the probes are added to each result

    def __call__(self, lane):
        from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        kinds = {g.parameter_kind for g in self.graph.parameter_groups if g.mutable}
        backend = SyntheticSizingBackend(self.graph, targets={k: self.targets[k] for k in kinds})
        if self.plan is not None:
            self.plan.wrap(backend)
        return CircuitSizingEnv(backend, self.graph, self.specs, Path(self.work_root) / f'worker-{lane}',
                                max_steps=self.max_steps, timeout_seconds=self.timeout_seconds,
                                stop_on_success=self.stop_on_success, expected_origin='synthetic')


def _synthetic_builder(compiled, work_root, run_settings):
    adv = run_settings.advanced
    return SyntheticEnvFactory(compiled.graph, compiled.specs, dict(MOCK_TARGETS), str(work_root),
                               adv.episode_length, adv.simulation_timeout_seconds,
                               adv.episode_terminates_on_success, compiled.plan)


def _with_computed_specs(factory, compiled):
    """The verified real factory, unchanged when every spec is a simulator result itself; otherwise wrapped so that the
    specs computed from the probes reach the reward (spec_equations.EquationNativeFactory)."""
    if not compiled.plan.injected:
        return factory
    from .spec_equations import EquationNativeFactory
    return EquationNativeFactory(factory, compiled.plan)


def _netlist_runtime(task_key, netlist, parser_config, *, circuit_class, pdk_id, top=None, notes=()):
    netlist, parser_config = Path(netlist), Path(parser_config)
    graph = parse_netlist(netlist, parser_config, top=top)
    circuit = dict(circuit_class=circuit_class, pdk_id=pdk_id, dut_hierarchy=top,
                   netlist_sha256=_sha256(netlist), parser_config_sha256=_sha256(parser_config),
                   netlist_file=str(netlist), parser_config_file=str(parser_config),
                   topology_id=f'netlist-sha256:{_sha256(netlist)[:16]}', complete=graph.complete,
                   evaluation_backend='analytic-toy-sizing-v1 (MOCK: quadratic score, not a circuit simulation)')
    return TaskRuntime(task_key, 'synthetic', graph, ('score',), circuit, netlist.read_text(), str(netlist),
                       str(parser_config), _synthetic_builder, notes=list(notes))


def starter_project(task_key) -> dict:
    """The project / task name a task's starter gives: what a run is filed under (runs/<task_name>/) until the user names
    it. Listed with every task, so the page can tell a name nobody typed from one the user chose."""
    kind, _, name = task_key.partition(':')
    return (dict(name=f"mock-{name.replace('_', '-')}", task_name=f'mock_{name}') if kind == 'synthetic'
            else dict(name=name.replace('_', '-'), task_name=name))


def list_tasks():
    tasks = []
    for name, info in SYNTHETIC_FIXTURES.items():
        tasks.append(dict(task_key=f'synthetic:{name}', kind='mock', circuit_class=info['circuit_class'],
                          pdk_id=info.get('pdk_id', MOCK_PDK), available=True, description=info.get('description', MOCK_DESCRIPTION)))
    for name, info in REAL_PROFILES.items():
        blocker = real_backend_blocker(None, name)               # each circuit has its own receipt and baseline
        tasks.append(dict(task_key=f'real:{name}', kind='real', circuit_class=info['circuit_class'], pdk_id='gpdk045',
                          available=blocker is None, blocker=blocker,
                          description='Verified GPDK045 bridge profile (Virtuoso + Spectre).'))
    from . import profiles
    for name, entry in profiles.list_profiles().items():         # created from a cell read out of Virtuoso
        blocker = profiles.MAESTRO_NOT_RUNNABLE if entry.get('recipe') == profiles.MAESTRO else generated_backend_blocker(None)
        tasks.append(dict(task_key=f'real:{name}', kind='real', circuit_class=entry['circuit_class'], generated=True,
                          pdk_id=entry.get('pdk_id') or 'gpdk045', available=blocker is None, blocker=blocker, library=entry['library'], cell=entry['core_cell'],
                          revision=entry.get('revision'), measurement=entry.get('measurement'), original=entry.get('original'),
                          verified=profiles.reference_metrics(name) is not None,
                          description=f"Profile generated from {entry['library']}/{entry['core_cell']} (Virtuoso + Spectre). "
                                      + ('' if profiles.reference_metrics(name) else 'No real baseline recorded yet.')))
    for task in tasks:
        task['starter_project'] = starter_project(task['task_key'])
    return tasks


def bridge_importable() -> bool:
    return importlib.util.find_spec('virtuoso_bridge') is not None


def _profile_settings(profile_id=None):
    from .connection import load_profiles
    loaded = load_profiles()
    key = profile_id or loaded['active']
    return loaded, (loaded['profiles'].get(key) if key else None)


def _not_a_virtuoso_connection(profile_id, settings):
    """Every real task here is a Virtuoso + Spectre testbench. A connection of another kind (ngspice) is named as
    such, instead of being reported as a Virtuoso profile with missing settings."""
    from .connection import KINDS, family_of, profile_kind
    kind = profile_kind(settings)
    if kind is None or family_of(kind) == 'virtuoso':
        return None                                   # an unknown kind is named by the connection check itself
    return (f'Connection {profile_id or "(the active one)"!r} is "{KINDS[kind]["label"]}". This circuit runs on Virtuoso + '
            'Spectre: choose a Virtuoso connection in the Connection window. Running circuits on ngspice is not built yet.')


CIRCUIT_KEYS = ('creation_receipt', 'reference_measurements')     # these two belong to ONE circuit, not to the link


def real_bindings(settings, name=None) -> dict:
    """The settings a real run of circuit `name` uses. A creation receipt and a baseline describe one
    circuit, so they are read from  "circuits": {"<name>": {...}}  first; the flat keys of the older
    single-circuit form are only the fallback. A flat receipt can never be applied to the wrong circuit
    silently: `real_backend_blocker` compares it with the circuit's design file, as the adapter does."""
    circuits = settings.get('circuits')
    own = (circuits.get(name) if isinstance(circuits, dict) and name else None) or {}
    merged = {k: v for k, v in settings.items() if k != 'circuits'}
    merged.update({k: own[k] for k in CIRCUIT_KEYS if isinstance(own, dict) and own.get(k)})
    return merged


def _binding_problem(name, bound):
    """Zero-cost consistency check of the two per-circuit files (local reads only). The adapter repeats
    the receipt comparison at connect; doing it here blocks a mismatch before anything is prepared."""
    info, root = REAL_PROFILES[name], repo_root()
    receipt_file, reference_file = Path(bound['creation_receipt']), Path(bound['reference_measurements'])
    for label, path in (('creation_receipt', receipt_file), ('reference_measurements', reference_file)):
        if not path.is_file():
            return f'{label} of real:{name} does not exist: {path}'
    try:
        receipt, reference = json.loads(receipt_file.read_text()), json.loads(reference_file.read_text())
        design = json.loads((root / info['design']).read_text())
    except (OSError, ValueError) as exc:
        return f'The binding files of real:{name} cannot be read: {type(exc).__name__}: {exc}'
    for key, expected in (('library', bound['library']), ('core_cell', design.get('core_cell')),
                          ('testbench_cell', design.get('testbench_cell'))):
        if receipt.get(key) != expected:
            return (f'The creation receipt bound to real:{name} is for {key}={receipt.get(key)!r}, but this circuit needs '
                    f'{expected!r}. Bind the receipt of THIS circuit under "circuits": {{"{name}": ...}}.')
    if reference.get('origin') != 'real' or not isinstance(reference.get('metrics'), dict) or not reference['metrics']:
        return f'reference_measurements of real:{name} must be verified REAL baseline measurements with a metrics table'
    return None


def real_backend_blocker(profile_id=None, name=None):
    """Why real execution is impossible here, or None. With `name`, the per-circuit bindings of that
    registered real task are checked as well."""
    loaded, settings = _profile_settings(profile_id)
    if not loaded['exists'] or not loaded['profiles']:
        return (f"No bridge connection profile is configured ({loaded['file']}). The backend never guesses hosts, "
                'libraries, accounts or model paths.')
    if settings is None:
        return f'Connection profile {profile_id!r} is not configured.'
    wrong_kind = _not_a_virtuoso_connection(profile_id, settings)
    if wrong_kind:
        return wrong_kind
    if settings.get('bridge_site_packages'):
        import site
        site.addsitedir(str(Path(settings['bridge_site_packages']).resolve()))
    if not bridge_importable():
        return (f'virtuoso_bridge is not importable by the backend interpreter ({sys.executable}). It is installed '
                'only in another virtualenv. Install virtuoso-bridge 0.8.0 into this interpreter, or set '
                '"bridge_site_packages" for the profile in configs/local/workbench/bridge_connection.json.')
    bound = real_bindings(settings, name)
    missing = [k for k in ('env_file', 'library', 'creation_receipt', 'model_file', 'reference_measurements')
               if not bound.get(k)]
    if missing:
        where = f' for real:{name}' if name and set(missing) <= set(CIRCUIT_KEYS) else ''
        hint = (f' Add them under "circuits": {{"{name}": {{...}}}} in {loaded["file"]}.' if where else '')
        return f'The connection profile lacks {missing}{where}, which a real run needs.{hint}'
    if name in REAL_PROFILES:
        return _binding_problem(name, bound)
    return None


def load_task(circuit, *, allow_real=False, profile_id=None) -> TaskRuntime:
    """Resolve a CircuitReference to a runtime. Raises TaskBlocked with the concrete reason."""
    root = repo_root()
    if circuit.source == 'registered_task':
        key = circuit.task_id or ''
        kind, _, name = key.partition(':')
        if kind == 'synthetic' and name in SYNTHETIC_FIXTURES:
            info = SYNTHETIC_FIXTURES[name]
            return _netlist_runtime(key, root / info['netlist'], root / info['config'],
                                    circuit_class=info['circuit_class'], pdk_id=info.get('pdk_id', MOCK_PDK),
                                    top=circuit.dut_hierarchy)
        if key in REMOVED_MOCK_TASKS:
            raise TaskBlocked(MOCK_TASK_REMOVED.format(task=key))
        if kind == 'real' and name not in REAL_PROFILES:
            from . import profiles
            if name in profiles.list_profiles():
                blocker = generated_backend_blocker(profile_id)
                if blocker:
                    raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
                return _generated_runtime(key, name, profile_id, authorized=bool(allow_real))
        if kind == 'real' and name in REAL_PROFILES:
            blocker = real_backend_blocker(profile_id, name)
            if blocker:
                raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
            # Without the authorization the task is still loaded - from local files, with no bridge contact - so it
            # can be shown, edited and validated. It cannot execute: prepare_run and the worker refuse it, and its
            # environment builder raises. (Refusing to LOAD it made the authorization dialog unreachable.)
            return _real_runtime(key, name, profile_id, authorized=bool(allow_real))
        raise TaskBlocked(f'Unknown registered task {key!r}')
    if circuit.source == 'netlist':
        if not circuit.netlist_path or not circuit.parser_config_path:
            missing = [label for label, value in (('the netlist file (netlist_path)', circuit.netlist_path),
                                                  ('a device mapping JSON (parser_config_path)', circuit.parser_config_path))
                       if not value]
            raise TaskBlocked(f'An imported netlist still needs {" and ".join(missing)}. The mapping says which pin is '
                              'which and what each device parameter means; that is never guessed.')
        return _netlist_runtime(f'netlist:{Path(circuit.netlist_path).name}', circuit.netlist_path,
                                circuit.parser_config_path, circuit_class=circuit.circuit_class,
                                pdk_id=circuit.pdk_id, top=circuit.dut_hierarchy,
                                notes=['Imported netlists can only be evaluated by the MOCK analytic backend: the '
                                       'repository has no generic real simulator runner for arbitrary netlists.'])
    if circuit.source == 'virtuoso':
        from . import native_cells
        imported = native_cells.load_import(circuit.library, circuit.cell) if circuit.library and circuit.cell else None
        if imported is None or allow_real:                   # allow_real = a run start: a cell without a profile never executes
            raise TaskBlocked((NATIVE_DRAFT_NOT_EXECUTABLE if imported else
                               'Optimizing an arbitrary native cellview needs a verified circuit profile (writable '
                               'parameters, CDF rules, analyses, measurements).') + ' Existing profiles: '
                              + ', '.join(f'real:{n}' for n in REAL_PROFILES), contract=REAL_INTERFACE_CONTRACT)
        return _native_draft_runtime(imported, circuit)
    raise TaskBlocked(f'Unsupported circuit source {circuit.source!r}')


NATIVE_DRAFT_NOT_EXECUTABLE = ('This cell was read from Virtuoso, but it has no circuit profile yet, so it cannot be '
                               'simulated or optimized: a profile fixes which sizes may be written and in which steps, '
                               'which testbench runs, and how results are measured.')


def _native_draft_runtime(imported, circuit):
    """A cell imported from Virtuoso (`native_cells`), loaded from its LOCAL copy: it can be shown, edited
    against, validated and summarized for the agent. It cannot execute - there is nothing to build."""
    from . import native_cells
    graph = native_cells.draft_graph(imported)

    def builder(compiled, work_root, run_settings):
        raise TaskBlocked(NATIVE_DRAFT_NOT_EXECUTABLE, contract=REAL_INTERFACE_CONTRACT)
    unverified = imported.get('unverified_models') or []
    notes = [f"Read from Virtuoso {imported['imported_utc'][:19]} UTC (netlist export of {imported['exported_cell']}, read-only). "
             'Shown from the local copy: read the cell again after changing it in Virtuoso.']
    if unverified:
        notes.append(f"Device type(s) {', '.join(unverified)} are not verified in this project yet: their pins are shown "
                     'unnamed, and nothing is assumed about them.')
    info = dict(circuit_class=circuit.circuit_class, pdk_id=circuit.pdk_id if circuit.pdk_id != 'unspecified'
                else imported.get('technology_library') or 'unspecified', dut_hierarchy=circuit.dut_hierarchy,
                netlist_sha256=imported['netlist_sha256'], parser_config_sha256=imported['mapping_sha256'],
                netlist_file=imported['netlist_path'], parser_config_file=imported['mapping_path'],
                topology_id=f"netlist-sha256:{imported['netlist_sha256'][:16]}", complete=graph.complete,
                evaluation_backend=None, native_draft=True, library=imported['library'], cell=imported['cell'],
                testbench_cell=imported.get('testbench_cell'), imported_utc=imported['imported_utc'],
                unverified_models=unverified)
    return TaskRuntime(f"virtuoso:{imported['library']}/{imported['cell']}", 'real', graph, (), info,
                       Path(imported['netlist_path']).read_text(), imported['netlist_path'], imported['mapping_path'],
                       builder, max_concurrency=1, notes=notes, authorized=False)


def generated_backend_blocker(profile_id=None):
    """Why a GENERATED profile cannot execute here, or None. Its receipt and (later) its baseline live in its own
    folder, so of the connection profile it needs only the link and the model file."""
    loaded, settings = _profile_settings(profile_id)
    if not loaded['exists'] or not loaded['profiles']:
        return (f"No bridge connection profile is configured ({loaded['file']}). The backend never guesses hosts, "
                'libraries, accounts or model paths.')
    if settings is None:
        return f'Connection profile {profile_id!r} is not configured.'
    wrong_kind = _not_a_virtuoso_connection(profile_id, settings)
    if wrong_kind:
        return wrong_kind
    if settings.get('bridge_site_packages'):
        import site
        site.addsitedir(str(Path(settings['bridge_site_packages']).resolve()))
    if not bridge_importable():
        return (f'virtuoso_bridge is not importable by the backend interpreter ({sys.executable}). Set '
                '"bridge_site_packages" for the profile in configs/local/workbench/bridge_connection.json.')
    missing = [k for k in ('env_file', 'model_file') if not settings.get(k)]
    return f'The connection profile lacks {missing}, which a real run needs.' if missing else None


def generated_bridge_config(name, profile_id=None):
    """(BridgeConfig, profile object, registry entry) of a generated profile: the link and the model file of the
    connection profile, the cell's OWN library, the receipt of the profile's folder. Local files only."""
    import site
    from . import profiles
    blocker = generated_backend_blocker(profile_id)
    if blocker:
        raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
    entry = profiles.list_profiles().get(name)
    if entry is None:
        raise TaskBlocked(f'Unknown generated profile {name!r}')
    connection = _profile_settings(profile_id)[1]
    if connection.get('bridge_site_packages'):
        site.addsitedir(str(Path(connection['bridge_site_packages']).resolve()))
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
    directory = Path(entry['directory'])
    try:
        profile = profiles.load_profile(name)
    except Exception as exc:
        raise TaskBlocked(f'The generated profile real:{name} no longer passes its own checks: {exc}')
    config = BridgeConfig(Path(connection['env_file']).resolve(), entry['library'], (directory / profiles.FILES['receipt']).resolve(),
                          (repo_root() / 'artifacts/local/bridge-state').resolve(), connection['model_file'],
                          profile=connection.get('profile'))
    return config, profile, entry


def _generated_runtime(task_key, name, profile_id=None, *, authorized=False):
    """A profile created from a cell read out of Virtuoso (`profiles`): the file-driven class, the cell's OWN
    library, the receipt of its folder. Until a real baseline is recorded there is nothing to compare a worker's
    first evaluation with, so none is passed (the factory's comparison is optional)."""
    from . import profiles, recipes
    config, profile, entry = generated_bridge_config(name, profile_id)
    directory = Path(entry['directory'])
    reference = profiles.reference_metrics(name)
    graph = profile.optimization_graph()

    def builder(compiled, work_root, run_settings):
        if entry.get('recipe') == profiles.MAESTRO:
            raise TaskBlocked(profiles.MAESTRO_NOT_RUNNABLE)
        if not authorized:
            raise TaskBlocked(REAL_AUTHORIZATION_REQUIRED, contract=REAL_INTERFACE_CONTRACT)
        from analog_optimizer.training.parallel import NativeEnvironmentFactory
        from analog_optimizer.envs.sizing import graph_contract
        if graph_contract(compiled.graph) != graph_contract(graph):
            raise TaskBlocked('This task fixes which widths may change, their ranges and their grid. The rows of the parameter '
                              'editor differ from what was saved; press "Save task" to save the new rows first.')
        adv = run_settings.advanced
        return _with_computed_specs(NativeEnvironmentFactory(config, profile, compiled.specs, Path(work_root), adv.episode_length,
                                                             adv.simulation_timeout_seconds, reference), compiled)
    structure, mapping = directory / profiles.FILES['structure'], directory / profiles.FILES['mapping']
    circuit = dict(circuit_class=entry['circuit_class'], pdk_id=entry.get('pdk_id') or 'gpdk045', dut_hierarchy=None,
                   netlist_sha256=_sha256(structure), parser_config_sha256=_sha256(mapping), netlist_file=str(structure),
                   parser_config_file=str(mapping), topology_id=f'profile:{name}', complete=True, generated_profile=True,
                   baseline_recorded=reference is not None, evaluation_backend='virtuoso_bridge + Spectre (REAL)')
    notes = ['Generated profile: it passes every offline check of the verified profiles, but '
             + ('its first real simulation has not been run yet - start with "Single baseline simulation".' if reference is None
                else 'only its recorded baseline has been simulated for real.')]
    if not authorized:
        notes.append('Loaded for viewing and validation only. Running it needs your explicit authorization of a real '
                     'simulation budget (asked when you press Start).')
    if entry.get('recipe') == profiles.MAESTRO:
        notes.insert(0, profiles.MAESTRO_NOT_RUNNABLE)
    provided = tuple(entry.get('provided_metrics') or ()) if entry.get('recipe') == profiles.MAESTRO else recipes.provided_metrics(entry['recipe'])
    return TaskRuntime(task_key, 'real', graph, provided, circuit, structure.read_text(),
                       str(structure), str(mapping), builder, max_concurrency=4, authorized=bool(authorized), notes=notes,
                       reference_metrics=None if reference is None else {
                           key: dict(value=value, unit=None) for key, value in reference.items() if isinstance(value, (int, float))})


def _verified_profile(name):
    """The profile object of a verified circuit, from its files in the repository: no connection, no bridge."""
    import importlib
    info, root = REAL_PROFILES[name], repo_root()
    module_name, _, class_name = info['profile'].partition(':')
    module = importlib.import_module(module_name)
    candidates = [getattr(module, class_name)] if class_name else [
        value for key, value in vars(module).items() if key.endswith('Profile') and isinstance(value, type)
        and value.__module__ == module.__name__]
    if len(candidates) != 1:
        raise TaskBlocked(f'Cannot identify the circuit profile class in {module_name}')
    return candidates[0](design_file=root / info['design'], mapping_file=root / info['mapping'],
                         reference_structure=root / info['structure'], reference_readback=root / info['readback'])


def _real_runtime(task_key, name, profile_id=None, *, authorized=False):
    """Assemble the verified native factory from local files; nothing here contacts the bridge. Only
    reachable with the bridge importable and complete bindings. The factory itself can only be BUILT
    when `authorized` - the explicit user action with a budget."""
    import site
    info, root = REAL_PROFILES[name], repo_root()
    connection = real_bindings(_profile_settings(profile_id)[1], name)
    if connection.get('bridge_site_packages'):
        site.addsitedir(str(Path(connection['bridge_site_packages']).resolve()))
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
    profile = _verified_profile(name)
    config = BridgeConfig(Path(connection['env_file']).resolve(), connection['library'],
                          Path(connection['creation_receipt']).resolve(),
                          (root / 'artifacts/local/bridge-state').resolve(), connection['model_file'],
                          profile=connection.get('profile'))
    reference = json.loads(Path(connection['reference_measurements']).read_text())
    if reference.get('origin') != 'real':
        raise TaskBlocked('reference_measurements must be verified REAL baseline measurements')
    graph = profile.optimization_graph()

    def builder(compiled, work_root, run_settings):
        if not authorized:
            raise TaskBlocked(REAL_AUTHORIZATION_REQUIRED, contract=REAL_INTERFACE_CONTRACT)
        from analog_optimizer.training.parallel import NativeEnvironmentFactory
        from analog_optimizer.envs.sizing import graph_contract
        if graph_contract(compiled.graph) != graph_contract(graph):
            raise TaskBlocked('A real profile fixes its writable parameters and legal grid. The configured variables '
                              'differ from the verified profile; real action permissions are not widened from the UI.')
        adv = run_settings.advanced
        return _with_computed_specs(NativeEnvironmentFactory(config, profile, compiled.specs, Path(work_root), adv.episode_length,
                                                             adv.simulation_timeout_seconds, reference['metrics']), compiled)
    circuit = dict(circuit_class=info['circuit_class'], pdk_id='gpdk045', dut_hierarchy=None,
                   netlist_sha256=_sha256(root / info['structure']), parser_config_sha256=_sha256(root / info['mapping']),
                   netlist_file=str(root / info['structure']), parser_config_file=str(root / info['mapping']),
                   topology_id=f'profile:{name}', complete=True, evaluation_backend='virtuoso_bridge + Spectre (REAL)')
    metrics = tuple(reference['metrics'])
    return TaskRuntime(task_key, 'real', graph, metrics, circuit, (root / info['structure']).read_text(),
                       str(root / info['structure']), str(root / info['mapping']), builder, max_concurrency=4,
                       authorized=bool(authorized),
                       reference_metrics={name: dict(value=value, unit=(reference.get('metric_units') or {}).get(name))
                                          for name, value in reference['metrics'].items() if isinstance(value, (int, float))},
                       notes=[] if authorized else ['Loaded for viewing and validation only. Running it needs your explicit '
                                                    'authorization of a real simulation budget (asked when you press Start).'])


def profile_parameter_rows(runtime) -> list:
    """The Parameters-tab rows a REAL circuit profile fixes, written from its own parameter groups (the same
    mapping as starter_config). A real profile accepts exactly these variables, ranges and grid: the engine compares the
    compiled configuration with the profile (`graph_contract`) and refuses anything else when the run starts. Empty for
    a task that fixes nothing (the MOCK task, a cell without a profile)."""
    return [] if runtime is None or runtime.mock else _graph_parameter_rows(runtime.base_graph)


_NOT_IN_AN_ID = re.compile(r'[^A-Za-z0-9_.\-]')


def _member_variable_id(group_id, device_id) -> str:
    """The Parameters-row ID of a group member that follows the group's leader: `<group>__<device>`, with every character
    an ID may not hold (schema: letters, digits, _ . -) written as _ - the / of a hierarchical path such as XU1/M1 or
    stage_a/pull_up, the <> of a bus. The ID is only a label; the exact device stays in `instance_path`. The MOCK
    starter used to keep the /, so choosing synthetic:vco gave three rows the schema rejects (status record 7.56)."""
    return f'{group_id}__{_NOT_IN_AN_ID.sub("_", str(device_id))}'


def _graph_parameter_rows(graph) -> list:
    from dataclasses import asdict
    rows = []
    for group in getattr(graph, 'parameter_groups', ()) or ():
        record, leader = asdict(group), None
        for member in record['members']:
            variable_id = record['id'] if leader is None else _member_variable_id(record['id'], member['device_id'])
            row = dict(variable_id=variable_id, instance_path=member['device_id'], parameter_name=member['parameter'],
                       unit=record['unit'], scale=record.get('scale') or 'linear',
                       value_type='integer' if record.get('domain') == 'integer' else 'continuous')
            if leader is None:
                row.update(lower=record['lower'], upper=record['upper'], step=record.get('step'),
                           optimized=bool(record.get('mutable', True)), initial_value=record.get('value'))
                leader = variable_id
            else:                                # a follower carries its group's flag: a frozen group is frozen as a whole
                row.update(binding_group=leader, ratio=member.get('ratio', 1.0), optimized=bool(record.get('mutable', True)))
            rows.append(row)
    return rows


def verified_spec_registry(circuit):
    """(version, entries) of the result registry a VERIFIED circuit brings along (REAL_REGISTRY_OF_RECORD), else None."""
    task_id = getattr(circuit, 'task_id', None) or ''
    if getattr(circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return None
    file = REAL_REGISTRY_OF_RECORD.get(task_id[len('real:'):])
    if file is None:
        return None
    record = json.loads((repo_root() / file).read_text())['schema']
    return record['version'], [dict(metric_id=name, unit=unit, reference=reference) for name, unit, reference in record['metrics']]


def real_starter_config(task_key: str) -> dict:
    """What the three editors show when a REAL task is chosen. Local files only: no connection, no bridge, no simulation.
    Parameters - the rows the circuit's profile fixes (a real run accepts exactly these). Specs - the targets of record of
    a verified circuit (REAL_TARGETS_OF_RECORD), each row stating its source; a profile generated from a cell has none,
    its requirements stay the user's to state. Probes - one row per result that carries a target; for a generated profile
    one per result a target can be set on. Run settings are left alone: a real budget is never suggested."""
    from . import profiles
    name = task_key.partition(':')[2]
    if name in REAL_PROFILES:
        circuit_class, pdk_id = REAL_PROFILES[name]['circuit_class'], 'gpdk045'
        graph, oscillator = _verified_profile(name).optimization_graph(), circuit_class == 'vco'
        file, *keys = REAL_TARGETS_OF_RECORD[name]
        specs = json.loads((repo_root() / file).read_text())
        for key in keys:
            specs = specs[key]
        basis = (f'Pilot target of record ({file}: {" / ".join(keys)}): a goal near the measured baseline of this '
                 'circuit, not a product specification.')
        results = {spec['metric_id']: spec['unit'] for spec in specs}
        probes = [dict(measurement_id=f'm_{metric}', analysis='tran' if oscillator else RESULT_ANALYSIS.get(metric, 'dc'),
                       result_source='backend_profile', source_name=metric, unit=unit,
                       notes='Computed by the circuit profile from the simulation results.')
                  for metric, unit in results.items()]
    else:
        entry = profiles.list_profiles().get(name)
        if entry is None:
            raise KeyError(task_key)
        circuit_class, pdk_id = entry['circuit_class'], entry.get('pdk_id') or 'gpdk045'
        saved = profiles.task_file(name)
        if saved is not None:                          # a saved task: its own rows, exactly as "Save task" stored them
            return dict(project=starter_project(task_key),
                        circuit=dict(source='registered_task', task_id=task_key, circuit_class=circuit_class, pdk_id=pdk_id),
                        parameters=saved.get('parameters') or [], measurements=saved.get('probes') or [], targets=saved.get('specs') or [])
        profile = profiles.load_profile(name)
        graph = profile.optimization_graph()
        # The Probes of the testbench the profile was made through: the rows reading the cell brought
        # (profiles.testbench_probes), built by the same function - so after Create profile the editors still hold
        # this task's own rows, and choosing another task treats them as nobody's work.
        probes = profiles.probe_rows(entry['recipe'], profiles.probe_results(entry['recipe'], entry.get('spec_registry')),
                                     profiles.design_signals(entry['recipe'], profile.design), entry.get('testbench_cell'))
        specs, basis = [], ''
    thresholds = dict(min=('>=', ('lower',)), max=('<=', ('upper',)), range=('interval', ('lower', 'upper')))
    targets = []
    for spec in specs:
        constraint, sides = thresholds[spec['comparator']]
        targets.append(dict(metric_id=spec['metric_id'], equation=f"m_{spec['metric_id']}", unit=spec['unit'],
                            constraint=constraint, **{side: spec[side] for side in sides},
                            normalization_scale=spec['scale'], basis=basis))
    return dict(
        project=starter_project(task_key),
        circuit=dict(source='registered_task', task_id=task_key, circuit_class=circuit_class, pdk_id=pdk_id),
        parameters=_graph_parameter_rows(graph),
        measurements=probes,
        targets=targets)


def starter_config(task_key: str) -> dict:
    """A valid starting configuration for a registered task. A convenience for manual editing; every field stays
    editable. The MOCK task: the groups its device mapping declares, with the toy `score` as its only target. A real
    task: real_starter_config. A removed MOCK task (REMOVED_MOCK_TASKS) has none: KeyError, like any unknown task."""
    from analog_optimizer.netlist.config import ParserConfig
    kind, _, name = task_key.partition(':')
    if kind == 'real' and name:
        return real_starter_config(task_key)
    if kind != 'synthetic' or name not in SYNTHETIC_FIXTURES:
        raise KeyError(task_key)
    root, info = repo_root(), SYNTHETIC_FIXTURES[name]
    parser_config = ParserConfig.from_file(root / info['config'])
    parameters = []
    for group in parser_config.parameter_groups:
        leader = None
        for member in group['members']:
            variable_id = f"{group['id']}" if leader is None else _member_variable_id(group['id'], member['device_id'])
            row = dict(variable_id=variable_id, instance_path=member['device_id'], parameter_name=member['parameter'],
                       unit=group['unit'], scale=group.get('scale', 'linear'),
                       value_type='integer' if group.get('domain') == 'integer' else 'continuous')
            if leader is None:
                row.update(lower=group['lower'], upper=group['upper'], step=group.get('step'),
                           optimized=group.get('mutable', True))
                leader = variable_id
            else:
                row.update(binding_group=leader, ratio=member.get('ratio', 1.0))
            parameters.append(row)
    return dict(
        project=starter_project(task_key),
        circuit=dict(source='registered_task', task_id=task_key, circuit_class=info['circuit_class'],
                     pdk_id=info.get('pdk_id', MOCK_PDK)),
        parameters=parameters,
        measurements=[dict(measurement_id='m_score', analysis='other', result_source='backend_profile',
                           source_name='score', unit='fixture',
                           notes='Analytic toy score from the MOCK backend; not a circuit measurement.')],
        targets=[dict(metric_id='score', equation='m_score', unit='fixture', constraint='>=', lower=0.95,
                      normalization_scale=1.0, basis='Mock acceptance threshold for plumbing tests only.')],
        run=dict(max_evaluations=60, seed=17))
