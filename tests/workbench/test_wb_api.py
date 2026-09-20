"""HTTP API: one schema for forms/agents/execution, restricted paths, run control through a detached
worker, connection endpoints, agent proposals. Mock backend and fake CLI/probe fixtures only."""
import io
import json
import os
from pathlib import Path
import stat
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_read, tasks
from gator_workbench.api import create_app
from gator_workbench.connection import ConnectionMonitor, LAYERS
from helpers import make_config

REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / 'fixtures' / 'fake_cli.py'


def probe(tmp_path, **states):
    layers = [dict(layer=n, state=states.get(n, 'ok'), reason_code=None, diagnostic=None, details={}) for n in LAYERS]
    script = tmp_path / 'probe.py'
    script.write_text(f'import json\nprint(json.dumps(dict(layers={layers!r})))\n')
    return ConnectionMonitor(probe_command=[sys.executable, str(script)])


@pytest.fixture
def client(tmp_path):
    app = create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path))
    return TestClient(app)


def config_json(tmp_path, **kwargs):
    return make_config(tmp_path, **kwargs).model_dump(mode='json')


def wait_for(client, run_dir, states=('completed', 'failed', 'paused', 'stopped', 'cancelled'), timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get('/api/runs/status', params=dict(run_dir=run_dir)).json()
        if status.get('state') in states and not status.get('worker_alive'):
            return status
        time.sleep(0.3)
    raise AssertionError(f'run did not finish: {status}')


# ------------------------------------------------------------------------------- schema / config
def test_forms_are_driven_by_the_backend_schema(client):
    data = client.get('/api/schema').json()
    assert data['schema_version'] == 'gator-workbench-config-v1'
    assert set(data['editors']) == {'parameters', 'targets', 'measurements'}
    assert all(column['guidance'] for columns in data['editors'].values() for column in columns)
    assert data['run_modes'] == ['scratch', 'resume', 'fine_tune', 'frozen'] and 'um' in data['units']
    assert 'WorkbenchConfig' in json.dumps(data['json_schema'].get('title', '')) or data['json_schema']['properties']['parameters']
    meta = client.get('/api/meta').json()
    assert 'no plots' in meta['produces'] and meta['default_output_root'].endswith('/outputs')


def test_validation_endpoint_and_schema_rejection(client, tmp_path):
    good = client.post('/api/config/validate', json=dict(config=config_json(tmp_path))).json()
    assert good['blocks_run'] is False and good['facts']['independent_action_variables'] == 2 and good['mock'] is True
    raw = config_json(tmp_path)
    raw['parameters'][0]['lower'] = 1.0
    bad = client.post('/api/config/validate', json=dict(config=raw)).json()
    assert bad['blocks_run'] and any(i['code'] == 'invalid_bounds' for i in bad['issues'])
    raw['run']['skip_validation'] = True
    response = client.post('/api/config/validate', json=dict(config=raw))
    assert response.status_code == 422 and 'skip_validation' in json.dumps(response.json())
    assert client.post('/api/config/validate', json=dict(config=config_json(tmp_path), host='evil')).status_code == 422


def test_tasks_and_circuit_loading(client):
    listed = client.get('/api/tasks').json()
    kinds = {t['task_key']: t for t in listed['tasks']}
    assert kinds['synthetic:opamp']['kind'] == 'mock' and 'MOCK' in kinds['synthetic:opamp']['description']
    real = kinds['real:gpdk045_ota5']
    assert real['available'] is False and real['blocker']                      # the specific blocker, not a fake backend
    assert 'NativeEnvironmentFactory' in listed['real_interface_contract']['environment_factory']
    loaded = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='synthetic:opamp'))).json()
    assert loaded['loaded'] and loaded['mock'] and set(loaded['hierarchy']) >= {'input_left', 'CL'}
    assert 'MOCK' in loaded['evaluation_backend'] and loaded['provided_metrics'] == ['score']
    blocked = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='real:gpdk045_ota5'))).json()
    assert blocked['loaded'] is False and blocked['blocker'] and blocked['interface_contract']
    native = client.post('/api/circuit/load', json=dict(circuit=dict(source='virtuoso', library='L', cell='C'))).json()
    assert native['loaded'] is False and 'verified circuit profile' in native['blocker']


def test_netlist_import_is_limited_to_operator_allowed_input_roots(client, tmp_path):
    ok = client.post('/api/circuit/load', json=dict(circuit=dict(
        source='netlist', netlist_path=str(REPO / 'tests/fixtures/synthetic/ldo.scs'),
        parser_config_path=str(REPO / 'configs/ldo.json'), dut_hierarchy=None)))
    assert ok.status_code == 200 and ok.json()['loaded'] and any('MOCK' in n for n in ok.json()['notes'])
    outside = tmp_path / 'secret.scs'
    outside.write_text('// x')
    for path in (str(outside), '/etc/passwd', str(REPO / 'configs/../../../etc/passwd')):
        response = client.post('/api/circuit/load', json=dict(circuit=dict(
            source='netlist', netlist_path=path, parser_config_path=str(REPO / 'configs/ldo.json'))))
        assert response.status_code == 403, path


def test_circuit_modification_is_diff_then_confirmed_working_copy(client, tmp_path):
    circuit = dict(source='netlist', netlist_path=str(REPO / 'tests/fixtures/synthetic/opamp.scs'),
                   parser_config_path=str(REPO / 'configs/opamp.json'))
    original = (REPO / 'tests/fixtures/synthetic/opamp.scs').read_text()
    body = dict(circuit=circuit, changes=[dict(instance_path='CL', parameter_name='c', new_value=2, unit='pF')],
                output_root=str(tmp_path))
    preview = client.post('/api/circuit/modify', json=body).json()
    assert preview['applied'] is False and preview['diff'][0]['after'] == pytest.approx(2e-12)
    assert not (tmp_path / 'working_copies').exists()                            # nothing written before confirmation
    applied = client.post('/api/circuit/modify', json=dict(body, confirmed=True)).json()
    copy = Path(applied['working_copy'])
    assert applied['applied'] and copy.is_file() and 'c=2e-12' in copy.read_text() and copy.parent.name == 'working_copies'
    assert (REPO / 'tests/fixtures/synthetic/opamp.scs').read_text() == original  # the original is never overwritten
    assert 'checkpoint compatibility' in applied['revalidate'] and 'No native schematic' in applied['note']
    native = client.post('/api/circuit/modify', json=dict(circuit=dict(source='virtuoso', library='L', cell='C'), changes=[]))
    assert native.status_code == 501 and 'NEW cellview' in native.json()['detail']['message']


# ------------------------------------------------------------------------------- output settings
def test_output_root_is_visible_checked_and_restricted(client, tmp_path):
    check = client.post('/api/output/check', json=dict(path=str(tmp_path / 'out'), create=True)).json()
    assert check['allowed'] and check['writable'] and check['free_bytes'] > 0 and check['host']
    assert check['mock_data_root'].endswith('/out/mock') and check['windows_mapping'] != 'not_checked'
    assert check['windows_path'] is None or check['windows_mapping'] == 'verified_by_readback'
    denied = client.post('/api/output/check', json=dict(path='/etc')).json()
    assert denied['allowed'] is False and 'backend operator' in denied['error']
    assert client.get('/api/output/browse', params=dict(path='/etc')).status_code == 403
    assert any(e['path'] == str(tmp_path) for e in client.get('/api/output/browse').json()['entries'])


# ------------------------------------------------------------------------------- runs through the worker
def test_start_pause_continue_stop_and_data_access(client, tmp_path):
    raw = config_json(tmp_path, threshold=1.5, run=dict(max_evaluations=400, concurrency=2))
    started = client.post('/api/runs/start', json=dict(config=raw)).json()
    run_dir = started['run_dir']
    assert started['mock'] and 'MOCK DATA' in started['mock_notice'] and started['connection_gate']['status'] == 'not_applicable'
    assert started['paths']['raw_data'].startswith(run_dir) and '/mock/' in run_dir
    duplicate = client.post('/api/runs/continue', json=dict(run_dir=run_dir))
    assert duplicate.status_code == 409 and duplicate.json()['detail']['code'] == 'already_running'   # never a second worker
    deadline = time.time() + 120
    while time.time() < deadline:
        status = client.get('/api/runs/status', params=dict(run_dir=run_dir)).json()
        if ((status.get('budget') or {}).get('completed') or 0) >= 6:
            break
        time.sleep(0.2)
    assert status['state'] == 'running' and status['worker_alive'] and status['paths'] and status['budget']['max_evaluations'] == 400
    client.post('/api/runs/command', json=dict(run_dir=run_dir, command='pause'))
    paused = wait_for(client, run_dir)
    done = paused['summary']['totals']['candidate_evaluations_charged']
    assert paused['state'] == 'paused' and 6 <= done < 400 and paused['summary']['output']['resumability'] == 'full_state'
    resumed = client.post('/api/runs/continue', json=dict(run_dir=run_dir, max_evaluations=done + 6)).json()
    assert resumed['run_dir'] == run_dir                                         # same directory
    finished = wait_for(client, run_dir)
    assert finished['state'] == 'completed' and finished['summary']['totals']['candidate_evaluations_charged'] == done + 6
    table = client.get('/api/runs/table', params=dict(run_dir=run_dir, table='evaluations', limit=5)).json()
    assert table['total_rows'] == done + 6 and len(table['rows']) == 5 and table['rows'][-1]['provenance'] == 'mock'
    files = client.get('/api/runs/files', params=dict(run_dir=run_dir)).json()
    names = {f['path'] for f in files['files']}
    assert {'run_manifest.json', 'effective_config.json', 'run_summary.json', 'artifact_manifest.json'} <= names
    assert files['total_bytes'] > 0 and not any(n.startswith('work/') for n in names)
    assert client.get('/api/runs/download', params=dict(run_dir=run_dir, path='run_summary.json')).json()['status'] == 'completed'
    assert client.get('/api/runs/download', params=dict(run_dir=run_dir, path='../../../../etc/passwd')).status_code == 403
    assert client.get('/api/runs/status', params=dict(run_dir='/etc')).status_code == 403
    events = client.get('/api/runs/logs', params=dict(run_dir=run_dir)).json()['entries']
    assert [e['event'] for e in events if e['event'] in ('control', 'resumed')] == ['control', 'resumed']
    exported = client.post('/api/runs/export-csv', json=dict(run_dir=run_dir, table='metrics')).json()
    assert exported['relative'].startswith('exports/metrics__seq')
    package = client.post('/api/runs/export-package', json=dict(run_dir=run_dir))
    members = zipfile.ZipFile(io.BytesIO(package.content)).namelist()
    assert 'run_summary.json' in members and any(m.endswith('.parquet') for m in members)
    assert not any(m.startswith(('work/', 'waveforms/', 'checkpoints/')) or m.lower().endswith(('.png', '.pdf', '.svg', '.html'))
                   for m in members)
    aggregates = client.post('/api/aggregates/export', json=dict(run_dir=run_dir)).json()
    assert set(aggregates['files']) >= {'run_summary', 'budget_success', 'paired_runs', 'transfer_summary', 'cumulative_cost'}
    listed = client.get('/api/runs', params=dict(output_root=str(tmp_path))).json()['runs']
    assert listed[0]['run_dir'] == run_dir and listed[0]['mock'] is True
    model = client.post('/api/runs/model', json=dict(run_dir=run_dir, config=raw)).json()
    assert model['description']['restoration_capability'] == 'full_state' and model['suggestion']['mode'] == 'resume'
    assert model['description']['path'].startswith(run_dir) and model['description']['counters']['evaluations_committed'] == done + 6


def test_single_baseline_simulation_is_a_costed_preflight_record(client, tmp_path):
    started = client.post('/api/runs/start', json=dict(config=config_json(tmp_path), baseline_only=True)).json()
    status = wait_for(client, started['run_dir'])
    assert status['summary']['totals']['candidate_evaluations_charged'] == 1      # it is not free
    assert status['summary']['totals']['spectre_launches'] == 1
    rows = client.get('/api/runs/table', params=dict(run_dir=started['run_dir'], table='evaluations')).json()['rows']
    assert len(rows) == 1 and rows[0]['phase'] == 'baseline'
    assert json.loads((Path(started['run_dir']) / 'run_manifest.json').read_text())['run_kind'] == 'baseline_preflight'


def test_blocked_and_rejected_starts(client, tmp_path):
    raw = config_json(tmp_path)
    raw['parameters'][0]['upper'] = 1e-9
    rejected = client.post('/api/runs/start', json=dict(config=raw))
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'validation'
    real = config_json(tmp_path)
    real['circuit'] = dict(source='registered_task', task_id='real:gpdk045_ota5')
    blocked = client.post('/api/runs/start', json=dict(config=real, authorize_real_simulation=True))
    detail = blocked.json()['detail']
    assert blocked.status_code == 409 and detail['code'] == 'task_blocked' and detail['report']['interface_contract']
    assert client.get('/api/runs', params=dict(output_root=str(tmp_path))).json()['runs'] == []   # nothing was created


# ------------------------------------------------------------------------------- connection
def test_connection_endpoints_accept_only_a_profile_identifier(client):
    before = client.get('/api/connection/status', params=dict(profile_id='lab')).json()
    assert before['overall'] == 'unknown' and before['checked_utc'] is None
    checked = client.post('/api/connection/check', json=dict(profile_id='lab', scope='full')).json()
    assert checked['overall'] == 'ok' and checked['trigger'] == 'user' and checked['cost']['evaluations_charged'] == 0
    assert [l['layer'] for l in checked['layers']] == list(LAYERS)
    after = client.get('/api/connection/status', params=dict(profile_id='lab')).json()
    assert after['overall'] == 'ok' and after['age_seconds'] is not None
    for body in (dict(profile_id='lab', host='10.0.0.1'), dict(profile_id='lab', port=22), dict(profile_id='lab', command='id'),
                 dict(profile_id='10.0.0.1:22'), dict(profile_id='../x'), dict(profile_id='lab', scope='everything'),
                 dict(profile_id='lab', env_file='/tmp/evil.env')):
        assert client.post('/api/connection/check', json=body).status_code == 422, body
    profiles = client.get('/api/connection/profiles').json()
    assert profiles['profiles'] == [] and profiles['connection_file_exists'] is False


def test_native_reads_are_gated_and_a_real_snapshot_is_summarised(tmp_path):
    down = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False,
                                 monitor=probe(tmp_path, bridge_package='failed', connection_profile='not_checked',
                                               tunnel='not_checked', daemon='not_checked')))
    blocked = down.post('/api/virtuoso/libraries', json=dict(profile_id='lab'))
    assert blocked.status_code == 409 and blocked.json()['detail']['gate']['blocking'] == ['bridge_package']
    # offline work keeps working while the bridge is down
    assert down.post('/api/config/validate', json=dict(config=config_json(tmp_path))).status_code == 200
    assert down.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='synthetic:ldo'))).json()['loaded']
    snapshot = json.loads((REPO / 'examples/circuits/gpdk045_ota5.cdf.json').read_text())   # captured REAL readback
    summary = bridge_read.summarize_snapshot(snapshot, library='GATOR_TESTS', cell='ota5_v1')
    assert summary['instance_count'] == 5 and summary['instances'][0]['master']['library']
    first = summary['instances'][0]['parameters']
    assert first['w']['raw'] and first['w']['value'] is None                     # CDF strings are shown as read, not guessed
    assert 'parameter semantics and units' in summary['requires_confirmation']
    with pytest.raises(ValueError):
        bridge_read.read(probe(tmp_path), 'lab', 'read_schematic', library='lib; rm -rf /', cell='c')


# ------------------------------------------------------------------------------- agent endpoints
@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    target = bin_dir / 'claude'
    target.write_text(f'#!{sys.executable}\n' + FIXTURE.read_text())
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv('PATH', f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.setenv('FAKE_CLI_SCENARIO', 'success')
    return monkeypatch


def test_agent_proposal_approval_and_application_over_http(client, tmp_path, fake_claude):
    settings = client.get('/api/agent/settings').json()
    assert settings['provider'] == 'claude_code' and 'independent of RL checkpoints' in settings['note']
    raw = config_json(tmp_path)
    proposal = client.post('/api/agent/propose', json=dict(kind='targets', prompt='raise to 0.97', config=raw)).json()
    assert proposal['status'] == 'proposed' and proposal['diff'][0]['key'] == 'score' and proposal['origin'] == 'claude_code'
    not_yet = client.post('/api/agent/apply', json=dict(proposal_id=proposal['proposal_id'], config=raw))
    assert not_yet.status_code == 409 and not_yet.json()['detail']['configuration_unchanged']
    client.post('/api/agent/approve', json=dict(proposal_id=proposal['proposal_id'], proposal_hash=proposal['proposal_hash'], config=raw))
    edited = json.loads(json.dumps(raw))
    edited['run']['max_evaluations'] += 5
    stale = client.post('/api/agent/apply', json=dict(proposal_id=proposal['proposal_id'], config=edited))
    assert stale.status_code == 409 and 'no longer valid' in stale.json()['detail']['message']
    again = client.post('/api/agent/propose', json=dict(kind='targets', prompt='raise to 0.97', config=raw)).json()
    client.post('/api/agent/approve', json=dict(proposal_id=again['proposal_id'], proposal_hash=again['proposal_hash'], config=raw))
    applied = client.post('/api/agent/apply', json=dict(proposal_id=again['proposal_id'], config=raw)).json()
    assert applied['config']['targets'][0]['lower'] == 0.97 and applied['validation']['blocks_run'] is False
    assert 'No circuit was written and no simulation was started' in applied['note']
    fake_claude.setenv('FAKE_CLI_SCENARIO', 'nonzero')
    failed = client.post('/api/agent/propose', json=dict(kind='targets', prompt='x', config=raw))
    assert failed.status_code == 409 and failed.json()['detail']['code'] == 'nonzero_exit' and failed.json()['detail']['configuration_unchanged']


def test_agent_settings_cannot_grant_write_tools_and_manual_mode_works(client, tmp_path, fake_claude):
    for bad in (dict(provider='claude_code', allowed_tools=['Bash']), dict(provider='claude_code', permission_mode='bypassPermissions'),
                dict(provider='nonsense'), dict(provider='claude_code', cli_path='/bin/sh')):
        assert client.put('/api/agent/settings', json=bad).status_code == 422, bad
    assert client.put('/api/agent/settings', json=dict(provider='disabled')).json()['saved']
    raw = config_json(tmp_path)
    disabled = client.post('/api/agent/propose', json=dict(kind='targets', prompt='x', config=raw))
    assert disabled.status_code == 409 and disabled.json()['detail']['code'] == 'disabled'
    task = client.post('/api/agent/export-task', json=dict(kind='targets', prompt='raise it', config=raw)).json()
    assert 'raise it' in task['prompt'] and task['output_json_schema']
    import importlib.util
    spec = importlib.util.spec_from_file_location('fake_cli_fixture', FIXTURE)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    imported = client.post('/api/agent/import-result', json=dict(kind='targets', prompt='raise it', config=raw, result=module.GOOD)).json()
    assert imported['origin'] == 'manual_import' and imported['provider'] == 'disabled'
    diagnostics = client.get('/api/agent/diagnostics').json()
    assert diagnostics['selected'] == 'disabled' and diagnostics['skills']['verification_level']
    assert 'sk-ant' not in json.dumps(diagnostics)


def test_automatic_checks_are_cheap_only_at_start_and_on_profile_change(tmp_path, monkeypatch):
    from gator_workbench import connection as connection_module
    settings_dir = Path(os.environ['GATOR_WORKBENCH_SETTINGS_DIR'])
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / 'bridge_connection.json').write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(env_file='/x/.env')))))
    monitor = probe(tmp_path)
    app = create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=monitor)
    app.state.auto_check_thread.join(timeout=60)
    started = monitor.status('lab')                       # backend start: one automatic check of the active profile
    assert started['trigger'] == 'auto' and started['scope'] == 'cheap' and monitor.probes_started == 1
    http = TestClient(app)
    changed = http.post('/api/connection/check', json=dict(profile_id='lab', scope='cheap', trigger='auto')).json()
    assert changed['trigger'] == 'auto' and changed['cost']['evaluations_charged'] == 0
    for scope in ('interactive', 'full'):                 # an automatic check may never reach Virtuoso or the license server
        assert http.post('/api/connection/check', json=dict(profile_id='lab', scope=scope, trigger='auto')).status_code == 422
    assert http.post('/api/connection/check', json=dict(profile_id='lab', scope='cheap', trigger='gate')).status_code == 422
    assert connection_module.public_profiles()['profiles'][0]['settings_present'] == ['env_file']     # presence only, no values
    quiet = create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path), auto_check_on_start=False)
    assert not hasattr(quiet.state, 'auto_check_thread')


def test_staleness_limit_is_configurable(tmp_path):
    app = create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False,
                     connection_stale_seconds=7.5)
    assert app.state.monitor.stale_after_seconds == 7.5
