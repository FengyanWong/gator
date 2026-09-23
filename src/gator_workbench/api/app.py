"""Local FastAPI backend of the GATOR workbench.

* Listens on 127.0.0.1 unless the operator says otherwise. No CORS: the UI is same-origin.
* There is no endpoint that accepts a command, a host, a port or an arbitrary path. Output paths
  must lie inside operator-allowed roots; netlists inside operator-allowed input roots; bridge
  access names a configured profile identifier only. Unknown request fields are rejected.
* Training/simulation run in detached worker processes, never inside a request.
* Errors returned to the browser are redacted.
"""
from __future__ import annotations

import asyncio
import io
import json
import mimetypes
import os
import secrets
from pathlib import Path
import threading
from urllib.parse import quote
import zipfile

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import (__version__, aggregates, agents, bridge_connect, bridge_read, checkpoints as ckpt, connection, runs, schema,
                tasks, units)
from .. import consistency, network_presets, profiles, recipes, task_files, virtuoso_setup, working_copy
from ..agents import AgentError, AgentRequest, AgentSettings, ProposalRejected, ProposalStore
from ..agents import catalog as agent_catalog
from ..agents import proposals as agent_proposals
from ..agents import readiness as agent_readiness
from ..agents import run_digest as agent_run_digest
from ..agents import settings_review as agent_review
from ..agents import diagnostics as agent_diagnostics
from ..agents import tools as agent_tool_catalog
from ..agents.prompts import circuit_summary
from .. import corner_check
from ..layout import RunLayout, environment_versions
from ..native_cells import load_import as load_cell_import       # `native_cells` is a route name in create_app
from ..paths import OutputRoots, PathNotAllowed, default_output_root, directory_bytes, repo_root, safe_child
from ..preload import preload
from ..security import redact
from ..storage.atomic import read_json, read_jsonl
from ..storage.dataset import DatasetReader, map_to_dict, utcnow
from ..storage.tables import TABLES, data_dictionary
from ..validation import validate


PROFILE_ID = r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$'        # a connection profile: an identifier, never a host, port or command
CADENCE_NAME = r'^[A-Za-z_][A-Za-z0-9_.\-]{0,127}$'      # a Virtuoso library or cell
TASK_NAME = r'^[a-z][a-z0-9_]{1,39}$'                  # a saved task: real:<name>


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


class CornerCheckBody(Body):
    run_dir: str
    designs: int = Field(corner_check.MAX_DESIGNS, ge=1, le=corner_check.MAX_DESIGNS)
    expected_designs: list[str] | None = None        # the evaluations the page showed: a plan that changed is refused
    simulations: int | None = Field(None, ge=1)      # the number the page showed (and a real check's user authorized)
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False


class CornerStopBody(Body):
    run_dir: str
    check_id: str = Field(pattern=corner_check.CHECK_ID.pattern)


class PathBody(Body):
    path: str
    create: bool = False


class ConnectionBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    scope: str = Field('interactive', pattern='^(cheap|interactive|full)$')
    trigger: str = Field('user', pattern='^(user|auto)$')      # auto = profile change in the UI: cheap layers only


class ConnectBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)      # an identifier: never a host, port or command


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


class PdkLoadBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    technology_library: str | None = Field(None, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$')   # empty = the connection's design library's
    model_file: str | None = Field(None, max_length=1000)                                        # empty = the connection's model file


class NativeReadBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    library: str | None = None
    cell: str | None = None
    testbench: str | None = None        # import only: the cell whose netlist is exported (the testbench around `cell`)
    work_here: bool = False             # import only: the user said this cell is a copy they made - the task flow works in it (working_copy.declare)


class CopyBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    library: str = Field(pattern=CADENCE_NAME)
    cell: str = Field(pattern=CADENCE_NAME)


class SetupBody(CopyBody):
    config: dict | None = None          # the editors' rows, to say how the copy's setup differs from them


class TaskSaveBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    name: str = Field(pattern=TASK_NAME)
    config: dict
    library: str | None = Field(None, pattern=CADENCE_NAME)
    cell: str | None = Field(None, pattern=CADENCE_NAME)
    task: str | None = Field(None, pattern=TASK_NAME)     # the open task: updated, or the source of Save as
    as_new: bool = False
    extras: dict | None = None          # what the task file holds beside the rows: analyses, variables, bindings, frequency, notes


class TaskFileBody(Body):
    config: dict
    library: str | None = Field(None, pattern=CADENCE_NAME)
    cell: str | None = Field(None, pattern=CADENCE_NAME)
    task: str | None = Field(None, pattern=TASK_NAME)
    extras: dict | None = None


class TaskFileTextBody(Body):
    text: str = Field(max_length=2_000_000)


class TaskCheckBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    config: dict


class ProfileActionBody(Body):
    name: str = Field(pattern=TASK_NAME)
    run_dir: str | None = None


class AgentSettingsBody(Body):
    provider: str
    model: str | None = None
    effort: str | None = None
    timeout_seconds: float | None = None      # IGNORED: a request has no time limit (7.48). Accepted because older pages send it
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


class DiffBody(Body):
    before: dict = {}
    after: dict = {}


class CancelBody(Body):
    request_id: str


class RejectBody(Body):
    proposal_id: str


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


def zip_download(members, name: str):
    """(file, name inside the archive) pairs as one zip download, built in memory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for item, inside in members:
            archive.write(item, inside)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/zip', headers=attachment(name))


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


KEEPALIVE_SECONDS = 10.0        # a live agent answer sends a comment line when it has nothing else: a page that left is noticed


def sse(kind: str, data) -> str:
    """One Server-Sent Event. json.dumps escapes every line break, so `data` is always a single line."""
    return f"event: {kind}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


def live_answer(request, provider, finish, done=None, outcome=None):
    """The agent's answer as Server-Sent Events (status record 7.48): `progress` while it works (agents/live.py), then ONE
    `result` (the proposal, exactly as the JSON answer) or ONE `error` (exactly as the 409 detail). The agent runs on a
    thread of its own. If the page goes away first, the request is cancelled: nobody would see the answer. `done` is
    called once the agent is finished, however it ended (the request's tools are closed with it). `outcome` says what the
    request's tools did, so a FAILURE can say it too - a failed request may already have written the working copy."""
    async def events():
        loop, inbox = asyncio.get_running_loop(), asyncio.Queue()

        def post(kind, data):
            try:
                loop.call_soon_threadsafe(inbox.put_nowait, (kind, data))
            except RuntimeError:                  # the event loop is gone: the server is stopping
                pass

        def work():
            try:
                post('result', finish(provider.propose(request, on_event=lambda event: post('progress', event))))
            except AgentError as exc:
                post('error', dict(exc.as_dict(), configuration_unchanged=True, **(outcome() if outcome else {})))
            except Exception as exc:              # the JSON answer would be an HTTP 500; a stream must still end with a verdict
                post('error', dict(code='internal_error', meaning='The workbench failed while handling the reply.',
                                   detail=redact(f'{type(exc).__name__}: {exc}', 1000), configuration_unchanged=True,
                                   **(outcome() if outcome else {})))
            finally:
                if done is not None:
                    done()
        threading.Thread(target=work, name=f'agent-{request.request_id[:8]}', daemon=True).start()
        finished = False
        try:
            while True:
                try:
                    kind, data = await asyncio.wait_for(inbox.get(), KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ': working\n\n'
                    continue
                yield sse(kind, data)
                if kind != 'progress':
                    finished = True
                    return
        finally:
            if not finished:
                agents.REGISTRY.cancel(request.request_id)
    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


def create_app(*, extra_output_roots=(), extra_input_roots=(), serve_frontend=True, monitor=None,
               auto_check_on_start=True, connection_stale_seconds=120.0, connector=None) -> FastAPI:
    # Endpoints run in a thread pool and import the optimizer lazily: two first imports at once corrupt
    # torch_geometric for the life of the process. Import it here, before any thread or request exists.
    preload()
    app = FastAPI(title='GATOR workbench', version=__version__, docs_url='/api/docs', openapi_url='/api/openapi.json')
    roots = OutputRoots(extra_output_roots)
    input_roots = [repo_root().resolve()] + [Path(p).expanduser().resolve() for p in extra_input_roots]
    proposals = ProposalStore()
    tool_sessions = {}                 # token -> the open tools of one agent request (agents/tools.py); empty between requests

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
        app.state.auto_check_thread = threading.Thread(target=auto_check, name='gator-connection-auto-check', daemon=True)
        app.state.auto_check_thread.start()

    # ------------------------------------------------------------------ helpers
    def fail(status, message, **extra):
        raise HTTPException(status, detail=dict(message=redact(str(message), 2000), **extra))

    def _bridge_call(action, *refusals):
        """A request that goes through the connection gate to Virtuoso. A blocked gate is a 409 carrying the gate; each
        (exception classes, code) of `refusals`, in order, a 409 with that code; a wrong name or value a 422; anything
        else a 502."""
        try:
            return action()
        except PermissionError as exc:
            raise HTTPException(409, detail=dict(message=str(exc), gate=getattr(exc, 'gate', None)))
        except Exception as exc:
            for kinds, code in refusals:
                if isinstance(exc, kinds):
                    fail(409, exc, code=code)
            fail(422 if isinstance(exc, (KeyError, ValueError)) else 502, exc)

    def parse_config(raw) -> schema.WorkbenchConfig:
        try:
            config = schema.WorkbenchConfig.model_validate(raw)
        except ValidationError as exc:
            fail(422, 'The configuration does not match the schema', errors=schema.describe_errors(exc))
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

    def validate_loaded(config, runtime):
        """Static validation against the loaded circuit, the SAME way for the page, the start checklist, the settings
        review and an applied proposal. A cell read from Virtuoso that has no task yet (a native draft) provides metrics
        nobody knows: they are not checked - an empty list reported every probe as `metric_not_provided` in the agent's
        checklist while the page showed none."""
        draft = runtime is not None and bool(runtime.circuit.get('native_draft'))
        return validate(config, graph=None if runtime is None else runtime.base_graph,
                        provided_metrics=None if runtime is None or draft else set(runtime.provided_metrics))

    def agent_settings() -> AgentSettings:
        saved = runs.load_settings().get('agent') or {}
        saved['provider'] = agents.default_provider_name(saved.get('provider'))
        saved['allowed_tools'] = tuple(saved.get('allowed_tools') or ())
        # The two CLIs take different effort levels. A level kept from the other provider (or a hand-edited file)
        # means "the CLI's default" rather than an error that would take the whole Agent tab down.
        if saved.get('effort') not in agent_catalog.efforts_for(saved['provider']):
            saved['effort'] = None
        # A request has no time limit (status record 7.48): the page shows it working and "Cancel request" stops it.
        # A limit kept in the file from before (300 s was the default) is ignored.
        saved.pop('timeout_seconds', None)
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

    # ------------------------------------------------------------------ PDK: the components the network knows
    @app.get('/api/pdks')
    def loaded_pdks():
        """The PDKs loaded so far (local files only). Each one can be the network's component list."""
        from .. import pdk
        return dict(pdks=pdk.list_pdks(), standard=dict(vocabulary=pdk.STANDARD, label=pdk.label(None),
                                                         kinds=list(pdk.standard_schema().device_kinds),
                                                         parameters=list(pdk.standard_schema().parameters)))

    @app.get('/api/pdks/{pdk_id}')
    def loaded_pdk(pdk_id: str):
        """Everything that was read about one loaded PDK: every component, its pins and roles, its parameters."""
        from .. import pdk
        record = pdk.load_record(pdk_id)
        if record is None:
            fail(404, f'PDK {pdk_id} is not loaded')
        return pdk.describe(record)

    @app.post('/api/pdks/load')
    def load_pdk(body: PdkLoadBody):
        """Explicit click: read one technology library's own description and its Spectre model files through the
        connection (read-only, no simulation), and store what the network needs. PDK files are not kept."""
        return _bridge_call(lambda: bridge_read.read(monitor, body.profile_id, 'pdk', library=body.technology_library or None,
                                                     model_file=body.model_file or None))          # a PdkError is a ValueError: 422

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
                      working_copy=working_copy.load(circuit.library, circuit.cell) if circuit.library and circuit.cell else None
                      ) if circuit.source == 'virtuoso' else {}
        if runtime is None:
            return dict(loaded=False, **blocked, **native)
        if circuit.source == 'virtuoso' and runtime.circuit.get('native_draft'):
            # What the testbench this copy was read through can measure: the rows the Probes tab follows.
            imported = load_cell_import(circuit.library, circuit.cell)
            native['testbench_probes'] = imported and profiles.testbench_probes(imported, graph=runtime.base_graph)
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
        can then be shown, edited against, validated and summarized for the agent. It cannot run: no profile.
        `work_here` (2026-09-23): the page asked whether the cell is a copy the user made and they said yes - the cell
        that was read becomes the task flow's working copy (working_copy.declare, no further contact with Virtuoso;
        the workbench makes no copy of its own any more); the answer then carries the record."""
        if body.work_here and not body.testbench:               # said before any export: the declaration would refuse anyway
            fail(409, 'Choose the cell\'s Testbench cell first: the task simulates the testbench and keeps its Maestro setup there.', code='refused')
        imported = _native(body, 'import_cell')
        if body.work_here:
            try:
                imported = dict(imported, working_copy=working_copy.declare(body.profile_id, body.library, body.cell))
            except working_copy.CopyError as exc:
                fail(409, exc, code='refused')
        return imported

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

    # ------------------------------------------------------------------ working copy + its Maestro setup
    COPY_REFUSED = ((working_copy.CopyError, virtuoso_setup.SetupError), 'refused')

    @app.post('/api/virtuoso/copy')
    def virtuoso_copy(body: CopyBody):
        """Refused since 2026-09-23 (user request): the workbench makes no copy of a cell any more. The user copies the
        cell and its testbench in Virtuoso and reads the copy (`/api/virtuoso/import` with `work_here`: the page asks
        whether it is a copy they made). `working_copy.make` stays for Save as through the API and for the tests."""
        fail(409, f'The workbench no longer makes copies of your cells ({body.library}/{body.cell} was not copied): copy the cell '
                  'and its testbench in Virtuoso yourself, then read the copy in the Virtuoso window - it asks whether the cell '
                  'is a copy you made and works in it.', code='copies_not_made')

    @app.post('/api/virtuoso/setup/read')
    def virtuoso_setup_read(body: SetupBody):
        """Explicit click: what the working copy's Maestro view holds (test, analyses, outputs, specs, variables and the
        instance parameters set to them) and the rows it stands for. With `config`: how the editors differ from it.
        Read-only, zero cost."""
        if not body.profile_id:
            fail(422, 'A connection profile is required')

        def read():
            found = working_copy.read_setup(monitor, body.profile_id, body.library, body.cell)
            if body.config is not None and found.get('test'):
                config = parse_config(body.config)
                ours = virtuoso_setup.from_rows(config, model_files=found['model_files'], analyses=found['analyses'],
                                                variables=found['variables'], bindings=found['bindings'],
                                                initial_conditions=found.get('initial_conditions'))
                found['editor_differences'] = virtuoso_setup.differences(ours, found)
            return found
        return _bridge_call(read, COPY_REFUSED)

    # ------------------------------------------------------------------ saved tasks: "Save task", "Save as", the task file
    @app.post('/api/virtuoso/task/save')
    def virtuoso_task_save(body: TaskSaveBody):
        """Explicit click - a person's only: store the editors' rows as the task real:<name>. The first save of a cell takes
        its working copy; on an open task, Save task updates it (next revision) and Save as (`as_new`) makes another task
        with a copy of its own. A Maestro-measured task writes its setup into its copy and reads it back first; then the
        copy is read into the workbench (read-only) and the task files are generated from it. Zero simulations."""
        if not body.profile_id:
            fail(422, 'A connection profile is required')
        config = parse_config(body.config)
        return _bridge_call(lambda: profiles.save_task(monitor, body.profile_id, body.name, config, library=body.library, cell=body.cell,
                                                       task=body.task, as_new=body.as_new, extras=body.extras,
                                                       run_rows=runs.list_runs(roots, include_mock=False)),
                            (profiles.NeedsFrequency, 'needs_expected_frequency'), ((profiles.ProfileError,), 'refused'), COPY_REFUSED)

    @app.post('/api/virtuoso/task/file')
    def virtuoso_task_file(body: TaskFileBody):
        """The task file of the CURRENT editors - what "Save task" would store - as text, laid out with its own
        explanations. Local files only: nothing is read from Virtuoso."""
        config = parse_config(body.config)
        entry = profiles.list_profiles().get(body.task) if body.task else None
        saved = profiles.task_file(body.task) if entry else None
        if entry:
            cell, copy = entry.get('original'), entry.get('copy')
            state_dir = (entry.get('copy_target') or {}).get('state_dir')      # None: a task made before working copies
            name = body.task
        else:
            record = working_copy.load(body.library, body.cell) if body.library and body.cell else None
            cell = (record or {}).get('original') or (dict(library=body.library, cell=body.cell, testbench=config.circuit.testbench_cell)
                                                        if body.library and body.cell else None)
            copy = (record or {}).get('copy')
            state_dir = working_copy.record_dir(body.library, body.cell) if record else None
            name = (body.cell or 'task').lower()
        setup = working_copy.last_written(dict(state_dir=state_dir)) if state_dir else None
        data = task_files.draft(config, name=name, cell=cell, copy=copy, saved=saved, extras=body.extras,
                                setup=dict(setup, test='GATOR') if setup else None)
        return dict(text=task_files.render(data), name=name, revision=(saved or {}).get('revision', 0), saved=saved is not None)

    @app.post('/api/virtuoso/task/check')
    def virtuoso_task_check(body: TaskCheckBody):
        """Explicit click ("Check now"): the check Start runs by itself before every run of a saved task - the editors
        against the task file, the task against its working copy in Virtuoso (the run adapter connects and exports, the
        deck is written, nothing is simulated), and a Maestro-measured task's Maestro test. Read-only; every step says
        what it found, a blocked gate included."""
        config = parse_config(body.config)
        try:
            return consistency.check(monitor, body.profile_id, config)
        except KeyError as exc:
            fail(409, exc.args[0] if exc.args else exc, code='not_a_saved_task')

    @app.post('/api/virtuoso/task/file/check')
    def virtuoso_task_file_check(body: TaskFileTextBody):
        """Read a task file someone edited: its rows (checked with the editors' schema), what it holds beside them, and
        every problem in plain words. Nothing is saved."""
        rows, extras, problems = task_files.parse(body.text)
        return dict(rows=rows, extras=extras, problems=problems, ok=not problems)

    def _native(body, op):
        return _bridge_call(lambda: bridge_read.read(monitor, body.profile_id, op, library=body.library, cell=body.cell,
                                                     testbench=body.testbench if op == 'import_cell' else None))

    # ------------------------------------------------------------------ configuration
    @app.post('/api/config/validate')
    def config_validate(body: ConfigBody):
        config = parse_config(body.config)
        runtime, blocked = load_runtime(config)
        report = validate_loaded(config, runtime)
        if runtime is not None and runtime.circuit.get('native_draft'):          # it must never look startable
            report.add('blocker', 'circuit_profile_missing', 'circuit', tasks.NATIVE_DRAFT_NOT_EXECUTABLE)
        return dict(report.as_dict(), config_hash=schema.config_hash(config),
                    task_definition_hash=schema.task_definition_hash(config), circuit_blocker=blocked,
                    mock=None if runtime is None else runtime.mock)

    @app.post('/api/config/diff')
    def config_diff(body: DiffBody):
        from ..agents.proposals import structured_diff
        return dict(diff=structured_diff(body.before, body.after))

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
    def connection_status(profile_id: str = Query(pattern=PROFILE_ID)):
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
        from .. import pdk
        own = pdk.run_vocabulary(run_dir)                  # the model's component list: the page's list follows it
        result['vocabulary'] = dict(name=own.name if own else pdk.STANDARD, label=own.label if own else pdk.label(None),
                                    pdk_id=own.pdk_id if own else None, sha256=own.sha256 if own else None,
                                    loaded=bool(own is None or pdk.load_record(own.pdk_id) is not None))
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
                    try:
                        vocabulary = runs._vocabulary_for(config, run_dir)      # what a run of this page would use
                    except runs.RunRejected as exc:
                        result['compatibility_unchecked'] = dict(
                            title='The component list of this configuration is not available',
                            what=str(exc), note='Load that PDK with "Load PDK..." in the RL network block, or choose the '
                            'standard list. The saved model itself is fine.', technical=f'{exc.code}: {exc}')
                    else:
                        contract = modes.current_contract(learner_experiment(config, runtime, task_hash),
                                                          modes.model_config_from(config.run.network),
                                                          modes.sac_config_from(config.run.advanced), compiled.spec_schema,
                                                          vocabulary)
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

    # ------------------------------------------------------------------ corner check: a run's best designs at 5 corners
    @app.get('/api/runs/corner-check/plan')
    def corner_check_plan(run_dir: str, designs: int = Query(corner_check.MAX_DESIGNS, ge=1, le=corner_check.MAX_DESIGNS)):
        """Which designs a check would simulate at which corners, and how many simulations that is. Free: local files."""
        return corner_check.plan(run_path(run_dir), designs=designs)

    @app.post('/api/runs/corner-check/start')
    def corner_check_start(body: CornerCheckBody):
        """A real circuit needs authorize_real_simulation (and the connection gate); nothing is created before both."""
        run_dir = run_path(body.run_dir)
        try:
            directory = corner_check.prepare(run_dir, designs=body.designs, expected=body.expected_designs,
                                             simulations=body.simulations, allow_real=body.authorize_real_simulation,
                                             acknowledge_unknown=body.acknowledge_unknown_connection, monitor=monitor)
        except (corner_check.CheckRefused, runs.RunRejected) as exc:
            raise HTTPException(409, detail=dict(message=redact(str(exc), 2000), code=exc.code, report=exc.report))
        request = read_json(directory / 'request.json')
        pid = corner_check.launch(directory, allow_real=body.authorize_real_simulation and not request['mock'])
        return dict(check_id=request['check_id'], worker_pid=pid, simulations=request['simulations'], mock=request['mock'])

    @app.get('/api/runs/corner-check/status')
    def corner_check_status(run_dir: str, check_id: str):
        try:
            return corner_check.check_status(run_path(run_dir), check_id)
        except corner_check.CheckRefused as exc:
            fail(400, exc)
        except FileNotFoundError:
            fail(404, 'This run has no corner check with that identifier.')

    @app.post('/api/runs/corner-check/stop')
    def corner_check_stop(body: CornerStopBody):
        """The simulation in flight ends, then the cell is restored; nothing is killed."""
        try:
            return corner_check.request_stop(run_path(body.run_dir), body.check_id)
        except corner_check.CheckRefused as exc:
            raise HTTPException(409, detail=dict(message=redact(str(exc), 2000), code=exc.code))
        except FileNotFoundError:
            fail(404, 'This run has no corner check with that identifier.')

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
        # Only the rows shown are read from disk and turned into Python: `tail` walks the parts from the newest backwards
        # (it read every part of the run, then kept 20).
        part = reader.tail(table, limit) if tail else reader.table(table).slice(0, limit)
        rows = part.to_pylist()
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
        members = ((item, item.relative_to(path).as_posix()) for item in sorted(p for p in path.rglob('*') if p.is_file()))
        return zip_download([(item, relative) for item, relative in members if relative.split('/')[0] not in
                             ('work', 'control', 'waveforms', 'checkpoints') and '/_quarantine/' not in relative],
                            f'{path.name}__data.zip')

    @app.post('/api/aggregates/export')
    def export_aggregates(body: ExportBody):
        run_dir = run_path(body.run_dir)
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
        return zip_download([(item, item.name) for item in members], f'{experiment.name}__aggregates.zip')

    # ------------------------------------------------------------------ agent assistance
    @app.get('/api/agent/diagnostics')
    def diagnostics():
        return dict(agent_diagnostics.diagnose(), availability=agents.availability(), selected=agent_settings().provider)

    @app.get('/api/agent/settings')
    def get_agent_settings():
        settings = agent_settings()
        return dict(vars(settings), allowed_tools=list(settings.allowed_tools), availability=agents.availability(),
                    catalog=agent_catalog.for_api(),        # static table + one local file read: no CLI, no model call
                    note='Agent model, effort and tools are independent of RL checkpoints, simulator '
                         'concurrency and evaluation budgets. A request has no time limit; "Cancel request" stops it.')

    @app.put('/api/agent/settings')
    def put_agent_settings(body: AgentSettingsBody):
        try:
            settings = AgentSettings(**dict(body.model_dump(exclude={'timeout_seconds'}), allowed_tools=tuple(body.allowed_tools))).validate()
            agents.make_provider(settings)
        except AgentError as exc:
            raise HTTPException(422, detail=exc.as_dict())
        saved = dict(vars(settings), allowed_tools=list(settings.allowed_tools))
        saved.pop('timeout_seconds')
        runs.save_settings(agent=saved)
        return dict(saved=True, provider=settings.provider)

    def run_readiness(config, runtime, blocked) -> dict:
        """The start checklist. Free: static validation, the output-root check and the monitor's CACHED connection
        status - no bridge contact, no simulator, no agent. A fresh connection test stays the user's button."""
        report = validate_loaded(config, runtime).as_dict()
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
            report = validate_loaded(parsed, runtime)
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
            # A real backend produces a fixed set of results per circuit type, and writes what the property form lets a user
            # type. Said to the agent, so its measurement rows name results that exist and its variables can be written.
            if runtime.circuit.get('native_draft'):
                summary['results_by_circuit_type'] = {key: list(recipes.provided_metrics(key)) for key in profiles.RECIPES}
                summary['real_backend_limits'] = (
                    'This cell has no circuit profile yet. When one is created from your proposal: a measurement with '
                    'result_source "backend_profile" must use a source_name from results_by_circuit_type for the fitting circuit '
                    'type; a parameter can be optimized when the property form of its instance (directly inside the core cell) '
                    'lets a user type it - transistor w, l, nf, m, a MIM capacitor\'s w, l, m, ... (a form that greys a field out '
                    'or computes it, e.g. areas, refuses it) - lengths on a 5 nm grid, counts in whole numbers, and a range that '
                    'contains the present value; a transistor varies its total width or its finger count, not both. Identical or '
                    'matched parts should follow one leader through binding_group with ratio 1. A target\'s metric_id must be '
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
        copy = None
        if body.kind in ('virtuoso_setup', 'virtuoso_work'):
            # The working copy the setup is for, given as DATA: its names, what the workbench last wrote into its Maestro
            # test, which values may be variables, and the only calculator functions an output may call. A `virtuoso_work`
            # request can read all of this again through its tools; it is here so the first turn already knows it.
            try:
                target = _setup_target(config)
            except working_copy.CopyError as exc:
                raise AgentError('invalid_request', str(exc))
            own = working_copy.is_declared(target)          # the user's own copy, declared on the read: written directly
            copy = dict(copy=target['copy'], cell_you_drew=None if own else target['original'], own_copy=own, test=virtuoso_setup.TEST,
                        maestro_now=working_copy.last_written(target) or 'nothing written by the workbench yet',
                        bindable=[dict(cell=c, instance=i, parameters=sorted(p)) for (c, i), p in sorted(working_copy.bindable_on(target).items())],
                        allowed_functions=sorted(virtuoso_setup.FUNCTIONS),
                        model_files=working_copy.default_model_files(config.run.connection_profile_id),
                        note=('This is the cell the user declared as a copy they made; the workbench writes into it directly. ' if own else '')
                             + 'The circuit data is read from the copy\'s cell; instance paths and nets are the same in the copy.')
        request = AgentRequest(kind=body.kind, user_prompt=body.prompt, config=config.model_dump(mode='json'),
                               circuit_summary=summary, selection=body.selection, readiness=ready, review=review, results=results,
                               web=bool(body.web), web_domains=agent_review.domains(runs.load_settings().get('agent_web_domains')),
                               copy=copy)
        if body.request_id:
            request.request_id = body.request_id
        return request, circuit_hash

    @app.post('/api/agent/propose')
    def propose(body: ProposeBody, http: Request):
        """Proposal only. Applying needs approval; circuit writes and simulations need their own authorization.
        A request that accepts `text/event-stream` gets the answer LIVE (`live_answer`), any other gets it in one piece.
        A request of a TOOL kind (agents/tools.py) also gets the workbench's Virtuoso tools for as long as it runs."""
        session = None
        try:
            request, circuit_hash = _request(body)
            provider = agents.make_provider(agent_settings())
            # Validated BEFORE the tools are opened: a request that cannot be sent used to leave the live-answer path with
            # an open tool session (its token still worked), because only the plain path had the `finally` that closes it.
            request.validate()
            if request.kind in agents.TOOL_KINDS and not getattr(provider, 'carries_tools', False):
                fail(409, f'The {settings_provider_name(provider)} provider cannot be given the workbench\'s Virtuoso tools, '
                          f'so a "{request.kind}" request would work without them and say it has them. Choose the Claude Code '
                          'provider under Agent settings, or a request kind that needs no tools.', code='tools_unsupported')
            session = _open_tools(request, parse_config(body.config), http)

            def finish(result):
                proposal = _proposal(request, result, circuit_hash, session)
                _audit(proposal)
                return proposal

            def done():
                if session is not None:
                    _close_tools(session)
            if 'text/event-stream' in http.headers.get('accept', ''):
                return live_answer(request, provider, finish, done=done, outcome=lambda: _tool_outcome(session))
            try:
                return finish(provider.propose(request))
            finally:
                done()
        except AgentError as exc:
            # A request that FAILS may already have written the working copy through its tools. Saying only
            # "configuration_unchanged" read as "nothing happened" (review of 2026-09-23): the tables are unchanged, the
            # copy in Virtuoso is not, and the answer now says which tools ran and whether one of them wrote.
            raise HTTPException(409, detail=dict(exc.as_dict(), configuration_unchanged=True, **_tool_outcome(session)))

    def _proposal(request, result, circuit_hash, session=None):
        """A reply - the agent's, or one imported by hand (no tools, so no `tool_calls`) - as a proposal: a Virtuoso setup
        checked for writability, what its tools did, whether the run would start after it, its suggestions tried."""
        proposal = proposals.create(request, result, circuit_hash=circuit_hash)
        if request.kind == 'virtuoso_setup':
            check_setup(request, proposal)
        proposal.update(_tool_outcome(session))
        proposal['readiness_after'] = readiness_after(request, proposal)
        check_suggestions(request, proposal)
        return proposal

    # ------------------------------------------------------------------ the agent's own tools (status record 7.68)
    def _open_tools(request, config, http):
        """Open this request's tools, if its kind has any. The session holds what the agent may not choose: the working
        copy (resolved from the configuration, never from a tool argument), the connection it goes through, and how many
        calls are left. It is closed when the request ends, and its token stops working with it."""
        names = agent_tool_catalog.granted(request.kind)
        if not names:
            return None
        profile_id = config.run.connection_profile_id
        session = agent_tool_catalog.ToolSession(
            request_id=request.request_id, token=secrets.token_urlsafe(32), kind=request.kind, monitor=monitor,
            profile_id=profile_id, names=tuple(names), on_call=_tool_record,
            target=lambda: _setup_target(config),
            read=lambda op, **wanted: bridge_read.read(monitor, profile_id, op, **wanted))
        tool_sessions[session.token] = session
        request.tools = tuple(names)
        request.tools_url = str(http.base_url).rstrip('/')
        request.tools_token = session.token
        return session

    def _close_tools(session):
        session.close()
        tool_sessions.pop(session.token, None)

    def _tool_outcome(session) -> dict:
        """What this request's tools did - said with the answer AND with a failure, because a request that ends badly may
        already have written the working copy."""
        if session is None:
            return {}
        return dict(tool_calls=[dict(tool=c['tool'], ok=c['ok'], error=c['error']) for c in session.history],
                    virtuoso_copy_written=session.wrote)

    def settings_provider_name(provider) -> str:
        return getattr(provider, 'name', None) or type(provider).__name__

    def _log_line(file, note, /, **entry):          # positional-only: an entry may carry any key
        """One line of a local agent log. A log that cannot be written never fails the request or its tool call."""
        from ..paths import local_settings_dir
        from ..storage.atomic import JsonlAppender
        try:
            log = JsonlAppender(local_settings_dir() / file)
            log.append(dict(time_utc=utcnow().isoformat(), **entry, note=note))
            log.close()
        except OSError:
            pass

    def _tool_record(entry):
        _log_line('agent_tool_calls.jsonl', "One workbench tool call of an agent request: a read, or a Maestro setup written "
                                            "into a working copy. Never the user's own cell, never a simulation.", **entry)

    @app.post('/api/agent/tools')
    def agent_tools(body: dict):
        """Where the tool server of ONE running request (gator_workbench/agent_tools.py) asks. The token says which
        request it belongs to; a request that has ended has no tools, and nothing else is accepted."""
        session = tool_sessions.get(str(body.get('token') or ''))
        if session is None or session.closed:
            raise HTTPException(403, detail='These tools are closed: the agent request they belong to is over.')
        if body.get('method') == 'list':
            return dict(tools=agent_tool_catalog.described(session.names))
        if body.get('method') != 'call':
            raise HTTPException(422, detail=f'Unknown tool method {body.get("method")!r}')
        return session.call(str(body.get('name') or ''), body.get('arguments') or {})

    def _setup_target(config):
        """The working copy a Virtuoso setup is about: the cell's own copy (Circuit source: Virtuoso) or an open task's copy."""
        circuit = config.circuit
        if circuit.source == 'virtuoso' and circuit.library and circuit.cell:
            return working_copy.draft_target(circuit.library, circuit.cell)
        if circuit.source == 'registered_task' and (circuit.task_id or '').startswith('real:'):
            entry = profiles.list_profiles().get(circuit.task_id[len('real:'):])
            if entry and entry.get('copy_target'):
                return entry['copy_target']
        raise working_copy.CopyError('Setting up in Virtuoso needs the cell the task flow works in: read the cell into the workbench '
                                     'and confirm that it is a copy you made (the Virtuoso window asks); a task saved with Save task has one')

    def _setup_of(config, proposal):
        setup = proposal.get('setup') or {}
        return virtuoso_setup.from_rows(config, analyses=setup.get('analyses'), variables=setup.get('variables'),
                                        bindings=setup.get('bindings'), initial_conditions=setup.get('initial_conditions'))

    def check_setup(request, proposal):
        """A proposed Virtuoso setup must be writable as it stands: only allowed calculator functions, variables only on
        values nothing is computed from, every output with the analysis it reads. Otherwise the proposal is refused here -
        before anyone can approve it - with the reasons."""
        preview = schema.WorkbenchConfig.model_validate(agent_proposals.apply_patch(request.config, proposal['patch']))
        target = _setup_target(preview)
        wanted = _setup_of(preview, proposal)
        problems = virtuoso_setup.validate(wanted, bindable=working_copy.bindable_on(target))
        if wanted['analyses'] is not None:
            read = {m.analysis for m in preview.measurements if m.result_source == 'ade_output' and m.analysis != 'other'}
            missing = sorted(read - set(wanted['analyses']))
            if missing:
                problems.append(f'Outputs read the analyses {", ".join(missing)}, which setup.analyses does not set')
        if problems:
            proposals.reject(proposal['proposal_id'])
            raise AgentError('schema_failure', 'The proposed Virtuoso setup was refused by the backend: ' + '; '.join(problems)[:3000],
                             problems=problems)
        proposal['virtuoso_copy'] = target['copy']

    @app.post('/api/agent/readiness')
    def readiness(body: ConfigBody):
        """What is still missing before this run can start. Computed here: no agent is called and nothing is probed."""
        config = parse_config(body.config)
        runtime, blocked = load_runtime(config)
        return run_readiness(config, runtime, blocked)

    @app.post('/api/agent/cancel')
    def cancel(body: CancelBody):
        return dict(cancelled=agents.REGISTRY.cancel(body.request_id))

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
            return _proposal(request, agents.DisabledProvider().import_result(request, body.result), circuit_hash)
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
        report = validate_loaded(new_config, runtime)
        proposal = proposals.get(body.proposal_id)
        if proposal['kind'] != 'virtuoso_setup':
            return dict(config=updated, validation=report.as_dict(),
                        note='Configuration only. No circuit was written and no simulation was started.')
        # The approved setup goes into the WORKING COPY - never the user's cell - and is read back. The rows are applied
        # either way; if Virtuoso cannot be reached, Save task does the rest later (the page keeps the approved setup for
        # it - the separate "Write to Virtuoso" button went on 2026-09-22).
        virtuoso, profile_id = None, new_config.run.connection_profile_id
        try:
            if not profile_id:
                raise working_copy.CopyError('No connection is chosen: choose one in the Connection window')
            target = _setup_target(new_config)
            written = working_copy.write_setup_on(monitor, profile_id, target, _setup_of(new_config, proposal))
            virtuoso = dict(written=True, matches=written['matches'], differences=written['differences'], copy=target['copy'])
        except PermissionError as exc:
            virtuoso = dict(written=False, error=str(exc), gate=getattr(exc, 'gate', None))
        except (working_copy.CopyError, virtuoso_setup.SetupError) as exc:
            virtuoso = dict(written=False, error=str(exc))
        except Exception as exc:
            virtuoso = dict(written=False, error=redact(f'{type(exc).__name__}: {exc}', 600))
        if virtuoso['written']:
            note = (f"The rows were applied and the setup was written into the working copy {target['copy']['library']}/"
                    f"{target['copy']['testbench']} (not your cell), then read back: "
                    + ('it matches.' if virtuoso['matches'] else 'it differs - see the differences.') + ' No simulation was started.')
        else:
            note = (f"The rows were applied; writing into the working copy failed: {virtuoso['error']} Once Virtuoso can be reached, "
                    "press Save task: it writes the rows and the approved setup into the copy.")
        return dict(config=updated, validation=report.as_dict(), virtuoso=virtuoso, note=note)

    @app.post('/api/agent/reject')
    def reject(body: RejectBody):
        try:
            return proposals.reject(body.proposal_id)
        except KeyError:
            fail(404, 'Unknown proposal')

    def _audit(proposal):
        _log_line('agent_audit.jsonl', 'Agent request audit only. Never an RL run id, checkpoint or simulation budget.',
                  **{key: proposal[key] for key in ('proposal_id', 'provider', 'origin', 'kind', 'audit')})

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(status_code=500, content=dict(detail=dict(message=redact(f'{type(exc).__name__}: {exc}', 1000))))

    dist = repo_root() / 'frontend' / 'dist'
    if serve_frontend and dist.is_dir():
        app.mount('/', StaticFiles(directory=str(dist), html=True), name='frontend')
    return app
