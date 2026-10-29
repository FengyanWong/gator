"""Redaction for anything that leaves the backend: logs, diagnostics, agent transcripts, API errors."""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S),
        '[REDACTED PRIVATE KEY]'),
    (re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{8,}'), '[REDACTED API KEY]'),
    (re.compile(r'\bsk-[A-Za-z0-9_\-]{20,}'), '[REDACTED API KEY]'),
    (re.compile(r'\b(gh[pousr]_[A-Za-z0-9]{20,})'), '[REDACTED TOKEN]'),
    (re.compile(r'(?i)\b(authorization\s*:\s*)(bearer|basic)\s+\S+'), r'\1\2 [REDACTED]'),
    (re.compile(r'(?i)\b((?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|token|secret|passwd|password|'
                r'client[_-]?secret|license[_-]?key)\s*["\']?\s*[=:]\s*["\']?)([^\s"\',;&]+)'), r'\1[REDACTED]'),
    (re.compile(r'(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):([^\s@/]+)@'), r'\1:[REDACTED]@'),
]


def redact(text, limit: int | None=None) -> str | None:
    """Return `text` with secrets masked, cut after `limit` characters when given; None stays None."""
    if text is None:
        return None
    text = str(text)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    if limit is not None and len(text) > limit:
        text = text[:limit] + f'... [truncated {len(text) - limit} chars]'
    return text


def skill_string(text) -> str:
    """A Python string as a SKILL string literal - the only escaping between a PDK's own text and the SKILL the workbench
    generates. The backslash is escaped first, then the quote: the other order would let a string close its literal."""
    return '"' + str(text).replace('\\', '\\\\').replace('"', '\\"') + '"'
