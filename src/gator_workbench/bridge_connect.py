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

from dataclasses import dataclass, field
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from . import connection, directories, ngspice_link
from .paths import append_local_log, repo_root
from .run_lock import RunLock
from .security import redact, skill_string
from .storage.atomic import read_json, write_json
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
    'nothing_to_connect': 'An ngspice connection has nothing to start or to load: press "Test connection".',
})


# ---------------------------------------------------------------------------- CIW command text
def ciw_lines(setup_path) -> dict | None:
    """The text to show beside "Load in Virtuoso CIW". Mirrors the hints of `virtuoso-bridge start/status`."""
    if not setup_path or not isinstance(setup_path, str) or any(c in setup_path for c in '\x00\n\r'):
        return None
    load = f'load({skill_string(setup_path)})'
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
# Virtuoso on the backend's own machine: the same layers, but there is no SSH to talk about.
_LOCAL_LAYER_TEXT = dict(_LAYER_TEXT, daemon='The bridge is set up on this machine, but the Virtuoso CIW does not answer - load '
                                             'the command below in the CIW, then test again')
_LOCAL_REASON_TEXT = dict(_REASON_TEXT, **{
    'local_bridge_not_set_up': 'The bridge is not set up on this machine yet - click "Set up local bridge"',
    'auth_failed': 'The daemon in the CIW rejected the token',
    'daemon_user_mismatch': "The port answers for ANOTHER user's Virtuoso daemon"})
_LOCAL_TESTED = {'cheap': 'Bridge package and profile are OK (Virtuoso on this machine needs no SSH tunnel). The Virtuoso CIW '
                          'has NOT been contacted yet - click "Test connection".',
                 'interactive': 'Connected: the Virtuoso CIW on this machine answered and the session is ready.',
                 'full': 'Connected: Virtuoso CIW on this machine, session, Spectre and a free license seat are all OK.'}
_SHARED_REASON_TEXT = {
    'unknown_kind': 'The connection profile names a kind of connection this workbench does not know',
    'kind_mismatch': 'The connection profile and the bridge env file disagree about where Virtuoso runs'}
_NGSPICE_LAYER_TEXT = {
    'connection_profile': 'The connection profile is not usable',
    'ssh': 'The ngspice machine cannot be reached over SSH',
    'ngspice': 'The ngspice program was not found',
    'trial_run': 'ngspice was found, but it did not solve the built-in test circuit',
}
_NGSPICE_REASON_TEXT = {
    'probe_timeout': 'The test did not answer in time',
    'unparseable_probe_output': 'The test process gave no readable result',
    'ssh_client_missing': 'The backend machine has no `ssh` program',
    'ngspice_version_unreadable': 'A program answered, but not like ngspice'}


def _transport(result) -> str:
    """'local' or 'ssh'. What the check itself found out beats the declared kind (a profile without a kind may still
    be local); a declared kind that disagrees never gets this far - it fails layer 2."""
    layers = result.get('layers') or []
    profile = next((item for item in layers if item.get('layer') == 'connection_profile'), None)
    mode = ((profile or {}).get('details') or {}).get('mode')
    if mode in ('local', 'remote'):
        return 'local' if mode == 'local' else 'ssh'
    if any(item.get('reason_code') == 'local_mode' for item in layers):
        return 'local'
    return connection.KINDS.get(result.get('kind'), connection.KINDS[connection.DEFAULT_KIND])['transport']


def _ngspice_tested(result, transport) -> str:
    found = next((item for item in result.get('layers') or [] if item.get('layer') == 'ngspice'), None)
    version = ((found or {}).get('details') or {}).get('version')
    where = 'on this machine' if transport == 'local' else 'on the remote machine'
    if result.get('scope') == 'cheap':
        return 'The profile is complete. ngspice has NOT been contacted yet - click "Test connection".'
    return (f"Connected: {'SSH works, and ' if transport == 'ssh' else ''}ngspice{f' {version}' if version else ''} {where} "
            'answered and solved the built-in test circuit.')


def summarize(result) -> dict:
    """One sentence + the next step for a check/status result. Adds nothing the layers do not say."""
    layers = result.get('layers') or []
    if result.get('checked_utc') is None:
        return dict(level='unknown', headline='Not tested yet.', broken_layer=None, next_step=None)
    if result.get('stale'):
        return dict(level='unknown', headline='The last test is too old to trust - test again.', broken_layer=None,
                    next_step=None)
    ngspice = connection.family_of(result.get('kind')) == 'ngspice'
    transport = _transport(result)
    broken = next((item for item in layers if item.get('state') in ('failed', 'not_ready', 'busy', 'unknown')), None)
    if broken is None:
        scope = result.get('scope', 'interactive')
        tested = _LOCAL_TESTED if transport == 'local' else _TESTED
        return dict(level='ok' if scope != 'cheap' else 'partial', broken_layer=None, next_step=None,
                    headline=_ngspice_tested(result, transport) if ngspice else tested.get(scope, tested['interactive']))
    if ngspice:
        by_reason, by_layer = _NGSPICE_REASON_TEXT, _NGSPICE_LAYER_TEXT
    else:
        by_reason, by_layer = (_LOCAL_REASON_TEXT, _LOCAL_LAYER_TEXT) if transport == 'local' else (_REASON_TEXT, _LAYER_TEXT)
    reason = broken.get('reason_code')
    headline = _SHARED_REASON_TEXT.get(reason) or by_reason.get(reason) or by_layer.get(broken['layer'], broken['layer'])
    if ngspice and broken['layer'] == 'ngspice' and reason == 'ngspice_not_found':
        headline += ' on this machine' if transport == 'local' else ' on the remote machine'
    level = dict(failed='error', not_ready='warn', busy='warn').get(broken['state'], 'unknown')
    return dict(level=level, headline=f'{headline}.', broken_layer=broken['layer'], reason_code=reason,
                next_step=(broken.get('details') or {}).get('next_step'))


def describe(result) -> dict:
    """A check/status result as the panel shows it: + `summary`, + `ciw` (from the tunnel layer; Virtuoso only) and
    + what kind of connection it is, in the words the panel uses."""
    tunnel = next((item for item in result.get('layers') or [] if item.get('layer') == 'tunnel'), None)
    kind = result.get('kind')
    info = connection.KINDS.get(kind, {})
    return dict(result, summary=summarize(result), ciw=ciw_lines(((tunnel or {}).get('details') or {}).get('setup_path')),
                family=info.get('family'), transport=_transport(result) if info else None, kind_label=info.get('label'))


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
    checkout = directories.local_path('bridge_checkout', home)       # the connection module's folder (record 7.168)
    if not importable:                                                # the bridge lives in another virtualenv
        for candidate in sorted((checkout / '.venv' / 'lib').glob('python*/site-packages')):
            if any(candidate.glob('virtuoso_bridge-*.dist-info')):
                site_packages = candidate
    problems = []
    if not env_file.is_file():
        problems.append(dict(reason_code='env_file_missing', message=f'No bridge env file at {env_file}. Create it in a '
                             'terminal with:  virtuoso-bridge init <user>@<host>'))
    if not importable and site_packages is None:
        problems.append(dict(reason_code='bridge_not_found', message='virtuoso-bridge is neither importable by the backend '
                             f'interpreter ({sys.executable}) nor installed under {checkout}/.venv. A checkout elsewhere: '
                             'set "virtuoso-bridge checkout" under Folders in this window.'))
    found = dict(env_file=str(env_file), env_file_exists=env_file.is_file(), bridge_importable=importable,
                 bridge_site_packages=None if site_packages is None else str(site_packages),
                 connection_file=str(connection.connection_file()), connection_file_exists=connection.connection_file().is_file(),
                 problems=problems, can_create=not problems)
    return dict(found, kinds=_kind_setups(found, home))


def _kind_setups(bridge, home) -> list:
    """Per kind of connection: what was found on this host, what is missing, and whether "Create" can work.
    Locates programs and reads NAMES only (the Host names of ~/.ssh/config); contacts nothing."""
    bridge_checks = [dict(ok=bridge['env_file_exists'], text=f"bridge env file {bridge['env_file']}"),
                     dict(ok=bridge['bridge_importable'] or bool(bridge['bridge_site_packages']),
                          text='virtuoso-bridge is importable by the backend' if bridge['bridge_importable']
                          else f"bridge package in {bridge['bridge_site_packages']}" if bridge['bridge_site_packages']
                          else 'virtuoso-bridge package')]
    program = shutil.which('ngspice')
    ssh_program = shutil.which('ssh')
    hosts = ngspice_link.ssh_config_hosts(home)
    setups = {
        'virtuoso_ssh': dict(checks=bridge_checks, problems=bridge['problems'], can_create=bridge['can_create'],
                             note='Which machine it is stays in the bridge env file; the first Connect verifies that it is '
                                  'NOT this machine.'),
        'virtuoso_local': dict(checks=bridge_checks, problems=bridge['problems'], can_create=bridge['can_create'],
                               note='For Virtuoso on this machine the bridge env file must say VB_REMOTE_HOST=localhost; the '
                                    'first "Set up local bridge" verifies it and starts nothing if it names another machine.'),
        'ngspice_local': dict(
            checks=[dict(ok=bool(program), text=f'ngspice program {program}' if program else 'ngspice program on the PATH of the backend')],
            problems=[] if program else [dict(reason_code='ngspice_not_found', message=ngspice_link.NEXT_STEPS['ngspice_not_found'] + ' The connection can be created now and tested after that.')],
            can_create=True, note='Uses the program `ngspice` found on the PATH when it is tested, or "ngspice_bin" if you add '
                                  'that to the profile by hand.'),
        'ngspice_ssh': dict(
            checks=[dict(ok=bool(ssh_program), text=f'ssh program {ssh_program}' if ssh_program else 'ssh program on the PATH of the backend'),
                    dict(ok=bool(hosts), text=f"{len(hosts)} Host name(s) in ~/.ssh/config" if hosts else 'a Host entry in ~/.ssh/config')],
            problems=([] if ssh_program else [dict(reason_code='ssh_client_missing', message=ngspice_link.NEXT_STEPS['ssh_client_missing'])])
            + ([] if hosts else [dict(reason_code='no_ssh_host', message='The browser may only pick a machine that is already '
                                      'named on this host. Add one to ~/.ssh/config, for example:  Host simhost / HostName <address> / '
                                      'User <you>  (one setting per line), make sure  ssh simhost true  works without a password, '
                                      'then press Refresh.')]),
            can_create=bool(ssh_program and hosts), ssh_hosts=hosts,
            note='The machine is chosen by its Host name in ~/.ssh/config; its address, user, port and key stay in that file.'),
    }
    return [dict(kind=kind, label=info['label'], family=info['family'], transport=info['transport'], summary=info['summary'],
                 **setups[kind]) for kind, info in connection.KINDS.items()]


_CREATE_LOCK = threading.Lock()
BRIDGE_PROFILE = re.compile(r'^[A-Za-z0-9_]{1,32}$')          # the suffix of the VB_*_<profile> variables of the bridge env file


class ProfileExists(FileExistsError):
    pass


def create_profile(profile_id=DEFAULT_PROFILE_ID, *, kind=connection.DEFAULT_KIND, ssh_host=None, bridge_profile=None,
                   home=None) -> dict:
    """Add ONE connection profile, built from what is found on this host, to the connection file (created if
    absent). Existing profiles are operator-owned and are never changed: an identifier that exists is refused,
    every other key of the file is written back as it was, `active` is only set when the file had none, and the
    previous file is kept as a timestamped copy next to it. A file that cannot be read is never replaced."""
    if not isinstance(profile_id, str) or not connection.PROFILE_ID.match(profile_id):
        raise ValueError('profile_id must be a short identifier (letters, digits, "_", "." or "-")')
    if kind not in connection.KINDS:
        raise ValueError(f'kind must be one of {sorted(connection.KINDS)}')
    family = connection.KINDS[kind]['family']
    if bridge_profile is not None and (family != 'virtuoso' or not isinstance(bridge_profile, str)
                                       or not BRIDGE_PROFILE.match(bridge_profile)):
        raise ValueError('bridge_profile is the name of a profile in the bridge env file (letters, digits, "_"); Virtuoso only')
    if (ssh_host is not None) != (kind == 'ngspice_ssh'):
        raise ValueError('ssh_host is required for "ngspice over SSH" and accepted for nothing else')
    with _CREATE_LOCK:
        target = connection.connection_file()
        existing = None
        if target.exists():
            try:
                existing = read_json(target, default=None)
            except (OSError, ValueError):                # not JSON at all
                existing = None
            if not isinstance(existing, dict) or not isinstance(existing.get('profiles'), dict):
                raise FileExistsError(f'{target} exists but is not a readable connection file. It is never replaced: '
                                      'repair or move it by hand.')
            if profile_id in existing['profiles']:
                raise ProfileExists(f'A connection named {profile_id!r} already exists in {target}. Existing connections are '
                                    'never changed from the browser: pick another name, or edit the file by hand.')
        found = detect_setup(home)
        setup = next(item for item in found['kinds'] if item['kind'] == kind)
        if family == 'virtuoso':
            if found['problems']:
                raise SetupNotFound(found['problems'][0]['reason_code'], ' '.join(p['message'] for p in found['problems']))
            profile = dict(kind=kind, env_file=found['env_file'], profile=bridge_profile)   # null = the bridge's default profile, explicitly
            if found['bridge_site_packages']:
                profile['bridge_site_packages'] = found['bridge_site_packages']
        elif kind == 'ngspice_ssh':
            # Only a machine this HOST already names: the browser can point the backend at nothing new.
            if not isinstance(ssh_host, str) or ssh_host not in setup['ssh_hosts']:
                raise SetupNotFound('ssh_host_not_configured', 'ssh_host must be one of the Host names in ~/.ssh/config of the '
                                    'backend user. ' + (setup['problems'][-1]['message'] if setup['problems'] else ''))
            profile = dict(kind=kind, ssh_host=ssh_host)
        else:
            profile = dict(kind=kind)                    # `ngspice` from the PATH at test time; "ngspice_bin" is a hand edit
        document = dict(existing) if existing else dict(active=profile_id, profiles={})
        document['profiles'] = dict(document['profiles'], **{profile_id: profile})
        if document.get('active') not in document['profiles']:
            document['active'] = profile_id
        backup = None
        if existing is not None:
            backup = target.with_name(f"{target.name}.before-{utcnow().strftime('%Y%m%dT%H%M%SZ')}-{profile_id}")
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, document)
    note = ('Enough for connecting and testing. Real-simulation tasks also need library, creation_receipt, model_file and '
            'reference_measurements in this file (docs/workbench.md).' if family == 'virtuoso' else
            'Enough for testing and for running the ngspice netlist tasks (Project column: "ngspice netlist..."). Virtuoso '
            'cells still need a Virtuoso connection.')
    return dict(created=True, profile_id=profile_id, kind=kind, connection_file=str(target), settings_present=sorted(profile),
                backup=None if backup is None else str(backup), note=note)


class FolderBusy(RuntimeError):
    pass


def save_directories(values) -> dict:
    """Explicit click on "Save folders" in the Connection window (record 7.168): `values` = {folder: path, or None for
    the default}. Each changed value is checked before anything is written - a local folder GATOR writes into is made
    and written once - and nothing is stored unless all pass. Stored in the connection file's "directories" block, only
    the values that differ from the defaults; the connections are left as they are, the previous file is kept as a
    copy, a file that is not a readable connection file is never replaced, a missing one is made with no connection.
    The adapter state folder does not change while its session lock is held (a run, a corner check or Save task), nor
    while GATOR_BRIDGE_STATE_DIR decides it. A value of the file that fails its check is dropped when the block is
    written again; names this backend does not know are kept."""
    if not isinstance(values, dict):
        raise ValueError('values must map each folder to a path, or to null for its default')
    with _CREATE_LOCK:
        target = connection.connection_file()
        existing = None
        if target.exists():
            try:
                existing = read_json(target, default=None)
            except (OSError, ValueError):                # not JSON at all
                existing = None
            if not isinstance(existing, dict) or not isinstance(existing.get('profiles'), dict):
                raise FileExistsError(f'{target} exists but is not a readable connection file. It is never replaced: '
                                      'repair or move it by hand.')
        current = directories.saved()[0]
        wanted = dict(current)
        for key, raw in values.items():
            text = directories.normalized(key, raw)
            if text is None:
                wanted.pop(key, None)
            else:
                wanted[key] = text
        changed = [key for key in directories.FIELDS if wanted.get(key) != current.get(key)]
        for key in changed:
            field = directories.FIELDS[key]
            if field.env and os.environ.get(field.env):
                raise FolderBusy(f'{field.label}: {field.env} in the backend\'s environment decides this folder; the '
                                 'connection file\'s value would not be used. Unset it and restart the backend first.')
            if key in wanted and field.side == directories.LOCAL:
                directories.check_local(key, wanted[key])
        if 'adapter_state' in changed:
            default = directories.FIELDS['adapter_state'].default
            for folder in {current.get('adapter_state') or default, wanted.get('adapter_state') or default}:
                if RunLock.held(Path(folder).expanduser() / 'session.lock'):
                    raise FolderBusy(f'A run, a corner check or Save task holds the adapter\'s session lock in {folder}. '
                                     'Change the folder once it has finished.')
        backup = None
        if changed:
            document = dict(existing) if existing else dict(active=None, profiles={})
            block = existing.get(directories.BLOCK) if existing else None
            block = {k: v for k, v in block.items() if k not in directories.FIELDS} if isinstance(block, dict) else {}
            block.update((key, wanted[key]) for key in directories.FIELDS if key in wanted)
            if block:
                document[directories.BLOCK] = block
            else:
                document.pop(directories.BLOCK, None)
            if existing is not None:
                backup = target.with_name(f"{target.name}.before-{utcnow().strftime('%Y%m%dT%H%M%SZ')}-folders")
                shutil.copy2(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            write_json(target, document)
    return dict(directories.describe(), saved=bool(changed), changed=changed, backup=None if backup is None else str(backup))


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
    disagreement = connection.kind_problem(settings, local)
    if disagreement:                                     # "this machine" must never open a tunnel to another one
        return failed(*disagreement)
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
    if settings is not None and connection.profile_kind(settings) is None:
        outcome = _outcome(False, 'failed', *connection.kind_problem(settings, local=False))
    elif settings is not None and connection.family_of(connection.profile_kind(settings)) == 'ngspice':
        outcome = _outcome(False, 'failed', 'nothing_to_connect', 'an ngspice connection has no tunnel or daemon')
    else:
        outcome = perform_connect(TunnelBridge, settings, profile_error=profile_error)
    print(json.dumps(outcome), flush=True)
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
        return connection.single_flight(self._lock, self._inflight, profile_id, lambda: self._attempt(profile_id))

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
                connection.kill_group(process)                               # only the connect process's own group
                process.wait()
                outcome = _outcome(False, 'failed', 'connect_timeout', f'no result within {self.timeout_seconds:g} s')
        result = dict(outcome, profile_id=profile_id, started_utc=started.isoformat(),
                      duration_seconds=round(time.monotonic() - began, 3))
        result.pop('bridge_connect', None)
        self._log(result)
        return result

    @staticmethod
    def _parse(stdout):
        for data in connection.json_lines(stdout):                          # upstream may print progress lines first
            if isinstance(data, dict) and data.get('bridge_connect') is True and isinstance(data.get('ok'), bool) \
                    and data.get('action') in ('started', 'already_running', 'failed') and isinstance(data.get('details'), dict):
                return data
        return None

    @staticmethod
    def _log(result):
        """Application-level log of user-triggered connection actions. Never a research table."""
        append_local_log('connection_actions.jsonl', lambda: dict(
            timestamp_utc=result['started_utc'], profile_id=result['profile_id'], trigger='user', action=result['action'],
            ok=result['ok'], reason_code=result['reason_code'], duration_seconds=result['duration_seconds'],
            diagnostic=redact(result['diagnostic'], 300)))


if __name__ == '__main__':
    raise SystemExit(_connect_main())
