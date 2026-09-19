"""Bounded attachments and positively owned scratch directories."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4


class SpaceExhausted(RuntimeError):
    pass


@dataclass(frozen=True)
class RecordingConfig:
    project_budget: int = 20 * 1024**3
    min_free: int = 5 * 1024**3
    attachment_budget: int = 256 * 1024**2
    # Reserved for each in-flight job, including transfer copies. Not a quota.
    temporary_reserve: int = 256 * 1024**2
    journal_reserve: int = 64 * 1024**2
    result_reserve: int = 1024**2
    error_bytes: int = 16 * 1024
    checkpoint_interval: int = 500
    update_interval: int = 100
    journal_mode: str = 'DELETE'

    def __post_init__(self):
        for name, value in vars(self).items():
            if name == 'journal_mode':
                if value not in ('DELETE', 'WAL'):
                    raise ValueError('journal_mode must be DELETE or WAL')
            elif type(value) is not int or value < (1 if name.endswith('interval') else 0):
                raise ValueError(f'Invalid recording budget: {name}')


def filesystem(path):
    """Linux/WSL mount type; unknown platforms cannot enable WAL automatically."""
    path = Path(path).resolve()
    matches = []
    try:
        for row in Path('/proc/mounts').read_text().splitlines():
            parts = row.split()
            mount = Path(parts[1].replace('\\040', ' '))
            if path.is_relative_to(mount):
                matches.append((len(mount.parts), parts[2]))
    except FileNotFoundError:
        return 'unknown'
    return max(matches)[1] if matches else 'unknown'


def disk_bytes(path):
    path = Path(path)
    try:
        if path.is_symlink():
            raise ValueError('Symlinks are not owned recording files')
        if path.is_file():
            return path.stat().st_size
        return sum(disk_bytes(child) for child in path.iterdir())
    except FileNotFoundError:
        # Read-only inspection can race the writer's allowed attachment eviction.
        return 0


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create_workspace(root, eval_id):
    root = Path(root).resolve()
    path = root / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    token = uuid4().hex
    (path / '.gator-owned').write_text(json.dumps(dict(eval_id=eval_id, token=token)))
    return dict(path=str(path), root=str(root), token=token, eval_id=eval_id,
                host='local', finished=False)


def checked_workspace(workspace):
    path, root = Path(workspace['path']), Path(workspace['root']).resolve()
    if not workspace['finished']:
        raise ValueError('Cannot clean a running or uncertain workspace')
    if path.is_symlink() or path.resolve() != path or path.parent != root:
        raise ValueError('Workspace escaped its dedicated root')
    if not path.exists():
        return path
    for directory, dirs, files in os.walk(path, followlinks=False):
        if any((Path(directory) / name).is_symlink() for name in dirs + files):
            raise ValueError('Symlink in owned workspace')
    marker = path / '.gator-owned'
    if json.loads(marker.read_text()) != dict(eval_id=workspace['eval_id'], token=workspace['token']):
        raise ValueError('Workspace ownership marker mismatch')
    assert_idle(path)
    return path


def assert_idle(path):
    """Timeout/return alone does not prove that a local Spectre process exited."""
    for pid_file in path.rglob('*.pid'):
        value = pid_file.read_text().strip()
        if value.isdigit():
            try:
                os.kill(int(value), 0)
            except ProcessLookupError:
                pass
            else:
                raise ValueError('Workspace process is still alive')
    proc_root = Path('/proc')
    if not proc_root.is_dir():
        raise ValueError('Local process liveness cannot be verified')
    for process in proc_root.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            if not (process / 'comm').read_text().strip().startswith('spectre'):
                continue
            cwd = (process / 'cwd').resolve()
            if cwd.is_relative_to(path) or str(path).encode() in (process / 'cmdline').read_bytes():
                raise ValueError('Spectre is still using this workspace')
        except (FileNotFoundError, ProcessLookupError):
            pass


def require_filesystem_space(path, config, reserve=None):
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    reserve = config.result_reserve if reserve is None else reserve
    if shutil.disk_usage(path).free - reserve < config.min_free:
        raise SpaceExhausted(f'Insufficient free space on output filesystem: {path}')


def remove_workspace(workspace):
    path = checked_workspace(workspace)
    if path.exists():
        shutil.rmtree(path)
        fsync_directory(path.parent)


def require_space(root, config, reserved=0):
    used = disk_bytes(root)
    free = shutil.disk_usage(root).free
    need = reserved + config.journal_reserve
    if used + need > config.project_budget or free - need < config.min_free:
        raise SpaceExhausted(f'Recording capacity exhausted: used={used}, free={free}, reserve={need}; '
                             'new simulations stopped; core records retained')
