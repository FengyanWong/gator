"""M6 synthetic leave-one-class-out acceptance, with one source policy per fold.

No electrical solver is used. Each encoder independently trains on two classes,
then runs scratch/frozen/adapt on the third, alongside random and pattern search.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from analog_optimizer.envs.sizing import write_record
from analog_optimizer.evaluation.benchmark import benchmark_call_budget, run_benchmark
from analog_optimizer.evaluation.cross_category import category_tasks, load_categories
from analog_optimizer.evaluation.transfer import digest
from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.training.sac import source_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/local/m6-cross-category')
    parser.add_argument('--heldout', nargs='+', choices=['opamp', 'ldo', 'vco'], default=['opamp', 'ldo', 'vco'])
    parser.add_argument('--encoders', nargs='+', choices=ENCODER_TYPES, default=list(ENCODER_TYPES))
    parser.add_argument('--seeds', nargs='+', type=int, default=[17, 29, 43])
    parser.add_argument('--pretrain-steps', type=int, default=4)
    parser.add_argument('--test-steps', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--hidden-dim', type=int, default=32)
    parser.add_argument('--heads', type=int, default=4)
    parser.add_argument('--layers', type=int, default=2)
    parser.add_argument('--max-calls', type=int, default=1800, help='Total across ALL requested folds and seeds')
    parser.add_argument('--dry-run', action='store_true', help='Validate all folds and budget without evaluations')
    args = parser.parse_args()
    if len(set(args.heldout)) != len(args.heldout):
        parser.error('Held-out classes must be unique')
    factory, schema, provenance = load_categories(ROOT)
    provenance['entrypoint_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    settings = {key: getattr(args, key) for key in (
        'seeds', 'encoders', 'pretrain_steps', 'test_steps', 'batch_size', 'hidden_dim', 'heads', 'layers', 'max_calls')}
    settings.update(spec_schema=asdict(schema), max_workers=1)
    folds = {name: category_tasks(factory, name) for name in args.heldout}
    budgets = {name: benchmark_call_budget(tasks, settings) for name, tasks in folds.items()}
    total = sum(budgets.values())
    if total > args.max_calls:
        parser.error(f'Planned {total} calls across all folds exceed max_calls={args.max_calls}')
    # Freeze every direction and its provenance before the first evaluation.
    plan = dict(version='m6-cross-category-suite-v1', origin='synthetic', settings=settings,
                source_sha256=source_digest(), provenance=provenance, planned_calls=total,
                folds={name: dict(planned_calls=budgets[name], tasks=[asdict(t) for t in tasks])
                       for name, tasks in folds.items()})
    plan['sha256'] = digest(plan)
    if args.dry_run:
        print(json.dumps(dict(origin='synthetic', planned_calls=total, folds=budgets,
                              action_counts={k: sum(g.mutable for g in v.parameter_groups)
                                             for k, v in factory.graphs.items()}, plan_sha256=plan['sha256']), indent=2))
        return 0
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True)
    write_record(directory / 'suite-protocol.json', plan)
    report = dict(completed=False, origin='synthetic', real_simulation_calls=0, synthetic_calls=0,
                  planned_calls=total, suite_sha256=plan['sha256'], folds={},
                  electrical_performance_validated=False)
    started = perf_counter()
    try:
        for name, tasks in folds.items():
            fold_report = {}
            try:
                run_benchmark(tasks, factory, directory / name, origin='synthetic',
                    settings=dict(settings, max_calls=budgets[name]),
                    provenance=dict(provenance, suite_sha256=plan['sha256'], heldout_class=name), report=fold_report)
            finally:
                report['folds'][name] = dict(completed=fold_report.get('completed', False),
                    calls=fold_report.get('calls', 0), report=str(directory / name / 'report.json'))
                report['synthetic_calls'] = sum(r['calls'] for r in report['folds'].values())
        report['completed'] = all(r['completed'] for r in report['folds'].values())
    except BaseException as exc:
        report.update(exception_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report['elapsed_seconds'] = perf_counter() - started
        report['unexecuted_folds'] = [name for name in folds if name not in report['folds']]
        write_record(directory / 'report.json', report)
        print('REPORT', directory / 'report.json', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
