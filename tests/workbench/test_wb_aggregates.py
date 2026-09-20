"""Five research CSV exports rebuilt from saved data, on a full MOCK workflow: two small tasks,
several seeds, scratch / fine_tune / frozen. These tests exercise accounting and plumbing only;
they establish nothing about algorithmic generalization."""
import csv
import json
from pathlib import Path

import pytest

from gator_workbench import aggregates, runs
from gator_workbench.storage import read_json
from helpers import execute, make_config, roots_for, summary


def table(experiment_dir, name):
    with (Path(experiment_dir) / 'aggregates' / f'{name}.csv').open(newline='') as stream:
        return list(csv.DictReader(stream))


def meta(experiment_dir, name):
    return read_json(Path(experiment_dir) / 'aggregates' / f'{name}.meta.json')


@pytest.fixture(scope='module')
def workflow(tmp_path_factory):
    root = tmp_path_factory.mktemp('workflow')
    labels = lambda **k: dict(dict(experiment_group='g1', budget_checkpoints=[5, 14, 50]), **k)
    source, _ = execute(make_config(root, 'synthetic:opamp', run=dict(max_evaluations=20, seed=100),
                                    project=dict(task_name='source_opamp'),
                                    research=labels(split='train', method_label='Pretraining')), root)
    experiment_id = read_json(source.manifest)['experiment_id']
    out = dict(experiment_id=experiment_id)
    made = dict(source=source)
    for order, (task, name, threshold) in enumerate([('synthetic:ldo', 'target_ldo', 0.9),
                                                     ('synthetic:opamp_two_stage', 'target_two_stage', 1.5)], start=1):
        for seed in (1, 2):
            pair = f'{name}-seed{seed}'
            common = dict(split='test', generalization_level='unseen_topology', training_sources=['opamp'],
                          comparison_pair_id=pair, task_order=order)
            made[name, 'scratch', seed], _ = execute(make_config(
                root, task, threshold=threshold, run=dict(max_evaluations=14, seed=seed), output=out,
                project=dict(task_name=name), research=labels(method_label='Scratch', **common)), root)
            for mode, label in (('fine_tune', 'Pretrained-Fine-tuned'), ('frozen', 'Pretrained-Frozen')):
                config = make_config(root, task, threshold=threshold, run=dict(max_evaluations=14, seed=seed, mode=mode),
                                     output=out, project=dict(task_name=name), research=labels(method_label=label, **common))
                config.run.model_source.run_dir = str(source.run_dir)
                made[name, mode, seed], _ = execute(config, root, confirm_transfer=True)
    return root, source.experiment_dir, made


def test_full_mock_workflow_completed(workflow):
    _, experiment_dir, made = workflow
    assert len(made) == 13 and all(summary(layout)['status'] == 'completed' for layout in made.values())
    experiment = read_json(experiment_dir / 'experiment.json')
    assert experiment['mock'] is True and len(experiment['runs']) == 13
    assert (experiment_dir / 'data_dictionary.json').is_file()


def test_run_summary_csv_has_one_row_per_run_with_costs_kept_apart(workflow):
    _, experiment_dir, made = workflow
    rows = table(experiment_dir, 'run_summary')
    assert len(rows) == 13 and len({r['run_id'] for r in rows}) == 13
    assert {r['mode'] for r in rows} == {'scratch', 'fine_tune', 'frozen'} and {r['provenance'] for r in rows} == {'mock'}
    for row in rows:
        s = next(summary(l) for l in made.values() if summary(l)['run_id'] == row['run_id'])
        assert int(row['total_evaluations_charged']) == s['totals']['candidate_evaluations_charged']
        if row['success'] == 'true':
            assert int(row['first_feasible_eval_count']) == s['first_feasible_eval_count'] <= int(row['total_evaluations_charged'])
            assert row['censoring_status'] == 'observed'
        else:                                       # null stays empty: never the budget, never 0
            assert row['first_feasible_eval_count'] == '' and row['censoring_status'] == 'right_censored'
    transfer = [r for r in rows if r['mode'] != 'scratch']
    assert all(r['pretrain_seed'] == '100' and r['target_seed'] in ('1', '2') for r in transfer)   # seeds kept apart
    assert all(r['source_cost_evaluations'] == '20' and r['source_cost_status'] == 'known' for r in transfer)
    assert all(r['source_cost_status'] == 'not_applicable' and r['source_cost_evaluations'] == '' for r in rows if r['mode'] == 'scratch')
    assert any(k.startswith('best_metric:score') for k in rows[0])                      # best PHYSICAL metric columns
    info = meta(experiment_dir, 'run_summary')
    assert info['rows'] == 13 and info['exporter_version'] and len(info['input_runs']['runs']) == 13
    assert all(r['cutoff_commit_seq'] for r in info['input_runs']['runs']) and info['input_runs']['contains_mock_data']


def test_budget_success_distinguishes_observed_unknown_and_censored(workflow):
    _, experiment_dir, _ = workflow
    rows = table(experiment_dir, 'budget_success')
    assert len(rows) == 13 * 3
    for row in rows:
        budget, limit = int(row['budget']), int(row['observation_limit'])
        if budget == 50 and row['success_within_budget'] != 'true':
            assert row['success_within_budget'] == '' and row['observation_status'] == 'unknown'   # budget never reached 50
        if row['success_within_budget'] == 'true':
            assert int(row['cost_evaluations']) <= budget and row['observation_status'] == 'observed'
        if row['success_within_budget'] == 'false':
            assert row['cost_evaluations'] == '' and row['observation_status'] == 'observed' and limit >= budget or row['cost_evaluations'] == ''
    infeasible = [r for r in rows if 'two_stage' in r['task_id'] and r['budget'] == '14']
    assert infeasible and all(r['success_within_budget'] == 'false' for r in infeasible)
    grouped = table(experiment_dir, 'budget_success_grouped')
    for group in grouped:
        total = sum(int(group[k]) for k in ('successes', 'failures', 'unknown', 'censored'))
        assert total == int(group['runs']) == len(group['run_ids'].split(';'))


def test_budget_outcome_rules():
    base = dict(first_feasible_eval_count=None, observation_limit=10, max_evaluations=40)
    assert aggregates.budget_outcome(dict(base, first_feasible_eval_count=7), 8) == (True, 'observed', 7)
    assert aggregates.budget_outcome(dict(base, first_feasible_eval_count=9), 8) == (False, 'observed', None)
    assert aggregates.budget_outcome(base, 10) == (False, 'observed', None)
    assert aggregates.budget_outcome(base, 25) == (None, 'censored', None)        # stopped early: NOT a failure
    assert aggregates.budget_outcome(dict(base, max_evaluations=10), 25) == (None, 'unknown', None)   # insufficient budget


def test_paired_runs_compute_ratios_only_for_two_real_successes(workflow):
    _, experiment_dir, _ = workflow
    rows = table(experiment_dir, 'paired_runs')
    assert len(rows) == 8                                # 2 tasks x 2 seeds x 2 treatments, each against its scratch run
    for row in rows:
        both = row['baseline_success'] == 'true' and row['treatment_success'] == 'true'
        if both:
            expected = int(row['treatment_first_feasible_eval_count']) / int(row['baseline_first_feasible_eval_count'])
            assert float(row['step_ratio']) == pytest.approx(expected)
            assert float(row['reduction_fraction']) == pytest.approx(1 - expected) and row['outcome_category'] == 'both_succeeded'
        else:
            assert row['step_ratio'] == '' and row['reduction_fraction'] == ''      # null, category preserved
            assert row['outcome_category'] in ('treatment_failed', 'baseline_failed', 'both_failed')
        assert row['controlled'] == 'true' and row['uncontrolled_differences'] == ''
        assert row['treatment_pretrain_seed'] == '100'
    assert any(r['outcome_category'] == 'both_failed' for r in rows)                # the infeasible task


def test_uncontrolled_pairs_are_not_presented_as_controlled():
    base = dict(run_id='a', mode='scratch', comparison_pair_id='p', target_seed=1, success=True, first_feasible_eval_count=0,
                task_definition_hash='t', initial_dimensions_sha256='i', max_evaluations=20, network=dict(layers=1),
                reward='r', concurrency=1, method_label='Scratch', pretrain_seed=None, censoring_status='observed')
    other = dict(base, run_id='b', mode='fine_tune', first_feasible_eval_count=4, concurrency=4, network=dict(layers=2))
    row, = aggregates._paired([base, other])
    assert row['controlled'] is False and row['uncontrolled_differences'] == ['network', 'concurrency']
    assert row['step_ratio'] is None                      # zero denominator => null, never a division error or inf


def test_transfer_summary_keeps_links_to_every_run(workflow):
    _, experiment_dir, _ = workflow
    rows = table(experiment_dir, 'transfer_summary')
    assert rows
    for row in rows:
        ids = row['run_ids'].split(';')
        assert int(row['runs']) == len(ids) == int(row['successes']) + int(row['failures']) + int(row['unknown'])
        costs = [c for c in row['costs_of_successes'].split(';') if c]
        assert len(costs) == int(row['successes'])                 # per-run costs, not only a mean
    ldo = [r for r in rows if r['target_circuit_class'] == 'ldo' and r['mode'] == 'fine_tune' and r['budget'] == '14']
    assert len(ldo) == 1 and ldo[0]['training_sources'] == 'opamp' and ldo[0]['runs'] == '2'


def test_cumulative_cost_counts_shared_pretraining_once(workflow):
    _, experiment_dir, _ = workflow
    rows = table(experiment_dir, 'cumulative_cost')
    stream = [r for r in rows if r['mode'] == 'fine_tune' and r['target_seed'] == '1']
    assert [r['task_order'] for r in stream] == ['1', '2']
    assert [r['source_pretraining_cost'] for r in stream] == ['20', '20']
    assert [r['cumulative_target_cost'] for r in stream] == ['14', '28']
    assert [r['cumulative_source_cost_deduplicated'] for r in stream] == ['20', '20']      # NOT 40
    assert [r['cumulative_total_cost'] for r in stream] == ['34', '48'] and stream[-1]['total_cost_status'] == 'computable'
    scratch = [r for r in rows if r['mode'] == 'scratch' and r['target_seed'] == '1']
    assert [r['cumulative_total_cost'] for r in scratch] == ['14', '28'] and scratch[0]['cumulative_source_cost_deduplicated'] == '0'
    assert len({r['stream'] for r in rows}) == 6                   # seeds/models are separate streams, never pooled


def test_unknown_source_cost_makes_totals_non_computable_never_zero():
    link = dict(run_id='src', evaluations_charged=None)
    rows = [dict(run_id=f'r{k}', task_order=k, mode='fine_tune', method_label='FT', pretrain_seed=None, target_seed=1,
                 task_id='t', provenance_chain=[link], source_cost_status='unknown', source_cost_evaluations=None,
                 source_run_id='src', source_checkpoint_id='c', total_evaluations_charged=10, success=True) for k in (1, 2)]
    result = aggregates._cumulative(rows)
    assert [r['cumulative_total_cost'] for r in result] == [None, None]
    assert [r['cumulative_source_cost_deduplicated'] for r in result] == [None, None]
    assert {r['total_cost_status'] for r in result} == {'non_computable_unknown_source_cost'}
    assert [r['cumulative_target_cost'] for r in result] == [10, 20]            # what IS known is still reported


def test_tables_regenerate_identically_from_saved_data(workflow):
    _, experiment_dir, _ = workflow
    before = {p.name: p.read_text() for p in (experiment_dir / 'aggregates').glob('*.csv')}
    aggregates.export_aggregates(experiment_dir)
    after = {p.name: p.read_text() for p in (experiment_dir / 'aggregates').glob('*.csv')}
    assert before == after and set(after) == {'run_summary.csv', 'budget_success.csv', 'budget_success_grouped.csv',
                                              'paired_runs.csv', 'transfer_summary.csv', 'cumulative_cost.csv'}


def test_summary_is_reconstructable_from_raw_tables(workflow):
    _, experiment_dir, made = workflow
    for layout in list(made.values())[:4]:
        saved = summary(layout)
        rebuilt = aggregates.reconstruct_from_tables(layout.run_dir, read_json(layout.manifest))
        assert rebuilt['totals']['candidate_evaluations_charged'] == saved['totals']['candidate_evaluations_charged']
        assert rebuilt['totals']['spectre_launches'] == saved['totals']['spectre_launches']
        if saved['first_feasible']:
            for key in ('first_feasible_eval_count', 'dispatch_index', 'completed_count', 'in_flight_count'):
                assert rebuilt['first_feasible'][key] == saved['first_feasible'][key]
        else:
            assert rebuilt['first_feasible'] is None
    layout = list(made.values())[0]
    hidden = layout.summary.with_suffix('.hidden')
    layout.summary.rename(hidden)
    try:
        runs_found, _ = aggregates.collect_runs(experiment_dir, include_mock=True)
        assert any(r['summary'].get('_source') == 'reconstructed_from_raw_tables' for r in runs_found)
    finally:
        hidden.rename(layout.summary)


def test_empty_experiment_exports_schema_defined_empty_tables(tmp_path):
    experiment = tmp_path / 'empty__000000000000'
    experiment.mkdir()
    (experiment / 'experiment.json').write_text(json.dumps(dict(experiment_id='000000000000', mock=False, runs=[])))
    paths = aggregates.export_aggregates(experiment)
    for name in ('run_summary', 'budget_success', 'paired_runs', 'transfer_summary', 'cumulative_cost'):
        rows = table(experiment, name)
        assert rows == []                                          # header only: no demonstration results
        header = (experiment / 'aggregates' / f'{name}.csv').read_text().strip().split(',')
        assert header == [c for c, _ in aggregates.COLUMNS[name]]
        assert meta(experiment, name)['empty_explanation']


def test_mock_data_is_isolated_from_real_aggregates(workflow, tmp_path):
    root, experiment_dir, made = workflow
    assert 'mock' in experiment_dir.parts and all('mock' in layout.run_dir.parts for layout in made.values())
    assert not [p for p in root.iterdir() if p.is_dir() and '__' in p.name]      # nothing mock in the real root
    runs_found, skipped = aggregates.collect_runs(experiment_dir, include_mock=False)
    assert runs_found == [] and len(skipped) == 13 and all('mock' in s['reason'] for s in skipped)
    manifest = read_json(made['source'].manifest)
    assert manifest['provenance'] == 'mock' and 'Not a circuit result' in manifest['mock_notice']
    # a mock-trained model can never be loaded for a real task
    config = make_config(root, run=dict(mode='frozen', connection_profile_id='lab'))
    config.run.model_source.run_dir = str(made['source'].run_dir)
    roots = roots_for(root)
    from gator_workbench import tasks
    real = tasks.load_task(config.circuit)
    real.origin = 'real'
    import gator_workbench.runs as runs_module
    original = runs_module.load_task
    runs_module.load_task = lambda circuit, allow_real=False, profile_id=None: real

    class PassingGate:                       # the connection gate is not what this test is about
        def gate(self, action, profile_id, acknowledge_unknown=False):
            return dict(allowed=True, status='passed', profile_id=profile_id, layers=[])
    try:
        with pytest.raises(runs.RunRejected) as error:
            runs.prepare_run(config, roots, allow_real=True, monitor=PassingGate())
        assert error.value.code == 'mock_isolation'
    finally:
        runs_module.load_task = original


def test_split_manifest_records_roles_and_warns_without_claiming_proof(workflow):
    _, experiment_dir, _ = workflow
    split = read_json(experiment_dir / 'split_manifest.json')
    assert split['counts'] == dict(train=1, validation=0, test=2, unspecified=0)
    task = next(t for t in split['tasks'] if t['task_name'] == 'target_ldo')
    assert task['role'] == 'test' and task['variable_ranges'] and task['initial_values'] and len(task['runs']) == 6
    assert 'does NOT prove' in split['limitations']


def test_detailed_csv_copy_is_on_demand_and_derived(workflow):
    _, _, made = workflow
    layout = made['source']
    assert not list(layout.exports.glob('*.csv'))                   # nothing exported unless asked
    path = aggregates.export_table_csv(layout.run_dir, 'evaluations')
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 20 and rows[0]['provenance'] == 'mock' and json.loads(rows[-1]['best_so_far_metrics'])
    assert read_json(path.with_suffix('.meta.json'))['cutoff_commit_seq'] == 20


def test_no_plotting_library_or_image_output_anywhere(workflow):
    root, _, _ = workflow
    source = Path(aggregates.__file__).parent
    for path in source.rglob('*.py'):
        text = path.read_text()
        for banned in ('matplotlib', 'plotly', 'seaborn', 'bokeh', 'altair', 'pyplot'):
            assert banned not in text.replace("'matplotlib', 'plotly', 'seaborn', 'bokeh', 'altair', 'pyplot'", ''), (path, banned)
    images = [p for p in root.rglob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.svg', '.pdf', '.gif', '.xlsx', '.html')]
    assert images == []
