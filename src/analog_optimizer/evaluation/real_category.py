"""Frozen nominal OpAmp/LDO/VCO pilot, with no simulator access during planning."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import importlib.metadata
import json
from pathlib import Path

from analog_optimizer.backends.conditions import SimulationCondition
from analog_optimizer.backends.gpdk045 import Gpdk045OtaProfile, GEOMETRY, equal, number
from analog_optimizer.backends.gpdk045_ldo import Gpdk045LdoProfile
from analog_optimizer.backends.gpdk045_vco import Gpdk045VcoProfile
from analog_optimizer.backends.common import file_digest
from analog_optimizer.backends.spectre_deck import build_deck
from analog_optimizer.envs.sizing import graph_contract
from analog_optimizer.graph.pyg_converter import FeatureSchema
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
from analog_optimizer.models.inputs import SpecSchema
from analog_optimizer.training.sac import SACConfig, source_digest
from .benchmark import benchmark_call_budget, benchmark_models
from .transfer import TransferTask, json_digest, validate_split


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass
class PhysicalCategories:
    definition: dict
    profiles: dict
    schema: SpecSchema
    files: dict

    def tasks(self, heldout):
        require(heldout in self.profiles, 'Unknown held-out physical class')
        tasks = []
        for name in sorted(self.profiles):
            cfg = self.definition['classes'][name]
            for partition in (('test',) if name == heldout else ('train','validation')):
                tasks.append(TransferTask(f'{name}-{partition}', partition,
                    'category' if partition=='test' else 'specification', cfg['family'],
                    self.profiles[name].optimization_graph(),
                    tuple(MetricSpec(**s) for s in cfg['specs'][partition]), circuit_class=name))
        validate_split(tasks)
        return tasks


def load_physical_categories(root, manifest=None):
    root = Path(root).resolve()
    path = Path(manifest or root/'configs/m6_real_cross_category.json').resolve()
    definition = read(path)
    require(definition['version']=='m6-real-categories-v1' and definition['origin']=='real',
            'Explicit real M6 contract required')
    classes = definition['classes']
    require(set(classes)=={'opamp','ldo','vco'}, 'All three qualified physical classes required')
    require(set(definition['heldout'])==set(classes) and len(definition['heldout'])==3,
            'Exactly three distinct held-out folds required')
    require(definition['settings']['max_workers']==1, 'Physical category pilot is serial')
    schema = SpecSchema(version=definition['schema']['version'],
                        metrics=tuple(tuple(m) for m in definition['schema']['metrics']))
    registry = {name:unit for name,unit,_ in schema.metrics}
    require(not any(unit=='fixture' or name.startswith('toy_') for name,unit,_ in schema.metrics),
            'Toy metrics cannot enter the physical registry')
    profiles, files = {}, {str(path):file_digest(path)}
    for name, cls in (('opamp',Gpdk045OtaProfile),('ldo',Gpdk045LdoProfile),('vco',Gpdk045VcoProfile)):
        cfg = classes[name]
        require(set(cfg['specs'])=={'train','validation','test'}, 'All specification partitions required')
        kwargs = dict(design_file=root/cfg['design'],mapping_file=root/cfg['mapping'],
                      reference_structure=root/cfg['netlist'],reference_readback=root/cfg['readback'])
        if name=='vco':
            require(cfg['analysis_mode']=='fast', 'Physical pilot requires the qualified fast VCO policy')
            kwargs['analysis_mode']='fast'
        else:
            require(cfg['analysis_mode']=='qualified', 'Unqualified analysis policy')
        profiles[name] = cls(**kwargs)
        for specs in cfg['specs'].values():
            parsed = tuple(MetricSpec(**s) for s in specs)
            SpecificationEvaluator(parsed)
            require(all(s.active and s.required and registry.get(s.metric_id)==s.unit for s in parsed),
                    'Every physical task metric must be required, active and registered with its unit')
        sources = [root/cfg[k] for k in ('design','mapping','netlist','readback')]
        mapping = read(root/cfg['mapping'])
        if 'models_file' in mapping:
            sources.append((root/cfg['mapping']).parent/mapping['models_file'])
        for source in sources:
            files[str(source.resolve())]=file_digest(source)
    conditions = root/'configs/gpdk045_conditions.json'
    files[str(conditions)]=file_digest(conditions)
    suite = PhysicalCategories(deepcopy(definition),profiles,schema,files)
    for name in definition['heldout']:
        suite.tasks(name)
    return suite


def suite_budget(suite):
    settings = suite.definition['settings']
    models, methods, validation_models = benchmark_models(settings)
    seeds = len(settings['seeds'])
    rows = {}
    for heldout in suite.definition['heldout']:
        tasks = suite.tasks(heldout)
        calls = benchmark_call_budget(tasks,settings)
        row = dict(source=seeds*len(models)*2*(1+settings['pretrain_steps']),
                   validation=seeds*len(validation_models)*2*2,
                   target=seeds*len(methods)*(1+settings['test_steps']))
        require(sum(row.values())==calls, 'Budget breakdown differs from runner')
        rows[heldout]=dict(**row,total=calls)
    benchmark = sum(r['total'] for r in rows.values())
    total = benchmark+len(suite.profiles)
    require(total<=settings['max_calls'], f'Global budget {total} including final checks exceeds cap {settings["max_calls"]}')
    return dict(folds=rows,benchmark_calls=benchmark,final_baseline_calls=len(suite.profiles),
                total_calls=total,cap=settings['max_calls'],unit='one complete nominal candidate package',
                failures_and_resets_counted=True,automatic_retries=0,cache_hits=0)


def bind_references(suite, bindings):
    """Verify trusted saved evidence against current physical profiles, offline."""
    require(set(bindings['circuits'])==set(suite.profiles), 'Missing qualified circuit binding')
    references, files = {}, {}
    require(bindings.get('prior_data_used_for_learning',False) is False,
            'Prior qualification data cannot be imported into learning')
    for evidence_path in bindings.get('prior_evidence',{}).values():
        path = Path(evidence_path).resolve()
        evidence = read(path)
        require(evidence.get('passed',evidence.get('completed')) is True, 'Prior qualification evidence is incomplete')
        files[str(path)] = file_digest(path)
    inspection_path = Path(bindings['final_inspection']).resolve()
    inspection = read(inspection_path)
    require(inspection['passed'] and inspection['all_circuits_restored'] and inspection['model_hashes_match_before'],
            'Completed physical restoration/model inspection required')
    files[str(inspection_path)] = file_digest(inspection_path)
    for name,profile in suite.profiles.items():
        binding = bindings['circuits'][name]
        receipt_path, measured_path = (Path(binding[k]).resolve() for k in ('creation_receipt','measurements'))
        receipt, measured = read(receipt_path),read(measured_path)
        baseline_parameters = profile.validate_readback(profile.reference)
        job = measured_path.parent
        result, bridge = read(job/'result.json'),read(job/'bridge_result.json')
        require(receipt['library']==bindings['library'] and receipt['config']==profile.design,
                'Circuit creation receipt differs from physical design')
        inspected = inspection['full_snapshots'][profile.design['core_cell']]
        require(profile.validate_readback(inspected)==baseline_parameters,
                'Inspected core differs from qualified reference')
        # The old OTA reference is a filtered CDF snapshot. Validate all physical
        # fields while retaining the complete inspected snapshot for live equality.
        actual, original = profile.instances(inspected),profile.instances(profile.reference)
        for device,_ in profile.writable_keys:
            inst_name = device.split('/')[1]
            require(all(equal(number(actual[inst_name]['params'][k]),number(original[inst_name]['params'][k]))
                        for k in ('w','fw','l','m','fingers')+GEOMETRY), 'Inspected baseline geometry differs')
        require(measured['origin']=='real' and result['origin']=='real' and result['status']=='ok'
                and result['simulator_invocations']==1, 'Successful real baseline required')
        condition = SimulationCondition.from_dict(result['condition'])
        profile.validate_condition(condition)
        require(condition.nominal_only and condition.corner==profile.nominal_corner, 'Nominal baseline required')
        require(bridge['cell']==profile.design['testbench_cell'] and bridge['library']==bindings['library']
                and bridge['model_file']==bindings['model_file'], 'Baseline execution binding differs')
        require(measured['job_id']==result['job_id']==bridge['job_id'] and
                measured['condition']==result['condition']==bridge['condition'], 'Baseline identity differs')
        require(measured['metrics']==result['metrics'] and measured['metric_units']==result['metric_units']
                and measured['metric_validity']==result['metric_validity'], 'Baseline measurements differ')
        assignments = {(p['device'],p['parameter']):p['value'] for p in result['applied_parameters']}
        require(assignments==baseline_parameters, 'Baseline must use the qualified initial widths')
        cfg = suite.definition['classes'][name]
        structure = Path(next(p for p in suite.files if p.endswith(cfg['netlist']))).read_text()
        builder = getattr(profile,'build_deck',build_deck)
        expected = builder(structure,bindings['model_file'],condition.corner.model_section,
                           temperature_c=condition.corner.temperature_c)
        deck = job/getattr(profile,'deck_name','opamp.scs')
        require(deck.read_text()==expected and file_digest(deck)==bridge['executed_sha256']==result['netlist_sha256'],
                'Qualified baseline deck differs from current numerical/physical policy')
        settings = getattr(profile,'analysis_settings',None)
        require(bridge.get('analysis_settings')==settings and measured.get('analysis_settings')==settings,
                'Qualified baseline analysis settings differ')
        for specs in cfg['specs'].values():
            evaluation = SpecificationEvaluator(MetricSpec(**s) for s in specs).evaluate(
                measured['metrics'],measured['metric_units'],measured['metric_validity'])
            require(evaluation.valid, 'Baseline is missing a required physical metric')
        references[name]=dict(measurements=str(measured_path),metrics=measured['metrics'],
            metric_units=measured['metric_units'],metric_validity=measured['metric_validity'],
            deck_sha256=file_digest(deck),analysis_settings=settings,
            graph_sha256=json_digest(graph_contract(profile.optimization_graph())),
            condition=asdict(condition),baseline_used_for_learning=False)
        for p in (receipt_path,measured_path,job/'result.json',job/'bridge_result.json',deck):
            files[str(p)] = file_digest(p)
    return references,files


def build_plan(root, manifest, bindings_path):
    suite = load_physical_categories(root,manifest)
    budget = suite_budget(suite)  # Reject the global cap before even reading run bindings.
    bindings_path = Path(bindings_path).resolve()
    bindings = read(bindings_path)
    references,files = bind_references(suite,bindings)
    files.update(suite.files)
    files[str(bindings_path)] = file_digest(bindings_path)
    entry = Path(root).resolve()/'examples/benchmark_real_cross_category.py'
    files[str(entry)] = file_digest(entry)
    settings = dict(suite.definition['settings'],spec_schema=asdict(suite.schema))
    models, methods, validation = benchmark_models(settings)
    plan = dict(version='m6-real-category-suite-v1',origin='real',
        manifest_path=str(Path(manifest).resolve()),bindings_path=str(bindings_path),
        definition=suite.definition,settings=settings,budget=budget,references=references,
        bindings=bindings,files=files,source_sha256=source_digest(),
        dependencies={name:importlib.metadata.version(name) for name in ('torch','torch-geometric','numpy','networkx')},
        feature_schema=asdict(FeatureSchema()),sac_config=asdict(SACConfig()),
        models={name:asdict(model) for name,model in models.items()},methods=list(methods),
        validation_models=list(validation),
        folds={name:[asdict(t) for t in suite.tasks(name)] for name in suite.definition['heldout']},
        policy=dict(source_order='alphabetic class order, sequential episodes',
            source_replay='fresh per fold/encoder/seed; shared across its two source tasks',
            validation='frozen diagnostic only; no hyperparameter or task selection',
            adaptation='copy same-architecture weights and alpha; fresh optimizers and replay per target',
            frozen='deterministic mean policy, measured reset and online queries, zero weight updates',
            normalizer='fixed registry references, no data fitting',stop_on_success=False,
            warmup_random_transitions=1,updates_per_eligible_step=1,
            prior_data='qualification only, no saved transitions/checkpoints imported',
            cross_fold_selection=False,blind_category_test=False))
    plan['sha256']=json_digest(plan)
    # Canonical JSON types make a freshly built plan equal to its saved form.
    return suite,json.loads(json.dumps(plan,allow_nan=False))


def freeze_plan(path, plan):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(plan,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')


def validate_frozen_plan(root, path):
    saved = read(path)
    payload = {k:v for k,v in saved.items() if k!='sha256'}
    require(saved.get('sha256')==json_digest(payload), 'Frozen plan digest mismatch')
    suite,current = build_plan(root,saved['manifest_path'],saved['bindings_path'])
    require(current==saved, 'Frozen plan no longer matches code, definitions, dependencies or qualification evidence')
    return suite,saved


@dataclass
class PhysicalFactory:
    """Gate every requested task against the frozen definitions before native work."""
    suite: PhysicalCategories
    delegate: object
    parallel_safe: bool = False

    def __post_init__(self):
        self._expected = {t.id:json_digest(asdict(t)) for heldout in self.suite.definition['heldout']
                          for t in self.suite.tasks(heldout)}

    def __call__(self, task, steps, output):
        return self.create_recorded(task,steps,output,None)

    def create_recorded(self, task, steps, output, recorder):
        require(json_digest(asdict(task))==self._expected.get(task.id),
                'Task differs from frozen physical definition')
        expected_steps = {'train':self.suite.definition['settings']['pretrain_steps'],
                          'validation':1,'test':self.suite.definition['settings']['test_steps']}[task.partition]
        require(steps==expected_steps, 'Episode steps differ from frozen budget')
        return self.delegate.create_recorded(task,steps,output,recorder)
