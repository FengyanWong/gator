"""Bounded real M4 acceptance: baseline, three candidates, two SAC updates, restore."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import site
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


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
    parser.add_argument('--bridge-site-packages', type=Path,
                        help='Optional existing trusted bridge venv site-packages; no package installation')
    parser.add_argument('--seed', type=int, default=20260919)
    args = parser.parse_args()
    if args.bridge_site_packages:
        if not args.bridge_site_packages.is_dir():
            parser.error('Bridge site-packages directory does not exist')
        site.addsitedir(str(args.bridge_site_packages.resolve()))

    import torch
    from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend
    from analog_optimizer.envs.sizing import CircuitSizingEnv, write_record
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.models.graph_transformer import ModelConfig
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.training.runner import collect_episode
    from analog_optimizer.training.sac import SACLearner
    from verify_opamp_environment import metrics_match

    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    reference = json.loads(args.reference_measurements.read_text())
    if reference['origin'] != 'real':
        raise ValueError('Real baseline reference required')
    specs = tuple(MetricSpec(**raw) for raw in json.loads(args.specs.read_text())['specs'])
    profile = Gpdk045OtaProfile(
        design_file=ROOT / 'configs/gpdk045_opamp_design.json', mapping_file=ROOT / 'configs/gpdk045_opamp.json',
        reference_structure=ROOT / 'examples/circuits/gpdk045_ota5.scs',
        reference_readback=ROOT / 'examples/circuits/gpdk045_ota5.cdf.json')
    backend = VirtuosoBridgeBackend(BridgeConfig(args.env.resolve(), args.library, args.creation_receipt.resolve(),
                                               args.state_root.resolve(), args.model_file), profile)
    graph = profile.optimization_graph()
    env = CircuitSizingEnv(backend, graph, specs, args.output, max_steps=3, stop_on_success=False)
    experiment = dict(origin='real', split='single-design-training-smoke-no-heldout-evaluation',
                      designs=[{'library': args.library, 'model_file': args.model_file,
                                'design_sha256': hashlib.sha256((ROOT / 'configs/gpdk045_opamp_design.json').read_bytes()).hexdigest(),
                                'mapping_sha256': hashlib.sha256((ROOT / 'configs/gpdk045_opamp.json').read_bytes()).hexdigest(),
                                'reference_sha256': hashlib.sha256(args.reference_measurements.read_bytes()).hexdigest(),
                                'conditions_sha256': hashlib.sha256((ROOT / 'configs/gpdk045_conditions.json').read_bytes()).hexdigest()}],
                      groups=[asdict(g) for g in graph.parameter_groups], specs=[asdict(s) for s in specs],
                      condition=asdict(env.condition), seed=args.seed, max_steps=3)
    model_config = ModelConfig(hidden_dim=32, heads=4, layers=2)
    learner = SACLearner(experiment=experiment, model_config=model_config)
    replay = ReplayBuffer(origin='real', capacity=100, seed=args.seed)
    report = dict(passed=False, origin='real', simulation_budget=5, automatic_retries=0,
                  experiment=experiment, model_config=asdict(model_config), stages=[],
                  note='Fresh learner; one random warmup + two policy candidates; no convergence or performance claim.')
    stdout = sys.stdout
    start = perf_counter()
    try:
        with (env.directory / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log), env:
            # The collector owns the initial reset: intercept its returned baseline for comparison.
            original_reset = env.reset
            baselines = []
            def checked_reset():
                obs, info = original_reset()
                if obs is None or info['truncated'] or not info['evaluation_valid']:
                    raise RuntimeError('Baseline failed; inspect environment journal')
                if not metrics_match(obs.metrics, reference['metrics']):
                    raise RuntimeError('Nominal baseline differs from the verified reference')
                record = json.loads(Path(info['record_path']).read_text())
                baselines.append(record)
                return obs, info
            env.reset = checked_reset
            report['stages'] = collect_episode(env, learner, replay, rng, warmup=1, batch_size=2)
            env.reset()  # Fifth Spectre call verifies restoration, beyond parameter readback.
            report.update(baseline_record=baselines[0], restored_baseline_record=baselines[1],
                          same_restored_deck=baselines[0]['netlist_sha256'] == baselines[1]['netlist_sha256'],
                          same_restored_metrics=metrics_match(baselines[0]['metrics'], baselines[1]['metrics']))
            report['bridge_version'] = backend.bridge_version
        report['restored'] = json.loads((env.directory / 'restoration.json').read_text())['state'] == 'restored'
        checkpoint = env.directory / 'checkpoint.pt'
        learner.save(checkpoint, replay, run_state=dict(collector_rng=rng.getstate(), completed_episodes=1,
                                                       simulation_calls=env.simulation_calls))
        report.update(checkpoint=str(checkpoint), replay_size=len(replay), training_updates=learner.updates)
        expected = learner.update(replay.sample(2))
        restored, restored_replay, _ = SACLearner.load(checkpoint, experiment=experiment, model_config=model_config)
        actual = restored.update(restored_replay.sample(2))
        report['exact_resume'] = expected == actual and all(torch.equal(a, b) for a, b in zip(
            list(learner.actor.parameters()) + list(learner.critics.parameters()) + list(learner.targets.parameters()) + [learner.log_alpha],
            list(restored.actor.parameters()) + list(restored.critics.parameters()) + list(restored.targets.parameters()) + [restored.log_alpha]))
        report['passed'] = (env.simulation_calls == 5 and len(replay) == 3 and report['training_updates'] == 2
                            and all(report[k] for k in ('restored', 'same_restored_deck', 'same_restored_metrics', 'exact_resume')))
        if not report['passed']:
            raise RuntimeError('Real SAC smoke acceptance failed')
        for stage in report['stages']:
            print(json.dumps({k: stage[k] for k in ('action_source', 'proposal', 'reward', 'success')}),
                  file=stdout, flush=True)
    except BaseException as exc:
        report.update(passed=False, exception_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report.update(simulation_calls=env.simulation_calls, elapsed_seconds=perf_counter() - start)
        write_record(env.directory / 'report.json', report)
        print('REPORT', env.directory / 'report.json', file=stdout, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
