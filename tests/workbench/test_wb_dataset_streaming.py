"""Bounded previews, exports and summary reconstruction preserve published snapshots and saved results."""
from contextlib import closing
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gator_workbench import aggregates
from gator_workbench.storage import DatasetReader, RawDataset, read_json
from gator_workbench.storage import dataset as dataset_io
from gator_workbench.storage.atomic import TEMP_MARKER
from gator_workbench.storage.tables import TABLES, arrow_schema


def _value(kind, index):
    if pa.types.is_string(kind):
        return f'fixture μ,"quoted"\n{index}'
    if pa.types.is_boolean(kind):
        return bool(index % 2)
    if pa.types.is_integer(kind):
        return index
    if pa.types.is_floating(kind):
        return index / 8
    if pa.types.is_timestamp(kind):
        return datetime(2026, 10, 17, microsecond=index, tzinfo=timezone.utc)
    if pa.types.is_list(kind):
        return [_value(kind.value_type, index)] if index % 2 else []
    if pa.types.is_struct(kind):
        return {field.name: _value(field.type, index) for field in kind}
    raise AssertionError(kind)


def _row(table, index):
    return {field.name: (None if field.nullable and index % 3 == 0 else _value(field.type, index))
            for field in arrow_schema(table)} | dict(run_id='synthetic', **(
                {'provenance': 'mock'} if table == 'evaluations' else {}))


@pytest.fixture
def dataset(tmp_path):
    writer = RawDataset(tmp_path / 'data', flush_every=3)
    for index in range(1, 10):
        writer.commit(dict(evaluation_id=f'fixture-{index}', commit_seq=index,
                           rows={table: [_row(table, index)] for table in TABLES}))
    writer.close()
    return DatasetReader(tmp_path / 'data')


def _original_csv(reader, table):
    """The pre-streaming exporter, retained as a byte-for-byte reference over all column types."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow([c.name for c in TABLES[table]['columns']])
    for row in reader.rows(table):
        cells = []
        for column in TABLES[table]['columns']:
            value = row[column.name]
            if column.type.startswith('map') and value is not None:
                value = json.dumps({pair['key']: pair['value'] for pair in value}, allow_nan=False)
            elif column.type.startswith('list') and value is not None:
                value = json.dumps(value, allow_nan=False, default=str)
            cells.append(aggregates._cell(value) if not hasattr(value, 'isoformat') else value.isoformat())
        writer.writerow(cells)
    return buffer.getvalue().encode('utf8')


@pytest.mark.parametrize('table', list(TABLES))
def test_csv_bytes_and_metadata_match_without_materializing_the_table(dataset, table, monkeypatch):
    expected = _original_csv(dataset, table)

    def full_read(*args, **kwargs):
        pytest.fail('A detailed export must not materialize the whole table')

    monkeypatch.setattr(DatasetReader, 'rows', full_read)
    monkeypatch.setattr(DatasetReader, 'table', full_read)
    path = aggregates.export_table_csv(dataset.root.parent, table)
    assert path.read_bytes() == expected
    meta = read_json(path.with_suffix('.meta.json'))
    assert meta['rows'] == 9 and meta['cutoff_commit_seq'] == 9 and meta['table'] == table


def _track_parts(monkeypatch):
    original, opened, batches = pq.ParquetFile, [], []

    class TrackedPart:
        def __init__(self, path):
            self.path, self.part, self.closed = Path(path), original(path), False
            self.reads, self.group_reads, self.batch_reads = [], [], []
            opened.append(self)

        @property
        def schema_arrow(self):
            return self.part.schema_arrow

        @property
        def metadata(self):
            return self.part.metadata

        @property
        def num_row_groups(self):
            return self.part.num_row_groups

        def read(self, **kwargs):
            self.reads.append(kwargs)
            return self.part.read(**kwargs)

        def read_row_groups(self, groups, **kwargs):
            self.group_reads.append(dict(row_groups=groups, **kwargs))
            return self.part.read_row_groups(groups, **kwargs)

        def iter_batches(self, **kwargs):
            self.batch_reads.append(kwargs)
            for batch in self.part.iter_batches(**kwargs):
                batches.append((self.path, kwargs['columns'], batch.num_rows))
                yield batch

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.part.close()
            self.closed = True

    monkeypatch.setattr(pq, 'ParquetFile', TrackedPart)
    return opened, batches


@pytest.mark.parametrize('limit,parts', [(1, 1), (3, 1), (4, 2), (9, 3), (20, 3), (0, 0)])
def test_head_reads_only_needed_parts_and_columns_and_closes(dataset, monkeypatch, limit, parts):
    columns = ['metric_name', 'raw_value']
    expected = dataset.table('metrics', columns).slice(0, limit)
    opened, batches = _track_parts(monkeypatch)
    assert dataset.head('metrics', limit, columns).equals(expected)
    assert len(opened) == parts and all(part.closed for part in opened)
    assert all(names == columns and count <= limit for _, names, count in batches)


def test_shown_head_omits_json_columns_and_never_reads_later_parts(dataset, monkeypatch):
    expected = dataset.shown_rows('states', 9)[1][:2]
    opened, batches = _track_parts(monkeypatch)
    columns, rows = dataset.shown_rows('states', 2, tail=False)
    assert rows == expected and all(not column.endswith('_json') for column in columns)
    assert len(opened) == 1 and opened[0].closed
    assert batches == [(dataset.parts('states')[0], columns, 2)]


@pytest.mark.parametrize('table', list(TABLES))
def test_tail_matches_all_column_types_across_parts(dataset, table):
    expected = dataset.table(table).slice(5)
    assert dataset.tail(table, 4).equals(expected)


@pytest.mark.parametrize('limit,parts', [(1, 1), (3, 1), (4, 2), (9, 3), (20, 3), (0, 1), (-1, 1)])
def test_tail_keeps_the_direct_path_for_small_parts(dataset, monkeypatch, limit, parts):
    columns = ['raw_value', 'metric_name']
    whole = dataset.table('metrics', columns)
    expected = whole.slice(max(0, whole.num_rows - limit))
    opened, batches = _track_parts(monkeypatch)
    assert dataset.tail('metrics', limit, columns).equals(expected)
    assert len(opened) == parts and all(part.closed for part in opened)
    assert all(part.reads == [{'columns': columns}] and not part.group_reads for part in opened)
    assert batches == []


def _tail_reader(tmp_path, *, table='metrics', count=4099, row_group_size=None, drop=()):
    root = tmp_path / 'mock' / 'data'
    path = root / table / 'part-000001.parquet'
    path.parent.mkdir(parents=True)
    contents = pa.Table.from_pylist([_row(table, i) for i in range(count)], schema=arrow_schema(table))
    pq.write_table(contents.drop(list(drop)), path, row_group_size=row_group_size)
    journal = root / '_journal' / 'flushes.jsonl'
    journal.parent.mkdir()
    journal.write_text(json.dumps(dict(flush_id=1, last_seq=1, parts={table: path.name},
                                      rows={table: count})) + '\n')
    return DatasetReader(root)


@pytest.mark.parametrize('table', list(TABLES))
def test_large_tail_matches_all_column_types(tmp_path, table):
    reader = _tail_reader(tmp_path, table=table, row_group_size=512)
    assert reader.tail(table, 20).equals(reader.table(table).slice(4079))


@pytest.mark.parametrize('limit', [1024, 2050, 4099, 5000])
def test_large_tail_limits_span_row_groups_or_exceed_the_part(tmp_path, limit):
    reader = _tail_reader(tmp_path, row_group_size=512)
    assert reader.tail('metrics', limit).equals(reader.table('metrics').slice(max(0, 4099 - limit)))


@pytest.mark.parametrize('row_group_size,groups,decoded', [(512, [7, 8], 515), (None, None, 4099)])
def test_large_tail_reads_only_relevant_row_groups(tmp_path, monkeypatch, row_group_size, groups, decoded):
    reader = _tail_reader(tmp_path, row_group_size=row_group_size)
    columns = ['raw_value', 'metric_name']
    expected = reader.table('metrics', columns).slice(4079)
    retained, complete = [], dataset_io._complete_columns

    def complete_columns(result, schema, table):
        retained.append(result.num_rows)
        return complete(result, schema, table)

    monkeypatch.setattr(dataset_io, '_complete_columns', complete_columns)
    opened, batches = _track_parts(monkeypatch)
    actual = reader.tail('metrics', 20, columns)
    assert actual.equals(expected)
    assert len(opened) == 1 and opened[0].closed
    assert opened[0].group_reads == ([dict(row_groups=groups, columns=columns)] if groups else [])
    assert opened[0].reads == ([] if groups else [dict(columns=columns)])
    assert batches == [] and retained == [decoded]


@pytest.mark.parametrize('all_missing', [False, True])
def test_large_tail_fills_missing_historical_nullable_columns(tmp_path, monkeypatch, all_missing):
    missing = next(field.name for field in arrow_schema('metrics') if field.nullable)
    reader = _tail_reader(tmp_path, row_group_size=512, drop=[missing])
    columns = [missing] if all_missing else [missing, 'metric_name']
    expected = reader.table('metrics', columns).slice(4079)
    opened, _ = _track_parts(monkeypatch)
    actual = reader.tail('metrics', 20, columns)
    assert actual.equals(expected) and actual[missing].null_count == 20
    assert opened[0].closed


@pytest.mark.parametrize('count', [0, 9, 4099])
def test_tail_missing_required_column_refuses_even_empty_parts(tmp_path, monkeypatch, count):
    reader = _tail_reader(tmp_path, count=count, row_group_size=512, drop=['run_id'])
    opened, _ = _track_parts(monkeypatch)
    with pytest.raises(ValueError, match='Historical metrics part lacks required column run_id'):
        reader.tail('metrics', 20)
    assert len(opened) == 1 and opened[0].closed


def test_tail_closes_the_file_when_selected_group_decoding_fails(tmp_path, monkeypatch):
    reader = _tail_reader(tmp_path, row_group_size=512)
    opened, _ = _track_parts(monkeypatch)

    def fail(*args, **kwargs):
        raise OSError('synthetic decode failure')

    monkeypatch.setattr(pq.ParquetFile, 'read_row_groups', fail)
    with pytest.raises(OSError, match='synthetic decode failure'):
        reader.tail('metrics', 20)
    assert len(opened) == 1 and opened[0].closed


def test_tail_preserves_empty_projection_and_empty_snapshot_schema(tmp_path):
    reader = _tail_reader(tmp_path)
    assert reader.tail('metrics', 20, []).equals(reader.table('metrics', []))
    empty = DatasetReader(tmp_path / 'mock' / 'empty')
    assert empty.tail('metrics', 20).equals(arrow_schema('metrics').empty_table())
    assert empty.tail('metrics', 20, ['metric_name']).column_names == ['metric_name']
    with pytest.raises(KeyError):
        reader.tail('metrics', 20, ['no_such_column'])


def test_streaming_batches_bound_even_a_large_single_part(tmp_path, monkeypatch):
    writer = RawDataset(tmp_path / 'data', flush_every=1)
    writer.commit(dict(evaluation_id='fixture', commit_seq=1,
                       rows={'metrics': [_row('metrics', i) for i in range(4099)]}))
    writer.close()
    opened, batches = _track_parts(monkeypatch)
    path = aggregates.export_table_csv(tmp_path, 'metrics')
    assert [count for _, _, count in batches] == [1024, 1024, 1024, 1024, 3]
    assert len(opened) == 1 and opened[0].closed
    assert read_json(path.with_suffix('.meta.json'))['rows'] == 4099


def test_streaming_snapshot_ignores_later_flushes_and_unlisted_parts(dataset):
    expected = dataset.table('metrics')
    writer = RawDataset(dataset.root, flush_every=1)
    writer.commit(dict(evaluation_id='later', commit_seq=10, rows={'metrics': [_row('metrics', 10)]}))
    writer.close()
    pq.write_table(expected, dataset.root / 'metrics' / 'part-999999.parquet')
    assert pa.Table.from_batches(list(dataset.iter_batches('metrics', batch_size=2))).equals(expected)
    assert dataset.tail('metrics', 4).equals(expected.slice(5))
    limited = DatasetReader(dataset.root, cutoff_seq=6)
    assert pa.Table.from_batches(list(limited.iter_batches('metrics'))).equals(expected.slice(0, 6))
    assert limited.tail('metrics', 4).equals(expected.slice(2, 4))
    path = aggregates.export_table_csv(dataset.root.parent, 'metrics', cutoff_seq=6)
    assert path.name == 'metrics__seq6.csv' and path.read_bytes() == _original_csv(limited, 'metrics')


def test_historical_nullable_columns_and_empty_projection_keep_row_count(dataset):
    paths = dataset.parts('metrics')
    column = next(field.name for field in arrow_schema('metrics') if field.nullable)
    for path in paths:
        with pq.ParquetFile(path) as part:
            old = part.read()
        pq.write_table(old.drop([column]), path)
    batches = list(dataset.iter_batches('metrics', batch_size=2))
    actual = pa.Table.from_batches(batches)
    assert actual.equals(dataset.table('metrics')) and actual[column].null_count == 9
    assert sum(b.num_rows for b in dataset.iter_batches('metrics', [column])) == 9
    assert sum(b.num_rows for b in dataset.iter_batches('metrics', [])) == 9
    assert dataset.head('metrics', 4, []).num_rows == 4


@pytest.mark.parametrize('empty', [False, True])
def test_missing_required_column_refuses_streaming_even_for_empty_part(dataset, empty):
    path = dataset.parts('metrics')[0]
    with pq.ParquetFile(path) as part:
        invalid = part.read().drop(['run_id'])
    pq.write_table(invalid.slice(0, 0) if empty else invalid, path)
    with pytest.raises(ValueError, match='Historical metrics part lacks required column run_id'):
        list(dataset.iter_batches('metrics'))


def test_empty_snapshot_exports_header_and_preserves_projected_schema(tmp_path):
    reader = DatasetReader(tmp_path / 'data')
    assert list(reader.iter_batches('metrics')) == []
    assert reader.head('metrics', 3).equals(arrow_schema('metrics').empty_table())
    assert reader.head('metrics', 3, ['metric_name']).column_names == ['metric_name']
    assert reader.table('metrics', []).column_names == []
    path = aggregates.export_table_csv(tmp_path, 'metrics')
    assert path.read_bytes() == _original_csv(reader, 'metrics')
    assert read_json(path.with_suffix('.meta.json'))['rows'] == 0
    with pytest.raises(ValueError, match='batch_size'):
        list(reader.iter_batches('metrics', batch_size=0))


@pytest.mark.parametrize('failure', ['read', 'write', 'publish'])
def test_failed_export_keeps_previous_files_and_removes_partial_output(dataset, monkeypatch, failure):
    path = aggregates.export_table_csv(dataset.root.parent, 'metrics')
    previous = path.read_bytes(), path.with_suffix('.meta.json').read_bytes()
    opened, _ = _track_parts(monkeypatch)
    if failure == 'read':
        original = DatasetReader.iter_batches

        def broken(self, *args, **kwargs):
            with closing(original(self, *args, **kwargs)) as batches:
                yield next(batches)
                raise OSError('fixture read failed')

        monkeypatch.setattr(DatasetReader, 'iter_batches', broken)
    elif failure == 'write':
        original = csv.writer

        class BrokenWriter:
            def __init__(self, *args, **kwargs):
                self.writer = original(*args, **kwargs)
                self.count = 0

            def writerow(self, row):
                self.count += 1
                if self.count == 3:
                    raise OSError('fixture write failed')
                return self.writer.writerow(row)

        monkeypatch.setattr(csv, 'writer', BrokenWriter)
    else:
        def broken(*args):
            raise OSError('fixture publish failed')

        monkeypatch.setattr(aggregates, 'publish', broken)
    with pytest.raises(OSError, match=f'fixture {failure} failed'):
        aggregates.export_table_csv(dataset.root.parent, 'metrics')
    assert (path.read_bytes(), path.with_suffix('.meta.json').read_bytes()) == previous
    assert not list(path.parent.glob(f'*{TEMP_MARKER}*'))
    assert opened and all(part.closed for part in opened)


def _summary_dataset(tmp_path, changes, *, part_size=3):
    """Published synthetic parts, including deliberately unordered/historical values."""
    root = tmp_path / 'mock' / 'summary' / 'data'
    (root / 'evaluations').mkdir(parents=True)
    (root / '_journal').mkdir()
    rows = [dict(_row('evaluations', i), evaluation_id=f'synthetic-{i}', valid=True,
                 all_hard_constraints_satisfied=False, normalized_constraint_violation=1.0,
                 attempts=1, cache_hit=False, condition_results_json='synthetic ' * 512) | change
            for i, change in enumerate(changes, 1)]
    flushes = []
    for offset in range(0, len(rows), part_size):
        part = rows[offset:offset + part_size]
        name = f'part-{len(flushes) + 1:06d}.parquet'
        pq.write_table(pa.Table.from_pylist(part, schema=arrow_schema('evaluations')), root / 'evaluations' / name)
        flushes.append(dict(first_seq=min(r['commit_seq'] for r in part),
                            last_seq=max(r['commit_seq'] for r in part), parts=dict(evaluations=name)))
    (root / '_journal' / 'flushes.jsonl').write_text(''.join(json.dumps(f) + '\n' for f in flushes))
    return DatasetReader(root)


def _original_summary(reader, manifest):
    """Reference from before the streaming change, including stable sorted/min selection."""
    rows = sorted(reader.rows('evaluations'), key=lambda r: r['commit_seq'])
    first = next((r for r in rows if r['all_hard_constraints_satisfied']), None)
    charged = max((r['cumulative_evaluations_charged'] for r in rows), default=0)
    valid = [r for r in rows if r['valid']]
    feasible = [r for r in valid if r['all_hard_constraints_satisfied']]
    best = feasible[0] if feasible else min(valid, key=lambda r: r['normalized_constraint_violation']) if valid else None
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


@pytest.mark.parametrize('changes', [
    [],
    [dict(valid=False, normalized_constraint_violation=None, attempts=3), dict(valid=False, cache_hit=True)],
    [dict(commit_seq=9, normalized_constraint_violation=0.5), dict(commit_seq=2, normalized_constraint_violation=0.5),
     dict(commit_seq=2, normalized_constraint_violation=0.5), dict(commit_seq=1, normalized_constraint_violation=2.0)],
    [dict(commit_seq=9, all_hard_constraints_satisfied=True), dict(commit_seq=2, all_hard_constraints_satisfied=True),
     dict(commit_seq=2, all_hard_constraints_satisfied=True), dict(commit_seq=1)],
    [dict(all_hard_constraints_satisfied=True, valid=False), dict(all_hard_constraints_satisfied=True)],
    [dict(normalized_constraint_violation=None)],
    [dict(normalized_constraint_violation=None), dict(all_hard_constraints_satisfied=True)],
    [dict(normalized_constraint_violation=float('nan')), dict(normalized_constraint_violation=0.25)],
    [dict(commit_seq=2, normalized_constraint_violation=float('nan')), dict(commit_seq=1)],
    [dict(normalized_constraint_violation=float('inf')), dict(normalized_constraint_violation=0.25)],
], ids=['empty', 'invalid', 'best-ties', 'feasible-ties', 'invalid-feasibility', 'single-null',
        'null-before-feasible', 'first-nan', 'later-nan', 'infinity'])
def test_summary_matches_the_original_for_ordering_nulls_and_empty_data(tmp_path, changes):
    reader = _summary_dataset(tmp_path, changes, part_size=2)
    manifest = dict(mode='fine_tune', source_model=dict(cost_status='known', cost_evaluations=73,
                                                      provenance_chain=[dict(run_id='synthetic-source')]))
    actual = aggregates.reconstruct_from_tables(reader.root.parent, manifest)
    expected = _original_summary(reader, manifest)
    # JSON compares the legacy NaN value by representation too (NaN != NaN).
    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_summary_still_rejects_noncomparable_valid_violations(tmp_path):
    reader = _summary_dataset(tmp_path, [dict(normalized_constraint_violation=None), {}])
    with pytest.raises(TypeError):
        _original_summary(reader, {})
    with pytest.raises(TypeError):
        aggregates.reconstruct_from_tables(reader.root.parent, {})


@pytest.mark.parametrize('feasible', [False, True])
def test_summary_projects_bounded_batches_without_full_reads_or_sorting(tmp_path, monkeypatch, feasible):
    # Cross the default batch boundary in one part. Commit order and counter maxima differ from file order.
    changes = [dict(commit_seq=(i * 17) % 2300, valid=i % 7 != 0, attempts=i % 4, cache_hit=i % 5 == 0,
                    all_hard_constraints_satisfied=feasible and i % 7 != 0 and i % 11 == 0,
                    normalized_constraint_violation=None if i % 7 == 0 else (i % 13) / 8,
                    cumulative_evaluations_charged=2300 - i, cumulative_launches=i % 37, global_env_step=i % 41)
               for i in range(2300)]
    reader = _summary_dataset(tmp_path, changes, part_size=2300)
    expected = _original_summary(reader, {})
    opened, batches = _track_parts(monkeypatch)

    def full_read(*args, **kwargs):
        pytest.fail('Summary reconstruction must not materialize the full table')

    monkeypatch.setattr(DatasetReader, 'rows', full_read)
    monkeypatch.setattr(DatasetReader, 'table', full_read)
    assert aggregates.reconstruct_from_tables(reader.root.parent, {}) == expected
    assert [size for _, _, size in batches] == [1024, 1024, 252]
    assert all(len(columns) == 13 and 'condition_results_json' not in columns for _, columns, _ in batches)
    assert len(opened) == 1 and all(part.closed for part in opened)


def test_summary_uses_one_published_snapshot_even_when_a_part_arrives_mid_read(tmp_path, monkeypatch):
    reader = _summary_dataset(tmp_path, [{}, dict(valid=False)], part_size=2)
    expected = _original_summary(reader, {})
    original = DatasetReader.iter_batches
    journal = reader.root / '_journal' / 'flushes.jsonl'
    extra = dict(_row('evaluations', 3), valid=True, all_hard_constraints_satisfied=True,
                 normalized_constraint_violation=0.0, attempts=8)
    pq.write_table(pa.Table.from_pylist([extra], schema=arrow_schema('evaluations')),
                   reader.root / 'evaluations' / 'later.parquet')  # ignored until published below

    def publish_later(self, *args, **kwargs):
        with journal.open('a') as stream:
            stream.write(json.dumps(dict(first_seq=3, last_seq=3, parts=dict(evaluations='later.parquet'))) + '\n')
        with closing(original(self, *args, **kwargs)) as batches:
            yield from batches

    monkeypatch.setattr(DatasetReader, 'iter_batches', publish_later)
    assert aggregates.reconstruct_from_tables(reader.root.parent, {}) == expected
    assert DatasetReader(reader.root).cutoff_seq == 3


def test_summary_closes_the_part_when_processing_a_batch_fails(tmp_path, monkeypatch):
    reader = _summary_dataset(tmp_path, [{}, {}])
    opened, _ = _track_parts(monkeypatch)
    original = DatasetReader.iter_batches

    class BrokenBatch:
        def to_pylist(self):
            raise OSError('fixture decode failed')

    def broken(self, *args, **kwargs):
        with closing(original(self, *args, **kwargs)) as batches:
            next(batches)
            yield BrokenBatch()

    monkeypatch.setattr(DatasetReader, 'iter_batches', broken)
    with pytest.raises(OSError, match='fixture decode failed'):
        aggregates.reconstruct_from_tables(reader.root.parent, {})
    assert opened and all(part.closed for part in opened)
