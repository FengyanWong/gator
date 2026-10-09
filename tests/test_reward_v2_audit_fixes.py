"""Regression tests for the audit findings of 2026-09-26 (record 7.97): explicit synthetic fixtures, no circuit."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from analog_optimizer.backends.backend import NetlistArtifact, UnsupportedCapability
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.envs import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models.inputs import SpecSchema
from research_support import SyntheticSizingFixture, environment

NOMINAL = SimulationCondition(PVTCorner('nominal', 'tt', 27.0, 1.0))


def prepared(opamp):
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], scale='linear')
    opamp.parameter_groups[1] = replace(opamp.parameter_groups[1], mutable=False)
    return opamp


class RelabelledFixture(SyntheticSizingFixture):
    """The synthetic fixture with a scripted origin and invocation count; nothing else changes."""
    origin, invocations = 'real', None

    def nominal_condition(self):
        return NOMINAL

    def validate_condition(self, condition):
        if condition not in (None, NOMINAL):
            raise UnsupportedCapability('fixture: nominal only')

    def generate_netlist(self, work_root, *, condition=None):
        artifact = super().generate_netlist(work_root)
        return NetlistArtifact(artifact.path, artifact.job_id, artifact.sha256, self.origin, condition)

    def run_simulation(self, request):
        result = super().run_simulation(request)
        return replace(result, origin=self.origin, condition=request.condition, simulator_invocations=self.invocations)


def test_a_synthetic_result_without_an_invocation_count_is_a_complete_call(opamp, tmp_path):
    """F1: the synthetic and MOCK backends never report simulator invocations; their call is never 'uncertain'."""
    backend = SyntheticSizingFixture(prepared(opamp))
    with environment(backend, tmp_path) as env:
        first, info = env.reset()
        assert not info['truncated'] and info['evaluation_valid'] and env.simulation_calls == 1
        assert env.uncertain_calls == 0 and env.confirmed_calls == 0            # no simulator was launched
        record = json.loads(Path(info['record_path']).read_text())
        assert record['jobs'][0]['uncertain_calls'] == 0 and record['jobs'][0]['confirmed_calls'] == 0
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 0})
        assert reward == 0 and not truncated and info['replay_eligible'] and env.simulation_calls == 2


@pytest.mark.parametrize('invocations, uncertain', [(None, 1), (1, 0), (0, 0)])
def test_a_real_result_reports_its_invocation_or_stays_uncertain(opamp, tmp_path, invocations, uncertain):
    backend = RelabelledFixture(prepared(opamp))
    backend.invocations = invocations
    specs = [MetricSpec('score', 'fixture', 'min', 1, lower=3)]
    with CircuitSizingEnv(backend, backend.graph, specs, tmp_path, expected_origin='real') as env:
        first, info = env.reset()
        assert info['truncated'] == (invocations is None) and env.uncertain_calls == uncertain
        assert env.confirmed_calls == (invocations or 0) and env.simulation_calls == (1 if invocations != 0 else 0)
        record = json.loads(Path(info['record_path']).read_text())
        assert record['jobs'][0]['uncertain_calls'] == uncertain
        if invocations is None:
            assert record['conditions_stop_reason'] == 'unavailable_or_uncertain_condition'


def test_the_registry_label_is_identity_and_the_layout_is_the_codes(opamp):
    """F2: the M6 modules name their registries; a name must not be refused as an input layout."""
    from analog_optimizer.evaluation.cross_category import load_categories
    schema = SpecSchema(version='physical-m6-registry-v1', metrics=(('a', 'V', 1.0),))
    assert schema.layout == 'spec-input-v2' and schema.width == 21 + 11
    assert load_categories(Path(__file__).resolve().parents[1])                  # constructs its own labelled registry
