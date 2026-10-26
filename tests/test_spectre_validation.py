"""Spectre completion checks on injected logs, without launching the simulator or contacting a license server."""

import pytest
from analog_optimizer.backends.spectre_validation import validate_completion


def test_license_information_and_zero_errors_are_not_license_failure():
    log = 'Licensing Information:\nlicense.dat\nspectre completes with 0 errors, 0 warnings, and 2 notices.\n'
    result = validate_completion(log, 0, ['license error'])
    assert result['errors'] == 0
    assert result['bridge_diagnostics'] == ['license error']
    assert result['bridge_080_license_false_positive']


@pytest.mark.parametrize('log,code,diagnostics', [
    ('spectre completes with 1 error, 0 warnings, and 0 notices.', 0, []),
    ('spectre completes with 0 errors, 0 warnings, and 0 notices.', 1, []),
    ('License denied', 0, ['license error']),
    ('Fatal error found by spectre\nspectre completes with 0 errors, 0 warnings, and 0 notices.', 0, []),
    ('spectre completes with 0 errors, 0 warnings, and 0 notices.', 0, ['unknown issue']),
])
def test_missing_or_conflicting_execution_evidence_is_rejected(log, code, diagnostics):
    with pytest.raises(ValueError):
        validate_completion(log, code, diagnostics)
