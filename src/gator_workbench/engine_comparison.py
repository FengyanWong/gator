"""The archive comparison's part of a run (docs/plan-bo-mobo-rl-archive-comparison.md; the experiment's WORKPLAN-steps2-7.md,
items 1, 5 and 6): the common first designs every method evaluates after its start design, and the two searches that
propose the designs instead of the network - `turbo_archive` (T0, T+) and `mobo` (M+).

The engine calls these functions on its single scheduler thread and they keep their state on it:
  - `engine.initial_designs`: the common first designs' proposals, given in order; `engine.counters['initial_given']`
    counts those dispatched (charged), so that a resume never gives one twice;
  - `engine.proposer`: the search (archive_compare.runtime.build_proposer). Its state goes with every save point
    (`collector_state['comparison']`) and a resume restores it. The designs a crash left committed after the save point
    are told again from the run's tables (`after_crash`), as the replay re-admits their transitions.

What a search is told of a finished design (one rule for both searches, fixed before any target run):
  - the start design (a reset) is not a search observation: it is the episode contract every method pays for, and
    production TuRBO is not told it either;
  - the point is the EXECUTED design - the group values the lane applied, read as the parameters table records them (the
    archive's own source) - in the unit cube of the frozen domain;
  - a design whose status is not a circuit result (a timeout, a lost link, the licence, a lane failure, a cancel: every
    status but ok, measurement_error, nonconverged and invalid_design) is no evidence about the circuit: neither search
    fits it, it only settles the proposal;
  - TuRBO is told the run's reward (its goal view's own), M+ every recorded output with its validity, read as the archive
    read them from the metrics table (the last row of a name wins, a value counts when it is finite).
"""
from __future__ import annotations

import math
import time

from analog_optimizer.parameters.actions import ActionMapper

from .archive_compare import coords, runtime
from .archive_compare.mobo import SCORED_STATUSES
from .run_definitions import RESUMABLE_SEARCH_OPTIMIZERS
from .storage.dataset import DatasetReader

INITIAL_SOURCE = 'common_initial'           # the evaluations' action_source of a common first design
INITIAL_PHASE = 'warmup'                     # and its phase: a design given before the method's own


def is_search(config) -> bool:
    return config.run.optimizer in RESUMABLE_SEARCH_OPTIMIZERS


def prepare(engine):
    """The common first designs, each checked legal on the compiled task, and for a new run of a search the search
    itself (a resume restores it: `restore`). Before any lane opens."""
    comparison = engine.config.run.comparison
    engine.initial_designs, engine.comparison_mapper, engine.comparison_groups = [], None, None
    engine.counters.setdefault('initial_given', 0)
    if comparison is None:
        return
    engine.comparison_mapper = ActionMapper(engine.compiled.graph)
    engine.comparison_groups = coords.group_rows(engine.compiled)
    if comparison.initial_designs is not None:
        engine.initial_designs = runtime.initial_designs(comparison, engine.comparison_groups, engine.comparison_mapper)
    if is_search(engine.config) and engine.entry == 'start':
        engine.proposer = runtime.build_proposer(engine.config, engine.compiled)
        engine._pending_events = list(getattr(engine, '_pending_events', None) or []) + [
            ('search_started', dict(runtime.started_event(engine.proposer), initial_designs=len(engine.initial_designs)))]


def next_initial(engine):
    """The next common first design's proposal, counted as given; None once all were given."""
    given = int(engine.counters.get('initial_given', 0))
    if given >= len(getattr(engine, 'initial_designs', None) or ()):
        return None
    engine.counters['initial_given'] = given + 1
    return dict(engine.initial_designs[given])


def legal_values(engine, proposal) -> dict:
    """The group values a proposal legalizes to: the design a lane executes for it."""
    return dict(engine.comparison_mapper.legalize(proposal).group_values)


def propose(engine, evaluation_id):
    """The search's next design. M+ values it with the designs still in flight (their legalized values); TuRBO, as in
    production, settles parallel proposals by its own random draws. The time it took is recorded (plan: proposal compute
    is part of a method's cost)."""
    started = time.perf_counter()
    detail = {}
    if engine.config.run.optimizer == 'mobo':
        pending = [legal_values(engine, s['busy']['proposal']) for s in engine.lane_state.values()
                   if s['busy'] and s['busy']['op'] == 'step' and s['busy'].get('proposal') is not None]
        proposal = engine.proposer.propose(pending)
        detail = dict(engine.proposer.last or {})
    else:
        proposal = engine.proposer.propose()
    engine._event('search_proposal', evaluation_id=evaluation_id, seconds=round(time.perf_counter() - started, 6),
                  observations=engine.proposer.observations, **detail)
    return proposal


def recorded_outputs(metric_rows):
    """Every recorded output of one design and its validity, read as the archive read the metrics table (step 1's
    inventory): the last row of a name wins; a name counts when its value is finite, valid when its row says so."""
    last = {}
    for row in metric_rows:
        last[row['metric_name']] = (row.get('raw_value'), row.get('valid'))
    metrics, validity = {}, {}
    for name, (value, valid) in last.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            metrics[name], validity[name] = float(value), valid is True
    return metrics, validity


def executed_values(engine, proposal, parameter_rows):
    """(group values, where they came from): the values the lane applied, from the parameters table's rows; the
    legalized proposal when the lane applied none (it failed before) or one lies off the frozen domain."""
    members = {(row['instance_path'], row['parameter_name']): row['executed_value'] for row in parameter_rows}
    try:
        values = coords.group_values(engine.comparison_groups, members)
        for group in engine.comparison_groups:
            coords.to_proposal(group, values[group['id']])         # inside the domain, or ValueError
        return values, 'executed'
    except ValueError:
        return legal_values(engine, proposal), 'legalized_proposal'


def observe(engine, *, evaluation_id, action_source, proposal, status, reward, parameter_rows, metric_rows, asked=None):
    """Tell the search one finished design: a design it proposed (`asked`), or one it was given (a common first design,
    or a design told again after a crash: asked=False)."""
    if asked is None:
        asked = action_source == engine.proposer.SOURCE
    if status not in SCORED_STATUSES:                # no circuit result: only the proposal is settled, nothing is fitted
        engine.proposer.search.tell(None, None, asked=asked, infrastructure=True)
        return
    values, origin = executed_values(engine, proposal, parameter_rows)
    if origin != 'executed':
        engine._event('search_point_from_proposal', evaluation_id=evaluation_id, status=status,
                      note='no applied value in the domain for every group: the legalized proposal is told instead')
    if engine.config.run.optimizer == 'mobo':
        metrics, validity = recorded_outputs(metric_rows)
        engine.proposer.observe(values, metrics, validity, status, asked=asked)
        return
    if engine.proposer.observe(values, reward, asked=asked):
        engine._event('search_region_restarted', evaluation_id=evaluation_id, **engine.proposer.search.summary())


def state(engine):
    """What a save point keeps of the search: its whole state (data, region, counters, random generators)."""
    if not is_search(engine.config) or engine.proposer is None:
        return None
    return dict(optimizer=engine.config.run.optimizer, proposer=engine.proposer.state_dict())


def restore(engine, collector):
    """A resume: the search as its save point left it. A save point without it cannot continue the run exactly."""
    if not is_search(engine.config):
        return None
    saved = collector.get('comparison')
    if not saved or saved.get('optimizer') != engine.config.run.optimizer or saved.get('proposer') is None:
        raise RuntimeError(f'The save point holds no {engine.config.run.optimizer} search state: this run cannot be '
                           'continued exactly')
    engine.proposer = runtime.build_proposer(engine.config, engine.compiled, state=saved['proposer'])
    return runtime.started_event(engine.proposer)


def after_crash(engine, checkpoint_seq):
    """A resume after a crash (evaluations committed or dispatched after the save point): the common first designs
    already given are counted from the evaluations table (an interrupted one stays spent, as its charge does), and the
    search is told, in commit order, every design committed after its save point - the proposals that asked for them
    were lost with the process, so each is told as one it did not ask for. An interrupted design was never measured
    and is not told. Returns what the resume event says of it."""
    reader = DatasetReader(engine.layout.data)
    evaluations = reader.rows('evaluations', ['evaluation_id', 'commit_seq', 'action_source', 'status', 'reward'])
    given = sum(1 for e in evaluations if e['action_source'] == INITIAL_SOURCE)
    engine.counters['initial_given'] = max(int(engine.counters.get('initial_given', 0)), given)
    report = dict(initial_given=engine.counters['initial_given'])
    if not is_search(engine.config):
        return report
    sources = (INITIAL_SOURCE, engine.proposer.SOURCE)
    later = sorted((e for e in evaluations if e['commit_seq'] > checkpoint_seq and e['action_source'] in sources
                    and e['status'] != 'interrupted'), key=lambda e: e['commit_seq'])
    if later:
        wanted = {e['evaluation_id'] for e in later}
        parameters, metrics = {}, {}
        for row in reader.rows('parameters', ['evaluation_id', 'variable_id', 'role', 'instance_path', 'parameter_name',
                                              'executed_value', 'raw_policy_action']):
            if row['evaluation_id'] in wanted:
                parameters.setdefault(row['evaluation_id'], []).append(row)
        for row in reader.rows('metrics', ['evaluation_id', 'metric_name', 'raw_value', 'valid']):
            if row['evaluation_id'] in wanted:
                metrics.setdefault(row['evaluation_id'], []).append(row)
        for e in later:
            rows = parameters.get(e['evaluation_id'], [])
            proposal = {row['variable_id']: row['raw_policy_action'] for row in rows if row['role'] == 'independent'}
            observe(engine, evaluation_id=e['evaluation_id'], action_source=e['action_source'], proposal=proposal,
                    status=e['status'], reward=e['reward'], parameter_rows=rows,
                    metric_rows=metrics.get(e['evaluation_id'], []), asked=False)
    report.update(retold=len(later), observations=engine.proposer.observations)
    return report
