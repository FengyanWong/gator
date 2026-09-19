"""Atomic, verified checkpoints and bounded policy retention (one shared learner)."""
from copy import deepcopy
import hashlib
import io
import os
from pathlib import Path
from uuid import uuid4

from .space import fsync_directory


def atomic_torch_save(payload, path, *, preflight=None):
    import torch
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Measure exact serialized size before touching the previous checkpoint.
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    contents = buffer.getvalue()
    if preflight:
        preflight(len(contents))
    temporary = path.with_name('.' + path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        if hashlib.sha256(temporary.read_bytes()).digest() != hashlib.sha256(contents).digest():
            raise IOError('Checkpoint verification failed')
        restored = torch.load(temporary, map_location='cpu', weights_only=False)
        if restored.keys() != payload.keys():
            raise IOError('Checkpoint structure verification failed')
        temporary.replace(path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


class CheckpointManager:
    def __init__(self, store, run_id, root, *, interval=500, validation_rule=None):
        if type(interval) is not int or interval < 1:
            raise ValueError('Checkpoint interval must be positive')
        self.store, self.run_id = store, run_id
        self.root, self.interval = Path(root).resolve() / 'checkpoints', interval
        self.validation_rule = validation_rule
        self.last_step = 0
        self.best_score = None
        for row in store.call('read', 'checkpoints'):
            if row['run_id'] == run_id and row['status'] == 'retained':
                if row['kind'] == 'full':
                    self.last_step = max(self.last_step, row['step'])
                elif row['kind'] == 'best_policy':
                    from .codec import unpack
                    saved = unpack(row['data'])
                    if saved['validation_rule'] != validation_rule:
                        raise ValueError('Validation selection rule changed')
                    self.best_score = saved['score']

    def maybe_save(self, learner, replay, env_steps, *, run_state=None, force=False):
        if not force and env_steps - self.last_step < self.interval:
            return None
        if replay.store is None:
            raise ValueError('Managed checkpoints require durable replay IDs')
        state = deepcopy(run_state or {})
        state['env_steps'] = env_steps
        state.setdefault('collector_recovery', 'fresh episode required; exact learner/replay continuation only')
        path = self.root / (uuid4().hex + '.pt')
        database = learner.save(path, replay, run_state=state,
                                preflight=lambda size: self.store.call('preflight', extra=size))
        self.store.call('checkpoint', self.run_id, str(path), 'full', env_steps,
                        dict(database=database, run_state=state))
        self.last_step = env_steps
        return path

    def policy(self, learner, env_steps, *, validation=None):
        kind, metadata = 'final_policy', {}
        if validation is not None:
            import math
            if self.validation_rule is None or validation['rule'] != self.validation_rule:
                raise ValueError('A fixed, matching validation rule is required for best policy')
            if validation.get('complete') is not True or not math.isfinite(validation['score']):
                raise ValueError('Validation must be complete with a finite score')
            direction = self.validation_rule['direction']
            if direction not in ('min', 'max'):
                raise ValueError('Validation direction must be min/max')
            score = validation['score']
            if self.best_score is not None and not (score < self.best_score if direction == 'min' else score > self.best_score):
                return None
            kind = 'best_policy'
            metadata = dict(score=score, validation_rule=self.validation_rule, validation=validation)
        elif self.validation_rule is not None:
            raise ValueError('Configured best policy requires completed validation evidence')
        path = self.root / (uuid4().hex + '.pt')
        atomic_torch_save(dict(actor=learner.actor.state_dict(), contract=learner.contract(), **metadata), path,
                          preflight=lambda size: self.store.call('preflight', extra=size))
        self.store.call('checkpoint', self.run_id, str(path), kind, env_steps, metadata)
        if validation is not None:
            self.best_score = validation['score']
        return path
