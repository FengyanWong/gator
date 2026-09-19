"""Create a new GPDK045 five-transistor OTA and export its AC testbench.

Run with the verified virtuoso-bridge environment. This script requires an
already-running bridge, refuses existing target cells, and never starts or
reconfigures a daemon. All host and library paths are explicit arguments.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from analog_optimizer.netlist.expressions import evaluate


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def require_ok(result):
    if not result.ok:
        raise RuntimeError("; ".join(result.errors))
    return result


from analog_optimizer.backends.gpdk045 import set_gpdk_mos


def configure_created(client, cfg, library, output):
    """Repair/configure only cells with a matching creation receipt."""
    receipt = json.loads((output / 'creation.json').read_text())
    if (receipt['library'] != library or receipt['core_cell'] != cfg['core_cell']
            or receipt['testbench_cell'] != cfg['testbench_cell']
            or not (output / 'core_readback.json').is_file()):
        raise RuntimeError('Missing matching creation receipt')
    core, tb = cfg['core_cell'], cfg['testbench_cell']
    for name, group in [('M1','input'), ('M2','input'), ('M3','load'), ('M4','load'), ('M5','tail')]:
        set_gpdk_mos(client, library, core, name, cfg[f'{group}_width'], cfg[f'{group}_length'])
    from virtuoso_bridge.virtuoso.schematic.ops import schematic_create_inst_by_master_name as inst
    tb_data = client.schematic.read(library, tb)
    with client.schematic.modify(library, tb) as sch:
        sch.add('foreach(s cv~>shapes when(s~>objType == "label" && s~>theLabel == "0" s~>theLabel = "gnd!"))')
        if not any(i['name'] == 'GND' for i in tb_data['instances']):
            sch.add(inst('analogLib', 'gnd', 'symbol', 'GND', 7.5, -1.0, 'R0'))
    write_json(output / 'core_readback.json', client.schematic.read(library, core, include_positions=True, param_filters=None))
    write_json(output / 'testbench_readback.json', client.schematic.read(library, tb, param_filters=None))
    print('Configured PDK callbacks and ground; readback saved', flush=True)


def build(client, cfg, library, remote_library_path, output):
    from virtuoso_bridge.virtuoso.ops import escape_skill_string
    from virtuoso_bridge.virtuoso.schematic.ops import (
        schematic_create_inst_by_master_name as inst,
        schematic_label_instance_term as label,
        schematic_create_pin as pin,
    )
    from virtuoso_bridge.virtuoso.schematic.params import set_instance_params

    core, tb = cfg['core_cell'], cfg['testbench_cell']
    for cell in (core, tb):
        exists = require_ok(client.execute_skill(
            f'ddGetObj("{escape_skill_string(library)}" "{escape_skill_string(cell)}")'
        )).output.strip()
        if exists != 'nil':
            raise RuntimeError(f'Refusing to overwrite existing cell {library}/{cell}')
    # Verify actual master terminals before any creation.
    masters = [(cfg['pdk_library'], cfg['nmos_cell']), (cfg['pdk_library'], cfg['pmos_cell']),
               ('analogLib', 'vdc'), ('analogLib', 'cap'), ('analogLib', 'gnd')]
    master_info = {}
    for lib, cell in masters:
        ports = client.symbol.read_ports(lib, cell)
        names = {p['name'] for p in ports['terms']}
        expected = ({'D', 'G', 'S', 'B'} if lib == cfg['pdk_library'] else
                    {'gnd!'} if cell == 'gnd' else {'PLUS', 'MINUS'})
        if names != expected:
            raise RuntimeError(f'Unexpected terminals for {lib}/{cell}: {names}')
        master_info[f'{lib}/{cell}'] = ports
    write_json(output / 'master_ports.json', master_info)
    if library not in client.library.list():
        info = client.library.create(library, remote_library_path, technology_library=cfg['pdk_library'])
    else:
        info = client.library.get(library)
        if info.path != remote_library_path or info.technology_library != cfg['pdk_library']:
            raise RuntimeError('Existing library path or technology binding does not match')
    write_json(output / 'library.json', asdict(info))
    write_json(output / 'creation.json', {'library': library, 'core_cell': core,
                                        'testbench_cell': tb, 'config': cfg,
                                        'created_at': datetime.now(timezone.utc).isoformat()})

    devices = [
        ('M1', cfg['nmos_cell'], 0.0, 1.5, 'R0', {'D': 'NLOAD', 'G': 'VINP', 'S': 'NTAIL', 'B': 'VSS'}, 'input'),
        ('M2', cfg['nmos_cell'], 3.0, 1.5, 'MY', {'D': 'VOUT', 'G': 'VINN', 'S': 'NTAIL', 'B': 'VSS'}, 'input'),
        ('M3', cfg['pmos_cell'], 0.0, 3.0, 'R0', {'D': 'NLOAD', 'G': 'NLOAD', 'S': 'VDD', 'B': 'VDD'}, 'load'),
        ('M4', cfg['pmos_cell'], 3.0, 3.0, 'MY', {'D': 'VOUT', 'G': 'NLOAD', 'S': 'VDD', 'B': 'VDD'}, 'load'),
        ('M5', cfg['nmos_cell'], 1.5, 0.0, 'R0', {'D': 'NTAIL', 'G': 'VBIAS', 'S': 'VSS', 'B': 'VSS'}, 'tail'),
    ]
    with client.schematic.create(library, core, timeout=90) as sch:
        for name, cell, x, y, orient, terms, _ in devices:
            sch.add(inst(cfg['pdk_library'], cell, 'symbol', name, x, y, orient))
            for term, net in terms.items():
                sch.add(label(name, term, net))
        for i, (name, direction) in enumerate([
            ('VINP', 'input'), ('VINN', 'input'), ('VBIAS', 'input'),
            ('VDD', 'inputOutput'), ('VSS', 'inputOutput'), ('VOUT', 'output'),
        ]):
            sch.add(pin(name, -2.0, 4.0 - i * 0.75, 'R0', direction=direction))
    require_ok(client.open_window(library, core, view='schematic'))
    for name, _, _, _, _, _, group in devices:
        set_gpdk_mos(client, library, core, name, cfg[f'{group}_width'], cfg[f'{group}_length'])
    actual = client.schematic.read(library, core, include_positions=True, param_filters=None)
    by_name = {item['name']: item for item in actual['instances']}
    if set(by_name) != {d[0] for d in devices}:
        raise RuntimeError('Core instance readback mismatch')
    for name, _, _, _, _, terms, group in devices:
        if by_name[name]['terms'] != terms:
            raise RuntimeError(f'Terminal readback mismatch: {name}: {by_name[name]["terms"]}')
        for key, expected in [('w', cfg[f'{group}_width']), ('fw', cfg[f'{group}_width']),
                              ('l', cfg[f'{group}_length']), ('fingers', '1')]:
            actual_value = by_name[name]['params'].get(key)
            if actual_value is None or not math.isclose(evaluate(str(actual_value), {}.__getitem__),
                                                       evaluate(expected, {}.__getitem__), rel_tol=1e-9):
                raise RuntimeError(f'CDF readback mismatch: {name}.{key}={actual_value}, expected {expected}')
    write_json(output / 'core_readback.json', actual)
    symbol = client.symbol.generate_from_schematic(library, core, sort_pins='alphanumeric', overwrite=False)
    write_json(output / 'symbol.json', asdict(symbol))

    sources = [('VDD', 'VDD', cfg['supply_v'], '0', '0'),
               ('VB', 'VBIAS', cfg['bias_v'], '0', '0'),
               ('VP', 'VINP', cfg['common_mode_v'], '0.5', '0'),
               ('VN', 'VINN', cfg['common_mode_v'], '0.5', '180')]
    with client.schematic.create(library, tb, timeout=90) as sch:
        sch.add(inst(library, core, 'symbol', 'XU1', 3.0, 1.5, 'R0'))
        for name in ('VINP', 'VINN', 'VBIAS', 'VDD', 'VSS', 'VOUT'):
            sch.add(label('XU1', name, 'gnd!' if name == 'VSS' else name))
        for i, (name, net, *_rest) in enumerate(sources):
            sch.add(inst('analogLib', 'vdc', 'symbol', name, i * 1.5, -1.0, 'R0'))
            sch.add(label(name, 'PLUS', net))
            sch.add(label(name, 'MINUS', 'gnd!'))
        sch.add(inst('analogLib', 'cap', 'symbol', 'CL', 6.0, 1.5, 'R0'))
        sch.add(label('CL', 'PLUS', 'VOUT'))
        sch.add(label('CL', 'MINUS', 'gnd!'))
        sch.add(inst('analogLib', 'gnd', 'symbol', 'GND', 7.5, -1.0, 'R0'))
    require_ok(client.open_window(library, tb, view='schematic'))
    for name, _net, dc, ac, phase in sources:
        set_instance_params(client, name, param_filters=None, strict=True, vdc=dc, acm=ac, acp=phase)
    set_instance_params(client, 'CL', param_filters=None, strict=True, c=cfg['load_capacitance'])
    write_json(output / 'testbench_readback.json', client.schematic.read(library, tb, param_filters=None))
    print(f'Created {library}/{core} and {library}/{tb}', flush=True)


def export(client, cfg, library, output):
    # Upstream OCEAN export changes the session's simulator/design selection.
    # Do not run while a user ADE/Maestro window is active.
    windows = client.list_windows()
    if any(any(t in w.get('name', '').lower() for t in ('maestro', 'assembler', 'explorer', 'analog design')) for w in windows):
        raise RuntimeError('Close active ADE/Maestro sessions before OCEAN export')
    package = output / ('export-' + uuid4().hex)
    result = client.schematic.export_netlist(library, cfg['testbench_cell'], package, timeout=120)
    manifest = {
        'origin': 'real', 'operation': 'schematic_netlist_export',
        'library': library, 'cell': cfg['testbench_cell'],
        'bridge_version': importlib.metadata.version('virtuoso-bridge'),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_file': result['source_file'], 'input_file': result['input_file'],
        'files': {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in package.rglob('*') if p.is_file()},
    }
    write_json(output / 'export_manifest.json', manifest)
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}, indent=2), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['create', 'configure', 'export'])
    p.add_argument('--env', type=Path, required=True)
    p.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/gpdk045_opamp_design.json')
    p.add_argument('--library', required=True)
    p.add_argument('--remote-library-path')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.action == 'create' and not a.remote_library_path:
        p.error('--remote-library-path is required for create')
    from virtuoso_bridge import VirtuosoClient
    from virtuoso_bridge.env import set_runtime_env_file
    from virtuoso_bridge.transport.tunnel import SSHClient
    set_runtime_env_file(a.env.resolve())
    if not SSHClient.is_running():
        raise RuntimeError('An existing bridge tunnel is required; no automatic startup')
    client = VirtuosoClient.from_env(timeout=30, log_to_ciw=False)
    cfg = json.loads(a.config.read_text())
    a.output.mkdir(parents=True, exist_ok=True)
    if a.action == 'create':
        build(client, cfg, a.library, a.remote_library_path, a.output)
    elif a.action == 'configure':
        configure_created(client, cfg, a.library, a.output)
    else:
        export(client, cfg, a.library, a.output)


if __name__ == '__main__':
    main()
