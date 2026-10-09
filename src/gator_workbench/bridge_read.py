"""Read-only access to native Virtuoso data through the bridge, in a short-lived process.

Only capabilities confirmed in the local virtuoso-bridge 0.8.0 checkout are used:
``client.library.list()``, ``client.library.get(name)``, ``client.schematic.read(lib, cell, ...)``
and, for the cells and views of one library, ``client.execute_skill`` with the SKILL of the bridge's
own example ``examples/01_virtuoso/basic/04_list_library_cells.py`` (copied, not written from
memory; read-only ``dd`` calls that open no cellview and touch no window). The bridge has no method
of its own for that listing. ``schematic.read`` always opens the view named ``schematic``, read-only,
and closes it again - which is why a view is never asked for: the listing only tells which cells
HAVE a schematic. Op ``pdk`` ("Load PDK", ``pdk.read_from_virtuoso``) reads a technology library's own description
with one ``execute_skill`` query and fetches its Spectre model files with the bridge's ``client.download_file`` into a
temporary folder outside the repository, deleted after scanning; one more query of the same kind reads the description
of the ideal parts' library, analogLib (``pdk.read_ideal_parts``).

Native databases are queried through the bridge, never parsed as text. What is read is shown
AS READ: CDF parameter strings stay strings, and port order / parameter semantics are marked as
requiring confirmation unless a verified circuit profile covers the design. Nothing here edits a
cellview, and every call is preceded by the connection gate for ``read_cellview``.
"""
from __future__ import annotations

import json
import re
import sys

from . import native_cells, pdk
from .connection import RealBridge, child_error, require_gate, resolve_profile_id, run_child
from .pdk import REMOTE_PATH
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
    parser.add_argument('--op', choices=('libraries', 'cells', 'read_schematic', 'import_cell', 'pdk'), required=True)
    parser.add_argument('--library')
    parser.add_argument('--cell')
    parser.add_argument('--testbench')
    parser.add_argument('--output')
    parser.add_argument('--model-file')
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
                # include_positions=True as in the run adapter's _read_snapshot: it is what adds `view` to every instance,
                # and a profile's reference readback must have the shape the adapter compares at run time.
                readbacks = {'core_readback.json': client.schematic.read(args.library, args.cell, include_positions=True, param_filters=None)}
                if args.testbench:
                    readbacks['testbench_readback.json'] = client.schematic.read(args.library, args.testbench,
                                                                                 include_positions=False, param_filters=None)
                # What the property form of every instance lets a user type (cdf_facts: one more read-only query). A
                # failed query leaves the import as before - transistor widths only - and keeps the reason.
                from . import cdf_facts
                try:
                    from virtuoso_bridge import decode_skill_output
                    answer = client.execute_skill(cdf_facts.facts_skill(args.library, args.cell), timeout=120)
                    readbacks[cdf_facts.FILE] = (cdf_facts.parse_facts(decode_skill_output(answer.output), library=args.library,
                                                                       cell=args.cell) if answer.ok else
                                                 dict(format=cdf_facts.FORMAT, library=args.library, cell=args.cell,
                                                      error=redact('; '.join(map(str, answer.errors)) or 'the query failed', 400)))
                except Exception as exc:
                    readbacks[cdf_facts.FILE] = dict(format=cdf_facts.FORMAT, library=args.library, cell=args.cell,
                                                     error=redact(f'{type(exc).__name__}: {exc}', 400))
            structure = Path(exported['input_file']).parent / 'netlist'      # the structure-only file, as the run adapter uses it
            (out / 'netlist.scs').write_text(structure.read_text())
            for name, snapshot in readbacks.items():
                (out / name).write_text(json.dumps(snapshot, default=str, indent=1))
            print(json.dumps(dict(library=args.library, cell=args.cell, testbench_cell=args.testbench,
                                  technology_library=info.technology_library)))
        elif args.op == 'pdk':
            # Read-only: the technology library's own description (CDF) in ONE query, and the model files downloaded into
            # a temporary folder outside the repository, scanned and deleted (pdk.read_from_virtuoso). Empty = the
            # technology library of the connection's design library, and the connection's model file.
            from contextlib import redirect_stdout
            from .pdk import read_from_virtuoso  # lazy: in the try: a failure of the import is handled with the rest
            with redirect_stdout(sys.stderr):                      # the bridge prints progress; stdout keeps the one JSON line
                library = args.library or (client.library.get(settings['library']).technology_library if settings.get('library') else None)
                if not library:
                    raise ValueError('Name the technology library: the connection states no design library to take it from')
                raw = read_from_virtuoso(client, technology_library=library, model_file=args.model_file or settings.get('model_file'),
                                         cache_host=host_identity(bridge, settings, args.profile_id))
            print(json.dumps(raw))
        else:
            snapshot = client.schematic.read(args.library, args.cell, include_positions=False, param_filters=None)
            print(json.dumps(dict(snapshot=snapshot), default=str))
    finally:
        client.close()
    return 0


def host_identity(bridge, settings, profile_id) -> str:
    """``user@host`` of the connection's Virtuoso host, under which the PDK reader keeps its copies of the model files
    (pdk.ModelFileCache, record 7.283: a profile's host can change while its id stays); the profile id when the bridge
    cannot say."""
    try:
        roles = bridge.roles(bridge.resolve_profile(settings.get('profile') or None))
        if roles.get('daemon_host'):
            return f"{roles.get('remote_user') or 'user'}@{roles['daemon_host']}"
    except Exception:
        pass
    return profile_id


def read(monitor, profile_id, op, *, library=None, cell=None, testbench=None, timeout=90.0, command=None, model_file=None):
    """Gate, then run the reader process. Raises PermissionError when the gate blocks."""
    for value in (library, cell, testbench):
        if value is not None and not NAME.match(value):
            raise ValueError('library and cell must be plain Cadence names')
    if model_file is not None:
        if not REMOTE_PATH.match(model_file) or '/../' in model_file:
            raise ValueError('The model file must be an absolute path on the simulator host (letters, digits, / . _ - +)')
    require_gate(monitor, 'read_cellview', profile_id, 'reading the native design')
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
    if op == 'pdk':
        argv += (['--library', library] if library else []) + (['--model-file', model_file] if model_file else [])
        timeout = max(timeout, 600.0)                              # ~5 MB of model files; a single query for all cells
    if op == 'import_cell':
        if not library or not cell:
            raise ValueError('library and cell are required')
        from uuid import uuid4
        native_cells.cell_dir(library, cell)                       # validates both names before anything is created
        incoming = native_cells.store_root() / f'.incoming-{uuid4().hex}'       # same filesystem as its final place
        incoming.parent.mkdir(parents=True, exist_ok=True)
        argv += ['--library', library, '--cell', cell, '--output', str(incoming)] + (['--testbench', testbench] if testbench else [])
        timeout = max(timeout, 300.0)                              # a netlist export alone may take two minutes
    try:
        finished = run_child(argv, timeout)
        if finished is None:
            raise TimeoutError('The bridge read did not finish in time')
        stdout, stderr, code = finished
        if code != 0:
            raise child_error(stderr, 'bridge read failed')
        data = json.loads(stdout.strip().splitlines()[-1])
        if op == 'import_cell':
            # The PDK - and the ideal parts read with it - before the cell's device mapping is built: a part that this very
            # press describes for the first time is then recognized in the cell at once, not only at the next read.
            read_pdk = pdk_with_import(monitor, profile_id, data.get('technology_library'), command=command)
            imported = native_cells.finish_import(incoming, library=library, cell=cell, testbench_cell=testbench,
                                                  technology_library=data.get('technology_library'), profile_id=profile_id)
            return dict(imported, pdk=read_pdk)
        if op == 'pdk':
            from . import pdk  # lazy: in the try: a failure of the import is handled with the rest
            return pdk.describe(pdk.finish_load(data))
    finally:
        if incoming is not None and incoming.exists():             # a failed or unparseable import leaves nothing behind
            import shutil
            shutil.rmtree(incoming, ignore_errors=True)
    if op == 'read_schematic':
        return summarize_snapshot(data['snapshot'], library=library, cell=cell)
    return data


def pdk_with_import(monitor, profile_id, technology_library, *, command=None) -> dict:
    """The PDK of a cell that was just read, read in the same press (user request 2026-09-27): the technology library its
    design library is attached to, through the same connection and the same gate, stored exactly as a press of "Load" in
    the PDK window stores it (versioned by content; reading an unchanged PDK again changes nothing). Reported BESIDE the
    cell, never instead of it: whatever fails here leaves the import as it is and says why. `state`: read / not_read /
    skipped."""
    if not technology_library:
        return dict(state='skipped', reason='The design library states no technology library, so no PDK was read with the '
                                            'cell. Name the PDK in the PDK window.')
    try:
        described = read(monitor, profile_id, 'pdk', library=technology_library, command=command)
    except Exception as exc:                      # the gate, a timeout, the reader, a PDK nothing was recognized in: all in words
        return dict(state='not_read', technology_library=technology_library, reason=str(exc) or exc.__class__.__name__)
    return dict(state='read', technology_library=technology_library, pdk_id=described['pdk_id'], vocabulary=described['vocabulary'],
                label=described['label'], version=described['version'], sha256=described['sha256'], summary=described['summary'],
                loaded_utc=described['loaded_utc'], ideal_parts=pdk.describe_ideal_parts(pdk.load_record(described['pdk_id']), brief=True))


if __name__ == '__main__':
    raise SystemExit(_main())
