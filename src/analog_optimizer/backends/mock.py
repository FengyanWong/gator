"""Explicit synthetic fixture provider; never performs networking or simulation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .backend import (
    BackendNotConnected, NetlistArtifact, SimulationRequest, SimulationResult,
    SimulationStatus, UnsupportedCapability, VirtuosoBackend,
)


class MockBackend(VirtuosoBackend):
    """Exports an immutable netlist and returns explicitly supplied test measurements.

    No device physics or parameter writeback is claimed. Nonempty candidate
    parameters are rejected, and synthetic results cannot certify a real design.
    """

    def __init__(self, netlist_text: str, *, metrics: dict[str, float | None] | None = None,
                 metric_units: dict[str, str] | None = None,
                 status: SimulationStatus = SimulationStatus.OK):
        self.netlist_text = netlist_text
        self.metrics = dict(metrics or {})
        self.metric_units = dict(metric_units or {})
        self.status = status
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def _require_connection(self) -> None:
        if not self.connected:
            raise BackendNotConnected("Call connect() before using the synthetic backend")

    @staticmethod
    def _job(work_root: Path) -> tuple[str, Path]:
        job_id = uuid4().hex
        directory = Path(work_root) / job_id
        directory.mkdir(parents=True, exist_ok=False)
        return job_id, directory

    def generate_netlist(self, work_root: Path, *, condition=None) -> NetlistArtifact:
        self._require_connection()
        self.validate_condition(condition)
        job_id, directory = self._job(work_root)
        path = directory / "input.scs"
        contents = self.netlist_text.encode()
        path.write_bytes(contents)
        artifact = NetlistArtifact(path, job_id, hashlib.sha256(contents).hexdigest(), "synthetic")
        (directory / "manifest.json").write_text(json.dumps({"job_id": job_id, "origin": "synthetic",
                                                           "sha256": artifact.sha256}, indent=2))
        return artifact

    def run_simulation(self, request: SimulationRequest) -> SimulationResult:
        self._require_connection()
        self.validate_condition(request.condition or request.netlist.condition)
        if request.parameters:
            raise UnsupportedCapability("MockBackend exports immutable fixtures; no parameter execution")
        if request.netlist.origin != "synthetic":
            raise ValueError("MockBackend accepts only explicitly synthetic artifacts")
        if hashlib.sha256(request.netlist.path.read_bytes()).hexdigest() != request.netlist.sha256:
            raise ValueError("Netlist artifact changed after export")
        started = perf_counter()
        job_id, directory = self._job(request.work_root)
        metrics = {name: self.metrics.get(name) for name in dict.fromkeys([*self.metrics, *request.required_metrics])}
        validity = {name: self.status == SimulationStatus.OK and value is not None and math.isfinite(value)
                    for name, value in metrics.items()}
        metrics = {name: value if validity[name] else None for name, value in metrics.items()}
        status = self.status
        required = request.required_metrics or tuple(metrics)
        if status == SimulationStatus.OK and (not metrics or not all(validity[name] for name in required)):
            status = SimulationStatus.MEASUREMENT_ERROR
        retryable = status in (SimulationStatus.TIMEOUT, SimulationStatus.TRANSPORT_ERROR, SimulationStatus.LICENSE_ERROR)
        result = SimulationResult(job_id, "mock", "synthetic", status, f"synthetic_{status.value}",
                                  retryable, False, metrics,
                                  {name: self.metric_units.get(name, "unspecified") for name in metrics},
                                  validity, {}, directory, perf_counter() - started)
        (directory / "result.json").write_text(json.dumps({
            "job_id": job_id, "origin": result.origin, "backend_kind": result.backend_kind,
            "status": status.value, "reason_code": result.reason_code, "retryable": retryable,
            "candidate_evaluated": False, "metrics": metrics, "metric_validity": validity,
            "metric_units": result.metric_units, "applied_parameters": {},
            "netlist_sha256": request.netlist.sha256, "elapsed_seconds": result.elapsed_seconds,
        }, indent=2, allow_nan=False))
        return result
