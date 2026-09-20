"""Read-only audit of a completed, trusted local M6 physical pilot.

Recomputes electrical metrics from saved PSF and probes checkpoint recovery in
memory. No bridge connection or new simulator evaluation is made. Torch files
contain Python objects and must come from a trusted local experiment.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'examples'))

import numpy as np
import torch
from analog_optimizer.backends.spectre_validation import validate_completion
from analog_optimizer.backends.virtuoso_bridge import build_deck, digest as file_digest, write_json
from analog_optimizer.envs.sizing import graph_contract, same_parameters
from analog_optimizer.evaluation.benchmark import benchmark_models, weight_digest
from analog_optimizer.evaluation.real_category import read, require, validate_frozen_plan
from analog_optimizer.evaluation.transfer import aggregate_runs, digest
from analog_optimizer.measurements.specs import SpecificationEvaluator
from analog_optimizer.models import ModelConfig
from analog_optimizer.parameters.actions import ActionMapper
from analog_optimizer.training.sac import SACConfig, SACLearner
from audit_ldo_baseline import check_metrics as check_ldo
from audit_vco_baseline import check_metrics as check_vco


def json_value(value):
    return json.loads(json.dumps(value, allow_nan=False))


def parameters(rows):
    result = {(r['device'], r['parameter']): r['value'] for r in rows}
    require(len(result) == len(rows), 'Repeated parameter identity')
    return result


def verify_export_files(directory, hashes):
    """Overlap small read-only file reads on Windows-mounted artifact storage."""
    directory = Path(directory).resolve()
    def verify(item):
        name, sha = item
        path = (directory/name).resolve()
        require(path.is_relative_to(directory), 'Export manifest path escapes its directory')
        require(file_digest(path) == sha, f'Export file changed: {path}')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(verify, hashes.items()))


def ac_metrics(frequency, positive, negative, output):
    """Independent NumPy calculation with log-frequency crossing interpolation."""
    f = np.asarray(frequency, dtype=float)
    p, n, v = (np.asarray(a, dtype=complex) for a in (positive, negative, output))
    require(f.ndim == 1 and len(f) >= 3 and np.all(np.isfinite(f)) and
            np.all(f > 0) and np.all(np.diff(f) > 0), 'Invalid AC frequency grid')
    require(all(a.shape == f.shape and np.all(np.isfinite(a)) for a in (p, n, v)),
            'Invalid AC vectors')
    require(np.all(np.abs(p-n) > 0), 'Zero differential AC stimulus')
    h = v / (p-n)
    require(np.all(np.abs(h) > 0), 'Zero AC response')
    db = 20*np.log10(np.abs(h))
    phase = np.rad2deg(np.unwrap(np.angle(h)))

    def crossings(level):
        indices = np.flatnonzero((db[:-1] > level) & (db[1:] <= level))
        rows = []
        for i in indices:
            fraction = (level-db[i])/(db[i+1]-db[i])
            rows.append((float(np.exp(np.log(f[i])+fraction*np.log(f[i+1]/f[i]))),
                         float(phase[i]+fraction*(phase[i+1]-phase[i]))))
        return rows

    bandwidth, unity = crossings(db[0]-3), crossings(0.)
    unique = db[0] > 0 and len(unity) == 1
    return dict(gain_db_at_start=float(db[0]), gain_reference_hz=float(f[0]),
                bandwidth_3db_hz=bandwidth[0][0] if bandwidth else None,
                unity_gain_hz=unity[0][0] if unique else None,
                phase_margin_estimate_deg=180+unity[0][1] if unique and abs(phase[0]) < 45 else None,
                unity_downward_crossings=len(unity))


def check_opamp(job, expected):
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, scalar, vector, frequency_hz
    raw = Path(read(job/'bridge_result.json')['metadata']['output_dir'])
    dc = read_psf_ascii(result_file(raw, 'dcOp.dc'))
    ac = read_psf_ascii(result_file(raw, 'ac.ac'))
    metrics = ac_metrics(frequency_hz(ac), vector(ac, 'VINP'), vector(ac, 'VINN'), vector(ac, 'VOUT'))
    supply, current, output = scalar(dc, 'VDD'), -scalar(dc, 'VDD:p'), scalar(dc, 'VOUT')
    require(math.isclose(supply, 1., abs_tol=1e-9), 'OTA DC supply changed')
    metrics.update(supply_current_a=current, supply_power_w=supply*current, output_dc_v=output)
    require(metrics.keys() == expected.keys(), 'OTA metric identities changed')
    for key, value in metrics.items():
        require((value is None and expected[key] is None) or
                (value is not None and expected[key] is not None and
                 math.isclose(value, expected[key], rel_tol=1e-9, abs_tol=1e-14)),
                f'OTA raw metric mismatch: {key}')


def checked_protocol(path, expected):
    payload = read(path)
    sha = payload.pop('sha256')
    require(sha == expected == digest(payload), f'Protocol digest mismatch: {path}')
    return payload


class CandidateAudit:
    def __init__(self, directory, suite, plan, state=None):
        self.directory, self.suite, self.plan = Path(directory).resolve(), suite, plan
        self.records, self.jobs, self.exports, self.versions = {}, set(), set(), set()
        self.counts, self.timings = Counter(), {}
        self.state = {} if state is None else state

    def check(self, path, task, *, baseline=False):
        path = Path(path).resolve()
        self.state['last_candidate'] = str(path)
        require(path.is_relative_to(self.directory), 'Candidate outside experiment')
        r = read(path)
        require(r['candidate_id'] not in self.records and path.stem == r['candidate_id'], 'Repeated candidate')
        require(r['state'] == 'completed' and r['origin'] == 'real' and r['status'] == 'ok' and
                r['evaluation_valid'] and r['candidate_evaluated'] and r['simulation_dispatched'] and
                not r['cache_hit'] and not r['retryable'], 'Incomplete or failed physical evaluation')
        require(r['kind'] == ('reset' if baseline else 'step') and
                r['replay_eligible'] == (not baseline), 'Candidate kind/replay mismatch')
        profile = self.suite.profiles[task.circuit_class]
        reference = self.plan['references'][task.circuit_class]
        require(r['metric_units'] == reference['metric_units'] and
                r['metrics'].keys() == reference['metrics'].keys(), 'Physical metric identities/units changed')
        require(r['condition'] == reference['condition'] and r['evaluation_purpose'] == 'nominal',
                'Candidate nominal condition changed')
        actual = parameters(r['applied_parameters'])
        mapper = ActionMapper(task.graph)
        expected = (task.graph.assignments({g.id:g.value for g in mapper.groups}) if baseline else
                    mapper.legalize(r['proposal']).assignments)
        profile.validate_assignment(actual)
        require(same_parameters(actual, expected) and same_parameters(parameters(r['requested_parameters']), actual),
                'Proposed and executed parameters differ')
        evaluated = SpecificationEvaluator(task.specs).evaluate(r['metrics'], r['metric_units'], r['metric_validity'])
        require(evaluated.valid and evaluated.success == r['success'] and
                math.isclose(evaluated.reward, r['reward'], abs_tol=1e-12) and
                evaluated.violations == r['violations'], 'Reward/feasibility mismatch')
        observation = r['observation']
        require(observation['specs'] == json_value([asdict(s) for s in task.specs]), 'Observation goal changed')
        for key in ('origin', 'status', 'condition', 'metrics', 'metric_units', 'metric_validity', 'job_id'):
            require(observation[key] == r[key], f'Observation differs: {key}')
        job = Path(r['artifact_directory']).resolve()
        export = Path(r['netlist_path']).resolve().parent
        require(job.is_relative_to(self.directory) and export.is_relative_to(self.directory) and
                job.name == r['job_id'] and export.name == r['export_job_id'], 'Wrong artifact identity')
        require(job not in self.jobs and export not in self.exports, 'Reused simulation/export job')
        result, bridge, measured, manifest = (read(job/n) for n in
            ('result.json', 'bridge_result.json', 'measurements.json', 'manifest.json'))
        original = read(export/'manifest.json')
        require(original['job_id'] == r['export_job_id'], 'Wrong original export identity')
        verify_export_files(export, original['files'])
        require(parameters(original['applied_parameters']) == actual ==
                profile.validate_export(original['original_structure_path'], read(export/'readback.json')),
                'Native CDF/export differs from executed parameters')
        for saved in (result, bridge, measured, manifest):
            require(saved['job_id'] == r['job_id'] and saved['origin'] == 'real' and
                    saved['condition'] == r['condition'], 'Simulation artifact context differs')
        require(result['status'] == 'ok' and result['simulator_invocations'] == 1 and
                parameters(result['applied_parameters']) == actual, 'Invalid simulator result')
        for key in ('metrics', 'metric_units', 'metric_validity'):
            require(result[key] == measured[key] == r[key], f'Measurement journal differs: {key}')
        for saved in (original, bridge, manifest):
            require(saved['library'] == self.plan['bindings']['library'] and
                    saved['cell'] == profile.design['testbench_cell'] and
                    saved['model_file'] == self.plan['bindings']['model_file'] and
                    saved.get('analysis_settings') == reference['analysis_settings'], 'Execution binding/policy changed')
        require(measured.get('analysis_settings') == reference['analysis_settings'], 'Measurement policy changed')
        structure = Path(original['structure_path'])
        graph = profile.optimization_graph(structure)
        graph.metadata['simulation_condition'] = r['condition']
        require(observation['graph'] == json_value(asdict(graph)), 'Observation graph differs from native export')
        deck = job/getattr(profile, 'deck_name', 'opamp.scs')
        expected_deck = getattr(profile, 'build_deck', build_deck)(
            structure.read_text(), self.plan['bindings']['model_file'],
            r['condition']['corner']['model_section'], temperature_c=r['condition']['corner']['temperature_c'])
        require(deck.read_text() == expected_deck and file_digest(deck) == r['netlist_sha256'] ==
                result['netlist_sha256'] == bridge['executed_sha256'] == original['executed_sha256'],
                'Executed deck differs from frozen physical policy')
        validate_completion((job/'results/spectre.out').read_text(), bridge['metadata']['returncode'], bridge['errors'])
        {'opamp':check_opamp, 'ldo':check_ldo, 'vco':check_vco}[task.circuit_class](job, r['metrics'])
        if baseline:
            require(r['netlist_sha256'] == reference['deck_sha256'] and r['metrics'] == reference['metrics'] and
                    r['metric_units'] == reference['metric_units'], 'Baseline differs from qualification')
        self.records[r['candidate_id']] = (path, r)
        self.jobs.add(job)
        self.exports.add(export)
        self.versions.add(result['simulator_version'])
        self.counts[task.circuit_class] += 1
        self.state['candidate_records_checked'] = len(self.records)
        self.timings.setdefault(task.circuit_class, []).append(dict(
            candidate_seconds=r['elapsed_seconds'], backend_seconds=result['elapsed_seconds']))
        if len(self.records) % 50 == 0:
            print(f'Verified {len(self.records)} candidate netlists, raw metric packages and rewards', flush=True)
        return r


def check_summary(row, records):
    """Recompute outcome/cost without relying on the runner's summary function."""
    first = next((r for r in records if r['success']), None)
    best = max(records, key=lambda r:r['reward'])
    require(row['success'] == (first is not None) and row['right_censored'] == (first is None) and
            row['first_feasible_call'] == (first['simulation_calls'] if first else None), 'Feasibility summary differs')
    require(row['calls'] == row['call_budget'] == len(records) == row['censor_call'] and
            row['valid_evaluations'] == len(records) and not row['failure_counts'], 'Episode accounting differs')
    for name, key in (('best_reward','reward'), ('best_metrics','metrics'),
                      ('best_metric_units','metric_units'), ('best_parameters','applied_parameters')):
        require(row[name] == best[key], f'Best candidate differs: {name}')
    require(row['duplicate_candidates'] == sum(bool(r['duplicate_of']) for r in records), 'Duplicate count differs')
    elapsed = row['time_to_first_feasible_seconds']
    require((first is None and elapsed is None) or
            (first is not None and 0 <= elapsed <= row['wall_seconds']), 'Invalid feasibility timing')
    require(row['censor_seconds'] == row['wall_seconds'], 'Censor duration differs')


def check_replay(items, phases, permitted, records):
    expected = [p for row in phases for p in row['records'][1:]]
    require([t.record_path for t in items] == expected, 'Replay does not exactly match permitted episode steps')
    observed = set()
    previous = {r:row['records'][i] for row in phases for i,r in enumerate(row['records'][1:])}
    for transition in items:
        transition.validate()
        path, r = records[transition.candidate_id]
        require(str(path) == transition.record_path, 'Replay candidate path differs')
        before = read(previous[transition.record_path])
        require(json_value(asdict(transition.observation)) == before['observation'] and
                json_value(asdict(transition.next_observation)) == r['observation'], 'Replay observation differs from evidence')
        for key in ('proposal', 'reward', 'terminated', 'truncated', 'bootstrap'):
            require(getattr(transition, key) == r[key], f'Replay differs: {key}')
        require(transition.applied_parameters == parameters(r['applied_parameters']), 'Replay executed action differs')
        matches = [t.id for t in permitted if transition.observation.specs == t.specs and
                   graph_contract(transition.observation.graph) == graph_contract(t.graph)]
        require(transition.observation.origin == 'real' and len(matches) == 1, 'Replay leaked across tasks')
        observed.update(matches)
    require(observed == {t.id for t in permitted}, 'Replay missing a permitted class')


def audit_fold(folder, suite, plan, candidates):
    fold = read(folder/'report.json')
    heldout = folder.name
    protocol = checked_protocol(folder/'protocol.json', fold['protocol_sha256'])
    require(protocol['tasks'] == plan['folds'][heldout] and
            protocol['settings']['provenance']['suite_sha256'] == plan['sha256'] and
            protocol['settings']['source_sha256'] == plan['source_sha256'], 'Fold differs from parent protocol')
    require(fold['completed'] and not fold['unexecuted_test_runs'] and not fold['validation_used_for_selection'],
            'Fold incomplete or used validation for selection')
    tasks = {t.id:t for t in suite.tasks(heldout)}
    models, methods, validation_models = benchmark_models(plan['settings'])
    seeds = plan['settings']['seeds']
    train = [t for t in tasks.values() if t.partition == 'train']
    expected_matrix = []
    for seed in seeds:
        expected_matrix.extend((t.id, model+'_pretrain', seed+i) for model in models for i,t in enumerate(train))
        expected_matrix.extend((t.id, model+'_validation_frozen', seed) for t in tasks.values()
                               if t.partition == 'validation' for model in validation_models)
        expected_matrix.extend((t.id, method, seed) for t in tasks.values() if t.partition == 'test' for method in methods)
    require([(r['task'],r['method'],r['seed']) for r in fold['phases']] == expected_matrix, 'Episode matrix/order changed')
    require(list(fold['methods']) == list(methods) and fold['models'] == plan['models'], 'Encoder/method matrix changed')
    updates = 0
    for row in fold['phases']:
        task = tasks[row['task']]
        require(row['completed'] and row['origin'] == 'real' and row['restoration']['state'] == 'restored',
                'Episode incomplete or not restored')
        require((row['partition'],row['circuit_class'],row['transfer']) ==
                (task.partition,task.circuit_class,task.transfer), 'Episode belongs to wrong partition')
        expected_phase = ('pretrain' if task.partition == 'train' else
                          'frozen' if task.partition == 'validation' else methods[row['method']][1])
        require(row['phase'] == expected_phase, 'Episode learning phase differs')
        model_name = (row['method'].split('_',1)[0] if task.partition != 'test' else methods[row['method']][0])
        require(row['model_config'] == (asdict(models[model_name]) if model_name else None),
                'Episode encoder configuration differs')
        records = [candidates.check(p, task, baseline=i == 0) for i,p in enumerate(row['records'])]
        require([r['simulation_calls'] for r in records] == list(range(1,len(records)+1)), 'Call journal discontinuity')
        require([r['step'] for r in records] == list(range(len(records))), 'Step journal discontinuity')
        require([r['observation']['remaining_steps'] for r in records] == list(reversed(range(len(records)))),
                'Observation horizon differs from episode budget')
        require(row['actions'] == [dict(candidate_id=r['candidate_id'],proposal=r['proposal'],source=a['source'])
                                  for r,a in zip(records[1:],row['actions'])] and
                len(row['actions']) == len(records)-1, 'Action history mismatch')
        check_summary(row, records)
        if row['phase'] == 'frozen':
            require(row['weight_before'] == row['weight_after'] and row['updates'] == row['replay_insertions'] == 0,
                    'Frozen policy updated or admitted replay')
        else:
            expected_insertions = (plan['settings']['pretrain_steps']*(train.index(task)+1)
                                   if row['phase'] == 'pretrain' else plan['settings']['test_steps'])
            expected_updates = (plan['settings']['pretrain_steps'] if row['phase'] == 'pretrain' and train.index(task) > 0
                                else len(records)-plan['settings']['batch_size'])
            require(row['updates'] == expected_updates and row['replay_insertions'] == expected_insertions,
                    'Update/replay budget differs')
        updates += row['updates']
        env = Path(row['records'][0]).parent.parent
        require(read(env/'restoration.json') == row['restoration'], 'Restoration journal differs')
        require(row['restoration']['parameters'] == records[0]['applied_parameters'], 'Baseline widths not restored')
        config = read(env/'config.json')
        sha = config.pop('sha256')
        require(sha == hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest() and
                all(r['config_sha256'] == sha for r in records), 'Environment configuration digest mismatch')
    expected_calls = plan['budget']['folds'][heldout]['total']
    require(fold['calls'] == fold['planned_calls'] == fold['real_simulation_calls'] == expected_calls ==
            sum(r['calls'] for r in fold['phases']) and fold['synthetic_calls'] == fold['cache_hits'] ==
            fold['automatic_retries'] == 0, 'Fold call accounting differs')
    require(fold['aggregate'] == aggregate_runs(fold['test_runs']), 'Aggregate differs from target rows')
    expected_checkpoints = {}
    require([(c['seed'],c['model']) for c in fold['pretraining_costs']] ==
            [(seed,model) for seed in seeds for model in models], 'Source checkpoint/cost matrix differs')
    for cost in fold['pretraining_costs']:
        phases = [r for r in fold['phases'] if r['phase'] == 'pretrain' and r['method'] == cost['model']+'_pretrain'
                  and any(r['task'] == t.id and r['seed'] == cost['seed']+i for i,t in enumerate(train))]
        require(len(phases) == len(train) and cost['calls'] == sum(r['calls'] for r in phases) and
                cost['updates'] == sum(r['updates'] for r in phases), 'Source cost differs')
        expected_checkpoints[folder/f'{cost["model"]}-{cost["seed"]}-pretrain.pt'] = (
            train, phases, cost['weight_sha256'], 'pretrain')
    target_phases = [r for r in fold['phases'] if r['partition'] == 'test']
    require(len(target_phases) == len(fold['test_runs']), 'Missing target results')
    for row, phase in zip(fold['test_runs'], target_phases):
        require(all(row[k] == v for k,v in phase.items()), 'Target summary differs from episode')
        if row['upfront_cost']:
            require(row['upfront_cost'] in fold['pretraining_costs'] and
                    row['upfront_cost']['model'] == methods[row['method']][0] and
                    row['upfront_cost']['seed'] == row['seed'] and
                    row['weight_before'] == row['upfront_cost']['weight_sha256'], 'Incorrect transferred weights')
        require(bool(row['upfront_cost']) == (methods[row['method']][0] is not None and row['phase'] != 'scratch'),
                'Missing or unexpected pretraining cost')
        require(row['marginal_online_calls'] == row['calls'] and row['pretraining_plus_online_calls'] ==
                row['calls']+(row['upfront_cost']['calls'] if row['upfront_cost'] else 0), 'Transfer cost differs')
        if row['phase'] in ('scratch','adaptation'):
            expected_checkpoints[folder/f'{row["task"]}-{row["method"]}-{row["seed"]}.pt'] = (
                [tasks[row['task']]], [row], row['weight_after'], row['phase'])
    require(set(folder.glob('*.pt')) == set(expected_checkpoints), 'Checkpoint matrix differs')
    checkpoints = []
    for path,(permitted,phases,expected_weight,phase) in expected_checkpoints.items():
        payload = torch.load(path,map_location='cpu',weights_only=False)
        contract, items = payload['contract'],payload['replay']['items']
        require(contract['model_config'] == phases[0]['model_config'] and contract['config'] == plan['sac_config'],
                'Checkpoint model or SAC settings differ')
        experiment = contract['experiment']
        require(contract['code_sha256'] == plan['source_sha256'] and experiment == dict(
            origin='real', split=phase, designs=[t.id for t in permitted], protocol_sha256=fold['protocol_sha256']),
            'Checkpoint belongs to another experiment')
        check_replay(items, phases, permitted, candidates.records)
        arguments = dict(experiment=experiment, spec_schema=suite.schema,
                         model_config=ModelConfig(**contract['model_config']), config=SACConfig(**contract['config']))
        model,replay,_ = SACLearner.load(path,**arguments)
        require(model.updates == sum(r['updates'] for r in phases) and weight_digest(model) == expected_weight,
                'Checkpoint training state differs')
        require(all(r['parameters'] == sum(p.numel() for module in (model.actor,model.critics)
                                          for p in module.parameters()) for r in phases), 'Parameter count differs')
        for optimizer in ('actor_optimizer','critic_optimizer','alpha_optimizer'):
            states = list(payload[optimizer]['state'].values())
            require(states and all(int(s['step']) == model.updates for s in states),
                    'Optimizer history includes unexpected updates')
        loss = model.update(replay.sample(plan['settings']['batch_size']))
        after = weight_digest(model)
        again,replay2,_ = SACLearner.load(path,**arguments)
        require(again.update(replay2.sample(plan['settings']['batch_size'])) == loss and weight_digest(again) == after,
                'Checkpoint next update is not exact')
        checkpoints.append(dict(path=str(path),sha256=file_digest(path),transitions=len(items),exact_next_update=True))
    return dict(calls=expected_calls,training_updates=updates,checkpoints=checkpoints,
                environments=len(fold['phases']),aggregate=fold['aggregate'])


def audit(directory, progress=print, state=None):
    directory = Path(directory).resolve()
    state = {} if state is None else state
    suite,plan = validate_frozen_plan(ROOT,directory/'suite-protocol.json')
    report = read(directory/'report.json')
    require(report['completed'] and report['all_circuits_and_models_restored'] and
            report['plan_sha256'] == plan['sha256'] and not report['unexecuted_folds'], 'Suite incomplete')
    reference = read(plan['bindings']['final_inspection'])
    for name in ('before.json','after.json'):
        inspection = read(directory/name)
        require(inspection['passed'] and inspection['full_snapshots'] == reference['full_snapshots'] and
                inspection['model_hashes'] == reference['model_hashes'], 'Protected circuit or model changed')
    require(set(report['folds']) == set(plan['folds']), 'Suite fold set differs')
    candidates = CandidateAudit(directory,suite,plan,state)
    folds = {}
    for heldout in suite.definition['heldout']:
        state['current_fold'] = heldout
        folds[heldout] = audit_fold(directory/heldout,suite,plan,candidates)
        state['folds_checked'] = list(folds)
        require(report['folds'][heldout]['completed'] and report['folds'][heldout]['calls'] == folds[heldout]['calls'],
                'Suite/fold counts differ')
        progress(f'Audited {heldout}: {folds[heldout]["calls"]} raw metric packages and '
                 f'{len(folds[heldout]["checkpoints"])} exact checkpoint recoveries',flush=True)
    require([r['circuit_class'] for r in report['final_checks']] == sorted(suite.profiles), 'Missing final baselines')
    for row in report['final_checks']:
        require(row['passed'] and row['calls'] == 1, 'Final baseline incomplete')
        task = next(t for t in suite.tasks(row['circuit_class']) if t.partition == 'test')
        candidates.check(row['record'],task,baseline=True)
        require(read(Path(row['record']).parent.parent/'restoration.json')['state'] == 'restored', 'Final reset not restored')
    require(set(directory.rglob('simulations/*/result.json')) == {p/'result.json' for p in candidates.jobs},
            'Unaccounted simulation artifacts')
    require(set(directory.rglob('candidates/*.json')) == {p for p,r in candidates.records.values()},
            'Unaccounted candidate artifacts')
    require(len(candidates.jobs) == report['calls'] == report['real_simulation_calls'] ==
            report['planned_calls'] == plan['budget']['total_calls'] and
            report['automatic_retries'] == report['cache_hits'] == 0, 'Suite cost differs from plan')
    timings = {name:{key:dict(mean=float(np.mean([r[key] for r in rows])),
                            median=float(np.median([r[key] for r in rows])),
                            p95=float(np.percentile([r[key] for r in rows],95)))
                    for key in rows[0]} for name,rows in candidates.timings.items()}
    checkpoints = [c for f in folds.values() for c in f['checkpoints']]
    return dict(passed=True,plan_sha256=plan['sha256'],new_simulator_calls=0,
                existing_real_calls=len(candidates.jobs),raw_metric_recomputations=len(candidates.jobs),
                calls_by_class=dict(candidates.counts),training_updates=sum(f['training_updates'] for f in folds.values()),
                checkpoint_count=len(checkpoints),checkpoints=checkpoints,
                restored_environments=sum(f['environments'] for f in folds.values())+len(report['final_checks']),
                all_circuits_and_models_restored=True,train_validation_test_isolated=True,
                frozen_weights_unchanged=True,timing_seconds=timings,simulator_versions=sorted(candidates.versions),
                aggregate_by_heldout={k:f['aggregate'] for k,f in folds.items()},
                limits=['Known nominal circuits; not a blind category-generalization test.',
                        'Short pilot; no convergence or encoder-superiority claim.',
                        'Model hashes cover the recorded entry and MOS files, not a recursive PDK digest.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--bridge-site-packages',type=Path,required=True)
    args = parser.parse_args()
    import site
    site.addsitedir(str(args.bridge_site_packages.resolve()))
    started = perf_counter()
    result = dict(passed=False,new_simulator_calls=0)
    try:
        result = audit(args.directory,state=result)
    except BaseException as exc:
        result.update(error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        result['audit_seconds'] = perf_counter()-started
        write_json(args.directory/'audit.json',result)
        print(json.dumps({k:v for k,v in result.items() if k not in ('checkpoints','aggregate_by_heldout')},indent=2))


if __name__ == '__main__':
    main()
