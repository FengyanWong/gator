"""Single-worker collector. Checkpoint/resume boundaries are completed episodes."""
from time import perf_counter

from .replay import Transition


def collect_episode(env, learner, replay, rng, *, warmup=8, batch_size=8):
    """One update per new eligible transition once a full batch is available.

    Both synthetic and real callers own their environment context/restoration.
    Failed calls remain in the environment journal and never create replay data.
    """
    if type(warmup) is not int or warmup < 0 or type(batch_size) is not int or batch_size < 1:
        raise ValueError('Warmup and batch size must be nonnegative/positive integers')
    if replay.origin != env.expected_origin or learner.experiment['origin'] != env.expected_origin:
        raise ValueError('Collector environment, learner and replay origins differ')
    observation, info = env.reset()
    if observation is None or info['terminated'] or info['truncated'] or not info['evaluation_valid']:
        raise RuntimeError(f'Reset did not produce an actionable state: {info["record_path"]}')
    rows = []
    for _ in range(env.max_steps):
        start = perf_counter()
        if replay.insertions < warmup:
            proposal = {group: rng.uniform(-1, 1) for group in env.mapper.group_ids}
            source = 'random_warmup'
        else:
            proposal = learner.act([observation])[0]
            source = 'sac_policy'
        inference_seconds = perf_counter() - start
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
        rows.append(dict(candidate_id=transition.candidate_id, record_path=transition.record_path,
                         proposal=proposal, action_source=source, reward=transition.reward,
                         success=step[4]['success'], duplicate_of=step[4]['duplicate_of'],
                         inference_seconds=inference_seconds, sampling_seconds=sampling_seconds,
                         update_seconds=update_seconds, update=update))
        observation = step[0]
        if step[2] or step[3]:
            break
    return rows
