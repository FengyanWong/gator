"""Recompute default rewards on the manifest-listed REAL M6 records, without loading learners.

This is recorded-data arithmetic validation, not a repeat of the physical or checkpoint audit.
The frozen protocol supplies each task's specs; records cannot choose their own goal.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct

from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
from analog_optimizer.training.sac import source_digest


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(directory):
    directory = Path(directory).resolve()
    report = read(directory / 'report.json')
    plan = read(directory / 'suite-protocol.json')
    digest = plan.pop('sha256')
    require(hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest() == digest == report['plan_sha256'],
            'Frozen protocol hash differs')
    require(report['origin'] == 'real' and report['completed'], 'A completed real report is required')
    records, counts, exclusions, failures = set(), Counter(), Counter(), []

    def check(path, task, category):
        path = Path(path).resolve()
        require(path.is_relative_to(directory) and path not in records, 'Duplicate or escaped record path')
        records.add(path)
        row = read(path)
        require(row['origin'] == 'real', 'Synthetic record in real manifest')
        counts[category] += 1
        if not (row['state'] == 'completed' and row['status'] == 'ok' and row['evaluation_valid']
                and row['candidate_evaluated'] and row['simulation_dispatched'] and not row['cache_hit']):
            exclusions[f"{row['state']}:{row['status']}"] += 1
            return
        require(row['observation']['specs'] == task['specs'], f'Goal mismatch: {path}')
        result = SpecificationEvaluator(MetricSpec(**spec) for spec in task['specs']).evaluate(
            row['metrics'], row['metric_units'], row['metric_validity'])
        counts['eligible'] += 1
        same = struct.pack('!d', result.reward) == struct.pack('!d', row['reward']) if result.reward is not None else False
        close = result.reward is not None and math.isclose(result.reward, row['reward'], rel_tol=0, abs_tol=1e-12)
        verdict = result.valid == row['evaluation_valid'] and result.success == row['success'] and result.violations == row['violations']
        counts['bitwise_equal'] += same
        counts['absolute_1e_12_equal'] += close
        counts['verdict_and_violations_equal'] += verdict
        if not (same and close and verdict):
            failures.append(dict(record=str(path), saved_reward=row['reward'], computed_reward=result.reward,
                                 bitwise_equal=same, absolute_1e_12_equal=close, verdict_equal=verdict))

    for heldout, tasks in plan['folds'].items():
        fold = read(directory / heldout / 'report.json')
        by_id = {task['id']: task for task in tasks}
        before = len(records)
        for phase in fold['phases']:
            for path in phase['records']:
                check(path, by_id[phase['task']], 'fold_records')
        require(len(records) - before == plan['budget']['folds'][heldout]['total'] == fold['calls'], 'Fold coverage differs')
    for final in report['final_checks']:
        require(final['passed'] and final['calls'] == 1, 'Final baseline incomplete')
        task = next(t for t in plan['folds'][final['circuit_class']] if t['partition'] == 'test')
        check(final['record'], task, 'final_check_records')
    require(counts['final_check_records'] == plan['budget']['final_baseline_calls'] == 3, 'Missing final baselines')
    require(len(records) == report['calls'] == plan['budget']['total_calls'] == 2811, 'Manifest coverage differs')
    return dict(kind='recorded-real-reward-identity', origin='real', fresh_simulator_calls=0,
                source_digest=source_digest(), historical_plan_sha256=digest, manifest_records=len(records),
                counts=dict(counts), exclusions=dict(exclusions), failures=failures,
                passed=not failures and not exclusions and counts['eligible'] == 2811,
                scope='Reward/spec arithmetic only; no fresh simulation, raw PSF audit or historical learner loading')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
