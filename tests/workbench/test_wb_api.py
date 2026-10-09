"""HTTP API: one schema for forms and execution, restricted paths, run control through a detached worker,
connection endpoints. Mock backend and fake probe fixtures only."""
import io
import json
import os
from pathlib import Path
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_read, tasks
from gator_workbench.api.app import attachment, file_snapshot
from gator_workbench.connection import ConnectionMonitor, LAYERS
from gator_workbench.storage.dataset import DatasetReader
from gator_workbench.storage.tables import TABLES
from helpers import make_config, workbench_app
from helpers import probe, wait_for
from gator_workbench import cli as workbench_cli
from gator_workbench.api import app as app_module
from helpers import roots_for
from helpers import prepared

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path):
    app = workbench_app(tmp_path, monitor=probe(tmp_path), auto_check_on_start=True)
    return TestClient(app)


def config_json(tmp_path, **kwargs):
    return make_config(tmp_path, **kwargs).model_dump(mode='json')


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
    assert good['blocks_run'] is False and good['facts']['independent_action_variables'] == 3 and good['mock'] is True
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
    assert kinds['synthetic:gpdk045_ota5']['kind'] == 'mock' and 'MOCK' in kinds['synthetic:gpdk045_ota5']['description']
    assert not [key for key in kinds if key.startswith('real:gpdk045_')]      # every built-in real task was removed (7.128)
    assert 'NativeEnvironmentFactory' in listed['real_interface_contract']['environment_factory']
    loaded = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='synthetic:gpdk045_ota5'))).json()
    assert loaded['loaded'] and loaded['mock'] and set(loaded['hierarchy']) >= {'XU1', 'CL'}
    assert 'MOCK' in loaded['evaluation_backend'] and loaded['provided_metrics'] == ['score']
    blocked = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='real:gpdk045_ota7'))).json()
    assert blocked['loaded'] is False and 'no longer exists' in blocked['blocker']
    native = client.post('/api/circuit/load', json=dict(circuit=dict(source='virtuoso', library='L', cell='C'))).json()
    assert native['loaded'] is False and 'verified circuit profile' in native['blocker']


def test_the_removed_netlist_source_is_refused_in_plain_words(client, tmp_path):
    """User request 2026-09-21 (status record 7.53): "Import Spectre netlist" is gone. A configuration saved before
    still reads, but no circuit is loaded from it - complete or not - so nothing can start from it; and a path
    outside the allowed roots is still refused before anything else."""
    netlist, mapping = str(REPO / 'tests/fixtures/synthetic/ldo.scs'), str(REPO / 'configs/ldo.json')
    for given in (dict(netlist_path=netlist, parser_config_path=mapping), dict(netlist_path=netlist), {}):
        answer = client.post('/api/circuit/load', json=dict(circuit=dict(source='netlist', **given)))
        assert answer.status_code == 200 and answer.json()['loaded'] is False, given
        assert answer.json()['blocker'] == tasks.NETLIST_SOURCE_REMOVED and 'netlist_path' not in answer.json()['blocker']
    saved = config_json(tmp_path)
    saved['circuit'] = dict(saved['circuit'], source='netlist', task_id=None, netlist_path=netlist, parser_config_path=mapping)
    checked = client.post('/api/config/validate', json=dict(config=saved))
    assert checked.status_code == 200 and checked.json()['circuit_blocker']['blocker'] == tasks.NETLIST_SOURCE_REMOVED
    started = client.post('/api/runs/start', json=dict(config=saved))
    assert started.status_code == 409 and started.json()['detail']['code'] == 'task_blocked'
    assert started.json()['detail']['message'] == tasks.NETLIST_SOURCE_REMOVED
    assert not list(tmp_path.rglob('run_manifest.json'))                          # refused before a run directory exists
    outside = tmp_path / 'secret.scs'
    outside.write_text('// x')
    for path in (str(outside), '/etc/passwd', str(REPO / 'configs/../../../etc/passwd')):
        response = client.post('/api/circuit/load', json=dict(circuit=dict(
            source='netlist', netlist_path=path, parser_config_path=mapping)))
        assert response.status_code == 403, path


def test_routes_without_a_caller_are_gone(client):
    # 2026-09-22: circuit changes proposed by the agent (a netlist file nothing could load), the Create profile form's
    # route (Save task replaced it) and the mode suggestion (it comes with /api/runs/model) were removed.
    # 2026-10-06 (record 7.226): the Agent tab's own agent and the LLM search methods.
    for path in ('/api/circuit/modify', '/api/virtuoso/profile', '/api/runs/suggest-mode', '/api/agent/propose',
                 '/api/agent/approve', '/api/agent/apply', '/api/agent/reject', '/api/agent/cancel', '/api/agent/export-task',
                 '/api/agent/import-result', '/api/agent/tools', '/api/runs/llm-hint'):
        assert client.post(path, json={}).status_code in (404, 405), path
    for path in ('/api/agent/settings', '/api/agent/diagnostics', '/api/runs/llm-thread?run_dir=x'):
        assert client.get(path).status_code in (404, 405), path
    # A malformed body is refused with 422 like everywhere else, not a 500.
    for path in ('/api/config/diff', '/api/aggregates/export', '/api/agent/open', '/api/agent/readiness'):
        assert client.post(path, json={'unexpected': 1}).status_code == 422, path


# ------------------------------------------------------------------------------- output settings
def test_output_root_is_visible_checked_and_restricted(client, tmp_path):
    check = client.post('/api/output/check', json=dict(path=str(tmp_path / 'out'), create=True)).json()
    assert check['allowed'] and check['writable'] and check['free_bytes'] > 0 and check['host']
    assert check['mock_data_root'].endswith('/out/mock') and check['windows_mapping'] != 'not_checked'
    assert check['windows_path'] is None or check['windows_mapping'] == 'verified_by_readback'
    # the folder's size only when asked (record 7.189): a look walks nothing
    assert check['bytes_used'] is None
    (tmp_path / 'out' / 'f.bin').write_bytes(b'0123456789')
    assert client.post('/api/output/check', json=dict(path=str(tmp_path / 'out'), usage=True)).json()['bytes_used'] == 10
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
    # The shown columns only are read (record 7.286): no `_json` column, and the same rows as a read of every column.
    assert not any(c.endswith('_json') for c in table['columns']) and all(list(r) == table['columns'] for r in table['rows'])
    whole = DatasetReader(Path(run_dir) / 'data').tail('evaluations', 5).to_pylist()
    assert 'condition_results_json' in whole[0] and [r['evaluation_id'] for r in whole] == [r['evaluation_id'] for r in table['rows']]
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
    csv_file = client.get('/api/runs/download', params=dict(run_dir=run_dir, path=exported['relative']))   # what the button then saves
    assert csv_file.headers['content-disposition'] == f'attachment; filename="{Path(exported["path"]).name}"'
    assert csv_file.text.splitlines()[0] == ','.join(c.name for c in TABLES['metrics']['columns'])
    package = client.post('/api/runs/export-package', json=dict(run_dir=run_dir))
    assert package.headers['content-disposition'] == f'attachment; filename="{Path(run_dir).name}__data.zip"'   # named after its run
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


def fabricated_run(tmp_path):
    """A run directory as far as the download routes care: inside an allowed root, with a manifest."""
    run = tmp_path / 'exp__0123456789ab' / 'runs' / 'task' / 'scratch__seed0__abcdef012345'
    (run / 'logs').mkdir(parents=True)
    (run / 'run_manifest.json').write_text(json.dumps(dict(run_id='abcdef012345', mock=True)))
    return run


def test_a_download_is_the_file_as_it_was_when_the_download_started(client, tmp_path):
    """The Logs tab downloads the log of a run that is still writing it."""
    run = fabricated_run(tmp_path)
    log, params = run / 'logs' / 'events.jsonl', dict(run_dir=str(run), path='logs/events.jsonl')
    complete = b''.join(json.dumps(dict(event='e', n=n)).encode() + b'\n' for n in range(3))
    log.write_bytes(complete + b'{"event":"torn' + b'x' * 100_000)       # a last line that is still being written
    size, chunks = file_snapshot(log)
    with log.open('ab') as stream:                                        # ...and the run logs on during the transfer
        stream.write(b'"}\n{"event":"later"}\n')
    assert size == len(complete) and b''.join(chunks) == complete         # neither the torn line nor the later ones
    log.write_bytes(complete + b'{"event":"torn')
    sent = client.get('/api/runs/download', params=params)
    assert sent.content == complete and sent.headers['content-length'] == str(len(complete))
    assert sent.headers['content-disposition'] == 'attachment; filename="events.jsonl"'
    log.write_bytes(b'{"event":"torn')                                    # no complete line yet: an empty file, not an error
    assert client.get('/api/runs/download', params=params).content == b''
    (run / 'notes.txt').write_bytes(b'no newline at the end')              # only a JSONL is cut back to whole lines
    assert client.get('/api/runs/download', params=dict(params, path='notes.txt')).content == b'no newline at the end'
    assert client.get('/api/runs/download', params=dict(params, path='logs/errors.jsonl')).status_code == 404   # nothing logged
    assert attachment('résumé.csv') == {'Content-Disposition': "attachment; filename*=utf-8''r%C3%A9sum%C3%A9.csv"}


def test_research_csvs_are_downloadable_as_one_zip(client, tmp_path):
    """They lie in <experiment>/aggregates, above the run directory, where the per-file download cannot reach."""
    params = dict(run_dir=str(fabricated_run(tmp_path)))
    nothing = client.get('/api/aggregates/download', params=params)
    assert nothing.status_code == 404 and 'exported' in nothing.json()['detail']['message']
    written = client.post('/api/aggregates/export', json=params).json()
    (Path(written['experiment_dir']) / 'aggregates' / 'notes.txt').write_text('not an export')
    package = client.get('/api/aggregates/download', params=params)
    assert package.headers['content-disposition'] == 'attachment; filename="exp__0123456789ab__aggregates.zip"'
    members = zipfile.ZipFile(io.BytesIO(package.content)).namelist()
    assert sorted(members) == sorted(f'{table}{suffix}' for table in written['files'] for suffix in ('.csv', '.meta.json'))
    assert len(members) == 12 and client.get('/api/aggregates/download', params=dict(run_dir='/etc')).status_code == 403


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
    real['circuit'] = dict(source='registered_task', task_id='real:gpdk045_ota7')
    blocked = client.post('/api/runs/start', json=dict(config=real, authorize_real_simulation=True))
    detail = blocked.json()['detail']
    assert blocked.status_code == 409 and detail['code'] == 'task_blocked' and 'no longer exists' in json.dumps(detail)
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
    down = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path, bridge_package='failed', connection_profile='not_checked',
                                               tunnel='not_checked', daemon='not_checked'), auto_check_on_start=True))
    blocked = down.post('/api/virtuoso/libraries', json=dict(profile_id='lab'))
    assert blocked.status_code == 409 and blocked.json()['detail']['gate']['blocking'] == ['bridge_package']
    # offline work keeps working while the bridge is down
    assert down.post('/api/config/validate', json=dict(config=config_json(tmp_path))).status_code == 200
    assert down.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='synthetic:gpdk045_ota5'))).json()['loaded']
    snapshot = json.loads((REPO / 'examples/circuits/gpdk045_ota5.cdf.json').read_text())   # captured REAL readback
    summary = bridge_read.summarize_snapshot(snapshot, library='GATOR_TESTS', cell='ota5_v1')
    assert summary['instance_count'] == 5 and summary['instances'][0]['master']['library']
    first = summary['instances'][0]['parameters']
    assert first['w']['raw'] and first['w']['value'] is None                     # CDF strings are shown as read, not guessed
    assert 'parameter semantics and units' in summary['requires_confirmation']
    with pytest.raises(ValueError):
        bridge_read.read(probe(tmp_path), 'lab', 'read_schematic', library='lib; rm -rf /', cell='c')


def test_cells_of_a_library_are_listed_with_their_views(tmp_path):
    """The Library -> Cell dropdowns (user request 2026-09-20). Fake reader process; no Virtuoso."""
    parsed = bridge_read.parse_cells('ota5_v1|views=symbol schematic maestro \nR_only|views=symbol \n\n'
                                     'bad name|views=schematic \nx|views=sch;ematic layout \n')
    assert parsed == [dict(name='ota5_v1', views=['maestro', 'schematic', 'symbol'], has_schematic=True),
                      dict(name='R_only', views=['symbol'], has_schematic=False),
                      dict(name='x', views=['layout'], has_schematic=False)]        # names that are not plain Cadence names are dropped
    assert 'ddGetObj("%s")' in bridge_read.CELLS_SKILL                               # read-only dd calls, as in the bridge's example
    assert not any(call in bridge_read.CELLS_SKILL for call in ('dbOpen', 'dbSave', 'ddDelete', 'hiOpen', 'geOpen'))
    fake = tmp_path / 'reader.py'
    fake.write_text('import json, sys\nprint(json.dumps(dict(argv=sys.argv[1:], cells=[], truncated=False)))\n')
    listed = bridge_read.read(probe(tmp_path), 'lab', 'cells', library='GATOR_TESTS', command=[sys.executable, str(fake)])
    assert listed['argv'] == ['--profile-id', 'lab', '--op', 'cells', '--library', 'GATOR_TESTS']
    for bad in (None, 'a"b', 'lib) ddDeleteObj(x'):                                   # nothing but a plain name reaches the SKILL text
        with pytest.raises(ValueError):
            bridge_read.read(probe(tmp_path), 'lab', 'cells', library=bad, command=[sys.executable, str(fake)])
    down = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path, tunnel='failed', daemon='not_checked')))
    blocked = down.post('/api/virtuoso/cells', json=dict(profile_id='lab', library='GATOR_TESTS'))
    assert blocked.status_code == 409 and blocked.json()['detail']['gate']['blocking'] == ['tunnel']


def test_automatic_checks_are_cheap_only_at_start_and_on_profile_change(tmp_path, monkeypatch):
    from gator_workbench import connection as connection_module
    settings_dir = Path(os.environ['GATOR_WORKBENCH_SETTINGS_DIR'])
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / 'bridge_connection.json').write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(env_file='/x/.env')))))
    monitor = probe(tmp_path)
    app = workbench_app(tmp_path, monitor=monitor, auto_check_on_start=True)
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
    quiet = workbench_app(tmp_path, monitor=probe(tmp_path))
    assert not hasattr(quiet.state, 'auto_check_thread')


def test_staleness_limit_is_configurable(tmp_path):
    app = workbench_app(tmp_path, connection_stale_seconds=7.5)
    assert app.state.monitor.stale_after_seconds == 7.5


def test_serve_checks_the_connection_at_start_only_when_asked(monkeypatch):
    """User request 2026-09-20: a check runs on a button press, so `serve` starts none unless the flag is given."""
    from gator_workbench import cli
    seen = []
    monkeypatch.setattr('gator_workbench.api.create_app', lambda **kwargs: seen.append(kwargs) or object())
    monkeypatch.setattr('uvicorn.run', lambda *args, **kwargs: None)
    assert cli.main(['serve']) == 0 and cli.main(['serve', '--connection-check-on-start']) == 0
    assert [kwargs['auto_check_on_start'] for kwargs in seen] == [False, True]


def test_the_last_routes_that_took_a_nul_byte_as_a_server_error_refuse_it(tmp_path):
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    bad = str(tmp_path / 'a\x00b')
    circuit = dict(source='registered_task', task_id='synthetic:gpdk045_ota5', netlist_path=bad)
    assert client.post('/api/circuit/load', json=dict(circuit=circuit)).status_code == 403
    assert client.post('/api/ngspice/read', json=dict(path=bad)).status_code == 403
    check = client.post('/api/ngspice/check', json=dict(text='* a deck\nR1 a 0 1k\n.end\n', source_path=bad))
    assert check.status_code < 500                                         # the deck is checked; the bad path is ignored


# ------------------------------------------------------------------------------- a stop never waits for ever
@pytest.mark.parametrize('ending', ['returns', 'raises'])
def test_serve_bounds_its_wait_for_open_requests_however_it_ends(monkeypatch, ending):
    import uvicorn
    import gator_workbench.api
    seen = {}

    def run(app, **options):
        seen.update(options)
        if ending == 'raises':
            raise KeyboardInterrupt
    monkeypatch.setattr(uvicorn, 'run', run)
    monkeypatch.setattr(gator_workbench.api, 'create_app', lambda **options: object())
    if ending == 'raises':
        with pytest.raises(KeyboardInterrupt):
            workbench_cli.main(['serve', '--port', '1'])
    else:
        assert workbench_cli.main(['serve', '--port', '1']) == 0
    assert seen['timeout_graceful_shutdown'] == workbench_cli.SHUTDOWN_GRACE_SECONDS


# ------------------------------------------------------------------------------- A15: the Host allowlist
@pytest.mark.parametrize('host, status', [('127.0.0.1:8765', 200), ('localhost:8765', 200), ('[::1]:8765', 200), ('testserver', 200),
                                          ('rebound.example', 400), ('rebound.example:8765', 400), ('127.0.0.1.nip.io', 400)])
def test_only_the_names_the_backend_is_served_under_are_answered(tmp_path, host, status):
    client = TestClient(workbench_app(tmp_path))
    assert client.get('/api/connection/profiles', headers={'Host': host}).status_code == status


def test_the_host_the_operator_serves_on_is_answered_too(tmp_path):
    client = TestClient(workbench_app(tmp_path, host='192.168.1.50'))
    assert client.get('/api/connection/profiles', headers={'Host': '192.168.1.50:8765'}).status_code == 200
    assert client.get('/api/connection/profiles', headers={'Host': 'rebound.example'}).status_code == 400
    assert app_module.trusted_hosts('2001:db8::5')[-1] == '[2001:db8::5]'
    assert app_module.trusted_hosts('Lab-PC.local')[-2:] == ['Lab-PC.local', 'lab-pc.local']
    assert app_module.trusted_hosts('::1') == app_module.trusted_hosts('localhost') == app_module.trusted_hosts()
    assert app_module.trusted_hosts('0.0.0.0') == app_module.trusted_hosts('::') == ['*']   # every interface: names unknown


def test_serve_hands_its_host_to_the_app(monkeypatch):
    import uvicorn
    from gator_workbench import api, cli as cli_module
    made, served = {}, {}
    monkeypatch.setattr(api, 'create_app', lambda **options: made.update(options) or 'app')
    monkeypatch.setattr(uvicorn, 'run', lambda app, **options: served.update(app=app, **options))
    assert cli_module.main(['serve', '--host', '192.168.1.50', '--port', '8799']) == 0
    assert made['host'] == '192.168.1.50' and served == dict(app='app', host='192.168.1.50', port=8799, log_level='info',
                                                             timeout_graceful_shutdown=cli_module.SHUTDOWN_GRACE_SECONDS)


# ------------------------------------------------------------------------------- A16: malformed bodies and NUL bytes
def test_a_malformed_model_request_is_refused_not_a_server_error(tmp_path):
    layout, _ = prepared(tmp_path)
    client = TestClient(workbench_app(tmp_path))
    for body in ({}, dict(run_dir=str(layout.run_dir), checkpoint_id=5), dict(run_dir=['x']),
                 dict(run_dir=str(layout.run_dir), config=[1]), dict(run_dir=str(layout.run_dir), unexpected=1)):
        assert client.post('/api/runs/model', json=body).status_code == 422, body
    # what the page sends is still answered as before: no save point yet is a 404, a foreign folder a 403
    assert client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest')).status_code == 404
    assert client.post('/api/runs/model', json=dict(run_dir='/etc', checkpoint_id='latest', config=None)).status_code == 403


def test_a_nul_byte_in_a_path_is_refused_like_any_other_bad_path(tmp_path):
    layout, _ = prepared(tmp_path)
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    bad = str(tmp_path / 'a\x00b')
    assert client.get('/api/runs/status', params=dict(run_dir=bad)).status_code == 403
    assert client.get('/api/output/browse', params=dict(path=bad)).status_code == 403
    assert client.get('/api/runs', params=dict(output_root=bad)).status_code == 403
    assert client.get('/api/runs/models', params=dict(output_root=bad)).status_code == 403
    assert client.get('/api/runs/download', params=dict(run_dir=str(layout.run_dir), path='run_manifest.json\x00')).status_code == 403
    check = client.post('/api/output/check', json=dict(path=bad))
    assert check.status_code == 200 and check.json()['allowed'] is False and 'NUL' in check.json()['error']
    assert roots_for(tmp_path).is_allowed(bad) is False
