"""Saving a task of the ring-oscillator cell the way the task-save tests do - its configuration with a frequency probe and spec, a ready working copy, Save task with fake programs - shared with other test modules (refactoring package D1)."""

import sys

from gator_workbench import profiles, schema, tasks, virtuoso_setup as vs, working_copy

from helpers import probe
from ring_cell_support import connection_file, FIXTURE, read_cell, ROWS
from fakes_virtuoso import CELL, COPY, copy_reader, fake_writer, LIB, maestro_netlister, SETUP, setup_writer, TB


FREQUENCY_PROBE = dict(measurement_id='m_osc_frequency_hz', analysis='tran', result_source='backend_profile', source_name='osc_frequency_hz', unit='Hz')


FREQUENCY_SPEC = dict(metric_id='osc_frequency_hz', equation='m_osc_frequency_hz', unit='Hz', constraint='>=', lower=1.1e9, normalization_scale=1e9)


def task_copier(tmp_path):
    """Stands in for `bridge_setup make_copy` making a "Save as" copy with renamed cells inside the copy library."""
    script = tmp_path / 'task_copier.py'
    script.write_text(f'''
import json, re, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{a: argv[i + 1] for i, a in enumerate(argv) if a.startswith('--') and i + 1 < len(argv) and not argv[i + 1].startswith('--')}}
rename = json.loads(args['--rename'])
with open({str(tmp_path / 'copier_calls.jsonl')!r}, 'a') as f:
    f.write(json.dumps(args) + '\\n')
out = Path(args['--output'])
text = (Path({str(FIXTURE)!r}) / 'netlist.scs').read_text().replace('// Library name: {LIB}', '// Library name: {COPY}')
for old, new in sorted(rename.items(), key=lambda kv: -len(kv[0])):
    text = re.sub(r'(?<![A-Za-z0-9_])' + re.escape(old) + r'(?![A-Za-z0-9_])', new, text)
(out / 'progress.json').write_text(json.dumps(dict(created_library=False, copied=[v + '/schematic' for v in rename.values()])))
(out / 'netlist.scs').write_text(text)
same = 'a' * 64
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench=args['--testbench'], copy_library=args['--copy-library'],
                      copy_path='/home/minlei/{COPY}', copy_cell=rename[args['--cell']], copy_testbench=rename[args['--testbench']],
                      rename=rename, technology_library='gpdk045', copy_technology_library='gpdk045', working_dir='/home/minlei',
                      created_library=False, cds_lib='/home/minlei/cds.lib', cells=[], copied=[dict(cell=v, view='schematic') for v in rename.values()],
                      remastered={{}}, originals_before={{k: same for k in rename}}, originals_after={{k: same for k in rename}})))
''')
    return [sys.executable, str(script)]


def config(probes=(FREQUENCY_PROBE,), specs=(FREQUENCY_SPEC,), rows=ROWS):
    return schema.WorkbenchConfig.model_validate(dict(
        circuit=dict(source='virtuoso', library=LIB, cell=CELL, testbench_cell=TB, circuit_class='vco'),
        parameters=list(rows), measurements=list(probes), targets=list(specs), run=dict(max_evaluations=5)))


def ready(tmp_path):
    """The user's ring oscillator read into the workbench through its testbench, with a verified working copy."""
    connection_file()
    read_cell(tmp_path)
    assert working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))['verified']


def save(tmp_path, name='ring_osc', cfg=None, **kwargs):
    commands = dict(read=copy_reader(tmp_path), copy=task_copier(tmp_path), **kwargs.pop('commands', {}))
    return profiles.save_task(probe(tmp_path), 'lab', name, cfg or config(), library=LIB, cell=CELL, commands=commands, **kwargs)


def task_config(tmp_path, name='ring_osc', **run):
    """The configuration the page holds for a saved task: exactly its saved rows (what "Reload saved values" brings)."""
    raw = tasks.starter_config(f'real:{name}')
    raw['run'] = dict(dict(max_evaluations=3, connection_profile_id='lab'), **run)
    raw['output'] = dict(output_root=str(tmp_path / 'out'), experiment_name='t')
    return schema.WorkbenchConfig.model_validate(raw)


def saved_ring(tmp_path):
    ready(tmp_path)
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9))
    return task_config(tmp_path)


def saved_maestro_task(tmp_path):
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n'}},
                  variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    save(tmp_path, name='ring_maestro', cfg=config(probes=rows['measurements'], specs=rows['targets']),
         extras=dict(analyses={'tran': {'stop': '50n'}}), commands=dict(setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path)))
    raw = tasks.starter_config('real:ring_maestro')
    raw['run'] = dict(max_evaluations=3, connection_profile_id='lab')
    return schema.WorkbenchConfig.model_validate(raw)
