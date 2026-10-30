"""Create a dedicated six-MOS LDO, refusing existing cells and protecting both OTAs."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from opamp_connection import add_connection_arguments, configure
from build_opamp_baseline import require_ok, export
from analog_optimizer.backends.gpdk045 import number, equal, set_gpdk_mos
from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend, write_json


def core_devices(cfg):
    # Positive OTA input is feedback: the PMOS pass stage adds one inversion.
    return [
        ('M1', cfg['nmos_cell'], 'input', {'D':'NLOAD','G':'VFB','S':'NTAIL','B':'VSS'}),
        ('M2', cfg['nmos_cell'], 'input', {'D':'VGATE','G':'VREF','S':'NTAIL','B':'VSS'}),
        ('M3', cfg['pmos_cell'], 'load', {'D':'NLOAD','G':'NLOAD','S':'VDD','B':'VDD'}),
        ('M4', cfg['pmos_cell'], 'load', {'D':'VGATE','G':'NLOAD','S':'VDD','B':'VDD'}),
        ('M5', cfg['nmos_cell'], 'tail', {'D':'NTAIL','G':'VBIAS','S':'VSS','B':'VSS'}),
        ('MP', cfg['pmos_cell'], 'pass', {'D':'VOUT','G':'VGATE','S':'VDD','B':'VDD'}),
    ]


def build(client, cfg, library, remote_library_path, output):
    from virtuoso_bridge.virtuoso.ops import escape_skill_string as esc
    from virtuoso_bridge.virtuoso.schematic.ops import (
        schematic_create_inst_by_master_name as inst, schematic_label_instance_term as label,
        schematic_create_pin as pin)
    from virtuoso_bridge.virtuoso.schematic.params import set_instance_params
    if cfg['topology'] != 'pmos_pass_ldo':
        raise ValueError('Explicit LDO design required')
    core, tb = cfg['core_cell'], cfg['testbench_cell']
    for cell in (core, tb):
        if require_ok(client.execute_skill(f'ddGetObj("{esc(library)}" "{esc(cell)}")')).output.strip() != 'nil':
            raise RuntimeError(f'Refusing to overwrite {library}/{cell}')
    library_info = client.library.get(library)
    if library_info.path != remote_library_path or library_info.technology_library != cfg['pdk_library']:
        raise ValueError('Library location or technology changed')
    masters = [(cfg['pdk_library'], cfg['nmos_cell']), (cfg['pdk_library'], cfg['pmos_cell'])]
    masters += [('analogLib', c) for c in ('vdc','ipulse','res','cap','gnd')]
    for lib, cell in masters:
        ports = {p['name'] for p in client.symbol.read_ports(lib, cell)['terms']}
        expected = {'D','G','S','B'} if lib == cfg['pdk_library'] else {'gnd!'} if cell == 'gnd' else {'PLUS','MINUS'}
        if ports != expected:
            raise ValueError(f'Unexpected master terminals: {lib}/{cell}')
    cdf_names = require_ok(client.execute_skill('cdfGetBaseCellCDF(ddGetObj("analogLib" "ipulse"))~>parameters~>name')).output
    write_json(output/'source-cdf-parameters.json', {'ipulse': cdf_names})
    if any(f'"{name}"' not in cdf_names for name in ('i1','i2','td','tr','tf','pw','per','idc')):
        raise ValueError('Installed ipulse CDF differs from the declared pulse contract')
    write_json(output/'creation.json', dict(library=library,core_cell=core,testbench_cell=tb,
        config=cfg,created_at=datetime.now(timezone.utc).isoformat()))
    devices = core_devices(cfg)
    ports = [('VREF','input'),('VBIAS','input'),('VDD','inputOutput'),('VSS','inputOutput'),('VOUT','output')]
    with client.schematic.create(library, core, timeout=90) as sch:
        for i,(name,cell,group,terms) in enumerate(devices):
            sch.add(inst(cfg['pdk_library'],cell,'symbol',name,3.*(i%3),3.*(i//3),'R0'))
            for terminal,net in terms.items():
                sch.add(label(name,terminal,net))
        for i,(name,positive,negative) in enumerate((('RUP','VOUT','VFB'),('RDN','VFB','VSS'))):
            sch.add(inst('analogLib','res','symbol',name,9.,3.-i*1.5,'R0'))
            sch.add(label(name,'PLUS',positive)); sch.add(label(name,'MINUS',negative))
        for i,(name,direction) in enumerate(ports):
            sch.add(pin(name,-2.,4.-i*.75,'R0',direction=direction))
    require_ok(client.open_window(library,core,view='schematic'))
    for name,cell,group,terms in devices:
        set_gpdk_mos(client,library,core,name,cfg[f'{group}_width'],cfg[f'{group}_length'])
    for name,key in (('RUP','feedback_upper'),('RDN','feedback_lower')):
        set_instance_params(client,name,param_filters=None,strict=True,r=cfg[key])
    snapshot = client.schematic.read(library,core,include_positions=True,param_filters=None)
    actual = {i['name']:i for i in snapshot['instances']}
    if set(actual) != {d[0] for d in devices} | {'RUP','RDN'}:
        raise ValueError('Unexpected LDO core instance set')
    for name,cell,group,terms in devices:
        if actual[name]['terms'] != terms:
            raise ValueError(f'Core terminal mismatch: {name}')
        for key,expected in (('w',cfg[f'{group}_width']),('fw',cfg[f'{group}_width']),
                             ('l',cfg[f'{group}_length']),('fingers','1'),('m','1')):
            if not equal(number(actual[name]['params'][key]),number(expected)):
                raise ValueError(f'CDF mismatch: {name}.{key}')
    for name,key,terms in (('RUP','feedback_upper',{'PLUS':'VOUT','MINUS':'VFB'}),
                            ('RDN','feedback_lower',{'PLUS':'VFB','MINUS':'VSS'})):
        if actual[name]['terms'] != terms or not equal(number(actual[name]['params']['r']),number(cfg[key])):
            raise ValueError('Feedback divider mismatch')
    write_json(output/'core_readback.json', snapshot)
    write_json(output/'symbol.json',asdict(client.symbol.generate_from_schematic(library,core,sort_pins='alphanumeric',overwrite=False)))
    sources = [('VDD','VDD',cfg['supply_v'],'1'),('VREF','VREF',cfg['reference_v'],'0'),('VB','VBIAS',cfg['bias_v'],'0')]
    with client.schematic.create(library,tb,timeout=90) as sch:
        sch.add(inst(library,core,'symbol','XU1',3.,1.5,'R0'))
        for name,_ in ports:
            sch.add(label('XU1',name,'gnd!' if name=='VSS' else name))
        for i,(name,net,dc,ac) in enumerate(sources):
            sch.add(inst('analogLib','vdc','symbol',name,i*1.5,-1.,'R0'))
            sch.add(label(name,'PLUS',net)); sch.add(label(name,'MINUS','gnd!'))
        for i,(name,cell) in enumerate((('COUT','cap'),('ILOAD','ipulse'))):
            sch.add(inst('analogLib',cell,'symbol',name,6.+i*1.5,1.5,'R0'))
            sch.add(label(name,'PLUS','VOUT')); sch.add(label(name,'MINUS','gnd!'))
        sch.add(inst('analogLib','gnd','symbol','GND',9.,-1.,'R0'))
    require_ok(client.open_window(library,tb,view='schematic'))
    for name,net,dc,ac in sources:
        set_instance_params(client,name,param_filters=None,strict=True,vdc=dc,acm=ac,acp='0')
    set_instance_params(client,'COUT',param_filters=None,strict=True,c=cfg['output_capacitance'])
    set_instance_params(client,'ILOAD',param_filters=None,strict=True,idc=cfg['load_current'],
        i1=cfg['load_current'],i2=cfg['load_current_high'],td=cfg['step_delay'],tr=cfg['step_rise'],
        tf=cfg['step_rise'],pw=cfg['step_width'],per=cfg['step_period'],acm='0')
    write_json(output/'testbench_readback.json',client.schematic.read(library,tb,param_filters=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--remote-library-path',required=True)
    args=parser.parse_args()
    config,profile=configure(args)
    args.output.mkdir(parents=True,exist_ok=False)
    design=json.loads((ROOT/'configs/gpdk045_ldo_design.json').read_text())
    report=dict(completed=False,protected_circuits_unchanged=False,real_simulation_calls=0)
    try:
        with (args.output/'bridge.log').open('w') as log,redirect_stdout(log),redirect_stderr(log),VirtuosoBridgeBackend(config,profile) as backend:
            def snapshots():
                return {cell:backend.client.schematic.read(args.library,cell,include_positions=True,param_filters=None)
                        for cell in ('ota5_v1','ota7_m5_v2')}
            before=snapshots(); write_json(args.output/'protected-before.json',before)
            try:
                build(backend.client,design,args.library,args.remote_library_path,args.output)
                export(backend.client,design,args.library,args.output)
                report['completed']=True
            finally:
                after=snapshots(); write_json(args.output/'protected-after.json',after)
                report['protected_circuits_unchanged']=before==after
                if before != after:
                    raise RuntimeError('Protected OTA circuit changed')
    except BaseException as exc:
        report.update(error_type=type(exc).__name__,error=str(exc)); raise
    finally:
        write_json(args.output/'build-report.json',report)
        print('BUILD',args.output,report,flush=True)


if __name__=='__main__':
    main()
