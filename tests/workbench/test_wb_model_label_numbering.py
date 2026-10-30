"""Run-list names remain stable while duplicate labels avoid rescanning occupied suffixes."""
from copy import deepcopy
import random

import pytest

from gator_workbench import checkpoints as ckpt


def rows_for(labels):
    """Create run-list entries with the supplied model labels."""
    return [dict(run_dir=f'/mock/run-{i:05d}', created_utc='2026-10-18T00:00:00Z',
                 model_label=label, renamed=False) for i, label in enumerate(labels)]


def previous_names(rows):
    """The previous public behavior: renamed rows first, using the unchanged single-name allocator."""
    taken, names = set(), {}
    ordered = sorted(rows, key=lambda row: (row.get('created_utc') or '', row['run_dir']))
    for renamed in (True, False):
        for row in ordered:
            label = row.get('model_label')
            if label and bool(row.get('renamed')) == renamed:
                name = ckpt.free_model_label(label, taken)
                taken.add(name)
                names[row['run_dir']] = name
    return names


@pytest.mark.parametrize('labels, expected', [
    ([], []),
    (['ota', 'ota', 'ota'], ['ota', 'ota (2)', 'ota (3)']),
    (['ota (4)', 'ota', 'ota', 'ota', 'ota'], ['ota (4)', 'ota', 'ota (2)', 'ota (3)', 'ota (5)']),
    (['ota (8)', 'ota (8)', 'ota (2)', 'ota', 'ota'], ['ota (8)', 'ota (2)', 'ota (3)', 'ota', 'ota (4)']),
    (['ota (2) (3)', 'ota (2) (3)', 'ota (2) (2)', 'ota (2)', 'ota (2)'],
     ['ota (2) (3)', 'ota (2) (2)', 'ota (2) (4)', 'ota (2)', 'ota (3)']),
    (['μ模型', 'μ模型', 'μ模型 (02)', 'μ模型 (02)', 'μ模型 (٢)', 'μ模型 (٢)'],
     ['μ模型', 'μ模型 (2)', 'μ模型 (02)', 'μ模型 (3)', 'μ模型 (٢)', 'μ模型 (4)']),
    ([None, '', 'ota', None, 'ota'], ['ota', 'ota (2)']),
])
def test_numbered_names_preserve_explicit_suffixes_nested_bases_and_holes(labels, expected):
    rows = rows_for(labels)
    before = deepcopy(rows)
    assert list(ckpt.unique_model_labels(rows).values()) == expected
    assert rows == before


def test_renamed_names_take_precedence_then_creation_time_and_run_path():
    rows = [dict(run_dir='/mock/b', created_utc='2', model_label='ota'),
            dict(run_dir='/mock/a', created_utc='2', model_label='ota'),
            dict(run_dir='/mock/c', created_utc=None, model_label='ota'),
            dict(run_dir='/mock/d', created_utc='3', model_label='ota', renamed=True),
            dict(run_dir='/mock/e', created_utc='1', model_label='ota (3)', renamed=True),
            dict(run_dir='/mock/f', created_utc='1', model_label='ota (4)')]
    expected = {'/mock/e': 'ota (3)', '/mock/d': 'ota', '/mock/c': 'ota (2)',
                '/mock/f': 'ota (4)', '/mock/a': 'ota (5)', '/mock/b': 'ota (6)'}
    assert ckpt.unique_model_labels(rows) == expected
    assert ckpt.unique_model_labels(list(reversed(rows))) == expected


@pytest.mark.parametrize('seed', range(8))
def test_mixed_labels_match_previous_allocator(seed):
    rng = random.Random(seed)
    labels = [None, '', 'ota', 'ldo', 'ota (2)', 'ota (3)', 'ota (9)', 'ota (02)', 'ota (0)',
              'ota (2) (2)', 'ota (2) (7)', 'ota (2) (2) (3)', 'μ模型', 'μ模型 (٢)', 'ota (x)']
    rows = rows_for([rng.choice(labels) for _ in range(200)])
    for row in rows:
        row.update(created_utc=rng.choice([None, '1', '2', '3']), renamed=rng.choice([False, True]))
    rng.shuffle(rows)
    assert ckpt.unique_model_labels(rows) == previous_names(rows)


def test_suffix_search_is_local_to_each_listing_and_fills_new_holes():
    rows = rows_for(['ota', 'ota (2)', 'ota (3)', 'ota', 'ota'])
    assert list(ckpt.unique_model_labels(rows).values()) == ['ota', 'ota (2)', 'ota (3)', 'ota (4)', 'ota (5)']
    # An older run can disappear between requests. The next list starts from its actual taken names.
    del rows[1]
    assert list(ckpt.unique_model_labels(rows).values()) == ['ota', 'ota (3)', 'ota (2)', 'ota (4)']


def test_large_duplicate_list_constructs_each_candidate_once(monkeypatch):
    rows = rows_for(['ota'] * 1024)
    expected = previous_names(rows)
    numbered, calls = ckpt.numbered, []

    def counted(base, suffix):
        """Record each numbered-label candidate while preserving its formatted value."""
        calls.append((base, suffix))
        return numbered(base, suffix)

    monkeypatch.setattr(ckpt, 'numbered', counted)
    assert ckpt.unique_model_labels(rows) == expected
    assert calls == [('ota', suffix) for suffix in range(2, 1025)]


def test_unique_labels_need_no_numbered_candidates(monkeypatch):
    def unexpected(*args):
        """Fail if a unique model label causes suffix candidates to be constructed."""
        pytest.fail('An already unique label should not construct suffix candidates')

    monkeypatch.setattr(ckpt, 'numbered', unexpected)
    rows = rows_for(['ota', 'ota (2)', 'ota (20)', 'ota (2) (2)', 'ldo'])
    assert ckpt.unique_model_labels(rows) == {row['run_dir']: row['model_label'] for row in rows}
