"""Lossless, versioned data encoding. No executable pickle in the database."""
from __future__ import annotations

import base64
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import importlib
import json
from pathlib import Path
import zlib

VERSION = 'gator-recording-v1'
MODULES = {
    'analog_optimizer.graph.circuit_graph', 'analog_optimizer.measurements.specs',
    'analog_optimizer.backends.conditions', 'analog_optimizer.envs.sizing',
}


def tree(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        cls = type(value)
        if cls.__module__ not in MODULES:
            # Configuration dataclasses need no executable type on read.
            return tree({f.name: getattr(value, f.name) for f in fields(value)})
        return {'@class': cls.__module__ + ':' + cls.__name__,
                'fields': {f.name: tree(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, dict):
        # Keep field/key order, including tuple parameter keys.
        return {'@dict': [[tree(k), tree(v)] for k, v in value.items()]}
    if isinstance(value, tuple):
        return {'@tuple': [tree(x) for x in value]}
    if isinstance(value, list):
        return [tree(x) for x in value]
    if isinstance(value, Path):
        return {'@path': str(value)}
    if isinstance(value, bytes):
        return {'@bytes': base64.b64encode(value).decode('ascii')}
    if type(value).__module__.startswith('numpy'):
        import numpy as np
        if isinstance(value, np.ndarray):
            if value.dtype.hasobject or value.dtype.fields:
                raise TypeError('Use named fields with plain numeric arrays')
            return {'@array': base64.b64encode(value.tobytes(order='C')).decode('ascii'),
                    'dtype': value.dtype.str, 'shape': list(value.shape), 'order': 'C'}
        return tree(value.item())
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f'Unsupported persistent value: {type(value).__name__}')


def untree(value):
    if isinstance(value, list):
        return [untree(x) for x in value]
    if not isinstance(value, dict):
        return value
    if '@dict' in value:
        return {untree(k): untree(v) for k, v in value['@dict']}
    if '@tuple' in value:
        return tuple(untree(x) for x in value['@tuple'])
    if '@path' in value:
        return Path(value['@path'])
    if '@bytes' in value:
        return base64.b64decode(value['@bytes'])
    if '@array' in value:
        import numpy as np
        dtype = np.dtype(value['dtype'])
        if dtype.hasobject or dtype.fields:
            raise ValueError('Unsafe array dtype')
        return np.frombuffer(base64.b64decode(value['@array']), dtype=dtype).reshape(value['shape']).copy()
    if '@class' in value:
        module, name = value['@class'].split(':')
        if module not in MODULES:
            raise ValueError('Unregistered persistent type')
        cls = getattr(importlib.import_module(module), name)
        if not is_dataclass(cls):
            raise ValueError('Expected a data class')
        return cls(**{k: untree(v) for k, v in value['fields'].items()})
    return {k: untree(v) for k, v in value.items()}


def raw(value):
    return json.dumps(tree(value), ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'), sort_keys=True).encode('utf8')


def pack(value):
    return zlib.compress(raw(value), level=6)


def unpack(value):
    return untree(json.loads(zlib.decompress(value)))


def identity(value):
    # Mapping insertion order is not content; explicit variable/array field-order
    # lists remain ordered. Storage still preserves original mapping order.
    def canonical(node):
        if isinstance(node, list):
            return [canonical(x) for x in node]
        if isinstance(node, dict):
            result = {key: canonical(val) for key, val in node.items()}
            if '@dict' in result:
                result['@dict'].sort(key=lambda pair: json.dumps(pair[0], sort_keys=True, ensure_ascii=False))
            return result
        return node
    encoded = json.dumps(canonical(tree(value)), sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf8')
    return hashlib.sha256(encoded).hexdigest()


def diff(before, after, path=()):
    """Exact small patches of encoded trees, including source metadata changes."""
    if type(before) is type(after) and isinstance(before, (dict, list)):
        keys = list(before) if isinstance(before, dict) else list(range(len(before)))
        other = list(after) if isinstance(after, dict) else list(range(len(after)))
        if keys == other:
            return [p for key in keys for p in diff(before[key], after[key], path + (key,))]
    if before == after:
        return []
    return [(path, after)]


def patched(before, patches):
    from copy import deepcopy
    result = deepcopy(before)
    for path, value in patches:
        if not path:
            result = deepcopy(value)
            continue
        target = result
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = deepcopy(value)
    return result
