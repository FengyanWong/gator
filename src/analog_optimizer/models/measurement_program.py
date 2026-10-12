"""Versioned, name-free measurement trees and explicit circuit bindings.

Names resolve addresses here and never become learned features. These are raw CPU
inputs, included in the observation cache, not cached neural representations.
"""
import fnmatch
import math

import torch

PROGRAM_KEY = 'spec_programs'
PROGRAM_VERSION = 'measurement-program-v1'
PROGRAM_UNITS = ('V', 'A', 'W', 'Hz', 's', 'dB', 'deg', 'V/V', 'V/A', '%', '1', 'count', 'ohm', 'F', 'H', 'm',
                 'J', 'rad', 'dBc/Hz', 'V/sqrt(Hz)', 'A/sqrt(Hz)', 'V^2/Hz', 'Vrms', 'V/s', 'Hz/V', 'degC', 'fixture')
OPERATIONS = (
    'unknown', 'number', 'add', 'sub', 'mul', 'div', 'pow', 'neg',
    'dc', 'ac', 'tran', 'noise', 'stb', 'pss', 'pnoise', 'other',
    'voltage', 'current', 'getdata', 'loopgain', 'transfer', 'outputnoise',
    'value', 'cross', 'phasemargin', 'gainmargin', 'ymax', 'ymin', 'peaktopeak',
    'clip', 'integ', 'iinteg', 'average', 'rms', 'frequency', 'dutycycle',
    'risetime', 'falltime', 'slewrate', 'delay', 'period', 'settlingtime', 'overshoot',
    'bandwidth', 'unitygainfreq', 'mag', 'abs', 'db20', 'db10', 'sqrt', 'phase',
    'real', 'imag', 'log', 'log10', 'exp', 'deriv', 'rising', 'falling', 'either',
    'result', 'from', 'to', 'initial', 'final', 'theta1', 'theta2', 'edge',
    'threshold', 'time', 'frequency_arg', 'nil', 'true', 'width', 'count', 'fingers',
    'larger', 'smaller', 'analyzer', 'excitation', 'reference',
    'probe', 'xf', 'mode', 'user', 'auto', 'percent', 'nth', 'direction',
    'vf', 'vs', 'vdc', 'vt', 'vn', 'vm', 'vp', 'vr', 'vi', 'v',
    'if', 'is', 'idc', 'it', 'in', 'im', 'ip', 'ir', 'ii', 'i',
) + tuple('unit:' + unit for unit in PROGRAM_UNITS)
BINDING_ROLES = ('voltage', 'reference', 'excitation', 'current', 'drain', 'gate', 'source', 'bulk',
                 'positive', 'negative', 'size')
BLOCK_KINDS = ('shared_source_pair', 'diode_mirror', 'parameter_tie', 'gain_stage', 'bias', 'compensation')
MAX_PROGRAM_NODES = 4096
MAX_PROGRAM_DEPTH = 64


def _blocks(graph, device_index):
    """Conservative electrical motifs; no stage/function guessed from names.

    Higher-level functions may be supplied explicitly in functional_blocks.
    Shared-source motifs are not claimed to be verified differential amplifiers.
    """
    terminals = {d.id: {} for d in graph.devices}
    for c in graph.connections:
        terminals[c.device_id][c.role] = c.net_id
    by_source = {}
    for d in graph.devices:
        pins = terminals[d.id]
        if d.kind in ('nmos', 'pmos') and all(p in pins for p in ('drain', 'gate', 'source', 'bulk')):
            by_source.setdefault((d.kind, pins['source'], pins['bulk']), []).append(d.id)
    blocks = set()
    rails = {n.id for n in graph.nets if set(n.roles).intersection(('ground', 'supply'))}
    for (_, source, _), devices in by_source.items():
        if len(devices) == 2 and source not in rails:
            a, b = devices
            pa, pb = terminals[a], terminals[b]
            if pa['gate'] != pb['gate'] and pa['drain'] != pb['drain']:
                blocks.add((BLOCK_KINDS.index('shared_source_pair'), tuple(sorted((device_index[a], device_index[b])))))
        gates = {}
        for device in devices:
            gates.setdefault(terminals[device]['gate'], []).append(device)
        for gate, members in gates.items():
            if len(members) > 1 and any(terminals[d]['drain'] == gate for d in members):
                blocks.add((BLOCK_KINDS.index('diode_mirror'), tuple(sorted(device_index[d] for d in members))))
    for group in graph.parameter_groups:
        members = tuple(sorted({device_index[m.device_id] for m in group.members}))
        if len(members) > 1:
            blocks.add((BLOCK_KINDS.index('parameter_tie'), members))
    for block in graph.metadata.get('functional_blocks', ()):
        if block.get('kind') not in BLOCK_KINDS or not block.get('members'):
            raise ValueError('A functional block needs a supported kind and explicit device members')
        try:
            members = tuple(sorted({device_index[m] for m in block['members']}))
        except KeyError as exc:
            raise ValueError('Unknown device in functional block') from exc
        blocks.add((BLOCK_KINDS.index(block['kind']), members))
    return sorted(blocks)


def prepare_programs(observation, *, operating_points=False):
    graph = observation.graph
    programs = graph.metadata.get(PROGRAM_KEY)
    if not isinstance(programs, dict):
        raise ValueError(f'Structured specs require {PROGRAM_KEY} metadata, including explicit unknown programs')
    devices = {d.id: i for i, d in enumerate(graph.devices)}
    nets = {n.id: len(devices) + i for i, n in enumerate(graph.nets)}
    ops, values, heights, owners, roots, children, slots, bindings, roles = [], [], [], [], [], [], [], [], []

    def visit(node, owner, depth=0):
        if depth > MAX_PROGRAM_DEPTH or len(ops) >= MAX_PROGRAM_NODES:
            raise ValueError('Measurement program exceeds the node/depth limit')
        if not isinstance(node, dict) or node.get('op') not in OPERATIONS:
            raise ValueError('Measurement program needs a known operation or an explicit unknown token')
        index = len(ops)
        ops.append(OPERATIONS.index(node['op']))
        owners.append(owner)
        values.append(None)
        heights.append(0)
        number = node.get('value')
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number)):
            raise ValueError('A measurement program constant must be finite')
        requested = node.get('bindings', [])
        resolved = 0
        for binding in requested:
            role = binding.get('role', 'voltage')
            if role not in BINDING_ROLES or binding.get('kind') not in ('device', 'net'):
                raise ValueError('Invalid measurement binding kind or role')
            table = devices if binding['kind'] == 'device' else nets
            addresses = [table[binding['id']]] if binding.get('id') in table else []
            if binding.get('selector') is not None:
                if binding['kind'] != 'net' or binding['selector'] != 'ground':
                    raise ValueError('Only the canonical ground selector is supported for a measurement reference')
                addresses = [nets[n.id] for n in graph.nets if 'ground' in n.roles]
            if binding.get('pattern'):
                # Size formulas read only widths the task varies, like the evaluator.
                sized = {m.device_id for g in graph.parameter_groups if g.parameter_kind == 'w' and g.mutable for m in g.members}
                addresses = [idx for name, idx in table.items() if name in sized and
                             (fnmatch.fnmatchcase(name, binding['id']) or fnmatch.fnmatchcase(name.rsplit('/', 1)[-1], binding['id']))]
            for address in addresses:
                bindings.append((index, address))
                roles.append(BINDING_ROLES.index(role))
            resolved += bool(addresses)
        # Two complementary numeric channels retain SI-scale thresholds/constants.
        magnitude = abs(number) if number is not None else 0.
        values[index] = [math.copysign(math.log1p(magnitude), number or 0.),
                         math.log10(magnitude) if magnitude else 0., float(number is not None),
                         float(node['op'] != 'unknown'), math.log1p(len(requested)),
                         resolved / len(requested) if requested else 0.]
        for slot, child in enumerate(node.get('children', ())):
            ci = visit(child, owner, depth + 1)
            children.append((ci, index))
            slots.append(0 if node['op'] == 'excitation' else slot)  # A set of sources has no naming order.
            heights[index] = max(heights[index], heights[ci] + 1)
        return index

    for spec in observation.specs:
        if spec.active:
            if spec.metric_id not in programs:
                raise ValueError(f'Missing measurement program for {spec.metric_id}')
            roots.append(visit(programs[spec.metric_id], len(roots)))
    blocks = _blocks(graph, devices)
    members = [(i, member) for i, (_, ids) in enumerate(blocks) for member in ids]
    coordinates = []
    for group in graph.parameter_groups:
        transform = math.log if group.scale == 'log' else float
        lo, hi, value = map(transform, (group.lower, group.upper, group.value))
        coordinates.append([(value - lo) / (hi - lo),
                            (group.step or 0.) / (group.upper - group.lower), math.log1p(len(group.members))])
    physics = []
    for device in graph.devices:
        op = (observation.operating_points or {}).get(device.id, {}) if operating_points else {}
        op = op if isinstance(op, dict) else {}
        read = lambda key: op.get(key) if not isinstance(op.get(key), bool) and isinstance(op.get(key), (int, float)) and math.isfinite(op[key]) else None
        gm, ids, gds, vgs, vth, vds, vdsat = (read(k) for k in ('gm', 'ids', 'gds', 'vgs', 'vth', 'vds', 'vdsat'))
        quantities = [abs(gm / ids) if gm is not None and ids else None,
                      abs(gm / gds) if gm is not None and gds else None,
                      abs(vgs) - abs(vth) if vgs is not None and vth is not None else None,
                      abs(vds) - abs(vdsat) if vds is not None and vdsat is not None else None,
                      abs(vds / vdsat) if vds is not None and vdsat else None]
        valid = [v is not None and math.isfinite(v) for v in quantities]
        from .inputs import signed_log
        physics.append([signed_log(v, ref) if mask else 0. for v, ref, mask in
                        zip(quantities, (10., 10., .1, .1, 1.), valid)] + [float(v) for v in valid])
    index_tensor = lambda pairs: torch.tensor(pairs, dtype=torch.long).reshape(-1, 2).T.contiguous()
    return dict(op=torch.tensor(ops, dtype=torch.long), values=torch.tensor(values, dtype=torch.float32).reshape(-1, 6),
                height=torch.tensor(heights, dtype=torch.long), owner=torch.tensor(owners, dtype=torch.long),
                roots=torch.tensor(roots, dtype=torch.long), children=index_tensor(children),
                slot=torch.tensor(slots, dtype=torch.float32), bindings=index_tensor(bindings),
                binding_role=torch.tensor(roles, dtype=torch.long),
                block_kind=torch.tensor([k for k, _ in blocks], dtype=torch.long), block_members=index_tensor(members),
                coordinates=torch.tensor(coordinates, dtype=torch.float32).reshape(-1, 3),
                physics=torch.tensor(physics, dtype=torch.float32).reshape(-1, 10))


def batch_programs(prepared):
    total_devices = sum(p.graph['device'].num_nodes for p in prepared)
    out = {}
    device_offset = net_offset = token_offset = spec_offset = block_offset = 0
    for circuit, p in enumerate(prepared):
        data = {k: v.clone() for k, v in p.structured.items()}
        ndevice = p.graph['device'].num_nodes
        data['owner'] += spec_offset
        data['roots'] += token_offset
        data['children'] += token_offset
        data['bindings'][0] += token_offset
        idx = data['bindings'][1]
        data['bindings'][1] = torch.where(idx < ndevice, idx + device_offset,
                                          idx - ndevice + total_devices + net_offset)
        data['block_members'][0] += block_offset
        data['block_members'][1] += device_offset
        data['block_batch'] = torch.full((len(data['block_kind']),), circuit, dtype=torch.long)
        for key, value in data.items():
            out.setdefault(key, []).append(value)
        device_offset += ndevice
        net_offset += p.graph['net'].num_nodes
        token_offset += len(data['op'])
        spec_offset += len(p.spec_items)
        block_offset += len(data['block_kind'])
    return {k: torch.cat(v, dim=1 if k in ('children', 'bindings', 'block_members') else 0) for k, v in out.items()}
