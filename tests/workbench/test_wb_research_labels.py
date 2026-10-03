"""Research labels retired on 2026-10-03 (record 7.163): `experiment_group` and `test_tasks`, which nothing read. A
configuration written with them still loads, and keeps the configuration hash it had while they were at their defaults."""
from gator_workbench import schema

from helpers import make_config


def _old(raw, **research):
    """`raw` as it was saved while the two labels existed: every research label written out, as the page and runs did."""
    labels = dict(split='unspecified', generalization_level='unspecified', training_sources=[], comparison_pair_id='unspecified',
                  task_order=None, pretrain_seed=None, budget_checkpoints=[], ablation_labels=[], method_label='unspecified',
                  experiment_group='unspecified', test_tasks=[])
    return dict(raw, research=dict(labels, **research))


def test_a_configuration_with_the_retired_labels_still_loads_without_them():
    raw = _old(make_config('/tmp').model_dump(mode='json'), experiment_group='g1', test_tasks=['a', 'b'])
    loaded = schema.WorkbenchConfig.model_validate(raw)
    research = loaded.model_dump(mode='json')['research']
    assert 'experiment_group' not in research and 'test_tasks' not in research


def test_a_configuration_saved_before_keeps_its_hash():
    raw = _old(make_config('/tmp').model_dump(mode='json'))
    assert schema.config_hash(raw) == schema.config_hash(schema.WorkbenchConfig.model_validate(raw))


def test_the_task_hash_never_saw_research_labels():
    raw = _old(make_config('/tmp').model_dump(mode='json'), experiment_group='g1')
    assert schema.task_definition_hash(schema.WorkbenchConfig.model_validate(raw)) == schema.task_definition_hash(make_config('/tmp'))
