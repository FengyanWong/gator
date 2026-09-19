from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class DeviceMapping:
    kind: str
    terminals: tuple[str, ...]
    roles: tuple[str, ...]
    # Aliases explicitly identify numeric physical fields, e.g. width -> w.
    parameters: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.terminals or len(self.terminals) != len(self.roles):
            raise ValueError("Device mapping must define a role for each terminal")
        if len(set(self.terminals)) != len(self.terminals):
            raise ValueError("Terminal names must be unique within a device mapping")
        if len(set(self.parameters.values())) != len(self.parameters):
            raise ValueError("Parameter aliases must map to distinct canonical fields")


@dataclass(frozen=True)
class ParserConfig:
    models: dict[str, DeviceMapping]
    mapping_version: str = "1"
    net_roles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    global_nets: tuple[str, ...] = ("0",)
    parameter_groups: tuple[dict, ...] = ()
    include_roots: tuple[Path, ...] = ()
    max_include_depth: int = 16
    max_hierarchy_depth: int = 32

    @classmethod
    def from_file(cls, path: str | Path) -> ParserConfig:
        path = Path(path).resolve()
        raw = json.loads(path.read_text())
        if "models_file" in raw:
            if "models" in raw:
                raise ValueError("Specify models or models_file, not both")
            raw["models"] = json.loads((path.parent / raw.pop("models_file")).read_text())
        raw["models"] = {name: DeviceMapping(kind=value["kind"],
                                           terminals=tuple(value["terminals"]),
                                           roles=tuple(value["roles"]),
                                           parameters=value.get("parameters", {}))
                         for name, value in raw["models"].items()}
        raw["net_roles"] = {name: tuple(roles) for name, roles in raw.get("net_roles", {}).items()}
        raw["include_roots"] = tuple((path.parent / root).resolve() for root in raw.get("include_roots", []))
        for key in ("global_nets", "parameter_groups"):
            if key in raw:
                raw[key] = tuple(raw[key])
        return cls(**raw)
