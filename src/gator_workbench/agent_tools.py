"""The tool server the Agent tab starts beside an agent CLI (status record 7.68): it OFFERS the workbench's tools and
RELAYS every call to the backend. It decides nothing.

The CLI speaks MCP over this process's stdin/stdout (JSON-RPC, one message per line); the process answers `initialize`,
`tools/list`, `tools/call` and `ping`, and nothing else. Each call goes to `POST <url>/api/agent/tools` of the workbench
that started it, with the one-time token of THAT request; the backend checks the token, the grant and the budget, does
the work through the same functions the buttons use, and records it (agents/tools.py). So this file holds no Virtuoso
access, no credentials and no rules: even started by hand it can do nothing the backend would not allow that request.

Environment: GATOR_TOOLS_URL (the backend's base address), GATOR_TOOLS_TOKEN. stdout carries protocol messages only -
everything else goes to stderr, which the CLI keeps out of the conversation.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

NAME = 'gator'
VERSION = '1'
PROTOCOL = '2025-06-18'                  # answered when the client asks for something we do not know
TIMEOUT = 900.0                          # one call may wait for Virtuoso; the request itself has no time limit


def ask(method, payload):
    """One request to the workbench that started this process. Returns its JSON answer, or an error answer."""
    url = os.environ.get('GATOR_TOOLS_URL', '').rstrip('/') + '/api/agent/tools'
    body = json.dumps(dict(payload, token=os.environ.get('GATOR_TOOLS_TOKEN', ''), method=method)).encode()
    request = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
    # Straight to the backend on this machine: urlopen would honour http_proxy, and a proxy would then see the one-time
    # tool token and every call (review of 2026-09-29).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=TIMEOUT) as answer:
            return json.loads(answer.read().decode('utf8', 'replace') or '{}')
    except urllib.error.HTTPError as exc:                       # the backend refused: its words go to the agent
        try:
            detail = json.loads(exc.read().decode('utf8', 'replace'))
        except ValueError:
            detail = {}
        message = detail.get('detail') if isinstance(detail.get('detail'), str) else detail.get('error')
        return dict(ok=False, error=message or f'The workbench answered {exc.code}')
    except Exception as exc:                                    # the workbench is gone (stopped, restarted)
        return dict(ok=False, error=f'The workbench could not be reached ({type(exc).__name__}): its tools are not available.')


def handle(message):
    """The answer to one JSON-RPC message, or None for a notification."""
    method, ident = message.get('method'), message.get('id')
    if ident is None:
        return None                                             # a notification (initialized, cancelled): nothing to answer
    if method == 'initialize':
        asked = (message.get('params') or {}).get('protocolVersion')
        return dict(protocolVersion=asked if isinstance(asked, str) and asked else PROTOCOL,
                    capabilities=dict(tools=dict(listChanged=False)),
                    serverInfo=dict(name=NAME, version=VERSION,
                                    title='GATOR workbench: read Virtuoso, write the working copy'))
    if method == 'ping':
        return {}
    if method == 'tools/list':
        answer = ask('list', {})
        return dict(tools=answer.get('tools') or [])
    if method == 'tools/call':
        params = message.get('params') or {}
        answer = ask('call', dict(name=params.get('name'), arguments=params.get('arguments') or {}))
        ok = bool(answer.get('ok'))
        content = json.dumps(answer.get('result') if ok else answer.get('error'), default=str, indent=1)
        return dict(content=[dict(type='text', text=content)], isError=not ok)
    raise LookupError(method)


def main(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue                                            # not our business: the CLI owns the framing
        if not isinstance(message, dict):
            continue
        try:
            result = handle(message)
        except LookupError as exc:
            result = None
            answer = dict(jsonrpc='2.0', id=message.get('id'), error=dict(code=-32601, message=f'Unknown method {exc}'))
        except Exception as exc:                                # never die on one message
            result = None
            answer = dict(jsonrpc='2.0', id=message.get('id'), error=dict(code=-32603, message=f'{type(exc).__name__}: {exc}'))
        else:
            if result is None:
                continue
            answer = dict(jsonrpc='2.0', id=message.get('id'), result=result)
        stdout.write(json.dumps(answer) + '\n')
        stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
