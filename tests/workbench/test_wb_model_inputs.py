"""Shared model-input contracts keep online/offline agreement and explicit exceptions."""
import itertools

import pytest

from analog_optimizer.graph.pyg_converter import OPERATING_POINT_COLUMNS
from gator_workbench import families, model_inputs, modes, network_inputs, pretrain
from helpers import make_config


@pytest.mark.parametrize('vocabulary', ('standard', 'families'))
@pytest.mark.parametrize('relative, models, second', list(itertools.product((False, True), repeat=3)))
def test_online_and_offline_models_share_the_same_supported_feature_contract(tmp_path, vocabulary, relative, models, second):
    inputs = dict(vocabulary=vocabulary, size_features='pdk_relative' if relative else 'absolute',
                  device_model_features=models, bench_features='relative' if second else 'absolute',
                  net_roles='rule' if second else 'task', operating_point_ratios=second)
    config = make_config(tmp_path)
    config.run.network = config.run.network.model_copy(update=inputs)
    listed = families.FamilyList(families.block_for(None)) if vocabulary == 'families' else None
    online = modes.runtime_options(config, listed)['feature_schema']
    offline = model_inputs.pool_feature_schema(pretrain.request_inputs(dict(inputs=inputs)))
    assert online == offline


@pytest.mark.parametrize('ratios', (False, True))
def test_raw_operating_points_remain_an_online_only_choice(tmp_path, ratios):
    config = make_config(tmp_path)
    config.run.network = config.run.network.model_copy(update=dict(operating_points=True, operating_point_ratios=ratios))
    online = modes.runtime_options(config)['feature_schema']
    offline = model_inputs.pool_feature_schema(pretrain.request_inputs(dict(inputs=dict(operating_point_ratios=ratios))))
    assert online.op_columns == OPERATING_POINT_COLUMNS
    assert offline.op_columns == (network_inputs.REGION_COLUMNS if ratios else ())
    with pytest.raises(ValueError, match='Unknown network inputs'):
        pretrain.request_inputs(dict(inputs=dict(operating_points=True)))


def test_native_ngspice_counts_extend_only_a_standard_online_component_list(tmp_path):
    config = make_config(tmp_path)
    config.circuit.task_id = 'ngspice:counts'
    config.parameters[0] = config.parameters[0].model_copy(update=dict(parameter_name='mult', unit='count'))
    online = modes.runtime_options(config)['feature_schema']
    family = modes.runtime_options(config, families.FamilyList(families.block_for(None)))['feature_schema']
    offline = model_inputs.pool_feature_schema(pretrain.request_inputs({}))
    assert online.parameters[-1] == 'mult' and online.references[-1] == 1.
    assert online.version.endswith('-counts-mult')
    assert 'mult' not in family.parameters and 'mult' not in offline.parameters


def test_publication_keeps_the_family_schema_without_a_source_pdk_mapping():
    inputs = pretrain.request_inputs(dict(inputs=dict(vocabulary='families', operating_point_ratios=True)))
    schema = model_inputs.pool_feature_schema(inputs)
    listed = model_inputs.published_vocabulary(dict(feature_schema=dict(version=schema.version)))
    assert listed.name == 'families' and listed.pdk_id is None and listed.devices == {}
    record = model_inputs.vocabulary_record(listed)
    assert record['name'] == 'families' and record['sha256'] == listed.sha256
    assert record['file'] == 'network_vocabulary.json'
    assert model_inputs.published_vocabulary(dict(feature_schema=dict(version='features-v1'))) is None
