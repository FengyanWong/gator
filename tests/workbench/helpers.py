"""Shared helpers for workbench tests. Everything here is MOCK: the analytic toy backend plus a
scripted variant that injects failures and delays. No Virtuoso, Spectre, network or agent CLI."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import time
from uuid import uuid4

from analog_optimizer.backends.backend import SimulationResult, SimulationStatus
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend

from gator_workbench import runs, schema, tasks
from gator_workbench.engine import RunEngine
from gator_workbench.paths import OutputRoots
from gator_workbench.storage import DatasetReader, read_json

SMALL_NET = dict(encoder_type='graph_transformer', hidden_dim=16, heads=2, layers=1)


class ScriptedBackend(SyntheticSizingBackend):
    """script: {simulation call number (1-based): 'timeout' | 'nan' | 'exception' | 'invalid_design'}."""
    def __init__(self, graph, *, targets, script=None, delay=0.0):
        super().__init__(graph, targets=targets)
        self.script, self.delay, self.seen = dict(script or {}), delay, 0

    def run_simulation(self, request):
        self.seen += 1
        action = self.script.get(self.seen)
        if self.delay:
            time.sleep(self.delay)
        if action == 'exception':
            raise RuntimeError('scripted backend exception')
        if action in ('timeout', 'invalid_design'):
            exported = self.exports[request.netlist.job_id][1]
            directory = request.work_root / uuid4().hex
            directory.mkdir(parents=True)
            status = SimulationStatus.TIMEOUT if action == 'timeout' else SimulationStatus.INVALID_DESIGN
            return SimulationResult(directory.name, 'scripted-mock', 'synthetic', status, f'scripted_{action}',
                                    action == 'timeout', action != 'timeout', {}, {}, {}, dict(exported), directory, 0.0)
        result = super().run_simulation(request)
        if action == 'nan':
            return replace(result, metrics={'score': float('nan')})
        return result


@dataclass
class ScriptedEnvFactory:
    graph: object
    specs: tuple
    work_root: str
    max_steps: int
    scripts: dict = field(default_factory=dict)     # lane id -> script
    delays: dict = field(default_factory=dict)      # lane id -> seconds per simulation
    stop_on_success: bool = False

    def __call__(self, lane):
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        kinds = {g.parameter_kind for g in self.graph.parameter_groups if g.mutable}
        backend = ScriptedBackend(self.graph, targets={k: tasks.MOCK_TARGETS[k] for k in kinds},
                                  script=self.scripts.get(str(lane)), delay=self.delays.get(str(lane), 0.0))
        return CircuitSizingEnv(backend, self.graph, self.specs, Path(self.work_root) / f'worker-{lane}',
                                max_steps=self.max_steps, stop_on_success=self.stop_on_success,
                                expected_origin='synthetic')


def make_config(root, task='synthetic:opamp', *, threshold=0.95, run=None, output=None, research=None,
                advanced=None, project=None, mutate=None):
    raw = tasks.starter_config(task)
    raw['targets'][0]['lower'] = threshold
    raw['run'].update(dict(max_evaluations=20, seed=11, network=dict(SMALL_NET)), **(run or {}))
    raw['run']['advanced'] = dict(dict(batch_size=4, warmup_transitions=4, episode_length=3), **(advanced or {}))
    raw['output'] = dict(dict(output_root=str(root), experiment_name='t', flush_every_evaluations=5,
                              checkpoint_every_evaluations=None), **(output or {}))
    if research:
        raw['research'] = research
    if project:
        raw['project'].update(project)
    if mutate:
        mutate(raw)
    return schema.WorkbenchConfig.model_validate(raw)


def roots_for(root):
    return OutputRoots([Path(root)], include_default=False)


def execute(config, root, *, scripts=None, delays=None, confirm_transfer=False, use_processes=False):
    """prepare + run in-process with thread lanes. Returns (layout, final_state)."""
    roots = roots_for(root)
    layout, _ = runs.prepare_run(config, roots, confirm_transfer=confirm_transfer)
    return layout, run_prepared(layout, scripts=scripts, delays=delays, use_processes=use_processes)


def run_prepared(layout, *, scripts=None, delays=None, use_processes=False):
    config = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    task = tasks.load_task(config.circuit)
    engine = RunEngine(layout.run_dir, task=task, use_processes=use_processes, lock=runs.take_lock(layout.run_dir))
    if scripts or delays:
        engine._lane_factory = ScriptedEnvFactory(engine.compiled.graph, engine.compiled.specs, str(layout.work),
                                                  config.run.advanced.episode_length, scripts or {}, delays or {},
                                                  config.run.advanced.episode_terminates_on_success)
    return engine.run()


def rows(layout, table, columns=None):
    return DatasetReader(layout.data).rows(table, columns)


def summary(layout):
    return read_json(layout.summary)
