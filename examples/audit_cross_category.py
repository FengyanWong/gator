"""Audit a trusted local M6 suite: leakage, toy evaluations and checkpoint recovery.

Loads Python/Torch checkpoints; use only artifacts created by this project.
No new backend evaluations are performed; recovery probes update memory only.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import torch
from analog_optimizer.envs.sizing import graph_contract, same_parameters, write_record
from analog_optimizer.evaluation.benchmark import weight_digest
from analog_optimizer.evaluation.cross_category import category_tasks, load_categories
from analog_optimizer.evaluation.transfer import digest
from analog_optimizer.measurements.specs import SpecificationEvaluator
from analog_optimizer.models import ModelConfig
from analog_optimizer.parameters.actions import ActionMapper
from analog_optimizer.training.sac import SACLearner, SACConfig, source_digest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_protocol(path, expected):
    payload = json.loads(path.read_text())
    sha = payload.pop('sha256')
    require(sha == expected == digest(payload), f'Protocol digest mismatch: {path}')
    return payload


def audit(directory):
    directory = Path(directory).resolve()
    report = json.loads((directory / 'report.json').read_text())
    suite = checked_protocol(directory / 'suite-protocol.json', report['suite_sha256'])
    require(report['completed'] and report['real_simulation_calls'] == 0, 'Suite incomplete or not synthetic')
    require(report['synthetic_calls'] == suite['planned_calls'], 'Suite cost differs from frozen plan')
    require(source_digest() == suite['source_sha256'], 'Source changed since experiment')
    for path, sha in suite['provenance']['files'].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, f'Fixture changed: {path}')
    factory, schema, _ = load_categories(ROOT)
    candidates, checkpoints, updates, seen_jobs = 0, [], 0, set()
    require(set(report['folds']) == set(suite['folds']), 'Suite fold set changed')
    for heldout in suite['folds']:
        folder = directory / heldout
        fold = json.loads((folder / 'report.json').read_text())
        protocol = checked_protocol(folder / 'protocol.json', fold['protocol_sha256'])
        require(protocol['settings']['provenance']['suite_sha256'] == report['suite_sha256'], 'Wrong parent suite')
        require(protocol['tasks'] == suite['folds'][heldout]['tasks'], 'Fold tasks differ from suite')
        tasks = {t.id: t for t in category_tasks(factory, heldout)}
        require(json.loads(json.dumps([asdict(t) for t in tasks.values()])) == protocol['tasks'], 'Task definitions changed')
        require(fold['completed'] and not fold['unexecuted_test_runs'], 'Fold incomplete')
        require(fold['calls'] == suite['folds'][heldout]['planned_calls'] == sum(r['calls'] for r in fold['phases']),
                'Fold cost mismatch')
        require(not fold['real_simulation_calls'] and not fold['cache_hits'] and not fold['automatic_retries'],
                'Unexpected real calls, cache or retries')
        expected_paths = {}
        source_tasks = [t for t in tasks.values() if t.partition == 'train']
        for cost in fold['pretraining_costs']:
            path = folder / f'{cost["model"]}-{cost["seed"]}-pretrain.pt'
            expected_paths[path] = (source_tasks, cost['weight_sha256'])
        for row in fold['test_runs']:
            require(row['circuit_class'] == heldout and row['transfer'] == 'category', 'Wrong target class')
            if row['upfront_cost']:
                require(row['weight_before'] == row['upfront_cost']['weight_sha256'], 'Transfer weights differ')
            if row['phase'] in ('scratch', 'adaptation'):
                expected_paths[folder / f'{row["task"]}-{row["method"]}-{row["seed"]}.pt'] = (
                    [tasks[row['task']]], row['weight_after'])
        for row in fold['phases']:
            task = tasks[row['task']]
            require(row['completed'] and row['restoration']['state'] == 'restored', 'Environment not restored')
            require(row['calls'] == row['call_budget'] == len(row['records']), 'Missing evaluations')
            updates += row['updates']
            if row['phase'] == 'frozen':
                require(row['weight_before'] == row['weight_after'] and row['replay_insertions'] == row['updates'] == 0,
                        'Frozen policy changed or admitted replay')
            objective = factory.definitions[task.circuit_class]
            mapper = ActionMapper(task.graph)
            for record_path in row['records']:
                record = json.loads(Path(record_path).read_text())
                require(record['origin'] == 'synthetic' and record['status'] == 'ok' and record['evaluation_valid'],
                        'Invalid analytic evaluation')
                require(record['job_id'] not in seen_jobs, 'Repeated job identity')
                seen_jobs.add(record['job_id'])
                actual = {(p['device'], p['parameter']): p['value'] for p in record['applied_parameters']}
                expected = (mapper.legalize(record['proposal']).assignments if record['proposal'] is not None else
                            task.graph.assignments({g.id: g.value for g in mapper.groups}))
                require(same_parameters(actual, expected), 'Executed parameters differ from proposal')
                errors = []
                for group in mapper.groups:
                    member = group.members[0]
                    value = actual[member.device_id, member.parameter] / member.ratio
                    lower, upper = group.lower, group.upper
                    if group.scale == 'log':
                        value, lower, upper = map(math.log, (value, lower, upper))
                    z = 2 * (value-lower) / (upper-lower) - 1
                    errors.append(((z-objective['targets'][group.parameter_kind])/2)**2)
                expected_metric = objective['score_offset'] + objective['score_multiplier'] * (1-sum(errors)/len(errors))
                require(set(record['metrics']) == {objective['metric_id']} and math.isclose(
                    record['metrics'][objective['metric_id']], expected_metric, abs_tol=1e-12), 'Toy metric mismatch')
                evaluated = SpecificationEvaluator(task.specs).evaluate(
                    record['metrics'], record['metric_units'], record['metric_validity'])
                require(evaluated.valid and evaluated.success == record['success'] and
                        math.isclose(evaluated.reward, record['reward'], abs_tol=1e-12), 'Reward mismatch')
                candidates += 1
        require(set(folder.glob('*.pt')) == set(expected_paths), 'Checkpoint set differs from learning matrix')
        for path, (permitted, expected_weight) in expected_paths.items():
            payload = torch.load(path, map_location='cpu', weights_only=False)
            contract = payload['contract']
            experiment = contract['experiment']
            require(experiment['protocol_sha256'] == fold['protocol_sha256'] and
                    set(experiment['designs']) == {t.id for t in permitted}, 'Checkpoint belongs to another task')
            observed = set()
            for transition in payload['replay']['items']:
                transition.validate()
                matches = [t.id for t in permitted if transition.observation.specs == t.specs and
                           graph_contract(transition.observation.graph) == graph_contract(t.graph)]
                require(transition.observation.origin == 'synthetic' and len(matches) == 1, 'Replay leaked across tasks')
                observed.update(matches)
            require(observed == {t.id for t in permitted}, 'Shared source replay is missing a source class')
            arguments = dict(experiment=experiment, spec_schema=schema, model_config=ModelConfig(**contract['model_config']),
                             config=SACConfig(**contract['config']))
            model, replay, _ = SACLearner.load(path, **arguments)
            require(weight_digest(model) == expected_weight, 'Checkpoint weights differ from report')
            expected_update = model.update(replay.sample(suite['settings']['batch_size']))
            expected_digest = weight_digest(model)
            restored, replay2, _ = SACLearner.load(path, **arguments)
            require(restored.update(replay2.sample(suite['settings']['batch_size'])) == expected_update and
                    weight_digest(restored) == expected_digest, 'Next update does not resume exactly')
            checkpoints.append(dict(path=str(path), exact_next_update=True, permitted_tasks=sorted(observed)))
        print(f'Audited {heldout}: {fold["calls"]} evaluations, {len(expected_paths)} checkpoints', flush=True)
    require(candidates == report['synthetic_calls'], 'Candidate audit count differs from suite')
    return dict(passed=True, synthetic_calls=candidates, real_simulation_calls=0, training_updates=updates,
                checkpoint_count=len(checkpoints), checkpoints=checkpoints, all_environments_restored=True,
                train_validation_test_isolated=True, electrical_performance_validated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = audit(args.directory)
    write_record(args.directory / 'audit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'checkpoints'}, indent=2))


if __name__ == '__main__':
    main()
