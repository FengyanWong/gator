"""Folders for organization only: never rename task files, change encoders or rewrite run provenance.

One store per kind (record 7.263; plan docs/plan-frontend-run-workflow.md, "Categories for runs and models"): `tasks`
(record 7.250, keyed by task key), `runs` and `models` (both keyed by a run's folder path - a model is one run's saved
model - but kept apart, because the Runs window and the RL model window serve different purposes). Each kind has its own
file in the workbench's settings folder; all share one lock and the same checks. An assignment of a run that is no longer
listed stays in its file and is simply not shown."""
from __future__ import annotations

import fcntl
import json
import re
import threading
from uuid import uuid4

from .paths import local_settings_dir
from .storage.atomic import write_json

FILE = 'task_folders.json'
# kind -> (file, the thing a folder holds, its plural)
KINDS = {'tasks': (FILE, 'task', 'tasks'), 'runs': ('run_folders.json', 'run', 'runs'),
         'models': ('model_folders.json', 'model', 'models')}
_LOCK = threading.Lock()


class FolderError(ValueError):
    """Folder organization could not be validated, read or changed."""
    pass


class FolderMissing(FolderError):
    """The requested organizational folder no longer exists."""
    pass


def _kind(kind: str) -> tuple[str, str, str]:
    if kind not in KINDS:
        raise ValueError(f'Unknown kind of folders: {kind}')
    return KINDS[kind]


def _name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 60 or re.search(r'[/\\\x00-\x1f\x7f]', name):
        raise FolderError('Use a folder name of 1–60 characters without slashes or control characters.')
    if name.casefold() in ('all tasks', 'all runs', 'all models', 'unfiled'):
        raise FolderError('All tasks, All runs, All models and Unfiled are reserved names.')
    return name


def read(kind: str='tasks') -> dict:
    """Read and validate folder organization, returning an empty initial state only when its file is absent."""
    file, noun, _ = _kind(kind)
    path = local_settings_dir() / file
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return dict(version=1, folders={}, assignments={})
    except (ValueError, OSError) as exc:
        raise FolderError(f'Cannot read {noun} folders; the existing file has been kept.') from exc
    try:
        if state['version'] != 1:
            raise ValueError('Unknown version')
        folders, assignments = state['folders'], state['assignments']
        if not isinstance(folders, dict) or not isinstance(assignments, dict):
            raise ValueError('Invalid collections')
        if not all(re.fullmatch(r'[0-9a-f]{32}', key) and _name(name) == name for key, name in folders.items()):
            raise ValueError('Invalid folder')
        if len({name.casefold() for name in folders.values()}) != len(folders):
            raise ValueError('Duplicate names')
        if not all(isinstance(key, str) and folder in folders for key, folder in assignments.items()):
            raise ValueError('Invalid assignment')
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise FolderError(
            f'{noun.capitalize()} folders contain invalid data; the existing file has been kept.') from exc
    return state


def _change(edit, kind: str) -> dict:
    # Serialize read/modify/write across browser tabs AND backend/maintenance processes - one lock for every kind.
    directory = local_settings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with _LOCK, (directory / 'task_folders.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(kind)
        edit(state)
        write_json(directory / _kind(kind)[0], state)
        return state


def _require(state: dict, folder_id: str, kind: str) -> None:
    if folder_id not in state['folders']:
        raise FolderMissing(f'This folder no longer exists. Refresh the {_kind(kind)[1]} list.')


def _unique(state: dict, name: str, except_id: str | None=None) -> None:
    if any(key != except_id and label.casefold() == name.casefold() for key, label in state['folders'].items()):
        raise FolderError('A folder with that name already exists.')


def create(name: str, kind: str='tasks') -> dict:
    """Create a uniquely named organizational folder and return its new identifier with the updated state."""
    name, folder_id = _name(name), uuid4().hex

    def edit(state: dict) -> None:
        _unique(state, name)
        state['folders'][folder_id] = name

    return dict(_change(edit, kind), created_id=folder_id)


def rename(folder_id: str, name: str, kind: str='tasks') -> dict:
    """Rename an existing organizational folder after checking that its new name is unique."""
    name = _name(name)

    def edit(state: dict) -> None:
        _require(state, folder_id, kind)
        _unique(state, name, folder_id)
        state['folders'][folder_id] = name

    return _change(edit, kind)


def remove(folder_id: str, kind: str='tasks') -> dict:
    """Remove an organizational folder and its assignments while retaining the organized items."""
    def edit(state: dict) -> None:
        _require(state, folder_id, kind)
        del state['folders'][folder_id]
        state['assignments'] = {key: value for key, value in state['assignments'].items() if value != folder_id}

    return _change(edit, kind)


def move(keys, folder_id: str | None, *, known_tasks=None, known=None, kind: str='tasks') -> dict:
    """Put `keys` (task keys, or run folders) into the folder, or back to Unfiled (`folder_id` None). Every key must be
    `known` - a registered task, a listed run - or nothing is changed."""
    _, noun, plural = _kind(kind)
    known = known_tasks if known is None else known
    if not keys or not set(keys) <= set(known or ()):
        raise FolderError(f'Some selected {plural} no longer exist. Refresh the {noun} list.')

    def edit(state: dict) -> None:
        if folder_id is not None:
            _require(state, folder_id, kind)
        for key in keys:
            if folder_id is None:
                state['assignments'].pop(key, None)
            else:
                state['assignments'][key] = folder_id

    return _change(edit, kind)
