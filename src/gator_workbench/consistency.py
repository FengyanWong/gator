"""The check before every run of a saved task (Virtuoso task flow, part 4).

The user asked for "frontend backend and virtuoso side consistency" (2026-09-21). A run runs exactly one saved task
on its working copy, so three sides must say the same thing before any costed simulation:

1. the rows of the three editors (Parameters, Probes, Specs) and the saved task file (``task.json``) - offline. Static
   validation says it while you edit (``task_not_saved``, blocking), so Start is not even offered on a difference;
2. the saved task and its working copy in Virtuoso: the run adapter connects (creation receipt, no ADE/Maestro window,
   the copy still has the recorded sizes), Virtuoso exports the testbench netlist and the export is compared with the
   recorded topology and every parameter, and the deck is written without simulating (``profile_preflight``);
3. a task measured by Maestro: the copy's Maestro test, read back, against the task file's ``maestro`` part.

Start, "Single baseline simulation" and Resume run parts 2 and 3 right after the connection gate
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
FIX_ROWS = 'Press Save task to save the rows as they are now, or Load starter configuration to take the saved rows back.'
FIX_COPY = ('The working copy was changed in Virtuoso after the task was saved: press Save task to take the copy as it is '
            'now, or undo the change in Virtuoso.')
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
    connection='A connection is chosen')
FAILED = dict(
    editors='The editors differ from the saved task',
    profile='The task\'s files do not pass the checks of the real backend',
    connect='The run adapter could not use the working copy',
    export='The working copy in Virtuoso differs from the saved task',
    deck='The simulation deck could not be written',
    close='The run adapter did not let go of the working copy cleanly',
    maestro='The working copy\'s Maestro test differs from the task',
    gate='The connection gate blocked the check',
    connection='No connection is chosen')


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


def _brief(value) -> str:
    if value is None:
        return '(none)'
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
        lines = []
        for item in structured_diff({section: kept}, {section: now}):
            if item['change'] == 'added':
                lines.append(f'{item["key"]} is here but not saved')
            elif item['change'] == 'removed':
                lines.append(f'{item["key"]} is saved but not here')
            else:
                fields = ', '.join(f'{f["field"]} {_brief(f["after"])} here, {_brief(f["before"])} saved' for f in item['fields'][:3])
                more = len(item['fields']) - 3
                lines.append(f'{item["key"]}: {fields}' + (f' (and {more} more)' if more > 0 else ''))
        found[section] = lines or ['the same rows, in another order']
    return found


def describe_rows(section, lines, *, name, revision) -> str:
    label = next(label for key, label, _i, _p in SECTIONS if key == section)
    shown = '; '.join(lines[:4]) + (f'; and {len(lines) - 4} more' if len(lines) > 4 else '')
    return f'{label} differ from the saved task real:{name} (revision {revision}): {shown}.'


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
    commands = commands or {}
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
        if item['ok']:
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
