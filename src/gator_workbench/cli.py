"""``gator-workbench`` command line (also ``python -m gator_workbench.cli``).

serve       start the local web workbench (127.0.0.1 by default)
validate    validate a configuration JSON file
run         prepare and execute one run in the foreground (mock tasks; real tasks need --authorize-real)
aggregates  regenerate the five research CSV tables of an experiment from saved data
check       zero-cost connection check of a configured bridge profile
pretrain    audit a frozen archive pool and train offline (no simulator)
compress-save-points  compress the save points of the runs under a folder, losslessly (a dry run without --apply)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from .names import CLEAN_EXIT_STATES, LOOPBACK_HOSTS

# Stopping the backend (Ctrl+C, or `kill`) waits this long for open requests, then cancels them: a request that hangs
# cannot hold the stop.
SHUTDOWN_GRACE_SECONDS = 5


def main(argv=None):
    args = _parser().parse_args(argv)
    return COMMANDS[args.command](args)


def _parser():
    parser = argparse.ArgumentParser(prog='gator-workbench', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve', help='start the web workbench')
    serve.add_argument('--host', default='127.0.0.1', help='default: local-only listening')
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--allow-root', action='append', default=[], help='additional allowed OUTPUT root (repeatable)')
    serve.add_argument('--allow-input-root', action='append', default=[], help='additional allowed netlist INPUT root')
    serve.add_argument('--connection-stale-seconds', type=float, default=120.0,
                       help='age after which a connection check result is shown as unknown (default 120)')
    serve.add_argument('--connection-check-on-start', action='store_true',
                       help='run one cheap connection check of the active profile at start (default: off - a check '
                            'runs only on a button press in the panel, and at the gate before a real action)')
    validate = sub.add_parser('validate', help='validate a configuration file')
    validate.add_argument('config', type=Path)
    run = sub.add_parser('run', help='prepare and execute one run in the foreground')
    run.add_argument('config', type=Path)
    run.add_argument('--allow-root', action='append', default=[])
    run.add_argument('--confirm-transfer', action='store_true')
    run.add_argument('--authorize-real', action='store_true', help='explicitly authorize a REAL simulation budget')
    run.add_argument('--acknowledge-unknown-connection', action='store_true')
    agg = sub.add_parser('aggregates', help='regenerate the research CSV tables')
    agg.add_argument('experiment_dir', type=Path)
    agg.add_argument('--include-mock', action='store_true')
    check = sub.add_parser('check', help='zero-cost bridge connection check')
    check.add_argument('profile_id')
    check.add_argument('--scope', choices=('cheap', 'interactive', 'full'), default='interactive')
    pretrain = sub.add_parser('pretrain', help='offline SAC from an explicit frozen archive pool')
    pretrain.add_argument('request', type=Path, help='JSON with pinned source runs, registry overrides and training settings')
    pretrain.add_argument('--output', type=Path, required=True, help='new artifact directory (never overwritten)')
    pretrain.add_argument('--audit-only', action='store_true', help='validate and split archives without training')
    compress = sub.add_parser('compress-save-points', help='compress the save points written before record 7.284')
    compress.add_argument('--root', type=Path, default=None, help="folder of experiments (default: the workbench's outputs/)")
    compress.add_argument('--apply', action='store_true', help='compress; without it, only say what would be compressed')
    compress.add_argument('--exclude', action='append', default=[],
                          help='leave the runs of experiment folders matching this pattern alone (repeatable)')
    compress.add_argument('--workers', type=int, default=4)
    return parser


def _serve(args):
    import uvicorn
    from .api import create_app
    if args.host not in LOOPBACK_HOSTS:
        print(f'WARNING: listening on {args.host} exposes run control beyond this machine. There is no '
              'authentication layer; use only on a trusted network.', file=sys.stderr)
    app = create_app(extra_output_roots=args.allow_root, extra_input_roots=args.allow_input_root,
                     connection_stale_seconds=args.connection_stale_seconds,
                     auto_check_on_start=args.connection_check_on_start, host=args.host)
    print(f'GATOR workbench: http://{args.host}:{args.port}   (API docs: /api/docs)', flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level='info', timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS)
    return 0


def _validate(args):
    from .schema import WorkbenchConfig
    from .tasks import TaskBlocked, load_task
    from .validation import validate as run_validation
    config = WorkbenchConfig.model_validate(json.loads(args.config.read_text()))
    try:
        runtime = load_task(config.circuit)
        report = run_validation(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
    except TaskBlocked as exc:
        print(f'circuit not loaded: {exc}', file=sys.stderr)
        report = run_validation(config)
    print(json.dumps(report.as_dict(), indent=2))
    return 1 if report.blocks_run else 0


def _run(args):
    from .schema import WorkbenchConfig
    import torch
    from . import runs
    from .connection import ConnectionMonitor
    from .engine import RunEngine
    from .paths import OutputRoots
    from .tasks import load_task
    torch.set_num_threads(1)
    config = WorkbenchConfig.model_validate(json.loads(args.config.read_text()))
    try:
        layout, manifest = runs.prepare_run(config, OutputRoots(args.allow_root), allow_real=args.authorize_real,
                                            confirm_transfer=args.confirm_transfer, monitor=ConnectionMonitor(),
                                            acknowledge_unknown=args.acknowledge_unknown_connection)
    except runs.RunRejected as exc:
        print(json.dumps(dict(rejected=str(exc), code=exc.code, report=exc.report), indent=2, default=str), file=sys.stderr)
        return 2
    print(f'RUN DIRECTORY: {layout.run_dir}', flush=True)
    if manifest['mock']:
        print('MOCK DATA: synthetic analytic backend; not a circuit result.', flush=True)
    task = load_task(config.circuit, allow_real=args.authorize_real, profile_id=config.run.connection_profile_id)
    state = RunEngine(layout.run_dir, task=task, lock=runs.take_lock(layout.run_dir)).run()
    print(f'STATE: {state}', flush=True)
    return 0 if state in CLEAN_EXIT_STATES else 1


def _aggregates(args):
    from .aggregates import export_aggregates
    print(json.dumps(export_aggregates(args.experiment_dir, include_mock=args.include_mock or None), indent=2))
    return 0


def _check(args):
    from .connection import ConnectionMonitor
    result = ConnectionMonitor().check(args.profile_id, scope=args.scope, trigger='user')
    for item in result['layers']:
        print(f"{item['layer']:<20} {item['state']:<15} {item['reason_code'] or ''}")
        if item['details'].get('next_step'):
            print(f"{'':<20} -> {item['details']['next_step']}")
    print(f"overall: {result['overall']}   (zero cost: no simulation, no budget)")
    return 0 if result['overall'] == 'ok' else 1


def _pretrain(args):
    from .pretrain import execute
    execute(json.loads(args.request.read_text()), args.output, audit_only=args.audit_only,
            progress=lambda row: print(json.dumps(row, allow_nan=False), flush=True))
    return 0


def _compress_save_points(args):
    from .paths import default_output_root
    from .save_point_compression import compress_save_points

    def say(folder, result):
        sizes = ' -> '.join(f'{result[k] / 1e6:.1f} MB' for k in ('before', 'after') if result.get(k) is not None)
        print(f"{result['status']:<15} {folder}  {sizes}  {result.get('reason') or ''}".rstrip(), flush=True)
    totals = compress_save_points(args.root or default_output_root(), apply=args.apply, exclude=args.exclude,
                                  workers=args.workers, progress=say)
    print(json.dumps(totals, indent=2), flush=True)
    return 1 if totals['problems'] else 0


COMMANDS = {'serve': _serve, 'validate': _validate, 'run': _run, 'aggregates': _aggregates, 'check': _check,
            'pretrain': _pretrain, 'compress-save-points': _compress_save_points}


if __name__ == '__main__':
    raise SystemExit(main())
