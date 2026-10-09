"""Run preparation and control for the API/CLI.

prepare_run   validate -> compile -> create a UNIQUE run directory (or reopen the original one for
              resume) -> write manifest, effective config, input snapshot, experiment files.
launch_worker start the detached worker process. Its lifetime does not depend on the HTTP server,
              a browser tab or a terminal; the run lock prevents duplicates.
send_command  pause / stop / cancel through a control file.
"""
from __future__ import annotations

from concurrent.futures import Future
import copy
from dataclasses import asdict
import hashlib
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from . import (CONFIG_SCHEMA_VERSION, OUTPUT_LAYOUT_VERSION, checkpoints as ckpt, connection, consistency, modes, pdk,
               run_index)
from .compile import CompileError, compile_task
from .connection import worker_environment
from .layout import RunLayout, code_provenance, environment_versions, new_experiment_dir, new_run_dir, read_run
from .paths import OutputRoots, is_mock_path, repo_root
from .pdk import run_vocabulary, write_run_vocabulary
from .run_definitions import learner_experiment
from .run_lock import RunLock
from .schema import REMOVED_SEARCH_METHODS, WorkbenchConfig, canonical_json, config_hash, task_definition_hash
from .storage.atomic import read_json, write_json
from .storage.dataset import utcnow, write_data_dictionary
from .task_registry import NATIVE_DRAFT_NOT_EXECUTABLE, REAL_AUTHORIZATION_REQUIRED
from .tasks import TaskBlocked, load_task, load_task_view
from .validation import validate
# re-exported: moved to settings_store.py by the refactoring (docs/plan-refactoring.md)
from .settings_store import _SETTINGS_LOCK, read_settings, load_settings, save_settings, remembered_output_root
# (not current_source_digest and the caches' own state: they are read and patched as run_index.<name>)
# re-exported: moved to run_index.py by the refactoring (docs/plan-refactoring.md)
from .run_index import (SEGMENT_FACTS, run_timing, lineage, _RunRow, _code_of, save_point_code, save_point_facts,
                        save_point, _resumability, READ_THREADS, LIVE_STATES, _fingerprint, _run_facts,
                        checkpoint_listing, _read_pool, read_many, checkpoint_listings, list_runs, model_label_rows,
                        output_root_of)

# Settings a resume may change. Everything that defines the task or the learner contract is fixed.
RESUMABLE_RUN_FIELDS = ('max_evaluations', 'max_spectre_launches', 'max_wall_seconds', 'max_retries',
                        'concurrency', 'stop_at_first_feasible', 'max_consecutive_failures')


_HELD_LOCKS: dict = {}          # run_dir -> RunLock taken during preparation, handed to the worker


def take_lock(run_dir):
    """The lock acquired while preparing a resume (None for a brand-new, unique run directory)."""
    return _HELD_LOCKS.pop(str(run_dir), None)


class RunRejected(ValueError):
    def __init__(self, message, *, report=None, code='rejected'):
        super().__init__(message)
        self.report, self.code = report, code


# ---------------------------------------------------------------------------- preparation
def _initial_dimensions(compiled):
    values = {g.id: g.value for g in compiled.graph.parameter_groups}
    return values, hashlib.sha256(canonical_json(values).encode()).hexdigest()


def _input_snapshot(layout: RunLayout, task, compiled, config):
    snapshot = layout.input_snapshot
    graph = compiled.graph
    write_json(snapshot / 'circuit.json', dict(
        circuit_id=graph.circuit_id, schema_version=graph.schema_version, complete=graph.complete,
        devices=[asdict(d) for d in graph.devices], nets=[asdict(n) for n in graph.nets],
        connections=[asdict(c) for c in graph.connections],
        parameters={device: {name: dict(raw=v.raw, value=v.value, reason=v.reason, source_name=v.source_name)
                             for name, v in values.items()} for device, values in graph.parameters.items()},
        diagnostics=[dict(code=d.code, message=d.message, severity=d.severity) for d in graph.diagnostics]))
    notes = []
    if task.netlist_text is not None:
        name = 'netlist.cir' if task.circuit.get('simulator') == 'ngspice' else 'netlist.scs'   # a SPICE deck is not .scs
        (snapshot / name).write_text(task.netlist_text, encoding='utf8')
        write_json(snapshot / 'hierarchy.json', dict(
            combined_netlist=name, dut_hierarchy=task.circuit.get('dut_hierarchy'),
            source_file=task.netlist_path, sha256=task.circuit.get('netlist_sha256'),
            instances=[d.id for d in graph.devices]))
        notes.append(f'input_snapshot: the source is ONE combined netlist, saved as {name} with hierarchy.json. '
                     'Separate dut.scs / testbench.scs do not exist and no empty placeholders were created.')
    write_json(snapshot / 'parameter_mapping.json', dict(variables=list(compiled.variables),
                                                         action_version='absolute-group-v1',
                                                         rule='absolute linear/log -> clamp -> nearest grid -> bindings'))
    write_json(snapshot / 'pdk_reference.json', dict(
        pdk_id=task.circuit.get('pdk_id'), parser_config_file=task.parser_config_path,
        parser_config_sha256=task.circuit.get('parser_config_sha256'),
        note='Reference only. Commercial PDK libraries, model files, keys and licenses are never copied.'))
    return notes


def _research_block(config, source_manifest):
    research = config.research.model_dump(mode='json')
    pretrain, origin = research.get('pretrain_seed'), 'user_label'
    if source_manifest:
        recorded = (source_manifest.get('seeds') or {}).get('target_seed')
        if pretrain is None:
            pretrain, origin = recorded, 'source_run_manifest'
        elif recorded is not None and recorded != pretrain:
            research['pretrain_seed_conflict'] = dict(user_label=pretrain, source_run_manifest=recorded)
    elif pretrain is None:
        origin = 'not_applicable' if config.run.mode == 'scratch' else 'unspecified'
    return research, pretrain, origin


def with_circuit_content(config: WorkbenchConfig, task) -> WorkbenchConfig:
    """Stamp the hash of the circuit that was ACTUALLY loaded into the configuration, so the task
    identity always reflects real content: a changed circuit is a changed task."""
    config = config.model_copy(deep=True)
    config.circuit.content_sha256 = task.circuit.get('netlist_sha256')
    return config


def suggest_mode(config: WorkbenchConfig, source_run_dir=None, task=None) -> dict:
    """resume when full state exists for the SAME task; fine_tune (needs confirmation) for an old model on
    a new task; scratch when nothing is loaded. `task`: the runtime the caller has already loaded (the saved-model
    check loaded it twice per edit)."""
    if not source_run_dir:
        return dict(mode='scratch', reason='No previous weights selected.', requires_confirmation=False)
    try:
        config = with_circuit_content(config, task or load_task(config.circuit))
    except TaskBlocked:
        pass
    try:
        meta = ckpt.read_metadata(ckpt.resolve_checkpoint(source_run_dir, 'latest'))
    except (FileNotFoundError, OSError) as exc:
        return dict(mode='scratch', reason=f'The selected run has no usable checkpoint: {exc}',
                    requires_confirmation=False)
    same = meta['task_definition_hash'] == task_definition_hash(config)
    if meta['restoration_capability'] == 'search_state':        # from an LLM-only run (a method removed on 2026-10-06)
        return dict(mode='scratch', reason='This save holds the search progress of an LLM-only run and no RL model.',
                    requires_confirmation=False)
    if same and meta['restoration_capability'] == 'full_state':
        return dict(mode='resume', reason='Full training state exists for the same task.', requires_confirmation=False)
    if same:
        return dict(mode='fine_tune', requires_confirmation=True,
                    reason=f"Same task but the checkpoint is {meta['restoration_capability']}; a full resume is impossible.")
    return dict(mode='fine_tune', requires_confirmation=True,
                reason='The model was trained on a different task. Loading it is a transfer: a new run is created and '
                       'the source recorded as its parent.')


def _vocabulary_for(config, source_run=None):
    """The component list a new run's network is built with (None = the standard list). A run that LOADS a saved model
    takes that model's own list when it names the same PDK - the network follows the model, as its sizes do - even if
    the PDK was loaded again since; the model's list is copied from its run folder."""
    wanted = pdk.requested(config)
    if source_run is not None:
        own = pdk.run_vocabulary(source_run)
        if own is not None and own.name == wanted:
            return own
    try:
        return pdk.current_vocabulary(wanted)
    except pdk.PdkError as exc:
        raise RunRejected(str(exc), code='pdk_not_loaded')


def vocabulary_record(vocabulary) -> dict:
    """What the manifest says about the component list (the list itself is the run's network_vocabulary.json)."""
    if vocabulary is None:
        return dict(name=pdk.STANDARD, label=pdk.label(None))
    return dict(name=vocabulary.name, label=vocabulary.label, pdk_id=vocabulary.pdk_id, version=vocabulary.version,
                sha256=vocabulary.sha256, file=pdk.RUN_FILE)


# ---- the contract a learner of the page's configuration would have (record 7.278) ---------------------------------
# SACLearner.contract() is a pure function of what the learner is built from, but getting it meant building the learner
# (five networks, 10-20 ms) and, inside contract(), hashing every file under src/analog_optimizer/ on the 9p-mounted D:
# drive (0.35-1.4 s) - once per inspection of a saved model, which the page asks for 0.5 s after every edit and once per
# model looked at in the RL model window. The inspection keeps the contract by everything it is made of except the
# experiment, whose two fields are cheap (the task hash in it changes at every edit of a row). A start builds it anew.
_CONTRACTS: dict = {}
_CONTRACTS_LOCK = threading.Lock()
CONTRACT_CACHE_MAX = 32


def _contract_key(model_config, sac_config, spec_schema, vocabulary, runtime) -> str:
    """Everything the contract is made of, as canonical JSON: the source digest of now (current_source_digest, kept 30 s),
    the library versions, the network and training settings, the spec schema, the component list and the runtime options
    (feature schema, reward settings, condition policy, planned conditions). A value that is not JSON raises: no key is
    better than a wrong one."""
    from dataclasses import is_dataclass
    import torch
    import torch_geometric

    def plain(value):
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        return value
    return canonical_json(dict(code=run_index.current_source_digest(), torch=str(torch.__version__), pyg=str(torch_geometric.__version__),
                               model_config=model_config.to_dict(), sac_config=asdict(sac_config),
                               spec_schema=None if spec_schema is None else asdict(spec_schema),
                               vocabulary=None if vocabulary is None else dict(name=vocabulary.name, sha256=vocabulary.sha256),
                               options={name: plain(value) for name, value in (runtime or {}).items()}))


def learner_contract(config, task, task_hash, spec_schema, vocabulary, *, cached=False) -> dict:
    """The contract a learner built from this configuration has: what a saved model is checked against. `cached`: the
    page's inspection of a saved model (POST /api/runs/model) takes the kept contract, see above; a start leaves it False
    and builds the learner, so the digest in its verdict is the source's of that moment."""
    experiment = learner_experiment(config, task, task_hash)
    model_config, sac_config = modes.model_config_from(config.run.network), modes.sac_config_from(config.run.advanced)
    runtime = modes.runtime_options(config, vocabulary)
    if not cached:
        return modes.current_contract(experiment, model_config, sac_config, spec_schema, vocabulary, runtime=runtime)
    key = _contract_key(model_config, sac_config, spec_schema, vocabulary, runtime)
    with _CONTRACTS_LOCK:
        contract = _CONTRACTS.get(key)
    if contract is None:
        contract = modes.current_contract(experiment, model_config, sac_config, spec_schema, vocabulary, runtime=runtime)
        with _CONTRACTS_LOCK:
            while len(_CONTRACTS) >= CONTRACT_CACHE_MAX:
                _CONTRACTS.pop(next(iter(_CONTRACTS)))
            _CONTRACTS[key] = contract
    return dict(copy.deepcopy(contract), **ckpt.experiment_fields(experiment))


def connection_gate(task, config, monitor, *, acknowledge_unknown=False):
    """Pre-dispatch gate (section 2.1). Runs BEFORE any directory, reservation or manifest exists, so a
    blocked start leaves nothing behind. Mock runs need no bridge layer: not_applicable."""
    if task.mock:
        return dict(status='not_applicable', allowed=True, reason='mock run: no bridge layer is involved')
    if monitor is None:
        raise RunRejected('A real run needs the connection gate; no connection monitor was supplied', code='connection_gate')
    profile_id = config.run.connection_profile_id
    if not profile_id:
        raise RunRejected('A real task needs run.connection_profile_id (the identifier of a configured profile). '
                          'There is no fallback to another profile or to mock mode.', code='connection_gate')
    # The connection must be of the family the task runs on: an ngspice netlist task never probes Virtuoso, and a
    # Virtuoso task never runs on ngspice. Said before the gate probes anything.
    family = getattr(task, 'connection_family', 'virtuoso')
    settings = connection.load_profiles()['profiles'].get(profile_id)
    if settings is not None and connection.family_of(connection.profile_kind(settings if isinstance(settings, dict) else {})) != family:
        label = connection.KINDS.get(connection.profile_kind(settings if isinstance(settings, dict) else {}) or '', {}).get('label', 'of an unknown kind')
        raise RunRejected(f'Connection {profile_id!r} is "{label}", but this task runs on '
                          + ('ngspice: choose an ngspice connection ("ngspice on this machine" or "ngspice over SSH") in the '
                             'Connection window, or add one there.' if family == 'ngspice' else
                             'Virtuoso + Spectre: choose a Virtuoso connection in the Connection window.'), code='connection_gate')
    try:
        gate = monitor.gate('real_simulation', profile_id, acknowledge_unknown=acknowledge_unknown)
    except (KeyError, ValueError) as exc:
        raise RunRejected(f'Unknown connection profile: {exc}', code='connection_gate')
    if not gate['allowed']:
        raise RunRejected('The connection gate blocked this action. Nothing was reserved or created.' if gate['status'] == 'blocked'
                          else 'Some connection layers are unknown; acknowledge them to proceed.', report=gate,
                          code='connection_gate_blocked' if gate['status'] == 'blocked' else 'connection_gate_acknowledge')
    return gate


def _check_consistency(config, task, monitor, acknowledge_unknown):
    """The check before every run of a saved task (consistency.py): its working copy in Virtuoso must still be what the
    task saved - read-only, no simulation. The rows were compared by static validation already. A difference refuses the
    start before anything is created; None for every other task."""
    if task.mock:
        return None
    if consistency.saved_task(config, with_entry=False) is None:
        return None
    result = consistency.check(monitor, config.run.connection_profile_id, config, rows=False, acknowledge_unknown=acknowledge_unknown)
    if not result['ok']:
        raise RunRejected(consistency.summary(result), report=result, code='consistency')
    return result


def manifest_conditions(conditions) -> dict:
    """What the manifest says about the conditions the run's designs are simulated at. Every manifest used to say
    "nominal-only", runs that train at corners too (review of 2026-09-29); the plan is `run.conditions`."""
    if conditions.policy == 'off':
        return dict(conditions=['nominal'], note='The sizing environment is nominal-only')
    when = 'every design' if conditions.policy == 'always' else 'designs that pass nominal'
    return dict(conditions=['nominal', *conditions.corners],
                note=f'Training at nominal and, for {when}, at the planned corners (policy {conditions.policy}); '
                     'resets are simulated at nominal only')


def model_label(config: WorkbenchConfig) -> str:
    """The name a run's RL model is filed under (record 7.159, the user's request of 2026-10-03: "Give the RL model its own
    label, independent of the project name"): the label typed in the RL model window, else the task's run label."""
    return (config.run.model_label or '').strip() or config.project.task_name


def saves_rl_model(config: WorkbenchConfig) -> bool:
    """Whether a run writes an RL model to disk: one with save points on. A Baseline simulation saves none."""
    return bool(config.output.save_checkpoints)


def _started(work) -> Future:
    """work() begun in a thread of its own now; .result() waits for its answer, or raises what it raised."""
    future = Future()

    def run():
        if future.set_running_or_notify_cancel():
            try:
                future.set_result(work())
            except BaseException as exc:
                future.set_exception(exc)
    threading.Thread(target=run, name='gator-started', daemon=True).start()
    return future


def prepare_run(config: WorkbenchConfig, roots: OutputRoots, *, allow_real=False, confirm_transfer=False,
                monitor=None, acknowledge_unknown=False, remember_concurrency=True):
    """Returns (RunLayout, manifest). Raises RunRejected with the validation/compatibility report."""
    if config.run.rehearsal is not None:
        roots.resolve(config.run.rehearsal.pool_manifest)
    try:
        task = load_task(config.circuit, allow_real=allow_real, profile_id=config.run.connection_profile_id)
    except TaskBlocked as exc:
        raise RunRejected(str(exc), report=dict(blocker=str(exc), interface_contract=exc.contract), code='task_blocked')
    if task.circuit.get('native_draft'):                  # read from Virtuoso, no profile: not even an authorization question
        raise RunRejected(NATIVE_DRAFT_NOT_EXECUTABLE, report=dict(blocker=NATIVE_DRAFT_NOT_EXECUTABLE), code='task_blocked')
    if not task.mock and not allow_real:                  # before anything is created, reserved or gated
        raise RunRejected(REAL_AUTHORIZATION_REQUIRED, code='real_authorization_required',
                          report=dict(blocker=REAL_AUTHORIZATION_REQUIRED, task_key=task.task_key,
                                      requested_max_evaluations=config.run.max_evaluations))
    config = with_circuit_content(config, task)
    report = validate(config, graph=task.base_graph, provided_metrics=set(task.provided_metrics))
    if report.blocks_run:
        raise RunRejected('The configuration has blocking issues', report=report.as_dict(), code='validation')
    try:
        compiled = compile_task(config, task.base_graph)
    except CompileError as exc:
        raise RunRejected(str(exc), code='compile')
    if config.run.concurrency > task.max_concurrency:
        raise RunRejected(f'This task supports at most {task.max_concurrency} concurrent simulation jobs',
                          code='concurrency')
    task_hash = task_definition_hash(config)
    # The manifest's code facts - git rev-parse and status on the 9p mount and the optimizer digest, 1.5-2 s - are read
    # while the connection is checked (record 7.279); the manifest takes them below. A resume writes none.
    provenance = _started(code_provenance) if config.run.mode != 'resume' else None
    gate = connection_gate(task, config, monitor, acknowledge_unknown=acknowledge_unknown)
    consistency = _check_consistency(config, task, monitor, acknowledge_unknown)
    if config.run.mode == 'resume':
        layout, manifest = _prepare_resume(config, roots, task, task_hash, gate)
        if consistency is not None:
            manifest['segments'][-1]['consistency_check'] = consistency
            try:
                write_json(layout.manifest, manifest)
            except BaseException:         # the run lock taken for this resume goes too: kept, it refused every later Resume
                take_lock(layout.run_dir).release()             # as "already running" until the backend restarted
                raise
        return layout, manifest
    output_root = config.output.output_root or remembered_output_root()
    check = roots.check(output_root, create=True, verify_windows=False)
    if not check['allowed'] or not check['writable']:
        raise RunRejected(f"Output root is not usable: {check['error'] or 'not writable'}", report=check, code='output')
    data_root = roots.data_root(output_root, mock=task.mock)      # mock data is confined to <root>/mock
    data_root.mkdir(parents=True, exist_ok=True)
    source_manifest = source_meta = source_dir = None
    source_model = dict(cost_status='not_applicable', cost_evaluations=None, provenance_chain=[])
    parent = None
    vocabulary = _vocabulary_for(config) if config.run.mode not in ('fine_tune', 'frozen') else None
    if config.run.mode in ('fine_tune', 'frozen'):
        source_run = Path(roots.resolve(config.run.model_source.run_dir))
        vocabulary = _vocabulary_for(config, source_run)
        if is_mock_path(source_run) != task.mock:
            raise RunRejected('A mock-trained model cannot be loaded for a real task (or vice versa)', code='mock_isolation')
        source_dir = ckpt.resolve_checkpoint(source_run, config.run.model_source.checkpoint_id)
        source_meta, source_manifest = ckpt.read_metadata(source_dir), read_json(source_run / 'run_manifest.json', default={})
        different = source_meta['task_definition_hash'] != task_hash
        if config.run.mode == 'fine_tune' and different and not confirm_transfer:
            raise RunRejected('Loading a model trained on a different task needs explicit confirmation',
                              report=suggest_mode(config, source_run), code='confirm_transfer')
        source_is_test_adaptation = (source_manifest.get('mode') == 'fine_tune'
                                     and (source_manifest.get('research') or {}).get('split') == 'test')
        if source_is_test_adaptation and not config.run.continual_learning:
            raise RunRejected('The selected source was itself fine-tuned on a test task. Each test task starts from the '
                              'fixed source checkpoint by default; enable run.continual_learning to label this '
                              'explicitly as continual learning.', code='continual_learning')
        contract = learner_contract(config, task, task_hash, compiled.spec_schema, vocabulary)
        compatibility = ckpt.check_compatibility(source_meta, mode=config.run.mode, task_definition_hash=task_hash,
                                                 contract=contract)
        if not compatibility['compatible']:
            raise RunRejected('The selected checkpoint is not compatible. No fallback to scratch is performed.',
                              report=compatibility, code='incompatible_checkpoint')
        cost = modes.source_cost(source_run)
        declared = config.run.model_source.source_pretraining_cost_evaluations
        if cost['status'] == 'unknown' and declared is not None:
            cost = dict(status='declared_by_user', evaluations_charged=declared, chain=cost['chain'])
        source_model = dict(run_id=source_meta['run_id'], run_dir=str(source_run),
                            checkpoint_id=source_meta['checkpoint_id'], weight_sha256=source_meta['weight_sha256'],
                            task_id=source_meta['task_id'], cost_status=cost['status'],
                            cost_evaluations=cost['evaluations_charged'], provenance_chain=cost['chain'],
                            compatibility=compatibility)
        parent = dict(run_id=source_meta['run_id'], run_dir=str(source_run), checkpoint_id=source_meta['checkpoint_id'],
                      relation=config.run.mode)
    experiment_dir, experiment_id, created = new_experiment_dir(data_root, config.output.experiment_name,
                                                                 config.output.experiment_id)
    layout, run_id = new_run_dir(experiment_dir, config.project.task_name, config.run.mode, config.run.seed)
    layout.create()
    write_run_vocabulary(layout.run_dir, vocabulary)          # the run's own copy: resume and later loads use it
    config = config.model_copy(deep=True)
    config.output.output_root, config.output.experiment_id = str(roots.resolve(output_root)), experiment_id
    research, pretrain_seed, pretrain_origin = _research_block(config, source_manifest)
    initial, initial_hash = _initial_dimensions(compiled)
    # The name this run's model goes by (record 7.225): the label in use, numbered when a model under this output root
    # carries it already - "ota7t", "ota7t (2)", "ota7t (3)". The label itself stays the key the run is remembered under.
    given_label = None
    if saves_rl_model(config):
        taken = set(ckpt.unique_model_labels(model_label_rows(config.output.output_root)).values())
        given_label = ckpt.free_model_label(model_label(config), taken)
    now = utcnow().isoformat()
    manifest = dict(
        layout_version=OUTPUT_LAYOUT_VERSION, config_schema_version=CONFIG_SCHEMA_VERSION,
        experiment_id=experiment_id, experiment_name=config.output.experiment_name, run_id=run_id,
        task_id=f'{config.project.task_name}:{task_hash[:16]}', task_name=config.project.task_name,
        model_label=given_label,
        task_definition_hash=task_hash, config_sha256=config_hash(config),
        comparison_pair_id=research['comparison_pair_id'], task_order=research['task_order'],
        run_kind='optimization', mode=config.run.mode, provenance='mock' if task.mock else 'real', mock=task.mock,
        mock_notice=('MOCK DATA: produced by a synthetic analytic backend. Not a circuit result; excluded from '
                     'real-experiment aggregates by default.') if task.mock else None,
        circuit=dict(task.circuit, task_key=task.task_key, source=config.circuit.source),
        test_conditions=manifest_conditions(config.run.conditions),
        definitions=dict(location='effective_config.json', variables=list(compiled.variables),
                         targets=list(compiled.targets), preference=compiled.preference,
                         reward=dict(version='constraint_violation_v2', settings=config.run.reward.model_dump(),
                                     conditions=config.run.conditions.model_dump(), clearance_rule='tightest_eligible_hard_spec_v1'),
                         feasibility='all active hard constraints, decided from raw values independently of reward',
                         action='absolute-group-v1: normalized proposal -> legalized physical assignment'),
        architecture=dict(network=config.run.network.model_dump(), sac=config.run.advanced.model_dump(mode='json'),
                          spec_schema=dict(version=compiled.spec_schema.version,
                                           metrics=[list(m) for m in compiled.spec_schema.metrics]),
                          vocabulary=vocabulary_record(vocabulary)),
        source_model=source_model, parent=parent,
        research=research, split=research['split'], generalization_level=research['generalization_level'],
        seeds=dict(target_seed=config.run.seed, pretrain_seed=pretrain_seed, pretrain_seed_origin=pretrain_origin,
                   note='target_seed drives this run; pretrain_seed belongs to the SOURCE run. Never merged.'),
        initial_dimensions=initial, initial_dimensions_sha256=initial_hash,
        budgets=dict(max_evaluations=config.run.max_evaluations, max_spectre_launches=config.run.max_spectre_launches,
                     max_wall_seconds=config.run.max_wall_seconds, max_retries=config.run.max_retries),
        execution=dict(concurrency=config.run.concurrency, cache_policy=config.run.cache_policy,
                       frozen_action=config.run.frozen_action if config.run.mode == 'frozen' else None),
        connection_gate=gate, consistency_check=consistency,
        authorization=dict(real_simulation=bool(allow_real and not task.mock),
                           authorized_max_evaluations=config.run.max_evaluations if allow_real and not task.mock else None),
        code=provenance.result(), environment=environment_versions(), created_utc=now, state='created',
        output=dict(output_root=config.output.output_root, data_root=str(data_root),
                    experiment_dir=str(experiment_dir), run_dir=str(layout.run_dir),
                    relative_run_dir=str(layout.run_dir.relative_to(experiment_dir))),
        segments=[dict(segment=1, entry='start', requested_utc=now)], notes=list(task.notes))
    manifest['notes'] += _input_snapshot(layout, task, compiled, config)
    write_json(layout.effective_config, config.model_dump(mode='json'))
    write_json(layout.manifest, manifest)
    write_json(layout.status, dict(state='created', run_id=run_id, mode=config.run.mode, mock=task.mock,
                                   paths=layout.subpaths(), heartbeat_utc=now))
    _register_in_experiment(experiment_dir, manifest, compiled, task, created)
    # The newest run that saves an RL model is remembered under the model's label (record 7.159): Resume, fine_tune and
    # frozen start from it. A run that saves no model (a Baseline simulation) leaves the label alone.
    with _SETTINGS_LOCK:             # the last_run merge reads and writes under the lock every other save takes
        remembered = load_settings().get('last_run', {})
        if saves_rl_model(config):
            remembered = {**remembered, model_label(config): str(layout.run_dir)}
        save_settings(output_root=config.output.output_root, last_run=remembered,
                      **(dict(concurrency=config.run.concurrency) if remember_concurrency else {}))
    return layout, manifest


def _prepare_resume(config, roots, task, task_hash, gate):
    run_dir = Path(roots.resolve(config.run.model_source.run_dir))
    layout = RunLayout(run_dir)
    manifest = read_json(layout.manifest, default=None)
    if not manifest:
        raise RunRejected(f'{run_dir} is not a run directory', code='not_a_run')
    # Take the run lock BEFORE reading or changing anything, and keep it until the worker ends: a second
    # "continue" (double click, reconnect) can then never append a segment or start a second worker.
    lock = RunLock(layout.control / 'run.lock')
    try:
        lock.acquire()
    except RuntimeError:
        raise RunRejected('This run already has an active worker; a duplicate is never started', code='already_running')
    try:
        result = _prepare_resume_locked(config, roots, task, task_hash, gate, layout, manifest, run_dir)
    except BaseException:
        lock.release()
        raise
    _HELD_LOCKS[str(layout.run_dir)] = lock
    return result


def _prepare_resume_locked(config, roots, task, task_hash, gate, layout, manifest, run_dir):
    previous, merged, meta, compatibility = _resume_checks(config, task, task_hash, layout, manifest, run_dir)
    history = layout.control / 'config_history'
    history.mkdir(parents=True, exist_ok=True)
    write_json(history / f"effective_config.segment{len(manifest['segments'])}.json", previous.model_dump(mode='json'))
    write_json(layout.effective_config, merged.model_dump(mode='json'))
    manifest['segments'].append(dict(segment=len(manifest['segments']) + 1, entry='resume',
                                     requested_utc=utcnow().isoformat(), from_checkpoint=meta['checkpoint_id'],
                                     compatibility=compatibility, connection_gate=gate,
                                     changed_run_settings={n: getattr(merged.run, n) for n in RESUMABLE_RUN_FIELDS
                                                           if getattr(merged.run, n) != getattr(previous.run, n)}))
    manifest['budgets'].update(max_evaluations=merged.run.max_evaluations,
                               max_spectre_launches=merged.run.max_spectre_launches,
                               max_wall_seconds=merged.run.max_wall_seconds, max_retries=merged.run.max_retries)
    manifest['state'] = 'created'
    write_json(layout.manifest, manifest)
    command = layout.control / 'command.json'
    if command.exists():
        command.unlink()                       # a stale pause must not stop the continued run immediately
    return layout, manifest


def _resume_checks(config, task, task_hash, layout, manifest, run_dir):
    """Everything an exact resume checks before it writes anything - the refusals of Continue. Shared by the press
    (under the run lock, _prepare_resume_locked) and the continuation check (record 7.261, no lock, nothing written).
    Returns (previous configuration, merged configuration, save point metadata, compatibility report)."""
    if manifest['task_definition_hash'] != task_hash:
        raise RunRejected('The task definition changed (circuit, variables, targets or measurements). This cannot be '
                          'presented as a continuation of the same training run; use fine_tune.',
                          report=suggest_mode(config, run_dir, task=task), code='task_changed')
    if manifest['mock'] != task.mock:
        raise RunRejected('Mock/real provenance differs from the run being resumed', code='mock_isolation')
    removed = (manifest.get('search_settings') or {}).get('method')
    if removed:
        # A run keeps the search method it started with: one of the LLM methods removed on 2026-10-06 is not continued as
        # SAC. Its records stay readable, and its RL model (all but LLM only have one) can start a new run.
        raise RunRejected(f'This run used the search method "{REMOVED_SEARCH_METHODS.get(removed, removed)}", which was removed '
                          'on 2026-10-06: SAC is the only search method now, and a run is never continued with another '
                          'method than it started with. Its results stay readable. '
                          + ('It holds no RL model.' if removed == 'llm' else 'To go on from its RL model, start a new run in '
                             'Fine-tune with its model chosen in the RL model window.'), code='search_method_removed')
    try:
        meta = ckpt.read_metadata(ckpt.resolve_checkpoint(run_dir, 'latest'))
    except FileNotFoundError as exc:
        raise RunRejected(f'Nothing to resume: {exc}', code='no_checkpoint')
    previous = WorkbenchConfig.model_validate(read_json(layout.effective_config))
    if (config.run.reward != previous.run.reward or config.run.conditions != previous.run.conditions
            or config.run.network.operating_points != previous.run.network.operating_points):
        raise RunRejected('Reward settings, condition plan and operating-point inputs cannot change on exact resume. '
                          'Use fine_tune with a compatible actor and fresh critics/replay.', code='reward_contract_changed')
    merged = previous.model_copy(deep=True)
    for name in RESUMABLE_RUN_FIELDS:
        setattr(merged.run, name, getattr(config.run, name))
    if merged.run.max_evaluations < meta['ledger']['charged']:
        raise RunRejected(f"max_evaluations ({merged.run.max_evaluations}) is below the {meta['ledger']['charged']} "
                          'evaluations this run already consumed; resume keeps existing counters', code='budget')
    compiled = compile_task(merged, task.base_graph)
    contract = modes.current_contract(learner_experiment(merged, task, task_hash),
                                      modes.model_config_from(merged.run.network),
                                      modes.sac_config_from(merged.run.advanced), compiled.spec_schema,
                                      run_vocabulary(run_dir), runtime=modes.runtime_options(merged, run_vocabulary(run_dir)))
    compatibility = ckpt.check_compatibility(meta, mode='resume', task_definition_hash=task_hash, contract=contract)
    if not compatibility['compatible']:
        raise RunRejected('The latest checkpoint cannot be fully resumed. No fallback to scratch is performed.',
                          report=compatibility, code='incompatible_checkpoint')
    return previous, merged, meta, compatibility


# Refusals of Continue that a NEW run avoids: the save point's RL model still loads in a fine-tune.
_FINE_TUNE_INSTEAD = ('task_changed', 'older_code', 'incompatible_checkpoint', 'reward_contract_changed',
                      'search_method_removed')


def continuation(run_dir, *, max_evaluations=None) -> dict:
    """Whether Continue can go on with this run, and with which budget - answered BEFORE the press (record 7.261, plan
    "Existing runs: continued in place"). The checks are the press's own (_resume_checks, and the validation and the
    concurrency limit of prepare_run), on the run's own saved configuration, without the run lock and without writing
    anything. Not asked here: the real-simulation authorization, the connection gate and the check before every run -
    they need the user or Virtuoso, and the press asks them as before. The press checks everything again under the lock.

    `max_evaluations`: a new total to check instead of the run's own. `used` counts the evaluations of the save point a
    continuation goes on from; the new total has to be more than that (`minimum_total`). `alternative`: the new run
    that still goes on from this run's model when Continue cannot (Fine-tune from its newest save point), or None."""
    run_dir = Path(run_dir)
    layout = RunLayout(run_dir)
    manifest = read_json(layout.manifest, default=None)
    answer = dict(run_dir=str(run_dir), eligible=False, code=None, reason=None, state=None, used=None, total=None,
                  remaining=None, minimum_total=None, exhausted=False, save_point=None, alternative=None)
    if not manifest:
        return dict(answer, code='not_a_run', reason=f'{run_dir} is not a run folder.')
    status = run_status(run_dir)
    point = save_point(run_dir)
    meta = None
    if point:
        try:
            meta = ckpt.read_metadata(ckpt.resolve_checkpoint(run_dir, 'latest'))
        except (OSError, ValueError):
            meta = None
    used = ((meta or {}).get('ledger') or {}).get('charged')
    if used is None:
        used = (status.get('budget') or {}).get('charged')
    total = (manifest.get('budgets') or {}).get('max_evaluations')
    answer.update(state=status.get('state'), save_point=point, used=used, total=total)
    if isinstance(used, int) and isinstance(total, int):
        answer.update(remaining=max(0, (max_evaluations or total) - used), minimum_total=used + 1, exhausted=used >= total)

    def refused(code, reason):
        alternative = None
        if code in _FINE_TUNE_INSTEAD and point and meta and meta.get('restoration_capability') != 'search_state':
            alternative = dict(action='fine_tune', run_dir=str(run_dir), checkpoint_id=point,
                               label='Fine-tune from its newest save point (a new run)')
        return dict(answer, code=code, reason=reason, alternative=alternative)

    if status.get('worker_alive'):
        return refused('already_running', 'This run is running now: a run is never continued twice.')
    if not point:
        return refused('no_checkpoint', 'This run folder holds no save point - none was written, or a copy was made '
                                        'without them, or they were deleted - so there is nothing to go on from.')
    if save_point_code(run_dir) == 'older':
        return refused('older_code', 'This run was saved by an older version of the optimizer code, and continuing it '
                                     'needs exactly that version. Its model still loads in a new run: fine-tune or frozen.')
    try:
        config = WorkbenchConfig.model_validate(read_json(layout.effective_config))
    except (OSError, ValueError) as exc:          # a pydantic ValidationError is a ValueError
        return refused('no_config', f"The run's saved configuration cannot be read: {exc}")
    config.run.mode, config.run.model_source.run_dir = 'resume', str(run_dir)
    if max_evaluations:
        config.run.max_evaluations = max_evaluations
    try:
        task = load_task_view(config.circuit, profile_id=config.run.connection_profile_id)
    except TaskBlocked as exc:
        return refused('task_blocked', str(exc))
    config = with_circuit_content(config, task)
    report = validate(config, graph=task.base_graph, provided_metrics=set(task.provided_metrics))
    if report.blocks_run:
        return refused('validation', "The run's own saved configuration has blocking issues by today's checks, so it "
                                     'cannot go on.')
    if config.run.concurrency > task.max_concurrency:
        return refused('concurrency', f'This task supports at most {task.max_concurrency} concurrent simulation jobs')
    try:
        _resume_checks(config, task, task_definition_hash(config), layout, manifest, run_dir)
    except RunRejected as exc:
        return refused(exc.code, str(exc))
    except CompileError as exc:
        return refused('compile', str(exc))
    return dict(answer, eligible=True)


def _register_in_experiment(experiment_dir, manifest, compiled, task, created):
    experiment_dir = Path(experiment_dir)
    lock = RunLock(experiment_dir / '.experiment.lock')
    import time
    for _ in range(200):
        try:
            lock.acquire(patience=0)            # this loop is its own patience (10 s)
            break
        except RuntimeError:
            time.sleep(0.05)
    else:
        # It used to fall through and do the read-modify-write anyway: two starts within the same seconds then lost one
        # run from experiment.json and split_manifest.json, silently (review of 2026-09-23). Refusing a start is the
        # lesser harm - nothing has been created yet, and the user can simply press Start again.
        raise RunRejected(f'Another run is being registered in {experiment_dir} right now (10 s). Nothing was created; '
                          'start it again in a moment.', code='experiment_busy')
    try:
        if created or not (experiment_dir / 'data_dictionary.json').exists():
            write_data_dictionary(experiment_dir / 'data_dictionary.json')
        experiment = read_json(experiment_dir / 'experiment.json', default=None) or dict(
            layout_version=OUTPUT_LAYOUT_VERSION, experiment_id=manifest['experiment_id'],
            experiment_name=manifest['experiment_name'], created_utc=manifest['created_utc'], mock=manifest['mock'],
            mock_notice=manifest['mock_notice'], runs=[])
        experiment['runs'].append(dict(run_id=manifest['run_id'], task_id=manifest['task_id'], mode=manifest['mode'],
                                       seed=manifest['seeds']['target_seed'],
                                       relative_run_dir=manifest['output']['relative_run_dir'],
                                       created_utc=manifest['created_utc']))
        write_json(experiment_dir / 'experiment.json', experiment)
        _update_split_manifest(experiment_dir, manifest, compiled, task)
    finally:
        lock.release()


def _update_split_manifest(experiment_dir, manifest, compiled, task):
    path = Path(experiment_dir) / 'split_manifest.json'
    split = read_json(path, default=None) or dict(layout_version=OUTPUT_LAYOUT_VERSION, tasks=[], overlap_warnings=[])
    entry = dict(task_id=manifest['task_id'], task_name=manifest['task_name'], role=manifest['split'],
                 generalization_level=manifest['generalization_level'], circuit_class=task.circuit.get('circuit_class'),
                 topology_id=task.circuit.get('topology_id'), netlist_sha256=task.circuit.get('netlist_sha256'),
                 specification=[dict(metric_id=t['metric_id'], lower=t['lower'], upper=t['upper'], hard=t['hard'])
                                for t in compiled.targets if t['active']],
                 variable_ranges=[dict(variable_id=v['variable_id'], lower=v['lower'], upper=v['upper'], unit=v['unit'])
                                  for v in compiled.variables if v['optimized']],
                 initial_values=manifest['initial_dimensions'], training_sources=manifest['research']['training_sources'],
                 runs=[manifest['run_id']])
    existing = next((t for t in split['tasks'] if t['task_id'] == entry['task_id'] and t['role'] == entry['role']), None)
    if existing:
        existing['runs'].append(manifest['run_id'])
    else:
        split['tasks'].append(entry)
    warnings = []
    tasks = split['tasks']
    for i, first in enumerate(tasks):
        for second in tasks[i + 1:]:
            if first['role'] == second['role'] or 'unspecified' in (first['role'], second['role']):
                continue
            same_netlist = first['netlist_sha256'] and first['netlist_sha256'] == second['netlist_sha256']
            same_spec = first['specification'] == second['specification']
            if same_netlist and same_spec:
                warnings.append(f"{first['task_id']} ({first['role']}) and {second['task_id']} ({second['role']}) share the "
                                'same netlist AND specification: identical task across partitions.')
            elif same_netlist and 'unseen_topology' in (first['generalization_level'], second['generalization_level']):
                warnings.append(f"{first['task_id']} and {second['task_id']} share a netlist but one is labelled unseen_topology.")
            if (second['generalization_level'] == 'unseen_circuit_class'
                    and second['circuit_class'] in (second['training_sources'] or [])):
                warnings.append(f"{second['task_id']}: unseen_circuit_class but its class is listed in training_sources.")
    split['overlap_warnings'] = sorted(set(warnings))
    split['counts'] = {role: sum(1 for t in tasks if t['role'] == role)
                       for role in ('train', 'validation', 'test', 'unspecified')}
    split['limitations'] = ('Overlap checks compare netlist hashes and specifications. A differing hash does NOT prove '
                            'the absence of leakage: renamed or reordered copies of one topology hash differently. Use '
                            'analog_optimizer.evaluation.transfer.same_topology for an exact isomorphism check.')
    write_json(path, split)


# ---------------------------------------------------------------------------- worker process
def launch_worker(layout: RunLayout, *, allow_real=False):
    """Detached process (own session). Returns the pid. Never launched by tests or at import time."""
    lock = take_lock(layout.run_dir) or RunLock(layout.control / 'run.lock')
    if not lock.held_here:
        try:
            lock.acquire()
        except RuntimeError:
            raise RunRejected('This run already has an active worker', code='already_running')
    return spawn_detached('worker', ['--run-dir', str(layout.run_dir)] + (['--allow-real'] if allow_real else []),
                          lock, layout.logs / 'worker.log')


def spawn_detached(module, args, lock, log_path) -> int:
    """`python -m gator_workbench.<module> <args> --lock-fd N` in a session of its own, holding `lock`: it is handed over
    through pass_fds and this process lets go of it without releasing it. Output goes to `log_path`. Returns the pid.
    Run workers and corner-check workers start this way."""
    log = Path(log_path).open('ab')
    try:
        process = subprocess.Popen([sys.executable, '-m', f'gator_workbench.{module}', *args, '--lock-fd', str(lock.fileno())],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, cwd=str(repo_root()),
                                   env=worker_environment(), start_new_session=True, close_fds=True, pass_fds=(lock.fileno(),))
    except BaseException:
        lock.release()
        raise
    finally:
        log.close()
    lock.detach()                   # the worker now owns the (never released) lock
    return process.pid


def send_command(run_dir, command: str):
    if command not in ('pause', 'stop', 'cancel', 'checkpoint'):
        raise ValueError('command must be pause, stop, cancel or checkpoint')
    layout = RunLayout(Path(run_dir))
    if not layout.manifest.is_file():
        raise FileNotFoundError(run_dir)
    if command == 'checkpoint':
        _check_save_now(layout)
    record = dict(id=uuid4().hex, command=command, issued_utc=utcnow().isoformat())
    write_json(layout.control / 'command.json', record)
    return record


def _check_save_now(layout):
    """`checkpoint` = "Save now": the RUNNING worker saves its model at the next safe boundary and goes on.
    It is refused, with the reason, whenever nothing would come of it - and it never replaces a pause, stop or
    cancel that is still in the one-slot control file (a run on its way down saves by itself, or was told not to)."""
    status = run_status(layout.run_dir)
    if not status['worker_alive']:
        ended = dict(paused='paused', stopped='stopped', completed='finished').get(status.get('state'), 'ended')
        raise RunRejected(f'This run is not running, so there is nothing new to save: its state was saved when it {ended}.',
                          code='not_running')
    pending = (read_json(layout.control / 'command.json', default={}) or {}).get('command')
    if pending in ('pause', 'stop', 'cancel') or status.get('state') in ('pausing', 'stopping'):
        raise RunRejected('This run is already on its way to a stop' + (
            ' (forced cancel): nothing more is saved.' if pending == 'cancel' else
            ': it saves everything by itself as soon as the simulation in flight has finished.'), code='already_stopping')
    output = (read_json(layout.effective_config, default={}) or {}).get('output') or {}
    if output.get('save_checkpoints') is False:
        raise RunRejected('This run was started with "Model checkpoints" switched off, so it keeps no saved model. '
                          'Start a run with that option on to be able to save.', code='checkpoints_off')


def worker_started(run_dir, since=0.0) -> bool:
    """A worker has been started for this run since the time `since`: it holds the run lock (prepare_run holds a continue's
    until it hands it over, launch_worker a start's from just before the spawn), or the status file was written after
    `since` - prepare_run writes it as `created` and a continue's previous segment left its own, both BEFORE the launch
    record; the worker writes it within seconds of starting. The launch-request reconciliation (record 7.271): a
    "launching" record whose run shows neither never got its worker."""
    layout = RunLayout(Path(run_dir))
    try:
        if RunLock.held(layout.control / 'run.lock'):
            return True
        return layout.status.is_file() and layout.status.stat().st_mtime > since
    except OSError:
        return False


def run_status(run_dir) -> dict:
    layout = RunLayout(Path(run_dir))
    status = read_json(layout.status, default={}) or {}
    alive = RunLock.held(layout.control / 'run.lock')
    if status.get('state') in ('starting', 'running', 'pausing', 'stopping') and not alive:
        status = dict(status, state='interrupted', note='The worker process is gone without a clean shutdown. Data '
                      'acknowledged before the interruption is preserved; resume to recover and continue.')
    return dict(status, worker_alive=alive, run_dir=str(layout.run_dir))


