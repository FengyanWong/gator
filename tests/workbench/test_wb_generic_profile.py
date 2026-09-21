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
from gator_workbench.generic_profile import GenericMosWidthProfile, RulesError, RULES_FORMAT, check_writable_record

REPO = Path(__file__).resolve().parents[2]
BOUNDS = dict(                                             # the bounds written into the four hand-written classes
    gpdk045_ota5={'M1': (3.6e-6, 4.4e-6), 'M2': (3.6e-6, 4.4e-6)},
    gpdk045_ota7={'M1': (3.6e-6, 4.4e-6), 'M2': (3.6e-6, 4.4e-6), 'M6': (7.2e-6, 8.8e-6), 'M7': (1.8e-6, 2.2e-6)},
    gpdk045_ldo={'M1': (3.6e-6, 4.4e-6), 'M2': (3.6e-6, 4.4e-6), 'MP': (7.2e-6, 8.8e-6)},
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


def test_rules_the_verified_backend_cannot_honour_are_refused(tmp_path):
    hand = hand_written('gpdk045_ota7')
    good = generated('gpdk045_ota7', tmp_path, hand)
    assert good.assignments() == hand.validate_readback(good.reference)
    assert good.assignments(dict(output_stage_width=8.8e-6))['XU1/M7', 'w'] == pytest.approx(2.2e-6)   # the 4:1 pair moves together
    bounds = [dict(instance=k, lower=lo, upper=hi) for k, (lo, hi) in BOUNDS['gpdk045_ota7'].items()]
    for changes in (dict(format='something-else'), dict(width_step=1e-9), dict(core_instance='X/U1'), dict(recipe='ring_oscillator'),
                    dict(writable=[]), dict(writable=bounds + [bounds[0]]),                          # nothing / twice
                    dict(writable=[dict(b, lower=b['lower'] + 1e-9) for b in bounds]),                 # a bound off the grid
                    dict(writable=[dict(b, upper=b['upper'] / 2) for b in bounds]),                    # the group leaves the bounds
                    dict(writable=bounds[:2]),                                                         # a mutable group is not writable
                    dict(writable=bounds + [dict(instance='CC', lower=1e-6, upper=2e-6)]),             # not a transistor
                    dict(mos_instances=['M1', 'M2'])):                                                 # instances unaccounted for
        with pytest.raises(ValueError):
            generated('gpdk045_ota7', tmp_path, hand, **changes)
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
    with pytest.raises(Exception, match='nominal condition only'):
        good.validate_condition(SimulationCondition(PVTCorner('ss_hot_low', 'ss', 125.0, 0.9), 'pvt_validation'))
    reference = deepcopy(good.reference)
    check_writable_record(reference, ['M1', 'M6'])
    instance(reference, 'M6')['params']['fingers'] = '4'
    with pytest.raises(RulesError, match='fingers'):
        check_writable_record(reference, ['M1', 'M6'])
