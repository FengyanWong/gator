"""Synthetic files exercise the real-baseline reader; no simulator, bridge or real settings are used."""
from datetime import datetime, timezone
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gator_workbench import baseline_reference as baseline
from gator_workbench.storage.dataset import DatasetReader
from gator_workbench.storage.tables import arrow_schema


COLUMNS = dict(evaluations=['evaluation_id', 'phase', 'provenance', 'result_source', 'completed_at'],
               metrics=['evaluation_id', 'measurement_id', 'metric_name', 'raw_value', 'unit', 'valid', 'aggregation_level'])


def evaluation(identifier='baseline', **changes):
    return dict(evaluation_id=identifier, phase='baseline', provenance='real', result_source='simulation',
                completed_at=datetime(2026, 11, 4, tzinfo=timezone.utc)) | changes


def metric(name='gain', value=1.0, **changes):
    return dict(evaluation_id='baseline', measurement_id=None, metric_name=name, raw_value=value, unit='fixture',
                valid=True, aggregation_level='condition') | changes


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    run = tmp_path / 'mock' / 'synthetic-baseline-evidence'
    profile = tmp_path / 'mock' / 'synthetic-profile'
    run.mkdir(parents=True)
    profile.mkdir()
    entry = dict(directory=str(profile), recipe=baseline.MAESTRO, provided_metrics=['gain', 'power'])
    monkeypatch.setattr(baseline, 'profile_entry', lambda name: entry if name == 'synthetic_fixture' else None)
    (run / 'effective_config.json').write_text(json.dumps(dict(circuit=dict(task_id='real:synthetic_fixture'))))
    (run / 'run_manifest.json').write_text(json.dumps(dict(run_id='synthetic-fixture', mock=False)))
    return run, profile


def publish(run, number, evaluations, metrics, *, missing=None):
    parts, counts = {}, {}
    for table, rows in [('evaluations', evaluations), ('metrics', metrics)]:
        schema = pa.schema([arrow_schema(table).field(name) for name in COLUMNS[table]])
        schema = pa.schema([field.with_nullable(True) if any(row.get(field.name) is None for row in rows)
                            else field for field in schema])
        values = pa.Table.from_pylist(rows, schema=schema)
        if missing and missing[0] == table:
            values = values.drop([missing[1]])
        folder = run / 'data' / table
        folder.mkdir(parents=True, exist_ok=True)
        parts[table] = f'part-{number}.parquet'
        pq.write_table(values, folder / parts[table], row_group_size=113)
        counts[table] = len(rows)
    journal = run / 'data' / '_journal' / 'flushes.jsonl'
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('a') as stream:
        stream.write(json.dumps(dict(flush_id=number, last_seq=number, parts=parts, rows=counts)) + '\n')


def before(run):
    """The prior full-read selection, preserving its exact predicates and duplicate handling."""
    reader = DatasetReader(run / 'data')
    rows = [row for row in reader.rows('evaluations', COLUMNS['evaluations'])
            if row['phase'] == 'baseline' and row['provenance'] == 'real' and row['result_source'] == 'simulation']
    if not rows:
        raise baseline.ProfileError('That run holds no real baseline simulation')
    first = rows[0]
    metrics = {row['metric_name']: row for row in reader.rows('metrics', COLUMNS['metrics'])
               if row['evaluation_id'] == first['evaluation_id'] and row['measurement_id'] is None
               and row['aggregation_level'] == 'condition'}
    return first, metrics


def test_first_baseline_and_last_raw_metrics_are_exact_across_all_parts(recorded):
    run, profile = recorded
    publish(run, 1, [evaluation('mock', provenance='synthetic'), evaluation('cached', result_source='cache'),
                     evaluation('unknown', phase=None), evaluation()],
            [metric(), metric('power', 2), metric(value=99, measurement_id='probe'), metric(value=98, aggregation_level='aggregate'),
             metric(value=97, aggregation_level=None), metric(value=96, evaluation_id='other')])
    publish(run, 2, [evaluation('later')], [metric(value=9, unit=None), metric(value=95, evaluation_id='later')])
    selected, raw = before(run)
    result = baseline.record_reference('synthetic_fixture', run)
    assert result['evaluation_id'] == selected['evaluation_id'] == 'baseline'
    assert result['completed_at'] == str(selected['completed_at'])
    assert result['metrics'] == {name: row['raw_value'] for name, row in raw.items()} == dict(gain=9, power=2)
    assert result['metric_units'] == dict(gain=None, power='fixture')
    assert json.loads((profile / baseline.FILES['reference']).read_text()) == result
    with pytest.raises(baseline.ProfileError, match='never replaced'):
        baseline.record_reference('synthetic_fixture', run)


def test_null_identifier_keeps_python_equality_semantics(recorded):
    run, _ = recorded
    publish(run, 1, [evaluation(None)], [metric(evaluation_id=None), metric('power', 2, evaluation_id=None)])
    selected, raw = before(run)
    result = baseline.record_reference('synthetic_fixture', run)
    assert result['evaluation_id'] == selected['evaluation_id'] is None
    assert result['metrics'] == {name: row['raw_value'] for name, row in raw.items()}


@pytest.mark.parametrize('changes', [dict(valid=False), dict(valid=None), dict(raw_value=None)])
def test_later_invalid_duplicate_still_refuses_reference(recorded, changes):
    run, profile = recorded
    publish(run, 1, [evaluation()], [metric(), metric('power', 2)])
    publish(run, 2, [], [metric(**changes)])
    with pytest.raises(baseline.ProfileError, match='not a complete, valid measurement'):
        baseline.record_reference('synthetic_fixture', run)
    assert not (profile / baseline.FILES['reference']).exists()


@pytest.mark.parametrize('missing', [('evaluations', 'phase'), ('metrics', 'valid')])
def test_later_missing_required_columns_still_fail(recorded, missing):
    run, profile = recorded
    publish(run, 1, [evaluation()], [metric(), metric('power', 2)])
    publish(run, 2, [evaluation('later')], [metric(value=9)], missing=missing)
    for read in (lambda: before(run), lambda: baseline.record_reference('synthetic_fixture', run)):
        with pytest.raises(ValueError, match=f'Historical {missing[0]} part lacks required column {missing[1]}'):
            read()
    assert not (profile / baseline.FILES['reference']).exists()


@pytest.mark.parametrize('table', ['evaluations', 'metrics'])
def test_later_corrupt_part_still_fails(recorded, table):
    run, profile = recorded
    publish(run, 1, [evaluation()], [metric(), metric('power', 2)])
    publish(run, 2, [evaluation('later')], [metric(value=9)])
    (run / 'data' / table / 'part-2.parquet').write_bytes(b'not a parquet file')
    with pytest.raises(pa.ArrowInvalid):
        before(run)
    with pytest.raises(pa.ArrowInvalid):
        baseline.record_reference('synthetic_fixture', run)
    assert not (profile / baseline.FILES['reference']).exists()


def test_only_selected_evidence_becomes_python_and_every_batch_is_consumed(recorded, monkeypatch):
    run, _ = recorded
    publish(run, 1, [evaluation()] + [evaluation(f'search-{i}', phase='search') for i in range(4096)],
            [metric(), metric('power', 2)] + [metric(evaluation_id=f'search-{i}') for i in range(4096)])
    publish(run, 2, [evaluation('later')], [metric(value=9)])
    converted, scanned, projections, closed = [], [], [], []

    class TrackedBatch:
        def __init__(self, value, table, filtered=False):
            self.value, self.table, self.filtered = value, table, filtered
            self.num_rows = value.num_rows

        def __getitem__(self, name):
            return self.value[name]

        def filter(self, mask):
            return TrackedBatch(self.value.filter(mask), self.table, True)

        def slice(self, *args):
            return TrackedBatch(self.value.slice(*args), self.table, self.filtered)

        def to_pylist(self):
            assert self.filtered and self.num_rows <= 1024
            converted.append((self.table, self.num_rows))
            return self.value.to_pylist()

    class TrackedReader(DatasetReader):
        def rows(self, *args, **kwargs):
            pytest.fail('Baseline evidence must not materialize whole tables')

        def iter_batches(self, table, columns=None, **kwargs):
            projections.append((table, columns))
            try:
                for batch in super().iter_batches(table, columns, **kwargs):
                    scanned.append((table, batch.num_rows))
                    yield TrackedBatch(batch, table)
            finally:
                closed.append(table)

    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', TrackedReader)
    result = baseline.record_reference('synthetic_fixture', run)
    assert result['metrics'] == dict(gain=9, power=2)
    assert projections == list(COLUMNS.items())
    assert {table: sum(n for kind, n in converted if kind == table) for table in COLUMNS} == dict(evaluations=1, metrics=3)
    assert {table: sum(n for kind, n in scanned if kind == table) for table in COLUMNS} == dict(evaluations=4098, metrics=4099)
    assert closed == ['evaluations', 'metrics']


@pytest.mark.parametrize('failed_table', ['evaluations', 'metrics'])
def test_conversion_failure_closes_the_active_iterator(recorded, monkeypatch, failed_table):
    run, profile = recorded
    closed = []

    class FailingBatch:
        num_rows = 1

        def __init__(self, value):
            self.value = value

        def __getitem__(self, name):
            return self.value[name]

        def filter(self, mask):
            return self

        def slice(self, *args):
            return self

        def to_pylist(self):
            raise RuntimeError('synthetic conversion error')

    class Reader:
        def __init__(self, *args):
            pass

        def iter_batches(self, table, columns):
            rows = [evaluation()] if table == 'evaluations' else [metric(), metric('power', 2)]
            batch = pa.RecordBatch.from_pylist(rows)
            try:
                yield FailingBatch(batch) if table == failed_table else batch
            finally:
                closed.append(table)

    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', Reader)
    with pytest.raises(RuntimeError, match='synthetic conversion error'):
        baseline.record_reference('synthetic_fixture', run)
    assert closed == (['evaluations'] if failed_table == 'evaluations' else ['evaluations', 'metrics'])
    assert not (profile / baseline.FILES['reference']).exists()
