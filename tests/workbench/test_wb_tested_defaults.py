"""The defaults measured on 2026-10-05 (record 7.183): what static validation says about soft actor-critic values that do
not learn and about a budget below the point where learning starts, the Specs row whose limit is 0, and the settings a new
configuration starts with. MOCK only; the measurement itself is in artifacts/local/reviews/defaults-study-2026-10-05."""
import pytest

from gator_workbench import network_presets as presets, schema, tasks, validation
from gator_workbench.compile import normalization_scale
from helpers import make_config


def issues(config):
    runtime = tasks.load_task(config.circuit)
    report = validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
    return report, {i.code: i for i in report.issues}


def test_values_with_which_the_search_stays_random_are_named(tmp_path):
    report, found = issues(make_config(tmp_path))                       # the schema defaults: temperature 0.2, one update
    slow = found['sac_values_random_search']
    assert slow.level == 'warning' and slow.path == 'run.advanced' and not report.blocks_run
    assert '1 update per evaluation and a starting temperature of 0.2' in slow.message and 'under Advanced in the RL model window' in slow.message
    assert 'GATOR baseline' not in slow.message                         # deleted, record 7.191
    tested = {**presets.legacy_baseline()['advanced'], **presets.TESTED}
    assert 'sac_values_random_search' not in issues(make_config(tmp_path, advanced=tested))[1]
    # each of the two alone is still said, in its own words; the measured boundaries are 4 updates and 0.05
    assert issues(make_config(tmp_path, advanced=dict(tested, updates_per_transition=2)))[1][
        'sac_values_random_search'].message.startswith('With 2 updates per evaluation, soft actor-critic')
    assert issues(make_config(tmp_path, advanced=dict(tested, initial_alpha=0.2)))[1][
        'sac_values_random_search'].message.startswith('With a starting temperature of 0.2, soft actor-critic')
    assert 'sac_values_random_search' not in issues(make_config(tmp_path, advanced=dict(tested, updates_per_transition=4,
                                                                                    initial_alpha=0.05)))[1]


def test_only_a_run_that_trains_is_told(tmp_path):
    assert 'sac_values_random_search' in issues(make_config(tmp_path))[1]
    for mode in ('resume', 'frozen'):                                   # a saved run keeps its own values; frozen never updates
        loaded = make_config(tmp_path, run=dict(mode=mode, model_source=dict(run_dir=str(tmp_path))))
        assert 'sac_values_random_search' not in issues(loaded)[1], mode
    fine_tune = make_config(tmp_path, run=dict(mode='fine_tune', model_source=dict(run_dir=str(tmp_path))))
    assert 'sac_values_random_search' in issues(fine_tune)[1]


def test_a_budget_below_the_start_of_learning_is_named_for_a_from_scratch_sac_run(tmp_path):
    report, found = issues(make_config(tmp_path, run=dict(max_evaluations=60)))
    short = found['budget_below_sac_learning']
    assert short.level == 'warning' and short.path == 'run.max_evaluations' and 'With 60 evaluations' in short.message
    assert not report.blocks_run
    assert validation.SAC_LEARNS_AFTER == 300
    assert 'budget_below_sac_learning' in issues(make_config(tmp_path, run=dict(max_evaluations=299)))[1]
    assert 'budget_below_sac_learning' not in issues(make_config(tmp_path, run=dict(max_evaluations=300)))[1]
    # a loaded model has already learned
    loaded = make_config(tmp_path, run=dict(max_evaluations=60, mode='fine_tune', model_source=dict(run_dir=str(tmp_path))))
    assert 'budget_below_sac_learning' not in issues(loaded)[1]


def zero_limit(tmp_path, **fields):
    def mutate(raw):
        raw['targets'][0].update(dict(dict(constraint='<=', lower=None, upper=0.0, normalization_scale=None), **fields))
    return make_config(tmp_path, mutate=mutate)


def test_a_limit_of_zero_needs_a_typed_scale(tmp_path):
    """An empty scale is the size of the limit; a limit of 0 has none, and the miss was silently counted against 1 unit."""
    config = zero_limit(tmp_path)
    assert normalization_scale(config.targets[0]) == 1.0                       # what the row would have run with
    report, found = issues(config)
    blocker = found['scale_needed_for_zero_limit']
    assert blocker.level == 'blocker' and blocker.path == 'targets[0].normalization_scale' and report.blocks_run
    assert 'the limit is 0' in blocker.message and 'More columns' in blocker.message
    assert 'scale_needed_for_zero_limit' not in issues(zero_limit(tmp_path, normalization_scale=0.05))[1]
    assert 'scale_needed_for_zero_limit' not in issues(zero_limit(tmp_path, upper=0.5))[1]
    assert 'scale_needed_for_zero_limit' in issues(zero_limit(tmp_path, constraint='>=', lower=0.0, upper=None))[1]
    # an interval is sized by its larger bound, so only [0, 0] has no size
    assert 'scale_needed_for_zero_limit' not in issues(zero_limit(tmp_path, constraint='interval', lower=-0.006, upper=0.0))[1]
    assert 'scale_needed_for_zero_limit' in issues(zero_limit(tmp_path, constraint='interval', lower=0.0, upper=0.0))[1]


def test_hard_and_scale_are_shown_on_request_and_keep_their_values(tmp_path):
    """Record 7.183: both step behind "More columns"; nothing about a row or its hashes changes."""
    columns = {c['name']: c for c in schema.editor_columns('targets')}
    assert columns['hard']['advanced'] and columns['normalization_scale']['advanced'] and not columns['lower']['advanced']
    config = make_config(tmp_path)
    assert config.targets[0].hard is True
    assert schema.PerformanceTarget.model_fields['normalization_scale'].default is None


@pytest.mark.parametrize('field,value', [('violation_shape', 'capped'), ('worst_spec_share', 0.0), ('objective_weight', 0.0),
                                         ('objective_shape', 'clipped'), ('margin_weight', 0.0), ('nominal_gate_band', 0.5)])
def test_the_schema_reward_defaults_stay_the_old_arithmetic(field, value):
    """A configuration saved without these fields meant them; the tested set is where a NEW configuration starts
    (frontend store.ts SIMPLE_REWARD), not a change of what an old file says."""
    assert getattr(schema.RewardConfig(), field) == value
