"""The agent's own tools (status record 7.68): the agent may READ from Virtuoso and WRITE the Maestro setup of the task's
WORKING COPY, and nothing else. Fake CLI and fake Virtuoso only - no agent and no Virtuoso is reached by these tests.

The end-to-end test starts the workbench under uvicorn and lets the FAKE CLI do what a real one does: start the tool
server named in `--mcp-config` and speak MCP to it. So the chain protocol -> server -> backend route -> session ->
workbench function is exercised as it runs in production; only the CLI and Virtuoso are doubles."""
import json
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import agent_tools as tool_server
from gator_workbench import bridge_read, working_copy
from gator_workbench.agents import AgentError, AgentRequest, AgentSettings, ClaudeCodeProvider
from gator_workbench.agents import base, tools as catalog
from gator_workbench.api import create_app
from helpers import make_config

FIXTURES = Path(__file__).parent / 'fixtures'
FAKE = FIXTURES / 'fake_cli.py'
sys.path.insert(0, str(FIXTURES))
import fake_cli                                                        # noqa: E402

COPY = dict(copy=dict(library='RING_GATOR', testbench='tb_ring', cells=['ring', 'tb_ring']),
            original=dict(library='RING', cell='ring'), schematics=[['RING_GATOR', 'ring']], state_dir=None)
SETUP_NOW = dict(test='GATOR', analyses={'tran': {'stop': '20n'}}, outputs=[dict(name='osc_frequency_hz', expression='frequency(VT("/OUT"))')],
                 specs=[dict(output='osc_frequency_hz', op='gt', value='1.1G')], variables={}, bindings=[])


@pytest.fixture
def fake_virtuoso(tmp_path, monkeypatch):
    """Every Virtuoso call of the tools, answered locally. Records what was asked."""
    asked = []
    state = tmp_path / 'copy-state'
    state.mkdir()
    target = dict(COPY, state_dir=str(state))

    def read(monitor, profile_id, op, **names):
        asked.append(dict(op=op, **names))
        if op == 'libraries':
            return dict(libraries=['RING', 'RING_GATOR', 'gpdk045'])
        if op == 'cells':
            return dict(cells=[dict(cell='ring', views=['schematic', 'symbol'])])
        return dict(schematic=dict(instances=[dict(name='M0', master='nmos', parameters=dict(w='1u'))], nets=['OUT']))

    def read_setup_on(monitor, profile_id, wanted, **kwargs):
        asked.append(dict(op='read_setup'))
        return dict(SETUP_NOW, rows=dict(measurements=[], targets=[]), fingerprint='fixture')

    def write_setup_on(monitor, profile_id, wanted, setup, **kwargs):
        asked.append(dict(op='write_setup', setup=setup))
        return dict(setup, matches=True, differences=[], written=setup, rows=dict(measurements=[], targets=[]))

    monkeypatch.setattr(bridge_read, 'read', read)
    monkeypatch.setattr(working_copy, 'read_setup_on', read_setup_on)
    monkeypatch.setattr(working_copy, 'write_setup_on', write_setup_on)
    monkeypatch.setattr(working_copy, 'draft_target', lambda library, cell: target)
    monkeypatch.setattr(working_copy, 'bindable_on', lambda wanted: {('tb_ring', 'C0'): {'c'}})
    monkeypatch.setattr(working_copy, 'last_written', lambda wanted: {})
    monkeypatch.setattr(working_copy, 'default_model_files', lambda profile_id: [['/pdk/gpdk045.scs', 'tt']])
    return asked


def session(asked, **kwargs):
    return catalog.ToolSession(request_id='req-0001', token='t0', kind='virtuoso_work', monitor=None, profile_id='lab',
                               names=tuple(catalog.granted('virtuoso_work')),
                               target=lambda: dict(COPY, state_dir='/tmp/state'),
                               read=lambda op, **names: bridge_read.read(None, 'lab', op, **names), **kwargs)


# ------------------------------------------------------------------------------- what the tools do and refuse
def test_the_granted_tools_are_the_ones_the_kind_may_use():
    assert catalog.granted('virtuoso_work') == tuple(catalog.TOOLS)
    for kind in ('draft_config', 'settings_review', 'run_review', 'virtuoso_setup'):
        assert catalog.granted(kind) == (), kind                    # only a tool kind has tools at all
    assert base.TOOL_KINDS == ('virtuoso_work',)
    assert [t['name'] for t in catalog.described(catalog.granted('virtuoso_work'))] == list(catalog.TOOLS)
    assert all(t['inputSchema']['type'] == 'object' for t in catalog.described(catalog.granted('virtuoso_work')))
    assert not any(TOOL['writes'] for name, TOOL in catalog.TOOLS.items() if name != 'working_copy_write_setup')


def test_reading_goes_through_the_workbench(fake_virtuoso):
    live = session(fake_virtuoso)
    assert live.call('virtuoso_libraries', {})['result']['libraries'][0] == 'RING'
    assert live.call('virtuoso_cells', dict(library='gpdk045'))['ok']
    assert live.call('virtuoso_read_cell', dict(library='RING', cell='ring'))['result']['schematic']['nets'] == ['OUT']
    facts = live.call('working_copy_facts', {})['result']
    assert facts['copy']['library'] == 'RING_GATOR' and facts['bindable'] == [dict(cell='tb_ring', instance='C0', parameters=['c'])]
    assert 'frequency' in facts['allowed_functions'] and facts['model_files'] == [['/pdk/gpdk045.scs', 'tt']]
    assert live.call('working_copy_setup', {})['result']['analyses'] == {'tran': {'stop': '20n'}}
    assert [a['op'] for a in fake_virtuoso] == ['libraries', 'cells', 'read_schematic', 'read_setup']
    assert [c['tool'] for c in live.history] == ['virtuoso_libraries', 'virtuoso_cells', 'virtuoso_read_cell',
                                                 'working_copy_facts', 'working_copy_setup']
    assert all(c['ok'] for c in live.history)


def test_writing_touches_the_copy_only_and_keeps_what_it_is_not_given(fake_virtuoso):
    live = session(fake_virtuoso)
    answer = live.call('working_copy_write_setup', dict(analyses={'tran': {'stop': '50n'}},
                                                        outputs=[dict(name='gain', expression='ymax(VF("/OUT"))')]))
    assert answer['ok'] and answer['result']['matches'] and answer['result']['copy']['library'] == 'RING_GATOR'
    written = [a for a in fake_virtuoso if a['op'] == 'write_setup'][0]['setup']
    assert written['analyses'] == {'tran': {'stop': '50n'}} and written['outputs'][0]['name'] == 'gain'
    assert written['specs'] == SETUP_NOW['specs']                    # not given: the copy keeps what it has (read first)
    assert written['variables'] is None and written['bindings'] is None
    assert [a['op'] for a in fake_virtuoso] == ['read_setup', 'write_setup'] and live.wrote is True


def test_a_tool_outside_the_grant_is_refused_and_the_target_is_not_the_agents_to_choose(fake_virtuoso):
    live = session(fake_virtuoso)
    for name in ('run_simulation', 'write_cell', 'mcp__gator__shell', 'working_copy_write_sizes'):
        answer = live.call(name, {})
        assert not answer['ok'] and 'not one of the tools' in answer['error'], name
    lean = session(fake_virtuoso)
    lean.names = ('virtuoso_libraries',)
    assert not lean.call('working_copy_write_setup', {})['ok']
    # The copy is resolved by the backend: a library/cell in the arguments is simply not part of the write tool's schema.
    assert 'library' not in catalog.TOOLS['working_copy_write_setup']['schema']['properties']
    assert live.call('virtuoso_libraries', dict(library='../etc'))['ok'] is False       # additionalProperties false; the handler takes none


def test_a_refused_setup_and_a_blocked_connection_are_answers_not_crashes(fake_virtuoso, monkeypatch):
    from gator_workbench import virtuoso_setup
    live = session(fake_virtuoso)

    def refuse(*args, **kwargs):
        raise virtuoso_setup.SetupError('The setup cannot be written: osc: system(...) is not a calculator function')
    monkeypatch.setattr(working_copy, 'write_setup_on', refuse)
    answer = live.call('working_copy_write_setup', dict(outputs=[], specs=[]))
    assert not answer['ok'] and 'not a calculator function' in answer['error']

    def blocked(*args, **kwargs):
        raise PermissionError('The connection gate blocked reading the native design')
    monkeypatch.setattr(bridge_read, 'read', blocked)
    answer = live.call('virtuoso_libraries', {})
    assert not answer['ok'] and 'refused the Virtuoso connection' in answer['error']
    assert live.calls == 2 and live.wrote is False


def test_the_budget_and_the_closed_session(fake_virtuoso):
    live = session(fake_virtuoso)
    for _ in range(catalog.MAX_WRITES):
        assert live.call('working_copy_write_setup', dict(outputs=[], specs=[]))['ok']
    stopped = live.call('working_copy_write_setup', dict(outputs=[], specs=[]))
    assert not stopped['ok'] and 'limit' in stopped['error'] and live.writes == catalog.MAX_WRITES
    live.calls = catalog.MAX_CALLS
    assert 'tool calls' in live.call('virtuoso_libraries', {})['error']
    live.close()
    assert 'over' in live.call('virtuoso_libraries', {})['error']


# ------------------------------------------------------------------------------- the tool server (MCP over stdin/stdout)
def rpc(monkeypatch, messages, answers):
    """Feed `messages` to the server with the backend answering `answers`; returns what it wrote on stdout."""
    import io
    sent = []

    def ask(method, payload):
        sent.append(dict(method=method, **payload))
        return answers.pop(0) if answers else dict(ok=False, error='nothing')
    monkeypatch.setattr(tool_server, 'ask', ask)
    out = io.StringIO()
    tool_server.main(stdin=io.StringIO('\n'.join(json.dumps(m) for m in messages) + '\n'), stdout=out)
    return [json.loads(line) for line in out.getvalue().splitlines()], sent


def test_the_tool_server_speaks_the_protocol_and_decides_nothing(monkeypatch):
    written, sent = rpc(monkeypatch, [
        dict(jsonrpc='2.0', id=1, method='initialize', params=dict(protocolVersion='2026-07-28')),
        dict(jsonrpc='2.0', method='notifications/initialized'),
        dict(jsonrpc='2.0', id=2, method='ping'),
        dict(jsonrpc='2.0', id=3, method='tools/list'),
        dict(jsonrpc='2.0', id=4, method='tools/call', params=dict(name='virtuoso_libraries', arguments={})),
        dict(jsonrpc='2.0', id=5, method='tools/call', params=dict(name='nope', arguments={})),
        dict(jsonrpc='2.0', id=6, method='resources/list'),
        'not json', dict(jsonrpc='2.0', id=7, method='initialize'),
    ], [dict(tools=[dict(name='virtuoso_libraries', description='d', inputSchema={})]),
        dict(ok=True, result=dict(libraries=['RING'])), dict(ok=False, error='nope is not one of the tools')])
    answers = {w.get('id'): w for w in written}
    assert answers[1]['result']['protocolVersion'] == '2026-07-28'        # the client's version is answered
    assert answers[1]['result']['capabilities']['tools'] == dict(listChanged=False)
    assert answers[2]['result'] == {} and answers[7]['result']['serverInfo']['name'] == 'gator'
    assert [t['name'] for t in answers[3]['result']['tools']] == ['virtuoso_libraries']
    assert answers[4]['result']['isError'] is False and 'RING' in answers[4]['result']['content'][0]['text']
    assert answers[5]['result']['isError'] is True and 'not one of the tools' in answers[5]['result']['content'][0]['text']
    assert answers[6]['error']['code'] == -32601                          # what it does not offer, it says so
    assert len(written) == 7 and [s['method'] for s in sent] == ['list', 'call', 'call']     # the notification and the junk line: no answer
    assert sent[1]['name'] == 'virtuoso_libraries'                        # it relays, it decides nothing


def test_the_tool_server_says_so_when_the_workbench_is_gone(monkeypatch):
    monkeypatch.setenv('GATOR_TOOLS_URL', 'http://127.0.0.1:1')           # nothing listens there
    monkeypatch.setenv('GATOR_TOOLS_TOKEN', 'x')
    answer = tool_server.ask('call', dict(name='virtuoso_libraries', arguments={}))
    assert answer['ok'] is False and 'could not be reached' in answer['error']


# ------------------------------------------------------------------------------- what the CLI is started with
def request_for(tmp_path, kind='virtuoso_work', **kwargs):
    return AgentRequest(kind=kind, user_prompt='Set this up', config=make_config(tmp_path).model_dump(mode='json'),
                        circuit_summary=dict(devices=[]), copy=dict(copy=COPY['copy']), **kwargs)


def test_the_cli_is_given_exactly_the_granted_tools_and_no_other_server(tmp_path):
    provider = ClaudeCodeProvider(AgentSettings(provider='claude_code'))
    request = request_for(tmp_path, tools=tuple(catalog.granted('virtuoso_work')), tools_url='http://127.0.0.1:8765',
                          tools_token='secret-token')
    directory, config = claude_config(provider, request)
    argv = provider.build_argv('claude', request, mcp_config=config)
    allowed = argv[argv.index('--allowedTools') + 1].split(',')
    assert allowed == catalog.mcp_names(catalog.granted('virtuoso_work'))
    assert '--strict-mcp-config' in argv and argv[argv.index('--mcp-config') + 1] == config
    server = json.loads(Path(config).read_text())['mcpServers']['gator']
    assert server['args'] == ['-m', 'gator_workbench.agent_tools']
    assert server['env']['GATOR_TOOLS_TOKEN'] == 'secret-token' and server['env']['GATOR_TOOLS_URL'] == 'http://127.0.0.1:8765'
    assert Path(config).stat().st_mode & 0o077 == 0                     # the token is not world-readable
    denied = argv[argv.index('--disallowedTools') + 1]
    assert 'Bash' in denied and 'WebSearch' in denied                   # the built-in deny list is unchanged
    import shutil
    shutil.rmtree(directory, ignore_errors=True)


def claude_config(provider, request):
    from gator_workbench.agents.claude_code import tool_server_config
    return tool_server_config(request)


def test_a_request_without_tools_gets_an_empty_server_set(tmp_path):
    provider = ClaudeCodeProvider(AgentSettings(provider='claude_code'))
    argv = provider.build_argv('claude', request_for(tmp_path, kind='virtuoso_setup'))
    assert argv[argv.index('--mcp-config') + 1] == '{"mcpServers":{}}' and '--strict-mcp-config' in argv
    assert '--allowedTools' not in argv
    assert claude_config(provider, request_for(tmp_path, kind='virtuoso_setup')) == (None, None)


def test_the_settings_file_can_neither_widen_nor_add_a_tool(tmp_path):
    for bad in (('Bash',), ('mcp__gator__working_copy_write_setup',), ('Read', 'Write')):
        with pytest.raises(AgentError) as error:
            AgentSettings(provider='claude_code', allowed_tools=bad).validate()
        assert error.value.code == 'invalid_request'
    assert AgentSettings(provider='claude_code', allowed_tools=('Read',)).validate()


def test_a_kind_without_a_grant_cannot_carry_tools_and_the_web_never_meets_them(tmp_path):
    with pytest.raises(AgentError) as error:
        request_for(tmp_path, kind='draft_config', tools=('virtuoso_libraries',), tools_url='u', tools_token='t').validate()
    assert 'not granted workbench tools' in error.value.detail
    with pytest.raises(AgentError):
        request_for(tmp_path, tools=('virtuoso_libraries',)).validate()                 # no address, no token
    hostile = request_for(tmp_path, tools=tuple(catalog.granted('virtuoso_work')), tools_url='u', tools_token='t')
    hostile.web = True
    with pytest.raises(AgentError) as error:                     # refused twice over: not a settings_review, and tools
        hostile.validate()
    assert 'online research' in error.value.detail or 'may not read the web' in error.value.detail
    assert 'settings_review' not in base.TOOL_KINDS and 'run_review' not in base.TOOL_KINDS      # the web and the tools never meet
    web_kind = request_for(tmp_path, kind='settings_review')
    web_kind.web = True
    assert web_kind.validate() and catalog.granted('settings_review') == ()


def test_a_denied_tool_outside_the_grant_is_counted_not_fatal(tmp_path):
    provider = ClaudeCodeProvider(AgentSettings(provider='claude_code'))
    request = request_for(tmp_path, tools=tuple(catalog.granted('virtuoso_work')), tools_url='u', tools_token='t')
    answer = json.dumps(dict(type='result', subtype='success', is_error=False, structured_output=dict(fake_cli.GOOD),
                             permission_denials=[dict(tool_name='Bash'), dict(tool_name='mcp__other__write')]))
    result = provider.parse(request, 0, answer, '')
    assert result.audit['tool_calls_refused'] == 2 and result.audit['tools_refused_names'] == ['Bash', 'mcp__other__write']
    granted_denial = json.dumps(dict(type='result', subtype='success', is_error=False, structured_output=dict(fake_cli.GOOD),
                                     permission_denials=[dict(tool_name='mcp__gator__working_copy_write_setup')]))
    with pytest.raises(AgentError) as error:
        provider.parse(request, 0, granted_denial, '')
    assert error.value.code == 'permission_denied'                       # a GRANTED tool refused all the same is a fault


# ------------------------------------------------------------------------------- the whole chain, over a real socket
@pytest.fixture
def cli(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    target = bin_dir / 'claude'
    target.write_text(f'#!{sys.executable}\n' + FAKE.read_text())
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    record = tmp_path / 'record.json'
    monkeypatch.setenv('PATH', f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.setenv('FAKE_CLI_RECORD', str(record))
    monkeypatch.setenv('FAKE_CLI_SCENARIO', 'tools')
    return record


@pytest.fixture
def server(tmp_path):
    import uvicorn
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    app = create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False)
    instance = uvicorn.Server(uvicorn.Config(app, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=instance.run, kwargs=dict(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(300):
        if instance.started:
            break
        time.sleep(0.02)
    yield f'http://127.0.0.1:{sock.getsockname()[1]}'
    instance.should_exit = True
    thread.join(timeout=10)


def test_the_agent_reads_and_writes_through_the_running_workbench(server, cli, tmp_path, fake_virtuoso, monkeypatch):
    import urllib.request
    calls = [['working_copy_facts', {}], ['virtuoso_cells', dict(library='RING_GATOR')],
             ['working_copy_write_setup', dict(analyses={'tran': {'stop': '50n'}},
                                               outputs=[dict(name='osc_frequency_hz', expression='frequency(VT("/OUT"))')],
                                               specs=[dict(output='osc_frequency_hz', op='gt', value='1.1G')])],
             ['working_copy_read_sizes', {}]]                            # never granted: the chain must refuse it
    monkeypatch.setenv('FAKE_CLI_TOOL_CALLS', json.dumps(calls))
    config = make_config(tmp_path).model_dump(mode='json')
    config['circuit'] = dict(config['circuit'], source='virtuoso', library='RING', cell='ring')
    body = json.dumps(dict(kind='virtuoso_work', prompt='Set this circuit up', config=config)).encode()
    answer = urllib.request.urlopen(urllib.request.Request(f'{server}/api/agent/propose', data=body,
                                                           headers={'Content-Type': 'application/json'}), timeout=120)
    proposal = json.loads(answer.read())
    assert proposal['kind'] == 'virtuoso_work' and proposal['status'] == 'proposed'
    assert proposal['virtuoso_copy_written'] is True
    assert [c['tool'] for c in proposal['tool_calls']] == ['working_copy_facts', 'virtuoso_cells', 'working_copy_write_setup',
                                                           'working_copy_read_sizes']
    assert [c['ok'] for c in proposal['tool_calls']] == [True, True, True, False]
    seen = json.loads(Path(str(cli)).read_text())['tools']
    assert seen[0]['initialize']['result']['serverInfo']['name'] == 'gator'
    assert seen[1]['tools'] == list(catalog.TOOLS)                       # the server offers exactly this request's grant
    assert json.loads(seen[2]['text'])['copy']['library'] == 'RING_GATOR'
    assert seen[4]['isError'] is False and json.loads(seen[4]['text'])['matches'] is True
    assert seen[5]['isError'] is True and 'not one of the tools' in seen[5]['text']
    assert [a['op'] for a in fake_virtuoso if a['op'] == 'write_setup'], 'the setup reached the workbench function'


def test_the_tools_are_closed_when_the_request_is_over(server, cli, tmp_path, fake_virtuoso, monkeypatch):
    import urllib.error
    import urllib.request
    monkeypatch.setenv('FAKE_CLI_TOOL_CALLS', json.dumps([['working_copy_facts', {}]]))
    config = make_config(tmp_path).model_dump(mode='json')
    config['circuit'] = dict(config['circuit'], source='virtuoso', library='RING', cell='ring')
    body = json.dumps(dict(kind='virtuoso_work', prompt='Set this up', config=config)).encode()
    urllib.request.urlopen(urllib.request.Request(f'{server}/api/agent/propose', data=body,
                                                  headers={'Content-Type': 'application/json'}), timeout=120).read()
    late = urllib.request.Request(f'{server}/api/agent/tools',
                                  data=json.dumps(dict(token='any', method='list')).encode(),
                                  headers={'Content-Type': 'application/json'})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(late, timeout=30)
    assert error.value.code == 403                                       # no token works once the request has ended


def test_the_request_directory_stays_empty(server, cli, tmp_path, fake_virtuoso, monkeypatch):
    import urllib.request
    monkeypatch.setenv('FAKE_CLI_TOOL_CALLS', json.dumps([]))
    config = make_config(tmp_path).model_dump(mode='json')
    config['circuit'] = dict(config['circuit'], source='virtuoso', library='RING', cell='ring')
    body = json.dumps(dict(kind='virtuoso_work', prompt='Set this up', config=config)).encode()
    urllib.request.urlopen(urllib.request.Request(f'{server}/api/agent/propose', data=body,
                                                  headers={'Content-Type': 'application/json'}), timeout=120).read()
    seen = json.loads(Path(str(cli)).read_text())
    assert seen['files_in_cwd'] == []                                    # the MCP config lives elsewhere and is deleted
    assert not Path(seen['argv'][seen['argv'].index('--mcp-config') + 1]).exists()


def test_the_json_and_the_live_answer_both_close_the_tools(tmp_path, fake_virtuoso, cli, monkeypatch):
    """Whatever the answer looked like, no token survives the request (the live path closes them in its own thread)."""
    monkeypatch.setenv('FAKE_CLI_TOOL_CALLS', json.dumps([['working_copy_facts', {}]]))
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))
    config = make_config(tmp_path).model_dump(mode='json')
    config['circuit'] = dict(config['circuit'], source='virtuoso', library='RING', cell='ring')
    body = dict(kind='virtuoso_work', prompt='Set this up', config=config)
    for headers in ({}, {'Accept': 'text/event-stream'}):
        answer = client.post('/api/agent/propose', json=body, headers=headers)
        assert answer.status_code == 200, answer.text
        closed, deadline = False, time.time() + 10                       # the live path closes them in its own thread
        while not closed and time.time() < deadline:
            closed = client.post('/api/agent/tools', json=dict(token='any', method='list')).status_code == 403
            time.sleep(0.05)
        assert closed
