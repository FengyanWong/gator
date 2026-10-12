"""Resolve the input contract shared by online and archived-data models.

The feature schema, learner arguments and recorded vocabulary are constructed here;
``network_inputs`` implements the observation view itself. Policy stays explicit:
online runs may read raw operating points and native count columns, offline pools
accept only their declared input keys, and publication keeps no source PDK mapping.
Nothing here constructs a learner, changes random state or writes an artifact.
"""
from __future__ import annotations

from dataclasses import replace

from . import families, network_inputs, vocabulary as component_lists
from .pdk_record import PdkError, STANDARD, label
from .run_definitions import RunRejected


def feature_schema(network, schema=None, *, native_counts=(), operating_points=False):
    """Extend a component schema in the same order for every learner input path.

    Callers choose the base component list and explicitly opt into online-only
    columns. Offline observations have already been viewed before being pooled.
    """
    from analog_optimizer.graph.pyg_converter import FeatureSchema, OPERATING_POINT_COLUMNS, OPERATING_POINT_REFERENCES
    if schema is None:
        schema = FeatureSchema()
    counts = sorted(set(native_counts) - set(schema.parameters))
    if counts:
        schema = replace(schema, version=schema.version + '-counts-' + '-'.join(counts),
                         parameters=schema.parameters + tuple(counts),
                         references=schema.references + (1.,) * len(counts))
    if operating_points:
        schema = replace(schema, op_columns=OPERATING_POINT_COLUMNS, op_references=OPERATING_POINT_REFERENCES)
    return network_inputs.feature_schema(schema, network)


def learner_options(vocabulary=None, runtime=None):
    """Identical input keywords for creating a learner and restoring its full state.

    Keep the optimizer's default (None) when no schema is specified. Runtime
    options deliberately take precedence over the vocabulary's unextended schema.
    """
    options = dict(feature_schema=None if vocabulary is None else vocabulary.schema)
    options.update(runtime or {})
    return options


def source_vocabulary(config, source_run=None):
    """Choose a new run's component list, retaining a loaded model's matching PDK list.

    Family-list models map the target task's PDK; a PDK-specific model keeps its
    saved list even when that PDK has since been reloaded. Resume instead reads the
    run's own list directly through ``vocabulary.run_vocabulary``.
    """
    wanted = component_lists.requested(config)
    if source_run is not None and wanted != families.NAME:
        own = component_lists.run_vocabulary(source_run)
        if own is not None and own.name == wanted:
            return own
    try:
        return component_lists.current_vocabulary(wanted, getattr(config.circuit, 'pdk_id', None))
    except PdkError as exc:
        raise RunRejected(str(exc), code='pdk_not_loaded')


def vocabulary_record(vocabulary) -> dict:
    """Manifest metadata for the component list kept in network_vocabulary.json."""
    if vocabulary is None:
        return dict(name=STANDARD, label=label(None))
    return dict(name=vocabulary.name, label=vocabulary.label, pdk_id=vocabulary.pdk_id, version=vocabulary.version,
                sha256=vocabulary.sha256, file=component_lists.RUN_FILE)


INPUT_KEYS = dict(spec_input=('slots', 'set', 'structured'), size_features=('absolute', 'pdk_relative'), device_model_features=(False, True),
                  vocabulary=('standard', 'families'),
                  # the second build (record 7.317)
                  bench_features=('absolute', 'relative'), net_roles=('task', 'rule'), operating_point_ratios=(False, True))


def request_inputs(request) -> dict:
    """Validate an offline request's input choices and resolve the existing defaults.

    Raw operating-point input is not offered offline. Ratios use archived operating
    points; the pool itself enforces the request's missing-operating-points policy.
    """
    inputs = dict(request.get('inputs') or {})
    if (request.get('model') or {}).get('encoder_type') == 'circuit_gps':
        inputs.setdefault('spec_input', 'structured')
        if inputs['spec_input'] != 'structured':
            raise ValueError('Offline CircuitGPS models require inputs.spec_input structured')
    if set(inputs) - INPUT_KEYS.keys():
        raise ValueError(f'Unknown network inputs {sorted(set(inputs) - INPUT_KEYS.keys())}; known: {sorted(INPUT_KEYS)}')
    for key, allowed in INPUT_KEYS.items():
        if key in inputs and inputs[key] not in allowed:
            raise ValueError(f'inputs.{key} must be one of {allowed}')
    return dict(network_inputs.transfer_settings(inputs), vocabulary=inputs.get('vocabulary', 'standard'))


def source_view(config, inputs):
    """Resolve one archive's view from its task and current PDK data.

    Its key pins those inputs beside the archive checksum. A family-only view is
    still required offline, where observations are transformed before pooling.
    Online learners apply that mapping in their vocabulary learner instead.
    """
    from .schema import WorkbenchConfig          # lazy: only archive input reconstruction needs the configuration schema
    try:
        recorded = WorkbenchConfig.model_validate(config)
    except Exception as exc:
        raise ValueError(f'The recorded configuration of a source cannot be read for the network inputs: {exc}') from exc
    recorded.run.network = recorded.run.network.model_copy(update={k: v for k, v in inputs.items() if k != 'vocabulary'})
    vocabulary = (families.FamilyList(families.block_for(getattr(recorded.circuit, 'pdk_id', None)))
                  if inputs['vocabulary'] == families.NAME else None)
    view = network_inputs.view_for(recorded, vocabulary)
    return view if view is not None or vocabulary is None else network_inputs.NetworkView(vocabulary=vocabulary)


def pool_feature_schema(inputs):
    """Offline pools accept standard or family columns, without online-only extras."""
    return feature_schema(inputs, families.schema() if inputs['vocabulary'] == families.NAME else None)


def published_vocabulary(contract):
    """A published pool keeps its trained list without selecting one source's PDK."""
    built_with = (contract.get('feature_schema') or {}).get('version', '').partition('+')[0]
    return families.FamilyList(families.block_for(None)) if built_with == families.VERSION else None
