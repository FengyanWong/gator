"""The structure of a SAVED RL model as a table: every layer with its type, shape and parameter count.

Read-only and tensor-only. ``model_weights.pt`` is loaded with ``weights_only=True`` after its SHA-256 matched
``metadata.json``; nothing is unpickled and nothing is plotted.

Layer TYPES and the "never used" flag come from REBUILDING the network from the contract stored in the
checkpoint (feature schema, goal/spec schema, model config). They are reported only when the rebuilt network
holds exactly the saved tensors - same names, same shapes (``types_verified``). Otherwise the table still lists
every saved tensor, grouped by layer, without types: a guess is never shown as a fact.

What a layer does (``role``) is a plain-language line per layer name, written from
``analog_optimizer.models.encoders.CircuitEncoder.forward``; a test pins that every layer of every encoder has one.
"""
from __future__ import annotations

from pathlib import Path
import re

from . import checkpoints as ckpt
from .storage.atomic import sha256_file

PARTS = (('actor', 'Actor', 'The policy: reads the circuit and the goals, proposes a size for every parameter group.'),
         ('critic', 'Critic', 'Judges a proposed action (its Q-value). Two identical critics are trained, and each has a '
                              'slowly following target copy: 4 networks of this structure are saved.'))

# (pattern on the layer path, section, what it does). First match wins.
ROLES = (
    (r'^encoder\.device_values$', 'Inputs', 'Device numbers (w, l, m, ... with their present / optimizable flags) into the hidden width.'),
    (r'^encoder\.device_kind$', 'Inputs', 'Look-up table: one learned vector per device kind (nmos, pmos, resistor, ...).'),
    (r'^encoder\.net_values$', 'Inputs', 'Net role (ground, supply, input, output, ...) into the hidden width.'),
    (r'^encoder\.context\.\d+$', 'Inputs', 'The goals: targets, measured values, budget and status, as one vector added to every node.'),
    (r'^encoder\.port_role$', 'Inputs', 'Look-up table: one learned vector per terminal role and direction (drain, gate, ...) - the edge label.'),
    (r'^encoder\.port_ordinal$', 'Inputs', 'Position of a terminal among equal ones, added to the edge label.'),
    (r'^encoder\.parameter_kind$', 'Inputs', 'Look-up table: one learned vector per parameter kind (w, l, m, ...).'),
    (r'^encoder\.binding_ratio$', 'Inputs', 'Ratio between a group and the device it drives (matched pairs, mirrors).'),
    (r'^encoder\.group_values\.\d+$', 'Inputs', 'Numbers of a parameter group (current value, bounds, ...) into the hidden width.'),
    (r'^encoder\.action_token\.\d+$', 'Inputs', 'Critic only: the proposed action of a group, injected into the devices it drives.'),
    (r'^encoder\.structural_projection$', 'Inputs', 'Topology-only random-walk return probabilities (2, 4, 8, 16 steps) into the hidden width.'),
    (r'^encoder\.operating_points$', 'Inputs', 'Measured nominal operating points with independent missing-value masks.'),
    (r'^encoder\.blocks\.(\d+)\.norm_\w+$', 'Block {n}', 'Normalization before the step that follows.'),
    (r'^encoder\.blocks\.(\d+)\.attention\.lin_skip$', 'Block {n}', "Skip path of PyG's TransformerConv."),
    (r'^encoder\.blocks\.(\d+)\.attention(\..+)?$', 'Block {n}', 'Message passing along the circuit connections: what a node takes from its neighbours.'),
    (r'^encoder\.blocks\.(\d+)\.message(\..+)?$', 'Block {n}', 'Message passing along the circuit connections: what a node takes from its neighbours.'),
    (r'^encoder\.blocks\.(\d+)\.ff\.\d+$', 'Block {n}', 'Per-node feed-forward step after the message passing.'),
    (r'^encoder\.blocks\.(\d+)\.global_attention\..+$', 'Block {n}', 'Global node attention within this circuit; other circuits and padding are masked.'),
    (r'^encoder\.group_readout\.norm_\w+$', 'Read-out', 'Normalize group queries, circuit node keys/values, or the group feed-forward input.'),
    (r'^encoder\.group_readout\.cross_attention\..+$', 'Read-out', 'Each bound parameter-group query attends to all device and net nodes in its own circuit.'),
    (r'^encoder\.group_readout\.ff\.\d+$', 'Read-out', 'Per-group feed-forward step after cross-attention.'),
    (r'^encoder\.group_head\.\d+$', 'Read-out', 'Per parameter group: its devices (mean), the group itself and the goals, combined.'),
    (r'^encoder\.output_norm$', 'Read-out', 'Final normalization of the node vectors.'),
    (r'^head\.\d+$', 'Output', None),      # differs per part, see HEAD_ROLE
)
HEAD_ROLE = dict(actor='Per parameter group: the mean and the spread (log-std) of the proposed action.',
                 critic='One number: the expected return (Q-value) of the proposed action.')
UNUSED_NOTE = ("Allocated by PyG's TransformerConv, but this network switches that path off (root_weight=False): the "
               'forward pass never reads these weights and they never receive a gradient. They are saved and counted, '
               'nothing else.')


def _describe(part, path):
    for pattern, section, role in ROLES:
        match = re.match(pattern, path)
        if match:
            number = int(match.group(1)) + 1 if match.groups() and match.group(1) and match.group(1).isdigit() else None
            return section.format(n=number), role if role is not None else HEAD_ROLE[part]
    return 'Other', None


def schemas(contract):
    """(FeatureSchema, SpecSchema) of a checkpoint's own contract: its JSON lists back as the tuples the schemas hold."""
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    from analog_optimizer.models.inputs import SpecSchema

    def tuples(value):
        return tuple(tuples(v) for v in value) if isinstance(value, (list, tuple)) else value
    return (FeatureSchema(**{k: tuples(v) for k, v in contract['feature_schema'].items()}),
            SpecSchema(**{k: tuples(v) for k, v in contract['spec_schema'].items()}))


def _rebuild(contract):
    """The network described by the checkpoint's own contract: {part: module}. Raises when it cannot be built."""
    from analog_optimizer.models.encoders import ModelConfig
    from analog_optimizer.models.graph_transformer import GraphCritic, GroupActor
    features, spec = schemas(contract)
    config = ModelConfig(**contract['model_config'])
    return dict(actor=GroupActor(features, spec, config), critic=GraphCritic(features, spec, config))


def _shape_text(module, tensors):
    for first, second in (('in_features', 'out_features'), ('in_channels', 'out_channels')):
        if isinstance(getattr(module, first, None), int) and isinstance(getattr(module, second, None), int):
            return f'{getattr(module, first)} -> {getattr(module, second)}'
    if hasattr(module, 'num_embeddings'):
        return f'{module.num_embeddings} entries x {module.embedding_dim}'
    if hasattr(module, 'normalized_shape'):
        return 'over ' + ' x '.join(str(n) for n in module.normalized_shape)
    return ', '.join('x'.join(str(n) for n in t['shape']) for t in tensors)


def _unused_paths(module):
    """Layers that exist but are never read. Decided from the rebuilt module, never from a name alone."""
    from torch_geometric.nn import TransformerConv
    return {f'{path}.lin_skip' for path, m in module.named_modules()
            if isinstance(m, TransformerConv) and not m.root_weight and getattr(m, 'lin_skip', None) is not None}


def _rows(part, state, module):
    """One row per layer that owns tensors. `module` is None when the network could not be rebuilt and verified."""
    owners = {}
    for name, tensor in state.items():
        path, _, leaf = name.rpartition('.')
        owners.setdefault(path, []).append(dict(name=leaf, shape=[int(n) for n in tensor.shape], count=int(tensor.numel())))
    modules = dict(module.named_modules()) if module is not None else {}
    unused = _unused_paths(module) if module is not None else set()
    rows = []
    for path, tensors in owners.items():           # state-dict order = the order the network is built in
        layer = modules.get(path)
        section, role = _describe(part, path)
        rows.append(dict(
            path=path, section=section, role=role, type=type(layer).__name__ if layer is not None else None,
            shape=_shape_text(layer, tensors), tensors=tensors, parameters=sum(t['count'] for t in tensors),
            unused=path in unused, note=UNUSED_NOTE if path in unused else None))
    return rows


def _same_tensors(module, state):
    built = module.state_dict()
    return list(built) == list(state) and all(tuple(built[k].shape) == tuple(state[k].shape) for k in state)


def load_verified(directory):
    """(metadata, tensors) of one checkpoint. `model_weights.pt` is read - tensor-only - only after its SHA-256
    matched the one recorded in metadata.json."""
    directory = Path(directory)
    meta = ckpt.read_metadata(directory)
    recorded = (meta.get('files') or {}).get('model_weights.pt')
    if not recorded or sha256_file(directory / 'model_weights.pt') != recorded['sha256']:
        raise ValueError('model_weights.pt is missing or does not match the checksum recorded in metadata.json')
    return meta, ckpt.load_weights(directory)


def structure(directory) -> dict:
    """The saved model in `directory` (one checkpoint) as layer tables. Verifies the weights file first."""
    meta, weights = load_verified(directory)
    critics = weights['critics']
    first = {k[2:]: v for k, v in critics.items() if k.startswith('0.')}
    second = {k[2:]: v for k, v in critics.items() if k.startswith('1.')}
    states = dict(actor=weights['actor'], critic=first)
    problem, built = None, {}
    try:
        built = _rebuild(meta['contract'])
        if not all(_same_tensors(built[part], states[part]) for part in states):
            problem, built = 'The network rebuilt from the recorded settings does not hold the same tensors as the file.', {}
    except Exception as exc:          # an older contract, another source version: the tensors are still listed
        problem, built = f'The network could not be rebuilt from the recorded settings ({type(exc).__name__}).', {}
    parts = []
    for part, title, about in PARTS:
        rows = _rows(part, states[part], built.get(part))
        total = sum(r['parameters'] for r in rows)
        sections = {}
        for row in rows:
            entry = sections.setdefault(row['section'], dict(section=row['section'], layers=0, parameters=0, unused=0))
            entry['layers'] += 1
            entry['parameters'] += row['parameters']
            entry['unused'] += row['parameters'] if row['unused'] else 0
        for row in rows:
            row['share'] = row['parameters'] / total if total else 0.0
        parts.append(dict(part=part, title=title, about=about, layers=rows, sections=list(sections.values()),
                          parameters=total, unused_parameters=sum(r['parameters'] for r in rows if r['unused'])))
    actor, critic = parts
    identical = ([(k, tuple(v.shape)) for k, v in first.items()] == [(k, tuple(v.shape)) for k, v in second.items()]
                 and [(k, tuple(v.shape)) for k, v in critics.items()] == [(k, tuple(v.shape)) for k, v in weights['targets'].items()])
    trained = actor['parameters'] + 2 * critic['parameters'] + int(weights['log_alpha'].numel())
    return dict(
        checkpoint_id=meta['checkpoint_id'], network=meta['contract']['model_config'], types_verified=not problem,
        types_problem=problem, parts=parts, critics_identical=identical,
        totals=dict(trained=trained, actor=actor['parameters'], critic_each=critic['parameters'], temperature=1,
                    target_copies=2 * critic['parameters'], saved=trained + 2 * critic['parameters'],
                    never_used=actor['unused_parameters'] + 2 * critic['unused_parameters'],
                    never_used_in_targets=2 * critic['unused_parameters']),
        explanation='trained = actor + 2 critics + the entropy temperature (1 number). The 2 target copies are saved '
                    'too; they are not trained by gradients but follow the critics slowly.')
