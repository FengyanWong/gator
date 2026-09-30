import shutil
from pathlib import Path

import pytest

from gator_workbench.ngspice_netlist import parse_text
from gator_workbench.ngspice_operating_points import instrument, read
from analog_optimizer.envs.sizing import mapped_operating_points


@pytest.mark.skipif(not shutil.which('ngspice'), reason='Free local ngspice is not installed')
def test_level1_mos_op_readout_matches_graph_and_finite_bias(tmp_path):
    import subprocess
    text = (Path(__file__).parents[2] / 'examples/circuits/ngspice_ota5_level1.cir').read_text()
    graph = parse_text(text).graph
    deck = tmp_path / 'deck.cir'
    deck.write_text(instrument(text, graph))
    done = subprocess.run(['ngspice', '-b', str(deck)], capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stderr
    raw = read(done.stdout, graph)
    mapped, unmatched = mapped_operating_points(graph, raw)
    mos = {d.id for d in graph.devices if d.kind in ('nmos', 'pmos')}
    assert set(mapped) == mos and not unmatched
    assert all(set(v) == {'ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat', 'region'} for v in mapped.values())
    assert all(v['gm'] > 0 and v['gds'] > 0 and v['region'] in (0, 1, 2, 3) for v in mapped.values())


@pytest.mark.skipif(not shutil.which('ngspice'), reason='Free local ngspice is not installed')
def test_analysis_counters_preserve_measured_values_and_count_actual_commands(tmp_path):
    import subprocess
    from gator_workbench.ngspice_analysis import instrument as counters, counts
    from gator_workbench.ngspice_netlist import read_results
    text = (Path(__file__).parents[2]/'examples/circuits/ngspice_ota5_level1.cir').read_text()
    parsed = parse_text(text)
    outputs = []
    for name, content in [('before',text), ('after',counters(instrument(text,parsed.graph)))]:
        deck = tmp_path/(name+'.cir')
        deck.write_text(content)
        run = subprocess.run(['ngspice','-b',str(deck)],capture_output=True,text=True,timeout=20)
        assert run.returncode==0,run.stderr
        outputs.append(run.stdout)
    assert read_results(outputs[0],parsed.result_names)==read_results(outputs[1],parsed.result_names)
    record = counts(outputs[1],complete=True)
    assert record['commands']=={'op':1,'ac':1} and record['analyses']==2
    assert counts(outputs[1],complete=False)['analyses'] is None


def test_analysis_counts_do_not_treat_run_as_one_analysis():
    from gator_workbench.ngspice_analysis import counts
    value=counts('GATOR_ANALYSIS_DISPATCH run\n',complete=True)
    assert value['analyses'] is None and not value['complete']
