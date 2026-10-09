"""The file-driven profile must behave exactly like the four hand-written, physically verified ones.

Each verified circuit is regenerated as a rule file over its RECORDED artefacts (real netlist export, real CDF
readback), and both forms are asked the same questions: which assignments are legal, which readbacks, transitions
and exports are accepted. No Virtuoso, no simulation."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import pickle

import pytest

from analog_optimizer.backends.gpdk045 import number
from analog_optimizer.backends.provenance import profile_contract
from analog_optimizer.envs.sizing import graph_contract
from analog_optimizer.parameters.actions import ActionMapper
from gator_workbench import tasks
from gator_workbench.generic_profile import GenericMosWidthProfile, RULES_FORMAT

from helpers import REPO                                                          # the same folder as here
from gator_workbench import compile as comp, schema
from helpers import make_config
from helpers import TOP
# The bounds written into the hand-written classes whose example files remain (the OTA7 and LDO ones left with their files
# on 2026-09-30, record 7.128, and with them the test of what the verified backend cannot honour, built on the OTA7).
BOUNDS = dict(
    gpdk045_ota5={'M1': (3.6e-6, 4.4e-6), 'M2': (3.6e-6, 4.4e-6)},
    gpdk045_vco={'MS1': (.9e-6, 1.1e-6), 'MS2': (.9e-6, 1.1e-6), 'MS3': (.9e-6, 1.1e-6)})
CIRCUITS = sorted(BOUNDS)


def hand_written(name):
    info = tasks.REAL_PROFILES[name]
    module_name, _, class_name = info['profile'].partition(':')
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name) if class_name else next(
        value for key, value in vars(module).items() if key.endswith('Profile') and isinstance(value, type)
        and value.__module__ == module.__name__)
    return cls(design_file=REPO / info['design'], mapping_file=REPO / info['mapping'],
               reference_structure=REPO / info['structure'], reference_readback=REPO / info['readback'])


def generated(name, tmp_path, hand, **changes):
    """The same circuit as rules + the same recorded files. Only ota5 needs a mapping of its own: its hand-written
    class narrows the input-pair group in code (3.6-4.4 um, linear, 5 nm) and freezes the other two."""
    info = tasks.REAL_PROFILES[name]
    mapping = REPO / info['mapping']
    if name == 'gpdk045_ota5':
        raw = json.loads(mapping.read_text())
        for group in raw['parameter_groups']:
            group.update(dict(lower=3.6e-6, upper=4.4e-6, scale='linear', step=5e-9, mutable=True)
                         if group['id'] == 'input_pair_width' else dict(mutable=False))
        mapping = tmp_path / 'gpdk045_opamp.json'
        mapping.write_text(json.dumps(raw))
    reference = json.loads((REPO / info['readback']).read_text())
    rules = dict(format=RULES_FORMAT, recipe='opamp_ac', core_instance='XU1', width_step=5e-9, mos_instances=list(hand.mos_names),
                 fixed_instances=[i['name'] for i in reference['instances'] if i['name'] not in hand.mos_names],
                 writable=[dict(instance=key, lower=lo, upper=hi) for key, (lo, hi) in BOUNDS[name].items()])
    rules.update(changes)
    (tmp_path / 'rules.json').write_text(json.dumps(rules))
    return GenericMosWidthProfile(rules_file=tmp_path / 'rules.json', design_file=REPO / info['design'], mapping_file=mapping,
                                  reference_structure=REPO / info['structure'], reference_readback=REPO / info['readback'],
                                  conditions_file=REPO / 'configs/gpdk045_conditions.json')


def verdict(call):
    try:
        return 'accepted', call()
    except (ValueError, KeyError) as exc:
        return 'rejected', type(exc).__name__


def instance(snapshot, name):
    return next(item for item in snapshot['instances'] if item['name'] == name)


@pytest.mark.parametrize('name', CIRCUITS)
def test_generated_rules_accept_and_reject_exactly_what_the_verified_class_does(name, tmp_path):
    hand = hand_written(name)
    gen = generated(name, tmp_path, hand)
    info = tasks.REAL_PROFILES[name]
    reference = json.loads((REPO / info['readback']).read_text())
    assert gen.writable_keys == hand.writable_keys and gen.mos_names == hand.mos_names
    nominal = hand.validate_readback(reference)
    assert gen.validate_readback(reference) == nominal
    assert gen.validate_export(REPO / info['structure'], reference) == hand.validate_export(REPO / info['structure'], reference)
    assert graph_contract(gen.optimization_graph()) == graph_contract(hand.optimization_graph())
    assert graph_contract(gen.optimization_graph(REPO / info['structure'])) == graph_contract(hand.optimization_graph()) \
        or name == 'gpdk045_ota5'                                   # ota5 narrows in code; its file mapping is the wide one
    assert len(profile_contract(gen)) == 64

    # ---- assignments: corners and centre of the action space, then every way of being wrong -------------------
    graph = hand.optimization_graph()
    groups = [g for g in graph.parameter_groups if g.mutable]
    candidates = [ActionMapper(graph).legalize({g.id: value for g in groups}).assignments for value in (-1., -.37, 0., .5, 1.)]
    for group in groups:                                          # one group off the grid / out of bounds, members kept consistent
        for delta in (1e-9, -2.5e-9, 1e-6, -1e-6):
            shifted = dict(nominal)
            for member in group.members:
                shifted[member.device_id, member.parameter] += delta * member.ratio
            candidates.append(shifted)
        if len(group.members) > 1:                                # matching / ratio broken by one legal grid step
            broken = dict(nominal)
            broken[group.members[0].device_id, 'w'] += 5e-9
            candidates.append(broken)
    first = next(iter(nominal))
    candidates += [{k: v for k, v in nominal.items() if k != first}, {**nominal, ('XU1/NOPE', 'w'): 1e-6},
                   {**nominal, first: float('nan')}, {**nominal, first: True}]
    outcomes = [(verdict(lambda c=c: hand.validate_assignment(c))[0], verdict(lambda c=c: gen.validate_assignment(c))[0]) for c in candidates]
    assert all(a == b for a, b in outcomes), outcomes
    assert {'accepted', 'rejected'} == {a for a, _ in outcomes}       # the sample really exercises both answers

    # ---- readbacks that must be refused -----------------------------------------------------------------------------
    writable = [device.split('/')[1] for device, _ in hand.writable_keys]
    frozen = next(n for n in hand.mos_names if n not in writable)
    tampered = []
    for change in (lambda s: instance(s, frozen)['params'].update(l='2u'),
                   lambda s: instance(s, frozen)['params'].update(w='9u', fw='9u'),
                   lambda s: instance(s, writable[0])['params'].update(fw='1.2345u'),      # no recorded width has this value
                   lambda s: instance(s, writable[0])['params'].update(ad='0'),
                   lambda s: instance(s, writable[0])['params'].update(fingers='2'),
                   lambda s: instance(s, frozen)['terms'].update(G='SOMEWHERE_ELSE'),
                   lambda s: instance(s, frozen).update(cell='another_master'),
                   lambda s: s['instances'].pop(),
                   lambda s: s['instances'].append(dict(instance(s, frozen), name='EXTRA'))):
        snapshot = deepcopy(reference)
        change(snapshot)
        tampered.append(snapshot)
    for other in gen.fixed_instances:                              # a capacitor or resistor of the core cell
        snapshot = deepcopy(reference)
        key = next(k for k in ('c', 'r') if k in instance(snapshot, other)['params'])
        instance(snapshot, other)['params'][key] = '123'
        tampered.append(snapshot)
    for snapshot in tampered:
        assert verdict(lambda: hand.validate_readback(snapshot))[0] == 'rejected'
        assert verdict(lambda: gen.validate_readback(snapshot))[0] == 'rejected'

    # ---- a width change: accepted with fresh derived geometry, refused with stale geometry ---------------------------
    target = candidates[4]                                         # the +1 corner: every writable width differs from nominal
    after = deepcopy(reference)
    for (device, _), width in target.items():
        params = instance(after, device.split('/')[1])['params']
        params.update(w=format(width, '.12g'), fw=format(width, '.12g'))
        for key in ('ad', 'as', 'pd', 'ps', 'nrd', 'nrs'):
            params[key] = format(number(params[key]) * 1.01, '.12g')
    stale = deepcopy(after)
    instance(stale, writable[0])['params']['pd'] = instance(reference, writable[0])['params']['pd']
    for profile in (hand, gen):
        assert verdict(lambda: profile.verify_transition(reference, after, target))[0] == 'accepted'
        assert verdict(lambda: profile.verify_transition(reference, stale, target))[0] == 'rejected'
        assert verdict(lambda: profile.verify_transition(reference, after, nominal))[0] == 'rejected'   # readback != requested

    # ---- workers receive the profile pickled ------------------------------------------------------------------------------
    clone = pickle.loads(pickle.dumps(gen))
    assert clone.validate_readback(reference) == nominal and profile_contract(clone) == profile_contract(gen)


def _ota5_profile(tmp_path, lower, upper, step):
    """A generated (rules file) profile of the verified OTA5 with the input pair varied over [lower, upper] in `step`."""
    info = tasks.REAL_PROFILES['gpdk045_ota5']
    mapping = json.loads((REPO / info['mapping']).read_text())
    for group in mapping['parameter_groups']:
        group.update(dict(lower=lower, upper=upper, scale='linear', step=step, mutable=True) if group['id'] == 'input_pair_width'
                     else dict(mutable=False))
    (tmp_path / 'mapping.json').write_text(json.dumps(mapping))
    reference = json.loads((REPO / info['readback']).read_text())
    mos = [f'M{i}' for i in range(1, 6)]
    (tmp_path / 'rules.json').write_text(json.dumps(dict(
        format=RULES_FORMAT, recipe='opamp_ac', core_instance='XU1', width_step=5e-9, mos_instances=mos,
        fixed_instances=[i['name'] for i in reference['instances'] if i['name'] not in mos],
        writable=[dict(instance=name, lower=lower, upper=upper) for name in ('M1', 'M2')])))
    return GenericMosWidthProfile(rules_file=tmp_path / 'rules.json', design_file=REPO / info['design'],
                                  mapping_file=tmp_path / 'mapping.json', reference_structure=REPO / info['structure'],
                                  reference_readback=REPO / info['readback'],
                                  conditions_file=REPO / 'configs/gpdk045_conditions.json')


def test_a_generated_profile_whose_range_was_typed_in_decimals_loads_and_accepts_its_top_value(tmp_path):
    # Before: refused at load with "Width of XU1/M1 outside its bounds or off the CDF-compatible grid" - its own check of
    # the corners of the action space met the top grid point, a hair above the rules' upper bound.
    profile = _ota5_profile(tmp_path, 1.84e-06, 4.238e-05, 2e-08)
    graph = profile.optimization_graph()
    top = ActionMapper(graph).legalize({'input_pair_width': 1.0}).assignments
    assert set(top.values()) == {TOP}
    profile.validate_assignment(top)
    assert profile.bounds == {'XU1/M1': (1.84e-06, TOP), 'XU1/M2': (1.84e-06, TOP)}
    with pytest.raises(ValueError, match='outside its bounds'):          # one grid step above the top stays refused
        profile.validate_assignment({key: TOP + 2e-08 for key in top})
    # Its mapping holds the typed bound (saved before compile took the top point). The rows saved with it still match what
    # a run gets - the check at Start (tasks._generated_runtime) - and so does the graph of an exported netlist.
    from analog_optimizer.envs.sizing import graph_contract
    rows = [schema.OptimizationParameter.model_validate(r) for r in tasks._graph_parameter_rows(profile.graph)]
    assert next(r for r in rows if r.variable_id == 'input_pair_width').upper == 4.238e-05
    compiled, _ = comp.build_graph(make_config(tmp_path).model_copy(update=dict(parameters=rows)), graph)
    assert graph_contract(compiled) == graph_contract(graph)
    exported = profile.optimization_graph(REPO / tasks.REAL_PROFILES['gpdk045_ota5']['structure'])
    assert graph_contract(exported) == graph_contract(graph)
    assert next(g for g in graph.parameter_groups if g.id == 'input_pair_width').upper == TOP


def test_a_generated_profile_whose_top_is_not_above_its_bound_keeps_its_bounds_exactly(tmp_path):
    profile = _ota5_profile(tmp_path, 3.6e-06, 4.4e-06, 5e-09)            # the verified OTA5 range
    assert profile.bounds == {'XU1/M1': (3.6e-06, 4.4e-06), 'XU1/M2': (3.6e-06, 4.4e-06)}
