"""Output directory layout (specification section 7) and manifest construction.

<data_root>/<experiment_name>__<experiment_id>/
  experiment.json  split_manifest.json  data_dictionary.json
  runs/<task_name>/<mode>__seed<seed>__<run_id>/   (see RunLayout)
  aggregates/*.csv

<data_root> is the selected output root for real tasks and <output_root>/mock for mock tasks.
A new run always gets a unique directory (mkdir exist_ok=False); a resumed run writes back to
its original directory. Paths inside manifests are relative and therefore portable; the
original absolute environment is recorded separately.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import socket
import stat
import subprocess
import sys
from uuid import uuid4

from . import OUTPUT_LAYOUT_VERSION, __version__
from .paths import directory_bytes, environment_label, repo_root
from .storage.atomic import TEMP_MARKER, read_json, read_jsonl, sha256_file, write_json
from .storage.dataset import utcnow

PURPOSES = {
    'run_manifest.json': 'Identity and provenance of the run',
    'model_label.json': "The model's name after a rename (the manifest keeps the name given at the start)",
    'effective_config.json': 'Exact validated configuration that was executed',
    'run_summary.json': 'Per-run research statistics',
    'artifact_manifest.json': 'This file list',
    'status.json': 'Live run-control status (not research data)',
    'input_snapshot': 'Circuit, netlist, parameter mapping and PDK reference the run started from',
    'data': 'Raw Parquet tables + write-ahead journal',
    'best_design': 'Best discovered circuit parameter sets and measurements (not a model)',
    'checkpoints': 'Model/training state; latest and best_policy pointers',
    'waveforms': 'Retained raw simulator output (never rendered)',
    'logs': 'events.jsonl, errors.jsonl and timings.jsonl (what each evaluation\'s stages took)',
    'exports': 'On-demand derived CSV copies of raw tables',
    'control': 'Run-control commands and the single-writer lock',
    'work': 'Registered temporary simulator working directories',
}


@dataclass(frozen=True)
class RunLayout:
    # The standard paths and directories belonging to one persisted run.
    run_dir: Path

    def __post_init__(self):
        object.__setattr__(self, 'run_dir', Path(self.run_dir))

    def __getattr__(self, name):
        table = dict(manifest='run_manifest.json', effective_config='effective_config.json',
                     summary='run_summary.json', artifact_manifest='artifact_manifest.json', status='status.json',
                     input_snapshot='input_snapshot', data='data', best_design='best_design',
                     checkpoints='checkpoints', waveforms='waveforms', logs='logs', exports='exports',
                     control='control', work='work', run_lock='control/run.lock', command='control/command.json')
        if name in table:
            return self.run_dir / table[name]
        raise AttributeError(name)

    @property
    def experiment_dir(self) -> Path:
        return self.run_dir.parents[2]

    def create(self):
        """Create the standard run subdirectories without replacing existing contents."""
        for name in ('input_snapshot', 'data', 'best_design', 'checkpoints', 'waveforms', 'logs', 'exports',
                     'control', 'work'):
            getattr(self, name).mkdir(parents=True, exist_ok=True)

    def subpaths(self):
        """Describe run artifact locations for persisted output metadata."""
        return dict(run=str(self.run_dir), raw_data=str(self.data), checkpoints=str(self.checkpoints),
                    replay='checkpoints/<checkpoint_id>/training_state.pt (embedded) + replay_buffer/manifest.json',
                    best_designs=str(self.best_design), csv_exports=str(self.exports),
                    aggregates=str(self.experiment_dir / 'aggregates'), waveforms=str(self.waveforms),
                    logs=str(self.logs), simulator_work=str(self.work))


# Simulator scratch on the local disk (record 7.149). The D: drive seen from WSL is a 9p mount, about 100 times slower per
# file operation: replayed offline, a lane's job folder (the 19 files of an mscr_ota7t job) took 0.15 s there and
# 0.002 s on the WSL disk, the preparation's export files 0.03 s and 0.0015 s.
SLOW_FILESYSTEMS = frozenset({'9p', 'drvfs', 'cifs', 'smb3', 'nfs', 'nfs4', 'fuse.sshfs'})


def filesystem_type(path, mounts=None) -> str | None:
    """The type of the filesystem holding `path`: that of the longest mount point above it in /proc/mounts (`mounts`,
    its text, for tests). None when unknown."""
    if mounts is None:
        try:
            mounts = Path('/proc/mounts').read_text()
        except OSError:
            return None
    target, best, kind = os.path.realpath(path), '', None
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        point = fields[1].replace('\\040', ' ')
        if (target == point or target.startswith(point.rstrip('/') + '/')) and len(point) > len(best):
            best, kind = point, fields[2]
    return kind


def local_scratch(layout: RunLayout) -> Path | None:
    """Where a run keeps its simulator scratch - the export packages and the per-job simulation folders of its lanes -
    when its folder is on a slow mount: a folder of its own under the connection module's "Simulator scratch"
    (`/tmp/gator-work` by default, on the WSL disk, which WSL empties at every boot; record 7.168). The lanes' own
    folders, with their launch journals, candidate records and restoration records, stay in the run folder; retention
    moves each kept job folder there as before. None when the run folder is on a local disk, when the scratch is on a
    slow mount too, or with GATOR_LOCAL_SCRATCH=off."""
    if os.environ.get('GATOR_LOCAL_SCRATCH', '').strip().lower() in ('off', '0', 'no', 'false'):
        return None
    from .directories import local_path  # lazy: layout and directories import each other
    root = local_path('local_scratch')
    if filesystem_type(layout.run_dir) not in SLOW_FILESYSTEMS or filesystem_type(root.parent) in SLOW_FILESYSTEMS:
        return None
    return root / layout.experiment_dir.name / layout.run_dir.name


def new_experiment_dir(data_root: Path, experiment_name: str, experiment_id: str | None):
    """Resolve an existing experiment or create a uniquely identified directory and report whether it is new."""
    data_root = Path(data_root)
    if experiment_id:
        directory = data_root / f'{experiment_name}__{experiment_id}'
        if not (directory / 'experiment.json').is_file():
            raise FileNotFoundError(f'Experiment {experiment_name}__{experiment_id} does not exist in {data_root}')
        return directory, experiment_id, False
    experiment_id = uuid4().hex[:12]
    directory = data_root / f'{experiment_name}__{experiment_id}'
    directory.mkdir(parents=True, exist_ok=False)      # never overwrite an experiment of the same name
    return directory, experiment_id, True


def new_run_dir(experiment_dir: Path, task_name: str, mode: str, seed: int):
    """Create a run directory beneath the experiment and return its layout and unique identifier."""
    run_id = uuid4().hex
    directory = Path(experiment_dir) / 'runs' / task_name / f'{mode}__seed{seed}__{run_id[:12]}'
    directory.mkdir(parents=True, exist_ok=False)
    return RunLayout(directory), run_id


def code_provenance():
    """Collect repository revision, worktree state, and optimizer-source identity without refreshing the Git index."""
    root = repo_root()

    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=20,
                                  check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    # --no-optional-locks: a plain `git status` may take .git/index.lock and rewrite the index to refresh its stat cache -
    # on every run start, in a working tree and index that several sessions share. The answer is the same without it.
    commit, status = git('rev-parse', 'HEAD'), git('--no-optional-locks', 'status', '--porcelain')
    try:
        from analog_optimizer.training.sac import source_digest
        optimizer_digest = source_digest()
    except Exception:                                    # pragma: no cover - torch missing
        optimizer_digest = None
    return dict(git_commit=commit or 'unknown', git_branch=git('rev-parse', '--abbrev-ref', 'HEAD') or 'unknown',
                git_dirty=None if status is None else bool(status),
                git_dirty_paths=None if status is None else len(status.splitlines()),
                analog_optimizer_source_sha256=optimizer_digest, workbench_version=__version__)


def environment_versions():
    """Record interpreter, host, and dependency versions, marking unavailable dependencies explicitly."""
    versions = dict(python=sys.version.split()[0], platform=platform.platform(), host=socket.gethostname(),
                    environment=environment_label(), executable=sys.executable, pid=os.getpid())
    for module in ('torch', 'torch_geometric', 'numpy', 'pyarrow', 'pydantic', 'networkx'):
        try:
            versions[module] = str(__import__(module).__version__)
        except Exception:
            versions[module] = 'unavailable'
    return versions


def build_artifact_manifest(layout: RunLayout, *, run_id, final: bool, dataset_status=None, notes=None):
    """List every file with relative path, purpose, format, size, checksum and write status."""
    entries = []
    flushed = set()
    for flush in _flushes(layout):
        flushed.update(f'data/{table}/{name}' for table, name in flush['parts'].items())
    paths = []
    for directory, dirs, files in os.walk(layout.run_dir):
        base = Path(directory)
        if base == layout.run_dir:
            dirs[:] = [name for name in dirs if name != 'work']
        paths.extend(base / name for name in files)
    # Prune simulator scratch before descending, then stat only retained files, once each. rglob visited every work
    # directory and is_file stat'ed all its files before they were excluded; retained files were stat'ed twice.
    for path in sorted(paths):
        relative = path.relative_to(layout.run_dir).as_posix()
        top = relative.split('/')[0]
        if TEMP_MARKER in path.name or top in ('work',) or relative == 'artifact_manifest.json':
            continue
        if relative.startswith('control/') and path.name.endswith('.lock'):
            continue
        status = 'final' if final else 'pending'
        if relative.startswith('data/') and relative.endswith('.parquet'):
            status = 'final' if relative in flushed else 'quarantined_unlisted_part'
        if relative.startswith('data/_journal/') and not final:
            status = 'pending'
        # A checkpoint carries its own per-file SHA-256 in its metadata.json (checkpoints.py), and a save point grows
        # with the replay buffer: re-hashing all of them at every run end read hundreds of megabytes twice over on the
        # 9p mount. They are listed with their size and cite their own checksums instead (review of 2026-09-23).
        own_checksum = top == 'checkpoints' and path.name != 'metadata.json'
        try:
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                continue
            entries.append(dict(path=relative, purpose=PURPOSES.get(top, PURPOSES.get(relative, 'run file')),
                                format=path.suffix.lstrip('.') or 'none', bytes=info.st_size,
                                sha256=None if own_checksum else (sha256_file(path) if final or status == 'final' else None),
                                checksum_in=f'checkpoints/{relative.split("/")[1]}/metadata.json' if own_checksum else None,
                                write_status=status))
        except OSError:
            continue
    rows = dataset_status['rows'] if dataset_status else None
    manifest = dict(layout_version=OUTPUT_LAYOUT_VERSION, run_id=run_id, generated_utc=utcnow().isoformat(),
                    final=final, relative_to='run directory (portable)', table_rows=rows,
                    total_bytes=sum(e['bytes'] for e in entries), files=entries, notes=notes or [],
                    original_environment=dict(run_dir=str(layout.run_dir), host=socket.gethostname(),
                                              environment=environment_label()))
    write_json(layout.artifact_manifest, manifest)
    return manifest


def _flushes(layout):
    return read_jsonl(layout.data / '_journal' / 'flushes.jsonl')


def run_bytes(layout: RunLayout) -> int:
    return directory_bytes(layout.run_dir)


def _subfolders(path, *, experiments=False) -> list[str]:
    """The folders in `path` as pathlib's glob `*` (or `*__*`) matched them - hidden names included; [] when `path` is
    no folder."""
    try:
        with os.scandir(path) as entries:
            return [e.path for e in entries if ('__' in e.name or not experiments) and e.is_dir()]
    except (FileNotFoundError, NotADirectoryError):
        return []


def find_runs(data_root, *, manifest=True) -> list[Path]:
    """Every run directory (has run_manifest.json) under a data root: <experiment with '__'>/runs/<task>/<run>.

    Walked with os.scandir rather than glob (record 7.274): on the 9p-mounted D: drive each file operation costs
    milliseconds, and glob also stat'ed runs/ and every run's manifest. `manifest=False` leaves out that last check, for a
    caller that reads the manifest anyway and skips a folder without one (runs.list_runs)."""
    found = []
    for experiment in _subfolders(data_root, experiments=True):
        for task in _subfolders(os.path.join(experiment, 'runs')):
            found += [Path(run) for run in _subfolders(task) if not manifest or os.path.isfile(os.path.join(run, 'run_manifest.json'))]
    return sorted(found)


def read_run(run_dir, *, status=True) -> dict:
    """`status=False` leaves status.json out, for a caller that reads it through runs.run_status (which adds the lock
    check) anyway: the run list read every status file twice."""
    layout = RunLayout(Path(run_dir))
    info = dict(run_dir=str(layout.run_dir), manifest=read_json(layout.manifest, default={}),
                summary=read_json(layout.summary, default={}))
    if status:
        info['status'] = read_json(layout.status, default={})
    return info
