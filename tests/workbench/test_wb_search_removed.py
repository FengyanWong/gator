"""The LLM search methods were removed on 2026-10-06 (record 7.226; the user: "SAC is the only default and other methods
should be launched through agent tab opened agent cli"). What stays: every configuration written before still loads with
the hashes it had, a page older than the server cannot start a removed method as if it were SAC, and a run made with one
is never continued as SAC - its records stay readable. MOCK only."""
import copy

from fastapi.testclient import TestClient
import pytest

from gator_workbench import runs, schema
from gator_workbench.storage.atomic import read_json, write_json
from helpers import execute, make_config, roots_for, workbench_app

# The block as every configuration made with the Search method box carried it: at its default (SAC), and one method of each
# removed kind with the settings the box wrote.
DEFAULT_SEARCH = dict(method='sac', provider=None, model=None, effort=None, candidates_per_call=4, max_llm_calls=None,
                      max_llm_notional_usd=None, llm_call_timeout_seconds=600.0, warm_start_count=None, initial_sac_updates=8,
                      rescue_stagnation_evaluations=8, rescue_max_rounds=2, hints_allowed=True)
RESCUE = dict(DEFAULT_SEARCH, method='sac_llm_rescue', provider='claude_code', model='opus', max_llm_calls=8, max_llm_notional_usd=15.0)


def with_search(config, search):
    raw = config.model_dump(mode='json')
    raw['run']['search'] = copy.deepcopy(search)
    return raw


def test_a_sac_configuration_written_with_the_search_block_loads_and_keeps_both_hashes(tmp_path):
    config = make_config(tmp_path)
    old = with_search(config, DEFAULT_SEARCH)
    loaded = schema.WorkbenchConfig.model_validate(old)
    assert 'search' not in loaded.model_dump(mode='json')['run'] and 'search' not in schema.RunSettings.model_fields
    # The block was hashed as absent at its default before (schema._hashed), so the hash of the file as written, of the
    # file as loaded and of a configuration that never had it are one and the same.
    assert schema.config_hash(old) == schema.config_hash(loaded) == schema.config_hash(config)
    assert schema.task_definition_hash(loaded) == schema.task_definition_hash(config)
    assert schema.removed_search_method(old) is None


@pytest.mark.parametrize('method', sorted(schema.REMOVED_SEARCH_METHODS))
def test_a_configuration_naming_a_removed_method_still_loads_and_is_named(tmp_path, method):
    raw = with_search(make_config(tmp_path), dict(RESCUE, method=method))
    assert schema.removed_search_method(raw) == method
    assert 'search' not in schema.WorkbenchConfig.model_validate(raw).model_dump(mode='json')['run']   # e.g. a run's own file
    assert schema.removed_search_method(dict(run=dict(search='llm'))) is None                        # not the block's shape


def test_a_page_older_than_the_server_cannot_start_a_removed_method_as_sac(tmp_path):
    client = TestClient(workbench_app(tmp_path))
    raw = with_search(make_config(tmp_path), RESCUE)
    refused = client.post('/api/runs/start', json=dict(config=raw))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'search_method_removed'
    assert 'SAC with LLM rescue' in refused.json()['detail']['message'] and 'reload' in refused.json()['detail']['message']
    assert not list(tmp_path.glob('**/run_manifest.json'))                  # nothing was created
    assert client.post('/api/config/validate', json=dict(config=raw)).status_code == 200      # the rows still validate


@pytest.mark.parametrize('method, says', [('sac_llm_rescue', 'Fine-tune with its model chosen in the RL model window'),
                                         ('llm', 'It holds no RL model')])
def test_a_run_made_with_a_removed_method_is_not_continued_as_sac(tmp_path, method, says):
    config = make_config(tmp_path, run=dict(max_evaluations=6))
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    manifest = read_json(layout.manifest)
    manifest['search_settings'] = dict(RESCUE, method=method)             # as runs.prepare_run recorded a method of them
    write_json(layout.manifest, manifest)
    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir, resumed.run.max_evaluations = 'resume', str(layout.run_dir), 12
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(resumed, roots_for(tmp_path))
    assert refused.value.code == 'search_method_removed' and says in str(refused.value)
    assert read_json(layout.manifest)['segments'] == manifest['segments']            # nothing was added to the run
    with pytest.raises(runs.RunRejected) as again:              # its lock was given back: the same answer, not "already running"
        runs.prepare_run(resumed, roots_for(tmp_path))
    assert again.value.code == 'search_method_removed'
