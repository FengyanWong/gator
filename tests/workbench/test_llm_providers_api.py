"""Hermetic provider processes and API consistency: no real model executable."""
import json
import stat
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from analog_optimizer.search.llm import output_schema
from gator_workbench.agents.sizing import SizingCliClient
from gator_workbench.schema import SearchSettings, WorkbenchConfig
from gator_workbench import runs
from gator_workbench.storage.atomic import write_json
from helpers import cli, workbench_app, roots_for, make_config
from test_llm_search import configure


@pytest.mark.parametrize('provider', ['claude_code', 'codex'])
def test_sizing_cli_isolated_and_counted_with_fixed_directory(tmp_path, cli, monkeypatch, provider):
    record = cli('success')
    executable = tmp_path / 'bin' / ('codex' if provider == 'codex' else 'claude')
    source = executable.read_text().replace('  --sandbox <MODE>', '  --ignore-user-config\\n  --sandbox <MODE>')
    source = source.replace("if __name__ == '__main__':", "GOOD = dict(analysis='fixture', notes=[], candidates=[dict(values={'width': 1.0}, rationale='fixture')])\nif __name__ == '__main__':")
    executable.write_text(source)
    runs.save_settings(agent=dict(provider=provider, cli_path=str(executable)))
    settings = SearchSettings(method='llm', provider=provider, max_llm_calls=2, max_llm_notional_usd=1)
    client = SizingCliClient('test-' + uuid4().hex, settings)
    for i in range(2):
        client.prepare_call(str(i), 1)
        response = client.complete('Synthetic data only', output_schema(['width'], 1))
        assert response['output']['candidates'][0]['values'] == {'width': 1.0}
        seen = json.loads(record.read_text())
        argv = seen['argv']
        assert seen['cwd'] == str(client.cwd) and not list(client.cwd.iterdir())
        if provider == 'claude_code':
            assert argv[argv.index('--tools') + 1] == ''
            assert '--strict-mcp-config' in argv and '--max-budget-usd' in argv
        else:
            assert '--ignore-user-config' in argv and 'web_search="disabled"' in argv
            assert 'features.shell_tool=false' in argv and 'features.unified_exec=false' in argv
            assert response['audit']['total_cost_usd'] is None
    client.cwd.rmdir()


def test_hint_route_and_thread_follow_same_phase_contract(tmp_path):
    config = configure(tmp_path, 'llm')
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    with TestClient(workbench_app(tmp_path)) as client:
        assert client.get('/api/runs/llm-thread', params={'run_dir':str(layout.run_dir)}).status_code == 200
        for enabled in (False, True):
            write_json(layout.status, dict(state='running', search=dict(hints_available=enabled)))
            reply = client.post('/api/runs/llm-hint', json={'run_dir':str(layout.run_dir),'text':'Explore bias'})
            assert reply.status_code == (200 if enabled else 409)
        assert client.post('/api/runs/llm-hint', json={'run_dir':str(layout.run_dir),'text':'x'*1501}).status_code == 422
        assert client.get('/api/runs/llm-thread', params={'run_dir':'/etc'}).status_code == 403


@pytest.mark.parametrize('body', [{}, {'text': 'Try this'}, {'run_dir': []},
                                  {'run_dir': '/tmp', 'text': 123}])
def test_malformed_hint_request_is_a_validation_error(tmp_path, body):
    with TestClient(workbench_app(tmp_path)) as client:
        assert client.post('/api/runs/llm-hint', json=body).status_code == 422


@pytest.mark.parametrize('method,patch', [
    ('llm', {'concurrency':2}), ('llm', {'mode':'fine_tune'}), ('llm', {'mode':'frozen'}),
    ('llm_warmstart', {'mode':'frozen'}), ('sac_llm_rescue', {'mode':'frozen'}),
    ('unknown', {}),
])
def test_ui_restrictions_are_enforced_by_schema(tmp_path, method, patch):
    data=make_config(tmp_path).model_dump(mode='json')
    data['run'].update(patch)
    data['run']['search']=dict(method=method,provider='codex',max_llm_calls=2)
    with pytest.raises(ValueError):
        WorkbenchConfig.model_validate(data)


@pytest.mark.parametrize('method', ['sac', 'llm_warmstart', 'llm', 'sac_llm_rescue'])
@pytest.mark.parametrize('optimized', [False, True])
def test_current_groups_are_blocked_before_sac_can_start(tmp_path, method, optimized):
    from gator_workbench.validation import validate
    data = make_config(tmp_path).model_dump(mode='json')
    data['run']['search'] = dict(method=method, provider='codex', max_llm_calls=2)
    data['parameters'].append(dict(variable_id='bias', instance_path='ibias', parameter_name='dc',
        unit='uA', lower=1, upper=100, optimized=optimized))
    report = validate(WorkbenchConfig.model_validate(data))
    blockers = [i for i in report.issues if i.code=='current_group_not_supported_by_sac']
    assert bool(blockers) == (method != 'llm')


@pytest.mark.parametrize('provider,initial,effort,selected', [
    ('codex','gpt-6-astra','ultra','gpt-6-luna'),
    ('claude_code','fable','high','haiku'),
])
def test_sizing_inherits_only_efforts_supported_by_selected_model(tmp_path, provider, initial, effort, selected):
    from gator_workbench.agents.sizing import resolve_settings
    runs.save_settings(agent=dict(provider=provider,model=initial,effort=effort))
    search=SearchSettings(method='llm',max_llm_calls=2,max_llm_notional_usd=1)
    assert resolve_settings(search).effort==effort
    search.model=selected
    assert resolve_settings(search).effort is None
    search.effort=effort
    with pytest.raises(ValueError,match='does not support effort'):
        resolve_settings(search)


def test_invalid_sizing_effort_is_a_start_validation_error(tmp_path):
    config=configure(tmp_path,'llm')
    config.run.search.effort='unsupported-level'
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(config,roots_for(tmp_path))
    assert error.value.code=='search_settings'
