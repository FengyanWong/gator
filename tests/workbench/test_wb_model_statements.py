"""Exact statement parsing on invented text only (origin=synthetic, provenance=mock)."""
from copy import deepcopy
import random

import pytest

from gator_workbench import device_models


def _before(text):
    """The previous parser, with whole-current-statement brace counting."""
    lines, current, depth = [], '', 0
    for raw in text.splitlines():
        line = raw.split('//')[0]
        if not current and line.lstrip().startswith('*'):
            continue
        line = line.rstrip()
        if line.lstrip().startswith('+'):
            if current:
                current += ' ' + line.lstrip()[1:]
                continue
            if lines:
                lines[-1] += ' ' + line.lstrip()[1:]
                continue
        if line.endswith('\\'):
            current += line[:-1] + ' '
            continue
        current += line
        depth = current.count('{') - current.count('}')
        if depth > 0:
            current += '\n'
            continue
        if current.strip():
            lines.append(current.strip())
        current = ''
    if current.strip():
        lines.append(current.strip())
    return lines


CASES = [
    ('empty', '', []),
    ('plain', ' a \n\n b//drop', ['a', 'b']),
    ('comments', '* skip {\n x\n * after', ['x']),
    ('star_inside', 'head {\n* } included\nnext', ['head {\n* } included', 'next']),
    ('nested', 'head {\n inner {\n value\n }\n}\nlast', ['head {\n inner {\n value\n }\n}', 'last']),
    ('negative_then_open', 'close }\nopen {\nx\n}\na', ['close }', 'open {\nx\n}', 'a']),
    ('previous_plus_brace', 'first\n +{unclosed\nsecond\n', ['first {unclosed', 'second']),
    ('plus_close', 'head {\n +}\nnext\nlast', ['head {\n }next', 'last']),
    ('plus_close_eof', 'head {\n +}', ['head {\n }']),
    ('plus_close_blank', 'head {\n +}\n\nnext', ['head {\n }', 'next']),
    ('plus_close_star', 'head {\n +}\n* included\nlast', ['head {\n }* included', 'last']),
    ('plus_close_backslash', 'head {\n +}\\\nnext\n', ['head {\n }\\next']),
    ('backslash_close', 'head {\n}\\\nnext\nlast', ['head {\n} next', 'last']),
    ('backslash_open', 'head {\\\nx\n}\n', ['head { x\n}']),
    ('backslash_eof', 'head \\\n value\\', ['head   value']),
    ('unclosed_eof', 'head {\n value\n', ['head {\n value']),
    ('unattached_plus', '+ first \n next', ['+ first', 'next']),
    ('unattached_plus_backslash', '+ first\\\nnext', ['+ first next']),
    ('quoted_brace', 'head "{"\nnext\n}', ['head "{"\nnext\n}']),
    ('comment_brace', 'head // {\nnext', ['head', 'next']),
    ('quoted_comment', 'head "// {"\nnext', ['head "', 'next']),
    ('brace_free_continuation', 'head\\\n + middle\\\n tail', ['head   middle\\ tail']),
    ('negative_continued', 'head {\n +}}\nlast\nnext {\nx\n}', ['head {\n }}last', 'next {\nx\n}']),
]


@pytest.mark.parametrize(('label', 'text', 'expected'), CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize('separator', ['\n', '\r\n', '\r'], ids=['lf', 'crlf', 'cr'])
def test_statement_boundaries_preserve_existing_continuation_rules(label, text, expected, separator):
    source = text.replace('\n', separator)
    assert device_models.statements(source) == _before(source) == expected


def _random_text(seed):
    """Generate reproducible statement fragments with mixed comments, continuations and line endings."""
    randomizer = random.Random(seed)
    lines = ['', ' ', '\t', '* comment {', ' // comment }', 'model mock primitive {', 'value=1',
             '}', '}}', '{', ' + value=2', '+ {', ' + }', '+ }\\', 'part\\', '{\\', '}\\',
             'quoted="{"', 'quoted="}"', 'quoted="//" {', 'value=1 // }', '  + // {', 'μ=3', '* }']
    separators = ['\n', '\r\n', '\r', '\u2028']
    return ''.join(randomizer.choice(lines) + randomizer.choice(separators) for _ in range(100)) \
        + randomizer.choice(['', 'tail', 'tail\\', '+ }', '// {'])


@pytest.mark.parametrize('seed', range(24))
def test_random_mixed_continuations_match_the_previous_parser(seed):
    text = _random_text(seed)
    assert device_models.statements(text) == _before(text)


def _large_card(count, *, mixed=False):
    """Build an invented model card with optional mixed continuation forms."""
    lines = ['model mock_card bsim4 type=n {']
    for index in range(count):
        line = f' {index + 1}: lmin=1n wmin=2n vth0=0.4 u0=0.03'
        if mixed and index % 3 == 0:
            lines += [line + '\\', ' vsat=1e5', ' +tox=2n']
        else:
            lines.append(line)
    return '\n'.join([*lines, '}', 'parameters after=1'])


@pytest.mark.parametrize('mixed', [False, True])
def test_large_invented_card_keeps_exact_statement_text(mixed):
    text = _large_card(1024, mixed=mixed)
    actual = device_models.statements(text)
    assert actual == _before(text)
    assert len(actual) == 2 and actual[-1] == 'parameters after=1'


def _invented_library():
    """Provide synthetic library text and device records covering includes, wrappers and missing models."""
    top = '\n'.join([
        'library mock', 'section tt', 'parameters delta=0.02', '+mobility=0.03',
        'include "card.scs" section=cards', 'include "missing.scs"', 'endsection tt',
        'section ff', 'parameters delta=0.04 mobility=0.04',
        'include "card.scs" section=cards', 'endsection ff', 'endl mock',
    ])
    card = '\n'.join([
        'library mock_card', 'section cards', 'inline subckt mock_n (d g s b)',
        'parameters l=1n w=2n\\', ' scale=1', 'mock_n (d g s b) mock_core l=l w=w',
        'model mock_core bsim4 type=n {', '1: lmin=1n wmin=2n vth0=0.4+delta\\',
        ' u0=mobility vsat=1e5', '+toxe=2n', ' 2: lmin=2n wmin=4n vth0=0.3 u0=0.02 vsat=9e4 tox=3n',
        '}', 'ends mock_n',
        'model mock_p bsim3v3 type=p lmin=4n wmin=8n vth0=-0.4*(temp/27) u0=100 vsat=8e4 tox=4n',
        'statistics {', 'process { vary delta dist=gauss std=0.01 }', '}', 'endsection cards', 'endl mock_card',
    ])
    record = dict(devices=dict(
        mock_n=dict(standard_kind='nmos', parameters=[]), mock_p=dict(standard_kind='pmos', parameters=[]),
        mock_missing=dict(standard_kind='nmos', parameters=[]),
        mock_default=dict(standard_kind='nmos', parameters=[dict(name='w', default='4n'), dict(name='l', default='2n')]),
    ))
    return {'/mock/top.scs': top, '/mock/card.scs': card}, record


def _library_result(module, files, record, section, temperature):
    """Collect parsed library facts, read order and MOS numbers for comparison."""
    calls = []

    def read(path):
        """Record requested model paths and return their invented contents."""
        calls.append(path)
        return files.get(path)

    library = module.read_library(read, '/mock/top.scs', section)
    return dict(parameters=library.parameters, cards=library.cards, wrappers=library.wrappers,
                missing=library.missing, seen=sorted(library.seen, key=repr), reads=calls,
                numbers=module.mos_numbers(library, record, temperature_c=temperature))


@pytest.mark.parametrize('section', ['tt', 'ff', None])
@pytest.mark.parametrize('temperature', [27.0, 127.0])
def test_library_structure_and_model_numbers_match_before_parser(monkeypatch, section, temperature):
    files, record = _invented_library()
    unchanged = deepcopy((files, record))
    actual = _library_result(device_models, files, record, section, temperature)
    with monkeypatch.context() as previous:
        previous.setattr(device_models, 'statements', _before)
        expected = _library_result(device_models, files, record, section, temperature)
    assert actual == expected
    assert (files, record) == unchanged
    if section is not None:
        assert len(actual['wrappers']['mock_n']['cards']['mock_core']['bins']) == 2
        assert actual['numbers'][0]['mock_n']['basis'] == 'model bin'
