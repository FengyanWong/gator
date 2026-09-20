"""Create an owned three-stage NMOS-current-limited ring VCO; never overwrite cells."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from opamp_connection import add_connection_arguments, configure
from build_opamp_baseline import require_ok, export
from analog_optimizer.backends.gpdk045 import number, equal, set_gpdk_mos
from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend, write_json

PROTECTED = ('ota5_v1', 'ota7_m5_v2', 'ldo_m6_v1')


def core_devices(cfg):
    devices = []
    for i, (input_net, output_net) in enumerate((('VOUT', 'N1'), ('N1', 'N2'), ('N2', 'VOUT')), 1):
        devices.extend([
            (f'MP{i}', cfg['pmos_cell'], cfg['p_width'], cfg['inverter_length'],
             dict(D=output_net, G=input_net, S='VDD', B='VDD')),
            (f'MN{i}', cfg['nmos_cell'], cfg['n_width'], cfg['inverter_length'],
             dict(D=output_net, G=input_net, S=f'S{i}', B='VSS')),
            (f'MS{i}', cfg['nmos_cell'], cfg['limiter_width'], cfg['limiter_length'],
             dict(D=f'S{i}', G='VCTRL', S='VSS', B='VSS'))])
    return devices


def build(client, cfg, library, remote_path, output):
    from virtuoso_bridge.virtuoso.ops import escape_skill_string as esc
    from virtuoso_bridge.virtuoso.schematic.ops import (
        schematic_create_inst_by_master_name as inst, schematic_label_instance_term as label,
        schematic_create_pin as pin)
    from virtuoso_bridge.virtuoso.schematic.params import set_instance_params
    core, tb = cfg['core_cell'], cfg['testbench_cell']
    for cell in (core, tb):
        if require_ok(client.execute_skill(f'ddGetObj("{esc(library)}" "{esc(cell)}")')).output.strip() != 'nil':
            raise RuntimeError(f'Refusing to overwrite {library}/{cell}')
    info = client.library.get(library)
    if info.path != remote_path or info.technology_library != cfg['pdk_library']:
        raise ValueError('Library location or technology mismatch')
    masters = [(cfg['pdk_library'], cfg[k]) for k in ('nmos_cell', 'pmos_cell')]
    masters += [('analogLib', c) for c in ('vdc', 'cap', 'gnd')]
    for lib, cell in masters:
        ports = {p['name'] for p in client.symbol.read_ports(lib, cell)['terms']}
        expected = {'D','G','S','B'} if lib == cfg['pdk_library'] else {'gnd!'} if cell == 'gnd' else {'PLUS','MINUS'}
        if ports != expected:
            raise ValueError(f'Unexpected master terminals: {lib}/{cell}')
    write_json(output/'creation.json', dict(library=library, core_cell=core, testbench_cell=tb,
               config=cfg, created_at=datetime.now(timezone.utc).isoformat()))
    devices = core_devices(cfg)
    caps = [('C1', 'N1'), ('C2', 'N2'), ('C3', 'VOUT')]
    ports = [('VCTRL','input'), ('VDD','inputOutput'), ('VSS','inputOutput'), ('VOUT','output')]
    with client.schematic.create(library, core, timeout=90) as sch:
        for j, (name, cell, width, length, terms) in enumerate(devices):
            sch.add(inst(cfg['pdk_library'], cell, 'symbol', name, (j//3)*4., (2-j%3)*2., 'R0'))
            for terminal, net in terms.items(): sch.add(label(name, terminal, net))
        for i, (name, net) in enumerate(caps):
            sch.add(inst('analogLib', 'cap', 'symbol', name, 2.+i*4., 3., 'R0'))
            sch.add(label(name, 'PLUS', net)); sch.add(label(name, 'MINUS', 'VSS'))
        for i, (name, direction) in enumerate(ports):
            sch.add(pin(name, -2., 4.-i, 'R0', direction=direction))
    require_ok(client.open_window(library, core, view='schematic'))
    for name, cell, width, length, terms in devices:
        set_gpdk_mos(client, library, core, name, width, length)
    for name, net in caps:
        set_instance_params(client, name, param_filters=None, strict=True, c=cfg['stage_capacitance'])
    snapshot = client.schematic.read(library, core, include_positions=True, param_filters=None)
    actual = {i['name']:i for i in snapshot['instances']}
    if set(actual) != {d[0] for d in devices}|{c[0] for c in caps}: raise ValueError('Unexpected core instances')
    for name, cell, width, length, terms in devices:
        if actual[name]['terms'] != terms: raise ValueError(f'Incorrect connections: {name}')
        for key, expected in (('w',width), ('fw',width), ('l',length), ('m','1'), ('fingers','1')):
            if not equal(number(actual[name]['params'][key]), number(expected)):
                raise ValueError(f'CDF mismatch: {name}.{key}')
    for name, net in caps:
        if actual[name]['terms'] != dict(PLUS=net, MINUS='VSS') or not equal(number(actual[name]['params']['c']), number(cfg['stage_capacitance'])):
            raise ValueError('Stage capacitor mismatch')
    write_json(output/'core_readback.json', snapshot)
    write_json(output/'symbol.json', asdict(client.symbol.generate_from_schematic(library, core, sort_pins='alphanumeric', overwrite=False)))
    with client.schematic.create(library, tb, timeout=90) as sch:
        sch.add(inst(library, core, 'symbol', 'XU1', 3., 1.5, 'R0'))
        for name, _ in ports: sch.add(label('XU1', name, 'gnd!' if name == 'VSS' else name))
        for i, name in enumerate(('VDD','VCTRL')):
            sch.add(inst('analogLib','vdc','symbol', name, i*2., -1., 'R0'))
            sch.add(label(name,'PLUS',name)); sch.add(label(name,'MINUS','gnd!'))
        sch.add(inst('analogLib','gnd','symbol','GND',6.,-1.,'R0'))
    require_ok(client.open_window(library, tb, view='schematic'))
    for name, value in (('VDD',cfg['supply_v']), ('VCTRL',cfg['control_v'])):
        set_instance_params(client, name, param_filters=None, strict=True, vdc=value, acm='0', acp='0')
    write_json(output/'testbench_readback.json', client.schematic.read(library,tb,param_filters=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--remote-library-path', required=True)
    args = parser.parse_args()
    config, profile = configure(args)
    args.output.mkdir(parents=True, exist_ok=False)
    design = json.loads((ROOT/'configs/gpdk045_vco_design.json').read_text())
    report = dict(completed=False, real_simulation_calls=0, protected_circuits_unchanged=False)
    try:
        with (args.output/'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log), VirtuosoBridgeBackend(config, profile) as backend:
            def snapshots():
                return {c:backend.client.schematic.read(args.library,c,include_positions=True,param_filters=None) for c in PROTECTED}
            before = snapshots(); write_json(args.output/'protected-before.json', before)
            try:
                build(backend.client, design, args.library, args.remote_library_path, args.output)
                export(backend.client, design, args.library, args.output)
                report['completed'] = True
            finally:
                after = snapshots(); write_json(args.output/'protected-after.json', after)
                report['protected_circuits_unchanged'] = before == after
                if before != after: raise RuntimeError('Protected circuit changed')
    except BaseException as exc:
        report.update(error_type=type(exc).__name__, error=str(exc)); raise
    finally:
        write_json(args.output/'build-report.json', report)
        print('BUILD', args.output, report, flush=True)


if __name__ == '__main__': main()
