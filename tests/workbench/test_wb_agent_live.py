"""Live agent answers (status record 7.48): the thinking summary and the reply reach the page while they are written, and
a request has no time limit. Fake CLI fixtures and one RECORDED real stream only - no agent is started by these tests.

`fixtures/claude_live_recorded.ndjson` is the stdout of a real `claude` 2.1.278 request of 2026-09-21 (`-p --output-format
stream-json --verbose --include-partial-messages --thinking-display summarized`, CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING=1,
sonnet at effort max, a small op-amp question with a four-field schema). Trimmed to its first 60 thinking pieces - the whole
thinking message of the recording was cut to the same text - and with session ids and uuids replaced; nothing else changed."""
import asyncio
import http.client
import json
import os
from pathlib import Path
import random
import socket
import stat
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import agents
from gator_workbench.agents import AgentError, AgentRequest, AgentSettings, ClaudeCodeProvider, CodexProvider
from gator_workbench.agents import base
from gator_workbench.agents.live import CodexTranslator, LiveTranslator, PartialAnswer
from gator_workbench.api import create_app
from gator_workbench.api.app import live_answer
from helpers import make_config

FIXTURES = Path(__file__).parent / 'fixtures'
FAKE = FIXTURES / 'fake_cli.py'
sys.path.insert(0, str(FIXTURES))
import fake_cli                                                     # noqa: E402  (its GOOD / THINKING / REPLY_ONLY)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name in ('claude', 'codex'):
        target = bin_dir / name
        target.write_text(f'#!{sys.executable}\n' + FAKE.read_text())
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
    record = tmp_path / 'record.json'
    monkeypatch.setenv('PATH', f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.setenv('FAKE_CLI_RECORD', str(record))

    def scenario(name):
        monkeypatch.setenv('FAKE_CLI_SCENARIO', name)
        return record
    return scenario


def request(tmp_path, kind='targets', prompt='Raise the score target to 0.97'):
    return AgentRequest(kind=kind, user_prompt=prompt, config=make_config(tmp_path).model_dump(mode='json'), circuit_summary=dict(devices=[]))


def joined(events, kind, key='text'):
    return ''.join(e[key] for e in events if e['type'] == kind)


# ------------------------------------------------------------------------------- reading the answer while it arrives
TRICKY = dict(kind='targets', patch=[dict(op='replace', section='targets', key='gain', value=dict(reasoning='a nested "reasoning" is not the reply'),
                                          basis='quoted: "0.97" \\ backslash')],
              reasoning='Line one.\nLine "two"\twith tab, back\\slash, µ, Ω, 😀 and — dash.', warnings=['w'], unresolved=[])


@pytest.mark.parametrize('ascii_only', [False, True])            # the model may write "µ" as it is or as µ (😀 = a surrogate pair)
@pytest.mark.parametrize('order', ['as_written', 'reply_first'])
def test_the_reply_is_decoded_exactly_however_the_pieces_are_cut(order, ascii_only):
    obj = TRICKY if order == 'as_written' else dict(kind=TRICKY['kind'], reasoning=TRICKY['reasoning'],
                                                    **{k: v for k, v in TRICKY.items() if k not in ('kind', 'reasoning')})
    text = json.dumps(obj, ensure_ascii=ascii_only)
    rng = random.Random(7)
    for cut in ('char', 'random', 'whole'):
        reader, fields, reply, at = PartialAnswer(), [], '', 0
        while at < len(text):
            size = 1 if cut == 'char' else rng.randint(1, 13) if cut == 'random' else len(text)
            started, piece = reader.feed(text[at:at + size])
            fields += started
            reply += piece
            at += size
        assert reply == obj['reasoning'], cut
        assert fields == list(obj), cut                            # the top-level fields, in the order they were written


def test_a_recorded_real_stream_rebuilds_the_thinking_and_the_reply():
    events, final, thinking = [], None, ''
    translator = LiveTranslator(events.append)
    for line in (FIXTURES / 'claude_live_recorded.ndjson').read_text().splitlines():
        translator.feed(line)
        event = json.loads(line)
        if event['type'] == 'result':
            final = event
        if event['type'] == 'assistant':
            thinking += ''.join(b.get('thinking', '') for b in event['message']['content'] if b['type'] == 'thinking')
    assert final['subtype'] == 'success' and final['usage']['output_tokens_details']['thinking_tokens'] > 0
    assert joined(events, 'reply') == final['structured_output']['reasoning'] and len(joined(events, 'reply')) > 400
    assert joined(events, 'thinking') == thinking and len(thinking) > 500
    assert [e['field'] for e in events if e['type'] == 'writing'] == ['kind', 'reasoning', 'patch', 'warnings']
    assert [e for e in events if e['type'] == 'model'] == [dict(type='model', model='claude-sonnet-5')]
    assert sum(e['type'] == 'reply' for e in events) > 20               # many small pieces, not one block
    first_reply = next(i for i, e in enumerate(events) if e['type'] == 'reply')
    assert all(e['type'] != 'thinking' or not e['text'] for e in events[first_reply:])      # the thinking came first


def test_steps_retries_side_text_and_a_rewritten_answer():
    events = []
    feed = LiveTranslator(events.append).feed
    stream = lambda event: json.dumps(dict(type='stream_event', event=event, parent_tool_use_id=None))
    for line in [
        json.dumps(dict(type='assistant', message=dict(content=[dict(type='tool_use', name='ToolSearch', input=dict(query='select:WebSearch'))]))),
        json.dumps(dict(type='assistant', message=dict(content=[dict(type='tool_use', name='WebSearch', input=dict(query='SAC analog sizing'))]))),
        json.dumps(dict(type='assistant', message=dict(content=[dict(type='tool_use', name='WebFetch', input=dict(url='https://arxiv.org/abs/1', prompt='x'))]))),
        json.dumps(dict(type='system', subtype='api_retry', attempt=2, max_retries=10, retry_delay_ms=5000, error_status=529)),
        json.dumps(dict(type='stream_event', parent_tool_use_id='toolu_sub', event=dict(type='content_block_start', index=0,
                                                                                         content_block=dict(type='text')))),    # a subagent: ignored
        'not json at all', '{"broken": ',
        stream(dict(type='message_start', message={})),
        stream(dict(type='content_block_start', index=0, content_block=dict(type='text', text=''))),
        stream(dict(type='content_block_delta', index=0, delta=dict(type='text_delta', text='Let me check the papers.'))),
        stream(dict(type='content_block_start', index=1, content_block=dict(type='tool_use', name='StructuredOutput', input={}))),
        stream(dict(type='content_block_delta', index=1, delta=dict(type='input_json_delta', partial_json='{"kind":"x","reasoning":"first try'))),
        stream(dict(type='message_start', message={})),
        stream(dict(type='content_block_start', index=0, content_block=dict(type='tool_use', name='StructuredOutput', input={}))),
        stream(dict(type='content_block_delta', index=0, delta=dict(type='input_json_delta', partial_json='{"reasoning":"second"}'))),
    ]:
        feed(line)
    steps = [e['text'] for e in events if e['type'] == 'step']
    assert steps[0] == 'Searching the web: SAC analog sizing' and steps[1] == 'Opening https://arxiv.org/abs/1'
    assert 'HTTP 529' in steps[2] and 'attempt 2 of 10' in steps[2] and len(steps) == 3      # ToolSearch is bookkeeping
    assert [e for e in events if e['type'] == 'say'] == [dict(type='say', text='', new=True), dict(type='say', text='Let me check the papers.', new=False)]
    kinds = [e['type'] for e in events if e['type'] in ('reply', 'restart')]
    assert kinds == ['reply', 'restart', 'reply'] and joined(events, 'reply') == 'first trysecond'   # the page clears on `restart`


# ------------------------------------------------------------------------------- the provider
def test_a_live_request_asks_for_live_output_and_reports_it(tmp_path, cli):
    record = cli('live')
    events = []
    result = ClaudeCodeProvider(AgentSettings(provider='claude_code')).propose(request(tmp_path), on_event=events.append)
    seen = json.loads(record.read_text())
    argv = seen['argv']
    assert argv[:4] == ['-p', '--output-format', 'stream-json', '--verbose']
    assert '--include-partial-messages' in argv and argv[argv.index('--thinking-display') + 1] == 'summarized'
    assert seen['fine_grained'] == '1'
    assert result.structured_output == fake_cli.GOOD                  # the proposal still comes from the final result only
    assert joined(events, 'thinking') == ''.join(fake_cli.THINKING) and joined(events, 'reply') == fake_cli.GOOD['reasoning']
    assert [e['field'] for e in events if e['type'] == 'writing'] == list(fake_cli.GOOD)
    assert {e['type'] for e in result.logs} == {'system', 'assistant'}    # no stream pieces kept as logs


def test_a_plain_request_is_unchanged(tmp_path, cli):
    record = cli('live')
    result = ClaudeCodeProvider(AgentSettings(provider='claude_code')).propose(request(tmp_path))
    seen = json.loads(record.read_text())
    assert '--include-partial-messages' not in seen['argv'] and '--thinking-display' not in seen['argv'] and seen['fine_grained'] is None
    assert result.structured_output == fake_cli.GOOD


def test_progress_arrives_while_the_cli_is_still_working(tmp_path, cli):
    cli('live_slow')                                                 # 1.5 s between the thinking and the answer
    stamps = []
    ClaudeCodeProvider(AgentSettings(provider='claude_code')).propose(request(tmp_path), on_event=lambda e: stamps.append((time.monotonic(), e['type'])))
    done = time.monotonic()
    first_thinking = next(t for t, kind in stamps if kind == 'thinking')
    assert done - first_thinking > 1.0, 'the thinking was handed over only at the end'


def test_a_cli_without_the_live_options_answers_in_one_piece(tmp_path, cli):
    record = cli('live_refused')
    events = []
    result = ClaudeCodeProvider(AgentSettings(provider='claude_code')).propose(request(tmp_path), on_event=events.append)
    assert result.structured_output == fake_cli.GOOD
    assert '--thinking-display' not in json.loads(record.read_text())['argv']          # the repeat, without the options
    assert any(e['type'] == 'step' and 'arrive in one piece' in e['text'] for e in events)


def test_cancel_stops_a_live_request_mid_stream(tmp_path, cli):
    cli('live_hang')
    provider, req, outcome, events = ClaudeCodeProvider(AgentSettings(provider='claude_code')), request(tmp_path), {}, []

    def run():
        try:
            provider.propose(req, on_event=events.append)
        except AgentError as exc:
            outcome['code'] = exc.code
    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.time() + 20
    while not any(e['type'] == 'thinking' and e['text'] for e in events) and time.time() < deadline:
        time.sleep(0.02)
    assert provider.cancel(req.request_id) is True
    thread.join(timeout=30)
    assert outcome == {'code': 'cancelled'} and base.REGISTRY.active() == []
    assert joined(events, 'thinking') == ''.join(fake_cli.THINKING)      # what had arrived before the cancel


def test_there_is_no_time_limit_unless_a_caller_sets_one(tmp_path, cli):
    assert AgentSettings().timeout_seconds is None and AgentSettings(provider='claude_code').validate()
    for bad in (0, -1, 3601):
        with pytest.raises(AgentError):
            AgentSettings(timeout_seconds=bad).validate()
    cli('hang')                                                      # a caller's own limit still works (and stops only its process)
    with pytest.raises(AgentError) as error:
        ClaudeCodeProvider(AgentSettings(provider='claude_code', timeout_seconds=1.0)).propose(request(tmp_path), on_event=lambda e: None)
    assert error.value.code == 'timeout' and base.REGISTRY.active() == []


# ------------------------------------------------------------------------------- Codex (status record 7.50)
def codex(**settings):
    return CodexProvider(AgentSettings(provider='codex', **settings))


def test_a_codex_request_shows_its_items_while_it_works(tmp_path, cli):
    record = cli('codex_live')
    events = []
    result = codex().propose(request(tmp_path), on_event=events.append)
    assert json.loads(record.read_text())['argv'][:2] == ['exec', '--json']
    assert result.structured_output == fake_cli.GOOD and result.origin == 'codex'       # still the answer file
    assert events[0] == dict(type='thinking', text='')                                  # turn.started: "Thinking..."
    assert joined(events, 'thinking') == '\n\n'.join(fake_cli.CODEX_REASONING)
    assert [e['text'] for e in events if e['type'] == 'step'] == ['Running: ls', 'Searching the web: SAC analog circuit sizing']
    assert [e['field'] for e in events if e['type'] == 'writing'] == ['reasoning'] and joined(events, 'reply') == fake_cli.GOOD['reasoning']


def test_codex_items_arrive_before_the_end(tmp_path, cli):
    cli('codex_live_slow')                                             # 1.5 s between the first reasoning and the answer
    stamps = []
    codex().propose(request(tmp_path), on_event=lambda e: stamps.append((time.monotonic(), e['type'], e.get('text'))))
    done = time.monotonic()
    assert done - next(t for t, kind, text in stamps if kind == 'thinking' and text) > 1.0


def test_a_codex_without_the_event_option_answers_in_one_piece(tmp_path, cli):
    record = cli('codex_without_json')
    events = []
    result = codex().propose(request(tmp_path), on_event=events.append)
    argv = json.loads(record.read_text())['argv']
    assert '--json' not in argv and '--experimental-json' not in argv and result.structured_output == fake_cli.GOOD
    assert [e['type'] for e in events] == ['step'] and 'one piece' in events[0]['text']
    cli('codex_live')                                                  # a plain request (no on_event) asks for no events either
    codex().propose(request(tmp_path))
    assert '--json' not in json.loads(record.read_text())['argv']


def test_codex_answer_comes_from_the_stream_when_no_file_is_written(tmp_path, cli):
    cli('codex_live_nofile')
    assert codex().propose(request(tmp_path), on_event=lambda e: None).structured_output == fake_cli.GOOD
    with pytest.raises(AgentError) as error:                          # without the stream there is nothing else to read
        codex().propose(request(tmp_path))
    assert error.value.code == 'no_structured_output'


def test_cancel_stops_a_codex_request_mid_stream(tmp_path, cli):
    cli('codex_live_hang')
    provider, req, outcome, events = codex(), request(tmp_path), {}, []

    def run():
        try:
            provider.propose(req, on_event=events.append)
        except AgentError as exc:
            outcome['code'] = exc.code
    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.time() + 20
    while not any(e['type'] == 'thinking' and e['text'] for e in events) and time.time() < deadline:
        time.sleep(0.02)
    assert provider.cancel(req.request_id) is True
    thread.join(timeout=30)
    assert outcome == {'code': 'cancelled'} and base.REGISTRY.active() == []
    assert joined(events, 'thinking') == fake_cli.CODEX_REASONING[0]


def test_every_documented_codex_item_is_read():
    events = []
    feed = CodexTranslator(events.append).feed
    for event in [
        dict(type='thread.started', thread_id='t'), dict(type='turn.started'),
        dict(type='item.started', item=dict(id='r1', type='reasoning', text='First')),
        dict(type='item.updated', item=dict(id='r1', type='reasoning', text='First part, then more')),
        dict(type='item.completed', item=dict(id='r1', type='reasoning', text='First part, then more')),
        dict(type='item.completed', item=dict(id='r2', type='reasoning', text='Second')),
        dict(type='item.started', item=dict(id='c1', type='command_execution', command='cat x', aggregated_output='', status='in_progress')),
        dict(type='item.completed', item=dict(id='c1', type='command_execution', command='cat x', aggregated_output='no such file',
                                              exit_code=1, status='failed')),
        dict(type='item.started', item=dict(id='m1', type='mcp_tool_call', server='docs', tool='search', arguments={}, status='in_progress')),
        dict(type='item.completed', item=dict(id='m1', type='mcp_tool_call', server='docs', tool='search', arguments={}, status='completed')),
        dict(type='item.completed', item=dict(id='f1', type='file_change', changes=[dict(path='a.txt', kind='update')], status='completed')),
        dict(type='item.started', item=dict(id='p1', type='todo_list', items=[dict(text='read', completed=False), dict(text='answer', completed=False)])),
        dict(type='item.updated', item=dict(id='p1', type='todo_list', items=[dict(text='read', completed=True), dict(text='answer', completed=False)])),
        dict(type='item.completed', item=dict(id='e1', type='error', message='a tool was slow')),
        dict(type='item.completed', item=dict(id='a1', type='agent_message', text='Looking at the rows first.')),
        dict(type='error', message='stream disconnected - retrying'),
        dict(type='turn.failed', error=dict(message='usage limit reached')),
        dict(type='item.completed', item=dict(id='a2', type='agent_message', text=json.dumps(dict(kind='targets', reasoning='Done.', patch=[])))),
        dict(type='turn.completed', usage=dict(input_tokens=1, cached_input_tokens=0, output_tokens=1)),
    ]:
        feed(json.dumps(event))
    for junk in ('not json', '[1, 2]', '{"type": "item.completed"}', '{"broken": '):
        feed(junk)
    assert joined(events, 'thinking') == 'First part, then more\n\nSecond'
    assert [e['text'] for e in events if e['type'] == 'step'] == [
        'Running: cat x', 'The command failed (exit 1): cat x', 'Using docs.search', 'Changing files: a.txt', 'Plan: read; answer',
        'codex: a tool was slow', 'codex: stream disconnected - retrying', 'The turn failed: usage limit reached']
    assert [e for e in events if e['type'] == 'say'] == [dict(type='say', text='Looking at the rows first.', new=True)]
    assert joined(events, 'reply') == 'Done.'


# ------------------------------------------------------------------------------- the HTTP answer
@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))


def frames(lines):
    """(event, data) pairs of a Server-Sent Events body; comment lines (keep-alive) are skipped."""
    kind, data = None, None
    for line in lines:
        if line.startswith('event:'):
            kind = line[6:].strip()
        elif line.startswith('data:'):
            data = json.loads(line[5:])
        elif not line.strip() and kind:
            yield kind, data
            kind, data = None, None


def propose_live(client, body):
    with client.stream('POST', '/api/agent/propose', json=body, headers={'Accept': 'text/event-stream'}) as response:
        assert response.status_code == 200 and response.headers['content-type'].startswith('text/event-stream')
        return list(frames(response.iter_lines()))


def test_the_api_streams_progress_then_the_same_proposal(client, tmp_path, cli):
    cli('live')
    raw = make_config(tmp_path).model_dump(mode='json')
    received = propose_live(client, dict(kind='targets', prompt='raise to 0.97', config=raw))
    kinds = [kind for kind, _ in received]
    assert kinds[-1] == 'result' and set(kinds[:-1]) == {'progress'} and kinds.count('result') == 1
    progress = [data for kind, data in received if kind == 'progress']
    assert joined(progress, 'reply') == fake_cli.GOOD['reasoning'] and joined(progress, 'thinking') == ''.join(fake_cli.THINKING)
    proposal = received[-1][1]
    assert proposal['status'] == 'proposed' and proposal['diff'][0]['key'] == 'score' and proposal['reasoning'] == fake_cli.GOOD['reasoning']
    assert 'readiness_after' in proposal and not any(log['type'] == 'stream_event' for log in proposal['logs'])
    plain = client.post('/api/agent/propose', json=dict(kind='targets', prompt='raise to 0.97', config=raw))
    assert plain.headers['content-type'].startswith('application/json')                  # without the header: one JSON body, as before
    assert {k for k in plain.json() if k not in ('proposal_id', 'created_utc')} == {k for k in proposal if k not in ('proposal_id', 'created_utc')}


def test_the_api_streams_a_codex_answer_too(client, tmp_path, cli):
    cli('codex_live')
    assert client.put('/api/agent/settings', json=dict(provider='codex')).json()['saved']
    received = propose_live(client, dict(kind='targets', prompt='raise to 0.97', config=make_config(tmp_path).model_dump(mode='json')))
    progress = [data for kind, data in received if kind == 'progress']
    assert received[-1][0] == 'result' and received[-1][1]['origin'] == 'codex' and received[-1][1]['diff'][0]['key'] == 'score'
    assert joined(progress, 'thinking') == '\n\n'.join(fake_cli.CODEX_REASONING) and joined(progress, 'reply') == fake_cli.GOOD['reasoning']
    assert [p['text'] for p in progress if p['type'] == 'step'] == ['Running: ls', 'Searching the web: SAC analog circuit sizing']


def test_api_errors_keep_their_shape(client, tmp_path, cli):
    cli('nonzero')
    raw = make_config(tmp_path).model_dump(mode='json')
    received = propose_live(client, dict(kind='targets', prompt='x', config=raw))
    assert received[-1][0] == 'error' and received[-1][1]['code'] == 'nonzero_exit' and received[-1][1]['configuration_unchanged']
    refused = client.post('/api/agent/propose', json=dict(kind='targets', prompt='  ', config=raw), headers={'Accept': 'text/event-stream'})
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'invalid_request'      # refused before any stream


def test_the_api_cancel_ends_a_live_answer_with_the_cancelled_verdict(client, tmp_path, cli):
    cli('live_hang')
    raw = make_config(tmp_path).model_dump(mode='json')

    def cancel_when_running():
        deadline = time.time() + 20
        while 'live-cancel-0001' not in base.REGISTRY.active() and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.5)                                               # the thinking pieces are out by now
        client.post('/api/agent/cancel', json=dict(request_id='live-cancel-0001'))
    threading.Thread(target=cancel_when_running, daemon=True).start()
    received = propose_live(client, dict(kind='targets', prompt='x', config=raw, request_id='live-cancel-0001'))
    assert received[-1] == ('error', received[-1][1]) and received[-1][1]['code'] == 'cancelled'
    assert joined([d for k, d in received if k == 'progress'], 'thinking') == ''.join(fake_cli.THINKING)


def test_the_saved_time_limit_is_gone(client, tmp_path):
    from gator_workbench import runs
    runs.save_settings(agent=dict(provider='disabled', timeout_seconds=300.0))            # as saved by earlier versions
    assert client.get('/api/agent/settings').json()['timeout_seconds'] is None
    older_page = dict(provider='disabled', model=None, effort=None, timeout_seconds=300, permission_mode='dontAsk', allowed_tools=[],
                      max_turns=None, stream=True)
    assert client.put('/api/agent/settings', json=older_page).json()['saved']            # an older page still sends it
    assert 'timeout_seconds' not in runs.load_settings()['agent']


# ------------------------------------------------------------------------------- over a real socket
@pytest.fixture
def server(tmp_path):
    """The app under uvicorn on a free local port: TestClient hands a streamed body over only when it is complete."""
    import uvicorn
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    app = create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False)
    instance = uvicorn.Server(uvicorn.Config(app, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=instance.run, kwargs=dict(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(200):
        if instance.started:
            break
        time.sleep(0.02)
    yield sock.getsockname()[1]
    instance.should_exit = True
    thread.join(timeout=10)


def open_live(port, body):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    connection.request('POST', '/api/agent/propose', body=json.dumps(body), headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    response = connection.getresponse()
    assert response.status == 200
    return connection, response


def test_events_cross_the_socket_as_they_happen(server, tmp_path, cli):
    cli('live_slow')
    connection, response = open_live(server, dict(kind='targets', prompt='raise to 0.97', config=make_config(tmp_path).model_dump(mode='json')))
    stamps = []
    while True:
        line = response.readline().decode()
        if not line:
            break
        if line.startswith('event:'):
            stamps.append((time.monotonic(), line[6:].strip()))
    connection.close()
    assert stamps[-1][1] == 'result'
    assert stamps[-1][0] - stamps[0][0] > 1.0, 'the page would have received everything at once'


def test_a_page_that_goes_away_stops_the_agent(server, tmp_path, cli):
    cli('live_hang')
    connection, response = open_live(server, dict(kind='targets', prompt='x', config=make_config(tmp_path).model_dump(mode='json'),
                                                  request_id='page-left-0001'))
    assert response.readline().startswith(b'event: progress')
    assert 'page-left-0001' in base.REGISTRY.active()
    connection.sock.shutdown(socket.SHUT_RDWR)
    connection.close()
    deadline = time.time() + 20
    while 'page-left-0001' in base.REGISTRY.active() and time.time() < deadline:
        time.sleep(0.05)
    assert 'page-left-0001' not in base.REGISTRY.active()


def test_live_answer_cancels_when_its_stream_is_closed_early(tmp_path, cli):
    """The same rule without a server: closing the event stream before its verdict cancels the request."""
    cli('live_hang')
    req = request(tmp_path)
    response = live_answer(req, ClaudeCodeProvider(AgentSettings(provider='claude_code')), finish=lambda result: dict(ok=True))

    async def first_then_close():
        body = response.body_iterator
        first = await body.__anext__()
        await body.aclose()
        return first
    first = asyncio.run(first_then_close())
    assert first.startswith('event: progress')
    deadline = time.time() + 20
    while req.request_id in base.REGISTRY.active() and time.time() < deadline:
        time.sleep(0.05)
    assert req.request_id not in base.REGISTRY.active()
