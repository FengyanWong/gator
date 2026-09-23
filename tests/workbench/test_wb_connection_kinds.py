"""Connection KINDS (2026-09-21): Virtuoso over SSH / on this machine, ngspice on this machine / over SSH.

Everything here runs against FAKE bridges, FAKE runners and a fake probe process, except the two tests marked
REAL, which launch what is actually on this host (`sh`, and `ngspice` only if it is installed). No test opens
an SSH connection, contacts Virtuoso or uses the network."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_connect, connection, ngspice_link, tasks
from gator_workbench.api.app import create_app
from gator_workbench.bridge_connect import BridgeConnector, describe, perform_connect, summarize
from gator_workbench.connection import ConnectionMonitor, LAYERS, NGSPICE_LAYERS, run_layers
from gator_workbench.storage.atomic import read_json, read_jsonl, write_json
from helpers import bridge_settings as settings  # noqa: F401 - an imported fixture belongs to this module
from test_wb_bridge_connect import FakeTunnel
from test_wb_connection import FakeBridge, reasons, states

VERSION_TEXT = '******\n** ngspice-36 : Circuit level simulation program\n** The U. C. Berkeley CAD Group\n******\n'
SOLVED = 'Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n\nNo. of Data Rows : 1\nv(out) = 5.000000e-01\nngspice-36 done\n'


def write_profiles(**profiles):
    write_json(connection.connection_file(), dict(active=next(iter(profiles)), profiles=profiles))


# ------------------------------------------------------------------------------- kinds of a profile
def test_a_profile_without_a_kind_is_virtuoso_over_ssh_and_the_browser_sees_kinds_not_hosts(tmp_path):
    write_profiles(lab=dict(env_file='/x/.env', profile=None, library='GATOR_TESTS'),
                   here=dict(kind='virtuoso_local', env_file='/x/.env'),
                   sim=dict(kind='ngspice_local'),
                   far=dict(kind='ngspice_ssh', ssh_host='alice@sim-host.example.com', ngspice_bin='/opt/ngspice/bin/ngspice'),
                   odd=dict(kind='hspice_cloud'))
    shown = connection.public_profiles()
    by_id = {p['profile_id']: p for p in shown['profiles']}
    assert (by_id['lab']['kind'], by_id['lab']['kind_declared'], by_id['lab']['transport']) == ('virtuoso_ssh', False, 'ssh')
    assert (by_id['here']['family'], by_id['here']['transport']) == ('virtuoso', 'local')
    assert (by_id['sim']['family'], by_id['sim']['transport']) == ('ngspice', 'local')
    assert (by_id['far']['family'], by_id['far']['transport'], by_id['far']['kind_label']) == ('ngspice', 'ssh', 'ngspice over SSH')
    assert by_id['odd']['kind'] is None and 'unknown kind' in by_id['odd']['kind_label']       # shown, never guessed
    assert [k['kind'] for k in shown['kinds']] == ['virtuoso_ssh', 'virtuoso_local', 'ngspice_local', 'ngspice_ssh']
    text = json.dumps(shown)
    assert 'sim-host' not in text and 'alice' not in text and '/opt/ngspice' not in text      # presence flags only
    assert by_id['far']['settings_present'] == ['kind', 'ngspice_bin', 'ssh_host']


@pytest.mark.parametrize('kind, local, reason', [
    ('virtuoso_ssh', False, None), ('virtuoso_local', True, None), (None, True, None), (None, False, None),
    ('virtuoso_local', False, 'kind_mismatch'), ('virtuoso_ssh', True, 'kind_mismatch'),
    ('virtuosso_ssh', False, 'unknown_kind'), ('ngspice_local', False, 'unknown_kind'),
])
def test_a_declared_virtuoso_kind_must_agree_with_the_bridge_env_file(settings, kind, local, reason):
    declared = dict(settings, **({} if kind is None else dict(kind=kind)))
    state = dict(mode='local', port=1, setup_path='/home/a/setup.il') if local else dict(port=65432)
    layers = run_layers(FakeBridge(local=local, state=state), declared, scope='interactive')
    if reason is None:
        assert states(layers)['connection_profile'] == 'ok' and states(layers)['daemon'] == 'ok'
        assert states(layers)['tunnel'] == ('not_applicable' if local else 'ok')
        return
    assert reasons(layers) == {'connection_profile': reason} and states(layers)['tunnel'] == 'not_checked'
    broken = layers[1]
    assert 'bridge_connection.json' in broken['details']['next_step'] and 'eda-host' not in json.dumps(layers)


def test_this_machine_never_opens_a_tunnel_to_another_one(settings):
    """The connect step refuses a kind that disagrees with the env file BEFORE anything is started."""
    bridge = FakeTunnel(local=False, running=False)
    outcome = perform_connect(bridge, dict(settings, kind='virtuoso_local'), settle_seconds=0)
    assert not outcome['ok'] and outcome['reason_code'] == 'kind_mismatch' and 'start_tunnel' not in bridge.calls
    assert 'nothing was started' in outcome['details']['next_step']
    bridge = FakeTunnel(local=True, running=False, state=None, comes_up=True)
    outcome = perform_connect(bridge, dict(settings, kind='virtuoso_local'), settle_seconds=0)
    assert outcome['ok'] and outcome['details']['mode'] == 'local' and bridge.calls.count('start_tunnel') == 1


def test_virtuoso_on_this_machine_is_worded_without_ssh(settings):
    local = dict(settings, kind='virtuoso_local')
    up = dict(mode='local', port=1, setup_path='/home/a/setup.il')
    cheap = describe(dict(kind='virtuoso_local', scope='cheap', checked_utc='x', layers=run_layers(FakeBridge(local=True, state=up), local, scope='cheap')))
    assert cheap['transport'] == 'local' and cheap['family'] == 'virtuoso' and cheap['kind_label'] == 'Virtuoso on this machine'
    assert 'needs no SSH tunnel' in cheap['summary']['headline'] and cheap['ciw']['load'] == 'load("/home/a/setup.il")'
    never = summarize(dict(kind='virtuoso_local', scope='interactive', checked_utc='x',
                           layers=run_layers(FakeBridge(local=True, state=None, running=False), local)))
    assert never['reason_code'] == 'local_bridge_not_set_up' and 'Set up local bridge' in never['headline']
    assert 'SSH' not in never['headline'] and 'Set up local bridge' in never['next_step']
    silent = summarize(dict(kind='virtuoso_local', scope='interactive', checked_utc='x',
                            layers=run_layers(FakeBridge(local=True, state=up, client_error=ConnectionRefusedError('refused')), local)))
    assert silent['broken_layer'] == 'daemon' and 'SSH' not in silent['headline'] and 'load the command' in silent['headline']
    ok = summarize(dict(kind='virtuoso_local', scope='interactive', checked_utc='x', layers=run_layers(FakeBridge(local=True, state=up), local)))
    assert ok['level'] == 'ok' and 'on this machine' in ok['headline']
    # A profile written before kinds existed is not second-guessed, and what the test FOUND decides the wording.
    legacy = describe(dict(kind='virtuoso_ssh', scope='interactive', checked_utc='x', layers=run_layers(FakeBridge(local=True, state=up), settings)))
    assert legacy['transport'] == 'local' and 'on this machine' in legacy['summary']['headline']


# ------------------------------------------------------------------------------- ngspice layers (fake runner)
class FakeRunner:
    """Scripted answers per step; records every argv. `ssh`, `version`, `trial` = (returncode, stdout, stderr),
    an exception instance to raise, or None = the call must not happen."""
    def __init__(self, programs=('ngspice', 'ssh'), ssh=(0, '', ''), version=(0, VERSION_TEXT, ''), trial=(0, SOLVED, '')):
        self.programs, self.answers, self.calls = set(programs), dict(ssh=ssh, version=version, trial=trial), []

    def which(self, program):
        return f'/usr/bin/{Path(program).name}' if Path(program).name in self.programs or program in self.programs else None

    def run(self, argv, *, timeout, stdin_text=None, cwd=None):
        self.calls.append(dict(argv=list(argv), stdin=stdin_text, timeout=timeout))
        command = argv[-1]
        step = 'ssh' if command == 'true' else 'version' if command.endswith('--version') else 'trial'
        answer = self.answers[step]
        assert answer is not None, f'unexpected call: {argv}'
        if isinstance(answer, BaseException):
            raise answer
        return answer


LOCAL = dict(kind='ngspice_local')
REMOTE = dict(kind='ngspice_ssh', ssh_host='alice@sim-host.example.com')


def test_ngspice_on_this_machine_all_layers_in_dependency_order():
    runner = FakeRunner()
    layers = ngspice_link.run_layers(runner, LOCAL)
    assert [item['layer'] for item in layers] == list(NGSPICE_LAYERS)
    assert states(layers) == dict(connection_profile='ok', ssh='not_applicable', ngspice='ok', trial_run='ok')
    assert layers[2]['details'] == dict(version='36', program='/usr/bin/ngspice')
    assert [c['argv'][1:] for c in runner.calls[:1]] == [['--version']] and runner.calls[1]['argv'][1] == '-b'
    assert len(runner.calls) == 2 and not any(c['argv'][0] == 'ssh' for c in runner.calls)      # ONE version call, ONE trial run
    deck = Path(runner.calls[1]['argv'][2])
    assert deck.name == 'divider.cir' and not deck.exists() and not deck.parent.exists()          # its folder went with the check
    shown = describe(dict(kind='ngspice_local', scope='interactive', checked_utc='x', layers=layers))
    assert shown['summary']['level'] == 'ok' and 'ngspice 36 on this machine' in shown['summary']['headline']
    assert shown['ciw'] is None and shown['transport'] == 'local' and shown['family'] == 'ngspice'


def test_ngspice_over_ssh_uses_batch_mode_argv_arrays_and_never_shows_the_host():
    runner = FakeRunner()
    layers = ngspice_link.run_layers(runner, dict(REMOTE, ngspice_bin='/opt/ngspice/bin/ngspice'))
    assert set(states(layers).values()) == {'ok'} and len(runner.calls) == 3
    for call in runner.calls:
        argv = call['argv']
        assert argv[:6] == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '--'] and argv[6] == REMOTE['ssh_host'] and len(argv) == 8
    assert [c['argv'][7] for c in runner.calls[:2]] == ['true', '/opt/ngspice/bin/ngspice --version']
    trial = runner.calls[2]
    assert trial['stdin'] == ngspice_link.DECK and 'mktemp' in trial['argv'][7] and 'rm -f "$deck"' in trial['argv'][7]
    text = json.dumps(describe(dict(kind='ngspice_ssh', scope='interactive', checked_utc='x', layers=layers)))
    assert 'sim-host' not in text and 'alice' not in text
    assert 'SSH works, and ngspice 36 on the remote machine' in text


@pytest.mark.parametrize('settings_, runner, layer_name, state, reason, step_mentions', [
    (LOCAL, dict(programs=('ssh',)), 'ngspice', 'failed', 'ngspice_not_found', 'sudo apt install ngspice'),
    (LOCAL, dict(version=(0, 'GNU bash, version 5.1', '')), 'ngspice', 'unknown', 'ngspice_version_unreadable', 'ngspice_bin'),
    (LOCAL, dict(version=subprocess.TimeoutExpired('ngspice', 15)), 'ngspice', 'unknown', 'probe_timeout', 'try again'),
    (LOCAL, dict(trial=(1, 'Error: circuit not parsed.', 'libngspice.so: cannot open shared object file')), 'trial_run', 'failed', 'trial_run_failed', 'shared libraries'),
    (LOCAL, dict(trial=(0, SOLVED.replace('5.000000e-01', '4.200000e-01'), '')), 'trial_run', 'failed', 'trial_run_failed', 'test circuit'),
    (REMOTE, dict(programs=('ngspice',)), 'ssh', 'failed', 'ssh_client_missing', 'OpenSSH'),
    (REMOTE, dict(ssh=(255, '', 'alice@sim-host.example.com: Permission denied (publickey).')), 'ssh', 'failed', 'ssh_failed', 'key-based login'),
    (REMOTE, dict(ssh=subprocess.TimeoutExpired('ssh', 14)), 'ssh', 'unknown', 'probe_timeout', 'try again'),
    (REMOTE, dict(version=(127, '', 'bash: ngspice: command not found')), 'ngspice', 'failed', 'ngspice_not_found', 'full path of the program there'),
    (REMOTE, dict(version=(255, '', 'Connection to sim-host.example.com closed.')), 'ngspice', 'unknown', 'ssh_failed', 'key-based login'),
])
def test_each_broken_ngspice_link_is_named_and_everything_downstream_is_not_checked(settings_, runner, layer_name, state, reason, step_mentions):
    layers = ngspice_link.run_layers(FakeRunner(**runner), settings_)
    index = NGSPICE_LAYERS.index(layer_name)
    assert (layers[index]['state'], layers[index]['reason_code']) == (state, reason), layers[index]
    assert all(item['state'] in ('ok', 'not_applicable') for item in layers[:index])
    assert all(item['state'] == 'not_checked' for item in layers[index + 1:])
    assert step_mentions in layers[index]['details']['next_step']
    assert 'sim-host' not in json.dumps(layers) and 'alice' not in json.dumps(layers)            # ssh names the host in its errors
    headline = summarize(dict(kind=settings_['kind'], scope='interactive', checked_utc='x', layers=layers))
    assert headline['broken_layer'] == layer_name and headline['level'] == ('error' if state == 'failed' else 'unknown')


@pytest.mark.parametrize('bad', [
    dict(kind='ngspice_ssh'),                                                     # no host at all
    dict(kind='ngspice_ssh', ssh_host='-oProxyCommand=touch /tmp/pwned'),          # an ssh OPTION instead of a host
    dict(kind='ngspice_ssh', ssh_host='sim host'), dict(kind='ngspice_ssh', ssh_host='host;id'),
    dict(kind='ngspice_ssh', ssh_host='$(id)@host'), dict(kind='ngspice_ssh', ssh_host=['sim-host']),
    dict(kind='ngspice_local', ngspice_bin='ngspice; rm -rf ~'), dict(kind='ngspice_local', ngspice_bin='-b'),
    dict(kind='ngspice_local', ngspice_bin='$(id)'), dict(kind='ngspice_ssh', ssh_host='sim-host', ngspice_bin='ngspice && id'),
    dict(kind='virtuoso_ssh'), dict(),
])
def test_a_setting_that_is_not_a_plain_name_stops_the_check_before_anything_runs(bad):
    runner = FakeRunner(ssh=None, version=None, trial=None)
    layers = ngspice_link.run_layers(runner, bad)
    assert states(layers)['connection_profile'] == 'failed' and runner.calls == []
    assert reasons(layers)['connection_profile'] in ('invalid_setting', 'profile_incomplete', 'unknown_kind')
    assert 'pwned' not in json.dumps(layers) and 'rm -rf' not in json.dumps(layers)               # a bad value is never echoed


def test_the_cheap_scope_contacts_nothing():
    runner = FakeRunner(ssh=None, version=None, trial=None)
    layers = ngspice_link.run_layers(runner, REMOTE, scope='cheap')
    assert states(layers) == dict(connection_profile='ok', ssh='not_checked', ngspice='not_checked', trial_run='not_checked')
    assert runner.calls == [] and connection.overall_state(layers, 'cheap', 'ngspice') == 'ok'
    assert summarize(dict(kind='ngspice_ssh', scope='cheap', checked_utc='x', layers=layers))['level'] == 'partial'


def test_the_ngspice_check_launches_nothing_that_survives_it_and_uses_no_shell():
    source = Path(ngspice_link.__file__).read_text()
    for forbidden in ('shell=True', 'Popen(', 'start_new_session', 'os.system', 'nohup', 'ControlMaster', 'ControlPersist'):
        assert forbidden not in source, forbidden
    assert {name for name in dir(ngspice_link.RealRunner) if not name.startswith('_')} == {'which', 'run'}
    assert ngspice_link.ssh_argv('sim-host', 'true')[-3:] == ['--', 'sim-host', 'true']            # `--` ends ssh's own options


def test_REAL_remote_command_line_runs_under_sh_and_leaves_no_file_behind(tmp_path):
    """REAL `sh`, fake ngspice: the remote command is executed as the remote shell would, minus the network."""
    fake = tmp_path / 'ngspice'
    fake.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "** ngspice-99 : fake"; exit 0; fi\n'
                    f'[ "$1" = "-b" ] && grep -q "^r2 out 0 1k" "$2" && echo "$2" > {tmp_path}/deck-seen && echo "v(out) = 5.000000e-01"\n')
    fake.chmod(0o755)

    class ShellInsteadOfSsh(ngspice_link.RealRunner):
        def run(self, argv, **kwargs):
            assert argv[0] == 'ssh' and argv[-3] == '--'
            return super().run(['sh', '-c', argv[-1]], **kwargs)
    layers = ngspice_link.run_layers(ShellInsteadOfSsh(), dict(kind='ngspice_ssh', ssh_host='sim-host', ngspice_bin=str(fake)))
    assert set(states(layers).values()) == {'ok'} and layers[2]['details']['version'] == '99'
    deck = Path((tmp_path / 'deck-seen').read_text().strip())
    assert deck.is_absolute() and not deck.exists()                                              # mktemp'ed, used, removed


def test_REAL_probe_of_ngspice_on_this_host_reports_what_is_really_here(tmp_path):
    """REAL check through the real probe process: whatever this host has, the answer must be the truth about it."""
    import shutil
    write_profiles(sim=dict(kind='ngspice_local'))
    result = ConnectionMonitor().check('sim', scope='interactive')
    assert result['kind'] == 'ngspice_local' and [item['layer'] for item in result['layers']] == list(NGSPICE_LAYERS)
    if shutil.which('ngspice'):
        assert result['overall'] == 'ok' and states(result['layers'])['trial_run'] == 'ok'
    else:
        assert result['overall'] == 'failed' and reasons(result['layers']) == {'ssh': 'local_mode', 'ngspice': 'ngspice_not_found'}
    assert result['cost'] == dict(evaluations_charged=0, spectre_launches=0, note='Zero-cost observation; never a baseline.')


# ------------------------------------------------------------------------------- monitor and gate, per family
def ngspice_probe(tmp_path, **overrides):
    layers = [dict(layer=n, state=overrides.get(n, 'ok'), reason_code=None, diagnostic=None, details={}) for n in NGSPICE_LAYERS]
    script = tmp_path / 'fake_ngspice_probe.py'
    script.write_text(f'import json\nprint(json.dumps(dict(layers={layers!r})))\n')
    return [sys.executable, str(script)]


def test_the_monitor_expects_the_layers_of_the_profiles_own_family(tmp_path):
    write_profiles(sim=dict(kind='ngspice_local'), lab=dict(env_file='/x/.env'))
    monitor = ConnectionMonitor(probe_command=ngspice_probe(tmp_path))
    never = monitor.status('sim')
    assert never['kind'] == 'ngspice_local' and [i['layer'] for i in never['layers']] == list(NGSPICE_LAYERS)
    assert [i['layer'] for i in monitor.status('lab')['layers']] == list(LAYERS)
    tested = monitor.check('sim')
    assert tested['overall'] == 'ok' and tested['kind'] == 'ngspice_local'
    wrong_family = monitor.check('lab')                                   # ngspice layers for a Virtuoso profile: not an answer
    assert wrong_family['overall'] == 'unknown' and {i['reason_code'] for i in wrong_family['layers']} == {'unparseable_probe_output'}
    assert [i['layer'] for i in wrong_family['layers']] == list(LAYERS)
    slow = ConnectionMonitor(probe_command=[sys.executable, '-c', 'import time; time.sleep(60)'], probe_timeout_seconds=0.5,
                             active_run_lookup=lambda profile: dict(last_successful_evaluation_utc=None))
    timed_out = slow.check('sim')
    assert reasons(timed_out['layers']) == {'ngspice': 'probe_timeout'} and states(timed_out['layers'])['ngspice'] == 'unknown'
    write_profiles(sim=dict(env_file='/x/.env'))                          # rewritten as a Virtuoso profile: the old result is not its
    assert monitor.status('sim')['checked_utc'] is None and [i['layer'] for i in monitor.status('sim')['layers']] == list(LAYERS)


def test_an_unknown_kind_is_named_by_the_real_probe_and_nothing_is_probed(tmp_path):
    write_profiles(odd=dict(kind='hspice_cloud', env_file='/x/.env'))
    result = ConnectionMonitor().check('odd', scope='full')               # the REAL probe process
    assert reasons(result['layers']) == {'connection_profile': 'unknown_kind'} and result['overall'] == 'failed'
    assert states(result['layers'])['bridge_package'] == 'not_checked'     # which chain applies is itself unknown
    assert 'ngspice_local' in result['layers'][1]['details']['next_step']


def test_the_gate_refuses_what_a_kind_cannot_serve_without_probing(tmp_path):
    write_profiles(sim=dict(kind='ngspice_local'), lab=dict(env_file='/x/.env'))
    monitor = ConnectionMonitor(probe_command=ngspice_probe(tmp_path))
    for action, word in (('read_cellview', 'Reading a Virtuoso library'), ('write_cellview', 'Virtuoso cell'),
                         ('real_simulation', 'not built yet')):
        gate = monitor.gate(action, 'sim', acknowledge_unknown=True)
        assert not gate['allowed'] and gate['status'] == 'blocked' and gate['blocking'] == ['connection_kind']
        assert gate['connection_kind'] == 'ngspice_local' and word in gate['next_steps'][0]
    assert monitor.probes_started == 0                                     # no test could change the answer
    assert monitor.gate('offline', 'sim')['allowed']
    refusals = [e for e in read_jsonl(connection.connection_file().parent / 'connection_checks.jsonl') if e.get('refusal')]
    assert len(refusals) == 3 and refusals[0]['refusal']['blocking'] == ['connection_kind']
    with pytest.raises(KeyError):
        monitor.gate('teleport', 'sim')
    with pytest.raises(ValueError):
        monitor.gate('read_cellview', 'sim; id')


def test_a_real_circuit_names_a_connection_of_the_wrong_kind_instead_of_missing_settings(tmp_path):
    write_profiles(sim=dict(kind='ngspice_ssh', ssh_host='sim-host'))
    for blocker in (tasks.real_backend_blocker('sim', 'gpdk045_ota5'), tasks.generated_backend_blocker('sim'),
                    tasks.real_backend_blocker(None, 'gpdk045_ota5')):      # None = the active profile
        assert 'ngspice over SSH' in blocker and 'Virtuoso connection' in blocker and 'env_file' not in blocker
        assert 'sim-host' not in blocker


# ------------------------------------------------------------------------------- creating connections
@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    (home / '.virtuoso-bridge').mkdir(parents=True)
    (home / '.virtuoso-bridge' / '.env').write_text('VB_REMOTE_HOST=eda-host\nVB_PASSWORD=super-secret-value\n')
    (home / '.ssh').mkdir()
    (home / '.ssh' / 'config').write_text('# comment\nHost simhost sim2\n  HostName 10.1.2.3\n  User alice\n  IdentityFile ~/.ssh/id_secret\n'
                                          'Host *.example.com !bad ?x\n  User bob\nhost=lower-case-keyword\nHost *\n  ServerAliveInterval 30\n')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(bridge_connect, '_bridge_importable', lambda: True)
    return home


def test_setup_detection_names_machines_and_programs_but_reads_no_address(fake_home):
    assert ngspice_link.ssh_config_hosts() == ['simhost', 'sim2', 'lower-case-keyword']            # no patterns, no `*`
    found = bridge_connect.detect_setup()
    by_kind = {item['kind']: item for item in found['kinds']}
    assert list(by_kind) == ['virtuoso_ssh', 'virtuoso_local', 'ngspice_local', 'ngspice_ssh']
    assert by_kind['ngspice_ssh']['ssh_hosts'] == ['simhost', 'sim2', 'lower-case-keyword'] and by_kind['ngspice_local']['can_create']
    assert 'localhost' in by_kind['virtuoso_local']['note']
    text = json.dumps(found)
    for secret in ('10.1.2.3', 'alice', 'id_secret', 'eda-host', 'super-secret-value', 'bob'):
        assert secret not in text, secret
    assert ngspice_link.ssh_config_hosts(fake_home / 'nowhere') == []


def test_a_connection_is_added_next_to_the_existing_ones_which_are_never_changed(fake_home):
    original = dict(active='lab', note_to_self='keep me', profiles=dict(lab=dict(
        env_file='/x/.env', profile=None, library='GATOR_TESTS', model_file='/pdk/gpdk045.scs',
        circuits=dict(gpdk045_ota5=dict(creation_receipt='/r/ota5.json', reference_measurements='/r/ota5-ref.json')))))
    write_json(connection.connection_file(), original)
    before = connection.connection_file().read_text()
    made = bridge_connect.create_profile('sim', kind='ngspice_local')
    assert made['kind'] == 'ngspice_local' and made['settings_present'] == ['kind'] and 'not built yet' in made['note']
    assert Path(made['backup']).read_text() == before                                             # the previous file, kept
    far = bridge_connect.create_profile('far', kind='ngspice_ssh', ssh_host='simhost')
    here = bridge_connect.create_profile('here', kind='virtuoso_local', bridge_profile='local_vm')
    now = read_json(connection.connection_file())
    assert now['profiles']['lab'] == original['profiles']['lab'] and now['active'] == 'lab' and now['note_to_self'] == 'keep me'
    assert list(now['profiles']) == ['lab', 'sim', 'far', 'here']
    assert now['profiles']['sim'] == dict(kind='ngspice_local') and now['profiles']['far'] == dict(kind='ngspice_ssh', ssh_host='simhost')
    assert now['profiles']['here'] == dict(kind='virtuoso_local', env_file=str(fake_home / '.virtuoso-bridge' / '.env'), profile='local_vm')
    assert far['backup'] != made['backup'] != here['backup']
    for again in ('lab', 'sim'):
        with pytest.raises(bridge_connect.ProfileExists):
            bridge_connect.create_profile(again, kind='ngspice_local')
    assert read_json(connection.connection_file()) == now


def test_creation_takes_names_only_and_never_replaces_a_file_it_cannot_read(fake_home):
    for kwargs in (dict(kind='ngspice_ssh'), dict(kind='ngspice_ssh', ssh_host='10.9.9.9'), dict(kind='ngspice_ssh', ssh_host='not-in-config'),
                   dict(kind='ngspice_ssh', ssh_host='*')):
        with pytest.raises((ValueError, bridge_connect.SetupNotFound)):
            bridge_connect.create_profile('far', **kwargs)
    for kwargs in (dict(kind='ngspice_local', ssh_host='simhost'), dict(kind='ngspice_local', bridge_profile='x'),
                   dict(kind='virtuoso_ssh', bridge_profile='a b'), dict(kind='virtuoso_ssh', bridge_profile='../x'), dict(kind='spectre_cloud')):
        with pytest.raises(ValueError):
            bridge_connect.create_profile('new', **kwargs)
    assert not connection.connection_file().exists()
    connection.connection_file().parent.mkdir(parents=True, exist_ok=True)
    connection.connection_file().write_text('{ this is not json')
    with pytest.raises(FileExistsError) as refused:
        bridge_connect.create_profile('sim', kind='ngspice_local')
    assert not isinstance(refused.value, bridge_connect.ProfileExists) and connection.connection_file().read_text() == '{ this is not json'


# ------------------------------------------------------------------------------- API
def test_api_adds_and_tests_an_ngspice_connection_and_has_nothing_to_connect(fake_home, tmp_path):
    connector = BridgeConnector(command=[sys.executable, '-c', 'raise SystemExit("the connect process must not run")'])
    http = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False,
                                 monitor=ConnectionMonitor(probe_command=ngspice_probe(tmp_path)), connector=connector))
    setup = http.get('/api/connection/setup').json()
    assert [k['kind'] for k in setup['kinds']][2:] == ['ngspice_local', 'ngspice_ssh']
    made = http.post('/api/connection/profile', json=dict(profile_id='far', kind='ngspice_ssh', ssh_host='simhost')).json()
    assert made['created'] and made['profiles']['profiles'][0]['kind_label'] == 'ngspice over SSH'
    for body in (dict(profile_id='x', kind='ngspice_ssh', ssh_host='alice@10.0.0.1'), dict(profile_id='x', kind='ngspice_ssh', ssh_host='a b'),
                 dict(profile_id='x', kind='ngspice_local', ngspice_bin='/bin/sh'), dict(profile_id='x', kind='ngspice_local', host='10.0.0.1'),
                 dict(profile_id='x', kind='telnet'), dict(profile_id='x', kind='virtuoso_ssh', env_file='/tmp/evil.env')):
        assert http.post('/api/connection/profile', json=body).status_code == 422, body
    unknown_host = http.post('/api/connection/profile', json=dict(profile_id='x', kind='ngspice_ssh', ssh_host='elsewhere'))
    assert unknown_host.status_code == 409 and unknown_host.json()['detail']['code'] == 'ssh_host_not_configured'
    assert http.post('/api/connection/profile', json=dict(profile_id='far', kind='ngspice_local')).json()['detail']['code'] == 'profile_exists'
    refused = http.post('/api/connection/connect', json=dict(profile_id='far'))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'nothing_to_connect' and connector.attempts_started == 0
    tested = http.post('/api/connection/check', json=dict(profile_id='far', scope='interactive')).json()
    assert tested['family'] == 'ngspice' and tested['transport'] == 'ssh' and tested['summary']['level'] == 'ok' and tested['ciw'] is None
    assert http.get('/api/connection/status', params=dict(profile_id='far')).json()['kind_label'] == 'ngspice over SSH'
    blocked = http.post('/api/virtuoso/libraries', json=dict(profile_id='far'))
    assert blocked.status_code == 409 and blocked.json()['detail']['gate']['blocking'] == ['connection_kind']
    assert 'simhost' not in json.dumps(tested)
