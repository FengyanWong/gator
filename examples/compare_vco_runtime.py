"""Compare fast VCO evaluations against saved reference runs at identical widths."""
import argparse
import json
from pathlib import Path
import re
from statistics import mean

from audit_vco_baseline import read, require
from analog_optimizer.backends.virtuoso_bridge import write_json


# Frozen before the first fast trial; qualification guards are unchanged.
LIMITS = {k:('relative',.001) for k in ('vco_frequency_low_hz','vco_frequency_hz',
    'vco_frequency_high_hz','vco_tuning_gain_hz_per_v','vco_tuning_fraction')}
LIMITS.update(supply_power_w=('relative',.005),vco_minimum_swing_v=('absolute',.001),
              vco_duty_cycle=('absolute',.001),vco_startup_detection_s=('absolute',2e-9))


def load_jobs(paths, mode):
    jobs = {}
    for path in paths:
        saved = read(path)
        require(saved['passed'], 'Unsuccessful qualification report')
        require(saved.get('analysis_settings',{}).get('mode','reference') == mode, 'Wrong analysis mode')
        require(saved.get('timestep_scale',1.) == 1., 'Half-step is a separate precision check')
        found = sorted(path.resolve().parent.rglob('simulations/*/result.json'))
        require(len(found) == saved.get('confirmed_invocations',saved.get('calls')), 'Call count mismatch')
        for result_path in found:
            result = read(result_path)
            require(result['status'] == 'ok' and result['simulator_invocations'] == 1, 'Invalid execution')
            require(result['job_id'] not in jobs, 'Duplicate job')
            jobs[result['job_id']] = (result_path.parent,result)
    return list(jobs.values())


def identity(result):
    # Same width assignment and nominal context, irrespective of report order.
    return (tuple(sorted((r['device'],r['parameter'],r['value']) for r in result['applied_parameters'])),
            json.dumps(result['condition'],sort_keys=True))


def timing(job, result):
    log = (job/'results/spectre.out').read_text()
    seconds = re.findall(r'elapsed time \(wall clock\): ([\d.]+) s',log)
    steps = re.findall(r'Number of accepted tran steps\s*=\s*(\d+)',log)
    require(len(seconds)==1 and len(steps)==3, 'Incomplete timing evidence')
    metadata = read(job/'bridge_result.json')['metadata']
    accumulated = re.findall(r'Time accumulated: CPU = [^,]+, elapsed = ([\d.]+) (ms|s)\.',log)
    require(bool(accumulated), 'Missing accumulated elapsed time')
    elapsed, unit = accumulated[-1]
    raw = Path(metadata['output_dir'])
    files = list(raw.glob('tran*.tran.tran'))
    require(len(files)==3, 'Missing raw transient files')
    # Spectre's aggregate footer can disagree with its own analysis clock and
    # Python's monotonic timer. Preserve both; use external elapsed for speedup.
    return dict(spectre_reported_wall_seconds=float(seconds[0]),
                spectre_accumulated_elapsed_seconds=float(elapsed)*(1e-3 if unit=='ms' else 1),
                bridge_remote_exec_seconds=metadata['timings']['remote_exec'],
                backend_seconds=result['elapsed_seconds'],
                accepted_steps=sum(map(int,steps)),transient_bytes=sum(p.stat().st_size for p in files))


def compare(reference, candidate, expected_unique_points):
    reference_by_point = {}
    for job,result in reference:
        reference_by_point.setdefault(identity(result),(job,result))
    rows, seen = [], set()
    for job,result in candidate:
        key = identity(result)
        require(key in reference_by_point, 'No reference at these device widths/condition')
        before_job,before = reference_by_point[key]
        require(read(job/'bridge_result.json')['source_sha256'] ==
                read(before_job/'bridge_result.json')['source_sha256'], 'Physical netlists differ')
        comparisons = {}
        for metric,(mode,limit) in LIMITS.items():
            a,b = before['metrics'][metric],result['metrics'][metric]
            difference = abs(b-a)/(abs(a) if mode=='relative' else 1.)
            comparisons[metric] = dict(reference=a,candidate=b,difference=difference,
                                       mode=mode,limit=limit,passed=difference<=limit)
        for metric,limit in (('vco_max_period_spread',.02),('vco_max_window_drift',.01)):
            require(result['metrics'][metric] <= limit, 'Oscillation stability failed')
        rows.append(dict(job=str(job),reference_job=str(before_job),parameters=result['applied_parameters'],
                         comparisons=comparisons,timing=timing(job,result)))
        seen.add(key)
    require(len(seen)==expected_unique_points, 'Incomplete unique width coverage')
    def summary(values):
        return {k:dict(mean=mean(v[k] for v in values),minimum=min(v[k] for v in values),
                       maximum=max(v[k] for v in values)) for k in values[0]}
    return dict(passed=all(c['passed'] for row in rows for c in row['comparisons'].values()),
        new_simulator_calls=0,reference_calls=len(reference),candidate_calls=len(candidate),
        unique_points=len(seen),limits=LIMITS,comparisons=rows,
        reference_timing=summary([timing(j,r) for j,r in reference]),
        candidate_timing=summary([row['timing'] for row in rows]),
        maximum_differences={k:max(row['comparisons'][k]['difference'] for row in rows) for k in LIMITS})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',nargs='+',type=Path,required=True)
    parser.add_argument('--candidate',nargs='+',type=Path,required=True)
    parser.add_argument('--expected-unique-points',type=int,default=8)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    report = compare(load_jobs(args.reference,'reference'),load_jobs(args.candidate,'fast'),args.expected_unique_points)
    write_json(args.output,report)
    print(json.dumps({k:v for k,v in report.items() if k!='comparisons'},indent=2))
    if not report['passed']:
        raise ValueError('Fast analysis exceeds frozen agreement limits')


if __name__ == '__main__':
    main()
