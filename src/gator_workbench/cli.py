"""``gator-workbench`` command line (also ``python -m gator_workbench.cli``).

serve       start the local web workbench (127.0.0.1 by default)
validate    validate a configuration JSON file
run         prepare and execute one run in the foreground (mock tasks; real tasks need --authorize-real)
aggregates  regenerate the five research CSV tables of an experiment from saved data
check       zero-cost connection check of a configured bridge profile
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
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
    args = parser.parse_args(argv)

    if args.command == 'serve':
        import uvicorn
        from .api import create_app
        if args.host not in ('127.0.0.1', 'localhost', '::1'):
            print(f'WARNING: listening on {args.host} exposes run control beyond this machine. There is no '
                  'authentication layer; use only on a trusted network.', file=sys.stderr)
        app = create_app(extra_output_roots=args.allow_root, extra_input_roots=args.allow_input_root,
                         connection_stale_seconds=args.connection_stale_seconds,
                         auto_check_on_start=args.connection_check_on_start)
        print(f'GATOR workbench: http://{args.host}:{args.port}   (API docs: /api/docs)', flush=True)
        uvicorn.run(app, host=args.host, port=args.port, log_level='info')
        return 0

    from .schema import WorkbenchConfig
    if args.command == 'validate':
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
    if args.command == 'run':
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
        return 0 if state in ('completed', 'paused', 'stopped') else 1
    if args.command == 'aggregates':
        from .aggregates import export_aggregates
        print(json.dumps(export_aggregates(args.experiment_dir, include_mock=args.include_mock or None), indent=2))
        return 0
    if args.command == 'check':
        from .connection import ConnectionMonitor
        result = ConnectionMonitor().check(args.profile_id, scope=args.scope, trigger='user')
        for item in result['layers']:
            print(f"{item['layer']:<20} {item['state']:<15} {item['reason_code'] or ''}")
            if item['details'].get('next_step'):
                print(f"{'':<20} -> {item['details']['next_step']}")
        print(f"overall: {result['overall']}   (zero cost: no simulation, no budget)")
        return 0 if result['overall'] == 'ok' else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
