"""Explicit seven-MOS Miller OTA profile, with two CDF-verified width groups.

The five-MOS profile retains its original action permissions. This profile
allows M1/M2 together and M6/M7 in a fixed 4:1 width ratio, on a 5 nm grid.
"""
import math

from .gpdk045 import Gpdk045MappedProfile, equal


class Gpdk045TwoStageProfile(Gpdk045MappedProfile):
    writable_keys = tuple((f'XU1/{name}', 'w') for name in ('M1', 'M2', 'M6', 'M7'))
    mos_names = tuple(f'M{i}' for i in range(1, 8))
    training_corners_supported = True
    passives = {'CC': 'c'}
    messages = dict(Gpdk045MappedProfile.messages, instance_set='Unexpected two-stage instance set', master='Unexpected {name} {key}',
                    passive='Fixed compensation capacitance changed', fixed='Unexpected fixed parameter {name}.{key}',
                    stale_fw='Stale finger width on {name}', geometry='Invalid derived geometry on {name}')

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
