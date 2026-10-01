"""A candidate's corner jobs two at a time (user decision of 2026-09-30): the rows, the call accounting and the stops of the
one-at-a-time plan, with at most `condition_jobs` simulations running at once. Scripted fixtures only: no circuit
solver, bridge or electrical evidence."""
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from analog_optimizer.backends import virtuoso_bridge
from analog_optimizer.backends.backend import SimulationStatus as Status
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.backends.native_preparation import NativeCandidateBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from tests.reward_v21_support import NOMINAL, ScriptedRealBackend, specs

CORNERS = tuple(SimulationCondition(PVTCorner(f'corner_{i}', 'ss', 125., .9), purpose='pvt_training') for i in range(4))
PLAN = (NOMINAL, *CORNERS)
UNAVAILABLE = (Status.BACKEND_ERROR, False, {'score': None, 'other': None}, {'score': False, 'other': False},
               {'score': 'fixture', 'other': 'fixture'})


class SideBySideBackend(ScriptedRealBackend):
    """ScriptedRealBackend with four corners, slow enough for jobs to overlap; it records when each job starts, how many
    run at once and on which thread."""
    concurrent_condition_jobs = 2

    def __init__(self, graph):
        super().__init__(graph, nominal_pass=True)
        self.lock = threading.Lock()
        self.running = self.peak = 0
        self.started, self.threads, self.delay, self.raises, self.on_start = [], {}, {}, {}, {}

    def validate_condition(self, condition):
        assert condition in PLAN

    def delegated(self, call):
        return call

    def run_simulation(self, request):
        with self.lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
            self.started.append(request.condition)
            self.threads[request.condition] = threading.get_ident()
        try:
            if request.condition in self.on_start:
                self.on_start[request.condition](request)
            time.sleep(self.delay.get(request.condition, .15))
            if request.condition in self.raises:
                raise self.raises[request.condition]
            with self.lock:
                return super().run_simulation(request)
        finally:
            with self.lock:
                self.running -= 1


def env_for(graph, directory, jobs):
    backend = SideBySideBackend(graph)
    return CircuitSizingEnv(backend, backend.graph, specs(), directory, max_steps=3, stop_on_success=False,
                            condition_policy='after_nominal', corners=CORNERS, condition_jobs=jobs)


def run_step(env, *, stop_file=None):
    """A reset, then one step of the full plan; the backend's start log begins at the step."""
    env.authorize_launches(1)
    env.reset()
    env.backend.started.clear()
    env.backend.peak = 0
    env.authorize_launches(len(PLAN), stop_file=stop_file)
    result = env.step({key: 0. for key in env.mapper.group_ids})
    return result, json.loads(Path(result[4]['record_path']).read_text())


def rows_of(record):
    return [(r['condition']['corner']['id'] if r['condition'] else 'nominal', r['status'], r['metrics'])
            for r in record['condition_results']]


def test_corner_jobs_run_two_at_a_time_and_give_the_one_at_a_time_result(opamp, tmp_path):
    outcome = {}
    for jobs in (1, 2):
        with env_for(opamp, tmp_path / f'jobs{jobs}', jobs) as env:
            result, record = run_step(env)
            outcome[jobs] = dict(result=result, record=record, peak=env.backend.peak, started=list(env.backend.started),
                                 threads=dict(env.backend.threads), counters=(env.simulation_calls, env.confirmed_calls,
                                                                              env.uncertain_calls))
    one, two = outcome[1], outcome[2]
    assert one['peak'] == 1 and two['peak'] == 2                          # never more than two at once
    assert one['started'] == two['started'] == list(PLAN)                   # launched in plan order
    assert rows_of(one['record']) == rows_of(two['record']) and len(two['record']['condition_results']) == len(PLAN)
    assert one['result'][1] == two['result'][1] and one['counters'] == two['counters']   # the same reward and accounting
    assert [j['index'] for j in two['record']['jobs']] == list(range(len(PLAN)))
    assert all(j['state'] == 'completed' for j in two['record']['jobs'])
    main = two['threads'][NOMINAL]                                           # the nominal on the owning thread,
    assert all(two['threads'][c] != main for c in CORNERS)                  # the corners on helper threads
    info_one, info_two = one['result'][4], two['result'][4]
    for key in ('conditions_evaluated', 'conditions_complete', 'nominal_success', 'robust_success', 'margins',
                'clearance_margin', 'worst_values', 'worst_conditions'):
        assert info_one[key] == info_two[key], key


def test_every_launch_intent_is_on_disk_before_its_job_starts(opamp, tmp_path):
    with env_for(opamp, tmp_path / 'w', 2) as env:
        seen = {}

        def look(request):                                                   # at the moment the simulator starts
            index = PLAN.index(request.condition)
            files = sorted(env.directory.glob(f'launch-*-{index}.json'), key=lambda p: p.stat().st_mtime)
            seen[index] = json.loads(files[-1].read_text())['state'] if files else None
        env.backend.on_start = {c: look for c in CORNERS}
        run_step(env)
    assert seen == {1: 'launch_intent', 2: 'launch_intent', 3: 'launch_intent', 4: 'launch_intent'}


def test_an_unavailable_corner_ends_the_launches_and_the_job_already_running_adds_no_row(opamp, tmp_path):
    outcome = {}
    for jobs in (1, 2):
        with env_for(opamp, tmp_path / f'jobs{jobs}', jobs) as env:
            env.backend.outcomes[CORNERS[0]] = UNAVAILABLE
            env.backend.delay[CORNERS[0]] = .3                              # its neighbour finishes first
            result, record = run_step(env)
            outcome[jobs] = dict(result=result, record=record, started=list(env.backend.started),
                                 calls=env.simulation_calls)
    one, two = outcome[1], outcome[2]
    assert one['started'] == [NOMINAL, CORNERS[0]]
    assert two['started'] == [NOMINAL, CORNERS[0], CORNERS[1]]              # corner 1 had already started
    assert rows_of(one['record']) == rows_of(two['record'])                # its row does not count
    assert [r[0] for r in rows_of(two['record'])] == ['nominal', 'corner_0']
    assert two['record']['conditions_stop_reason'] == one['record']['conditions_stop_reason'] == 'unavailable_or_uncertain_condition'
    assert len(two['record']['jobs']) == 3 and all(j['state'] == 'completed' for j in two['record']['jobs'])   # but it is accounted
    assert two['calls'] == one['calls'] + 1
    assert one['result'][3] and two['result'][3] and one['result'][1] is None and two['result'][1] is None   # truncated alike


def test_a_failing_job_waits_for_the_one_beside_it_and_launches_nothing_more(opamp, tmp_path):
    with env_for(opamp, tmp_path / 'w', 2) as env:
        env.backend.raises[CORNERS[1]] = ValueError('FIXTURE: the simulator host refused the job')
        env.backend.delay[CORNERS[0]] = .4
        try:
            run_step(env)
        except ValueError as error:
            assert 'FIXTURE' in str(error)
        else:
            raise AssertionError('the failure was not raised')
        assert env.backend.running == 0                                      # nothing left running
        assert env.backend.started == [NOMINAL, CORNERS[0], CORNERS[1]]    # no corner after the failure
        record = json.loads(sorted((env.directory / 'candidates').glob('*.json'), key=lambda p: p.stat().st_mtime)[-1].read_text())
    states = {j['index']: j['state'] for j in record['jobs']}
    assert record['state'] == 'execution_error' and states == {0: 'completed', 1: 'completed', 2: 'launch_intent'}


def test_a_coordinator_stop_ends_the_launches_and_the_running_jobs_keep_their_rows(opamp, tmp_path):
    outcome = {}
    for jobs in (1, 2):
        stop = tmp_path / f'stop{jobs}'
        with env_for(opamp, tmp_path / f'jobs{jobs}', jobs) as env:
            env.backend.on_start = {CORNERS[1]: lambda request, stop=stop: stop.touch()}
            env.backend.delay[CORNERS[0]] = .3
            result, record = run_step(env, stop_file=stop)
            outcome[jobs] = dict(record=record, started=list(env.backend.started))
    for jobs in (1, 2):
        assert outcome[jobs]['started'] == [NOMINAL, CORNERS[0], CORNERS[1]], jobs
        assert outcome[jobs]['record']['conditions_stop_reason'] == 'coordinator_stop'
    assert rows_of(outcome[1]['record']) == rows_of(outcome[2]['record'])


def test_one_job_at_a_time_where_the_backend_or_the_circuit_says_so(opamp, tmp_path):
    capacity = NativeCandidateBackend.concurrent_condition_jobs.fget
    assert capacity(SimpleNamespace(circuit=SimpleNamespace())) == 2
    assert capacity(SimpleNamespace(circuit=SimpleNamespace(measures_in_virtuoso=True))) == 1   # OCEAN in the session
    assert virtuoso_bridge.VirtuosoBridgeBackend.concurrent_condition_jobs == 1
    with env_for(opamp, tmp_path / 'w', 2) as env:
        env.backend.concurrent_condition_jobs = 1
        run_step(env)
        assert env.backend.peak == 1


def test_a_helper_thread_passes_the_owner_check_only_when_delegated_for_a_simulation(tmp_path):
    env_file = tmp_path / 'bridge.env'
    env_file.write_text('VB_FIXTURE=1\n')
    backend = virtuoso_bridge.VirtuosoBridgeBackend.__new__(virtuoso_bridge.VirtuosoBridgeBackend)
    backend.config = SimpleNamespace(env_file=env_file)
    backend.client, backend._thread, backend.bridge_version = object(), threading.get_ident(), 'fixture'
    backend._env_hash, backend._bound_env = virtuoso_bridge.digest(env_file), backend._vb_env()
    backend._require_connection()
    outcome = {}

    def helper():
        for name, call in [('plain', lambda: backend._require_connection(delegable=True)),
                           ('delegated, other call', backend.delegated(lambda: backend._require_connection())),
                           ('delegated simulation', backend.delegated(lambda: backend._require_connection(delegable=True)))]:
            try:
                call()
                outcome[name] = 'passed'
            except RuntimeError:
                outcome[name] = 'refused'
    thread = threading.Thread(target=helper)
    thread.start()
    thread.join()
    assert outcome == {'plain': 'refused', 'delegated, other call': 'refused', 'delegated simulation': 'passed'}
    assert virtuoso_bridge.delegated_owner() is None


def test_two_simulations_logging_at_once_keep_their_logs_apart(tmp_path, capsys):
    together = threading.Barrier(2)

    def job(name):
        with (tmp_path / f'{name}.log').open('w') as log, virtuoso_bridge._captured(log):
            together.wait()
            for i in range(300):
                print(f'{name} {i}')
    threads = [threading.Thread(target=job, args=(name,)) for name in ('a', 'b')]
    for thread in threads:
        thread.start()
    print('from the owning thread')
    for thread in threads:
        thread.join()
    for name in ('a', 'b'):
        lines = (tmp_path / f'{name}.log').read_text().splitlines()
        assert len(lines) == 300 and all(line.startswith(f'{name} ') for line in lines)
    assert 'from the owning thread' in capsys.readouterr().out
