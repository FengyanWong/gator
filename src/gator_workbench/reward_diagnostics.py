"""Read-only steering check from existing scored evaluations and learner updates."""
from __future__ import annotations
import math

VERDICT = ('The network is still choosing close to random: the reward differences are smaller '
           'than its exploration bonus.')


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def steering(evaluations, updates):
    """Linear-interpolated empirical p90-p10; a missing latest diagnostic stays unknown."""
    ordered = sorted(evaluations, key=lambda r: (r.get('completion_index') or 0, r.get('dispatch_index') or 0))
    rewards = [
        r['reward'] for r in ordered if _finite(r.get('reward'))][-50:]
    rewards.sort()
    def quantile(p):
        position = (len(rewards) - 1) * p
        low = int(position)
        return rewards[low] + (rewards[min(low + 1, len(rewards) - 1)] - rewards[low]) * (position - low)
    spread = quantile(.9) - quantile(.1) if len(rewards) >= 2 else None
    latest = updates[-1] if updates else {}
    alpha, log_prob = latest.get('alpha'), latest.get('mean_log_prob')
    bonus = alpha * -log_prob if _finite(alpha) and _finite(log_prob) else None
    return dict(scored_designs=len(rewards), reward_spread=spread, exploration_bonus=bonus,
                verdict=VERDICT if spread is not None and bonus is not None and spread < bonus else None)


def load(run_dir):
    from .layout import RunLayout
    from .storage.dataset import DatasetReader
    reader = DatasetReader(RunLayout(run_dir).data)
    total = reader.row_counts().get('evaluations', 0)
    limit = min(64, total)
    while True:
        rows = reader.tail('evaluations', limit, ['completion_index', 'dispatch_index', 'reward']).to_pylist()
        if sum(_finite(r.get('reward')) for r in rows) >= 50 or limit >= total:
            break
        limit = min(total, max(1, limit * 2))
    return steering(rows, reader.tail('learner_updates', 1, ['alpha', 'mean_log_prob']).to_pylist())
