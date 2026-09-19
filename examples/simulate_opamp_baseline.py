"""Run a real DC/AC baseline from a verified Virtuoso structure export.

The model file stays on the Spectre host. Exported default MC settings are
replaced with an explicit TT testbench; no ADE-equivalence claim is made.
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
from uuid import uuid4


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env', type=Path, required=True)
    p.add_argument('--structure', type=Path, required=True)
    p.add_argument('--model-file', required=True, help='Absolute Spectre-host path')
    p.add_argument('--section', default='tt')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--load-capacitance', help='Override only the explicit CL capacitor in this job')
    a = p.parse_args()
    if not a.model_file.startswith('/') or any(c in a.model_file for c in '\n\r"'):
        p.error('--model-file must be an absolute host path without quotes/newlines')
    if not re.fullmatch(r'[A-Za-z_]\w*', a.section):
        p.error('invalid model section')
    from virtuoso_bridge.env import set_runtime_env_file
    from virtuoso_bridge.spectre.runner import SpectreSimulator
    set_runtime_env_file(a.env.resolve())
    job_id = uuid4().hex
    job = a.output.resolve() / job_id
    job.mkdir(parents=True, exist_ok=False)
    structure = a.structure.read_text()
    if re.search(r'^\s*(include|ahdl_include|simulator|global)\b', structure, re.M):
        raise ValueError('Expected standalone exported structure, not a complete simulation deck')
    if a.load_capacitance:
        if not re.fullmatch(r'(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[munpf]?', a.load_capacitance):
            raise ValueError('Invalid capacitor override')
        structure, count = re.subn(r'(?m)^(CL\s+\(VOUT 0\)\s+capacitor\s+c=)\S+\s*$',
                                   lambda m: m[1] + a.load_capacitance, structure)
        if count != 1:
            raise ValueError('Expected exactly one verified CL (VOUT 0) capacitor')
    deck = job / 'opamp.scs'
    deck.write_text(
        'simulator lang=spectre\nglobal 0\n'
        + f'include "{a.model_file}" section={a.section}\n'
        + structure + '\n'
        + 'simulatorOptions options reltol=1e-5 vabstol=1e-8 iabstol=1e-13 temp=27 tnom=27\n'
        + 'dcOp dc\ndcOpInfo info what=oppoint where=rawfile\n'
        + 'ac ac start=10 stop=1G dec=60\n'
        + 'save VOUT VINP VINN VDD VBIAS XU1.NTAIL XU1.NLOAD VDD:p\n'
        + 'saveOptions options save=allpub\n')
    manifest = {'job_id': job_id, 'origin': 'real', 'candidate_evaluated': False,
                'bridge_version': importlib.metadata.version('virtuoso-bridge'),
                'source_structure': str(a.structure.resolve()),
                'source_sha256': hashlib.sha256(a.structure.read_bytes()).hexdigest(),
                'executed_sha256': hashlib.sha256(deck.read_bytes()).hexdigest(),
                'model_file': a.model_file, 'section': a.section, 'temperature_c': 27,
                'load_override': a.load_capacitance}
    (job / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    sim = SpectreSimulator.from_env(work_dir=job / 'results', timeout=120,
                                   output_format='psfascii', spectre_args=[], keep_remote_files=True)
    with (job / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
        result = sim.run_simulation(deck)
    manifest.update(status=result.status.value, candidate_evaluated=result.ok,
                    errors=result.errors, metadata=result.metadata)
    (job / 'result.json').write_text(json.dumps(manifest, indent=2, default=str, allow_nan=False))
    print('JOB', job, 'STATUS', result.status.value, flush=True)
    if not result.ok:
        print(result.errors)
        return 1
    from analyze_opamp_baseline import analyze
    try:
        analyze(job)
    except (ValueError, FileNotFoundError) as exc:
        manifest.update(measurement_status='error', measurement_error=str(exc))
        (job / 'result.json').write_text(json.dumps(manifest, indent=2, default=str, allow_nan=False))
        raise
    manifest['measurement_status'] = 'ok'
    (job / 'result.json').write_text(json.dumps(manifest, indent=2, default=str, allow_nan=False))
    (a.output / 'latest_job.txt').write_text(str(job) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
