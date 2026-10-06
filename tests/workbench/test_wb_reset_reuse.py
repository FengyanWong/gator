"""Every 5th reset of a lane simulates the starting design; the others start from the lane's last valid reset without
reserving, charging or recording an evaluation (user decision of 2026-09-30: the unchanged design used to be simulated at
every reset). Scripted lanes; a MOCK run simulates every reset, so the test lifts that exclusion as a real run has it."""
from gator_workbench import runs, schema, tasks
from gator_workbench.engine import RunEngine
from gator_workbench.storage.atomic import read_json, read_jsonl
from helpers import ScriptedEnvFactory, make_config, roots_for, rows

RESETS = ('baseline', 'episode_reset')


def run(tmp_path, *, reuse, budget=10):
    config = make_config(tmp_path, run=dict(max_evaluations=budget, concurrency=1), advanced=dict(episode_length=1))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    config = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    engine = RunEngine(layout.run_dir, task=tasks.load_task(config.circuit), use_processes=False, lock=runs.take_lock(layout.run_dir))
    engine._lane_factory = ScriptedEnvFactory(engine.compiled.graph, engine.compiled.specs, str(layout.work), 1)
    if reuse:
        engine._resets_are_reused = lambda: True
    engine.run()
    phases = [r['phase'] for r in rows(layout, 'evaluations')]
    reused = [e for e in read_jsonl(layout.logs / 'events.jsonl') if e.get('event') == 'episode_reset_reused']
    return phases, reused, engine


def test_a_real_run_simulates_every_fifth_reset_and_spends_the_budget_on_steps(tmp_path):
    phases, reused, engine = run(tmp_path, reuse=True)
    assert engine.ledger.charged == 10 and len(phases) == 10                # the whole budget, every row a real evaluation
    assert phases.count('baseline') == 1 and phases.count('episode_reset') == 1   # resets 1 and 6 simulated
    assert sum(p not in RESETS for p in phases) == 8                         # 8 steps instead of 5
    assert len(reused) == 6 and all(e.get('status') != 'refused' and e['reused_candidate_id'] for e in reused)
    assert all(not s['busy'] for s in engine.lane_state.values())


def test_a_mock_run_still_simulates_every_reset(tmp_path):
    phases, reused, engine = run(tmp_path, reuse=False)
    assert not reused and engine.ledger.charged == 10
    assert phases.count('baseline') + phases.count('episode_reset') == 5 and sum(p not in RESETS for p in phases) == 5
