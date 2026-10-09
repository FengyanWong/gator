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
import socket
import tempfile
import threading
import time
from uuid import uuid4

# A script that imports these helpers OUTSIDE pytest (a scratch smoke run) must not write the user's remembered settings:
# prepare_run() saves output_root / concurrency / last_run into the settings folder, and conftest.py only redirects it under
# pytest. On 2026-09-22 a smoke script rewrote the live configs/local/workbench/settings.json this way. Under pytest the
# variable is already set and nothing happens: `setdefault(..., mkdtemp())` made the folder anyway and left 2 per test
# process in /tmp (review round 5: 1,384 of them).
if not os.environ.get('GATOR_WORKBENCH_SETTINGS_DIR'):
    os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = tempfile.mkdtemp(prefix='gator-wb-helpers-settings-')

import pytest

from analog_optimizer.backends.backend import SimulationResult, SimulationStatus
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend

from gator_workbench import runs, schema, task_registry, tasks
from gator_workbench.engine import RunEngine
from gator_workbench.paths import OutputRoots
from gator_workbench.storage import DatasetReader, read_json
import sys
from gator_workbench.connection import ConnectionMonitor, LAYERS
import json
from gator_workbench import task_saving
from gator_workbench import validation
from gator_workbench.storage.atomic import write_json

REPO = Path(__file__).resolve().parents[2]

SMALL_NET = dict(encoder_type='graph_transformer', hidden_dim=16, heads=2, layers=1)


def workbench_app(root, **options):
    from gator_workbench.api import create_app
    return create_app(**{'extra_output_roots': [str(root)], 'serve_frontend': False, 'auto_check_on_start': False, **options})


@contextmanager
def workbench_server(root):
    """Serve the isolated test app on loopback, including streaming responses."""
    import uvicorn
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        instance = uvicorn.Server(uvicorn.Config(workbench_app(root), log_level='warning', lifespan='off'))
        thread = threading.Thread(target=instance.run, kwargs=dict(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(300):
                if instance.started:
                    break
                time.sleep(0.02)
            else:
                raise RuntimeError('The test HTTP server did not start')
            yield sock.getsockname()[1]
        finally:
            instance.should_exit = True
            thread.join(timeout=10)


# Two fixtures that several test modules used to write out for themselves (review of 2026-09-23). A module gets one by
# importing it: `from helpers import bridge_is_importable  # noqa: F401` - an imported fixture belongs to that module,
# so the autouse one below applies there and nowhere else.
@pytest.fixture(autouse=True)
def bridge_is_importable(monkeypatch):
    """The Virtuoso bridge package counts as installed, so a real task is not blocked for the want of it."""
    monkeypatch.setattr(tasks, 'bridge_importable', lambda: True)


@pytest.fixture
def bridge_settings(tmp_path):
    """A connection profile's settings: an environment file with a secret in it (redaction is tested on this)."""
    env = tmp_path / 'bridge.env'
    env.write_text('VB_REMOTE_HOST=eda-host\nVB_PASSWORD=super-secret-value\n')
    return dict(env_file=str(env), profile='lab')


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

# Other circuits as MOCK circuits a test may add (netlist + device mapping, the mapping's groups): the GPDK045 VCO example
# and the optimizer package's toy LDO and two-stage op-amp (the GPDK045 OTA7 and LDO examples were deleted on 2026-09-30,
# record 7.128).
OTHER_CIRCUITS = dict(
    toy_ldo=dict(netlist='tests/fixtures/synthetic/ldo.scs', config='configs/ldo.json', circuit_class='ldo',
                 pdk_id=tasks.MOCK_PDK),
    toy_opamp_two_stage=dict(netlist='tests/fixtures/synthetic/opamp_two_stage.scs', config='configs/opamp_two_stage.json',
                             circuit_class='opamp', pdk_id=tasks.MOCK_PDK),
    gpdk045_vco=dict(netlist='examples/circuits/gpdk045_vco.scs', config='configs/gpdk045_vco.json', circuit_class='vco',
                     pdk_id='gpdk045'),
)


@contextmanager
def other_circuits(*names):
    """synthetic:<name> for each named OTHER_CIRCUITS entry, in this process only (runs through `execute`, not a detached
    worker, which would not see them). Removed again afterwards."""
    added = {name: dict(OTHER_CIRCUITS[name], description='test only') for name in names}
    task_registry.SYNTHETIC_FIXTURES.update(added)
    try:
        yield [f'synthetic:{name}' for name in names]
    finally:
        for name in added:
            task_registry.SYNTHETIC_FIXTURES.pop(name, None)


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


def probe(tmp_path, **states):
    layers = [dict(layer=n, state=states.get(n, 'ok'), reason_code=None, diagnostic=None, details={}) for n in LAYERS]
    script = tmp_path / 'probe.py'
    script.write_text(f'import json\nprint(json.dumps(dict(layers={layers!r})))\n')
    return ConnectionMonitor(probe_command=[sys.executable, str(script)])


def wait_for(client, run_dir, states=('completed', 'failed', 'paused', 'stopped', 'cancelled'), timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get('/api/runs/status', params=dict(run_dir=run_dir)).json()
        if status.get('state') in states and not status.get('worker_alive'):
            return status
        time.sleep(0.3)
    raise AssertionError(f'run did not finish: {status}')


def edit_json(path, change):
    value = json.loads(Path(path).read_text())
    change(value)
    Path(path).write_text(json.dumps(value))


@pytest.fixture(autouse=True)
def _no_save_yet(monkeypatch):
    """The module keeps the running save and the last one for the whole process: each test starts without either."""
    monkeypatch.setattr(task_saving, '_running', None)
    monkeypatch.setattr(task_saving, '_last', None)
    monkeypatch.setattr(task_saving, '_took', {})


def issues(report, level=None):
    return {i.code for i in report.issues if level is None or i.level == level}


def check(config, task='synthetic:gpdk045_ota5'):
    runtime = tasks.load_task(config.circuit)
    return validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics)), runtime


# ------------------------------------------------------------------------------- pauses for infrastructure failures
def infrastructure_pause(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2,
                                                           max_consecutive_infrastructure_failures=3,
                                                           max_consecutive_failures=50))
    script = {n: 'timeout' for n in range(3, 40)}
    layout, state = execute(config, tmp_path, scripts={'0': script, '1': script})
    assert state == 'paused' and summary(layout)['stop_reason'] == 'infrastructure_failures'
    return config, layout


def prepared(root, **kwargs):
    """A MOCK run as prepare_run leaves it for its worker: state `created`."""
    layout, manifest = runs.prepare_run(make_config(root, **kwargs), roots_for(root))
    return layout, manifest


TOP = 4.2380000000000004e-05


# ---- run folders read many at a time ----------------------------------------------------------------------------------
def fabricate_run(root, name, *, created, kind=None, state='completed', task='real:ring_a'):
    run = root / 'exp__0123456789ab' / 'runs' / 'task' / name
    run.mkdir(parents=True)
    write_json(run / 'run_manifest.json', dict(run_id=name, created_utc=created, mock=False, experiment_name='exp',
                                               experiment_id='0123456789ab', task_name='task', run_kind=kind, state=state,
                                               circuit=dict(task_key=task)))
    write_json(run / 'status.json', dict(state=state))
    write_json(run / 'run_summary.json', dict(output=dict(resumability='full_state')))
    return run
