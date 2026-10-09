"""A Spectre job folder as the bridge leaves it, read the same way by the three measurement readers (opamp, ldo, vco):
the bridge's result record, the independent completion evidence of the simulator's log, and the folder of raw results.
Each reader still decides which checks come first."""
import json
from pathlib import Path

from analog_optimizer.backends.spectre_validation import validate_completion


def read_result(job, result_name):
    """The bridge's result record in the job folder `job` (a Path)."""
    return json.loads((job / result_name).read_text())


def completion_evidence(job, result):
    """validate_completion over the job's results/spectre.out, the bridge's return code and its diagnostics."""
    return validate_completion((job / 'results' / 'spectre.out').read_text(), result['metadata']['returncode'],
                               result['errors'])


def raw_folder(result):
    """The folder the simulator wrote its raw results to."""
    return Path(result['metadata']['output_dir'])
