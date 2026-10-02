"""Comparison protocol tests use only MOCK simulations and fake verification."""
import importlib
from pathlib import Path
from threading import Event

import pytest

from gator_workbench import tasks, runs
from gator_workbench.engine import RunEngine
from gator_workbench.paths import OutputRoots
from gator_workbench.storage import DatasetReader
from gator_workbench.storage.atomic import write_json, read_json
from helpers import make_config


@pytest.fixture
def evidence(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'examples'))
    return importlib.import_module('llm_sizing_evidence')


@pytest.mark.parametrize('arm',['sac','llm_warmstart','llm','sac_llm_rescue','matched_random','matched_seeded'])
def test_equal_budget_is_required_for_every_arm(evidence,tmp_path,arm):
    config=make_config(tmp_path,run=dict(max_evaluations=2000))
    config.run.search.max_llm_calls=10
    config.run.search.method=arm if not arm.startswith('matched') else 'llm_warmstart'
    plan={'comparison':dict(protocol=evidence.PROTOCOL,circuits=['fixture'],evaluations_per_run=2000,seeds=[config.run.seed])}
    evidence.validate_comparison(config,{'name':'fixture'},plan)
    config.run.max_evaluations=60
    with pytest.raises(ValueError,match='same frozen'):
        evidence.validate_comparison(config,{'name':'fixture'},plan)


def test_zero_successes_no_longer_exclude_circuits(evidence):
    calibration=importlib.import_module('calibrate_analoggym')
    reports=[]
    for name in ('amp_c','amp_a','amp_b'):
        for method,n in [('random',5),('pattern',3)]:
            for seed in range(n):
                reports.append(dict(circuit=name,method=method,success=False,completed=True,designs=[],
                    simulator_processes=60,verification_processes=0,passing_designs=0,verified_passes=0,run_id=f'{name}-{method}-{seed}'))
    summary=calibration.summarize(reports,24,Event())
    assert summary['selected_circuits']==['amp_a','amp_b','amp_c']
    assert summary['selection_satisfied'] and all(c['eligible'] for c in summary['circuits'])


def test_progress_includes_failed_candidates_and_reports_unreached_budget(evidence):
    rows=[dict(evaluation_id=str(i),commit_seq=i,valid=valid,all_hard_constraints_satisfied=False,
               normalized_constraint_violation=value) for i,(valid,value) in enumerate([(True,9.),(False,0.),(True,4.),(True,7.)],1)]
    metrics=[dict(evaluation_id='3',hard=True,aggregation_level='aggregate',metric_name='settling',
                  raw_value=5e-6,violation=4.,valid=True,satisfied=False)]
    report=evidence.constraint_progress(rows,metrics,budget=2000)
    assert [p['best_violation'] for p in report['trajectory']]==[9.,9.,4.,4.]
    assert report['best_design']['evaluation_id']=='3' and report['improvement']==5.
    assert report['best_design']['specs'][0]['value']==5e-6
    assert report['checkpoints'][-1]==dict(evaluation=2000,reached=False,best_violation=None)
    assert report['trajectory'][1]['violation'] is None


@pytest.mark.parametrize('verified',[True,False])
def test_engine_rechecks_every_pass_before_next_dispatch_without_extra_learning(evidence,tmp_path,verified):
    config=make_config(tmp_path,threshold=0.,run=dict(max_evaluations=3))
    task=tasks.load_task(config.circuit)
    layout,_=runs.prepare_run(config,OutputRoots(extra_roots=[str(tmp_path)]))
    checked=[]
    def verify(bundle,values,observed,directory,**kwargs):
        checked.append(values)
        return dict(passed=verified,simulator_processes=2,differences=[] if verified else ['verdict'])
    guard=evidence.PassingDesignVerifier({'leaders':{},'fixed_native_values':{}},layout.run_dir,tmp_path,verify=verify)
    def observer(evaluation,record):
        directory=tmp_path/'synthetic-native'/evaluation['evaluation_id']
        write_json(directory/'benchmark.json',dict(native_metrics={'score':1.},upstream_passed=True))
        guard(evaluation,dict(record,artifact_directory=str(directory)))
    state=RunEngine(layout.run_dir,task=task,evaluation_observer=observer).run()
    rows=DatasetReader(layout.data).rows('evaluations')
    transitions=DatasetReader(layout.data).rows('transitions')
    expected=3 if verified else 1
    assert len(checked)==len(rows)==expected
    assert guard.summary()['simulator_processes']==expected*2
    assert state==('completed' if verified else 'failed')
    assert (tmp_path/'comparison-STOP.json').exists()==(not verified)
    # Only original search steps can make transitions; baseline and verification do not.
    assert len(transitions)<=max(0,expected-1)
    if not verified:
        driver=importlib.import_module('benchmark_llm_sizing')
        with pytest.raises(ValueError,match='Comparison stopped'):
            driver.run_arm(config,'sac',tmp_path)


def test_false_negative_verdict_stops_comparison(evidence,tmp_path):
    write_json(tmp_path/'native'/'benchmark.json',dict(native_metrics={},upstream_passed=True))
    guard=evidence.PassingDesignVerifier({},tmp_path/'run',tmp_path)
    with pytest.raises(RuntimeError,match='verification failed'):
        guard(dict(evaluation_id='e1',all_hard_constraints_satisfied=False,valid=True),
              dict(artifact_directory=str(tmp_path/'native')))
    assert guard.summary()['failed'] and guard.summary()['simulator_processes']==0


def test_early_failure_remains_in_success_rate_denominator(evidence,tmp_path):
    config=make_config(tmp_path,run=dict(max_evaluations=2000)).model_dump(mode='json')
    rows=[dict(configuration=config,arm='sac',provider=None,seed=i,success=ok,budget_reached=ok,
               constraint_progress={'best_design':{'violation':0. if ok else 3.}},verification={'failed':False},
               run_dir=f'run-{i}') for i,ok in enumerate([True,False])]
    summary=evidence.summarize_comparison(rows)['groups'][0]
    assert summary['runs']==2 and summary['success_rate']==0.5 and summary['runs_reaching_budget']==1
    assert summary['best_violations']==[0.,3.]


def test_missing_native_evidence_blocks_later_arms(evidence,tmp_path):
    guard=evidence.PassingDesignVerifier({},tmp_path/'run',tmp_path)
    with pytest.raises(RuntimeError,match='verification failed'):
        guard(dict(evaluation_id='pass',all_hard_constraints_satisfied=True,valid=True),{})
    assert guard.summary()['failed'] and guard.summary()['verified_passes']==0
    assert (tmp_path/'comparison-STOP.json').exists()


def test_benchmark_manifest_cannot_resume_without_verifier(evidence,tmp_path):
    config=make_config(tmp_path)
    layout,manifest=runs.prepare_run(config,OutputRoots(extra_roots=[str(tmp_path)]))
    manifest['benchmark_verification_required']=True
    write_json(layout.manifest,manifest)
    with pytest.raises(ValueError,match='requires its independent evaluation verifier'):
        RunEngine(layout.run_dir,task=tasks.load_task(config.circuit))
