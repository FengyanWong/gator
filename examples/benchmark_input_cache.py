"""Offline input-cache timings; synthetic fixtures, never a Spectre speed claim."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def timed(call):
    start = perf_counter()
    result = call()
    return perf_counter() - start, result


def main():
    import torch
    import torch_geometric
    from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
    from analog_optimizer.envs.sizing import CircuitSizingEnv
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.models import ENCODER_TYPES, ModelConfig
    from analog_optimizer.models.inputs import ObservationTensorCache, batch_observations
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    from analog_optimizer.training.replay import Transition
    from analog_optimizer.training.sac import SACLearner, source_digest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/local/input-cache-benchmark')
    parser.add_argument('--repeats', type=int, default=30)
    parser.add_argument('--updates', type=int, default=8)
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()
    if min(args.repeats, args.updates, args.batch_size) < 1:
        parser.error('Counts must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    transitions, calls = [], 0
    for name in ('opamp', 'ldo'):
        graph = SpectreParser(ParserConfig.from_file(ROOT / f'configs/{name}.json')).parse_file(
            ROOT / f'tests/fixtures/synthetic/{name}.scs')
        backend = SyntheticSizingBackend(graph, targets={'w': .4, 'c': -.3})
        specs = (MetricSpec('score', 'fixture', 'min', 1, lower=.95),)
        with CircuitSizingEnv(backend, graph, specs, args.output / 'candidates', max_steps=8,
                              stop_on_success=False, expected_origin='synthetic') as env:
            observation, _ = env.reset()
            for i in range(8):
                proposal = {group: -.8 + i * .2 for group in env.mapper.group_ids}
                step = env.step(proposal)
                transitions.append(Transition.from_step(observation, proposal, step))
                observation = step[0]
        assert backend.parameters == backend.initial
        calls += backend.calls
    batch = [transitions[i % len(transitions)] for i in range(args.batch_size)]
    observations = [t.observation for t in batch]
    cache = ObservationTensorCache()
    topologies_only = ObservationTensorCache(0)
    cold, _ = timed(lambda: batch_observations(observations, cache=cache))
    # Warm interpreter and collation before measuring paired, alternating modes.
    for _ in range(3):
        batch_observations(observations)
        batch_observations(observations, cache=cache)
        batch_observations(observations, cache=topologies_only)
    timings = {name: [] for name in ('uncached', 'topology_only', 'warm_inputs')}
    modes = {'uncached': None, 'topology_only': topologies_only, 'warm_inputs': cache}
    for i in range(args.repeats):
        copies = deepcopy(observations)
        for name in (tuple(modes) if i % 2 else tuple(reversed(modes))):
            elapsed, _ = timed(lambda: batch_observations(copies, cache=modes[name]))
            timings[name].append(elapsed)
    batch_times = {name: median(values) * 1000 for name, values in timings.items()}
    models = []
    experiment = {'origin': 'synthetic', 'split': 'cache-timing-fixture', 'designs': ['opamp', 'ldo']}
    for encoder in ENCODER_TYPES:
        config = ModelConfig(hidden_dim=32, heads=4, layers=2, encoder_type=encoder)
        torch.manual_seed(731)
        cached = SACLearner(experiment=experiment, model_config=config)
        torch.manual_seed(731)
        uncached = SACLearner(experiment=experiment, model_config=config,
                              input_cache_capacity=0, topology_cache_capacity=0)
        models_by_mode = {'uncached': uncached, 'warm_inputs': cached}
        durations = {name: [] for name in models_by_mode}
        for i in range(args.updates + 2):
            copied = deepcopy(batch)
            rng = torch.get_rng_state()
            results = {}
            for name in (tuple(models_by_mode) if i % 2 else tuple(reversed(models_by_mode))):
                torch.set_rng_state(rng)
                elapsed, results[name] = timed(lambda: models_by_mode[name].update(copied))
                if i >= 2:  # Optimizer/runtime/cache warmup.
                    durations[name].append(elapsed)
            assert results['uncached'] == results['warm_inputs']
        for component in ('actor', 'critics', 'targets'):
            for a, b in zip(getattr(cached, component).parameters(), getattr(uncached, component).parameters()):
                assert torch.equal(a, b)
        assert torch.equal(cached.log_alpha, uncached.log_alpha)
        elapsed = {name: median(values) * 1000 for name, values in durations.items()}
        models.append({'encoder': encoder, 'model_config': asdict(config), 'median_update_ms': elapsed,
                       'speedup': elapsed['uncached'] / elapsed['warm_inputs'],
                       'exact_losses_and_parameters': True, 'cache': cached.input_cache.info()})
    report = dict(origin='synthetic', real_simulation_calls=0, analytic_evaluations=calls,
                  batch_size=args.batch_size, input_repeats=args.repeats, update_repeats=args.updates,
                  threads=torch.get_num_threads(), torch=str(torch.__version__),
                  pyg=str(torch_geometric.__version__), code_sha256=source_digest(),
                  timing_scope='CPU input batching and full SAC.update; replay deepcopy and backend calls excluded',
                  cold_input_batch_ms=cold * 1000, median_input_batch_ms=batch_times,
                  input_speedup=batch_times['uncached'] / batch_times['warm_inputs'],
                  cache=cache.info(), models=models)
    path = args.output / 'report.json'
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'report': str(path), 'median_input_batch_ms': batch_times,
                      'input_speedup': report['input_speedup'],
                      'update_speedup': {r['encoder']: r['speedup'] for r in models}}, indent=2))


if __name__ == '__main__':
    main()
