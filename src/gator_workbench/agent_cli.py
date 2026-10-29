"""The Agent window's two buttons (record 7.226; the window itself record 7.253): Claude Code or Codex in a terminal window of
its own, in the workbench's folder.

A launch is the CLI as you would start it yourself: no permission option, no settings file, no model and no prompt from
the workbench. What it may do is what YOUR settings say (Claude Code: ~/.claude/settings.json and the folder's .claude/;
Codex: config.toml in its home), it is signed in with your own account, and its session goes into your history like any
other (Claude Code: ~/.claude/projects, which `claude --resume` lists; Codex: the Codex app's own home, so the app lists
it). The backend writes a small start script, opens the window and is done: nothing waits for the CLI, nothing reads what
it says, and the workbench sends nothing to a model.

GATOR_AGENT_CLI_LAUNCH=off makes every launch a dry run that says what it would open: the tests and the browser checks'
backends set it, so no window ever opens from them.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess

from .paths import repo_root

CLIS = ('claude', 'codex')
NAMES = dict(claude='Claude Code', codex='Codex')
LAUNCH_ENV = 'GATOR_AGENT_CLI_LAUNCH'
WINDOWS_USERS = Path('/mnt/c/Users')
INTEROP_DIR = Path('/run/WSL')                   # WSL's interop sockets, through which Windows programs start
# Where the start scripts are written: on the WSL disk, beside the run adapter's state (paths.bridge_state_dir).
SCRIPT_DIR = Path('~/.local/state/gator/agent-cli')
# Linux terminals tried in this order when the backend runs on a Linux desktop (not WSL): each takes the command after
# it.
LINUX_TERMINALS = (('x-terminal-emulator', '-e'), ('gnome-terminal', '--'), ('konsole', '-e'), ('xfce4-terminal', '-x'),
                   ('xterm', '-e'))


class LaunchError(RuntimeError):
    """The window could not be opened. The message says why in plain words; `command` is what to type by hand."""
    def __init__(self, message, command):
        super().__init__(message)
        self.command = command


def working_directory() -> Path:
    """The folder the CLI starts in: the workbench's own repository, where CLAUDE.md and the docs are."""
    return repo_root()


def in_wsl(env=None) -> bool:
    """Detect WSL from the supplied environment or the operating-system release string."""
    env = os.environ if env is None else env
    return bool(env.get('WSL_DISTRO_NAME')) or 'microsoft' in platform.release().lower()


def codex_home(env=None) -> Path | None:
    """The Codex home to use: $CODEX_HOME when it is set; from WSL, the Windows user's .codex that holds a sign-in - the
    Codex app keeps its home there and points its own WSL agent at it, so sessions started here are in the app's history;
    else None (codex then uses ~/.codex)."""
    env = os.environ if env is None else env
    if env.get('CODEX_HOME'):
        return Path(env['CODEX_HOME'])
    if not in_wsl(env):
        return None
    try:
        homes = [home for home in sorted(WINDOWS_USERS.glob('*/.codex')) if (home / 'auth.json').is_file()]
    except OSError:
        return None
    return homes[0] if homes else None


def _codex_app_binaries(home: Path | None) -> list:
    """The Linux builds the Codex app ships for its WSL agent (<home>/bin/wsl/<build>/codex), the newest first."""
    if home is None:
        return []
    try:
        found = [(path.stat().st_mtime, path) for path in (home / 'bin' / 'wsl').glob('*/codex') if os.access(path,
            os.X_OK)]
    except OSError:
        return []
    return [path for _, path in sorted(found, reverse=True)]


def _codex_sqlite_home(env, home: Path | None) -> Path | None:
    """Where the Codex app's WSL agent keeps its state database (it sets CODEX_SQLITE_HOME to the WSL disk). Taken with the
    app's own home only, as the app does; a home named by $CODEX_HOME keeps its database in itself unless
    $CODEX_SQLITE_HOME says otherwise."""
    if env.get('CODEX_SQLITE_HOME'):
        return Path(env['CODEX_SQLITE_HOME'])
    sqlite = Path.home() / '.codex' / 'sqlite'
    return sqlite if home is not None and not env.get('CODEX_HOME') and sqlite.is_dir() else None


def find(cli, env=None) -> dict:
    """Where the CLI is and what its start needs. Free: a PATH look-up and a few file stats, no CLI is run."""
    if cli not in CLIS:
        raise ValueError(f'Unknown CLI {cli!r}: choose one of {", ".join(CLIS)}')
    env = os.environ if env is None else env
    found = dict(cli=cli, name=NAMES[cli], executable=None, environment={}, path_prepend=[], note=None)
    if cli == 'claude':
        local = Path.home() / '.local' / 'bin' / 'claude'           # where the standalone install puts it
        found['executable'] = shutil.which('claude', path=env.get('PATH')) or (str(local) if os.access(local,
            os.X_OK) else None)
        found['note'] = None if found[
            'executable'] else 'Claude Code is not installed for this user (no `claude` on the PATH).'
        return found
    home = codex_home(env)
    on_path = shutil.which('codex', path=env.get('PATH'))
    bundled = _codex_app_binaries(home)
    found['executable'] = on_path or (str(bundled[0]) if bundled else None)
    if home is not None:
        found['environment']['CODEX_HOME'] = str(home)
        sqlite = _codex_sqlite_home(env, home)
        if sqlite is not None:
            found['environment']['CODEX_SQLITE_HOME'] = str(sqlite)
    if not on_path and bundled:
        # As the app starts its own agent: its build folders first on the PATH, the newest codex first (another one
        # holds the `rg` codex searches with).
        first = [str(path.parent) for path in bundled]
        try:
            others = [str(d) for d in sorted((home / 'bin' / 'wsl').iterdir()) if d.is_dir() and str(d) not in first]
        except OSError:
            others = []
        found['path_prepend'] = first + others
    if not found['executable']:
        found[
            'note'] = 'Codex is not installed for this user: no `codex` on the PATH, and no Codex app build was found.'
    return found


def _quoted(path) -> str:
    return shlex.quote(str(path))


def start_script(found: dict, directory: Path) -> str:
    """The shell lines the new window runs: into the folder, the CLI exactly as you would type it, then your own shell
    (the window stays open after the CLI ends)."""
    name = found['name']
    lines = [
        '# Written by the GATOR workbench for the Agent window\'s "%s" button; the window it opened ran it '
        'once.' % name,
             '# The CLI starts as you start it yourself: your own settings decide what it may do.',
             f'cd {_quoted(directory)} || exit 1']
    lines += [f'export {key}={_quoted(value)}' for key, value in found['environment'].items()]
    if found['path_prepend']:
        lines.append('export PATH=' + ':'.join(_quoted(d) for d in found['path_prepend']) + ':"$PATH"')
    lines += [f"printf '\\n%s in %s\\n\\n' {_quoted(name)} \"$PWD\"",
              _quoted(found['executable']),
              f"""printf '\\n%s has ended. This window is a shell in %s; "exit" closes it.\\n' """
              f'{_quoted(name)} "$PWD"',
              'exec bash -li']
    return '\n'.join(lines) + '\n'


def by_hand(found: dict, directory: Path) -> str:
    """The same start as one line to type in a terminal of your own."""
    parts = [f'cd {_quoted(directory)}']
    env = ' '.join(f'{key}={_quoted(value)}' for key, value in found['environment'].items())
    if found['path_prepend']:
        env = (env + ' ' if env else '') + 'PATH=' + ':'.join(_quoted(d) for d in found['path_prepend']) + ':"$PATH"'
    parts.append((env + ' ' if env else '') + _quoted(found['executable'] or found['cli']))
    return ' && '.join(parts)


def window_argv(script: Path, title: str, env=None) -> list | None:
    """How a terminal window is opened from here: Windows Terminal from WSL, else PowerShell's Start-Process (a console
    window), else a Linux desktop's terminal; None when there is none."""
    env = os.environ if env is None else env
    shell = ['bash', '-l', str(script)]
    if in_wsl(env):
        distro = env.get('WSL_DISTRO_NAME')
        wsl = ['wsl.exe', *(['-d', distro] if distro else []), '--cd', str(script.parent), '--', *shell]
        terminal = shutil.which('wt.exe', path=env.get('PATH'))
        if terminal:
            return [terminal, '-w', 'new', 'new-tab', '--title', title, *wsl]
        powershell = shutil.which('powershell.exe', path=env.get('PATH'))
        if powershell:
            listed = ','.join("'" + part.replace("'", "''") + "'" for part in wsl[1:])
            return [powershell, '-NoProfile', '-Command', f'Start-Process -FilePath wsl.exe -ArgumentList {listed}']
        return None
    if not (env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')):
        return None
    for program, option in LINUX_TERMINALS:
        terminal = shutil.which(program, path=env.get('PATH'))
        if terminal:
            return [terminal, option, *shell]
    return None


def availability(env=None) -> dict:
    """What the Agent window shows before a press: the folder, and per CLI whether it was found. Free."""
    env = os.environ if env is None else env
    directory = working_directory()
    clis = []
    for cli in CLIS:
        found = find(cli, env)
        clis.append(dict(cli=cli, name=found['name'], available=bool(found['executable']),
                         executable=found['executable'],
                         codex_home=found['environment'].get('CODEX_HOME'), note=found['note'],
                         command=by_hand(found, directory)))
    return dict(directory=str(directory), clis=clis, launch=_launch_mode(env),
                note=
                    'Each button opens the CLI in a terminal window of its own, in this folder, as you start it '
                    'yourself: your own settings decide what it may do, and the session is in your history.')


def interop_socket(env) -> str | None:
    """The WSL interop socket Windows programs are started through. The backend inherits the one of the WSL session that
    started it, and a server can outlive that session (a desktop app's instance that restarted): then the distro's own
    socket (`/run/WSL/1_interop`, its first init) takes over, else the newest one there is."""
    current = env.get('WSL_INTEROP')
    if current and os.path.exists(current):
        return current
    folder = INTEROP_DIR
    candidates = [folder / '1_interop'] + sorted(folder.glob('*_interop'),
        key=lambda s: s.stat().st_mtime if s.exists() else 0, reverse=True)
    return next((str(c) for c in candidates if c.exists()), current)


def _session_marker(key) -> bool:
    return key == 'CLAUDECODE' or key.startswith(('CLAUDE_CODE_', 'CLAUDE_SSH_')) or key in ('CLAUDE_PID',
        'CLAUDE_AGENT_SDK_VERSION')


def _launch_mode(env) -> str:
    return 'off' if str(env.get(LAUNCH_ENV, '')).strip().lower() in ('off', '0', 'no', 'false') else 'on'


def open_cli(cli, *, env=None, script_dir=None, run=subprocess.Popen) -> dict:
    """Open `cli` in a window of its own. Returns what was started; raises LaunchError (with the command to type by hand)
    when there is no CLI or no terminal to open it in."""
    env = os.environ if env is None else env
    found = find(cli, env)
    directory = working_directory()
    command = by_hand(found, directory)
    if not found['executable']:
        raise LaunchError(found['note'], command)
    folder = Path(script_dir) if script_dir is not None else SCRIPT_DIR.expanduser()
    script, text = folder / f'{cli}.sh', start_script(found, directory)
    title = f"{found['name']} - {directory.name}"
    argv = window_argv(script, title, env)
    if argv is None:
        raise LaunchError('No terminal window can be opened from the workbench server here (no Windows Terminal, '
                          'PowerShell or desktop terminal was found). Start it in a terminal of your own.', command)
    answer = dict(cli=cli, name=found['name'], directory=str(directory), executable=found['executable'],
                  codex_home=found['environment'].get('CODEX_HOME'), command=command, script=str(script),
                  terminal=Path(argv[0]).name)
    if _launch_mode(env) == 'off':                 # writes nothing either: the tests never touch the home folder
        return dict(answer, opened=False, dry_run=True, argv=argv, script_text=text,
                    note=f'{LAUNCH_ENV}=off: nothing was opened (tests and browser checks).')
    folder.mkdir(parents=True, exist_ok=True)
    written = script.with_name(script.name + '.new')        # a new file each time: a window still running the old one
    written.write_text(text)                                 # keeps reading its own copy
    os.replace(written, script)
    # The window's process owns nothing of the backend's: no inherited standard streams, and its own session, so
    # stopping the workbench server leaves the CLI running. From WSL the window is a new WSL session that builds its
    # environment as any terminal does (WSLENV emptied: no variable of the backend travels into it). On a Linux desktop
    # the terminal inherits the backend's environment, less the markers a Claude Code session sets for its own child
    # processes - a backend started from such a session would otherwise start the CLI as that session's child.
    child_env = {key: value for key, value in env.items() if not _session_marker(key)}
    child_env['WSLENV'] = ''
    if in_wsl(env):
        child_env['WSL_INTEROP'] = interop_socket(env)
    try:
        run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(folder),
            env=child_env, start_new_session=True)
    except OSError as exc:
        raise LaunchError(f'The terminal could not be started ({type(exc).__name__}: {exc}). Start it in a terminal of '
                          'your own.', command) from exc
    return dict(answer, opened=True, note=f"{found['name']} opens in a new window in {directory}.")
