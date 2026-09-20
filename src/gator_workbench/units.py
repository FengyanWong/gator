"""Explicit unit registry. Conversions are declared, never guessed from a name.

Each accepted unit string maps to (canonical unit, multiplicative factor), or to
an affine rule for the few units that need one. Unknown units are rejected so a
typo cannot silently change a bound by orders of magnitude.
"""
from __future__ import annotations

import math

# canonical unit -> {accepted spelling: factor to canonical}
_LINEAR = {
    'm': {'m': 1.0, 'mm': 1e-3, 'um': 1e-6, 'µm': 1e-6, 'nm': 1e-9},
    'F': {'F': 1.0, 'mF': 1e-3, 'uF': 1e-6, 'µF': 1e-6, 'nF': 1e-9, 'pF': 1e-12, 'fF': 1e-15, 'aF': 1e-18},
    'ohm': {'ohm': 1.0, 'Ohm': 1.0, 'Ω': 1.0, 'kohm': 1e3, 'kΩ': 1e3, 'Mohm': 1e6, 'MΩ': 1e6},
    'H': {'H': 1.0, 'mH': 1e-3, 'uH': 1e-6, 'µH': 1e-6, 'nH': 1e-9, 'pH': 1e-12},
    'V': {'V': 1.0, 'mV': 1e-3, 'uV': 1e-6, 'µV': 1e-6, 'nV': 1e-9, 'kV': 1e3},
    'A': {'A': 1.0, 'mA': 1e-3, 'uA': 1e-6, 'µA': 1e-6, 'nA': 1e-9, 'pA': 1e-12},
    'W': {'W': 1.0, 'mW': 1e-3, 'uW': 1e-6, 'µW': 1e-6, 'nW': 1e-9, 'pW': 1e-12},
    'Hz': {'Hz': 1.0, 'kHz': 1e3, 'MHz': 1e6, 'GHz': 1e9, 'THz': 1e12},
    's': {'s': 1.0, 'ms': 1e-3, 'us': 1e-6, 'µs': 1e-6, 'ns': 1e-9, 'ps': 1e-12, 'fs': 1e-15},
    'deg': {'deg': 1.0, 'degree': 1.0, '°': 1.0},
    'rad': {'rad': 1.0},
    'dB': {'dB': 1.0},
    'dBc/Hz': {'dBc/Hz': 1.0},
    'V/sqrt(Hz)': {'V/sqrt(Hz)': 1.0, 'nV/sqrt(Hz)': 1e-9, 'uV/sqrt(Hz)': 1e-6, 'µV/sqrt(Hz)': 1e-6},
    'A/sqrt(Hz)': {'A/sqrt(Hz)': 1.0, 'pA/sqrt(Hz)': 1e-12, 'fA/sqrt(Hz)': 1e-15},
    'V^2/Hz': {'V^2/Hz': 1.0},
    'Vrms': {'Vrms': 1.0, 'mVrms': 1e-3, 'uVrms': 1e-6, 'µVrms': 1e-6},
    'V/s': {'V/s': 1.0, 'V/us': 1e6, 'V/µs': 1e6, 'V/ns': 1e9},
    'Hz/V': {'Hz/V': 1.0, 'MHz/V': 1e6, 'GHz/V': 1e9},
    '%': {'%': 1.0},
    'count': {'count': 1.0},
    '1': {'1': 1.0, 'ratio': 1.0, 'unitless': 1.0, '': 1.0},
    # Explicit synthetic-fixture unit used by the analytic toy backends; never physical.
    'fixture': {'fixture': 1.0},
}
# spelling -> (canonical, scale, offset): canonical = value * scale + offset
_AFFINE = {'degC': ('degC', 1.0, 0.0), '°C': ('degC', 1.0, 0.0), 'C': ('degC', 1.0, 0.0),
           'K': ('degC', 1.0, -273.15)}

_LOOKUP: dict[str, tuple[str, float, float]] = {}
for _canonical, _spellings in _LINEAR.items():
    for _spelling, _factor in _spellings.items():
        if _spelling in _LOOKUP and _LOOKUP[_spelling][0] != _canonical:
            raise RuntimeError(f'Ambiguous unit spelling in registry: {_spelling!r}')
        _LOOKUP[_spelling] = (_canonical, _factor, 0.0)
_LOOKUP.update(_AFFINE)

CANONICAL_UNITS = tuple(sorted(set(v[0] for v in _LOOKUP.values())))

# Canonical unit expected for each feature-schema parameter kind used by the optimizer
# (analog_optimizer.graph.pyg_converter.FeatureSchema.parameters). "m"/"nf" are counts.
PARAMETER_KIND_UNITS = {'w': 'm', 'l': 'm', 'm': 'count', 'nf': 'count', 'r': 'ohm',
                        'c': 'F', 'ind': 'H', 'dc': None}  # dc source: V or A, caller decides


class UnitError(ValueError):
    pass


def known(unit: str) -> bool:
    return unit in _LOOKUP


def canonical_unit(unit: str) -> str:
    if unit not in _LOOKUP:
        raise UnitError(f'Unknown unit {unit!r}; accepted units: {", ".join(sorted(_LOOKUP))}')
    return _LOOKUP[unit][0]


def to_canonical(value: float, unit: str) -> float:
    """Convert a finite value to its canonical unit. Non-finite input is an error, not NaN."""
    if unit not in _LOOKUP:
        raise UnitError(f'Unknown unit {unit!r}')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UnitError('Only finite numbers can be converted')
    _, scale, offset = _LOOKUP[unit]
    return float(value) * scale + offset


def compatible(first: str, second: str) -> bool:
    return known(first) and known(second) and canonical_unit(first) == canonical_unit(second)


def is_affine(unit: str) -> bool:
    return unit in _AFFINE and _AFFINE[unit][2] != 0.0


def scale_to_canonical(value: float, unit: str) -> float:
    """Convert a *difference* (tolerance, step, normalization scale): no affine offset."""
    if unit not in _LOOKUP:
        raise UnitError(f'Unknown unit {unit!r}')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UnitError('Only finite numbers can be converted')
    return float(value) * _LOOKUP[unit][1]
