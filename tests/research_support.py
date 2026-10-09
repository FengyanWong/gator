"""Fixtures several research test modules share (refactoring package D1)."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from uuid import uuid4
from pathlib import Path
from types import SimpleNamespace

import pytest
torch = pytest.importorskip('torch')

from analog_optimizer.backends.backend import NetlistArtifact, SimulationResult, SimulationStatus, VirtuosoBackend
from analog_optimizer.envs import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.backends.gpdk045 import GEOMETRY, Gpdk045OtaProfile, number
from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend
from analog_optimizer.envs.sizing import ConditionResult, mapped_operating_points, Observation
from analog_optimizer.backends.conditions import SimulationCondition
from analog_optimizer.graph.circuit_graph import (CircuitGraph, Connection, Device, Diagnostic, Net, ParameterBinding, ParameterGroup, ParameterValue, SourceSpan)
from analog_optimizer.training.replay import Transition
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.models.graph_transformer import ModelConfig
from analog_optimizer.training.sac import SACLearner



@pytest.fixture(autouse=True)
def cpu():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


class SyntheticSizingFixture(VirtuosoBackend):
    def __init__(self, graph):
        self.graph = deepcopy(graph)
        self.initial = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
        self.parameters = dict(self.initial)
        self.status, self.evaluated, self.unit = SimulationStatus.OK, True, 'fixture'
        self.valid, self.value_override = True, None
        self.connected, self.calls, self.writes = False, 0, 0
        self.exports = {}

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def restore(self):
        self.parameters = dict(self.initial)

    def read_parameters(self):
        return dict(self.parameters)

    def set_parameters(self, parameters):
        self.writes += 1
        self.parameters = dict(parameters)

    def generate_netlist(self, work_root):
        job_id = uuid4().hex
        directory = work_root / job_id
        directory.mkdir(parents=True)
        path = directory / 'fixture.json'
        path.write_text(json.dumps(sorted(self.parameters.items())))
        self.exports[job_id] = dict(self.parameters)
        return NetlistArtifact(path, job_id, hashlib.sha256(path.read_bytes()).hexdigest(), 'synthetic')

    def get_circuit_graph(self, artifact):
        graph, values = deepcopy(self.graph), self.exports[artifact.job_id]
        for group_index, group in enumerate(graph.parameter_groups):
            if not group.mutable:
                continue
            for member in group.members:
                old = graph.parameters[member.device_id][member.parameter]
                key = (member.device_id, old.source_name or member.parameter)
                graph.parameters[member.device_id][member.parameter] = replace(old, value=values[key], raw=str(values[key]))
            graph.parameter_groups[group_index] = replace(group, value=values[key] / member.ratio)
        return graph

    def run_simulation(self, request):
        self.calls += 1
        directory = request.work_root / uuid4().hex
        directory.mkdir(parents=True)
        value = next(iter(self.parameters.values())) / 1e-6
        if self.value_override is not None:
            value = self.value_override
        return SimulationResult(directory.name, 'synthetic-sizing-fixture', 'synthetic', self.status,
                                'injected_fixture', False, self.evaluated, {'score': value},
                                {'score': self.unit}, {'score': self.valid}, dict(self.parameters), directory, 0.01)


def environment(backend, tmp_path, **kwargs):
    return CircuitSizingEnv(backend, backend.graph, [MetricSpec('score', 'fixture', 'min', 1, lower=3)],
                            tmp_path, expected_origin='synthetic', **kwargs)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile():
    return Gpdk045OtaProfile(design_file=ROOT / 'configs/gpdk045_opamp_design.json',
                            mapping_file=ROOT / 'configs/gpdk045_opamp.json',
                            reference_structure=ROOT / 'examples/circuits/gpdk045_ota5.scs',
                            reference_readback=ROOT / 'examples/circuits/gpdk045_ota5.cdf.json')


@pytest.fixture
def adapter(tmp_path, monkeypatch, profile):
    env = tmp_path / 'bridge.env'
    env.write_text('# offline test configuration\n')
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps({'library': 'TEST', 'core_cell': profile.design['core_cell'],
                                  'testbench_cell': profile.design['testbench_cell'], 'config': profile.design}))
    state = deepcopy(profile.reference)
    client = SimpleNamespace(closed=False, list_windows=lambda: [])
    client.close = lambda: setattr(client, 'closed', True)
    def export(lib, cell, output, timeout):
        output.mkdir()
        (output / 'netlist').write_bytes((ROOT / 'examples/circuits/gpdk045_ota5.scs').read_bytes())
        return {'input_file': str(output / 'input.scs')}
    client.schematic = SimpleNamespace(read=lambda *a, **kw: deepcopy(state), export_netlist=export)
    def attach(self):
        self.bridge_version = 'offline-fault-injection'
        return client
    monkeypatch.setattr(VirtuosoBridgeBackend, '_attach', attach)
    backend = VirtuosoBridgeBackend(BridgeConfig(env, 'TEST', receipt, tmp_path / 'state', '/models/gpdk.scs'), profile)
    backend.test_state = state
    backend.test_client = client
    yield backend
    backend.close()


def changing_writer(backend, *, fail_second=False, stale=False):
    calls = []
    def write(client, lib, cell, name, width, length):
        calls.append(name)
        if fail_second and len(calls) == 2:
            raise RuntimeError('injected callback failure')
        params = backend.circuit.instances(backend.test_state)[name]['params']
        ratio = number(width) / number(params['w'])
        params['w'] = params['fw'] = width
        if not stale:
            # Deliberate test-only values; this is not a PDK/physics model.
            for key in GEOMETRY:
                params[key] = str(number(params[key]) * ratio)
    return write, calls


def observation(graph, *, steps=4):
    return Observation(deepcopy(graph), (MetricSpec('score', 'fixture', 'min', 1, lower=.95),),
                       {'score': .6}, {'score': True}, {'score': 'fixture'}, 'ok', 'synthetic', steps, 'fixture')


EVIDENCE = ROOT / 'artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649'


def read(path):
    return json.loads(Path(path).read_text())


def recorded_observation(record):
    assert record['origin'] == 'real' and record['status'] == 'ok'
    saved = deepcopy(record['observation'])
    data = saved.pop('graph')
    data['devices'] = [Device(**dict(d, terminals=tuple(d['terminals']), source=SourceSpan(**d['source']))) for d in data['devices']]
    data['nets'] = [Net(**dict(n, roles=tuple(n['roles']))) for n in data['nets']]
    data['connections'] = [Connection(**c) for c in data['connections']]
    data['parameters'] = {d: {k: ParameterValue(**dict(v, source=SourceSpan(**v['source']))) for k, v in values.items()}
                          for d, values in data['parameters'].items()}
    data['parameter_groups'] = [ParameterGroup(**dict(g, members=tuple(ParameterBinding(**m) for m in g['members'])))
                                for g in data['parameter_groups']]
    data['diagnostics'] = [Diagnostic(**dict(d, source=SourceSpan(**d['source']))) for d in data['diagnostics']]
    graph = CircuitGraph(**data)
    condition = SimulationCondition.from_dict(saved.pop('condition'))
    measurements = read(Path(record['artifact_directory']) / 'measurements.json')
    assert measurements['origin'] == 'real' and measurements['job_id'] == record['job_id']
    operating_points, unmatched = mapped_operating_points(graph, measurements.get('operating_points'))
    row = ConditionResult(condition, saved['status'], record['candidate_evaluated'], saved['metrics'],
                          saved['metric_units'], saved['metric_validity'], saved['job_id'], record['reason_code'],
                          measurements.get('operating_points') or {})
    saved['specs'] = tuple(MetricSpec(**s) for s in saved['specs'])
    return Observation(graph=graph, condition=condition, **saved, condition_results=(row,),
                       planned_conditions=(condition,), operating_points=operating_points,
                       unmatched_operating_points=unmatched)


@pytest.fixture(scope='module')
def real_transition():
    if not EVIDENCE.is_dir():
        pytest.fail('Required local REAL evidence is unavailable; do not substitute a simulator mock')
    report = read(EVIDENCE / 'opamp/report.json')
    phase = next(p for p in report['phases'] if p['circuit_class'] == 'opamp')
    before, after = (read(p) for p in phase['records'][:2])
    first, last = recorded_observation(before), recorded_observation(after)
    transition = Transition(first, after['proposal'], after['reward'], last, after['terminated'], after['truncated'],
                            after['bootstrap'], {(p['device'], p['parameter']): p['value'] for p in after['applied_parameters']},
                            after['candidate_id'], phase['records'][1])
    transition.validate()
    return transition


EXPERIMENT = {'origin': 'synthetic', 'split': 'training-fixture', 'designs': ['opamp-v1', 'ldo-v1']}


@pytest.fixture(autouse=True)
def deterministic_cpu():
    threads = torch.get_num_threads()
    rng = torch.get_rng_state()
    torch.set_num_threads(1)
    torch.manual_seed(135)
    yield
    torch.set_num_threads(threads)
    torch.set_rng_state(rng)


@pytest.fixture
def transitions(opamp, ldo, tmp_path):
    result = []
    for graph in (opamp, ldo):
        backend = SyntheticSizingBackend(graph, targets={'w': .4, 'c': -.3})
        with CircuitSizingEnv(backend, graph, observation(graph).specs, tmp_path,
                              max_steps=3, stop_on_success=False, expected_origin='synthetic') as env:
            current, _ = env.reset()
            for value in (-.6, .2, .7):
                proposal = {g: value for g in env.mapper.group_ids}
                step = env.step(proposal)
                result.append(Transition.from_step(current, proposal, step))
                current = step[0]
        assert backend.parameters == backend.initial
    return result


def model_config(encoder):
    return ModelConfig(hidden_dim=16, heads=2, layers=2, encoder_type=encoder)


def learner(encoder='graph_transformer', **kwargs):
    return SACLearner(experiment=EXPERIMENT, model_config=model_config(encoder), **kwargs)


MODEL = ModelConfig(hidden_dim=16, heads=2, layers=2)
