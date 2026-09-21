"""DisabledProvider: every manual workflow stays available without any agent.

It never fabricates a response. It can export a complete task description for use with any
external assistant, and import a structured result, which then goes through exactly the same
validation, diff and approval path and is labelled ``manual_import``.
"""
from __future__ import annotations

import json

from .base import AgentError, AgentProvider, AgentRequest, AgentResult
from .prompts import task_description


class DisabledProvider(AgentProvider):
    name = 'disabled'

    def available(self):
        return dict(provider=self.name, available=True, executable=None, reason=None)

    def propose(self, request: AgentRequest, on_event=None) -> AgentResult:
        raise AgentError('disabled')

    def export_task(self, request: AgentRequest) -> dict:
        request.validate()
        return task_description(request)

    def import_result(self, request: AgentRequest, payload) -> AgentResult:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise AgentError('incomplete_output', f'Not valid JSON: {exc}')
        if not isinstance(payload, dict):
            raise AgentError('no_structured_output', 'A JSON object is required')
        return AgentResult(request.request_id, self.name, 'manual_import', payload, [],
                           dict(note='Imported by the user; not produced by an agent run from this application.'))
