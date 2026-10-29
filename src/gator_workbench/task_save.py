"""Save task: the editors' rows stored as the task real:<name> - the working copy's Maestro setup written and read back,
the copy read into the workbench again, the profile files and the task file generated from it, a new revision with its
history kept.

Moved from profiles.py by the refactoring (docs/plan-refactoring.md); profiles.py re-exports every name.
task_saving.py runs one save at a time and reports how far it is; the save itself is this module's save_task.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from . import bridge_read, native_cells, recipes, task_files, units, virtuoso_setup, working_copy
from .circuit_types import MAESTRO, RECIPES
from .compile import normalization_scale
from .names import TRASH_STAMP
from .profile_generate import write_profile_files
from .profile_store import FILES, HISTORY, ProfileError, TASK_FILE, profile_dir, profile_entry, task_file
from .saved_rows import describe_undone, undone_by_saving
from .saved_tasks import TRASH, load_profile, tasks_for_cell, working_run_of
from .storage.atomic import write_json
from .storage.dataset import utcnow
from .task_registry import REAL_PROFILES, REMOVED_REAL_TASKS
from .validation import Report, check_equation


class NewerSaved(ProfileError):
    """The rows are older than the saved task: saving them would undo what was saved since (record 7.203). `undone`
    goes to the page with the refusal, which asks: Reload saved values, or save anyway."""

    def __init__(self, message, undone) -> None:
        super().__init__(message)
        self.detail_extra = dict(undone=undone)


# ---------------------------------------------------------------------------------- saving a task: "Save task" / "Save as"
def measurement_kind(config) -> str:
    """How a task measures, read from its Probes: all Maestro outputs -> 'maestro'; all results of one circuit type ->
    that type."""
    measured = list(config.measurements)
    if not measured:
        raise ProfileError('Probes is empty: say what the simulation measures (Probes tab) before saving the task')
    measured = [m for m in measured if m.result_source != 'size_estimate'] or measured   # not simulated: beside either way
    sources = {m.result_source for m in measured}
    if sources == {'size_estimate'}:
        raise ProfileError('Probes holds only size estimates: add what the simulation measures before saving the task')
    if sources == {'ade_output'}:
        return MAESTRO
    if sources == {'backend_profile'}:
        names = {m.source_name for m in measured}
        fitting = [recipe for recipe in RECIPES if names <= set(recipes.provided_metrics(recipe))]
        if len(fitting) == 1:
            return fitting[0]
        if not fitting:
            raise ProfileError(f'The probes name results that no circuit type gives together: {", ".join(sorted(names))}')
        raise ProfileError('The probes fit both circuit types (only supply results): add a probe that says which one, '
                           'e.g. osc_frequency_hz or gain_db_at_start')
    raise ProfileError('The probes mix Maestro outputs and results of a circuit type: a task measures one way')


def check_saveable(name, config, *, task=None, as_new: bool=False, run_rows=(), replace_newer: bool=False, base_revision=None) -> None:
    """The refusals of `save_task` that read nothing from Virtuoso, on their own: the Save route asks them before it
    chooses the Virtuoso session the save goes to (record 7.351), so that a refused save contacts no Virtuoso.
    `save_task` asks them again, unchanged."""
    _saveable(name, config, task, as_new, run_rows, replace_newer, base_revision)
    measurement_kind(config)


def save_task(monitor, profile_id, name, config, *, library=None, cell=None, task=None, as_new: bool=False, extras=None,
              run_rows=(), commands=None, progress=None, base_revision=None, replace_newer: bool=False) -> dict:
    """Explicit press - only a person can do it: store the editors' rows as the task real:<name>.

    * First save from a cell: the task takes the cell's working copy. "Save task" on an open task updates THAT task (a
      new revision, same name); "Save as" (`as_new`) makes a new task with a copy of its own, made from the open task's
      copy, cells renamed <cell>_<name>.
    * Virtuoso side first: a Maestro-measured task writes its setup (outputs and specs from the rows; analyses,
      variables and bindings from `extras`, else from what the copy was last written with, else from the saved task
      file) into its copy and reads it back - it must match;
      then the copy is read into the workbench again (netlist + CDF readback, read-only): the reference every run of
      the task is compared with.
    * Then the profile files are generated from that copy and the task file is written. A new revision keeps the
      recorded baseline only when parameters, probes, measurement, analyses, variables and bindings are unchanged.
    * `progress(step, steps)` hears each step as it starts, with every step this save takes (`task_saving.TITLES`): the
      page shows them while the save runs (record 7.198).
    * Rows older than the saved task - saving them would undo what was saved since (`consistency.undone_by_saving`;
      `base_revision`: the revision the page's rows came from) - are refused with what they would undo (`NewerSaved`),
      before anything is written, until the user answers "Save anyway" (`replace_newer`; record 7.203)."""
    commands, extras = commands or {}, dict(extras or {})
    directory, current, updating = _saveable(name, config, task, as_new, run_rows, replace_newer, base_revision)
    kind = measurement_kind(config)
    steps = (['copy'] if current and not updating else []) + (['setup', 'deck'] if kind == MAESTRO else []) + ['read', 'files']
    mark = (lambda step: progress(step, steps)) if progress else (lambda step: None)
    saved = task_file(task) if current else None
    target, claimed = _save_target(
        updating, current, task, mark, monitor, profile_id, name, commands, library, cell)
    staging = directory.with_name(f'.{name}.saving')
    try:
        # What the task file adds beside the rows: sent with this save, else what the copy was last written with (by the last
        # save, "Write to Virtuoso" or an approved agent setup - so never older than the saved task's), else the saved task's;
        # a part none of them names stays as the copy has it. Save as starts from the open task's copy.
        base = working_copy.last_written(current['copy_target'] if current else target) or (saved or {}).get('maestro') or {}
        maestro = None
        if kind == MAESTRO:
            maestro, probes, deck = _prepare_saved_maestro(
                config, extras, base, mark, monitor, profile_id, target, commands)
        imported, frequency, measurement, revision, extra = _stage_task_files(
            mark, monitor, profile_id, target, commands, extras, saved, kind, updating, staging, maestro)
        if kind == MAESTRO:
            # Maestro's circuit part and the export the task is generated from must be the same circuit.
            exported = Path(imported['netlist_path']).read_text()
            if working_copy.structure(deck['circuit']) != working_copy.structure(exported):
                raise ProfileError('Maestro netlists the working copy differently from its schematic export: look at the copy in '
                                   'Virtuoso, then save again')
            extra['maestro_deck_sha256'] = deck['sha256']
            # The network's result registry: exactly the task's outputs, each with the scale its spec normalizes by.
            extra['spec_registry'] = _spec_registry(config, deck, probes)
        result = write_profile_files(name, config, recipe=kind, imported=imported, staging=staging, expected_frequency_hz=frequency, entry_extra=extra)
        if kind == MAESTRO:
            write_json(staging / FILES['maestro_deck'], {k: v for k, v in deck.items() if k != 'circuit'})
        data = _write_saved_task_record(
            name, revision, extra, target, measurement, maestro, result, config, extras, saved, imported, staging)
        changed, baseline_kept = _publish_task_revision(
            updating, name, current, saved, data, staging, directory, kind)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if not updating and directory.exists() and not (directory / TASK_FILE).is_file():
            shutil.rmtree(directory, ignore_errors=True)
        if claimed:
            working_copy.release(*claimed, name)
        raise
    return dict(task_key=f'real:{name}', name=name, revision=revision, measurement=measurement, runnable=True,
                copy=target['copy'], original=target['original'], directory=str(directory), created=not updating,
                baseline_kept=baseline_kept, changed=sorted(changed), circuit_class=result['entry']['circuit_class'],
                pdk_id=result['entry']['pdk_id'], parameters=[row.model_dump(mode='json') for row in result['rows']],
                maestro_matches=None if maestro is None else True)


def _save_target(updating, current, task, mark, monitor, profile_id, name, commands, library, cell) -> tuple:
    """Choose the existing task copy, clone it for Save as, or claim the cell copy for its first save."""
    claimed = None
    if updating:
        target = current['copy_target']
    elif current:
        if not current.get('copy_target'):
            raise ProfileError(f'real:{task} was made before tasks had working copies: read its cell in the Virtuoso window (confirming '
                               'that it is a copy you made) and save a new task')
        mark('copy')
        target = working_copy.make_task_copy(monitor, profile_id, current['copy_target'], name,
                                             source_netlist=(Path(current['directory']) / FILES['structure']).read_text(),
                                             command=commands.get('copy'))
    else:
        target = _first_save_target(library, cell, name)
        claimed = (library, cell)
    return target, claimed


def _prepare_saved_maestro(config, extras, base, mark, monitor, profile_id, target, commands) -> tuple:
    """Write and verify the working copy Maestro setup, then obtain its measurement probes and exported deck."""
    setup = _maestro_setup(config, extras, base)
    mark('setup')
    written = working_copy.write_setup_on(monitor, profile_id, target, setup, command=commands.get('setup'))
    if not written['matches']:
        raise ProfileError('The copy\'s Maestro setup reads back differently from the rows: ' + '; '.join(written['differences']))
    maestro = virtuoso_setup.normalize(written)
    # Maestro's own deck of the test, netlisted once: every evaluation runs it around the circuit it exports,
    # and OCEAN measures the outputs with their signal names translated by Maestro's own name maps.
    probes, outputs = _maestro_outputs(config, maestro)
    mark('deck')
    deck = working_copy.maestro_deck_on(monitor, profile_id, target, outputs, command=commands.get('deck'))
    return maestro, probes, deck


def _stage_task_files(
    mark, monitor, profile_id, target, commands, extras, saved, kind, updating, staging, maestro) -> tuple:
    """Read the working copy back into the workbench and initialize the revision staging directory and metadata."""
    mark('read')
    bridge_read.read(monitor, profile_id, 'import_cell', library=target['copy']['library'], cell=target['copy']['cell'],
                     testbench=target['copy']['testbench'], command=commands.get('read'))
    mark('files')
    imported = native_cells.load_import(target['copy']['library'], target['copy']['cell'])
    if imported is None:
        raise ProfileError('The working copy could not be read back into the workbench')
    frequency = extras.get('expected_frequency_hz', ((saved or {}).get('measurement') or {}).get('expected_frequency_hz'))
    measurement = dict(kind=kind, **({'expected_frequency_hz': float(frequency)} if kind == 'ring_oscillator' and frequency else {}))
    revision = (saved or {}).get('revision', 0) + 1 if updating else 1
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    extra = dict(original=target['original'], copy=target['copy'], copy_target=target, revision=revision,
                 measurement=kind, runnable=True, saved_utc=utcnow().isoformat())
    if kind == MAESTRO:
        extra['provided_metrics'] = [o['name'] for o in maestro['outputs']]
    return imported, frequency, measurement, revision, extra


def _write_saved_task_record(
    name, revision, extra, target, measurement, maestro, result, config, extras, saved, imported, staging):
    """Build and write the task record from the verified working copy, editor rows, and generated profile."""
    data = task_files.build(
        name=name, revision=revision, saved_utc=extra['saved_utc'], cell=target['original'], copy=target['copy'],
        measurement=measurement,
        maestro=None if maestro is None else dict(test=maestro['test'], model_files=maestro['model_files'], analyses=maestro['analyses'],
                                                  variables=maestro['variables'], bindings=maestro['bindings'],
                                                  initial_conditions=maestro['initial_conditions'],
                                                  outputs=maestro['outputs'], specs=maestro['specs']),
        parameters=[row.model_dump(mode='json', exclude_none=True) for row in result['rows']],
        probes=[m.model_dump(mode='json', exclude_none=True) for m in config.measurements],
        specs=[t.model_dump(mode='json', exclude_none=True) for t in config.targets],
        notes=extras.get('notes', (saved or {}).get('notes', '')),
        virtuoso=dict(copy_netlist_sha256=imported['netlist_sha256'],
                      maestro_fingerprint=virtuoso_setup.fingerprint(maestro) if maestro else None))
    write_json(staging / TASK_FILE, data)
    return data


def _publish_task_revision(updating, name, current, saved, data, staging, directory, kind) -> tuple:
    """Replace the saved revision, publish its staging directory, and check the resulting real-backend profile."""
    changed, baseline_kept = set(), False
    if updating:
        changed, baseline_kept = _replace_revision(name, current, saved, data, staging)
    staging.rename(directory)
    try:
        load_profile(name).check_deck() if kind == MAESTRO else load_profile(name)   # every check of the verified classes
    except Exception as exc:
        raise ProfileError(f'The task does not pass the checks of the real backend: {exc}')
    return changed, baseline_kept


def _saveable(name, config, task, as_new, run_rows, replace_newer, base_revision) -> tuple:
    """The checks of save_task before anything is written: the name, the task it updates (none running), a name
    still free for a new one, every spec judging Probes the task has, rows not older than the saved task (NewerSaved).
    Returns (the task's folder, the entry of the open task or None, whether the save updates it)."""
    directory = profile_dir(name)                                # validates the name
    current = profile_entry(task) if task else None
    if task and current is None:
        raise ProfileError(f'Unknown task real:{task}')
    updating = current is not None and not as_new
    if updating:
        if name != task:
            raise ProfileError('Save task keeps the task name: use Save as for a task under another name')
        working = working_run_of(name, run_rows)
        if working is not None:
            raise ProfileError(f'Run {working.get("run_id") or working["run_dir"]} of real:{name} is working right now: let it finish first')
        if not current.get('copy_target'):
            raise ProfileError(f'real:{name} was made before tasks had working copies: read its cell in the Virtuoso window (confirming '
                               'that it is a copy you made) and save a new task')
    elif name in REAL_PROFILES or f'real:{name}' in REMOVED_REAL_TASKS or directory.exists():   # a removed one's name stays reserved
        raise ProfileError(f'A task called real:{name} already exists: choose another name')
    # a spec must judge Probes the task has (the editors' check)
    probes, refused = {m.measurement_id: m for m in config.measurements}, []
    for spec in config.targets:
        check_equation(spec, spec.metric_id, report := Report(), probes)
        refused += [f'Spec {spec.metric_id}: {issue.message}' for issue in report.issues if issue.level == 'error']
    if refused:
        raise ProfileError(' '.join(refused))
    if updating and not replace_newer:
        undone = undone_by_saving(config, name, task_file(name), base=base_revision)
        if undone:
            raise NewerSaved(describe_undone(name, undone) + ' Press Reload saved values to take the saved rows, or save anyway.',
                             undone)
    return directory, current, updating


def _first_save_target(library, cell, name):
    """The first save from a cell: the cell (one with no task yet) becomes the task's working copy, claimed for it."""
    if not library or not cell:
        raise ProfileError('Say which cell the task is of')
    existing = [t for t in tasks_for_cell(library, cell)]
    if existing:
        raise ProfileError(f'{library}/{cell} already has the task(s) {", ".join(t["task_key"] for t in existing)}: open one and use Save as')
    target = working_copy.draft_target(library, cell)
    working_copy.claim(library, cell, name)
    return target


def _maestro_setup(config, extras, base):
    """What Save task writes into the working copy's Maestro test: the rows' outputs and specs; the model files,
    analyses, variables, bindings and initial conditions sent with this save, else those the copy was last written
    with (`base`)."""
    setup = virtuoso_setup.from_rows(config, model_files=extras.get('model_files') or base.get('model_files') or (),
                                     analyses=extras['analyses'] if 'analyses' in extras else base.get('analyses'),
                                     variables=extras['variables'] if 'variables' in extras else base.get('variables'),
                                     bindings=extras['bindings'] if 'bindings' in extras else base.get('bindings'),
                                     initial_conditions=(extras['initial_conditions'] if 'initial_conditions' in extras
                                                         else base.get('initial_conditions')))
    return setup


def _maestro_outputs(config, maestro) -> tuple:
    """(the Probes rows by their Maestro output name, the outputs Maestro's deck is netlisted to measure)."""
    probes = {m.source_name: m for m in config.measurements if m.result_source == 'ade_output'}
    outputs = [dict(name=o['name'], expression=o['expression'], analysis=probes[o['name']].analysis if o['name'] in probes
                    else virtuoso_setup.analysis_of(o['expression']), unit=probes[o['name']].unit if o['name'] in probes else '1')
               for o in maestro['outputs']]
    return probes, outputs


def _spec_registry(config, deck, probes):
    """The result registry of a Maestro-measured task: exactly its outputs, each with the scale its spec normalizes by."""
    by_probe = {t.equation.strip(): t for t in config.targets}
    registry = []
    for output in deck['outputs']:
        probe = probes.get(output['name'])
        spec = by_probe.get(probe.measurement_id) if probe is not None else None
        scale = units.scale_to_canonical(normalization_scale(spec), spec.unit) if spec is not None else 1.0
        registry.append(dict(metric_id=output['name'], unit=units.canonical_unit(output['unit']) if units.known(output['unit'])
                             else output['unit'], reference=abs(float(scale)) or 1.0))
    return registry


def _replace_revision(name, current, saved, data, staging) -> tuple:
    """A new revision of an open task: the old folder's files kept under history/r<N>/ in the new one, the recorded
    baseline kept when nothing it depends on changed, the old folder moved aside. Returns (what changed, whether the
    baseline was kept)."""
    changed, baseline_kept = set(), False
    old = Path(current['directory'])
    history = staging / HISTORY
    if (old / HISTORY).is_dir():
        shutil.copytree(old / HISTORY, history)
    keep = history / f'r{saved.get("revision", 0) if saved else 0}'
    keep.mkdir(parents=True, exist_ok=True)
    for item in old.iterdir():
        if item.is_file():
            shutil.copy2(item, keep / item.name)
    changed = task_files.what_changed(saved, data)
    if (old / FILES['reference']).is_file() and not changed & task_files.BASELINE_PARTS:
        shutil.copy2(old / FILES['reference'], staging / FILES['reference'])
        baseline_kept = True
        entry = json.loads((staging / FILES['entry']).read_text())
        write_json(staging / FILES['entry'], dict(entry, status=current.get('status', entry['status']),
                                                  baseline_recorded_utc=current.get('baseline_recorded_utc')))
    aside = old.parent / TRASH / f'{name}.r{saved.get("revision", 0) if saved else 0}.{utcnow().strftime(TRASH_STAMP)}'
    aside.parent.mkdir(parents=True, exist_ok=True)
    old.rename(aside)
    return changed, baseline_kept
