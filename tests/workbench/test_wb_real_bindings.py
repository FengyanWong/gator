"""Per-circuit bindings of a connection profile: a creation receipt and a baseline belong to ONE circuit.
Local files only; nothing here contacts a bridge or starts a simulation."""
import json
from pathlib import Path

import pytest

from gator_workbench import tasks
from gator_workbench.paths import local_settings_dir
from gator_workbench.schema import CircuitReference
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module

REPO = Path(__file__).resolve().parents[2]
DESIGNS = {name: json.loads((REPO / info['design']).read_text()) for name, info in tasks.REAL_PROFILES.items()}


def receipt(tmp_path, name, **overrides):
    design = DESIGNS[name]
    path = tmp_path / f'{name}-creation.json'
    path.write_text(json.dumps(dict(dict(library='MY_LIB', core_cell=design['core_cell'],
                                         testbench_cell=design['testbench_cell'], config=design), **overrides)))
    return str(path)


def baseline(tmp_path, name, origin='real', metrics=None):
    path = tmp_path / f'{name}-measurements.json'
    path.write_text(json.dumps(dict(origin=origin, metrics=dict(supply_power_w=1e-6) if metrics is None else metrics)))
    return str(path)


def write_profile(**profile):
    target = local_settings_dir() / 'bridge_connection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(dict(env_file='/x/.env', library='MY_LIB',
                                                                               model_file='/pdk/model.scs'), **profile)))))


def test_each_circuit_uses_its_own_receipt_and_baseline(tmp_path):
    circuits = {name: dict(creation_receipt=receipt(tmp_path, name), reference_measurements=baseline(tmp_path, name))
                for name in ('gpdk045_ota5', 'gpdk045_ldo')}
    write_profile(circuits=circuits)
    bound = tasks.real_bindings(tasks._profile_settings('lab')[1], 'gpdk045_ldo')
    assert bound['creation_receipt'] == circuits['gpdk045_ldo']['creation_receipt'] and 'circuits' not in bound
    assert bound['library'] == 'MY_LIB' and bound['model_file'] == '/pdk/model.scs'          # the link is shared
    assert tasks.real_backend_blocker('lab', 'gpdk045_ota5') is None and tasks.real_backend_blocker('lab', 'gpdk045_ldo') is None
    listed = {t['task_key']: t for t in tasks.list_tasks()}
    assert listed['real:gpdk045_ota5']['available'] and listed['real:gpdk045_ldo']['available']
    assert not listed['real:gpdk045_vco']['available'] and 'real:gpdk045_vco' in listed['real:gpdk045_vco']['blocker']


def test_a_connection_only_profile_says_which_circuit_keys_are_missing(tmp_path):
    write_profile()
    message = tasks.real_backend_blocker('lab', 'gpdk045_ota5')
    assert "['creation_receipt', 'reference_measurements'] for real:gpdk045_ota5" in message
    assert '"circuits": {"gpdk045_ota5"' in message
    with pytest.raises(tasks.TaskBlocked) as raised:
        tasks.load_task(CircuitReference(source='registered_task', task_id='real:gpdk045_ota5'), allow_real=True, profile_id='lab')
    assert 'gpdk045_ota5' in str(raised.value) and raised.value.contract['connection_file_keys']


def test_the_flat_single_circuit_form_still_works_but_never_binds_the_wrong_circuit(tmp_path):
    write_profile(creation_receipt=receipt(tmp_path, 'gpdk045_ota5'), reference_measurements=baseline(tmp_path, 'gpdk045_ota5'))
    assert tasks.real_backend_blocker('lab', 'gpdk045_ota5') is None
    wrong = tasks.real_backend_blocker('lab', 'gpdk045_ldo')                  # the opamp receipt must not reach the LDO
    assert 'core_cell' in wrong and DESIGNS['gpdk045_ota5']['core_cell'] in wrong and DESIGNS['gpdk045_ldo']['core_cell'] in wrong


@pytest.mark.parametrize('profile, fragment', [
    (lambda t: dict(circuits=dict(gpdk045_ota5=dict(creation_receipt=str(t / 'absent.json'),
                                                    reference_measurements=baseline(t, 'gpdk045_ota5')))), 'does not exist'),
    (lambda t: dict(circuits=dict(gpdk045_ota5=dict(creation_receipt=receipt(t, 'gpdk045_ota5', library='OTHER_LIB'),
                                                    reference_measurements=baseline(t, 'gpdk045_ota5')))), "library='OTHER_LIB'"),
    (lambda t: dict(circuits=dict(gpdk045_ota5=dict(creation_receipt=receipt(t, 'gpdk045_ota5'),
                                                    reference_measurements=baseline(t, 'gpdk045_ota5', origin='synthetic')))),
     'verified REAL baseline'),
    (lambda t: dict(circuits=dict(gpdk045_ota5=dict(creation_receipt=receipt(t, 'gpdk045_ota5'),
                                                    reference_measurements=baseline(t, 'gpdk045_ota5', metrics={})))),
     'verified REAL baseline'),
])
def test_inconsistent_bindings_block_before_anything_is_prepared(tmp_path, profile, fragment):
    write_profile(**profile(tmp_path))
    assert fragment in tasks.real_backend_blocker('lab', 'gpdk045_ota5')


def test_a_real_task_loads_for_viewing_but_cannot_execute_without_the_explicit_authorization(tmp_path):
    """Refusing to LOAD it made the authorization dialog unreachable (the UI learns "real" from the loaded circuit)."""
    write_profile(circuits=dict(gpdk045_ota5=dict(creation_receipt=receipt(tmp_path, 'gpdk045_ota5'),
                                                  reference_measurements=baseline(tmp_path, 'gpdk045_ota5'))))
    reference = CircuitReference(source='registered_task', task_id='real:gpdk045_ota5')
    shown = tasks.load_task(reference, allow_real=False, profile_id='lab')
    assert not shown.mock and shown.authorized is False and shown.base_graph.devices and shown.provided_metrics
    assert any('explicit authorization' in note for note in shown.notes)
    with pytest.raises(tasks.TaskBlocked, match='explicit user action'):
        shown.env_factory_builder(None, tmp_path, None)                     # the one thing it must never do
    assert tasks.load_task(reference, allow_real=True, profile_id='lab').authorized is True


def test_an_unauthorized_real_start_is_refused_before_anything_exists(tmp_path, monkeypatch):
    from gator_workbench import runs
    from helpers import make_config, roots_for
    config = make_config(tmp_path, run=dict(max_evaluations=6, connection_profile_id='lab'))
    runtime = tasks.load_task(config.circuit)
    runtime.origin = 'real'                                                 # a MOCK-evaluated task relabelled as real
    monkeypatch.setattr(runs, 'load_task', lambda circuit, allow_real=False, profile_id=None: runtime)
    before = sorted(path.name for path in tmp_path.iterdir())
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(config, roots_for(tmp_path), allow_real=False, monitor=None)
    assert refused.value.code == 'real_authorization_required' and 'explicit user action' in str(refused.value)
    assert refused.value.report['requested_max_evaluations'] == 6
    assert sorted(path.name for path in tmp_path.iterdir()) == before       # no run directory, no experiment, no gate probe
    assert runs.list_runs(roots_for(tmp_path), tmp_path) == []


def test_the_worker_refuses_a_real_run_that_was_not_authorized(tmp_path):
    """Third line of defence: a worker launched without --allow-real never reaches the engine."""
    source = (REPO / 'src/gator_workbench/worker.py').read_text()
    guard = source.index('if not task.mock and not args.allow_real')
    assert guard < source.index("if task.mock != manifest['mock']")          # checked right after loading, before any work
    assert 'profile_id=config.run.connection_profile_id' in source          # the gated profile, never silently the active one
