"""Task providers: what circuit is optimized and which EXISTING backend evaluates it.

* ``synthetic:*`` tasks use the optimizer's explicit analytic toy backend
  (``SyntheticSizingBackend``). They are MOCK: origin=synthetic, provenance=mock, their
  ``score`` is not a circuit metric, and their data is confined to the mock output root.
  The workbench offers NONE since 2026-09-30 (user request, status record 7.128): the last
  one, ``synthetic:gpdk045_ota5``, is in ``REMOVED_MOCK_TASKS`` with the four it had replaced.
  A test, or a browser check's scratch backend, registers its own through the file named by
  ``GATOR_WORKBENCH_SYNTHETIC_FIXTURES`` (``tests/workbench/fixtures/synthetic_fixtures.json``).
* The ``netlist`` source (a Spectre netlist file imported by path) was removed on user
  request (status record 7.53). The schema still reads it, so configurations and runs
  saved before stay readable, but no circuit is loaded from it: ``NETLIST_SOURCE_REMOVED``.
* ``ngspice:*`` tasks are SPICE decks the user saved in the ngspice window (``ngspice_tasks``): REAL circuit
  simulations by ngspice, on this machine or over ssh, through an ngspice connection; no license, no Virtuoso.
* ``real:*`` tasks describe the verified GPDK045 bridge profiles. They are only
  runnable when the backend interpreter can import ``virtuoso_bridge`` and the operator
  supplied a connection file. Otherwise the precise blocker and the interface contract
  are returned. Nothing falls back to mock. All four were removed on user request:
  OTA5 and VCO on 2026-09-23 (status record 7.73, their example cells deleted from
  Virtuoso), OTA7 and LDO on 2026-09-30 (record 7.128, their example files deleted too):
  ``REMOVED_REAL_TASKS``. The real tasks are the ones saved from a Virtuoso cell.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

from . import caches, model_library, native_cells, task_names, task_registry
from .connection import KINDS, family_of, named_or_active, profile_kind
from .paths import bridge_env_snapshot, bridge_session_dir, bridge_state_dir, connection_file, repo_root
from .spec_equations import EquationNativeFactory
from .storage.atomic import sha256_file as _sha256
# re-exported: moved to task_registry.py by the refactoring (docs/plan-refactoring.md)
from .task_registry import (ENV_SYNTHETIC_FIXTURES, REAL_LANES, _registered_fixtures, MOCK_PDK, MOCK_DESCRIPTION,
                            REMOVED_MOCK_TASKS, MOCK_TASK_REMOVED, REAL_PROFILES, REMOVED_REAL_TASKS,
                            REAL_TARGETS_OF_RECORD, REAL_REGISTRY_OF_RECORD, RESULT_ANALYSIS, REAL_INTERFACE_CONTRACT,
                            REAL_AUTHORIZATION_REQUIRED, TaskBlocked, TaskRuntime, starter_project,
                            offered_real_profiles, real_task_removed, CORNER_TASKS, training_capabilities,
                            NETLIST_SOURCE_REMOVED, NATIVE_DRAFT_NOT_EXECUTABLE, _verified_profile, verified_profile,
                            verified_spec_registry)

# Normalized toy optimum per parameter kind for the analytic mock objective. Arbitrary by
# construction: the mock backend checks plumbing, never electrical behaviour.
MOCK_TARGETS = {'w': 0.4, 'l': -0.2, 'm': 0.0, 'nf': 0.0, 'r': 0.3, 'c': -0.3, 'ind': 0.1, 'dc': 0.2}


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
    reward_settings: object = None    # measurements.specs.RewardSettings: the run's settings, the same ones the learner enforces

    def __call__(self, lane):
        from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        kinds = {g.parameter_kind for g in self.graph.parameter_groups if g.mutable}
        backend = SyntheticSizingBackend(self.graph, targets={k: self.targets[k] for k in kinds})
        if self.plan is not None:
            self.plan.wrap(backend)
        return CircuitSizingEnv(backend, self.graph, self.specs, Path(self.work_root) / f'worker-{lane}',
                                max_steps=self.max_steps, timeout_seconds=self.timeout_seconds,
                                stop_on_success=self.stop_on_success, expected_origin='synthetic',
                                reward_settings=self.reward_settings)


def _synthetic_builder(compiled, work_root, run_settings):
    from analog_optimizer.measurements.specs import RewardSettings
    adv = run_settings.advanced
    return SyntheticEnvFactory(compiled.graph, compiled.specs, dict(MOCK_TARGETS), str(work_root),
                               adv.episode_length, adv.simulation_timeout_seconds,
                               adv.episode_terminates_on_success, compiled.plan,
                               RewardSettings(**run_settings.reward.model_dump()))


def _with_computed_specs(factory, compiled):
    """The verified real factory, unchanged when every spec is a simulator result itself; otherwise wrapped so that the
    specs computed from the probes reach the reward (spec_equations.EquationNativeFactory)."""
    if not compiled.plan.injected and not compiled.plan.sizes:        # sizes: probes worked out from the sizes (record 7.308)
        return factory
    return EquationNativeFactory(factory, compiled.plan)


def _netlist_runtime(task_key, netlist, parser_config, *, circuit_class, pdk_id, top=None, notes=()):
    netlist, parser_config = Path(netlist), Path(parser_config)
    graph = parse_netlist(netlist, parser_config, top=top)
    digest = _sha256(netlist)                          # one hash for both fields: each read of the netlist is a 9p round trip
    circuit = dict(circuit_class=circuit_class, pdk_id=pdk_id, dut_hierarchy=top,
                   netlist_sha256=digest, parser_config_sha256=_sha256(parser_config),
                   netlist_file=str(netlist), parser_config_file=str(parser_config),
                   topology_id=f'netlist-sha256:{digest[:16]}', complete=graph.complete,
                   evaluation_backend='analytic-toy-sizing-v1 (MOCK: quadratic score, not a circuit simulation)')
    return TaskRuntime(task_key, 'synthetic', graph, ('score',), circuit, netlist.read_text(), str(netlist),
                       str(parser_config), _synthetic_builder, notes=list(notes))


def list_tasks():
    tasks = []
    for name, info in task_registry.SYNTHETIC_FIXTURES.items():
        tasks.append(dict(task_key=f'synthetic:{name}', kind='mock', circuit_class=info['circuit_class'],
                          pdk_id=info.get('pdk_id', MOCK_PDK), available=True, description=info.get('description', MOCK_DESCRIPTION)))
    for name, info in offered_real_profiles().items():
        blocker = real_backend_blocker(None, name)               # each circuit has its own receipt and baseline
        tasks.append(dict(task_key=f'real:{name}', kind='real', circuit_class=info['circuit_class'], pdk_id='gpdk045',
                          available=blocker is None, blocker=blocker,
                          description='Verified GPDK045 bridge profile (Virtuoso + Spectre).'))
    from . import profiles  # lazy: profiles imports the optimizer (torch)
    # What keeps a generated task from running is the same for all of them (the active connection), and each task's
    # reference is read once: both were read per task, the reference twice (record 7.279; 141 file opens per list).
    shared_blocker = None
    for name, entry in profiles.list_profiles().items():         # created from a cell read out of Virtuoso
        if entry.get('recipe') == profiles.MAESTRO and not entry.get('runnable'):
            blocker = profiles.MAESTRO_NOT_RUNNABLE
        else:
            if shared_blocker is None:
                shared_blocker = (generated_backend_blocker(None),)
            blocker = shared_blocker[0]
        reference = profiles.reference_metrics(name)
        tasks.append(dict(task_key=f'real:{name}', kind='real', circuit_class=entry['circuit_class'], generated=True,
                          pdk_id=entry.get('pdk_id') or 'gpdk045', available=blocker is None, blocker=blocker, library=entry['library'], cell=entry['core_cell'],
                          revision=entry.get('revision'), measurement=entry.get('measurement'), original=entry.get('original'),
                          verified=reference is not None,
                          # The task window (record 7.227) shows these facts of the saved task: all from its entry, no other file read.
                          testbench=entry.get('testbench_cell'), saved_utc=entry.get('saved_utc'), created_utc=entry.get('created_utc'),
                          baseline_recorded_utc=entry.get('baseline_recorded_utc'), status=entry.get('status'),
                          variables=len(entry.get('optimized_variables') or ()), results=len(entry.get('provided_metrics') or ()),
                          description=f"Profile generated from {entry['library']}/{entry['core_cell']} (Virtuoso + Spectre). "
                                      + ('' if reference else 'No real baseline recorded yet.')))
    from . import ngspice_tasks  # lazy: ngspice_tasks imports the optimizer (torch)
    tasks.extend(ngspice_tasks.task_entries())                 # SPICE decks saved in the ngspice window
    given, keys = task_names.names(), [task['task_key'] for task in tasks]
    for task in tasks:
        # The name the windows show (record 7.302): the task's own unless it was renamed. Its key never changes.
        task['name'] = task_names.shown(task['task_key'], given, keys)
        task['starter_project'] = starter_project(task['task_key'], task['name'])
        task['training_capabilities'] = training_capabilities(task['task_key'])
    return tasks


def bridge_importable() -> bool:
    return importlib.util.find_spec('virtuoso_bridge') is not None


def profile_settings(profile_id=None):
    loaded, _, settings = named_or_active(profile_id)
    return loaded, settings


def _not_a_virtuoso_connection(profile_id, settings):
    """Every real task here is a Virtuoso + Spectre testbench. A connection of another kind (ngspice) is named as
    such, instead of being reported as a Virtuoso profile with missing settings."""
    kind = profile_kind(settings)
    if kind is None or family_of(kind) == 'virtuoso':
        return None                                   # an unknown kind is named by the connection check itself
    return (f'Connection {profile_id or "(the active one)"!r} is "{KINDS[kind]["label"]}". This circuit runs on Virtuoso + '
            'Spectre: choose a Virtuoso connection in the Connection window. An ngspice connection runs the ngspice netlist '
            'tasks (Project column: "ngspice netlist...").')


def bridge_config_of(connection):
    """The BridgeConfig of a real task's bindings (`real_bindings` of its connection): the env file, library, creation
    receipt and model file it names, and the adapter's state folder. These older, built-in tasks run with the verified
    adapter and factory as they are, which take no lock of their cell (record 7.311): they stay in the first Virtuoso
    session. (A task saved from a cell runs in any session: its adapter locks its cell, `cdf_write.backend_class`.)"""
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
    env_file = bridge_env_snapshot(connection['env_file'])                                    # its own copy: record 7.306
    _first_session_only(env_file, connection, 'This task')
    return BridgeConfig(env_file, connection['library'], Path(connection['creation_receipt']).resolve(),
                        bridge_state_dir().resolve(), connection['model_file'],
                        profile=connection.get('profile'))


def _first_session_only(env_file, connection, what):
    """Refuse a further Virtuoso session for a task whose adapter does not lock its cell (record 7.311)."""
    if bridge_session_dir(env_file, connection.get('profile')) != bridge_state_dir():
        raise TaskBlocked(f'{what} is written by the older adapter, which does not lock its cell: it runs in the first Virtuoso '
                          f'session only, and this connection reaches another (bridge profile {connection.get("profile")!r}). '
                          'Choose a connection of the first session.')


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


def _link_problem(profile_id, not_importable):
    """(why the connection profile cannot reach a real bridge here, or None; the profiles file; the profile's settings).
    `not_importable`: what to do when the bridge package is missing, completed with where to set it."""
    loaded, settings = profile_settings(profile_id)
    if not loaded['exists'] or not loaded['profiles']:
        return (f"No bridge connection profile is configured ({loaded['file']}). The backend never guesses hosts, "
                'libraries, accounts or model paths.'), loaded, settings
    if settings is None:
        return f'Connection profile {profile_id!r} is not configured.', loaded, settings
    wrong_kind = _not_a_virtuoso_connection(profile_id, settings)
    if wrong_kind:
        return wrong_kind, loaded, settings
    if settings.get('bridge_site_packages'):
        import site
        site.addsitedir(str(Path(settings['bridge_site_packages']).resolve()))
    if not bridge_importable():
        return (f'virtuoso_bridge is not importable by the backend interpreter ({sys.executable}). {not_importable} for the '
                'profile in configs/local/workbench/bridge_connection.json.'), loaded, settings
    return None, loaded, settings


def real_backend_blocker(profile_id=None, name=None):
    """Why real execution is impossible here, or None. With `name`, the per-circuit bindings of that
    registered real task are checked as well."""
    problem, loaded, settings = _link_problem(profile_id, 'It is installed only in another virtualenv. Install virtuoso-bridge '
                                              '0.8.0 into this interpreter, or set "bridge_site_packages"')
    if problem:
        return problem
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
        if not key:
            raise TaskBlocked('No task is chosen: choose one under "Task".')
        kind, _, name = key.partition(':')
        if kind == 'synthetic' and name in task_registry.SYNTHETIC_FIXTURES:
            info = task_registry.SYNTHETIC_FIXTURES[name]
            return _netlist_runtime(key, root / info['netlist'], root / info['config'],
                                    circuit_class=info['circuit_class'], pdk_id=info.get('pdk_id', MOCK_PDK),
                                    top=circuit.dut_hierarchy)
        if key in REMOVED_MOCK_TASKS:
            raise TaskBlocked(MOCK_TASK_REMOVED.format(task=key))
        if key in REMOVED_REAL_TASKS:
            raise TaskBlocked(real_task_removed(key))
        if kind == 'real' and name not in REAL_PROFILES:
            from . import profiles  # lazy: profiles imports the optimizer (torch)
            if profiles.profile_entry(name) is not None:
                blocker = generated_backend_blocker(profile_id)
                if blocker:
                    raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
                return _generated_runtime(key, name, profile_id, authorized=bool(allow_real))
        if kind == 'ngspice' and name:
            from . import ngspice_tasks  # lazy: ngspice_tasks imports the optimizer (torch)
            return ngspice_tasks.runtime(key, name, profile_id, authorized=bool(allow_real))
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
        raise TaskBlocked(NETLIST_SOURCE_REMOVED)
    if circuit.source == 'virtuoso':
        imported = native_cells.load_import(circuit.library, circuit.cell) if circuit.library and circuit.cell else None
        if imported is None or allow_real:                   # allow_real = a run start: a cell without a profile never executes
            raise TaskBlocked((NATIVE_DRAFT_NOT_EXECUTABLE if imported else
                               'Optimizing an arbitrary native cellview needs a verified circuit profile (writable '
                               'parameters, CDF rules, analyses, measurements).') + ' Existing profiles: '
                              + ', '.join(f'real:{n}' for n in offered_real_profiles()), contract=REAL_INTERFACE_CONTRACT)
        return _native_draft_runtime(imported, circuit)
    raise TaskBlocked(f'Unsupported circuit source {circuit.source!r}')


# ---- a saved task as the page loads it: kept while its files are unchanged ----------------------------------------------
# Loading a GENERATED task (real:<name>, saved from a cell) opens ~43 files - every saved task's entry three times, its own
# folder, the connection file - and rebuilds its form writer: 0.3-1 s on the 9p-mounted D: drive, at EVERY edit of the
# page (validation, task load, Matched devices, the saved-model check; review of 2026-10-01). The page's loads keep the
# runtime while none of the files it is built from changed; the link and the model file are checked at every call, as
# before. A run never takes this path: it loads with the authorization (load_task(allow_real=True)).
_VIEW_LIMIT = 16
_view_cache: dict = {}


def _view_stamp(name):
    """(name, size, mtime) of what a generated task is built from - its folder and every file in it, the folder of saved
    tasks, the connection file, the conditions file - or None when one of them cannot be read (then nothing is kept)."""
    from . import profiles  # lazy: profiles imports the optimizer (torch)
    try:
        store = profiles.store_root()
        folder = store / name
        parts = [(str(store), 0, store.stat().st_mtime_ns), (str(folder), 0, folder.stat().st_mtime_ns)]
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_file():
                    stat = entry.stat()
                    parts.append((entry.name, stat.st_size, stat.st_mtime_ns))
        for path in (connection_file(), repo_root() / 'configs' / 'gpdk045_conditions.json'):
            stat = path.stat()
            parts.append((str(path), stat.st_size, stat.st_mtime_ns))
        return tuple(sorted(parts))
    except OSError:
        return None


def load_task_view(circuit, *, profile_id=None) -> TaskRuntime:
    """load_task(circuit) - without the authorization - for the page; a generated task is kept while its files are
    unchanged. What a caller may change (the circuit facts, the notes) is its own copy; the graph is shared and read
    only (compile_task deep-copies it before it sets variables)."""
    key = (circuit.task_id or '') if circuit.source == 'registered_task' else ''
    kind, _, name = key.partition(':')
    if kind != 'real' or not name or name in REAL_PROFILES or key in REMOVED_REAL_TASKS:
        return load_task(circuit, profile_id=profile_id)
    stamp, memo = _view_stamp(name), (key, profile_id)
    kept = _view_cache.get(memo)
    if stamp is not None and kept is not None and kept[0] == stamp:
        blocker = generated_backend_blocker(profile_id)
        if blocker:
            raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
        runtime = kept[1]
    else:
        runtime = load_task(circuit, profile_id=profile_id)
        _view_cache.pop(memo, None)
        if stamp is not None and runtime.circuit.get('generated_profile'):
            _view_cache[memo] = (stamp, runtime)
            while len(_view_cache) > _VIEW_LIMIT:
                _view_cache.pop(next(iter(_view_cache)))
    return replace(runtime, circuit=deepcopy(runtime.circuit), notes=list(runtime.notes))


def _native_draft_runtime(imported, circuit):
    """A cell imported from Virtuoso (`native_cells`), loaded from its LOCAL copy: it can be shown, edited
    against, validated and summarized for the agent. It cannot execute - there is nothing to build."""
    graph = native_cells.draft_graph(imported)

    def builder(compiled, work_root, run_settings):
        raise TaskBlocked(NATIVE_DRAFT_NOT_EXECUTABLE, contract=REAL_INTERFACE_CONTRACT)
    unverified = imported.get('unverified_models') or []
    notes = [f"Read from Virtuoso {imported['imported_utc'][:19]} UTC (netlist export of {imported['exported_cell']}, read-only). "
             'Shown from the local copy: read the cell again after changing it in Virtuoso.']
    if unverified:
        notes.append(f"Device type(s) {', '.join(unverified)} are described neither by the cell's PDK nor by the ideal parts "
                     'of analogLib read with it: their pins are shown unnamed, and nothing is assumed about them.')
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
    problem, _, settings = _link_problem(profile_id, 'Set "bridge_site_packages"')
    if problem:
        return problem
    missing = [k for k in ('env_file', 'model_file') if not settings.get(k)]
    return f'The connection profile lacks {missing}, which a real run needs.' if missing else None


def generated_bridge_config(name, profile_id=None):
    """(BridgeConfig, profile object, registry entry) of a generated profile: the link and the model file of the
    connection profile, the cell's OWN library, the receipt of the profile's folder. Local files only."""
    import site
    from . import profiles  # lazy: profiles imports the optimizer (torch)
    blocker = generated_backend_blocker(profile_id)
    if blocker:
        raise TaskBlocked(blocker, contract=REAL_INTERFACE_CONTRACT)
    entry = profiles.profile_entry(name)
    if entry is None:
        raise TaskBlocked(f'Unknown generated profile {name!r}')
    connection = profile_settings(profile_id)[1]
    if connection.get('bridge_site_packages'):
        site.addsitedir(str(Path(connection['bridge_site_packages']).resolve()))
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
    directory = Path(entry['directory'])
    try:
        profile = profiles.load_profile(name)
    except Exception as exc:
        raise TaskBlocked(f'The generated profile real:{name} no longer passes its own checks: {exc}')
    # The settings file as it is NOW, in a copy of its own (record 7.306): what is written to the shared file later -
    # a second Virtuoso session's keys, say - cannot end the run that binds this one.
    env_file = bridge_env_snapshot(connection['env_file'])
    # The state folder of the Virtuoso session this connection reaches (record 7.311): a lock per session, so a second
    # session carries a second run; the task's adapter locks its cell beside it (cdf_write.backend_class).
    config = BridgeConfig(env_file, entry['library'], (directory / profiles.FILES['receipt']).resolve(),
                          bridge_session_dir(env_file, connection.get('profile')).resolve(), connection['model_file'],
                          profile=connection.get('profile'))
    if entry.get('recipe') == profiles.MAESTRO:                   # its OCEAN measurement reaches Virtuoso the way the run does
        profile.bridge = dict(env_file=str(config.env_file), profile=connection.get('profile'), site=connection.get('bridge_site_packages'))
    return config, profile, entry


def _generated_runtime(task_key, name, profile_id=None, *, authorized=False):
    """A profile created from a cell read out of Virtuoso (`profiles`): the file-driven class, the cell's OWN
    library, the receipt of its folder. Until a real baseline is recorded there is nothing to compare a worker's
    first evaluation with, so none is passed (the factory's comparison is optional)."""
    from . import profiles, recipes  # lazy: profiles and recipes import the optimizer (torch)
    config, profile, entry = generated_bridge_config(name, profile_id)
    directory = Path(entry['directory'])
    reference = profiles.reference_metrics(name)
    graph = profile.optimization_graph()

    def builder(compiled, work_root, run_settings):
        if entry.get('recipe') == profiles.MAESTRO and not entry.get('runnable'):
            raise TaskBlocked(profiles.MAESTRO_NOT_RUNNABLE)
        if not authorized:
            raise TaskBlocked(REAL_AUTHORIZATION_REQUIRED, contract=REAL_INTERFACE_CONTRACT)
        from analog_optimizer.envs.sizing import graph_contract
        # lazy: cdf_write imports the optimizer (torch)
        from .cdf_write import factory_class              # a task written by the PDK's form: the form writer owns the cell
        if graph_contract(compiled.graph) != graph_contract(graph):
            raise TaskBlocked('This task fixes which values may change, their ranges and their grid. The rows of the parameter '
                              'editor differ from what was saved; press "Save task" to save the new rows first.')
        adv = run_settings.advanced
        from analog_optimizer.measurements.specs import RewardSettings
        # its decks load only the parts of the model file it uses (7.154)
        model_library.attach(profile, config, reference=reference, structure=structure.read_text())
        # a Maestro task reads its operating points for a network that uses them (record 7.298)
        # the raw input (record 7.298) or the ratios of the second build (record 7.317)
        profile.read_operating_points = bool(run_settings.network.operating_points or run_settings.network.operating_point_ratios)
        return _with_computed_specs(factory_class(profile)(config, profile, compiled.specs, Path(work_root), adv.episode_length,
                                                           adv.simulation_timeout_seconds, reference,
                                                           reward_settings=RewardSettings(**run_settings.reward.model_dump())), compiled)
    structure, mapping = directory / profiles.FILES['structure'], directory / profiles.FILES['mapping']
    circuit = dict(circuit_class=entry['circuit_class'], pdk_id=entry.get('pdk_id') or 'gpdk045', dut_hierarchy=None,
                   netlist_sha256=_sha256(structure), parser_config_sha256=_sha256(mapping), netlist_file=str(structure),
                   parser_config_file=str(mapping), topology_id=f'profile:{name}', complete=True, generated_profile=True,
                   baseline_recorded=reference is not None, evaluation_backend='virtuoso_bridge + Spectre (REAL)',
                   baseline_attempt=None if reference is not None else entry.get('baseline_attempt'))
    notes = ['Generated profile: it passes every offline check of the verified profiles, but '
             + ('its first real simulation has not been run yet - start with "Baseline simulation"; when it finishes, '
                'its result becomes the task\'s reference by itself.' if reference is None
                else 'only its recorded baseline has been simulated for real.')]
    if not authorized:
        notes.append('Loaded for viewing and validation only. Running it needs your explicit authorization of a real '
                     'simulation budget (asked when you press Start).')
    if entry.get('recipe') == profiles.MAESTRO:
        notes.insert(0, profiles.MAESTRO_NOT_RUNNABLE if not entry.get('runnable') else
                     'Measured by Maestro: every evaluation runs the Maestro deck of its working copy\'s test around the exported '
                     'circuit, and OCEAN measures the outputs on that run\'s results.')
    provided = tuple(entry.get('provided_metrics') or ()) if entry.get('recipe') == profiles.MAESTRO else recipes.provided_metrics(entry['recipe'])
    return TaskRuntime(task_key, 'real', graph, provided, circuit, structure.read_text(),
                       str(structure), str(mapping), builder, max_concurrency=REAL_LANES, authorized=bool(authorized), notes=notes,
                       reference_metrics=None if reference is None else {
                           key: dict(value=value, unit=None) for key, value in reference.items() if isinstance(value, (int, float))})


def _real_runtime(task_key, name, profile_id=None, *, authorized=False):
    """Assemble the verified native factory from local files; nothing here contacts the bridge. Only
    reachable with the bridge importable and complete bindings. The factory itself can only be BUILT
    when `authorized` - the explicit user action with a budget."""
    import site
    info, root = REAL_PROFILES[name], repo_root()
    connection = real_bindings(profile_settings(profile_id)[1], name)
    if connection.get('bridge_site_packages'):
        site.addsitedir(str(Path(connection['bridge_site_packages']).resolve()))
    profile = verified_profile(name)
    config = bridge_config_of(connection)
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
        from analog_optimizer.measurements.specs import RewardSettings
        from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
        corners = {row['id']: PVTCorner(**row) for row in profile.condition_config['screening_corners']}
        selected = tuple(SimulationCondition(corners[key], 'pvt_training') for key in run_settings.conditions.corners)
        return _with_computed_specs(NativeEnvironmentFactory(config, profile, compiled.specs, Path(work_root), adv.episode_length,
                                                             adv.simulation_timeout_seconds, reference['metrics'],
                                                             reward_settings=RewardSettings(**run_settings.reward.model_dump()),
                                                             condition_policy=run_settings.conditions.policy, corners=selected), compiled)
    circuit = dict(circuit_class=info['circuit_class'], pdk_id='gpdk045', dut_hierarchy=None,
                   netlist_sha256=_sha256(root / info['structure']), parser_config_sha256=_sha256(root / info['mapping']),
                   netlist_file=str(root / info['structure']), parser_config_file=str(root / info['mapping']),
                   topology_id=f'profile:{name}', complete=True, evaluation_backend='virtuoso_bridge + Spectre (REAL)')
    metrics = tuple(reference['metrics'])
    return TaskRuntime(task_key, 'real', graph, metrics, circuit, (root / info['structure']).read_text(),
                       str(root / info['structure']), str(root / info['mapping']), builder, max_concurrency=REAL_LANES,
                       authorized=bool(authorized),
                       reference_metrics={name: dict(value=value, unit=(reference.get('metric_units') or {}).get(name))
                                          for name, value in reference['metrics'].items() if isinstance(value, (int, float))},
                       notes=[] if authorized else ['Loaded for viewing and validation only. Running it needs your explicit '
                                                    'authorization of a real simulation budget (asked when you press Start).'])


def profile_parameter_rows(runtime) -> list:
    """The Parameters-tab rows a REAL circuit profile fixes, written from its own parameter groups (the same
    mapping as starter_config). A real profile accepts exactly these variables, ranges and grid: the engine compares the
    compiled configuration with the profile (`graph_contract`) and refuses anything else when the run starts. Empty for
    a task that fixes nothing (a MOCK circuit, a cell without a profile)."""
    return [] if runtime is None or runtime.mock else _graph_parameter_rows(runtime.base_graph)


_NOT_IN_AN_ID = re.compile(r'[^A-Za-z0-9_.\-]')


def member_variable_id(group_id, device_id) -> str:
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
            variable_id = record['id'] if leader is None else member_variable_id(record['id'], member['device_id'])
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


def real_starter_config(task_key: str) -> dict:
    """What the three editors show when a REAL task is chosen. Local files only: no connection, no bridge, no simulation.
    Parameters - the rows the circuit's profile fixes (a real run accepts exactly these). Specs - the targets of record of
    a verified circuit (REAL_TARGETS_OF_RECORD), each row stating its source; a profile generated from a cell has none,
    its requirements stay the user's to state. Probes - one row per result that carries a target; for a generated profile
    one per result a target can be set on. Run settings are left alone: a real budget is never suggested."""
    from . import profiles  # lazy: profiles imports the optimizer (torch)
    if task_key in REMOVED_REAL_TASKS:
        raise KeyError(task_key)
    name = task_key.partition(':')[2]
    if name in REAL_PROFILES:
        circuit_class, pdk_id = REAL_PROFILES[name]['circuit_class'], 'gpdk045'
        graph, oscillator = verified_profile(name).optimization_graph(), circuit_class == 'vco'
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
        entry = profiles.profile_entry(name)
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
    editable. A MOCK circuit a test registered: the groups its device mapping declares, with the toy `score` as its only
    target. A real task: real_starter_config. A removed MOCK or real task (REMOVED_MOCK_TASKS, REMOVED_REAL_TASKS) has
    none: KeyError, like any unknown task."""
    from analog_optimizer.netlist.config import ParserConfig
    kind, _, name = task_key.partition(':')
    if kind == 'real' and name:
        return real_starter_config(task_key)
    if kind == 'ngspice' and name:
        from . import ngspice_tasks  # lazy: ngspice_tasks imports the optimizer (torch)
        return ngspice_tasks.starter_config(task_key)          # KeyError for a task that does not exist
    if kind != 'synthetic' or name not in task_registry.SYNTHETIC_FIXTURES:
        raise KeyError(task_key)
    root, info = repo_root(), task_registry.SYNTHETIC_FIXTURES[name]
    parser_config = ParserConfig.from_file(root / info['config'])
    parameters = []
    for group in parser_config.parameter_groups:
        leader = None
        for member in group['members']:
            variable_id = f"{group['id']}" if leader is None else member_variable_id(group['id'], member['device_id'])
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


# The names these had before refactoring package B9 (2026-10-09), kept for code that still uses them.
_member_variable_id = member_variable_id
_profile_settings = profile_settings


# The caches of this module: caches.clear_all() empties them with every other one (refactoring package B10).
caches.register(globals(), '_view_cache')
