"""Explicit "Connect SSH" action, the CIW command text and the plain-language test status, with a FAKE
bridge and a fake connect process. No test opens an SSH connection or contacts a real Virtuoso."""
import json
from pathlib import Path
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_connect, connection
from gator_workbench.bridge_connect import BridgeConnector, ciw_lines, describe, perform_connect, summarize
from gator_workbench.connection import ConnectionMonitor, LAYERS, run_layers
from gator_workbench.storage.atomic import read_jsonl
from helpers import bridge_settings as settings, workbench_app   # noqa: F401 - an imported fixture belongs to this module
from fakes_connection import FakeBridge, FakeTunnel, SETUP


def connect(settings, **behaviour):
    """Run connection setup against a fake tunnel with no settling delay."""
    bridge = FakeTunnel(**behaviour)
    return perform_connect(bridge, settings, settle_seconds=0), bridge


# ------------------------------------------------------------------------------- CIW command text
def test_ciw_lines_are_the_load_command_the_bridge_would_print():
    lines = ciw_lines(SETUP)
    assert lines['load'] == f'load("{SETUP}")' and lines['replace_running_daemon'] == ['RBStop()', f'load("{SETUP}")']
    assert any('/tmp is isolated' in note for note in lines['notes'])                  # only for a /tmp path
    assert not any('/tmp is isolated' in n for n in ciw_lines('/home/alice/vb/virtuoso_setup.il')['notes'])
    assert ciw_lines('/home/a "b"\\c.il')['load'] == 'load("/home/a \\"b\\"\\\\c.il")'   # a valid SKILL string literal
    for unusable in (None, '', 7, '/x\nload("/evil.il")', '/x\r', '/x\x00'):
        assert ciw_lines(unusable) is None


# ------------------------------------------------------------------------------- connect
def test_a_running_tunnel_is_left_untouched(settings):
    outcome, bridge = connect(settings, running=True)
    assert outcome['ok'] and outcome['action'] == 'already_running' and 'start_tunnel' not in bridge.calls
    assert outcome['details']['ciw']['load'] == f'load("{SETUP}")' and outcome['details']['mode'] == 'remote'


def test_a_stopped_tunnel_is_started_once_and_the_ciw_command_is_reported(settings):
    outcome, bridge = connect(settings, running=False)
    assert outcome['ok'] and outcome['action'] == 'started' and bridge.calls.count('start_tunnel') == 1
    assert bridge.calls.index('version') < bridge.calls.index('bind_env') < bridge.calls.index('start_tunnel')
    assert outcome['details']['ciw']['load'] == f'load("{SETUP}")' and outcome['reason_code'] is None


def test_ssh_failure_is_named_redacted_and_tells_the_next_step(settings):
    error = RuntimeError('SSH tunnel failed: Permission denied (publickey) password=hunter2\nsecond line with detail')
    outcome, _ = connect(settings, running=False, start_error=error)
    assert not outcome['ok'] and outcome['action'] == 'failed' and outcome['reason_code'] == 'ssh_failed'
    assert 'Permission denied' in outcome['diagnostic'] and 'hunter2' not in json.dumps(outcome)
    assert 'second line' not in outcome['diagnostic']
    assert 'virtuoso-bridge start -p lab' in outcome['details']['next_step'] and 'ciw' not in outcome['details']


def test_a_tunnel_that_exits_right_away_is_not_reported_as_connected(settings):
    outcome, bridge = connect(settings, running=False, comes_up=False)
    assert not outcome['ok'] and outcome['reason_code'] == 'tunnel_exited' and bridge.calls.count('start_tunnel') == 1


@pytest.mark.parametrize('behaviour, reason', [
    (dict(import_error=True), 'bridge_not_importable'),
    (dict(version='0.9.1'), 'bridge_version_unverified'),
    (dict(resolved='some-other-profile'), 'implicit_profile_binding'),
    (dict(roles=dict(daemon_host=None, spectre_host=None, remote_user='alice')), 'profile_incomplete'),
])
def test_nothing_is_started_unless_the_profile_is_the_one_a_run_would_use(settings, behaviour, reason):
    outcome, bridge = connect(settings, running=False, **behaviour)
    assert not outcome['ok'] and outcome['reason_code'] == reason and 'start_tunnel' not in bridge.calls
    assert outcome['details']['next_step']


def test_missing_env_file_or_unknown_profile_starts_nothing(tmp_path):
    outcome, bridge = connect(dict(env_file=str(tmp_path / 'absent.env'), profile='lab'), running=False)
    assert outcome['reason_code'] == 'env_file_missing' and 'start_tunnel' not in bridge.calls
    bridge = FakeTunnel(running=False)
    outcome = perform_connect(bridge, None, profile_error=('connection_file_missing', 'no file'))
    assert outcome['reason_code'] == 'connection_file_missing' and 'start_tunnel' not in bridge.calls


def test_local_mode_sets_the_bridge_up_without_a_tunnel(settings):
    outcome, bridge = connect(settings, local=True, running=False, state=None, comes_up=True)
    assert bridge.calls.count('start_tunnel') == 1 and outcome['ok'] and outcome['details']['mode'] == 'local'
    assert outcome['reason_code'] == 'setup_path_unknown'                   # this fake saved no state -> no invented path


def test_a_tunnel_without_a_saved_setup_path_gets_no_invented_command(settings):
    outcome, _ = connect(settings, running=True, state=dict(port=65432))
    assert outcome['ok'] and outcome['reason_code'] == 'setup_path_unknown' and 'ciw' not in outcome['details']
    assert 'virtuoso-bridge status -p lab' in outcome['details']['next_step']


def test_connecting_never_stops_or_restarts_anything(settings):
    connect(settings, running=True)
    added = {n for n in dir(bridge_connect.TunnelBridge) if not n.startswith('_')} - \
            {n for n in dir(connection.RealBridge) if not n.startswith('_')}
    assert added == {'start_tunnel'}
    source = Path(bridge_connect.__file__).read_text()
    for forbidden in ('.stop(', 'restart(', 'RBStart', 'execute_skill', 'shell=True', 'cli_load', 'bootstrap'):
        assert forbidden not in source, forbidden             # no stop/restart, no SKILL sent to the CIW, no shell
    assert '.warm(' not in Path(connection.__file__).read_text() and '.warm(' in source      # only HERE can a tunnel start


# ------------------------------------------------------------------------------- connector (process)
def fake_process(tmp_path, body):
    """Write a fixture subprocess program and return the command that runs it."""
    script = tmp_path / 'fake_connect.py'
    script.write_text('import sys, json, time, os\n' + body)
    return [sys.executable, str(script)]


def outcome_json(**overrides):
    """Build a successful connector-process response with the requested overrides."""
    return dict(dict(bridge_connect=True, ok=True, action='started', reason_code=None, diagnostic=None,
                     details=dict(mode='remote', ciw=ciw_lines(SETUP))), **overrides)


def test_connector_reads_the_last_json_line_and_logs_the_action(tmp_path):
    body = f"print('Starting tunnel...'); print('[port] 65432 busy, auto-switched to 65433'); print(json.dumps({outcome_json()!r}))"
    result = BridgeConnector(command=fake_process(tmp_path, body)).connect('lab')
    assert result['ok'] and result['action'] == 'started' and result['profile_id'] == 'lab' and 'bridge_connect' not in result
    assert result['details']['ciw']['load'] == f'load("{SETUP}")' and result['duration_seconds'] >= 0
    from gator_workbench.paths import local_settings_dir
    entries = read_jsonl(local_settings_dir() / 'connection_actions.jsonl')
    assert len(entries) == 1 and entries[0]['action'] == 'started' and entries[0]['trigger'] == 'user'
    assert 'ciw' not in entries[0]                                          # an application log, not a copy of the result


def test_a_double_click_shares_one_attempt(tmp_path):
    counter = tmp_path / 'count'
    body = f"open({str(counter)!r}, 'a').write('x'); time.sleep(0.6); print(json.dumps({outcome_json()!r}))"
    connector, results = BridgeConnector(command=fake_process(tmp_path, body)), []
    threads = [threading.Thread(target=lambda: results.append(connector.connect('lab'))) for _ in range(5)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert counter.read_text() == 'x' and connector.attempts_started == 1 and len(results) == 5


def test_timeout_and_unreadable_output_are_failures_never_success(tmp_path):
    slow = BridgeConnector(command=fake_process(tmp_path, 'time.sleep(60)'), timeout_seconds=0.5).connect('lab')
    assert not slow['ok'] and slow['reason_code'] == 'connect_timeout' and slow['duration_seconds'] < 10
    for body in ("print('Tunnel already running.')", "print('{not json')", "print(json.dumps(dict(ok=True, action='started')))",
                 f"print(json.dumps({outcome_json(action='stopped')!r}))", 'sys.exit(3)'):
        result = BridgeConnector(command=fake_process(tmp_path, body)).connect('lab')
        assert not result['ok'] and result['reason_code'] == 'unparseable_output', body


def test_the_connector_accepts_only_an_identifier_and_uses_no_shell(tmp_path):
    connector = BridgeConnector(command=fake_process(tmp_path, f'print(json.dumps({outcome_json()!r}))'))
    for hostile in ('eda-host.example.com:22', '../../etc/passwd', 'lab; rm -rf /', '$(id)', '-p', 'a b', '', None, 7, 'x' * 80):
        with pytest.raises(ValueError):
            connector.connect(hostile)
    assert connector.attempts_started == 0


def test_the_real_connect_process_starts_nothing_without_a_profile(tmp_path):
    """REAL process (no fixture), no connection file: it must refuse before any SSH call."""
    result = BridgeConnector().connect('lab')
    assert not result['ok'] and result['action'] == 'failed'
    assert result['reason_code'] in ('connection_file_missing', 'bridge_not_importable')


# ------------------------------------------------------------------------------- status sentence
def check_result(scope='interactive', **states):
    """Build scoped connection-check results from the supplied layer outcomes."""
    layers = [dict(layer=n, state=states.get(n, 'ok' if n in dict(cheap=LAYERS[:3], interactive=LAYERS[:5], full=LAYERS)[scope]
                                             else 'not_checked'), reason_code=None, diagnostic=None, details={}) for n in LAYERS]
    return dict(scope=scope, checked_utc='2026-09-20T10:00:00+00:00', stale=False, layers=layers)


def test_the_status_sentence_names_the_broken_link_and_the_next_step(settings):
    assert summarize(dict(checked_utc=None, layers=[]))['headline'] == 'Not tested yet.'
    assert summarize(dict(check_result(), stale=True))['level'] == 'unknown'
    assert summarize(check_result('interactive'))['level'] == 'ok' and 'CIW answered' in summarize(check_result())['headline']
    assert summarize(check_result('full'))['level'] == 'ok'
    cheap = summarize(check_result('cheap'))
    assert cheap['level'] == 'partial' and 'NOT been contacted' in cheap['headline']   # a tunnel alone is not "connected"
    down = summarize(dict(scope='interactive', checked_utc='x', layers=run_layers(FakeBridge(running=False), settings)))
    assert down['level'] == 'error' and down['broken_layer'] == 'tunnel' and 'Connect SSH' in down['headline']
    assert 'Connect SSH' in down['next_step']
    silent = summarize(dict(scope='interactive', checked_utc='x',
                            layers=run_layers(FakeBridge(client_error=ConnectionRefusedError('refused')), settings)))
    assert silent['broken_layer'] == 'daemon' and 'load the command' in silent['headline'] and 'load("...")' in silent['next_step']
    busy = summarize(check_result(daemon='busy') | dict(layers=[dict(l, reason_code='busy_active_run') if l['layer'] == 'daemon'
                                                                else l for l in check_result(daemon='busy')['layers']]))
    assert busy['level'] == 'warn' and 'busy is not failed' in busy['headline']


def test_the_check_reports_the_setup_path_and_describe_turns_it_into_the_command(settings):
    layers = run_layers(FakeBridge(state=dict(port=65432, setup_path=SETUP)), settings, scope='cheap')
    tunnel = next(l for l in layers if l['layer'] == 'tunnel')
    assert tunnel['state'] == 'ok' and tunnel['details']['setup_path'] == SETUP
    shown = describe(dict(scope='cheap', checked_utc='x', layers=layers))
    assert shown['ciw']['load'] == f'load("{SETUP}")' and shown['summary']['level'] == 'partial'
    down = run_layers(FakeBridge(state=dict(port=65432, setup_path=SETUP), running=False), settings, scope='cheap')
    assert describe(dict(checked_utc='x', layers=down))['ciw'] is None      # connect first; a dead tunnel's path is not offered
    local = run_layers(FakeBridge(local=True, state=dict(mode='local', port=1, setup_path='/home/a/setup.il')), settings, scope='cheap')
    assert describe(dict(checked_utc='x', layers=local))['ciw']['load'] == 'load("/home/a/setup.il")'


# ------------------------------------------------------------------------------- profile creation
@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Provide a temporary home and bridge metadata without using the real bridge installation."""
    home = tmp_path / 'home'
    (home / '.virtuoso-bridge').mkdir(parents=True)
    (home / '.virtuoso-bridge' / '.env').write_text('VB_REMOTE_HOST=eda-host\nVB_PASSWORD=super-secret-value\n')
    site = home / 'virtuoso-bridge-lite' / '.venv' / 'lib' / 'python3.10' / 'site-packages'
    (site / 'virtuoso_bridge-0.8.0.dist-info').mkdir(parents=True)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(bridge_connect, '_bridge_importable', lambda: False)               # bridge lives in another venv
    return home, site


def test_a_profile_is_created_from_what_is_on_this_host_and_never_overwritten(fake_home):
    home, site = fake_home
    found = bridge_connect.detect_setup()
    assert found['can_create'] and found['env_file_exists'] and found['bridge_site_packages'] == str(site)
    assert 'super-secret-value' not in json.dumps(found) and 'eda-host' not in json.dumps(found)   # located, never read
    created = bridge_connect.create_profile('lab')
    assert created['created'] and created['settings_present'] == ['bridge_site_packages', 'env_file', 'kind', 'profile']
    assert created['backup'] is None                                         # there was no file to keep a copy of
    assert connection.resolve_profile_id('lab') == dict(kind='virtuoso_ssh', env_file=str(home / '.virtuoso-bridge' / '.env'),
                                                        profile=None, bridge_site_packages=str(site))
    assert connection.load_profiles()['active'] == 'lab'
    # An EXISTING connection is operator-owned and is never changed from the browser (the kinds of 2026-09-21 made
    # adding a second one possible; that is pinned in test_wb_connection_kinds.py).
    before = connection.connection_file().read_text()
    with pytest.raises(FileExistsError):
        bridge_connect.create_profile('lab')
    with pytest.raises(bridge_connect.ProfileExists):
        bridge_connect.create_profile('lab', kind='ngspice_local')
    assert connection.connection_file().read_text() == before


def test_profile_creation_refuses_bad_names_and_a_missing_setup(fake_home, tmp_path):
    for hostile in ('eda-host:22', '../x', 'a b', '', None, '$(id)'):
        with pytest.raises(ValueError):
            bridge_connect.create_profile(hostile)
    with pytest.raises(bridge_connect.SetupNotFound) as raised:
        bridge_connect.create_profile('lab', home=tmp_path / 'empty-home')
    assert raised.value.reason_code == 'env_file_missing' and not connection.connection_file().exists()


# ------------------------------------------------------------------------------- API
def api(tmp_path, connector_body=None, **probe_states):
    """Provide an API client backed by fixture probe and connector subprocesses."""
    layers = [dict(layer=n, state=probe_states.get(n, 'ok'), reason_code=None, diagnostic=None,
                   details=dict(setup_path=SETUP) if n == 'tunnel' else {}) for n in LAYERS]
    script = tmp_path / 'probe.py'
    script.write_text(f'import json\nprint(json.dumps(dict(layers={layers!r})))\n')
    connector = BridgeConnector(command=fake_process(tmp_path, connector_body or f'print(json.dumps({outcome_json()!r}))'))
    app = workbench_app(tmp_path, monitor=ConnectionMonitor(probe_command=[sys.executable, str(script)]), connector=connector)
    return TestClient(app), connector


def test_api_create_profile_connect_and_test(fake_home, tmp_path):
    http, connector = api(tmp_path)
    assert http.get('/api/connection/setup').json()['can_create'] is True
    assert http.post('/api/connection/connect', json=dict(profile_id='lab')).status_code == 404       # not configured yet
    created = http.post('/api/connection/profile', json=dict(profile_id='lab')).json()
    assert created['created'] and [p['profile_id'] for p in created['profiles']['profiles']] == ['lab']
    again = http.post('/api/connection/profile', json=dict(profile_id='lab'))
    assert again.status_code == 409 and again.json()['detail']['code'] == 'profile_exists'
    connected = http.post('/api/connection/connect', json=dict(profile_id='lab')).json()
    assert connected['connect']['ok'] and connected['connect']['details']['ciw']['load'] == f'load("{SETUP}")'
    assert connected['status']['scope'] == 'cheap' and connected['status']['summary']['level'] == 'partial'
    assert connector.attempts_started == 1
    tested = http.post('/api/connection/check', json=dict(profile_id='lab', scope='interactive')).json()
    assert tested['summary']['level'] == 'ok' and tested['ciw']['load'] == f'load("{SETUP}")'
    assert http.get('/api/connection/status', params=dict(profile_id='lab')).json()['summary']['headline'] == tested['summary']['headline']


def test_api_connect_takes_an_identifier_and_nothing_else(fake_home, tmp_path):
    http, connector = api(tmp_path)
    http.post('/api/connection/profile', json=dict(profile_id='lab'))
    for body in (dict(profile_id='lab', host='10.0.0.1'), dict(profile_id='lab', port=22), dict(profile_id='lab', command='id'),
                 dict(profile_id='10.0.0.1:22'), dict(profile_id='../x'), dict(profile_id='lab', env_file='/tmp/evil.env'), {}):
        assert http.post('/api/connection/connect', json=body).status_code == 422, body
        assert http.post('/api/connection/profile', json=body).status_code == 422, body
    assert connector.attempts_started == 0


def test_api_reports_a_failed_connect_without_pretending(fake_home, tmp_path):
    failed = dict(bridge_connect=True, ok=False, action='failed', reason_code='ssh_failed', diagnostic='RuntimeError: denied',
                  details=dict(next_step='verify ssh'))
    http, _ = api(tmp_path, connector_body=f'print(json.dumps({failed!r}))', tunnel='failed', daemon='not_checked',
                  session_readiness='not_checked', spectre='not_checked', spectre_license='not_checked')
    http.post('/api/connection/profile', json=dict(profile_id='lab'))
    answer = http.post('/api/connection/connect', json=dict(profile_id='lab')).json()
    assert not answer['connect']['ok'] and answer['connect']['reason_code'] == 'ssh_failed'
    assert answer['status']['overall'] == 'failed' and answer['status']['summary']['broken_layer'] == 'tunnel'
