"""Three real qualification evaluations through reset/step; no learner updates."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from opamp_connection import add_connection_arguments
from verify_ldo_baseline import make_profile, qualification_specs
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.training.replay import Transition


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    args=parser.parse_args()
    if args.bridge_site_packages:
        import site
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    profile=make_profile()
    config=BridgeConfig(args.env.resolve(),args.library,args.creation_receipt.resolve(),args.state_root.resolve(),args.model_file,profile=args.profile)
    directory=args.output.resolve()/uuid4().hex;directory.mkdir(parents=True)
    backend=VirtuosoBridgeBackend(config,profile)
    env=CircuitSizingEnv(backend,profile.optimization_graph(),qualification_specs(),directory/'environment',
                         max_steps=2,stop_on_success=False,expected_origin='real')
    report=dict(passed=False,origin='real',planned_calls=3,training_updates=0,qualification_only=True,
                records=[],transition_checks=0)
    try:
        with (directory/'bridge.log').open('w') as log,redirect_stdout(log),redirect_stderr(log),env:
            def snapshots():
                return {cell:backend.client.schematic.read(args.library,cell,include_positions=True,param_filters=None)
                        for cell in ('ota5_v1','ota7_m5_v2',profile.design['core_cell'])}
            before=snapshots();write_json(directory/'before.json',before)
            observation,info=env.reset();report['records'].append(info['record_path'])
            if observation is None or info['terminated'] or info['truncated']:
                raise RuntimeError('LDO reset did not return a usable observation')
            for x,y in ((.5,-.5),(-.5,.5)):
                proposal=dict(input_pair_width=x,pass_width=y)
                step=env.step(proposal);report['records'].append(step[4]['record_path'])
                Transition.from_step(observation,proposal,step).validate()
                report['transition_checks']+=1
                observation=step[0]
            if step[3] or not step[2]:
                raise RuntimeError('Finite-horizon LDO episode did not terminate correctly')
            backend.restore()
            after=snapshots();write_json(directory/'after.json',after)
            report['all_circuits_restored']=before==after
            if before!=after:
                raise RuntimeError('Full circuit snapshot changed')
        report['restoration']=json.loads((env.directory/'restoration.json').read_text())
        report['passed']=report['restoration']['state']=='restored' and env.simulation_calls==3
        if not report['passed']:
            raise RuntimeError('LDO environment restoration/cost check failed')
    except BaseException as exc:
        report.update(passed=False,error_type=type(exc).__name__,error=str(exc));raise
    finally:
        report['calls']=env.simulation_calls
        write_json(directory/'verification.json',report)
        print('ENVIRONMENT',directory/'verification.json',flush=True)


if __name__=='__main__': main()
