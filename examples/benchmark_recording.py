"""6000+ injected MockBackend evaluations, real recorder/replay/checkpoint I/O; no Spectre."""
from dataclasses import asdict, replace
import argparse
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from analog_optimizer.backends.backend import SimulationStatus
from analog_optimizer.backends.mock import MockBackend
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser
from analog_optimizer.recording import ExperimentStore, RecordingConfig, RunRecorder
from analog_optimizer.recording.checkpoint import CheckpointManager
from analog_optimizer.recording.setup import create_run
from analog_optimizer.recording.reader import RunReader


class InjectedSizingMock(MockBackend):
    """Mock metric/status injection plus toy parameter readback; no physics model."""
    def __init__(self, graph):
        super().__init__('simulator lang=spectre\n', metric_units={'score': 'fixture'})
        self.fixture = SyntheticSizingBackend(graph, targets={'w': .4, 'c': -.3})
        self.calls = 0

    def connect(self):
        super().connect()
        self.fixture.connect()

    def close(self):
        self.fixture.close()
        super().close()

    def restore(self):
        self.fixture.restore()

    def set_parameters(self, values):
        self.fixture.set_parameters(values)

    def read_parameters(self):
        return self.fixture.read_parameters()

    def generate_netlist(self, root):
        return self.fixture.generate_netlist(root)

    def get_circuit_graph(self, artifact):
        return self.fixture.get_circuit_graph(artifact)

    def run_simulation(self, request):
        self.calls += 1
        self.status = {17: SimulationStatus.TIMEOUT, 37: SimulationStatus.NONCONVERGED,
                       57: SimulationStatus.MEASUREMENT_ERROR}.get(self.calls % 100, SimulationStatus.OK)
        self.metrics = {'score': None if self.calls % 100 == 57 else (.99 if self.calls % 3 else .6)}
        result = super().run_simulation(replace(request, parameters={}))
        return replace(result, candidate_evaluated=self.status in (SimulationStatus.OK, SimulationStatus.NONCONVERGED),
                       applied_parameters=dict(request.parameters), simulator_invocations=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory on local Linux ext4/xfs/etc.')
    parser.add_argument('--evaluations', type=int, default=6000)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.evaluations < 6000:
        parser.error('Acceptance volume requires at least 6000 evaluations')
    if args.output.exists():
        parser.error('Use a new output directory for an unambiguous volume measurement')
    import torch
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.replay import ReplayBuffer, Transition
    from analog_optimizer.training.sac import SACLearner, SACConfig
    torch.set_num_threads(1)
    torch.manual_seed(19)
    rng = random.Random(19)
    graph = SpectreParser(ParserConfig.from_file(ROOT / 'configs/opamp.json')).parse_file(ROOT / 'tests/fixtures/synthetic/opamp.scs')
    backend = InjectedSizingMock(graph)
    configuration = RecordingConfig()
    started = time.perf_counter()
    with ExperimentStore(args.output, configuration) as store:
        run = create_run(store, ROOT, dict(origin='mock', seed=19, algorithm='existing SAC; sparse updates for storage acceptance',
                         algorithm_config=asdict(SACConfig()), model_config=asdict(ModelConfig(hidden_dim=32, heads=4, layers=2)),
                         simulator_version='not_applicable_mock', pdk='not_applicable_mock'),
                         project_files=['configs/opamp.json', 'configs/synthetic_models.json', 'examples/benchmark_recording.py'],
                         templates={'mock': 'injected values; no electrical simulation'})
        recorder = RunRecorder(store, run)
        learner = SACLearner(experiment=dict(origin='synthetic', split='recording-acceptance', designs=['mock-opamp']),
                             model_config=ModelConfig(hidden_dim=32, heads=4, layers=2))
        replay = ReplayBuffer(capacity=256, origin='synthetic', seed=19, store=store)
        checkpoints = CheckpointManager(store, run, args.output)
        steps = 0
        with CircuitSizingEnv(backend, graph, [MetricSpec('score', 'fixture', 'min', 1, lower=.95)],
                              args.output / 'collector', max_steps=199, stop_on_success=False,
                              expected_origin='synthetic', recorder=recorder) as env:
            observation = None
            while backend.calls < args.evaluations:
                if env._done:
                    observation, _ = env.reset()
                else:
                    proposal = {k: rng.uniform(-1, 1) for k in env.mapper.group_ids}
                    step = env.step(proposal)
                    steps += 1
                    if step[4]['replay_eligible']:
                        replay.add(Transition.from_step(observation, proposal, step))
                    observation = step[0]
                    if steps % 1000 == 0 and len(replay) >= 4:
                        learner.update(replay.sample(4))
                    checkpoints.maybe_save(learner, replay, steps, run_state={'collector_rng': rng.getstate()})
                if backend.calls % 1000 == 0:
                    print(json.dumps(dict(evaluations=backend.calls, env_steps=steps, bytes=store.call('usage')['total'])), flush=True)
        final_checkpoint = checkpoints.maybe_save(learner, replay, steps, force=True, run_state={'collector_rng': rng.getstate()})
        checkpoints.policy(learner, steps)
        expected = learner.update(replay.sample(4))
        restored, saved, _ = SACLearner.load(final_checkpoint, experiment=learner.experiment,
                                             model_config=learner.model_config, store=store)
        exact = restored.update(saved.sample(4)) == expected and all(
            torch.equal(a, b) for a, b in zip(learner.actor.parameters(), restored.actor.parameters()))
        store.call('end_run', run)
        report = dict(run_id=run, root=str(args.output.resolve()), evaluations=backend.calls,
                      env_steps=steps, transition_count=len(store.call('read', 'transitions')), replay_members=len(replay),
                      real_simulation_calls=0, exact_learner_resume=exact,
                      summary=store.call('read', 'run', run)['summary'],
                      elapsed_seconds=time.perf_counter() - started)
    # Measure after closing/checkpointing SQLite; include peak reserve assumptions in docs.
    from analog_optimizer.recording.space import disk_bytes
    from save_recording_summary import add_summary_to_report
    add_summary_to_report(args.output, run, report)
    report['bytes'] = {name: disk_bytes(args.output / name) for name in
                       ('experiments.sqlite3', 'experiments.sqlite3-journal', 'experiments.sqlite3-wal',
                        'attachments', 'checkpoints', 'temporary')}
    report['total_bytes'] = disk_bytes(args.output)
    report['summary'] = {k: v for k, v in report['summary'].items() if k not in ('initial', 'best_feasible', 'best_infeasible')}
    report['passed'] = exact and report['evaluations'] >= 6000 and report['bytes']['temporary'] == 0
    destination = args.report or args.output / 'acceptance-report.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report['passed']:
        raise RuntimeError('Recording acceptance failed')


if __name__ == '__main__':
    main()
