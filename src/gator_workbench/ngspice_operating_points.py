"""Optional scalar MOS readout inside the candidate's existing ngspice invocation.

Names come from graph devices. SKY130 primitive cells expose a MOS named m<cell>;
other external subcircuits need an explicit mapping before they can be read.
Region codes follow GATOR's existing off/triode/saturation/subthreshold convention,
derived from measured bias and the simulator's vth/vdsat (not from requested sizes).
"""
import math
import re

from .ngspice_netlist import read_results


def probes(graph):
    result = {}
    for index, device in enumerate(graph.devices):
        if device.kind not in ('nmos', 'pmos'):
            continue
        name = device.id.replace('/', '.').lower()
        if not re.fullmatch(r'[a-zA-Z0-9_.:$-]+', name):
            continue
        if name.split('.')[-1].startswith('m'):
            vector = f'm.{name}' if '.' in name else name
            threshold = 'von'  # supported by level 1 and BSIM MOS operating-point interfaces
        elif device.model_ref.startswith('sky130_fd_pr__') and re.fullmatch(r'[a-zA-Z0-9_]+', device.model_ref):
            vector = f'm.{name}.m{device.model_ref.lower()}'
            threshold = 'vth'
        else:
            continue
        result[device.id.replace('/', '.')] = {key: (f'gator_op_{index}_{key}', f'@{vector}[{native}]')
            for key, native in dict(ids='id', gm='gm', gds='gds', vgs='vgs', vds='vds',
                                   vth=threshold, vdsat='vdsat').items()}
    return result


def instrument(text, graph):
    readings = probes(graph)
    if not readings:
        return text
    commands = []
    for quantities in readings.values():
        for label, expression in quantities.values():
            commands += [f'let {label} = {expression}', f'print {label}']
    def block(before):
        # Preserve the deck's print/wrdata precision. Changing numdgt and then
        # unsetting it does not restore ngspice's original formatting state.
        return '\n'.join(commands) + '\n'
    if re.search(r'(?im)^\s*\.control\s*$', text):
        if re.search(r'(?im)^\s*op\s*$', text):
            return re.sub(r'(?im)^(\s*op\s*)$', lambda m: m[1] + '\n' + block(text[:m.start()]), text, count=1)
        # Read bias after the requested analyses so instrumentation does not change
        # their starting solution or adaptive transient stepping.
        return re.sub(r'(?im)^\s*\.endc\s*$', lambda m: 'op\n' + block(text[:m.start()]) + '.endc', text, count=1)
    content = '.control\nrun\nop\n' + block('') + '.endc\n'
    return re.sub(r'(?im)^\s*\.end\s*$', content + '.end', text, count=1)


def read(text, graph):
    result = {}
    for name, quantities in probes(graph).items():
        found = read_results(text, [label for label, _ in quantities.values()])
        values = {key: found[label] for key, (label, _) in quantities.items()
                  if label in found and math.isfinite(found[label])}
        if {'ids', 'vgs', 'vds', 'vth', 'vdsat'} <= values.keys():
            if abs(values['vgs']) <= abs(values['vth']):
                values['region'] = 0 if abs(values['ids']) < 1e-15 else 3
            else:
                values['region'] = 2 if abs(values['vds']) >= abs(values['vdsat']) else 1
        if values:
            result[name] = values
    return result
