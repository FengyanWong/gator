"""Provider-independent agent plumbing: requests, results, the error taxonomy and a safe
subprocess runner.

Safety properties enforced here rather than left to each provider:
  * argv is always a list and the prompt always travels on stdin - never a shell string;
  * permission/tool arguments come from the REQUEST KIND, never from user text;
  * arguments that bypass permissions are refused outright;
  * the child inherits the environment unchanged. Protective variables are never deleted to
    get around a nested-session restriction, and no credential is added or read;
  * cancel/timeout signal only this request's own process group - never Virtuoso, a training
    worker or an unrelated agent session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from uuid import uuid4

from .catalog import efforts_for

REQUEST_KINDS = ('draft_config', 'parameters', 'targets', 'measurements', 'modify_fields', 'circuit_modification', 'readiness',
                 'minimal_start', 'settings_review', 'run_review')
SECTIONS_BY_KIND = {
    'draft_config': ('parameters', 'targets', 'measurements'), 'parameters': ('parameters',),
    'targets': ('targets',), 'measurements': ('measurements',),
    'modify_fields': ('parameters', 'targets', 'measurements'), 'circuit_modification': (),
    'readiness': ('parameters', 'targets', 'measurements'),      # "what is missing to start?": a checklist, plus rows it can fix
    # The fewest row changes after which the run can start. proposals.normalize() refuses a change to a row that has no
    # blocking issue, so "as few as possible" is enforced here and not merely asked for.
    'minimal_start': ('parameters', 'targets', 'measurements'),
    # Suggestions for the SETTINGS of the whole workbench (agents/settings_review.py). It patches no table: the user applies
    # a suggestion with a click, like typing the value into its panel. The only kind that may be allowed to read the web.
    'settings_review': (),
    # What a run produced (agents/run_digest.py, given as DATA - the agent reads no file): an explanation, and what to change next
    # as rows of the three tables and/or as settings suggestions. Never online.
    'run_review': ('parameters', 'targets', 'measurements'),
}
# Arguments that would remove the permission boundary. Refused even if configured.
FORBIDDEN_ARGUMENTS = ('--dangerously-skip-permissions', '--allow-dangerously-skip-permissions',
                       'bypassPermissions', '--dangerously-bypass-approvals-and-sandbox', '--yolo',
                       'danger-full-access', '--disable-slash-commands')
READ_ONLY_TOOLS = ('Read', 'Grep', 'Glob')           # the only tools a proposal request may ever be granted
WRITE_OR_EXEC_TOOLS = ('Bash', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Task', 'Agent')

ERROR_CODES = {
    'cli_missing': 'The agent CLI is not installed or not on the backend PATH.',
    'unsupported_cli': 'The installed CLI does not offer an option this provider needs.',
    'unauthenticated': 'The CLI reported that it is not authenticated.',
    'model_unavailable': 'The requested model is not available to this account/deployment.',
    'skill_not_visible': 'A required skill is not visible to the CLI in the backend environment.',
    'permission_denied': 'The agent attempted a tool call that the request does not permit.',
    'nonzero_exit': 'The CLI exited with a nonzero status.',
    'error_result': 'The CLI returned an error result.',
    'timeout': 'The request exceeded its time limit and its subprocess was stopped.',
    'cancelled': 'The request was cancelled by the user.',
    'no_structured_output': 'The result carried no structured output.',
    'schema_failure': 'The structured output did not satisfy the schema.',
    'incomplete_output': 'The CLI output was incomplete or not valid JSON.',
    'disabled': 'Agent assistance is disabled; use task-description export and structured-result import.',
    'invalid_request': 'The request is not valid.',
}


class AgentError(RuntimeError):
    def __init__(self, code, detail='', **extra):
        if code not in ERROR_CODES:
            raise ValueError(f'Unknown agent error code {code!r}')
        super().__init__(f'{code}: {detail or ERROR_CODES[code]}')
        self.code, self.detail, self.extra = code, detail or ERROR_CODES[code], extra

    def as_dict(self):
        return dict(code=self.code, meaning=ERROR_CODES[self.code], detail=self.detail, **self.extra)


@dataclass
class AgentSettings:
    """Agent model/effort/timeout/tools are independent of RL checkpoints, Spectre concurrency and
    circuit-evaluation budgets."""
    provider: str = 'disabled'
    model: str | None = None
    effort: str | None = None
    timeout_seconds: float = 300.0
    permission_mode: str = 'dontAsk'
    allowed_tools: tuple = ()
    max_turns: int | None = None
    cli_path: str | None = None
    stream: bool = True

    def validate(self):
        if self.timeout_seconds <= 0 or self.timeout_seconds > 3600:
            raise AgentError('invalid_request', 'timeout_seconds must be within (0, 3600]')
        if self.permission_mode in FORBIDDEN_ARGUMENTS or self.permission_mode not in ('default', 'plan', 'dontAsk'):
            raise AgentError('invalid_request', f'permission_mode {self.permission_mode!r} is not allowed for proposals; '
                                                'use default, plan or dontAsk. Permission bypass is never available.')
        extra = [t for t in self.allowed_tools if t not in READ_ONLY_TOOLS]
        if extra:
            raise AgentError('invalid_request', f'Only read-only tools {READ_ONLY_TOOLS} may be granted; refused: {extra}')
        if self.effort is not None and self.effort not in efforts_for(self.provider):      # the two CLIs differ
            raise AgentError('invalid_request', f'Unknown effort {self.effort!r} for provider {self.provider!r}; '
                                                f'it accepts {efforts_for(self.provider)}')
        for value in (self.model, self.cli_path):
            if value is not None and (not isinstance(value, str) or any(c in value for c in '\x00\n\r')):
                raise AgentError('invalid_request', 'model and cli_path must be single-line strings')
        if self.model is not None and self.model.startswith('-'):
            raise AgentError('invalid_request', 'model must not look like a command-line option')
        return self


@dataclass
class AgentRequest:
    kind: str
    user_prompt: str
    config: dict                       # current configuration (JSON)
    circuit_summary: dict | None       # authorized engineering summary only
    selection: list = field(default_factory=list)   # modify_fields: [{section, key, fields}]
    readiness: dict | None = None      # backend-computed start checklist (agents/readiness.py): words only, given as DATA
    review: dict | None = None         # settings_review only: settings, cited presets and a task digest without design data
    results: dict | None = None        # run_review only: the digest of ONE run's output, built by the backend
    web: bool = False                  # settings_review only, per request: may search the web and open publication pages
    web_domains: tuple = ()            # hosts WebFetch may open when `web` is set (operator-defined, never from a request)
    requires_bridge_skill: bool = False
    request_id: str = field(default_factory=lambda: uuid4().hex)

    def validate(self):
        if self.kind not in REQUEST_KINDS:
            raise AgentError('invalid_request', f'kind must be one of {REQUEST_KINDS}')
        if not isinstance(self.user_prompt, str) or not self.user_prompt.strip():
            raise AgentError('invalid_request', 'A prompt is required')
        if len(self.user_prompt) > 20000:
            raise AgentError('invalid_request', 'The prompt is too long (20000 characters maximum)')
        if self.web and self.kind != 'settings_review':
            raise AgentError('invalid_request', 'Only a settings_review request may use online research')
        if self.kind == 'run_review' and not self.results:
            raise AgentError('invalid_request', 'A run_review needs a run: choose one with "Runs..." first')
        if self.kind == 'modify_fields' and not self.selection:
            raise AgentError('invalid_request', 'modify_fields needs a selection of rows/fields')
        return self


@dataclass
class AgentResult:
    request_id: str
    provider: str
    origin: str                        # claude_code | codex | manual_import | fixture - never silently "mock"
    structured_output: dict
    logs: list = field(default_factory=list)          # intermediate events, kept apart from the final output
    audit: dict = field(default_factory=dict)         # session id, usage, cost: audit only, never RL state


def assert_safe_arguments(argv):
    for argument in argv:
        if not isinstance(argument, str) or '\x00' in argument:
            raise AgentError('invalid_request', 'Arguments must be NUL-free strings')
        if any(bad == argument or bad in argument.split('=') for bad in FORBIDDEN_ARGUMENTS):
            raise AgentError('invalid_request', f'Refusing permission-bypassing argument {argument!r}')
    return argv


class ProcessRegistry:
    """Tracks only the subprocesses this backend started for agent requests."""
    def __init__(self):
        self._lock, self._processes, self._cancelled = threading.Lock(), {}, set()

    def register(self, request_id, process):
        with self._lock:
            self._processes[request_id] = process

    def forget(self, request_id):
        with self._lock:
            self._processes.pop(request_id, None)
            self._cancelled.discard(request_id)

    def cancel(self, request_id) -> bool:
        with self._lock:
            process = self._processes.get(request_id)
            if process is None:
                return False
            self._cancelled.add(request_id)
        _stop(process)
        return True

    def was_cancelled(self, request_id) -> bool:
        with self._lock:
            return request_id in self._cancelled

    def active(self):
        with self._lock:
            return sorted(self._processes)


REGISTRY = ProcessRegistry()


def _stop(process, grace=3.0):
    """Signal ONLY this request's own process group (created with start_new_session)."""
    if process.poll() is not None:
        return
    try:
        group = os.getpgid(process.pid)
        if group == os.getpgid(0):          # never our own group: that would hit workers and the server
            process.terminate()
        else:
            os.killpg(group, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        process.wait(timeout=grace)


def run_cli(argv, *, stdin_text, cwd, timeout, request_id, registry=REGISTRY, env=None, max_output=32 * 1024 * 1024):
    """Run a CLI without a shell. Returns (returncode, stdout, stderr). Raises AgentError for
    missing binary, timeout and cancellation."""
    assert_safe_arguments(argv)
    cwd = Path(cwd)
    if not cwd.is_dir():
        raise AgentError('invalid_request', f'Working directory does not exist: {cwd}')
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=str(cwd), env=dict(os.environ) if env is None else env, shell=False,
                                   start_new_session=True, text=True, encoding='utf8', errors='replace')
    except FileNotFoundError:
        raise AgentError('cli_missing', f'{argv[0]!r} was not found by the backend process')
    except PermissionError:
        raise AgentError('cli_missing', f'{argv[0]!r} is not executable by the backend process')
    registry.register(request_id, process)
    try:
        try:
            stdout, stderr = process.communicate(stdin_text.replace('\x00', ''), timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(process)
            process.communicate()
            raise AgentError('timeout', f'No result within {timeout:g} s; the request subprocess was stopped')
        if registry.was_cancelled(request_id):
            raise AgentError('cancelled')
        if len(stdout) > max_output:
            raise AgentError('incomplete_output', 'CLI output exceeded the size limit')
        return process.returncode, stdout, stderr
    finally:
        registry.forget(request_id)


class AgentProvider:
    name = 'base'

    def __init__(self, settings: AgentSettings | None = None):
        self.settings = (settings or AgentSettings()).validate()

    def available(self) -> dict:
        raise NotImplementedError

    def propose(self, request: AgentRequest) -> AgentResult:
        raise NotImplementedError

    def cancel(self, request_id) -> bool:
        return REGISTRY.cancel(request_id)
