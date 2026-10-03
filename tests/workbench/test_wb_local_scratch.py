"""Simulator scratch on the local disk for a run whose folder is on a slow mount (record 7.149): the mount check, the
links in an environment's folder, and a whole run whose job folders live in the scratch until retention moves them."""
import pickle
from pathlib import Path

from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from gator_workbench import engine as engine_module, layout
from gator_workbench.lanes import ScratchLinked, link_scratch, unlink_scratch
from gator_workbench.layout import RunLayout
from helpers import bridge_is_importable, execute, make_config  # noqa: F401 - an imported fixture belongs to this module

MOUNTS = ('/dev/sdd / ext4 rw,relatime 0 0\n'
          'D:\\134 /mnt/d 9p rw,noatime,aname=drvfs;path=D:\\ 0 0\n'
          'E:\\134 /mnt/d/deep 9p rw 0 0\n'
          'none /mnt/my\\040drive drvfs rw 0 0\n')


def test_the_filesystem_comes_from_the_longest_mount_point_above_the_path():
    assert layout.filesystem_type('/mnt/d/gator/outputs/run', MOUNTS) == '9p'
    assert layout.filesystem_type('/home/someone/outputs', MOUNTS) == 'ext4'
    assert layout.filesystem_type('/mnt/dd/outputs', MOUNTS) == 'ext4'          # only starts with /mnt/d
    assert layout.filesystem_type('/mnt/my drive/outputs', MOUNTS) == 'drvfs'   # \040 is a space in /proc/mounts
    assert layout.filesystem_type('/x', '') is None


def test_only_a_run_folder_on_a_slow_mount_gets_a_local_scratch(tmp_path, monkeypatch):
    run = RunLayout(tmp_path / 'exp__abc' / 'runs' / 'task' / 'scratch__seed1__0123456789ab')
    monkeypatch.delenv('GATOR_LOCAL_SCRATCH', raising=False)
    monkeypatch.setattr(layout, 'filesystem_type', lambda path, mounts=None: '9p' if str(path).startswith(str(tmp_path)) else 'ext4')
    assert layout.local_scratch(run) == Path('/tmp/gator-work') / 'exp__abc' / 'scratch__seed1__0123456789ab'   # the default (7.168)
    monkeypatch.setenv('GATOR_LOCAL_SCRATCH', 'off')
    assert layout.local_scratch(run) is None
    monkeypatch.delenv('GATOR_LOCAL_SCRATCH')
    monkeypatch.setattr(layout, 'filesystem_type', lambda path, mounts=None: 'ext4')
    assert layout.local_scratch(run) is None
    monkeypatch.setattr(layout, 'filesystem_type', lambda path, mounts=None: '9p')   # the local disk slow too: no gain
    assert layout.local_scratch(run) is None


class Env:
    def __init__(self, directory):
        self.directory = directory


class EnvFactory:
    """Like the optimizer's environment: its own fresh folder, with its candidate records made at once."""
    def __init__(self, root):
        self.root = root

    def __call__(self, lane_id):
        directory = Path(self.root) / f'env{lane_id}'
        (directory / 'candidates').mkdir(parents=True)
        return Env(directory)


def test_an_environment_s_two_scratch_folders_become_links_and_nothing_else(tmp_path):
    work, scratch = tmp_path / 'work', tmp_path / 'scratch'
    factory = pickle.loads(pickle.dumps(ScratchLinked(EnvFactory(work), scratch)))       # a process lane gets a copy
    env = factory(0)
    for name in ('exports', 'simulations'):
        assert (env.directory / name).is_symlink() and (env.directory / name).resolve() == scratch / 'env0' / name
    assert (env.directory / 'candidates').is_dir() and not (env.directory / 'candidates').is_symlink()
    (env.directory / 'simulations' / 'job1').mkdir()
    (env.directory / 'simulations' / 'job1' / 'result.json').write_text('{}')
    assert (scratch / 'env0' / 'simulations' / 'job1' / 'result.json').is_file()
    link_scratch(env.directory, tmp_path / 'elsewhere')                                   # done once only
    assert (env.directory / 'exports').resolve() == scratch / 'env0' / 'exports'
    unlink_scratch(env.directory)
    assert not (env.directory / 'exports').exists() and (scratch / 'env0' / 'simulations' / 'job1').is_dir()
    (env.directory / 'exports').mkdir()                                                   # a real folder stays real
    link_scratch(env.directory, scratch)
    assert not (env.directory / 'exports').is_symlink() and (env.directory / 'simulations').is_symlink()


def test_a_run_keeps_its_job_folders_in_the_scratch_until_retention_moves_them_and_clears_it_at_the_end(tmp_path, monkeypatch):
    roots = {}

    def scratch_for(run):
        roots['scratch'] = tmp_path / 'scratch' / run.run_dir.name
        return roots['scratch']
    monkeypatch.setattr(engine_module, 'local_scratch', scratch_for)
    sources, apply = [], engine_module.RunEngine._apply_retention

    def watching(self, plan, role):
        sources.extend(Path(item['source']).resolve() for item in plan if item['source'])   # where it is right now
        return apply(self, plan, role)
    monkeypatch.setattr(engine_module.RunEngine, '_apply_retention', watching)
    simulate = SyntheticSizingBackend.run_simulation

    def writing(self, request):                          # the toy backend leaves its job folders empty: give each a file
        result = simulate(self, request)
        (Path(result.artifact_directory) / 'result.json').write_text('{}')
        return result
    monkeypatch.setattr(SyntheticSizingBackend, 'run_simulation', writing)
    out = tmp_path / 'out'
    run, state = execute(make_config(out, run=dict(max_evaluations=6), output=dict(waveform_retention='all')), out)
    assert state == 'completed' and sources
    assert all(source.is_relative_to(roots['scratch']) for source in sources)                  # every job folder
    assert len(list(run.waveforms.glob('*/attempt-*/result.json'))) == len(sources)            # each one kept
    assert not roots['scratch'].exists() and not roots['scratch'].parent.exists()             # cleared at the end
    assert not [path for path in run.work.rglob('*') if path.is_symlink()]                     # no link left
    assert list(run.work.rglob('candidates'))                                                  # the lanes' own folders
    events = (run.logs / 'events.jsonl').read_text()
    assert '"simulator_scratch"' in events and str(roots['scratch']) in events


def test_process_lanes_link_their_own_scratch_folders(tmp_path, monkeypatch):
    """Real lanes are processes: each builds its environment itself, from a pickled copy of the factory."""
    roots = {}

    def scratch_for(run):
        roots['scratch'] = tmp_path / 'scratch' / run.run_dir.name
        return roots['scratch']
    monkeypatch.setattr(engine_module, 'local_scratch', scratch_for)
    sources, apply = [], engine_module.RunEngine._apply_retention

    def watching(self, plan, role):
        sources.extend(Path(item['source']).resolve() for item in plan if item['source'])
        return apply(self, plan, role)
    monkeypatch.setattr(engine_module.RunEngine, '_apply_retention', watching)
    out = tmp_path / 'out'
    run, state = execute(make_config(out, run=dict(max_evaluations=4, concurrency=2)), out, use_processes=True)
    assert state == 'completed' and sources
    assert all(source.is_relative_to(roots['scratch']) for source in sources)
    assert not roots['scratch'].exists() and not [path for path in run.work.rglob('*') if path.is_symlink()]
