"""Follow-up of review round 5 (2026-10-01): the agent CLIs stop with the backend, a proposal is applied once, the ngspice
deck is published whole, the tool relay ignores proxies, and a run paused for infrastructure failures can be resumed."""
import gc
import http.server
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import warnings

import pytest
from fastapi.testclient import TestClient

from gator_workbench import agent_tools, cli as workbench_cli, ngspice_tasks, runs
from gator_workbench.agents import ProposalRejected, base, proposals
from helpers import cli, execute, make_config, roots_for, rows, run_prepared, summary, workbench_app  # noqa: F401 (cli: fixture)
import test_wb_agents

FIXTURES = Path(__file__).parent / 'fixtures'


def sleeper():
    return subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)


# ------------------------------------------------------------------------------- the agent CLIs stop with the backend
def test_stop_all_cancels_every_cli_the_backend_started():
    registry, processes = base.ProcessRegistry(), [sleeper(), sleeper()]
    try:
        for number, process in enumerate(processes):
            registry.register(f'r{number}', process)
        registry.stop_all()
        assert [process.wait(timeout=10) for process in processes] == [-signal.SIGTERM] * 2
        assert registry.was_cancelled('r0') and registry.was_cancelled('r1')    # their requests end as "cancelled"
    finally:
        for process in processes:
            process.kill()


def test_the_app_stops_its_agent_clis_when_it_shuts_down(tmp_path):
    process = sleeper()
    try:
        with TestClient(workbench_app(tmp_path)):
            base.REGISTRY.register('shutdown-test', process)
            assert process.poll() is None
        assert process.wait(timeout=10) == -signal.SIGTERM
    finally:
        base.REGISTRY.done('shutdown-test')
        process.kill()


@pytest.mark.parametrize('ending', ['returns', 'raises'])
def test_serve_bounds_its_wait_for_open_requests_and_stops_the_clis_however_it_ends(monkeypatch, ending):
    import uvicorn
    import gator_workbench.api
    seen, stopped = {}, []

    def run(app, **options):
        seen.update(options)
        if ending == 'raises':
            raise KeyboardInterrupt
    monkeypatch.setattr(uvicorn, 'run', run)
    monkeypatch.setattr(gator_workbench.api, 'create_app', lambda **options: object())
    monkeypatch.setattr(base.REGISTRY, 'stop_all', lambda: stopped.append(True))
    if ending == 'raises':
        with pytest.raises(KeyboardInterrupt):
            workbench_cli.main(['serve', '--port', '1'])
    else:
        assert workbench_cli.main(['serve', '--port', '1']) == 0
    assert seen['timeout_graceful_shutdown'] == workbench_cli.SHUTDOWN_GRACE_SECONDS and stopped == [True]


def children(pid):
    found = []
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                if int((entry / 'stat').read_text().rsplit(')', 1)[1].split()[1]) == pid:
                    found.append(int(entry.name))
            except (OSError, ValueError, IndexError):
                pass
    return found


def running(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


@pytest.mark.skipif(not Path('/proc').is_dir(), reason='reads the process table from /proc')
def test_a_stopped_backend_leaves_no_agent_cli_behind(tmp_path):
    """A real backend, an agent request answered in one piece whose CLI hangs, then `kill` (SIGTERM). Before, the backend
    waited for the request for ever, and a forced stop left the CLI running on its own."""
    directory = tmp_path / 'bin'
    directory.mkdir()
    for name in ('claude', 'codex'):
        (directory / name).write_text(f'#!{sys.executable}\n' + (FIXTURES / 'fake_cli.py').read_text())
        (directory / name).chmod(0o755)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    src = Path(__file__).resolve().parents[2] / 'src'
    env = dict(os.environ, PATH=f'{directory}{os.pathsep}{os.environ["PATH"]}', FAKE_CLI_SCENARIO='hang',
               FAKE_CLI_RECORD=str(tmp_path / 'record.json'), PYTHONPATH=f'{src}{os.pathsep}{os.environ.get("PYTHONPATH", "")}')
    server = subprocess.Popen([sys.executable, '-m', 'gator_workbench.cli', 'serve', '--port', str(port), '--allow-root', str(tmp_path)],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    agents = []
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        body = json.dumps(dict(kind='targets', prompt='raise to 0.97', config=make_config(tmp_path).model_dump(mode='json')))
        threading.Thread(target=lambda: _post(port, body), daemon=True).start()
        while not agents and time.monotonic() < deadline:
            agents = children(server.pid)
            time.sleep(0.05)
        assert agents, 'the agent CLI did not start'
        server.terminate()
        server.wait(timeout=workbench_cli.SHUTDOWN_GRACE_SECONDS + 20)              # waited for ever before
        time.sleep(0.5)
        assert not [pid for pid in agents if running(pid)]                          # and no CLI outlives it
    finally:
        server.kill()
        for pid in agents:
            if running(pid):
                os.killpg(pid, signal.SIGKILL)


def _post(port, body):
    import http.client
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=120)
    try:
        connection.request('POST', '/api/agent/propose', body=body, headers={'Content-Type': 'application/json'})
        connection.getresponse().read()
    except Exception:                         # the backend stops while the request waits: that is the point
        pass


def test_the_live_reader_closes_the_cli_pipes(tmp_path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always', ResourceWarning)
        answer = base.run_cli([sys.executable, '-c', 'import sys; print("out"); print("err", file=sys.stderr)'],
                              stdin_text='', cwd=tmp_path, timeout=30, request_id='pipes', on_line=lambda line: None)
        gc.collect()
    assert answer == (0, 'out\n', 'err\n')
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]     # "unclosed file" for stdout and stderr


# ------------------------------------------------------------------------------- one proposal, applied once
def test_two_presses_of_apply_apply_a_proposal_once(tmp_path, cli, monkeypatch):
    req, store, result = test_wb_agents.proposal_for(tmp_path, cli)
    proposal = store.create(req, result, circuit_hash='c1')
    store.approve(proposal['proposal_id'], proposal_hash=proposal['proposal_hash'], config=req.config, circuit_hash='c1')
    patch = proposals.apply_patch
    monkeypatch.setattr(proposals, 'apply_patch', lambda *a, **k: (time.sleep(0.2), patch(*a, **k))[1])   # a slow apply
    outcomes = []

    def press():
        try:
            outcomes.append(store.apply(proposal['proposal_id'], config=req.config, circuit_hash='c1')['targets'][0]['lower'])
        except ProposalRejected as exc:
            outcomes.append(str(exc))
    presses = [threading.Thread(target=press) for _ in range(2)]
    for thread in presses:
        thread.start()
    for thread in presses:
        thread.join(timeout=10)
    assert sorted(outcomes, key=str) == [0.97, 'The proposal has not been approved']      # both applied it before
    assert store.get(proposal['proposal_id'])['status'] == 'applied'


# ------------------------------------------------------------------------------- the ngspice deck is published whole
DECK = '* a divider\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 2k\n.op\n.end\n'


def test_a_failed_save_leaves_the_deck_before_it_whole(monkeypatch):
    ngspice_tasks.save('divider', DECK)
    deck = ngspice_tasks.task_dir('divider') / ngspice_tasks.FILES['netlist']
    write = Path.write_text

    def half_then_fail(self, text, *args, **kwargs):            # the disk fills up half way through the new deck
        write(self, text[:len(text) // 2], *args, **kwargs)
        raise OSError(28, 'No space left on device')
    with monkeypatch.context() as patched, pytest.raises(OSError):
        patched.setattr(Path, 'write_text', half_then_fail)
        ngspice_tasks.save('divider', DECK.replace('2k', '3k'))
    assert deck.read_text() == DECK                               # it was the half-written new deck before
    assert ngspice_tasks.list_tasks()['divider']['revision'] == 1


# ------------------------------------------------------------------------------- the tool relay ignores proxies
class Recorder(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        self.server.seen.append((self.path, body))
        answer = json.dumps(dict(ok=True)).encode() if self.server.answers else b''
        self.send_response(200 if self.server.answers else 502)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, *args):
        pass


def serving(answers):
    server = http.server.HTTPServer(('127.0.0.1', 0), Recorder)
    server.seen, server.answers = [], answers
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_the_one_time_tool_token_never_goes_through_a_proxy(monkeypatch):
    workbench, proxy = serving(True), serving(False)
    try:
        monkeypatch.setenv('GATOR_TOOLS_URL', f'http://127.0.0.1:{workbench.server_port}')
        monkeypatch.setenv('GATOR_TOOLS_TOKEN', 'secret-token')
        for name in ('http_proxy', 'HTTP_PROXY'):
            monkeypatch.setenv(name, f'http://127.0.0.1:{proxy.server_port}')
        for name in ('no_proxy', 'NO_PROXY'):
            monkeypatch.delenv(name, raising=False)
        assert agent_tools.ask('read', {}) == dict(ok=True)
        assert proxy.seen == [] and b'secret-token' in workbench.seen[0][1]       # the proxy got the token before
    finally:
        workbench.shutdown()
        proxy.shutdown()


# ------------------------------------------------------------------------------- pauses for infrastructure failures
def infrastructure_pause(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2,
                                                           max_consecutive_infrastructure_failures=3,
                                                           max_consecutive_failures=50))
    script = {n: 'timeout' for n in range(3, 40)}
    layout, state = execute(config, tmp_path, scripts={'0': script, '1': script})
    assert state == 'paused' and summary(layout)['stop_reason'] == 'infrastructure_failures'
    return config, layout


def test_a_run_paused_for_infrastructure_failures_continues_when_resumed(tmp_path):
    config, layout = infrastructure_pause(tmp_path)
    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))
    assert run_prepared(again) == 'completed'                     # the link works again; it paused again at once before
    final = summary(layout)
    assert final['stop_reason'] == 'budget_exhausted' and final['totals']['candidate_evaluations_charged'] == 40


def test_a_candidate_a_pause_stops_before_its_launch_is_cancelled_not_a_failure_of_the_link(tmp_path, monkeypatch):
    from analog_optimizer.envs.sizing import CircuitSizingEnv
    layout, _ = runs.prepare_run(make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2)),
                                 roots_for(tmp_path))
    authorize, calls = CircuitSizingEnv.authorize_launches, {}

    def pause_on_the_way(env, allowance, *, stop_file=None):
        authorize(env, allowance, stop_file=stop_file)
        calls[id(env)] = calls.get(id(env), 0) + (allowance > 0)
        if calls[id(env)] == 3 and 'paused' not in calls:       # Pause is pressed while this candidate is on its way
            calls['paused'] = True
            runs.send_command(layout.run_dir, 'pause')
            deadline = time.monotonic() + 30
            while not Path(stop_file).exists() and time.monotonic() < deadline:
                time.sleep(0.005)
    monkeypatch.setattr(CircuitSizingEnv, 'authorize_launches', pause_on_the_way)
    assert run_prepared(layout) == 'paused' and summary(layout)['stop_reason'] == 'user_pause'
    evaluations = rows(layout, 'evaluations')
    stopped = [e for e in evaluations if e['status'] == 'cancelled']
    assert len(stopped) == 1 and stopped[0]['failure_type'] == 'cancelled'
    assert 'stopped before nominal evaluation' in stopped[0]['diagnostics']
    assert not [e for e in evaluations if e['failure_type'] and e['failure_type'].startswith('infrastructure')]


def test_a_resume_that_fails_writing_its_check_gives_the_run_lock_back(tmp_path, monkeypatch):
    config, layout = infrastructure_pause(tmp_path)
    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    monkeypatch.setattr(runs, '_check_consistency', lambda *args: dict(ok=True))     # a saved task's check, written down
    write = runs.write_json

    def full_disk(path, value, **options):
        if Path(path) == layout.manifest and value['segments'][-1].get('consistency_check'):
            raise OSError(28, 'No space left on device')
        return write(path, value, **options)
    with monkeypatch.context() as patched, pytest.raises(OSError):
        patched.setattr(runs, 'write_json', full_disk)
        runs.prepare_run(resumed, roots_for(tmp_path))
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))      # refused as "already running" until a restart before
    runs.take_lock(again.run_dir).release()
