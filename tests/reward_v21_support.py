"""Scripted mechanism fixtures only: no circuit solver, bridge or electrical evidence."""
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path

from analog_optimizer.backends.backend import NetlistArtifact, SimulationStatus
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.envs.sizing import CircuitSizingEnv, Observation
from analog_optimizer.measurements.specs import MetricSpec, RewardSettings, SpecificationEvaluator
from analog_optimizer.parameters.actions import ActionMapper
from analog_optimizer.training.replay import Transition
from tests.test_sizing_env import SyntheticSizingFixture

NOMINAL = SimulationCondition(PVTCorner('nominal', 'tt', 27., 1.))
CORNERS = tuple(SimulationCondition(PVTCorner(f'corner_{i}', 'ss', 125., .9), purpose='pvt_training')
                for i in range(2))
PLAN = (NOMINAL, *CORNERS)


class ScriptedRealBackend(SyntheticSizingFixture):
    """A fake backend labelled real to exercise corner contracts; values are scripted."""

    def __init__(self, graph, *, nominal_pass=False):
        super().__init__(graph)
        self.nominal_pass = nominal_pass
        self.outcomes = {}
        self.launched = []
        self.stop_after_nominal = None
        self.unknown = False

    def nominal_condition(self):
        return NOMINAL

    def validate_condition(self, condition):
        assert condition in PLAN

    def generate_netlist(self, work_root, *, condition=None):
        artifact = super().generate_netlist(work_root)
        return replace(artifact, origin='real', condition=condition or NOMINAL)

    def derive_condition_artifact(self, artifact, work_root, *, condition):
        return self.generate_netlist(work_root, condition=condition)

    def run_simulation(self, request):
        result = super().run_simulation(request)
        self.launched.append(request.condition)
        status, evaluated, values, validity, units = self.outcomes.get(request.condition, (
            SimulationStatus.OK, True, {'score': 2. if self.nominal_pass else .5, 'other': 2.},
            {'score': True, 'other': True}, {'score': 'fixture', 'other': 'fixture'}))
        if self.stop_after_nominal and request.condition == NOMINAL:
            self.stop_after_nominal.touch()
        return replace(result, origin='real', condition=request.condition, status=status,
                       candidate_evaluated=evaluated, metrics=values, metric_validity=validity,
                       metric_units=units, simulator_invocations=None if self.unknown else 1)


def specs(flag=True):
    return (MetricSpec('score', 'fixture', 'min', 1., lower=1., missing_is_failure=flag),
            MetricSpec('other', 'fixture', 'min', 1., lower=1.))


def environment(graph, output, *, policy='after_nominal', flag=True, nominal_pass=False, **kwargs):
    backend = ScriptedRealBackend(graph, nominal_pass=nominal_pass)
    return CircuitSizingEnv(backend, backend.graph, specs(flag), output, max_steps=kwargs.pop('max_steps', 3),
                            stop_on_success=kwargs.pop('stop_on_success', False), condition_policy=policy,
                            corners=() if policy == 'off' else CORNERS, **kwargs)


def reset(env):
    env.authorize_launches(1)
    return env.reset()


def step(env, value=0., *, stop_file=None):
    env.authorize_launches(len(env.planned_conditions), stop_file=stop_file)
    proposal = {key: value for key in env.mapper.group_ids}
    return proposal, env.step(proposal)


@dataclass
class ParallelFactory:
    graph: object
    output: Path
    condition_policy: str = 'after_nominal'

    def __call__(self, lane):
        return self.create_recorded(lane, None)

    def create_recorded(self, lane, recorder):
        return environment(self.graph, self.output / f'lane-{lane}', nominal_pass=bool(lane),
                           recorder=recorder, max_steps=2)


def algebraic_transitions(graph):
    """Fixed toy replay, built by arithmetic alone; not a simulator or collector run."""
    import random
    rng = random.Random(291)
    settings = RewardSettings(violation_shape='compressed', worst_spec_share=.5)
    goal = (MetricSpec('score', 'fixture', 'min', 1., lower=1.),)
    evaluator = SpecificationEvaluator(goal, settings)
    mapper = ActionMapper(graph)
    first = Observation(deepcopy(graph), goal, {'score': 0.}, {'score': True}, {'score': 'fixture'},
                        'ok', 'synthetic', 1, 'algebraic-initial', reward_settings=settings)
    transitions = []
    for i in range(64):
        action = mapper.legalize({key: rng.uniform(-1., 1.) for key in mapper.group_ids})
        updated = deepcopy(graph)
        for index, group in enumerate(updated.parameter_groups):
            if not group.mutable:
                continue
            for member in group.members:
                old = updated.parameters[member.device_id][member.parameter]
                value = action.assignments[(member.device_id, old.source_name or member.parameter)]
                updated.parameters[member.device_id][member.parameter] = replace(old, value=value, raw=str(value))
            updated.parameter_groups[index] = replace(group, value=action.group_values[group.id])
        score = 1. - sum((value - .75) ** 2 for value in action.proposal.values()) / len(action.proposal)
        last = replace(first, graph=updated, metrics={'score': score}, remaining_steps=0, job_id=f'algebraic-{i}')
        reward = evaluator.evaluate(last.metrics, last.metric_units, last.metric_validity).reward
        transition = Transition(first, action.proposal, reward, last, True, False, False, action.assignments,
                                f'algebraic-{i}', f'unit-fixture:{i}', reward_settings=settings)
        transition.validate()
        transitions.append(transition)
    return transitions
