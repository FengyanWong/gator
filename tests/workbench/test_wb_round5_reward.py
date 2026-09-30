"""Round-5 review (2026-09-29) of the reward v2.1 workbench side: corner reachability, the steering check and the corner
check. Bugs: an unreadable old run failed every OTA7 validation (A1), a missing data part failed every status poll (A2), a
missing flagged value lost a corner check's summary (A8), the reference counted as a run design (A10). Speed: the three
read the same run files again on every call (B1, B2, B5); they are now kept until those files change. MOCK and local files
only: no Virtuoso, no Spectre, no agent CLI (a fake one)."""
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from gator_workbench import corner_check as cc, reachability, reward_diagnostics, spec_equations, tasks
from gator_workbench.paths import OutputRoots
from gator_workbench.schema import WorkbenchConfig
from gator_workbench.storage.atomic import read_json, write_json
from gator_workbench.storage.dataset import DatasetReader
from helpers import cli, execute, make_config, workbench_app  # noqa: F401  (cli: a fixture)

UNITS = dict(gain_db_at_start='dB', unity_gain_hz='Hz', phase_margin_estimate_deg='deg', supply_power_w='W', output_dc_v='V',
             unity_downward_crossings='count')
MEETS = dict(gain_db_at_start=60.0, unity_gain_hz=4.0e6, phase_margin_estimate_deg=80.0, supply_power_w=2.8e-6, output_dc_v=0.4,
             unity_downward_crossings=1.0)                   # every OTA7 hard spec of the starter configuration


def ota7(root, corners=('ss_hot_low',)):
    return WorkbenchConfig.model_validate(dict(
        tasks.real_starter_config('real:gpdk045_ota7'), output=dict(output_root=str(root)),
        run=dict(max_evaluations=10, max_spectre_launches=20, conditions=dict(policy='after_nominal', corners=list(corners)))))


def recorded_run(root, name, saved):
    """An OTA7 run folder in `root` as find_runs finds it: its manifest and the configuration it was started with."""
    run = root / f'{name}__0000' / 'runs' / 'gpdk045_ota7' / name
    run.mkdir(parents=True)
    write_json(run / 'run_manifest.json', dict(run_id=name))
    write_json(run / 'effective_config.json', saved)
    return run


def corner_results(run, check_id, evaluation_id, gain, corners=('nominal', 'ss_hot_low')):
    """Corner-check result rows of one design (appended), all specs met except, maybe, the gain."""
    path = run / 'corner_checks' / check_id / 'results.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = dict(MEETS, gain_db_at_start=gain)
    with path.open('a') as stream:
        for corner in corners:
            stream.write(json.dumps(dict(evaluation_id=evaluation_id, corner=corner, status='ok', candidate_evaluated=True,
                                         metrics=metrics, metric_units=UNITS, metric_validity={k: True for k in metrics})) + '\n')


def complete(table, rows):
    """`rows` as a part the reader accepts: every column the table declares - a value the test gives is kept, a required
    column it leaves out gets a neutral value of its type (DatasetReader may refuse a part that lacks one), anything else
    is empty. A column the table does not declare is an error of the test, not dropped quietly."""
    from datetime import datetime, timezone
    from gator_workbench.storage.tables import arrow_schema
    schema = arrow_schema(table)
    # A value the test leaves empty on purpose (a missing diagnostic) keeps its column, marked as allowed to be empty.
    schema = pa.schema([f.with_nullable(True) if any(f.name in row and row[f.name] is None for row in rows) else f
                        for f in schema])
    unknown = {key for row in rows for key in row} - set(schema.names)
    assert not unknown, f'{table} declares no column {sorted(unknown)}'

    def neutral(field):
        kind = field.type
        return (None if field.nullable else False if pa.types.is_boolean(kind) else 0 if pa.types.is_integer(kind)
                else 0.0 if pa.types.is_floating(kind) else datetime(2026, 9, 29, tzinfo=timezone.utc)
                if pa.types.is_timestamp(kind) else [] if pa.types.is_list(kind) or pa.types.is_map(kind) else 'test')
    return pa.Table.from_pylist([{f.name: row[f.name] if f.name in row else neutral(f) for f in schema} for row in rows],
                                schema=schema)


def flush(data, rows_by_table):
    """One flush as RawDataset lists it: a part per table, then ONE journal record naming them."""
    journal = data / '_journal' / 'flushes.jsonl'
    records = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
    name = f'part-{len(records) + 1:06d}.parquet'
    parts, counts = {}, {}
    for table, rows in rows_by_table.items():
        (data / table).mkdir(parents=True, exist_ok=True)
        pq.write_table(complete(table, rows), data / table / name)
        parts[table], counts[table] = name, len(rows)
    last = (records[-1]['last_seq'] if records else 0) + max(counts.values())
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('a') as stream:
        stream.write(json.dumps(dict(flush_id=len(records) + 1, last_seq=last, parts=parts, rows=counts)) + '\n')


def condition_rows(evaluation_id, gain, corners=('nominal', 'ss_hot_low')):
    """A recorded evaluation of the run tables: its status and its per-condition metrics rows."""
    metrics = [dict(evaluation_id=evaluation_id, condition=corner, metric_name=name, raw_value=value, unit=UNITS[name],
                    valid=True, aggregation_level='condition')
               for corner in corners for name, value in dict(MEETS, gain_db_at_start=gain).items()]
    return dict(evaluations=[dict(evaluation_id=evaluation_id, status='ok')], metrics=metrics)


@pytest.fixture
def no_qualification(monkeypatch):
    """The retained reward-v2 qualification is left out, so an answer depends on the runs of the test alone."""
    monkeypatch.setattr(reachability, '_qualification_reference', lambda config, all_candidates=False: [])
    monkeypatch.setattr(reachability, '_qualification_runs', lambda config: [])


def fresh(config, roots):
    """The answer without anything kept from an earlier call - what the code before the caches computed."""
    reachability._DESIGNS.clear()
    reachability._SAVED.clear()
    return reachability.check(config, roots=roots)


# ------------------------------------------------------------------------------------------------ A1: old runs never fail a validation
def test_a_run_saved_with_a_removed_encoder_or_a_missing_data_part_does_not_fail_validation(tmp_path):
    config = ota7(tmp_path)
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    body = dict(config=config.model_dump(mode='json'))
    before = client.post('/api/config/validate', json=body)
    assert before.status_code == 200
    warning = [i for i in before.json()['issues'] if i['code'] == 'corner_reachability']
    old = config.model_dump(mode='json')
    old['run']['conditions'] = dict(policy='off', corners=[])
    old['run']['network']['encoder_type'] = 'mlp'                  # removed 2026-09-26: this configuration no longer loads
    recorded_run(tmp_path, 'mlp', old)
    damaged = recorded_run(tmp_path, 'damaged', config.model_dump(mode='json'))
    flush(damaged / 'data', condition_rows('e1', 60.0))
    (damaged / 'data' / 'metrics' / 'part-000001.parquet').unlink()   # the journal lists a part that is gone
    for route in ('/api/config/validate', '/api/agent/readiness'):
        response = client.post(route, json=body)
        assert response.status_code == 200, (route, response.text[:300])
    after = client.post('/api/config/validate', json=body).json()
    assert [i for i in after['issues'] if i['code'] == 'corner_reachability'] == warning   # the two runs are skipped, nothing else


def test_an_unexpected_reachability_error_leaves_the_validation_without_that_warning(tmp_path, monkeypatch):
    from gator_workbench.api.support import validate_loaded
    config = ota7(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError('unexpected')
    monkeypatch.setattr(reachability, 'check', broken)
    report = validate_loaded(config, None, roots=OutputRoots([tmp_path], include_default=False))
    assert not any(i.code == 'corner_reachability' for i in report.issues)
    assert report.facts['corner_reachability'] is None


# ------------------------------------------------------------------------------------------------ B1: reachability kept per run file
def test_reachability_is_kept_until_a_run_file_changes(tmp_path, no_qualification, monkeypatch):
    config, roots = ota7(tmp_path), OutputRoots([tmp_path], include_default=False)
    run = recorded_run(tmp_path, 'r1', config.model_dump(mode='json'))
    flush(run / 'data', condition_rows('e1', 50.0))
    first = reachability.check(config, roots=roots)
    assert not first['observed_feasible'] and 'misses gain_db_at_start at nominal by 3.3 dB' in first['warning']
    reads = []
    real = DatasetReader.rows
    monkeypatch.setattr(DatasetReader, 'rows', lambda self, *a, **k: reads.append(a) or real(self, *a, **k))
    assert reachability.check(config, roots=roots) == first and reads == []             # nothing read again
    assert fresh(config, roots) == first and reads                                          # and the same as without the cache
    # A new flush of the run's tables: a design that meets every spec.
    flush(run / 'data', condition_rows('e2', 55.0))
    second = reachability.check(config, roots=roots)
    assert second['observed_feasible'] and second['design'] == 'e2' and second == fresh(config, roots)
    # Corner-check results: appended to, and a new check.
    other = recorded_run(tmp_path, 'r2', config.model_dump(mode='json'))
    corner_results(other, '20260929T000000Z-00000001', 'c1', 40.0)
    config.targets[0].lower = 70.0                                                         # nothing meets the gain now
    assert reachability.check(config, roots=roots)['checked_designs'] == 3
    corner_results(other, '20260929T000000Z-00000001', 'c2', 71.0)
    assert reachability.check(config, roots=roots)['design'] == 'c2'
    corner_results(other, '20260929T000000Z-00000002', 'c3', 72.0)
    assert reachability.check(config, roots=roots)['checked_designs'] == 5
    # A continued run rewrites its configuration: changed probes cannot reinterpret its old metric names.
    saved = config.model_dump(mode='json')
    saved['measurements'][0]['unit'] = 'V'
    write_json(other / 'effective_config.json', saved)
    third = reachability.check(config, roots=roots)
    assert third['checked_designs'] == 2 and not third['observed_feasible'] and third == fresh(config, roots)


def test_the_retained_qualification_is_read_once_per_report(tmp_path, monkeypatch):
    from gator_workbench import paths
    config = ota7(tmp_path)
    root = tmp_path / 'artifacts/local/reward-v2-real/20260926-qualification-04'
    jobs = []
    for label, corner in (('baseline_nominal_1', 'nominal'), ('derived_ss_hot_low', 'ss_hot_low')):
        directory = root / 'stage-a' / 'simulations' / label
        write_json(directory / 'result.json', dict(condition=dict(corner=dict(id=corner)), status='ok', candidate_evaluated=True,
                                                   metrics=dict(MEETS), metric_units=UNITS, metric_validity={k: True for k in MEETS}))
        jobs.append(dict(label=label, artifact_directory=str(directory)))
    write_json(root / 'stage-a' / 'report.json', dict(jobs=jobs, aggregates=[]))
    monkeypatch.setattr(paths, 'repo_root', lambda: tmp_path)
    first = reachability._qualification_reference(config)
    assert [d['id'] for d in first] == ['reference'] and set(first[0]['conditions']) == {'nominal', 'ss_hot_low'}
    first[0]['conditions']['nominal']['metrics'].clear()                 # what a caller does with its answer stays its own
    opened = []
    real = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k: opened.append(self.name) or real(self, *a, **k))
    again = reachability._qualification_reference(config)
    assert again[0]['conditions']['nominal']['metrics'] == MEETS and opened == []
    write_json(root / 'stage-a' / 'report.json', dict(jobs=jobs[:1], aggregates=[]))   # a new report: read again
    assert set(reachability._qualification_reference(config)[0]['conditions']) == {'nominal'}


def test_suggestion_checks_do_not_work_out_the_reachability_warning(tmp_path, cli, monkeypatch):
    from gator_workbench.agents import settings_review
    cli('settings_review')
    calls, during = [], []
    real_check, real_review = reachability.check, settings_review.check
    monkeypatch.setattr(reachability, 'check', lambda *a, **k: calls.append(1) or real_check(*a, **k))

    def review(*args, **kwargs):
        before = len(calls)
        answer = real_review(*args, **kwargs)
        during.append(len(calls) - before)
        return answer
    monkeypatch.setattr(settings_review, 'check', review)
    client = TestClient(workbench_app(tmp_path))
    reply = client.post('/api/agent/propose', json=dict(kind='settings_review', prompt='Review my settings.',
                                                        config=ota7(tmp_path).model_dump(mode='json')))
    assert reply.status_code == 200 and reply.json()['suggestions']
    assert calls and during == [0]       # the checklists still carry it; each tried suggestion keeps only errors and blockers


# ------------------------------------------------------------------------------------------------ A2 + B2: the steering check
def steering_as_before(run_dir):
    """reward_diagnostics.load as it was before the cache: the newest 64 rows, doubled until 50 are scored."""
    reader = DatasetReader(Path(run_dir) / 'data')
    total = reader.row_counts().get('evaluations', 0)
    limit = min(64, total)
    while True:
        rows = reader.tail('evaluations', limit, ['completion_index', 'dispatch_index', 'reward']).to_pylist()
        if sum(reward_diagnostics._finite(r.get('reward')) for r in rows) >= 50 or limit >= total:
            break
        limit = min(total, max(1, limit * 2))
    return reward_diagnostics.steering(rows, reader.tail('learner_updates', 1, ['alpha', 'mean_log_prob']).to_pylist())


def test_steering_is_kept_until_a_flush(tmp_path, monkeypatch):
    data, index = tmp_path / 'data', 0
    for part in range(12):
        rows = []
        for _ in range(16):
            index += 1
            finite = part % 3 != 1 and index % 5
            rows.append(dict(completion_index=index + (3 if index % 4 == 0 else 0), dispatch_index=index,
                             reward=(math.sin(index) if finite else None if index % 2 else float('nan'))))
        flush(data, dict(evaluations=rows, learner_updates=[dict(alpha=0.2, mean_log_prob=-1.0 - part)]))
    assert reward_diagnostics.load(tmp_path) == steering_as_before(tmp_path)
    reads = []
    real = pq.read_table
    monkeypatch.setattr(pq, 'read_table', lambda *a, **k: reads.append(a[0]) or real(*a, **k))
    reward_diagnostics._STEERING.clear()
    answer = reward_diagnostics.load(tmp_path)
    assert answer['scored_designs'] == 50 and reads, 'read once after the flush'
    reads.clear()
    assert reward_diagnostics.load(tmp_path) == answer and reads == [], 'kept between polls'
    flush(data, dict(evaluations=[dict(completion_index=500, dispatch_index=500, reward=40.0)],
                     learner_updates=[dict(alpha=None, mean_log_prob=-1.0)]))
    changed = reward_diagnostics.load(tmp_path)
    assert changed != answer and changed == steering_as_before(tmp_path) and changed['exploration_bonus'] is None


def test_status_with_a_missing_data_part_still_answers(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=6)), tmp_path)
    assert state == 'completed'
    next((layout.data / 'evaluations').glob('part-*.parquet')).unlink()
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    response = client.get('/api/runs/status', params=dict(run_dir=str(layout.run_dir)))
    assert response.status_code == 200 and response.json()['steering'] is None
    assert response.json()['state'] == 'completed'


# ------------------------------------------------------------------------------------------------ B5: the corner-check plan
def test_a_plan_reads_the_run_tables_once_per_flush_journal(tmp_path, monkeypatch):
    layout, _ = execute(make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=12)), tmp_path)
    first = cc.plan(layout.run_dir)
    reads = []
    real = pq.read_table
    monkeypatch.setattr(pq, 'read_table', lambda *a, **k: reads.append(a[0]) or real(*a, **k))
    assert cc.plan(layout.run_dir) == first and cc.plan(layout.run_dir, designs=1)['designs'] == first['designs'][:1]
    assert reads == []
    cc._TABLES.clear()
    assert cc.plan(layout.run_dir) == first and reads, 'the same plan as read afresh'
    journal = layout.data / '_journal' / 'flushes.jsonl'
    journal.write_text(journal.read_text().splitlines(True)[0])            # the tables change: only the first flush
    cut = cc.plan(layout.run_dir)
    assert cut['counts']['evaluations'] == 5 < first['counts']['evaluations']
    cc._TABLES.clear()
    assert cc.plan(layout.run_dir) == cut


# ------------------------------------------------------------------------------------------------ A8 + A10: the corner check
def test_a_missing_flagged_value_at_a_corner_still_writes_the_summary(tmp_path, monkeypatch):
    from dataclasses import replace
    from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
    flagged = make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=12),
                          mutate=lambda raw: raw['targets'][0].update(missing_is_failure=True))
    layout, _ = execute(flagged, tmp_path)
    original, calls = SyntheticSizingBackend.run_simulation, []

    def without_score_at_ss(self, request):
        calls.append(1)
        result = original(self, request)
        return replace(result, metrics={}) if len(calls) == 2 else result     # an OK result that lacks the flagged value
    monkeypatch.setattr(SyntheticSizingBackend, 'run_simulation', without_score_at_ss)
    directory = cc.prepare(layout.run_dir, designs=1)
    assert cc.execute(directory) == 'completed'
    summary = read_json(directory / 'summary.json')
    entry = summary['designs'][0]
    assert entry['disposition'] == 'inconclusive' and 'Missing value = failed' in entry['grading_error']
    assert summary['verdicts'] == dict(accepted=0, rejected=0, inconclusive=1)
    assert cc.check_status(layout.run_dir, directory.name)['status']['state'] == 'completed'


def test_the_task_reference_is_not_counted_as_a_design_of_the_run(tmp_path):
    from gator_workbench.compile import compile_task
    config = WorkbenchConfig.model_validate(dict(tasks.real_starter_config('real:gpdk045_ota7'), run=dict(max_evaluations=10)))
    graph = tasks._verified_profile('gpdk045_ota7').optimization_graph()
    source = lambda d, p: graph.parameters[d][p].source_name or p
    expected = {(d, source(d, p)) for d, p in graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})}
    context = SimpleNamespace(mock=False, compiled=compile_task(config, graph), layout=SimpleNamespace(data=tmp_path),
                              expected_keys=expected, source_name=source)
    chosen, counts = cc.candidates(context)
    assert [d['evaluation_id'] for d in chosen] == ['task_reference']
    assert counts['feasible'] == 0 and counts['distinct'] == 0            # "0 feasible evaluations, 0 different designs"


# ------------------------------------------------------------------------------------------------ D
def test_one_finite_rule():
    assert reward_diagnostics._finite is spec_equations._finite
