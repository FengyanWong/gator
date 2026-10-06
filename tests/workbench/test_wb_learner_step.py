"""Record 7.221: the learner-step speed-ups change nothing a run records.

The replay lends its stored transitions to the learner instead of deep-copying a sample (ReplayBuffer.update_learner),
the input cache is spared re-hashing those observations, and with a discount of exactly 0 the learner leaves out the
next states' batch, actor and target critics (SACLearner.zero_gamma_shortcut). A seeded MOCK run must record the same
proposals, executed sizes, rewards and learner losses as on the old path (copied samples, full calculation)."""
import pytest

from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACLearner
from helpers import execute, make_config, rows

pytestmark = pytest.mark.xdist_group('test_wb_learner_step')

EVALUATIONS = ('commit_seq', 'episode_step', 'phase', 'action_source', 'policy_version', 'reward', 'valid', 'status',
               'terminated', 'replay_eligible', 'normalized_constraint_violation')
UPDATES = ('cumulative_updates', 'evaluations_collected', 'actor_loss', 'critic_loss', 'alpha_loss', 'alpha',
           'mean_log_prob', 'target_mean', 'critic_grad_norm', 'actor_grad_norm')
PARAMETERS = ('variable_id', 'member_variable_id', 'instance_path', 'parameter_name', 'raw_policy_action',
              'decoded_value', 'executed_value', 'value_before', 'projected')


def recorded(layout):
    evaluations = rows(layout, 'evaluations')
    order = {e['evaluation_id']: e['commit_seq'] for e in evaluations}
    return dict(evaluations=sorted((tuple(e[c] for c in EVALUATIONS) for e in evaluations), key=repr),
                updates=sorted((tuple(u[c] for c in UPDATES) for u in rows(layout, 'learner_updates')), key=repr),
                parameters=sorted(((order[p['evaluation_id']],) + tuple(p[c] for c in PARAMETERS)
                                   for p in rows(layout, 'parameters')), key=repr))


def run(tmp_path, monkeypatch, name, gamma, *, old_path):
    shortcuts = []
    draw = SACLearner._draw_skipped_next_action_noise
    with monkeypatch.context() as patch:
        patch.setattr(SACLearner, '_draw_skipped_next_action_noise',
                      lambda self, states: shortcuts.append(len(states)) or draw(self, states))
        if old_path:
            patch.setattr(ReplayBuffer, 'update_learner', lambda self, learner, size: learner.update(self.sample(size)))
            patch.setattr(SACLearner, 'zero_gamma_shortcut', False)
        root = tmp_path / name
        config = make_config(root, run=dict(max_evaluations=20, seed=5),
                             advanced=dict(gamma=gamma, updates_per_transition=4))
        layout, state = execute(config, root)
    assert state == 'completed'
    return recorded(layout), shortcuts


@pytest.mark.parametrize('gamma', [0.0, .99])
def test_a_run_records_the_same_with_the_speedups_as_on_the_old_path(tmp_path, monkeypatch, gamma):
    new, shortcuts = run(tmp_path, monkeypatch, 'new', gamma, old_path=False)
    old, old_shortcuts = run(tmp_path, monkeypatch, 'old', gamma, old_path=True)
    assert len(new['updates']) > 10 and len(new['evaluations']) == 20
    assert new == old
    # The run's own discount decides: a run with gamma 0 takes the shortcut, any other never; nothing forces it.
    assert bool(shortcuts) == (gamma == 0) and not old_shortcuts
