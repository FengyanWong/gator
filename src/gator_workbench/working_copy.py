"""Working copies: the cells the task flow edits in Virtuoso are COPIES, never the cells the user drew.

A cell read into the workbench (``native_cells``, through its testbench) gets one working copy: the testbench and
every cell of its library under it, copied into ``<library>_GATOR`` - a library the workbench creates itself, in
Virtuoso's working directory, bound to the same technology library. Cell and instance names stay the same, so every
Parameters row and Probes signal names the same instance path in the copy as in the original.

Making the copy is the first write into Virtuoso. It is an explicit press, passes the connection gate for
``write_cellview``, takes the project's Virtuoso session lock and backs up ``cds.lib`` before a library is added
(``bridge_setup.py``). It is accepted only when three things hold, each checked from what Virtuoso answers:

* the copy's netlist is the original's, line for line (comments aside): same devices, nets and values;
* every copied cell in that netlist comes from the copy library - the testbench really points at the copy;
* the original schematics read back identical before and after - nothing was written into them.

A library of that name that the workbench did not make is never written into. The record of each copy lives under
``configs/local/workbench/working_copies/<library>/<cell>/``.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from . import bridge_setup, native_cells, virtuoso_setup
from .paths import local_settings_dir
from .storage.atomic import write_json
from .storage.dataset import utcnow

FORMAT = 'gator-working-copy-1'
RECORD = 'copy.json'
ATTEMPT = 'failed_attempt.json'                  # beside the record folder: what a copy that stopped half-way wrote
LIBRARIES = 'libraries.json'                      # the libraries the workbench created: the only ones it writes into
MAX_LIBRARY = 64


class CopyError(ValueError):
    """Why a working copy cannot be made, in words the form can show."""


def store_root() -> Path:
    return local_settings_dir() / 'working_copies'


def copy_library_name(library) -> str:
    name = f'{library}{bridge_setup.SUFFIX}'
    if not native_cells.NAME.match(name) or len(name) > MAX_LIBRARY:
        raise CopyError(f'{library} is too long a library name to add "{bridge_setup.SUFFIX}" to')
    return name


def record_dir(library, cell) -> Path:
    return store_root() / _checked(library) / _checked(cell)


def _checked(name) -> str:
    if not isinstance(name, str) or not native_cells.NAME.match(name):
        raise CopyError('Library and cell names must be plain Cadence names')
    return name


def load(library, cell) -> dict | None:
    """The working copy of a cell, or None."""
    try:
        record = json.loads((record_dir(library, cell) / RECORD).read_text())
    except (OSError, ValueError, CopyError):
        return None
    return record if record.get('format') == FORMAT else None


def own_libraries() -> dict:
    try:
        return json.loads((store_root() / LIBRARIES).read_text())
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------------- checks of what came back
COMMENT = re.compile(r'^\s*//')


def structure(text) -> dict:
    """A netlist as {block: sorted statements}: comments and blank lines dropped, continuation lines joined, one block
    per `subckt ... ends` and one for the top level. The order of statements inside a block means nothing to Spectre -
    re-pointing an instance moves it in Virtuoso's database, so the netlister writes it elsewhere - which is why the
    statements are compared as sets, not as sequences."""
    statements, pending = [], ''
    for line in text.splitlines():
        if not line.strip() or COMMENT.match(line):
            continue
        pending += line.strip()
        if pending.endswith('\\'):
            pending = pending[:-1].rstrip() + ' '
            continue
        statements.append(' '.join(pending.split()))
        pending = ''
    if pending:
        statements.append(' '.join(pending.split()))
    blocks, current = {'(top level)': []}, '(top level)'
    for statement in statements:
        words = statement.split()
        if words[0] == 'subckt' and len(words) > 1:
            current = f'subckt {words[1]}'
            blocks[current] = []
        elif words[0] == 'ends':
            current = '(top level)'
        else:
            blocks[current].append(statement)
    return {name: sorted(lines) for name, lines in blocks.items()}


def netlist_libraries(text) -> dict:
    """{cell: library} from the netlister's `// Library name:` / `// Cell name:` comment pairs."""
    found, library = {}, None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('// Library name:'):
            library = stripped.split(':', 1)[1].strip()
        elif stripped.startswith('// Cell name:') and library is not None:
            found[stripped.split(':', 1)[1].strip()] = library
    return found


def compare(original_netlist, copy_netlist, *, copy_library, copied_cells) -> list[str]:
    """Problems of a copy as plain sentences; empty = the copy is the original, pointing at itself."""
    problems = []
    left, right = structure(original_netlist), structure(copy_netlist)
    for block in sorted(set(left) | set(right)):
        only_original = sorted(set(left.get(block, [])) - set(right.get(block, [])))
        only_copy = sorted(set(right.get(block, [])) - set(left.get(block, [])))
        if only_original or only_copy or len(left.get(block, [])) != len(right.get(block, [])):
            problems.append(f'The copy does not netlist like the original in {block}: '
                            f'only in the original {only_original[:3] or "-"}, only in the copy {only_copy[:3] or "-"}')
    libraries = netlist_libraries(copy_netlist)
    stray = sorted(cell for cell in copied_cells if libraries.get(cell) not in (None, copy_library))
    if stray:
        problems.append(f'In the copy these cells still come from another library: {", ".join(stray)}')
    return problems


def _own(copy_library, path, technology_library, library, profile_id):
    ours = own_libraries()
    if copy_library not in ours:
        ours[copy_library] = dict(path=path, technology_library=technology_library, created_utc=utcnow().isoformat(),
                                  for_library=library, profile_id=profile_id)
        write_json(store_root() / LIBRARIES, ours)


def _keep_attempt(incoming, attempt_file, attempt, copy_library, library, profile_id):
    """A copy that stopped half-way: the library it created is still the workbench's, and what it wrote may be written
    over by the next try of the SAME copy - nothing else in that library may."""
    try:
        progress = json.loads((incoming / 'progress.json').read_text())
    except (OSError, ValueError):
        return
    if progress.get('created_library'):
        _own(copy_library, progress.get('copy_path'), progress.get('copy_technology_library'), library, profile_id)
    written = sorted(set(attempt.get('copied', [])) | set(progress.get('copied', [])))
    if written:
        write_json(attempt_file, dict(copied=written, updated_utc=utcnow().isoformat()))


def reverify(library, cell) -> dict | None:
    """Recompute a copy's verdict from what Virtuoso exported (the copy's netlist, kept in its record folder) and the
    original's import, without contacting Virtuoso. For a copy whose files are there; None when there is no copy."""
    record, imported = load(library, cell), native_cells.load_import(library, cell)
    if record is None or imported is None:
        return None
    directory = record_dir(library, cell)
    problems = compare(Path(imported['netlist_path']).read_text(), (directory / 'netlist.scs').read_text(),
                       copy_library=record['copy']['library'], copied_cells=sorted({c['cell'] for c in record['copied']}))
    if not record.get('originals_unchanged'):
        problems.append('The original cells read back differently after the copy - look at them in Virtuoso')
    record = dict(record, problems=problems, netlist_equal=not any('netlist like' in p for p in problems),
                  verified=not problems, reverified_utc=utcnow().isoformat())
    write_json(directory / RECORD, record)
    return record


# ---------------------------------------------------------------------------------- making one
def make(monitor, profile_id, library, cell, *, command=None, timeout=600.0) -> dict:
    """Explicit press: copy the cell that was read into the workbench, with its testbench, into the workbench's own
    library. Returns the record; an existing copy is returned as it is (a copy is made once)."""
    existing = load(library, cell)
    if existing:
        return dict(existing, already=True)
    imported = native_cells.load_import(library, cell)
    if imported is None:
        raise CopyError('Read the cell into the workbench first (Read this cell into the workbench)')
    testbench = imported.get('testbench_cell')
    if not testbench:
        raise CopyError('Read the cell through its testbench first: the copy is of the testbench and the cell under it')
    copy_library = copy_library_name(library)
    ours = own_libraries()
    gate = monitor.gate('write_cellview', profile_id)
    if not gate['allowed']:
        error = PermissionError('The connection gate blocked writing into Virtuoso')
        error.gate = gate
        raise error
    target = record_dir(library, cell)
    attempt_file = target.parent / f'{cell}.{ATTEMPT}'
    try:
        attempt = json.loads(attempt_file.read_text())
    except (OSError, ValueError):
        attempt = {}
    incoming = target.parent / f'.incoming-{uuid4().hex}'
    incoming.mkdir(parents=True)
    try:
        args = ['--library', library, '--cell', cell, '--testbench', testbench, '--copy-library', copy_library,
                '--overwrite', json.dumps(sorted(attempt.get('copied', [])))]
        if copy_library in ours:
            args.append('--reuse-library')
        try:
            answer = bridge_setup.run(profile_id, 'make_copy', args=args, output=incoming, command=command, timeout=timeout)
        except BaseException:
            _keep_attempt(incoming, attempt_file, attempt, copy_library, library, profile_id)
            raise
        if answer.get('created_library'):
            _own(copy_library, answer['copy_path'], answer['copy_technology_library'], library, profile_id)
        copy_netlist = (incoming / 'netlist.scs').read_text()
        copied_cells = sorted({item['cell'] for item in answer['copied']})
        problems = compare(Path(imported['netlist_path']).read_text(), copy_netlist, copy_library=copy_library,
                           copied_cells=copied_cells)
        touched = sorted(name for name, digest in answer['originals_before'].items() if answer['originals_after'].get(name) != digest)
        if touched:
            problems.append(f'The original cells read back differently after the copy: {", ".join(touched)} - look at them in Virtuoso')
        if answer.get('copy_technology_library') != answer.get('technology_library'):
            problems.append(f'The copy library is bound to {answer.get("copy_technology_library")!r}, the original to '
                            f'{answer.get("technology_library")!r}')
        record = dict(format=FORMAT, created_utc=utcnow().isoformat(), profile_id=profile_id,
                      original=dict(library=library, cell=cell, testbench=testbench, netlist_sha256=imported['netlist_sha256']),
                      copy=dict(library=copy_library, cell=cell, testbench=testbench, path=answer['copy_path']),
                      technology_library=answer['technology_library'], created_library=answer['created_library'],
                      cds_lib=answer['cds_lib'], cells=answer['cells'], copied=answer['copied'], remastered=answer['remastered'],
                      originals_unchanged=not touched, netlist_equal=not problems, problems=problems,
                      verified=not problems)
        write_json(incoming / RECORD, record)
        incoming.rename(target)
        attempt_file.unlink(missing_ok=True)
    except BaseException:
        shutil.rmtree(incoming, ignore_errors=True)
        raise
    return dict(record, directory=str(target), already=False)


# ---------------------------------------------------------------------------------- the Maestro setup of a copy
ANALOGLIB_PRIMITIVES = ('res', 'cap', 'ind', 'vdc', 'idc', 'vsource', 'isource')     # nothing is derived from their values
SECTION = 'tt'                                                               # the verified nominal condition (gpdk045_conditions.json)


def verified(library, cell) -> dict:
    record = load(library, cell)
    if record is None:
        raise CopyError('Make the working copy first: the task flow writes only into the copy')
    if not record.get('verified'):
        raise CopyError('The working copy did not pass its checks: ' + '; '.join(record.get('problems') or ['(no details)']))
    return record


def _readbacks(library, cell) -> dict:
    """{(cell, instance): readback entry} of the testbench and the cell, as read from the ORIGINAL at import (CDF
    parameter names and values, library/cell of each instance)."""
    imported, record = native_cells.load_import(library, cell), load(library, cell)
    directory, found = Path(imported['directory']), {}
    for owner, name in ((record['original']['testbench'], 'testbench_readback.json'), (cell, 'core_readback.json')):
        try:
            data = json.loads((directory / name).read_text())
        except (OSError, ValueError):
            continue
        for instance in data.get('instances', []):
            found[(owner, instance['name'])] = instance
    return found


def bindable(library, cell) -> dict:
    """{(cell, instance): parameter names} a Maestro variable may set: analogLib's own resistor, capacitor, inductor and
    sources, which nothing else is computed from. A PDK device is never bound: its CDF callbacks derive other values
    (the GPDK045 transistor's 12 side values stayed stale under a variable width, 2026-09-21) or clamp the value."""
    verified(library, cell)
    return {key: set(entry.get('params') or {}) for key, entry in _readbacks(library, cell).items()
            if entry.get('lib') == 'analogLib' and entry.get('cell') in ANALOGLIB_PRIMITIVES}


def _original_values(library, cell) -> dict:
    """{(cell, instance, parameter): value} of the ORIGINAL design, from its CDF readback."""
    return {(c, i, p): v for (c, i), entry in _readbacks(library, cell).items() for p, v in (entry.get('params') or {}).items()}


def _request_dir(library, cell) -> Path:
    directory = record_dir(library, cell) / 'setup' / utcnow().strftime('%Y%m%dT%H%M%S%f')
    directory.mkdir(parents=True)
    return directory


def _schematics(record):
    return [c['cell'] for c in record['cells'] if 'schematic' in c['views']]


def _gated(monitor, action, profile_id, what):
    gate = monitor.gate(action, profile_id)
    if not gate['allowed']:
        error = PermissionError(f'The connection gate blocked {what}')
        error.gate = gate
        raise error


def _run_setup(op, profile_id, record, request, *, command=None):
    out = _request_dir(record['original']['library'], record['original']['cell'])
    (out / 'request.json').write_text(json.dumps(request, indent=1))
    answer = bridge_setup.run(profile_id, op, args=['--library', record['original']['library'], '--cell', record['copy']['cell'],
                                                     '--testbench', record['copy']['testbench'], '--copy-library', record['copy']['library'],
                                                     '--request', str(out / 'request.json')],
                              output=out, command=command, timeout=300.0)
    write_json(out / 'answer.json', answer)
    return answer


def _described(answer) -> dict:
    """A read-back setup as the page gets it: the setup, its fingerprint and the rows it stands for."""
    usable = bool(answer.get('test'))
    return dict(answer, fingerprint=virtuoso_setup.fingerprint(answer) if usable else None,
                rows=virtuoso_setup.to_rows(answer) if usable else dict(measurements=[], targets=[]))


def read_setup(monitor, profile_id, library, cell, *, command=None) -> dict:
    """Explicit press: what the copy's Maestro view says now. Read-only, zero cost."""
    record = verified(library, cell)
    _gated(monitor, 'read_cellview', profile_id, 'reading the Maestro setup')
    answer = _run_setup('read_setup', profile_id, record, dict(cells=_schematics(record), test=virtuoso_setup.TEST), command=command)
    return _described(answer)


def default_model_files(profile_id):
    """The model file a new test gets: the connection's own (the file every real run of the project includes), in the
    verified nominal section. None known: the test keeps what it has."""
    from .connection import resolve_profile_id
    try:
        model_file = resolve_profile_id(profile_id).get('model_file')
    except (KeyError, ValueError, OSError):
        return []
    return [[model_file, SECTION]] if model_file else []


def write_setup(monitor, profile_id, library, cell, setup, *, command=None) -> dict:
    """Explicit press: make the copy's Maestro test say what `setup` says, read it back and compare. A variable that
    is no longer set on a parameter puts the ORIGINAL cell's value back. Zero cost; writes only into the copy."""
    record = verified(library, cell)
    setup = dict(setup)
    if not setup.get('model_files'):
        setup['model_files'], setup['keep_model_files'] = default_model_files(profile_id), True
    problems = virtuoso_setup.validate(setup, bindable=bindable(library, cell))
    if problems:
        raise virtuoso_setup.SetupError('The setup cannot be written: ' + '; '.join(problems))
    _gated(monitor, 'write_cellview', profile_id, 'writing the Maestro setup')
    last_file = record_dir(library, cell) / 'last_written_setup.json'
    try:
        last = json.loads(last_file.read_text())
    except (OSError, ValueError):
        last = {}
    wanted = {(b['cell'], b['instance'], b['parameter']) for b in setup.get('bindings') or []}
    originals = _original_values(library, cell)
    restore = [[c, i, p, originals[(c, i, p)]] for c, i, p in {(b['cell'], b['instance'], b['parameter']) for b in last.get('bindings') or []} - wanted
               if (c, i, p) in originals]
    normalized = virtuoso_setup.normalize(setup)
    normalized['analyses'] = None if setup.get('analyses') is None else normalized['analyses']
    normalized['keep_model_files'] = bool(setup.get('keep_model_files'))
    answer = _run_setup('write_setup', profile_id, record, dict(cells=_schematics(record), test=normalized['test'], setup=normalized,
                                                              restore=restore), command=command)
    wanted, got = virtuoso_setup.normalize(setup), virtuoso_setup.normalize(answer)
    # What was left to the copy (analyses not sent, model files not chosen) is compared with what the copy has.
    expected = dict(wanted, analyses=wanted['analyses'] if setup.get('analyses') is not None else got['analyses'],
                    model_files=got['model_files'] if setup.get('keep_model_files') and got['model_files'] else wanted['model_files'])
    write_json(last_file, virtuoso_setup.normalize(setup))
    found = _described(answer)
    diffs = virtuoso_setup.differences(expected, answer)
    return dict(found, written=virtuoso_setup.normalize(setup), differences=diffs, matches=not diffs)
