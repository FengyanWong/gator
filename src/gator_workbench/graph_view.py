"""What a SAVED policy does on the circuit of its own run: the data behind the circuit graph view.

Nothing is simulated and nothing is written. The state is one the run ARCHIVED (the exact observation the network
saw before an evaluation, rebuilt by ``TrajectoryLoader``), the policy is the chosen save point (tensor-only read of
``model_weights.pt`` after its checksum matched, network rebuilt from the recorded contract and required to hold
exactly the saved tensors), and one forward pass of the actor is run on the CPU. That works for MOCK and for real
runs alike and costs no evaluation.

Attention is read WITHOUT touching ``src/analog_optimizer``: a forward hook on each attention convolution
(``TransformerConv`` / ``GATv2Conv``) repeats that layer's own computation on its own inputs with
``return_attention_weights=True``. The layers are deterministic (dropout 0), so these are the weights the pass used;
a test compares the policy's output with and without the hooks.

How to read attention (returned to the page as ``reading``): it is normalized PER RECEIVING NODE - over all
connections arriving at one node the values of a head sum to 1. A node with a single connection therefore always
shows 1.0, which says nothing. The uniform share 1/k is given next to every value. Attention shows where the network
looked, not why it chose an action; it is a debugging aid, not evidence.
"""
from __future__ import annotations

from pathlib import Path

from . import checkpoints as ckpt, model_structure, network_inputs
from .pdk import run_vocabulary
from .run_definitions import decode_action
from .schema import WorkbenchConfig
from .storage.atomic import read_json
from .storage.dataset import map_to_dict
from .trajectory import TrajectoryLoader

READING = ('Attention is normalized per RECEIVING node: over all connections arriving at one node, the values of a '
           'head sum to 1. A node with a single connection always shows 1.0 - that says nothing. Compare a value with '
           'the uniform share 1/k given next to it. Attention shows where the network looked, not why it chose an '
           'action: a debugging aid, not evidence.')


class GraphViewUnavailable(ValueError):
    """The view cannot be built for this model, said in plain words (HTTP 409)."""


def _actor(meta, weights):
    try:
        actor = model_structure.rebuild_network(meta['contract'])['actor']
    except Exception as exc:
        raise GraphViewUnavailable('The network of this save point could not be rebuilt from its recorded settings '
                                   f'({type(exc).__name__}), so it cannot be run here.') from exc
    if not model_structure.same_tensors(actor, weights['actor']):
        raise GraphViewUnavailable('The network rebuilt from the recorded settings does not hold the same tensors as '
                                   'the saved file, so it is not run here.')
    actor.load_state_dict(weights['actor'])
    return actor.eval()


def _one_row(reader, table, column, value, columns=None, flushes=None):
    """The ONE row of an archive table with `column == value`, read with a parquet filter: the other rows are never
    turned into Python objects (a long run holds thousands of states with their JSON patches). `flushes`: the flush
    records whose parts are searched, in that order; all of them, oldest first, when not given."""
    import pyarrow.parquet as pq
    for flush in reader.flushes if flushes is None else flushes:
        if table in flush['parts']:
            found = pq.read_table(reader.root / table / flush['parts'][table], columns=columns, filters=[(column, '=', value)])
            if found.num_rows:
                return found.to_pylist()[0]
    return None


def _step(loader, wanted, saved_at):
    """The archived transition to show: the asked evaluation, else the last one the save point had seen.
    Only the column of evaluation numbers is read in full; the chosen transition and its state are single-row reads,
    so the cost of a request does not grow with everything a long run archived."""
    numbers = sorted(loader.reader.table('transitions', ['commit_seq'])['commit_seq'].to_pylist())
    if not numbers:
        raise GraphViewUnavailable('This run kept no archive of the states the network saw ("Transition archive" was '
                                   'off in its output settings, or it recorded no evaluation yet), so there is nothing '
                                   'to replay the model on.')
    first, last = numbers[0], numbers[-1]
    if wanted is None:
        chosen = ([n for n in numbers if saved_at is None or n <= saved_at] or numbers)[-1]
    elif wanted in numbers:
        chosen = wanted
    else:
        raise GraphViewUnavailable(f'This run has no archived evaluation {wanted}: it holds {first} to {last}.')
    # A transition is committed with its evaluation number, so it sits in the part of the flush whose range holds that
    # number; its state was written in that flush or an earlier one (once, with the first transition that saw it). One read
    # for the transition and the states newest first from there, instead of every part of a long run oldest first (the
    # default view of a 400-evaluation run: 96 parquet reads, ~1.2 s on the 9p mount). Anything not found there is looked
    # for in the other parts, as before.
    flushes = loader.reader.flushes
    at = next((i for i, f in enumerate(flushes) if f['first_seq'] <= chosen <= f['last_seq']), len(flushes) - 1)
    columns = ['commit_seq', 'state_ref', 'action', 'policy_version']
    row = (_one_row(loader.reader, 'transitions', 'commit_seq', chosen, columns, flushes[at:at + 1])
           or _one_row(loader.reader, 'transitions', 'commit_seq', chosen, columns))
    state = (_one_row(loader.reader, 'states', 'state_id', row['state_ref'], flushes=flushes[at::-1])
             or _one_row(loader.reader, 'states', 'state_id', row['state_ref'], flushes=flushes[at + 1:]))
    if state is None:
        raise GraphViewUnavailable(f'The archive of this run holds no state for evaluation {chosen}.')
    loader._states = {state['state_id']: state}           # what TrajectoryLoader.observation() looks the state up in
    return row, dict(first=first, last=last, count=len(numbers))


def capture_attention(actor, run):
    """Run `run()` and return (its result, [per attention layer: (edge_index [2,E], alpha [E,H])])."""
    import torch
    from torch_geometric.nn import GATv2Conv, TransformerConv
    captured, handles = [], []

    def hook(module, inputs, output):
        with torch.no_grad():
            _, (edge_index, alpha) = module.forward(*inputs, return_attention_weights=True)
        captured.append((edge_index, alpha))
    for module in actor.modules():
        if isinstance(module, (TransformerConv, GATv2Conv)):
            handles.append(module.register_forward_hook(hook))
    try:
        with torch.no_grad():
            result = run()
    finally:
        for handle in handles:
            handle.remove()
    return result, captured


def capture_dense_attention(actor, run):
    """Inspect global/group weights only on demand; leave the policy's output untouched."""
    import torch
    captured, handles = [], []

    def hook(module, inputs, kwargs, output):
        with torch.no_grad():
            _, weights = module.forward(*inputs, **dict(kwargs, need_weights=True, average_attn_weights=False))
        captured.append(dict(kind=module.attention_kind, weights=weights.detach().cpu()))

    for module in actor.modules():
        if isinstance(module, torch.nn.MultiheadAttention) and hasattr(module, 'attention_kind'):
            handles.append(module.register_forward_hook(hook, with_kwargs=True))
    try:
        with torch.no_grad():
            result = run()
    finally:
        for handle in handles:
            handle.remove()
    return result, captured


STANDARD_FAMILY = dict(nmos='nmos', pmos='pmos', resistor='resistor', capacitor='capacitor', inductor='inductor',
                       vsource='vsource', isource='isource')


def _family(device, vocabulary):
    """The standard kind a device is drawn as: its own kind, or - for a PDK kind - the PDK's family of it (an n-type PDK
    transistor is drawn like an nmos). The page shows the PDK kind as the name; only shape and colour follow this."""
    if device.kind in STANDARD_FAMILY or vocabulary is None:
        return STANDARD_FAMILY.get(device.kind, 'unknown')
    entry = vocabulary.devices.get(device.model_ref) or {}
    family = entry.get('family')
    if family == 'mos':
        return {'n': 'nmos', 'p': 'pmos'}.get(entry.get('polarity'), 'mos')
    return family or 'unknown'


def _network_of(run_dir):
    """The network block of a run's own configuration (effective_config.json), or {}."""
    config = read_json(Path(run_dir) / 'effective_config.json', default={}) or {}
    return ((config.get('run') or {}).get('network') or {}) if isinstance(config, dict) else {}


def _network_view(run_dir, vocabulary):
    """The NetworkView the run's model was trained with, or None (no transferable inputs)."""
    recorded = network_inputs.read_run_record(run_dir)
    if recorded is None:
        return None
    try:
        config = WorkbenchConfig.model_validate(read_json(Path(run_dir) / 'effective_config.json'))
        view = network_inputs.view_for(config, vocabulary)
    except Exception as exc:
        raise GraphViewUnavailable('What this run showed its network (its spec descriptions or its PDK\'s device '
                                   f'numbers) cannot be rebuilt here ({type(exc).__name__}).') from exc
    if view is None or view.key != recorded.get('view_key'):
        raise GraphViewUnavailable('What this run showed its network has changed since it ran (its task\'s spec '
                                   "descriptions or its PDK's device numbers), so the circuit cannot be shown to it the same way.")
    return view


def graph_view(run_dir, checkpoint_id='latest', *, evaluation=None) -> dict:
    from analog_optimizer.models.inputs import batch_observations
    run_dir = Path(run_dir)
    directory = ckpt.resolve_checkpoint(run_dir, checkpoint_id)
    meta, weights = model_structure.load_verified(directory)
    actor = _actor(meta, weights)
    features, spec = model_structure.schemas(meta['contract'])
    loader = TrajectoryLoader(run_dir)
    row, steps = _step(loader, evaluation, (meta.get('counters') or {}).get('evaluations_committed'))
    observation = loader.observation(row['state_ref'])
    # A run built with a PDK's component list saw every circuit through that PDK's view: replay it the same way, and
    # draw what the network saw (the PDK kinds and pin roles). The run's own copy of the list is used, never a newer load.
    vocabulary = run_vocabulary(run_dir)
    if vocabulary is not None:
        if network_inputs.feature_schema(vocabulary.schema, _network_of(run_dir)) != features:
            raise GraphViewUnavailable('The component list kept in this run folder is not the one this save point was '
                                       'trained with, so the circuit cannot be shown to it the same way.')
    # The transferable inputs (record 7.298) are shown to the network only: the page draws the circuit as recorded (its
    # sizes as simulated, never a PDK's device numbers), with the PDK kinds and pin roles of the list when there is one.
    seen = _network_view(run_dir, vocabulary)
    shown = vocabulary.view(observation) if vocabulary is not None else observation
    batch = batch_observations([seen.view(observation) if seen is not None else shown], features, spec)
    observation = shown
    (sample, layers), dense_layers = capture_dense_attention(actor,
        lambda: capture_attention(actor, lambda: actor.sample(batch, deterministic=True)))
    policy = batch.proposals(sample.actions)[0]
    recorded = map_to_dict(row['action']) if row.get('action') is not None else {}

    graph = observation.graph
    device_ids, net_ids = [d.id for d in graph.devices], [n.id for n in graph.nets]
    count = len(device_ids)
    roles = features.terminal_roles
    # One entry per physical connection; both directions of the network's edge list are folded into it.
    connections = {}
    for c in graph.connections:
        connections[(c.device_id, c.net_id, c.role, c.ordinal)] = dict(
            id=f'{c.device_id}.{c.terminal}#{c.ordinal}->{c.net_id}', device=c.device_id, net=c.net_id, terminal=c.terminal,
            role=c.role, ordinal=c.ordinal, attention=[])
    edge_index, edge_role, edge_ordinal = batch.edge_index.tolist(), batch.edge_role.tolist(), batch.edge_ordinal.tolist()
    incoming = [0] * (count + len(net_ids))
    for receiver in edge_index[1]:
        incoming[receiver] += 1
    keys = []
    for position, (source, receiver) in enumerate(zip(*edge_index)):
        to_net = edge_role[position] % 2 == 0                       # direction 0 = device -> net
        device, net = (source, receiver - count) if to_net else (receiver, source - count)
        keys.append(((device_ids[device], net_ids[net], roles[edge_role[position] // 2], int(edge_ordinal[position])),
                     'to_net' if to_net else 'to_device', incoming[receiver]))
    for number, (index, alpha) in enumerate(layers):
        if index.tolist() != edge_index:
            raise GraphViewUnavailable('An attention layer reported other connections than the network was given.')
        for entry in connections.values():
            entry['attention'].append(dict(layer=number + 1))
        for (key, direction, competitors), heads in zip(keys, alpha.tolist()):
            slot = connections[key]['attention'][number]
            slot[direction] = sum(heads) / len(heads)
            slot[f'{direction}_heads'] = heads
            slot[f'{direction}_uniform'] = 1 / competitors
    member_of = {}
    for group in graph.parameter_groups:
        for member in group.members:
            member_of.setdefault(member.device_id, []).append(group.id)
    groups = []
    for group in graph.parameter_groups:
        z, done = policy.get(group.id), recorded.get(group.id)
        groups.append(dict(
            id=group.id, parameter=group.parameter_kind, unit=group.unit, value=group.value, lower=group.lower,
            upper=group.upper, scale=group.scale, mutable=group.mutable,
            members=[dict(device=m.device_id, parameter=m.parameter, ratio=m.ratio) for m in group.members],
            policy_action=z, policy_value=None if z is None else decode_action(z, group.lower, group.upper, group.scale),
            recorded_action=done,
            recorded_value=None if done is None else decode_action(done, group.lower, group.upper, group.scale)))
    config = meta['contract']['model_config']
    has_attention = bool(layers)
    return dict(
        checkpoint_id=meta['checkpoint_id'], run_dir=str(run_dir), task_id=meta.get('task_id'), network=config,
        circuit_id=graph.circuit_id, origin=observation.origin,
        step=dict(evaluation=row['commit_seq'], policy_version_then=row.get('policy_version'),
                  saved_at=(meta.get('counters') or {}).get('evaluations_committed'), status=observation.status, **steps),
        metrics=[dict(id=k, value=v, unit=observation.metric_units.get(k, ''), valid=bool(observation.metric_validity.get(k)))
                 for k, v in sorted(observation.metrics.items())],
        vocabulary=dict(name=vocabulary.name, label=vocabulary.label) if vocabulary is not None else dict(name='standard', label='standard (8 generic kinds)'),
        devices=[dict(id=d.id, kind=d.kind, model=d.model_ref, groups=member_of.get(d.id, []), family=_family(d, vocabulary),
                      parameters={name: p.value for name, p in (graph.parameters.get(d.id) or {}).items() if p.value is not None})
                 for d in graph.devices],
        nets=[dict(id=n.id, roles=list(n.roles)) for n in graph.nets],
        connections=list(connections.values()), groups=groups,
        node_attention=dict(
            nodes=[f'd:{name}' for name in device_ids] + [f'n:{name}' for name in net_ids],
            groups=[g.id for g in graph.parameter_groups],
            global_layers=[item['weights'][0].tolist() for item in dense_layers if item['kind'] == 'global'],
            group_layers=[item['weights'][0].tolist() for item in dense_layers if item['kind'] == 'group'],
            reading='Normalized over all nodes in this circuit for each query and head. These are attention weights, '
                    'not physical connections or a causal explanation of the action.'),
        attention=dict(available=has_attention, layers=len(layers), heads=len(layers[0][1][0]) if has_attention else 0,
                       reason=None if has_attention else
                       f"The {config['encoder_type']} encoder has no attention: the picture shows the circuit and "
                       'the proposed sizes only.'),
        reading=READING,
        actions_note='policy = what THIS save point proposes for this state (its mean action, no exploration noise), '
                     'before the value is snapped to the grid. recorded = what the run really tried at this evaluation '
                     '(a random warm-up action, or the policy of that moment with exploration noise).')
