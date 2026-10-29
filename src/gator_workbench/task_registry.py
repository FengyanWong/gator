"""The registered tasks' facts that other modules need without loading a task: the verified circuits and the names that
stay reserved, the MOCK stand-ins a test registers, the messages that refuse a removed or unrunnable task, the task
runtime's shape, and which result registry a verified circuit brings.

Moved from tasks.py by the refactoring (docs/plan-refactoring.md): compile, validation, profiles, runs and
ngspice_tasks imported these lazily from tasks, which closed an import cycle through profiles. tasks.py re-exports
every name except SYNTHETIC_FIXTURES, which is read as task_registry.SYNTHETIC_FIXTURES so that a test's patch of it
reaches every reader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path

from . import task_names
from .paths import repo_root


# No MOCK task in the workbench (user request 2026-09-30, status record 7.128; before it the one MOCK task was
# synthetic:gpdk045_ota5, the GPDK045 OTA5 netlist and mapping on the free toy backend). The toy backend stays for the
# tests: they register their stand-in - that same circuit - through a JSON file ({name: dict(netlist, config,
# circuit_class, pdk_id, description)}) named by this variable, which every child process (run worker, lane) inherits.
# A model a MOCK run trains can never load into a real run (runs: mock_isolation).
ENV_SYNTHETIC_FIXTURES = 'GATOR_WORKBENCH_SYNTHETIC_FIXTURES'


# Lanes a real task may run at once: the optimizer's MAX_SPECTRE_WORKERS (native_preparation.py), 4 until record 7.143.
REAL_LANES = 6


def _registered_fixtures() -> dict:
    path = os.environ.get(ENV_SYNTHETIC_FIXTURES)
    return json.loads(Path(path).read_text()) if path else {}


SYNTHETIC_FIXTURES = _registered_fixtures()


# What an entry that names no PDK / description gets (a circuit a test registers for itself, e.g. test_wb_pdk's demo).
MOCK_PDK, MOCK_DESCRIPTION = (
    'synthetic-fixture'
), (
    'MOCK: the analytic toy backend on a fixture netlist. Its score is not a circuit result.'
)


REMOVED_MOCK_TASKS = ('synthetic:opamp', 'synthetic:opamp_two_stage', 'synthetic:ldo', 'synthetic:vco',
    'synthetic:gpdk045_ota5')


MOCK_TASK_REMOVED = (
    '{task} no longer exists: the workbench has no MOCK task since 2026-09-30 (user request). Choose one of '
                     'your saved tasks under "Task".')


REAL_PROFILES = {
    'gpdk045_ota5': dict(profile='analog_optimizer.backends.gpdk045:Gpdk045OtaProfile', circuit_class='opamp',
                         design='configs/gpdk045_opamp_design.json', mapping='configs/gpdk045_opamp.json',
                         structure='examples/circuits/gpdk045_ota5.scs',
                         readback='examples/circuits/gpdk045_ota5.cdf.json'),
    'gpdk045_vco': dict(profile='analog_optimizer.backends.gpdk045_vco', circuit_class='vco',
                        design='configs/gpdk045_vco_design.json', mapping='configs/gpdk045_vco.json',
                        structure='examples/circuits/gpdk045_vco.scs',
                        readback='examples/circuits/gpdk045_vco.cdf.json'),
}


# Built-in tasks REMOVED on user request (2026-09-23, status record 7.73): their example cells - GATOR_TESTS/ota5_v1
# and vco_m6_v1 with their testbenches - were deleted from Virtuoso (backup:
# artifacts/local/example-cells-deleted-2026-09-23/). Their entries stay in REAL_PROFILES on purpose: the names stay
# reserved (a saved task cannot take over a name that old runs and the M5/M6 record use), the tests' MOCK stand-in
# runs on the OTA5 netlist and mapping, and test_wb_generic_profile still compares the generated profile with the
# hand-written ones. What offers, starts or checks a task goes through offered_real_profiles() and refuses these in
# words, like REMOVED_MOCK_TASKS. OTA7 and LDO followed on 2026-09-30 (user request, record 7.128) with their example
# netlists and configurations, so their entries left REAL_PROFILES too; their names stay reserved all the same
# (profiles.save_task refuses every name in REMOVED_REAL_TASKS). The optimizer package's own profiles for them stay,
# as research code, and run from a checkout before that commit.
REMOVED_REAL_TASKS = ('real:gpdk045_ota5', 'real:gpdk045_vco', 'real:gpdk045_ota7', 'real:gpdk045_ldo')


# The TARGETS OF RECORD of the verified circuits: the frozen specification files of the real experiments, as (file, keys
# down to the list of specs). Pilot goals near each circuit's measured baseline - not product specifications. They are
# what the Specs tab shows when such a task is chosen (starter_config); `train` is the partition a run from scratch
# belongs to.
REAL_TARGETS_OF_RECORD = {
    'gpdk045_ota5': ('configs/m6_real_cross_category.json', 'classes', 'opamp', 'specs', 'train'),
    'gpdk045_vco': ('configs/m6_real_cross_category.json', 'classes', 'vco', 'specs', 'train'),
}


# The VCO results are not in the optimizer's default result registry (score + the op-amp results) and the UI has no
# editor for the registry, so a target on them could not even be stated. That task brought the registry of record of the
# real cross-category experiment (so did the LDO task until 2026-09-30), the way a generated profile brings its own
# (profiles.task_spec_registry). The OTA task stayed on the default registry.
REAL_REGISTRY_OF_RECORD = {'gpdk045_vco': 'configs/m6_real_cross_category.json'}


# Which analysis of the circuit profiles produces a result: the label on its Probes row. Everything else is a DC
# operating point, except that an oscillator's results all come from its transient run.
RESULT_ANALYSIS = dict.fromkeys(('gain_db_at_start', 'gain_reference_hz', 'bandwidth_3db_hz', 'unity_gain_hz',
                                 'phase_margin_estimate_deg', 'unity_downward_crossings', 'ldo_psrr_1khz_db'), 'ac')


RESULT_ANALYSIS.update(dict.fromkeys(('ldo_step_deviation_v', 'ldo_step_final_shift_v', 'ldo_step_tail_ripple_v'),
    'tran'))


REAL_INTERFACE_CONTRACT = dict(
    environment_factory='analog_optimizer.training.parallel.NativeEnvironmentFactory(config, profile, specs, output, '
                        'max_steps, timeout_seconds, reference_metrics)',
    bridge_config='analog_optimizer.backends.virtuoso_bridge.BridgeConfig(env_file, library, creation_receipt, '
                  'state_root, model_file, section, profile)',
    connection_file=str(Path('configs/local/workbench/bridge_connection.json')),
    connection_file_format='{"active": "<id>", "profiles": {"<id>": {...keys below...}}}',
    connection_file_keys=['env_file', 'library', 'model_file', 'profile (optional)', 'bridge_site_packages (optional)',
                          'circuits: {"<task name, e.g. gpdk045_vco>": {"creation_receipt": ..., '
                          '"reference_measurements": ...}}',
                          'creation_receipt + reference_measurements at the top level (older single-circuit form; used '
                          'only for a circuit without its own "circuits" entry)'],
    requirements=['virtuoso-bridge 0.8.0 importable by the backend interpreter',
                  'an ALREADY RUNNING bridge tunnel (automatic startup is disabled by the adapter)',
                  'a dedicated Virtuoso session; no ADE/Maestro window open on the design',
                  'verified real baseline measurements for the selected profile'],
    max_concurrency=REAL_LANES,
    note='Native CDF preparation is serialized by the existing preparation service; only Spectre runs in parallel.')


REAL_AUTHORIZATION_REQUIRED = (
    'Real Virtuoso/Spectre execution requires an explicit user action with an authorized budget; '
                               'it is never started implicitly.')


class TaskBlocked(RuntimeError):
    """The task cannot be evaluated here. Carries the blocker; never replaced by mock data."""
    def __init__(self, message, *, contract=None):
        super().__init__(message)
        self.contract = contract


@dataclass
class TaskRuntime:
    # A task's circuit, provenance and environment-factory contract with its execution limits and authorization.
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
    notes: list = field(default_factory=list)
    authorized: bool = True            # False = a real task loaded to be SHOWN and validated only: it cannot execute
    # verified REAL results of the INITIAL design: {metric: {value, unit}}; None if unknown
    reference_metrics: dict | None = None
    connection_family: str = 'virtuoso'     # which family of connection a real run needs: virtuoso (Spectre) or ngspice

    @property
    def mock(self) -> bool:
        return self.origin == 'synthetic'


def starter_project(task_key, shown=None) -> dict:
    """The project / task name a task's starter gives: what a run is filed under (runs/<task_name>/) until the user names
    it. Listed with every task, so the page can tell a name nobody typed from one the user chose. A renamed task (record
    7.302, task_names) gives the name it is shown under; `shown`: that name when the caller read it already."""
    kind, _, name = task_key.partition(':')
    shown = task_names.shown(task_key) if shown is None else shown
    if shown != name:
        return dict(name=shown.replace('_', '-'), task_name=shown)
    return (dict(name=f"mock-{name.replace('_', '-')}", task_name=f'mock_{name}') if kind == 'synthetic'
            else dict(name=name.replace('_', '-'), task_name=name))


def offered_real_profiles() -> dict:
    """The verified circuits offered as tasks: REAL_PROFILES without REMOVED_REAL_TASKS."""
    return {name: info for name, info in REAL_PROFILES.items() if f'real:{name}' not in REMOVED_REAL_TASKS}


def real_task_removed(task) -> str:
    """Explain when a retired built-in task was removed and how to select a saved real task."""
    when = '2026-09-30' if task in ('real:gpdk045_ota7', 'real:gpdk045_ldo') else '2026-09-23'
    return (
        f'{task} no longer exists: the built-in verified tasks were removed on user request (this one on {when}). The '
            'real tasks are the ones you save from a Virtuoso cell; choose one under "Task".')


# The tasks that train at corners. None since 2026-09-30: the only one, real:gpdk045_ota7, was removed (record 7.128).
CORNER_TASKS = frozenset()


def training_capabilities(task_key):
    """Describe whether a task supports corner training and which condition policies it offers."""
    corners = task_key in CORNER_TASKS
    return dict(corners=corners, policies=['off', 'after_nominal', 'always'] if corners else ['off'])


NETLIST_SOURCE_REMOVED = (
    'The workbench no longer imports Spectre netlist files. Choose a registered task or a Virtuoso '
                          'cell under "Circuit source".')


NATIVE_DRAFT_NOT_EXECUTABLE = ('This cell was read from Virtuoso, but it has no circuit profile yet, so it cannot be '
                               'simulated or optimized: a profile fixes which sizes may be written and in which steps, '
                               'which testbench runs, and how results are measured.')


def verified_profile(name):
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


def verified_spec_registry(circuit):
    (
        '(version, entries) of the result registry a VERIFIED circuit brings along (REAL_REGISTRY_OF_RECORD), '
        'else None.'
    )
    task_id = getattr(circuit, 'task_id', None) or ''
    if getattr(circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return None
    file = REAL_REGISTRY_OF_RECORD.get(task_id[len('real:'):])
    if file is None:
        return None
    record = json.loads((repo_root() / file).read_text())['schema']
    return record['version'], [dict(metric_id=name, unit=unit, reference=reference) for name, unit,
        reference in record['metrics']]


def fixed_by_verified_profile(runtime) -> bool:
    """Whether a loaded task's Parameters rows are fixed by a verified built-in circuit profile (a run accepts exactly
    those): real:<name> of REAL_PROFILES, not a profile generated from a cell."""
    name = runtime.task_key.partition(':')[2]
    return runtime.task_key.startswith('real:') and name in REAL_PROFILES and not runtime.circuit.get(
        'generated_profile')


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_verified_profile = verified_profile
