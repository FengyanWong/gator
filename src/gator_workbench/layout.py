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
import subprocess
import sys
from uuid import uuid4

from . import OUTPUT_LAYOUT_VERSION, __version__
from .paths import directory_bytes, environment_label, repo_root
from .storage.atomic import TEMP_MARKER, read_json, sha256_file, write_json
from .storage.dataset import utcnow

PURPOSES = {
    'run_manifest.json': 'Identity and provenance of the run',
    'effective_config.json': 'Exact validated configuration that was executed',
    'run_summary.json': 'Per-run research statistics',
    'artifact_manifest.json': 'This file list',
    'status.json': 'Live run-control status (not research data)',
    'input_snapshot': 'Circuit, netlist, parameter mapping and PDK reference the run started from',
    'data': 'Raw Parquet tables + write-ahead journal',
    'best_design': 'Best discovered circuit parameter sets and measurements (not a model)',
    'checkpoints': 'Model/training state; latest and best_policy pointers',
    'waveforms': 'Retained raw simulator output (never rendered)',
    'logs': 'events.jsonl and errors.jsonl',
    'exports': 'On-demand derived CSV copies of raw tables',
    'control': 'Run-control commands and the single-writer lock',
    'work': 'Registered temporary simulator working directories',
}


@dataclass(frozen=True)
class RunLayout:
    run_dir: Path

    def __post_init__(self):
        object.__setattr__(self, 'run_dir', Path(self.run_dir))

    def __getattr__(self, name):
        table = dict(manifest='run_manifest.json', effective_config='effective_config.json',
                     summary='run_summary.json', artifact_manifest='artifact_manifest.json', status='status.json',
                     input_snapshot='input_snapshot', data='data', best_design='best_design',
                     checkpoints='checkpoints', waveforms='waveforms', logs='logs', exports='exports',
                     control='control', work='work')
        if name in table:
            return self.run_dir / table[name]
        raise AttributeError(name)

    @property
    def experiment_dir(self) -> Path:
        return self.run_dir.parents[2]

    def create(self):
        for name in ('input_snapshot', 'data', 'best_design', 'checkpoints', 'waveforms', 'logs', 'exports',
                     'control', 'work'):
            getattr(self, name).mkdir(parents=True, exist_ok=True)

    def subpaths(self):
        return dict(run=str(self.run_dir), raw_data=str(self.data), checkpoints=str(self.checkpoints),
                    replay='checkpoints/<checkpoint_id>/training_state.pt (embedded) + replay_buffer/manifest.json',
                    best_designs=str(self.best_design), csv_exports=str(self.exports),
                    aggregates=str(self.experiment_dir / 'aggregates'), waveforms=str(self.waveforms),
                    logs=str(self.logs), simulator_work=str(self.work))


def new_experiment_dir(data_root: Path, experiment_name: str, experiment_id: str | None):
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
    run_id = uuid4().hex
    directory = Path(experiment_dir) / 'runs' / task_name / f'{mode}__seed{seed}__{run_id[:12]}'
    directory.mkdir(parents=True, exist_ok=False)
    return RunLayout(directory), run_id


def code_provenance():
    root = repo_root()

    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=20,
                                  check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    commit, status = git('rev-parse', 'HEAD'), git('status', '--porcelain')
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
    for path in sorted(p for p in layout.run_dir.rglob('*') if p.is_file()):
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
            entries.append(dict(path=relative, purpose=PURPOSES.get(top, PURPOSES.get(relative, 'run file')),
                                format=path.suffix.lstrip('.') or 'none', bytes=path.stat().st_size,
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
    from .storage.atomic import read_jsonl
    return read_jsonl(layout.data / '_journal' / 'flushes.jsonl')


def run_bytes(layout: RunLayout) -> int:
    return directory_bytes(layout.run_dir)


def find_runs(data_root) -> list[Path]:
    """Every run directory (has run_manifest.json) under a data root."""
    data_root = Path(data_root)
    if not data_root.is_dir():
        return []
    return sorted(p.parent for p in data_root.glob('*__*/runs/*/*/run_manifest.json'))


def read_run(run_dir) -> dict:
    layout = RunLayout(Path(run_dir))
    return dict(run_dir=str(layout.run_dir), manifest=read_json(layout.manifest, default={}),
                summary=read_json(layout.summary, default={}), status=read_json(layout.status, default={}))
