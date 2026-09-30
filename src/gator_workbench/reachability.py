"""Non-blocking, read-only corner reachability evidence. No simulator or bridge calls."""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache
import json
import math
from pathlib import Path
from .reward_diagnostics import file_identity, kept, tables_version


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


_DESIGNS: dict = {}                     # run folder -> (what its designs were read from, _recorded_designs)
_SAVED: dict = {}                       # effective_config.json -> (its stat, its content)


def _designs(run):
    """_recorded_designs, read again only when the run's tables or its corner checks' results changed. Every validation
    of an OTA7 task with corners asks for it (after each page edit, on readiness, on every Agent request), and reading
    the tables is slow: 346 data parts per call for five 400-evaluation runs, a second on local disk, more on the 9p mount."""
    run = Path(run)
    checks = sorted((run / 'corner_checks').glob('*/results.jsonl'))
    version = (tables_version(run / 'data'), tuple((path.parent.name, file_identity(path)) for path in checks))
    return kept(_DESIGNS, str(run), version, lambda: _recorded_designs(run))


def _saved(run):
    """A run's effective_config.json as saved, read again only when the file changed (a continued run rewrites it)."""
    from .storage.atomic import read_json
    path = Path(run) / 'effective_config.json'
    return kept(_SAVED, str(path), file_identity(path), lambda: read_json(path, default={}) or {})


def _qualification_reference(config, *, all_candidates=False):
    """Retained reward-v2 qualification, named explicitly; never scan artifacts/.

    This is optional recorded evidence, not a runtime dependency or a claim of
    reachability. Current hard specs are recomputed from its raw measured values.
    """
    from .paths import repo_root
    if config.circuit.task_id != 'real:gpdk045_ota7':
        return []
    root = repo_root() / 'artifacts/local/reward-v2-real/20260926-qualification-04'
    version = file_identity(root / 'stage-a/report.json')
    report = _stage_a_report(str(root), version)
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
                try:
                    text = _job_result(job['artifact_directory'], str(root), version)
                except FileNotFoundError:
                    text = None
                result = None if text is None else json.loads(text)      # parsed afresh: the caller owns what it gets
                if result:
                    rows[result['condition']['corner']['id']] = result
        if rows:
            designs.append(dict(id=name, conditions=rows))
    return designs


# The retained qualification is read once per version of its reports (their stat), not on every validation: each resolve
# and read there costs milliseconds on the 9p-mounted repository (0.7 s per validation of OTA7 with four corners). The job
# results are written before the report that names them, and never after, so the report's stat stands for them too.
@lru_cache(maxsize=4)
def _stage_a_report(root, version):
    """The stage-A report. `version`, its stat, only keys the cache."""
    from .storage.atomic import read_json
    return read_json(Path(root) / 'stage-a/report.json', default={}) or {}


@lru_cache(maxsize=64)
def _job_result(directory, root, version):
    """The text of a job's result.json; None when it lies outside `root`. A missing file raises, and is not kept.
    `version`, the stat of the report that names the job, only keys the cache."""
    path = Path(directory) / 'result.json'
    if not path.resolve().is_relative_to(Path(root).resolve()):
        return None
    return path.read_text(encoding='utf8')


def _qualification_runs(config):
    from .paths import repo_root
    if config.circuit.task_id != 'real:gpdk045_ota7':
        return []
    root = repo_root() / 'artifacts/local/reward-v2-real/20260926-qualification-05'
    return list(_stage_runs(str(root), tuple(file_identity(root / f'stage-{stage}/report.json') for stage in ('b', 'c'))))


@lru_cache(maxsize=4)
def _stage_runs(root, versions):
    """The run folders the stage-B and stage-C reports name inside `root`. `versions`, their stats, only key the cache."""
    from .storage.atomic import read_json
    root, paths = Path(root), []
    for stage in ('b', 'c'):
        report = read_json(root / f'stage-{stage}/report.json', default={}) or {}
        directory = report.get('run_directory')
        if directory and Path(directory).resolve().is_relative_to(root.resolve()):
            paths.append(Path(directory))
    return tuple(paths)


def check(config, *, roots=None):
    from .paths import OutputRoots
    from . import runs
    from .layout import find_runs
    from .schema import WorkbenchConfig
    if config.run.conditions.policy == 'off':
        return None
    roots = roots or OutputRoots()
    root = config.output.output_root or runs.remembered_output_root()
    designs = _qualification_reference(config, all_candidates=True)
    run_dirs = set(_qualification_runs(config))
    if roots.is_allowed(root):
        run_dirs.update(find_runs(root))
    for run in sorted(run_dirs):
        # A run that cannot be read is no evidence, and never a failed validation: one saved with an option removed since
        # (an encoder) used to make every validation of this task an HTTP 500 (review of 2026-09-29), and a damaged file
        # or data part did too.
        try:
            saved = _saved(run)
            if saved.get('circuit', {}).get('task_id') != config.circuit.task_id:
                continue
            # Changed probe definitions cannot reinterpret old metric names.
            previous = WorkbenchConfig.model_validate(saved)
            if previous.measurements == config.measurements:
                designs.extend(_designs(run))
        except Exception:
            continue
    return assess(config, designs)
