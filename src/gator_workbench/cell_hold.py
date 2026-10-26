"""A cell one Virtuoso session holds open for editing: which session, and letting go of it (record 7.351).

Virtuoso's own lock: a cell one Virtuoso holds open for editing cannot be written through another one, and the hold
outlives the work that took it - a run's form writer opens the cell for editing and closes its own reference, while the
session's simulation setup keeps one more open (record 7.311; record 7.350 met it on the published reference, whose run in
the second Virtuoso stopped at its first parameter write). Letting go = reopening the cell read-only (`dbReopen`): it stays
open, the lock goes. Only when nothing can be lost: no unsaved edits, and in no window, where the user may be editing it.

The SKILL uses only what the bridge's own code uses (`dbGetOpenCellViews`, `dbIsCellViewModified`, `hiGetWindowList` with
`win~>cellView`: virtuoso_bridge maestro/lifecycle.py, sos/cellview.py, layout/ops.py) and the `dbReopen` the published
reference was let go of with on 2026-10-14 (record 7.350). Every call is a short-lived process (`connection.run_child`).
Letting go changes Virtuoso, so it passes the connection gate first, like a write; the look reads only, and asks
without one - a gate's probe would cost a second or two before every Start, and a session that does not answer is simply
not counted (`session_routing`).
"""
from __future__ import annotations

import json
import sys

from .connection import RealBridge, child_error, json_lines, require_gate, resolve_profile_id, run_child
from .security import redact, skill_string

LOOK_SECONDS = 20          # one session's answer; a session busy with a run can be slow to answer
VIEW = 'schematic'


def _matching(library, cell) -> str:
    return (f'and(cv~>libName == {skill_string(library)} cv~>cellName == {skill_string(cell)} '
            f'cv~>viewName == {skill_string(VIEW)})')


# One line per open cellview of the cell: its mode ("a" = open for editing, "r" = read-only), whether it has unsaved
# edits, and in how many windows it is shown. Read-only: nothing is opened, changed or closed.
LOOK = '''let((rows shown)
  rows = ""
  foreach(cv dbGetOpenCellViews()
    when(%(matching)s
      shown = 0
      foreach(win hiGetWindowList()
        when(eq(car(errset(win~>cellView)) cv) shown = shown + 1))
      rows = strcat(rows sprintf(nil "%%s|%%s|%%d\\n" cv~>mode if(dbIsCellViewModified(cv) "modified" "saved") shown))))
  rows)'''

# The cell's cellview open for editing, reopened read-only - refused in words when it has unsaved edits or is shown in
# a window. "released", or "none" when this session does not hold the cell open for editing (any more).
RELEASE = '''let((done)
  done = "none"
  foreach(cv dbGetOpenCellViews()
    when(and(%(matching)s cv~>mode == "a")
      when(dbIsCellViewModified(cv) error("%%s" "the cell has unsaved edits in this Virtuoso"))
      foreach(win hiGetWindowList()
        when(eq(car(errset(win~>cellView)) cv) error("%%s" "the cell is shown in a window of this Virtuoso")))
      unless(dbReopen(cv "r") error("%%s" "dbReopen did not reopen the cell read-only"))
      done = "released"))
  done)'''


# What a run does with its own cell when it ends (`cdf_write.CellLocked`): the same reopening, but silent - a cell with
# unsaved edits or in a window is left as it is, and nothing is raised. "released" or "none".
LET_GO = '''let((done)
  done = "none"
  foreach(cv dbGetOpenCellViews()
    when(and(%(matching)s cv~>mode == "a" !dbIsCellViewModified(cv)
             !exists(win hiGetWindowList() eq(car(errset(win~>cellView)) cv)))
      when(dbReopen(cv "r") done = "released")))
  done)'''


def let_go_skill(library, cell) -> str:
    """Render the SKILL request to release an unmodified cell's edit lock when it is not shown in a window."""
    return LET_GO % dict(matching=_matching(library, cell))


def parse_rows(decoded) -> dict:
    """The LOOK answer as one summary: open (bool), editing (open for editing), saved (no unsaved edits), windows."""
    rows = []
    for line in filter(None, (str(decoded or '').strip().splitlines())):
        mode, _, rest = line.strip().partition('|')
        state, _, shown = rest.partition('|')
        rows.append(dict(mode=mode, saved=state == 'saved', windows=int(shown) if shown.isdigit() else 0))
    return dict(open=bool(rows), editing=any(r['mode'] == 'a' for r in rows), saved=all(r['saved'] for r in rows),
                windows=sum(r['windows'] for r in rows))


def _call(op, profile_id, library, cell, timeout):
    what = 'the look at the cell' if op == 'look' else 'letting go of the cell'
    finished = run_child([sys.executable, '-m', 'gator_workbench.cell_hold', '--profile-id', profile_id, '--op', op,
                          '--library', library, '--cell', cell], timeout)
    if finished is None:
        raise TimeoutError(f'Virtuoso did not answer within {timeout:.0f} s')
    stdout, stderr, code = finished
    if code != 0:
        raise child_error(stderr, f'{what} failed')
    data = next((d for d in json_lines(stdout) if isinstance(d, dict) and d.get('op') == op), None)
    if data is None:
        raise RuntimeError(f'{what}: no answer')
    return data


def look(profile_id, library, cell, *, timeout=LOOK_SECONDS) -> dict:
    """How session `profile_id` holds the cell (`parse_rows`); read-only, without a gate. Raises when the session could
    not be asked."""
    return _call('look', profile_id, library, cell, timeout)['hold']


def release(monitor, profile_id, library, cell, *, timeout=LOOK_SECONDS) -> bool:
    """Let go of the cell in session `profile_id`, after the connection gate: True when it held the cell open for editing
    and now holds it read-only, False when it did not hold it so. Raises, in words, when it may not (unsaved edits, a
    window) or could not."""
    require_gate(monitor, 'write_cellview', profile_id, 'letting go of the cell', acknowledge_unknown=True)
    return _call('release', profile_id, library, cell, timeout)['released']


def _main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--op', choices=('look', 'release'), required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--cell', required=True)
    args = parser.parse_args(argv)
    settings = resolve_profile_id(args.profile_id)
    bridge = RealBridge(settings)
    bridge.version()
    bridge.bind_env(settings['env_file'])
    client = bridge.client(settings.get('profile') or None, 30)
    try:
        from virtuoso_bridge import decode_skill_output
        text = (LOOK if args.op == 'look' else RELEASE) % dict(matching=_matching(args.library, args.cell))
        answer = client.execute_skill(text, timeout=LOOK_SECONDS - 5)
        if not answer.ok or answer.errors:
            raise RuntimeError('; '.join(map(str, answer.errors)) or 'the SKILL call failed')
        decoded = decode_skill_output(answer.output)
        print(json.dumps(dict(op='look', hold=parse_rows(decoded)) if args.op == 'look'
                         else dict(op='release', released=str(decoded).strip() == 'released')))
    except Exception as exc:
        print(redact(f'{type(exc).__name__}: {exc}', 400), file=sys.stderr)
        return 1
    finally:
        try:
            client.close()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(_main())
