"""Offline SAC on an explicit, frozen archive pool. Never constructs a simulator.

This is phase 0 of plan-general-network.md. Checkpoints are provisional transfer
weights; the specialist/proposal gates and online rehearsal still precede real runs.
Source archives are read-only; episode splits happen before optional relabelling.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import time

from . import families, network_inputs, spec_descriptors
from .checkpoints import CheckpointStore
from .model_inputs import INPUT_KEYS, pool_feature_schema, request_inputs, source_view  # input helpers remain importable here
from .modes import seed_everything
from .offline_storage import DiskSequence, DiskTransitions, shown_type as _shown_type
from .storage.atomic import read_json, write_json
from .trajectory import TrajectoryLoader


DEFAULT_SEED = 0
DEFAULT_UPDATES = 20_000


def identity(value) -> str:
    """Hash a value's sorted JSON representation while rejecting nonfinite JSON numbers."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def archive_identity(directory) -> str:
    """Pin tables, journal, static graphs/specs and recorded configuration; no weights/unpickling."""
    directory = Path(directory)
    files = [directory / name for name in ('run_manifest.json', 'effective_config.json', 'run_summary.json')]
    files += sorted((directory / 'data').rglob('*.parquet'))
    files += sorted((directory / 'data' / 'states' / 'static').glob('*.json'))
    files += [directory / 'data' / '_journal' / 'flushes.jsonl']
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(directory)).encode())
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
    return digest.hexdigest()


def shared_registry(registries, overrides):
    """Stable order, explicit reference conflicts, and no implicit unit conversion."""
    from analog_optimizer.models.inputs import SpecSchema
    entries = defaultdict(set)
    for registry in registries:
        for name, unit, reference in registry:
            entries[name].add((unit, float(reference)))
    if set(overrides) - entries.keys():
        raise ValueError('Reference override names a metric absent from the source registries')
    merged = []
    for name, values in sorted(entries.items()):
        units = {unit for unit, _ in values}
        if len(units) != 1:
            raise ValueError(f'Conflicting units for {name}: {sorted(units)}')
        if len(values) > 1 and name not in overrides:
            raise ValueError(f'Explicit reference override required for {name}')
        merged.append((name, next(iter(units)), float(overrides.get(name, next(iter(values))[1]))))
    # Must match compile.build_spec_schema for a WorkbenchConfig with spec_registry set.
    return SpecSchema(version='spec-input-custom-v1', metrics=tuple(merged))


@dataclass
class Pool:
    # A prepared offline archive pool with training splits, schemas, audit data and optional disk storage.
    training: dict
    validation: dict
    schema: object
    reward_settings: object
    audit: dict
    feature_schema: object = None          # None: the standard list (every pool before record 7.298)
    storage: object = None


MISSING_OPERATING_POINTS = ('refuse', 'mask')


def inputs_identity(run_dir, inputs) -> str | None:
    """What a source archive's designs are shown under these inputs, as one checksum - beside `archive_identity` for the
    source's entry of a request (`inputs_sha256`): the pool then refuses to be built once it changed. It is the view's
    key: the spec descriptions, the PDK's device numbers and family mapping, the second build's nets and test
    variables. `inputs`: the request's `inputs` block; None for inputs that show every design as recorded."""
    inputs = request_inputs(dict(inputs=inputs))
    if not (network_inputs.any_transfer(inputs) or inputs['vocabulary'] == families.NAME):
        return None
    return source_view(read_json(Path(run_dir) / 'effective_config.json'), inputs).key


def prepare_pool(request, *, progress=None, storage_dir=None):
    """Disk storage changes memory use, preserving validation and sampling semantics."""
    storage_mode = request.get('pool_storage', 'memory')
    if storage_mode not in ('memory', 'disk'):
        raise ValueError('pool_storage must be memory or disk')
    storage = None
    if storage_mode == 'disk':
        storage = DiskTransitions(None if storage_dir is None else Path(storage_dir) / 'transitions.sqlite')
    try:
        return _prepare_pool(request, progress=progress, storage=storage)
    except BaseException:
        if storage is not None:
            storage.close()
        raise


def _prepare_pool(request, *, progress=None, storage=None) -> Pool:
    """Read and validate every eligible transition, then split whole run-scoped episodes."""
    origin, fraction, seed, inputs, missing_points, transfer, migrated_settings = _pool_request_settings(request)
    groups, registries, sources = defaultdict(lambda: defaultdict(list)), [], []
    run_ids, candidates, settings = set(), set(), None
    relabel = request.get('relabel_upper', {})
    target_sets = relabel_targets(request)
    targets_only, balance = pool_options(request, target_sets, relabel, fraction)
    seen_tasks = set()
    for source in request['runs']:
        directory, manifest, config, summary, task, run_id, read_points = _read_pool_source(
            source, run_ids, origin, inputs, missing_points, registries)
        view = source_view(config, inputs) if transfer else None
        stated = stated_scales(config)                 # the Scale boxes this task filled: a moved limit leaves them alone
        # What the designs of this source are shown is read from the PDK and the task's files as they stand now, which
        # neither the request nor the archive's checksum covers (record 7.319): the audit says which view it was, and
        # a request that pinned one (`inputs_sha256`, from `inputs_identity`) is refused when it is another now.
        shown_as = None if view is None else view.key
        loader, raw, eligible, transitions, wanted = _load_pool_transitions(directory, source, run_id, shown_as)
        if targets_only and task not in target_sets:
            raise ValueError(f'{task} has no relabel_targets: with relabel_targets_only its transitions would not be pooled')
        seen_tasks.add(task)
        counts = Counter()
        original_settings = {}
        for row, transition in zip(eligible, transitions, strict=True):
            transition, settings, first, last, episode = _validate_pool_transition(
                row, transition, original_settings, candidates, run_id, manifest, origin, migrated_settings, settings, counts)
            # What the network is shown of this archive (network_inputs, record 7.298) - applied last: a copy under other
            # limits is re-scored and validated as recorded first (a shown observation no longer holds the recorded sizes).
            shown = (lambda t: t) if view is None else (lambda t: _shown(t, view))
            def keep(t):
                viewed = shown(t)
                return storage.append(viewed) if storage is not None else viewed
            _append_relabelled_transitions(
                keep, transition, first, last, episode, groups, task, relabel, target_sets, stated, counts, targets_only, balance)
        _record_pool_source(
            directory, source, run_id, task, read_points, shown_as, summary, transitions, raw, counts,
            original_settings, migrated_settings, sources, wanted)
        if storage is not None:
            storage.commit()
        del transitions, loader
        if progress:
            progress(dict(event='source_loaded', **sources[-1]))
    training, validation, schema, features, audit = _split_and_audit_pool(
        request, origin, seed, fraction, inputs, groups, registries, sources, settings, relabel, target_sets,
        migrated_settings, storage, progress, seen_tasks, targets_only, balance)
    return Pool(training, validation, schema, settings, audit, features, storage)


def _pool_request_settings(request) -> tuple:
    """Validate the pool request and resolve its split, input, and optional reward-migration settings."""
    origin = request['origin']
    if origin not in ('real', 'synthetic'):
        raise ValueError('Pool origin must be real or synthetic')
    fraction = request.get('holdout_fraction', 0.1)
    if not 0 <= fraction < 1 or not request.get('runs'):
        raise ValueError('Nonempty sources and a holdout_fraction from 0 (no holdout) to below 1 are required')
    seed = request.get('seed', DEFAULT_SEED)
    inputs = request_inputs(request)
    missing_points = request.get('missing_operating_points', 'refuse')
    if missing_points not in MISSING_OPERATING_POINTS:
        raise ValueError(f'missing_operating_points must be one of {MISSING_OPERATING_POINTS}')
    transfer = network_inputs.any_transfer(inputs) or inputs['vocabulary'] == families.NAME
    migrated_settings = None
    if 'migrate_reward_settings' in request:
        from analog_optimizer.measurements.specs import RewardSettings
        migrated_settings = RewardSettings(**request['migrate_reward_settings'])
    return origin, fraction, seed, inputs, missing_points, transfer, migrated_settings


def _read_pool_source(source, run_ids, origin, inputs, missing_points, registries) -> tuple:
    """Read one frozen source and validate its identity, origin, network inputs, and specification registry."""
    directory = Path(source['run_dir']).resolve()
    if archive_identity(directory) != source['archive_sha256']:
        raise ValueError(f'Archive changed after selection: {directory}')
    manifest = read_json(directory / 'run_manifest.json')
    config = read_json(directory / 'effective_config.json')
    summary = read_json(directory / 'run_summary.json')
    task = config['circuit']['task_id']
    run_id = manifest['run_id']
    if run_id in run_ids:
        raise ValueError(f'Duplicate source run: {run_id}')
    run_ids.add(run_id)
    if manifest.get('state') not in ('completed', 'stopped', 'failed', 'paused'):
        raise ValueError('Source run must be quiescent before freezing its archive')
    if manifest.get('mock') != (origin == 'synthetic') or manifest.get('provenance') != (
            'mock' if origin == 'synthetic' else 'real'):
        raise ValueError(f'Origin mismatch for {run_id}')
    network = manifest['architecture']['network']
    if network.get('vocabulary', 'standard') not in ('standard', families.NAME):
        raise ValueError('Offline pool currently requires the standard or family component list')
    # A source that read operating points keeps them in its recorded designs; the pool shows them only as the ratios
    # of the second build (record 7.317), never as the raw input. Until then such a source was refused.
    read_points = network_inputs.reads_operating_points(network)
    if inputs['operating_point_ratios'] and not read_points and missing_points != 'mask':
        raise ValueError(f'{run_id} read no operating points, and this request trains with the operating-point ratios: '
                         'leave the run out, or say missing_operating_points "mask" (its designs then show the ratios '
                         'as missing)')
    if inputs['spec_input'] == 'slots':
        metrics = manifest['architecture']['spec_schema'].get('metrics')
        if metrics is None:
            raise ValueError(f'{run_id} read its specs as a set and has no result registry: pool it with inputs.spec_input "set"')
        registries.append(metrics)
    return directory, manifest, config, summary, task, run_id, read_points


def _load_pool_transitions(directory, source, run_id, shown_as) -> tuple:
    """Verify pinned inputs and archived files, then reconstruct the requested replay-eligible candidates."""
    if source.get('inputs_sha256') not in (None, shown_as):
        raise ValueError(f'Network inputs changed after selection: {run_id} would be shown to the network another way '
                         'than the request pinned (its PDK was loaded again, or its task\'s spec descriptions or test '
                         'variables changed)')
    loader = TrajectoryLoader(directory)
    problems = loader.reader.verify()
    if problems:
        raise ValueError(f'Archive checksum failure: {problems}')
    wanted = selected_candidates(source, run_id)
    selection = {} if wanted is None else dict(candidate_ids=wanted)        # without one: read as before
    raw = loader.transition_rows(**selection)
    eligible = [row for row in raw if row['replay_eligible_archive']]
    transitions = loader.transitions(**selection)
    if not transitions:
        raise ValueError(f'No replay-eligible transitions: {run_id}')
    if wanted is not None and wanted - {t.candidate_id for t in transitions}:
        raise ValueError(f'{run_id}: {len(wanted - {t.candidate_id for t in transitions})} of the selected candidate_ids '
                         'are not replay-eligible transitions of this run')
    return loader, raw, eligible, transitions, wanted


def _validate_pool_transition(row, transition, original_settings, candidates, run_id, manifest, origin, migrated_settings, settings, counts) -> tuple:
    """Validate and optionally migrate one archived transition before it enters the pool."""
    original_settings[identity(asdict(transition.reward_settings))] = asdict(transition.reward_settings)
    if transition.candidate_id in candidates:
        raise ValueError(f'Duplicate archived candidate: {transition.candidate_id}')
    candidates.add(transition.candidate_id)
    if row['run_id'] != run_id or row['task_id'] != manifest['task_id']:
        raise ValueError('Transition provenance differs from source manifest')
    first, last = transition.observation, transition.next_observation
    if first.origin != origin or last.origin != origin:
        raise ValueError('Mixed observation origins in pool')
    if (first.condition_policy != 'off' or len(first.planned_conditions) > 1 or
            any(c is not None and not c.nominal_only for c in first.planned_conditions)):
        raise ValueError('Phase 0 currently supports nominal-only archives')
    # Stronger than Transition.validate's numerical tolerance: the relabelling gate.
    if last.evaluation.reward != transition.reward:
        raise ValueError('Unchanged-goal re-scoring does not exactly reproduce the archived reward')
    if migrated_settings is not None:
        transition = migrated(transition, migrated_settings)
        first, last = transition.observation, transition.next_observation
        counts['reward_migrated'] += 1
    if settings is None:
        settings = transition.reward_settings
    if transition.reward_settings != settings:
        raise ValueError('Mixed reward settings need an explicit migration; cannot pool as recorded')
    episode = (run_id, row['worker_id'], row['episode_id'])
    if not row['episode_id']:
        raise ValueError('Episode identity required for leakage-free holdout')
    return transition, settings, first, last, episode


def _append_relabelled_transitions(keep, transition, first, last, episode, groups, task, relabel, target_sets, stated, counts, targets_only, balance) -> None:
    """Store the selected transition and its requested relabelled variants within the episode."""
    if not targets_only:
        groups[task][episode].append((keep(transition), False))
    if task in relabel:
        derived = _relabeled(transition, first, last, relabel[task], task)
        groups[task][episode].append((keep(derived), True))
        counts['relabeled'] += 1
    for number, changes in enumerate(target_sets.get(task, ()), 1):       # one more copy per target set (record 7.312)
        key = f'target_set:{number}' if balance == 'target_set' else task
        groups[key][episode].append((keep(_retargeted(transition, first, last, changes, task, stated)), ('set', number)))
        counts['relabeled'] += 1


def _record_pool_source(
    directory, source, run_id, task, read_points, shown_as, summary, transitions, raw, counts, original_settings,
    migrated_settings, sources, wanted) -> None:
    """Recheck the source archive identity and append its loaded-transition audit record."""
    # Detect source mutation during reconstruction, too.
    if archive_identity(directory) != source['archive_sha256']:
        raise ValueError(f'Archive changed while loading: {directory}')
    sources.append(dict(run_dir=str(directory), run_id=run_id, task=task,
                        archive_sha256=source['archive_sha256'], **({'operating_points': True} if read_points else {}),
                        **({} if shown_as is None else {'inputs_sha256': shown_as}),
                        evaluations=summary['totals']['candidate_evaluations_charged'],
                        eligible=len(transitions), excluded=len(raw) - len(transitions),
                        **({} if wanted is None else {'selected': len(wanted)}),
                        relabeled=counts['relabeled'],
                        **({'reward_migrated': counts['reward_migrated'],
                            'original_reward_settings': list(original_settings.values())}
                           if migrated_settings is not None else {})))


def _split_and_audit_pool(
    request, origin, seed, fraction, inputs, groups, registries, sources, settings, relabel, target_sets,
    migrated_settings, storage, progress, seen_tasks, targets_only, balance) -> tuple:
    """Split whole episodes and describe the frozen source pool, input schemas, and optional reward migration."""
    if (set(relabel) | set(target_sets)) - seen_tasks:
        raise ValueError('Relabel task absent from pool')
    # lazy: program schemas are needed here only when reconstructing an archive pool.
    from .spec_programs import spec_program_schema
    schema = (spec_program_schema() if inputs['spec_input'] == 'structured' else
              spec_descriptors.spec_set_schema() if inputs['spec_input'] == 'set' else _pool_registry(registries, request))
    features = pool_feature_schema(inputs)
    training, validation, split = _split_episodes(groups, schema, seed, fraction, storage=storage, progress=progress)
    audit = dict(format='gator-offline-pool-v1', origin=origin, seed=seed, holdout_fraction=fraction,
                 request_sha256=identity(request), sources=sources, spec_schema=asdict(schema),
                 feature_schema=asdict(features), inputs=network_inputs.as_recorded(inputs), reward_settings=asdict(settings),
                 source_evaluations=sum(s['evaluations'] for s in sources), new_simulator_launches=0,
                 eligible=sum(s['eligible'] for s in sources), excluded=sum(s['excluded'] for s in sources),
                 relabeled=sum(s['relabeled'] for s in sources),
                 per_task={t: dict(training=len(training[t]), validation=len(validation[t])) for t in training},
                 split=split, split_sha256=identity(split), unchanged_reward_gate='exact_match',
                 diagnostic_scope='within-source episode holdout; not an unseen-circuit transfer result')
    if target_sets:
        audit['relabel_target_sets'] = {task: len(sets) for task, sets in sorted(target_sets.items())}
    if targets_only or balance != 'task':
        audit.update(relabel_targets_only=targets_only, balance=balance)
    if migrated_settings is not None:
        audit['reward_migration'] = dict(settings=asdict(migrated_settings),
                                       count=sum(s['reward_migrated'] for s in sources),
                                       source_archives_unchanged=True)
    return training, validation, schema, features, audit


def _shown(transition, view):
    """Validate physical transitions before viewing; relative sizes cannot be validated as physical actions."""
    values = {f.name: getattr(transition, f.name) for f in fields(transition)}
    values.update(observation=view.view(transition.observation), next_observation=view.view(transition.next_observation))
    return _shown_type()(**values)


def selected_candidates(source, run_id) -> set | None:
    """A source's `candidate_ids` (the archive comparison: exactly the transitions of a frozen bundle), as a set; None
    when the source pools every replay-eligible transition of its run, as before."""
    if 'candidate_ids' not in source:
        return None
    wanted = source['candidate_ids']
    if not isinstance(wanted, list) or not wanted or not all(isinstance(c, str) and c for c in wanted):
        raise ValueError(f'candidate_ids of {run_id} must be a nonempty list of candidate ids')
    if len(set(wanted)) != len(wanted):
        raise ValueError(f'candidate_ids of {run_id} names a candidate twice')
    return set(wanted)


def pool_options(request, target_sets, relabel, fraction) -> tuple:
    """(relabel_targets_only, balance) of a request; the defaults pool as before.
    relabel_targets_only: only the target-set copies are pooled, not the transition under its recorded targets - a pool
    of exactly the goal views it names (the archive comparison: its four portfolio views).
    balance: 'task' (the default) cycles over the source tasks; 'target_set' over the target sets, uniformly across the
    sources within each - the views balanced whatever source task a transition came from. It groups each transition's
    copies apart, so it needs relabel_targets_only, the same number of target sets for every task and no holdout (a
    holdout per group would put one episode in training under one view and in validation under another)."""
    targets_only, balance = bool(request.get('relabel_targets_only', False)), request.get('balance', 'task')
    if balance not in ('task', 'target_set'):
        raise ValueError('balance is "task" or "target_set"')
    if targets_only and (not target_sets or relabel):
        raise ValueError('relabel_targets_only needs relabel_targets and no relabel_upper')
    if balance == 'target_set':
        if not targets_only or fraction:
            raise ValueError('balance "target_set" needs relabel_targets_only and holdout_fraction 0')
        if len({len(sets) for sets in target_sets.values()}) != 1:
            raise ValueError('balance "target_set" needs the same number of target sets for every task (set k of each '
                             'task is one goal)')
    return targets_only, balance


class BalancedSampler:
    """Every task appears once in each shuffled cycle, even across batch boundaries."""
    def __init__(self, training, seed, *, track_candidates: bool=False) -> None:
        self.training, self.rng, self.pending = training, random.Random(seed), []
        self.counts = Counter()
        self.candidate_counts = Counter()
        self.track_candidates = track_candidates

    def sample(self, size) -> list:
        """Sample transitions while cycling through shuffled tasks to balance their contributions."""
        result = []
        for _ in range(size):
            if not self.pending:
                self.pending = sorted(self.training)
                self.rng.shuffle(self.pending)
            task = self.pending.pop()
            transition = self.rng.choice(self.training[task])
            result.append(transition)
            self.counts[task] += 1
            if self.track_candidates:
                self.candidate_counts[transition.candidate_id] += 1
        return result


def migrated(transition, settings):
    """An archived transition re-scored under the reward settings `settings` (`migrate_reward_settings`): both observations
    and the transition carry them, and the reward is the next observation's under them; the recorded measurements stay as
    they are. The pool and the rehearsal snapshot drawn from it (`rehearsal.build_snapshot`) both use it (record 7.352)."""
    first, last = (replace(o, reward_settings=settings) for o in (transition.observation, transition.next_observation))
    moved = replace(transition, observation=first, next_observation=last, reward_settings=settings, reward=last.evaluation.reward)
    moved.validate()
    return moved


def _relabeled(transition, first, last, changes, task):
    """A copy of an archived transition with the upper limits of some specs changed (`changes`: metric -> new upper),
    re-scored and validated."""
    known = {s.metric_id for s in first.specs}
    if set(changes) - known:
        raise ValueError(f'Relabel metric absent in {task}')
    specs = tuple(replace(s, upper=changes[s.metric_id]) if s.metric_id in changes else s
                  for s in first.specs)
    if any(s.comparator != 'max' for s in first.specs if s.metric_id in changes):
        raise ValueError('Upper-limit relabelling requires max-comparator rows')
    a, b = replace(first, specs=specs), replace(last, specs=specs)
    derived = replace(transition, observation=a, next_observation=b, reward=b.evaluation.reward)
    derived.validate()
    return derived


TARGET_KEYS = ('lower', 'upper', 'scale', 'objective')
OBJECTIVES = ('none', 'min', 'max')


def relabel_targets(request) -> dict:
    """request['relabel_targets'] (record 7.312; the transfer experiment's multi-target models): task -> a list of target
    sets, each `{metric: {"lower": x, "upper": y}}` with one or both limits. Every archived transition of the task is
    pooled once as recorded and once more under each target set, re-scored - so one network sees the same designs
    judged by several targets, each target among its inputs. {} when the request has none.

    A row may also state its "scale" (kept as stated, whatever its limits) and its "objective" ("none", "min" or "max":
    the direction a design that meets every limit is still improved in). With them a target set can describe a whole
    goal view of the archive comparison (plan-bo-mobo-rl-archive-comparison.md 4.2: the preference direction set, the
    scales held fixed), so that its copies score exactly as a run of that view does. Without them nothing changes."""
    target_sets = request.get('relabel_targets') or {}
    for task, sets in target_sets.items():
        if not isinstance(sets, list) or not sets or not all(isinstance(changes, dict) and changes for changes in sets):
            raise ValueError(f'relabel_targets of {task} must be a list of target sets, each naming at least one metric')
        for changes in sets:
            for metric, limits in changes.items():
                if not isinstance(limits, dict) or not limits or set(limits) - set(TARGET_KEYS):
                    raise ValueError(f'A target of {metric} in {task} names "lower", "upper" or both '
                                     '(and may add "scale" and "objective")')
                scale = limits.get('scale')
                if 'scale' in limits and (isinstance(scale, bool) or not isinstance(scale, (int, float))
                                          or not math.isfinite(scale) or scale <= 0):
                    raise ValueError(f'The scale of {metric} in {task} must be a finite positive number')
                if 'objective' in limits and limits['objective'] not in OBJECTIVES:
                    raise ValueError(f'The objective of {metric} in {task} is one of {", ".join(OBJECTIVES)}')
    return target_sets


def stated_scales(config) -> frozenset:
    """The specs of a recorded configuration whose Scale box was filled (`normalization_scale`): their scale is the
    user's, whatever the limits are."""
    rows = (config or {}).get('targets') or ()
    return frozenset(row['metric_id'] for row in rows if isinstance(row, dict) and row.get('normalization_scale'))


def retargeted_specs(specs, changes, task, stated=()) -> tuple:
    """`specs` with the limits of some rows moved (`changes`: metric -> {"lower": x, "upper": y}). A row keeps its kind:
    only a limit it has may be moved (an "at most" row its upper limit, an "at least" row its lower one, a range
    both), and a range stays a range. A row whose scale was the size of its limit - the rule of an empty Scale box,
    `compile.normalization_scale` - gets the size of its new limit, as the task saved with that limit would; a stated
    scale stays. `stated`: the rows whose scale the task states (`stated_scales` of the source's configuration). A
    stated scale that happens to equal the size of its limit is still stated: until record 7.322 it was taken for an
    empty box and moved with the limit, so the copy was scored on another scale than the task saved with that limit.
    A row that names its "scale" takes that scale; a row that names its "objective" takes that direction (`relabel_targets`)."""
    known = {s.metric_id: s for s in specs}
    if set(changes) - known.keys():
        raise ValueError(f'Relabel metric absent in {task}')
    size = lambda lower, upper: max([abs(v) for v in (lower, upper) if v is not None] or [0.0]) or 1.0
    result = []
    for spec in specs:
        limits = changes.get(spec.metric_id)
        if limits is None:
            result.append(spec)
            continue
        sides = [side for side in ('lower', 'upper') if side in limits]
        if any(getattr(spec, side) is None for side in sides):
            raise ValueError(f'{spec.metric_id} in {task} has no {"/".join(side for side in sides if getattr(spec, side) is None)} limit to move')
        lower, upper = limits.get('lower', spec.lower), limits.get('upper', spec.upper)
        if lower is not None and upper is not None and not lower < upper:
            raise ValueError(f'The new limits of {spec.metric_id} in {task} are not a range')
        if 'scale' in limits:
            scale = float(limits['scale'])
        else:
            follows = spec.metric_id not in stated and math.isclose(spec.scale, size(spec.lower, spec.upper), rel_tol=1e-12)
            scale = size(lower, upper) if follows else spec.scale
        result.append(replace(spec, lower=lower, upper=upper, scale=scale, objective=limits.get('objective', spec.objective)))
    return tuple(result)


def _retargeted(transition, first, last, changes, task, stated=()):
    """A copy of an archived transition under another target set (`retargeted_specs`), re-scored and validated."""
    specs = retargeted_specs(first.specs, changes, task, stated)
    a, b = replace(first, specs=specs), replace(last, specs=specs)
    derived = replace(transition, observation=a, next_observation=b, reward=b.evaluation.reward)
    derived.validate()
    return derived


def _pool_registry(registries, request):
    """The result registry the pool is read with: the one the sources share, or the request's explicit one when it covers
    every source metric with its recorded unit."""
    schema = shared_registry(registries, request.get('reference_overrides', {}))
    if request.get('spec_registry') is not None:
        from analog_optimizer.models.inputs import SpecSchema
        explicit = SpecSchema(version='spec-input-custom-v1', metrics=tuple(
            (entry['metric_id'], entry['unit'], float(entry['reference'])) for entry in request['spec_registry']))
        units = {name: unit for name, unit, _ in explicit.metrics}
        if any(units.get(name) != unit for name, unit, _ in schema.metrics):
            raise ValueError('Explicit registry must cover every source metric with its recorded unit')
        schema = explicit
    return schema


def _split_episodes(groups, schema, seed, fraction, *, storage=None, progress=None) -> tuple:
    """Whole run-scoped episodes split into training and validation per task, reproducibly from the seed; every
    observation checked against the registry on the way. Returns (training, validation, the split's rows)."""
    from analog_optimizer.models.inputs import SpecSetSchema, context_features, spec_set_features
    read = spec_set_features if isinstance(schema, SpecSetSchema) else context_features
    training, validation, split = {}, {}, []
    total = sum(len(rows) for episodes in groups.values() for rows in episodes.values())
    last_report = time.monotonic()
    if progress:
        progress(dict(event='pool_validation', completed_transitions=0, total_transitions=total))
    for task, episodes in sorted(groups.items()):
        keys = sorted(episodes)
        if fraction and len(keys) < 2:
            raise ValueError(f'At least two episodes required for {task}')
        random.Random(f'{seed}:{task}').shuffle(keys)
        n = 0 if not fraction else min(len(keys) - 1, max(1, math.ceil(len(keys) * fraction)))   # 0: no holdout
        training[task], validation[task] = [], []
        for i, key in enumerate(keys):
            subset = 'validation' if i < n else 'training'
            target = validation if i < n else training
            for transition, derived in episodes[key]:
                reference = transition
                if storage is not None:
                    transition = storage.get(reference)
                # Validate the shared registry on both endpoints without constructing an encoder.
                for observation in (transition.observation, transition.next_observation):
                    read(observation, schema)
                target[task].append(reference)
                row = dict(task=task, run_id=key[0], worker_id=key[1], episode_id=key[2],
                           candidate_id=transition.candidate_id, relabeled=bool(derived), subset=subset)
                if isinstance(derived, tuple):                     # which of the task's target sets (relabel_targets), from 1
                    row['target_set'] = derived[1]
                split.append(row)
                if progress:
                    now = time.monotonic()
                    if len(split) % 1000 == 0 or len(split) == total or now - last_report >= 30:
                        progress(dict(event='pool_validation', completed_transitions=len(split),
                                      total_transitions=total, task=task))
                        last_report = now
    if storage is not None:
        training = {task: DiskSequence(storage, refs) for task, refs in training.items()}
        validation = {task: DiskSequence(storage, refs) for task, refs in validation.items()}
    return training, validation, split

def evaluate(learner, pool, batch_size=32):
    """Held-out Q MSE versus a constant fitted on TRAINING rewards only."""
    import torch
    result = {}
    with torch.no_grad():
        for task, transitions in pool.validation.items():
            if not len(transitions):                  # no holdout (holdout_fraction 0): nothing to score
                continue
            training = pool.training[task]
            constant = (training.reward_mean if hasattr(training, 'reward_mean') else
                        sum(t.reward for t in training) / len(training))
            error, constant_error = [0., 0.], 0.
            for start in range(0, len(transitions), batch_size):
                chunk = transitions[start:start + batch_size]
                batch = learner.batch([t.observation for t in chunk])
                actions = torch.tensor([t.proposal[g] for t, ids in zip(chunk, batch.group_ids) for g in ids])
                reward = torch.tensor([t.reward for t in chunk], dtype=batch.context.dtype)
                for i, critic in enumerate(learner.critics):
                    error[i] += float(((critic(batch, actions) - reward) ** 2).sum())
                constant_error += sum((t.reward - constant) ** 2 for t in chunk)
            result[task] = dict(count=len(transitions), q1_mse=error[0] / len(transitions),
                                q2_mse=error[1] / len(transitions), constant_mse=constant_error / len(transitions))
    return result


def execute(request, output, *, audit_only: bool=False, progress=None):
    """Create a new offline artifact; refuse overwrite. Provisional weights are saved periodically."""
    import torch
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.training.sac import SACConfig, SACLearner

    output, updates, batch_size, interval, started = _begin_offline_artifact(request, output)
    learner = None
    pool = None
    loaded_sources = 0

    def status(state, **extra) -> None:
        record = dict(state=state, updates=0 if learner is None else learner.updates,
                      elapsed_seconds=time.monotonic() - started, new_simulator_launches=0,
                      updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
        write_json(output / 'status.json', record)
        if progress:
            progress(record)

    def pool_progress(event) -> None:
        nonlocal loaded_sources
        if event['event'] == 'pool_validation':
            status('loading', phase='validating_pool', **{k: v for k, v in event.items() if k != 'event'})
        elif event['event'] == 'source_loaded':
            loaded_sources += 1
            status('loading', phase='loading_sources', completed_sources=loaded_sources,
                   total_sources=len(request['runs']))
        if progress:
            progress(event)

    try:
        status('loading', phase='loading_sources', completed_sources=0, total_sources=len(request.get('runs', ())))
        pool = prepare_pool(request, progress=pool_progress, storage_dir=output)
        _save_pool_audit(status, pool, output)
        if audit_only:
            status('audited', source_evaluations=pool.audit['source_evaluations'], eligible=pool.audit['eligible'])
            return pool.audit
        experiment, model, sac = _offline_training_config(torch, request, pool, ModelConfig, SACConfig)
        learner = SACLearner(experiment=experiment, spec_schema=pool.schema, model_config=model,
                             config=sac, reward_settings=pool.reward_settings, feature_schema=pool.feature_schema)
        _train_offline(
            request, pool, ReplayBuffer, output, learner, status, experiment, updates, batch_size, interval)
        status('trained_unqualified', source_evaluations=pool.audit['source_evaluations'],
               pending_gates=['specialist critic comparison', 'actor proposal diagnostics',
                              'forgetting-curve review', 'workbench model publication', 'online rehearsal'])
        return pool.audit
    except BaseException as exc:
        status('interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', error=str(exc))
        raise
    finally:
        if pool is not None and pool.storage is not None:
            pool.storage.close()


def _begin_offline_artifact(request, output) -> tuple:
    """Validate offline run settings and create the new artifact directory with its frozen request."""
    output = Path(output).resolve()
    if request['origin'] == 'synthetic' and 'mock' not in output.parts:
        raise ValueError('Synthetic offline artifacts must be under a mock/ directory')
    updates, batch_size = request.get('updates', DEFAULT_UPDATES), request.get('batch_size', 8)
    interval = request.get('checkpoint_every', 1000)
    if any(type(x) is not int or x < 1 for x in (updates, batch_size, interval)):
        raise ValueError('updates, batch_size and checkpoint_every must be positive integers')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'request.json', request)
    started = time.monotonic()
    return output, updates, batch_size, interval, started


def _save_pool_audit(status, pool, output) -> None:
    """Report pool-save progress and persist the frozen pool audit and specification registry."""
    status('loading', phase='saving_pool', completed_transitions=len(pool.audit['split']),
           total_transitions=len(pool.audit['split']))
    write_json(output / 'pool.json', pool.audit)
    write_json(output / 'spec_registry.json', [dict(metric_id=n, unit=u, reference=r)       # a spec set has none
                                               for n, u, r in getattr(pool.schema, 'metrics', ())])


def _offline_training_config(torch, request, pool, ModelConfig, SACConfig) -> tuple:
    """Seed offline training and construct its experiment, model, and zero-discount learner configuration."""
    torch.set_num_threads(1)
    seed_everything(request.get('seed', DEFAULT_SEED))
    experiment = dict(origin=request['origin'], split='offline_training',
                      designs=pool.audit['sources'], pool_sha256=pool.audit['request_sha256'])
    model = ModelConfig(**request.get('model', dict(hidden_dim=48, heads=4, layers=4)))
    sac = SACConfig(**request.get('sac', dict(gamma=0., learning_rate=1e-3, initial_alpha=0.01, tau=0.005)))
    if sac.gamma != 0:
        raise ValueError('Phase-0 reward-regression diagnostics require gamma=0')
    return experiment, model, sac


def _train_offline(
    request, pool, ReplayBuffer, output, learner, status, experiment, updates, batch_size, interval) -> None:
    """Construct the offline sampler and checkpoint store, then run the requested learner updates with periodic saves."""
    sampler = BalancedSampler(pool.training, request.get('seed', DEFAULT_SEED), track_candidates=True)
    replay = ReplayBuffer(1, origin=request['origin'])
    # This path has no online collector or replay. Do not advertise RunEngine resume.
    store = CheckpointStore(output, run_id=pool.audit['request_sha256'][:24], task_id='offline:general',
                            task_definition_hash=pool.audit['request_sha256'], save_replay=False, keep_last=2)
    history = []
    candidate_runs = {r['candidate_id']: r['run_id'] for r in pool.audit['split'] if r['subset'] == 'training'}
    def checkpoint() -> None:
        status('training', phase='evaluating_validation', validation_transitions=sum(map(len, pool.validation.values())))
        scores = evaluate(learner, pool)
        history.append(dict(updates=learner.updates, scores=scores))
        write_json(output / 'validation.json', history)
        # The sampler's record of this save, written BEFORE the save point, with the update count it belongs to and the
        # sampler's own state (record 7.352): written after it, a stop between the two left the newest save point with
        # the record of the one before, and nothing in the record said so.
        per_run = Counter()
        for candidate, count in sampler.candidate_counts.items():
            per_run[candidate_runs[candidate]] += count
        write_json(output / 'sampling.json', dict(learner_updates=learner.updates, sampled_per_task=dict(sampler.counts),
                   sampled_per_run=dict(per_run), unique_training_candidates=len(sampler.candidate_counts),
                   available_training_candidates=len(candidate_runs),
                   candidate_counts=dict(sampler.candidate_counts),
                   candidate_note='a design and its relabelled copies share one candidate id',
                   sampler_state=dict(random=sampler.rng.getstate(), pending=list(sampler.pending))))
        store.save(learner, replay, ledger_state={}, data_cursor=dict(commit_seq=0),
                   counters=dict(evaluations_committed=0, learner_updates=learner.updates, replay_size=0),
                   collector_state=None, mode='scratch', effective_experiment=experiment)
        status('training', sampled_per_task=dict(sampler.counts), scores=scores,
               source_evaluations=pool.audit['source_evaluations'],
               parameter_counts={k: sum(p.numel() for p in v.parameters()) for k, v in
                                 [('actor', learner.actor), ('critics', learner.critics)]})
    checkpoint()
    for _ in range(updates):
        losses = learner.update(sampler.sample(batch_size))
        if learner.updates % interval == 0 or learner.updates == updates:
            checkpoint()
        elif learner.updates % 100 == 0:
            status('training', losses=losses, sampled_per_task=dict(sampler.counts))
