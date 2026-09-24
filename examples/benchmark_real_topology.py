"""Frozen M5 nominal specification and real OTA topology transfer benchmark.

Every circuit has an independent creation receipt, qualified reference and
restorable profile. Episodes serialize the shared native CDF/bridge session.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from opamp_connection import add_connection_arguments, configure
from verify_two_stage_ota import make_profile
from benchmark_transfer import build_tasks
from analog_optimizer.backends.virtuoso_bridge import digest, write_json
from analog_optimizer.evaluation.runtime import BenchmarkFactory, BaselineCheck, TaskBaselineChecks, MultiCircuitFactory
from analog_optimizer.evaluation.transfer import TransferTask, validate_split
from analog_optimizer.measurements.specs import MetricSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--target-creation-receipt', type=Path, required=True)
    parser.add_argument('--reference-measurements', type=Path, required=True)
    parser.add_argument('--target-qualification', type=Path, required=True)
    parser.add_argument('--seeds', nargs='+', type=int, default=[17, 29, 43])
    parser.add_argument('--pretrain-steps', type=int, default=16)
    parser.add_argument('--test-steps', type=int, default=12)
    parser.add_argument('--max-calls', type=int, default=600)
    parser.add_argument('--encoders', nargs='+', choices=['graph_transformer','mlp','gcn','rgcn','gat'],
                        default=['graph_transformer'], help='Encoders to run, each as scratch / frozen / adapt. port_gnn was removed on 2026-09-24; the former default protocol (graph_transformer + port_gnn, six methods) runs only from source commit bbdfe36.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config, source_profile = configure(args)
    target_profile = make_profile()
    qualification = json.loads(args.target_qualification.read_text())
    if not qualification.get('passed') or not qualification.get('full_snapshot_restored'):
        raise ValueError('Completed real target qualification and restoration are required')
    target_config = replace(config, creation_receipt=args.target_creation_receipt.resolve())
    target_reference = Path(qualification['reference_measurements'])
    references = [json.loads(p.read_text()) for p in (args.reference_measurements, target_reference)]
    if any(r['origin'] != 'real' for r in references):
        raise ValueError('Both reference measurements must have real provenance')
    # Bind qualification to the current profile, not only to its label.
    from analog_optimizer.backends.virtuoso_bridge import build_deck
    from hashlib import sha256
    expected_deck = build_deck((ROOT/'examples/circuits/gpdk045_ota7.scs').read_text(),config.model_file)
    if sha256(expected_deck.encode()).hexdigest() != qualification['stages'][0]['netlist_sha256']:
        raise ValueError('Target qualification deck differs from the current circuit')
    for cfg, profile in ((config,source_profile),(target_config,target_profile)):
        receipt = json.loads(cfg.creation_receipt.read_text())
        if receipt['library'] != cfg.library or receipt['config'] != profile.design:
            raise ValueError('Circuit creation receipt/configuration mismatch')
    tasks = build_tasks('real')
    specification = json.loads((ROOT/'configs/gpdk045_ota7_transfer.json').read_text())
    target = TransferTask(specification['id'],'test','topology','gpdk045_ota',target_profile.optimization_graph(),
                          tuple(MetricSpec(**s) for s in specification['specs']))
    tasks.append(target)
    validate_split(tasks)
    factories = {t.id:BenchmarkFactory('real',target_config if t==target else config,
                                     target_profile if t==target else source_profile) for t in tasks}
    source_check = BaselineCheck(references[0]['metrics'],digest(args.reference_measurements.parent/'opamp.scs'))
    target_check = BaselineCheck(references[1]['metrics'],qualification['stages'][0]['netlist_sha256'])
    checks = TaskBaselineChecks({t.id:target_check if t==target else source_check for t in tasks})
    factory = MultiCircuitFactory(factories)
    settings = dict(seeds=args.seeds,pretrain_steps=args.pretrain_steps,test_steps=args.test_steps,
                    batch_size=2,max_calls=args.max_calls-2,encoders=args.encoders,
                    max_workers=1,sampling='serialized native CDF across independent circuit profiles')
    from analog_optimizer.evaluation.benchmark import benchmark_models, run_benchmark
    models,methods,validation = benchmark_models(settings)
    planned = len(args.seeds)*(len(models)*(1+args.pretrain_steps)+2*len(validation)+len(methods)*2*(1+args.test_steps))
    if planned+2>args.max_calls:
        raise ValueError(f'Planned {planned+2} calls including restoration exceed cap {args.max_calls}')
    project_files = ['configs/gpdk045_opamp_design.json','configs/gpdk045_opamp.json',
        'configs/gpdk045_opamp_transfer.json','configs/gpdk045_ota7_design.json','configs/gpdk045_ota7.json',
        'configs/gpdk045_ota7_transfer.json','configs/gpdk045_conditions.json',
        'examples/circuits/gpdk045_ota5.scs','examples/circuits/gpdk045_ota5.cdf.json',
        'examples/circuits/gpdk045_ota7.scs','examples/circuits/gpdk045_ota7.cdf.json',
        'examples/benchmark_real_topology.py','examples/verify_two_stage_ota.py','examples/build_two_stage_ota.py']
    provenance = dict(real_scope='same-family specification and new topology; nominal only',
        qualification_calls=qualification['calls'],qualification_report=str(args.target_qualification.resolve()),
        qualification_sha256=digest(args.target_qualification),qualification_used_for_learning=False,
        commissioning_used_for_specification_design=True,blind_topology_benchmark=False,
        files={f:digest(ROOT/f) for f in project_files},
        reference_sha256=[digest(p) for p in (args.reference_measurements,target_reference)],
        model_file=config.model_file,library=config.library,
        lineage=specification['lineage'],purpose=specification['purpose'])
    if args.dry_run:
        print(json.dumps(dict(tasks=[t.id for t in tasks],planned_calls=planned,restoration_calls=2,
                              settings=settings,provenance=provenance),indent=2))
        return
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    directory=args.output.resolve()/uuid4().hex
    directory.mkdir(parents=True)
    print('REPORT',directory/'report.json',flush=True)
    report=dict(passed=False,completed=False,restoration_checks=[],qualification_calls=qualification['calls'])
    started=perf_counter()
    console=sys.stdout
    def progress(message):
        print(message,file=console,flush=True)
    from analog_optimizer.training.runtime import RunResources
    with RunResources(report,directory/'report.json') as resources:
        with (directory/'bridge.log').open('w') as log, redirect_stdout(log),redirect_stderr(log):
            run_benchmark(tasks,factory,directory,origin='real',settings=settings,provenance=provenance,
                          baseline_check=checks,report=report,progress=progress)
            for task in (tasks[0],target):
                env=factory(task,1,directory/'restoration-verification')
                row=dict(task=task.id,passed=False,calls=0)
                report['restoration_checks'].append(row)
                try:
                    with env:
                        _,info=env.reset()
                        record=json.loads(Path(info['record_path']).read_text())
                        checks.for_task(task)(record)
                    row.update(passed=True,record=info['record_path'])
                finally:
                    row['calls']=env.simulation_calls
                    report['calls']+=env.simulation_calls
                    report['real_simulation_calls']+=env.simulation_calls
            report.update(passed=True,end_to_end_seconds=perf_counter()-started,
                          benchmark_plus_qualification_calls=report['calls']+qualification['calls'])
    print('COMPLETE',directory/'report.json',flush=True)


if __name__=='__main__':
    main()
