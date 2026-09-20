"""Offline tests for independent audit calculations and evidence tampering."""
from copy import deepcopy
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from analog_optimizer.backends.conditions import SimulationCondition
from analog_optimizer.envs.sizing import Observation, parameter_rows
from analog_optimizer.evaluation.real_category import load_physical_categories
from analog_optimizer.parameters.actions import ActionMapper
from analog_optimizer.training.replay import Transition

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('real_category_audit_test',ROOT/'examples/audit_real_cross_category.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_ac_log_interpolation_and_nonzero_stimulus():
    f = [1.,10.,100.,1000.]
    db,phase = np.array([20.,10.,0.,-10.]),np.array([0.,-20.,-40.,-60.])
    h = 10**(db/20)*np.exp(1j*np.deg2rad(phase))
    measured = audit.ac_metrics(f,[1.]*4,[-1.]*4,2*h)
    assert measured['gain_db_at_start'] == pytest.approx(20.)
    assert measured['bandwidth_3db_hz'] == pytest.approx(10**.3)
    assert measured['unity_gain_hz'] == pytest.approx(100.)
    assert measured['phase_margin_estimate_deg'] == pytest.approx(140.)
    assert measured['unity_downward_crossings'] == 1


def test_ac_multiple_crossings_have_no_unique_unity_or_margin():
    h = 10**(np.array([10.,-10.,10.,-10.])/20)
    measured = audit.ac_metrics([1.,10.,100.,1000.],[1.]*4,[0.]*4,h)
    assert measured['unity_downward_crossings'] == 2
    assert measured['unity_gain_hz'] is measured['phase_margin_estimate_deg'] is None


@pytest.mark.parametrize('damage',['frequency','finite','stimulus','response','shape'])
def test_ac_rejects_invalid_raw_data(damage):
    f,p,n,v = [1.,10.,100.],[1.]*3,[0.]*3,[10.,1.,.1]
    if damage == 'frequency':f[1]=1.
    elif damage == 'finite':v[1]=float('nan')
    elif damage == 'stimulus':n[1]=1.
    elif damage == 'response':v[1]=0.
    else:v.pop()
    with pytest.raises(ValueError):audit.ac_metrics(f,p,n,v)


def test_export_hash_check_detects_changes_and_path_escape(tmp_path):
    path=tmp_path/'netlist';path.write_text('original')
    hashes={'netlist':audit.file_digest(path)}
    audit.verify_export_files(tmp_path,hashes)
    path.write_text('different')
    with pytest.raises(ValueError,match='changed'):audit.verify_export_files(tmp_path,hashes)
    with pytest.raises(ValueError,match='escapes'):audit.verify_export_files(tmp_path,{'../netlist':'irrelevant'})


@pytest.fixture
def replay_evidence(tmp_path):
    suite=load_physical_categories(ROOT)
    task=next(t for t in suite.tasks('ldo') if t.partition=='test')
    metrics={s.metric_id:s.lower if s.lower is not None else s.upper for s in task.specs}
    before=Observation(task.graph,task.specs,metrics,{k:True for k in metrics},
        {s.metric_id:s.unit for s in task.specs},'ok','real',1,'offline-before',
        SimulationCondition(suite.profiles['ldo'].nominal_corner))
    after=replace(before,remaining_steps=0,job_id='offline-after')
    proposal={g.id:0. for g in ActionMapper(task.graph).groups}
    applied=ActionMapper(task.graph).legalize(proposal).assignments
    previous,path=tmp_path/'before.json',tmp_path/'after.json'
    previous.write_text(json.dumps(dict(observation=audit.json_value(asdict(before)))))
    transition=Transition(before,proposal,0.,after,True,False,False,applied,'offline-candidate',str(path))
    record=dict(observation=audit.json_value(asdict(after)),proposal=proposal,reward=0.,terminated=True,
                truncated=False,bootstrap=False,applied_parameters=parameter_rows(applied))
    records={'offline-candidate':(path,record)}
    phases=[dict(records=[str(previous),str(path)])]
    return transition,phases,[task],records


def test_replay_matches_exact_permitted_evidence(replay_evidence):
    transition,phases,tasks,records=replay_evidence
    audit.check_replay([transition],phases,tasks,records)


@pytest.mark.parametrize('damage',['missing','extra','measurement','provenance','action'])
def test_replay_audit_rejects_leakage_and_forged_evidence(replay_evidence,damage):
    transition,phases,tasks,records=replay_evidence
    items=[transition]
    if damage=='missing':items=[]
    elif damage=='extra':items.append(transition)
    elif damage=='measurement':
        records['offline-candidate'][1]['observation']['metrics']['ldo_output_error_v']=.123
    elif damage=='provenance':items=[replace(transition,record_path='/different/experiment/after.json')]
    else:records['offline-candidate'][1]['proposal']={'input_pair_width':1.,'pass_width':1.}
    with pytest.raises(ValueError):audit.check_replay(items,phases,tasks,records)
