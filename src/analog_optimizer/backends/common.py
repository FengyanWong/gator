"""Helpers shared by the backends, the environment and the recording: a file's digest, a JSON file replaced whole, a
parameter assignment as rows. Moved here from virtuoso_bridge.py (which still exports them) by the optimizer clean-up
of 2026-10-09 (plan-refactoring E6)."""
import hashlib
import json
from pathlib import Path


def file_digest(path):
    """SHA-256 of a file's bytes (of a JSON value: evaluation.transfer.json_digest). virtuoso_bridge.digest names it too."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + '\n')
    temporary.replace(path)


def parameter_rows(parameters):
    return [{'device': d, 'parameter': p, 'value': value} for (d, p), value in sorted(parameters.items())]
