"""Include discovery recognizes the same quoted prefixes without scanning unrelated model text for comments."""
import random

import pytest

from gator_workbench import model_scan


def previous(text):
    return sorted({match.group(1) for line in text.splitlines()
                   for match in [model_scan._INCLUDE.match(model_scan._strip_comment(line))] if match})


@pytest.mark.parametrize('line', [
    '', ' ', '// include "hidden.scs"', '* include "hidden.scs"', 'x include "not-start.scs"',
    'include "a.scs"', '  InClUdE\t"b.scs" // comment', 'include "a//b.scs"',
    'include "a.scs" // include "ignored.scs"', 'include "first.scs" include "second.scs"',
    'include ""', 'include "unclosed // text', 'include // comment "not-a-file"',
    'include"missing-space.scs"', 'include \'single-quote.scs\'', 'includes "plural.scs"',
    'include "a\\"//b.scs"', 'include "a\\"b.scs"', '\u2003include\u00a0"unicode space.scs"',
    'include\t"µ-model.scs" section=tt', 'model fake bsim4 type=n { // include "not-a-file"',
])
def test_comment_quote_and_directive_boundaries_keep_original_result(line):
    assert model_scan.includes_of(line) == previous(line)


@pytest.mark.parametrize('seed', range(10))
def test_random_directives_and_noise_match_original(seed):
    rng = random.Random(seed)
    prefixes = ['', ' ', '\t', '// ', '* ', 'model x ', '\u2003']
    heads = ['include ', 'INCLUDE\t', 'includes ', 'include//', 'include', '+ include ']
    bodies = ['"a.scs"', '"a//b.scs"', '"a\\"//b"', '""', '"unclosed', "'a.scs'", 'x']
    tails = ['', ' // include "noise.scs"', ' section=tt', ' "another.scs"', ' // "']
    lines = [rng.choice(prefixes) + rng.choice(heads) + rng.choice(bodies) + rng.choice(tails)
             for _ in range(150)]
    text = rng.choice(['\n', '\r\n', '\r']).join(lines)
    assert model_scan.includes_of(text) == previous(text)


def test_output_remains_sorted_deduplicated_and_comment_walk_is_unused(monkeypatch):
    text = '\n'.join(['include "z.scs"', 'include "a.scs"', 'include "z.scs"',
                      *[f'model synthetic_{i} resistor r={i} // synthetic comment' for i in range(1000)]])
    expected = previous(text)
    assert expected == ['a.scs', 'z.scs']

    def unwanted(line):
        pytest.fail('Include discovery must not walk every model line to strip comments')

    monkeypatch.setattr(model_scan, '_strip_comment', unwanted)
    assert model_scan.includes_of(text) == expected
