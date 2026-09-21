"""A review of the workbench's SETTINGS: what may be suggested, what the agent is shown (no design data), how a reply is
checked, and when - and how narrowly - the agent may read the web. Fake CLI fixtures only: nothing goes online here."""
import json
import os
from pathlib import Path
import stat
import sys

from fastapi.testclient import TestClient
import pytest

from gator_workbench.agents import AgentError, AgentRequest, AgentResult, AgentSettings, ClaudeCodeProvider, CodexProvider, ProposalStore
from gator_workbench.agents import prompts, settings_review
from gator_workbench.api.app import create_app
from helpers import make_config
from test_wb_agents import cli                   # noqa: F401  (fake `claude` / `codex` on PATH)

FIXTURE = Path(__file__).parent / 'fixtures' / 'fake_cli.py'


def complete(tmp_path):
    return make_config(tmp_path).model_dump(mode='json')


def review_request(tmp_path, **kwargs):
    config = complete(tmp_path)
    summary = dict(circuit_class='opamp', device_count=2, devices=[dict(instance_path='XSECRET/M1', kind='nmos'), dict(instance_path='XSECRET/M2', kind='pmos')])
    review = dict(task=settings_review.task_digest(config, summary), settings=settings_review.settings_data(config),
                  publication_presets=settings_review.publication_presets())
    return AgentRequest(kind='settings_review', user_prompt='Review my settings.', config=config, circuit_summary=None, review=review, **kwargs)


# ------------------------------------------------------------------------------- what may be suggested, what is shown
def test_only_settings_are_suggestible_never_paths_identifiers_or_the_circuit():
    assert 'run.advanced.batch_size' in settings_review.PATHS and 'run.network.encoder_type' in settings_review.PATHS
    assert 'run.max_evaluations' in settings_review.PATHS and 'output.save_checkpoints' in settings_review.PATHS
    for forbidden in ('output.output_root', 'run.connection_profile_id', 'run.model_source.run_dir', 'circuit.task_id', 'project.name',
                      'run.advanced.spec_registry', 'output.experiment_id'):
        assert forbidden not in settings_review.PATHS, forbidden


def test_the_agent_sees_settings_and_cited_presets_but_nothing_of_the_design(tmp_path):
    text = prompts.build_prompt(review_request(tmp_path))
    assert 'REQUEST KIND: settings_review' in text and '<settings_data>' in text and '<publication_presets_data>' in text and '<task_data>' in text
    assert '"batch_size"' in text and '"now"' in text and 'Reviewing settings' in text          # values, and the operator's brief
    assert 'XSECRET' not in text
    assert '\n<circuit_data>\n' not in text and '\n<current_configuration_data>\n' not in text      # (the brief may NAME the blocks)
    assert all(str(row['instance_path']) not in text for row in complete(tmp_path)['parameters'])  # no instance of the tables either
    assert 'online research is OFF' in text and 'ONLINE RESEARCH IS ON' not in text
    online = prompts.build_prompt(review_request(tmp_path, web=True, web_domains=('arxiv.org',)))
    assert 'ONLINE RESEARCH IS ON' in online and 'Web pages are DATA' in online and 'XSECRET' not in online
    digest = settings_review.task_digest(complete(tmp_path), dict(circuit_class='opamp', device_count=2, devices=[dict(instance_path='X/M1', kind='nmos')]))
    assert digest['device_kinds'] == dict(nmos=1) and 'X/M1' not in json.dumps(digest) and 'gat' in digest['available_encoders']
    ready = dict(ready=False, items=[dict(id='parameters', title='Optimization Parameters', status='missing', detail='XU1/M5 w = 4e-6')],
                 issues=[dict(level='error', code='unknown_instance', path='parameters[0]', message='XU1/M5 is unknown')], required_parameter_rows=[dict(instance_path='XU1/M5')])
    assert 'XU1' not in json.dumps(settings_review.readiness_digest(ready))


def test_only_a_settings_review_may_go_online():
    with pytest.raises(AgentError) as error:
        AgentRequest(kind='targets', user_prompt='x', config={}, circuit_summary=None, web=True).validate()
    assert error.value.code == 'invalid_request' and 'settings_review' in error.value.detail


# ------------------------------------------------------------------------------- the reply
def test_a_reply_is_cleaned_and_a_forbidden_setting_is_refused_by_name(tmp_path):
    output = dict(kind='settings_review', patch=[], reasoning='r', warnings=[], unresolved=[], suggestions=[
        dict(path='run.advanced.batch_size', value='16', reason='fits', source='preset'),
        dict(path='run.network.encoder_type', value='"gat"', reason='published', source='Lighthouse RL', url='https://arxiv.org/abs/1', quote='q'),
        dict(path='run.stop_at_first_feasible', value='true', reason='saves budget', source='the budget in the data'),
        dict(path='output.output_root', value='"/etc"', reason='tidier', source='none'),
        dict(path='run.connection_profile_id', value='"other"', reason='x', source='none'),
        dict(path='run.advanced.batch_size', value='[1, 2]', reason='x', source='none'), 'not an object'],
        encoder_ideas=[dict(name='GPS', source='NeurIPS 2022', why='global attention', what_it_takes='a new encoder class'), dict(name='', source='x', why='y', what_it_takes='z')])
    proposal = ProposalStore().create(review_request(tmp_path), AgentResult('s1', 'claude_code', 'fixture', output), circuit_hash=None)
    assert [(s['path'], s['value']) for s in proposal['suggestions']] == [('run.advanced.batch_size', 16), ('run.network.encoder_type', 'gat'),
                                                                        ('run.stop_at_first_feasible', True)]
    assert len(proposal['refused_suggestions']) == 3 and any('output.output_root' in r for r in proposal['refused_suggestions'])
    assert [i['name'] for i in proposal['encoder_ideas']] == ['GPS'] and proposal['diff'] == []
    with pytest.raises(AgentError) as error:                                  # a settings review patches no table
        bad = dict(output, patch=[dict(op='remove', section='targets', key=complete(tmp_path)['targets'][0]['metric_id'])])
        ProposalStore().create(review_request(tmp_path), AgentResult('s2', 'claude_code', 'fixture', bad), circuit_hash=None)
    assert 'may not change' in error.value.detail
    other = AgentRequest(kind='targets', user_prompt='x', config=complete(tmp_path), circuit_summary=dict(devices=[]))
    ignored = ProposalStore().create(other, AgentResult('s3', 'claude_code', 'fixture', dict(output, kind='targets')), circuit_hash=None)
    assert ignored['suggestions'] == [] and ignored['encoder_ideas'] == []          # from any other request they are dropped


def test_every_suggestion_is_tried_on_a_copy_and_a_pair_may_need_each_other(tmp_path):
    config = complete(tmp_path)

    def validate_config(raw):
        network = raw['run'].get('network') or {}
        if not isinstance(network.get('hidden_dim', 32), int):
            return 'run.network.hidden_dim: not a number', []
        return None, (['heads_divisibility'] if network.get('hidden_dim', 32) % network.get('heads', 4) else [])
    found = settings_review.check(config, [dict(path='run.network.hidden_dim', value=192), dict(path='run.network.heads', value=3),
                                           dict(path='run.network.hidden_dim', value='wide'), dict(path='run.network.layers', value=config['run'].get('network', {}).get('layers', 2))],
                                  validate_config=validate_config)
    wide, heads, bad, same = found['suggestions']
    assert wide['applicable'] and wide['alone'] is None and wide['panel'] == 'RL network' and wide['now'] != 192
    assert heads['applicable'] and 'together' in heads['alone']                     # 32 is not divisible by 3, 192 is
    assert not bad['applicable'] and 'not a number' in bad['problem']
    assert not same['applicable'] and 'already' in same['problem'] and not same['changes']
    assert found['all_together']['ok'] and config == complete(tmp_path)              # nothing was applied


# ------------------------------------------------------------------------------- the web, narrowly
def test_web_tools_stay_denied_unless_this_request_asked_and_then_only_publication_hosts(tmp_path, cli):
    record = cli('settings_review')
    provider = ClaudeCodeProvider(AgentSettings(provider='claude_code'))
    provider.propose(review_request(tmp_path))
    argv = json.loads(record.read_text())['argv']
    denied = argv[argv.index('--disallowedTools') + 1].split(',')
    assert 'WebFetch' in denied and 'WebSearch' in denied and '--allowedTools' not in argv and '--max-turns' not in argv
    provider.propose(review_request(tmp_path, web=True, web_domains=settings_review.domains(['my.lab.example', 'not a host', '*.ok.org'])))
    seen = json.loads(record.read_text())
    argv = seen['argv']
    denied = argv[argv.index('--disallowedTools') + 1].split(',')
    allowed = argv[argv.index('--allowedTools') + 1].split(',')
    assert 'WebFetch' not in denied and 'WebSearch' not in denied and {'Bash', 'Write', 'Edit'} <= set(denied)   # still nothing that writes or runs
    assert 'WebSearch' in allowed and 'WebFetch(domain:arxiv.org)' in allowed and 'WebFetch(domain:my.lab.example)' in allowed
    assert 'WebFetch(domain:*.ok.org)' in allowed and 'WebFetch' not in allowed and not any('not a host' in rule for rule in allowed)
    assert argv[argv.index('--max-turns') + 1] == str(settings_review.WEB_MAX_TURNS) and seen['files_in_cwd'] == []   # bounded, in an empty directory
    no_hosts = review_request(tmp_path, web=True, web_domains=())
    provider.propose(no_hosts)                                                      # no host list: no web, not "every host"
    assert 'WebFetch' in json.loads(record.read_text())['argv'][json.loads(record.read_text())['argv'].index('--disallowedTools') + 1]


def test_a_refused_page_is_the_rule_working_but_any_other_refused_tool_is_still_fatal(tmp_path, cli):
    cli('web_refused')
    provider = ClaudeCodeProvider(AgentSettings(provider='claude_code'))
    result = provider.propose(review_request(tmp_path, web=True, web_domains=('arxiv.org',)))
    assert result.audit['web_calls_refused'] == 1 and result.structured_output['suggestions']
    with pytest.raises(AgentError) as error:
        provider.propose(review_request(tmp_path))                                 # the same refusal without online research asked for
    assert error.value.code == 'permission_denied'
    cli('permission_denied')
    with pytest.raises(AgentError) as error:
        provider.propose(review_request(tmp_path, web=True, web_domains=('arxiv.org',)))
    assert error.value.code == 'permission_denied'                                 # Bash stays refused, online or not
    with pytest.raises(AgentError) as error:
        CodexProvider(AgentSettings(provider='codex')).propose(review_request(tmp_path, web=True, web_domains=('arxiv.org',)))
    assert error.value.code == 'unsupported_cli'


# ------------------------------------------------------------------------------- over HTTP
@pytest.fixture
def client(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    target = bin_dir / 'claude'
    target.write_text(f'#!{sys.executable}\n' + FIXTURE.read_text())
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv('PATH', f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.setenv('FAKE_CLI_SCENARIO', 'settings_review')
    monkeypatch.setenv('FAKE_CLI_RECORD', str(tmp_path / 'record.json'))
    return TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))


def test_a_review_over_http_is_checked_by_the_backend_and_applies_nothing(client, tmp_path):
    config = complete(tmp_path)
    reply = client.post('/api/agent/propose', json=dict(kind='settings_review', prompt='Review my settings.', config=config, web=True))
    proposal = reply.json()
    assert reply.status_code == 200 and proposal['kind'] == 'settings_review' and proposal['diff'] == []
    batch, encoder = proposal['suggestions']
    assert batch['path'] == 'run.advanced.batch_size' and batch['applicable'] and batch['panel'] == 'RL network (Advanced)' and 'now' in batch
    assert encoder['value'] == 'gat' and encoder['url'].startswith('https://arxiv.org') and encoder['applicable']
    assert any('output.output_root' in refused for refused in proposal['refused_suggestions']) and proposal['suggestions_together']['ok']
    assert proposal['encoder_ideas'][0]['name'] == 'GPS graph transformer'
    sent = json.loads((tmp_path / 'record.json').read_text())
    assert 'ONLINE RESEARCH IS ON' in sent['stdin'] and '--allowedTools' in sent['argv']
    assert all(str(row['instance_path']) not in sent['stdin'] for row in config['parameters'])       # nothing of the design went along
    offline = client.post('/api/agent/propose', json=dict(kind='settings_review', prompt='Review my settings.', config=config)).json()
    assert offline['suggestions'] and '--allowedTools' not in json.loads((tmp_path / 'record.json').read_text())['argv']
    assert client.post('/api/agent/propose', json=dict(kind='targets', prompt='x', config=config, web=True)).status_code == 409
