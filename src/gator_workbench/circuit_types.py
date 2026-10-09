"""The circuit types a task can be saved as, and what each needs from a cell: the supply, the core instance, the ring of
a ring oscillator, the nets of an op-amp; the measurement kinds (a circuit type's own results, or the Maestro outputs
of the task's working copy); and the probes each circuit type offers, with the testbench net or supply branch each is
read from.

Moved from profiles.py by the refactoring (docs/plan-refactoring.md); profiles.py re-exports every name.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import native_cells, recipes
from .profile_store import ProfileError
from .task_registry import RESULT_ANALYSIS


RECIPES = {'ring_oscillator': dict(label='Ring oscillator (free-running)', circuit_class='vco'),
           'opamp_ac': dict(label='Op-amp / OTA (AC gain)', circuit_class='opamp')}
OPAMP_NETS = dict(VDD='supply', VINP='input', VINN='input', VOUT='output', VBIAS='bias')


def _core_instance(imported, graph) -> str:
    try:
        testbench = json.loads((Path(imported['directory']) / native_cells.FILES['testbench_readback']).read_text())
    except (OSError, ValueError):
        raise ProfileError('The testbench readback is missing: read the cell into the workbench again, with its testbench cell chosen')
    names = [item['name'] for item in testbench.get('instances', []) if item.get('cell') == imported['cell'] and item.get('lib') == imported['library']]
    if len(names) != 1:
        raise ProfileError(f'The testbench must contain the cell {imported["cell"]} exactly once (found {len(names)} times)')
    if not any(device.id.startswith(f'{names[0]}/') for device in graph.devices):
        raise ProfileError(f'The exported netlist has no devices under {names[0]}/ - was the right testbench exported?')
    return names[0]


def _supply(graph):
    """(source name, supply net, dc text) of THE supply: the only DC voltage source of the testbench level."""
    roles = {}
    for c in graph.connections:
        roles.setdefault(c.device_id, {})[c.role] = c.net_id
    sources = [d.id for d in graph.devices if d.kind == 'vsource' and '/' not in d.id]
    if len(sources) != 1:
        raise ProfileError(f'The free-running oscillator recipe expects exactly one voltage source in the testbench (the supply); found {len(sources)}')
    name = sources[0]
    dc = graph.parameters[name].get('dc')
    if dc is None or not dc.valid or roles[name].get('negative') != '0':
        raise ProfileError(f'The supply source {name} needs a numeric dc value and its minus terminal on ground (net 0)')
    return name, roles[name]['positive'], dc


def _ring(graph, core, supply_text) -> dict:
    """Stage nets in ring order (output first) and alternating start voltages, read off the inverter chain."""
    gate, drain = {}, {}
    for c in graph.connections:
        if c.device_id.startswith(f'{core}/') and c.role in ('gate', 'drain'):
            (gate if c.role == 'gate' else drain)[c.device_id] = c.net_id
    chain = {}
    for device, g in gate.items():
        if chain.setdefault(g, drain[device]) != drain[device]:
            raise ProfileError('Not a plain inverter ring: two transistors share a gate net but drive different nets')
    outputs = [net for net in chain if '/' not in net]
    if len(outputs) != 1:
        raise ProfileError('The ring must have exactly one net that reaches the testbench (its output); found '
                           + (', '.join(outputs) or 'none'))
    order, net = [outputs[0]], chain[outputs[0]]
    while net != outputs[0] and len(order) <= len(chain):
        order.append(net)
        net = chain.get(net)
    if net != outputs[0] or len(order) != len(chain) or len(order) < 3 or len(order) % 2 == 0:
        raise ProfileError('Not a plain inverter ring with an odd number of stages (3, 5, ...): this recipe does not fit the cell')
    spectre = [name.replace('/', '.') for name in order]
    return dict(stage_nets=spectre, initial_conditions={name: ('0' if index % 2 == 0 else supply_text) for index, name in enumerate(spectre)})


def _opamp_fit(graph, core):
    """Raises unless the testbench is wired like the verified OTA's: the op-amp recipe reads exactly these nets and source."""
    nets = {net.id for net in graph.nets}
    missing = sorted(({*OPAMP_NETS, f'{core}/NTAIL', f'{core}/NLOAD'} - nets) | ({'source VDD'} - {f'source {d.id}' for d in graph.devices if d.kind == 'vsource'}))
    if missing:
        raise ProfileError('The op-amp recipe expects the testbench of the verified OTA (nets VDD, VINP, VINN, VOUT, VBIAS, a supply '
                           f'source named VDD, internal nets NTAIL and NLOAD). Missing here: {", ".join(missing)}')


# ---------------------------------------------------------------------------------- probes of a testbench
# The results of each circuit type, and where in the testbench each one is read: `output` = the net it is taken at,
# `stages` = every ring net, `supply` = the branch of the supply source (Spectre `<source>:p`). What a result MEANS is
# fixed by the circuit type (recipes.py, measurements/); the testbench decides which net and which source that is.
PROBES = {
    recipes.RING: dict(
        osc_frequency_hz=('output', 'oscillation frequency at {output}'),
        supply_power_w=('supply', 'average power delivered by the supply {source}'),
        supply_current_a=('supply', 'average current delivered by the supply {source}'),
        osc_minimum_swing_v=('stages', 'smallest cycle swing of the ring nets'),
        osc_duty_cycle=('output', 'duty cycle at {output}'),
        osc_max_period_spread=('stages', 'largest period spread of the ring nets (a check of regular cycles)'),
        osc_max_window_drift=('stages', 'largest frequency drift between the two halves of the measurement window'),
        osc_startup_detection_s=('stages', 'time by which every ring net oscillates regularly, from the declared start voltages')),
    'opamp_ac': dict(
        gain_db_at_start=('output', 'gain from VINP - VINN to {output} at the lowest AC frequency'),
        gain_reference_hz=('output', 'the frequency at which that gain is read'),
        bandwidth_3db_hz=('output', '-3 dB bandwidth of that gain'),
        unity_gain_hz=('output', 'unity-gain frequency of that gain'),
        phase_margin_estimate_deg=('output', 'phase margin estimated at the unity-gain frequency (unity feedback, not an stb analysis)'),
        unity_downward_crossings=('output', 'how often the gain falls through 0 dB'),
        supply_current_a=('supply', 'DC current delivered by the supply {source}'),
        supply_power_w=('supply', 'DC power delivered by the supply {source}'),
        output_dc_v=('output', 'DC voltage at {output}')),
}
SIGNAL_LENGTH = 300                                                # schema.MeasurementDefinition.signal


def _type_signals(recipe, graph, core) -> dict:
    """{output, stages?, source} of a testbench for one circuit type; raises ProfileError when the testbench does not fit it.
    The same reading of the netlist Create profile makes."""
    if recipe == recipes.RING:
        source, _, dc = _supply(graph)
        stages = _ring(graph, core, format(dc.value, '.12g'))['stage_nets']
        return dict(output=stages[0], stages=stages, source=source)
    _opamp_fit(graph, core)
    return dict(output='VOUT', source='VDD')


def design_signals(recipe, design) -> dict:
    """The same, for a profile that exists: read from its design file."""
    if recipe == recipes.RING:
        return dict(output=design['stage_nets'][0], stages=list(design['stage_nets']), source=design['supply_source'])
    return dict(output='VOUT', source='VDD')


def probe_results(recipe, spec_registry=None) -> dict:
    """{result: unit} a circuit type produces and a target can be set on (the profile's own registry, else the one it
    will bring, else the default one), in the circuit type's order."""
    from analog_optimizer.models.inputs import SpecSchema
    registry = ({e['metric_id']: e['unit'] for e in spec_registry} if spec_registry
                else dict(recipes.RING_METRICS) if recipe == recipes.RING
                else {metric: unit for metric, unit, _ in SpecSchema().metrics})
    return {metric: registry[metric] for metric in recipes.provided_metrics(recipe) if metric in registry}


def probe_rows(recipe, results, signals, testbench) -> list:
    """Rows of the Probes editor: one per result, naming the testbench net or supply branch it is read from."""
    label, rows = RECIPES[recipe]['label'], []
    for metric, unit in results.items():
        where, meaning = PROBES[recipe][metric]
        signal = f'{signals["source"]}:p' if where == 'supply' else signals['output'] if where == 'output' else ' '.join(signals['stages'])
        if len(signal) > SIGNAL_LENGTH:
            signal = f'{signals["output"]} and {len(signals["stages"]) - 1} more ring nets'
        rows.append(dict(measurement_id=f'm_{metric}', analysis='tran' if recipe == recipes.RING else RESULT_ANALYSIS.get(metric, 'dc'),
                         result_source='backend_profile', source_name=metric, signal=signal, unit=unit,
                         notes=f'Testbench {testbench}, circuit type {label}: {meaning.format(**signals)}.'))
    return rows


def testbench_probes(imported, graph=None) -> dict:
    """What the testbench a cell was read through can measure, as rows of the Probes editor: the results of the ONE
    circuit type the testbench fits, each naming the net or supply branch of THIS testbench it is read from. Local files
    only - the copy Virtuoso exported (`native_cells`) - so it answers for the testbench that was actually read, not for
    whatever the form shows now. No rows, and the reason, when the cell was read without a testbench or the testbench
    fits no circuit type (or more than one)."""
    testbench = imported.get('testbench_cell')
    answer = dict(library=imported['library'], cell=imported['cell'], testbench_cell=testbench, circuit_type=None,
                  circuit_type_label=None, rows=[], reason=None, not_fitting={})
    if not testbench:
        answer['reason'] = 'The cell was read without a testbench cell: read it again through its testbench.'
        return answer
    graph = native_cells.draft_graph(imported) if graph is None else graph
    try:
        core = _core_instance(imported, graph)
    except ProfileError as exc:
        answer['reason'] = str(exc)
        return answer
    fitting = {}
    for recipe in RECIPES:
        try:
            fitting[recipe] = _type_signals(recipe, graph, core)
        except (ProfileError, KeyError) as exc:                  # KeyError: a transistor without a drain or gate net
            answer['not_fitting'][RECIPES[recipe]['label']] = str(exc) if isinstance(exc, ProfileError) else 'The netlist does not fit this type'
    if len(fitting) != 1:
        answer['reason'] = (f'The testbench {testbench} fits none of the circuit types.' if not fitting else
                            f'The testbench {testbench} fits more than one circuit type ({", ".join(fitting)}): choose the probes yourself.')
        return answer
    (recipe, signals), = fitting.items()
    answer.update(circuit_type=recipe, circuit_type_label=RECIPES[recipe]['label'],
                  rows=probe_rows(recipe, probe_results(recipe), signals, testbench))
    return answer


MAESTRO = 'maestro'                     # a task whose probes are Maestro outputs of its working copy (runs: OCEAN, coming)
MAESTRO_NOT_RUNNABLE = ('This task measures the Maestro outputs of its working copy, and it was saved before such tasks could '
                        'run: press Save task once - Maestro then netlists its test, and every run uses that deck.')
NEEDS_FREQUENCY = ('The ring-oscillator measurement needs a rough expected oscillation frequency: it sizes the transient '
                   '(60 periods, measured after 20). Give it once; the task file keeps it.')


class NeedsFrequency(ProfileError):
    """Save task needs the expected frequency of the ring-oscillator measurement (the page asks for it once)."""
