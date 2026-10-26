"""Small edits of a Maestro deck's tail that need nothing else of the workbench (record 7.298): whether it saves the DC
operating point, and the tail with it added for a run whose network reads operating points.

Maestro's own names: the DC solve `dcOp` and its operating-point output `dcOpInfo` (Spectre `info what=oppoint`, written to
the raw results, where `psf_binary` reads it). One DC solve more per evaluation; every other analysis and output stays."""
from __future__ import annotations

import re

_DC_OP_INFO = re.compile(r'^\s*dcOpInfo\s+info\b', re.M)
_DC_OP = re.compile(r'^\s*dcOp\s+dc\b', re.M)
DC_OPERATING_POINT = ('// GATOR (record 7.298): the DC operating point a network with operating-point inputs reads\n'
                      'dcOpInfo info what=oppoint where=rawfile\n')


def has_dc_operating_point(tail) -> bool:
    """Detect a DC operating-point information directive in a deck's trailing text."""
    return bool(_DC_OP_INFO.search(tail or ''))


def with_dc_operating_point(tail):
    """A deck tail that solves and saves the DC operating point, unchanged when it does already. The info statement follows
    its DC solve directly, as Maestro writes them: a test that solves `dcOp` already gets the info right after that
    statement, any other gets both at its end."""
    if has_dc_operating_point(tail):
        return tail
    lines = (tail or '').split('\n')
    found = next((i for i, line in enumerate(lines) if _DC_OP.match(line)), None)
    if found is None:
        return (tail or '').rstrip('\n') + '\n' + DC_OPERATING_POINT.replace('dcOpInfo info', 'dcOp dc\ndcOpInfo info', 1)
    end = found
    while lines[end].rstrip().endswith('\\') and end + 1 < len(lines):      # a statement continued on the next lines
        end += 1
    return '\n'.join(lines[:end + 1] + DC_OPERATING_POINT.rstrip('\n').split('\n') + lines[end + 1:])
