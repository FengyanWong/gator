"""Record 7.278: the contract a learner of the page's configuration would have (runs.learner_contract) is kept for the
inspection of a saved model (POST /api/runs/model), by everything it is made of except the experiment - building it
meant five networks and, inside SACLearner.contract(), hashing every optimizer source file on the slow D: drive, 0.35
to 1.4 s per check. A start builds it anew. These tests pin what is kept, what is not, and that a kept answer is the
built one."""
import pytest

from analog_optimizer.training import sac
from gator_workbench import checkpoints as ckpt, modes, run_index, runs, schema, tasks
from gator_workbench.compile import compile_task
from helpers import SMALL_NET, make_config


@pytest.fixture
def builds(monkeypatch):
    """Counts the learners built; the kept contracts start empty; the source digest is a constant (the real one hashes
    the package, 0.4 s on the D: drive)."""
    built, original = [], modes._new_learner
    monkeypatch.setattr(modes, '_new_learner', lambda *args, **kwargs: built.append(1) or original(*args, **kwargs))
    monkeypatch.setattr(runs, '_CONTRACTS', {})
    monkeypatch.setattr(run_index, 'current_source_digest', lambda max_age=30.0: 'digest-of-now')
    monkeypatch.setattr(sac, 'source_digest', lambda: 'digest-of-now')
    return built


def contract_of(config, *, cached):
    """Compile a circuit and return its learner contract with the requested cache setting."""
    task = tasks.load_task(config.circuit)
    config = runs.with_circuit_content(config, task)
    task_hash = schema.task_definition_hash(config)
    compiled = compile_task(config, task.base_graph)
    return runs.learner_contract(config, task, task_hash, compiled.spec_schema, None, cached=cached)


def wider(raw):
    raw['parameters'][0]['upper'] = raw['parameters'][0]['upper'] * 1.5


def test_the_kept_contract_is_the_built_one(tmp_path, builds):
    config = make_config(tmp_path)
    built = contract_of(config, cached=False)
    kept, again = contract_of(config, cached=True), contract_of(config, cached=True)
    assert kept == built == again
    assert len(builds) == 2                                  # the start, and the first inspection; the second was kept


def test_an_edited_row_keeps_the_contract_and_fills_in_its_experiment(tmp_path, builds):
    first = contract_of(make_config(tmp_path), cached=True)
    edited = make_config(tmp_path, mutate=wider)
    second = contract_of(edited, cached=True)
    assert len(builds) == 1                                  # the same network, settings, specs and component list
    assert second['experiment_sha256'] != first['experiment_sha256']      # the task hash changed: this call's experiment
    assert second == contract_of(edited, cached=False)       # and the kept answer is what a built learner says


def test_other_settings_are_another_contract(tmp_path, builds, monkeypatch):
    contract_of(make_config(tmp_path), cached=True)
    contract_of(make_config(tmp_path, run=dict(network=dict(SMALL_NET, hidden_dim=SMALL_NET['hidden_dim'] * 2))), cached=True)
    contract_of(make_config(tmp_path, advanced=dict(gamma=0.5)), cached=True)
    monkeypatch.setattr(run_index, 'current_source_digest', lambda max_age=30.0: 'the-package-changed')
    contract_of(make_config(tmp_path), cached=True)
    assert len(builds) == 4


def test_a_start_builds_the_learner_every_time(tmp_path, builds):
    config = make_config(tmp_path)
    contract_of(config, cached=False)
    contract_of(config, cached=False)
    assert len(builds) == 2 and runs._CONTRACTS == {}


def test_the_kept_contracts_are_bounded(tmp_path, builds, monkeypatch):
    monkeypatch.setattr(runs, 'CONTRACT_CACHE_MAX', 2)
    for gamma in (0.1, 0.2, 0.3):
        contract_of(make_config(tmp_path, advanced=dict(gamma=gamma)), cached=True)
    assert len(runs._CONTRACTS) == 2 and len(builds) == 3
    contract_of(make_config(tmp_path, advanced=dict(gamma=0.1)), cached=True)         # the oldest went: built again
    assert len(builds) == 4


def test_a_kept_contract_is_not_shared_with_its_callers(tmp_path, builds):
    config = make_config(tmp_path)
    first = contract_of(config, cached=True)
    first['feature_schema'] = 'changed by a caller'
    assert contract_of(config, cached=True)['feature_schema'] != 'changed by a caller'


def test_experiment_fields_are_the_contract_summary_fields(tmp_path):
    experiment = dict(origin='synthetic', split='train', designs=[dict(task_key='t')])
    learner = modes._new_learner(experiment, modes.model_config_from(schema.NetworkConfig(**SMALL_NET)),
                                 modes.sac_config_from(make_config(tmp_path).run.advanced), None)
    summary = ckpt.contract_summary(learner)
    assert ckpt.experiment_fields(experiment) == dict(origin=summary['origin'], experiment_sha256=summary['experiment_sha256'])
