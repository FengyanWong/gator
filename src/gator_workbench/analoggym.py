"""Pinned, local AnalogGym-Opt adapter. No model files or upstream Python are vendored.

The importer keeps both original testbenches. A candidate writes their common
parameters, then ngspice sources the transient deck after the AC/DC control block.
The upstream evaluator reads its native output files. This preserves its documented
penalty sentinels as benchmark outputs; they are not invented successful measurements.
Only the audited module hashes below may be loaded, from an explicitly imported task.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import threading

from analog_optimizer.backends.backend import SimulationStatus
from .ngspice_backend import NgspiceBackend, NgspiceEnvFactory
from .ngspice_netlist import parse_text

COMMIT = '10093e3496ef2c7d06494d91d131b0cc5de6c25b'
MODULES = {
 'circuit_config_loader':'0e82a1ce8b8cb2639ebe3c57021cd6e46b1c56ecaecefc8ade9c8ba903f1002d',
 'dev_params':'39be8de9c93ef83be7f8e031896330b791bb65078179a97d1d60167e1fb6788f',
 'utils':'1d632e1ab9fda7609134158d84a056c07ccd7eba964cae16b4c51827fa2d60e1',
 'reporting_metrics':'b058872a4a77a682816afc87005daf687d4235fed97333f2253ab3f9723aef79',
 'AmpEnv':'a1388e7e9966d5832c095f61cac050fa35e35bd7b700186cfe63ebc11d4c97ec',
 'LdoEnv':'26d2783189a993afc210b524825af809fe09f544793e2bbfc41ae471535e85af'}
_LOCK = threading.Lock()


@lru_cache(maxsize=4)
def evaluator_modules(root):
    """Import only the pinned public evaluator, without invoking its destructive constructor."""
    root = Path(root)
    for name, expected in MODULES.items():
        if hashlib.sha256((root / (name + '.py')).read_bytes()).hexdigest() != expected:
            raise ValueError(f'AnalogGym evaluator {name} differs from pinned commit {COMMIT}')
    with _LOCK:
        previous = {name: sys.modules.get(name) for name in MODULES}
        loaded = {}
        try:
            for name in MODULES:
                spec = importlib.util.spec_from_file_location(name, root / (name + '.py'))
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                loaded[name] = module
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        return loaded


def evaluate_outputs(bundle, directory, values):
    modules = evaluator_modules(bundle['checkout'])
    cls = modules['LdoEnv'].LdoEnv if bundle['name'].startswith('ldo_') else modules['AmpEnv'].AmpEnv
    env = cls.__new__(cls)
    config = bundle['config']
    env.circuit_config, env.path = config, config['file_paths']
    env.device_count = {name: row['num'] for name, row in config['device'].items()}
    env.eps, env.post_target_bonus_config = 1e-8, {}
    parser = modules['utils'].OutputParser2(tuple(map(tuple, config['ckt_hierarchy'])), str(directory))
    result = env._get_info(parser, values)
    if result is None:
        raise ValueError('Upstream evaluator could not read the candidate outputs')
    aliases = {'phase_margin':'phase_margin (deg)', 'settlingTime':'setting_time', 'Active_Area':'Active Area'}
    metrics = {key: result.get(aliases.get(key, key)) for key in config['performance']}
    metrics = {key: float(value) if value is not None and math.isfinite(value) else None for key,value in metrics.items()}
    components = result['reward_components']
    passed = all(components[key] >= -1e-12 for key in
                 ('base_constraint_reward','base_FOML_score','base_FOMS_score','base_Active_Area_score'))
    return metrics, passed, result


def physical_graph(parsed):
    """SKY130 primitive W/L inputs are in micrometres; GATOR uses SI lengths."""
    resistors = set()
    for index, device in enumerate(parsed.graph.devices):
        if device.model_ref in ('sky130_fd_pr__res_high_po_0p35', 'sky130_fd_pr__res_xhigh_po_0p35') and len(device.terminals)==3:
            terminals = ('positive', 'negative', 'bulk')
            parsed.graph.devices[index] = replace(device, kind='resistor', terminals=terminals)
            resistors.add(device.id)
            parsed.graph.connections = [replace(c, terminal=terminals[c.ordinal]) if c.device_id==device.id else c
                                        for c in parsed.graph.connections]
        if device.kind in ('nmos','pmos') and device.model_ref.startswith('sky130_fd_pr__'):
            values = parsed.graph.parameters[device.id]
            for key in ('w','l'):
                if key in values and values[key].valid:
                    values[key] = replace(values[key], value=values[key].value * 1e-6)
    parsed.graph.diagnostics = [d for d in parsed.graph.diagnostics if not (
        d.code in ('port_count','unknown_device') and any(d.message.startswith(name+':') for name in resistors))]
    return parsed


def substitute(text, values):
    for name, value in values.items():
        pattern = rf'(?im)^(\s*\.param\s+{re.escape(name)}\s*=)[^\n]*$'
        text, count = re.subn(pattern, lambda m: m[1] + format(value,'.17g'), text)
        if count != 1:
            raise ValueError(f'Expected one explicit parameter {name}, got {count}')
    return text


def export_best_decks(text, bundle, device_kinds, members):
    """Write both native testbenches and verify every requested physical member."""
    try:
        assignments = {(m['instance_path'], m['parameter_name']): float(m['value'])
                       for m in members if m.get('value') is not None}
        values = native_values(bundle, assignments)
        primary = substitute(text, values)
        transient = substitute(bundle['transient'], values)
        for index, deck in enumerate((primary, transient)):
            graph = physical_graph(parse_text(deck, device_kinds=device_kinds, scan_includes=False)).graph
            for (device, parameter), expected in assignments.items():
                # Transient uses one DUT instance; AC/DC may use several.
                if device not in graph.parameters:
                    if index == 0:
                        raise ValueError(f'{device} is missing from exported AC/DC testbench')
                    continue
                actual = graph.parameters[device].get(parameter)
                if actual is None or not actual.valid or not math.isclose(actual.value, expected, rel_tol=1e-12):
                    raise ValueError(f'{device}.{parameter} did not read back from exported benchmark deck')
        primary, count = re.subn(r'(?im)^\s*\.endc\s*$', 'source transient.cir\n.endc', primary, count=1)
        if count != 1:
            raise ValueError('Expected one AC/DC control block for benchmark export')
        return dict(status='verified', text=primary, additional_files={'transient.cir': transient})
    except (KeyError, ValueError) as exc:
        return dict(status='unsupported', reason=f'Benchmark export: {exc}')


def native_values(bundle, parameters):
    """Retain the declared fixed bias even when a caller supplies extra assignments."""
    fixed = bundle.get('fixed_native_values', {})
    for name, value in fixed.items():
        row = bundle['leaders'][name]
        assigned = parameters.get((row['device'], row['parameter']))
        if assigned is not None and not math.isclose(assigned, value * row['physical_per_native'], rel_tol=1e-12):
            raise ValueError(f'{name} is fixed at the benchmark starting bias')
    return {name: fixed[name] if name in fixed else
            parameters[(row['device'], row['parameter'])] / row['physical_per_native']
            for name, row in bundle['leaders'].items()}


def validate_benchmark_config(config, bundle):
    """Freeze the approved domain/scoring across numeric and AI comparison arms."""
    fixed = bundle.get('fixed_native_values', {})
    expected = {k:v for k,v in bundle['native_initial'].items() if k.startswith('I_')}
    if fixed != expected or bundle.get('scoring') != 'feasibility_only':
        raise ValueError('Reimport the benchmark with fixed starting bias and feasibility-only scoring')
    if any(t.direction_after_feasible != 'none' for t in config.targets):
        raise ValueError('Benchmark objective metrics must be descriptive only')
    if any(p.variable_id.split('__')[0] in fixed or p.unit in ('A', 'mA', 'uA', 'nA') for p in config.parameters):
        raise ValueError('Benchmark bias currents must remain outside the search domain for every arm')
    probes = {p.source_name for p in config.measurements}
    if not set(bundle['metric_units']) <= probes:
        raise ValueError('Every benchmark metric must remain a Probe')


class AnalogGymBackend(NgspiceBackend):
    def __init__(self, *args, bundle, **kwargs):
        text, graph, link = args
        empty = deepcopy(graph)
        empty.parameter_groups = []
        super().__init__(text, empty, link, **kwargs)
        if link.remote:
            raise ValueError('Imported AnalogGym tasks currently require free local ngspice')
        self.bundle, self.graph = bundle, deepcopy(graph)
        self.initial = graph.assignments({g.id:g.value for g in graph.parameter_groups if g.mutable})
        self.parameters = dict(self.initial)

    def native_values(self, parameters=None):
        parameters = self.parameters if parameters is None else parameters
        return native_values(self.bundle, parameters)

    def deck(self, parameters=None):
        return substitute(self.text, self.native_values(parameters))

    def generate_netlist(self, work_root, *, condition=None):
        artifact = super().generate_netlist(work_root, condition=condition)
        companion = artifact.path.parent / 'transient.cir'
        from .ngspice_analysis import instrument
        companion.write_text(instrument(substitute(self.bundle['transient'], self.native_values())))
        text = artifact.path.read_text()
        text = re.sub(r'(?im)^\s*\.endc\s*$', 'source transient.cir\n.endc', text, count=1)
        artifact.path.write_text(text)
        artifact = replace(artifact, sha256=hashlib.sha256(artifact.path.read_bytes()).hexdigest())
        self.exports[artifact.job_id] = (artifact, dict(self.parameters))
        return artifact

    def get_circuit_graph(self, artifact):
        saved, values = self.exports[artifact.job_id]
        if artifact != saved or hashlib.sha256(artifact.path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError('Imported candidate deck changed')
        parsed = physical_graph(parse_text(artifact.path.read_text(), device_kinds=self.device_kinds, scan_includes=False))
        graph = deepcopy(self.graph)
        for i,group in enumerate(graph.parameter_groups):
            for member in group.members:
                actual = parsed.graph.parameters[member.device_id][member.parameter]
                expected = values[(member.device_id, member.parameter)]
                if not actual.valid or not math.isclose(actual.value, expected, rel_tol=1e-12):
                    raise ValueError(f'Imported candidate did not read back {member}')
                graph.parameters[member.device_id][member.parameter] = actual
            graph.parameter_groups[i] = replace(group, value=values[(group.members[0].device_id,group.members[0].parameter)])
        graph.validate()
        return graph

    def run_simulation(self, request):
        result = super().run_simulation(replace(request, required_metrics=tuple(self.parsed.result_names)))
        metrics = {key:None for key in self.bundle['metric_units']}
        verdict, failure = False, None
        if result.candidate_evaluated:
            try:
                metrics, verdict, _ = evaluate_outputs(self.bundle, request.netlist.path.parent,
                                                       self.native_values(request.parameters))
            except (ValueError, OSError, IndexError, TypeError, ZeroDivisionError) as exc:
                failure = str(exc)[:400]
        # Native benchmark outputs include its published penalty sentinels. Their
        # source and the independent benchmark verdict stay explicit in the job evidence.
        (result.artifact_directory/'benchmark.json').write_text(json.dumps(dict(
            benchmark_commit=COMMIT, native_metrics=metrics, upstream_passed=verdict, error=failure,
            analyses=['AC/DC testbench','transient testbench'], simulator_processes=result.simulator_invocations),allow_nan=False))
        scale = self.bundle['metric_scales']
        metrics = {key: value * scale[key] if value is not None else None for key,value in metrics.items()}
        return replace(result, metrics=metrics, metric_units=self.bundle['metric_units'],
                       metric_validity={key:value is not None for key,value in metrics.items()},
                       status=SimulationStatus.MEASUREMENT_ERROR if failure else result.status,
                       error_summary=failure or result.error_summary)


@dataclass(frozen=True)
class AnalogGymFactory(NgspiceEnvFactory):
    bundle: dict = None

    def __call__(self, lane):
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        backend = AnalogGymBackend(self.text, self.graph, self.link, bundle=self.bundle, units=self.units,
            device_kinds=self.device_kinds, include_root=self.include_root, circuit_id=self.circuit_id, source=self.source)
        if self.plan is not None:
            self.plan.wrap(backend)
        return CircuitSizingEnv(backend,self.graph,self.specs,Path(self.work_root)/f'worker-{lane}',max_steps=self.max_steps,
            timeout_seconds=self.timeout_seconds,stop_on_success=self.stop_on_success,expected_origin='real',
            reward_settings=self.reward_settings)
