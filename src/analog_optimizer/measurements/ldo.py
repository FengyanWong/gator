"""Explicit DC, small-signal supply rejection and held load-step measurements."""
import json
import math
from pathlib import Path
from statistics import mean

from analog_optimizer.backends.gpdk045 import number
from analog_optimizer.measurements.spectre_job import completion_evidence, raw_folder, read_result


def real_vector(values, name):
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError(f'{name} needs at least two samples')
    if any(isinstance(v, bool) or not isinstance(v, (int, float, complex)) or
           complex(v).imag != 0 or not math.isfinite(complex(v).real) for v in values):
        raise ValueError(f'{name} must be finite and real')
    return [complex(v).real for v in values]


def endpoint_regulation(axis, output, expected_start, expected_stop):
    axis, output = real_vector(axis, 'sweep axis'), real_vector(output, 'sweep output')
    if len(axis) != len(output) or any(b <= a for a,b in zip(axis,axis[1:])):
        raise ValueError('Sweep samples must match and increase strictly')
    if not all(math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-12) for a,b in
               ((axis[0],expected_start),(axis[-1],expected_stop))):
        raise ValueError('Sweep did not cover its declared endpoints')
    return abs((output[-1]-output[0])/(axis[-1]-axis[0]))


def psrr_at(frequency, supply, output, target=1000.):
    frequency = real_vector(frequency, 'frequency')
    if (len(supply) != len(output) or len(supply) != len(frequency) or
            any(b <= a for a,b in zip(frequency,frequency[1:])) or frequency[0] <= 0):
        raise ValueError('AC samples must match a positive increasing frequency axis')
    gains = []
    for vin,vout in zip(supply,output):
        if any(not math.isfinite(complex(v).real) or not math.isfinite(complex(v).imag) or abs(v)==0
               for v in (vin,vout)):
            raise ValueError('PSRR requires finite nonzero supply and output responses')
        gains.append(-20*math.log10(abs(vout/vin)))
    for i,(a,b) in enumerate(zip(frequency,frequency[1:])):
        if a <= target <= b:
            fraction=math.log(target/a)/math.log(b/a)
            return gains[i]+fraction*(gains[i+1]-gains[i])
    raise ValueError('PSRR frequency outside the observed range')


def load_step_metrics(time, output, current, *, delay, rise, stop, low, high, nominal_output):
    time,output,current = (real_vector(v,n) for v,n in ((time,'time'),(output,'output'),(current,'current')))
    if (not 0 < delay < delay+rise < stop or not 0 < low < high or
            len(time)!=len(output) or len(time)!=len(current) or
            any(b<=a for a,b in zip(time,time[1:])) or time[0] > 1e-12 or
            not math.isclose(time[-1],stop,rel_tol=1e-6,abs_tol=1e-12)):
        raise ValueError('Incomplete or inconsistent transient coverage')
    pre=[i for i,t in enumerate(time) if delay*.5 <= t <= delay*.9]
    post=[i for i,t in enumerate(time) if t >= delay+rise]
    tail=[i for i,t in enumerate(time) if t >= delay+.8*(stop-delay)]
    if min(len(pre),len(post),len(tail)) < 3:
        raise ValueError('Insufficient samples in transient measurement windows')
    for indices,expected in ((pre,low),(post,high)):
        if any(not math.isclose(current[i],expected,rel_tol=1e-5,abs_tol=1e-12) for i in indices):
            raise ValueError('Measured load does not match the declared held step')
    baseline=mean(output[i] for i in pre)
    if not math.isclose(baseline,nominal_output,rel_tol=1e-4,abs_tol=1e-6):
        raise ValueError('Pre-step transient does not match the nominal operating point')
    changed=[v for t,v in zip(time,output) if t >= delay]
    final=[output[i] for i in tail]
    return dict(ldo_step_deviation_v=max(abs(v-baseline) for v in changed),
                ldo_step_final_shift_v=abs(mean(final)-baseline),
                ldo_step_tail_ripple_v=max(final)-min(final))


def analyze(job, *, design, result_name='bridge_result.json', mos_names=('M1','M2','M3','M4','M5','MP')):
    from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, scalar, vector, frequency_hz
    job=Path(job)
    result=read_result(job,result_name)
    if result['status']!='success':
        raise ValueError('Simulation did not succeed')
    condition=result['condition']
    if condition['purpose']!='nominal' or condition.get('monte_carlo') is not None:
        raise ValueError('LDO measurements currently require nominal-only execution')
    evidence=completion_evidence(job,result)
    raw=raw_folder(result)
    datasets={name:read_psf_ascii(result_file(raw,filename)) for name,filename in (
        ('dc','dcOp.dc'),('op','dcOpInfo.info'),('ac','ac.ac'),
        ('line','lineSweep.dc'),('load','loadSweep.dc'),('tran','tran.tran.tran'))}
    dc={key:scalar(datasets['dc'],key) for key in ('VDD','VOUT','VREF','VBIAS','VDD:p','ILOAD:i','XU1.VFB','XU1.VGATE')}
    for key,expected in (('VDD',condition['corner']['supply_v']),('VREF',number(design['reference_v'])),
                         ('VBIAS',number(design['bias_v'])),('ILOAD:i',number(design['load_current']))):
        if not math.isclose(dc[key],expected,rel_tol=1e-6,abs_tol=1e-12):
            raise ValueError(f'Measured {key} differs from the testbench contract')
    target=number(design['reference_v'])*(1+number(design['feedback_upper'])/number(design['feedback_lower']))
    load_low,load_high=map(number,(design['load_current'],design['load_current_high']))
    metrics=dict(output_dc_v=dc['VOUT'],supply_power_w=-dc['VDD:p']*dc['VDD'],
        ldo_output_error_v=abs(dc['VOUT']-target),ldo_quiescent_current_a=-dc['VDD:p']-dc['ILOAD:i'],
        ldo_line_regulation_v_per_v=endpoint_regulation(vector(datasets['line'],'VDD'),vector(datasets['line'],'VOUT'),.95,1.05),
        ldo_load_regulation_v_per_a=endpoint_regulation(vector(datasets['load'],'ILOAD:i'),vector(datasets['load'],'VOUT'),load_low,load_high),
        ldo_psrr_1khz_db=psrr_at(frequency_hz(datasets['ac']),vector(datasets['ac'],'VDD'),vector(datasets['ac'],'VOUT')))
    metrics.update(load_step_metrics(vector(datasets['tran'],'time'),vector(datasets['tran'],'VOUT'),
        vector(datasets['tran'],'ILOAD:i'),delay=number(design['step_delay']),rise=number(design['step_rise']),
        stop=number(design['tran_stop']),low=load_low,high=load_high,nominal_output=dc['VOUT']))
    op={f'XU1.{name}':{key:scalar(datasets['op'],f'XU1.{name}:{key}')
        for key in ('ids','gm','gds','vgs','vds','vth','vdsat','region')} for name in mos_names}
    units=dict(output_dc_v='V',supply_power_w='W',ldo_output_error_v='V',ldo_quiescent_current_a='A',
        ldo_line_regulation_v_per_v='V/V',ldo_load_regulation_v_per_a='V/A',ldo_psrr_1khz_db='dB',
        ldo_step_deviation_v='V',ldo_step_final_shift_v='V',ldo_step_tail_ripple_v='V')
    summary=dict(origin='real',job_id=result['job_id'],condition=condition,metrics=metrics,
        metric_units=units,metric_validity={k:math.isfinite(v) for k,v in metrics.items()},dc=dc,
        operating_points=op,execution_evidence=evidence,reference_output_v=target,
        notes=['Ideal reference/bias generation power is excluded; divider current is included in quiescent current.',
               'Line/load metrics are absolute endpoint slopes over the declared sweeps, not differential worst cases.',
               'Transient starts from its DC operating point; finite-window settling is not a startup or STB stability proof.',
               'Supply sweep is a fixed characterization analysis in a nominal candidate package, not PVT training.'])
    (job/'measurements.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary
