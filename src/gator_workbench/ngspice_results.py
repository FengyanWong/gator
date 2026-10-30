"""ngspice measurement declarations, printed values and failure classification.

These pure readers share no simulator, task-store or run-engine state.
"""
from __future__ import annotations

import math
import re

from .ngspice_syntax import Measurement

MEASURE_ANALYSES = {'ac': 'ac', 'dc': 'dc', 'tran': 'tran', 'sp': 'other', 'noise': 'noise'}


def _guess_unit(analysis, words):
    """The unit a .meas result most likely has, from its own words: the measure type decides. FIND / MAX / MIN / AVG /
    RMS / PP / INTEG / DERIV of v(...) -> V, i(...) -> A, vdb -> dB, vp / ph -> rad (ngspice's default); WHEN, TRIG /
    TARG (a point on the x axis) -> s in tran, Hz in ac, V in dc; PARAM -> 1. The Probes row stays editable."""
    words = [w.lower() for w in words]
    kind = words[0] if words else ''
    expression = ' '.join(words[1:2])
    if kind == 'param':
        return '1'
    if kind in ('when', 'trig', 'targ'):
        return {'tran': 's', 'ac': 'Hz', 'dc': 'V'}.get(analysis, '1')
    if kind in ('find', 'max', 'min', 'avg', 'rms', 'pp', 'integ', 'deriv', 'max_at', 'min_at'):
        return expression_unit(expression, {'tran': 's', 'ac': 'Hz', 'dc': 'V'}.get(analysis, '1') if kind in ('max_at', 'min_at') else None)
    return '1'


NAME_UNITS = {'_deg': 'deg', '_rad': 'rad', '_hz': 'Hz', '_db': 'dB', '_w': 'W', '_v': 'V', '_a': 'A', '_s': 's', '_f': 'F',
              '_ohm': 'ohm', '_h': 'H', '_j': 'J', '_pct': '%'}


def unit_from_name(name):
    """A unit the result's own name states with its suffix (gain_db, ugf_hz, phase_margin_deg, power_w), or None."""
    lowered = (name or '').lower()
    for suffix, unit in NAME_UNITS.items():
        if lowered.endswith(suffix):
            return unit
    return None


def expression_unit(expression, default=None):
    """The unit of an ngspice expression such as v(out), vdb(out), i(vdd), -1.8*i(vdd): a guess from its outermost
    signal function; `default` (else '1') when there is none."""
    text = (expression or '').lower()
    if re.search(r'\bvdb\(|\bdb\(', text):
        return 'dB'
    if re.search(r'\bvp\(|\bph\(|\bphase\(', text):
        return 'rad'
    if re.search(r'\bi\(|\bi[a-z]*\(', text) and not re.search(r'\bv\(|\bv[a-z]*\(', text):
        return 'A'
    if re.search(r'\bv\(|\bv[a-z]*\(', text):
        return 'V'
    return default or '1'


def _measure(words, line, text):
    """A `.meas[ure] <analysis> <name> ...` (deck) or `meas <analysis> <name> ...` (control) statement, or None."""
    if len(words) < 3:
        return None
    analysis = words[1].lower()
    if analysis not in MEASURE_ANALYSES:
        return None
    name = words[2].lower()
    if not re.match(r'^[a-z_]\w*$', name):
        return None
    return Measurement(name, MEASURE_ANALYSES[analysis], unit_from_name(name) or _guess_unit(analysis, [w.lower() for w in words[3:]]), line, text)


RESULT_LINE = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|[-+]?(?:nan|inf))\b', re.IGNORECASE)


FAILURE_PATTERNS = (
    ('nonconverged', re.compile(r'(?i)(timestep too small|no convergence|singular matrix|gmin stepping failed|'
                                r'source stepping failed|convergence problem|failed to converge|too many iterations)')),
    ('measurement_error', re.compile(r'(?i)(\bmeas(?:ure(?:ment)?)?\b.*\bfailed|out of interval|no such vector|vector .* not found|'
                                     r'result is not a number)')),
    ('deck_error', re.compile(r'(?i)(error on line|fatal error|unknown subckt|could not find include|'
                              r'unable to find definition of model|model .* not found|no circuit loaded|'
                              r'syntax error|cannot compute substitute|error in netlist)')),
)


def read_results(stdout, wanted):
    """{name: value} for every `<name> = <number>` line of ngspice's batch output whose name is one of `wanted` (ngspice
    prints .meas names in lowercase). nan / inf stay out: a failed measurement is missing, never a number."""
    names = {name.lower(): name for name in wanted}
    found = {}
    for line in (stdout or '').splitlines():
        match = RESULT_LINE.match(line)
        if not match:
            continue
        key = match.group(1).lower()
        if key not in names or key in found:
            continue
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if math.isfinite(value):
            found[names[key]] = value
    return found


def classify_failure(stdout, stderr, returncode):
    """(status word, one line of evidence) when the output says the deck or the solution failed, else (None, '')."""
    text = '\n'.join(filter(None, (stdout, stderr)))
    for status, pattern in FAILURE_PATTERNS:
        match = pattern.search(text)
        if match:
            start = text.rfind('\n', 0, match.start()) + 1
            end = text.find('\n', match.end())
            return status, text[start:end if end >= 0 else len(text)].strip()[:300]
    if returncode not in (0, None):
        tail = [line.strip() for line in (stderr or stdout or '').splitlines() if line.strip()]
        return 'deck_error', (tail[-1] if tail else f'ngspice ended with exit code {returncode}')[:300]
    return None, ''
