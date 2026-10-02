"""Free B4 calibration with independent upstream re-simulation of EVERY passing design.

No provider code is imported. The original two upstream testbenches are separate
ngspice processes. Any value/verdict disagreement stops the entire calibration;
already-running candidates finish and remain recorded. No automatic retries.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
import multiprocessing
from pathlib import Path
import random
import shutil
import subprocess
import time
import os
from uuid import uuid4

from analog_optimizer.backends.backend import SimulationRequest
from analog_optimizer.evaluation.benchmark import PatternSearch
from analog_optimizer.measurements.specs import SpecificationEvaluator
from analog_optimizer.parameters import ActionMapper
from analog_optimizer.training.sac import source_digest
from gator_workbench.analoggym import AnalogGymBackend, evaluate_outputs, validate_benchmark_config
from gator_workbench.compile import compile_task, hard_constraints, reward_settings
from gator_workbench.ngspice_backend import NgspiceLink
from gator_workbench.ngspice_tasks import parse_entry
from gator_workbench.schema import WorkbenchConfig
from gator_workbench.storage.atomic import read_json, write_json
from check_analoggym import original_deck

_STOP = None


def initialize_worker(stop):
    global _STOP
    _STOP = stop


def metric_differences(upstream, observed):
    differences = []
    for key in sorted(set(upstream) | set(observed)):
        expected, actual = upstream.get(key), observed.get(key)
        equal = key in upstream and key in observed and (
            actual is expected if actual is None or expected is None else
            abs(actual - expected) <= 1e-9 * abs(expected))
        if not equal:
            differences.append(dict(metric=key, upstream=expected, gator=actual))
    return differences


def verify_pass(bundle, values, observed, directory, *, timeout=120):
    directory.mkdir(parents=True, exist_ok=False)
    evidence = dict(passed=False, gator_passed=True, upstream_passed=None,
                    simulator_processes=0, differences=[], error=None, tolerance_relative=1e-9)
    try:
        codes = []
        for kind in ('ACDC', 'Tran'):
            deck = directory / (kind + '.cir')
            deck.write_text(original_deck(bundle, kind, values))
            evidence['simulator_processes'] += 1
            with (directory / (kind + '.log')).open('w') as log:
                result = subprocess.run(['ngspice', '-b', deck.name], cwd=directory,
                                        stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            codes.append(result.returncode)
        metrics, passed, _ = evaluate_outputs(bundle, directory, values)
        evidence.update(upstream_metrics=metrics, upstream_passed=passed, upstream_exit_codes=codes)
        evidence['differences'] = metric_differences(metrics, observed)
        if not passed:
            evidence['differences'].append(dict(verdict=True, upstream=False, gator=True))
        evidence['passed'] = not evidence['differences']
    except Exception as exc:
        evidence['error'] = f'{type(exc).__name__}: {exc}'[:1000]
    write_json(directory / 'verification.json', evidence)
    return evidence


def run_calibration(directory, output, scratch, method, seed, count, stop=None, *, timeout=120, resume=False):
    stop = _STOP if stop is None else stop
    entry = read_json(directory / 'task.json')
    bundle = entry['analoggym']
    run_id = f'{bundle["name"]}-{method}-{seed}'
    destination = output / run_id / 'result.json'
    previous = read_json(destination) if destination.exists() else None
    if previous and not resume:
        raise ValueError(f'Calibration evidence already exists: {destination}')
    config = WorkbenchConfig.model_validate(read_json(directory / 'config.json'))
    validate_benchmark_config(config, bundle)
    text = (directory / 'netlist.cir').read_text()
    compiled = compile_task(config, parse_entry(entry, text).graph)
    mapper = ActionMapper(compiled.graph)
    evaluator = SpecificationEvaluator(compiled.specs, reward_settings(config))
    pattern = PatternSearch(mapper.groups)
    rng = random.Random(seed)
    backend = AnalogGymBackend(text, compiled.graph, NgspiceLink('ngspice_local'), bundle=bundle,
                               device_kinds=entry['device_kinds'])
    report = dict(run_id=run_id, attempt_id=uuid4().hex, circuit=bundle['name'], method=method, seed=seed, requested_evaluations=count,
                  completed=False, success=False, first_feasible=None, best_feasible=None, designs=[],
                  simulator_processes=0, verification_processes=0, passing_designs=0, verified_passes=0,
                  fixed_bias_currents=bundle['fixed_native_values'], reward_settings=asdict(evaluator.settings),
                  configuration_sha256=hashlib.sha256((directory/'config.json').read_bytes()).hexdigest(),
                  retries=0, llm_calls=0, error=None)
    if previous:
        for key in ('configuration_sha256','run_id','requested_evaluations','fixed_bias_currents','reward_settings'):
            if previous[key] != report[key]:
                raise ValueError(f'Cannot resume calibration with changed {key}')
        if previous['error'] or previous['passing_designs'] != previous['verified_passes'] or any(
                'disagree' in (row['error'] or '') for row in previous['designs']):
            raise ValueError('Cannot resume after a calibration failure or unresolved passing-design parity')
        report = previous
        # Replay only proposal-generator state, never simulations or optimizer learning.
        for index, row in enumerate(report['designs']):
            proposal = None if index == 0 else pattern.propose() if method == 'pattern' else {
                key:rng.uniform(-1,1) for key in mapper.group_ids}
            if row['index'] != index or row['proposal'] != proposal:
                raise ValueError('Calibration proposal journal differs from its frozen seed/schedule')
            if method == 'pattern':
                pattern.observe(proposal,row.get('reward'))
        passing = [d for d in report['designs'] if (d.get('verification') or {}).get('passed')]
        if passing:
            first=passing[0]
            report['best_feasible']=dict(index=first['index'],native_values=first['native_values'],
                clearance_margin=first['clearance_margin'],probes=first['metrics'],probe_units=first['metric_units'],
                native_probes=first['native_metrics'],metrics_descriptive_only=True)
        if report['completed']:
            write_json(destination,report)
            return report
    started = time.monotonic() - report.get('elapsed_seconds',0)
    backend.connect()
    try:
        for index in range(len(report['designs']),count):
            if stop.is_set():
                break
            proposal = None if index == 0 else pattern.propose() if method == 'pattern' else {
                key: rng.uniform(-1, 1) for key in mapper.group_ids}
            if proposal is not None:
                backend.set_parameters(mapper.legalize(proposal).assignments)
            values = backend.native_values()
            work = scratch / run_id / str(index)
            verdict = False
            item = dict(index=index, native_values=values, proposal=proposal, error=None,
                        gator_passed=False, verification=None)
            try:
                artifact = backend.generate_netlist(work / 'gator')
                backend.get_circuit_graph(artifact)
                result = backend.run_simulation(SimulationRequest(artifact, work / 'gator',
                    timeout_seconds=timeout, parameters=backend.parameters, condition=artifact.condition))
                report['simulator_processes'] += result.simulator_invocations or 0
                native = read_json(result.artifact_directory / 'benchmark.json')
                evaluated = evaluator.evaluate_conditions((result,))
                valid, feasible, violations, violation = hard_constraints(
                    compiled.targets, result.metrics, result.metric_validity)
                verdict = result.status.value in ('ok', 'measurement_error') and feasible
                item.update(valid=valid and result.status.value in ('ok', 'measurement_error'),
                            normalized_constraint_violation=violation, spec_violations=violations,
                            status=result.status.value, reward=evaluated.reward if evaluated.valid else None,
                            gator_passed=verdict, metrics=result.metrics, metric_units=result.metric_units,
                            native_metrics=native['native_metrics'], upstream_on_imported_outputs=native['upstream_passed'],
                            clearance_margin=evaluated.clearance_margin,
                            analysis_counts=read_json(result.artifact_directory / 'analysis-counts.json'))
                # A false negative also invalidates parity; never silently continue it.
                if verdict != native['upstream_passed'] or verdict != evaluated.success:
                    item['error'] = 'GATOR/upstream verdict disagreement on imported outputs'
                    stop.set()
                if verdict:
                    report['passing_designs'] += 1
                    verification = verify_pass(bundle, values, native['native_metrics'], work/'upstream', timeout=timeout)
                    item['verification'] = verification
                    report['verification_processes'] += verification['simulator_processes']
                    if not verification['passed']:
                        stop.set()
                        item['error'] = 'Independent upstream re-simulation disagrees; calibration stopped'
                    else:
                        report['verified_passes'] += 1
                        report['success'] = True
                        if report['first_feasible'] is None:
                            report['first_feasible'] = dict(evaluation=index+1, seconds=time.monotonic()-started)
                        best = report['best_feasible']
                        # Feasibility-only rewards tie at zero: workbench keeps the earliest.
                        if best is None:
                            report['best_feasible'] = dict(index=index, native_values=values,
                                clearance_margin=evaluated.clearance_margin, probes=result.metrics,
                                probe_units=result.metric_units, native_probes=native['native_metrics'],
                                metrics_descriptive_only=True)
                if method == 'pattern':
                    pattern.observe(proposal, item['reward'])
                if not result.candidate_evaluated:
                    item['error'] = result.error_summary or 'Candidate was not evaluated'
            except Exception as exc:
                item['error'] = f'{type(exc).__name__}: {exc}'[:1000]
                stop.set()  # Unexpected harness failures never produce a partial success claim.
            item['elapsed_seconds'] = time.monotonic()-started
            report['designs'].append(item)
            report['elapsed_seconds'] = item['elapsed_seconds']
            write_json(destination, report)
            if item['error'] or verdict:
                # Keep all passing rechecks and failure evidence; discard only this run's large nonpassing waves.
                pass
            else:
                shutil.rmtree(work)
        report['completed'] = len(report['designs']) == count and not stop.is_set()
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'[:1000]
        stop.set()
    finally:
        backend.close()
        report['elapsed_seconds'] = time.monotonic()-started
        write_json(destination, report)
    return report


def summarize(reports, expected, stop):
    circuits = []
    for name in sorted({r['circuit'] for r in reports}):
        rows = [r for r in reports if r['circuit']==name]
        random_runs = [r for r in rows if r['method']=='random']
        pattern_runs = [r for r in rows if r['method']=='pattern']
        nr = sum(r['success'] for r in random_runs)
        np = sum(r['success'] for r in pattern_runs)
        complete = len(random_runs)==5 and len(pattern_runs)==3 and all(r['completed'] for r in rows)
        circuits.append(dict(circuit=name, completed=complete, random_successes=nr, random_runs=len(random_runs),
            pattern_successes=np, pattern_runs=len(pattern_runs),
            eligible=not any(r.get('error') or any(d.get('error') and 'disagree' in d['error']
                             for d in r['designs']) for r in rows)))
    selected = [r['circuit'] for r in circuits if r['eligible']][:3]
    return dict(status='stopped' if stop.is_set() else 'complete' if len(reports)==expected else 'running',
        expected_runs=expected, completed_runs=sum(r['completed'] for r in reports), circuits=circuits,
        selected_circuits=selected, selection_satisfied=len(selected)==3,
        selection_rule='B3 import/domain/parity eligibility only; no short-run success requirement; first three alphabetically. LDO excluded by B3.',
        candidate_evaluations=sum(len(r['designs']) for r in reports),
        simulator_processes=sum(r['simulator_processes'] for r in reports),
        upstream_verification_processes=sum(r['verification_processes'] for r in reports),
        passing_designs=sum(r['passing_designs'] for r in reports),
        independently_verified_passes=sum(r['verified_passes'] for r in reports),
        parity_disagreements=[dict(run=r['run_id'], index=d['index'], error=d['error']) for r in reports
                             for d in r['designs'] if d['error'] and ('disagree' in d['error'])],
        runs=[{k:v for k,v in r.items() if k!='designs'} for r in reports],
        scoring='feasibility_only', after_feasible_objective=None, optimizer_source_digest=source_digest(),
        fixed_currents_for_every_arm=True, llm_calls=0, paid_requests_authorized=False,
        pattern_repeat_note='Deterministic common starting design; three seed labels are not independent trajectories.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--settings',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scratch',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--resume',action='store_true',help='Continue journals with identical frozen config/seeds; never resume a parity disagreement')
    args=p.parse_args()
    plan=read_json(args.plan)
    calibration=plan['calibration']
    if args.workers != calibration['workers']:
        p.error('Worker count differs from the frozen calibration plan')
    for key,value in calibration.get('simulator_environment', {}).items():
        if os.environ.get(key) != value:
            p.error(f'{key} must be {value!r} as recorded in the calibration plan')
    for name in calibration['eligible_after_parity']:
        directory=args.settings/'ngspice'/('analoggym_'+name)
        for filename,expected in plan['frozen_import_sha256'][name].items():
            if hashlib.sha256((directory/filename).read_bytes()).hexdigest() != expected:
                p.error(f'Frozen benchmark file changed: {name}/{filename}')
        validate_benchmark_config(WorkbenchConfig.model_validate(read_json(directory/'config.json')),
                                  read_json(directory/'task.json')['analoggym'])
    jobs=[(name,method,seed) for method in ('random','pattern') for seed in calibration[method+'_seeds']
          for name in calibration['eligible_after_parity']]
    context=multiprocessing.get_context('spawn')
    stop=context.Event()
    reports=[]
    errors=[]
    with ProcessPoolExecutor(max_workers=args.workers,mp_context=context,
                             initializer=initialize_worker,initargs=(stop,)) as pool:
        futures={pool.submit(run_calibration, args.settings/'ngspice'/('analoggym_'+name),
            args.output,args.scratch,method,seed,calibration['evaluations_per_run'],resume=args.resume):(name,method,seed)
            for name,method,seed in jobs}
        for future in as_completed(futures):
            try:
                report=future.result()
                reports.append(report)
                print(json.dumps({k:v for k,v in report.items() if k not in ('designs','best_feasible')}),flush=True)
            except Exception as exc:
                stop.set()
                error=dict(job=futures[future],fatal=str(exc))
                errors.append(error)
                print(json.dumps(error),flush=True)
            write_json(args.output/'summary.json',dict(summarize(reports,len(jobs),stop),fatal_errors=errors))
    summary=summarize(reports,len(jobs),stop)
    write_json(args.output/'summary.json',dict(summary,fatal_errors=errors))
    if stop.is_set():
        raise SystemExit('Calibration stopped. See summary.json and per-run evidence.')


if __name__=='__main__':
    main()
