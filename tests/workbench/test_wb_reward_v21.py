"""Reward v2.1 workbench contracts; no physical calls or backend sessions."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gator_workbench import corner_check, reward_diagnostics, tasks
from gator_workbench.compile import build_specs, normalization_scale, training_conditions
from gator_workbench.modes import sac_config_from
from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash, editor_columns
from gator_workbench.reward_diagnostics import steering, VERDICT
import json
import math
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from gator_workbench.storage.dataset import DatasetReader
from helpers import execute, make_config, workbench_app


def ota(**run):
    """A configuration of the tests' MOCK stand-in (the OTA5). These contracts were first written on real:gpdk045_ota7;
    it was removed on 2026-09-30 (record 7.128) with its corner training and the tests that needed that."""
    return WorkbenchConfig.model_validate({**tasks.starter_config('synthetic:gpdk045_ota5'),
                                           'run': dict(max_evaluations=10, **run)})


def test_legacy_defaults_keep_exact_pinned_hashes():
    c = ota()
    # Pinned with the output defaults of then; record 7.280 made them a save point every 200 evaluations and the tables
    # every 64. A configuration saved earlier states 50 and 16 and keeps its hash, which is what is pinned here.
    c = c.model_copy(update=dict(output=c.output.model_copy(update=dict(checkpoint_every_evaluations=50, flush_every_evaluations=16))))
    # And record 7.294 turned run.advanced.update_after_dispatch on by default: a configuration of then ran with it off.
    c = c.model_copy(update=dict(run=c.run.model_copy(update=dict(advanced=c.run.advanced.model_copy(update=dict(update_after_dispatch=False))))))
    assert config_hash(c) == 'a32dbd027a6769bc1d28ca48d4f55fb430e77be9b097fff3f3dce5a80785b9d7'       # pinned on the stand-in
    assert task_definition_hash(c) == '5f181ef30c4ba6b5a1663871f07d48c9ed976334b6b8babd9870a7157c8a978a'   # (7.128)
    assert c.run.reward.violation_shape == 'capped' and c.run.advanced.alpha_learning_rate is None
    legacy = c.model_dump(mode='json')
    legacy['run']['reward'].pop('nominal_gate_band')
    legacy['run']['reward'].pop('objective_shape')
    legacy['run']['advanced'].pop('alpha_learning_rate')
    for row in legacy['targets']:
        row.pop('missing_is_failure'); row.pop('margin_sides')
    assert config_hash(legacy) == config_hash(c)
    legacy['run']['reward']['worst_spec_share'] = .4
    assert config_hash(legacy) == config_hash(WorkbenchConfig.model_validate(legacy))


@pytest.mark.parametrize('field,value', [('nominal_gate_band', 0.), ('nominal_gate_band', 1.), ('objective_shape', 'bad')])
def test_reward_settings_reject_invalid_values(field, value):
    with pytest.raises(ValidationError):
        ota(reward={field: value})


@pytest.mark.parametrize('rate', [0, -1, float('inf')])
def test_alpha_rate_requires_finite_positive_value(rate):
    with pytest.raises(ValidationError):
        ota(advanced=dict(alpha_learning_rate=rate))


def test_new_fields_change_contracts_and_compile():
    c = ota(max_spectre_launches=20, reward=dict(nominal_gate_band=.4, objective_shape='compressed'),
            advanced=dict(alpha_learning_rate=.003))
    c.targets[0].missing_is_failure = True
    c.targets[0].margin_sides = 'lower'
    specs, targets, _ = build_specs(c)
    assert specs[0].margin_sides == targets[0]['margin_sides'] == 'lower'
    # Since 2026-10-10 the optimizer counts a missing value as failed on EVERY hard spec (its own default): a row's stored
    # switch is not passed on - the same specs whatever it says - and it stays in the rows and their hashes.
    assert all(s.missing_is_failure for s in specs)
    c.targets[0].missing_is_failure = False
    assert build_specs(c)[0] == specs and all(s.missing_is_failure for s in build_specs(ota())[0])
    c.targets[0].missing_is_failure = True
    assert training_conditions(c) == ()                                          # no task trains at corners (7.128)
    assert sac_config_from(c.run.advanced).alpha_learning_rate == .003
    assert config_hash(c) != config_hash(ota()) and task_definition_hash(c) != task_definition_hash(ota())
    columns = {row['name']: row for row in editor_columns('targets')}
    assert columns['margin_sides']['advanced'] and not columns['margin_sides']['hidden']
    assert columns['missing_is_failure']['hidden'] and not columns['missing_is_failure']['advanced']    # no row switch any more


def test_saved_empty_scale_retains_threshold_rule():
    c = ota()
    c.targets[0].normalization_scale = None
    assert normalization_scale(c.targets[0]) == abs(c.targets[0].lower)
    assert c.targets[0].normalization_scale is None


def test_no_task_trains_at_corners_now():
    for key in ('real:gpdk045_ota7', 'synthetic:gpdk045_ota5', 'ngspice:ota5_level1', 'real:mscr_ota7t'):
        assert tasks.training_capabilities(key) == dict(corners=False, policies=['off'])


def test_steering_uses_last_50_scored_in_completion_order():
    rows = [dict(completion_index=i, reward=float(i)) for i in range(60)]
    rows += [dict(completion_index=61, reward=None), dict(completion_index=62, reward=float('nan'))]
    check = steering(rows[::-1], [dict(alpha=2., mean_log_prob=-30.)])
    assert check['scored_designs'] == 50
    assert check['reward_spread'] == pytest.approx(39.2)
    assert check['exploration_bonus'] == 60
    assert check['verdict'] == VERDICT
    assert steering(rows, [dict(alpha=.01, mean_log_prob=-1)])['verdict'] is None


def test_steering_missing_latest_update_does_not_use_stale_bonus():
    assert steering([], []) == dict(scored_designs=0, reward_spread=None, exploration_bonus=None, verdict=None)
    check = steering([dict(reward=0.)], [dict(alpha=.2, mean_log_prob=-2), dict(alpha=None)])
    assert check['reward_spread'] is None and check['exploration_bonus'] is None and check['verdict'] is None


def test_readiness_exposes_nonblocking_reachability_warning():
    from gator_workbench.readiness import build
    result = build(ota().model_dump(mode='json'), validation=dict(blocks_run=False, issues=[dict(
        level='warning', code='corner_reachability', path='run.conditions', message='The reference misses gain. Use Corner check.')]))
    item = next(i for i in result['items'] if i['id'] == 'corner_reachability')
    assert item['status'] == 'warning' and 'reference misses' in item['detail']


def test_corner_margin_side_does_not_change_failure_grading():
    from analog_optimizer.backends.backend import SimulationStatus
    from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
    target = dict(metric_id='power', lower=0., upper=10., scale=1., active=True, hard=True, unit='W', margin_sides='upper')
    assert corner_check._margin(target, 1.) > corner_check._margin(target, 5.)
    evaluator = SpecificationEvaluator([MetricSpec('power', 'W', 'range', 1., lower=0., upper=10., margin_sides='upper')])
    result = SimpleNamespace(metrics={'power': -1.}, metric_units={'power': 'W'}, metric_validity={'power': True},
                             status=SimulationStatus.OK, candidate_evaluated=True)
    state, evaluation, failing = corner_check.grade(result, evaluator, [target])
    assert state == 'failed' and not evaluation.success and failing[0]['violation'] == 1


def complete(table, rows):
    """`rows` as a part the reader accepts: every column the table declares - a value the test gives is kept, a required
    column it leaves out gets a neutral value of its type (DatasetReader may refuse a part that lacks one), anything else
    is empty. A column the table does not declare is an error of the test, not dropped quietly."""
    from datetime import datetime, timezone
    from gator_workbench.storage.tables import arrow_schema
    schema = arrow_schema(table)
    # A value the test leaves empty on purpose (a missing diagnostic) keeps its column, marked as allowed to be empty.
    schema = pa.schema([f.with_nullable(True) if any(f.name in row and row[f.name] is None for row in rows) else f
                        for f in schema])
    unknown = {key for row in rows for key in row} - set(schema.names)
    assert not unknown, f'{table} declares no column {sorted(unknown)}'

    def neutral(field):
        kind = field.type
        return (None if field.nullable else False if pa.types.is_boolean(kind) else 0 if pa.types.is_integer(kind)
                else 0.0 if pa.types.is_floating(kind) else datetime(2026, 9, 29, tzinfo=timezone.utc)
                if pa.types.is_timestamp(kind) else [] if pa.types.is_list(kind) or pa.types.is_map(kind) else 'test')
    return pa.Table.from_pylist([{f.name: row[f.name] if f.name in row else neutral(f) for f in schema} for row in rows],
                                schema=schema)


def flush(data, rows_by_table):
    """One flush as RawDataset lists it: a part per table, then ONE journal record naming them."""
    journal = data / '_journal' / 'flushes.jsonl'
    records = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
    name = f'part-{len(records) + 1:06d}.parquet'
    parts, counts = {}, {}
    for table, rows in rows_by_table.items():
        (data / table).mkdir(parents=True, exist_ok=True)
        pq.write_table(complete(table, rows), data / table / name)
        parts[table], counts[table] = name, len(rows)
    last = (records[-1]['last_seq'] if records else 0) + max(counts.values())
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('a') as stream:
        stream.write(json.dumps(dict(flush_id=len(records) + 1, last_seq=last, parts=parts, rows=counts)) + '\n')


# ------------------------------------------------------------------------------------------------ A2 + B2: the steering check
def steering_as_before(run_dir):
    """reward_diagnostics.load as it was before the cache: the newest 64 rows, doubled until 50 are scored."""
    reader = DatasetReader(Path(run_dir) / 'data')
    total = reader.row_counts().get('evaluations', 0)
    limit = min(64, total)
    while True:
        rows = reader.tail('evaluations', limit, ['completion_index', 'dispatch_index', 'reward']).to_pylist()
        if sum(reward_diagnostics.is_finite_number(r.get('reward')) for r in rows) >= 50 or limit >= total:
            break
        limit = min(total, max(1, limit * 2))
    return reward_diagnostics.steering(rows, reader.tail('learner_updates', 1, ['alpha', 'mean_log_prob']).to_pylist())


def test_steering_is_kept_until_a_flush(tmp_path, monkeypatch):
    data, index = tmp_path / 'data', 0
    for part in range(12):
        rows = []
        for _ in range(16):
            index += 1
            finite = part % 3 != 1 and index % 5
            rows.append(dict(completion_index=index + (3 if index % 4 == 0 else 0), dispatch_index=index,
                             reward=(math.sin(index) if finite else None if index % 2 else float('nan'))))
        flush(data, dict(evaluations=rows, learner_updates=[dict(alpha=0.2, mean_log_prob=-1.0 - part)]))
    assert reward_diagnostics.load(tmp_path) == steering_as_before(tmp_path)
    reads = []
    real = pq.ParquetFile                                   # a part is read through its one open (record 7.286)
    monkeypatch.setattr(pq, 'ParquetFile', lambda *a, **k: reads.append(a[0]) or real(*a, **k))
    reward_diagnostics._STEERING.clear()
    answer = reward_diagnostics.load(tmp_path)
    assert answer['scored_designs'] == 50 and reads, 'read once after the flush'
    reads.clear()
    assert reward_diagnostics.load(tmp_path) == answer and reads == [], 'kept between polls'
    flush(data, dict(evaluations=[dict(completion_index=500, dispatch_index=500, reward=40.0)],
                     learner_updates=[dict(alpha=None, mean_log_prob=-1.0)]))
    changed = reward_diagnostics.load(tmp_path)
    assert changed != answer and changed == steering_as_before(tmp_path) and changed['exploration_bonus'] is None


def test_status_with_a_missing_data_part_still_answers(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=6)), tmp_path)
    assert state == 'completed'
    next((layout.data / 'evaluations').glob('part-*.parquet')).unlink()
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    response = client.get('/api/runs/status', params=dict(run_dir=str(layout.run_dir)))
    assert response.status_code == 200 and response.json()['steering'] is None
    assert response.json()['state'] == 'completed'
