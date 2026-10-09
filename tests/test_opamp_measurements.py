"""The five-transistor OTA's measurement reader, `measurements.opamp.analyze` (record 7.292: it had no test, and the
optimizer clean-up of the plan's E9 moves its start-up code). No simulation: the Spectre job folder is written here and
the bridge's PSF reader is a stand-in (as in test_vco), answering from in-memory datasets of a single-pole amplifier."""
import cmath
import csv
import json
import math
import sys
from types import ModuleType

import pytest

from analog_optimizer.measurements import opamp

A0, POLE = 100.0, 1e3                                   # 40 dB, -3 dB at 1 kHz: unity gain near 100 kHz, phase margin ~90.6 deg
FREQ = [10 * 10 ** (k / 10) for k in range(61)]       # 10 Hz .. 10 MHz, ten points a decade
MOS = tuple(f'M{i}' for i in range(1, 6))
OP_KEYS = ('ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat', 'region')


def datasets(supply=1.8):
    response = [A0 / complex(1, f / POLE) for f in FREQ]
    dc = {'VDD': supply, 'VOUT': 0.9, 'VINP': 0.9, 'VINN': 0.9, 'VBIAS': 0.5, 'XU1.NTAIL': 0.2, 'XU1.NLOAD': 1.2,
          'VDD:p': -40e-6}
    op = {f'XU1.{m}:{key}': 1e-6 * (i + 1) for i, m in enumerate(MOS) for key in OP_KEYS}
    ac = {'freq': FREQ, 'VINP': [0.5 + 0j] * len(FREQ), 'VINN': [-0.5 + 0j] * len(FREQ), 'VOUT': response}
    return {'dcOp.dc': dc, 'dcOpInfo.info': op, 'ac.ac': ac}


@pytest.fixture
def psf(monkeypatch):
    """The bridge's PSF reader, answering from the datasets the test sets in `psf.data`."""
    module = ModuleType('virtuoso_bridge.spectre.psf')
    module.data = datasets()
    module.result_file = lambda raw, name: raw / name
    module.read_psf_ascii = lambda path: module.data[path.name]
    module.scalar = lambda dataset, key: dataset[key]
    module.vector = lambda dataset, key: dataset[key]
    module.frequency_hz = lambda dataset: dataset['freq']
    monkeypatch.setitem(sys.modules, 'virtuoso_bridge.spectre.psf', module)
    return module


def job(tmp_path, *, status='success', condition=None, log='spectre completes with 0 errors, 3 warnings, and 5 notices.',
        returncode=0, errors=()):
    folder = tmp_path / 'job'
    (folder / 'results').mkdir(parents=True)
    (folder / 'results' / 'spectre.out').write_text(log + '\n')
    result = dict(status=status, job_id='job-1', section='tt', temperature_c=27.0, errors=list(errors),
                  metadata=dict(output_dir=str(tmp_path / 'raw'), returncode=returncode))
    if condition is not None:
        result['condition'] = condition
    (folder / 'result.json').write_text(json.dumps(result))
    return folder


def test_a_single_pole_amplifier_is_measured_as_it_is(tmp_path, psf):
    folder = job(tmp_path)
    summary = opamp.analyze(folder)
    metrics = summary['metrics']
    unity = POLE * math.sqrt(A0 ** 2 - 1)                                    # |A0 / (1 + j f/POLE)| = 1
    assert metrics['gain_db_at_start'] == pytest.approx(20 * math.log10(abs(A0 / complex(1, FREQ[0] / POLE))))
    assert metrics['gain_reference_hz'] == FREQ[0]
    assert metrics['bandwidth_3db_hz'] == pytest.approx(POLE, rel=0.02)
    assert metrics['unity_gain_hz'] == pytest.approx(unity, rel=0.02)
    assert metrics['phase_margin_estimate_deg'] == pytest.approx(180 + math.degrees(cmath.phase(A0 / complex(1, unity / POLE))),
                                                                 abs=0.5)
    assert metrics['unity_downward_crossings'] == 1
    assert metrics['supply_current_a'] == pytest.approx(40e-6) and metrics['supply_power_w'] == pytest.approx(72e-6)
    assert metrics['output_dc_v'] == 0.9
    assert 'gain_db' not in metrics and 'phase_deg' not in metrics             # the curves go to the CSV, not the metrics
    assert summary['metric_validity'] == {name: True for name in metrics}
    assert set(summary['metric_units']) == set(metrics)
    assert (summary['origin'], summary['job_id'], summary['section'], summary['temperature_c']) == ('real', 'job-1', 'tt', 27.0)
    assert summary['condition'] is None and summary['dc']['VDD'] == 1.8
    assert set(summary['operating_points']) == {f'XU1.{m}' for m in MOS}
    assert all(set(point) == set(OP_KEYS) for point in summary['operating_points'].values())
    assert summary['operating_points']['XU1.M3']['gm'] == pytest.approx(3e-6)
    assert summary['execution_evidence'] == dict(returncode=0, errors=0, warnings=3, notices=5, bridge_diagnostics=[],
                                                 bridge_080_license_false_positive=False)
    assert json.loads((folder / 'measurements.json').read_text()) == summary
    with (folder / 'ac_response.csv').open(newline='') as stream:
        table = list(csv.reader(stream))
    assert table[0] == ['frequency_hz', 'gain_db', 'phase_deg'] and len(table) == 1 + len(FREQ)
    assert float(table[1][1]) == pytest.approx(metrics['gain_db_at_start'])
    assert float(table[-1][2]) == pytest.approx(math.degrees(cmath.phase(A0 / complex(1, FREQ[-1] / POLE))), abs=1e-9)


def test_a_condition_must_match_the_measured_supply(tmp_path, psf):
    condition = dict(corner=dict(supply_v=1.8, temperature_c=27.0), monte_carlo=None)
    assert opamp.analyze(job(tmp_path / 'same', condition=condition))['condition'] == condition
    psf.data = datasets(supply=1.62)
    with pytest.raises(ValueError, match='Measured VDD differs from the requested PVT condition'):
        opamp.analyze(job(tmp_path / 'other', condition=condition))
    with pytest.raises(ValueError, match='Monte Carlo requires an explicit per-sample measurement reader'):
        opamp.analyze(job(tmp_path / 'mc', condition=dict(condition, monte_carlo=dict(seed=1))))


@pytest.mark.parametrize('damage', ['failed', 'nonzero_exit', 'errors_in_log', 'two_summaries', 'fatal', 'diagnostics'])
def test_a_simulation_without_clean_completion_evidence_is_refused(tmp_path, psf, damage):
    clean = 'spectre completes with 0 errors, 0 warnings, and 0 notices.'
    folder = job(tmp_path, **dict(failed=dict(status='error'), nonzero_exit=dict(returncode=1),
                                  errors_in_log=dict(log='spectre completes with 2 errors, 0 warnings, and 0 notices.'),
                                  two_summaries=dict(log=clean + '\n' + clean), fatal=dict(log='Fatal error found\n' + clean),
                                  diagnostics=dict(errors=['netlist error']))[damage])
    with pytest.raises(ValueError):
        opamp.analyze(folder)
    assert not (folder / 'measurements.json').exists()


def test_bad_ac_data_is_a_measurement_failure(tmp_path, psf):
    psf.data['ac.ac'] = dict(psf.data['ac.ac'], VINN=psf.data['ac.ac']['VINP'])          # no differential stimulus
    with pytest.raises(ValueError, match='Zero differential AC stimulus'):
        opamp.analyze(job(tmp_path))
