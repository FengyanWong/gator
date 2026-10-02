"""Dedicated nominal LDO profile; independent permissions and measurement contract."""
import math

from .backend import UnsupportedCapability
from .gpdk045 import Gpdk045MappedProfile, equal, number


class Gpdk045LdoProfile(Gpdk045MappedProfile):
    writable_keys=tuple((f'XU1/{name}','w') for name in ('M1','M2','MP'))
    mos_names=('M1','M2','M3','M4','M5','MP')
    deck_name='ldo.scs'
    passives={'RUP':'r','RDN':'r'}
    reads_snapshot_first=False
    messages=dict(instance_set='Unexpected LDO core instance set',master='LDO master/terminal mismatch: {name}',
                  passive='Fixed feedback resistor changed',fixed='Fixed LDO parameter changed: {name}.{key}',
                  stale_fw='Invalid LDO CDF geometry: {name}',geometry='Invalid LDO CDF geometry: {name}',
                  readback='LDO CDF readback differs from requested widths',stale_geometry='Stale derived LDO geometry: {name}',
                  topology='LDO exported topology differs from reference',parameter_set='Exported LDO parameter set changed',
                  mismatch='Exported LDO parameter mismatch: {device}.{key}')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.design.get('topology')!='pmos_pass_ldo':
            raise ValueError('Explicit PMOS-pass LDO configuration required')
        expected={'input_pair_width':{'XU1/M1','XU1/M2'},'pass_width':{'XU1/MP'}}
        groups={g.id:g for g in self.graph.parameter_groups}
        if groups.keys()!=expected.keys():
            raise ValueError('Unexpected LDO action groups')
        for key,members in expected.items():
            g=groups[key]
            bounds=(3.6e-6,4.4e-6) if key=='input_pair_width' else (7.2e-6,8.8e-6)
            if (not g.mutable or {m.device_id for m in g.members}!=members or
                    any(m.parameter!='w' or m.ratio!=1 for m in g.members) or
                    g.scale!='linear' or g.domain!='continuous' or g.step!=5e-9 or
                    (g.lower,g.upper)!=bounds):
                raise ValueError('LDO action mapping differs from its width contract')

    def validate_condition(self, condition):
        super().validate_condition(condition)
        if not condition.nominal_only or condition.corner!=self.nominal_corner:
            raise UnsupportedCapability('LDO profile supports its qualified nominal package only')

    def assignments(self, width=4e-6, pass_width=8e-6):
        result={('XU1/M1','w'):width,('XU1/M2','w'):width,('XU1/MP','w'):pass_width}
        self.validate_assignment(result)
        return result

    def validate_assignment(self, parameters):
        if set(parameters)!=set(self.writable_keys):
            raise ValueError('Complete LDO input-pair and pass-width assignments required')
        for (device,_),value in parameters.items():
            bounds=(7.2e-6,8.8e-6) if device=='XU1/MP' else (3.6e-6,4.4e-6)
            if (isinstance(value,bool) or not math.isfinite(value) or not bounds[0]<=value<=bounds[1]
                    or not self._on_width_grid(value)):
                raise ValueError('LDO width outside bounds or CDF-compatible grid')
        if not equal(parameters['XU1/M1','w'],parameters['XU1/M2','w']):
            raise ValueError('LDO input pair must remain matched')

    def build_deck(self, structure, model_file, section='tt', *, temperature_c=27.):
        from .virtuoso_bridge import build_deck_header
        cfg=self.design
        return (build_deck_header(structure,model_file,section,temperature_c=temperature_c)
            + 'dcOp dc\ndcOpInfo info what=oppoint where=rawfile\n'
            + f'loadSweep dc dev=ILOAD param=dc start={number(cfg["load_current"]):.12g} stop={number(cfg["load_current_high"]):.12g} lin=2\n'
            + 'lineSweep dc dev=VDD param=dc start=0.95 stop=1.05 lin=2\n'
            + 'ac ac start=10 stop=100M dec=60\n'
            + f'tran tran stop={number(cfg["tran_stop"]):.12g} maxstep={number(cfg["tran_maxstep"]):.12g} errpreset=conservative\n'
            + 'save VDD VREF VBIAS VOUT XU1.VFB XU1.VGATE VDD:p ILOAD:i\n'
            + 'saveOptions options save=allpub\n')

    def analyze(self, job, **kwargs):
        from analog_optimizer.measurements.ldo import analyze
        return analyze(job,design=self.design,**kwargs)
