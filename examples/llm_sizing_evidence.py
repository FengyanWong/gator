"""Benchmark-only progress and independent validation; never a learning signal."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
from pathlib import Path
from time import perf_counter

from gator_workbench.analoggym import native_values
from gator_workbench.storage.atomic import read_json, write_json

PROTOCOL = 'llm-sizing-comparison-v2'


def validate_comparison(config, bundle, plan):
    comparison = (plan or {}).get('comparison', {})
    if comparison.get('protocol') != PROTOCOL:
        raise ValueError('AnalogGym comparison requires the revised frozen comparison plan (--plan)')
    if bundle['name'] not in comparison['circuits']:
        raise ValueError('Circuit is outside the frozen comparison cohort')
    if config.run.max_evaluations != comparison['evaluations_per_run']:
        raise ValueError('All comparison arms must use the same frozen per-run evaluation budget')
    if config.run.seed not in comparison['seeds']:
        raise ValueError('Seed is outside the frozen comparison plan')
    if config.run.max_wall_seconds is not None or config.run.max_spectre_launches is not None:
        raise ValueError('Evaluation-budget comparison must not have a competing wall-time or simulator-launch limit')
    if config.run.conditions.policy != 'off':
        raise ValueError('AnalogGym comparison uses the nominal upstream testbenches only')


class PassingDesignVerifier:
    """Called after a durable evaluation and before retention / the next dispatch.

    The original simulation alone feeds replay. Checks have separate directories,
    counts and timing. A durable STOP marker prevents subsequent arms sharing this
    output root from starting after a mismatch or unresolved verification.
    """
    def __init__(self, bundle, run_dir, output, *, timeout=120, verify=None):
        self.bundle, self.root = bundle, Path(run_dir) / 'upstream-verification'
        self.stop_file = Path(output) / 'comparison-STOP.json'
        self.timeout, self.verify = timeout, verify
        self.records = []
        self.seconds = 0.

    def __call__(self, evaluation, record):
        passed = bool(evaluation['all_hard_constraints_satisfied'])
        item = dict(evaluation_id=evaluation['evaluation_id'], gator_passed=passed,
                    passed=False, simulator_processes=0, error=None)
        started = perf_counter()
        try:
            if passed:
                write_json(self.stop_file, dict(reason='Verification pending', run_dir=str(self.root.parent),
                                               evaluation_id=evaluation['evaluation_id']))
            directory = record.get('artifact_directory')
            source = Path(directory) / 'benchmark.json' if directory else None
            native = read_json(source) if source and source.is_file() else None
            if not passed and not evaluation['valid'] and native is None:
                return  # An infrastructure failure need not have simulator output.
            if native is None:
                raise ValueError('Valid design has no native benchmark evidence')
            if passed != native['upstream_passed']:
                raise ValueError('GATOR/upstream verdict disagreement on imported outputs')
            if not passed:
                return
            applied = {(p['device'], p['parameter']): p['value'] for p in record['applied_parameters']}
            values = native_values(self.bundle, applied)
            destination = self.root / evaluation['evaluation_id']
            verify = self.verify
            if verify is None:
                from calibrate_analoggym import verify_pass
                verify = verify_pass
            item.update(verify(self.bundle, values, native['native_metrics'], destination, timeout=self.timeout))
            item['native_values'] = values
        except Exception as exc:
            item['error'] = f'{type(exc).__name__}: {exc}'[:1000]
        item['elapsed_seconds'] = perf_counter() - started
        self.seconds += item['elapsed_seconds']
        self.records.append(item)
        write_json(self.root / 'summary.json', self.summary())
        if not item['passed']:
            write_json(self.stop_file, dict(reason='Independent verification failed; comparison stopped', **item))
            raise RuntimeError('Independent upstream verification failed; see upstream-verification/summary.json')
        self.stop_file.unlink(missing_ok=True)

    def summary(self):
        return dict(required=True, passing_designs=sum(r['gator_passed'] for r in self.records),
                    verified_passes=sum(r['passed'] for r in self.records),
                    simulator_processes=sum(r['simulator_processes'] for r in self.records),
                    elapsed_seconds=self.seconds, failed=any(not r['passed'] for r in self.records),
                    tolerance_relative=1e-9, tolerance_absolute=0., records=list(self.records))


def constraint_progress(evaluations, metrics=(), *, budget):
    """Uncapped worst hard-spec violation: minimize on valid complete designs.

    Never combine individual specs from different designs into a feasible design.
    Invalid evaluations consume the x-axis but cannot improve the incumbent.
    """
    by_id = defaultdict(list)
    for row in metrics:
        if row.get('hard') and row.get('aggregation_level') == 'aggregate':
            by_id[row['evaluation_id']].append(dict(metric=row['metric_name'], value=row.get('raw_value'),
                violation=row.get('violation'), valid=row.get('valid'), satisfied=row.get('satisfied')))
    trajectory, best, baseline = [], None, None
    rows = sorted(evaluations, key=lambda r: r['commit_seq'])
    def timestamp(value):
        return value if isinstance(value, datetime) else datetime.fromisoformat(value)
    start = timestamp(rows[0]['started_at']) if rows and rows[0].get('started_at') else None
    for index, row in enumerate(rows, 1):
        value = row.get('normalized_constraint_violation')
        valid = bool(row['valid']) and value is not None and math.isfinite(value)
        if index == 1 and valid:
            baseline = value
        if valid and (best is None or value < best['violation']):
            best = dict(evaluation_id=row['evaluation_id'], evaluation=index, violation=value,
                        specs=by_id[row['evaluation_id']])
        elapsed = ((timestamp(row['completed_at']) - start).total_seconds()
                   if start and row.get('completed_at') else row.get('elapsed_seconds'))
        trajectory.append(dict(evaluation=index, evaluation_id=row['evaluation_id'], elapsed_seconds=elapsed,
            valid=valid, feasible=bool(row['all_hard_constraints_satisfied']), specs=by_id[row['evaluation_id']],
            violation=value if valid else None, best_violation=None if best is None else best['violation'],
            best_evaluation_id=None if best is None else best['evaluation_id']))
    checkpoints = sorted({n for n in (1, 60, 100, 250, 500, 1000, 2000, 5000, budget) if n <= budget})
    return dict(definition='Minimum across valid designs of their largest uncapped normalized hard-spec violation',
        budget=budget, completed_evaluations=len(rows), baseline_violation=baseline, best_design=best,
        improvement=None if baseline is None or best is None else baseline-best['violation'],
        checkpoints=[dict(evaluation=n, reached=n<=len(rows),
            best_violation=trajectory[n-1]['best_violation'] if n<=len(rows) else None) for n in checkpoints],
        trajectory=trajectory)


def summarize_comparison(results):
    """Descriptive, unpooled circuit/method/provider/budget groups, including early endings."""
    grouped = defaultdict(list)
    for result in results:
        cfg = result['configuration']
        key = (cfg['circuit']['task_id'], result['arm'], result['provider'],
               cfg['run']['max_evaluations'], cfg['run']['search'].get('model'), cfg['run']['search'].get('effort'),
               result.get('steered', False), result.get('degraded', False))
        grouped[key].append(result)
    groups = []
    for (circuit, arm, provider, budget, model, effort, steered, degraded), rows in grouped.items():
        successes = sum(r['success'] for r in rows)
        groups.append(dict(circuit=circuit, arm=arm, provider=provider, evaluations_per_run=budget,
            model=model, effort=effort, steered=steered, degraded=degraded, runs=len(rows), successes=successes, success_rate=successes/len(rows),
            runs_reaching_budget=sum(r['budget_reached'] for r in rows),
            best_violations=[(r['constraint_progress']['best_design'] or {}).get('violation') for r in rows],
            seeds=[r['seed'] for r in rows], verification_failed=any(r['verification'].get('failed') for r in rows),
            run_dirs=[r['run_dir'] for r in rows]))
    return dict(protocol=PROTOCOL, groups=groups,
                valid_for_comparison=not any(g['verification_failed'] for g in groups),
                note='All supplied runs remain in denominators. Early endings are explicit; no ranking or pooled circuit claim.')
