"""Offline physical-protocol tests. Generated evidence is explicitly test-only."""
from copy import deepcopy
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

import analog_optimizer.evaluation.real_category as module
from analog_optimizer.backends.conditions import SimulationCondition
from analog_optimizer.backends.virtuoso_bridge import build_deck, digest as file_digest, parameter_rows
from analog_optimizer.envs.sizing import Observation
from analog_optimizer.evaluation.real_category import (PhysicalFactory, bind_references, build_plan,
    freeze_plan, load_physical_categories, suite_budget, validate_frozen_plan)
from analog_optimizer.evaluation.transfer import validate_split
from analog_optimizer.models import ENCODER_TYPES, ModelConfig
from analog_optimizer.models.inputs import context_features
from analog_optimizer.training.sac import SACLearner

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'configs/m6_real_cross_category.json'


@pytest.fixture
def suite():
    return load_physical_categories(ROOT)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')


@pytest.fixture
def fixture_bindings(suite,tmp_path):
    """Artificial files exercise validation; these never certify a real run."""
    bindings=dict(library='OFFLINE_TEST',model_file='/offline-test/model.scs',circuits={})
    inspection=tmp_path/'inspection.json'
    write(inspection,dict(passed=True,all_circuits_restored=True,model_hashes_match_before=True,
        full_snapshots={p.design['core_cell']:p.reference for p in suite.profiles.values()},
        model_hashes={'model.scs':'offline-test-digest'}))
    bindings['final_inspection']=str(inspection)
    for name,profile in suite.profiles.items():
        cfg=suite.definition['classes'][name]
        folder=tmp_path/name
        receipt=folder/'receipt.json'
        write(receipt,dict(library=bindings['library'],config=profile.design))
        condition=asdict(SimulationCondition(profile.nominal_corner))
        metric_units={s['metric_id']:s['unit'] for rows in cfg['specs'].values() for s in rows}
        common=dict(job_id=f'offline-fixture-{name}',origin='real',condition=condition,
                    metrics={k:1. for k in metric_units},metric_units=metric_units,
                    metric_validity={k:True for k in metric_units})
        policy=getattr(profile,'analysis_settings',None)
        write(folder/'measurements.json',dict(common,analysis_settings=policy))
        deck=folder/getattr(profile,'deck_name','opamp.scs')
        deck.write_text(getattr(profile,'build_deck',build_deck)((ROOT/cfg['netlist']).read_text(),bindings['model_file']))
        write(folder/'result.json',dict(common,status='ok',simulator_invocations=1,
            netlist_sha256=file_digest(deck),applied_parameters=parameter_rows(profile.validate_readback(profile.reference))))
        write(folder/'bridge_result.json',dict(job_id=common['job_id'],cell=profile.design['testbench_cell'],
            library=bindings['library'],model_file=bindings['model_file'],condition=condition,
            executed_sha256=file_digest(deck),analysis_settings=policy))
        bindings['circuits'][name]=dict(creation_receipt=str(receipt),measurements=str(folder/'measurements.json'))
    path=tmp_path/'bindings.json';write(path,bindings)
    return path


@pytest.mark.parametrize('heldout',['opamp','ldo','vco'])
def test_physical_holdout_has_qualified_actions_and_disjoint_classes(suite,heldout):
    tasks=suite.tasks(heldout)
    assert {t.circuit_class for t in tasks if t.partition!='test'}==set(suite.profiles)-{heldout}
    target=next(t for t in tasks if t.partition=='test')
    assert sum(g.mutable for g in target.graph.parameter_groups)=={'opamp':1,'ldo':2,'vco':3}[heldout]
    validate_split(tasks)
    with pytest.raises(ValueError,match='Held-out category'):
        validate_split(tasks+[replace(target,id='leaked',partition='train',transfer='specification')])


def test_global_budget_counts_all_folds_and_final_baselines(suite):
    budget=suite_budget(suite)
    assert budget['total_calls']==2370 and budget['benchmark_calls']==2367
    assert budget['final_baseline_calls']==3
    assert budget['folds']['vco']==dict(source=270,validation=60,target=459,total=789)   # five encoders since 2026-09-24 (six: 324/72/540/936)
    suite.definition['settings']['max_calls']=2369
    with pytest.raises(ValueError,match='Global budget'):
        suite_budget(suite)


@pytest.mark.parametrize('damage',['unit','toy','optional','missing_partition','policy','workers','duplicate_fold'])
def test_invalid_physical_contract_rejected_offline(tmp_path,damage):
    definition=json.loads(MANIFEST.read_text())
    if damage=='unit': definition['classes']['ldo']['specs']['train'][0]['unit']='mW'
    elif damage=='toy': definition['schema']['metrics'][0][1]='fixture'
    elif damage=='optional': definition['classes']['vco']['specs']['test'][0]['required']=False
    elif damage=='missing_partition': del definition['classes']['opamp']['specs']['validation']
    elif damage=='policy': definition['classes']['vco']['analysis_mode']='reference'
    elif damage=='workers': definition['settings']['max_workers']=2
    else: definition['heldout']=['opamp','ldo','ldo']
    path=tmp_path/'manifest.json';write(path,definition)
    with pytest.raises(ValueError):load_physical_categories(ROOT,path)


def test_frozen_plan_rejects_overwrite_tampering_and_source_drift(fixture_bindings,tmp_path,monkeypatch):
    _,plan=build_plan(ROOT,MANIFEST,fixture_bindings)
    path=tmp_path/'protocol.json';freeze_plan(path,plan)
    assert validate_frozen_plan(ROOT,path)[1]==plan
    with pytest.raises(FileExistsError):freeze_plan(path,plan)
    monkeypatch.setattr(module,'source_digest',lambda:'different-production-source')
    with pytest.raises(ValueError,match='no longer matches'):validate_frozen_plan(ROOT,path)
    plan['settings']['test_steps']+=1;write(path,plan)
    with pytest.raises(ValueError,match='digest mismatch'):validate_frozen_plan(ROOT,path)


@pytest.mark.parametrize('damage',['policy','unit','width','deck','receipt','inspection'])
def test_binding_rejects_wrong_baseline_evidence(suite,fixture_bindings,damage):
    bindings=json.loads(fixture_bindings.read_text())
    folder=Path(bindings['circuits']['vco']['measurements']).parent
    filename={'policy':'bridge_result.json','unit':'measurements.json','width':'result.json',
              'receipt':'receipt.json'}.get(damage)
    if filename:
        path=folder/filename;data=json.loads(path.read_text())
        if damage=='policy':data['analysis_settings']['start_s']=1e-6
        elif damage=='unit':data['metric_units']['vco_frequency_hz']='MHz'
        elif damage=='width':data['applied_parameters'][0]['value']=1.1e-6
        else:data['config']['supply_v']=2
        write(path,data)
    elif damage=='inspection':
        path=Path(bindings['final_inspection']);data=json.loads(path.read_text());data['passed']=False;write(path,data)
    else:(folder/'vco.scs').write_text('modified numerical deck')
    with pytest.raises(ValueError):bind_references(suite,bindings)


def test_factory_rejects_task_and_horizon_drift_before_delegate(suite):
    calls=[]
    delegate=SimpleNamespace(create_recorded=lambda *args:calls.append(args))
    factory=PhysicalFactory(suite,delegate)
    task=next(t for t in suite.tasks('vco') if t.partition=='test')
    with pytest.raises(ValueError,match='budget'):factory(task,9,'unused')
    changed=replace(task,specs=(replace(task.specs[0],upper=999e6),)+task.specs[1:])
    with pytest.raises(ValueError,match='definition'):factory(changed,8,'unused')
    assert calls==[]
    factory(task,8,'unused');assert len(calls)==1


@pytest.mark.parametrize('encoder',ENCODER_TYPES)
def test_physical_metric_masks_and_variable_action_batch(suite,encoder):
    old=torch.get_num_threads();torch.set_num_threads(1)
    try:
        observations=[]
        for name in ('opamp','ldo','vco'):
            task=next(t for t in suite.tasks(name) if t.partition=='test')
            metrics={s.metric_id:(s.lower if s.lower is not None else s.upper) for s in task.specs}
            observation=Observation(task.graph,task.specs,metrics,{k:True for k in metrics},
                {s.metric_id:s.unit for s in task.specs},'ok','real',8,'offline-model-input',
                SimulationCondition(suite.profiles[name].nominal_corner))
            contexts=context_features(observation,suite.schema)[:-7].reshape(-1,13)
            for index,(metric,_,_) in enumerate(suite.schema.metrics):
                if metric not in metrics: assert not contexts[index].any()
            observations.append(observation)
        learner=SACLearner(experiment=dict(origin='real',split='offline-contract-test',designs=list(suite.profiles)),
            spec_schema=suite.schema,model_config=ModelConfig(encoder_type=encoder,hidden_dim=16,heads=2,layers=1))
        batch=learner.batch(observations)
        assert batch.action_counts.tolist()==[1,2,3]
        proposals=learner.act(observations,deterministic=True)
        assert list(map(len,proposals))==[1,2,3]
        assert all(-1<=v<=1 for p in proposals for v in p.values())
        assert learner.updates==0
    finally:torch.set_num_threads(old)


def runner_module():
    spec=importlib.util.spec_from_file_location('physical_runner_test',ROOT/'examples/benchmark_real_cross_category.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def test_runner_retains_partial_costs_and_stops_after_failure(suite,fixture_bindings,tmp_path,monkeypatch):
    runner=runner_module();_,plan=build_plan(ROOT,MANIFEST,fixture_bindings)
    calls=[]
    def fail(*args,report,**kwargs):
        calls.append(args[0]);report.update(calls=7,completed=False)
        raise RuntimeError('injected simulator failure')
    monkeypatch.setattr(runner,'run_benchmark',fail)
    factory=SimpleNamespace(delegate=SimpleNamespace(factories={'opamp-train':None}))
    def inspect(*args):return dict(passed=True)
    directory=tmp_path/'run'
    with pytest.raises(RuntimeError,match='injected simulator failure'):
        runner.execute_suite(suite,plan,factory,None,directory,inspect=inspect)
    report=json.loads((directory/'report.json').read_text())
    assert len(calls)==1 and report['calls']==report['real_simulation_calls']==7
    assert report['unexecuted_folds']==['ldo','vco'] and not report['completed']
    assert report['all_circuits_and_models_restored'] and report['final_checks']==[]


@pytest.mark.parametrize('inspection_failure',[False,True])
def test_suite_final_resets_are_counted_and_inspection_can_fail(suite,fixture_bindings,tmp_path,monkeypatch,inspection_failure):
    runner=runner_module();_,plan=build_plan(ROOT,MANIFEST,fixture_bindings)
    def completed(*args,report,settings,**kwargs):report.update(calls=settings['max_calls'],completed=True)
    monkeypatch.setattr(runner,'run_benchmark',completed)
    class FinalReset:
        simulation_calls=0
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def reset(self):
            self.simulation_calls=1
            path=tmp_path/'fake-final-record.json';write(path,{'offline_test_only':True})
            return None,dict(record_path=str(path))
    class Delegate:
        factories={'opamp-train':None}
        def __call__(self,task,steps,output):
            assert task.partition=='test' and steps==1
            return FinalReset()
    checks=SimpleNamespace(for_task=lambda task:lambda row:None)
    inspections=[]
    def inspect(*args):
        inspections.append(True)
        return dict(passed=not inspection_failure or len(inspections)==1)
    run=tmp_path/'complete'
    factory=SimpleNamespace(delegate=Delegate())
    if inspection_failure:
        with pytest.raises(ValueError,match='Final circuit/model state'):
            runner.execute_suite(suite,plan,factory,checks,run,inspect=inspect)
    else:runner.execute_suite(suite,plan,factory,checks,run,inspect=inspect)
    report=json.loads((run/'report.json').read_text())
    assert report['calls']==2370 and len(report['final_checks'])==3
    assert report['completed'] is (not inspection_failure)


def test_cli_planning_has_no_runtime_factory_or_output(fixture_bindings,tmp_path,monkeypatch,capsys):
    runner=runner_module()
    def forbidden(*args,**kwargs):pytest.fail('Planning attempted to construct a runtime factory')
    monkeypatch.setattr(runner,'runtime_factory',forbidden)
    monkeypatch.setattr('sys.argv',['benchmark_real_cross_category.py','--dry-run',
        '--bindings',str(fixture_bindings),'--output',str(tmp_path/'must-not-exist')])
    runner.main()
    result=json.loads(capsys.readouterr().out)
    assert result['planned_calls']['total_calls']==2370 and result['new_simulator_calls']==0
    assert not (tmp_path/'must-not-exist').exists()
