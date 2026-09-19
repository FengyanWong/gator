"""Capture only explicitly selected project files; never crawl a PDK/install tree."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import subprocess


def fingerprint(path, *, version=None):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return dict(location=str(path.resolve()), version=version, sha256=digest.hexdigest(),
                bytes=path.stat().st_size)


def project_snapshot(root, files):
    """Explicit allowlist also covers untracked sources when Git is unavailable."""
    root = Path(root).resolve()
    contents = {}
    for name in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Snapshot file must belong to this project')
        if any(word in part.lower() for part in path.relative_to(root).parts
               for word in ('license', '.env', 'secret', 'credential', 'pdk', 'node_modules', 'site-packages')):
            raise ValueError('PDK, installed dependencies and credentials are not project snapshots')
        contents[str(path.relative_to(root))] = path.read_bytes()
    def git(*args):
        run = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
        return run.stdout.decode('utf8', errors='replace') if run.returncode == 0 else None
    commit = git('rev-parse', 'HEAD')
    paths = list(contents)
    return dict(git_commit=None if commit is None else commit.strip(),
                git_status='unavailable' if commit is None else git('status', '--porcelain', '--', *paths),
                project_diff=None if commit is None else git('diff', '--binary', 'HEAD', '--', *paths),
                files=contents, python=platform.python_version(),
                dependencies={d.metadata['Name']: d.version for d in importlib.metadata.distributions()})
