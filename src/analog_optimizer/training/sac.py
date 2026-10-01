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
    def __init__(self, *, experiment, feature_schema=None, spec_schema=None, model_config=None, config=None,
                 input_cache_capacity=2048, topology_cache_capacity=64, reward_settings=None,
                 condition_policy='off', planned_conditions=()):
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
        self.input_cache = ObservationTensorCache(input_cache_capacity,
                                                 topology_capacity=topology_cache_capacity)
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

    def batch(self, observations):
        return batch_observations(observations, self.feature_schema, self.spec_schema, cache=self.input_cache)

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

    def update(self, transitions):
        if not transitions:
            raise ValueError('Empty SAC update')
        for transition in transitions:
            transition.validate()
            observation = transition.observation
            if (transition.reward_settings != self.reward_settings or observation.condition_policy != self.condition_policy
                    or (self.planned_conditions and observation.planned_conditions != self.planned_conditions)):
                raise ValueError('Replay reward/condition contract differs from learner')
            if transition.observation.origin != self.experiment['origin']:
                raise ValueError('Experiment/replay origin mismatch')
        current = self.batch([t.observation for t in transitions])
        following = self.batch([t.next_observation for t in transitions])
        actions = torch.tensor([t.proposal[g] for t, ids in zip(transitions, current.group_ids) for g in ids])
        rewards = torch.tensor([t.reward for t in transitions], dtype=torch.float32)
        bootstrap = torch.tensor([t.bootstrap for t in transitions], dtype=torch.bool)
        alpha = self.alpha.detach()
        with torch.no_grad():
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
                    model_config=asdict(self.model_config), config=asdict(self.config),
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
             input_cache_capacity=2048, topology_cache_capacity=64, store=None, reward_settings=None,
             condition_policy='off', planned_conditions=()):
        # This API intentionally accepts trusted checkpoints only (see class docstring).
        payload = torch.load(path, map_location='cpu', weights_only=False)
        if payload.get('contract', {}).get('checkpoint_version') != 'graph-sac-v2':
            raise ValueError('Checkpoint v1 is not supported by reward v2; explicit migration is required')
        learner = cls(experiment=experiment, feature_schema=feature_schema, spec_schema=spec_schema,
                      model_config=model_config, config=config, input_cache_capacity=input_cache_capacity,
                      topology_cache_capacity=topology_cache_capacity, reward_settings=reward_settings,
                      condition_policy=condition_policy, planned_conditions=planned_conditions)
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
