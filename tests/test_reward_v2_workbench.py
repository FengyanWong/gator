"""No-call checks of real task contracts and serialization of recorded REAL states."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pyarrow as pa
import pytest

from gator_workbench.compile import compile_task, training_conditions
from gator_workbench.modes import runtime_options
from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash
from gator_workbench.storage.tables import arrow_schema, normalize_row
from gator_workbench.tasks import _verified_profile, real_starter_config
from gator_workbench.trajectory import StateEncoder
from test_reward_v2_real_data import real_transition  # Actual M6 measurements, no simulator implementation.

ROOT = Path(__file__).resolve().parents[1]


def baseline():
    return json.loads((ROOT / 'artifacts/local/reward-v2-real/20260926-implementation-01/baseline.json').read_text())


def robust_config():
    raw = deepcopy(baseline()['config'])
    raw['run'].update(max_spectre_launches=42, max_retries=0,
                      reward=dict(violation_shape='compressed', worst_spec_share=.5),
                      conditions=dict(policy='always', corners=['ss_hot_low', 'ff_cold_high', 'fs_nominal', 'sf_nominal']))
    raw['run']['network']['operating_points'] = True
    return WorkbenchConfig.model_validate(raw)


def test_default_real_task_hash_identity():
    original = baseline()
    config = WorkbenchConfig.model_validate(dict(real_starter_config('real:gpdk045_ota7'), run=dict(max_evaluations=10)))
    assert config_hash(config) == original['config_hash']
    assert task_definition_hash(config) == original['task_definition_hash']


def test_real_profile_plan_compile_and_deck_transform():
    config = robust_config()
    profile = _verified_profile('gpdk045_ota7')
    compiled = compile_task(config, profile.optimization_graph())
    runtime = runtime_options(config)
    assert len(runtime['feature_schema'].op_columns) == 12
    assert compiled.spec_schema.width == 21 * len(compiled.spec_schema.metrics) + 11
    assert runtime['reward_settings'].worst_spec_share == .5
    assert len(runtime['planned_conditions']) == 5
    exported = (ROOT / 'examples/circuits/gpdk045_ota7.scs').read_text()
    before = profile.parser.parse_text(exported)
    for condition in training_conditions(config):
        prepared = profile.structure_for_condition(exported, condition)
        parsed = profile.parser.parse_text(prepared)
        assert parsed.parameters['VDD']['dc'].value == condition.corner.supply_v
        for device, values in before.parameters.items():
            if device == 'VDD':
                continue
            assert values == parsed.parameters[device]
    # These are unsimulated deck transformations, not claimed electrical corner results.
    assert 'nominal_only' in asdict(compiled.specs[0])


@pytest.mark.parametrize('change', ['no_cap', 'retry', 'unsupported_profile', 'empty_corners'])
def test_invalid_real_training_plan_refused_before_any_backend(change):
    raw = robust_config().model_dump(mode='json')
    if change == 'no_cap':
        raw['run']['max_spectre_launches'] = None
    elif change == 'retry':
        raw['run']['max_retries'] = 1
    elif change == 'unsupported_profile':
        raw['circuit']['task_id'] = 'real:gpdk045_ldo'
    else:
        raw['run']['conditions']['corners'] = []
    with pytest.raises(ValueError):
        WorkbenchConfig.model_validate(raw)


def test_recorded_real_state_roundtrip_through_workbench_arrow(real_transition, tmp_path):
    from analog_optimizer.recording import codec
    from analog_optimizer.envs.sizing import Observation
    observation = real_transition.next_observation
    encoder = StateEncoder(tmp_path, task_id='recorded-real-m6', graph=real_transition.observation.graph,
                           specs=observation.specs, feature_schema_version='test-recorded-schema',
                           spec_schema_version='spec-input-v2')
    _, row = encoder.encode(observation, run_id='recorded-data-check-no-new-run')
    table = pa.Table.from_pylist([normalize_row('states', row)], schema=arrow_schema('states'))
    stored = table.to_pylist()[0]
    fields = codec.untree(json.loads(stored['observation_fields_json']))
    graph = codec.untree(codec.patched(encoder.template, codec.untree(json.loads(stored['graph_patch_json']))))
    restored = Observation(graph=graph, specs=encoder.specs, **fields)
    assert codec.raw(restored) == codec.raw(observation)
    assert restored.evaluation == observation.evaluation


def test_live_commit_condition_json_dependency(real_transition):
    import inspect
    from gator_workbench.engine import RunEngine
    # The live commit branch must resolve json in its own module, not in its caller.
    serializer = inspect.getclosurevars(RunEngine._commit).globals['json']
    rows = [asdict(row) for row in real_transition.next_observation.condition_results]
    serialized = serializer.dumps(rows)
    assert json.loads(serialized) == rows
