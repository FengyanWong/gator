"""Small, persistent folders shared by the workbench's windows: tasks (record 7.250), runs and models (record 7.263)."""
from pathlib import Path

from fastapi import FastAPI
from pydantic import Field

from .. import task_folders, tasks
from ..paths import PathNotAllowed
from .models import Body
from .support import fail


# Validated display name used when creating or renaming a workbench folder.
class FolderName(Body):
    name: str = Field(min_length=1, max_length=60)


# Task keys and target folder identity used to change task-folder membership.
class FolderMove(Body):
    task_keys: list[str] = Field(min_length=1, max_length=10000)
    folder_id: str | None


class RunFolderMove(Body):
    """Runs, or the models they saved, by their run folders - as the run list names them."""
    run_dirs: list[str] = Field(min_length=1, max_length=10000)
    folder_id: str | None


def _call(operation):
    try:
        return operation()
    except task_folders.FolderMissing as exc:
        fail(404, exc)
    except task_folders.FolderError as exc:
        fail(409, exc)


def register(app: FastAPI, context):
    """Register persistent folder endpoints for tasks, runs and saved RL models."""
    @app.get('/api/task-folders')
    def folders():
        return _call(task_folders.read)

    @app.post('/api/task-folders')
    def create(body: FolderName):
        return _call(lambda: task_folders.create(body.name))

    # Supply current task keys when assigning selected tasks to a folder.
    @app.put('/api/task-folders/assign')
    def move(body: FolderMove):
        return _call(lambda: task_folders.move(body.task_keys, body.folder_id,
                                              known_tasks=[t['task_key'] for t in tasks.list_tasks()]))

    @app.patch('/api/task-folders/{folder_id}')
    def rename(folder_id: str, body: FolderName):
        return _call(lambda: task_folders.rename(folder_id, body.name))

    @app.delete('/api/task-folders/{folder_id}')
    def remove(folder_id: str):
        return _call(lambda: task_folders.remove(folder_id))

    def runs_that_exist(run_dirs):
        """The run folders among `run_dirs` that are runs under the allowed output roots now (a run moved, deleted or
        outside the roots is not; the move then changes nothing and says so)."""
        found = []
        for run_dir in run_dirs:
            try:
                if (Path(context.roots.resolve(run_dir)) / 'run_manifest.json').is_file():
                    found.append(run_dir)
            except (PathNotAllowed, OSError, ValueError):
                pass
        return found

    # The run window's and the RL model window's folders (record 7.263): the same five routes, keyed by run folder.
    def register_kind(kind, prefix):
        @app.get(prefix)
        def folders_of_kind():
            return _call(lambda: task_folders.read(kind))

        @app.post(prefix)
        def create_in_kind(body: FolderName):
            return _call(lambda: task_folders.create(body.name, kind))

        # Supply existing authorized run directories when assigning runs or saved models to a folder.
        @app.put(f'{prefix}/assign')
        def move_in_kind(body: RunFolderMove):
            return _call(lambda: task_folders.move(body.run_dirs, body.folder_id, known=runs_that_exist(body.run_dirs),
                kind=kind))

        @app.patch(prefix + '/{folder_id}')
        def rename_in_kind(folder_id: str, body: FolderName):
            return _call(lambda: task_folders.rename(folder_id, body.name, kind))

        @app.delete(prefix + '/{folder_id}')
        def remove_in_kind(folder_id: str):
            return _call(lambda: task_folders.remove(folder_id, kind))

    register_kind('runs', '/api/run-folders')
    register_kind('models', '/api/model-folders')
