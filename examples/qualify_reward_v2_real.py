"""Bounded, manifest-pinned reward-v2 qualification against the existing REAL OTA7.

freeze and preflight launch no simulator. No connection repair or mock fallback.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import site
import re
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'artifacts/local/reward-v2-real/20260926-implementation-01/baseline.json'
CORNER_IDS = ['ss_hot_low', 'ff_cold_high', 'fs_nominal', 'sf_nominal']


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    from gator_workbench.storage.atomic import write_json
    write_json(Path(path), data)


def call_counts(jobs):
    return dict(started_calls=len(jobs), completed_calls=sum(j.get('confirmed_calls') or 0 for j in jobs),
                uncertain_calls=sum(j.get('confirmed_calls') is None for j in jobs))


def settings(output):
    directory = output / 'private-settings'
    if not directory.exists():
        directory.mkdir(parents=True)
        shutil.copy2(ROOT / 'configs/local/workbench/bridge_connection.json', directory / 'bridge_connection.json')
    os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = str(directory)
    profile = read(directory / 'bridge_connection.json')['profiles']['lab']
    if profile.get('bridge_site_packages'):
        site.addsitedir(profile['bridge_site_packages'])


def runtime(output):
    from gator_workbench.schema import WorkbenchConfig
    from gator_workbench.tasks import load_task
    from gator_workbench.compile import compile_task
    config = WorkbenchConfig.model_validate(read(output / 'configuration.json'))
    task = load_task(config.circuit, allow_real=True, profile_id='lab')
    compiled = compile_task(config, task.base_graph)
    factory = task.env_factory_builder(compiled, output / 'stage-a/work', config.run)
    return config, task, compiled, factory


def freeze(output, continue_from=None):
    from analog_optimizer.training.sac import source_digest
    from analog_optimizer.backends.virtuoso_bridge import parameter_rows
    from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash
    from gator_workbench.tasks import _verified_profile
    if (output / 'manifest.json').exists():
        raise ValueError('Manifest already exists; do not overwrite frozen provenance')
    baseline = read(BASELINE)
    raw = baseline['config']
    raw['run'].update(connection_profile_id='lab', max_evaluations=10, max_spectre_launches=42,
                      max_retries=0, concurrency=1, stop_at_first_feasible=False, seed=17,
                      reward=dict(violation_shape='compressed', worst_spec_share=.5, objective_weight=0., margin_weight=0.),
                      conditions=dict(policy='always', corners=CORNER_IDS))
    raw['run']['network']['operating_points'] = True
    raw['run']['advanced'].update(episode_length=4, episode_terminates_on_success=False,
                                  warmup_transitions=2, batch_size=2)
    config = WorkbenchConfig.model_validate(raw)
    write(output / 'configuration.json', config.model_dump(mode='json'))
    _, task, compiled, factory = runtime(output)
    profile = _verified_profile('gpdk045_ota7')
    graph = task.base_graph
    base = {g.id: g.value for g in graph.parameter_groups if g.mutable}
    assignments = [dict(name='baseline', values=base)]
    for group in graph.parameter_groups:
        if not group.mutable:
            continue
        values = dict(base)
        values[group.id] += group.step if group.value + group.step <= group.upper else -group.step
        assignments.append(dict(name=group.id + '_one_grid_step', values=values))
    for item in assignments:
        values = graph.assignments(item['values'])
        profile.validate_assignment(values)
        item['parameters'] = parameter_rows(values)
    files = [Path(__file__).resolve(), ROOT / 'docs/plan-reward-v2-real-flow.md', Path(factory.config.creation_receipt)]
    files += [ROOT / p for p in ('configs/gpdk045_ota7.json', 'configs/gpdk045_ota7_design.json',
              'configs/gpdk045_ota7_transfer.json', 'configs/gpdk045_conditions.json',
              'examples/circuits/gpdk045_ota7.scs', 'examples/circuits/gpdk045_ota7.cdf.json')]
    files += list((ROOT / 'src/gator_workbench').rglob('*.py'))
    manifest = dict(origin='real', scope='engineering qualification, not a reward superiority experiment',
        source_digest=source_digest(), baseline_source_digest=baseline['source_digest'],
        dependencies={name: importlib.metadata.version(name) for name in ('torch', 'torch-geometric', 'virtuoso-bridge')},
        files={str(p.relative_to(ROOT)): sha(p) for p in files}, config_hash=config_hash(config),
        task_definition_hash=task_definition_hash(config), configuration_sha256=sha(output / 'configuration.json'),
        connection_profile_id='lab', task_id='real:gpdk045_ota7', graph=asdict(graph), specs=[asdict(s) for s in compiled.specs],
        spec_registry=asdict(compiled.spec_schema), candidates=assignments,
        conditions=[asdict(profile.nominal_condition())] if hasattr(profile, 'nominal_condition') else
                   [dict(corner=asdict(profile.nominal_corner), purpose='nominal', monte_carlo=None)],
        reward=config.run.reward.model_dump(), seed=17, automatic_retries=0,
        license_acknowledgement=dict(unknown_allowed=True, reason_code='license_not_checkable',
            authorization='User follow-up: permit all actions without license. and fix the problem',
            license_bypass=False),
        tolerances=dict(relative=1e-8, references={name: ref for name, _, ref in compiled.spec_schema.metrics},
                        discrete_metrics=['unity_downward_crossings'], validity='exact',
                        formula='abs(a-b) <= 1e-8 * max(abs(a), abs(b), reference)'),
        stopping_rules=['first unresolved correctness/required measurement/budget/restoration failure',
                        'unknown launch: stop and reconcile; never automatically retry',
                        'valid infeasibility does not stop corner evaluation or justify changing targets'],
        stages=dict(A=dict(maximum_launches=21, expected_launches=21, state='not_started'),
                    B=dict(maximum_launches=43, expected_launches=43, state='not_started',
                           episodes=2, steps=4, concurrency=1, training_cap=42, restoration_cap=1),
                    C=dict(maximum_launches=13, expected_launches=8, state='not_started',
                           concurrency=2, training_cap=11, restoration_cap=1)), maximum_launches=77,
        feasibility_required_for_measurement_qualification=False,
        unobserved_physical_success_or_failure_branches='report as coverage gaps; do not fabricate evidence')
    manifest['conditions'] += [asdict(c) for c in factory.corners]
    if continue_from is not None:
        previous = continue_from.resolve()
        old = read(previous / 'manifest.json')
        stage_a, stage_b = read(previous / 'stage-a/report.json'), read(previous / 'stage-b/report.json')
        if (old['source_digest'] != manifest['source_digest'] or not stage_a['passed'] or stage_b['passed'] or
                stage_a['completed_calls'] != 21 or stage_b['completed_calls'] != 1 or
                stage_a['uncertain_calls'] or stage_b['uncertain_calls']):
            raise ValueError('Continuation requires the exact passed A and accounted failed B evidence')
        manifest['continuation'] = dict(directory=str(previous), manifest_sha256=sha(previous / 'manifest.json'),
            stage_a_report=str(previous / 'stage-a/report.json'), stage_a_sha256=sha(previous / 'stage-a/report.json'),
            stage_b_report=str(previous / 'stage-b/report.json'), stage_b_sha256=sha(previous / 'stage-b/report.json'),
            prior_confirmed_calls=22, prior_uncertain_calls=0, prior_B_calls=1,
            authorization='User explicitly approved B cumulative ceiling 44; total remains 77',
            reason='json import fixed in workbench commit; optimizer/measurement source unchanged')
        manifest['stages']['A']['state'] = 'passed_in_prior_manifest'
        manifest['stages']['B'].update(maximum_launches=44, prior_launches=1, expected_launches=44)
        manifest['stages']['C']['maximum_launches'] = 12
    write(output / 'corners.json', dict(origin='real', planned_conditions=manifest['conditions'],
                                      source_sha256=sha(ROOT / 'configs/gpdk045_conditions.json')))
    write(output / 'manifest.json', manifest)
    print(json.dumps(dict(manifest=str(output / 'manifest.json'), sha256=sha(output / 'manifest.json'),
                          source_digest=manifest['source_digest'], maximum_launches=77, physical_calls=0)))


def verify(output):
    from analog_optimizer.training.sac import source_digest
    manifest = read(output / 'manifest.json')
    if source_digest() != manifest['source_digest'] or sha(output / 'configuration.json') != manifest['configuration_sha256']:
        raise RuntimeError('Source/configuration differs from frozen manifest')
    for name, digest in manifest['files'].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError('Frozen file changed: ' + name)
    if previous := manifest.get('continuation'):
        for stage in ('a', 'b'):
            if sha(previous['stage_' + stage + '_report']) != previous['stage_' + stage + '_sha256']:
                raise RuntimeError('Prior physical qualification evidence changed')
    return manifest


def stage_report_path(output, stage):
    manifest = read(output / 'manifest.json')
    if stage == 'A' and manifest.get('continuation'):
        return Path(manifest['continuation']['stage_a_report'])
    return output / ('stage-' + stage.lower()) / 'report.json'


def preflight(output):
    import fcntl
    from gator_workbench.connection import _probe_main
    from gator_workbench.security import redact
    verify(output)
    start = perf_counter()
    lock_path = ROOT / 'artifacts/local/bridge-state/session.lock'
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Existing backend owns the shared Virtuoso session; do not displace it')
    log = output / 'preflight-private.log'
    with log.open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
        _probe_main(['--profile-id', 'lab', '--scope', 'full'])
    result = next(json.loads(line) for line in reversed(log.read_text().splitlines()) if line.startswith('{"layers"'))
    public = dict(origin='real', physical_calls=0, elapsed_seconds=perf_counter() - start,
                  manifest_sha256=sha(output / 'manifest.json'),
                  layers=[dict(name=r.get('layer'), state=r.get('state'), reason=r.get('reason_code'),
                               diagnostic=redact(r.get('diagnostic'), 500)) for r in result['layers']])
    public['unknown_license_acknowledged'] = verify(output)['license_acknowledgement']['unknown_allowed']
    public['passed'] = all(r['state'] in ('ok', 'not_applicable') or
        (public['unknown_license_acknowledged'] and r['name'] == 'spectre_license' and
         r['state'] == 'unknown' and r['reason'] == 'license_not_checkable') for r in public['layers'])
    write(output / 'preflight.json', public)
    print(json.dumps(public, indent=2))
    if not public['passed']:
        raise RuntimeError('REAL prerequisite failed. Stop; no automatic connection repair or alternative backend')


def stage_a(output):
    from analog_optimizer.backends.backend import SimulationRequest
    from analog_optimizer.backends.conditions import SimulationCondition
    from analog_optimizer.backends.native_preparation import NativeCandidateBackend, preparation_session
    from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
    from analog_optimizer.envs.sizing import ConditionResult, same_parameters, write_record
    from analog_optimizer.measurements.specs import SpecificationEvaluator
    from analog_optimizer.measurements.opamp import analyze
    from analog_optimizer.training.workers import WorkerLimits
    from gator_workbench.security import redact
    from fractions import Fraction

    manifest = verify(output)
    if not read(output / 'preflight.json')['passed']:
        raise RuntimeError('A passing real prerequisite report is required')
    directory = output / 'stage-a'
    directory.mkdir(exist_ok=True)
    journal = directory / 'report.json'
    if journal.exists():
        raise RuntimeError('Stage A was already attempted; no automatic retry or overwriting evidence')
    _, task, compiled, factory = runtime(output)
    plan = (SimulationCondition.from_dict(manifest['conditions'][0]),) + tuple(factory.corners)
    parameters = [{(r['device'], r['parameter']): r['value'] for r in c['parameters']}
                  for c in manifest['candidates']]
    evaluator = SpecificationEvaluator(compiled.specs, factory.reward_settings)
    report = dict(origin='real', stage='A', manifest_sha256=sha(output / 'manifest.json'),
        planned_calls=21, maximum_calls=21, started_calls=0, completed_calls=0, uncertain_calls=0,
        planned_candidates=3, candidates=0, resets=0, transitions=0, updates=0, jobs=[], comparisons=[], aggregates=[],
        passed=False, restoration_confirmation='not_started')
    start = perf_counter()

    def save():
        report['wall_seconds'] = perf_counter() - start
        report.update(call_counts(report['jobs']))
        write_record(journal, report)

    def semantic_text(path):
        return '\n'.join(line.strip() for line in Path(path).read_text().splitlines()
                         if line.strip() and not line.lstrip().startswith('//'))

    def compare(left, right, label):
        checks = []
        for spec in compiled.specs:
            key = spec.metric_id
            a, b = left.metrics[key], right.metrics[key]
            reference = manifest['tolerances']['references'][key]
            limit = manifest['tolerances']['relative'] * max(abs(a), abs(b), reference)
            passed = (a == b if key in manifest['tolerances']['discrete_metrics'] else abs(a-b) <= limit)
            checks.append(dict(metric=key, left=a, right=b, limit=limit, passed=passed,
                               validity_equal=left.metric_validity[key] == right.metric_validity[key]))
        item = dict(label=label, left=left.job_id, right=right.job_id, checks=checks,
                    passed=all(c['passed'] and c['validity_equal'] for c in checks))
        report['comparisons'].append(item)
        save()
        if not item['passed']:
            raise RuntimeError('Frozen measurement comparison failed: ' + label)

    def execute(backend, artifact, assignment, label, *, confirmation=False):
        verify(output)
        if len(report['jobs']) >= (21 if confirmation else 20):
            raise RuntimeError('Stage A launch ceiling reached')
        metadata = read(artifact.path.parent / 'manifest.json')
        condition = artifact.condition
        deck = artifact.path.read_text()
        section = re.search(r'^include .+ section=(\w+)$', deck, re.M)
        temperature = re.search(r'^simulatorOptions .* temp=([^ ]+)', deck, re.M)
        if (not section or section[1] != condition.corner.model_section or not temperature or
                float(temperature[1]) != condition.corner.temperature_c or
                sha(metadata['original_structure_path']) != metadata['original_structure_sha256'] or
                sha(artifact.path) != artifact.sha256):
            raise RuntimeError('Executed deck/provenance does not match its condition')
        backend.get_circuit_graph(artifact)
        row = dict(label=label, state='launch_intent', condition=asdict(condition),
                   export_manifest=str(artifact.path.parent / 'manifest.json'), deck_sha256=artifact.sha256,
                   confirmed_calls=None)
        report['jobs'].append(row)
        save()  # Durable intent precedes the physical invocation; unresolved calls are never free.
        result = backend.run_simulation(SimulationRequest(artifact, directory / 'simulations',
            required_metrics=evaluator.required_metrics, timeout_seconds=factory.timeout_seconds,
            parameters=assignment, condition=condition))
        row.update(state='returned', job_id=result.job_id, status=result.status.value,
                   confirmed_calls=result.simulator_invocations, reason=result.reason_code,
                   artifact_directory=str(result.artifact_directory))
        save()
        if result.simulator_invocations != 1 or result.status.value != 'ok' or not result.candidate_evaluated:
            raise RuntimeError('Physical qualification stopped: ' + label + ': ' + result.reason_code)
        if result.condition != condition or not same_parameters(result.applied_parameters, assignment):
            raise RuntimeError('Result condition/parameter identity mismatch')
        measured = read(result.artifact_directory / 'measurements.json')
        reparsed = getattr(factory.profile, 'analyze', analyze)(result.artifact_directory,
            result_name='bridge_result.json', mos_names=factory.profile.mos_names)
        if measured != reparsed or any(not result.metric_validity.get(k) for k in evaluator.required_metrics):
            raise RuntimeError('Required measurement or independent PSF reparse mismatch')
        supply = measured['dc']['VDD']
        if not math.isclose(supply, condition.corner.supply_v, rel_tol=1e-8, abs_tol=0.):
            raise RuntimeError('Measured supply differs from the frozen condition')
        row.update(measured_supply_v=supply, psf_reparse_equal=True,
                   measurements_sha256=sha(result.artifact_directory / 'measurements.json'), state='qualified')
        save()
        print(json.dumps(dict(stage='A', label=label, confirmed_calls=report['completed_calls'],
                              status=result.status.value, measured_supply_v=supply)), flush=True)
        return result

    def aggregate(results, label):
        rows = tuple(ConditionResult(r.condition, r.status.value, r.candidate_evaluated,
                    r.metrics, r.metric_units, r.metric_validity, r.job_id, r.reason_code,
                    r.operating_points or {}) for r in results)
        verdict = evaluator.evaluate_conditions(rows, planned_conditions=plan)
        # Independent rational arithmetic on measured values, with actual-bound verdicts.
        penalties, passed = {}, True
        for spec in compiled.specs:
            if not spec.active:
                continue
            applicable = results[:1] if spec.nominal_only else results
            distances = []
            for result in applicable:
                value = result.metrics[spec.metric_id]
                terms = [Fraction(0)]
                if spec.lower is not None:
                    terms.append((Fraction(spec.lower)-Fraction(value))/Fraction(spec.scale))
                if spec.upper is not None:
                    terms.append((Fraction(value)-Fraction(spec.upper))/Fraction(spec.scale))
                distances.append(max(terms))
                if spec.required:
                    passed &= ((spec.lower is None or value >= spec.lower) and
                               (spec.upper is None or value <= spec.upper))
            distance = max(distances)
            penalties[spec.metric_id] = float(distance/(1+distance))
        weighted = sum(s.weight*penalties[s.metric_id] for s in compiled.specs if s.active)
        total = sum(s.weight for s in compiled.specs if s.active)
        expected = -.5*weighted/total - .5*max(penalties[s.metric_id] for s in compiled.specs if s.active and s.required)
        valid = (verdict.valid and verdict.complete and verdict.success == passed and
                 math.isclose(verdict.reward, expected, rel_tol=0., abs_tol=1e-12) and
                 all(math.isclose(verdict.violations[k], v, rel_tol=0., abs_tol=1e-12) for k, v in penalties.items()))
        report['aggregates'].append(dict(candidate=label, evaluation=asdict(verdict),
            independently_computed_reward=expected, independently_computed_success=passed, passed=valid))
        save()
        if not valid:
            raise RuntimeError('Independent reward/verdict check failed: ' + label)

    save()
    try:
        with preparation_session(factory.config, factory.profile, WorkerLimits(), report) as preparation:
            with NativeCandidateBackend(factory.config, factory.profile, preparation) as backend:
                base, _ = backend.prepare_candidate(directory / 'exports', parameters[0], candidate_id='baseline')
                report['candidates'] += 1
                first = execute(backend, base, parameters[0], 'baseline_nominal_1')
                repeat = execute(backend, base, parameters[0], 'baseline_nominal_2')
                compare(first, repeat, 'nominal_repeat')
                derived, artifacts = [], []
                for condition in plan[1:]:
                    artifact = backend.derive_condition_artifact(base, directory / 'exports', condition=condition)
                    artifacts.append(artifact)
                    derived.append(execute(backend, artifact, parameters[0], 'derived_' + condition.corner.id))
                aggregate([first] + derived, 'baseline')
                for condition, original, previous in zip(plan[1:], artifacts, derived):
                    fresh, _ = backend.prepare_candidate(directory / 'exports', parameters[0],
                        candidate_id='fresh_' + condition.corner.id)
                    artifact = backend.derive_condition_artifact(fresh, directory / 'exports', condition=condition)
                    deck_equal = semantic_text(original.path) == semantic_text(artifact.path)
                    old, new = (read(a.path.parent / 'manifest.json') for a in (original, artifact))
                    structure_equal = semantic_text(old['structure_path']) == semantic_text(new['structure_path'])
                    report['comparisons'].append(dict(label='fresh_export_' + condition.corner.id,
                        passed=deck_equal and structure_equal, deck_equal=deck_equal, structure_equal=structure_equal,
                        independent_original_exports=old['original_structure_path'] != new['original_structure_path']))
                    save()
                    if not deck_equal or not structure_equal:
                        raise RuntimeError('Independent export semantic deck comparison failed')
                    current = execute(backend, artifact, parameters[0], 'fresh_' + condition.corner.id)
                    compare(previous, current, 'derived_vs_fresh_' + condition.corner.id)
                for candidate, assignment in zip(manifest['candidates'][1:], parameters[1:]):
                    base, _ = backend.prepare_candidate(directory / 'exports', assignment, candidate_id=candidate['name'])
                    report['candidates'] += 1
                    results = [execute(backend, base, assignment, candidate['name'] + '_nominal')]
                    for condition in plan[1:]:
                        artifact = backend.derive_condition_artifact(base, directory / 'exports', condition=condition)
                        results.append(execute(backend, artifact, assignment, candidate['name'] + '_' + condition.corner.id))
                    aggregate(results, candidate['name'])
        if report['preparation_restoration']['state'] != 'restored':
            raise RuntimeError('Preparation owner did not confirm restoration')
        with VirtuosoBridgeBackend(factory.config, factory.profile) as backend:
            if not same_parameters(backend.read_parameters(), parameters[0]):
                raise RuntimeError('Restored schematic differs from the baseline')
            restored = backend.generate_netlist(directory / 'restored-exports')
            confirmation = execute(backend, restored, parameters[0], 'restored_nominal', confirmation=True)
            compare(first, confirmation, 'restored_baseline')
            report['restoration_confirmation'] = dict(state='passed', job_id=confirmation.job_id)
        report['passed'] = True
    except BaseException as exc:
        report['failure'] = dict(type=type(exc).__name__, diagnostic=redact(str(exc), 1000))
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'preflight', 'stage_a'])
    parser.add_argument('output', type=Path)
    parser.add_argument('--continue-from', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings(output)
    if args.operation == 'freeze':
        freeze(output, args.continue_from)
    else:
        if args.continue_from is not None:
            parser.error('--continue-from is only valid for freeze')
        globals()[args.operation](output)


if __name__ == '__main__':
    main()
