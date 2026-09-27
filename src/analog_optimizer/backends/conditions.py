"""Simulation conditions are evaluation inputs, never sizing action dimensions.

Training uses explicit nominal and pvt_training identities. Post-validation
and Monte Carlo retain separate purposes and cannot enter training replay.
The MC types reserve sample identity; statistical execution is not implemented.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class PVTCorner:
    id: str
    model_section: str
    temperature_c: float
    supply_v: float

    def __post_init__(self):
        for name in (self.id, self.model_section):
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_]\w*', name):
                raise ValueError('Corner ID and model section must be identifiers')
        if not finite_number(self.temperature_c) or self.temperature_c <= -273.15:
            raise ValueError('Invalid temperature in degrees Celsius')
        if not finite_number(self.supply_v) or self.supply_v <= 0:
            raise ValueError('Supply voltage must be finite and positive')
        object.__setattr__(self, 'temperature_c', float(self.temperature_c))
        object.__setattr__(self, 'supply_v', float(self.supply_v))
        # Profile-specific model sections and electrical bounds are checked by
        # the backend, not guessed here from a name such as "nmos1v".


@dataclass(frozen=True)
class MonteCarloConfig:
    samples: int
    seed: int
    variation: str = 'all'
    model_section: str = 'mc'

    def __post_init__(self):
        if isinstance(self.samples, bool) or not isinstance(self.samples, int) or self.samples < 1:
            raise ValueError('Monte Carlo samples must be a positive integer')
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 1 <= self.seed <= 2147483647:
            raise ValueError('Monte Carlo seed must be an integer in [1, 2147483647]')
        if self.variation not in ('process', 'mismatch', 'all'):
            raise ValueError('Monte Carlo variation must be process, mismatch or all')
        if not re.fullmatch(r'[A-Za-z_]\w*', self.model_section):
            raise ValueError('Invalid statistical model section')
        # A seed alone does not prove that the PDK statistics were activated.
        # Future adapters must record model identity, sampling method and each
        # sample index, and validate the actual statistical model combination.


@dataclass(frozen=True)
class SimulationCondition:
    corner: PVTCorner
    purpose: str = 'nominal'
    monte_carlo: MonteCarloConfig | None = None

    def __post_init__(self):
        if not isinstance(self.corner, PVTCorner):
            raise ValueError('A typed PVT corner is required')
        if self.purpose not in ('nominal', 'pvt_training', 'pvt_validation', 'mc_validation'):
            raise ValueError('Unsupported evaluation purpose')
        if self.monte_carlo is not None and not isinstance(self.monte_carlo, MonteCarloConfig):
            raise ValueError('A typed Monte Carlo configuration is required')
        if (self.purpose == 'mc_validation') != (self.monte_carlo is not None):
            raise ValueError('Monte Carlo is reserved for explicit mc_validation')

    @property
    def nominal_only(self):
        return self.purpose == 'nominal' and self.monte_carlo is None

    @property
    def fingerprint(self):
        # Future caches must ALSO include sizing, PDK/model fingerprints,
        # testbench, analyses and measurement versions. This is only one part.
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls, raw):
        value = dict(raw)
        value['corner'] = PVTCorner(**value['corner'])
        if value.get('monte_carlo') is not None:
            value['monte_carlo'] = MonteCarloConfig(**value['monte_carlo'])
        return cls(**value)
