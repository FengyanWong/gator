"""Reading a PDK out of Virtuoso: the SKILL programs that list a library's components with their CDF and its ideal parts,
the model files fetched from the simulator host (kept per host while unchanged, record 7.279/7.283), and the finished
record saved.

Moved from pdk.py by the refactoring (docs/plan-refactoring.md); pdk.py re-exports every name.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import shutil
import tempfile
from pathlib import Path

from .cdf_text import parse_cdf_text
from .model_scan import includes_of, scan_model_text
from .paths import local_settings_dir
from .pdk_record import (IDEAL_LIBRARY, MAX_MODEL_BYTES, MAX_MODEL_FILES, NAME, PdkError, REMOTE_PATH,
                         ideal_parts_of, build_record, load_record, save_record)
from .security import redact
from .storage.atomic import read_json, write_json


# ------------------------------------------------------------------------------------------ the Virtuoso query
# One read-only call. `ddGetObj`, `cdfGetBaseCellCDF` and `cdfFindParamByName` open nothing. A cell that has no Spectre
# entry of its own is netlisted through its schematic: that schematic is opened READ-ONLY and closed again exactly as
# the bridge's own reader does (virtuoso_bridge/virtuoso/schematic/reader.py, unwindProtect + dbClose), only to see which
# primitive it places and with which model. Lines are collected in a list and joined once.
PDK_SKILL = r'''
let((lib lines cdf sp mp cv)
  lib = ddGetObj("@LIBRARY@")
  lines = nil
  when(lib
    foreach(cell lib~>cells
      cdf = cdfGetBaseCellCDF(cell)
      if(null(cdf) then
        lines = cons(sprintf(nil "NOCDF|%s|%L" cell~>name cell~>views~>name) lines)
      else
        sp = get(cdf~>simInfo 'spectre)
        mp = cdfFindParamByName(cdf "model")
        lines = cons(sprintf(nil "CELL|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cell~>name
          if(mp mp~>defValue nil) get(sp 'termOrder) get(sp 'termMapping) get(sp 'instParameters)
          get(sp 'otherParameters) get(sp 'propMapping) get(sp 'componentName) get(sp 'namePrefix)
          cell~>views~>name) lines)
        lines = cons(sprintf(nil "FORM|%s|%L|%L" cell~>name cdf~>formInitProc cdf~>doneProc) lines)
        foreach(p cdf~>parameters
          lines = cons(sprintf(nil "PARAM|%s|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cell~>name p~>name p~>paramType p~>units p~>defValue
            p~>prompt p~>editable p~>display p~>callback p~>choices p~>range) lines))
        when(and(null(sp) member("schematic" cell~>views~>name))
          cv = nil
          unwindProtect(
            progn(
              cv = dbOpenCellViewByType(lib~>name cell~>name "schematic" "schematic" "r")
              when(cv
                foreach(inst cv~>instances
                  lines = cons(sprintf(nil "LEAF|%s|%s|%s|%s|%L" cell~>name inst~>name inst~>libName inst~>cellName
                    dbGetq(inst model)) lines))))
            progn(when(cv dbClose(cv) cv = nil)))))))
  buildString(reverse(lines) "\n"))
'''


def pdk_skill(library):
    if not NAME.match(library or ''):
        raise ValueError('The technology library must be a plain Cadence name')
    return PDK_SKILL.replace('@LIBRARY@', library)


# The CELL / NOCDF lines of PDK_SKILL and nothing else: no parameter, no form, no schematic opened. One line per cell
# (180 in IC23.1's analogLib, 0.1 MB, about a second).
IDEAL_SKILL = r'''
let((lib lines cdf sp mp)
  lib = ddGetObj("@LIBRARY@")
  lines = nil
  when(lib
    foreach(cell lib~>cells
      cdf = cdfGetBaseCellCDF(cell)
      if(null(cdf) then
        lines = cons(sprintf(nil "NOCDF|%s|%L" cell~>name cell~>views~>name) lines)
      else
        sp = get(cdf~>simInfo 'spectre)
        mp = cdfFindParamByName(cdf "model")
        lines = cons(sprintf(nil "CELL|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cell~>name
          if(mp mp~>defValue nil) get(sp 'termOrder) get(sp 'termMapping) get(sp 'instParameters)
          get(sp 'otherParameters) get(sp 'propMapping) get(sp 'componentName) get(sp 'namePrefix)
          cell~>views~>name) lines))))
  buildString(reverse(lines) "\n"))
'''


def ideal_skill(library=IDEAL_LIBRARY):
    if not NAME.match(library or ''):
        raise ValueError('The library of ideal parts must be a plain Cadence name')
    return IDEAL_SKILL.replace('@LIBRARY@', library)


# ------------------------------------------------------------------------------------------ reading (reader process)
# The model files of a PDK, kept by the reader between reads (record 7.279): every cell read and every Save task read
# the PDK again, nine downloads and 5.3 MB for GPDK045, 2.5-5 s, for files that do not change. A file is taken from the
# copy only when the simulator host reports the size and modification time recorded when it was downloaded AND the copy
# still has the SHA-256 recorded for it; whatever cannot be told for sure is downloaded, as before. The time is asked
# before a download: a file that changes during one is fetched again next time. Outside the PDK store (pdks/).
STAMP_SKILL = r'''
let((lines)
  lines = nil
  foreach(p list(@PATHS@)
    lines = cons(if(isFile(p) then sprintf(nil "%s|%L|%L" p fileLength(p) fileTimeModified(p)) else sprintf(nil "%s|missing" p))
      lines))
  buildString(reverse(lines) "\n"))
'''


def remote_stamps(client, decode, paths) -> dict:
    """{path: (bytes, modified)} of these model files on the simulator host, in one read-only query; a file not there,
    or not told plainly, is left out. {} when the query fails: then everything is downloaded."""
    paths = [p for p in paths if REMOTE_PATH.match(p or '') and '/../' not in p]
    if not paths:
        return {}
    try:
        result = client.execute_skill(STAMP_SKILL.replace('@PATHS@', ' '.join(f'"{p}"' for p in paths)), timeout=30)
        text = decode(result.output) if result.ok else ''
    except Exception:
        return {}
    stamps = {}
    for line in (text or '').splitlines():
        path, _, rest = line.partition('|')
        size, _, modified = rest.partition('|')
        if path in paths and size.isdigit() and modified.isdigit():
            stamps[path] = (int(size), modified)
    return stamps


class ModelFileCache:
    """The reader's copies of one technology library's model files: `index.json` {remote path: bytes, modified, sha256}
    and the files themselves, named by their SHA-256. `host`: whose files they are (record 7.283; Astra's review of
    7.279: the stamps - size and modification time - of the same path on two hosts can agree while the files differ, and
    the second host was served the first one's copy). The copies of each host live in a folder of their own."""

    def __init__(self, technology_library, host=None):
        base = local_settings_dir() / 'pdk-model-files'
        self.folder = (base / host_folder_name(host) if host else base) / technology_library
        index = read_json(self.folder / 'index.json', default={})
        self.index = index if isinstance(index, dict) else {}

    def paths(self):
        return list(self.index)

    def get(self, remote, stamp):
        """The kept bytes of `remote`, or None: not kept, another stamp on the host now, or a copy that changed."""
        known = self.index.get(remote)
        if not stamp or not isinstance(known, dict) or (known.get('bytes'), known.get('modified')) != stamp:
            return None
        try:
            data = (self.folder / str(known.get('sha256'))).read_bytes()
        except OSError:
            return None
        return data if len(data) == stamp[0] and hashlib.sha256(data).hexdigest() == known.get('sha256') else None

    def put(self, remote, stamp, data):
        """Keep a download under the stamp asked for before it - only when its size is that stamp's."""
        if not stamp or len(data) != stamp[0]:
            return
        digest = hashlib.sha256(data).hexdigest()
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if not (self.folder / digest).is_file():
                tmp = self.folder / f'{digest}.part'
                tmp.write_bytes(data)
                tmp.replace(self.folder / digest)
            self.index[remote] = dict(bytes=stamp[0], modified=stamp[1], sha256=digest)
            write_json(self.folder / 'index.json', self.index)
        except OSError:
            pass                                        # a copy not kept is only a download next time


def host_folder_name(host) -> str:
    """A folder name for a host identity such as ``user@host`` or ``user@host:port``: its letters, digits, ``@``, ``.``,
    ``-`` and ``_`` kept, anything else ``_``, at most 80 characters."""
    return re.sub(r'[^A-Za-z0-9@._-]+', '_', str(host))[:80] or 'host'


def read_from_virtuoso(client, *, technology_library, model_file, decode=None, cache_host=None):
    """Runs in the bridge reader process. Returns the raw material for `finish_load`. The model files go to a temporary
    folder outside the repository and are deleted before this returns; a copy of each is kept for the next read
    (ModelFileCache, record 7.279), and an unchanged file is taken from it instead of downloaded. `cache_host`: the
    identity of the host the files come from (``user@host``), under which the copies are kept (record 7.283).
    `decode`: the bridge's ``decode_skill_output`` (injectable for tests without the bridge)."""
    if decode is None:
        from virtuoso_bridge import decode_skill_output as decode
    result = client.execute_skill(pdk_skill(technology_library), timeout=180)
    if not result.ok:
        raise RuntimeError('; '.join(result.errors) or 'reading the PDK description failed')
    cdf_text = decode(result.output)
    ideal = read_ideal_parts(client, decode)
    if not REMOTE_PATH.match(model_file or '') or '/../' in model_file:
        raise ValueError('The model file must be an absolute path on the simulator host')
    scratch = Path(tempfile.mkdtemp(prefix='gator-pdk-'))
    cache = ModelFileCache(technology_library, cache_host)
    try:
        # Breadth first, as before; each level's files new to this read are stamped in one query before any download.
        files, sources, total = {}, [], 0
        stamps = remote_stamps(client, decode, [model_file, *cache.paths()])
        stamping = model_file in stamps                 # a query that failed is not asked again in this read
        level = [model_file]
        while level:
            unstamped = [p for p in level if p not in stamps and p not in files]
            if unstamped and stamping:
                stamps.update(remote_stamps(client, decode, unstamped))
            following = []
            for remote in level:
                if remote in files:
                    continue
                if len(files) >= MAX_MODEL_FILES:
                    raise RuntimeError(f'More than {MAX_MODEL_FILES} model files are included; not read further')
                data = cache.get(remote, stamps.get(remote))
                if data is None:
                    local = scratch / f'{len(files):03d}_{Path(remote).name}'
                    fetched = client.download_file(remote, local, timeout=300)
                    if not fetched.ok or not local.is_file():
                        raise RuntimeError(f"Cannot read {remote} on the simulator host: {'; '.join(fetched.errors or []) or 'download failed'}")
                    data = local.read_bytes()
                    cache.put(remote, stamps.get(remote), data)
                total += len(data)
                if total > MAX_MODEL_BYTES:
                    raise RuntimeError('The model files are larger than the reader accepts')
                text = data.decode('utf-8', errors='replace')
                files[remote] = text
                sources.append(dict(path=remote, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
                for include in includes_of(text):
                    target = posixpath.normpath(include if include.startswith('/') else posixpath.join(posixpath.dirname(remote), include))
                    if REMOTE_PATH.match(target) and target not in files and target not in level and target not in following:
                        following.append(target)
            level = following
        scans = [scan_model_text(text, remote) for remote, text in files.items()]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return dict(technology_library=technology_library, cdf_text=cdf_text, scans=scans, ideal=ideal,
                sources=dict(model_files=sources, cdf=dict(library=technology_library, lines=len(cdf_text.splitlines()))))


def read_ideal_parts(client, decode, library=IDEAL_LIBRARY) -> dict:
    """Runs in the bridge reader process, with the PDK: the generic library's description in one read-only query.
    Whatever goes wrong is returned as the reason - the PDK itself is read and stored all the same."""
    try:
        result = client.execute_skill(ideal_skill(library), timeout=120)
        if not result.ok:
            return dict(library=library, error=redact('; '.join(map(str, result.errors)) or 'the query failed', 400))
        text = decode(result.output)
        return dict(library=library, cdf_text=text) if (text or '').strip() else dict(
            library=library, error=f'Virtuoso knows no library called {library}, or it holds no cell')
    except Exception as exc:
        return dict(library=library, error=redact(f'{type(exc).__name__}: {exc}', 400))


def finish_load(raw) -> dict:
    """Runs in the backend: parse, build, store. Refuses a PDK in which nothing could be recognized."""
    library = raw['technology_library']
    cdf = parse_cdf_text(raw['cdf_text'])
    if not cdf['cells']:
        raise PdkError(f'{library} has no cell with a component description (CDF). Is it the technology library?')
    record = build_record(library, cdf, raw['scans'], sources=raw.get('sources'), technology_library=library)
    if not record['devices']:
        raise PdkError(f'No cell of {library} names a Spectre model that the model files define.')
    record['ideal_parts'] = ideal_parts_of(raw.get('ideal'), load_record(library))
    return save_record(record)
