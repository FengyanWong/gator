"""Task providers: what circuit is optimized and which EXISTING backend evaluates it.

* ``synthetic:*`` tasks use the optimizer's explicit analytic toy backend
  (``SyntheticSizingBackend``). They are MOCK: origin=synthetic, provenance=mock, their
  ``score`` is not a circuit metric, and their data is confined to the mock output root.
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
import sys

from .paths import local_settings_dir, repo_root

# Normalized toy optimum per parameter kind for the analytic mock objective. Arbitrary by
# construction: the mock backend checks plumbing, never electrical behaviour.
MOCK_TARGETS = {'w': 0.4, 'l': -0.2, 'm': 0.0, 'nf': 0.0, 'r': 0.3, 'c': -0.3, 'ind': 0.1, 'dc': 0.2}

SYNTHETIC_FIXTURES = {
    'opamp': dict(netlist='tests/fixtures/synthetic/opamp.scs', config='configs/opamp.json', circuit_class='opamp'),
    'opamp_two_stage': dict(netlist='tests/fixtures/synthetic/opamp_two_stage.scs',
                            config='configs/opamp_two_stage.json', circuit_class='opamp'),
    'ldo': dict(netlist='tests/fixtures/synthetic/ldo.scs', config='configs/ldo.json', circuit_class='ldo'),
    'vco': dict(netlist='tests/fixtures/synthetic/vco.scs', config='configs/vco.json', circuit_class='vco'),
}

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

REAL_INTERFACE_CONTRACT = dict(
    environment_factory='analog_optimizer.training.parallel.NativeEnvironmentFactory(config, profile, specs, output, '
                        'max_steps, timeout_seconds, reference_metrics)',
    bridge_config='analog_optimizer.backends.virtuoso_bridge.BridgeConfig(env_file, library, creation_receipt, '
                  'state_root, model_file, section, profile)',
    connection_file=str(Path('configs/local/workbench/bridge_connection.json')),
    connection_file_format='{"active": "<id>", "profiles": {"<id>": {...keys below...}}}',
    connection_file_keys=['env_file', 'library', 'creation_receipt', 'model_file', 'profile (optional)',
                          'reference_measurements', 'bridge_site_packages (optional)'],
    requirements=['virtuoso-bridge 0.8.0 importable by the backend interpreter',
                  'an ALREADY RUNNING bridge tunnel (automatic startup is disabled by the adapter)',
                  'a dedicated Virtuoso session; no ADE/Maestro window open on the design',
                  'verified real baseline measurements for the selected profile'],
    max_concurrency=4,
    note='Native CDF preparation is serialized by the existing preparation service; only Spectre runs in parallel.')


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

    def __call__(self, lane):
        from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        kinds = {g.parameter_kind for g in self.graph.parameter_groups if g.mutable}
        backend = SyntheticSizingBackend(self.graph, targets={k: self.targets[k] for k in kinds})
        return CircuitSizingEnv(backend, self.graph, self.specs, Path(self.work_root) / f'worker-{lane}',
                                max_steps=self.max_steps, timeout_seconds=self.timeout_seconds,
                                stop_on_success=self.stop_on_success, expected_origin='synthetic')


def _synthetic_builder(compiled, work_root, run_settings):
    adv = run_settings.advanced
    return SyntheticEnvFactory(compiled.graph, compiled.specs, dict(MOCK_TARGETS), str(work_root),
                               adv.episode_length, adv.simulation_timeout_seconds,
                               adv.episode_terminates_on_success)


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


def list_tasks():
    tasks = []
    for name, info in SYNTHETIC_FIXTURES.items():
        tasks.append(dict(task_key=f'synthetic:{name}', kind='mock', circuit_class=info['circuit_class'],
                          available=True, description='Analytic toy objective on a synthetic fixture netlist. '
                                                      'MOCK data; not a circuit result.'))
    for name, info in REAL_PROFILES.items():
        blocker = real_backend_blocker()
        tasks.append(dict(task_key=f'real:{name}', kind='real', circuit_class=info['circuit_class'],
                          available=blocker is None, blocker=blocker,
                          description='Verified GPDK045 bridge profile (Virtuoso + Spectre).'))
    return tasks


def bridge_importable() -> bool:
    return importlib.util.find_spec('virtuoso_bridge') is not None


def _profile_settings(profile_id=None):
    from .connection import load_profiles
    loaded = load_profiles()
    key = profile_id or loaded['active']
    return loaded, (loaded['profiles'].get(key) if key else None)


def real_backend_blocker(profile_id=None):
    loaded, settings = _profile_settings(profile_id)
    if not loaded['exists'] or not loaded['profiles']:
        return (f"No bridge connection profile is configured ({loaded['file']}). The backend never guesses hosts, "
                'libraries, accounts or model paths.')
    if settings is None:
        return f'Connection profile {profile_id!r} is not configured.'
    if settings.get('bridge_site_packages'):
        import site
        site.addsitedir(str(Path(settings['bridge_site_packages']).resolve()))
    if not bridge_importable():
        return (f'virtuoso_bridge is not importable by the backend interpreter ({sys.executable}). It is installed '
                'only in another virtualenv. Install virtuoso-bridge 0.8.0 into this interpreter, or set '
                '"bridge_site_packages" for the profile in configs/local/workbench/bridge_connection.json.')
    missing = [k for k in ('env_file', 'library', 'creation_receipt', 'model_file', 'reference_measurements')
               if not settings.get(k)]
    if missing:
        return f'The connection profile lacks {missing}, which a real run needs.'
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
                                    circuit_class=info['circuit_class'], pdk_id='synthetic-fixture',
                                    top=circuit.dut_hierarchy)
        if kind == 'real' and name in REAL_PROFILES:
            blocker = real_backend_blocker(profile_id)
            if blocker:
                raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
            if not allow_real:
                raise TaskBlocked('Real Virtuoso/Spectre execution requires an explicit user action with an '
                                  'authorized budget; it is never started implicitly.',
                                  contract=REAL_INTERFACE_CONTRACT)
            return _real_runtime(key, name, profile_id)
        raise TaskBlocked(f'Unknown registered task {key!r}')
    if circuit.source == 'netlist':
        if not circuit.netlist_path or not circuit.parser_config_path:
            raise TaskBlocked('A netlist source needs netlist_path and parser_config_path; device port order and '
                              'parameter semantics are never guessed.')
        return _netlist_runtime(f'netlist:{Path(circuit.netlist_path).name}', circuit.netlist_path,
                                circuit.parser_config_path, circuit_class=circuit.circuit_class,
                                pdk_id=circuit.pdk_id, top=circuit.dut_hierarchy,
                                notes=['Imported netlists can only be evaluated by the MOCK analytic backend: the '
                                       'repository has no generic real simulator runner for arbitrary netlists.'])
    if circuit.source == 'virtuoso':
        raise TaskBlocked('Optimizing an arbitrary native cellview needs a verified circuit profile (writable '
                          'parameters, CDF rules, analyses, measurements). Existing profiles: '
                          + ', '.join(f'real:{n}' for n in REAL_PROFILES), contract=REAL_INTERFACE_CONTRACT)
    raise TaskBlocked(f'Unsupported circuit source {circuit.source!r}')


def _real_runtime(task_key, name, profile_id=None):
    """Assemble the verified native factory. Only reachable with the bridge importable, a
    connection file present and an explicit user action (allow_real)."""
    import importlib
    import site
    info, root = REAL_PROFILES[name], repo_root()
    connection = _profile_settings(profile_id)[1]
    if connection.get('bridge_site_packages'):
        site.addsitedir(str(Path(connection['bridge_site_packages']).resolve()))
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
    module_name, _, class_name = info['profile'].partition(':')
    module = importlib.import_module(module_name)
    candidates = [getattr(module, class_name)] if class_name else [
        value for key, value in vars(module).items() if key.endswith('Profile') and isinstance(value, type)
        and value.__module__ == module.__name__]
    if len(candidates) != 1:
        raise TaskBlocked(f'Cannot identify the circuit profile class in {module_name}')
    profile = candidates[0](design_file=root / info['design'], mapping_file=root / info['mapping'],
                            reference_structure=root / info['structure'], reference_readback=root / info['readback'])
    config = BridgeConfig(Path(connection['env_file']).resolve(), connection['library'],
                          Path(connection['creation_receipt']).resolve(),
                          (root / 'artifacts/local/bridge-state').resolve(), connection['model_file'],
                          profile=connection.get('profile'))
    reference = json.loads(Path(connection['reference_measurements']).read_text())
    if reference.get('origin') != 'real':
        raise TaskBlocked('reference_measurements must be verified REAL baseline measurements')
    graph = profile.optimization_graph()

    def builder(compiled, work_root, run_settings):
        from analog_optimizer.training.parallel import NativeEnvironmentFactory
        from analog_optimizer.envs.sizing import graph_contract
        if graph_contract(compiled.graph) != graph_contract(graph):
            raise TaskBlocked('A real profile fixes its writable parameters and legal grid. The configured variables '
                              'differ from the verified profile; real action permissions are not widened from the UI.')
        adv = run_settings.advanced
        return NativeEnvironmentFactory(config, profile, compiled.specs, Path(work_root), adv.episode_length,
                                        adv.simulation_timeout_seconds, reference['metrics'])
    circuit = dict(circuit_class=info['circuit_class'], pdk_id='gpdk045', dut_hierarchy=None,
                   netlist_sha256=_sha256(root / info['structure']), parser_config_sha256=_sha256(root / info['mapping']),
                   netlist_file=str(root / info['structure']), parser_config_file=str(root / info['mapping']),
                   topology_id=f'profile:{name}', complete=True, evaluation_backend='virtuoso_bridge + Spectre (REAL)')
    metrics = tuple(reference['metrics'])
    return TaskRuntime(task_key, 'real', graph, metrics, circuit, (root / info['structure']).read_text(),
                       str(root / info['structure']), str(root / info['mapping']), builder, max_concurrency=4)


def starter_config(task_key: str) -> dict:
    """A valid starting configuration for a registered synthetic task, derived from the fixture's own
    declared parameter groups. A convenience for manual editing; every field stays editable."""
    from analog_optimizer.netlist.config import ParserConfig
    kind, _, name = task_key.partition(':')
    if kind != 'synthetic' or name not in SYNTHETIC_FIXTURES:
        raise KeyError(task_key)
    root, info = repo_root(), SYNTHETIC_FIXTURES[name]
    parser_config = ParserConfig.from_file(root / info['config'])
    parameters = []
    for group in parser_config.parameter_groups:
        leader = None
        for member in group['members']:
            variable_id = f"{group['id']}" if leader is None else f"{group['id']}__{member['device_id']}"
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
        project=dict(name=f'mock-{name}', task_name=f'mock_{name}'),
        circuit=dict(source='registered_task', task_id=task_key, circuit_class=info['circuit_class'],
                     pdk_id='synthetic-fixture'),
        parameters=parameters,
        measurements=[dict(measurement_id='m_score', analysis='other', result_source='backend_profile',
                           source_name='score', unit='fixture',
                           notes='Analytic toy score from the MOCK backend; not a circuit measurement.')],
        targets=[dict(metric_id='score', measurement_id='m_score', unit='fixture', constraint='>=', lower=0.95,
                      normalization_scale=1.0, basis='Mock acceptance threshold for plumbing tests only.')],
        run=dict(max_evaluations=60, seed=17))
