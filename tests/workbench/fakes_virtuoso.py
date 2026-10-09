"""Fake Virtuoso-side programs and cells that several test modules share: the setup writer, the working-copy writer and its cells, an exported cell's reader, the Maestro netlister and the copy reader (refactoring package D1)."""

import json
import sys
from pathlib import Path
from gator_workbench import bridge_read
from helpers import probe
from ring_cell_support import FIXTURE


REPO = Path(__file__).resolve().parents[2]
RING = (REPO / 'tests/workbench/fixtures/ring_osc/netlist.scs').read_text()        # the user's real ring-oscillator export
LIB, CELL, TB, COPY = 'GPDK045_RINGOSC', 'ring_osc_3stage', 'tb_ring_osc_3stage', 'GPDK045_RINGOSC_GATOR'

SETUP = dict(test='GATOR', model_files=[['/pdk/gpdk045.scs', 'tt']], analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}},
             outputs=[dict(name='freq', expression='frequency(VT("/OUT"))'), dict(name='vmax', expression='ymax(VT("/OUT"))')],
             specs=[dict(output='freq', op='gt', value='1e+09'), dict(output='vmax', op='range', value=['0.9', '1.1'])],
             variables={'VSUP': '1.0'}, bindings=[dict(cell=TB, instance='V0', parameter='vdc', variable='VSUP')])


def setup_writer(tmp_path, answer):
    """Stands in for the setup ops of `python -m gator_workbench.bridge_setup`: logs the request, answers `answer`."""
    script = tmp_path / 'setup_writer.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{a: argv[i + 1] for i, a in enumerate(argv) if a.startswith('--') and i + 1 < len(argv)}}
request = json.loads(Path(args['--request']).read_text())
with open({str(tmp_path / 'setup_calls.jsonl')!r}, 'a') as f:
    f.write(json.dumps(dict(op=args['--op'], copy=args['--copy-library'], testbench=args['--testbench'], request=request)) + '\\n')
print(json.dumps({json.dumps(answer)!r} and json.loads({json.dumps(answer)!r})))
''')
    return [sys.executable, str(script)]


def imported(tmp_path):
    script = tmp_path / 'reader.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output'])
out.mkdir(parents=True)
(out / 'netlist.scs').write_text({RING!r})
(out / 'core_readback.json').write_text(json.dumps(dict(origin='fixture', instances=[])))
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    return bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library=LIB, cell=CELL, testbench=TB,
                            command=[sys.executable, str(script)])


def fake_writer(tmp_path, *, netlist=None, touched=False, fail_after=None, created=True, log='calls.jsonl'):
    """Stands in for `python -m gator_workbench.bridge_setup`: writes what the real process writes."""
    copy_netlist = RING.replace(f'// Library name: {LIB}', f'// Library name: {COPY}') if netlist is None else netlist
    script = tmp_path / 'writer.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{}}
for i, a in enumerate(argv):
    if a.startswith('--'):
        args[a] = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('--') else True
with open({str(tmp_path / log)!r}, 'a') as f:
    f.write(json.dumps(args) + '\\n')
out = Path(args['--output'])
progress = dict(created_library={created!r} and '--reuse-library' not in args, copied=[])
if progress['created_library']:
    progress.update(copy_path='/home/minlei/{COPY}', copy_technology_library='gpdk045')
for view in ['{TB}/schematic', '{CELL}/schematic', '{CELL}/symbol']:
    if {fail_after!r} is not None and len(progress['copied']) == {fail_after!r}:
        (out / 'progress.json').write_text(json.dumps(progress))
        sys.exit('Traceback\\nRuntimeError: copying {CELL}/symbol: dbCopyCellView refused')
    progress['copied'].append(view)
(out / 'progress.json').write_text(json.dumps(progress))
(out / 'netlist.scs').write_text({copy_netlist!r})
same = 'a' * 64
print(json.dumps(dict(library='{LIB}', cell='{CELL}', testbench='{TB}', copy_library='{COPY}', copy_path='/home/minlei/{COPY}',
                      technology_library='gpdk045', copy_technology_library='gpdk045', working_dir='/home/minlei',
                      created_library=progress['created_library'], cds_lib='/home/minlei/cds.lib',
                      cells=[dict(cell='{TB}', views=['schematic'], has_cdf=False), dict(cell='{CELL}', views=['schematic', 'symbol'], has_cdf=False)],
                      copied=[dict(cell=v.split('/')[0], view=v.split('/')[1]) for v in progress['copied']],
                      remastered={{'{TB}': dict(headers=1, sch_check='(0 0)'), '{CELL}': dict(headers=0, sch_check='(0 0)')}},
                      originals_before={{'{TB}': same, '{CELL}': same}},
                      originals_after={{'{TB}': same, '{CELL}': 'b' * 64 if {touched!r} else same}})))
''')
    return [sys.executable, str(script)]


EXPORT = (REPO / 'examples/circuits/gpdk045_ota5.scs').read_text()            # a recorded REAL Virtuoso export


def fake_reader(tmp_path, netlist=EXPORT, fail=False):
    """Stands in for `python -m gator_workbench.bridge_read`: writes what the real reader writes."""
    script = tmp_path / 'reader.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output'])
out.mkdir(parents=True)
(out / 'netlist.scs').write_text({netlist!r})
(out / 'core_readback.json').write_text(json.dumps(dict(origin='fixture', instances=[])))
if {fail!r}:
    sys.exit('Traceback\\nRuntimeError: export failed on the fixture')
print('progress line the bridge might print')
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'),
                      technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


def copy_reader(tmp_path):
    """Stands in for `bridge_read` reading a working copy INTO the workbench: the recorded export, with the names
    Virtuoso gives the copy (its library in the comments, renamed cells for a "Save as" copy)."""
    script = tmp_path / 'copy_reader.py'
    script.write_text(f'''
import json, re, shutil, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output']); out.mkdir(parents=True)
text = (Path({str(FIXTURE)!r}) / 'netlist.scs').read_text().replace('// Library name: {LIB}', '// Library name: ' + args['--library'])
text = re.sub(r'\\btb_ring_osc_3stage\\b', args['--testbench'], text)
text = re.sub(r'(?<![A-Za-z0-9_])ring_osc_3stage(?![A-Za-z0-9_])', args['--cell'], text)
(out / 'netlist.scs').write_text(text)
shutil.copy(Path({str(FIXTURE)!r}) / 'core_readback.json', out / 'core_readback.json')
bench = json.loads((Path({str(FIXTURE)!r}) / 'testbench_readback.json').read_text())
for item in bench['instances']:                      # the copied testbench points at the copied cell
    if item.get('cell') == 'ring_osc_3stage':
        item.update(lib=args['--library'], cell=args['--cell'])
(out / 'testbench_readback.json').write_text(json.dumps(bench))
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


MAESTRO_HEAD = ('// Generated for: spectre\nsimulator lang=spectre\nglobal 0\nparameters temperature=27\n'
                'include "/pdk/model.scs" section=tt\n\n')


MAESTRO_TAIL = ('\nsimulatorOptions options psfversion="1.4.0" reltol=1e-3 temp=27\n'
                'tran tran stop=50n errpreset=conservative write="spectre.ic" annotate=status\n'
                'finalTimeOP info what=oppoint where=rawfile\nsaveOptions options save=allpub\n')


def maestro_netlister(tmp_path, circuit=None):
    """Stands in for `bridge_setup maestro_netlist`: Maestro's netlist folder of the copy's test - input.scs = a head, the
    circuit (the recorded export with the copy's names, as the copy reader gives it), a tail - plus name maps in the
    format the real netlister writes (amap/). `circuit` replaces the circuit part (a netlist that differs)."""
    script = tmp_path / 'maestro_netlister.py'
    script.write_text(f'''
import json, re, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{a: argv[i + 1] for i, a in enumerate(argv) if a.startswith('--') and i + 1 < len(argv)}}
with open({str(tmp_path / 'netlister_calls.jsonl')!r}, 'a') as f:
    f.write(json.dumps(dict(op=args['--op'], copy=args['--copy-library'], testbench=args['--testbench'])) + '\\n')
text = {circuit!r} or (Path({str(FIXTURE)!r}) / 'netlist.scs').read_text().replace('// Library name: {LIB}', '// Library name: ' + args['--copy-library'])
text = re.sub(r'\\btb_ring_osc_3stage\\b', args['--testbench'], text)
text = re.sub(r'(?<![A-Za-z0-9_])ring_osc_3stage(?![A-Za-z0-9_])', args['--cell'], text)
folder = Path(args['--output']) / 'maestro_netlist' / 'netlist'
(folder / 'amap').mkdir(parents=True)
(folder / 'netlist').write_text(text)
(folder / 'input.scs').write_text({MAESTRO_HEAD!r} + text + {MAESTRO_TAIL!r})
maps = {{'top_level_map.inst': [('__NEXT_FILE__', args['--testbench'])],
        '__simulator_information__': [('__artInstanceTerminalDelimiter__', ':'), ('__artHierarchyDelimiter__', '.')],
        args['--testbench'] + '.inst': [('V0n', 'analogLib_vdc_spectre'), ('XU1n', args['--cell'])],
        args['--testbench'] + '.net': [('gnd!v', '0v')],
        'analogLib_vdc_spectre.inst': [('PLUSv', ':pv'), ('MINUSv', '(FUNCTION minus(root("PLUS")))v')],
        args['--cell'] + '.inst': [('MN1n MN2n MN3n', 'gpdk045_nmos1v_spectre'), ('OUTv', ':1v')],
        'gpdk045_nmos1v_spectre.inst': [('Dv', ':dv'), ('Gv', ':gv')]}}
for name, pairs in maps.items():
    (folder / 'amap' / name).write_text('HEADER\\n"PSFversion" "1.00"\\n' + ''.join('"%s" "%s"\\n' % (k, v.replace('"', '\\\\"')) for k, v in pairs))
print(json.dumps(dict(test='GATOR', remote='/tmp/gator_maestro_netlist/x', folder=str(folder))))
''')
    return [sys.executable, str(script)]
