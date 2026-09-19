"""Finite real DC/AC acceptance: baseline, bounds, seeded random widths, repeat, restore."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import math
from pathlib import Path
import random
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend
from analog_optimizer.envs import CircuitSizingEnv
from analog_optimizer.envs.sizing import write_record
from analog_optimizer.measurements.specs import MetricSpec


def build_plan(seed, random_candidates):
    rng = random.Random(seed)
    initial_state = rng.getstate()
    candidates = [('lower_bound', -1.0), ('upper_bound', 1.0)]
    candidates += [(f'random_{i + 1}', rng.uniform(-1, 1)) for i in range(random_candidates)]
    candidates.append(('repeat_previous', candidates[-1][1]))
    return candidates, initial_state, rng.getstate()


def metrics_match(first, second):
    return first.keys() == second.keys() and all(
        (a is None and second[k] is None) or
        (a is not None and second[k] is not None and math.isclose(a, second[k], rel_tol=1e-6, abs_tol=1e-12))
        for k, a in first.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--creation-receipt', type=Path, required=True)
    parser.add_argument('--model-file', required=True)
    parser.add_argument('--reference-measurements', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=ROOT / 'artifacts/local/bridge-state')
    parser.add_argument('--specs', type=Path, default=ROOT / 'configs/gpdk045_opamp_smoke_specs.json')
    parser.add_argument('--seed', type=int, default=20260919)
    parser.add_argument('--random-candidates', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.random_candidates <= 20:
        parser.error('--random-candidates must be between 1 and 20')
    specification = json.loads(args.specs.read_text())
    specs = [MetricSpec(**s) for s in specification['specs']]
    reference = json.loads(args.reference_measurements.read_text())
    if reference['origin'] != 'real':
        raise ValueError('Reference must contain real baseline measurements')
    profile = Gpdk045OtaProfile(
        design_file=ROOT / 'configs/gpdk045_opamp_design.json',
        mapping_file=ROOT / 'configs/gpdk045_opamp.json',
        reference_structure=ROOT / 'examples/circuits/gpdk045_ota5.scs',
        reference_readback=ROOT / 'examples/circuits/gpdk045_ota5.cdf.json')
    backend = VirtuosoBridgeBackend(BridgeConfig(
        args.env.resolve(), args.library, args.creation_receipt.resolve(),
        args.state_root.resolve(), args.model_file), profile)
    plan, initial_rng, final_rng = build_plan(args.seed, args.random_candidates)
    env = CircuitSizingEnv(backend, profile.optimization_graph(), specs, args.output,
                           max_steps=len(plan), stop_on_success=False)
    stdout = sys.stdout
    report = {'passed': False, 'origin': 'real', 'seed': args.seed,
              'rng_initial': initial_rng, 'rng_after_plan': final_rng,
              'purpose': specification.get('purpose'), 'plan': plan,
              'simulation_budget': len(plan) + 2, 'stages': [],
              'notes': ['Acceptance targets are not a held-out optimization benchmark.',
                        'Phase margin is an open-loop estimate; no STB or transient validation.',
                        'Power excludes a physical bias generator.']}
    started = perf_counter()

    def collect(name, observation, info, reward=None):
        record = json.loads(Path(info['record_path']).read_text())
        stage = {'name': name, 'candidate_id': info['candidate_id'], 'job_id': info['job_id'],
                 'status': info['status'], 'success': info['success'], 'reward': reward,
                 'width_m': record['applied_parameters'][0]['value'],
                 'metrics': record['metrics'], 'violations': info['violations'],
                 'netlist_sha256': record['netlist_sha256'], 'record_path': info['record_path'],
                 'duplicate_of': info['duplicate_of'], 'elapsed_seconds': record['elapsed_seconds'],
                 'timings': record['timings']}
        report['stages'].append(stage)
        write_record(env.directory / 'verification.json', report)
        print(json.dumps({k: stage[k] for k in ('name', 'status', 'width_m', 'success', 'reward')}),
              file=stdout, flush=True)
        if info['status'] != 'ok' or not info['evaluation_valid'] or info['truncated'] or observation is None:
            raise RuntimeError(f'{name}: evaluation did not complete; inspect {info["record_path"]}')
        return stage

    try:
        with (env.directory / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log), env:
            report.update(bridge_version=backend.bridge_version, backend_session_directory=str(backend.session_dir))
            obs, info = env.reset()
            baseline = collect('baseline', obs, info)
            if not metrics_match(baseline['metrics'], reference['metrics']):
                raise RuntimeError('Baseline metrics differ from the previously verified reference')
            for index, (name, action) in enumerate(plan):
                obs, reward, terminated, truncated, info = env.step({'input_pair_width': action})
                collect(name, obs, info, reward)
                if terminated != (index == len(plan) - 1) or truncated:
                    raise RuntimeError('Unexpected episode boundary')
            count = env.simulation_calls
            try:
                env.step({'input_pair_width': 0})
            except RuntimeError:
                report['budget_enforced'] = env.simulation_calls == count
            else:
                raise RuntimeError('Step budget was not enforced')
            obs, info = env.reset()
            restored = collect('restored_baseline', obs, info)
            previous, repeated = report['stages'][-3:-1]
            report.update(
                same_restored_deck=baseline['netlist_sha256'] == restored['netlist_sha256'],
                repeated_baseline_metrics=metrics_match(baseline['metrics'], restored['metrics']),
                repeat_identified=repeated['duplicate_of'] == previous['candidate_id'],
                repeat_same_deck=previous['netlist_sha256'] == repeated['netlist_sha256'],
                repeat_same_metrics=metrics_match(previous['metrics'], repeated['metrics']),
                changed_deck=baseline['netlist_sha256'] != report['stages'][1]['netlist_sha256'],
                observed_feasible_and_infeasible={s['success'] for s in report['stages']} == {True, False},
                simulation_calls=env.simulation_calls)
        restoration = json.loads((env.directory / 'restoration.json').read_text())
        report['restored'] = restoration['state'] == 'restored'
        checks = ('budget_enforced', 'same_restored_deck', 'repeated_baseline_metrics', 'repeat_identified',
                  'repeat_same_deck', 'repeat_same_metrics', 'changed_deck', 'observed_feasible_and_infeasible', 'restored')
        report['passed'] = all(report[k] for k in checks) and env.simulation_calls == report['simulation_budget']
        if not report['passed']:
            raise RuntimeError('Environment acceptance checks failed')
    except BaseException as exc:
        report.update(passed=False, exception_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report.update(simulation_calls=env.simulation_calls, elapsed_seconds=perf_counter() - started)
        write_record(env.directory / 'verification.json', report)
        print('REPORT', env.directory / 'verification.json', file=stdout, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
