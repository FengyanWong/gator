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
    assert [i['id'] for i in report['items']][:4] == ['circuit', 'parameters', 'measurements', 'targets']     # the gating order = tab order


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
    assert items['parameters']['action'].startswith('Press "Load task"')            # a registered task brings its own rows
    typed = readiness.build(dict(config, circuit=dict(source='virtuoso', library='L', cell='C')), task=task(), validation=dict(blocks_run=True, issues=found, facts={}))
    assert by_id(typed)['parameters']['action'].startswith('Fill in')                                  # a cell read from Virtuoso has no starter


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
    good = dict(item='Specs', status='missing', who='you', action='State the gain you need.', basis='no hard constraint')
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


# ------------------------------------------------------------------------------- the fewest changes that let the run start
def test_only_rows_with_a_blocking_issue_may_be_changed(tmp_path):
    config = complete(tmp_path)
    second = dict(config['parameters'][0], variable_id='second')
    config['parameters'].append(second)
    last = len(config['parameters']) - 1
    blocking = [issue('error', 'initial_out_of_bounds', f'parameters[{last}].initial_value'), issue('error', 'unknown_unit', 'targets[0].unit')]
    assert readiness.changeable_rows(config, blocking) == dict(parameters=['second'], targets=[config['targets'][0]['metric_id']], measurements=[])
    whole = readiness.changeable_rows(config, blocking + [issue('error', 'binding_graph', 'parameters')])
    assert whole['parameters'] == '*'                                          # an issue about the section: any row may be the cause
    assert readiness.changeable_rows(config, [issue('error', 'x', 'parameters[99].unit'), issue('error', 'y', 'run.network')]) == dict(
        parameters=[], targets=[], measurements=[])


def minimal(tmp_path, config, blocking, patch):
    state = readiness.build(config, task=task(), validation=dict(blocks_run=bool(blocking), issues=blocking, facts={}))
    req = AgentRequest(kind='minimal_start', user_prompt='Make it startable with the fewest changes.', config=config,
                       circuit_summary=dict(devices=[]), readiness=state)
    output = dict(kind='minimal_start', patch=patch, reasoning='minimum', warnings=[], unresolved=[])
    return ProposalStore().create(req, AgentResult('m1', 'claude_code', 'fixture', output), circuit_hash=None)


def test_a_minimal_start_proposal_cannot_touch_a_valid_row(tmp_path):
    from gator_workbench.agents import AgentError
    config = complete(tmp_path)
    target = config['targets'][0]
    rewrite = [dict(op='replace', section='targets', key=target['metric_id'], value=dict(target, lower=0.5), basis='tidier')]
    with pytest.raises(AgentError) as error:
        minimal(tmp_path, config, [], rewrite)                                  # nothing is wrong with that row
    assert error.value.code == 'schema_failure' and 'no blocking issue' in error.value.detail
    with pytest.raises(AgentError):
        minimal(tmp_path, config, [], [dict(op='remove', section='targets', key=target['metric_id'])])
    broken = [issue('error', 'missing_threshold', 'targets[0].lower')]
    proposal = minimal(tmp_path, config, broken, rewrite)                       # the same edit IS the fix when the row is at fault
    assert [d['key'] for d in proposal['diff']] == [target['metric_id']] and proposal['kind'] == 'minimal_start'
    extra = dict(config['parameters'][0], variable_id='added_variable')
    added = minimal(tmp_path, config, [], [dict(op='add', section='parameters', key='added_variable', value=extra, basis='PROVISIONAL: 0.5x-2x')])
    assert added['diff'][0]['change'] == 'added'                                # adding is allowed; whether it was NEEDED is the prompt's rule


def test_the_minimal_start_prompt_states_the_limits_and_the_brief_explains_provisional_values(tmp_path):
    state = readiness.build(complete(tmp_path), task=task(), validation=dict(blocks_run=False, issues=[], facts={}))
    text = prompts.build_prompt(request(tmp_path, kind='minimal_start', readiness=state))
    assert 'AS FEW CHANGES AS POSSIBLE' in text and 'may NOT be replaced or removed' in text and '"changeable_rows"' in text
    assert 'The smallest startable setup' in text and 'PROVISIONAL:' in text and 'initial_design_results' in text


def test_the_backend_says_whether_the_run_would_start_after_the_proposal(client, tmp_path):
    config = complete(tmp_path)
    empty = dict(config, parameters=[], targets=[], measurements=[])
    rows = [dict(op='add', section=section, key=row[key], value=row, basis='PROVISIONAL: copied from the fixture')
            for section, key in (('parameters', 'variable_id'), ('measurements', 'measurement_id')) for row in config[section]]
    half = client.post('/api/agent/import-result', json=dict(kind='minimal_start', prompt='fewest changes', config=empty,
                                                             result=dict(kind='minimal_start', patch=rows, reasoning='r', warnings=[], unresolved=[])))
    after = half.json()['readiness_after']
    assert half.status_code == 200 and not after['ready'] and after['changed_rows'] == len(rows)
    assert 'Parameters' in after['resolved'] and [r['title'] for r in after['remaining']] == ['Specs']
    rows += [dict(op='add', section='targets', key=row['metric_id'], value=row, basis='PROVISIONAL: no worse than the initial design')
             for row in config['targets']]
    full = client.post('/api/agent/import-result', json=dict(kind='minimal_start', prompt='fewest changes', config=empty,
                                                             result=dict(kind='minimal_start', patch=rows, reasoning='r', warnings=[], unresolved=[])))
    after = full.json()['readiness_after']
    assert after['ready'] and after['remaining'] == [] and 'Worked out by the backend' in after['note']
    target = config['targets'][0]
    refused = client.post('/api/agent/import-result', json=dict(kind='minimal_start', prompt='fewest changes', config=config, result=dict(
        kind='minimal_start', reasoning='r', warnings=[], unresolved=[],
        patch=[dict(op='replace', section='targets', key=target['metric_id'], value=dict(target, soft_weight=2.0))])))
    assert refused.status_code == 409 and 'no blocking issue' in refused.json()['detail']['detail']


def test_a_real_circuit_tells_the_agent_the_verified_results_of_the_design_as_it_stands(client, tmp_path, monkeypatch):
    import dataclasses
    from gator_workbench import tasks
    genuine = tasks.load_task

    def as_real(circuit, **kwargs):
        runtime = genuine(circuit, **kwargs)
        return dataclasses.replace(runtime, origin='real', reference_metrics=dict(gain_db_at_start=dict(value=25.0, unit='dB')))
    monkeypatch.setattr(tasks, 'load_task', as_real)
    client.post('/api/agent/propose', json=dict(kind='minimal_start', prompt='fewest changes', config=complete(tmp_path)))
    sent = json.loads((tmp_path / 'record.json').read_text())['stdin']
    assert '"initial_design_results"' in sent and '"gain_db_at_start"' in sent and 'REQUEST KIND: minimal_start' in sent
    assert tasks.TaskRuntime.__dataclass_fields__['reference_metrics'].default is None      # unknown unless a baseline is on record


# ------------------------------------------------------------------------------- a verified real circuit fixes its variables
def test_a_real_profile_accepts_only_its_own_variables_and_the_checklist_says_so_before_the_start(tmp_path):
    config = complete(tmp_path)
    fixed = [dict(variable_id='pair_width', instance_path='XU1/M1', parameter_name='w', unit='m', lower=1e-6, upper=2e-6)]
    ok = dict(blocks_run=False, issues=[], facts={})
    passed = dict(overall='ok', age_seconds=1.0, layers=[])
    real = dict(config, run=dict(config['run'], connection_profile_id='lab'))
    kw = dict(task=task(mock=False), validation=ok, connection=passed, output=dict(allowed=True, exists=True, writable=True, error=None))
    differs = readiness.build(real, profile=dict(rows=fixed, matches=False, error=None), **kw)
    assert not differs['ready'] and by_id(differs)['parameters']['status'] == 'missing'
    assert 'refused the moment it starts' in by_id(differs)['parameters']['detail'] and differs['changeable_rows']['parameters'] == '*'
    assert differs['required_parameter_rows'] == fixed
    assert by_id(differs)['parameters']['action'].startswith('Press "Load task"')      # free and exact: before any agent request
    same = readiness.build(real, profile=dict(rows=fixed, matches=True, error=None), **kw)
    assert same['ready'] and by_id(same)['parameters']['status'] == 'done' and same['changeable_rows']['parameters'] == []
    stuck = readiness.build(real, profile=dict(rows=fixed, matches=None, error='CompileError: no such device'), **kw)
    assert not stuck['ready'] and 'does not compile' in by_id(stuck)['parameters']['detail']
    none_yet = readiness.build(dict(real, parameters=[]), profile=dict(rows=fixed, matches=None, error=None), **kw)
    assert by_id(none_yet)['parameters']['status'] == 'missing' and 'None is configured yet' in by_id(none_yet)['parameters']['detail']
    free = readiness.build(config, task=task(), validation=ok, profile=None)             # a fixture fixes nothing
    assert free['required_parameter_rows'] == [] and by_id(free)['parameters']['status'] == 'done'


def test_the_rows_a_profile_fixes_are_written_from_its_own_parameter_groups():
    from dataclasses import dataclass, field
    from gator_workbench import tasks

    @dataclass
    class Group:
        id: str
        unit: str
        value: float
        lower: float
        upper: float
        members: list = field(default_factory=list)
        domain: str = 'continuous'
        scale: str = 'linear'
        mutable: bool = True
        step: float | None = None
    pair = Group('pair_width', 'm', 4e-6, 3.6e-6, 4.4e-6, step=5e-9, members=[dict(device_id='XU1/M1', parameter='w', ratio=1.0),
                                                                           dict(device_id='XU1/M2', parameter='w', ratio=1.0)])
    tail = Group('tail_width', 'm', 4e-6, 1e-6, 1e-5, scale='log', mutable=False, members=[dict(device_id='XU1/M5', parameter='w', ratio=1.0)])
    runtime = SimpleNamespace(mock=False, base_graph=SimpleNamespace(parameter_groups=[pair, tail]))
    rows = tasks.profile_parameter_rows(runtime)
    assert [r['variable_id'] for r in rows] == ['pair_width', 'pair_width__XU1_M2', 'tail_width']
    assert rows[0] == dict(variable_id='pair_width', instance_path='XU1/M1', parameter_name='w', unit='m', scale='linear', value_type='continuous',
                           lower=3.6e-6, upper=4.4e-6, step=5e-9, optimized=True, initial_value=4e-6)
    assert rows[1]['binding_group'] == 'pair_width' and rows[1]['ratio'] == 1.0 and 'lower' not in rows[1]
    assert rows[2]['optimized'] is False and rows[2]['scale'] == 'log'
    assert tasks.profile_parameter_rows(SimpleNamespace(mock=True, base_graph=runtime.base_graph)) == [] and tasks.profile_parameter_rows(None) == []
