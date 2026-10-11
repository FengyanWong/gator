"""The second build of the network inputs (record 7.317): the testbench's sources on their own scales, net tags by one
rule, the operating-point ratios, and offline pools that take runs with operating points. What the rule reads is checked
on a hand-built bench (no netlist, no PDK); the run, the model's contract and the pool on the MOCK backend only."""
from dataclasses import asdict
import hashlib
import json
from types import SimpleNamespace

import pytest

from analog_optimizer.graph.circuit_graph import CircuitGraph, Connection, Device, Net, ParameterBinding, ParameterGroup, ParameterValue, SourceSpan
from gator_workbench import checkpoints, compile as compile_mod, network_inputs, pretrain, runs, spec_descriptors, tasks
from gator_workbench.schema import _hashed, config_hash
from gator_workbench.storage.atomic import read_json
from gator_workbench.validation import validate
from helpers import execute, make_config

pytestmark = pytest.mark.xdist_group('test_wb_inputs_second_build')
SECOND = dict(bench_features='relative', net_roles='rule', operating_point_ratios=True)
SPAN = SourceSpan('test', 1)
NUMBERS = dict(g45n1svt=dict(lmin=45e-9, wmin=120e-9, basis='model bin', vth0=0.42, u0=0.03, vsat=1.1e5, tox=2.1e-9),
               g45p1svt=dict(lmin=45e-9, wmin=120e-9, basis='model bin', vth0=-0.41, u0=0.009, vsat=8e4, tox=2.2e-9))
POINTS = {'DUT/M1': dict(ids=1e-4, gm=1e-3, gds=1e-5, vgs=0.6, vds=0.9, vth=0.4, vdsat=0.15, region=2),
          'DUT/M2': dict(ids=-1e-4, gm=5e-4, gds=0.0, vgs=-0.7, vth=-0.45),          # no gds worth dividing by, no vds
          'CL': dict(ids=1.0, gm=1.0)}                                                  # not a transistor: ignored


def with_network(network):
    def mutate(raw):
        raw['run']['network'].update(network)
    return mutate


def number(value):
    return ParameterValue(repr(value), value, SPAN)


def text(raw):
    """A parameter the netlist gives as a word: a waveform type, or the name of a test variable."""
    return ParameterValue(raw, None, SPAN, reason='not a number')


def bench_graph():
    """A two-transistor circuit in a testbench as a Maestro task holds one: the circuit's devices under DUT/, the
    sources and the load at the top level. RN_SRC stands at the supply's own voltage and comes first, so only the rule's
    count of pins tells the two apart."""
    devices, connections, parameters = [], [], {}

    def add(name, kind, model, nets, **values):
        terminals = ('d', 'g', 's', 'b') if kind in ('nmos', 'pmos') else ('PLUS', 'MINUS')
        roles = ('drain', 'gate', 'source', 'bulk') if kind in ('nmos', 'pmos') else ('positive', 'negative')
        devices.append(Device(name, kind, model, terminals, SPAN))
        connections.extend(Connection(name, net, terminal, ordinal, role)
                           for ordinal, (net, terminal, role) in enumerate(zip(nets, terminals, roles)))
        parameters[name] = {key: value if isinstance(value, ParameterValue) else number(value) for key, value in values.items()}

    add('DUT/M1', 'nmos', 'g45n1svt', ('VOUT', 'VCM', 'DUT/TAIL', '0'), w=2e-6, l=2e-7)
    add('DUT/M2', 'pmos', 'g45p1svt', ('VOUT', 'IBIAS', 'VDD', 'VDD'), w=4e-6, l=2e-7)
    add('RN_SRC', 'vsource', 'vsource', ('RN', '0'), dc=1.8, type=text('dc'))
    add('VDD_SRC', 'vsource', 'vsource', ('VDD', '0'), dc=1.8, mag=1.0, type=text('dc'))
    add('VCM_SRC', 'vsource', 'vsource', ('VCM', '0'), dc=0.9, type=text('dc'))
    add('VPROBE', 'vsource', 'vsource', ('VOUT', 'VFB'), dc=0.0, type=text('dc'))
    add('IREF', 'isource', 'isource', ('VDD', 'IBIAS'), dc=50e-6, type=text('dc'))
    add('ILOAD', 'isource', 'isource', ('VOUT', '0'), dc=text('il'), type=text('pulse'), val0=10e-6, val1=0.01)
    add('CL', 'capacitor', 'capacitor', ('VOUT', '0'), c=1e-12)
    nets = [Net('VDD'), Net('VOUT'), Net('VCM'), Net('VFB'), Net('IBIAS'), Net('RN'), Net('DUT/TAIL'), Net('0', ('ground',), 'mapping')]
    groups = [ParameterGroup('w_pair', 'w', 'm', 2e-6, 1e-6, 8e-6, (ParameterBinding('DUT/M1', 'w'),))]
    graph = CircuitGraph('bench', devices, nets, connections, parameters, groups)
    graph.validate()
    return graph


def shown(graph, device):
    return {key: value.value for key, value in graph.parameters[device].items() if value.valid}


def test_without_the_second_build_nothing_changes():
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    assert not network_inputs.any_transfer({}) and not network_inputs.second_build(dict(spec_input='set'))
    assert network_inputs.feature_schema(FeatureSchema(), {}) == FeatureSchema()
    first = network_inputs.feature_schema(FeatureSchema(), dict(size_features='pdk_relative', device_model_features=True))
    assert first.version == '1.0+pdk-relative-sizes-v1+device-model-features-v1' and not first.op_columns
    # A view of the first build keeps the key it had before the second build existed (the formula of record 7.298, written
    # out): a run of then still resumes, and its circuit is still shown as its network saw it.
    view = network_inputs.NetworkView(numbers=NUMBERS, relative_sizes=True, model_features=True)
    identity = dict(descriptors=None, numbers=NUMBERS, relative_sizes=True, model_features=True, vocabulary=None)
    assert view.key == hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    assert view.view_graph(bench_graph()).nets == bench_graph().nets            # the task's own tags, untouched
    assert network_inputs.as_recorded(network_inputs.transfer_settings(dict(spec_input='set'))) == dict(
        spec_input='set', size_features='absolute', device_model_features=False)


def test_a_configuration_without_the_second_build_keeps_its_hash(tmp_path):
    config = make_config(tmp_path)
    raw = config.model_dump(mode='json')
    assert {key: raw['run']['network'][key] for key in network_inputs.SECOND_BUILD_DEFAULTS} == network_inputs.SECOND_BUILD_DEFAULTS
    assert not set(network_inputs.SECOND_BUILD_DEFAULTS) & set(_hashed(raw)['run']['network'])      # hashed as absent
    changed = make_config(tmp_path, mutate=with_network(dict(net_roles='rule')))
    assert config_hash(changed) != config_hash(config)
    assert _hashed(changed.model_dump(mode='json'))['run']['network']['net_roles'] == 'rule'


def test_the_bench_is_read_off_the_graph_by_one_rule():
    graph = bench_graph()
    bench = network_inputs.bench_of_graph(graph, dict(il=1e-3))
    assert bench.ground == {'0'}
    # RN_SRC has the same voltage and stands first: the supply is the one whose net feeds more pins.
    assert (bench.supply_source, bench.supply_net, bench.supply_v) == ('VDD_SRC', 'VDD', 1.8)
    by_name = {source.id: source for source in bench.sources}
    assert set(by_name) == {'RN_SRC', 'VDD_SRC', 'VCM_SRC', 'VPROBE', 'IREF', 'ILOAD'}          # nothing from inside the circuit
    assert by_name['VDD_SRC'].signal and by_name['ILOAD'].signal and not by_name['VCM_SRC'].signal
    assert by_name['ILOAD'].dc == 1e-3 and network_inputs.bench_of_graph(graph).sources[-1].dc is None
    assert by_name['VPROBE'].nets == ('VOUT', 'VFB') and not by_name['VPROBE'].grounded
    roles = network_inputs.ruled_roles(graph, bench, ('VOUT', 'NOT_A_NET'))
    assert roles == {'0': ('ground',), 'VDD': ('supply', 'input'), 'VOUT': ('input', 'output'), 'VCM': ('bias',),
                     'IBIAS': ('bias',), 'RN': ('bias',)}                                         # VFB: a 0 V probe tags nothing
    # A task that tags its supply itself is taken at its word, whatever the voltages say.
    tagged = bench_graph()
    tagged.nets[5] = Net('RN', ('supply',), 'mapping')
    assert network_inputs.bench_of_graph(tagged).supply_source == 'RN_SRC'
    assert network_inputs.bench_of_graph(CircuitGraph('none', [], [], [], {})).supply_source is None


def test_the_view_shows_sources_net_tags_and_ratios_and_leaves_the_recorded_graph_alone():
    from analog_optimizer.graph.pyg_converter import FeatureSchema, OPERATING_POINT_COLUMNS, to_pyg
    graph = bench_graph()
    view = network_inputs.NetworkView(bench_features=True, net_rule=True, op_ratios=True, measured_nets=('VOUT',),
                                      variables=dict(il=1e-3))               # as the netlist writes it (record 7.319)
    seen = view.view_graph(graph, POINTS)
    seen.validate()
    assert view.view_graph(seen, POINTS) is seen                                  # never viewed twice
    assert shown(seen, 'IREF') == dict(idc=50e-6)                                  # amperes left the column of volts
    # dc=il is read from the test's variables; the netlist's own val0 / val1 stay (no column of the network reads them)
    assert shown(seen, 'ILOAD') == dict(idc=1e-3, ilow=10e-6, ihigh=0.01, val0=10e-6, val1=0.01)
    assert shown(seen, 'VDD_SRC') == dict(dc=1.8, mag=1.0, ac=1.0, vrel=1.0)
    assert shown(seen, 'VCM_SRC') == dict(dc=0.9, vrel=0.5) and shown(seen, 'VPROBE') == dict(dc=0.0, vrel=0.0)
    assert shown(seen, 'CL') == dict(c=1e-12)
    assert {net.id: net.roles for net in seen.nets} == {
        'VDD': ('supply', 'input'), 'VOUT': ('input', 'output'), 'VCM': ('bias',), 'VFB': ('normal',), 'IBIAS': ('bias',),
        'RN': ('bias',), 'DUT/TAIL': ('normal',), '0': ('ground',)}
    first, second = shown(seen, 'DUT/M1'), shown(seen, 'DUT/M2')
    assert (first['op_gm_id'], first['op_gain'], first['op_sat']) == pytest.approx((10.0, 100.0, 6.0))
    assert first['op_vov'] == pytest.approx(0.2) and second['op_vov'] == pytest.approx(0.25) and second['op_gm_id'] == pytest.approx(5.0)
    assert 'op_gain' not in second and 'op_sat' not in second                       # missing numbers stay missing
    assert not any(key.startswith('op_') for key in shown(seen, 'CL'))
    assert not any(key.startswith('op_') for values in view.view_graph(graph).parameters.values() for key in values)   # no simulation yet
    # the recorded graph is what the simulator saw
    assert shown(graph, 'IREF') == dict(dc=50e-6) and graph.nets == bench_graph().nets and 'op_gm_id' not in graph.parameters['DUT/M1']
    schema = network_inputs.feature_schema(FeatureSchema(), SECOND)
    assert schema.version == '1.0+bench-features-v1+net-roles-by-rule-v1+op-ratios-v1'
    assert schema.parameters[-11:] == network_inputs.BENCH_COLUMNS + network_inputs.RATIO_COLUMNS
    assert schema.op_columns == network_inputs.REGION_COLUMNS and set(schema.op_columns) < set(OPERATING_POINT_COLUMNS)
    data = to_pyg(seen, schema, operating_points=POINTS)
    row = {device.id: i for i, device in enumerate(seen.devices)}
    column = schema.parameters.index
    import math
    assert float(data['device'].x[row['IREF'], column('idc')]) == pytest.approx(math.log1p(50.0))      # 50 uA, no longer 0.00005
    assert float(data['device'].x[row['IREF'], column('dc')]) == 0 and not bool(data['device'].parameter_present[row['IREF'], column('dc')])
    assert float(data['device'].x[row['VCM_SRC'], column('vrel')]) == pytest.approx(math.log1p(0.5))
    flags = data['device'].op[row['DUT/M1']].tolist()                             # its region, one of five
    assert [flag > 0 for flag in flags] == [name == 'region_sat' for name in schema.op_columns]
    # with the raw operating points on as well, the network keeps all twelve of their columns
    from dataclasses import replace
    raw = replace(FeatureSchema(), op_columns=OPERATING_POINT_COLUMNS, op_references=(1.0,) * len(OPERATING_POINT_COLUMNS))
    assert network_inputs.feature_schema(raw, SECOND).op_columns == OPERATING_POINT_COLUMNS


def test_a_row_that_varies_a_source_keeps_its_value_where_the_row_expects_it():
    graph = bench_graph()
    graph.parameter_groups.append(ParameterGroup('vcm', 'dc', 'V', 0.9, 0.5, 1.2, (ParameterBinding('VCM_SRC', 'dc'),)))
    graph.validate()
    seen = network_inputs.NetworkView(bench_features=True).view_graph(graph)
    seen.validate()
    assert shown(seen, 'VCM_SRC') == dict(dc=0.9, vrel=0.5)


def test_the_nets_the_active_specs_read_and_the_variables_of_a_test():
    probe = lambda name, signal, source='expression': SimpleNamespace(measurement_id=name, signal=signal, result_source=source)  # noqa: E731
    spec = lambda equation, active=True: SimpleNamespace(equation=equation, active=active)                                      # noqa: E731
    config = SimpleNamespace(
        measurements=[probe('gain', 'value(dB20(VF("/VOUT")) 1)'), probe('swing', 'ymax(VT("/DUT/X"))'), probe('low', 'ymin(VT("/VOUT"))'),
                      probe('pm', 'phaseMargin(getData("loopGain" ?result "stb"))'), probe('unused', 'VF("/VFB")'),
                      probe('area', 'fingers("mn*", 400n)', 'size_estimate'), probe('iq', 'IDC("/VDD_SRC/PLUS")')],
        targets=[spec('gain'), spec('swing - low'), spec('pm'), spec('unused', active=False), spec('area'), spec('iq')])
    assert spec_descriptors.measured_nets(config) == ('DUT/X', 'VOUT')
    deck = dict(head='simulator lang=spectre\nparameters temperature=27 il=1m vin=900m name=other\n',
                tail='dc dc param=vin start=0 stop=1\nac ac start=1 stop=1G\n')
    assert network_inputs.variables_of_deck(deck) == dict(temperature=27.0, il=1e-3)      # vin is swept; "other" is no number
    assert network_inputs.variables_of_deck(None) == {} and network_inputs.variables_of_deck(dict(head=3)) == {}


@pytest.fixture(scope='module')
def second_run(tmp_path_factory):
    root = tmp_path_factory.mktemp('second-build')
    layout, state = execute(make_config(root, run=dict(max_evaluations=24), mutate=with_network(SECOND),
                                        advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
    assert state == 'completed'
    return layout


def test_a_run_with_the_second_build_trains_and_its_model_loads_only_with_it(second_run, tmp_path):
    record = read_json(second_run.run_dir / network_inputs.RUN_FILE)
    assert {key: record[key] for key in SECOND} == SECOND and 'measured_nets' in record['second_build'] and record['view_key']
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(second_run.run_dir, 'latest'))
    features = meta['contract']['feature_schema']
    assert features['version'].endswith('+bench-features-v1+net-roles-by-rule-v1+op-ratios-v1')
    assert tuple(features['op_columns']) == network_inputs.REGION_COLUMNS
    from gator_workbench.vocabulary import schema_label
    assert schema_label(features).endswith('bench sources on their own scales, net tags by rule, operating-point ratios')
    for network, expected in ((SECOND, True), ({}, False), (dict(SECOND, operating_point_ratios=False), False)):
        config = make_config(tmp_path, mutate=with_network(network))
        loaded = tasks.load_task(config.circuit)
        compiled = compile_mod.compile_task(config, loaded.base_graph)
        contract = runs.learner_contract(config, loaded, 'h' * 64, compiled.spec_schema, None)
        report = checkpoints.check_compatibility(meta, mode='fine_tune', contract=contract, task_definition_hash='h' * 64)
        assert report['compatible'] is expected, report
        if not expected:
            assert {c['component'] for c in report['checks'] if c['status'] == 'incompatible'} == {
                'graph feature schema (components the network knows)'}


def test_the_checks_say_what_the_rule_reads_on_the_task(tmp_path):
    config = make_config(tmp_path, mutate=with_network(SECOND))
    report = validate(config, graph=tasks.load_task(config.circuit).base_graph)
    assert not [i for i in report.issues if i.level in ('blocker', 'error')], report.issues
    codes = {i.code: i for i in report.issues}
    assert {'bench_features_relative', 'net_roles_by_rule', 'operating_point_ratios'} <= set(codes)
    assert codes['net_roles_by_rule'].path == 'run.network.net_roles' and 'ground' in codes['net_roles_by_rule'].message
    plain = validate(make_config(tmp_path), graph=tasks.load_task(config.circuit).base_graph)
    assert not {'bench_features_relative', 'net_roles_by_rule', 'operating_point_ratios'} & {i.code for i in plain.issues}


def test_an_offline_pool_takes_the_second_build_and_runs_with_operating_points(second_run, tmp_path):
    plain, state = execute(make_config(tmp_path, run=dict(max_evaluations=24),
                                       advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), tmp_path)
    assert state == 'completed'

    def request(sources, **extra):
        return dict(origin='synthetic', seed=7, holdout_fraction=0.2,
                    runs=[dict(run_dir=str(s.run_dir), archive_sha256=pretrain.archive_identity(s.run_dir)) for s in sources],
                    updates=3, batch_size=3, checkpoint_every=2, model=dict(hidden_dim=16, heads=2, layers=1),
                    sac=dict(gamma=0., learning_rate=1e-3, initial_alpha=0.01), **extra)

    # A pool without the second build records its inputs as it always did, and now takes a run that read operating points.
    pool = pretrain.prepare_pool(request([second_run]))
    assert set(pool.audit['inputs']) == {'spec_input', 'size_features', 'device_model_features', 'vocabulary'}
    assert pool.audit['sources'][0]['operating_points'] is True and not pool.feature_schema.op_columns
    # The ratios need runs that read operating points: one that did not is refused in words, or masked on request.
    with pytest.raises(ValueError, match='read no operating points'):
        pretrain.prepare_pool(request([plain], inputs=SECOND))
    with pytest.raises(ValueError, match='missing_operating_points must be one of'):
        pretrain.prepare_pool(request([plain], inputs=SECOND, missing_operating_points='guess'))
    masked = pretrain.prepare_pool(request([plain], inputs=SECOND, missing_operating_points='mask'))
    assert 'operating_points' not in masked.audit['sources'][0]
    pool = pretrain.prepare_pool(request([second_run], inputs=SECOND))
    assert {key: pool.audit['inputs'][key] for key in SECOND} == SECOND
    assert pool.feature_schema.version.endswith('+op-ratios-v1') and pool.feature_schema.op_columns == network_inputs.REGION_COLUMNS
    for transitions in pool.training.values():
        assert all(t.observation.graph.metadata.get(network_inputs.VIEW_KEY) for t in transitions)
    audit = pretrain.execute(request([second_run], inputs=SECOND), tmp_path / 'mock' / 'offline')
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(tmp_path / 'mock' / 'offline', 'latest'))
    assert meta['contract']['feature_schema'] == json.loads(json.dumps(audit['feature_schema']))
    assert asdict(pool.feature_schema) == audit['feature_schema'] or json.loads(json.dumps(asdict(pool.feature_schema))) == audit['feature_schema']
