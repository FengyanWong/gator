"""One Save task at a time, and how far it is (`task_saving`, the steps `profiles.save_task` reports, GET /api/tasks/saving;
record 7.198). FAKE bridge processes and stand-in saves only - no Virtuoso, no simulation."""
import threading

from fastapi.testclient import TestClient

from gator_workbench import profiles, task_saving, virtuoso_setup as vs, working_copy
from helpers import _no_save_yet, bridge_is_importable, probe, workbench_app   # noqa: F401 - an imported fixture belongs to this module
from task_save_support import config, ready, save
from fakes_virtuoso import CELL, LIB, maestro_netlister, SETUP, setup_writer

MAESTRO_STEPS = ['setup', 'deck', 'read', 'files']


def test_a_save_reports_each_step_as_it_starts_with_every_step_it_takes(tmp_path):
    ready(tmp_path)
    heard = []
    progress = lambda step, steps: heard.append((step, tuple(steps)))
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9), progress=progress)
    assert heard == [('read', ('read', 'files')), ('files', ('read', 'files'))]       # a ring oscillator: no Maestro test to write
    heard.clear()
    save(tmp_path, name='ring_fast', task='ring_osc', as_new=True, progress=progress)  # the API's Save as makes a copy first
    assert [step for step, _ in heard] == ['copy', 'read', 'files'] and {steps for _, steps in heard} == {('copy', 'read', 'files')}
    assert all(step in task_saving.TITLES for step, _ in heard)


def test_a_maestro_task_reports_its_two_virtuoso_steps_first(tmp_path):
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n'}},
                  variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    heard = []
    save(tmp_path, name='ring_maestro', cfg=config(probes=rows['measurements'], specs=rows['targets']),
         extras=dict(analyses={'tran': {'stop': '50n'}}), commands=dict(setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path)),
         progress=lambda step, steps: heard.append((step, tuple(steps))))
    assert [step for step, _ in heard] == MAESTRO_STEPS and {steps for _, steps in heard} == {tuple(MAESTRO_STEPS)}
    assert working_copy.load(LIB, CELL)['claimed_by'] == 'ring_maestro'


def _client(tmp_path):
    """Provide task-save routes with a successful fake connection probe."""
    return TestClient(workbench_app(tmp_path, monitor=probe(tmp_path), auto_check_on_start=True))


def _held_save(monkeypatch, *, revision=7):
    """A stand-in save that reports its first step, then waits until the test lets it go on."""
    started, go_on = threading.Event(), threading.Event()

    def held(monitor, profile_id, name, config, **kwargs):
        """Report setup progress and hold the fake save until the test releases it."""
        kwargs['progress']('setup', MAESTRO_STEPS)
        started.set()
        assert go_on.wait(20)
        kwargs['progress']('files', MAESTRO_STEPS)
        return dict(task_key=f'real:{name}', name=name, revision=revision, created=False, baseline_kept=True, changed=['specs'], parameters=[])
    monkeypatch.setattr(profiles, 'save_task', held)
    return started, go_on


def test_one_save_at_a_time_whichever_page_sends_it_and_its_steps_can_be_followed(tmp_path, monkeypatch):
    client = _client(tmp_path)
    assert client.get('/api/tasks/saving').json() == dict(running=None, last=None)
    started, go_on = _held_save(monkeypatch)
    body = dict(profile_id='lab', name='ring_osc', task='ring_osc', config=config().model_dump(mode='json'))
    answers = []
    first = threading.Thread(target=lambda: answers.append(client.post('/api/virtuoso/task/save', json=body)))
    first.start()
    try:
        assert started.wait(20)
        now = client.get('/api/tasks/saving').json()['running']
        assert (now['task_key'], now['step'], now['step_number']) == ('real:ring_osc', 'setup', 1)
        assert [s['id'] for s in now['steps']] == MAESTRO_STEPS and now['steps'][1]['title'] == task_saving.TITLES['deck']
        assert now['seconds'] >= 0 and now['step_seconds'] >= 0 and now['usual_seconds'] is None
        # A second press - another tab, or a page loaded again that missed the first one - is refused, saying what runs.
        second = client.post('/api/virtuoso/task/save', json=dict(body, name='other', task=None, library=LIB, cell=CELL))
        assert second.status_code == 409 and second.json()['detail']['code'] == 'save_running'
        assert second.json()['detail']['running']['id'] == now['id'] and 'real:ring_osc' in second.json()['detail']['message']
        # Nor can the task being saved be deleted meanwhile.
        gone = client.post('/api/virtuoso/profile/delete', json=dict(name='ring_osc'))
        assert gone.status_code == 409 and 'being saved' in gone.json()['detail']['message']
    finally:
        go_on.set()
        first.join(20)
    assert answers[0].status_code == 200 and answers[0].json()['revision'] == 7
    after = client.get('/api/tasks/saving').json()
    assert after['running'] is None and after['last']['id'] == now['id'] and after['last']['ok']
    assert after['last']['answer'] == dict(task_key='real:ring_osc', revision=7, created=False, baseline_kept=True, changed=['specs'])
    # The next save may start; while it runs, the page can say how long the last save of this task took.
    started, go_on = _held_save(monkeypatch, revision=8)
    again = threading.Thread(target=lambda: answers.append(client.post('/api/virtuoso/task/save', json=body)))
    again.start()
    try:
        assert started.wait(20)
        assert client.get('/api/tasks/saving').json()['running']['usual_seconds'] == after['last']['seconds']
    finally:
        go_on.set()
        again.join(20)
    assert answers[1].status_code == 200 and answers[1].json()['revision'] == 8


def test_a_save_that_fails_says_why_and_frees_the_place(tmp_path, monkeypatch):
    client = _client(tmp_path)

    def refused(monitor, profile_id, name, config, **kwargs):
        """Report read progress before refusing the fake working-copy readback."""
        kwargs['progress']('read', ['read', 'files'])
        raise profiles.ProfileError('The working copy could not be read back into the workbench')
    monkeypatch.setattr(profiles, 'save_task', refused)
    body = dict(profile_id='lab', name='ring_osc', task='ring_osc', config=config().model_dump(mode='json'))
    answer = client.post('/api/virtuoso/task/save', json=body)
    assert answer.status_code == 409 and answer.json()['detail']['code'] == 'refused'
    state = client.get('/api/tasks/saving').json()
    assert state['running'] is None and not state['last']['ok'] and 'answer' not in state['last']
    assert state['last']['problem'] == dict(message='The working copy could not be read back into the workbench', code='refused')
    assert task_saving.running_task() is None and task_saving._took == {}             # a failed save sets no usual time
