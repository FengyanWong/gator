"""ngspice netlist tasks (2026-09-23, user request): the SPICE reader and deck writer (ngspice_netlist), the task store
and its starter rows (ngspice_tasks), the evaluation backend (ngspice_backend), the routes and the run preparation.

Fake runners and a fake probe process everywhere, except the tests marked REAL: they run the ngspice installed on this
machine on the example deck (skipped when there is none). No Virtuoso, no network, no agent CLI."""
from pathlib import Path
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus
from gator_workbench import ngspice_backend, ngspice_netlist as ng, ngspice_tasks, ngspice_tasks as nt, runs, schema, tasks
from gator_workbench.connection import NGSPICE_LAYERS
from gator_workbench.ngspice_backend import NgspiceBackend, NgspiceLink
from gator_workbench.storage import DatasetReader, read_json
from helpers import roots_for, workbench_app
from fakes_connection import EXAMPLE, NGSPICE, REPO, ngspice_probe, write_profiles


DECK = '''* a divider with a sized load in a subcircuit used once
.param rl=2k
v1 in 0 dc 1
r1 in out 1k
x1 out 0 load
.subckt load a b
r2 a b {rl}
c1 a b 1p
.ends
.op
.control
op
let vout_v = v(out)
print vout_v
.endc
.end
'''
GAIN_OUTPUT = '''Doing analysis at TEMP = 27.000000 and TNOM = 27.000000
No. of Data Rows : 181
gain_db             =  4.64864e+01 at=  1.00000e+00
ugf_hz              =  2.86474e+07
vout_v = 1.178058e+00
ngspice-47 done
'''


def circuit(task_key):
    """Refer to a saved ngspice task through its registered task key."""
    return schema.CircuitReference(source='registered_task', task_id=task_key)


# ------------------------------------------------------------------------------- the reader
def test_the_reader_builds_the_graph_the_optimizer_expects():
    parsed = ng.parse_text(DECK, source='deck.cir', circuit_id='divider')
    graph = parsed.graph
    graph.validate()                                                  # complete, every terminal connected
    assert [(d.id, d.kind) for d in graph.devices] == [('v1', 'vsource'), ('r1', 'resistor'), ('x1/r2', 'resistor'), ('x1/c1', 'capacitor')]
    assert {n.id: n.roles for n in graph.nets} == {'in': ('normal',), '0': ('ground',), 'out': ('normal',)}
    assert graph.parameters['x1/r2']['r'].value == 2000.0 and graph.parameters['x1/r2']['r'].raw == '{rl}'
    assert graph.parameters['r1']['r'].value == 1000.0 and graph.parameters['v1']['dc'].value == 1.0
    assert set(parsed.sizables) == {('v1', 'dc'), ('r1', 'r'), ('x1/r2', 'r'), ('x1/c1', 'c')}   # the subcircuit is used once
    assert [(m.name, m.analysis, m.unit) for m in parsed.measurements] == [('vout_v', 'dc', 'V')]
    assert parsed.has_control and parsed.has_end and parsed.subckt_uses == {'load': 1}
    assert [c.role for c in graph.connections if c.device_id == 'x1/r2'] == ['positive', 'negative']
    assert graph.metadata['simulator'] == 'ngspice' and graph.metadata['analysis_context'][0]['text'] == '.op'


def test_a_node_written_in_two_spellings_is_one_net():
    """Record 7.322: ngspice reads node names without regard to case, so `IN` and `in` are one wire. The reader made
    a net of each spelling - the same divider in mixed capitals had five nets instead of three, and its resistors no
    longer met. One net per name now, under the spelling the deck gives first; a deck of one spelling reads as before."""
    lower = 'divider\nv1 in 0 dc 1\nr1 in mid 1k\nr2 mid 0 1k\n.op\n.end\n'
    mixed = 'divider\nV1 IN 0 dc 1\nr1 in MID 1k\nR2 mid 0 1k\n.op\n.end\n'
    one, two = ng.parse_text(lower).graph, ng.parse_text(mixed).graph
    one.validate(), two.validate()
    assert [n.id for n in one.nets] == ['in', '0', 'mid'] and [n.id for n in two.nets] == ['IN', '0', 'MID']
    wiring = lambda graph: [(c.device_id.lower(), c.net_id.lower(), c.ordinal) for c in graph.connections]      # noqa: E731
    assert wiring(one) == wiring(two)                                    # the same circuit
    # inside a subcircuit, through its ports and for a global node too
    nested = ('nested\n.subckt half a B\nr1 a x 1k\nr2 X B 1k\n.ends\n.global VDD\nx1 IN out half\nX2 OUT 0 HALF\n'
              'v1 in 0 dc 1\nv2 vdd 0 dc 1\nr9 Vdd in 1\n.op\n.end\n')
    graph = ng.parse_text(nested).graph
    graph.validate()
    assert sorted(n.id for n in graph.nets) == ['0', 'IN', 'X2/x', 'out', 'vdd', 'x1/x']
    assert {c.net_id for c in graph.connections if c.device_id in ('x1/r1', 'x1/r2')} == {'IN', 'x1/x', 'out'}


def test_a_subcircuit_used_twice_is_shown_but_not_sized():
    twice = DECK.replace('x1 out 0 load\n', 'x1 out 0 load\nx2 out 0 load\n')
    parsed = ng.parse_text(twice)
    assert [d.id for d in parsed.graph.devices] == ['v1', 'r1', 'x1/r2', 'x1/c1', 'x2/r2', 'x2/c1']
    assert set(parsed.sizables) == {('v1', 'dc'), ('r1', 'r')} and parsed.subckt_uses == {'load': 2}
    with pytest.raises(ng.NetlistError, match='not a sizable value'):
        ng.rewrite(parsed, {('x1/r2', 'r'): 3000.0})


def test_numbers_expressions_continuations_and_comments():
    assert ng.number('1Meg') == 1e6 and ng.number('1M') == 1e-3 and ng.number('10uF') == pytest.approx(10e-6) and ng.number('1kohm') == 1e3
    assert ng.number('2.5e-6') == 2.5e-6 and ng.number('abc') is None and ng.number('{x}') is None
    assert ng.evaluate('{2*wn}', {'wn': 3e-6}.__getitem__) == 6e-6 and ng.evaluate("'sqrt(4)*1u'", lambda n: 0) == 2e-6
    with pytest.raises(ng.Unresolved):
        ng.evaluate('{__import__("os")}', lambda n: 0)
    deck = ('* continuation lines and comments\n'
            'm1 d g 0 0 nch W = 2u $ a comment\n'
            '+ L=0.18u ; another\n'
            '.model nch nmos level=1\n'
            'v1 d 0 dc 1.8\nvg g 0 dc 0.9\n.op\n.end\n')
    parsed = ng.parse_text(deck)
    values = parsed.graph.parameters['m1']
    assert values['w'].value == 2e-6 and values['l'].value == 0.18e-6 and parsed.graph.devices[0].kind == 'nmos'
    assert parsed.sizables[('m1', 'l')].token.line == 3 and parsed.sizables[('m1', 'w')].source_name == 'w'


def test_model_kinds_come_from_the_deck_the_included_files_and_the_user(tmp_path):
    (tmp_path / 'models.lib').write_text('* models\n.model nch.1 nmos level=54\n.model pch pmos level=1\n.subckt pdkcell d g s b\n.ends\n')
    deck = ('* pdk-like deck\n.include models.lib\nvdd vdd 0 dc 1.8\n'
            'm1 out in 0 0 nch W=1u L=0.1u\nm2 out in vdd vdd pch W=2u L=0.1u\n'
            'x1 out in 0 0 pdkcell W=1u\nx2 out in 0 mystery W=1u\nq1 out in 0 npn1\n.model npn1 npn\n.op\n.end\n')
    parsed = ng.parse_text(deck, include_root=str(tmp_path))
    kinds = {d.id: d.kind for d in parsed.graph.devices}
    assert kinds == {'vdd': 'vsource', 'm1': 'nmos', 'm2': 'pmos', 'x1': 'unknown', 'x2': 'unknown', 'q1': 'unknown'}
    assert parsed.model_types['nch'] == 'nmos' and parsed.unknown_models == ['pdkcell', 'mystery', 'npn1']   # a bipolar has no kind the network knows
    assert parsed.graph.complete                                      # unknown is a warning: ngspice simulates it anyway
    assert {d.code for d in parsed.graph.diagnostics} == {'unknown_device'}
    assert ('x1', 'w') not in parsed.sizables                         # an unknown device is never sized
    declared = ng.parse_text(deck, include_root=str(tmp_path), device_kinds={'pdkcell': 'nmos'})
    x1 = next(d for d in declared.graph.devices if d.id == 'x1')
    assert x1.kind == 'nmos' and x1.terminals == ('d', 'g', 's', 'b') and ('x1', 'w') in declared.sizables
    assert declared.unknown_models == ['mystery', 'npn1']
    with pytest.raises(ng.NetlistError, match='not one of'):
        ng.parse_text(deck, device_kinds={'pdkcell': 'bjt'})
    # without the folder, the include cannot be scanned: said as a warning, and the MOS kinds stay unknown
    blind = ng.parse_text(deck)
    assert any(d.code == 'include_not_scanned' for d in blind.graph.diagnostics)
    assert {d.id: d.kind for d in blind.graph.devices}['m1'] == 'unknown'


def test_the_writer_replaces_only_the_value_tokens_and_the_deck_reads_back(tmp_path):
    parsed = ng.parse_text(DECK, include_root=str(tmp_path))
    text, written = ng.rewrite(parsed, {('r1', 'r'): 1500.0, ('x1/r2', 'r'): 2500.0})
    before, after = DECK.split('\n'), text.split('\n')
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert changed == [('r1 in out 1k', 'r1 in out 1500'), ('r2 a b {rl}', 'r2 a b 2500')] and len(before) == len(after)
    again = ng.parse_text(text)
    assert again.graph.parameters['r1']['r'].value == 1500.0 and again.graph.parameters['x1/r2']['r'].value == 2500.0
    # the same by the deck's own spelling of the value (the optimizer's assignment keys)
    same, _ = ng.rewrite(parsed, {('r1', 'r'): 1500.0})
    assert same.split('\n')[3] == 'r1 in out 1500'
    # relative includes made absolute for a local run; a deck without .end gets one
    deck = '* inc\n.include models.lib\n.lib "sky.lib" tt\nr1 a 0 1k\n.op\n'
    resolved, _ = ng.deck_text(ng.parse_text(deck, include_root=str(tmp_path)), {}, include_root=str(tmp_path), absolute_includes=True)
    assert f'.include "{tmp_path / "models.lib"}"' in resolved and f'.lib "{tmp_path / "sky.lib"}" tt' in resolved and resolved.endswith('.end\n')


def test_results_are_read_from_the_batch_output_and_failures_are_classified():
    assert ng.read_results(GAIN_OUTPUT, ['gain_db', 'ugf_hz', 'vout_v', 'missing']) == {'gain_db': 46.4864, 'ugf_hz': 28647400.0, 'vout_v': 1.178058}
    assert ng.read_results('x = nan\ny = inf\nz = 1.5\nTEMP = 27\n', ['x', 'y', 'z', 'temp']) == {'z': 1.5, 'temp': 27.0}
    assert ng.read_results('Gain_DB = 3\n', ['gain_db']) == {'gain_db': 3.0}          # ngspice prints names in lowercase
    assert ng.classify_failure('Error: timestep too small at t=1e-9\n', '', 1) == ('nonconverged', 'Error: timestep too small at t=1e-9')
    assert ng.classify_failure('', 'Error: Could not find include file models.lib\n', 1)[0] == 'deck_error'
    status, evidence = ng.classify_failure(' meas ac ugf when(WHEN) : out of interval\n .meas ac ugf when vdb(out)=0 failed!\n', '', 0)
    assert status == 'measurement_error' and 'out of interval' in evidence
    assert ng.classify_failure(GAIN_OUTPUT, '', 0) == (None, '')
    assert ng.classify_failure('', 'boom', 3) == ('deck_error', 'boom')


def test_the_example_deck_reads_as_documented():
    parsed = ng.parse_file(EXAMPLE)
    assert [(m.name, m.unit) for m in parsed.measurements] == [('vout_v', 'V'), ('supply_power_w', 'W'), ('gain_db', 'dB'), ('ugf_hz', 'Hz'),
                                                                ('phase_at_ugf_deg', 'deg'), ('phase_margin_deg', 'deg')]
    assert len(parsed.sizables) == 17 and parsed.subckt_uses == {'ota5': 1} and nt._problems(parsed) == []
    assert {d.kind for d in parsed.graph.devices} == {'vsource', 'isource', 'nmos', 'pmos', 'capacitor'}
    assert ngspice_backend.deck_condition(EXAMPLE.read_text()).corner.supply_v == 1.8


# ------------------------------------------------------------------------------- the backend
class FakeRunner:
    """Answers with canned output; records every deck it was given."""
    def __init__(self, answers):
        self.answers, self.decks = list(answers), []

    def local(self, program, deck, timeout):
        """Record the deck and return or raise the next scripted ngspice answer."""
        self.decks.append(deck.read_text())
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def remote(self, host, program, deck_text, timeout):
        """Record the remote deck and use the same scripted answers as local execution."""
        self.decks.append(deck_text)
        return self.local(program, type('D', (), dict(read_text=lambda self: deck_text))(), timeout)


def sized_graph(text, groups):
    """The task's graph with `groups` = {device_id: (parameter, lower, upper)} as mutable groups, as compile would build."""
    from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
    parsed = ng.parse_text(text)
    graph = parsed.graph
    for device, (parameter, lower, upper) in groups.items():
        value = graph.parameters[device][parameter]
        kind = {'r': 'r', 'c': 'c', 'w': 'w', 'l': 'l', 'dc': 'dc'}[parameter]
        unit = {'r': 'ohm', 'c': 'F', 'w': 'm', 'l': 'm', 'dc': 'V'}[parameter]
        graph.parameter_groups.append(ParameterGroup(f'{device}_{parameter}', kind, unit, value.value, lower, upper,
                                                     (ParameterBinding(device, parameter),)))
    graph.validate()
    return graph


def test_the_backend_holds_its_parameters_and_refuses_in_its_own_words(tmp_path):
    """Record 7.292 (plan-refactoring E8): connect, close and the held parameters come from the package's HeldParameters;
    the messages stay the ngspice backend's own (this test passes on the code before that step too)."""
    graph = sized_graph(DECK, {'r1': ('r', 500.0, 4000.0)})
    backend = NgspiceBackend(DECK, graph, NgspiceLink('ngspice_local'), units={'vout_v': 'V'}, runner=FakeRunner([]))
    assert backend.connected is False
    for call in (backend.restore, backend.read_parameters, lambda: backend.set_parameters({}),
                 lambda: backend.generate_netlist(tmp_path)):
        with pytest.raises(ngspice_backend.BackendNotConnected, match=r'^ngspice backend is not connected$'):
            call()
    backend.connect()
    assert backend.read_parameters() == {('r1', 'r'): 1000.0}
    backend.set_parameters({('r1', 'r'): 1500.0})
    for bad in ({}, {('r1', 'r'): 1500.0, ('r2', 'r'): 1.0}, {('r1', 'r'): float('nan')}):
        with pytest.raises(ValueError, match=r'^Unexpected ngspice parameter assignment$'):
            backend.set_parameters(bad)
    assert backend.read_parameters() == {('r1', 'r'): 1500.0}
    backend.restore()
    assert backend.read_parameters() == {('r1', 'r'): 1000.0}
    backend.close()
    assert backend.connected is False


def test_the_backend_writes_the_deck_reads_it_back_and_reports_each_outcome(tmp_path):
    ok = (0, 'vout_v = 6.000000e-01\nngspice-47 done\n', '')
    runner = FakeRunner([ok, (0, 'vout_v: no data\n .meas failed!\n', ''), (1, 'Error: timestep too small\n', ''),
                         (1, '', 'Error: Could not find include file x.lib\n'), subprocess.TimeoutExpired('ngspice', 5), FileNotFoundError('no ngspice')])
    graph = sized_graph(DECK, {'r1': ('r', 500.0, 4000.0)})
    backend = NgspiceBackend(DECK, graph, NgspiceLink('ngspice_local'), units={'vout_v': 'V'}, runner=runner)
    with pytest.raises(ngspice_backend.BackendNotConnected):
        backend.read_parameters()                                     # not connected yet
    backend.connect()
    assert backend.read_parameters() == {('r1', 'r'): 1000.0} and backend.nominal_condition().corner.supply_v == 1.0
    backend.set_parameters({('r1', 'r'): 1500.0})
    artifact = backend.generate_netlist(tmp_path / 'exports')
    assert artifact.origin == 'real' and 'r1 in out 1500' in artifact.path.read_text()
    graph_again = backend.get_circuit_graph(artifact)
    assert graph_again.parameters['r1']['r'].value == 1500.0 and graph_again.parameter_groups[0].value == 1500.0
    request = SimulationRequest(artifact, tmp_path / 'sims', ('vout_v',), 5.0, {('r1', 'r'): 1500.0}, condition=backend.condition)
    result = backend.run_simulation(request)
    assert result.status == SimulationStatus.OK and result.metrics == {'vout_v': 0.6} and result.metric_units == {'vout_v': 'V'}
    assert result.metric_validity == {'vout_v': True} and result.origin == 'real' and result.simulator_version == 'ngspice-47'
    assert result.simulator_invocations == 1 and (result.artifact_directory / 'ngspice.log').is_file()
    assert 'r1 in out 1500' in runner.decks[0]
    missing = backend.run_simulation(request)
    assert missing.status == SimulationStatus.MEASUREMENT_ERROR and missing.metrics == {'vout_v': None} and missing.candidate_evaluated
    failed = backend.run_simulation(request)
    assert failed.status == SimulationStatus.NONCONVERGED and failed.candidate_evaluated and 'timestep' in failed.error_summary
    broken = backend.run_simulation(request)
    assert broken.status == SimulationStatus.BACKEND_ERROR and not broken.candidate_evaluated and 'include' in broken.error_summary
    late = backend.run_simulation(request)
    assert late.status == SimulationStatus.TIMEOUT and late.retryable and not late.candidate_evaluated
    gone = backend.run_simulation(request)
    assert gone.status == SimulationStatus.TRANSPORT_ERROR and gone.reason_code == 'program_not_found' and gone.simulator_invocations == 0
    backend.restore()
    assert backend.read_parameters() == {('r1', 'r'): 1000.0}
    with pytest.raises(ValueError):
        backend.set_parameters({('r1', 'r'): 1.0, ('x1/c1', 'c'): 1e-12})
    backend.close()


def test_the_link_validates_the_connection_settings_and_the_remote_command_is_fixed():
    assert NgspiceLink.from_settings(dict(kind='ngspice_local')).max_concurrency >= 1
    far = NgspiceLink.from_settings(dict(kind='ngspice_ssh', ssh_host='simhost', ngspice_bin='/opt/ngspice/bin/ngspice'))
    assert far.remote and far.max_concurrency == ngspice_backend.SSH_CONCURRENCY and far.label == 'ngspice over SSH'
    assert ngspice_backend.remote_run_command(far.program).startswith('d=$(mktemp -d) && cat > "$d/deck.cir"')
    for bad in (dict(kind='virtuoso_ssh'), dict(kind='ngspice_ssh'), dict(kind='ngspice_ssh', ssh_host='-oProxyCommand=x'),
                dict(kind='ngspice_local', ngspice_bin='ngspice; rm -rf /')):
        with pytest.raises(ngspice_backend.NgspiceLinkError):
            NgspiceLink.from_settings(bad)
    runner = FakeRunner([(255, '', 'ssh: connect to host simhost port 22: Connection refused\n')])
    graph = sized_graph(DECK, {'r1': ('r', 500.0, 4000.0)})
    backend = NgspiceBackend(DECK, graph, far, runner=runner)
    backend.connect()
    artifact = backend.generate_netlist(Path(tempfile.mkdtemp(prefix='gator-ngspice-link-')))
    result = backend.run_simulation(SimulationRequest(artifact, artifact.path.parent, ('vout_v',), 5.0, backend.read_parameters(), condition=backend.condition))
    assert result.status == SimulationStatus.TRANSPORT_ERROR and result.reason_code == 'ssh_failed'
    assert 'simhost' not in result.error_summary and '<ssh host>' in result.error_summary   # the destination never leaves


@pytest.mark.parametrize('outcome', ['ok', 'nonconverged', 'timeout'])
def test_each_local_attempt_keeps_its_own_deck_and_raw_output(tmp_path, outcome):
    class RawRunner:
        """A local ngspice stand-in that leaves distinct raw output for each attempt."""
        def __init__(self):
            self.calls = 0

        def local(self, program, deck, timeout):
            """Write attempt-specific raw output and return the configured success, failure or timeout."""
            self.calls += 1
            (deck.parent / 'results.raw').write_text(f'fake raw output {self.calls}')
            if outcome == 'timeout':
                raise subprocess.TimeoutExpired(program, timeout)
            return (0, 'vout_v = 0.6\n', '') if outcome == 'ok' else (1, 'Error: timestep too small\n', '')

    deck = DECK.replace('print vout_v', 'print vout_v\nwrite results.raw all')
    backend = NgspiceBackend(deck, sized_graph(deck, {'r1': ('r', 500.0, 4000.0)}), NgspiceLink('ngspice_local'),
                             units={'vout_v': 'V'}, runner=RawRunner())
    backend.connect()
    try:
        artifact = backend.generate_netlist(tmp_path / 'exports')
        request = SimulationRequest(artifact, tmp_path / 'sims', ('vout_v',), 5.0, backend.read_parameters(),
                                    condition=backend.condition)
        first, second = backend.run_simulation(request), backend.run_simulation(request)
        assert first.status.value == second.status.value == outcome
        assert first.artifact_directory != second.artifact_directory
        for number, result in enumerate((first, second), start=1):
            assert (result.artifact_directory / 'results.raw').read_text() == f'fake raw output {number}'
            assert (result.artifact_directory / 'deck.cir').read_bytes() == artifact.path.read_bytes()
        assert not (artifact.path.parent / 'results.raw').exists()
        backend.get_circuit_graph(artifact)                   # retrying never changes the verified export
    finally:
        backend.close()


# ------------------------------------------------------------------------------- the task store
def test_the_task_store_saves_lists_revises_and_deletes():
    entry = nt.save('divider', DECK, circuit_class='divider')
    assert entry['task_key'] == 'ngspice:divider' and entry['revision'] == 1 and entry['created'] and entry['devices'] == 4
    assert list(nt.list_tasks()) == ['divider'] and (Path(entry['directory']) / 'netlist.cir').read_text() == DECK
    starter = nt.starter_config('ngspice:divider')
    rows = {r['variable_id']: r for r in starter['parameters']}
    assert set(rows) == {'v1_dc', 'r1_r', 'x1_r2_r', 'x1_c1_c'}
    assert rows['r1_r'] == dict(variable_id='r1_r', instance_path='r1', parameter_name='r', unit='ohm', scale='linear', value_type='continuous',
                                optimized=True, notes='r on line 4', lower=500.0, upper=2000.0)
    assert rows['x1_c1_c']['unit'] == 'pF' and rows['x1_c1_c']['lower'] == 0.5 and rows['x1_c1_c']['notes'].endswith('of subcircuit load')
    assert rows['v1_dc']['optimized'] is False and rows['v1_dc']['unit'] == 'V'
    assert starter['measurements'] == [dict(measurement_id='m_vout_v', analysis='dc', result_source='backend_profile', source_name='vout_v',
                                            unit='V', notes='line 14: print vout_v')]
    assert starter['targets'] == [] and starter['project'] == dict(name='divider', task_name='divider')
    again = nt.save('divider', DECK.replace('1k', '3k'), circuit_class='divider')
    assert again['revision'] == 2 and not again['created'] and (Path(again['directory']) / 'history' / 'r1.cir').read_text() == DECK
    assert tasks.starter_config('ngspice:divider')['parameters'][0]['upper'] == 6000.0        # r1: 3k now, half..twice
    gone = nt.delete('divider')
    assert gone['deleted'] == 'ngspice:divider' and Path(gone['kept_copy']).is_dir() and nt.list_tasks() == {}
    with pytest.raises(KeyError):
        nt.load('divider')
    for name, text in (('Bad Name', DECK), ('ok', '   '), ('ok', '* title only\n.end\n')):
        with pytest.raises(nt.NgspiceTaskError):
            nt.save(name, text)
    assert nt.parse_kinds_text('a=nmos, b=pmos\nc=resistor') == {'a': 'nmos', 'b': 'pmos', 'c': 'resistor'}
    with pytest.raises(nt.NgspiceTaskError):
        nt.parse_kinds_text('nmos')
    with pytest.raises(nt.NgspiceTaskError):
        nt.delete('never')


def test_a_task_is_a_real_task_that_needs_an_ngspice_connection():
    nt.save('divider', DECK)
    listed = {t['task_key']: t for t in tasks.list_tasks()}
    assert listed['ngspice:divider']['kind'] == 'ngspice' and not listed['ngspice:divider']['available']   # no connection file yet
    assert 'ngspice connection' in listed['ngspice:divider']['blocker']
    runtime = tasks.load_task(circuit('ngspice:divider'))
    assert runtime.origin == 'real' and not runtime.mock and runtime.connection_family == 'ngspice' and not runtime.authorized
    assert runtime.provided_metrics == ('vout_v',) and runtime.circuit['simulator'] == 'ngspice' and runtime.circuit['revision'] == 1
    assert runtime.parser_config_path is None and runtime.netlist_text == DECK
    write_profiles(lab=dict(env_file='/x/.env'), sim=dict(kind='ngspice_local'))
    assert 'Virtuoso over SSH' in tasks.load_task(circuit('ngspice:divider'), profile_id='lab').circuit['connection_problem']
    ready = tasks.load_task(circuit('ngspice:divider'), profile_id='sim', allow_real=True)
    assert ready.circuit['connection_problem'] is None and ready.authorized and 'ngspice on this machine' in ' '.join(ready.notes)
    assert {t['task_key']: t['available'] for t in tasks.list_tasks()}['ngspice:divider'] is False   # the ACTIVE one is Virtuoso
    with pytest.raises(tasks.TaskBlocked, match='deleted or never saved'):
        tasks.load_task(circuit('ngspice:nothing'))
    with pytest.raises(KeyError):
        tasks.starter_config('ngspice:nothing')


def prepared_config(tmp_path, task_key, *, profile='sim', evaluations=3):
    """Build a short single-lane ngspice run containing only adjustable parameter rows."""
    starter = tasks.starter_config(task_key)
    raw = dict(starter, run=dict(max_evaluations=evaluations, seed=3, connection_profile_id=profile, concurrency=1,
                                 network=dict(encoder_type='graph_transformer', hidden_dim=16, heads=2, layers=1),
                                 advanced=dict(batch_size=2, warmup_transitions=2, episode_length=2)),
               output=dict(output_root=str(tmp_path), experiment_name='ng', flush_every_evaluations=1, checkpoint_every_evaluations=None))
    raw['parameters'] = [r for r in raw['parameters'] if r['optimized']]
    return schema.WorkbenchConfig.model_validate(raw)


@pytest.mark.parametrize('policy', ['best_and_failures', 'all', 'none'])
def test_a_run_retains_local_ngspice_raw_files_by_its_policy(tmp_path, monkeypatch, policy):
    """Full worker/retention path with a stand-in process; no ngspice program is run."""
    from gator_workbench import worker

    class RawRunner:
        """An ngspice stand-in that produces raw and numerical files for retention checks."""
        def local(self, program, deck, timeout):
            """Write fixture output files and report a successful voltage measurement."""
            (deck.parent / 'results.raw').write_text('fake raw waveform')
            (deck.parent / 'values.dat').write_text('fake numerical output')
            return 0, 'vout_v = 0.6\n', ''

    monkeypatch.setattr(ngspice_backend, 'RealRunner', RawRunner)
    nt.save('divider', DECK.replace('print vout_v', 'print vout_v\nwrite results.raw all\nwrdata values.dat v(out)'))
    write_profiles(sim=dict(kind='ngspice_local'))
    config = prepared_config(tmp_path, 'ngspice:divider', evaluations=1)
    config.output.waveform_retention = policy
    config.targets = [schema.PerformanceTarget(metric_id='vout_v', equation='m_vout_v', unit='V', constraint='>=',
                                               lower=0.4, normalization_scale=0.1)]
    layout, _ = runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=ngspice_probe(tmp_path))
    assert worker.main(['--run-dir', str(layout.run_dir), '--allow-real', '--threads']) == 0
    jobs = DatasetReader(layout.data).rows('simulator_jobs')
    assert len(jobs) == 1
    if policy == 'none':
        assert jobs[0]['retention_status'] == 'deleted_by_policy'
        assert not list(layout.run_dir.rglob('results.raw'))
    else:
        retained = layout.run_dir / jobs[0]['output_path']
        assert (retained / 'results.raw').read_text() == 'fake raw waveform'
        assert (retained / 'values.dat').read_text() == 'fake numerical output'
        assert (retained / 'deck.cir').is_file() and (retained / 'ngspice.log').is_file()
        entry = read_json(layout.waveforms / 'index.json')['entries'][jobs[0]['job_id']]
        assert entry['status'] == ('retained_best' if policy == 'best_and_failures' else 'retained_all')


def test_a_run_needs_an_authorization_and_a_connection_of_the_right_family(tmp_path):
    nt.save('divider', DECK)
    write_profiles(lab=dict(env_file='/x/.env'), sim=dict(kind='ngspice_local'))
    config = prepared_config(tmp_path, 'ngspice:divider')
    config.targets = [schema.PerformanceTarget(metric_id='vout_v', equation='m_vout_v', unit='V', constraint='>=', lower=0.4, normalization_scale=0.1)]
    monitor = ngspice_probe(tmp_path)
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(config, roots_for(tmp_path), monitor=monitor)
    assert refused.value.code == 'real_authorization_required'
    config.run.connection_profile_id = 'lab'
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=monitor)
    assert refused.value.code == 'connection_gate' and 'Virtuoso over SSH' in str(refused.value) and 'ngspice' in str(refused.value)
    assert monitor.probes_started == 0 and not list(tmp_path.rglob('run_manifest.json'))
    config.run.connection_profile_id = 'sim'
    layout, manifest = runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=monitor)
    assert manifest['provenance'] == 'real' and not manifest['mock'] and manifest['circuit']['simulator'] == 'ngspice'
    assert manifest['connection_gate']['needed_layers'] == list(NGSPICE_LAYERS) and manifest['authorization']['real_simulation']
    assert (layout.input_snapshot / 'netlist.cir').read_text() == DECK and not (layout.input_snapshot / 'netlist.scs').exists()
    assert read_json(layout.input_snapshot / 'hierarchy.json')['combined_netlist'] == 'netlist.cir'


def test_a_virtuoso_task_on_an_ngspice_connection_is_refused_before_anything_is_probed(tmp_path):
    """Shown with the built-in OTA7 until it was removed (record 7.128): a task saved from a cell is refused the same way."""
    from cdf_write_support import make
    make(tmp_path)
    write_profiles(lab=dict(env_file='/x/.env'), sim=dict(kind='ngspice_local'))
    monitor = ngspice_probe(tmp_path)
    raw = tasks.starter_config('real:ring_cdf')
    raw['run'], raw['output'] = dict(max_evaluations=2, connection_profile_id='sim'), dict(experiment_name='x', output_root=str(tmp_path))
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(schema.WorkbenchConfig.model_validate(raw), roots_for(tmp_path), allow_real=True, monitor=monitor)
    assert refused.value.code == 'task_blocked' and 'ngspice on this machine' in str(refused.value)
    assert 'Virtuoso + Spectre' in str(refused.value) and monitor.probes_started == 0


# ------------------------------------------------------------------------------- the routes
@pytest.fixture
def client(tmp_path):
    """Provide ngspice routes with a fake connection probe."""
    return TestClient(workbench_app(tmp_path, monitor=ngspice_probe(tmp_path), auto_check_on_start=True))


def test_the_routes_read_check_save_load_and_delete(client, tmp_path):
    read = client.post('/api/ngspice/read', json=dict(path=str(EXAMPLE)))
    assert read.status_code == 200 and read.json()['text'].startswith('* Five-transistor OTA') and read.json()['path'] == str(EXAMPLE)
    outside = tmp_path / 'secret.cir'
    outside.write_text(DECK)
    assert client.post('/api/ngspice/read', json=dict(path=str(outside))).status_code == 403
    assert client.post('/api/ngspice/read', json=dict(path=str(REPO / 'nothing.cir'))).status_code == 409
    checked = client.post('/api/ngspice/check', json=dict(text=DECK)).json()
    assert checked['ok'] and checked['devices'] == 4 and checked['measurements'][0]['name'] == 'vout_v' and checked['problems'] == []
    assert client.post('/api/ngspice/check', json=dict(text='* nothing\n.end\n')).json()['problems']
    assert client.post('/api/ngspice/check', json=dict(text=DECK, device_kinds='x=y')).status_code == 422
    assert client.post('/api/ngspice/check', json=dict(text=DECK, path='/x')).status_code == 422       # no unknown field
    saved = client.post('/api/ngspice/task/save', json=dict(name='divider', text=DECK, device_kinds='', circuit_class='divider'))
    assert saved.status_code == 200 and saved.json()['task_key'] == 'ngspice:divider' and saved.json()['created']
    assert saved.json()['starter']['measurements'][0]['measurement_id'] == 'm_vout_v' and saved.json()['check']['devices'] == 4
    listed = {t['task_key']: t for t in client.get('/api/tasks').json()['tasks']}
    assert listed['ngspice:divider']['kind'] == 'ngspice' and listed['ngspice:divider']['starter_project']['task_name'] == 'divider'
    starter = client.get('/api/tasks/starter', params=dict(task_key='ngspice:divider'))
    assert starter.status_code == 200 and [r['variable_id'] for r in starter.json()['parameters']] == ['r1_r', 'v1_dc', 'x1_c1_c', 'x1_r2_r']
    loaded = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='ngspice:divider'))).json()
    assert loaded['loaded'] and loaded['simulator'] == 'ngspice' and loaded['mock'] is False and loaded['provided_metrics'] == ['vout_v']
    assert loaded['circuit']['revision'] == 1 and 'ngspice connection' in ' '.join(loaded['notes']) and loaded['hierarchy'] == {'v1': {}, 'r1': {}, 'x1': {'r2': {}, 'c1': {}}}
    task = client.get('/api/ngspice/task', params=dict(name='divider')).json()
    assert task['text'] == DECK and task['revision'] == 1
    assert client.get('/api/ngspice/task', params=dict(name='never')).status_code == 404
    config = dict(starter.json(), run=dict(max_evaluations=2), output=dict(experiment_name='x'))
    config['targets'] = [dict(metric_id='vout_v', equation='m_vout_v', unit='V', constraint='>=', lower=0.4, normalization_scale=0.1)]
    validated = client.post('/api/config/validate', json=dict(config=config)).json()
    assert not validated['blocks_run'] and validated['circuit_blocker'] is None
    # a start without an ngspice connection: refused in words, before a run directory exists
    write_profiles(lab=dict(env_file='/x/.env'))
    config['run']['connection_profile_id'] = 'lab'
    started = client.post('/api/runs/start', json=dict(config=config, authorize_real_simulation=True))
    assert started.status_code == 409 and started.json()['detail']['code'] == 'connection_gate' and 'ngspice' in started.json()['detail']['message']
    assert not list(tmp_path.rglob('run_manifest.json'))
    deleted = client.post('/api/ngspice/task/delete', json=dict(name='divider'))
    assert deleted.status_code == 200 and deleted.json()['deleted'] == 'ngspice:divider'
    assert client.post('/api/ngspice/task/delete', json=dict(name='divider')).status_code == 409
    assert 'ngspice:divider' not in {t['task_key'] for t in client.get('/api/tasks').json()['tasks']}
    plan = client.get('/api/runs/corner-check/plan', params=dict(run_dir=str(tmp_path)))
    assert plan.status_code in (403, 404)                                              # not a run: the plan is not the point here


def test_the_corner_check_says_it_has_no_ngspice_profile():
    from gator_workbench import corner_check
    with pytest.raises(corner_check.CheckRefused, match='ngspice netlist task has none'):
        corner_check._real_profile('ngspice:divider')


# ------------------------------------------------------------------------------- REAL: the installed ngspice
@pytest.mark.skipif(not NGSPICE, reason='ngspice is not installed on this machine')
def test_REAL_the_installed_ngspice_solves_the_trial_deck_and_the_example():
    from gator_workbench import ngspice_link
    layers = ngspice_link.run_layers(ngspice_link.RealRunner(), dict(kind='ngspice_local'), scope='full')
    assert [(l['layer'], l['state']) for l in layers] == [(n, s) for n, s in zip(NGSPICE_LAYERS, ('ok', 'not_applicable', 'ok', 'ok'))]
    graph = sized_graph(EXAMPLE.read_text(), {'xota/m1': ('w', 2e-6, 8e-6)})
    backend = NgspiceBackend(EXAMPLE.read_text(), graph, NgspiceLink('ngspice_local', NGSPICE), units={'gain_db': 'dB'},
                             include_root=str(EXAMPLE.parent), source=str(EXAMPLE))
    backend.connect()
    work = Path(tempfile.mkdtemp(prefix='gator-ngspice-real-'))
    results = []
    for width in (4e-6, 6e-6):
        backend.set_parameters({('xota/m1', 'w'): width})
        artifact = backend.generate_netlist(work / 'exports')
        backend.get_circuit_graph(artifact)
        results.append(backend.run_simulation(SimulationRequest(artifact, work / 'sims', ('gain_db',), 60.0, backend.read_parameters(),
                                                                condition=backend.condition)))
    backend.close()
    assert all(r.status == SimulationStatus.OK for r in results) and results[0].simulator_version.startswith('ngspice-')
    assert results[0].metrics['gain_db'] == pytest.approx(46.4864, abs=0.01) and results[0].metric_units['gain_db'] == 'dB'
    assert results[1].metrics['gain_db'] != results[0].metrics['gain_db']              # a changed width changes the circuit
    assert set(results[0].metrics) == {'vout_v', 'supply_power_w', 'gain_db', 'ugf_hz', 'phase_at_ugf_deg', 'phase_margin_deg'}


@pytest.mark.skipif(not NGSPICE, reason='ngspice is not installed on this machine')
def test_REAL_a_whole_run_on_the_installed_ngspice(tmp_path):
    """The example deck as a task, an ngspice_local connection with a fake probe, the run worker in this process (thread
    lanes): evaluations are real ngspice simulations, the tables hold them, the best design is written as a deck."""
    from gator_workbench import worker
    nt.save('ota5', EXAMPLE.read_text(), source_path=str(EXAMPLE), circuit_class='opamp')
    write_profiles(sim=dict(kind='ngspice_local', ngspice_bin=NGSPICE))
    config = prepared_config(tmp_path, 'ngspice:ota5', evaluations=4)
    config.parameters = [p for p in config.parameters if p.variable_id in ('xota_m1_w', 'xota_m2_w')]
    config.parameters[1].binding_group, config.parameters[1].ratio = 'xota_m1_w', 1.0
    config.targets = [schema.PerformanceTarget(metric_id='gain_db', equation='m_gain_db', unit='dB', constraint='>=', lower=40.0, normalization_scale=10.0),
                      schema.PerformanceTarget(metric_id='phase_margin_deg', equation='m_phase_margin_deg', unit='deg', constraint='>=', lower=60.0,
                                               normalization_scale=10.0, hard=False),
                      schema.PerformanceTarget(metric_id='energy_j', equation='m_supply_power_w / m_ugf_hz', unit='J', constraint='<=', upper=1e-9,
                                               normalization_scale=1e-10, hard=False)]
    layout, manifest = runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=ngspice_probe(tmp_path))
    assert worker.main(['--run-dir', str(layout.run_dir), '--allow-real', '--threads']) == 0
    summary = read_json(layout.summary)
    assert summary['totals']['candidate_evaluations_charged'] == 4 and summary['status'] == 'completed'
    evaluations = DatasetReader(layout.data).rows('evaluations')
    assert len(evaluations) == 4 and all(row['provenance'] == 'real' for row in evaluations)
    assert all(row['reward'] is not None for row in evaluations if row['episode_step'] > 0)   # resets carry no reward row
    metrics = DatasetReader(layout.data).rows('metrics')
    names = {row['metric_name'] for row in metrics}
    assert {'gain_db', 'phase_margin_deg', 'energy_j'} <= names                         # the computed spec too
    best = read_json(layout.best_design / 'best_feasible.json')
    assert best['status'] == 'found'
    deck = layout.best_design / 'optimized_dut.cir'
    assert deck.is_file() and not (layout.best_design / 'optimized_dut.scs').exists()
    written = ng.parse_text(deck.read_text()).graph.parameters['xota/m1']['w'].value
    members = best['design']['expanded_bindings']                                         # value in the canonical unit (m)
    assert written == pytest.approx(next(m['value'] for m in members if m['instance_path'] == 'xota/m1'), rel=1e-9)
    jobs = DatasetReader(layout.data).rows('simulator_jobs')                              # the job folders themselves are cleaned by retention
    assert len(jobs) == 4 and all(job['exit_status'] == 'ok' for job in jobs)


# ------------------------------------------------------------------------------- the ngspice deck is published whole
SMALL_DECK = '* a divider\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 2k\n.op\n.end\n'


def test_a_failed_save_leaves_the_deck_before_it_whole(monkeypatch):
    ngspice_tasks.save('divider', SMALL_DECK)
    deck = ngspice_tasks.task_dir('divider') / ngspice_tasks.FILES['netlist']
    write = Path.write_text

    def half_then_fail(self, text, *args, **kwargs):            # the disk fills up half way through the new deck
        """Write half the replacement deck before raising a simulated full-disk error."""
        write(self, text[:len(text) // 2], *args, **kwargs)
        raise OSError(28, 'No space left on device')
    with monkeypatch.context() as patched, pytest.raises(OSError):
        patched.setattr(Path, 'write_text', half_then_fail)
        ngspice_tasks.save('divider', SMALL_DECK.replace('2k', '3k'))
    assert deck.read_text() == SMALL_DECK                               # it was the half-written new deck before
    assert ngspice_tasks.list_tasks()['divider']['revision'] == 1
