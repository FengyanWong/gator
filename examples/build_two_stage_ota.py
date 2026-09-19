"""Create an independent two-stage OTA while holding the existing session lock.

Connection arguments identify the ORIGINAL five-MOS baseline for protection.
The new names/configuration are taken from gpdk045_ota7_design.json; existing
cells are refused, and no existing schematic is reconfigured.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from opamp_connection import add_connection_arguments, configure
from build_opamp_baseline import build, export
from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--remote-library-path', required=True)
    args = parser.parse_args()
    config, profile = configure(args)
    args.output.mkdir(parents=True, exist_ok=False)
    design = json.loads((ROOT / 'configs/gpdk045_ota7_design.json').read_text())
    report = dict(completed=False, original_design_unchanged=False)
    try:
        with (args.output / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
            with VirtuosoBridgeBackend(config, profile) as backend:
                before = backend.read_cdf_snapshot()
                write_json(args.output / 'original-before.json', before)
                try:
                    build(backend.client, design, args.library, args.remote_library_path, args.output)
                    export(backend.client, design, args.library, args.output)
                    report['completed'] = True
                finally:
                    after = backend.read_cdf_snapshot()
                    write_json(args.output / 'original-after.json', after)
                    report['original_design_unchanged'] = before == after
                    if before != after:
                        raise RuntimeError('Original five-MOS baseline changed')
    finally:
        write_json(args.output / 'build-report.json', report)
    print('BUILD', args.output, report, flush=True)


if __name__ == '__main__':
    main()
