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
budget-authorized "Baseline simulation" of the new task - it is labelled unverified until then. A
finished one records itself as the task's reference (`adopt_baseline_run`, record 7.78).

The rows of the editors are returned ADJUSTED (bounds snapped onto the grid, the step filled in,
followers without clamps of their own): a real run requires the configured variables to be exactly the
profile's (``graph_contract``), so the form must show what was registered.

Moved from profiles.py by the refactoring (docs/plan-refactoring.md); profiles.py re-exports every name.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import shutil

from . import cdf_facts, cdf_rules, native_cells, pdk_record, recipes, units
from .circuit_types import (MAESTRO, NEEDS_FREQUENCY, NeedsFrequency, OPAMP_NETS, RECIPES, core_instance, opamp_fit,
                            ring_stages, supply_of)
from .compile import CompileError, build_graph
from .generic_profile import RULES_FORMAT, VERIFIED_WIDTH_STEP, check_writable_record
from .paths import repo_root
from .profile_store import FILES, FORMAT, ProfileError, profile_dir
from .saved_tasks import load_profile, task_for_cell
from .storage.atomic import UNREADABLE, read_json_quiet, write_json
from .storage.dataset import utcnow
from .task_registry import REAL_PROFILES
from .validation import resolve_leaders


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
    facts = read_json_quiet(Path(imported['directory']) / cdf_facts.FILE, UNREADABLE)
    if facts is UNREADABLE:
        return None
    if facts.get('format') != cdf_facts.FORMAT or (facts.get('library'), facts.get('cell')) != (imported['library'], imported['cell']):
        return None
    return facts


CONDITIONS_TEMPLATE_FILE = 'conditions_template.json'      # in a PDK's folder of the local settings


def _nominal_supply() -> float:
    return float(json.loads((repo_root() / 'configs' / 'gpdk045_conditions.json').read_text())['nominal']['supply_v'])


def conditions_template(technology_library):
    """The PVT conditions template of a PDK whose supplies are stated RELATIVE to the testbench supply ("supply_scale":
    true): the PDK's own `conditions_template.json` in the local settings (pdks/<technology library>/: git-ignored, never
    in the repository), else configs/<technology library>_conditions.json; or None: gpdk045 keeps its verified absolute
    file and nothing changes for its tasks (2026-10-09, circuits at 3.3 V and 1.8 V on one second foundry PDK)."""
    if not technology_library or not re.fullmatch(r'[A-Za-z0-9_]+', str(technology_library)):
        return None
    try:
        local = pdk_record.pdk_dir(str(technology_library)) / CONDITIONS_TEMPLATE_FILE
    except pdk_record.PdkError:
        return None
    for path in (local, repo_root() / 'configs' / f'{technology_library}_conditions.json'):
        if path.is_file():
            data = json.loads(path.read_text())
            return data if data.get('supply_scale') is True else None
    return None


def scaled_conditions_for(technology_library, supply_v):
    """A task's own conditions: the PDK template with every supply multiplied by the testbench supply (nominal = the
    testbench's), or None when the PDK has no relative template."""
    template = conditions_template(technology_library)
    if template is None:
        return None
    supply = float(supply_v)
    if not math.isfinite(supply) or supply <= 0:
        raise ProfileError(f'The testbench supply must be a positive number to scale the {technology_library} conditions; got {supply_v!r}')

    def scaled(corner):
        return dict(corner, supply_v=round(float(corner['supply_v']) * supply, 9))
    policy = dict(template['model_policy'],
                  screening_supply_v_bounds=[round(float(b) * supply, 9) for b in template['model_policy']['screening_supply_v_bounds']])
    out = {k: v for k, v in template.items() if k not in ('supply_scale', 'note')}
    out.update(nominal=scaled(template['nominal']), screening_corners=[scaled(c) for c in template['screening_corners']], model_policy=policy,
               scaled_from=dict(template=f'configs/{technology_library}_conditions.json', testbench_supply_v=supply))
    return out


def largest_supply(graph):
    """(source name, supply net, dc) of the testbench's supply when the bench has several DC voltage sources: the one with
    the largest dc value, its minus terminal on ground; refused in words when none, or when two share the largest value."""
    roles = {}
    for c in graph.connections:
        roles.setdefault(c.device_id, {})[c.role] = c.net_id
    found = []
    for d in graph.devices:
        if d.kind != 'vsource' or '/' in d.id:
            continue
        dc = graph.parameters[d.id].get('dc')
        if dc is not None and dc.valid and roles.get(d.id, {}).get('negative') == '0' and dc.value > 0:
            found.append((dc.value, d.id, roles[d.id]['positive'], dc))
    if not found:
        raise ProfileError('No DC voltage source with its minus terminal on ground: the testbench needs its supply as one')
    found.sort(key=lambda item: -item[0])
    if len(found) > 1 and math.isclose(found[0][0], found[1][0], rel_tol=1e-9):
        raise ProfileError(f'Two DC voltage sources share the largest value ({found[0][1]}, {found[1][1]}): which one is the supply?')
    _, name, net, dc = found[0]
    return name, net, dc


def write_profile_files(name, config, *, recipe, imported, staging, expected_frequency_hz=None, entry_extra=None) -> dict:
    """Write the profile files of `imported` (the import of the cell a task runs on - its working copy - or, on the
    older route, the original) into the new folder `staging`: device mapping, netlist, CDF readback, design, rules,
    receipt and registry entry. Refuses, in plain words, whatever the verified real backend cannot do."""
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    text, mapping, reference = _checked_import(imported, name)
    write_json(staging / FILES['mapping'], mapping)
    (staging / FILES['structure']).write_text(text)
    graph = SpectreParser(ParserConfig.from_file(staging / FILES['mapping'])).parse_file(staging / FILES['structure'])
    core = core_instance(imported, graph)
    rows, optimized, facts, specs, compiled = _compile_profile_rows(imported, config, graph, core, reference)
    instances, mos, writable = _profile_devices(graph, reference, core, compiled)
    design, net_roles = _profile_design(recipe, imported, expected_frequency_hz, graph, core)
    _check_profile_measurements(recipe, config)
    _write_profile_data(mapping, net_roles, compiled, staging, design, reference, imported)
    _write_profile_rules(specs, staging, recipe, core, mos, instances, writable, facts, reference, compiled)
    entry = _write_profile_entry(
        staging, imported, design, recipe, config, name, core, optimized, specs, entry_extra)
    return dict(entry=entry, rows=rows)


def _compile_profile_rows(imported, config, graph, core, reference):
    """Adjust editor rows through the verified width or form writer and compile their graph contract."""
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
        try:
            rows, optimized, leaders, specs = cdf_rules.adjust(config, graph, core, facts, reference)
        except cdf_rules.RowError as exc:
            raise ProfileError(str(exc)) from None
    adjusted = config.model_copy(update=dict(parameters=rows))
    try:
        compiled, _ = build_graph(adjusted, graph)
    except (CompileError, ValueError) as exc:
        raise ProfileError(str(exc))
    return rows, optimized, facts, specs, compiled


def _profile_devices(graph, reference, core, compiled):
    """Collect recorded instances and the writable ranges of mutable parameter-group members."""
    kinds = {device.id: device.kind for device in graph.devices}
    instances = [item['name'] for item in reference['instances']]
    mos = [n for n in instances if kinds.get(f'{core}/{n}') in ('nmos', 'pmos')]
    writable = {}
    for group in compiled.parameter_groups:
        if group.mutable:
            for member in group.members:
                writable[member.device_id.split('/')[1]] = (group.lower * member.ratio, group.upper * member.ratio)
    return instances, mos, writable


def _profile_design(recipe, imported, expected_frequency_hz, graph, core):
    """Build circuit-specific design metadata and net roles using the existing timing and supply checks."""
    design = dict(topology=f'generated:{recipe}', pdk_library=imported.get('technology_library'), library=imported['library'],
                  core_cell=imported['cell'], testbench_cell=imported['testbench_cell'])
    if recipe == 'ring_oscillator':
        if expected_frequency_hz is None:
            raise NeedsFrequency(NEEDS_FREQUENCY)
        source, supply_net, dc = supply_of(graph)
        try:
            timing = recipes.ring_timing(expected_frequency_hz)
        except ValueError as exc:
            raise ProfileError(str(exc))
        design.update(supply_v=format(dc.value, '.12g'), supply_source=source, supply_net=supply_net,
                      expected_frequency_hz=float(expected_frequency_hz), **timing,
                      **recipes.CONTRACT, **ring_stages(graph, core, format(dc.value, '.12g')))
        net_roles = {supply_net: ['supply'], design['stage_nets'][0]: ['output']}
    elif recipe == MAESTRO:
        try:
            source, supply_net, dc = supply_of(graph)
            design.update(supply_v=format(dc.value, '.12g'), supply_source=source, supply_net=supply_net)
            net_roles = {supply_net: ['supply']}
        except ProfileError:                           # more than one source: the verified nominal supply, no role guessed...
            if conditions_template(imported.get('technology_library')) is not None:     # ...unless the PDK scales its conditions to the supply
                source, supply_net, dc = largest_supply(graph)
                design.update(supply_v=format(dc.value, '.12g'), supply_source=source, supply_net=supply_net)
                net_roles = {supply_net: ['supply']}
            else:
                design.update(supply_v=format(_nominal_supply(), '.12g'))
                net_roles = {}
    else:
        opamp_fit(graph, core)
        design.update(supply_v=format(graph.parameters['VDD']['dc'].value, '.12g'))
        net_roles = {net: [role] for net, role in OPAMP_NETS.items()}
    return design, net_roles


def _check_profile_measurements(recipe, config):
    """Reject backend-profile measurements that the selected circuit recipe does not provide."""
    available = recipes.provided_metrics(recipe)
    unknown = [f'{m.measurement_id} ({m.source_name})' for m in config.measurements
               if m.result_source == 'backend_profile' and m.source_name and m.source_name not in available]
    if unknown:
        raise ProfileError(f'Measurement(s) {", ".join(unknown)} use a result this circuit type does not produce. '
                           f'Available: {", ".join(available)}')


def _write_profile_data(mapping, net_roles, compiled, staging, design, reference, imported):
    """Persist the adjusted mapping, design, readback, and any supply-scaled conditions for the profile."""
    # No `value` in a group, as in the verified mappings: the parser takes it from the netlist it reads. A recorded value
    # made every export of a changed candidate fail its own graph check ("Binding/current value mismatch").
    mapping.update(net_roles={'0': ['ground'], **net_roles},
                   parameter_groups=[dict({k: v for k, v in asdict(group).items() if k != 'value'}, members=[asdict(m) for m in group.members])
                                     for group in compiled.parameter_groups])
    write_json(staging / FILES['mapping'], mapping)
    write_json(staging / FILES['design'], design)
    write_json(staging / FILES['readback'], reference)
    conditions = scaled_conditions_for(imported.get('technology_library'), design['supply_v'])
    if conditions is not None:                        # the task's own PVT conditions: a PDK with a relative template
        write_json(staging / FILES['conditions'], conditions)


def _write_profile_rules(specs, staging, recipe, core, mos, instances, writable, facts, reference, compiled):
    """Write verified width rules or form-derived rules while retaining their existing refusal messages."""
    if specs is None:
        write_json(staging / FILES['rules'], dict(
            format=RULES_FORMAT, recipe=recipe, core_instance=core, width_step=VERIFIED_WIDTH_STEP, mos_instances=mos,
            fixed_instances=[n for n in instances if n not in mos],
            writable=[dict(instance=n, lower=lo, upper=hi) for n, (lo, hi) in writable.items()]))
    else:
        try:
            rules = cdf_rules.rules_v2(recipe=recipe, core=core, facts=facts, reference=reference, compiled=compiled, specs=specs)
        except cdf_rules.RowError as exc:
            raise ProfileError(str(exc)) from None
        write_json(staging / FILES['rules'], dict(rules, mos_instances=mos))


def _write_profile_entry(staging, imported, design, recipe, config, name, core, optimized, specs, entry_extra):
    """Write the creation receipt and registry entry for the generated profile."""
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
    return entry


def create_profile(name, config, *, recipe, expected_frequency_hz=None) -> dict:
    """The older route (API only; the page saves tasks with `save_task`): a profile of the ORIGINAL cell."""
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
                           + ('' if existing['generated'] else ' (a verified built-in circuit): choose it in the Tasks window'))
    staging = directory.with_name(f'.{name}.creating')
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        result = write_profile_files(name, config, recipe=recipe, imported=imported, staging=staging, expected_frequency_hz=expected_frequency_hz)
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


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_generate = write_profile_files
