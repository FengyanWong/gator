"""Synthetic chart inputs: filter unused metric rows before Python/list materialization."""
from itertools import product

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gator_workbench import training_series as ts
from gator_workbench.storage.tables import arrow_schema


SPEC_SCHEMA = pa.schema([arrow_schema('metrics').field(name) for name in ts.SPEC_COLUMNS])


def metric(index, *, level='aggregate', hard=True):
    """Build a synthetic metric row with configurable aggregation and hard-spec status."""
    return dict(evaluation_id=f'synthetic-{index % 3}', metric_name=f'spec-μ-{index % 2}',
                raw_value=None if index % 4 == 0 else index / 8, unit='fixture',
                threshold_lower=0.5, threshold_upper=None if index % 2 else 2.0, hard=hard,
                satisfied=None if index % 4 == 0 else index % 2 == 0,
                failure_reason='synthetic missing value' if index % 4 == 0 else None,
                aggregation_level=level)


def expected_specs(rows):
    # The public rule includes soft specs (hard=False), but excludes probes (hard=None).
    """Return expected chart columns for aggregate hard and soft specs."""
    kept = [row for row in rows if row.get('aggregation_level') == 'aggregate' and row.get('hard') is not None]
    return {name: [row.get(name) for row in kept] for name in ts.SPEC_COLUMNS if name != 'aggregation_level'}


@pytest.mark.parametrize('chunked', [False, True])
@pytest.mark.parametrize('selection', ['mixed', 'all', 'none', 'empty'])
def test_parquet_and_journal_keep_the_same_order_values_and_soft_specs(selection, chunked):
    choices = list(product(('aggregate', 'condition', 'nominal_only', None), (True, False, None)))
    rows = [metric(i, level=level, hard=hard) for i, (level, hard) in enumerate(choices)]
    if selection == 'all':
        rows = [metric(i, hard=bool(i % 2)) for i in range(9)]
    elif selection == 'none':
        rows = [metric(i, level='condition' if i % 2 else 'aggregate', hard=None) for i in range(9)]
    elif selection == 'empty':
        rows = []
    table = pa.Table.from_pylist(rows, schema=SPEC_SCHEMA)
    if chunked:
        table = pa.concat_tables([table.slice(0, 2), table.slice(2, 3), table.slice(5)])
    before = table.to_pylist()
    expected = expected_specs(rows)
    assert ts._table_columns(table, None) == expected
    assert ts._rows_columns(iter(rows), ts.SPEC_COLUMNS, None) == expected
    assert table.to_pylist() == before                           # source data is not edited
    assert all(len(values) == len(expected['metric_name']) for values in expected.values())


def test_only_retained_arrow_rows_are_converted_to_python():
    rows = [metric(i, level='aggregate' if i % 17 == 0 else 'condition', hard=bool(i % 2)) for i in range(2048)]
    table = pa.Table.from_pylist(rows, schema=SPEC_SCHEMA)
    converted = []

    class ConvertedColumn:
        """An Arrow column wrapper that records Python conversion sizes."""
        def __init__(self, column, name):
            self.column, self.name = column, name

        def to_pylist(self):
            """Record the column and row count materialized into Python values."""
            converted.append((self.name, len(self.column)))
            return self.column.to_pylist()

    class TrackedTable:
        """An Arrow table wrapper that permits payload access only after filtering."""
        def __init__(self, value, filtered=False):
            self.value, self.filtered = value, filtered
            self.column_names = value.column_names

        def __getitem__(self, name):
            """Refuse unfiltered payload access and track conversions of filtered columns."""
            if self.filtered:
                return ConvertedColumn(self.value[name], name)
            assert name in ('aggregation_level', 'hard'), 'Payload columns must be filtered before conversion'
            return self.value[name]

        def filter(self, mask):
            return TrackedTable(self.value.filter(mask), filtered=True)

        def drop(self, names):
            return TrackedTable(self.value.drop(names), filtered=self.filtered)

    expected = expected_specs(rows)
    assert ts._table_columns(TrackedTable(table), None) == expected
    assert converted == [(name, len(expected['metric_name'])) for name in expected]


def test_excluded_journal_rows_do_not_materialize_payload_columns():
    class ExcludedRow(dict):
        """A journal row that rejects payload reads when filtering should exclude it."""
        def get(self, name, default=None):
            """Permit only the two fields needed to decide whether a metric row is retained."""
            assert name in ('aggregation_level', 'hard'), 'Unused metric payload must not be copied into lists'
            return super().get(name, default)

    kept = [metric(3, hard=False), metric(1, hard=True)]
    rows = [ExcludedRow(aggregation_level='condition', hard=True), kept[0],
            ExcludedRow(aggregation_level='aggregate', hard=None), kept[1], ExcludedRow()]
    assert ts._rows_columns(iter(rows), ts.SPEC_COLUMNS, None) == expected_specs(kept)


@pytest.mark.parametrize('missing', [('hard',), ('failure_reason', 'threshold_lower', 'threshold_upper')])
def test_historical_nullable_columns_keep_their_existing_meaning(tmp_path, missing):
    path = tmp_path / 'mock' / 'historical.parquet'
    path.parent.mkdir()
    rows = [metric(1), metric(2, hard=False), metric(3, level='condition')]
    pq.write_table(pa.Table.from_pylist(rows, schema=SPEC_SCHEMA).drop(missing), path)
    read = ts._read_part(path, 'metrics', ts.SPEC_COLUMNS)
    expected = expected_specs([dict(row, **dict.fromkeys(missing)) for row in rows])
    assert ts._table_columns(read, None) == expected


@pytest.mark.parametrize('missing', ['evaluation_id', 'aggregation_level'])
def test_missing_required_columns_fail_even_when_no_spec_would_be_kept(tmp_path, missing):
    path = tmp_path / 'mock' / 'broken.parquet'
    path.parent.mkdir()
    pq.write_table(pa.Table.from_pylist([metric(1, hard=None)], schema=SPEC_SCHEMA).drop([missing]), path)
    with pytest.raises(ValueError, match=f'lacks required column {missing}'):
        ts._read_part(path, 'metrics', ts.SPEC_COLUMNS)


def test_invalid_spec_projection_still_requires_the_hard_flag():
    with pytest.raises(KeyError, match='hard'):
        ts._rows_columns([], ('aggregation_level',), None)
    with pytest.raises(KeyError, match='hard'):
        ts._table_columns(pa.table({'aggregation_level': pa.array([], type=pa.string())}), None)
