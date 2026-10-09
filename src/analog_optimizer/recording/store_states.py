"""Observations stored once, as patches of their task's graph (content-addressed, deduplicated), and the
transitions between them.

One of the parts ExperimentStore (store.py) is made of since 2026-10-09 (plan-refactoring E5); its methods run on
the store's writer thread, inside the transaction of the operation that called them."""
from dataclasses import fields

from .codec import identity, pack, unpack, tree, untree, diff, patched


class StateRecords:
    def _state_definition(self, graph_id, task_id):
        return tree(self._asset(graph_id)), self._asset(self._asset(task_id)['spec_id'])

    def _state(self, observation, graph_id, task_id):
        if observation is None:
            return None
        template, specs = self._state_definition(graph_id, task_id)
        encoded = tree(observation.graph)
        patches = diff(template, encoded)
        if patched(template, patches) != encoded:
            raise ValueError('Graph reconstruction is not exact')
        values = {f.name: getattr(observation, f.name) for f in fields(observation)
                  if f.name not in ('graph', 'specs')}
        if tuple(observation.specs) != specs:
            raise ValueError('State spec differs from task')
        data = dict(graph_patches=patches, observation=values,
                    normalizer_version='fixed-references-signed-log1p-v1')
        key = identity((graph_id, task_id, data))
        if not self.db.execute('SELECT 1 FROM states WHERE id=?', (key,)).fetchone():
            self.db.execute('INSERT INTO states VALUES(?,?,?,?)', (key, graph_id, task_id, pack(data)))
        return key

    def _load_state(self, state_id):
        if state_id is None:
            return None
        from analog_optimizer.envs.sizing import Observation
        row = self.db.execute('SELECT * FROM states WHERE id=?', (state_id,)).fetchone()
        if row is None:
            raise KeyError(state_id)
        data = unpack(row['data'])
        graph = untree(patched(tree(self._asset(row['graph_id'])), data['graph_patches']))
        specs = self._asset(self._asset(row['task_id'])['spec_id'])
        return Observation(graph=graph, specs=specs, **data['observation'])

    def _transition(self, row, transition, known_states):
        eval_id = row['id']
        data = dict(transition)
        if data.get('replay_eligible') is True:
            from .session import transition_from_data
            # Derived by the writer from the exact submitted states, never trust
            # a caller-supplied fingerprint. _state verifies their reconstruction.
            data.pop('replay_fingerprint', None)
            data['replay_fingerprint'] = transition_from_data(data, validate=False).fingerprint()
        def state(value):
            return known_states[id(value)] if id(value) in known_states else self._state(value, row['graph_id'], row['task_id'])
        first = state(data.pop('observation', None))
        last = state(data.pop('next_observation', None))
        data.update(task_id=row['task_id'], graph_id=row['graph_id'], eval_id=eval_id)
        for flag in ('terminated', 'truncated'):
            if type(data.get(flag)) is not bool:
                raise ValueError('Transition needs separate boolean end flags')
        tid = data.pop('transition_id', eval_id)
        digest = identity((first, last, data))
        old = self.db.execute('SELECT hash FROM transitions WHERE id=?', (tid,)).fetchone()
        if old and old[0] != digest:
            raise ValueError('Conflicting transition ID')
        self.db.execute('INSERT OR IGNORE INTO transitions(id,eval_id,state_id,next_state_id,data,hash) '
                        'VALUES(?,?,?,?,?,?)', (tid, eval_id, first, last, pack(data), digest))
        return tid

    def _op_verify_transition(self, transition_id, fingerprint):
        row = self.db.execute('SELECT t.data,e.result_hash,e.state FROM transitions t '
                              'JOIN evaluations e ON e.id=t.eval_id WHERE t.id=?', (transition_id,)).fetchone()
        if row is None or row['result_hash'] is None or row['state'] != 'completed':
            raise ValueError('Replay requires a committed transition')
        data = unpack(row['data'])
        if data.get('replay_eligible') is not True:
            raise ValueError('Recorded transition is ineligible for training replay')
        expected = data.get('replay_fingerprint')
        if expected is None:
            # Databases written before fingerprint admission remain usable;
            # only those older rows require full readback, with no migration.
            from .session import transition_from_data
            expected = transition_from_data(self._op_read('transition', transition_id)).fingerprint()
        if expected != fingerprint:
            raise ValueError('Replay differs from durable transition')
        return True
