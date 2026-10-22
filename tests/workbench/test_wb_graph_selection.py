"""Graph inspection selects the same archived state while bounding evaluation-number decoding."""
from contextlib import closing
import json
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gator_workbench import graph_view
from gator_workbench.storage.dataset import DatasetReader


def _archive(tmp_path, groups):
    root = tmp_path / 'mock' / 'graph-selection' / 'data'
    for name in ('transitions', 'states', '_journal'):
        (root / name).mkdir(parents=True, exist_ok=True)
    flushes = []
    for index, numbers in enumerate(groups):
        name = f'part-{index:06d}.parquet'
        state_ids = [f'synthetic-state-{index}-{offset}' for offset in range(len(numbers))]
        pq.write_table(pa.table({'commit_seq': pa.array(numbers, type=pa.int64()),
                                 'state_ref': state_ids,
                                 'action': pa.array([[]] * len(numbers), type=pa.list_(pa.struct([
                                     ('key', pa.string()), ('value', pa.float64())]))),
                                 'policy_version': ['synthetic'] * len(numbers)}), root / 'transitions' / name)
        pq.write_table(pa.table({'state_id': state_ids, 'origin': ['synthetic'] * len(numbers),
                                 'provenance': ['mock'] * len(numbers)}), root / 'states' / name)
        present = [number for number in numbers if number is not None]
        flushes.append(dict(first_seq=min(present, default=0), last_seq=max(present, default=0),
                            parts={'transitions': name, 'states': name},
                            rows={'transitions': len(numbers), 'states': len(numbers)}))
    (root / '_journal' / 'flushes.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in flushes))
    return DatasetReader(root)


def _original(reader, wanted, saved_at):
    """The previous selection, kept independent of the production fallback."""
    numbers = sorted(reader.table('transitions', ['commit_seq'])['commit_seq'].to_pylist())
    if not numbers:
        raise graph_view.GraphViewUnavailable('This run kept no archive of the states the network saw ("Transition archive" was '
                                             'off in its output settings, or it recorded no evaluation yet), so there is nothing '
                                             'to replay the model on.')
    first, last = numbers[0], numbers[-1]
    if wanted is None:
        chosen = ([n for n in numbers if saved_at is None or n <= saved_at] or numbers)[-1]
    elif wanted in numbers:
        chosen = wanted
    else:
        raise graph_view.GraphViewUnavailable(f'This run has no archived evaluation {wanted}: it holds {first} to {last}.')
    return chosen, dict(first=first, last=last, count=len(numbers))


def _outcome(call):
    try:
        return ('answer', call())
    except Exception as exc:
        return ('error', type(exc), str(exc))


@pytest.mark.parametrize('wanted,saved_at', [(None, None), (None, 7), (None, -100), (None, 100),
                                          (None, -(1 << 100)), (None, 1 << 100),
                                          (-4, 0), (7, -100), (15, None), (6, None),
                                          (1 << 100, None), (-(1 << 100), None)])
@pytest.mark.parametrize('declared', [True, False])
def test_sparse_unsorted_duplicate_numbers_preserve_selected_row_and_state(tmp_path, monkeypatch, wanted, saved_at, declared):
    reader = _archive(tmp_path, [[9, 2, 7, 7], [15, -4, 3], [8, 1]])
    if not declared:
        for flush in reader.flushes:
            flush.pop('rows')  # Unknown counts use streaming even for this small differential fixture.
    loader = SimpleNamespace(reader=reader, _states=None)
    with monkeypatch.context() as patch:
        patch.setattr(graph_view, '_step_number', _original)
        expected = _outcome(lambda: graph_view._step(loader, wanted, saved_at))
        expected_states = loader._states
    loader._states = None
    assert _outcome(lambda: graph_view._step(loader, wanted, saved_at)) == expected
    assert loader._states == expected_states


def test_large_selection_uses_only_bounded_projected_batches(tmp_path, monkeypatch):
    numbers = [2 * number for number in reversed(range(10001))] + [42, 42]
    reader = _archive(tmp_path, [numbers[:6000], numbers[6000:]])
    expected = _original(reader, None, 9999)
    observed, closed = [], []
    original = reader.iter_batches

    def batches(table, columns=None, *, batch_size=1024):
        assert table == 'transitions' and columns == ['commit_seq'] and batch_size == 1024
        try:
            with closing(original(table, columns, batch_size=batch_size)) as source:
                for batch in source:
                    observed.append(batch.num_rows)
                    yield batch
        finally:
            closed.append(True)

    def whole_table(*args, **kwargs):
        pytest.fail('Ordinary graph selection must not materialize all evaluation numbers')

    monkeypatch.setattr(reader, 'iter_batches', batches)
    monkeypatch.setattr(reader, 'table', whole_table)
    assert graph_view._step_number(reader, None, 9999) == expected
    assert sum(observed) == len(numbers) and max(observed) <= 1024 and len(observed) > 2
    assert closed == [True]


@pytest.mark.parametrize('numbers,wanted,saved_at', [([], None, None), ([None], None, None),
                                                  ([1, None], None, None), ([None, None], 1, None),
                                                  ([1, 4], None, 3.5), ([1, 4], True, None),
                                                  ([1, 4], 4.0, None), ([1, 4], None, 'bad')])
@pytest.mark.parametrize('declared', [True, False])
def test_exceptional_values_preserve_legacy_answers_and_errors(tmp_path, numbers, wanted, saved_at, declared):
    reader = _archive(tmp_path, [numbers])
    if not declared:
        reader.flushes[0].pop('rows')
    assert _outcome(lambda: graph_view._step_number(reader, wanted, saved_at)) == _outcome(
        lambda: _original(reader, wanted, saved_at))


def test_null_fallback_closes_current_part_before_the_legacy_read(tmp_path, monkeypatch):
    reader = _archive(tmp_path, [[1, None, 2]])
    reader.flushes[0].pop('rows')
    original, whole = reader.iter_batches, reader.table
    closed = []

    def batches(*args, **kwargs):
        try:
            with closing(original(*args, **kwargs)) as source:
                yield from source
        finally:
            closed.append(True)

    def table(*args, **kwargs):
        assert closed == [True]
        return whole(*args, **kwargs)

    monkeypatch.setattr(reader, 'iter_batches', batches)
    monkeypatch.setattr(reader, 'table', table)
    with pytest.raises(TypeError):
        graph_view._step_number(reader, None, None)


@pytest.mark.parametrize('declared', [True, False])
def test_selection_keeps_the_readers_published_snapshot(tmp_path, declared):
    reader = _archive(tmp_path, [[1, 5], [9]])
    if not declared:
        for flush in reader.flushes:
            flush.pop('rows')
    path = reader.root / 'transitions' / 'part-later.parquet'
    pq.write_table(pa.table({'commit_seq': [100]}), path)
    assert graph_view._step_number(reader, None, None) == (9, dict(first=1, last=9, count=3))
    with (reader.root / '_journal' / 'flushes.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(first_seq=100, last_seq=100, parts={'transitions': path.name},
                                     rows={'transitions': 1})) + '\n')
    assert graph_view._step_number(reader, None, None) == (9, dict(first=1, last=9, count=3))
    assert graph_view._step_number(DatasetReader(reader.root), None, None) == (100, dict(first=1, last=100, count=4))


@pytest.mark.parametrize('count', [32, 400, 800, 4096, 4097])
def test_declared_small_archive_preserves_direct_reads_at_the_allocation_cap(tmp_path, monkeypatch, count):
    reader = _archive(tmp_path, [list(reversed(range(count // 2))), list(range(count // 2, count))])
    calls = []
    legacy = graph_view._legacy_step_number

    def direct(*args):
        calls.append(True)
        return legacy(*args)

    monkeypatch.setattr(graph_view, '_legacy_step_number', direct)
    assert graph_view._step_number(reader, None, count // 2) == _original(reader, None, count // 2)
    assert bool(calls) == (count <= 4096)


@pytest.mark.parametrize('rows', [None, [], 'bad', {}, {'transitions': None}, {'transitions': -1},
                                {'transitions': '5'}, {'transitions': 5.0}, {'transitions': True}])
def test_unknown_or_malformed_published_counts_use_streaming(tmp_path, monkeypatch, rows):
    reader = _archive(tmp_path, [[5, 1, 3]])
    reader.flushes[0]['rows'] = rows

    def direct(*args):
        pytest.fail('Unknown/malformed row counts cannot establish the small-allocation cap')

    monkeypatch.setattr(graph_view, '_legacy_step_number', direct)
    assert graph_view._step_number(reader, None, 4) == (3, dict(first=1, last=5, count=3))
