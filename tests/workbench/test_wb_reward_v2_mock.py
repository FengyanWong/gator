"""F3 of the reward-v2 audit (record 7.97): a MOCK run uses the reward settings of its configuration - the same
ones the learner enforces on every replay batch - and keeps one counted job row per toy evaluation."""
import json
from pathlib import Path

from tests.workbench.helpers import execute, make_config, rows, summary


def test_a_mock_run_uses_the_configured_reward_settings(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=16, reward=dict(
        violation_shape='compressed', worst_spec_share=0.5, margin_weight=0.1)))
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    effective = json.loads(Path(layout.effective_config).read_text())
    assert effective['run']['reward'] == dict(violation_shape='compressed', worst_spec_share=0.5,
                                              objective_weight=0.0, margin_weight=0.1, nominal_gate_band=0.5, objective_shape='clipped')
    transitions = rows(layout, 'transitions', ['reward_version', 'replay_admitted'])
    assert transitions and all(t['reward_version'] == 'constraint_violation_v2' for t in transitions)
    # the learner refuses a replay whose settings differ from its own: its updates prove the environment used the same
    assert summary(layout)['totals']['gradient_updates'] >= 1
    jobs = rows(layout, 'simulator_jobs', ['launch_counted', 'invocation_confirmed', 'condition'])
    assert len(jobs) == 16 and all(j['launch_counted'] and j['condition'] == 'nominal' for j in jobs)
