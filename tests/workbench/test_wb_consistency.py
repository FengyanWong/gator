"""The check before every run of a saved task (task flow part 4, `consistency.py`): the editors against the task file
(also static validation, `task_not_saved`), the task against its working copy in Virtuoso (the run adapter's
no-simulation preflight), and a Maestro-measured task's Maestro test. Start refuses on a difference and creates nothing.
FAKE check processes and the recorded ring-oscillator export only - no Virtuoso, no simulation."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import consistency, profile_preflight, runs, schema, tasks, virtuoso_setup as vs
from gator_workbench.validation import validate
from helpers import bridge_is_importable, MOCK_TASK, probe, roots_for, workbench_app   # noqa: F401 - an imported fixture belongs to this module
from task_save_support import config as cell_config, ready, save, saved_ring, task_config
from fakes_virtuoso import maestro_netlister, SETUP, setup_writer

OK_STEPS = [dict(step='profile', ok=True, detail='p'), dict(step='connect', ok=True, detail='c'),
            dict(step='export', ok=True, detail='e'), dict(step='deck', ok=True, detail='d')]


def preflight_process(tmp_path, steps, tag='check'):
    """Stands in for `python -m gator_workbench.profile_preflight`: prints progress, then its one JSON line."""
    script = tmp_path / f'{tag}.py'
    script.write_text('import json, sys\nprint("bridge progress")\n'
                      f'print(json.dumps(dict(profile_preflight=True, name=sys.argv[2], ok={all(s["ok"] for s in steps)!r}, '
                      f'simulated=False, deck=None, steps={steps!r})))\n')
    return [sys.executable, str(script)]


def test_static_validation_says_when_the_editors_differ_from_the_saved_task(tmp_path):
    cfg = saved_ring(tmp_path)
    issues = lambda c: [i for i in validate(c).as_dict()['issues'] if i['code'] == 'task_not_saved']
    assert issues(cfg) == []                                                   # the saved rows, as "Reload saved values" brings them
    tighter = cfg.model_copy(deep=True)
    tighter.targets[0].lower = 1.3e9
    [issue] = issues(tighter)
    assert issue['path'] == 'targets' and issue['level'] == 'error'
    assert 'Specs differ from the saved task real:ring_osc (revision 1): osc_frequency_hz: lower 1.3 GHz here, 1.1 GHz saved' in issue['message']
    assert 'Press Save as' in issue['message'] and 'Reload saved values' in issue['message']        # the page's words (7.376)
    wider = cfg.model_copy(deep=True)
    wider.parameters[0].upper = wider.parameters[0].upper + 0.2
    wider.measurements = wider.measurements[:0]
    assert sorted(i['path'] for i in issues(wider)) == ['measurements', 'parameters']
    assert validate(wider).blocks_run
    resumed = tighter.model_copy(deep=True)
    resumed.run.mode = 'resume'                                                # a resume runs the run's own saved rows
    assert issues(resumed) == []
    mock = schema.WorkbenchConfig.model_validate(dict(tasks.starter_config(MOCK_TASK), run=dict(max_evaluations=3)))
    assert issues(mock) == []                                     # a registered circuit without a task file (record 7.128)


def test_the_check_compares_the_three_sides_and_says_what_to_do(tmp_path):
    cfg = saved_ring(tmp_path)
    passed = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, OK_STEPS)))
    assert passed['ok'] and passed['task'] == 'real:ring_osc' and passed['revision'] == 1 and passed['simulated'] is False
    assert [s['step'] for s in passed['steps']] == ['editors', 'profile', 'connect', 'export', 'deck']
    assert passed['steps'][0]['detail'] == 'Parameters, Probes and Specs are those of revision 1.'
    # the copy was changed in Virtuoso: the export no longer matches the saved task
    drifted = OK_STEPS[:2] + [dict(step='export', ok=False, detail='ValueError: MN1 w=1.1u, recorded 1u')]
    result = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, drifted, 'drift')))
    [failed] = [s for s in result['steps'] if not s['ok']]
    assert not result['ok'] and failed['title'] == 'The working copy in Virtuoso differs from the saved task'
    assert failed['fix'] == consistency.FIX_COPY and 'MN1 w=1.1u' in failed['detail']
    assert consistency.summary(result).startswith('Not started: the working copy in Virtuoso differs from the saved task. ValueError: MN1')
    # an ADE/Maestro window on the copy: the run would fail the same way, and the fix says which windows to close
    window = OK_STEPS[:1] + [dict(step='connect', ok=False, detail='RuntimeError: Active ADE/Maestro window conflicts with OCEAN export: maestro(1)')]
    result = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, window, 'window')))
    assert 'Close those ADE/Maestro windows' in [s for s in result['steps'] if not s['ok']][0]['fix']
    # the gate, no connection, and the editors - each said in its own step
    blocked = consistency.check(probe(tmp_path, tunnel='failed'), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, OK_STEPS)))
    gate = [s for s in blocked['steps'] if not s['ok']][0]
    assert gate['step'] == 'gate' and 'tunnel' in gate['detail'] and 'Connection window' in gate['fix']
    unconnected = consistency.check(probe(tmp_path), None, cfg)
    assert [s['step'] for s in unconnected['steps']] == ['editors', 'connection'] and not unconnected['ok']
    edited = cfg.model_copy(deep=True)
    edited.targets[0].lower = 1.3e9
    result = consistency.check(probe(tmp_path), 'lab', edited, commands=dict(preflight=preflight_process(tmp_path, OK_STEPS)))
    assert result['steps'][0]['ok'] is False and result['steps'][0]['fix'] == consistency.FIX_ROWS and not result['ok']
    with pytest.raises(KeyError):
        consistency.check(probe(tmp_path), 'lab', cell_config())            # a cell read from Virtuoso is no saved task


def test_a_maestro_measured_task_is_compared_with_its_maestro_test(tmp_path):
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n'}},
                  variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    save(tmp_path, name='ring_maestro', cfg=cell_config(probes=rows['measurements'], specs=rows['targets']),
         extras=dict(analyses={'tran': {'stop': '50n'}}), commands=dict(setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path)))
    cfg = task_config(tmp_path, 'ring_maestro')
    skipped = OK_STEPS[:3] + [dict(step='deck', ok=True, skipped=True, detail=profile_preflight.DECK_LATER)]
    same = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, skipped),
                                                                         setup=setup_writer(tmp_path, answer)))
    assert same['ok'] and [s['step'] for s in same['steps']][-2:] == ['deck', 'maestro'] and same['steps'][-2]['skipped']
    changed = dict(answer, outputs=[dict(SETUP['outputs'][0], expression='frequency(VT("/OUT2"))')] + SETUP['outputs'][1:])
    result = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, skipped, 'maestro'),
                                                                           setup=setup_writer(tmp_path, changed)))
    [failed] = [s for s in result['steps'] if not s['ok']]
    assert failed['step'] == 'maestro' and 'VT("/OUT2")' in failed['detail'] and 'Save as' in failed['fix']
    reads = [json.loads(line)['op'] for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert reads.count('read_setup') == 2                                     # a read, never a write


def test_a_start_voltage_changed_in_virtuoso_stops_the_run(tmp_path):
    """The initial conditions of a task are part of what is compared: a start voltage changed in the copy (or an ic file
    that is gone) is a difference, so nothing starts until the task is saved again."""
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    conditions = {'N1': '0', 'OUT': '0.9'}

    def answer(ic):
        """Build a Maestro setup response with the supplied initial conditions."""
        return dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n'}},
                    variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={}, initial_conditions=ic)

    save(tmp_path, name='ring_ic', cfg=cell_config(probes=rows['measurements'], specs=rows['targets']),
         extras=dict(analyses={'tran': {'stop': '50n'}}, initial_conditions=conditions),
         commands=dict(setup=setup_writer(tmp_path, answer(conditions)), deck=maestro_netlister(tmp_path)))
    cfg = task_config(tmp_path, 'ring_ic')
    skipped = OK_STEPS[:3] + [dict(step='deck', ok=True, skipped=True, detail=profile_preflight.DECK_LATER)]
    same = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, skipped),
                                                                        setup=setup_writer(tmp_path, answer(conditions))))
    assert same['ok']
    result = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, skipped, 'maestro'),
                                                                           setup=setup_writer(tmp_path, answer({'OUT': '0.5'}))))
    [failed] = [s for s in result['steps'] if not s['ok']]
    assert failed['step'] == 'maestro' and 'Initial condition on OUT: the task says 0.9, Virtuoso has 0.5' in failed['detail']
    assert 'Initial condition on N1' in failed['detail'] and 'Save as' in failed['fix']


def test_a_start_is_refused_on_a_difference_and_the_check_is_recorded_when_it_passes(tmp_path, monkeypatch):
    cfg = saved_ring(tmp_path)
    outcome = dict(steps=OK_STEPS[:2] + [dict(step='export', ok=False, detail='ValueError: topology differs')])
    seen = []

    def fake_preflight(monitor, name, profile_id, *, acknowledge_unknown=False, command=None, timeout=300.0):
        """Record preflight arguments and return the aggregate verdict of the fixture steps."""
        seen.append(dict(name=name, profile_id=profile_id, acknowledge_unknown=acknowledge_unknown))
        return dict(profile_preflight=True, name=name, ok=all(s['ok'] for s in outcome['steps']), steps=outcome['steps'], simulated=False)
    monkeypatch.setattr(profile_preflight, 'preflight', fake_preflight)
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(cfg, roots_for(tmp_path), allow_real=True, monitor=probe(tmp_path))
    assert refused.value.code == 'consistency' and str(refused.value).startswith('Not started: the working copy in Virtuoso differs')
    assert refused.value.report['steps'][-1]['fix'] == consistency.FIX_COPY
    assert not (tmp_path / 'out').exists() or not any((tmp_path / 'out').rglob('run_manifest.json'))      # nothing was created
    outcome['steps'] = OK_STEPS
    layout, manifest = runs.prepare_run(cfg, roots_for(tmp_path), allow_real=True, monitor=probe(tmp_path))
    assert manifest['consistency_check']['ok'] and [s['step'] for s in manifest['consistency_check']['steps']] == ['profile', 'connect', 'export', 'deck']
    assert seen == [dict(name='ring_osc', profile_id='lab', acknowledge_unknown=False)] * 2
    # the editors differ: static validation refuses first, and the copy is not even read
    edited = cfg.model_copy(deep=True)
    edited.targets[0].lower = 1.3e9
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(edited, roots_for(tmp_path), allow_real=True, monitor=probe(tmp_path))
    assert refused.value.code == 'validation' and len(seen) == 2


def test_a_busy_virtuoso_is_named_and_the_task_is_not_blamed(tmp_path, monkeypatch):
    """Record 7.207: while a command-line run held the adapter's session lock, Check now said "BlockingIOError" with the
    advice for a changed working copy (press Save task). Now it says who holds Virtuoso, and does not even read it."""
    import subprocess
    from gator_workbench.paths import bridge_state_dir
    cfg = saved_ring(tmp_path)
    # the lock was taken between the look for a holder and the adapter's connect: the adapter's refusal says the same
    taken = OK_STEPS[:1] + [dict(step='connect', ok=False, detail='BlockingIOError: [Errno 11] Resource temporarily unavailable')]
    result = consistency.check(probe(tmp_path), 'lab', cfg, commands=dict(preflight=preflight_process(tmp_path, taken)))
    busy = result['steps'][-1]
    assert busy['step'] == 'busy' and busy['fix'] == consistency.FIX_BUSY and 'Save' not in busy['fix']
    assert 'held by another process (BlockingIOError: [Errno 11]' in busy['detail']
    lock = bridge_state_dir() / 'session.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()
    assert consistency.lock_holder(lock) is None and consistency.lock_holder(tmp_path / 'missing') is None
    holder = subprocess.Popen([sys.executable, '-c', 'import fcntl, sys, time\nf = open(sys.argv[1], "a+")\n'
                               'fcntl.flock(f, fcntl.LOCK_EX)\nprint("held", flush=True)\ntime.sleep(60)', str(lock)],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline() == 'held\n'
        assert consistency.lock_holder(lock).startswith(f'a process (process {holder.pid}, started ')
        monkeypatch.setattr(profile_preflight, 'preflight', lambda *a, **kw: pytest.fail('Virtuoso was read while it is busy'))
        result = consistency.check(probe(tmp_path), 'lab', cfg)
        assert not result['ok'] and [s['step'] for s in result['steps']] == ['editors', 'busy']
        busy = result['steps'][-1]
        assert busy['title'] == 'Another real run is using Virtuoso, so the working copy could not be checked'
        assert busy['fix'] == consistency.FIX_BUSY and f'process {holder.pid}' in busy['detail']
        with pytest.raises(runs.RunRejected) as refused:
            runs.prepare_run(cfg, roots_for(tmp_path), allow_real=True, monitor=probe(tmp_path))
        assert str(refused.value).startswith('Not started: another real run is using Virtuoso')
    finally:
        holder.kill()
        holder.wait()
    assert consistency.lock_holder(lock) is None


def test_the_check_route_replaces_check_against_virtuoso(tmp_path, monkeypatch):
    cfg = saved_ring(tmp_path)
    monkeypatch.setattr(profile_preflight, 'preflight', lambda monitor, name, profile_id, **kw: dict(profile_preflight=True, ok=True, steps=OK_STEPS))
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path), auto_check_on_start=True))
    answer = client.post('/api/virtuoso/task/check', json=dict(profile_id='lab', config=cfg.model_dump(mode='json'))).json()
    assert answer['ok'] and answer['task'] == 'real:ring_osc' and answer['steps'][0]['step'] == 'editors'
    mock = schema.WorkbenchConfig.model_validate(dict(tasks.starter_config(MOCK_TASK), run=dict(max_evaluations=3)))
    refused = client.post('/api/virtuoso/task/check', json=dict(profile_id='lab', config=mock.model_dump(mode='json')))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'not_a_saved_task'
    assert client.post('/api/virtuoso/profile/preflight', json=dict(name='ring_osc', profile_id='lab')).status_code in (404, 405)


def test_the_no_simulation_check_leaves_the_deck_of_a_maestro_task_for_later(tmp_path, monkeypatch):
    """In-process: the adapter compares the export and refuses only when it builds the deck - the check says the deck
    was left out instead of failing the export."""
    from analog_optimizer.backends import virtuoso_bridge
    from gator_workbench.generic_profile import RulesError

    class Profile:
        """A profile stand-in that selects the Maestro recipe."""
        recipe = 'maestro'

    class Adapter:
        """A Maestro adapter stand-in whose netlist generation raises a rules error."""
        def __init__(self, config, profile):
            pass

        def connect(self):
            pass

        def generate_netlist(self, work_root):
            raise RulesError('Running a Maestro-measured task is not built yet')

        def close(self):
            pass
    monkeypatch.setattr(tasks, 'generated_bridge_config', lambda name, profile_id: (None, Profile(), {}))
    monkeypatch.setattr(virtuoso_bridge, 'VirtuosoBridgeBackend', Adapter)
    outcome = profile_preflight.run('ring_maestro', 'lab', tmp_path / 'work')
    assert outcome['ok'] and [s['step'] for s in outcome['steps']] == ['profile', 'connect', 'export', 'deck']
    assert outcome['steps'][-1] == dict(step='deck', ok=True, skipped=True, detail=profile_preflight.DECK_LATER)
    Profile.recipe = 'ring_oscillator'                                         # any other task: a refusal is a failure
    outcome = profile_preflight.run('ring_osc', 'lab', tmp_path / 'work2')
    assert not outcome['ok'] and outcome['steps'][-1]['step'] == 'export' and 'not built yet' in outcome['steps'][-1]['detail']
