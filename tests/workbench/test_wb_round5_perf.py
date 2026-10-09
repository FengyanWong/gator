"""Round 5 of the repository review (2026-09-29). A7: the top of a range typed in decimals is a legal value again - in a
MOCK run and in a generated profile - without touching src/analog_optimizer. B4, B6, B7, B9 and D: speed-ups and a
cleanup, each proved behaviour-identical before/after outside the suite; these tests pin what they save. MOCK only."""
import importlib.util
import json
import math
import random
import sys
import time
from pathlib import Path

import pytest

from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
from analog_optimizer.netlist.config import DeviceMapping, ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser
from analog_optimizer.parameters.actions import ActionMapper
from gator_workbench import compile as comp, engine as engine_module, graph_view, pdk, schema, structures, task_registry, tasks, units, validation
from gator_workbench.generic_profile import RULES_FORMAT, GenericMosWidthProfile
from helpers import bridge_is_importable, execute, make_config, rows  # noqa: F401 - autouse here: the bridge counts as installed

REPO = Path(__file__).resolve().parents[2]
# A width range as a user types it: 1.84 .. 42.38 um in 0.02 um steps. The optimizer's top grid point, lower + n*step,
# is 4.2380000000000004e-05 m - a hair above 42.38 um (4.238e-05). OTA5's input pair is 4 um wide: on that grid.
TYPED = dict(unit='um', lower=1.84, upper=42.38, step=0.02)
TOP = 4.2380000000000004e-05


def decimal_range(raw):
    next(r for r in raw['parameters'] if r['variable_id'] == 'input_pair_width').update(TYPED)


# ------------------------------------------------------------------------------ A7: the top of a decimal range
def test_the_optimizers_top_grid_point_is_the_compiled_upper_bound_and_nothing_else_moves(tmp_path):
    config = make_config(tmp_path, mutate=decimal_range)
    base = tasks.load_task(config.circuit).base_graph
    compiled = comp.compile_task(config, base)
    group = next(g for g in compiled.graph.parameter_groups if g.id == 'input_pair_width')
    typed = units.to_canonical(42.38, 'um')
    assert typed == 4.238e-05 and group.upper == TOP > typed
    assert group.project(1.0) == TOP                          # its top value is legal now: the group accepts it as its value
    ParameterGroup(group.id, group.parameter_kind, group.unit, TOP, group.lower, group.upper, group.members,
                   step=group.step).validate()
    assert next(v for v in compiled.variables if v['variable_id'] == 'input_pair_width')['upper'] == TOP
    # every other grid point is the one the typed bound gave
    before = ParameterGroup('g', 'w', 'm', group.value, group.lower, typed, (ParameterBinding('M1', 'w'),), step=group.step)
    for k in range(0, 2027, 7):
        value = group.lower + k * group.step
        assert group.project(value) == before.project(value)
    # a range whose top point is not above its bound compiles to exactly what was typed (bitwise)
    plain = comp.compile_task(make_config(tmp_path), base)
    assert [(g.lower, g.upper, g.step) for g in plain.graph.parameter_groups] == [
        (1e-06, 1e-05, None), (2e-06, 2e-05, None), (1e-06, 1e-05, None)]


def test_a_followers_own_clamp_at_the_leaders_range_moves_with_the_top_point(tmp_path):
    def clamp_follower(raw):
        decimal_range(raw)
        follower = next(r for r in raw['parameters'] if r.get('binding_group') == 'input_pair_width')
        follower.update(unit='um', lower=1.84, upper=42.38)        # its own clamp: the same range
    config = make_config(tmp_path, mutate=clamp_follower)
    compiled = comp.compile_task(config, tasks.load_task(config.circuit).base_graph)
    group = next(g for g in compiled.graph.parameter_groups if g.id == 'input_pair_width')
    follower = group.members[1]
    assert group.upper == TOP and follower.upper == TOP and follower.lower == 1.84e-06


def test_grid_top_is_the_top_that_project_reaches_on_thousands_of_typed_ranges():
    rng = random.Random(5)
    moved = 0
    for _ in range(20000):
        step_um = rng.choice([0.005, 0.01, 0.02, 0.05, 0.1, 0.12, 0.2])
        low_um = round(rng.randrange(1, 200) * step_um, 6)
        high_um = round(low_um + rng.randrange(1, 3000) * step_um, 6)
        lower, upper, step = (units.to_canonical(low_um, 'um'), units.to_canonical(high_um, 'um'),
                              units.scale_to_canonical(step_um, 'um'))
        typed = ParameterGroup('g', 'w', 'm', lower, lower, upper, (ParameterBinding('M', 'w'),), step=step)
        top = comp.grid_top(lower, upper, step)
        grid = lower + math.floor((upper - lower) / step + 1e-12) * step       # the optimizer's own top grid point
        if grid <= upper:
            assert top is upper                                  # untouched: the very float that was typed
            continue
        moved += 1
        assert top == grid
        assert typed.project(upper) == upper                     # the package clamps since the round-5 optimizer step
        snapped = ParameterGroup('g', 'w', 'm', lower, lower, top, (ParameterBinding('M', 'w'),), step=step)
        assert snapped.project(top) == top and snapped.project(upper) == top
        for value in (lower, (lower + upper) / 2, upper - step):
            assert snapped.project(value) == typed.project(value)
    assert 3000 < moved < 10000                                   # about a quarter of such ranges overshoot


class _AlwaysTop(random.Random):
    """Every random warm-up proposal at the top of its range (z = +1)."""
    def uniform(self, a, b):
        return b


def test_a_mock_run_that_always_proposes_the_top_of_a_decimal_range_evaluates_every_candidate(tmp_path, monkeypatch):
    # Before: each such candidate failed "invalid bounds/current value" in the optimizer's own group check (an
    # execution_error), and the first one ended the run.
    prepare = engine_module.RunEngine._prepare

    def always_top(self):
        prepare(self)
        self.rng = _AlwaysTop(0)
    monkeypatch.setattr(engine_module.RunEngine, '_prepare', always_top)
    config = make_config(tmp_path, run=dict(max_evaluations=9), advanced=dict(warmup_transitions=50), mutate=decimal_range)
    layout, state = execute(config, tmp_path)
    evaluations = rows(layout, 'evaluations', ['evaluation_id', 'action_source', 'status', 'valid', 'failure_type'])
    steps = [e for e in evaluations if e['action_source'] == 'random_warmup']
    assert state == 'completed' and len(evaluations) == 9 and len(steps) == 6, evaluations
    assert all(e['status'] == 'ok' and e['valid'] for e in evaluations), evaluations
    executed = {(r['evaluation_id'], r['instance_path']): (r['executed_value'], r['upper'], r['raw_policy_action'])
                for r in rows(layout, 'parameters', ['evaluation_id', 'instance_path', 'executed_value', 'upper', 'raw_policy_action'])}
    for e in steps:
        for device in ('XU1/M1', 'XU1/M2'):                       # the leader and its follower, both at the top point
            assert executed[e['evaluation_id'], device] == (TOP, TOP, 1.0)


def _ota5_profile(tmp_path, lower, upper, step):
    """A generated (rules file) profile of the verified OTA5 with the input pair varied over [lower, upper] in `step`."""
    info = tasks.REAL_PROFILES['gpdk045_ota5']
    mapping = json.loads((REPO / info['mapping']).read_text())
    for group in mapping['parameter_groups']:
        group.update(dict(lower=lower, upper=upper, scale='linear', step=step, mutable=True) if group['id'] == 'input_pair_width'
                     else dict(mutable=False))
    (tmp_path / 'mapping.json').write_text(json.dumps(mapping))
    reference = json.loads((REPO / info['readback']).read_text())
    mos = [f'M{i}' for i in range(1, 6)]
    (tmp_path / 'rules.json').write_text(json.dumps(dict(
        format=RULES_FORMAT, recipe='opamp_ac', core_instance='XU1', width_step=5e-9, mos_instances=mos,
        fixed_instances=[i['name'] for i in reference['instances'] if i['name'] not in mos],
        writable=[dict(instance=name, lower=lower, upper=upper) for name in ('M1', 'M2')])))
    return GenericMosWidthProfile(rules_file=tmp_path / 'rules.json', design_file=REPO / info['design'],
                                  mapping_file=tmp_path / 'mapping.json', reference_structure=REPO / info['structure'],
                                  reference_readback=REPO / info['readback'],
                                  conditions_file=REPO / 'configs/gpdk045_conditions.json')


def test_a_generated_profile_whose_range_was_typed_in_decimals_loads_and_accepts_its_top_value(tmp_path):
    # Before: refused at load with "Width of XU1/M1 outside its bounds or off the CDF-compatible grid" - its own check of
    # the corners of the action space met the top grid point, a hair above the rules' upper bound.
    profile = _ota5_profile(tmp_path, 1.84e-06, 4.238e-05, 2e-08)
    graph = profile.optimization_graph()
    top = ActionMapper(graph).legalize({'input_pair_width': 1.0}).assignments
    assert set(top.values()) == {TOP}
    profile.validate_assignment(top)
    assert profile.bounds == {'XU1/M1': (1.84e-06, TOP), 'XU1/M2': (1.84e-06, TOP)}
    with pytest.raises(ValueError, match='outside its bounds'):          # one grid step above the top stays refused
        profile.validate_assignment({key: TOP + 2e-08 for key in top})
    # Its mapping holds the typed bound (saved before compile took the top point). The rows saved with it still match what
    # a run gets - the check at Start (tasks._generated_runtime) - and so does the graph of an exported netlist.
    from analog_optimizer.envs.sizing import graph_contract
    rows = [schema.OptimizationParameter.model_validate(r) for r in tasks._graph_parameter_rows(profile.graph)]
    assert next(r for r in rows if r.variable_id == 'input_pair_width').upper == 4.238e-05
    compiled, _ = comp.build_graph(make_config(tmp_path).model_copy(update=dict(parameters=rows)), graph)
    assert graph_contract(compiled) == graph_contract(graph)
    exported = profile.optimization_graph(REPO / tasks.REAL_PROFILES['gpdk045_ota5']['structure'])
    assert graph_contract(exported) == graph_contract(graph)
    assert next(g for g in graph.parameter_groups if g.id == 'input_pair_width').upper == TOP


def test_a_form_writer_task_saved_before_keeps_matching_its_rows_and_its_top_value(tmp_path):
    # The recorded ring oscillator's MIM capacitor side, 2 .. 5.6 um on the 5 nm grid, tops out at 5.600000000000001e-06.
    # Such a task ran before (the form writer allows 1e-12 at its bounds); saved before compile took the top point, its
    # mapping and rules hold 5.6e-06 - its rows must still pass the check at Start, without saving it again.
    from analog_optimizer.envs.sizing import graph_contract
    from gator_workbench import profiles
    from test_wb_cdf_write import config, make
    entry = make(tmp_path)
    directory = Path(entry['directory'])
    mapping, rules = json.loads((directory / 'mapping.json').read_text()), json.loads((directory / 'rules.json').read_text())
    side = next(g for g in mapping['parameter_groups'] if g['id'] == 'wc')
    assert side['upper'] == 5.600000000000001e-06                          # saved now: the top grid point
    side['upper'] = 5.6e-06
    for write in rules['writes']:
        if write['upper'] == 5.600000000000001e-06:
            write['upper'] = 5.6e-06
    (directory / 'mapping.json').write_text(json.dumps(mapping))
    (directory / 'rules.json').write_text(json.dumps(rules))
    profile = profiles.load_profile('ring_cdf')
    graph = profile.optimization_graph()
    compiled, _ = comp.build_graph(config(entry['parameters']), graph)
    assert graph_contract(compiled) == graph_contract(graph)
    top = ActionMapper(graph).legalize({g.id: 1.0 for g in graph.parameter_groups if g.mutable}).assignments
    profile.validate_assignment(top)
    assert {v for (device, name), v in top.items() if device.startswith('XU1/C') and name == 'w'} == {5.600000000000001e-06}


def test_a_generated_profile_whose_top_is_not_above_its_bound_keeps_its_bounds_exactly(tmp_path):
    profile = _ota5_profile(tmp_path, 3.6e-06, 4.4e-06, 5e-09)            # the verified OTA5 range
    assert profile.bounds == {'XU1/M1': (3.6e-06, 4.4e-06), 'XU1/M2': (3.6e-06, 4.4e-06)}


# ------------------------------------------------------------------------------ B4: the graph view reads what it shows
def test_the_graph_view_reads_one_transition_part_and_its_state_newest_first(tmp_path, monkeypatch):
    config = make_config(tmp_path, run=dict(max_evaluations=30), output=dict(flush_every_evaluations=3, checkpoint_every_evaluations=10))
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    import pyarrow.parquet as pq
    filtered, read = [], pq.read_table

    def counting(path, *args, **kwargs):
        if kwargs.get('filters'):
            filtered.append(Path(path).parent.name)
        return read(path, *args, **kwargs)
    monkeypatch.setattr(pq, 'read_table', counting)
    # The transition: the one part of the flush that holds its number. Its state: that part or the one before (a state is
    # written once, with the transition that first sees it - here the previous evaluation's). It was every part, oldest
    # first, for both.
    view = graph_view.graph_view(layout.run_dir)
    assert filtered in (['transitions', 'states'], ['transitions', 'states', 'states']), filtered
    from gator_workbench.trajectory import TrajectoryLoader
    loader = TrajectoryLoader(layout.run_dir)
    numbers = sorted(loader.reader.table('transitions', ['commit_seq'])['commit_seq'].to_pylist())
    assert len(numbers) == view['step']['count'] > 10 and len(loader.reader.flushes) > 5          # parts to skip
    for number in numbers:
        filtered.clear()
        row, _ = graph_view._step(loader, number, None)
        assert filtered in (['transitions', 'states'], ['transitions', 'states', 'states']), (number, filtered)
        whole = graph_view._one_row(loader.reader, 'transitions', 'commit_seq', number)            # every part, oldest first
        assert {k: whole[k] for k in row} == row
        assert loader._states == {row['state_ref']: graph_view._one_row(loader.reader, 'states', 'state_id', row['state_ref'])}


def test_scalars_do_not_search_for_a_missing_dateutil_per_value():
    import pyarrow as pa
    import gator_workbench.storage.dataset  # noqa: F401 - importing it is what sets the sentinel
    assert 'dateutil' in sys.modules
    if sys.modules['dateutil'] is not None:
        pytest.skip('dateutil is installed here')
    assert importlib.util.find_spec('dateutil') is None
    started = time.perf_counter()
    for value in range(2000):
        pa.scalar(value)                                          # what a parquet filter does with its value
    assert time.perf_counter() - started < 0.5                    # a failed import search per value was ~1 ms


# ------------------------------------------------------------------------------ B6: the PDK record, once per validation
FIXTURE = Path(__file__).parent / 'fixtures' / 'pdk_demo'


@pytest.fixture
def demo_pdk(tmp_path, monkeypatch):
    """demo045 loaded in this test's settings and the MOCK demo circuit registered (as test_wb_pdk does)."""
    scans = [pdk.scan_model_text((FIXTURE / 'models' / name).read_text(), f'/pdk/demo045/models/{name}')
             for name in ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')]
    record = pdk.finish_load(dict(technology_library='demo045', cdf_text=(FIXTURE / 'cdf.txt').read_text(), scans=scans,
                                  sources=dict(model_files=[])))
    models = pdk.parse_models(record)
    models['vsource'] = dict(kind='vsource', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'dc': 'dc'})
    models['capacitor'] = dict(kind='capacitor', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'c': 'c'})
    mapping = tmp_path / 'demo_mapping.json'
    mapping.write_text(json.dumps(dict(mapping_version='demo045-test', models=models, global_nets=['0'], net_roles={'0': ['ground']},
                                       parameter_groups=[dict(id='input_w', parameter_kind='w', unit='m', lower=1e-6, upper=10e-6,
                                                              members=[dict(device_id='XU1/M1', parameter='w')])])))
    monkeypatch.setitem(task_registry.SYNTHETIC_FIXTURES, 'pdk_demo', dict(netlist=str(FIXTURE / 'demo_circuit.scs'), config=str(mapping),
                                                                   circuit_class='opamp'))
    loads = dict(load_record=0, list_pdks=0)
    load, listing = pdk.load_record, pdk.list_pdks

    def counted_load(*args, **kwargs):
        loads['load_record'] += 1
        return load(*args, **kwargs)

    def counted_list(*args, **kwargs):
        loads['list_pdks'] += 1
        return listing(*args, **kwargs)
    monkeypatch.setattr(pdk, 'load_record', counted_load)
    monkeypatch.setattr(pdk, 'list_pdks', counted_list)
    return loads


def test_a_validation_reads_the_pdk_record_once_and_lists_the_loaded_pdks_once(demo_pdk, tmp_path):
    extra = [dict(variable_id=f'x{i}', instance_path=device, parameter_name=name, unit='1', lower=1, upper=4)
             for i, (device, name) in enumerate((('XU1/Q1', 'area'), ('XU1/L1', 'nr'), ('XU1/M1', 'region'), ('XU1/M2', 'sa')))]

    def config(vocabulary):
        def mutate(raw):
            raw['run']['network']['vocabulary'] = vocabulary
            raw['parameters'] += extra
        return make_config(tmp_path, 'synthetic:pdk_demo', mutate=mutate)
    graph = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='synthetic:pdk_demo')).base_graph
    demo_pdk.update(load_record=0, list_pdks=0)
    under_pdk = validation.validate(config('pdk:demo045'), graph=graph)
    assert demo_pdk == dict(load_record=1, list_pdks=0)            # it was read four times
    assert 'pdk_vocabulary' in [i.code for i in under_pdk.issues]
    demo_pdk.update(load_record=0, list_pdks=0)
    standard = validation.validate(config('standard'), graph=graph)
    assert demo_pdk == dict(load_record=2, list_pdks=1)            # one listing (it loads each PDK) + one read, for all rows
    hints = [i.message for i in standard.issues if i.code == 'parameter_kind_unsupported']
    assert len(hints) == 4 and sum('The loaded PDK demo045 knows it' in m for m in hints) == 2


# ------------------------------------------------------------------------------ B7: matched devices on a large circuit
def test_matched_devices_of_800_transistors_are_found_without_trying_every_pair_against_every_pair():
    _mos = dict(terminals=('D', 'G', 'S', 'B'), roles=('drain', 'gate', 'source', 'bulk'), parameters={'w': 'w', 'l': 'l'})
    mapping = ParserConfig(models={'nch': DeviceMapping('nmos', **_mos), 'pch': DeviceMapping('pmos', **_mos),
                                   'vsource': DeviceMapping('vsource', terminals=('PLUS', 'MINUS'), roles=('positive', 'negative'),
                                                            parameters={'dc': 'dc'})},
                           net_roles={'0': ('ground',)})
    stages = ''.join(f'T{i} (t{i} vb 0 0) nch w=2u l=1u\nA{i} (x{i} ip{i} t{i} 0) nch w=4u l=500n\n'
                     f'B{i} (y{i} in{i} t{i} 0) nch w=4u l=500n\nL{i} (x{i} x{i} vdd vdd) pch w=2u l=1u\n'
                     f'R{i} (y{i} x{i} vdd vdd) pch w=2u l=1u\n' for i in range(160))
    graph = SpectreParser(mapping).parse_text(stages + 'V1 (vdd 0) vsource dc=1\n')
    started = time.perf_counter()
    found = structures.recognize(graph)
    elapsed = time.perf_counter() - started
    kinds = {}
    for s in found:
        kinds[s.kind] = kinds.get(s.kind, 0) + 1
    assert kinds == dict(differential_pair=160, tail_source=160, active_load=160)
    assert [s.devices for s in found[:2]] == [('A0', 'B0'), ('T0',)]
    assert next(s.devices for s in found if s.kind == 'active_load') == ('L0', 'R0')
    assert elapsed < 3.0, elapsed                                 # every pair against every pair took 12 s here


# ------------------------------------------------------------------------------ B9 and D: reads per evaluation / per load
def test_a_mock_run_resolves_its_work_folder_and_reads_the_waveform_index_once(tmp_path, monkeypatch):
    reads, resolved = [], []
    read_json, resolve = engine_module.read_json, Path.resolve

    def counting_read(path, *args, **kwargs):
        reads.append(Path(path).name)
        return read_json(path, *args, **kwargs)
    monkeypatch.setattr(engine_module, 'read_json', counting_read)

    def counting_resolve(self, *args, **kwargs):
        if self.name == 'work':
            resolved.append(str(self))
        return resolve(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', counting_resolve)
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=12)), tmp_path)
    assert state == 'completed'
    assert reads.count('index.json') == 1                         # it was read after every evaluation
    assert resolved.count(str(layout.work)) == 1                  # three times per evaluation before


def test_loading_the_mock_task_hashes_its_netlist_once(monkeypatch):
    hashed, sha256 = [], tasks._sha256

    def counting(path):
        hashed.append(Path(path).name)
        return sha256(path)
    monkeypatch.setattr(tasks, '_sha256', counting)
    runtime = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='synthetic:gpdk045_ota5'))
    assert sorted(hashed) == ['gpdk045_opamp.json', 'gpdk045_ota5.scs']
    assert runtime.circuit['topology_id'] == f"netlist-sha256:{runtime.circuit['netlist_sha256'][:16]}"
