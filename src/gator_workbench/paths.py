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


def default_output_root() -> Path:
    return repo_root() / 'outputs'


ENV_SETTINGS_DIR = 'GATOR_WORKBENCH_SETTINGS_DIR'


def local_settings_dir() -> Path:
    """Remembered settings, connection profiles and application logs. configs/local/ is already
    git-ignored. The environment override is the ONE switch that also reaches child processes (run
    workers, connection probes), so tests can never write into a user's real settings."""
    override = os.environ.get(ENV_SETTINGS_DIR)
    if override:
        return Path(override)
    return repo_root() / 'configs' / 'local' / 'workbench'


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
    def __init__(self, extra_roots=(), *, include_default=True):
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
    def resolve(self, path) -> Path:
        """Resolve symlinks/.. and require the result to be inside an allowed root."""
        refuse_nul(path)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise PathNotAllowed('An absolute backend path is required')
        resolved = candidate.resolve()
        for root in self.roots:
            if resolved == root or root in resolved.parents:
                return resolved
        raise PathNotAllowed(f'{resolved} is outside the allowed output roots: '
                             + ', '.join(str(r) for r in self.roots)
                             + f'. Roots can only be added by the backend operator (--allow-root or '
                               f'{ENV_ALLOWED_ROOTS}).')

    def is_allowed(self, path) -> bool:
        try:
            self.resolve(path)
            return True
        except (PathNotAllowed, OSError):
            return False

    def browse(self, path=None):
        """Restricted directory listing for the output-root picker (directories only)."""
        if path is None:
            return dict(path=None, parent=None,
                        entries=[dict(name=str(r), path=str(r), exists=r.exists()) for r in self.roots])
        current = self.resolve(path)
        entries = []
        if current.is_dir():
            for child in sorted(current.iterdir()):
                if child.is_dir() and not child.is_symlink() and not child.name.startswith('.'):
                    entries.append(dict(name=child.name, path=str(child), exists=True))
        parent = str(current.parent) if self.is_allowed(current.parent) else None
        return dict(path=str(current), parent=parent, entries=entries[:500])

    # ---------------------------------------------------------------- checks
    def check(self, path, *, create=False, verify_windows=True):
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

    def _windows_mapping(self, directory: Path, probe: Path, token: str):
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
    def data_root(self, output_root, *, mock: bool) -> Path:
        root = self.resolve(output_root)
        if MOCK_SUBDIR in root.parts[len(self._owning_root(root).parts):]:
            raise PathNotAllowed(f'Select the output root itself, not its {MOCK_SUBDIR}/ directory')
        return root / MOCK_SUBDIR if mock else root

    def _owning_root(self, resolved: Path) -> Path:
        return next(r for r in self.roots if resolved == r or r in resolved.parents)


def is_mock_path(path) -> bool:
    return MOCK_SUBDIR in Path(path).parts


def _existing_parent(path: Path) -> Path:
    while not path.exists():
        path = path.parent
    return path


def filesystem_type(path) -> str:
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
    try:
        release = Path('/proc/sys/kernel/osrelease').read_text().strip()
    except OSError:
        return 'unknown'
    return f'WSL2 ({release})' if 'microsoft' in release.lower() else f'Linux ({release})'


def directory_bytes(path) -> int:
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
