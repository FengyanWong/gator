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


from .connection import named_or_active
from .paths import bridge_cell_lock, bridge_session_lock
from .security import redact
from .storage.dataset import utcnow
from .virtuoso_setup import differences
# re-exported: moved to saved_rows.py by the refactoring (docs/plan-refactoring.md)
from .saved_rows import (SECTIONS, FIX_ROWS, FIX_NEWER, saved_task, QUANTITY_FIELDS, _brief, row_differences,
                         describe_rows, _FILES, _read_json, revision_file, _models, _rows, _file_rows, unsaved_rows,
                         undone_by_saving, undone_lines, describe_undone)

FIX_COPY = ('The working copy was changed in Virtuoso after the task was saved: undo the change in Virtuoso, or press Save '
            'as to make a new task from the copy as it is now.')
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


def _step(step, ok, *, detail=None, fix=None, **more) -> dict:
    return dict(step=step, ok=ok, title=TITLES[step] if ok else FAILED[step], detail=detail, **({} if ok else dict(fix=fix)), **more)


def editors_step(config, name, saved) -> dict:
    """Report whether the Parameters, Probes, and Specs rows match the saved task revision."""
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


def _busy_step(reason=None, locks=None) -> dict:
    """Another real run or check holds the lock of the task's Virtuoso session, or of its cell: one process at a time
    drives a Virtuoso session, and one works on a cell whatever the session (record 7.311)."""
    session, cell = locks or (bridge_session_lock(), None)
    if cell is not None and not lock_holder(session) and (lock_holder(cell) or 'is in use by another run' in (reason or '')):
        holder = lock_holder(cell) or f'another process ({reason})'
        return _step('busy', False, fix=FIX_BUSY, detail=f'The cell\'s lock ({cell}) is held by {holder}, working on this cell through '
                     'another Virtuoso session. Only one real run or check works on a cell at a time; nothing was read from it.')
    holder = lock_holder(session) or f'another process ({reason or "it did not say which"})'
    return _step('busy', False, fix=FIX_BUSY, detail=f'The run adapter\'s session lock ({session}) is held by {holder}. Only one real '
                 'run or check works in a Virtuoso session at a time; nothing was read from it.')


def task_locks(profile_id, entry) -> tuple:
    """(session lock, cell lock) a real run or check of this task takes: the lock of the Virtuoso session its connection
    reaches and the lock of its cell (record 7.311). The first session's lock when the connection cannot be read."""
    try:
        settings = named_or_active(profile_id)[2] or {}
    except Exception:
        settings = {}
    session = bridge_session_lock(settings.get('env_file'), settings.get('profile')) if settings.get('env_file') else bridge_session_lock()
    cell = bridge_cell_lock(entry['library'], entry['core_cell']) if entry and entry.get('library') and entry.get('core_cell') else None
    return session, cell


def _connect_fix(detail) -> str:
    text = (detail or '').lower()
    if 'ade/maestro window' in text:
        return 'Close those ADE/Maestro windows in Virtuoso (the run exports through OCEAN, which they block), then check again.'
    if 'tunnel' in text:
        return 'Bring the link up in the Connection window, then check again.'
    if 'creation receipt' in text or 'receipt' in text:
        return 'The task\'s files and its creation record disagree: save it as a new task (Save as).'
    return FIX_COPY


def copy_steps(monitor, profile_id, name, entry, saved, *, acknowledge_unknown=False, commands=None) -> list:
    """Parts 2 and 3: the saved task against its working copy in Virtuoso. Read-only; each step says what it found."""
    from . import profile_preflight, profiles, working_copy  # lazy: profiles imports the optimizer (torch)
    commands = commands or {}
    locks = task_locks(profile_id, entry)
    if any(lock is not None and lock_holder(lock) for lock in locks):     # record 7.207: the adapter could not take a lock
        return [_busy_step(locks=locks)]
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
        if step == 'connect' and not item['ok'] and (item.get('detail') or '').startswith(('BlockingIOError', 'CellBusy')):
            steps.append(_busy_step(item.get('detail'), locks))    # taken between the look above and the connect
        elif item['ok']:
            steps.append(_step(step, True, detail=item.get('detail'), **({'skipped': True} if item.get('skipped') else {})))
        else:
            fix = (_connect_fix(item.get('detail')) if step == 'connect' else FIX_COPY if step == 'export'
                   else 'Save it as a new task (Save as).' if step == 'profile' else 'See the reason; then check again.')
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
                           fix='Undo the change in Maestro, or press Save as: it makes a new task and writes these rows\' setup '
                               'into its own copy. If the change in Maestro is what you want, make it in Probes and Specs (or '
                               'the Task file) first.'))
    return steps


def check(monitor, profile_id, config, *, rows=True, acknowledge_unknown=False, commands=None) -> dict:
    """The whole check of the saved task `config` runs. `rows=False`: the rows were compared already (static
    validation, before a start). Raises KeyError when the configuration runs no saved task."""
    found = saved_task(config)
    if found is None:
        raise KeyError('Only a saved task is checked: choose one in the Tasks window')
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
