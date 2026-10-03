"""The model / effort lists the Agent tab offers, and what each provider does with a choice.
Fake CLI fixtures only: no real Claude/Codex session is started and no model is called."""
import json
import os

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
    claude = {m['id']: m['efforts'] for m in catalog.CATALOG['claude_code']['models']}       # the documented levels per model
    assert claude['claude-opus-4-6'] == claude['claude-sonnet-4-6'] == ['low', 'medium', 'high', 'max']
    assert claude['claude-sonnet-4-5'] == [] and claude['claude-opus-4-8'] == list(catalog.CLAUDE_EFFORTS)


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


def _codex_file(path, models):
    """A stand-in for the file the Codex app keeps (models_cache.json), with an account part that must never be served."""
    path.write_text(json.dumps(dict(fetched_at='2026-10-03T15:50:41Z', etag='W/"x"', client_version='0.160.0',
                                    identity=dict(email='someone@example.com'), models=models)), encoding='utf8')
    return path


def _model(slug, priority, efforts, visibility='list', **extra):
    return dict(slug=slug, display_name=slug.upper(), description=f'{slug} described.', visibility=visibility,
                priority=priority, default_reasoning_level=efforts[0] if efforts else None,
                supported_reasoning_levels=[dict(effort=e, description='...') for e in efforts], **extra)


def test_codex_list_comes_from_the_codex_app_file(tmp_path, monkeypatch):
    cache = _codex_file(tmp_path / 'models_cache.json', [
        _model('gpt-old', 13, ['low', 'medium', 'high', 'xhigh'], upgrade=dict(
            model='gpt-new', retirement_at='2026-10-14T19:00:00Z', migration_markdown='GPT-old retires on October 14, 2026.')),
        _model('gpt-new', 1, ['low', 'medium', 'high', 'xhigh', 'max', 'ultra', 'turbo']),
        _model('gpt-hidden', 2, ['low'], visibility='hide'),
        _model('-rf', 3, ['low']), _model('two\nlines', 4, ['low']), _model('gpt-new', 5, ['low']), 'not a model'])
    monkeypatch.setenv(catalog.CODEX_CACHE_ENV, str(cache))
    entry = catalog.codex_entry(search=True)
    assert (entry['origin'], entry['cache_file'], entry['verified']) == ('codex_app', str(cache), '2026-10-03')
    assert [m['id'] for m in entry['models']] == ['gpt-new', 'gpt-old']    # the app's order; hidden, unsafe, repeated left out
    old = entry['models'][1]
    assert old['label'] == 'gpt-old (retires 2026-10-14)' and 'retires on October 14' in old['note']
    assert 'default effort: low' in old['note'] and old['efforts'] == ['low', 'medium', 'high', 'xhigh']
    assert 'someone@example.com' not in json.dumps(entry)
    # A level only the app lists becomes valid for Codex, and each model keeps its own levels (sizing drops the rest).
    assert 'turbo' in catalog.efforts_for('codex') and 'turbo' not in catalog.efforts_for('claude_code')
    AgentSettings(provider='codex', model='gpt-new', effort='turbo').validate()
    assert catalog.model_entry('codex', 'gpt-6-astra') is None           # the hand table is not mixed in
    _codex_file(cache, [_model('gpt-newer', 1, ['low'])])                # the app refreshed its file: read again
    assert [m['id'] for m in catalog.codex_entry()['models']] == ['gpt-newer']


def test_codex_list_falls_back_to_the_hand_table_and_says_why(tmp_path, monkeypatch):
    entry = catalog.codex_entry(search=True)
    assert entry['origin'] == 'hand_table' and 'switched off' in entry['cache_note']      # the suite never reads the user's
    monkeypatch.setenv(catalog.CODEX_CACHE_ENV, str(tmp_path / 'missing.json'))
    entry = catalog.codex_entry(search=True)
    assert entry['models'] == catalog.CATALOG['codex']['models'] and 'not found' in entry['cache_note']
    broken = tmp_path / 'broken.json'
    monkeypatch.setenv(catalog.CODEX_CACHE_ENV, str(broken))
    for text in ('{ not json', json.dumps(dict(models='none')), json.dumps(dict(models=[_model('gpt-x', 1, ['low'], 'hide')]))):
        broken.write_text(text)
        entry = catalog.codex_entry(search=True)
        assert entry['origin'] == 'hand_table' and str(broken) in entry['cache_note'], text
    assert catalog.efforts_for('codex') == catalog.CODEX_EFFORTS


def test_codex_file_is_looked_for_in_the_codex_homes_and_the_newest_wins(tmp_path, monkeypatch):
    home, windows = tmp_path / 'home', tmp_path / 'Users'
    monkeypatch.delenv(catalog.CODEX_CACHE_ENV)
    monkeypatch.delenv('CODEX_HOME', raising=False)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(catalog, '_WINDOWS_USERS', windows)              # from WSL: C:\Users\<name>\.codex of the desktop app
    assert 'not found' in catalog.codex_entry(search=True)['cache_note']
    (home / '.codex').mkdir(parents=True)
    (windows / 'someone' / '.codex').mkdir(parents=True)
    linux = _codex_file(home / '.codex' / 'models_cache.json', [_model('gpt-linux', 1, ['low'])])
    app = _codex_file(windows / 'someone' / '.codex' / 'models_cache.json', [_model('gpt-app', 1, ['low'])])
    os.utime(linux, (1_000_000_000, 1_000_000_000))
    assert [m['id'] for m in catalog.codex_entry(search=True)['models']] == ['gpt-app']
    os.utime(app, (900_000_000, 900_000_000))
    assert [m['id'] for m in catalog.codex_entry(search=True)['models']] == ['gpt-linux']
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'elsewhere'))
    (tmp_path / 'elsewhere').mkdir()
    _codex_file(tmp_path / 'elsewhere' / 'models_cache.json', [_model('gpt-codex-home', 1, ['low'])])
    assert [m['id'] for m in catalog.codex_entry()['models']] == ['gpt-codex-home']      # a changed place is searched again


def test_settings_endpoint_serves_the_codex_app_list(client, tmp_path, monkeypatch):
    cache = _codex_file(tmp_path / 'models_cache.json', [_model('gpt-new', 1, ['low', 'turbo']), _model('gpt-luna', 2, ['low'])])
    monkeypatch.setenv(catalog.CODEX_CACHE_ENV, str(cache))
    codex = client.get('/api/agent/settings').json()['catalog']['codex']
    assert codex['origin'] == 'codex_app' and [m['id'] for m in codex['models']] == ['gpt-new', 'gpt-luna']
    assert codex['fetched_at'] == '2026-10-03T15:50:41Z' and 'identity' not in json.dumps(codex)
    assert client.put('/api/agent/settings', json=dict(provider='codex', model='gpt-new', effort='turbo')).status_code == 200
    _codex_file(cache, [_model('gpt-newer', 1, ['low'])])                # "Re-read list" is the same GET
    assert [m['id'] for m in client.get('/api/agent/settings').json()['catalog']['codex']['models']] == ['gpt-newer']
