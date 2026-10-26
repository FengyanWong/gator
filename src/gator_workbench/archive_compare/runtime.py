"""What a run of the comparison loads before its first design: the pinned files of `run.comparison`, checked against the
compiled task, and the search that proposes its designs (`turbo_archive`: T0/T+; `mobo`: M+).

Files (written by the comparison's step 2 and kept outside the repository):
  - initial designs (archive_compare.initial): `group_ids` and `designs[].proposal` - the common first designs;
  - a TuRBO archive: {"format": "archive-compare-turbo-archive-v1", "group_ids", "u": [[...]], "reward": [...]} - unit-cube
    points of the archived designs and their rewards under the run's goal view (None for a failed design);
  - a MOBO archive: {"format": "archive-compare-mobo-archive-v1", "group_ids", "u", "metrics": [{...}], "validity":
    [{...}], "status": [...]} - every recorded output of each archived design.
Each is refused unless its sha256 is the one the configuration pins and its groups are the compiled task's, in order.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .coords import group_rows
from .mobo import MoboProposer, Problem
from .turbo_archive import ArchiveProposer

INITIAL_FORMAT = 'archive-compare-initial-designs-v1'
TURBO_ARCHIVE_FORMAT = 'archive-compare-turbo-archive-v1'
MOBO_ARCHIVE_FORMAT = 'archive-compare-mobo-archive-v1'


class ComparisonFileError(ValueError):
    pass


def _pinned(path, sha256, what) -> dict:
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ComparisonFileError(f'The {what} file {path} is not the one this run pins (sha256 differs)')
    return json.loads(data)


def _groups_match(found, groups, what):
    expected = [g['id'] for g in groups]
    if list(found) != expected:
        raise ComparisonFileError(f'The {what} file names groups {list(found)[:5]}... but the compiled task varies {expected[:5]}...')


def initial_designs(comparison, groups, mapper) -> list:
    """The common first designs' proposals, each checked legal on the compiled task."""
    data = _pinned(comparison.initial_designs, comparison.initial_designs_sha256, 'initial designs')
    if data.get('format') != INITIAL_FORMAT:
        raise ComparisonFileError(f"The initial designs file has format {data.get('format')!r}")
    _groups_match(data['group_ids'], groups, 'initial designs')
    proposals = []
    for design in data['designs']:
        proposal = {g: float(design['proposal'][g]) for g in data['group_ids']}
        legal = mapper.legalize(proposal)
        if any(legal.group_values[g] != design['group_values'][g] for g in data['group_ids']):
            raise ComparisonFileError(f"Initial design {design['index']} no longer legalizes to the values it records")
        proposals.append(proposal)
    return proposals


def problem_for(config, compiled):
    """M+'s Problem from the run's compiled specs (its goal view) and its two objectives."""
    rows = []
    for spec in compiled.specs:
        if spec.active and spec.required:
            rows.append(dict(metric=spec.metric_id, unit=spec.unit, lower=spec.lower, upper=spec.upper, scale=spec.scale))
    objectives = [o.model_dump() for o in config.run.comparison.objectives]
    return Problem(rows, objectives, energy_rule=config.run.comparison.energy_rule)


def build_proposer(config, compiled, *, state=None):
    """The run's search: restored from `state` (a resume) or new, with its archive."""
    groups = group_rows(compiled)
    comparison = config.run.comparison
    optimizer = config.run.optimizer
    archive = None
    if comparison.archive is not None:
        archive = _pinned(comparison.archive, comparison.archive_sha256, 'archive')
        _groups_match(archive['group_ids'], groups, 'archive')
    if optimizer == 'turbo_archive':
        if state is not None:
            proposer = ArchiveProposer.from_state(state)
        else:
            if archive is not None and archive.get('format') != TURBO_ARCHIVE_FORMAT:
                raise ComparisonFileError(f"A turbo_archive run reads a {TURBO_ARCHIVE_FORMAT} archive, not {archive.get('format')!r}")
            proposer = ArchiveProposer(groups, seed=config.run.seed, archive=archive, **comparison.settings)
        if proposer.group_ids != [g['id'] for g in groups]:
            raise ComparisonFileError('The saved search varies other groups than the compiled task')
        return proposer
    if optimizer == 'mobo':
        problem = problem_for(config, compiled)
        if state is not None:
            return MoboProposer.from_state(state, problem)
        source = None
        if archive is not None:
            if archive.get('format') != MOBO_ARCHIVE_FORMAT:
                raise ComparisonFileError(f"A mobo run reads a {MOBO_ARCHIVE_FORMAT} archive, not {archive.get('format')!r}")
            source = dict(u=archive['u'], y=[problem.outcome(m, v, s)[0]
                                             for m, v, s in zip(archive['metrics'], archive['validity'], archive['status'])])
        return MoboProposer(groups, problem, seed=config.run.seed, archive=source, settings=comparison.settings)
    raise ValueError(f'{optimizer} is not a comparison search')


def started_event(proposer) -> dict:
    """What the run's event log says when its search starts."""
    search = proposer.search
    if hasattr(search, 'summary'):
        return dict(search.summary(), groups=len(proposer.group_ids))
    return dict(version=search.state_dict()['version'], archived=search.archived, groups=len(proposer.group_ids),
                settings=search.settings, problem=search.problem.describe())
