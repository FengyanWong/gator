"""Check baseline/perturbation/repeat results and plot their measured AC data."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path


def compare(baseline, perturbed, repeat):
    results = [json.loads((p / 'result.json').read_text()) for p in (baseline, perturbed, repeat)]
    data = [json.loads((p / 'measurements.json').read_text()) for p in (baseline, perturbed, repeat)]
    if any(r['status'] != 'success' or r['origin'] != 'real' for r in results):
        raise ValueError('All three real simulations must succeed')
    if len({r['job_id'] for r in results}) != 3:
        raise ValueError('Three distinct jobs required')
    if results[0]['executed_sha256'] != results[2]['executed_sha256']:
        raise ValueError('Repeat did not execute the original deck')
    if results[0]['executed_sha256'] == results[1]['executed_sha256']:
        raise ValueError('Perturbed deck did not change')
    if len({r['source_sha256'] for r in results}) != 1:
        raise ValueError('Source structure changed between runs')
    metrics = [d['metrics'] for d in data]
    for key in ('gain_db_at_start', 'unity_gain_hz', 'bandwidth_3db_hz', 'supply_power_w', 'output_dc_v'):
        if not math.isclose(metrics[0][key], metrics[2][key], rel_tol=1e-6, abs_tol=1e-12):
            raise ValueError(f'Baseline repeat mismatch: {key}')
    if not metrics[1]['unity_gain_hz'] < metrics[0]['unity_gain_hz']:
        raise ValueError('Larger CL did not lower unity-gain frequency')
    return {'passed': True, 'job_ids': [r['job_id'] for r in results],
            'repeat_relative_tolerance': 1e-6, 'repeat_absolute_tolerance': 1e-12,
            'same_original_deck': True, 'source_unchanged': True,
            'baseline_metrics': metrics[0], 'perturbed_metrics': metrics[1],
            'repeat_metrics': metrics[2]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path)
    p.add_argument('perturbed', type=Path)
    p.add_argument('repeat', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = compare(a.baseline, a.perturbed, a.repeat)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True, constrained_layout=True)
    for job, label, color, style in [(a.baseline, 'CL = 1.0 pF', '#007f88', '-'),
                                    (a.perturbed, 'CL = 1.1 pF', '#cc6c26', '--')]:
        with (job / 'ac_response.csv').open() as f:
            rows = list(csv.DictReader(f))
        freq = [float(r['frequency_hz']) for r in rows]
        axes[0].semilogx(freq, [float(r['gain_db']) for r in rows], style, color=color, lw=2, label=label)
        axes[1].semilogx(freq, [float(r['phase_deg']) for r in rows], style, color=color, lw=2)
    axes[0].axhline(0, color='gray', lw=.8)
    axes[0].set(ylabel='Differential gain (dB)', title='GPDK045 five-transistor OTA — measured Spectre AC response')
    axes[0].legend()
    axes[1].set(ylabel='Phase (degrees)', xlabel='Frequency (Hz)')
    for ax in axes:
        ax.grid(True, which='both', alpha=.16)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('TT · 27 °C · VDD = 1.0 V · VCM = 0.6 V · VBIAS = 0.4 V', fontsize=10)
    fig.savefig(a.output / 'opamp_ac.png', dpi=180)
    fig.savefig(a.output / 'opamp_ac.svg')
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
