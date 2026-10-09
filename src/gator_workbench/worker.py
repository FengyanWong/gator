"""Detached run worker: ``python -m gator_workbench.worker --run-dir <dir>``.

Owns exactly one run directory (enforced by the run lock). It reads everything it needs
from that directory, so it is independent of the HTTP server, the browser and any agent
CLI session. Real Virtuoso/Spectre tasks additionally require ``--allow-real``, which the
API only passes after an explicit, budgeted user authorization.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
from .names import CLEAN_EXIT_STATES


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--allow-real', action='store_true',
                        help='Permit a real Virtuoso/Spectre task (explicit user authorization only)')
    parser.add_argument('--threads', action='store_true', help='Force thread lanes instead of worker processes')
    parser.add_argument('--lock-fd', type=int, help='Inherited, already-locked run lock descriptor')
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    # Everything before engine.run() can fail: a module another session is half-way through editing, a configuration or
    # task hash that no longer matches after schema.py/compile.py changed, a mock/real mismatch. Such a run used to stay
    # `created` for ever with no error on the page (the traceback went to logs/worker.log only, review of 2026-09-29).
    try:
        import torch
        from .engine import RunEngine  # lazy: in the try: a failure of the import is handled with the rest
        from .layout import RunLayout  # lazy: in the try: a failure of the import is handled with the rest
        from .schema import WorkbenchConfig  # lazy: in the try: a failure of the import is handled with the rest
        # lazy: in the try: a failure of the import is handled with the rest
        from .storage.atomic import read_json, write_json
        from .tasks import TaskBlocked, load_task  # lazy: in the try: a failure of the import is handled with the rest

        layout = RunLayout(run_dir)
        config = WorkbenchConfig.model_validate(read_json(layout.effective_config))
        manifest = read_json(layout.manifest)
        try:
            # The profile the gate checked is the profile the run uses - never silently the active one.
            task = load_task(config.circuit, allow_real=args.allow_real, profile_id=config.run.connection_profile_id)
            if not task.mock and not args.allow_real:
                # lazy: in the try: a failure of the import is handled with the rest
                from .tasks import REAL_AUTHORIZATION_REQUIRED
                raise TaskBlocked(REAL_AUTHORIZATION_REQUIRED)
        except TaskBlocked as exc:
            write_json(layout.status, dict(state='failed', run_id=manifest['run_id'], error=str(exc),
                                           blocker=str(exc), interface_contract=exc.contract, paths=layout.subpaths()))
            print(f'BLOCKED: {exc}', file=sys.stderr)
            return 2
        if task.mock != manifest['mock']:
            print('Mock/real provenance differs from the run manifest', file=sys.stderr)
            _record_failed_start(run_dir, 'Mock/real provenance differs from the run manifest')
            return 2
        # One learner thread, as in the existing training entry points; simulator threads are separate.
        torch.set_num_threads(1)
        from .run_lock import RunLock  # lazy: in the try: a failure of the import is handled with the rest
        lock = None if args.lock_fd is None else RunLock.adopt(layout.run_lock, args.lock_fd)
        engine = RunEngine(layout.run_dir, task=task, use_processes=False if args.threads else None, lock=lock)
    except Exception as exc:
        _record_failed_start(run_dir, exc)
        raise                          # the traceback still goes to logs/worker.log, and the exit status is 1

    def request_stop(signum, _frame):
        # A signal asks for the same safe sequence as the Stop button; it never kills simulators.
        from .runs import send_command
        send_command(layout.run_dir, 'stop')
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    state = engine.run()
    print(f'RUN {manifest["run_id"]} ended: {state}', flush=True)
    return 0 if state in CLEAN_EXIT_STATES else 1


RESUMABLE = ('paused', 'stopped', 'interrupted')      # the states Run status offers Continue for (RunTabs.tsx)


def _record_failed_start(run_dir: Path, problem) -> None:
    """status.json says `failed` with the reason (a text, or the exception, redacted), in the shape of the TaskBlocked
    answer; the engine reports everything after its start itself. With as few imports as possible: the module that
    failed may be one of them, so plain JSON and a rename are the fallback."""
    manifest = run_dir / 'run_manifest.json'
    if not manifest.is_file():                             # not a run directory: nothing is written, nothing created
        return
    if isinstance(problem, BaseException):
        try:
            from .security import redact  # lazy: in the try: a failure of the import is handled with the rest
            problem = redact(f'{type(problem).__name__}: {problem}', 2000)
        except Exception:                                  # not even redaction imports: only the type is said
            problem = f'{type(problem).__name__} (see logs/worker.log)'
    status = dict(state='failed', run_id=None, error=problem)
    try:
        facts = json.loads(manifest.read_text(encoding='utf8'))
        status['run_id'] = facts.get('run_id')
        # A continued run that cannot start keeps the state it rested in, with the reason: `failed` would take Continue
        # away from the page for good, although the cause (a half-edited module, a changed schema) may be gone tomorrow.
        previous = json.loads((run_dir / 'status.json').read_text(encoding='utf8'))
        if (facts.get('segments') or [{}])[-1].get('entry') == 'resume' and previous.get('state') in RESUMABLE:
            status = dict(previous, error=problem)
    except Exception:
        pass
    try:
        from .layout import RunLayout  # lazy: in the try: a failure of the import is handled with the rest
        from .storage.atomic import write_json  # lazy: in the try: a failure of the import is handled with the rest
        write_json(run_dir / 'status.json', dict(status, paths=RunLayout(run_dir).subpaths()))
    except Exception:
        try:
            temporary = run_dir / f'status.json.gwtmp-{os.getpid()}'        # storage.atomic's temporary marker
            temporary.write_text(json.dumps(status, indent=2) + '\n', encoding='utf8')
            os.replace(temporary, run_dir / 'status.json')
        except OSError as exc:
            print(f'The failed start could not be recorded in status.json: {exc}', file=sys.stderr)


if __name__ == '__main__':
    raise SystemExit(main())
