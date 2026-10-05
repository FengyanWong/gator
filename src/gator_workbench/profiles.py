"""Circuit profiles GENERATED from a cell that was read out of Virtuoso (``native_cells``).

"Create profile" turns (a) the local copy of the cell - Virtuoso's netlist export and CDF readback -
and (b) what the three editors say may vary into the same set of files a hand-written profile has
(design, mapping, reference netlist, reference readback, creation receipt) plus ``rules.json`` for the
file-driven ``generic_profile`` class, under ``configs/local/workbench/profiles/<name>/``. The result is
registered as the task ``real:<name>`` (``tasks.py``).

Creating a profile contacts nothing: no Virtuoso, no simulation. It REFUSES whatever the real backend
cannot do, in plain words. Widths of single-finger, m=1 transistors take the verified width writer
(``generic_profile``, rules of format 1). Any other value takes the form writer (``cdf_rules`` /
``cdf_write``, rules of format 2): a parameter qualifies when the PDK's property form lets a user type it
in that instance - read from Virtuoso together with the cell (``cdf_facts``: its form field, rule,
callback and choices) - and not otherwise; lengths stay on the 5 nm grid, counts on whole numbers. Device
types: the verified ones, and every component of a loaded PDK (pins as the PDK itself states them).
Always refused: a supply other than the verified nominal one. What it cannot know is whether the circuit
then simulates as hoped: a generated profile has NO real baseline until the user runs the
budget-authorized "Single baseline simulation" of the new task - it is labelled unverified until then. A
finished one records itself as the task's reference (`adopt_baseline_run`, record 7.78).

The rows of the editors are returned ADJUSTED (bounds snapped onto the grid, the step filled in,
followers without clamps of their own): a real run requires the configured variables to be exactly the
profile's (``graph_contract``), so the form must show what was registered.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
import re
import shutil

from . import native_cells, recipes, units
from .generic_profile import RULES_FORMAT, VERIFIED_WIDTH_STEP, check_writable_record
from .paths import local_settings_dir, repo_root
from .storage.atomic import sha256_file as _sha256, write_json
from .storage.dataset import utcnow

NAME = re.compile(r'^[a-z][a-z0-9_]{1,39}$')
FORMAT = 'gator-generated-profile-1'
FILES = dict(design='design.json', mapping='mapping.json', structure='structure.scs', readback='readback.cdf.json',
             rules='rules.json', receipt='creation.json', entry='profile.json', reference='reference_measurements.json',
             maestro_deck='maestro_deck.json')
RECIPES = {'ring_oscillator': dict(label='Ring oscillator (free-running)', circuit_class='vco'),
           'opamp_ac': dict(label='Op-amp / OTA (AC gain)', circuit_class='opamp')}
OPAMP_NETS = dict(VDD='supply', VINP='input', VINN='input', VOUT='output', VBIAS='bias')


class ProfileError(ValueError):
    """Why a profile cannot be created, in words the form can show."""


def store_root() -> Path:
    return local_settings_dir() / 'profiles'


def profile_dir(name) -> Path:
    if not isinstance(name, str) or not NAME.match(name):
        raise ProfileError('The profile name must be lowercase letters, digits and "_" (2-40 characters, starting with a letter)')
    return store_root() / name


def list_profiles() -> dict:
    found = {}
    root = store_root()
    for entry_file in sorted(root.glob(f'*/{FILES["entry"]}')) if root.is_dir() else ():
        try:
            entry = json.loads(entry_file.read_text())
        except (OSError, ValueError):
            continue
        if entry.get('format') == FORMAT and entry.get('name') == entry_file.parent.name and NAME.match(entry['name']):
            found[entry['name']] = dict(entry, directory=str(entry_file.parent))
    return found


def tasks_for_cell(library, cell) -> list:
    """The GENERATED tasks of a cell: saved from it (their `original`), or running on it (their copy is this cell)."""
    found = []
    for entry in list_profiles().values():
        original = entry.get('original') or {}
        if (original.get('library'), original.get('cell')) == (library, cell) or (entry['library'], entry['core_cell']) == (library, cell):
            found.append(dict(task_key=entry['task_key'], name=entry['name'], generated=True))
    return found


def task_for_cell(library, cell) -> dict | None:
    """The registered task a Virtuoso cell already belongs to, or None: the profile generated from it, or one of the
    verified built-in circuits. A built-in names its cell in its design file and its library in a Virtuoso connection
    (``bridge_connection.json``), so a cell of the same name in any other library is another cell. Local reads only."""
    generated = tasks_for_cell(library, cell)
    if generated:
        return generated[0]
    from .connection import load_profiles
    from .tasks import REAL_PROFILES
    if not library or not cell or library not in {settings.get('library') for settings in load_profiles()['profiles'].values()
                                                  if isinstance(settings, dict)}:
        return None
    for name, info in REAL_PROFILES.items():
        try:
            design = json.loads((repo_root() / info['design']).read_text())
        except (OSError, ValueError):
            continue
        if design.get('core_cell') == cell:
            return dict(task_key=f'real:{name}', name=name, generated=False)
    return None


def load_profile(name):
    """The profile object for the real backend. Every check of the verified classes runs in its constructor."""
    entry = list_profiles().get(name)
    if entry is None:
        raise ProfileError(f'Unknown generated profile {name!r}')
    directory = Path(entry['directory'])
    _refuse_recorded_group_values(name, directory / FILES['mapping'])
    from . import cdf_write                                  # rules of format 2: any value the PDK's form lets a user type
    classes = cdf_write.PROFILE_CLASSES if cdf_write.rules_format(directory / FILES['rules']) == cdf_write.RULES_FORMAT \
        else recipes.PROFILE_CLASSES
    return classes[entry['recipe']](
        rules_file=directory / FILES['rules'], design_file=directory / FILES['design'], mapping_file=directory / FILES['mapping'],
        reference_structure=directory / FILES['structure'], reference_readback=directory / FILES['readback'],
        conditions_file=repo_root() / 'configs' / 'gpdk045_conditions.json')


def _refuse_recorded_group_values(name, mapping_file):
    """A task saved before 2026-09-22 recorded each group's value in its mapping. It then loads, passes every offline
    check and its baseline, and fails on the FIRST changed candidate with "Binding/current value mismatch" - after a
    real evaluation has been paid for. Say it before anything is started (review of 2026-09-23)."""
    try:
        mapping = json.loads(Path(mapping_file).read_text())
    except (OSError, ValueError):
        return                                   # an unreadable mapping is the profile object's own error to report
    stale = [g.get('id') for g in (mapping.get('parameter_groups') or [])
             if isinstance(g, dict) and 'value' in g and (g.get('lower') is not None or g.get('upper') is not None)]
    if stale:
        raise ProfileError(f'real:{name} was saved before the mapping stopped recording a fixed value per variable, so its '
                           f'first changed candidate would be refused by its own graph check ({", ".join(map(str, stale[:3]))}'
                           f'{"..." if len(stale) > 3 else ""}). Open the task and press "Save task" once; nothing else changes.')


def task_spec_registry(circuit) -> list | None:
    """The result registry of the generated profile a configuration runs, or None (any other task: the default
    registry, or whatever the configuration states itself)."""
    task_id = getattr(circuit, 'task_id', None) or ''
    if getattr(circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return None
    entry = list_profiles().get(task_id[len('real:'):])
    return None if entry is None else entry.get('spec_registry')


def reference_metrics(name) -> dict | None:
    """The recorded REAL baseline of a generated profile, once there is one."""
    try:
        reference = json.loads((profile_dir(name) / FILES['reference']).read_text())
    except (OSError, ValueError):
        return None
    return reference['metrics'] if reference.get('origin') == 'real' and isinstance(reference.get('metrics'), dict) else None


# ---------------------------------------------------------------------------------- creation
def _on_grid(value, step=VERIFIED_WIDTH_STEP) -> bool:
    return math.isclose(value / step, round(value / step), rel_tol=0, abs_tol=1e-7)


def _group_step(ratios, wanted):
    """The smallest group step that moves EVERY member by whole 5 nm steps (a 1 : 0.25 pair needs 20 nm)."""
    if wanted is not None:
        if any(not _on_grid(wanted * ratio) for ratio in ratios):
            raise ProfileError(f'A step of {wanted:g} m does not keep every bound transistor on the 5 nm width grid')
        return wanted
    for multiple in range(1, 401):
        if all(_on_grid(multiple * VERIFIED_WIDTH_STEP * ratio) for ratio in ratios):
            return multiple * VERIFIED_WIDTH_STEP
    raise ProfileError('No width step up to 2 um keeps every bound transistor on the 5 nm grid: simplify the ratios')


def _adjust_rows(config, graph, core):
    """Rows of the parameter editor -> the rows a real run can honour. Raises ProfileError with the reason."""
    from .validation import resolve_leaders
    rows = [row.model_copy() for row in config.parameters]
    try:
        leaders = resolve_leaders(rows)
    except ValueError as exc:
        raise ProfileError(str(exc))
    kinds = {device.id: device.kind for device in graph.devices}
    optimized = {row.variable_id for row in rows if row.optimized and not row.binding_group}
    if not optimized:
        raise ProfileError('Nothing is marked as optimized: the parameter editor needs at least one variable that may change')
    for row in rows:
        leader_id, _ = leaders[row.variable_id]
        if leader_id not in optimized:
            continue                                              # a fixed variable: recorded, never written
        where = f'{row.variable_id} ({row.instance_path}.{row.parameter_name})'
        if row.parameter_name != 'w' or kinds.get(row.instance_path) not in ('nmos', 'pmos'):
            raise ProfileError(f'{where}: the real backend can only change transistor widths (parameter "w" of an nmos/pmos). '
                               'Mark anything else as not optimized.')
        if not (row.instance_path or '').startswith(f'{core}/') or (row.instance_path or '').count('/') != 1:
            raise ProfileError(f'{where}: only transistors directly inside the core cell ({core}/...) can be sized')
        if units.canonical_unit(row.unit) != 'm':
            raise ProfileError(f'{where}: a width needs a length unit (um, nm, m)')
    adjusted = []
    for row in rows:
        leader_id, _ = leaders[row.variable_id]
        if leader_id in optimized and row.binding_group:          # a follower keeps the ratio and nothing else
            row = row.model_copy(update=dict(lower=None, upper=None, step=None, scale='linear', value_type='continuous'))
        elif row.variable_id in optimized:
            if row.scale != 'linear' or row.value_type != 'continuous':
                raise ProfileError(f'{row.variable_id}: use a linear, continuous range - widths move on a fixed 5 nm grid')
            if row.lower is None or row.upper is None:
                raise ProfileError(f'{row.variable_id}: a lower and an upper bound are required')
            scale = units.scale_to_canonical(1.0, row.unit)
            ratios = [ratio for other, (lead, ratio) in leaders.items() if lead == row.variable_id]
            step = _group_step(ratios, None if row.step is None else units.scale_to_canonical(row.step, row.unit))
            lower = math.ceil(units.to_canonical(row.lower, row.unit) / step - 1e-7) * step
            upper = math.floor(units.to_canonical(row.upper, row.unit) / step + 1e-7) * step
            current = graph.parameters.get(row.instance_path, {}).get('w')
            if current is None or not current.valid:
                raise ProfileError(f'{row.variable_id}: the width of {row.instance_path} could not be read from the netlist')
            if not lower < upper or not lower - 1e-15 <= current.value <= upper + 1e-15:
                raise ProfileError(f'{row.variable_id}: the range {lower:g} .. {upper:g} m (after snapping onto the grid) must '
                                   f'contain the present width {current.value:g} m')
            digits = 6                                            # 1e-6 of the unit: far below 5 nm in um, exact in nm
            row = row.model_copy(update=dict(lower=round(lower / scale, digits), upper=round(upper / scale, digits),
                                             step=round(step / scale, digits), initial_value=None))
        adjusted.append(row)
    return adjusted, optimized, leaders


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
    from .tasks import RESULT_ANALYSIS
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


def _checked_import(imported, name):
    """(netlist text, device mapping, core CDF readback) of an import a profile can be made from, or a plain refusal."""
    text = Path(imported['netlist_path']).read_text()
    # The verified models, and what was read from Virtuoso with the cell: every component of its PDK (pins as the PDK
    # states them) and every ideal part of analogLib (pdk.ideal_models, record 7.190).
    mapping, unverified = native_cells.build_mapping(text, circuit_id=name, technology_library=imported.get('technology_library'))
    if unverified:
        raise ProfileError(f'Device type(s) {", ".join(unverified)} are described neither by the cell\'s PDK nor by the ideal parts of '
                           'analogLib that are read with it, and this project has not verified them: their pin order is unknown, so '
                           'the circuit cannot be described to the optimizer. Read the PDK again in the PDK window (it reads both '
                           'descriptions); a part from another library is not read yet.')
    reference = json.loads((Path(imported['directory']) / native_cells.FILES['core_readback']).read_text())
    if any(key not in item for item in reference.get('instances', []) for key in ('name', 'lib', 'cell', 'view', 'terms', 'params')):
        raise ProfileError('This copy of the cell lacks details a profile needs (it was read by an older version): press "Read the cell again"')
    return text, mapping, reference


def _form_facts(imported):
    """What the property form of each instance lets a user type, read together with the cell (`cdf_facts`), or None
    for a cell read before that was recorded."""
    from . import cdf_facts
    try:
        facts = json.loads((Path(imported['directory']) / cdf_facts.FILE).read_text())
    except (OSError, ValueError):
        return None
    if facts.get('format') != cdf_facts.FORMAT or (facts.get('library'), facts.get('cell')) != (imported['library'], imported['cell']):
        return None
    return facts


def _nominal_supply() -> float:
    return float(json.loads((repo_root() / 'configs' / 'gpdk045_conditions.json').read_text())['nominal']['supply_v'])


def _generate(name, config, *, recipe, imported, staging, expected_frequency_hz=None, entry_extra=None) -> dict:
    """Write the profile files of `imported` (the import of the cell a task runs on - its working copy - or, on the
    older route, the original) into the new folder `staging`: device mapping, netlist, CDF readback, design, rules,
    receipt and registry entry. Refuses, in plain words, whatever the verified real backend cannot do."""
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    from .compile import CompileError, build_graph
    text, mapping, reference = _checked_import(imported, name)
    write_json(staging / FILES['mapping'], mapping)
    (staging / FILES['structure']).write_text(text)
    graph = SpectreParser(ParserConfig.from_file(staging / FILES['mapping'])).parse_file(staging / FILES['structure'])
    core = _core_instance(imported, graph)
    facts, specs = _form_facts(imported), None
    try:                                              # the verified width writer, when it can do what the rows ask
        rows, optimized, leaders = _adjust_rows(config, graph, core)
        check_writable_record(reference, sorted({row.instance_path.split('/')[1] for row in rows
                                                 if leaders[row.variable_id][0] in optimized}))
    except ValueError as refused:                     # else the form writer, by the form rules read with the cell
        if facts is None or facts.get('error'):
            hint = (' (Read the cell again: reading it now also records what its property form lets you type, and then '
                    'such values can vary too.)' if facts is None else f' (What its property form lets you type could not be '
                    f'read with the cell: {facts["error"]})')
            raise ProfileError(str(refused) + hint) from None
        from . import cdf_rules
        try:
            rows, optimized, leaders, specs = cdf_rules.adjust(config, graph, core, facts, reference)
        except cdf_rules.RowError as exc:
            raise ProfileError(str(exc)) from None
    adjusted = config.model_copy(update=dict(parameters=rows))
    try:
        compiled, _ = build_graph(adjusted, graph)
    except (CompileError, ValueError) as exc:
        raise ProfileError(str(exc))
    kinds = {device.id: device.kind for device in graph.devices}
    instances = [item['name'] for item in reference['instances']]
    mos = [n for n in instances if kinds.get(f'{core}/{n}') in ('nmos', 'pmos')]
    writable = {}
    for group in compiled.parameter_groups:
        if group.mutable:
            for member in group.members:
                writable[member.device_id.split('/')[1]] = (group.lower * member.ratio, group.upper * member.ratio)
    design = dict(topology=f'generated:{recipe}', pdk_library=imported.get('technology_library'), library=imported['library'],
                  core_cell=imported['cell'], testbench_cell=imported['testbench_cell'])
    if recipe == 'ring_oscillator':
        if expected_frequency_hz is None:
            raise NeedsFrequency(NEEDS_FREQUENCY)
        source, supply_net, dc = _supply(graph)
        try:
            timing = recipes.ring_timing(expected_frequency_hz)
        except ValueError as exc:
            raise ProfileError(str(exc))
        design.update(supply_v=format(dc.value, '.12g'), supply_source=source, supply_net=supply_net,
                      expected_frequency_hz=float(expected_frequency_hz), **timing,
                      **recipes.CONTRACT, **_ring(graph, core, format(dc.value, '.12g')))
        net_roles = {supply_net: ['supply'], design['stage_nets'][0]: ['output']}
    elif recipe == MAESTRO:
        try:
            source, supply_net, dc = _supply(graph)
            design.update(supply_v=format(dc.value, '.12g'), supply_source=source, supply_net=supply_net)
            net_roles = {supply_net: ['supply']}
        except ProfileError:                           # more than one source: the verified nominal supply, no role guessed
            design.update(supply_v=format(_nominal_supply(), '.12g'))
            net_roles = {}
    else:
        _opamp_fit(graph, core)
        design.update(supply_v=format(graph.parameters['VDD']['dc'].value, '.12g'))
        net_roles = {net: [role] for net, role in OPAMP_NETS.items()}
    available = recipes.provided_metrics(recipe)
    unknown = [f'{m.measurement_id} ({m.source_name})' for m in config.measurements
               if m.result_source == 'backend_profile' and m.source_name and m.source_name not in available]
    if unknown:
        raise ProfileError(f'Measurement(s) {", ".join(unknown)} use a result this circuit type does not produce. '
                           f'Available: {", ".join(available)}')
    # No `value` in a group, as in the verified mappings: the parser takes it from the netlist it reads. A recorded value
    # made every export of a changed candidate fail its own graph check ("Binding/current value mismatch").
    mapping.update(net_roles={'0': ['ground'], **net_roles},
                   parameter_groups=[dict({k: v for k, v in asdict(group).items() if k != 'value'}, members=[asdict(m) for m in group.members])
                                     for group in compiled.parameter_groups])
    write_json(staging / FILES['mapping'], mapping)
    write_json(staging / FILES['design'], design)
    write_json(staging / FILES['readback'], reference)
    if specs is None:
        write_json(staging / FILES['rules'], dict(
            format=RULES_FORMAT, recipe=recipe, core_instance=core, width_step=VERIFIED_WIDTH_STEP, mos_instances=mos,
            fixed_instances=[n for n in instances if n not in mos],
            writable=[dict(instance=n, lower=lo, upper=hi) for n, (lo, hi) in writable.items()]))
    else:
        from . import cdf_rules
        try:
            rules = cdf_rules.rules_v2(recipe=recipe, core=core, facts=facts, reference=reference, compiled=compiled, specs=specs)
        except cdf_rules.RowError as exc:
            raise ProfileError(str(exc)) from None
        write_json(staging / FILES['rules'], dict(rules, mos_instances=mos))
    write_json(staging / FILES['receipt'], dict(
        library=imported['library'], core_cell=imported['cell'], testbench_cell=imported['testbench_cell'], config=design,
        receipt_recorded_at=utcnow().isoformat(), source_netlist_sha256=imported['netlist_sha256'], imported_utc=imported['imported_utc'],
        note='Generated by the workbench from a cell that already existed in Virtuoso; the workbench did not create the cell.'))
    circuit_class = RECIPES[recipe]['circuit_class'] if recipe in RECIPES else (config.circuit.circuit_class or 'unspecified')
    entry = dict(format=FORMAT, name=name, task_key=f'real:{name}', recipe=recipe, circuit_class=circuit_class,
                 library=imported['library'], core_cell=imported['cell'], testbench_cell=imported['testbench_cell'], core_instance=core,
                 pdk_id=imported.get('technology_library') or 'unspecified', created_utc=utcnow().isoformat(),
                 provided_metrics=list(recipes.provided_metrics(recipe)), optimized_variables=sorted(optimized),
                 writer='widths' if specs is None else 'form',
                 spec_registry=recipes.spec_registry(recipe, design) if recipe in RECIPES else None,
                 status='unverified: no real baseline simulation has been recorded for this profile yet')
    entry.update(entry_extra or {})                   # what the task adds: its cells, copy, revision, measurement
    write_json(staging / FILES['entry'], entry)
    return dict(entry=entry, rows=rows)


def create_profile(name, config, *, recipe, expected_frequency_hz=None) -> dict:
    """The older route (API only; the page saves tasks with `save_task`): a profile of the ORIGINAL cell."""
    from .tasks import REAL_PROFILES
    directory = profile_dir(name)
    if name in REAL_PROFILES or directory.exists():
        raise ProfileError(f'A profile called {name!r} already exists')
    if recipe not in RECIPES:
        raise ProfileError(f'Unknown circuit type {recipe!r}; available: {", ".join(RECIPES)}')
    circuit = config.circuit
    imported = native_cells.load_import(circuit.library, circuit.cell) if circuit.source == 'virtuoso' and circuit.library and circuit.cell else None
    if imported is None:
        raise ProfileError('Read the cell into the workbench first (Circuit source: Virtuoso library / cell / view)')
    if not imported.get('testbench_cell'):
        raise ProfileError('Choose the testbench cell and read the cell again: a profile simulates the testbench, not the bare cell')
    existing = task_for_cell(imported['library'], imported['cell'])
    if existing:
        raise ProfileError(f'{imported["library"]}/{imported["cell"]} already has the registered task {existing["task_key"]}'
                           + ('' if existing['generated'] else ' (a verified built-in circuit): choose it under Source: Registered task'))
    staging = directory.with_name(f'.{name}.creating')
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        result = _generate(name, config, recipe=recipe, imported=imported, staging=staging, expected_frequency_hz=expected_frequency_hz)
        staging.rename(directory)
        try:
            load_profile(name)                                    # every check of the verified classes, against the recorded files
        except Exception as exc:
            raise ProfileError(f'The generated profile does not pass the checks of the real backend: {exc}')
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return dict(result['entry'], directory=str(directory), parameters=[row.model_dump(mode='json') for row in result['rows']])


# ---------------------------------------------------------------------------------- saving a task: "Save task" / "Save as"
TASK_FILE = 'task.json'
HISTORY = 'history'


def measurement_kind(config) -> str:
    """How a task measures, read from its Probes: all Maestro outputs -> 'maestro'; all results of one circuit type ->
    that type."""
    measured = list(config.measurements)
    if not measured:
        raise ProfileError('Probes is empty: say what the simulation measures (Probes tab) before saving the task')
    sources = {m.result_source for m in measured}
    if sources == {'ade_output'}:
        return MAESTRO
    if sources == {'backend_profile'}:
        names = {m.source_name for m in measured}
        fitting = [recipe for recipe in RECIPES if names <= set(recipes.provided_metrics(recipe))]
        if len(fitting) == 1:
            return fitting[0]
        if not fitting:
            raise ProfileError(f'The probes name results that no circuit type gives together: {", ".join(sorted(names))}')
        raise ProfileError('The probes fit both circuit types (only supply results): add a probe that says which one, '
                           'e.g. osc_frequency_hz or gain_db_at_start')
    raise ProfileError('The probes mix Maestro outputs and results of a circuit type: a task measures one way')


def task_file(name) -> dict | None:
    try:
        return json.loads((profile_dir(name) / TASK_FILE).read_text())
    except (OSError, ValueError, ProfileError):
        return None


def save_task(monitor, profile_id, name, config, *, library=None, cell=None, task=None, as_new=False, extras=None,
              run_rows=(), commands=None, progress=None) -> dict:
    """Explicit press - only a person can do it: store the editors' rows as the task real:<name>.

    * First save from a cell: the task takes the cell's working copy. "Save task" on an open task updates THAT task (a
      new revision, same name); "Save as" (`as_new`) makes a new task with a copy of its own, made from the open task's
      copy, cells renamed <cell>_<name>.
    * Virtuoso side first: a Maestro-measured task writes its setup (outputs and specs from the rows; analyses,
      variables and bindings from `extras`, else from what the copy was last written with, else from the saved task
      file) into its copy and reads it back - it must match;
      then the copy is read into the workbench again (netlist + CDF readback, read-only): the reference every run of
      the task is compared with.
    * Then the profile files are generated from that copy and the task file is written. A new revision keeps the
      recorded baseline only when parameters, probes, measurement, analyses, variables and bindings are unchanged.
    * `progress(step, steps)` hears each step as it starts, with every step this save takes (`task_saving.TITLES`): the
      page shows them while the save runs (record 7.198)."""
    from . import bridge_read, task_files, virtuoso_setup, working_copy
    from .tasks import REAL_PROFILES, REMOVED_REAL_TASKS
    commands, extras = commands or {}, dict(extras or {})
    directory = profile_dir(name)                                # validates the name
    current = list_profiles().get(task) if task else None
    if task and current is None:
        raise ProfileError(f'Unknown task real:{task}')
    updating = current is not None and not as_new
    if updating:
        if name != task:
            raise ProfileError('Save task keeps the task name: use Save as for a task under another name')
        working = working_run_of(name, run_rows)
        if working is not None:
            raise ProfileError(f'Run {working.get("run_id") or working["run_dir"]} of real:{name} is working right now: let it finish first')
        if not current.get('copy_target'):
            raise ProfileError(f'real:{name} was made before tasks had working copies: read its cell in the Virtuoso window (confirming '
                               'that it is a copy you made) and save a new task')
    elif name in REAL_PROFILES or f'real:{name}' in REMOVED_REAL_TASKS or directory.exists():   # a removed one's name stays reserved
        raise ProfileError(f'A task called real:{name} already exists: choose another name')
    from .validation import Report, _check_equation              # a spec must judge Probes the task has (the editors' check)
    probes, refused = {m.measurement_id: m for m in config.measurements}, []
    for spec in config.targets:
        _check_equation(spec, spec.metric_id, report := Report(), probes)
        refused += [f'Spec {spec.metric_id}: {issue.message}' for issue in report.issues if issue.level == 'error']
    if refused:
        raise ProfileError(' '.join(refused))
    kind = measurement_kind(config)
    steps = (['copy'] if current and not updating else []) + (['setup', 'deck'] if kind == MAESTRO else []) + ['read', 'files']
    mark = (lambda step: progress(step, steps)) if progress else (lambda step: None)
    saved = task_file(task) if current else None
    claimed = None
    if updating:
        target = current['copy_target']
    elif current:
        if not current.get('copy_target'):
            raise ProfileError(f'real:{task} was made before tasks had working copies: read its cell in the Virtuoso window (confirming '
                               'that it is a copy you made) and save a new task')
        mark('copy')
        target = working_copy.make_task_copy(monitor, profile_id, current['copy_target'], name,
                                             source_netlist=(Path(current['directory']) / FILES['structure']).read_text(),
                                             command=commands.get('copy'))
    else:
        if not library or not cell:
            raise ProfileError('Say which cell the task is of')
        existing = [t for t in tasks_for_cell(library, cell)]
        if existing:
            raise ProfileError(f'{library}/{cell} already has the task(s) {", ".join(t["task_key"] for t in existing)}: open one and use Save as')
        target = working_copy.draft_target(library, cell)
        working_copy.claim(library, cell, name)
        claimed = (library, cell)
    staging = directory.with_name(f'.{name}.saving')
    try:
        # What the task file adds beside the rows: sent with this save, else what the copy was last written with (by the last
        # save, "Write to Virtuoso" or an approved agent setup - so never older than the saved task's), else the saved task's;
        # a part none of them names stays as the copy has it. Save as starts from the open task's copy.
        base = working_copy.last_written(current['copy_target'] if current else target) or (saved or {}).get('maestro') or {}
        maestro = None
        if kind == MAESTRO:
            setup = virtuoso_setup.from_rows(config, model_files=extras.get('model_files') or base.get('model_files') or (),
                                             analyses=extras['analyses'] if 'analyses' in extras else base.get('analyses'),
                                             variables=extras['variables'] if 'variables' in extras else base.get('variables'),
                                             bindings=extras['bindings'] if 'bindings' in extras else base.get('bindings'),
                                             initial_conditions=(extras['initial_conditions'] if 'initial_conditions' in extras
                                                                 else base.get('initial_conditions')))
            mark('setup')
            written = working_copy.write_setup_on(monitor, profile_id, target, setup, command=commands.get('setup'))
            if not written['matches']:
                raise ProfileError('The copy\'s Maestro setup reads back differently from the rows: ' + '; '.join(written['differences']))
            maestro = virtuoso_setup.normalize(written)
            # Maestro's own deck of the test, netlisted once: every evaluation runs it around the circuit it exports,
            # and OCEAN measures the outputs with their signal names translated by Maestro's own name maps.
            probes = {m.source_name: m for m in config.measurements if m.result_source == 'ade_output'}
            outputs = [dict(name=o['name'], expression=o['expression'], analysis=probes[o['name']].analysis if o['name'] in probes
                            else virtuoso_setup.analysis_of(o['expression']), unit=probes[o['name']].unit if o['name'] in probes else '1')
                       for o in maestro['outputs']]
            mark('deck')
            deck = working_copy.maestro_deck_on(monitor, profile_id, target, outputs, command=commands.get('deck'))
        mark('read')
        bridge_read.read(monitor, profile_id, 'import_cell', library=target['copy']['library'], cell=target['copy']['cell'],
                         testbench=target['copy']['testbench'], command=commands.get('read'))
        mark('files')
        imported = native_cells.load_import(target['copy']['library'], target['copy']['cell'])
        if imported is None:
            raise ProfileError('The working copy could not be read back into the workbench')
        frequency = extras.get('expected_frequency_hz', ((saved or {}).get('measurement') or {}).get('expected_frequency_hz'))
        measurement = dict(kind=kind, **({'expected_frequency_hz': float(frequency)} if kind == 'ring_oscillator' and frequency else {}))
        revision = (saved or {}).get('revision', 0) + 1 if updating else 1
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        extra = dict(original=target['original'], copy=target['copy'], copy_target=target, revision=revision,
                     measurement=kind, runnable=True, saved_utc=utcnow().isoformat())
        if kind == MAESTRO:
            extra['provided_metrics'] = [o['name'] for o in maestro['outputs']]
        if kind == MAESTRO:
            # Maestro's circuit part and the export the task is generated from must be the same circuit.
            exported = Path(imported['netlist_path']).read_text()
            if working_copy.structure(deck['circuit']) != working_copy.structure(exported):
                raise ProfileError('Maestro netlists the working copy differently from its schematic export: look at the copy in '
                                   'Virtuoso, then save again')
            extra['maestro_deck_sha256'] = deck['sha256']
            # The network's result registry: exactly the task's outputs, each with the scale its spec normalizes by.
            from . import units
            from .compile import normalization_scale
            by_probe = {t.equation.strip(): t for t in config.targets}
            registry = []
            for output in deck['outputs']:
                probe = probes.get(output['name'])
                spec = by_probe.get(probe.measurement_id) if probe is not None else None
                scale = units.scale_to_canonical(normalization_scale(spec), spec.unit) if spec is not None else 1.0
                registry.append(dict(metric_id=output['name'], unit=units.canonical_unit(output['unit']) if units.known(output['unit'])
                                     else output['unit'], reference=abs(float(scale)) or 1.0))
            extra['spec_registry'] = registry
        result = _generate(name, config, recipe=kind, imported=imported, staging=staging, expected_frequency_hz=frequency, entry_extra=extra)
        if kind == MAESTRO:
            write_json(staging / FILES['maestro_deck'], {k: v for k, v in deck.items() if k != 'circuit'})
        data = task_files.build(
            name=name, revision=revision, saved_utc=extra['saved_utc'], cell=target['original'], copy=target['copy'],
            measurement=measurement,
            maestro=None if maestro is None else dict(test=maestro['test'], model_files=maestro['model_files'], analyses=maestro['analyses'],
                                                      variables=maestro['variables'], bindings=maestro['bindings'],
                                                      initial_conditions=maestro['initial_conditions'],
                                                      outputs=maestro['outputs'], specs=maestro['specs']),
            parameters=[row.model_dump(mode='json', exclude_none=True) for row in result['rows']],
            probes=[m.model_dump(mode='json', exclude_none=True) for m in config.measurements],
            specs=[t.model_dump(mode='json', exclude_none=True) for t in config.targets],
            notes=extras.get('notes', (saved or {}).get('notes', '')),
            virtuoso=dict(copy_netlist_sha256=imported['netlist_sha256'],
                          maestro_fingerprint=virtuoso_setup.fingerprint(maestro) if maestro else None))
        write_json(staging / TASK_FILE, data)
        changed, baseline_kept = set(), False
        if updating:
            old = Path(current['directory'])
            history = staging / HISTORY
            if (old / HISTORY).is_dir():
                shutil.copytree(old / HISTORY, history)
            keep = history / f'r{saved.get("revision", 0) if saved else 0}'
            keep.mkdir(parents=True, exist_ok=True)
            for item in old.iterdir():
                if item.is_file():
                    shutil.copy2(item, keep / item.name)
            changed = task_files.what_changed(saved, data)
            if (old / FILES['reference']).is_file() and not changed & task_files.BASELINE_PARTS:
                shutil.copy2(old / FILES['reference'], staging / FILES['reference'])
                baseline_kept = True
                entry = json.loads((staging / FILES['entry']).read_text())
                write_json(staging / FILES['entry'], dict(entry, status=current.get('status', entry['status']),
                                                          baseline_recorded_utc=current.get('baseline_recorded_utc')))
            aside = old.parent / TRASH / f'{name}.r{saved.get("revision", 0) if saved else 0}.{utcnow().strftime("%Y%m%dT%H%M%S%fZ")}'
            aside.parent.mkdir(parents=True, exist_ok=True)
            old.rename(aside)
        staging.rename(directory)
        try:
            load_profile(name).check_deck() if kind == MAESTRO else load_profile(name)   # every check of the verified classes
        except Exception as exc:
            raise ProfileError(f'The task does not pass the checks of the real backend: {exc}')
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if not updating and directory.exists() and not (directory / TASK_FILE).is_file():
            shutil.rmtree(directory, ignore_errors=True)
        if claimed:
            working_copy.release(*claimed, name)
        raise
    return dict(task_key=f'real:{name}', name=name, revision=revision, measurement=measurement, runnable=True,
                copy=target['copy'], original=target['original'], directory=str(directory), created=not updating,
                baseline_kept=baseline_kept, changed=sorted(changed), circuit_class=result['entry']['circuit_class'],
                pdk_id=result['entry']['pdk_id'], parameters=[row.model_dump(mode='json') for row in result['rows']],
                maestro_matches=None if maestro is None else True)


# ---------------------------------------------------------------------------------- the first real baseline
def record_reference(name, run_dir) -> dict:
    """The REAL baseline of a finished run of `real:<name>` becomes the profile's reference: from then on every
    worker's first evaluation is compared with it (`NativeEnvironmentFactory.reference_metrics`), as for the four
    verified profiles. Taken from the run's own tables - the raw backend metrics of the evaluation with phase
    `baseline` - and only when that evaluation is real, came from a simulation and every metric of the recipe is
    there and valid. An existing reference is never replaced: a reference that moves is not a reference."""
    from .storage.dataset import DatasetReader
    entry = list_profiles().get(name)
    if entry is None:
        raise ProfileError(f'Unknown generated profile {name!r}')
    directory, run_dir = Path(entry['directory']), Path(run_dir)
    target = directory / FILES['reference']
    if target.exists():
        raise ProfileError(f'real:{name} already has a recorded baseline; it is never replaced. To start over, delete the task and save it again.')
    try:
        config = json.loads((run_dir / 'effective_config.json').read_text())
        manifest = json.loads((run_dir / 'run_manifest.json').read_text())
    except (OSError, ValueError):
        raise ProfileError('Not a finished run directory')
    if (config.get('circuit') or {}).get('task_id') != f'real:{name}' or manifest.get('mock'):
        raise ProfileError(f'That run did not simulate real:{name}')
    reader = DatasetReader(run_dir / 'data')
    baselines = [row for row in reader.rows('evaluations', ['evaluation_id', 'phase', 'provenance', 'result_source', 'completed_at'])
                 if row['phase'] == 'baseline' and row['provenance'] == 'real' and row['result_source'] == 'simulation']
    if not baselines:
        raise ProfileError('That run holds no real baseline simulation')
    evaluation = baselines[0]['evaluation_id']
    # The simulator's own results are the per-condition rows (a spec computed by a formula has no measurement_id either).
    raw = {row['metric_name']: row for row in reader.rows('metrics', ['evaluation_id', 'measurement_id', 'metric_name', 'raw_value', 'unit',
                                                                      'valid', 'aggregation_level'])
           if row['evaluation_id'] == evaluation and row['measurement_id'] is None and row['aggregation_level'] == 'condition'}
    # A task measured by Maestro names its own results (its outputs; `recipes.provided_metrics` has none for it) - found
    # on the user's first real baseline, 2026-09-24: with the recipe's empty tuple every Maestro baseline was "unexpected".
    expected = list(entry.get('provided_metrics') or ()) if entry.get('recipe') == MAESTRO else list(recipes.provided_metrics(entry['recipe']))
    if not expected:
        raise ProfileError(f'real:{name} names no result to record (its provided_metrics are empty)')
    problems = [metric for metric in expected if metric not in raw or not raw[metric]['valid'] or raw[metric]['raw_value'] is None]
    if problems or set(raw) != set(expected):
        raise ProfileError('The baseline of that run is not a complete, valid measurement '
                           f'(missing or invalid: {", ".join(problems) or "unexpected metrics " + ", ".join(sorted(set(raw) - set(expected)))})')
    reference = dict(origin='real', profile=name, run_dir=str(run_dir), run_id=manifest.get('run_id'), evaluation_id=evaluation,
                     completed_at=str(baselines[0]['completed_at']), recorded_utc=utcnow().isoformat(),
                     metrics={metric: raw[metric]['raw_value'] for metric in expected},
                     metric_units={metric: raw[metric]['unit'] for metric in expected},
                     note='Raw backend metrics of the baseline evaluation, read from the run\'s metrics table.')
    write_json(target, reference)
    write_json(directory / FILES['entry'], dict({k: v for k, v in entry.items() if k not in ('directory', 'baseline_attempt')},
                                                status='baseline recorded: one real simulation of the recorded sizes',
                                                baseline_recorded_utc=reference['recorded_utc']))
    return reference


def latest_baseline_run(name, run_dirs):
    """The newest run among `run_dirs` whose baseline can become the reference of real:<name>, or None."""
    for run_dir in run_dirs:
        try:
            config = json.loads((Path(run_dir) / 'effective_config.json').read_text())
        except (OSError, ValueError):
            continue
        if (config.get('circuit') or {}).get('task_id') == f'real:{name}':
            return str(run_dir)
    return None


# ---------------------------------------------------------------------------------- a finished Single baseline simulation records itself
BASELINE_KIND = 'baseline_preflight'                 # run_kind of the header's "Single baseline simulation" (api/app.py `_start`)


def _run_outlived_the_task(entry, manifest) -> str | None:
    """Why a run cannot be the reference of the task as it is NOW, or None. A task saved again after the run (its cell,
    its parameters, its Maestro setup: `write_setup_on` keeps the reference only when no baseline part changed) is not
    the task that run simulated, so an older run's baseline would describe a task that no longer exists."""
    circuit = manifest.get('circuit') or {}
    directory = Path(entry['directory'])
    try:
        current = dict(netlist_sha256=_sha256(directory / FILES['structure']), parser_config_sha256=_sha256(directory / FILES['mapping']))
    except OSError:
        return 'the task files cannot be read'
    if any(circuit.get(key) != value for key, value in current.items()):
        return 'the task was saved again after that run (its cell or its parameters differ)'
    saved, created = entry.get('saved_utc'), manifest.get('created_utc')
    try:
        if saved and created and datetime.fromisoformat(created) < datetime.fromisoformat(saved):
            return 'the task was saved again after that run'
    except ValueError:
        pass
    return None


def adopt_baseline_run(run_dir, manifest=None) -> dict | None:
    """A finished "Single baseline simulation" of a generated task becomes the task's reference BY ITSELF - until record
    7.78 (2026-09-24) "Record the baseline run as reference" was a press of its own, and after the user's first real
    baseline the Project column still said "no real baseline yet". The worker calls this at the end of such a run
    (engine.py `_adopt_baseline`); for a run made before that, `adopt_latest_baseline` does it when the task is loaded.

    None when the run is not one to record (an optimization run, a MOCK run, a built-in circuit): nothing to say.
    Otherwise dict(recorded, name, note) - the note is the sentence for the run's manifest. A refused measurement
    (incomplete, invalid) is kept in the task's entry as `baseline_attempt`, so the column can say why the task still
    has no baseline; a run the task has outlived is left alone. A reference is never replaced."""
    run_dir = Path(run_dir)
    if manifest is None:
        try:
            manifest = json.loads((run_dir / 'run_manifest.json').read_text())
        except (OSError, ValueError):
            return None
    task_key = (manifest.get('circuit') or {}).get('task_key') or ''
    if manifest.get('run_kind') != BASELINE_KIND or manifest.get('mock') or not task_key.startswith('real:'):
        return None
    name = task_key[len('real:'):]
    entry = list_profiles().get(name)
    if entry is None:
        return None
    if manifest.get('state') != 'completed':
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: the run ended as {manifest.get("state")}.')
    if reference_metrics(name) is not None:
        return dict(recorded=False, name=name, note=f'{task_key} already has a recorded baseline; it is never replaced.')
    outlived = _run_outlived_the_task(entry, manifest)
    if outlived:
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: {outlived}.')
    attempt = entry.get('baseline_attempt') or {}
    if attempt.get('run_id') and attempt.get('run_id') == manifest.get('run_id'):      # tried before: the answer has not changed
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: {attempt["reason"]}', attempt=attempt)
    try:
        reference = record_reference(name, run_dir)
    except ProfileError as exc:
        attempt = dict(run_id=manifest.get('run_id'), run_dir=str(run_dir), reason=str(exc),
                       ended_utc=((manifest.get('segments') or [{}])[-1]).get('ended_utc') or manifest.get('created_utc'))
        write_json(Path(entry['directory']) / FILES['entry'], dict({k: v for k, v in entry.items() if k != 'directory'}, baseline_attempt=attempt))
        return dict(recorded=False, name=name, note=f'Not recorded as the reference of {task_key}: {exc}', attempt=attempt)
    return dict(recorded=True, name=name, reference=reference,
                note=f'Recorded as the reference of {task_key}: every later run compares its first evaluation with this result.')


def adopt_latest_baseline(name, data_root) -> dict | None:
    """The newest completed Single baseline simulation of real:<name> under the output root becomes its reference - for
    a run made before such runs recorded themselves. Called when a generated task without a reference is loaded
    (api/app.py `circuit_load`); reads the run manifests only, one small file per run, and never once a reference
    exists. Only the newest completed one is tried: a refusal is remembered in the entry and said in the column."""
    from .layout import find_runs
    newest = None
    for run_dir in find_runs(data_root):
        try:
            manifest = json.loads((run_dir / 'run_manifest.json').read_text())
        except (OSError, ValueError):
            continue
        if (manifest.get('run_kind') == BASELINE_KIND and manifest.get('state') == 'completed' and not manifest.get('mock')
                and (manifest.get('circuit') or {}).get('task_key') == f'real:{name}'
                and (newest is None or (manifest.get('created_utc') or '') > newest[0])):
            newest = (manifest.get('created_utc') or '', run_dir, manifest)
    if newest is None:
        return None
    outcome = adopt_baseline_run(newest[1], manifest=newest[2])
    return outcome if outcome and outcome['recorded'] else None


# ---------------------------------------------------------------------------------- starting over
TRASH = '.deleted'                                  # under the profile store; `list_profiles` never looks inside
WORKING_STATES = ('starting', 'running', 'pausing', 'stopping')     # a worker holds the run (`runs.run_status`)


def working_run_of(name, run_rows):
    """The run of real:<name> a worker is on right now, among the rows of `runs.list_runs`, or None."""
    for row in run_rows:
        if row.get('state') not in WORKING_STATES or row.get('mock'):
            continue
        try:
            manifest = json.loads((Path(row['run_dir']) / 'run_manifest.json').read_text())
        except (OSError, ValueError):
            continue
        if (manifest.get('circuit') or {}).get('task_key') == f'real:{name}':
            return row
    return None


def delete_profile(name, *, run_rows=()) -> dict:
    """Take a GENERATED profile out of the registered tasks, so its cell can get a new one (its name is free again).

    Its folder is moved to ``profiles/.deleted/<name>.<utc>/``, not erased: a recorded baseline cost a real
    simulation, and the runs made with the profile refer to these files. The copy of the cell that was read from
    Virtuoso stays where it is. Refused while a worker is on a run of the task. Runs that were made keep their data;
    a paused one can no longer be resumed. The verified built-in circuits are not in this store and cannot be deleted."""
    from .tasks import REAL_PROFILES
    entry = list_profiles().get(name)
    if entry is None:
        raise ProfileError(f'real:{name} is a verified built-in circuit, not a generated profile: it cannot be deleted'
                           if name in REAL_PROFILES else f'Unknown generated profile {name!r}')
    working = working_run_of(name, run_rows)
    if working is not None:
        raise ProfileError(f'Run {working.get("run_id") or working["run_dir"]} of real:{name} is working right now: abort it or let it finish first')
    directory = Path(entry['directory'])
    kept = directory.parent / TRASH / f'{name}.{utcnow().strftime("%Y%m%dT%H%M%S%fZ")}'
    kept.parent.mkdir(parents=True, exist_ok=True)
    directory.rename(kept)
    original = entry.get('original') or {}
    if original.get('library') and original.get('cell'):             # the cell's working copy is free for a new task
        from . import working_copy
        working_copy.release(original['library'], original['cell'], name)
        # The page puts the answer into its Circuit source: the user's OWN cell, not the working copy the task ran on (that
        # used to lead the next "Save task" to make a copy of the copy). A profile made before working copies has none.
        cell = dict(library=original['library'], cell=original['cell'], testbench_cell=original.get('testbench'))
    else:
        cell = dict(library=entry['library'], cell=entry['core_cell'], testbench_cell=entry.get('testbench_cell'))
    return dict(deleted=entry['task_key'], name=name, **cell,
                baseline_recorded=(kept / FILES['reference']).is_file(), kept_copy=str(kept))
