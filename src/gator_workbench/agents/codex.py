"""CodexProvider: the same request/result contract through ``codex exec``.

Neither CLI was installed on the development host, and no Codex documentation was checked
for this version. The provider therefore VERIFIES every option it wants to use against the
locally installed ``codex exec --help`` (a local, non-billable call) and reports
``unsupported_cli`` instead of guessing when an option is absent. It always asks for a
read-only sandbox and never for an approval/sandbox bypass.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from ..security import redact
from .base import AgentError, AgentProvider, AgentRequest, AgentResult, run_cli
from .claude_code import AUTH_PATTERNS, MODEL_PATTERNS
from .prompts import PROPOSAL_SCHEMA, build_prompt

WANTED_OPTIONS = ('--output-schema', '--output-last-message', '--sandbox')


class CodexProvider(AgentProvider):
    name = 'codex'

    def executable(self):
        if self.settings.cli_path:
            path = Path(self.settings.cli_path)
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which('codex')

    def available(self):
        path = self.executable()
        return dict(provider=self.name, available=path is not None, executable=path,
                    reason=None if path else '`codex` is not on the backend process PATH')

    def help_text(self, executable):
        try:
            done = subprocess.run([executable, 'exec', '--help'], capture_output=True, text=True, timeout=30,
                                  stdin=subprocess.DEVNULL, shell=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AgentError('unsupported_cli', f'`codex exec --help` could not be run: {exc}')
        return done.stdout + done.stderr

    def propose(self, request: AgentRequest) -> AgentResult:
        request.validate()
        executable = self.executable()
        if executable is None:
            raise AgentError('cli_missing', '`codex` was not found on the PATH of the BACKEND process')
        help_text = self.help_text(executable)
        missing = [option for option in WANTED_OPTIONS if option not in help_text]
        if missing:
            raise AgentError('unsupported_cli', f'The installed codex CLI does not list {missing} under `codex exec '
                                                '--help`; structured proposals cannot be requested safely.')
        scratch = Path(tempfile.mkdtemp(prefix='gator-agent-'))
        try:
            schema_file, answer_file = scratch / 'schema.json', scratch / 'answer.json'
            schema_file.write_text(json.dumps(PROPOSAL_SCHEMA))
            argv = [executable, 'exec', '--sandbox', 'read-only', '--output-schema', str(schema_file),
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
                                           timeout=self.settings.timeout_seconds, request_id=request.request_id)
            logs = [dict(type='stdout', text=redact(line, 500)) for line in stdout.splitlines()[-200:]]
            excerpt = redact(stderr.strip(), 2000)
            if code != 0:
                if AUTH_PATTERNS.search(stderr + stdout):
                    raise AgentError('unauthenticated', excerpt)
                if MODEL_PATTERNS.search(stderr + stdout):
                    raise AgentError('model_unavailable', excerpt)
                raise AgentError('nonzero_exit', f'exit status {code}', exit_code=code, stderr=excerpt)
            if not answer_file.is_file():
                raise AgentError('no_structured_output', 'codex wrote no final message file')
            try:
                structured = json.loads(answer_file.read_text())
            except json.JSONDecodeError:
                raise AgentError('incomplete_output', 'The final message is not valid JSON')
            if not isinstance(structured, dict):
                raise AgentError('no_structured_output', 'The final message is not a JSON object')
            return AgentResult(request.request_id, self.name, 'codex', structured, logs,
                               dict(exit_code=code, note='Audit metadata only; never RL state.'))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
