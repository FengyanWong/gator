"""Run control, saved models and data-only exports."""
from __future__ import annotations
import mimetypes
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from .. import aggregates, checkpoints as ckpt, runs, schema
from .. import corner_check
from ..layout import RunLayout
from ..paths import PathNotAllowed, safe_child
from ..storage.atomic import read_json, read_jsonl_tail, JsonlAppender
from ..storage.dataset import DatasetReader, map_to_dict, utcnow
from ..storage.tables import TABLES
from .models import CommandBody, ContinueBody, CornerCheckBody, CornerStopBody, ExportBody, GraphViewBody, HintBody, ModelStructureBody, StartBody
from .support import attachment, compatibility_unchecked, fail, file_snapshot, run_files, zip_download
from .context import ApiContext


# /api/runs/model took any dict: {}, a numeric checkpoint_id or a list as run_dir failed with HTTP 500 (review of 2026-09-29).
class ModelBody(ModelStructureBody):
    """A saved model and, optionally, the page's configuration to compare it with."""
    config: dict | None = None


def register(app: FastAPI, context: ApiContext):
    @app.get('/api/runs/llm-thread')
    def llm_thread(run_dir: str):
        directory = context.run_path(run_dir)
        status = read_json(directory / 'status.json', default={})
        manifest = read_json(directory / 'run_manifest.json', default={})
        search = status.get('search') or manifest.get('search')
        return dict(run_dir=str(directory), search=search, state=status.get('state'),
                    events=read_jsonl_tail(directory / 'llm/live.jsonl', 5000))

    @app.post('/api/runs/llm-hint')
    def llm_hint(body: HintBody):
        directory = context.run_path(body.run_dir)
        status = read_json(directory / 'status.json', default={})
        if status.get('state') != 'running' or not (status.get('search') or {}).get('hints_available'):
            fail(409, 'This run cannot accept another AI hint in its current phase')
        text = body.text
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1500:
            fail(422, 'A hint needs 1–1500 characters')
        path = directory / 'control/llm_hints.jsonl'
        if len(read_jsonl_tail(path, 51)) >= 50:
            fail(409, 'This run has reached its 50-hint limit')
        log = JsonlAppender(path)
        try:
            log.append(dict(text=text.strip(), utc=utcnow().isoformat()))
        finally:
            log.close()
        return dict(accepted=True, note='Included in the next eligible call; does not trigger a rescue or change budgets.')

    @app.get('/api/runs')
    def get_runs(output_root: str | None = None, include_mock: bool = True):
        try:
            return dict(runs=runs.list_runs(context.roots, output_root, include_mock=include_mock))
        except PathNotAllowed as exc:
            fail(403, exc)

    @app.post('/api/runs/model')
    def describe_model(body: ModelBody):
        """The selected RL model: source task, save time, schema, counters, actual path, restorable
        components and compatibility with the CURRENT configuration. Independent of the agent model."""
        run_dir = context.run_path(body.run_dir)
        try:
            description = ckpt.describe(run_dir, body.checkpoint_id or 'latest')
        except FileNotFoundError as exc:
            fail(404, exc)
        result = dict(description=description)
        from .. import pdk
        own = pdk.run_vocabulary(run_dir)                  # the model's component list: the page's list follows it
        result['vocabulary'] = dict(name=own.name if own else pdk.STANDARD, label=own.label if own else pdk.label(None),
                                    pdk_id=own.pdk_id if own else None, sha256=own.sha256 if own else None,
                                    loaded=bool(own is None or pdk.load_record(own.pdk_id) is not None))
        if body.config:
            config, runtime, blocked = context.load_config(body.config)
            if runtime is not None:
                from ..compile import CompileError, compile_task
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
                        contract = runs.learner_contract(config, runtime, task_hash, compiled.spec_schema, vocabulary)
                        meta_ = ckpt.read_metadata(description['path'])
                        mode = config.run.mode if config.run.mode != 'scratch' else 'fine_tune'
                        result['compatibility'] = ckpt.check_compatibility(meta_, mode=mode, task_definition_hash=task_hash,
                                                                           contract=contract)
                result['suggestion'] = runs.suggest_mode(config, run_dir, task=runtime)   # the task loaded above, not a second load
        return result

    @app.get('/api/runs/default-model')
    def default_model(label: str | None = None, project: str | None = None):
        """Default = the newest model saved under this RL model label (record 7.159), and that run's `latest`, not
        `best`. `project`: the project name runs were remembered under before the label, asked when the label has none."""
        remembered = runs.load_settings().get('last_run') or {}
        last = (remembered.get(label.strip()) if label and label.strip() else None) or (remembered.get(project) if project else None)
        if not last or not context.roots.is_allowed(last) or not (Path(last) / 'checkpoints' / 'latest.json').is_file():
            return dict(run_dir=None, checkpoint_id='latest', reason='No saved model under this label yet.')
        return dict(run_dir=last, checkpoint_id='latest', description=ckpt.describe(last, 'latest'))

    @app.get('/api/runs/models')
    def saved_models(output_root: str | None = None, include_mock: bool = True):
        """The model chooser's list: every run that holds a saved RL model, with all of its save points.
        Small metadata files only; the selected model is verified by `/api/runs/model` as before."""
        try:
            return dict(models=ckpt.saved_models(runs.list_runs(context.roots, output_root, include_mock=include_mock)))
        except PathNotAllowed as exc:
            fail(403, exc)

    @app.post('/api/runs/model/structure')
    def model_structure_table(body: ModelStructureBody):
        """Every layer of the chosen saved model with its type, shape and parameter count - a table, no plot.
        Tensor-only read of `model_weights.pt` after its checksum matched; types only when the rebuilt network
        holds exactly the saved tensors."""
        from .. import model_structure
        run_dir = context.run_path(body.run_dir)
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
        run_dir = context.run_path(body.run_dir)
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
            config.run.search = schema.SearchSettings()
            config.run.mode, config.run.max_evaluations = 'scratch', 1         # exactly ONE costed evaluation
            config.output.save_checkpoints = False
            config.project.task_name = f'{config.project.task_name}.baseline'
        try:
            layout, manifest = runs.prepare_run(config, context.roots, allow_real=allow_real,
                                                confirm_transfer=getattr(body, 'confirm_transfer', False), monitor=context.monitor,
                                                acknowledge_unknown=body.acknowledge_unknown_connection)
        except runs.RunRejected as exc:
            fail(409, exc, code=exc.code, report=exc.report)
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
        return _start(context.parse_config(body.config), body, baseline_only=body.baseline_only)

    @app.post('/api/runs/continue')
    def continue_run(body: ContinueBody):
        run_dir = context.run_path(body.run_dir)
        config = schema.WorkbenchConfig.model_validate(read_json(RunLayout(run_dir).effective_config))
        config.run.mode, config.run.model_source.run_dir = 'resume', str(run_dir)
        if body.max_evaluations:
            config.run.max_evaluations = body.max_evaluations
        return _start(config, body)

    @app.post('/api/runs/command')
    def command(body: CommandBody):
        try:
            return runs.send_command(context.run_path(body.run_dir), body.command)
        except runs.RunRejected as exc:            # "Save now" on a run that cannot or need not save: said, not done
            fail(409, exc, code=exc.code)

    @app.get('/api/runs/status')
    def status(run_dir: str):
        path = context.run_path(run_dir)
        layout = RunLayout(path)
        result = runs.run_status(path)
        from ..reward_diagnostics import load as steering_check
        try:
            result['steering'] = steering_check(path)
        except Exception:                   # a diagnostic line: a missing or damaged data part leaves it empty, never the status
            result['steering'] = None
        manifest = read_json(layout.manifest, default={}) or {}
        result.update(manifest=dict(mode=manifest.get('mode'), mock=manifest.get('mock'), task_id=manifest.get('task_id'),
                                    seeds=manifest.get('seeds'), source_model=manifest.get('source_model'),
                                    budgets=manifest.get('budgets'), output=manifest.get('output'),
                                    connection_gate=manifest.get('connection_gate'), mock_notice=manifest.get('mock_notice')),
                      summary=read_json(layout.summary, default=None))
        profile = (result.get('connection_profile_id') or None)
        result['connection'] = context.monitor.status(profile) if profile else dict(overall='not_applicable')
        return result

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

    @app.get('/api/runs/table')
    def table(run_dir: str, table: str, limit: int = Query(20, ge=1, le=500), tail: bool = True):
        if table not in TABLES:
            fail(404, 'Unknown table')
        reader = DatasetReader(context.run_path(run_dir) / 'data')
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
        return dict(kind=kind, entries=read_jsonl_tail(context.run_path(run_dir) / 'logs' / f'{kind}.jsonl', limit))

    @app.get('/api/runs/training')
    def training(run_dir: str, flushes: int = Query(0, ge=0)):
        """The Training tab's numbers (record 7.193): the run's recorded evaluations, learner updates and spec values
        from flush record `flushes` on, then the journal's bundles no flush has published yet. Read-only; nothing is
        computed into them, and nothing is simulated."""
        from .. import training_series
        try:
            return training_series.read_training(context.run_path(run_dir), flushes)
        except FileNotFoundError as exc:
            fail(404, exc)

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
        members = run_files(path, exclude_roots=('work', 'control', 'waveforms', 'checkpoints'), exclude_dirs=('_quarantine',))
        return zip_download(((item, relative) for item, relative, _ in members), f'{path.name}__data.zip')

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
