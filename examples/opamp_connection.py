"""Explicit connection arguments for the verified, dedicated OTA test circuit."""
from pathlib import Path
import site

ROOT = Path(__file__).resolve().parents[1]


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

