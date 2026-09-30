"""No-tool sizing clients. These are invoked only by an authorized run worker.

No model call is made by importing, validating or inspecting this module.
"""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading

from .base import AgentSettings, AgentRequest, AgentError, ProcessRegistry, run_cli
from .claude_code import ClaudeCodeProvider, LIVE_ENV
from .codex import CodexProvider, listed, EVENT_OPTIONS
from .live import LiveTranslator, CodexTranslator


def resolve_settings(search):
    from ..runs import load_settings
    from . import default_provider_name
    saved = load_settings().get('agent') or {}
    provider = search.provider or default_provider_name(saved.get('provider'))
    if provider == 'disabled':
        raise ValueError('Enable Claude Code or Codex in the Agent tab before using AI sizing')
    same = provider == saved.get('provider')
    result = search.model_copy(update=dict(provider=provider,
        model=search.model or (saved.get('model') if same else None),
        effort=search.effort or (saved.get('effort') if same else None)))
    from .catalog import model_entry
    entry = model_entry(provider, result.model)
    if entry is not None and result.effort is not None and result.effort not in entry['efforts']:
        if search.effort is not None:
            raise ValueError(f'{result.model} does not support effort {result.effort!r}; choose one of '
                             f'{entry["efforts"] or ["provider default"]}')
        # Inheritance is optional. Do not carry e.g. Astra's Ultra setting into
        # Luna, or record a Haiku effort that its CLI deliberately omits.
        result = result.model_copy(update=dict(effort=None))
    try:
        AgentSettings(provider=provider, model=result.model, effort=result.effort).validate()
    except AgentError as exc:
        raise ValueError(str(exc)) from exc
    if provider == 'claude_code' and result.max_llm_notional_usd is None:
        raise ValueError('Claude sizing requires a notional cost ceiling as well as a call ceiling')
    return result


class CancellableRegistry(ProcessRegistry):
    """Cancellation before Popen registration still stops the newly registered child."""
    def __init__(self):
        super().__init__()
        self.stopped = threading.Event()

    def register(self, request_id, process):
        super().register(request_id, process)
        if self.stopped.is_set():
            self.cancel(request_id)

    def stop(self):
        self.stopped.set()
        for request_id in self.active():
            self.cancel(request_id)


class SizingCliClient:
    def __init__(self, run_id, search):
        from ..runs import load_settings
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', run_id):
            raise ValueError('Invalid run ID')
        saved = load_settings().get('agent') or {}
        settings = AgentSettings(provider=search.provider, model=search.model, effort=search.effort,
            timeout_seconds=min(3600, search.llm_call_timeout_seconds), allowed_tools=(),
            cli_path=saved.get('cli_path') if saved.get('provider') == search.provider else None)
        self.provider = (ClaudeCodeProvider if search.provider == 'claude_code' else CodexProvider)(settings)
        self.timeout = search.llm_call_timeout_seconds
        self.cwd = Path('/tmp') / f'gator-llm-{run_id}'
        self.cwd.mkdir(mode=0o700, exist_ok=True)
        self.registry = CancellableRegistry()
        self.call_id, self.remaining_cost = None, None

    def prepare_call(self, call_id, remaining_cost):
        self.call_id, self.remaining_cost = call_id, remaining_cost

    def cancel(self):
        self.registry.stop()

    def complete(self, prompt, schema, *, on_event=None):
        if self.registry.stopped.is_set():
            raise AgentError('cancelled')
        executable = self.provider.executable()
        if not executable and self.provider.name == 'codex' and not self.provider.settings.cli_path:
            candidates = [p for p in Path('/mnt/c/Users/38094/.codex/bin/wsl').glob('*/codex')
                          if p.is_file() and os.access(p, os.X_OK)]
            executable = str(max(candidates, key=lambda p: p.stat().st_mtime_ns)) if candidates else None
        if not executable:
            raise AgentError('cli_missing')
        emit = on_event or (lambda event: None)
        if self.provider.name == 'claude_code':
            request = AgentRequest('parameters', prompt, {}, None, request_id=self.call_id)
            argv = self.provider.build_argv(executable, request, live=True, schema=schema)
            argv += ['--tools', '', '--max-budget-usd', str(self.remaining_cost)]
            code, stdout, stderr = run_cli(argv, stdin_text=prompt, cwd=self.cwd, timeout=self.timeout,
                request_id=self.call_id, registry=self.registry, env=dict(os.environ, **LIVE_ENV),
                on_line=LiveTranslator(emit).feed)
            result = self.provider.parse(request, code, stdout, stderr)
            return dict(output=result.structured_output, audit=result.audit)
        help_text = self.provider.help_text(executable)
        if not listed('--ignore-user-config', help_text):
            raise AgentError('unsupported_cli', 'Sizing needs --ignore-user-config to isolate tools from personal settings')
        events = next((option for option in EVENT_OPTIONS if listed(option, help_text)), None)
        translator = CodexTranslator(emit)
        directory = Path(tempfile.mkdtemp(prefix='gator-llm-schema-'))
        try:
            schema_file, answer_file = directory / 'schema.json', directory / 'answer.json'
            schema_file.write_text(json.dumps(schema))
            argv = self.provider.build_argv(executable, help_text, schema_file, answer_file, events)
            overrides = ['--ignore-user-config']
            for value in ('web_search="disabled"', 'features.shell_tool=false', 'features.unified_exec=false',
                          'features.multi_agent=false', 'features.apps=false', 'features.plugins=false',
                          'features.code_mode=false', 'features.image_generation=false', 'tools.view_image=false',
                          'mcp_servers={}', 'approval_policy="never"'):
                overrides += ['--config', value]
            argv[-1:-1] = overrides
            code, stdout, stderr = run_cli(argv, stdin_text=prompt, cwd=self.cwd, timeout=self.timeout,
                request_id=self.call_id, registry=self.registry, on_line=translator.feed if events else None)
            if code:
                raise AgentError('nonzero_exit', f'Codex sizing exited with status {code}')
            if not answer_file.is_file():
                raise AgentError('no_structured_output')
            try:
                output = json.loads(answer_file.read_text())
            except ValueError:
                raise AgentError('incomplete_output')
            usage = None
            for line in stdout.splitlines():
                try:
                    event = json.loads(line)
                    if event.get('type') == 'turn.completed':
                        usage = event.get('usage')
                except ValueError:
                    pass
            return dict(output=output, audit=dict(usage=usage, total_cost_usd=None))
        finally:
            shutil.rmtree(directory)
