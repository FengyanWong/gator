"""The whole-cell read, the bridge's own answer in a fraction of the time on a large cell (record 7.296).

The bridge's `client.schematic.read(library, cell, include_positions=..., param_filters=None)` runs one SKILL program
(virtuoso-bridge 0.8.0, `virtuoso_bridge.virtuoso.schematic.reader`) that grows its answer a line at a time with
`result = strcat(result X)`. Each strcat copies the whole answer so far, so the time grows with the square of the answer.
On `mscr_vco_lin_c` (34 instances, 1,092 values, a 30 kB answer) the read took 434 ms inside Virtuoso, of which getting
the values (cdfGetInstCDF and their text) was about 4 ms. Here the same program appends each line to a list (`tconc`)
and joins the list once at the end (`buildString`). The text is the same by construction, and the bridge's own parser
turns it into the same dictionary. Measured on 2026-10-09 (record 7.296: 50 rounds on mscr_vco_lin_c and mscr_ota5t,
the two texts identical in every round): 5.7 ms against 434 ms inside Virtuoso, 70 ms against 498 ms at the client.
A small cell gains nothing (mscr_ota5t, 6 kB: 15.7 against 15.5 ms at the client).

The program is derived from the bridge's own text when first used, and each change is checked to apply exactly as
measured. A bridge whose text is not that one, or one that cannot be imported (the tests' stand-ins), reads with the
bridge's own call, so a read never answers differently from the bridge's."""
from functools import lru_cache

from . import caches

TIMEOUT = 300                  # schematic.read's own default: large schematics take longer than the transport's


@lru_cache(maxsize=2)
def program(include_positions: bool):
    """The bridge's read program with its answer collected in a list, before the cell is bound; None when the bridge
    cannot be imported or its text is not the one measured."""
    try:
        from virtuoso_bridge.virtuoso.schematic import reader
        text = reader._SKILL_TOPOLOGY.replace('{geometry_inst}', reader._GEOMETRY_INST_EXPR if include_positions else '')
        text = text.replace('{notes_section}', reader._NOTES_SECTION_EXPR)
    except (ImportError, AttributeError):
        return None
    for old, new in (('let((cv result)', 'let((cv result out)'),
                     (r'result = "INSTANCES\n"', r'out = tconc(nil "INSTANCES\n")'),
                     ('\n  result)\n    else "ERROR")', '\n  buildString(car(out) ""))\n    else "ERROR")')):
        if text.count(old) != 1:
            return None
        text = text.replace(old, new)
    text = text.replace('result = strcat(result ', 'tconc(out ')
    if 'strcat(' in text or text.count('result') != 1:     # every strcat was an append; `result` is only declared now
        return None
    return text


def read_cell(client, library, cell, *, include_positions=True):
    """`client.schematic.read(library, cell, include_positions=include_positions, param_filters=None)`: the same answer."""
    text = program(include_positions)
    if text is None or not callable(getattr(client, 'execute_skill', None)):
        return client.schematic.read(library, cell, include_positions=include_positions, param_filters=None)
    from virtuoso_bridge import decode_skill_output
    from virtuoso_bridge.virtuoso.schematic import reader
    # From here on read_schematic's own steps and words (virtuoso-bridge 0.8.0), for a named cell and no filter.
    answer = client.execute_skill(reader._build_cellview_read_skill(text, library, cell), timeout=TIMEOUT)
    if getattr(answer, 'errors', None):
        raise RuntimeError(f'read_schematic SKILL error: {answer.errors[0]}')
    raw = decode_skill_output(answer.output)
    if raw.strip() == 'ERROR':
        raise RuntimeError(f'read_schematic could not open schematic {library}/{cell}')
    if not raw.strip():
        raise RuntimeError(f'read_schematic returned empty output for {library}/{cell}')
    return reader._parse_schematic(raw, include_positions=include_positions, filter_config=None)


# The cache of this module: caches.clear_all() empties it with every other one (refactoring package B10).
caches.register(globals(), 'program')
