"""CPU SAC: normalized proposals, packed action dimensions and independent encoders."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import random

import numpy as np
import torch
from torch import nn
from torch.distributions import Normal
from torch.nn import functional as F
import torch_geometric

from analog_optimizer.graph.pyg_converter import FeatureSchema
from analog_optimizer.models.inputs import ObservationTensorCache, SpecSchema, batch_observations
from analog_optimizer.models import GroupActor, GraphCritic, ModelConfig
from .replay import ReplayBuffer


@dataclass(frozen=True)
class SACConfig:
    gamma: float = 0.99
    tau: float = 0.005
    learning_rate: float = 3e-4
    initial_alpha: float = 0.2
    target_entropy_per_action: float = 1.0
    max_grad_norm: float = 10.0
    alpha_learning_rate: float | None = None

    def __post_init__(self):
        if any(not math.isfinite(v) for k, v in asdict(self).items() if k != 'alpha_learning_rate'):
            raise ValueError('SAC hyperparameters must be finite')
        if not 0 <= self.gamma <= 1 or not 0 < self.tau <= 1:
            raise ValueError('Invalid discount/target mixing coefficient')
        if min(self.learning_rate, self.initial_alpha, self.target_entropy_per_action, self.max_grad_norm) <= 0:
            raise ValueError('SAC scale parameters must be positive')
        if self.alpha_learning_rate is not None and (isinstance(self.alpha_learning_rate, bool)
                or not isinstance(self.alpha_learning_rate, (int, float))
                or not math.isfinite(self.alpha_learning_rate) or self.alpha_learning_rate <= 0):
            raise ValueError('Alpha learning rate must be positive and finite, or None to use the learning rate')


def temperature_loss(log_alpha, log_prob, action_counts, entropy_per_action):
    target_entropy = -entropy_per_action * action_counts
    return -(log_alpha * (log_prob.detach() + target_entropy)).mean()


@torch.no_grad()
def soft_update(target, source, tau):
    for target_parameter, parameter in zip(target.parameters(), source.parameters(), strict=True):
        target_parameter.lerp_(parameter, tau)


def source_digest():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*.py')):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class SACLearner:
    """No autograd through backend/projection; Q always uses normalized proposal z.

    Checkpoints are local trusted Python/Torch artifacts. They contain replay
    dataclasses and must never be loaded from untrusted sources.
    """
    # With a discount of exactly 0 the bootstrap term is multiplied by zero, so update() leaves out the next states'
    # batch, actor forward and target critics and keeps everything else bit for bit (record 7.221). Tests switch it off
    # on one learner to compare with the full calculation; it never changes the configured gamma.
    zero_gamma_shortcut = True

    # Record 7.221: 8,192 entries (was 2,048) hold every distinct state of a full 10,000-transition replay of the recorded
    # mscr_ota7t runs (~4.6 kB of tensors each); at 2,048 a full replay hit 29 % and a learner step took 29 % longer. The
    # byte bound only caps unexpectedly large graphs.
    INPUT_CACHE_CAPACITY, INPUT_CACHE_MAX_BYTES = 8192, 256 * 2**20

    def __init__(self, *, experiment, feature_schema=None, spec_schema=None, model_config=None, config=None,
                 input_cache_capacity=INPUT_CACHE_CAPACITY, topology_cache_capacity=64, reward_settings=None,
                 condition_policy='off', planned_conditions=(), input_cache_max_bytes=INPUT_CACHE_MAX_BYTES):
        from analog_optimizer.measurements.specs import RewardSettings
        self.reward_settings = RewardSettings() if reward_settings is None else reward_settings
        if not isinstance(self.reward_settings, RewardSettings) or condition_policy not in ('off', 'always', 'after_nominal'):
            raise ValueError('Typed reward settings and a supported condition policy are required')
        self.condition_policy, self.planned_conditions = condition_policy, tuple(planned_conditions)
        if condition_policy != 'off' and len(self.planned_conditions) < 2:
            raise ValueError('Robust learner requires the complete condition plan')
        self.feature_schema, self.spec_schema = feature_schema or FeatureSchema(), spec_schema or SpecSchema()
        self.model_config, self.config = model_config or ModelConfig(), config or SACConfig()
        if (experiment.get('origin') not in ('real', 'synthetic') or not experiment.get('split')
                or not experiment.get('designs')):
            raise ValueError('Experiment must identify origin, split and design/mapping provenance')
        self.experiment = deepcopy(experiment)
        self.input_cache = ObservationTensorCache(input_cache_capacity, topology_capacity=topology_cache_capacity,
                                                  max_bytes=input_cache_max_bytes)
        args = self.feature_schema, self.spec_schema, self.model_config
        self.actor = GroupActor(*args)
        self.critics = nn.ModuleList([GraphCritic(*args), GraphCritic(*args)])
        self.targets = deepcopy(self.critics).requires_grad_(False).eval()
        self.log_alpha = nn.Parameter(torch.tensor(math.log(self.config.initial_alpha)))
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=self.config.learning_rate)
        self.critic_optimizer = torch.optim.Adam(self.critics.parameters(), lr=self.config.learning_rate)
        alpha_rate = self.config.learning_rate if self.config.alpha_learning_rate is None else self.config.alpha_learning_rate
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_rate)
        self.updates = 0

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def batch(self, observations, *, digests=None):
        """`digests`: see ``update``; only an owner that keeps the observations unchanged may pass them."""
        return batch_observations(observations, self.feature_schema, self.spec_schema, cache=self.input_cache,
                                  digests=digests)

    def skips_unused_bootstrap(self):
        """True when update() leaves out the next-state work: the run's own discount is exactly zero."""
        return self.zero_gamma_shortcut and self.config.gamma == 0

    def _batch(self, observations, digests):
        # Subclasses may override batch(observations) without the digests keyword: they then get the plain call.
        return self.batch(observations) if digests is None else self.batch(observations, digests=digests)

    def _draw_skipped_next_action_noise(self, next_observations):
        """What actor.sample(next-state batch) draws from the default torch generator, without the network:
        GroupActor.sample calls Normal(mu, std).rsample(), one entry per active action - every mutable parameter group,
        which the transition contract keeps equal between a state and its next state - and rsample draws
        torch.empty(shape).normal_(). The same shape, dtype and device here leave the generator exactly where the full
        calculation leaves it, so the current-state actor sample and every later action stay identical."""
        count = sum(group.mutable for o in next_observations for group in o.graph.parameter_groups)
        reference = next(self.actor.parameters())
        Normal(torch.zeros(count, dtype=reference.dtype, device=reference.device),
               torch.ones(count, dtype=reference.dtype, device=reference.device)).rsample()

    @torch.no_grad()
    def act(self, observations, *, deterministic=False):
        batch = self.batch(observations)
        return batch.proposals(self.actor.sample(batch, deterministic=deterministic).actions)

    def _optimize(self, optimizer, loss, parameters):
        if not torch.isfinite(loss):
            raise FloatingPointError('Non-finite SAC loss')
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        norm = nn.utils.clip_grad_norm_(list(parameters), self.config.max_grad_norm, error_if_nonfinite=True)
        optimizer.step()
        return float(norm)

    def update(self, transitions, *, digests=None):
        """One SAC update on `transitions`, which it only reads.

        `digests`: optional (observation, next observation) ``observation_digest`` pairs, one per transition, from an
        owner that lends its stored transitions unchanged (``ReplayBuffer.update_learner``); they only spare the input
        cache from re-hashing those observations. With a discount of exactly 0 the next states are not batched or
        evaluated (see ``zero_gamma_shortcut``); every result and the random-number state are unchanged."""
        if not transitions:
            raise ValueError('Empty SAC update')
        if digests is not None and len(digests) != len(transitions):
            raise ValueError('One digest pair per transition is required')
        for transition in transitions:
            transition.validate()
            observation = transition.observation
            if (transition.reward_settings != self.reward_settings or observation.condition_policy != self.condition_policy
                    or (self.planned_conditions and observation.planned_conditions != self.planned_conditions)):
                raise ValueError('Replay reward/condition contract differs from learner')
            if transition.observation.origin != self.experiment['origin']:
                raise ValueError('Experiment/replay origin mismatch')
        skip = self.skips_unused_bootstrap()
        current = self._batch([t.observation for t in transitions], None if digests is None else [d[0] for d in digests])
        following = None if skip else self._batch([t.next_observation for t in transitions],
                                                  None if digests is None else [d[1] for d in digests])
        actions = torch.tensor([t.proposal[g] for t, ids in zip(transitions, current.group_ids) for g in ids])
        rewards = torch.tensor([t.reward for t in transitions], dtype=torch.float32)
        alpha = self.alpha.detach()
        with torch.no_grad():
            if skip:
                # gamma == 0: rewards + 0 * (finite bootstrap term) is the reward itself, bit for bit (only a reward of
                # -0.0 could come out as +0.0 there; equal in every comparison and loss).
                self._draw_skipped_next_action_noise([t.next_observation for t in transitions])
                target = rewards
            else:
                bootstrap = torch.tensor([t.bootstrap for t in transitions], dtype=torch.bool)
                next_sample = self.actor.sample(following)
                next_q = torch.minimum(*(q(following, next_sample.actions) for q in self.targets))
                target = rewards + self.config.gamma * torch.where(
                    bootstrap, next_q - alpha * next_sample.log_prob, torch.zeros_like(next_q))
        q1, q2 = (q(current, actions) for q in self.critics)
        critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
        critic_norm = self._optimize(self.critic_optimizer, critic_loss, self.critics.parameters())
        self.critic_optimizer.zero_grad(set_to_none=True)
        self.critics.requires_grad_(False)
        try:
            sample = self.actor.sample(current)
            policy_q = torch.minimum(*(q(current, sample.actions) for q in self.critics))
            actor_loss = (alpha * sample.log_prob - policy_q).mean()
            actor_norm = self._optimize(self.actor_optimizer, actor_loss, self.actor.parameters())
        finally:
            self.critics.requires_grad_(True)
        alpha_loss = temperature_loss(self.log_alpha, sample.log_prob,
                                      current.action_counts.float(), self.config.target_entropy_per_action)
        self._optimize(self.alpha_optimizer, alpha_loss, [self.log_alpha])
        soft_update(self.targets, self.critics, self.config.tau)
        self.updates += 1
        return dict(updates=self.updates, critic_loss=float(critic_loss.detach()),
                    actor_loss=float(actor_loss.detach()), alpha_loss=float(alpha_loss.detach()),
                    alpha=float(self.alpha.detach()), mean_log_prob=float(sample.log_prob.detach().mean()),
                    target_mean=float(target.mean()), critic_grad_norm=critic_norm, actor_grad_norm=actor_norm,
                    action_counts=current.action_counts.tolist())

    def contract(self):
        from analog_optimizer.measurements.specs import REWARD_VERSION, CLEARANCE_RULE
        return dict(checkpoint_version='graph-sac-v2', graph_schema='1.0',
                    reward_version=REWARD_VERSION, reward_settings=asdict(self.reward_settings),
                    clearance_rule=CLEARANCE_RULE, condition_policy=self.condition_policy,
                    planned_conditions=[None if c is None else asdict(c) for c in self.planned_conditions],
                    failure_policy='continue_attributed',
                    feature_schema=asdict(self.feature_schema), spec_schema=asdict(self.spec_schema),
                    normalizer='fixed-references-signed-log1p-v1', action_version='absolute-group-v1',
                    critic_action='normalized_proposal', budget='finite_horizon_termination',
                    model_config=self.model_config.to_dict(), config=asdict(self.config),
                    experiment=self.experiment, device='cpu', code_sha256=source_digest(),
                    torch_version=str(torch.__version__), pyg_version=str(torch_geometric.__version__))

    def save(self, path, replay, *, run_state=None, preflight=None):
        if replay.origin != self.experiment['origin']:
            raise ValueError('Checkpoint replay origin mismatch')
        payload = dict(contract=self.contract(), actor=self.actor.state_dict(), critics=self.critics.state_dict(),
                       targets=self.targets.state_dict(), log_alpha=self.log_alpha.detach(),
                       actor_optimizer=self.actor_optimizer.state_dict(),
                       critic_optimizer=self.critic_optimizer.state_dict(), alpha_optimizer=self.alpha_optimizer.state_dict(),
                       replay=replay.state_dict(copy=False) if replay.store is None else replay.manifest(),
                       replay_format='embedded-v1' if replay.store is None else 'replay-ids-v1',
                       updates=self.updates, run_state=deepcopy(run_state or {}),
                       torch_rng=torch.get_rng_state(), python_rng=random.getstate(), numpy_rng=np.random.get_state(),
                       torch_threads=torch.get_num_threads(), deterministic=torch.are_deterministic_algorithms_enabled())
        from analog_optimizer.recording.checkpoint import atomic_torch_save
        atomic_torch_save(payload, path, preflight=preflight)
        return payload['replay'].get('database')

    @classmethod
    def load(cls, path, *, experiment, feature_schema=None, spec_schema=None, model_config=None, config=None,
             input_cache_capacity=INPUT_CACHE_CAPACITY, topology_cache_capacity=64, store=None, reward_settings=None,
             condition_policy='off', planned_conditions=(), input_cache_max_bytes=INPUT_CACHE_MAX_BYTES):
        # This API intentionally accepts trusted checkpoints only (see class docstring).
        payload = torch.load(path, map_location='cpu', weights_only=False)
        if payload.get('contract', {}).get('checkpoint_version') != 'graph-sac-v2':
            raise ValueError('Checkpoint v1 is not supported by reward v2; explicit migration is required')
        learner = cls(experiment=experiment, feature_schema=feature_schema, spec_schema=spec_schema,
                      model_config=model_config, config=config, input_cache_capacity=input_cache_capacity,
                      topology_cache_capacity=topology_cache_capacity, reward_settings=reward_settings,
                      condition_policy=condition_policy, planned_conditions=planned_conditions,
                      input_cache_max_bytes=input_cache_max_bytes)
        if payload['contract'] != learner.contract():
            raise ValueError('Checkpoint schema/action/config/experiment/code/dependency mismatch')
        learner.actor.load_state_dict(payload['actor'])
        learner.critics.load_state_dict(payload['critics'])
        learner.targets.load_state_dict(payload['targets'])
        with torch.no_grad():
            learner.log_alpha.copy_(payload['log_alpha'])
        learner.actor_optimizer.load_state_dict(payload['actor_optimizer'])
        learner.critic_optimizer.load_state_dict(payload['critic_optimizer'])
        learner.alpha_optimizer.load_state_dict(payload['alpha_optimizer'])
        learner.updates = payload['updates']
        if payload.get('replay_format') == 'replay-ids-v1':
            if store is None:
                raise ValueError('This checkpoint requires its original recording database')
            replay = ReplayBuffer.from_manifest(payload['replay'], store)
        else:
            replay = ReplayBuffer.from_state_dict(payload['replay'])
        if replay.origin != learner.experiment['origin']:
            raise ValueError('Checkpoint replay origin mismatch')
        torch.set_num_threads(payload['torch_threads'])
        torch.use_deterministic_algorithms(payload['deterministic'])
        torch.set_rng_state(payload['torch_rng'])
        random.setstate(payload['python_rng'])
        np.random.set_state(payload['numpy_rng'])
        return learner, replay, payload['run_state']
