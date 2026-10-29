"""A loaded PDK's record: what the network's component list says about each of the PDK's parts (its family, pin roles,
writable parameters with their ranges and units), the ideal parts of analogLib beside them, and the store of records
in the workbench's settings.

Moved from pdk.py by the refactoring (docs/plan-refactoring.md); pdk.py re-exports every name.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .cdf_text import NUMERIC_CDF_TYPES, cdf_entry, leaf_of, writability, write_source, parse_cdf_text
from .model_scan import CDF_UNITS, file_line, classify_model, merge_scans, pin_roles
from .paths import local_settings_dir
from .storage.atomic import read_json, write_json
from .storage.dataset import utcnow


FORMAT = 'gator-pdk-1'
VOCABULARY_FORMAT = 'gator-pdk-vocabulary-1'
STANDARD = 'standard'
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$')          # a technology library name (also a folder name)
REMOTE_PATH = re.compile(r'^/[A-Za-z0-9_./+\-]{1,1000}$')           # an absolute POSIX path; no shell characters
MAX_MODEL_FILES, MAX_MODEL_BYTES = 64, 128 * 1024 * 1024


PRIMITIVE_PINS = {'mos': ('d', 'g', 's', 'b'), 'bjt': ('c', 'b', 'e', 's'), 'diode': ('a', 'c')}
FAMILY_LABEL = {'mos': 'MOS transistor', 'bjt': 'bipolar transistor', 'diode': 'diode', 'resistor': 'resistor',
                'capacitor': 'capacitor', 'varactor': 'varactor', 'inductor': 'inductor', 'other': 'other'}


UNIT_REFERENCE = {'m': 1e-6, 'F': 1e-12, 'ohm': 1e3, 'H': 1e-9, 'V': 1.0, 'A': 1e-6, 's': 1e-9, 'Hz': 1e9, 'W': 1e-3,
                  'degC': 1.0, 'deg': 1.0, 'count': 1.0}
# The optimizer can vary a group only in one of its eight standard parameter kinds, each with a fixed unit
# (analog_optimizer.models.inputs). A PDK parameter is varied in the kind of its unit: its own name stays on the binding.
ACTION_CLASS = {'m': 'l', 'count': 'm', 'ohm': 'r', 'F': 'c', 'H': 'ind', 'V': 'dc'}
SCALE_TOLERANCE_DECADES = 1.5          # two parameters of one name share a column only if their scales agree this closely


def standard_schema():
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    return FeatureSchema()


STANDARD_UNITS = {'w': 'm', 'l': 'm', 'm': 'count', 'nf': 'count', 'r': 'ohm', 'c': 'F', 'ind': 'H', 'dc': 'V'}


# ------------------------------------------------------------------------------------------ the ideal parts
# What a circuit holds besides its PDK's components lives in Cadence's generic library. Until record 7.190 the workbench
# knew five of those parts from definitions written by hand into the example circuits' mapping files, and lost two of
# them when the examples were deleted (record 7.187). Now the library says it itself, read with every PDK.
IDEAL_LIBRARY = 'analogLib'
IDEAL_FORMAT = 'gator-ideal-parts-1'


# The Spectre components the optimizer's standard list has a kind for, each with the one value its instance line carries
# (netlist name -> the standard parameter it is). All are two-terminal: Spectre's first node is the positive one. A
# current probe is a 0 V source in series, which is how the project's own mapping always read it. Every other component
# of the library is still read and named - pins as the library orders them - and reaches the network as "unknown", as a
# PDK's diode or bipolar does under the standard list.
MAX_IDEAL_PINS = 64             # analogLib's `nport` states 2,000 pins, `vcvsp` 42: an order longer than this is counted, not kept
IDEAL_KINDS = {'vsource': ('vsource', {'dc': 'dc'}), 'isource': ('isource', {'dc': 'dc'}), 'resistor': ('resistor', {'r': 'r'}),
               'capacitor': ('capacitor', {'c': 'c'}), 'inductor': ('inductor', {'l': 'ind'}), 'iprobe': ('vsource', {})}


class PdkError(ValueError):
    """Why a PDK cannot be loaded or used, in words the page can show."""


def build_record(pdk_id, cdf, scans, *, sources=None, technology_library=None):
    """The PDK record: one entry per Spectre model a cell of the library netlists to, and the component list."""
    scan = merge_scans(scans)
    cells, leaves = cdf['cells'], cdf['leaves']
    by_model, not_netlisted = _netlisted_models(cells, leaves)
    devices = {}
    for model in sorted(by_model):
        _record_model(model, by_model, cells, scan, pdk_id, devices)
    used = set(devices)
    unused = sorted((set(scan['subckts']) | set(scan['models'])) - used)
    _assign_columns(devices)
    vocabulary = _vocabulary(pdk_id, devices)
    record = dict(format=FORMAT, pdk_id=pdk_id, technology_library=technology_library or pdk_id, loaded_utc=utcnow().isoformat(),
                  sources=sources or {}, devices=devices, not_netlisted=not_netlisted, layout_only=cdf.get('layout_only', []),
                  model_file_definitions_not_used=unused,
                  duplicates=scan['duplicates'][:50], vocabulary=vocabulary, summary=_summary(devices))
    record['sha256'] = vocabulary['sha256']
    return record


def _netlisted_models(cells, leaves):
    """Group netlisted cells by Spectre model and record why remaining cells have no usable model."""
    by_model, not_netlisted = {}, []
    for name in sorted(cells):
        cell = cells[name]
        spectre, parent, via = cell.get('spectre'), None, None
        model = cell.get('model') or (spectre or {}).get('component_name')
        if spectre is None:
            leaf = leaf_of(cells, leaves, name)
            if leaf is None:
                not_netlisted.append(dict(cell=name, reason='no Spectre entry and no netlisted primitive in its schematic'
                                          if 'schematic' in cell.get('views', []) else 'no Spectre entry (not netlisted)'))
                continue
            parent, via, model = name, leaf, leaf['model']
            spectre = cells[leaf['cell']]['spectre']
        if not model or not isinstance(model, str):
            placed = any(leaf['cell'] == name for entries in leaves.values() for leaf in entries)
            not_netlisted.append(dict(cell=name, reason='a primitive placed inside other cells, which name its model' if placed
                                      else 'its description names no Spectre model'))
            continue
        by_model.setdefault(model, []).append(dict(cell=name, spectre=spectre, parent=parent, via=via,
                                                   leaf_cell=via['cell'] if via else name))
    return by_model, not_netlisted


def _record_model(model, by_model, cells, scan, pdk_id, devices):
    """Choose the representative cell and assemble the classified model record with its pins, parameters, and problems."""
    uses = by_model[model]
    # The cell whose pins are all named in its own mapping describes the pins (nmos1v rather than nmos1v_3 with its
    # inherited bulk); ties go to the shortest, then alphabetical name.
    uses.sort(key=lambda u: (not all(str(t) in u['spectre']['term_mapping'] for t in u['spectre']['term_order'] or []),
                             len(u['cell']), u['cell']))
    lead = uses[0]
    units_declared = sorted({str(p.get('units')) for u in uses for p in cells[u['leaf_cell']]['parameters'].values()
                             if p.get('units')} | {str(p.get('units')) for u in uses if u['parent']
                                                    for p in cells[u['parent']]['parameters'].values() if p.get('units')})
    found = classify_model(model, scan, cdf_units=units_declared)
    problems = []
    pins, subckt = _model_pins(model, found, scan, lead, problems)
    parameters, leaf_cell, parent = _model_parameters(lead, cells)
    standard = dict(mos={'n': 'nmos', 'p': 'pmos'}.get(found.get('polarity')), resistor='resistor',
                    capacitor='capacitor', inductor='inductor').get(found['family']) or 'unknown'
    known = {p['role'] for p in pins}
    if 'unknown' in known and found['family'] != 'other':
        problems.append('the role of some pins could not be established')
    forms = dict(self=cells[leaf_cell].get('form'), parent=cells[parent].get('form') if parent else None)
    devices[model] = dict(
        model=model, kind=f'{pdk_id}:{model}', cells=[u['cell'] for u in uses], form=forms,
        netlisted_through=sorted({u['via']['cell'] for u in uses if u['via']}),
        family=found['family'], family_label=FAMILY_LABEL[found['family']], polarity=found.get('polarity'),
        family_basis=found['family_basis'], pins=pins, parameters=parameters,
        standard_kind=standard, standard_roles=_standard_roles(standard, pins),
        source=file_line(subckt) if subckt else file_line(scan['models'][model]) if model in scan['models'] else None,
        problems=problems)


def _model_pins(model, found, scan, lead, problems):
    """Reconcile symbol pin order and mapping with model-file pins and record any unresolved roles."""
    roles = pin_roles(model, found, scan) if found['family'] != 'other' else None
    order = [str(t) for t in lead['spectre'].get('term_order') or []]
    mapping = {str(k): str(v) for k, v in lead['spectre'].get('term_mapping', {}).items()}
    pins = []
    subckt = scan['subckts'].get(model)
    model_pins = subckt['pins'] if subckt else [str(i + 1) for i in range(len(order))]
    if not order:
        problems.append('the description gives no pin order')
    if subckt is not None and order and len(order) != len(model_pins):
        problems.append(f'{len(order)} pins in the description, {len(model_pins)} in the model file')
    for index, symbol in enumerate(order):
        target = mapping.get(symbol, '').lstrip(':')
        model_pin = model_pins[index] if index < len(model_pins) else None
        role = roles[index]['role'] if roles and index < len(roles) else 'unknown'
        basis = roles[index]['basis'] if roles and index < len(roles) else 'no role established'
        allowed = {model_pin, str(index + 1)} | ({PRIMITIVE_PINS[found['family']][index]}
                                                 if subckt is None and index < len(PRIMITIVE_PINS.get(found['family'], ())) else set())
        if target and model_pin is not None and target not in allowed and not target.startswith('('):
            problems.append(f'pin {symbol} maps to {target} but position {index + 1} of {model} is {model_pin}')
            role, basis = 'unknown', 'pin order and mapping disagree'
        pins.append(dict(name=symbol, model_pin=model_pin, role=role, basis=basis))
    return pins, subckt


def _model_parameters(lead, cells):
    """Read netlisted parameter defaults and determine their units, numeric status, and writable CDF sources."""
    parameters = []
    leaf_cell, parent = lead['leaf_cell'], lead['parent']
    prop = {str(k): str(v) for k, v in lead['spectre'].get('prop_mapping', {}).items()}
    for netlist in [str(p) for p in lead['spectre'].get('inst_parameters') or []]:
        cdf_name = prop.get(netlist, netlist)
        entry, default = cdf_entry(cells, leaf_cell, cdf_name, parent)
        if entry is None:
            entry, default = cdf_entry(cells, leaf_cell, netlist, parent)
        kind = (entry or {}).get('type')
        unit = CDF_UNITS.get((entry or {}).get('units'))
        numeric = kind in NUMERIC_CDF_TYPES and (default is not None or unit is not None or netlist in STANDARD_UNITS)
        source = write_source(cells, leaf_cell, cdf_name if entry is not None and cdf_name in cells[leaf_cell]['parameters']
                               else netlist, parent)
        parameters.append(dict(name=netlist, cdf=cdf_name, type=kind, unit=unit, unit_declared=unit is not None,
                               default=default, prompt=(entry or {}).get('prompt'), numeric=bool(numeric),
                               write=source, writable=writability(source, numeric)))
    return parameters, leaf_cell, parent


def _standard_roles(kind, pins):
    if kind in ('nmos', 'pmos'):
        return [p['role'] if p['role'] in ('drain', 'gate', 'source', 'bulk') else 'unknown' for p in pins]
    if kind in ('resistor', 'capacitor', 'inductor'):
        return [p['role'] if p['role'] in ('positive', 'negative', 'bulk') else 'unknown' for p in pins]
    return ['unknown'] * len(pins)


def _decade(value):
    return None if not value else math.log10(abs(value))


def _compatible(a, b):
    """Two parameters may share one network column: same declared unit, or (undeclared) defaults of the same scale."""
    if a['unit'] and b['unit']:
        return a['unit'] == b['unit']
    ua = a['unit'] or b['unit']
    reference = UNIT_REFERENCE.get(ua) if ua else None
    da, db = _decade(a['default']), _decade(b['default'])
    if reference is not None:
        other = db if a['unit'] else da
        return other is None or abs(other - math.log10(reference)) <= SCALE_TOLERANCE_DECADES
    return da is None or db is None or abs(da - db) <= SCALE_TOLERANCE_DECADES


def _reference(entries):
    units = {e['unit'] for e in entries if e['unit']}
    if len(units) == 1:
        return UNIT_REFERENCE.get(next(iter(units)), 1.0)
    decades = [_decade(e['default']) for e in entries if _decade(e['default']) is not None]
    return 10.0 ** round(sum(decades) / len(decades)) if decades else 1.0


def _typical(entries, family):
    """The geometric mean of the nonzero defaults a family gives one parameter name (None if it gives none)."""
    decades = [_decade(p['default']) for d, p in entries if d['family'] == family and _decade(p['default']) is not None]
    return 10.0 ** (sum(decades) / len(decades)) if decades else None


def _assign_columns(devices):
    """Give every numeric parameter a canonical name and a network column (in place).

    canonical: the netlist name, unless that name is one of the eight standard parameters with another meaning (an
    inductor's `r` is its radius, not a resistance); then the CDF's own name for it (`rad`).
    column: the canonical name, shared by every device whose parameter of that name has the same scale; the standard
    names keep the standard scale. Names whose scales disagree across families get one column per family
    (`bjt.area`, `diode.area`)."""
    standard = standard_schema()
    standard_ref = dict(zip(standard.parameters, standard.references))
    groups = {}
    for device in devices.values():
        for p in device['parameters']:
            if not p['numeric']:
                p.update(canonical=None, column=None, reference=None, action_class=None)
                continue
            probe = dict(unit=STANDARD_UNITS.get(p['name']), default=standard_ref.get(p['name']))
            if p['name'] in STANDARD_UNITS and not _compatible(dict(p, unit=p['unit'] if p['unit'] != 'count' else None),
                                                               dict(probe, unit=probe['unit'] if probe['unit'] != 'count' else None)):
                p['canonical'] = p['cdf'] if p['cdf'] != p['name'] and p['cdf'] not in STANDARD_UNITS else f"{p['name']}_{device['family']}"
            else:
                p['canonical'] = p['name']
            if p['canonical'] in STANDARD_UNITS and not p['unit']:
                p['unit'], p['unit_basis'] = STANDARD_UNITS[p['canonical']], 'same name and scale as the standard parameter'
            groups.setdefault(p['canonical'], []).append((device, p))

    def agree(entries):
        return all(_compatible(a[1], b[1]) for i, a in enumerate(entries) for b in entries[i + 1:])

    for name, entries in sorted(groups.items()):
        if name in standard_ref:
            for _, p in entries:
                p.update(column=name, reference=standard_ref[name])
            continue
        # Within one family a name is one quantity (a transistor's `scc` stays one column even where the flavours'
        # defaults differ); only families that disagree get columns of their own.
        families = sorted({d['family'] for d, _ in entries})
        firsts = [next(item for item in entries if item[0]['family'] == f) for f in families]
        if len(families) == 1 or agree([(d, dict(p, default=_typical(entries, d['family']))) for d, p in firsts]):
            columns = {name: entries}
        else:
            columns = {f'{family}.{name}': [item for item in entries if item[0]['family'] == family] for family in families}
        for column, members in columns.items():
            reference = _reference([p for _, p in members])
            for _, p in members:
                p.update(column=column, reference=reference)
    for device in devices.values():
        for p in device['parameters']:
            if p['numeric']:
                unit = p['unit']
                p['action_class'] = p['canonical'] if p['canonical'] in STANDARD_UNITS else ACTION_CLASS.get(unit)
                if p['action_class'] == 'l' and p['canonical'] == 'w':
                    p['action_class'] = 'w'


def _vocabulary(pdk_id, devices):
    """The component list the network is built with, and what the network view does per Spectre model."""
    standard = standard_schema()
    roles = list(standard.terminal_roles)
    roles += sorted({pin['role'] for device in devices.values() for pin in device['pins']} - set(roles))
    columns = {}
    for device in devices.values():
        for p in device['parameters']:
            if p['numeric'] and p['column'] not in standard.parameters:
                columns.setdefault(p['column'], p['reference'])
    extra = sorted(columns)
    view = {model: dict(kind=device['kind'], roles=[p['role'] for p in device['pins']], family=device['family'],
                        polarity=device.get('polarity'),
                        columns={key: p['column'] for p in device['parameters'] if p['numeric']
                                 for key in dict.fromkeys((p['name'], p['canonical']))})
            for model, device in sorted(devices.items())}
    body = dict(format=VOCABULARY_FORMAT, pdk_id=pdk_id,
                device_kinds=list(standard.device_kinds) + [devices[m]['kind'] for m in sorted(devices)],
                terminal_roles=roles, net_roles=list(standard.net_roles),
                parameters=list(standard.parameters) + extra,
                references=list(standard.references) + [float(columns[c]) for c in extra], devices=view)
    sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(body, version=f'pdk-{pdk_id}-{sha[:16]}', sha256=sha)


def _summary(devices):
    counts = {}
    for device in devices.values():
        key = device['family'] if device['family'] not in ('mos', 'bjt') or not device.get('polarity') \
            else f"{device['family']}:{device['polarity']}"
        counts[key] = counts.get(key, 0) + 1
    return dict(devices=len(devices), cells=sum(len(d['cells']) for d in devices.values()), by_family=counts,
                with_problems=sorted(m for m, d in devices.items() if d['problems']))


# ------------------------------------------------------------------------------------------ the ideal parts' record
def _pin_names(order):
    """A CDF pin order as names, or None when it is absent or not a plain list. SKILL prints a pin called `t` as its
    truth value, which the reader turns into True."""
    if not isinstance(order, list) or not order:
        return None
    names = ['t' if pin is True else str(pin) for pin in order if isinstance(pin, (str, int)) or pin is True]
    return names if len(names) == len(order) and len(set(names)) == len(names) else None


def build_ideal_parts(library, cdf) -> dict:
    """What the generic library says about its parts: one entry per Spectre component a cell netlists as, with every pin
    order the library states for it and, where the standard list has a kind for the component, that kind.

    Several cells share a component, and not always with the same pins: `vdc`, `vpulse`, `vsin` netlist a `vsource` with
    two nodes, `vprbs` and the cell called `vsource` itself one with six. So a component keeps each stated pin order with
    the cells that state it, and a netlist is read with the order that has as many pins as its lines have nodes
    (`ideal_models`). A cell that netlists with a model named on the instance (`nmos4`, `bsim4`) is no component of its
    own: its model belongs to a PDK."""
    by_component, not_components = {}, []
    for name in sorted(cdf['cells']):
        spectre = cdf['cells'][name].get('spectre') or {}
        component = spectre.get('component_name')
        if not isinstance(component, str) or not component:
            not_components.append(dict(cell=name, reason='netlists with a model named on the instance' if spectre
                                       else 'no Spectre entry (not netlisted)'))
            continue
        by_component.setdefault(component, {}).setdefault(tuple(_pin_names(spectre.get('term_order')) or ()), []).append(name)
    components = {}
    for component in sorted(by_component):
        orders = by_component[component]
        # Most cells first, then the order of the cell that carries the component's own name, then the shorter one.
        stated = sorted((pins for pins in orders if pins and len(pins) <= MAX_IDEAL_PINS),
                        key=lambda pins: (-len(orders[pins]), component not in orders[pins], len(pins), pins))
        kind, aliases = IDEAL_KINDS.get(component, ('unknown', {}))
        if kind != 'unknown' and not any(len(pins) == 2 for pins in stated):
            kind, aliases = 'unknown', {}                # never the two-terminal part the standard list means
        if not stated:
            basis = 'the library states no pin order for it'
        elif kind == 'unknown':
            basis = f'Spectre component {component}: the standard list has no kind for it, so the network sees "unknown"'
        else:
            basis = f'Spectre component {component} with two nodes: the first is the positive one' + (
                ' (a current probe is a 0 V source in series)' if component == 'iprobe' else '')
        components[component] = dict(
            component=component, cells=sorted(cell for cells in orders.values() for cell in cells), kind=kind,
            parameters=dict(aliases), basis=basis,
            pin_orders=[dict(pins=list(pins), cells=sorted(orders[pins])) for pins in stated],
            cells_without_pin_order=sorted(orders.get((), [])),
            cells_with_too_many_pins=sorted(cell for pins, cells in orders.items() if len(pins) > MAX_IDEAL_PINS for cell in cells))
    body = dict(format=IDEAL_FORMAT, library=library, components=components)
    sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    usable = [c for c in components.values() if c['pin_orders']]
    return dict(body, sha256=sha, read_utc=utcnow().isoformat(), not_components=not_components,
                layout_only=cdf.get('layout_only', []),
                summary=dict(cells=len(cdf['cells']) + len(cdf.get('layout_only', [])), components=len(components),
                             recognized=len(usable), with_a_kind=sorted(c['component'] for c in usable if c['kind'] != 'unknown'),
                             as_unknown=sum(1 for c in usable if c['kind'] == 'unknown'),
                             without_pins=sorted(c['component'] for c in components.values() if not c['pin_orders'])))


def ideal_parts_of(read, previous):
    """The ideal parts for a record that is being stored: what this read brought, else what an earlier read of the same
    PDK brought (kept, with the reason this read brought nothing), else only the reason."""
    read = read or {}
    library = read.get('library') or IDEAL_LIBRARY
    reason = read.get('error')
    if read.get('cdf_text'):
        cdf = parse_cdf_text(read['cdf_text'])
        if cdf['cells']:
            return build_ideal_parts(library, cdf)
        reason = f'{library} has no cell with a component description (CDF)'
    reason = reason or 'this read did not ask for them (an older reader)'
    kept = (previous or {}).get('ideal_parts')
    if isinstance(kept, dict) and kept.get('components'):
        return dict(kept, not_read_again=reason)
    return dict(format=IDEAL_FORMAT, library=library, components={}, error=reason)


def ideal_models(record, node_counts=None) -> dict:
    """The parser's device mappings for the ideal parts read with a PDK: every component the library states a pin order
    for - its kind where the standard list has one and the line has two nodes, "unknown" with its pins named otherwise.
    `node_counts` = {component: how many nodes its lines have in the netlist being read} picks, per component, the
    stated order of that length; a component whose lines differ in length, or fit no stated order, gets no mapping (it
    stays unrecognized, which the reader of the cell reports). Without it: the first order of each component."""
    parts = (record or {}).get('ideal_parts') or {}
    models = {}
    for name, part in (parts.get('components') or {}).items():
        orders = [order['pins'] for order in part.get('pin_orders') or []]
        if node_counts is not None:
            if name not in node_counts or len(set(node_counts[name])) != 1:
                continue
            orders = [pins for pins in orders if len(pins) == next(iter(node_counts[name]))]
        if not orders:
            continue
        pins = orders[0]
        standard = part['kind'] != 'unknown' and len(pins) == 2
        models[name] = dict(kind=part['kind'] if standard else 'unknown', terminals=list(pins),
                            roles=['positive', 'negative'] if standard else ['unknown'] * len(pins),
                            parameters=dict(part['parameters']) if standard else {})
    return models


def describe_ideal_parts(record, *, brief=False):
    """What the page shows about the ideal parts read with a PDK; None for a PDK loaded before they were read."""
    parts = (record or {}).get('ideal_parts')
    if not isinstance(parts, dict):
        return None
    out = dict(library=parts.get('library'), read_utc=parts.get('read_utc'), sha256=parts.get('sha256'),
               summary=parts.get('summary'), error=parts.get('error'), not_read_again=parts.get('not_read_again'))
    if not brief:
        out.update(components=list((parts.get('components') or {}).values()), not_components=parts.get('not_components', []))
    return out


# ------------------------------------------------------------------------------------------ storage
def store_root() -> Path:
    return local_settings_dir() / 'pdks'


def pdk_dir(pdk_id) -> Path:
    """Validate a technology-library identifier and return its local PDK directory."""
    if not isinstance(pdk_id, str) or not NAME.match(pdk_id):
        raise PdkError('A PDK is named by its technology library: a plain Cadence name')
    return store_root() / pdk_id


def save_record(record) -> dict:
    """The current record of a PDK, plus every version ever loaded (a run names its version by SHA-256, and a model
    trained with one version must still find it after the PDK was loaded again)."""
    directory = pdk_dir(record['pdk_id'])
    (directory / 'versions').mkdir(parents=True, exist_ok=True)
    version = directory / 'versions' / f"{record['sha256']}.json"
    if not version.exists():
        write_json(version, record)
    write_json(directory / 'pdk.json', record)
    return record


def load_record(pdk_id, sha256=None) -> dict | None:
    """Load a current or versioned PDK record only when its identity and format match."""
    try:
        directory = pdk_dir(pdk_id)
    except PdkError:
        return None
    path = directory / ('pdk.json' if sha256 is None else f'versions/{sha256}.json')
    if sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', sha256):
        return None
    record = read_json(path, default=None)
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('pdk_id') != pdk_id:
        return None
    return record


def list_pdks() -> list:
    """Describe valid current PDK records in storage-directory order."""
    root = store_root()
    found = []
    for path in sorted(root.glob('*/pdk.json')) if root.is_dir() else ():
        record = load_record(path.parent.name)
        if record is not None:
            found.append(describe(record, brief=True))
    return found


def describe(record, *, brief=False):
    """What the page shows about a loaded PDK."""
    out = dict(pdk_id=record['pdk_id'], vocabulary=f"pdk:{record['pdk_id']}", sha256=record['sha256'],
               version=record['vocabulary']['version'], loaded_utc=record['loaded_utc'],
               technology_library=record['technology_library'], summary=record['summary'],
               label=label(record['vocabulary']), sources=record.get('sources', {}),
               columns=len(record['vocabulary']['parameters']), kinds=len(record['vocabulary']['device_kinds']),
               roles=len(record['vocabulary']['terminal_roles']), ideal_parts=describe_ideal_parts(record, brief=brief))
    if not brief:
        out.update(devices=list(record['devices'].values()), not_netlisted=record['not_netlisted'],
                   layout_only=record['layout_only'], not_used=record['model_file_definitions_not_used'],
                   parameters=record['vocabulary']['parameters'], terminal_roles=record['vocabulary']['terminal_roles'])
    return out


def label(vocabulary) -> str:
    """Describe either the standard vocabulary or a PDK vocabulary's size and version."""
    if vocabulary is None:
        return 'standard (8 generic kinds)'
    count = len(vocabulary['devices'])
    return f"PDK {vocabulary['pdk_id']} ({count} components, version {vocabulary['sha256'][:8]})"


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_ideal_parts_of = ideal_parts_of
