"""No-call checks of real task contracts and serialization of recorded REAL states. The two checks built on the OTA7 task
(its starter's hash identity, its corner deck) left with it on 2026-09-30 (record 7.128)."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pyarrow as pa
import pytest

from gator_workbench.schema import WorkbenchConfig
from gator_workbench.storage.tables import arrow_schema, normalize_row
from gator_workbench.trajectory import StateEncoder
from research_support import real_transition   # Actual M6 measurements, no simulator implementation.

ROOT = Path(__file__).resolve().parents[1]
# Every test here reads recorded REAL evidence (artifacts/ is not in git); skipped where it is absent.
pytestmark = pytest.mark.requires_evidence('artifacts/local/reward-v2-real/20260926-implementation-01/baseline.json',
                                           'artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649')


def baseline():
    """Read the local reward baseline evidence used by compatibility assertions."""
    return json.loads((ROOT / 'artifacts/local/reward-v2-real/20260926-implementation-01/baseline.json').read_text())


def robust_config():
    """Build a bounded corner configuration with worst-spec reward compression and operating points enabled."""
    raw = deepcopy(baseline()['config'])
    raw['run'].update(max_spectre_launches=42, max_retries=0,
                      reward=dict(violation_shape='compressed', worst_spec_share=.5),
                      conditions=dict(policy='always', corners=['ss_hot_low', 'ff_cold_high', 'fs_nominal', 'sf_nominal']))
    raw['run']['network']['operating_points'] = True
    return WorkbenchConfig.model_validate(raw)


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
    # Follow the scheduler's delegate: the live commit branch must resolve json in its own module. Since the readability
    # refactor the serializing step is a helper of `commit`, so the name is looked up in that module, not in `commit`.
    phase = inspect.getclosurevars(RunEngine._commit).globals['engine_commit']
    serializer = vars(phase)['json']
    rows = [asdict(row) for row in real_transition.next_observation.condition_results]
    serialized = serializer.dumps(rows)
    assert json.loads(serialized) == rows
