"""A fixed Parameters row (optimized = false) is never sent to the simulator: its members keep the circuit's values, and no
candidate reports them. The engine's record of a candidate read them as missing, so every candidate of a task with one
fixed row was "incomplete" - never valid, never feasible - and the run never found its best design (review of
2026-10-03). MOCK backend only."""
from helpers import execute, make_config, rows, summary


def fix_one(raw):
    """Disable optimization for the first parameter outside a binding group."""
    next(p for p in raw['parameters'] if not p.get('binding_group')).update(optimized=False)


def test_a_task_with_a_fixed_row_still_finds_its_feasible_best_design(tmp_path):
    reference, _ = execute(make_config(tmp_path / 'all', threshold=0.5, run=dict(max_evaluations=12)), tmp_path / 'all')
    assert any(e['best_so_far_feasible'] for e in rows(reference, 'evaluations'))      # this threshold is reached at all
    layout, state = execute(make_config(tmp_path / 'fixed', threshold=0.5, run=dict(max_evaluations=12), mutate=fix_one),
                            tmp_path / 'fixed')
    assert state == 'completed', summary(layout)['error']
    evaluations = rows(layout, 'evaluations')
    assert any(e['all_hard_constraints_satisfied'] for e in evaluations)
    assert evaluations[-1]['best_so_far_feasible'] is True                              # the tracker saw them
    assert (summary(layout).get('best_design') or {}).get('feasible') is True
