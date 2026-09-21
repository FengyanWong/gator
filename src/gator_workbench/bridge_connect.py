"""Explicit, user-triggered bridge connection - the counterpart of the observing check.

``connection.py`` OBSERVES and never repairs; its test pins that, and nothing here changes it.
This module holds the only actions that alter the link, and each one runs ONLY on an explicit
user click - never on page load, on a timer, at backend start, or as a side effect of a check:

  * ``create_profile``  writes ``bridge_connection.json`` from a bridge setup found ON THIS HOST
    (the env file made by ``virtuoso-bridge init`` and the bridge's site-packages). The browser
    supplies an identifier and nothing else - no host, port, path or command. An existing
    connection file is operator-owned and is never overwritten.
  * ``BridgeConnector.connect``  starts the SSH tunnel of a configured profile the way
    ``virtuoso-bridge start`` does (``SSHClient.from_env(keep_remote_files=True).warm()``), in a
    short-lived process, and reports the line to load in the Virtuoso CIW. A tunnel that is
    already running is left untouched. Like the upstream command, a first start deploys the bridge
    setup files to the remote host and may record an auto-switched local port in the env file.

Deliberately absent: stopping or restarting a tunnel, restarting the daemon, and injecting the
load command into the CIW. Loading the setup file stays a manual step in the user's own Virtuoso.
SSH runs in BatchMode (upstream), so a missing key fails fast instead of waiting for a password.
Hosts, tokens and passwords never appear in a result or a log; the only remote detail reported is
the setup-file path, because that path IS the command the user has to type.

Also here, because they describe the link to the user rather than probe it: ``ciw_lines`` (the
CIW command text) and ``summarize`` (one plain sentence for a check result).

Capabilities used, confirmed against the local virtuoso-bridge 0.8.0 source on 2026-09-20:
``SSHClient.from_env``, ``.warm()``, ``.close()``, plus what the check already uses.
"""
from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

from . import connection
from .paths import local_settings_dir, repo_root
from .security import redact
from .storage.atomic import JsonlAppender, write_json
from .storage.dataset import utcnow

DEFAULT_PROFILE_ID = 'lab'
NEXT_STEPS = dict(connection.NEXT_STEPS, **{
    'ssh_failed': 'SSH to the target failed. It runs in batch mode, so it needs key-based login (it cannot ask for a '
                  'password). Run in a terminal:  virtuoso-bridge start{profile_arg}   - it prints the exact ssh command to '
                  'verify. Check the host and user settings (and the jump host, if any) in the env file of this profile.',
    'tunnel_exited': 'The tunnel process exited right after it started. Run in a terminal:  virtuoso-bridge start'
                     '{profile_arg}   to see the manual ssh command and its error.',
    'connect_timeout': 'Connecting did not finish in time. Check the network/VPN to the target host, then try again.',
    'setup_path_unknown': 'The bridge state holds no setup-file path (a tunnel started outside the bridge?). Run in a '
                          'terminal:  virtuoso-bridge status{profile_arg}   - it prints the load("...") line.',
})


# ---------------------------------------------------------------------------- CIW command text
def ciw_lines(setup_path) -> dict | None:
    """The text to show beside "Load in Virtuoso CIW". Mirrors the hints of `virtuoso-bridge start/status`."""
    if not setup_path or not isinstance(setup_path, str) or any(c in setup_path for c in '\x00\n\r'):
        return None
    escaped = setup_path.replace('\\', '\\\\').replace('"', '\\"')       # a SKILL string literal
    load = f'load("{escaped}")'
    notes = ['If the CIW answers "already running", the old daemon was not replaced: run the two lines under '
             '"replace a running daemon" instead.',
             'To load it on every Virtuoso start, add the same load(...) line to your .cdsinit.']
    if setup_path.startswith('/tmp/'):
        notes.append("If the CIW reports `load: can't access file`, its /tmp is isolated from SSH: set "
                     'VB_REMOTE_SCRATCH_ROOT in the env file to a shared home/scratch directory, then connect again.')
    return dict(load=load, replace_running_daemon=['RBStop()', load], setup_path=setup_path, notes=notes)


# ---------------------------------------------------------------------------- plain-language status
_LAYER_TEXT = {
    'bridge_package': 'The backend cannot use the virtuoso-bridge package',
    'connection_profile': 'The connection profile is not usable',
    'tunnel': 'The SSH tunnel is not running - click "Connect SSH"',
    'daemon': 'SSH is connected, but the Virtuoso CIW does not answer - load the command below in the CIW, then test again',
    'session_readiness': 'Connected, but the Virtuoso session is not ready',
    'spectre': 'Connected to the CIW, but Spectre was not found on the Spectre host',
    'spectre_license': 'Connected, but no free Spectre license is reported',
}
_REASON_TEXT = {
    'auth_failed': 'SSH is connected, but the daemon in the CIW rejected the token',
    'daemon_user_mismatch': "SSH is connected, but the port answers for ANOTHER user's Virtuoso daemon",
    'busy_active_run': 'The CIW is busy with the active run (busy is not failed)',
    'probe_timeout': 'The test did not answer in time',
    'license_not_checkable': 'Connected, but the license server gave nothing the check could read',
    'conflicting_ade_windows': 'Connected, but conflicting ADE/Maestro windows are open in Virtuoso',
    'unparseable_probe_output': 'The test process gave no readable result',
}
_TESTED = {'cheap': 'Bridge package, profile and SSH tunnel are OK. The Virtuoso CIW has NOT been contacted yet - click '
                    '"Test connection".',
           'interactive': 'Connected: the SSH tunnel is up, the Virtuoso CIW answered and the session is ready.',
           'full': 'Connected: SSH tunnel, Virtuoso CIW, session, Spectre and a free license seat are all OK.'}


def summarize(result) -> dict:
    """One sentence + the next step for a check/status result. Adds nothing the layers do not say."""
    layers = result.get('layers') or []
    if result.get('checked_utc') is None:
        return dict(level='unknown', headline='Not tested yet.', broken_layer=None, next_step=None)
    if result.get('stale'):
        return dict(level='unknown', headline='The last test is too old to trust - test again.', broken_layer=None,
                    next_step=None)
    broken = next((item for item in layers if item.get('state') in ('failed', 'not_ready', 'busy', 'unknown')), None)
    if broken is None:
        scope = result.get('scope', 'interactive')
        return dict(level='ok' if scope != 'cheap' else 'partial', headline=_TESTED.get(scope, _TESTED['interactive']),
                    broken_layer=None, next_step=None)
    headline = _REASON_TEXT.get(broken.get('reason_code')) or _LAYER_TEXT.get(broken['layer'], broken['layer'])
    level = dict(failed='error', not_ready='warn', busy='warn').get(broken['state'], 'unknown')
    return dict(level=level, headline=f'{headline}.', broken_layer=broken['layer'], reason_code=broken.get('reason_code'),
                next_step=(broken.get('details') or {}).get('next_step'))


def describe(result) -> dict:
    """A check/status result as the panel shows it: + `summary` and + `ciw` (from the tunnel layer)."""
    tunnel = next((item for item in result.get('layers') or [] if item.get('layer') == 'tunnel'), None)
    return dict(result, summary=summarize(result), ciw=ciw_lines(((tunnel or {}).get('details') or {}).get('setup_path')))


# ---------------------------------------------------------------------------- profile creation
class SetupNotFound(RuntimeError):
    def __init__(self, reason_code, message):
        super().__init__(message)
        self.reason_code = reason_code


def _bridge_importable() -> bool:
    return importlib.util.find_spec('virtuoso_bridge') is not None


def detect_setup(home=None) -> dict:
    """What a default profile would be built from: paths found on this host. The env file is only
    located, never read (it names the target host and may hold credentials)."""
    home = Path(home or os.path.expanduser('~'))
    env_file = home / '.virtuoso-bridge' / '.env'                     # where `virtuoso-bridge init` writes it
    importable = _bridge_importable()
    site_packages = None
    if not importable:                                                # the bridge lives in another virtualenv
        for candidate in sorted((home / 'virtuoso-bridge-lite' / '.venv' / 'lib').glob('python*/site-packages')):
            if any(candidate.glob('virtuoso_bridge-*.dist-info')):
                site_packages = candidate
    problems = []
    if not env_file.is_file():
        problems.append(dict(reason_code='env_file_missing', message=f'No bridge env file at {env_file}. Create it in a '
                             'terminal with:  virtuoso-bridge init <user>@<host>'))
    if not importable and site_packages is None:
        problems.append(dict(reason_code='bridge_not_found', message='virtuoso-bridge is neither importable by the backend '
                             f'interpreter ({sys.executable}) nor installed under {home}/virtuoso-bridge-lite/.venv.'))
    return dict(env_file=str(env_file), env_file_exists=env_file.is_file(), bridge_importable=importable,
                bridge_site_packages=None if site_packages is None else str(site_packages),
                connection_file=str(connection.connection_file()), connection_file_exists=connection.connection_file().is_file(),
                problems=problems, can_create=not problems and not connection.connection_file().is_file())


_CREATE_LOCK = threading.Lock()


def create_profile(profile_id=DEFAULT_PROFILE_ID, *, home=None) -> dict:
    """Write the connection file for the bridge setup detected on this host. Never overwrites."""
    if not isinstance(profile_id, str) or not connection.PROFILE_ID.match(profile_id):
        raise ValueError('profile_id must be a short identifier (letters, digits, "_", "." or "-")')
    with _CREATE_LOCK:
        target = connection.connection_file()
        if target.exists():
            raise FileExistsError(f'{target} already exists. It is operator-owned and is never overwritten; edit it by hand.')
        found = detect_setup(home)
        if found['problems']:
            raise SetupNotFound(found['problems'][0]['reason_code'], ' '.join(p['message'] for p in found['problems']))
        profile = dict(env_file=found['env_file'], profile=None)      # profile null = the bridge's default profile, explicitly
        if found['bridge_site_packages']:
            profile['bridge_site_packages'] = found['bridge_site_packages']
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, dict(active=profile_id, profiles={profile_id: profile}))
    return dict(created=True, profile_id=profile_id, connection_file=str(target), settings_present=sorted(profile),
                note='Enough for connecting and testing. Real-simulation tasks also need library, creation_receipt, '
                     'model_file and reference_measurements in this file (docs/workbench.md).')


# ---------------------------------------------------------------------------- the connect process
class TunnelBridge(connection.RealBridge):
    """The check's facade plus the ONE starting call. Kept out of `connection.RealBridge` on purpose."""
    def start_tunnel(self, profile):
        from virtuoso_bridge.transport.tunnel import SSHClient
        ssh = SSHClient.from_env(keep_remote_files=True, profile=profile)     # exactly what `virtuoso-bridge start` does
        try:
            ssh.warm()
        finally:
            ssh.close()                                                       # closes the runner; the tunnel survives


def _outcome(ok, action, reason=None, diagnostic=None, profile_arg='', **details):
    next_step = NEXT_STEPS.get(reason, '').format(profile_arg=profile_arg) or None if reason else None
    return dict(bridge_connect=True, ok=bool(ok), action=action, reason_code=reason, diagnostic=redact(diagnostic, 600),
                details={k: v for k, v in dict(details, next_step=next_step).items() if v is not None})


def perform_connect(bridge_factory, settings, *, settle_seconds=1.0, profile_error=None) -> dict:
    """Runs inside the short-lived process. Same preconditions, in the same order, as the check's
    layers 1-2, so "Connect" and "Test" can never disagree about the profile."""
    settings = settings or {}
    profile = settings.get('profile') or None
    arg = f' -p {profile}' if profile else ''

    def failed(reason, diagnostic=None):
        return _outcome(False, 'failed', reason, diagnostic, profile_arg=arg)

    try:
        bridge = bridge_factory(settings)
        version = bridge.version()
    except Exception as exc:
        return failed('bridge_not_importable', f'{type(exc).__name__}: {exc}')
    if version != connection.VERIFIED_BRIDGE_VERSION:
        return failed('bridge_version_unverified', f'installed {version}')
    if profile_error:
        return failed(*profile_error)
    env_file = settings.get('env_file')
    if not env_file or not Path(env_file).is_file():
        return failed('env_file_missing', 'the env file of this profile does not exist')
    try:
        bridge.bind_env(env_file)
        if bridge.resolve_profile(profile) != profile:
            return failed('implicit_profile_binding', 'the bridge would bind a profile that is not the configured one')
        roles = bridge.roles(profile)
    except Exception as exc:
        return failed('profile_incomplete', f'{type(exc).__name__}: {exc}')
    if not roles.get('daemon_host'):
        return failed('profile_incomplete', "missing settings: ['daemon_host']")
    local = bridge.is_local(roles.get('daemon_host'))
    try:
        state, running = bridge.tunnel_state(profile)
    except Exception as exc:
        return failed('tunnel_state_unreadable', f'{type(exc).__name__}: {exc}')
    if running:
        action = 'already_running'                       # left untouched: never stopped, never restarted
    else:
        try:
            bridge.start_tunnel(profile)
        except Exception as exc:
            first_line = (str(exc).strip().splitlines() or [''])[0]
            return failed('ssh_failed', f'{type(exc).__name__}: {first_line}')
        if not local:
            time.sleep(settle_seconds)                   # upstream waits, then re-checks that the process survived
        try:
            state, running = bridge.tunnel_state(profile)
        except Exception as exc:
            return failed('tunnel_state_unreadable', f'{type(exc).__name__}: {exc}')
        if not running:
            return failed('tunnel_exited', 'the tunnel process exited shortly after it started')
        action = 'started'
    mode = 'local' if local or (state or {}).get('mode') == 'local' else 'remote'
    ciw = ciw_lines((state or {}).get('setup_path'))
    if ciw is None:
        return _outcome(True, action, 'setup_path_unknown', profile_arg=arg, mode=mode)
    return _outcome(True, action, mode=mode, ciw=ciw)


def _connect_main(argv=None):
    """Entry point of the short-lived connect process: prints ONE JSON object as its last line."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-id', required=True)
    args = parser.parse_args(argv)
    settings, profile_error = None, None
    try:
        settings = connection.resolve_profile_id(args.profile_id)
    except (KeyError, ValueError) as exc:
        name = 'connection_file_missing' if not connection.connection_file().is_file() else 'profile_not_configured'
        profile_error = (name, f'profile {args.profile_id!r}: {exc}')
    print(json.dumps(perform_connect(TunnelBridge, settings, profile_error=profile_error)), flush=True)
    return 0


@dataclass
class BridgeConnector:
    """Runs the connect process off the request thread's own state: one at a time per profile
    (a double click or a second browser tab shares the attempt already running), with a timeout
    that kills only the connect process group - an ssh tunnel it already started lives in its own
    session, exactly as after `virtuoso-bridge start`."""
    timeout_seconds: float = 150.0               # a cold handshake through a jump host can take > 30 s (upstream note)
    command: list | None = None                  # tests inject a fake process; default = this module as a process
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _inflight: dict = field(default_factory=dict)
    attempts_started: int = 0

    def connect(self, profile_id) -> dict:
        if not isinstance(profile_id, str) or not connection.PROFILE_ID.match(profile_id):
            raise ValueError('profile_id must be the identifier of a configured profile')
        with self._lock:
            future = self._inflight.get(profile_id)
            owner = future is None
            if owner:
                future = self._inflight[profile_id] = Future()
        if not owner:
            return future.result()
        try:
            result = self._attempt(profile_id)
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._inflight.pop(profile_id, None)

    def _attempt(self, profile_id):
        started, began = utcnow(), time.monotonic()
        self.attempts_started += 1
        base = self.command or [sys.executable, '-m', 'gator_workbench.bridge_connect']
        # Output goes to files, not pipes: a pipe would stay open for as long as any descendant holds it.
        with tempfile.TemporaryFile('w+') as out, tempfile.TemporaryFile('w+') as err:
            process = subprocess.Popen([*base, '--profile-id', profile_id], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       shell=False, env=connection.worker_environment(), cwd=str(repo_root()),
                                       start_new_session=True)
            try:
                process.wait(timeout=self.timeout_seconds)
                out.seek(0); err.seek(0)
                outcome = self._parse(out.read()) or _outcome(False, 'failed', 'unparseable_output',
                                                              err.read()[-300:] or 'no JSON on stdout')
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)       # only the connect process's own group
                except (ProcessLookupError, PermissionError):
                    pass
                process.wait()
                outcome = _outcome(False, 'failed', 'connect_timeout', f'no result within {self.timeout_seconds:g} s')
        result = dict(outcome, profile_id=profile_id, started_utc=started.isoformat(),
                      duration_seconds=round(time.monotonic() - began, 3))
        result.pop('bridge_connect', None)
        self._log(result)
        return result

    @staticmethod
    def _parse(stdout):
        for line in reversed((stdout or '').strip().splitlines()):           # upstream may print progress lines first
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get('bridge_connect') is True and isinstance(data.get('ok'), bool) \
                    and data.get('action') in ('started', 'already_running', 'failed') and isinstance(data.get('details'), dict):
                return data
        return None

    @staticmethod
    def _log(result):
        """Application-level log of user-triggered connection actions. Never a research table."""
        try:
            log = JsonlAppender(local_settings_dir() / 'connection_actions.jsonl')
            log.append(dict(timestamp_utc=result['started_utc'], profile_id=result['profile_id'], trigger='user',
                            action=result['action'], ok=result['ok'], reason_code=result['reason_code'],
                            duration_seconds=result['duration_seconds'], diagnostic=redact(result['diagnostic'], 300)))
            log.close()
        except OSError:
            pass


if __name__ == '__main__':
    raise SystemExit(_connect_main())
