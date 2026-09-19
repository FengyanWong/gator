"""Single-worker collector. Checkpoint/resume boundaries are completed episodes."""
from time import perf_counter

from .replay import Transition


def collect_episode(env, learner, replay, rng, *, warmup=8, batch_size=8,
                    checkpoints=None, update_recorder=None, run_state=None, history_limit=100):
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
    observation, info = env.reset()
    if observation is None or info['terminated'] or info['truncated'] or not info['evaluation_valid']:
        raise RuntimeError(f'Reset did not produce an actionable state: {info["record_path"]}')
    history = dict(rows=[], rows_count=0)
    rows = history['rows']
    for _ in range(env.max_steps):
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
        step = env.step(proposal)
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
