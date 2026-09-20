"""Read-only access to native Virtuoso data through the bridge, in a short-lived process.

Only capabilities confirmed in the local virtuoso-bridge 0.8.0 source are used:
``client.library.list()`` and ``client.schematic.read(lib, cell, ...)``. That version has NO
method that lists the cells or views of a library, and SKILL is not written from memory, so
cell and view names are entered by the user and verified by an actual read.

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
    parser.add_argument('--op', choices=('libraries', 'read_schematic'), required=True)
    parser.add_argument('--library')
    parser.add_argument('--cell')
    args = parser.parse_args(argv)
    settings = resolve_profile_id(args.profile_id)
    bridge = RealBridge(settings)
    bridge.version()
    bridge.bind_env(settings['env_file'])
    client = bridge.client(settings.get('profile') or None, 30)
    try:
        if args.op == 'libraries':
            print(json.dumps(dict(libraries=sorted(client.library.list()))))
        else:
            snapshot = client.schematic.read(args.library, args.cell, include_positions=False, param_filters=None)
            print(json.dumps(dict(snapshot=snapshot), default=str))
    finally:
        client.close()
    return 0


def read(monitor, profile_id, op, *, library=None, cell=None, timeout=90.0, command=None):
    """Gate, then run the reader process. Raises PermissionError when the gate blocks."""
    for value in (library, cell):
        if value is not None and not NAME.match(value):
            raise ValueError('library and cell must be plain Cadence names')
    gate = monitor.gate('read_cellview', profile_id)
    if not gate['allowed']:
        error = PermissionError('The connection gate blocked reading the native design')
        error.gate = gate
        raise error
    argv = (command or [sys.executable, '-m', 'gator_workbench.bridge_read']) + ['--profile-id', profile_id, '--op', op]
    if op == 'read_schematic':
        if not library or not cell:
            raise ValueError('library and cell are required')
        argv += ['--library', library, '--cell', cell]
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               shell=False, env=worker_environment(), cwd=str(repo_root()), start_new_session=True)
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
    if op == 'read_schematic':
        return summarize_snapshot(data['snapshot'], library=library, cell=cell)
    return data


if __name__ == '__main__':
    raise SystemExit(_main())
