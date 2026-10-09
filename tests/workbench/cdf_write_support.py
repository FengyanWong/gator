"""The CDF-write tests' variant of the ring-oscillator cell - a reader that also brings the CDF facts, rows of several parameters and units, a profile made from them - that other test modules share (refactoring package D1)."""

import sys
from gator_workbench import bridge_read, profiles, schema
from helpers import probe
from ring_cell_support import CIRCUIT, FIXTURE


def fake_reader(tmp_path, files=('netlist.scs', 'core_readback.json', 'testbench_readback.json', 'core_cdf.json')):
    script = tmp_path / 'ring_reader.py'
    script.write_text(f'''
import json, shutil, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output']); out.mkdir(parents=True)
for name in {tuple(files)!r}:
    shutil.copy(Path({str(FIXTURE)!r}) / name, out / name)
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


def read_cell(tmp_path, **kw):
    return bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GPDK045_RINGOSC', cell='ring_osc_3stage',
                            testbench='tb_ring_osc_3stage', command=fake_reader(tmp_path, **kw))


def row(variable_id, instance, parameter='w', unit='um', lower=None, upper=None, leader=None, **more):
    return dict(dict(variable_id=variable_id, instance_path=instance, parameter_name=parameter, unit=unit, optimized=True,
                     lower=lower, upper=upper, binding_group=leader, ratio=1.0), **more)


def stage_rows(parameter, lead, lower, upper, instances=('MN1', 'MN2', 'MN3'), unit='um', **more):
    first, *rest = instances
    return [row(lead, f'XU1/{first}', parameter, unit, lower, upper, **more)] + [
        row(f'{lead}{i + 2}', f'XU1/{name}', parameter, unit, leader=lead) for i, name in enumerate(rest)]


MIXED = (stage_rows('w', 'wn', 0.6, 1.6) + stage_rows('l', 'ln', 0.045, 0.1)
         + stage_rows('w', 'wc', 2.0, 5.6, instances=('C1', 'C2', 'C3'))
         + [row('mc', 'XU1/C1', 'm', 'count', 1, 4, value_type='integer')])


def config(rows):
    return schema.WorkbenchConfig.model_validate(dict(circuit=CIRCUIT, parameters=rows, run=dict(max_evaluations=5)))


def make(tmp_path, rows=MIXED, name='ring_cdf'):
    read_cell(tmp_path)
    return profiles.create_profile(name, config(rows), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
