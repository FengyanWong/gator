"""Audit the actual JSON files handed to both Codex entry points, without launching a CLI."""
import json
from uuid import uuid4

import pytest

from analog_optimizer.search.llm import output_schema
from gator_workbench.agents.base import AgentError, AgentRequest, AgentSettings
from gator_workbench.agents.codex import CodexProvider
from gator_workbench.agents.codex_schema import CODEX_PROPOSAL_SCHEMA
from gator_workbench.agents.prompts import PROPOSAL_SCHEMA
from gator_workbench.agents.sizing import SizingCliClient
from gator_workbench.schema import SearchSettings
from gator_workbench.agents.proposals import ProposalRejected, normalize
from helpers import make_config


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
    assert captured == [CODEX_PROPOSAL_SCHEMA]
    assert strict_schema_issues(captured[0]) == []


def test_agent_tab_codex_schema_is_strict():
    assert strict_schema_issues(CODEX_PROPOSAL_SCHEMA) == []
    # The other providers and manual import retain their existing shared contract.
    assert PROPOSAL_SCHEMA['properties']['patch']['items']['properties']['value'] == {'type': 'object'}


def codex_reply(monkeypatch, request, reply):
    """Intercept the real provider's CLI boundary: check the sent schema and return
    a strict-format answer through its output file, with no model call."""
    from gator_workbench.agents import codex
    monkeypatch.setattr(CodexProvider, 'executable', lambda self: '/never-executed/codex')
    monkeypatch.setattr(CodexProvider, 'help_text', lambda *args: '--output-schema --output-last-message --sandbox')

    def complete(argv, **kwargs):
        from pathlib import Path
        assert strict_schema_issues(json.loads(Path(argv[argv.index('--output-schema') + 1]).read_text())) == []
        assert 'COMPLETE row encoded as JSON text' in kwargs['stdin_text']
        assert argv[argv.index('--sandbox') + 1] == 'read-only'
        Path(argv[argv.index('--output-last-message') + 1]).write_text(json.dumps(reply))
        return 0, '', ''

    monkeypatch.setattr(codex, 'run_cli', complete)
    return CodexProvider(AgentSettings(provider='codex')).propose(request)


def strict_reply(kind, **fields):
    return dict(dict(kind=kind, reasoning='Fixture', patch=[], warnings=[], unresolved=[], checklist=None,
                     suggestions=None, encoder_ideas=None, setup=None), **fields)


def test_codex_strict_reply_decodes_rows_and_setup_before_normal_validation(tmp_path, monkeypatch):
    config = make_config(tmp_path).model_dump(mode='json')
    request = AgentRequest('virtuoso_setup', 'Offline fixture', config, None, copy=dict(library='fixture', cell='copy'))
    row = dict(config['parameters'][0], notes='Preserve JSON text: {"a":1}')
    setup = dict(analyses={'tran': {'stop': '40n'}}, variables={'vdd': '1.0'}, initial_conditions={'out': '0'},
                 bindings=[dict(cell='copy', instance='M1', parameter='w', variable='width')])
    reply = strict_reply(request.kind, patch=[dict(op='replace', section='parameters', key=row['variable_id'],
                                                  value=json.dumps(row), basis=None)],
                         setup={key: json.dumps(value) if isinstance(value, dict) else value for key, value in setup.items()})
    result = codex_reply(monkeypatch, request, reply)
    assert result.structured_output['patch'][0]['value'] == row
    clean = normalize(request, result)
    assert clean['setup'] == setup and clean['patch'][0]['value'] == row
    # JSON encoding cannot smuggle a forbidden row field or widen a request's scope.
    reply['patch'][0]['value'] = json.dumps(dict(row, allowed_tools=['Bash']))
    with pytest.raises(ProposalRejected, match='backend validation'):
        normalize(request, codex_reply(monkeypatch, request, reply))
    reply['patch'][0]['value'] = json.dumps(row)
    restricted = AgentRequest('measurements', 'Offline fixture', config, None)
    with pytest.raises(ProposalRejected, match='backend validation'):
        normalize(restricted, codex_reply(monkeypatch, restricted, reply))


@pytest.mark.parametrize('value', ['{broken', '[]', '1', 'null'])
def test_codex_malformed_encoded_row_is_reported_as_schema_failure(monkeypatch, value):
    request = AgentRequest('parameters', 'Offline fixture', {}, None)
    reply = strict_reply(request.kind, patch=[dict(op='add', section='parameters', key='w', value=value, basis=None)])
    with pytest.raises(AgentError) as error:
        codex_reply(monkeypatch, request, reply)
    assert error.value.code == 'schema_failure'


def test_codex_nullable_remove_and_advisory_fields_keep_their_contract(monkeypatch):
    request = AgentRequest('readiness', 'Offline fixture', {}, None)
    reply = strict_reply(request.kind, patch=[dict(op='remove', section='parameters', key='w', value=None, basis=None)],
                         checklist=[dict(item='Bounds', status='missing', who='you', action='Set bounds', basis=None)])
    clean = normalize(request, codex_reply(monkeypatch, request, reply))
    assert clean['patch'][0]['value'] is None
    assert clean['checklist'][0]['basis'] == '' and clean['setup'] is None


def test_strict_audit_checks_nested_union_and_dictionary_values():
    broken = {'anyOf': [{'type': 'array', 'items': {'type': 'object',
        'properties': {'value': {'type': 'number'}}, 'required': []}}]}
    assert strict_schema_issues(broken) == [
        '$/anyOf/0/items: additionalProperties must be false',
        '$/anyOf/0/items: required must list every property exactly once']

