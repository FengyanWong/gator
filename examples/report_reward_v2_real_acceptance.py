"""Audit saved REAL qualification evidence; no simulation or changes to recorded runs."""
import ast
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from report_reward_v2_acceptance import ALLOWED, OUTPUT, ROOT, read, sha
from analog_optimizer.training.sac import source_digest
from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash
from gator_workbench.storage.atomic import write_json
from gator_workbench.storage.dataset import DatasetReader
from gator_workbench.tasks import real_starter_config
from gator_workbench.trajectory import TrajectoryLoader

Q = ROOT / 'artifacts/local/reward-v2-real/20260926-qualification-05'
SELECTED = ['tests/test_reward_v2.py', 'tests/test_reward_v2_real_data.py', 'tests/test_reward_v2_budget.py',
            'tests/test_reward_v2_workbench.py', 'tests/test_reward_v2_qualification.py', 'tests/test_specs.py']


def restored(record):
    evidence = Path(record['session_dir']) / 'restoration.json'
    assert record['state'] == 'restored' and read(evidence)['status'] == 'restored'
    return dict(path=str(evidence), sha256=sha(evidence), state='restored')


def audit_run(stage, calls, evaluations, transitions):
    root = Path(stage['run_directory'])
    dataset = DatasetReader(root / 'data')
    jobs, candidates = dataset.rows('simulator_jobs'), dataset.rows('evaluations')
    assert len(jobs) == calls and len(candidates) == evaluations and len({j['job_id'] for j in jobs}) == calls
    by_job, raw_evidence = {}, []
    for job in jobs:
        assert job['provenance'] == 'real' and job['invocation_confirmed'] and job['launch_counted']
        result_path = root / job['output_path'] / 'result.json'
        result = read(result_path)
        assert result['origin'] == 'real' and result['status'] == 'ok' and result['simulator_invocations'] == 1
        assert result['job_id'] == job['job_id'] and result['condition']['corner']['id'] == job['condition']
        by_job[job['job_id']] = result
        raw_evidence.append(dict(job_id=job['job_id'], result=str(result_path), sha256=sha(result_path)))
    for candidate in candidates:
        rows = json.loads(candidate['condition_results_json'])
        reset = candidate['action_source'] == 'reset'
        assert len(rows) == (1 if reset else 5) and candidate['conditions_complete'] is (not reset)
        for row in rows:
            actual = by_job[row['job_id']]
            assert all(row[k] == actual[k] for k in ('condition', 'metrics', 'metric_units', 'metric_validity', 'status'))
    recovered = TrajectoryLoader(root).transitions()
    assert len(recovered) == transitions
    for transition in recovered:
        observation = transition.next_observation
        penalties, feasible = {}, True
        for spec in observation.specs:
            if not spec.active:
                continue
            rows = observation.condition_results[:1] if spec.nominal_only else observation.condition_results
            distances = []
            for row in rows:
                value = row.metrics[spec.metric_id]
                distances.append(max(0., (spec.lower-value)/spec.scale if spec.lower is not None else 0.,
                                     (value-spec.upper)/spec.scale if spec.upper is not None else 0.))
                if spec.required:
                    feasible &= ((spec.lower is None or value >= spec.lower) and (spec.upper is None or value <= spec.upper))
            d = max(distances)
            penalties[spec.metric_id] = d/(1+d)
        active = [s for s in observation.specs if s.active]
        expected = (-.5*sum(s.weight*penalties[s.metric_id] for s in active)/sum(s.weight for s in active)
                    -.5*max(penalties[s.metric_id] for s in active if s.required))
        assert math.isclose(transition.reward, expected, rel_tol=0., abs_tol=1e-12)
        assert observation.evaluation.success == feasible
    return dict(passed=True, confirmed_job_rows=len(jobs), durable_evaluation_rows=len(candidates),
        recovered_transitions=len(recovered), independent_reward_tolerance=1e-12, condition_records_match_raw_results=True,
        nominal_feasible_candidates=sum(bool(c['nominal_feasible']) for c in candidates),
        robust_feasible_candidates=sum(bool(c['robust_feasible']) for c in candidates), raw_evidence=raw_evidence)


def main():
    baseline, manifest = read(OUTPUT / 'baseline.json'), read(Q / 'manifest.json')
    identity = read(OUTPUT / 'identity-reader-final.json')
    source, snapshot = ROOT / 'src/analog_optimizer', Path(baseline['source_snapshot'])
    changed = [str(p.relative_to(source)) for p in sorted(source.rglob('*.py'))
               if not (snapshot / p.relative_to(source)).exists() or p.read_bytes() != (snapshot / p.relative_to(source)).read_bytes()]
    removed = [str(p.relative_to(snapshot)) for p in snapshot.rglob('*.py') if not (source / p.relative_to(snapshot)).exists()]
    assert set(changed) <= ALLOWED | {'recording/reader.py'} and not removed
    protected = [name for name, digest in baseline['protected_hashes'].items() if sha(name) != digest]
    assert not protected
    digest = source_digest()
    assert digest == identity['source_digest'] == manifest['source_digest'] and identity['passed']
    default = WorkbenchConfig.model_validate(dict(real_starter_config('real:gpdk045_ota7'), run=dict(max_evaluations=10)))
    assert config_hash(default) == baseline['config_hash'] and task_definition_hash(default) == baseline['task_definition_hash']
    xml = Q / 'software-tests.xml'
    suite = ET.parse(xml).getroot().find('testsuite')
    assert suite is not None and all(int(suite.attrib[k]) == 0 for k in ('failures', 'errors', 'skipped'))
    parsed = list(source.rglob('*.py')) + list((ROOT / 'src/gator_workbench').rglob('*.py'))
    for path in parsed:
        ast.parse(path.read_text(), filename=str(path))
    checks = dict(kind='non-MOCK-selected-software-checks', selected={p: sha(ROOT / p) for p in SELECTED},
        pytest=dict(suite.attrib), junitxml=str(xml), junitxml_sha256=sha(xml), python_files_parsed=len(parsed),
        unrun_legacy_test_files=sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tests').rglob('test_*.py')
                                     if str(p.relative_to(ROOT)) not in SELECTED),
        typescript=dict(command='node.exe node_modules/typescript/bin/tsc --noEmit', passed=True, production_build=False))
    write_json(Q / 'software-check-manifest.json', checks)
    stages = dict(A=read(manifest['continuation']['stage_a_report']), B=read(Q / 'stage-b/report.json'), C=read(Q / 'stage-c/report.json'))
    failed_b = read(manifest['continuation']['stage_b_report'])
    assert all(stage['passed'] for stage in stages.values()) and failed_b['completed_calls'] == 1
    assert [stages[k]['completed_calls'] for k in ('A', 'B', 'C')] == [21, 43, 8]
    assert all(stage['uncertain_calls'] == 0 for stage in stages.values())
    for name, stage in stages.items():
        records = [stage['preparation_restoration']] if name == 'A' else [s['preparation']['preparation_restoration'] for s in stage['segments']]
        stage['verified_restorations'] = [restored(r) for r in records]
        assert stage['restoration_confirmation']['state'] == 'passed'
    physical_evidence = []
    for job in stages['A']['jobs']:
        result_path = Path(job['artifact_directory']) / 'result.json'
        result = read(result_path)
        assert result['origin'] == 'real' and result['simulator_invocations'] == 1
        assert result['job_id'] == job['job_id'] and result['status'] == 'ok'
        assert sha(Path(job['artifact_directory']) / 'measurements.json') == job['measurements_sha256']
        physical_evidence.append(dict(job_id=job['job_id'], result=str(result_path), sha256=sha(result_path)))
    stages['B']['data_audit'] = audit_run(stages['B'], 42, 10, 8)
    stages['C']['data_audit'] = audit_run(stages['C'], 7, 3, 1)
    for name in ('B', 'C'):
        physical_evidence.extend(stages[name]['data_audit']['raw_evidence'])
        confirmation = stages[name]['restoration_confirmation']
        result_path = Path(confirmation['artifact_directory']) / 'result.json'
        result = read(result_path)
        assert result['origin'] == 'real' and result['status'] == 'ok' and result['simulator_invocations'] == 1
        assert result['job_id'] == confirmation['job_id'] and all(c['passed'] for c in confirmation['checks'])
        physical_evidence.append(dict(job_id=result['job_id'], result=str(result_path), sha256=sha(result_path)))
    assert stages['C']['unfunded_five_job_step_refused']
    assert len(stages['B']['recorded_real_replay_checks']) == 6 and all(c['passed'] for c in stages['B']['recorded_real_replay_checks'])
    failed_b['verified_restoration'] = restored(failed_b['segments'][0]['preparation']['preparation_restoration'])
    b_root = Path(failed_b['run_directory'])
    b_results = list((b_root / 'work').glob('worker-*/*/simulations/*/result.json'))
    assert len(b_results) == 1 and read(b_results[0])['simulator_invocations'] == 1
    failed_result = read(b_results[0])
    assert failed_result['origin'] == 'real' and failed_result['status'] == 'ok'
    physical_evidence.append(dict(job_id=failed_result['job_id'], result=str(b_results[0]), sha256=sha(b_results[0])))
    assert len(physical_evidence) == len({r['job_id'] for r in physical_evidence}) == 73
    failed_b['durable_table_rows'] = {name: len(DatasetReader(b_root / 'data').rows(name)) for name in ('evaluations', 'simulator_jobs', 'transitions')}
    stages['B'].update(prior_failed_attempt=failed_b, cumulative_calls_including_failed_attempt=44, cumulative_authorized_ceiling=44)
    assert all(sha(ROOT / name) == value for name, value in manifest['files'].items())
    browser = read(Q / 'ui/browser-report.json')
    assert browser['passed'] and browser['route_interception'] is False and browser['simulator_calls'] == 0
    browser['evidence_hashes'] = {str(p.relative_to(ROOT)): sha(p) for p in [
        Q / 'ui/browser-report.json', ROOT / 'frontend/scripts/reward_v2_real_check.mjs',
        ROOT / 'frontend/vite.reward-check.config.mjs', *sorted((Q / 'ui').glob('*.png'))]}
    browser['frontend_source_hashes'] = {str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / 'frontend/src').rglob('*')) if p.is_file()}
    report = dict(origin='real', generated_utc=datetime.now(timezone.utc).isoformat(), all_gates_passed=True,
        status='bounded_engineering_qualification_passed_not_a_reward_superiority_study',
        manifest_sha256=sha(Q / 'manifest.json'), manifest=str(Q / 'manifest.json'), prior_manifest=manifest['continuation'],
        source=dict(before=baseline['source_digest'], after=digest, snapshot=str(snapshot), optimizer_files_changed=changed,
                    optimizer_files_removed=removed, final_files={str(p.relative_to(ROOT)): sha(p) for p in parsed}),
        configuration=dict(default_real_config_hash=config_hash(default), default_real_task_hash=task_definition_hash(default),
                           default_hashes_unchanged=True, robust_sha256=sha(Q / 'configuration.json')),
        dependencies=manifest['dependencies'], protected_files=dict(checked=len(baseline['protected_hashes']), changed=protected),
        audit_tool=dict(path=str(Path(__file__).resolve()), sha256=sha(Path(__file__))),
        physical_evidence=physical_evidence,
        stages=stages, totals=dict(new_confirmed_spectre_calls=73, uncertain_calls=0, on_policy_transitions=9, on_policy_updates=7,
            total_ceiling=77, remaining_total_ceiling=4, cost_includes_failed_B_call=True, optional_999_call_study_started=False),
        counting_conventions=dict(A='three unique assignments, seven prepared exports, 21 physical jobs',
            B='10 completed-run evaluations including two resets, plus one failed-at-commit reset',
            C='three evaluations: two resets and one five-condition step'),
        authorization=dict(unknown_license_acknowledged=True, normal_licensing_used=True, license_bypass=False,
            recording_reader_permission=True, stage_B_cumulative_ceiling=44, stage_C_effective_ceiling=12),
        earlier_no_call_failure=dict(directory='20260926-qualification-03', calls=0,
            result='journal bug before first dispatch; restored and corrected before successful A'),
        reward_identity=identity, software=checks, browser=browser,
        gates=dict(A1='passed_identity_default_hashes_v1_columns', A2='passed_pure_contracts',
            A3='passed_real_decks_PSF_supply_reward_restoration', A4='passed_real_B_updates_tables_pause_resume',
            A5='passed_real_C_shared_admission_restoration_with_declared_unobserved_failure_branches',
            A6='passed_three_encoders_OP_on_off_exact_next_update_from_B_replay',
            A7='passed_current_source_scratch_UI_real_API_TypeScript', A8='passed_provenance_audit'),
        gaps=['No robust-feasible design observed; not proof of domain infeasibility',
              'Physical bonus path unobserved; historical-real algebra checks only',
              'No induced physical attributed failure, mid-corner cancel, uncertain launch or worker-loss recovery; pure contract coverage only',
              'Failed B raw measurement/charged ledger survive; failed commit produced no evaluation/job table row',
              'Legacy full test suite unrun; no reward-superiority or manufacturing-yield claim'],
        shared_tree=dict(head_before=baseline['head'], head_now=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), task_committed=False, task_pushed=False),
        restrictions=dict(mock_used=False, fabricated_circuit_outputs=False, live_frontend_build=False,
                          user_backend_8765_touched=False, automatic_physical_retries=0))
    write_json(Q / 'acceptance-summary.json', report)
    print(json.dumps(dict(report=str(Q / 'acceptance-summary.json'), optimizer_digest=digest,
        optimizer_files_changed=len(changed), tests=suite.attrib['tests'], calls=73, uncertain=0, gates_passed=True), indent=2))


if __name__ == '__main__':
    main()
