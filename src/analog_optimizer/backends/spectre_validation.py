"""Independent completion evidence for the verified bridge 0.8.0 runner."""
import re


def validate_completion(log_text: str, returncode: int, bridge_diagnostics: list[str]) -> dict:
    summaries = re.findall(r'^spectre completes with (\d+) errors?, (\d+) warnings?, and (\d+) notices?\.',
                           log_text, re.M | re.I)
    if returncode != 0 or len(summaries) != 1 or int(summaries[0][0]) != 0:
        raise ValueError('Spectre must exit 0 with exactly one zero-error completion summary')
    if re.search(r'^\s*(?:Fatal\b|Error\s+(?:found|\())', log_text, re.M | re.I):
        raise ValueError('Spectre log contains an explicit error/fatal marker')
    # runner.py 0.8.0 line 402 matches "license" anywhere together with
    # "error" anywhere, including the successful "0 errors" summary.
    # Preserve this diagnostic and require independent success evidence.
    if any(message != 'license error' for message in bridge_diagnostics):
        raise ValueError('Unexpected bridge diagnostics require review')
    return {'returncode': returncode, 'errors': int(summaries[0][0]),
            'warnings': int(summaries[0][1]), 'notices': int(summaries[0][2]),
            'bridge_diagnostics': bridge_diagnostics,
            'bridge_080_license_false_positive': bool(bridge_diagnostics)}
