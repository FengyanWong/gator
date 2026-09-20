"""Qualify the dedicated LDO with bounded native CDF changes and restoration."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from opamp_connection import add_connection_arguments
from analog_optimizer.backends.backend import SimulationRequest
from analog_optimizer.backends.gpdk045_ldo import Gpdk045LdoProfile
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json
from analog_optimizer.evaluation.runtime import BaselineCheck
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator


def make_profile():
    return Gpdk045LdoProfile(design_file=ROOT/'configs/gpdk045_ldo_design.json',mapping_file=ROOT/'configs/gpdk045_ldo.json',
        reference_structure=ROOT/'examples/circuits/gpdk045_ldo.scs',reference_readback=ROOT/'examples/circuits/gpdk045_ldo.cdf.json')


def qualification_specs():
    return (MetricSpec('ldo_output_error_v','V','max',.02,upper=.02),
            MetricSpec('ldo_quiescent_current_a','A','range',8e-6,lower=0,upper=8e-6),
            MetricSpec('ldo_line_regulation_v_per_v','V/V','max',.1,upper=.1),
            MetricSpec('ldo_load_regulation_v_per_a','V/A','max',1000,upper=1000),
            MetricSpec('ldo_psrr_1khz_db','dB','min',20,lower=10),
            MetricSpec('ldo_step_deviation_v','V','max',.05,upper=.05),
            MetricSpec('ldo_step_tail_ripple_v','V','max',.001,upper=.001))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--baseline-only',action='store_true')
    args=parser.parse_args()
    if args.bridge_site_packages:
        import site
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    profile=make_profile()
    config=BridgeConfig(args.env.resolve(),args.library,args.creation_receipt.resolve(),args.state_root.resolve(),args.model_file,profile=args.profile)
    directory=args.output.resolve()/uuid4().hex;directory.mkdir(parents=True)
    points=[('baseline',4e-6,8e-6)] if args.baseline_only else [
        ('baseline',4e-6,8e-6),('input_high',4.4e-6,8e-6),('baseline_repeat',4e-6,8e-6),
        ('pass_high',4e-6,8.8e-6),('both_low',3.6e-6,7.2e-6),('both_high',4.4e-6,8.8e-6),('restored',4e-6,8e-6)]
    report=dict(origin='real',passed=False,planned_calls=len(points),calls_attempted=0,confirmed_invocations=0,
        stages=[],qualification_only=True,specs=[asdict(s) for s in qualification_specs()])
    backend=VirtuosoBridgeBackend(config,profile)
    try:
        with (directory/'bridge.log').open('w') as log,redirect_stdout(log),redirect_stderr(log),backend:
            report['session_dir']=str(backend.session_dir)
            def protected():
                return {cell:backend.client.schematic.read(args.library,cell,include_positions=True,param_filters=None)
                        for cell in ('ota5_v1','ota7_m5_v2')}
            before=backend.read_cdf_snapshot();others=protected()
            write_json(directory/'before.json',dict(ldo=before,protected=others))
            try:
                check=None
                for name,width,pass_width in points:
                    assignment=profile.assignments(width,pass_width)
                    backend.set_parameters(assignment)
                    artifact=backend.generate_netlist(directory/'exports')
                    report['calls_attempted']+=1
                    write_json(directory/'verification.json',report)
                    result=backend.run_simulation(SimulationRequest(artifact,directory/'simulations',
                        required_metrics=tuple(s.metric_id for s in qualification_specs()),parameters=assignment))
                    report['confirmed_invocations']+=result.simulator_invocations or 0
                    evaluation=SpecificationEvaluator(qualification_specs()).evaluate(result.metrics,result.metric_units,result.metric_validity)
                    row=dict(name=name,status=result.status.value,reason=result.reason_code,metrics=result.metrics,
                        metric_units=result.metric_units,metric_validity=result.metric_validity,
                        evaluation_valid=evaluation.valid,qualification_success=evaluation.success,
                        netlist_sha256=artifact.sha256,invocations=result.simulator_invocations,
                        job=str(result.artifact_directory),parameters=[dict(device=k[0],parameter=k[1],value=v) for k,v in assignment.items()])
                    report['stages'].append(row);write_json(directory/'verification.json',report)
                    if result.status.value!='ok' or result.simulator_invocations!=1 or not evaluation.success:
                        raise RuntimeError(f'LDO qualification failed at {name}; inspect {result.artifact_directory}')
                    if check is None: check=BaselineCheck(result.metrics,artifact.sha256)
                    elif name in ('baseline_repeat','restored'): check(row)
                    elif artifact.sha256==report['stages'][0]['netlist_sha256'] or result.metrics==report['stages'][0]['metrics']:
                        raise RuntimeError('Width action did not change both deck and measured response')
                report['passed']=True
            finally:
                backend.restore()
                after=backend.read_cdf_snapshot();other_after=protected()
                write_json(directory/'after.json',dict(ldo=after,protected=other_after))
                report.update(full_snapshot_restored=before==after,protected_circuits_unchanged=others==other_after)
                if before!=after or others!=other_after:
                    report['passed']=False
                    raise RuntimeError('Circuit snapshot restoration failed')
    except BaseException as exc:
        report.update(passed=False,error_type=type(exc).__name__,error=str(exc));raise
    finally:
        write_json(directory/'verification.json',report)
        print('VERIFICATION',directory/'verification.json',flush=True)


if __name__=='__main__': main()
