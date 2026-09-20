"""Leave one declared circuit class out; all fixtures and objectives are synthetic."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from analog_optimizer.backends.synthetic_category import SyntheticCategoryBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv, graph_contract
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models.inputs import SpecSchema
from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser
from .transfer import TransferTask, validate_split


@dataclass(frozen=True)
class CategoryFactory:
    definitions: dict
    graphs: dict
    parallel_safe: bool = True

    def __call__(self, task, steps, output):
        return self.create_recorded(task, steps, output, None)

    def create_recorded(self, task, steps, output, recorder):
        definition = self.definitions[task.circuit_class]
        if (task.family != definition['family'] or
                graph_contract(task.graph) != graph_contract(self.graphs[task.circuit_class])):
            raise ValueError('Task differs from its declared synthetic class fixture')
        expected = MetricSpec(definition['metric_id'], 'fixture', scale=1,
                              **definition['specs'][task.partition])
        if task.specs != (expected,):
            raise ValueError('Task specifications differ from the frozen category definition')
        backend = SyntheticCategoryBackend(task.graph, **{key: definition[key] for key in (
            'targets', 'metric_id', 'score_multiplier', 'score_offset')})
        return CircuitSizingEnv(backend, task.graph, task.specs, output, max_steps=steps,
                                stop_on_success=False, expected_origin='synthetic', recorder=recorder)


def load_categories(root, manifest=None):
    root = Path(root).resolve()
    path = Path(manifest) if manifest is not None else root / 'configs/m6_cross_category.json'
    definition = json.loads(path.read_text())
    if definition['version'] != 'm6-synthetic-categories-v1' or definition['origin'] != 'synthetic':
        raise ValueError('Only the explicit synthetic M6 category contract is supported')
    classes = definition['classes']
    if set(classes) != {'opamp', 'ldo', 'vco'}:
        raise ValueError('M6 acceptance requires explicit opamp, ldo and vco fixtures')
    graphs, files = {}, {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()}
    for name, config in classes.items():
        mapping, netlist = root / config['mapping'], root / config['netlist']
        graphs[name] = SpectreParser(ParserConfig.from_file(mapping)).parse_file(netlist)
        # Validate the toy objective and mutable action coverage before running.
        SyntheticCategoryBackend(graphs[name], **{key: config[key] for key in (
            'targets', 'metric_id', 'score_multiplier', 'score_offset')})
        model_file = mapping.parent / json.loads(mapping.read_text())['models_file']
        for source in (mapping, netlist, model_file):
            files[str(source.resolve())] = hashlib.sha256(source.read_bytes()).hexdigest()
    schema = SpecSchema(version='m6-toy-spec-input-v1',
                        metrics=tuple((classes[name]['metric_id'], 'fixture', 1.0) for name in sorted(classes)))
    return CategoryFactory(deepcopy(classes), graphs), schema, dict(
        origin='synthetic', files=files, definition=definition,
        electrical_performance_validated=False, selection='predeclared; no fold used to tune another fold')


def category_tasks(factory, heldout):
    if heldout not in factory.definitions:
        raise ValueError('Unknown held-out category')
    tasks = []
    for name in sorted(factory.definitions):
        config = factory.definitions[name]
        for partition in (('test',) if name == heldout else ('train', 'validation')):
            spec = MetricSpec(config['metric_id'], 'fixture', scale=1, **config['specs'][partition])
            tasks.append(TransferTask(f'{name}-{partition}', partition,
                'category' if partition == 'test' else 'specification', config['family'],
                deepcopy(factory.graphs[name]), (spec,), circuit_class=name))
    validate_split(tasks)
    return tasks
