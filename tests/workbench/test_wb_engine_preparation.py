"""A real (native) environment factory needs the optimizer's preparation service - the ONE owner of the Virtuoso
session - alive from before the first lane opens until after the last lane closed. The workbench engine never
entered it, so no real task could run from the workbench (found by the first authorized real baseline, 2026-09-21:
"'NoneType' object has no attribute 'baseline'", before any simulator launch). Scripted backend; no Virtuoso."""
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

from gator_workbench import runs, schema, tasks
from gator_workbench.engine import RunEngine
from gator_workbench.storage.atomic import read_json
from helpers import ScriptedEnvFactory, make_config, roots_for

EVENTS = []


@dataclass
class NativeLikeFactory(ScriptedEnvFactory):
    """Behaves like NativeEnvironmentFactory: unusable until `preparation_context` handed out the prepared copy."""
    prepared: bool = False
    restoration: dict = field(default_factory=lambda: dict(state='restored'))

    @contextmanager
    def preparation_context(self, limits, report):
        EVENTS.append(('enter', type(limits).__name__))
        report['preparation'] = dict(session_dir='/fixture/session')
        try:
            yield replace(self, prepared=True)
        finally:
            report['preparation_restoration'] = dict(self.restoration)
            EVENTS.append(('exit', None))

    def __call__(self, lane):
        if not self.prepared:
            raise AttributeError("'NoneType' object has no attribute 'baseline'")        # what the real factory did
        EVENTS.append(('lane_open', lane))
        return super().__call__(lane)


def run_with(tmp_path, factory_changes=None):
    EVENTS.clear()
    config = make_config(tmp_path, run=dict(max_evaluations=6, concurrency=2))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    config = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    engine = RunEngine(layout.run_dir, task=tasks.load_task(config.circuit), use_processes=False, lock=runs.take_lock(layout.run_dir))
    engine._lane_factory = NativeLikeFactory(engine.compiled.graph, engine.compiled.specs, str(layout.work),
                                             config.run.advanced.episode_length, **(factory_changes or {}))
    return layout, engine, engine.run()


def test_the_preparation_service_brackets_the_lanes(tmp_path):
    layout, engine, state = run_with(tmp_path)
    assert state == 'completed', read_json(layout.status).get('error')
    kinds = [kind for kind, _ in EVENTS]
    assert kinds[0] == 'enter' and kinds[-1] == 'exit' and kinds.count('enter') == kinds.count('exit') == 1
    assert kinds.count('lane_open') == 2 and EVENTS[0][1] == 'WorkerLimits'
    assert engine.preparation_report['preparation_restoration'] == dict(state='restored') and engine._preparation is None
    events = [row['event'] for row in map(__import__('json').loads, (layout.logs / 'events.jsonl').read_text().splitlines())]
    assert 'preparation_service_started' in events


def test_an_unrestored_schematic_is_reported_not_swallowed(tmp_path):
    layout, engine, state = run_with(tmp_path, dict(restoration=dict(state='recovery_required', error='fixture')))
    summary = read_json(layout.run_dir / 'run_summary.json')
    text = __import__('json').dumps([read_json(layout.status), summary])
    assert 'preparation service: restoration state recovery_required' in text


def test_a_factory_without_the_context_is_used_as_before(tmp_path):
    EVENTS.clear()
    config = make_config(tmp_path, run=dict(max_evaluations=4))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    config = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    engine = RunEngine(layout.run_dir, task=tasks.load_task(config.circuit), use_processes=False, lock=runs.take_lock(layout.run_dir))
    assert engine.run() == 'completed' and engine.preparation_report is None and EVENTS == []
