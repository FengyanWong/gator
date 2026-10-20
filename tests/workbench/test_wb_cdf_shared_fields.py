"""Read-only CDF parsing from invented query text (origin=synthetic, provenance=mock)."""
from copy import deepcopy
import random

import pytest

from gator_workbench import cdf_facts, cdf_text, pdk


def _before_cdf(text):
    """The previous public CDF parser, including its independent field splitting."""
    skill_value, plist, form_rule = cdf_text.skill_value, cdf_text._plist, cdf_text._form_rule
    cells, leaves, layout_only = {}, {}, []
    lines = [cdf_text.query_fields(raw.rstrip('\r')) for raw in (text or '').splitlines()]
    for parts in sorted(lines, key=lambda parts: parts[0] != 'CELL'):
        tag = parts[0]
        if tag == 'CELL' and len(parts) >= 11:
            name = parts[1]
            spectre = dict(term_order=skill_value(parts[3]), term_mapping=plist(skill_value(parts[4])),
                           inst_parameters=skill_value(parts[5]), other_parameters=skill_value(parts[6]),
                           prop_mapping=plist(skill_value(parts[7])), component_name=skill_value(parts[8]),
                           name_prefix=skill_value(parts[9]))
            has_spectre = any(v for key, v in spectre.items() if key not in ('name_prefix',))
            cells[name] = dict(name=name, model=skill_value(parts[2]), spectre=spectre if has_spectre else None,
                               views=skill_value(parts[10]) or [], parameters={})
        elif tag == 'PARAM' and len(parts) >= 7 and parts[1] in cells:
            entry = dict(type=skill_value(parts[3]), units=skill_value(parts[4]), default=skill_value(parts[5]),
                         prompt=skill_value(parts[6]))
            if len(parts) >= 11:
                entry.update(editable=form_rule(parts[7]), display=form_rule(parts[8]), callback=skill_value(parts[9]),
                             choices=skill_value(parts[10]))
            if len(parts) >= 12:
                entry['range'] = cdf_text.numeric_range(skill_value(parts[11]))
            cells[parts[1]]['parameters'][parts[2]] = entry
        elif tag == 'FORM' and len(parts) >= 4 and parts[1] in cells:
            cells[parts[1]]['form'] = dict(init=skill_value(parts[2]), done=skill_value(parts[3]))
        elif tag == 'LEAF' and len(parts) >= 6:
            leaves.setdefault(parts[1], []).append(dict(instance=parts[2], library=parts[3], cell=parts[4],
                                                         model=skill_value(parts[5])))
        elif tag == 'NOCDF' and len(parts) >= 2:
            layout_only.append(dict(cell=parts[1], views=skill_value(parts[2]) if len(parts) > 2 else []))
    return dict(cells=cells, leaves=leaves, layout_only=sorted(layout_only, key=lambda item: item['cell']))


def _before_facts(text, *, library, cell):
    """The previous metadata pass followed by an independent CDF text parse."""
    instances, masters, rules, conflicts, opened, after = {}, {}, {}, [], None, None
    for raw in (text or '').splitlines():
        parts = cdf_facts.query_fields(raw.rstrip('\r'))
        tag = parts[0] if parts else ''
        if tag == 'INST' and len(parts) >= 4:
            instances[parts[1]] = dict(library=parts[2], cell=parts[3])
        elif tag == 'RULE' and len(parts) >= 5 and parts[3] in ('E', 'D') and parts[4] in ('yes', 'no', 'form'):
            rules.setdefault(parts[1], {}).setdefault(parts[2], {})['editable' if parts[3] == 'E' else 'display'] = parts[4]
        elif tag == 'MASTER' and len(parts) >= 3:
            if parts[1] in masters and masters[parts[1]] != parts[2]:
                conflicts.append(parts[1])
            masters[parts[1]] = parts[2]
        elif tag == 'OPENED':
            opened = parts[1:]
        elif tag == 'AFTER' and len(parts) >= 2:
            after = cdf_facts.skill_value(parts[1])
    cdf = _before_cdf(text)
    return dict(format=cdf_facts.FORMAT, library=library, cell=cell, instances=instances, masters=masters, cells=cdf['cells'],
                leaves=cdf['leaves'], rules=rules, conflicts=sorted(set(conflicts)),
                opened_mode=cdf_facts.skill_value(opened[0]) if opened else None, modified_after=bool(after))


def _cell(name='mock_device', model='mock_model'):
    return '|'.join(['CELL', name, f'"{model}"', '(D G S B)', '(nil D \\:d G \\:g S \\:s B \\:b)',
                     '(w l)', 'nil', '(nil w simW)', 'nil', 'M', '(symbol schematic)'])


def _rich_rows():
    return [
        'PARAM|mock_device|w|string|lengthMetric|1u|"Width | µ"|t|nil|"callback(x)"|(1u 2u)|(1e-9 1e-3)',
        'INST|M1|mock_lib|old_device', 'MASTER|mock_device|mock_lib',
        _cell(model='older_model'), 'FORM|mock_device|nil|"done()"',
        'LEAF|mock_parent|R1|mock_lib|mock_device|"mock_model"',
        'LEAF|mock_parent|R2|mock_lib|mock_device|nil',
        'RULE|M1|w|E|yes', 'RULE|M1|w|E|no', 'RULE|M1|w|D|form', 'RULE|M1|w|other|yes',
        'RULE|M1|w|D|invalid', 'OPENED|"r"|nil', 'AFTER|nil',
        'MASTER|mock_device|other_lib', 'MASTER|mock_device|mock_lib', 'INST|M1|mock_lib|mock_device',
        'NOCDF|z_layout|(layout)', 'NOCDF|a_layout', 'NOCDF|a_layout|(symbol)',
        _cell(),
        'PARAM|mock_device|w|string|lengthMetric|2u|"Later width | Ω"|nil|t|nil|nil|(1e-9 2e-3)',
        r'PARAM|mock_device|simW|string|lengthMetric|"iPar(\\"w\\")"|"Escaped \" quote | pipe"|t|t|nil|nil',
        'PARAM|mock_device|short|string|nil|3|"old seven-field row"',
        'FORM|mock_device|"init()"|nil',
        'CELL|no_spectre|nil|nil|nil|nil|nil|nil|nil|R|(layout)',
        'PARAM|absent|w|string|nil|1|"ignored"', 'FORM|absent|nil|nil',
        'CELL|short', 'PARAM|mock_device|too_short', 'LEAF|short', 'RULE|short', 'INST|short',
        'OPENED|"read-only"|t', 'AFTER|t', '', 'UNKNOWN|"unterminated | value',
        '* ignored', 'ignored\nphysical line',
    ]


def _large_text(count):
    return '\n'.join([_cell(), 'INST|M1|mock_lib|mock_device', 'AFTER|nil',
                      *[f'PARAM|mock_device|p{i}|string|nil|{i}|"Invented | value {i}"|t|t|nil|nil'
                        for i in range(count)]])


@pytest.mark.parametrize('text', [None, '', '\n\r\n', 'UNKNOWN|x', 'AFTER|nil', 'OPENED', 'AFTER|t'])
def test_empty_short_and_metadata_only_inputs_keep_their_answers(text):
    assert cdf_facts.parse_facts(text, library='mock_lib', cell='mock_core') == \
        _before_facts(text, library='mock_lib', cell='mock_core')
    assert cdf_text.parse_cdf_text(text) == _before_cdf(text)


@pytest.mark.parametrize('separator', ['\n', '\r\n', '\r', '\u2028'])
@pytest.mark.parametrize('seed', range(8))
def test_shuffled_rich_rows_preserve_full_facts_and_cdf(seed, separator):
    rows = _rich_rows()
    random.Random(seed).shuffle(rows)
    text = separator.join(rows)
    assert cdf_facts.parse_facts(text, library='mock_lib', cell='mock_core') == \
        _before_facts(text, library='mock_lib', cell='mock_core')
    assert cdf_text.parse_cdf_text(text) == _before_cdf(text)
    assert pdk.parse_cdf_text(text) == _before_cdf(text)


def test_duplicate_cell_and_parameter_order_remains_stable():
    text = '\n'.join(_rich_rows())
    facts = cdf_facts.parse_facts(text, library='mock_lib', cell='mock_core')
    assert facts['cells']['mock_device']['model'] == 'mock_model'
    assert facts['cells']['mock_device']['parameters']['w']['default'] == '2u'
    assert facts['cells']['mock_device']['parameters']['simW']['default'] == 'iPar("w")'
    assert facts['cells']['mock_device']['parameters']['simW']['prompt'] == 'Escaped " quote | pipe'
    assert facts['cells']['mock_device']['form'] == dict(init='init()', done=None)
    assert facts['instances']['M1'] == dict(library='mock_lib', cell='mock_device')
    assert facts['masters']['mock_device'] == 'mock_lib' and facts['conflicts'] == ['mock_device']
    assert facts['rules']['M1']['w'] == dict(editable='no', display='form')
    assert facts['opened_mode'] == 'read-only' and facts['modified_after'] is True
    assert [leaf['instance'] for leaf in facts['leaves']['mock_parent']] == ['R1', 'R2']


def test_field_row_consumer_accepts_one_pass_input_without_mutating_rows():
    rows = [cdf_text.query_fields(raw.rstrip('\r')) for raw in '\n'.join(_rich_rows()).splitlines()]
    original = deepcopy(rows)
    iterator = iter(rows)
    expected = _before_cdf('\n'.join(_rich_rows()))
    assert cdf_text._parse_cdf_fields(iterator) == expected
    assert list(iterator) == [] and rows == original


def _counted(monkeypatch, parser, text, *, facts):
    original = cdf_text.query_fields
    calls = []

    def query(line):
        calls.append(line)
        return original(line)

    with monkeypatch.context() as patched:
        patched.setattr(cdf_text, 'query_fields', query)
        patched.setattr(cdf_facts, 'query_fields', query)
        try:
            value = parser(text, library='mock_lib', cell='mock_core') if facts else parser(text)
            outcome = ('returned', value)
        except ValueError as exc:
            outcome = ('raised', type(exc), str(exc))
    return outcome, calls


@pytest.mark.parametrize('count', [0, 1, 4096])
def test_facts_split_each_physical_line_once_and_public_cdf_stays_one_pass(monkeypatch, count):
    text = _large_text(count)
    before, old_calls = _counted(monkeypatch, _before_facts, text, facts=True)
    after, new_calls = _counted(monkeypatch, cdf_facts.parse_facts, text, facts=True)
    assert before == after
    expected_lines = [raw.rstrip('\r') for raw in text.splitlines()]
    assert old_calls == expected_lines * 2 and new_calls == expected_lines
    assert sum(map(len, old_calls)) == 2 * sum(map(len, new_calls))
    before, old_calls = _counted(monkeypatch, _before_cdf, text, facts=False)
    after, new_calls = _counted(monkeypatch, cdf_text.parse_cdf_text, text, facts=False)
    assert before == after and old_calls == new_calls == expected_lines


@pytest.mark.parametrize(('text', 'early'), [
    ('AFTER|)\n' + _cell() + '\nAFTER|nil', True),
    ('INST|M1|mock_lib|mock_device\nAFTER|)\n' + _cell(), True),
    (_cell(model=')') + '\nAFTER|nil', False),  # quoted model is valid; malformed CDF field below is not
    ('CELL|bad|)|nil|nil|nil|nil|nil|nil|nil|nil\nAFTER|nil', False),
    (_cell() + '\nPARAM|mock_device|w|)|nil|1|nil\nAFTER|nil', False),
    (_cell() + '\nOPENED|)', False),
    ('OPENED|)\nCELL|bad|)|nil|nil|nil|nil|nil|nil|nil|nil', False),
])
def test_error_type_message_and_early_metadata_stop_are_preserved(monkeypatch, text, early):
    before, old_calls = _counted(monkeypatch, _before_facts, text, facts=True)
    after, new_calls = _counted(monkeypatch, cdf_facts.parse_facts, text, facts=True)
    assert before == after
    if early:
        assert before[0] == 'raised'
        assert old_calls == new_calls
        assert old_calls[-1] == 'AFTER|)' and len(old_calls) < len(text.splitlines())
    else:
        assert old_calls == new_calls * 2
