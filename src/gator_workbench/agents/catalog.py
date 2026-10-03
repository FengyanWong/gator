"""Models and effort levels each provider's CLI accepts: what the Agent tab offers in its drop-downs.

Showing this costs nothing - no CLI is started and no model is called. Claude Code cannot list its models and the
vendors' model endpoints need an API key this application never holds, so the Claude Code list is a table maintained
by hand from the vendor's documentation (``verified`` says when, ``source`` where). The Codex list comes from the
Codex app itself whenever its file is there: the app keeps the models the signed-in ACCOUNT may use in
``models_cache.json`` in its home folder and refreshes that file by itself; it is read here, never written. Without
it the hand table below is shown. Either list is a convenience, not a gate: any other single-line model name is
still accepted ("Custom..." in the UI), because model line-ups change faster than this file.

This module imports nothing from the package, so ``base`` can use it for validation.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

CLAUDE_EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
CLAUDE_EFFORTS_46 = ('low', 'medium', 'high', 'max')            # Opus 4.6 / Sonnet 4.6: xhigh came with Opus 4.7
CODEX_EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max', 'ultra')

# Alias -> the model it resolved to on the Anthropic API when this table was verified. Used ONLY to find the
# per-model effort in the user's Claude Code settings; the alias itself is what is passed to the CLI.
CLAUDE_ALIASES = {'fable': 'claude-fable-5-1', 'opus': 'claude-opus-5-5', 'sonnet': 'claude-sonnet-5-5',
                  'haiku': 'claude-haiku-4-5-20251001'}


def _claude(model_id, label, note, efforts=CLAUDE_EFFORTS):
    return dict(id=model_id, label=label, note=note, efforts=list(efforts))


_PRICE = 'API list price per million tokens in / out: '        # a subscription is not billed per request,
_NO_EFFORT = ' Effort is not supported by this model and is ignored.'  # but usage is weighed in the same proportion
_NO_XHIGH = ' Effort xhigh is not offered by this model.'

CATALOG = {
    'claude_code': dict(
        verified='2026-10-03', source='https://code.claude.com/docs/en/model-config', origin='hand_table',
        efforts=list(CLAUDE_EFFORTS),
        default_note='Nothing is passed: the CLI uses your Claude Code settings and account default.',
        # Left out on purpose (typed under "Custom..." they are still passed on): `default` is "CLI default" above;
        # `opusplan` runs Opus only in plan mode, which a one-shot `claude -p` request never enters; the `[1m]`
        # spellings change nothing here - the current models already run with 1M context on the Anthropic API.
        models=[
            _claude('fable', 'fable - latest Fable (Fable 5.1)', 'Most capable, heaviest on usage. ' + _PRICE + '$10 / $50.'),
            _claude('opus', 'opus - latest Opus (Opus 5.5)', 'Complex reasoning. ' + _PRICE + '$4 / $20.'),
            _claude('sonnet', 'sonnet - latest Sonnet (Sonnet 5.5)', 'Everyday work; usually enough to fill in a '
                    'configuration. ' + _PRICE + '$2 / $10.'),
            _claude('haiku', 'haiku - latest Haiku (Haiku 4.5)', 'Fastest and lightest. ' + _PRICE + '$1 / $5.' + _NO_EFFORT, ()),
            _claude('best', 'best - Fable where available, otherwise Opus', 'Resolved by Claude Code from what the account may use.'),
            _claude('claude-fable-5-1', 'claude-fable-5-1 (pinned version)', _PRICE + '$10 / $50.'),
            _claude('claude-fable-5', 'claude-fable-5 (pinned version)', _PRICE + '$10 / $50.'),
            _claude('claude-opus-5-5', 'claude-opus-5-5 (pinned version)', _PRICE + '$4 / $20.'),
            _claude('claude-opus-5', 'claude-opus-5 (pinned version)', _PRICE + '$5 / $25.'),
            _claude('claude-opus-4-8', 'claude-opus-4-8 (pinned version)', _PRICE + '$5 / $25.'),
            _claude('claude-opus-4-7', 'claude-opus-4-7 (pinned version)', _PRICE + '$5 / $25.'),
            _claude('claude-opus-4-6', 'claude-opus-4-6 (pinned version)', _PRICE + '$5 / $25.' + _NO_XHIGH, CLAUDE_EFFORTS_46),
            _claude('claude-sonnet-5-5', 'claude-sonnet-5-5 (pinned version)', _PRICE + '$2 / $10.'),
            _claude('claude-sonnet-5', 'claude-sonnet-5 (pinned version)', _PRICE + '$2 / $10.'),
            _claude('claude-sonnet-4-6', 'claude-sonnet-4-6 (pinned version)', _PRICE + '$3 / $15.' + _NO_XHIGH, CLAUDE_EFFORTS_46),
            _claude('claude-sonnet-4-5', 'claude-sonnet-4-5 (pinned version)', _PRICE + '$3 / $15.' + _NO_EFFORT, ()),
            _claude('claude-haiku-4-5', 'claude-haiku-4-5 (pinned version)', _PRICE + '$1 / $5.' + _NO_EFFORT, ()),
        ]),
    # Shown only when the Codex app's own list (below) cannot be read.
    'codex': dict(
        verified='2026-10-03', source='https://learn.chatgpt.com/docs/models', origin='hand_table',
        efforts=list(CODEX_EFFORTS),
        default_note='Nothing is passed: the CLI uses your Codex configuration.',
        # Effort reaches codex as `--config model_reasoning_effort="<level>"`, and only if its --help lists --config.
        caveat='Local CLI help was inspected without a model request. Model access depends on the account; '
               'Ultra permits delegation in Codex, while sizing disables tools and delegation.',
        models=[dict(id=model_id, label=label, note=note,
                     efforts=list(CODEX_EFFORTS[:4] if model_id == 'gpt-5.5' else
                                  CODEX_EFFORTS[:-1] if model_id == 'gpt-6-luna' else CODEX_EFFORTS))
                for model_id, label, note in (
            ('gpt-6.1-sol', 'gpt-6.1-sol - Sol', 'Near-Astra performance at a lower cost.'),
            ('gpt-6-astra', 'gpt-6-astra - Astra', 'Most capable. Requested benchmark model.'),
            ('gpt-6-luna', 'gpt-6-luna - Luna', 'Most efficient.'),
            ('gpt-6-sol', 'gpt-6-sol - Sol (previous generation)', 'Previous generation workhorse model.'),
            ('gpt-5.5', 'gpt-5.5 (legacy)', 'Retires from Codex on 2026-10-14.'))]),
    'disabled': dict(verified=None, source=None, efforts=[], default_note='No agent is called.', models=[]),
}

# The Codex app's own list. Looked for in GATOR_CODEX_MODELS_CACHE (a file; "off" = never read one, which the test
# suite sets), else in $CODEX_HOME, ~/.codex and - from WSL - the Windows users' .codex folders, where the Codex
# desktop app keeps it. The most recently written file wins.
CODEX_CACHE_ENV = 'GATOR_CODEX_MODELS_CACHE'
_WINDOWS_USERS = Path('/mnt/c/Users')
_MODEL_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,99}')        # passed to the CLI as --model
_LEVEL = re.compile(r'[a-z][a-z0-9_-]{0,19}')
_DAY = re.compile(r'\d{4}-\d{2}-\d{2}')
_codex_where = None     # the search inputs of the last search, and what it found (a Path, or None)
_codex_file = None
_codex_read = {}        # (path, mtime_ns, size) -> what that one version of the file gave


def _codex_candidates():
    override = os.environ.get(CODEX_CACHE_ENV)
    if override is not None:
        override = override.strip()
        return [] if override.lower() in ('', 'off', 'none') else [Path(override)]
    homes = [os.environ.get('CODEX_HOME'), str(Path.home() / '.codex')]
    files = [Path(home) / 'models_cache.json' for home in homes if home]
    try:
        files += sorted(_WINDOWS_USERS.glob('*/.codex/models_cache.json'))
    except OSError:
        pass
    return files


def _newest(paths):
    found = []
    for path in paths:
        try:
            found.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return max(found, key=lambda item: item[0])[1] if found else None


def _text(value, limit=300) -> str:
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def _priority(entry):
    rank = entry.get('priority')
    return rank if isinstance(rank, int) and not isinstance(rank, bool) else 10 ** 6


def _from_codex_file(path):
    """(listing, None) of one models_cache.json, or (None, why not). Takes only what the drop-downs show - name,
    description, effort levels, default effort, retirement - and never `identity` or any other part of the file.
    Models the app hides (visibility other than "list") are left out, as in the app's own picker."""
    try:
        raw = json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError) as exc:
        return None, f'{path} could not be read ({type(exc).__name__})'
    entries = raw.get('models') if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return None, f'{path} holds no model list'
    models = []
    for entry in sorted((e for e in entries if isinstance(e, dict)), key=_priority):
        slug = entry.get('slug')
        if (entry.get('visibility') != 'list' or not isinstance(slug, str) or not _MODEL_NAME.fullmatch(slug)
                or any(m['id'] == slug for m in models)):
            continue
        levels = entry.get('supported_reasoning_levels')
        levels = [level.get('effort') for level in levels if isinstance(level, dict)] if isinstance(levels, list) else []
        efforts = list(dict.fromkeys(e for e in levels if isinstance(e, str) and _LEVEL.fullmatch(e)))
        default = entry.get('default_reasoning_level')
        upgrade = entry.get('upgrade') if isinstance(entry.get('upgrade'), dict) else {}
        retires = _text(upgrade.get('retirement_at'))[:10]
        retires = retires if _DAY.fullmatch(retires) else ''
        note = ' '.join(part for part in (
            _text(entry.get('description')),
            f'Codex default effort: {default}.' if isinstance(default, str) and default in efforts else '',
            _text(upgrade.get('migration_markdown'))) if part)
        models.append(dict(id=slug, label=slug + (f' (retires {retires})' if retires else ''),
                           note=note or 'Listed by the Codex app.', efforts=efforts))
    if not models:
        return None, f'{path} lists no model'
    return dict(models=models, file=str(path), fetched_at=_text(raw.get('fetched_at'), 40) or None,
                client_version=_text(raw.get('client_version'), 40) or None), None


def codex_app_listing(search=False):
    """(listing, None), or (None, why there is none). ``search`` looks for the file again - the Agent tab does on every
    settings read; validation reuses the place found last and re-reads the file only when it changed."""
    global _codex_where, _codex_file
    where = (os.environ.get(CODEX_CACHE_ENV), os.environ.get('CODEX_HOME'), str(Path.home()), str(_WINDOWS_USERS))
    if search or where != _codex_where:
        _codex_where, _codex_file = where, _newest(_codex_candidates())
    if _codex_file is None:
        return None, ('reading the Codex app’s list is switched off' if (where[0] or '').strip().lower() in ('off', 'none')
                      else 'the Codex app’s model list (models_cache.json) was not found')
    try:
        stat = _codex_file.stat()
    except OSError:
        _codex_where = None                                     # gone: look again next time
        return None, f'{_codex_file} is no longer there'
    key = (str(_codex_file), stat.st_mtime_ns, stat.st_size)
    if key not in _codex_read:
        _codex_read.clear()
        _codex_read[key] = _from_codex_file(_codex_file)
    return _codex_read[key]


def codex_entry(search=False) -> dict:
    """The Codex list the Agent tab offers: the app's own when it can be read, else the hand table with the reason."""
    listing, problem = codex_app_listing(search)
    if listing is None:
        return dict(CATALOG['codex'], cache_note=problem)
    efforts = list(dict.fromkeys([*CODEX_EFFORTS, *(e for m in listing['models'] for e in m['efforts'])]))
    return dict(CATALOG['codex'], origin='codex_app', models=listing['models'], efforts=efforts,
                verified=(listing['fetched_at'] or '')[:10] or None, fetched_at=listing['fetched_at'],
                cache_file=listing['file'], client_version=listing['client_version'])


def _entry(provider) -> dict:
    return codex_entry() if provider == 'codex' else CATALOG.get(provider, {})


def efforts_for(provider) -> tuple:
    """Effort levels a provider's CLI accepts. A provider without its own list (``disabled``, unknown) keeps any
    level some provider accepts, so switching provider never invalidates a saved file by itself."""
    return tuple(_entry(provider).get('efforts') or dict.fromkeys([*CLAUDE_EFFORTS, *codex_entry()['efforts']]))


def model_entry(provider, model):
    return next((m for m in _entry(provider).get('models', ()) if m['id'] == model), None)


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
    listing['codex'] = codex_entry(search=True)                  # the Codex app may have refreshed its list since
    return listing
