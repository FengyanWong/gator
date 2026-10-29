"""The network's component list (vocabulary): the standard list or a loaded PDK's, the one a run uses and keeps a copy of
(pdk.json in the run folder), the learner class it is built with, and its view of a circuit graph.

Moved from pdk.py by the refactoring (docs/plan-refactoring.md); pdk.py re-exports every name.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from . import families
from .pdk_record import PdkError, STANDARD, VOCABULARY_FORMAT, label, load_record, standard_schema
from .storage.atomic import read_json, write_json

_PDK_PREFIX_CHARS = 4



# ------------------------------------------------------------------------------------------ the network's view
class Vocabulary:
    """A loaded PDK's component list, as the learner uses it. Built from the `vocabulary` block of a record (or of a
    run's own copy), never from the live PDK folder: what a run used is fixed at its start."""

    def __init__(self, block: dict) -> None:
        if not isinstance(block, dict) or block.get('format') != VOCABULARY_FORMAT:
            raise PdkError('Not a PDK component list')
        self.block = block
        self.pdk_id, self.sha256, self.version = block['pdk_id'], block['sha256'], block['version']
        self.devices = block['devices']
        from analog_optimizer.graph.pyg_converter import FeatureSchema
        self.schema = FeatureSchema(version=block['version'], device_kinds=tuple(block['device_kinds']),
                                    terminal_roles=tuple(block['terminal_roles']), net_roles=tuple(block['net_roles']),
                                    parameters=tuple(block['parameters']),
                                    references=tuple(float(r) for r in block['references']))
        self.name = f'pdk:{self.pdk_id}'

    @property
    def label(self) -> str:
        return label(self.block)

    def view_graph(self, graph):
        """The graph as the network sees it (a new object; `graph` is not changed)."""
        from analog_optimizer.graph.circuit_graph import CircuitGraph
        devices, roles, renames = [], {}, {}
        for device in graph.devices:
            entry = self.devices.get(device.model_ref)
            if entry is None or len(entry['roles']) != len(device.terminals):
                devices.append(device)
                continue
            devices.append(replace(device, kind=entry['kind']))
            roles[device.id] = entry['roles']
            renames[device.id] = entry['columns']
        connections = [replace(c, role=roles[c.device_id][c.ordinal]) if c.device_id in roles else c
                       for c in graph.connections]
        parameters = {}
        for device_id, values in graph.parameters.items():
            columns = renames.get(device_id)
            if not columns:
                parameters[device_id] = values
                continue
            moved = {}
            for key, value in values.items():
                target = columns.get(key, key)
                moved[target if target not in moved else key] = value
            parameters[device_id] = moved
        groups = []
        for group in graph.parameter_groups:
            members = tuple(replace(m, parameter=renames[m.device_id].get(m.parameter, m.parameter))
                            if m.device_id in renames else m for m in group.members)
            groups.append(replace(group, members=members) if members != group.members else group)
        return CircuitGraph(graph.circuit_id, devices, list(graph.nets), connections, parameters, groups,
                            list(graph.diagnostics), graph.metadata, graph.schema_version)

    def view(self, observation):
        """Return an observation whose graph uses this vocabulary's network representation."""
        return replace(observation, graph=self.view_graph(observation.graph))


def parse_models(record) -> dict:
    """The parser's device mappings (``ParserConfig.models``) for every component of a loaded PDK, in the STANDARD
    list's terms: the kind and pin roles of the eight generic kinds, `unknown` for a family that list has no kind for
    (bipolar, diode). A circuit graph thus keeps what the standard list reads - with its pins named - and only the
    network's view adds the PDK kinds (Vocabulary.view). Parameters keep their netlist names, except where a name means
    something else in the standard list (an inductor's radius `r` becomes `rad`; its netlist name is kept for writing)."""
    models = {}
    for model, device in (record or {}).get('devices', {}).items():
        names = [pin['name'] for pin in device['pins']]
        aliases = {p['name']: p['canonical'] for p in device['parameters'] if p['numeric'] and p.get('canonical')}
        if not names or len(set(names)) != len(names) or len(set(aliases.values())) != len(aliases):
            continue
        models[model] = dict(kind=device['standard_kind'], terminals=names, roles=device['standard_roles'],
            parameters=aliases)
    return models


def vocabulary_of_record(record) -> Vocabulary:
    return Vocabulary(record['vocabulary'])


def parameter_facts(record, model_ref, name):
    """Return a PDK record's entry for one device parameter, found by name or canonical alias, or None."""
    device = (record or {}).get('devices', {}).get(model_ref)
    if device is None:
        return None
    return next((p for p in device['parameters'] if name in (p['name'], p.get('canonical'))), None)


# ------------------------------------------------------------------------------------------ learner
def learner_class(vocabulary) -> type:
    """The optimizer's own SACLearner, or - with a PDK list - a subclass whose only change is that the observations are
    shown to the network through the PDK's view. Weights, losses, saving and the contract are the package's own."""
    from analog_optimizer.training.sac import SACLearner
    if vocabulary is None:
        return SACLearner

    class PdkViewLearner(SACLearner):
        """A SAC learner that batches observations through the selected PDK vocabulary."""
        def batch(self, observations, *, digests=None):
            # The network sees new objects (the PDK's view): digests of the recorded observations do not describe
            # them, so the input cache keys the viewed observations by their own content (record 7.221).
            """Batch the observations as the PDK view shows them; `digests` is ignored."""
            return super().batch([vocabulary.view(o) for o in observations])
    return PdkViewLearner


# ------------------------------------------------------------------------------------------ runs
RUN_FILE = 'network_vocabulary.json'


def requested(config) -> str:
    """Read the requested network vocabulary, falling back to the standard vocabulary."""
    return getattr(getattr(config.run, 'network', None), 'vocabulary', STANDARD) or STANDARD


def current_vocabulary(name, pdk_id=None) -> Vocabulary | None:
    """`standard` -> None; `pdk:<id>` -> the currently loaded version of that PDK (PdkError when it is not loaded);
    `families` -> the device-family list, mapped from the loaded record of `pdk_id` (the task's PDK) when there is one."""
    if name in (None, '', STANDARD):
        return None
    if name == families.NAME:
        return families.FamilyList(families.block_for(pdk_id))
    if not name.startswith('pdk:'):
        raise PdkError(f'Unknown component list {name!r}')
    record = load_record(name[_PDK_PREFIX_CHARS:])
    if record is None:
        raise PdkError(
            f'PDK {name[_PDK_PREFIX_CHARS:]} is not loaded. Read it in the Virtuoso window first ("PDK '
            f'window..." reads one by name).')
    return vocabulary_of_record(record)


def run_vocabulary(run_dir) -> Vocabulary | None:
    """The component list a run was started with (its own copy), or None for the standard list."""
    block = read_json(Path(run_dir) / RUN_FILE, default=None)
    if block is None:
        return None
    if isinstance(block, dict) and block.get('format') == families.FORMAT:      # the family list (record 7.298)
        return families.FamilyList(block)
    return Vocabulary(block)


def write_run_vocabulary(run_dir, vocabulary) -> None:
    """Persist a selected vocabulary's block in the run directory when one is present."""
    if vocabulary is not None:
        write_json(Path(run_dir) / RUN_FILE, vocabulary.block)


def schema_label(feature_schema) -> str:
    """A saved model's component list in words, from the feature schema its contract records, with the transferable
    inputs of record 7.298 its version names after a "+" (sizes relative to the PDK, device model features)."""
    version, _, inputs = (feature_schema or {}).get('version', '').partition('+')
    extra = ''.join(f', {words}' for words in (('sizes relative to the PDK',) if 'pdk-relative-sizes' in inputs else ())
                    + (('device model features',) if 'device-model-features' in inputs else ())
                    # record 7.317
                    + (('bench sources on their own scales',) if 'bench-features' in inputs else ())
                    + (('net tags by rule',) if 'net-roles-by-rule' in inputs else ())
                    + (('operating-point ratios',) if 'op-ratios' in inputs else ()))
    if version == families.VERSION:
        return f'device families ({len(families.KINDS) - 1} kinds)' + extra
    if version.startswith('pdk-'):
        kinds = len((feature_schema or {}).get('device_kinds') or ()) - len(standard_schema().device_kinds)
        return (
            f"PDK {version[_PDK_PREFIX_CHARS:].rsplit('-', 1)[0]} ({kinds} components, version "
            f"{version.rsplit('-', 1)[-1][:8]}){extra}"
        )
    return 'standard (8 generic kinds)' + extra


def run_vocabulary_facts(run_dir, feature_schema=None) -> dict:
    """The component list a run's model was made with, as the RL model window shows it: its name, label, PDK and
    checksum, and whether that PDK is loaded here (a model of a PDK's list loads only with that list).
    `feature_schema`: the one the chosen save point's contract records. A folder that keeps no list of its own - an
    offline model published before record 7.319 - is the family list when that schema says so, not the standard one."""
    own = run_vocabulary(run_dir)
    if own is None and (feature_schema or {}).get('version', '').partition('+')[0] == families.VERSION:
        # the list itself: each task's PDK is mapped at its start
        own = families.FamilyList(families.block_for(None))
    return dict(name=own.name if own else STANDARD, label=own.label if own else label(None),
                pdk_id=own.pdk_id if own else None, sha256=own.sha256 if own else None,
                loaded=bool(own is None or own.name == families.NAME or load_record(own.pdk_id) is not None))
