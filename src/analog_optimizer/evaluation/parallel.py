"""Parallel independent seeds; every seed retains isolated learners and replays."""
import json
from pathlib import Path
from time import perf_counter

from analog_optimizer.envs.sizing import write_record
from analog_optimizer.training.workers import OwnedWorker, worker_progress, wait_workers
from .transfer import aggregate_runs


def _seed(tasks, factory, directory, origin, settings, provenance, seed, baseline_check, recorder, limits):
    import torch
    from .benchmark import run_benchmark
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    worker_progress(dict(seed=seed, operation='initialize'))
    return run_benchmark(tasks, factory, directory, origin=origin, settings=settings, provenance=provenance,
                         progress=worker_progress, baseline_check=baseline_check, recorder=recorder,
                         limits=limits, _execution_seeds=[seed])


def run_seeds(tasks, factory, directory, *, origin, settings, provenance, report, baseline_check,
              recorder, limits, max_workers, progress):
    seeds, pools, results, active = settings['seeds'], [], {}, {}
    count = min(max_workers, len(seeds))
    report.update(worker_count=count, scheduling='independent seeds; one sequential environment per process',
                  worker_shutdown=[], unfinished_seeds=[], errors=[])
    started, primary = perf_counter(), None
    try:
        for lane in range(count):
            pools.append(OwnedWorker(lane, limits))
        for start in range(0, len(seeds), count):
            batch = seeds[start:start+count]
            active = {lane: seed for lane, seed in enumerate(batch)}
            pending = {lane: pools[lane].submit(_seed, tasks, factory, Path(directory) / f'seed-{seed}',
                origin, settings, provenance, seed, baseline_check, recorder, limits, heartbeat=True)
                for lane, seed in active.items()}
            for lane, future in wait_workers(pending):
                seed = active[lane]
                try:
                    results[seed] = future.result()
                except BaseException as exc:
                    primary = primary or exc
                    report['errors'].append(dict(seed=seed, type=type(exc).__name__, message=str(exc)))
                    report['unfinished_seeds'].append(dict(seed=seed, state='unconfirmed',
                        last_progress=future.future.progress, recovery='inspect recorded evaluations; do not retry automatically'))
                else:
                    progress(f'Seed {seed} completed: {results[seed]["calls"]} calls')
                    active.pop(lane, None)
                if primary is not None:
                    # Stop the batch immediately after a stalled seed is detected.
                    # Peers retain their durable evaluations and last phase report.
                    raise primary
            if primary:
                raise primary
            active = {}
        report['completed'] = True
    except BaseException as exc:
        primary = exc
        report.update(completed=False, exception_type=type(exc).__name__, error=str(exc))
    finally:
        known = {row['seed'] for row in report['unfinished_seeds']}
        report['unfinished_seeds'].extend(dict(seed=seed, state='interrupted',
            recovery='inspect recorded evaluations; no automatic retry')
            for seed in active.values() if seed not in known)
        for pool in pools:
            try:
                stopped = pool.shutdown()
                report['worker_shutdown'].append(stopped)
                if stopped['state'] == 'still_alive':
                    raise RuntimeError('Benchmark worker did not stop')
            except BaseException as exc:
                primary = primary or exc
                report.setdefault('cleanup_errors', []).append(str(exc))
        # Read only completed on-disk phase reports for failed/interrupted seeds.
        for seed in seeds:
            path = Path(directory) / f'seed-{seed}' / 'report.json'
            if seed not in results and path.exists():
                try:
                    results[seed] = json.loads(path.read_text())
                except Exception as exc:
                    report.setdefault('cleanup_errors', []).append(str(exc))
        for key in ('phases', 'test_runs', 'pretraining_costs'):
            report[key] = [row for seed in seeds for row in results.get(seed, {}).get(key, [])]
        report['calls'] = sum(r['calls'] for r in results.values())
        report['call_count_kind'] = 'confirmed_phase_reports' if primary is None else 'confirmed_lower_bound'
        report['seed_reports'] = {str(seed): str(Path(directory) / f'seed-{seed}' / 'report.json') for seed in results}
        finished = {(r['task'], r['method'], r['seed']) for r in report['test_runs']}
        report['unexecuted_test_runs'] = [dict(task=t.id, method=m, seed=s) for t in tasks if t.partition == 'test'
                                        for m in report['methods'] for s in seeds if (t.id, m, s) not in finished]
        report['cost_by_partition'] = {part: dict(calls=sum(r['calls'] for r in report['phases'] if r['partition'] == part),
            wall_seconds=sum(r['wall_seconds'] for r in report['phases'] if r['partition'] == part))
            for part in ('train', 'validation', 'test')}
        report.update(completed=primary is None, aggregate=aggregate_runs(report['test_runs']),
                      real_simulation_calls=report['calls'] if origin == 'real' else 0,
                      synthetic_calls=report['calls'] if origin == 'synthetic' else 0,
                      elapsed_seconds=perf_counter()-started)
        try:
            write_record(Path(directory) / 'report.json', report)
        except BaseException as exc:
            primary = primary or exc
    if primary is not None:
        raise primary
    return report
