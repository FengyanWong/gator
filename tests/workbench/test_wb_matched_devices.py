"""Matched devices... (status record 7.103): structures read from the typed circuit graph, and the ties they suggest for
the Parameters rows. The idea is netlist-crawler's; the difference pinned here is that device types and pin roles come from
the verified mapping, never from instance names, and that a pair must share a tail node, not a rail. Local files only."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from analog_optimizer.netlist.config import DeviceMapping, ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser

from gator_workbench import ngspice_netlist, ngspice_tasks as nt, schema, structures, tasks
from gator_workbench.circuit_summary import circuit_summary
from gator_workbench.validation import independent_action_count, validate
from helpers import workbench_app

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / 'examples' / 'circuits' / 'ngspice_ota5_level1.cir'

_MOS = dict(terminals=('D', 'G', 'S', 'B'), roles=('drain', 'gate', 'source', 'bulk'), parameters={'w': 'w', 'l': 'l'})
_TWO = dict(terminals=('PLUS', 'MINUS'), roles=('positive', 'negative'))
MAPPING = ParserConfig(models={'nch': DeviceMapping('nmos', **_MOS), 'pch': DeviceMapping('pmos', **_MOS),
                               'resistor': DeviceMapping('resistor', parameters={'r': 'r'}, **_TWO),
                               'vsource': DeviceMapping('vsource', parameters={'dc': 'dc'}, **_TWO),
                               'isource': DeviceMapping('isource', parameters={'dc': 'dc'}, **_TWO)},
                       net_roles={'0': ('ground',)})


def graph_of(text):
    return SpectreParser(MAPPING).parse_text(text)


def found(graph):
    return [(s.kind, s.devices) for s in structures.recognize(graph)]


def rows(raw):
    return [schema.OptimizationParameter.model_validate(r) for r in raw]


def width_rows(graph, devices, lower=0.1, upper=100.0):
    """One independent width row per device, in um, around nothing in particular (the circuit value is inside)."""
    return rows([dict(variable_id=d.replace('/', '_') + '_w', instance_path=d, parameter_name='w', unit='um', lower=lower,
                      upper=upper, optimized=True) for d in devices])


# ------------------------------------------------------------------------------ recognition
@pytest.mark.parametrize('name', ['gpdk045_ota5'])        # the OTA7 and LDO left with their files (7.128)
def test_the_amplifiers_of_record_have_their_pair_tail_and_mirror_load_and_no_rail_pairs(name):
    graph = tasks.verified_profile(name).optimization_graph()
    assert found(graph) == [('differential_pair', ('XU1/M1', 'XU1/M2')), ('tail_source', ('XU1/M5',)),
                            ('active_load', ('XU1/M3', 'XU1/M4'))]
    # netlist-crawler reported M6 / MP with M3 and with M4 as differential pairs: they only share VDD.


def test_the_ring_oscillator_has_no_matched_structure():
    assert found(tasks.verified_profile('gpdk045_vco').optimization_graph()) == []


def test_the_ngspice_example_also_has_its_bias_mirror():
    graph = ngspice_netlist.parse_file(EXAMPLE).graph
    assert found(graph) == [('differential_pair', ('xota/m1', 'xota/m2')), ('tail_source', ('xota/m5',)),
                            ('active_load', ('xota/m3', 'xota/m4')), ('current_mirror', ('xota/m6', 'xota/m5'))]


def test_names_and_unlabelled_rails_decide_nothing():
    """A PMOS input pair whose instances are called INP / INN, a tail called TAIL, bulks on the tail node, and a supply that
    no mapping labels: the pair is found by its pins; two PMOS on that supply are not a pair."""
    graph = graph_of('''
TAIL (ntail vbp vdd vdd) pch w=2u l=1u
INP (outn vip ntail ntail) pch w=4u l=0.5u
INN (outp vin ntail ntail) pch w=4u l=0.5u
LOADA (outn outn 0 0) nch w=1u l=1u
LOADB (outp outn 0 0) nch w=1u l=1u
P1 (a x vdd vdd) pch w=1u l=1u
P2 (b y vdd vdd) pch w=1u l=1u
V1 (vdd 0) vsource dc=1
''')
    assert found(graph) == [('differential_pair', ('INN', 'INP')), ('tail_source', ('TAIL',)),
                            ('active_load', ('LOADA', 'LOADB'))]


def test_a_cross_coupled_pair_may_sit_on_a_rail_and_a_resistor_can_be_a_tail():
    graph = graph_of('''
XA (qa qb 0 0) nch w=1u l=100n
XB (qb qa 0 0) nch w=1u l=100n
M1 (d1 g1 s 0) nch w=2u l=100n
M2 (d2 g2 s 0) nch w=2u l=100n
RT (s 0) resistor r=10k
''')
    assert found(graph) == [('differential_pair', ('M1', 'M2')), ('cross_coupled_pair', ('XA', 'XB'))]


def test_a_folded_cascode_is_followed_along_both_branches():
    graph = graph_of('''
M0 (tail vb 0 0) nch w=4u l=1u
M1 (f1 vip tail 0) nch w=4u l=500n
M2 (f2 vin tail 0) nch w=4u l=500n
M3 (f1 vbp vdd vdd) pch w=8u l=1u
M4 (f2 vbp vdd vdd) pch w=8u l=1u
M5 (o1 vcp f1 vdd) pch w=6u l=500n
M6 (o2 vcp f2 vdd) pch w=6u l=500n
M7 (o1 vcn y1 0) nch w=3u l=500n
M8 (o2 vcn y2 0) nch w=3u l=500n
M9 (y1 o1 0 0) nch w=2u l=1u
M10 (y2 o1 0 0) nch w=2u l=1u
V1 (vdd 0) vsource dc=1
''')
    assert found(graph) == [('differential_pair', ('M1', 'M2')), ('tail_source', ('M0',)),
                            ('load_pair', ('M3', 'M4')), ('cascode_pair', ('M5', 'M6')),
                            ('cascode_pair', ('M7', 'M8')), ('load_pair', ('M9', 'M10'))]


def test_parallel_devices_and_common_source_stages_are_not_pairs():
    graph = graph_of('''
M1 (d g1 s 0) nch w=1u l=100n
M2 (d g2 s 0) nch w=1u l=100n
M3 (x ga 0 0) nch w=1u l=100n
M4 (y gb 0 0) nch w=1u l=100n
I1 (s 0) isource dc=10u
''')
    assert found(graph) == []                     # M1/M2 share their drain; M3/M4 share only ground


def test_the_agent_summary_lists_the_structures():
    summary = circuit_summary(tasks.verified_profile('gpdk045_ota5').optimization_graph())
    assert summary['structures'] == [
        'XU1/M1 and XU1/M2 are a differential pair (gates VINP / VINN, shared source XU1/NTAIL).',
        'XU1/M5 is the tail current source of the pair XU1/M1 / XU1/M2.',
        'XU1/M3 (diode-connected) and XU1/M4 are the current-mirror load of XU1/M1 / XU1/M2.']


# ------------------------------------------------------------------------------ ties
def test_the_ngspice_rows_get_the_pair_and_the_load_tied_and_the_bias_mirror_offered():
    parsed = ngspice_netlist.parse_file(EXAMPLE)
    graph, before = parsed.graph, rows(nt.parameter_rows(parsed))
    plan = {s['id']: s for s in structures.plan_ties(graph, before)}
    assert {i: s['default'] for i, s in plan.items()} == {'differential_pair:xota/m1+xota/m2': True,
                                                          'active_load:xota/m3+xota/m4': True,
                                                          'current_mirror:xota/m6+xota/m5': False}
    assert 'design variable' in plan['current_mirror:xota/m6+xota/m5']['note']
    assert [(c['device'], c['parameter'], c['action'], c['ratio']) for c in plan['differential_pair:xota/m1+xota/m2']['changes']] == [
        ('xota/m2', 'w', 'tie', 1.0), ('xota/m2', 'l', 'tie', 1.0)]
    chosen = {i for i, s in plan.items() if s['default']}
    after = rows(structures.apply_ties(graph, before, chosen))
    assert independent_action_count(before) == 7 and independent_action_count(after) == 5
    by_id = {r.variable_id: r for r in after}
    assert (by_id['xota_m2_w'].binding_group, by_id['xota_m2_w'].ratio, by_id['xota_m2_w'].lower) == ('xota_m1_w', 1.0, None)
    assert 'Its own range was 2 .. 8 um.' in by_id['xota_m2_w'].notes and by_id['xota_m4_l'].binding_group == 'xota_m3_l'
    assert [r.variable_id for r in after] == [r.variable_id for r in before]           # tied in place, no row added or moved
    config = schema.WorkbenchConfig.model_validate(dict(nt_config(after)))
    report = validate(config, graph=graph, provided_metrics=None)
    # Ties remain valid; SAC's existing current-unit limitation is now reported
    # before starting instead of crashing when the first learning batch is made.
    assert [(i.level, i.code) for i in report.issues if i.path.startswith('parameters') and i.level != 'info'] == [
        ('blocker', 'current_group_not_supported_by_sac')]
    again = structures.plan_ties(graph, after)                                         # applying twice changes nothing
    assert [s['id'] for s in again if s['acts']] == ['current_mirror:xota/m6+xota/m5']


def nt_config(parameter_rows):
    return dict(project=dict(name='ota', task_name='ota'), circuit=dict(source='registered_task', task_id='synthetic:gpdk045_ota5'),
                parameters=[r.model_dump() for r in parameter_rows], run=dict(max_evaluations=10))


def test_a_device_without_a_row_gets_a_follower_row_after_its_leader_and_a_mirror_keeps_its_ratio():
    graph = graph_of('''
M1 (d1 g1 s 0) nch w=2u l=100n
M2 (d2 g2 s 0) nch w=2u l=100n
M5 (s nb 0 0) nch w=2u l=1u
M6 (nb nb 0 0) nch w=1u l=1u
I1 (nb 0) isource dc=10u
''')
    before = width_rows(graph, ['M1', 'M6', 'M5'])
    plan = {s['id']: s for s in structures.plan_ties(graph, before)}
    assert [(c['device'], c['action']) for c in plan['differential_pair:M1+M2']['changes']] == [('M2', 'add')]
    mirror = plan['current_mirror:M6+M5']
    assert [(c['device'], c['action'], c['ratio']) for c in mirror['changes']] == [('M5', 'tie', 2.0)]   # the ratio the circuit has
    after = structures.apply_ties(graph, before, set(plan))
    assert [(r['variable_id'], r['binding_group'], r['ratio']) for r in after] == [
        ('M1_w', None, 1.0), ('M1_w__M2', 'M1_w', 1.0), ('M6_w', None, 1.0), ('M5_w', 'M6_w', 2.0)]
    added = after[1]
    assert (added['instance_path'], added['unit'], added['optimized'], added['lower']) == ('M2', 'um', True, None)
    assert added['notes'].startswith('Added: Tied to M1_w (differential pair, ratio 1)')


def test_existing_ties_are_kept_and_other_ties_are_left_alone():
    graph = graph_of('''
M1 (d1 g1 s 0) nch w=2u l=100n
M2 (d2 g2 s 0) nch w=2u l=100n
M3 (d1 bias vdd vdd) pch w=4u l=100n
M4 (d2 bias vdd vdd) pch w=4u l=100n
I1 (s 0) isource dc=10u
V1 (vdd 0) vsource dc=1
''')
    base = [dict(variable_id='a', instance_path='M1', parameter_name='w', unit='um', lower=1, upper=4, optimized=True),
            dict(variable_id='b', instance_path='M2', parameter_name='w', unit='um', binding_group='a', ratio=1.0),
            dict(variable_id='c', instance_path='M3', parameter_name='w', unit='um', lower=2, upper=8, optimized=True),
            dict(variable_id='d', instance_path='M4', parameter_name='w', unit='um', binding_group='a', ratio=2.0)]
    plan = {s['id']: s for s in structures.plan_ties(graph, rows(base))}
    assert [(c['action'], c['reason']) for c in plan['differential_pair:M1+M2']['changes']] == [('kept', 'already follows a')]
    assert not plan['differential_pair:M1+M2']['default']
    assert [(c['device'], c['action']) for c in plan['load_pair:M3+M4']['changes']] == [('M4', 'skip')]   # the user's own tie
    assert structures.apply_ties(graph, rows(base), set(plan)) == [r.model_dump() for r in rows(base)]


# ------------------------------------------------------------------------------ the route
def post(client, config, apply=None):
    response = client.post('/api/parameters/matched', json=dict(config=config, apply=apply))
    assert response.status_code == 200, response.text
    return response.json()


def test_the_route_suggests_for_an_ngspice_task_and_shows_the_change(tmp_path):
    nt.save('ota', EXAMPLE.read_text())
    starter = tasks.starter_config('ngspice:ota')
    config = dict(starter, run=dict(max_evaluations=10))
    client = TestClient(workbench_app(tmp_path))
    answer = post(client, config)
    assert answer['applicable'] and answer['independent_before'] == 7 and answer['note'] == ''
    assert [s['kind'] for s in answer['structures']] == ['differential_pair', 'tail_source', 'active_load', 'current_mirror']
    chosen = [s['id'] for s in answer['suggestions'] if s['default']]
    shown = post(client, config, chosen)
    assert shown['independent_after'] == 5
    assert [p['code'] for p in shown['problems']] == ['current_group_not_supported_by_sac']
    changed = {(d['key'], f['field']) for d in shown['diff'] for f in d['fields']}
    assert ('xota_m2_w', 'binding_group') in changed and ('xota_m4_w', 'binding_group') in changed
    assert {d['section'] for d in shown['diff']} == {'parameters'} and {d['change'] for d in shown['diff']} == {'modified'}
    assert {r['variable_id']: r['binding_group'] for r in shown['parameters']}['xota_m2_w'] == 'xota_m1_w'


def test_the_route_says_plainly_when_the_circuit_cannot_be_read(tmp_path):
    client = TestClient(workbench_app(tmp_path))
    config = dict(project=dict(name='x', task_name='x'), circuit=dict(source='registered_task', task_id='ngspice:missing'),
                  run=dict(max_evaluations=10))
    answer = post(client, config)
    assert not answer['applicable'] and answer['blocked'] and answer['structures'] == []
    assert answer['why_not'].startswith('The circuit could not be read')
