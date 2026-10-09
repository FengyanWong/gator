"""Calibration from random designs (standalone since record 7.248; legacy combined runs remain readable).

A Calibration run evaluates N independent random designs over the Parameters ranges. The historical combined API
first simulates the starting design, then draws its random designs; both paths use the same proposal arithmetic.
Two settings come out of it, both as PROPOSALS: nothing here changes a configuration or a task.

* Scale of a Specs row: the median miss, in the row's own unit, among the random designs that miss the row. With it a
  typical failing random design counts as a miss of 1 on every row (0.5 after the compressed shape), so no row leads
  the reward only because of its unit or the size of its limit.
  A row with a lower AND an upper limit (a window) that most random designs are inside gets at most half its width
  (record 7.217): a design inside the window has at most that much room, the margin bonus is paid on the row with the
  least room measured in its Scale, and so a wider Scale on a window holds the margin bonus of the whole task small.
  A window most random designs miss keeps the typical miss: it has to be found first, and half its width - a thirtieth
  of the typical miss on the ring oscillator's frequency row - would make nearly every design count the same.
* Initial alpha (the starting temperature of soft actor-critic): 0.1 x the standard deviation of the reward among the
  random designs, the reward worked out again with the proposed scales by the reward code a run uses. It is proposed
  only when it differs from the value the run had by a factor of 2 or more (record 7.217): closer values made no
  measurable difference in the tests, and a proposal only made the page differ from the saved default.

What was measured, and what was not, is in docs/decisions.md ("Calibration with the baseline run").

The run's own tables are the only input (evaluations, metrics) with its effective configuration; the result is one file
in the run folder, `calibration.json`.
"""
from __future__ import annotations

import math
import statistics
from types import SimpleNamespace
from . import compile as compiler, schema, units
from .layout import RunLayout
from .storage import DatasetReader, read_dict, read_json
from .storage.dataset import utcnow

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
ALPHA_FACTOR = 2.0                         # proposed only when it differs from the value in use by this factor or more
SAME_REWARD = 1e-9
# The rule a result was worked out with. 1: record 7.197. 3 (record 7.217): a window most random designs are inside gets
# at most half its width; Initial alpha only when it differs by ALPHA_FACTOR. (2 was an unreleased state of record
# 7.217 - half its width for every window - under which six Baseline simulations of 2026-10-05 were recorded.) A run's
# file written under another rule is worked out again from the run's recorded designs when it is read (`current`).
RULE = 3


def prepare(config, designs, *, random_only=False):
    """The baseline run's configuration (a copy the caller made), changed in place for `designs` calibration designs.

    Legacy combined runs simulate the starting design once per lane before the random designs. With `random_only`,
    every evaluation is a random design and the engine bypasses reset simulations and replay.
    After its resets the legacy path runs only random designs: the warm-up covers all of them, no episode ends in between (a reset would cost a simulation), nothing is
    learned from them (an update is never due), a passing design does not stop the run, and a streak of designs that
    cannot be measured does not either - how many could not be is part of the answer."""
    run, adv = config.run, config.run.advanced
    lanes = run.concurrency
    run.max_evaluations = designs if random_only else lanes + designs
    run.stop_at_first_feasible = False
    run.max_consecutive_failures = max(run.max_consecutive_failures, lanes + designs)
    adv.warmup_transitions, adv.episode_length, adv.episode_terminates_on_success = designs, designs, False
    adv.update_every = designs + 1
    request = dict(designs=designs, lanes=lanes, evaluations=run.max_evaluations)
    if random_only:
        request['random_only'] = True
        run.rehearsal = None
        config.output.save_transition_archive = False
    return request


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _round(value):
    """Two significant digits: a proposal is an estimate from a few dozen designs, not a measured constant."""
    return float(f'{value:.2g}')


def _text(value, unit):
    """A number of a note, three digits, written as every quantity is (record 7.208): 300 mV, 25 MHz, 9.6 deg."""
    return units.text(float(f'{value:.3g}'), unit)


def _rewards(config, designs, values):
    """The reward of each design under `config`'s Specs rows and reward settings, by the reward code a run uses."""
    from analog_optimizer.measurements.specs import SpecificationEvaluator
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
    designs = sorted((e for e in evaluations if e.get('action_source') == RANDOM_SOURCE), key=lambda e: e.get('dispatch_index') or 0)
    wanted = {e['evaluation_id'] for e in designs}
    values: dict = {}
    for row in metric_rows:
        if row['evaluation_id'] in wanted and row.get('valid') and _finite(row.get('raw_value')):
            values.setdefault(row['evaluation_id'], {})[row['metric_name']] = row['raw_value']
    recorded = [e['reward'] if _finite(e.get('reward')) else None for e in designs]
    scored = sum(r is not None for r in recorded)
    rule = dict(version=RULE, scale='the median miss among the random designs that miss the row',
                window='at most half the window when most random designs are inside it',
                min_scored=MIN_SCORED, min_misses=MIN_MISSES, min_miss_share=MIN_MISS_SHARE, scale_within=list(SCALE_WITHIN),
                alpha_per_sd=ALPHA_PER_SD, alpha_within=list(ALPHA_WITHIN), alpha_factor=ALPHA_FACTOR)
    result = dict(format=FORMAT, status='not_calibrated', reason=None, scale_note=None, rule=rule,
                  designs=dict(simulated=len(designs), scored=scored, passing=sum(bool(e.get('all_hard_constraints_satisfied')) for e in designs)),
                  rows=[], initial_alpha=dict(used=config.run.advanced.initial_alpha, proposed=None, estimate=None, reward_sd=None, reward_sd_used=None, note=None))
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
        row = _propose_scale(target, specs[target.metric_id], designs, values, compressed, proposed)
        result['rows'].append(row)

    # The starting temperature belongs to the reward the next run will have: the proposed scales, the same reward settings.
    # The reward code must first reproduce what the run recorded with the scales it had; otherwise nothing is proposed.
    alpha = _propose_alpha(config, designs, values, recorded, proposed, result)
    if proposed or alpha['proposed'] is not None:
        result['status'] = 'calibrated'
    elif alpha['estimate'] is not None:
        result['reason'] = ('The random designs give nothing to change: no Scale is proposed for a Specs row, and the Initial alpha in use '
                            f'({alpha["used"]:g}) is close to the estimate ({alpha["estimate"]:g}).')
    else:
        result['reason'] = 'The random designs give no proposal: no row is missed often enough, and the reward spread could not be named.'
    return result



def _propose_scale(target, spec, designs, values, compressed, proposed):
    """One active Specs row: what the random designs measured and missed, and the Scale proposed for it (also put into
    `proposed`), or why none is. Returns the row of the result."""
    factor = units.scale_to_canonical(1.0, target.unit)
    measured = [values[e['evaluation_id']][target.metric_id] for e in designs if target.metric_id in values.get(e['evaluation_id'], {})]
    misses = [miss for miss in (max(0.0, 0.0 if spec.lower is None else spec.lower - value,
                                    0.0 if spec.upper is None else value - spec.upper) for value in measured) if miss > 0]
    stated = target.normalization_scale or None
    empty_box = compiler.normalization_scale(target.model_copy(update=dict(normalization_scale=None)))
    from_limit = any(v not in (None, 0) for v in (target.lower, target.upper))       # else the empty box means 1, a placeholder
    # A window: a lower and an upper limit. Half its width, in the row's unit, is the most room a design can have in it.
    window = _finite(target.lower) and _finite(target.upper) and target.upper > target.lower
    half = float(f'{(target.upper - target.lower) / 2:.12g}') if window else None
    row = dict(metric_id=target.metric_id, unit=target.unit, lower=target.lower, upper=target.upper, scale_stated=stated,
               scale_used=compiler.normalization_scale(target), measured=len(measured), misses=len(misses),
               median_miss=None, proposed_scale=None, limited=None, note=None, half_window=half)
    if misses:
        row['median_miss'] = statistics.median(misses) / factor
    few = len(misses) < MIN_MISSES or len(misses) < MIN_MISS_SHARE * len(measured)
    inside = 2 * len(misses) <= len(measured)            # at least half of the random designs are within this row's limits
    too_few = (f'{len(misses)} of {len(measured)} random designs miss this row: too few to name a typical miss.')
    if not compressed:
        pass
    elif few and not window:
        row['note'] = f'{too_few} Its Scale stays as it is.'
    elif target.direction_after_feasible != 'none':
        # One number, two jobs: on this row the Scale also measures how far the objective is past its limit (the objective
        # bonus), so a proposal from the misses would change what the bonus means. A judgment: in the test it made no
        # measurable difference whether this row was calibrated too (docs/decisions.md).
        row['note'] = 'This row carries the objective: its Scale also measures the objective bonus, so it stays as it is.'
    elif few and (row['scale_used'] <= half or not inside):
        row['note'] = f'{too_few} Its Scale stays as it is.'
    elif few:
        # A window few designs miss, with a Scale wider than half of it. The Scale then decides nothing about finding the
        # window, but the room inside it counts as at most half / Scale - and the margin bonus follows the row with the
        # least room, so it cannot pay for more than that on any row of the task.
        row['proposed_scale'] = proposed[target.metric_id] = half
        row['limited'] = 'window'
        row['note'] = (f'{too_few} Half the window is proposed: with the Scale in use ({_text(row["scale_used"], target.unit)}) the middle of '
                       f'the window counts as {half / row["scale_used"]:.2g} of a Scale away from its limits, and the margin bonus of the '
                       'whole task cannot pay for more room than that.')
    else:
        scale = row['median_miss']
        if from_limit:
            low, high = (bound * empty_box for bound in SCALE_WITHIN)
            if scale < low:
                scale, row['limited'] = low, 'low'
            elif scale > high:
                scale, row['limited'] = high, 'high'
            if row['limited']:
                row['note'] = (f'The typical miss is {_text(row["median_miss"], target.unit)}; the proposal is kept within '
                               f'{SCALE_WITHIN[0]:g} to {SCALE_WITHIN[1]:g} times the size of the limit.')
        scale = _round(scale)
        if window and scale > half and inside:
            # Most designs are inside the window already: what its Scale still decides is the margin bonus.
            scale, row['limited'] = half, 'window'
            row['note'] = (f'The typical miss is {_text(row["median_miss"], target.unit)}, more than half the window, and '
                           f'{len(measured) - len(misses)} of {len(measured)} random designs are inside it. The proposal is half the '
                           'window: a design inside it has at most that much room, and with a larger Scale the margin bonus of the '
                           'whole task could not pay for more.')
        elif window and scale > half:
            # Most designs miss the window: it has to be found first, and the typical miss as its Scale is what tells a
            # near design from a far one. Half the window - many times smaller - would make nearly all of them count the same.
            wider = (f'{len(misses)} of {len(measured)} random designs miss this window, so its Scale is their typical miss: the '
                     f'search has to find the window first. While that is wider than half the window ({_text(half, target.unit)}), a '
                     f'design inside counts as at most {half / scale:.2g} of a Scale clear, and the margin bonus of the whole task stays '
                     'that small.')
            row['note'] = f'{row["note"]} {wider}' if row['note'] else wider
        row['proposed_scale'] = proposed[target.metric_id] = scale
    return row


def _propose_alpha(config, designs, values, recorded, proposed, result):
    """The starting temperature for the reward the next run will have (the proposed Scales, the same reward settings),
    once the reward code reproduces what the run recorded; written into result['initial_alpha'] and
    result['reward_check']. Returns result['initial_alpha']."""
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
            alpha['estimate'] = estimate = _round(value)
            used = alpha['used']
            # the numbers as the page shows them: 0.025 against 0.05 is a factor of 2, and is proposed
            if _finite(used) and used > 0 and max(estimate / used, used / estimate) < ALPHA_FACTOR * (1 - 1e-9):
                # Close to the value the run had: no proposal. 0.011 to 0.014 against 0.01 made no measurable difference in the
                # tests; a factor of 4 did (docs/decisions.md).
                alpha['note'] = (f'Not proposed: the estimate is {alpha["estimate"]:g} ({ALPHA_PER_SD:g} x the reward spread), within a '
                                 f'factor of {ALPHA_FACTOR:g} of the {used:g} in use. The value in use stays.')
            else:
                alpha['proposed'] = alpha['estimate']
                if value != ALPHA_PER_SD * spread:
                    alpha['note'] = (f'{ALPHA_PER_SD:g} x the reward spread is {ALPHA_PER_SD * spread:.2g}; the proposal is kept within '
                                     f'{ALPHA_WITHIN[0]:g} to {ALPHA_WITHIN[1]:g}.')
    return alpha

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
    layout = RunLayout(run_dir)
    manifest = manifest if manifest is not None else read_dict(layout.manifest)
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


_AGAIN: dict = {}                          # run folder -> its result worked out again under today's rule (this process)


def current(run_dir, manifest=None):
    """A run's calibration as the page shows it: the run's own file - or, when that file was written under an older rule,
    the proposals worked out again from the run's recorded designs (record 7.217: the designs are simulated and paid for;
    only the arithmetic changed). Nothing is written: the run's file stays what the run said at its end, and the answer
    names both rules (`recalculated`). None: the run has no calibration result (yet)."""
    from pathlib import Path
    stored = read_json(Path(run_dir) / FILE, default=None)
    if not isinstance(stored, dict) or (stored.get('rule') or {}).get('version') == RULE:
        return stored
    key = str(run_dir)
    if key not in _AGAIN:
        try:
            again = from_run(run_dir, manifest)
            again.update(created_utc=stored.get('created_utc'),
                         recalculated=dict(from_rule=(stored.get('rule') or {}).get('version', 1), to_rule=RULE))
        except Exception:                  # its tables are gone or cannot be read: what the run said stands
            again = stored
        _AGAIN[key] = again
    return _AGAIN[key]
