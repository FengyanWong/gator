"""Run settings retired on 2026-09-29 (`schema.RETIRED_RUN_FIELDS`): "Threads per job" never reached a simulator - no
task ever applied it - so the box looked like a control that was none. A configuration written with it still loads,
and both hashes are exactly what they were, so every run, checkpoint, task file and approval made before keeps its
identity (every stored configuration had the default, 1)."""
import copy
import json

from gator_workbench import schema
from gator_workbench.agents import settings_review
from helpers import make_config


def test_a_configuration_written_with_it_still_loads_and_keeps_both_hashes(tmp_path):
    config = make_config(tmp_path)
    data = config.model_dump(mode='json')
    assert 'threads_per_job' not in data['run'] and 'threads_per_job' not in schema.RunSettings.model_fields
    old = copy.deepcopy(data)
    old['run']['threads_per_job'] = 1                                   # as every configuration made before carries it
    loaded = schema.WorkbenchConfig.model_validate(old)
    assert 'threads_per_job' not in loaded.model_dump(mode='json')['run']
    assert schema.config_hash(old) == schema.config_hash(loaded) == schema.config_hash(config)
    assert schema.task_definition_hash(loaded) == schema.task_definition_hash(config)


def test_the_hash_sees_it_at_its_old_default_as_before(tmp_path):
    """The hashed form is the one a configuration had before the field went: the run section with threads_per_job 1."""
    config = make_config(tmp_path)
    hashed = schema._hashed(config.model_dump(mode='json'))
    assert hashed['run']['threads_per_job'] == 1
    assert json.loads(schema.canonical_json(hashed))['run']['threads_per_job'] == 1


def test_nothing_offers_or_records_it_any_more():
    assert 'threads_per_job' not in settings_review.SUGGESTIBLE['run']              # the agent's settings review
    assert 'threads_per_job' not in schema.RunSettings.model_fields
