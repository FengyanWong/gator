"""The ring-oscillator test cell of the profile tests - its recorded export, a fake reader of it, its rows and configuration, a connection file - that several test modules share (refactoring package D1)."""

import json
from pathlib import Path
import sys
from gator_workbench import bridge_read, schema
from gator_workbench.paths import local_settings_dir
from helpers import probe


FIXTURE = Path(__file__).parent / 'fixtures' / 'ring_osc'


CIRCUIT = dict(source='virtuoso', library='GPDK045_RINGOSC', cell='ring_osc_3stage', testbench_cell='tb_ring_osc_3stage', circuit_class='vco')


def fake_reader(tmp_path, *, testbench=True):
    script = tmp_path / 'ring_reader.py'
    script.write_text(f'''
import json, shutil, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output']); out.mkdir(parents=True)
for name in ('netlist.scs', 'core_readback.json') + (('testbench_readback.json',) if {testbench!r} else ()):
    shutil.copy(Path({str(FIXTURE)!r}) / name, out / name)
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


def read_cell(tmp_path, testbench='tb_ring_osc_3stage'):
    return bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GPDK045_RINGOSC', cell='ring_osc_3stage',
                            testbench=testbench, command=fake_reader(tmp_path, testbench=bool(testbench)))


def row(variable_id, instance, lower=None, upper=None, leader=None, **more):
    return dict(dict(variable_id=variable_id, instance_path=instance, parameter_name='w', unit='um', optimized=True, lower=lower,
                     upper=upper, binding_group=leader, ratio=1.0), **more)


ROWS = [row('wn', 'XU1/MN1', 0.6, 1.6), row('wn2', 'XU1/MN2', leader='wn'), row('wn3', 'XU1/MN3', leader='wn'),
        row('wp', 'XU1/MP1', 1.2003, 3.2), row('wp2', 'XU1/MP2', leader='wp'), row('wp3', 'XU1/MP3', leader='wp')]


def config(rows=ROWS, **circuit):
    return schema.WorkbenchConfig.model_validate(dict(circuit=dict(CIRCUIT, **circuit), parameters=rows, run=dict(max_evaluations=5)))


def connection_file():
    target = local_settings_dir() / 'bridge_connection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(env_file='/x/.env', library='GATOR_TESTS', model_file='/pdk/model.scs')))))
