"""Detached run worker: ``python -m gator_workbench.worker --run-dir <dir>``.

Owns exactly one run directory (enforced by the run lock). It reads everything it needs
from that directory, so it is independent of the HTTP server, the browser and any agent
CLI session. Real Virtuoso/Spectre tasks additionally require ``--allow-real``, which the
API only passes after an explicit, budgeted user authorization.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--allow-real', action='store_true',
                        help='Permit a real Virtuoso/Spectre task (explicit user authorization only)')
    parser.add_argument('--threads', action='store_true', help='Force thread lanes instead of worker processes')
    parser.add_argument('--lock-fd', type=int, help='Inherited, already-locked run lock descriptor')
    args = parser.parse_args(argv)

    import torch
    from .engine import RunEngine
    from .layout import RunLayout
    from .schema import WorkbenchConfig
    from .storage.atomic import read_json, write_json
    from .tasks import TaskBlocked, load_task

    layout = RunLayout(args.run_dir.resolve())
    config = WorkbenchConfig.model_validate(read_json(layout.effective_config))
    manifest = read_json(layout.manifest)
    try:
        task = load_task(config.circuit, allow_real=args.allow_real)
    except TaskBlocked as exc:
        write_json(layout.status, dict(state='failed', run_id=manifest['run_id'], error=str(exc),
                                       blocker=str(exc), interface_contract=exc.contract, paths=layout.subpaths()))
        print(f'BLOCKED: {exc}', file=sys.stderr)
        return 2
    if task.mock != manifest['mock']:
        print('Mock/real provenance differs from the run manifest', file=sys.stderr)
        return 2
    # One learner thread, as in the existing training entry points; simulator threads are separate.
    torch.set_num_threads(1)
    from .engine import RunLock
    lock = None if args.lock_fd is None else RunLock.adopt(layout.control / 'run.lock', args.lock_fd)
    engine = RunEngine(layout.run_dir, task=task, use_processes=False if args.threads else None, lock=lock)

    def request_stop(signum, _frame):
        # A signal asks for the same safe sequence as the Stop button; it never kills simulators.
        from .runs import send_command
        send_command(layout.run_dir, 'stop')
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    state = engine.run()
    print(f'RUN {manifest["run_id"]} ended: {state}', flush=True)
    return 0 if state in ('completed', 'paused', 'stopped') else 1


if __name__ == '__main__':
    raise SystemExit(main())
