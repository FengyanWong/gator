"""Explicit seven-MOS Miller OTA profile, with two CDF-verified width groups.

The five-MOS profile retains its original action permissions. This profile
allows M1/M2 together and M6/M7 in a fixed 4:1 width ratio, on a 5 nm grid.
"""
from copy import deepcopy
import math

from .gpdk045 import Gpdk045OtaProfile, GEOMETRY, equal, number


class Gpdk045TwoStageProfile(Gpdk045OtaProfile):
    writable_keys = tuple((f'XU1/{name}', 'w') for name in ('M1', 'M2', 'M6', 'M7'))
    mos_names = tuple(f'M{i}' for i in range(1, 8))
    training_corners_supported = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.design.get('topology') != 'two_stage_miller':
            raise ValueError('Explicit two-stage design configuration required')
        groups = {g.id: g for g in self.graph.parameter_groups if g.mutable}
        expected = {'input_pair_width': {'XU1/M1': 1., 'XU1/M2': 1.},
                    'output_stage_width': {'XU1/M6': 1., 'XU1/M7': .25}}
        if groups.keys() != expected.keys():
            raise ValueError('Unexpected two-stage action groups')
        for key, members in expected.items():
            g = groups[key]
            if ({m.device_id: m.ratio for m in g.members} != members or
                    any(m.parameter != 'w' for m in g.members) or g.domain != 'continuous' or
                    g.scale != 'linear' or g.step is None):
                raise ValueError('Two-stage group binding differs from the validated width contract')
        for value in (-1., 0., 1.):
            from analog_optimizer.parameters.actions import ActionMapper
            self.validate_assignment(ActionMapper(self.graph).legalize({k: value for k in groups}).assignments)

    def assignments(self, width, output_width=8e-6):
        result = {('XU1/M1', 'w'): width, ('XU1/M2', 'w'): width,
                  ('XU1/M6', 'w'): output_width, ('XU1/M7', 'w'): output_width / 4}
        self.validate_assignment(result)
        return result

    def validate_assignment(self, parameters):
        if set(parameters) != set(self.writable_keys):
            raise ValueError('Complete two-stage matched width assignments required')
        for key, value in parameters.items():
            bounds = {'XU1/M6': (7.2e-6, 8.8e-6), 'XU1/M7': (1.8e-6, 2.2e-6)}.get(key[0], (3.6e-6, 4.4e-6))
            if (not math.isfinite(value) or not bounds[0] <= value <= bounds[1] or
                    not math.isclose(value / 5e-9, round(value / 5e-9), rel_tol=0, abs_tol=1e-7)):
                raise ValueError('Two-stage width outside validated bounds or CDF grid')
        if (not equal(parameters['XU1/M1', 'w'], parameters['XU1/M2', 'w']) or
                not equal(parameters['XU1/M6', 'w'], 4 * parameters['XU1/M7', 'w'])):
            raise ValueError('Two-stage width matching/ratio constraint violated')

    def optimization_graph(self, structure=None):
        graph = self.parser.parse_file(structure) if structure is not None else deepcopy(self.graph)
        graph.validate()
        self.validate_assignment(graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable}))
        return graph

    def validate_readback(self, snapshot):
        actual, reference = self.instances(snapshot), self.instances(self.reference)
        if set(actual) != set(reference) or set(actual) != set(self.mos_names) | {'CC'}:
            raise ValueError('Unexpected two-stage instance set')
        writable = {d.split('/')[1] for d, _ in self.writable_keys}
        for name, inst in actual.items():
            ref = reference[name]
            for key in ('lib', 'cell', 'view', 'terms'):
                if inst[key] != ref[key]:
                    raise ValueError(f'Unexpected {name} {key}')
            if name == 'CC':
                if not equal(number(inst['params']['c']), number(ref['params']['c'])):
                    raise ValueError('Fixed compensation capacitance changed')
                continue
            params = inst['params']
            fixed = ('l', 'm', 'fingers') + (() if name in writable else ('w', 'fw') + GEOMETRY)
            for key in fixed:
                if not equal(number(params[key]), number(ref['params'][key])):
                    raise ValueError(f'Unexpected fixed parameter {name}.{key}')
            if not equal(number(params['w']), number(params['fw'])):
                raise ValueError(f'Stale finger width on {name}')
            if any(number(params[key]) <= 0 for key in GEOMETRY):
                raise ValueError(f'Invalid derived geometry on {name}')
        result = {(device, key): number(actual[device.split('/')[1]]['params'][key])
                  for device, key in self.writable_keys}
        self.validate_assignment(result)
        return result

    def verify_transition(self, before, after, expected):
        actual = self.validate_readback(after)
        if any(not equal(actual[k], v) for k, v in expected.items()):
            raise ValueError('CDF width readback differs from requested values')
        old, new = self.instances(before), self.instances(after)
        for device, _ in self.writable_keys:
            name = device.split('/')[1]
            a, b = old[name]['params'], new[name]['params']
            if not equal(number(a['w']), number(b['w'])):
                for key in ('ad', 'as', 'pd', 'ps', 'nrd', 'nrs'):
                    if equal(number(a[key]), number(b[key])):
                        raise ValueError(f'Stale derived geometry {name}.{key}')

    def validate_export(self, structure, snapshot):
        graph = self.parser.parse_file(structure)
        graph.validate()
        def topology(g):
            return (sorted((d.id, d.model_ref, d.terminals) for d in g.devices),
                    sorted((c.device_id, c.terminal, c.net_id) for c in g.connections))
        if topology(graph) != topology(self.graph):
            raise ValueError('Exported topology differs from the verified reference')
        actual = self.instances(snapshot)
        writable = {d for d, _ in self.writable_keys}
        for device, params in graph.parameters.items():
            ref = self.graph.parameters[device]
            if params.keys() != ref.keys():
                raise ValueError(f'Exported parameter set changed on {device}')
            for key, param in params.items():
                if device in writable and key in ('w',) + GEOMETRY:
                    expected = number(actual[device.split('/')[1]]['params'][key])
                    same = param.valid and equal(param.value, expected)
                elif param.valid and ref[key].valid:
                    same = equal(param.value, ref[key].value)
                else:
                    same = param.raw == ref[key].raw
                if not same:
                    raise ValueError(f'Exported parameter mismatch: {device}.{key}')
        return self.validate_readback(snapshot)
