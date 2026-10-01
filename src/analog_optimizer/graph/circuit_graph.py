"""Cadence- and Torch-independent graph schema. Names are writeback IDs only."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass(frozen=True)
class SourceSpan:
    file: str
    line: int
    column: int = 1

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    source: SourceSpan
    severity: str = "error"


@dataclass(frozen=True)
class ParameterValue:
    raw: str
    value: float | None
    source: SourceSpan
    reason: str | None = None
    source_name: str | None = None

    @property
    def valid(self) -> bool:
        return self.value is not None and math.isfinite(self.value)


@dataclass(frozen=True)
class Device:
    id: str
    kind: str
    model_ref: str
    terminals: tuple[str, ...]
    source: SourceSpan


@dataclass(frozen=True)
class Net:
    id: str
    roles: tuple[str, ...] = ("normal",)
    role_source: str = "default"


@dataclass(frozen=True)
class Connection:
    device_id: str
    net_id: str
    terminal: str
    ordinal: int
    role: str


@dataclass(frozen=True)
class ParameterBinding:
    device_id: str
    parameter: str
    ratio: float = 1.0
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True)
class ParameterGroup:
    id: str
    parameter_kind: str
    unit: str
    value: float
    lower: float
    upper: float
    members: tuple[ParameterBinding, ...]
    domain: str = "continuous"
    scale: str = "linear"
    mutable: bool = True
    step: float | None = None

    def validate(self) -> None:
        if not self.members or not all(math.isfinite(v) for v in (self.value, self.lower, self.upper)):
            raise ValueError(f"{self.id}: empty members or non-finite domain")
        if not self.lower <= self.value <= self.upper or self.lower >= self.upper:
            raise ValueError(f"{self.id}: invalid bounds/current value")
        if self.domain not in ("continuous", "integer") or self.scale not in ("linear", "log"):
            raise ValueError(f"{self.id}: unsupported domain/scale")
        if self.scale == "log" and self.lower <= 0:
            raise ValueError(f"{self.id}: log domain must be positive")
        if self.step is not None and (not math.isfinite(self.step) or self.step <= 0):
            raise ValueError(f"{self.id}: step must be finite and positive")
        if self.domain == "integer":
            if any(v != int(v) for v in (self.value, self.lower, self.upper, self.step or 1)):
                raise ValueError(f"{self.id}: integer domain requires integral values")
        if self.step and not math.isclose((self.value - self.lower) / self.step,
                                          round((self.value - self.lower) / self.step), abs_tol=1e-9):
            raise ValueError(f"{self.id}: current value is off the legal grid")
        for member in self.members:
            if not math.isfinite(member.ratio) or member.ratio <= 0:
                raise ValueError(f"{self.id}: binding ratio must be positive")
            for bound in (member.lower, member.upper):
                if bound is not None and not math.isfinite(bound):
                    raise ValueError(f"{self.id}: non-finite member bound")
            if member.lower is not None and self.lower * member.ratio < member.lower:
                raise ValueError(f"{self.id}: group domain violates member lower bound")
            if member.upper is not None and self.upper * member.ratio > member.upper:
                raise ValueError(f"{self.id}: group domain violates member upper bound")

    def project(self, value: float) -> float:
        """Clamp/quantize physical values; this is not a SAC action adapter."""
        self.validate()
        if not math.isfinite(value):
            raise ValueError("Cannot project a non-finite value")
        if not self.mutable:
            return self.value
        value = min(self.upper, max(self.lower, value))
        step = self.step or (1.0 if self.domain == "integer" else None)
        if step:
            index = min(math.floor((self.upper - self.lower) / step + 1e-12),
                        max(0, math.floor((value - self.lower) / step + 0.5)))
            # lower + index*step can land one float step above `upper` for bounds typed in decimals (1.84 .. 42.38 um in
            # 0.02 um steps: 4.2380000000000004e-05), and the group then refused its own top value. In range: unchanged.
            value = min(self.upper, max(self.lower, self.lower + index * step))
        return value


@dataclass
class CircuitGraph:
    circuit_id: str
    devices: list[Device]
    nets: list[Net]
    connections: list[Connection]
    # Dynamic sizes are separate from the static device/net/terminal structure.
    parameters: dict[str, dict[str, ParameterValue]]
    parameter_groups: list[ParameterGroup] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    schema_version: str = "1.0"

    @property
    def complete(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    def validate(self, *, require_complete: bool = True) -> None:
        if require_complete and not self.complete:
            raise ValueError("Incomplete graph: " + "; ".join(d.message for d in self.diagnostics
                                                             if d.severity == "error"))
        devices = {d.id: d for d in self.devices}
        nets = {n.id for n in self.nets}
        if len(devices) != len(self.devices) or len(nets) != len(self.nets):
            raise ValueError("Duplicate device/net ID")
        if set(self.parameters) != set(devices):
            raise ValueError("Parameter table must cover exactly the device IDs")
        ports: set[tuple[str, int]] = set()
        for c in self.connections:
            if c.device_id not in devices or c.net_id not in nets:
                raise ValueError("Dangling connection")
            device = devices[c.device_id]
            if not 0 <= c.ordinal < len(device.terminals) or device.terminals[c.ordinal] != c.terminal:
                raise ValueError("Invalid terminal ordinal/name")
            if (c.device_id, c.ordinal) in ports:
                raise ValueError("Duplicate terminal connection")
            ports.add((c.device_id, c.ordinal))
        if len(ports) != sum(len(d.terminals) for d in self.devices):
            raise ValueError("Missing terminal connection")
        group_ids: set[str] = set()
        bound: set[tuple[str, str]] = set()
        for group in self.parameter_groups:
            group.validate()
            if group.id in group_ids:
                raise ValueError(f"Duplicate parameter group {group.id}")
            group_ids.add(group.id)
            for member in group.members:
                key = (member.device_id, member.parameter)
                if key in bound:
                    raise ValueError(f"Conflicting parameter bindings: {key}")
                bound.add(key)
                if member.device_id not in devices or devices[member.device_id].kind == "unknown":
                    raise ValueError(f"Unknown optimizable device: {member.device_id}")
                parameter = self.parameters[member.device_id].get(member.parameter)
                if parameter is None or not parameter.valid:
                    raise ValueError(f"Unresolved optimizable parameter: {key}")
                if not math.isclose(parameter.value, group.value * member.ratio, rel_tol=1e-9, abs_tol=1e-18):
                    raise ValueError(f"Binding/current value mismatch: {key}")

    def assignments(self, group_values: dict[str, float]) -> dict[tuple[str, str], float]:
        """Return explicit flattened instance/parameter writeback IDs, never line positions."""
        self.validate()
        groups = {g.id: g for g in self.parameter_groups}
        if group_values.keys() - groups.keys():
            raise ValueError("Unknown parameter group")
        return {(m.device_id, self.parameters[m.device_id][m.parameter].source_name or m.parameter):
                groups[name].project(value) * m.ratio
                for name, value in group_values.items() for m in groups[name].members}
