"""Read-only chart formatting from synthetic Arrow records; no learner or simulation."""
from collections import Counter
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gator_workbench import training_series as ts
from gator_workbench.storage.tables import arrow_schema


COLUMNS = ('commit_seq', 'best_so_far_metrics', 'best_so_far_feasible', 'committed_at', 'reward')
SCHEMA = pa.schema([arrow_schema('evaluations').field(name) for name in COLUMNS])


def _before(table, objective):
    """Original formatter before skipping no-objective nested conversion."""
    if 'aggregation_level' in table.column_names:
        import pyarrow.compute as pc
        table = table.filter(pc.and_(pc.equal(table['aggregation_level'], 'aggregate'),
                                     pc.is_valid(table['hard']))).drop(['aggregation_level'])
    out = {}
    for name in table.column_names:
        column = table[name]
        if name in ts.TIME_COLUMNS:
            micros = column.cast(pa.int64()).to_pylist()
            out[name] = [None if value is None else value / 1e6 for value in micros]
        elif name == 'best_so_far_metrics':
            out['best_so_far_objective'] = ts._objective_values(
                column.to_pylist(), objective, table['best_so_far_feasible'].to_pylist())
        else:
            out[name] = column.to_pylist()
    return out


def _table(kind='mixed', chunked=False):
    """Build Arrow metrics fixtures with optional empty, null-only, or chunked columns."""
    maps = [None, [], [{'key': 'score', 'value': 3.5}],
            [{'key': 'other', 'value': 8.0}, {'key': 'score', 'value': 2.5}],
            [{'key': 'score', 'value': 1.5}, {'key': 'score', 'value': 9.0}],
            [{'key': 'score', 'value': None}, {'key': 'score', 'value': 4.0}]]
    rows = [dict(commit_seq=i + 1, best_so_far_metrics=value, best_so_far_feasible=feasible,
                 committed_at=None if i % 2 else datetime(2026, 10, 18, 12, 0, i, 123456, tzinfo=timezone.utc),
                 reward=None if i % 3 == 0 else i / 8)
            for i, (value, feasible) in enumerate((value, feasible) for value in maps for feasible in (True, False, None))]
    if kind == 'all-null':
        rows = [dict(row, best_so_far_metrics=None) for row in rows]
    elif kind == 'empty':
        rows = []
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    return pa.concat_tables([table.slice(0, 2), table.slice(2, 3), table.slice(5)]) if chunked else table


@pytest.mark.parametrize('objective', [None, {}, {'metric': 'score'}, {'metric': 'missing'}],
                         ids=['absent', 'empty', 'score', 'unrecorded'])
@pytest.mark.parametrize('kind', ['mixed', 'all-null', 'empty'])
@pytest.mark.parametrize('chunked', [False, True])
def test_all_columns_match_before_for_no_objective_and_existing_objectives(objective, kind, chunked):
    table = _table(kind, chunked)
    original = table.to_pylist()
    expected = _before(table, objective)
    assert ts._table_columns(table, objective) == expected
    assert list(ts._table_columns(table, objective)) == list(expected)
    assert table.to_pylist() == original
    if not objective:
        assert expected['best_so_far_objective'] == [None] * len(table)


@pytest.mark.parametrize('objective', [None, {}, {'metric': 'score'}], ids=['absent', 'empty', 'present'])
@pytest.mark.parametrize('empty', [False, True])
def test_feasibility_column_remains_required_even_without_rows_or_objective(objective, empty):
    table = _table('empty' if empty else 'mixed').drop(['best_so_far_feasible'])
    errors = []
    for formatter in (_before, ts._table_columns):
        with pytest.raises(KeyError, match='best_so_far_feasible') as captured:
            formatter(table, objective)
        errors.append(str(captured.value))
    assert errors[0] == errors[1]


class _TrackedColumn:
    """An Arrow column wrapper that counts conversion to Python values."""
    def __init__(self, value, name, calls):
        self.value, self.name, self.calls = value, name, calls

    def __len__(self):
        return len(self.value)

    def cast(self, kind):
        return _TrackedColumn(self.value.cast(kind), self.name, self.calls)

    def to_pylist(self):
        self.calls[self.name] += 1
        return self.value.to_pylist()


class _TrackedTable:
    """A table wrapper that exposes instrumented Arrow columns."""
    def __init__(self, value, calls):
        self.value, self.calls = value, calls
        self.column_names = value.column_names

    def __getitem__(self, name):
        return _TrackedColumn(self.value[name], name, self.calls)


@pytest.mark.parametrize('objective', [None, {}, {'metric': 'score'}], ids=['absent', 'empty', 'present'])
@pytest.mark.parametrize('chunked', [False, True])
def test_only_unused_nested_maps_and_duplicate_feasibility_conversion_are_removed(objective, chunked):
    table = _table(chunked=chunked)
    old_calls, new_calls = Counter(), Counter()
    assert ts._table_columns(_TrackedTable(table, new_calls), objective) == _before(_TrackedTable(table, old_calls), objective)
    assert old_calls['best_so_far_metrics'] == 1 and old_calls['best_so_far_feasible'] == 2
    if objective:
        assert new_calls == old_calls
    else:
        assert new_calls['best_so_far_metrics'] == 0 and new_calls['best_so_far_feasible'] == 1
        assert new_calls == old_calls - Counter(best_so_far_metrics=1, best_so_far_feasible=1)


def test_objective_present_keeps_first_duplicate_metric_and_true_feasibility_rule():
    values = ts._table_columns(_table(), {'metric': 'score'})['best_so_far_objective']
    assert values == [None, None, None, None, None, None, 3.5, None, None, 2.5, None, None,
                      1.5, None, None, None, None, None]


@pytest.mark.parametrize('missing', ['best_so_far_metrics', 'best_so_far_feasible'])
@pytest.mark.parametrize('objective', [None, {'metric': 'score'}], ids=['absent', 'present'])
def test_historical_projection_keeps_nullable_fill_and_required_column_refusal(tmp_path, missing, objective):
    path = tmp_path / 'mock' / 'historical-evaluations.parquet'
    path.parent.mkdir()
    # Direct formatter cases above deliberately include nulls in required fields. A saved Parquet part cannot:
    # use valid required values here so the missing-column reader contract itself is exercised.
    rows = _table().to_pylist()
    for row in rows:
        if row['best_so_far_feasible'] is None:
            row['best_so_far_feasible'] = False
        if row['committed_at'] is None:
            row['committed_at'] = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA).drop([missing]), path)
    if missing == 'best_so_far_feasible':
        with pytest.raises(ValueError, match='lacks required column best_so_far_feasible'):
            ts._read_part(path, 'evaluations', COLUMNS)
        return
    restored = ts._read_part(path, 'evaluations', COLUMNS)
    assert ts._table_columns(restored, objective) == _before(restored, objective)
    assert restored[missing].null_count == len(restored)
