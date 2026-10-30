"""What the collectors of training data do the same way: the warm-up's random proposal, and a timed learner update on
a sampled batch. Shared by training/runner.py, training/parallel.py, evaluation/benchmark.py and the workbench's run
engine since 2026-10-09 (plan-refactoring E3); each keeps its own recording and history."""
from time import perf_counter


def random_proposal(rng, group_ids):
    """A normalized action in [-1, 1] per parameter group, drawn from `rng` in the groups' order: the order of the draws
    is part of every seeded run's reproducibility."""
    return {group: rng.uniform(-1, 1) for group in group_ids}


def timed_update(learner, replay, batch_size):
    """One learner update on a batch sampled from `replay`: (its record, its seconds)."""
    start = perf_counter()
    update = learner.update(replay.sample(batch_size))
    update_seconds = perf_counter() - start
    return update, update_seconds
