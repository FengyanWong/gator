"""Run control, saved models and data-only exports."""
from __future__ import annotations
import mimetypes
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from .. import (aggregates, calibration, checkpoints as ckpt, connection, corner_check, graph_view, launch_requests,
                model_structure, runs, schema, session_routing, training_series)
from ..compile import CompileError
from ..layout import RunLayout
from ..paths import PathNotAllowed, safe_child
from ..storage.atomic import read_json, read_jsonl_tail, write_json
from ..storage.dataset import DatasetReader, utcnow
from ..storage.tables import TABLES
from ..vocabulary import run_vocabulary_facts
from .context import ApiContext
from .models import (CommandBody, ContinueBody, CornerCheckBody, CornerStopBody, ExportBody, GraphViewBody,
                     ModelStructureBody, RenameModelBody, StartBody)
from .support import attachment, compatibility_unchecked, fail, file_snapshot, package_files, run_files, zip_download


# /api/runs/model took any dict: {}, a numeric checkpoint_id or a list as run_dir failed with HTTP 500 (review of 2026-09-29).
class ModelBody(ModelStructureBody):
    """A saved model and, optionally, the page's configuration to compare it with."""
    config: dict | None = None



def start_run(context, config, body, *, baseline_only: bool=False, record=None, session=None) -> dict:
    """`session`: a Virtuoso session chosen for this run already (Save task hands its own to the baseline it starts,
    record 7.351) - no second choice; this start lets it go, or hands it to its worker, as it would its own choice."""
    config, allow_real, random_only, calibrating = _configure_start(config, body, baseline_only)
    # A connection with two Virtuoso sessions: the run goes to whichever is free (record 7.351, session_routing). A busy
    # session that holds the task's cell lets go of it once prepare_run's refusals have passed (`before_write`).
    config, session = _select_start_session(config, session, allow_real, context)
    layout, manifest, made = _prepare_start_directory(
        config, context, allow_real, body, session, baseline_only, random_only, calibrating, record)
    pid = _launch_start_worker(layout, allow_real, manifest, session)
    return dict(made, worker_pid=pid)


def _configure_start(config, body, baseline_only) -> tuple:
    """Validate calibration options and copy the configuration for a baseline or calibration run."""
    allow_real = bool(body.authorize_real_simulation)
    designs, calibrating = getattr(body, 'calibration_designs', 0), None
    random_only = getattr(body, 'calibration_only', False)
    if random_only and (baseline_only or not designs):
        fail(400, 'Calibration needs random designs and cannot also request a baseline.')
    if designs and not (baseline_only or random_only):
        fail(400, 'Calibration designs belong to the Baseline simulation (baseline_only), or Calibration (calibration_only), not to an optimization run.')
    if baseline_only or random_only:
        config = config.model_copy(deep=True)
        config.run.mode, config.run.max_evaluations = 'scratch', 1         # exactly ONE costed evaluation
        config.output.save_checkpoints = False
        config.project.task_name = f'{config.project.task_name}.{"calibration" if random_only else "baseline"}'
        config.run.rehearsal = None
        if designs:                                # ... and then the random designs of the calibration (record 7.197)
            calibrating = calibration.prepare(config, designs, random_only=random_only)
    return config, allow_real, random_only, calibrating


def _select_start_session(config, session, allow_real, context) -> tuple:
    """Attach the supplied session or choose an available session for a real run."""
    if session is not None:
        config = session_routing.with_session(config, session)
    elif allow_real:
        try:
            config, session = session_routing.route(config, context.monitor)
        except session_routing.SessionsBusy as exc:
            fail(409, exc, code=exc.code, report=exc.report)
    return config, session


def _prepare_start_directory(config, context, allow_real, body, session, baseline_only, random_only, calibrating, record) -> tuple:
    """Prepare the run directory and persist its launch records, releasing the session when either step fails."""
    try:
        layout, manifest = runs.prepare_run(config, context.roots, allow_real=allow_real,
                                            confirm_transfer=getattr(body, 'confirm_transfer', False), monitor=context.monitor,
                                            acknowledge_unknown=body.acknowledge_unknown_connection,
                                            remember_concurrency=not getattr(body, 'automatic_baseline', False),
                                            before_write=lambda: session_routing.release_pending(session, context.monitor))
    except session_routing.SessionsBusy as exc:
        session_routing.finished(session)
        fail(409, exc, code=exc.code, report=exc.report)
    except runs.RunRejected as exc:
        session_routing.finished(session)
        fail(409, exc, code=exc.code, report=exc.report)
    except PathNotAllowed as exc:
        session_routing.finished(session)
        fail(403, exc)
    except BaseException:
        session_routing.finished(session)
        raise
    try:
        if session is not None:                    # which session, and why, in the run's record (its current segment)
            manifest['segments'][-1]['virtuoso_session'] = session.record()
            manifest['notes'].append(session.said)
        if baseline_only or random_only:
            manifest['run_kind'] = 'calibration' if random_only else 'baseline_preflight'
            manifest['notes'].append('Calibration: random designs only; no starting-design evaluation.' if random_only else
                                     'Baseline simulation: a costed preflight evaluation, not a free check.')
            if calibrating:
                manifest['calibration'] = calibrating
                manifest['notes'].append((f'Calibration: {calibrating["designs"]} random designs over the ' if random_only else
                                          f'With calibration: after the baseline, {calibrating["designs"]} random designs over the ') +
                                         'Parameters ranges (each of them a costed evaluation; nothing is learned from them).')
        if session is not None or baseline_only or random_only:
            write_json(layout.manifest, manifest)  # one write for both (the manifest is on the D: drive)
        made = dict(run_dir=str(layout.run_dir), run_id=manifest['run_id'], mock=manifest['mock'], worker_pid=None,
                    paths=layout.subpaths(), connection_gate=manifest.get('connection_gate'),
                    mock_notice=manifest['mock_notice'], connection_profile_id=config.run.connection_profile_id,
                    virtuoso_session=session.record() if session is not None else None)
        if record is not None:
            record(made)                     # the request's answer is on disk BEFORE the worker exists (see `once`)
    except BaseException:
        # Nothing runs: the session goes back, and so does the lock prepare_run took for a continue's worker - held on,
        # every later continue of this run was refused as already_running until the backend restarted (review of
        # 2026-10-07, follow-up 1; since record 7.351 a manifest write that fails here lets them go as well).
        session_routing.finished(session)
        held = runs.take_lock(layout.run_dir)
        if held is not None:
            held.release()
        raise
    return layout, manifest, made




def _launch_start_worker(layout, allow_real, manifest, session):
    """Launch the worker, release its session on launch failure, and record a successful start."""
    try:
        pid = runs.launch_worker(layout, allow_real=allow_real and not manifest['mock'])
    except BaseException:
        session_routing.finished(session)
        raise
    session_routing.started(session, pid)    # reserved until the worker holds the session's lock, or has ended
    return pid


def worker_started(answer, at) -> bool:
    """Whether the run a launching record (written at `at`) names has its worker (launch_requests: the `started` test)."""
    return bool(answer.get('run_dir')) and runs.worker_started(answer['run_dir'], since=at)


def once(request_id, kind, work):
    """A launch answered once (record 7.261): `work(record)` makes the run; the same request id again gets the answer the
    first request got instead of a second run, and a request still on its way is refused (409 request_pending). `work`
    calls `record(answer)` as soon as the run exists and BEFORE its worker is started - a "launching" record, the answer
    once the worker is there (`worker_started`), on its way until then, nothing once stale (record 7.271) - so the answer
    is on disk whatever happens next: written only after the spawn, a write that failed left the request "pending",
    then "unknown" a quarter of an hour later, and the same id made a second run (review of 2026-10-07); written as
    "done" before the spawn, a backend that died in between answered the repeat with a run that never started. A refusal,
    or a failure before the worker exists (the worker is started last, and nothing after it raises), leaves no record: the
    page's repeat with the answers to the backend's questions is a request of its own."""
    if not request_id:
        return work(lambda answer: None)
    try:
        done = launch_requests.claim(request_id, kind, started=worker_started)
    except launch_requests.RequestPending as exc:
        fail(409, exc, code='request_pending')
    if done is not None:
        return dict(done, repeated=True)
    try:
        result = work(lambda answer: launch_requests.prepared(request_id, answer))
    except BaseException:
        launch_requests.drop(request_id)
        raise
    launch_requests.answer(request_id, result)          # the same answer, with the worker's pid now
    return result


def register(app: FastAPI, context: ApiContext) -> None:
    """The run routes, registered in this order: the order of registration is the order of matching."""
    _run_list_and_model_routes(app, context)
    _launch_and_control_routes(app, context)
    _corner_check_routes(app, context)
    _run_data_routes(app, context)
    _export_routes(app, context)


def _run_list_and_model_routes(app: FastAPI, context: ApiContext) -> None:
    """The run list and the saved models: describe, default, rename, list, structure, graph view."""
    _register_run_list_route(app, context)

    _register_model_description_route(app, context)

    _register_default_model_route(app, context)

    _register_model_rename_route(app, context)

    _register_saved_models_route(app, context)

    _register_model_structure_route(app, context)

    _register_model_graph_view_route(app, context)


def _register_run_list_route(app, context) -> None:
    """Register the run-list endpoint with its existing refresh and output-root choices."""
    @app.get('/api/runs')
    def get_runs(output_root: str | None = None, include_mock: bool = True, fresh: bool = False):
        """`fresh`: every run folder read again, past the run list's cache (the page's Refresh list; record 7.274)."""
        try:
            return dict(runs=runs.list_runs(context.roots, output_root, include_mock=include_mock, fresh=fresh))
        except PathNotAllowed as exc:
            fail(403, exc)


def _register_model_description_route(app, context) -> None:
    """Register saved-model facts and compatibility with the current configuration."""
    @app.post('/api/runs/model')
    def describe_model(body: ModelBody):
        """The selected RL model: source task, save time, schema, counters, actual path, restorable
        components and compatibility with the CURRENT configuration. Independent of the agent model."""
        run_dir = context.run_path(body.run_dir)
        try:
            description = ckpt.describe(run_dir, body.checkpoint_id or 'latest')
        except FileNotFoundError as exc:
            fail(404, exc)
        except runs.RunRejected as exc:
            fail(409, exc, code=exc.code)
        result = dict(description=description)
        # the model's component list: the page's list follows it
        result['vocabulary'] = run_vocabulary_facts(run_dir, (description.get('contract') or {}).get('feature_schema'))
        if body.config:
            config, runtime, blocked = context.load_config(body.config)
            if runtime is not None:
                config = runs.with_circuit_content(config, runtime)
                try:
                    result['compatibility'] = runs.model_compatibility(config, runtime, run_dir, description['path'])
                except CompileError as exc:
                    # The configuration ON THE PAGE is not complete yet. That is no fault of the saved model: its
                    # facts are still returned, and the page says in plain words what is missing (it used to be a
                    # 500 "CompileError: mp1_w: bounds are required" that hid the model as well).
                    result['compatibility_unchecked'] = compatibility_unchecked(exc)
                except runs.RunRejected as exc:
                    result['compatibility_unchecked'] = dict(
                        title='The component list of this configuration is not available',
                        what=str(exc), note='Read that PDK in the Virtuoso window ("PDK window..." reads one by name), or choose the '
                        'standard list. The saved model itself is fine.', technical=f'{exc.code}: {exc}')
                result['suggestion'] = runs.suggest_mode(config, run_dir, task=runtime)   # the task loaded above, not a second load
        return result


def _register_default_model_route(app, context) -> None:
    """Register lookup of the newest saved model under a model or legacy project label."""
    @app.get('/api/runs/default-model')
    def default_model(label: str | None = None, project: str | None = None):
        """Default = the newest model saved under this RL model label (record 7.159), and that run's `latest`, not
        `best`. `project`: the project name runs were remembered under before the label, asked when the label has none."""
        return runs.default_model(context.roots, label, project)


def _register_model_rename_route(app, context) -> None:
    """Register saved-model label changes and name-conflict responses."""
    @app.post('/api/runs/model/rename')
    def rename_model(body: RenameModelBody):
        """Gives a saved model a new name (record 7.225; user: "add a functionality of rename saved model"). Kept in the
        run folder's model_label.json - the manifest keeps the name the run was given at its start, and the engine
        never rewrites that file, so a live run can be renamed too. A name another model under the same output root
        carries is refused (409 name_taken): the user chose it, nothing is numbered here."""
        run_dir = context.run_path(body.run_dir)
        rows = runs.model_label_rows(runs.output_root_of(run_dir))
        names = ckpt.unique_model_labels(rows)
        taken = {name for directory, name in names.items() if directory != str(run_dir)}
        try:
            record = ckpt.rename_model(run_dir, body.model_label, taken=taken)
        except ckpt.ModelNameTaken as exc:
            fail(409, exc, code='name_taken')
        except ValueError as exc:
            fail(422, exc)
        return dict(run_dir=str(run_dir), model_label=record['model_label'], previous=record['previous'])


def _register_saved_models_route(app, context) -> None:
    """Register the model chooser list with its saved checkpoints."""
    @app.get('/api/runs/models')
    def saved_models(output_root: str | None = None, include_mock: bool = True, fresh: bool = False):
        """The model chooser's list: every run that holds a saved RL model, with all of its save points.
        Small metadata files only; the selected model is verified by `/api/runs/model` as before. The run list's cache
        keeps each run's save points too (record 7.274), read many runs at a time (7.279); `fresh` reads every run
        folder again."""
        try:
            rows = runs.list_runs(context.roots, output_root, include_mock=include_mock, fresh=fresh)
            return dict(models=ckpt.saved_models(rows, runs.checkpoint_listings(rows)))
        except PathNotAllowed as exc:
            fail(403, exc)


def _register_model_structure_route(app, context) -> None:
    """Register the saved model network-structure table endpoint."""
    @app.post('/api/runs/model/structure')
    def model_structure_table(body: ModelStructureBody):
        """Every layer of the chosen saved model with its type, shape and parameter count - a table, no plot.
        Tensor-only read of `model_weights.pt` after its checksum matched; types only when the rebuilt network
        holds exactly the saved tensors."""
        run_dir = context.run_path(body.run_dir)
        try:
            return model_structure.structure(ckpt.resolve_checkpoint(run_dir, body.checkpoint_id))
        except FileNotFoundError as exc:
            fail(404, exc)
        except ValueError as exc:
            fail(409, exc)


def _register_model_graph_view_route(app, context) -> None:
    """Register archived-state graph inspection for a selected saved model."""
    @app.post('/api/runs/model/graph-view')
    def model_graph_view(body: GraphViewBody):
        """The data of the circuit graph view: the chosen save point replayed on a state its own run ARCHIVED -
        the circuit, the attention on every connection, the size the policy proposes per group. One forward pass on
        the CPU; nothing is simulated and nothing is written. The picture is drawn in the browser only."""
        run_dir = context.run_path(body.run_dir)
        try:
            return graph_view.graph_view(run_dir, body.checkpoint_id, evaluation=body.evaluation)
        except FileNotFoundError as exc:
            fail(404, exc)
        except ValueError as exc:                  # GraphViewUnavailable included: said in plain words
            fail(409, exc)


def _launch_and_control_routes(app: FastAPI, context: ApiContext) -> None:
    """Start, continue, the launch requests, the run commands and the run status."""
    # Reject removed search methods and deduplicate the request before starting the configured run.
    @app.post('/api/runs/start')
    def start(body: StartBody):
        removed = schema.removed_search_method(body.config)
        if removed:
            # Only a page older than this server sends one (the configuration it keeps drops the search block when it
            # loads, store.ts migrateConfig): starting it as SAC would run something else than the page said.
            fail(409, f'Not started: this configuration asks for the search method "{schema.REMOVED_SEARCH_METHODS[removed]}", '
                      'which was removed on 2026-10-06 - SAC is the only search method now. The page is older than the '
                      'server: reload it, check Run configuration, and press Start again.', code='search_method_removed')
        return once(body.request_id, 'start', lambda record: start_run(
            context, context.parse_config(body.config), body, baseline_only=body.baseline_only, record=record))

    # Authorize the run directory and deduplicate its continuation request.
    @app.post('/api/runs/continue')
    def continue_run(body: ContinueBody):
        run_dir = context.run_path(body.run_dir)

        def work(record):
            """Rebuild resume settings from the saved configuration before submitting the continuation launch."""
            config = schema.WorkbenchConfig.model_validate(read_json(RunLayout(run_dir).effective_config))
            config.run.mode, config.run.model_source.run_dir = 'resume', str(run_dir)
            if config.run.connection_profile_id:          # on whichever session of its connection is free (record 7.351)
                config.run.connection_profile_id = connection.session_group(config.run.connection_profile_id)[0]
            if body.max_evaluations:
                config.run.max_evaluations = body.max_evaluations
            return start_run(context, config, body, record=record)
        return once(body.request_id, 'continue', work)

    @app.get('/api/runs/request')
    def launch_request(request_id: str = Query(pattern=launch_requests.ID_PATTERN)):
        """What became of a launch the page sent before it was reloaded (record 7.261): done (with the run), pending, or
        unknown - it never arrived, was refused, or failed; nothing was made then."""
        return launch_requests.lookup(request_id, started=worker_started)

    @app.get('/api/runs/continuation')
    def continuation(run_dir: str, max_evaluations: int | None = Query(None, ge=1)):
        """Whether Continue can go on with this run, checked before the press (record 7.261): read-only, without the run
        lock; the press checks everything again."""
        return runs.continuation(context.run_path(run_dir), max_evaluations=max_evaluations)

    # Send a supported run command and report a rejected command as a conflict.
    @app.post('/api/runs/command')
    def command(body: CommandBody):
        try:
            return runs.send_command(context.run_path(body.run_dir), body.command)
        except runs.RunRejected as exc:            # "Save now" on a run that cannot or need not save: said, not done
            fail(409, exc, code=exc.code)

    # Read run state with the cached status of its configured connection.
    @app.get('/api/runs/status')
    def status(run_dir: str):
        path = context.run_path(run_dir)
        return runs.status_view(path, context.monitor.status)


def _corner_check_routes(app: FastAPI, context: ApiContext) -> None:
    """The corner check of a run: plan, start, status, stop."""
    @app.get('/api/runs/corner-check/plan')
    def corner_check_plan(run_dir: str, designs: int = Query(corner_check.MAX_DESIGNS, ge=1, le=corner_check.MAX_DESIGNS)):
        """Which designs a check would simulate at which corners, and how many simulations that is. Free: local files."""
        return corner_check.plan(context.run_path(run_dir), designs=designs)

    @app.post('/api/runs/corner-check/start')
    def corner_check_start(body: CornerCheckBody):
        """A real circuit needs authorize_real_simulation (and the connection gate); nothing is created before both."""
        run_dir = context.run_path(body.run_dir)
        try:
            directory = corner_check.prepare(run_dir, designs=body.designs, expected=body.expected_designs,
                                             simulations=body.simulations, allow_real=body.authorize_real_simulation,
                                             acknowledge_unknown=body.acknowledge_unknown_connection, monitor=context.monitor)
        except (corner_check.CheckRefused, runs.RunRejected) as exc:
            fail(409, exc, code=exc.code, report=exc.report)
        request = read_json(directory / 'request.json')
        pid = corner_check.launch(directory, allow_real=body.authorize_real_simulation and not request['mock'])
        return dict(check_id=request['check_id'], worker_pid=pid, simulations=request['simulations'], mock=request['mock'])

    # Return one corner-check state after authorizing its run directory.
    @app.get('/api/runs/corner-check/status')
    def corner_check_status(run_dir: str, check_id: str):
        try:
            return corner_check.check_status(context.run_path(run_dir), check_id)
        except corner_check.CheckRefused as exc:
            fail(400, exc)
        except FileNotFoundError:
            fail(404, 'This run has no corner check with that identifier.')

    @app.post('/api/runs/corner-check/stop')
    def corner_check_stop(body: CornerStopBody):
        """The simulation in flight ends, then the cell is restored; nothing is killed."""
        try:
            return corner_check.request_stop(context.run_path(body.run_dir), body.check_id)
        except corner_check.CheckRefused as exc:
            fail(409, exc, code=exc.code)
        except FileNotFoundError:
            fail(404, 'This run has no corner check with that identifier.')


def _run_data_routes(app: FastAPI, context: ApiContext) -> None:
    """A run's files, data tables, log, training series and file downloads."""
    # List run files outside the work directory and lock files, including their total size.
    @app.get('/api/runs/files')
    def files(run_dir: str):
        path = context.run_path(run_dir)
        entries = []
        for item, relative, stat in run_files(path, exclude_roots=('work',)):
            if relative.endswith('.lock'):
                continue
            entries.append(dict(path=relative, bytes=stat.st_size, modified_utc=utcnow().fromtimestamp(
                stat.st_mtime, tz=utcnow().tzinfo).isoformat()))
        return dict(run_dir=str(path), files=entries, total_bytes=sum(e['bytes'] for e in entries),
                    paths=RunLayout(path).subpaths())

    # Return a bounded table view together with columns, row count and commit cutoff.
    @app.get('/api/runs/table')
    def table(run_dir: str, table: str, limit: int = Query(20, ge=1, le=500), tail: bool = True):
        if table not in TABLES:
            fail(404, 'Unknown table')
        reader = DatasetReader(context.run_path(run_dir) / 'data')
        names, rows = reader.shown_rows(table, limit, tail=tail)
        return dict(table=table, total_rows=reader.row_counts()[table], cutoff_commit_seq=reader.cutoff_seq,
                    columns=names, rows=rows)

    @app.get('/api/runs/logs')
    def logs(run_dir: str, kind: str = Query('events', pattern='^(events|errors)$'), limit: int = Query(100, ge=1, le=1000)):
        return dict(kind=kind, entries=read_jsonl_tail(context.run_path(run_dir) / 'logs' / f'{kind}.jsonl', limit))

    @app.get('/api/runs/training')
    def training(run_dir: str, flushes: int = Query(0, ge=0), tail_cursor: str | None = Query(None, max_length=1024)):
        """The Training tab's numbers (record 7.193): the run's recorded evaluations, learner updates and spec values
        from flush record `flushes` on, then the journal's bundles no flush has published yet. Read-only; nothing is
        computed into them, and nothing is simulated."""
        try:
            return training_series.read_training(context.run_path(run_dir), flushes, tail_cursor=tail_cursor)
        except FileNotFoundError as exc:
            fail(404, exc)

    # Stream only the size captured when an authorized run file is opened.
    @app.get('/api/runs/download')
    def download(run_dir: str, path: str):
        try:
            target = safe_child(context.run_path(run_dir), path)
        except PathNotAllowed as exc:
            fail(403, exc)
        if not target.is_file():
            fail(404, 'No such file')
        size, chunks = file_snapshot(target)             # a live run's logs grow while they are downloaded
        return StreamingResponse(chunks, media_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream',
                                 headers={'Content-Length': str(size), **attachment(target.name)})


def _export_routes(app: FastAPI, context: ApiContext) -> None:
    """Data-only exports: a run's CSV tables and package, the research aggregates."""
    # Export one known run table as CSV and return its absolute and run-relative paths.
    @app.post('/api/runs/export-csv')
    def export_csv(body: ExportBody):
        if body.table not in TABLES:
            fail(404, 'Unknown table')
        path = aggregates.export_table_csv(context.run_path(body.run_dir), body.table)
        return dict(path=str(path), relative=str(path.relative_to(context.run_path(body.run_dir))))

    @app.post('/api/runs/export-package')
    def export_package(body: ExportBody):
        """Data-only package: JSON, Parquet, CSV, JSONL, netlists. No waveforms, work files or models."""
        path = context.run_path(body.run_dir)
        members = package_files(path, exclude_roots=('work', 'control', 'waveforms', 'checkpoints'), exclude_dirs=('_quarantine',))
        return zip_download(members, f'{path.name}__data.zip')

    # Regenerate aggregate exports for the experiment that contains the selected run.
    @app.post('/api/aggregates/export')
    def export_aggregates(body: ExportBody):
        run_dir = context.run_path(body.run_dir)
        experiment = RunLayout(run_dir).experiment_dir
        return dict(experiment_dir=str(experiment), files=aggregates.export_aggregates(experiment))

    @app.get('/api/aggregates/download')
    def download_aggregates(run_dir: str):
        """The research CSVs of this run's experiment as one zip: they lie above the run directory, where the per-file
        download cannot reach. Only what the exporter writes (<table>.csv + <table>.meta.json), as it is on disk now."""
        experiment = RunLayout(context.run_path(run_dir)).experiment_dir
        members = [experiment / 'aggregates' / f'{table}{suffix}' for table in aggregates.COLUMNS for suffix in ('.csv', '.meta.json')]
        members = [m for m in members if m.is_file() and not m.is_symlink()]
        if not members:
            fail(404, 'No research CSVs have been exported for this experiment yet')
        return zip_download([(item, item.name) for item in members], f'{experiment.name}__aggregates.zip')
