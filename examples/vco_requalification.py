"""Strict-mode requalification of VCO designs first evaluated with the fast policy.

Planning and comparison are offline and read only saved pilot artifacts. Execution
drives one injected backend in reference mode, counts every invocation against the
frozen ceiling and never retries. Feasibility changes are findings, not errors.

This lives outside the analog_optimizer package on purpose: that package's source
digest gates checkpoint loading and revalidation of frozen physical plans.
"""
from __future__ import annotations

import json
from pathlib import Path

from analog_optimizer.backends.backend import SimulationRequest
from analog_optimizer.backends.gpdk045_vco import Gpdk045VcoProfile
from analog_optimizer.backends.virtuoso_bridge import digest as file_digest, write_json
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
from analog_optimizer.evaluation.runtime import BaselineCheck
from analog_optimizer.evaluation.transfer import digest


VERSION = 'm6-vco-requalification-v1'
MANIFEST = 'configs/m6_real_cross_category.json'
SCOPES = ('best', 'feasible')
# Identical to the limits frozen for the fast-policy qualification; not retuned here.
AGREEMENT_LIMITS = {k: ('relative', .001) for k in ('vco_frequency_low_hz', 'vco_frequency_hz',
    'vco_frequency_high_hz', 'vco_tuning_gain_hz_per_v', 'vco_tuning_fraction')}
AGREEMENT_LIMITS.update(supply_power_w=('relative', .005), vco_minimum_swing_v=('absolute', .001),
                        vco_duty_cycle=('absolute', .001), vco_startup_detection_s=('absolute', 2e-9))
STABILITY_LIMITS = dict(vco_max_period_spread=.02, vco_max_window_drift=.01)
# Historical strict jobs needed up to 44 s of a 60 s limit. The limit is not part of the deck.
TIMEOUT_SECONDS = 180.
SOURCE_FILES = ('src/analog_optimizer/backends/gpdk045_vco.py', 'src/analog_optimizer/measurements/vco.py',
                'examples/vco_requalification.py', 'examples/requalify_vco_designs.py',
                MANIFEST, 'configs/gpdk045_vco_design.json', 'configs/gpdk045_vco.json')
INTERPRETATION = (
    'A design is strict-confirmed only if its reference-mode simulation is valid and satisfies every required test specification.',
    'Agreement limits are those frozen for the fast-policy qualification; exceeding one fails this requalification.',
    'A lost or unchanged feasibility verdict is a reported finding and does not fail execution.',
    'With scope "best", a run whose saved design is not confirmed is unconfirmed, not re-scored: its later feasible candidates were not resimulated.',
    'No pilot result, learner or replay is modified; strict results never enter training.')


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_value(value):
    return json.loads(json.dumps(value, allow_nan=False))


def parameters(rows):
    result = {(r['device'], r['parameter']): r['value'] for r in rows}
    require(len(result) == len(rows), 'Repeated parameter identity')
    return result


def load_profile(root, analysis_mode):
    cfg = read(Path(root)/MANIFEST)['classes']['vco']
    require(cfg['analysis_mode'] == 'fast', 'The pilot must have used the qualified fast policy')
    root = Path(root)
    return Gpdk045VcoProfile(analysis_mode=analysis_mode, design_file=root/cfg['design'],
        mapping_file=root/cfg['mapping'], reference_structure=root/cfg['netlist'],
        reference_readback=root/cfg['readback'])


def collect_designs(run_directory, profile, scope='best'):
    """Distinct feasible width assignments with every held-out run that reported them."""
    require(scope in SCOPES, 'Unknown requalification scope')
    run = Path(run_directory).resolve()
    suite, fold, audit = (read(run/p) for p in ('report.json', 'vco/report.json', 'audit.json'))
    require(suite.get('completed') and suite.get('origin') == 'real' and fold.get('completed')
            and fold.get('origin') == 'real' and not fold.get('unexecuted_test_runs'),
            'Completed real pilot required')
    require(audit.get('passed') and audit.get('plan_sha256') == suite.get('plan_sha256'),
            'Pilot artifacts must first pass their independent audit')
    designs = {}
    for test_run in fold['test_runs']:
        require(test_run['circuit_class'] == 'vco' and test_run['partition'] == 'test'
                and test_run['origin'] == 'real', 'Unexpected held-out run')
        records = []
        for name in test_run['records']:
            path = Path(name).resolve()
            require(path.is_relative_to(run), 'Candidate record escapes the pilot directory')
            records.append((path, read(path)))
        feasible = [(call, path, r) for call, (path, r) in enumerate(records, 1) if r['success']]
        require(bool(feasible) == bool(test_run['success']), 'Run success differs from its candidate records')
        if not feasible:
            continue
        call, _, first = feasible[0]
        # Feasible rewards tie at zero and the first is retained, so the saved design is the success claim.
        require(call == test_run['first_feasible_call'] and first['metrics'] == test_run['best_metrics']
                and parameters(first['applied_parameters']) == parameters(test_run['best_parameters']),
                'Saved best design is not the first feasible candidate')
        for call, path, record in (feasible[:1] if scope == 'best' else feasible):
            require(record['status'] == 'ok' and record['origin'] == 'real' and record['state'] == 'completed'
                    and record['evaluation_valid'] and not record['cache_hit'], 'Invalid feasible candidate record')
            assignment = parameters(record['applied_parameters'])
            profile.validate_assignment(assignment)
            job = Path(record['artifact_directory']).resolve()
            require(job.is_relative_to(run), 'Simulation job escapes the pilot directory')
            bridge = read(job/'bridge_result.json')
            require(bridge['analysis_settings'] == profile.analysis_settings
                    and bridge['executed_sha256'] == record['netlist_sha256']
                    and parameters(bridge['applied_parameters']) == assignment, 'Fast execution evidence differs')
            fast = dict(record=str(path), job=str(job), netlist_sha256=record['netlist_sha256'],
                        source_sha256=bridge['source_sha256'], metrics=record['metrics'],
                        metric_units=record['metric_units'], library=bridge['library'], cell=bridge['cell'],
                        model_file=bridge['model_file'], condition=bridge['condition'])
            entry = designs.setdefault(tuple(sorted(assignment.items())),
                                       dict(parameters=record['applied_parameters'], fast=fast, claims=[]))
            require(entry['fast']['metrics'] == fast['metrics'] and entry['fast']['source_sha256'] == fast['source_sha256'],
                    'Identical widths produced different fast evidence')
            entry['claims'].append(dict(method=test_run['method'], seed=test_run['seed'], call=call,
                                        first_feasible=call == test_run['first_feasible_call']))
    width = len(str(len(designs)))
    return [dict(id=f'design-{i:0{max(width, 2)}d}', **designs[key]) for i, key in enumerate(sorted(designs), 1)]


def build_plan(root, run_directory, reference_verification, scope='best'):
    """Deterministic from saved evidence and sources, so a frozen plan can be revalidated."""
    root = Path(root).resolve()
    run, reference_path = Path(run_directory).resolve(), Path(reference_verification).resolve()
    fast, strict = load_profile(root, 'fast'), load_profile(root, 'reference')
    designs = collect_designs(run, fast, scope)
    require(designs, 'No feasible VCO design to requalify')
    connection = {k: designs[0]['fast'][k] for k in ('library', 'cell', 'model_file', 'condition')}
    require(all(d['fast'][k] == v for d in designs for k, v in connection.items()), 'Designs use different bindings')
    reference = read(reference_path)
    stage = reference['stages'][0]
    require(reference['passed'] and reference['origin'] == 'real' and reference.get('timestep_scale', 1.) == 1.
            and reference['analysis_settings'] == strict.analysis_settings and reference['full_snapshot_restored']
            and stage['name'] == 'baseline' and stage['status'] == 'ok' and stage['evaluation_valid']
            and parameters(stage['parameters']) == strict.assignments(), 'Qualified strict baseline evidence required')
    names = ['baseline', *(d['id'] for d in designs), 'restored']
    plan = dict(version=VERSION, scope=scope, manifest_path=MANIFEST, run_directory=str(run),
        purpose='Reference-mode resimulation of feasible held-out VCO designs found with the fast policy',
        reference_verification=str(reference_path),
        pilot=dict(plan_sha256=read(run/'report.json')['plan_sha256'],
                   **{f'{k}_sha256': file_digest(run/p) for k, p in
                      (('suite_report', 'report.json'), ('fold_report', 'vco/report.json'), ('audit', 'audit.json'))}),
        connection=connection, fast_settings=fast.analysis_settings, strict_settings=strict.analysis_settings,
        baseline=dict(parameters=stage['parameters'], metrics=stage['metrics'],
                      netlist_sha256=stage['netlist_sha256'], verification_sha256=file_digest(reference_path)),
        test_specs=read(root/MANIFEST)['classes']['vco']['specs']['test'],
        agreement_limits=AGREEMENT_LIMITS, stability_limits=STABILITY_LIMITS, designs=designs, stages=names,
        planned_calls=len(names), call_cap=len(names), timeout_seconds=TIMEOUT_SECONDS,
        automatic_retries=0, cache_hits=0, training_updates=0, interpretation=INTERPRETATION,
        claims=sum(len(d['claims']) for d in designs),
        source_hashes={name: file_digest(root/name) for name in SOURCE_FILES})
    plan = json_value(plan)
    plan['sha256'] = digest(plan)
    return plan


def freeze_plan(path, plan):
    path = Path(path)
    require(not path.exists(), 'Refusing to overwrite a frozen requalification plan')
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, plan)
    return plan['sha256']


def validate_frozen_plan(root, path):
    saved = read(path)
    require(saved.get('sha256') == digest({k: v for k, v in saved.items() if k != 'sha256'}),
            'Frozen plan digest mismatch')
    current = build_plan(root, saved['run_directory'], saved['reference_verification'], saved['scope'])
    require(current == saved, 'Frozen plan no longer matches code, definitions or pilot evidence')
    return saved


def execute(plan, backend, profile, directory, *, protected=lambda: {}, metadata=None):
    """Baseline, every frozen design, then a restored baseline; one reference-mode call each."""
    require(profile.analysis_settings == plan['strict_settings'] and profile.timestep_scale == 1.,
            'Strict numerical policy differs from the frozen plan')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    specs = tuple(MetricSpec(**s) for s in plan['test_specs'])
    evaluator = SpecificationEvaluator(specs)
    points = ([('baseline', plan['baseline']['parameters'])] + [(d['id'], d['parameters']) for d in plan['designs']]
              + [('restored', plan['baseline']['parameters'])])
    require([name for name, _ in points] == plan['stages'] and len(points) == plan['planned_calls'] <= plan['call_cap'],
            'Stage list differs from the frozen budget')
    report = dict(origin='real', passed=False, plan_sha256=plan['sha256'], planned_calls=len(points),
        calls_attempted=0, confirmed_invocations=0, stages=[], qualification_only=True, training_updates=0,
        timestep_scale=profile.timestep_scale, analysis_settings=profile.analysis_settings, specs=plan['test_specs'],
        **(metadata or {}))
    check = BaselineCheck(plan['baseline']['metrics'], plan['baseline']['netlist_sha256'])
    try:
        before, others = backend.read_cdf_snapshot(), protected()
        write_json(directory/'before.json', dict(vco=before, protected=others))
        try:
            for name, rows in points:
                require(report['calls_attempted'] < plan['call_cap'], 'Frozen call ceiling reached')
                assignment = parameters(rows)
                profile.validate_assignment(assignment)
                backend.set_parameters(assignment)
                artifact = backend.generate_netlist(directory/'exports')
                report['calls_attempted'] += 1
                write_json(directory/'verification.json', report)
                result = backend.run_simulation(SimulationRequest(artifact, directory/'simulations',
                    required_metrics=tuple(s.metric_id for s in specs), parameters=assignment,
                    timeout_seconds=plan['timeout_seconds']))
                report['confirmed_invocations'] += result.simulator_invocations or 0
                evaluation = evaluator.evaluate(result.metrics, result.metric_units, result.metric_validity)
                row = dict(name=name, status=result.status.value, reason=result.reason_code, metrics=result.metrics,
                    metric_units=result.metric_units, metric_validity=result.metric_validity,
                    evaluation_valid=evaluation.valid, test_success=evaluation.success, test_reward=evaluation.reward,
                    test_violations=evaluation.violations, netlist_sha256=artifact.sha256,
                    invocations=result.simulator_invocations, elapsed_seconds=result.elapsed_seconds,
                    job=str(result.artifact_directory), parameters=rows)
                report['stages'].append(row)
                write_json(directory/'verification.json', report)
                if result.simulator_invocations != 1:
                    raise RuntimeError(f'Uncertain simulator invocation at {name}; no automatic retry')
                if name in ('baseline', 'restored'):
                    if result.status.value != 'ok':
                        raise RuntimeError(f'Strict baseline failed at {name}; inspect {result.artifact_directory}')
                    check(row)
                elif result.status.value not in ('ok', 'measurement_error'):
                    raise RuntimeError(f'Strict execution failed at {name}; inspect {result.artifact_directory}')
            report['passed'] = True
        finally:
            backend.restore()
            after, others_after = backend.read_cdf_snapshot(), protected()
            write_json(directory/'after.json', dict(vco=after, protected=others_after))
            report.update(full_snapshot_restored=before == after, protected_circuits_unchanged=others == others_after)
            if before != after or others != others_after:
                report['passed'] = False
                raise RuntimeError('Circuit snapshot restoration failed')
    except BaseException as exc:
        report.update(passed=False, error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_json(directory/'verification.json', report)
    return report


def compare(plan, verification):
    """Offline fast-versus-strict agreement and strict feasibility for every frozen claim."""
    require(verification['plan_sha256'] == plan['sha256'] and verification['passed']
            and verification['analysis_settings'] == plan['strict_settings']
            and verification['confirmed_invocations'] == plan['planned_calls']
            and [s['name'] for s in verification['stages']] == plan['stages'],
            'Verification is not a complete execution of this frozen plan')
    evaluator = SpecificationEvaluator(MetricSpec(**s) for s in plan['test_specs'])
    stages = {s['name']: s for s in verification['stages']}
    rows, runs = [], {}
    for design in plan['designs']:
        stage, fast = stages[design['id']], design['fast']
        require(stage['parameters'] == design['parameters'], 'Executed widths differ from the frozen design')
        bridge = read(Path(stage['job'])/'bridge_result.json')
        require(bridge['source_sha256'] == fast['source_sha256'], 'Physical netlists differ')
        require(bridge['analysis_settings'] == plan['strict_settings'], 'Strict job used another numerical policy')
        row = dict(id=design['id'], parameters=design['parameters'], claims=design['claims'], job=stage['job'],
                   fast_job=fast['job'], strict_status=stage['status'], strict_valid=False, strict_success=False,
                   comparisons=None, agreement_passed=False, strict_violations=None)
        if stage['status'] == 'ok':
            evaluation = evaluator.evaluate(stage['metrics'], stage['metric_units'], stage['metric_validity'])
            require(evaluation.success == stage['test_success'], 'Saved strict feasibility differs')
            comparisons = {}
            for metric, (mode, limit) in AGREEMENT_LIMITS.items():
                a, b = stage['metrics'][metric], fast['metrics'][metric]
                difference = abs(b - a)/(abs(a) if mode == 'relative' else 1.)
                comparisons[metric] = dict(strict=a, fast=b, difference=difference, mode=mode, limit=limit,
                                           passed=difference <= limit)
            stable = all(stage['metrics'][k] <= limit for k, limit in STABILITY_LIMITS.items())
            row.update(strict_valid=evaluation.valid, strict_success=bool(evaluation.valid and evaluation.success),
                comparisons=comparisons, strict_violations=evaluation.violations, stability_passed=stable,
                agreement_passed=stable and all(c['passed'] for c in comparisons.values()),
                principal={k: dict(strict=stage['metrics'][k], fast=fast['metrics'][k])
                           for k in ('vco_frequency_hz', 'supply_power_w')})
        rows.append(row)
        for claim in design['claims']:
            entry = runs.setdefault((claim['method'], claim['seed']), dict(method=claim['method'], seed=claim['seed'],
                fast_success=True, requalified_candidates=0, strict_confirmed_candidates=0,
                first_feasible_confirmed=None, first_strict_feasible_call=None))
            entry['requalified_candidates'] += 1
            if claim['first_feasible']:
                entry['first_feasible_confirmed'] = row['strict_success']
            if row['strict_success']:
                entry['strict_confirmed_candidates'] += 1
                entry['first_strict_feasible_call'] = min(claim['call'], entry['first_strict_feasible_call'] or claim['call'])
    runs = [runs[key] for key in sorted(runs)]
    for entry in runs:
        # Only a complete feasible-candidate scope can re-score a run under the strict policy.
        entry['strict_success'] = entry['strict_confirmed_candidates'] > 0 if plan['scope'] == 'feasible' else None
    methods = {}
    for entry in runs:
        m = methods.setdefault(entry['method'], dict(fast_successes=0, first_feasible_confirmed=0, strict_successes=0))
        m['fast_successes'] += 1
        m['first_feasible_confirmed'] += bool(entry['first_feasible_confirmed'])
        m['strict_successes'] = None if plan['scope'] == 'best' else m['strict_successes'] + bool(entry['strict_success'])
    compared = [r for r in rows if r['comparisons']]
    agreement = bool(rows) and all(r['strict_valid'] and r['agreement_passed'] for r in rows)
    return json_value(dict(passed=agreement, new_simulator_calls=0, plan_sha256=plan['sha256'], scope=plan['scope'],
        designs=len(rows), strict_valid_designs=sum(r['strict_valid'] for r in rows),
        strict_confirmed_designs=sum(r['strict_success'] for r in rows),
        unconfirmed_designs=[r['id'] for r in rows if not r['strict_success']],
        fast_policy_agreement_passed=agreement, limits=AGREEMENT_LIMITS,
        maximum_differences={k: max(r['comparisons'][k]['difference'] for r in compared) for k in AGREEMENT_LIMITS}
                            if compared else {},
        strict_backend_seconds=sum(s['elapsed_seconds'] for s in verification['stages']),
        runs=runs, methods=methods, comparisons=rows))
