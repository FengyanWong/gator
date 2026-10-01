"""Proposals: validation, scope enforcement, structured diff, hash-bound approval, application.

A proposal is only ever a suggestion:
  * passing the JSON schema authorizes nothing - rows are re-validated with the configuration
    schema, the patch must stay inside the scope of the REQUEST KIND (and, for modify_fields,
    inside the selected rows/fields), and the result is semantically validated again;
  * an approval is bound to the proposal hash AND to the configuration and circuit hashes the
    proposal was generated against. If either changed, the approval is invalidated and the
    diff must be reviewed again;
  * applying a proposal changes configuration only. It never writes a circuit, never starts a
    simulation and never touches validation, directory permissions or approval rules. (The one
    kind that goes further, `virtuoso_setup`, has its approved `setup` written into the cell's
    WORKING COPY by the API route after this step - never into the user's cell.);
  * a failed proposal leaves the user's configuration untouched.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import threading

from pydantic import ValidationError

from ..schema import SECTION_KEYS, SECTIONS, WorkbenchConfig, canonical_json, config_hash
from ..storage.dataset import utcnow
from .base import AgentError, AgentRequest, AgentResult, SECTIONS_BY_KIND
from . import settings_review


CHECKLIST_STATES = ('done', 'missing', 'warning', 'unknown', 'not_applicable')


def _hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf8')).hexdigest()


class ProposalRejected(ValueError):
    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or [message]


def normalize(request: AgentRequest, result: AgentResult):
    """Validate the structured output against scope and row schemas. Returns the clean patch."""
    output = result.structured_output
    problems = []
    allowed_top = {'kind', 'patch', 'circuit_changes', 'reasoning', 'warnings', 'unresolved', 'checklist', 'suggestions', 'encoder_ideas',
                   'setup'}
    extra = set(output) - allowed_top
    if extra:
        problems.append(f'Unexpected top-level keys {sorted(extra)} (a proposal cannot carry settings or instructions)')
    patch = output.get('patch')
    if not isinstance(patch, list):
        raise ProposalRejected('`patch` must be a list', ['`patch` must be a list'])
    sections = SECTIONS_BY_KIND[request.kind]
    selected = {(s['section'], s['key']): set(s.get('fields') or []) for s in request.selection}
    clean = []
    for index, op in enumerate(patch):
        where = f'patch[{index}]'
        if not isinstance(op, dict) or set(op) - {'op', 'section', 'key', 'value', 'basis'}:
            problems.append(f'{where}: malformed operation')
            continue
        action, section, key = op.get('op'), op.get('section'), op.get('key')
        if action not in ('add', 'replace', 'remove') or section not in SECTIONS or not isinstance(key, str):
            problems.append(f'{where}: invalid op/section/key')
            continue
        if section not in sections:
            problems.append(f'{where}: a `{request.kind}` request may not change `{section}`')
            continue
        if request.kind == 'minimal_start' and action != 'add':
            # "As few changes as possible" is a rule here, not a wish: a row the backend finds nothing wrong with stays as it is.
            allowed = ((request.readiness or {}).get('changeable_rows') or {}).get(section)
            if allowed != '*' and key not in (allowed or ()):
                problems.append(f'{where}: `{section}/{key}` has no blocking issue, so a minimal-start request may not {action} it')
                continue
        if request.kind == 'modify_fields':
            if (section, key) not in selected or action != 'replace':
                problems.append(f'{where}: only the selected rows may be replaced')
                continue
        value = None
        if action != 'remove':
            try:
                value = SECTIONS[section].model_validate(op.get('value')).model_dump(mode='json')
            except ValidationError as exc:
                problems.append(f'{where}: invalid {section} row: ' + '; '.join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:6]))
                continue
            if value[SECTION_KEYS[section]] != key:
                problems.append(f'{where}: key {key!r} differs from the row ID {value[SECTION_KEYS[section]]!r}')
                continue
        clean.append(dict(op=action, section=section, key=key, value=value, basis=str(op.get('basis') or '')[:1000]))
    if problems:
        raise ProposalRejected('The proposal was rejected by backend validation', problems)
    # The agent no longer proposes netlist changes (the request kind went on 2026-09-22: nothing could load the file it wrote).
    # An empty list, as older exported results carry, is accepted.
    if output.get('circuit_changes'):
        raise ProposalRejected('The agent cannot change the circuit: it proposes rows (and, for a working copy, its Maestro '
                               'setup)', ['circuit_changes present'])
    text = lambda name: [str(item)[:1000] for item in (output.get(name) or []) if isinstance(item, (str, int, float))]
    # Advisory text only: it changes nothing and is not part of what an approval is bound to. Malformed entries are dropped.
    checklist = [dict(item=str(entry.get('item') or '')[:200], status=entry.get('status'), who=entry.get('who'),
                      action=str(entry.get('action') or '')[:600], basis=str(entry.get('basis') or '')[:600])
                 for entry in (output.get('checklist') if isinstance(output.get('checklist'), list) else [])[:40]
                 if isinstance(entry, dict) and entry.get('status') in CHECKLIST_STATES and entry.get('who') in ('you', 'agent')
                 and str(entry.get('item') or '').strip()]
    # Suggestions for settings exist for a settings_review only; from any other request they are dropped, not obeyed.
    review = (settings_review.normalize(output) if request.kind in ('settings_review', 'run_review')
              else dict(suggestions=[], refused=[], encoder_ideas=[]))
    return dict(patch=clean, checklist=checklist, review=review,
                setup=_setup(request, output.get('setup')),
                reasoning=str(output.get('reasoning') or '')[:8000], warnings=text('warnings'), unresolved=text('unresolved'))


def _setup(request, raw):
    """The `setup` part of a virtuoso_setup proposal, reduced to its four parts in their shapes; from any other request
    it is dropped, not obeyed. What it may contain (functions, bindable values, net names and voltages) is checked by
    the backend on top."""
    if request.kind != 'virtuoso_setup' or not isinstance(raw, dict):
        return None
    problems, clean = [], {}
    analyses = raw.get('analyses')
    if analyses is not None:
        if not isinstance(analyses, dict) or any(not isinstance(k, str) or not isinstance(v, dict) for k, v in analyses.items()):
            problems.append('setup.analyses must map an analysis name to its options')
        else:
            clean['analyses'] = {k[:40]: {str(o)[:60]: str(v)[:200] for o, v in options.items()} for k, options in list(analyses.items())[:20]}
    variables = raw.get('variables')
    if variables is not None:
        if not isinstance(variables, dict):
            problems.append('setup.variables must map a variable name to its value')
        else:
            clean['variables'] = {str(k)[:64]: str(v)[:200] for k, v in list(variables.items())[:100]}
    conditions = raw.get('initial_conditions')
    if conditions is not None:
        if not isinstance(conditions, dict):
            problems.append('setup.initial_conditions must map a net to its start voltage')
        else:
            clean['initial_conditions'] = {str(k)[:128]: str(v)[:64] for k, v in list(conditions.items())[:200]}
    bindings = raw.get('bindings')
    if bindings is not None:
        if not isinstance(bindings, list) or any(not isinstance(b, dict) or set(b) != {'cell', 'instance', 'parameter', 'variable'} for b in bindings):
            problems.append('setup.bindings must list {cell, instance, parameter, variable} objects')
        else:
            clean['bindings'] = [{k: str(b[k])[:128] for k in ('cell', 'instance', 'parameter', 'variable')} for b in bindings[:100]]
    if problems:
        raise ProposalRejected('The proposal was rejected by backend validation', problems)
    return clean


def apply_patch(config: dict, patch, *, selection=None) -> dict:
    """Pure function: returns a NEW configuration dict. The input is never mutated."""
    result = deepcopy(config)
    selected = {(s['section'], s['key']): set(s.get('fields') or []) for s in (selection or [])}
    for op in patch:
        section, key, id_field = op['section'], op['key'], SECTION_KEYS[op['section']]
        rows = result.setdefault(section, [])
        index = next((i for i, row in enumerate(rows) if row.get(id_field) == key), None)
        if op['op'] == 'add':
            if index is not None:
                raise ProposalRejected(f'{section}/{key} already exists; use replace')
            rows.append(op['value'])
        elif index is None:
            raise ProposalRejected(f'{section}/{key} does not exist')
        elif op['op'] == 'remove':
            rows.pop(index)
        else:
            fields = selected.get((section, key))
            if fields:                                   # modify_fields: nothing outside the chosen fields may move
                changed = {f for f in set(rows[index]) | set(op['value']) if rows[index].get(f) != op['value'].get(f)}
                if changed - fields:
                    raise ProposalRejected(f'{section}/{key}: fields {sorted(changed - fields)} were not selected for change')
            rows[index] = op['value']
    return result


def structured_diff(before: dict, after: dict) -> list:
    diff = []
    for section, id_field in SECTION_KEYS.items():
        old = {row[id_field]: row for row in before.get(section, [])}
        new = {row[id_field]: row for row in after.get(section, [])}
        for key in sorted(set(old) | set(new)):
            if key not in old:
                diff.append(dict(section=section, key=key, change='added', fields=[
                    dict(field=f, before=None, after=v) for f, v in new[key].items()]))
            elif key not in new:
                diff.append(dict(section=section, key=key, change='removed', fields=[
                    dict(field=f, before=v, after=None) for f, v in old[key].items()]))
            else:
                fields = [dict(field=f, before=old[key].get(f), after=new[key].get(f))
                          for f in sorted(set(old[key]) | set(new[key])) if old[key].get(f) != new[key].get(f)]
                if fields:
                    diff.append(dict(section=section, key=key, change='modified', fields=fields))
    return diff


class ProposalStore:
    """In-memory proposal registry of one backend process (proposals are short-lived review items)."""
    def __init__(self):
        self._lock, self._items = threading.Lock(), {}

    def create(self, request: AgentRequest, result: AgentResult, *, circuit_hash) -> dict:
        try:
            normalized = normalize(request, result)
            preview = apply_patch(request.config, normalized['patch'], selection=request.selection)
            WorkbenchConfig.model_validate(preview)
        except ProposalRejected as exc:
            raise AgentError('schema_failure', '; '.join(exc.problems)[:4000], problems=exc.problems)
        except ValidationError as exc:
            raise AgentError('schema_failure', 'The patched configuration is not valid: ' + str(exc)[:2000])
        proposal = dict(
            proposal_id=result.request_id, provider=result.provider, origin=result.origin, kind=request.kind,
            created_utc=utcnow().isoformat(), status='proposed', base_config_hash=config_hash(request.config),
            circuit_hash=circuit_hash, proposal_hash=_hash(dict(patch=normalized['patch'],
                                                                **({'setup': normalized['setup']} if normalized['setup'] is not None else {}))),
            patch=normalized['patch'], setup=normalized['setup'],
            diff=structured_diff(request.config, preview), reasoning=normalized['reasoning'],
            warnings=normalized['warnings'], unresolved=normalized['unresolved'], checklist=normalized['checklist'],
            suggestions=normalized['review']['suggestions'], refused_suggestions=normalized['review']['refused'],
            encoder_ideas=normalized['review']['encoder_ideas'],
            selection=request.selection,
            logs=result.logs, audit=result.audit, approval=None,
            authorizes='nothing: applying needs an explicit approval bound to this exact proposal, configuration and '
                       'circuit; circuit writes and simulations need their own separate authorization')
        with self._lock:
            self._items[proposal['proposal_id']] = proposal
        return proposal

    def get(self, proposal_id) -> dict:
        with self._lock:
            return self._get(proposal_id)

    def _get(self, proposal_id) -> dict:
        if proposal_id not in self._items:
            raise KeyError(proposal_id)
        return self._items[proposal_id]

    def _still_current(self, proposal, config, circuit_hash):
        reasons = []
        if config_hash(config) != proposal['base_config_hash']:
            reasons.append('the configuration changed after the proposal was generated')
        if circuit_hash != proposal['circuit_hash']:
            reasons.append('the circuit changed after the proposal was generated')
        return reasons

    # approve, apply and reject check a proposal's state and change it in one step under the store's lock: two presses
    # (a double click, a second tab) used to both pass the check, so a proposal could be applied - and written - twice.
    def approve(self, proposal_id, *, proposal_hash, config, circuit_hash) -> dict:
        with self._lock:
            return self._approve(self._get(proposal_id), proposal_hash, config, circuit_hash)

    def _approve(self, proposal, proposal_hash, config, circuit_hash) -> dict:
        if proposal['status'] not in ('proposed', 'approved'):
            raise ProposalRejected(f"Proposal is {proposal['status']}")
        if proposal_hash != proposal['proposal_hash']:
            raise ProposalRejected('The approval refers to a different proposal version')
        reasons = self._still_current(proposal, config, circuit_hash)
        if reasons:
            proposal.update(status='invalidated', invalidated_because=reasons)
            raise ProposalRejected('Approval refused: ' + ' and '.join(reasons) + '. Generate and review a new diff.', reasons)
        proposal.update(status='approved', approval=dict(approved_utc=utcnow().isoformat(),
                                                         proposal_hash=proposal_hash,
                                                         config_hash=proposal['base_config_hash'], circuit_hash=circuit_hash))
        return proposal

    def apply(self, proposal_id, *, config, circuit_hash) -> dict:
        """Returns the new configuration. An old approval does not survive a changed config/circuit."""
        with self._lock:
            return self._apply(self._get(proposal_id), config, circuit_hash)

    def _apply(self, proposal, config, circuit_hash) -> dict:
        if proposal['status'] != 'approved' or not proposal['approval']:
            raise ProposalRejected('The proposal has not been approved')
        reasons = self._still_current(proposal, config, circuit_hash)
        if reasons:
            proposal.update(status='invalidated', approval=None, invalidated_because=reasons)
            raise ProposalRejected('The earlier approval is no longer valid: ' + ' and '.join(reasons), reasons)
        updated = apply_patch(config, proposal['patch'], selection=proposal['selection'])
        WorkbenchConfig.model_validate(updated)
        proposal.update(status='applied', applied_utc=utcnow().isoformat())
        return updated

    def reject(self, proposal_id):
        with self._lock:
            proposal = self._get(proposal_id)
            proposal.update(status='rejected')
            return proposal
