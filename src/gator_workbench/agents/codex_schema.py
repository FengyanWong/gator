"""Codex's strict wire schema, decoded to the shared proposal contract before validation.

Strict output requires closed objects and every property to be required (optional
ones are nullable): https://developers.openai.com/api/docs/guides/structured-outputs
Rows and Maestro dictionaries have arbitrary keys in the shared contract. Only
these objects travel as JSON text; their normal backend validators still decide
which fields, values and operations are allowed. Claude and manual imports keep
their existing schema. No permissions or approval checks change here.
"""
from __future__ import annotations

import json

from .base import AgentError
from .prompts import PROPOSAL_SCHEMA


def _strict(schema):
    if schema.get('type') == 'object':
        if schema.get('additionalProperties') is not False:
            return dict(type='string', description='A JSON object encoded as text, not prose. '
                        'Use the row fields or Maestro dictionary structure described in the prompt.')
        required = set(schema.get('required', []))
        properties = {key: _strict(value) for key, value in schema.get('properties', {}).items()}
        return dict(schema, properties={key: value if key in required else dict(anyOf=[value, dict(type='null')])
                                        for key, value in properties.items()}, required=list(properties))
    if schema.get('type') == 'array':
        return dict(schema, items=_strict(schema['items']))
    if 'enum' in schema and 'type' not in schema:
        return dict(schema, type='string')
    return dict(schema)


CODEX_PROPOSAL_SCHEMA = _strict(PROPOSAL_SCHEMA)
OUTPUT_INSTRUCTIONS = '''CODEX OUTPUT FORMAT
Follow the supplied output schema. Optional fields are required but may be null.
For patch add/replace operations, value is the COMPLETE row encoded as JSON text;
for remove it is null. For setup, analyses, variables and initial_conditions are
JSON objects encoded as text, or null when omitted. For example, analyses holds
the JSON text {"tran":{"stop":"40n"}}; variables holds {"vdd":"1.0"}.
Other fields, including setup.bindings, keep their normal structured shape.
The workbench decodes these strings, then runs the same row, scope and approval
checks as for any other provider. JSON text cannot grant additional permissions.
'''


def decode_proposal(value, schema=PROPOSAL_SCHEMA, path='$'):
    """Decode only schema-designated objects. Unknown fields remain for validation
    to reject; text such as reasoning/basis is never interpreted as JSON. Legacy
    object payloads from older CLI fixtures remain valid shared-contract inputs."""
    if schema.get('type') == 'object':
        if schema.get('additionalProperties') is not False:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (ValueError, RecursionError) as exc:
                    raise AgentError('schema_failure', f'{path} must contain a JSON object') from exc
            if not isinstance(value, dict):
                raise AgentError('schema_failure', f'{path} must contain a JSON object')
            return value
        if isinstance(value, dict):
            properties, required = schema.get('properties', {}), schema.get('required', [])
            return {key: decode_proposal(item, properties[key], f'{path}.{key}') if key in properties else item
                    for key, item in value.items() if not (key in properties and key not in required and item is None)}
    if schema.get('type') == 'array' and isinstance(value, list):
        return [decode_proposal(item, schema['items'], f'{path}[{index}]') for index, item in enumerate(value)]
    return value
