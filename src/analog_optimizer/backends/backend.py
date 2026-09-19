from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import math
from .conditions import SimulationCondition


class UnsupportedCapability(RuntimeError):
    """The selected backend does not implement the requested operation."""


class BackendNotConnected(RuntimeError):
    pass


class SimulationStatus(str, Enum):
    OK = "ok"
    INVALID_DESIGN = "invalid_design"
    NONCONVERGED = "nonconverged"
    MEASUREMENT_ERROR = "measurement_error"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    LICENSE_ERROR = "license_error"
    BACKEND_ERROR = "backend_error"


@dataclass(frozen=True)
class NetlistArtifact:
    path: Path
    job_id: str
    sha256: str
    origin: str
    condition: SimulationCondition | None = None


@dataclass(frozen=True)
class SimulationRequest:
    netlist: NetlistArtifact
    work_root: Path
    required_metrics: tuple[str, ...] = ()
    timeout_seconds: float = 60.0
    parameters: dict[tuple[str, str], float] = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)
    condition: SimulationCondition | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if any(not math.isfinite(v) for v in self.parameters.values()):
            raise ValueError("Parameters must be finite")
        if self.condition is not None and not isinstance(self.condition, SimulationCondition):
            raise ValueError('A typed simulation condition is required')
        if self.condition is not None and self.condition != self.netlist.condition:
            raise ValueError('Requested condition differs from the prepared netlist')


@dataclass(frozen=True)
class SimulationResult:
    job_id: str
    backend_kind: str
    origin: str
    status: SimulationStatus
    reason_code: str
    retryable: bool
    candidate_evaluated: bool
    metrics: dict[str, float | None]
    metric_units: dict[str, str]
    metric_validity: dict[str, bool]
    applied_parameters: dict[tuple[str, str], float]
    artifact_directory: Path
    elapsed_seconds: float
    condition: SimulationCondition | None = None
    # None for deterministic runs; explicit zero-based index for future MC samples.
    sample_index: int | None = None


@dataclass(frozen=True)
class MonteCarloResult:
    """Reserved batch contract; no current backend claims to implement MC.

    samples retains failed/unavailable samples too. Do not drop them before
    estimating yield. Invocation count and sample count are different budgets.
    """
    condition: SimulationCondition
    samples: tuple[SimulationResult, ...]
    simulator_invocations: int

    def __post_init__(self):
        mc = self.condition.monte_carlo
        if mc is None or self.condition.purpose != 'mc_validation':
            raise ValueError('Monte Carlo batch requires mc_validation context')
        if len(self.samples) != mc.samples:
            raise ValueError('Keep a result, including failures, for every requested MC sample')
        indices = [s.sample_index for s in self.samples]
        if any(type(i) is not int for i in indices) or set(indices) != set(range(mc.samples)):
            raise ValueError('MC sample indices must cover the batch exactly once')
        if any(s.condition != self.condition for s in self.samples):
            raise ValueError('Mixed Monte Carlo conditions')
        # Random device perturbations are statistical outputs. The nominal
        # executed sizing and result provenance must remain the same per batch.
        first = self.samples[0]
        if any((s.origin, s.backend_kind, s.applied_parameters) !=
               (first.origin, first.backend_kind, first.applied_parameters) for s in self.samples):
            raise ValueError('MC samples must share nominal sizing and provenance')
        if type(self.simulator_invocations) is not int or self.simulator_invocations < 1:
            raise ValueError('A statistical batch must record its simulator invocation count')


class VirtuosoBackend(ABC):
    """Our abstraction, NOT the upstream virtuoso-bridge-lite API.

    The bridge adapter implements these operations for its explicit circuit profile.
    Optional operations fail loudly rather than returning fabricated success.
    """

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def generate_netlist(self, work_root: Path, *, condition: SimulationCondition | None = None) -> NetlistArtifact: ...

    def nominal_condition(self) -> SimulationCondition | None:
        """None is reserved for legacy synthetic fixtures, not an implicit PVT default."""
        return None

    def validate_condition(self, condition: SimulationCondition | None) -> None:
        """Preflight BEFORE writing parameters or exporting; fail explicitly if unsupported."""
        if condition is not None:
            raise UnsupportedCapability('Explicit simulation conditions are not implemented by this backend')

    def set_parameters(self, parameters: dict[tuple[str, str], float]) -> None:
        raise UnsupportedCapability("Parameter writeback is not implemented by this backend")

    def read_parameters(self) -> dict[tuple[str, str], float]:
        raise UnsupportedCapability("Parameter readback is not implemented by this backend")

    def restore(self) -> None:
        raise UnsupportedCapability("Restoration is not implemented by this backend")

    def get_circuit_graph(self, artifact: NetlistArtifact):
        """Read the verified export with this backend's permitted action groups."""
        raise UnsupportedCapability("Export graph readback is not implemented by this backend")

    def run_simulation(self, request: SimulationRequest) -> SimulationResult:
        raise UnsupportedCapability("Simulation is not implemented by this backend")

    def run_monte_carlo(self, request: SimulationRequest) -> MonteCarloResult:
        """Future statistical entry point; never substitute repeated nominal runs."""
        raise UnsupportedCapability('Monte Carlo execution/sample parsing is not implemented by this backend')

    def get_operating_points(self) -> dict:
        raise UnsupportedCapability("Operating points are not implemented by this backend")

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> VirtuosoBackend:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
