"""Single-writer raw dataset: fsynced write-ahead journal + closed Parquet parts.

Durability contract
-------------------
* ``commit(bundle)`` appends the bundle to ``data/_journal/wal.jsonl`` and fsyncs
  BEFORE returning. That return is the acknowledgement: an acknowledged result is
  never lost, even if the process dies before the next Parquet flush.
* ``flush()`` writes one closed part per table (temp file -> fsync -> rename), the
  ``evaluations`` table last, then appends ONE fsynced record to
  ``data/_journal/flushes.jsonl``. A part belongs to the dataset only if a flush
  record lists it, which gives readers a fixed snapshot ("cutoff sequence").
* Recovery quarantines parts no flush record lists (an interrupted flush), removes
  only this package's temp files, and re-buffers journal bundles newer than the last
  flushed sequence. Bundles are keyed by ``evaluation_id``; re-committing a known key
  is a no-op, so history is never double-counted.

Exactly one writer per run directory (enforced by the run lock). Workers never write
table files; they return results to the scheduler, which commits them.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import sys

from .. import TABLE_SCHEMA_VERSION
from .atomic import (JsonlAppender, PersistenceError, publish, read_jsonl, remove_registered_temporaries, sha256_file,
                     temporary_path, write_json)
from .tables import FLUSH_ORDER, TABLES, arrow_schema, data_dictionary, normalize_row

TIMESTAMP_COLUMNS = {table: [c.name for c in spec['columns'] if c.type == 'timestamp']
                     for table, spec in TABLES.items()}

# pyarrow turns a timezone-aware timestamp into Python by trying `import pytz` first and falling back to zoneinfo. pytz
# is not a dependency, and a FAILED import is not cached: every single value repeated a full sys.path search (measured
# 2026-09-22: 400 rows took 500 ms instead of 2 ms, more on the 9p-mounted repo). A None entry makes that import fail at
# once; the rows are identical (zoneinfo either way). An installed pytz is left alone.
if 'pytz' not in sys.modules and importlib.util.find_spec('pytz') is None:
    sys.modules['pytz'] = None
# Likewise `dateutil`: pyarrow retries `import dateutil.relativedelta` for each scalar it makes (a parquet filter's).
if 'dateutil' not in sys.modules and importlib.util.find_spec('dateutil') is None:
    sys.modules['dateutil'] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class RawDataset:
    """A single-writer dataset that journals evaluation bundles before publishing closed Parquet parts."""
    def __init__(self, data_dir, *, enabled_tables=None, flush_every: int=16) -> None:
        self.root = Path(data_dir)
        self.journal_dir = self.root / '_journal'
        self.quarantine_dir = self.root / '_quarantine'
        self.enabled = set(enabled_tables or TABLES)
        unknown = self.enabled - set(TABLES)
        if unknown:
            raise KeyError(f'Unknown tables: {sorted(unknown)}')
        self.flush_every = flush_every
        for table in TABLES:
            (self.root / table).mkdir(parents=True, exist_ok=True)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.recovery = self._recover()
        self._wal = JsonlAppender(self.journal_dir / 'wal.jsonl')
        self._flush_log = JsonlAppender(self.journal_dir / 'flushes.jsonl')
        self.bytes_written = 0
        self.last_success = None
        self.failed = None

    # ------------------------------------------------------------------ recovery
    def _recover(self) -> dict:
        removed = remove_registered_temporaries(self.root)
        flushes = read_jsonl(self.journal_dir / 'flushes.jsonl')
        listed = {(table, name) for flush in flushes for table, name in flush['parts'].items()}
        quarantined = []
        for table in TABLES:
            for part in sorted((self.root / table).glob('part-*.parquet')):
                if (table, part.name) not in listed:
                    self.quarantine_dir.mkdir(exist_ok=True)
                    target = self.quarantine_dir / f'{table}__{part.name}'
                    shutil.move(str(part), str(target))
                    quarantined.append(str(target.relative_to(self.root)))
        self._flushes = flushes
        self.flushed_seq = max((f['last_seq'] for f in flushes), default=0)
        self.flushed_rows = {table: sum(f['rows'].get(table, 0) for f in flushes) for table in TABLES}
        self._known = set()
        for flush in flushes:
            self._known.update(flush.get('evaluation_ids', []))
        self._buffer = []
        rebuffered = 0
        for bundle in read_jsonl(self.journal_dir / 'wal.jsonl'):
            key = bundle['evaluation_id']
            # At the flushed number itself only a record not yet flushed can be unknown: a rows-only record
            # (record_rows) written after that flush. Every flushed key is known from flushes.jsonl, since the first
            # flush ever written.
            if bundle['commit_seq'] >= self.flushed_seq and key not in self._known:
                self._buffer.append(bundle)
                self._known.add(key)
                rebuffered += 1
        self.last_seq = max([self.flushed_seq] + [b['commit_seq'] for b in self._buffer])
        return dict(removed_temporaries=removed, quarantined_parts=quarantined,
                    rebuffered_bundles=rebuffered, flushed_seq=self.flushed_seq)

    # ------------------------------------------------------------------ writes
    def has(self, evaluation_id) -> bool:
        """Check whether an evaluation identifier is already known to this dataset."""
        return evaluation_id in self._known

    def next_seq(self) -> int:
        return self.last_seq + 1

    def commit(self, bundle) -> bool:
        """Durably acknowledge one evaluation bundle. Idempotent on evaluation_id.

        bundle = {evaluation_id, commit_seq, rows: {table: [row, ...]}}
        Returns False (and writes nothing) when the evaluation is already committed.
        """
        if self.failed is not None:
            raise PersistenceError(f'Dataset writer previously failed: {self.failed}')
        key, seq = bundle['evaluation_id'], bundle['commit_seq']
        if key in self._known:
            return False
        if seq != self.last_seq + 1:
            raise ValueError(f'commit_seq must be contiguous: expected {self.last_seq + 1}, got {seq}')
        self._append(key, seq, self._normalized(bundle.get('rows', {})))
        self.last_seq = seq
        return True

    def record_rows(self, table, rows, *, origin='rows') -> bool:
        """Durably record rows of `table` that belong to no evaluation of their own (record 7.283: the rows of learner
        updates run after the last commit, when no later commit is sure to carry them - a save point or a pause right
        after them). The record takes the LAST commit's number, so a save point taken right after it holds the rows,
        and a recovery keeps or drops them together with that evaluation; its key is its own, never an evaluation's.
        Returns False, and writes nothing, for no rows or a table that is not enabled."""
        if self.failed is not None:
            raise PersistenceError(f'Dataset writer previously failed: {self.failed}')
        if table not in TABLES:
            raise KeyError(table)
        if not rows or table not in self.enabled:
            return False
        from uuid import uuid4
        self._append(f'{origin}:{table}:{self.last_seq}:{uuid4().hex[:12]}', self.last_seq,
            self._normalized({table: rows}))
        return True

    def _normalized(self, tables) -> dict:
        rows = {}
        for table, items in tables.items():
            if table not in TABLES:
                raise KeyError(table)
            if table in self.enabled:
                rows[table] = [normalize_row(table, row) for row in items]
                for row in rows[table]:      # the journal is JSON: timestamps travel as ISO-8601 UTC
                    for name in TIMESTAMP_COLUMNS[table]:
                        if isinstance(row[name], datetime):
                            row[name] = row[name].astimezone(timezone.utc).isoformat()
        return rows

    def _append(self, key, seq, rows) -> None:
        record = dict(evaluation_id=key, commit_seq=seq, rows=rows)
        try:
            self._wal.append(record)
        except PersistenceError as exc:
            self.failed = str(exc)
            raise
        self._buffer.append(_roundtrip(record))
        self._known.add(key)
        self.last_success = utcnow()
        if len(self._buffer) >= self.flush_every:
            self.flush()

    def flush(self) -> dict | None:
        """Publish buffered bundles as closed parts. No-op when nothing is buffered."""
        if not self._buffer:
            return None
        if self.failed is not None:
            raise PersistenceError(f'Dataset writer previously failed: {self.failed}')
        import pyarrow as pa
        import pyarrow.parquet as pq
        flush_id = len(self._flushes) + 1
        first, last = self._buffer[0]['commit_seq'], self._buffer[-1]['commit_seq']
        parts, counts, sizes, checksums = {}, {}, {}, {}
        # ---- Publish all table parts before recording the completed flush in its journal.
        try:
            for table in FLUSH_ORDER:
                rows = [row for bundle in self._buffer for row in bundle['rows'].get(table, [])]
                if not rows:
                    continue
                for row in rows:
                    for name in TIMESTAMP_COLUMNS[table]:
                        row[name] = _parse_time(row[name])
                name = f'part-{flush_id:06d}.parquet'
                destination = self.root / table / name
                temporary = temporary_path(destination)
                pq.write_table(pa.Table.from_pylist(rows, schema=arrow_schema(table)), temporary, compression='zstd')
                sizes[table] = publish(temporary, destination)
                checksums[table] = sha256_file(destination)
                parts[table], counts[table] = name, len(rows)
            record = dict(flush_id=flush_id, first_seq=first, last_seq=last, parts=parts, rows=counts,
                          bytes=sizes, sha256=checksums, table_schema=TABLE_SCHEMA_VERSION,
                          evaluation_ids=[b['evaluation_id'] for b in self._buffer],
                          flushed_at=utcnow().isoformat())
            self._flush_log.append(record)
        except (OSError, PersistenceError) as exc:
            self.failed = str(exc)
            raise PersistenceError(f'Parquet flush failed; dispatch must pause: {exc}') from exc
        # ---- Advance in-memory cursors only after the completed flush has been recorded.
        self._flushes.append(record)
        self.flushed_seq = last
        for table, count in counts.items():
            self.flushed_rows[table] += count
        self.bytes_written += sum(sizes.values())
        self._buffer = []
        self.last_success = utcnow()
        return record

    def compact_journal(self) -> None:
        """Drop journal entries already covered by a flush record (called at checkpoints)."""
        self._wal.close()
        path = self.journal_dir / 'wal.jsonl'
        # see _recover: the flushed number too
        keep = [b for b in read_jsonl(path) if b['commit_seq'] >= self.flushed_seq]
        temporary = temporary_path(path)
        with temporary.open('x', encoding='utf8') as stream:
            import json
            for bundle in keep:
                stream.write(json.dumps(bundle, allow_nan=False, separators=(',', ':')) + '\n')
            stream.flush()
        publish(temporary, path)
        self._wal = JsonlAppender(path)

    def cursor(self) -> dict:
        """Log cursors stored inside a checkpoint so model, data and ledger share one boundary."""
        return dict(commit_seq=self.last_seq, flushed_seq=self.flushed_seq, flushes=len(self._flushes),
                    rows=dict(self.flushed_rows), buffered_bundles=len(self._buffer))

    def status(self) -> dict:
        """Describe the current journal, flush, buffered-bundle and persistence status."""
        return dict(last_commit_seq=self.last_seq, flushed_seq=self.flushed_seq, flushes=len(self._flushes),
                    buffered_bundles=len(self._buffer), rows=dict(self.flushed_rows),
                    bytes_written=self.bytes_written, failed=self.failed,
                    last_successful_save=None if self.last_success is None else self.last_success.isoformat())

    def close(self) -> None:
        """Flush a healthy dataset and close both journal streams even when flushing fails."""
        try:
            if self.failed is None:
                self.flush()
        finally:
            self._wal.close()
            self._flush_log.close()


def _roundtrip(record):
    import json
    return json.loads(json.dumps(record, allow_nan=False, default=_json_default))


def _json_default(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


# ---------------------------------------------------------------------- reading
def _read_schema(table: str, columns=None):
    import pyarrow as pa
    schema = arrow_schema(table)
    return schema if columns is None else pa.schema([schema.field(c) for c in columns])


def _complete_columns(result, schema, table: str) -> list:
    """Keep the same historical-column rules for whole parts and streaming batches."""
    import pyarrow as pa
    arrays = []
    for field in schema:
        if field.name in result.column_names:
            arrays.append(result[field.name])
        elif field.nullable:
            arrays.append(pa.nulls(result.num_rows, type=field.type))
        else:
            raise ValueError(f'Historical {table} part lacks required column {field.name}')
    return arrays


class DatasetReader:
    """Read a fixed snapshot: only parts listed by flush records up to `cutoff_seq`."""
    def __init__(self, data_dir, *, cutoff_seq: int | None=None) -> None:
        self.root = Path(data_dir)
        flushes = read_jsonl(self.root / '_journal' / 'flushes.jsonl')
        if cutoff_seq is not None:
            flushes = [f for f in flushes if f['last_seq'] <= cutoff_seq]
        self.flushes = flushes
        self.cutoff_seq = max((f['last_seq'] for f in flushes), default=0)

    def parts(self, table: str) -> list[Path]:
        """List a table's part paths in published flush order."""
        return [self.root / table / f['parts'][table] for f in self.flushes if table in f['parts']]

    @staticmethod
    def _read_part(path, table: str, columns=None, *, tail_rows: int | None=None):
        """Old Parquet parts acquire newly added nullable columns on read only. One open of the part serves its schema
        and its data: the second open cost a Data tab read on the 9p mount 20-40 ms (record 7.286)."""
        import pyarrow as pa
        import pyarrow.parquet as pq
        schema = _read_schema(table, columns)
        with pq.ParquetFile(path) as part:
            present = part.schema_arrow.names
            selected = [name for name in schema.names if name in present]
            if tail_rows is None or tail_rows <= 0 or not len(schema) or part.num_row_groups <= 1:
                result = part.read(columns=selected)
            else:
                groups, rows = [], 0
                for index in reversed(range(part.num_row_groups)):
                    groups.append(index)
                    rows += part.metadata.row_group(index).num_rows
                    if rows >= tail_rows:
                        break
                # Read selected groups in published order. Keep the direct read when all groups are needed;
                # streaming the inside of a large group increased both time and native memory in measurement.
                result = (part.read(columns=selected) if len(groups) == part.num_row_groups else
                          part.read_row_groups(list(reversed(groups)), columns=selected))
        result = pa.Table.from_arrays(_complete_columns(result, schema, table), schema=schema)
        # Slice after filling historical columns: Arrow cannot slice a zero-column result's row count reliably.
        return result if tail_rows is None else result.slice(max(0, result.num_rows - tail_rows))

    def table(self, table: str, columns=None):
        """Read and concatenate published table parts, preserving the schema when no parts exist."""
        import pyarrow as pa
        paths = self.parts(table)
        if not paths:
            return _read_schema(table, columns).empty_table()
        return pa.concat_tables([self._read_part(p, table, columns) for p in paths])

    def rows(self, table: str, columns=None) -> list[dict]:
        """Materialize the selected table columns as Python row dictionaries."""
        return self.table(table, columns).to_pylist()

    def iter_batches(self, table: str, columns=None, *, batch_size: int=1024):
        """Read the fixed snapshot a bounded number of rows at a time, in part order. Close the iterator if stopping
        early so that the current Parquet file is released; no later part is opened until it is needed."""
        import pyarrow as pa
        import pyarrow.parquet as pq
        if batch_size <= 0:
            raise ValueError('batch_size must be greater than zero')
        schema = _read_schema(table, columns)
        for path in self.parts(table):
            with pq.ParquetFile(path) as part:
                present = set(part.schema_arrow.names)
                for field in schema:
                    if field.name not in present and not field.nullable:
                        raise ValueError(f'Historical {table} part lacks required column {field.name}')
                for batch in part.iter_batches(batch_size=batch_size,
                    columns=[c for c in schema.names if c in present]):
                    yield (pa.RecordBatch.from_arrays(_complete_columns(batch, schema, table), schema=schema)
                           if len(schema) else batch)

    def head(self, table: str, limit: int, columns=None):
        """The FIRST `limit` rows without materializing the rest of the table."""
        import pyarrow as pa
        schema = _read_schema(table, columns)
        if limit <= 0:
            return schema.empty_table()
        taken, have = [], 0
        with closing(self.iter_batches(table, columns, batch_size=min(limit, 1024))) as batches:
            for batch in batches:
                batch = batch.slice(0, limit - have)
                taken.append(batch)
                have += batch.num_rows
                if have >= limit:
                    break
        return pa.Table.from_batches(taken, schema=schema)

    def tail(self, table: str, limit: int, columns=None):
        """The LAST `limit` rows: walk parts and row groups backwards, then read only the required groups.
        Single-group parts keep their direct read path. Each visited part is opened only once."""
        import pyarrow as pa
        paths, taken, have = self.parts(table), [], 0
        for path in reversed(paths):
            part = self._read_part(path, table, columns, tail_rows=limit - have)
            taken.append(part)
            have += part.num_rows
            if have >= limit:
                break
        if not taken:
            return self.table(table, columns)                       # no part yet: the empty table with its schema
        whole = pa.concat_tables(list(reversed(taken)))
        return whole.slice(max(0, whole.num_rows - limit))

    def row_counts(self) -> dict[str, int]:
        """Sum each table's published row counts from the flush records."""
        return {table: sum(f['rows'].get(table, 0) for f in self.flushes) for table in TABLES}

    def verify(self) -> list[str]:
        """Checksum every listed part. Returns a list of problems (empty = intact)."""
        problems = []
        for flush in self.flushes:
            for table, name in flush['parts'].items():
                path = self.root / table / name
                if not path.exists():
                    problems.append(f'missing {table}/{name}')
                elif sha256_file(path) != flush['sha256'][table]:
                    problems.append(f'checksum mismatch {table}/{name}')
        return problems

    def shown_rows(self, table: str, limit: int, tail: bool=True) -> tuple[list[str], list[dict]]:
        """(column names, rows) of `table` as the page's Data tab shows them: the newest `limit` rows (`tail`) or the first
        ones, JSON-ready. Only the rows shown are turned into Python: `tail` walks parts from the newest backwards,
        skips older row groups (a partial row group still needs full decoding). Only the columns
        shown are read: the `_json` columns
        (a state's graph patch and observation fields, an evaluation's condition results) were read and decoded, then
        dropped - 7.4 MB of a VCO run's states for the 65 KB shown (Astra's review of 7.284, record 7.286)."""
        columns = [c for c in TABLES[table]['columns'] if not c.name.endswith('_json')]
        names = [c.name for c in columns]
        part = self.tail(table, limit, names) if tail else self.head(table, limit, names)
        rows = part.to_pylist()
        for row in rows:
            for column in columns:
                value = row[column.name]
                if column.type.startswith('map') and value is not None:
                    row[column.name] = map_to_dict(value)
                elif hasattr(value, 'isoformat'):
                    row[column.name] = value.isoformat()
        return names, rows


def map_to_dict(pairs) -> dict | None:
    """Return a stored map's key/value pairs as a dict, or None for a null map."""
    return None if pairs is None else {item['key']: item['value'] for item in pairs}


def write_data_dictionary(path) -> dict:
    return write_json(path, data_dictionary())
