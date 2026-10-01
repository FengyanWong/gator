"""Every 5th reset of a lane simulates the starting design; the others start from the lane's last valid reset without
reserving, charging or recording an evaluation (user decision of 2026-09-30: the unchanged design used to be simulated at
every reset). Scripted lanes; a MOCK run simulates every reset, so the test lifts that exclusion as a real run has it."""
from types import SimpleNamespace

import pytest

from analog_optimizer.parameters import ActionMapper
from analog_optimizer.search import FakeClient
from gator_workbench import runs, schema, tasks
from gator_workbench.compile import compile_task
from gator_workbench.engine import RunEngine
from gator_workbench.search import SearchSession
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


def search_run(tmp_path, method, budget=16):
    """An AI sizing method on the MOCK task with one-step episodes, the exclusion lifted as a real run has it."""
    config = make_config(tmp_path, run=dict(max_evaluations=budget))
    rescue = dict(rescue_stagnation_evaluations=1, rescue_max_rounds=1) if method == 'sac_llm_rescue' else {}
    config.run.search = schema.SearchSettings(method=method, provider='codex', max_llm_calls=8, warm_start_count=4,
                                              initial_sac_updates=3, candidates_per_call=2, **rescue)
    config.run.advanced.batch_size = 4
    config.run.advanced.warmup_transitions = 4
    config.run.advanced.episode_length = 1
    mapper = ActionMapper(compile_task(config, tasks.load_task(config.circuit).base_graph).graph)
    client = FakeClient([dict(analysis='Synthetic fixture', notes=[], candidates=[dict(
        values=mapper.legalize(dict.fromkeys(mapper.group_ids, z)).group_values, rationale='Synthetic fixture')
        for z in (start, start + .05)]) for start in (-.9, -.7, -.5, -.3, -.1, .1, .3, .5)])
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    engine = RunEngine(layout.run_dir, task=tasks.load_task(config.circuit), llm_client=client,
                       lock=runs.take_lock(layout.run_dir))
    engine._resets_are_reused = lambda: True
    assert engine.run() == 'completed', read_json(layout.status)
    reused = [e for e in read_jsonl(layout.logs / 'events.jsonl') if e.get('event') == 'episode_reset_reused']
    return rows(layout, 'evaluations'), reused, engine


@pytest.mark.parametrize('method', ['llm_warmstart', 'sac_llm_rescue', 'llm'])
def test_ai_sizing_methods_keep_their_schedule_when_resets_are_reused(tmp_path, method):
    evaluations, reused, engine = search_run(tmp_path, method)
    assert engine.ledger.charged == len(evaluations)                           # every charged evaluation is a row
    assert all(e.get('status') != 'refused' for e in reused)
    assert all(not s['busy'] for s in engine.lane_state.values())
    steps = [r for r in evaluations if r['phase'] not in RESETS]
    if method == 'llm':             # one long episode (it may end at its call ceiling): the baseline is its only reset
        assert not reused and len(evaluations) - len(steps) == 1
        return
    assert engine.ledger.charged == 16 and reused and len(steps) > 8           # more than one reset in two was free
    if method == 'llm_warmstart':
        assert [r['action_source'] for r in steps[:4]] == ['llm_proposal'] * 4
        assert engine.search.schedule.admitted == 4 and engine.search.schedule.trained == 3


def test_a_reused_reset_in_flight_is_not_a_pending_design():
    lanes = dict(a=dict(busy=dict(op='reset_reused')), b=dict(busy=dict(op='step')), c=dict(busy=None),
                 d=dict(busy=dict(op='reset')))
    assert SearchSession.pending_designs(SimpleNamespace(engine=SimpleNamespace(lane_state=lanes))) == 1


def test_the_warm_start_budget_note_counts_only_the_resets_a_run_pays_for():
    """The note "cannot collect all starting transitions plus resets" counted every reset as paid until 2026-10-01."""
    assert runs.warm_start_resets(8, 1, mock=True) == 8                       # MOCK: every reset is simulated
    assert runs.warm_start_resets(8, 1, mock=False) == 2                      # real: resets 1 and 6 of 8
    assert runs.warm_start_resets(10, 1, mock=False) == 2 and runs.warm_start_resets(11, 1, mock=False) == 3
    assert runs.warm_start_resets(8, 3, mock=False) == 1 and runs.warm_start_resets(0, 3, mock=False) == 0
