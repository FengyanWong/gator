"""The Agent tab's two buttons (record 7.226): Claude Code or Codex in a terminal window of its own, in the workbench's
folder, started as the user starts it - no permission option, the user's own account and history. Fake CLIs and fake
terminals only: no window is ever opened (tests/conftest.py also turns real launches off)."""
import json
import os
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from gator_workbench import agent_cli
from helpers import workbench_app


def executable(path, text='#!/bin/sh\nexit 0\n'):
    """Create an executable fixture script at the requested path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home of its own (no ~/.local/bin/claude, no ~/.codex) and a PATH with nothing but the system's tools."""
    folder = tmp_path / 'home'
    folder.mkdir()
    monkeypatch.setenv('HOME', str(folder))
    monkeypatch.setattr(agent_cli, 'WINDOWS_USERS', tmp_path / 'no-windows-users')
    return folder


def env(tmp_path, **extra):
    """An environment as the backend may have it: WSL, a PATH of fakes first, Claude Code session markers inherited."""
    return dict(PATH=f'{tmp_path / "bin"}:/usr/bin:/bin', WSL_DISTRO_NAME='Ubuntu', HOME=os.environ['HOME'], CLAUDECODE='1',
                CLAUDE_CODE_ENTRYPOINT='claude-desktop', WSLENV='GATOR_WORKBENCH_URL', **extra)


# ------------------------------------------------------------------------------- finding the CLIs
def test_claude_is_the_one_on_the_path_or_the_standalone_install(tmp_path, home):
    assert agent_cli.find('claude', env(tmp_path))['executable'] is None
    assert 'not installed' in agent_cli.find('claude', env(tmp_path))['note']
    local = executable(home / '.local' / 'bin' / 'claude')
    assert agent_cli.find('claude', env(tmp_path))['executable'] == str(local)
    on_path = executable(tmp_path / 'bin' / 'claude')
    found = agent_cli.find('claude', env(tmp_path))
    assert found['executable'] == str(on_path) and found['environment'] == {} and found['path_prepend'] == []
    with pytest.raises(ValueError, match='Unknown CLI'):
        agent_cli.find('bash', env(tmp_path))


def test_codex_uses_the_codex_apps_home_and_build_so_its_sessions_are_in_the_apps_history(tmp_path, home, monkeypatch):
    users = tmp_path / 'Users'
    codex_home = users / 'alice' / '.codex'
    (codex_home / 'auth.json').parent.mkdir(parents=True)
    (codex_home / 'auth.json').write_text('{}')
    old = executable(codex_home / 'bin' / 'wsl' / 'aaa' / 'codex')
    new = executable(codex_home / 'bin' / 'wsl' / 'bbb' / 'codex')
    os.utime(old, (1, 1))
    executable(codex_home / 'bin' / 'wsl' / 'ccc' / 'rg')                 # the app's other build folder: its search tool
    (home / '.codex' / 'sqlite').mkdir(parents=True)                       # where the app's WSL agent keeps its state
    monkeypatch.setattr(agent_cli, 'WINDOWS_USERS', users)
    found = agent_cli.find('codex', env(tmp_path))
    assert found['executable'] == str(new)                                 # the newest build
    assert found['environment'] == dict(CODEX_HOME=str(codex_home), CODEX_SQLITE_HOME=str(home / '.codex' / 'sqlite'))
    assert found['path_prepend'] == [str(new.parent), str(old.parent), str(codex_home / 'bin' / 'wsl' / 'ccc')]
    # A codex the user installed on the PATH is the one they type: it wins, in the same home.
    mine = executable(tmp_path / 'bin' / 'codex')
    found = agent_cli.find('codex', env(tmp_path))
    assert found['executable'] == str(mine) and found['path_prepend'] == [] and found['environment']['CODEX_HOME'] == str(codex_home)
    # $CODEX_HOME, when the backend has it, names the home; outside WSL no Windows folder is looked at.
    assert agent_cli.find('codex', env(tmp_path, CODEX_HOME='/elsewhere'))['environment'] == dict(CODEX_HOME='/elsewhere')
    monkeypatch.setattr(agent_cli.platform, 'release', lambda: '6.1.0-generic')
    linux = {k: v for k, v in env(tmp_path).items() if k != 'WSL_DISTRO_NAME'}
    assert agent_cli.codex_home(linux) is None and agent_cli.find('codex', linux)['environment'] == {}


def test_no_codex_anywhere_says_so(tmp_path, home):
    found = agent_cli.find('codex', env(tmp_path))
    assert found['executable'] is None and 'not installed' in found['note']


# ------------------------------------------------------------------------------- the start script
def test_the_start_script_is_the_cli_as_typed_in_the_folder_then_your_shell(tmp_path, home):
    """Run for real with a fake CLI that records where and how it was started: the folder, the Codex home, nothing on its
    command line. The window then stays a shell of the user's (`exec bash -li`; here it reads end of input and ends)."""
    record = tmp_path / 'record.json'
    fake = executable(tmp_path / "my bin" / "co'dex", '#!/usr/bin/env python3\nimport json, os, sys\n'
                      f'json.dump(dict(argv=sys.argv[1:], cwd=os.getcwd(), home=os.environ.get("CODEX_HOME"), path=os.environ["PATH"]), '
                      f'open({str(record)!r}, "w"))\n')
    folder = tmp_path / "the work's folder"
    folder.mkdir()
    found = dict(cli='codex', name='Codex', executable=str(fake), environment=dict(CODEX_HOME="/mnt/c/Users/o'neil/.codex"),
                 path_prepend=[str(tmp_path / 'build one')], note=None)
    script = tmp_path / 'codex.sh'
    script.write_text(agent_cli.start_script(found, folder))
    assert subprocess.run(['bash', '-n', str(script)]).returncode == 0
    done = subprocess.run(['bash', str(script)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
                          env=dict(PATH='/usr/bin:/bin', HOME=str(home)))
    assert done.returncode == 0, done.stderr
    seen = json.loads(record.read_text())
    assert seen['argv'] == [] and seen['cwd'] == str(folder)              # no option of the workbench's: your own settings
    assert seen['home'] == "/mnt/c/Users/o'neil/.codex" and seen['path'].startswith(str(tmp_path / 'build one') + ':')
    assert 'Codex has ended' in done.stdout


def test_the_command_to_type_by_hand_is_the_same_start(tmp_path):
    found = dict(cli='codex', name='Codex', executable='/opt/codex', environment=dict(CODEX_HOME='/h'), path_prepend=['/b'], note=None)
    assert agent_cli.by_hand(found, Path('/repo')) == 'cd /repo && CODEX_HOME=/h PATH=/b:"$PATH" /opt/codex'
    assert agent_cli.by_hand(dict(found, executable=None, environment={}, path_prepend=[]), Path('/repo')) == 'cd /repo && codex'


# ------------------------------------------------------------------------------- the window
def test_a_window_from_wsl_is_windows_terminal_then_a_console(tmp_path, home):
    script = Path('/state/claude.sh')
    executable(tmp_path / 'bin' / 'powershell.exe')
    console = agent_cli.window_argv(script, 'Claude Code - gator', env(tmp_path))
    assert console[0].endswith('powershell.exe') and console[1:3] == ['-NoProfile', '-Command']
    assert console[3] == ("Start-Process -FilePath wsl.exe -ArgumentList '-d','Ubuntu','--cd','/state','--','bash','-l',"
                          "'/state/claude.sh'")
    terminal = executable(tmp_path / 'bin' / 'wt.exe')
    assert agent_cli.window_argv(script, 'Claude Code - gator', env(tmp_path)) == [
        str(terminal), '-w', 'new', 'new-tab', '--title', 'Claude Code - gator',
        'wsl.exe', '-d', 'Ubuntu', '--cd', '/state', '--', 'bash', '-l', '/state/claude.sh']


def test_a_window_on_a_linux_desktop_and_none_without_one(tmp_path, home, monkeypatch):
    monkeypatch.setattr(agent_cli.platform, 'release', lambda: '6.1.0-generic')
    linux = {k: v for k, v in env(tmp_path).items() if k != 'WSL_DISTRO_NAME'}
    terminal = executable(tmp_path / 'bin' / 'xterm')
    assert agent_cli.window_argv(Path('/s/x.sh'), 't', linux) is None                     # no display: no window
    assert agent_cli.window_argv(Path('/s/x.sh'), 't', dict(linux, DISPLAY=':0')) == [str(terminal), '-e', 'bash', '-l', '/s/x.sh']


# ------------------------------------------------------------------------------- the launch
def launch_env(tmp_path):
    """Provide fake launcher executables with the dry-run override removed."""
    executable(tmp_path / 'bin' / 'claude')
    executable(tmp_path / 'bin' / 'wt.exe')
    return env(tmp_path)                                   # GATOR_AGENT_CLI_LAUNCH not in it: a launch would be real


def test_a_launch_opens_the_window_on_its_own_and_hands_it_nothing_of_the_backend(tmp_path, home):
    started = []
    answer = agent_cli.open_cli('claude', env=launch_env(tmp_path), script_dir=tmp_path / 'state',
                                run=lambda argv, **options: started.append((argv, options)))
    assert answer['opened'] is True and answer['terminal'] == 'wt.exe' and answer['executable'] == str(tmp_path / 'bin' / 'claude')
    assert answer['directory'] == str(agent_cli.working_directory()) and 'cd ' in answer['command']
    (argv, options), = started
    assert argv[-1] == str(tmp_path / 'state' / 'claude.sh') and '--title' in argv
    text = (tmp_path / 'state' / 'claude.sh').read_text()
    assert text.splitlines()[-3] == str(tmp_path / 'bin' / 'claude')       # the CLI alone: no flag, no prompt, no model
    assert '--dangerously' not in text and 'permission' not in text.split('\n', 2)[2]
    assert options['start_new_session'] is True and options['stdin'] == subprocess.DEVNULL and options['stdout'] == subprocess.DEVNULL
    child = options['env']
    assert child['WSLENV'] == '' and 'CLAUDECODE' not in child and 'CLAUDE_CODE_ENTRYPOINT' not in child
    assert not list((tmp_path / 'state').glob('*.new'))                    # written whole, then put in place


def test_a_server_that_outlived_its_wsl_session_still_reaches_windows(tmp_path, home, monkeypatch):
    """Windows programs start through the WSL interop socket the server inherited; when that session is gone the
    distro's own socket is used, so the window still opens."""
    sockets = tmp_path / 'run-wsl'
    sockets.mkdir()
    (sockets / '1_interop').write_text('')
    monkeypatch.setattr(agent_cli, 'INTEROP_DIR', sockets)
    assert agent_cli.interop_socket(dict(WSL_INTEROP=str(tmp_path / 'gone_interop'))) == str(sockets / '1_interop')
    alive = sockets / '42_interop'
    alive.write_text('')
    assert agent_cli.interop_socket(dict(WSL_INTEROP=str(alive))) == str(alive)          # a live one is kept
    started = []
    agent_cli.open_cli('claude', env=dict(launch_env(tmp_path), WSL_INTEROP=str(tmp_path / 'gone_interop')), script_dir=tmp_path / 'state',
                       run=lambda argv, **options: started.append(options['env']))
    assert started[0]['WSL_INTEROP'] == str(sockets / '1_interop')


def test_the_tests_switch_makes_a_launch_a_dry_run_that_writes_nothing(tmp_path, home):
    def never(*args, **kwargs):
        raise AssertionError('a window was opened')
    answer = agent_cli.open_cli('claude', env=dict(launch_env(tmp_path), GATOR_AGENT_CLI_LAUNCH='off'), script_dir=tmp_path / 'state', run=never)
    assert answer['opened'] is False and answer['dry_run'] is True and answer['argv'][0].endswith('wt.exe')
    assert answer['script_text'].splitlines()[-3] == str(tmp_path / 'bin' / 'claude') and not (tmp_path / 'state').exists()
    assert os.environ['GATOR_AGENT_CLI_LAUNCH'] == 'off'                   # the whole suite runs with it (conftest.py)


def test_a_launch_that_cannot_happen_says_why_and_what_to_type(tmp_path, home):
    with pytest.raises(agent_cli.LaunchError, match='not installed') as missing:
        agent_cli.open_cli('codex', env=env(tmp_path), script_dir=tmp_path / 'state', run=None)
    assert missing.value.command.endswith('&& codex')
    executable(tmp_path / 'bin' / 'claude')
    with pytest.raises(agent_cli.LaunchError, match='No terminal window') as nowhere:
        agent_cli.open_cli('claude', env=env(tmp_path), script_dir=tmp_path / 'state', run=None)
    assert nowhere.value.command.endswith(str(tmp_path / 'bin' / 'claude'))

    def broken(*args, **kwargs):
        raise FileNotFoundError(2, 'No such file')
    with pytest.raises(agent_cli.LaunchError, match='could not be started'):
        agent_cli.open_cli('claude', env=launch_env(tmp_path), script_dir=tmp_path / 'state', run=broken)


# ------------------------------------------------------------------------------- the routes
def test_the_routes_list_the_clis_and_open_one_dry(tmp_path, home, monkeypatch):
    executable(tmp_path / 'bin' / 'claude')
    executable(tmp_path / 'bin' / 'wt.exe')
    monkeypatch.setenv('PATH', f'{tmp_path / "bin"}:/usr/bin:/bin')      # not the machine's PATH: a codex installed for the user made codex=False fail
    monkeypatch.setenv('WSL_DISTRO_NAME', 'Ubuntu')
    client = TestClient(workbench_app(tmp_path))
    listed = client.get('/api/agent/clis').json()
    assert listed['directory'] == str(agent_cli.working_directory()) and listed['launch'] == 'off'
    assert {c['cli']: c['available'] for c in listed['clis']} == dict(claude=True, codex=False)
    opened = client.post('/api/agent/open', json=dict(cli='claude'))
    assert opened.status_code == 200 and opened.json()['dry_run'] is True and opened.json()['terminal'] == 'wt.exe'
    refused = client.post('/api/agent/open', json=dict(cli='codex'))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'cli_not_opened'
    assert 'not installed' in refused.json()['detail']['message'] and refused.json()['detail']['command'].endswith('codex')
    for body in (dict(cli='bash'), dict(cli='claude', args='--dangerously-skip-permissions'), {}):
        assert client.post('/api/agent/open', json=body).status_code == 422, body      # nothing but the CLI's name
