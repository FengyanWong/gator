"""Bounded-memory storage for validated offline transitions, using the recording codec."""
from collections import OrderedDict
from dataclasses import dataclass
import functools
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zlib

from analog_optimizer.recording import codec
from analog_optimizer.training.replay import Transition


@functools.cache
def shown_type():
    """Already-validated physical transitions viewed in different input coordinates. Here, not in `pretrain` (which uses
    it to view a pool's designs), so that this storage does not import `pretrain`, which imports it (record 7.352)."""
    @dataclass(frozen=True)
    class ShownTransition(Transition):
        # An already-validated transition expressed in transformed network-input coordinates.
        def validate(self):
            """Skip physical-coordinate validation for an already-validated viewed transition."""
            return None
    return ShownTransition


@dataclass(frozen=True)
class TransitionRef:
    # A disk-row reference carrying the transition identity checked during retrieval.
    index: int
    candidate_id: str
    reward: float


class DiskTransitions:
    """A compressed SQLite transition store with checksum checks and a bounded decoded cache."""
    def __init__(self, path=None, *, cache_size=32):
        self.connection = None
        self.temporary = tempfile.TemporaryDirectory(prefix='gator-offline-pool-') if path is None else None
        path = Path(self.temporary.name) / 'transitions.sqlite' if path is None else path
        self.path = Path(path)
        if self.path.exists():
            raise FileExistsError(self.path)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute('CREATE TABLE transitions (id INTEGER PRIMARY KEY, payload BLOB, sha256 TEXT)')
        self.cache_size, self.cache = cache_size, OrderedDict()

    def append(self, transition):
        """Store a compressed transition with its checksum and return its identity reference."""
        payload = zlib.compress(json.dumps(dict(
            viewed=type(transition) is not Transition, transition=codec.tree(vars(transition))),
            allow_nan=False, separators=(',', ':')).encode(), level=1)
        cursor = self.connection.execute('INSERT INTO transitions(payload, sha256) VALUES (?, ?)',
                                         (payload, hashlib.sha256(payload).hexdigest()))
        return TransitionRef(cursor.lastrowid, transition.candidate_id, transition.reward)

    def get(self, reference):
        """Return a cached transition or decode a stored row after checking its checksum and identity."""
        if reference.index in self.cache:
            self.cache.move_to_end(reference.index)
            return self.cache[reference.index]
        payload, checksum = self.connection.execute('SELECT payload, sha256 FROM transitions WHERE id=?',
                                                    (reference.index,)).fetchone()
        if hashlib.sha256(payload).hexdigest() != checksum:
            raise ValueError('Offline transition storage checksum mismatch')
        data = json.loads(zlib.decompress(payload))
        values = codec.untree(data['transition'])
        if data['viewed']:
            transition = shown_type()(**values)
        else:
            transition = Transition(**values)
        if transition.candidate_id != reference.candidate_id or transition.reward != reference.reward:
            raise ValueError('Offline transition storage identity mismatch')
        if self.cache_size:
            self.cache[reference.index] = transition
            while len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
        return transition

    def commit(self):
        self.connection.commit()

    def close(self):
        """Close the store, clear its decoded cache and remove an owned temporary directory."""
        if self.connection is not None:
            self.cache.clear()
            self.connection.close()
            self.connection = None
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None

    def __del__(self):
        self.close()


class DiskSequence:
    """Sequence compatible with the existing task-balanced random sampler."""
    def __init__(self, store, references):
        self.store, self.references = store, references
        self.reward_mean = sum(r.reward for r in references) / len(references) if references else 0.

    def __len__(self):
        return len(self.references)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self.store.get(r) for r in self.references[index]]
        return self.store.get(self.references[index])
