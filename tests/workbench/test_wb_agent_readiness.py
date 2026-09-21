"""What is missing before a run can start: the backend's free checklist, the editable brief, and the agent
request that is built on both. Fake CLI fixtures only - no model is called and nothing is probed."""
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from gator_workbench.agents import AgentRequest, AgentResult, ProposalStore, prompts, readiness
from gator_workbench.api.app import create_app
from helpers import make_config

FIXTURE = Path(__file__).parent / 'fixtures' / 'fake_cli.py'


def task(mock=True, devices=7):
    return SimpleNamespace(mock=mock, base_graph=SimpleNamespace(devices=[object()] * devices), provided_metrics={'score', 'power'})


def by_id(report):
    return {item['id']: item for item in report['items']}


def issue(level, code, path, message='message'):
    return dict(level=level, code=code, path=path, message=message)


def complete(tmp_path):
    return make_config(tmp_path).model_dump(mode='json')


# ------------------------------------------------------------------------------- the free checklist
def test_a_complete_mock_configuration_is_ready_and_needs_no_bridge(tmp_path):
    report = readiness.build(complete(tmp_path), task=task(), validation=dict(blocks_run=False, issues=[], facts={}),
                             output=dict(allowed=True, exists=True, writable=True, error=None))
    items = by_id(report)
    assert report['ready'] and report['next']['id'] == 'start' and items['start']['status'] == 'done'
    assert report['provided_metrics'] == ['power', 'score']                  # what the agent may write targets on
    assert items['connection']['status'] == 'not_applicable' and 'authorization' not in items
    assert [i['id'] for i in report['items']][:4] == ['circuit', 'parameters', 'targets', 'measurements']     # the gating order


def test_empty_tables_are_the_agents_to_fix_and_everything_else_is_the_users(tmp_path):
    config = dict(complete(tmp_path), parameters=[], targets=[], measurements=[])
    found = [issue('error', 'nothing_to_optimize', 'parameters', 'At least one optimized variable is required'),
             issue('error', 'no_hard_constraint', 'targets', 'At least one active hard constraint is required'),
             issue('error', 'missing_model_source', 'run.model_source', 'fine_tune needs a model')]
    report = readiness.build(config, task=task(), validation=dict(blocks_run=True, issues=found, facts={}),
                             output=dict(allowed=True, exists=False, writable=False, error=None))
    items = by_id(report)
    assert not report['ready'] and report['next']['id'] == 'parameters'
    assert {k: items[k]['status'] for k in ('parameters', 'targets', 'measurements')} == dict.fromkeys(('parameters', 'targets', 'measurements'), 'missing')
    assert all(items[k]['who'] == 'agent' for k in ('parameters', 'targets', 'measurements'))
    assert items['validation']['who'] == 'you' and 'fine_tune needs a model' in items['validation']['detail']
    assert items['output']['status'] == 'done' and 'created when the run starts' in items['output']['detail']
    assert items['start']['status'] == 'missing'


def test_an_inactive_or_soft_target_does_not_define_feasibility(tmp_path):
    config = complete(tmp_path)
    for row in config['targets']:
        row['hard'] = False
    items = by_id(readiness.build(config, task=task(), validation=dict(blocks_run=False, issues=[], facts={})))
    assert items['targets']['status'] == 'missing' and 'feasible' in items['targets']['detail']


def test_a_budget_that_cannot_learn_is_a_warning_not_a_block(tmp_path):
    found = [issue('warning', 'budget_within_warmup', 'run.max_evaluations', 'The whole budget is random warm-up')]
    report = readiness.build(complete(tmp_path), task=task(), validation=dict(blocks_run=False, issues=found, facts={}),
                             output=dict(allowed=True, exists=True, writable=True, error=None))
    assert by_id(report)['run']['status'] == 'warning' and report['ready']


def test_a_real_circuit_needs_a_profile_a_passed_test_and_the_users_authorization(tmp_path):
    config = complete(tmp_path)
    ok = dict(blocks_run=False, issues=[], facts={})
    items = by_id(readiness.build(config, task=task(mock=False), validation=ok))
    assert items['connection']['status'] == 'missing' and items['authorization']['status'] == 'at_start'
    config['run']['connection_profile_id'] = 'lab'
    never = dict(overall='unknown', age_seconds=None, layers=[dict(layer='tunnel', state='unknown')])
    items = by_id(readiness.build(config, task=task(mock=False), validation=ok, connection=never))
    assert items['connection']['status'] == 'unknown' and 'never tested' in items['connection']['detail']
    failed = dict(overall='failed', age_seconds=12.0, layers=[dict(layer='tunnel', state='failed', details=dict(host='10.1.2.3', user='minlei'))])
    report = readiness.build(config, task=task(mock=False), validation=ok, connection=failed)
    assert by_id(report)['connection']['status'] == 'missing' and not report['ready']
    passed = dict(overall='ok', age_seconds=3.0, layers=[dict(layer='tunnel', state='ok')])
    report = readiness.build(config, task=task(mock=False), validation=ok, connection=passed,
                             output=dict(allowed=True, exists=True, writable=True, error=None))
    assert report['ready'] and by_id(report)['connection']['status'] == 'done'
    text = json.dumps(readiness.build(config, task=task(mock=False), validation=ok, connection=failed))
    assert '10.1.2.3' not in text and 'minlei' not in text and 'lab' not in text        # words only: no host, account or profile


def test_an_unreadable_circuit_is_the_first_thing_missing(tmp_path):
    report = readiness.build(complete(tmp_path), task=None, task_blocker='No connection profile carries bindings for this circuit')
    assert report['next']['id'] == 'circuit' and 'bindings' in report['next']['detail'] and not report['ready']


# ------------------------------------------------------------------------------- the brief and the request
def request(tmp_path, kind='readiness', **kwargs):
    return AgentRequest(kind=kind, user_prompt='What is still missing before this run can start?', config=complete(tmp_path),
                        circuit_summary=dict(devices=[]), **kwargs)


def test_every_request_carries_the_brief_and_the_live_state_as_data(tmp_path, monkeypatch):
    state = readiness.build(complete(tmp_path), task=task(), validation=dict(blocks_run=False, issues=[], facts={}))
    text = prompts.build_prompt(request(tmp_path, readiness=state))
    assert 'OPERATOR GUIDE' in text and 'The order a start is gated in' in text
    assert '<run_readiness_data>' in text and '"ready"' in text and 'Return `checklist`' in text
    assert text.index('RULES') < text.index('OPERATOR GUIDE') < text.index('<user_prompt_data>')     # it never outranks the rules
    other = prompts.build_prompt(request(tmp_path, kind='targets', readiness=state))
    assert 'OPERATOR GUIDE' in other and '<run_readiness_data>' in other and 'Return `checklist`' not in other
    exported = prompts.task_description(request(tmp_path, readiness=state))
    assert 'OPERATOR GUIDE' in exported['prompt'] and 'checklist' in exported['output_json_schema']['properties']
    edited = tmp_path / 'brief.md'
    edited.write_text('A RUN NEEDS A FRESH COFFEE FIRST')                       # the file is read per request: no restart
    monkeypatch.setattr(prompts, 'GUIDE_PATH', edited)
    assert 'A FRESH COFFEE' in prompts.build_prompt(request(tmp_path))
    monkeypatch.setattr(prompts, 'GUIDE_PATH', tmp_path / 'missing.md')
    assert 'OPERATOR GUIDE' not in prompts.build_prompt(request(tmp_path))      # a missing brief is not an error


def test_the_checklist_of_a_reply_is_kept_as_advice_and_never_part_of_the_approval(tmp_path):
    good = dict(item='Performance Targets', status='missing', who='you', action='State the gain you need.', basis='no hard constraint')
    output = dict(kind='readiness', patch=[], reasoning='Targets are missing.', warnings=[], unresolved=['required gain'],
                  checklist=[good, dict(item='x', status='exploded', who='you', action='-'), 'not an object',
                             dict(item='', status='done', who='agent', action='-'), dict(item='y', status='done', who='root', action='-')])
    store = ProposalStore()
    proposal = store.create(request(tmp_path), AgentResult('r1', 'claude_code', 'fixture', output), circuit_hash=None)
    assert proposal['checklist'] == [good] and proposal['kind'] == 'readiness' and proposal['diff'] == []
    same = store.create(request(tmp_path), AgentResult('r2', 'claude_code', 'fixture', dict(output, checklist=[])), circuit_hash=None)
    assert same['proposal_hash'] == proposal['proposal_hash']                  # advice does not change what an approval binds to


# ------------------------------------------------------------------------------- over HTTP
@pytest.fixture
def client(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    target = bin_dir / 'claude'
    target.write_text(f'#!{sys.executable}\n' + FIXTURE.read_text())
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv('PATH', f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.setenv('FAKE_CLI_SCENARIO', 'success')
    monkeypatch.setenv('FAKE_CLI_RECORD', str(tmp_path / 'record.json'))
    return TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))


def test_the_checklist_is_free_and_an_agent_request_is_told_the_same(client, tmp_path):
    config = complete(tmp_path)
    ready = client.post('/api/agent/readiness', json=dict(config=config)).json()
    assert ready['ready'] and 'No model was called' in ready['note'] and not (tmp_path / 'record.json').exists()
    empty = dict(config, parameters=[], targets=[], measurements=[])
    blocked = client.post('/api/agent/readiness', json=dict(config=empty)).json()
    assert not blocked['ready'] and blocked['next']['id'] == 'parameters' and not (tmp_path / 'record.json').exists()
    assert client.post('/api/agent/readiness', json=dict(config=dict(config, run='nonsense'))).status_code == 422
    client.post('/api/agent/propose', json=dict(kind='readiness', prompt='What is missing?', config=config))
    sent = json.loads((tmp_path / 'record.json').read_text())['stdin']
    assert 'REQUEST KIND: readiness' in sent and '<run_readiness_data>' in sent and 'OPERATOR GUIDE' in sent
    assert '"ready": true' in sent
