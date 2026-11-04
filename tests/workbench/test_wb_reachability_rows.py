"""Synthetic recorded corner evidence: bounded conversion with the same rows and historical-column rules."""
from collections import defaultdict
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gator_workbench import reachability
from gator_workbench.storage.atomic import read_jsonl
from gator_workbench.storage.dataset import DatasetReader
from gator_workbench.storage.tables import arrow_schema


METRIC_FIELDS = ['run_id', 'evaluation_id', 'condition', 'metric_name', 'raw_value', 'unit', 'valid',
                 'aggregation_level', 'failure_reason']


def metric(identifier, value, *, level='condition', condition='nominal', name='gain', valid=True, unit='V/V'):
    return dict(run_id='synthetic-run', evaluation_id=identifier, condition=condition, metric_name=name,
                raw_value=value, unit=unit, valid=valid, aggregation_level=level,
                failure_reason=None if valid else 'synthetic missing measurement')


def publish(run, number, evaluations, metrics, *, missing=()):
    data = run / 'data'
    parts, counts = {}, {}
    for table, rows, fields in [('evaluations', evaluations, ['evaluation_id', 'status']),
                                ('metrics', metrics, METRIC_FIELDS)]:
        schema = pa.schema([arrow_schema(table).field(name) for name in fields])
        # Older/external parts can carry a null in a declared-required field; both readers preserve that value.
        schema = pa.schema([field.with_nullable(True) if any(row.get(field.name) is None for row in rows)
                            else field for field in schema])
        values = pa.Table.from_pylist(rows, schema=schema)
        if table == 'metrics':
            values = values.drop(missing)
        folder = data / table
        folder.mkdir(parents=True, exist_ok=True)
        parts[table] = f'part-{number}.parquet'
        pq.write_table(values, folder / parts[table], row_group_size=113)
        counts[table] = len(rows)
    journal = data / '_journal' / 'flushes.jsonl'
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('a') as stream:
        stream.write(json.dumps(dict(flush_id=number, last_seq=number, parts=parts, rows=counts)) + '\n')


def as_before(run):
    """The previous whole-table algorithm, including first-seen order and last-record-wins duplicates."""
    reader = DatasetReader(run / 'data')
    grouped = defaultdict(lambda: defaultdict(lambda: dict(status='ok', candidate_evaluated=True,
        metrics={}, metric_units={}, metric_validity={})))
    statuses = {row['evaluation_id']: row.get('status') for row in reader.rows('evaluations',
                                                                            ['evaluation_id', 'status'])}
    for row in reader.rows('metrics'):
        if row.get('aggregation_level') != 'condition':
            continue
        condition = grouped[row['evaluation_id']][row['condition']]
        condition['status'] = statuses.get(row['evaluation_id']) or 'unavailable'
        condition['candidate_evaluated'] = condition['status'] in ('ok', 'measurement_error')
        name = row['metric_name']
        condition['metrics'][name] = row['raw_value']
        condition['metric_units'][name] = row['unit']
        condition['metric_validity'][name] = row['valid']
    designs = [dict(id=key, conditions=dict(value)) for key, value in grouped.items()]
    for path in sorted((run / 'corner_checks').glob('*/results.jsonl')):
        checks = defaultdict(dict)
        for row in read_jsonl(path):
            checks[row['evaluation_id']][row['corner']] = row
        designs.extend(dict(id=key, conditions=rows) for key, rows in checks.items())
    return designs


def test_exact_recorded_evidence_across_parts_and_corner_checks(tmp_path):
    run = tmp_path / 'mock' / 'evidence'
    publish(run, 1, [dict(evaluation_id='first', status='ok'), dict(evaluation_id='second', status='timeout')],
            [metric('first', 1), metric('second', None, valid=False), metric('aggregate-only', 20, level='aggregate'),
             metric('missing-status', 3), metric('null-status', 4), metric('first', 2, condition='slow')])
    publish(run, 2, [dict(evaluation_id='first', status='transport_error'),
                     dict(evaluation_id='second', status='measurement_error'), dict(evaluation_id='null-status', status=None)],
            [metric('first', 9, unit=None), metric('second', 7, name='μ_gain'), metric('ignored', 99, level=None)])
    for folder, value in [('z-check', 12), ('a-check', 10)]:
        path = run / 'corner_checks' / folder / 'results.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text('\n'.join(json.dumps(dict(evaluation_id='first', corner='slow', metrics={'gain': v}))
                                  for v in [value - 1, value]) + '\n')
    result = reachability._recorded_designs(run)
    assert result == as_before(run)
    assert [row['id'] for row in result] == ['first', 'second', 'missing-status', 'null-status', 'first', 'first']
    assert result[0]['conditions']['nominal']['metrics']['gain'] == 9
    assert result[0]['conditions']['nominal']['candidate_evaluated'] is False
    assert result[1]['conditions']['nominal']['candidate_evaluated'] is True
    assert result[2]['conditions']['nominal']['status'] == result[3]['conditions']['nominal']['status'] == 'unavailable'
    assert [row['conditions']['slow']['metrics']['gain'] for row in result[-2:]] == [10, 12]


@pytest.mark.parametrize('rows', [[], [metric('aggregate', 8, level='aggregate'), metric('missing', 9, level=None)]])
def test_empty_or_non_condition_tables_stay_empty(tmp_path, rows):
    publish(tmp_path, 1, [], rows)
    assert reachability._recorded_designs(tmp_path) == as_before(tmp_path) == []


def test_historical_nullable_unit_remains_unknown(tmp_path):
    publish(tmp_path, 1, [dict(evaluation_id='one', status='ok')], [metric('one', 1)], missing=['unit'])
    result = reachability._recorded_designs(tmp_path)
    assert result == as_before(tmp_path)
    assert result[0]['conditions']['nominal']['metric_units'] == {'gain': None}


@pytest.mark.parametrize('missing', ['run_id', 'evaluation_id', 'aggregation_level'])
def test_missing_required_columns_still_fail_before_filtering(tmp_path, missing):
    publish(tmp_path, 1, [], [metric('excluded', 3, level='aggregate')], missing=[missing])
    for read in (as_before, reachability._recorded_designs):
        with pytest.raises(ValueError, match=f'Historical metrics part lacks required column {missing}'):
            read(tmp_path)


def test_only_selected_condition_payloads_are_converted_in_bounded_batches(tmp_path, monkeypatch):
    rows = [metric(f'synthetic-{i}', i, level='condition' if i % 97 == 0 else 'aggregate') for i in range(4097)]
    evaluations = [dict(evaluation_id=row['evaluation_id'], status='ok') for row in rows]
    publish(tmp_path, 1, evaluations, rows)
    expected = as_before(tmp_path)
    converted, projected, closed = [], [], []

    class TrackedBatch:
        def __init__(self, batch, table, filtered=False):
            self.batch, self.table, self.filtered = batch, table, filtered

        def __getitem__(self, name):
            return self.batch[name]

        def filter(self, mask):
            return TrackedBatch(self.batch.filter(mask), self.table, filtered=True)

        def select(self, names):
            return TrackedBatch(self.batch.select(names), self.table, self.filtered)

        def to_pylist(self):
            assert self.batch.num_rows <= 1024
            if self.table == 'metrics':
                assert self.filtered, 'Condition filtering must precede Python payload conversion'
                assert set(self.batch.schema.names) == {'evaluation_id', 'condition', 'metric_name', 'raw_value', 'unit', 'valid'}
            converted.append((self.table, self.batch.num_rows))
            return self.batch.to_pylist()

    class TrackedReader(DatasetReader):
        def rows(self, *args, **kwargs):
            pytest.fail('Reachability must not materialize whole tables')

        def iter_batches(self, table, columns=None, **kwargs):
            projected.append((table, columns))
            try:
                for batch in super().iter_batches(table, columns, **kwargs):
                    yield TrackedBatch(batch, table)
            finally:
                closed.append(table)

    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', TrackedReader)
    assert reachability._recorded_designs(tmp_path) == expected
    assert sum(n for table, n in converted if table == 'metrics') == 43
    assert sum(n for table, n in converted if table == 'evaluations') == len(evaluations)
    assert projected == [('evaluations', ['evaluation_id', 'status']), ('metrics',
                         ['run_id', 'evaluation_id', 'metric_name', 'condition', 'raw_value', 'unit', 'valid', 'aggregation_level'])]
    assert closed == ['evaluations', 'metrics']
