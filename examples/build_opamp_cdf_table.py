"""Prepare all 161 matched-width CDF rows; compare native exports; restore OTA."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import site
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def add_connection_arguments(parser):
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--creation-receipt', type=Path, required=True)
    parser.add_argument('--model-file', required=True)
    parser.add_argument('--profile', default=None)
    parser.add_argument('--state-root', type=Path, default=ROOT / 'artifacts/local/bridge-state')
    parser.add_argument('--bridge-site-packages', type=Path)
    parser.add_argument('--output', type=Path, required=True)


def configure(args):
    if args.bridge_site_packages:
        if not args.bridge_site_packages.is_dir():
            raise ValueError('Bridge site-packages directory does not exist')
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
    from analog_optimizer.backends.virtuoso_bridge import BridgeConfig
    profile = Gpdk045OtaProfile(
        design_file=ROOT / 'configs/gpdk045_opamp_design.json',
        mapping_file=ROOT / 'configs/gpdk045_opamp.json',
        reference_structure=ROOT / 'examples/circuits/gpdk045_ota5.scs',
        reference_readback=ROOT / 'examples/circuits/gpdk045_ota5.cdf.json')
    config = BridgeConfig(args.env.resolve(), args.library, args.creation_receipt.resolve(),
                          args.state_root.resolve(), args.model_file, profile=args.profile)
    return config, profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--pdk-root', required=True, help='PDK root on the Spectre host; hashed to detect changes')
    args = parser.parse_args()
    config, profile = configure(args)
    from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
    from analog_optimizer.backends.cdf_table import build_cdf_table, pdk_fingerprint
    if args.output.exists():
        parser.error('--output must be a new directory; existing tables are never overwritten')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stdout = sys.stdout
    log_path = args.output.with_name(args.output.name + '-preparation-' + uuid4().hex + '.log')
    def progress(done, total):
        if done == 1 or done % 10 == 0 or done == total:
            print(f'CDF rows verified: {done}/{total}', file=stdout, flush=True)
    with log_path.open('x') as log, redirect_stdout(log), redirect_stderr(log):
        with VirtuosoBridgeBackend(config, profile) as backend:
            pdk = pdk_fingerprint(args.pdk_root, profile=args.profile)
            result = build_cdf_table(backend, args.output, pdk=pdk, progress=progress,
                                     verify_pdk=lambda: pdk_fingerprint(args.pdk_root, profile=args.profile))
    print('CDF_TABLE', result, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
