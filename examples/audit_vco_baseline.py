"""Audit saved VCO qualification runs without invoking Virtuoso or Spectre."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from verify_vco_baseline import make_profile, qualification_specs
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
    """Independently recompute fixed-contract VCO metrics using NumPy arrays."""
    import numpy as np
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, vector
    result = read(job/'bridge_result.json')
    raw = Path(result['metadata']['output_dir'])
    all_stages, points = [], {}
    start, stop = 1e-6, 2e-6
    if result.get('analysis_settings') is not None:
        start, stop = (result['analysis_settings'][k] for k in ('start_s','stop_s'))
    for label, control in (('Low',.55),('Nom',.65),('High',.75)):
        data = read_psf_ascii(result_file(raw,f'tran{label}.tran.tran'))
        def values(key):
            values = np.asarray(vector(data,key),dtype=complex)
            require(np.all(values.imag == 0) and np.all(np.isfinite(values)), 'Non-real or nonfinite trace')
            return values.real
        t = values('time')
        require(t[0] == 0 and math.isclose(t[-1],stop) and np.all(np.diff(t)>0), 'Time coverage mismatch')
        require(np.allclose(values('VDD'),1.,rtol=1e-6,atol=1e-9), 'Supply mismatch')
        require(np.allclose(values('VCTRL'),control,rtol=1e-6,atol=1e-9), 'Control mismatch')
        stages = {}
        for node in ('XU1.N1','XU1.N2','VOUT'):
            v = values(node)
            def edges(up):
                ix = np.flatnonzero((v[:-1]<.5)&(v[1:]>=.5) if up else (v[:-1]>.5)&(v[1:]<=.5))
                return t[ix]+(.5-v[ix])*(t[ix+1]-t[ix])/(v[ix+1]-v[ix])
            rises, falls = edges(True), edges(False)
            edges_late = rises[(rises>=start)&(rises<=stop)]
            periods = np.diff(edges_late)
            require(len(periods)>=8, 'Insufficient cycles')
            middle = (start+stop)/2
            first = periods[edges_late[1:]<=middle]
            second = periods[edges_late[:-1]>=middle]
            require(min(len(first),len(second))>=8, 'Insufficient half-window cycles')
            median = np.median(periods)
            require(np.max(np.diff(t[max(0,np.searchsorted(t,start)-1):])) <= min(periods)/40,
                    'Undersampled oscillation')
            require(np.ptp(periods)/median <= .02 and abs(np.mean(first)-np.mean(second))/median <= .01,
                    'Unsettled or drifting oscillation')
            swings, duties = [], []
            def cycle(a,b):
                wave = v[np.searchsorted(t,a):np.searchsorted(t,b,side='right')]
                fall = falls[(falls>a)&(falls<b)]
                if len(wave)==0 or len(fall)!=1 or wave.min()>.2 or wave.max()<.8 or np.ptp(wave)<.8:
                    return None
                return float(np.ptp(wave)),float((fall[0]-a)/(b-a))
            for a,b in zip(edges_late,edges_late[1:]):
                c = cycle(a,b); require(c is not None, 'Swing/crossing failure')
                swings.append(c[0]); duties.append(c[1])
            consecutive, detected = 0, None
            for a,b in zip(rises,rises[1:]):
                good = abs((b-a)-median)/median<=.02 and cycle(a,b) is not None
                consecutive = consecutive+1 if good else 0
                if consecutive>=8:
                    detected=float(b);break
            require(detected is not None and detected<=start, 'Startup detection failure')
            stages[node] = dict(frequency=1/float(np.mean(periods)),swing=min(swings),
                duty=float(np.mean(duties)),spread=float(np.ptp(periods)/median),
                drift=float(abs(np.mean(first)-np.mean(second))/median),startup=detected)
        current = values('VDD:p')
        tx = np.concatenate(([start],t[(t>start)&(t<stop)],[stop]))
        ix = np.interp(tx,t,current)
        power = -float(np.sum(np.diff(tx)*(ix[1:]+ix[:-1])/2)/(stop-start))
        require(power > 0, 'Invalid power')
        frequencies = [s['frequency'] for s in stages.values()]
        require(np.ptp(frequencies)/np.mean(frequencies) <= .01, 'Stage frequencies differ')
        points[label] = dict(stages=stages,power=power)
        all_stages.extend(stages.values())
    low,nom,high = (points[k]['stages']['VOUT']['frequency'] for k in ('Low','Nom','High'))
    require(low < nom < high, 'Nonmonotonic tuning')
    metrics = dict(vco_frequency_hz=nom,vco_frequency_low_hz=low,vco_frequency_high_hz=high,
        vco_tuning_gain_hz_per_v=(high-low)/(.75-.55),vco_tuning_fraction=(high-low)/nom,
        supply_power_w=points['Nom']['power'],vco_minimum_swing_v=min(s['swing'] for s in all_stages),
        vco_max_period_spread=max(s['spread'] for s in all_stages),
        vco_max_window_drift=max(s['drift'] for s in all_stages),
        vco_startup_detection_s=max(s['startup'] for s in all_stages),
        vco_duty_cycle=points['Nom']['stages']['VOUT']['duty'])
    require(metrics.keys() == expected.keys(), 'Metric identity mismatch')
    for name,value in metrics.items():
        require(math.isclose(value,expected[name],rel_tol=1e-8,abs_tol=1e-12), f'Metric mismatch: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verification', nargs='+', type=Path)
    parser.add_argument('--bridge-site-packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import site
    site.addsitedir(str(args.bridge_site_packages.resolve()))
    evaluator = SpecificationEvaluator(qualification_specs())
    counts, jobs = Counter(), set()
    wall_seconds = 0.
    report = dict(passed=False, new_simulator_calls=0, verification=[str(p.resolve()) for p in args.verification])
    try:
        for path in args.verification:
            saved, directory = read(path), path.resolve().parent
            settings = saved.get('analysis_settings')
            profile = make_profile(analysis_mode=settings['mode'] if settings else 'reference',
                                   timestep_scale=saved.get('timestep_scale',1.))
            require(settings is None or settings == profile.analysis_settings, 'Unknown numerical policy')
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
                require(manifest.get('analysis_settings') == settings, 'Export analysis settings differ')
                expected_deck = profile.build_deck(Path(manifest['structure_path']).read_text(),
                    manifest['model_file'], manifest['section'], temperature_c=manifest['temperature_c'])
                require((manifest_path.parent/'vco.scs').read_text() == expected_deck, 'Executed numerical policy differs')
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
                manifest = manifests[digest(job/'vco.scs')]
                require(bridge.get('analysis_settings') == settings, 'Simulation analysis settings differ')
                require(result['condition'] == manifest['condition'], 'Condition mismatch')
                require(parameters(result['applied_parameters']) == parameters(manifest['applied_parameters']), 'Executed parameters differ')
                counts[result['status']] += 1
                wall_seconds += result['elapsed_seconds']
                if result['status'] == 'ok':
                    require(read(job/'measurements.json').get('analysis_settings') == settings, 'Measurement policy differs')
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
