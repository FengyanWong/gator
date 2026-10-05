"""Calibration from the random designs of a task's baseline run (record 7.197).

A "Baseline simulation" asked to calibrate (the page asks every time, record 7.202) goes on, after the one simulation of
the starting design, with N random designs - uniform draws over the Parameters ranges, the very draws a run's warm-up
makes - and this module reads what they measured. Two settings come out of it, both as PROPOSALS: nothing here changes a
configuration or a task, the page shows them with one Apply button.

* Scale of a Specs row: the median miss, in the row's own unit, among the random designs that miss the row. With it a
  typical failing random design counts as a miss of 1 on every row (0.5 after the compressed shape), so no row leads
  the reward only because of its unit or the size of its limit.
* Initial alpha (the starting temperature of soft actor-critic): 0.1 x the standard deviation of the reward among the
  random designs, the reward worked out again with the proposed scales by the reward code a run uses.

What was measured, and what was not, is in docs/decisions.md ("Calibration with the baseline run").

The run's own tables are the only input (evaluations, metrics) with its effective configuration; the result is one file
in the run folder, `calibration.json`.
"""
from __future__ import annotations

import math
import statistics
from types import SimpleNamespace

FORMAT = 'gator-calibration-1'
FILE = 'calibration.json'
MAX_DESIGNS = 500                          # the page asks for 64 (App.tsx CALIBRATION_DESIGNS)
RANDOM_SOURCE = 'random_warmup'            # engine.py `_dispatch`: a uniform draw over every optimized range

MIN_SCORED = 16                            # random designs with a reward before anything is proposed
MIN_MISSES = 8                             # designs that miss a row before its Scale is proposed ...
MIN_MISS_SHARE = 0.125                     # ... and their share of the designs that measured the row (8 of 64)
SCALE_WITHIN = (0.01, 10.0)                # a proposed Scale stays within these multiples of what an empty box means
ALPHA_PER_SD = 0.1
ALPHA_WITHIN = (1e-4, 0.05)                # validation.py warns above 0.05 (the designs stay a random search)
SAME_REWARD = 1e-9


def prepare(config, designs):
    """The baseline run's configuration (a copy the caller made), changed in place for `designs` calibration designs.

    Every lane simulates the starting design once (its reset - the first of them is the baseline) and then only random
    designs: the warm-up covers all of them, no episode ends in between (a reset would cost a simulation), nothing is
    learned from them (an update is never due), a passing design does not stop the run, and a streak of designs that
    cannot be measured does not either - how many could not be is part of the answer."""
    run, adv = config.run, config.run.advanced
    lanes = run.concurrency
    run.max_evaluations = lanes + designs
    run.stop_at_first_feasible = False
    run.max_consecutive_failures = max(run.max_consecutive_failures, lanes + designs)
    adv.warmup_transitions, adv.episode_length, adv.episode_terminates_on_success = designs, designs, False
    adv.update_every = designs + 1
    return dict(designs=designs, lanes=lanes, evaluations=lanes + designs)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _round(value):
    """Two significant digits: a proposal is an estimate from a few dozen designs, not a measured constant."""
    return float(f'{value:.2g}')


def _rewards(config, designs, values):
    """The reward of each design under `config`'s Specs rows and reward settings, by the reward code a run uses."""
    from analog_optimizer.measurements.specs import SpecificationEvaluator
    from . import compile as compiler
    specs = compiler.build_specs(config)[0]
    evaluator = SpecificationEvaluator(specs, compiler.reward_settings(config))
    units = {spec.metric_id: spec.unit for spec in specs}
    rewards = []
    for design in designs:
        measured = values.get(design['evaluation_id'], {})
        row = SimpleNamespace(condition=None, status=design.get('status'), candidate_evaluated=True, metrics=dict(measured),
                              metric_units={name: units[name] for name in measured if name in units},
                              metric_validity={name: True for name in measured})
        try:
            rewards.append(evaluator.evaluate_conditions((row,)).reward)
        except ValueError:
            rewards.append(None)
    return rewards


def calibrate(config, evaluations, metric_rows) -> dict:
    """The proposals from a run's rows. `evaluations`: rows of the evaluations table (evaluation_id, dispatch_index,
    action_source, status, reward, all_hard_constraints_satisfied). `metric_rows`: the metrics table's rows of the Specs
    (aggregation_level 'aggregate', hard not None): evaluation_id, metric_name, raw_value (canonical unit), valid."""
    from . import compile as compiler, units
    designs = sorted((e for e in evaluations if e.get('action_source') == RANDOM_SOURCE), key=lambda e: e.get('dispatch_index') or 0)
    wanted = {e['evaluation_id'] for e in designs}
    values: dict = {}
    for row in metric_rows:
        if row['evaluation_id'] in wanted and row.get('valid') and _finite(row.get('raw_value')):
            values.setdefault(row['evaluation_id'], {})[row['metric_name']] = row['raw_value']
    recorded = [e['reward'] if _finite(e.get('reward')) else None for e in designs]
    scored = sum(r is not None for r in recorded)
    rule = dict(scale='the median miss among the random designs that miss the row', min_scored=MIN_SCORED, min_misses=MIN_MISSES,
                min_miss_share=MIN_MISS_SHARE, scale_within=list(SCALE_WITHIN), alpha_per_sd=ALPHA_PER_SD, alpha_within=list(ALPHA_WITHIN))
    result = dict(format=FORMAT, status='not_calibrated', reason=None, scale_note=None, rule=rule,
                  designs=dict(simulated=len(designs), scored=scored, passing=sum(bool(e.get('all_hard_constraints_satisfied')) for e in designs)),
                  rows=[], initial_alpha=dict(used=config.run.advanced.initial_alpha, proposed=None, reward_sd=None, reward_sd_used=None, note=None))
    if scored < MIN_SCORED:
        result['reason'] = (f'{scored} of the {len(designs)} random designs gave a reward; at least {MIN_SCORED} are needed '
                            'before a typical miss or a reward spread can be named.')
        return result

    specs = {spec.metric_id: spec for spec in compiler.build_specs(config)[0]}
    proposed = {}
    # The median puts a typical miss at 1: the middle of the compressed shape, and the cap of the capped one - where half
    # of the failing designs would count the same. So a Scale is proposed for the compressed shape only.
    compressed = config.run.reward.violation_shape == 'compressed'
    if not compressed:
        result['scale_note'] = ('No Scale is proposed: the reward uses the capped violation shape, where a miss of 1 or more counts '
                                'the same, and the calibration puts a typical miss at 1. It is made for the compressed shape '
                                '("Use the tested reward").')
    for target in config.targets:
        if not target.active:
            continue
        spec, factor = specs[target.metric_id], units.scale_to_canonical(1.0, target.unit)
        measured = [values[e['evaluation_id']][target.metric_id] for e in designs if target.metric_id in values.get(e['evaluation_id'], {})]
        misses = [miss for miss in (max(0.0, 0.0 if spec.lower is None else spec.lower - value,
                                        0.0 if spec.upper is None else value - spec.upper) for value in measured) if miss > 0]
        stated = target.normalization_scale or None
        empty_box = compiler.normalization_scale(target.model_copy(update=dict(normalization_scale=None)))
        from_limit = any(v not in (None, 0) for v in (target.lower, target.upper))       # else the empty box means 1, a placeholder
        row = dict(metric_id=target.metric_id, unit=target.unit, lower=target.lower, upper=target.upper, scale_stated=stated,
                   scale_used=compiler.normalization_scale(target), measured=len(measured), misses=len(misses),
                   median_miss=None, proposed_scale=None, limited=None, note=None)
        if misses:
            row['median_miss'] = statistics.median(misses) / factor
        if compressed and (len(misses) < MIN_MISSES or len(misses) < MIN_MISS_SHARE * len(measured)):
            row['note'] = (f'{len(misses)} of {len(measured)} random designs miss this row: too few to name a typical miss. '
                           'Its Scale stays as it is.')
        elif compressed and target.direction_after_feasible != 'none':
            # One number, two jobs: on this row the Scale also measures how far the objective is past its limit (the objective
            # bonus), so a proposal from the misses would change what the bonus means. A judgment: in the test it made no
            # measurable difference whether this row was calibrated too (docs/decisions.md).
            row['note'] = 'This row carries the objective: its Scale also measures the objective bonus, so it stays as it is.'
        elif compressed:
            scale = row['median_miss']
            if from_limit:
                low, high = (bound * empty_box for bound in SCALE_WITHIN)
                if scale < low:
                    scale, row['limited'] = low, 'low'
                elif scale > high:
                    scale, row['limited'] = high, 'high'
                if row['limited']:
                    row['note'] = (f'The typical miss is {row["median_miss"]:.3g} {target.unit}; the proposal is kept within '
                                   f'{SCALE_WITHIN[0]:g} to {SCALE_WITHIN[1]:g} times the size of the limit.')
            row['proposed_scale'] = proposed[target.metric_id] = _round(scale)
        result['rows'].append(row)

    # The starting temperature belongs to the reward the next run will have: the proposed scales, the same reward settings.
    # The reward code must first reproduce what the run recorded with the scales it had; otherwise nothing is proposed.
    alpha = result['initial_alpha']
    again = _rewards(config, designs, values)
    reproduced = sum((a is None and b is None) or (a is not None and b is not None and abs(a - b) <= SAME_REWARD) for a, b in zip(recorded, again))
    result['reward_check'] = dict(designs=len(designs), reproduced=reproduced)
    alpha['reward_sd_used'] = statistics.stdev([r for r in recorded if r is not None])
    if reproduced != len(designs):
        alpha['note'] = (f'Not proposed: the recorded reward of {len(designs) - reproduced} of {len(designs)} random designs could not be '
                         'worked out again from the recorded values.')
    else:
        changed = config.model_copy(deep=True)
        for target in changed.targets:
            if target.metric_id in proposed:
                target.normalization_scale = proposed[target.metric_id]
        rewards = [r for r in _rewards(changed, designs, values) if r is not None]
        alpha['reward_sd'] = spread = statistics.stdev(rewards) if len(rewards) >= 2 else 0.0
        if len(rewards) < MIN_SCORED or spread <= SAME_REWARD:
            alpha['note'] = 'Not proposed: the reward does not differ among the random designs.'
        else:
            value = min(max(ALPHA_PER_SD * spread, ALPHA_WITHIN[0]), ALPHA_WITHIN[1])
            alpha['proposed'] = _round(value)
            if value != ALPHA_PER_SD * spread:
                alpha['note'] = (f'{ALPHA_PER_SD:g} x the reward spread is {ALPHA_PER_SD * spread:.2g}; the proposal is kept within '
                                 f'{ALPHA_WITHIN[0]:g} to {ALPHA_WITHIN[1]:g}.')
    if proposed or alpha['proposed'] is not None:
        result['status'] = 'calibrated'
    else:
        result['reason'] = 'The random designs give no proposal: no row is missed often enough, and the reward spread could not be named.'
    return result


def sentence(result) -> str:
    """One line for the run's notes and its event log."""
    designs = result['designs']
    if result['status'] != 'calibrated':
        return f'Calibration: nothing proposed. {result["reason"]}'
    rows = [row for row in result['rows'] if row['proposed_scale'] is not None]
    alpha = result['initial_alpha']['proposed']
    return (f'Calibration from {designs["scored"]} scored random designs ({designs["simulated"]} simulated): a Scale proposed for '
            f'{len(rows)} of {len(result["rows"])} Specs rows'
            + (f', Initial alpha {alpha:g}' if alpha is not None else ', no Initial alpha') + '. Nothing is applied by the run.')


def from_run(run_dir, manifest=None) -> dict:
    """The calibration of a finished baseline run, from its tables and its effective configuration."""
    from . import schema
    from .layout import RunLayout
    from .storage import DatasetReader, read_json
    from .storage.dataset import utcnow
    layout = RunLayout(run_dir)
    manifest = manifest if manifest is not None else (read_json(layout.manifest, default={}) or {})
    config = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    reader = DatasetReader(layout.data)
    evaluations = reader.rows('evaluations', ['evaluation_id', 'dispatch_index', 'action_source', 'status', 'reward',
                                              'all_hard_constraints_satisfied'])
    metric_rows = [row for row in reader.rows('metrics', ['evaluation_id', 'metric_name', 'raw_value', 'valid', 'hard', 'aggregation_level'])
                   if row['aggregation_level'] == 'aggregate' and row['hard'] is not None]
    result = calibrate(config, evaluations, metric_rows)
    request = manifest.get('calibration') or {}
    result['designs']['requested'] = request.get('designs')
    if not result['designs']['simulated']:                # said as what happened, not as "0 of the 0 random designs"
        stopped = ((manifest.get('segments') or [{}])[-1]).get('stop_reason')
        result['reason'] = ('The starting design gave no valid result, so no random design was simulated.' if stopped == 'baseline_invalid'
                            else 'No random design was simulated: the run ended before the calibration began.')
    result.update(run_id=manifest.get('run_id'), task_key=(manifest.get('circuit') or {}).get('task_key'),
                  run_state=manifest.get('state'), created_utc=utcnow().isoformat())
    return result
