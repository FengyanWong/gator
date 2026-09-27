"""Local provenance report for the license-blocked reward-v2 implementation.

Does not execute tests, simulations or browser actions; reads their saved evidence.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from analog_optimizer.training.sac import source_digest
from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash
from gator_workbench.storage.atomic import write_json
from gator_workbench.tasks import real_starter_config

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/local/reward-v2-real/20260926-implementation-01'
QUALIFICATION = ROOT / 'artifacts/local/reward-v2-real/20260926-qualification-01'
SELECTED = ['tests/test_reward_v2.py', 'tests/test_reward_v2_real_data.py', 'tests/test_reward_v2_budget.py',
            'tests/test_reward_v2_workbench.py', 'tests/test_specs.py']
ALLOWED = {'backends/backend.py', 'backends/conditions.py', 'backends/gpdk045.py', 'backends/gpdk045_two_stage.py',
           'backends/native_preparation.py', 'backends/virtuoso_bridge.py', 'envs/sizing.py', 'graph/pyg_converter.py',
           'measurements/specs.py', 'models/encoders.py', 'models/inputs.py', 'recording/codec.py',
           'recording/store.py', 'recording/session.py', 'recording/checkpoint.py', 'recording/report.py',
           'training/parallel.py', 'training/replay.py', 'training/runner.py', 'training/sac.py'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    baseline = read(OUTPUT / 'baseline.json')
    identity = read(OUTPUT / 'identity-final-2.json')
    preflight = read(QUALIFICATION / 'preflight.json')
    assert not preflight['passed'] and preflight['physical_calls'] == 0
    source = ROOT / 'src/analog_optimizer'
    snapshot = Path(baseline['source_snapshot'])
    changed = [str(p.relative_to(source)) for p in sorted(source.rglob('*.py'))
               if not (snapshot / p.relative_to(source)).is_file() or
               p.read_bytes() != (snapshot / p.relative_to(source)).read_bytes()]
    removed = [str(p.relative_to(snapshot)) for p in snapshot.rglob('*.py') if not (source / p.relative_to(snapshot)).exists()]
    assert set(changed) <= ALLOWED and not removed
    protected = [name for name, digest in baseline['protected_hashes'].items() if sha(name) != digest]
    assert not protected
    config = WorkbenchConfig.model_validate(dict(real_starter_config('real:gpdk045_ota7'), run=dict(max_evaluations=10)))
    assert config_hash(config) == baseline['config_hash'] and task_definition_hash(config) == baseline['task_definition_hash']
    final_digest = source_digest()
    assert identity['source_digest'] == final_digest and identity['passed']
    suite = ET.parse(OUTPUT / 'software-tests-final.xml').getroot().find('testsuite')
    assert suite is not None and int(suite.attrib['failures']) == int(suite.attrib['errors']) == int(suite.attrib['skipped']) == 0
    parsed = list(source.rglob('*.py')) + list((ROOT / 'src/gator_workbench').rglob('*.py'))
    for path in parsed:
        ast.parse(path.read_text(), filename=str(path))
    unrun = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tests').rglob('test_*.py') if str(p.relative_to(ROOT)) not in SELECTED)
    checks = dict(kind='non-MOCK-selected-software-checks', selected={p: sha(ROOT / p) for p in SELECTED},
                  pytest=dict(suite.attrib), evidence=str(OUTPUT / 'software-tests-final.xml'),
                  unrun_legacy_test_files=unrun, python_files_parsed=len(parsed),
                  coverage_limit='No unfiltered full suite, fake simulator, physical run, or browser run',
                  typescript=dict(command='node.exe node_modules/typescript/bin/tsc --noEmit', passed=True,
                                  production_build=False, existing_windows_runtime=True))
    write_json(OUTPUT / 'software-check-manifest.json', checks)
    report = dict(origin='real', status='implementation_present_physical_acceptance_blocked',
        all_gates_passed=False, manifest_sha256=sha(QUALIFICATION / 'manifest.json'),
        frozen_qualification_manifest=str(QUALIFICATION / 'manifest.json'), preflight=preflight,
        manifest_requires_refreeze=True,
        refreeze_reason='No physical calls occurred. Subsequent offline integration fixes changed the source after preflight.',
        source=dict(before=baseline['source_digest'], after=final_digest, snapshot=str(snapshot),
                    optimizer_files_changed=changed, optimizer_files_removed=removed,
                    final_files={str(p.relative_to(ROOT)): sha(p) for p in parsed}),
        configuration=dict(default_real_config_hash=config_hash(config), default_real_task_hash=task_definition_hash(config),
                           hashes_unchanged=True, robust_configuration_sha256=sha(QUALIFICATION / 'configuration.json')),
        dependencies=baseline['dependencies'],
        protected_files=dict(checked=len(baseline['protected_hashes']), changed=protected),
        shared_tree=dict(head_before=baseline['head'], head_now=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), task_committed=False, task_pushed=False,
            note='Concurrent user-owned work changed HEAD and built dist (workbench records 7.90-7.93); not actions of this task.'),
        stages={name: dict(planned_maximum_calls=maximum, started_calls=0, completed_calls=0,
                           confirmed_calls=0, uncertain_calls=0, candidates=0, resets=0, transitions=0,
                           updates=0, wall_seconds=0., state='not_started_prerequisite_blocked')
                for name, maximum in [('A', 21), ('B', 43), ('C', 13)]},
        totals=dict(new_spectre_calls=0, candidate_evaluations=0, on_policy_transitions=0, on_policy_updates=0,
                    remaining_acceptance_ceiling=77, optional_999_call_study_started=False),
        restoration=dict(state='not_required_no_circuit_mutation', physical_snapshot_restore_verified=False),
        scope_blocker=dict(path='src/analog_optimizer/recording/reader.py', permission_requested=True, changed=False,
                           issue='Legacy overview recomputes nominal constraints; needs explicitly authorized v2 read-side aggregation'),
        reward_identity=identity, software=checks,
        gates=dict(
            A1=dict(status='passed_no_call', evidence=['identity-final-2.json', 'software-tests-final.xml']),
            A2=dict(status='passed_pure_arithmetic', evidence=['software-tests-final.xml']),
            A3=dict(status='blocked', reason='license_not_checkable; no Stage A execution'),
            A4=dict(status='blocked', reason='No Stage B run; historical real codec/replay/update tests passed'),
            A5=dict(status='partial', reason='Pure full-plan/global/crash ledger checks passed; Stage C and physical restoration unrun'),
            A6=dict(status='partial', reason='GT/RGCN/GATv2, op on/off, historical-real updates/exact next-update checks passed; no B-derived replay'),
            A7=dict(status='partial', reason='TypeScript passed; current-source scratch browser against new real runs unrun'),
            A8=dict(status='partial', reason='Source/default hashes/protected files audited; physical provenance unavailable')),
        remaining=['Resolve or explicitly acknowledge the unknown license gate before any Spectre launch',
                   'Authorize the limited recording/reader.py addition, then finish and test its robust overview',
                   'Refreeze the final source and stage execution drivers, then execute A, B and C in order',
                   'Stage A derived/re-exported corner comparisons and saved-PSF recomputation',
                   'Stage B workbench learning, pause/resume and six B-data replay checks',
                   'Stage C shared physical launch admission and each stage physical restoration',
                   'Current-source scratch API/browser check of settings, coverage, model facts and real tables',
                   'Failure/success branches not naturally observed must remain physical coverage gaps'],
        restrictions=dict(mock_used=False, user_backend_8765_touched=False, task_live_frontend_build=False,
                          fabricated_circuit_outputs=False))
    write_json(OUTPUT / 'acceptance-summary.json', report)
    print(json.dumps(dict(report=str(OUTPUT / 'acceptance-summary.json'), after_digest=final_digest,
                          optimizer_files_changed=len(changed), tests=suite.attrib['tests'],
                          physical_calls=0, all_gates_passed=False), indent=2))


if __name__ == '__main__':
    main()
