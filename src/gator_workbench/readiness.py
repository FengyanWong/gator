"""What is still missing before this RL run can start - computed by the backend, never by a model.

One function turns facts the backend already has (the loaded task or its blocker, the static validation
report, the run/output settings, the LAST KNOWN connection result) into an ordered checklist: the free answer of
"What's missing?" in the Agent window, each item with what to do about it. (It lived in the Agent tab's agent package
until 2026-10-06, record 7.226, when that agent was replaced by the Claude Code and Codex buttons; the tab became the
window on 2026-10-07, record 7.253.)

Nothing here probes anything: no bridge contact, no simulator, no CLI, no model. In particular it reads the
connection monitor's cached status only - a fresh connection test stays an explicit user action.
Words only: no host, account, port, path or profile content is put into a checklist.
"""
from __future__ import annotations

from . import tasks
from .security import redact

TABLES = ('parameters', 'measurements', 'targets')                                  # checklist order = the editor tab order
BLOCKING = ('error', 'blocker')
TITLES = dict(parameters='Parameters', measurements='Probes', targets='Specs')      # = the editor tab names (frontend Editors.tsx)
LEARNING_WARNINGS = ('budget_within_warmup', 'budget_below_batch')
# An item an agent can help with: Claude Code or Codex, opened from the Agent window in this folder, can draft its rows from a
# description. Everything else is the user's own step.
AGENT_HELP = ' Claude Code or Codex (the Agent window) can also draft the rows from your description.'


def _section(path) -> str:
    head = str(path or '').replace('[', '.').split('.', 1)[0]
    return head if head in TABLES + ('run', 'output', 'circuit', 'research', 'project') else 'other'


def _item(item_id, title, status, who, detail, action=''):
    return dict(id=item_id, title=title, status=status, who=who, detail=detail, action=action)


def build(config: dict, *, task=None, task_blocker=None, validation=None, connection=None, output=None, profile=None) -> dict:
    """``config`` and ``validation`` are plain dicts (JSON form). ``task`` is the loaded runtime or None,
    ``connection`` the monitor's cached status dict or None, ``output`` the result of the output-root check.
    ``profile`` = dict(rows, matches) for a REAL circuit whose profile fixes its optimized variables: the rows it
    accepts, and whether the configured variables compile to exactly them (None = could not be compared yet)."""
    validation = validation or dict(blocks_run=True, issues=[], facts={})
    issues = validation.get('issues') or []
    blocking = [i for i in issues if i.get('level') in BLOCKING]
    by_section = {}
    for issue in blocking:
        by_section.setdefault(_section(issue.get('path')), []).append(issue)
    run, items = config.get('run') or {}, []
    mock = None if task is None else bool(task.mock)

    # 1. circuit
    if task is not None:
        items.append(_item('circuit', 'Circuit', 'done', 'you',
                           f"{'Synthetic (MOCK)' if mock else 'REAL'} circuit read: {len(task.base_graph.devices)} devices."))
    else:
        items.append(_item('circuit', 'Circuit', 'missing', 'you', str(task_blocker or 'No circuit could be read.')[:400],
                           'Open a task in the Tasks window, or make one there with "New task".'))

    # 2-4. the three tables
    items += _table_items(config, by_section, profile)

    # 5. blocking issues outside the tables
    other = [i for section, found in by_section.items() if section not in TABLES for i in found]
    if other:
        items.append(_item('validation', 'Other blocking issues', 'missing', 'you', _say(other),
                           'Open the blocking-issues list in the header; each entry names its field.'))

    # 6. run configuration
    mode, budget = run.get('mode', 'scratch'), run.get('max_evaluations')
    starving = [i for i in issues if i.get('code') in LEARNING_WARNINGS]
    detail = f"Mode {mode}, budget {budget} evaluation{'' if budget == 1 else 's'}, concurrency {run.get('concurrency', 1)}."
    if starving:
        items.append(_item('run', 'Run configuration', 'warning', 'you', detail + ' ' + _say(starving),
                           'Raise "Evaluation budget" under Run configuration, or lower batch size / warm-up under Advanced in '
                           'the RL model window: as set, '
                           'the run would not learn.'))
    else:
        items.append(_item('run', 'Run configuration', 'done', 'you', detail))

    reachability = [i for i in issues if i.get('code') == 'corner_reachability']
    if reachability:
        items.append(_item('corner_reachability', 'Corner targets', 'warning', 'you',
                           ' '.join(i['message'] for i in reachability), 'Open Corner check.'))

    # 7. output folder
    items += _output_items(output)

    # 8-9. real circuits only
    items += _connection_items(mock, run, connection, budget)

    missing = [i for i in items if i['status'] == 'missing']
    ready = not missing and not validation.get('blocks_run')
    items.append(_item('start', 'Start', 'done' if ready else 'missing', 'you',
                       'Nothing blocks a start.' if ready else f"{len(missing)} item(s) above still block a start.",
                       'Press "Calibration" (64 random designs '
                       'to propose reward settings) or "Start".' if ready else ''))
    return dict(ready=ready, next=missing[0] if missing else items[-1], items=items,
                note='Computed by the backend from the live configuration. No model was called, nothing was probed: '
                     'the connection line is the LAST test result, not a new one.')


def _say(found) -> str:
    """The first three issues' messages, each cut at 200 characters, and how many more there are."""
    return '; '.join(str(i.get('message'))[:200] for i in found[:3]) + (f' (+{len(found) - 3} more)' if len(found) > 3 else '')


def _table_items(config, by_section, profile) -> list:
    """The Parameters, Specs and Probes items: each table filled, empty, differing from the saved task, or not the rows a
    verified circuit fixes."""
    items = []
    rows = {name: len(config.get(name) or []) for name in TABLES}
    hard = [t for t in (config.get('targets') or []) if t.get('hard') and t.get('active', True)]
    registered = (config.get('circuit') or {}).get('source') == 'registered_task'
    fixed = (profile or {}).get('rows') or []
    uncompiled = (profile or {}).get('error') if fixed and rows['parameters'] else None
    mismatch = bool(fixed) and rows['parameters'] > 0 and (profile.get('matches') is False or bool(uncompiled))
    for name in TABLES:
        found = by_section.get(name, [])
        if name == 'parameters' and fixed and (mismatch or not rows['parameters']) and not found:
            detail = (f'This verified circuit fixes its optimized variables ({len(fixed)} rows: which sizes may be written, their range and '
                      'grid). ' + (f'The configuration does not compile, so they could not be compared: {uncompiled}' if uncompiled
                                  else 'The configured variables differ from them, so the run would be refused the moment it starts.'
                                  if mismatch else 'None is configured yet.'))
            items.append(_item(name, TITLES[name], 'missing', 'agent', detail,
                               'Double-click the task in the Tasks window: it brings exactly these rows, free.'))
            continue
        unsaved = [i for i in found if i.get('code') == 'task_not_saved']
        if unsaved and len(unsaved) == len(found):
            # The rows are there and differ from the saved task (an edit, an applied calibration, an older page): the fix
            # is ONE press, and the issue itself says which. Said whole here: cut at 200 characters it lost exactly that
            # sentence, and the general advice below ("Reload saved values ... or the agent writes the rows") told the
            # user to throw away what they had just applied (found with the calibration, record 7.204).
            items.append(_item(name, TITLES[name], 'missing', 'you', ' '.join(str(i.get('message')) for i in unsaved),
                               '"Save as" is on the editors\' tab line; "Reload saved values" is under "not saved", beside '
                               'the task\'s name.'))
            continue
        empty = dict(parameters=not rows['parameters'], targets=not hard, measurements=not rows['measurements'])[name]
        if found or empty:
            detail = _say(found) if found else dict(
                parameters='No optimized variable yet.', targets='No active hard constraint yet, so nothing defines "feasible".',
                measurements='No probe is defined; every spec is an equation over probes.')[name]
            action = ('Write each requirement in the "Specs" tab, with where it comes from.' if name == 'targets'
                      else f'Fill in the "{TITLES[name]}" tab.')
            if registered:                  # a registered task brings its own rows: free, exact, and the first thing to try
                action = 'Double-click the task in the Tasks window for its own rows, or ' + action[0].lower() + action[1:]
            action += AGENT_HELP
            items.append(_item(name, TITLES[name], 'missing', 'agent', detail, action))
        else:
            count = len(hard) if name == 'targets' else rows[name]
            items.append(_item(name, TITLES[name], 'done', 'agent',
                               f"{count} {'active hard constraint' if name == 'targets' else 'row'}{'' if count == 1 else 's'}."))
    return items


def _output_items(output) -> list:
    """The output folder's item, from the output-root check (None: not checked)."""
    items = []
    if output is None:
        items.append(_item('output', 'Output folder', 'unknown', 'you', 'Not checked.'))
    elif not output.get('allowed') or output.get('error'):
        items.append(_item('output', 'Output folder', 'missing', 'you', 'The folder is outside the allowed roots or cannot be used.',
                           'Choose another folder under "Output settings" (right).'))
    elif output.get('exists') and not output.get('writable'):
        items.append(_item('output', 'Output folder', 'missing', 'you', 'The folder exists but is not writable.',
                           'Choose another folder under "Output settings" (right).'))
    else:
        items.append(_item('output', 'Output folder', 'done', 'you',
                           'Writable.' if output.get('exists') else 'Allowed; it is created when the run starts.'))
    return items


def _connection_items(mock, run, connection, budget) -> list:
    """A real circuit's connection and budget items; a MOCK circuit's note that it needs no connection."""
    items = []
    if mock is False:
        if not run.get('connection_profile_id'):
            items.append(_item('connection', 'Connection', 'missing', 'you', 'No connection is selected.',
                               'Press the connection button in the header: in its window choose a Virtuoso connection, '
                               'connect, then "Test connection".'))
        else:
            overall = (connection or {}).get('overall', 'unknown')
            layers = ', '.join(f"{layer.get('layer')} {layer.get('state')}" for layer in (connection or {}).get('layers') or [])
            status = dict(ok='done', failed='missing', not_ready='missing').get(overall, 'unknown')
            age = (connection or {}).get('age_seconds')
            when = 'never tested in this backend session' if age is None else f'last test {round(age)} s ago'
            items.append(_item('connection', 'Connection', status, 'you', f'{overall} ({when}). {layers}'.strip(),
                               '' if status == 'done' else 'Press the connection button in the header, then "Test connection" '
                               'in its window. A '
                               'start tests again by itself and asks you to acknowledge layers that stay unknown.'))
        items.append(_item('authorization', 'Real simulation budget', 'at_start', 'you',
                           f'Pressing Start asks you to authorize {budget} real evaluation(s). Only you can.'))
    elif mock is True:
        items.append(_item('connection', 'Connection', 'not_applicable', 'you', 'A synthetic (MOCK) circuit needs no connection.'))
    return items


def profile_rows_check(config, runtime, report):
    """A real circuit profile fixes WHICH sizes may be written and their range and grid. The engine checks that only
    when the worker starts (after the budget was authorized), so the checklist says it: the configuration compiled
    offline and compared with the profile. Returns dict(rows, matches, error), or None for a task that fixes no rows."""
    fixed = tasks.profile_parameter_rows(runtime)
    profile = None
    if fixed:
        matches = problem = None
        broken = any(i['level'] in ('error', 'blocker') and str(i['path']).startswith('parameters') for i in report['issues'])
        if config.parameters and not broken:
            try:
                from analog_optimizer.envs.sizing import graph_contract
                # lazy: in the try: a failure of the import is handled with the rest
                from .compile import compile_task
                matches = graph_contract(compile_task(config, runtime.base_graph).graph) == graph_contract(runtime.base_graph)
            except Exception as exc:                   # it does not compile: a start would be refused for that alone
                problem = redact(f'{type(exc).__name__}: {exc}', 300)
        profile = dict(rows=fixed, matches=matches, error=problem)
    return profile
