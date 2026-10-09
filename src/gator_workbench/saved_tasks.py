"""The saved tasks around a cell and a run: the tasks a Virtuoso cell belongs to, a saved task's profile object for the
real backend (every check of the verified classes runs when it is built), and the run of a task that is working right
now.

Moved from profiles.py by the refactoring (docs/plan-refactoring.md): the profile generator and Save task need these,
and profiles.py re-exports every name.
"""
from __future__ import annotations

from pathlib import Path

from . import cdf_write, recipes
from .connection import load_profiles
from .names import WORKING_STATES
# re-exported: profiles and task_save take it from here
from .names import TRASH
from .paths import repo_root
from .profile_store import FILES, ProfileError, list_profiles, profile_entry
from .storage.atomic import UNREADABLE, read_json_quiet
from .task_registry import REAL_PROFILES


def tasks_for_cell(library, cell) -> list:
    """The GENERATED tasks of a cell: saved from it (their `original`), or running on it (their copy is this cell)."""
    found = []
    for entry in list_profiles().values():
        original = entry.get('original') or {}
        if (original.get('library'), original.get('cell')) == (library, cell) or (entry['library'], entry['core_cell']) == (library, cell):
            found.append(dict(task_key=entry['task_key'], name=entry['name'], generated=True))
    return found


def task_for_cell(library, cell) -> dict | None:
    """The registered task a Virtuoso cell already belongs to, or None: the profile generated from it, or one of the
    verified built-in circuits. A built-in names its cell in its design file and its library in a Virtuoso connection
    (``bridge_connection.json``), so a cell of the same name in any other library is another cell. Local reads only."""
    generated = tasks_for_cell(library, cell)
    if generated:
        return generated[0]
    if not library or not cell or library not in {settings.get('library') for settings in load_profiles()['profiles'].values()
                                                  if isinstance(settings, dict)}:
        return None
    for name, info in REAL_PROFILES.items():
        design = read_json_quiet(repo_root() / info['design'], UNREADABLE)
        if design is UNREADABLE:
            continue
        if design.get('core_cell') == cell:
            return dict(task_key=f'real:{name}', name=name, generated=False)
    return None


def load_profile(name):
    """The profile object for the real backend. Every check of the verified classes runs in its constructor."""
    entry = profile_entry(name)
    if entry is None:
        raise ProfileError(f'Unknown generated profile {name!r}')
    directory = Path(entry['directory'])
    _refuse_recorded_group_values(name, directory / FILES['mapping'])
    # rules of format 2: any value the PDK's form lets a user type
    classes = cdf_write.PROFILE_CLASSES if cdf_write.rules_format(directory / FILES['rules']) == cdf_write.RULES_FORMAT \
        else recipes.PROFILE_CLASSES
    return classes[entry['recipe']](
        rules_file=directory / FILES['rules'], design_file=directory / FILES['design'], mapping_file=directory / FILES['mapping'],
        reference_structure=directory / FILES['structure'], reference_readback=directory / FILES['readback'],
        conditions_file=repo_root() / 'configs' / 'gpdk045_conditions.json')


def _refuse_recorded_group_values(name, mapping_file):
    """A task saved before 2026-09-22 recorded each group's value in its mapping. It then loads, passes every offline
    check and its baseline, and fails on the FIRST changed candidate with "Binding/current value mismatch" - after a
    real evaluation has been paid for. Say it before anything is started (review of 2026-09-23)."""
    mapping = read_json_quiet(mapping_file, UNREADABLE)
    if mapping is UNREADABLE:
        return                                   # an unreadable mapping is the profile object's own error to report
    stale = [g.get('id') for g in (mapping.get('parameter_groups') or [])
             if isinstance(g, dict) and 'value' in g and (g.get('lower') is not None or g.get('upper') is not None)]
    if stale:
        raise ProfileError(f'real:{name} was saved before the mapping stopped recording a fixed value per variable, so its '
                           f'first changed candidate would be refused by its own graph check ({", ".join(map(str, stale[:3]))}'
                           f'{"..." if len(stale) > 3 else ""}). Open the task and press "Save task" once; nothing else changes.')


# ---------------------------------------------------------------------------------- starting over


def working_run_of(name, run_rows):
    """The run of real:<name> a worker is on right now, among the rows of `runs.list_runs`, or None."""
    for row in run_rows:
        if row.get('state') not in WORKING_STATES or row.get('mock'):
            continue
        manifest = read_json_quiet(Path(row['run_dir']) / 'run_manifest.json', UNREADABLE)
        if manifest is UNREADABLE:
            continue
        if (manifest.get('circuit') or {}).get('task_key') == f'real:{name}':
            return row
    return None
