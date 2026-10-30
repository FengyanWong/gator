"""Offline fault injection. Fake clients here never certify real simulation results."""
from copy import deepcopy
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus, UnsupportedCapability
from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend, build_deck
import analog_optimizer.backends.virtuoso_bridge as module
from research_support import ROOT, adapter, changing_writer, profile


def test_profile_rejects_unmatched_partial_and_out_of_range(profile):
    for values in [{('XU1/M1', 'w'): 4e-6}, profile.assignments(4e-6) | {('XU1/M3', 'w'): 4e-6},
                   {('XU1/M1', 'w'): 4e-6, ('XU1/M2', 'w'): 4.4e-6},
                   {('XU1/M1', 'w'): float('nan'), ('XU1/M2', 'w'): float('nan')}]:
        with pytest.raises(ValueError):
            profile.validate_assignment(values)
    with pytest.raises(ValueError):
        profile.assignments(8e-6)
    with pytest.raises(ValueError, match='width grid'):
        profile.assignments(4.1067917531630854e-6)


def test_rollback_after_partial_write_and_close_restore(adapter, monkeypatch):
    write, calls = changing_writer(adapter, fail_second=True)
    monkeypatch.setattr(module, 'set_gpdk_mos', write)
    with adapter:
        with pytest.raises(RuntimeError, match='injected'):
            adapter.set_parameters(adapter.circuit.assignments(4.4e-6))
        assert adapter.read_parameters() == adapter.circuit.assignments(4e-6)
        record = json.loads(next(adapter.session_dir.glob('update-*')).read_text())
        assert record['status'] == 'rolled_back'
        adapter.set_parameters(adapter.circuit.assignments(4.4e-6))
        assert adapter.read_parameters() == adapter.circuit.assignments(4.4e-6)
    assert adapter.test_client.closed
    assert adapter.circuit.validate_readback(adapter.test_state) == adapter.circuit.assignments(4e-6)
    assert json.loads((adapter.session_dir / 'restoration.json').read_text())['status'] == 'restored'


def test_stale_cdf_is_not_success(adapter, monkeypatch):
    write, _ = changing_writer(adapter, stale=True)
    monkeypatch.setattr(module, 'set_gpdk_mos', write)
    with adapter:
        with pytest.raises(ValueError, match='Stale derived'):
            adapter.set_parameters(adapter.circuit.assignments(4.4e-6))
        assert adapter.read_parameters() == adapter.circuit.assignments(4e-6)


def test_failed_restoration_is_explicit_and_releases_resources(adapter, monkeypatch):
    adapter.connect()
    def fail(*args):
        raise ConnectionError('injected disconnected bridge')
    monkeypatch.setattr(module, 'set_gpdk_mos', fail)
    with pytest.raises(RuntimeError, match='restoration failed'):
        adapter.set_parameters(adapter.circuit.assignments(4.4e-6))
    assert json.loads(next(adapter.session_dir.glob('update-*')).read_text())['status'] == 'recovery_required'
    with pytest.raises(ConnectionError):
        adapter.close()
    assert json.loads((adapter.session_dir / 'restoration.json').read_text())['status'] == 'recovery_required'
    assert adapter.client is None and adapter._lock_file is None
    assert not adapter._process_lock.locked()


def test_active_ade_blocks_connection_without_mutation(adapter):
    adapter.test_client.list_windows = lambda: [{'name': 'ADE Assembler'}]
    with pytest.raises(RuntimeError, match='conflicts'):
        adapter.connect()
    assert adapter.test_client.closed
    assert not adapter._process_lock.locked()


def test_lock_and_configuration_change_fail_closed(adapter, monkeypatch):
    adapter.config.state_root.mkdir()
    with (adapter.config.state_root / 'session.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            adapter.connect()
    with adapter:
        second = VirtuosoBridgeBackend(adapter.config, adapter.circuit)
        with pytest.raises(RuntimeError, match='owns this process'):
            second.connect()
        monkeypatch.setenv('VB_TEST_CHANGED', '1')
        with pytest.raises(RuntimeError, match='configuration changed'):
            adapter.read_parameters()


def test_export_rejects_changed_topology_or_passive(profile, tmp_path):
    text = (ROOT / 'examples/circuits/gpdk045_ota5.scs').read_text()
    for changed in (text.replace('CL (VOUT 0)', 'CL (VOUT VDD)'), text.replace('c=1p', 'c=2p')):
        path = tmp_path / 'changed.scs'
        path.write_text(changed)
        with pytest.raises(ValueError):
            profile.validate_export(path, profile.reference)


def test_immutable_artifacts_and_parameter_binding(adapter, tmp_path):
    with adapter:
        a, b = [adapter.generate_netlist(tmp_path / 'exports') for _ in range(2)]
        assert a.path != b.path and a.sha256 == b.sha256
        with pytest.raises(ValueError, match='parameters differ'):
            adapter.run_simulation(SimulationRequest(a, tmp_path, parameters=adapter.circuit.assignments(4.4e-6)))
        a.path.write_text('modified')
        with pytest.raises(ValueError, match='modified'):
            adapter.run_simulation(SimulationRequest(a, tmp_path))


@pytest.mark.parametrize('mode', ['failure', 'timeout', 'missing', 'missing_psf', 'valid'])
def test_result_status_measurements_and_no_stale_op(adapter, tmp_path, monkeypatch, mode):
    def run(deck):
        """Return an injected bridge outcome or timeout without launching a simulator."""
        if mode == 'timeout':
            raise TimeoutError('injected timeout')
        return SimpleNamespace(ok=mode != 'failure', status=SimpleNamespace(value='success' if mode != 'failure' else 'error'),
                               errors=['injected failure'] if mode == 'failure' else [], metadata={})
    monkeypatch.setattr(adapter, '_new_simulator', lambda *a: SimpleNamespace(run_simulation=run))
    def measure(*a, **kw):
        """Supply test measurements and operating points, or simulate a missing PSF result."""
        if mode == 'missing_psf':
            raise FileNotFoundError('injected missing PSF')
        return {'metrics': {'gain': 25}, 'metric_units': {'gain': 'dB'}, 'metric_validity': {'gain': True},
                'operating_points': {'test_only': {'gm': 1e-6}}}
    monkeypatch.setattr(module, 'analyze', measure)
    with adapter:
        artifact = adapter.generate_netlist(tmp_path / 'exports')
        result = adapter.run_simulation(SimulationRequest(artifact, tmp_path / 'runs',
                                                          ('missing',) if mode == 'missing' else ('gain',)))
        expected = {'failure': SimulationStatus.BACKEND_ERROR, 'timeout': SimulationStatus.TIMEOUT,
                    'missing': SimulationStatus.MEASUREMENT_ERROR,
                    'missing_psf': SimulationStatus.MEASUREMENT_ERROR, 'valid': SimulationStatus.OK}[mode]
        assert result.status == expected
        assert result.candidate_evaluated == (mode in ('missing', 'valid'))
        if mode in ('missing', 'valid'):
            assert result.operating_points == {'test_only': {'gm': 1e-6}}
        assert json.loads((result.artifact_directory / 'result.json').read_text())['status'] == expected.value
        if mode != 'valid':
            with pytest.raises(UnsupportedCapability):
                adapter.get_operating_points()
        else:
            assert adapter.get_operating_points()['test_only']['gm'] == 1e-6


def test_deck_preserves_baseline_conditions():
    text = build_deck('CL (VOUT 0) capacitor c=1p\n', '/models/gpdk.scs')
    assert 'section=tt' in text and 'temp=27' in text and 'dec=60' in text
    with pytest.raises(ValueError):
        build_deck('include "hidden.scs"', '/models/gpdk.scs')


def test_export_graph_has_only_verified_action_and_checks_digest(adapter, tmp_path):
    with adapter:
        artifact = adapter.generate_netlist(tmp_path / 'exports')
        graph = adapter.get_circuit_graph(artifact)
        assert [g.id for g in graph.parameter_groups if g.mutable] == ['input_pair_width']
        group = graph.parameter_groups[0]
        assert (group.lower, group.upper, group.scale) == (3.6e-6, 4.4e-6, 'linear')
        assert group.step == 5e-9
        metadata = json.loads((artifact.path.parent / 'manifest.json').read_text())
        Path(metadata['structure_path']).write_text('changed')
        with pytest.raises(ValueError, match='structure changed'):
            adapter.get_circuit_graph(artifact)


def test_real_cdf_rounding_is_projected_before_writeback(profile):
    from analog_optimizer.parameters import ActionMapper
    action = ActionMapper(profile.optimization_graph()).legalize({'input_pair_width': 0.2669793829077143})
    assert action.projected_groups == ('input_pair_width',)
    assert list(action.assignments.values()) == pytest.approx([4.105e-6, 4.105e-6])
    profile.validate_assignment(action.assignments)


def test_five_pdk_corners_prepare_realistic_decks_without_schematic_changes(adapter, tmp_path):
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
    before = deepcopy(adapter.test_state)
    with adapter:
        baseline = adapter.generate_netlist(tmp_path / 'nominal')
        for row in adapter.circuit.condition_config['screening_corners']:
            corner = PVTCorner(**row)
            condition = SimulationCondition(corner, 'pvt_validation')
            artifact = adapter.generate_netlist(tmp_path / 'pvt', condition=condition)
            text = artifact.path.read_text()
            assert f'section={corner.model_section}' in text
            assert f'temp={corner.temperature_c:.12g} tnom=27' in text
            graph = adapter.get_circuit_graph(artifact)
            assert graph.parameters['VDD']['dc'].value == corner.supply_v
            assert graph.parameters['VN']['dc'].value == 0.6
            assert graph.parameters['VB']['dc'].value == 0.4
            assert graph.metadata['simulation_condition']['purpose'] == 'pvt_validation'
            assert sum(g.mutable for g in graph.parameter_groups) == 1
            assert adapter.test_state == before
            if corner.id == 'nominal':
                assert artifact.sha256 == baseline.sha256  # Legacy nominal deck is unchanged.
        # Previously verified baseline bytes with the fixture's /models/gpdk.scs path.
        assert baseline.sha256 == 'e8f80f40a465a192a2501e070414588587816c25328917adcae70d3d652d5772'


def test_pvt_voltage_unknown_sections_and_mc_fail_preflight(adapter, tmp_path):
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition, MonteCarloConfig
    from dataclasses import replace
    nominal = adapter.nominal_condition()
    invalid = [SimulationCondition(replace(nominal.corner, supply_v=1.8), 'pvt_validation'),
               SimulationCondition(replace(nominal.corner, temperature_c=150), 'pvt_validation'),
               SimulationCondition(replace(nominal.corner, model_section='unknown'), 'pvt_validation'),
               SimulationCondition(replace(nominal.corner, model_section='ss'))]
    for condition in invalid:
        with pytest.raises(ValueError):
            adapter.generate_netlist(tmp_path / 'rejected', condition=condition)
    mc = SimulationCondition(nominal.corner, 'mc_validation', MonteCarloConfig(4, 42))
    with pytest.raises(UnsupportedCapability, match='MC interface reserved'):
        adapter.generate_netlist(tmp_path / 'rejected', condition=mc)
    assert adapter.client is None and not (tmp_path / 'rejected').exists()


def test_pvt_result_preserves_prepared_context(adapter, tmp_path, monkeypatch):
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
    monkeypatch.setattr(adapter, '_new_simulator', lambda *a: SimpleNamespace(run_simulation=lambda deck:
        SimpleNamespace(ok=True, status=SimpleNamespace(value='success'), errors=[], metadata={})))
    monkeypatch.setattr(module, 'analyze', lambda *a, **kw: {
        'metrics': {'gain': 20}, 'metric_units': {'gain': 'dB'}, 'metric_validity': {'gain': True}, 'operating_points': {}})
    condition = SimulationCondition(PVTCorner('ss_hot_low', 'ss', 125, 0.9), 'pvt_validation')
    with adapter:
        artifact = adapter.generate_netlist(tmp_path / 'exports', condition=condition)
        result = adapter.run_simulation(SimulationRequest(artifact, tmp_path / 'runs', ('gain',), condition=condition))
        assert result.condition == condition and result.sample_index is None
        saved = json.loads((result.artifact_directory / 'result.json').read_text())
        assert saved['condition']['corner']['supply_v'] == 0.9
