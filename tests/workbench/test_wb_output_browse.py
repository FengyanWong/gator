"""Restricted output-folder listings keep their visible order without per-child Path metadata reads."""
import os
from pathlib import Path

import pytest

from gator_workbench import paths


def previous_browse(roots, path=None):
    """Return the original path-based directory listing as a comparison oracle."""
    if path is None:
        return dict(path=None, parent=None,
                    entries=[dict(name=str(r), path=str(r), exists=r.exists()) for r in roots.roots])
    current = roots.resolve(path)
    entries = []
    if current.is_dir():
        for child in sorted(current.iterdir()):
            if child.is_dir() and not child.is_symlink() and not child.name.startswith('.'):
                entries.append(dict(name=child.name, path=str(child), exists=True))
    parent = str(current.parent) if roots.is_allowed(current.parent) else None
    return dict(path=str(current), parent=parent, entries=entries[:500])


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    """Provide one isolated output root without environment-defined allowed roots."""
    monkeypatch.delenv(paths.ENV_ALLOWED_ROOTS, raising=False)
    root = tmp_path / 'mock'
    root.mkdir()
    return root, paths.OutputRoots([root], include_default=False)


@pytest.mark.parametrize('count', [0, 5, 500, 503])
def test_listing_keeps_first_500_sorted_visible_directories(allowed, count):
    root, roots = allowed
    names = [f'folder-{i}' for i in range(count)] + ['B', 'b', 'μ-folder', 'a space']
    for name in reversed(names):
        (root / name).mkdir()
    for i in range(40):
        (root / f'file-{i}').write_bytes(b'synthetic')
    (root / '.hidden-directory').mkdir()
    (root / '.hidden-file').write_bytes(b'synthetic')
    answer = roots.browse(root)
    assert answer == previous_browse(roots, root)
    assert [row['name'] for row in answer['entries']] == sorted(names, key=Path)[:500]
    assert all(row['exists'] for row in answer['entries'])
    assert answer['parent'] is None


def test_links_and_special_files_are_not_offered(allowed, tmp_path):
    root, roots = allowed
    inside, outside = root / 'inside', tmp_path / 'outside'
    inside.mkdir(); outside.mkdir()
    (root / 'file').write_bytes(b'synthetic')
    for name, destination in [('inside-link', inside), ('outside-link', outside),
                              ('file-link', root / 'file'), ('broken-link', root / 'missing')]:
        (root / name).symlink_to(destination)
    os.mkfifo(root / 'pipe')
    assert roots.browse(root) == previous_browse(roots, root)
    assert [row['name'] for row in roots.browse(root)['entries']] == ['inside']
    # An explicitly selected link is still resolved and checked against the allowlist.
    assert roots.browse(root / 'inside-link') == roots.browse(inside)
    with pytest.raises(paths.PathNotAllowed):
        roots.browse(root / 'outside-link')


def test_roots_missing_file_parent_and_nul_behavior_are_unchanged(allowed, tmp_path):
    root, roots = allowed
    nested = root / 'nested'; nested.mkdir()
    file = root / 'file'; file.write_bytes(b'synthetic')
    for target in (None, nested, root / 'missing', file):
        assert roots.browse(target) == previous_browse(roots, target)
    assert roots.browse(nested)['parent'] == str(root)
    for target in (tmp_path, str(root) + '/bad\x00name'):
        with pytest.raises(paths.PathNotAllowed):
            roots.browse(target)


def test_child_path_stat_calls_are_avoided(allowed, monkeypatch):
    root, roots = allowed
    for name in ('a', 'b', 'c'):
        (root / name).mkdir()
    (root / 'file').write_bytes(b'synthetic')
    real_stat, reads = Path.stat, []

    def counted(path, *args, **kwargs):
        """Record metadata reads of direct children while preserving normal stat results."""
        if path.parent == root:
            reads.append(path.name)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', counted)
    expected = previous_browse(roots, root)
    assert len(reads) == 7  # one type check per child, plus one link check per directory
    reads.clear()
    assert roots.browse(root) == expected
    assert reads == []  # directory entries may still need filesystem fallback stats; these are explicit Path calls


def test_scan_failure_closes_iterator_and_propagates(allowed, monkeypatch):
    root, roots = allowed
    closed = []

    class BrokenScan:
        """A directory scan that fails during iteration and records closure."""
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def __iter__(self):
            raise OSError('synthetic listing failure')

    monkeypatch.setattr(paths.os, 'scandir', lambda path: BrokenScan())
    with pytest.raises(OSError, match='synthetic listing failure'):
        roots.browse(root)
    assert closed == [True]


def test_child_type_error_precedes_hidden_and_link_exclusion(allowed, monkeypatch):
    root, roots = allowed
    closed = []

    class InaccessibleEntry:
        """A hidden link whose target type check fails before link exclusion is allowed."""
        name = '.inaccessible-link'

        def is_dir(self, *, follow_symlinks=True):
            """Raise the configured target-access failure after checking link-following behavior."""
            assert follow_symlinks
            raise PermissionError('synthetic inaccessible target')

        def is_symlink(self):
            """Fail if link exclusion runs before the target type check."""
            pytest.fail('The failed type check precedes link exclusion')

    class Scan:
        """A scan yielding the inaccessible entry and recording context exit."""
        def __enter__(self):
            return iter([InaccessibleEntry()])

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(paths.os, 'scandir', lambda path: Scan())
    with pytest.raises(PermissionError, match='synthetic inaccessible target'):
        roots.browse(root)
    assert closed == [True]
