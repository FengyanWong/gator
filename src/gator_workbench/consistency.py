"""The check before every run of a saved task (Virtuoso task flow, part 4).

The user asked for "frontend backend and virtuoso side consistency" (2026-09-21). A run runs exactly one saved task
on its working copy, so three sides must say the same thing before any costed simulation:

1. the rows of the three editors (Parameters, Probes, Specs) and the saved task file (``task.json``) - offline. Static
   validation says it while you edit (``task_not_saved``, blocking), so Start is not even offered on a difference;
2. the saved task and its working copy in Virtuoso: the run adapter connects (creation receipt, no ADE/Maestro window,
   the copy still has the recorded sizes), Virtuoso exports the testbench netlist and the export is compared with the
   recorded topology and every parameter, and the deck is written without simulating (``profile_preflight``);
3. a task measured by Maestro: the copy's Maestro test, read back, against the task file's ``maestro`` part.

Start, "Baseline simulation" and Resume run parts 2 and 3 right after the connection gate
(``runs.prepare_run``) and create nothing on a difference; "Check now" in the task's block runs all three on its own.
Read-only, no simulation, no budget. It replaces "Check against Virtuoso", which was part 2 alone.

Not compared (yet): the user's own cell against the working copy. A copy is made once; a change of the cell after it
is not taken over.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from .security import redact
from .storage.dataset import utcnow

# (configuration key, editor name, row ID field, task file part)
SECTIONS = (('parameters', 'Parameters', 'variable_id', 'parameters'), ('measurements', 'Probes', 'measurement_id', 'probes'),
            ('targets', 'Specs', 'metric_id', 'specs'))
FIX_ROWS = 'Press Save task to save the rows as they are now, or Reload saved values to take the saved rows back.'
# The rows are older than the saved task (record 7.203): saving them would undo what was saved since.
FIX_NEWER = ('These rows are older than the saved task: it was saved again (revision {current}) after they were loaded '
             '(revision {base}). Press Reload saved values to take the saved rows; Save task would undo that change, and asks '
             'first.')
FIX_COPY = ('The working copy was changed in Virtuoso after the task was saved: press Save task to take the copy as it is '
            'now, or undo the change in Virtuoso.')
# Another real run or check holds the run adapter's session lock (record 7.207): nothing is wrong with the task.
FIX_BUSY = ('Nothing in the task or its working copy needs changing: check again when that run has ended. A run started '
            'from this page stops with Abort; one started from a command line stops there.')
TITLES = dict(
    editors='The editors hold the rows of the saved task',
    profile='The task\'s files pass the checks of the real backend',
    connect='The run adapter reaches the working copy: its creation record matches, no ADE/Maestro window is open on it, '
            'and it still has the recorded sizes',
    export='The netlist Virtuoso exports from the working copy matches the saved task: topology and every parameter',
    deck='The simulation deck is written (not run)',
    close='The run adapter let go of the working copy',
    maestro='The working copy\'s Maestro test says what the task says: outputs, specs, analyses, variables, bindings',
    gate='The connection allows the check',
    connection='A connection is chosen',
    busy='No other real run is using Virtuoso')
FAILED = dict(
    editors='The editors differ from the saved task',
    profile='The task\'s files do not pass the checks of the real backend',
    connect='The run adapter could not use the working copy',
    export='The working copy in Virtuoso differs from the saved task',
    deck='The simulation deck could not be written',
    close='The run adapter did not let go of the working copy cleanly',
    maestro='The working copy\'s Maestro test differs from the task',
    gate='The connection gate blocked the check',
    connection='No connection is chosen',
    busy='Another real run is using Virtuoso, so the working copy could not be checked')
# What a holder of the session lock is, by its command line: the page's run worker, a command-line run, a Corner check,
# another check (profile_preflight). `lock_holder` names the process that started a multiprocessing lane.
_HOLDERS = (('gator_workbench.worker', 'a run started from a workbench page'), ('gator_workbench.cli run', 'a run started from a command line'),
            ('gator_workbench.corner_check', 'a Corner check'), ('gator_workbench.profile_preflight', 'another check or a run\'s start check'))


def saved_task(config, *, with_entry=True):
    """(name, list entry, task file) of the saved task a configuration runs, or None: MOCK, a built-in circuit, a cell
    read from Virtuoso, or a task made before task files (Create profile). The task file is one file read (static
    validation asks on every edit); `with_entry=False` skips the task list and gives None for the entry."""
    circuit = config.circuit
    if circuit.source != 'registered_task' or not (circuit.task_id or '').startswith('real:'):
        return None
    from . import profiles
    name = circuit.task_id[len('real:'):]
    saved = profiles.task_file(name)
    if saved is None or not with_entry:
        return None if saved is None else (name, None, saved)
    entry = profiles.list_profiles().get(name)
    return None if entry is None else (name, entry, saved)


# The fields that hold a number in their row's unit: written as the editors write them (record 7.208: 1.3 GHz, 400 uA).
QUANTITY_FIELDS = dict(parameters=('lower', 'upper', 'step', 'initial_value'), targets=('lower', 'upper', 'normalization_scale'))


def _brief(value, unit=None) -> str:
    if value is None:
        return '(none)'
    if unit is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
        from . import units
        return units.text(value, unit)
    if isinstance(value, float):
        return format(value, '.6g')                                  # 1.3e+09, not 1300000000.0
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 40 else text[:37] + '...'


def row_differences(config, saved) -> dict:
    """{configuration key: [plain sentences]} for each editor whose rows differ from the task file `saved`. Rows are
    compared as the schema reads them, so a field shown with its default equals one left out."""
    from .agents.proposals import structured_diff
    from .schema import MeasurementDefinition, OptimizationParameter, PerformanceTarget
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
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if len(_FILES) > 256:
            _FILES.clear()
        _FILES[key] = data
    return _FILES[key]


def revision_file(name, revision) -> dict | None:
    """The task file of revision `revision` of real:<name>: the current one, or the copy kept in history/r<N>/."""
    from .profiles import HISTORY, TASK_FILE, ProfileError, profile_dir
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
    from .schema import MeasurementDefinition, OptimizationParameter, PerformanceTarget
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


def _step(step, ok, *, detail=None, fix=None, **more) -> dict:
    return dict(step=step, ok=ok, title=TITLES[step] if ok else FAILED[step], detail=detail, **({} if ok else dict(fix=fix)), **more)


def editors_step(config, name, saved) -> dict:
    differences = row_differences(config, saved)
    if not differences:
        return _step('editors', True, detail=f'Parameters, Probes and Specs are those of revision {saved.get("revision")}.')
    return _step('editors', False, fix=FIX_ROWS, detail=' '.join(describe_rows(section, lines, name=name, revision=saved.get('revision'))
                                                                  for section, lines in differences.items()))


def _gate_step(exc) -> dict:
    gate = getattr(exc, 'gate', None) or {}
    layers = ', '.join([*(gate.get('blocking') or []), *(gate.get('uncertain') or [])]) or gate.get('status') or 'unknown'
    return _step('gate', False, detail=f'{exc} ({layers}).', fix='Bring the link up in the Connection window, then check again.')


def lock_holder(path) -> str | None:
    """Who holds the flock on `path` (the run adapter's session lock), read from /proc/locks WITHOUT taking the lock: a
    probe that took it, even shared, would make a real run that connects at that moment fail. "a run started from a
    command line (process 123, started 18:49: python -m gator_workbench.cli run ...)", or None: nobody, or not Linux."""
    import os
    from datetime import datetime
    from pathlib import Path
    proc = lambda pid, part: Path(f'/proc/{pid}/{part}')
    try:
        stat = Path(path).stat()
        key = f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}:{stat.st_ino}'
        # "19: FLOCK  ADVISORY  WRITE 3034112 08:30:143825 0 EOF"; a process waiting for the lock has "->" before its type
        pids = [int(f[f.index(key) - 1]) for f in map(str.split, Path('/proc/locks').read_text().splitlines()) if key in f and '->' not in f]
        if not pids:
            return None
        pid = pids[0]
        for _ in range(3):                                         # a lane of a run: name the process that started it
            argv = [a for a in proc(pid, 'cmdline').read_bytes().decode(errors='replace').split('\0') if a]
            if not any('multiprocessing' in a for a in argv):
                break
            pid = int(proc(pid, 'stat').read_text().rsplit(')', 1)[1].split()[1])
        fields = proc(pid, 'stat').read_text().rsplit(')', 1)[1].split()     # fields[0] is field 3 of proc(5): state
        boot = next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
        started = datetime.fromtimestamp(boot + int(fields[19]) / os.sysconf('SC_CLK_TCK')).strftime('%H:%M')
    except (OSError, ValueError, IndexError, StopIteration):
        return None
    command = ' '.join([Path(argv[0]).name, *argv[1:]]) if argv else '?'
    kind = next((label for marker, label in _HOLDERS if marker in command), 'a process')
    return redact(f'{kind} (process {pid}, started {started}: {command}', 300) + ')'


def _busy_step(reason=None) -> dict:
    """Another real run or check holds the adapter's session lock: only one process drives the Virtuoso cell at a time."""
    from .paths import bridge_state_dir
    lock = bridge_state_dir() / 'session.lock'
    holder = lock_holder(lock) or f'another process ({reason or "it did not say which"})'
    return _step('busy', False, fix=FIX_BUSY, detail=f'The run adapter\'s session lock ({lock}) is held by {holder}. Only one real '
                 'run or check works on Virtuoso at a time; nothing was read from it.')


def _connect_fix(detail) -> str:
    text = (detail or '').lower()
    if 'ade/maestro window' in text:
        return 'Close those ADE/Maestro windows in Virtuoso (the run exports through OCEAN, which they block), then check again.'
    if 'tunnel' in text:
        return 'Bring the link up in the Connection window, then check again.'
    if 'creation receipt' in text or 'receipt' in text:
        return 'The task\'s files and its creation record disagree: save the task again (Save task).'
    return FIX_COPY


def copy_steps(monitor, profile_id, name, entry, saved, *, acknowledge_unknown=False, commands=None) -> list:
    """Parts 2 and 3: the saved task against its working copy in Virtuoso. Read-only; each step says what it found."""
    from . import profile_preflight, profiles, working_copy
    from .virtuoso_setup import differences
    from .paths import bridge_state_dir
    commands = commands or {}
    if lock_holder(bridge_state_dir() / 'session.lock'):           # record 7.207: the adapter could not take the lock
        return [_busy_step()]
    try:
        result = profile_preflight.preflight(monitor, name, profile_id, acknowledge_unknown=acknowledge_unknown,
                                             command=commands.get('preflight'))
    except PermissionError as exc:
        return [_gate_step(exc)]
    except Exception as exc:                                       # timeout, no answer: the check itself could not run
        return [_step('connect', False, detail=redact(f'{type(exc).__name__}: {exc}', 600), fix='Try again; if it persists, '
                      'use "Test" in the Connection window.')]
    steps = []
    for item in result['steps']:
        step = item['step'] if item['step'] in TITLES else 'connect'
        if step == 'connect' and not item['ok'] and (item.get('detail') or '').startswith('BlockingIOError'):
            steps.append(_busy_step(item.get('detail')))           # taken between the look above and the connect
        elif item['ok']:
            steps.append(_step(step, True, detail=item.get('detail'), **({'skipped': True} if item.get('skipped') else {})))
        else:
            fix = (_connect_fix(item.get('detail')) if step == 'connect' else FIX_COPY if step == 'export'
                   else 'Save the task again (Save task).' if step == 'profile' else 'See the reason; then check again.')
            steps.append(_step(step, False, detail=item.get('detail'), fix=fix))
    if entry.get('recipe') == profiles.MAESTRO and all(s['ok'] for s in steps):
        expected = saved.get('maestro') or {}
        try:
            found = working_copy.read_setup_on(monitor, profile_id, entry['copy_target'], acknowledge_unknown=acknowledge_unknown,
                                               command=commands.get('setup'))
        except PermissionError as exc:
            steps.append(_gate_step(exc))
            return steps
        except Exception as exc:
            steps.append(_step('maestro', False, detail=redact(f'{type(exc).__name__}: {exc}', 600), fix='Try again.'))
            return steps
        told = ['the working copy has no Maestro test GATOR any more'] if not found.get('test') else differences(expected, found)
        steps.append(_step('maestro', True, detail='Read back from the working copy: it matches the task file.') if not told else
                     _step('maestro', False, detail='; '.join(told[:8]) + (f'; and {len(told) - 8} more' if len(told) > 8 else ''),
                           fix='Press Save task: it writes the task\'s setup into the copy again. If the change in Maestro is what '
                               'you want instead: Read setup, Use in editors, then Save task.'))
    return steps


def check(monitor, profile_id, config, *, rows=True, acknowledge_unknown=False, commands=None) -> dict:
    """The whole check of the saved task `config` runs. `rows=False`: the rows were compared already (static
    validation, before a start). Raises KeyError when the configuration runs no saved task."""
    found = saved_task(config)
    if found is None:
        raise KeyError('Only a task saved with "Save task" is checked: open one under Source: Registered task')
    name, entry, saved = found
    steps = [editors_step(config, name, saved)] if rows else []
    if not profile_id:
        steps.append(_step('connection', False, detail='Nothing was read from Virtuoso.', fix='Choose a connection in the Connection window.'))
    else:
        steps += copy_steps(monitor, profile_id, name, entry, saved, acknowledge_unknown=acknowledge_unknown, commands=commands)
    return dict(consistency_check=True, task=f'real:{name}', revision=saved.get('revision'), ok=all(s['ok'] for s in steps),
                steps=steps, simulated=False, checked_utc=utcnow().isoformat())


def summary(result) -> str:
    """One sentence for a refused start: what differs first, and what to do."""
    failed = [s for s in result['steps'] if not s['ok']]
    if not failed:
        return f'{result["task"]} is consistent.'
    first = failed[0]
    return ' '.join(filter(None, [f'Not started: {first["title"][0].lower()}{first["title"][1:]}.', first['detail'], first['fix']]))
