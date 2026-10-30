"""Record 7.282: a run removes the simulator host's folders of designs whose raw output it does not keep - each folder named,
never a pattern, each one named by the run's own measurement - at each save point and at the end, and says Virtuoso's
memory at its start and end. Driven here with a runner that only records what it was asked to run."""
import json
import shlex
from types import SimpleNamespace

from gator_workbench import schema
from gator_workbench.engine import HOST_CLEANUP_CHUNK, RunEngine
from helpers import make_config

BRIDGE = '/tmp/virtuoso_bridge_minlei/fyworkstation/virtuoso_bridge_spectre'


def engine_like(tmp_path, *, mock=False, keep=False, runner=None):
    """Build a minimal engine stand-in that records host-cleanup events and errors."""
    events, errors = [], []
    config = make_config(tmp_path, output=dict(keep_simulator_host_folders=keep))
    engine = SimpleNamespace(task=SimpleNamespace(mock=mock, task_key='real:mscr_ota7t'), config=config, _host_folders=[],
                             _host_run=runner if runner is not None else False,
                             _event=lambda name, **fields: events.append(dict(event=name, **fields)),
                             _log_error=lambda name, exc, **fields: errors.append((name, str(exc))))
    for name in ('_host_runner', '_remember_host_folder', '_clean_host', '_log_virtuoso_memory'):
        setattr(engine, name, getattr(RunEngine, name).__get__(engine))
    return engine, events, errors


def job_with(tmp_path, name, raw):
    """Create a job directory whose measurements identify the supplied host results."""
    folder = tmp_path / name
    folder.mkdir()
    (folder / 'measurements.json').write_text(json.dumps(dict(results_on_host=raw, metrics={})))
    return folder


def test_only_a_folder_the_bridge_made_and_the_measurement_named_is_remembered(tmp_path):
    engine, _, _ = engine_like(tmp_path, runner=lambda script: '')
    for name, raw in (('a', f'{BRIDGE}/fef81c08/input.raw'), ('b', f'{BRIDGE}/fef81c08/input.raw'),     # the same twice: once
                      ('c', f'{BRIDGE}/1ef2c177/input.raw'), ('d', '/home/minlei/project/input.raw'),
                      ('e', f'{BRIDGE}/../../../etc/input.raw'), ('f', '/tmp/virtuoso_bridge_minlei/fyworkstation/other/ab12cd/input.raw'),
                      ('g', f'{BRIDGE}/NOT-HEX/input.raw'), ('h', None)):
        engine._remember_host_folder(job_with(tmp_path, name, raw))
    engine._remember_host_folder(tmp_path / 'no-such-job')
    assert engine._host_folders == [f'{BRIDGE}/fef81c08', f'{BRIDGE}/1ef2c177']
    mock, _, _ = engine_like(tmp_path / 'mock', mock=True)
    kept, _, _ = engine_like(tmp_path / 'kept', keep=True)
    for other in (mock, kept):
        other._remember_host_folder(tmp_path / 'a')
        assert other._host_folders == [] and other._host_runner() is None


def test_the_folders_are_removed_by_name_a_chunk_at_a_time_and_kept_when_that_fails(tmp_path):
    asked = []
    engine, events, errors = engine_like(tmp_path, runner=lambda script: asked.append(script) or '')
    folders = [f'{BRIDGE}/{n:08x}' for n in range(HOST_CLEANUP_CHUNK + 5)]
    engine._host_folders = list(folders)
    engine._clean_host()
    assert len(asked) == 2 and engine._host_folders == [] and errors == []
    named = [shlex.split(script)[3:] for script in asked]                    # rm -rf -- <folder> <folder> ...
    assert all(shlex.split(script)[:3] == ['rm', '-rf', '--'] for script in asked) and sum(named, []) == folders
    assert events == [dict(event='simulator_host_folders_removed', count=len(folders), left=0)]

    def broken(script):
        raise RuntimeError('the bridge connection to the simulator host is not running')
    engine, events, errors = engine_like(tmp_path, runner=broken)
    engine._host_folders = folders[:3]
    engine._clean_host()
    assert engine._host_folders == folders[:3] and errors and events == []   # tried again at the next save point


def test_virtuoso_memory_is_read_from_its_own_processes(tmp_path):
    listing = '    PID   RSS COMMAND\n 4242 10752000 virtuoso\n 4300  2048 bash\n 4400 51200 cdsXvfb-virtuoso\n'   # as the host's ps writes it
    engine, events, errors = engine_like(tmp_path, runner=lambda script: listing)
    engine._log_virtuoso_memory('start')
    assert errors == [] and events[0]['when'] == 'start'
    assert [p['pid'] for p in events[0]['processes']] == [4242, 4400] and events[0]['total_mb'] == 10550.0
    mock, mock_events, _ = engine_like(tmp_path / 'mock', mock=True)
    mock._log_virtuoso_memory('start')
    assert mock_events == []


def test_keeping_the_host_folders_is_a_setting_hashed_as_absent_while_off(tmp_path):
    config = make_config(tmp_path)
    raw = config.model_dump(mode='json')
    del raw['output']['keep_simulator_host_folders']
    assert config.output.keep_simulator_host_folders is False and schema.config_hash(config) == schema.config_hash(raw)
    assert schema.config_hash(make_config(tmp_path, output=dict(keep_simulator_host_folders=True))) != schema.config_hash(config)


def test_a_failure_dropped_for_the_storage_limit_has_its_host_folder_remembered_first(tmp_path):
    """Record 7.283 (Astra's review of 7.282): the storage-limit deletion in _apply_retention let the local copy go
    without reading its host folder from it - the other two deletions did - so those folders stayed on the host."""
    engine, events, errors = engine_like(tmp_path, runner=lambda script: '')
    run_dir = tmp_path / 'run'
    work, waveforms = run_dir / 'work', run_dir / 'waveforms'
    for folder in (work, waveforms):
        folder.mkdir(parents=True)
    engine.layout = SimpleNamespace(run_dir=run_dir, work=work, waveforms=waveforms)
    engine.config = make_config(tmp_path, output=dict(waveform_storage_limit_bytes=0))      # any failure kept is too much
    engine._waveform_index = engine._work_resolved = engine._scratch = engine.previous_best_waveform = None
    for name in ('_apply_retention', '_inside_work'):
        setattr(engine, name, getattr(RunEngine, name).__get__(engine))
    job = job_with(work, 'job-1', f'{BRIDGE}/0a1b2c3d/input.raw')
    (job / 'input.raw').write_bytes(b'x' * 100)
    engine._apply_retention([dict(source=str(job), record={}, decision='retained_failure', target='waveforms/jobs/job-1',
                                  job_id='job-1', evaluation_id='e1', journal=None)], None)
    assert not (waveforms / 'jobs' / 'job-1').exists() and not job.exists()          # kept, then dropped for space
    assert engine._host_folders == [f'{BRIDGE}/0a1b2c3d']                              # its host folder goes at the next save point
    index = json.loads((waveforms / 'index.json').read_text())
    assert index['entries']['job-1']['status'] == 'deleted_storage_limit' and errors == []
    assert any(e['event'] == 'waveform_retention_changed' and e['status'] == 'deleted_storage_limit' for e in events)
