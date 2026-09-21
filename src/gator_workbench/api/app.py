"""Local FastAPI backend of the GATOR workbench.

* Listens on 127.0.0.1 unless the operator says otherwise. No CORS: the UI is same-origin.
* There is no endpoint that accepts a command, a host, a port or an arbitrary path. Output paths
  must lie inside operator-allowed roots; netlists inside operator-allowed input roots; bridge
  access names a configured profile identifier only. Unknown request fields are rejected.
* Training/simulation run in detached worker processes, never inside a request.
* Errors returned to the browser are redacted.
"""
from __future__ import annotations

import io
import mimetypes
import os
from pathlib import Path
from urllib.parse import quote
import zipfile

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import (__version__, aggregates, agents, bridge_connect, bridge_read, checkpoints as ckpt, connection, runs, schema,
                tasks, units)
from .. import network_presets, profile_preflight, profiles, recipes
from ..agents import AgentError, AgentRequest, AgentSettings, ProposalRejected, ProposalStore
from ..agents import catalog as agent_catalog
from ..agents import proposals as agent_proposals
from ..agents import readiness as agent_readiness
from ..agents import run_digest as agent_run_digest
from ..agents import settings_review as agent_review
from ..agents import diagnostics as agent_diagnostics
from ..agents.prompts import circuit_summary
from ..best_design import export_netlist
from ..layout import RunLayout, environment_versions
from ..paths import OutputRoots, PathNotAllowed, default_output_root, directory_bytes, repo_root, safe_child
from ..preload import preload
from ..security import redact
from ..storage.atomic import read_json, read_jsonl
from ..storage.dataset import DatasetReader, map_to_dict, utcnow
from ..storage.tables import TABLES, data_dictionary
from ..validation import validate


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')          # hosts, ports, commands... simply do not exist as fields


class ConfigBody(Body):
    config: dict


class CircuitBody(Body):
    circuit: dict


class StartBody(Body):
    config: dict
    confirm_transfer: bool = False
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False
    baseline_only: bool = False


class CommandBody(Body):
    run_dir: str
    command: str = Field(pattern='^(pause|stop|cancel|checkpoint)$')       # checkpoint = "Save now": save and go on


class ContinueBody(Body):
    run_dir: str
    max_evaluations: int | None = Field(None, ge=1)
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False


class PathBody(Body):
    path: str
    create: bool = False


class ConnectionBody(Body):
    profile_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$')
    scope: str = Field('interactive', pattern='^(cheap|interactive|full)$')
    trigger: str = Field('user', pattern='^(user|auto)$')      # auto = profile change in the UI: cheap layers only


class ConnectBody(Body):
    profile_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$')      # an identifier: never a host, port or command


class CreateConnectionBody(ConnectBody):
    """Identifiers only. `ssh_host` is a Host NAME that ~/.ssh/config of the backend user already holds (checked
    against that file by the backend); `bridge_profile` is a profile name of the bridge env file. Never an address."""
    kind: str = Field('virtuoso_ssh', pattern='^(virtuoso_ssh|virtuoso_local|ngspice_local|ngspice_ssh)$')
    ssh_host: str | None = Field(None, pattern=r'^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$')
    bridge_profile: str | None = Field(None, pattern=r'^[A-Za-z0-9_]{1,32}$')


class NetworkSettingsBody(Body):
    network: dict | None = None         # hidden_dim / heads / layers
    advanced: dict | None = None        # the SAC numbers stored per encoder; any other key is rejected


class NetworkResetBody(Body):
    to: str = Field('publication', pattern='^(publication|gator_baseline)$')


class NativeReadBody(Body):
    profile_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$')
    library: str | None = None
    cell: str | None = None
    testbench: str | None = None        # import only: the cell whose netlist is exported (the testbench around `cell`)


class CreateProfileBody(Body):
    config: dict
    name: str = Field(pattern=r'^[a-z][a-z0-9_]{1,39}$')
    recipe: str = Field(pattern=r'^[a-z_]{1,40}$')
    expected_frequency_hz: float | None = Field(None, gt=0)


class ProfileActionBody(Body):
    name: str = Field(pattern=r'^[a-z][a-z0-9_]{1,39}$')
    profile_id: str | None = Field(None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$')
    run_dir: str | None = None


class AgentSettingsBody(Body):
    provider: str
    model: str | None = None
    effort: str | None = None
    timeout_seconds: float = 300.0
    permission_mode: str = 'dontAsk'
    allowed_tools: list[str] = []
    max_turns: int | None = None
    stream: bool = True


class ProposeBody(Body):
    kind: str
    prompt: str
    config: dict
    selection: list[dict] = []
    request_id: str | None = None
    web: bool = False                  # settings_review only: this ONE request may search the web and open publication sites
    run_dir: str | None = None         # run_review only: the run whose output the agent is given a digest of


class ImportBody(ProposeBody):
    result: dict | str


class ApproveBody(Body):
    proposal_id: str
    proposal_hash: str
    config: dict


class ApplyBody(Body):
    proposal_id: str
    config: dict


class CircuitChangeBody(Body):
    circuit: dict
    changes: list[dict]
    confirmed: bool = False
    output_root: str | None = None


class ExportBody(Body):
    run_dir: str
    table: str | None = None


class ModelStructureBody(Body):
    run_dir: str
    checkpoint_id: str = Field('latest', max_length=120)


class GraphViewBody(ModelStructureBody):
    evaluation: int | None = Field(None, ge=1)      # which archived evaluation of that run; empty = the last one the save point had seen


def compatibility_unchecked(exc) -> dict:
    """The configuration on the page does not compile, so a saved model cannot be compared with it YET. Said in plain
    words for the "RL model to load" block; the developer text stays available under "Technical details"."""
    import re
    text = str(exc)
    row = re.fullmatch(r'(.+): bounds are required', text)
    unresolved = re.fullmatch(r'(.+): (.+) is unresolved', text)
    if row:
        what = (f'Parameter row "{row.group(1)}" is set to be optimized but has no lower and no upper bound. Fill in both '
                'bounds in the Parameters table, or untick "optimize" for that row.')
    elif unresolved:
        what = (f'Parameter row "{unresolved.group(1)}" points at {unresolved.group(2)}, and the loaded circuit has no usable '
                'value there. Correct the instance or parameter name of that row in the Parameters table.')
    else:
        what = 'The Parameters / Targets tables on this page cannot be turned into a task yet.'
    return dict(title='Not compared with your configuration yet: the configuration on this page is incomplete.', what=what,
                note='This says nothing about the saved model. Its facts, its network structure and its circuit graph view '
                     'are unaffected; the comparison appears as soon as the configuration is complete. The blocking '
                     'issues in the header list the same problem.',
                technical=redact(f'{type(exc).__name__}: {text}', 500))


def attachment(name: str) -> dict:
    """Content-Disposition of a download. The browser saves the file under this name."""
    encoded = quote(name)
    return {'Content-Disposition': f'attachment; filename="{name}"' if encoded == name
            else f"attachment; filename*=utf-8''{encoded}"}


def file_snapshot(path: Path, chunk_size: int = 1 << 20):
    """(size, chunks): exactly the bytes `path` holds now, however much is appended while they are sent.

    A live run keeps appending to its logs. FileResponse announces the size first and then reads to the end of the
    file, so a file that grew in between breaks the transfer. A JSONL snapshot ends on its last complete line."""
    stream = Path(path).open('rb')
    try:
        size = os.fstat(stream.fileno()).st_size
        if Path(path).suffix == '.jsonl':
            while size:                                 # a torn last line is not part of the record (see read_jsonl)
                start = max(0, size - 65536)
                stream.seek(start)
                newline = stream.read(size - start).rfind(b'\n')
                if newline >= 0 or not start:
                    size = start + newline + 1
                    break
                size = start
            stream.seek(0)
    except BaseException:
        stream.close()
        raise

    def chunks():
        with stream:
            remaining = size
            while remaining:
                block = stream.read(min(chunk_size, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
    return size, chunks()


def create_app(*, extra_output_roots=(), extra_input_roots=(), serve_frontend=True, monitor=None,
               auto_check_on_start=True, connection_stale_seconds=120.0, connector=None) -> FastAPI:
    # Endpoints run in a thread pool and import the optimizer lazily: two first imports at once corrupt
    # torch_geometric for the life of the process. Import it here, before any thread or request exists.
    preload()
    app = FastAPI(title='GATOR workbench', version=__version__, docs_url='/api/docs', openapi_url='/api/openapi.json')
    roots = OutputRoots(extra_output_roots)
    input_roots = [repo_root().resolve()] + [Path(p).expanduser().resolve() for p in extra_input_roots]
    proposals = ProposalStore()

    def active_run(profile_id):
        for run in runs.list_runs(roots, include_mock=False)[:20]:
            status = runs.run_status(run['run_dir'])
            if status.get('worker_alive') and status.get('connection_profile_id') == profile_id:
                return status
        return None
    # After `connection_stale_seconds` a result is shown as `unknown` with its age, never as a current `ok`.
    monitor = monitor or connection.ConnectionMonitor(active_run_lookup=active_run,
                                                      stale_after_seconds=float(connection_stale_seconds))
    connector = connector or bridge_connect.BridgeConnector()
    app.state.roots, app.state.monitor, app.state.proposals, app.state.connector = roots, monitor, proposals, connector

    def auto_check():
        """Once at backend start: the CHEAP layers of the active profile (package, profile, tunnel state).
        No SKILL round trip, no Virtuoso contact, nothing started or repaired. Off the request thread."""
        try:
            active = connection.load_profiles()['active']
            if active:
                monitor.check(active, scope='cheap', trigger='auto')
        except Exception:                      # a diagnostic must never prevent the backend from starting
            pass
    if auto_check_on_start:
        import threading
        app.state.auto_check_thread = threading.Thread(target=auto_check, name='gator-connection-auto-check', daemon=True)
        app.state.auto_check_thread.start()

    # ------------------------------------------------------------------ helpers
    def fail(status, message, **extra):
        raise HTTPException(status, detail=dict(message=redact(str(message), 2000), **extra))

    def parse_config(raw) -> schema.WorkbenchConfig:
        try:
            config = schema.WorkbenchConfig.model_validate(raw)
        except ValidationError as exc:
            fail(422, 'The configuration does not match the schema',
                 errors=[dict(path='.'.join(map(str, e['loc'])), message=e['msg']) for e in exc.errors()[:50]])
        authorize_circuit(config.circuit)
        return config

    def authorize_circuit(circuit):
        for name in ('netlist_path', 'parser_config_path'):
            value = getattr(circuit, name)
            if value:
                resolved = Path(value).expanduser().resolve()
                if not any(resolved == r or r in resolved.parents for r in input_roots):
                    fail(403, f'{name} is outside the allowed input roots. Roots are added by the backend operator '
                              '(--allow-input-root), never from the browser.')

    def run_path(run_dir) -> Path:
        try:
            path = roots.resolve(run_dir)
        except PathNotAllowed as exc:
            fail(403, exc)
        if not (path / 'run_manifest.json').is_file():
            fail(404, 'Not a run directory')
        return path

    def load_runtime(config, *, allow_real=False):
        try:
            return tasks.load_task(config.circuit, allow_real=allow_real, profile_id=config.run.connection_profile_id), None
        except tasks.TaskBlocked as exc:
            return None, dict(blocker=str(exc), interface_contract=exc.contract)
        except Exception as exc:
            return None, dict(blocker=redact(f'{type(exc).__name__}: {exc}', 1000), interface_contract=None)

    def agent_settings() -> AgentSettings:
        saved = runs.load_settings().get('agent') or {}
        saved['provider'] = agents.default_provider_name(saved.get('provider'))
        saved['allowed_tools'] = tuple(saved.get('allowed_tools') or ())
        # The two CLIs take different effort levels. A level kept from the other provider (or a hand-edited file)
        # means "the CLI's default" rather than an error that would take the whole Agent tab down.
        if saved.get('effort') not in agent_catalog.efforts_for(saved['provider']):
            saved['effort'] = None
        return AgentSettings(**saved).validate()

    # ------------------------------------------------------------------ meta / schema
    @app.get('/api/meta')
    def meta():
        settings = runs.load_settings()
        return dict(version=__version__, repo_root=str(repo_root()), environment=environment_versions(),
                    default_output_root=str(default_output_root()), remembered=settings,
                    output_root=runs.remembered_output_root(), allowed_output_roots=[str(r) for r in roots.roots],
                    allowed_input_roots=[str(r) for r in input_roots],
                    produces='data, configurations, models, netlists and logs only - no plots, images or reports',
                    agent_provider_default=agents.default_provider_name((settings.get('agent') or {}).get('provider')))

    @app.get('/api/schema')
    def get_schema():
        return dict(schema_version=schema.CONFIG_SCHEMA_VERSION, json_schema=schema.json_schema(),
                    editors={name: schema.editor_columns(name) for name in schema.SECTIONS},
                    section_keys=schema.SECTION_KEYS, units=sorted(units._LOOKUP), run_modes=schema.RUN_MODES,
                    encoder_types=schema.ENCODER_TYPES, tables=list(TABLES), data_dictionary=data_dictionary())

    # ------------------------------------------------------------------ per-encoder network settings
    @app.get('/api/network-settings')
    def network_settings():
        """What choosing an encoder loads: the operator's saved values, else the publication preset."""
        return network_presets.describe()

    @app.put('/api/network-settings/{encoder}')
    def save_network_settings(encoder: str, body: NetworkSettingsBody):
        """Editing a value in the panel stores it for THAT encoder. The whole value set is validated."""
        try:
            return network_presets.save(encoder, body.network, body.advanced)
        except KeyError:
            fail(404, f'Unknown encoder: {encoder}')
        except network_presets.InvalidNetworkSettings as exc:
            fail(422, exc)

    @app.post('/api/network-settings/{encoder}/reset')
    def reset_network_settings(encoder: str, body: NetworkResetBody):
        try:
            return network_presets.reset(encoder, body.to)
        except KeyError:
            fail(404, f'Unknown encoder: {encoder}')

    @app.get('/api/tasks')
    def get_tasks():
        return dict(tasks=tasks.list_tasks(), real_interface_contract=tasks.REAL_INTERFACE_CONTRACT)

    @app.get('/api/tasks/starter')
    def starter(task_key: str):
        """The rows the three editors start from for a registered task. A real task: its profile's parameters and, for a
        verified circuit, its targets of record - read from local files, no connection and no simulation."""
        try:
            return tasks.starter_config(task_key)
        except KeyError:
            fail(404, 'No starter configuration for this task')
        except Exception as exc:                           # a generated profile whose files no longer pass their own checks
            fail(409, redact(f'The starting rows of {task_key} cannot be built: {type(exc).__name__}: {exc}', 600))

    # ------------------------------------------------------------------ circuit
    @app.post('/api/circuit/load')
    def circuit_load(body: CircuitBody):
        try:
            circuit = schema.CircuitReference.model_validate(body.circuit)
        except ValidationError as exc:
            fail(422, exc)
        authorize_circuit(circuit)
        shell = schema.WorkbenchConfig.model_validate(dict(circuit=circuit.model_dump(), run=dict(max_evaluations=1)))
        runtime, blocked = load_runtime(shell)
        # A Virtuoso cell that already has a registered task - a profile generated from it, or one of the verified
        # built-in circuits - is not "browse only", and gets no second profile: the form points to its task.
        existing = profiles.task_for_cell(circuit.library, circuit.cell) if circuit.source == 'virtuoso' and circuit.library and circuit.cell else None
        native = dict(profile_task=existing and existing['task_key'], profile_task_generated=existing and existing['generated'],
                      profile_recipes=[dict(id=key, label=value['label']) for key, value in profiles.RECIPES.items()]) if circuit.source == 'virtuoso' else {}
        if runtime is None:
            return dict(loaded=False, **blocked, **native)
        graph = runtime.base_graph
        tree = {}
        for device in graph.devices:
            node = tree
            for part in device.id.split('/'):
                node = node.setdefault(part, {})
        return dict(loaded=True, task_key=runtime.task_key, mock=runtime.mock, circuit=runtime.circuit,
                    content_sha256=runtime.circuit.get('netlist_sha256'), provided_metrics=list(runtime.provided_metrics),
                    hierarchy=tree, summary=circuit_summary(graph, circuit=runtime.circuit), complete=graph.complete,
                    diagnostics=[dict(code=d.code, severity=d.severity, message=d.message) for d in graph.diagnostics],
                    analysis_context=graph.metadata.get('analysis_context'), notes=runtime.notes,
                    evaluation_backend=runtime.circuit.get('evaluation_backend'), max_concurrency=runtime.max_concurrency,
                    native_draft=bool(runtime.circuit.get('native_draft')), generated_profile=bool(runtime.circuit.get('generated_profile')),
                    baseline_recorded=runtime.circuit.get('baseline_recorded'), **native)

    @app.post('/api/circuit/modify')
    def circuit_modify(body: CircuitChangeBody):
        """proposal -> structured diff -> user confirmation -> execution on a WORKING COPY -> reread + validate.
        The original netlist is never overwritten. A netlist is not a native schematic."""
        circuit = schema.CircuitReference.model_validate(body.circuit)
        authorize_circuit(circuit)
        if circuit.source == 'virtuoso':
            fail(501, 'Writing a native schematic is not implemented. Contract: connection gate write_cellview, explicit '
                      'user confirmation, execution on a NEW cellview (never the original or a PDK library), reread '
                      'and validate. The bridge offers schematic.create/modify/edit/plan for this.',
                 required_gate='write_cellview', needed_layers=list(connection.ACTION_LAYERS['write_cellview']))
        shell = schema.WorkbenchConfig.model_validate(dict(circuit=circuit.model_dump(), run=dict(max_evaluations=1)))
        runtime, blocked = load_runtime(shell)
        if runtime is None:
            fail(409, blocked['blocker'])
        members, diff = [], []
        for change in body.changes:
            try:
                value = units.to_canonical(float(change['new_value']), change['unit'])
            except (KeyError, ValueError, units.UnitError) as exc:
                fail(422, f'Invalid circuit change: {exc}')
            current = runtime.base_graph.parameters.get(change['instance_path'], {}).get(change['parameter_name'])
            if current is None:
                fail(422, f"{change['instance_path']}.{change['parameter_name']} is not in the circuit")
            members.append(dict(instance_path=change['instance_path'], parameter_name=change['parameter_name'], value=value))
            diff.append(dict(instance_path=change['instance_path'], parameter_name=change['parameter_name'],
                             before=current.value, after=value, before_expression=current.raw))

        def reparse(text):
            from analog_optimizer.netlist.config import ParserConfig
            from analog_optimizer.netlist.spectre_parser import SpectreParser
            return SpectreParser(ParserConfig.from_file(runtime.parser_config_path)).parse_text(
                text, source=runtime.netlist_path, top=runtime.circuit.get('dut_hierarchy'))
        outcome = export_netlist(runtime.netlist_text, runtime.base_graph, members, reparse=reparse)
        if outcome['status'] != 'verified':
            fail(409, f"The change cannot be applied safely: {outcome['reason']}")
        if not body.confirmed:
            return dict(applied=False, diff=diff, note='Structured diff only. Confirm to write a working copy.')
        root = roots.resolve(body.output_root or runs.remembered_output_root())
        target_dir = root / 'working_copies'
        target_dir.mkdir(parents=True, exist_ok=True)
        from uuid import uuid4
        target = target_dir / f'{Path(runtime.netlist_path).stem}__{uuid4().hex[:10]}.scs'
        target.write_text(outcome['text'], encoding='utf8')
        return dict(applied=True, diff=diff, working_copy=str(target), original_untouched=runtime.netlist_path,
                    revalidate=['variable references', 'measurement nodes', 'test environment', 'checkpoint compatibility'],
                    note='Reload the circuit from the working copy. The task identity changed, so earlier approvals and '
                         'a full resume of earlier runs no longer apply. No native schematic was generated.')

    @app.post('/api/virtuoso/libraries')
    def native_libraries(body: NativeReadBody):
        return _native(body, 'libraries')

    @app.post('/api/virtuoso/cells')
    def native_cells(body: NativeReadBody):
        """The cells of one library with their views, and the library's technology library. Read-only."""
        return _native(body, 'cells')

    @app.post('/api/virtuoso/read')
    def native_read(body: NativeReadBody):
        return _native(body, 'read_schematic')

    @app.post('/api/virtuoso/import')
    def native_import(body: NativeReadBody):
        """Explicit click: read a cell INTO the workbench - Virtuoso's netlist export of the testbench (or of the
        cell) plus the parameter readback, kept locally (`native_cells`). Gated and read-only; zero cost. The cell
        can then be shown, edited against, validated and summarized for the agent. It cannot run: no profile."""
        return _native(body, 'import_cell')

    @app.post('/api/virtuoso/profile')
    def native_create_profile(body: CreateProfileBody):
        """Explicit click: turn the cell that was read into the workbench + the rows of the three editors into a
        circuit profile and register it as `real:<name>`. Contacts nothing (no Virtuoso, no simulation). Whatever the
        verified real backend cannot do is refused with the reason. Returns the rows ADJUSTED onto the width grid: a
        real run requires the configured variables to be exactly the registered ones."""
        config = parse_config(body.config)
        try:
            return profiles.create_profile(body.name, config, recipe=body.recipe, expected_frequency_hz=body.expected_frequency_hz)
        except profiles.ProfileError as exc:
            fail(409, exc, code='profile_refused')

    @app.post('/api/virtuoso/profile/preflight')
    def native_profile_preflight(body: ProfileActionBody):
        """Explicit click: check a generated profile against the LIVE cell without simulating - the run adapter
        connects, Virtuoso exports, the export is compared with the record, the deck is written. Read-only, zero
        cost, gated. It takes the session lock of a real run, so the two exclude each other."""
        if not body.profile_id:
            fail(422, 'A connection profile is required')
        try:
            return profile_preflight.preflight(monitor, body.name, body.profile_id)
        except PermissionError as exc:
            raise HTTPException(409, detail=dict(message=str(exc), gate=getattr(exc, 'gate', None)))
        except KeyError:
            fail(404, 'Unknown generated profile')
        except Exception as exc:
            fail(502, exc)

    @app.post('/api/virtuoso/profile/reference')
    def native_profile_reference(body: ProfileActionBody):
        """Explicit click: the real baseline of a finished run of this task becomes the profile's reference (read
        from the run's own tables; never replaced once recorded). Without `run_dir`: the newest run of the task."""
        try:
            run_dir = run_path(body.run_dir) if body.run_dir else profiles.latest_baseline_run(
                body.name, [r['run_dir'] for r in runs.list_runs(roots, include_mock=False)])
            if run_dir is None:
                fail(409, f'No run of real:{body.name} was found under the output root. Run "Single baseline simulation" first.',
                     code='no_baseline_run')
            return profiles.record_reference(body.name, run_dir)
        except profiles.ProfileError as exc:
            fail(409, exc, code='reference_refused')

    @app.post('/api/virtuoso/profile/delete')
    def native_profile_delete(body: ProfileActionBody):
        """Explicit click (the page asks once more): take a generated profile out of the registered tasks, so its cell
        can get a new one. Contacts nothing. The folder is kept aside, the runs that were made keep their data; refused
        while a worker is on a run of the task, and for the verified built-in circuits."""
        try:
            return profiles.delete_profile(body.name, run_rows=runs.list_runs(roots, include_mock=False))
        except profiles.ProfileError as exc:
            fail(409, exc, code='delete_refused')

    def _native(body, op):
        try:
            return bridge_read.read(monitor, body.profile_id, op, library=body.library, cell=body.cell,
                                    testbench=body.testbench if op == 'import_cell' else None)
        except PermissionError as exc:
            raise HTTPException(409, detail=dict(message=str(exc), gate=getattr(exc, 'gate', None)))
        except (KeyError, ValueError) as exc:
            fail(422, exc)
        except Exception as exc:
            fail(502, exc)

    # ------------------------------------------------------------------ configuration
    @app.post('/api/config/validate')
    def config_validate(body: ConfigBody):
        config = parse_config(body.config)
        runtime, blocked = load_runtime(config)
        draft = runtime is not None and bool(runtime.circuit.get('native_draft'))
        # A cell read from Virtuoso has no profile yet: which metrics it will provide is unknown (not checked),
        # and it must never look startable.
        report = validate(config, graph=None if runtime is None else runtime.base_graph,
                          provided_metrics=None if runtime is None or draft else set(runtime.provided_metrics))
        if draft:
            report.add('blocker', 'circuit_profile_missing', 'circuit', tasks.NATIVE_DRAFT_NOT_EXECUTABLE)
        return dict(report.as_dict(), config_hash=schema.config_hash(config),
                    task_definition_hash=schema.task_definition_hash(config), circuit_blocker=blocked,
                    mock=None if runtime is None else runtime.mock)

    @app.post('/api/config/diff')
    def config_diff(body: dict):
        from ..agents.proposals import structured_diff
        return dict(diff=structured_diff(body.get('before') or {}, body.get('after') or {}))

    # ------------------------------------------------------------------ output settings
    @app.get('/api/output/browse')
    def output_browse(path: str | None = None):
        try:
            return roots.browse(path)
        except PathNotAllowed as exc:
            fail(403, exc)

    @app.post('/api/output/check')
    def output_check(body: PathBody):
        result = roots.check(body.path, create=body.create)
        if result['allowed'] and result['resolved']:
            result['mock_data_root'] = str(Path(result['resolved']) / 'mock')
            result['bytes_used'] = directory_bytes(result['resolved']) if Path(result['resolved']).is_dir() else 0
        return result

    # ------------------------------------------------------------------ connection (section 2.1)
    @app.get('/api/connection/profiles')
    def connection_profiles():
        return connection.public_profiles()

    @app.get('/api/connection/status')
    def connection_status(profile_id: str = Query(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$')):
        return bridge_connect.describe(monitor.status(profile_id))

    @app.post('/api/connection/check')
    def connection_check(body: ConnectionBody):
        """Read-only and zero-cost; never a baseline simulation. trigger=auto (profile change) is limited
        to the cheap layers by the monitor itself. The answer carries a one-sentence `summary` and, once the
        tunnel layer is known, the `ciw` line to load in Virtuoso."""
        try:
            return bridge_connect.describe(monitor.check(body.profile_id, scope=body.scope, trigger=body.trigger))
        except ValueError as exc:
            fail(422, exc)

    @app.get('/api/connection/setup')
    def connection_setup():
        """What "Create connection" would use, per kind of connection: the bridge setup, the ngspice and ssh programs
        and the Host NAMES of ~/.ssh/config found on THIS host. Locates and names; contacts nothing."""
        return bridge_connect.detect_setup()

    @app.post('/api/connection/profile')
    def connection_create_profile(body: CreateConnectionBody):
        """Explicit click. The browser names the new connection and its kind; every path comes from this host and
        an ssh machine only by a Host name this host already holds. Existing connections are operator-owned and are
        never changed: a new one is added next to them, the previous file is kept as a copy."""
        try:
            created = bridge_connect.create_profile(body.profile_id, kind=body.kind, ssh_host=body.ssh_host,
                                                    bridge_profile=body.bridge_profile)
        except bridge_connect.ProfileExists as exc:
            fail(409, exc, code='profile_exists')
        except FileExistsError as exc:
            fail(409, exc, code='connection_file_unreadable')
        except bridge_connect.SetupNotFound as exc:
            fail(409, exc, code=exc.reason_code)
        except ValueError as exc:
            fail(422, exc)
        return dict(created, profiles=connection.public_profiles())

    @app.post('/api/connection/connect')
    def connection_connect(body: ConnectBody):
        """Explicit click: start the SSH tunnel of a configured Virtuoso profile (as `virtuoso-bridge start` does; for
        Virtuoso on this machine it sets the local bridge up instead) and report the line to load in the CIW. A
        running tunnel is left untouched; nothing is ever stopped or restarted. Followed by the CHEAP check (no
        Virtuoso contact) so the indicator shows the new state. An ngspice connection has nothing to start."""
        try:
            settings = connection.resolve_profile_id(body.profile_id)
        except KeyError:
            fail(404, 'Unknown connection profile', code='profile_not_configured')
        if connection.family_of(connection.profile_kind(settings)) == 'ngspice':
            fail(409, bridge_connect.NEXT_STEPS['nothing_to_connect'], code='nothing_to_connect')
        result = connector.connect(body.profile_id)
        return dict(connect=result, status=bridge_connect.describe(monitor.check(body.profile_id, scope='cheap', trigger='user')))

    # ------------------------------------------------------------------ runs
    @app.get('/api/runs')
    def get_runs(output_root: str | None = None, include_mock: bool = True):
        try:
            return dict(runs=runs.list_runs(roots, output_root, include_mock=include_mock))
        except PathNotAllowed as exc:
            fail(403, exc)

    @app.post('/api/runs/suggest-mode')
    def suggest_mode(body: dict):
        config = parse_config(body.get('config'))
        source = body.get('source_run_dir')
        if source:
            run_path(source)
        return runs.suggest_mode(config, source)

    @app.post('/api/runs/model')
    def describe_model(body: dict):
        """The selected RL model: source task, save time, schema, counters, actual path, restorable
        components and compatibility with the CURRENT configuration. Independent of the agent model."""
        run_dir = run_path(body.get('run_dir'))
        try:
            description = ckpt.describe(run_dir, body.get('checkpoint_id') or 'latest')
        except FileNotFoundError as exc:
            fail(404, exc)
        result = dict(description=description)
        if body.get('config'):
            config = parse_config(body['config'])
            runtime, blocked = load_runtime(config)
            if runtime is not None:
                from ..compile import CompileError, compile_task
                from ..engine import learner_experiment
                from .. import modes
                config = runs.with_circuit_content(config, runtime)
                task_hash = schema.task_definition_hash(config)
                try:
                    compiled = compile_task(config, runtime.base_graph)
                except CompileError as exc:
                    # The configuration ON THE PAGE is not complete yet. That is no fault of the saved model: its
                    # facts are still returned, and the page says in plain words what is missing (it used to be a
                    # 500 "CompileError: mp1_w: bounds are required" that hid the model as well).
                    result['compatibility_unchecked'] = compatibility_unchecked(exc)
                else:
                    contract = modes.current_contract(learner_experiment(config, runtime, task_hash),
                                                      modes.model_config_from(config.run.network),
                                                      modes.sac_config_from(config.run.advanced), compiled.spec_schema)
                    meta_ = ckpt.read_metadata(description['path'])
                    mode = config.run.mode if config.run.mode != 'scratch' else 'fine_tune'
                    result['compatibility'] = ckpt.check_compatibility(meta_, mode=mode, task_definition_hash=task_hash,
                                                                       contract=contract)
                result['suggestion'] = runs.suggest_mode(config, run_dir)
        return result

    @app.get('/api/runs/default-model')
    def default_model(project: str):
        """Default = last compatible model used by this project, and that run's `latest`, not `best`."""
        last = (runs.load_settings().get('last_run') or {}).get(project)
        if not last or not roots.is_allowed(last) or not (Path(last) / 'checkpoints' / 'latest.json').is_file():
            return dict(run_dir=None, checkpoint_id='latest', reason='No previous model for this project.')
        return dict(run_dir=last, checkpoint_id='latest', description=ckpt.describe(last, 'latest'))

    @app.get('/api/runs/models')
    def saved_models(output_root: str | None = None, include_mock: bool = True):
        """The model chooser's list: every run that holds a saved RL model, with all of its save points.
        Small metadata files only; the selected model is verified by `/api/runs/model` as before."""
        try:
            return dict(models=ckpt.saved_models(runs.list_runs(roots, output_root, include_mock=include_mock)))
        except PathNotAllowed as exc:
            fail(403, exc)

    @app.post('/api/runs/model/structure')
    def model_structure_table(body: ModelStructureBody):
        """Every layer of the chosen saved model with its type, shape and parameter count - a table, no plot.
        Tensor-only read of `model_weights.pt` after its checksum matched; types only when the rebuilt network
        holds exactly the saved tensors."""
        from .. import model_structure
        run_dir = run_path(body.run_dir)
        try:
            return model_structure.structure(ckpt.resolve_checkpoint(run_dir, body.checkpoint_id))
        except FileNotFoundError as exc:
            fail(404, exc)
        except ValueError as exc:
            fail(409, exc)

    @app.post('/api/runs/model/graph-view')
    def model_graph_view(body: GraphViewBody):
        """The data of the circuit graph view: the chosen save point replayed on a state its own run ARCHIVED -
        the circuit, the attention on every connection, the size the policy proposes per group. One forward pass on
        the CPU; nothing is simulated and nothing is written. The picture is drawn in the browser only."""
        from .. import graph_view
        run_dir = run_path(body.run_dir)
        try:
            return graph_view.graph_view(run_dir, body.checkpoint_id, evaluation=body.evaluation)
        except FileNotFoundError as exc:
            fail(404, exc)
        except ValueError as exc:                  # GraphViewUnavailable included: said in plain words
            fail(409, exc)

    def _start(config, body, *, baseline_only=False):
        allow_real = bool(body.authorize_real_simulation)
        if baseline_only:
            config = config.model_copy(deep=True)
            config.run.mode, config.run.max_evaluations = 'scratch', 1         # exactly ONE costed evaluation
            config.output.save_checkpoints = False
            config.project.task_name = f'{config.project.task_name}.baseline'
        try:
            layout, manifest = runs.prepare_run(config, roots, allow_real=allow_real,
                                                confirm_transfer=getattr(body, 'confirm_transfer', False), monitor=monitor,
                                                acknowledge_unknown=body.acknowledge_unknown_connection)
        except runs.RunRejected as exc:
            raise HTTPException(409, detail=dict(message=redact(str(exc), 2000), code=exc.code, report=exc.report))
        except PathNotAllowed as exc:
            fail(403, exc)
        if baseline_only:
            manifest['run_kind'] = 'baseline_preflight'
            manifest['notes'].append('Single baseline simulation: a costed preflight evaluation, not a free check.')
            from ..storage.atomic import write_json
            write_json(layout.manifest, manifest)
        pid = runs.launch_worker(layout, allow_real=allow_real and not manifest['mock'])
        return dict(run_dir=str(layout.run_dir), run_id=manifest['run_id'], mock=manifest['mock'], worker_pid=pid,
                    paths=layout.subpaths(), connection_gate=manifest.get('connection_gate'),
                    mock_notice=manifest['mock_notice'])

    @app.post('/api/runs/start')
    def start(body: StartBody):
        return _start(parse_config(body.config), body, baseline_only=body.baseline_only)

    @app.post('/api/runs/continue')
    def continue_run(body: ContinueBody):
        run_dir = run_path(body.run_dir)
        config = schema.WorkbenchConfig.model_validate(read_json(RunLayout(run_dir).effective_config))
        config.run.mode, config.run.model_source.run_dir = 'resume', str(run_dir)
        if body.max_evaluations:
            config.run.max_evaluations = body.max_evaluations
        return _start(config, body)

    @app.post('/api/runs/command')
    def command(body: CommandBody):
        try:
            return runs.send_command(run_path(body.run_dir), body.command)
        except runs.RunRejected as exc:            # "Save now" on a run that cannot or need not save: said, not done
            raise HTTPException(409, detail=dict(message=redact(str(exc), 2000), code=exc.code))

    @app.get('/api/runs/status')
    def status(run_dir: str):
        path = run_path(run_dir)
        layout = RunLayout(path)
        result = runs.run_status(path)
        manifest = read_json(layout.manifest, default={}) or {}
        result.update(manifest=dict(mode=manifest.get('mode'), mock=manifest.get('mock'), task_id=manifest.get('task_id'),
                                    seeds=manifest.get('seeds'), source_model=manifest.get('source_model'),
                                    budgets=manifest.get('budgets'), output=manifest.get('output'),
                                    connection_gate=manifest.get('connection_gate'), mock_notice=manifest.get('mock_notice')),
                      summary=read_json(layout.summary, default=None))
        profile = (result.get('connection_profile_id') or None)
        result['connection'] = monitor.status(profile) if profile else dict(overall='not_applicable')
        return result

    @app.get('/api/runs/files')
    def files(run_dir: str):
        path = run_path(run_dir)
        entries = []
        for item in sorted(p for p in path.rglob('*') if p.is_file()):
            relative = item.relative_to(path).as_posix()
            if relative.startswith('work/') or relative.endswith('.lock'):
                continue
            stat = item.stat()
            entries.append(dict(path=relative, bytes=stat.st_size, modified_utc=utcnow().fromtimestamp(
                stat.st_mtime, tz=utcnow().tzinfo).isoformat()))
        return dict(run_dir=str(path), files=entries, total_bytes=sum(e['bytes'] for e in entries),
                    paths=RunLayout(path).subpaths())

    @app.get('/api/runs/table')
    def table(run_dir: str, table: str, limit: int = Query(20, ge=1, le=500), tail: bool = True):
        if table not in TABLES:
            fail(404, 'Unknown table')
        reader = DatasetReader(run_path(run_dir) / 'data')
        rows = reader.rows(table)
        rows = rows[-limit:] if tail else rows[:limit]
        clean = []
        for row in rows:
            for column in TABLES[table]['columns']:
                value = row[column.name]
                if column.type.startswith('map') and value is not None:
                    row[column.name] = map_to_dict(value)
                elif hasattr(value, 'isoformat'):
                    row[column.name] = value.isoformat()
            clean.append({k: v for k, v in row.items() if not k.endswith('_json')})
        return dict(table=table, total_rows=reader.row_counts()[table], cutoff_commit_seq=reader.cutoff_seq,
                    columns=[c.name for c in TABLES[table]['columns'] if not c.name.endswith('_json')], rows=clean)

    @app.get('/api/runs/logs')
    def logs(run_dir: str, kind: str = Query('events', pattern='^(events|errors)$'), limit: int = Query(100, ge=1, le=1000)):
        return dict(kind=kind, entries=read_jsonl(run_path(run_dir) / 'logs' / f'{kind}.jsonl')[-limit:])

    @app.get('/api/runs/download')
    def download(run_dir: str, path: str):
        try:
            target = safe_child(run_path(run_dir), path)
        except PathNotAllowed as exc:
            fail(403, exc)
        if not target.is_file():
            fail(404, 'No such file')
        size, chunks = file_snapshot(target)             # a live run's logs grow while they are downloaded
        return StreamingResponse(chunks, media_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream',
                                 headers={'Content-Length': str(size), **attachment(target.name)})

    @app.post('/api/runs/export-csv')
    def export_csv(body: ExportBody):
        if body.table not in TABLES:
            fail(404, 'Unknown table')
        path = aggregates.export_table_csv(run_path(body.run_dir), body.table)
        return dict(path=str(path), relative=str(path.relative_to(run_path(body.run_dir))))

    @app.post('/api/runs/export-package')
    def export_package(body: ExportBody):
        """Data-only package: JSON, Parquet, CSV, JSONL, netlists. No waveforms, work files or models."""
        path = run_path(body.run_dir)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(p for p in path.rglob('*') if p.is_file()):
                relative = item.relative_to(path).as_posix()
                if relative.split('/')[0] in ('work', 'control', 'waveforms', 'checkpoints') or '/_quarantine/' in relative:
                    continue
                archive.write(item, relative)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type='application/zip',
                                 headers={'Content-Disposition': f'attachment; filename="{path.name}__data.zip"'})

    @app.post('/api/aggregates/export')
    def export_aggregates(body: dict):
        run_dir = run_path(body.get('run_dir'))
        experiment = RunLayout(run_dir).experiment_dir
        return dict(experiment_dir=str(experiment), files=aggregates.export_aggregates(experiment))

    @app.get('/api/aggregates/download')
    def download_aggregates(run_dir: str):
        """The research CSVs of this run's experiment as one zip: they lie above the run directory, where the per-file
        download cannot reach. Only what the exporter writes (<table>.csv + <table>.meta.json), as it is on disk now."""
        experiment = RunLayout(run_path(run_dir)).experiment_dir
        members = [experiment / 'aggregates' / f'{table}{suffix}' for table in aggregates.COLUMNS for suffix in ('.csv', '.meta.json')]
        members = [m for m in members if m.is_file() and not m.is_symlink()]
        if not members:
            fail(404, 'No research CSVs have been exported for this experiment yet')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for item in members:
                archive.write(item, item.name)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type='application/zip', headers=attachment(f'{experiment.name}__aggregates.zip'))

    # ------------------------------------------------------------------ agent assistance
    @app.get('/api/agent/diagnostics')
    def diagnostics():
        return dict(agent_diagnostics.diagnose(), availability=agents.availability(), selected=agent_settings().provider)

    @app.get('/api/agent/settings')
    def get_agent_settings():
        settings = agent_settings()
        return dict(vars(settings), allowed_tools=list(settings.allowed_tools), availability=agents.availability(),
                    catalog=agent_catalog.for_api(),        # static table + one local file read: no CLI, no model call
                    note='Agent model, effort, timeout and tools are independent of RL checkpoints, simulator '
                         'concurrency and evaluation budgets.')

    @app.put('/api/agent/settings')
    def put_agent_settings(body: AgentSettingsBody):
        try:
            settings = AgentSettings(**dict(body.model_dump(), allowed_tools=tuple(body.allowed_tools))).validate()
            agents.make_provider(settings)
        except AgentError as exc:
            raise HTTPException(422, detail=exc.as_dict())
        runs.save_settings(agent=dict(vars(settings), allowed_tools=list(settings.allowed_tools)))
        return dict(saved=True, provider=settings.provider)

    def run_readiness(config, runtime, blocked) -> dict:
        """The start checklist. Free: static validation, the output-root check and the monitor's CACHED connection
        status - no bridge contact, no simulator, no agent. A fresh connection test stays the user's button."""
        report = validate(config, graph=None if runtime is None else runtime.base_graph,
                          provided_metrics=None if runtime is None else set(runtime.provided_metrics)).as_dict()
        profile_id = config.run.connection_profile_id
        try:
            link = monitor.status(profile_id) if profile_id and runtime is not None and not runtime.mock else None
        except (KeyError, ValueError):
            link = None
        try:
            output = roots.check(config.output.output_root or runs.remembered_output_root(), create=False, verify_windows=False)
        except Exception:                                  # a checklist must never fail because one line cannot be filled in
            output = None
        # A real circuit profile fixes WHICH sizes may be written and their range and grid. The engine checks that only when
        # the worker starts (after the budget was authorized), so say it here: compile offline and compare with the profile.
        fixed = tasks.profile_parameter_rows(runtime)
        profile = None
        if fixed:
            matches = problem = None
            broken = any(i['level'] in ('error', 'blocker') and str(i['path']).startswith('parameters') for i in report['issues'])
            if config.parameters and not broken:
                try:
                    from analog_optimizer.envs.sizing import graph_contract
                    from ..compile import compile_task
                    matches = graph_contract(compile_task(config, runtime.base_graph).graph) == graph_contract(runtime.base_graph)
                except Exception as exc:                   # it does not compile: a start would be refused for that alone
                    problem = redact(f'{type(exc).__name__}: {exc}', 300)
            profile = dict(rows=fixed, matches=matches, error=problem)
        return agent_readiness.build(config.model_dump(mode='json'), task=runtime, task_blocker=(blocked or {}).get('blocker'),
                                     validation=report, connection=link, output=output, profile=profile)

    def check_suggestions(request, proposal):
        """Every suggested setting is tried on a COPY of the configuration - schema, then static validation with the loaded
        circuit - so the user sees which rows are legal before applying one. Nothing is applied here."""
        if request.kind not in ('settings_review', 'run_review'):
            return
        runtime, _ = load_runtime(parse_config(request.config))

        def validate_config(raw):
            try:
                parsed = schema.WorkbenchConfig.model_validate(raw)
            except ValidationError as exc:
                return '; '.join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3]), []
            report = validate(parsed, graph=None if runtime is None else runtime.base_graph,
                              provided_metrics=None if runtime is None else set(runtime.provided_metrics))
            return None, [issue.code for issue in report.issues if issue.level in ('error', 'blocker')]
        checked = agent_review.check(request.config, proposal['suggestions'], validate_config=validate_config)
        proposal['suggestions'], proposal['suggestions_together'] = checked['suggestions'], checked['all_together']

    def readiness_after(request, proposal):
        """Would the run start once this proposal is applied? The backend's own answer on the patched configuration -
        never the agent's claim. None when it cannot be worked out (the proposal itself is unaffected)."""
        try:
            patched = parse_config(agent_proposals.apply_patch(request.config, proposal['patch'], selection=request.selection))
            runtime, blocked = load_runtime(patched)
            after = run_readiness(patched, runtime, blocked)
        except Exception:
            return None
        state = {item['id']: item['status'] for item in after['items']}
        was_missing = [item for item in (request.readiness or {}).get('items', []) if item['status'] == 'missing' and item['id'] != 'start']
        return dict(ready=after['ready'], changed_rows=len(proposal['diff']),
                    resolved=[item['title'] for item in was_missing if state.get(item['id']) != 'missing'],
                    remaining=[dict(title=item['title'], who=item['who'], detail=item['detail'], action=item['action'])
                               for item in after['items'] if item['status'] == 'missing' and item['id'] != 'start'],
                    note='Worked out by the backend on the configuration as it would be after approval.')

    def _request(body) -> tuple:
        config = parse_config(body.config)
        runtime, blocked = load_runtime(config)
        summary = None if runtime is None else circuit_summary(runtime.base_graph, circuit=runtime.circuit)
        if summary is not None and not runtime.mock:
            # A real backend produces a fixed set of results per circuit type, and writes transistor widths only. Said to
            # the agent, so its measurement rows name results that exist and its variables are ones that can be written.
            if runtime.circuit.get('native_draft'):
                summary['results_by_circuit_type'] = {key: list(recipes.provided_metrics(key)) for key in profiles.RECIPES}
                summary['real_backend_limits'] = (
                    'This cell has no circuit profile yet. When one is created from your proposal: a measurement with '
                    'result_source "backend_profile" must use a source_name from results_by_circuit_type for the fitting circuit '
                    'type; only transistor widths can be optimized (parameter "w" of an nmos/pmos directly inside the core cell, '
                    'single finger, m = 1), on a 5 nm grid with a linear range that contains the present width. Identical or '
                    'matched transistors should follow one leader through binding_group with ratio 1. A target\'s metric_id must be '
                    'one of those result names too (the profile registers exactly them for the optimizer).')
            else:
                summary['results_provided'] = list(runtime.provided_metrics)
            if runtime.reference_metrics:
                # Verified REAL results of the design AS IT STANDS (its recorded baseline). The only numbers a PROVISIONAL
                # "no worse than the initial design" target may be built from; nothing here is a requirement of the user.
                summary['initial_design_results'] = runtime.reference_metrics
        circuit_hash = None if runtime is None else runtime.circuit.get('netlist_sha256')
        ready, review = run_readiness(config, runtime, blocked), None
        if body.kind == 'settings_review':
            # Settings, cited presets and a digest of the task - and nothing of the design (no instance, net or size), so a
            # request that may read web pages has nothing of it to give away.
            raw = config.model_dump(mode='json')
            review = dict(task=agent_review.task_digest(raw, summary), settings=agent_review.settings_data(raw),
                          publication_presets=agent_review.publication_presets(), run_readiness=agent_review.readiness_digest(ready))
            summary = None
        results = None
        if body.kind == 'run_review':
            if not body.run_dir:
                raise AgentError('invalid_request', 'A run_review needs a run: choose one with "Runs..." first')
            # The agent reads no file: the backend condenses the run's own records. `run_path` keeps it inside the allowed roots.
            results = agent_run_digest.load(run_path(body.run_dir))
            review = dict(settings=agent_review.settings_data(config.model_dump(mode='json')))      # so a suggestion names a real setting
        request = AgentRequest(kind=body.kind, user_prompt=body.prompt, config=config.model_dump(mode='json'),
                               circuit_summary=summary, selection=body.selection, readiness=ready, review=review, results=results,
                               web=bool(body.web), web_domains=agent_review.domains(runs.load_settings().get('agent_web_domains')))
        if body.request_id:
            request.request_id = body.request_id
        return request, circuit_hash

    @app.post('/api/agent/propose')
    def propose(body: ProposeBody):
        """Proposal only. Applying needs approval; circuit writes and simulations need their own authorization."""
        try:
            request, circuit_hash = _request(body)
            provider = agents.make_provider(agent_settings())
            result = provider.propose(request)
            proposal = proposals.create(request, result, circuit_hash=circuit_hash)
        except AgentError as exc:
            raise HTTPException(409, detail=dict(exc.as_dict(), configuration_unchanged=True))
        proposal['readiness_after'] = readiness_after(request, proposal)
        check_suggestions(request, proposal)
        _audit(proposal)
        return proposal

    @app.post('/api/agent/readiness')
    def readiness(body: ConfigBody):
        """What is still missing before this run can start. Computed here: no agent is called and nothing is probed."""
        config = parse_config(body.config)
        runtime, blocked = load_runtime(config)
        return run_readiness(config, runtime, blocked)

    @app.post('/api/agent/cancel')
    def cancel(body: dict):
        return dict(cancelled=agents.REGISTRY.cancel(str(body.get('request_id'))))

    @app.post('/api/agent/export-task')
    def export_task(body: ProposeBody):
        try:
            request, _ = _request(body)
            return agents.DisabledProvider().export_task(request)
        except AgentError as exc:
            raise HTTPException(422, detail=exc.as_dict())

    @app.post('/api/agent/import-result')
    def import_result(body: ImportBody):
        try:
            request, circuit_hash = _request(body)
            result = agents.DisabledProvider().import_result(request, body.result)
            proposal = proposals.create(request, result, circuit_hash=circuit_hash)
            proposal['readiness_after'] = readiness_after(request, proposal)
            check_suggestions(request, proposal)
            return proposal
        except AgentError as exc:
            raise HTTPException(409, detail=dict(exc.as_dict(), configuration_unchanged=True))

    def _circuit_hash(config):
        runtime, _ = load_runtime(config)
        return None if runtime is None else runtime.circuit.get('netlist_sha256')

    @app.post('/api/agent/approve')
    def approve(body: ApproveBody):
        config = parse_config(body.config)
        try:
            return proposals.approve(body.proposal_id, proposal_hash=body.proposal_hash,
                                     config=config.model_dump(mode='json'), circuit_hash=_circuit_hash(config))
        except KeyError:
            fail(404, 'Unknown proposal')
        except ProposalRejected as exc:
            raise HTTPException(409, detail=dict(message=str(exc), problems=exc.problems))

    @app.post('/api/agent/apply')
    def apply(body: ApplyBody):
        config = parse_config(body.config)
        try:
            updated = proposals.apply(body.proposal_id, config=config.model_dump(mode='json'),
                                      circuit_hash=_circuit_hash(config))
        except KeyError:
            fail(404, 'Unknown proposal')
        except ProposalRejected as exc:
            raise HTTPException(409, detail=dict(message=str(exc), problems=exc.problems, configuration_unchanged=True))
        new_config = parse_config(updated)
        runtime, _ = load_runtime(new_config)
        report = validate(new_config, graph=None if runtime is None else runtime.base_graph,
                          provided_metrics=None if runtime is None else set(runtime.provided_metrics))
        return dict(config=updated, validation=report.as_dict(),
                    note='Configuration only. No circuit was written and no simulation was started.')

    @app.post('/api/agent/reject')
    def reject(body: dict):
        try:
            return proposals.reject(str(body.get('proposal_id')))
        except KeyError:
            fail(404, 'Unknown proposal')

    def _audit(proposal):
        from ..paths import local_settings_dir
        from ..storage.atomic import JsonlAppender
        try:
            log = JsonlAppender(local_settings_dir() / 'agent_audit.jsonl')
            log.append(dict(time_utc=utcnow().isoformat(), proposal_id=proposal['proposal_id'], provider=proposal['provider'],
                            origin=proposal['origin'], kind=proposal['kind'], audit=proposal['audit'],
                            note='Agent request audit only. Never an RL run id, checkpoint or simulation budget.'))
            log.close()
        except OSError:
            pass

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(status_code=500, content=dict(detail=dict(message=redact(f'{type(exc).__name__}: {exc}', 1000))))

    dist = repo_root() / 'frontend' / 'dist'
    if serve_frontend and dist.is_dir():
        app.mount('/', StaticFiles(directory=str(dist), html=True), name='frontend')
    return app
