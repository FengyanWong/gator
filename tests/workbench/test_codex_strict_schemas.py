"""Audit the actual JSON files handed to both Codex entry points, without launching a CLI."""
import json
from uuid import uuid4

import pytest

from analog_optimizer.search.llm import output_schema
from gator_workbench.agents.base import AgentRequest, AgentSettings
from gator_workbench.agents.codex import CodexProvider
from gator_workbench.agents.prompts import PROPOSAL_SCHEMA
from gator_workbench.agents.sizing import SizingCliClient
from gator_workbench.schema import SearchSettings


def strict_schema_issues(schema, path='$'):
    """All branches, arrays, definitions and schema-valued additionalProperties are inspected."""
    issues = []
    if isinstance(schema, dict):
        kind = schema.get('type')
        if kind == 'object' or isinstance(kind, list) and 'object' in kind or 'properties' in schema:
            if schema.get('additionalProperties') is not False:
                issues.append(path + ': additionalProperties must be false')
            required = schema.get('required')
            properties = schema.get('properties', {})
            if not isinstance(required, list) or len(required) != len(set(required)) or set(required) != set(properties):
                issues.append(path + ': required must list every property exactly once')
        for key, value in schema.items():
            issues.extend(strict_schema_issues(value, path + '/' + key))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            issues.extend(strict_schema_issues(value, path + '/' + str(index)))
    return issues


@pytest.mark.parametrize('expected', [(), ('FOML', 'FOMS', 'Power', 'GBW')])
def test_sizing_codex_sent_schema_is_strict(monkeypatch, expected):
    captured = []
    monkeypatch.setattr(CodexProvider, 'executable', lambda self: '/never-executed/codex')
    monkeypatch.setattr(CodexProvider, 'help_text', lambda *args: '--ignore-user-config')

    def intercept(self, executable, help_text, schema_file, answer_file, events=None):
        captured.append(json.loads(schema_file.read_text()))
        raise StopIteration('Intercepted before any process launch')

    monkeypatch.setattr(CodexProvider, 'build_argv', intercept)
    client = SizingCliClient('strict-schema-' + uuid4().hex, SearchSettings(method='llm', provider='codex', max_llm_calls=1))
    try:
        with pytest.raises(StopIteration):
            client.complete('Offline schema audit', output_schema(['W_M1', 'M_M2'], 4, expected))
        assert len(captured) == 1
        assert strict_schema_issues(captured[0]) == []
    finally:
        client.cwd.rmdir()


def test_agent_tab_codex_sent_schema_is_the_audited_schema(monkeypatch):
    captured = []
    monkeypatch.setattr(CodexProvider, 'executable', lambda self: '/never-executed/codex')
    monkeypatch.setattr(CodexProvider, 'help_text', lambda *args: '--output-schema --output-last-message --sandbox')

    def intercept(self, executable, help_text, schema_file, answer_file, events=None):
        captured.append(json.loads(schema_file.read_text()))
        raise StopIteration('Intercepted before any process launch')

    monkeypatch.setattr(CodexProvider, 'build_argv', intercept)
    provider = CodexProvider(AgentSettings(provider='codex'))
    with pytest.raises(StopIteration):
        provider.propose(AgentRequest('parameters', 'Offline schema audit', {}, None))
    assert captured == [PROPOSAL_SCHEMA]
    assert len(strict_schema_issues(captured[0])) == 16


@pytest.mark.xfail(strict=True, reason='Known Agent-tab proposal schema incompatibilities; user requested audit only, no schema change')
def test_agent_tab_codex_schema_is_strict():
    assert strict_schema_issues(PROPOSAL_SCHEMA) == []


def test_strict_audit_checks_nested_union_and_dictionary_values():
    broken = {'anyOf': [{'type': 'array', 'items': {'type': 'object',
        'properties': {'value': {'type': 'number'}}, 'required': []}}]}
    assert strict_schema_issues(broken) == [
        '$/anyOf/0/items: additionalProperties must be false',
        '$/anyOf/0/items: required must list every property exactly once']

