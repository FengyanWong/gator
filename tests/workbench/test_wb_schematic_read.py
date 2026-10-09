"""The whole-cell read built once instead of line by line (record 7.296, schematic_read).

Without the bridge - as in this suite - every read is the bridge's own call. The fast path itself runs against the real
bridge package in a child process (the suite's own process must keep the bridge unimportable): its program is the
bridge's with exactly the list changes, and on the same answer from Virtuoso it returns what the bridge's read_schematic
returns, its refusals included."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from gator_workbench import cdf_write, schematic_read

SRC = Path(__file__).resolve().parents[2] / 'src'
BRIDGE_SITE = (Path.home() / 'virtuoso-bridge-lite' / '.venv' / 'lib' / f'python{sys.version_info[0]}.{sys.version_info[1]}'
               / 'site-packages')


class Reader:
    """A client with only the bridge's own read: it records what it was asked."""
    def __init__(self):
        self.calls = []
        self.schematic = SimpleNamespace(read=self.read)

    def read(self, library, cell, **kw):
        self.calls.append((library, cell, kw))
        return dict(instances=[], nets={}, pins={}, notes=[], cell=cell)


def test_without_the_bridges_program_a_read_is_the_bridges_own_call(monkeypatch):
    monkeypatch.setattr(schematic_read, 'program', lambda include_positions: None)
    client = Reader()
    client.execute_skill = lambda *a, **kw: pytest.fail('nothing but the bridge read may run')
    assert schematic_read.read_cell(client, 'LIB', 'core') == dict(instances=[], nets={}, pins={}, notes=[], cell='core')
    schematic_read.read_cell(client, 'LIB', 'tb', include_positions=False)
    assert client.calls == [('LIB', 'core', dict(include_positions=True, param_filters=None)),
                            ('LIB', 'tb', dict(include_positions=False, param_filters=None))]


def test_a_client_that_cannot_run_skill_reads_with_the_bridges_own_call(monkeypatch):
    monkeypatch.setattr(schematic_read, 'program', lambda include_positions: 'let((cv result out) ...)')
    client = Reader()
    schematic_read.read_cell(client, 'LIB', 'core')
    assert client.calls == [('LIB', 'core', dict(include_positions=True, param_filters=None))]


def test_the_run_adapter_reads_its_core_cell_through_it(monkeypatch):
    asked = []
    monkeypatch.setattr(cdf_write, 'read_cell', lambda client, library, cell: asked.append((client, library, cell)) or 'snapshot')
    backend = SimpleNamespace(client='client', config=SimpleNamespace(library='MScR'),
                              circuit=SimpleNamespace(design=dict(core_cell='mscr_vco_lin_c')))
    assert cdf_write.CdfBridgeBackend._read_snapshot(backend) == 'snapshot'
    assert asked == [('client', 'MScR', 'mscr_vco_lin_c')]


# An answer as Virtuoso prints the read program's string: instances with positions, a shift+deleted one, terminals,
# parameters (one with a quoted string), nets, pins and a note. The same text answers both programs.
ANSWER = '\n'.join([
    'INSTANCES',
    'INST|MN1|gpdk045|nmos1v|(0.0 0.5)|R0|((-0.3 0.1) (0.3 0.9))|1|symbol',
    'TERM|D|out', 'TERM|G|in', 'TERM|S|gnd!',
    'PARAM|w|"1.2u"', 'PARAM|l|"45n"', 'PARAM|fingers|"2"', 'PARAM|model|"gpdk045_nmos1v"',
    'INST|R1|analogLib|res|(1.0 0.5)|R90|((0.8 0.2) (1.2 0.8))|1|symbol',
    'NLACTION|ignore',
    'TERM|PLUS|out', 'TERM|MINUS|vdd!',
    'PARAM|r|"10k"',
    'NETS',
    'NET|out|1|signal|nil|MN1.D|R1.PLUS',
    'NET|vdd!|1|supply|t|R1.MINUS',
    'PINS',
    'PIN|in|input|1|in|1',
    'NOTES',
    'NOTE|bias "A"|(0.5 1.5)|stick|0.0625|R0|lowerCenter',
    'END', ''])

CHILD = r'''
import json, site, sys
from types import SimpleNamespace
site.addsitedir(sys.argv[1])
sys.path.insert(0, sys.argv[2])
from gator_workbench import schematic_read
from virtuoso_bridge.virtuoso.schematic import reader
ANSWER = json.loads(sys.argv[3])

class Client:
    def __init__(self, output=None, errors=None):
        self.output, self.errors, self.sent = output, errors or [], []
        self.schematic = SimpleNamespace(read=lambda *a, **kw: ('bridge read', a, kw))
    def execute_skill(self, skill, timeout=None):
        self.sent.append((skill, timeout))
        return SimpleNamespace(ok=not self.errors, errors=self.errors, output=self.output)

def printed(text):                            # a SKILL string as Virtuoso prints it
    return '"' + text.replace('"', '\\"').replace('\n', '\\n') + '"'

def outcome(call):
    try:
        return ('answer', call())
    except Exception as exc:
        return (type(exc).__name__, str(exc))

found = {}
for positions in (True, False):
    ours = schematic_read.program(positions)
    theirs = reader._SKILL_TOPOLOGY.replace('{geometry_inst}', reader._GEOMETRY_INST_EXPR if positions else '') \
        .replace('{notes_section}', reader._NOTES_SECTION_EXPR)
    back = ours.replace('let((cv result out)', 'let((cv result)').replace(r'out = tconc(nil "INSTANCES\n")', r'result = "INSTANCES\n"') \
        .replace('buildString(car(out) "")', 'result').replace('tconc(out ', 'result = strcat(result ')
    found[f'program {positions}'] = dict(same_but_the_list=back == theirs, appends=theirs.count('result = strcat(result '),
                                         strcat_left=ours.count('strcat('), tconc=ours.count('tconc('))
    answer = ANSWER if positions else '\n'.join(l.split('|')[0] + '|' + '|'.join(l.split('|')[1:4]) if l.startswith('INST|') else l
                                                for l in ANSWER.split('\n'))
    cases = dict(answer=dict(output=printed(answer)), errors=dict(output=None, errors=['*Error* eval: undefined function']),
                 error=dict(output=printed('ERROR')), empty=dict(output='""'))
    for case, kw in cases.items():
        a, b = Client(**kw), Client(**kw)
        mine = outcome(lambda: schematic_read.read_cell(a, 'MScR', 'cell_a', include_positions=positions))
        bridge = outcome(lambda: reader.read_schematic(b, 'MScR', 'cell_a', include_positions=positions, param_filters=None))
        found[f'{case} {positions}'] = dict(
            same=mine == bridge, mine=mine[0], instances=len(mine[1]['instances']) if mine[0] == 'answer' else mine[1],
            sent_ours=a.sent == [(reader._build_cellview_read_skill(ours, 'MScR', 'cell_a'), 300)],
            sent_bridge_timeout=b.sent[0][1], one_call_each=(len(a.sent), len(b.sent)) == (1, 1))

# A bridge whose program is not the one measured: its own read, unchanged.
schematic_read.program.cache_clear()
reader._SKILL_TOPOLOGY = reader._SKILL_TOPOLOGY.replace('result = "INSTANCES\\n"', 'result = strcat("INSTANCES" "\\n")')
client = Client(output=printed(ANSWER))
found['other bridge'] = dict(program=schematic_read.program(True), answer=schematic_read.read_cell(client, 'MScR', 'cell_a'),
                             sent=len(client.sent))
print(json.dumps(found, default=str))
'''


@pytest.mark.skipif(not BRIDGE_SITE.is_dir(), reason='the bridge checkout is not on this machine')
def test_with_the_bridge_the_answer_is_the_bridges_on_the_same_text_its_refusals_included():
    run = subprocess.run([sys.executable, '-c', CHILD, str(BRIDGE_SITE), str(SRC), json.dumps(ANSWER)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    found = json.loads(run.stdout.strip().splitlines()[-1])
    for positions in ('True', 'False'):
        program = found[f'program {positions}']
        assert program == dict(same_but_the_list=True, appends=program['appends'], strcat_left=0, tconc=program['appends'] + 1)
        assert program['appends'] >= 10
        for case in ('answer', 'errors', 'error', 'empty'):
            got = found[f'{case} {positions}']
            assert got['same'] and got['sent_ours'] and got['one_call_each'] and got['sent_bridge_timeout'] == 300, (case, got)
        assert found[f'answer {positions}']['mine'] == 'answer' and found[f'answer {positions}']['instances'] == 2
        assert found[f'errors {positions}']['mine'] == 'RuntimeError'
    assert found['other bridge'] == dict(program=None, sent=0, answer=['bridge read', ['MScR', 'cell_a'],
                                                                       dict(include_positions=True, param_filters=None)])
