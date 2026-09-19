"""Commission the real two-stage topology and verify independent width groups.

These baseline/domain qualification samples are NOT held-out performance data.
All seven nominal DC/AC calls and every unsuccessful attempt are retained.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from opamp_connection import add_connection_arguments
from analog_optimizer.backends.backend import SimulationRequest
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json, digest
from analog_optimizer.backends.gpdk045_two_stage import Gpdk045TwoStageProfile
from analog_optimizer.evaluation.runtime import BaselineCheck


def make_profile():
    return Gpdk045TwoStageProfile(design_file=ROOT / 'configs/gpdk045_ota7_design.json',
        mapping_file=ROOT / 'configs/gpdk045_ota7.json',
        reference_structure=ROOT / 'examples/circuits/gpdk045_ota7.scs',
        reference_readback=ROOT / 'examples/circuits/gpdk045_ota7.cdf.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    args = parser.parse_args()
    if args.bridge_site_packages:
        import site
        site.addsitedir(str(args.bridge_site_packages.resolve()))
    profile = make_profile()
    config = BridgeConfig(args.env.resolve(), args.library, args.creation_receipt.resolve(),
                          args.state_root.resolve(), args.model_file, profile=args.profile)
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True)
    report = dict(origin='real', passed=False, stages=[], calls=0, domain_qualification_only=True)
    backend = VirtuosoBridgeBackend(config, profile)
    try:
        with (directory / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log), backend:
            report['session_dir'] = str(backend.session_dir)
            before = backend.read_cdf_snapshot()
            check = None
            points = [('baseline', 4e-6, 8e-6), ('input_high', 4.4e-6, 8e-6),
                      ('baseline_repeat', 4e-6, 8e-6), ('output_high', 4e-6, 8.8e-6),
                      ('both_low', 3.6e-6, 7.2e-6), ('both_high', 4.4e-6, 8.8e-6),
                      ('restored', 4e-6, 8e-6)]
            for name, first, second in points:
                backend.set_parameters(profile.assignments(first, second))
                artifact = backend.generate_netlist(directory / 'exports')
                result = backend.run_simulation(SimulationRequest(artifact, directory / 'simulations',
                    required_metrics=('gain_db_at_start', 'unity_gain_hz', 'phase_margin_estimate_deg',
                                      'supply_power_w', 'output_dc_v'),
                    parameters=profile.assignments(first, second)))
                report['calls'] += 1
                row = dict(name=name, status=result.status.value, metrics=result.metrics,
                    metric_units=result.metric_units, netlist_sha256=artifact.sha256,
                    evaluation_valid=all(result.metric_validity.values()),
                    invocations=result.simulator_invocations, job=str(result.artifact_directory))
                report['stages'].append(row)
                write_json(directory / 'verification.json', report)
                if result.status.value != 'ok' or result.simulator_invocations != 1:
                    raise RuntimeError(f'Invalid commissioning simulation: {name}: {row}')
                if name == 'baseline':
                    check = BaselineCheck(result.metrics, artifact.sha256)
                elif name in ('baseline_repeat', 'restored'):
                    check(row)
                else:
                    assert artifact.sha256 != report['stages'][0]['netlist_sha256']
                    assert result.metrics != report['stages'][0]['metrics']
            if backend.read_cdf_snapshot() != before:
                raise RuntimeError('Full two-stage CDF snapshot not restored')
            report.update(passed=True, full_snapshot_restored=True,
                reference_measurements=str(Path(report['stages'][0]['job']) / 'measurements.json'))
    except BaseException as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_json(directory / 'verification.json', report)
        print('VERIFICATION', directory / 'verification.json', flush=True)


if __name__ == '__main__':
    main()
