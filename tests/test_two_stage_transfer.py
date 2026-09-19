"""Real-export profile contracts; no Cadence or network needed."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from analog_optimizer.backends.gpdk045_two_stage import Gpdk045TwoStageProfile
from analog_optimizer.evaluation.runtime import BaselineCheck, TaskBaselineChecks, MultiCircuitFactory, BenchmarkFactory
from analog_optimizer.evaluation.transfer import same_topology
from analog_optimizer.parameters.actions import ActionMapper
from test_bridge_adapter import adapter, changing_writer
import analog_optimizer.backends.virtuoso_bridge as adapter_module

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile():
    return Gpdk045TwoStageProfile(design_file=ROOT/'configs/gpdk045_ota7_design.json',
        mapping_file=ROOT/'configs/gpdk045_ota7.json',
        reference_structure=ROOT/'examples/circuits/gpdk045_ota7.scs',
        reference_readback=ROOT/'examples/circuits/gpdk045_ota7.cdf.json')


def test_new_topology_is_not_isomorphic_and_has_two_actions(profile):
    from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
    source = Gpdk045OtaProfile(design_file=ROOT/'configs/gpdk045_opamp_design.json',
        mapping_file=ROOT/'configs/gpdk045_opamp.json',
        reference_structure=ROOT/'examples/circuits/gpdk045_ota5.scs',
        reference_readback=ROOT/'examples/circuits/gpdk045_ota5.cdf.json')
    assert not same_topology(source.graph, profile.graph)
    assert len(ActionMapper(source.optimization_graph()).groups) == 1
    assert len(ActionMapper(profile.optimization_graph()).groups) == 2
    assert len(profile.graph.devices) == 13
    assert profile.validate_readback(profile.reference) == profile.assignments(4e-6)


@pytest.mark.parametrize('input_action,output_action', [(-1,-1),(1,1),(-1,1),(1,-1),(.313,.517)])
def test_all_group_members_stay_on_grid_and_keep_ratio(profile, input_action, output_action):
    values = ActionMapper(profile.optimization_graph()).legalize(
        dict(input_pair_width=input_action, output_stage_width=output_action)).assignments
    profile.validate_assignment(values)
    assert values['XU1/M6','w'] == pytest.approx(4*values['XU1/M7','w'])


def test_partial_unmatched_and_unauthorized_assignments_rejected(profile):
    good = profile.assignments(4e-6)
    for bad in [dict(list(good.items())[:2]), good | {('XU1/M6','w'):8.005e-6},
                good | {('XU1/M7','w'):2.001e-6},good | {('XU1/M3','w'):8e-6}]:
        with pytest.raises(ValueError):
            profile.validate_assignment(bad)


@pytest.mark.parametrize('name,param,value', [('M6','l','600n'),('M7','fingers','2'),('CC','c','2p')])
def test_fixed_new_stage_fields_rejected(profile,name,param,value):
    state=deepcopy(profile.reference)
    profile.instances(state)[name]['params'][param]=value
    with pytest.raises(ValueError):
        profile.validate_readback(state)


def test_output_stage_geometry_must_follow_width(profile):
    state=deepcopy(profile.reference)
    for name,width in [('M6','8.8u'),('M7','2.2u')]:
        profile.instances(state)[name]['params'].update(w=width,fw=width)
    with pytest.raises(ValueError,match='Stale derived'):
        profile.verify_transition(profile.reference,state,profile.assignments(4e-6,8.8e-6))


def test_new_stage_is_restored_after_partial_write(adapter,monkeypatch):
    write,calls=changing_writer(adapter)
    def fail_once(*args):
        if args[3]=='M7' and len(calls)==3:
            calls.append('injected')
            raise RuntimeError('second-stage partial failure')
        return write(*args)
    monkeypatch.setattr(adapter_module,'set_gpdk_mos',fail_once)
    with adapter:
        with pytest.raises(RuntimeError,match='partial failure'):
            adapter.set_parameters(adapter.circuit.assignments(4.4e-6,8.8e-6))
        assert adapter.read_parameters()==adapter.circuit.assignments(4e-6)
        adapter.set_parameters(adapter.circuit.assignments(4.4e-6,8.8e-6))
    assert adapter.circuit.validate_readback(adapter.test_state)==adapter.circuit.assignments(4e-6)
    assert {'M1','M2','M6','M7'} <= set(calls)


def test_new_topology_export_rejects_changed_connections_and_cap(profile,tmp_path):
    text=(ROOT/'examples/circuits/gpdk045_ota7.scs').read_text()
    for old,new in [('CC (NSTAGE VOUT)','CC (NSTAGE VDD)'),('capacitor c=1p','capacitor c=2p'),
                    ('M6 (VOUT NSTAGE VDD VDD)','M6 (VOUT NLOAD VDD VDD)')]:
        assert old in text
        path=tmp_path/'changed.scs';path.write_text(text.replace(old,new))
        with pytest.raises(ValueError):
            profile.validate_export(path,profile.reference)


def test_circuit_specific_baselines_and_factory_reject_wrong_profile(profile,tmp_path):
    from types import SimpleNamespace
    checks=TaskBaselineChecks({'a':BaselineCheck({'gain':25},'a'),'b':BaselineCheck({'gain':53},'b')})
    record=dict(evaluation_valid=True,metrics={'gain':53},netlist_sha256='b')
    checks.for_task(SimpleNamespace(id='b'))(record)
    with pytest.raises(RuntimeError):
        checks.for_task(SimpleNamespace(id='a'))(record)
    factory=MultiCircuitFactory({'a':BenchmarkFactory('real',profile=profile)})
    graph=deepcopy(profile.graph)
    graph.connections[0]=__import__('dataclasses').replace(graph.connections[0],net_id='VDD')
    with pytest.raises(ValueError,match='Task graph'):
        factory(SimpleNamespace(id='a',graph=graph),1,tmp_path)
    assert not factory.parallel_safe
