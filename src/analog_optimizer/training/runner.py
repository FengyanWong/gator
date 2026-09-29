"""Single-worker collector. Checkpoint/resume boundaries are completed episodes."""
from time import perf_counter

from .replay import Transition


class LaunchBudget:
    """Parent-owned full-candidate reservations for standalone collectors."""

    def __init__(self, maximum, *, consumed=0, journal=None):
        if maximum is not None and (type(maximum) is not int or maximum < 1):
            raise ValueError('Launch maximum must be a positive integer')
        if type(consumed) is not int or consumed < 0 or maximum is not None and consumed > maximum:
            raise ValueError('Invalid previously consumed launch count')
        self.maximum, self.consumed, self.journal = maximum, consumed, journal
        self.holds, self.uncertain, self.candidates = {}, 0, 0

    def snapshot(self):
        return dict(maximum=self.maximum, charged_calls=self.consumed, uncertain_calls=self.uncertain,
                    reservations=dict(self.holds), candidates=self.candidates)

    def _persist(self):
        if self.journal is not None:
            from analog_optimizer.envs.sizing import write_record
            write_record(self.journal, self.snapshot())

    def reserve(self, key, allowance):
        if key in self.holds or type(allowance) is not int or allowance < 1:
            raise ValueError('Invalid or duplicate candidate reservation')
        if self.uncertain:
            raise RuntimeError('Reconcile unresolved launches before further dispatch')
        if self.maximum is not None and self.consumed + sum(self.holds.values()) + allowance > self.maximum:
            return False
        self.holds[key] = allowance
        self.candidates += 1
        self._persist()
        return True

    def finish(self, key, calls, *, uncertain=0):
        allowance = self.holds[key]
        if type(calls) is not int or not 0 <= calls <= allowance or not 0 <= uncertain <= calls:
            raise ValueError('Receipt exceeds candidate launch allowance')
        del self.holds[key]
        self.consumed += calls
        self.uncertain += uncertain
        self._persist()


def collect_episode(env, learner, replay, rng, *, warmup=8, batch_size=8,
                    checkpoints=None, update_recorder=None, run_state=None, history_limit=100,
                    max_simulation_calls=None):
    """One update per new eligible transition once a full batch is available.

    Both synthetic and real callers own their environment context/restoration.
    Failed calls remain in the environment journal and never create replay data.
    """
    if type(warmup) is not int or warmup < 0 or type(batch_size) is not int or batch_size < 1:
        raise ValueError('Warmup and batch size must be nonnegative/positive integers')
    if replay.origin != env.expected_origin or learner.experiment['origin'] != env.expected_origin:
        raise ValueError('Collector environment, learner and replay origins differ')
    from copy import deepcopy
    from .workers import append_history
    base_state = deepcopy(run_state or {})
    calls_before = env.simulation_calls
    if env.condition_policy != 'off' and max_simulation_calls is None:
        raise ValueError('Robust collection requires a finite global launch ceiling')
    budget = LaunchBudget(max_simulation_calls, consumed=base_state.get('simulation_calls', 0),
                          journal=env.directory / 'collector-launch-budget.json')

    def evaluate(key, allowance, operation):
        if not budget.reserve(key, allowance):
            raise RuntimeError('Insufficient launch capacity for the complete candidate')
        before, unknown = env.simulation_calls, env.uncertain_calls
        env.authorize_launches(allowance)
        try:
            return operation()
        finally:
            budget.finish(key, env.simulation_calls - before, uncertain=env.uncertain_calls - unknown)

    observation, info = evaluate('reset', 1, env.reset)
    if observation is None or info['terminated'] or info['truncated'] or not info['evaluation_valid']:
        raise RuntimeError(f'Reset did not produce an actionable state: {info["record_path"]}')
    history = dict(rows=[], rows_count=0)
    rows = history['rows']
    for index in range(env.max_steps):
        allowance = len(env.planned_conditions)
        if budget.maximum is not None and budget.consumed + allowance > budget.maximum:
            break
        start = perf_counter()
        if replay.insertions < warmup:
            proposal = {group: rng.uniform(-1, 1) for group in env.mapper.group_ids}
            source = 'random_warmup'
        else:
            proposal = learner.act([observation])[0]
            source = 'sac_policy'
        inference_seconds = perf_counter() - start
        if env.recorder is not None:
            env.recorder.phase = 'random_exploration' if source == 'random_warmup' else 'training'
            env.recorder.policy_version = learner.updates
        start = perf_counter()
        step = evaluate(f'step-{index}', allowance, lambda: env.step(proposal))
        sampling_seconds = perf_counter() - start
        transition = Transition.from_step(observation, proposal, step)
        replay.add(transition)
        update, update_seconds = None, 0.0
        if len(replay) >= batch_size:
            start = perf_counter()
            update = learner.update(replay.sample(batch_size))
            update_seconds = perf_counter() - start
            if update_recorder is not None:
                update_recorder.add(update)
        if checkpoints is not None:
            saved = dict(base_state, collector_rng=rng.getstate(), episode=env.episode, step=env.steps,
                         boundary='completed_episode_step; restart collection at fresh episodes',
                         completed_episodes=base_state.get('completed_episodes', 0) + int(step[2] and not step[3]),
                         synthetic_calls=base_state.get('synthetic_calls', 0) + env.simulation_calls - calls_before,
                         simulation_calls=base_state.get('simulation_calls', 0) + env.simulation_calls - calls_before)
            checkpoints.maybe_save(learner, replay, replay.insertions, run_state=saved)
        append_history(history, 'rows', dict(candidate_id=transition.candidate_id, record_path=transition.record_path,
                         proposal=proposal, action_source=source, reward=transition.reward,
                         success=step[4]['success'], duplicate_of=step[4]['duplicate_of'],
                         inference_seconds=inference_seconds, sampling_seconds=sampling_seconds,
                         update_seconds=update_seconds, update=update),
                       history_limit if env.recorder is not None else None)
        observation = step[0]
        if step[2] or step[3]:
            break
    return rows
