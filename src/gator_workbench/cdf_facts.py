"""What the property form of each instance of a cell lets a user edit - read from Virtuoso, never assumed.

Read together with the cell itself (``bridge_read`` op ``import_cell``: one more read-only query, stored as
``core_cdf.json`` beside the netlist and the readback). For every instance of the core cell: its master; for every
master (and for a master without a Spectre entry of its own - a PDK resistor places a primitive - the primitives its
schematic places): the CDF exactly as the PDK loader reads it (``pdk.parse_cdf_text``: parameters with type, default,
units, the form's editable / display rules, callback, choices; the form's init and done procedures; the Spectre entry
that says which CDF parameter feeds which netlist parameter). And per instance, the form's rules that are SKILL
expressions, evaluated on that instance as it is now (``cdfgData->calcParam->value != "width"``): yes, no, or "decided
by the open form" when the rule needs the form's widgets (GPDK045's ``gpdk045_mosEditable`` does).

Nothing is edited: the cell and the masters' schematics are opened read-only and closed, no form procedure is run,
the query reports whether the cell was modified afterwards (it never was in the probes).

``sources`` and ``editable`` then answer, for one netlist parameter of one device, which CDF parameter a user types
to set it and whether the form lets them - the basis of what Save task accepts as a writable parameter
(``cdf_rules``) and of what the real run writes (``cdf_write``).
"""
from __future__ import annotations

import re

from .pdk import CDF_UNITS, _fields, _number, _write_source, parse_cdf_text, skill_value

FORMAT = 'gator-cdf-facts-1'
FILE = 'core_cdf.json'
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]{0,127}$')
MODE_TYPES = ('cyclic', 'boolean', 'radio')           # a parameter that selects a mode: never changed by a write

FACTS_SKILL = r'''
let((cv lines masters extra cell cdf sp mp lcv val key rule)
  lines = nil
  masters = nil
  extra = nil
  cv = dbOpenCellViewByType("@LIBRARY@" "@CELL@" "schematic" "schematic" "r")
  unwindProtect(
    progn(
      unless(cv error("cannot open the cell"))
      lines = cons(sprintf(nil "OPENED|%L|%L" cv~>mode cv~>modifiedButNotSaved) lines)
      foreach(inst cv~>instances
        when(inst~>purpose != "pin"
          lines = cons(sprintf(nil "INST|%s|%s|%s" inst~>name inst~>libName inst~>cellName) lines)
          when(ddGetObj(inst~>libName inst~>cellName)
            key = list(inst~>libName inst~>cellName)
            unless(member(key masters) masters = cons(key masters))
            let((cdfgData cdfgForm)
              cdfgData = cdfGetInstCDF(inst)
              cdfgForm = nil
              when(cdfgData
                foreach(p cdfgData~>parameters
                  foreach(which '("E" "D")
                    rule = if(which == "E" p~>editable p~>display)
                    when(and(stringp(rule) rule != "t" rule != "nil")
                      val = errsetstring(rule)
                      lines = cons(sprintf(nil "RULE|%s|%s|%s|%s" inst~>name p~>name which
                        cond((null(val) "form") (car(val) "yes") (t "no"))) lines)))))))))
      foreach(key masters
        cell = ddGetObj(car(key) cadr(key))
        cdf = cdfGetBaseCellCDF(cell)
        when(and(cdf null(get(cdf~>simInfo 'spectre)) member("schematic" cell~>views~>name))
          lcv = nil
          unwindProtect(
            progn(
              lcv = dbOpenCellViewByType(car(key) cadr(key) "schematic" "schematic" "r")
              when(lcv
                foreach(inst lcv~>instances
                  when(inst~>purpose != "pin"
                    lines = cons(sprintf(nil "LEAF|%s|%s|%s|%s|%L" cadr(key) inst~>name inst~>libName inst~>cellName
                      dbGetq(inst model)) lines)
                    when(and(ddGetObj(inst~>libName inst~>cellName)
                             !member(list(inst~>libName inst~>cellName) masters)
                             !member(list(inst~>libName inst~>cellName) extra))
                      extra = cons(list(inst~>libName inst~>cellName) extra))))))
            when(lcv dbClose(lcv) lcv = nil))))
      foreach(key append(reverse(masters) reverse(extra))
        cell = ddGetObj(car(key) cadr(key))
        cdf = cdfGetBaseCellCDF(cell)
        lines = cons(sprintf(nil "MASTER|%s|%s|%L" cadr(key) car(key) and(cdf t)) lines)
        when(cdf
          sp = get(cdf~>simInfo 'spectre)
          mp = cdfFindParamByName(cdf "model")
          lines = cons(sprintf(nil "CELL|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cadr(key)
            if(mp mp~>defValue nil) get(sp 'termOrder) get(sp 'termMapping) get(sp 'instParameters)
            get(sp 'otherParameters) get(sp 'propMapping) get(sp 'componentName) get(sp 'namePrefix)
            cell~>views~>name) lines)
          lines = cons(sprintf(nil "FORM|%s|%L|%L" cadr(key) cdf~>formInitProc cdf~>doneProc) lines)
          foreach(p cdf~>parameters
            lines = cons(sprintf(nil "PARAM|%s|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cadr(key) p~>name p~>paramType p~>units
              p~>defValue p~>prompt p~>editable p~>display p~>callback p~>choices p~>range) lines))))
      lines = cons(sprintf(nil "AFTER|%L" cv~>modifiedButNotSaved) lines))
    when(cv dbClose(cv)))
  buildString(reverse(lines) "\n"))
'''


def facts_skill(library, cell) -> str:
    for value in (library, cell):
        if not NAME.match(value or ''):
            raise ValueError('library and cell must be plain Cadence names')
    return FACTS_SKILL.replace('@LIBRARY@', library).replace('@CELL@', cell)


def parse_facts(text, *, library, cell) -> dict:
    """The query's lines -> {format, library, cell, instances, masters, cells, leaves, rules, modified, conflicts}."""
    instances, masters, rules, conflicts, opened, after = {}, {}, {}, [], None, None
    for raw in (text or '').splitlines():
        parts = _fields(raw.rstrip('\r'))
        tag = parts[0] if parts else ''
        if tag == 'INST' and len(parts) >= 4:
            instances[parts[1]] = dict(library=parts[2], cell=parts[3])
        elif tag == 'RULE' and len(parts) >= 5 and parts[3] in ('E', 'D') and parts[4] in ('yes', 'no', 'form'):
            rules.setdefault(parts[1], {}).setdefault(parts[2], {})['editable' if parts[3] == 'E' else 'display'] = parts[4]
        elif tag == 'MASTER' and len(parts) >= 3:
            if parts[1] in masters and masters[parts[1]] != parts[2]:
                conflicts.append(parts[1])                 # one cell name in two libraries: its facts cannot be told apart
            masters[parts[1]] = parts[2]
        elif tag == 'OPENED':
            opened = parts[1:]
        elif tag == 'AFTER' and len(parts) >= 2:
            after = skill_value(parts[1])
    cdf = parse_cdf_text(text)
    return dict(format=FORMAT, library=library, cell=cell, instances=instances, masters=masters, cells=cdf['cells'],
                leaves=cdf['leaves'], rules=rules, conflicts=sorted(set(conflicts)),
                opened_mode=skill_value(opened[0]) if opened else None, modified_after=bool(after))


# ------------------------------------------------------------------------------------------ one netlist parameter
class NotWritable(ValueError):
    """Why a parameter cannot be written by a real run, in words the editor can show."""


def _device(facts, core, device):
    """(instance, its master cell, the cell whose Spectre entry netlists the device, parent cell or None)."""
    parts = (device or '').split('/')
    if len(parts) not in (2, 3) or parts[0] != core:
        raise NotWritable(f'{device}: only parts directly inside the core cell ({core}/...) - or the one primitive a PDK cell '
                          'of the core cell places - can be written')
    instance = parts[1]
    placed = facts['instances'].get(instance)
    if placed is None:
        raise NotWritable(f'{device}: {instance} is not an instance of the core cell as it was read')
    master = placed['cell']
    if master in facts.get('conflicts', ()):
        raise NotWritable(f'{device}: two libraries have a cell called {master}; its form cannot be told apart')
    cells = facts['cells']
    if master not in cells:
        raise NotWritable(f'{device}: its cell {placed["library"]}/{master} has no description (CDF) to edit it by')
    if len(parts) == 2:
        if not cells[master].get('spectre'):
            raise NotWritable(f'{device}: {master} is netlisted through the parts inside it; name the part (e.g. {device}/R0)')
        return instance, master, master, None
    leaf = next((item for item in facts['leaves'].get(master, []) if item['instance'] == parts[2]), None)
    if leaf is None or leaf['cell'] not in cells or not cells[leaf['cell']].get('spectre'):
        raise NotWritable(f'{device}: {parts[2]} is not a netlisted part of the cell {master}')
    return instance, master, leaf['cell'], master


def sources(facts, core, device) -> dict:
    """{netlist parameter: where a user sets it (pdk._write_source) or None} for every netlist parameter of `device`."""
    instance, master, netlisted, parent = _device(facts, core, device)
    cell = facts['cells'][netlisted]
    spectre = cell['spectre'] or {}
    prop = {str(k): str(v) for k, v in (spectre.get('prop_mapping') or {}).items()}
    found = {}
    for name in [str(p) for p in spectre.get('inst_parameters') or []]:
        cdf_name = prop.get(name, name)
        if cdf_name not in cell['parameters'] and name in cell['parameters']:
            cdf_name = name
        found[name] = _write_source(facts['cells'], netlisted, cdf_name, parent)
    return found


def _rule_state(facts, instance, cdf_name, which):
    return ((facts.get('rules') or {}).get(instance) or {}).get(cdf_name, {}).get(which)


# analogLib's display rule asks whether the simulator the form is opened for lists the parameter. Read outside ADE it says
# no, yet every parameter written here is one of Spectre's instance parameters (`sources`), so Spectre's form shows it.
TOOL_DISPLAY = re.compile(r"\s*artParameterInToolDisplay\(\s*'?\w+\s*\)\s*")


def editable(facts, instance, source) -> str | None:
    """None when the form lets a user type this value into `instance` now (or only the open form can tell), else why not."""
    if source['editable'] is None:
        return 'this PDK was read before the form rules were: read the cell again'
    if source['editable'] is False:
        return 'the form never lets a user type it (it is computed)'
    if source['display'] is False:
        return 'the form never shows it'
    if _rule_state(facts, instance, source['cdf'], 'editable') == 'no':
        return f'the form greys it out in the setting {instance} has now (its rule: {source["editable"]})'
    if _rule_state(facts, instance, source['cdf'], 'display') == 'no' and not TOOL_DISPLAY.fullmatch(str(source['display'])):
        return f'the form hides it in the setting {instance} has now (its rule: {source["display"]})'
    return None


def value_kind(source, current):
    """(kind, choices) of a CDF parameter holding a number, or raise NotWritable. string = a number typed as text."""
    kind = source['type']
    if kind == 'cyclic':
        choices = source.get('choices')
        if not isinstance(choices, list) or not choices or any(_number(c) is None for c in choices):
            raise NotWritable('it is a choice between words (a mode), not a number')
        return 'choice', [str(c) for c in choices]
    if kind in MODE_TYPES:
        raise NotWritable(f'it is a {kind} setting, not a number')
    if kind not in ('string', 'int', 'float'):
        raise NotWritable(f'its CDF type is {kind!r}')
    if kind == 'string' and _number(current) is None:
        raise NotWritable(f'its present value {current!r} is not a number')
    return kind, None


def unit_of(facts, source) -> str:
    """The canonical unit of a CDF parameter: its declared units, else a count."""
    entry = ((facts['cells'].get(source['cell']) or {}).get('parameters') or {}).get(source['cdf']) or {}
    return CDF_UNITS.get(entry.get('units')) or '1'


def mode_parameters(facts, cell) -> list:
    """The settings of a cell's form that choose a mode (shown to the user; a hidden one is bookkeeping)."""
    return sorted(name for name, entry in ((facts['cells'].get(cell) or {}).get('parameters') or {}).items()
                  if entry.get('type') in MODE_TYPES and entry.get('display') is not False)


def form_of(facts, cell) -> dict:
    form = (facts['cells'].get(cell) or {}).get('form') or {}
    return dict(init=form.get('init'), done=form.get('done'))
