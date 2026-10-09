"""What is missing before a run can start: the backend's free checklist behind "What's missing?" in the Agent window
(readiness.py; until 2026-10-06 also the brief of the Agent tab's own agent, record 7.226; the tab became a window on
2026-10-07, record 7.253). No model is called and nothing is probed."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from gator_workbench import readiness
from helpers import make_config, workbench_app


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
    assert items['parameters']['action'].startswith('Press "Reload saved values"')            # a registered task brings its own rows
    assert all('Claude Code or Codex (the Agent window)' in items[k]['action'] for k in ('parameters', 'targets', 'measurements'))
    typed = readiness.build(dict(config, circuit=dict(source='virtuoso', library='L', cell='C')), task=task(), validation=dict(blocks_run=True, issues=found, facts={}))
    assert by_id(typed)['parameters']['action'].startswith('Fill in')                                  # a cell read from Virtuoso has no starter


def test_rows_that_differ_from_the_saved_task_are_one_press_of_the_users_and_the_issue_says_which(tmp_path):
    """Record 7.204: after "Apply calibration" the Specs hold Scales the saved task does not. The checklist used to cut
    the issue before its last sentence and to advise "Reload saved values ... or the agent writes the rows"."""
    message = ('Specs differ from the saved task real:demo (revision 1): gain_vv: normalization_scale 260 V/V here, (none) saved; ibias_a: '
               'normalization_scale 280 uA here, (none) saved; pm_deg: normalization_scale 9.6 deg here, (none) saved; ugbw_hz: normalization_scale '
               '11 MHz here, (none) saved. Press Save task to save the rows as they are now, or Reload saved values to take the saved rows back.')
    report = readiness.build(complete(tmp_path), task=task(), validation=dict(blocks_run=True, issues=[issue('error', 'task_not_saved', 'targets', message)], facts={}))
    item = by_id(report)['targets']
    assert item['status'] == 'missing' and item['who'] == 'you' and item['detail'] == message          # whole, its last sentence included
    assert item['action'].startswith('"Save task" is above the editors') and 'agent' not in item['action']
    assert not report['ready'] and report['next']['id'] == 'targets'
    # another blocking issue on the same table keeps the general advice: the rows themselves need work
    both = readiness.build(complete(tmp_path), task=task(), validation=dict(blocks_run=True, facts={}, issues=[
        issue('error', 'task_not_saved', 'targets', message), issue('error', 'unknown_metric', 'targets[0].equation', 'no such probe')]))
    assert by_id(both)['targets']['who'] == 'agent' and by_id(both)['targets']['action'].startswith('Press "Reload saved values"')


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


# ------------------------------------------------------------------------------- over HTTP
def test_the_checklist_is_free_and_computed_by_the_backend(tmp_path):
    client = TestClient(workbench_app(tmp_path))
    config = complete(tmp_path)
    ready = client.post('/api/agent/readiness', json=dict(config=config)).json()
    assert ready['ready'] and 'No model was called' in ready['note'] and set(ready) == {'ready', 'next', 'items', 'note'}
    empty = dict(config, parameters=[], targets=[], measurements=[])
    blocked = client.post('/api/agent/readiness', json=dict(config=empty)).json()
    assert not blocked['ready'] and blocked['next']['id'] == 'parameters'
    assert 'Claude Code or Codex (the Agent window)' in blocked['next']['action']  # what an agent opened from the Agent window can do
    assert client.post('/api/agent/readiness', json=dict(config=dict(config, run='nonsense'))).status_code == 422


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
    assert 'refused the moment it starts' in by_id(differs)['parameters']['detail']
    assert by_id(differs)['parameters']['action'].startswith('Press "Reload saved values"')      # free and exact
    same = readiness.build(real, profile=dict(rows=fixed, matches=True, error=None), **kw)
    assert same['ready'] and by_id(same)['parameters']['status'] == 'done'
    stuck = readiness.build(real, profile=dict(rows=fixed, matches=None, error='CompileError: no such device'), **kw)
    assert not stuck['ready'] and 'does not compile' in by_id(stuck)['parameters']['detail']
    none_yet = readiness.build(dict(real, parameters=[]), profile=dict(rows=fixed, matches=None, error=None), **kw)
    assert by_id(none_yet)['parameters']['status'] == 'missing' and 'None is configured yet' in by_id(none_yet)['parameters']['detail']
    free = readiness.build(config, task=task(), validation=ok, profile=None)             # a fixture fixes nothing
    assert by_id(free)['parameters']['status'] == 'done'


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
