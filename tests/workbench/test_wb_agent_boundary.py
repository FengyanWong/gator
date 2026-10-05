"""The Agent tab agent's tool boundary (record 7.186): every request starts with a named list of built-in tools, so a tool
the CLI adds in a later release is not reachable by default; the user's claude.ai documents may be read, never changed.

Checked once on the real claude 2.1.278 at no cost (unknown model name: the CLI lists the session's tools, the API refuses
the model): the lists below are what each kind got. These tests pin the command line that produced them.
"""
from __future__ import annotations

import pytest

from gator_workbench.agents import AgentRequest, AgentSettings, ClaudeCodeProvider
from gator_workbench.agents import base, tools as catalog
from gator_workbench.agents.claude_code import BUILTIN_TOOLS, CLAUDE_DOCS_READ, CLAUDE_DOCS_WRITE, WEB_TOOLS

# Built-in tools that reach outside a request or run something: messages to the user's other Claude sessions, routines on
# claude.ai, notifications, artifacts, workflows, scheduled prompts, shells, edits. None may ever be in `--tools`.
OUTWARD = ('SendMessage', 'ListAgents', 'RemoteTrigger', 'PushNotification', 'SendUserFile', 'CronCreate', 'CronDelete',
           'CronList', 'Artifact', 'ArtifactComments', 'ArtifactData', 'Workflow', 'Monitor', 'Skill', 'TaskStop',
           'DesignSync', 'EnterWorktree', 'ExitWorktree', 'Agent', 'Task', 'Bash', 'PowerShell', 'Edit', 'Write',
           'MultiEdit', 'NotebookEdit', 'ShareOnboardingGuide', 'AskUserQuestion')


def value(argv, flag):
    assert argv.count(flag) == 1, f'{flag} must appear exactly once'
    return argv[argv.index(flag) + 1]


def request(kind, **kwargs):
    extra = {}
    if kind in ('virtuoso_setup', 'virtuoso_work'):
        extra['copy'] = dict(copy='lib/cell')
    if kind == 'run_review':
        extra['results'] = dict(run='x')
    return AgentRequest(kind=kind, user_prompt='x', config={}, circuit_summary=None, **extra, **kwargs)


def argv_for(kind, settings=None, **kwargs):
    provider = ClaudeCodeProvider(settings or AgentSettings(provider='claude_code'))
    if kind == 'virtuoso_work':
        kwargs.setdefault('tools', tuple(catalog.granted('virtuoso_work')))
    return provider.build_argv('claude', request(kind, **kwargs), mcp_config='{"mcpServers":{}}')


@pytest.mark.parametrize('kind', base.REQUEST_KINDS)
def test_every_kind_starts_with_only_the_named_builtin_tools(kind):
    argv = argv_for(kind)
    named = value(argv, '--tools').split(',')
    assert named == list(BUILTIN_TOOLS)
    assert not set(named) & set(OUTWARD)


def test_an_online_settings_review_adds_exactly_the_two_web_tools():
    argv = argv_for('settings_review', web=True, web_domains=('arxiv.org',))
    named = value(argv, '--tools').split(',')
    assert named == list(BUILTIN_TOOLS + WEB_TOOLS) and not set(named) & set(OUTWARD)
    allowed = value(argv, '--allowedTools').split(',')
    assert 'WebSearch' in allowed and 'WebFetch(domain:arxiv.org)' in allowed and 'WebFetch' not in allowed


def test_web_tools_stay_off_for_every_other_kind_even_when_asked():
    for kind in base.REQUEST_KINDS:
        if kind == 'settings_review':
            continue
        named = value(argv_for(kind, web=True, web_domains=('arxiv.org',)), '--tools').split(',')
        assert not set(named) & set(WEB_TOOLS)


@pytest.mark.parametrize('kind', base.REQUEST_KINDS)
def test_claude_documents_are_readable_and_never_writable(kind):
    argv = argv_for(kind)
    allowed = value(argv, '--allowedTools').split(',')
    denied = value(argv, '--disallowedTools').split(',')
    assert set(CLAUDE_DOCS_READ) <= set(allowed)
    assert set(CLAUDE_DOCS_WRITE) <= set(denied) and not set(CLAUDE_DOCS_WRITE) & set(allowed)
    assert {name.rsplit('__', 1)[1] for name in CLAUDE_DOCS_READ} == {'read', 'query', 'guide'}


def test_virtuoso_work_keeps_its_virtuoso_tools_and_the_search_that_loads_them():
    argv = argv_for('virtuoso_work')
    allowed = value(argv, '--allowedTools').split(',')
    assert allowed[-len(catalog.granted('virtuoso_work')):] == catalog.mcp_names(catalog.granted('virtuoso_work'))
    assert 'ToolSearch' in value(argv, '--tools').split(',') and '--strict-mcp-config' in argv


def test_settings_cannot_add_a_builtin_tool():
    from gator_workbench.agents import AgentError
    wide = AgentSettings(provider='claude_code', allowed_tools=('SendMessage', 'RemoteTrigger'))
    with pytest.raises(AgentError):
        wide.validate()                                    # a settings file naming another tool is refused...
    with pytest.raises(AgentError):
        ClaudeCodeProvider(wide)                           # ...before any command line exists


def test_sizing_calls_start_with_no_builtin_tool_and_no_documents():
    provider = ClaudeCodeProvider(AgentSettings(provider='claude_code'))
    argv = provider.build_argv('claude', request('parameters'), live=True, schema={'type': 'object'}, builtin_tools=(),
                               claude_docs=False)
    assert value(argv, '--tools') == ''
    assert '--allowedTools' not in argv
    assert set(CLAUDE_DOCS_WRITE) <= set(value(argv, '--disallowedTools').split(','))
