"""Collection resumes at fresh episodes; learner/replay use the saved position."""
from copy import deepcopy

ROUND = 'completed_parallel_round; restart collection at fresh episodes'
RUN = 'completed_parallel_run'


def parallel_state(rng, report, *, completed_before=0, calls_before=0, boundary=ROUND):
    return dict(version='collector-v2', boundary=boundary, collector_rng=rng.getstate(),
                completed_episodes=completed_before + report['completed_episodes'],
                simulation_calls=calls_before + report['simulation_calls'],
                collector_recovery='fresh episodes; no in-flight job adoption',
                call_count_kind=report.get('call_count_kind', 'confirmed'))


def restore_parallel(state, rng):
    if state.get('boundary') not in (ROUND, RUN):
        raise ValueError('Resume requires a completed parallel round or run checkpoint')
    for key in ('completed_episodes', 'simulation_calls'):
        if type(state.get(key)) is not int or state[key] < 0:
            raise ValueError(f'Invalid checkpoint cumulative counter: {key}')
    rng.setstate(state['collector_rng'])
    return deepcopy(state)
