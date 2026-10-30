"""The local backends' connection and parameter contract (record 7.292). MockBackend and SyntheticSizingBackend - and the
workbench's ngspice backend, in test_wb_ngspice - share LocalConnection / HeldParameters since the optimizer clean-up
(plan-refactoring E8); each still refuses in its own words. These tests pass on the code before that step too, except
the last: the synthetic backend's generate_netlist took no `condition` keyword before."""
import math

import pytest

from analog_optimizer.backends.backend import BackendNotConnected, UnsupportedCapability
from analog_optimizer.backends.mock import MockBackend
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend


def test_the_mock_backend_connects_by_a_flag_and_refuses_in_its_own_words(tmp_path):
    backend = MockBackend('R (a 0) resistor r=1k', metrics={'gain': 10})
    assert backend.connected is False
    with pytest.raises(BackendNotConnected, match=r'^Call connect\(\) before using the synthetic backend$'):
        backend.generate_netlist(tmp_path)
    backend.connect()
    assert backend.connected is True and backend.generate_netlist(tmp_path).path.is_file()
    backend.close()
    assert backend.connected is False
    with pytest.raises(BackendNotConnected, match=r'^Call connect\(\) before using the synthetic backend$'):
        backend.generate_netlist(tmp_path)
    with MockBackend('') as entered:
        assert entered.connected is True
    assert entered.connected is False


def test_the_synthetic_backend_holds_its_parameters_and_refuses_in_its_own_words(opamp, tmp_path):
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    assert backend.connected is False
    for call in (backend.restore, backend.read_parameters, lambda: backend.set_parameters({}),
                 lambda: backend.generate_netlist(tmp_path)):
        with pytest.raises(BackendNotConnected, match=r'^Synthetic sizing backend is not connected$'):
            call()
    backend.connect()
    initial = backend.read_parameters()
    assert initial == backend.initial and initial is not backend.parameters
    key = sorted(initial)[0]
    changed = {**initial, key: initial[key] * 1.1}
    backend.set_parameters(changed)
    assert backend.read_parameters() == changed and backend.parameters is not changed
    for bad in ({}, {**initial, ('nowhere', 'w'): 1.0}, {**initial, key: math.nan}, {**initial, key: math.inf}):
        with pytest.raises(ValueError, match=r'^Unexpected synthetic parameter assignment$'):
            backend.set_parameters(bad)
    assert backend.read_parameters() == changed                       # a refused assignment changes nothing
    backend.restore()
    assert backend.read_parameters() == initial
    backend.close()
    with pytest.raises(BackendNotConnected, match=r'^Synthetic sizing backend is not connected$'):
        backend.read_parameters()


def test_the_synthetic_backend_takes_the_condition_keyword_of_the_contract(opamp, tmp_path):
    """generate_netlist(work_root, *, condition=None) as VirtuosoBackend declares it (record 7.292, E8): None is its
    only condition; an explicit one is refused as the base contract refuses it."""
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    backend.connect()
    assert backend.generate_netlist(tmp_path, condition=None).path.is_file()
    with pytest.raises(UnsupportedCapability, match='Explicit simulation conditions are not implemented by this backend'):
        backend.generate_netlist(tmp_path, condition=object())
