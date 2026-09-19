import json

import pytest

from analog_optimizer.backends.backend import (
    BackendNotConnected, SimulationRequest, SimulationStatus, UnsupportedCapability, VirtuosoBackend,
)
from analog_optimizer.backends.mock import MockBackend


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        VirtuosoBackend()


def test_synthetic_export_job_isolation_and_lifecycle(tmp_path, parser):
    backend = MockBackend("R (a 0) resistor r=1k", metrics={"gain": 10}, metric_units={"gain": "dB"})
    with pytest.raises(BackendNotConnected):
        backend.generate_netlist(tmp_path)
    with backend:
        a, b = backend.generate_netlist(tmp_path), backend.generate_netlist(tmp_path)
        assert a.job_id != b.job_id and a.path != b.path
        assert a.origin == "synthetic"
        assert parser.parse_file(a.path).devices[0].kind == "resistor"
        result = backend.run_simulation(SimulationRequest(a, tmp_path, ("gain",)))
        assert result.status == SimulationStatus.OK
        assert result.origin == "synthetic" and not result.candidate_evaluated
        assert result.metric_validity == {"gain": True}
        saved = json.loads((result.artifact_directory / "result.json").read_text())
        assert saved["origin"] == "synthetic"
    assert not backend.connected


@pytest.mark.parametrize("status", list(SimulationStatus))
def test_injected_status_never_becomes_real_success(tmp_path, status):
    with MockBackend("", metrics={"gain": 10}, status=status) as backend:
        artifact = backend.generate_netlist(tmp_path)
        result = backend.run_simulation(SimulationRequest(artifact, tmp_path, ("gain",)))
    assert result.status == status and result.origin == "synthetic"
    assert result.metric_validity["gain"] == (status == SimulationStatus.OK)
    if status != SimulationStatus.OK:
        assert result.metrics["gain"] is None


def test_missing_metric_nan_and_unsupported_writeback(tmp_path):
    with MockBackend("", metrics={"gain": float("nan")}) as backend:
        artifact = backend.generate_netlist(tmp_path)
        result = backend.run_simulation(SimulationRequest(artifact, tmp_path, ("gain", "power")))
        assert result.status == SimulationStatus.MEASUREMENT_ERROR
        assert result.metrics == {"gain": None, "power": None}
        assert not any(result.metric_validity.values())
        with pytest.raises(UnsupportedCapability):
            backend.set_parameters({("Q", "w"): 1e-6})
        with pytest.raises(UnsupportedCapability):
            backend.run_simulation(SimulationRequest(artifact, tmp_path, parameters={("Q", "w"): 1e-6}))
        artifact.path.write_text("changed")
        with pytest.raises(ValueError, match="changed"):
            backend.run_simulation(SimulationRequest(artifact, tmp_path))


@pytest.mark.parametrize("metrics", [{}, {"gain": float("nan")}])
def test_empty_or_invalid_measurements_cannot_claim_ok(tmp_path, metrics):
    with MockBackend("", metrics=metrics) as backend:
        artifact = backend.generate_netlist(tmp_path)
        assert backend.run_simulation(SimulationRequest(artifact, tmp_path)).status == SimulationStatus.MEASUREMENT_ERROR
