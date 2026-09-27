"""FAKE agent CLI used ONLY by tests (installed as `claude` or `codex` on a temporary PATH).

It emulates documented result shapes with fixed events and records how it was invoked. It makes
no network request and is never a real agent; proposals it yields are labelled by the provider
under test, and tests assert on plumbing only.

Environment: FAKE_CLI_SCENARIO (behaviour), FAKE_CLI_RECORD (JSON file receiving argv/stdin/cwd/env).
"""
import json
import os
import sys
import time

ROW = dict(metric_id='score', equation='m_score', unit='fixture', constraint='>=', lower=0.97, upper=None,
           target=None, tolerance=0.0, hard=True, direction_after_feasible='none', soft_weight=1.0,
           normalization_scale=1.0, active=True, basis='User asked for 0.97 in the prompt.')
GOOD = dict(kind='targets', patch=[dict(op='replace', section='targets', key='score', value=ROW,
                                        basis='User prompt')],
            reasoning='Raised the threshold as requested.', warnings=['Mock metric; not a circuit quantity.'],
            unresolved=['No datasheet was cited for this value.'])


REVIEW = dict(kind='settings_review', patch=[], reasoning='Two settings stand out for a 60-evaluation budget.', warnings=[], unresolved=[],
              suggestions=[dict(path='run.advanced.batch_size', value='16', reason='Fits the budget.', source='GATOR preset for gatv2 (Lighthouse RL)'),
                           dict(path='run.network.encoder_type', value='"gatv2"', reason='Borrowed starting settings from GAT sizing.', source='Lighthouse RL',
                                url='https://arxiv.org/abs/2607.14008', quote='We use a graph attention network'),
                           dict(path='output.output_root', value='"/tmp/elsewhere"', reason='tidier', source='none')],
              encoder_ideas=[dict(name='GPS graph transformer', source='Rampasek et al., NeurIPS 2022', url='https://arxiv.org/abs/2205.12454',
                                  why='Global attention.', what_it_takes='A new encoder class in the optimizer package.')])


def use_tools(argv):
    """What a CLI does with `--mcp-config`: start the server it names and speak MCP to it over its stdin/stdout.
    The calls below are the ones a test asserts on - including one tool that was never granted."""
    import subprocess
    config = json.loads(open(argv[argv.index('--mcp-config') + 1]).read())
    server = config['mcpServers']['gator']
    process = subprocess.Popen([server['command']] + server['args'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               env=dict(os.environ, **server.get('env', {})), text=True, bufsize=1)
    seen = []

    def rpc(method, params=None, ident=[0]):
        ident[0] += 1
        process.stdin.write(json.dumps(dict(jsonrpc='2.0', id=ident[0], method=method, params=params or {})) + '\n')
        process.stdin.flush()
        return json.loads(process.stdout.readline() or '{}')

    try:
        seen.append(dict(initialize=rpc('initialize', dict(protocolVersion='2025-06-18', clientInfo=dict(name='fake')))))
        process.stdin.write(json.dumps(dict(jsonrpc='2.0', method='notifications/initialized')) + '\n')
        process.stdin.flush()
        seen.append(dict(tools=[t['name'] for t in (rpc('tools/list').get('result') or {}).get('tools', [])]))
        for name, arguments in json.loads(os.environ.get('FAKE_CLI_TOOL_CALLS', '[]')):
            answer = rpc('tools/call', dict(name=name, arguments=arguments)).get('result') or {}
            seen.append(dict(call=name, isError=answer.get('isError'), text=(answer.get('content') or [{}])[0].get('text', '')[:4000]))
    finally:
        process.stdin.close()
        process.terminate()
    return seen


def main():
    argv = sys.argv[1:]
    name = os.path.basename(sys.argv[0])
    if argv[:1] == ['--version']:
        print(f'9.9.9 (fake {name} test fixture)')
        return 0
    if name == 'codex' and argv[:2] == ['exec', '--help']:
        hidden = os.environ.get('FAKE_CLI_SCENARIO') == 'old_codex'
        no_config = hidden or os.environ.get('FAKE_CLI_SCENARIO') == 'codex_without_config'
        no_json = hidden or os.environ.get('FAKE_CLI_SCENARIO') == 'codex_without_json'
        print('Usage: codex exec [OPTIONS] [PROMPT]\n  --sandbox <MODE>\n  --model <MODEL>\n  --skip-git-repo-check'
              + ('' if hidden else '\n  --output-schema <FILE>\n  --output-last-message <FILE>')
              + ('' if no_config else '\n  -c, --config <key=value>')
              + ('' if no_json else '\n  --json  Print events to stdout as JSONL'))
        return 0
    stdin = sys.stdin.read()
    scenario = os.environ.get('FAKE_CLI_SCENARIO', 'success')
    if scenario in ('live_demo', 'codex_demo') and 'FAKE-HANG' in stdin:     # a browser check asks for a never-ending answer by prompt text
        scenario = 'live_hang' if scenario == 'live_demo' else 'codex_live_hang'
    # `tools_then_denied`: the tools ARE used (the working copy is written) and the request fails afterwards - the case
    # where the answer must still say what was written (review of 2026-09-23).
    tools = use_tools(argv) if scenario in ('tools', 'tools_then_denied') and '--mcp-config' in argv else None
    record = os.environ.get('FAKE_CLI_RECORD')
    if record:
        with open(record, 'w') as stream:
            json.dump(dict(argv=argv, stdin=stdin, cwd=os.getcwd(), path=os.environ.get('PATH'),
                           home=os.environ.get('HOME'), claudecode=os.environ.get('CLAUDECODE'),
                           fine_grained=os.environ.get('CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING'),
                           tools=tools, files_in_cwd=sorted(os.listdir('.'))), stream)
    if scenario == 'hang':
        time.sleep(120)
        return 0
    if name == 'codex':
        return codex(argv, scenario)
    return claude(argv, scenario)


def result(**fields):
    base = dict(type='result', subtype='success', is_error=False, duration_ms=1234, num_turns=1, result='done',
                session_id='fake-session-0001', total_cost_usd=0.0123,
                usage=dict(input_tokens=1500, output_tokens=200), permission_denials=[])
    base.update(fields)
    return base


def emit(argv, final):
    if 'stream-json' in argv:
        print(json.dumps(dict(type='system', subtype='init', session_id='fake-session-0001', tools=[], model='fake')))
        print(json.dumps(dict(type='assistant', message=dict(content=[dict(type='text', text='Working on it...')]))))
        print(json.dumps(final))
    else:
        print(json.dumps(final))


THINKING = ['**Reading the request**\n\nThe user gives ', '0.97 for the ', 'score target and cites the prompt, ', 'so the row can be written.']
REPLY_ONLY = dict(kind='targets', reasoning='Your configuration already has what you asked for:\n\n- the `score` target stays at **0.95**\n'
                                            '- nothing else changes\n\nAsk again with a number if you want it moved.',
                  patch=[], warnings=['This fixture reply comes from the fake CLI of the tests.'], unresolved=[])


def live(argv, final, *, pause=0.0, hang=False, pieces=7):
    """`--include-partial-messages` in the shape recorded from the real CLI 2.1.278 (see test_wb_agent_live.py): a thinking
    summary in pieces, then the StructuredOutput input a few characters at a time, then the whole messages and the result."""
    def out(event, stream=True):
        print(json.dumps(dict(type='stream_event', event=event, parent_tool_use_id=None) if stream else event), flush=True)
    out(dict(type='system', subtype='init', session_id='fake-session-0001', tools=[], model='fake-live-model'), stream=False)
    out(dict(type='message_start', message=dict(model='fake-live-model', role='assistant', content=[])))
    out(dict(type='content_block_start', index=0, content_block=dict(type='thinking', thinking='', signature='')))
    for piece in THINKING:
        out(dict(type='content_block_delta', index=0, delta=dict(type='thinking_delta', thinking=piece)))
        out(dict(type='system', subtype='thinking_tokens', estimated_tokens=9, estimated_tokens_delta=3), stream=False)
        time.sleep(pause / len(THINKING))
    if hang:
        time.sleep(120)
    out(dict(type='content_block_delta', index=0, delta=dict(type='signature_delta', signature='fake-signature')))
    out(dict(type='content_block_stop', index=0))
    out(dict(type='assistant', message=dict(content=[dict(type='thinking', thinking=''.join(THINKING), signature='fake')])), stream=False)
    out(dict(type='content_block_start', index=1, content_block=dict(type='tool_use', id='toolu_fake', name='StructuredOutput', input={})))
    text = json.dumps(final)
    for start in range(0, len(text), pieces):
        out(dict(type='content_block_delta', index=1, delta=dict(type='input_json_delta', partial_json=text[start:start + pieces])))
        time.sleep(pause / 40)
    out(dict(type='assistant', message=dict(content=[dict(type='tool_use', id='toolu_fake', name='StructuredOutput', input=final)])), stream=False)
    out(dict(type='content_block_stop', index=1))
    out(dict(type='message_delta', delta=dict(stop_reason='tool_use')))
    out(dict(type='message_stop'))
    out(result(structured_output=final), stream=False)


def claude(argv, scenario):
    partial = '--include-partial-messages' in argv
    if scenario.startswith('live') and scenario != 'live_refused' and not partial:
        emit(argv, result(structured_output=REPLY_ONLY if scenario == 'live_demo' else GOOD))     # asked for the whole answer
    elif scenario == 'live':
        live(argv, GOOD)
    elif scenario == 'live_slow':                       # time between the thinking and the answer: the events must come first
        live(argv, GOOD, pause=1.5)
    elif scenario == 'live_hang':                       # thinks, then never answers: for "Cancel request" mid-stream
        live(argv, GOOD, hang=True)
    elif scenario == 'live_demo':                       # a reply valid for any configuration, paced for a browser check
        live(argv, REPLY_ONLY, pause=float(os.environ.get('FAKE_CLI_PAUSE', '4')), pieces=5)
    elif scenario == 'live_refused':                    # a CLI version without the live options: fails before any model call
        if '--thinking-display' in argv:
            print("error: unknown option '--thinking-display'", file=sys.stderr)
            return 1
        emit(argv, result(structured_output=GOOD))
    elif scenario == 'tools':                           # the workbench's own tools were used above; the answer is the rows
        emit(argv, result(structured_output=dict(GOOD, kind='virtuoso_work'),
                          permission_denials=json.loads(os.environ.get('FAKE_CLI_DENIALS', '[]'))))
    elif scenario == 'success':
        emit(argv, result(structured_output=GOOD))
    elif scenario == 'settings_review':
        emit(argv, result(structured_output=REVIEW))
    elif scenario == 'web_refused':                     # a page outside the allowed hosts was refused; the review itself is fine
        emit(argv, result(structured_output=REVIEW, permission_denials=[dict(tool_name='WebFetch', tool_input=dict(url='https://example.org/x'))]))
    elif scenario == 'no_structured_output':
        emit(argv, result(result='Here is the config:\n```json\n' + json.dumps(GOOD) + '\n```'))
    elif scenario == 'nonzero':
        print('fatal: something broke', file=sys.stderr)
        return 3
    elif scenario == 'permission_denied':
        emit(argv, result(structured_output=GOOD, permission_denials=[dict(tool_name='Bash', tool_input=dict(command='rm -rf x'))]))
    elif scenario == 'tools_then_denied':      # the working copy was written above; THEN the request fails
        emit(argv, result(structured_output=GOOD,
                          permission_denials=[dict(tool_name='mcp__gator__working_copy_write_setup', tool_input={})]))
    elif scenario == 'unauthenticated':
        emit(argv, result(subtype='error_during_execution', is_error=True, result='Invalid API key · Please run /login'))
        return 1
    elif scenario == 'model_unavailable':
        print('API Error: 404 {"type":"error","error":{"type":"not_found_error","message":"model: claude-fable-5-1 not found"}}',
              file=sys.stderr)
        return 1
    elif scenario == 'schema_failure':
        emit(argv, result(subtype='error_max_structured_output_retries', is_error=True, result=''))
        return 1
    elif scenario == 'garbage':
        print('Thinking...\n{"type": "result", "structured_out')
    elif scenario == 'stderr_config':
        print(json.dumps(GOOD), file=sys.stderr)              # configuration-looking text on stderr must be ignored
        print('progress: 50%')
    elif scenario == 'out_of_scope':
        bad = dict(GOOD, patch=[dict(op='remove', section='parameters', key='input_pair_width')])
        emit(argv, result(structured_output=bad))
    elif scenario == 'escalation':
        emit(argv, result(structured_output=dict(GOOD, settings=dict(allowedTools=['Bash'], permission_mode='bypassPermissions'),
                                                 skip_validation=True, output_root='/etc')))
    elif scenario == 'bad_row':
        emit(argv, result(structured_output=dict(GOOD, patch=[dict(op='replace', section='targets', key='score',
                                                                   value=dict(ROW, run_shell='rm -rf /', lower='high'))])))
    elif scenario == 'other_field':
        emit(argv, result(structured_output=dict(GOOD, patch=[dict(op='replace', section='targets', key='score',
                                                                   value=dict(ROW, hard=False))])))
    else:
        print(f'unknown scenario {scenario}', file=sys.stderr)
        return 9
    return 0


CODEX_REASONING = ['**Reading the request**\n\nThe user gives 0.97 for the score target.',
                   '**Checking the row**\n\nIt names its source, so it can be written.']


def codex_events(final, *, pause=0.0, hang=False):
    """`codex exec --json` in the documented shape (Non-interactive mode; SDK events.ts / items.ts): whole items, no pieces."""
    def out(event):
        print(json.dumps(event), flush=True)
    out(dict(type='thread.started', thread_id='fake-thread-0001'))
    out(dict(type='turn.started'))
    for number, text in enumerate(CODEX_REASONING):
        out(dict(type='item.completed', item=dict(id=f'item_{number}', type='reasoning', text=text)))
        time.sleep(pause / 4)
        if hang:
            time.sleep(120)
    out(dict(type='item.started', item=dict(id='item_5', type='command_execution', command='ls', aggregated_output='', status='in_progress')))
    out(dict(type='item.completed', item=dict(id='item_5', type='command_execution', command='ls', aggregated_output='',
                                              exit_code=0, status='completed')))
    out(dict(type='item.completed', item=dict(id='item_6', type='web_search', query='SAC analog circuit sizing')))
    time.sleep(pause / 2)
    out(dict(type='item.completed', item=dict(id='item_7', type='agent_message', text=json.dumps(final))))
    out(dict(type='turn.completed', usage=dict(input_tokens=1500, cached_input_tokens=0, output_tokens=200)))


def codex(argv, scenario):
    if scenario == 'nonzero':
        print('error: not logged in', file=sys.stderr)
        return 1
    target = argv[argv.index('--output-last-message') + 1]
    final = REPLY_ONLY if scenario == 'codex_demo' else GOOD
    if '--json' in argv or '--experimental-json' in argv:
        codex_events(final, pause=1.5 if scenario == 'codex_live_slow' else float(os.environ.get('FAKE_CLI_PAUSE', '4'))
                     if scenario == 'codex_demo' else 0.0, hang=scenario == 'codex_live_hang')
    else:
        print(json.dumps(dict(type='thread.started')))
    if scenario != 'codex_live_nofile':                  # a CLI version that writes no output file: the answer is the last message
        with open(target, 'w') as stream:
            stream.write('this is prose, not json' if scenario == 'garbage' else json.dumps(final))
    return 0


if __name__ == '__main__':
    sys.exit(main())
