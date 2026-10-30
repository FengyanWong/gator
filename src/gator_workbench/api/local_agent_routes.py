"""Local Agent HTTP surface. A review returns editor JSON; it never writes it."""
from __future__ import annotations

import threading
from typing import Literal
from fastapi import HTTPException, Query
from pydantic import Field

from .models import Body, ConfigBody
from ..local_agent.catalog import CATALOG
from ..local_agent.manager import Manager
from ..security import redact


class ModelAction(Body):
    action: Literal['install', 'deploy', 'undeploy', 'delete']


class Message(Body):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1)  # no answer truncation when conversation history includes a long answer


class Chat(ConfigBody):
    model_id: str
    messages: list[Message] = Field(min_length=1, max_length=1000)


def register(app, context):
    creation_lock = threading.Lock()

    def manager():
        with creation_lock:
            if not getattr(app.state, 'local_agent', None):
                app.state.local_agent = Manager()
            return app.state.local_agent

    def call(operation):
        try:
            return operation()
        except KeyError:
            raise HTTPException(404, 'Unknown model or expired Agent job.')
        except ValueError as exc:
            raise HTTPException(409, redact(str(exc), 3000))

    def model_id(value):
        if value not in CATALOG:
            raise HTTPException(404, 'Unknown catalog model.')
        return value

    @app.get('/api/local-agent')
    def status():
        def read():
            service = manager()
            service.bootstrap()
            return service.status()
        return call(read)

    @app.get('/api/local-agent/models/{identifier}/compatibility')
    def preflight(identifier: str):
        return call(lambda: manager().preflight(model_id(identifier)))

    @app.post('/api/local-agent/models/{identifier}')
    def action(identifier: str, body: ModelAction):
        return call(lambda: getattr(manager(), body.action)(model_id(identifier)))

    @app.post('/api/local-agent/chat')
    def chat(body: Chat):
        context.parse_config(body.config)
        if body.messages[-1].role != 'user':
            raise HTTPException(422, 'The newest message must be from the user.')
        return call(lambda: manager().chat(model_id(body.model_id), body.config,
                                           [m.model_dump() for m in body.messages], context))

    @app.get('/api/local-agent/jobs/{identifier}')
    def job(identifier: str, offset: int = Query(0, ge=0)):
        return call(lambda: manager().job(identifier, offset))

    @app.post('/api/local-agent/jobs/{identifier}/cancel')
    def cancel(identifier: str):
        return call(lambda: manager().cancel(identifier))

    @app.post('/api/local-agent/jobs/{identifier}/review')
    def review(identifier: str, body: ConfigBody):
        return call(lambda: manager().review(identifier, body.config, context))
