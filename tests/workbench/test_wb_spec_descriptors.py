"""What each spec measures, as numbers without its name (record 7.298, spec input "set"): OCEAN probe expressions read
into a tree, the bench's supply and AC stimulus read from its netlist, and one description per spec."""
import math

import pytest

from gator_workbench import schema, spec_descriptors as sd
from helpers import make_config


def facts(analysis, expression, bench=sd.Bench(), **kwargs):
    return set(k for k, v in sd.probe_facts(analysis, expression, bench, **kwargs).items() if v and k not in ('position', 'span'))


BENCH = sd.Bench('VDD_SRC', frozenset({'VDD_SRC'}))
GAIN = 'value(dB20(((VF("/OP") - VF("/ON")) / (VF("/INP") - VF("/INN")))) 10)'


def test_expressions_parse_into_a_tree_with_si_numbers_and_keywords():
    tree = sd.parse_expression('cross(VT("/OUT") (0.99 * value(VS("/VOUT") 1.8)) 1 "rising" ?mode "user")')
    assert tree.kind == 'call' and tree.value == 'cross' and [c.kind for c in tree.children] == ['call', 'mul', 'number', 'string', 'keyword']
    assert sd.parse_expression('value(VF("/OUT") 10k)').children[1].value == pytest.approx(1e4)
    assert sd.parse_expression('-1.8 * IDC("/VDD_SRC/PLUS")').kind == 'mul'
    for unreadable in ('value(VF("/OUT") 10', 'a ) b', '', None, '@@'):
        assert sd.parse_expression(unreadable) is None


def test_what_a_probe_reads_and_how():
    assert facts('ac', GAIN) == {'analysis_ac', 'signal_voltage', 'node_difference', 'form_ratio', 'reduction_value_at',
                                 'reduction_decibel', 'has_position'}
    assert sd.probe_facts('ac', GAIN)['position'] == pytest.approx(0.1) and sd.probe_facts('ac', GAIN)['span'] == 0   # 10 Hz
    assert facts('stb', 'phaseMargin((- getData("loopGain" ?result "stb")))') == {'analysis_stb', 'signal_loop_gain', 'reduction_margin'}
    assert facts('dc', '(-1.8 * IDC("/VDD_SRC/PLUS"))', BENCH) == {'analysis_dc', 'signal_current', 'from_supply', 'form_negated',
                                                                    'form_scaled'}
    assert facts('ac', '(- value(dB20(VF("/VOUT")) 1000))', BENCH) == {
        'analysis_ac', 'signal_voltage', 'ac_stimulus_on_supply', 'form_negated', 'reduction_value_at', 'reduction_decibel',
        'has_position'}
    psrr = f'({GAIN} - value(dB20(getData("/VDD_SRC" ?result "xf")) 10))'
    cmrr = f'({GAIN} - value(dB20(getData("/VCMAC" ?result "xf")) 10) - 6.02)'
    assert {'signal_transfer_xf', 'from_supply'} <= facts('ac', psrr, BENCH) and 'from_other_source' not in facts('ac', psrr, BENCH)
    assert {'signal_transfer_xf', 'from_other_source', 'form_offset'} <= facts('ac', cmrr, BENCH)
    assert facts('noise', 'sqrt(integ(pow(getData("out" ?result "noise") 2) 10 1e+07))') == {
        'analysis_noise', 'signal_noise', 'reduction_integral', 'reduction_root', 'has_position'}
    assert facts('tran', 'frequency(clip(VT("/OUT") 1e-08 3e-08))') == {'analysis_tran', 'signal_voltage', 'reduction_waveform',
                                                                        'reduction_window', 'has_position'}
    assert facts('dc', 'value(VS("/VREF") 27)') == {'analysis_dc', 'signal_voltage', 'reduction_value_at'}   # a sweep value: no place
    assert facts('dc', 'VOUT', measured_by_analyzer=True) == {'analysis_dc', 'signal_no_expression'}
    assert facts('xyz', 'not ( readable') == {'analysis_other', 'signal_no_expression'}


def test_the_bench_s_supply_and_ac_stimulus_come_from_its_netlist():
    netlist = '\n'.join(['subckt amp A B VDD', 'VINNER (A 0) vsource dc=5 mag=1', 'ends amp',
                         'VPROBE (OUT FB) vsource dc=0 type=dc', 'VB_SRC (net2 0) vsource dc=650.00m type=dc',
                         'VDD_SRC (VDD 0) vsource dc=1.8 mag=1 type=dc', 'VDS (STP0 VCM) vsource dc=vd type=dc',
                         'VSTP (STP STP0) vsource mag=1 type=pulse val0=0 \\', '    val1=100.0m period=2u',
                         'ILOAD (OUT 0) isource dc=10.00m type=dc'])
    assert sd.bench_of_netlist(netlist) == sd.Bench('VDD_SRC', frozenset({'VDD_SRC', 'VSTP'}))
    assert sd.bench_of_netlist(netlist, 'VB_SRC').supply == 'VB_SRC'               # what design.json declares wins
    assert sd.bench_of_netlist('') == sd.Bench()


def _ade(raw):
    raw['measurements'] = [dict(measurement_id='m_gain', analysis='ac', result_source='ade_output', source_name='gain',
                                signal=GAIN, unit='dB'),
                           dict(measurement_id='m_f1', analysis='tran', result_source='ade_output', source_name='f1',
                                signal='frequency(clip(VT("/OUT") 1e-08 3e-08))', unit='Hz'),
                           dict(measurement_id='m_f5', analysis='tran', result_source='ade_output', source_name='f5',
                                signal='frequency(clip(VT("/OUT") 1e-07 1.2e-07))', unit='Hz')]
    first = dict(raw['targets'][0])
    raw['targets'] = [dict(first, metric_id='gain_db', equation='m_gain', unit='dB', lower=60.0),
                      dict(first, metric_id='kvco_hz_v', equation='(m_f5 - m_f1) / 0.8', unit='Hz/V', lower=1e8)]


def test_every_spec_of_a_task_gets_one_description(tmp_path):
    config = make_config(tmp_path, mutate=_ade)
    described = sd.describe_specs(config, sd.Bench())
    assert set(described) == {'gain_db', 'kvco_hz_v'} and all(len(v) == len(sd.DESCRIPTOR_COLUMNS) for v in described.values())
    gain, kvco = (dict(zip(sd.DESCRIPTOR_COLUMNS, described[k])) for k in ('gain_db', 'kvco_hz_v'))
    assert gain['form_ratio'] == 1 and gain['form_combined_probes'] == 0 and gain['probe_count'] == pytest.approx(math.log1p(1))
    assert kvco['form_combined_probes'] == 1 and kvco['probe_count'] == pytest.approx(math.log1p(2)) and kvco['analysis_tran'] == 1
    assert sd.words(described['gain_db'], 'dB') == ('dB; ac analysis; reads node voltages; a difference of two nodes; a ratio; '
                                                    'as value at a point, in decibels; at 10 Hz')
    mock = sd.describe_specs(make_config(tmp_path), sd.Bench())                     # a built-in analyzer's probes
    assert all(dict(zip(sd.DESCRIPTOR_COLUMNS, v))['signal_no_expression'] == 1 for v in mock.values())


def test_the_schema_is_the_optimizer_s_set_input():
    from analog_optimizer.models.inputs import SpecSetSchema
    built = sd.spec_set_schema()
    assert isinstance(built, SpecSetSchema) and built.descriptor_columns == sd.DESCRIPTOR_COLUMNS
    assert built.version == 'spec-set-v1/gator-spec-descriptor-v2' and len(sd.DESCRIPTOR_COLUMNS) == 38
    canonical = {schema_unit for schema_unit, _ in sd.UNIT_REFERENCES}
    from gator_workbench import units
    assert {units.canonical_unit(u) for u in units.LOOKUP} <= canonical          # every unit the workbench knows has a place


def test_windows_bands_and_series_tell_alike_specs_apart():
    place = lambda analysis, expression: (round(sd.probe_facts(analysis, expression)['position'], 6),
                                          round(sd.probe_facts(analysis, expression)['span'], 6))
    psrr = [place('ac', f'ymax(clip(dB20(VF("/VREG")) {a} {b}))') for a, b in ((1, 10000), (1, 1000000), (1000000, 1e+10))]
    assert psrr == [(0.2, 0.4), (0.3, 0.6), (0.8, 0.4)]                       # up to 10 kHz, up to 1 MHz, above 1 MHz
    bands = [place('noise', f'sqrt(integ(pow(getData("out" ?result "noise") 2) 10 {b}))') for b in (1e+07, 1e+08)]
    assert bands[0] != bands[1]
    steps = [place('tran', f'frequency(clip((VT("/OUTP") - VT("/OUTN")) {a} {b}))')
             for a, b in ((1.3e-08, 2.95e-08), (3.8e-08, 5.45e-08), (6.3e-08, 7.95e-08))]
    assert len(set(steps)) == 3 and steps == sorted(steps)                   # a series in time order
    words = sd.words(tuple(float(sd.probe_facts('ac', 'ymax(clip(dB20(VF("/VREG")) 1000000 1e+10))').get(c, 0.0))
                           for c in sd.DESCRIPTOR_COLUMNS), 'dB')
    assert words.endswith('over 1 MHz to 10 GHz')


def test_a_combined_spec_takes_its_place_from_the_probe_it_names_first(tmp_path):
    def series(raw):
        raw['measurements'] = [dict(measurement_id=f'm_f{i}', analysis='tran', result_source='ade_output', source_name=f'f{i}',
                                    signal=f'frequency(clip(VT("/OUT") {i}e-08 {i + 1}e-08))', unit='Hz') for i in (1, 2, 3)]
        first = dict(raw['targets'][0])
        raw['targets'] = [dict(first, metric_id=f'inl{i}', unit='1', lower=-0.1, upper=0.1,
                               equation=f'(m_f{i} - (m_f1 + m_f2 + m_f3) / 3) / ((m_f1 + m_f2 + m_f3) / 3)') for i in (1, 2, 3)]
    described = sd.describe_specs(make_config(tmp_path, mutate=series), sd.Bench())
    places = [dict(zip(sd.DESCRIPTOR_COLUMNS, described[f'inl{i}']))['position'] for i in (1, 2, 3)]
    assert places == sorted(places) and len(set(places)) == 3

