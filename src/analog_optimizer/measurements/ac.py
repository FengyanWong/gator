"""Open-loop differential gain and unity-feedback estimates from an AC sweep."""
from __future__ import annotations
import cmath
import math


def measure_ac(frequencies, positive_input, negative_input, output):
    if len(frequencies) < 3 or any(len(v) != len(frequencies) for v in (positive_input, negative_input, output)):
        raise ValueError('Need at least three equally sized AC vectors')
    if any(not math.isfinite(f) or f <= 0 for f in frequencies) or any(b <= a for a, b in zip(frequencies, frequencies[1:])):
        raise ValueError('Frequencies must be finite, positive and strictly increasing')
    gain = []
    for vp, vn, vo in zip(positive_input, negative_input, output):
        if any(not (math.isfinite(complex(v).real) and math.isfinite(complex(v).imag)) for v in (vp, vn, vo)):
            raise ValueError('Non-finite AC value')
        differential = vp - vn
        if abs(differential) <= 1e-15:
            raise ValueError('Zero differential AC stimulus')
        h = vo / differential
        if abs(h) == 0 or not (math.isfinite(h.real) and math.isfinite(h.imag)):
            raise ValueError('Invalid transfer value')
        gain.append(h)
    db = [20 * math.log10(abs(h)) for h in gain]
    phase = []
    for h in gain:
        value = math.degrees(cmath.phase(h))
        if phase:
            value = phase[-1] + (value - phase[-1] + 180) % 360 - 180
        phase.append(value)

    def crossings(level):
        found = []
        for i in range(1, len(db)):
            if db[i - 1] > level >= db[i]:
                fraction = (level - db[i - 1]) / (db[i] - db[i - 1])
                freq = math.exp(math.log(frequencies[i-1]) + fraction * math.log(frequencies[i] / frequencies[i-1]))
                angle = phase[i-1] + fraction * (phase[i] - phase[i-1])
                found.append((freq, angle))
        return found

    bandwidth = crossings(db[0] - 3)
    unity = crossings(0)
    # A single downward crossing and non-inverting low-frequency response
    # are required. This is an estimate for unity negative feedback, not STB.
    ugf = unity[0][0] if len(unity) == 1 and db[0] > 0 else None
    pm = 180 + unity[0][1] if ugf is not None and abs(phase[0]) < 45 else None
    return {
        'gain_db_at_start': db[0], 'gain_reference_hz': frequencies[0],
        'bandwidth_3db_hz': bandwidth[0][0] if bandwidth else None,
        'unity_gain_hz': ugf, 'phase_margin_estimate_deg': pm,
        'unity_downward_crossings': len(unity),
        'gain_db': db, 'phase_deg': phase,
    }
