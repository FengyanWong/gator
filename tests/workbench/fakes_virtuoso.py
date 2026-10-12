"""Fake Virtuoso-side programs and cells that several test modules share: the setup writer, the working-copy writer and its cells, an exported cell's reader, the Maestro netlister and the copy reader (refactoring package D1)."""

import json
import sys
from pathlib import Path
from copy import deepcopy
import math
import re
from types import SimpleNamespace

from gator_workbench import bridge_read, cdf_write
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend

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


def maestro_netlister(tmp_path, circuit=None, *, head=MAESTRO_HEAD):
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
(folder / 'input.scs').write_text({head!r} + text + {MAESTRO_TAIL!r})
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


# ------------------------------------------------------------------------------------------ the fake Virtuoso
MOS_NETLIST = dict(w='w', l='l', nf='fingers', m='m', **{k: k for k in ('as', 'ad', 'ps', 'pd', 'nrd', 'nrs')})


CAP_NETLIST = dict(w='w', l='l', m='m')


SET = re.compile(r'cdfgData~>(\w+)~>value = ("(?:[^"\\]|\\.)*"|[^\s)]+)')


CALL = re.compile(r'unless\(errsetstring\("((?:[^"\\]|\\.)*)"\) error')


BLOCK = re.compile(r'x~>name == "([^"]+)"')


HOLDS = re.compile(r'funcall\(same cdfParseFloatString\(or\(cdfgData~>(\w+)~>value ""\)\) ([-\d.e+]+)\)'
                   r'|funcall\(same cdfgData~>(\w+)~>value ([-\d.e+]+)\)'
                   r'|equal\(cdfgData~>(\w+)~>value "([^"]*)"\)'
                   r'|equal\(cdfgData~>(\w+)~>value (\d+)\)')


FINAL = re.compile(r'unless\((.+?) error\("%s" "((?:[^"\\]|\\.)*)"\)\)$')


ROUNDS = re.compile(r'rounds < (\d+)')


PROC = re.compile(r'funcall\(stringToSymbol\("(\w+)"\) (cdfgData|inst)\)')


def holds_of(text):
    """(field, wanted, numeric) of a generated "does the instance hold this value" test."""
    m = HOLDS.search(text)
    if not m:
        return None
    groups = [g for g in m.groups() if g is not None]
    field, wanted = groups[0], groups[1]
    return field, wanted, m.group(5) is None


def num(text):
    from analog_optimizer.backends.gpdk045 import number
    return number(text)


def wpe(length):
    """Stand-in for a GPDK045 well-proximity value (sca): its width callback computes it from the current length."""
    return format(3.25e-6 / length, '.7g')


class FakeVirtuoso:
    """Runs the writer's SKILL as the form would: the fields it sets, then the callbacks. Test model only."""

    def __init__(self, reference, netlist, *, clamp=5.6e-6, fold_above=None, keep_capacitance=False, proximity=False):
        self.state, self.netlist, self.clamp, self.fold_above = deepcopy(reference), netlist, clamp, fold_above
        self.proximity = proximity                                           # model the well-proximity value (sca)
        self.keep_capacitance = keep_capacitance
        self.skill, self.saves, self.opened, self.form_calls, self.rounds = [], 0, [], [], {}
        self.schematic = SimpleNamespace(read=lambda *a, **kw: deepcopy(self.state), export_netlist=self.export)

    def list_windows(self):
        return []

    def close(self):
        pass

    def params(self, name):
        return next(i for i in self.state['instances'] if i['name'] == name)['params']

    def callback(self, name, text):
        p, field = self.params(name), re.search(r"'\s*(\w+)", text).group(1)
        if text.startswith('gpdk045_mosCB'):
            w, fingers = num(p['w']), num(p['fingers'])
            if field == 'w' and self.fold_above and w > self.fold_above:
                fingers = math.ceil(w / self.fold_above)                     # the form folds a wide transistor
                p['fingers'] = str(fingers)
            if field == 'fw':
                w = num(p['fw']) * fingers
                p['w'] = format(w, '.12g')
            p['fw'] = format(w / fingers, '.12g')
            for key in ('ad', 'as'):
                p[key] = format(w * 1.4e-7, '.12g')
            for key in ('pd', 'ps'):
                p[key] = format(2 * w + 2.8e-7, '.12g')
            for key in ('nrd', 'nrs'):
                p[key] = format(1.4e-7 / w, '.12g')
            if field == 'w' and self.proximity:                              # from the length it has NOW (GPDK045's does)
                p['sca'] = wpe(num(p['l']))
        elif text.startswith('gpdk045_capCB'):
            if field == 'm' and self.keep_capacitance:                       # a form that keeps the total capacitance
                p['w'] = format(num(p['w']) * 0.5, '.12g')                   # moves a value written before it
            else:
                p[field] = format(min(self.clamp, max(1e-6, num(p[field]))), '.12g')
            w, l = num(p['w']), num(p['l'])
            p['c'] = format(1.025e-3 * w * l + 2.425e-10 * 2 * (w + l), '.6g')       # area + fringe, 6 digits
            p['pasUpdateParamList'] = f'{field} c'                           # bookkeeping the form rewrites

    def holds(self, name, test):
        field, wanted, numeric = test
        have = self.params(name).get(field)
        return (have is not None and num(have) is not None and math.isclose(num(have), float(wanted), rel_tol=1e-9, abs_tol=1e-30)
                if numeric else have == wanted)

    def blocks(self, skill):
        """The generated SKILL as the writer means it: per instance its form procedures, the ordered (test, field, value,
        callback) of the round, the round limit and the final checks. Nothing is assumed: what is not in the text does not
        happen here either."""
        out, current = [], None
        for line in skill.splitlines():
            block = BLOCK.search(line)
            if block:
                current = dict(instance=block.group(1), init=None, done=None, rounds=0, targets=[], final=[], pending=[])
                out.append(current)
            if current is None:
                continue
            for name, argument in PROC.findall(line):
                current['init' if argument == 'cdfgData' else 'done'] = name
            if 'when(or(' in line:
                current['pending'] = [t for t in (holds_of(part) for part in line.split(' !')) if t]
            found = ROUNDS.search(line)
            if found:
                current['rounds'] = int(found.group(1))
            if 'lengthTyped = t' in line:
                current['retype'] = True                                     # the width is typed again after a length
            if line.strip().startswith('unless(') and holds_of(line) and 'error(' not in line:
                current['test'] = holds_of(line)                             # the round's "unless it already holds"
            setter = SET.search(line)
            if setter and current.get('test'):
                value = setter.group(2)
                current['targets'].append(dict(test=current.pop('test'), field=setter.group(1),
                                               value=json.loads(value) if value.startswith('"') else value, callback=None))
            called = CALL.search(line)
            if called and current['targets']:
                current['targets'][-1]['callback'] = json.loads(f'"{called.group(1)}"')
            end = FINAL.search(line.strip())
            if end and holds_of(end.group(1)) and 'value = ' not in line:
                current['final'].append((holds_of(end.group(1)), end.group(2)))
        return out

    def execute_skill(self, skill, timeout=60):
        """Run it as Virtuoso would: an instance whose values all hold is not touched, the round repeats while something
        was written (at most the generated limit), and a generated final check that fails is the answer."""
        self.skill.append(skill)
        changed = False
        for block in self.blocks(skill):
            name = block['instance']
            if block['pending'] and all(self.holds(name, test) for test in block['pending']):
                continue                                                     # untouched: no form procedure, no callback
            self.opened.append(name)
            if block['init']:
                self.form_calls.append((name, block['init']))
            for round_number in range(block['rounds']):
                self.rounds[name] = round_number + 1
                wrote, length_typed = False, False
                for target in block['targets']:
                    again = block.get('retype') and target['field'] == 'w' and length_typed
                    if self.holds(name, target['test']) and not again:
                        continue
                    self.params(name)[target['field']] = target['value']
                    if target['callback']:
                        self.callback(name, target['callback'])
                    length_typed = target['field'] == 'l' or (length_typed and target['field'] != 'w')
                    wrote = True
                if not wrote:
                    break
            for test, message in block['final']:
                if not self.holds(name, test):
                    return SimpleNamespace(ok=False, output=None, errors=[message])
            if block['done']:
                self.form_calls.append((name, block['done']))
            changed = True
        if changed:
            self.saves += 1
        return SimpleNamespace(ok=True, output='t', errors=[])

    def export(self, lib, cell, output, timeout):
        """The fixture's netlist with the values of the cell as it is now."""
        output.mkdir()
        text = self.netlist.replace('\\\n', ' ')
        for inst in self.state['instances']:
            names = MOS_NETLIST if inst['cell'] in ('nmos1v', 'pmos1v') else CAP_NETLIST
            def put(match):
                key = match.group(1)
                return f'{key}={inst["params"][names[key]]}' if key in names and names[key] in inst['params'] else match.group(0)
            text = re.sub(rf'(?m)^(\s*{inst["name"]} \(.*)$',
                          lambda line: re.sub(r'\b(\w+)=\(?([^\s()]+)\)?', put, line.group(1)), text)
        (output / 'netlist').write_text(text)
        return {'input_file': str(output / 'input.scs')}


def backend_of(tmp_path, monkeypatch, profile, directory, **fake):
    client = FakeVirtuoso(profile.reference, (directory / 'structure.scs').read_text(), **fake)

    def attach(self):
        self.bridge_version = 'offline-fault-injection'
        return client
    monkeypatch.setattr(VirtuosoBridgeBackend, '_attach', attach)
    env = tmp_path / 'bridge.env'
    env.write_text('# offline test configuration\n')
    config = BridgeConfig(env, 'GPDK045_RINGOSC', directory / 'creation.json', tmp_path / 'state', '/models/gpdk045.scs')
    return cdf_write.backend_class(profile)(config, profile), client
