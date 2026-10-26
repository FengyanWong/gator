"""`reset_reused`: an episode starts from the last valid reset's observation without simulating the (same) starting
design again - the workbench engine re-simulates it at every 5th reset only (user decision of 2026-09-30). Scripted
fixtures only."""
import json

import pytest

from analog_optimizer.backends.backend import SimulationStatus as Status
from analog_optimizer.envs.sizing import CircuitSizingEnv
from reward_v21_support import NOMINAL, reset, ScriptedRealBackend, specs

FAILED = (Status.BACKEND_ERROR, False, {'score': None, 'other': None}, {'score': False, 'other': False},
          {'score': 'fixture', 'other': 'fixture'})
ABSENT = {'record', 'receipt', 'eval_id', 'record_path', 'candidate_id', 'job_id'}


def env_for(graph, directory):
    """Build a short environment whose scripted backend reports nominal success."""
    backend = ScriptedRealBackend(graph, nominal_pass=True)
    return CircuitSizingEnv(backend, backend.graph, specs(), directory, max_steps=2, stop_on_success=False)


def step(env):
    """Authorize one launch and submit a zero action to exercise candidate rechecks."""
    env.authorize_launches(1)
    return env.step({key: 0. for key in env.mapper.group_ids})


def candidates(env):
    """Read candidate receipts from the environment directory for reuse and launch assertions."""
    return [json.loads(p.read_text()) for p in (env.directory / 'candidates').glob('*.json')]


def test_a_reused_reset_starts_the_episode_from_the_last_real_one_and_launches_nothing(opamp, tmp_path):
    with env_for(opamp, tmp_path / 'w') as env:
        real_obs, real = reset(env)
        step(env)
        launched, calls, records = len(env.backend.launched), env.simulation_calls, len(candidates(env))
        obs, info = env.reset_reused()
        assert len(env.backend.launched) == launched and env.simulation_calls == calls and len(candidates(env)) == records
        assert obs.metrics == real_obs.metrics and obs is not real_obs
        assert info['reset_reused'] and info['reused_candidate_id'] == real['candidate_id'] and not ABSENT & info.keys()
        assert info['evaluation_valid'] and not info['replay_eligible'] and not info['terminated'] and not info['truncated']
        assert env.episode == 2 and env.steps == 0
        step(env)                                                            # the episode goes on from there
        assert env.steps == 1 and sum(r['kind'] == 'step' for r in candidates(env)) == 2


def test_there_is_nothing_to_reuse_before_a_valid_reset(opamp, tmp_path):
    with env_for(opamp, tmp_path / 'w') as env:
        with pytest.raises(RuntimeError, match='No valid reset to reuse'):
            env.reset_reused()
        env.backend.outcomes[NOMINAL] = FAILED
        _, info = reset(env)
        assert not info['evaluation_valid']
        with pytest.raises(RuntimeError, match='No valid reset to reuse'):   # a failed reset is never reused
            env.reset_reused()
        env.backend.outcomes.pop(NOMINAL)
        _, valid = reset(env)
        assert env.reset_reused()[1]['reused_candidate_id'] == valid['candidate_id']
        assert env.backend.launched.count(NOMINAL) == 2
