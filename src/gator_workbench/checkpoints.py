"""Checkpoints with one consistency boundary, declared restoration capability and a
strictly separate notion of latest / best_policy / best_design.

Layout (``<run>/checkpoints/<checkpoint_id>/``)
  training_state.pt   full learner state written by the EXISTING ``SACLearner.save``: actor, twin
                      critics, targets, all three optimizers, temperature, RNG states, the replay
                      snapshot (embedded) and ``run_state`` = budget ledger + data cursors + counters.
                      One file => weights, replay and counters can never be from different moments.
  model_weights.pt    tensors + plain contract only; loadable with ``weights_only=True``. Used by
                      fine_tune / frozen, so transfer never unpickles arbitrary objects.
  replay_buffer/manifest.json  membership of the finite replay snapshot, verifiable against the
                      complete transitions archive without unpickling.
  metadata.json       capability (full_state | weights_only | partial), missing components,
                      counters, contract, checksums, recoverable boundary.
``latest.json`` is replaced atomically only after every file above is complete.

``training_state.pt`` is a trusted LOCAL artifact (it contains dataclasses). It is only ever
loaded from inside an allowed output root after its SHA-256 matched ``metadata.json``.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import re
import shutil
from uuid import uuid4

from . import CHECKPOINT_METADATA_VERSION
from .storage.atomic import PersistenceError, publish, read_json, sha256_file, temporary_path, write_json
from .storage.dataset import utcnow

FULL_COMPONENTS = ('graph_spec_encoders', 'actor', 'twin_critics', 'target_networks', 'actor_optimizer',
                   'critic_optimizer', 'temperature', 'temperature_optimizer', 'preprocessing_definition',
                   'random_states', 'counters', 'schema_and_action_semantics', 'budget_ledger', 'data_cursors',
                   'replay_snapshot')
RECOVERABLE_BOUNDARY = ('Quiescent scheduler boundary: no evaluation reserved or in flight, all results committed '
                        'and flushed. Collection restarts at fresh episodes. The internal state of a running '
                        'simulator process is never saved or restored, and asynchronous simulation order is not '
                        'guaranteed to reproduce bit-for-bit.')


class CheckpointIncompatible(RuntimeError):
    def __init__(self, report):
        self.report = report
        failed = [c for c in report['checks'] if c['status'] == 'incompatible']
        super().__init__('Checkpoint is not compatible: ' + '; '.join(f"{c['component']}: {c['detail']}" for c in failed))


def _digest(value) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@contextmanager
def _one_source_digest():
    """One save asked for the optimizer package's source digest three times (the contract inside `learner.save` and two
    contract summaries), each time reading all its .py files again - about 0.4 s apiece on the 9p-mounted repo. The code
    running in this process cannot change during a save, so the whole save uses ONE digest, taken here. Nothing under
    src/analog_optimizer changes; its function is back in place when the save ends."""
    import analog_optimizer.training.sac as sac
    original = sac.source_digest
    digest = original()
    sac.source_digest = lambda: digest
    try:
        yield
    finally:
        sac.source_digest = original


def contract_summary(learner) -> dict:
    """JSON-able description of everything that decides weight/semantic compatibility."""
    import json
    contract = learner.contract()
    # Canonical JSON form (tuples -> lists) so a live contract compares equal to one read back from
    # metadata.json. Without this every resume would be reported as a schema mismatch.
    return json.loads(json.dumps(_contract_fields(contract), allow_nan=False))


def _contract_fields(contract) -> dict:
    return dict(checkpoint_version=contract['checkpoint_version'], graph_schema=contract['graph_schema'],
                reward_version=contract.get('reward_version'), reward_settings=contract.get('reward_settings'),
                clearance_rule=contract.get('clearance_rule'), failure_policy=contract.get('failure_policy'),
                condition_policy=contract.get('condition_policy'), planned_conditions=contract.get('planned_conditions'),
                feature_schema=contract['feature_schema'], spec_schema=contract['spec_schema'],
                normalizer=contract['normalizer'], action_version=contract['action_version'],
                critic_action=contract['critic_action'], budget_semantics=contract['budget'],
                model_config=contract['model_config'], sac_config=contract['config'],
                origin=contract['experiment']['origin'], code_sha256=contract['code_sha256'],
                torch_version=contract['torch_version'], pyg_version=contract['pyg_version'],
                experiment_sha256=_digest(contract['experiment']))


def weight_digest(learner) -> str:
    from analog_optimizer.evaluation.benchmark import weight_digest as digest
    return digest(learner)


class CheckpointStore:
    def __init__(self, run_dir, *, run_id, task_id, task_definition_hash, save_replay=True, keep_last=None):
        self.root = Path(run_dir) / 'checkpoints'
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_id, self.task_id, self.task_hash = run_id, task_id, task_definition_hash
        self.save_replay, self.keep_last = save_replay, keep_last
        self.last_saved_at = None

    # ------------------------------------------------------------------ save
    def save(self, learner, replay, *, ledger_state, data_cursor, counters, collector_state, mode,
             kind='periodic', effective_experiment, frozen=False):
        """Write a complete checkpoint, then (and only then) move the ``latest`` pointer."""
        import torch
        from analog_optimizer.training.replay import ReplayBuffer
        checkpoint_id = f"ckpt-{counters['evaluations_committed']:08d}-{uuid4().hex[:8]}"
        directory = self.root / checkpoint_id
        staging = self.root / f'.staging-{checkpoint_id}'
        if staging.exists():
            shutil.rmtree(staging)
        (staging / 'replay_buffer').mkdir(parents=True)
        missing, not_applicable = [], []
        saved_replay = replay
        if frozen:
            # Nothing is learned in frozen mode, so there is no replay to restore: not a deficiency.
            not_applicable += ['replay_snapshot (frozen mode trains nothing and keeps no replay)',
                               'optimizer progress (no optimizer step is ever taken)']
            saved_replay = ReplayBuffer(1, origin=learner.experiment['origin'])
        elif not self.save_replay:
            missing += ['replay_snapshot (disabled in output settings)']
            saved_replay = ReplayBuffer(replay.capacity, origin=replay.origin)
        run_state = dict(version='workbench-run-state-v1', run_id=self.run_id, task_id=self.task_id,
                         task_definition_hash=self.task_hash, mode=mode, ledger=ledger_state,
                         data_cursor=data_cursor, counters=counters, collector=collector_state,
                         boundary=RECOVERABLE_BOUNDARY)
        try:
            with _one_source_digest():
                learner.save(staging / 'training_state.pt', saved_replay, run_state=run_state)
                contract = contract_summary(learner)
            weights = dict(format='gator-workbench-weights-v1', contract=contract,
                           actor=learner.actor.state_dict(), critics=learner.critics.state_dict(),
                           targets=learner.targets.state_dict(), log_alpha=learner.log_alpha.detach().clone(),
                           updates=int(learner.updates))
            temporary = temporary_path(staging / 'model_weights.pt')
            torch.save(weights, temporary)
            publish(temporary, staging / 'model_weights.pt')
            members = [] if saved_replay is not replay else [t.candidate_id for t in replay._items]
            manifest = dict(format='embedded in training_state.pt (replay embedded-v1)',
                            included=saved_replay is replay, capacity=replay.capacity if replay is not None else None,
                            size=len(members), insertions=getattr(replay, 'insertions', 0),
                            position=getattr(replay, '_position', 0),
                            evicted=max(0, getattr(replay, 'insertions', 0) - len(members)),
                            member_candidate_ids=members,
                            note='A finite circular buffer. Once insertions exceed capacity it no longer holds the '
                                 'complete history; the complete archive is data/transitions.')
            write_json(staging / 'replay_buffer' / 'manifest.json', manifest)
            capability = 'full_state' if not missing else 'weights_only'
            files = {}
            for path in sorted(p for p in staging.rglob('*') if p.is_file()):
                files[str(path.relative_to(staging))] = dict(bytes=path.stat().st_size, sha256=sha256_file(path))
            metadata = dict(
                metadata_version=CHECKPOINT_METADATA_VERSION, checkpoint_id=checkpoint_id, kind=kind,
                run_id=self.run_id, task_id=self.task_id, task_definition_hash=self.task_hash, mode=mode,
                created_utc=utcnow().isoformat(), restoration_capability=capability,
                restorable_components=[c for c in FULL_COMPONENTS
                                       if c != 'replay_snapshot' or not (missing or not_applicable)],
                missing_components=missing, not_applicable_components=not_applicable,
                recoverable_boundary=RECOVERABLE_BOUNDARY,
                counters=counters, ledger=ledger_state, data_cursor=data_cursor,
                replay=dict(size=manifest['size'], insertions=manifest['insertions'], capacity=manifest['capacity'],
                            evicted=manifest['evicted']),
                contract=contract, experiment=effective_experiment,
                weight_sha256=weight_digest(learner), files=files,
                trust='training_state.pt holds Python dataclasses: load it only from a trusted local output root. '
                      'model_weights.pt holds tensors only and is loaded with weights_only=True.',
                concepts=dict(latest='most recently SAFELY saved state (this pointer)',
                              best_policy='selected only by an explicit validation-set rule; see best_policy.json',
                              best_design='a circuit parameter set + measurements; see best_design/, not a model'))
            write_json(staging / 'metadata.json', metadata)
            staging.replace(directory)
        except BaseException as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, (OSError, PersistenceError)):
                raise PersistenceError(f'Checkpoint could not be saved: {exc}') from exc
            raise
        # Every file is complete and verified in place: only now move the pointer.
        write_json(self.root / 'latest.json', dict(
            checkpoint_id=checkpoint_id, path=f'checkpoints/{checkpoint_id}', created_utc=metadata['created_utc'],
            restoration_capability=capability, commit_seq=data_cursor['commit_seq'], kind=kind,
            meaning='most recently safely saved state; NOT automatically the best policy'))
        if not (self.root / 'best_policy.json').exists():
            write_json(self.root / 'best_policy.json', dict(
                selected=None, status='not_selected',
                reason='No validation-set policy evaluation has occurred in this run; a best policy is never invented.'))
        self.last_saved_at = utcnow()
        self._prune(checkpoint_id)
        return metadata

    def relabel(self, checkpoint_id, kind, *, was):
        """Give an existing save another kind when the state it holds is exactly the one a new save would write (a run
        that ends right after a periodic save). Only its role changes: files, counters and checksums stay as they are;
        `relabelled_from` records the kind it had. Returns the updated metadata."""
        path = self.root / checkpoint_id / 'metadata.json'
        metadata = dict(read_json(path), kind=kind, relabelled_from=was, relabelled_utc=utcnow().isoformat())
        write_json(path, metadata)
        latest = read_json(self.root / 'latest.json', default=None)
        if latest and latest.get('checkpoint_id') == checkpoint_id:
            write_json(self.root / 'latest.json', dict(latest, kind=kind))
        return metadata

    def _prune(self, keep_id):
        if self.keep_last is None:
            return []
        periodic = []
        # The selected best policy is a model somebody chose on purpose: pruning never removes it.
        best = (read_json(self.root / 'best_policy.json', default=None) or {}).get('selected')
        for directory in self.root.glob('ckpt-*'):
            meta = read_json(directory / 'metadata.json', default={})
            if meta.get('kind') == 'periodic' and directory.name not in (keep_id, best):
                periodic.append((meta.get('created_utc') or '', directory.name, directory))
        # Oldest first BY SAVE TIME. A name is the evaluation count plus a random suffix, so names alone put the saves made
        # at one count - every save of an offline pretraining - in random order, and pruning kept random ones (review of
        # 2026-10-07).
        periodic.sort()
        removed = []
        for _, _, directory in periodic[:max(0, len(periodic) - (self.keep_last - 1))]:
            shutil.rmtree(directory)
            removed.append(directory.name)
        return removed

    def select_best_policy(self, checkpoint_id, *, validation_rule, score, selection_cost_evaluations):
        """Only an explicit validation-set rule may select a best policy; its cost is recorded."""
        import math
        if not validation_rule or validation_rule.get('direction') not in ('min', 'max'):
            raise ValueError('An explicit validation rule with a min/max direction is required')
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError('A finite validation score is required')
        current = read_json(self.root / 'best_policy.json', default={})
        if current.get('selected') and current['validation_rule'] != validation_rule:
            raise ValueError('The validation selection rule changed during the run')
        previous = current.get('score') if current.get('selected') else None
        better = previous is None or (score < previous if validation_rule['direction'] == 'min' else score > previous)
        cost = (current.get('selection_cost_evaluations') or 0) + selection_cost_evaluations
        if better:
            write_json(self.root / 'best_policy.json', dict(
                selected=checkpoint_id, status='selected', path=f'checkpoints/{checkpoint_id}', score=score,
                validation_rule=validation_rule, selection_cost_evaluations=cost, selected_utc=utcnow().isoformat()))
        else:
            write_json(self.root / 'best_policy.json', dict(current, selection_cost_evaluations=cost))
        return better


# ---------------------------------------------------------------------- discovery / loading
def resolve_checkpoint(run_dir, checkpoint_id='latest') -> Path:
    root = Path(run_dir) / 'checkpoints'
    if checkpoint_id in ('latest', 'best_policy'):
        pointer = read_json(root / f'{checkpoint_id}.json', default={})
        target = pointer.get('checkpoint_id') if checkpoint_id == 'latest' else pointer.get('selected')
        if not target:
            raise FileNotFoundError(f'{run_dir} has no {checkpoint_id} checkpoint'
                                    + (f": {pointer.get('reason')}" if pointer.get('reason') else ''))
        checkpoint_id = target
    directory = (root / checkpoint_id).resolve()
    if root.resolve() not in directory.parents or not (directory / 'metadata.json').is_file():
        raise FileNotFoundError(f'No checkpoint {checkpoint_id} in {run_dir}')
    return directory


def read_metadata(directory) -> dict:
    return read_json(Path(directory) / 'metadata.json')


@lru_cache(maxsize=128)
def _display_digest(path, identity):
    """Display-only checksum reuse. Actual model loading always hashes the files again."""
    return sha256_file(path)


def verify_files(directory, *, cached=False) -> list[str]:
    directory, problems = Path(directory), []
    for relative, info in read_metadata(directory)['files'].items():
        path = directory / relative
        if not path.is_file():
            problems.append(f'missing {relative}')
        else:
            if cached:
                st = path.stat()
                digest = _display_digest(str(path.resolve()), (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
            else:
                digest = sha256_file(path)
            if digest != info['sha256']:
                problems.append(f'checksum mismatch {relative}')
    return problems


def check_compatibility(metadata, *, mode, task_definition_hash, contract) -> dict:
    """Visible, per-component verdicts. Never silently degrades to scratch.

    Deliberately NOT criteria: the graph node count (other topologies are valid transfer
    targets) and the number of action dimensions (equal dimensions prove nothing).
    """
    saved, checks = metadata['contract'], []
    if metadata.get('restoration_capability') == 'search_state':      # an LLM-only run's save (method removed 2026-10-06)
        return dict(mode=mode, compatible=False, checks=[dict(component='policy weights', status='incompatible',
            detail='This save holds the search progress of an LLM-only run, a search method removed on 2026-10-06. '
                   'It has no RL model to load.')],
            checkpoint_id=metadata['checkpoint_id'], source_run_id=metadata['run_id'], restoration_capability='search_state')

    def add(component, ok, detail, *, fatal=True):
        checks.append(dict(component=component, detail=detail,
                           status='ok' if ok else 'incompatible' if fatal else 'warning'))
    strict = mode == 'resume'
    add('checkpoint version', saved.get('checkpoint_version') == contract.get('checkpoint_version') == 'graph-sac-v2',
        'Reward v2 requires graph-sac-v2; v1 input/checkpoint migration is not implemented.')
    for key in ('reward_version', 'reward_settings', 'clearance_rule', 'failure_policy', 'condition_policy', 'planned_conditions'):
        same = saved.get(key) == contract.get(key)
        add(key, same, 'identical' if same else 'Different reward/condition contract; fine-tune resets critics, targets and replay.',
            fatal=strict)
    from .pdk import schema_label
    same = saved['feature_schema'] == contract['feature_schema']
    add('graph feature schema (components the network knows)', same,
        'identical' if same else f"this model knows the {schema_label(saved['feature_schema'])} component list; this run "
        f"uses the {schema_label(contract['feature_schema'])} list. A model only loads with the list it was trained with.")
    for key, label in [('spec_schema', 'goal/spec input schema'),
                       ('model_config', 'network architecture'), ('action_version', 'action semantics'),
                       ('graph_schema', 'circuit graph schema'), ('normalizer', 'preprocessing/normalization'),
                       ('critic_action', 'critic action representation'), ('origin', 'real/synthetic origin')]:
        add(label, saved[key] == contract[key],
            'identical' if saved[key] == contract[key] else f'saved {saved[key]!r} != current {contract[key]!r}')
    add('optimizer source code digest', saved['code_sha256'] == contract['code_sha256'],
        'identical' if saved['code_sha256'] == contract['code_sha256'] else
        f"checkpoint was written by analog_optimizer source {saved['code_sha256'][:12]}..., current source is "
        f"{contract['code_sha256'][:12]}... (a file under src/analog_optimizer/ changed)."
        + (' SACLearner.load requires an exact match for a full resume.' if strict else
           ' Weight tensors are still loaded shape-strictly; recorded as provenance.'), fatal=strict)
    for key, label in [('torch_version', 'torch version'), ('pyg_version', 'torch-geometric version')]:
        add(label, saved[key] == contract[key],
            'identical' if saved[key] == contract[key] else f'saved {saved[key]} != current {contract[key]}',
            fatal=strict)
    add('SAC hyperparameters', saved['sac_config'] == contract['sac_config'],
        'identical' if saved['sac_config'] == contract['sac_config'] else
        'differ' + (' (a resumed run must keep its training configuration)' if strict else
                    ' (allowed: new optimizers are created for the target task)'), fatal=strict)
    same_task = metadata['task_definition_hash'] == task_definition_hash
    if strict:
        add('task definition (circuit, variables, targets, measurements)', same_task,
            'identical' if same_task else 'The task changed. This cannot be presented as a continuation of the same '
            'training run; use fine_tune, which creates a new run and records this one as its parent.')
        add('restoration capability', metadata['restoration_capability'] == 'full_state',
            metadata['restoration_capability'] + ('' if metadata['restoration_capability'] == 'full_state' else
                                                   f"; missing {metadata['missing_components']}"))
        add('learner experiment contract', saved['experiment_sha256'] == contract['experiment_sha256'],
            'identical' if saved['experiment_sha256'] == contract['experiment_sha256'] else 'differs')
    else:
        checks.append(dict(component='task definition', status='ok' if not same_task else 'warning',
                           detail='different task (expected for transfer)' if not same_task else
                           'same task as the source; consider resume if full state exists'))
    compatible = not any(c['status'] == 'incompatible' for c in checks)
    return dict(mode=mode, compatible=compatible, checks=checks, checkpoint_id=metadata['checkpoint_id'],
                source_run_id=metadata['run_id'], restoration_capability=metadata['restoration_capability'],
                suggestion=None if compatible or not strict else 'fine_tune')


def load_weights(directory) -> dict:
    """Tensor-only load (weights_only=True): no arbitrary-object deserialization for transfer."""
    import torch
    path = Path(directory) / 'model_weights.pt'
    payload = torch.load(path, map_location='cpu', weights_only=True)
    if payload.get('format') != 'gator-workbench-weights-v1':
        raise ValueError('Unsupported weights file')
    return payload


def describe(run_dir, checkpoint_id='latest') -> dict:
    """What the UI shows for a selected model: source task, save time, schema, counters, actual path,
    restorable components and (separately computed) compatibility."""
    directory = resolve_checkpoint(run_dir, checkpoint_id)
    meta = read_metadata(directory)
    return dict(checkpoint_id=meta['checkpoint_id'], path=str(directory), kind=meta['kind'],
                source_run_id=meta['run_id'], source_task_id=meta['task_id'], mode=meta['mode'],
                created_utc=meta['created_utc'], metadata_version=meta['metadata_version'],
                counters=meta['counters'], restoration_capability=meta['restoration_capability'],
                restorable_components=meta['restorable_components'], missing_components=meta['missing_components'],
                contract=meta['contract'], file_problems=verify_files(directory, cached=True))


# ---------------------------------------------------------------------- choosing a model
def list_checkpoints(run_dir) -> dict:
    """Every complete save point of one run, oldest first, for the model chooser.

    Reads the small ``metadata.json`` files only: nothing is hashed and no tensor is loaded
    (``describe`` does that for the ONE model that is finally selected). A directory without
    readable metadata (staging, damaged) is never offered."""
    root = Path(run_dir) / 'checkpoints'

    def optional(path):
        try:
            value = read_json(path, default=None)
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
    latest, best = optional(root / 'latest.json').get('checkpoint_id'), optional(root / 'best_policy.json')
    points = []
    for directory in root.glob('ckpt-*'):
        meta = optional(directory / 'metadata.json')
        if meta.get('checkpoint_id') != directory.name:
            continue
        counters, network = meta.get('counters') or {}, (meta.get('contract') or {}).get('model_config') or {}
        points.append(dict(
            checkpoint_id=directory.name, kind=meta.get('kind'), created_utc=meta.get('created_utc'),
            mode=meta.get('mode'), evaluations=counters.get('evaluations_committed'),
            learner_updates=counters.get('learner_updates'), replay_size=counters.get('replay_size'),
            restoration_capability=meta.get('restoration_capability'),
            missing_components=meta.get('missing_components') or [],
            network={key: network[key] for key in ('encoder_type', 'hidden_dim', 'heads', 'layers',
                                                   'structural_encoding', 'architecture_version') if key in network},
            is_latest=directory.name == latest, is_best_policy=directory.name == best.get('selected')))
    points.sort(key=lambda point: (point['created_utc'] or '', point['checkpoint_id']))
    return dict(run_dir=str(run_dir), latest=latest if any(p['is_latest'] for p in points) else None,
                best_policy=dict(selected=best.get('selected') if any(p['is_best_policy'] for p in points) else None,
                                 status=best.get('status'), reason=best.get('reason'), score=best.get('score')),
                checkpoints=points)


def saved_models(run_entries) -> list[dict]:
    """The model chooser's list: every listed run that holds at least one complete save point, most
    recently saved first. ``run_entries`` are the rows of ``runs.list_runs``. A run without a save
    point has no model to load, so it is left out instead of failing when it is selected."""
    models = []
    for entry in run_entries:
        listing = list_checkpoints(entry['run_dir'])
        # An LLM-only run's saves (a search method removed on 2026-10-06) hold no RL model.
        listing['checkpoints'] = [p for p in listing['checkpoints'] if p['restoration_capability'] != 'search_state']
        if not listing['checkpoints']:
            continue
        newest = next((p for p in listing['checkpoints'] if p['is_latest']), listing['checkpoints'][-1])
        manifest = getattr(entry, 'manifest', None)          # a list_runs row keeps the manifest it was built from
        if manifest is None:
            manifest = read_json(Path(entry['run_dir']) / 'run_manifest.json', default=None) or {}
        circuit = manifest.get('circuit') or {}
        models.append(dict(
            # The model's name: the run row carries it, unique under the output root (runs.list_runs, record 7.225); a row
            # built elsewhere falls back to the manifest's.
            entry, task_name=manifest.get('task_name'), circuit_task=circuit.get('task_key'),
            model_label=entry.get('model_label') or model_label_of(entry['run_dir'], manifest)['model_label'],
            circuit_class=circuit.get('circuit_class'), latest=listing['latest'], best_policy=listing['best_policy'],
            checkpoints=listing['checkpoints'], network=newest['network'], saved_utc=newest['created_utc'],
            trained_evaluations=newest['evaluations'], learner_updates=newest['learner_updates'],
            restoration_capability=newest['restoration_capability']))
    return sorted(models, key=lambda model: model['saved_utc'] or '', reverse=True)


# ---------------------------------------------------------------------------- the model's name (record 7.225)
# A run's model is named by the manifest's `model_label` (the label in use at the start, record 7.159). No two models
# under one output root carry the same name: at the start a name already given gets the first free number, "ota7t (2)",
# "ota7t (3)" (the user's request of 2026-10-06: "for saved rl models with same names add numbering to them by default");
# models from before are numbered the same way when they are listed, oldest first. A rename writes `model_label.json`
# in the run folder: the engine rewrites the manifest from memory while a run lives, and never that file.
MODEL_LABEL_FILE = 'model_label.json'
MODEL_LABEL_MAX = 80


class ModelNameTaken(ValueError):
    pass


def model_label_of(run_dir, manifest=None) -> dict:
    """``{'model_label': name or None, 'renamed': bool}``: the name a run's model was renamed to, else the one its
    manifest was given at the start; None for a run that saves no model (a baseline, LLM only)."""
    renamed = read_json(Path(run_dir) / MODEL_LABEL_FILE, default=None) or {}
    label = renamed.get('model_label') if isinstance(renamed, dict) else None
    if isinstance(label, str) and label.strip():
        return dict(model_label=label.strip(), renamed=True)
    if manifest is None:
        manifest = read_json(Path(run_dir) / 'run_manifest.json', default=None) or {}
    if 'model_label' not in manifest:
        # A run from before the label (record 7.159) was filed under its task name; it has a model only if it saved one.
        label = manifest.get('task_name') if (Path(run_dir) / 'checkpoints' / 'latest.json').is_file() else None
    else:
        label = manifest.get('model_label')
    return dict(model_label=label.strip() if isinstance(label, str) and label.strip() else None, renamed=False)


def numbered(label, n) -> str:
    return f'{label} ({n})'


def free_model_label(label, taken) -> str:
    """`label` itself when no model carries it, else the first free "label (n)" from 2 up - counted from the name
    without its own number, so a taken "ota (2)" becomes "ota (3)", never "ota (2) (2)"."""
    if label not in taken:
        return label
    own = re.fullmatch(r'(.+) \((\d+)\)', label)
    base, n = (own.group(1), 2) if own else (label, 2)
    while numbered(base, n) in taken:
        n += 1
    return numbered(base, n)


def unique_model_labels(rows) -> dict:
    """run_dir -> the name its model goes by, no two alike. Rows: dicts with run_dir, created_utc, model_label and
    renamed (as model_label_of gives them); a row without a model is left out. Renamed models keep their names (taken
    first); the others are taken oldest first, and a name already taken gets its first free number."""
    taken, names = set(), {}
    ordered = sorted(rows, key=lambda row: (row.get('created_utc') or '', row['run_dir']))
    for renamed_pass in (True, False):
        for row in ordered:
            label = row.get('model_label')
            if not label or bool(row.get('renamed')) != renamed_pass:
                continue
            name = free_model_label(label, taken)
            taken.add(name)
            names[row['run_dir']] = name
    return names


def rename_model(run_dir, label, *, taken) -> dict:
    """Gives the model of `run_dir` the name `label` (model_label.json). `taken`: the names of the OTHER models under
    the output root - a name among them is refused (ModelNameTaken), nothing is numbered on a rename: the user chose
    the name. ValueError for an empty or over-long name."""
    label = (label or '').strip()
    if not label:
        raise ValueError('A model needs a name.')
    if len(label) > MODEL_LABEL_MAX:
        raise ValueError(f'A model name has at most {MODEL_LABEL_MAX} characters.')
    if label in taken:
        raise ModelNameTaken(f'A model named "{label}" exists already under this output folder. Choose another name.')
    run_dir = Path(run_dir)
    before = read_json(run_dir / MODEL_LABEL_FILE, default=None) or {}
    previous = model_label_of(run_dir)['model_label']
    given = (read_json(run_dir / 'run_manifest.json', default=None) or {}).get('model_label')
    record = dict(model_label=label, previous=previous, given_at_start=given, renamed_utc=utcnow().isoformat(),
                  history=[*(before.get('history') or []), *([dict(model_label=previous, until_utc=utcnow().isoformat())] if previous else [])])
    write_json(run_dir / MODEL_LABEL_FILE, record)
    return record
