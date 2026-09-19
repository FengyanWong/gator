"""Run frozen M5 synthetic topology checks or a bounded real specification pilot."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import site
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def build_tasks(origin):
    from analog_optimizer.evaluation.transfer import TransferTask
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    if origin == 'synthetic':
        graph = SpectreParser(ParserConfig.from_file(ROOT / 'configs/opamp.json')).parse_file(
            ROOT / 'tests/fixtures/synthetic/opamp.scs')
        heldout = SpectreParser(ParserConfig.from_file(ROOT / 'configs/opamp_two_stage.json')).parse_file(
            ROOT / 'tests/fixtures/synthetic/opamp_two_stage.scs')
        return [TransferTask(name, split, transfer, 'synthetic_ota', g,
                            (MetricSpec('score', 'fixture', 'min', 1, lower=target),))
                for name, split, transfer, g, target in [
                    ('toy-train-90', 'train', 'specification', graph, .90),
                    ('toy-train-94', 'train', 'specification', graph, .94),
                    ('toy-validation-96', 'validation', 'specification', graph, .96),
                    ('toy-test-spec-98', 'test', 'specification', graph, .98),
                    ('toy-test-topology-98', 'test', 'topology', heldout, .98)]]
    from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
    profile = make_profile()
    graph = profile.optimization_graph()
    raw = json.loads((ROOT / 'configs/gpdk045_opamp_transfer.json').read_text())
    base = tuple(MetricSpec(**s) for s in raw['common_specs'])
    return [TransferTask(t['id'], t['partition'], 'specification', 'gpdk045_ota', graph,
                         base + tuple(MetricSpec(**s) for s in t['specs'])) for t in raw['tasks']]


def make_profile():
    from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
    return Gpdk045OtaProfile(design_file=ROOT / 'configs/gpdk045_opamp_design.json',
                           mapping_file=ROOT / 'configs/gpdk045_opamp.json',
                           reference_structure=ROOT / 'examples/circuits/gpdk045_ota5.scs',
                           reference_readback=ROOT / 'examples/circuits/gpdk045_ota5.cdf.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', choices=['synthetic', 'real'], default='synthetic')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/local/m5')
    parser.add_argument('--seeds', nargs='+', type=int, default=[17, 29, 43])
    parser.add_argument('--pretrain-steps', type=int)
    parser.add_argument('--test-steps', type=int)
    parser.add_argument('--max-calls', type=int)
    parser.add_argument('--encoders', nargs='+',
                        choices=['graph_transformer', 'mlp', 'rgcn', 'gat', 'port_gnn', 'gcn'],
                        help='Each selected encoder runs scratch/frozen/adapt; omitted keeps the M5 six methods')
    parser.add_argument('--hidden-dim', type=int, default=32)
    parser.add_argument('--heads', type=int, default=4)
    parser.add_argument('--layers', type=int, default=2)
    parser.add_argument('--env', type=Path)
    parser.add_argument('--library')
    parser.add_argument('--creation-receipt', type=Path)
    parser.add_argument('--model-file')
    parser.add_argument('--reference-measurements', type=Path)
    parser.add_argument('--bridge-site-packages', type=Path)
    args = parser.parse_args()
    real = args.origin == 'real'
    if real and any(getattr(args, k) is None for k in
                    ('env', 'library', 'creation_receipt', 'model_file', 'reference_measurements')):
        parser.error('Real benchmark requires the existing explicit bridge/model/baseline arguments')
    if args.bridge_site_packages:
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    import torch
    from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
    from analog_optimizer.envs.sizing import CircuitSizingEnv, write_record
    from analog_optimizer.evaluation.benchmark import run_benchmark
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True)
    settings = dict(seeds=args.seeds, encoders=args.encoders,
                    hidden_dim=args.hidden_dim, heads=args.heads, layers=args.layers,
                    pretrain_steps=args.pretrain_steps if args.pretrain_steps is not None else (2 if real else 16),
                    test_steps=args.test_steps if args.test_steps is not None else (3 if real else 8), batch_size=2,
                    max_calls=(args.max_calls if args.max_calls is not None else (100 if real else 600)) - int(real))
    # Reserve one extra real call to verify the restored baseline by simulation.
    tasks = build_tasks(args.origin)
    baseline_records = []
    check = None
    provenance = {'fixtures_are_analytic_not_circuit_simulation': not real,
                  'real_scope': 'same-topology specifications only' if real else None}
    files = ['configs/gpdk045_opamp_transfer.json', 'configs/gpdk045_conditions.json',
             'configs/gpdk045_opamp.json', 'configs/gpdk045_opamp_design.json',
             'examples/circuits/gpdk045_ota5.scs', 'examples/circuits/gpdk045_ota5.cdf.json'] if real else [
                 'configs/opamp.json', 'configs/opamp_two_stage.json', 'configs/synthetic_models.json',
                 'tests/fixtures/synthetic/opamp.scs', 'tests/fixtures/synthetic/opamp_two_stage.scs']
    provenance['files'] = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
    provenance['entrypoint_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if real:
        from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend
        from verify_opamp_environment import metrics_match
        reference = json.loads(args.reference_measurements.read_text())
        if reference['origin'] != 'real':
            raise ValueError('Real baseline reference required')
        provenance.update(library=args.library, model_file=args.model_file,
                          reference_sha256=hashlib.sha256(args.reference_measurements.read_bytes()).hexdigest())
        config = BridgeConfig(args.env.resolve(), args.library, args.creation_receipt.resolve(),
                              ROOT / 'artifacts/local/bridge-state', args.model_file)
        def factory(task, steps, output):
            return CircuitSizingEnv(VirtuosoBridgeBackend(config, make_profile()), task.graph, task.specs,
                                    output, max_steps=steps, stop_on_success=False, expected_origin='real')
        def check(record):
            baseline_records.append(record)
            if (not record.get('evaluation_valid') or not metrics_match(record['metrics'], reference['metrics'])
                    or record['netlist_sha256'] != baseline_records[0]['netlist_sha256']):
                raise RuntimeError('Baseline parameters/deck/metrics differ from the verified reference')
    else:
        provenance['toy_targets'] = {'w': .4, 'c': -.3}
        def factory(task, steps, output):
            return CircuitSizingEnv(SyntheticSizingBackend(task.graph, targets=provenance['toy_targets']),
                                    task.graph, task.specs, output, max_steps=steps, stop_on_success=False,
                                    expected_origin='synthetic')
    stdout = sys.stdout
    progress = lambda message: print(message, file=stdout, flush=True)
    started = perf_counter()
    try:
        with (directory / 'execution.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
            report = run_benchmark(tasks, factory, directory, origin=args.origin, settings=settings,
                                   provenance=provenance, progress=progress, baseline_check=check)
            if real:
                verify = factory(tasks[0], 1, directory / 'restoration-verification')
                try:
                    with verify:
                        _, info = verify.reset()
                        record = json.loads(Path(info['record_path']).read_text())
                        check(record)
                    report['restoration_verified'] = True
                    report['restoration_record'] = info['record_path']
                finally:
                    report['restoration_verification_calls'] = verify.simulation_calls
                    report['real_simulation_calls'] += verify.simulation_calls
                    report['calls'] += verify.simulation_calls
                    report['end_to_end_seconds'] = perf_counter() - started
                    if not report.get('restoration_verified'):
                        report['completed'] = False
                    write_record(directory / 'report.json', report)
    finally:
        progress('REPORT ' + str(directory / 'report.json'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
