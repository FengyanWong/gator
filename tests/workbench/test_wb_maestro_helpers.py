"""Record 7.315: the Maestro helper process that stays behind. A Maestro session opened in the background starts a
headless `virtuoso -beanhost ... -beanLogFile <logs>/amps_Service<N>.log ... -mpssession virtuoso<pid>`; closing the session
should end it, and some are never told and hold their memory for good. `bridge_setup._session_close` follows every close
with a look at those helpers. The host-side check is run here for real, by a stand-in Virtuoso on stand-in processes."""
import re
import subprocess
import sys
import time
import types

import pytest

from gator_workbench import bridge_setup

# One group, one worker: a look also finds the helpers of a Virtuoso that no longer runs - another test's stand-ins,
# were two of these tests to run at the same time.
pytestmark = [pytest.mark.skipif(not sys.platform.startswith('linux'), reason='the check reads /proc, as on the simulator host'),
              pytest.mark.xdist_group('maestro_helpers')]


def named(tmp_path, folder, name, text):
    program = tmp_path / folder / name
    program.parent.mkdir()
    program.write_text(text)
    program.chmod(0o755)
    return program


def running_as(process, name):
    for _ in range(150):                                                 # until the program itself runs under its name
        if open(f'/proc/{process.pid}/comm').read().strip() == name:
            return process
        time.sleep(0.02)
    raise AssertionError(f'{name} did not start')


class Virtuoso:
    """A stand-in Virtuoso: a process named virtuoso that runs the clean-up's ``sh(...)`` as its own child, and answers
    like the bridge - a SKILL string with the line ends written out. `in_use` = a Maestro session or an ADE window open."""
    def __init__(self, tmp_path, tag='v'):
        self.calls, self.in_use, self.folder = [], False, tmp_path
        program = named(tmp_path, f'virtuoso-{tag}', 'virtuoso', '#!/bin/sh\nwhile read -r file; do sh "$file"; echo done; done\n')
        self.process = running_as(subprocess.Popen([str(program)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True), 'virtuoso')
        self.pid = self.process.pid

    def execute_skill(self, text, timeout=60):
        self.calls.append(text)
        if 'maeCloseSession' in text:
            return types.SimpleNamespace(ok=True, errors=[], output='t')
        assert 'if(or(maeGetSessions() null(windows) car(windows)) then all = "maestro in use" else ' in text
        assert 'rexMatchp("ADE Assembler" n)' in text and 'rexMatchp("ADE Explorer" n)' in text and 'deleteFile(out)' in text
        assert 'car(errset(axlGetWindowSession(w)))' in text and 'car(errset(w~>davSession))' in text
        if self.in_use:
            return types.SimpleNamespace(ok=True, errors=[], output='"maestro in use"')
        [literal] = re.findall(r'sh\(strcat\("((?:[^"\\]|\\.)*)" out " 2>/dev/null"\)\)', text)
        command = re.sub(r'\\(.)', r'\1', literal)                       # what SKILL makes of the literal
        assert command.endswith(' > ')
        job, out = self.folder / f'job{len(self.calls)}.sh', self.folder / f'job{len(self.calls)}.out'
        job.write_text(command + str(out) + ' 2>/dev/null\n')
        self.process.stdin.write(f'{job}\n')
        self.process.stdin.flush()
        assert self.process.stdout.readline().strip() == 'done'
        return types.SimpleNamespace(ok=True, errors=[], output='"' + out.read_text().replace('\n', '\\n') + '"')

    def end(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)


@pytest.fixture
def host(tmp_path):
    started = []

    def virtuoso(tag='v'):
        started.append(Virtuoso(tmp_path, tag))
        return started[-1]

    def helper(number, of, *, name='virtuoso', first='-beanhost', option='-beanLogFile', log='amps_Service{}.log'):
        """A stand-in for one helper of the Virtuoso with the process id `of`, started the way Maestro starts it."""
        program = named(tmp_path, f'helper{number}', name, '#!/bin/sh\nread line\n')       # waits on its input: no child, no CPU
        process = subprocess.Popen([str(program), first, 'HOST', '-beanport', '11363', '-beanbinlog', '', option,
                                    str(tmp_path / log.format(number)), '-mpssession', f'virtuoso{of}', '-mpshost', 'HOST',
                                    '-davinciService', 'DaVinciService_12'], stdin=subprocess.PIPE)
        started.append(types.SimpleNamespace(end=lambda: (process.poll() is None and process.kill(), process.wait(timeout=5))))
        return running_as(process, name[:15])

    yield types.SimpleNamespace(virtuoso=virtuoso, helper=helper)
    for one in started:
        one.end()


def alive(process):
    return process.poll() is None


def test_a_helper_no_session_needs_is_removed_and_nothing_else(host):
    virtuoso, second = host.virtuoso(), host.virtuoso('second')
    gone = host.virtuoso('gone')
    gone.end()                                                           # a Virtuoso that no longer runs
    left_behind = host.helper(495, virtuoso.pid)
    of_a_dead_virtuoso = host.helper(43, gone.pid)
    of_the_second_virtuoso = host.helper(121, second.pid)                # that session's own business
    other_program = host.helper(13, virtuoso.pid, name='simulator')      # not Virtuoso
    not_a_helper = host.helper(15, virtuoso.pid, first='-nograph')       # Virtuoso, but not started as a helper
    other_log = host.helper(17, virtuoso.pid, log='amps_Logging{}.log')  # another kind of service
    untouched = (of_the_second_virtuoso, other_program, not_a_helper, other_log)

    found = bridge_setup._helper_sweep(virtuoso)                         # a look removes nothing
    assert {(h['state'], h['pid'], h['log']) for h in found} == {('found', left_behind.pid, 'Service495.log'), ('found', of_a_dead_virtuoso.pid, 'Service43.log')}
    assert all(h['kb'] > 0 and h['age'] >= 0 for h in found) and alive(left_behind) and alive(of_a_dead_virtuoso)

    removed = bridge_setup._helper_sweep(virtuoso, remove=[left_behind.pid, *(p.pid for p in untouched), virtuoso.pid, second.pid])
    assert [(h['state'], h['pid']) for h in removed if h['state'] == 'removed'] == [('removed', left_behind.pid)]
    assert left_behind.wait(timeout=5) == -9                             # only what is a helper is removed, even when named
    assert all(alive(p) for p in untouched) and alive(of_a_dead_virtuoso) and alive(virtuoso.process) and alive(second.process)

    virtuoso.in_use = True                                               # a Maestro session or an ADE window is open
    assert bridge_setup._helper_sweep(virtuoso, remove=[of_a_dead_virtuoso.pid]) == [] and alive(of_a_dead_virtuoso)
    virtuoso.in_use = False
    [last] = bridge_setup._helper_sweep(virtuoso, remove=[of_a_dead_virtuoso.pid])
    assert last['state'] == 'removed' and of_a_dead_virtuoso.wait(timeout=5) == -9


def test_a_close_waits_for_a_helper_that_is_ending_and_removes_the_one_that_stays(host, capsys, monkeypatch):
    virtuoso = host.virtuoso()
    bridge_setup._session_close(virtuoso, 'fnxSession3')                 # no helper: the close and one look
    assert virtuoso.calls[0] == 'maeCloseSession(?session "fnxSession3" ?forceClose t)' and len(virtuoso.calls) == 2

    ending = host.helper(21, virtuoso.pid)                               # a helper that was told to end: gone in a moment
    naps, sleep = [], time.sleep

    def nap(seconds):                                                    # the module's own wait between two looks
        if seconds < 0.5:
            return sleep(seconds)                                        # (subprocess waits through the same function)
        naps.append(seconds)
        ending.kill()
        ending.wait(timeout=5)

    monkeypatch.setattr(bridge_setup.time, 'sleep', nap)
    assert bridge_setup._reap_helpers(virtuoso) == [] and naps == [0.5]
    monkeypatch.undo()

    stays = host.helper(23, virtuoso.pid)                                # one that was never told
    virtuoso.calls.clear()
    begun = time.monotonic()
    [removed] = bridge_setup._reap_helpers(virtuoso, wait=1.0)
    assert removed['pid'] == stays.pid and stays.wait(timeout=5) == -9
    assert 0.9 < time.monotonic() - begun < 3.0 and len(virtuoso.calls) >= 3      # looked, waited, then removed
    said = capsys.readouterr().out
    assert f'Maestro helper process {stays.pid} (Service23.log, started ' in said and 'outlived its session: removed' in said

    late = host.helper(25, virtuoso.pid)
    seen = []
    real = bridge_setup._helper_sweep

    def sweep(client, remove=()):                                        # a helper that appears after the first look
        seen.append(tuple(remove))
        return [] if len(seen) == 1 else real(client, remove)

    monkeypatch.setattr(bridge_setup, '_helper_sweep', sweep)
    assert bridge_setup._reap_helpers(virtuoso, wait=1.0) == [] and alive(late)   # is not this close's to remove
    monkeypatch.undo()

    virtuoso.in_use = True                                               # and with a session open nothing is looked at
    assert bridge_setup._reap_helpers(virtuoso, wait=1.0) == [] and alive(late)


def test_a_look_that_fails_fails_nothing_and_its_text_is_not_one_the_maestro_fakes_answer():
    class Plain:                                                         # the Maestro tests' client: every call answers t
        def __init__(self):
            self.calls = []

        def execute_skill(self, text, timeout=60):
            self.calls.append(text)
            return types.SimpleNamespace(ok=True, errors=[], output='t')

    client = Plain()
    bridge_setup._session_close(client, 'fnxSession3')
    assert len(client.calls) == 2 and client.calls[0].startswith('maeCloseSession(')
    look = client.calls[1]
    for needed in ('maeGetSessions()', 'hiGetWindowList()', '-beanhost', '*/amps_Service*.log', '-mpssession', 'kill -9 $pid'):
        assert needed in look
    for word in ('outfile(', 'maeOpenSetup', 'ddGetObj', 'modelFiles', 'maeGetSetup', 'maeGetTestOutputs'):
        assert word not in look

    class Broken(Plain):
        def execute_skill(self, text, timeout=60):
            if 'maeCloseSession' not in text:
                raise RuntimeError('Socket timeout')
            return super().execute_skill(text, timeout)

    bridge_setup._session_close(Broken(), 'fnxSession4')                 # the close stands, the look is skipped
    assert bridge_setup._helper_sweep(Broken()) == [] and bridge_setup._reap_helpers(Broken()) == []
