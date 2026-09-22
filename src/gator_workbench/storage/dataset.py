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

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import sys

from .. import TABLE_SCHEMA_VERSION
from .atomic import (JsonlAppender, PersistenceError, publish, read_jsonl, remove_registered_temporaries,
                     sha256_file, temporary_path, write_json)
from .tables import FLUSH_ORDER, TABLES, arrow_schema, normalize_row

TIMESTAMP_COLUMNS = {table: [c.name for c in spec['columns'] if c.type == 'timestamp']
                     for table, spec in TABLES.items()}

# pyarrow turns a timezone-aware timestamp into Python by trying `import pytz` first and falling back to zoneinfo. pytz
# is not a dependency, and a FAILED import is not cached: every single value repeated a full sys.path search (measured
# 2026-09-22: 400 rows took 500 ms instead of 2 ms, more on the 9p-mounted repo). A None entry makes that import fail at
# once; the rows are identical (zoneinfo either way). An installed pytz is left alone.
if 'pytz' not in sys.modules and importlib.util.find_spec('pytz') is None:
    sys.modules['pytz'] = None


def utcnow():
    return datetime.now(timezone.utc)


def _parse_time(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class RawDataset:
    def __init__(self, data_dir, *, enabled_tables=None, flush_every=16):
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
    def _recover(self):
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
            if bundle['commit_seq'] > self.flushed_seq and key not in self._known:
                self._buffer.append(bundle)
                self._known.add(key)
                rebuffered += 1
        self.last_seq = max([self.flushed_seq] + [b['commit_seq'] for b in self._buffer])
        return dict(removed_temporaries=removed, quarantined_parts=quarantined,
                    rebuffered_bundles=rebuffered, flushed_seq=self.flushed_seq)

    # ------------------------------------------------------------------ writes
    def has(self, evaluation_id) -> bool:
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
        rows = {}
        for table, items in bundle.get('rows', {}).items():
            if table not in TABLES:
                raise KeyError(table)
            if table in self.enabled:
                rows[table] = [normalize_row(table, row) for row in items]
                for row in rows[table]:      # the journal is JSON: timestamps travel as ISO-8601 UTC
                    for name in TIMESTAMP_COLUMNS[table]:
                        if isinstance(row[name], datetime):
                            row[name] = row[name].astimezone(timezone.utc).isoformat()
        record = dict(evaluation_id=key, commit_seq=seq, rows=rows)
        try:
            self._wal.append(record)
        except PersistenceError as exc:
            self.failed = str(exc)
            raise
        self._buffer.append(_roundtrip(record))
        self._known.add(key)
        self.last_seq = seq
        self.last_success = utcnow()
        if len(self._buffer) >= self.flush_every:
            self.flush()
        return True

    def flush(self):
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
        self._flushes.append(record)
        self.flushed_seq = last
        for table, count in counts.items():
            self.flushed_rows[table] += count
        self.bytes_written += sum(sizes.values())
        self._buffer = []
        self.last_success = utcnow()
        return record

    def compact_journal(self):
        """Drop journal entries already covered by a flush record (called at checkpoints)."""
        self._wal.close()
        path = self.journal_dir / 'wal.jsonl'
        keep = [b for b in read_jsonl(path) if b['commit_seq'] > self.flushed_seq]
        temporary = temporary_path(path)
        with temporary.open('x', encoding='utf8') as stream:
            import json
            for bundle in keep:
                stream.write(json.dumps(bundle, allow_nan=False, separators=(',', ':')) + '\n')
            stream.flush()
        publish(temporary, path)
        self._wal = JsonlAppender(path)

    def cursor(self):
        """Log cursors stored inside a checkpoint so model, data and ledger share one boundary."""
        return dict(commit_seq=self.last_seq, flushed_seq=self.flushed_seq, flushes=len(self._flushes),
                    rows=dict(self.flushed_rows), buffered_bundles=len(self._buffer))

    def status(self):
        return dict(last_commit_seq=self.last_seq, flushed_seq=self.flushed_seq, flushes=len(self._flushes),
                    buffered_bundles=len(self._buffer), rows=dict(self.flushed_rows),
                    bytes_written=self.bytes_written, failed=self.failed,
                    last_successful_save=None if self.last_success is None else self.last_success.isoformat())

    def close(self):
        try:
            if self.failed is None:
                self.flush()
        finally:
            self._wal.close()
            self._flush_log.close()


def _roundtrip(record):
    import json
    return json.loads(json.dumps(record, allow_nan=False, default=_json_default))


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


# ---------------------------------------------------------------------- reading
class DatasetReader:
    """Read a fixed snapshot: only parts listed by flush records up to `cutoff_seq`."""
    def __init__(self, data_dir, *, cutoff_seq=None):
        self.root = Path(data_dir)
        flushes = read_jsonl(self.root / '_journal' / 'flushes.jsonl')
        if cutoff_seq is not None:
            flushes = [f for f in flushes if f['last_seq'] <= cutoff_seq]
        self.flushes = flushes
        self.cutoff_seq = max((f['last_seq'] for f in flushes), default=0)

    def parts(self, table):
        return [self.root / table / f['parts'][table] for f in self.flushes if table in f['parts']]

    def table(self, table, columns=None):
        import pyarrow as pa
        import pyarrow.parquet as pq
        paths = self.parts(table)
        if not paths:
            schema = arrow_schema(table)
            if columns:
                schema = pa.schema([schema.field(c) for c in columns])
            return schema.empty_table()
        return pa.concat_tables([pq.read_table(p, columns=columns) for p in paths])

    def rows(self, table, columns=None):
        return self.table(table, columns).to_pylist()

    def row_counts(self):
        return {table: sum(f['rows'].get(table, 0) for f in self.flushes) for table in TABLES}

    def verify(self):
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


def map_to_dict(pairs):
    return None if pairs is None else {item['key']: item['value'] for item in pairs}


def write_data_dictionary(path):
    from .tables import data_dictionary
    return write_json(path, data_dictionary())
