"""Per-encoder network settings: the starting preset of each encoder (network sizes from publications, every training
value of the runs that learned on GATOR circuits, record 7.192) with provenance, and the operator's saved values behind
the panel's encoder drop-down; the GATOR baseline is deleted (record 7.191). No simulator, no network access."""
import json

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from gator_workbench import modes, network_presets as presets, schema, tasks, validation
from gator_workbench.paths import local_settings_dir
from helpers import make_config, workbench_app

ALL_FIELDS = presets.NETWORK_FIELDS + presets.ADVANCED_FIELDS


@pytest.fixture
def client(tmp_path):
    return TestClient(workbench_app(tmp_path, auto_check_on_start=True))


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
    """Pinned on purpose: a changed number must come with a changed citation (docs/network-presets.md). A published
    training number replaced by the one of the runs that learned (record 7.192) is still pinned, under `published`."""
    original = ('graph_transformer', 'rgcn', 'gatv2')
    sizes = {name: tuple(presets.publication(name)['network'][k] for k in ('hidden_dim', 'heads', 'layers')) for name in original}
    assert sizes == dict(graph_transformer=(48, 4, 4), rgcn=(32, 4, 4), gatv2=(192, 3, 4))
    keys = ('learning_rate', 'gamma', 'tau', 'batch_size', 'warmup_transitions', 'replay_capacity', 'episode_length')

    def cited(name, key):
        field = presets.PRESETS[name]['fields'][key]
        return field.get('published', field)['value']
    training = {name: tuple(cited(name, k) for k in keys) for name in original}
    li2023, attention = (3e-4, 0.99, 0.005, 128, 1000, 100000, 50), (1e-3, 0.9, 0.005, 32, 8, 50, 30)
    assert training == dict(graph_transformer=attention, gatv2=attention, rgcn=li2023)
    cited_fields = {name: [field.get('published', field) for field in preset['fields'].values()]
                    for name, preset in presets.PRESETS.items()}
    borrowed = {name for name, fields in cited_fields.items() if any(field['match'] == 'closest' for field in fields)}
    assert borrowed == {'graph_transformer', 'gatv2'}  # settings borrowed from other architectures
    assert all(field['match'] == 'closest' for field in cited_fields['gatv2']
               if field['source'])                  # GAT papers must not become GATv2 sizing evidence


def test_a_value_without_a_publication_is_the_gator_default_and_says_so():
    legacy = presets.legacy_baseline()
    flat = {**legacy['network'], **legacy['advanced'], **presets.LEARNED}
    for encoder, preset in presets.PRESETS.items():
        for name, field in preset['fields'].items():
            if field['basis'] in ('gator_default', 'gator_tested', 'gator_measured_with', 'not_used'):
                assert field['value'] == flat[name], f'{encoder}.{name} claims the GATOR default but differs from it'
            # compared and chosen on GATOR circuits (the three of record 7.183, the learning rate of record 7.199), saying
            # what was measured; the other training values of those runs say that they are what the measurements were made
            # with, not a compared optimum
            assert (field['basis'] == 'gator_tested') == (name in presets.COMPARED and field['source'] is None and encoder not in schema.GLOBAL_ENCODERS), (encoder, name)
            measured_with = name in presets.LEARNED and name not in presets.COMPARED and field['source'] is None and encoder not in schema.GLOBAL_ENCODERS
            assert (field['basis'] == 'gator_measured_with') == measured_with, (encoder, name)
            if field['basis'] in ('gator_tested', 'gator_measured_with'):
                assert 'record 7.183' in field['note'] or 'record 7.199' in field['note'], (encoder, name)
            if field['basis'] == 'gator_measured_with':
                assert 'The value the measurements of 2026-10-05 were made with' in field['note'], (encoder, name)


def test_every_preset_trains_with_the_values_of_the_runs_that_learned():
    """Record 7.192 (user: "merge the publication preset and overwrite those settings with the previous learned settings",
    then "All training numbers"): the network sizes stay published, every training value is the one of the runs that
    learned on GATOR circuits. A replaced published value is kept under `published` and named in the note."""
    legacy = presets.legacy_baseline()
    # record 7.199 (user: "use learning rate 1e-3 in the starting preset"): compared with 8 updates and discount 0, chosen
    assert presets.LEARNED == dict(presets.TESTED, batch_size=8, learning_rate=1e-3, warmup_transitions=8,
                                   replay_capacity=10000, episode_length=4)
    assert set(presets.COMPARED) == {'initial_alpha', 'updates_per_transition', 'gamma', 'learning_rate'}
    # besides the compared values, those runs had the schema defaults - and a 32 / 4 / 2 network
    assert {k: legacy['advanced'][k] for k in presets.LEARNED if k not in presets.COMPARED} == {
        k: v for k, v in presets.LEARNED.items() if k not in presets.COMPARED}
    runs = {**legacy['advanced'], **presets.LEARNED}                   # every training number of the runs that learned
    for encoder, preset in presets.PRESETS.items():
        assert presets.publication(encoder)['advanced'] == runs, encoder
        for name, field in preset['fields'].items():
            if 'published' in field:
                assert name in presets.LEARNED and field['published']['value'] != field['value'], (encoder, name)
                assert field['published']['source'] in presets.REFERENCES and field['published']['basis'] in presets.BASES
                assert field['note'].startswith(f"Published: {field['published']['value']:g} ("), (encoder, name)
        if encoder not in schema.GLOBAL_ENCODERS:
            assert 'record 7.192' in preset['summary'] and '32 / 4 / 2' in preset['summary']
    replaced = {(e, n) for e, p in presets.PRESETS.items() for n, f in p['fields'].items() if 'published' in f}
    # the attention presets' published learning rate is 1e-3 already: kept as published, with the GATOR note added
    assert replaced == {(e, n) for e in ('graph_transformer', 'gatv2')
                        for n in ('gamma', 'batch_size', 'replay_capacity', 'episode_length')} | {
        ('rgcn', n) for n in ('learning_rate', 'gamma', 'batch_size', 'warmup_transitions', 'updates_per_transition',
                              'replay_capacity', 'episode_length')}
    for encoder in ('graph_transformer', 'gatv2'):
        field = presets.PRESETS[encoder]['fields']['learning_rate']
        assert field['source'] == 'li2021can' and 'Also the GATOR value.' in field['note'] and 'record 7.199' in field['note']


def test_references_are_citable():
    used = {f['source'] for p in presets.PRESETS.values() for f in p['fields'].values() if f['source']}
    assert used <= set(presets.REFERENCES)
    for key, reference in presets.REFERENCES.items():
        assert {'short', 'authors', 'title', 'venue', 'year', 'url', 'algorithm', 'budget'} <= set(reference), key
        assert reference['url'].startswith('https://') and 1990 < reference['year'] < 2100


@pytest.mark.parametrize('encoder', schema.GLOBAL_ENCODERS)
def test_new_encoders_are_experimental_and_keep_their_structural_settings(client, encoder):
    entry = presets.entry(encoder)
    assert entry['experimental'] and entry['supports_structural_encoding'] and entry['architecture_reference']
    assert all(field['basis'] == 'experimental' for field in entry['provenance'].values())
    assert entry['network'] == dict(hidden_dim=48, heads=4, layers=4,
                                     structural_encoding='rwse' if encoder in ('graph_gps', 'circuit_gps') else 'none')
    response = client.put(f'/api/network-settings/{encoder}', json=dict(network=dict(structural_encoding='none', layers=3)))
    assert response.status_code == 200
    assert presets.entry(encoder)['network']['structural_encoding'] == 'none'
    assert presets.entry(encoder)['network']['layers'] == 3
    response = client.put(f'/api/network-settings/{encoder}', json=dict(network=dict(structural_encoding='rwse')))
    assert response.status_code == 200
    config = modes.model_config_from(schema.NetworkConfig(encoder_type=encoder, **presets.entry(encoder)['network']))
    assert config.to_dict()['structural_encoding'] == 'rwse'
    assert client.put('/api/network-settings/rgcn', json=dict(network=dict(structural_encoding='rwse'))).status_code == 422


def test_the_tested_values_build_a_learner_and_a_bare_configuration_keeps_the_schema_defaults(tmp_path):
    """Record 7.183: the three training values measured on 2026-10-05. The schema defaults themselves - the legacy
    baseline - stay, so a configuration without a network block means what it meant."""
    legacy = presets.legacy_baseline()
    assert legacy['network'] == dict(hidden_dim=32, heads=4, layers=2, structural_encoding='none')
    assert legacy['advanced']['batch_size'] == 8 and legacy['advanced']['warmup_transitions'] == 8
    assert presets.TESTED == dict(initial_alpha=0.01, updates_per_transition=8, gamma=0.0)
    assert {k: legacy['advanced'][k] for k in presets.TESTED} == dict(initial_alpha=0.2, updates_per_transition=1, gamma=0.99)
    raw = make_config(tmp_path).model_dump(mode='json')
    del raw['run']['network'], raw['run']['advanced']
    bare = schema.WorkbenchConfig.model_validate(raw)             # old configurations keep their meaning
    # (the component list, added later, defaults to the standard one every old configuration was built with)
    assert bare.run.network.model_dump() == dict(encoder_type='graph_transformer', **legacy['network'], vocabulary='standard',
                                                 operating_points=False,          # added 2026-09-26 (reward v2), off = as before
                                                 spec_input='slots', size_features='absolute',
                                                 device_model_features=False,     # added 2026-10-10 (7.298), off = as before
                                                 bench_features='absolute', net_roles='task',
                                                 operating_point_ratios=False)    # added 2026-10-11 (7.317), off = as before
    assert {k: v for k, v in bare.run.advanced.model_dump().items() if k in legacy['advanced']} == legacy['advanced']
    modes.sac_config_from(schema.AdvancedRL(**{**legacy['advanced'], **presets.TESTED}))   # the tested values build a learner


def test_an_encoder_put_on_the_deleted_gator_baseline_reads_as_the_publication_preset():
    """Record 7.191 (user: "Delete the gator baseline in RL networks and keep the publication preset"). Pressed before
    2026-10-05 the button stored the schema defaults (the user's own graph_transformer entry), pressed later that day the
    schema's sizes with the tested values; both now read as the publication preset, and the file is not rewritten. The
    same numbers saved at other times were typed by the operator and stay theirs."""
    legacy = presets.legacy_baseline()
    tested = dict(network=legacy['network'], advanced={**legacy['advanced'], **presets.TESTED})
    saved_file().parent.mkdir(parents=True, exist_ok=True)

    def read(values, saved_utc):
        text = json.dumps(dict(schema=presets.SETTINGS_SCHEMA, encoders=dict(graph_transformer=dict(values, saved_utc=saved_utc))))
        saved_file().write_text(text)
        entry = presets.entry('graph_transformer')
        assert saved_file().read_text() == text                                     # reading never rewrites the file
        return entry

    preset = presets.publication('graph_transformer')
    for values, saved_utc in ((legacy, '2026-10-03T17:50:40+00:00'), (tested, '2026-10-05T10:00:00+00:00')):
        entry = read(values, saved_utc)
        assert entry['origin'] == 'publication' and entry['problem'] is None and entry['saved_utc'] is None, saved_utc
        assert (entry['network'], entry['advanced']) == (preset['network'], preset['advanced'])
        assert 'followed_baseline' not in entry
    # the preset this lands on still learns: the two values that decide it are the tested ones (no random search again)
    assert {k: preset['advanced'][k] for k in ('initial_alpha', 'updates_per_transition')} == dict(initial_alpha=0.01,
                                                                                                    updates_per_transition=8)
    assert json.loads(saved_file().read_text())['encoders']['graph_transformer']['saved_utc'] == '2026-10-05T10:00:00+00:00'
    own = read(legacy, '2026-10-05T06:00:00+00:00')                                # the schema defaults typed after 7.183
    assert own['origin'] == 'custom' and own['advanced'] == legacy['advanced']
    typed = read(tested, '2026-10-06T08:00:00+00:00')                              # the old baseline typed after the deletion
    assert typed['origin'] == 'custom' and (typed['network'], typed['advanced']) == (tested['network'], tested['advanced'])
    edited = read(dict(legacy, advanced=dict(legacy['advanced'], batch_size=16)), '2026-10-03T17:50:40+00:00')
    assert edited['origin'] == 'custom' and edited['advanced']['initial_alpha'] == 0.2 and edited['advanced']['batch_size'] == 16
    read(legacy, '2026-10-03T17:50:40+00:00')
    changed = presets.save('graph_transformer', dict(layers=3))                    # an edit starts from the preset, not the old values
    assert changed['origin'] == 'custom' and changed['network'] == dict(preset['network'], layers=3)
    assert changed['advanced'] == preset['advanced']


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
    before = presets.entry('rgcn')
    assert before['origin'] == 'publication' and before['saved_utc'] is None and not saved_file().exists()
    after = presets.save('rgcn', dict(hidden_dim=48), dict(batch_size=16))
    assert after['origin'] == 'custom' and after['network']['hidden_dim'] == 48 and after['advanced']['batch_size'] == 16
    assert after['network']['layers'] == before['network']['layers']            # untouched fields keep their value
    assert after['publication'] == before['publication']                         # the preset itself never changes
    assert presets.entry('rgcn')['network']['hidden_dim'] == 48                   # what the drop-down loads next time
    assert presets.entry('gatv2')['origin'] == 'publication'                       # other encoders are untouched
    stored = json.loads(saved_file().read_text())
    assert stored['schema'] == presets.SETTINGS_SCHEMA and set(stored['encoders']) == {'rgcn'}


def test_editing_back_to_the_preset_values_forgets_the_saved_copy():
    preset = presets.publication('rgcn')
    presets.save('rgcn', dict(hidden_dim=preset['network']['hidden_dim'] + 4))
    assert presets.save('rgcn', dict(hidden_dim=preset['network']['hidden_dim']))['origin'] == 'publication'
    assert 'rgcn' not in json.loads(saved_file().read_text())['encoders']


def test_the_whole_value_set_is_validated_not_one_field_at_a_time():
    with pytest.raises(presets.InvalidNetworkSettings, match='divisible'):
        presets.save('gatv2', dict(hidden_dim=30, heads=4))
    assert presets.save('gatv2', dict(hidden_dim=30, heads=5))['network'] == dict(
        hidden_dim=30, heads=5, layers=presets.publication('gatv2')['network']['layers'], structural_encoding='none')
    assert presets.save('rgcn', dict(hidden_dim=30, heads=4))['network']['hidden_dim'] == 30      # heads is ignored there
    previous = presets.entry('rgcn')
    for bad in (dict(network=dict(hidden_dim=2)), dict(network=dict(layers=0)), dict(advanced=dict(tau=0)),
                dict(advanced=dict(gamma=1.5)), dict(advanced=dict(batch_size=1.5)),
                dict(advanced=dict(freeze_encoder=True)), dict(network=dict(encoder_type='gatv2'))):
        with pytest.raises(presets.InvalidNetworkSettings):
            presets.save('rgcn', bad.get('network'), bad.get('advanced'))
    assert presets.entry('rgcn') == previous                                    # a rejected edit stores nothing


def test_a_damaged_settings_file_falls_back_to_the_preset_and_says_why():
    saved_file().parent.mkdir(parents=True, exist_ok=True)
    saved_file().write_text(json.dumps(dict(schema=presets.SETTINGS_SCHEMA, encoders=dict(
        gatv2=dict(network=dict(hidden_dim=30, heads=4), advanced={}), rgcn='oops'))))
    gatv2, rgcn = presets.entry('gatv2'), presets.entry('rgcn')
    assert gatv2['origin'] == 'publication' and 'ignored' in gatv2['problem'] and gatv2['network'] == gatv2['publication']['network']
    assert rgcn['origin'] == 'publication' and 'ignored' in rgcn['problem']
    saved_file().write_text('not json at all {')
    torn = presets.entry('gatv2')
    assert torn['origin'] == 'publication' and 'not valid JSON' in torn['problem']
    with pytest.raises(presets.InvalidNetworkSettings, match='not valid JSON'):
        presets.save('gatv2', dict(layers=3))                                      # never overwritten behind the operator's back
    assert saved_file().read_text() == 'not json at all {'


# ------------------------------------------------------------------------------- HTTP
def test_api_serves_the_settings_the_panel_needs(client):
    data = client.get('/api/network-settings').json()
    assert data['encoders'] == list(schema.ENCODER_TYPES) and data['default_encoder'] == 'graph_transformer'
    assert data['attention_encoders'] == list(presets.ATTENTION_ENCODERS) and data['scale_note']
    assert data['network_fields'] == list(presets.NETWORK_FIELDS) and data['advanced_fields'] == list(presets.ADVANCED_FIELDS)
    assert data['tested']['values'] == presets.TESTED and 'record 7.183' in data['tested']['note']
    assert 'gator_baseline' not in data and data['legacy_baseline']['advanced']['updates_per_transition'] == 1   # record 7.191
    assert data['learned'] == presets.LEARNED                                                                     # record 7.192
    for encoder, entry in data['settings'].items():
        assert entry['uses_heads'] == (encoder != 'rgcn')
        assert set(entry['network']) == set(presets.NETWORK_FIELDS) and set(entry['advanced']) == set(presets.ADVANCED_FIELDS)
        assert set(entry['provenance']) == set(ALL_FIELDS) and entry['origin'] == 'publication'


def test_api_edit_and_rejections(client):
    put = client.put('/api/network-settings/gatv2', json=dict(network=dict(hidden_dim=48, heads=6), advanced=dict(learning_rate=1e-3)))
    assert put.status_code == 200 and put.json()['origin'] == 'custom' and put.json()['advanced']['learning_rate'] == 1e-3
    assert client.get('/api/network-settings').json()['settings']['gatv2']['network']['heads'] == 6
    bad = client.put('/api/network-settings/gatv2', json=dict(network=dict(hidden_dim=50, heads=6)))
    assert bad.status_code == 422 and 'divisible' in bad.json()['detail']['message']
    assert client.put('/api/network-settings/gatv2', json=dict(network=dict(hidden_dim=48), host='x')).status_code == 422
    assert client.put('/api/network-settings/lstm', json=dict(network=dict(hidden_dim=48))).status_code == 404
    preset = presets.publication('gatv2')                     # typed back to the preset: the saved copy is forgotten
    back = client.put('/api/network-settings/gatv2', json=preset)
    assert back.status_code == 200 and back.json()['origin'] == 'publication'
    # the two preset buttons and the reset route behind them are gone (record 7.191)
    assert client.post('/api/network-settings/gatv2/reset', json=dict(to='publication')).status_code == 404


def test_a_configuration_built_from_any_preset_passes_the_run_schema(tmp_path):
    for encoder in schema.ENCODER_TYPES:
        values = presets.publication(encoder)
        config = make_config(tmp_path, run=dict(network=dict(encoder_type=encoder, **values['network'])),
                             advanced=values['advanced'])
        runtime = tasks.load_task(config.circuit)
        report = validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
        assert not [i for i in report.issues if i.level == 'error'], encoder


def test_the_default_encoder_preset_trains_end_to_end_on_the_mock_backend(tmp_path):
    """Not only valid numbers: the engine runs with them (48-wide 4-layer graph transformer, batch 8, 8 updates per
    evaluation, discount 0)."""
    from helpers import execute, rows
    values = presets.publication('graph_transformer')
    config = make_config(tmp_path, run=dict(max_evaluations=16, network=dict(encoder_type='graph_transformer', **values['network'])),
                         advanced=values['advanced'])
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    updates = rows(layout, 'learner_updates')
    assert updates and all(update['batch_size'] == 8 for update in updates)      # one batch was filled and used
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


# ------------------------------------------------------------------------------- removed encoders
def test_gat_v1_is_rejected_without_migrating_saved_settings(client):
    legacy = dict(network=dict(hidden_dim=64, heads=4, layers=2), advanced={})
    saved_file().parent.mkdir(parents=True, exist_ok=True)
    saved_file().write_text(json.dumps(dict(encoders=dict(gat=legacy))))
    before = saved_file().read_bytes()
    current = client.get('/api/network-settings').json()
    assert 'gat' not in current['encoders'] and 'gat' not in current['settings']
    assert current['settings']['gatv2']['origin'] == 'publication'
    assert current['settings']['gatv2']['network'] == presets.publication('gatv2')['network']
    assert saved_file().read_bytes() == before
    assert client.put('/api/network-settings/gat', json=dict(network=dict(hidden_dim=32))).status_code == 404
    with pytest.raises(ValidationError, match=r'gat \(GATv1\) was replaced by gatv2'):
        schema.NetworkConfig(encoder_type='gat')


@pytest.mark.parametrize('encoder,date,commit', [('port_gnn','2026-09-24','bbdfe36'),
                                                ('mlp','2026-09-26','9bc488f'), ('gcn','2026-09-26','9bc488f')])
def test_removed_encoders_are_gone_from_the_list_and_refused_in_words(client,encoder,date,commit):
    """Removed encoders are not offered or editable; imports explain the matching historical source."""
    data = client.get('/api/network-settings').json()
    assert data['encoders'] == list(schema.ENCODER_TYPES) == ['graph_transformer','rgcn','gatv2', 'graph_gps', 'group_cross_attention', 'circuit_gps']
    assert encoder not in data['settings'] and encoder not in presets.PRESETS
    assert client.put(f'/api/network-settings/{encoder}', json=dict(network=dict(hidden_dim=32))).status_code == 404
    with pytest.raises(KeyError):
        presets.entry(encoder)
    with pytest.raises(ValidationError) as caught:
        schema.NetworkConfig(encoder_type=encoder)
    message = str(caught.value)
    assert f'removed from the optimizer on {date}' in message and commit in message and 'rgcn' in message
    assert schema.NetworkConfig(encoder_type='rgcn').encoder_type == 'rgcn'
