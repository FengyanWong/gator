"""Two Virtuoso sessions carry a run each (record 7.311; user, 2026-10-11, of a second Virtuoso opened beside the first:
"do you think second virtuoso can be used for sizing? to accelerate", then "build that once B has landed").

Until now one lock stood for "Virtuoso": a second real run, check or Save task was refused whatever session it would
have used. Now every Virtuoso session has its own lock - one process at a time drives a session - and every cell has
one - one process at a time works on a cell, whatever the session, because each session keeps its own copy of an open
cell in memory and the second to save would write over the first. The optimizer package is not touched: its adapter
takes the lock of the state folder it is given, and the workbench's adapter class takes the cell's lock around it."""
from dataclasses import replace
import fcntl
import json
from pathlib import Path
import subprocess
import sys

import pytest

from gator_workbench import cdf_write, consistency, corner_check, paths, profiles, tasks
from gator_workbench.run_lock import RunLock
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from cdf_write_support import make, stage_rows
from fakes_virtuoso import backend_of

SETTINGS = ('VB_REMOTE_HOST=simhost\nVB_REMOTE_PORT=65001\nVB_LOCAL_PORT=65221\n'
            '# a second Virtuoso session, opened beside the first\n'
            'VB_REMOTE_HOST_s2=simhost\nVB_REMOTE_PORT_s2="65017"\nVB_LOCAL_PORT_s2=65222\n'
            'VB_REMOTE_HOST_other=simhost\nVB_REMOTE_PORT_other=65017 # the same daemon as s2\n'
            'VB_REMOTE_HOST_twin=simhost\nVB_REMOTE_PORT_twin=65001\n'
            'VB_REMOTE_HOST_half=simhost\n')


def connections(tmp_path) -> Path:
    """Four connections on one settings file: the first session, the second, another name for the second, another name
    for the first."""
    settings = tmp_path / '.env'
    settings.write_text(SETTINGS)
    one = lambda profile: dict(env_file=str(settings), profile=profile, library='GATOR_TESTS', model_file='/pdk/model.scs')
    target = paths.local_settings_dir() / 'bridge_connection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(active='lab', profiles=dict(lab=one(None), second=one('s2'), again=one('other'), twin=one('twin')))))
    return settings


def holder_of(lock):
    """Another process that holds `lock` until it is killed."""
    Path(lock).parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen([sys.executable, '-c', 'import fcntl, sys, time\nf = open(sys.argv[1], "a+")\n'
                                'fcntl.flock(f, fcntl.LOCK_EX)\nprint("held", flush=True)\ntime.sleep(60)', str(lock)],
                               stdout=subprocess.PIPE, text=True)
    assert process.stdout.readline() == 'held\n'
    return process


def test_a_session_is_told_by_where_its_daemon_listens_and_what_cannot_be_told_apart_is_the_first(tmp_path):
    settings, root = connections(tmp_path), paths.bridge_state_dir()
    key = lambda profile: paths.bridge_session_key(settings, profile)
    assert key(None) is None and key('') is None                  # no bridge profile: the first session
    assert key('s2') == key('other') == 'other'                   # two names, one host and port: one session, one name
    assert key('twin') is None                                    # the first session's own host and port
    assert key('half') is None and key('nobody') is None          # no port, no keys at all: not told apart
    assert paths.bridge_session_key(tmp_path / 'missing.env', 's2') is None
    assert paths.bridge_session_dir() == paths.bridge_session_dir(settings, None) == paths.bridge_session_dir(settings, 'twin') == root
    assert paths.bridge_session_dir(settings, 's2') == root / 'sessions' / 'other'
    assert paths.bridge_session_lock() == root / 'session.lock'    # the first session's lock is the file it always was
    assert paths.bridge_session_lock(settings, 's2') == root / 'sessions' / 'other' / 'session.lock'
    assert paths.bridge_state_root_of(root / 'sessions' / 'other') == root == paths.bridge_state_root_of(root)
    assert paths.bridge_cell_lock('LIB', 'cell') == root / 'cells' / 'LIB' / 'cell.lock'
    assert paths.bridge_cell_lock('../x', 'a/b').parent.parent == root / 'cells'      # a name is never a path
    without_first = tmp_path / 'named-only.env'
    without_first.write_text('VB_REMOTE_HOST_s2=simhost\nVB_REMOTE_PORT_s2=65017\n')
    assert paths.bridge_session_key(without_first, 's2') is None   # no first session to tell it from


def test_a_task_gets_the_state_folder_of_the_session_its_connection_reaches(tmp_path):
    make(tmp_path)
    connections(tmp_path)
    root = paths.bridge_state_dir().resolve()
    first, profile, entry = tasks.generated_bridge_config('ring_cdf', 'lab')
    assert first.state_root == root and first.profile is None and isinstance(profile, cdf_write.CdfWritableProfile)
    second, _, _ = tasks.generated_bridge_config('ring_cdf', 'second')
    assert second.state_root == root / 'sessions' / 'other' and second.profile == 's2'
    assert tasks.generated_bridge_config('ring_cdf', 'again')[0].state_root == second.state_root      # one session, one lock
    assert tasks.generated_bridge_config('ring_cdf', 'twin')[0].state_root == root
    assert second.env_file.parent == root / 'env-snapshots'        # the settings copy (record 7.306) stays in the root
    # what the busy checks look at for this task: the lock of its session and the lock of its cell
    assert consistency.task_locks('second', entry) == (root / 'sessions' / 'other' / 'session.lock',
                                                       root / 'cells' / entry['library'] / f'{entry["core_cell"]}.lock')
    assert consistency.task_locks('lab', entry)[0] == consistency.task_locks('unknown connection', entry)[0] == root / 'session.lock'


def test_a_built_in_task_stays_in_the_first_session_and_a_width_only_task_locks_its_cell_like_any_other(tmp_path, monkeypatch):
    """The built-in tasks of the optimizer package run with its own adapter and factory, which take no lock of their cell:
    beside a run in another session they could write the same cell, so they are refused there. A task saved from a cell
    that varies only single-finger widths keeps the verified width writer - and holds its cell's lock like a form-written
    one, in whichever session (2026-10-11: the logic cell of the transfer experiment is such a task)."""
    settings = connections(tmp_path)
    receipt = tmp_path / 'creation.json'
    receipt.write_text('{}')
    bound = lambda profile: dict(env_file=str(settings), library='LIB', creation_receipt=str(receipt), model_file='/pdk/model.scs', profile=profile)
    assert tasks.bridge_config_of(bound(None)).state_root == tasks.bridge_config_of(bound('twin')).state_root == paths.bridge_state_dir().resolve()
    with pytest.raises(tasks.TaskBlocked, match='runs in the first Virtuoso session only'):
        tasks.bridge_config_of(bound('s2'))
    made = make(tmp_path, rows=stage_rows('w', 'wn', 0.6, 1.6))
    assert made['writer'] == 'widths'
    config, profile, _ = tasks.generated_bridge_config('ring_cdf', 'second')
    assert not isinstance(profile, cdf_write.CdfWritableProfile) and config.state_root == paths.bridge_state_dir().resolve() / 'sessions' / 'other'
    backend, _ = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    assert isinstance(backend, cdf_write.CellLocked) and type(backend) is cdf_write.backend_class(profile)
    cell = paths.bridge_cell_lock(backend.config.library, profile.design['core_cell'], backend.config.state_root)
    backend.connect()
    assert RunLock.held(cell) and RunLock.held(backend.config.state_root / 'session.lock')
    backend.close()
    assert not RunLock.held(cell)
    other = cdf_write.cell_lock(backend.config.library, profile.design['core_cell'], backend.config.state_root)
    with pytest.raises(cdf_write.CellBusy):
        backend.connect()
    other.close()
    # the run's own preparation makes the same adapter, and its factory is the verified one with that preparation
    assert type(cdf_write.CdfPreparationFactory(backend.config, profile)()) is type(backend)
    import analog_optimizer.training.parallel as verified
    assert issubclass(cdf_write.factory_class(profile), verified.NativeEnvironmentFactory)


def test_the_adapter_holds_its_cells_lock_from_connect_to_close_and_a_busy_cell_is_refused_in_words(tmp_path, monkeypatch):
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, _ = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    root = backend.config.state_root
    cell = paths.bridge_cell_lock(backend.config.library, profile.design['core_cell'], root)
    assert not cell.exists()
    backend.connect()
    assert RunLock.held(cell) and RunLock.held(root / 'session.lock')
    backend.connect()                                              # connected already: nothing is taken twice
    with pytest.raises(cdf_write.CellBusy, match=f'The cell {backend.config.library}/{profile.design["core_cell"]} is in use'):
        cdf_write.cell_lock(backend.config.library, profile.design['core_cell'], root)
    backend.close()
    assert not RunLock.held(cell) and not RunLock.held(root / 'session.lock')
    # somebody else works on the cell - through another session, whose lock is another file
    other = cdf_write.cell_lock(backend.config.library, profile.design['core_cell'], root)
    with pytest.raises(cdf_write.CellBusy, match='through this Virtuoso session or another one'):
        backend.connect()
    assert backend.client is None and not RunLock.held(root / 'session.lock')          # nothing of the session was taken
    other.close()
    backend.connect()                                              # and nothing was left behind: the cell is free again
    assert RunLock.held(cell)
    backend.close()


def test_each_session_has_its_own_lock_so_a_run_in_the_first_does_not_stop_one_in_the_second(tmp_path, monkeypatch):
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, _ = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    root = backend.config.state_root
    second = type(backend)(replace(backend.config, state_root=root / 'sessions' / 'other'), profile)
    running = holder_of(root / 'session.lock')                     # a run of another cell in the first session
    try:
        with pytest.raises(BlockingIOError):
            backend.connect()                                      # the first session is taken, as it always was
        assert backend._cell_lock is None                          # ... and the cell was let go again
        second.connect()                                           # the second session is free
        assert RunLock.held(root / 'sessions' / 'other' / 'session.lock')
        assert RunLock.held(paths.bridge_cell_lock(second.config.library, profile.design['core_cell'], root))       # the root's cells/
        assert (root / 'sessions' / 'other' / second.session_id / 'initial.json').is_file()                    # its journal beside its lock
        second.close()
    finally:
        running.kill()
        running.wait()
    assert sorted(p.relative_to(root).as_posix() for p in paths.bridge_locks(root)) == [
        f'cells/{second.config.library}/{profile.design["core_cell"]}.lock', 'session.lock', 'sessions/other/session.lock']


def test_check_now_says_which_lock_is_held_the_tasks_session_or_its_cell(tmp_path):
    make(tmp_path)
    connections(tmp_path)
    entry = profiles.profile_entry('ring_cdf')
    session, cell = consistency.task_locks('second', entry)
    first = holder_of(paths.bridge_session_lock())                 # a run in the FIRST session
    try:
        assert not any(consistency.lock_holder(lock) for lock in (session, cell))       # leaves the second session's task free
        assert corner_check.bridge_busy('lab', 'real:ring_cdf') and not corner_check.bridge_busy('second', 'real:ring_cdf')
        assert corner_check.bridge_busy()                          # asked without a run: the first session's lock, as before
    finally:
        first.kill()
        first.wait()
    working = holder_of(cell)                                      # a run on this cell, through whichever session
    try:
        assert corner_check.bridge_busy('second', 'real:ring_cdf') and corner_check.bridge_busy('lab', 'real:ring_cdf')
        step = consistency._busy_step(locks=(session, cell))
        assert step['step'] == 'busy' and not step['ok'] and step['fix'] == consistency.FIX_BUSY
        assert f'The cell\'s lock ({cell}) is held by a process (process {working.pid}' in step['detail']
        assert 'through another Virtuoso session' in step['detail']
    finally:
        working.kill()
        working.wait()
    taken = holder_of(session)                                     # a run in the task's own session
    try:
        step = consistency._busy_step(locks=(session, cell))
        assert f'session lock ({session}) is held by a process (process {taken.pid}' in step['detail']
    finally:
        taken.kill()
        taken.wait()
    # the adapter's own refusal, when the cell was taken between the look and the connect
    late = consistency._busy_step('CellBusy: The cell LIB/cell is in use by another run, check or task save', (session, cell))
    assert 'The cell\'s lock' in late['detail'] and 'another process (CellBusy' in late['detail']
    assert 'session lock' in consistency._busy_step('BlockingIOError: [Errno 11]', (session, cell))['detail']


def test_a_write_from_the_page_takes_its_connections_session_and_its_cells(tmp_path, monkeypatch):
    """Save task's write process (bridge_setup): refused while its session or one of its cells is in use, and a run in
    the other session does not stop it."""
    from gator_workbench import bridge_setup
    connections(tmp_path)
    seen = []

    class Stop(Exception):
        """A sentinel that ends the fake bridge call after session selection is observed."""
        pass

    def bridge(settings):
        """Record the selected connection profile and stop before any bridge action."""
        seen.append(settings.get('profile'))
        raise Stop
    monkeypatch.setattr(bridge_setup, 'RealBridge', bridge)
    argv = lambda profile_id: ['--profile-id', profile_id, '--op', 'read_setup', '--library', 'LIB', '--cell', 'cell', '--testbench', 'tb_cell',
                               '--copy-library', 'COPY', '--rename', '{"cell": "cell_b"}', '--output', str(tmp_path)]
    first = holder_of(paths.bridge_session_lock())
    try:
        with pytest.raises(SystemExit, match='using Virtuoso right now'):
            bridge_setup._main(argv('lab'))
        with pytest.raises(Stop):                                  # the second session is free: the write goes on to the bridge
            bridge_setup._main(argv('second'))
    finally:
        first.kill()
        first.wait()
    assert seen == ['s2']
    for name in ('cell', 'cell_b', 'tb_cell'):                     # the cell, the name of its copy and the bench
        working = holder_of(paths.bridge_cell_lock('COPY', name))
        try:
            with pytest.raises(SystemExit, match=f'working on COPY/{name} through another Virtuoso session'):
                bridge_setup._main(argv('second'))
        finally:
            working.kill()
            working.wait()
    assert seen == ['s2']
    assert not any(RunLock.held(lock) for lock in paths.bridge_locks())               # every lock was let go
