"""The folders of the connection module (record 7.168): their defaults are the values the code used before, a saved value
is used where the folder is used, every value is checked before anything is written, and the connections themselves are
never changed. No test contacts Virtuoso: the simulator-side folders are checked with a fake SKILL client."""
import fcntl
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_connect, bridge_setup, connection, directories, layout, paths
from gator_workbench.layout import RunLayout
from helpers import workbench_app

BEFORE = {'adapter_state': '~/.local/state/gator/bridge-state', 'local_scratch': '/tmp/gator-work',
          'bridge_checkout': '~/virtuoso-bridge-lite', 'simulator_ic': '~/.gator/ic', 'maestro_netlist': '/tmp/gator_maestro_netlist'}


@pytest.fixture
def http(tmp_path, monkeypatch):
    """Provide an API client with a temporary home and no bridge-state override."""
    monkeypatch.delenv('GATOR_BRIDGE_STATE_DIR')                 # the tests' own folder is set by conftest; these test the setting
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))            # `~` - so no check looks at the real adapter lock
    (tmp_path / 'home').mkdir()
    return TestClient(workbench_app(tmp_path))


def write_connections(document):
    """Write connection settings to the configured fixture connection file."""
    connection.connection_file().parent.mkdir(parents=True, exist_ok=True)
    connection.connection_file().write_text(json.dumps(document))


LAB = dict(kind='virtuoso_ssh', env_file='/home/u/.virtuoso-bridge/.env', profile=None)


def test_the_defaults_are_the_folders_used_before(http):
    shown = http.get('/api/connection/directories').json()
    assert {f['key']: f['default'] for f in shown['fields']} == BEFORE
    assert all(f['source'] == 'default' and f['value'] == f['default'] and f['saved'] is None for f in shown['fields'])
    assert {f['key'] for f in shown['fields'] if f['side'] == 'simulator'} == {'simulator_ic', 'maestro_netlist'}
    assert 'VB_REMOTE_SCRATCH_ROOT' in shown['note'] and shown['connection_file'] == str(connection.connection_file())
    assert paths.bridge_state_dir() == Path.home() / '.local/state/gator/bridge-state'
    assert directories.local_path('bridge_checkout', '/h') == Path('/h/virtuoso-bridge-lite')


def test_saved_folders_are_used_and_the_connections_stay_as_they_were(http, tmp_path, monkeypatch):
    write_connections(dict(active='lab', profiles=dict(lab=LAB), extra='kept'))
    state, scratch, checkout = tmp_path / 'state', tmp_path / 'scratch', tmp_path / 'bridge'
    checkout.mkdir()
    saved = http.put('/api/connection/directories', json=dict(values=dict(
        adapter_state=str(state), local_scratch=str(scratch) + '/', bridge_checkout=str(checkout),
        simulator_ic='~/gator/ic', maestro_netlist='/tmp/gator_maestro_netlist'))).json()     # the default: not stored
    assert saved['saved'] and saved['changed'] == ['adapter_state', 'local_scratch', 'bridge_checkout', 'simulator_ic']
    document = json.loads(connection.connection_file().read_text())
    assert document['profiles'] == dict(lab=LAB) and document['active'] == 'lab' and document['extra'] == 'kept'
    assert document['directories'] == dict(adapter_state=str(state), local_scratch=str(scratch), bridge_checkout=str(checkout),
                                           simulator_ic='~/gator/ic')
    assert json.loads(Path(saved['backup']).read_text()) == dict(active='lab', profiles=dict(lab=LAB), extra='kept')
    assert state.is_dir() and scratch.is_dir() and not list(state.iterdir())             # made and written once, nothing left
    by_key = {f['key']: f for f in http.get('/api/connection/directories').json()['fields']}
    assert by_key['local_scratch']['source'] == 'file' and by_key['local_scratch']['value'] == str(scratch)
    assert by_key['maestro_netlist']['source'] == 'default'
    # ... and where each one is used
    assert paths.bridge_state_dir() == state
    monkeypatch.delenv('GATOR_LOCAL_SCRATCH', raising=False)
    monkeypatch.setattr(layout, 'filesystem_type', lambda path, mounts=None: '9p' if str(path).startswith('/mnt/') else 'ext4')
    run = RunLayout(Path('/mnt/d/out/exp__abc/runs/task/scratch__seed1__0123456789ab'))
    assert layout.local_scratch(run) == scratch / 'exp__abc' / 'scratch__seed1__0123456789ab'
    site = checkout / '.venv' / 'lib' / 'python3.10' / 'site-packages'
    (site / 'virtuoso_bridge-0.8.0.dist-info').mkdir(parents=True)
    monkeypatch.setattr(bridge_connect, '_bridge_importable', lambda: False)
    assert bridge_connect.detect_setup()['bridge_site_packages'] == str(site)
    # back to the defaults: the block goes, the connections stay
    reset = http.put('/api/connection/directories', json=dict(values={key: None for key in BEFORE})).json()
    assert reset['saved'] and 'directories' not in json.loads(connection.connection_file().read_text())
    assert paths.bridge_state_dir() == Path.home() / '.local/state/gator/bridge-state'
    again = http.put('/api/connection/directories', json=dict(values=dict(local_scratch=''))).json()
    assert again['saved'] is False and again['backup'] is None                          # nothing changed, nothing written


@pytest.mark.parametrize('key, value', [
    ('local_scratch', 'relative/folder'), ('local_scratch', '/'), ('adapter_state', '~'), ('adapter_state', '/tmp/a/../b'),
    ('local_scratch', '/tmp/a\nb'), ('simulator_ic', 'ic'), ('simulator_ic', '/tmp/my ic'), ('simulator_ic', '~/a/../b'),
    ('maestro_netlist', '/tmp/x"; system("id")'), ('maestro_netlist', '/tmp/$(id)'), ('maestro_netlist', '~'),
    ('unknown_folder', '/tmp/x')])
def test_a_folder_that_fails_its_check_is_refused_and_nothing_is_written(http, tmp_path, key, value):
    write_connections(dict(active='lab', profiles=dict(lab=LAB)))
    before = connection.connection_file().read_text()
    refused = http.put('/api/connection/directories', json=dict(values={'simulator_ic': '~/ok/ic', key: value}))
    assert refused.status_code == 422 and refused.json()['detail']['code'] == 'invalid_folder'
    assert refused.json()['detail']['folder'] == key
    assert connection.connection_file().read_text() == before


def test_what_a_local_folder_must_offer(http, tmp_path, monkeypatch):
    blocker = tmp_path / 'a-file'
    blocker.write_text('x')
    refused = http.put('/api/connection/directories', json=dict(values=dict(adapter_state=str(blocker / 'state'))))
    assert refused.status_code == 422 and 'cannot be written' in refused.json()['detail']['message']
    refused = http.put('/api/connection/directories', json=dict(values=dict(bridge_checkout=str(tmp_path / 'nowhere'))))
    assert refused.status_code == 422 and 'no folder' in refused.json()['detail']['message']
    monkeypatch.setattr(layout, 'filesystem_type', lambda path, mounts=None: '9p')
    refused = http.put('/api/connection/directories', json=dict(values=dict(local_scratch=str(tmp_path / 'scratch'))))
    assert refused.status_code == 422 and 'slow mount' in refused.json()['detail']['message']
    assert not connection.connection_file().exists()                    # a refused save makes no file either


def test_a_missing_file_is_made_without_a_connection_and_a_connection_added_later_keeps_the_folders(http, tmp_path, monkeypatch):
    saved = http.put('/api/connection/directories', json=dict(values=dict(maestro_netlist='~/gator/netlists'))).json()
    assert saved['saved'] and saved['backup'] is None
    assert json.loads(connection.connection_file().read_text()) == dict(active=None, profiles={},
                                                                        directories=dict(maestro_netlist='~/gator/netlists'))
    assert http.get('/api/connection/profiles').json()['profiles'] == []
    (Path.home() / '.virtuoso-bridge').mkdir()
    (Path.home() / '.virtuoso-bridge' / '.env').write_text('VB_REMOTE_HOST=eda-host\n')
    monkeypatch.setattr(bridge_connect, '_bridge_importable', lambda: True)
    assert http.post('/api/connection/profile', json=dict(profile_id='lab')).json()['created']
    document = json.loads(connection.connection_file().read_text())
    assert document['active'] == 'lab' and document['directories'] == dict(maestro_netlist='~/gator/netlists')


def test_an_unreadable_file_is_never_replaced_and_a_bad_hand_edit_is_not_used(http):
    connection.connection_file().parent.mkdir(parents=True, exist_ok=True)
    connection.connection_file().write_text('{not json')
    refused = http.put('/api/connection/directories', json=dict(values=dict(simulator_ic='~/ic2')))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'connection_file_unreadable'
    assert connection.connection_file().read_text() == '{not json'
    write_connections(dict(active=None, profiles={}, directories=dict(local_scratch='scratch', simulator_ic='~/ic2', newer='x')))
    by_key = {f['key']: f for f in http.get('/api/connection/directories').json()['fields']}
    assert by_key['local_scratch']['value'] == '/tmp/gator-work' and 'default is used' in by_key['local_scratch']['problem']
    assert by_key['simulator_ic']['value'] == '~/ic2' and by_key['simulator_ic']['problem'] is None
    http.put('/api/connection/directories', json=dict(values=dict(maestro_netlist='/tmp/nl2')))
    assert json.loads(connection.connection_file().read_text())['directories'] == dict(
        newer='x', simulator_ic='~/ic2', maestro_netlist='/tmp/nl2')                   # unknown names kept, the bad value dropped


def test_the_adapter_state_folder_does_not_move_under_a_held_lock_or_an_environment_variable(http, tmp_path, monkeypatch):
    current = tmp_path / 'state-now'
    write_connections(dict(active=None, profiles={}, directories=dict(adapter_state=str(current))))
    current.mkdir()
    with (current / 'session.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)              # a run holds it
        refused = http.put('/api/connection/directories', json=dict(values=dict(adapter_state=str(tmp_path / 'state-new'))))
        assert refused.status_code == 409 and refused.json()['detail']['code'] == 'folder_busy'
        assert http.put('/api/connection/directories', json=dict(values=dict(simulator_ic='~/ic3'))).json()['saved']
    for held in ('sessions/s2/session.lock', 'cells/LIB/cell.lock'):          # a second Virtuoso session's run, a cell's (record 7.311)
        (current / held).parent.mkdir(parents=True)
        with (current / held).open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            refused = http.put('/api/connection/directories', json=dict(values=dict(adapter_state=str(tmp_path / 'state-new'))))
            assert refused.status_code == 409 and refused.json()['detail']['code'] == 'folder_busy', held
    assert http.put('/api/connection/directories', json=dict(values=dict(adapter_state=str(tmp_path / 'state-new')))).json()['saved']
    monkeypatch.setenv('GATOR_BRIDGE_STATE_DIR', str(tmp_path / 'from-env'))
    field = {f['key']: f for f in http.get('/api/connection/directories').json()['fields']}['adapter_state']
    assert field['source'] == 'environment' and field['value'] == str(tmp_path / 'from-env') and field['saved'] == str(tmp_path / 'state-new')
    assert paths.bridge_state_dir() == tmp_path / 'from-env'
    refused = http.put('/api/connection/directories', json=dict(values=dict(adapter_state=None)))
    assert refused.status_code == 409 and 'GATOR_BRIDGE_STATE_DIR' in refused.json()['detail']['message']


def test_only_paths_reach_the_folders_route(http):
    for body in ({}, dict(values='x'), dict(values=dict(local_scratch=3)), dict(values={}, profile_id='lab'),
                 dict(values={}, command='id')):
        assert http.put('/api/connection/directories', json=body).status_code == 422, body


# ------------------------------------------------------------------------------- the simulator host
class Client:
    """Answers the SKILL calls of bridge_setup's Maestro functions; `home` is the simulator user's home."""
    def __init__(self, listed='(("/pdk/model.scs" "tt"))', home='/home/sim'):
        self.calls, self.listed, self.home, self.downloads = [], listed, home, []

    def execute_skill(self, text, timeout=60):
        """Record SKILL calls and return fixture directory and Maestro responses."""
        self.calls.append(text)
        if text.startswith('strcat(getShellEnvVar("HOME") '):
            output = '"' + self.home + text.split('"')[3] + '"'
        else:
            answers = [('maeOpenSetup', '"fnxSession1"'), ('?typeName "tests"', '("GATOR")'), ('?option "modelFiles"', self.listed), ('maeGetEnabledAnalysis', 'nil'), ('maeGetTestOutputs', '""'),
                       ('ddGetObj', '"yes"'), ('outfile(', 't'), ('maeCreateNetlistForCorner', 't')]
            output = next((value for key, value in answers if key in text), 't')
        return types.SimpleNamespace(ok=True, errors=[], output=output)

    def download_file(self, remote, local, recursive=False):
        """Record a requested download and create a synthetic local netlist tree."""
        self.downloads.append(remote)
        folder = Path(local) / 'netlist'
        (folder / 'amap').mkdir(parents=True)
        (folder / 'input.scs').write_text('')
        (folder / 'netlist').write_text('')


@pytest.fixture
def skill(monkeypatch):
    """Install a fixture bridge module with an identity SKILL-output decoder."""
    fake = types.ModuleType('virtuoso_bridge')
    fake.decode_skill_output = lambda text: text
    monkeypatch.setitem(sys.modules, 'virtuoso_bridge', fake)


def test_initial_condition_files_go_to_the_configured_folder_and_old_ones_are_still_recognized(http, skill):
    setup = dict(test='GATOR', initial_conditions={'OUT': '0.9'}, model_files=None, analyses=None, outputs=[], specs=[],
                 variables=None)
    client = Client()
    bridge_setup.write_maestro(client, 'L_GATOR', 'tb', setup)               # the default folder, under the host's home
    [write] = [c for c in client.calls if 'outfile(' in c]
    assert '"/home/sim/.gator/ic/L_GATOR__tb__GATOR.scs"' in write and 'createDir("/home/sim/.gator/ic")' in write
    http.put('/api/connection/directories', json=dict(values=dict(simulator_ic='/data/sim/ic')))
    client = Client(listed='(("/home/sim/.gator/ic/L_GATOR__tb__GATOR.scs") ("/pdk/model.scs" "tt"))')
    bridge_setup.write_maestro(client, 'L_GATOR', 'tb', setup)
    assert not any('getShellEnvVar' in c for c in client.calls)                # an absolute folder needs no home
    [write] = [c for c in client.calls if 'outfile(' in c]
    assert 'createDir("/data") createDir("/data/sim") createDir("/data/sim/ic")' in write
    [models] = [c for c in client.calls if c.startswith('maeSetEnvOption')]
    assert '("/data/sim/ic/L_GATOR__tb__GATOR.scs" "")' in models and '/home/sim/.gator/ic' not in models  # the old one replaced
    assert '("/pdk/model.scs" "tt")' in models
    read = bridge_setup.read_maestro(Client(listed='(("/data/sim/ic/L_GATOR__tb__GATOR.scs") ("/pdk/model.scs" "tt"))'),
                                     'L_GATOR', 'tb', test='GATOR')
    assert read['ic_file'] == '/data/sim/ic/L_GATOR__tb__GATOR.scs' and read['model_files'] == [['/pdk/model.scs', 'tt']]
    assert not bridge_setup._is_ic_file('/data/sim/ic/deeper/x.scs', bridge_setup._ic_folders())


def test_maestro_netlists_go_to_the_configured_folder(http, skill, tmp_path):
    client = Client()
    assert bridge_setup.maestro_netlist(client, 'L_GATOR', 'tb', test='GATOR', out=tmp_path / 'a')['remote'] == \
        '/tmp/gator_maestro_netlist/L_GATOR/tb'
    http.put('/api/connection/directories', json=dict(values=dict(maestro_netlist='~/gator/netlists')))
    client = Client(home='/export/home/ana')
    done = bridge_setup.maestro_netlist(client, 'L_GATOR', 'tb', test='GATOR', out=tmp_path / 'b')
    assert done['remote'] == '/export/home/ana/gator/netlists/L_GATOR/tb' == client.downloads[0]
    assert any('maeCreateNetlistForCorner("GATOR" "Nominal" "/export/home/ana/gator/netlists/L_GATOR/tb"' in c for c in client.calls)
