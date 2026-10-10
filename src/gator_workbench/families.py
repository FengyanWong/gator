"""The device-family component list (record 7.298): one fixed list of device kinds that every PDK maps into by rule, the
list a new model is built with (user, 2026-10-10: the family list replaces the standard list for new models; models
trained with the standard list keep it and load as before).

Why a fixed list: the network's first layer holds one learned entry per kind, pin role and parameter column, so a list
that grew with every loaded PDK would break every saved model each time, and a PDK's own list (``pdk:<id>``) names kinds
no other PDK has. The families are what transfers: a second foundry's nMOS model and GPDK045's ``g45n1svt`` are both an nMOS. What
tells the variants of one family apart is numbers, not names (the device model features of ``network_inputs``).

- kinds: unknown, nmos, pmos, npn, pnp, diode, varactor, resistor, capacitor, inductor, vsource, isource;
- pin roles: drain, gate, source, bulk, collector, base, emitter, anode, cathode, positive, negative (and unknown);
- parameters: the standard eight (w, l, m, nf, r, c, ind, dc) and a junction device's `area`.

Each component of the run's PDK takes the family its PDK record gives it (``model_scan.classify_model``: by the Spectre
primitive of its model, never by its name), the roles of its pins and its parameters under their canonical names; a
part the record does not name (an ideal source, an analogLib resistor) keeps its own kind when that is a family, and a
component the rules could not classify is "unknown". Like a PDK list, the family list is applied at the network's input
only (``view``), and a run keeps its own copy (``network_vocabulary.json``) of the mapping its PDK gave at its start.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json

from . import pdk_record

NAME = 'families'
FORMAT = 'gator-family-list-v1'
VERSION = 'families-v1'
KINDS = ('unknown', 'nmos', 'pmos', 'npn', 'pnp', 'diode', 'varactor', 'resistor', 'capacitor', 'inductor', 'vsource',
         'isource')
ROLES = ('unknown', 'drain', 'gate', 'source', 'bulk', 'collector', 'base', 'emitter', 'anode', 'cathode', 'positive',
         'negative')
PARAMETERS = ('w', 'l', 'm', 'nf', 'r', 'c', 'ind', 'dc', 'area')
REFERENCES = (1e-6, 1e-6, 1.0, 1.0, 1e3, 1e-12, 1e-9, 1.0, 1.0)
_POLAR = {('mos', 'n'): 'nmos', ('mos', 'p'): 'pmos', ('bjt', 'npn'): 'npn', ('bjt', 'pnp'): 'pnp'}


def family_kind(family, polarity=None) -> str:
    """The kind of a PDK record's family (and polarity): a MOS or bipolar needs its polarity; 'other' is unknown."""
    if family in ('mos', 'bjt'):
        return _POLAR.get((family, polarity), 'unknown')
    return family if family in KINDS else 'unknown'


def schema():
    from analog_optimizer.graph.pyg_converter import FeatureSchema          # lazy: the optimizer imports torch
    return FeatureSchema(version=VERSION, device_kinds=KINDS, terminal_roles=ROLES, net_roles=FeatureSchema().net_roles,
                         parameters=PARAMETERS, references=REFERENCES)


def block_for(pdk_id) -> dict:
    """The family list's mapping for one PDK's components, from its loaded record (no mapping when it is not loaded)."""
    record = pdk_record.load_record(pdk_id) if pdk_id else None      # read through the module: tests patch it
    devices = {}
    for model, device in sorted(((record or {}).get('devices') or {}).items()):
        devices[model] = dict(
            kind=family_kind(device.get('family'), device.get('polarity')), family=device.get('family'),
            polarity=device.get('polarity'), roles=[pin['role'] if pin.get('role') in ROLES else 'unknown' for pin in device['pins']],
            columns={p['name']: p['canonical'] for p in device.get('parameters', ())
                     if p.get('numeric') and p.get('canonical') in PARAMETERS})
    body = dict(format=FORMAT, name=NAME, version=VERSION, pdk_id=pdk_id, record_sha256=(record or {}).get('sha256'),
                devices=devices)
    return dict(body, sha256=hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest())


class FamilyList:
    """The family list as a run uses it (the same contract as ``vocabulary.Vocabulary``: name, label, schema, view)."""

    name = NAME

    def __init__(self, block):
        if not isinstance(block, dict) or block.get('format') != FORMAT:
            raise ValueError('Not a family list')
        self.block, self.devices = block, block['devices']
        self.pdk_id, self.sha256, self.version = block.get('pdk_id'), block['sha256'], VERSION
        self.schema = schema()

    @property
    def label(self):
        return f'device families ({len(KINDS) - 1} kinds)'

    def view_graph(self, graph):
        """The graph as the network sees it (a new object; `graph` is not changed)."""
        from analog_optimizer.graph.circuit_graph import CircuitGraph   # lazy: the optimizer imports torch
        devices, roles, renames = [], {}, {}
        for device in graph.devices:
            entry = self.devices.get(device.model_ref)
            if entry is not None and len(entry['roles']) == len(device.terminals):
                devices.append(replace(device, kind=entry['kind']))
                roles[device.id] = entry['roles']
                renames[device.id] = entry['columns']
            else:
                devices.append(device if device.kind in KINDS else replace(device, kind='unknown'))
        connections = [replace(c, role=roles[c.device_id][c.ordinal]) if c.device_id in roles
                       else c if c.role in ROLES else replace(c, role='unknown') for c in graph.connections]
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
        return replace(observation, graph=self.view_graph(observation.graph))


def coverage(graph, family_list) -> dict:
    """How the family list sees a circuit: {kind: count} of its devices (names of what reads as unknown kept)."""
    seen = family_list.view_graph(graph)
    counts = {}
    for device in seen.devices:
        counts[device.kind] = counts.get(device.kind, 0) + 1
    return dict(kinds=counts, unknown=[d.model_ref for d in seen.devices if d.kind == 'unknown'])
