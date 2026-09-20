"""Best DESIGN = a circuit parameter set with its measurements. It is not a model and is
kept strictly apart from the ``latest`` and ``best_policy`` checkpoint pointers.

Selection rule (recorded with every result):
  * a feasible design always beats an infeasible one;
  * among feasible designs: the declared post-feasibility preference metric if one exists,
    otherwise the existing reward (which only differs through soft targets), otherwise the
    earliest design. No objective is invented;
  * among infeasible valid designs: smallest normalized hard-constraint violation.
Invalid evaluations (NaN, missing measurements, failures) are never candidates.

When no feasible design exists ``best_feasible.json`` says so explicitly with null; no
fictitious result, no parameters.csv and no optimized netlist are produced.
"""
from __future__ import annotations

import csv
import io
import math
from pathlib import Path
import re

from .storage.atomic import publish, temporary_path, write_json
from .storage.dataset import utcnow


class BestDesignTracker:
    def __init__(self, preference=None, state=None):
        self.preference = preference
        self.feasible = self.infeasible = None
        if state:
            self.feasible, self.infeasible = state.get('feasible'), state.get('infeasible')

    def state_dict(self):
        return dict(feasible=self.feasible, infeasible=self.infeasible)

    def _better_feasible(self, new, old):
        if old is None:
            return True
        if self.preference:
            a, b = new['metrics'].get(self.preference['metric']), old['metrics'].get(self.preference['metric'])
            if a is None or b is None:
                return b is None and a is not None
            return a < b if self.preference['direction'] == 'min' else a > b
        if new['reward'] is not None and old['reward'] is not None and not math.isclose(new['reward'], old['reward']):
            return new['reward'] > old['reward']
        return False

    def offer(self, candidate) -> str | None:
        """candidate: dict(evaluation_id, valid, feasible, violation, reward, metrics, ...). Returns role."""
        if not candidate['valid']:
            return None
        if candidate['feasible']:
            if self._better_feasible(candidate, self.feasible):
                self.feasible = candidate
                return 'best_feasible'
            return None
        if self.infeasible is None or candidate['violation'] < self.infeasible['violation']:
            self.infeasible = candidate
            return 'best_infeasible'
        return None

    @property
    def best(self):
        return self.feasible or self.infeasible

    def selection_rule(self):
        return dict(feasible_over_infeasible=True, preference=self.preference,
                    feasible_tiebreak='existing reward (soft targets), then earliest',
                    infeasible='smallest normalized hard-constraint violation',
                    scope='best OBSERVED design; no claim of global optimality')


def _record(candidate, *, status, tracker, task, config_summary):
    if candidate is None:
        return dict(status=status, design=None, selection_rule=tracker.selection_rule(), generated_utc=utcnow().isoformat())
    return dict(status=status, generated_utc=utcnow().isoformat(), selection_rule=tracker.selection_rule(),
                design=dict(evaluation_id=candidate['evaluation_id'], commit_seq=candidate['commit_seq'],
                            feasible=candidate['feasible'], reward=candidate['reward'],
                            normalized_constraint_violation=candidate['violation'],
                            independent_variables=candidate['variables'], expanded_bindings=candidate['members'],
                            metrics=candidate['metrics'], metric_units=candidate['metric_units'],
                            constraints=candidate['constraints'], test_conditions=candidate['conditions'],
                            provenance=candidate['provenance'],
                            validation_status='nominal evaluation only; no PVT/Monte-Carlo post-validation '
                                              'has been performed'),
                task=task, specification=config_summary)


def write_outputs(directory, tracker: BestDesignTracker, *, task, config_summary, netlist_text, graph,
                  reparse=None, netlist_name='optimized_dut.scs'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    notes = {}
    feasible = tracker.feasible
    write_json(directory / 'best_feasible.json', _record(
        feasible, status='found' if feasible else 'none_found', tracker=tracker, task=task,
        config_summary=config_summary) | ({} if feasible else {
            'reason': 'No evaluated design satisfied every hard constraint. This is an explicit null, not a result.'}))
    write_json(directory / 'best_infeasible.json', _record(
        tracker.infeasible, status='found' if tracker.infeasible else 'none_found', tracker=tracker, task=task,
        config_summary=config_summary))
    for name in ('parameters.csv', netlist_name):
        stale = directory / name
        if feasible is None and stale.exists():
            stale.unlink()
    if feasible is None:
        notes['parameters.csv'] = notes[netlist_name] = 'not created: no feasible design exists'
        return notes
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(['variable_id', 'member_variable_id', 'role', 'instance_path', 'parameter_name', 'value', 'unit',
                     'ratio', 'evaluation_id'])
    for member in feasible['members']:
        writer.writerow([member['variable_id'], member['member_variable_id'], member['role'], member['instance_path'],
                         member['parameter_name'], repr(float(member['value'])), member['unit'], member['ratio'],
                         feasible['evaluation_id']])
    temporary = temporary_path(directory / 'parameters.csv')
    temporary.write_text(buffer.getvalue(), encoding='utf8')
    publish(temporary, directory / 'parameters.csv')
    outcome = export_netlist(netlist_text, graph, feasible['members'], reparse=reparse)
    if outcome['status'] == 'verified':
        temporary = temporary_path(directory / netlist_name)
        temporary.write_text(outcome['text'], encoding='utf8')
        publish(temporary, directory / netlist_name)
        notes[netlist_name] = ('project netlist with the best parameters, verified by re-parsing. This is NOT a native '
                               'schematic; writing back to Virtuoso needs user confirmation and a new cellview.')
    else:
        stale = directory / netlist_name
        if stale.exists():
            stale.unlink()
        notes[netlist_name] = f"not created: {outcome['reason']}"
    return notes


def export_netlist(netlist_text, graph, members, *, reparse=None):
    """Rewrite parameter values on top-level instance lines, then PROVE the result by re-parsing.

    Returns dict(status='verified', text=...) or dict(status='unsupported', reason=...). Nothing
    is written unless every targeted value reads back exactly and every other value is unchanged.
    """
    if not netlist_text:
        return dict(status='unsupported', reason='the task has no project netlist text')
    lines = netlist_text.split('\n')
    devices = {d.id: d for d in graph.devices}
    for member in members:
        path, parameter = member['instance_path'], member['parameter_name']
        if '/' in path:
            return dict(status='unsupported', reason=f'{path} is inside a subcircuit; editing a shared definition '
                                                     'would change every instance of it')
        device = devices.get(path)
        value = graph.parameters.get(path, {}).get(parameter)
        if device is None or value is None:
            return dict(status='unsupported', reason=f'{path}.{parameter} is not in the parsed circuit')
        source_name = value.source_name or parameter
        index = device.source.line - 1
        pattern = re.compile(r'(?<![\w.])' + re.escape(source_name) + r'(\s*=\s*)' + re.escape(value.raw) + r'(?![\w.])')
        replaced = False
        while 0 <= index < len(lines):
            new_line, count = pattern.subn(lambda m: f'{source_name}{m.group(1)}{float(member["value"]):.12g}',
                                           lines[index], count=1)
            if count:
                lines[index], replaced = new_line, True
                break
            if not lines[index].rstrip().endswith('\\'):
                break
            index += 1
        if not replaced:
            return dict(status='unsupported', reason=f'could not locate {source_name}={value.raw} on the line of {path}')
    text = '\n'.join(lines)
    if reparse is None:
        return dict(status='unsupported', reason='no parser available to verify the rewritten netlist')
    try:
        check = reparse(text)
    except Exception as exc:
        return dict(status='unsupported', reason=f'rewritten netlist does not parse: {exc}')
    wanted = {(m['instance_path'], m['parameter_name']): float(m['value']) for m in members}
    for device_id, parameters in graph.parameters.items():
        for name, old in parameters.items():
            new = check.parameters.get(device_id, {}).get(name)
            expected = wanted.get((device_id, name), old.value)
            if new is None or (expected is None) != (new.value is None) or (
                    expected is not None and not math.isclose(new.value, expected, rel_tol=1e-9, abs_tol=1e-24)):
                return dict(status='unsupported', reason=f'verification failed for {device_id}.{name}')
    return dict(status='verified', text=text)
