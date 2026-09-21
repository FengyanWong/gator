"""What is still missing before this RL run can start - computed by the backend, never by a model.

One function turns facts the backend already has (the loaded task or its blocker, the static validation
report, the run/output settings, the LAST KNOWN connection result) into an ordered checklist. It is the
zero-cost answer shown in the Agent tab, and the same data is handed to the agent so that a paid request
starts from the truth instead of guessing it.

Nothing here probes anything: no bridge contact, no simulator, no CLI, no model. In particular it reads the
connection monitor's cached status only - a fresh connection test stays an explicit user action.
Words only: no host, account, port, path or profile content is put into a checklist.
"""
from __future__ import annotations

TABLES = ('parameters', 'targets', 'measurements')
BLOCKING = ('error', 'blocker')
TITLES = dict(parameters='Optimization Parameters', targets='Performance Targets', measurements='Measurement Definitions')
LEARNING_WARNINGS = ('budget_within_warmup', 'budget_below_batch')


def _section(path) -> str:
    head = str(path or '').replace('[', '.').split('.', 1)[0]
    return head if head in TABLES + ('run', 'output', 'circuit', 'research', 'project') else 'other'


def _item(item_id, title, status, who, detail, action=''):
    return dict(id=item_id, title=title, status=status, who=who, detail=detail, action=action)


def build(config: dict, *, task=None, task_blocker=None, validation=None, connection=None, output=None) -> dict:
    """``config`` and ``validation`` are plain dicts (JSON form). ``task`` is the loaded runtime or None,
    ``connection`` the monitor's cached status dict or None, ``output`` the result of the output-root check."""
    validation = validation or dict(blocks_run=True, issues=[], facts={})
    issues = validation.get('issues') or []
    blocking = [i for i in issues if i.get('level') in BLOCKING]
    by_section = {}
    for issue in blocking:
        by_section.setdefault(_section(issue.get('path')), []).append(issue)
    say = lambda found: '; '.join(str(i.get('message'))[:200] for i in found[:3]) + (f' (+{len(found) - 3} more)' if len(found) > 3 else '')  # noqa: E731
    run, items = config.get('run') or {}, []
    mock = None if task is None else bool(task.mock)

    # 1. circuit
    if task is not None:
        items.append(_item('circuit', 'Circuit', 'done', 'you',
                           f"{'Synthetic (MOCK)' if mock else 'REAL'} circuit read: {len(task.base_graph.devices)} devices."))
    else:
        items.append(_item('circuit', 'Circuit', 'missing', 'you', str(task_blocker or 'No circuit could be read.')[:400],
                           'Choose the circuit under "Circuit source" (left) and load it.'))

    # 2-4. the three tables: the only part an agent proposal can change
    rows = {name: len(config.get(name) or []) for name in TABLES}
    hard = [t for t in (config.get('targets') or []) if t.get('hard') and t.get('active', True)]
    for name in TABLES:
        found = by_section.get(name, [])
        empty = dict(parameters=not rows['parameters'], targets=not hard, measurements=not rows['measurements'])[name]
        if found or empty:
            detail = say(found) if found else dict(
                parameters='No optimized variable yet.', targets='No active hard constraint yet, so nothing defines "feasible".',
                measurements='No measurement is defined; every target needs one.')[name]
            action = ('State the requirement and where it comes from; the agent can then write the rows.' if name == 'targets'
                      else f'Fill in "{TITLES[name]}", or ask the agent to draft it from the circuit.')
            items.append(_item(name, TITLES[name], 'missing', 'agent', detail, action))
        else:
            count = len(hard) if name == 'targets' else rows[name]
            items.append(_item(name, TITLES[name], 'done', 'agent',
                               f"{count} {'active hard constraint' if name == 'targets' else 'row'}{'' if count == 1 else 's'}."))

    # 5. blocking issues outside the tables
    other = [i for section, found in by_section.items() if section not in TABLES for i in found]
    if other:
        items.append(_item('validation', 'Other blocking issues', 'missing', 'you', say(other),
                           'Open the blocking-issues list in the header; each entry names its field.'))

    # 6. run configuration
    mode, budget = run.get('mode', 'scratch'), run.get('max_evaluations')
    starving = [i for i in issues if i.get('code') in LEARNING_WARNINGS]
    detail = f"Mode {mode}, budget {budget} evaluation{'' if budget == 1 else 's'}, concurrency {run.get('concurrency', 1)}."
    if starving:
        items.append(_item('run', 'Run configuration', 'warning', 'you', detail + ' ' + say(starving),
                           'Raise "Max evaluations" or lower batch size / warm-up under "RL network" (Advanced): as set, '
                           'the run would not learn.'))
    else:
        items.append(_item('run', 'Run configuration', 'done', 'you', detail))

    # 7. output folder
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

    # 8-9. real circuits only
    if mock is False:
        if not run.get('connection_profile_id'):
            items.append(_item('connection', 'Virtuoso bridge connection', 'missing', 'you', 'No connection profile is selected.',
                               'Select a profile in "Virtuoso bridge connection" (left), connect, then "Test connection".'))
        else:
            overall = (connection or {}).get('overall', 'unknown')
            layers = ', '.join(f"{layer.get('layer')} {layer.get('state')}" for layer in (connection or {}).get('layers') or [])
            status = dict(ok='done', failed='missing', not_ready='missing').get(overall, 'unknown')
            age = (connection or {}).get('age_seconds')
            when = 'never tested in this backend session' if age is None else f'last test {round(age)} s ago'
            items.append(_item('connection', 'Virtuoso bridge connection', status, 'you', f'{overall} ({when}). {layers}'.strip(),
                               '' if status == 'done' else 'Press "Test connection" (left). A start tests again by itself and '
                               'asks you to acknowledge layers that stay unknown.'))
        items.append(_item('authorization', 'Real simulation budget', 'at_start', 'you',
                           f'Pressing Start asks you to authorize {budget} real evaluation(s). Only you can.'))
    elif mock is True:
        items.append(_item('connection', 'Virtuoso bridge connection', 'not_applicable', 'you', 'A synthetic (MOCK) circuit needs no bridge.'))

    missing = [i for i in items if i['status'] == 'missing']
    ready = not missing and not validation.get('blocks_run')
    items.append(_item('start', 'Start', 'done' if ready else 'missing', 'you',
                       'Nothing blocks a start.' if ready else f"{len(missing)} item(s) above still block a start.",
                       'Press "Single baseline simulation" (one costed evaluation) or "Start".' if ready else ''))
    return dict(ready=ready, next=missing[0] if missing else items[-1], items=items, facts=validation.get('facts') or {},
                # Metric names the simulation backend really returns for this circuit: a target on anything else is refused.
                provided_metrics=sorted(str(m) for m in (getattr(task, 'provided_metrics', None) or ()))[:80],
                run=dict(mode=mode, max_evaluations=budget, concurrency=run.get('concurrency', 1), seed=run.get('seed'),
                         encoder=(run.get('network') or {}).get('encoder_type'), mock=mock),
                issues=[dict(level=i.get('level'), code=i.get('code'), path=i.get('path'), message=str(i.get('message'))[:300])
                        for i in issues if i.get('level') != 'info'][:40],
                note='Computed by the backend from the live configuration. No model was called, nothing was probed: '
                     'the connection line is the LAST test result, not a new one.')
