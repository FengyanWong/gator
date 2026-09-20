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

ROW = dict(metric_id='score', measurement_id='m_score', unit='fixture', constraint='>=', lower=0.97, upper=None,
           target=None, tolerance=0.0, hard=True, direction_after_feasible='none', soft_weight=1.0,
           normalization_scale=1.0, active=True, basis='User asked for 0.97 in the prompt.')
GOOD = dict(kind='targets', patch=[dict(op='replace', section='targets', key='score', value=ROW,
                                        basis='User prompt')],
            reasoning='Raised the threshold as requested.', warnings=['Mock metric; not a circuit quantity.'],
            unresolved=['No datasheet was cited for this value.'])


def main():
    argv = sys.argv[1:]
    name = os.path.basename(sys.argv[0])
    if argv[:1] == ['--version']:
        print(f'9.9.9 (fake {name} test fixture)')
        return 0
    if name == 'codex' and argv[:2] == ['exec', '--help']:
        hidden = os.environ.get('FAKE_CLI_SCENARIO') == 'old_codex'
        print('Usage: codex exec [OPTIONS] [PROMPT]\n  --sandbox <MODE>\n  --model <MODEL>\n  --skip-git-repo-check'
              + ('' if hidden else '\n  --output-schema <FILE>\n  --output-last-message <FILE>'))
        return 0
    stdin = sys.stdin.read()
    scenario = os.environ.get('FAKE_CLI_SCENARIO', 'success')
    record = os.environ.get('FAKE_CLI_RECORD')
    if record:
        with open(record, 'w') as stream:
            json.dump(dict(argv=argv, stdin=stdin, cwd=os.getcwd(), path=os.environ.get('PATH'),
                           home=os.environ.get('HOME'), claudecode=os.environ.get('CLAUDECODE'),
                           files_in_cwd=sorted(os.listdir('.'))), stream)
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


def claude(argv, scenario):
    if scenario == 'success':
        emit(argv, result(structured_output=GOOD))
    elif scenario == 'no_structured_output':
        emit(argv, result(result='Here is the config:\n```json\n' + json.dumps(GOOD) + '\n```'))
    elif scenario == 'nonzero':
        print('fatal: something broke', file=sys.stderr)
        return 3
    elif scenario == 'permission_denied':
        emit(argv, result(structured_output=GOOD, permission_denials=[dict(tool_name='Bash', tool_input=dict(command='rm -rf x'))]))
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


def codex(argv, scenario):
    if scenario == 'nonzero':
        print('error: not logged in', file=sys.stderr)
        return 1
    target = argv[argv.index('--output-last-message') + 1]
    print(json.dumps(dict(type='thread.started')))
    with open(target, 'w') as stream:
        stream.write('this is prose, not json' if scenario == 'garbage' else json.dumps(GOOD))
    return 0


if __name__ == '__main__':
    sys.exit(main())
