"""Goal views (plan sections 3 and 4.2): one case's limits, explicit scales, preferred direction and the experiment's
reward settings, as a run configuration the workbench's own compiler accepts.

A view is built from a TEMPLATE - a recorded `effective_config.json` of the case's reference task - by changing only
its target rows and its reward settings: every row takes the view's limits and its explicit scale (decision D4: a
tightened row keeps its base scale), the preferred metric its direction, the other rows none. Its identity is the
compiled specs, the preference and the reward settings, hashed (`identity`). The same view as a target set of
`pretrain` (`target_set`) re-scores archived designs as a run of the view does; `parity` checks that, design by design.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from types import SimpleNamespace

from .. import units
from ..compile import normalization_scale

FORMAT = 'archive-compare-goal-view-v1'
DIRECTIONS = {'minimize': 'min', 'maximize': 'max'}
SIDES = {'<=': ('upper',), '>=': ('lower',), 'interval': ('lower', 'upper')}


def canonical(value) -> str:
    """Encode sorted compact JSON while rejecting non-finite numbers."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value) -> str:
    """Hash a value's canonical JSON representation."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _in_unit(canonical, unit, own, *, difference=False):
    """`canonical` (a limit, or a scale when `difference`) written in the row's own `unit`: the template's own number
    `own` when it already converts to exactly `canonical`, else the converted number, checked to convert back exactly."""
    if canonical is None:
        return None
    convert = units.scale_to_canonical if difference else units.to_canonical
    if own is not None and convert(own, unit) == canonical:
        return own
    _, factor, offset = units.LOOKUP[unit]
    value = canonical / factor if difference else (canonical - offset) / factor
    for _ in range(4):                               # the nearest float that converts back exactly, if a step away
        if convert(value, unit) == canonical:
            return value
        value = math.nextafter(value, math.inf if convert(value, unit) < canonical else -math.inf)
    raise ValueError(f'{canonical!r} cannot be written exactly in {unit}')


def view_config(template: dict, view: dict, reward: dict) -> dict:
    """The run configuration of `view` (a goal view of cases.json: rows with metric, canonical unit, constraint, lower,
    upper, scale; preferred_metric and preferred_direction) built from `template`. A template row may state its numbers
    in another unit of the same quantity (um for a length): the view's canonical numbers are written in that unit, exactly
    (`_in_unit`). Refuses a template whose active rows are not exactly the view's rows, or whose row differs in quantity,
    constraint kind or hardness."""
    rows = {row['metric']: row for row in view['rows']}
    config = deepcopy(template)
    active = [t for t in config['targets'] if t.get('active', True)]
    if {t['metric_id'] for t in active} != set(rows) or len(active) != len(rows):
        raise ValueError(f"The template's active rows {sorted(t['metric_id'] for t in active)} are not the view's "
                         f'{sorted(rows)}')
    if view['preferred_metric'] not in rows or view['preferred_direction'] not in DIRECTIONS:
        raise ValueError(f"Unknown preferred metric or direction: {view['preferred_metric']!r} {view['preferred_direction']!r}")
    for target in active:
        row = rows[target['metric_id']]
        if (units.canonical_unit(target['unit']) != row['unit'] or target['constraint'] != row['constraint']
                or not target['hard']):
            raise ValueError(f"{target['metric_id']}: the template row ({target['unit']}, {target['constraint']}, "
                             f"hard={target['hard']}) differs from the view's ({row['unit']}, {row['constraint']})")
        for side in ('lower', 'upper'):
            if (row[side] is None) != (side not in SIDES[row['constraint']]):
                raise ValueError(f"{target['metric_id']}: a {row['constraint']} row states exactly its {SIDES[row['constraint']]}")
        own_scale = normalization_scale(SimpleNamespace(normalization_scale=target.get('normalization_scale'),
                                                        lower=target['lower'], upper=target['upper']))
        target.update(lower=_in_unit(row['lower'], target['unit'], target['lower']),
                      upper=_in_unit(row['upper'], target['unit'], target['upper']),
                      normalization_scale=_in_unit(row['scale'], target['unit'], own_scale, difference=True),
                      direction_after_feasible=view['preferred_direction'] if target['metric_id'] == view['preferred_metric'] else 'none')
    config['run']['reward'] = dict(reward)
    return config


def identity(compiled, settings) -> tuple[dict, str]:
    """(record, sha256) of a compiled view: its specs (every field of the optimizer's MetricSpec, in canonical units),
    its preference and its reward settings - what decides how a design is scored, and nothing else."""
    record = dict(format=FORMAT, specs=[asdict(spec) for spec in compiled.specs], preference=compiled.preference,
                  reward_settings=asdict(settings))
    return record, digest(record)


def target_set(compiled) -> dict:
    """The compiled view as one target set of `pretrain.relabel_targets`: every active row's limits (canonical units),
    its scale and its objective, so a re-scored copy carries exactly these specs."""
    rows = {}
    for spec in compiled.specs:
        if not spec.active:
            continue
        entry = {side: getattr(spec, side) for side in ('lower', 'upper') if getattr(spec, side) is not None}
        rows[spec.metric_id] = dict(entry, scale=spec.scale, objective=spec.objective)
    return rows


def evaluation_row(metrics: dict, validity: dict, units: dict, status: str):
    """One nominal condition row as the optimizer's evaluator reads it, from recorded raw values: `metrics` and `validity`
    by metric (missing values stay missing), `units` the canonical unit of each, `status` the evaluation's recorded status."""
    return SimpleNamespace(condition=None, status=status, candidate_evaluated=True,
                           metrics={k: v for k, v in metrics.items() if v is not None},
                           metric_units={k: units[k] for k, v in metrics.items() if v is not None},
                           metric_validity={k: bool(validity.get(k)) for k, v in metrics.items() if v is not None})


def fresh_evaluation(compiled, settings, metrics, validity, status):
    """The view's own evaluation of one recorded design - the reward a run of the view would give it."""
    from analog_optimizer.measurements.specs import SpecificationEvaluator
    units = {spec.metric_id: spec.unit for spec in compiled.specs}
    return SpecificationEvaluator(compiled.specs, settings).evaluate_conditions(
        (evaluation_row(metrics, validity, units, status),))
