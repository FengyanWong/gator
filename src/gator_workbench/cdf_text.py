"""A PDK's component descriptions as Virtuoso writes them (CDF): the SKILL values and property lists of the text the PDK
read returns, a parameter's form rule and numeric range, and the CDF entry of one parameter (its value, units, whether
the form lets a user type it).

Moved from pdk.py by the refactoring (docs/plan-refactoring.md); pdk.py re-exports every name.
"""
from __future__ import annotations

import math
import re


NUMERIC_CDF_TYPES = ('string', 'int', 'float')


# ------------------------------------------------------------------------------------------ SKILL output
def _fields(line):
    """Split a query line at `|`, but never inside a quoted string."""
    out, current, quoted, i = [], [], False, 0
    while i < len(line):
        char = line[i]
        if char == '\\' and quoted and i + 1 < len(line):
            current.append(line[i:i + 2])
            i += 2
            continue
        if char == '"':
            quoted = not quoted
        if char == '|' and not quoted:
            out.append(''.join(current))
            current = []
        else:
            current.append(char)
        i += 1
    out.append(''.join(current))
    return out


def skill_value(text):
    """A value printed by SKILL's %L (as the bridge returns it: its backslashes doubled once more).
    nil -> None, t -> True, "s" -> str, (a b) -> list, symbols -> str, numbers -> int/float."""
    text = (text or '').strip().replace('\\\\', '\\')
    tokens, i = [], 0
    while i < len(text):
        char = text[i]
        if char.isspace():
            i += 1
        elif char in '()':
            tokens.append(char)
            i += 1
        elif char == '"':
            j, chars = i + 1, []
            while j < len(text) and text[j] != '"':
                if text[j] == '\\' and j + 1 < len(text):
                    j += 1
                chars.append(text[j])
                j += 1
            tokens.append(('s', ''.join(chars)))
            i = j + 1
        else:
            j, chars = i, []
            while j < len(text) and not text[j].isspace() and text[j] not in '()"':
                if text[j] == '\\' and j + 1 < len(text):
                    j += 1
                chars.append(text[j])
                j += 1
            tokens.append(('a', ''.join(chars)))
            i = j

    def atom(token):
        kind, value = token
        if kind == 's':
            return value
        if value == 'nil':
            return None
        if value == 't':
            return True
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value

    def parse(position):
        token = tokens[position]
        if token == '(':
            items, position = [], position + 1
            while position < len(tokens) and tokens[position] != ')':
                item, position = parse(position)
                items.append(item)
            return items, position + 1
        if token == ')':
            raise ValueError('unbalanced SKILL list')
        return atom(token), position + 1
    if not tokens:
        return None
    value, _ = parse(0)
    return value


def _plist(value):
    """A SKILL disembodied property list `(nil k1 v1 k2 v2)` -> {k1: v1}. Symbols like `\\:d` arrive as ':d'."""
    if not isinstance(value, list) or not value or value[0] is not None:
        return {}
    items = value[1:]
    return {str(items[i]): items[i + 1] for i in range(0, len(items) - 1, 2)}


def _form_rule(text):
    """A CDF `editable` / `display` attribute: True (unset, or t), False (the expression nil), or the SKILL expression that
    decides it for one instance (e.g. gpdk045_mosEditable('w) or cdfgData->calcParam->value != "width")."""
    value = skill_value(text)
    if value is None or value is True or value == 't':
        return True
    if value == 'nil':
        return False
    return str(value)


def numeric_range(value):
    """A CDF `range` attribute as two numbers, or None when it is absent or not a plain numeric pair. The property form
    itself refuses a value outside it, so a task whose bounds leave it would die on its first clamped candidate."""
    if isinstance(value, str):
        value = [part for part in value.replace('(', ' ').replace(')', ' ').split() if part]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    return [low, high] if low <= high and math.isfinite(low) and math.isfinite(high) else None


def parse_cdf_text(text):
    """The query's lines -> {cells: {name: {...}}, leaves: {cell: [{instance, library, cell, model}]}, layout_only: [..]}."""
    cells, leaves, layout_only = {}, {}, []
    lines = [_fields(raw.rstrip('\r')) for raw in (text or '').splitlines()]
    # Cells first, then what belongs to them: the order of a library's cells (and of the lines) is not guaranteed.
    for parts in sorted(lines, key=lambda parts: parts[0] != 'CELL'):
        tag = parts[0]
        if tag == 'CELL' and len(parts) >= 11:
            name = parts[1]
            spectre = dict(term_order=skill_value(parts[3]), term_mapping=_plist(skill_value(parts[4])),
                           inst_parameters=skill_value(parts[5]), other_parameters=skill_value(parts[6]),
                           prop_mapping=_plist(skill_value(parts[7])), component_name=skill_value(parts[8]),
                           name_prefix=skill_value(parts[9]))
            has_spectre = any(v for key, v in spectre.items() if key not in ('name_prefix',))
            cells[name] = dict(name=name, model=skill_value(parts[2]), spectre=spectre if has_spectre else None,
                               views=skill_value(parts[10]) or [], parameters={})
        elif tag == 'PARAM' and len(parts) >= 7 and parts[1] in cells:
            entry = dict(type=skill_value(parts[3]), units=skill_value(parts[4]), default=skill_value(parts[5]),
                         prompt=skill_value(parts[6]))
            if len(parts) >= 11:                          # how the property form treats it (Load PDK since 2026-09-22)
                entry.update(editable=_form_rule(parts[7]), display=_form_rule(parts[8]), callback=skill_value(parts[9]),
                             choices=skill_value(parts[10]))
            if len(parts) >= 12:                          # the range the form itself enforces (2026-09-23): (low high)
                entry['range'] = numeric_range(skill_value(parts[11]))
            cells[parts[1]]['parameters'][parts[2]] = entry
        elif tag == 'FORM' and len(parts) >= 4 and parts[1] in cells:
            cells[parts[1]]['form'] = dict(init=skill_value(parts[2]), done=skill_value(parts[3]))
        elif tag == 'LEAF' and len(parts) >= 6:
            leaves.setdefault(parts[1], []).append(dict(instance=parts[2], library=parts[3], cell=parts[4],
                                                         model=skill_value(parts[5])))
        elif tag == 'NOCDF' and len(parts) >= 2:
            layout_only.append(dict(cell=parts[1], views=skill_value(parts[2]) if len(parts) > 2 else []))
    return dict(cells=cells, leaves=leaves, layout_only=sorted(layout_only, key=lambda item: item['cell']))


# ------------------------------------------------------------------------------------------ building the record
def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    from analog_optimizer.netlist.expressions import UnresolvedExpression, evaluate

    def refuse(name):
        raise UnresolvedExpression(name)
    try:
        return evaluate(str(value), refuse)
    except (UnresolvedExpression, ValueError):
        return None


_REFERENCE = re.compile(r'^\s*([ip])Par\(\s*"([A-Za-z_]\w*)"\s*\)\s*$')


def _cdf_entry(cells, cell, name, parent=None, depth=0):
    """(CDF parameter entry, default value resolved through iPar/pPar references) of `name` on `cell`."""
    entry = (cells.get(cell) or {}).get('parameters', {}).get(name)
    if entry is None:
        return None, None
    default, units = entry.get('default'), entry.get('units')
    found = _REFERENCE.match(default) if isinstance(default, str) else None
    if found and depth < 6:
        target_cell = cell if found.group(1) == 'i' else parent
        if target_cell:
            inner, value = _cdf_entry(cells, target_cell, found.group(2), None, depth + 1)
            if inner is not None:
                return dict(entry, units=units or inner.get('units')), value
        return entry, None
    return entry, _number(default)


def _write_source(cells, cell, name, parent=None, depth=0):
    """Which CDF parameter a user edits to set CDF parameter `name` of `cell`: `name` itself, or - when its default ties it
    to another one - that one: `iPar("x")` = x of the same instance (GPDK045's `simW` = `w`, an inductor's `width` = its
    choice list `width_cyclic`), `pPar("x")` = x of the cell that places this primitive (a resistor's `segL`). None when
    the chain leads nowhere. `editable` / `display` are the form's own rules (True, False or a SKILL expression decided per
    instance); both are None for a PDK loaded before the form was read."""
    entry = (cells.get(cell) or {}).get('parameters', {}).get(name)
    if entry is None or depth > 6:
        return None
    found = _REFERENCE.match(entry['default']) if isinstance(entry.get('default'), str) else None
    if found:
        if found.group(1) == 'i':
            return _write_source(cells, cell, found.group(2), parent, depth + 1)
        inner = _write_source(cells, parent, found.group(2), None, depth + 1) if parent else None
        return None if inner is None else dict(inner, on='parent')
    return dict(cdf=name, on='self', cell=cell, type=entry.get('type'), editable=entry.get('editable'),
                display=entry.get('display'), callback=entry.get('callback'), choices=entry.get('choices'),
                range=entry.get('range'))          # what the form itself accepts, when the PDK declares it


def _writable(source, numeric):
    """'yes' / 'no' / 'depends' (on the instance's current mode, decided in Virtuoso) / 'unknown' (no form read)."""
    if source is None or not numeric:
        return 'no'
    if source['editable'] is None:
        return 'unknown'
    if source['editable'] is False or source['display'] is False or source['type'] not in NUMERIC_CDF_TYPES + ('cyclic',):
        return 'no'
    if source['type'] == 'cyclic' and not (isinstance(source['choices'], list)
                                           and all(_number(c) is not None for c in source['choices'])):
        return 'no'                                       # a choice list of words (a mode), not of numbers
    return 'yes' if source['editable'] is True and source['display'] is True else 'depends'


def _leaf_of(cells, leaves, name):
    """A cell without a Spectre entry of its own: the one primitive its schematic places that has one."""
    found = [leaf for leaf in leaves.get(name, []) if (cells.get(leaf['cell']) or {}).get('spectre') and leaf.get('model')]
    return found[0] if len(found) == 1 else None
