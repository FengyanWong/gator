"""Small, persistent folders shared by the workbench's task windows."""
from fastapi import FastAPI
from pydantic import Field

from .. import task_folders, tasks
from .models import Body
from .support import fail


class FolderName(Body):
    name: str = Field(min_length=1, max_length=60)


class FolderMove(Body):
    task_keys: list[str] = Field(min_length=1, max_length=10000)
    folder_id: str | None


def _call(operation):
    try:
        return operation()
    except task_folders.FolderMissing as exc:
        fail(404, exc)
    except task_folders.FolderError as exc:
        fail(409, exc)


def register(app: FastAPI, context):
    @app.get('/api/task-folders')
    def folders():
        return _call(task_folders.read)

    @app.post('/api/task-folders')
    def create(body: FolderName):
        return _call(lambda: task_folders.create(body.name))

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
