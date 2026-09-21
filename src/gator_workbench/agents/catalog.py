"""Models and effort levels each provider's CLI accepts: what the Agent tab offers in its drop-downs.

Showing this costs nothing - it is a static table plus one local settings read; no CLI is started and no
model is called. Neither CLI can list its models, and the vendors' model endpoints need an API key this
application never holds, so the table is maintained by hand from the vendors' documentation (``verified``
says when, ``source`` where). It is a convenience, not a gate: any other single-line model name is still
accepted ("Custom..." in the UI), because model line-ups change faster than this file.

This module imports nothing from the package, so ``base`` can use it for validation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CLAUDE_EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
CODEX_EFFORTS = ('minimal', 'low', 'medium', 'high', 'xhigh')

# Alias -> the model it resolved to on the Anthropic API when this table was verified. Used ONLY to find the
# per-model effort in the user's Claude Code settings; the alias itself is what is passed to the CLI.
CLAUDE_ALIASES = {'fable': 'claude-fable-5-1', 'opus': 'claude-opus-5', 'sonnet': 'claude-sonnet-5',
                  'haiku': 'claude-haiku-4-5-20251001'}


def _claude(model_id, label, note, efforts=CLAUDE_EFFORTS):
    return dict(id=model_id, label=label, note=note, efforts=list(efforts))


_PRICE = 'API list price per million tokens in / out: '        # a subscription is not billed per request,
_NO_EFFORT = ' Effort is not supported by this model and is ignored.'  # but usage is weighed in the same proportion

CATALOG = {
    'claude_code': dict(
        verified='2026-09-20', source='https://code.claude.com/docs/en/model-config',
        efforts=list(CLAUDE_EFFORTS),
        default_note='Nothing is passed: the CLI uses your Claude Code settings, else the account default (Opus 5 on '
                     'Max, Sonnet 5 on Pro) at effort high.',
        models=[
            _claude('fable', 'fable - latest Fable (Fable 5.1)', 'Most capable, heaviest on usage. ' + _PRICE + '$10 / $50.'),
            _claude('opus', 'opus - latest Opus (Opus 5)', 'Complex reasoning. ' + _PRICE + '$5 / $25.'),
            _claude('sonnet', 'sonnet - latest Sonnet (Sonnet 5)', 'Everyday work; usually enough to fill in a '
                    'configuration. ' + _PRICE + '$2 / $10.'),
            _claude('haiku', 'haiku - latest Haiku (Haiku 4.5)', 'Fastest and lightest. ' + _PRICE + '$1 / $5.' + _NO_EFFORT, ()),
            _claude('claude-fable-5-1', 'claude-fable-5-1 (pinned version)', _PRICE + '$10 / $50.'),
            _claude('claude-opus-5', 'claude-opus-5 (pinned version)', _PRICE + '$5 / $25.'),
            _claude('claude-sonnet-5', 'claude-sonnet-5 (pinned version)', _PRICE + '$2 / $10.'),
            _claude('claude-haiku-4-5-20251001', 'claude-haiku-4-5-20251001 (pinned version)', _PRICE + '$1 / $5.' + _NO_EFFORT, ()),
        ]),
    'codex': dict(
        verified='2026-09-20', source='https://learn.chatgpt.com/docs/models',
        efforts=list(CODEX_EFFORTS),
        default_note='Nothing is passed: the CLI uses your Codex configuration.',
        # Effort reaches codex as `--config model_reasoning_effort="<level>"`, and only if its --help lists --config.
        caveat='From the documentation only: Codex has never been installed here, so this list is untested. '
               'xhigh depends on the model.',
        models=[dict(id=model_id, label=label, note=note, efforts=list(CODEX_EFFORTS)) for model_id, label, note in (
            ('gpt-6-astra', 'gpt-6-astra - Astra', 'Recommended.'),
            ('gpt-5.6-sol', 'gpt-5.6-sol - 5.6 Sol', 'Recommended.'),
            ('gpt-5.6-terra', 'gpt-5.6-terra - 5.6 Terra', 'Recommended.'),
            ('gpt-5.6-luna', 'gpt-5.6-luna - 5.6 Luna', 'Recommended.'),
            ('gpt-5.5', 'gpt-5.5 (legacy)', 'Legacy: retires from Codex on 2026-10-14.'),
            ('gpt-5.4', 'gpt-5.4 (legacy)', 'Legacy.'),
            ('gpt-5.4-mini', 'gpt-5.4-mini (legacy)', 'Legacy.'))]),
    'disabled': dict(verified=None, source=None, efforts=[], default_note='No agent is called.', models=[]),
}
ALL_EFFORTS = tuple(dict.fromkeys(CLAUDE_EFFORTS + CODEX_EFFORTS))


def efforts_for(provider) -> tuple:
    """Effort levels a provider's CLI accepts. A provider without its own list (``disabled``, unknown) keeps any
    level some provider accepts, so switching provider never invalidates a saved file by itself."""
    return tuple(CATALOG.get(provider, {}).get('efforts') or ALL_EFFORTS)


def model_entry(provider, model):
    return next((m for m in CATALOG.get(provider, {}).get('models', ()) if m['id'] == model), None)


def supports_effort(provider, model) -> bool:
    """False only for a LISTED model known to take no effort. The CLI default and custom names are unknown here,
    so the level is passed on and the CLI decides."""
    entry = model_entry(provider, model)
    return entry is None or bool(entry['efforts'])


def claude_cli_default() -> dict:
    """What `claude` will use when the application passes neither --model nor --effort, as far as local files can
    tell. Reads ONLY the model/effort keys of the user's Claude Code settings - never `env`, tokens or anything
    else in that file - and the two overriding environment variables of THIS process (the one that starts the CLI)."""
    directory = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude')
    try:
        saved = json.loads((directory / 'settings.json').read_text(encoding='utf8'))
        saved = saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        saved = {}
    text = lambda value: value if isinstance(value, str) and value.strip() else None       # noqa: E731
    model = text(os.environ.get('ANTHROPIC_MODEL')) or text(saved.get('model'))
    per_model = saved.get('modelSettings') if isinstance(saved.get('modelSettings'), dict) else {}

    def effort_of(name):
        chosen = per_model.get(CLAUDE_ALIASES.get(name, name)) or per_model.get(name) or {}
        return (text(os.environ.get('CLAUDE_CODE_EFFORT_LEVEL'))
                or text(chosen.get('effortLevel') if isinstance(chosen, dict) else None) or text(saved.get('effortLevel')))

    # The effort the settings give EACH listed model: with a per-model level, "CLI default" differs by model.
    by_model = {m['id']: effort_of(m['id']) if m['efforts'] else None for m in CATALOG['claude_code']['models']}
    effort = effort_of(model)
    return dict(model=model, effort=effort, efforts_by_model=by_model,
                note='Read from your Claude Code settings; a per-model effort there overrides the general one. '
                     'Not confirmed by a request: only a real reply shows what was used.' if model or effort else
                     'Your Claude Code settings name no model or effort, so the account default applies.')


def for_api() -> dict:
    listing = {name: dict(entry) for name, entry in CATALOG.items()}
    listing['claude_code']['cli_default'] = claude_cli_default()
    return listing
