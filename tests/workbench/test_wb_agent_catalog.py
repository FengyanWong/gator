"""The model / effort lists the Agent tab offers, and what each provider does with a choice.
Fake CLI fixtures only: no real Claude/Codex session is started and no model is called."""
import json

from fastapi.testclient import TestClient
import pytest

from gator_workbench import agents, runs
from gator_workbench.agents import AgentError, AgentSettings, ClaudeCodeProvider, CodexProvider, catalog
from helpers import cli, workbench_app
from test_wb_agents import request


def test_every_listed_choice_is_one_the_settings_accept():
    assert set(catalog.CATALOG) == set(agents.PROVIDERS)
    for provider, entry in catalog.CATALOG.items():
        ids = [m['id'] for m in entry['models']]
        assert len(ids) == len(set(ids))
        for model in entry['models']:
            assert set(model['efforts']) <= set(entry['efforts']) and model['label'] and model['note']
            for effort in [None, *model['efforts']]:
                AgentSettings(provider=provider, model=model['id'], effort=effort).validate()
    assert catalog.CATALOG['codex']['caveat']           # never installed here: the list must say it is unexercised
    assert catalog.CATALOG['claude_code']['verified'] and catalog.CATALOG['claude_code']['source'].startswith('https://')


def test_effort_levels_differ_per_provider():
    AgentSettings(provider='claude_code', effort='max').validate()
    AgentSettings(provider='codex', effort='max').validate()
    for provider, effort in (('claude_code', 'minimal'), ('codex', 'minimal'), ('claude_code', 'ludicrous')):
        with pytest.raises(AgentError) as error:
            AgentSettings(provider=provider, effort=effort).validate()
        assert error.value.code == 'invalid_request' and provider in error.value.detail
    AgentSettings(provider='disabled', effort='max').validate()          # a kept level never blocks switching it off
    assert catalog.supports_effort('claude_code', 'sonnet') and not catalog.supports_effort('claude_code', 'haiku')
    assert catalog.supports_effort('claude_code', None) and catalog.supports_effort('claude_code', 'some-future-model')


def test_claude_gets_no_effort_flag_for_a_model_that_takes_none(tmp_path, cli):
    record = cli('success')
    ClaudeCodeProvider(AgentSettings(provider='claude_code', model='haiku', effort='high')).propose(request(tmp_path))
    argv = json.loads(record.read_text())['argv']
    assert argv[argv.index('--model') + 1] == 'haiku' and '--effort' not in argv
    ClaudeCodeProvider(AgentSettings(provider='claude_code', model='sonnet', effort='low')).propose(request(tmp_path))
    argv = json.loads(record.read_text())['argv']
    assert argv[argv.index('--effort') + 1] == 'low'
    ClaudeCodeProvider(AgentSettings(provider='claude_code', effort='medium')).propose(request(tmp_path))
    argv = json.loads(record.read_text())['argv']                        # CLI default model: unknown here, passed on
    assert '--model' not in argv and argv[argv.index('--effort') + 1] == 'medium'


def test_codex_effort_is_a_config_override_and_needs_a_cli_that_lists_it(tmp_path, cli):
    record = cli('success')
    CodexProvider(AgentSettings(provider='codex', model='gpt-5.6-sol', effort='high')).propose(request(tmp_path))
    argv = json.loads(record.read_text())['argv']
    assert argv[argv.index('--config') + 1] == 'model_reasoning_effort="high"' and argv[-1] == '-'
    assert argv[argv.index('--model') + 1] == 'gpt-5.6-sol'
    CodexProvider(AgentSettings(provider='codex')).propose(request(tmp_path))
    assert '--config' not in json.loads(record.read_text())['argv']      # nothing chosen, nothing passed
    cli('codex_without_config')
    with pytest.raises(AgentError) as error:
        CodexProvider(AgentSettings(provider='codex', effort='high')).propose(request(tmp_path))
    assert error.value.code == 'unsupported_cli' and '--config' in error.value.detail


def test_cli_default_reads_only_model_and_effort_keys(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    monkeypatch.delenv('ANTHROPIC_MODEL', raising=False)
    monkeypatch.delenv('CLAUDE_CODE_EFFORT_LEVEL', raising=False)
    assert catalog.claude_cli_default()['model'] is None and 'account default' in catalog.claude_cli_default()['note']
    (tmp_path / 'settings.json').write_text(json.dumps(dict(
        model='fable', effortLevel='xhigh', modelSettings={'claude-fable-5-1': dict(effortLevel='high')},
        env=dict(ANTHROPIC_AUTH_TOKEN='secret-token-value'), apiKeyHelper='/bin/secret')))
    found = catalog.claude_cli_default()
    assert (found['model'], found['effort']) == ('fable', 'high')        # the per-model level overrides the general one
    assert 'secret' not in json.dumps(found) and set(found) == {'model', 'effort', 'efforts_by_model', 'note'}
    by_model = found['efforts_by_model']                                 # "CLI default" effort differs by model
    assert (by_model['fable'], by_model['claude-fable-5-1'], by_model['sonnet'], by_model['haiku']) == ('high', 'high', 'xhigh', None)
    (tmp_path / 'settings.json').write_text(json.dumps(dict(model='sonnet', effortLevel='xhigh')))
    assert (catalog.claude_cli_default()['model'], catalog.claude_cli_default()['effort']) == ('sonnet', 'xhigh')
    monkeypatch.setenv('ANTHROPIC_MODEL', 'opus')
    monkeypatch.setenv('CLAUDE_CODE_EFFORT_LEVEL', 'low')
    assert (catalog.claude_cli_default()['model'], catalog.claude_cli_default()['effort']) == ('opus', 'low')
    (tmp_path / 'settings.json').write_text('{ not json')
    monkeypatch.delenv('ANTHROPIC_MODEL')
    monkeypatch.delenv('CLAUDE_CODE_EFFORT_LEVEL')
    assert catalog.claude_cli_default()['model'] is None                 # unreadable settings are not an error


@pytest.fixture
def client(tmp_path, monkeypatch, cli):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'no-claude-settings'))
    return TestClient(workbench_app(tmp_path))


def test_settings_endpoint_serves_the_lists_and_survives_a_level_from_the_other_provider(client):
    settings = client.get('/api/agent/settings').json()
    listing = settings['catalog']
    assert set(listing) == {'claude_code', 'codex', 'disabled'} and listing['disabled']['models'] == []
    assert [m['id'] for m in listing['claude_code']['models']][:4] == ['fable', 'opus', 'sonnet', 'haiku']
    assert listing['claude_code']['cli_default'] == catalog.claude_cli_default()
    assert listing['codex']['efforts'] == list(catalog.CODEX_EFFORTS)
    saved = client.put('/api/agent/settings', json=dict(provider='claude_code', model='sonnet', effort='low'))
    assert saved.status_code == 200
    again = client.get('/api/agent/settings').json()
    assert (again['model'], again['effort']) == ('sonnet', 'low')
    assert client.put('/api/agent/settings', json=dict(provider='codex', effort='max')).status_code == 200
    assert client.put('/api/agent/settings', json=dict(provider='codex', effort='minimal')).status_code == 422
    # A file edited by hand (or kept from the other provider) must not take the Agent tab down with a 500.
    runs.save_settings(agent=dict(provider='codex', model=None, effort='minimal'))
    kept = client.get('/api/agent/settings')
    assert kept.status_code == 200 and kept.json()['effort'] is None and kept.json()['provider'] == 'codex'
