"""Local-only reward-v2 baseline; never connects to a backend or copies credentials."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import site
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = str(output / 'settings')
    from analog_optimizer.training.sac import source_digest
    from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash
    from gator_workbench.tasks import real_bindings, real_starter_config, _binding_problem

    source = root / 'src' / 'analog_optimizer'
    snapshot = output / 'source' / 'analog_optimizer'
    shutil.copytree(source, snapshot, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    config = WorkbenchConfig.model_validate(dict(real_starter_config('real:gpdk045_ota7'),
                                                 run=dict(max_evaluations=10)))
    settings_path = root / 'configs/local/workbench/bridge_connection.json'
    settings = json.loads(settings_path.read_text()) if settings_path.is_file() else {}
    profiles = settings.get('profiles', {})
    bindings = []
    for identifier, profile in profiles.items():
        if profile.get('kind', 'virtuoso_ssh') not in ('virtuoso_ssh', 'virtuoso_local'):
            continue
        bound = real_bindings(profile, 'gpdk045_ota7')
        if profile.get('bridge_site_packages'):
            site.addsitedir(profile['bridge_site_packages'])
        required = ('env_file', 'library', 'creation_receipt', 'model_file', 'reference_measurements')
        missing = [key for key in required if not bound.get(key)]
        problem = 'missing binding fields: ' + ', '.join(missing) if missing else _binding_problem('gpdk045_ota7', bound)
        evidence = {}
        for key in ('creation_receipt', 'reference_measurements'):
            path = Path(bound[key]) if bound.get(key) else None
            if path and path.is_file():
                evidence[key] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        # A consistency error may contain local paths, but never raw settings or env-file contents.
        bindings.append(dict(profile_id=identifier, consistent=problem is None, problem=problem, evidence=evidence))
    protected = list((root / 'configs').glob('*.json')) + list((root / 'examples').glob('*.py'))
    protected += list((root / 'tests/fixtures/synthetic').glob('*.scs'))
    baseline = dict(
        kind='reward-v2-source-and-real-task-baseline', origin='real', physical_calls=0,
        source_digest=source_digest(), source_snapshot=str(snapshot),
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        dependencies={name: importlib.metadata.version(name) for name in ('torch', 'torch-geometric', 'virtuoso-bridge')},
        config=config.model_dump(mode='json'), config_hash=config_hash(config), task_definition_hash=task_definition_hash(config),
        real_bindings=bindings, protected_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected})
    (output / 'baseline.json').write_text(json.dumps(baseline, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: baseline[key] for key in ('source_digest', 'config_hash', 'task_definition_hash', 'dependencies', 'real_bindings')}, indent=2))
    print(f'Baseline: {output / "baseline.json"}')


if __name__ == '__main__':
    main()
