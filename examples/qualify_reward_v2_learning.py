"""REAL workbench acceptance B/C after qualified Stage A; never a simulator substitute."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
from time import perf_counter

from qualify_reward_v2_real import read, runtime, settings, sha, stage_report_path, verify, write
from gator_workbench.engine import RunEngine


class QualificationEngine(RunEngine):
    """Only orchestration boundaries differ; all measurements, learning and storage are production code."""
    def __init__(self, *args, qualification, stage, pause_boundary=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.qualification, self.stage, self.pause_boundary = qualification, stage, pause_boundary
        self.driver_sha256 = sha(__file__)

    def _dispatch(self, lane):
        verify(self.qualification)
        if sha(__file__) != self.driver_sha256:
            raise RuntimeError('Qualification driver changed during execution')
        super()._dispatch(lane)

    def _commit(self, lane, busy, result):
        super()._commit(lane, busy, result)
        step = result.get('step')
        if not result['ok'] or not step or step[3]:
            raise RuntimeError('Qualification stops after the first unresolved evaluation failure')
        if self.pause_boundary and self.counters['global_env_step'] == 4:
            from gator_workbench.runs import send_command
            if busy['op'] != 'step' or not step[2]:
                raise RuntimeError('Pause must occur exactly at the first episode boundary')
            send_command(self.layout.run_dir, 'pause')
        if self.stage == 'C' and busy['op'] == 'step':
            if not step[2]:
                raise RuntimeError('C permits only one step per lane')
            self.lane_state[lane.lane_id]['finished'] = True
            self._event('qualification_episode_ceiling', lane=lane.lane_id)


def restore_confirmation(output, directory, report):
    from analog_optimizer.backends.backend import SimulationRequest
    from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
    from analog_optimizer.envs.sizing import same_parameters, write_record
    manifest = verify(output)
    _, _, compiled, factory = runtime(output)
    assignment = {(p['device'], p['parameter']): p['value'] for p in manifest['candidates'][0]['parameters']}
    if report['uncertain_calls'] or report['started_calls'] >= report['maximum_calls']:
        raise RuntimeError('No authorized restoration-confirmation slot remains')
    with VirtuosoBridgeBackend(factory.config, factory.profile) as backend:
        if not same_parameters(backend.read_parameters(), assignment):
            raise RuntimeError('Restored schematic does not match frozen baseline sizes')
        artifact = backend.generate_netlist(directory / 'restored-export')
        report['restoration_confirmation'] = dict(state='launch_intent', confirmed_calls=None)
        report['started_calls'] += 1
        report['uncertain_calls'] += 1
        write_record(directory / 'report.json', report)
        result = backend.run_simulation(SimulationRequest(artifact, directory / 'restored-simulation',
            required_metrics=tuple(s.metric_id for s in compiled.specs if s.active and s.required),
            parameters=assignment, timeout_seconds=factory.timeout_seconds, condition=artifact.condition))
        confirmation = report['restoration_confirmation']
        confirmation.update(state='returned', job_id=result.job_id, status=result.status.value,
                            confirmed_calls=result.simulator_invocations, artifact_directory=str(result.artifact_directory))
        if result.simulator_invocations is not None:
            report['uncertain_calls'] -= 1
            report['completed_calls'] += result.simulator_invocations
        write_record(directory / 'report.json', report)
        if result.status.value != 'ok' or result.simulator_invocations != 1:
            raise RuntimeError('Restored baseline confirmation failed: ' + result.reason_code)
        first = read(read(stage_report_path(output, 'A'))['jobs'][0]['artifact_directory'] + '/result.json')
        checks = []
        for spec in compiled.specs:
            key = spec.metric_id
            a, b = first['metrics'][key], result.metrics[key]
            limit = manifest['tolerances']['relative'] * max(abs(a), abs(b), manifest['tolerances']['references'][key])
            passed = a == b if key in manifest['tolerances']['discrete_metrics'] else abs(a-b) <= limit
            checks.append(dict(metric=key, limit=limit, difference=abs(a-b), passed=passed))
        confirmation.update(checks=checks, state='passed' if all(c['passed'] for c in checks) else 'failed')
        if confirmation['state'] != 'passed':
            raise RuntimeError('Restored measurement differs from frozen baseline tolerance')


def replay_checks(run_dir, directory, config):
    import torch
    from analog_optimizer.graph.pyg_converter import FeatureSchema, OPERATING_POINT_COLUMNS, OPERATING_POINT_REFERENCES
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.training.sac import SACLearner
    from gator_workbench import modes
    from gator_workbench.trajectory import TrajectoryLoader
    from gator_workbench.compile import compile_task
    from gator_workbench.tasks import load_task
    transitions = TrajectoryLoader(run_dir).transitions()
    if len(transitions) != 8:
        raise RuntimeError('B must retain eight actual eligible transitions')
    compiled = compile_task(config, load_task(config.circuit, allow_real=True, profile_id='lab').base_graph)
    results = []
    for encoder in ('graph_transformer', 'rgcn', 'gatv2'):
        for op in (False, True):
            torch.manual_seed(260926)
            schema = (FeatureSchema(op_columns=OPERATING_POINT_COLUMNS, op_references=OPERATING_POINT_REFERENCES)
                      if op else FeatureSchema())
            first = transitions[0].observation
            arguments = dict(experiment=dict(origin='real', split='recorded-B-replay', designs=[str(run_dir)]),
                feature_schema=schema, spec_schema=compiled.spec_schema,
                model_config=replace(modes.model_config_from(config.run.network), encoder_type=encoder, attention_mode=None),
                reward_settings=first.reward_settings, condition_policy=first.condition_policy,
                planned_conditions=first.planned_conditions)
            learner = SACLearner(**arguments)
            replay = ReplayBuffer(origin='real', seed=26)
            for transition in transitions:
                replay.add(transition)
            learner.act([first])
            checkpoint = directory / f'{encoder}-op-{op}.pt'
            learner.save(checkpoint, replay)
            expected = learner.update(replay.sample(2))
            restored, restored_replay, _ = SACLearner.load(checkpoint, **arguments)
            actual = restored.update(restored_replay.sample(2))
            equal = expected == actual and all(torch.equal(value, restored_module.state_dict()[key])
                for module, restored_module in ((learner.actor, restored.actor), (learner.critics, restored.critics),
                                                (learner.targets, restored.targets))
                for key, value in module.state_dict().items()) and torch.equal(learner.log_alpha, restored.log_alpha)
            results.append(dict(encoder=encoder, operating_points=op, passed=equal, update=actual,
                checkpoint_sha256=sha(checkpoint), fresh_spectre_calls=0, source='recorded Stage B real transitions'))
            write(directory / 'replay-checks.json', results)
            if not equal:
                raise RuntimeError('Exact next-update replay check failed')
    return results


def capture_engine(report, current):
    report.update(run_directory=str(current.layout.run_dir), started_calls=current.ledger.launches,
        uncertain_calls=current.ledger.uncertain_launches,
        completed_calls=current.ledger.launches-current.ledger.uncertain_launches,
        candidates=current.ledger.charged, resets=current.counters['episodes'],
        transitions=current.replay.insertions, updates=current.learner.updates, ledger=current.ledger.snapshot())
    report['segments'].append(dict(state=current.manifest['state'], stop_reason=current.stop_reason,
        error=current.error, preparation=current.preparation_report, calls=current.ledger.launches,
        updates=current.learner.updates, candidates=current.ledger.charged))


def finish_stage(output, directory, report, engine, stage, config):
    from gator_workbench.storage.dataset import DatasetReader
    from gator_workbench.trajectory import TrajectoryLoader
    calls, candidates, transitions = (42, 10, 8) if stage == 'B' else (7, 3, 1)
    if (engine.ledger.launches != calls or engine.ledger.charged != candidates or
            engine.replay.insertions != transitions or engine.ledger.uncertain_launches or engine.ledger.retries):
        raise RuntimeError('Real launch/candidate/replay accounting differs from the frozen protocol')
    dataset = DatasetReader(engine.layout.data)
    counts = {name: len(dataset.rows(name)) for name in ('evaluations', 'simulator_jobs', 'transitions', 'states', 'learner_updates')}
    report['table_rows'] = counts
    if counts['simulator_jobs'] != calls or counts['evaluations'] != candidates or counts['transitions'] != transitions:
        raise RuntimeError('Persisted job/evaluation/transition table count mismatch')
    recovered = TrajectoryLoader(engine.layout.run_dir).transitions()
    if len(recovered) != transitions or any(len(t.next_observation.condition_results) != 5 for t in recovered):
        raise RuntimeError('Persisted real trajectories lost a condition')
    if stage == 'C':
        if engine.ledger.reserve(launches=5) is not None:
            raise RuntimeError('Persisted global ledger admitted an unfunded step')
        report['unfunded_five_job_step_refused'] = True
    restore_confirmation(output, directory, report)
    if stage == 'B':
        report['recorded_real_replay_checks'] = replay_checks(engine.layout.run_dir, directory, config)
    report['passed'] = True


def resume_b(output):
    """Continue the actually saved episode boundary after the no-call lock handoff error."""
    from analog_optimizer.envs.sizing import write_record
    from gator_workbench.connection import ConnectionMonitor
    from gator_workbench.runs import connection_gate
    from gator_workbench.schema import WorkbenchConfig
    from gator_workbench.security import redact
    from gator_workbench.tasks import load_task
    import torch
    torch.set_num_threads(1)
    parent = verify(output)
    directory = output / 'stage-b'
    report = read(directory / 'report.json')
    if (report['completed_calls'] != 21 or report['uncertain_calls'] or report['transitions'] != 4 or
            report['segments'][-1]['state'] != 'paused' or
            not report.get('failure', {}).get('diagnostic', '').startswith('Another worker already owns this run:')):
        raise RuntimeError('This continuation only accepts the recorded no-call lock-handoff failure')
    frozen = directory / 'resume-control-manifest.json'
    if frozen.exists():
        raise RuntimeError('Continuation was already attempted; no automatic retry')
    write(directory / 'report-before-resume.json', report)
    config = WorkbenchConfig.model_validate(read(directory / 'configuration.json'))
    task = load_task(config.circuit, allow_real=True, profile_id='lab')
    manifest = read(Path(report['run_directory']) / 'run_manifest.json')
    if manifest['state'] != 'created' or manifest['segments'][-1]['entry'] != 'resume':
        raise RuntimeError('Resume was not prepared by the production run gate')
    write(frozen, dict(origin='real', parent_manifest_sha256=sha(output / 'manifest.json'),
        source_digest=parent['source_digest'], driver_sha256=sha(__file__),
        original_driver_sha256=sha(directory / 'driver-at-start.py'),
        paused_report_sha256=sha(directory / 'report-before-resume.json'),
        already_confirmed_in_this_run=21, remaining_training_calls=21, remaining_restoration_calls=1,
        new_physical_retry=False, purpose='continue the prepared same-run resume after fixing lock handoff'))
    connection_gate(task, config, ConnectionMonitor(), acknowledge_unknown=True)
    report['resolved_runner_failures'] = [report.pop('failure')]
    report['resume_control_manifest_sha256'] = sha(frozen)
    start, elapsed = perf_counter(), report['wall_seconds']
    try:
        engine = QualificationEngine(report['run_directory'], task=task, qualification=output, stage='B')
        state = engine.run()
        capture_engine(report, engine)
        if state != 'completed' or engine.error:
            raise RuntimeError('Real resume failed: ' + str(engine.error or state))
        finish_stage(output, directory, report, engine, 'B', config)
    except BaseException as exc:
        report['failure'] = dict(type=type(exc).__name__, diagnostic=redact(str(exc), 1500))
        raise
    finally:
        report['wall_seconds'] = elapsed + perf_counter()-start
        write_record(directory / 'report.json', report)


def replay_b(output):
    """Reprocess only B's saved real transitions after repairing the encoder selector in this driver."""
    from gator_workbench.schema import WorkbenchConfig
    import torch
    torch.set_num_threads(1)
    verify(output)
    directory = output / 'stage-b'
    report = read(directory / 'report.json')
    if (report['completed_calls'] != 43 or report['uncertain_calls'] or report['transitions'] != 8 or
            report['restoration_confirmation']['state'] != 'passed' or
            report.get('failure', {}).get('diagnostic') != 'encoder_type conflicts with legacy attention_mode'):
        raise RuntimeError('Replay-only repair requires the completed physical B evidence')
    write(directory / 'report-before-replay-repair.json', report)
    target = directory / 'replay-final'
    target.mkdir(exist_ok=False)
    write(target / 'manifest.json', dict(origin='real', fresh_spectre_calls=0, driver_sha256=sha(__file__),
        parent_report_sha256=sha(directory / 'report-before-replay-repair.json'),
        reason='Clear the legacy attention alias when selecting another encoder in the check driver'))
    config = WorkbenchConfig.model_validate(read(directory / 'configuration.json'))
    start = perf_counter()
    report['recorded_real_replay_checks'] = replay_checks(report['run_directory'], target, config)
    report['resolved_runner_failures'].append(report.pop('failure'))
    report['passed'] = True
    report['wall_seconds'] += perf_counter()-start
    write(directory / 'report.json', report)


def run(output, stage):
    from analog_optimizer.envs.sizing import write_record
    from gator_workbench.budget import BudgetLedger
    from gator_workbench.connection import ConnectionMonitor
    from gator_workbench.paths import OutputRoots
    from gator_workbench.runs import prepare_run, take_lock, with_circuit_content
    from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash
    from gator_workbench.security import redact
    from gator_workbench.storage.dataset import DatasetReader
    from gator_workbench.tasks import load_task
    from gator_workbench.trajectory import TrajectoryLoader
    import torch
    torch.set_num_threads(1)
    parent = verify(output)
    previous = stage_report_path(output, 'A' if stage == 'B' else 'B')
    if not read(previous)['passed']:
        raise RuntimeError('Previous real stage did not pass')
    directory = output / ('stage-' + stage.lower())
    directory.mkdir(exist_ok=True)
    if (directory / 'manifest.json').exists():
        raise RuntimeError('Stage already frozen/attempted; no automatic rerun')
    raw = read(output / 'configuration.json')
    raw['output'].update(output_root=str(directory / 'workbench'), experiment_name='reward-v2-acceptance-' + stage,
                         waveform_retention='all', flush_every_evaluations=1)
    raw['run'].update(max_consecutive_failures=1, max_consecutive_infrastructure_failures=1)
    if stage == 'C':
        raw['run'].update(max_evaluations=4, concurrency=2, max_spectre_launches=11)
        raw['run']['advanced']['episode_length'] = 1
    config = WorkbenchConfig.model_validate(raw)
    task = load_task(config.circuit, allow_real=True, profile_id='lab')
    config = with_circuit_content(config, task)
    maximum, expected = (43, 43) if stage == 'B' else (13, 8)
    prior_calls = parent.get('continuation', {}).get('prior_confirmed_calls', 0)
    if stage == 'C':
        prior_calls += read(previous)['completed_calls']
        maximum = min(maximum, 77-prior_calls)
    elif prior_calls:
        maximum = min(maximum, parent['stages']['B']['maximum_launches'] - parent['continuation']['prior_B_calls'])
    if maximum < expected or prior_calls + expected > 77:
        raise RuntimeError('The remaining global/stage ceiling cannot fund the frozen protocol')
    write(directory / 'configuration.json', config.model_dump(mode='json'))
    frozen = dict(origin='real', stage=stage, parent_manifest_sha256=sha(output / 'manifest.json'),
        previous_stage_report_sha256=sha(previous), source_digest=parent['source_digest'],
        driver_sha256=sha(__file__), configuration_sha256=sha(directory / 'configuration.json'),
        config_hash=config_hash(config), task_definition_hash=task_definition_hash(config),
        maximum_launches=maximum, expected_launches=expected, training_cap=config.run.max_spectre_launches,
        prior_confirmed_calls=prior_calls, global_ceiling=77,
        restoration_cap=1, retries=0, dependencies=parent['dependencies'],
        boundary='pause after step 4 then resume same run' if stage == 'B' else 'one episode per lane; refuse an unfunded five-job step')
    write(directory / 'manifest.json', frozen)
    report = dict(origin='real', stage=stage, manifest_sha256=sha(directory / 'manifest.json'),
        planned_calls=expected, maximum_calls=maximum, started_calls=0, completed_calls=0, uncertain_calls=0,
        candidates=0, resets=0, transitions=0, updates=0, passed=False, segments=[], restoration_confirmation='not_started')
    report['prior_confirmed_calls'] = prior_calls
    start, engine = perf_counter(), None
    if stage == 'C':
        ledger = BudgetLedger(4, max_launches=11)
        assert ledger.reserve(launches=1) and ledger.reserve(launches=1) and ledger.reserve(launches=5)
        assert ledger.reserve(launches=5) is None
        report['pure_pre_dispatch_admission'] = dict(passed=True, type='ledger arithmetic only', snapshot=ledger.snapshot())

    def save():
        report['wall_seconds'] = perf_counter() - start
        write_record(directory / 'report.json', report)

    def capture(current):
        capture_engine(report, current)
        save()

    save()
    try:
        roots = OutputRoots([directory], include_default=False)
        monitor = ConnectionMonitor()
        layout, _ = prepare_run(config, roots, allow_real=True, monitor=monitor, acknowledge_unknown=True)
        engine = QualificationEngine(layout.run_dir, task=task, qualification=output, stage=stage,
                                     pause_boundary=stage == 'B')
        state = engine.run()
        capture(engine)
        if state != ('paused' if stage == 'B' else 'completed') or engine.error:
            raise RuntimeError('Real workbench segment failed: ' + str(engine.error or state))
        if stage == 'B':
            if engine.ledger.launches != 21 or engine.ledger.charged != 5 or engine.replay.insertions != 4:
                raise RuntimeError('Unexpected first-episode costs at pause boundary')
            resumed = config.model_copy(deep=True)
            resumed.run.mode = 'resume'
            resumed.run.model_source.run_dir = str(layout.run_dir)
            resumed_layout, _ = prepare_run(resumed, roots, allow_real=True, monitor=monitor, acknowledge_unknown=True)
            if resumed_layout.run_dir != layout.run_dir:
                raise RuntimeError('Resume changed run identity')
            engine = QualificationEngine(layout.run_dir, task=task, qualification=output, stage=stage,
                                         lock=take_lock(layout.run_dir))
            state = engine.run()
            capture(engine)
            if state != 'completed' or engine.error:
                raise RuntimeError('Real resume failed: ' + str(engine.error or state))
        finish_stage(output, directory, report, engine, stage, config)
    except BaseException as exc:
        report['failure'] = dict(type=type(exc).__name__, diagnostic=redact(str(exc), 1500))
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['B', 'C', 'resume_B', 'replay_B'])
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    settings(args.output.resolve())
    if args.stage == 'resume_B':
        resume_b(args.output.resolve())
    elif args.stage == 'replay_B':
        replay_b(args.output.resolve())
    else:
        run(args.output.resolve(), args.stage)


if __name__ == '__main__':
    main()
