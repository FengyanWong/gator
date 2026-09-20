"""Audit saved LDO qualification runs without invoking Virtuoso or Spectre."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from verify_ldo_baseline import make_profile, qualification_specs
from analog_optimizer.backends.virtuoso_bridge import digest, write_json
from analog_optimizer.backends.spectre_validation import validate_completion
from analog_optimizer.measurements.specs import SpecificationEvaluator


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parameters(rows):
    return {(r['device'], r['parameter']): r['value'] for r in rows}


def check_metrics(job, expected):
    """Recompute the qualified fixed testbench metrics directly from saved PSF."""
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, scalar, vector, frequency_hz
    result = read(job / 'bridge_result.json')
    raw = Path(result['metadata']['output_dir'])
    data = {k: read_psf_ascii(result_file(raw, v)) for k, v in (
        ('dc', 'dcOp.dc'), ('line', 'lineSweep.dc'), ('load', 'loadSweep.dc'),
        ('ac', 'ac.ac'), ('tran', 'tran.tran.tran'))}
    def values(dataset, name):
        return [complex(v).real for v in vector(data[dataset], name)]
    output = scalar(data['dc'], 'VOUT')
    supply = scalar(data['dc'], 'VDD')
    supply_current = -scalar(data['dc'], 'VDD:p')
    load = scalar(data['dc'], 'ILOAD:i')
    require(math.isclose(supply, 1.) and math.isclose(load, 1e-5), 'Incorrect DC stimuli')
    metrics = dict(output_dc_v=output, supply_power_w=supply*supply_current,
                   ldo_output_error_v=abs(output-.8), ldo_quiescent_current_a=supply_current-load)
    for name, signal, low, high, metric in (
        ('line', 'VDD', .95, 1.05, 'ldo_line_regulation_v_per_v'),
        ('load', 'ILOAD:i', 1e-5, 2e-5, 'ldo_load_regulation_v_per_a')):
        x, y = values(name, signal), values(name, 'VOUT')
        require(math.isclose(x[0], low) and math.isclose(x[-1], high), 'Sweep endpoints changed')
        metrics[metric] = abs((y[-1]-y[0])/(high-low))
    frequencies = frequency_hz(data['ac'])
    index = next(i for i, f in enumerate(frequencies) if math.isclose(f, 1000.))
    vin, vout = vector(data['ac'], 'VDD')[index], vector(data['ac'], 'VOUT')[index]
    metrics['ldo_psrr_1khz_db'] = 20*math.log10(abs(vin)/abs(vout))
    t, v, current = (values('tran', s) for s in ('time', 'VOUT', 'ILOAD:i'))
    require(t[0] == 0 and math.isclose(t[-1], 80e-6), 'Transient coverage changed')
    pre = [i for i, time in enumerate(t) if 5e-6 <= time <= 9e-6]
    tail = [v[i] for i, time in enumerate(t) if time >= 66e-6]
    require(all(math.isclose(current[i], 1e-5) for i in pre), 'Initial load changed')
    require(all(math.isclose(current[i], 2e-5) for i, time in enumerate(t) if time >= 10.1e-6),
            'Held load step missing')
    baseline = sum(v[i] for i in pre)/len(pre)
    metrics.update(ldo_step_deviation_v=max(abs(value-baseline) for time, value in zip(t, v) if time >= 10e-6),
                   ldo_step_final_shift_v=abs(sum(tail)/len(tail)-baseline),
                   ldo_step_tail_ripple_v=max(tail)-min(tail))
    require(metrics.keys() == expected.keys(), 'Metric identities changed')
    for name, value in metrics.items():
        require(math.isclose(value, expected[name], rel_tol=1e-9, abs_tol=1e-14), f'Metric mismatch: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verification', nargs='+', type=Path)
    parser.add_argument('--bridge-site-packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import site
    site.addsitedir(str(args.bridge_site_packages.resolve()))
    profile = make_profile()
    evaluator = SpecificationEvaluator(qualification_specs())
    counts, jobs = Counter(), set()
    wall_seconds = 0.
    report = dict(passed=False, new_simulator_calls=0, verification=[str(p.resolve()) for p in args.verification])
    try:
        for path in args.verification:
            saved, directory = read(path), path.resolve().parent
            require(read(directory/'before.json') == read(directory/'after.json'), 'Snapshots differ')
            manifests = {}
            for manifest_path in directory.rglob('manifest.json'):
                manifest = read(manifest_path)
                if manifest.get('cell') != profile.design['testbench_cell']:
                    continue
                if manifest_path.parent != Path(manifest['structure_path']).parent:
                    continue  # A simulation job also preserves a copy of its export manifest.
                for name, sha in manifest['files'].items():
                    require(digest(manifest_path.parent/name) == sha, f'Export digest mismatch: {name}')
                actual = profile.validate_export(manifest['original_structure_path'], read(manifest_path.parent/'readback.json'))
                require(actual == parameters(manifest['applied_parameters']), 'Export CDF differs')
                manifests[manifest['executed_sha256']] = manifest
            found = sorted(directory.rglob('simulations/*/result.json'))
            count = saved.get('confirmed_invocations', saved.get('calls'))
            require(len(found) == count, 'Recorded call count differs from saved results')
            for result_path in found:
                job, result = result_path.parent, read(result_path)
                require(result['job_id'] not in jobs, 'Duplicate simulation job')
                jobs.add(result['job_id'])
                require(result['simulator_invocations'] == 1, 'Unknown invocation count')
                bridge = read(job/'bridge_result.json')
                validate_completion((job/'results/spectre.out').read_text(), bridge['metadata']['returncode'], bridge['errors'])
                manifest = manifests[digest(job/'ldo.scs')]
                require(result['condition'] == manifest['condition'], 'Condition mismatch')
                require(parameters(result['applied_parameters']) == parameters(manifest['applied_parameters']), 'Executed parameters differ')
                counts[result['status']] += 1
                wall_seconds += result['elapsed_seconds']
                if result['status'] == 'ok':
                    check_metrics(job, result['metrics'])
                    evaluation = evaluator.evaluate(result['metrics'], result['metric_units'], result['metric_validity'])
                    require(evaluation.valid and evaluation.success, 'Qualification criterion failed')
                else:
                    require(result['status'] == 'measurement_error' and not result['metrics'], 'Unexpected failure')
            for record_path in saved.get('records', []):
                record = read(record_path)
                require(record['state'] == 'completed' and record['replay_eligible'] == (record['kind'] == 'step')
                        and not record['cache_hit'], 'Invalid environment record')
                result = read(Path(record['artifact_directory'])/'result.json')
                require(record['metrics'] == result['metrics'], 'Environment metrics differ')
                evaluation = evaluator.evaluate(result['metrics'], result['metric_units'], result['metric_validity'])
                require(record['reward'] == evaluation.reward and record['success'] == evaluation.success, 'Reward mismatch')
            stages = saved.get('stages', [])
            for stage in stages:
                result = read(Path(stage['job'])/'result.json')
                require(stage['metrics'] == result['metrics'] and stage['status'] == result['status'], 'Stage result mismatch')
                if stage['name'] in ('baseline_repeat', 'restored'):
                    require(stage['metrics'] == stages[0]['metrics'] and stage['netlist_sha256'] == stages[0]['netlist_sha256'], 'Baseline repeat differs')
        report.update(passed=True, existing_simulator_calls=len(jobs), statuses=dict(counts),
                      metric_recomputations=counts['ok'], summed_simulation_and_measurement_seconds=wall_seconds)
    except BaseException as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_json(args.output, report)
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
