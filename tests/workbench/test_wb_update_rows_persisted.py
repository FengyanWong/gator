"""Record 7.283 (Astra's review of 7.281): the rows of learner updates run after the last commit - with the switch
run.advanced.update_after_dispatch - are durable before a save point and at the end, as a rows-only record of the
dataset at the last commit's number (RawDataset.record_rows), instead of counted by the save point and lost at a pause
that came before another commit."""
import json

import pytest

from gator_workbench import checkpoints as ckpt
from gator_workbench.engine import RunEngine
from gator_workbench.storage import DatasetReader, RawDataset, read_json
from helpers import execute, make_config, rows


def update_row(n, collected):
    return dict(run_id='r', update_id=f'r:u{n:09d}', updated_at='2026-10-08T10:00:00+00:00', evaluations_collected=collected,
                actor_loss=0.1, critic_loss=0.2, alpha_loss=0.0, alpha=0.01, mean_log_prob=-1.0, target_mean=0.0,
                critic_grad_norm=1.0, actor_grad_norm=1.0, learning_rate=1e-3, replay_size=n, batch_size=4,
                cumulative_updates=n, policy_version=n, update_seconds=0.01)


def commit(dataset, seq):
    assert dataset.commit(dict(evaluation_id=f'e{seq}', commit_seq=seq, rows={}))


# ---- the dataset ---------------------------------------------------------------------------------------------------
def test_a_rows_only_record_takes_the_last_commits_number_and_a_cursor_there_covers_it(tmp_path):
    dataset = RawDataset(tmp_path, enabled_tables={'evaluations', 'learner_updates'}, flush_every=100)
    commit(dataset, 1)
    commit(dataset, 2)
    assert dataset.record_rows('learner_updates', [update_row(1, 2), update_row(2, 2)])
    assert dataset.last_seq == 2 and dataset.next_seq() == 3                      # no evaluation was committed
    dataset.flush()                                                               # as a save point does right after
    commit(dataset, 3)                                                            # and the next one follows as before
    dataset.close()
    reader = DatasetReader(tmp_path)
    assert [r['cumulative_updates'] for r in reader.rows('learner_updates')] == [1, 2]
    at_two = DatasetReader(tmp_path, cutoff_seq=2)                                # a save point taken right after: both rows
    assert len(at_two.rows('learner_updates')) == 2 and at_two.row_counts()['learner_updates'] == 2


def test_nothing_is_written_for_no_rows_or_a_table_that_is_off(tmp_path):
    dataset = RawDataset(tmp_path, enabled_tables={'evaluations'}, flush_every=100)
    commit(dataset, 1)
    assert dataset.record_rows('learner_updates', [update_row(1, 1)]) is False       # the log is off: no record
    assert dataset.record_rows('evaluations', []) is False
    with pytest.raises(KeyError):
        dataset.record_rows('no_such_table', [dict(a=1)])
    assert len(dataset._buffer) == 1 and dataset.cursor()['buffered_bundles'] == 1
    dataset.close()


def test_a_record_written_after_a_flush_at_the_same_number_survives_a_crash(tmp_path):
    dataset = RawDataset(tmp_path, enabled_tables={'evaluations', 'learner_updates'}, flush_every=100)
    commit(dataset, 1)
    dataset.flush()                                                               # flushed_seq is 1
    dataset.record_rows('learner_updates', [update_row(1, 1)])                    # at number 1, in the journal only
    dataset.record_rows('learner_updates', [update_row(2, 1)])                    # a second one at the same number
    recovered = RawDataset(tmp_path, enabled_tables={'evaluations', 'learner_updates'})   # a restart, without close()
    assert recovered.recovery['rebuffered_bundles'] == 2 and recovered.last_seq == 1
    recovered.close()
    reader = DatasetReader(tmp_path)
    assert [r['cumulative_updates'] for r in reader.rows('learner_updates')] == [1, 2]
    assert len(reader.flushes) == 2 and reader.flushes[1]['first_seq'] == reader.flushes[1]['last_seq'] == 1
    dataset._buffer.clear()                                                       # the crashed writer never flushes again
    dataset.close()
    again = RawDataset(tmp_path, enabled_tables={'evaluations', 'learner_updates'})   # everything flushed: nothing twice
    assert again.recovery['rebuffered_bundles'] == 0
    again.close()
    assert DatasetReader(tmp_path).row_counts()['learner_updates'] == 2


# ---- the engine ----------------------------------------------------------------------------------------------------
def covered_rows(layout, meta):
    return len(DatasetReader(layout.data, cutoff_seq=meta['data_cursor']['commit_seq']).rows('learner_updates'))


def events_of(layout):
    return [json.loads(line)['event'] for line in (layout.logs / 'events.jsonl').read_text().splitlines()]


def test_a_pause_right_after_a_commit_keeps_the_rows_of_the_updates_it_counts(tmp_path, monkeypatch):
    """The loss Astra reproduced: the pause is taken at the top of the pass after the commit whose updates wait for the
    next dispatch - no dispatch follows, no lane is busy, the run ends. The pause save point counted three updates; their
    rows had no commit to go with."""
    original = RunEngine._poll_control

    def pause_once_updates_wait(self):
        original(self)
        if self._pending_updates and self.stop_reason is None:
            self.requested, self.stop_reason = 'pause', 'user_pause'                # as the pause command does
    monkeypatch.setattr(RunEngine, '_poll_control', pause_once_updates_wait)
    config = make_config(tmp_path, run=dict(max_evaluations=30, concurrency=1),
                         advanced=dict(updates_per_transition=3, update_after_dispatch=True))
    layout, state = execute(config, tmp_path)
    assert state == 'paused'
    meta = ckpt.read_metadata(ckpt.resolve_checkpoint(layout.run_dir, 'latest'))
    learned = meta['counters']['learner_updates']
    assert meta['kind'] == 'pause' and learned == 3                                  # the one result's three updates
    assert len(rows(layout, 'learner_updates')) == learned == covered_rows(layout, meta)
    assert 'learner_update_rows_unrecorded' not in events_of(layout)


def test_every_save_points_cursor_covers_the_rows_of_the_updates_it_counts(tmp_path):
    for concurrency in (1, 2):
        config = make_config(tmp_path / str(concurrency), run=dict(max_evaluations=30, concurrency=concurrency),
                             advanced=dict(updates_per_transition=3, update_after_dispatch=True),
                             output=dict(checkpoint_every_evaluations=10))
        layout, state = execute(config, tmp_path / str(concurrency))
        assert state == 'completed'
        points = [ckpt.read_metadata(folder) for folder in (layout.run_dir / 'checkpoints').iterdir()
                  if folder.is_dir() and (folder / 'metadata.json').is_file()]
        assert len(points) >= 3
        for meta in points:
            assert covered_rows(layout, meta) == meta['counters']['learner_updates'], (concurrency, meta['checkpoint_id'])
        assert len(rows(layout, 'learner_updates')) == max(p['counters']['learner_updates'] for p in points) > 0
        assert 'learner_update_rows_unrecorded' not in events_of(layout)
