"""The Agent window (record 7.226; a tab until 7.253): Claude Code or Codex in a terminal window of its own (agent_cli.py), and the free
"What's missing?" checklist (readiness.py)."""
from __future__ import annotations
from fastapi import FastAPI
from .. import agent_cli
from .models import ConfigBody, OpenCliBody
from .support import fail
from .context import ApiContext


def register(app: FastAPI, context: ApiContext):
    """Register the routes for agent-CLI availability and launch, and for the run start checklist."""
    @app.get('/api/agent/clis')
    def clis():
        """The folder the two CLIs open in, and whether each is installed. Free: no CLI is run, nothing is sent."""
        return agent_cli.availability()

    @app.post('/api/agent/open')
    def open_cli(body: OpenCliBody):
        """A terminal window of its own with the CLI in the workbench's folder, started as you start it yourself (your
        settings, your account, your history). The workbench sends it nothing and does not wait for it."""
        try:
            return agent_cli.open_cli(body.cli)
        except agent_cli.LaunchError as exc:
            fail(409, exc, code='cli_not_opened', command=exc.command)

    @app.post('/api/agent/readiness')
    def readiness(body: ConfigBody):
        """What is still missing before this run can start. Computed here: no agent is called and nothing is probed."""
        config, runtime, blocked = context.load_config(body.config)
        return context.run_readiness(config, runtime, blocked)
