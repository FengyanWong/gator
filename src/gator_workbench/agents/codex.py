"""CodexProvider: the same request/result contract through ``codex exec``.

Neither CLI was installed on the development host, and no Codex documentation was checked
for this version. The provider therefore VERIFIES every option it wants to use against the
locally installed ``codex exec --help`` (a local, non-billable call) and reports
``unsupported_cli`` instead of guessing when an option is absent. It always asks for a
read-only sandbox and never for an approval/sandbox bypass.

A LIVE request (status record 7.50) adds ``--json``: the CLI then prints its events as JSON
lines, which agents/live.py turns into what the page shows while Codex works. That option is
taken from the Codex documentation ("Non-interactive mode"; its TypeScript SDK passes the
older name ``--experimental-json``) and is used only when ``codex exec --help`` lists one of
the two; otherwise the answer arrives in one piece, as before. Still the answer is the output
file, and only when a CLI version writes none is it the last agent message of the stream.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ..security import redact
from .base import AgentError, AgentRequest, AgentResult, CliProvider, run_cli
from .claude_code import AUTH_PATTERNS, MODEL_PATTERNS
from .live import CodexTranslator
from .prompts import PROPOSAL_SCHEMA, build_prompt

WANTED_OPTIONS = ('--output-schema', '--output-last-message', '--sandbox')
EVENT_OPTIONS = ('--json', '--experimental-json')      # events as JSON lines: the documented name first


def listed(option, help_text) -> bool:
    """`option` as a whole word of the help text: `--json` is not `--json-schema`."""
    return re.search(rf'(?<![\w-]){re.escape(option)}(?![\w-])', help_text) is not None


class CodexProvider(CliProvider):
    name = cli = 'codex'

    def help_text(self, executable):
        try:
            done = subprocess.run([executable, 'exec', '--help'], capture_output=True, text=True, timeout=30,
                                  stdin=subprocess.DEVNULL, shell=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AgentError('unsupported_cli', f'`codex exec --help` could not be run: {exc}')
        return done.stdout + done.stderr

    def propose(self, request: AgentRequest, on_event=None) -> AgentResult:
        """With `on_event`, the CLI's events are reported while it works, as far as `codex exec --help` lists an event
        option (see the module text); the proposal comes from the answer either way."""
        request.validate()
        if request.web:
            raise AgentError('unsupported_cli', 'Online research is wired for the Claude Code provider only: the codex CLI was never '
                                                'installed here, so its web options could not be verified. Switch it off or change provider.')
        executable = self.executable()
        if executable is None:
            raise AgentError('cli_missing', '`codex` was not found on the PATH of the BACKEND process')
        help_text = self.help_text(executable)
        missing = [option for option in WANTED_OPTIONS if option not in help_text]
        if missing:
            raise AgentError('unsupported_cli', f'The installed codex CLI does not list {missing} under `codex exec '
                                                '--help`; structured proposals cannot be requested safely.')
        events = next((option for option in EVENT_OPTIONS if listed(option, help_text)), None) if on_event else None
        if on_event and not events:
            on_event(dict(type='step', text='This version of the codex CLI lists no event option (--json) under `codex exec '
                                            '--help`; the answer will arrive in one piece.'))
        translator = CodexTranslator(on_event) if events else None
        scratch = Path(tempfile.mkdtemp(prefix='gator-agent-'))
        try:
            schema_file, answer_file = scratch / 'schema.json', scratch / 'answer.json'
            schema_file.write_text(json.dumps(PROPOSAL_SCHEMA))
            argv = [executable, 'exec', *([events] if events else []), '--sandbox', 'read-only', '--output-schema', str(schema_file),
                    '--output-last-message', str(answer_file)]
            if '--skip-git-repo-check' in help_text:
                argv.append('--skip-git-repo-check')            # the scratch directory is not a repository
            if self.settings.model:
                argv += ['--model', self.settings.model]
            if self.settings.effort:                               # codex has no effort flag: it is a config override
                if '--config' not in help_text:
                    raise AgentError('unsupported_cli', 'The installed codex CLI does not list `--config` under `codex '
                                                        'exec --help`, so the reasoning effort cannot be set; clear it.')
                argv += ['--config', f'model_reasoning_effort="{self.settings.effort}"']
            argv.append('-')                                       # prompt on stdin
            code, stdout, stderr = run_cli(argv, stdin_text=build_prompt(request), cwd=scratch,
                                           timeout=self.settings.timeout_seconds, request_id=request.request_id,
                                           on_line=translator.feed if translator else None)
            logs = [dict(type='stdout', text=redact(line, 500)) for line in stdout.splitlines()[-200:]]
            excerpt = redact(stderr.strip(), 2000)
            if code != 0:
                if AUTH_PATTERNS.search(stderr + stdout):
                    raise AgentError('unauthenticated', excerpt)
                if MODEL_PATTERNS.search(stderr + stdout):
                    raise AgentError('model_unavailable', excerpt)
                raise AgentError('nonzero_exit', f'exit status {code}', exit_code=code, stderr=excerpt)
            final = answer_file.read_text() if answer_file.is_file() else translator.last_message if translator else None
            if final is None:
                raise AgentError('no_structured_output', 'codex wrote no final message file')
            try:
                structured = json.loads(final)
            except json.JSONDecodeError:
                raise AgentError('incomplete_output', 'The final message is not valid JSON')
            if not isinstance(structured, dict):
                raise AgentError('no_structured_output', 'The final message is not a JSON object')
            return AgentResult(request.request_id, self.name, 'codex', structured, logs,
                               dict(exit_code=code, note='Audit metadata only; never RL state.'))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
