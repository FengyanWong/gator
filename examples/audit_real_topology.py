"""Read-only independent audit of a completed M5 real-topology benchmark."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import torch
from analog_optimizer.evaluation.transfer import digest, same_topology
from analog_optimizer.backends.virtuoso_bridge import digest as file_digest
from analog_optimizer.parameters.actions import ActionMapper
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
from analog_optimizer.training.sac import source_digest, SACLearner, SACConfig
from analog_optimizer.models import ModelConfig
from analog_optimizer.evaluation.benchmark import weight_digest, ENCODER_LABELS
from benchmark_transfer import make_profile as source_profile
from verify_two_stage_ota import make_profile as target_profile


def audit(directory):
    report=json.loads((directory/'report.json').read_text())
    protocol=json.loads((directory/'protocol.json').read_text())
    sha=protocol.pop('sha256')
    assert digest(protocol)==sha==report['protocol_sha256']
    assert report['passed'] and report['completed'] and not report['unexecuted_test_runs']
    assert source_digest()==protocol['settings']['source_sha256']
    for path,expected in protocol['settings']['provenance']['files'].items():
        assert file_digest(ROOT/path)==expected,path
    assert report['calls']==report['planned_calls']+2
    assert report['calls']==sum(r['calls'] for r in report['phases'])+sum(r['calls'] for r in report['restoration_checks'])
    assert report['real_simulation_calls']==report['calls'] and report['synthetic_calls']==0
    assert report['cache_hits']==report['automatic_retries']==0
    assert all(r['passed'] and r['calls']==1 for r in report['restoration_checks'])
    tasks={t['id']:t for t in protocol['tasks']}
    profiles={t['id']:target_profile() if t['transfer']=='topology' else source_profile() for t in protocol['tasks']}
    graphs={k:v.optimization_graph() for k,v in profiles.items()}
    assert not same_topology(source_profile().graph,target_profile().graph)
    baselines={}
    candidate_count=0
    model_versions=set()
    seen_jobs=set()
    for row in report['phases']:
        assert row['completed'] and row['calls']==row['call_budget']
        assert not row['failure_counts'] and row['restoration']['state']=='restored'
        if row['phase']=='frozen':
            assert row['weight_before']==row['weight_after'] and row['replay_insertions']==0
        evaluator=SpecificationEvaluator(tuple(MetricSpec(**s) for s in tasks[row['task']]['specs']))
        mapper=ActionMapper(graphs[row['task']])
        baseline=json.loads(Path(row['records'][0]).read_text())
        signature=(baseline['netlist_sha256'],baseline['metrics'],baseline['applied_parameters'])
        if row['task'] in baselines:
            assert baselines[row['task']]==signature
        baselines[row['task']]=signature
        for record_path in row['records']:
            candidate_count+=1
            record=json.loads(Path(record_path).read_text())
            assert record['origin']=='real' and record['status']=='ok' and record['evaluation_valid']
            assert record['condition']['purpose']=='nominal' and not record['cache_hit']
            actual={(r['device'],r['parameter']):r['value'] for r in record['applied_parameters']}
            profiles[row['task']].validate_assignment(actual)
            expected=(mapper.legalize(record['proposal']).assignments if record['proposal'] is not None else
                      graphs[row['task']].assignments({g.id:g.value for g in mapper.groups}))
            assert all(abs(actual[k]-v)<1e-18 for k,v in expected.items())
            # Independent reward and feasibility computation from saved physical measurements.
            evaluated=evaluator.evaluate(record['metrics'],record['metric_units'],record['metric_validity'])
            assert abs(evaluated.reward-record['reward'])<1e-12 and evaluated.success==record['success']
            job=Path(record['artifact_directory'])
            assert job.is_relative_to(directory) and job.name==record['job_id']
            result=json.loads((job/'result.json').read_text())
            assert result['simulator_invocations']==1 and result['status']=='ok'
            assert result['netlist_sha256']==record['netlist_sha256']==file_digest(job/'opamp.scs')
            assert record['job_id'] not in seen_jobs
            seen_jobs.add(record['job_id'])
            model_versions.add(result['simulator_version'])
    checkpoints=[]
    for path in sorted(directory.glob('*.pt')):
        payload=torch.load(path,map_location='cpu',weights_only=False)
        contract=payload['contract']
        assert contract['code_sha256']==protocol['settings']['source_sha256']
        experiment=contract['experiment']
        assert experiment['protocol_sha256']==sha and experiment['origin']=='real'
        permitted=[tasks[t] for t in experiment['designs']]
        phase=experiment['split']
        assert all(t['partition']==('train' if phase=='pretrain' else 'test') for t in permitted)
        items=payload['replay']['items']
        for transition in items:
            transition.validate()
            assert transition.observation.origin=='real'
            assert any([asdict(s) for s in transition.observation.specs]==t['specs'] for t in permitted)
            if phase=='pretrain':
                assert not {'XU1/M6','XU1/M7'} & {d.id for d in transition.observation.graph.devices}
        arguments=dict(experiment=experiment,model_config=ModelConfig(**contract['model_config']),
                       config=SACConfig(**contract['config']))
        learner,replay,state=SACLearner.load(path,**arguments)
        if phase=='pretrain':
            label=ENCODER_LABELS[contract['model_config']['encoder_type']]
            expected=next(c['weight_sha256'] for c in report['pretraining_costs']
                          if c['model']==label and c['seed']==state['seed'])
        else:
            expected=next(r['weight_after'] for r in report['test_runs']
                          if r['task']==state['task'] and r['seed']==state['seed']
                          and r['method']==state['summary']['method'])
        assert weight_digest(learner)==expected
        loss=learner.update(replay.sample(2))
        updated=weight_digest(learner)
        restored,again,_=SACLearner.load(path,**arguments)
        assert restored.update(again.sample(2))==loss
        assert weight_digest(restored)==updated
        checkpoints.append(dict(file=path.name,phase=phase,transitions=len(items),exact_next_update=True))
    for row in report['test_runs']:
        if row['upfront_cost']:
            assert row['weight_before']==row['upfront_cost']['weight_sha256']
    for restoration in report['restoration_checks']:
        record=json.loads(Path(restoration['record']).read_text())
        assert (record['netlist_sha256'],record['metrics'],record['applied_parameters'])==baselines[restoration['task']]
    return dict(passed=True,report=str(directory/'report.json'),protocol_sha256=sha,
        real_calls=report['calls'],qualification_calls=report['qualification_calls'],
        total_real_calls=report['benchmark_plus_qualification_calls'],candidate_records_audited=candidate_count,
        checkpoint_count=len(checkpoints),checkpoints=checkpoints,simulator_versions=sorted(model_versions),
        train_test_isolation=True,frozen_weights_unchanged=True,all_baselines_restored=True,
        action_counts={k:len(ActionMapper(g).groups) for k,g in graphs.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    result=audit(args.directory.resolve())
    (args.directory/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
