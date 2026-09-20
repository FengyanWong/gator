"""Compare trusted baseline/half-step VCO artifacts without new simulations."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('half_step', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    a, b = (json.loads(p.read_text()) for p in (args.baseline,args.half_step))
    report = dict(passed=False, new_simulator_calls=0, baseline=str(args.baseline.resolve()),
                  half_step=str(args.half_step.resolve()), comparisons={})
    try:
        if not a['passed'] or not b['passed'] or a['timestep_scale'] != 1 or b['timestep_scale'] != .5:
            raise ValueError('Successful baseline and half-step qualifications required')
        x, y = a['stages'][0], b['stages'][0]
        if x['parameters'] != y['parameters']:
            raise ValueError('Precision comparison changed device widths')
        first, second = ((Path(s['job'])/'vco.scs').read_text() for s in (x,y))
        if first.count('maxstep=1e-10') != 3 or first.replace('maxstep=1e-10','maxstep=5e-11') != second:
            raise ValueError('Decks differ beyond the three maximum timestep settings')
        # Limits fixed before the tighter run: 0.1% frequency/tuning, 0.5% power,
        # 1 mV swing and 0.001 duty, 2 ns detection latency.
        limits = {k:('relative',.001) for k in ('vco_frequency_low_hz','vco_frequency_hz',
                    'vco_frequency_high_hz','vco_tuning_gain_hz_per_v','vco_tuning_fraction')}
        limits.update(supply_power_w=('relative',.005),vco_minimum_swing_v=('absolute',.001),
                      vco_duty_cycle=('absolute',.001),vco_startup_detection_s=('absolute',2e-9))
        for key, (mode, limit) in limits.items():
            before, after = x['metrics'][key], y['metrics'][key]
            difference = abs(after-before)/(abs(before) if mode == 'relative' else 1.)
            report['comparisons'][key] = dict(baseline=before,half_step=after,mode=mode,
                                             difference=difference,limit=limit,passed=difference<=limit)
        report['passed'] = all(v['passed'] for v in report['comparisons'].values())
        if not report['passed']: raise ValueError('Timestep sensitivity exceeds declared qualification limits')
    except BaseException as exc:
        report.update(error_type=type(exc).__name__,error=str(exc)); raise
    finally:
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
