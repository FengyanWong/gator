"""ngspice connection check: the four layers of a profile of kind ``ngspice_local`` / ``ngspice_ssh``.

    connection_profile -> ssh -> ngspice -> trial_run

Same contract as the Virtuoso check in ``connection.py``: layers in dependency order, the broken link is
named, everything downstream stays ``not_checked`` - and it OBSERVES:

  * nothing is installed, started, stopped or left running: every process it launches ends with the check;
  * the trial run is ONE fixed three-element divider written by this module - never a user circuit, never a
    source of circuit metrics, no budget, no license. It is to ngspice what the ``1+1`` SKILL round trip is to
    the Virtuoso CIW: proof that the simulator really answers, not only that a file exists;
  * over SSH the deck goes to a ``mktemp`` file on the remote machine, removed again by the same command;
  * the browser names a profile and nothing else. The ssh destination and the program path come from the
    operator-owned connection file, are validated against a strict pattern BEFORE anything runs, are passed as
    argv entries (no shell on this machine; ``--`` ends ssh's own options) and never appear in a result.

SSH runs in BatchMode with the user's own ssh configuration - ports, keys and jump hosts belong in
``~/.ssh/config`` - so a missing key fails fast instead of waiting for a password.

This test is also the gate of a real run on the connection (``connection.FAMILY_ACTIONS``): the ngspice netlist
tasks (``ngspice_tasks``) run through ``ngspice_backend``, which reaches ngspice the same two ways.

Confirmed against a real ngspice-36 on 2026-09-21: ``--version`` prints ``ngspice-36``, and ``ngspice -b <deck>``
runs the ``.control`` block below and prints ``v(out) = 5.000000e-01``.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from . import connection
from .connection import NGSPICE_LAYERS, layer

SSH_HOST = re.compile(r'^(?:[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}@)?[A-Za-z0-9_][A-Za-z0-9_.\-]{0,252}$')
PROGRAM = re.compile(r'^[A-Za-z0-9_./+][A-Za-z0-9_./+\-]{0,254}$')     # a name or a path: no blank, quote or shell character
SSH_ALIAS = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$')
VERSION = re.compile(r'ngspice-(\d+(?:\.\d+)*)')
RESULT = re.compile(r'(?i)v\(out\)\s*=\s*([-+0-9.eE]+)')
EXPECTED_VOLTS = 0.5
DECK = '''* GATOR workbench connection test: a fixed resistive divider (no user circuit, no budget, no license)
v1 in 0 dc 1
r1 in out 1k
r2 out 0 1k
.control
op
print v(out)
quit
.endc
.end
'''
SSH_CONNECT_SECONDS = 8
SSH_COMMAND_SECONDS = 14           # three ssh calls at most: stays inside the monitor's 45 s probe timeout
LOCAL_SECONDS = 15
NEXT_STEPS = {
    'unknown_kind': connection.NEXT_STEPS['unknown_kind'],
    'profile_incomplete': 'An "ngspice over SSH" profile needs "ssh_host" in configs/local/workbench/bridge_connection.json: a '
                          'Host name from ~/.ssh/config (recommended) or user@host.',
    'invalid_setting': '"ssh_host" must be a Host name from ~/.ssh/config or user@host, and "ngspice_bin" a program name or '
                       'path, written with letters, digits, "_", ".", "-" and "/" only. Ports, keys and jump hosts belong '
                       'in ~/.ssh/config.',
    'ssh_client_missing': 'The `ssh` program was not found on the backend machine. Install the OpenSSH client.',
    'ssh_failed': 'SSH to the ngspice machine failed. It runs in batch mode, so it needs key-based login (it cannot ask '
                  'for a password) and an already accepted host key. Verify in a terminal:  ssh <the host of this profile> true',
    'ngspice_not_found': 'ngspice was not found on this machine. Install it (Ubuntu/Debian:  sudo apt install ngspice), or set '
                         '"ngspice_bin" of this profile to the full path of the program.',
    'ngspice_not_found_remote': 'ngspice was not found on the remote machine. A non-interactive ssh shell often has a shorter '
                                'PATH than a login shell: set "ngspice_bin" of this profile to the full path of the program there.',
    'ngspice_version_unreadable': 'The program answered --version with something that does not look like ngspice. Check '
                                  '"ngspice_bin" of this profile.',
    'trial_run_failed': 'ngspice was found but did not solve the built-in three-element test circuit. A broken installation '
                        '(missing shared libraries) is the usual cause: run  ngspice -b  on any small deck by hand to see '
                        'the full output.',
    'probe_timeout': connection.NEXT_STEPS['probe_timeout'],
}


class RealRunner:
    """The few processes of the check. argv arrays only; no shell on this machine; nothing survives the call."""
    def which(self, program):
        return shutil.which(program)

    def run(self, argv, *, timeout, stdin_text=None, cwd=None):
        feed = dict(input=stdin_text) if stdin_text is not None else dict(stdin=subprocess.DEVNULL)
        done = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, shell=False, cwd=cwd, **feed)
        return done.returncode, done.stdout or '', done.stderr or ''


def ssh_argv(host, remote_command):
    return ['ssh', '-o', 'BatchMode=yes', '-o', f'ConnectTimeout={SSH_CONNECT_SECONDS}', '--', host, remote_command]


def remote_trial_command(program):
    """One fixed remote command; `program` has passed PROGRAM, so it needs no quoting. The deck arrives on stdin."""
    return f'deck=$(mktemp) && cat > "$deck" && {program} -b "$deck"; status=$?; rm -f "$deck"; exit $status'


def ssh_config_hosts(home=None) -> list:
    """Host names (aliases) of ~/.ssh/config that name ONE machine - what "ngspice over SSH" may be created with
    from the browser. Only the names are read: HostName, User, keys and everything else stay in the file."""
    config = Path(home or os.path.expanduser('~')) / '.ssh' / 'config'
    try:
        lines = config.read_text(errors='replace').splitlines()
    except OSError:
        return []
    found = []
    for line in lines:
        words = line.split('#', 1)[0].replace('=', ' ', 1).split()
        if len(words) >= 2 and words[0].lower() == 'host':
            found += [word for word in words[1:] if SSH_ALIAS.match(word) and word not in found]   # no *, ?, ! patterns
    return found


def _tail(*texts, lines=3):
    kept = [line.strip() for text in texts for line in (text or '').splitlines() if line.strip()]
    return ' | '.join(kept[-lines:])


def run_layers(runner, settings, *, scope='interactive', timeout=5.0):
    """Check the ngspice layers in dependency order. `timeout` is accepted for symmetry with the Virtuoso check;
    the limits that matter here are the constants above."""
    wanted = connection.FAMILY_SCOPES['ngspice'][scope]
    results = {name: layer(name) for name in NGSPICE_LAYERS}
    settings = settings or {}
    kind = settings.get('kind')
    remote = kind == 'ngspice_ssh'
    host = settings.get('ssh_host')

    def scrub(text):
        """The ssh destination never leaves in a diagnostic (ssh names it in its own error lines)."""
        text = str(text or '')
        for secret in sorted({part for part in [host, *str(host or '').split('@')] if part}, key=len, reverse=True):
            text = text.replace(secret, '<ssh host>')
        return text

    def fail(name, state, reason, diagnostic=None, *, step=None, **details):
        results[name] = layer(name, state, reason, scrub(diagnostic) if diagnostic else None,
                              next_step=NEXT_STEPS.get(step or reason), **details)
        return list(results.values())

    def call(argv, **kwargs):
        """(returncode, stdout, stderr), or a string naming why there is no answer."""
        try:
            return runner.run(argv, **kwargs)
        except subprocess.TimeoutExpired:
            return 'probe_timeout'
        except OSError as exc:
            return f'{type(exc).__name__}: {exc}'

    # 1 -- connection profile: only the workbench's own file is read; nothing is contacted
    if kind not in ('ngspice_local', 'ngspice_ssh'):
        return fail('connection_profile', 'failed', 'unknown_kind', f'kind {str(kind)[:40]!r} is not an ngspice kind')
    program = settings.get('ngspice_bin') or 'ngspice'
    if not isinstance(program, str) or not PROGRAM.match(program):
        return fail('connection_profile', 'failed', 'invalid_setting', '"ngspice_bin" is not a plain program name or path')
    if remote and not host:
        return fail('connection_profile', 'failed', 'profile_incomplete', 'missing settings: ["ssh_host"]', missing=['ssh_host'])
    if remote and (not isinstance(host, str) or not SSH_HOST.match(host)):
        host = None                                      # never echoed, never scrubbed against: it is not a host
        return fail('connection_profile', 'failed', 'invalid_setting', '"ssh_host" is not a Host name or user@host')
    results['connection_profile'] = layer('connection_profile', 'ok', mode='remote' if remote else 'local',
                                          settings=dict(ngspice_bin='set' if settings.get('ngspice_bin') else 'default (ngspice)',
                                                        ssh_host='set' if remote else 'not used'))
    if 'ssh' not in wanted:
        return list(results.values())
    # 2 -- ssh: can a command be run on the remote machine at all?
    if not remote:
        results['ssh'] = layer('ssh', 'not_applicable', 'local_mode')
    else:
        if not runner.which('ssh'):
            return fail('ssh', 'failed', 'ssh_client_missing', 'no `ssh` on the PATH of the backend')
        answer = call(ssh_argv(host, 'true'), timeout=SSH_COMMAND_SECONDS)
        if answer == 'probe_timeout':
            return fail('ssh', 'unknown', 'probe_timeout', f'no answer within {SSH_COMMAND_SECONDS} s')
        if isinstance(answer, str) or answer[0] != 0:
            return fail('ssh', 'failed', 'ssh_failed', answer if isinstance(answer, str)
                        else _tail(answer[2], lines=1) or f'ssh ended with exit code {answer[0]}')
        results['ssh'] = layer('ssh', 'ok')
    # 3 -- the ngspice program: found, and it says it is ngspice
    missing = 'ngspice_not_found_remote' if remote else 'ngspice_not_found'
    if remote:
        answer = call(ssh_argv(host, f'{program} --version'), timeout=SSH_COMMAND_SECONDS)
    else:
        located = runner.which(program)
        if not located:
            return fail('ngspice', 'failed', 'ngspice_not_found', f'`{program}` is not an executable on the PATH of the backend',
                        step=missing)
        answer = call([located, '--version'], timeout=LOCAL_SECONDS)
    if answer == 'probe_timeout':
        return fail('ngspice', 'unknown', 'probe_timeout', 'ngspice --version did not answer in time')
    if isinstance(answer, str):
        return fail('ngspice', 'failed', 'ngspice_not_found', answer, step=missing)
    code, out, err = answer
    if remote and code == 255:
        return fail('ngspice', 'unknown', 'ssh_failed', _tail(err, lines=1) or 'ssh ended with exit code 255')
    if code in (126, 127):                               # the remote shell: found-but-not-executable / not found
        return fail('ngspice', 'failed', 'ngspice_not_found', _tail(err, lines=1) or f'exit code {code}', step=missing)
    version = VERSION.search(out + '\n' + err)
    if code != 0 or 'ngspice' not in (out + err).lower():
        return fail('ngspice', 'unknown', 'ngspice_version_unreadable', _tail(out, err) or f'exit code {code}')
    results['ngspice'] = layer('ngspice', 'ok', version=version.group(1) if version else None,
                               program=None if remote else located)
    if 'trial_run' not in wanted:
        return list(results.values())
    # 4 -- trial run: the fixed divider, solved for real
    if remote:
        answer = call(ssh_argv(host, remote_trial_command(program)), timeout=SSH_COMMAND_SECONDS, stdin_text=DECK)
    else:
        with tempfile.TemporaryDirectory(prefix='gator-ngspice-check-') as folder:
            deck = Path(folder) / 'divider.cir'
            deck.write_text(DECK)
            answer = call([located, '-b', str(deck)], timeout=LOCAL_SECONDS, cwd=folder)
    if answer == 'probe_timeout':
        return fail('trial_run', 'unknown', 'probe_timeout', 'the built-in test circuit did not finish in time')
    if isinstance(answer, str):
        return fail('trial_run', 'failed', 'trial_run_failed', answer)
    code, out, err = answer
    measured = RESULT.search(out)
    try:
        volts = float(measured.group(1)) if measured else None
    except ValueError:
        volts = None
    if volts is None or abs(volts - EXPECTED_VOLTS) > 1e-6:
        return fail('trial_run', 'failed', 'trial_run_failed', _tail(out, err) or f'exit code {code}, no v(out) in the output')
    results['trial_run'] = layer('trial_run', 'ok', measured='v(out) = 0.5 V on a fixed 1 V divider',
                                 note='A built-in three-element circuit: no user circuit, no budget, no license.')
    return list(results.values())
