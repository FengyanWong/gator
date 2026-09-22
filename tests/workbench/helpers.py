"""Shared helpers for workbench tests. Everything here is MOCK: the analytic toy backend plus a
scripted variant that injects failures and delays. No Virtuoso, Spectre, network or agent CLI.

The circuit is a REAL one (status record 7.59): the workbench's one MOCK task, synthetic:gpdk045_ota5, is the GPDK045
OTA5 netlist on the toy backend. A test that needs other circuits (a transfer to another topology, a multi-task
experiment) registers more real examples for its own process with `other_circuits`; the workbench never lists them."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

# A script that imports these helpers OUTSIDE pytest (a scratch smoke run) must not write the user's remembered settings:
# prepare_run() saves output_root / concurrency / last_run into the settings folder, and conftest.py only redirects it under
# pytest. On 2026-09-22 a smoke script rewrote the live configs/local/workbench/settings.json this way. Under pytest the
# variable is already set and this line does nothing.
os.environ.setdefault('GATOR_WORKBENCH_SETTINGS_DIR', tempfile.mkdtemp(prefix='gator-wb-helpers-settings-'))

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


MOCK_TASK = 'synthetic:gpdk045_ota5'      # 3 width groups (input pair, mirror pair, tail): 5 rows, 3 action variables

# The other real GPDK045 examples, as MOCK circuits a test may add (netlist + device mapping, the mapping's groups).
OTHER_CIRCUITS = dict(
    gpdk045_ldo=dict(netlist='examples/circuits/gpdk045_ldo.scs', config='configs/gpdk045_ldo.json', circuit_class='ldo'),
    gpdk045_ota7=dict(netlist='examples/circuits/gpdk045_ota7.scs', config='configs/gpdk045_ota7.json', circuit_class='opamp'),
    gpdk045_vco=dict(netlist='examples/circuits/gpdk045_vco.scs', config='configs/gpdk045_vco.json', circuit_class='vco'),
)


@contextmanager
def other_circuits(*names):
    """synthetic:<name> for each named OTHER_CIRCUITS entry, in this process only (runs through `execute`, not a detached
    worker, which would not see them). Removed again afterwards."""
    added = {name: dict(OTHER_CIRCUITS[name], pdk_id='gpdk045', description='test only') for name in names}
    tasks.SYNTHETIC_FIXTURES.update(added)
    try:
        yield [f'synthetic:{name}' for name in names]
    finally:
        for name in added:
            tasks.SYNTHETIC_FIXTURES.pop(name, None)


def make_config(root, task=MOCK_TASK, *, threshold=0.95, run=None, output=None, research=None,
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
