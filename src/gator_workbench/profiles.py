"""Circuit profiles GENERATED from a cell that was read out of Virtuoso (``native_cells``).

"Create profile" turns (a) the local copy of the cell - Virtuoso's netlist export and CDF readback -
and (b) what the three editors say may vary into the same set of files a hand-written profile has
(design, mapping, reference netlist, reference readback, creation receipt) plus ``rules.json`` for the
file-driven ``generic_profile`` class, under ``configs/local/workbench/profiles/<name>/``. The result is
registered as the task ``real:<name>`` (``tasks.py``).

Creating a profile contacts nothing: no Virtuoso, no simulation. It REFUSES whatever the verified real
backend cannot do (``generic_profile``): anything but MOS widths, multi-finger / m>1 transistors, a log
scale, an unverified device type, a supply other than the verified nominal one. A refusal says what to
change, in plain words. What it cannot know is whether the circuit then simulates as hoped: a generated
profile has NO real baseline until the user runs the budget-authorized "Single baseline simulation" of
the new task - it is labelled unverified until then.

The rows of the editors are returned ADJUSTED (bounds snapped onto the width grid, the step filled in,
followers without clamps of their own): a real run requires the configured variables to be exactly the
profile's (``graph_contract``), so the form must show what was registered.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import shutil

from . import native_cells, recipes, units
from .generic_profile import RULES_FORMAT, VERIFIED_WIDTH_STEP, check_writable_record
from .paths import local_settings_dir, repo_root
from .storage.atomic import write_json
from .storage.dataset import utcnow

NAME = re.compile(r'^[a-z][a-z0-9_]{1,39}$')
FORMAT = 'gator-generated-profile-1'
FILES = dict(design='design.json', mapping='mapping.json', structure='structure.scs', readback='readback.cdf.json',
             rules='rules.json', receipt='creation.json', entry='profile.json', reference='reference_measurements.json')
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


def profile_for_cell(library, cell) -> dict | None:
    return next((entry for entry in list_profiles().values() if entry['library'] == library and entry['core_cell'] == cell), None)


def load_profile(name):
    """The profile object for the real backend. Every check of the verified classes runs in its constructor."""
    entry = list_profiles().get(name)
    if entry is None:
        raise ProfileError(f'Unknown generated profile {name!r}')
    directory = Path(entry['directory'])
    return recipes.PROFILE_CLASSES[entry['recipe']](
        rules_file=directory / FILES['rules'], design_file=directory / FILES['design'], mapping_file=directory / FILES['mapping'],
        reference_structure=directory / FILES['structure'], reference_readback=directory / FILES['readback'],
        conditions_file=repo_root() / 'configs' / 'gpdk045_conditions.json')


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
    if any(row.target_kind != 'instance_parameter' for row in rows):
        raise ProfileError('Design variables cannot be written by the real backend: use instance parameters only')
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


def create_profile(name, config, *, recipe, expected_frequency_hz=None) -> dict:
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    from .compile import CompileError, build_graph
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
    if profile_for_cell(imported['library'], imported['cell']):
        raise ProfileError(f'{imported["library"]}/{imported["cell"]} already has the profile real:{profile_for_cell(imported["library"], imported["cell"])["name"]}')
    text = Path(imported['netlist_path']).read_text()
    mapping, unverified = native_cells.build_mapping(text, circuit_id=name)
    if unverified:
        raise ProfileError(f'Device type(s) {", ".join(unverified)} are not verified in this project: their pin order is unknown, '
                           'so the circuit cannot be described to the optimizer')
    reference = json.loads((Path(imported['directory']) / native_cells.FILES['core_readback']).read_text())
    if any(key not in item for item in reference.get('instances', []) for key in ('name', 'lib', 'cell', 'view', 'terms', 'params')):
        raise ProfileError('This copy of the cell lacks details a profile needs (it was read by an older version): press "Read the cell again"')
    staging = directory.with_name(f'.{name}.creating')
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        write_json(staging / FILES['mapping'], mapping)
        (staging / FILES['structure']).write_text(text)
        graph = SpectreParser(ParserConfig.from_file(staging / FILES['mapping'])).parse_file(staging / FILES['structure'])
        core = _core_instance(imported, graph)
        rows, optimized, leaders = _adjust_rows(config, graph, core)
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
        try:
            check_writable_record(reference, list(writable))
        except ValueError as exc:
            raise ProfileError(str(exc))
        design = dict(topology=f'generated:{recipe}', pdk_library=imported.get('technology_library'), library=imported['library'],
                      core_cell=imported['cell'], testbench_cell=imported['testbench_cell'])
        if recipe == 'ring_oscillator':
            if expected_frequency_hz is None:
                raise ProfileError('Give a rough expected oscillation frequency: it sizes the transient simulation')
            source, supply_net, dc = _supply(graph)
            try:
                timing = recipes.ring_timing(expected_frequency_hz)
            except ValueError as exc:
                raise ProfileError(str(exc))
            design.update(supply_v=format(dc.value, '.12g'), supply_source=source, supply_net=supply_net,
                          expected_frequency_hz=float(expected_frequency_hz), **timing,
                          **recipes.CONTRACT, **_ring(graph, core, format(dc.value, '.12g')))
            net_roles = {supply_net: ['supply'], design['stage_nets'][0]: ['output']}
        else:
            nets = {net.id for net in graph.nets}
            missing = sorted(({*OPAMP_NETS, f'{core}/NTAIL', f'{core}/NLOAD'} - nets) | ({'source VDD'} - {f'source {d.id}' for d in graph.devices if d.kind == 'vsource'}))
            if missing:
                raise ProfileError('The op-amp recipe expects the testbench of the verified OTA (nets VDD, VINP, VINN, VOUT, VBIAS, a supply '
                                   f'source named VDD, internal nets NTAIL and NLOAD). Missing here: {", ".join(missing)}')
            design.update(supply_v=format(graph.parameters['VDD']['dc'].value, '.12g'))
            net_roles = {net: [role] for net, role in OPAMP_NETS.items()}
        available = recipes.provided_metrics(recipe)
        unknown = [f'{m.measurement_id} ({m.source_name})' for m in config.measurements
                   if m.result_source == 'backend_profile' and m.source_name and m.source_name not in available]
        if unknown:
            raise ProfileError(f'Measurement(s) {", ".join(unknown)} use a result this circuit type does not produce. '
                               f'Available: {", ".join(available)}')
        mapping.update(net_roles={'0': ['ground'], **net_roles},
                       parameter_groups=[dict(asdict(group), members=[asdict(m) for m in group.members]) for group in compiled.parameter_groups])
        write_json(staging / FILES['mapping'], mapping)
        write_json(staging / FILES['design'], design)
        write_json(staging / FILES['readback'], reference)
        write_json(staging / FILES['rules'], dict(
            format=RULES_FORMAT, recipe=recipe, core_instance=core, width_step=VERIFIED_WIDTH_STEP, mos_instances=mos,
            fixed_instances=[n for n in instances if n not in mos],
            writable=[dict(instance=n, lower=lo, upper=hi) for n, (lo, hi) in writable.items()]))
        write_json(staging / FILES['receipt'], dict(
            library=imported['library'], core_cell=imported['cell'], testbench_cell=imported['testbench_cell'], config=design,
            receipt_recorded_at=utcnow().isoformat(), source_netlist_sha256=imported['netlist_sha256'], imported_utc=imported['imported_utc'],
            note='Generated by the workbench from a cell that already existed in Virtuoso; the workbench did not create the cell.'))
        entry = dict(format=FORMAT, name=name, task_key=f'real:{name}', recipe=recipe, circuit_class=RECIPES[recipe]['circuit_class'],
                     library=imported['library'], core_cell=imported['cell'], testbench_cell=imported['testbench_cell'], core_instance=core,
                     pdk_id=imported.get('technology_library') or 'unspecified', created_utc=utcnow().isoformat(),
                     provided_metrics=list(recipes.provided_metrics(recipe)), optimized_variables=sorted(optimized),
                     status='unverified: no real baseline simulation has been recorded for this profile yet')
        write_json(staging / FILES['entry'], entry)
        staging.rename(directory)
        try:
            load_profile(name)                                    # every check of the verified classes, against the recorded files
        except Exception as exc:
            raise ProfileError(f'The generated profile does not pass the checks of the real backend: {exc}')
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return dict(entry, directory=str(directory), parameters=[row.model_dump(mode='json') for row in rows])


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
        raise ProfileError(f'real:{name} already has a recorded baseline; it is never replaced. Create a new profile to start over.')
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
    raw = {row['metric_name']: row for row in reader.rows('metrics', ['evaluation_id', 'measurement_id', 'metric_name', 'raw_value', 'unit', 'valid'])
           if row['evaluation_id'] == evaluation and row['measurement_id'] is None}
    expected = list(recipes.provided_metrics(entry['recipe']))
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
    write_json(directory / FILES['entry'], dict({k: v for k, v in entry.items() if k != 'directory'},
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
