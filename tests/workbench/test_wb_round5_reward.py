"""Round-5 review (2026-09-29) of the reward v2.1 workbench side: the steering check and the corner check. Bugs: a
missing data part failed every status poll (A2), a missing flagged value lost a corner check's summary (A8). Speed: both
read the same run files again on every call (B2, B5); they are now kept until those files change. The corner
reachability tests (A1, A10, B1) left on 2026-09-30 with real:gpdk045_ota7, the only task that trained at corners
(record 7.128). MOCK and local files only: no Virtuoso, no Spectre, no agent CLI (a fake one)."""
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from gator_workbench import corner_check as cc, reachability, reward_diagnostics, spec_equations
from gator_workbench.storage.atomic import read_json
from gator_workbench.storage.dataset import DatasetReader
from helpers import cli, execute, make_config, workbench_app  # noqa: F401  (cli: a fixture)

UNITS = dict(gain_db_at_start='dB', unity_gain_hz='Hz', phase_margin_estimate_deg='deg', supply_power_w='W', output_dc_v='V',
             unity_downward_crossings='count')
MEETS = dict(gain_db_at_start=60.0, unity_gain_hz=4.0e6, phase_margin_estimate_deg=80.0, supply_power_w=2.8e-6, output_dc_v=0.4,
             unity_downward_crossings=1.0)                   # every OTA7 hard spec of the starter configuration


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


# ------------------------------------------------------------------------------------------------ D
def test_one_finite_rule():
    assert reward_diagnostics._finite is spec_equations._finite
