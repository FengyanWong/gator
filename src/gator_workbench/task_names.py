"""The name a task is SHOWN under (record 7.302; user: "add rename functionality to tasks"). Organization only, like the
folders beside it: a rename never touches the task's key (`real:<name>`), its files, its Virtuoso cell, a run or a saved
model - every recorded run keeps naming the task it ran on. What changes is the name the windows show and the label new
runs of the task are filed under (`task_registry.starter_project`).

One small file in the workbench's settings folder, `task_names.json` (`{version, names: {task key: shown name}}`),
written under the folders' lock. A task without an entry is shown under its own name; giving a task its own name back
removes the entry."""
from __future__ import annotations

import fcntl
import json
import re

from .names import TASK_NAME
from .paths import local_settings_dir
from .storage.atomic import write_json
from .task_folders import _LOCK

FILE = 'task_names.json'
_NAME = re.compile(TASK_NAME)


class TaskNameError(ValueError):
    pass


class TaskNameTaken(TaskNameError):
    pass


class TaskNameMissing(TaskNameError):
    pass


def internal(task_key) -> str:
    """The name in the key: what the task's files, its cell and its runs carry."""
    return str(task_key).partition(':')[2]


def _read() -> dict:
    """The stored names; FileNotFoundError when none was ever given, TaskNameError for a file that is not ours."""
    state = json.loads((local_settings_dir() / FILE).read_text())
    names = state.get('names') if isinstance(state, dict) and state.get('version') == 1 else None
    if not isinstance(names, dict) or not all(isinstance(k, str) and isinstance(v, str) and _NAME.match(v) for k, v in names.items()):
        raise TaskNameError('The task names file contains invalid data; the existing file has been kept.')
    return names


def names() -> dict:
    """task key -> shown name, for the tasks that were renamed. A file that cannot be read gives none: the task list
    must never fail over a name (a rename then says what is wrong)."""
    try:
        return _read()
    except (OSError, ValueError):
        return {}


def shown(task_key, given=None, others=()) -> str:
    """The name a task is shown under. `given`: the stored names (read when None). `others`: the keys of the other
    registered tasks - a stored name that one of them carries as its own name is not used (a task saved later under
    that name wins; nothing is rewritten)."""
    given = names() if given is None else given
    name = given.get(task_key)
    if not name or any(internal(other) == name for other in others if other != task_key):
        return internal(task_key)
    return name


def rename(task_key, name, *, known) -> dict:
    """Shows the task `task_key` under `name` from now on. `known`: the keys of the registered tasks. Refused: a task
    that is not registered (TaskNameMissing), a name that is not a task name (TaskNameError), a name another task has
    or is shown under (TaskNameTaken). The task's own name removes its entry."""
    known = list(known)
    if task_key not in known:
        raise TaskNameMissing('This task is no longer registered. Refresh the task list.')
    name = (name or '').strip()
    if not _NAME.match(name):
        raise TaskNameError('Use a task name of 2-40 characters: a lower-case letter first, then lower-case letters, '
                            'digits and underscores.')
    directory = local_settings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with _LOCK, (directory / 'task_folders.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            given = _read()
        except FileNotFoundError:
            given = {}
        except (OSError, ValueError) as exc:
            raise TaskNameError('Cannot read the task names; the existing file has been kept.') from exc
        others = [key for key in known if key != task_key]
        if any(name in (internal(key), shown(key, given, known)) for key in others):
            raise TaskNameTaken(f'Another task is named "{name}" or shown under that name. Choose another name.')
        previous = shown(task_key, given, known)
        if name == internal(task_key):
            given.pop(task_key, None)
        else:
            given[task_key] = name
        write_json(directory / FILE, dict(version=1, names=given))
    return dict(task_key=task_key, name=name, previous=previous, internal_name=internal(task_key))


def forget(task_key) -> None:
    """A deleted task loses its shown name, so a task saved later under the same key starts with its own."""
    directory = local_settings_dir()
    if not (directory / FILE).is_file():
        return
    with _LOCK, (directory / 'task_folders.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            given = _read()
        except (OSError, ValueError):
            return
        if given.pop(task_key, None) is not None:
            write_json(directory / FILE, dict(version=1, names=given))
