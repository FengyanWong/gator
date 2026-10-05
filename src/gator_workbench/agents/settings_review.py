"""A review of the SETTINGS of the whole workbench - run configuration, RL network, RL training, output - as
opposed to the three tables a proposal patches.

The agent answers a `settings_review` request with `suggestions` (one setting, one value, a reason and a source
each) and `encoder_ideas`. Nothing here is applied by an agent or by the backend: a suggestion is a row the user
may apply with a click, exactly as if the value had been typed into its panel. This module decides WHICH settings
may be suggested at all, gives the agent their present values and meaning, and checks every suggestion against the
schema and the static validation before the user sees it.

Never suggestible, whatever a reply contains: the circuit, the connection profile, a model source, the output
folder, project names - paths, identifiers and choices that are the user's alone.

Online research is optional and per request. Then - and only then - the agent may search the web and open pages
of PUBLICATION_DOMAINS; it is given a reduced description of the task with no device, instance or size in it, so
there is nothing of the design that a hostile page could talk it into sending anywhere.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

from ..schema import ENCODER_TYPES, AdvancedRL, NetworkConfig, OutputSettings, RunSettings

# Where a setting lives -> the fields of it that may be suggested.
SUGGESTIBLE = {
    'run': ('mode', 'concurrency', 'max_evaluations', 'max_spectre_launches', 'max_wall_seconds', 'max_retries',
            'max_consecutive_failures', 'max_consecutive_infrastructure_failures', 'seed', 'stop_at_first_feasible', 'frozen_action',
            'continual_learning'),
    'run.network': tuple(NetworkConfig.model_fields),
    'run.advanced': tuple(name for name in AdvancedRL.model_fields if name != 'spec_registry'),
    'output': ('save_learner_updates', 'save_checkpoints', 'save_replay_snapshots', 'save_transition_archive', 'export_summary_csv',
               'checkpoint_every_evaluations', 'checkpoint_every_seconds', 'keep_last_checkpoints'),
}
# Two fields that are ONE setting: a checkpoint interval counted in evaluations or in seconds (user request 2026-09-22;
# validation.py refuses both at once). A suggested value for one empties the other - on the copy it is tried on, and
# when the user applies it (`clears`). Always, not only when the other has a value: an absent
# `checkpoint_every_evaluations` still means the schema's default of 50.
EXCLUSIVE = {'output.checkpoint_every_evaluations': 'output.checkpoint_every_seconds',
             'output.checkpoint_every_seconds': 'output.checkpoint_every_evaluations'}
MODELS = {'run': RunSettings, 'run.network': NetworkConfig, 'run.advanced': AdvancedRL, 'output': OutputSettings}
PANELS = {'run': 'Run configuration', 'run.network': 'RL network', 'run.advanced': 'RL network (Advanced)', 'output': 'Output settings'}
PATHS = tuple(f'{group}.{name}' for group, names in SUGGESTIBLE.items() for name in names)

# Publishers, preprint servers and code hosts. WebFetch rules match the HOST of a URL; `*.` covers subdomains.
PUBLICATION_DOMAINS = ('arxiv.org', '*.arxiv.org', 'ieeexplore.ieee.org', 'dl.acm.org', 'openreview.net', 'proceedings.mlr.press',
                       'proceedings.neurips.cc', 'papers.nips.cc', 'aclanthology.org', 'link.springer.com', 'www.sciencedirect.com',
                       'www.nature.com', 'www.mdpi.com', 'doi.org', 'www.semanticscholar.org', 'api.semanticscholar.org',
                       'github.com', 'raw.githubusercontent.com', 'pytorch-geometric.readthedocs.io')
HOST = re.compile(r'^(\*\.)?[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$')
WEB_LINK = re.compile(r'^https?://', re.IGNORECASE)
WEB_MAX_TURNS = 40                   # bounds what one research request can cost (there is no time limit: status record 7.48)


def domains(extra=()) -> tuple:
    """The built-in list plus hosts the OPERATOR added in the settings file. Never taken from a request."""
    added = [str(item).strip().lower() for item in (extra or ()) if isinstance(item, str)]
    return tuple(dict.fromkeys(PUBLICATION_DOMAINS + tuple(host for host in added if HOST.match(host))))


def _get(config: dict, path: str):
    node = config
    for part in path.split('.'):
        node = (node or {}).get(part) if isinstance(node, dict) else None
    return node


def _set(config: dict, path: str, value) -> dict:
    result = deepcopy(config)
    node = result
    parts = path.split('.')
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return result


def _apply(config: dict, path: str, value, clears) -> dict:
    result = _set(config, path, value)
    for other in clears:
        result = _set(result, other, None)
    return result


def settings_data(config: dict) -> dict:
    """Present value, meaning and limits of every setting that may be suggested, grouped by the panel it is in."""
    listing = {}
    for group, names in SUGGESTIBLE.items():
        properties = MODELS[group].model_json_schema().get('properties', {})
        listing[group] = dict(panel=PANELS[group], fields={
            name: {key: value for key, value in dict(
                now=_get(config, f'{group}.{name}'), meaning=properties.get(name, {}).get('description'),
                choices=properties.get(name, {}).get('enum'), minimum=properties.get(name, {}).get('minimum', properties.get(name, {}).get('exclusiveMinimum')),
                maximum=properties.get(name, {}).get('maximum', properties.get(name, {}).get('exclusiveMaximum'))).items() if value is not None or key == 'now'}
            for name in names})
    return listing


def publication_presets() -> dict:
    """The curated, cited presets of network_presets.py in a compact form: values per encoder, where each comes from,
    and the publications. They are a starting point with a citation - none was evaluated on this project's circuits."""
    from .. import network_presets
    described = network_presets.describe()
    encoders = {}
    for encoder, entry in described['settings'].items():
        published = entry.get('publication') or {}
        where = {}
        for field, record in (entry.get('provenance') or {}).items():
            if isinstance(record, dict):
                where[field] = ' | '.join(str(record[key]) for key in ('basis', 'source', 'match') if record.get(key))
        encoders[encoder] = dict(summary=entry.get('summary'), network=published.get('network'), advanced=published.get('advanced'), where=where)
    references = {key: {k: ref.get(k) for k in ('short', 'title', 'venue', 'year', 'url', 'algorithm', 'budget')}
                  for key, ref in (described.get('references') or {}).items()}
    return dict(encoders=encoders, references=references, scale_note=described.get('scale_note'),
                tested=described.get('tested'), learned=described.get('learned'),
                note='The network sizes were collected by hand from the cited publications (docs/network-presets.md). None was evaluated on '
                     'a circuit of this project, and they differ widely, so they must not be used for an equal-size comparison of encoders. '
                     'The three values under `tested` were compared on this project and chosen (record 7.183); `learned` are all the training values of '
                     'the runs that learned there, which every preset now uses (record 7.192). The network sizes are still the published ones.')


def task_digest(config: dict, circuit_summary: dict | None) -> dict:
    """What a settings review needs to know about the task - and nothing of the design itself: no instance, net,
    device size or file. Safe to have in the context of a request that may read web pages."""
    kinds = {}
    for device in (circuit_summary or {}).get('devices') or []:
        kinds[str(device.get('kind'))] = kinds.get(str(device.get('kind')), 0) + 1
    parameters = config.get('parameters') or []
    return dict(circuit_class=(circuit_summary or {}).get('circuit_class') or (config.get('circuit') or {}).get('circuit_class'),
                device_count=(circuit_summary or {}).get('device_count'), device_kinds=kinds,
                optimized_variables=sum(1 for row in parameters if row.get('optimized', True) and not row.get('binding_group')),
                bound_variables=sum(1 for row in parameters if row.get('binding_group')),
                targets=[dict(metric_id=row.get('metric_id'), constraint=row.get('constraint'), hard=row.get('hard'), active=row.get('active'))
                         for row in config.get('targets') or []],
                measurements=len(config.get('measurements') or []), available_encoders=list(ENCODER_TYPES))


def readiness_digest(readiness: dict | None) -> dict | None:
    """The start checklist without anything of the design: states and codes, no detail text, no rows."""
    if not readiness:
        return None
    return dict(ready=readiness.get('ready'), run=readiness.get('run'), facts=readiness.get('facts'),
                items=[dict(id=item.get('id'), title=item.get('title'), status=item.get('status')) for item in readiness.get('items') or []],
                issues=[dict(level=issue.get('level'), code=issue.get('code'), path=issue.get('path')) for issue in readiness.get('issues') or []])


def _web_link(value) -> str:
    """A reply's link, kept only when it is a web address: the page renders it as a link, and a reply that read web pages
    could carry a `javascript:` one (review of 2026-09-29). Anything else becomes empty."""
    url = str(value or '')[:300]
    return url if WEB_LINK.match(url) else ''


def normalize(output: dict) -> dict:
    """The parts of a reply that belong to a settings review, cleaned. A suggestion for anything but a suggestible
    setting is dropped and named; values arrive as JSON text ("0.0003", "true", "\\"gatv2\\"") or as plain words."""
    kept, refused = [], []
    for entry in (output.get('suggestions') if isinstance(output.get('suggestions'), list) else [])[:40]:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
            continue
        path = entry['path'].strip()
        if path not in PATHS:
            refused.append(f'{path}: not a setting an agent may suggest')
            continue
        raw = entry.get('value')
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
            except ValueError:
                value = raw.strip()
        else:
            value = raw
        if isinstance(value, (dict, list)):
            refused.append(f'{path}: a suggested value must be a single number, word or true/false')
            continue
        text = lambda key, limit: str(entry.get(key) or '')[:limit]                     # noqa: E731
        kept.append(dict(path=path, value=value, reason=text('reason', 800), source=text('source', 600), url=_web_link(entry.get('url')), quote=text('quote', 400)))
    ideas = [dict(name=str(idea.get('name') or '')[:120], source=str(idea.get('source') or '')[:600], url=_web_link(idea.get('url')),
                  why=str(idea.get('why') or '')[:800], what_it_takes=str(idea.get('what_it_takes') or '')[:800])
             for idea in (output.get('encoder_ideas') if isinstance(output.get('encoder_ideas'), list) else [])[:10]
             if isinstance(idea, dict) and str(idea.get('name') or '').strip()]
    return dict(suggestions=kept, refused=refused, encoder_ideas=ideas)


def check(config: dict, suggestions, *, validate_config) -> dict:
    """Try every suggestion on a COPY of the configuration. ``validate_config(dict) -> (problem | None, blocking codes)``
    is supplied by the API layer (schema + static validation with the loaded circuit). Nothing is applied here."""
    _, before = validate_config(config)
    checked, together = [], config
    for item in suggestions:
        now = _get(config, item['path'])
        clears = [EXCLUSIVE[item['path']]] if item['path'] in EXCLUSIVE and item['value'] is not None else []
        record = dict(item, now=now, panel=PANELS[item['path'].rsplit('.', 1)[0]], changes=now != item['value'], applicable=False, problem=None,
                      alone=None, clears=clears)
        if not record['changes']:
            record['problem'] = 'It is already set to this value.'
        else:
            problem, after = validate_config(_apply(config, item['path'], item['value'], clears))
            new = sorted(set(after) - set(before))
            record['problem'] = problem
            record['applicable'] = problem is None          # a legal value; `alone` says when it needs another row of this list
            record['alone'] = f"Applied alone it raises a blocking issue ({', '.join(new)}); apply it together with the related rows." if new else None
            if problem is None:
                together = _apply(together, item['path'], item['value'], clears)
        checked.append(record)
    problem, after = validate_config(together)
    new = sorted(set(after) - set(before))
    return dict(suggestions=checked, all_together=dict(ok=problem is None and not new, problem=problem or (', '.join(new) if new else None)))
