"""Explicit project provenance setup used by the command-line examples."""
from pathlib import Path

from .provenance import project_snapshot


def create_run(store, project_root, configuration, *, project_files=(), templates=None):
    root = Path(project_root).resolve()
    source_files = [str(p.relative_to(root)) for p in sorted((root / 'src').rglob('*.py'))]
    source_files += [str(p.relative_to(root)) for p in sorted((root / 'examples').glob('*.py'))]
    files = list(dict.fromkeys(['pyproject.toml', *source_files, *project_files]))
    snapshot = project_snapshot(root, files)
    snapshot_id = store.call('asset', 'project_snapshot', snapshot)
    template_id = store.call('asset', 'netlist_templates', templates or {})
    config = dict(configuration, schema_version='gator-recording-v1', project_snapshot_asset_id=snapshot_id,
                  netlist_templates_asset_id=template_id,
                  reproducibility='Requires original PDK/model paths, dependencies and Virtuoso/Spectre environment; '
                                  'PDK and license contents are not archived.')
    return store.call('run', config)
