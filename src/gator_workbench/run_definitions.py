"""Definitions of the run engine that other modules use without the engine itself: the lane statuses that count as
infrastructure failures, the decoding of a normalized action, the learner contract's experiment identity.

Moved from engine.py by the refactoring (docs/plan-refactoring.md).
"""
from __future__ import annotations

import math

from .schema import WorkbenchConfig


INFRASTRUCTURE_FAILURES = ('timeout', 'transport_error', 'license_error', 'backend_error')


def optimizer_of(manifest):
    """The recorded optimizer; manifests from before the choice are SAC runs."""
    return (manifest.get('architecture') or {}).get('optimizer', 'sac')


def saves_rl_model(config: WorkbenchConfig) -> bool:
    """Bayesian search never trains the learner, even when checkpoints are enabled."""
    return config.run.optimizer == 'sac' and bool(config.output.save_checkpoints)


def require_rl_model(manifest):
    """Reject historical Bayesian save points as well as runs that now save none."""
    if optimizer_of(manifest) == 'bayes':
        raise RunRejected('Bayesian optimization runs do not train an RL model. Their search cannot be resumed '
                          'and their saved weights cannot be loaded for fine-tuning or evaluation.', code='no_rl_model')


def decode_action(z, lower, upper, scale):
    """Physical value a normalized action decodes to BEFORE projection (mirrors ActionMapper;
    a test pins the two together)."""
    if z in (-1, 1):
        return lower if z == -1 else upper
    fraction = (z + 1) / 2
    if scale == 'log':
        return math.exp((1 - fraction) * math.log(lower) + fraction * math.log(upper))
    return (1 - fraction) * lower + fraction * upper


def learner_experiment(config: WorkbenchConfig, task, task_hash):
    """The learner contract identity. Budgets, concurrency and output settings are deliberately
    excluded so that extending a budget does not turn a resume into a different experiment."""
    adv = config.run.advanced
    result = dict(origin=task.origin, split=config.research.split, run_kind='gator-workbench-v1',
                designs=[dict(task_key=task.task_key, task_definition_hash=task_hash,
                              netlist_sha256=task.circuit.get('netlist_sha256'),
                              parser_config_sha256=task.circuit.get('parser_config_sha256'))],
                seed=config.run.seed,
                collector=dict(episode_length=adv.episode_length, batch_size=adv.batch_size,
                               warmup_transitions=adv.warmup_transitions, update_every=adv.update_every,
                               updates_per_transition=adv.updates_per_transition,
                               episode_terminates_on_success=adv.episode_terminates_on_success,
                               replay_capacity=adv.replay_capacity))
    if config.run.rehearsal is not None:
        result['rehearsal'] = config.run.rehearsal.model_dump(mode='json')
    return result


class RunRejected(ValueError):
    def __init__(self, message, *, report=None, code='rejected'):
        super().__init__(message)
        self.report, self.code = report, code
