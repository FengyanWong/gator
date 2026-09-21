"""Read-only access to native Virtuoso data through the bridge, in a short-lived process.

Only capabilities confirmed in the local virtuoso-bridge 0.8.0 checkout are used:
``client.library.list()``, ``client.library.get(name)``, ``client.schematic.read(lib, cell, ...)``
and, for the cells and views of one library, ``client.execute_skill`` with the SKILL of the bridge's
own example ``examples/01_virtuoso/basic/04_list_library_cells.py`` (copied, not written from
memory; read-only ``dd`` calls that open no cellview and touch no window). The bridge has no method
of its own for that listing. ``schematic.read`` always opens the view named ``schematic``, read-only,
and closes it again - which is why a view is never asked for: the listing only tells which cells
HAVE a schematic.

Native databases are queried through the bridge, never parsed as text. What is read is shown
AS READ: CDF parameter strings stay strings, and port order / parameter semantics are marked as
requiring confirmation unless a verified circuit profile covers the design. Nothing here edits a
cellview, and every call is preceded by the connection gate for ``read_cellview``.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys

from .connection import RealBridge, resolve_profile_id, worker_environment
from .paths import repo_root
from .security import redact

NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]{0,127}$')
MAX_CELLS = 5000
# The SKILL of virtuoso-bridge-lite/examples/01_virtuoso/basic/04_list_library_cells.py, unchanged. `library` has
# passed NAME, so it cannot close the string literal.
CELLS_SKILL = '''
let((lib out views)
  lib = ddGetObj("%s")
  out = ""
  when(lib
    foreach(cell lib~>cells
      views = ""
      foreach(view cell~>views
        views = strcat(views view~>name " "))
      out = strcat(out sprintf(nil "%%s|views=%%s\\n" cell~>name views))))
  out)
'''


def parse_cells(decoded):
    """`cell|views=a b c` lines -> [{name, views, has_schematic}], sorted by name."""
    cells = []
    for row in filter(None, (line.strip() for line in (decoded or '').splitlines())):
        name, _, views = row.partition('|views=')
        if NAME.match(name):
            views = sorted(v for v in views.split() if NAME.match(v))
            cells.append(dict(name=name, views=views, has_schematic='schematic' in views))
    return sorted(cells, key=lambda item: item['name'].lower())


def summarize_snapshot(snapshot, *, library, cell):
    """Turn a ``schematic.read`` snapshot into the hierarchy/parameter view of the left panel."""
    instances = []
    for item in snapshot.get('instances', []):
        terms = item.get('terms') or {}
        if isinstance(terms, list):
            terms = {t.get('name'): t.get('net') for t in terms if isinstance(t, dict)}
        instances.append(dict(
            instance_path=item.get('name'), master=dict(library=item.get('lib'), cell=item.get('cell'), view=item.get('view')),
            terminals=[dict(terminal=k, net=v) for k, v in terms.items()],
            parameters={k: dict(raw=v, value=None, note='CDF string as read; not converted') for k, v in (item.get('params') or {}).items()}))
    return dict(source='virtuoso', library=library, cell=cell, origin=snapshot.get('origin', 'bridge_readback'),
                instances=instances, instance_count=len(instances),
                nets=sorted({t['net'] for i in instances for t in i['terminals'] if t['net']}),
                requires_confirmation=['terminal order and roles of PDK devices', 'parameter semantics and units',
                                       'which parameters may be written and on which grid',
                                       'analyses, loads, supplies and ADE outputs of the testbench'],
                note='Read through the bridge. Optimizing a native design needs a verified circuit profile; the '
                     'existing ones are listed under registered real tasks.')


def _main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--op', choices=('libraries', 'cells', 'read_schematic', 'import_cell'), required=True)
    parser.add_argument('--library')
    parser.add_argument('--cell')
    parser.add_argument('--testbench')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    settings = resolve_profile_id(args.profile_id)
    bridge = RealBridge(settings)
    bridge.version()
    bridge.bind_env(settings['env_file'])
    client = bridge.client(settings.get('profile') or None, 30)
    try:
        if args.op == 'libraries':
            print(json.dumps(dict(libraries=sorted(client.library.list()))))
        elif args.op == 'cells':
            from virtuoso_bridge import decode_skill_output
            info = client.library.get(args.library)               # an unknown library raises here instead of listing nothing
            listed = client.execute_skill(CELLS_SKILL % args.library, timeout=60)
            if not listed.ok:
                raise RuntimeError('; '.join(listed.errors) or 'listing the cells failed')
            cells = parse_cells(decode_skill_output(listed.output))
            print(json.dumps(dict(library=args.library, technology_library=info.technology_library,
                                  cells=cells[:MAX_CELLS], truncated=len(cells) > MAX_CELLS)))
        elif args.op == 'import_cell':
            # Read-only: Virtuoso's own netlister writes the netlist of the testbench (or of the cell), and the
            # parameters are read back. The same two calls the run adapter makes for every candidate; no cellview
            # is edited. The bridge prints progress, so stdout is kept for the one JSON line below.
            from contextlib import redirect_stderr, redirect_stdout
            from pathlib import Path
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=False)
            info = client.library.get(args.library)
            with (out / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
                exported = client.schematic.export_netlist(args.library, args.testbench or args.cell, out / 'package', timeout=120)
                readbacks = {'core_readback.json': client.schematic.read(args.library, args.cell, include_positions=False, param_filters=None)}
                if args.testbench:
                    readbacks['testbench_readback.json'] = client.schematic.read(args.library, args.testbench,
                                                                                 include_positions=False, param_filters=None)
            structure = Path(exported['input_file']).parent / 'netlist'      # the structure-only file, as the run adapter uses it
            (out / 'netlist.scs').write_text(structure.read_text())
            for name, snapshot in readbacks.items():
                (out / name).write_text(json.dumps(snapshot, default=str, indent=1))
            print(json.dumps(dict(library=args.library, cell=args.cell, testbench_cell=args.testbench,
                                  technology_library=info.technology_library)))
        else:
            snapshot = client.schematic.read(args.library, args.cell, include_positions=False, param_filters=None)
            print(json.dumps(dict(snapshot=snapshot), default=str))
    finally:
        client.close()
    return 0


def read(monitor, profile_id, op, *, library=None, cell=None, testbench=None, timeout=90.0, command=None):
    """Gate, then run the reader process. Raises PermissionError when the gate blocks."""
    for value in (library, cell, testbench):
        if value is not None and not NAME.match(value):
            raise ValueError('library and cell must be plain Cadence names')
    gate = monitor.gate('read_cellview', profile_id)
    if not gate['allowed']:
        error = PermissionError('The connection gate blocked reading the native design')
        error.gate = gate
        raise error
    argv = (command or [sys.executable, '-m', 'gator_workbench.bridge_read']) + ['--profile-id', profile_id, '--op', op]
    if op == 'cells':
        if not library:
            raise ValueError('library is required')
        argv += ['--library', library]
    if op == 'read_schematic':
        if not library or not cell:
            raise ValueError('library and cell are required')
        argv += ['--library', library, '--cell', cell]
    incoming = None
    if op == 'import_cell':
        if not library or not cell:
            raise ValueError('library and cell are required')
        from uuid import uuid4
        from . import native_cells
        native_cells.cell_dir(library, cell)                       # validates both names before anything is created
        incoming = native_cells.store_root() / f'.incoming-{uuid4().hex}'       # same filesystem as its final place
        incoming.parent.mkdir(parents=True, exist_ok=True)
        argv += ['--library', library, '--cell', cell, '--output', str(incoming)] + (['--testbench', testbench] if testbench else [])
        timeout = max(timeout, 300.0)                              # a netlist export alone may take two minutes
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               shell=False, env=worker_environment(), cwd=str(repo_root()), start_new_session=True)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            process.communicate()
            raise TimeoutError('The bridge read did not finish in time')
        if process.returncode != 0:
            raise RuntimeError(redact(stderr.strip().splitlines()[-1] if stderr.strip() else 'bridge read failed', 400))
        data = json.loads(stdout.strip().splitlines()[-1])
        if op == 'import_cell':
            return native_cells.finish_import(incoming, library=library, cell=cell, testbench_cell=testbench,
                                              technology_library=data.get('technology_library'), profile_id=profile_id)
    finally:
        if incoming is not None and incoming.exists():             # a failed or unparseable import leaves nothing behind
            import shutil
            shutil.rmtree(incoming, ignore_errors=True)
    if op == 'read_schematic':
        return summarize_snapshot(data['snapshot'], library=library, cell=cell)
    return data


if __name__ == '__main__':
    raise SystemExit(_main())
