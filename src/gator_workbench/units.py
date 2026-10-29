"""Explicit unit registry. Conversions are declared, never guessed from a name.

Each accepted unit string maps to (canonical unit, multiplicative factor), or to
an affine rule for the few units that need one. Unknown units are rejected so a
typo cannot silently change a bound by orders of magnitude.
"""
from __future__ import annotations

import math

_MILLI = 0.001
_MICRO = 1e-06
_NANO = 1e-09
_PICO = 1e-12
_FEMTO = 1e-15
_KILO = 1000.0
_MEGA = 1000000.0
_GIGA = 1000000000.0


# canonical unit -> {accepted spelling: factor to canonical}
_LINEAR = {
    'm': {'m': 1.0, 'mm': _MILLI, 'um': _MICRO, 'µm': _MICRO, 'nm': _NANO},
    'F': {'F': 1.0, 'mF': _MILLI, 'uF': _MICRO, 'µF': _MICRO, 'nF': _NANO, 'pF': _PICO, 'fF': _FEMTO, 'aF': 1e-18},
    'ohm': {'ohm': 1.0, 'Ohm': 1.0, 'Ω': 1.0, 'kohm': _KILO, 'kΩ': _KILO, 'Mohm': _MEGA, 'MΩ': _MEGA},
    'H': {'H': 1.0, 'mH': _MILLI, 'uH': _MICRO, 'µH': _MICRO, 'nH': _NANO, 'pH': _PICO},
    'V': {'V': 1.0, 'mV': _MILLI, 'uV': _MICRO, 'µV': _MICRO, 'nV': _NANO, 'kV': _KILO},
    'A': {'A': 1.0, 'mA': _MILLI, 'uA': _MICRO, 'µA': _MICRO, 'nA': _NANO, 'pA': _PICO},
    'W': {'W': 1.0, 'mW': _MILLI, 'uW': _MICRO, 'µW': _MICRO, 'nW': _NANO, 'pW': _PICO},
    # Energy, e.g. the Specs equation "power / frequency" = energy per cycle.
    'J': {'J': 1.0, 'mJ': _MILLI, 'uJ': _MICRO, 'µJ': _MICRO, 'nJ': _NANO, 'pJ': _PICO, 'fJ': _FEMTO, 'aJ': 1e-18},
    'Hz': {'Hz': 1.0, 'kHz': _KILO, 'MHz': _MEGA, 'GHz': _GIGA, 'THz': 1e12},
    's': {'s': 1.0, 'ms': _MILLI, 'us': _MICRO, 'µs': _MICRO, 'ns': _NANO, 'ps': _PICO, 'fs': _FEMTO},
    'deg': {'deg': 1.0, 'degree': 1.0, '°': 1.0},
    'rad': {'rad': 1.0},
    'dB': {'dB': 1.0},
    'dBc/Hz': {'dBc/Hz': 1.0},
    'V/sqrt(Hz)': {'V/sqrt(Hz)': 1.0, 'nV/sqrt(Hz)': _NANO, 'uV/sqrt(Hz)': _MICRO, 'µV/sqrt(Hz)': _MICRO},
    'A/sqrt(Hz)': {'A/sqrt(Hz)': 1.0, 'pA/sqrt(Hz)': _PICO, 'fA/sqrt(Hz)': _FEMTO},
    'V^2/Hz': {'V^2/Hz': 1.0},
    'Vrms': {'Vrms': 1.0, 'mVrms': _MILLI, 'uVrms': _MICRO, 'µVrms': _MICRO},
    'V/s': {'V/s': 1.0, 'V/us': _MEGA, 'V/µs': _MEGA, 'V/ns': _GIGA},
    'Hz/V': {'Hz/V': 1.0, 'MHz/V': _MEGA, 'GHz/V': _GIGA},
    # Line and load regulation of a regulator, as the verified LDO profile reports them. V/A is kept apart from ohm:
    # it is a regulation figure, and the result registry of record spells it this way.
    'V/V': {'V/V': 1.0, 'mV/V': _MILLI},
    'V/A': {'V/A': 1.0, 'mV/mA': 1.0, 'mV/A': _MILLI},
    '%': {'%': 1.0},
    'count': {'count': 1.0},
    '1': {'1': 1.0, 'ratio': 1.0, 'unitless': 1.0, '': 1.0},
    # Explicit synthetic-fixture unit used by the analytic toy backends; never physical.
    'fixture': {'fixture': 1.0},
}
# spelling -> (canonical, scale, offset): canonical = value * scale + offset
_AFFINE = {'degC': ('degC', 1.0, 0.0), '°C': ('degC', 1.0, 0.0), 'C': ('degC', 1.0, 0.0),
           'K': ('degC', 1.0, -273.15)}

LOOKUP: dict[str, tuple[str, float, float]] = {}
for _canonical, _spellings in _LINEAR.items():
    for _spelling, _factor in _spellings.items():
        if _spelling in LOOKUP and LOOKUP[_spelling][0] != _canonical:
            raise RuntimeError(f'Ambiguous unit spelling in registry: {_spelling!r}')
        LOOKUP[_spelling] = (_canonical, _factor, 0.0)
LOOKUP.update(_AFFINE)

# Canonical unit expected for each feature-schema parameter kind used by the optimizer
# (analog_optimizer.graph.pyg_converter.FeatureSchema.parameters). "m"/"nf" are counts.
PARAMETER_KIND_UNITS = {'w': 'm', 'l': 'm', 'm': 'count', 'nf': 'count', 'r': 'ohm',
                        'c': 'F', 'ind': 'H', 'dc': None}  # dc source: V or A, caller decides


class UnitError(ValueError):
    """The error for an unknown unit, or for converting a value that is not a finite number."""
    pass


def known(unit: str) -> bool:
    return unit in LOOKUP


def canonical_unit(unit: str) -> str:
    """Return a registered unit's canonical name or reject an unknown unit."""
    if unit not in LOOKUP:
        raise UnitError(f'Unknown unit {unit!r}; accepted units: {", ".join(sorted(LOOKUP))}')
    return LOOKUP[unit][0]


def to_canonical(value: float, unit: str) -> float:
    """Convert a finite value to its canonical unit. Non-finite input is an error, not NaN."""
    if unit not in LOOKUP:
        raise UnitError(f'Unknown unit {unit!r}')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UnitError('Only finite numbers can be converted')
    _, scale, offset = LOOKUP[unit]
    return float(value) * scale + offset


def compatible(first: str, second: str) -> bool:
    """Check whether both units are registered and have the same canonical unit."""
    return known(first) and known(second) and canonical_unit(first) == canonical_unit(second)


def is_affine(unit: str) -> bool:
    """Check whether converting the unit requires a nonzero affine offset."""
    return unit in _AFFINE and _AFFINE[unit][2] != 0.0


def scale_to_canonical(value: float, unit: str) -> float:
    """Convert a *difference* (tolerance, step, normalization scale): no affine offset."""
    if unit not in LOOKUP:
        raise UnitError(f'Unknown unit {unit!r}')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UnitError('Only finite numbers can be converted')
    return float(value) * LOOKUP[unit][1]


# ---------------------------------------------------------------------- the written form of a quantity (record 7.208)
# One way of writing a quantity in the whole workbench (user: "a unified way of unit representation in the parameters
# probes and specs windows considering the convenience usage of users", chose "Prefix per value"): the number, an SI
# prefix and the unit, as Virtuoso's forms write them - 1.2 um, 45 nm, 9.535 kohm, 400 uA, 100 MHz, -30 dB, 60 deg. In
# English letters only (user: "dont use greek characters for unit, use english letters instead"): u for micro, ohm, deg;
# the Greek spellings (µm, kΩ, °) are still read. The digits are the stored number's own, moved and never computed. The
# page writes and reads quantities with the same table (`written_forms`, sent with /api/schema); stored numbers and
# units never change.
PREFIXABLE = {'m', 'F', 'ohm', 'H', 'V', 'A', 'W', 'J', 'Hz', 's', 'Vrms', 'V/s', 'Hz/V', 'V/sqrt(Hz)', 'A/sqrt(Hz)',
    'V/A'}
SYMBOLS = {'Ohm': 'ohm', 'Ω': 'ohm', 'degree': 'deg', '°': 'deg', 'C': 'degC', '°C': 'degC', '1': '', 'ratio': '',
    'unitless': '',
           '': '', 'count': '', 'fixture': ''}
QUANTITIES = {'m': 'a length', 'F': 'a capacitance', 'ohm': 'a resistance', 'H': 'an inductance', 'V': 'a voltage',
              'A': 'a current', 'W': 'a power', 'J': 'an energy', 'Hz': 'a frequency', 's': 'a time', 'deg': 'an angle',
              'rad': 'an angle', 'dB': 'a level in dB', 'dBc/Hz': 'a phase noise',
              'V/sqrt(Hz)': 'a voltage noise density',
              'A/sqrt(Hz)': 'a current noise density', 'V^2/Hz': 'a noise power density', 'Vrms': 'an rms voltage',
              'V/s': 'a slew rate', 'Hz/V': 'a tuning gain', 'V/V': 'a voltage ratio', 'V/A': 'a regulation in V/A',
              '%': 'a percentage', 'count': 'a count', '1': 'a plain number', 'degC': 'a temperature',
              'fixture': 'a fixture value'}
_PREFIXES = {-18: 'a', -15: 'f', -12: 'p', -9: 'n', -6: 'u', -3: 'm', 0: '', 3: 'k', 6: 'M', 9: 'G', 12: 'T'}


def written_forms() -> dict:
    """The table the page writes and reads quantities with: every accepted spelling -> [canonical, factor, offset], the
    canonical units that take an SI prefix, how a unit is written (Ω as ohm), what quantity it is, and the unit of each
    parameter kind."""
    return dict(spellings={spelling: list(rule) for spelling, rule in sorted(LOOKUP.items())},
                prefixable=sorted(PREFIXABLE),
                symbols=SYMBOLS, quantities=QUANTITIES,
                # the unit a parameter of these names is sized in (w and l lengths, m and nf counts...): the editors
                # have no Unit column for Parameters since record 7.208, so this decides what a value typed in such a
                # row must be
                kinds={name: unit for name, unit in PARAMETER_KIND_UNITS.items() if unit})


def symbol(unit: str) -> str:
    """How a unit is written, in English letters: Ω as ohm, ° as deg; a plain number or a count without one."""
    return SYMBOLS.get(unit, unit)


def _join(number: str, written: str) -> str:
    return f'{number} {written}' if written else number


def _shortest(value: float) -> str:
    text = repr(float(value))
    return text[:-2] if text.endswith('.0') else text


def text(value, unit: str | None) -> str:
    """A stored number of a row in `unit`, written the one way: 4.5e-7 in m as 450 nm, 0.6 in um as 600 nm, 0.0004 in A as
    400 uA, 1e8 in Hz as 100 MHz, -30 in dB as -30 dB. Not a number: as it is."""
    from decimal import Decimal
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return '' if value is None else str(value)
    unit = unit or ''
    rule = LOOKUP.get(unit)
    if rule is None or rule[0] not in PREFIXABLE or rule[2] != 0.0:
        return _join(_shortest(value), symbol(unit) if rule is None or rule[1] == 1.0 else unit)
    canonical, factor, _offset = rule
    shift = round(math.log10(factor))
    if abs(10.0 ** shift - factor) > _PICO * factor:
        return _join(_shortest(value), unit)
    if value == 0:                                             # in the row's own prefix: 0 um
        return _join('0', f'{_PREFIXES.get(shift, "")}{symbol(canonical)}')
    sign, digits, exponent = Decimal(_shortest(abs(value))).normalize().as_tuple()
    digits = ''.join(map(str, digits))
    exponent += shift
    lead = exponent + len(digits) - 1
    # beyond the prefixes: the exponent form, in the canonical unit
    if not -18 <= lead < 15:
        number = f'{digits[0]}{"." + digits[1:] if len(digits) > 1 else ""}e{lead}'
        return _join(f'{"-" if value < 0 else ""}{number}', symbol(canonical))
    prefix = lead // 3 * 3
    moved = exponent - prefix
    if moved >= 0:
        number = digits + '0' * moved
    else:
        point = len(digits) + moved
        number = f'{digits[:point]}.{digits[point:]}' if point > 0 else f'0.{"0" * -point}{digits}'
    return _join(f'{"-" if value < 0 else ""}{number}', f'{_PREFIXES[prefix]}{symbol(canonical)}')


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_LOOKUP = LOOKUP
