"""Per-encoder network settings: publication presets with provenance, the GATOR baseline, and the
operator's saved values behind the panel's encoder drop-down. No simulator, no network access."""
import json

import pytest
from fastapi.testclient import TestClient

from gator_workbench import modes, network_presets as presets, schema, tasks, validation
from gator_workbench.api import create_app
from gator_workbench.paths import local_settings_dir
from helpers import make_config

ALL_FIELDS = presets.NETWORK_FIELDS + presets.ADVANCED_FIELDS


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False))


def saved_file():
    return local_settings_dir() / presets.SETTINGS_FILE


# ------------------------------------------------------------------------------- the preset table
def test_every_encoder_has_a_complete_valid_preset_with_provenance():
    assert set(presets.PRESETS) == set(schema.ENCODER_TYPES)
    for encoder, preset in presets.PRESETS.items():
        assert set(preset['fields']) == set(ALL_FIELDS), encoder
        assert preset['summary'].strip()
        values = presets.publication(encoder)                    # raises if the run schema would reject it
        for name, field in preset['fields'].items():
            assert field['basis'] in presets.BASES and field['match'] in presets.MATCHES, (encoder, name)
            assert field['source'] is None or field['source'] in presets.REFERENCES, (encoder, name)
            if field['basis'] in ('paper', 'official_code', 'adapted'):
                assert field['source'] and field['note'].strip(), f'{encoder}.{name}: a published value needs its source'
            if field['match'] == 'closest':                      # borrowed from another network: only ever a published value
                assert field['basis'] in ('paper', 'official_code', 'adapted'), (encoder, name)
        if encoder in presets.ATTENTION_ENCODERS:
            assert values['network']['hidden_dim'] % values['network']['heads'] == 0
        else:
            assert preset['fields']['heads']['basis'] == 'not_used'


def test_the_preset_numbers_are_the_ones_verified_in_the_primary_sources():
    """Pinned on purpose: a changed number must come with a changed citation (docs/network-presets.md)."""
    sizes = {name: tuple(presets.publication(name)['network'].values()) for name in schema.ENCODER_TYPES}
    assert sizes == dict(graph_transformer=(48, 4, 4), mlp=(256, 4, 4), rgcn=(32, 4, 4), gat=(192, 3, 4),
                         port_gnn=(32, 4, 5), gcn=(32, 4, 7))                       # (hidden, heads, layers)
    keys = ('learning_rate', 'gamma', 'tau', 'batch_size', 'warmup_transitions', 'replay_capacity', 'episode_length')
    training = {name: tuple(presets.publication(name)['advanced'][k] for k in keys) for name in schema.ENCODER_TYPES}
    li2023, attention = (3e-4, 0.99, 0.005, 128, 1000, 100000, 50), (1e-3, 0.9, 0.005, 32, 8, 50, 30)
    assert training == dict(graph_transformer=attention, gat=attention, gcn=li2023, rgcn=li2023, port_gnn=li2023,
                            mlp=(3e-3, 0.8, 0.005, 256, 120, 1000000, 30))
    borrowed = {name for name, preset in presets.PRESETS.items()
                if any(field['match'] == 'closest' for field in preset['fields'].values())}
    assert borrowed == {'graph_transformer', 'port_gnn'}          # no publication trains these networks as sizing agents


def test_a_value_without_a_publication_is_the_gator_default_and_says_so():
    baseline = presets.gator_baseline()
    flat = {**baseline['network'], **baseline['advanced']}
    for encoder, preset in presets.PRESETS.items():
        for name, field in preset['fields'].items():
            if field['basis'] in ('gator_default', 'not_used'):
                assert field['value'] == flat[name], f'{encoder}.{name} claims the GATOR default but differs from it'


def test_references_are_citable():
    used = {f['source'] for p in presets.PRESETS.values() for f in p['fields'].values() if f['source']}
    assert used <= set(presets.REFERENCES)
    for key, reference in presets.REFERENCES.items():
        assert {'short', 'authors', 'title', 'venue', 'year', 'url', 'algorithm', 'budget'} <= set(reference), key
        assert reference['url'].startswith('https://') and 1990 < reference['year'] < 2100


def test_the_gator_baseline_is_the_schema_default_and_stays_the_fallback_of_a_bare_configuration(tmp_path):
    baseline = presets.gator_baseline()
    assert baseline['network'] == dict(hidden_dim=32, heads=4, layers=2)
    assert baseline['advanced']['batch_size'] == 8 and baseline['advanced']['warmup_transitions'] == 8
    raw = make_config(tmp_path).model_dump(mode='json')
    del raw['run']['network'], raw['run']['advanced']
    bare = schema.WorkbenchConfig.model_validate(raw)             # old configurations keep their meaning
    # (the component list, added later, defaults to the standard one every old configuration was built with)
    assert bare.run.network.model_dump() == dict(encoder_type='graph_transformer', **baseline['network'], vocabulary='standard')
    assert {k: v for k, v in bare.run.advanced.model_dump().items() if k in baseline['advanced']} == baseline['advanced']


def test_every_preset_builds_the_real_network_and_sac_configuration():
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    from analog_optimizer.models.encoders import build_encoder
    from analog_optimizer.models.inputs import SpecSchema
    for encoder in schema.ENCODER_TYPES:
        values = presets.publication(encoder)
        model = modes.model_config_from(schema.NetworkConfig(encoder_type=encoder, **values['network']))
        modes.sac_config_from(schema.AdvancedRL(**values['advanced']))
        network = build_encoder(FeatureSchema(), SpecSchema(), model)
        assert len(network.blocks) == values['network']['layers'] and model.encoder_type == encoder


# ------------------------------------------------------------------------------- choose / edit / reset
def test_editing_is_stored_per_encoder_and_choosing_reads_it_back():
    before = presets.entry('gcn')
    assert before['origin'] == 'publication' and before['saved_utc'] is None and not saved_file().exists()
    after = presets.save('gcn', dict(hidden_dim=48), dict(batch_size=16))
    assert after['origin'] == 'custom' and after['network']['hidden_dim'] == 48 and after['advanced']['batch_size'] == 16
    assert after['network']['layers'] == before['network']['layers']            # untouched fields keep their value
    assert after['publication'] == before['publication']                         # the preset itself never changes
    assert presets.entry('gcn')['network']['hidden_dim'] == 48                   # what the drop-down loads next time
    assert presets.entry('gat')['origin'] == 'publication'                       # other encoders are untouched
    stored = json.loads(saved_file().read_text())
    assert stored['schema'] == presets.SETTINGS_SCHEMA and set(stored['encoders']) == {'gcn'}


def test_reset_returns_to_the_publication_preset_or_stores_the_gator_baseline():
    presets.save('rgcn', dict(layers=5))
    back = presets.reset('rgcn', 'publication')
    assert back['origin'] == 'publication' and 'rgcn' not in json.loads(saved_file().read_text())['encoders']
    baseline = presets.reset('rgcn', 'gator_baseline')
    assert (baseline['network'], baseline['advanced']) == (presets.gator_baseline()['network'],
                                                           presets.gator_baseline()['advanced'])
    assert baseline['origin'] in ('gator_baseline', 'publication')              # equal only if the preset IS the baseline
    with pytest.raises(presets.InvalidNetworkSettings):
        presets.reset('rgcn', 'factory')
    with pytest.raises(KeyError):
        presets.reset('lstm', 'publication')


def test_editing_back_to_the_preset_values_forgets_the_saved_copy():
    preset = presets.publication('mlp')
    presets.save('mlp', dict(hidden_dim=preset['network']['hidden_dim'] + 4))
    assert presets.save('mlp', dict(hidden_dim=preset['network']['hidden_dim']))['origin'] == 'publication'
    assert 'mlp' not in json.loads(saved_file().read_text())['encoders']


def test_the_whole_value_set_is_validated_not_one_field_at_a_time():
    with pytest.raises(presets.InvalidNetworkSettings, match='divisible'):
        presets.save('gat', dict(hidden_dim=30, heads=4))
    assert presets.save('gat', dict(hidden_dim=30, heads=5))['network'] == dict(
        hidden_dim=30, heads=5, layers=presets.publication('gat')['network']['layers'])
    assert presets.save('gcn', dict(hidden_dim=30, heads=4))['network']['hidden_dim'] == 30      # heads is ignored there
    for bad in (dict(network=dict(hidden_dim=2)), dict(network=dict(layers=0)), dict(advanced=dict(tau=0)),
                dict(advanced=dict(gamma=1.5)), dict(advanced=dict(batch_size=1.5)),
                dict(advanced=dict(freeze_encoder=True)), dict(network=dict(encoder_type='gat'))):
        with pytest.raises(presets.InvalidNetworkSettings):
            presets.save('port_gnn', bad.get('network'), bad.get('advanced'))
    assert presets.entry('port_gnn')['origin'] == 'publication'                  # a rejected edit stores nothing


def test_a_damaged_settings_file_falls_back_to_the_preset_and_says_why():
    saved_file().parent.mkdir(parents=True, exist_ok=True)
    saved_file().write_text(json.dumps(dict(schema=presets.SETTINGS_SCHEMA, encoders=dict(
        gat=dict(network=dict(hidden_dim=30, heads=4), advanced={}), gcn='oops'))))
    gat, gcn = presets.entry('gat'), presets.entry('gcn')
    assert gat['origin'] == 'publication' and 'ignored' in gat['problem'] and gat['network'] == gat['publication']['network']
    assert gcn['origin'] == 'publication' and 'ignored' in gcn['problem']
    saved_file().write_text('not json at all {')
    torn = presets.entry('gat')
    assert torn['origin'] == 'publication' and 'not valid JSON' in torn['problem']
    with pytest.raises(presets.InvalidNetworkSettings, match='not valid JSON'):
        presets.save('gat', dict(layers=3))                                      # never overwritten behind the operator's back
    assert saved_file().read_text() == 'not json at all {'


# ------------------------------------------------------------------------------- HTTP
def test_api_serves_the_settings_the_panel_needs(client):
    data = client.get('/api/network-settings').json()
    assert data['encoders'] == list(schema.ENCODER_TYPES) and data['default_encoder'] == 'graph_transformer'
    assert data['attention_encoders'] == ['graph_transformer', 'gat'] and data['scale_note']
    assert data['network_fields'] == list(presets.NETWORK_FIELDS) and data['advanced_fields'] == list(presets.ADVANCED_FIELDS)
    for encoder, entry in data['settings'].items():
        assert entry['uses_heads'] == (encoder in ('graph_transformer', 'gat'))
        assert set(entry['network']) == set(presets.NETWORK_FIELDS) and set(entry['advanced']) == set(presets.ADVANCED_FIELDS)
        assert set(entry['provenance']) == set(ALL_FIELDS) and entry['origin'] == 'publication'


def test_api_edit_reset_and_rejections(client):
    put = client.put('/api/network-settings/gat', json=dict(network=dict(hidden_dim=48, heads=6), advanced=dict(learning_rate=1e-3)))
    assert put.status_code == 200 and put.json()['origin'] == 'custom' and put.json()['advanced']['learning_rate'] == 1e-3
    assert client.get('/api/network-settings').json()['settings']['gat']['network']['heads'] == 6
    bad = client.put('/api/network-settings/gat', json=dict(network=dict(hidden_dim=50, heads=6)))
    assert bad.status_code == 422 and 'divisible' in bad.json()['detail']['message']
    assert client.put('/api/network-settings/gat', json=dict(network=dict(hidden_dim=48), host='x')).status_code == 422
    assert client.put('/api/network-settings/lstm', json=dict(network=dict(hidden_dim=48))).status_code == 404
    assert client.post('/api/network-settings/gat/reset', json=dict(to='factory')).status_code == 422
    assert client.post('/api/network-settings/lstm/reset', json=dict(to='publication')).status_code == 404
    reset = client.post('/api/network-settings/gat/reset', json=dict(to='publication'))
    assert reset.status_code == 200 and reset.json()['origin'] == 'publication'


def test_a_configuration_built_from_any_preset_passes_the_run_schema(tmp_path):
    for encoder in schema.ENCODER_TYPES:
        values = presets.publication(encoder)
        config = make_config(tmp_path, run=dict(network=dict(encoder_type=encoder, **values['network'])),
                             advanced=values['advanced'])
        runtime = tasks.load_task(config.circuit)
        report = validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
        assert not [i for i in report.issues if i.level == 'error'], encoder


def test_the_default_encoder_preset_trains_end_to_end_on_the_mock_backend(tmp_path):
    """Not only valid numbers: the engine runs with them (48-wide 4-layer graph transformer, batch 32, replay 50)."""
    from helpers import execute, rows
    values = presets.publication('graph_transformer')
    config = make_config(tmp_path, run=dict(max_evaluations=45, network=dict(encoder_type='graph_transformer', **values['network'])),
                         advanced=values['advanced'])
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    updates = rows(layout, 'learner_updates')
    assert updates and all(update['batch_size'] == 32 for update in updates)     # one batch was filled and used
    sources = {row['action_source'] for row in rows(layout, 'evaluations')}
    assert {'random_warmup', 'sac_policy'} <= sources                           # warm-up ended, the policy acted


# ------------------------------------------------------------------------------- the scale warning
def test_a_budget_that_never_leaves_warm_up_is_reported(tmp_path):
    def codes(config):
        runtime = tasks.load_task(config.circuit)
        report = validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
        return {i.code: i.level for i in report.issues}
    starved = codes(make_config(tmp_path, run=dict(max_evaluations=20), advanced=dict(warmup_transitions=20)))
    assert starved['budget_within_warmup'] == 'warning'
    assert 'budget_within_warmup' not in codes(make_config(tmp_path, run=dict(max_evaluations=21), advanced=dict(warmup_transitions=20)))
