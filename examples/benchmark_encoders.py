#!/usr/bin/env python3
"""Current synthetic encoder comparison; defaults to a budget-only preview.

The older M5/M6 entrypoints are frozen evidence. This entrypoint exposes every
current encoder and structural ablation without rewriting those scripts.
Nothing here invokes a circuit simulator or establishes transfer performance.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from analog_optimizer.evaluation.benchmark import benchmark_call_budget, run_benchmark
from analog_optimizer.evaluation.cross_category import category_tasks, load_categories
from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.models.encoders import GLOBAL_ENCODERS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--encoders', nargs='+', choices=ENCODER_TYPES, required=True)
    parser.add_argument('--heldout', choices=['opamp', 'ldo', 'vco'], default='opamp')
    parser.add_argument('--structural-encoding', choices=['none', 'rwse'],
                        help='Override structural inputs for selected global/group encoders only')
    parser.add_argument('--hidden-dim', type=int, default=48)
    parser.add_argument('--heads', type=int, default=4)
    parser.add_argument('--layers', type=int, default=4)
    parser.add_argument('--seeds', nargs='+', type=int, default=[17])
    parser.add_argument('--pretrain-steps', type=int, default=4)
    parser.add_argument('--test-steps', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--max-calls', type=int, default=300)
    parser.add_argument('--execute', action='store_true', help='Run the explicitly synthetic comparison')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/local/encoder-comparison')
    args = parser.parse_args()
    factory, schema, provenance = load_categories(ROOT)
    tasks = category_tasks(factory, args.heldout)
    settings = {key: getattr(args, key) for key in ('encoders', 'seeds', 'hidden_dim', 'heads', 'layers',
        'pretrain_steps', 'test_steps', 'batch_size', 'max_calls')}
    if args.structural_encoding is not None and not set(args.encoders).intersection(GLOBAL_ENCODERS):
        parser.error('--structural-encoding requires graph_gps or group_cross_attention')
    settings.update(spec_schema=asdict(schema), max_workers=1,
        structural_encodings={name: args.structural_encoding for name in args.encoders
                              if name in GLOBAL_ENCODERS and args.structural_encoding is not None})
    try:
        calls = benchmark_call_budget(tasks, settings)
    except ValueError as exc:
        parser.error(str(exc))
    preview = dict(origin='synthetic', planned_calls=calls, settings=settings, executed=args.execute)
    if args.execute:
        import torch
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        provenance['entrypoint_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        directory = args.output.resolve() / 'mock' / uuid4().hex
        result = run_benchmark(tasks, factory, directory, origin='synthetic', settings=settings,
                               provenance=provenance)
        preview['completed'] = result['completed']
        preview['report'] = str(directory / 'report.json')
    print(json.dumps(preview, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
