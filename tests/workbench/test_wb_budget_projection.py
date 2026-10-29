"""Synthetic saved-run exports: budget copies carry only fields consumed downstream."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from gator_workbench import aggregates as a


STAMP = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
TRANSFER_FIELDS = {'training_sources', 'circuit_class', 'topology_id', 'generalization_level', 'encoder_type', 'ablation_labels'}


def _before_export(experiment_dir, *, include_mock=None, budgets=None):
    """The prior exporter, including full flat-row copies for each budget checkpoint."""
    experiment_dir = Path(experiment_dir)
    experiment = a.read_dict(experiment_dir / 'experiment.json')
    if include_mock is None:
        include_mock = bool(experiment.get('mock'))
    runs, skipped = a.collect_runs(experiment_dir, include_mock=include_mock)
    rows = [a._flat(run) for run in runs]
    directory = experiment_dir / 'aggregates'
    directory.mkdir(parents=True, exist_ok=True)
    inputs = dict(experiment_id=experiment.get('experiment_id'), include_mock=include_mock, skipped=skipped,
                  runs=[dict(run_id=row['run_id'], relative_run_dir=row['relative_run_dir'],
                             cutoff_commit_seq=row['cutoff_commit_seq'], summary_source=row['summary_source']) for row in rows],
                  contains_mock_data=any(row['provenance'] == 'mock' for row in rows))
    empty = None if rows else ('No eligible runs. ' + ('Mock runs exist but are excluded from real-experiment aggregates.'
                                                       if any('mock' in item.get('reason', '') for item in skipped) else
                                                       'The experiment has no runs yet.'))
    paths = {}
    metric_columns = sorted({f'best_metric:{key}' for row in rows for key in row['best_metrics']})
    for row in rows:
        row.update({f'best_metric:{key}': value for key, value in row['best_metrics'].items()})
    paths['run_summary'] = a._write(directory, 'run_summary', rows, inputs=inputs, explanation=empty, extra_columns=metric_columns)
    budget_rows = []
    for row in rows:
        for budget in sorted(set(budgets or row['budget_checkpoints'] or ([row['max_evaluations']] if row['max_evaluations'] else []))):
            success, status, cost = a.budget_outcome(row, budget)
            budget_rows.append(dict(row, budget=budget, success_within_budget=success, observation_status=status,
                                    cost_evaluations=cost, cost_convention=a.FIRST_FEASIBLE_CONVENTION))
    paths['budget_success'] = a._write(directory, 'budget_success', budget_rows, inputs=inputs,
                                     explanation=empty or 'No budget checkpoints are defined for these runs.')
    grouped = {}
    for row in budget_rows:
        grouped.setdefault((row['task_id'], row['mode'], row['optimizer'], row['method_label'], row['provenance'], row['budget']), []).append(row)
    grouped_rows = [dict(task_id=key[0], mode=key[1], optimizer=key[2], method_label=key[3], provenance=key[4], budget=key[5], runs=len(members),
                         successes=sum(1 for row in members if row['success_within_budget'] is True),
                         failures=sum(1 for row in members if row['success_within_budget'] is False),
                         unknown=sum(1 for row in members if row['observation_status'] == 'unknown'),
                         censored=sum(1 for row in members if row['observation_status'] == 'censored'),
                         run_ids=[row['run_id'] for row in members])
                    for key, members in sorted(grouped.items(), key=lambda item: tuple(map(str, item[0])))]
    paths['budget_success_grouped'] = a._write(directory, 'budget_success_grouped', grouped_rows, inputs=inputs, explanation=empty)
    paths['paired_runs'] = a._write(directory, 'paired_runs', a._paired(rows), inputs=inputs,
                                  explanation=empty or 'No runs share a comparison_pair_id with both a scratch baseline '
                                                       'and a treatment at the same target seed.')
    paths['transfer_summary'] = a._write(directory, 'transfer_summary', a._transfer(budget_rows), inputs=inputs, explanation=empty)
    paths['cumulative_cost'] = a._write(directory, 'cumulative_cost', a._cumulative(rows), inputs=inputs,
                                      explanation=empty or 'No run carries a task_order label.')
    return {name: str(path) for name, path in paths.items()}


def saved_records(count=12, metrics=16, checkpoints=(5, 14, 50)):
    """Invented JSON records, explicitly synthetic/mock even when testing a historical mock flag."""
    result = []
    for index in range(count):
        mode = ('scratch', 'fine_tune', 'frozen')[index % 3]
        first = (4, 18, None, None)[index % 4]
        limit = (25, 25, 25, 7)[index % 4]
        pair = index // 3
        manifest = dict(origin='synthetic', provenance='mock', mock=True, experiment_id='synthetic-experiment',
                        run_id=f'mock-{index:04}', task_id=f'synthetic-task-{pair % 2}', task_name='Synthetic α, "task"\nline',
                        task_definition_hash=f'task-{pair}', initial_dimensions_sha256='synthetic-dimensions',
                        circuit=dict(circuit_class='synthetic-class', topology_id=f'synthetic-topology-{pair % 2}'),
                        mode=mode, seeds=dict(target_seed=pair, pretrain_seed=100 + pair % 2), split='test',
                        generalization_level='unspecified' if index % 5 == 0 else 'unseen_topology',
                        comparison_pair_id=f'synthetic-pair-{pair}', task_order=index + 1,
                        research=dict(method_label='Synthetic method', training_sources=['synthetic-source', 'µ'],
                                      ablation_labels=[] if index % 2 else ['synthetic-ablation'], budget_checkpoints=list(checkpoints)),
                        architecture=dict(optimizer='bayes' if index % 5 == 0 else 'sac',
                                          network=dict(encoder_type='synthetic-encoder', hidden_dim=32)),
                        definitions=dict(reward=dict(version='synthetic')), execution=dict(concurrency=2),
                        budgets=dict(max_evaluations=40), output=dict(relative_run_dir=f'runs/task/mock-{index:04}'))
        source = dict(status='not_applicable', evaluations_charged=None, provenance_chain=[])
        if mode != 'scratch':
            manifest['source_model'] = dict(run_id='mock-source', checkpoint_id='mock-point')
            source = dict(status='known', evaluations_charged=100,
                          provenance_chain=[dict(run_id='mock-source', evaluations_charged=100)])
        summary = dict(origin='synthetic', provenance='mock', status='completed' if first else 'interrupted',
                       stop_reason='budget_exhausted' if first else 'user_pause',
                       first_feasible=None if first is None else dict(first_feasible_eval_count=first, dispatch_index=first + 1),
                       censoring=dict(status='observed' if first is not None else 'right_censored', observation_limit=limit),
                       totals=dict(candidate_evaluations_charged=limit, spectre_launches=limit, failures=1, retries=0, cache_hits=0),
                       time=dict(active_seconds=3.5, paused_seconds=0, sum_job_runtime_seconds=5.0),
                       best_design=dict(evaluation_id=f'synthetic-evaluation-{index}', feasible=first is not None,
                                        normalized_constraint_violation=0 if first is not None else 1.25,
                                        metrics={f'synthetic-metric-{metric}': (index + metric) / 8 for metric in range(metrics)}),
                       source_model_cost=source,
                       output=dict(completeness='complete', resumability='weights_only', data_cursor=dict(commit_seq=index + 17)))
        result.append(dict(manifest=manifest, summary=summary))
    return result


def _saved_experiment(tmp_path, records, *, mock=True):
    """Write an experiment and its run records for budget-projection tests."""
    directory = tmp_path / 'mock' / 'synthetic-experiment'
    directory.mkdir(parents=True)
    (directory / 'experiment.json').write_text(json.dumps(dict(origin='synthetic', provenance='mock', mock=mock,
                                                              experiment_id='synthetic-experiment')), encoding='utf8')
    for record in records:
        run_dir = directory / record['manifest']['output']['relative_run_dir']
        run_dir.mkdir(parents=True)
        for name, data in [('run_manifest', record['manifest']), ('run_summary', record['summary'])]:
            (run_dir / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
    return directory


@pytest.mark.parametrize('scenario', ['normal', 'override', 'empty-override', 'fallback', 'no-budgets', 'mixed-budgets',
                                      'empty-runs', 'excluded-mock', 'historical-mixed-mock-flags', 'wide-metrics'])
def test_all_six_exports_keep_exact_bytes_metadata_and_input_records(tmp_path, monkeypatch, scenario):
    records = saved_records(metrics=80 if scenario == 'wide-metrics' else 16)
    budgets, include_mock = None, None
    if scenario == 'override':
        budgets = [50, 5, 14, 5]
    elif scenario == 'empty-override':
        budgets = []
    elif scenario in ('fallback', 'no-budgets', 'mixed-budgets'):
        for index, record in enumerate(records):
            if scenario != 'mixed-budgets' or index % 2:
                record['manifest']['research']['budget_checkpoints'] = []
                if scenario != 'fallback':
                    record['manifest']['budgets']['max_evaluations'] = None if index % 2 else 0
    elif scenario == 'empty-runs':
        records = []
    elif scenario == 'excluded-mock':
        include_mock = False
    elif scenario == 'historical-mixed-mock-flags':
        include_mock = False
        for index, record in enumerate(records):
            record['manifest']['mock'] = bool(index % 2)
    directory = _saved_experiment(tmp_path, records)
    original_files = {str(path): path.read_bytes() for path in directory.glob('runs/*/*/*.json')}
    monkeypatch.setattr(a, 'utcnow', lambda: STAMP)
    old_paths = _before_export(directory, include_mock=include_mock, budgets=budgets)
    expected = {path.name: path.read_bytes() for path in (directory / 'aggregates').iterdir()}
    new_paths = a.export_aggregates(directory, include_mock=include_mock, budgets=budgets)
    assert old_paths == new_paths and set(new_paths) == set(a.COLUMNS)
    assert {path.name: path.read_bytes() for path in (directory / 'aggregates').iterdir()} == expected
    assert {str(path): path.read_bytes() for path in directory.glob('runs/*/*/*.json')} == original_files
    for name in a.COLUMNS:
        metadata = json.loads(expected[f'{name}.meta.json'])
        assert metadata['generated_utc'] == STAMP.isoformat()
        assert metadata['exporter_version'] == a.EXPORTER_VERSION


def test_budget_rows_keep_exact_consumed_fields_and_release_unneeded_metrics(tmp_path, monkeypatch):
    directory = _saved_experiment(tmp_path, saved_records(metrics=100))
    write, captured = a._write, {}

    def capture(directory, name, rows, **kwargs):
        captured[name] = copy.deepcopy(rows)
        return write(directory, name, rows, **kwargs)

    monkeypatch.setattr(a, '_write', capture)
    _before_export(directory)
    before = captured.copy()
    a.export_aggregates(directory)
    after = captured.copy()
    expected_fields = {name for name, _ in a.COLUMNS['budget_success']} | TRANSFER_FIELDS
    assert len(before['budget_success']) == len(after['budget_success']) == 36
    for old, new in zip(before['budget_success'], after['budget_success']):
        assert set(new) == expected_fields
        assert new == {key: old[key] for key in expected_fields}
        assert len(old) > len(new) + 100
    for name in a.COLUMNS.keys() - {'budget_success'}:
        assert before[name] == after[name]
    assert {row['observation_status'] for row in after['budget_success']} == {'observed', 'unknown', 'censored'}
    assert {row['success_within_budget'] for row in after['budget_success']} == {True, False, None}
