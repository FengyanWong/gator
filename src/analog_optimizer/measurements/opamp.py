"""Measurements for the verified five-transistor OTA DC/AC testbench."""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
from .ac import measure_ac
from analog_optimizer.backends.spectre_validation import validate_completion


def analyze(job, *, result_name="result.json"):
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, scalar, vector, frequency_hz
    result = json.loads((job / result_name).read_text())
    if result['status'] != 'success':
        raise ValueError('Simulation did not succeed')
    raw = Path(result['metadata']['output_dir'])
    log_path = job / 'results' / 'spectre.out'
    evidence = validate_completion(log_path.read_text(), result['metadata']['returncode'], result['errors'])
    dc = read_psf_ascii(result_file(raw, 'dcOp.dc'))
    op = read_psf_ascii(result_file(raw, 'dcOpInfo.info'))
    ac = read_psf_ascii(result_file(raw, 'ac.ac'))
    freq = frequency_hz(ac)
    response = measure_ac(freq, vector(ac, 'VINP'), vector(ac, 'VINN'), vector(ac, 'VOUT'))
    with (job / 'ac_response.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frequency_hz', 'gain_db', 'phase_deg'])
        writer.writerows(zip(freq, response.pop('gain_db'), response.pop('phase_deg')))
    dc_values = {key: scalar(dc, key) for key in ('VDD', 'VOUT', 'VINP', 'VINN', 'VBIAS', 'XU1.NTAIL', 'XU1.NLOAD', 'VDD:p')}
    condition = result.get('condition')
    if condition is not None:
        # PVT labels must describe the actual measured supply. MC will require
        # per-sample directory selection before this single-point extractor.
        if condition.get('monte_carlo') is not None:
            raise ValueError('Monte Carlo requires an explicit per-sample measurement reader')
        if not math.isclose(dc_values['VDD'], condition['corner']['supply_v'], rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError('Measured VDD differs from the requested PVT condition')
    operating_points = {f'XU1.M{i}': {key: scalar(op, f'XU1.M{i}:{key}')
                        for key in ('ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat', 'region')}
                        for i in range(1, 6)}
    metrics = {**response, 'supply_current_a': -dc_values['VDD:p'],
               'supply_power_w': -dc_values['VDD:p'] * dc_values['VDD'],
               'output_dc_v': dc_values['VOUT']}
    summary = {'origin': 'real', 'job_id': result['job_id'], 'section': result['section'],
               'condition': condition,
               'temperature_c': result['temperature_c'], 'metrics': metrics,
               'metric_validity': {k: v is not None for k, v in metrics.items()},
               'metric_units': {'gain_db_at_start': 'dB', 'gain_reference_hz': 'Hz',
                                'bandwidth_3db_hz': 'Hz', 'unity_gain_hz': 'Hz',
                                'phase_margin_estimate_deg': 'deg', 'unity_downward_crossings': 'count',
                                'supply_current_a': 'A', 'supply_power_w': 'W', 'output_dc_v': 'V'},
               'dc': dc_values, 'operating_points': operating_points, 'execution_evidence': evidence,
               'notes': ['Phase margin is an open-loop unity-negative-feedback estimate, not an STB result.',
                         'Ideal bias voltage source; bias generator power is excluded.']}
    (job / 'measurements.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    return summary
