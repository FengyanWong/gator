"""Which Virtuoso session the page's work goes to, when its connection has more than one (record 7.351).

The user, 2026-10-15, of a connection that reaches two Virtuoso sessions (record 7.345 shows both under one connection):
"send it to whichever is free". The page names the CONNECTION (`lab`); a run (Start, Baseline simulation, Calibration,
Continue), a Check now or a Save task it starts goes to one of the connection's sessions, chosen here:

1. A session is free when nothing holds its lock (record 7.311: every run, check and save holds the lock of the Virtuoso
   session it works in), no queue holds its queue lock (`paths.bridge_queue_lock`: between two runs of a queue the
   session lock is free for a moment) and no run this backend started a moment ago is still on its way to taking it.
2. Of the free sessions, the one that holds the task's cell open for editing - Virtuoso's own lock: a cell held open for
   editing in one Virtuoso cannot be written through another (`cell_hold`). A run lets go of its cell when it ends
   (`cdf_write.CellLocked`), so such a hold is one left by a run from before, or a cell opened by hand.
3. Otherwise the free session whose last connection test passed, the connection's own session first.

A busy session that holds the cell open for editing lets go of it when nothing can be lost (saved, in no window) -
after the work's own refusals that need no Virtuoso (`release_pending`) - so the free session can write it; otherwise the
start is refused in words, and so is a start when no session is free. Nothing is chosen for a connection of one session,
for a session named by its own name (`lab2`, as queues and command-line runs do - those keep exactly their session), or
for a task the older adapter writes (first session only, `tasks._first_session_only`). Command-line runs never come here.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import threading
import time
import uuid

from . import cell_hold, connection, profile_store
from .consistency import lock_holder
from .paths import bridge_cell_lock, bridge_session_dir, bridge_state_dir
from .security import redact
from .task_registry import REAL_PROFILES

PREPARING_SECONDS = 600     # a start's own checks (connection gate, check against Virtuoso) before its run exists
STARTING_SECONDS = 300      # then its worker's start, until the worker holds the session's lock

_GUARD = threading.Lock()   # around the reservations and each decision; never held while Virtuoso is asked
_RESERVED: dict = {}        # session lock path -> dict(token, until, attached, pid, cell, said, profile_id)


class SessionsBusy(RuntimeError):
    """No session of the connection can take the work now; the message says why, session by session."""
    code = 'sessions_busy'

    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report or {}


@dataclass
class Choice:
    # A selected Virtuoso session with its explanation and reservation bookkeeping.
    profile_id: str                       # the session the work goes to (its connection name)
    connection: str                       # the connection the page named
    label: str                            # "Virtuoso 2"
    said: str                             # one sentence for the page and the run's record
    sessions: list = field(default_factory=list)
    lock: str | None = None               # the session lock reserved for the work
    token: str = ''                       # this choice's reservation: `started` and `finished` touch only their own
    # (session, who, library, cell): to let go of the cell first (`release_pending`)
    release: tuple | None = None

    def record(self) -> dict:
        """Return the connection and session details intended for the page and run record."""
        return dict(connection=self.connection, session=self.profile_id, label=self.label, said=self.said,
                    sessions=self.sessions)


def grouped(profile_id) -> bool:
    """Whether there is a session to choose for work on connection `profile_id`: it names a connection - not one of its
    sessions by that session's own name - that has more than one session. One read of the connection file; the callers
    ask it before they read anything about the task."""
    group = connection.session_group(profile_id) if profile_id else []
    return len(group) > 1 and profile_id == group[0]


def _sessions(group, profiles, root) -> list:
    sessions = []
    for index, profile_id in enumerate(group):
        settings = profiles.get(profile_id) or {}
        folder = bridge_session_dir(settings['env_file'], settings.get('profile'),
            root) if settings.get('env_file') else root
        sessions.append(dict(profile_id=profile_id, label=f'Virtuoso {index + 1}', lock=str(folder / 'session.lock'),
                             queue=folder / 'queue.lock', first=folder == root))
    return sessions


def _clock(seconds_ago=0.) -> str:
    return datetime.fromtimestamp(time.time() - seconds_ago).strftime('%H:%M')


def _alive(pid) -> bool:
    """Whether process `pid` still runs (a zombie, ended but not yet collected, does not)."""
    try:
        state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != 'Z'


def _state(session, now):
    """free, busy (its lock or its queue lock is held: by whom) or starting (reserved for a run started here a moment
    ago). Under the guard."""
    holder = lock_holder(Path(session['lock']))
    item = _RESERVED.get(session['lock'])
    if item is not None and (now > item['until'] or (item['attached'] and (holder or not _alive(item['pid'])))):
        _RESERVED.pop(session['lock'], None)    # expired; its worker holds the lock itself now; or the worker has ended
        item = None
    if holder:
        return 'busy', holder
    queue = lock_holder(session['queue'])
    if queue:
        return 'busy', f'a queue works in this session, between two of its runs now: {queue}'
    if item is not None:
        return 'starting', item['said']
    return 'free', None


def _who(session) -> str:
    return f"{session['label']} ({session['profile_id']})"


def _status(monitor, profile_id):
    """The cached result of the session's last connection test (nothing is probed): 'ok', 'failed', ... or None."""
    try:
        return monitor.status(profile_id).get('overall') if monitor is not None else None
    except Exception:
        return None


def _free(sessions, cell, root) -> list:
    """Every session's state now, and the free ones; the refusals that need no Virtuoso. Under the guard."""
    now = time.monotonic()
    for session in sessions:
        session['state'], session['holder'] = _state(session, now)
    if cell is not None and any(item.get('cell') == tuple(cell) for item in _RESERVED.values()):
        raise SessionsBusy(
            f'The cell {cell[0]}/{cell[1]} was given to a run started a moment ago, which is still starting. '
            'Only one run or check works on a cell at a time; try again when it has started or ended.',
            report=dict(sessions=_public(sessions)))
    held = lock_holder(bridge_cell_lock(*cell, root)) if cell is not None else None
    if held:
        raise SessionsBusy(
            f'The cell {cell[0]}/{cell[1]} is in use: {held}. Only one run or check works on a cell at a time, '
            'whatever the Virtuoso session; try again when it has finished.',
            report=dict(sessions=_public(sessions)))
    free = [s for s in sessions if s['state'] == 'free']
    if not free:
        raise SessionsBusy('Every Virtuoso session of this connection is busy: ' + '; '.join(
            f"{_who(s)}: {s['holder']}" for s in sessions) +
                '. Try again when one has finished. A run started from this page stops with Abort; one started '
                'from a command line stops there.',
            report=dict(sessions=_public(sessions)))
    return free


def _ask_all(sessions, monitor, cell):
    """Each session's hold of the cell, asked side by side and read-only: {profile_id: hold dict | None (not asked or no
    answer)}. A session whose last connection test failed is not asked: its answer could only time out."""
    library, name = cell

    def ask(session):
        if _status(monitor, session['profile_id']) == 'failed':
            session['look_error'] = 'not asked: its last connection test failed'
            return None
        try:
            return cell_hold.look(session['profile_id'], library, name)
        except Exception as exc:
            session['look_error'] = redact(f'{type(exc).__name__}: {exc}', 200)
            return None
    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        return dict(zip((s['profile_id'] for s in sessions), pool.map(ask, sessions)))


def choose(profile_id, *, cell=None, first_session_only=False, monitor=None, purpose='run') -> Choice | None:
    """The session for work the page started on connection `profile_id`, reserved for it (`started` / `finished`), or None
    when there is nothing to choose: the connection has one session, `profile_id` names a session by its own name, or
    the task runs in the first session only. `cell`: (library, cell) the work writes, or None. Raises SessionsBusy.
    Virtuoso is asked without the guard, which is held only to read the sessions and to reserve one: a slow answer keeps
    no other choice waiting, and what changed meanwhile is read again before the session is reserved."""
    profiles = connection.load_profiles()['profiles']
    group = next((members for members in connection.session_groups(profiles).values() if profile_id in members),
                 [profile_id])
    if len(group) < 2 or profile_id != group[0]:
        return None
    root = bridge_state_dir()
    sessions = _sessions(group, profiles, root)
    if first_session_only:
        eligible = [s for s in sessions if s['first']]
        if len(eligible) < 2:
            return None                                     # the connection's first session, as before
        sessions = eligible
    holds = {}
    if cell is not None:
        with _GUARD:
            free = _free(sessions, cell, root)
        # Asked only where the answer can change the choice: a busy session (it must let go of the cell for a free one
        # to write it), and the free ones only when there is more than one of them to choose from.
        asked = [s for s in sessions if s['state'] != 'free' or len(free) > 1]
        holds = _ask_all(asked, monitor, cell) if asked else {}
    with _GUARD:
        free = _free(sessions, cell, root)                  # again: anything may have changed while Virtuoso answered
        for session in sessions:
            session['hold'] = holds.get(session['profile_id'])
        owner = next((s for s in sessions if (s['hold'] or {}).get('editing')), None)
        release = None
        if owner is not None and owner['state'] == 'free':
            chosen, why = owner, 'it holds the cell open for editing, so only it can write the cell now'
        else:
            # a busy session holds the cell: it lets go of it, or a refusal
            if owner is not None:
                hold, where = owner['hold'], f'{cell[0]}/{cell[1]}'
                if not hold['saved']:
                    raise SessionsBusy(
                        f'{_who(owner)} holds {where} open for editing with unsaved edits, and is busy ('
                        f"{owner['holder']}). Save or discard the edits there, or wait until it is free.",
                        report=dict(sessions=_public(sessions)))
                if hold['windows']:
                    raise SessionsBusy(f'{_who(owner)} shows {where} in a window, open for editing, and is busy '
                                       f"({owner['holder']}). Close that window or make the cell read-only there "
                                       '(Design > Make Read Only), then start again.',
                                       report=dict(sessions=_public(sessions)))
                release = (owner['profile_id'], _who(owner), *cell)
            # The free session whose last test passed first; the connection's own session first among equals.
            chosen = min(free, key=lambda s: (_status(monitor, s['profile_id']) != 'ok', sessions.index(s)))
            busy = [s for s in sessions if s['state'] != 'free']
            why = ('it is free; ' + '; '.join(f"{_who(s)} is busy: {s['holder']}" for s in busy) if busy else
                   "every session is free, and it is the connection's own" if chosen is sessions[0] else
                   f"every session is free, and the last connection test of {_who(sessions[0])} did not pass")
        said = f"Virtuoso session: {_who(chosen)} - {why}."
        if release is not None:
            said += (f" {owner['label']} let go of the cell it held open for editing (saved, in no window), so that "
                     f"{chosen['label']} can write it.")
        token = uuid.uuid4().hex
        _RESERVED[chosen['lock']] = dict(token=token, until=time.monotonic() + PREPARING_SECONDS, attached=False,
                                         pid=None,
                                         profile_id=chosen['profile_id'],
                                         cell=tuple(cell) if cell is not None else None,
                                         said=f'a {purpose} started from this page at {_clock()} is starting there')
        for session in sessions:
            session['chosen'] = session is chosen
        return Choice(profile_id=chosen['profile_id'], connection=group[0], label=chosen['label'], said=said,
                      sessions=_public(sessions), lock=chosen['lock'], token=token, release=release)


def _public(sessions) -> list:
    return [dict(profile_id=s['profile_id'], label=s['label'], state=s.get('state'), holder=s.get('holder'),
                 hold=s.get('hold'), **({'look_error': s['look_error']} if s.get('look_error') else {}),
                 **({'chosen': True} if s.get('chosen') else {})) for s in sessions]


def release_pending(choice: Choice | None, monitor) -> None:
    """The busy session the choice found holding the cell open for editing lets go of it (`cell_hold.release`, gated:
    a write) - called after the work's own refusals that need no Virtuoso and before its first write, so a refused
    start changes nothing in Virtuoso. SessionsBusy, in words, when it fails; the caller lets the reservation go."""
    if choice is None or choice.release is None:
        return
    holder, who, library, cell = choice.release
    try:
        cell_hold.release(monitor, holder, library, cell)
    except Exception as exc:
        raise SessionsBusy(
            f'{who} holds {library}/{cell} open for editing and is busy; letting go of the cell there failed: '
                           f'{redact(str(exc), 300)}. Start again when it is free.') from None
    choice.release = None


def started(choice: Choice | None, pid: int) -> None:
    """The run's worker `pid` is starting: the session stays reserved until the worker holds its lock, or has ended."""
    if choice is None:
        return
    with _GUARD:
        item = _RESERVED.get(choice.lock)
        if item is not None and item['token'] == choice.token:
            item.update(attached=True, pid=pid, until=time.monotonic() + STARTING_SECONDS)


def finished(choice: Choice | None) -> None:
    """The work ended (a check, a save) or never began (a refused start): its session is free to choose again. Only this
    choice's own reservation goes - one that outlived its time limit leaves a newer start's alone."""
    if choice is None:
        return
    with _GUARD:
        item = _RESERVED.get(choice.lock)
        if item is not None and item['token'] == choice.token:
            del _RESERVED[choice.lock]


def task_cell(config):
    """(library, cell) a configuration's task writes, and whether it runs in the first session only: the working copy of a
    task made from a Virtuoso cell (its list entry, as the cell's lock is found: `consistency.task_locks`); (None, True)
    for a built-in real task (its older adapter, `tasks._first_session_only`); (None, False) when there is nothing to say
    (MOCK, ngspice)."""
    circuit = config.circuit
    task_id = getattr(circuit, 'task_id', None) or ''
    if getattr(circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return None, False
    name = task_id[len('real:'):]
    if name in REAL_PROFILES:
        return None, True
    entry = profile_store.profile_entry(name)
    if entry and entry.get('library') and entry.get('core_cell'):
        return (entry['library'], entry['core_cell']), False
    return None, False


def route(config, monitor, *, purpose='run'):
    """(the configuration with the chosen session, Choice) for a real Virtuoso task of the page; the configuration as it is
    and None when there is nothing to choose. Raises SessionsBusy. The choice's release, if any, is still to be done
    (`release_pending`)."""
    profile_id = config.run.connection_profile_id
    if not grouped(profile_id):
        return config, None
    cell, first_only = task_cell(config)
    if cell is None and not first_only and not (getattr(config.circuit, 'task_id', '') or '').startswith('real:'):
        return config, None
    choice = choose(profile_id, cell=cell, first_session_only=first_only, monitor=monitor, purpose=purpose)
    return with_session(config, choice), choice


def with_session(config, choice):
    """`config` sent to the chosen session (a copy when that is another connection name)."""
    if choice is None or choice.profile_id == config.run.connection_profile_id:
        return config
    routed = config.model_copy(deep=True)
    routed.run.connection_profile_id = choice.profile_id
    return routed
