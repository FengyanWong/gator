"""Calibration safety contracts; independent evaluator subprocesses are faked here."""
import importlib.util
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from analog_optimizer.backends.backend import SimulationStatus
from gator_workbench import tasks
from gator_workbench.analoggym import native_values, validate_benchmark_config
from gator_workbench.compile import compile_task
from gator_workbench.storage.atomic import write_json
from helpers import make_config


@pytest.fixture
def calibration(monkeypatch):
    examples = Path(__file__).resolve().parents[2] / 'examples'
    monkeypatch.syspath_prepend(str(examples))
    spec = importlib.util.spec_from_file_location('calibration_under_test', examples / 'calibrate_analoggym.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_bias_is_not_overridden_by_an_extra_assignment():
    bundle = dict(leaders={'I_bias':dict(device='I1',parameter='dc',physical_per_native=1),
                          'W_M1':dict(device='M1',parameter='w',physical_per_native=1e-6)},
                  fixed_native_values={'I_bias':20e-6})
    assert native_values(bundle, {('M1','w'):2e-6}) == {'I_bias':20e-6,'W_M1':2.0}
    with pytest.raises(ValueError, match='fixed at'):
        native_values(bundle, {('M1','w'):2e-6,('I1','dc'):30e-6})


@pytest.mark.parametrize('method',['sac','llm_warmstart','llm','sac_llm_rescue'])
def test_benchmark_domain_and_scoring_checks_apply_to_every_mode(tmp_path,method):
    config=make_config(tmp_path)
    config.run.search.method=method
    bundle=dict(native_initial={'I_bias':20e-6},fixed_native_values={'I_bias':20e-6},
                metric_units={'score':'fixture'},scoring='feasibility_only')
    validate_benchmark_config(config,bundle)
    config.targets[0].direction_after_feasible='maximize'
    with pytest.raises(ValueError,match='descriptive only'):
        validate_benchmark_config(config,bundle)
    config.targets[0].direction_after_feasible='none'
    config.parameters[0].unit='uA'
    with pytest.raises(ValueError,match='every arm'):
        validate_benchmark_config(config,bundle)
    config.parameters[0].unit='um'
    config.measurements=[]
    with pytest.raises(ValueError,match='Every benchmark metric'):
        validate_benchmark_config(config,bundle)


def test_comparison_reports_best_feasible_probe_rows(tmp_path,monkeypatch):
    examples=Path(__file__).resolve().parents[2]/'examples'
    monkeypatch.syspath_prepend(str(examples))
    from benchmark_llm_sizing import run_arm
    config=make_config(tmp_path,threshold=0.,run=dict(max_evaluations=3))
    result=run_arm(config,'sac',tmp_path/'comparison')
    best=result['best_feasible_probes']
    assert result['state']=='completed' and result['llm_calls']==0
    assert best['metrics_descriptive_only'] is True
    assert best['evaluation_id']==result['summary']['best_feasible_evaluation_id']
    assert any(row['measurement_id']=='m_score' and row['valid'] for row in best['rows'])


def test_comparison_accepts_imported_starter_without_run_settings(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'examples'))
    import benchmark_llm_sizing as driver
    from gator_workbench import ngspice_tasks
    config=make_config(tmp_path)
    data=config.model_dump(mode='json')
    starter={k:data[k] for k in ('project','circuit','parameters','measurements','targets')}
    bundle=dict(native_initial={},fixed_native_values={},metric_units={'score':'fixture'},scoring='feasibility_only')
    monkeypatch.setattr(driver.tasks,'load_task',lambda *args,**kwargs:SimpleNamespace(
        mock=False,connection_family='ngspice',circuit={'analoggym_task':True}))
    monkeypatch.setattr(ngspice_tasks,'load',lambda *args:(dict(starter=starter,analoggym=bundle),''))
    def intercepted(*args,**kwargs):
        raise StopIteration('Preparation reached; no simulation')
    monkeypatch.setattr(driver.runs,'prepare_run',intercepted)
    with pytest.raises(StopIteration,match='Preparation reached'):
        driver.run_arm(config,'sac',tmp_path/'comparison',authorize_ngspice=True)


@pytest.mark.parametrize('parameter',['mf','mult'])
def test_native_count_parameters_enter_sac_without_changing_default_schema(tmp_path,parameter):
    from analog_optimizer.envs.sizing import Observation
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    from analog_optimizer.models.inputs import batch_observations
    from gator_workbench.modes import runtime_options
    from gator_workbench.validation import Report, _check_parameters
    from gator_workbench.ngspice_netlist import parse_text
    from gator_workbench.schema import WorkbenchConfig
    config=make_config(tmp_path)
    assert runtime_options(config)['feature_schema']==FeatureSchema()
    data=config.model_dump(mode='json')
    data['circuit']['task_id']='ngspice:count_fixture'
    data['parameters']=[dict(variable_id='count',instance_path='X1',parameter_name='m',unit='count',
                            lower=1,upper=4,value_type='integer',optimized=True),
                        dict(variable_id='native_count',instance_path='X1',parameter_name=parameter,unit='count',
                            lower=1,upper=4,value_type='integer',optimized=True,binding_group='count')]
    config=WorkbenchConfig.model_validate(data)
    report=Report()
    _check_parameters(config,report,None,None)
    assert not any(i.code in ('parameter_kind_unsupported','mixed_parameter_kind_group') for i in report.issues)
    graph=parse_text(f'Count fixture\nX1 out 0 countcap m=2 {parameter}=2\n.end\n',
                     device_kinds={'countcap':'capacitor'},scan_includes=False).graph
    compiled=compile_task(config,graph)
    schema=runtime_options(config)['feature_schema']
    assert schema.parameters==FeatureSchema().parameters+(parameter,)
    assert schema.references[-1]==1. and 'current' not in schema.parameters
    observation=Observation(compiled.graph,compiled.specs,{'score':1.},{'score':True},{'score':'fixture'},
                            'ok','synthetic',5,'count-fixture')
    batch_observations([observation],schema,compiled.spec_schema)


@pytest.mark.parametrize('actual,expected,equal', [(1+5e-10,1,True),(1+2e-9,1,False),
    (1e-18,0,False),(0,0,True),(None,None,True),(None,1,False)])
def test_parity_uses_relative_tolerance_without_absolute_floor(calibration,actual,expected,equal):
    assert (not calibration.metric_differences({'value':expected},{'value':actual})) == equal


@pytest.mark.parametrize('passes,value,valid', [(True,1.,True),(False,1.,False),(True,1.0001,False)])
def test_independent_verification_checks_values_and_verdict(calibration,tmp_path,monkeypatch,passes,value,valid):
    commands=[]
    monkeypatch.setattr(calibration,'original_deck',lambda *args:'* Original testbench fixture\n.end')
    monkeypatch.setattr(calibration.subprocess,'run',lambda command,**kwargs:commands.append(command) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(calibration,'evaluate_outputs',lambda *args:({'FOML':value},passes,{}))
    result=calibration.verify_pass({}, {}, {'FOML':1.}, tmp_path/'verification')
    assert result['passed'] == valid
    assert result['simulator_processes'] == len(commands) == 2
    assert commands[0][-1]=='ACDC.cir' and commands[1][-1]=='Tran.cir'


@pytest.mark.parametrize('independent_pass',[False,True])
def test_every_passing_design_is_rechecked_and_disagreement_stops_all(calibration,tmp_path,monkeypatch,independent_pass):
    config=make_config(tmp_path)
    graph=tasks.load_task(config.circuit).base_graph
    bundle=dict(name='fixture',fixed_native_values={},metric_units={'score':'fixture'},native_initial={},scoring='feasibility_only')
    directory=tmp_path/'task'; directory.mkdir()
    write_json(directory/'task.json',dict(analoggym=bundle,device_kinds={}))
    write_json(directory/'config.json',config.model_dump(mode='json'))
    (directory/'netlist.cir').write_text('* Fixture only')
    monkeypatch.setattr(calibration,'parse_entry',lambda *args:SimpleNamespace(graph=graph))
    # The fixture's backend returns a passing, finite, valid score every time.
    class Backend:
        def __init__(self,*args,**kwargs):
            self.parameters={}; self.count=0
        def connect(self): pass
        def close(self): pass
        def set_parameters(self, values): self.parameters=values
        def native_values(self): return {'W':1.}
        def generate_netlist(self,root):
            root.mkdir(parents=True)
            return SimpleNamespace(path=root/'deck.cir',condition=None)
        def get_circuit_graph(self,artifact): return graph
        def run_simulation(self,request):
            self.count+=1
            write_json(request.work_root/'benchmark.json',dict(native_metrics={'score':1.},upstream_passed=True))
            write_json(request.work_root/'analysis-counts.json',dict(analyses=1,commands={'op':1},complete=True))
            return SimpleNamespace(status=SimulationStatus.OK,condition=None,job_id=str(self.count),
                candidate_evaluated=True,simulator_invocations=1,artifact_directory=request.work_root,
                metrics={'score':1.},metric_units={'score':'fixture'},metric_validity={'score':True})
    monkeypatch.setattr(calibration,'AnalogGymBackend',Backend)
    checked=[]
    def verify(*args,**kwargs):
        checked.append(args[1])
        return dict(passed=independent_pass,simulator_processes=2,differences=[] if independent_pass else ['verdict'])
    monkeypatch.setattr(calibration,'verify_pass',verify)
    stop=Event()
    result=calibration.run_calibration(directory,tmp_path/'output',tmp_path/'scratch','random',1,3,stop)
    assert len(checked)==len(result['designs'])==(3 if independent_pass else 1)
    assert stop.is_set() == (not independent_pass)
    assert result['completed'] == independent_pass
    assert result['verified_passes']==(3 if independent_pass else 0)
    assert result['verification_processes']==2*len(checked)
    if independent_pass:
        assert result['best_feasible']['probes']=={'score':1.}
        assert result['best_feasible']['index']==0
        uninterrupted = list(result['designs'])
        result.update(completed=False, designs=result['designs'][:1], simulator_processes=1,
                      verification_processes=2, passing_designs=1, verified_passes=1)
        write_json(tmp_path/'output'/result['run_id']/'result.json',result)
        checked.clear()
        resumed=calibration.run_calibration(directory,tmp_path/'output',tmp_path/'scratch-resumed',
            'random',1,3,Event(),resume=True)
        assert resumed['completed'] and len(checked)==2
        assert [d['proposal'] for d in resumed['designs']]==[d['proposal'] for d in uninterrupted]
        assert resumed['verified_passes']==3 and resumed['simulator_processes']==3
    else:
        with pytest.raises(ValueError,match='Cannot resume after'):
            calibration.run_calibration(directory,tmp_path/'output',tmp_path/'scratch-resumed',
                'random',1,3,Event(),resume=True)

