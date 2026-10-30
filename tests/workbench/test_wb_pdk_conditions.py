"""A PDK whose conditions template states supplies RELATIVE to the testbench supply ("supply_scale": true, 2026-10-09:
circuits at 3.3 V and 1.8 V on one second foundry PDK) gives every saved task its own conditions.json, scaled to its supply;
gpdk045 tasks keep the verified absolute file and nothing of theirs changes. The template of such a PDK lives in the PDK's
folder of the local settings, never in the repository: the one here is invented."""
import json

import pytest

from gator_workbench import pdk_record, profile_generate, saved_tasks
from gator_workbench.paths import repo_root
from gator_workbench.profile_store import FILES, ProfileError

PDK = 'foundry180'                         # an invented technology library
TEMPLATE = dict(
    schema_version='1.0', supply_scale=True,
    nominal=dict(id='nominal', model_section='tt', temperature_c=27.0, supply_v=1.0),
    screening_corners=[dict(id='nominal', model_section='tt', temperature_c=27.0, supply_v=1.0),
                       dict(id='ss_hot_low', model_section='ss', temperature_c=125.0, supply_v=0.9),
                       dict(id='ff_cold_high', model_section='ff', temperature_c=-40.0, supply_v=1.1)],
    model_policy=dict(deterministic_sections=['tt', 'ss', 'ff'], temperature_c_bounds=[-40.0, 125.0],
                      screening_supply_v_bounds=[0.9, 1.1], bias_policy='testbench sources as drawn',
                      statistical_section='mc', monte_carlo_execution_implemented=False),
    post_validation=dict(top_k=3, lambda_failed=1.0, reject_any_failed_corner=True, training_condition='nominal_only',
                         monte_carlo=None, max_deterministic_points_per_screen=15),
    evidence=dict(pdk_version='invented', model_entry='invented.scs', model_entry_sha256='0' * 64, selection_note='a test'))


@pytest.fixture
def template():
    """The invented PDK's template, where a real one is kept: its folder in the (temporary) local settings."""
    folder = pdk_record.pdk_dir(PDK)
    folder.mkdir(parents=True)
    (folder / profile_generate.CONDITIONS_TEMPLATE_FILE).write_text(json.dumps(TEMPLATE))
    return TEMPLATE


def test_gpdk045_has_no_relative_template():
    assert profile_generate.conditions_template('gpdk045') is None            # the absolute file: not a template
    assert profile_generate.conditions_template(None) is None
    assert profile_generate.conditions_template('../etc') is None
    assert profile_generate.scaled_conditions_for('gpdk045', 1.0) is None


def test_no_file_under_configs_is_a_relative_template():
    """Such a template belongs to a PDK that is not in the repository: it is read from the local settings."""
    for path in (repo_root() / 'configs').glob('*_conditions.json'):
        assert json.loads(path.read_text()).get('supply_scale') is not True, path.name


def test_a_relative_template_scales_with_the_testbench_supply(template):
    assert profile_generate.conditions_template(PDK) == template
    for supply in (3.3, 1.8):
        own = profile_generate.scaled_conditions_for(PDK, supply)
        assert own['nominal']['supply_v'] == pytest.approx(supply) and own['nominal']['model_section'] == 'tt'
        corners = {c['id']: c for c in own['screening_corners']}
        assert corners['ss_hot_low']['supply_v'] == pytest.approx(0.9 * supply)
        assert corners['ff_cold_high']['supply_v'] == pytest.approx(1.1 * supply)
        assert own['model_policy']['screening_supply_v_bounds'] == pytest.approx([0.9 * supply, 1.1 * supply])
        assert set(c['model_section'] for c in own['screening_corners']) <= set(own['model_policy']['deterministic_sections'])
        assert 'supply_scale' not in own and own['scaled_from']['testbench_supply_v'] == supply
    with pytest.raises(ProfileError):
        profile_generate.scaled_conditions_for(PDK, 0)
    (pdk_record.pdk_dir(PDK) / profile_generate.CONDITIONS_TEMPLATE_FILE).write_text(json.dumps(dict(template, supply_scale=False)))
    assert profile_generate.conditions_template(PDK) is None                 # an absolute file is not a template


def test_a_task_runs_under_its_own_conditions_file_when_it_has_one(tmp_path):
    assert saved_tasks.conditions_file_for(tmp_path) == repo_root() / 'configs' / 'gpdk045_conditions.json'
    (tmp_path / FILES['conditions']).write_text('{}')
    assert saved_tasks.conditions_file_for(tmp_path) == tmp_path / FILES['conditions']


def test_the_significant_digit_spelling_of_derived_values():
    """Read off one netlister's exports of 2026-10-09: a zero per integer digit beyond the first; everything else as written."""
    from gator_workbench.cdf_write import significant_digit_spelling as spell
    assert spell('10.96u') == '10.960u' and spell('20.7442u') == '20.74420u' and spell('15.75u') == '15.750u'
    assert spell('13.145u') == '13.1450u' and spell('10.54u') == '10.540u' and spell('20.9484u') == '20.94840u'
    assert spell('5.54u') == '5.54u' and spell('8.25u') == '8.25u' and spell('500n') == '500n' and spell('16.0u') == '16.0u'
    for same in ('1.35e-12', '0.054', '2.4e-12', 'iPar("w")', '5u', '20u'):
        assert spell(same) == same
