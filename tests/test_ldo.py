"""LDO measurements; these tests perform no real simulations. The GPDK045 LDO profile's own tests left with its example
files on 2026-09-30 (record 7.128); they run from a checkout before that commit."""
import pytest

from analog_optimizer.measurements.ldo import endpoint_regulation, psrr_at, load_step_metrics


def test_regulation_and_psrr_use_measured_axes_and_input_amplitude():
    assert endpoint_regulation([.95,1,1.05],[.799,.8,.801],.95,1.05)==pytest.approx(.02)
    assert endpoint_regulation([1e-5,1.5e-5,2e-5],[.8,.799,.798],1e-5,2e-5)==pytest.approx(200)
    assert psrr_at([100,1000,10000],[2+0j]*3,[.02+0j]*3)==pytest.approx(40)
    with pytest.raises(ValueError): endpoint_regulation([1,1],[.8,.8],1,2)
    with pytest.raises(ValueError): endpoint_regulation([1,2],[.8,.8],0,2)
    with pytest.raises(ValueError): psrr_at([100,1000],[0j,1],[.1,.1])
    with pytest.raises(ValueError): psrr_at([1,2],[1,1],[.1,.1])


def trace():
    """Construct a synthetic output-voltage and load-current trace around a load step."""
    time=[i*1e-6 for i in range(81)]
    output=[.8 if t<10e-6 else .797 for t in time]
    current=[10e-6 if t<10e-6 else 20e-6 for t in time]
    kwargs=dict(delay=10e-6,rise=.1e-6,stop=80e-6,low=10e-6,high=20e-6,nominal_output=.8)
    return time,output,current,kwargs


def test_load_step_measures_deviation_and_finite_window_ripple():
    time,output,current,kwargs=trace()
    result=load_step_metrics(time,output,current,**kwargs)
    assert result['ldo_step_deviation_v']==pytest.approx(.003)
    assert result['ldo_step_final_shift_v']==pytest.approx(.003)
    assert result['ldo_step_tail_ripple_v']==0


@pytest.mark.parametrize('damage',['missing_step','truncated','nan','wrong_initial','unordered'])
def test_load_step_bad_data_is_measurement_failure(damage):
    time,output,current,kwargs=trace()
    if damage=='missing_step': current=[1e-5]*len(time)
    elif damage=='truncated': time,output,current=time[:-1],output[:-1],current[:-1]
    elif damage=='nan': output[-1]=float('nan')
    elif damage=='wrong_initial': kwargs['nominal_output']=.6
    else: time[-2]=time[-1]
    with pytest.raises(ValueError): load_step_metrics(time,output,current,**kwargs)
