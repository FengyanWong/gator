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

The second build (record 7.317; ``bench_features`` "relative", ``net_roles`` "rule", ``operating_point_ratios``; the
page sets the three with the first three: "Network inputs: Transferable 2") adds, in the same view:

- bench features "relative": what the testbench's sources say, on scales of their own. A current source's DC value
  moves from the column it shared with voltages (divided by 1, so 50 uA read as 0.00005) to ``idc`` (in uA); a voltage
  source's DC value is also given as a share of the supply (``vrel``; the supply itself reads 1); a source's AC
  magnitude (``ac``) and the two levels of a step (``ilow``/``ihigh`` in uA, ``vlow``/``vhigh`` as a share of the
  supply) become columns; a DC value the netlist gives as a variable of the test (``dc=il``) is read from the test's
  variables. The supply is found on the graph by one rule (``bench_of_graph``);
- net roles "rule": every net is tagged by one rule on the graph, whatever its task tagged: ground, supply, input (a
  source that carries a signal drives it), output (an active spec's probe reads its voltage), bias (a DC source other
  than the supply drives it). A net may carry several tags; every other net is "normal";
- operating-point ratios: four columns per MOS device from the design's own operating point - gm/Id, gm/gds,
  |Vgs| - |Vth| and |Vds|/|Vdsat| - numbers that mean the same in every PDK; the simulator's region is the network's
  own operating-point input (its five region columns only, unless the raw operating points are on too). A run with
  them reads operating points as a run with ``operating_points`` does; a design without them shows them as missing.

A viewed observation carries a marker, so it is never viewed twice. The view of a replayed observation is kept by its
digest (the replay's own, record 7.221): a learner step views each distinct state once.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
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
# The second build (record 7.317)
BENCH_SUFFIX = '+bench-features-v1'
NET_SUFFIX = '+net-roles-by-rule-v1'
RATIO_SUFFIX = '+op-ratios-v1'
BENCH_COLUMNS = ('idc', 'vrel', 'ac', 'ilow', 'ihigh', 'vlow', 'vhigh')
BENCH_REFERENCES = (1e-6, 1.0, 1.0, 1e-6, 1e-6, 1.0, 1.0)      # uA, share of the supply, AC magnitude, uA, uA, shares
RATIO_COLUMNS = ('op_gm_id', 'op_gain', 'op_vov', 'op_sat')
RATIO_REFERENCES = (10.0, 10.0, 0.1, 1.0)                     # 1/V, gm/gds, V of overdrive, |Vds|/|Vdsat|
REGION_COLUMNS = ('region_off', 'region_triode', 'region_sat', 'region_subth', 'region_breakdown')    # of the optimizer's own list
SOURCE_KINDS = ('vsource', 'isource')
RULE_ROLES = ('ground', 'supply', 'input', 'output', 'bias')  # the order a net's tags are written in
SECOND_BUILD_DEFAULTS = dict(bench_features='absolute', net_roles='task', operating_point_ratios=False)
RUN_FILE = 'network_inputs.json'
FORMAT = 'gator-network-inputs-v1'


def transfer_settings(network) -> dict:
    """The network-input settings of a network block (a NetworkConfig or its dump), defaults filled in: the three of
    record 7.298 and the three of the second build (record 7.317)."""
    get = (lambda k, d: network.get(k, d)) if isinstance(network, dict) else (lambda k, d: getattr(network, k, d))
    return dict(spec_input=get('spec_input', 'slots'), size_features=get('size_features', 'absolute'),
                device_model_features=bool(get('device_model_features', False)),
                bench_features=get('bench_features', 'absolute'), net_roles=get('net_roles', 'task'),
                operating_point_ratios=bool(get('operating_point_ratios', False)))


def second_build(network) -> bool:
    """Whether a network block asks for any input of the second build (record 7.317)."""
    settings = transfer_settings(network)
    return any(settings[key] != default for key, default in SECOND_BUILD_DEFAULTS.items())


def as_recorded(settings) -> dict:
    """Settings as a record keeps them: a second-build setting at its default is left out, so the records of runs and
    pools without the second build read exactly as they did before it existed."""
    return {key: value for key, value in settings.items() if SECOND_BUILD_DEFAULTS.get(key, object()) != value}


def reads_operating_points(network) -> bool:
    """Whether a run with this network block reads each design's operating points (the raw input or the ratios)."""
    get = (lambda k: network.get(k)) if isinstance(network, dict) else (lambda k: getattr(network, k, None))
    return bool(get('operating_points') or get('operating_point_ratios'))


def reads_raw_operating_points(network) -> bool:
    """Check whether dictionary or object settings request raw operating-point inputs."""
    get = (lambda k: network.get(k)) if isinstance(network, dict) else (lambda k: getattr(network, k, None))
    return bool(get('operating_points'))


def any_transfer(network) -> bool:
    """Check whether any transferable network-input representation is enabled."""
    settings = transfer_settings(network)
    return (settings['spec_input'] in ('set', 'structured') or settings['size_features'] == 'pdk_relative'
            or settings['device_model_features'] or second_build(settings))


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
    if settings['bench_features'] == 'relative':
        schema = replace(schema, version=schema.version + BENCH_SUFFIX, parameters=schema.parameters + BENCH_COLUMNS,
                         references=schema.references + BENCH_REFERENCES)
    if settings['net_roles'] == 'rule':                 # the same columns, another meaning: the version alone tells
        schema = replace(schema, version=schema.version + NET_SUFFIX)
    if settings['operating_point_ratios']:
        schema = replace(schema, version=schema.version + RATIO_SUFFIX, parameters=schema.parameters + RATIO_COLUMNS,
                         references=schema.references + RATIO_REFERENCES)
        if not schema.op_columns and reads_raw_operating_points(network):     # both inputs on, and a caller that did not
            from analog_optimizer.graph.pyg_converter import OPERATING_POINT_COLUMNS, OPERATING_POINT_REFERENCES   # add them itself
            schema = replace(schema, op_columns=OPERATING_POINT_COLUMNS, op_references=OPERATING_POINT_REFERENCES)
        if not schema.op_columns:                       # the region only; the raw numbers stay with `operating_points`
            schema = replace(schema, op_columns=REGION_COLUMNS, op_references=(1.0,) * len(REGION_COLUMNS))
    return schema


def describe_version(version) -> list:
    """Words for the input suffixes of a feature schema version (the saved-model window shows them)."""
    words = []
    if RELATIVE_SUFFIX in (version or ''):
        words.append('sizes relative to the PDK')
    if MODEL_SUFFIX in (version or ''):
        words.append('device model features')
    if BENCH_SUFFIX in (version or ''):
        words.append('bench sources on their own scales')
    if NET_SUFFIX in (version or ''):
        words.append('net tags by rule')
    if RATIO_SUFFIX in (version or ''):
        words.append('operating-point ratios')
    return words


# ------------------------------------------------------------------------------------------ the bench, read off a graph
@dataclass(frozen=True)
class BenchSource:
    """One source of the testbench: its nets that are not ground, its DC value (a variable of the test resolved), and
    whether it carries a signal (an AC magnitude, a waveform, or two different step levels)."""
    id: str
    kind: str
    nets: tuple
    grounded: bool
    dc: float | None
    signal: bool


@dataclass(frozen=True)
class GraphBench:
    # Graph-derived ground, supply and source facts used to construct transferable bench features.
    ground: frozenset = frozenset()
    supply_source: str | None = None
    supply_net: str | None = None
    supply_v: float | None = None
    sources: tuple = ()


def _number(values, key, variables=None):
    """A source parameter as a number: its value, else the test variable its text names - by the name as written, as
    Spectre reads it (BIAS and bias are two variables); None when neither is known."""
    found = values.get(key)
    if found is None:
        return None
    if found.valid:
        return float(found.value)
    named = (variables or {}).get((found.raw or '').strip())
    return float(named) if isinstance(named, (int, float)) and not isinstance(named, bool) and math.isfinite(named) else None


def _carries_signal(values, variables=None):
    mag, low, high = (_number(values, key, variables) for key in ('mag', 'val0', 'val1'))
    kind = values.get('type')
    waveform = (kind.raw or '').strip().strip('"').lower() if kind is not None else ''
    return bool(mag) or waveform not in ('', 'dc') or (low is not None and high is not None and low != high)


def bench_of_graph(graph, variables=None) -> GraphBench:
    """The testbench as the second build reads it (record 7.317), from the graph alone, so every task - Virtuoso,
    ngspice or a stand-in - is read by the same rule:

    - ground: the nets the task tags as ground, and nets named 0 or gnd!;
    - sources: the voltage and current sources at the top level (a source inside the circuit is part of the circuit);
    - the supply: among the top-level voltage sources with one pin on ground and a DC value other than 0, the one on a
      net the task itself tags as the supply; else the one with the largest DC value; of equals the one whose net
      touches the most pins (a supply rail feeds many devices, a reference one gate); of equals the first.

    Nothing is read from a name. `variables`: the test's design variables ({name: number}), for a DC value the netlist
    gives as one of them."""
    ground = frozenset(n.id for n in graph.nets if 'ground' in n.roles or n.id in ('0', 'gnd!'))
    tagged = {n.id for n in graph.nets if 'supply' in n.roles}
    pins, wired = Counter(c.net_id for c in graph.connections), {}
    for connection in sorted(graph.connections, key=lambda c: c.ordinal):
        wired.setdefault(connection.device_id, []).append(connection.net_id)
    sources, best = [], None
    for position, device in enumerate(graph.devices):
        if device.kind not in SOURCE_KINDS or '/' in device.id:
            continue
        values, nets = graph.parameters[device.id], wired.get(device.id, [])
        others = tuple(n for n in nets if n not in ground)
        grounded = len(nets) == 2 and len(others) == 1
        dc = _number(values, 'dc', variables)
        sources.append(BenchSource(device.id, device.kind, others, grounded, dc, _carries_signal(values, variables)))
        if device.kind == 'vsource' and grounded and dc:
            rank = (others[0] in tagged, abs(dc), pins[others[0]], -position)
            if best is None or rank > best[0]:
                best = (rank, device.id, others[0], abs(dc))
    if best is None:
        return GraphBench(ground, sources=tuple(sources))
    return GraphBench(ground, best[1], best[2], best[3], tuple(sources))


def ruled_roles(graph, bench, measured_nets=()) -> dict:
    """{net: its tags in RULE_ROLES order} by the one rule of the second build (a net without a tag is left out):
    ground; supply; input - a net a signal-carrying source drives; output - a net an active spec's probe reads; bias - a
    net a DC source other than the supply drives (a reference, a common-mode level, a bias or load current; a 0 V
    voltage source is a probe and tags nothing)."""
    nets, tags = {n.id for n in graph.nets}, {}
    def tag(net, role):
        if net in nets:
            tags.setdefault(net, set()).add(role)
    for net in bench.ground:
        tag(net, 'ground')
    if bench.supply_net is not None:
        tag(bench.supply_net, 'supply')
    for net in measured_nets:
        if net not in bench.ground:
            tag(net, 'output')
    for source in bench.sources:
        if source.signal:
            for net in source.nets:
                tag(net, 'input')
        elif source.id != bench.supply_source and not (source.kind == 'vsource' and source.dc == 0):
            for net in source.nets:
                if net != bench.supply_net:
                    tag(net, 'bias')
    return {net: tuple(role for role in RULE_ROLES if role in found) for net, found in tags.items()}


_ASSIGNMENT = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\s=]+)')


def variables_of_deck(deck) -> dict:
    """{name: number} of a Maestro deck's design variables (the `parameters` lines of its head), without the ones an
    analysis sweeps (`param=<name>` in its tail): a swept variable has no one value. Names are kept as written:
    Spectre tells BIAS from bias (until record 7.319 they were put in lower case, and two such variables read as one)."""
    if not isinstance(deck, dict) or not isinstance(deck.get('head'), str):
        return {}
    tail, found = deck.get('tail') if isinstance(deck.get('tail'), str) else '', {}
    for line in deck['head'].replace('\\\n', ' ').splitlines():
        if not line.strip().startswith('parameters'):
            continue
        for name, text in _ASSIGNMENT.findall(line.strip()[len('parameters'):]):
            try:
                value = spec_descriptors._number(text.strip('"'))
            except (ValueError, IndexError):
                continue
            if math.isfinite(value) and not re.search(r'\bparam\s*=\s*' + re.escape(name) + r'\b', tail):
                found[name] = value
    return found


def bench_variables(config) -> dict:
    """The design variables of a saved Maestro task's test (its profile's deck), or {} for any other task."""
    task_id = getattr(config.circuit, 'task_id', None) or ''
    if getattr(config.circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return {}
    entry = profile_entry(task_id[len('real:'):])
    if entry is None:
        return {}
    return variables_of_deck(read_json(Path(entry['directory']) / 'maestro_deck.json', default=None))


def _keyed(variables) -> dict:
    """The test variables as a view's key holds them: in lower case, as every key made before record 7.319 held them,
    while that still tells them apart - the view then shows what it showed, and the runs made before keep their key -
    and as written when two differ only in case (such a view read both as one before, so its key rightly moves)."""
    lowered = {name.lower(): value for name, value in variables.items()}
    return lowered if len(lowered) == len(variables) else dict(variables)


# ------------------------------------------------------------------------------------------ the view
class NetworkView:
    """What the network sees of an observation (see the module text). `numbers`: device_models' {model: numbers} of
    the task's PDK; `descriptors`: spec_descriptors' {metric_id: description}; `vocabulary`: the run's PDK component
    list, applied last (it renames parameter columns). The second build (record 7.317): `bench_features` - the sources on
    their own scales, with `variables` = the test's design variables; `net_rule` - net tags by rule, with
    `measured_nets` = the nets the active specs' probes read; `op_ratios` - the operating-point ratios of an
    observation's own operating points."""

    CAPACITY = 8192                       # as many distinct states as the learner's own input cache (record 7.221)

    def __init__(self, *, descriptors=None, numbers=None, relative_sizes=False, model_features=False, vocabulary=None,
                 bench_features=False, net_rule=False, op_ratios=False, measured_nets=(), variables=None, programs=None):
        self.programs = programs
        self.descriptors = None if descriptors is None else {k: tuple(float(x) for x in v) for k, v in descriptors.items()}
        self.numbers = dict(numbers or {})
        self.relative_sizes, self.model_features, self.vocabulary = bool(relative_sizes), bool(model_features), vocabulary
        self.bench_features, self.net_rule, self.op_ratios = bool(bench_features), bool(net_rule), bool(op_ratios)
        self.measured_nets = tuple(sorted(set(measured_nets))) if self.net_rule else ()
        self.variables = {str(k): float(v) for k, v in (variables or {}).items()} if (self.bench_features or self.net_rule) else {}
        identity = dict(descriptors=self.descriptors, numbers=self.numbers if (relative_sizes or model_features) else None,
                        relative_sizes=self.relative_sizes, model_features=self.model_features,
                        vocabulary=None if vocabulary is None else vocabulary.sha256)
        if programs is not None:
            identity['measurement_programs'] = programs
        if self.bench_features or self.net_rule or self.op_ratios:      # only then: a view without them keeps its key
            identity['second_build'] = dict(bench_features=self.bench_features, net_rule=self.net_rule, op_ratios=self.op_ratios,
                                            measured_nets=list(self.measured_nets), variables=_keyed(self.variables))
        self.key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        self._seen, self._lock = OrderedDict(), threading.Lock()

    # ---- one graph
    def view_graph(self, graph, operating_points=None):
        """`operating_points`: the observation's own ({device: {quantity: number}}), for the operating-point ratios; a
        graph viewed without them (a check of a task before any simulation) shows the ratios as missing."""
        from analog_optimizer.graph.circuit_graph import CircuitGraph, ParameterBinding, ParameterValue, SourceSpan
        from analog_optimizer.models.inputs import SPEC_DESCRIPTOR_KEY
        if graph.metadata.get(VIEW_KEY) == self.key:
            return graph
        devices = {d.id: d for d in graph.devices}
        parameters = {device_id: dict(values) for device_id, values in graph.parameters.items()}
        groups = list(graph.parameter_groups)
        nets = list(graph.nets)
        bench = bench_of_graph(graph, self.variables) if (self.bench_features or self.net_rule) else None
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
        if self.bench_features:
            self._bench_columns(graph, parameters, bench, lambda value: ParameterValue('', float(value), SourceSpan('network-view', 1)))
        if self.net_rule:
            roles = ruled_roles(graph, bench, self.measured_nets)
            nets = [replace(net, roles=roles.get(net.id, ('normal',)), role_source='network-view') for net in nets]
        if self.op_ratios and operating_points:
            self._ratio_columns(devices, parameters, operating_points,
                                lambda value: ParameterValue('', float(value), SourceSpan('network-view', 1)))
        metadata = dict(graph.metadata)
        metadata[VIEW_KEY] = self.key
        if self.descriptors is not None:
            metadata[SPEC_DESCRIPTOR_KEY] = self.descriptors
        if self.programs is not None:
            from analog_optimizer.models.measurement_program import PROGRAM_KEY
            metadata[PROGRAM_KEY] = self.programs
        viewed = CircuitGraph(graph.circuit_id, list(graph.devices), nets, list(graph.connections), parameters,
                              groups, list(graph.diagnostics), metadata, graph.schema_version)
        return self.vocabulary.view_graph(viewed) if self.vocabulary is not None else viewed

    def _bench_columns(self, graph, parameters, bench, shown):
        """The sources on their own scales (see the module text). A value a parameter row varies stays where it is: the
        row and its devices must keep agreeing."""
        bound = {(m.device_id, m.parameter) for group in graph.parameter_groups for m in group.members}
        supply = bench.supply_v
        for device in graph.devices:
            if device.kind not in SOURCE_KINDS:
                continue
            values = parameters[device.id]
            dc, mag, low, high = (_number(values, key, self.variables) for key in ('dc', 'mag', 'val0', 'val1'))
            if mag is not None:
                values['ac'] = shown(mag)
            if device.kind == 'isource':
                if dc is not None and (device.id, 'dc') not in bound:
                    values.pop('dc')                    # amperes leave the column of volts
                    values['idc'] = shown(dc)
                for column, level in (('ilow', low), ('ihigh', high)):
                    if level is not None:
                        values[column] = shown(level)
                continue
            if dc is not None and (device.id, 'dc') not in bound and not values['dc'].valid:
                values['dc'] = shown(dc)                # a DC value read from the test's variables
            if supply:
                for column, level in (('vrel', dc), ('vlow', low), ('vhigh', high)):
                    if level is not None:
                        values[column] = shown(level / supply)

    def _ratio_columns(self, devices, parameters, operating_points, shown):
        """gm/Id, gm/gds, |Vgs| - |Vth| and |Vds|/|Vdsat| of every MOS device that has the numbers; a ratio whose
        numbers are missing, or whose divisor is 0, is left out (the network then sees it as missing)."""
        for device_id, quantities in operating_points.items():
            device = devices.get(device_id)
            if device is None or device.kind not in MOS_KINDS or not isinstance(quantities, dict):
                continue
            def number(key):
                value = quantities.get(key)
                return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
            ids, gm, gds, vgs, vds, vth, vdsat = (number(key) for key in ('ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat'))
            found = dict(op_gm_id=abs(gm) / abs(ids) if gm is not None and ids else None,
                         op_gain=abs(gm) / abs(gds) if gm is not None and gds else None,
                         op_vov=abs(vgs) - abs(vth) if vgs is not None and vth is not None else None,
                         op_sat=abs(vds) / abs(vdsat) if vds is not None and vdsat else None)
            for column, value in found.items():
                if value is not None and math.isfinite(value):
                    parameters[device_id][column] = shown(value)

    def _reference(self, device, column):
        """The divisor of a device's width or length: its MOS model's minimum, else one micrometre (the standard
        list's own reference, so a capacitor's width reads as before)."""
        if column not in SIZE_COLUMNS:
            return None
        value = (self.numbers.get(device.model_ref) or {}).get(SIZE_COLUMNS[column]) if device.kind in MOS_KINDS else None
        return float(value) if isinstance(value, (int, float)) and value > 0 else 1e-6

    # ---- observations
    def view(self, observation):
        """Return an observation with its graph transformed into the configured network view."""
        return replace(observation, graph=self.view_graph(observation.graph, getattr(observation, 'operating_points', None)))

    def derive(self, digest):
        """The digest of a viewed observation from its recorded one: the view is a fixed function of it."""
        return hashlib.sha256(self.key.encode() + digest).digest()

    def view_known(self, observation, digest):
        """Reuse or cache a viewed observation by its replay digest."""
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
        """A SAC learner that applies the configured network view before batching observations."""
        network_view = view

        def batch(self, observations, *, digests=None):
            """Batch viewed observations with derived digests when replay identities are available."""
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
    descriptors = spec_descriptors.describe_specs(config) if settings['spec_input'] in ('set', 'structured') else None
    # lazy: load the measurement-program compiler when preparing transferable network inputs.
    from .spec_programs import describe_programs
    programs = describe_programs(config) if settings['spec_input'] == 'structured' else None
    needs_numbers = settings['size_features'] == 'pdk_relative' or settings['device_model_features']
    document = numbers_for(config, required=needs_numbers) if needs_numbers else None
    bench, rule = settings['bench_features'] == 'relative', settings['net_roles'] == 'rule'
    view = NetworkView(descriptors=descriptors, programs=programs, numbers=(document or {}).get('devices'),
                       relative_sizes=settings['size_features'] == 'pdk_relative',
                       model_features=settings['device_model_features'], vocabulary=vocabulary,
                       bench_features=bench, net_rule=rule, op_ratios=settings['operating_point_ratios'],
                       measured_nets=spec_descriptors.measured_nets(config) if rule else (),
                       variables=bench_variables(config) if (bench or rule) else None)
    return view, run_record(config, view, document)


def view_for(config, vocabulary=None):
    """The NetworkView of a configuration, or None when it uses none of the transferable inputs."""
    return prepared(config, vocabulary)[0]


def read_run_record(run_dir):
    """Read the run's network-input record only when its stored format is recognized."""
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
    record = dict(format=FORMAT, **as_recorded(transfer_settings(config.run.network)),
                  operating_points=bool(config.run.network.operating_points),
                  descriptor_version=None if view is None or view.descriptors is None else spec_descriptors.DESCRIPTOR_VERSION,
                  spec_descriptors=None if view is None else view.descriptors,
                  pdk_id=getattr(config.circuit, 'pdk_id', None),
                  pdk_record_sha256=(document or {}).get('record_sha256'), view_key=None if view is None else view.key)
    if view is not None and second_build(config.run.network):          # record 7.317: what the rule was given
        record['second_build'] = dict(measured_nets=list(view.measured_nets), test_variables=sorted(view.variables))
    if view is not None and view.programs is not None:
        from analog_optimizer.models.measurement_program import PROGRAM_VERSION
        record['measurement_programs'] = dict(version=PROGRAM_VERSION, specs=view.programs)
    return record


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
