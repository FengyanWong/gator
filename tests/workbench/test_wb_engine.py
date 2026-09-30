"""Run engine: shared budgets under several workers, retry accounting, asynchronous first
feasibility / failure / null, pause-resume, forced cancellation and real crash recovery.
All evaluations use the MOCK analytic backend (optionally scripted to fail)."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from gator_workbench import runs, schema, tasks
from gator_workbench.engine import RunEngine, RunLock
from gator_workbench.storage import DatasetReader, read_json
from gator_workbench.storage.atomic import read_jsonl
from helpers import ScriptedEnvFactory, execute, make_config, roots_for, rows, run_prepared, summary

REPO = Path(__file__).resolve().parents[2]


def by_seq(layout, table='evaluations'):
    return sorted(rows(layout, table), key=lambda r: r['commit_seq'])


# ------------------------------------------------------------------------------- budget
def test_budget_is_shared_by_all_workers_and_never_exceeded(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=23, concurrency=3)), tmp_path)
    assert state == 'completed'
    evaluations = by_seq(layout)
    assert len(evaluations) == 23 and len({e['evaluation_id'] for e in evaluations}) == 23
    assert {e['worker_id'] for e in evaluations} == {'0', '1', '2'}
    assert sorted(e['dispatch_index'] for e in evaluations) == list(range(1, 24))
    assert [e['commit_seq'] for e in evaluations] == list(range(1, 24))
    assert [e['completion_index'] for e in evaluations] == list(range(1, 24))
    assert max(e['cumulative_evaluations_charged'] for e in evaluations) == 23
    s = summary(layout)
    assert s['totals']['candidate_evaluations_charged'] == 23 and s['stop_reason'] == 'budget_exhausted'
    assert s['budget']['remaining'] == 0 and s['totals']['released_reservations'] == 0
    # baselines, resets and warm-up all count; an episode reset does not reset the budget
    phases = [e['phase'] for e in evaluations]
    assert phases.count('baseline') == 1 and phases.count('episode_reset') >= 3 and 'warmup' in phases
    assert all(e['provenance'] == 'mock' for e in evaluations)


def test_every_table_is_written_with_raw_values_and_action_provenance(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=14)), tmp_path)
    reader = DatasetReader(layout.data)
    counts = reader.row_counts()
    assert counts['evaluations'] == 14 and counts['simulator_jobs'] == 14 and reader.verify() == []
    assert counts['parameters'] == 14 * 5                       # 3 independent variables, two with a bound member
    assert counts['learner_updates'] > 0 and counts['transitions'] > 0 and counts['states'] > 0
    parameters = reader.rows('parameters')
    step = next(p for p in parameters if p['raw_policy_action'] is not None and p['role'] == 'independent')
    assert -1 <= step['raw_policy_action'] <= 1
    assert step['lower'] <= step['executed_value'] <= step['upper'] and step['decoded_value'] is not None
    bound = next(p for p in parameters if p['role'] == 'bound_member' and p['evaluation_id'] == step['evaluation_id']
                 and p['variable_id'] == 'input_pair_width')
    leader = next(p for p in parameters if p['role'] == 'independent' and p['evaluation_id'] == step['evaluation_id']
                  and p['variable_id'] == 'input_pair_width')
    assert bound['executed_value'] == pytest.approx(leader['executed_value'] * bound['ratio'])
    reset = next(p for p in parameters if p['raw_policy_action'] is None)
    assert reset['decoded_value'] is None and reset['executed_value'] is not None        # baseline: no action
    metrics = reader.rows('metrics')
    raw = [m for m in metrics if m['aggregation_level'] == 'condition']
    aggregate = [m for m in metrics if m['aggregation_level'] == 'aggregate']
    assert len(raw) == len(aggregate) == 14                     # per-condition raw value AND the value used for reward
    assert all(m['raw_value'] is not None and m['unit'] == 'fixture' for m in raw)
    assert all(m['threshold_lower'] == pytest.approx(0.95) and m['hard'] for m in aggregate)
    updates = reader.rows('learner_updates')
    assert [u['cumulative_updates'] for u in updates] == list(range(1, len(updates) + 1))
    assert all(u['replay_size'] >= u['batch_size'] for u in updates)


def test_thinned_update_logging_keeps_cumulative_counts_exact(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=24), output=dict(learner_update_log_every=3)), tmp_path)
    updates = rows(layout, 'learner_updates')
    assert updates and all(u['cumulative_updates'] % 3 == 0 for u in updates)
    assert summary(layout)['totals']['gradient_updates'] >= updates[-1]['cumulative_updates']


# ------------------------------------------------------------------------------- retries / failures
def test_retry_keeps_the_evaluation_id_and_costs_a_launch_not_an_evaluation(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=6, max_retries=2))
    layout, state = execute(config, tmp_path, scripts={'0': {2: 'timeout', 3: 'timeout'}})
    assert state == 'completed'
    evaluations, jobs = by_seq(layout), rows(layout, 'simulator_jobs')
    assert len(evaluations) == 6                                   # retries are NOT new candidates
    retried = next(e for e in evaluations if e['attempts'] == 3)
    attempts = sorted((j for j in jobs if j['evaluation_id'] == retried['evaluation_id']), key=lambda j: j['attempt'])
    assert [j['attempt'] for j in attempts] == [1, 2, 3]
    assert [j['exit_status'] for j in attempts] == ['timeout', 'timeout', 'ok']
    assert [j['timed_out'] for j in attempts] == [True, True, False]
    assert attempts[0]['retry_reason'] is None and 'timeout' in attempts[1]['retry_reason']
    assert retried['valid'] and retried['status'] == 'ok'
    s = summary(layout)
    assert s['totals']['candidate_evaluations_charged'] == 6 and s['totals']['spectre_launches'] == 8
    assert s['totals']['retries'] == 2 and len(jobs) == 8


def test_without_retries_a_failure_is_charged_recorded_and_never_feasible(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=8, max_retries=0))
    layout, _ = execute(config, tmp_path, scripts={'0': {2: 'timeout', 4: 'nan', 5: 'invalid_design'}})
    evaluations = by_seq(layout)
    assert len(evaluations) == 8
    failed = [e for e in evaluations if not e['valid']]
    # timeout = infrastructure failure; 'nan' = the simulator ran but the measurement is unusable;
    # invalid_design = the backend attributed the failure to the candidate
    assert sorted(e['status'] for e in failed) == ['invalid_design', 'ok', 'timeout']
    assert next(e for e in failed if e['status'] == 'ok')['failure_type'] == 'invalid_measurement'
    assert all(not e['all_hard_constraints_satisfied'] and e['normalized_constraint_violation'] is None for e in failed)
    assert all(e['failure_type'] for e in failed) and len(failed) == 3
    timeout = next(e for e in failed if e['status'] == 'timeout')
    assert timeout['reward'] is None and timeout['truncated'] and not timeout['replay_eligible']
    bad_metrics = [m for m in rows(layout, 'metrics') if not m['valid']]
    assert bad_metrics and all(m['raw_value'] is None and m['failure_reason'] for m in bad_metrics)
    s = summary(layout)
    assert s['totals']['failures'] == 3 and s['totals']['candidate_evaluations_charged'] == 8   # no refund


def test_launch_limit_is_a_hard_cap(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=50, max_spectre_launches=7))
    layout, _ = execute(config, tmp_path)
    s = summary(layout)
    assert s['totals']['spectre_launches'] == 7 and s['totals']['candidate_evaluations_charged'] == 7


def test_consecutive_failures_stop_safely_with_data_saved(tmp_path):
    # 'nan' = the simulator ran but every measurement is unusable: a failure, yet NOT an infrastructure failure
    config = make_config(tmp_path, run=dict(max_evaluations=40, max_consecutive_failures=3))
    layout, state = execute(config, tmp_path, scripts={'0': {n: 'nan' for n in range(2, 40)}})
    assert state == 'failed' and summary(layout)['stop_reason'] == 'consecutive_failures'
    assert len(by_seq(layout)) == 4 and (layout.checkpoints / 'latest.json').exists()


def test_backend_exception_is_recorded_and_stops_the_run(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=10)), tmp_path, scripts={'0': {3: 'exception'}})
    assert state == 'failed'
    last = by_seq(layout)[-1]
    assert last['status'] == 'execution_error' and 'scripted backend exception' in last['diagnostics']
    assert summary(layout)['totals']['candidate_evaluations_charged'] == 3
    assert any(e['error'] == 'evaluation_exception' for e in read_jsonl(layout.logs / 'errors.jsonl'))


# ------------------------------------------------------------------------------- first feasibility
def test_asynchronous_first_feasibility_counts_in_flight_work(tmp_path):
    # lane 0 is slow, so results arrive out of dispatch order
    config = make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=30, concurrency=3, seed=5))
    layout, _ = execute(config, tmp_path, delays={'0': 0.25, '1': 0.0, '2': 0.0})
    evaluations = by_seq(layout)
    assert any(e['dispatch_index'] != e['completion_index'] for e in evaluations)        # genuinely asynchronous
    first = summary(layout)['first_feasible']
    event = next(e for e in evaluations if e['all_hard_constraints_satisfied'])
    assert first['evaluation_id'] == event['evaluation_id'] and first['commit_seq'] == event['commit_seq']
    # decided when the scheduler RECEIVED the result, never from the size of an id or the dispatch order
    assert first['first_feasible_eval_count'] == event['cumulative_evaluations_charged']
    assert first['first_feasible_eval_count'] == first['completed_count'] + first['in_flight_count']
    assert first['dispatch_index'] == event['dispatch_index']
    assert not event['after_first_feasible']
    later = [e for e in evaluations if e['commit_seq'] > event['commit_seq']]
    assert later and all(e['after_first_feasible'] for e in later)
    marked = {e['evaluation_id'] for e in evaluations if e['in_flight_at_first_feasible']}
    assert marked == set(first['in_flight_evaluation_ids']) and event['evaluation_id'] not in marked
    s = summary(layout)                                     # first-feasibility cost is NOT the final cost
    assert s['first_feasible_eval_count'] < s['target_task_cost']['evaluations_charged'] == 30


def test_stop_at_first_feasible_still_records_in_flight_results(tmp_path):
    config = make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=60, concurrency=3, seed=5,
                                                           stop_at_first_feasible=True))
    layout, state = execute(config, tmp_path, delays={'0': 0.2})
    s = summary(layout)
    assert state == 'completed' and s['stop_reason'] == 'first_feasible'
    first = s['first_feasible']
    assert s['totals']['candidate_evaluations_charged'] == first['first_feasible_eval_count']   # nothing new dispatched
    assert s['totals']['candidate_evaluations_completed'] == first['first_feasible_eval_count']  # in-flight were kept
    assert len(by_seq(layout)) == first['completed_count'] + first['in_flight_count']


def test_no_feasible_design_gives_null_and_right_censoring_not_the_budget(tmp_path):
    layout, state = execute(make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=12)), tmp_path)
    s = summary(layout)
    assert state == 'completed' and s['first_feasible'] is None and s['first_feasible_eval_count'] is None
    assert s['censoring'] == dict(s['censoring'], status='right_censored', first_feasible_eval_count=None, observation_limit=12)
    best = read_json(layout.best_design / 'best_feasible.json')
    assert best['status'] == 'none_found' and best['design'] is None                # explicit null, no fiction
    assert not (layout.best_design / 'parameters.csv').exists()
    assert not (layout.best_design / 'optimized_dut.scs').exists()
    infeasible = read_json(layout.best_design / 'best_infeasible.json')
    assert infeasible['status'] == 'found' and infeasible['design']['feasible'] is False
    assert read_json(layout.checkpoints / 'best_policy.json')['selected'] is None   # never invented


# ------------------------------------------------------------------------------- best design
def test_best_design_records_variables_bindings_and_metrics(tmp_path):
    layout, _ = execute(make_config(tmp_path, threshold=0.9, run=dict(max_evaluations=25)), tmp_path)
    best = read_json(layout.best_design / 'best_feasible.json')
    design = best['design']
    assert best['status'] == 'found' and design['feasible'] and design['provenance'] == 'mock'
    assert {v['variable_id'] for v in design['independent_variables']} == {'input_pair_width', 'mirror_pair_width', 'tail_width'}
    assert len(design['expanded_bindings']) == 5 and design['test_conditions'] == ['nominal']
    assert 'no PVT' in design['validation_status'] and design['metrics']['score'] >= 0.9
    evaluation = next(e for e in by_seq(layout) if e['evaluation_id'] == design['evaluation_id'])
    assert evaluation['all_hard_constraints_satisfied']
    lines = (layout.best_design / 'parameters.csv').read_text().strip().splitlines()
    assert lines[0].startswith('variable_id,member_variable_id,role,instance_path') and len(lines) == 6
    # The OTA5's transistors sit inside its subcircuit XU1: a netlist with the best widths would edit the shared
    # definition, so none is written - as for the real OTA5 - and the artifact manifest says why.
    assert not (layout.best_design / 'optimized_dut.scs').exists()
    notes = read_json(layout.run_dir / 'artifact_manifest.json')['notes']
    assert any(n.startswith('best_design/optimized_dut.scs: not created: XU1/M1 is inside a subcircuit') for n in notes), notes
    assert 'w=(4u)' in (layout.input_snapshot / 'netlist.scs').read_text()      # the source netlist is never modified


def test_a_best_design_netlist_is_rewritten_and_proved_by_reparsing():
    """best_design.export_netlist on the real OTA5 netlist: a top-level value (the load CL) is rewritten and verified by
    re-parsing; a value inside the subcircuit is refused."""
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    from gator_workbench import tasks
    from gator_workbench.best_design import export_netlist
    netlist, mapping = REPO / 'examples/circuits/gpdk045_ota5.scs', REPO / 'configs/gpdk045_opamp.json'
    graph, text = tasks.parse_netlist(netlist, mapping), netlist.read_text()
    reparse = lambda rewritten: SpectreParser(ParserConfig.from_file(mapping)).parse_text(rewritten)
    outcome = export_netlist(text, graph, [dict(instance_path='CL', parameter_name='c', value=2.5e-12)], reparse=reparse)
    assert outcome['status'] == 'verified', outcome.get('reason')
    line = next(l for l in outcome['text'].split('\n') if l.startswith('CL '))
    assert 'c=2.5e-12' in line and 'CL (VOUT 0) capacitor c=1p' in text
    assert reparse(outcome['text']).parameters['CL']['c'].value == pytest.approx(2.5e-12)
    refused = export_netlist(text, graph, [dict(instance_path='XU1/M1', parameter_name='w', value=5e-6)], reparse=reparse)
    assert refused['status'] == 'unsupported' and 'inside a subcircuit' in refused['reason']


def test_input_snapshot_has_no_fake_dut_or_testbench_files(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=4)), tmp_path)
    names = {p.name for p in layout.input_snapshot.iterdir()}
    assert names == {'circuit.json', 'netlist.scs', 'hierarchy.json', 'parameter_mapping.json', 'pdk_reference.json'}
    manifest = read_json(layout.manifest)
    assert any('no empty placeholders' in note for note in manifest['notes'])
    assert 'never copied' in read_json(layout.input_snapshot / 'pdk_reference.json')['note']


# ------------------------------------------------------------------------------- pause / resume / cancel
def request_after(layout, command, evaluations, timeout=60, *, in_flight=False):
    """Send `command` once the run shows `evaluations` completed - and, with `in_flight`, a simulation running right then
    (without that, a busy machine could send a forced cancel between two evaluations, with nothing left to cancel)."""
    import threading

    def watch():
        deadline = time.time() + timeout
        while time.time() < deadline:
            budget = (read_json(layout.status, default={}) or {}).get('budget') or {}
            if (budget.get('completed') or 0) >= evaluations and (not in_flight or (budget.get('in_flight') or 0) > 0):
                runs.send_command(layout.run_dir, command)
                return
            time.sleep(0.01)
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread


def test_pause_saves_consistently_and_resume_continues_the_same_run(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    request_after(layout, 'pause', 8)
    assert run_prepared(layout, delays={'0': 0.03, '1': 0.03}) == 'paused'
    paused = summary(layout)
    done = paused['totals']['candidate_evaluations_charged']
    assert 8 <= done < 40 and paused['stop_reason'] == 'user_pause'
    assert paused['totals']['candidate_evaluations_completed'] == done        # in-flight jobs were recorded first
    assert paused['censoring']['status'] == 'right_censored' and paused['censoring']['observation_limit'] == done
    meta = read_json(layout.checkpoints / read_json(layout.checkpoints / 'latest.json')['checkpoint_id'] / 'metadata.json')
    assert meta['kind'] == 'pause' and meta['restoration_capability'] == 'full_state'
    assert meta['ledger']['charged'] == meta['data_cursor']['commit_seq'] == done   # one consistency boundary
    assert meta['counters']['replay_insertions'] == meta['replay']['insertions']
    updates_before = meta['counters']['learner_updates']

    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    again, manifest = runs.prepare_run(resumed, roots_for(tmp_path))
    assert again.run_dir == layout.run_dir                                    # writes back to the ORIGINAL directory
    assert [s['entry'] for s in manifest['segments']] == ['start', 'resume']
    assert run_prepared(again) == 'completed'
    final = summary(layout)
    assert final['totals']['candidate_evaluations_charged'] == 40            # counters were retained, not reset
    evaluations = by_seq(layout)
    assert [e['commit_seq'] for e in evaluations] == list(range(1, 41))
    assert len({e['evaluation_id'] for e in evaluations}) == 40
    assert final['totals']['gradient_updates'] > updates_before and final['segments'] == 2
    assert final['time']['paused_seconds'] >= 0 and final['mode'] == 'scratch'
    assert [e['phase'] for e in evaluations].count('baseline') == 1          # no second "first" baseline


def test_resume_refuses_a_changed_task_and_a_running_run(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=6))
    layout, _ = execute(config, tmp_path)
    changed = make_config(tmp_path, threshold=1.2, run=dict(max_evaluations=12, mode='resume'))
    changed.run.model_source.run_dir = str(layout.run_dir)
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(changed, roots_for(tmp_path))
    assert error.value.code == 'task_changed' and error.value.report['mode'] == 'fine_tune'   # suggestion, not a fallback
    same = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=3, mode='resume'))
    same.run.model_source.run_dir = str(layout.run_dir)
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(same, roots_for(tmp_path))
    assert error.value.code == 'budget'                                       # below what was already consumed
    lock = RunLock(layout.control / 'run.lock'); lock.acquire()
    try:
        same.run.max_evaluations = 12
        with pytest.raises(runs.RunRejected) as error:
            runs.prepare_run(same, roots_for(tmp_path))
        assert error.value.code == 'already_running'                          # reconnecting never duplicates a run
        with pytest.raises(runs.RunRejected):
            runs.launch_worker(layout)
    finally:
        lock.release()


@dataclass
class CancelHeldFactory(ScriptedEnvFactory):
    """Lane 1's first step (its second simulation, after its reset) does not end on its own: it waits until the engine
    has read the cancel (the run's stop/condition file exists) AND has recorded an evaluation as cancelled (a cancelled
    condition receipt in events.jsonl). The stop file alone would not do: the engine writes it before it looks at the
    jobs, so a job released by it could still end first. No delay decides anything (review round 5, E2: with timed
    jobs, 2 of 56 parallel copies had both jobs end before the cancel was read - status.json is written at most once a
    second)."""
    stop_file: str = ''
    events: str = ''
    deadline: float = 60.0                     # only if the engine never records the cancel; the test then fails

    def __call__(self, lane):
        env = super().__call__(lane)
        if str(lane) == '1':
            simulate, calls = env.backend.run_simulation, []

            def held(request):
                calls.append(request)
                if len(calls) == 2:
                    end = time.time() + self.deadline
                    while time.time() < end and not (Path(self.stop_file).exists() and any(
                            e.get('event') == 'condition_receipt' and e.get('status') == 'cancelled'
                            for e in read_jsonl(self.events))):
                        time.sleep(0.01)
                return simulate(request)
            env.backend.run_simulation = held
        return env


def test_forced_cancel_records_unfinished_evaluations_as_charged(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    request_after(layout, 'cancel', 4, in_flight=True)
    # lane 1's first step is still running when the cancel is read, whatever the machine's load (CancelHeldFactory)
    effective = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    engine = RunEngine(layout.run_dir, task=tasks.load_task(effective.circuit), use_processes=False,
                       lock=runs.take_lock(layout.run_dir))
    engine._lane_factory = CancelHeldFactory(engine.compiled.graph, engine.compiled.specs, str(layout.work),
                                             effective.run.advanced.episode_length, {}, {},
                                             effective.run.advanced.episode_terminates_on_success,
                                             stop_file=str(layout.control / 'stop-condition-jobs.json'),
                                             events=str(layout.logs / 'events.jsonl'))
    assert engine.run() == 'cancelled'
    s = summary(layout)
    evaluations = by_seq(layout)
    assert s['termination']['forced'] and not s['termination']['normal_completion']
    assert len(evaluations) == s['totals']['candidate_evaluations_charged']    # started => charged => recorded
    cancelled = [e for e in evaluations if e['status'] == 'cancelled']
    assert cancelled and all(not e['valid'] and 'unknown' in e['diagnostics'] for e in cancelled)
    assert s['censoring']['status'] == 'right_censored' and s['output']['completeness'] == 'partial'


def test_a_reservation_cancelled_before_start_is_refunded(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=30))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    request_after(layout, 'stop', 5)
    assert run_prepared(layout, delays={'0': 0.05}) == 'stopped'
    s = summary(layout)
    assert s['totals']['candidate_evaluations_charged'] == len(by_seq(layout))
    assert s['totals']['candidate_evaluations_charged'] + s['budget']['remaining'] == 30


# ------------------------------------------------------------------------------- real crash recovery
CRASH_SCRIPT = '''
import sys
sys.path[:0] = [{src!r}, {tests!r}]
import torch; torch.set_num_threads(1)
from gator_workbench.layout import RunLayout
from helpers import run_prepared
run_prepared(RunLayout({run_dir!r}), delays={{'0': 0.08}})
'''


def test_sigkill_recovery_loses_nothing_acknowledged_and_double_counts_nothing(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=30),
                         output=dict(checkpoint_every_evaluations=4, flush_every_evaluations=3))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    script = CRASH_SCRIPT.format(src=str(REPO / 'src'), tests=str(Path(__file__).parent), run_dir=str(layout.run_dir))
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            committed = ((read_json(layout.status, default={}) or {}).get('persistence') or {}).get('last_commit_seq', 0)
            if committed >= 10:
                break
            assert process.poll() is None, 'worker ended before it could be killed'
            time.sleep(0.02)
        process.send_signal(signal.SIGKILL)                       # no finally, no flush, no checkpoint
    finally:
        process.wait(timeout=30)
    assert runs.run_status(layout.run_dir)['state'] == 'interrupted'
    acknowledged = [b['evaluation_id'] for b in read_jsonl(layout.data / '_journal' / 'wal.jsonl')]
    started = [d['evaluation_id'] for d in read_jsonl(layout.data / '_journal' / 'dispatch.jsonl')]
    flushed_before = {i for f in read_jsonl(layout.data / '_journal' / 'flushes.jsonl') for i in f['evaluation_ids']}
    assert len(started) >= 10

    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))
    assert run_prepared(again) == 'completed'
    evaluations = by_seq(layout)
    ids = [e['evaluation_id'] for e in evaluations]
    assert len(ids) == len(set(ids))                               # nothing double-counted
    assert set(acknowledged) | flushed_before <= set(ids)          # nothing acknowledged was lost
    assert set(started) <= set(ids)                                # everything that STARTED stays charged
    assert [e['commit_seq'] for e in evaluations] == list(range(1, len(ids) + 1))
    s = summary(layout)
    assert s['totals']['candidate_evaluations_charged'] == 30 == len(ids)     # the budget was not granted twice
    interrupted = [e for e in evaluations if e['status'] == 'interrupted']
    assert len(interrupted) == s['totals']['interrupted_evaluations'] <= 1
    assert all(not e['valid'] and e['failure_type'] == 'interrupted_by_crash' for e in interrupted)
    resume_event = next(e for e in read_jsonl(layout.logs / 'events.jsonl') if e['event'] == 'resumed')
    assert resume_event['checkpoint_commit_seq'] <= len(acknowledged) + len(flushed_before)
    assert DatasetReader(layout.data).verify() == []


def test_the_detached_worker_process_runs_independently(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=6))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    env = dict(os.environ, PYTHONPATH=str(REPO / 'src'))
    done = subprocess.run([sys.executable, '-m', 'gator_workbench.worker', '--run-dir', str(layout.run_dir)],
                          capture_output=True, text=True, timeout=180, env=env, cwd=str(tmp_path))
    assert done.returncode == 0, done.stderr[-2000:]
    assert runs.run_status(layout.run_dir)['state'] == 'completed' and summary(layout)['totals']['candidate_evaluations_charged'] == 6


# ------------------------------------------------------------------------------- persistence failure
def test_core_persistence_failure_stops_simulating_instead_of_losing_data(tmp_path, monkeypatch):
    """A failing disk must stop dispatch. Continuing to simulate while results are dropped is the one
    thing that may never happen."""
    import pyarrow.parquet as pq
    real_write, calls = pq.write_table, []

    def failing_after_first_flush(table, where, *args, **kwargs):
        calls.append(str(where))
        if len({c.split('part-')[1][:6] for c in calls if 'part-' in c}) > 1:      # second flush onwards
            raise OSError(28, 'No space left on device')
        return real_write(table, where, *args, **kwargs)
    monkeypatch.setattr(pq, 'write_table', failing_after_first_flush)
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=60), output=dict(flush_every_evaluations=4))
    layout, state = execute(config, tmp_path)
    monkeypatch.setattr(pq, 'write_table', real_write)
    status = read_json(layout.status)
    assert state == 'failed' and status['stop_reason'] == 'persistence_failure' and 'No space left' in status['error']
    charged = status['budget']['charged']
    assert charged < 20, 'the run kept simulating after persistence failed'          # 60 were allowed
    assert 'No space left' in status['persistence']['failed']
    errors = read_jsonl(layout.logs / 'errors.jsonl')
    assert any(e['error'] == 'persistence_failure' for e in errors)
    # everything acknowledged before the failure is still there and recoverable
    acknowledged = [b['evaluation_id'] for b in read_jsonl(layout.data / '_journal' / 'wal.jsonl')]
    flushed = {i for f in read_jsonl(layout.data / '_journal' / 'flushes.jsonl') for i in f['evaluation_ids']}
    assert len(set(acknowledged) | flushed) >= 4
    from gator_workbench.storage import RawDataset
    recovered = RawDataset(layout.data)                                               # a later restart re-buffers them
    assert all(recovered.has(key) for key in set(acknowledged) | flushed)
    recovered.close()
    assert sorted(set(r['evaluation_id'] for r in rows(layout, 'evaluations'))) == sorted(set(acknowledged) | flushed)


# ------------------------------------------------------------------------------- a Single baseline simulation records itself (7.78)
def test_a_single_baseline_run_asks_the_task_flow_to_record_it_when_it_ends(tmp_path, monkeypatch):
    """The header's "Single baseline simulation" is a run of kind baseline_preflight (api `_start`). When it ends, the
    worker hands it to profiles.adopt_baseline_run, and what that says goes into the manifest's notes; a MOCK run gets no
    note (there is nothing to record), an optimization run is never handed over."""
    from gator_workbench import profiles
    from gator_workbench.storage.atomic import write_json
    handed = []

    def fake_adopt(run_dir, manifest=None):
        handed.append((Path(run_dir), manifest['state'], manifest['run_kind']))
        return dict(recorded=True, name='ring', note='FIXTURE: recorded as the reference of real:ring')
    monkeypatch.setattr(profiles, 'adopt_baseline_run', fake_adopt)
    # an optimization run: not handed over
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=3)), tmp_path)
    assert state == 'completed' and handed == [] and 'FIXTURE' not in json.dumps(read_json(layout.manifest)['notes'])
    # a baseline run: handed over once the manifest says how it ended, and the answer is in its notes and its artifact manifest
    roots = roots_for(tmp_path)
    layout, manifest = runs.prepare_run(make_config(tmp_path, run=dict(max_evaluations=1)), roots)
    manifest['run_kind'] = 'baseline_preflight'
    write_json(layout.manifest, manifest)
    assert run_prepared(layout) == 'completed'
    assert handed == [(layout.run_dir, 'completed', 'baseline_preflight')]
    final = read_json(layout.manifest)
    assert final['notes'][-1] == 'FIXTURE: recorded as the reference of real:ring'
    assert 'FIXTURE: recorded as the reference of real:ring' in read_json(layout.run_dir / 'artifact_manifest.json')['notes']
    events = read_jsonl(layout.logs / 'events.jsonl')
    assert [e for e in events if e['event'] == 'baseline_reference'][0]['recorded'] is True
    # the real helper on a MOCK baseline run: nothing to record, nothing said, the run ends as it would have
    monkeypatch.undo()
    layout, manifest = runs.prepare_run(make_config(tmp_path, run=dict(max_evaluations=1)), roots)
    manifest['run_kind'] = 'baseline_preflight'
    write_json(layout.manifest, manifest)
    assert run_prepared(layout) == 'completed' and 'reference' not in json.dumps(read_json(layout.manifest)['notes'])
