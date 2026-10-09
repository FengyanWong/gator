"""Check a generated profile against the LIVE cell without simulating anything.

Everything the first real evaluation does before Spectre starts, and nothing after: the adapter connects
(creation receipt, existing tunnel, no conflicting ADE/Maestro window, the cell in Virtuoso still has the
recorded sizes), Virtuoso exports the testbench netlist, the export is compared with the recorded
topology and parameters, and the simulation deck is written. No parameter is written (so the adapter has
nothing to restore), no simulator is started, no budget is touched. It exists because a generated profile
has never met the real cell through the run path: a mismatch should show up here, not in a costed run.

Explicit click only. It runs in a short-lived process like every other bridge access, because the
adapter binds the bridge environment and takes the project's session lock
(``session.lock`` in ``paths.bridge_state_dir()`` - the same lock a real run takes, so the two exclude
each other). The gate asks for the layers of ``write_cellview`` (1-5: package, profile, tunnel, daemon,
session readiness); nothing is written - those are simply the layers a netlist export needs.

Since the task flow's part 4 it is one part of the check before every run (``consistency.py``): Start runs it by itself,
and "Check now" shows its steps. A task measured by Maestro has no deck of its own yet (its run path is the next part):
its export is still compared, and the deck step says it was left out.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback

from . import tasks
from .connection import child_error, json_lines, require_gate, run_child
from .security import redact
from .storage.dataset import utcnow

STEPS = ('profile', 'connect', 'export', 'deck')
MEANING = dict(
    profile='The profile files pass the offline checks of the verified profiles.',
    connect='Connected through the run adapter: the receipt matches, no ADE/Maestro window is in the way, and the cell in '
            'Virtuoso still has the recorded sizes.',
    export='Virtuoso exported the testbench netlist; its topology and every parameter match the recorded reference.',
    deck='The simulation deck was written (not run).')
DECK_LATER = ('Not written: a task measured by Maestro gets its deck from the run path of such tasks, the next part of the '
              'build. The export above was compared all the same.')


def run(name, profile_id, work_root) -> dict:
    """In the short-lived process. Returns {ok, steps: [{step, ok, detail}], deck}."""
    from .generic_profile import RulesError
    steps, deck, backend = [], None, None

    def done(step, detail=None):
        steps.append(dict(step=step, ok=True, detail=detail or MEANING[step]))
    current = 'profile'
    try:
        config, profile, entry = tasks.generated_bridge_config(name, profile_id)
        done('profile')
        current = 'connect'
        from .cdf_write import backend_class              # the adapter the run itself uses for this task
        backend = backend_class(profile)(config, profile)
        backend.connect()
        done('connect')
        current = 'export'
        try:
            artifact = backend.generate_netlist(Path(work_root))
        except RulesError as exc:
            # A Maestro-measured task refuses only when the deck is built, after the export was read back and compared.
            if getattr(profile, 'recipe', None) != 'maestro' or 'not built yet' not in str(exc):
                raise
            done('export')
            steps.append(dict(step='deck', ok=True, skipped=True, detail=DECK_LATER))
        else:
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


def preflight(monitor, name, profile_id, *, timeout=300.0, command=None, acknowledge_unknown=False) -> dict:
    """Gate, then the check process. Raises PermissionError when the gate blocks. `acknowledge_unknown`: the start this
    check belongs to acknowledged unknown connection layers, so this gate accepts them too."""
    from . import profiles
    directory = profiles.profile_dir(name)
    if profiles.profile_entry(name) is None:
        raise KeyError(name)
    # the write gate for its layer set (1-5); nothing is written
    require_gate(monitor, 'write_cellview', profile_id, 'the check', acknowledge_unknown=acknowledge_unknown)
    work_root = directory / 'preflight' / utcnow().strftime('%Y%m%dT%H%M%S')
    work_root.mkdir(parents=True, exist_ok=True)
    argv = (command or [sys.executable, '-m', 'gator_workbench.profile_preflight']) + [
        '--name', name, '--profile-id', profile_id, '--work-root', str(work_root)]
    finished = run_child(argv, timeout)
    if finished is None:
        raise TimeoutError('The check did not finish in time')
    stdout, stderr, _ = finished
    for data in json_lines(stdout):
        if isinstance(data, dict) and data.get('profile_preflight') is True:
            (work_root / 'preflight.json').write_text(json.dumps(data, indent=1))
            return dict(data, work_root=str(work_root))
    raise child_error(stderr, 'the check gave no result')


if __name__ == '__main__':
    raise SystemExit(_main())
