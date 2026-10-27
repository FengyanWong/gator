"""The store of saved tasks: each task's folder under the workbench's settings, its profile entry, its task file and the
folder of its earlier revisions, its recorded real baseline, and the result registry it brings.

Moved from profiles.py by the refactoring (docs/plan-refactoring.md): compile, validation, consistency and tasks read
these without needing the profile generator or Save task, and profiles.py re-exports every name.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .names import TASK_NAME
from .paths import local_settings_dir
from .storage.atomic import UNREADABLE, read_json_quiet


NAME = re.compile(TASK_NAME)
FORMAT = 'gator-generated-profile-1'
FILES = dict(design='design.json', mapping='mapping.json', structure='structure.scs', readback='readback.cdf.json',
             rules='rules.json', receipt='creation.json', entry='profile.json', reference='reference_measurements.json',
             maestro_deck='maestro_deck.json', conditions='conditions.json')      # conditions: only tasks of a PDK with a relative template (2026-10-09)


class ProfileError(ValueError):
    """Why a profile cannot be created, in words the form can show."""


def store_root() -> Path:
    return local_settings_dir() / 'profiles'


def profile_dir(name) -> Path:
    """Validate a profile name and return its local storage directory."""
    if not isinstance(name, str) or not NAME.match(name):
        raise ProfileError('The profile name must be lowercase letters, digits and "_" (2-40 characters, starting with a letter)')
    return store_root() / name


def list_profiles() -> dict:
    """Read recognizable stored profile entries and attach their directory paths."""
    found = {}
    root = store_root()
    for entry_file in sorted(root.glob(f'*/{FILES["entry"]}')) if root.is_dir() else ():
        entry = read_json_quiet(entry_file, UNREADABLE)
        if entry is UNREADABLE:
            continue
        if entry.get('format') == FORMAT and entry.get('name') == entry_file.parent.name and NAME.match(entry['name']):
            found[entry['name']] = dict(entry, directory=str(entry_file.parent))
    return found


def profile_entry(name) -> dict | None:
    """`list_profiles().get(name)`, from that one profile's file (record 7.279): the list reads every profile.json in the
    store - about 35 files on the 9p-mounted D: drive, 0.15 s - and the check of each edit, a task's load and the saved
    model's check each wanted one. The same answer: a folder of exactly that name (a case-insensitive drive opens
    other spellings too), readable JSON of this format naming itself."""
    root = store_root()
    if not isinstance(name, str) or not NAME.match(name) or not root.is_dir():
        return None
    entry_file = root / name / FILES['entry']
    try:
        if name not in os.listdir(root):
            return None
        entry = json.loads(entry_file.read_text())
    except (OSError, ValueError):
        return None
    if entry.get('format') == FORMAT and entry.get('name') == name:
        return dict(entry, directory=str(entry_file.parent))
    return None


def task_spec_registry(circuit) -> list | None:
    """The result registry of the generated profile a configuration runs, or None (any other task: the default
    registry, or whatever the configuration states itself)."""
    task_id = getattr(circuit, 'task_id', None) or ''
    if getattr(circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return None
    entry = profile_entry(task_id[len('real:'):])
    return None if entry is None else entry.get('spec_registry')


def reference_metrics(name) -> dict | None:
    """The recorded REAL baseline of a generated profile, once there is one."""
    try:
        reference = json.loads((profile_dir(name) / FILES['reference']).read_text())
    except (OSError, ValueError):
        return None
    return reference['metrics'] if reference.get('origin') == 'real' and isinstance(reference.get('metrics'), dict) else None


# The task file of a saved task, and the folder that keeps the task files of its earlier revisions.
TASK_FILE = 'task.json'
HISTORY = 'history'


def task_file(name) -> dict | None:
    """Read a profile's task JSON, returning nothing when the name or file cannot be read."""
    try:
        return json.loads((profile_dir(name) / TASK_FILE).read_text())
    except (OSError, ValueError, ProfileError):
        return None
