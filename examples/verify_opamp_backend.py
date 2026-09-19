"""Verify the real bridge adapter with a restored 4 -> 4.4 -> 4 um width cycle."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import math
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus
from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend, write_json

METRICS = ('gain_db_at_start', 'bandwidth_3db_hz', 'unity_gain_hz',
           'phase_margin_estimate_deg', 'supply_power_w', 'output_dc_v')


def matching_metrics(first, second):
    return all(math.isclose(first[k], second[k], rel_tol=1e-6, abs_tol=1e-12) for k in METRICS)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['inspect', 'cycle'])
    p.add_argument('--env', type=Path, required=True)
    p.add_argument('--library', required=True)
    p.add_argument('--creation-receipt', type=Path, required=True)
    p.add_argument('--model-file', required=True)
    p.add_argument('--reference-measurements', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--state-root', type=Path, default=ROOT / 'artifacts/local/bridge-state')
    a = p.parse_args()
    if a.action == 'cycle' and a.reference_measurements is None:
        p.error('--reference-measurements is required for a cycle')
    profile = Gpdk045OtaProfile(design_file=ROOT / 'configs/gpdk045_opamp_design.json',
                                mapping_file=ROOT / 'configs/gpdk045_opamp.json',
                                reference_structure=ROOT / 'examples/circuits/gpdk045_ota5.scs',
                                reference_readback=ROOT / 'examples/circuits/gpdk045_ota5.cdf.json')
    config = BridgeConfig(a.env.resolve(), a.library, a.creation_receipt.resolve(),
                          a.state_root.resolve(), a.model_file)
    output = a.output.resolve() / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    stdout = sys.stdout
    report = {'origin': 'real', 'passed': False, 'stages': []}
    backend = VirtuosoBridgeBackend(config, profile)
    try:
        with (output / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log), backend:
            report.update(bridge_version=backend.bridge_version, session_directory=str(backend.session_dir))
            if a.action == 'inspect':
                report.update(passed=True, inspection_only=True,
                              parameters={str(k): v for k, v in backend.read_parameters().items()})
            else:
                reference = json.loads(a.reference_measurements.read_text())
                if reference['origin'] != 'real':
                    raise ValueError('Reference measurements must come from the real baseline')
                for name, width in [('baseline', 4e-6), ('width_plus_10_percent', 4.4e-6), ('restored', 4e-6)]:
                    if name == 'width_plus_10_percent':
                        backend.set_parameters(profile.assignments(width))
                    elif name == 'restored':
                        backend.restore()
                    artifact = backend.generate_netlist(output / 'exports')
                    result = backend.run_simulation(SimulationRequest(artifact, output / 'simulations',
                                                                      METRICS, 120, profile.assignments(width)))
                    stage = {'name': name, 'width_m': width, 'export_job_id': artifact.job_id,
                             'executed_sha256': artifact.sha256, 'job_id': result.job_id,
                             'directory': str(result.artifact_directory), 'status': result.status.value,
                             'metrics': result.metrics, 'elapsed_seconds': result.elapsed_seconds,
                             'timings': dict(backend.timings)}
                    report['stages'].append(stage)
                    write_json(output / 'verification.json', report)
                    print(json.dumps(stage), file=stdout, flush=True)
                    if result.status != SimulationStatus.OK:
                        raise RuntimeError(f'{name} failed: {result.reason_code}')
                    stage['operating_points'] = backend.get_operating_points()
                    if name == 'baseline' and not matching_metrics(stage['metrics'], reference['metrics']):
                        raise ValueError('Fresh baseline differs from the previously verified measurements')
                first, changed, restored = report['stages']
                report.update(same_restored_deck=first['executed_sha256'] == restored['executed_sha256'],
                              repeated_metrics=matching_metrics(first['metrics'], restored['metrics']),
                              changed_deck=first['executed_sha256'] != changed['executed_sha256'],
                              changed_response=any(not math.isclose(first['metrics'][k], changed['metrics'][k],
                                                    rel_tol=1e-5, abs_tol=1e-12) for k in METRICS),
                              restored_parameters=backend.read_parameters() == profile.assignments(4e-6))
                report['passed'] = all(report[k] for k in ('same_restored_deck', 'repeated_metrics',
                                                            'changed_deck', 'changed_response', 'restored_parameters'))
                if not report['passed']:
                    raise ValueError('Width cycle verification failed')
    except BaseException as exc:
        report.update(passed=False, error=str(exc), exception_type=type(exc).__name__)
        raise
    finally:
        write_json(output / 'verification.json', report)
        print('REPORT', output / 'verification.json', file=stdout, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
