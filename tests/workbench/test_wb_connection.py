"""Virtuoso / bridge connection check (specification 2.1), with FAKE bridge clients and a fake probe
process. No test contacts a real Virtuoso, tunnel, daemon, Spectre host or license server."""
import fcntl
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import connection, consistency, paths, runs, tasks
from gator_workbench.connection import ConnectionMonitor, LAYERS, run_layers
from gator_workbench.storage.atomic import read_jsonl
from helpers import bridge_settings as settings, execute, make_config, roots_for, rows, summary, workbench_app   # noqa: F401 - an imported fixture belongs to this module
from fakes_connection import FakeBridge, OK_BODY, fake_probe, layers_json, monitor_for, reasons, states, write_profiles

REPO = Path(__file__).resolve().parents[2]


def check(settings, scope='full', run_active=False, **behaviour):
    """Run the requested connection-check scope against a configurable fake bridge."""
    bridge = FakeBridge(**behaviour)
    return run_layers(bridge, settings, scope=scope, run_active=run_active), bridge


# ------------------------------------------------------------------------------- layers
def test_all_layers_ok_in_dependency_order(settings):
    layers, bridge = check(settings)
    assert [item['layer'] for item in layers] == list(LAYERS) and set(states(layers).values()) == {'ok'}
    assert bridge.calls.index('version') < bridge.calls.index('tunnel_state') < bridge.calls.index('skill') \
        < bridge.calls.index('readiness') < bridge.calls.index('license')
    assert bridge.calls.count('skill') == 1                                   # ONE trivial round trip
    license_layer = layers[-1]
    assert license_layer['details']['features'] == [dict(feature='Virtuoso_Multi_mode_Simulation', issued=10, in_use=3, available=7)]
    assert 'does not check out or hold a seat' in license_layer['details']['note']


def downstream_not_checked(layers, failed_layer):
    """Assert that layers after the failed layer remain unchecked."""
    index = LAYERS.index(failed_layer)
    assert all(item['state'] == 'not_checked' for item in layers[index + 1:]), states(layers)   # never ok, never failed


@pytest.mark.parametrize('behaviour, layer_name, state, reason', [
    (dict(import_error=True), 'bridge_package', 'failed', 'bridge_not_importable'),
    (dict(version='0.9.1'), 'bridge_package', 'failed', 'bridge_version_unverified'),
    (dict(resolved='some-other-profile'), 'connection_profile', 'failed', 'implicit_profile_binding'),
    (dict(roles=dict(daemon_host=None, spectre_host=None, remote_user='alice')), 'connection_profile', 'failed', 'profile_incomplete'),
    (dict(running=False), 'tunnel', 'failed', 'tunnel_not_running'),
    (dict(client_error=ConnectionRefusedError('refused')), 'daemon', 'failed', 'no_response'),
    (dict(skill=(False, ['no reply'])), 'daemon', 'failed', 'no_response'),
    (dict(skill=(False, ['Daemon authentication failed'])), 'daemon', 'failed', 'auth_failed'),
    (dict(user=dict(ok=False, skipped=False, error='daemon user bob != alice')), 'daemon', 'failed', 'daemon_user_mismatch'),
    (dict(license=dict(spectre_path=None, licenses=[])), 'spectre', 'failed', 'spectre_not_found'),
])
def test_each_broken_link_is_named_and_everything_downstream_is_not_checked(settings, behaviour, layer_name, state, reason):
    layers, _ = check(settings, **behaviour)
    assert states(layers)[layer_name] == state and reasons(layers)[layer_name] == reason
    assert all(item['state'] == 'ok' or item['state'] == 'not_applicable' for item in layers[:LAYERS.index(layer_name)])
    downstream_not_checked(layers, layer_name)
    broken = next(item for item in layers if item['layer'] == layer_name)
    assert broken['details']['next_step']                                     # the specific next step, not "failed"


def test_bridge_in_another_virtualenv_is_not_a_virtuoso_failure(settings):
    layers, _ = check(settings, import_error=True)
    assert reasons(layers) == {'bridge_package': 'bridge_not_importable'}
    assert layers[0]['details']['interpreter'] == sys.executable and states(layers)['daemon'] == 'not_checked'


def test_no_profile_still_checks_the_package_layer_first(settings):
    layers = run_layers(FakeBridge(), None, profile_error=('connection_file_missing', 'no file'))
    assert states(layers)['bridge_package'] == 'ok' and reasons(layers) == {'connection_profile': 'connection_file_missing'}
    downstream_not_checked(layers, 'connection_profile')
    layers = run_layers(FakeBridge(import_error=True), None, profile_error=('connection_file_missing', 'no file'))
    assert reasons(layers) == {'bridge_package': 'bridge_not_importable'}       # the FIRST broken link, not a later one
    downstream_not_checked(layers, 'bridge_package')


def test_missing_env_file(settings):
    layers, _ = check(dict(settings, env_file=str(Path(settings['env_file']).with_name('absent.env'))))
    assert reasons(layers)['connection_profile'] == 'env_file_missing'
    downstream_not_checked(layers, 'connection_profile')


def test_local_mode_has_no_tunnel(settings):
    layers, _ = check(settings, local=True, state=dict(mode='local', port=65432), running=True)
    assert states(layers)['tunnel'] == 'not_applicable' and states(layers)['daemon'] == 'ok'
    layers, _ = check(settings, local=True, state=None, running=False)       # local mode, bridge never set up
    assert states(layers)['tunnel'] == 'not_applicable' and reasons(layers)['daemon'] == 'local_bridge_not_set_up'
    broken = next(item for item in layers if item['layer'] == 'daemon')      # its own next step: not "load the line" (there is none yet)
    assert broken['state'] == 'failed' and 'Set up local bridge' in broken['details']['next_step']


def test_readiness_is_separate_from_connectivity(settings):
    layers, _ = check(settings, windows=['ADE Assembler Editing: lib tb maestro'])
    assert states(layers)['daemon'] == 'ok'                                   # connected...
    assert states(layers)['session_readiness'] == 'not_ready'                 # ...but the adapter would refuse to run
    assert reasons(layers)['session_readiness'] == 'conflicting_ade_windows'
    assert states(layers)['spectre'] == states(layers)['spectre_license'] == 'not_checked'


def test_readiness_reuses_the_adapters_own_rule():
    """The panel calls the adapter's rule, so there are never two definitions of 'ready'."""

    class Client:
        """A bridge client stand-in that returns the fixture window listing."""
        def __init__(self, names):
            self.names = names

        def list_windows(self):
            return [dict(name=n) for n in self.names]
    bridge = connection.RealBridge.__new__(connection.RealBridge)
    bridge.readiness(Client(['Virtuoso Schematic Editor L: lib cell schematic']))       # fine
    for conflicting in ('ADE Explorer', 'Maestro: tb', 'Analog Design Environment', 'ADE Assembler'):
        with pytest.raises(RuntimeError):
            bridge.readiness(Client([conflicting]))
    source = (REPO / 'src/analog_optimizer/backends/virtuoso_bridge.py').read_text()
    assert f"!= '{connection.VERIFIED_BRIDGE_VERSION}'" in source              # the verified version cannot drift apart


@pytest.mark.parametrize('lines, state, reason', [
    (['Users of Spectre_Basic:  (Total of 4 licenses issued;  Total of 4 licenses in use)'], 'failed', 'license_unavailable'),
    ([], 'unknown', 'license_not_checkable'),
    (['lmstat: command not found', 'garbage ### output'], 'unknown', 'license_not_checkable'),
    (['Users of Layout_Suite:  (Total of 5 licenses issued;  Total of 1 license in use)'], 'unknown', 'license_not_checkable'),
])
def test_license_unavailable_not_checkable_and_unparseable(settings, lines, state, reason):
    layers, _ = check(settings, license=dict(spectre_path='/cad/spectre', licenses=lines))
    assert states(layers)['spectre'] == 'ok' and states(layers)['spectre_license'] == state
    assert reasons(layers)['spectre_license'] == reason


def test_license_is_not_checked_unless_asked(settings):
    layers, bridge = check(settings, scope='interactive')
    assert states(layers)['spectre'] == states(layers)['spectre_license'] == 'not_checked' and 'license' not in bridge.calls
    layers, bridge = check(settings, scope='cheap')
    assert states(layers)['daemon'] == 'not_checked' and 'client' not in bridge.calls     # cheap = no Virtuoso contact


# ---- a connection that does not ask its license server (record 7.479) -----------------------------------------------
@pytest.mark.parametrize('lines', [
    [],                                                                                             # nothing read
    ['Users of Virtuoso_Multi_mode_Simulation:  (Total of 10 licenses issued;  Total of 3 licenses in use)'],     # seats free
    ['Users of Spectre_Basic:  (Total of 4 licenses issued;  Total of 4 licenses in use)'],         # none free
])
def test_a_connection_that_does_not_ask_its_license_server_gets_no_license_answer(settings, lines):
    """The bridge's license check returns only the lines of licenses that are in use at that moment, so uncounted
    licenses, an idle license server and a host without lmstat all read as nothing: the license part was `unknown` at
    every full test, and a real start from the page was refused once, asked whether to go ahead and was then tested in
    full a second time (all 106 full tests of the user's log). A connection may say "license_check": false: the
    license part is then not applicable - not ok, not failed, not unknown - and Spectre itself is still looked for."""
    layers, bridge = check(dict(settings, license_check=False), license=dict(spectre_path='/cad/spectre', licenses=lines))
    assert states(layers)['spectre'] == 'ok' and states(layers)['spectre_license'] == 'not_applicable'
    assert reasons(layers)['spectre_license'] == 'license_not_asked'
    details = layers[-1]['details']
    assert '"license_check": false' in details['note'] and 'features' not in details and 'next_step' not in details
    assert bridge.calls.count('license') == 1                           # the one call that finds Spectre is still made
    assert connection.overall_state(layers, 'full') == 'ok'


def test_a_missing_spectre_is_still_named_when_the_license_server_is_not_asked(settings):
    layers, _ = check(dict(settings, license_check=False), license=dict(spectre_path=None, licenses=[]))
    assert states(layers)['spectre'] == 'failed' and reasons(layers)['spectre'] == 'spectre_not_found'
    assert states(layers)['spectre_license'] == 'not_checked'


@pytest.mark.parametrize('value', [True, None, 'false', 0, 'no'])
def test_only_the_value_false_switches_the_license_question_off(settings, value):
    layers, _ = check(dict(settings, license_check=value), license=dict(spectre_path='/cad/spectre', licenses=[]))
    assert states(layers)['spectre_license'] == 'unknown' and reasons(layers)['spectre_license'] == 'license_not_checkable'
    assert '"license_check": false' in layers[-1]['details']['next_step']       # the next step names the setting


def test_the_license_setting_reaches_the_probe_from_the_connection_file(settings, monkeypatch, capsys):
    write_profiles(lab=dict(settings, license_check=False), asking=dict(settings))
    monkeypatch.setattr(connection, 'RealBridge', FakeBridge(license=dict(spectre_path='/cad/spectre', licenses=[])))
    assert connection._probe_main(['--profile-id', 'lab', '--scope', 'full']) == 0
    assert states(json.loads(capsys.readouterr().out)['layers'])['spectre_license'] == 'not_applicable'
    assert connection._probe_main(['--profile-id', 'asking', '--scope', 'full']) == 0
    assert states(json.loads(capsys.readouterr().out)['layers'])['spectre_license'] == 'unknown'


def test_raw_license_output_and_credentials_never_leave(settings):
    raw = ['Users of Spectre_Basic:  (Total of 4 licenses issued;  Total of 1 licenses in use)',
           '    bob eda-host-17 /dev/pts/3 (v23.1) (licserver/5280 1234), start Fri 9/20 10:01', 'password=hunter2']
    layers, _ = check(settings, license=dict(spectre_path='/cad/spectre', licenses=raw, raw_output='\n'.join(raw)))
    text = json.dumps(layers)
    for secret in ('bob', 'eda-host-17', 'licserver', 'hunter2', 'super-secret-value'):
        assert secret not in text
    assert layers[1]['details']['settings'] == dict(daemon_host='set', spectre_host='set', remote_user='set')
    layers, _ = check(settings, client_error=RuntimeError('ssh://alice:p4ssw0rd@eda-host failed token=abc123'))
    assert 'p4ssw0rd' not in json.dumps(layers) and 'abc123' not in json.dumps(layers)


def test_busy_during_an_active_run_is_not_failed(settings):
    layers, _ = check(settings, run_active=True, client_error=TimeoutError('timed out'))
    assert states(layers)['daemon'] == 'busy' and reasons(layers)['daemon'] == 'busy_active_run'
    layers, _ = check(settings, run_active=False, client_error=TimeoutError('timed out'))
    assert states(layers)['daemon'] == 'failed'


def test_the_probe_only_observes(settings, monkeypatch):
    """No tunnel/daemon start-stop-restart, no adapter connect(), no session lock."""
    from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
    monkeypatch.setattr(VirtuosoBridgeBackend, 'connect', lambda self: pytest.fail('the probe called adapter.connect()'))
    locked = []
    real_flock = fcntl.flock
    monkeypatch.setattr(fcntl, 'flock', lambda *a: locked.append(a) or real_flock(*a))
    layers, bridge = check(settings)
    assert set(states(layers).values()) == {'ok'} and locked == []
    assert not any(word in call for call in bridge.calls for word in ('start', 'stop', 'restart', 'warm', 'deploy'))
    assert bridge.calls[-1] == 'license' and 'close' in bridge.calls                   # only its own client is closed
    facade = {name for name in dir(connection.RealBridge) if not name.startswith('_')}
    assert facade == {'version', 'bind_env', 'resolve_profile', 'roles', 'is_local', 'tunnel_state', 'client', 'skill_ok',
                      'daemon_user', 'readiness', 'license'}
    source = Path(connection.__file__).read_text()
    for forbidden in ('SSHClient.start', '.stop(', 'restart(', 'warm_remote_session', 'ensure_ready', 'session.lock',
                      'virtuoso-bridge", "st', "'status'], ", 'shell=True'):
        assert forbidden not in source, forbidden


def test_status_is_unknown_before_the_first_check_and_when_stale(tmp_path):
    monitor = monitor_for(tmp_path, OK_BODY, stale_after_seconds=0.3)
    first = monitor.status('lab')
    assert first['overall'] == 'unknown' and first['checked_utc'] is None and {i['state'] for i in first['layers']} == {'unknown'}
    assert monitor.check('lab', scope='full')['overall'] == 'ok'
    fresh = monitor.status('lab')
    assert fresh['overall'] == 'ok' and fresh['stale'] is False and fresh['age_seconds'] is not None
    time.sleep(0.4)
    stale = monitor.status('lab')                                           # a cached ok is never shown as current
    assert stale['stale'] and stale['overall'] == 'unknown' and stale['age_seconds'] >= 0.3
    assert {i['state'] for i in stale['layers']} == {'unknown'} and stale['layers'][0]['previous_state'] == 'ok'


def test_concurrent_requests_are_coalesced_into_one_probe(tmp_path):
    counter = tmp_path / 'count'
    body = f"open({str(counter)!r}, 'a').write('x'); time.sleep(0.6); " + OK_BODY
    monitor = monitor_for(tmp_path, body)
    results = []
    threads = [threading.Thread(target=lambda: results.append(monitor.check('lab'))) for _ in range(6)]   # six browser tabs
    [t.start() for t in threads]; [t.join() for t in threads]
    assert counter.read_text() == 'x' and monitor.probes_started == 1 and len(results) == 6
    assert len({r['checked_utc'] for r in results}) == 1


def test_probe_timeout_kills_only_the_probe_and_reports_unknown_or_busy(tmp_path):
    monitor = monitor_for(tmp_path, 'time.sleep(60)', probe_timeout_seconds=0.5)
    result = monitor.check('lab')
    assert result['overall'] == 'unknown' and states(result['layers'])['daemon'] == 'unknown'
    assert reasons(result['layers'])['daemon'] == 'probe_timeout' and result['duration_seconds'] < 10
    busy = monitor_for(tmp_path, 'time.sleep(60)', probe_timeout_seconds=0.5,
                       active_run_lookup=lambda profile: dict(last_successful_evaluation_utc='2026-09-20T10:00:00+00:00'))
    result = busy.check('lab')
    assert states(result['layers'])['daemon'] == 'busy' and result['run_active']
    assert result['last_successful_bridge_interaction_utc'] == '2026-09-20T10:00:00+00:00'
    os.kill(os.getpid(), 0)


def test_unparseable_probe_output_is_unknown_never_ok(tmp_path):
    for body in ("print('Virtuoso Bridge v0.8.0\\n[tunnel] running\\n[daemon] OK')", "print('{not json')",
                 "print(json.dumps(dict(layers=[dict(layer='daemon', state='ok')])))", 'sys.exit(3)'):
        result = monitor_for(tmp_path, body).check('lab')
        assert result['overall'] == 'unknown' and {i['state'] for i in result['layers']} == {'unknown'}, body


def test_browser_may_only_name_a_configured_profile(tmp_path):
    monitor = monitor_for(tmp_path, OK_BODY)
    for hostile in ('eda-host.example.com:65432', '../../etc/passwd', 'lab; rm -rf /', '$(id)', '-p', 'a b', '', None, 7,
                    'x' * 80, 'ssh://host'):
        with pytest.raises(ValueError):
            monitor.check(hostile)
    for unconfigured in ('10.0.0.5', 'not-configured'):                    # well-formed, but not a configured profile
        with pytest.raises(KeyError):
            connection.resolve_profile_id(unconfigured)
    with pytest.raises(ValueError):
        monitor.check('lab', scope='full', trigger='auto')                  # automatic checks: cheap layers only
    assert monitor.check('lab', scope='cheap', trigger='auto')['trigger'] == 'auto'
    command = monitor._command('lab', 'full', False)
    assert isinstance(command, list) and command[-4:] == ['--scope', 'full', '--timeout', '5']   # argv array, no shell


def test_checks_are_logged_in_an_application_log_not_in_research_data(tmp_path):
    monitor = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(tunnel="failed")!r})))')
    monitor.check('lab', trigger='user')
    from gator_workbench.paths import local_settings_dir
    entries = read_jsonl(local_settings_dir() / 'connection_checks.jsonl')
    assert len(entries) == 1
    entry = entries[0]
    assert set(entry) >= {'timestamp_utc', 'profile_id', 'trigger', 'duration_seconds', 'layers'} and entry['trigger'] == 'user'
    assert [l['layer'] for l in entry['layers']] == list(LAYERS)


def test_real_probe_process_reports_the_true_state_of_this_environment(tmp_path):
    """REAL check (no fixture): it runs the actual probe module with the worker interpreter. Without a
    connection file it must say so; it must not pretend anything is ok."""
    result = ConnectionMonitor().check('lab', scope='cheap')
    found, layer_states = reasons(result['layers']), states(result['layers'])
    # Dependency order holds even without a profile: layer 1 is checked first, and exactly ONE link is named.
    assert len(found) == 1 and result['overall'] == 'failed'
    if layer_states['bridge_package'] == 'ok':                      # bridge importable by this interpreter
        assert found == {'connection_profile': 'connection_file_missing'}
    else:                                                           # the development host: bridge lives in another venv
        assert found == {'bridge_package': 'bridge_not_importable'} and layer_states['connection_profile'] == 'not_checked'
    assert layer_states['tunnel'] == layer_states['daemon'] == 'not_checked'
    assert result['cost'] == dict(evaluations_charged=0, spectre_launches=0, note='Zero-cost observation; never a baseline.')


# ------------------------------------------------------------------------------- gate
def test_offline_actions_never_need_the_bridge(tmp_path):
    monitor = monitor_for(tmp_path, 'sys.exit(1)')
    gate = monitor.gate('offline', 'lab')
    assert gate['allowed'] and gate['status'] == 'not_applicable' and monitor.probes_started == 0
    assert connection.ACTION_LAYERS['read_cellview'] == LAYERS[:4] and connection.ACTION_LAYERS['real_simulation'] == LAYERS


def test_gate_blocks_on_failure_and_needs_acknowledgement_for_unknown(tmp_path):
    blocked = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(tunnel="failed", daemon="not_checked")!r})))')
    gate = blocked.gate('real_simulation', 'lab', acknowledge_unknown=True)
    assert not gate['allowed'] and gate['status'] == 'blocked' and gate['blocking'] == ['tunnel']   # ack cannot override a failure
    unknown = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(spectre_license="unknown")!r})))')
    gate = unknown.gate('real_simulation', 'lab')
    assert not gate['allowed'] and gate['status'] == 'needs_acknowledgement' and gate['uncertain'] == ['spectre_license']
    gate = unknown.gate('real_simulation', 'lab', acknowledge_unknown=True)
    assert gate['allowed'] and gate['status'] == 'passed_with_acknowledged_unknown' and gate['acknowledged_unknown']
    ready = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(session_readiness="not_ready")!r})))')
    assert ready.gate('write_cellview', 'lab')['blocking'] == ['session_readiness']
    assert ready.gate('read_cellview', 'lab')['allowed']                    # reading does not need readiness


def test_a_passing_check_seconds_old_serves_the_next_cellview_gate(tmp_path):
    """A Save task, an import or the window's reads gated two or three times within seconds, one probe each (review of
    2026-09-30). One passing probe now serves them for `gate_reuse_seconds`; a real simulation, an older check, a check
    from before a run started, a failed one and a cheap one never serve a gate."""
    monitor = monitor_for(tmp_path, OK_BODY)
    first, second = monitor.gate('write_cellview', 'lab'), monitor.gate('read_cellview', 'lab')
    assert first['allowed'] and not first['check_reused'] and second['allowed'] and second['check_reused']
    assert monitor.probes_started == 1 and second['checked_utc'] == first['checked_utc']      # the reused check's own time
    assert not monitor.gate('real_simulation', 'lab')['check_reused'] and monitor.probes_started == 2   # always afresh
    monitor.gate_reuse_seconds = 0.2
    time.sleep(0.3)
    assert not monitor.gate('write_cellview', 'lab')['check_reused'] and monitor.probes_started == 3   # too old
    monitor.gate_reuse_seconds = 30.0
    assert monitor.gate('write_cellview', 'lab')['check_reused'] and monitor.probes_started == 3
    monitor.active_run_lookup = lambda profile_id: dict(run_id='fixture')                   # a run started since
    assert not monitor.gate('write_cellview', 'lab')['check_reused'] and monitor.probes_started == 4
    failing = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(session_readiness="not_ready")!r})))')
    assert failing.gate('write_cellview', 'lab')['blocking'] == ['session_readiness']
    assert failing.gate('write_cellview', 'lab')['blocking'] == ['session_readiness'] and failing.probes_started == 2
    opened = monitor_for(tmp_path, OK_BODY)
    opened.check('lab', scope='interactive', trigger='user')                                # the page's test when it opens
    assert opened.gate('read_cellview', 'lab')['check_reused'] and opened.probes_started == 1
    cheap = monitor_for(tmp_path, OK_BODY)
    cheap.check('lab', scope='cheap', trigger='auto')                                       # tunnel and package only
    assert not cheap.gate('read_cellview', 'lab')['check_reused'] and cheap.probes_started == 2


def real_task(tmp_path, monkeypatch):
    """A MOCK-evaluated task relabelled as real, to exercise the gate without any real backend."""
    config = make_config(tmp_path, run=dict(max_evaluations=6, connection_profile_id='lab'))
    runtime = tasks.load_task(config.circuit)
    runtime.origin = 'real'
    monkeypatch.setattr(runs, 'load_task', lambda circuit, allow_real=False, profile_id=None: runtime)
    return config


def test_a_blocked_start_creates_nothing_and_charges_nothing(tmp_path, monkeypatch):
    config = real_task(tmp_path, monkeypatch)
    monitor = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(daemon="failed")!r})))')
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=monitor)
    assert error.value.code == 'connection_gate_blocked' and error.value.report['blocking'] == ['daemon']
    after = sorted(p.name for p in tmp_path.iterdir() if p.name not in ('fake_probe.py', '_settings'))
    assert after == [n for n in before if n not in ('fake_probe.py', '_settings')]     # no run dir, no experiment, no mock fallback
    assert runs.list_runs(roots_for(tmp_path), tmp_path) == []
    from gator_workbench.paths import local_settings_dir
    refusal = read_jsonl(local_settings_dir() / 'connection_checks.jsonl')[-1]
    assert refusal['trigger'] == 'gate' and refusal['refusal']['blocking'] == ['daemon']   # refusal logged by the application
    with pytest.raises(runs.RunRejected) as error:                                       # no profile => no fallback profile
        config.run.connection_profile_id = None
        runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=monitor)
    assert error.value.code == 'connection_gate' and 'no fallback' in str(error.value).lower()


def test_gate_result_is_recorded_in_the_manifest(tmp_path, monkeypatch):
    from gator_workbench.storage import read_json
    config = real_task(tmp_path, monkeypatch)
    unknown = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(spectre_license="unknown")!r})))')
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=unknown)
    assert error.value.code == 'connection_gate_acknowledge'
    layout, manifest = runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=unknown, acknowledge_unknown=True)
    gate = read_json(layout.manifest)['connection_gate']
    assert gate['status'] == 'passed_with_acknowledged_unknown' and gate['profile_id'] == 'lab' and gate['checked_utc']
    assert {l['layer']: l['state'] for l in gate['layers']}['spectre_license'] == 'unknown'
    assert 'mock' not in layout.run_dir.parts                               # a real task never lands in the mock root


def test_a_start_is_not_held_up_for_a_license_server_that_is_not_asked(tmp_path, monkeypatch):
    """Record 7.479: an unknown license part needs an acknowledgement before a real run (the test above); a license
    part that is not asked needs none, and the start is tested once."""
    from gator_workbench.storage import read_json
    config = real_task(tmp_path, monkeypatch)
    unasked = monitor_for(tmp_path, f'print(json.dumps(dict(layers={layers_json(spectre_license="not_applicable")!r})))')
    gate = unasked.gate('real_simulation', 'lab')
    assert gate['allowed'] and gate['status'] == 'passed' and gate['uncertain'] == [] and gate['blocking'] == []
    assert not gate['acknowledged_unknown'] and unasked.probes_started == 1
    layout, manifest = runs.prepare_run(config, roots_for(tmp_path), allow_real=True, monitor=unasked)    # no acknowledgement
    recorded = read_json(layout.manifest)['connection_gate']
    assert recorded['status'] == 'passed' and unasked.probes_started == 2
    assert {l['layer']: l['state'] for l in recorded['layers']}['spectre_license'] == 'not_applicable'


def test_mock_runs_record_not_applicable_and_work_while_the_bridge_is_down(tmp_path):
    from gator_workbench.storage import read_json
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=5)), tmp_path)   # no monitor at all
    assert state == 'completed' and read_json(layout.manifest)['connection_gate']['status'] == 'not_applicable'


def test_the_check_costs_no_budget_and_writes_no_research_rows(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=5)), tmp_path)
    before = (summary(layout)['totals'], len(rows(layout, 'evaluations')), len(rows(layout, 'simulator_jobs')))
    monitor = monitor_for(tmp_path, OK_BODY)
    for _ in range(3):
        result = monitor.check('lab', scope='full')
        assert result['cost']['evaluations_charged'] == 0 and result['cost']['spectre_launches'] == 0
    after = (summary(layout)['totals'], len(rows(layout, 'evaluations')), len(rows(layout, 'simulator_jobs')))
    assert before == after


# ------------------------------------------------------------------------------- in-run infrastructure failures
@pytest.mark.parametrize('status, reason, text, expected', [
    ('license_error', None, '', 'license_unavailable'),
    ('backend_error', 'bridge_reported_failure', 'Spectre: license checkout failed for feature X', 'license_unavailable'),
    ('timeout', 'python_timeout', 'daemon gave no response', 'daemon_no_response'),
    ('transport_error', None, '', 'bridge_unreachable'),
    ('backend_error', 'unclassified_bridge_failure', 'ssh: connect to host: Connection refused', 'bridge_unreachable'),
    ('timeout', 'scripted_timeout', '', 'infrastructure_unclassified'),
    ('nonconverged', None, 'license', None), ('invalid_design', None, '', None), ('ok', None, '', None),
])
def test_infrastructure_failures_are_classified_apart_from_circuit_failures(status, reason, text, expected):
    assert connection.classify_infrastructure_failure(status, reason, text) == expected


def test_consecutive_infrastructure_failures_pause_safely_instead_of_burning_budget(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2,
                                                           max_consecutive_infrastructure_failures=3,
                                                           max_consecutive_failures=50))
    script = {n: 'timeout' for n in range(3, 40)}
    layout, state = execute(config, tmp_path, scripts={'0': script, '1': script})
    s = summary(layout)
    assert state == 'paused' and s['stop_reason'] == 'infrastructure_failures'          # distinct stop reason, resumable
    assert s['totals']['candidate_evaluations_charged'] < 15                            # the budget was NOT spent on a dead link
    assert s['output']['resumability'] == 'full_state' and 'gate' in s['error']
    evaluations = sorted(rows(layout, 'evaluations'), key=lambda r: r['commit_seq'])
    while evaluations[-1]['status'] == 'cancelled':       # dispatched just before the pause, which stopped it before its launch
        assert evaluations.pop()['failure_type'] == 'cancelled'
    assert [e['failure_type'] for e in evaluations[-3:]] == ['infrastructure_unclassified'] * 3
    assert all(e['status'] == 'timeout' for e in evaluations[-3:])                     # started => still charged, not refunded
    jobs = [j for j in rows(layout, 'simulator_jobs') if ':' in j['exit_status']]
    assert jobs and all(j['exit_status'] == 'timeout:infrastructure_unclassified' for j in jobs)
    events = [e for e in read_jsonl(layout.logs / 'events.jsonl') if e['event'] == 'connection_check']
    assert events and events[0]['status'] == 'not_applicable'                           # mock run: no bridge to check


def test_circuit_failures_do_not_count_as_infrastructure_failures(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=12, max_consecutive_infrastructure_failures=2,
                                                           max_consecutive_failures=50))
    layout, state = execute(config, tmp_path, scripts={'0': {n: 'invalid_design' for n in range(2, 40, 2)}})
    assert state == 'completed' and summary(layout)['stop_reason'] == 'budget_exhausted'


# ---- the connection gate's run lookup -------------------------------------------------------------------------------
def test_the_gate_asks_for_a_working_run_only_when_a_check_could_be_reused(tmp_path):
    asked = []
    monitor = monitor_for(tmp_path, OK_BODY, active_run_lookup=lambda profile_id: asked.append(profile_id))
    monitor.gate('write_cellview', 'lab')                                     # nothing to reuse: only the probe asks
    assert len(asked) == 1 and monitor.probes_started == 1
    assert monitor.gate('read_cellview', 'lab')['check_reused'] and len(asked) == 2     # reusable: asked once, to compare
    monitor.gate_reuse_seconds = 0.0
    time.sleep(0.05)
    assert not monitor.gate('read_cellview', 'lab')['check_reused']         # too old: not asked for the reuse any more
    assert len(asked) == 3 and monitor.probes_started == 2


def test_one_look_for_a_working_run_serves_the_gate_for_three_seconds(tmp_path, monkeypatch):
    from gator_workbench.api import app as app_module
    looks = []
    monkeypatch.setattr(runs, 'list_runs', lambda roots, *args, **kwargs: looks.append(1) or [])
    lookup = workbench_app(tmp_path).state.monitor.active_run_lookup
    assert lookup('lab') is None and lookup('lab') is None and len(looks) == 1
    assert lookup('other') is None and len(looks) == 2                      # each connection has its own answer
    monkeypatch.setattr(app_module, 'ACTIVE_RUN_REUSE_SECONDS', 0.0)
    assert lookup('lab') is None and len(looks) == 3


# ---- the session lock is asked first (record 7.478) ---------------------------------------------------------------------
SESSIONS_ENV = ('VB_REMOTE_HOST=simhost\nVB_REMOTE_PORT=65001\nVB_LOCAL_PORT=65221\n'
                'VB_REMOTE_HOST_s2=simhost\nVB_REMOTE_PORT_s2=65017\nVB_LOCAL_PORT_s2=65222\n')


def two_sessions(tmp_path):
    """`lab` reaches the first Virtuoso session and `lab2` the second; `sim` is an ngspice connection and `bare` a Virtuoso
    connection without a bridge settings file. Returns the settings file and the two sessions' locks."""
    env = tmp_path / 'sessions.env'
    env.write_text(SESSIONS_ENV)
    write_profiles(lab=dict(env_file=str(env)), lab2=dict(env_file=str(env), kind='virtuoso_ssh', profile='s2', session_group='lab'),
                   sim=dict(kind='ngspice_local'), bare=dict(kind='virtuoso_ssh'))
    first, second = paths.bridge_session_lock(str(env)), paths.bridge_session_lock(str(env), 's2')
    assert first != second
    return env, first, second


def held(lock):
    """`lock` held by this process, as a run holds its session's, until the stream is closed."""
    Path(lock).parent.mkdir(parents=True, exist_ok=True)
    stream = open(lock, 'a+')
    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return stream


def counted_looks(monkeypatch, found=()):
    """Every look at the run list from here on is counted; it finds the runs `found`."""
    looks = []
    monkeypatch.setattr(runs, 'list_runs', lambda roots, *args, **kwargs: looks.append(1) or list(found))
    return looks


def test_a_free_session_lock_answers_for_a_working_run_without_a_look_at_the_runs(tmp_path, monkeypatch):
    """Every connection test, check and gate began with a look at the run list for a run that works on the connection:
    5-10 s on the D: drive once 826 runs were under the output root, for a test of 0.7 s. Every real run holds the lock
    of the Virtuoso session it works in, so a lock that nobody holds answers at once. While it is held the runs are
    looked at, as before; each session has its own lock."""
    _, first, second = two_sessions(tmp_path)
    looks = counted_looks(monkeypatch)
    app = workbench_app(tmp_path)
    lookup = app.state.monitor.active_run_lookup
    assert lookup('lab') is None and lookup('lab2') is None and looks == []        # no lock file: never taken
    first.parent.mkdir(parents=True, exist_ok=True)
    first.touch()
    assert lookup('lab') is None and looks == []                                    # a lock file nobody holds
    stream = held(first)
    try:
        assert lookup('lab') is None and len(looks) == 1                            # held: the look, as before
        assert lookup('lab') is None and len(looks) == 1                            # ... which serves for three seconds
        assert lookup('lab2') is None and len(looks) == 1                           # the second session is free
    finally:
        stream.close()
    assert lookup('lab') is None and len(looks) == 1                                # free again: no look
    stream = held(second)
    try:
        assert lookup('lab') is None and len(looks) == 1 and lookup('lab2') is None and len(looks) == 2
    finally:
        stream.close()
    # The page's own request: a connection test through the API reads no run list either.
    app.state.monitor.probe_command = fake_probe(tmp_path, OK_BODY)
    answer = TestClient(app).post('/api/connection/check', json=dict(profile_id='lab', scope='interactive', trigger='user'))
    assert answer.status_code == 200 and answer.json()['overall'] == 'ok' and answer.json()['run_active'] is False
    assert len(looks) == 2 and app.state.monitor.probes_started == 1


def test_a_held_session_lock_finds_the_run_and_a_free_one_forgets_it(tmp_path, monkeypatch):
    _, first, _ = two_sessions(tmp_path)
    working = dict(worker_alive=True, connection_profile_id='lab', last_successful_evaluation_utc='2026-11-06T00:00:00+00:00')
    looks = counted_looks(monkeypatch, found=[dict(run_dir='a-run')])
    monkeypatch.setattr(runs, 'run_status', lambda run_dir: working)
    app = workbench_app(tmp_path)
    lookup = app.state.monitor.active_run_lookup
    app.state.monitor.probe_command = fake_probe(tmp_path, OK_BODY)
    stream = held(first)
    try:
        assert lookup('lab') == working and len(looks) == 1
        checked = app.state.monitor.check('lab', scope='interactive', trigger='user')
        assert checked['run_active'] is True and checked['last_successful_bridge_interaction_utc'] == working['last_successful_evaluation_utc']
        assert len(looks) == 1                                                      # within the look's three seconds
    finally:
        stream.close()
    # The lock is free within those three seconds: what the look found has ended, and is not answered again.
    assert lookup('lab') is None and len(looks) == 1
    assert app.state.monitor.check('lab', scope='interactive', trigger='user')['run_active'] is False


@pytest.mark.parametrize('profile_id', ['sim', 'bare', 'not-set-up'])
def test_a_connection_with_no_session_lock_to_ask_gets_the_look_at_the_runs(tmp_path, monkeypatch, profile_id):
    """An ngspice run takes no session lock, a Virtuoso connection without a bridge settings file has none that could
    be named, and a name that is not set up has nothing: the runs are looked at, as before."""
    two_sessions(tmp_path)
    looks = counted_looks(monkeypatch)
    assert workbench_app(tmp_path).state.monitor.active_run_lookup(profile_id) is None and len(looks) == 1


def test_where_the_locks_cannot_be_read_the_runs_are_looked_at(tmp_path, monkeypatch):
    from gator_workbench.api import app as app_module
    two_sessions(tmp_path)
    looks = counted_looks(monkeypatch)
    monkeypatch.setattr(app_module, 'ACTIVE_RUN_REUSE_SECONDS', 0.0)
    lookup = workbench_app(tmp_path).state.monitor.active_run_lookup
    monkeypatch.setattr(consistency, 'lock_pids', lambda path: None)                # no /proc/locks: not Linux
    assert lookup('lab') is None and len(looks) == 1
    monkeypatch.setattr(consistency, 'lock_pids', lambda path: 1 / 0)               # the shortcut never fails the check
    assert lookup('lab') is None and len(looks) == 2
    assert app_module.session_idle('lab') is False and app_module.session_idle(None) is False
