"""Data-only aggregate exporters (specification section 11). They rebuild everything from
saved run data: no simulation is launched, nothing is plotted, no report is written.

  run_summary.csv      one row per run
  budget_success.csv   one row per run per evaluation-budget checkpoint (+ grouped counts)
  paired_runs.csv      comparison pairs; ratios only when both sides genuinely succeeded
  transfer_summary.csv grouped transfer statistics WITH links to every contributing run
  cumulative_cost.csv  task order K, de-duplicated source pretraining cost, cumulative success

Every table has a ``<name>.meta.json`` sidecar with its schema, exporter version, input run
set and per-run cutoff sequence number, so it can be regenerated at any time. With no data a
schema-defined EMPTY table plus an explanation is written - never demonstration rows.

A CSV is a derived view of a fixed snapshot; the Parquet tables remain the source of truth.
Mock runs live under a separate root and are excluded from real-experiment aggregates.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from statistics import mean, median

from . import EXPORTER_VERSION
from .layout import RunLayout
from .storage.atomic import publish, read_json, temporary_path, write_json
from .storage.dataset import DatasetReader, utcnow

FIRST_FEASIBLE_CONVENTION = 'evaluations_charged_when_scheduler_confirmed_feasibility_including_in_flight'

COLUMNS = {
    'run_summary': [
        ('experiment_id', 'Experiment'), ('run_id', 'Run'), ('task_id', 'Task identity'), ('task_name', 'Task name'),
        ('circuit_class', 'Circuit class'), ('topology_id', 'Topology/netlist identifier'),
        ('provenance', 'real | mock'), ('mode', 'scratch | fine_tune | frozen (original mode of the run)'),
        ('method_label', 'Research method label'), ('encoder_type', 'Encoder architecture'),
        ('ablation_labels', 'Ablation labels, ;-separated'), ('split', 'train | validation | test | unspecified'),
        ('generalization_level', 'Generalization level label'), ('training_sources', 'Source training set, ;-separated'),
        ('comparison_pair_id', 'Comparison pair'), ('task_order', 'Position K in a fixed task order'),
        ('target_seed', 'Seed of THIS run'), ('pretrain_seed', 'Seed of the SOURCE pretraining run'),
        ('source_run_id', 'Source model run'), ('source_checkpoint_id', 'Source checkpoint'),
        ('source_cost_status', 'known | unknown | declared_by_user | not_applicable'),
        ('source_cost_evaluations', 'Source pretraining cost; empty = unknown, never 0'),
        ('status', 'Final run state'), ('stop_reason', 'Why the run ended'), ('success', 'A feasible design was confirmed'),
        ('first_feasible_eval_count', 'Primary first-feasibility cost; empty = none found'),
        ('first_feasible_dispatch_index', 'dispatch_index of the successful candidate'),
        ('first_feasible_completed_count', 'Evaluations completed at the event'),
        ('first_feasible_in_flight_count', 'Evaluations in flight at the event'),
        ('first_feasible_launches', 'Simulator launches at the event'),
        ('first_feasible_active_seconds', 'Active seconds at the event'),
        ('censoring_status', 'observed | right_censored'), ('observation_limit', 'Evaluations charged when observation ended'),
        ('max_evaluations', 'Configured budget'), ('total_evaluations_charged', 'FINAL cost: evaluations started'),
        ('total_spectre_launches', 'FINAL cost: simulator launches incl. retries/failures'),
        ('failures', 'Failed evaluations'), ('retries', 'Retry attempts'), ('cache_hits', 'Cache hits'),
        ('interrupted_evaluations', 'Charged evaluations lost to a crash'), ('environment_steps', 'Environment steps'),
        ('gradient_updates', 'Learner updates'), ('active_seconds', 'Active wall-clock'), ('paused_seconds', 'Paused wall-clock'),
        ('sum_job_runtime_seconds', 'Summed job runtime (not elapsed time)'), ('concurrency', 'Concurrent jobs'),
        ('best_is_feasible', 'Best design is feasible'), ('best_evaluation_id', 'Best design evaluation'),
        ('best_normalized_violation', 'Best design violation'), ('completeness', 'complete | partial'),
        ('resumability', 'full_state | weights_only | none'), ('summary_source', 'run_summary.json | reconstructed_from_raw_tables'),
        ('cutoff_commit_seq', 'Data snapshot used'), ('relative_run_dir', 'Run directory inside the experiment')],
    'budget_success': [
        ('run_id', 'Run'), ('task_id', 'Task'), ('mode', 'Mode'), ('method_label', 'Method'), ('target_seed', 'Target seed'),
        ('pretrain_seed', 'Pretraining seed'), ('provenance', 'real | mock'), ('budget', 'Evaluation-budget checkpoint B'),
        ('success_within_budget', 'true | false | empty when not known'),
        ('observation_status', 'observed | unknown (budget never reached B by design) | censored (ended early before B)'),
        ('cost_evaluations', 'first_feasible_eval_count when success within B'), ('cost_convention', 'Accounting convention'),
        ('observation_limit', 'Evaluations observed'), ('stop_reason', 'Why observation ended')],
    'budget_success_grouped': [
        ('task_id', 'Task'), ('mode', 'Mode'), ('method_label', 'Method'), ('provenance', 'real | mock'), ('budget', 'B'),
        ('runs', 'Runs in the group'), ('successes', 'Known successes'), ('failures', 'Known failures'),
        ('unknown', 'Unknown'), ('censored', 'Censored'), ('run_ids', 'Contributing runs, ;-separated')],
    'paired_runs': [
        ('comparison_pair_id', 'Pair ID'), ('target_seed', 'Shared target seed'), ('baseline_run_id', 'Baseline (scratch) run'),
        ('treatment_run_id', 'Treatment run'), ('treatment_mode', 'Treatment mode'), ('treatment_method_label', 'Method'),
        ('treatment_pretrain_seed', 'Source pretraining seed of the treatment'),
        ('pairing_criteria', 'Criteria checked'), ('controlled', 'All pairing criteria equal'),
        ('uncontrolled_differences', 'What differs, ;-separated'), ('baseline_success', 'Baseline success'),
        ('treatment_success', 'Treatment success'), ('baseline_first_feasible_eval_count', 'Baseline cost'),
        ('treatment_first_feasible_eval_count', 'Treatment cost'),
        ('step_ratio', 'treatment/baseline; empty unless both succeeded and baseline > 0'),
        ('reduction_fraction', '1 - step_ratio; empty unless computable'), ('outcome_category', 'Failure category'),
        ('baseline_censoring', 'Baseline censoring'), ('treatment_censoring', 'Treatment censoring')],
    'transfer_summary': [
        ('training_sources', 'Source training set'), ('target_circuit_class', 'Target class'),
        ('target_topology_id', 'Target topology'), ('generalization_level', 'Level'), ('mode', 'Mode'),
        ('method_label', 'Method'), ('encoder_type', 'Encoder'), ('ablation_labels', 'Ablations'), ('budget', 'B'),
        ('runs', 'Sample count'), ('successes', 'Known successes'), ('failures', 'Known failures'),
        ('unknown', 'Unknown or censored'), ('mean_cost_of_successes', 'Mean cost of successes'),
        ('median_cost_of_successes', 'Median cost of successes'), ('costs_of_successes', 'Every cost, ;-separated'),
        ('run_ids', 'Links to the original runs, ;-separated')],
    'cumulative_cost': [
        ('stream', 'Method stream: mode | method | source model | pretrain seed | target seed'), ('task_order', 'K'),
        ('run_id', 'Run at position K'), ('task_id', 'Task'), ('mode', 'Mode'), ('method_label', 'Method'),
        ('target_seed', 'Target seed'), ('pretrain_seed', 'Pretraining seed'), ('source_checkpoint', 'run_id/checkpoint_id'),
        ('source_pretraining_cost', 'Source cost of THIS run; empty = unknown'),
        ('target_task_cost', 'Evaluations charged by this run'), ('success', 'Success'),
        ('cumulative_target_cost', 'Sum of target costs up to K'),
        ('cumulative_source_cost_deduplicated', 'Each distinct source run counted once; empty if any is unknown'),
        ('cumulative_total_cost', 'Target + de-duplicated source; empty when not computable'),
        ('total_cost_status', 'computable | non_computable_unknown_source_cost'),
        ('cumulative_success_count', 'Successes up to K'), ('counted_source_runs', 'Distinct source runs counted')],
}


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return ';'.join(str(v) for v in value)
    return str(value)


def _write(directory, name, rows, *, inputs, explanation=None, extra_columns=()):
    columns = [c for c, _ in COLUMNS[name]] + list(extra_columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(column)) for column in columns])
    path = Path(directory) / f'{name}.csv'
    temporary = temporary_path(path)
    temporary.write_text(buffer.getvalue(), encoding='utf8')
    publish(temporary, path)
    write_json(Path(directory) / f'{name}.meta.json', dict(
        table=name, exporter_version=EXPORTER_VERSION, generated_utc=utcnow().isoformat(), rows=len(rows),
        schema=[dict(name=c, description=d) for c, d in COLUMNS[name]]
        + [dict(name=c, description='Best-design physical metric (canonical unit)') for c in extra_columns],
        input_runs=inputs, empty_explanation=explanation if not rows else None,
        null_convention='empty cell = null/unknown. It never means 0, and never means failure.',
        source_of_truth='Parquet raw tables + run JSON files; this CSV is a derived snapshot'))
    return path


# ----------------------------------------------------------------------------- run collection
def reconstruct_from_tables(run_dir, manifest):
    """Rebuild run statistics from the raw evaluations table when run_summary.json is missing."""
    reader = DatasetReader(Path(run_dir) / 'data')
    rows = sorted(reader.rows('evaluations'), key=lambda r: r['commit_seq'])
    first = next((r for r in rows if r['all_hard_constraints_satisfied']), None)
    charged = max((r['cumulative_evaluations_charged'] for r in rows), default=0)
    valid = [r for r in rows if r['valid']]
    best = None
    feasible = [r for r in valid if r['all_hard_constraints_satisfied']]
    if feasible:
        best = feasible[0]
    elif valid:
        best = min(valid, key=lambda r: r['normalized_constraint_violation'])
    return dict(
        status='interrupted', stop_reason='interrupted', mode=manifest.get('mode'),
        first_feasible=None if first is None else dict(
            first_feasible_eval_count=first['cumulative_evaluations_charged'], dispatch_index=first['dispatch_index'],
            completed_count=first['cumulative_completed'], in_flight_count=first['in_flight_at_commit'],
            spectre_launches=first['cumulative_launches'], active_seconds=None),
        censoring=dict(status='observed' if first else 'right_censored', observation_limit=charged),
        totals=dict(candidate_evaluations_charged=charged, spectre_launches=max((r['cumulative_launches'] for r in rows), default=0),
                    failures=sum(1 for r in rows if not r['valid']), retries=sum(max(0, r['attempts'] - 1) for r in rows),
                    cache_hits=sum(1 for r in rows if r['cache_hit']), interrupted_evaluations=None,
                    environment_steps=max((r['global_env_step'] for r in rows), default=0), gradient_updates=None),
        time=dict(active_seconds=None, paused_seconds=None, sum_job_runtime_seconds=None),
        best_design=None if best is None else dict(evaluation_id=best['evaluation_id'],
                                                   feasible=best['all_hard_constraints_satisfied'], metrics={},
                                                   normalized_constraint_violation=best['normalized_constraint_violation']),
        output=dict(completeness='partial', resumability=None, data_cursor=dict(commit_seq=reader.cutoff_seq)),
        source_model_cost=dict(status=(manifest.get('source_model') or {}).get('cost_status'),
                               evaluations_charged=(manifest.get('source_model') or {}).get('cost_evaluations'),
                               provenance_chain=(manifest.get('source_model') or {}).get('provenance_chain', [])),
        _source='reconstructed_from_raw_tables')


def collect_runs(experiment_dir, *, include_mock=False):
    experiment_dir = Path(experiment_dir)
    runs, skipped = [], []
    for manifest_path in sorted(experiment_dir.glob('runs/*/*/run_manifest.json')):
        run_dir = manifest_path.parent
        manifest = read_json(manifest_path, default=None)
        if not manifest:
            skipped.append(dict(run_dir=str(run_dir), reason='unreadable run_manifest.json'))
            continue
        if manifest.get('mock') and not include_mock:
            skipped.append(dict(run_id=manifest.get('run_id'), reason='mock data excluded from real-experiment aggregates'))
            continue
        summary = read_json(RunLayout(run_dir).summary, default=None)
        if summary is None:
            try:
                summary = reconstruct_from_tables(run_dir, manifest)
            except Exception as exc:
                skipped.append(dict(run_id=manifest.get('run_id'), reason=f'no summary and raw tables unreadable: {exc}'))
                continue
        runs.append(dict(run_dir=run_dir, manifest=manifest, summary=summary))
    return runs, skipped


def _flat(run):
    m, s = run['manifest'], run['summary']
    research, first = m.get('research') or {}, s.get('first_feasible')
    totals, time_, best = s.get('totals') or {}, s.get('time') or {}, s.get('best_design')
    source = s.get('source_model_cost') or {}
    return dict(
        experiment_id=m.get('experiment_id'), run_id=m['run_id'], task_id=m.get('task_id'), task_name=m.get('task_name'),
        task_definition_hash=m.get('task_definition_hash'), circuit_class=(m.get('circuit') or {}).get('circuit_class'),
        topology_id=(m.get('circuit') or {}).get('topology_id'), provenance=m.get('provenance'), mode=m.get('mode'),
        method_label=research.get('method_label'), encoder_type=((m.get('architecture') or {}).get('network') or {}).get('encoder_type'),
        ablation_labels=research.get('ablation_labels') or [], split=m.get('split'),
        generalization_level=m.get('generalization_level'), training_sources=research.get('training_sources') or [],
        comparison_pair_id=m.get('comparison_pair_id'), task_order=m.get('task_order'),
        target_seed=(m.get('seeds') or {}).get('target_seed'), pretrain_seed=(m.get('seeds') or {}).get('pretrain_seed'),
        source_run_id=(m.get('source_model') or {}).get('run_id'),
        source_checkpoint_id=(m.get('source_model') or {}).get('checkpoint_id'),
        source_cost_status=source.get('status'), source_cost_evaluations=source.get('evaluations_charged'),
        provenance_chain=source.get('provenance_chain') or [],
        status=s.get('status'), stop_reason=s.get('stop_reason'), success=first is not None,
        first_feasible_eval_count=None if first is None else first['first_feasible_eval_count'],
        first_feasible_dispatch_index=None if first is None else first.get('dispatch_index'),
        first_feasible_completed_count=None if first is None else first.get('completed_count'),
        first_feasible_in_flight_count=None if first is None else first.get('in_flight_count'),
        first_feasible_launches=None if first is None else first.get('spectre_launches'),
        first_feasible_active_seconds=None if first is None else first.get('active_seconds'),
        censoring_status=(s.get('censoring') or {}).get('status'),
        observation_limit=(s.get('censoring') or {}).get('observation_limit'),
        max_evaluations=(m.get('budgets') or {}).get('max_evaluations'),
        total_evaluations_charged=totals.get('candidate_evaluations_charged'),
        total_spectre_launches=totals.get('spectre_launches'), failures=totals.get('failures'),
        retries=totals.get('retries'), cache_hits=totals.get('cache_hits'),
        interrupted_evaluations=totals.get('interrupted_evaluations'), environment_steps=totals.get('environment_steps'),
        gradient_updates=totals.get('gradient_updates'), active_seconds=time_.get('active_seconds'),
        paused_seconds=time_.get('paused_seconds'), sum_job_runtime_seconds=time_.get('sum_job_runtime_seconds'),
        concurrency=(m.get('execution') or {}).get('concurrency'),
        best_is_feasible=None if best is None else best.get('feasible'),
        best_evaluation_id=None if best is None else best.get('evaluation_id'),
        best_normalized_violation=None if best is None else best.get('normalized_constraint_violation'),
        best_metrics={} if best is None else (best.get('metrics') or {}),
        completeness=(s.get('output') or {}).get('completeness'), resumability=(s.get('output') or {}).get('resumability'),
        summary_source=s.get('_source', 'run_summary.json'),
        cutoff_commit_seq=((s.get('output') or {}).get('data_cursor') or {}).get('commit_seq'),
        relative_run_dir=(m.get('output') or {}).get('relative_run_dir'),
        initial_dimensions_sha256=m.get('initial_dimensions_sha256'),
        network=(m.get('architecture') or {}).get('network'), reward=(m.get('definitions') or {}).get('reward'),
        budget_checkpoints=research.get('budget_checkpoints') or [])


def budget_outcome(row, budget):
    """(success_within_budget, observation_status, cost). Early-stopped or under-budgeted runs are
    never turned into failures."""
    first, limit = row['first_feasible_eval_count'], row['observation_limit'] or 0
    if first is not None and first <= budget:
        return True, 'observed', first
    if first is not None or limit >= budget:
        return False, 'observed', None
    if (row['max_evaluations'] or 0) < budget:
        return None, 'unknown', None
    return None, 'censored', None


def export_aggregates(experiment_dir, *, include_mock=None, budgets=None):
    """Write all five tables into <experiment_dir>/aggregates. Returns {table: path}."""
    experiment_dir = Path(experiment_dir)
    experiment = read_json(experiment_dir / 'experiment.json', default={}) or {}
    if include_mock is None:
        include_mock = bool(experiment.get('mock'))     # a mock experiment aggregates its own (labelled) mock runs
    runs, skipped = collect_runs(experiment_dir, include_mock=include_mock)
    rows = [_flat(r) for r in runs]
    directory = experiment_dir / 'aggregates'
    directory.mkdir(parents=True, exist_ok=True)
    inputs = dict(experiment_id=experiment.get('experiment_id'), include_mock=include_mock, skipped=skipped,
                  runs=[dict(run_id=r['run_id'], relative_run_dir=r['relative_run_dir'],
                             cutoff_commit_seq=r['cutoff_commit_seq'], summary_source=r['summary_source']) for r in rows],
                  contains_mock_data=any(r['provenance'] == 'mock' for r in rows))
    empty = None if rows else ('No eligible runs. ' + ('Mock runs exist but are excluded from real-experiment aggregates.'
                                                       if any('mock' in s.get('reason', '') for s in skipped) else
                                                       'The experiment has no runs yet.'))
    paths = {}
    metric_columns = sorted({f'best_metric:{k}' for r in rows for k in r['best_metrics']})
    for r in rows:
        r.update({f'best_metric:{k}': v for k, v in r['best_metrics'].items()})
    paths['run_summary'] = _write(directory, 'run_summary', rows, inputs=inputs, explanation=empty,
                                  extra_columns=metric_columns)
    # ---- budget_success
    budget_rows = []
    for r in rows:
        for budget in sorted(set(budgets or r['budget_checkpoints'] or ([r['max_evaluations']] if r['max_evaluations'] else []))):
            success, status, cost = budget_outcome(r, budget)
            budget_rows.append(dict(r, budget=budget, success_within_budget=success, observation_status=status,
                                    cost_evaluations=cost, cost_convention=FIRST_FEASIBLE_CONVENTION))
    paths['budget_success'] = _write(directory, 'budget_success', budget_rows, inputs=inputs,
                                     explanation=empty or 'No budget checkpoints are defined for these runs.')
    grouped = {}
    for b in budget_rows:
        grouped.setdefault((b['task_id'], b['mode'], b['method_label'], b['provenance'], b['budget']), []).append(b)
    grouped_rows = [dict(task_id=k[0], mode=k[1], method_label=k[2], provenance=k[3], budget=k[4], runs=len(v),
                         successes=sum(1 for x in v if x['success_within_budget'] is True),
                         failures=sum(1 for x in v if x['success_within_budget'] is False),
                         unknown=sum(1 for x in v if x['observation_status'] == 'unknown'),
                         censored=sum(1 for x in v if x['observation_status'] == 'censored'),
                         run_ids=[x['run_id'] for x in v]) for k, v in sorted(grouped.items(), key=lambda i: tuple(map(str, i[0])))]
    paths['budget_success_grouped'] = _write(directory, 'budget_success_grouped', grouped_rows, inputs=inputs, explanation=empty)
    paths['paired_runs'] = _write(directory, 'paired_runs', _paired(rows), inputs=inputs,
                                  explanation=empty or 'No runs share a comparison_pair_id with both a scratch baseline '
                                                       'and a treatment at the same target seed.')
    paths['transfer_summary'] = _write(directory, 'transfer_summary', _transfer(budget_rows), inputs=inputs, explanation=empty)
    paths['cumulative_cost'] = _write(directory, 'cumulative_cost', _cumulative(rows), inputs=inputs,
                                      explanation=empty or 'No run carries a task_order label.')
    return {name: str(path) for name, path in paths.items()}


def _paired(rows):
    result, groups = [], {}
    for r in rows:
        if r['comparison_pair_id'] and r['comparison_pair_id'] != 'unspecified':
            groups.setdefault((r['comparison_pair_id'], r['target_seed']), []).append(r)
    criteria = ['task_definition_hash', 'initial_dimensions_sha256', 'max_evaluations', 'target_seed']
    soft = ['network', 'reward', 'concurrency']
    for (pair_id, seed), members in sorted(groups.items(), key=lambda i: (str(i[0][0]), str(i[0][1]))):
        for base in [m for m in members if m['mode'] == 'scratch']:
            for other in [m for m in members if m['mode'] != 'scratch']:
                differences = [c for c in criteria + soft if base[c] != other[c]]
                both = base['success'] and other['success']
                ratio = None
                if both and base['first_feasible_eval_count']:
                    ratio = other['first_feasible_eval_count'] / base['first_feasible_eval_count']
                category = ('both_succeeded' if both else 'treatment_failed' if base['success'] else
                            'baseline_failed' if other['success'] else 'both_failed')
                result.append(dict(
                    comparison_pair_id=pair_id, target_seed=seed, baseline_run_id=base['run_id'],
                    treatment_run_id=other['run_id'], treatment_mode=other['mode'],
                    treatment_method_label=other['method_label'], treatment_pretrain_seed=other['pretrain_seed'],
                    pairing_criteria=criteria + soft, controlled=not differences, uncontrolled_differences=differences,
                    baseline_success=base['success'], treatment_success=other['success'],
                    baseline_first_feasible_eval_count=base['first_feasible_eval_count'],
                    treatment_first_feasible_eval_count=other['first_feasible_eval_count'], step_ratio=ratio,
                    reduction_fraction=None if ratio is None else 1 - ratio, outcome_category=category,
                    baseline_censoring=base['censoring_status'], treatment_censoring=other['censoring_status']))
    return result


def _transfer(budget_rows):
    groups = {}
    for b in budget_rows:
        key = (';'.join(b['training_sources']) or 'unspecified', b['circuit_class'], b['topology_id'],
               b['generalization_level'], b['mode'], b['method_label'], b['encoder_type'],
               ';'.join(b['ablation_labels']), b['budget'])
        groups.setdefault(key, []).append(b)
    rows = []
    for key, members in sorted(groups.items(), key=lambda i: tuple(map(str, i[0]))):
        costs = [m['cost_evaluations'] for m in members if m['success_within_budget'] is True]
        rows.append(dict(zip(['training_sources', 'target_circuit_class', 'target_topology_id', 'generalization_level',
                              'mode', 'method_label', 'encoder_type', 'ablation_labels', 'budget'], key),
                         runs=len(members), successes=len(costs),
                         failures=sum(1 for m in members if m['success_within_budget'] is False),
                         unknown=sum(1 for m in members if m['success_within_budget'] is None),
                         mean_cost_of_successes=mean(costs) if costs else None,
                         median_cost_of_successes=median(costs) if costs else None, costs_of_successes=costs,
                         run_ids=[m['run_id'] for m in members]))
    return rows


def _cumulative(rows):
    streams = {}
    for r in rows:
        if r['task_order'] is None:
            continue
        root = r['provenance_chain'][-1]['run_id'] if r['provenance_chain'] else 'none'
        key = f"{r['mode']}|{r['method_label']}|source={root}|pretrain_seed={r['pretrain_seed']}|target_seed={r['target_seed']}"
        streams.setdefault(key, []).append(r)
    result = []
    for key, members in sorted(streams.items()):
        counted, source_total, target_total, successes, unknown = {}, 0, 0, 0, False
        for r in sorted(members, key=lambda m: (m['task_order'], m['run_id'])):
            if r['mode'] != 'scratch':
                if r['source_cost_status'] not in ('known', 'declared_by_user'):
                    unknown = True          # an unknown source cost makes every later total non-computable
                for link in r['provenance_chain']:
                    if link['run_id'] not in counted:          # shared pretraining is counted exactly once
                        counted[link['run_id']] = link.get('evaluations_charged')
                        if link.get('evaluations_charged') is None:
                            unknown = True
                        else:
                            source_total += link['evaluations_charged']
                if r['source_cost_status'] == 'declared_by_user' and not r['provenance_chain']:
                    marker = f"declared:{r['source_run_id']}"
                    if marker not in counted:
                        counted[marker] = r['source_cost_evaluations']
                        source_total += r['source_cost_evaluations'] or 0
            target_total += r['total_evaluations_charged'] or 0
            successes += int(bool(r['success']))
            result.append(dict(
                stream=key, task_order=r['task_order'], run_id=r['run_id'], task_id=r['task_id'], mode=r['mode'],
                method_label=r['method_label'], target_seed=r['target_seed'], pretrain_seed=r['pretrain_seed'],
                source_checkpoint=None if not r['source_run_id'] else f"{r['source_run_id']}/{r['source_checkpoint_id']}",
                source_pretraining_cost=r['source_cost_evaluations'], target_task_cost=r['total_evaluations_charged'],
                success=r['success'], cumulative_target_cost=target_total,
                cumulative_source_cost_deduplicated=None if unknown else source_total,
                cumulative_total_cost=None if unknown else source_total + target_total,
                total_cost_status='non_computable_unknown_source_cost' if unknown else 'computable',
                cumulative_success_count=successes, counted_source_runs=sorted(counted)))
    return result


def export_table_csv(run_dir, table, *, cutoff_seq=None):
    """On-demand detailed CSV copy of one raw table into <run>/exports (derived, fixed snapshot)."""
    from .storage.dataset import map_to_dict
    from .storage.tables import TABLES
    import json
    if table not in TABLES:
        raise KeyError(table)
    layout = RunLayout(Path(run_dir))
    reader = DatasetReader(layout.data, cutoff_seq=cutoff_seq)
    columns = [c.name for c in TABLES[table]['columns']]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(columns)
    count = 0
    for row in reader.rows(table):
        cells = []
        for column in TABLES[table]['columns']:
            value = row[column.name]
            if column.type.startswith('map') and value is not None:
                value = json.dumps(map_to_dict(value), allow_nan=False)
            elif column.type.startswith('list') and value is not None:
                value = json.dumps(value, allow_nan=False, default=str)
            cells.append(_cell(value) if not hasattr(value, 'isoformat') else value.isoformat())
        writer.writerow(cells)
        count += 1
    layout.exports.mkdir(parents=True, exist_ok=True)
    path = layout.exports / f'{table}__seq{reader.cutoff_seq}.csv'
    temporary = temporary_path(path)
    temporary.write_text(buffer.getvalue(), encoding='utf8')
    publish(temporary, path)
    write_json(layout.exports / f'{table}__seq{reader.cutoff_seq}.meta.json', dict(
        table=table, rows=count, cutoff_commit_seq=reader.cutoff_seq, exporter_version=EXPORTER_VERSION,
        generated_utc=utcnow().isoformat(), note='Derived copy. Nested cells are JSON. Parquet stays the source of truth.'))
    return path
