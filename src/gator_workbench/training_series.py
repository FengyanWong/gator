"""The Training tab's numbers (record 7.193): a run's recorded training values as compact columns, read incrementally.

Read-only, and nothing is computed INTO the numbers. They come from the run's own records, never from console text: the
Parquet parts that ``data/_journal/flushes.jsonl`` lists (storage/dataset.py: a part is published whole and never
rewritten), then the acknowledged bundles of ``data/_journal/wal.jsonl`` that no flush has published yet. Those are the
same rows, journaled before the next flush (every 16 evaluations by default), so a live run is drawn up to its newest
result without waiting for the next part. The training loop is not touched: no event, no file and no simulation is added
for the charts, and the page draws them in the browser only.

Cursor: the number of flush records the page already holds. An answer carries the rows of the next flush records
(``final``: they never change) and, once the page holds every flush, the journal's bundles after the newest one
(``tail``: provisional cursor pages, replaced when a later flush publishes those rows, so nothing is counted twice).
A journal being rewritten while it is read (compaction at a save point) resets the tail; a missing bundle gives an
empty tail for that answer and the next read finds the rows in a part.

What is NOT here, because the run does not record it: an episode return (the reward is recorded per evaluation - the
step reward), a separate evaluation of the policy during training (only a frozen run evaluates a policy), and an
objective when no Specs row says "then lower/higher is better". The answer says so instead of inventing them.

Polling cost (record 7.221): an answer reads the configuration and the manifest once each, the flush log only from where
the previous answer stopped, and keeps the configuration's objective while its text is unchanged (see "Caches" below).
A cache changes what an answer costs, never what it says; ``read_training(..., cached=False)`` reads every file whole.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
import os
from pathlib import Path
import stat
import threading

from .layout import RunLayout
from .storage.atomic import read_json, read_jsonl
from .storage.tables import arrow_schema

# The recorded columns each table gives, by their own names (storage/tables.py says what each one means). Two are
# delivered in another form: a timestamp as seconds since 1970 (UTC), and best_so_far_metrics as ONE number - the
# objective's value of the best feasible design so far (best_so_far_objective, below).
EVALUATION_COLUMNS = ('commit_seq', 'completion_index', 'global_env_step', 'episode_id', 'episode_step', 'phase',
                      'action_source', 'status', 'policy_version', 'reward', 'valid', 'all_hard_constraints_satisfied',
                      'normalized_constraint_violation', 'clearance_margin', 'best_so_far_feasible',
                      'best_so_far_violation', 'execution_seconds', 'committed_at')
UPDATE_COLUMNS = ('cumulative_updates', 'evaluations_collected', 'update_phase', 'actor_loss', 'critic_loss', 'alpha_loss',
                  'alpha', 'mean_log_prob', 'target_mean', 'critic_grad_norm', 'actor_grad_norm', 'updated_at')
# A spec's row: one per evaluation and spec, the value its equation gave and the limits it was held to (engine._metric_rows:
# aggregation_level 'aggregate' with `hard` set; a probe that no spec shows whole has hard = null and is not a spec).
SPEC_COLUMNS = ('evaluation_id', 'metric_name', 'raw_value', 'unit', 'threshold_lower', 'threshold_upper', 'hard',
                'satisfied', 'failure_reason', 'aggregation_level')
STRING_COLUMNS = {'episode_id', 'phase', 'action_source', 'status', 'update_phase', 'metric_name', 'failure_reason'}
TIME_COLUMNS = {'committed_at', 'updated_at'}
MAX_ROWS = 30000                # page target (evaluations + updates + specs); a published flush is indivisible
_POOL = None
_POOL_LOCK = threading.Lock()


def _pool():
    """Parts are read side by side: on the 9p-mounted D: drive a part costs ~30 ms of waiting, and the 192 parts of an
    800-evaluation run took 5.9 s one after the other, 0.24 s eight at a time (measured 2026-10-05)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(8, thread_name_prefix='training-parts')
        return _POOL


def _finite(value):
    """A number as JSON can carry it: the tables never store a non-finite number, and nothing here makes one up."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _epoch(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.timestamp()


def _read_part(path, table, columns):
    """One open per part (DatasetReader._read_part opens it twice): the columns asked for, and a column an older part
    lacks as nulls - the reader's rule for parts written before the column existed."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = arrow_schema(table)
    with pq.ParquetFile(path) as part:
        present = set(part.schema_arrow.names)
        data = part.read(columns=[c for c in columns if c in present])
    arrays = []
    for name in columns:
        field = schema.field(name)
        if name in data.column_names:
            arrays.append(data[name])
        elif field.nullable:
            arrays.append(pa.nulls(data.num_rows, type=field.type))
        else:
            raise ValueError(f'Historical {table} part lacks required column {name}')
    return pa.Table.from_arrays(arrays, names=list(columns))


def _table_columns(table, objective):
    """pyarrow table -> {column: python list}, timestamps as epoch seconds."""
    import pyarrow as pa
    out = {}
    for name in table.column_names:
        column = table[name]
        if name in TIME_COLUMNS:
            micros = column.cast(pa.int64()).to_pylist()
            out[name] = [None if v is None else v / 1e6 for v in micros]
        elif name == 'best_so_far_metrics':
            out['best_so_far_objective'] = _objective_values(
                column.to_pylist(), objective, table['best_so_far_feasible'].to_pylist())
        else:
            out[name] = column.to_pylist()
    if 'aggregation_level' in out:              # spec rows only (see SPEC_COLUMNS)
        keep = [i for i, (level, hard) in enumerate(zip(out['aggregation_level'], out['hard']))
                if level == 'aggregate' and hard is not None]
        out = {k: [v[i] for i in keep] for k, v in out.items() if k != 'aggregation_level'}
    return out


def _objective_values(maps, objective, feasible):
    """best_so_far_metrics holds the metrics of the design the run keeps as best (best_design.py: a feasible design
    always beats an infeasible one; among feasible ones the objective decides). The objective's value of it, only while
    that design is feasible: before the first feasible design there is no best feasible objective, and none is made up."""
    if not objective:
        return [None] * len(maps)
    metric = objective['metric']
    values = []
    for pairs, is_feasible in zip(maps, feasible):
        value = None
        for item in (pairs or ()) if is_feasible is True else ():
            if item['key'] == metric:
                value = item['value']
                break
        values.append(value)
    return values


def _rows_columns(rows, columns, objective):
    """Journal rows (dicts, timestamps as ISO text, map columns as key/value pairs) -> the same columns as a part gives."""
    out = {name: [] for name in columns if name != 'best_so_far_metrics'}
    if 'best_so_far_metrics' in columns:
        out['best_so_far_objective'] = []
    for row in rows:
        for name in columns:
            value = row.get(name)
            if name in TIME_COLUMNS:
                out[name].append(_epoch(value))
            elif name == 'best_so_far_metrics':
                out['best_so_far_objective'].extend(_objective_values([value], objective, [row.get('best_so_far_feasible')]))
            else:
                out[name].append(value)
    if 'aggregation_level' in out:
        keep = [i for i, (level, hard) in enumerate(zip(out['aggregation_level'], out['hard']))
                if level == 'aggregate' and hard is not None]
        out = {k: [v[i] for i in keep] for k, v in out.items() if k != 'aggregation_level'}
    return out


class _Chunk:
    """The rows of consecutive bundles, in commit order: evaluations, learner updates and spec values."""
    def __init__(self):
        self.evaluations, self.updates, self.specs, self.spec_defs = {}, {}, {}, {}

    @staticmethod
    def _extend(target, columns):
        for name, values in columns.items():
            target.setdefault(name, []).extend(values)

    def add(self, evaluations=None, updates=None, specs=None, seq_of=None):
        if evaluations:
            self._extend(self.evaluations, evaluations)
        if updates:
            self._extend(self.updates, updates)
        if specs and specs.get('metric_name'):
            # A spec row names its evaluation; the page places it by that evaluation's commit sequence.
            specs = dict(specs, commit_seq=[seq_of.get(e) for e in specs['evaluation_id']])
            for name, unit, lower, upper, hard in zip(specs['metric_name'], specs['unit'], specs['threshold_lower'],
                                                      specs['threshold_upper'], specs['hard']):
                self.spec_defs[name] = dict(unit=unit, threshold_lower=_finite(lower), threshold_upper=_finite(upper),
                                            hard=hard)
            self._extend(self.specs, {k: v for k, v in specs.items()
                                      if k in ('commit_seq', 'metric_name', 'raw_value', 'satisfied', 'failure_reason')})

    def as_json(self):
        def encode(columns, order):
            n = len(next(iter(columns.values()), []))
            result = {'n': n}
            for name in order:
                if name not in columns:
                    continue
                values = columns[name]
                if name in STRING_COLUMNS:          # a few distinct words, many rows: each word once, then its number
                    words, codes = {}, []
                    for value in values:
                        codes.append(-1 if value is None else words.setdefault(value, len(words)))
                    result[name] = {'values': list(words), 'codes': codes}
                else:
                    result[name] = [_finite(v) for v in values]
            return result
        evaluation_order = [c for c in EVALUATION_COLUMNS] + ['best_so_far_objective']
        return dict(evaluations=encode(self.evaluations, evaluation_order),
                    updates=encode(self.updates, UPDATE_COLUMNS),
                    specs=encode(self.specs, ('commit_seq', 'metric_name', 'raw_value', 'satisfied', 'failure_reason')),
                    spec_defs=self.spec_defs)


def _flush_chunk(data, flushes, objective):
    """The rows of these flush records, read from their parts eight at a time, kept in commit order."""
    jobs = []
    for flush in flushes:
        for table, columns in (('evaluations', ('evaluation_id',) + EVALUATION_COLUMNS + ('best_so_far_metrics',)),
                               ('learner_updates', UPDATE_COLUMNS), ('metrics', SPEC_COLUMNS)):
            if table in flush['parts']:
                jobs.append((flush['flush_id'], table, data / table / flush['parts'][table], columns))
    tables = dict(zip([(j[0], j[1]) for j in jobs],
                      _pool().map(lambda job: _table_columns(_read_part(job[2], job[1], list(job[3])), objective), jobs)))
    chunk = _Chunk()
    for flush in flushes:
        evaluations = tables.get((flush['flush_id'], 'evaluations'))
        # evaluation_id is read but not delivered: the spec rows of this flush find their evaluation through it.
        seq_of = dict(zip(evaluations['evaluation_id'], evaluations['commit_seq'])) if evaluations else {}
        chunk.add(evaluations, tables.get((flush['flush_id'], 'learner_updates')),
                  tables.get((flush['flush_id'], 'metrics')), seq_of)
    return chunk


def _bundle_chunk(bundles, objective):
    chunk = _Chunk()
    for bundle in bundles:
        rows = bundle.get('rows') or {}
        evaluations = rows.get('evaluations') or []
        seq_of = {row['evaluation_id']: row['commit_seq'] for row in evaluations}
        chunk.add(_rows_columns(evaluations, EVALUATION_COLUMNS + ('best_so_far_metrics',), objective) if evaluations else None,
                  _rows_columns(rows.get('learner_updates') or [], UPDATE_COLUMNS, objective) if rows.get('learner_updates') else None,
                  _rows_columns(rows.get('metrics') or [], SPEC_COLUMNS, objective) if rows.get('metrics') else None,
                  seq_of)
    return chunk


def _journal_lines(stream, block_size=1 << 16):
    """Acknowledged lines backwards, with the byte offset immediately after each; bounded by a block and one line."""
    position = stream.seek(0, os.SEEK_END)
    pending, at_end = b'', True
    while position:
        size = min(position, block_size)
        position -= size
        stream.seek(position)
        block = stream.read(size) + pending
        pieces = block.split(b'\n')
        pending = pieces[0]
        end = position + len(block) + 1
        for line in reversed(pieces[1:]):
            if at_end:
                at_end = False                # bytes after the final newline are not acknowledged
            elif line.strip():
                yield line, end
            end -= len(line) + 1
    if not at_end and pending.strip():
        yield pending, len(pending) + 1


def journal_tail(path, after_seq, *, block_size=1 << 16):
    """The journal's acknowledged bundles with commit_seq > after_seq, oldest first, read from the end backwards and
    stopping at the first older bundle - the part a flush has not published yet, not the whole journal (it can hold a
    long run when save points are off). The blocks are walked as atomic.read_jsonl_tail walks them: bytes after the final
    newline are not an acknowledged record and are skipped. Returns (bundles, complete): complete is False when the
    bundles found do not follow `after_seq` one by one - the journal was rewritten between reading the flush list and
    reading it (compaction at a save point) - or a line cannot be read; no bundle is given then, and the next read finds
    them in a part."""
    path = Path(path)
    try:
        stream = path.open('rb')
    except FileNotFoundError:
        return [], True
    found = []
    try:
        with stream:
            for line, _ in _journal_lines(stream, block_size):
                bundle = json.loads(line)
                if bundle['commit_seq'] <= after_seq:
                    break
                found.append(bundle)
    except (ValueError, KeyError, TypeError, UnicodeError):
        return [], False
    found.reverse()
    if [b['commit_seq'] for b in found] != list(range(after_seq + 1, after_seq + 1 + len(found))):
        return [], False
    return found, True


def journal_page(path, after_seq, objective, cursor=None, *, max_rows=MAX_ROWS):
    """A bounded page, seeking directly to the next unread journal row on later polls.

    The cursor is tied to both the last flush and the open file's identity. A flush or atomic journal replacement
    resets the provisional rows in the browser. A row offset also splits a single large bundle without separating
    its spec values from their evaluation identities. Only newline-terminated (acknowledged) bundles are read.
    """
    chunk = _Chunk()
    page = dict(start=cursor, cursor=None, reset=True, more=False)
    try:
        stream = Path(path).open('rb')
    except FileNotFoundError:
        return chunk, page, True, after_seq
    with stream:
        stat = os.fstat(stream.fileno())
        identity = [stat.st_dev, stat.st_ino]
        offset, row_offset, seq = 0, 0, after_seq
        try:
            saved = json.loads(cursor) if cursor else {}
            if (saved.get('base') == after_seq and saved.get('file') == identity
                    and all(type(saved.get(k)) is int and saved[k] >= 0 for k in ('offset', 'row', 'seq'))
                    and saved['offset'] <= stat.st_size and saved['seq'] >= after_seq):
                offset, row_offset, seq = saved['offset'], saved['row'], saved['seq']
                page['reset'] = False
        except (ValueError, TypeError, AttributeError):
            pass
        remaining = max_rows
        try:
            if page['reset'] and after_seq:
                # New flush: locate its boundary from the end, without rescanning the already published history.
                offset = next((end for line, end in _journal_lines(stream)
                               if json.loads(line)['commit_seq'] <= after_seq), 0)
            stream.seek(offset)
            while remaining > 0:
                offset = stream.tell()
                line = stream.readline()
                if not line.endswith(b'\n'):
                    break                       # keep the offset: an unfinished bundle may be acknowledged next time
                if not line.strip():
                    continue
                bundle = json.loads(line)
                if bundle['commit_seq'] <= after_seq:
                    row_offset = 0
                    continue
                if bundle['commit_seq'] != seq + 1:
                    raise ValueError('Journal changed while reading its flush boundary')
                source = _bundle_chunk([bundle], objective)
                skip = row_offset
                consumed, size = 0, 0
                for name in ('evaluations', 'updates', 'specs'):
                    columns = getattr(source, name)
                    count = len(next(iter(columns.values()), []))
                    size += count
                    start = min(skip, count)
                    skip -= start
                    take = min(count - start, remaining)
                    if take:
                        _Chunk._extend(getattr(chunk, name), {k: v[start:start + take] for k, v in columns.items()})
                        consumed += take
                        remaining -= take
                chunk.spec_defs.update(source.spec_defs)
                if row_offset > size:
                    raise ValueError('Journal cursor is outside its bundle')
                row_offset += consumed
                if row_offset < size:
                    page['more'] = True
                    break
                seq = bundle['commit_seq']
                offset, row_offset = stream.tell(), 0
                if remaining == 0:
                    # A torn last line is not another page. Leave it for the next ordinary poll.
                    page['more'] = stream.readline().endswith(b'\n')
                    break
        except (ValueError, KeyError, TypeError, UnicodeError):
            return _Chunk(), dict(start=cursor, cursor=None, reset=True, more=False), False, after_seq
        page['cursor'] = json.dumps(dict(base=after_seq, file=identity, offset=offset, row=row_offset, seq=seq),
                                    separators=(',', ':'))
    return chunk, page, True, seq


# --------------------------------------------------------------------------------------------------------------- Caches
# Record 7.221. A poll of an unchanged 800-evaluation run read its whole flush log (64 records, 109 kB: ~14 ms on the
# 9p-mounted D: drive, read line by line), its configuration twice and its manifest twice (~4 ms a file). Kept now:
# * the flush log's complete records, read on from a byte offset. The log is append-only (storage/dataset.py appends one
#   fsynced record per flush and never rewrites a complete one; a writer reopening it only cuts off an unfinished last
#   line), so a poll reads only the bytes after the last complete record it holds - after checking that the log is still
#   that file with those bytes: the same device and inode, not shorter, the same size only with the same times, its
#   first 4 kB and the last record it read (at least the last 4 kB) unchanged. A run made again at the same path, a
#   replaced or cut log, fails one of them and is read whole again. A log that cannot be opened, or holds a complete
#   line that is not JSON, is read exactly as before (read_jsonl): its answer - or its error, with the line's number -
#   is the same. Not seen: a record in the middle rewritten in place while the log also grew - which no writer does.
# * the configuration's parse, validation and objective, kept while its text is the same. The text is read every time:
#   on that drive a stat costs about as much as reading the 14 kB file, and only the text proves it unchanged.
# Never kept: the manifest (a resume adds a segment), the worker's state and lock, the journal's tail (rewritten at save
# points), the Parquet parts, and a read that failed or found no file. Both caches are bounded (least recently used goes
# first) and shared by the server's threads under one lock that is never held while a file is read.
FLUSH_INDEX_RUNS = 16              # runs whose flush records are kept (the Training tab draws up to four at once)
FLUSH_INDEX_BYTES = 16 << 20       # flush-log bytes kept parsed, all runs together (~1.2 bytes of memory per byte)
CONFIG_CACHE_RUNS = 32             # runs whose configuration's objective is kept
CONFIG_CACHE_BYTES = 4 << 20       # configuration text kept, all runs together (a configuration is ~15 kB)
_ANCHOR = 4096                     # bytes compared at least, at the start and at the end of what was read
_FLUSH_FIELDS = ('flush_id', 'last_seq', 'parts', 'rows')     # all that read_training reads of a flush record
_CACHE_LOCK = threading.Lock()
_FLUSH_LOGS = OrderedDict()        # flushes.jsonl (absolute path) -> _FlushLog; least recently used first
_CONFIGS = OrderedDict()           # effective_config.json (absolute path) -> (text, parsed, objective)
_STATS = dict.fromkeys(('flush_reads', 'flush_unchanged', 'flush_appended', 'flush_rebuilt', 'flush_fallbacks',
                        'flush_evictions', 'flush_bytes_read', 'flush_bytes_parsed', 'config_hits', 'config_misses',
                        'config_evictions'), 0)


class _FlushLog:
    """One flush log as it was last read: its complete records (the fields read_training reads; a record that is not a
    JSON object stays whole, so it fails where it always did), where the last complete one ends (`offset`) and where it
    begins (`last`), the unfinished bytes after it (`pending`), and what proves the log unchanged: device and inode,
    size and times, its first _ANCHOR bytes (`head`) and the bytes before `offset` (`tail`): the last record, and at
    least _ANCHOR bytes. Made from `data`, the bytes read from `start` on (the last tail's start, or 0)."""
    __slots__ = ('identity', 'times', 'size', 'offset', 'last', 'head', 'tail', 'pending', 'records')

    def __init__(self, info, start, data, offset, last, head, records):
        self.identity, self.times = (info.st_dev, info.st_ino), (info.st_mtime_ns, info.st_ctime_ns)
        self.size, self.offset, self.last, self.head, self.records = start + len(data), offset, last, head, records
        window = max(start, min(offset - _ANCHOR, offset if last is None else last))
        self.tail, self.pending = data[window - start:offset - start], data[offset - start:]


def _pread(fd, size, offset):
    """`size` bytes from `offset`; fewer only at the end of the file."""
    chunks = []
    while size > 0:
        chunk = os.pread(fd, size, offset)
        if not chunk:
            break
        chunks.append(chunk)
        size -= len(chunk)
        offset += len(chunk)
    return b''.join(chunks)


def _complete_records(data):
    """read_jsonl's reading of these bytes: each newline-terminated line is a record, a blank one is skipped, the bytes
    after the last newline are not acknowledged yet. Returns (records, bytes used, where the last record begins or
    None), or None when a complete line is not JSON - read_jsonl then raises its error, with the line's number."""
    lines = data.split(b'\n')
    used = len(data) - len(lines.pop())          # the bytes after the last newline (none when it ends with one)
    records, last, position = [], None, 0
    try:
        for line in lines:
            text = line.strip()
            if text:
                record = json.loads(text)
                records.append({k: record[k] for k in _FLUSH_FIELDS if k in record} if type(record) is dict else record)
                last = position
            position += len(line) + 1
    except Exception:
        return None
    return records, used, last


def _note(**counts):
    with _CACHE_LOCK:
        for name, count in counts.items():
            _STATS[name] += count


def _forget(key):
    """Not read here: the caller reads the log as before. Nothing is kept of it."""
    with _CACHE_LOCK:
        _FLUSH_LOGS.pop(key, None)
        _STATS['flush_fallbacks'] += 1


def _keep(key, entry):
    with _CACHE_LOCK:
        _FLUSH_LOGS.pop(key, None)
        if entry.offset <= FLUSH_INDEX_BYTES:
            _FLUSH_LOGS[key] = entry
        held = sum(kept.offset for kept in _FLUSH_LOGS.values())
        while _FLUSH_LOGS and (len(_FLUSH_LOGS) > FLUSH_INDEX_RUNS or held > FLUSH_INDEX_BYTES):
            _, old = _FLUSH_LOGS.popitem(last=False)
            held -= old.offset
            _STATS['flush_evictions'] += 1


def _flush_records(path):
    """The records read_jsonl(path) gives (the fields read_training reads), reading only what was appended since the
    last answer while the log is provably the same file. None when it cannot be read so - no such file, not a regular
    file, a log larger than the whole cache, a complete line that is not JSON: the caller reads it as before."""
    key = os.path.abspath(path)
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return _forget(key)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > FLUSH_INDEX_BYTES:
            return _forget(key)
        with _CACHE_LOCK:
            entry = _FLUSH_LOGS.get(key)
            _STATS['flush_reads'] += 1
        if (entry is not None and entry.identity == (info.st_dev, info.st_ino) and info.st_size >= entry.offset
                and (info.st_size != entry.size or entry.times == (info.st_mtime_ns, info.st_ctime_ns))):
            start = entry.offset - len(entry.tail)                  # 0 when the tail holds the head as well
            data = _pread(fd, info.st_size - start, start)
            head = _pread(fd, len(entry.head), 0) if start else entry.head
            if data[:len(entry.tail)] == entry.tail and head == entry.head:
                read = len(data) + (len(head) if start else 0)
                fresh = data[len(entry.tail):]
                if fresh == entry.pending:                          # nothing new (the size and the times agree)
                    _note(flush_unchanged=1, flush_bytes_read=read)
                    _keep(key, entry)
                    return entry.records
                parsed = _complete_records(fresh)
                if parsed is None:
                    return _forget(key)
                added, used, last = parsed
                offset, records = entry.offset + used, entry.records + tuple(added)
                _keep(key, _FlushLog(info, start, data, offset, entry.last if last is None else entry.offset + last,
                                     entry.head if start else data[:min(offset, _ANCHOR)], records))
                _note(flush_appended=1, flush_bytes_read=read, flush_bytes_parsed=used)
                return records
        # The first read, another file, or bytes that changed where they never do: the whole log again.
        data = _pread(fd, info.st_size, 0)
        parsed = _complete_records(data)
        if parsed is None:
            return _forget(key)
        records, used, last = parsed
        records = tuple(records)
        _keep(key, _FlushLog(info, 0, data, used, last, data[:min(used, _ANCHOR)], records))
        _note(flush_rebuilt=1, flush_bytes_read=len(data), flush_bytes_parsed=used)
        return records
    finally:
        os.close(fd)


def _config(path, cached=True):
    """effective_config.json as read_json(path, default=None) reads it - once per answer, for both the objective and the
    learner line - with its objective. Kept while the text is the same (a resume rewrites the file); a missing file or a
    text that is not JSON is never kept. The parsed configuration handed out is shared: it is read, never changed."""
    try:
        text = Path(path).read_text(encoding='utf8')
    except FileNotFoundError:
        return None, None
    key = os.path.abspath(path)
    if cached:
        with _CACHE_LOCK:
            kept = _CONFIGS.get(key)
            if kept is not None and kept[0] == text:
                _CONFIGS.move_to_end(key)
                _STATS['config_hits'] += 1
                return kept[1], _copy(kept[2])
    config = json.loads(text)
    objective = _objective(config)
    if cached:
        with _CACHE_LOCK:
            _STATS['config_misses'] += 1
            _CONFIGS.pop(key, None)
            if len(text) <= CONFIG_CACHE_BYTES:
                _CONFIGS[key] = (text, config, objective)
            held = sum(len(kept[0]) for kept in _CONFIGS.values())
            while _CONFIGS and (len(_CONFIGS) > CONFIG_CACHE_RUNS or held > CONFIG_CACHE_BYTES):
                _, old = _CONFIGS.popitem(last=False)
                held -= len(old[0])
                _STATS['config_evictions'] += 1
    return config, _copy(objective)


def _copy(objective):
    """The objective an answer carries is its own: a caller changing it cannot change the kept one."""
    return dict(objective) if isinstance(objective, dict) else objective


def clear_caches():
    """Forget every kept flush log and configuration, and the counts (tests and measurements; costs only)."""
    with _CACHE_LOCK:
        _FLUSH_LOGS.clear()
        _CONFIGS.clear()
        for name in _STATS:
            _STATS[name] = 0


def cache_stats():
    """What the caches hold and did since clear_caches(): runs, records and log bytes kept, reads by kind, bytes read
    and parsed from flush logs, configuration hits."""
    with _CACHE_LOCK:
        kept = list(_FLUSH_LOGS.values())
        return dict(_STATS, flush_runs=len(kept), flush_records_held=sum(len(e.records) for e in kept),
                    flush_bytes_held=sum(e.offset for e in kept), config_runs=len(_CONFIGS))


def _objective(config):
    from . import schema
    from .compile import build_specs
    if not config:
        return None
    try:
        return build_specs(schema.WorkbenchConfig.model_validate(config))[2]
    except Exception:                       # a configuration this backend can no longer read: no objective is claimed
        return None


def run_objective(run_dir):
    """The run's objective as its best-design tracker uses it (compile.build_specs: the last active Specs row whose
    "then lower/higher is better" is set), from the run's own effective_config.json; None when there is none."""
    return _objective(read_json(RunLayout(run_dir).effective_config, default=None))


def learner_record(run_dir):
    """Whether this run records learner updates, and in plain words why not (engine._prepare decides the same way)."""
    layout = RunLayout(run_dir)
    config = read_json(layout.effective_config, default={}) or {}
    manifest = read_json(layout.manifest, default={}) or {}
    return _learner(config, manifest)


def _learner(config, manifest):
    """learner_record from the configuration and the manifest already read."""
    output, run = config.get('output') or {}, config.get('run') or {}
    method = (run.get('search') or {}).get('method', 'sac')
    every = output.get('learner_update_log_every') or 1
    if manifest.get('run_kind') == 'offline_pretraining':
        return dict(recorded=False, every=every, reason='Offline training records its validation curve in validation.json; '
                    'it has no simulator evaluations or online learner-update rows.')
    if manifest.get('mode') == 'frozen' or run.get('mode') == 'frozen':
        return dict(recorded=False, every=every, reason='A frozen run evaluates a saved policy without training it: '
                    'there are no learner updates, so no losses, temperature or entropy.')
    if method == 'llm':                  # a run of the search method "LLM only", removed on 2026-10-06 (record 7.226)
        return dict(recorded=False, every=every, reason='An LLM-only run has no RL learner, so no losses, temperature '
                    'or entropy.')
    if output.get('save_learner_updates') is False:
        return dict(recorded=False, every=every, reason='This run was started with "save learner updates" off '
                    '(Output settings), so its losses, temperature and entropy were not recorded.')
    return dict(recorded=True, every=every, reason=None)


def read_training(run_dir, flushes=0, *, max_rows=MAX_ROWS, tail_cursor=None, cached=True):
    """The Training tab's answer for one run: the rows of flush records [flushes, served) and, once served is the last
    one, the journal's tail. Raises FileNotFoundError when the folder holds no run data. The configuration and the
    manifest are read once; `cached=False` also reads the flush log whole and compiles the configuration again (the
    answer is the same - the tests compare both)."""
    layout = RunLayout(Path(run_dir))
    data = layout.data
    journal = data / '_journal'
    records = _flush_records(journal / 'flushes.jsonl') if cached else None
    if records is None:                     # not read from where the last answer stopped: exactly as before 7.221
        if not journal.is_dir():
            raise FileNotFoundError('This folder holds no recorded run data.')
        records = read_jsonl(journal / 'flushes.jsonl')
    total = len(records)
    start = max(0, min(int(flushes), total))
    manifest = read_json(layout.manifest, default={}) or {}
    config, objective = _config(layout.effective_config, cached)
    chosen, rows = [], 0
    for record in records[start:]:
        if chosen and rows + sum(record['rows'].get(t, 0) for t in ('evaluations', 'learner_updates', 'metrics')) > max_rows:
            break
        chosen.append(record)
        rows += sum(record['rows'].get(t, 0) for t in ('evaluations', 'learner_updates', 'metrics'))
    served = start + len(chosen)
    final = _flush_chunk(data, chosen, objective) if chosen else _Chunk()
    tail, tail_complete, latest = None, True, (records[-1]['last_seq'] if records else 0)
    tail_page = dict(start=tail_cursor, cursor=None, reset=True, more=False)
    if served == total:
        budget = max(0, max_rows - rows)
        if budget:
            pending, tail_page, tail_complete, latest = journal_page(
                data / '_journal' / 'wal.jsonl', latest, objective, tail_cursor, max_rows=budget)
            tail = pending.as_json()
        else:
            tail_page['more'] = True
    from .runs import run_status
    status = run_status(layout.run_dir)      # status.json + the run lock: whether a run compared beside the shown one still works
    return dict(run_dir=str(layout.run_dir), run_id=manifest.get('run_id'), mode=manifest.get('mode'),
                mock=manifest.get('mock'), state=status.get('state'), worker_alive=bool(status.get('worker_alive')),
                flushes=dict(served=served, total=total, start=start),
                final=final.as_json(), tail=tail, tail_complete=tail_complete, latest_seq=latest, tail_page=tail_page,
                objective=objective, learner=_learner(config or {}, manifest),
                segments=[{k: s.get(k) for k in ('segment', 'entry', 'started_utc', 'ended_utc', 'end_state', 'stop_reason')}
                          for s in manifest.get('segments') or []])
