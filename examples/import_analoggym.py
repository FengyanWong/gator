"""Import the pinned MIT AnalogGym-Opt benchmark, without copying its models into GATOR.

Usage: python examples/import_analoggym.py CHECKOUT --settings CONFIGS_LOCAL_DIRECTORY
Optional dependencies: PyYAML, tabulate. The output stays uncommitted in configs/local.
The original evaluator, not YAML captions, defines the benchmark pass rule.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from gator_workbench.analoggym import COMMIT, evaluator_modules, physical_graph
from gator_workbench.ngspice_netlist import parse_text, evaluate
from gator_workbench.schema import WorkbenchConfig
from gator_workbench.storage.atomic import write_json

KINDS = {'sky130_fd_pr__nfet_01v8':'nmos','sky130_fd_pr__pfet_01v8':'pmos',
         'sky130_fd_pr__nfet_01v8_lvt':'nmos','sky130_fd_pr__pfet_01v8_lvt':'pmos',
         'sky130_fd_pr__cap_mim_m3_1':'capacitor','sky130_fd_pr__res_xhigh_po_0p35':'resistor',
         'sky130_fd_pr__res_high_po_0p35':'resistor'}
AMP_HARD = {'phase_margin','dcgain','PSRP','PSRN','cmrrdc','settlingTime','FOML','FOMS','Active_Area'}
LDO_HARD = {'phase_margin','dcgain','PSRR','LNR','LR','vos','vdrop','FOML','FOMS','Active_Area'}
LOWER = {'dcgain','GBW','sr','FOMS','FOML'}
UNITS = {'phase_margin':'deg','dcgain':'dB','PSRP':'dB','PSRN':'dB','PSRR':'dB','cmrrdc':'dB',
         'vos':'V','TC':'1','settlingTime':'s','FOML':'1','FOMS':'1','Active_Area':'1','Power':'W','GBW':'Hz',
         'sr':'1','LNR':'1','LR':'1','vdrop':'V','undershoot':'V','overshoot':'V'}


def load_config(checkout, name):
    loader = evaluator_modules(str(checkout))['circuit_config_loader'].CircuitConfigLoader
    return loader(str(checkout/'circuit_configs')).get_circuit_config(name)


def materialize(checkout, name, config, values, deck_kind):
    directory = (checkout/'circuit_configs'/config['base_dir']).resolve()
    files=config['file_paths']
    source=directory/files[deck_kind+'_cir_path']
    text=source.read_text()
    dut=(directory/files['netlist_path']).read_text()
    # One definition per testbench instance permits explicit tied parameter rows.
    sub=re.search(r'(?im)^\s*\.subckt\s+(\S+)',dut).group(1)
    definitions=[]
    def specialize(match):
        instance=match[1].split()[0]
        renamed=sub+'__'+instance
        definitions.append(re.sub(r'(?i)\b'+re.escape(sub)+r'\b',renamed,dut))
        return match[1]+renamed+match[2]
    text=re.sub(r'(?im)^(x[^\n]*\s)'+re.escape(sub)+r'(\s*)$',specialize,text)
    vars_text='\n'.join(f'.param {key}={value:.17g}' for key,value in values.items())
    def include(match):
        value=match[1].strip('"\'')
        path=(source.parent/value).resolve()
        if path.name==files['netlist_path']:return '\n'.join(definitions)
        if path.name==files['vars_path']:return vars_text
        if path.name==files['dev_params_path']:return path.read_text()
        return f'.include "{path}"'
    text=re.sub(r'(?im)^\s*\.include\s+([^\s]+)\s*$',include,text)
    return text


def import_one(checkout, name, settings):
    from gator_workbench import ngspice_tasks
    config=load_config(checkout,name)
    native={f'{param}_{device}':float(row['init'][param]) for device,row in config['device'].items() for param in row['range']}
    issues=[]
    for device,row in config['device'].items():
        for param,bounds in row['range'].items():
            if not float(bounds[0])<=native[f'{param}_{device}']<=float(bounds[1]):
                issues.append(f'{param}_{device}: starting value {native[f"{param}_{device}"]} outside {bounds}')
            step = row.get('step', {}).get(param)
            if step:
                ticks = (native[f'{param}_{device}']-float(bounds[0]))/float(step)
                if abs(ticks-round(ticks)) > 1e-7:
                    issues.append(f'{param}_{device}: starting value is off the benchmark grid')
    primary=materialize(checkout,name,config,native,'ACDC')
    transient=materialize(checkout,name,config,native,'Tran')
    parsed=physical_graph(parse_text(primary,device_kinds=KINDS,scan_includes=False))
    occurrences={key:[] for key in native}
    for device in parsed.graph.devices:
        for parameter,value in parsed.graph.parameters[device.id].items():
            if not value.valid:continue
            matches=[key for key in native if re.search(r'(?i)\b'+re.escape(key)+r'\b',value.raw)]
            if not matches:continue
            if len(matches)!=1:raise ValueError(f'Compound variable expression: {value.raw}')
            key=matches[0]
            scale=value.value/native[key]
            occurrences[key].append((device.id,parameter,scale,value.value))
    rows,leaders=[],{}
    fixed_native = {key: value for key, value in native.items() if key.startswith('I_')}
    for key,items in occurrences.items():
        if not items:raise ValueError(f'{key} has no writable graph binding')
        items.sort(key=lambda x:(abs(x[2]-(1e-6 if key.startswith(('W_','L_')) else 1)),x[0],x[1]))
        dev,param,scale,initial=items[0]
        leaders[key]=dict(device=dev,parameter=param,physical_per_native=scale)
        if key in fixed_native:
            continue  # Same starting bias for every arm, including LLM-only.
        family,device_name=key.split('_',1)
        row=config['device'][device_name]
        low,high=map(float,row['range'][family]);step=row.get('step',{}).get(family)
        unit='um' if family in ('W','L') else 'A' if family=='I' else 'count'
        shown=1e6 if unit=='um' else 1
        for index,(dev,param,member_scale,initial) in enumerate(items):
            rows.append(dict(variable_id=key if index==0 else key+f'__{index}',instance_path=dev,parameter_name=param,
                initial_value=initial*shown,unit=unit,optimized=True,value_type='integer' if family=='M' else 'continuous',
                lower=low*member_scale*shown,upper=high*member_scale*shown,
                step=float(step)*member_scale*shown if step is not None else None,
                scale='log' if family=='I' else 'linear',binding_group=key if index else None,
                ratio=member_scale/scale,notes=f'AnalogGym variable {key}; native-to-SI factor {member_scale:g}'))
    measurements,targets=[],[]
    ldo=name.startswith('ldo_')
    metric_units={key:UNITS[key] for key in config['performance']}
    metric_scales={key:1e-3 if key=='Power' else 1 for key in metric_units}
    if ldo:metric_units['FOML']='V'
    for key,value in config['performance'].items():
        unit=metric_units[key]
        target=float(value['target'])*metric_scales[key]
        hard=key in (LDO_HARD if ldo else AMP_HARD)
        higher=key in LOWER and not(ldo and key=='FOML')
        measurements.append(dict(measurement_id='probe_'+key,analysis='other',result_source='backend_profile',source_name=key,unit=unit,
            notes='Pinned AnalogGym evaluator output; native penalties are recorded explicitly in benchmark.json.'))
        targets.append(dict(metric_id=key,equation='probe_'+key,unit=unit,hard=hard,active=hard,
            constraint='interval' if key=='phase_margin' else '>=' if higher else '<=',
            lower=45 if key=='phase_margin' else target if higher else None,
            upper=90 if key=='phase_margin' else None if higher else target,
            normalization_scale=max(abs(target),1e-12),direction_after_feasible='none',
            basis='AmpEnv._get_info / LdoEnv._get_info at '+COMMIT))
    task_name='analoggym_'+name
    starter=dict(project=dict(name='AnalogGym-Opt',task_name=name),
        circuit=dict(source='registered_task',task_id='ngspice:'+task_name,circuit_class='ldo' if ldo else 'opamp',pdk_id='sky130'),
        parameters=rows,measurements=measurements,targets=targets)
    bundle=dict(version='analoggym-opt-v1',name=name,checkout=str(checkout),commit=COMMIT,config=config,
                transient=transient,leaders=leaders,metric_units=metric_units,metric_scales=metric_scales,
                preflight_issues=issues,license='MIT',native_initial=native, fixed_native_values=fixed_native,
                scoring='feasibility_only', objective_metrics_descriptive_only=True)
    directory=settings/'ngspice'/task_name
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'netlist.cir').write_text(primary)
    entry=dict(name=task_name,task_key='ngspice:'+task_name,revision=1,title='AnalogGym-Opt '+name,
        device_kinds=KINDS,circuit_class='ldo' if ldo else 'opamp',pdk_id='sky130',simulator='ngspice',
        source_path=str(checkout/'simulation_files'/name/config['file_paths']['ACDC_cir_path']),
        netlist_sha256=hashlib.sha256((primary+json.dumps(bundle,sort_keys=True)).encode()).hexdigest(),
        devices=len(parsed.graph.devices),measurements=measurements,analoggym=bundle,starter=starter)
    write_json(directory/'task.json',entry)
    full=WorkbenchConfig.model_validate(dict(starter,run=dict(max_evaluations=60),output=dict(output_root=str(settings/'outputs'))))
    write_json(directory/'config.json',full.model_dump(mode='json'))
    return dict(name=name,task=entry['task_key'],directory=str(directory),variables=len(native),bindings=len(rows),issues=issues)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout',type=Path);parser.add_argument('--settings',type=Path,required=True)
    parser.add_argument('--circuits',nargs='*')
    args=parser.parse_args();root=args.checkout.resolve();settings=args.settings.resolve()
    repo=Path(__file__).resolve().parents[1]
    if repo==root or repo in root.parents:parser.error('Benchmark checkout must be outside this repository')
    if repo/'configs/local' not in settings.parents:parser.error('Imported tasks must stay under configs/local')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if commit!=COMMIT:parser.error(f'Expected pinned commit {COMMIT}, got {commit}')
    if 'MIT License' not in (root/'LICENSE').read_text():parser.error('Expected MIT licence')
    evaluator_modules(str(root))
    os.environ['GATOR_WORKBENCH_SETTINGS_DIR']=str(settings)
    results=[]
    for name in args.circuits or sorted(p.stem for p in (root/'circuit_configs').glob('*.yaml')):
        try:result=import_one(root,name,settings)
        except Exception as exc:result=dict(name=name,error=f'{type(exc).__name__}: {exc}')
        results.append(result);print(json.dumps(result),flush=True)
    write_json(settings/'import-report.json',dict(commit=commit,license='MIT',circuits=results))


if __name__=='__main__':main()
