"""Matched sizing experiments through the workbench's actual scheduler.

Controls never instantiate a provider. Fake/replay replies must be supplied explicitly.
Real AI requires --authorize-llm plus ceilings in the configuration; this flag is not
user approval by itself. Only use it after the operator has approved that slice.
All outputs, including failures and degraded/steered runs, remain separate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter

from analog_optimizer.parameters import ActionMapper
from analog_optimizer.search import FakeClient, ReplayClient, RandomProposer, SeededProposer
from gator_workbench import runs, tasks
from gator_workbench.compile import compile_task
from gator_workbench.engine import RunEngine, RunLock
from gator_workbench.paths import OutputRoots
from gator_workbench.schema import SearchSettings, WorkbenchConfig
from gator_workbench.storage import DatasetReader
from gator_workbench.storage.atomic import read_json, read_jsonl, write_json
from llm_sizing_evidence import PassingDesignVerifier, constraint_progress, validate_comparison, summarize_comparison

ARMS = ('sac', 'matched_random', 'matched_seeded', 'llm_warmstart', 'llm', 'sac_llm_rescue')


def run_arm(config, arm, output, *, client=None, authorize_llm=False, authorize_ngspice=False, plan=None):
    # One comparison output root owns its stop marker and serial execution lock.
    lock = RunLock(Path(output) / '.comparison.lock')
    lock.acquire()
    try:
        return _run_arm(config, arm, output, client=client, authorize_llm=authorize_llm,
                        authorize_ngspice=authorize_ngspice, plan=plan)
    finally:
        lock.release()


def _run_arm(config, arm, output, *, client=None, authorize_llm=False, authorize_ngspice=False, plan=None):
    if arm not in ARMS:
        raise ValueError('Unknown benchmark arm')
    if not os.environ.get('GATOR_WORKBENCH_SETTINGS_DIR'):
        raise ValueError('Set a scratch GATOR_WORKBENCH_SETTINGS_DIR before preparing a benchmark')
    if (Path(output) / 'comparison-STOP.json').exists():
        raise ValueError('Comparison stopped by independent verification; resolve the recorded disagreement first')
    config = config.model_copy(deep=True)
    config.output.output_root = str(Path(output).resolve())
    config.run.mode, config.run.concurrency, config.run.stop_at_first_feasible = 'scratch', 1, False
    config.run.model_source = type(config.run.model_source)()
    control = arm if arm.startswith('matched_') else None
    if arm == 'sac':
        config.run.search = SearchSettings()
    elif control:
        config.run.search = config.run.search.model_copy(update=dict(method='llm_warmstart', provider=None,
            model=None, effort=None, max_llm_calls=1, max_llm_notional_usd=None, hints_allowed=False))
    else:
        config.run.search = config.run.search.model_copy(update=dict(method=arm, hints_allowed=False))
        if client is None and not authorize_llm:
            raise ValueError('Real AI is disabled. Supply FakeClient/ReplayClient or an explicitly approved ceiling.')
    config = WorkbenchConfig.model_validate(config.model_dump(mode='json'))
    task = tasks.load_task(config.circuit, allow_real=authorize_ngspice, profile_id=config.run.connection_profile_id)
    if not task.mock and task.connection_family != 'ngspice':
        raise ValueError('This driver permits only MOCK or free local ngspice, never Virtuoso/Spectre')
    benchmark_bundle = None
    if (task.circuit or {}).get('analoggym_task'):
        from gator_workbench.analoggym import validate_benchmark_config
        from gator_workbench.ngspice_tasks import load
        entry, _ = load(config.circuit.task_id.removeprefix('ngspice:'))
        benchmark_bundle = entry['analoggym']
        validate_benchmark_config(config, benchmark_bundle)
        validate_comparison(config, benchmark_bundle, plan)
        reference = WorkbenchConfig.model_validate(dict(entry['starter'], run=dict(max_evaluations=60)))
        if config.parameters != reference.parameters:
            raise ValueError('Comparison parameter domain must match the imported fixed-bias domain')
        if config.run.reward != reference.run.reward:
            raise ValueError('Comparison reward settings must match the unchanged calibration reward')
        if [t.model_dump(mode='json') for t in config.targets] != [t.model_dump(mode='json') for t in reference.targets]:
            raise ValueError('Comparison targets must match the imported upstream pass rule')
    proposer = None
    if control:
        mapper = ActionMapper(compile_task(config, task.base_graph).graph)
        adv = config.run.advanced
        count = config.run.search.warm_start_count or max(8, adv.batch_size, adv.warmup_transitions)
        proposer = (RandomProposer(mapper.group_ids, seed=config.run.seed) if arm == 'matched_random'
                    else SeededProposer(mapper, count, seed=config.run.seed))
    roots = OutputRoots(extra_roots=[str(Path(output).resolve())])
    from gator_workbench.connection import ConnectionMonitor
    layout, manifest = runs.prepare_run(config, roots, allow_real=authorize_ngspice, benchmark_control=control,
                                        monitor=ConnectionMonitor() if not task.mock else None)
    manifest['benchmark_arm'] = arm
    manifest['benchmark_verification_required'] = benchmark_bundle is not None
    manifest['benchmark_notes'] = dict(plain_sac_schedule='unchanged online updates during random warm-up',
        llm_only_episode='one baseline then one long episode; zero learner updates',
        matched_controls='same W/U handover, bounds, reward, SAC and episode resets as the LLM warm-start arm')
    write_json(layout.manifest, manifest)
    if benchmark_bundle is not None:
        write_json(layout.run_dir / 'comparison-plan.json', plan)
    verifier = PassingDesignVerifier(benchmark_bundle, layout.run_dir, output,
        timeout=config.run.advanced.simulation_timeout_seconds) if benchmark_bundle is not None else None
    started = perf_counter()
    engine = RunEngine(layout.run_dir, task=task, llm_client=client, seed_proposer=proposer,
                       lock=runs.take_lock(layout.run_dir), evaluation_observer=verifier)
    state = engine.run()
    elapsed = perf_counter() - started
    reader = DatasetReader(layout.data)
    evaluations, parameters, updates, calls = (reader.rows(n) for n in ('evaluations','parameters','learner_updates','llm_calls'))
    designs = {}
    for row in parameters:
        if row['role'] == 'independent':
            designs.setdefault(row['evaluation_id'], {})[row['variable_id']] = row['executed_value']
    seen, repeats = set(), 0
    for row in evaluations:
        key = tuple(sorted(designs.get(row['evaluation_id'], {}).items()))
        repeats += key in seen
        seen.add(key)
    live = read_jsonl(layout.run_dir / 'llm/live.jsonl')
    jobs = reader.rows('simulator_jobs')
    analyses = [json.loads(j['analysis'].removeprefix('ngspice:')) for j in jobs
                if (j.get('analysis') or '').startswith('ngspice:')]
    analysis_counts = Counter()
    for entry in analyses:
        analysis_counts.update(entry['commands'])
    summary = read_json(layout.summary)
    best_id = summary.get('best_feasible_evaluation_id')
    metric_rows = reader.rows('metrics')
    probe_rows = [r for r in metric_rows if r['evaluation_id'] == best_id]
    progress = constraint_progress(evaluations, metric_rows, budget=config.run.max_evaluations)
    verification = verifier.summary() if verifier is not None else dict(required=False, failed=False, simulator_processes=0)
    if verifier is not None:
        passing = sum(bool(e['all_hard_constraints_satisfied']) for e in evaluations)
        verification['complete'] = passing == verification['verified_passes'] and not verification['failed']
        verification['failed'] = not verification['complete'] or verifier.stop_file.exists()
    search_state = engine.search.status() if engine.search else {}
    write_json(layout.run_dir / 'constraint-progress.json', progress)
    result = dict(arm=arm, seed=config.run.seed, provider=config.run.search.provider if not control else None,
        run_dir=str(layout.run_dir), state=state, elapsed_seconds=elapsed,
        configuration=config.model_dump(mode='json'), summary=summary,
        constraint_progress=progress, verification=verification,
        success=best_id is not None and not verification['failed'],
        comparison_qualified=not verification['failed'],
        budget_reached=len(evaluations)==config.run.max_evaluations,
        steered=bool(search_state.get('steered')), degraded=bool(search_state.get('degraded')),
        verification_seconds=verification.get('elapsed_seconds', 0.),
        search_and_learning_seconds=elapsed-verification.get('elapsed_seconds', 0.),
        total_simulator_launches=engine.ledger.launches+verification['simulator_processes'],
        best_feasible_probes=None if best_id is None or verification['failed'] else dict(evaluation_id=best_id,
            metrics_descriptive_only=True, rows=probe_rows),
        source_counts=dict(Counter(e['action_source'] for e in evaluations)), resets=sum(e['action_source']=='reset' for e in evaluations),
        duplicate_evaluations=repeats, duplicate_rate=repeats/len(evaluations) if evaluations else None,
        initial_updates=sum(u['update_phase']=='initial' for u in updates),
        online_updates=sum(u['update_phase']!='initial' for u in updates),
        initial_training_seconds=sum(u['update_seconds'] for u in updates if u['update_phase']=='initial'),
        llm_calls=len(calls), input_tokens=sum(r['input_tokens'] for r in calls) if calls and all(r['input_tokens'] is not None for r in calls) else None,
        output_tokens=sum(r['output_tokens'] for r in calls) if calls and all(r['output_tokens'] is not None for r in calls) else None,
        notional_cost_usd=sum(r['notional_cost_usd'] for r in calls) if calls and all(r['notional_cost_usd'] is not None for r in calls) else None,
        llm_latency_seconds=sum(r['latency_seconds'] or 0 for r in calls),
        llm_waiting_seconds=engine.search.waiting_seconds() if engine.search else 0.,
        simulator_launches=engine.ledger.launches, retries=engine.ledger.retries,
        analysis_commands_observed=dict(analysis_counts),
        analyses=sum(a['analyses'] for a in analyses) if analyses and len(analyses)==len(jobs)
            and all(a['complete'] for a in analyses) else None,
        analysis_accounting_complete=bool(analyses) and len(analyses)==len(jobs) and all(a['complete'] for a in analyses),
        unused_suggestions=sum(e['type']=='unused' for e in live),
        note='Latency is call duration, including overlap with SAC in rescue; it is not all blocked waiting time.')
    write_json(layout.run_dir / 'benchmark-result.json', result)
    if control and calls:
        raise AssertionError('A numeric control recorded an LLM call')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--arm', choices=ARMS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan', type=Path, help='Required frozen v2 plan for AnalogGym comparisons')
    parser.add_argument('--fake-replies', type=Path)
    parser.add_argument('--replay-records', type=Path)
    parser.add_argument('--authorize-llm', action='store_true')
    parser.add_argument('--authorize-ngspice', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('GATOR_WORKBENCH_SETTINGS_DIR', tempfile.mkdtemp(prefix='gator-sizing-benchmark-settings-'))
    if args.fake_replies and args.replay_records:
        parser.error('Choose either fake replies or replay records')
    client = FakeClient(read_json(args.fake_replies)) if args.fake_replies else ReplayClient(read_json(args.replay_records)) if args.replay_records else None
    result = run_arm(WorkbenchConfig.model_validate(read_json(args.config)), args.arm, args.output,
                     client=client, authorize_llm=args.authorize_llm, authorize_ngspice=args.authorize_ngspice,
                     plan=read_json(args.plan) if args.plan else None)
    summaries = [read_json(p) for p in sorted(args.output.rglob('benchmark-result.json'))]
    current = [r for r in summaries if 'constraint_progress' in r and 'verification' in r]
    write_json(args.output / 'comparison-summary.json', dict(summarize_comparison(current),
        legacy_results_not_pooled=len(summaries)-len(current)))
    print(json.dumps({k: result[k] for k in ('arm', 'state', 'run_dir', 'llm_calls', 'initial_updates', 'online_updates')}))


if __name__ == '__main__':
    main()
