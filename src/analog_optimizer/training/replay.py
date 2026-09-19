"""Replay admission validates executed sizing and excludes validation/infrastructure results."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random

from analog_optimizer.envs.sizing import Observation, graph_contract, same_parameters, parameter_rows
from analog_optimizer.measurements.specs import SpecificationEvaluator
from analog_optimizer.models.inputs import validate_observation
from analog_optimizer.parameters.actions import ActionMapper


@dataclass(frozen=True)
class Transition:
    observation: Observation
    proposal: dict[str, float]
    reward: float
    next_observation: Observation
    terminated: bool
    truncated: bool
    bootstrap: bool
    applied_parameters: dict[tuple[str, str], float]
    candidate_id: str
    record_path: str
    action_version: str = 'absolute-group-v1'

    def validate(self):
        first, last = self.observation, self.next_observation
        validate_observation(first)
        validate_observation(last)
        if first.status != 'ok' or first.remaining_steps < 1:
            raise ValueError('Cannot act from a terminal or failed state')
        if first.origin != last.origin or first.condition != last.condition:
            raise ValueError('Transition origin/nominal condition changed')
        if first.specs != last.specs or graph_contract(first.graph) != graph_contract(last.graph):
            raise ValueError('Transition changed topology, action contract or goal')
        if self.action_version != 'absolute-group-v1':
            raise ValueError('Unsupported action semantics')
        if any(type(flag) is not bool for flag in (self.terminated, self.truncated, self.bootstrap)):
            raise ValueError('Termination flags must be booleans')
        if self.truncated or self.bootstrap != (not self.terminated):
            raise ValueError('Truncated/invalid bootstrap transition cannot enter nominal replay')
        if last.remaining_steps != first.remaining_steps - 1 or (last.remaining_steps == 0 and not self.terminated):
            raise ValueError('Finite-horizon budget must terminate without bootstrap')
        action = ActionMapper(first.graph).legalize(self.proposal)
        actual = last.graph.assignments({g.id: g.value for g in last.graph.parameter_groups if g.mutable})
        if not same_parameters(actual, action.assignments) or not same_parameters(actual, self.applied_parameters):
            raise ValueError('Proposed, executed and next-state parameters differ')
        initial_evaluation = SpecificationEvaluator(first.specs).evaluate(
            first.metrics, first.metric_units, first.metric_validity)
        if not initial_evaluation.valid:
            raise ValueError('Initial observation has no valid required measurements')
        evaluation = SpecificationEvaluator(last.specs).evaluate(last.metrics, last.metric_units, last.metric_validity)
        expected = evaluation.reward if last.status == 'ok' and evaluation.valid else None
        if last.status in ('invalid_design', 'nonconverged') and self.terminated:
            expected = -1.0
        if (expected is None or isinstance(self.reward, bool) or not math.isfinite(self.reward)
                or not math.isclose(self.reward, expected, rel_tol=1e-10, abs_tol=1e-12)):
            raise ValueError('Reward/status/measurement contract mismatch')
        if not self.candidate_id or not self.record_path:
            raise ValueError('Candidate provenance is required')

    @classmethod
    def from_step(cls, observation, proposal, step):
        next_observation, reward, terminated, truncated, info = step
        if info.get('replay_eligible') is not True or next_observation is None or reward is None:
            raise ValueError('Step is not eligible for replay')
        path = Path(info['record_path'])
        record = json.loads(path.read_text())
        applied = {(p['device'], p['parameter']): p['value'] for p in record['applied_parameters']}
        transition = cls(deepcopy(observation), dict(proposal), reward, deepcopy(next_observation),
                         terminated, truncated, info['bootstrap'], applied, info['candidate_id'], str(path))
        transition.validate()
        from dataclasses import asdict
        expected = {
            'state': 'completed', 'kind': 'step', 'replay_eligible': True,
            'evaluation_purpose': 'nominal', 'origin': observation.origin,
            'condition': None if observation.condition is None else asdict(observation.condition),
            'candidate_id': transition.candidate_id, 'proposal': transition.proposal,
            'reward': reward, 'terminated': terminated, 'truncated': truncated,
            'bootstrap': info['bootstrap'], 'job_id': next_observation.job_id,
            'status': next_observation.status, 'metrics': next_observation.metrics,
            'metric_validity': next_observation.metric_validity,
            'applied_parameters': parameter_rows(applied),
        }
        if any(record.get(key) != value for key, value in expected.items()):
            raise ValueError('Candidate journal differs from the replay transition')
        return transition


class ReplayBuffer:
    def __init__(self, capacity=10000, *, origin, seed=0):
        if type(capacity) is not int or capacity < 1 or origin not in ('real', 'synthetic'):
            raise ValueError('Replay needs positive capacity and explicit origin')
        self.capacity, self.origin = capacity, origin
        self._items, self._position, self.insertions = [], 0, 0
        self._rng = random.Random(seed)

    def __len__(self):
        return len(self._items)

    def add(self, transition):
        transition.validate()
        if transition.observation.origin != self.origin:
            raise ValueError('Cannot mix synthetic and real replay')
        transition = deepcopy(transition)
        if len(self._items) < self.capacity:
            self._items.append(transition)
        else:
            self._items[self._position] = transition
        self._position = (self._position + 1) % self.capacity
        self.insertions += 1

    def sample(self, batch_size):
        if type(batch_size) is not int or not 1 <= batch_size <= len(self):
            raise ValueError('Insufficient replay for sampling without replacement')
        return deepcopy(self._rng.sample(self._items, batch_size))

    def state_dict(self):
        return deepcopy(dict(capacity=self.capacity, origin=self.origin, items=self._items,
                             position=self._position, insertions=self.insertions, rng=self._rng.getstate()))

    @classmethod
    def from_state_dict(cls, state):
        result = cls(state['capacity'], origin=state['origin'])
        if (len(state['items']) > result.capacity or not 0 <= state['position'] < result.capacity
                or state['insertions'] < len(state['items'])
                or state['position'] != state['insertions'] % result.capacity):
            raise ValueError('Invalid replay checkpoint')
        for item in state['items']:
            item.validate()
            if item.observation.origin != result.origin:
                raise ValueError('Replay origin mismatch')
        result._items = deepcopy(state['items'])
        result._position, result.insertions = state['position'], state['insertions']
        result._rng.setstate(state['rng'])
        return result
