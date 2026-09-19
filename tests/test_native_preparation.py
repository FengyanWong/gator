"""Offline CDF fixtures and real IPC/process scheduling; no Cadence certification."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
import json
import multiprocessing
import os
from pathlib import Path
import random
import re
import threading
import time
from types import SimpleNamespace

import pytest

from test_bridge_adapter import profile, adapter, changing_writer
from analog_optimizer.backends import virtuoso_bridge as bridge
from analog_optimizer.backends.backend import SimulationRequest, SimulationResult, SimulationStatus
from analog_optimizer.backends.gpdk045 import GEOMETRY, number
from analog_optimizer.backends.native_preparation import (
    NativeCandidateBackend, PreparationService, PreparationManager)
from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend, BridgeConfig, digest
from analog_optimizer.training.parallel import NativeEnvironmentFactory, collect_parallel_episodes
from analog_optimizer.measurements.specs import MetricSpec

ROOT = Path(__file__).resolve().parents[1]


def fixture_export(state, circuit, output):
    """Test-only native-export stand-in; never infer PDK equations in production."""
    output.mkdir()
    text = (ROOT / 'examples/circuits/gpdk045_ota5.scs').read_text()
    for name in ('M1', 'M2'):
        params = circuit.instances(state)[name]['params']
        first = text.index('    ' + name + ' (')
        last = text.index('\n    M', first + 1)
        statement = text[first:last]
        for key in ('w',) + GEOMETRY:
            statement = re.sub(r'\b' + key + r'=(?:\([^)]*\)|\S+)',
                               lambda _: key + '=(' + str(params[key]) + ')', statement)
        text = text[:first] + statement + text[last:]
    (output / 'netlist').write_text(text)
    return {'input_file': str(output / 'input.scs')}


@pytest.fixture
def service(adapter, monkeypatch):
    writer, calls = changing_writer(adapter)
    monkeypatch.setattr(bridge, 'set_gpdk_mos', writer)
    adapter.test_client.schematic.export_netlist = lambda lib, cell, output, timeout: fixture_export(
        adapter.test_state, adapter.circuit, output)
    service = PreparationService(lambda: adapter, timeout_seconds=10)
    service.baseline()
    yield service, adapter, calls
    service.close()


def activate_lane(backend):
    """Skip the unavailable upstream connection in offline tests only."""
    backend._active = True
    backend._thread, backend._pid = threading.get_ident(), os.getpid()
    backend._env_hash, backend._bound_env = digest(backend.config.env_file), backend._vb_env()


def test_only_actual_candidates_prepared_including_duplicates(service, tmp_path):
    service, adapter, calls = service
    profile = adapter.circuit
    assert calls == []  # Connecting never enumerates or exports a width grid.
    lane = NativeCandidateBackend(adapter.config, profile, service)
    activate_lane(lane)
    saved = []
    for index, width in enumerate([4.105e-6, 3.6e-6, 4.105e-6]):
        parameters = profile.assignments(width)
        artifact, applied = lane.prepare_candidate(tmp_path / 'exports', parameters, candidate_id=f'candidate-{index}')
        assert applied == parameters
        assert profile.validate_export(artifact.path.parent / 'conditioned_structure.scs',
                                       json.loads((artifact.path.parent / 'readback.json').read_text())) == parameters
        meta = json.loads((artifact.path.parent / 'manifest.json').read_text())
        assert meta['candidate_id'] == f'candidate-{index}' and not meta['cache_hit']
        saved.append(artifact)
    assert len(calls) == 6 and len({a.path for a in saved}) == 3
    assert saved[0].sha256 == saved[2].sha256 != saved[1].sha256
    assert all(digest(a.path) == a.sha256 for a in saved)
    assert len(lane._exports) == 1 and not adapter._exports
    assert service.close()['prepared_candidates'] == 3
    assert profile.validate_readback(adapter.test_state) == profile.assignments(4e-6)
    lane.close()


def test_modified_prepared_export_and_wrong_parameters_never_simulate(service, tmp_path):
    service, adapter, _ = service
    lane = NativeCandidateBackend(adapter.config, adapter.circuit, service)
    activate_lane(lane)
    artifact, applied = lane.prepare_candidate(tmp_path, adapter.circuit.assignments(4.1e-6), candidate_id='test')
    with pytest.raises(ValueError, match='parameters differ'):
        lane.run_simulation(SimulationRequest(artifact, tmp_path, parameters=adapter.circuit.assignments(4e-6)))
    artifact.path.write_text('tampered')
    with pytest.raises(ValueError, match='modified'):
        lane.run_simulation(SimulationRequest(artifact, tmp_path, parameters=applied))
    lane.close()


@pytest.mark.parametrize('failure', ['stale_cdf', 'wrong_native', 'partial_write'])
def test_failed_preparation_never_reaches_simulator_and_owner_restores(adapter, monkeypatch, tmp_path, failure):
    writer, calls = changing_writer(adapter, stale=failure == 'stale_cdf', fail_second=failure == 'partial_write')
    monkeypatch.setattr(bridge, 'set_gpdk_mos', writer)
    service = PreparationService(lambda: adapter, timeout_seconds=10)
    service.baseline()
    try:
        with pytest.raises((RuntimeError, ValueError)):
            service.prepare(adapter.circuit.assignments(4.4e-6), tmp_path, adapter.nominal_condition(), 'bad')
        with pytest.raises(RuntimeError, match='stopped'):
            service.prepare(adapter.circuit.assignments(4e-6), tmp_path, adapter.nominal_condition(), 'later')
        assert not list(tmp_path.rglob('result.json'))
    finally:
        result = service.close()
    assert result['prepared_candidates'] == 0
    assert adapter.circuit.validate_readback(adapter.test_state) == adapter.circuit.assignments(4e-6)


class OfflinePreparationBackend(VirtuosoBridgeBackend):
    def _attach(self):
        self.bridge_version = 'offline-scheduling-fixture'
        self.state = deepcopy(self.circuit.reference)
        return SimpleNamespace(list_windows=lambda: [], close=lambda: None,
            schematic=SimpleNamespace(read=lambda *a, **kw: deepcopy(self.state),
                export_netlist=lambda lib, cell, output, timeout: fixture_export(self.state, self.circuit, output)))

    def _write_widths(self, parameters):
        begin = time.time()
        time.sleep(.08)
        for device, parameter in parameters:
            params = self.circuit.instances(self.state)[device.split('/')[1]]['params']
            value = parameters[device, parameter]
            ratio = value / number(params['w'])
            params['w'] = params['fw'] = str(value)
            for key in GEOMETRY:
                params[key] = str(number(params[key]) * ratio)
        bridge.write_json(self.config.state_root / ('prepare-' + __import__('uuid').uuid4().hex + '.json'),
                          dict(pid=os.getpid(), start=begin, end=time.time()))


@dataclass
class OfflinePreparationFactory:
    config: object
    circuit: object

    def __call__(self):
        return OfflinePreparationBackend(self.config, self.circuit)


class OfflineLane(NativeCandidateBackend):
    def connect(self):
        baseline = self.preparation.baseline()
        assert baseline['initial_parameters'] == self._parameters
        activate_lane(self)

    def prepare_recording(self, recorder, eval_id):
        pass

    def finish_recording(self, receipt):
        pass

    def run_simulation(self, request):
        begin = time.time()
        self.get_circuit_graph(request.netlist)
        # Hold the simulator open while the next candidate is prepared.
        time.sleep(.6)
        result_root = request.work_root / request.netlist.job_id
        result_root.mkdir(parents=True)
        bridge.write_json(self.config.state_root / ('simulate-' + request.netlist.job_id + '.json'),
                          dict(pid=os.getpid(), start=begin, end=time.time()))
        applied = self._exports[request.netlist.job_id][1]
        assert applied == request.parameters
        return SimulationResult(request.netlist.job_id, 'offline-fixture', 'real', SimulationStatus.OK,
            'offline-fixture', False, True, {'score': next(iter(applied.values())) / 4e-6},
            {'score': 'fixture'}, {'score': True}, applied, result_root, time.time() - begin,
            request.condition, simulator_invocations=1)


@dataclass(frozen=True)
class OfflineNativeFactory(NativeEnvironmentFactory):
    def create_recorded(self, lane, recorder):
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        return CircuitSizingEnv(OfflineLane(self.config, self.profile, self.preparation),
            self.profile.optimization_graph(), self.specs, self.output / f'worker-{lane}',
            max_steps=self.max_steps, stop_on_success=False, recorder=recorder)


@pytest.mark.parametrize('recorded', [False, True])
def test_serial_native_preparation_overlaps_four_simulators_with_independent_replay(profile, tmp_path, monkeypatch, recorded):
    import torch
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.sac import SACLearner
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.backends import native_preparation
    monkeypatch.setattr(native_preparation, 'BridgePreparationFactory', OfflinePreparationFactory)
    torch.set_num_threads(1)
    env = tmp_path / 'env'
    env.write_text('# offline')
    receipt = tmp_path / 'receipt.json'
    bridge.write_json(receipt, dict(library='TEST', config=profile.design,
        core_cell=profile.design['core_cell'], testbench_cell=profile.design['testbench_cell']))
    config = BridgeConfig(env, 'TEST', receipt, tmp_path / 'state', '/models/offline.scs')
    factory = OfflineNativeFactory(config, profile, (MetricSpec('score', 'fixture', 'min', 1, lower=1),),
                                   tmp_path, 2)
    learner = SACLearner(experiment=dict(origin='real', split='offline-integration', designs=['fixture']),
                        model_config=ModelConfig(hidden_dim=16, heads=2, layers=1))
    replay = ReplayBuffer(origin='real')
    from contextlib import ExitStack
    with ExitStack() as stack:
        recorder = None
        if recorded:
            from analog_optimizer.recording import start_service, RunRecorder
            manager, store = start_service(tmp_path / 'records', dict(min_free=0, temporary_reserve=0))
            stack.callback(manager.shutdown)
            stack.callback(store.close)
            recorder = RunRecorder(store, store.call('run', {}))
            # Keep an in-memory replay here so lane-specific transitions can be audited below.
        report = collect_parallel_episodes(factory, learner, replay, random.Random(8), max_workers=4,
            episodes=4, warmup=4, batch_size=2, recorder=recorder)
        if recorded:
            assert store.call('read', 'run', recorder.run_id)['summary']['evaluations'] == 12
    assert report['passed'] and report['simulation_calls'] == 12 and len(replay) == 8
    assert report['preparation_restoration']['prepared_candidates'] == 12
    preparations = [json.loads(p.read_text()) for p in config.state_root.glob('prepare-*.json')]
    simulations = [json.loads(p.read_text()) for p in config.state_root.glob('simulate-*.json')]
    assert {p['pid'] for p in preparations} == {report['preparation']['pid']}
    assert len({p['pid'] for p in simulations}) == 4
    assert report['preparation']['pid'] not in {p['pid'] for p in simulations}
    ordered = sorted(preparations, key=lambda p: p['start'])
    assert all(a['end'] <= b['start'] for a, b in zip(ordered, ordered[1:]))
    assert any(p['start'] < s['end'] and s['start'] < p['end'] for p in preparations for s in simulations)
    events = sorted([(s['start'], 1) for s in simulations] + [(s['end'], -1) for s in simulations])
    active = peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    assert peak == 4
    for stage in ([] if recorded else report['stages']):
        record = json.loads(Path(stage['record_path']).read_text())
        manifest = json.loads(Path(record['netlist_path']).with_name('manifest.json').read_text())
        assert record['candidate_id'] == manifest['candidate_id'] == stage['candidate_id']
        assert record['requested_parameters'] == manifest['proposed_parameters'] == record['applied_parameters']
    for transition in replay._items:
        width = next(iter(transition.next_observation.graph.assignments(
            {g.id: g.value for g in transition.next_observation.graph.parameter_groups if g.mutable}).values()))
        assert transition.next_observation.metrics['score'] == width / 4e-6


def test_five_spectre_workers_rejected_before_any_io():
    with pytest.raises(ValueError, match='between 1 and 4'):
        collect_parallel_episodes(None, None, None, None, max_workers=5, episodes=5)
