"""The workbench's remembered settings (settings.json in its settings folder): read, saved one writer at a time, and the
output root a page or a run uses when none is given.

Moved from runs.py by the refactoring (docs/plan-refactoring.md); runs.py re-exports every name.
"""
from __future__ import annotations

import json
import threading

from .paths import default_output_root, local_settings_dir
from .storage.atomic import read_json, write_json


# ---------------------------------------------------------------------------- settings memory
# One writer at a time: two saves at once (Agent settings and a run start) each read the file, and the later write
# dropped the earlier one's keys (review of 2026-09-29). Reentrant, so prepare_run can hold it across its last_run
# merge.
SETTINGS_LOCK = threading.RLock()


def read_settings() -> tuple[dict, str | None]:
    """(settings, problem). The user may edit this file by hand: a typo in it used to take /api/meta and /api/runs down
    with HTTP 500. It now reads as empty, and `problem` says why in plain words."""
    path = local_settings_dir() / 'settings.json'
    try:
        settings = read_json(path, default={})
    except json.JSONDecodeError as exc:
        return {}, f'{path} is not valid JSON (line {exc.lineno}): fix or remove it; nothing is saved to it until then.'
    except (OSError, ValueError) as exc:                # unreadable, or not UTF-8 text
        return {}, f'{path} cannot be read ({type(exc).__name__}): fix or remove it; nothing is saved to it until then.'
    if not isinstance(settings, dict):
        return {}, f'{path} does not hold a JSON object: fix or remove it; nothing is saved to it until then.'
    return settings, None


def load_settings() -> dict:
    return read_settings()[0]


def save_settings(**updates) -> dict:
    """Merge settings updates under the writer lock without overwriting an unreadable settings file."""
    with SETTINGS_LOCK:
        settings, problem = read_settings()
        settings.update(updates)
        if problem is None:          # never overwrite a file that could not be read: it holds the user's own edits
            write_json(local_settings_dir() / 'settings.json', settings)
        return settings


def remembered_output_root() -> str:
    """Return the remembered output root or the configured default."""
    return load_settings().get('output_root') or str(default_output_root())


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_SETTINGS_LOCK = SETTINGS_LOCK
