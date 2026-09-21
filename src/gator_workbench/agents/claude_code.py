"""ClaudeCodeProvider: non-interactive proposals through the locally installed ``claude`` CLI.

Documented behaviour relied upon (code.claude.com/docs headless + cli-reference, checked
2026-09-20; the CLI was NOT installed on the development host, so none of this could be
exercised against a real binary there - tests use a fake CLI fixture):
  * ``claude -p`` reads the prompt from stdin;
  * ``--output-format json`` prints one result object, ``stream-json`` prints NDJSON events whose
    last event has type ``result``; with ``-p`` stream-json is used together with ``--verbose``;
  * ``--json-schema '<inline schema>'`` puts validated output in ``structured_output``; repeated
    validation failure gives subtype ``error_max_structured_output_retries``;
  * denied tool calls are listed in ``permission_denials``;
  * ``--permission-mode``, ``--allowedTools``, ``--disallowedTools``, ``--model``, ``--effort``.
Not documented, therefore NOT used: a non-billable authentication check (authentication is
reported as unknown until a real request answers), ``--disable-slash-commands``, a nested-session
variable. ``--bare`` is never passed because it skips skill discovery.

Only the final ``structured_output`` is treated as configuration. stderr, progress text and
Markdown are never parsed as JSON.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from ..security import redact
from .base import (AgentError, AgentProvider, AgentRequest, AgentResult, WRITE_OR_EXEC_TOOLS, run_cli)
from .catalog import supports_effort
from .settings_review import WEB_MAX_TURNS, WEB_TIMEOUT_SECONDS
from .prompts import build_prompt, proposal_schema_json

WEB_TOOLS = ('WebSearch', 'WebFetch')
AUTH_PATTERNS = re.compile(r'(?i)(invalid api key|please run /login|not logged in|authentication[_ ]error|'
                           r'oauth token (has )?expired|unauthorized|401\b|credit balance|login required)')
MODEL_PATTERNS = re.compile(r'(?i)(model[^.\n]{0,80}(not found|does not exist|not available|unavailable|invalid|'
                            r'not supported|no access)|invalid model|unknown model|404[^\n]{0,40}model)')


class ClaudeCodeProvider(AgentProvider):
    name = 'claude_code'

    def executable(self):
        if self.settings.cli_path:
            path = Path(self.settings.cli_path)
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which('claude')

    def available(self):
        path = self.executable()
        return dict(provider=self.name, available=path is not None, executable=path,
                    reason=None if path else "`claude` is not on the backend process PATH")

    def working_directory(self, request: AgentRequest):
        """Proposal requests run in an empty scratch directory: even a read-only tool then has nothing
        sensitive to read. Only a request that needs a project skill runs in the repository, because
        project skills are discovered relative to the working directory."""
        if request.requires_bridge_skill:
            from ..paths import repo_root
            return repo_root(), None
        scratch = tempfile.mkdtemp(prefix='gator-agent-')
        return Path(scratch), scratch

    def build_argv(self, executable, request: AgentRequest):
        s = self.settings
        argv = [executable, '-p', '--output-format', 'stream-json' if s.stream else 'json']
        if s.stream:
            argv.append('--verbose')
        # Online research (a settings_review that asked for it, nothing else): the two web tools come off the deny list - a
        # denied tool cannot be re-allowed - and WebFetch is allowed for the operator's publication hosts only. Everything that
        # writes or executes stays denied, and the working directory stays the empty scratch directory.
        web = bool(request.web and request.kind == 'settings_review' and request.web_domains)
        denied = [tool for tool in WRITE_OR_EXEC_TOOLS if not (web and tool in WEB_TOOLS)]
        allowed = list(s.allowed_tools) + (['WebSearch'] + [f'WebFetch(domain:{host})' for host in request.web_domains] if web else [])
        argv += ['--json-schema', proposal_schema_json(), '--permission-mode', s.permission_mode, '--disallowedTools', ','.join(denied)]
        if allowed:
            argv += ['--allowedTools', ','.join(allowed)]
        if s.model:
            argv += ['--model', s.model]
        if s.effort and supports_effort(self.name, s.model):      # e.g. Haiku takes no effort: nothing to pass
            argv += ['--effort', s.effort]
        if s.max_turns or web:
            argv += ['--max-turns', str(int(s.max_turns or WEB_MAX_TURNS))]
        return argv

    def propose(self, request: AgentRequest) -> AgentResult:
        request.validate()
        executable = self.executable()
        if executable is None:
            raise AgentError('cli_missing', '`claude` was not found on the PATH of the BACKEND process. A working '
                                            'terminal session does not prove the web backend has the same PATH.')
        if request.requires_bridge_skill:
            from .diagnostics import skill_visibility
            visibility = skill_visibility()
            if not visibility['any_visible_on_disk']:
                raise AgentError('skill_not_visible', visibility['summary'], visibility=visibility)
        cwd, scratch = self.working_directory(request)
        try:
            code, stdout, stderr = run_cli(self.build_argv(executable, request), stdin_text=build_prompt(request),
                                           cwd=cwd, timeout=max(self.settings.timeout_seconds, WEB_TIMEOUT_SECONDS) if request.web
                                           else self.settings.timeout_seconds, request_id=request.request_id)
        finally:
            if scratch:
                shutil.rmtree(scratch, ignore_errors=True)
        return self.parse(request, code, stdout, stderr)

    # ------------------------------------------------------------------ parsing
    def parse(self, request, code, stdout, stderr) -> AgentResult:
        logs, result = self._events(stdout)
        stderr_excerpt = redact(stderr.strip(), 2000)
        haystack = ' '.join(filter(None, [stderr, json.dumps(result) if result else '']))
        if result is None:
            if AUTH_PATTERNS.search(stderr):
                raise AgentError('unauthenticated', stderr_excerpt)
            if MODEL_PATTERNS.search(stderr):
                raise AgentError('model_unavailable', stderr_excerpt)
            if code != 0:
                raise AgentError('nonzero_exit', f'exit status {code}', exit_code=code, stderr=stderr_excerpt)
            raise AgentError('incomplete_output', 'No result object was found on stdout', stderr=stderr_excerpt)
        audit = dict(session_id=result.get('session_id'), usage=result.get('usage'), num_turns=result.get('num_turns'),
                     total_cost_usd=result.get('total_cost_usd'), duration_ms=result.get('duration_ms'),
                     subtype=result.get('subtype'), exit_code=code,
                     note='Audit metadata of the agent request only. Never an RL run id, checkpoint or simulation budget.')
        denials = result.get('permission_denials') or []
        if request.web:                 # a page outside the publication hosts was refused: that is the rule working, not a fault
            refused = [d for d in denials if isinstance(d, dict) and d.get('tool_name') in WEB_TOOLS]
            denials = [d for d in denials if d not in refused]
            audit['web_calls_refused'] = len(refused)
        if denials:
            raise AgentError('permission_denied', f'{len(denials)} tool call(s) were denied; a proposal request may not '
                                                  'write files or run commands',
                             denials=[dict(tool=d.get('tool_name')) for d in denials if isinstance(d, dict)], audit=audit)
        subtype = str(result.get('subtype') or '')
        if subtype == 'error_max_structured_output_retries':
            raise AgentError('schema_failure', 'The model could not produce schema-valid output', audit=audit)
        if result.get('is_error') or subtype.startswith('error'):
            text = redact(str(result.get('result') or subtype), 2000)
            if AUTH_PATTERNS.search(haystack):
                raise AgentError('unauthenticated', text, audit=audit)
            if MODEL_PATTERNS.search(haystack):
                raise AgentError('model_unavailable', text, audit=audit)
            raise AgentError('error_result', text, subtype=subtype, audit=audit)
        if code != 0:
            raise AgentError('nonzero_exit', f'exit status {code} despite a result object', exit_code=code,
                             stderr=stderr_excerpt, audit=audit)
        structured = result.get('structured_output')
        if not isinstance(structured, dict):
            # `result` may hold prose or Markdown. It is deliberately NOT parsed as configuration.
            raise AgentError('no_structured_output', 'The result has no `structured_output` object', audit=audit)
        return AgentResult(request.request_id, self.name, 'claude_code', structured, logs, audit)

    @staticmethod
    def _events(stdout):
        """Split intermediate events (logs) from the final result payload. Handles both formats."""
        text = stdout.strip()
        if not text:
            return [], None
        logs, result = [], None
        try:
            single = json.loads(text)
            if isinstance(single, dict):
                return [], single if single.get('type') == 'result' or 'structured_output' in single else None
            if isinstance(single, list):
                lines = [json.dumps(item) for item in single]
            else:
                return [], None
        except json.JSONDecodeError:
            lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logs.append(dict(type='unparsed', text=redact(line, 500)))
                continue
            if isinstance(event, dict) and event.get('type') == 'result':
                result = event
            elif isinstance(event, dict):
                logs.append(dict(type=event.get('type'), subtype=event.get('subtype'),
                                 summary=redact(json.dumps(event)[:500])))
        return logs, result
