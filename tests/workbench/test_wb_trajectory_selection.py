"""Selecting archive replay keeps exact transitions without decoding unrelated Python rows."""
from contextlib import closing
from dataclasses import replace
import json
import shutil

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from analog_optimizer.recording import codec
from gator_workbench.storage import RawDataset
from gator_workbench.trajectory import TrajectoryLoader
from helpers import execute, make_config

pytestmark = pytest.mark.xdist_group('test_wb_trajectory_selection')


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    root = tmp_path_factory.mktemp('selected-archive')
    config = make_config(root, run=dict(max_evaluations=16, network=dict(hidden_dim=8, heads=2, layers=1)),
                         output=dict(flush_every_evaluations=4))
    layout, state = execute(config, root)
    assert state == 'completed'
    return layout.run_dir


@pytest.fixture
def archive(source, tmp_path):
    run = tmp_path / 'mock' / 'archive'
    shutil.copytree(source / 'data', run / 'data')
    return run


def _fingerprints(transitions):
    return [transition.fingerprint() for transition in transitions]


def _edit_rows(run, table, edit):
    for path in TrajectoryLoader(run).reader.parts(table):
        with pq.ParquetFile(path) as part:
            original = part.read()
        rows = original.to_pylist()
        for row in rows:
            edit(row)
        schema = pa.schema([field.with_nullable(field.nullable or any(row[field.name] is None for row in rows))
                            for field in original.schema])
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def test_cold_subset_matches_full_load_and_keeps_public_state_cache_complete(archive):
    full = TrajectoryLoader(archive).transitions()
    candidates = {full[-1].candidate_id, full[2].candidate_id}
    loader = TrajectoryLoader(archive)
    selected = loader.transitions(candidate_ids=candidates)
    assert _fingerprints(selected) == _fingerprints([t for t in full if t.candidate_id in candidates])
    assert loader._states is None
    assert loader.state_rows() == TrajectoryLoader(archive).state_rows()
    assert _fingerprints(loader.transitions()) == _fingerprints(full)


def test_only_selected_rows_are_converted_to_python(archive, monkeypatch):
    loader = TrajectoryLoader(archive)
    rows = loader.transition_rows()
    chosen = [row for row in rows if row['replay_eligible_archive']][2:4]
    wanted = dict(transitions={row['candidate_id'] for row in chosen},
                  states={row[key] for row in chosen for key in ('state_ref', 'next_state_ref')})
    decoded, original = dict(states=0, transitions=0), loader.reader.iter_batches

    class Batch:
        def __init__(self, table, batch):
            self.table, self.batch = table, batch

        def __getitem__(self, key):
            return self.batch[key]

        def filter(self, mask):
            return Batch(self.table, self.batch.filter(mask))

        def to_pylist(self):
            result = self.batch.to_pylist()
            key = 'state_id' if self.table == 'states' else 'candidate_id'
            assert all(row[key] in wanted[self.table] for row in result)
            decoded[self.table] += len(result)
            return result

    def tracked(table):
        with closing(original(table, batch_size=2)) as batches:
            for batch in batches:
                yield Batch(table, batch)

    def whole_table(*args, **kwargs):
        pytest.fail('A subset must not materialize an entire table')

    monkeypatch.setattr(loader.reader, 'iter_batches', tracked)
    monkeypatch.setattr(loader.reader, 'rows', whole_table)
    result = loader.transitions(candidate_ids=wanted['transitions'])
    assert len(result) == 2 and decoded == {table: len(ids) for table, ids in wanted.items()}


@pytest.mark.parametrize('candidates', [set(), {'absent'}, []])
def test_empty_and_missing_selections_do_not_read_states(archive, candidates, monkeypatch):
    loader = TrajectoryLoader(archive)
    original = loader.reader.iter_batches

    def tracked(table, *args, **kwargs):
        assert table != 'states'
        yield from original(table, *args, **kwargs)

    monkeypatch.setattr(loader.reader, 'iter_batches', tracked)
    assert loader.transitions(candidate_ids=candidates) == [] and loader._states is None


def test_subset_reuses_a_loaded_state_cache_and_never_aliases_observations(archive, monkeypatch):
    loader = TrajectoryLoader(archive)
    cached = loader.state_rows()
    expected = loader.transitions()[1]
    candidate = expected.candidate_id
    fingerprint = expected.fingerprint()
    original = loader.reader.iter_batches

    def tracked(table, *args, **kwargs):
        assert table != 'states'
        yield from original(table, *args, **kwargs)

    monkeypatch.setattr(loader.reader, 'iter_batches', tracked)
    first = loader.transitions(candidate_ids=[candidate, candidate])[0]
    first.observation.metrics['score'] = 123456.
    second = loader.transitions(candidate_ids={candidate})[0]
    assert second.fingerprint() == fingerprint and loader.state_rows() is cached
    assert first.observation.graph is not second.observation.graph


def test_subset_calls_do_not_retain_or_share_selected_states(archive):
    loader = TrajectoryLoader(archive)
    candidate = loader.transition_rows()[1]['candidate_id']
    first = loader.transitions(candidate_ids={candidate})[0]
    fingerprint = first.fingerprint()
    first.next_observation.metrics['score'] = 123456.
    assert loader.transitions(candidate_ids={candidate})[0].fingerprint() == fingerprint
    assert loader._states is None


def test_fixed_snapshot_and_last_duplicate_state_match_the_full_reader(archive):
    loader = TrajectoryLoader(archive)
    full = TrajectoryLoader(archive).transitions()
    candidate = full[2].candidate_id
    row = next(row for row in loader.transition_rows() if row['candidate_id'] == candidate)
    state = TrajectoryLoader(archive).state_rows()[row['state_ref']]
    values = codec.untree(json.loads(state['observation_fields_json']))
    values['job_id'] = 'last-duplicate'
    values['condition_results'] = (replace(values['condition_results'][0], job_id=values['job_id']),
                                   *values['condition_results'][1:])
    state['observation_fields_json'] = json.dumps(codec.tree(values))
    writer = RawDataset(archive / 'data')
    writer.record_rows('states', [state])
    writer.close()
    assert loader.transitions(candidate_ids={candidate})[0].fingerprint() == full[2].fingerprint()
    expected = TrajectoryLoader(archive).transitions(candidate_ids={candidate})[0]
    assert expected.observation.job_id == 'last-duplicate'
    assert expected.fingerprint() == next(t for t in TrajectoryLoader(archive).transitions()
                                          if t.candidate_id == candidate).fingerprint()


def test_cutoff_and_unlisted_parts_preserve_selected_order(archive):
    loader = TrajectoryLoader(archive, cutoff_seq=8)
    full = loader.transitions()
    candidates = {t.candidate_id for t in TrajectoryLoader(archive).transitions()}
    # Unlisted corrupt parts must never be opened.
    (archive / 'data' / 'states' / 'part-999999.parquet').write_bytes(b'not a published part')
    (archive / 'data' / 'transitions' / 'part-999999.parquet').write_bytes(b'not a published part')
    actual = TrajectoryLoader(archive, cutoff_seq=8).transitions(candidate_ids=candidates)
    assert _fingerprints(actual) == _fingerprints(full)


@pytest.mark.parametrize('field,value', [('reward', None), ('truncated', True), ('next_state_ref', None)])
def test_ineligible_selected_rows_do_not_load_states(archive, field, value, monkeypatch):
    candidate = TrajectoryLoader(archive).transitions()[0].candidate_id
    _edit_rows(archive, 'transitions', lambda row: row.update({field: value}) if row['candidate_id'] == candidate else None)
    loader = TrajectoryLoader(archive)
    original = loader.reader.iter_batches

    def tracked(table, *args, **kwargs):
        assert table != 'states'
        yield from original(table, *args, **kwargs)

    monkeypatch.setattr(loader.reader, 'iter_batches', tracked)
    assert loader.transitions(candidate_ids={candidate}) == []


def test_legacy_rewards_and_invalid_selected_transitions_still_fail(archive):
    candidates = [t.candidate_id for t in TrajectoryLoader(archive).transitions()]
    _edit_rows(archive, 'transitions', lambda row: row.update(reward_version='legacy')
               if row['candidate_id'] == candidates[0] else None)
    with pytest.raises(ValueError, match='explicit migration'):
        TrajectoryLoader(archive).transitions(candidate_ids={candidates[0]})
    assert len(TrajectoryLoader(archive).transitions(candidate_ids={candidates[1]})) == 1
    _edit_rows(archive, 'transitions', lambda row: row.update(reward=999.)
               if row['candidate_id'] == candidates[1] else None)
    with pytest.raises(ValueError, match='Reward/status/measurement contract mismatch'):
        TrajectoryLoader(archive).transitions(candidate_ids={candidates[1]})
    assert TrajectoryLoader(archive).transitions(candidate_ids={candidates[1]}, validate=False)[0].reward == 999.


def test_missing_selected_state_is_not_silently_dropped(archive):
    candidate = TrajectoryLoader(archive).transitions()[0].candidate_id
    _edit_rows(archive, 'transitions', lambda row: row.update(state_ref='missing-selected-state')
               if row['candidate_id'] == candidate else None)
    with pytest.raises(KeyError, match='missing-selected-state'):
        TrajectoryLoader(archive).transitions(candidate_ids={candidate})


def test_raw_selection_preserves_stable_commit_order(archive):
    for path in TrajectoryLoader(archive).reader.parts('transitions'):
        with pq.ParquetFile(path) as part:
            table = part.read()
        rows = table.to_pylist()[::-1]
        for row in rows:
            row['commit_seq'] %= 3
        pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    loader = TrajectoryLoader(archive)
    full = loader.transition_rows()
    candidates = {row['candidate_id'] for row in full[::2]}
    assert loader.transition_rows(candidate_ids=candidates) == [row for row in full if row['candidate_id'] in candidates]


def test_filter_error_closes_the_current_batch_reader(archive, monkeypatch):
    loader = TrajectoryLoader(archive)
    closed = []

    class BrokenBatch:
        def __getitem__(self, key):
            return pa.array(['some-candidate'])

        def filter(self, mask):
            raise ValueError('fixture filter failure')

    def batches(table):
        try:
            yield BrokenBatch()
        finally:
            closed.append(table)

    monkeypatch.setattr(loader.reader, 'iter_batches', batches)
    with pytest.raises(ValueError, match='fixture filter failure'):
        loader.transitions(candidate_ids={'some-candidate'})
    assert closed == ['transitions']
