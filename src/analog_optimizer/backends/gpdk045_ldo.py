"""Dedicated nominal LDO profile; independent permissions and measurement contract."""
from copy import deepcopy
import math

from .backend import UnsupportedCapability
from .gpdk045 import Gpdk045OtaProfile, GEOMETRY, equal, number


class Gpdk045LdoProfile(Gpdk045OtaProfile):
    writable_keys=tuple((f'XU1/{name}','w') for name in ('M1','M2','MP'))
    mos_names=('M1','M2','M3','M4','M5','MP')
    deck_name='ldo.scs'

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

    def optimization_graph(self, structure=None):
        graph=self.parser.parse_file(structure) if structure is not None else deepcopy(self.graph)
        graph.validate()
        self.validate_assignment(graph.assignments({g.id:g.value for g in graph.parameter_groups if g.mutable}))
        return graph

    def validate_readback(self, snapshot):
        actual,reference=self.instances(snapshot),self.instances(self.reference)
        if set(actual)!=set(reference) or set(actual)!=set(self.mos_names)|{'RUP','RDN'}:
            raise ValueError('Unexpected LDO core instance set')
        writable={device.split('/')[1] for device,_ in self.writable_keys}
        for name,inst in actual.items():
            ref=reference[name]
            if any(inst[k]!=ref[k] for k in ('lib','cell','view','terms')):
                raise ValueError(f'LDO master/terminal mismatch: {name}')
            if name in ('RUP','RDN'):
                if not equal(number(inst['params']['r']),number(ref['params']['r'])):
                    raise ValueError('Fixed feedback resistor changed')
                continue
            p=inst['params']
            for key in ('l','m','fingers')+(() if name in writable else ('w','fw')+GEOMETRY):
                if not equal(number(p[key]),number(ref['params'][key])):
                    raise ValueError(f'Fixed LDO parameter changed: {name}.{key}')
            if not equal(number(p['w']),number(p['fw'])) or any(number(p[k])<=0 for k in GEOMETRY):
                raise ValueError(f'Invalid LDO CDF geometry: {name}')
        result={(device,key):number(actual[device.split('/')[1]]['params'][key]) for device,key in self.writable_keys}
        self.validate_assignment(result)
        return result

    def verify_transition(self, before, after, expected):
        actual=self.validate_readback(after)
        if any(not equal(actual[k],v) for k,v in expected.items()):
            raise ValueError('LDO CDF readback differs from requested widths')
        old,new=self.instances(before),self.instances(after)
        for device,_ in self.writable_keys:
            name=device.split('/')[1]
            a,b=old[name]['params'],new[name]['params']
            if not equal(number(a['w']),number(b['w'])) and any(
                    equal(number(a[k]),number(b[k])) for k in ('ad','as','pd','ps','nrd','nrs')):
                raise ValueError(f'Stale derived LDO geometry: {name}')

    def validate_export(self, structure, snapshot):
        graph=self.parser.parse_file(structure)
        graph.validate()
        def topology(g):
            return (sorted((d.id,d.model_ref,d.terminals) for d in g.devices),
                    sorted((c.device_id,c.terminal,c.net_id) for c in g.connections))
        if topology(graph)!=topology(self.graph):
            raise ValueError('LDO exported topology differs from reference')
        actual=self.instances(snapshot)
        writable={d for d,_ in self.writable_keys}
        for device,params in graph.parameters.items():
            ref=self.graph.parameters[device]
            if params.keys()!=ref.keys():
                raise ValueError('Exported LDO parameter set changed')
            for key,param in params.items():
                if device in writable and key in ('w',)+GEOMETRY:
                    same=param.valid and equal(param.value,number(actual[device.split('/')[1]]['params'][key]))
                elif param.valid and ref[key].valid:
                    same=equal(param.value,ref[key].value)
                else:
                    same=param.raw==ref[key].raw
                if not same:
                    raise ValueError(f'Exported LDO parameter mismatch: {device}.{key}')
        return self.validate_readback(snapshot)

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
