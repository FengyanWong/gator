"""The saved tasks (real:<name>), by one name: every function about them is reachable as profiles.<name>, as its callers
and the tests have always written it. Where each one lives (the refactoring of 2026-10-09, docs/plan-refactoring.md):

- profile_store: the store - a task's folder, entry, task file, history, recorded baseline, result registry;
- circuit_types: the circuit types and measurement kinds, what each needs from a cell, the probes each offers;
- saved_tasks: the tasks of a cell, a task's profile object for the real backend, a task's working run;
- profile_generate: a profile generated from a cell read out of Virtuoso ("Create profile", and every Save task);
- task_save: Save task;
- baseline_reference: a task's real baseline, recorded from a finished Baseline simulation;
- here: deleting a task.
"""
from __future__ import annotations

from pathlib import Path

from . import working_copy
from .storage.dataset import utcnow
from .task_registry import REAL_PROFILES
# re-exported: moved to profile_store.py by the refactoring (docs/plan-refactoring.md)
from .profile_store import (NAME, FORMAT, FILES, ProfileError, store_root, profile_dir, list_profiles, profile_entry,
                            task_spec_registry, reference_metrics, TASK_FILE, HISTORY, task_file)
# re-exported: moved to circuit_types.py by the refactoring (docs/plan-refactoring.md)
from .circuit_types import (RECIPES, OPAMP_NETS, MAESTRO, MAESTRO_NOT_RUNNABLE, NEEDS_FREQUENCY, NeedsFrequency,
                            _core_instance, _supply, _ring, _opamp_fit, PROBES, SIGNAL_LENGTH, _type_signals,
                            design_signals, probe_results, probe_rows, testbench_probes)
# re-exported: moved to saved_tasks.py by the refactoring (docs/plan-refactoring.md)
from .saved_tasks import (tasks_for_cell, task_for_cell, load_profile, _refuse_recorded_group_values, TRASH,
                          WORKING_STATES, working_run_of)
# re-exported: moved to profile_generate.py by the refactoring (docs/plan-refactoring.md)
from .profile_generate import (_on_grid, _group_step, _adjust_rows, _checked_import, _form_facts, _nominal_supply,
                               _generate, create_profile)
# re-exported: moved to baseline_reference.py by the refactoring (docs/plan-refactoring.md)
from .baseline_reference import (record_reference, latest_baseline_run, BASELINE_KIND, _run_outlived_the_task,
                                 adopt_baseline_run, adopt_latest_baseline)
# re-exported: moved to task_save.py by the refactoring (docs/plan-refactoring.md)
from .task_save import NewerSaved, measurement_kind, save_task


def delete_profile(name, *, run_rows=()) -> dict:
    """Take a GENERATED profile out of the registered tasks, so its cell can get a new one (its name is free again).

    Its folder is moved to ``profiles/.deleted/<name>.<utc>/``, not erased: a recorded baseline cost a real
    simulation, and the runs made with the profile refer to these files. The copy of the cell that was read from
    Virtuoso stays where it is. Refused while a worker is on a run of the task. Runs that were made keep their data;
    a paused one can no longer be resumed. The verified built-in circuits are not in this store and cannot be deleted."""
    entry = profile_entry(name)
    if entry is None:
        raise ProfileError(f'real:{name} is a verified built-in circuit, not a generated profile: it cannot be deleted'
                           if name in REAL_PROFILES else f'Unknown generated profile {name!r}')
    working = working_run_of(name, run_rows)
    if working is not None:
        raise ProfileError(f'Run {working.get("run_id") or working["run_dir"]} of real:{name} is working right now: abort it or let it finish first')
    directory = Path(entry['directory'])
    kept = directory.parent / TRASH / f'{name}.{utcnow().strftime("%Y%m%dT%H%M%S%fZ")}'
    kept.parent.mkdir(parents=True, exist_ok=True)
    directory.rename(kept)
    original = entry.get('original') or {}
    if original.get('library') and original.get('cell'):             # the cell's working copy is free for a new task
        from . import working_copy
        working_copy.release(original['library'], original['cell'], name)
        # The page puts the answer into its Circuit source: the user's OWN cell, not the working copy the task ran on (that
        # used to lead the next "Save task" to make a copy of the copy). A profile made before working copies has none.
        cell = dict(library=original['library'], cell=original['cell'], testbench_cell=original.get('testbench'))
    else:
        cell = dict(library=entry['library'], cell=entry['core_cell'], testbench_cell=entry.get('testbench_cell'))
    return dict(deleted=entry['task_key'], name=name, **cell,
                baseline_recorded=(kept / FILES['reference']).is_file(), kept_copy=str(kept))
