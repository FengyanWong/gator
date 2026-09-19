import math
import pytest

from analog_optimizer.measurements.ac import measure_ac


def test_single_pole_known_response_and_differential_normalization():
    frequencies = [10 ** (i / 100) for i in range(701)]
    # A0=100, pole=1 kHz; stimulus is 2 V differential, not 1 V.
    response = [2 * 100 / (1 + 1j * f / 1000) for f in frequencies]
    m = measure_ac(frequencies, [1] * len(frequencies), [-1] * len(frequencies), response)
    assert m['gain_db_at_start'] == pytest.approx(40, abs=1e-4)
    assert m['bandwidth_3db_hz'] == pytest.approx(1000 * math.sqrt(10 ** .3 - 1), rel=1e-3)
    assert m['unity_gain_hz'] == pytest.approx(1000 * math.sqrt(100**2 - 1), rel=1e-4)
    assert m['phase_margin_estimate_deg'] == pytest.approx(90.573, abs=.002)


def test_missing_crossing_is_invalid_and_inverted_gain_has_no_pm():
    assert measure_ac([1, 2, 3], [1]*3, [0]*3, [2]*3)['unity_gain_hz'] is None
    assert measure_ac([1, 2, 3], [1]*3, [0]*3, [-10, -2, -.5])['phase_margin_estimate_deg'] is None


@pytest.mark.parametrize('frequencies,inputs,outputs', [
    ([1, 1, 3], [1]*3, [1]*3), ([1, 2, 3], [0]*3, [1]*3),
    ([1, 2, 3], [1]*3, [1, float('nan'), 1]), ([1, 2, 3], [1]*3, [1, 0, 1]),
])
def test_invalid_measurements_raise(frequencies, inputs, outputs):
    with pytest.raises(ValueError):
        measure_ac(frequencies, inputs, [0]*3, outputs)
