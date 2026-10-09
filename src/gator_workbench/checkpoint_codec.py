"""A save point's training_state.pt written compressed: every zip entry deflated and proved byte-identical before the
file is used (record 7.284).

Moved from save_point_compression.py by the refactoring (docs/plan-refactoring.md): checkpoints writes every save
point through it, and the one-time pass over older save points (which needs checkpoints) stays in
save_point_compression.py, which re-exports these names.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import zipfile

from .storage.atomic import publish, temporary_path


LEVEL = 3                   # deflate level: 1 gave 15.5 MB in 0.39 s, 3 gave 14.4 MB in 0.43 s, 6 gave 13.9 MB in 0.82 s


def is_deflated(archive) -> bool:
    """Whether every entry of the zip archive (a path or a file object) is deflated: a save point already compressed."""
    with zipfile.ZipFile(archive) as opened:
        entries = opened.infolist()
    return bool(entries) and all(e.compress_type == zipfile.ZIP_DEFLATED for e in entries)


def deflate(data: bytes, target) -> dict:
    """Write the torch archive `data` (its bytes) to the new file `target`, every entry deflated, and prove it lossless:
    the same entry names in the same order, each entry's size, CRC and bytes equal to the original's, and the file on
    disk holding exactly the archive checked. Returns {bytes, sha256} of `target`; raises ValueError, leaving no
    `target`, when anything differs. The archive is built in memory and written in one piece: written entry by entry
    (a save point has ~1,500), the 9p-mounted D: drive took 3-5 s more per save point."""
    target = Path(target)
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, 'w') as written:
        for entry in source.infolist():
            copy = zipfile.ZipInfo(entry.filename, date_time=entry.date_time)
            copy.compress_type, copy.external_attr = zipfile.ZIP_DEFLATED, entry.external_attr
            written.writestr(copy, source.read(entry), compresslevel=LEVEL)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(io.BytesIO(archive)) as written:
        before, after = source.infolist(), written.infolist()
        if [e.filename for e in before] != [e.filename for e in after]:
            raise ValueError('the compressed archive does not hold the same entries in the same order')
        for old, new in zip(before, after):
            if (old.file_size, old.CRC) != (new.file_size, new.CRC) or source.read(old) != written.read(new):
                raise ValueError(f'entry {old.filename} differs after compression')
    try:
        with target.open('xb') as stream:
            stream.write(archive)
        if target.read_bytes() != archive:
            raise ValueError(f'{target} does not hold the compressed archive as written')
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return dict(bytes=len(archive), sha256=hashlib.sha256(archive).hexdigest())


def write_compressed(source, destination) -> dict:
    """A save point's training_state.pt, written by the package at `source` (a local temporary file), published
    compressed at `destination`. Returns {bytes, sha256} of `destination`."""
    temporary = temporary_path(Path(destination))
    result = deflate(Path(source).read_bytes(), temporary)
    publish(temporary, Path(destination))
    return result
