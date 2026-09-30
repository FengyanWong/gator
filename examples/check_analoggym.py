"""Free local parity gate against independent, original AnalogGym testbenches.

No provider imports or requests. Run after import_analoggym.py. Failed circuits
stop at their first mismatch and remain excluded; tolerances are never relaxed.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import random
import re
import subprocess
import time

from analog_optimizer.backends.backend import SimulationRequest
from analog_optimizer.parameters import ActionMapper
from gator_workbench.analoggym import AnalogGymBackend, evaluate_outputs
from gator_workbench.compile import compile_task, hard_constraints
from gator_workbench.ngspice_backend import NgspiceLink
from gator_workbench.ngspice_tasks import parse_entry
from gator_workbench.schema import WorkbenchConfig
from gator_workbench.storage.atomic import write_json


def original_deck(bundle, kind, values):
    """Original topology and separate processes; inline only its own parameter files."""
    config = bundle['config']
    directory = (Path(bundle['checkout'])/'circuit_configs'/config['base_dir']).resolve()
    source = directory/config['file_paths'][kind+'_cir_path']
    def include(match):
        path = (source.parent/match[1].strip('"\'')).resolve()
        if path.name == config['file_paths']['vars_path']:
            return '\n'.join(f'.param {key}={value:.17g}' for key,value in values.items())
        if path.name in (config['file_paths']['dev_params_path'], config['file_paths']['netlist_path']):
            return path.read_text()
        return f'.include "{path}"'
    return re.sub(r'(?im)^\s*\.include\s+([^\s]+)\s*$', include, source.read_text())


def check_one(directory, output, count=20, seed=1729, timeout=120):
    directory, output = Path(directory), Path(output)
    entry = json.loads((directory/'task.json').read_text())
    bundle = entry['analoggym']
    report = dict(name=bundle['name'], seed=seed, requested_designs=count, tolerance_relative=1e-9,
                  passed=False, designs=[], exclusion=None, simulator_processes=0)
    destination = output/bundle['name']/'result.json'
    if bundle['preflight_issues']:
        report['exclusion'] = '; '.join(bundle['preflight_issues'])
        write_json(destination,report)
        return report
    text = (directory/'netlist.cir').read_text()
    config = WorkbenchConfig.model_validate_json((directory/'config.json').read_text())
    compiled = compile_task(config, parse_entry(entry,text).graph)
    mapper = ActionMapper(compiled.graph)
    rng = random.Random(seed)
    backend = AnalogGymBackend(text,compiled.graph,NgspiceLink('ngspice_local'),bundle=bundle,
                               device_kinds=entry['device_kinds'])
    backend.connect()
    for index in range(count):
        started = time.monotonic()
        local = output/bundle['name']/str(index)
        original = local/'original'
        original.mkdir(parents=True, exist_ok=True)
        action = mapper.legalize({g:rng.uniform(-1,1) for g in mapper.group_ids})
        backend.set_parameters(action.assignments)
        values = backend.native_values()
        item = dict(index=index, native_values=values, differences=[], error=None)
        try:
            codes=[]
            for kind in ('ACDC','Tran'):
                deck = original/(kind+'.cir')
                deck.write_text(original_deck(bundle,kind,values))
                report['simulator_processes'] += 1
                with (original/(kind+'.log')).open('w') as log:
                    result = subprocess.run(['ngspice','-b',deck.name],cwd=original,stdout=log,
                                            stderr=subprocess.STDOUT,timeout=timeout)
                codes.append(result.returncode)
            native, passed, _ = evaluate_outputs(bundle, original, values)
            artifact = backend.generate_netlist(local/'gator')
            backend.get_circuit_graph(artifact)
            result = backend.run_simulation(SimulationRequest(artifact,local/'gator',
                timeout_seconds=timeout,parameters=backend.parameters,condition=artifact.condition))
            report['simulator_processes'] += result.simulator_invocations or 0
            observed = json.loads((result.artifact_directory/'benchmark.json').read_text())
            for key, expected in native.items():
                actual = observed['native_metrics'][key]
                equal = (actual is expected if actual is None or expected is None else
                         abs(actual-expected) <= 1e-9*abs(expected))
                if not equal: item['differences'].append(dict(metric=key,upstream=expected,gator=actual))
            verdict = result.status.value in ('ok', 'measurement_error') and hard_constraints(
                compiled.targets, result.metrics, result.metric_validity)[1]
            item.update(upstream_exit_codes=codes, upstream_passed=passed,gator_passed=verdict,
                        gator_status=result.status.value, operating_point_devices=len(result.operating_points or {}),
                        gator_metrics=result.metrics, upstream_metrics=native)
            if passed != verdict: item['differences'].append(dict(verdict=True,upstream=passed,gator=verdict))
            if not result.candidate_evaluated: item['error']=result.error_summary
        except Exception as exc:
            item['error']=f'{type(exc).__name__}: {exc}'[:1000]
        item['seconds'] = time.monotonic()-started
        report['designs'].append(item)
        write_json(destination,report)
        if item['error'] or item['differences']:
            report['exclusion']='Failed strict parity; see first failing design'
            break
    report['passed'] = len(report['designs'])==count and not report['exclusion']
    write_json(destination,report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--settings',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4);p.add_argument('--circuits',nargs='*')
    args=p.parse_args()
    directories=sorted((args.settings/'ngspice').glob('analoggym_*'))
    if args.circuits: directories=[d for d in directories if d.name.removeprefix('analoggym_') in args.circuits]
    reports=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(check_one,str(d.resolve()),str(args.output.resolve())):d.name for d in directories}
        for job in as_completed(jobs):
            try: result=job.result()
            except Exception as exc: result=dict(name=jobs[job],passed=False,error=str(exc))
            reports.append(result)
            print(json.dumps({k:v for k,v in result.items() if k!='designs'}),flush=True)
            write_json(args.output/'summary.json',dict(circuits=reports))


if __name__=='__main__':main()
