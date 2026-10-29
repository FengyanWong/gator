"""Pinned, bounded source replay drawn only from an offline training partition.

The target replay, launch ledger and optimizer are unchanged. Persistent data uses
the recording codec's whitelisted JSON types, never executable pickle.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
import gzip
import json
from pathlib import Path
import random

from analog_optimizer.models.inputs import context_features, observation_digest
from analog_optimizer.recording import codec
from analog_optimizer.training.replay import Transition

from .pretrain import BalancedSampler, archive_identity, identity, migrated, retargeted_specs, stated_scales
from .storage.atomic import publish, read_json, sha256_file as file_sha, temporary_path, write_json
from .trajectory import TrajectoryLoader


def build_snapshot(training_dir, output, *, capacity=2048, seed=0, progress=None):
    """Publish a bounded training-only replay snapshot after verifying its offline split and source archives."""
    directory, output = Path(training_dir), Path(output)
    request, audit = read_json(directory / 'request.json'), read_json(directory / 'pool.json')
    if identity(request) != audit['request_sha256'] or identity(audit['split']) != audit['split_sha256']:
        raise ValueError('Offline request or episode partition changed')
    if audit['origin'] == 'synthetic' and 'mock' not in output.parts:
        raise ValueError('Synthetic rehearsal must be under mock/')
    rows = defaultdict(list)
    for row in audit['split']:
        if row['subset'] == 'training':
            rows[row['task']].append(row)
    if capacity < len(rows):
        raise ValueError('Rehearsal capacity must include every source task')
    # A pool whose rewards were recomputed (`migrate_reward_settings`) is drawn as it was trained on: re-scored the same way,
    # before any relabelling (record 7.352). The manifest says the migrated settings, and so do its transitions now.
    migration = audit.get('reward_migration')
    if migration is not None:
        from analog_optimizer.measurements.specs import RewardSettings
        migration = RewardSettings(**migration['settings'])
    # ---- Allocate bounded samples across source tasks before reading selected transitions.
    rng, selected = random.Random(seed), []
    for i, task in enumerate(sorted(rows)):
        n = capacity // len(rows) + (i < capacity % len(rows))
        selected.extend(rng.sample(rows[task], min(n, len(rows[task]))))
    output.mkdir(parents=True, exist_ok=False)
    data = output / 'transitions.jsonl.gz'
    temporary = temporary_path(data)
    with gzip.open(temporary, 'wt', encoding='utf8') as stream:
        for source in audit['sources']:
            chosen = [r for r in selected if r['run_id'] == source['run_id']]
            if not chosen:
                continue
            path = Path(source['run_dir'])
            if archive_identity(path) != source['archive_sha256']:
                raise ValueError('Source archive changed before rehearsal snapshot')
            transitions = {t.candidate_id: t for t in TrajectoryLoader(path).transitions(
                candidate_ids={r['candidate_id'] for r in chosen})}
            stated = stated_scales(read_json(path / 'effective_config.json'))
            for row in chosen:
                transition = transitions[row['candidate_id']]
                if migration is not None:
                    transition = migrated(transition, migration)
                if row['relabeled']:
                    if row.get('target_set'):                      # one of the task's target sets (pretrain.relabel_targets)
                        specs = retargeted_specs(transition.observation.specs, request['relabel_targets'][row['task']][row['target_set'] - 1], row['task'], stated)
                    else:
                        changes = request['relabel_upper'][row['task']]
                        specs = tuple(replace(s, upper=changes[s.metric_id]) if s.metric_id in changes else s
                                      for s in transition.observation.specs)
                    a, b = (replace(o, specs=specs) for o in (transition.observation, transition.next_observation))
                    transition = replace(transition, observation=a, next_observation=b, reward=b.evaluation.reward)
                transition.validate()
                stream.write(json.dumps(dict(selection=row, transition=codec.tree(vars(transition))),
                                        allow_nan=False, separators=(',', ':')) + '\n')
            if archive_identity(path) != source['archive_sha256']:
                raise ValueError('Source archive changed during rehearsal snapshot')
            if progress:
                progress(dict(event='rehearsal_source', run_id=source['run_id'], count=len(chosen)))
    # ---- Publish after checking each selected source archive before and after its read.
    publish(temporary, data)
    manifest = dict(format='gator-rehearsal-v1', origin=audit['origin'], capacity=capacity, count=len(selected),
                    selection=selected, seed=seed, request_sha256=audit['request_sha256'],
                    split_sha256=audit['split_sha256'], spec_schema=audit['spec_schema'],
                    reward_settings=audit['reward_settings'], source_evaluations=audit['source_evaluations'],
                    data_file=data.name, data_sha256=file_sha(data), sources=audit['sources'])
    write_json(output / 'manifest.json', manifest)
    return manifest


class Rehearsal:
    """Mix a verified source replay pool into learner updates while retaining resumable sampling state."""
    def __init__(self, settings, learner, *, origin, seed, batch_size):
        self.learner, self.sha = learner, settings.pool_sha256
        path = Path(settings.pool_manifest)
        if file_sha(path) != self.sha:
            raise ValueError('Rehearsal manifest checksum mismatch')
        manifest = read_json(path)
        if manifest.get('format') != 'gator-rehearsal-v1' or manifest['origin'] != origin:
            raise ValueError('Rehearsal format or origin mismatch')
        if (identity(manifest['spec_schema']) != identity(asdict(learner.spec_schema)) or
                identity(manifest['reward_settings']) != identity(asdict(learner.reward_settings))):
            raise ValueError('Rehearsal schema or reward mismatch')
        data = (path.parent / manifest['data_file']).resolve()
        if data.parent != path.parent.resolve() or file_sha(data) != manifest['data_sha256']:
            raise ValueError('Rehearsal data path or checksum mismatch')
        # ---- Validate stored transitions against the pinned training-only selection.
        training, actual, self.digests = defaultdict(list), [], {}
        with gzip.open(data, 'rt', encoding='utf8') as stream:
            for line in stream:
                item = json.loads(line)
                row = item['selection']
                if row['subset'] != 'training':
                    raise ValueError('Held-out transitions cannot enter rehearsal')
                transition = Transition(**codec.untree(item['transition']))
                if transition.candidate_id != row['candidate_id'] or transition.observation.origin != origin:
                    raise ValueError('Rehearsal transition provenance mismatch')
                transition.validate()
                if transition.reward_settings != learner.reward_settings:
                    raise ValueError('Rehearsal transition reward mismatch')
                for observation in (transition.observation, transition.next_observation):
                    context_features(observation, learner.spec_schema)
                actual.append(row)
                training[row['task']].append(transition)
                self.digests[id(transition)] = (observation_digest(transition.observation),
                                                observation_digest(transition.next_observation))
        if (Counter(map(identity, actual)) != Counter(map(identity, manifest['selection'])) or
                len(actual) != manifest['count'] or not 0 < len(actual) <= manifest['capacity']):
            raise ValueError('Rehearsal selection or capacity mismatch')
        # ---- Partition each update batch between source and target samples.
        self.source_size = round(batch_size * settings.fraction)
        self.online_size = batch_size - self.source_size
        if min(self.source_size, self.online_size) < 1:
            raise ValueError('Rehearsal batch must contain both target and source transitions')
        self.sampler = BalancedSampler(dict(training), seed)

    def update(self, transitions, *, digests):
        """Append a balanced sample of source transitions and their digests to a learner update."""
        source = self.sampler.sample(self.source_size)
        return self.learner.update(list(transitions) + source,
                                   digests=list(digests) + [self.digests[id(t)] for t in source])

    def state_dict(self):
        """Capture the rehearsal pool identity and sampler state needed for continuation."""
        return dict(pool_sha256=self.sha, rng=self.sampler.rng.getstate(), pending=list(self.sampler.pending),
                    counts=dict(self.sampler.counts))

    def load_state_dict(self, state):
        """Restore sampler state only when the checkpoint names the same rehearsal pool."""
        if state['pool_sha256'] != self.sha:
            raise ValueError('Resume rehearsal pool differs from checkpoint')
        self.sampler.rng.setstate(state['rng'])
        self.sampler.pending = list(state['pending'])
        self.sampler.counts = Counter(state['counts'])
