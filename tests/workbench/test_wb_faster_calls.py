"""Record 7.279: the calls behind edits, windows and Virtuoso's checks answer as before, only faster - one task's profile
read instead of all of them, the connection gate's run lookup asked only when a check could be reused and kept 3 s, the
task list's shared facts worked out once, the source digest hashed again in a thread, a start's code facts read while
the connection is checked, run folders read many at a time, a PDK's model files kept between reads."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time

import pytest

from gator_workbench import baseline_reference, checkpoints as ckpt, pdk, profiles, run_index, runs, tasks
from gator_workbench.api import support
from gator_workbench.storage.atomic import write_json
from helpers import roots_for, workbench_app
from test_wb_connection import OK_BODY, monitor_for

PDK_FIXTURE = Path(__file__).parent / 'fixtures' / 'pdk_demo'
MODEL = '/pdk/demo045/models/demo045.scs'


def write_profile(folder_name, **fields):
    folder = profiles.store_root() / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    entry = dict(format=profiles.FORMAT, name=folder_name, circuit_class='oscillator', library='LIB', core_cell=f'{folder_name}_cell')
    (folder / profiles.FILES['entry']).write_text(json.dumps({**entry, **fields}))
    return folder


# ---- one task's profile --------------------------------------------------------------------------------------------
def test_one_profile_is_read_as_the_whole_list_reads_it():
    write_profile('ring_a')
    write_profile('ring_b', revision=3)
    write_profile('other_format', format='gator-generated-profile-0')
    write_profile('not_its_name', name='someone_else')
    (profiles.store_root() / 'bad_json').mkdir()
    (profiles.store_root() / 'bad_json' / profiles.FILES['entry']).write_text('{not json')
    (profiles.store_root() / 'no_entry').mkdir()
    listed = profiles.list_profiles()
    assert set(listed) == {'ring_a', 'ring_b'}
    for name in ('ring_a', 'ring_b', 'other_format', 'not_its_name', 'bad_json', 'no_entry', 'missing', 'Ring_a', '', '../x', None, 7):
        assert profiles.profile_entry(name) == listed.get(name), name


# ---- the connection gate's run lookup -------------------------------------------------------------------------------
def test_the_gate_asks_for_a_working_run_only_when_a_check_could_be_reused(tmp_path):
    asked = []
    monitor = monitor_for(tmp_path, OK_BODY, active_run_lookup=lambda profile_id: asked.append(profile_id))
    monitor.gate('write_cellview', 'lab')                                     # nothing to reuse: only the probe asks
    assert len(asked) == 1 and monitor.probes_started == 1
    assert monitor.gate('read_cellview', 'lab')['check_reused'] and len(asked) == 2     # reusable: asked once, to compare
    monitor.gate_reuse_seconds = 0.0
    time.sleep(0.05)
    assert not monitor.gate('read_cellview', 'lab')['check_reused']         # too old: not asked for the reuse any more
    assert len(asked) == 3 and monitor.probes_started == 2


def test_one_look_for_a_working_run_serves_the_gate_for_three_seconds(tmp_path, monkeypatch):
    from gator_workbench.api import app as app_module
    looks = []
    monkeypatch.setattr(runs, 'list_runs', lambda roots, *args, **kwargs: looks.append(1) or [])
    lookup = workbench_app(tmp_path).state.monitor.active_run_lookup
    assert lookup('lab') is None and lookup('lab') is None and len(looks) == 1
    assert lookup('other') is None and len(looks) == 2                      # each connection has its own answer
    monkeypatch.setattr(app_module, 'ACTIVE_RUN_REUSE_SECONDS', 0.0)
    assert lookup('lab') is None and len(looks) == 3


# ---- the task list ----------------------------------------------------------------------------------------------------
def test_the_task_list_asks_once_what_blocks_generated_tasks_and_reads_each_reference_once(monkeypatch):
    for name in ('ring_a', 'ring_b', 'ring_c'):
        write_profile(name)
    write_profile('maestro_x', recipe=profiles.MAESTRO, runnable=False)
    blockers, references = [], []
    monkeypatch.setattr(tasks, 'generated_backend_blocker', lambda profile_id=None: blockers.append(profile_id) or 'no link')
    monkeypatch.setattr(profiles, 'reference_metrics', lambda name: references.append(name) or (dict(x=1) if name == 'ring_b' else None))
    listed = {t['task_key']: t for t in tasks.list_tasks() if t.get('generated')}
    assert blockers == [None] and sorted(references) == ['maestro_x', 'ring_a', 'ring_b', 'ring_c']
    assert [listed[f'real:{n}']['blocker'] for n in ('ring_a', 'ring_b', 'ring_c')] == ['no link'] * 3
    assert listed['real:maestro_x']['blocker'] == profiles.MAESTRO_NOT_RUNNABLE
    assert listed['real:ring_b']['verified'] and not listed['real:ring_a']['verified']
    assert listed['real:ring_a']['description'].endswith('No real baseline recorded yet.')
    assert listed['real:ring_b']['description'].endswith('(Virtuoso + Spectre). ')


# ---- the source digest and a start's code facts ---------------------------------------------------------------------
def test_the_source_digest_is_hashed_again_in_a_thread_once_known(monkeypatch):
    import analog_optimizer.training.sac as sac
    values, release = iter(['first', 'second']), threading.Event()

    def digest():
        value = next(values)
        if value == 'second':
            release.wait(5)
        return value
    monkeypatch.setattr(sac, 'source_digest', digest)
    monkeypatch.setattr(run_index, '_SOURCE_DIGEST', dict(value=None, at=0.0, refreshing=False))
    assert run_index.current_source_digest() == 'first'                         # the first one: hashed at once
    assert run_index.current_source_digest(max_age=0.0) == 'first'              # older: answered at once, hashed in a thread
    assert run_index._SOURCE_DIGEST['refreshing'] and run_index.current_source_digest(max_age=0.0) == 'first'   # one thread at a time
    release.set()
    for _ in range(200):
        if not run_index._SOURCE_DIGEST['refreshing']:
            break
        time.sleep(0.01)
    assert run_index.current_source_digest() == 'second'


def test_a_started_job_gives_its_answer_or_its_error():
    assert runs._started(lambda: 41 + 1).result(5) == 42

    def fails():
        raise ValueError('no git')
    with pytest.raises(ValueError, match='no git'):
        runs._started(fails).result(5)


# ---- run folders read many at a time ----------------------------------------------------------------------------------
def fabricate_run(root, name, *, created, kind=None, state='completed', task='real:ring_a'):
    run = root / 'exp__0123456789ab' / 'runs' / 'task' / name
    run.mkdir(parents=True)
    write_json(run / 'run_manifest.json', dict(run_id=name, created_utc=created, mock=False, experiment_name='exp',
                                               experiment_id='0123456789ab', task_name='task', run_kind=kind, state=state,
                                               circuit=dict(task_key=task)))
    write_json(run / 'status.json', dict(state=state))
    write_json(run / 'run_summary.json', dict(output=dict(resumability='full_state')))
    return run


def test_read_many_answers_in_the_order_asked():
    items = list(range(60))
    assert runs.read_many(lambda n: (time.sleep(0.002 * (n % 3)), n * n)[1], items) == [n * n for n in items]
    assert runs.read_many(str, [7]) == ['7'] and runs.read_many(str, []) == []


def test_the_saved_models_listings_read_many_at_a_time_are_those_read_one_by_one(tmp_path):
    for n in range(5):
        run = fabricate_run(tmp_path, f'r{n}', created=f'2026-10-08T10:0{n}:00+00:00')
        point = run / 'checkpoints' / f'ckpt-0000001{n}-a'
        point.mkdir(parents=True)
        write_json(point / 'metadata.json', dict(checkpoint_id=point.name, kind='periodic', created_utc='2026-10-08T10:10:00+00:00',
                                                 mode='scratch', counters=dict(evaluations_committed=10, learner_updates=10, replay_size=10),
                                                 restoration_capability='full_state', missing_components=[],
                                                 contract=dict(code_sha256='abc', model_config=dict(encoder_type='rgcn', hidden_dim=16, heads=2, layers=1))))
        write_json(run / 'checkpoints' / 'latest.json', dict(checkpoint_id=point.name))
    rows = runs.list_runs(roots_for(tmp_path), tmp_path)
    assert ckpt.saved_models(rows, runs.checkpoint_listings(rows)) == ckpt.saved_models(rows)
    assert [r['run_id'] for r in rows] == ['r4', 'r3', 'r2', 'r1', 'r0']


def test_a_task_load_finds_its_newest_baseline_through_the_run_cache(tmp_path, monkeypatch):
    fabricate_run(tmp_path, 'old', created='2026-10-01T10:00:00+00:00', kind=profiles.BASELINE_KIND)
    newest = fabricate_run(tmp_path, 'new', created='2026-10-05T10:00:00+00:00', kind=profiles.BASELINE_KIND)
    fabricate_run(tmp_path, 'failed', created='2026-10-06T10:00:00+00:00', kind=profiles.BASELINE_KIND, state='failed')
    fabricate_run(tmp_path, 'other', created='2026-10-07T10:00:00+00:00', kind=profiles.BASELINE_KIND, task='real:ring_b')
    fabricate_run(tmp_path, 'train', created='2026-10-07T11:00:00+00:00')
    given = []

    def adopt(run_dir, manifest=None):
        given.append((Path(run_dir), manifest))
        manifest['state'] = 'changed by the callee'                         # a copy: the run list's cache keeps its own
        return dict(recorded=True, name='ring_a')
    monkeypatch.setattr(baseline_reference, 'adopt_baseline_run', adopt)
    assert profiles.adopt_latest_baseline('ring_a', tmp_path) == dict(recorded=True, name='ring_a')
    assert [run for run, _ in given] == [newest]
    assert runs._run_facts(newest)['manifest']['state'] == 'completed'
    assert profiles.adopt_latest_baseline('ring_none', tmp_path) is None


def test_a_runs_files_listed_many_at_a_time_are_those_listed_one_by_one(tmp_path):
    for relative in ('run_manifest.json', 'data/evaluations/part-0.parquet', 'data/_quarantine/x.bin', 'work/lane-1/job.json',
                     'logs/events.jsonl', 'checkpoints/ckpt-a/metadata.json'):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(relative)

    def one_by_one(root, *, exclude_roots=(), exclude_dirs=()):          # run_files before record 7.279
        entries = []
        for directory, dirs, files in os.walk(root):
            base = Path(directory)
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not (base == root and d in exclude_roots)]
            for name in files:
                info = (base / name).stat()
                if stat.S_ISREG(info.st_mode):
                    entries.append((base / name, (base / name).relative_to(root).as_posix(), info))
        return sorted(entries, key=lambda entry: entry[1])
    for options in (dict(), dict(exclude_roots=('work',)), dict(exclude_roots=('work', 'checkpoints'), exclude_dirs=('_quarantine',))):
        assert support.run_files(tmp_path, **options) == one_by_one(tmp_path, **options)


# ---- the PDK's model files ----------------------------------------------------------------------------------------------
class _Result:
    def __init__(self, ok=True, output='', errors=()):
        self.ok, self.output, self.errors = ok, output, list(errors)


class _Host:
    """The simulator host and Virtuoso, as the PDK reader sees them: the demo045 files, each with a modification time."""
    def __init__(self, files, modified):
        self.files, self.modified, self.downloads, self.stamp_queries, self.stamps_answer = files, modified, [], 0, True

    def execute_skill(self, text, timeout):
        if 'fileTimeModified' in text:
            self.stamp_queries += 1
            if not self.stamps_answer:
                return _Result(ok=False, errors=['*Error* the session is busy'])
            lines = [f'{p}|{len(self.files[p])}|{self.modified[p]}' if p in self.files else f'{p}|missing'
                     for p in re.findall(r'"(/[^"]+)"', text)]
            return _Result(output='\n'.join(lines))
        if 'ddGetObj("analogLib")' in text:
            return _Result(output=(PDK_FIXTURE / 'ideal.txt').read_text())
        return _Result(output=(PDK_FIXTURE / 'cdf.txt').read_text())

    def download_file(self, remote, local, timeout=None):
        self.downloads.append(remote)
        Path(local).write_bytes(self.files[remote])
        return _Result()


def test_the_pdk_model_files_are_downloaded_only_when_the_host_holds_others():
    files = {f'/pdk/demo045/models/{name}': (PDK_FIXTURE / 'models' / name).read_bytes()
             for name in ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')}
    modified = {path: '1727000000' for path in files}

    def read(host):
        return pdk.read_from_virtuoso(host, technology_library='demo045', model_file=MODEL, decode=lambda text: text)
    first_host = _Host(files, modified)
    first = read(first_host)
    assert sorted(first_host.downloads) == sorted(files)                       # the first read downloads every file
    again = _Host(files, modified)
    assert read(again) == first and again.downloads == [] and again.stamp_queries == 1   # nothing changed: nothing downloaded
    passive = '/pdk/demo045/models/demo045_passive.scs'
    changed_files = dict(files, **{passive: files[passive] + b'\n* one more line\n'})
    changed = _Host(changed_files, dict(modified, **{passive: '1727000100'}))
    answer = read(changed)
    assert changed.downloads == [passive]                                      # only the file the host holds anew
    assert answer['sources']['model_files'] != first['sources']['model_files']
    copy = pdk.ModelFileCache('demo045')
    kept = copy.folder / copy.index[MODEL]['sha256']
    kept.write_bytes(b'* not the file any more\n')                              # a copy that changed is not trusted
    damaged = _Host(changed_files, dict(modified, **{passive: '1727000100'}))
    assert read(damaged) == answer and damaged.downloads == [MODEL]
    busy = _Host(changed_files, dict(modified, **{passive: '1727000100'}))
    busy.stamps_answer = False                                                 # no answer about the files: all downloaded
    assert read(busy) == answer and sorted(busy.downloads) == sorted(files) and busy.stamp_queries == 1
    shutil.rmtree(copy.folder)


def test_the_model_file_copies_are_kept_per_host():
    """Record 7.283 (Astra's review of 7.279): the same path on two hosts can carry the same size and modification time
    with different content; the copies are kept per host, so the second host is never served the first one's file."""
    files = {f'/pdk/demo045/models/{name}': (PDK_FIXTURE / 'models' / name).read_bytes()
             for name in ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')}
    modified = {path: '1727000000' for path in files}
    passive = '/pdk/demo045/models/demo045_passive.scs'
    other = dict(files, **{passive: files[passive][:-1] + (b'Y' if files[passive][-1:] != b'Y' else b'Z')})    # the same length

    def read(host, identity):
        return pdk.read_from_virtuoso(host, technology_library='demo045', model_file=MODEL, decode=lambda text: text, cache_host=identity)
    folders = [pdk.ModelFileCache('demo045', identity).folder for identity in ('minlei@vm-a', 'minlei@vm-b')]
    assert [f.parent.name for f in folders] == ['minlei@vm-a', 'minlei@vm-b'] and folders[0].parent.parent == folders[1].parent.parent
    assert pdk.host_folder_name('user@host:22/../x') == 'user@host_22_.._x' and pdk.host_folder_name('') == 'host'
    try:
        a = read(_Host(files, modified), 'minlei@vm-a')
        second = _Host(other, modified)                                           # the same stamps, another file
        b = read(second, 'minlei@vm-b')
        assert sorted(second.downloads) == sorted(files)                          # its own copies: everything downloaded
        assert b['sources']['model_files'] != a['sources']['model_files']
        again = _Host(files, modified)
        assert read(again, 'minlei@vm-a') == a and again.downloads == []          # the first host's copies still serve it
    finally:
        for folder in folders:
            shutil.rmtree(folder.parent, ignore_errors=True)
