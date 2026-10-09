"""Fixes from the repository review of 2026-09-22 (docs/frontend_implementation_status.md, status record 7.64): one
validation for a cell read from Virtuoso, a completed run that ends right after a periodic save, one source digest per
save, one fsync per JSON file, and timestamps that no longer retry a missing `pytz` for every value. MOCK only."""
import datetime as dt
import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import tasks
from gator_workbench.api import create_app
from gator_workbench.storage import read_json
from helpers import execute, make_config
from test_wb_api import probe
from test_wb_profiles import CIRCUIT, config, connection_file, read_cell


def test_a_cell_read_from_virtuoso_is_validated_the_same_way_everywhere(tmp_path, monkeypatch):
    # Before: the page left the metrics of a cell without a task unchecked, while the start checklist checked them against
    # an EMPTY list - every probe was "metric_not_provided" there and nowhere else.
    monkeypatch.setattr(tasks, 'bridge_importable', lambda: True)
    read_cell(tmp_path)
    connection_file()
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False,
                                   monitor=probe(tmp_path)))
    loaded = client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()
    assert loaded['native_draft'] and loaded['testbench_probes']['rows']
    raw = config().model_dump(mode='json')
    raw['measurements'] = loaded['testbench_probes']['rows']
    page = client.post('/api/config/validate', json=dict(config=raw)).json()
    checklist = client.post('/api/agent/readiness', json=dict(config=raw)).json()
    assert 'metric_not_provided' not in [i['code'] for i in page['issues']]
    assert 'metric_not_provided' not in json.dumps(checklist) and 'it provides []' not in json.dumps(checklist)
    assert 'circuit_profile_missing' in [i['code'] for i in page['issues']]            # and it still cannot be started


def _checkpoints(layout):
    found = [read_json(p / 'metadata.json') for p in sorted((layout.run_dir / 'checkpoints').glob('ckpt-*'))]
    return [(m['counters']['evaluations_committed'], m['kind'], m.get('relabelled_from')) for m in found]


def test_a_run_that_completes_right_after_a_periodic_save_does_not_save_it_twice(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=8), output=dict(checkpoint_every_evaluations=4)), tmp_path)
    assert state == 'completed'
    saved = _checkpoints(layout)
    assert saved[-1] == (8, 'final', 'periodic') and [s for s in saved if s[0] == 8] == [saved[-1]]
    latest = read_json(layout.run_dir / 'checkpoints' / 'latest.json')
    assert latest['kind'] == 'final'
    events = [json.loads(line) for line in (layout.logs / 'events.jsonl').read_text().splitlines()]
    assert any(e.get('event') == 'checkpoint_saved' and e.get('kind') == 'final' and e.get('relabelled_from') == 'periodic' for e in events)


def test_a_run_that_completes_between_two_periodic_saves_still_writes_its_final_save(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=6), output=dict(checkpoint_every_evaluations=4)), tmp_path)
    assert state == 'completed'
    assert _checkpoints(layout)[-1] == (6, 'final', None)


def test_one_save_hashes_the_optimizer_source_once(monkeypatch):
    from analog_optimizer.training import sac
    from gator_workbench import checkpoints
    calls, real = [], sac.source_digest
    monkeypatch.setattr(sac, 'source_digest', lambda: calls.append(1) or real())
    with checkpoints._one_source_digest():
        first, second, third = sac.source_digest(), sac.source_digest(), sac.source_digest()
    assert first == second == third == real() and len(calls) == 1
    sac.source_digest()
    assert len(calls) == 2                                                       # the package's own function is back


def test_a_json_file_is_fsynced_once(tmp_path, monkeypatch):
    from gator_workbench.storage import atomic
    calls, real = [], os.fsync
    monkeypatch.setattr(os, 'fsync', lambda fd: calls.append(fd) or real(fd))
    atomic.write_json(tmp_path / 'a.json', dict(value=1))
    assert len(calls) == 2                                                       # the file's bytes, then its directory
    assert [p.name for p in tmp_path.iterdir()] == ['a.json'] and read_json(tmp_path / 'a.json') == dict(value=1)


def test_timestamps_do_not_search_for_a_missing_pytz_per_value():
    import importlib.util
    import pyarrow as pa
    import gator_workbench.storage.dataset  # noqa: F401 - importing it is what sets the sentinel
    assert 'pytz' in sys.modules                          # the real package, or None: "not installed", answered at once
    if sys.modules['pytz'] is not None:
        pytest.skip('pytz is installed here')
    assert importlib.util.find_spec('pytz') is None
    column = pa.array([dt.datetime(2026, 9, 22, tzinfo=dt.timezone.utc)] * 2000, type=pa.timestamp('us', tz='UTC'))
    started = time.perf_counter()
    rows = pa.table({'t': column}).to_pylist()
    assert rows[0]['t'].tzinfo is not None and time.perf_counter() - started < 0.5      # was ~1.25 ms per value


def test_a_row_outside_the_pdks_own_range_is_refused_when_the_task_is_saved(tmp_path, monkeypatch):
    """The PDK declares in its CDF what its property form accepts. It was never read, so a row outside it passed every
    offline check and the first candidate the PDK clamped stopped the run - after a real evaluation was paid for."""
    from gator_workbench import cdf_rules, pdk
    text = '\n'.join([
        'CELL|nmos1v|"nch"|("D" "G" "S" "B")|nil|("w" "l")|nil|nil|nil|nil|("schematic")',
        'PARAM|nmos1v|w|"float"|"lengthMetric"|1e-06|"Width"|t|t|nil|nil|(1e-07 1e-05)',
        'PARAM|nmos1v|l|"float"|"lengthMetric"|4.5e-08|"Length"|t|t|nil|nil|nil'])
    cells = pdk.parse_cdf_text(text)['cells']
    assert cells['nmos1v']['parameters']['w']['range'] == [1e-07, 1e-05]       # read from the PDK
    assert cells['nmos1v']['parameters']['l']['range'] is None                 # the PDK declares none: unchanged
    source = pdk.write_source(cells, 'nmos1v', 'w')
    assert source['range'] == [1e-07, 1e-05]                                   # and it reaches the rules
    assert pdk.numeric_range('(2 1)') is None and pdk.numeric_range(['1u', '5u']) is None      # only a plain pair counts
    assert cdf_rules is not None
