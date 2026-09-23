"""Interchangeable agent providers. They ASSIST configuration preparation and diagnostics; they are
never in the SAC inner loop, and every manual workflow works without them."""
from __future__ import annotations

import shutil

from .base import (AgentError, AgentProvider, AgentRequest, AgentResult, AgentSettings, ERROR_CODES, REGISTRY,
                   REQUEST_KINDS, TOOL_KINDS)
from .claude_code import ClaudeCodeProvider
from .codex import CodexProvider
from .disabled import DisabledProvider
from .proposals import ProposalRejected, ProposalStore

PROVIDERS = {'claude_code': ClaudeCodeProvider, 'codex': CodexProvider, 'disabled': DisabledProvider}


def default_provider_name(previous=None) -> str:
    """Honour an existing selection. With none, prefer Claude Code when its CLI is available;
    otherwise Disabled (the UI then lists what is and is not available)."""
    if previous in PROVIDERS:
        return previous
    return 'claude_code' if shutil.which('claude') else 'disabled'


def make_provider(settings: AgentSettings) -> AgentProvider:
    if settings.provider not in PROVIDERS:
        raise AgentError('invalid_request', f'Unknown provider {settings.provider!r}; available: {sorted(PROVIDERS)}')
    return PROVIDERS[settings.provider](settings)


def availability() -> list:
    return [PROVIDERS[name](AgentSettings(provider=name)).available() for name in PROVIDERS]


__all__ = ['AgentError', 'AgentProvider', 'AgentRequest', 'AgentResult', 'AgentSettings', 'ERROR_CODES', 'REGISTRY',
           'REQUEST_KINDS', 'TOOL_KINDS', 'ClaudeCodeProvider', 'CodexProvider', 'DisabledProvider', 'ProposalRejected',
           'ProposalStore', 'PROVIDERS', 'default_provider_name', 'make_provider', 'availability']
