"""LDO contracts and fault injection; these tests perform no real simulations."""
from copy import deepcopy
from pathlib import Path

import pytest

from analog_optimizer.backends.gpdk045_ldo import Gpdk045LdoProfile
from analog_optimizer.backends.backend import UnsupportedCapability
from analog_optimizer.backends.conditions import SimulationCondition, PVTCorner
from analog_optimizer.measurements.ldo import endpoint_regulation, psrr_at, load_step_metrics
from analog_optimizer.parameters.actions import ActionMapper
from test_bridge_adapter import adapter, changing_writer
import analog_optimizer.backends.virtuoso_bridge as adapter_module

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def profile():
    return Gpdk045LdoProfile(design_file=ROOT/'configs/gpdk045_ldo_design.json',
        mapping_file=ROOT/'configs/gpdk045_ldo.json',reference_structure=ROOT/'examples/circuits/gpdk045_ldo.scs',
        reference_readback=ROOT/'examples/circuits/gpdk045_ldo.cdf.json')


def test_ldo_native_export_and_action_domain(profile):
    assert profile.graph.complete and len(profile.graph.devices)==13
    mapper=ActionMapper(profile.optimization_graph())
    assert mapper.group_ids==('input_pair_width','pass_width')
    for x,y in ((-1,-1),(1,1),(-1,1),(1,-1),(.123,.547)):
        profile.validate_assignment(mapper.legalize(dict(input_pair_width=x,pass_width=y)).assignments)
    for bad in ({('XU1/MP','w'):8e-6}, profile.assignments()|{('XU1/M1','w'):4.001e-6},
                profile.assignments()|{('XU1/M1','w'):4.4e-6}, profile.assignments()|{('XU1/MP','w'):9e-6}):
        with pytest.raises(ValueError): profile.validate_assignment(bad)


@pytest.mark.parametrize('name,key,value',[('MP','l','600n'),('M5','w','5u'),('RUP','r','210k'),('RDN','r','590k')])
def test_fixed_parameters_rejected(profile,name,key,value):
    snap=deepcopy(profile.reference); profile.instances(snap)[name]['params'][key]=value
    with pytest.raises(ValueError): profile.validate_readback(snap)


def test_ldo_partial_write_rolls_back_all_three_devices(adapter,monkeypatch):
    write,calls=changing_writer(adapter)
    def fail_once(*args):
        if args[3]=='MP' and len(calls)==2:
            calls.append('injected'); raise RuntimeError('pass device callback failed')
        return write(*args)
    monkeypatch.setattr(adapter_module,'set_gpdk_mos',fail_once)
    with adapter:
        with pytest.raises(RuntimeError,match='callback failed'):
            adapter.set_parameters(adapter.circuit.assignments(4.4e-6,8.8e-6))
        assert adapter.read_parameters()==adapter.circuit.assignments()
        adapter.set_parameters(adapter.circuit.assignments(4.4e-6,8.8e-6))
    assert adapter.circuit.validate_readback(adapter.test_state)==adapter.circuit.assignments()
    assert {'M1','M2','MP'}<=set(calls)


@pytest.mark.parametrize('old,new', [('GATE','LOAD'),('r=200K','r=210K'),('c=10n','c=20n'),('val1=20u','val1=30u')])
def test_export_rejects_topology_fixed_values_and_pulse_changes(profile,tmp_path,old,new):
    text=(ROOT/'examples/circuits/gpdk045_ldo.scs').read_text()
    assert old in text
    path=tmp_path/'changed.scs';path.write_text(text.replace(old,new))
    with pytest.raises(ValueError): profile.validate_export(path,profile.reference)


def test_ldo_rejects_unqualified_conditions_and_prepares_own_analyses(profile):
    profile.validate_condition(SimulationCondition(profile.nominal_corner))
    with pytest.raises(UnsupportedCapability):
        profile.validate_condition(SimulationCondition(PVTCorner('screen','ss',125,.9),'pvt_validation'))
    deck=profile.build_deck((ROOT/'examples/circuits/gpdk045_ldo.scs').read_text(),'/models/pdk.scs')
    assert 'lineSweep dc' in deck and 'loadSweep dc' in deck and 'tran tran' in deck
    assert 'save VDD VREF VBIAS VOUT' in deck and 'VINP' not in deck


def test_regulation_and_psrr_use_measured_axes_and_input_amplitude():
    assert endpoint_regulation([.95,1,1.05],[.799,.8,.801],.95,1.05)==pytest.approx(.02)
    assert endpoint_regulation([1e-5,1.5e-5,2e-5],[.8,.799,.798],1e-5,2e-5)==pytest.approx(200)
    assert psrr_at([100,1000,10000],[2+0j]*3,[.02+0j]*3)==pytest.approx(40)
    with pytest.raises(ValueError): endpoint_regulation([1,1],[.8,.8],1,2)
    with pytest.raises(ValueError): endpoint_regulation([1,2],[.8,.8],0,2)
    with pytest.raises(ValueError): psrr_at([100,1000],[0j,1],[.1,.1])
    with pytest.raises(ValueError): psrr_at([1,2],[1,1],[.1,.1])


def trace():
    time=[i*1e-6 for i in range(81)]
    output=[.8 if t<10e-6 else .797 for t in time]
    current=[10e-6 if t<10e-6 else 20e-6 for t in time]
    kwargs=dict(delay=10e-6,rise=.1e-6,stop=80e-6,low=10e-6,high=20e-6,nominal_output=.8)
    return time,output,current,kwargs


def test_load_step_measures_deviation_and_finite_window_ripple():
    time,output,current,kwargs=trace()
    result=load_step_metrics(time,output,current,**kwargs)
    assert result['ldo_step_deviation_v']==pytest.approx(.003)
    assert result['ldo_step_final_shift_v']==pytest.approx(.003)
    assert result['ldo_step_tail_ripple_v']==0


@pytest.mark.parametrize('damage',['missing_step','truncated','nan','wrong_initial','unordered'])
def test_load_step_bad_data_is_measurement_failure(damage):
    time,output,current,kwargs=trace()
    if damage=='missing_step': current=[1e-5]*len(time)
    elif damage=='truncated': time,output,current=time[:-1],output[:-1],current[:-1]
    elif damage=='nan': output[-1]=float('nan')
    elif damage=='wrong_initial': kwargs['nominal_output']=.6
    else: time[-2]=time[-1]
    with pytest.raises(ValueError): load_step_metrics(time,output,current,**kwargs)
