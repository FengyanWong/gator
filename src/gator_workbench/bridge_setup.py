"""Writes into Virtuoso for the task flow, in a short-lived process - never into the cell the user drew.

Two kinds of write, both into the working copy only. The WORKING COPY itself (`working_copy.py`): the testbench and every cell of the same library
under it are copied into a library of the workbench's own (``<library>_GATOR``, next to the user's libraries in
Virtuoso's working directory, bound to the same technology library), and the copied testbench is re-pointed at the
copied cells. And the MAESTRO SETUP of the copy's testbench (`virtuoso_setup.py`): one test, its model file, analyses,
outputs, specs and design variables (``maeOpenSetup`` in a background session, ``maeCreateTest``, ``maeSetEnvOption``,
``maeSetAnalysis``, ``maeDeleteOutput`` / ``maeAddOutput``, ``maeSetSpec``, ``maeSetVar`` / ``maeDeleteVar``,
``maeSaveSetup``, always closed with ``maeCloseSession ?forceClose t``), read back with ``maeGetSetup``,
``maeGetEnabledAnalysis``, ``maeGetAnalysis``, ``maeGetTestOutputs``, ``maeGetVar``, ``maeGetEnvOption`` and
``axlGetSpecData``. Only functions whose syntax was read from the Cadence documentation of the installation itself
(``client.find_skill``) are used: ``dbOpenCellViewByType``, ``dbCopyCellView``, ``dbSetInstHeaderMasterName``,
``schCheck``, ``dbSave``, ``dbClose``, ``getWorkingDir`` - and the bridge's own ``library.create`` (``ddCreateLib`` +
``techBindTechFile``, read back) and ``schematic.export_netlist``.

Cellviews are opened by library and cell name, never through a window, so what has the focus does not matter. The
process takes the project's Virtuoso session lock (the one every real run and the no-simulation check take), so a
write never interleaves with a simulation's own edits. Every name has passed ``NAME`` before it is put into SKILL.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
import sys
from pathlib import Path

from . import directories, virtuoso_setup
from .connection import RealBridge, child_error, resolve_profile_id, run_child
from .names import CADENCE_NAME
from .paths import bridge_session_lock
from .security import skill_string as _q

NAME = re.compile(CADENCE_NAME)
COPIED_VIEWS = ('schematic', 'symbol')
SUFFIX = '_GATOR'

# The cells of `library` under the testbench, and each one's views: `cell|views=a b|cdf=t` lines. Read-only - cellviews
# opened "r" and closed again; a cellview the user has open in a window stays open (dbClose drops only this reference).
HIERARCHY_SKILL = '''
let((lib todo seen out cell cv views)
  lib = "%(library)s"
  todo = list("%(testbench)s")
  out = ""
  while(todo
    cell = car(todo)
    todo = cdr(todo)
    unless(member(cell seen)
      seen = cons(cell seen)
      views = ""
      foreach(v ddGetObj(lib cell)~>views views = strcat(views v~>name " "))
      out = strcat(out sprintf(nil "%%s|views=%%s|cdf=%%L\\n" cell views
                               and(isCallable('cdfGetBaseCellCDF) cdfGetBaseCellCDF(ddGetObj(lib cell)) t)))
      when(ddGetObj(lib cell "schematic")
        cv = dbOpenCellViewByType(lib cell "schematic" nil "r")
        when(cv
          foreach(ih cv~>instHeaders
            when(ih~>libName == lib && !member(ih~>cellName seen)
              todo = cons(ih~>cellName todo)))
          dbClose(cv)))))
  out)
'''
# One view of one cell into the copy library. g_overwrite is t only for a cellview a failed earlier attempt of the
# same copy wrote (the caller lists them); anything else already there makes the whole copy stop before writing.
COPY_VIEW_SKILL = '''
let((src dst)
  src = dbOpenCellViewByType("%(library)s" "%(cell)s" "%(view)s" nil "r")
  unless(src error("cannot open %(library)s/%(cell)s/%(view)s"))
  dst = dbCopyCellView(src "%(copy_library)s" "%(dest)s" "%(view)s" nil nil %(overwrite)s)
  dbClose(src)
  unless(dst error("dbCopyCellView refused %(copy_library)s/%(dest)s/%(view)s"))
  dbClose(dst)
  t)
'''
# Which of the cellviews about to be written already exist in the copy library: "cell/view " words.
EXISTING_SKILL = '''
let((out)
  out = ""
  foreach(pair list(%(pairs)s)
    when(ddGetObj("%(copy_library)s" car(pair) cadr(pair))
      out = strcat(out car(pair) "/" cadr(pair) " ")))
  out)
'''
# Re-point every instance of a copied cell in one copied schematic at its copy (same name, or the new name of a "Save as"
# copy), then check and save it. Answers "remastered|<header count>|<schCheck result>".
REMASTER_SKILL = '''
let((cv n checked pairs hit)
  pairs = list(%(pairs)s)
  cv = dbOpenCellViewByType("%(copy_library)s" "%(dest)s" "schematic" nil "a")
  unless(cv error("cannot open %(copy_library)s/%(dest)s/schematic for editing"))
  n = 0
  foreach(ih cv~>instHeaders
    hit = assoc(ih~>cellName pairs)
    when(ih~>libName == "%(library)s" && hit
      dbSetInstHeaderMasterName(ih "%(copy_library)s" cadr(hit) ih~>viewName)
      n = n + 1))
  checked = schCheck(cv)
  dbSave(cv)
  dbClose(cv)
  sprintf(nil "remastered|%%d|%%L" n checked))
'''


def parse_hierarchy(decoded):
    """`cell|views=a b|cdf=t` lines -> [{cell, views, has_cdf}] in discovery order (testbench first)."""
    cells = []
    for row in filter(None, (line.strip() for line in (decoded or '').splitlines())):
        name, _, rest = row.partition('|views=')
        views, _, cdf = rest.partition('|cdf=')
        if NAME.match(name):
            cells.append(dict(cell=name, views=sorted(v for v in views.split() if NAME.match(v)), has_cdf=cdf.strip() not in ('', 'nil')))
    return cells


def fingerprint(snapshot) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def _skill(client, text, what, timeout=60):
    from virtuoso_bridge import decode_skill_output
    result = client.execute_skill(text, timeout=timeout)
    if not result.ok or result.errors:
        raise RuntimeError(f'{what}: ' + ('; '.join(result.errors) or 'SKILL call failed'))
    return decode_skill_output(result.output)


def _originals(client, library, cells):
    """Read-only fingerprints of the original schematics: compared before and after, they prove the copy wrote
    nothing into the user's cells."""
    return {c['cell']: fingerprint(client.schematic.read(library, c['cell'], include_positions=True, param_filters=None))
            for c in cells if 'schematic' in c['views']}


def make_copy(client, *, library, cell, testbench, copy_library, reuse_library, overwrite, out, rename=None):
    """Copy the testbench and its library's cells under it into `copy_library`. `progress.json` in `out` is rewritten
    after every step, so a copy that stops half-way still says which library it created and what it wrote."""
    progress = dict(created_library=False, copied=[])

    def note(**changes):
        progress.update(changes)
        (out / 'progress.json').write_text(json.dumps(progress, indent=1))

    info = client.library.get(library)
    working_dir = _skill(client, 'getWorkingDir()', 'reading the working directory').strip().strip('"')
    cells = parse_hierarchy(_skill(client, HIERARCHY_SKILL % dict(library=library, testbench=testbench), 'reading the hierarchy'))
    if not cells or cells[0]['cell'] != testbench or cell not in {c['cell'] for c in cells}:
        raise RuntimeError(f'{cell} is not under the testbench {testbench} in {library}')
    unusable = [c['cell'] for c in cells if not set(COPIED_VIEWS) & set(c['views'])]
    with_cdf = [c['cell'] for c in cells if c['has_cdf']]
    if unusable or with_cdf:
        raise RuntimeError('Cannot copy this hierarchy yet: '
                           + '; '.join(filter(None, [unusable and f'no schematic or symbol view: {", ".join(unusable)}',
                                                      with_cdf and f'cells with parameters of their own (CDF) are not copied yet: {", ".join(with_cdf)}'])))
    rename = {c['cell']: (rename or {}).get(c['cell'], c['cell']) for c in cells}       # source cell -> its copy's name
    if copy_library == library and any(src == dst for src, dst in rename.items()):
        raise RuntimeError('A copy inside the same library needs new cell names')
    for dst in rename.values():
        if not NAME.match(dst):
            raise RuntimeError(f'{dst!r} is not a plain Cadence cell name')
    targets = [(rename[c['cell']], view) for c in cells for view in COPIED_VIEWS if view in c['views']]
    before = _originals(client, library, cells)
    existing = set(client.library.list())
    cds_lib = f'{working_dir}/cds.lib'
    if copy_library in existing:
        if not reuse_library:
            raise RuntimeError(f'A library called {copy_library} already exists and was not made by the workbench: nothing was written')
        pairs = ' '.join(f'list("{c}" "{v}")' for c, v in targets)
        present = set(_skill(client, EXISTING_SKILL % dict(pairs=pairs, copy_library=copy_library), 'looking into the copy library').strip().strip('"').split())
        foreign = sorted(present - set(overwrite))
        if foreign:
            raise RuntimeError(f'{copy_library} already holds {", ".join(foreign)} (another copy uses them): nothing was written')
        copy_info = client.library.get(copy_library)
    else:
        if not client.download_file(cds_lib, out / 'cds.lib.before').ok:
            raise RuntimeError(f'Could not back up {cds_lib} before adding a library: nothing was written')
        copy_info = client.library.create(copy_library, f'{working_dir}/{copy_library}', technology_library=info.technology_library)
        note(created_library=True, copy_path=copy_info.path, copy_technology_library=copy_info.technology_library)
        client.download_file(cds_lib, out / 'cds.lib.after')
    source_of = {dst: src for src, dst in rename.items()}
    for name, view in targets:
        _skill(client, COPY_VIEW_SKILL % dict(library=library, cell=source_of[name], dest=name, view=view, copy_library=copy_library,
                                              overwrite='t' if f'{name}/{view}' in overwrite else 'nil'),
               f'copying {source_of[name]}/{view} as {name}')
        note(copied=progress['copied'] + [f'{name}/{view}'])
    pairs = ' '.join(f'list("{src}" "{dst}")' for src, dst in rename.items())
    remastered = {}
    for item in cells:
        if 'schematic' in item['views']:
            answer = _skill(client, REMASTER_SKILL % dict(library=library, dest=rename[item['cell']], copy_library=copy_library, pairs=pairs),
                            f're-pointing {rename[item["cell"]]}').strip().strip('"')
            _, count, checked = answer.split('|', 2)
            remastered[rename[item['cell']]] = dict(headers=int(count), sch_check=checked)
    exported = client.schematic.export_netlist(copy_library, rename[testbench], out / 'package', timeout=180)
    structure = Path(exported['input_file']).parent / 'netlist'
    (out / 'netlist.scs').write_text(structure.read_text())
    after = _originals(client, library, cells)
    return dict(library=library, cell=cell, testbench=testbench, copy_library=copy_library, copy_path=copy_info.path,
                copy_cell=rename[cell], copy_testbench=rename[testbench], rename=rename,
                technology_library=info.technology_library, copy_technology_library=copy_info.technology_library,
                working_dir=working_dir, created_library=progress['created_library'], cds_lib=cds_lib, cells=cells,
                copied=[dict(cell=c, view=v) for c, v in (item.split('/') for item in progress['copied'])],
                remastered=remastered, originals_before=before, originals_after=after)


# ---------------------------------------------------------------------------------- Maestro setup of the copy
def _alist(options):
    return '`(' + ' '.join(f'({_q(k)} {_q(v)})' for k, v in options.items()) + ')'


def _session_open(client, library, testbench, mode='a'):
    raw = _skill(client, f'maeOpenSetup({_q(library)} {_q(testbench)} "maestro" ?mode {_q(mode)})', 'opening the Maestro setup').strip().strip('"')
    if not raw or raw in ('nil', 't'):
        raise RuntimeError(f'maeOpenSetup failed for {library}/{testbench}')
    return raw


def _read_model_files(client, test, s):
    """The test's model files as [[file, section]]; an entry without a section is a one-element list in Virtuoso's
    answer (live 2026-09-22: `(("<ic file>") ("<pdk>" "tt"))`), and its section comes back empty."""
    listed = _skill(client, f'maeGetEnvOption({_q(test)} ?option "modelFiles"{s})', 'reading the model files')
    return [[file, section] for file, section in re.findall(r'\(\s*"([^"]*)"(?:\s+"([^"]*)")?\s*\)', listed or '')]


def _session_close(client, session):
    client.execute_skill(f'maeCloseSession(?session {_q(session)} ?forceClose t)', timeout=60)


def _list(decoded):
    """A decoded SKILL list of strings: ("a" "b") -> ['a', 'b']; nil -> []."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', decoded or '')


def read_maestro(client, library, testbench, *, test):
    """What the copy's Maestro view holds for the workbench's test. A view that does not exist yet answers empty."""
    exists = _skill(client, f'if(ddGetObj({_q(library)} {_q(testbench)} "maestro") "yes" "no")', 'looking for the Maestro view').strip().strip('"') == 'yes'
    answer = dict(exists=exists, tests=[], test=None, model_files=[], analyses={}, variables={}, outputs=[], specs=[], raw_specs={},
                  simulator_mode=None, initial_conditions={}, ic_file=None)
    if not exists:
        return answer
    session = _session_open(client, library, testbench, mode='r')
    s = f' ?session {_q(session)}'
    try:
        answer['tests'] = _list(_skill(client, f'maeGetSetup(?typeName "tests"{s})', 'reading the tests'))
        if test not in answer['tests']:
            return answer
        answer['test'] = test
        answer['simulator_mode'] = _skill(client, f"let((th) th = maeGetTestSession({_q(test)}{s}) if(th asiGetHighPerformanceOptionVal(th 'uniMode) \"\"))",
                                          'reading the simulator mode').strip().strip('"') or None
        listed_files, ic_folders = _read_model_files(client, test, s), _ic_folders()
        answer['model_files'] = [m for m in listed_files if not _is_ic_file(m[0], ic_folders)]
        for path, _section in listed_files:                       # the ic file, if the test carries one
            if _is_ic_file(path, ic_folders):
                answer['ic_file'] = path
                answer['initial_conditions'] = virtuoso_setup.parse_ic_file(_ic_read(client, path))
        for name in _list(_skill(client, f'maeGetEnabledAnalysis({_q(test)}{s})', 'reading the analyses')):
            options = _skill(client, f'maeGetAnalysis({_q(test)} {_q(name)}{s})', f'reading the {name} options')
            answer['analyses'][name] = {k: v for k, v in re.findall(r'\(\s*"([^"]*)"\s+"([^"]*)"\s*\)', options or '')}
        for name in _list(_skill(client, f'maeGetSetup(?typeName "variables"{s})', 'reading the variables')):
            answer['variables'][name] = _skill(client, f'maeGetVar({_q(name)}{s})', f'reading {name}').strip().strip('"')
        listed = _skill(client, f'let((out) out = "" foreach(o maeGetTestOutputs({_q(test)}{s}) out = strcat(out o~>name "\\t" '
                                f'cond((stringp(o~>expression) o~>expression) (o~>expression sprintf(nil "%L" o~>expression)) (t "")) "\\n")) out)',
                                'reading the outputs')
        for line in (listed or '').strip().strip('"').replace('\\n', '\n').replace('\\t', '\t').splitlines():
            name, _, expression = line.partition('\t')
            if name:
                answer['outputs'].append(dict(name=name, expression=expression.replace('\\"', '"')))
        for output in answer['outputs']:
            raw = _skill(client, f'axlGetSpecData(axlGetMainSetupDB({_q(session)}) {_q(output["name"])} {_q(test)})',
                         f'reading the spec on {output["name"]}')
            answer['raw_specs'][output['name']] = raw
            spec = parse_spec(raw)
            if spec:
                answer['specs'].append(dict(output=output['name'], **spec))
    finally:
        _session_close(client, session)
    return answer


def parse_spec(raw):
    """{op, value} from axlGetSpecData's answer, or None. The live IC23.1 answers ("gt" "1e+09") and
    ("range" "0.9" "1.1") (read 2026-09-21); any other kind is kept, marked unsupported."""
    items = _list(raw)
    if not items:
        return None
    op, values = items[0], items[1:]
    if op in ('gt', 'lt') and len(values) == 1:
        return dict(op=op, value=values[0])
    if op == 'range' and len(values) == 2:
        return dict(op=op, value=values)
    return dict(op='unsupported', value=' '.join(items)[:200])


def _remote_path(client, folder, name=None):
    """A folder of the simulator host from the connection module (record 7.168), with `name` below it, as an absolute
    path: `~` is the home of the user Virtuoso runs as, read from Virtuoso."""
    tail = folder[1:] if folder.startswith('~/') else folder
    if name:
        tail = f'{tail}/{name}'
    if not folder.startswith('~/'):
        return tail
    raw = _skill(client, f'strcat(getShellEnvVar("HOME") {_q(tail)})', 'finding the home directory')
    path = (raw or '').strip().strip('"')
    if not path.startswith('/') or not path.endswith(tail) or len(path) == len(tail):
        raise RuntimeError(f'could not build the path {folder}/{name or ""} on the host (got {path!r})')
    return path


def _ic_folders():
    """The folders an initial-condition file of a test can be in: the connection module's "Initial-condition files" and
    its default, where the tests saved before it was changed keep theirs."""
    return {directories.value('simulator_ic'), directories.FIELDS['simulator_ic'].default}


def _is_ic_file(path, folders):
    """A file directly in one of `folders` (a folder under `~` matched by its part below the home)."""
    parent = path.rsplit('/', 1)[0]
    return any(parent == f or f.startswith('~/') and parent.endswith(f[1:]) for f in folders)


def _ic_path(client, library, testbench, test):
    """Where this test's initial-condition file lives on the simulator host: in the "Initial-condition files" folder,
    `~/.gator/ic` by default (the simulator user's home decides)."""
    path = _remote_path(client, directories.value('simulator_ic'), f'{library}__{testbench}__{test}.scs')
    if not path.startswith('/') or not _is_ic_file(path, _ic_folders()):
        raise RuntimeError(f'could not build the initial-conditions path on the host (got {path!r})')
    return path


def _ic_write(client, path, text):
    """Write the ic file (each level of its folder is made first); SKILL writes it, so no file is uploaded."""
    escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    parts = path.split('/')[1:-1]
    levels = ' '.join(f'createDir({_q("/" + "/".join(parts[:k]))})' for k in range(1, len(parts) + 1))
    written = _skill(client, f'let((p) {levels} '
                             f'p = outfile({_q(path)} "w") unless(p error("cannot write %s" {_q(path)})) '
                             f'fprintf(p "%s" "{escaped}") close(p) isFile({_q(path)}))', 'writing the initial conditions')
    if (written or '').strip() not in ('t', '"t"'):
        raise RuntimeError(f'the initial-conditions file was not written ({path})')


def _ic_read(client, path):
    """What the ic file on the host says (empty when it is gone)."""
    raw = _skill(client, f'let((p line all) all = "" p = infile({_q(path)}) if(p progn(while(gets(line p) all = strcat(all line)) close(p)) all) all)',
                 'reading the initial conditions')
    return (raw or '').strip().strip('"').replace('\\n', '\n')


def write_maestro(client, library, testbench, setup):
    """Make the copy's Maestro test say exactly what `setup` says (outputs are removed and added again, so each one
    keeps no stale spec), save, close. Other tests in the view are left alone."""
    test = setup['test']
    session = _session_open(client, library, testbench, mode='a')
    s = f' ?session {_q(session)}'
    try:
        created = test not in _list(_skill(client, f'maeGetSetup(?typeName "tests"{s})', 'reading the tests'))
        if created:
            _skill(client, f'maeCreateTest({_q(test)} ?lib {_q(library)} ?cell {_q(testbench)} ?view "schematic" ?simulator "spectre"{s})',
                   'creating the test')
        # Initial conditions travel as a model file without a section: Maestro's netlist then `include`s the ic file,
        # so its own runs and every run deck built from its netlist start the circuit the same way. None = keep.
        conditions, ic_path, listed, ic_folders = setup.get('initial_conditions'), None, None, _ic_folders()
        if conditions is not None:                            # None = keep them as they are; {} = the test should have none
            listed = _read_model_files(client, test, s)
            if conditions or any(_is_ic_file(file, ic_folders) for file, _section in listed):
                ic_path = _ic_path(client, library, testbench, test)
                if conditions:
                    _ic_write(client, ic_path, virtuoso_setup.ic_file_text(conditions))
                else:
                    _skill(client, f'if(isFile({_q(ic_path)}) deleteFile({_q(ic_path)}) t)', 'removing the initial conditions file')
        wanted = [list(m) for m in setup['model_files'] or []]
        stating = bool(wanted) and (created or not setup.get('keep_model_files'))
        if stating or ic_path:
            if listed is None:                                # conditions kept: the ic file the test has stays registered
                listed = _read_model_files(client, test, s)
            base = wanted if stating else listed
            keep_ic = [m for m in listed if _is_ic_file(m[0], ic_folders)] if conditions is None else []
            entries = [m for m in base if not _is_ic_file(m[0], ic_folders)] + keep_ic + ([[ic_path, '']] if conditions else [])
            files = ' '.join(f'({_q(f)} {_q(section)})' for f, section in entries)
            _skill(client, f'maeSetEnvOption({_q(test)} ?options `(("modelFiles" ({files}))){s})', 'setting the model files')
        for name in _list(_skill(client, f'maeGetEnabledAnalysis({_q(test)}{s})', 'reading the analyses')) if setup['analyses'] is not None else ():
            if name not in setup['analyses']:
                _skill(client, f'maeSetAnalysis({_q(test)} {_q(name)} ?enable nil{s})', f'switching {name} off')
        for name, options in (setup['analyses'] or {}).items():
            _skill(client, f'maeSetAnalysis({_q(test)} {_q(name)} ?enable t' + (f' ?options {_alist(options)}' if options else '') + f'{s})',
                   f'setting the {name} analysis')
        existing = _skill(client, f'let((out) out = "" foreach(o maeGetTestOutputs({_q(test)}{s}) out = strcat(out o~>name "\\n")) out)', 'reading the outputs')
        for name in filter(None, (existing or '').strip().strip('"').replace('\\n', '\n').splitlines()):
            _skill(client, f'maeDeleteOutput({_q(name)} {_q(test)}{s})', f'removing output {name}')
        for output in setup['outputs']:
            _skill(client, f'maeAddOutput({_q(output["name"])} {_q(test)} ?outputType "point" ?expr {_q(output["expression"])}{s})',
                   f'adding output {output["name"]}')
        for spec in setup['specs']:
            value = ('list(' + ' '.join(_q(v) for v in spec['value']) + ')') if isinstance(spec['value'], list) else _q(spec['value'])
            _skill(client, f'maeSetSpec({_q(spec["output"])} {_q(test)} ?{spec["op"]} {value}{s})', f'setting the spec on {spec["output"]}')
        if setup['variables'] is not None:                   # None: the variables stay as they are
            for name in _list(_skill(client, f'maeGetSetup(?typeName "variables"{s})', 'reading the variables')):
                if name not in setup['variables']:
                    _skill(client, f'maeDeleteVar({_q(name)}{s})', f'removing variable {name}')
            for name, value in setup['variables'].items():
                _skill(client, f'maeSetVar({_q(name)} {_q(value)}{s})', f'setting variable {name}')
        # The simulator mode the optimizer's runs use (plain Spectre: the run adapter passes no +aps), so a Maestro run of
        # the copy computes the same numbers (APS takes other time steps; seen live 2026-09-22).
        _skill(client, f"let((th) th = maeGetTestSession({_q(test)}{s}) unless(th error(\"no simulation session for the test\")) "
                       f"asiSetHighPerformanceOptionVal(th 'uniMode {_q(setup.get('simulator_mode') or 'Spectre')}))", 'setting the simulator mode')
        _skill(client, f'maeSaveSetup(?lib {_q(library)} ?cell {_q(testbench)} ?view "maestro"{s})', 'saving the Maestro setup')
    finally:
        _session_close(client, session)


def write_bindings(client, library, bindings, restore):
    """Set instance parameters of the copy to variable names (`bindings`), or back to the value the original has
    (`restore`: [(cell, instance, parameter, value)]). One open/check/save per cell."""
    by_cell = {}
    for b in bindings:
        by_cell.setdefault(b['cell'], []).append((b['instance'], b['parameter'], b['variable']))
    for cell, instance, parameter, value in restore:
        by_cell.setdefault(cell, []).append((instance, parameter, value))
    for cell, items in by_cell.items():
        sets = ' '.join(f'cdfFindParamByName(cdfGetInstCDF(dbFindAnyInstByName(cv {_q(i)})) {_q(p)})~>value = {_q(v)}' for i, p, v in items)
        _skill(client, f'let((cv) cv = dbOpenCellViewByType({_q(library)} {_q(cell)} "schematic" nil "a") '
                       f'unless(cv error("cannot open {library}/{cell} for editing")) {sets} schCheck(cv) dbSave(cv) dbClose(cv) t)',
               f'setting variables on {cell}')


def read_bindings(client, library, cells, variables):
    """Instance parameters of the copied schematics whose value is exactly a design variable's name."""
    if not variables:
        return []
    names = ' '.join(_q(v) for v in variables)
    found = []
    for cell in cells:
        raw = _skill(client, f'let((cv out) out = "" cv = dbOpenCellViewByType({_q(library)} {_q(cell)} "schematic" nil "r") '
                             f'when(cv foreach(inst cv~>instances foreach(p cdfGetInstCDF(inst)~>parameters '
                             f'when(stringp(p~>value) && member(p~>value list({names})) '
                             f'out = strcat(out inst~>name "\\t" p~>name "\\t" p~>value "\\n")))) dbClose(cv)) out)',
                     f'reading the variables set on {cell}')
        for line in (raw or '').strip().strip('"').replace('\\n', '\n').replace('\\t', '\t').splitlines():
            parts = line.split('\t')
            if len(parts) == 3:
                found.append(dict(cell=cell, instance=parts[0], parameter=parts[1], variable=parts[2]))
    return found


def maestro_netlist(client, library, testbench, *, test, out):
    """Maestro's own netlist of one test at the nominal corner (``maeCreateNetlistForCorner``), downloaded into
    `out/maestro_netlist`: the deck every evaluation of a Maestro-measured task runs around the circuit it exports, and
    the name maps (``amap/``) its output expressions are translated with. Maestro writes the netlist files into a
    folder of its own on the simulator host - one per copy's testbench under the connection module's "Maestro netlists",
    `/tmp/gator_maestro_netlist` by default; nothing in the design is written. A read-only session first; an editable
    one only when Maestro refuses to netlist from it."""
    remote = _remote_path(client, directories.value('maestro_netlist'), f'{library}/{testbench}')
    for mode in ('r', 'a'):
        session = _session_open(client, library, testbench, mode=mode)
        try:
            done = client.execute_skill(f'maeCreateNetlistForCorner({_q(test)} "Nominal" {_q(remote)} ?session {_q(session)})', timeout=240)
        finally:
            _session_close(client, session)
        if done.ok and not done.errors and done.output.strip() not in ('nil', ''):
            break
    else:
        raise RuntimeError('Maestro did not netlist the test: ' + ('; '.join(done.errors) or done.output or 'no answer'))
    local = out / 'maestro_netlist'
    client.download_file(remote, local, recursive=True)
    found = sorted(local.rglob('input.scs'))
    if not found or not (found[0].parent / 'netlist').is_file() or not (found[0].parent / 'amap').is_dir():
        raise RuntimeError('Maestro\'s netlist folder lacks input.scs, netlist or amap/')
    return dict(test=test, remote=remote, folder=str(found[0].parent))


def setup_op(client, op, *, library, testbench, cells, setup=None, restore=(), test):
    if op == 'write_setup':
        write_maestro(client, library, testbench, setup)
        write_bindings(client, library, setup['bindings'] or [], restore)      # None: nothing bound or unbound
    answer = read_maestro(client, library, testbench, test=test)
    answer['bindings'] = read_bindings(client, library, cells, list(answer['variables']))
    return answer


def _main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--op', choices=('make_copy', 'read_setup', 'write_setup', 'maestro_netlist'), required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--cell', required=True)
    parser.add_argument('--testbench', required=True)
    parser.add_argument('--copy-library', required=True)
    parser.add_argument('--request', help='JSON file: setup to write, cells, restore list, test name (setup ops)')
    parser.add_argument('--reuse-library', action='store_true')
    parser.add_argument('--overwrite', default='[]', help='JSON list of cell/view a failed earlier attempt wrote')
    parser.add_argument('--rename', default='{}', help='JSON map source cell -> name of its copy (Save as)')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    for value in (args.library, args.cell, args.testbench, args.copy_library):
        if not NAME.match(value):
            raise SystemExit('library and cell names must be plain Cadence names')
    out = Path(args.output)
    lock_path = bridge_session_lock()                          # the run adapter's lock (record 7.167)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A real run or a check is using Virtuoso right now: try again when it has finished')
        settings = resolve_profile_id(args.profile_id)
        bridge = RealBridge(settings)
        bridge.version()
        bridge.bind_env(settings['env_file'])
        client = bridge.client(settings.get('profile') or None, 60)
        try:
            from contextlib import redirect_stderr, redirect_stdout
            with (out / 'bridge.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
                if args.op == 'make_copy':
                    answer = make_copy(client, library=args.library, cell=args.cell, testbench=args.testbench,
                                       copy_library=args.copy_library, reuse_library=args.reuse_library,
                                       overwrite=set(json.loads(args.overwrite)), out=out, rename=json.loads(args.rename))
                elif args.op == 'maestro_netlist':
                    request = json.loads(Path(args.request).read_text())
                    answer = maestro_netlist(client, args.copy_library, args.testbench, test=request['test'], out=out)
                else:
                    request = json.loads(Path(args.request).read_text())
                    answer = setup_op(client, args.op, library=args.copy_library, testbench=args.testbench, cells=request['cells'],
                                      setup=request.get('setup'), restore=[tuple(r) for r in request.get('restore', [])],
                                      test=request['test'])
        finally:
            client.close()
    print(json.dumps(answer, default=str))
    return 0


def run(profile_id, op, *, args, output, timeout=600.0, command=None):
    """Run one write process; returns its JSON answer. The caller has passed the connection gate."""
    argv = (command or [sys.executable, '-m', 'gator_workbench.bridge_setup']) + ['--profile-id', profile_id, '--op', op,
                                                                                 '--output', str(output)] + list(args)
    finished = run_child(argv, timeout)
    if finished is None:
        raise TimeoutError('The Virtuoso write did not finish in time; look at the copy before trying again')
    stdout, stderr, code = finished
    if code != 0:
        raise child_error(stderr, 'the Virtuoso write failed', 600)
    return json.loads(stdout.strip().splitlines()[-1])


if __name__ == '__main__':
    raise SystemExit(_main())
