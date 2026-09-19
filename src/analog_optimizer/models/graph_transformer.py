"""Shared SAC heads; legacy import path retained for the M4/M5 API."""
from __future__ import annotations

from dataclasses import dataclass
import math

import torch
from torch import nn
from torch.nn import functional as F
from torch.distributions import Normal

from .inputs import SpecSchema
from analog_optimizer.graph.pyg_converter import FeatureSchema
from .encoders import ModelConfig, PortGraphEncoder, build_encoder, mlp, segment_sum, segment_mean


@dataclass
class PolicySample:
    actions: torch.Tensor
    log_prob: torch.Tensor
    mean_actions: torch.Tensor


class GroupActor(nn.Module):
    def __init__(self, feature_schema=None, spec_schema=None, config=None):
        super().__init__()
        self.config = config or ModelConfig()
        self.encoder = build_encoder(feature_schema or FeatureSchema(), spec_schema or SpecSchema(), self.config)
        self.head = mlp(self.config.hidden_dim, self.config.hidden_dim, 2)

    def distribution(self, batch):
        _, groups, _ = self.encoder(batch)
        mu, log_std = self.head(groups[batch.active]).unbind(-1)
        return mu, log_std.clamp(self.config.log_std_min, self.config.log_std_max)

    def sample(self, batch, *, deterministic=False):
        mu, log_std = self.distribution(batch)
        distribution = Normal(mu, log_std.exp())
        raw = mu if deterministic else distribution.rsample()
        actions = torch.tanh(raw)
        # Stable log(1 - tanh(raw)^2), even for saturated actions.
        correction = 2 * (math.log(2) - raw - F.softplus(-2 * raw))
        per_group = distribution.log_prob(raw) - correction
        return PolicySample(actions, segment_sum(per_group, batch.action_batch, batch.size), mu.tanh())


class GraphCritic(nn.Module):
    def __init__(self, feature_schema=None, spec_schema=None, config=None):
        super().__init__()
        config = config or ModelConfig()
        self.encoder = build_encoder(feature_schema or FeatureSchema(), spec_schema or SpecSchema(), config,
                                         action_conditioned=True)
        self.head = mlp(config.hidden_dim * 3, config.hidden_dim, 1)

    def forward(self, batch, actions):
        nodes, groups, context = self.encoder(batch, actions)
        pooled = segment_mean(nodes, batch.node_batch, batch.size)
        group_pool = segment_mean(groups[batch.active], batch.action_batch, batch.size)
        return self.head(torch.cat((pooled, group_pool, context), dim=-1)).squeeze(-1)
