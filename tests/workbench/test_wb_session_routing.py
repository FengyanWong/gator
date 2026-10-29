"""Work the page starts goes to whichever Virtuoso session of its connection is free (record 7.351; user, 2026-10-15, of a
connection that reaches two Virtuoso sessions: "send it to whichever is free").

The page names the connection; a run, a Check now or a Save task goes to a free session of it - first the one that holds
the task's cell open for editing (Virtuoso's own lock), then the one whose last test passed, the connection's own first.
A busy session that holds the cell lets go of it when nothing can be lost; a run lets go of its own cell when it ends.
Virtuoso itself is a stand-in here: the look at a cell and letting go of it are replaced, and the adapter's client is the
fake of `fakes_virtuoso`."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from gator_workbench import cdf_write, cell_hold, connection, paths, profiles, schema, session_routing, tasks
from gator_workbench.run_lock import RunLock
from cdf_write_support import make
from fakes_virtuoso import backend_of
from helpers import make_config

SETTINGS = ('VB_REMOTE_HOST=simhost\nVB_REMOTE_PORT=65001\nVB_LOCAL_PORT=65221\n'
            'VB_REMOTE_HOST_s2=simhost\nVB_REMOTE_PORT_s2=65017\nVB_LOCAL_PORT_s2=65222\n')
CELL = ('GATOR_TESTS', 'ota')


@pytest.fixture(autouse=True)
def _no_reservations():
    """Clear process-local session reservations before and after each test."""
    session_routing._RESERVED.clear()
    yield
    session_routing._RESERVED.clear()


def connections(tmp_path, **extra):
    """`lab` reaches the first Virtuoso session and `lab2` the second, as one connection (`session_group`)."""
    settings = tmp_path / '.env'
    settings.write_text(SETTINGS)
    one = dict(env_file=str(settings), library='GATOR_TESTS', model_file='/pdk/model.scs')
    target = paths.local_settings_dir() / 'bridge_connection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(active='lab', profiles=dict(
        lab=dict(one, profile=None), lab2=dict(one, kind='virtuoso_ssh', profile='s2', session_group='lab'),
        **{key: dict(one, **value) for key, value in extra.items()}))))
    return settings


def first_lock():
    """Return the default connection's session-lock path."""
    return paths.bridge_session_lock()


def second_lock(settings):
    """Return the second session's lock path for the supplied connection settings."""
    return paths.bridge_session_lock(settings, 's2')


def holder_of(lock):
    """Another process that holds `lock` until it is killed (a run, as the lock's reader sees one)."""
    Path(lock).parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen([sys.executable, '-c', 'import fcntl, sys, time\nf = open(sys.argv[1], "a+")\n'
                                'fcntl.flock(f, fcntl.LOCK_EX)\nprint("held", flush=True)\ntime.sleep(60)', str(lock)],
                               stdout=subprocess.PIPE, text=True)
    assert process.stdout.readline() == 'held\n'
    return process


class Monitor:
    """The connection monitor's cached results: nothing is probed."""
    def __init__(self, **states):
        self.states = states

    def status(self, profile_id):
        """Report the configured readiness state for one connection profile."""
        return dict(overall=self.states.get(profile_id, 'unknown'))


def holds(monkeypatch, answers, released=None):
    """Virtuoso's answers about the cell, per session: a hold dict, or an exception to raise."""
    asked = []

    def look(profile_id, library, cell, **_):
        """Return scripted cell-ownership facts while asserting the routing guard is released."""
        assert not session_routing._GUARD.locked()          # Virtuoso is asked without the guard: nobody else waits
        asked.append(profile_id)
        answer = answers.get(profile_id, dict(open=False, editing=False, saved=True, windows=0))
        if isinstance(answer, Exception):
            raise answer
        return answer

    def release(monitor, profile_id, library, cell, **_):
        """Record a simulated cell release or raise the configured release error."""
        if isinstance(released, Exception):
            raise released
        (released if isinstance(released, list) else []).append((profile_id, library, cell))
        return True
    monkeypatch.setattr(session_routing.cell_hold, 'look', look)
    monkeypatch.setattr(session_routing.cell_hold, 'release', release)
    return asked


EDITING = dict(open=True, editing=True, saved=True, windows=0)


def test_one_entry_per_virtuoso_session_joins_a_connection(tmp_path):
    connections(tmp_path, lab3=dict(kind='virtuoso_ssh', profile='s2', session_group='lab'),       # s2 again: not a session
                solo=dict(profile=None))
    groups = connection.session_groups(connection.load_profiles()['profiles'])
    assert groups == {'lab': ['lab', 'lab2']}
    assert connection.session_group('lab2') == connection.session_group('lab') == ['lab', 'lab2']
    assert connection.session_group('lab3') == ['lab3'] and connection.session_group('nobody') == ['nobody']
    shown = {g['profile_id']: g['session_profile_ids'] for g in connection.public_profiles()['groups']}
    assert shown == {'lab': ['lab', 'lab2'], 'lab3': ['lab3'], 'solo': ['solo']}        # the second card of s2 is its own


def test_nothing_is_chosen_for_one_session_a_session_named_by_its_own_name_or_a_first_session_task(tmp_path, monkeypatch):
    connections(tmp_path, solo=dict(profile=None))
    asked = holds(monkeypatch, {})
    assert session_routing.choose('solo', cell=CELL) is None
    assert session_routing.choose('lab2', cell=CELL) is None                   # a queue's session stays its session
    assert session_routing.choose('lab', cell=None, first_session_only=True) is None
    assert asked == [] and session_routing._RESERVED == {}


def test_with_every_session_free_the_connections_own_goes_first_and_a_start_on_its_way_keeps_its_session(tmp_path, monkeypatch):
    settings = connections(tmp_path)
    holds(monkeypatch, {})
    first = session_routing.choose('lab', cell=CELL, monitor=Monitor())
    assert (first.profile_id, first.label, first.connection) == ('lab', 'Virtuoso 1', 'lab')
    assert "every session is free, and it is the connection's own" in first.said
    other = session_routing.choose('lab', cell=('GATOR_TESTS', 'ring'), monitor=Monitor())    # a second press, another cell
    assert other.profile_id == 'lab2' and 'Virtuoso 1 (lab) is busy: a run started from this page' in other.said
    assert other.lock == str(second_lock(settings))
    with pytest.raises(session_routing.SessionsBusy, match='Every Virtuoso session of this connection is busy'):
        session_routing.choose('lab', cell=('GATOR_TESTS', 'vco'), monitor=Monitor())
    session_routing.finished(first)                                          # refused, or a check that ended
    assert session_routing.choose('lab', cell=('GATOR_TESTS', 'vco'), monitor=Monitor()).profile_id == 'lab'


def test_the_same_cell_is_not_given_twice_while_its_first_run_is_starting(tmp_path, monkeypatch):
    connections(tmp_path)
    holds(monkeypatch, {})
    started = session_routing.choose('lab', cell=CELL, monitor=Monitor())
    session_routing.started(started, os.getpid())             # a worker that is still starting
    with pytest.raises(session_routing.SessionsBusy, match='was given to a run started a moment ago'):
        session_routing.choose('lab', cell=CELL, monitor=Monitor())


def test_a_busy_first_session_sends_the_work_to_the_second_and_two_busy_ones_are_named(tmp_path, monkeypatch):
    settings = connections(tmp_path)
    holds(monkeypatch, {})
    running = holder_of(first_lock())
    try:
        chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor())
        assert chosen.profile_id == 'lab2' and 'Virtuoso 1 (lab) is busy' in chosen.said and 'process' in chosen.said
        session_routing.finished(chosen)
        other = holder_of(second_lock(settings))
        try:
            with pytest.raises(session_routing.SessionsBusy) as refused:
                session_routing.choose('lab', cell=CELL, monitor=Monitor())
            assert 'Virtuoso 1 (lab):' in str(refused.value) and 'Virtuoso 2 (lab2):' in str(refused.value)
            assert [s['state'] for s in refused.value.report['sessions']] == ['busy', 'busy']
        finally:
            other.kill()
            other.wait()
    finally:
        running.kill()
        running.wait()


def test_a_reservation_ends_when_its_worker_holds_the_lock(tmp_path, monkeypatch):
    connections(tmp_path)
    holds(monkeypatch, {})
    chosen = session_routing.choose('lab', monitor=Monitor())
    worker = holder_of(first_lock())                                  # the run's worker took the session's lock
    session_routing.started(chosen, worker.pid)
    try:
        assert session_routing.choose('lab', monitor=Monitor()).profile_id == 'lab2'
        assert str(first_lock()) not in session_routing._RESERVED      # the lock itself says busy now
    finally:
        worker.kill()
        worker.wait()
    session_routing._RESERVED.clear()
    assert session_routing.choose('lab', monitor=Monitor()).profile_id == 'lab'      # its run ended: free again


def test_a_reservation_ends_when_its_worker_ends_without_taking_the_lock(tmp_path, monkeypatch):
    """A short run - a one-design baseline - can end before anybody looks again: its session is free at once, not after
    the reservation's time limit."""
    connections(tmp_path)
    holds(monkeypatch, {})
    chosen = session_routing.choose('lab', monitor=Monitor())
    ended = subprocess.Popen([sys.executable, '-c', 'pass'])
    ended.wait()
    session_routing.started(chosen, ended.pid)
    assert session_routing.choose('lab', monitor=Monitor()).profile_id == 'lab'
    session_routing._RESERVED.clear()
    starting = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        chosen = session_routing.choose('lab', monitor=Monitor())
        session_routing.started(chosen, starting.pid)                 # still starting: the session stays promised
        assert session_routing.choose('lab', monitor=Monitor()).profile_id == 'lab2'
    finally:
        starting.kill()
        starting.wait()


def test_of_two_free_sessions_the_one_whose_last_test_passed(tmp_path, monkeypatch):
    connections(tmp_path)
    holds(monkeypatch, {})
    chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor(lab='failed', lab2='ok'))
    assert chosen.profile_id == 'lab2' and 'the last connection test of Virtuoso 1 (lab) did not pass' in chosen.said


def test_the_free_session_that_holds_the_cell_open_for_editing_takes_it(tmp_path, monkeypatch):
    connections(tmp_path)
    asked = holds(monkeypatch, {'lab2': EDITING})
    chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor(lab='ok'))
    assert chosen.profile_id == 'lab2' and 'it holds the cell open for editing' in chosen.said
    assert sorted(asked) == ['lab', 'lab2']
    assert [s.get('hold', {}).get('editing') for s in chosen.sessions] == [False, True]


def test_a_busy_session_that_holds_the_cell_lets_go_of_it_when_nothing_can_be_lost(tmp_path, monkeypatch):
    connections(tmp_path)
    released = []
    asked = holds(monkeypatch, {'lab': EDITING}, released)
    running = holder_of(first_lock())
    try:
        chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor())
    finally:
        running.kill()
        running.wait()
    assert chosen.profile_id == 'lab2' and asked == ['lab']
    assert 'Virtuoso 1 let go of the cell it held open for editing (saved, in no window)' in chosen.said
    # ... once the work's own refusals have passed (`release_pending`, before anything is written), not while choosing
    assert released == [] and chosen.release == ('lab', 'Virtuoso 1 (lab)', *CELL)
    session_routing.release_pending(chosen, Monitor())
    assert released == [('lab', *CELL)] and chosen.release is None
    session_routing.release_pending(chosen, Monitor())                  # once
    assert released == [('lab', *CELL)]


@pytest.mark.parametrize('hold, words', [(dict(EDITING, saved=False), 'with unsaved edits'),
                                         (dict(EDITING, windows=1), 'in a window, open for editing')])
def test_a_busy_session_keeps_a_cell_with_unsaved_edits_or_in_a_window_and_the_start_is_refused(tmp_path, monkeypatch, hold, words):
    connections(tmp_path)
    released = []
    holds(monkeypatch, {'lab': hold}, released)
    running = holder_of(first_lock())
    try:
        with pytest.raises(session_routing.SessionsBusy, match=words):
            session_routing.choose('lab', cell=CELL, monitor=Monitor())
    finally:
        running.kill()
        running.wait()
    assert released == [] and session_routing._RESERVED == {}


def test_letting_go_that_fails_refuses_the_start_in_words(tmp_path, monkeypatch):
    connections(tmp_path)
    holds(monkeypatch, {'lab': EDITING}, RuntimeError('the cell is shown in a window of this Virtuoso'))
    running = holder_of(first_lock())
    try:
        chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor())
    finally:
        running.kill()
        running.wait()
    with pytest.raises(session_routing.SessionsBusy, match='letting go of the cell there failed: the cell is shown'):
        session_routing.release_pending(chosen, Monitor())


def test_a_queue_between_two_runs_keeps_its_session(tmp_path, monkeypatch):
    """A queue holds its session's queue lock for its whole life: in the moment between two of its runs the session lock is
    free, and work from the page sent there would make the queue's next run fail (the review of record 7.351)."""
    settings = connections(tmp_path)
    holds(monkeypatch, {})
    queue = holder_of(paths.bridge_queue_lock(settings, 's2'))
    try:
        chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor(lab='failed', lab2='ok'))
        assert chosen.profile_id == 'lab'                               # not the free-looking session 2
        assert 'Virtuoso 2 (lab2) is busy: a queue works in this session' in chosen.said
        session_routing.finished(chosen)
        first = holder_of(first_lock())
        try:
            with pytest.raises(session_routing.SessionsBusy, match='a queue works in this session'):
                session_routing.choose('lab', cell=CELL, monitor=Monitor())
        finally:
            first.kill()
            first.wait()
    finally:
        queue.kill()
        queue.wait()
    assert paths.bridge_queue_lock(settings, 's2') == second_lock(settings).with_name('queue.lock')


def test_a_choice_lets_go_of_its_own_reservation_only(tmp_path, monkeypatch):
    connections(tmp_path)
    holds(monkeypatch, {})
    old = session_routing.choose('lab', monitor=Monitor())
    session_routing._RESERVED.clear()                                   # its time limit passed
    new = session_routing.choose('lab', monitor=Monitor())
    assert new.lock == old.lock and new.token != old.token
    session_routing.finished(old)                                       # the old work ends late
    session_routing.started(old, os.getpid())
    assert session_routing._RESERVED[new.lock]['token'] == new.token and not session_routing._RESERVED[new.lock]['attached']
    session_routing.finished(new)
    assert session_routing._RESERVED == {}


def test_a_session_whose_last_test_failed_is_not_asked(tmp_path, monkeypatch):
    connections(tmp_path)
    asked = holds(monkeypatch, {'lab2': EDITING})
    chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor(lab2='failed'))
    assert asked == ['lab'] and chosen.profile_id == 'lab'
    assert chosen.sessions[1]['look_error'] == 'not asked: its last connection test failed'


def test_a_cell_in_use_is_refused_before_virtuoso_is_asked(tmp_path, monkeypatch):
    connections(tmp_path)
    asked = holds(monkeypatch, {})
    working = holder_of(paths.bridge_cell_lock(*CELL))
    try:
        with pytest.raises(session_routing.SessionsBusy, match='The cell GATOR_TESTS/ota is in use'):
            session_routing.choose('lab', cell=CELL, monitor=Monitor())
    finally:
        working.kill()
        working.wait()
    assert asked == []


def test_a_session_that_cannot_be_asked_is_said_and_the_choice_goes_on(tmp_path, monkeypatch):
    connections(tmp_path)
    holds(monkeypatch, {'lab2': TimeoutError('Virtuoso did not answer within 20 s')})
    chosen = session_routing.choose('lab', cell=CELL, monitor=Monitor())
    assert chosen.profile_id == 'lab'
    assert chosen.sessions[1]['look_error'] == 'TimeoutError: Virtuoso did not answer within 20 s'


def test_route_gives_a_task_from_a_cell_its_cell_and_a_copy_of_the_configuration(tmp_path, monkeypatch):
    make(tmp_path)
    connections(tmp_path)
    entry = profiles.profile_entry('ring_cdf')
    asked = []
    monkeypatch.setattr(session_routing.cell_hold, 'look', lambda pid, library, cell, **_: asked.append((pid, library, cell))
                        or dict(open=False, editing=False, saved=True, windows=0))
    config = schema.WorkbenchConfig.model_validate(dict(tasks.starter_config('real:ring_cdf'),
                                                        run=dict(max_evaluations=3, connection_profile_id='lab')))
    assert session_routing.task_cell(config) == ((entry['library'], entry['core_cell']), False)
    running = holder_of(first_lock())
    try:
        routed, choice = session_routing.route(config, Monitor())
    finally:
        running.kill()
        running.wait()
    assert routed.run.connection_profile_id == 'lab2' and config.run.connection_profile_id == 'lab'
    assert routed is not config and choice.profile_id == 'lab2'
    # only the busy session is asked: the one free session is chosen whatever it holds
    assert asked == [('lab', entry['library'], entry['core_cell'])]
    assert session_routing.grouped('lab') and not session_routing.grouped('lab2') and not session_routing.grouped(None)
    built_in = SimpleNamespace(circuit=SimpleNamespace(source='registered_task', task_id='real:gpdk045_ota5'))
    assert session_routing.task_cell(built_in) == (None, True)
    mock = SimpleNamespace(circuit=SimpleNamespace(source='registered_task', task_id='synthetic:anything'))
    assert session_routing.task_cell(mock) == (None, False)


def test_a_continued_run_may_change_session_within_its_connection_and_never_its_connection(tmp_path):
    from gator_workbench.runs import resumed_session
    connections(tmp_path, other=dict(profile=None))
    assert resumed_session('lab2', 'lab') == 'lab2' and resumed_session('lab', 'lab2') == 'lab'
    assert resumed_session('other', 'lab') == 'lab' and resumed_session('lab2', 'other') == 'other'
    assert resumed_session('lab', 'lab') == 'lab' and resumed_session('lab', None) is None


def test_start_records_the_chosen_session_and_lets_it_go_when_the_start_is_refused(tmp_path, monkeypatch):
    """The wiring of `start_run`: the routed configuration is what is prepared, the run's record and the page's answer
    say which session and why, the session stays reserved for the starting worker - and is let go of on a refusal."""
    from fastapi import HTTPException
    from gator_workbench import runs
    from gator_workbench.api import run_routes
    from gator_workbench.layout import RunLayout
    from gator_workbench.storage.atomic import read_json, write_json
    choice = session_routing.Choice(profile_id='lab2', connection='lab', label='Virtuoso 2', lock='L',
                                    said='Virtuoso session: Virtuoso 2 (lab2) - it is free; Virtuoso 1 (lab) is busy: a run.')
    calls, prepared = [], []

    def route(config, monitor, **_):
        """Route the fixture configuration to the second connection profile."""
        routed = config.model_copy(deep=True)
        routed.run.connection_profile_id = 'lab2'
        return routed, choice
    monkeypatch.setattr(session_routing, 'route', route)
    monkeypatch.setattr(session_routing, 'started', lambda c, pid: calls.append(('started', c, pid)))
    monkeypatch.setattr(session_routing, 'finished', lambda c: calls.append(('finished', c)))
    monkeypatch.setattr(session_routing, 'release_pending', lambda c, monitor: calls.append(('release', c)))
    layout = RunLayout(tmp_path / 'run')
    layout.manifest.parent.mkdir(parents=True, exist_ok=True)

    def prepare(config, roots, before_write=None, **_):
        """Record the routed profile and perform the fixture's pre-write release before creating its manifest."""
        prepared.append(config.run.connection_profile_id)
        before_write()                       # every refusal of prepare_run has passed: the busy holder lets go now
        manifest = dict(run_id='r1', mock=False, mock_notice='', notes=['made'], segments=[dict(segment=1, entry='start')])
        write_json(layout.manifest, manifest)
        return layout, manifest
    monkeypatch.setattr(runs, 'prepare_run', prepare)
    monkeypatch.setattr(runs, 'launch_worker', lambda layout, allow_real: 4321)
    config = make_config(tmp_path, run=dict(connection_profile_id='lab'))
    body = SimpleNamespace(authorize_real_simulation=True, acknowledge_unknown_connection=False)
    context = SimpleNamespace(roots=None, monitor=None)
    answer = run_routes.start_run(context, config, body)
    assert prepared == ['lab2'] and answer['connection_profile_id'] == 'lab2' and answer['worker_pid'] == 4321
    assert answer['virtuoso_session']['said'] == choice.said
    assert calls == [('release', choice), ('started', choice, 4321)]
    manifest = read_json(layout.manifest)
    assert manifest['segments'][-1]['virtuoso_session']['session'] == 'lab2' and manifest['notes'] == ['made', choice.said]
    calls.clear()

    # A session chosen already (Save task hands its own to the baseline it starts): no second choice.
    monkeypatch.setattr(session_routing, 'route', lambda *a, **k: pytest.fail('chose again'))
    prepared.clear()
    answer = run_routes.start_run(context, config, body, session=choice)
    assert prepared == ['lab2'] and calls == [('release', choice), ('started', choice, 4321)]
    monkeypatch.setattr(session_routing, 'route', route)
    calls.clear()

    # A manifest write that fails after prepare_run: the session and a continue's run lock go back (they were kept).
    released_locks = []
    monkeypatch.setattr(runs, 'take_lock', lambda run_dir: SimpleNamespace(release=lambda: released_locks.append(run_dir)))
    monkeypatch.setattr(run_routes, 'write_json', lambda *a, **k: (_ for _ in ()).throw(OSError('Input/output error')))
    with pytest.raises(OSError):
        run_routes.start_run(context, config, body)
    assert calls == [('release', choice), ('finished', choice)] and released_locks == [layout.run_dir]
    monkeypatch.setattr(run_routes, 'write_json', write_json)
    calls.clear()

    def busy_holder(config, roots, before_write=None, **_):
        """Refuse preparation because a busy session cannot release its edited cell."""
        raise session_routing.SessionsBusy('Virtuoso 1 (lab) holds L/c open for editing and is busy; letting go failed')
    monkeypatch.setattr(runs, 'prepare_run', busy_holder)                 # the hook's refusal comes out of prepare_run
    with pytest.raises(HTTPException) as caught:
        run_routes.start_run(context, config, body)
    assert caught.value.status_code == 409 and calls == [('finished', choice)]
    calls.clear()

    def refused(config, roots, **_):
        """Simulate a connection-gate refusal before run preparation."""
        raise runs.RunRejected('The connection gate blocked this action.', code='connection_gate_blocked')
    monkeypatch.setattr(runs, 'prepare_run', refused)
    with pytest.raises(HTTPException) as caught:
        run_routes.start_run(context, config, body)
    assert caught.value.status_code == 409 and calls == [('finished', choice)]
    calls.clear()
    monkeypatch.setattr(session_routing, 'route', lambda config, monitor, **_: (_ for _ in ()).throw(
        session_routing.SessionsBusy('Every Virtuoso session of this connection is busy: ...', report=dict(sessions=[]))))
    with pytest.raises(HTTPException) as caught:
        run_routes.start_run(context, config, body)
    assert caught.value.status_code == 409 and calls == []


def test_the_look_and_letting_go_read_virtuosos_answer(monkeypatch):
    assert cell_hold.parse_rows('') == dict(open=False, editing=False, saved=True, windows=0)
    assert cell_hold.parse_rows('r|saved|0\na|modified|2\n') == dict(open=True, editing=True, saved=False, windows=2)
    skill = cell_hold.LOOK % dict(matching=cell_hold._matching('L"x', 'c'))
    assert 'cv~>libName == "L\\"x"' in skill and 'dbGetOpenCellViews()' in skill and 'dbReopen' not in skill   # read-only
    release = cell_hold.RELEASE % dict(matching=cell_hold._matching('L', 'c'))
    assert release.index('dbIsCellViewModified') < release.index('hiGetWindowList') < release.index('dbReopen(cv "r")')
    assert 'error(' not in cell_hold.let_go_skill('L', 'c') and 'dbReopen(cv "r")' in cell_hold.let_go_skill('L', 'c')
    calls = []
    monkeypatch.setattr(cell_hold, 'require_gate', lambda monitor, action, pid, what, **kw: calls.append((action, pid, kw)))
    monkeypatch.setattr(cell_hold, 'run_child', lambda argv, timeout: (
        '{"op": "look", "hold": {"open": true, "editing": true, "saved": true, "windows": 0}}\n', '', 0) if 'look' in argv
        else ('{"op": "release", "released": true}\n', '', 0))
    assert cell_hold.look('lab', 'L', 'c')['editing'] is True
    assert calls == []                                       # a read: no gate's probe before every Start
    assert cell_hold.release(None, 'lab', 'L', 'c') is True
    assert calls == [('write_cellview', 'lab', dict(acknowledge_unknown=True))]      # a write: gated
    monkeypatch.setattr(cell_hold, 'run_child', lambda argv, timeout: ('', 'RuntimeError: the cell has unsaved edits in this Virtuoso\n', 1))
    with pytest.raises(RuntimeError, match='unsaved edits'):
        cell_hold.release(None, 'lab', 'L', 'c')
    monkeypatch.setattr(cell_hold, 'run_child', lambda argv, timeout: None)
    with pytest.raises(TimeoutError):
        cell_hold.look('lab', 'L', 'c')


def test_a_run_lets_go_of_its_cell_after_restoring_it_and_before_its_locks(tmp_path, monkeypatch):
    """The form writer opened the cell for editing and Virtuoso kept it so; when the run ends the cell, back at its recorded
    sizes, is reopened read-only - under both locks, before the client closes - so the other session can write it."""
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    root = backend.config.state_root
    cell = paths.bridge_cell_lock(backend.config.library, profile.design['core_cell'], root)
    let_go = cell_hold.let_go_skill(backend.config.library, profile.design['core_cell'])
    seen = []
    original = client.execute_skill

    def execute(skill, timeout=60):
        """Record lock ownership and dirty state when the fake backend releases its cell."""
        if skill == let_go:
            seen.append((RunLock.held(cell), RunLock.held(root / 'session.lock'), backend._dirty))
        return original(skill, timeout)
    client.execute_skill = execute
    backend.connect()
    backend._dirty = True                     # a candidate was written: close restores the cell first
    restored = []
    monkeypatch.setattr(type(backend).__mro__[2], 'restore', lambda self: (restored.append(True), setattr(self, '_dirty', False)))
    backend.close()
    assert restored == [True] and seen == [(True, True, False)] and client.skill[-1] == let_go
    assert not RunLock.held(cell) and backend.client is None
    before = len(client.skill)
    backend.connect()                         # a connection that only reads - a check - leaves Virtuoso as it found it
    backend.close()
    assert len(seen) == 1 and let_go not in client.skill[before:]
    backend.connect()                         # one that wrote and restored on its own: let go before the client closes
    backend._dirty = True
    backend._dirty = False
    backend.close()
    assert len(seen) == 2 and client.skill[-1] == let_go and restored == [True]


def test_letting_go_never_stops_a_run_from_closing(tmp_path, monkeypatch):
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    original = client.execute_skill

    def execute(skill, timeout=60):
        """Inject a timeout only when the backend attempts to release its cell."""
        if 'dbReopen' in skill:
            raise TimeoutError('Virtuoso did not answer')
        return original(skill, timeout)
    client.execute_skill = execute
    backend.connect()
    backend._dirty = True                     # it wrote, and restored
    backend._dirty = False
    backend.close()
    assert backend.edit_lock_released is None and backend.client is None
    assert not RunLock.held(backend.config.state_root / 'session.lock')
    # a restore that fails is the run's own error, as before: nothing is let go of after it
    backend.connect()
    backend._dirty = True
    monkeypatch.setattr(type(backend).__mro__[2], 'restore', lambda self: (_ for _ in ()).throw(RuntimeError('restore failed')))
    with pytest.raises(RuntimeError, match='restore failed'):
        backend.close()
    assert backend.client is None and not RunLock.held(backend.config.state_root / 'session.lock')


def test_save_task_hands_its_session_to_its_baseline_or_lets_it_go(monkeypatch):
    """The first save of a task starts its baseline: the session the save chose goes on to it, instead of a second choice
    asking both Virtuosos again a moment later (the review of record 7.351)."""
    from gator_workbench.api import task_baseline
    choice = session_routing.Choice(profile_id='lab2', connection='lab', label='Virtuoso 2', said='.', lock='L', token='t')
    calls, handed = [], []
    monkeypatch.setattr(session_routing, 'finished', lambda c: calls.append(('finished', c)))
    task_baseline.after_save(None, dict(created=False, baseline_kept=True, task_key='real:x'), session=choice)
    assert calls == [('finished', choice)]                       # no baseline to start: the session goes back
    calls.clear()
    monkeypatch.setattr(task_baseline, '_start', lambda context, task_key, **kw: handed.append(kw['session']) or dict(state='started'))
    made = dict(created=True, task_key='real:x')
    task_baseline.after_save(None, made, profile_id='lab', session=choice)
    assert handed == [choice] and calls == [] and made['baseline'] == dict(state='started')


def test_save_task_refusals_that_need_no_virtuoso_can_be_asked_first(tmp_path):
    from gator_workbench import task_save
    make(tmp_path)
    with pytest.raises(profiles.ProfileError, match='already exists'):
        task_save.check_saveable('ring_cdf', make_config(tmp_path))
