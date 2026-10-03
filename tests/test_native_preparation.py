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
from analog_optimizer.backends import native_preparation, virtuoso_bridge as bridge
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
    (output / 'netlist').write_text(fixture_text(state, circuit))
    return {'input_file': str(output / 'input.scs')}


def fixture_text(state, circuit):
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
    return text


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


def test_more_spectre_workers_than_the_cap_are_rejected_before_any_io():
    with pytest.raises(ValueError, match='between 1 and 6'):
        collect_parallel_episodes(None, None, None, None, max_workers=7, episodes=7)
    assert native_preparation.MAX_SPECTRE_WORKERS == 6                        # 4 until record 7.143


def counted(adapter):
    """Counts the whole-cell reads and window checks the preparation makes through the fake client."""
    counts, read, windows = dict(read=0, windows=0), adapter.test_client.schematic.read, adapter.test_client.list_windows
    def counted_read(*args, **kwargs):
        counts['read'] += 1
        return read(*args, **kwargs)
    def counted_windows():
        counts['windows'] += 1
        return windows()
    adapter.test_client.schematic.read, adapter.test_client.list_windows = counted_read, counted_windows
    return counts


def test_a_prepared_candidate_reads_the_cell_before_and_after_its_write_and_after_its_export(service, tmp_path):
    """Three whole-cell reads and one window check per candidate (record 7.137, user decision of 2026-10-01): a readback
    right after the write's own readback and a read before the export repeated a check made a moment earlier."""
    service, adapter, _ = service
    counts = counted(adapter)
    lane = NativeCandidateBackend(adapter.config, adapter.circuit, service)
    activate_lane(lane)
    artifact, applied = lane.prepare_candidate(tmp_path, adapter.circuit.assignments(4.1e-6), candidate_id='one')
    assert applied == adapter.circuit.assignments(4.1e-6) and counts == dict(read=3, windows=1)
    assert json.loads((artifact.path.parent / 'manifest.json').read_text())['applied_parameters']
    lane.close()


def test_a_cell_edited_during_the_export_is_still_refused(service, tmp_path):
    """The read after the export still sees an edit made in Virtuoso while the candidate was being prepared."""
    service, adapter, _ = service
    params = adapter.circuit.instances(adapter.test_state)['M1']['params']
    length, export = params['l'], adapter.test_client.schematic.export_netlist
    def edited_while_exporting(lib, cell, output, timeout):
        params['l'] = '1u'                                   # someone changes the cell in Virtuoso meanwhile
        return export(lib, cell, output, timeout)
    adapter.test_client.schematic.export_netlist = edited_while_exporting
    lane = NativeCandidateBackend(adapter.config, adapter.circuit, service)
    activate_lane(lane)
    with pytest.raises((RuntimeError, ValueError), match=r'M1\.l'):              # a fixed parameter that changed
        lane.prepare_candidate(tmp_path, adapter.circuit.assignments(4.1e-6), candidate_id='edited')
    params['l'] = length                                     # undo the edit, so that the owner's restoration can verify
    lane.close()


def test_check_only_mode_compares_a_netlist_built_from_each_readback_with_its_native_export(adapter, monkeypatch, tmp_path):
    """GATOR_NETLIST_BUILD=check (record 7.140): the session's first export is the template, every candidate's built
    netlist is compared with its native export, and a build that differs stops the service."""
    monkeypatch.setenv('GATOR_NETLIST_BUILD', 'check')
    writer, _ = changing_writer(adapter)
    monkeypatch.setattr(bridge, 'set_gpdk_mos', writer)
    adapter.test_client.schematic.export_netlist = lambda lib, cell, output, timeout: fixture_export(
        adapter.test_state, adapter.circuit, output)
    templates = []
    def render(template, snapshot):
        templates.append(template)
        return fixture_text(snapshot, adapter.circuit)
    monkeypatch.setattr(adapter.circuit, 'render_export', render, raising=False)
    service = PreparationService(lambda: adapter, timeout_seconds=10)
    service.baseline()
    try:
        for width in (4.1e-6, 3.6e-6):
            _, _, metadata = service.prepare(adapter.circuit.assignments(width), tmp_path, adapter.nominal_condition(), f'w{width}')
            assert metadata['built_export'] == 'matches the native export'
        assert len(templates) == 2 and templates[0] == templates[1]          # one template: the session's first export
        monkeypatch.setattr(adapter.circuit, 'render_export', lambda template, snapshot: template, raising=False)
        with pytest.raises(ValueError, match='differs from the native export: statement'):
            service.prepare(adapter.circuit.assignments(4.4e-6), tmp_path, adapter.nominal_condition(), 'stale')
    finally:
        service.close()


def started(adapter, monkeypatch, mode):
    """A preparation service around the fake adapter, its exports counted, its netlists built as the fixture exports."""
    if mode is None:
        monkeypatch.delenv('GATOR_NETLIST_BUILD', raising=False)
    else:
        monkeypatch.setenv('GATOR_NETLIST_BUILD', mode)
    writer, _ = changing_writer(adapter)
    monkeypatch.setattr(bridge, 'set_gpdk_mos', writer)
    counts = dict(exports=0, reads=0)
    def export(lib, cell, output, timeout):
        counts['exports'] += 1
        return fixture_export(adapter.test_state, adapter.circuit, output)
    read = adapter.test_client.schematic.read
    def counted_read(*args, **kwargs):
        counts['reads'] += 1
        return read(*args, **kwargs)
    adapter.test_client.schematic.export_netlist, adapter.test_client.schematic.read = export, counted_read
    monkeypatch.setattr(adapter.circuit, 'render_export', lambda template, snapshot: fixture_text(snapshot, adapter.circuit),
                        raising=False)
    service = PreparationService(lambda: adapter, timeout_seconds=10)
    service.baseline()
    return service, counts


def test_a_native_mode_builds_nothing(adapter, monkeypatch, tmp_path):
    service, counts = started(adapter, monkeypatch, 'native')
    monkeypatch.setattr(adapter.circuit, 'render_export', lambda *a: pytest.fail('built in native mode'), raising=False)
    try:
        _, _, metadata = service.prepare(adapter.circuit.assignments(4.1e-6), tmp_path, adapter.nominal_condition(), 'plain')
        assert 'built_export' not in metadata and metadata['netlist_source'] == 'native export' and counts['exports'] == 1
    finally:
        service.close()


def test_by_default_a_netlist_is_built_from_the_readback_with_a_native_export_every_fifth_candidate(adapter, monkeypatch, tmp_path):
    """Record 7.142 (user decision of 2026-10-02): the session's first candidate and every 5th after are exported and
    compared with their build; the others are built, without an export and without a read after the write's readback."""
    service, counts = started(adapter, monkeypatch, None)
    widths = [4.1e-6, 3.6e-6, 4.4e-6, 4.105e-6, 4.1e-6, 3.6e-6, 4.4e-6]
    try:
        sources = []
        for index, width in enumerate(widths):
            before = dict(counts)
            artifact, applied, metadata = service.prepare(adapter.circuit.assignments(width), tmp_path,
                                                          adapter.nominal_condition(), f'c{index}')
            sources.append(metadata['netlist_source'])
            assert applied == adapter.circuit.assignments(width)
            built = Path(metadata['original_structure_path']).read_text()
            assert native_preparation.first_difference(built, fixture_text(adapter.test_state, adapter.circuit)) is None
            if metadata['netlist_source'] == 'native export':
                assert metadata['built_export'] == 'matches the native export' and counts['exports'] == before['exports'] + 1
                assert metadata['preparation'] == 'actual-candidate-cdf-native-export'
            else:
                assert counts == dict(before, reads=before['reads'] + 2)     # the reads before and after the write only
                assert metadata['preparation'] == 'actual-candidate-cdf-built-netlist' and 'built_export' not in metadata
        assert sources == ['native export'] + ['built from the readback'] * 4 + ['native export', 'built from the readback']
    finally:
        service.close()


def test_the_windows_are_checked_before_each_export_and_not_for_a_built_netlist(adapter, monkeypatch, tmp_path):
    """Record 7.149: an open ADE/Maestro window conflicts with OCEAN's export, not with a write. A candidate whose netlist
    is built from its readback runs no OCEAN and checks no window; the next export still refuses such a window."""
    service, _ = started(adapter, monkeypatch, None)
    checks, windows = [], []

    def listed():
        checks.append(1)
        return list(windows)
    adapter.test_client.list_windows = listed
    try:
        made = []
        for index, width in enumerate([4.1e-6, 3.6e-6, 4.4e-6, 4.105e-6, 4.1e-6]):
            before = len(checks)
            _, _, metadata = service.prepare(adapter.circuit.assignments(width), tmp_path, adapter.nominal_condition(), f'c{index}')
            made.append((metadata['netlist_source'], len(checks) - before))
        assert made == [('native export', 1)] + [('built from the readback', 0)] * 4
        windows.append({'name': 'ADE Assembler'})                                  # opened while the run goes on
        with pytest.raises(RuntimeError, match='conflicts with OCEAN export'):     # the 6th candidate is exported
            service.prepare(adapter.circuit.assignments(3.6e-6), tmp_path, adapter.nominal_condition(), 'c5')
    finally:
        service.close()


def test_an_unknown_netlist_mode_is_refused_before_anything_is_prepared(adapter, monkeypatch):
    monkeypatch.setenv('GATOR_NETLIST_BUILD', 'sometimes')
    service = PreparationService(lambda: adapter, timeout_seconds=10)
    with pytest.raises(ValueError, match='GATOR_NETLIST_BUILD must be one of skip, check, native'):
        service.baseline()


class OceanClient:
    """`execute_skill` and `download_file` as the real bridge client has them, OCEAN's current design kept as Virtuoso
    keeps it: one set-up serves every createNetlist until something sets another design."""

    def __init__(self, inner, adapter):
        self.inner, self.adapter, self.design, self.setups, self.netlists = inner, adapter, None, 0, 0
        self.schematic, self.list_windows, self.close = inner.schematic, inner.list_windows, inner.close

    def execute_skill(self, text, timeout=60):
        if text.startswith('progn(simulator('):
            self.setups += 1
            self.design = re.search(r'design\("([^"]+)" "([^"]+)"', text).groups()
            return SimpleNamespace(ok=True, output='t', errors=[])
        assert 'createNetlist(?recreateAll t' in text, text
        self.netlists += 1
        return SimpleNamespace(ok=True, output=f'"/sim/{self.design[1]}/spectre/schematic/netlist/input.scs"', errors=[])

    def download_file(self, remote, local, timeout=None, recursive=False):
        assert recursive and remote.endswith('/netlist')
        local.mkdir()
        (local / 'input.scs').write_text('')
        (local / 'netlist').write_text(fixture_text(self.adapter.test_state, self.adapter.circuit))
        return SimpleNamespace(ok=True)


def test_the_netlister_is_set_up_once_and_again_when_another_design_took_it(adapter, monkeypatch, tmp_path):
    """Record 7.142 (user decision of 2026-10-02): OCEAN set up once per session instead of before every export (0.27 ->
    0.18 s per export on Virtuoso, 7.140); a netlist of another testbench means something set OCEAN meanwhile."""
    ocean = OceanClient(adapter.test_client, adapter)
    monkeypatch.setattr(VirtuosoBridgeBackend, '_attach', lambda self: setattr(self, 'bridge_version', 'offline') or ocean)
    adapter.connect()
    for index in range(3):
        adapter.generate_netlist(tmp_path / f'e{index}')
    assert (ocean.setups, ocean.netlists) == (1, 3)
    ocean.design = ('OTHER', 'tb_other')                      # another tool set OCEAN to its own testbench meanwhile
    adapter.generate_netlist(tmp_path / 'after')
    assert (ocean.setups, ocean.netlists) == (2, 5)           # noticed, set up again, netlisted again
    monkeypatch.setattr(adapter.circuit, 'measures_in_virtuoso', True, raising=False)
    exports = []
    adapter.test_client.schematic.export_netlist = lambda lib, cell, output, timeout: exports.append(cell) or fixture_export(
        adapter.test_state, adapter.circuit, output)
    adapter.generate_netlist(tmp_path / 'maestro')            # OCEAN shared with the measurement: the bridge's export
    assert exports == [adapter.circuit.design['testbench_cell']] and (ocean.setups, ocean.netlists) == (2, 5)
