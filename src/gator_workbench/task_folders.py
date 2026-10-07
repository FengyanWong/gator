"""Task organization only: never rename task files, change encoders or rewrite run provenance."""
from __future__ import annotations

import fcntl
import json
import re
import threading
from uuid import uuid4

from .paths import local_settings_dir
from .storage.atomic import write_json

FILE = 'task_folders.json'
_LOCK = threading.Lock()


class FolderError(ValueError):
    pass


class FolderMissing(FolderError):
    pass


def _name(value):
    name = value.strip()
    if not name or len(name) > 60 or re.search(r'[/\\\x00-\x1f\x7f]', name):
        raise FolderError('Use a folder name of 1–60 characters without slashes or control characters.')
    if name.casefold() in ('all tasks', 'unfiled'):
        raise FolderError('All tasks and Unfiled are reserved names.')
    return name


def read():
    path = local_settings_dir() / FILE
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return dict(version=1, folders={}, assignments={})
    except (ValueError, OSError) as exc:
        raise FolderError('Cannot read task folders; the existing file has been kept.') from exc
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
        raise FolderError('Task folders contain invalid data; the existing file has been kept.') from exc
    return state


def _change(edit):
    # Serialize read/modify/write across browser tabs AND backend/maintenance processes.
    directory = local_settings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with _LOCK, (directory / 'task_folders.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read()
        edit(state)
        write_json(directory / FILE, state)
        return state


def _require(state, folder_id):
    if folder_id not in state['folders']:
        raise FolderMissing('This folder no longer exists. Refresh the task list.')


def _unique(state, name, except_id=None):
    if any(key != except_id and label.casefold() == name.casefold() for key, label in state['folders'].items()):
        raise FolderError('A folder with that name already exists.')


def create(name):
    name, folder_id = _name(name), uuid4().hex

    def edit(state):
        _unique(state, name)
        state['folders'][folder_id] = name

    return dict(_change(edit), created_id=folder_id)


def rename(folder_id, name):
    name = _name(name)

    def edit(state):
        _require(state, folder_id)
        _unique(state, name, folder_id)
        state['folders'][folder_id] = name

    return _change(edit)


def remove(folder_id):
    def edit(state):
        _require(state, folder_id)
        del state['folders'][folder_id]
        state['assignments'] = {key: value for key, value in state['assignments'].items() if value != folder_id}

    return _change(edit)


def move(task_keys, folder_id, *, known_tasks):
    if not task_keys or not set(task_keys) <= set(known_tasks):
        raise FolderError('Some selected tasks no longer exist. Refresh the task list.')

    def edit(state):
        if folder_id is not None:
            _require(state, folder_id)
        for key in task_keys:
            if folder_id is None:
                state['assignments'].pop(key, None)
            else:
                state['assignments'][key] = folder_id

    return _change(edit)
