"""Live progress of an agent request: the CLI's JSON lines, turned into a few plain events for the page.

Claude Code (`LiveTranslator`), checked against `claude` 2.1.278 with two real requests on 2026-09-21 (status record 7.48):
  * `--include-partial-messages` adds `stream_event` lines that wrap the API's own stream events;
  * `--thinking-display summarized` makes `thinking_delta` carry a readable SUMMARY of the model's thinking. Without it
    a `-p` request asks for none: thinking blocks arrive empty, with a signature only;
  * the answer is the input of the `StructuredOutput` tool call. With CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING=1 it
    arrives as `input_json_delta` pieces of a few words each (one about every 50 ms), in the order the model writes the
    fields - the schema lists `reasoning` right after `kind`, so the reply text comes before the rows.
Codex (`CodexTranslator`, status record 7.50): `codex exec --json` prints one event per line - thread.started,
turn.started, item.started / item.updated / item.completed, turn.completed, turn.failed, error - carrying WHOLE items
(reasoning, agent_message, command_execution, web_search, mcp_tool_call, file_change, todo_list, error). There are no
text pieces, so a reasoning summary appears item by item and the answer in one piece. Taken from the Codex
documentation ("Non-interactive mode") and the event types of its TypeScript SDK (sdk/typescript/src/events.ts,
items.ts), read on 2026-09-21; `codex` was never installed here, so no real stream of it has been seen.
Everything here is DISPLAY only. The proposal still comes from the CLI's final answer and is validated exactly as
before; a piece that cannot be read is skipped, never guessed at.
"""
from __future__ import annotations

import json

from ..security import redact

ANSWER_TOOL = 'StructuredOutput'
REPLY_FIELD = 'reasoning'
QUIET_TOOLS = ('ToolSearch',)          # loads the definitions of the web tools: bookkeeping, not a step worth showing
TOOL_PREFIX = 'mcp__gator__'           # the workbench's own tools (agents/tools.py), said in plain words in the chat


def workbench_step(tool, data) -> str:
    """What a call of the workbench's own tools reads like in the conversation."""
    name, data = tool[len(TOOL_PREFIX):], data if isinstance(data, dict) else {}
    if name == 'virtuoso_libraries':
        return 'Virtuoso: listing the libraries'
    if name == 'virtuoso_cells':
        return f"Virtuoso: listing the cells of {data.get('library', '')}"
    if name == 'virtuoso_read_cell':
        return f"Virtuoso: reading {data.get('library', '')}/{data.get('cell', '')}"
    if name == 'working_copy_facts':
        return 'Looking at the working copy: what may be set there'
    if name == 'working_copy_setup':
        return "Reading the working copy's Maestro setup"
    if name == 'working_copy_write_setup':
        parts = [part for part in ('analyses', 'outputs', 'specs', 'variables', 'bindings') if data.get(part) is not None]
        return 'Writing into the working copy: ' + (', '.join(parts) if parts else 'the Maestro setup')
    return f'Workbench tool: {name}'


class PartialAnswer:
    """Reads the JSON object of the answer while it arrives in pieces. It reports each top-level field the model starts
    writing, and the decoded text of one string field (`reasoning`) as it grows. One pass over each character."""

    def __init__(self, field=REPLY_FIELD):
        self.field = field
        self.depth = 0
        self.in_string = self.escape = self.is_key = self.expect_key = self.capture = False
        self.key = []
        self.hex = None                # the digits of a \\uXXXX escape still being read
        self.high = None               # a high surrogate waiting for its low half

    def feed(self, piece: str):
        """Returns (top-level fields started in this piece, new text of the reply field)."""
        started, text = [], []
        for ch in piece:
            if self.in_string:
                self._in_string(ch, started, text)
            elif ch == '"':
                self.in_string = True
                if self.depth == 1 and self.expect_key:
                    self.is_key, self.expect_key, self.key = True, False, []
                elif self.depth == 1 and self.key == [self.field]:
                    self.capture = True
            elif ch in '{[':
                self.depth += 1
                self.expect_key = self.depth == 1 and ch == '{'
            elif ch in '}]':
                self.depth -= 1
            elif ch == ',' and self.depth == 1:
                self.expect_key = True
        return started, ''.join(text)

    def _in_string(self, ch, started, text):
        if self.hex is not None:                                   # inside \\uXXXX
            self.hex += ch
            if len(self.hex) == 4:
                self._code_point(int(self.hex, 16) if all(c in '0123456789abcdefABCDEF' for c in self.hex) else 0xFFFD, text)
                self.hex = None
            return
        if self.escape:
            self.escape = False
            if ch == 'u':
                self.hex = ''
            else:
                self._char({'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f'}.get(ch, ch), text)
            return
        if ch == '\\':
            self.escape = True
        elif ch == '"':
            self.in_string = False
            if self.is_key:
                self.is_key = False
                started.append(''.join(self.key))
                self.key = [''.join(self.key)]                     # the field whose value comes next
            elif self.capture:
                self.capture = False
                self.key = []                                      # the reply is complete; a later field of the same name is not it
        else:
            self._char(ch, text)

    def _code_point(self, code, text):
        if 0xD800 <= code <= 0xDBFF:
            self.high = code
            return
        if 0xDC00 <= code <= 0xDFFF and self.high is not None:
            code, self.high = 0x10000 + ((self.high - 0xD800) << 10) + (code - 0xDC00), None
        self._char(chr(code) if not 0xD800 <= code <= 0xDFFF else '�', text)

    def _char(self, ch, text):
        if self.high is not None:                                  # a lone high surrogate: shown as a replacement mark
            self.high = None
            if self.capture:
                text.append('�')
        if self.is_key:
            self.key.append(ch)
        elif self.capture:
            text.append(ch)


class LiveTranslator:
    """Feed it every stdout line of `claude -p --output-format stream-json --verbose --include-partial-messages`; it
    calls `emit` with small dicts the page shows while the agent works:
      model    {model}          the model the CLI actually runs
      thinking {text}           more of the thinking summary ('' when a thinking block starts without text)
      step     {text}           a tool call (web search, page opened...) or an API retry
      say      {text, new}      free text the agent writes between steps (`new`: a new paragraph starts)
      writing  {field}          the answer reached this top-level field (reasoning, patch, suggestions...)
      reply    {text}           more of the reply text (the `reasoning` field)
      restart  {}               the answer is being written again (the CLI asked the model to retry it)
    Lines of a subagent and anything unexpected are ignored."""

    def __init__(self, emit):
        self.emit = emit
        self.blocks = {}               # index -> kind of the content block, for the current message
        self.answer = None             # PartialAnswer of the StructuredOutput call being written
        self.thought = False           # some thinking was shown: a later thinking block starts a new paragraph

    def feed(self, line: str):
        line = line.strip()
        if not line.startswith('{'):
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict) or event.get('parent_tool_use_id'):
            return
        kind = event.get('type')
        if kind == 'stream_event' and isinstance(event.get('event'), dict):
            self._stream(event['event'])
        elif kind == 'assistant':
            self._steps(event.get('message') or {})
        elif kind == 'system' and event.get('subtype') == 'init' and event.get('model'):
            self.emit(dict(type='model', model=str(event['model'])[:80]))
        elif kind == 'system' and event.get('subtype') == 'api_retry':
            status = event.get('error_status')
            wait = (event.get('retry_delay_ms') or 0) / 1000
            self.emit(dict(type='step', text=f"The model service did not answer{f' (HTTP {status})' if status else ''}; the CLI "
                                            f"retries in {wait:.0f} s (attempt {event.get('attempt')} of {event.get('max_retries')})."))

    def _stream(self, event):
        kind = event.get('type')
        if kind == 'message_start':
            self.blocks = {}
        elif kind == 'content_block_start':
            block = event.get('content_block') or {}
            index, block_type = event.get('index'), block.get('type')
            self.blocks[index] = ANSWER_TOOL if block_type == 'tool_use' and block.get('name') == ANSWER_TOOL else block_type
            if block_type == 'thinking':
                self.emit(dict(type='thinking', text='\n\n' if self.thought else ''))
            elif self.blocks[index] == ANSWER_TOOL:
                if self.answer is not None:
                    self.emit(dict(type='restart'))
                self.answer = PartialAnswer()
            elif block_type == 'text':
                self.emit(dict(type='say', text='', new=True))
        elif kind == 'content_block_delta':
            delta = event.get('delta') or {}
            block = self.blocks.get(event.get('index'))
            if delta.get('type') == 'thinking_delta' and delta.get('thinking'):
                self.thought = True
                self.emit(dict(type='thinking', text=delta['thinking']))
            elif delta.get('type') == 'text_delta' and delta.get('text'):
                self.emit(dict(type='say', text=delta['text'], new=False))
            elif delta.get('type') == 'input_json_delta' and block == ANSWER_TOOL and self.answer is not None:
                started, text = self.answer.feed(delta.get('partial_json') or '')
                for field in started:
                    self.emit(dict(type='writing', field=field[:60]))
                if text:
                    self.emit(dict(type='reply', text=text))

    def _steps(self, message):
        """A finished tool call, as one line. The complete assistant message carries the whole input."""
        for block in message.get('content') or []:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            name, data = block.get('name'), block.get('input') or {}
            if name == ANSWER_TOOL or name in QUIET_TOOLS:
                continue
            if isinstance(name, str) and name.startswith(TOOL_PREFIX):
                self.emit(dict(type='step', text=redact(workbench_step(name, data), 300)))
                continue
            if name == 'WebSearch':
                text = f"Searching the web: {data.get('query', '')}"
            elif name == 'WebFetch':
                text = f"Opening {data.get('url', '')}"
            elif name in ('Read', 'Grep', 'Glob'):
                text = f"{name}: {data.get('file_path') or data.get('pattern') or ''}"
            else:
                text = f'Using {name}'
            self.emit(dict(type='step', text=redact(text, 300)))


class CodexTranslator:
    """Feed it every stdout line of `codex exec --json`; it calls `emit` with the events of `LiveTranslator` (no `model`,
    no `restart`: the stream carries neither). Items come whole, so:
      * a reasoning summary is shown when its item arrives (an `item.updated` that extends it adds the rest);
      * commands, web searches, tool calls, file changes, a plan and item errors are steps, once per item;
      * the final agent message is the answer: its `reasoning` field is the reply, shown in one piece. A message that is not
        such an answer (a remark on the way) is `say` text.
    `last_message` keeps the text of the last agent message: the answer if a CLI version wrote no output file."""

    def __init__(self, emit):
        self.emit = emit
        self.shown = {}                # reasoning item id -> the text already shown
        self.stepped = set()           # item ids (and "<id>:failed") already shown as a step
        self.thought = False           # some reasoning was shown: the next item starts a new paragraph
        self.last_message = None

    def feed(self, line: str):
        line = line.strip()
        if not line.startswith('{'):
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict):
            return
        kind = event.get('type')
        if kind == 'turn.started':
            self.emit(dict(type='thinking', text=''))                  # the model is at work: "Thinking..."
        elif kind in ('item.started', 'item.updated', 'item.completed') and isinstance(event.get('item'), dict):
            self._item(event['item'], done=kind == 'item.completed')
        elif kind == 'turn.failed':
            message = (event.get('error') or {}).get('message') if isinstance(event.get('error'), dict) else None
            self.emit(dict(type='step', text=redact(f"The turn failed: {message or 'no reason given'}", 300)))
        elif kind == 'error' and event.get('message'):
            self.emit(dict(type='step', text=redact(f"codex: {event['message']}", 300)))

    def _item(self, item, done):
        kind, key, text = item.get('type'), item.get('id'), item.get('text')
        if kind == 'reasoning':
            if isinstance(text, str) and text:
                before = self.shown.get(key, '')
                new = text[len(before):] if text.startswith(before) else '\n\n' + text
                if new:
                    self.emit(dict(type='thinking', text=('\n\n' if self.thought and not before else '') + new))
                    self.thought = True
                self.shown[key] = text
            return
        if kind == 'agent_message':
            if done and isinstance(text, str):
                self.last_message = text
                try:
                    answer = json.loads(text)
                except json.JSONDecodeError:
                    answer = None
                if isinstance(answer, dict) and isinstance(answer.get(REPLY_FIELD), str):
                    self.emit(dict(type='writing', field=REPLY_FIELD))
                    self.emit(dict(type='reply', text=answer[REPLY_FIELD]))
                elif text.strip():
                    self.emit(dict(type='say', text=redact(text, 2000), new=True))
            return
        if kind == 'command_execution' and done and item.get('status') == 'failed' and f'{key}:failed' not in self.stepped:
            self.stepped.add(f'{key}:failed')
            self.emit(dict(type='step', text=redact(f"The command failed (exit {item.get('exit_code')}): {item.get('command', '')}", 300)))
            return
        if key in self.stepped:
            return
        if kind == 'command_execution':
            line = f"Running: {item.get('command', '')}"
        elif kind == 'web_search':
            line = f"Searching the web: {item.get('query', '')}"
        elif kind == 'mcp_tool_call':
            line = f"Using {item.get('server', '')}.{item.get('tool', '')}"
        elif kind == 'file_change':
            line = 'Changing files: ' + ', '.join(str(c.get('path', '')) for c in item.get('changes') or [] if isinstance(c, dict))
        elif kind == 'todo_list':
            line = 'Plan: ' + '; '.join(str(t.get('text', '')) for t in item.get('items') or [] if isinstance(t, dict))
        elif kind == 'error':
            line = f"codex: {item.get('message', '')}"
        else:
            return
        self.stepped.add(key)
        self.emit(dict(type='step', text=redact(line, 300)))
