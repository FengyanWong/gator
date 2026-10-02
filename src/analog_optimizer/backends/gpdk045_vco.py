"""Dedicated nominal three-stage current-limited ring VCO profile."""
import math

from .backend import UnsupportedCapability
from .gpdk045 import Gpdk045MappedProfile, number


class Gpdk045VcoProfile(Gpdk045MappedProfile):
    writable_keys = tuple((f'XU1/MS{i}', 'w') for i in (1, 2, 3))
    mos_names = tuple(f'M{k}{i}' for i in (1, 2, 3) for k in ('P', 'N', 'S'))
    deck_name = 'vco.scs'
    passives = {f'C{i}': 'c' for i in (1, 2, 3)}
    reads_snapshot_first = False
    messages = dict(instance_set='Unexpected VCO core instance set', master='VCO master/terminal mismatch: {name}',
                    passive='Fixed VCO stage capacitor changed', fixed='Fixed VCO parameter changed: {name}.{key}',
                    stale_fw='Invalid VCO CDF geometry: {name}', geometry='Invalid VCO CDF geometry: {name}',
                    readback='VCO CDF readback differs from requested widths', stale_geometry='Stale derived VCO geometry: {name}',
                    topology='VCO exported topology differs from reference', parameter_set='Exported VCO parameter set changed',
                    mismatch='Exported VCO parameter mismatch: {device}.{key}')

    def __init__(self, *, analysis_mode='fast', timestep_scale=1., **kwargs):
        if analysis_mode not in ('reference', 'fast'):
            raise ValueError('Unknown VCO analysis mode')
        self.analysis_mode = analysis_mode
        if timestep_scale not in (1., .5):
            raise ValueError('Only baseline or half-step numerical qualification supported')
        self.timestep_scale = timestep_scale
        super().__init__(**kwargs)
        if self.design.get('topology') != 'n_current_limited_ring3':
            raise ValueError('Explicit three-stage VCO design required')
        groups = {g.id:g for g in self.graph.parameter_groups}
        if set(groups) != {f'stage{i}_width' for i in (1, 2, 3)}:
            raise ValueError('Unexpected VCO action groups')
        for i in (1, 2, 3):
            g = groups[f'stage{i}_width']
            if (not g.mutable or len(g.members) != 1 or g.members[0].device_id != f'XU1/MS{i}'
                    or g.members[0].parameter != 'w' or g.members[0].ratio != 1
                    or (g.lower, g.upper, g.step) != (.9e-6, 1.1e-6, 5e-9)
                    or g.scale != 'linear' or g.domain != 'continuous'):
                raise ValueError('VCO action mapping differs from its width contract')

    def validate_condition(self, condition):
        super().validate_condition(condition)
        if not condition.nominal_only or condition.corner != self.nominal_corner:
            raise UnsupportedCapability('VCO supports its qualified nominal package only')

    def assignments(self, w1=1e-6, w2=1e-6, w3=1e-6):
        result = dict(zip(self.writable_keys, (w1, w2, w3)))
        self.validate_assignment(result)
        return result

    def validate_assignment(self, parameters):
        if set(parameters) != set(self.writable_keys):
            raise ValueError('Complete three-stage VCO assignments required')
        if any(isinstance(v, bool) or not math.isfinite(v) or not .9e-6 <= v <= 1.1e-6
               or not self._on_width_grid(v) for v in parameters.values()):
            raise ValueError('VCO width outside bounds or CDF-compatible grid')

    @property
    def analysis_settings(self):
        """Numerical policy is separate from the immutable physical creation receipt."""
        settings = dict(version=1, mode=self.analysis_mode,
            stop_s=number(self.design['tran_stop']), start_s=number(self.design['measurement_start']),
            maxstep_s=number(self.design['tran_maxstep']), errpreset='conservative',
            reltol=1e-5, vabstol=1e-8, iabstol=1e-13)
        if self.analysis_mode == 'fast':
            settings.update(stop_s=6e-7, start_s=2e-7, maxstep_s=5e-11,
                            errpreset='moderate', reltol=1e-4, vabstol=1e-6, iabstol=1e-12)
        settings['maxstep_s'] *= self.timestep_scale
        return settings

    def build_deck(self, structure, model_file, section='tt', *, temperature_c=27.):
        from .virtuoso_bridge import build_deck_header
        cfg = self.design
        settings = self.analysis_settings
        deck = build_deck_header(structure, model_file, section, temperature_c=temperature_c)
        if self.analysis_mode == 'fast':
            old = 'simulatorOptions options reltol=1e-5 vabstol=1e-8 iabstol=1e-13'
            if deck.count(old) != 1:
                raise ValueError('Unexpected simulator options header')
            deck = deck.replace(old, 'simulatorOptions options ' + ' '.join(
                f'{key}={settings[key]:.12g}' for key in ('reltol', 'vabstol', 'iabstol')))
        deck += ('dcOp dc\ndcOpInfo info what=oppoint where=rawfile\n'
                 'ic VOUT=0 XU1.N1=1 XU1.N2=0\n'
                 'save VDD VCTRL VOUT XU1.N1 XU1.N2 VDD:p\n'
                 'saveOptions options save=selected\n')
        for label, key in (('Low','control_low_v'), ('Nom','control_v'), ('High','control_high_v')):
            deck += f'control{label} alter dev=VCTRL param=dc value={number(cfg[key]):.12g}\n'
            deck += (f'tran{label} tran stop={settings["stop_s"]:.12g} '
                     f'maxstep={settings["maxstep_s"]:.12g} '
                     f'errpreset={settings["errpreset"]} ic=all skipdc=no useprevic=no restart=yes\n')
        return deck

    def analyze(self, job, **kwargs):
        from analog_optimizer.measurements.vco import analyze
        return analyze(job, design=self.design, analysis_settings=self.analysis_settings, **kwargs)
