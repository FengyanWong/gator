"""Synthetic network views preserve graph identity, terminal multiplicity and parameter bindings."""
from copy import deepcopy

import pytest

from analog_optimizer.graph.circuit_graph import (
    CircuitGraph, Connection, Device, Net, ParameterBinding, ParameterGroup, ParameterValue, SourceSpan,
)
from gator_workbench import families
from gator_workbench.pdk_record import VOCABULARY_FORMAT
from gator_workbench.vocabulary import Vocabulary


@pytest.mark.parametrize('family_view', [False, True])
def test_views_remap_values_and_groups_without_mutating_the_simulator_graph(family_view):
    source = SourceSpan('synthetic.scs', 1)
    value = lambda number: ParameterValue(str(number), number, source)
    graph = CircuitGraph('synthetic', [
        Device('M', 'nmos', 'mapped', ('out', 'in', 'gnd', 'gnd'), source),
        Device('X', 'unrecognized', 'unmapped', ('out',), source),
        Device('B', 'nmos', 'mapped', ('out',), source),  # wrong pin count: no mapping
    ], [Net(name) for name in ('out', 'in', 'gnd')], [
        Connection('M', net, terminal, index, 'unknown')
        for index, (net, terminal) in enumerate(zip(('out', 'in', 'gnd', 'gnd'), ('d', 'g', 's', 'b')))
    ] + [Connection('X', 'out', 'p', 0, 'unrecognized')],
        {'M': {'w': value(1), 'width': value(2), 'length': value(3)}, 'X': {'gain': value(4)}, 'B': {'width': value(5)}},
        [ParameterGroup('sizes', 'w', 'm', 1, 0.1, 10,
                        (ParameterBinding('M', 'width', 2, 0.2, 20), ParameterBinding('B', 'width'))),
         ParameterGroup('fixed', 'dc', 'V', 1, 0, 2, (ParameterBinding('X', 'gain'),))],
        metadata={'origin': 'synthetic', 'provenance': 'mock'})
    before = deepcopy(graph)
    devices = {'mapped': {'kind': 'nmos', 'roles': ['drain', 'gate', 'source', 'bulk'],
                          'columns': {'width': 'w', 'length': 'l'}}}
    block = dict(devices=devices, pdk_id='synthetic', sha256='0' * 64)
    view = families.FamilyList(dict(block, format=families.FORMAT)) if family_view else Vocabulary(dict(
        block, format=VOCABULARY_FORMAT, version='synthetic', device_kinds=families.KINDS,
        terminal_roles=families.ROLES, net_roles=['normal'], parameters=families.PARAMETERS,
        references=families.REFERENCES))
    seen = view.view_graph(graph)
    assert graph == before and seen is not graph
    assert list(seen.parameters['M']) == ['w', 'width', 'l']  # the existing w keeps the second value under its old key
    assert seen.parameters['M']['l'] is graph.parameters['M']['length']
    assert seen.parameters['M']['width'].value == 2
    assert seen.parameters['X'] is graph.parameters['X'] and seen.parameters['B'] is graph.parameters['B']
    assert seen.parameter_groups[0].members == (ParameterBinding('M', 'w', 2, 0.2, 20), ParameterBinding('B', 'width'))
    assert seen.parameter_groups[1] is graph.parameter_groups[1]
    assert [connection.role for connection in seen.connections[:4]] == ['drain', 'gate', 'source', 'bulk']
    assert [connection.net_id for connection in seen.connections[:4]] == ['out', 'in', 'gnd', 'gnd']
    assert seen.devices[1].kind == ('unknown' if family_view else 'unrecognized')
    assert seen.connections[-1].role == ('unknown' if family_view else 'unrecognized')
    assert seen.devices[2] == graph.devices[2]
    assert seen.metadata is graph.metadata and seen.schema_version == graph.schema_version
