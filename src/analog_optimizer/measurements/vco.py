"""Sustained ring oscillation and three-point voltage tuning from real transients."""
from bisect import bisect_left, bisect_right
import json
import math
from pathlib import Path
from statistics import mean, median

from analog_optimizer.backends.gpdk045 import number
from analog_optimizer.backends.spectre_validation import validate_completion
from .ldo import real_vector


def checked_trace(time, values):
    time, values = real_vector(time, 'time'), real_vector(values, 'trace')
    if len(time) != len(values) or any(b <= a for a,b in zip(time,time[1:])):
        raise ValueError('Transient samples must match a strictly increasing time axis')
    return time, values


def crossings(time, values, threshold, rising=True):
    """Linearly interpolated crossings; callers validate samples and resolution."""
    result = []
    for a,b,x,y in zip(time,time[1:],values,values[1:]):
        if (x < threshold <= y) if rising else (x > threshold >= y):
            result.append(a+(b-a)*(threshold-x)/(y-x))
    return result


def window_mean(time, values, start, stop):
    """Time-weighted trapezoidal mean on an exactly clipped window."""
    time, values = checked_trace(time, values)
    if not time[0] <= start < stop <= time[-1]:
        raise ValueError('Mean window outside trace')
    def at(t):
        i = bisect_left(time,t)
        if time[i] == t: return values[i]
        return values[i-1]+(values[i]-values[i-1])*(t-time[i-1])/(time[i]-time[i-1])
    indices = range(bisect_right(time,start),bisect_left(time,stop))
    points = [(start,at(start))]+[(time[i],values[i]) for i in indices]+[(stop,at(stop))]
    return sum((b-a)*(x+y)/2 for (a,x),(b,y) in zip(points,points[1:]))/(stop-start)


def oscillation_metrics(time, voltage, *, supply, start, stop, minimum_cycles=8,
                        minimum_swing_fraction=.8, maximum_period_spread=.02,
                        maximum_half_window_drift=.01):
    time, voltage = checked_trace(time, voltage)
    if (not 0 < start < stop or time[0] > 1e-15 or
            not math.isclose(time[-1],stop,rel_tol=1e-8,abs_tol=1e-15)):
        raise ValueError('Incomplete oscillator transient coverage')
    if (not math.isfinite(supply) or supply <= 0 or minimum_cycles < 3 or
            not 0 < minimum_swing_fraction <= 1 or not 0 < maximum_period_spread < 1 or
            not 0 < maximum_half_window_drift < 1):
        raise ValueError('Invalid oscillator measurement contract')
    rising = crossings(time,voltage,supply/2)
    falling = crossings(time,voltage,supply/2,False)
    steady = [t for t in rising if start <= t <= stop]
    if len(steady) < minimum_cycles+1:
        raise ValueError('No sustained oscillation: insufficient complete cycles')
    periods = [b-a for a,b in zip(steady,steady[1:])]
    period = median(periods)
    if (max(periods)-min(periods))/period > maximum_period_spread:
        raise ValueError('Unsettled or irregular oscillator periods')
    measured_times = time[max(0,bisect_left(time,start)-1):]
    if max(b-a for a,b in zip(measured_times,measured_times[1:])) > min(periods)/40:
        raise ValueError('Oscillator waveform is undersampled')
    halves = [[b-a for a,b in zip(steady,steady[1:]) if lo <= a and b <= hi]
              for lo,hi in ((start,(start+stop)/2),((start+stop)/2,stop))]
    if min(map(len,halves)) < minimum_cycles:
        raise ValueError('Insufficient sustained cycles in each half window')
    drift = abs(mean(halves[0])-mean(halves[1]))/period
    if drift > maximum_half_window_drift:
        raise ValueError('Oscillator frequency drifts between steady-state windows')

    def cycle(a,b):
        samples = voltage[bisect_left(time,a):bisect_right(time,b)]
        fall = falling[bisect_right(falling,a):bisect_left(falling,b)]
        if (not samples or len(fall) != 1 or min(samples) > .2*supply or max(samples) < .8*supply
                or max(samples)-min(samples) < minimum_swing_fraction*supply):
            raise ValueError('Oscillation lacks a full swing or has extra crossings')
        return max(samples)-min(samples), (fall[0]-a)/(b-a)
    checked = [cycle(a,b) for a,b in zip(steady,steady[1:])]
    # Detection ends after N full, late-frequency-consistent cycles from the declared IC.
    # This is not spontaneous/noise-driven physical startup.
    run, detected = 0, None
    for a,b in zip(rising,rising[1:]):
        good = abs((b-a)-period)/period <= maximum_period_spread
        if good:
            try: cycle(a,b)
            except ValueError: good = False
        run = run+1 if good else 0
        if run >= minimum_cycles:
            detected = b; break
    if detected is None or detected > start:
        raise ValueError('Oscillator did not establish sustained cycles by the declared deadline')
    return dict(frequency_hz=1/mean(periods), minimum_cycle_swing_v=min(v[0] for v in checked),
                duty_cycle=mean(v[1] for v in checked), period_spread=(max(periods)-min(periods))/period,
                half_window_drift=drift, startup_detection_s=detected,
                complete_cycles=len(periods), rising_crossings_s=steady)


def analyze(job, *, design, analysis_settings=None, result_name='bridge_result.json', mos_names=()):
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, scalar, vector
    job = Path(job)
    result = json.loads((job/result_name).read_text())
    recorded_settings = result.get('analysis_settings')
    if recorded_settings != analysis_settings:
        raise ValueError('VCO analysis settings differ from executed manifest')
    condition = result['condition']
    if result['status'] != 'success' or condition['purpose'] != 'nominal' or condition.get('monte_carlo') is not None:
        raise ValueError('VCO measurements require a successful nominal execution')
    evidence = validate_completion((job/'results/spectre.out').read_text(),result['metadata']['returncode'],result['errors'])
    raw = Path(result['metadata']['output_dir'])
    dc = read_psf_ascii(result_file(raw,'dcOp.dc'))
    op = read_psf_ascii(result_file(raw,'dcOpInfo.info'))
    supply, start, stop = (number(design[k]) for k in ('supply_v','measurement_start','tran_stop'))
    if analysis_settings is not None:
        start, stop = analysis_settings['start_s'], analysis_settings['stop_s']
    for key,expected in (('VDD',supply),('VCTRL',number(design['control_v']))):
        if not math.isclose(scalar(dc,key),expected,rel_tol=1e-7,abs_tol=1e-12):
            raise ValueError('VCO DC testbench stimulus mismatch')
    settings = {k:design[k] for k in ('minimum_cycles','minimum_swing_fraction','maximum_period_spread','maximum_half_window_drift')}
    points = {}
    for label,key in (('Low','control_low_v'),('Nom','control_v'),('High','control_high_v')):
        data = read_psf_ascii(result_file(raw,f'tran{label}.tran.tran'))
        time = real_vector(vector(data,'time'),'time')
        for signal,expected in (('VDD',supply),('VCTRL',number(design[key]))):
            _, values = checked_trace(time,vector(data,signal))
            if any(not math.isclose(v,expected,rel_tol=1e-6,abs_tol=1e-9) for v in values):
                raise ValueError(f'Incorrect transient stimulus: {label}/{signal}')
        stages = {name:oscillation_metrics(time,vector(data,name),supply=supply,start=start,stop=stop,**settings)
                  for name in ('XU1.N1','XU1.N2','VOUT')}
        frequencies = [s['frequency_hz'] for s in stages.values()]
        if (max(frequencies)-min(frequencies))/mean(frequencies) > .01:
            raise ValueError('Ring stages have inconsistent frequencies')
        power = -supply*window_mean(time,vector(data,'VDD:p'),start,stop)
        if power <= 0: raise ValueError('Invalid mean supply power')
        points[label] = dict(control_v=number(design[key]),stages=stages,power_w=power)
    low,nom,high = (points[k]['stages']['VOUT']['frequency_hz'] for k in ('Low','Nom','High'))
    if not low < nom < high:
        raise ValueError('Control voltage does not produce increasing oscillation frequency')
    stages = [s for p in points.values() for s in p['stages'].values()]
    metrics = dict(vco_frequency_hz=nom,vco_frequency_low_hz=low,vco_frequency_high_hz=high,
        vco_tuning_gain_hz_per_v=(high-low)/(points['High']['control_v']-points['Low']['control_v']),
        vco_tuning_fraction=(high-low)/nom,supply_power_w=points['Nom']['power_w'],
        vco_minimum_swing_v=min(s['minimum_cycle_swing_v'] for s in stages),
        vco_max_period_spread=max(s['period_spread'] for s in stages),
        vco_max_window_drift=max(s['half_window_drift'] for s in stages),
        vco_startup_detection_s=max(s['startup_detection_s'] for s in stages),
        vco_duty_cycle=points['Nom']['stages']['VOUT']['duty_cycle'])
    units = dict(vco_frequency_hz='Hz',vco_frequency_low_hz='Hz',vco_frequency_high_hz='Hz',
        vco_tuning_gain_hz_per_v='Hz/V',vco_tuning_fraction='1',supply_power_w='W',
        vco_minimum_swing_v='V',vco_max_period_spread='1',vco_max_window_drift='1',
        vco_startup_detection_s='s',vco_duty_cycle='1')
    operating_points = {f'XU1.{name}':{key:scalar(op,f'XU1.{name}:{key}')
        for key in ('ids','gm','gds','vgs','vds','vth','vdsat','region')} for name in mos_names}
    summary = dict(origin='real',job_id=result['job_id'],condition=condition,metrics=metrics,
        analysis_settings=analysis_settings,
        metric_units=units,metric_validity={k:math.isfinite(v) for k,v in metrics.items()},
        operating_points=operating_points,execution_evidence=evidence,tuning_points=points,
        notes=['Startup detection uses declared initial conditions; not unassisted or noise-driven startup.',
               'Operating points are the nominal DC equilibrium, not phase-resolved oscillation values.',
               'Three control stimuli are fixed qualification analyses, not PVT or additional action dimensions.',
               'Deterministic transient period spread is not physical jitter or phase noise.'])
    (job/'measurements.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary
