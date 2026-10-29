"""Matched-device seeds skip impossible peers without changing recognition or suggested ties."""
from collections import Counter
from copy import deepcopy
import random
from types import SimpleNamespace

import pytest

from gator_workbench import schema, structures


def graph_of(devices, *, rails=('0',)):
    """Invented typed pin graphs: (id, kind, model, {role: net}), never simulator or PDK inputs."""
    graph = SimpleNamespace(devices=[], connections=[], nets=[], parameters={},
                            metadata=dict(origin='synthetic', provenance='mock'))
    nets = set()
    for name, kind, model, pins in devices:
        graph.devices.append(SimpleNamespace(id=name, kind=kind, model_ref=model))
        graph.connections.extend(SimpleNamespace(device_id=name, terminal=role, role=role, net_id=net)
                                 for role, net in pins.items())
        nets.update(pins.values())
        graph.parameters[name] = {p: SimpleNamespace(value=1.0, valid=True) for p in ('w', 'l')}
    graph.nets = [SimpleNamespace(id=net, roles=('ground',) if net in rails else ()) for net in sorted(nets)]
    return graph


def mos(name, drain, gate, source, *, kind='nmos', model='nch', bulk='0'):
    """Describe one MOS device with explicit terminal roles for a synthetic graph."""
    return name, kind, model, dict(drain=drain, gate=gate, source=source, bulk=bulk)


def global_groups(devices):
    """Original candidate enumeration: every later transistor, before the unchanged electrical predicates."""
    order = list(devices)
    return {name: (order, index) for index, name in enumerate(order)}


def previous_recognition(graph, monkeypatch):
    """Run structure recognition with the original global candidate groups."""
    with monkeypatch.context() as patch:
        patch.setattr(structures, '_seed_groups', global_groups)
        return [item.as_dict() for item in structures.recognize(graph)]


def stages(count):
    """Build repeated five-transistor stages with one shared supply source."""
    devices = []
    for i in range(count):
        devices.extend([mos(f'T{i}', f't{i}', 'vb', '0'),
                        mos(f'A{i}', f'x{i}', f'ip{i}', f't{i}'),
                        mos(f'B{i}', f'y{i}', f'in{i}', f't{i}'),
                        mos(f'L{i}', f'x{i}', f'x{i}', 'vdd', kind='pmos', model='pch', bulk='vdd'),
                        mos(f'R{i}', f'y{i}', f'x{i}', 'vdd', kind='pmos', model='pch', bulk='vdd')])
    devices.append(('V1', 'vsource', None, dict(positive='vdd', negative='0')))
    return graph_of(devices)


def test_interleaved_groups_keep_global_natural_pair_order(monkeypatch):
    graph = graph_of([mos('M12', 'c2', 'c1', '0'), mos('M3', 'c1', 'c2', '0'),
                      mos('M11', 'b2', 'b1', 'vdd', kind='pmos', model='pch', bulk='vdd'),
                      mos('M1', 'a1', 'a2', '0'), mos('M10', 'a2', 'a1', '0'),
                      mos('M2', 'b1', 'b2', 'vdd', kind='pmos', model='pch', bulk='vdd')], rails=('0', 'vdd'))
    expected = previous_recognition(graph, monkeypatch)
    actual = [item.as_dict() for item in structures.recognize(graph)]
    assert actual == expected
    assert [(item['kind'], item['devices']) for item in actual] == [
        ('cross_coupled_pair', ['M1', 'M10']), ('cross_coupled_pair', ['M2', 'M11']),
        ('cross_coupled_pair', ['M3', 'M12'])]


@pytest.mark.parametrize('devices', [[], [('R1', 'resistor', None, dict(positive='a', negative='0'))],
                                     [('M1', 'nmos', 'nch', dict(drain='a', source='0'))]])
def test_empty_non_mos_and_incomplete_pins_keep_no_seeds(devices, monkeypatch):
    graph = graph_of(devices)
    assert [item.as_dict() for item in structures.recognize(graph)] == previous_recognition(graph, monkeypatch) == []


@pytest.mark.parametrize('seed', range(12))
def test_random_typed_graphs_match_original_pair_scan(seed, monkeypatch):
    rng = random.Random(seed)
    devices = [mos('XA', 'left', 'right', '0'), mos('XB', 'right', 'left', '0')]
    nets = ['0', 'vdd', *[f'n{i}' for i in range(10)]]
    for i in range(60):
        kind = rng.choice(['nmos', 'pmos', 'unknown', 'resistor', 'isource'])
        pins = ({role: rng.choice(nets) for role in ('drain', 'gate', 'source', 'bulk')} if kind in structures.MOS else
                {role: rng.choice(nets) for role in ('positive', 'negative')})
        if kind in structures.MOS and rng.randrange(10) == 0:
            pins.pop('gate')
        devices.append((f'M{i}', kind, rng.choice(['model-a', 'model-b', None]), pins))
    rng.shuffle(devices)
    graph = graph_of(devices, rails=('0', 'vdd'))
    rng.shuffle(graph.connections)
    graph.metadata['globals'] = ['n9']
    before = deepcopy(graph)
    assert [item.as_dict() for item in structures.recognize(graph)] == previous_recognition(graph, monkeypatch)
    assert graph == before


@pytest.mark.parametrize('seed', range(4))
def test_natural_sort_ties_case_and_hierarchy_names_preserve_stable_order(seed, monkeypatch):
    names = ['M1', 'm1', 'M01', 'm001', 'M2', 'm02', 'M10', 'm010',
             'Block1/M1', 'block01/m01', 'Block2/M1', 'block02/m01']
    devices = []
    for index, name in enumerate(names):
        pair, side = divmod(index, 2)
        devices.append(mos(name, f'out{pair}-{side}', f'out{pair}-{1 - side}', '0' if pair % 2 else 'vdd',
                           model=None if pair % 3 == 0 else 'nch'))
    random.Random(seed).shuffle(devices)
    graph = graph_of(devices, rails=('0', 'vdd'))
    expected = previous_recognition(graph, monkeypatch)
    assert len(expected) == 6
    assert [item.as_dict() for item in structures.recognize(graph)] == expected


@pytest.mark.parametrize('rail', ['none', 'role', 'global'])
def test_source_rail_rules_and_missing_model_remain_unchanged(rail, monkeypatch):
    graph = graph_of([mos('M1', 'left', 'in-a', 'tail', model=None),
                      mos('M2', 'right', 'in-b', 'tail', model=None),
                      ('I1', 'isource', None, dict(positive='tail', negative='0'))],
                     rails=('0', 'tail') if rail == 'role' else ('0',))
    if rail == 'global':
        graph.metadata['globals'] = ['tail']
    answer = [item.as_dict() for item in structures.recognize(graph)]
    assert answer == previous_recognition(graph, monkeypatch)
    assert [item['kind'] for item in answer] == (['differential_pair'] if rail == 'none' else [])


def test_800_mos_fixture_keeps_full_output_with_fewer_actual_seed_candidates(monkeypatch):
    graph = stages(160)
    original_groups = structures._seed_groups

    def recognized(grouping):
        """Return recognition output and candidate-read counts for one grouping strategy."""
        calls = Counter()

        class Members(list):
            """A candidate list that counts indexed reads and rejects tail-slice copies."""
            def __getitem__(self, index):
                """Count a single candidate lookup and refuse slicing."""
                assert isinstance(index, int), 'The seed scan must not copy a tail slice'
                calls['candidate'] += 1
                return super().__getitem__(index)

        def counted(mos_by_id):
            """Wrap shared candidate lists with counters while preserving their shared identities."""
            groups, copies = grouping(mos_by_id), {}
            for members, _ in groups.values():
                if id(members) not in copies:
                    copies[id(members)] = Members(members)
            return {name: (copies[id(members)], index) for name, (members, index) in groups.items()}

        with monkeypatch.context() as patch:
            patch.setattr(structures, '_seed_groups', counted)
            answer = [item.as_dict() for item in structures.recognize(graph)]
        return answer, calls['candidate']

    before, old_candidates = recognized(global_groups)
    after, new_candidates = recognized(original_groups)
    assert after == before
    assert Counter(item['kind'] for item in after) == dict(differential_pair=160, tail_source=160, active_load=160)
    assert (old_candidates, new_candidates) == (319600, 63920)


def test_suggestions_defaults_and_applied_ties_remain_identical(monkeypatch):
    graph = stages(4)
    rows = [schema.OptimizationParameter(variable_id=d.id + '_w', instance_path=d.id, parameter_name='w',
                                         unit='um', optimized=True, lower=0.25, upper=4)
            for d in graph.devices if d.kind in structures.MOS]
    before_graph, before_rows = deepcopy(graph), deepcopy(rows)
    with monkeypatch.context() as patch:
        patch.setattr(structures, '_seed_groups', global_groups)
        previous = structures.suggest(graph, rows)
        chosen = [s['id'] for s in previous['suggestions'] if s['default']]
        expected = structures.suggest(graph, rows, chosen)
    assert chosen
    assert structures.suggest(graph, rows) == previous
    assert structures.suggest(graph, rows, chosen) == expected
    assert graph == before_graph and rows == before_rows
