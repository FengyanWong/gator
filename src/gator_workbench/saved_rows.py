"""A configuration's rows against its saved task: which saved task a configuration runs, which rows differ and how to say
it, and whether saving would undo what was saved since (rows older than the saved task, record 7.203). Local file
reads only: no Virtuoso.

Moved from consistency.py by the refactoring (docs/plan-refactoring.md): validation checks every edit against the
saved task, and importing the live check (Virtuoso, profiles) for that closed an import cycle. consistency.py
re-exports every name.
"""
from __future__ import annotations

import json

from pydantic import ValidationError
from . import caches, profile_store, units
from .diffs import structured_diff
from .profile_store import HISTORY, ProfileError, TASK_FILE, profile_dir
from .schema import MeasurementDefinition, OptimizationParameter, PerformanceTarget
from .storage.atomic import UNREADABLE, read_json_quiet


# (configuration key, editor name, row ID field, task file part)
SECTIONS = (('parameters', 'Parameters', 'variable_id', 'parameters'), ('measurements', 'Probes', 'measurement_id', 'probes'),
            ('targets', 'Specs', 'metric_id', 'specs'))
# The page's words (record 7.376): its one save button is Save as, a new task (record 7.246); Reload saved values opens
# from "not saved" beside the task's name (record 7.372).
FIX_ROWS = ('Press Save as to keep these rows as a new task, or Reload saved values (under "not saved", beside the task\'s '
            'name) to take the saved rows back.')
# The rows are older than the saved task (record 7.203): saving them would undo what was saved since.
# Save as makes a new task: it undoes nothing of the saved one (only an update of the task itself would, and it asks first).
FIX_NEWER = ('These rows are older than the saved task: it was saved again (revision {current}) after they were loaded '
             '(revision {base}). Press Reload saved values (under "not saved", beside the task\'s name) to take the saved '
             'rows; Save as keeps these rows as a new task and leaves the saved one as it is.')


def saved_task(config, *, with_entry=True):
    """(name, list entry, task file) of the saved task a configuration runs, or None: MOCK, a built-in circuit, a cell
    read from Virtuoso, or a task made before task files (Create profile). The task file is one file read (static
    validation asks on every edit); `with_entry=False` skips the task list and gives None for the entry."""
    circuit = config.circuit
    if circuit.source != 'registered_task' or not (circuit.task_id or '').startswith('real:'):
        return None
    name = circuit.task_id[len('real:'):]
    saved = profile_store.task_file(name)
    if saved is None or not with_entry:
        return None if saved is None else (name, None, saved)
    entry = profile_store.profile_entry(name)
    return None if entry is None else (name, entry, saved)


# The fields that hold a number in their row's unit: written as the editors write them (record 7.208: 1.3 GHz, 400 uA).
QUANTITY_FIELDS = dict(parameters=('lower', 'upper', 'step', 'initial_value'), targets=('lower', 'upper', 'normalization_scale'))


def _brief(value, unit=None) -> str:
    if value is None:
        return '(none)'
    if unit is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
        return units.text(value, unit)
    if isinstance(value, float):
        return format(value, '.6g')                                  # 1.3e+09, not 1300000000.0
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 40 else text[:37] + '...'


def row_differences(config, saved) -> dict:
    """{configuration key: [plain sentences]} for each editor whose rows differ from the task file `saved`. Rows are
    compared as the schema reads them, so a field shown with its default equals one left out."""
    models = dict(parameters=OptimizationParameter, measurements=MeasurementDefinition, targets=PerformanceTarget)
    normal = lambda model, row: model.model_validate(row if isinstance(row, dict) else row.model_dump()).model_dump(mode='json', exclude_none=True)
    found = {}
    for section, _label, key, part in SECTIONS:
        now = [normal(models[section], row) for row in getattr(config, section)]
        try:
            kept = [normal(models[section], row) for row in saved.get(part) or []]
        except ValidationError as exc:
            found[section] = [f'the saved rows no longer read with this workbench ({exc.errors()[0]["msg"]}): save the task again']
            continue
        if now == kept:
            continue
        unit_of = {row.get(key): row.get('unit') for row in kept + now}
        in_unit = lambda item, field, value: _brief(value, unit_of.get(item['key']) if field in QUANTITY_FIELDS.get(section, ()) else None)
        lines = []
        for item in structured_diff({section: kept}, {section: now}):
            if item['change'] == 'added':
                lines.append(f'{item["key"]} is here but not saved')
            elif item['change'] == 'removed':
                lines.append(f'{item["key"]} is saved but not here')
            else:
                fields = ', '.join(f'{f["field"]} {in_unit(item, f["field"], f["after"])} here, {in_unit(item, f["field"], f["before"])} saved'
                                   for f in item['fields'][:3])
                more = len(item['fields']) - 3
                lines.append(f'{item["key"]}: {fields}' + (f' (and {more} more)' if more > 0 else ''))
        found[section] = lines or ['the same rows, in another order']
    return found


def describe_rows(section, lines, *, name, revision) -> str:
    label = next(label for key, label, _i, _p in SECTIONS if key == section)
    shown = '; '.join(lines[:4]) + (f'; and {len(lines) - 4} more' if len(lines) > 4 else '')
    return f'{label} differ from the saved task real:{name} (revision {revision}): {shown}.'


# ---------------------------------------------------------------------- rows older than the saved task (record 7.203)
# On 2026-10-05 a page that still held the rows of revision 2 of mscr_ldo2_rgcn pressed Save task twice: it stored those
# rows over revision 3 and took out the Scale 6 that revision had added (record 7.194). Save task now asks first.
_FILES: dict = {}                                    # (path, mtime, size) -> the parsed task file: the history never changes


def _read_json(path):
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _FILES:
        data = read_json_quiet(path, UNREADABLE)
        if data is UNREADABLE:
            return None
        if len(_FILES) > 256:
            _FILES.clear()
        _FILES[key] = data
    return _FILES[key]


def revision_file(name, revision) -> dict | None:
    """The task file of revision `revision` of real:<name>: the current one, or the copy kept in history/r<N>/."""
    try:
        folder = profile_dir(name)
    except ProfileError:
        return None
    for path in (folder / TASK_FILE, folder / HISTORY / f'r{revision}' / TASK_FILE):
        data = _read_json(path)
        if isinstance(data, dict) and data.get('revision') == revision:
            return data
    return None


def _models():
    return dict(parameters=OptimizationParameter, measurements=MeasurementDefinition, targets=PerformanceTarget)


def _rows(rows_of_section) -> dict | None:
    """{section: {row ID: the row as the schema reads it}} - as `row_differences` compares rows. None: rows this
    workbench no longer reads."""
    models, out = _models(), {}
    try:
        for section, _label, key, _part in SECTIONS:
            out[section] = {}
            for row in rows_of_section(section) or []:
                normal = models[section].model_validate(row if isinstance(row, dict) else row.model_dump())
                out[section][getattr(normal, key)] = normal.model_dump(mode='json', exclude_none=True)
    except ValidationError:
        return None
    return out


def _file_rows(data):
    parts = {section: part for section, _label, _key, part in SECTIONS}
    return None if not isinstance(data, dict) else _rows(lambda section: data.get(parts[section]))


def unsaved_rows(config, saved) -> dict | None:
    """The editors' rows that differ from the task file `saved`, row by row: what the editors mark as not saved (record
    7.222, user: "highlight the rows that are unsaved"). Per section: the IDs of the rows here that are not saved
    (`added`), of the saved rows not here (`removed`), the rows that differ (`changed`: the saved value of each field that
    differs, and the saved row's unit to write it in), and whether the same rows stand in another order (`reordered`).
    Compared as `row_differences` compares rows, so a field shown with its default equals one left out. None: the saved
    rows no longer read with this workbench."""
    here, kept = _rows(lambda section: getattr(config, section)), _file_rows(saved)
    if here is None or kept is None:
        return None
    sections = {}
    for section, _label, _key, _part in SECTIONS:
        now, then = here[section], kept[section]
        changed = {row_id: dict(fields={field: then[row_id].get(field) for field in sorted({*row, *then[row_id]})
                                        if row.get(field) != then[row_id].get(field)}, unit=then[row_id].get('unit'))
                   for row_id, row in now.items() if row_id in then and row != then[row_id]}
        sections[section] = dict(added=[row_id for row_id in now if row_id not in then],
                                 removed=[row_id for row_id in then if row_id not in now], changed=changed,
                                 reordered=[row_id for row_id in now if row_id in then] != [row_id for row_id in then if row_id in now])
    return dict(revision=saved.get('revision'), sections=sections)


def undone_by_saving(config, name, saved, base=None) -> dict | None:
    """What "Save task" with the editors' rows would UNDO of the saved task real:<name>: what was saved after the
    revision the rows came from. That revision is the newest earlier one whose rows are exactly the editors' (the rows of
    a page that missed a later save, or brought back by Undo), else `base` - the revision the page noted when it loaded
    the task's rows or saved them. None when nothing would be undone: the rows came from the saved revision, already
    hold what was saved since, or their origin cannot be told (no `base`, and edits on top of an earlier revision).
    Per row ID, against that revision: a field changed since that the rows here still have as before; a row added or
    changed since that the rows here lack; a row removed since that the rows here still have."""
    current = (saved or {}).get('revision')
    if not isinstance(current, int) or current < 2:
        return None
    here, now = _rows(lambda section: getattr(config, section)), _file_rows(saved)
    if here is None or now is None or here == now:
        return None
    origin = next((revision for revision in range(current - 1, 0, -1) if _file_rows(revision_file(name, revision)) == here), None)
    then = here
    if origin is None:
        if not isinstance(base, int) or not 1 <= base < current:
            return None
        origin, then = base, _file_rows(revision_file(name, base))
        if then is None:
            return None
    items = []
    for section, _label, _key, _part in SECTIONS:
        before_rows, saved_rows, rows = then[section], now[section], here[section]
        for row_id in dict.fromkeys([*before_rows, *saved_rows]):
            before, after, row = before_rows.get(row_id), saved_rows.get(row_id), rows.get(row_id)
            if before == after or row == after:
                continue                                         # not changed since, or the rows here hold it already
            if after is None:
                if row is not None:
                    items.append(dict(section=section, row=row_id, change='back'))
            elif row is None:
                items.append(dict(section=section, row=row_id, change='removed'))
            else:
                for field in sorted(set(before or {}) | set(after)):
                    if (before or {}).get(field) != after.get(field) and row.get(field) != after.get(field):
                        items.append(dict(section=section, row=row_id, change='field', field=field, saved=after.get(field),
                                          here=row.get(field), unit=after.get('unit')))
    return dict(base=origin, current=current, items=items) if items else None


def undone_lines(undone) -> list[str]:
    labels = {section: label for section, label, _key, _part in SECTIONS}
    out = []
    for item in undone['items']:
        where = f'{labels[item["section"]]} {item["row"]}'
        if item['change'] == 'field':
            unit = item.get('unit') if item['field'] in QUANTITY_FIELDS.get(item['section'], ()) else None
            out.append(f'{where}: {item["field"]} {_brief(item["saved"], unit)} saved, {_brief(item["here"], unit)} here')
        elif item['change'] == 'removed':
            out.append(f'{where} is saved but not here')
        else:
            out.append(f'{where} was taken out of the saved task but is still here')
    return out


def describe_undone(name, undone) -> str:
    lines = undone_lines(undone)
    shown = '; '.join(lines[:4]) + (f'; and {len(lines) - 4} more' if len(lines) > 4 else '')
    return (f'real:{name} was saved again after these rows were loaded: it is revision {undone["current"]} now, the rows here '
            f'are revision {undone["base"]}\'s. Saving them would undo what was saved since: {shown}.')


# The caches of this module: caches.clear_all() empties them with every other one (refactoring package B10).
caches.register(globals(), '_FILES')
