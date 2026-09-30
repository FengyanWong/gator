"""Task and circuit APIs, including supported legacy request contracts."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from pydantic import ValidationError
from .. import bridge_read, runs, schema, tasks
from .. import consistency, ngspice_tasks, profiles, structures, task_files, virtuoso_setup, working_copy
from ..agents.prompts import circuit_summary
from ..native_cells import load_import as load_cell_import
from ..paths import PathNotAllowed, refuse_nul
from ..security import redact
from .models import CircuitBody, ConfigBody, CopyBody, DiffBody, MatchedBody, NativeReadBody, NgspiceCheckBody, NgspiceNameBody, NgspiceReadBody, NgspiceSaveBody, ProfileActionBody, SetupBody, TaskCheckBody, TaskFileBody, TaskFileTextBody, TaskSaveBody
from .support import _bridge_call, fail, load_runtime, validate_loaded
from .context import ApiContext

COPY_REFUSED = ((working_copy.CopyError, virtuoso_setup.SetupError), 'refused')


def register(app: FastAPI, context: ApiContext):
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

    @app.post('/api/circuit/load')
    def circuit_load(body: CircuitBody):
        try:
            circuit = schema.CircuitReference.model_validate(body.circuit)
        except ValidationError as exc:
            fail(422, exc)
        context.authorize_circuit(circuit)
        shell = schema.WorkbenchConfig.model_validate(dict(circuit=circuit.model_dump(), run=dict(max_evaluations=1)))
        runtime, blocked = load_runtime(shell)
        if runtime is not None and runtime.circuit.get('generated_profile') and not runtime.circuit.get('baseline_recorded'):
            # A Single baseline simulation records itself when it finishes (record 7.78); one made before that, or one
            # whose worker could not, becomes the reference now: the newest completed one of this task under the
            # remembered output root (the one every run is filed under; none remembered = no run was ever made here),
            # from its manifest and tables, nothing simulated. The task is then loaded again with its reference.
            remembered = runs.load_settings().get('output_root')
            try:
                adopted = remembered and profiles.adopt_latest_baseline(runtime.task_key[len('real:'):], context.roots.resolve(remembered))
            except (PathNotAllowed, OSError):
                adopted = None
            if adopted:
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
        return dict(loaded=True, training_capabilities=tasks.training_capabilities(runtime.task_key), task_key=runtime.task_key, mock=runtime.mock, circuit=runtime.circuit,
                    simulator=runtime.circuit.get('simulator') or ('mock' if runtime.mock else 'spectre'),
                    content_sha256=runtime.circuit.get('netlist_sha256'), provided_metrics=list(runtime.provided_metrics),
                    hierarchy=tree, summary=circuit_summary(graph, circuit=runtime.circuit), complete=graph.complete,
                    diagnostics=[dict(code=d.code, severity=d.severity, message=d.message) for d in graph.diagnostics],
                    analysis_context=graph.metadata.get('analysis_context'), notes=runtime.notes,
                    evaluation_backend=runtime.circuit.get('evaluation_backend'), max_concurrency=runtime.max_concurrency,
                    native_draft=bool(runtime.circuit.get('native_draft')), generated_profile=bool(runtime.circuit.get('generated_profile')),
                    baseline_recorded=runtime.circuit.get('baseline_recorded'), baseline_attempt=runtime.circuit.get('baseline_attempt'), **native)

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
        from the run's own tables; never replaced once recorded). Without `run_dir`: the newest run of the task. Since
        record 7.78 a finished Single baseline simulation records itself; the press is for a run made another way
        (an optimization run's first evaluation, a run made before)."""
        try:
            run_dir = context.run_path(body.run_dir) if body.run_dir else profiles.latest_baseline_run(
                body.name, [r['run_dir'] for r in runs.list_runs(context.roots, include_mock=False)])
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
            return profiles.delete_profile(body.name, run_rows=runs.list_runs(context.roots, include_mock=False))
        except profiles.ProfileError as exc:
            fail(409, exc, code='delete_refused')

    def _ngspice_kinds(body):
        try:
            return (ngspice_tasks.parse_kinds_text(body.device_kinds) if isinstance(body.device_kinds, str)
                    else ngspice_tasks._clean_kinds(body.device_kinds or {}))
        except ngspice_tasks.NgspiceTaskError as exc:
            fail(422, exc)

    def _ngspice_source(path):
        """The file a deck was loaded from, for its relative includes: only a path under the input roots counts - the
        browser names no other file (it got this one from /api/ngspice/read)."""
        if not path or '\x00' in str(path):         # a NUL byte is no file (the OS refuses it with ValueError)
            return None
        resolved = Path(path).expanduser().resolve()
        return str(resolved) if any(resolved == r or r in resolved.parents for r in context.input_roots) else None

    @app.post('/api/ngspice/read')
    def ngspice_read(body: NgspiceReadBody):
        """A deck read from a file on the backend machine (inside an allowed input root) into the window's text box."""
        try:
            refuse_nul(body.path)                  # refused like any path outside the input roots, not an HTTP 500
            return ngspice_tasks.read_file(body.path, context.input_roots)
        except PermissionError as exc:
            fail(403, exc)
        except ngspice_tasks.NgspiceTaskError as exc:
            fail(409, exc, code='refused')

    @app.post('/api/ngspice/check')
    def ngspice_check(body: NgspiceCheckBody):
        """How the deck reads: elements, the values a run can vary, the results, problems. Nothing is stored or run."""
        source = _ngspice_source(body.source_path)
        return ngspice_tasks.check(body.text, device_kinds=_ngspice_kinds(body),
                                   include_root=str(Path(source).parent) if source else None)

    @app.post('/api/ngspice/task/save')
    def ngspice_save(body: NgspiceSaveBody):
        """Explicit press: the deck becomes the task ngspice:<name>, or its next revision. No simulation."""
        try:
            entry = ngspice_tasks.save(body.name, body.text, device_kinds=_ngspice_kinds(body), source_path=_ngspice_source(body.source_path),
                                       circuit_class=body.circuit_class, pdk_id=body.pdk_id)
        except ngspice_tasks.NgspiceTaskError as exc:
            fail(409, exc, code='refused')
        parsed = ngspice_tasks.parse_entry(entry, body.text)
        return dict(entry, starter=ngspice_tasks.starter_config(entry['task_key']), check=dict(ok=True, **ngspice_tasks.summary(parsed)))

    @app.get('/api/ngspice/task')
    def ngspice_task(name: str):
        """The saved deck of a task, for editing in the window."""
        try:
            entry, text = ngspice_tasks.load(name)
        except (KeyError, ngspice_tasks.NgspiceTaskError):
            fail(404, f'No ngspice task named {name!r}')
        return dict(entry, text=text)

    @app.post('/api/ngspice/task/delete')
    def ngspice_delete(body: NgspiceNameBody):
        """Explicit click (the page asks once more): the task leaves the list; its folder is kept aside. Refused while a
        run of it is working."""
        try:
            return ngspice_tasks.delete(body.name, run_rows=runs.list_runs(context.roots, include_mock=False))
        except ngspice_tasks.NgspiceTaskError as exc:
            fail(409, exc, code='delete_refused')

    @app.post('/api/virtuoso/copy')
    def virtuoso_copy(body: CopyBody):
        """Refused since 2026-09-23 (user request): the workbench makes no copy of a cell any more. The user copies the
        cell and its testbench in Virtuoso and reads the copy (`/api/virtuoso/import` with `work_here`: the page asks
        whether it is a copy they made). `working_copy.make` stays for the tests only: Save as through the API makes its
        copy with `working_copy.make_task_copy`, which does not call it."""
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
            found = working_copy.read_setup(context.monitor, body.profile_id, body.library, body.cell)
            if body.config is not None and found.get('test'):
                config = context.parse_config(body.config)
                ours = virtuoso_setup.from_rows(config, model_files=found['model_files'], analyses=found['analyses'],
                                                variables=found['variables'], bindings=found['bindings'],
                                                initial_conditions=found.get('initial_conditions'))
                found['editor_differences'] = virtuoso_setup.differences(ours, found)
            return found
        return _bridge_call(read, COPY_REFUSED)

    @app.post('/api/virtuoso/task/save')
    def virtuoso_task_save(body: TaskSaveBody):
        """Explicit click - a person's only: store the editors' rows as the task real:<name>. The first save of a cell takes
        its working copy; on an open task, Save task updates it (next revision) and Save as (`as_new`) makes another task
        with a copy of its own. A Maestro-measured task writes its setup into its copy and reads it back first; then the
        copy is read into the workbench (read-only) and the task files are generated from it. Zero simulations."""
        if not body.profile_id:
            fail(422, 'A connection profile is required')
        config = context.parse_config(body.config)
        return _bridge_call(lambda: profiles.save_task(context.monitor, body.profile_id, body.name, config, library=body.library, cell=body.cell,
                                                       task=body.task, as_new=body.as_new, extras=body.extras,
                                                       run_rows=runs.list_runs(context.roots, include_mock=False)),
                            (profiles.NeedsFrequency, 'needs_expected_frequency'), ((profiles.ProfileError,), 'refused'), COPY_REFUSED)

    @app.post('/api/virtuoso/task/file')
    def virtuoso_task_file(body: TaskFileBody):
        """The task file of the CURRENT editors - what "Save task" would store - as text, laid out with its own
        explanations. Local files only: nothing is read from Virtuoso."""
        config = context.parse_config(body.config)
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
        config = context.parse_config(body.config)
        try:
            return consistency.check(context.monitor, body.profile_id, config)
        except KeyError as exc:
            fail(409, exc.args[0] if exc.args else exc, code='not_a_saved_task')

    @app.post('/api/virtuoso/task/file/check')
    def virtuoso_task_file_check(body: TaskFileTextBody):
        """Read a task file someone edited: its rows (checked with the editors' schema), what it holds beside them, and
        every problem in plain words. Nothing is saved."""
        rows, extras, problems = task_files.parse(body.text)
        return dict(rows=rows, extras=extras, problems=problems, ok=not problems)

    def _native(body, op):
        return _bridge_call(lambda: bridge_read.read(context.monitor, body.profile_id, op, library=body.library, cell=body.cell,
                                                     testbench=body.testbench if op == 'import_cell' else None))

    @app.post('/api/config/validate')
    def config_validate(body: ConfigBody):
        config, runtime, blocked = context.load_config(body.config)
        report = validate_loaded(config, runtime, roots=context.roots)
        if runtime is not None and runtime.circuit.get('native_draft'):          # it must never look startable
            report.add('blocker', 'circuit_profile_missing', 'circuit', tasks.NATIVE_DRAFT_NOT_EXECUTABLE)
        return dict(report.as_dict(), config_hash=schema.config_hash(config),
                    task_definition_hash=schema.task_definition_hash(config), circuit_blocker=blocked,
                    mock=None if runtime is None else runtime.mock)

    @app.post('/api/config/diff')
    def config_diff(body: DiffBody):
        from ..agents.proposals import structured_diff
        return dict(diff=structured_diff(body.before, body.after))

    @app.post('/api/parameters/matched')
    def parameters_matched(body: MatchedBody):
        """Matched devices... (status record 7.103): the structures of the loaded circuit and the ties they suggest for
        the Parameters rows; with `apply`, also those rows with the chosen ties made, their diff and what validation says
        about them. Local files only: nothing is simulated, nothing is stored - the page applies the rows or not."""
        from ..agents.proposals import structured_diff
        from ..validation import independent_action_count
        config, runtime, blocked = context.load_config(body.config)
        if runtime is None:
            return dict(applicable=False, blocked=True, why_not=f'The circuit could not be read: {blocked["blocker"]}',
                        structures=[], suggestions=[])
        name = runtime.task_key.partition(':')[2]
        verified = runtime.task_key.startswith('real:') and name in tasks.REAL_PROFILES and not runtime.circuit.get('generated_profile')
        answer = structures.suggest(runtime.base_graph, list(config.parameters), None if verified else body.apply)
        answer.update(applicable=not verified, independent_before=independent_action_count(config.parameters))
        if verified:
            return dict(answer, suggestions=[], why_not=f'The rows of {runtime.task_key} are fixed by its verified circuit '
                        'profile: a run accepts exactly those. The structures are listed for information.')
        answer['note'] = ('Save task afterwards: the task runs with the rows it was saved with.'
                          if runtime.circuit.get('generated_profile') else 'The ties become part of the task when you '
                          'press Save task.' if runtime.circuit.get('native_draft') else '')
        if body.apply is not None:
            before = config.model_dump(mode='json')
            after = dict(before, parameters=answer['parameters'])
            proposed = context.parse_config(after)
            report = validate_loaded(proposed, runtime, reachability=False)     # only the rows' errors are used
            answer['parameters'] = proposed.model_dump(mode='json')['parameters']       # as the schema reads them
            answer.update(diff=structured_diff(before, proposed.model_dump(mode='json')),
                          independent_after=independent_action_count(proposed.parameters),
                          problems=[i.as_dict() for i in report.issues if i.path.startswith('parameters')
                                    and i.level in ('error', 'blocker')])
        return answer
