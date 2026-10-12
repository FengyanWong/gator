"""Write candidate values into their original SPICE tokens without changing other deck text."""
from __future__ import annotations

from pathlib import Path
import re

from .ngspice_syntax import NetlistError, Parsed

def format_value(value):
    """A number ngspice reads back as the same value: 12 significant digits, plain notation."""
    return f'{float(value):.12g}'


def rewrite(parsed: Parsed, assignments, *, include_root=None, absolute_includes=False):
    """The deck with every (device_id, parameter) of `assignments` set to its value: each value's own token is
    replaced, from the last token of a line backwards so the columns stay valid. Values inside a subcircuit are written
    into its definition, which the parser guarantees is used once. With `absolute_includes`, relative .include /
    .lib paths are resolved from `include_root` (ngspice resolves them from ITS working directory, not from the
    deck's folder). Returns (text, {device_id.parameter: new token text})."""
    lines = list(parsed.lines)
    edits = {}
    by_source = parsed.by_source
    for (device_id, parameter), value in assignments.items():
        sizable = parsed.sizables.get((device_id, parameter)) or by_source.get((device_id, parameter))
        if sizable is None:
            raise NetlistError(f'{device_id}.{parameter} cannot be written: not a sizable value of this netlist')
        edits.setdefault(sizable.token.line, []).append((sizable.token, format_value(value)))
    written = {}
    for line_number, changes in edits.items():
        line = lines[line_number - 1]
        for token, text in sorted(changes, key=lambda c: -c[0].column):
            if line[token.column:token.column + len(token.text)] != token.text:
                raise NetlistError(f'line {line_number}: the deck changed under the parser ({token.text!r} not found)')
            line = line[:token.column] + text + line[token.column + len(token.text):]
            written[f'{token.line}:{token.column}'] = text
        lines[line_number - 1] = line
    if absolute_includes and include_root is not None:
        for kind, target, line_number in parsed.includes:
            path = Path(target)
            if path.is_absolute():
                continue
            line = lines[line_number - 1]
            absolute = str((Path(include_root) / path).resolve())
            quoted = re.escape(target)
            lines[line_number - 1] = re.sub(r'(?i)^(\s*\.(?:include|inc|lib)\s+)(["\']?)' + quoted + r'\2',
                                            lambda m: f'{m.group(1)}"{absolute}"', line, count=1)
    return '\n'.join(lines), written


def deck_text(parsed: Parsed, assignments, **kwargs):
    """`rewrite` plus the `.end` line a deck needs (some hand-written decks leave it out; ngspice wants it)."""
    text, written = rewrite(parsed, assignments, **kwargs)
    if not parsed.has_end:
        text = text.rstrip('\n') + '\n.end\n'
    return text, written
