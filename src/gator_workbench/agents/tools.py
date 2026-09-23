"""What the Agent tab's agent may DO while it works: named workbench operations, nothing raw (status record 7.68).

The level the user chose on 2026-09-22 is "read + write the working copy": the agent may READ from Virtuoso and WRITE
the Maestro setup of the task's WORKING COPY. It may not write the user's own cells, it may not write device sizes (a
size written between runs makes the run's consistency check refuse to start; sizes are the optimizer's, written inside a
run and restored afterwards), it may not start a simulation, and there is no shell and no raw SKILL - only the calls
below exist.

Every tool is a thin wrapper around the function a BUTTON uses, so the connection gate, the Virtuoso session lock, the
name checks and the records apply unchanged. Four things the agent cannot reach through this module:
  * WHICH copy is written - the backend resolves it from the request's own configuration, never from a tool argument;
  * a tool that is not granted to the request's kind: the session refuses it, and the tool server does not even list it;
  * more calls than this request's budget, so a loop cannot run away (the user's "Cancel request" also stops it);
  * anything at all once the request is over: the session is closed and its token stops working.
Every call is recorded in `configs/local/workbench/agent_tool_calls.jsonl` and shown in the chat while it happens.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time

from .. import virtuoso_setup, working_copy
from ..security import redact

SERVER = 'gator'                     # the MCP server name the CLI is given; a tool is `mcp__gator__<name>` to the model
MAX_CALLS = 80                       # per request, over all tools
MAX_WRITES = 12                      # per request; a write is one Maestro setup written into the copy
MAX_RESULT = 40_000                  # characters of one result handed to the model


class ToolRefused(Exception):
    """A call the workbench does not allow. Told to the agent as an error result - never a crash of the request."""


def _cap(value):
    text = json.dumps(value, default=str)
    if len(text) <= MAX_RESULT:
        return value
    return dict(truncated=True, note=f'The result was longer than {MAX_RESULT} characters; ask for a smaller part of it.',
                head=text[:MAX_RESULT])


# ------------------------------------------------------------------------------- the tools
def _libraries(session, arguments):
    """Every library Virtuoso lists."""
    return session.read('libraries')


def _cells(session, arguments):
    """The cells of one library, with the views each has."""
    return session.read('cells', library=arguments['library'])


def _read_cell(session, arguments):
    """One schematic as Virtuoso reports it: instances with their parameters, and the nets between them."""
    return session.read('read_schematic', library=arguments['library'], cell=arguments['cell'])


def _copy_facts(session, arguments):
    """The working copy this request is about - no Virtuoso call, the workbench's own records."""
    target = session.target()
    bindable = working_copy.bindable_on(target)
    own = working_copy.is_declared(target)                 # the user's own copy, declared on the read: written directly
    return dict(copy=target['copy'], cell_you_drew=None if own else target['original'], own_copy=own, test=virtuoso_setup.TEST,
                last_written_by_the_workbench=working_copy.last_written(target) or None,
                bindable=[dict(cell=c, instance=i, parameters=sorted(p)) for (c, i), p in sorted(bindable.items())],
                allowed_functions=sorted(virtuoso_setup.FUNCTIONS),
                model_files=working_copy.default_model_files(session.profile_id),
                note=('This is the cell the user declared as a copy they made; the workbench writes into it directly. ' if own else '')
                     + 'Only these instance parameters may be set to a Maestro variable. Transistor sizes are not among '
                     'them and are not yours to write: the optimizer writes them inside a run and restores them.')


def _copy_setup(session, arguments):
    """What the copy's Maestro test holds right now, read back from Virtuoso."""
    return working_copy.read_setup_on(session.monitor, session.profile_id, session.target())


def _write_setup(session, arguments):
    """Write the Maestro setup into the copy, read it back and say what differs. A part left out stays as it is."""
    session.charge_write()
    target = session.target()
    parts = {name: arguments.get(name) for name in ('analyses', 'variables', 'bindings', 'outputs', 'specs',
                                                    'initial_conditions')}
    if parts['outputs'] is None or parts['specs'] is None:            # left out: keep what the copy has
        current = working_copy.read_setup_on(session.monitor, session.profile_id, target)
        for name in ('outputs', 'specs'):
            if parts[name] is None:
                parts[name] = current.get(name) or []
    setup = dict(test=virtuoso_setup.TEST, **parts)
    try:
        written = working_copy.write_setup_on(session.monitor, session.profile_id, target, setup)
    except virtuoso_setup.SetupError as exc:
        raise ToolRefused(str(exc))
    session.wrote = True
    return dict(copy=target['copy'], matches=written['matches'], differences=written['differences'],
                now=dict(analyses=written.get('analyses'), outputs=written.get('outputs'), specs=written.get('specs'),
                         variables=written.get('variables'), bindings=written.get('bindings')),
                note='Written into the working copy only' + (' - the cell the user declared as their copy' if working_copy.is_declared(target)
                                                             else ', not into the cell the user drew') + '. Nothing was simulated.')


ROW = dict(type='object', additionalProperties=False)
TOOLS = {
    'virtuoso_libraries': dict(
        handler=_libraries, writes=False, virtuoso=True,
        description='List the libraries of the Virtuoso session. Read-only.',
        schema=dict(type='object', additionalProperties=False, properties={})),
    'virtuoso_cells': dict(
        handler=_cells, writes=False, virtuoso=True,
        description='List the cells of one library, with the views each of them has. Read-only.',
        schema=dict(type='object', additionalProperties=False, required=['library'],
                    properties=dict(library=dict(type='string', description='Library name as Virtuoso spells it')))),
    'virtuoso_read_cell': dict(
        handler=_read_cell, writes=False, virtuoso=True,
        description='Read one schematic: its instances with their parameters, and the nets between them. Read-only, any library.',
        schema=dict(type='object', additionalProperties=False, required=['library', 'cell'],
                    properties=dict(library=dict(type='string'), cell=dict(type='string')))),
    'working_copy_facts': dict(
        handler=_copy_facts, writes=False, virtuoso=False,
        description='The working copy of THIS task: its library and cells, which instance parameters may be set to a Maestro '
                    'variable, the calculator functions an output may call, the model file, and what the workbench last wrote. '
                    'No Virtuoso call.',
        schema=dict(type='object', additionalProperties=False, properties={})),
    'working_copy_setup': dict(
        handler=_copy_setup, writes=False, virtuoso=True,
        description="Read the working copy's Maestro test as it is now: analyses, outputs, specs, variables and bindings.",
        schema=dict(type='object', additionalProperties=False, properties={})),
    'working_copy_write_setup': dict(
        handler=_write_setup, writes=True, virtuoso=True,
        description='Write the Maestro setup into the working copy (never your own cell, no simulation), read it back and '
                    'report what differs. A part you leave out keeps what the copy has. Outputs are Cadence calculator '
                    'expressions; a spec limits one output.',
        schema=dict(type='object', additionalProperties=False, properties=dict(
            analyses=dict(type='object', description='Analysis name -> its options, e.g. {"tran": {"stop": "20n"}}. '
                                                     'Left out: the copy keeps its analyses.',
                          additionalProperties=dict(type='object')),
            outputs=dict(type='array', description='Named expressions, e.g. {"name": "osc_frequency_hz", "expression": '
                                                   '"frequency(VT(\\"/OUT\\"))"}. Left out: the copy keeps its outputs.',
                         items=dict(ROW, required=['name', 'expression'],
                                    properties=dict(name=dict(type='string'), expression=dict(type='string')))),
            specs=dict(type='array', description='A limit on one output: op "gt" or "lt" with one value, "range" with two.',
                       items=dict(ROW, required=['output', 'op', 'value'],
                                  properties=dict(output=dict(type='string'), op=dict(enum=['gt', 'lt', 'range']),
                                                  value=dict(anyOf=[dict(type='string'), dict(type='number'),
                                                                    dict(type='array', items=dict(type=['string', 'number']))])))),
            variables=dict(type='object', description='Maestro design variables: name -> value.',
                           additionalProperties=dict(type=['string', 'number'])),
            initial_conditions=dict(type='object', description='A start voltage per net for a circuit that does not start by '
                                                               'itself (an oscillator sits in its symmetric DC point forever), '
                                                               'e.g. {"OUT": "0.9", "XU1.N1": "0"}; nets as the netlist spells '
                                                               'them. Left out: the copy keeps what it has, {} clears them.',
                                    additionalProperties=dict(type=['string', 'number'])),
            bindings=dict(type='array', description='Instance parameters set to a variable. Only what working_copy_facts '
                                                    'lists as bindable; a transistor size can never be one.',
                          items=dict(ROW, required=['cell', 'instance', 'parameter', 'variable'],
                                     properties=dict(cell=dict(type='string'), instance=dict(type='string'),
                                                     parameter=dict(type='string'), variable=dict(type='string'))))))),
}
GRANTS = {'virtuoso_work': tuple(TOOLS)}          # per request KIND, never from the settings file (agents/base.py)


def granted(kind) -> tuple:
    return GRANTS.get(kind, ())


def mcp_names(names) -> list:
    return [f'mcp__{SERVER}__{name}' for name in names]


def plain_name(tool) -> str:
    """`mcp__gator__virtuoso_cells` -> `virtuoso_cells`; anything else unchanged."""
    prefix = f'mcp__{SERVER}__'
    return tool[len(prefix):] if isinstance(tool, str) and tool.startswith(prefix) else tool


def check_arguments(schema, arguments):
    """The names of a call, against the tool's own schema: no unknown argument reaches a handler, and a missing required
    one is said plainly. The VALUES are checked where they are used - by the setup validation and by Virtuoso itself."""
    allowed = set(schema.get('properties') or {})
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise ToolRefused(f'This tool has no argument {", ".join(unknown)} (it takes: {", ".join(sorted(allowed)) or "none"}).')
    missing = sorted(set(schema.get('required') or ()) - set(arguments))
    if missing:
        raise ToolRefused(f'This tool needs {", ".join(missing)}.')


def described(names) -> list:
    """The granted tools as the tool server lists them (MCP `tools/list`)."""
    return [dict(name=name, description=TOOLS[name]['description'], inputSchema=TOOLS[name]['schema'])
            for name in names if name in TOOLS]


# ------------------------------------------------------------------------------- one request's session
@dataclass
class ToolSession:
    """The tools of ONE agent request. It holds what the agent may not choose: the copy it writes into, the connection
    it goes through, and how many calls it has left."""
    request_id: str
    token: str
    kind: str
    monitor: object
    profile_id: str | None
    target: object                                 # callable() -> the working copy of this request's configuration
    read: object                                   # callable(op, **names) -> a Virtuoso read (bridge_read)
    on_call: object = None                         # callable(entry) - the live step and the record
    names: tuple = ()
    calls: int = 0
    writes: int = 0
    wrote: bool = False                            # this request changed the copy
    closed: bool = False
    history: list = field(default_factory=list)

    def charge_write(self):
        if self.writes >= MAX_WRITES:
            raise ToolRefused(f'This request has written the setup {MAX_WRITES} times, which is its limit. Say what is '
                              'still missing in your answer instead.')
        self.writes += 1

    def call(self, name, arguments) -> dict:
        """Run one granted tool. Returns {ok, result} or {ok: False, error} - a refusal is an answer, not an exception."""
        started = time.monotonic()
        name = plain_name(name)
        entry = dict(request_id=self.request_id, tool=name, arguments=arguments)
        try:
            if self.closed:
                raise ToolRefused('This request is over; its tools are closed.')
            if name not in self.names or name not in TOOLS:
                raise ToolRefused(f'{name!r} is not one of the tools of this request ({", ".join(self.names) or "none"}).')
            if self.calls >= MAX_CALLS:
                raise ToolRefused(f'This request has used its {MAX_CALLS} tool calls. Answer with what you have.')
            if not isinstance(arguments, dict):
                raise ToolRefused('Arguments must be an object.')
            check_arguments(TOOLS[name]['schema'], arguments)
            self.calls += 1
            result = TOOLS[name]['handler'](self, arguments)
            answer = dict(ok=True, result=_cap(result))
        except ToolRefused as exc:
            answer = dict(ok=False, error=redact(str(exc), 2000))
        except PermissionError as exc:                             # the connection gate
            answer = dict(ok=False, error=redact(f'The workbench refused the Virtuoso connection for this: {exc}', 2000))
        except (KeyError, ValueError, OSError) as exc:
            answer = dict(ok=False, error=redact(f'{type(exc).__name__}: {exc}', 2000))
        except Exception as exc:                                   # never take the request down over a tool
            answer = dict(ok=False, error=redact(f'The workbench could not do that: {type(exc).__name__}: {exc}', 2000))
        entry.update(ok=answer['ok'], error=answer.get('error'), seconds=round(time.monotonic() - started, 3))
        self.history.append(entry)
        if self.on_call:
            try:
                self.on_call(entry)
            except Exception:
                pass                                               # a display or a record must not fail a tool call
        return answer

    def close(self):
        self.closed = True
