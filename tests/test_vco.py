"""Offline VCO contract and waveform fault injection; no simulator calls."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from analog_optimizer.backends.gpdk045_vco import Gpdk045VcoProfile
from analog_optimizer.backends.backend import UnsupportedCapability
from analog_optimizer.backends.conditions import SimulationCondition, PVTCorner
from analog_optimizer.measurements.vco import oscillation_metrics, window_mean
from analog_optimizer.parameters.actions import ActionMapper
from test_bridge_adapter import adapter, changing_writer
import analog_optimizer.backends.virtuoso_bridge as adapter_module

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile():
    return Gpdk045VcoProfile(analysis_mode='reference',design_file=ROOT/'configs/gpdk045_vco_design.json',
        mapping_file=ROOT/'configs/gpdk045_vco.json',reference_structure=ROOT/'examples/circuits/gpdk045_vco.scs',
        reference_readback=ROOT/'examples/circuits/gpdk045_vco.cdf.json')


def test_native_vco_graph_and_three_actions(profile):
    assert profile.graph.complete and len(profile.graph.devices) == 14
    mapper = ActionMapper(profile.optimization_graph())
    assert mapper.group_ids == ('stage1_width','stage2_width','stage3_width')
    for values in ((-1,0,1),(1,-1,0),(.24,.51,-.91)):
        profile.validate_assignment(mapper.legalize(dict(zip(mapper.group_ids,values))).assignments)
    for bad in ({('XU1/MS1','w'):1e-6}, profile.assignments()|{('XU1/MS1','w'):1.001e-6},
                profile.assignments()|{('XU1/MS2','w'):1.2e-6},profile.assignments()|{('XU1/MS3','w'):True}):
        with pytest.raises(ValueError): profile.validate_assignment(bad)


@pytest.mark.parametrize('name,key,value',[('MS1','l','600n'),('MP1','w','2.2u'),('MN3','fingers','2'),('C2','c','60f')])
def test_fixed_vco_parameters_rejected(profile,name,key,value):
    snap = deepcopy(profile.reference); profile.instances(snap)[name]['params'][key] = value
    with pytest.raises(ValueError): profile.validate_readback(snap)


def test_vco_partial_write_rolls_back_three_groups(adapter,monkeypatch):
    write,calls = changing_writer(adapter)
    def fail_once(*args):
        if args[3] == 'MS3' and len(calls) == 2:
            calls.append('injected'); raise RuntimeError('stage callback failed')
        return write(*args)
    monkeypatch.setattr(adapter_module,'set_gpdk_mos',fail_once)
    with adapter:
        with pytest.raises(RuntimeError,match='stage callback'):
            adapter.set_parameters(adapter.circuit.assignments(1.1e-6,.9e-6,1.05e-6))
        assert adapter.read_parameters() == adapter.circuit.assignments()
        adapter.set_parameters(adapter.circuit.assignments(1.1e-6,.9e-6,1.05e-6))
    assert adapter.circuit.validate_readback(adapter.test_state) == adapter.circuit.assignments()


@pytest.mark.parametrize('old,new',[('c=50f','c=60f'),('dc=650.00m','dc=700m'),('N1','Nbad')])
def test_vco_export_fixed_stimuli_and_topology(profile,tmp_path,old,new):
    text = (ROOT/'examples/circuits/gpdk045_vco.scs').read_text()
    assert old in text
    path = tmp_path/'changed.scs'; path.write_text(text.replace(old,new))
    with pytest.raises(ValueError): profile.validate_export(path,profile.reference)


def test_vco_condition_and_analysis_contract(profile):
    profile.validate_condition(SimulationCondition(profile.nominal_corner))
    with pytest.raises(UnsupportedCapability):
        profile.validate_condition(SimulationCondition(PVTCorner('screen','ss',125,.9),'pvt_validation'))
    deck = profile.build_deck((ROOT/'examples/circuits/gpdk045_vco.scs').read_text(),'/models/pdk.scs')
    assert deck.count(' alter dev=VCTRL param=dc') == 3
    assert deck.count(' tran stop=') == 3 and 'useprevic=no' in deck
    assert 'ic VOUT=0 XU1.N1=1 XU1.N2=0' in deck and 'save=selected' in deck


def trace(frequency=50e6, interval=.2e-9):
    t = [i*interval for i in range(round(2e-6/interval)+1)]
    v = [.5+.49*math.sin(2*math.pi*frequency*x) for x in t]
    return t,v


def measure(t,v):
    return oscillation_metrics(t,v,supply=1.,start=1e-6,stop=2e-6)


def test_sustained_cycles_frequency_duty_and_startup_detection():
    t,v = trace(); result = measure(t,v)
    assert result['frequency_hz'] == pytest.approx(50e6,rel=1e-9)
    assert result['duty_cycle'] == pytest.approx(.5,rel=1e-9)
    assert result['minimum_cycle_swing_v'] == pytest.approx(.98,rel=1e-4)
    assert result['startup_detection_s'] < .2e-6
    assert result['period_spread'] < 1e-10 and result['complete_cycles'] >= 48


@pytest.mark.parametrize('damage',['flat','decay','small','stops','slow','undersampled','nan','unordered','truncated','drifting','late'])
def test_invalid_oscillation_is_never_a_frequency(damage):
    t,v = trace()
    if damage == 'flat': v = [.5]*len(t)
    elif damage == 'decay': v = [.5+(x-.5)*math.exp(-time/1e-7) for time,x in zip(t,v)]
    elif damage == 'small': v = [.5+(x-.5)*.1 for x in v]
    elif damage == 'stops': v = [x if time < 1.5e-6 else .5 for time,x in zip(t,v)]
    elif damage == 'slow': t,v = trace(1e6)
    elif damage == 'undersampled': t,v = trace(interval=2e-9)
    elif damage == 'nan': v[-1] = float('nan')
    elif damage == 'unordered': t[-2] = t[-1]
    elif damage == 'truncated': t,v = t[:-1],v[:-1]
    elif damage == 'drifting': v = [.5+.49*math.sin(2*math.pi*(50e6*time+5e12*time*time)) for time in t]
    else: v = [x if time > 1.1e-6 else .5 for time,x in zip(t,v)]
    with pytest.raises(ValueError): measure(t,v)


def test_power_integrates_nonuniform_samples_and_clips_window():
    assert window_mean([0,.01,.1,1],[0,.01,.1,1],.05,.75) == pytest.approx(.4)
    with pytest.raises(ValueError): window_mean([0,1],[1,2],-.1,.5)


def test_reference_deck_retains_original_numerics(profile):
    deck = profile.build_deck((ROOT/'examples/circuits/gpdk045_vco.scs').read_text(),'/models/pdk.scs')
    assert 'reltol=1e-5 vabstol=1e-8 iabstol=1e-13' in deck
    assert deck.count('tran stop=2e-06 maxstep=1e-10 errpreset=conservative') == 3


def test_default_policy_and_reference_escape_hatch():
    kwargs = dict(design_file=ROOT/'configs/gpdk045_vco_design.json',
        mapping_file=ROOT/'configs/gpdk045_vco.json',reference_structure=ROOT/'examples/circuits/gpdk045_vco.scs',
        reference_readback=ROOT/'examples/circuits/gpdk045_vco.cdf.json')
    fast = Gpdk045VcoProfile(**kwargs)
    reference = Gpdk045VcoProfile(analysis_mode='reference',**kwargs)
    assert fast.analysis_settings['mode'] == 'fast'
    assert fast.design == reference.design and fast.assignments() == reference.assignments()
    with pytest.raises(ValueError,match='Unknown VCO analysis mode'):
        Gpdk045VcoProfile(analysis_mode='unknown',**kwargs)


def test_fast_policy_does_not_modify_physical_design_or_receipt(profile, adapter, tmp_path):
    original = deepcopy(profile.design)
    profile.analysis_mode = 'fast'
    deck = profile.build_deck((ROOT/'examples/circuits/gpdk045_vco.scs').read_text(),'/models/pdk.scs')
    assert deck.count('tran stop=6e-07 maxstep=5e-11 errpreset=moderate') == 3
    assert 'reltol=0.0001 vabstol=1e-06 iabstol=1e-12' in deck
    assert profile.design == original
    adapter.circuit.analysis_mode = 'fast'
    def export(lib, cell, output, timeout):
        output.mkdir()
        (output/'netlist').write_bytes((ROOT/'examples/circuits/gpdk045_vco.scs').read_bytes())
        return {'input_file':str(output/'input.scs')}
    adapter.test_client.schematic.export_netlist = export
    with adapter:
        artifact = adapter.generate_netlist(tmp_path/'exports')
        manifest = json.loads((artifact.path.parent/'manifest.json').read_text())
        assert manifest['analysis_settings'] == profile.analysis_settings


def test_analysis_rejects_window_mismatch_before_reading_waveforms(profile, tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    psf = ModuleType('virtuoso_bridge.spectre.psf')
    for name in ('read_psf_ascii','result_file','scalar','vector'):
        setattr(psf,name,lambda *args: pytest.fail('Waveforms read with mismatched settings'))
    monkeypatch.setitem(sys.modules,'virtuoso_bridge.spectre.psf',psf)
    (tmp_path/'bridge_result.json').write_text(json.dumps({'analysis_settings':profile.analysis_settings|{'start_s':0.}}))
    with pytest.raises(ValueError,match='settings differ'):
        profile.analyze(tmp_path)


@pytest.mark.parametrize('frequency,valid',[(75e6,True),(25e6,False)])
def test_short_window_still_requires_eight_cycles_per_half(frequency, valid):
    t,v = trace(frequency,interval=.05e-9)
    end = round(.6e-6/.05e-9)+1
    def run():
        return oscillation_metrics(t[:end],v[:end],supply=1.,start=.2e-6,stop=.6e-6)
    if valid:
        assert run()['frequency_hz'] == pytest.approx(frequency,rel=1e-6)
    else:
        with pytest.raises(ValueError,match='Insufficient sustained cycles'):
            run()
