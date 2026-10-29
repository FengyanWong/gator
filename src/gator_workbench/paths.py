"""Output roots: allowlist, real writability test, free space, verified Windows mapping.

* The browser may only choose directories inside roots the BACKEND operator allowed
  (repository ``outputs/`` plus roots given on the command line / environment). No API
  request, imported file or agent proposal can add a root.
* A Windows path is reported only after a token written through Linux was read back
  through Windows. ``wslpath`` alone is a translation, not a verification.
* Mock (synthetic) data lives under a separate ``mock/`` root and real tasks cannot
  write there, nor mock tasks outside it.
"""
from __future__ import annotations

import functools
from heapq import nsmallest
import os
from pathlib import Path
import shutil
import socket
import subprocess
from uuid import uuid4

from .storage.atomic import TEMP_MARKER, JsonlAppender, fsync_directory

MOCK_SUBDIR = 'mock'
ENV_ALLOWED_ROOTS = 'GATOR_WORKBENCH_ALLOWED_ROOTS'


class PathNotAllowed(PermissionError):
    """A requested output path is outside the allowed roots or violates their path rules."""
    pass


def refuse_nul(path) -> None:
    """A NUL byte is no path at all: the OS refuses it with ValueError, which surfaced as HTTP 500 on every route that
    takes a path (review of 2026-09-29). It is refused like any other path that is not allowed."""
    if '\x00' in str(path):
        raise PathNotAllowed('A path cannot contain a NUL character')


@functools.lru_cache(maxsize=1)
def repo_root() -> Path:
    """Repository that contains this package (src/gator_workbench/..). Resolved once: on the 9p-mounted D: drive a
    resolve looks up every part of the path, and reading the task list called it 38 times (review of 2026-10-01)."""
    return Path(__file__).resolve().parents[2]


ENV_DEFAULT_OUTPUT_ROOT = 'GATOR_WORKBENCH_DEFAULT_OUTPUT_ROOT'


def default_output_root() -> Path:
    """The repository's outputs/. GATOR_WORKBENCH_DEFAULT_OUTPUT_ROOT names another folder: the browser checks' scratch
    backends (run_checks.sh) must not list the user's runs - the page takes over a live one it finds (record 7.276)."""
    given = os.environ.get(ENV_DEFAULT_OUTPUT_ROOT)
    return Path(given) if given else repo_root() / 'outputs'


ENV_SETTINGS_DIR = 'GATOR_WORKBENCH_SETTINGS_DIR'


def local_settings_dir() -> Path:
    """Remembered settings, connection profiles and application logs. configs/local/ is already
    git-ignored. The environment override is the ONE switch that also reaches child processes (run
    workers, connection probes), so tests can never write into a user's real settings."""
    override = os.environ.get(ENV_SETTINGS_DIR)
    if override:
        return Path(override)
    return repo_root() / 'configs' / 'local' / 'workbench'


def inside(path, roots) -> bool:
    """`path` is one of `roots` or lies under one of them (all resolved already)."""
    return any(path == root or root in path.parents for root in roots)


# in the adapter's state root: a folder per further session, a lock per cell
SESSIONS_DIR, CELLS_DIR = 'sessions', 'cells'


def _plain(name) -> str:
    """A name as a file name: letters, digits, `_`, `-` and `.` kept, anything else `_`."""
    import re
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(name)).lstrip('.') or '_'


def bridge_session_key(env_file: str | os.PathLike[str], profile) -> str | None:
    """Which Virtuoso session a connection reaches when it is NOT the first one (record 7.311), else None.

    A connection names the bridge's settings file and, in it, a bridge profile: the keys `VB_REMOTE_HOST_<profile>` and
    `VB_REMOTE_PORT_<profile>` say where that session's daemon listens; the keys without a suffix are the first session,
    the one every connection reached until a second Virtuoso was opened. The answer is the name of the first profile, in
    alphabetical order, whose keys name the same host and port - two profiles that reach one daemon are one session.
    Whatever cannot be told apart from the first session IS the first session: no profile, a file that cannot be read, a
    missing host or port on either side, or the first session's own host and port."""
    if not profile:
        return None
    values = {}
    try:
        for line in Path(env_file).read_text(encoding='utf-8', errors='replace').splitlines():
            key, found, value = line.strip().removeprefix('export ').partition('=')
            if found and not key.startswith('#'):
                values[key.strip()] = value.split(' #')[0].strip().strip('"\'')
    except OSError:
        return None

    def target(suffix):
        host, port = values.get('VB_REMOTE_HOST' + suffix), values.get('VB_REMOTE_PORT' + suffix)
        return (host, port) if host and port else None
    mine, first = target(f'_{profile}'), target('')
    if mine is None or first is None or mine == first:
        return None
    names = [key[len('VB_REMOTE_HOST_'):] for key in values if key.startswith('VB_REMOTE_HOST_')]
    return _plain(min(name for name in names if target(f'_{name}') == mine))


def bridge_session_dir(env_file: str | os.PathLike[str] | None=None, profile=None,
    root: str | os.PathLike[str] | None=None) -> Path:
    """The adapter's state folder of ONE Virtuoso session (record 7.311): its session lock and a folder per adapter
    session with the crash journal of each write. The first session keeps the state root itself, as before; a further
    session (`bridge_session_key`) has `sessions/<name>` in it. One process at a time drives a Virtuoso session, and with
    a lock each, two sessions carry a run each. `root`: the state root when the caller holds it (`bridge_state_dir`
    reads the connection file)."""
    key = bridge_session_key(env_file, profile) if env_file is not None else None
    root = Path(root) if root is not None else bridge_state_dir()
    return root if key is None else root / SESSIONS_DIR / key


def bridge_session_lock(env_file: str | os.PathLike[str] | None=None, profile=None,
    root: str | os.PathLike[str] | None=None) -> Path:
    """The run adapter's session lock (record 7.167): every process that works in a Virtuoso session takes it - a run, a
    corner check, Save task. Without arguments the first session's; with a connection's settings file and bridge profile,
    the lock of the session that connection reaches (record 7.311)."""
    return bridge_session_dir(env_file, profile, root) / 'session.lock'


def bridge_queue_lock(env_file: str | os.PathLike[str] | None=None, profile=None,
    root: str | os.PathLike[str] | None=None) -> Path:
    """The lock a queue holds for its whole life in the Virtuoso session it works in (record 7.351), beside the session
    lock: between two of its runs the session lock is free for a moment, and the page, which sends its work to whichever
    session is free (`session_routing`), must not take the session then - the queue's next run would find it taken."""
    return bridge_session_dir(env_file, profile, root) / 'queue.lock'


def bridge_cell_lock(library, cell, root: str | os.PathLike[str] | None=None) -> Path:
    """The lock of one cell (record 7.311): whoever works on a cell holds it beside its session's lock, so that two
    Virtuoso sessions never work on the same cell - each has its own copy of an open cell in memory, and the second to
    save would write over the first. In `cells/` of the adapter's state root (`root`: that root when the caller holds it,
    as the adapter does)."""
    return (Path(root) if root is not None else bridge_state_dir()) / CELLS_DIR / _plain(
        library) / f'{_plain(cell)}.lock'


def bridge_state_root_of(state_dir: str | os.PathLike[str]) -> Path:
    """The adapter's state root, from the state folder of one session (`bridge_session_dir`)."""
    state_dir = Path(state_dir)
    return state_dir.parent.parent if state_dir.parent.name == SESSIONS_DIR else state_dir


def bridge_locks(root: str | os.PathLike[str] | None=None) -> list:
    """Every lock file there is in an adapter state root: the first session's, the further sessions', the cells'."""
    root = Path(root) if root is not None else bridge_state_dir()
    return [p for p in (root / 'session.lock', *sorted(root.glob(f'{SESSIONS_DIR}/*/session.lock')),
                        *sorted(root.glob(f'{CELLS_DIR}/*/*.lock'))) if p.is_file()]


def bridge_state_dir() -> Path:
    """The run adapter's state root: its session lock (`session.lock`, taken by every process that works on the Virtuoso
    cell, so that two never do at once) and a folder per session with the crash journal of each write (record 7.167).
    Since record 7.311 also `sessions/<name>` - the same two things for each further Virtuoso session - and `cells/`, a
    lock per cell (`bridge_session_dir`, `bridge_cell_lock`).
    On the WSL disk by default, kept across restarts (`/tmp` is not): under artifacts/ on D:, a 9p mount, a candidate's
    two journal writes took 16 ms, there 1.3 ms. The folder "Adapter state" of the connection module since record 7.168
    (`directories`); GATOR_BRIDGE_STATE_DIR overrides it (the tests). Every GATOR process must name the same folder: one
    started with other settings (GATOR_WORKBENCH_SETTINGS_DIR) reads its own connection file, so it needs the same value
    there or the variable. Sessions before record 7.167 stay in artifacts/local/bridge-state."""
    # lazy: directories imports this module
    from .directories import local_path
    return local_path('adapter_state')


def bridge_env_snapshot(env_file: str | os.PathLike[str]) -> Path:
    """A private copy of the bridge's settings file that never changes, for one run to bind (record 7.306).

    The run adapter binds the settings FILE when it attaches and checks it at every call, so that a run cannot go on
    against a link somebody re-pointed: any later change of the file ends the run in the middle of a write ("Bridge
    configuration changed during an active worker") and leaves its cell half-written. On 2026-10-10 another session
    added the keys of a second Virtuoso session to the shared file and a run of a queue ended that way. A run now binds
    a copy named by the file's own checksum, in the adapter's state folder: the settings it started with stay what
    they were whatever is written to the shared file, a run started afterwards takes the file as it is then, and the
    adapter's check is as strict as before on the copy it holds. The file may hold a secret: the copies sit in a folder
    of the adapter's state root that only its owner may enter, each readable by its owner only, and a copy older than
    30 days is removed when a new one is written. A settings file that cannot be read is returned as it was named (the
    attach then fails in its own words, as before)."""
    import hashlib
    import re
    import time
    source = Path(env_file).resolve()
    try:
        data = source.read_bytes()
    except OSError:
        return source
    folder = bridge_state_dir() / 'env-snapshots'
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    target = folder / f'{hashlib.sha256(data).hexdigest()}.env'
    try:
        same = target.read_bytes() == data
    except OSError:
        same = False
    if not same:
        temporary = folder / f'{TEMP_MARKER}{uuid4().hex}'
        temporary.write_bytes(data)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        # copies no run can still hold: a month old, another settings file
        for other in folder.iterdir():
            if other != target and re.fullmatch(r'[0-9a-f]{64}\.env',
                other.name) and time.time() - other.stat().st_mtime > 30 * 86400:
                other.unlink(missing_ok=True)
    return target.resolve()


def append_local_log(name, record) -> None:
    """One line of an application log in the settings folder: `record()`, built once the file is open. A log that
    cannot be written is skipped - it never fails what it records."""
    try:
        log = JsonlAppender(local_settings_dir() / name)
        log.append(record())
        log.close()
    except OSError:
        pass


class OutputRoots:
    """The allowlist of output roots, used to resolve, list and check output directories."""
    def __init__(self, extra_roots=(), *, include_default: bool=True) -> None:
        roots = [default_output_root()] if include_default else []
        roots += [Path(p) for p in extra_roots]
        roots += [Path(p) for p in os.environ.get(ENV_ALLOWED_ROOTS, '').split(os.pathsep) if p]
        self.roots = []
        for root in roots:
            resolved = root.expanduser().resolve()
            if resolved not in self.roots:
                self.roots.append(resolved)
        self._mapping_cache: dict[str, dict] = {}

    # ---------------------------------------------------------------- allowlist
    def resolve(self, path: str | os.PathLike[str]) -> Path:
        """Resolve symlinks/.. and require the result to be inside an allowed root."""
        refuse_nul(path)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise PathNotAllowed('An absolute backend path is required')
        resolved = candidate.resolve()
        if inside(resolved, self.roots):
            return resolved
        raise PathNotAllowed(f'{resolved} is outside the allowed output roots: '
                             + ', '.join(str(r) for r in self.roots)
                             + f'. Roots can only be added by the backend operator (--allow-root or '
                               f'{ENV_ALLOWED_ROOTS}).')

    def is_allowed(self, path: str | os.PathLike[str]) -> bool:
        """Check whether path resolution succeeds within the configured output roots."""
        try:
            self.resolve(path)
            return True
        except (PathNotAllowed, OSError):
            return False

    def browse(self, path: str | os.PathLike[str] | None=None) -> dict:
        """Restricted directory listing for the output-root picker (directories only)."""
        if path is None:
            return dict(path=None, parent=None,
                        entries=[dict(name=str(r), path=str(r), exists=r.exists()) for r in self.roots])
        current = self.resolve(path)
        entries = []
        if current.is_dir():
            with os.scandir(current) as children:
                names = nsmallest(500, (child.name for child in children
                                       if child.is_dir() and not child.is_symlink() and not child.name.startswith('.')),
                                  key=Path)  # preserve native Path ordering, including Windows case folding
            entries = [dict(name=name, path=str(current / name), exists=True) for name in names]
        parent = str(current.parent) if self.is_allowed(current.parent) else None
        return dict(path=str(current), parent=parent, entries=entries)

    # ---------------------------------------------------------------- checks
    def check(self, path: str | os.PathLike[str], *, create: bool=False, verify_windows: bool=True) -> dict:
        """Writability is TESTED by creating, fsyncing, reading and removing a probe file."""
        result = dict(requested=str(path), allowed=False, exists=False, writable=False, error=None,
                      resolved=None, free_bytes=None, total_bytes=None, filesystem=None,
                      host=socket.gethostname(), environment=environment_label(),
                      windows_path=None, windows_mapping='not_checked')
        try:
            resolved = self.resolve(path)
        except (PathNotAllowed, OSError) as exc:
            result['error'] = str(exc)
            return result
        result.update(allowed=True, resolved=str(resolved))
        try:
            if create:
                resolved.mkdir(parents=True, exist_ok=True)
            result['exists'] = resolved.is_dir()
            probe_dir = resolved if resolved.is_dir() else _existing_parent(resolved)
            usage = shutil.disk_usage(probe_dir)
            result.update(free_bytes=usage.free, total_bytes=usage.total, filesystem=filesystem_type(probe_dir))
            if resolved.is_dir():
                token = uuid4().hex
                probe = resolved / f'.writable{TEMP_MARKER}{token}'
                with probe.open('x') as stream:
                    stream.write(token)
                    stream.flush()
                    os.fsync(stream.fileno())
                fsync_directory(resolved)
                ok = probe.read_text() == token
                if verify_windows:
                    result.update(self._windows_mapping(resolved, probe, token))
                probe.unlink()
                result['writable'] = ok
            else:
                result['error'] = 'Directory does not exist yet (it is created when a run starts)'
                result['writable'] = os.access(probe_dir, os.W_OK)   # parent only; stated as such
                result['writable_basis'] = 'parent_directory_permission_only'
        except OSError as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
        return result

    def _windows_mapping(self, directory: Path, probe: Path, token: str) -> dict:
        key = str(directory)
        if key in self._mapping_cache:
            return self._mapping_cache[key]
        outcome = dict(windows_path=None, windows_mapping='unavailable')
        wslpath, cmd = shutil.which('wslpath'), shutil.which('cmd.exe')
        if not wslpath or not cmd:
            outcome['windows_mapping'] = 'unavailable_no_wsl_interop'
        else:
            try:
                translated = subprocess.run([wslpath, '-w', str(directory)], capture_output=True, text=True,
                                            timeout=10, check=True).stdout.strip()
                probe_windows = subprocess.run([wslpath, '-w', str(probe)], capture_output=True, text=True,
                                               timeout=10, check=True).stdout.strip()
                seen = subprocess.run([cmd, '/d', '/c', 'type', probe_windows], capture_output=True, text=True,
                                      timeout=20, cwd='/mnt/c' if Path('/mnt/c').is_dir() else None)
                if seen.returncode == 0 and seen.stdout.strip() == token:
                    outcome = dict(windows_path=translated, windows_mapping='verified_by_readback')
                else:
                    outcome['windows_mapping'] = 'translation_not_verified'
            except (OSError, subprocess.SubprocessError) as exc:
                outcome['windows_mapping'] = f'verification_failed: {type(exc).__name__}'
        if outcome['windows_mapping'] == 'verified_by_readback':
            self._mapping_cache[key] = outcome
        return outcome

    # ---------------------------------------------------------------- mock isolation
    def data_root(self, output_root: str | os.PathLike[str], *, mock: bool) -> Path:
        """Return the resolved output root, or its mock/ folder when `mock`; refuse a root within mock/."""
        root = self.resolve(output_root)
        if MOCK_SUBDIR in root.parts[len(self._owning_root(root).parts):]:
            raise PathNotAllowed(f'Select the output root itself, not its {MOCK_SUBDIR}/ directory')
        return root / MOCK_SUBDIR if mock else root

    def _owning_root(self, resolved: Path) -> Path:
        return next(r for r in self.roots if resolved == r or r in resolved.parents)


def is_mock_path(path: str | os.PathLike[str]) -> bool:
    """Check whether a path contains the reserved synthetic-data directory component."""
    return MOCK_SUBDIR in Path(path).parts


def _existing_parent(path: Path) -> Path:
    while not path.exists():
        path = path.parent
    return path


def filesystem_type(path: str | os.PathLike[str]) -> str:
    """Identify the filesystem of the deepest matching Linux mount, or return unknown."""
    path = Path(path).resolve()
    best = (-1, 'unknown')
    try:
        for row in Path('/proc/mounts').read_text().splitlines():
            parts = row.split()
            mount = Path(parts[1].replace('\\040', ' '))
            if path == mount or mount in path.parents:
                best = max(best, (len(mount.parts), parts[2]))
    except OSError:
        pass
    return best[1]


def environment_label() -> str:
    """Describe the Linux or WSL kernel from its release string when available."""
    try:
        release = Path('/proc/sys/kernel/osrelease').read_text().strip()
    except OSError:
        return 'unknown'
    return f'WSL2 ({release})' if 'microsoft' in release.lower() else f'Linux ({release})'


def directory_bytes(path: str | os.PathLike[str]) -> int:
    """Bytes of the regular files under `path`; symlinks are neither counted nor followed, an unreadable folder counts
    nothing. One os.scandir pass and one stat per file: rglob + is_file + is_symlink + stat listed every folder twice
    and took 4.4 s for the 406 files of the D: output folder, on every page open (review of 2026-09-29)."""
    total = 0
    path = Path(path)
    if not path.is_dir():
        return 0
    pending = [path]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except PermissionError:          # as rglob did: a folder that cannot be listed is skipped
            pass
    return total


def safe_child(base: Path, relative: str) -> Path:
    """Resolve `relative` under `base`, refusing traversal and symlink escapes (file downloads)."""
    refuse_nul(relative)
    base = Path(base).resolve()
    target = (base / relative).resolve()
    if target != base and base not in target.parents:
        raise PathNotAllowed('Path escapes the run directory')
    return target


# ---------------------------------------------------------------------------- profiles
def connection_file() -> Path:
    return local_settings_dir() / 'bridge_connection.json'
