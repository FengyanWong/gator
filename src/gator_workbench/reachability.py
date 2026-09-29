"""Non-blocking, read-only corner reachability evidence. No simulator or bridge calls."""
from __future__ import annotations
from collections import defaultdict
import math
from pathlib import Path


def assess(config, designs):
    from .compile import build_specs
    from .spec_equations import SpecPlan
    specs, _, _ = build_specs(config)
    hard = [s for s in specs if s.active and s.required]
    plan = SpecPlan.from_config(config)
    conditions = ['nominal', *config.run.conditions.corners]
    ranked = []
    for design in designs:
        misses, unknown = [], 0
        for condition in conditions:
            row = design['conditions'].get(condition, {})
            if row.get('status') not in ('ok', 'measurement_error') or not row.get('candidate_evaluated'):
                unknown += max(1, sum(not s.nominal_only or condition == 'nominal' for s in hard))
                continue
            raw = {k: v for k, v in row.get('metrics', {}).items() if row.get('metric_validity', {}).get(k) is True
                   and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)}
            # Wrong units cannot establish reachability, even when a number looks plausible.
            from .units import canonical_unit
            for probe in config.measurements:
                key = probe.source_name
                if key and row.get('metric_units', {}).get(key) != canonical_unit(probe.unit):
                    raw.pop(key, None)
            values = plan.spec_values(probes=plan.probe_values(raw))
            for spec in hard:
                if spec.nominal_only and condition != 'nominal':
                    continue
                value = values.get(spec.metric_id)
                if value is None or not math.isfinite(value):
                    unknown += 1
                    continue
                distance = max(0., (spec.lower - value) if spec.lower is not None else 0.,
                               (value - spec.upper) if spec.upper is not None else 0.)
                if distance:
                    misses.append(dict(metric=spec.metric_id, condition=condition, distance=distance,
                                       unit=spec.unit, normalized=distance / spec.scale))
        misses.sort(key=lambda m: -m['normalized'])
        if hard and not misses and not unknown:
            return dict(observed_feasible=True, design=design['id'], checked_designs=len(designs), warning=None)
        ranked.append((unknown, max((m['normalized'] for m in misses), default=0.),
                       sum(m['normalized'] for m in misses), design['id'], misses))
    best = min(ranked, key=lambda item: item[:3]) if ranked else None
    detail = ''
    if best:
        name = 'The reference' if best[3] == 'reference' else f'The best recorded design ({best[3]})'
        detail = ' ' + name + ' misses ' + '; '.join(
            f"{m['metric']} at {m['condition']} by {m['distance']:.3g} {m['unit']}" for m in best[4][:3]) + '.' if best[4] else ''
        if best[0]:
            detail += f' {best[0]} required condition/spec results are unavailable for that design.'
    message = ('No recorded design of this task meets every hard spec at every planned condition.' + detail +
               ' Use Corner check on the reference or a recorded design before choosing targets or wider parameter ranges. This warning does not block a start.')
    return dict(observed_feasible=False, checked_designs=len(designs), best_design=None if best is None else best[3],
                worst_misses=[] if best is None else best[4][:3], warning=message)


def _recorded_designs(run_dir):
    from .storage.dataset import DatasetReader
    from .storage.atomic import read_jsonl
    reader = DatasetReader(Path(run_dir) / 'data')
    grouped = defaultdict(lambda: defaultdict(lambda: dict(status='ok', candidate_evaluated=True,
        metrics={}, metric_units={}, metric_validity={})))
    status_by_id = {r['evaluation_id']: r.get('status') for r in reader.rows('evaluations', ['evaluation_id', 'status'])}
    for row in reader.rows('metrics'):
        if row.get('aggregation_level') != 'condition':
            continue
        condition = grouped[row['evaluation_id']][row['condition']]
        condition['status'] = status_by_id.get(row['evaluation_id']) or 'unavailable'
        condition['candidate_evaluated'] = condition['status'] in ('ok', 'measurement_error')
        name = row['metric_name']
        condition['metrics'][name] = row['raw_value']
        condition['metric_units'][name] = row['unit']
        condition['metric_validity'][name] = row['valid']
    designs = [dict(id=key, conditions=dict(value)) for key, value in grouped.items()]
    for path in sorted((Path(run_dir) / 'corner_checks').glob('*/results.jsonl')):
        grouped_check = defaultdict(dict)
        for row in read_jsonl(path):
            grouped_check[row['evaluation_id']][row['corner']] = row
        designs.extend(dict(id=key, conditions=rows) for key, rows in grouped_check.items())
    return designs


def _qualification_reference(config, *, all_candidates=False):
    """Retained reward-v2 qualification, named explicitly; never scan artifacts/.

    This is optional recorded evidence, not a runtime dependency or a claim of
    reachability. Current hard specs are recomputed from its raw measured values.
    """
    from .paths import repo_root
    from .storage.atomic import read_json
    if config.circuit.task_id != 'real:gpdk045_ota7':
        return []
    root = repo_root() / 'artifacts/local/reward-v2-real/20260926-qualification-04'
    report = read_json(root / 'stage-a/report.json', default={}) or {}
    jobs = {j['label']: j for j in report.get('jobs', [])}
    names = ['reference']
    if all_candidates:
        names += [row['candidate'] for row in report.get('aggregates', []) if row['candidate'] != 'baseline']
    designs = []
    for name in names:
        labels = (['baseline_nominal_1', *[f'derived_{c}' for c in config.run.conditions.corners]] if name == 'reference'
                  else [f'{name}_{c}' for c in ['nominal', *config.run.conditions.corners]])
        rows = {}
        for label in labels:
            job = jobs.get(label)
            if job:
                path = Path(job['artifact_directory']) / 'result.json'
                if not path.resolve().is_relative_to(root.resolve()):
                    continue
                result = read_json(path, default=None)
                if result:
                    rows[result['condition']['corner']['id']] = result
        if rows:
            designs.append(dict(id=name, conditions=rows))
    return designs


def _qualification_runs(config):
    from .paths import repo_root
    from .storage.atomic import read_json
    if config.circuit.task_id != 'real:gpdk045_ota7':
        return []
    root = repo_root() / 'artifacts/local/reward-v2-real/20260926-qualification-05'
    paths = []
    for stage in ('b', 'c'):
        report = read_json(root / f'stage-{stage}/report.json', default={}) or {}
        directory = report.get('run_directory')
        if directory and Path(directory).resolve().is_relative_to(root.resolve()):
            paths.append(Path(directory))
    return paths


def check(config, *, roots=None):
    from .paths import OutputRoots
    from . import runs
    from .layout import find_runs
    from .storage.atomic import read_json
    if config.run.conditions.policy == 'off':
        return None
    roots = roots or OutputRoots()
    root = config.output.output_root or runs.remembered_output_root()
    designs = _qualification_reference(config, all_candidates=True)
    run_dirs = set(_qualification_runs(config))
    if roots.is_allowed(root):
        run_dirs.update(find_runs(root))
    for run in sorted(run_dirs):
        saved = read_json(run / 'effective_config.json', default={}) or {}
        if saved.get('circuit', {}).get('task_id') != config.circuit.task_id:
            continue
        # Changed probe definitions cannot reinterpret old metric names.
        from .schema import WorkbenchConfig
        previous = WorkbenchConfig.model_validate(saved)
        if previous.measurements == config.measurements:
            designs.extend(_recorded_designs(run))
    return assess(config, designs)
