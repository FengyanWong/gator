"""Maestro's info outputs that no output reads are left out of a run's deck (record 7.157): which ones go, which stay,
when a task keeps them all, and the Maestro recipe's deck. No Virtuoso, no simulation."""
import pytest

from gator_workbench import profiles, recipes
from gator_workbench.recipes import INFO_ENV, without_unread_info
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module

TAIL = ('simulatorOptions options reltol=1e-3 temp=27\nstb stb probe=IPRB0 start=1 stop=10G dec=20\ndc dc write="spectre.dc"\n'
        'modelParameter info what=models where=rawfile\nelement info what=inst where=rawfile\n'
        'outputParameter info what=output where=rawfile\ndesignParamVals info what=parameters where=rawfile\n'
        'primitives info what=primitives where=rawfile\nsubckts info what=subckts where=rawfile\n'
        'finalTimeOP info what=oppoint where=rawfile\ndcOpInfo info what=oppoint where=rawfile\nsaveOptions options save=allpub\n')
OUTPUTS = [dict(name='gain', spectre_expression='value(mag(getData("loopGain" ?result "stb")) 10)', analysis='stb'),
           dict(name='ibias', spectre_expression='IDC("V0:p")', analysis='dc')]
NOTE = ("// GATOR: Maestro's info outputs modelParameter element outputParameter designParamVals primitives subckts left out "
        "- no output reads them (record 7.157)")


def test_the_six_unread_info_outputs_go_and_the_operating_points_stay():
    lean = without_unread_info(TAIL, OUTPUTS)
    assert lean == ('simulatorOptions options reltol=1e-3 temp=27\nstb stb probe=IPRB0 start=1 stop=10G dec=20\n'
                    'dc dc write="spectre.dc"\n' + NOTE + '\nfinalTimeOP info what=oppoint where=rawfile\n'
                    'dcOpInfo info what=oppoint where=rawfile\nsaveOptions options save=allpub\n')
    assert without_unread_info(lean, OUTPUTS) == lean                      # nothing left to leave out
    plain = 'tran tran stop=50n\nfinalTimeOP info what=oppoint where=rawfile\nsaveOptions options save=allpub\n'
    assert without_unread_info(plain, OUTPUTS) == plain                    # none of them: no comment either


@pytest.mark.parametrize('expression', ['VAR("vdd") * IDC("V0:p")', 'getData("M1:gm" ?result "element")',
                                        'value(getData("toxe" ?result "modelParameter"))'])
def test_a_task_whose_outputs_may_read_them_keeps_all_six(expression):
    assert without_unread_info(TAIL, OUTPUTS + [dict(name='x', spectre_expression=expression, analysis='dc')]) == TAIL


def test_the_switch_keeps_them_and_refuses_other_values(monkeypatch):
    monkeypatch.setenv(INFO_ENV, 'keep')
    assert without_unread_info(TAIL, OUTPUTS) == TAIL
    monkeypatch.setenv(INFO_ENV, 'off')
    with pytest.raises(ValueError, match='GATOR_INFO_OUTPUTS must be one of drop, keep'):
        without_unread_info(TAIL, OUTPUTS)


def test_a_statement_continued_on_the_next_line_goes_whole():
    tail = 'dc dc\nmodelParameter info what=models \\\n    where=rawfile\nsaveOptions options save=allpub\n'
    assert without_unread_info(tail, OUTPUTS) == ("dc dc\n// GATOR: Maestro's info outputs modelParameter left out - no output "
                                                  "reads them (record 7.157)\nsaveOptions options save=allpub\n")


def test_the_maestro_recipe_s_deck_leaves_them_out(tmp_path):
    from task_save_support import saved_maestro_task
    saved_maestro_task(tmp_path)
    profile = profiles.load_profile('ring_maestro')
    assert isinstance(profile, recipes.GenericMaestroProfile)
    saved = dict(profile.maestro)
    profile._deck = dict(saved, tail=saved['tail'] + 'element info what=inst where=rawfile\n')
    deck = profile.build_deck('XU1 (OUT VDD 0) ring_osc_3stage\n', '/pdk/model.scs', 'tt')
    assert 'element info' not in deck and "info outputs element left out" in deck and 'finalTimeOP info' in deck
    profile._deck = saved                                                   # the fixture's own tail has none of them
    assert profile.build_deck('X\n', '/pdk/model.scs', 'tt') == saved['head'] + 'X\n' + saved['tail']
