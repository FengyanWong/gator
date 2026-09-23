"""Working copies: the cell the task flow edits in Virtuoso - its Maestro setup, and the device sizes of every run.

Since 2026-09-23 (user request) the workbench makes NO copy of its own. The user copies the cell and its testbench
in Virtuoso, reads the copy into the workbench, and the page asks whether it is a copy they made: on "yes" the cell
that was read IS the working copy (``declare``: a record with ``copy == original``, ``declared: true``). Everything
that writes "into the copy" then writes into that cell, which is why the page warns before the question.

Until then a cell read into the workbench (``native_cells``, through its testbench) got a copy the workbench made
(``make``): the testbench and every cell of its library under it, copied into ``<library>_GATOR`` - a library the
workbench created itself, in Virtuoso's working directory, bound to the same technology library - accepted only when
the copy's netlist was the original's, every copied cell came from the copy library, and the originals read back
unchanged. Tasks saved on such a copy keep running on it: their records name it, and nothing migrates them.
``make`` itself is still what "Save as" through the API and the tests use; the page no longer offers it.

Cell and instance names are the same in a copy as in the original, so every Parameters row and Probes signal names
the same instance path either way. The record of each working copy lives under
``configs/local/workbench/working_copies/<library>/<cell>/``.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from . import bridge_setup, native_cells, virtuoso_setup
from .connection import require_gate
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


def netlist_cells(text, library) -> list:
    """[{cell, views}] of `library` in an exported netlist, from the netlister's `// Library name:` / `// Cell name:` /
    `// View name:` comment triplets, in the order they appear (the top cell - the testbench - comes last). What a
    declared copy records as its cells, where a made copy recorded what it copied."""
    found, current = {}, {}
    for line in text.splitlines():
        stripped = line.strip()
        for key, name in (('// Library name:', 'library'), ('// Cell name:', 'cell'), ('// View name:', 'view')):
            if stripped.startswith(key):
                current[name] = stripped.split(':', 1)[1].strip()
                break
        if current.keys() >= {'library', 'cell', 'view'}:
            if current['library'] == library and native_cells.NAME.match(current['cell']) and native_cells.NAME.match(current['view']):
                views = found.setdefault(current['cell'], [])
                if current['view'] not in views:
                    views.append(current['view'])
            current = {}
    return [dict(cell=cell, views=sorted(views)) for cell, views in found.items()]


def is_declared(target) -> bool:
    """A record or target whose copy IS the cell that was read: the user's own copy, declared on the read."""
    original, copy = target.get('original') or {}, target.get('copy') or {}
    return bool(copy) and (original.get('library'), original.get('cell')) == (copy.get('library'), copy.get('cell'))


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
    if record.get('declared'):                       # the user's own copy: there is no separate original to compare with
        return record
    directory = record_dir(library, cell)
    problems = compare(Path(imported['netlist_path']).read_text(), (directory / 'netlist.scs').read_text(),
                       copy_library=record['copy']['library'], copied_cells=sorted({c['cell'] for c in record['copied']}))
    if not record.get('originals_unchanged'):
        problems.append('The original cells read back differently after the copy - look at them in Virtuoso')
    record = dict(record, problems=problems, netlist_equal=not any('netlist like' in p for p in problems),
                  verified=not problems, reverified_utc=utcnow().isoformat())
    write_json(directory / RECORD, record)
    return record


# ---------------------------------------------------------------------------------- the user's own copy (since 2026-09-23)
def declare(profile_id, library, cell) -> dict:
    """The user's OWN copy: the workbench makes no copy of its own any more (user request 2026-09-23). After a cell was
    read into the workbench, the page asks whether it is a copy the user made; on "yes" the import request carries
    `work_here` and the cell that was read becomes the task flow's working copy - the same record as a made copy, with
    copy == original - so everything that writes "into the copy" (the Maestro setup when a task is saved, the device
    sizes of every run, put back at its end) writes into THIS cell. Nothing is contacted: the import already proved
    that the cell netlists through its testbench and reads back; `verified` here means "the user said it is a copy",
    not a netlist comparison (there is no separate original). A cell that has a record keeps it (`already`), so a
    task saved on a copy the workbench made earlier keeps running on that copy."""
    existing = load(library, cell)
    if existing:
        return dict(existing, already=True)
    imported = native_cells.load_import(library, cell)
    if imported is None:
        raise CopyError('Read the cell into the workbench first (Read this cell into the workbench)')
    testbench = imported.get('testbench_cell')
    if not testbench:
        raise CopyError('Read the cell through its testbench first: a task simulates the testbench, and its Maestro setup lives there')
    technology = imported.get('technology_library')
    if technology and library == technology:
        raise CopyError(f'{library} is the technology library - the PDK itself: copy the cell into a library of yours first')
    cells = netlist_cells(Path(imported['netlist_path']).read_text(), library)
    named = {c['cell'] for c in cells}
    if not {cell, testbench} <= named:
        raise CopyError(f'The export of {testbench} does not name both {cell} and {testbench} in {library}: read the cell again '
                        'through a testbench of the same library')
    record = dict(format=FORMAT, created_utc=utcnow().isoformat(), profile_id=profile_id, declared=True,
                  original=dict(library=library, cell=cell, testbench=testbench, netlist_sha256=imported['netlist_sha256']),
                  copy=dict(library=library, cell=cell, testbench=testbench, path=None),
                  technology_library=technology, created_library=False, cds_lib=None, cells=cells, copied=[], remastered={},
                  originals_unchanged=None, netlist_equal=None, problems=[], verified=True)
    target = record_dir(library, cell)
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / RECORD, record)
    return dict(record, directory=str(target), already=False)


# ---------------------------------------------------------------------------------- making one (until 2026-09-23)
def make(monitor, profile_id, library, cell, *, command=None, timeout=600.0) -> dict:
    """Copy the cell that was read into the workbench, with its testbench, into the workbench's own library. Returns
    the record; an existing copy is returned as it is (a copy is made once). The page no longer offers this (user
    request 2026-09-23: the user makes the copy, see `declare`); `make_task_copy` (Save as through the API) and the
    tests still go this way, and tasks saved on a made copy keep running on it."""
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
    require_gate(monitor, 'write_cellview', profile_id, 'writing into Virtuoso')
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
        raise CopyError('This cell is not yet the one the task flow works in: read it into the workbench and confirm that it is a copy '
                        'you made (the Virtuoso window asks when you read it)')
    if not record.get('verified'):
        raise CopyError('The working copy did not pass its checks: ' + '; '.join(record.get('problems') or ['(no details)']))
    return record


def _readbacks(original) -> dict:
    """{(cell, instance): readback entry} of the ORIGINAL testbench and cell, as read at import (CDF parameter names and
    values, the library/cell of each instance)."""
    imported = native_cells.load_import(original['library'], original['cell'])
    if imported is None:
        return {}
    directory, found = Path(imported['directory']), {}
    for owner, name in ((original['testbench'], 'testbench_readback.json'), (original['cell'], 'core_readback.json')):
        try:
            data = json.loads((directory / name).read_text())
        except (OSError, ValueError):
            continue
        for instance in data.get('instances', []):
            found[(owner, instance['name'])] = instance
    return found


def bindable_on(target) -> dict:
    """{(cell of the copy, instance): parameter names} a Maestro variable may set: analogLib's own resistor, capacitor,
    inductor and sources, which nothing else is computed from. A PDK device is never bound: its CDF callbacks derive
    other values (the GPDK045 transistor's 12 side values stayed stale under a variable width, 2026-09-21) or clamp."""
    names = target['names']
    return {(names.get(owner, owner), instance): set(entry.get('params') or {})
            for (owner, instance), entry in _readbacks(target['original']).items()
            if entry.get('lib') == 'analogLib' and entry.get('cell') in ANALOGLIB_PRIMITIVES}


def _original_values_on(target) -> dict:
    """{(cell of the copy, instance, parameter): value} the ORIGINAL design has, from its CDF readback."""
    names = target['names']
    return {(names.get(owner, owner), instance, parameter): value
            for (owner, instance), entry in _readbacks(target['original']).items() for parameter, value in (entry.get('params') or {}).items()}


# ---------------------------------------------------------------------------------- targets: which copy a setup is about
def draft_target(library, cell) -> dict:
    """The cell's own working copy - the cell itself when the user declared it their copy, or the copy the workbench
    made before 2026-09-23 - as the setup functions take it."""
    record = verified(library, cell)
    return dict(original=record['original'], copy=record['copy'], names={c['cell']: c['cell'] for c in record['cells']},
                schematics=[c['cell'] for c in record['cells'] if 'schematic' in c['views']],
                state_dir=str(record_dir(library, cell)))


def claim(library, cell, task):
    """The first task saved from a cell takes the cell's working copy; a second task gets its own copy (Save as)."""
    record = verified(library, cell)
    if record.get('claimed_by') not in (None, task):
        raise CopyError(f'{library}/{cell} belongs to the task real:{record["claimed_by"]}: open it (Save task saves it again). Another task '
                        'needs another copy: make one in Virtuoso and read it in the Virtuoso window')
    write_json(record_dir(library, cell) / RECORD, dict(record, claimed_by=task))


def release(library, cell, task):
    record = load(library, cell)
    if record and record.get('claimed_by') == task:
        write_json(record_dir(library, cell) / RECORD, {k: v for k, v in record.items() if k != 'claimed_by'})


def task_copy_dir(task) -> Path:
    return store_root() / '_tasks' / _checked(task)


def make_task_copy(monitor, profile_id, source, task, *, source_netlist, command=None, timeout=600.0) -> dict:
    """"Save as": a copy of its own for the new task `task`, made from the working copy of the task being saved
    (`source`, a target) inside the same library, every copied cell named <original cell>_<task>. Accepted when it
    netlists like the source copy (names mapped back) and the source copy reads back unchanged. Returns its target."""
    names = {original: f'{original}_{task}' for original in source['names']}
    for name in names.values():
        if not native_cells.NAME.match(name) or len(name) > 120:
            raise CopyError(f'The copy cell name {name!r} would not be a plain Cadence name: choose a shorter task name')
    rename = {source['names'][original]: new for original, new in names.items()}
    require_gate(monitor, 'write_cellview', profile_id, 'writing into Virtuoso')
    directory = task_copy_dir(task)
    attempt_file = directory.parent / f'{task}.{ATTEMPT}'
    try:
        attempt = json.loads(attempt_file.read_text())
    except (OSError, ValueError):
        attempt = {}
    incoming = directory.parent / f'.incoming-{uuid4().hex}'
    incoming.mkdir(parents=True)
    library = source['copy']['library']
    try:
        args = ['--library', library, '--cell', source['copy']['cell'], '--testbench', source['copy']['testbench'],
                '--copy-library', library, '--reuse-library', '--rename', json.dumps(rename),
                '--overwrite', json.dumps(sorted(attempt.get('copied', [])))]
        try:
            answer = bridge_setup.run(profile_id, 'make_copy', args=args, output=incoming, command=command, timeout=timeout)
        except BaseException:
            _keep_attempt(incoming, attempt_file, attempt, library, library, profile_id)
            raise
        text = (incoming / 'netlist.scs').read_text()
        for old, new in sorted(rename.items(), key=lambda item: -len(item[1])):
            text = re.sub(rf'\b{re.escape(new)}\b', old, text)
        problems = compare(source_netlist, text, copy_library=library, copied_cells=sorted(rename))
        touched = sorted(name for name, digest in answer['originals_before'].items() if answer['originals_after'].get(name) != digest)
        if touched:
            problems.append(f'The source copy read back differently afterwards: {", ".join(touched)}')
        if problems:
            raise CopyError('The new copy did not pass its checks: ' + '; '.join(problems))
        target = dict(original=source['original'], copy=dict(library=library, cell=answer['copy_cell'], testbench=answer['copy_testbench']),
                      names=names, schematics=[names[o] for o, c in source['names'].items() if c in source['schematics']],
                      state_dir=str(directory))
        write_json(incoming / RECORD, dict(format=FORMAT, created_utc=utcnow().isoformat(), profile_id=profile_id, task=task,
                                           made_from=source['copy'], target=target, copied=answer['copied'], verified=True))
        if directory.exists():
            directory.rename(directory.with_name(f'{task}.replaced-{utcnow().strftime("%Y%m%dT%H%M%S")}'))
        incoming.rename(directory)
        attempt_file.unlink(missing_ok=True)
    except BaseException:
        shutil.rmtree(incoming, ignore_errors=True)
        raise
    return target


def _request_dir(target) -> Path:
    directory = Path(target['state_dir']) / 'setup' / utcnow().strftime('%Y%m%dT%H%M%S%f')
    directory.mkdir(parents=True)
    return directory


def _run_setup(op, profile_id, target, request, *, command=None):
    out = _request_dir(target)
    (out / 'request.json').write_text(json.dumps(request, indent=1))
    answer = bridge_setup.run(profile_id, op, args=['--library', target['original']['library'], '--cell', target['copy']['cell'],
                                                     '--testbench', target['copy']['testbench'], '--copy-library', target['copy']['library'],
                                                     '--request', str(out / 'request.json')],
                              output=out, command=command, timeout=300.0)
    write_json(out / 'answer.json', answer)
    return answer


def _described(answer) -> dict:
    """A read-back setup as the page gets it: the setup, its fingerprint and the rows it stands for."""
    usable = bool(answer.get('test'))
    return dict(answer, fingerprint=virtuoso_setup.fingerprint(answer) if usable else None,
                rows=virtuoso_setup.to_rows(answer) if usable else dict(measurements=[], targets=[]))


def read_setup_on(monitor, profile_id, target, *, command=None, acknowledge_unknown=False) -> dict:
    """What the Maestro view of one copy says now. Read-only, zero cost. `acknowledge_unknown`: see profile_preflight."""
    require_gate(monitor, 'read_cellview', profile_id, 'reading the Maestro setup', acknowledge_unknown=acknowledge_unknown)
    answer = _run_setup('read_setup', profile_id, target, dict(cells=target['schematics'], test=virtuoso_setup.TEST), command=command)
    return _described(answer)


def read_setup(monitor, profile_id, library, cell, *, command=None) -> dict:
    """Explicit press: what the cell's working copy's Maestro view says now. Read-only, zero cost."""
    return read_setup_on(monitor, profile_id, draft_target(library, cell), command=command)


def default_model_files(profile_id):
    """The model file a new test gets: the connection's own (the file every real run of the project includes), in the
    verified nominal section. None known: the test keeps what it has."""
    from .connection import resolve_profile_id
    try:
        model_file = resolve_profile_id(profile_id).get('model_file')
    except (KeyError, ValueError, OSError):
        return []
    return [[model_file, SECTION]] if model_file else []


def write_setup_on(monitor, profile_id, target, setup, *, command=None) -> dict:
    """Make one copy's Maestro test say what `setup` says, read it back and compare. A variable that is no longer set on
    a parameter puts the ORIGINAL cell's value back. Zero cost; writes only into that copy."""
    setup = dict(setup)
    if not setup.get('model_files'):
        setup['model_files'], setup['keep_model_files'] = default_model_files(profile_id), True
    problems = virtuoso_setup.validate(setup, bindable=bindable_on(target))
    if problems:
        raise virtuoso_setup.SetupError('The setup cannot be written: ' + '; '.join(problems))
    require_gate(monitor, 'write_cellview', profile_id, 'writing the Maestro setup')
    last_file = Path(target['state_dir']) / 'last_written_setup.json'
    try:
        last = json.loads(last_file.read_text())
    except (OSError, ValueError):
        last = {}
    # None = leave as the copy has it. `initial_conditions` belongs here too: without it a setup that simply does not
    # mention them (every plain "Save task" of an open task) would be read as "this test has none" and DELETE them - it
    # did, to the user's ring task on 2026-09-22 23:08, and the next save then stored a task file without them.
    keep = [part for part in ('analyses', 'variables', 'bindings', 'initial_conditions') if setup.get(part) is None]
    wanted = {(b['cell'], b['instance'], b['parameter']) for b in setup.get('bindings') or []}
    originals = _original_values_on(target)
    restore = [] if 'bindings' in keep else [
        [c, i, p, originals[(c, i, p)]] for c, i, p in {(b['cell'], b['instance'], b['parameter']) for b in last.get('bindings') or []} - wanted
        if (c, i, p) in originals]
    normalized = virtuoso_setup.normalize(setup)
    for part in keep:
        normalized[part] = None
    normalized['keep_model_files'] = bool(setup.get('keep_model_files'))
    answer = _run_setup('write_setup', profile_id, target, dict(cells=target['schematics'], test=normalized['test'], setup=normalized,
                                                              restore=restore), command=command)
    wanted, got = virtuoso_setup.normalize(setup), virtuoso_setup.normalize(answer)
    # What was left to the copy (a part not sent, model files not chosen) is compared with what the copy has.
    expected = dict(wanted, model_files=got['model_files'] if setup.get('keep_model_files') and got['model_files'] else wanted['model_files'],
                    **{part: got[part] for part in keep})
    write_json(last_file, expected)                                    # what the copy holds now
    found = _described(answer)
    diffs = virtuoso_setup.differences(expected, answer)
    return dict(found, written=expected, differences=diffs, matches=not diffs)


def last_written(target) -> dict:
    """The setup last written into this copy (what its Maestro test holds, as far as the workbench wrote it), or {}."""
    try:
        return json.loads((Path(target['state_dir']) / 'last_written_setup.json').read_text())
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def maestro_deck_on(monitor, profile_id, target, outputs, *, command=None, acknowledge_unknown=False) -> dict:
    """Maestro's own deck of one copy's test, split around its circuit (`virtuoso_setup.split_deck`), with every output
    expression translated to the names Spectre gives its results (`ocean.Names`, from the netlist's own name maps).
    What a Maestro-measured task runs on every evaluation (task flow part 5). `outputs`: [{name, expression, analysis,
    unit}]. Read-only for the design: Maestro writes its netlist files into a folder of its own. Refused in words when
    Maestro's netlist has an unexpected layout, an output reads an analysis the deck does not run, or a signal name
    cannot be translated plainly."""
    import hashlib
    from . import ocean
    require_gate(monitor, 'read_cellview', profile_id, 'netlisting the copy\'s Maestro test', acknowledge_unknown=acknowledge_unknown)
    answer = _run_setup('maestro_netlist', profile_id, target, dict(cells=target['schematics'], test=virtuoso_setup.TEST), command=command)
    folder = Path(answer['folder'])
    deck, circuit = (folder / 'input.scs').read_text(), (folder / 'netlist').read_text()
    head, tail = virtuoso_setup.split_deck(deck, circuit)
    analyses = virtuoso_setup.deck_analyses(tail)
    try:
        names = ocean.Names(folder / 'amap')
    except (OSError, ValueError) as exc:
        raise virtuoso_setup.SetupError(f'Maestro\'s name maps could not be read: {exc}')
    translated, problems = [], []
    for output in outputs:
        if output['analysis'] not in analyses:
            problems.append(f'Output {output["name"]} reads the {output["analysis"]} analysis, which the Maestro test does not run')
            continue
        try:
            translated.append(dict(output, spectre_expression=ocean.translate(output['expression'], names)))
        except ValueError as exc:
            problems.append(f'Output {output["name"]}: {exc}')
    if problems:
        raise virtuoso_setup.SetupError('; '.join(problems))
    model_file, section = virtuoso_setup.deck_include(head)
    return dict(format=virtuoso_setup.DECK_FORMAT, test=answer.get('test', virtuoso_setup.TEST), head=head, tail=tail,
                sha256=hashlib.sha256((head + '\0' + tail).encode()).hexdigest(), analyses=analyses, outputs=translated,
                model_file=model_file, section=section, circuit=circuit, netlisted_utc=utcnow().isoformat(),
                remote_netlist=answer.get('remote'))
