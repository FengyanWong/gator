"""Virtuoso / bridge connection check (specification section 2.1).

The chain  browser -> WSL backend -> bridge package -> SSH tunnel -> daemon in the Virtuoso CIW
-> Spectre host -> license  is checked layer by layer, in dependency order, and the broken link
is named. The check OBSERVES and never repairs:

  * it never starts, restarts or stops the tunnel, the daemon or Virtuoso;
  * it never takes the adapter's session lock, never calls the adapter's ``connect()`` (which
    reads and later restores design state) and never borrows a worker's client;
  * it launches no simulation, reserves/charges no budget, writes no research table, opens no
    cellview for editing and writes to no library. It is NOT the costed baseline of section 9
    and must never be used to obtain circuit metrics;
  * the browser supplies only the IDENTIFIER of a configured profile. Hosts, ports, paths and
    commands are never accepted from a request.

This module lives outside ``analog_optimizer`` because that package's source digest gates
checkpoint loading and the experiment audits.

The one action that DOES start a tunnel - the user's explicit "Connect SSH" click - lives in
``bridge_connect.py``, deliberately apart from this module: nothing here can start anything, and
``test_the_probe_only_observes`` keeps it that way. To let the panel show the line to load in the
CIW, the tunnel layer reports the ``setup_path`` the bridge saved in its own state file (a path on
the Virtuoso host; read locally, no network contact).

Capabilities used, reconfirmed against the local virtuoso-bridge 0.8.0 source on 2026-09-20:
``importlib.metadata.version('virtuoso-bridge')``, ``env.set_runtime_env_file``,
``profile.resolve_profile``, ``remote_host_roles_from_os``, ``SSHClient.read_state`` /
``is_running``, ``VirtuosoClient.from_env`` + ``execute_skill``, ``daemon_guard.check_daemon_user``,
``list_windows`` (through the adapter's own readiness rule) and ``SpectreSimulator.check_license``.
``virtuoso-bridge status`` is deliberately NOT used: it prints into the CIW and issues many SKILL
calls, which is more than an observation.

Connection kinds (2026-09-21). A profile declares WHAT it connects to and HOW with ``"kind"``:
``virtuoso_ssh`` (the default, so files written before kinds existed keep working), ``virtuoso_local``
(Virtuoso on the backend's own machine: the bridge's local mode, no tunnel), ``ngspice_local`` and
``ngspice_ssh``. The two Virtuoso kinds share the seven layers below; for a declared kind, layer 2 also
checks that the bridge env file agrees (a profile that says "this machine" must never start an SSH
tunnel somewhere else). The ngspice kinds have their own four layers, checked by ``ngspice_link.py`` -
this module stays unable to launch anything. The monitor and the gate work per family; an action a
family cannot serve (reading a Virtuoso cell through ngspice) is refused without probing anything. Since
2026-09-23 an ngspice connection also serves ``real_simulation``: the ngspice netlist tasks run on it.
"""
from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from .paths import append_local_log, repo_root
from .security import redact
from .storage.atomic import read_json
from .storage.dataset import utcnow
# re-exported: moved to paths.py by the refactoring (docs/plan-refactoring.md)
from .paths import connection_file

VERIFIED_BRIDGE_VERSION = '0.8.0'      # mirrors the pin in analog_optimizer/backends/virtuoso_bridge.py (a test pins both)
LAYERS = ('bridge_package', 'connection_profile', 'tunnel', 'daemon', 'session_readiness', 'spectre', 'spectre_license')
STATES = ('ok', 'failed', 'not_ready', 'not_applicable', 'not_checked', 'busy', 'unknown')
CHEAP_LAYERS = LAYERS[:3]              # no contact with Virtuoso: safe for automatic checks
INTERACTIVE_LAYERS = LAYERS[:5]        # adds one read-only SKILL round trip + the readiness rule
ACTION_LAYERS = {
    'offline': (),                                   # manual editing, JSON, data export, mock runs
    'read_cellview': LAYERS[:4],
    'write_cellview': LAYERS[:5],
    'real_simulation': LAYERS,                       # baseline, start, continue
}
# ---------------------------------------------------------------------------- connection kinds
KINDS = {
    'virtuoso_ssh': dict(family='virtuoso', transport='ssh', label='Virtuoso over SSH',
                         summary='Virtuoso + Spectre on another machine, reached through the virtuoso-bridge SSH tunnel.'),
    'virtuoso_local': dict(family='virtuoso', transport='local', label='Virtuoso on this machine',
                           summary='Virtuoso + Spectre on the same machine as the workbench backend: virtuoso-bridge in '
                                   'local mode, no SSH tunnel.'),
    'ngspice_local': dict(family='ngspice', transport='local', label='ngspice on this machine',
                          summary='The ngspice program installed on the same machine as the workbench backend.'),
    'ngspice_ssh': dict(family='ngspice', transport='ssh', label='ngspice over SSH',
                        summary='The ngspice program on another machine, run through ssh (key-based login).'),
}
DEFAULT_KIND = 'virtuoso_ssh'          # a profile written before kinds existed
NGSPICE_LAYERS = ('connection_profile', 'ssh', 'ngspice', 'trial_run')
FAMILY_LAYERS = dict(virtuoso=LAYERS, ngspice=NGSPICE_LAYERS)
FAMILY_SCOPES = dict(
    virtuoso=dict(cheap=CHEAP_LAYERS, interactive=INTERACTIVE_LAYERS, full=LAYERS),
    # cheap = no contact with anything, as for Virtuoso. ngspice has no license layer, so full = interactive.
    ngspice=dict(cheap=NGSPICE_LAYERS[:1], interactive=NGSPICE_LAYERS, full=NGSPICE_LAYERS))
# What each family can serve. An ngspice connection runs the ngspice netlist tasks (ngspice_backend, 2026-09-23): a
# real run on it probes its four layers first. Reading or writing a Virtuoso cell stays a Virtuoso matter.
FAMILY_ACTIONS = dict(virtuoso=ACTION_LAYERS, ngspice={'offline': (), 'real_simulation': NGSPICE_LAYERS})
TIMEOUT_LAYER = dict(virtuoso='daemon', ngspice='ngspice')      # the layer a probe that never answered is reported on
UNSUPPORTED_ACTION = {
    'read_cellview': 'This is an ngspice connection. Reading a Virtuoso library or cell needs a Virtuoso connection: '
                     'choose one in the Connection window.',
    'write_cellview': 'This is an ngspice connection. Working on a Virtuoso cell needs a Virtuoso connection: choose one '
                      'in the Connection window.',
}


def profile_kind(settings) -> str | None:
    """The declared kind of a profile; without one it is Virtuoso over SSH. None = a kind this backend does not know."""
    kind = (settings or {}).get('kind')
    if kind is None:
        return DEFAULT_KIND
    return kind if isinstance(kind, str) and kind in KINDS else None


def family_of(kind) -> str:
    return KINDS[kind]['family'] if kind in KINDS else 'virtuoso'


def kind_of_profile(profile_id) -> str | None:
    """Kind of a CONFIGURED profile (reads the workbench's own connection file, nothing else). A profile that is
    not configured counts as the default kind: its check then names the missing profile itself."""
    settings = load_profiles()['profiles'].get(profile_id)
    return DEFAULT_KIND if settings is None else profile_kind(settings if isinstance(settings, dict) else {})


def kind_problem(settings, local):
    """(reason_code, diagnostic) when a DECLARED Virtuoso kind and the bridge env file disagree, else None.
    `local` is what the bridge resolved from its env file. An undeclared kind is never second-guessed."""
    declared = (settings or {}).get('kind')
    if declared is None:
        return None
    if declared not in KINDS:
        return 'unknown_kind', f'kind {str(declared)[:40]!r} is not one of {sorted(KINDS)}'
    if KINDS[declared]['family'] != 'virtuoso':
        return 'unknown_kind', f'kind {declared!r} is not a Virtuoso kind'
    if (KINDS[declared]['transport'] == 'local') != bool(local):
        return 'kind_mismatch', (f'the profile is declared as "{KINDS[declared]["label"]}", but the bridge env file names '
                                 f'{"this machine (localhost)" if local else "another machine"}')
    return None


LICENSE_NOTE = ('A license query is a snapshot. It does not check out or hold a seat and does not guarantee that a '
                'later simulation will obtain one.')
NEXT_STEPS = {
    'bridge_not_importable': 'Install virtuoso-bridge 0.8.0 into the backend interpreter, or set "bridge_site_packages" '
                             'for this profile in configs/local/workbench/bridge_connection.json, then check again.',
    'bridge_version_unverified': f'The existing adapter has only been verified with virtuoso-bridge {VERIFIED_BRIDGE_VERSION}. '
                                 'Install that version, or review the adapter before upgrading.',
    'connection_file_missing': 'Create configs/local/workbench/bridge_connection.json with a named profile '
                               '(see docs/workbench.md). Hosts and accounts are never guessed.',
    'profile_not_configured': 'Choose one of the configured profile identifiers.',
    'env_file_missing': 'Point "env_file" of this profile at the bridge .env file (created by `virtuoso-bridge init`).',
    'profile_incomplete': 'Complete the missing settings in the bridge .env file of this profile.',
    'implicit_profile_binding': 'The bridge resolves a different profile than the one configured. Set "profile" '
                                'explicitly (or run `virtuoso-bridge profile clear`) so runs never bind implicitly.',
    'unknown_kind': 'Set "kind" of this profile in configs/local/workbench/bridge_connection.json to one of: '
                    'virtuoso_ssh, virtuoso_local, ngspice_local, ngspice_ssh.',
    'kind_mismatch': 'The connection file and the bridge env file disagree, so nothing was started. Either change "kind" of '
                     'this profile in configs/local/workbench/bridge_connection.json, or point the bridge env file at the '
                     'machine you mean (VB_REMOTE_HOST=localhost means this machine).',
    'local_bridge_not_set_up': 'Click "Set up local bridge" in the Connection window, or run in a terminal:  '
                               'virtuoso-bridge start{profile_arg}   Then load the shown line in the Virtuoso CIW.',
    'tunnel_not_running': 'Click "Connect SSH" in this panel, or run in a terminal:  virtuoso-bridge start{profile_arg}   '
                          '(a check never starts the tunnel; only that explicit click or command does).',
    'no_response': 'Virtuoso is not running, or the bridge setup file is not loaded in the CIW. Paste the load("...") '
                   'line shown in this panel into the CIW, then test again. If the CIW says "already running", run '
                   'RBStop() there first and load it again.',
    'auth_failed': 'The daemon rejected the token. Restart the bridge from your terminal: virtuoso-bridge restart{profile_arg}',
    'daemon_user_mismatch': 'The port answers for another user\'s daemon. Use your own Virtuoso session/profile.',
    'conflicting_ade_windows': 'Close the listed ADE/Maestro/Explorer windows; the adapter refuses to run while they are open.',
    'spectre_not_found': 'Make `spectre` available on the Spectre host (PATH, VB_SPECTRE_BIN or VB_CADENCE_CSHRC in the .env).',
    'license_unavailable': 'No Spectre seat is reported free. Wait, or ask your license administrator.',
    'license_not_checkable': 'The license server gave nothing parseable (lmstat missing or no matching feature listed).',
    'probe_timeout': 'The probe did not answer in time. Check the network/tunnel and try again.',
    'busy_active_run': 'A run is using the CIW; a probe timeout during a run means busy, not failed.',
}


def layer(name, state='not_checked', reason=None, diagnostic=None, **details):
    if state not in STATES:
        raise ValueError(state)
    return dict(layer=name, state=state, reason_code=reason, diagnostic=redact(diagnostic, 600),
                details={k: v for k, v in details.items() if v is not None})


def load_profiles() -> dict:
    """{'profiles': {id: {...}}, 'active': id}. Operator-owned file; the browser only names an id."""
    data = read_json(connection_file(), default=None)
    if not isinstance(data, dict) or not isinstance(data.get('profiles'), dict):
        return dict(profiles={}, active=None, file=str(connection_file()), exists=connection_file().is_file())
    active = data.get('active') if data.get('active') in data['profiles'] else next(iter(data['profiles']), None)
    return dict(profiles=data['profiles'], active=active, file=str(connection_file()), exists=True)


def public_profiles() -> dict:
    """What the browser may see: identifiers and presence flags. Never a value that could be a secret."""
    loaded = load_profiles()

    def public(key, value):
        value = value if isinstance(value, dict) else {}
        kind = profile_kind(value)                       # None = a kind this backend does not know: shown, never guessed
        info = KINDS.get(kind, {})
        return dict(profile_id=key, bridge_profile=value.get('profile'), kind=kind, kind_declared='kind' in value,
                    family=info.get('family'), transport=info.get('transport'),
                    kind_label=info.get('label') or f"unknown kind {str(value.get('kind'))[:40]!r}",
                    settings_present=sorted(k for k, v in value.items() if v))
    return dict(active=loaded['active'], connection_file=loaded['file'], connection_file_exists=loaded['exists'],
                kinds=[dict(kind=kind, **info) for kind, info in KINDS.items()],
                profiles=[public(key, value) for key, value in loaded['profiles'].items()])


PROFILE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$')


def resolve_profile_id(profile_id):
    """Only a configured identifier is accepted. Anything else (host, path, command...) is refused."""
    if not isinstance(profile_id, str) or not PROFILE_ID.match(profile_id):
        raise ValueError('profile_id must be the identifier of a configured profile')
    loaded = load_profiles()
    if profile_id not in loaded['profiles']:
        raise KeyError(profile_id)
    return loaded['profiles'][profile_id]


def worker_environment() -> dict:
    """The environment a run worker gets. The probe uses exactly this, so `ok` predicts a run."""
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(repo_root() / 'src'), env.get('PYTHONPATH')]))
    return env


def kill_group(process) -> None:
    """SIGKILL a child's OWN process group (it was started with start_new_session) - never the backend's."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_child(argv, timeout):
    """Run `argv` in the worker environment, in a process group of its own, for at most `timeout` seconds:
    (stdout, stderr, returncode), or None when it did not finish in time - its group is then killed. The one way the
    backend waits for a bridge read, a Virtuoso write, a profile check or a connection probe."""
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               shell=False, env=worker_environment(), cwd=str(repo_root()), start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(process)
        process.communicate()
        return None
    return stdout, stderr, process.returncode


def require_gate(monitor, action, profile_id, what, *, acknowledge_unknown=False) -> dict:
    """The gate for `action`, or PermissionError('The connection gate blocked <what>') carrying the gate as `.gate` (the
    page shows its blocking layers). Every bridge read, Virtuoso write and profile check asks this way."""
    gate = monitor.gate(action, profile_id, acknowledge_unknown=acknowledge_unknown)
    if not gate['allowed']:
        error = PermissionError(f'The connection gate blocked {what}')
        error.gate = gate
        raise error
    return gate


def child_error(stderr, default, limit=400) -> RuntimeError:
    """What a failed child said last on stderr (redacted), as the error to raise."""
    lines = (stderr or '').strip().splitlines()
    return RuntimeError(redact(lines[-1] if lines else default, limit))


def json_lines(stdout):
    """The lines of a child's stdout that are JSON, parsed, from the last line up (a child may print other lines first)."""
    for line in reversed((stdout or '').strip().splitlines()):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield data


def single_flight(lock, inflight, key, work):
    """`work()` once per `key` at a time: a caller that finds one running shares its result or its exception.
    `inflight` maps a key to the Future of the call running for it and is guarded by `lock`."""
    with lock:
        future = inflight.get(key)
        owner = future is None
        if owner:
            future = inflight[key] = Future()
    if not owner:
        return future.result()
    try:
        result = work()
        future.set_result(result)
        return result
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        with lock:
            inflight.pop(key, None)


# ---------------------------------------------------------------------------- bridge facade
class RealBridge:
    """Thin facade over the installed bridge. Only observation methods exist here - there is
    deliberately no start/stop/restart/warm method to call by accident."""
    def __init__(self, settings):
        import site
        if settings.get('bridge_site_packages'):
            site.addsitedir(str(Path(settings['bridge_site_packages']).resolve()))

    def version(self):
        import importlib.metadata
        import virtuoso_bridge  # noqa: F401  (importability through THIS interpreter and import path)
        return importlib.metadata.version('virtuoso-bridge')

    def bind_env(self, env_file):
        from virtuoso_bridge.env import set_runtime_env_file
        set_runtime_env_file(Path(env_file).resolve())

    def resolve_profile(self, explicit):
        from virtuoso_bridge.profile import resolve_profile
        return resolve_profile(explicit)

    def roles(self, profile):
        from virtuoso_bridge.transport.remote_roles import remote_host_roles_from_os
        roles = remote_host_roles_from_os(profile)
        return dict(daemon_host=roles.daemon_host, spectre_host=roles.spectre_host, remote_user=roles.remote_user)

    def is_local(self, host):
        from virtuoso_bridge.transport.tunnel import _is_localhost
        return bool(host) and _is_localhost(host)

    def tunnel_state(self, profile):
        from virtuoso_bridge.transport.tunnel import SSHClient
        return SSHClient.read_state(profile), SSHClient.is_running(profile)

    def client(self, profile, timeout):
        from virtuoso_bridge import VirtuosoClient
        return VirtuosoClient.from_env(timeout=timeout, log_to_ciw=False, profile=profile)   # as the adapter does

    def skill_ok(self, client, timeout):
        from virtuoso_bridge.models import ExecutionStatus
        probe = client.execute_skill('1+1', timeout=timeout)                 # trivial and read-only
        return probe.status == ExecutionStatus.SUCCESS, [str(e) for e in (probe.errors or [])]

    def daemon_user(self, client, profile, timeout):
        from virtuoso_bridge.daemon_guard import check_daemon_user
        check = check_daemon_user(client, profile=profile, timeout=timeout)
        return dict(ok=check.ok, skipped=getattr(check, 'skipped', False), error=check.error)

    def readiness(self, client):
        """The adapter's OWN rule, called on a stand-in: the panel and the adapter cannot disagree."""
        from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
        VirtuosoBridgeBackend._check_windows(SimpleNamespace(client=client))

    def license(self, profile):
        from virtuoso_bridge.spectre.runner import SpectreSimulator
        return SpectreSimulator.from_env(profile=profile).check_license()


LICENSE_LINE = re.compile(r'Users of\s+([\w.\-]+):\s*\(Total of\s+(\d+)\s+licenses? issued;\s*Total of\s+(\d+)\s+licenses? in use\)')
SPECTRE_FEATURE = re.compile(r'(?i)(spectre|multi_mode_simulation|mmsim|virtuoso_multi_mode)')


def parse_license_lines(lines):
    """Isolated text parser. Returns feature counts only: raw license-server output can name other
    users and hosts and is never returned, logged or sent to an agent."""
    features = []
    for line in lines or []:
        match = LICENSE_LINE.search(str(line))
        if match:
            issued, used = int(match.group(2)), int(match.group(3))
            features.append(dict(feature=match.group(1), issued=issued, in_use=used, available=max(0, issued - used)))
    return features


# ---------------------------------------------------------------------------- the layers
def run_layers(bridge_factory, settings, *, scope='interactive', timeout=5.0, run_active=False, profile_error=None):
    """Check layers in dependency order. Everything downstream of a failure stays `not_checked`.

    scope: 'cheap' (layers 1-3, no Virtuoso contact), 'interactive' (1-5), 'full' (1-7).
    profile_error: (reason_code, diagnostic) when no usable profile exists. Layer 1 is STILL checked
    first, so the first broken link is named and no upstream layer is left `not_checked` behind a failure.
    """
    wanted = dict(cheap=CHEAP_LAYERS, interactive=INTERACTIVE_LAYERS, full=LAYERS)[scope]
    results = {name: layer(name) for name in LAYERS}
    settings = settings or {}
    profile = settings.get('profile') or None
    arg = f' -p {profile}' if profile else ''

    def fail(name, state, reason, diagnostic=None, **details):
        results[name] = layer(name, state, reason, diagnostic,
                              next_step=NEXT_STEPS.get(reason, '').format(profile_arg=arg) or None, **details)
        return list(results.values())

    # 1 -- bridge package
    try:
        bridge = bridge_factory(settings)
        version = bridge.version()
    except Exception as exc:
        return fail('bridge_package', 'failed', 'bridge_not_importable', f'{type(exc).__name__}: {exc}',
                    interpreter=sys.executable)
    if version != VERIFIED_BRIDGE_VERSION:
        return fail('bridge_package', 'failed', 'bridge_version_unverified', f'installed {version}',
                    installed_version=version, verified_version=VERIFIED_BRIDGE_VERSION, interpreter=sys.executable)
    results['bridge_package'] = layer('bridge_package', 'ok', installed_version=version,
                                      verified_version=VERIFIED_BRIDGE_VERSION, interpreter=sys.executable)
    # 2 -- connection profile
    if profile_error:
        return fail('connection_profile', 'failed', profile_error[0], profile_error[1])
    env_file = settings.get('env_file')
    if not env_file or not Path(env_file).is_file():
        return fail('connection_profile', 'failed', 'env_file_missing', 'the env file of this profile does not exist')
    try:
        bridge.bind_env(env_file)
        resolved = bridge.resolve_profile(profile)
        if resolved != profile:
            return fail('connection_profile', 'failed', 'implicit_profile_binding',
                        'the bridge would bind a profile that is not the configured one')
        roles = bridge.roles(profile)
    except Exception as exc:
        return fail('connection_profile', 'failed', 'profile_incomplete', f'{type(exc).__name__}: {exc}')
    local = bridge.is_local(roles.get('daemon_host'))
    missing = [name for name in ('daemon_host',) if not roles.get(name)]
    if missing:
        return fail('connection_profile', 'failed', 'profile_incomplete', f'missing settings: {missing}', missing=missing)
    disagreement = kind_problem(settings, local)          # a declared kind must match what the bridge would really do
    if disagreement:
        return fail('connection_profile', 'failed', disagreement[0], disagreement[1])
    results['connection_profile'] = layer('connection_profile', 'ok', bridge_profile=profile or '(default)',
                                          mode='local' if local else 'remote',
                                          settings={k: 'set' if v else 'not set' for k, v in roles.items()})
    # 3 -- tunnel
    try:
        state, running = bridge.tunnel_state(profile)
    except Exception as exc:
        return fail('tunnel', 'unknown', 'tunnel_state_unreadable', f'{type(exc).__name__}: {exc}')
    setup_path = (state or {}).get('setup_path') or None      # the file to load in the CIW, as the bridge saved it
    if local or (state or {}).get('mode') == 'local':
        results['tunnel'] = layer('tunnel', 'not_applicable', 'local_mode', setup_path=setup_path)
        if not state:
            return fail('daemon', 'failed', 'local_bridge_not_set_up',
                        'local mode, but the bridge has no state: it was not set up on this machine yet')
    elif not running:
        return fail('tunnel', 'failed', 'tunnel_not_running', 'no tunnel is running for this profile')
    else:
        results['tunnel'] = layer('tunnel', 'ok', setup_path=setup_path)
    if 'daemon' not in wanted:
        return list(results.values())
    # 4 -- daemon / Virtuoso CIW: one trivial read-only round trip
    client = None
    try:
        try:
            client = bridge.client(profile, timeout)
            ok, errors = bridge.skill_ok(client, timeout)
        except Exception as exc:
            timed_out = isinstance(exc, TimeoutError) or 'timed out' in str(exc).lower() or 'timeout' in str(exc).lower()
            if run_active and timed_out:
                return fail('daemon', 'busy', 'busy_active_run', 'the CIW is occupied by the active run')
            return fail('daemon', 'failed', 'no_response', f'{type(exc).__name__}: {exc}')
        if not ok:
            if any('authentication' in e.lower() for e in errors):
                return fail('daemon', 'failed', 'auth_failed', 'the daemon rejected the request')
            if run_active:
                return fail('daemon', 'busy', 'busy_active_run', 'the CIW is occupied by the active run')
            return fail('daemon', 'failed', 'no_response', '; '.join(errors)[:300] or 'no successful answer')
        try:
            user = bridge.daemon_user(client, profile, timeout)
        except Exception as exc:
            user = dict(ok=True, skipped=True, error=f'{type(exc).__name__}: {exc}')
        if not user['ok']:
            return fail('daemon', 'failed', 'daemon_user_mismatch', 'the answering daemon belongs to another user')
        results['daemon'] = layer('daemon', 'ok', user_check='skipped' if user.get('skipped') else 'matched')
        # 5 -- session readiness: the adapter's own refusal conditions
        try:
            bridge.readiness(client)
            results['session_readiness'] = layer('session_readiness', 'ok')
        except RuntimeError as exc:
            results['session_readiness'] = layer('session_readiness', 'not_ready', 'conflicting_ade_windows', str(exc),
                                                 next_step=NEXT_STEPS['conflicting_ade_windows'])
            return list(results.values())       # connectivity is fine; Spectre layers stay not_checked
        except Exception as exc:
            return fail('session_readiness', 'unknown', 'readiness_unreadable', f'{type(exc).__name__}: {exc}')
    finally:
        if client is not None:
            try:
                client.close()                  # closes only this probe's client; upstream keeps the shared tunnel
            except Exception:
                pass
    if 'spectre' not in wanted:
        return list(results.values())
    # 6 + 7 -- Spectre executable and license snapshot (one upstream call provides both)
    try:
        info = bridge.license(profile)
    except Exception as exc:
        return fail('spectre', 'unknown', 'spectre_check_failed', f'{type(exc).__name__}: {exc}')
    if not info.get('spectre_path'):
        return fail('spectre', 'failed', 'spectre_not_found', 'the executable was not found on the resolved Spectre host')
    results['spectre'] = layer('spectre', 'ok', version=redact(info.get('version'), 120))
    features = parse_license_lines(info.get('licenses'))
    relevant = [f for f in features if SPECTRE_FEATURE.search(f['feature'])]
    if not relevant:
        results['spectre_license'] = layer('spectre_license', 'unknown', 'license_not_checkable',
                                           'no Spectre-related feature could be parsed from the license server',
                                           note=LICENSE_NOTE, next_step=NEXT_STEPS['license_not_checkable'])
    elif any(f['available'] > 0 for f in relevant):
        results['spectre_license'] = layer('spectre_license', 'ok', features=relevant, note=LICENSE_NOTE)
    else:
        results['spectre_license'] = layer('spectre_license', 'failed', 'license_unavailable', features=relevant,
                                           note=LICENSE_NOTE, next_step=NEXT_STEPS['license_unavailable'])
    return list(results.values())


# ---------------------------------------------------------------------------- probe process
def _probe_main(argv=None):
    """Entry point of the short-lived probe process: prints ONE JSON object."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--scope', choices=('cheap', 'interactive', 'full'), default='interactive')
    parser.add_argument('--timeout', type=float, default=5.0)
    parser.add_argument('--run-active', action='store_true')
    args = parser.parse_args(argv)
    settings, profile_error = None, None
    try:
        settings = resolve_profile_id(args.profile_id)
    except (KeyError, ValueError) as exc:
        name = 'connection_file_missing' if not connection_file().is_file() else 'profile_not_configured'
        profile_error = (name, f'profile {args.profile_id!r}: {exc}')
    if settings is not None and profile_kind(settings) is None:
        # Which chain of layers applies is itself unknown: nothing is probed and the one problem is named.
        reason, diagnostic = kind_problem(settings, local=False)
        layers = [layer(name, 'failed', reason, diagnostic, next_step=NEXT_STEPS[reason]) if name == 'connection_profile'
                  else layer(name) for name in LAYERS]
    elif settings is not None and family_of(profile_kind(settings)) == 'ngspice':
        from . import ngspice_link                       # kept apart: what THIS module may do is pinned by its own test
        layers = ngspice_link.run_layers(ngspice_link.RealRunner(), settings, scope=args.scope, timeout=args.timeout)
    else:
        layers = run_layers(RealBridge, settings, scope=args.scope, timeout=args.timeout, run_active=args.run_active,
                            profile_error=profile_error)
    print(json.dumps(dict(layers=layers)))
    return 0


@dataclass
class ConnectionMonitor:
    """Runs probes off the request thread, coalesces concurrent requests per profile, caches results
    with their age and logs every check. Several browser tabs never multiply probes."""
    stale_after_seconds: float = 120.0
    # A passing check this recent serves a cellview gate instead of a new probe (review of 2026-09-30): a Save task, an
    # import or the window's reads gated two or three times within seconds, about 0.9 s each. See _recent_pass.
    gate_reuse_seconds: float = 30.0
    probe_timeout_seconds: float = 45.0
    probe_command: list | None = None            # tests inject a fake probe; default = this module as a process
    active_run_lookup: object = None             # callable(profile_id) -> dict | None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _inflight: dict = field(default_factory=dict)
    _results: dict = field(default_factory=dict)
    probes_started: int = 0

    def _command(self, profile_id, scope, run_active):
        base = self.probe_command or [sys.executable, '-m', 'gator_workbench.connection']
        return [*base, '--profile-id', profile_id, '--scope', scope, '--timeout', '5'] + (['--run-active'] if run_active else [])

    def check(self, profile_id, *, scope='interactive', trigger='user'):
        # run_safety: the single in-run check made after repeated infrastructure failures, once dispatch stopped.
        if trigger not in ('user', 'gate', 'auto', 'run_safety'):
            raise ValueError('trigger must be user, gate, auto or run_safety')
        if trigger == 'auto' and scope != 'cheap':
            raise ValueError('Automatic checks are limited to the cheap layers')
        if not isinstance(profile_id, str) or not PROFILE_ID.match(profile_id):
            raise ValueError('profile_id must be the identifier of a configured profile')
        # coalesced: a second check of the same profile and scope shares the probe already running
        return single_flight(self._lock, self._inflight, (profile_id, scope), lambda: self._probe(profile_id, scope, trigger))

    def _probe(self, profile_id, scope, trigger):
        active = self.active_run_lookup(profile_id) if self.active_run_lookup else None
        kind = kind_of_profile(profile_id)                      # the workbench's own file; decides which layers to expect
        family = family_of(kind)
        names, slow = FAMILY_LAYERS[family], TIMEOUT_LAYER[family]
        started, began = utcnow(), time.monotonic()
        self.probes_started += 1
        finished = run_child(self._command(profile_id, scope, bool(active)), self.probe_timeout_seconds)
        if finished is not None:
            stdout, stderr, _ = finished
            layers = self._parse(stdout, names)
            if layers is None:
                layers = [layer(n, 'unknown', 'unparseable_probe_output', stderr[-300:] if stderr else 'no JSON on stdout')
                          for n in names]
        else:                                                           # only the probe's own process group was killed
            state, reason = ('busy', 'busy_active_run') if active and family == 'virtuoso' else ('unknown', 'probe_timeout')
            layers = [layer(n, state if n == slow else 'not_checked', reason if n == slow else None,
                            next_step=NEXT_STEPS[reason] if n == slow else None) for n in names]
        result = dict(profile_id=profile_id, kind=kind, scope=scope, trigger=trigger, checked_utc=started.isoformat(),
                      duration_seconds=round(time.monotonic() - began, 3), layers=layers,
                      overall=overall_state(layers, scope, family), stale=False, age_seconds=0.0,
                      run_active=bool(active),
                      last_successful_bridge_interaction_utc=(active or {}).get('last_successful_evaluation_utc'),
                      cost=dict(evaluations_charged=0, spectre_launches=0, note='Zero-cost observation; never a baseline.'))
        with self._lock:
            self._results[profile_id] = result
        self._log(result)
        return result

    @staticmethod
    def _parse(stdout, names=LAYERS):
        for data in json_lines(stdout):
            layers = data.get('layers') if isinstance(data, dict) else None
            if isinstance(layers, list) and all(isinstance(item, dict) for item in layers) \
                    and [item.get('layer') for item in layers] == list(names) \
                    and all(item.get('state') in STATES for item in layers):
                return layers
        return None

    def status(self, profile_id):
        """Last result with its age. Before the first check, or once stale, every layer is `unknown`:
        a cached `ok` is never presented as current."""
        with self._lock:
            result = self._results.get(profile_id)
        kind = kind_of_profile(profile_id)
        if result is not None and result.get('kind') != kind:
            result = None                                # the profile was rewritten as another kind: that result is not its
        if result is None:
            return dict(profile_id=profile_id, kind=kind, checked_utc=None, age_seconds=None, stale=True, overall='unknown',
                        layers=[layer(n, 'unknown', 'never_checked') for n in FAMILY_LAYERS[family_of(kind)]])
        age = (utcnow() - _parse_time(result['checked_utc'])).total_seconds()
        if age <= self.stale_after_seconds:
            return dict(result, age_seconds=round(age, 1))
        return dict(result, age_seconds=round(age, 1), stale=True, overall='unknown',
                    layers=[dict(item, state='unknown', reason_code='stale_result', previous_state=item['state'])
                            for item in result['layers']])

    def gate(self, action, profile_id, *, acknowledge_unknown=False):
        """Pre-dispatch gate. Blocks on failed/not_ready; unknown/busy/not_checked need an explicit
        acknowledgement. A blocked start reserves nothing and creates nothing."""
        if action not in ACTION_LAYERS:
            raise KeyError(action)
        if not ACTION_LAYERS[action]:
            return dict(action=action, allowed=True, status='not_applicable', needed_layers=[], layers=[],
                        note='This action needs no bridge layer and keeps working while the bridge is down.')
        if not isinstance(profile_id, str) or not PROFILE_ID.match(profile_id):
            raise ValueError('profile_id must be the identifier of a configured profile')
        kind = kind_of_profile(profile_id)
        needed = FAMILY_ACTIONS[family_of(kind)].get(action)
        if needed is None:
            # The connection is of a kind that cannot serve this action at all. Nothing is probed: no test could change it.
            sentence = UNSUPPORTED_ACTION.get(action, f'This kind of connection ({kind}) cannot serve {action}.')
            gate = dict(action=action, allowed=False, profile_id=profile_id, connection_kind=kind, checked_utc=None,
                        status='blocked', needed_layers=[], blocking=['connection_kind'], uncertain=[],
                        acknowledged_unknown=False, bridge_version=None, next_steps=[sentence],
                        layers=[dict(layer='connection_kind', state='failed', reason_code='unsupported_by_connection_kind')])
            self._log(dict(profile_id=profile_id, trigger='gate', checked_utc=utcnow().isoformat(), duration_seconds=0.0,
                           overall='failed', layers=[dict(gate['layers'][0], diagnostic=sentence)],
                           refusal=dict(action=action, status='blocked', blocking=gate['blocking'], uncertain=[])))
            return gate
        scope = 'full' if 'spectre' in needed else 'interactive'
        reused = self._recent_pass(profile_id, kind, needed) if action != 'real_simulation' and scope == 'interactive' else None
        result = reused or self.check(profile_id, scope=scope, trigger='gate')
        relevant = [item for item in result['layers'] if item['layer'] in needed]
        blocking = [item for item in relevant if item['state'] in ('failed', 'not_ready')]
        uncertain = [item for item in relevant if item['state'] in ('unknown', 'busy', 'not_checked')]
        allowed = not blocking and (not uncertain or acknowledge_unknown)
        gate = dict(action=action, allowed=allowed, profile_id=profile_id, checked_utc=result['checked_utc'],
                    status='passed' if allowed and not uncertain else 'passed_with_acknowledged_unknown' if allowed
                    else 'blocked' if blocking else 'needs_acknowledgement',
                    needed_layers=list(needed), blocking=[i['layer'] for i in blocking],
                    uncertain=[i['layer'] for i in uncertain], acknowledged_unknown=bool(acknowledge_unknown and uncertain),
                    layers=[dict(layer=i['layer'], state=i['state'], reason_code=i['reason_code']) for i in relevant],
                    bridge_version=next((i['details'].get('installed_version') for i in result['layers']
                                         if i['layer'] == 'bridge_package'), None),
                    next_steps=[i['details'].get('next_step') for i in blocking + uncertain if i['details'].get('next_step')],
                    check_reused=reused is not None)
        if not allowed:
            self._log(dict(result, trigger='gate', refusal=dict(action=action, status=gate['status'],
                                                                 blocking=gate['blocking'], uncertain=gate['uncertain'])))
        return gate

    def _recent_pass(self, profile_id, kind, needed):
        """The last check of this profile when it may serve a cellview gate: an interactive or full check at most
        `gate_reuse_seconds` old, of the same connection kind, made with the same run state (active or not), in which every
        layer the gate needs was ok. Otherwise None, and the gate probes. A failed or uncertain result is never reused -
        the next gate tests again - and a real simulation is never gated on a reused check. What a lost link costs in those
        seconds: the child process that then works on the cell reports the bridge's own error instead of this gate's."""
        with self._lock:
            result = self._results.get(profile_id)
        if result is None or result.get('kind') != kind or result.get('scope') not in ('interactive', 'full'):
            return None
        age = (utcnow() - _parse_time(result['checked_utc'])).total_seconds()
        if not 0 <= age <= self.gate_reuse_seconds:
            return None
        states = {item['layer']: item['state'] for item in result['layers']}
        if not all(states.get(name) == 'ok' for name in needed):
            return None
        # Asked last (record 7.279): the lookup reads the run list on the D: drive, 1-2.4 s, and only a result that could
        # be reused needs it. It was asked first, so every gate that went on to probe paid for it twice.
        active = self.active_run_lookup(profile_id) if self.active_run_lookup else None
        return result if bool(active) == bool(result.get('run_active')) else None

    def _log(self, result):
        """Application-level diagnostics log. Never a research table, never an aggregate."""
        append_local_log('connection_checks.jsonl', lambda: dict(
            timestamp_utc=result['checked_utc'], profile_id=result['profile_id'], trigger=result['trigger'],
            duration_seconds=result['duration_seconds'], overall=result['overall'], refusal=result.get('refusal'),
            layers=[dict(layer=i['layer'], state=i['state'], reason_code=i['reason_code'],
                         diagnostic=redact(i['diagnostic'], 300)) for i in result['layers']]))


def _parse_time(text):
    from datetime import datetime
    return datetime.fromisoformat(text)


def overall_state(layers, scope, family='virtuoso'):
    wanted = FAMILY_SCOPES[family][scope]
    states = [item['state'] for item in layers if item['layer'] in wanted]
    for state in ('failed', 'not_ready', 'busy', 'unknown'):
        if state in states:
            return state
    if 'not_checked' in states:
        return 'unknown'
    return 'ok'


INFRASTRUCTURE_PATTERNS = (
    ('license_unavailable', re.compile(r'(?i)(licen[sc]e|lmgrd|lmstat|checkout failed|no license|FLEXnet|LMF-|SPECTRE-\d+.*licen)')),
    ('daemon_no_response', re.compile(r'(?i)(daemon|CIW|skill.*(timeout|timed out)|no response|RAMIC|bridge setup)')),
    ('bridge_unreachable', re.compile(r'(?i)(connection refused|connection reset|broken pipe|ssh|tunnel|unreachable|'
                                      r'network|socket|transport|upload failed|EOF)')),
)


def classify_infrastructure_failure(status, reason_code=None, text=None):
    """Distinct infrastructure failure types, so a lost link is distinguishable from circuit and
    convergence failures. Returns None when the failure is not an infrastructure failure."""
    if status in (None, 'ok', 'invalid_design', 'nonconverged', 'measurement_error'):
        return None
    if status == 'license_error':
        return 'license_unavailable'
    haystack = ' '.join(str(x) for x in (reason_code, text) if x)
    for name, pattern in INFRASTRUCTURE_PATTERNS:
        if pattern.search(haystack):
            return name
    if status == 'transport_error':
        return 'bridge_unreachable'
    if status in ('timeout', 'backend_error', 'execution_error'):
        return 'infrastructure_unclassified'
    return None


if __name__ == '__main__':
    raise SystemExit(_probe_main())
