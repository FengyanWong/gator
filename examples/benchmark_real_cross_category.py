"""Freeze/check the physical M6 pilot offline; execute only an unchanged saved plan."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import shlex
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json
from analog_optimizer.evaluation.benchmark import run_benchmark
from analog_optimizer.evaluation.real_category import (PhysicalFactory, build_plan, freeze_plan,
    read, require, validate_frozen_plan)
from analog_optimizer.evaluation.runtime import BenchmarkFactory, BaselineCheck, MultiCircuitFactory, TaskBaselineChecks


def runtime_factory(suite, plan, *, env_file, state_root, profile_name=None):
    bindings = plan['bindings']
    factories, checks = {}, {}
    for heldout in suite.definition['heldout']:
        for task in suite.tasks(heldout):
            name = task.circuit_class
            config = BridgeConfig(Path(env_file).resolve(),bindings['library'],
                Path(bindings['circuits'][name]['creation_receipt']).resolve(),Path(state_root).resolve(),
                bindings['model_file'],profile=profile_name)
            factories[task.id]=BenchmarkFactory('real',config,suite.profiles[name])
            reference=plan['references'][name]
            checks[task.id]=BaselineCheck(reference['metrics'],reference['deck_sha256'])
    return PhysicalFactory(suite,MultiCircuitFactory(factories)),TaskBaselineChecks(checks)


def inspect_physical_state(factory, plan):
    """Read all protected cores and the same two model files as qualification."""
    from virtuoso_bridge.transport.tunnel import SSHClient
    expected=read(plan['bindings']['final_inspection'])
    entry=Path(plan['bindings']['model_file'])
    model_paths=[entry.parent/name for name in expected['model_hashes']]
    with VirtuosoBridgeBackend(factory.config,factory.profile) as backend:
        snapshots={cell:backend.client.schematic.read(factory.config.library,cell,
                    include_positions=True,param_filters=None) for cell in expected['full_snapshots']}
        result=SSHClient.from_env().run_command('sha256sum '+' '.join(shlex.quote(str(p)) for p in model_paths),timeout=30)
        require(result.returncode==0, 'Cannot verify qualified model hashes')
        hashes={Path(p).name:h for h,p in (line.split() for line in result.stdout.splitlines())}
    return dict(passed=snapshots==expected['full_snapshots'] and hashes==expected['model_hashes'],
                full_snapshots=snapshots,model_hashes=hashes,
                model_hash_scope='Previously recorded entry and MOS files only; not recursive')


def execute_suite(suite, plan, factory, checks, directory, *, inspect=inspect_physical_state, progress=print):
    """Serial suite, fail fast; every fold and final reset contributes to one cap."""
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    freeze_plan(directory/'suite-protocol.json',plan)
    report=dict(completed=False,origin='real',plan_sha256=plan['sha256'],
                planned_calls=plan['budget']['total_calls'],calls=0,folds={},final_checks=[],
                automatic_retries=0,cache_hits=0)
    started=perf_counter()
    primary=None
    base=factory.delegate.factories['opamp-train']
    try:
        before=inspect(base,plan)
        write_json(directory/'before.json',before)
        require(before['passed'], 'Circuit/model state differs before experiment')
        for name in suite.definition['heldout']:
            tasks=suite.tasks(name)
            fold_report={}
            try:
                reserved=plan['budget']['folds'][name]['total']
                require(report['calls']+reserved+plan['budget']['final_baseline_calls']<=report['planned_calls'],
                        'Suite budget exhausted before fold construction')
                run_benchmark(tasks,factory,directory/name,origin='real',
                    settings=dict(plan['settings'],max_calls=reserved),
                    provenance=dict(suite_sha256=plan['sha256'],heldout_class=name,
                        reference_evidence=plan['references'],prior_data_used_for_learning=False),
                    baseline_check=checks,report=fold_report,progress=progress)
                require(fold_report.get('completed'), 'Fold did not complete')
            finally:
                report['folds'][name]=dict(completed=fold_report.get('completed',False),
                    calls=fold_report.get('calls',0),report=str(directory/name/'report.json'))
                report['calls']=sum(r['calls'] for r in report['folds'].values())
                write_json(directory/'report.json',report)
        # Separate, budgeted baseline resets; no candidate step or learner update.
        for name in sorted(suite.profiles):
            task=next(t for t in suite.tasks(name) if t.partition=='test')
            require(report['calls']+1<=report['planned_calls'], 'No budget for final baseline check')
            env=factory.delegate(task,1,directory/'final-baselines')
            row=dict(circuit_class=name,passed=False,calls=0)
            report['final_checks'].append(row)
            try:
                with env:
                    _,info=env.reset()
                    record=read(info['record_path'])
                    checks.for_task(task)(record)
                row.update(passed=True,record=info['record_path'])
            finally:
                row['calls']=env.simulation_calls
                report['calls']+=env.simulation_calls
                write_json(directory/'report.json',report)
        report['completed']=all(r['completed'] for r in report['folds'].values())
    except BaseException as exc:
        primary=exc
        report.update(exception_type=type(exc).__name__,error=str(exc),completed=False)
        raise
    finally:
        try:
            after=inspect(base,plan)
            write_json(directory/'after.json',after)
            report['all_circuits_and_models_restored']=after['passed']
            require(after['passed'], 'Final circuit/model state differs')
        except BaseException as exc:
            report.update(completed=False,inspection_error=str(exc))
            if primary is None:
                primary=exc
        report.update(real_simulation_calls=report['calls'],elapsed_seconds=perf_counter()-started,
            unexecuted_folds=[k for k in suite.definition['heldout'] if k not in report['folds']])
        write_json(directory/'report.json',report)
        if primary is not None and sys.exc_info()[0] is None:
            raise primary
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--freeze',type=Path,help='Write an immutable protocol; no bridge or simulator calls')
    action.add_argument('--check-plan',type=Path,help='Verify saved protocol and all local evidence; no network')
    action.add_argument('--execute',type=Path,help='Run the exact frozen protocol')
    action.add_argument('--dry-run',action='store_true',help='Validate/budget only (the default)')
    parser.add_argument('--manifest',type=Path,default=ROOT/'configs/m6_real_cross_category.json')
    parser.add_argument('--bindings',type=Path,help='Local JSON with qualified receipts/baselines and library/model binding')
    parser.add_argument('--env',type=Path)
    parser.add_argument('--profile')
    parser.add_argument('--bridge-site-packages',type=Path)
    parser.add_argument('--state-root',type=Path,default=ROOT/'artifacts/local/bridge-state')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/local/m6-real-cross-category')
    args=parser.parse_args()
    if args.execute or args.check_plan:
        suite,plan=validate_frozen_plan(ROOT,args.execute or args.check_plan)
    else:
        if args.bindings is None:
            parser.error('--bindings is required to prepare a physical plan')
        suite,plan=build_plan(ROOT,args.manifest,args.bindings)
    summary=dict(origin='real',encoders=plan['settings']['encoders'],planned_calls=plan['budget'],metric_count=len(suite.schema.metrics),
        action_counts={k:sum(g.mutable for g in p.optimization_graph().parameter_groups) for k,p in suite.profiles.items()},
        plan_sha256=plan['sha256'],new_simulator_calls=0)
    if not args.execute:
        if args.freeze:
            freeze_plan(args.freeze,plan)
            summary['frozen_protocol']=str(args.freeze.resolve())
        print(json.dumps(summary,indent=2))
        return
    if args.env is None:
        parser.error('--env is required for explicit execution')
    if args.bridge_site_packages:
        import site
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    factory,checks=runtime_factory(suite,plan,env_file=args.env,state_root=args.state_root,profile_name=args.profile)
    directory=args.output.resolve()/uuid4().hex
    console=sys.stdout
    args.output.resolve().mkdir(parents=True,exist_ok=True)
    with (args.output.resolve()/f'{directory.name}.log').open('x') as log,redirect_stdout(log),redirect_stderr(log):
        execute_suite(suite,plan,factory,checks,directory,progress=lambda msg:print(msg,file=console,flush=True))
    print('REPORT',directory/'report.json',flush=True)


if __name__=='__main__':
    main()
