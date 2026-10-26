"""Ordered model paths, using invented definitions only (origin=synthetic, provenance=mock)."""
from copy import deepcopy
import random

import pytest

from gator_workbench import model_scan


def _before(subckt, scan, start, end, blocked, *, behavioural=False):
    """The previous traversal, independent of the adjacency implementation."""
    edges = []
    for element in subckt['elements']:
        if len(element['nodes']) == 2:
            family = model_scan._element_family(element, subckt, scan)[0]
            edges.append((element['nodes'][0], element['nodes'][1], family or 'other'))
        elif behavioural and element['master'].lower() == 'bsource' and len(element['nodes']) > 2:
            family = model_scan._element_family(element, subckt, scan)[0]
            edges.append((element['nodes'][0], element['nodes'][1], 'behavioural' if family in (None, 'other') else family))
    found, stack = [], [(start, (), frozenset([start]))]
    while stack and len(found) < 64:
        node, families, seen = stack.pop()
        for a, b, family in edges:
            for here, there in ((a, b), (b, a)):
                if here != node:
                    continue
                if there == end:
                    found.append(families + (family,))
                elif there not in seen and there not in blocked and len(seen) < 32:
                    stack.append((there, families + (family,), seen | {there}))
    return found


def _fixture(edges):
    """Create an invented subcircuit and scan record from terminal-to-terminal elements."""
    elements = [dict(name=f'mock{i}', nodes=[a, b], master=master, sets=[])
                for i, (a, b, master) in enumerate(edges)]
    subckt = dict(name='mock_wrapper', pins=['s', 't'], models={}, elements=elements, inline=False,
                  file='/mock/invented.scs', line=1, origin='synthetic', provenance='mock')
    scan = dict(models={}, subckts={'mock_wrapper': subckt}, duplicates=[])
    return subckt, scan


def _same(subckt, scan, start='s', end='t', blocked=(), *, behavioural=False):
    """Assert path results match the original reader without mutating the input records."""
    unchanged = deepcopy((subckt, scan, blocked))
    expected = _before(subckt, scan, start, end, blocked, behavioural=behavioural)
    actual = model_scan._paths(subckt, scan, start, end, blocked, behavioural=behavioural)
    assert actual == expected
    assert (subckt, scan, blocked) == unchanged
    return actual


@pytest.mark.parametrize(('edges', 'start', 'end', 'blocked', 'expected'), [
    ([], 's', 't', (), []),
    ([('s', 't', 'resistor')], 's', 't', (), [('resistor',)]),
    ([('s', 't', 'resistor')], 't', 's', (), [('resistor',)]),
    ([('s', 't', 'resistor')], 's', 't', ('t',), [('resistor',)]),
    ([('s', 'a', 'resistor'), ('a', 't', 'capacitor')], 's', 't', ('s',), [('resistor', 'capacitor')]),
    ([('s', 'a', 'resistor'), ('a', 't', 'capacitor')], 's', 't', ('a',), []),
    ([('s', 's', 'resistor')], 's', 's', ('s',), [('resistor',), ('resistor',)]),
    ([('s', 't', 'resistor'), ('s', 't', 'resistor'), ('t', 's', 'capacitor')],
     's', 't', (), [('resistor',), ('resistor',), ('capacitor',)]),
    ([('other', 't', 'resistor')], 's', 't', (), []),
    ([('s', 't', 'invented_unknown')], 's', 't', (), [('other',)]),
])
def test_terminal_checks_orientation_and_duplicate_paths(edges, start, end, blocked, expected):
    assert _same(*_fixture(edges), start, end, blocked) == expected


def test_lifo_branch_order_keeps_direct_paths_before_deeper_paths():
    edges = [('s', 'a', 'resistor'), ('a', 't', 'capacitor'), ('s', 'b', 'inductor'),
             ('b', 't', 'resistor'), ('s', 't', 'diode')]
    assert _same(*_fixture(edges)) == [('diode',), ('inductor', 'resistor'), ('resistor', 'capacitor')]


def test_seen_end_is_accepted_even_when_it_reuses_an_edge_back_to_start():
    assert _same(*_fixture([('s', 'a', 'resistor')]), end='s') == [('resistor', 'resistor')]


@pytest.mark.parametrize('length', [31, 32, 33])
def test_seen_limit_allows_the_terminal_edge_but_not_another_internal_node(length):
    edges = [(f'n{i}', f'n{i+1}', 'resistor') for i in range(length)]
    expected = [('resistor',) * length] if length <= 32 else []
    assert _same(*_fixture(edges), 'n0', f'n{length}') == expected


def test_one_popped_node_can_add_more_than_the_outer_64_path_limit():
    families = ['resistor', 'capacitor', 'inductor'] * 23
    edges = [('s', 't', family) for family in families]
    assert _same(*_fixture(edges)) == [(family,) for family in families]


def test_path_limit_preserves_branch_order_and_finishes_the_current_node():
    edges = [('s', 'a', 'resistor'), ('s', 'b', 'diode'), ('s', 'c', 'inductor')]
    edges += [('a', 't', 'resistor')] * 40 + [('b', 't', 'capacitor')] * 40 + [('c', 't', 'diode')] * 40
    assert _same(*_fixture(edges)) == [('inductor', 'diode')] * 40 + [('diode', 'capacitor')] * 40


@pytest.mark.parametrize('behavioural', [False, True])
def test_element_classification_calls_and_order_are_unchanged(monkeypatch, behavioural):
    subckt, scan = _fixture([('s', 't', 'resistor'), ('x', 'y', 'invented_unknown')])
    subckt['elements'] += [
        dict(name='controlled_r', nodes=['s', 't', 'control'], master='bsource', sets=['r']),
        dict(name='controlled_i', nodes=['s', 't', 'control', '0'], master='BSOURCE', sets=['i']),
        dict(name='controlled_other', nodes=['s', 't', 'control'], master='bsource', sets=[]),
        dict(name='two_terminal_source', nodes=['s', 't'], master='bsource', sets=[]),
        dict(name='not_two_terminal', nodes=['s', 't', 'body'], master='diode', sets=[]),
        dict(name='one_terminal', nodes=['s'], master='bsource', sets=['r']),
        dict(name='no_terminals', nodes=[], master='bsource', sets=['r']),
    ]
    calls, original = [], model_scan._element_family

    def classify(element, *args, **kwargs):
        """Record element-classification order while retaining the original classification."""
        calls.append(element['name'])
        return original(element, *args, **kwargs)

    monkeypatch.setattr(model_scan, '_element_family', classify)
    expected = _before(subckt, scan, 's', 't', (), behavioural=behavioural)
    before_calls = calls[:]
    calls.clear()
    assert model_scan._paths(subckt, scan, 's', 't', (), behavioural=behavioural) == expected
    assert calls == before_calls == (['mock0', 'mock1'] +
                                    (['controlled_r', 'controlled_i', 'controlled_other'] if behavioural else []) +
                                    ['two_terminal_source'])
    assert expected == ([('resistor',), ('resistor',), ('behavioural',), ('behavioural',), ('other',)]
                        if behavioural else [('resistor',), ('other',)])


def _random_fixture(seed):
    """Create reproducible invented paths with mixed device kinds and parallel elements."""
    randomizer = random.Random(seed)
    nodes = ['s', 't', 'N1', 'n1', 'n.01', 'branch!', '0', 'internal/node']
    masters = ['resistor', 'capacitor', 'inductor', 'diode', 'bsource', 'invented_unknown']
    subckt, scan = _fixture([(randomizer.choice(nodes), randomizer.choice(nodes), randomizer.choice(masters))
                             for _ in range(18)])
    for element in subckt['elements']:
        if randomizer.randrange(4) == 0:
            element['nodes'].append(randomizer.choice(nodes))
        if element['master'] == 'bsource':
            element['sets'] = randomizer.choice([[], ['r'], ['c'], ['q'], ['l'], ['i']])
    subckt['elements'] += deepcopy(subckt['elements'][:2])  # Parallel elements retain separate paths.
    randomizer.shuffle(subckt['elements'])
    return subckt, scan


@pytest.mark.parametrize('seed', range(12))
@pytest.mark.parametrize('behavioural', [False, True])
def test_random_multigraphs_preserve_ordered_paths_and_inputs(seed, behavioural):
    subckt, scan = _random_fixture(seed)
    for start, end, blocked in [('s', 't', ()), ('s', 's', ('s',)),
                                ('N1', 'n1', ('0', 'branch!')), ('missing', 't', ('t',))]:
        _same(subckt, scan, start, end, blocked, behavioural=behavioural)


@pytest.mark.parametrize('disconnected', [0, 993])
def test_chain_paths_ignore_unrelated_elements_without_changing_classification(disconnected):
    edges = [(f'n{i}', f'n{i+1}', 'resistor') for i in range(31)]
    edges += [(f'x{i}', f'y{i}', 'capacitor') for i in range(disconnected)]
    assert _same(*_fixture(edges), 'n0', 'n31') == [('resistor',) * 31]


@pytest.mark.parametrize(('name', 'units', 'family'), [
    ('mock_series', (), 'diode'), ('mock_parallel', (), 'other'), ('mock_nested', (), 'resistor'),
    ('mock_behaviour', (), 'resistor'), ('mock_controlled', ('capacitance',), 'capacitor'),
    ('mock_controlled', (), 'other'), ('mock_unknown', (), 'other'),
])
def test_full_classification_and_pin_roles_match_previous_traversal(monkeypatch, name, units, family):
    text = '\n'.join([
        'model mock_diode diode',
        'subckt mock_series (s t body)', 'r1 (s inner) resistor', 'd1 (inner t) mock_diode',
        'd2 (inner body) mock_diode', 'ends mock_series',
        'subckt mock_parallel (s t)', 'r1 (s t) resistor', 'd1 (s t) mock_diode', 'ends mock_parallel',
        'subckt mock_leaf (s t)', 'r1 (s t) resistor', 'ends mock_leaf',
        'subckt mock_nested (s t)', 'x1 (s inner) mock_leaf', 'r1 (inner t) resistor', 'ends mock_nested',
        'subckt mock_behaviour (s t ctl)', 'b1 (s inner ctl) bsource r=1',
        'b2 (inner t ctl) bsource r=2', 'ends mock_behaviour',
        'subckt mock_controlled (s t ctl)', 'b1 (s t ctl) bsource i=1', 'ends mock_controlled',
        'subckt mock_unknown (s t)', 'x1 (s t) invented_undefined', 'ends mock_unknown',
    ])
    scan = model_scan.scan_model_text(text, '/mock/invented.scs')
    unchanged = deepcopy(scan)
    actual = model_scan.classify_model(name, scan, cdf_units=units)
    actual_roles = model_scan.pin_roles(name, actual, scan)
    with monkeypatch.context() as previous:
        previous.setattr(model_scan, '_paths', _before)
        expected = model_scan.classify_model(name, scan, cdf_units=units)
        expected_roles = model_scan.pin_roles(name, expected, scan)
    assert actual == expected
    assert actual_roles == expected_roles
    assert actual['family'] == family
    assert scan == unchanged
