"""The transferable network inputs of record 7.298: what the network sees of a run's observations when its settings ask
for them (``run.network``: spec_input "set", size_features "pdk_relative", device_model_features). The page sets the
three together ("Network inputs: Transferable"); a configuration may set them one by one.

Everything happens at the network's input, as the PDK component list already does (``vocabulary.Vocabulary.view``):
the environment, the backend, the replay and every recorded table keep the graph and the observations the simulator
saw; the learner's ``batch`` shows the network a VIEW of them (``NetworkView``):

- spec input "set": the spec set input of the optimizer (``SpecSetSchema``) - every active spec one item, described by
  ``spec_descriptors`` - so a model reads any spec list; the descriptions go into the viewed graph's metadata;
- size features "pdk_relative": each MOS width and length divided by its model's minimum (``device_models``: the
  smallest bin of the PDK's nominal model section, else the cell's CDF default), so a minimum-length device reads the
  same in every PDK; any other device's width and length in micrometres as before (the columns of w and l then have
  no unit of their own: reference 1, each device its own divisor);
- device model features: four columns more per device - threshold voltage, mobility, saturation velocity, oxide
  thickness of its model (``device_models``) - present on MOS devices only.

Operating points (``run.network.operating_points``) are the optimizer's own input; a Maestro task reads them for such a
run (``recipes.maestro_operating_points``).

A viewed observation carries a marker, so it is never viewed twice. The view of a replayed observation is kept by its
digest (the replay's own, record 7.221): a learner step views each distinct state once.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import threading

from . import device_models, spec_descriptors
from .deck_ops import has_dc_operating_point
from .profile_store import profile_entry
from .storage.atomic import read_json
from .vocabulary import learner_class as vocabulary_learner

VIEW_KEY = 'network_view'
RELATIVE_SUFFIX = '+pdk-relative-sizes-v1'
MODEL_SUFFIX = '+device-model-features-v1'
MODEL_COLUMNS = ('tech_vth0', 'tech_u0', 'tech_vsat', 'tech_tox')
MODEL_REFERENCES = (1.0, 1e-2, 1e5, 1e-9)            # V, m^2/Vs (100 cm^2/Vs), m/s, m
SIZE_COLUMNS = dict(w='wmin', l='lmin')
MOS_KINDS = ('nmos', 'pmos')
RUN_FILE = 'network_inputs.json'
FORMAT = 'gator-network-inputs-v1'


def transfer_settings(network) -> dict:
    """The record-7.298 settings of a network block (a NetworkConfig or its dump), defaults filled in."""
    get = (lambda k, d: network.get(k, d)) if isinstance(network, dict) else (lambda k, d: getattr(network, k, d))
    return dict(spec_input=get('spec_input', 'slots'), size_features=get('size_features', 'absolute'),
                device_model_features=bool(get('device_model_features', False)))


def any_transfer(network) -> bool:
    settings = transfer_settings(network)
    return (settings['spec_input'] == 'set' or settings['size_features'] == 'pdk_relative'
            or settings['device_model_features'])


def feature_schema(schema, network):
    """The feature schema of a network block: `schema` (the standard list or a PDK's) with w and l without a unit for
    PDK-relative sizes and four more columns for device model features. The version names both, so a model built
    with them loads only with them - and on any PDK."""
    settings = transfer_settings(network)
    if settings['size_features'] == 'pdk_relative':
        references = tuple(1.0 if name in SIZE_COLUMNS else ref for name, ref in zip(schema.parameters, schema.references))
        schema = replace(schema, version=schema.version + RELATIVE_SUFFIX, references=references)
    if settings['device_model_features']:
        schema = replace(schema, version=schema.version + MODEL_SUFFIX, parameters=schema.parameters + MODEL_COLUMNS,
                         references=schema.references + MODEL_REFERENCES)
    return schema


def describe_version(version) -> list:
    """Words for the input suffixes of a feature schema version (the saved-model window shows them)."""
    words = []
    if RELATIVE_SUFFIX in (version or ''):
        words.append('sizes relative to the PDK')
    if MODEL_SUFFIX in (version or ''):
        words.append('device model features')
    return words


# ------------------------------------------------------------------------------------------ the view
class NetworkView:
    """What the network sees of an observation (see the module text). `numbers`: device_models' {model: numbers} of
    the task's PDK; `descriptors`: spec_descriptors' {metric_id: description}; `vocabulary`: the run's PDK component
    list, applied last (it renames parameter columns)."""

    CAPACITY = 8192                       # as many distinct states as the learner's own input cache (record 7.221)

    def __init__(self, *, descriptors=None, numbers=None, relative_sizes=False, model_features=False, vocabulary=None):
        self.descriptors = None if descriptors is None else {k: tuple(float(x) for x in v) for k, v in descriptors.items()}
        self.numbers = dict(numbers or {})
        self.relative_sizes, self.model_features, self.vocabulary = bool(relative_sizes), bool(model_features), vocabulary
        identity = dict(descriptors=self.descriptors, numbers=self.numbers if (relative_sizes or model_features) else None,
                        relative_sizes=self.relative_sizes, model_features=self.model_features,
                        vocabulary=None if vocabulary is None else vocabulary.sha256)
        self.key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        self._seen, self._lock = OrderedDict(), threading.Lock()

    # ---- one graph
    def view_graph(self, graph):
        from analog_optimizer.graph.circuit_graph import CircuitGraph, ParameterBinding, ParameterValue, SourceSpan
        from analog_optimizer.models.inputs import SPEC_DESCRIPTOR_KEY
        if graph.metadata.get(VIEW_KEY) == self.key:
            return graph
        devices = {d.id: d for d in graph.devices}
        parameters = {device_id: dict(values) for device_id, values in graph.parameters.items()}
        groups = list(graph.parameter_groups)
        if self.relative_sizes:
            for device_id, values in parameters.items():
                for column, value in list(values.items()):
                    ref = self._reference(devices[device_id], column)
                    if ref is not None and value.valid:
                        values[column] = replace(value, value=value.value / ref)
            for i, group in enumerate(groups):
                if group.parameter_kind not in SIZE_COLUMNS:
                    continue
                own = [self._reference(devices[m.device_id], m.parameter) for m in group.members]
                if any(r is None for r in own):
                    continue
                scale = own[0]
                members = tuple(ParameterBinding(m.device_id, m.parameter, m.ratio * scale / r,
                                                 None if m.lower is None else m.lower / r,
                                                 None if m.upper is None else m.upper / r)
                                for m, r in zip(group.members, own))
                groups[i] = replace(group, value=group.value / scale, lower=group.lower / scale, upper=group.upper / scale,
                                    step=None if group.step is None else group.step / scale, members=members)
        if self.model_features:
            source = SourceSpan('network-view', 1)
            for device_id, device in devices.items():
                numbers = self.numbers.get(device.model_ref) if device.kind in MOS_KINDS else None
                for column, name in zip(MODEL_COLUMNS, ('vth0', 'u0', 'vsat', 'tox')):
                    if numbers and isinstance(numbers.get(name), (int, float)):
                        parameters[device_id][column] = ParameterValue('', float(numbers[name]), source)
        metadata = dict(graph.metadata)
        metadata[VIEW_KEY] = self.key
        if self.descriptors is not None:
            metadata[SPEC_DESCRIPTOR_KEY] = self.descriptors
        viewed = CircuitGraph(graph.circuit_id, list(graph.devices), list(graph.nets), list(graph.connections), parameters,
                              groups, list(graph.diagnostics), metadata, graph.schema_version)
        return self.vocabulary.view_graph(viewed) if self.vocabulary is not None else viewed

    def _reference(self, device, column):
        """The divisor of a device's width or length: its MOS model's minimum, else one micrometre (the standard
        list's own reference, so a capacitor's width reads as before)."""
        if column not in SIZE_COLUMNS:
            return None
        value = (self.numbers.get(device.model_ref) or {}).get(SIZE_COLUMNS[column]) if device.kind in MOS_KINDS else None
        return float(value) if isinstance(value, (int, float)) and value > 0 else 1e-6

    # ---- observations
    def view(self, observation):
        return replace(observation, graph=self.view_graph(observation.graph))

    def derive(self, digest):
        """The digest of a viewed observation from its recorded one: the view is a fixed function of it."""
        return hashlib.sha256(self.key.encode() + digest).digest()

    def view_known(self, observation, digest):
        with self._lock:
            found = self._seen.get(digest)
            if found is not None:
                self._seen.move_to_end(digest)
                return found
        viewed = self.view(observation)
        with self._lock:
            self._seen[digest] = viewed
            while len(self._seen) > self.CAPACITY:
                self._seen.popitem(last=False)
        return viewed


def learner_class(vocabulary=None, view=None):
    """The learner of a run: without a view, as before (the package's SACLearner, or the PDK list's view learner);
    with one, a subclass whose only change is that the network sees the view of every observation."""
    if view is None:
        return vocabulary_learner(vocabulary)
    from analog_optimizer.training.sac import SACLearner

    class NetworkViewLearner(SACLearner):
        network_view = view

        def batch(self, observations, *, digests=None):
            if digests is None:
                return super().batch([view.view(o) for o in observations])
            digests = list(digests)
            viewed = [view.view_known(o, d) for o, d in zip(observations, digests)]
            return super().batch(viewed, digests=[view.derive(d) for d in digests])
    return NetworkViewLearner


# ------------------------------------------------------------------------------------------ a run's inputs
class InputsUnavailable(ValueError):
    """The settings ask for something this task or its PDK cannot give, in words."""


def numbers_for(config, *, required=False):
    """device_models' numbers of the configuration's PDK (None when they cannot be read and not `required`)."""
    pdk_id = getattr(config.circuit, 'pdk_id', None)
    document = device_models.load(pdk_id) if pdk_id else None
    if document is None and required:
        raise InputsUnavailable(f'The device numbers of PDK {pdk_id or "(none named)"} cannot be read: load that PDK in the '
                                'PDK window (its model files are read from the copy Load PDK keeps).')
    return document


def prepared(config, vocabulary=None):
    """(NetworkView, the run's record of it) of a configuration; (None, None) without the transferable inputs."""
    if not any_transfer(config.run.network):
        return None, None
    settings = transfer_settings(config.run.network)
    descriptors = spec_descriptors.describe_specs(config) if settings['spec_input'] == 'set' else None
    needs_numbers = settings['size_features'] == 'pdk_relative' or settings['device_model_features']
    document = numbers_for(config, required=needs_numbers) if needs_numbers else None
    view = NetworkView(descriptors=descriptors, numbers=(document or {}).get('devices'),
                       relative_sizes=settings['size_features'] == 'pdk_relative',
                       model_features=settings['device_model_features'], vocabulary=vocabulary)
    return view, run_record(config, view, document)


def view_for(config, vocabulary=None):
    """The NetworkView of a configuration, or None when it uses none of the transferable inputs."""
    return prepared(config, vocabulary)[0]


def read_run_record(run_dir):
    record = read_json(Path(run_dir) / RUN_FILE, default=None)
    return record if isinstance(record, dict) and record.get('format') == FORMAT else None


def coverage(graph, document):
    """{'missing_sizes': [model, ...], 'missing_numbers': [model, ...]} of a graph's MOS models against device_models'
    numbers - names only, never the numbers."""
    devices = (document or {}).get('devices', {})
    models = sorted({d.model_ref for d in graph.devices if d.kind in MOS_KINDS})
    return dict(models=models,
                missing_sizes=[m for m in models if not all(isinstance(devices.get(m, {}).get(k), (int, float))
                                                            for k in ('lmin', 'wmin'))],
                missing_numbers=[m for m in models if not all(k in devices.get(m, {}) for k in ('vth0', 'u0', 'vsat', 'tox'))])


def run_record(config, view, document=None) -> dict:
    """What a run keeps in its folder (RUN_FILE): the settings, the spec descriptions and which PDK numbers it used (by
    the record's checksum - the numbers themselves stay in the PDK folder)."""
    return dict(format=FORMAT, **transfer_settings(config.run.network),
                operating_points=bool(config.run.network.operating_points),
                descriptor_version=None if view is None or view.descriptors is None else spec_descriptors.DESCRIPTOR_VERSION,
                spec_descriptors=None if view is None else view.descriptors,
                pdk_id=getattr(config.circuit, 'pdk_id', None),
                pdk_record_sha256=(document or {}).get('record_sha256'), view_key=None if view is None else view.key)


def maestro_dc_operating_point(config):
    """For a saved Maestro task: 'saved' when its test saves the DC operating point (dcOpInfo), 'added' when a run with
    operating-point inputs gets it added to the deck (recipes.with_dc_operating_point); None for any other task."""
    task_id = getattr(config.circuit, 'task_id', None) or ''
    if getattr(config.circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return None
    entry = profile_entry(task_id[len('real:'):])
    if entry is None or entry.get('recipe') != 'maestro':
        return None
    deck = read_json(Path(entry['directory']) / 'maestro_deck.json', default=None)
    if not isinstance(deck, dict):
        return None
    return 'saved' if has_dc_operating_point(deck.get('tail')) else 'added'
