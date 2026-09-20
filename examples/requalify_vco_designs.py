"""Requalify feasible fast-policy VCO designs with the strict reference deck.

freeze, check and compare are offline. Only execute connects to the bridge, and it
spends at most the frozen number of reference-mode Spectre calls without retries.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from opamp_connection import add_connection_arguments
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json
from vco_requalification import (SCOPES, build_plan, compare, execute, freeze_plan,
    load_profile, read, require, validate_frozen_plan)

PROTECTED = ('ota5_v1', 'ota7_m5_v2', 'ldo_m6_v1')


def summary(plan):
    return {k: plan[k] for k in ('version', 'scope', 'sha256', 'planned_calls', 'call_cap', 'claims',
                                 'training_updates', 'automatic_retries')} | dict(designs=len(plan['designs']))


def run(args):
    plan = validate_frozen_plan(ROOT, args.plan)
    require(args.library == plan['connection']['library'] and args.model_file == plan['connection']['model_file'],
            'Connection differs from the bindings used by the pilot')
    if args.bridge_site_packages:
        import site
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    profile = load_profile(ROOT, 'reference')
    config = BridgeConfig(args.env.resolve(), args.library, args.creation_receipt.resolve(),
                          args.state_root.resolve(), args.model_file, profile=args.profile)
    directory = args.output.resolve()/uuid4().hex
    directory.mkdir(parents=True)
    write_json(directory/'plan.json', plan)
    backend = VirtuosoBridgeBackend(config, profile)
    try:
        with (directory/'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log), backend:
            def protected():
                return {cell: backend.client.schematic.read(args.library, cell, include_positions=True,
                                                            param_filters=None) for cell in PROTECTED}
            execute(plan, backend, profile, directory, protected=protected,
                    metadata=dict(session_dir=str(backend.session_dir)))
    finally:
        print('VERIFICATION', directory/'verification.json', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    freeze = commands.add_parser('freeze', help='Freeze the design list, limits and call ceiling; no simulator')
    freeze.add_argument('run_directory', type=Path)
    freeze.add_argument('--reference', type=Path, required=True, help='Saved strict baseline verification.json')
    freeze.add_argument('--scope', choices=SCOPES, default='best')
    freeze.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('check', help='Rebuild and compare a frozen plan; no simulator')
    check.add_argument('plan', type=Path)
    real = commands.add_parser('execute', help='Spend the frozen reference-mode calls through the bridge')
    real.add_argument('plan', type=Path)
    add_connection_arguments(real)
    offline = commands.add_parser('compare', help='Fast-versus-strict agreement and strict feasibility; no simulator')
    offline.add_argument('plan', type=Path)
    offline.add_argument('verification', type=Path)
    offline.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        plan = build_plan(ROOT, args.run_directory, args.reference, args.scope)
        freeze_plan(args.output, plan)
        print(json.dumps(summary(plan), indent=2))
    elif args.command == 'check':
        print(json.dumps(summary(validate_frozen_plan(ROOT, args.plan)), indent=2))
    elif args.command == 'execute':
        run(args)
    else:
        report = compare(validate_frozen_plan(ROOT, args.plan), read(args.verification))
        write_json(args.output, report)
        print(json.dumps({k: v for k, v in report.items() if k != 'comparisons'}, indent=2))
        if not report['passed']:
            raise ValueError('Fast policy disagrees with the strict reference beyond the frozen limits')


if __name__ == '__main__':
    main()
