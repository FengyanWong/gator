"""Condition identities and unsupported PVT/Monte Carlo calls checked with synthetic data, without simulations."""

from dataclasses import asdict, replace
from pathlib import Path

import pytest

from analog_optimizer.backends.conditions import PVTCorner, MonteCarloConfig, SimulationCondition
from analog_optimizer.backends.backend import (NetlistArtifact, SimulationRequest, SimulationResult,
                                               SimulationStatus, MonteCarloResult, UnsupportedCapability)
from analog_optimizer.backends.mock import MockBackend


def nominal():
    """Provide the nominal process, voltage and temperature condition for injected results."""
    return SimulationCondition(PVTCorner('nominal', 'tt', 27, 1))


def test_roundtrip_and_condition_identity_cover_statistics():
    first = nominal()
    second = SimulationCondition(PVTCorner('nominal', 'tt', 27.0, 1.0))
    assert first == second and first.fingerprint == second.fingerprint
    assert SimulationCondition.from_dict(asdict(first)) == first
    mc = SimulationCondition(first.corner, 'mc_validation', MonteCarloConfig(3, 123))
    variants = [mc, replace(mc, monte_carlo=replace(mc.monte_carlo, seed=124)),
                replace(mc, monte_carlo=replace(mc.monte_carlo, samples=4)),
                replace(mc, monte_carlo=replace(mc.monte_carlo, variation='mismatch'))]
    assert len({v.fingerprint for v in [first, *variants]}) == 5
    assert SimulationCondition.from_dict(asdict(mc)) == mc


@pytest.mark.parametrize('change', [{'temperature_c': float('nan')}, {'temperature_c': -274},
    {'supply_v': 0}, {'supply_v': True}, {'model_section': 'tt\ninclude'}, {'id': '../tt'}])
def test_bad_corners_rejected(change):
    with pytest.raises(ValueError):
        replace(nominal().corner, **change)


@pytest.mark.parametrize('change', [{'samples': 0}, {'samples': True}, {'seed': 0},
    {'seed': 1.1}, {'variation': 'nominal'}, {'model_section': 'mc;'}])
def test_bad_statistics_rejected(change):
    with pytest.raises(ValueError):
        replace(MonteCarloConfig(3, 123), **change)


def test_mc_cannot_be_tagged_as_training_or_deterministic_validation():
    for purpose in ('nominal', 'pvt_validation'):
        with pytest.raises(ValueError, match='mc_validation'):
            SimulationCondition(nominal().corner, purpose, MonteCarloConfig(3, 123))
    with pytest.raises(ValueError):
        SimulationCondition(nominal().corner, 'mc_validation')


def test_request_cannot_relabel_immutable_netlist(tmp_path):
    context = nominal()
    artifact = NetlistArtifact(tmp_path / 'input.scs', 'job', 'hash', 'synthetic', context)
    assert SimulationRequest(artifact, tmp_path, condition=context).condition == context
    with pytest.raises(ValueError, match='differs'):
        SimulationRequest(artifact, tmp_path, condition=replace(context, purpose='pvt_validation'))


def test_mock_never_fakes_pvt_or_mc_execution(tmp_path):
    with MockBackend('') as backend:
        with pytest.raises(UnsupportedCapability):
            backend.generate_netlist(tmp_path, condition=nominal())
        assert not list(tmp_path.iterdir())
        with pytest.raises(UnsupportedCapability, match='Monte Carlo'):
            backend.run_monte_carlo(None)


def sample(context, index):
    """Build an indexed nonconverged result with the supplied simulation condition."""
    return SimulationResult(str(index), 'test_fixture', 'synthetic', SimulationStatus.NONCONVERGED,
                            'injected', False, True, {}, {}, {}, {('M', 'w'): 1e-6},
                            Path('/synthetic'), 0, context, index)


def test_mc_batch_keeps_failures_and_sample_identity():
    condition = SimulationCondition(nominal().corner, 'mc_validation', MonteCarloConfig(2, 123))
    results = (sample(condition, 0), sample(condition, 1))
    batch = MonteCarloResult(condition, results, 1)
    assert batch.simulator_invocations == 1 and len(batch.samples) == 2
    for invalid in (results[:1], (results[0], results[0]),
                    (results[0], replace(results[1], condition=nominal())),
                    (results[0], replace(results[1], sample_index=True)),
                    (results[0], replace(results[1], origin='real')),
                    (results[0], replace(results[1], applied_parameters={('M', 'w'): 2e-6}))):
        with pytest.raises(ValueError):
            MonteCarloResult(condition, invalid, 1)
