"""Read-only steering check from existing scored evaluations and learner updates."""
from __future__ import annotations
import os
from pathlib import Path
from .layout import RunLayout
from .spec_equations import is_finite_number

VERDICT = ('The network is still choosing close to random: the reward differences are smaller '
           'than its exploration bonus.')


def steering(evaluations, updates):
    """Linear-interpolated empirical p90-p10; a missing latest diagnostic stays unknown."""
    ordered = sorted(evaluations, key=lambda r: (r.get('completion_index') or 0, r.get('dispatch_index') or 0))
    rewards = [
        r['reward'] for r in ordered if is_finite_number(r.get('reward'))][-50:]
    rewards.sort()
    def quantile(p):
        position = (len(rewards) - 1) * p
        low = int(position)
        return rewards[low] + (rewards[min(low + 1, len(rewards) - 1)] - rewards[low]) * (position - low)
    spread = quantile(.9) - quantile(.1) if len(rewards) >= 2 else None
    latest = updates[-1] if updates else {}
    alpha, log_prob = latest.get('alpha'), latest.get('mean_log_prob')
    bonus = alpha * -log_prob if is_finite_number(alpha) and is_finite_number(log_prob) else None
    return dict(scored_designs=len(rewards), reward_spread=spread, exploration_bonus=bonus,
                verdict=VERDICT if spread is not None and bonus is not None and spread < bonus else None)


_STEERING: dict = {}                    # data folder -> (tables_version, answer)


def load(run_dir):
    """The steering check of a run. The run status asks for it on every poll (1.5 s apart), and each answer read 7 to 18
    data parts (90-590 ms on the 9p-mounted repository), so it is kept until a flush changes the tables. The parts are
    read through DatasetReader.tail, as always: whatever the reader does to a part (an old part's missing columns) holds."""
    data = RunLayout(run_dir).data
    return dict(kept(_STEERING, str(data), tables_version(data), lambda: _load(data)))


def _load(data):
    from .storage.dataset import DatasetReader  # lazy: tests patch storage.dataset.DatasetReader
    reader = DatasetReader(data)
    total = reader.row_counts().get('evaluations', 0)
    limit = min(64, total)
    while True:
        rows = reader.tail('evaluations', limit, ['completion_index', 'dispatch_index', 'reward']).to_pylist()
        if sum(is_finite_number(r.get('reward')) for r in rows) >= 50 or limit >= total:
            break
        limit = min(total, max(1, limit * 2))
    return steering(rows, reader.tail('learner_updates', 1, ['alpha', 'mean_log_prob']).to_pylist())


# ---------------------------------------------------------------- answers kept while the files they come from are unchanged
# Shared with reachability.py and corner_check.py: their answers come from the same run files.
def file_identity(path):
    """A file's stat as a cache key, as checkpoints.verify_files keys its display digests; None when there is no file."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def tables_version(data_dir):
    """A run's recorded tables as a cache key: the stat of their flush journal. A data part belongs to the tables only once
    a flush record lists it, and is never rewritten after (storage/dataset.py), so the tables change only when a flush
    appends a record there."""
    return file_identity(Path(data_dir) / '_journal' / 'flushes.jsonl')


def kept(cache: dict, key, version, compute):
    """compute(), kept in `cache` under `key` while `version` stays the same. One entry per key: a new version replaces
    the old one. The caller works `version` out BEFORE compute() reads the files, so a file that changes in between is read
    again next time, never kept under the old version. An exception is not kept: the next call tries again."""
    entry = cache.get(key)
    if entry is not None and entry[0] == version:
        return entry[1]
    value = compute()
    cache[key] = (version, value)
    return value
