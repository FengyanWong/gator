"""Qualify the dedicated VCO with bounded native CDF changes and restoration."""
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
from analog_optimizer.backends.gpdk045_vco import Gpdk045VcoProfile
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json
from analog_optimizer.evaluation.runtime import BaselineCheck
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator


def make_profile(*, analysis_mode='fast', timestep_scale=1.):
    return Gpdk045VcoProfile(analysis_mode=analysis_mode,timestep_scale=timestep_scale,design_file=ROOT/'configs/gpdk045_vco_design.json',mapping_file=ROOT/'configs/gpdk045_vco.json',
        reference_structure=ROOT/'examples/circuits/gpdk045_vco.scs',reference_readback=ROOT/'examples/circuits/gpdk045_vco.cdf.json')


def qualification_specs():
    return (MetricSpec('vco_frequency_hz','Hz','range',1e8,lower=1e6,upper=1e9),
            MetricSpec('supply_power_w','W','range',1e-3,lower=0,upper=1e-3),
            MetricSpec('vco_minimum_swing_v','V','min',1,lower=.8),
            MetricSpec('vco_tuning_fraction','1','min',1,lower=.05),
            MetricSpec('vco_max_period_spread','1','max',.02,upper=.02),
            MetricSpec('vco_max_window_drift','1','max',.01,upper=.01),
            MetricSpec('vco_startup_detection_s','s','max',1e-6,upper=1e-6),
            MetricSpec('vco_duty_cycle','1','range',1,lower=.05,upper=.95))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--baseline-only',action='store_true')
    parser.add_argument('--analysis-mode', choices=('reference','fast'), default='fast')
    parser.add_argument('--half-step',action='store_true',help='Use half the maximum timestep for numerical qualification')
    args=parser.parse_args()
    if args.bridge_site_packages:
        import site
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    profile=make_profile(analysis_mode=args.analysis_mode,timestep_scale=.5 if args.half_step else 1.)
    config=BridgeConfig(args.env.resolve(),args.library,args.creation_receipt.resolve(),args.state_root.resolve(),args.model_file,profile=args.profile)
    directory=args.output.resolve()/uuid4().hex;directory.mkdir(parents=True)
    points=[('baseline',1e-6,1e-6,1e-6)] if args.baseline_only else [
        ('baseline',1e-6,1e-6,1e-6),('stage1_high',1.1e-6,1e-6,1e-6),
        ('baseline_repeat',1e-6,1e-6,1e-6),('stage2_high',1e-6,1.1e-6,1e-6),
        ('stage3_high',1e-6,1e-6,1.1e-6),('all_low',.9e-6,.9e-6,.9e-6),
        ('all_high',1.1e-6,1.1e-6,1.1e-6),('restored',1e-6,1e-6,1e-6)]
    report=dict(origin='real',passed=False,planned_calls=len(points),calls_attempted=0,confirmed_invocations=0,
        stages=[],qualification_only=True,timestep_scale=profile.timestep_scale,
        analysis_settings=profile.analysis_settings,specs=[asdict(s) for s in qualification_specs()])
    backend=VirtuosoBridgeBackend(config,profile)
    try:
        with (directory/'bridge.log').open('w') as log,redirect_stdout(log),redirect_stderr(log),backend:
            report['session_dir']=str(backend.session_dir)
            def protected():
                return {cell:backend.client.schematic.read(args.library,cell,include_positions=True,param_filters=None)
                        for cell in ('ota5_v1','ota7_m5_v2','ldo_m6_v1')}
            before=backend.read_cdf_snapshot();others=protected()
            write_json(directory/'before.json',dict(vco=before,protected=others))
            try:
                check=None
                for name,w1,w2,w3 in points:
                    assignment=profile.assignments(w1,w2,w3)
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
                        raise RuntimeError(f'VCO qualification failed at {name}; inspect {result.artifact_directory}')
                    if check is None: check=BaselineCheck(result.metrics,artifact.sha256)
                    elif name in ('baseline_repeat','restored'): check(row)
                    elif artifact.sha256==report['stages'][0]['netlist_sha256'] or result.metrics==report['stages'][0]['metrics']:
                        raise RuntimeError('Width action did not change both deck and measured response')
                report['passed']=True
            finally:
                backend.restore()
                after=backend.read_cdf_snapshot();other_after=protected()
                write_json(directory/'after.json',dict(vco=after,protected=other_after))
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
