"""Aggregate formatting/publication checks using only synthetic, mock-labelled rows."""
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path

import pytest

from gator_workbench import aggregates
from gator_workbench.storage.atomic import PersistenceError, TEMP_MARKER


STAMP = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
INPUTS = {'origin': 'synthetic', 'contains_mock_data': True,
          'runs': [{'run_id': 'mock-run', 'provenance': 'mock', 'cutoff_commit_seq': 17}]}


def _before(directory, name, rows, *, inputs, explanation=None, extra_columns=()):
    """Original aggregate writer, independent of the streaming implementation."""
    columns = [c for c, _ in aggregates.COLUMNS[name]] + list(extra_columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(columns)
    for row in rows:
        writer.writerow([aggregates._cell(row.get(column)) for column in columns])
    path = Path(directory) / f'{name}.csv'
    temporary = aggregates.temporary_path(path)
    temporary.write_text(buffer.getvalue(), encoding='utf8')
    aggregates.publish(temporary, path)
    aggregates.write_json(Path(directory) / f'{name}.meta.json', dict(
        table=name, exporter_version=aggregates.EXPORTER_VERSION, generated_utc=aggregates.utcnow().isoformat(),
        rows=len(rows), schema=[dict(name=c, description=d) for c, d in aggregates.COLUMNS[name]]
        + [dict(name=c, description='Best-design physical metric (canonical unit)') for c in extra_columns],
        input_runs=inputs, empty_explanation=explanation if not rows else None,
        null_convention='empty cell = null/unknown. It never means 0, and never means failure.',
        source_of_truth='Parquet raw tables + run JSON files; this CSV is a derived snapshot'))
    return path


def _rows(name, extra_columns=()):
    """Build CSV fixture rows containing scalar, collection, null, and nonfinite values."""
    values = [None, True, False, 0, -4, 1.25, -0.0, float('nan'), float('inf'),
              'synthetic: α,β "quoted"\nline\rCR\r\nCRLF', [], ['a;b', 'c,d', None], ('µ', 4)]
    columns = [column for column, _ in aggregates.COLUMNS[name]] + list(extra_columns)
    return [{column: values[(index + row * 5) % len(values)] for index, column in enumerate(columns)}
            for row in range(3)] + [{'provenance': 'mock', 'run_id': 'mock-run'}]


def _directory(tmp_path, label):
    """Create an isolated MOCK run directory for aggregate output fixtures."""
    directory = tmp_path / 'mock' / label
    directory.mkdir(parents=True)
    return directory


@pytest.mark.parametrize('name', aggregates.COLUMNS)
@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('translated_newline', [None, '\r\n'], ids=['native', 'windows-translation'])
def test_all_six_tables_keep_exact_csv_and_metadata(tmp_path, monkeypatch, name, empty, translated_newline):
    monkeypatch.setattr(aggregates, 'utcnow', lambda: STAMP)
    original_open = Path.open
    if translated_newline is not None:
        def translated_open(path, mode='r', *args, **kwargs):
            """Emulate Windows newline translation for the temporary CSV stream."""
            if f'.csv{TEMP_MARKER}' in path.name and mode in ('w', 'x'):
                # Emulate Windows text translation on any host. Both paths previously/defaulted to None.
                assert kwargs.get('newline') is None
                kwargs['newline'] = translated_newline
            return original_open(path, mode, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', translated_open)
    extra = ('best_metric:synthetic_score',) if name == 'run_summary' else ()
    rows = [] if empty else _rows(name, extra)
    paths = [writer(_directory(tmp_path, label), name, rows, inputs=INPUTS,
                    explanation='No synthetic rows selected.', extra_columns=extra)
             for label, writer in [('before', _before), ('after', aggregates._write)]]
    assert paths[0].read_bytes() == paths[1].read_bytes()
    assert paths[0].with_suffix('.meta.json').read_bytes() == paths[1].with_suffix('.meta.json').read_bytes()
    metadata = json.loads(paths[1].with_suffix('.meta.json').read_bytes())
    assert metadata['rows'] == len(rows)
    assert metadata['input_runs'] == INPUTS
    assert metadata['empty_explanation'] == ('No synthetic rows selected.' if empty else None)
    assert [column['name'] for column in metadata['schema']] == [c for c, _ in aggregates.COLUMNS[name]] + list(extra)
    assert not list(paths[1].parent.glob(f'*{TEMP_MARKER}*'))


def _existing(directory):
    """Write previous CSV and metadata outputs for publication-boundary assertions."""
    path = directory / 'run_summary.csv'
    metadata = path.with_suffix('.meta.json')
    path.write_bytes(b'old CSV\n')
    metadata.write_bytes(b'old metadata\n')
    return path, metadata


class _BadCell:
    """A CSV cell whose string conversion raises a fixture error."""
    def __str__(self):
        raise ValueError('synthetic cell cannot be serialized')


class _BadRow(dict):
    """A row whose field lookup raises a fixture error."""
    def get(self, column):
        raise RuntimeError('synthetic row cannot be read')


@pytest.mark.parametrize('failure, error', [('cell', ValueError), ('row', RuntimeError), ('encoding', UnicodeEncodeError)])
def test_serialization_failures_preserve_previous_publication(tmp_path, failure, error):
    invalid = {'experiment_id': _BadCell()} if failure == 'cell' else (
        _BadRow() if failure == 'row' else {'experiment_id': '\ud800'})
    messages = []
    for label, writer in [('before', _before), ('after', aggregates._write)]:
        directory = _directory(tmp_path, label)
        path, metadata = _existing(directory)
        with pytest.raises(error) as captured:
            writer(directory, 'run_summary', [dict(run_id='mock-run'), invalid], inputs=INPUTS)
        # Encoding offsets differ for a single row versus a whole CSV, but the same error reaches the caller.
        messages.append(str(captured.value))
        assert path.read_bytes() == b'old CSV\n' and metadata.read_bytes() == b'old metadata\n'
        if label == 'after':
            assert not list(directory.glob(f'*{TEMP_MARKER}*'))
    if failure != 'encoding':
        assert messages[0] == messages[1]


def test_partial_temporary_write_is_closed_and_removed_without_publishing(tmp_path, monkeypatch):
    directory = _directory(tmp_path, 'after')
    path, metadata = _existing(directory)
    original_open = Path.open
    streams = []

    class InterruptedWriter:
        """A temporary output stream that fails on its third write."""
        def __init__(self, stream):
            self.stream, self.calls = stream, 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, text):
            """Forward initial writes and inject a failure before the third write."""
            self.calls += 1
            self.stream.write(text)
            if self.calls == 3:
                raise OSError('synthetic disk write failure')
            return len(text)

    def interrupted_open(file, mode='r', *args, **kwargs):
        """Wrap only the temporary CSV stream with the interrupted writer."""
        stream = original_open(file, mode, *args, **kwargs)
        if f'.csv{TEMP_MARKER}' in file.name and mode == 'x':
            streams.append(stream)
            return InterruptedWriter(stream)
        return stream

    monkeypatch.setattr(Path, 'open', interrupted_open)
    with pytest.raises(OSError, match='synthetic disk write failure'):
        aggregates._write(directory, 'run_summary', _rows('run_summary'), inputs=INPUTS)
    assert len(streams) == 1 and streams[0].closed
    assert path.read_bytes() == b'old CSV\n' and metadata.read_bytes() == b'old metadata\n'
    assert not list(directory.glob(f'*{TEMP_MARKER}*'))


@pytest.mark.parametrize('failure', ['before-rename', 'after-rename', 'metadata'])
def test_failures_keep_existing_csv_then_metadata_publication_boundary(tmp_path, monkeypatch, failure):
    publish = aggregates.publish
    write_json = aggregates.write_json
    for label, writer in [('before', _before), ('after', aggregates._write)]:
        directory = _directory(tmp_path, label)
        path, metadata = _existing(directory)

        def failed_publish(temporary, destination):
            """Inject a persistence error on the selected side of CSV publication."""
            if failure == 'before-rename':
                raise PersistenceError('synthetic publication failure')
            result = publish(temporary, destination)
            if failure == 'after-rename':
                raise PersistenceError('synthetic visibility failure')
            return result

        def failed_metadata(destination, value):
            """Inject a failure while publishing the metadata output."""
            if failure == 'metadata':
                raise PersistenceError('synthetic metadata failure')
            return write_json(destination, value)

        with monkeypatch.context() as patch:
            patch.setattr(aggregates, 'publish', failed_publish)
            patch.setattr(aggregates, 'write_json', failed_metadata)
            with pytest.raises(PersistenceError, match='synthetic'):
                writer(directory, 'run_summary', _rows('run_summary'), inputs=INPUTS)
        assert metadata.read_bytes() == b'old metadata\n'
        assert (path.read_bytes() == b'old CSV\n') == (failure == 'before-rename')
        if label == 'after':
            assert not list(directory.glob(f'*{TEMP_MARKER}*'))


def test_stream_closes_before_csv_and_metadata_are_published(tmp_path, monkeypatch):
    directory = _directory(tmp_path, 'after')
    path, metadata = _existing(directory)
    original_open, publish, write_json = Path.open, aggregates.publish, aggregates.write_json
    streams, events = [], []

    def tracked_open(file, mode='r', *args, **kwargs):
        """Capture the temporary CSV stream so publication can assert that it is closed."""
        stream = original_open(file, mode, *args, **kwargs)
        if f'.csv{TEMP_MARKER}' in file.name and mode == 'x':
            streams.append(stream)
        return stream

    def tracked_publish(temporary, destination):
        """Verify the closed stream and previous outputs before publishing the new CSV."""
        assert len(streams) == 1 and streams[0].closed
        assert path.read_bytes() == b'old CSV\n' and metadata.read_bytes() == b'old metadata\n'
        events.append('csv')
        return publish(temporary, destination)

    def tracked_metadata(destination, value):
        """Verify that CSV publication precedes the metadata update."""
        assert events == ['csv'] and path.read_bytes() != b'old CSV\n'
        assert metadata.read_bytes() == b'old metadata\n'
        events.append('metadata')
        return write_json(destination, value)

    monkeypatch.setattr(Path, 'open', tracked_open)
    monkeypatch.setattr(aggregates, 'publish', tracked_publish)
    monkeypatch.setattr(aggregates, 'write_json', tracked_metadata)
    aggregates._write(directory, 'run_summary', _rows('run_summary'), inputs=INPUTS)
    assert events == ['csv', 'metadata']
