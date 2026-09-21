"""Check a generated profile against the LIVE cell without simulating anything.

Everything the first real evaluation does before Spectre starts, and nothing after: the adapter connects
(creation receipt, existing tunnel, no conflicting ADE/Maestro window, the cell in Virtuoso still has the
recorded sizes), Virtuoso exports the testbench netlist, the export is compared with the recorded
topology and parameters, and the simulation deck is written. No parameter is written (so the adapter has
nothing to restore), no simulator is started, no budget is touched. It exists because a generated profile
has never met the real cell through the run path: a mismatch should show up here, not in a costed run.

Explicit click only. It runs in a short-lived process like every other bridge access, because the
adapter binds the bridge environment and takes the project's session lock
(``artifacts/local/bridge-state/session.lock`` - the same lock a real run takes, so the two exclude
each other). The gate asks for the layers of ``write_cellview`` (1-5: package, profile, tunnel, daemon,
session readiness); nothing is written - those are simply the layers a netlist export needs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import traceback

from .connection import worker_environment
from .paths import repo_root
from .security import redact
from .storage.dataset import utcnow

STEPS = ('profile', 'connect', 'export', 'deck')
MEANING = dict(
    profile='The profile files pass the offline checks of the verified profiles.',
    connect='Connected through the run adapter: the receipt matches, no ADE/Maestro window is in the way, and the cell in '
            'Virtuoso still has the recorded sizes.',
    export='Virtuoso exported the testbench netlist; its topology and every parameter match the recorded reference.',
    deck='The simulation deck was written (not run).')


def run(name, profile_id, work_root) -> dict:
    """In the short-lived process. Returns {ok, steps: [{step, ok, detail}], deck}."""
    from . import tasks
    steps, deck, backend = [], None, None

    def done(step, detail=None):
        steps.append(dict(step=step, ok=True, detail=detail or MEANING[step]))
    current = 'profile'
    try:
        config, profile, entry = tasks.generated_bridge_config(name, profile_id)
        done('profile')
        current = 'connect'
        from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
        backend = VirtuosoBridgeBackend(config, profile)
        backend.connect()
        done('connect')
        current = 'export'
        artifact = backend.generate_netlist(Path(work_root))
        done('export')
        current = 'deck'
        deck = str(artifact.path)
        tail = [line for line in Path(artifact.path).read_text().splitlines() if line.strip()][-4:]
        done('deck', MEANING['deck'] + ' Last lines: ' + ' | '.join(tail))
    except BaseException as exc:                                   # reported, never raised: the caller shows the step that failed
        steps.append(dict(step=current, ok=False, detail=redact(f'{type(exc).__name__}: {exc}', 600),
                          trace=redact(traceback.format_exc()[-1500:], 1500)))
    finally:
        if backend is not None:
            try:
                backend.close()
            except BaseException as exc:
                steps.append(dict(step='close', ok=False, detail=redact(f'{type(exc).__name__}: {exc}', 400)))
    return dict(profile_preflight=True, name=name, ok=all(s['ok'] for s in steps) and len(steps) == len(STEPS), steps=steps, deck=deck,
                simulated=False, checked_utc=utcnow().isoformat())


def _main(argv=None):
    import argparse
    from contextlib import redirect_stdout
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--work-root', required=True)
    args = parser.parse_args(argv)
    with redirect_stdout(sys.stderr):                              # the bridge prints progress; stdout carries one JSON line
        result = run(args.name, args.profile_id, args.work_root)
    print(json.dumps(result), flush=True)
    return 0


def preflight(monitor, name, profile_id, *, timeout=300.0, command=None) -> dict:
    """Gate, then the check process. Raises PermissionError when the gate blocks."""
    from . import profiles
    directory = profiles.profile_dir(name)
    if name not in profiles.list_profiles():
        raise KeyError(name)
    gate = monitor.gate('write_cellview', profile_id)              # its layer set (1-5); nothing is written
    if not gate['allowed']:
        error = PermissionError('The connection gate blocked the check')
        error.gate = gate
        raise error
    work_root = directory / 'preflight' / utcnow().strftime('%Y%m%dT%H%M%S')
    work_root.mkdir(parents=True, exist_ok=True)
    argv = (command or [sys.executable, '-m', 'gator_workbench.profile_preflight']) + [
        '--name', name, '--profile-id', profile_id, '--work-root', str(work_root)]
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               shell=False, env=worker_environment(), cwd=str(repo_root()), start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        process.communicate()
        raise TimeoutError('The check did not finish in time')
    for line in reversed((stdout or '').strip().splitlines()):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get('profile_preflight') is True:
            (work_root / 'preflight.json').write_text(json.dumps(data, indent=1))
            return dict(data, work_root=str(work_root))
    raise RuntimeError(redact((stderr or '').strip().splitlines()[-1] if (stderr or '').strip() else 'the check gave no result', 400))


if __name__ == '__main__':
    raise SystemExit(_main())
