"""A finished baseline records itself (record 7.78): a single baseline simulation becomes the reference, a refused one is remembered and said, one made before is adopted, a Maestro-measured task records its own outputs (refactoring package D4: from test_wb_profiles)."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from gator_workbench import profiles, recipes, schema, tasks
from gator_workbench.storage.atomic import sha256_file

from helpers import probe, workbench_app
from ring_cell_support import config, connection_file, read_cell
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module


# ------------------------------------------------------------------------------------------------ a finished baseline records itself (7.78)
RING_VALUES = dict(zip(recipes.RING_METRICS, (1.2092e9, 1.96e-4, 1.96e-4, 0.999, 0.508, 1e-6, 1e-6, 3.1e-9)))


def baseline_run(tmp_path, monkeypatch, run_dir, *, run_id='r1', run_kind='baseline_preflight', state='completed', mock=False,
                 task_key='real:ring_osc_3stage', created='2026-09-23T22:45:18+00:00', valid=True, circuit=None):
    """A Baseline simulation of the ring task as its run directory holds it: the manifest the worker writes
    (run_kind, circuit.task_key, state) and the tables the reference is read from (a fake reader, counted)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'effective_config.json').write_text(json.dumps(dict(circuit=dict(source='registered_task', task_id=task_key))))
    directory = profiles.profile_dir('ring_osc_3stage')
    facts = dict(task_key=task_key, netlist_sha256=sha256_file(directory / 'structure.scs'),
                 parser_config_sha256=sha256_file(directory / 'mapping.json'), **(circuit or {}))
    manifest = dict(run_id=run_id, mock=mock, run_kind=run_kind, state=state, created_utc=created, circuit=facts,
                    segments=[dict(segment=1, ended_utc='2026-09-23T22:45:32+00:00')], notes=[])
    (run_dir / 'run_manifest.json').write_text(json.dumps(manifest))
    tables = dict(
        evaluations=[dict(evaluation_id='e0', phase='baseline', provenance='real', result_source='simulation', completed_at='2026-09-23T22:45:30')],
        metrics=[dict(evaluation_id='e0', measurement_id=None, metric_name=k, raw_value=v, unit=recipes.RING_METRICS[k], valid=valid,
                      aggregation_level='condition') for k, v in RING_VALUES.items()])
    reads = []

    class FakeReader:
        """A reader that serves projected baseline rows from the fixture tables."""
        def __init__(self, data_dir):
            reads.append(Path(data_dir))

        def rows(self, table, columns=None):
            return [{c: row[c] for c in columns} for row in tables[table]]
    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', FakeReader)
    return manifest, reads


def test_a_finished_single_baseline_simulation_records_itself(tmp_path, monkeypatch):
    """Record 7.78: after the user's first real baseline the column still said "no real baseline yet" - recording the
    reference was a press of its own. The worker now asks for it at the end of a baseline_preflight run."""
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    entry_file = profiles.profile_dir('ring_osc_3stage') / profiles.FILES['entry']
    entry_file.write_text(json.dumps(dict(json.loads(entry_file.read_text()), saved_utc='2026-09-23T02:56:41+00:00')))   # as Save task records it
    run_dir = tmp_path / 'run1'
    manifest, reads = baseline_run(tmp_path, monkeypatch, run_dir)
    # not one to record: an optimization run, a MOCK run, a verified built-in circuit - nothing to say
    assert profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, run_kind='optimization')) is None
    assert profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, mock=True)) is None
    assert profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, circuit=dict(manifest['circuit'], task_key='real:gpdk045_ota7'))) is None
    # a run that did not complete, or one the task has outlived (saved again after it): said, not recorded
    ended = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, state='failed'))
    assert ended['recorded'] is False and 'ended as failed' in ended['note']
    stale = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, circuit=dict(manifest['circuit'], netlist_sha256='0' * 64)))
    assert stale['recorded'] is False and 'saved again after that run' in stale['note']
    older = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, created_utc='2020-01-01T00:00:00+00:00'))
    assert older['recorded'] is False and 'saved again after that run' in older['note']
    assert profiles.reference_metrics('ring_osc_3stage') is None and not reads
    # the run as it is: recorded, from the run's own tables
    done = profiles.adopt_baseline_run(run_dir)                       # the manifest read from the run directory
    assert done['recorded'] is True and done['name'] == 'ring_osc_3stage' and done['note'].startswith('Recorded as the reference of real:ring_osc_3stage')
    assert profiles.reference_metrics('ring_osc_3stage') == RING_VALUES and reads == [run_dir / 'data']
    entry = profiles.list_profiles()['ring_osc_3stage']
    assert entry['status'].startswith('baseline recorded') and entry['baseline_recorded_utc'] and 'baseline_attempt' not in entry
    # never replaced: a second baseline run says so and reads no table
    again = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, run_id='r2'))
    assert again['recorded'] is False and 'never replaced' in again['note'] and len(reads) == 1


def test_a_refused_baseline_is_remembered_and_said_until_a_good_one_comes(tmp_path, monkeypatch):
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    bad = tmp_path / 'bad'
    manifest, reads = baseline_run(tmp_path, monkeypatch, bad, run_id='bad1', valid=False)
    refused = profiles.adopt_baseline_run(bad)
    assert refused['recorded'] is False and 'not a complete, valid measurement' in refused['note']
    attempt = profiles.list_profiles()['ring_osc_3stage']['baseline_attempt']
    assert attempt['run_id'] == 'bad1' and attempt['run_dir'] == str(bad) and attempt['ended_utc'] == '2026-09-23T22:45:32+00:00'
    assert 'not a complete, valid measurement' in attempt['reason']
    # the same run again (the task loaded once more): the answer is known, no table is read
    assert profiles.adopt_baseline_run(bad)['note'] == refused['note'] and len(reads) == 1
    # the column is told why the task still has no baseline
    loaded = tasks.load_task(schema.CircuitReference.model_validate(dict(source='registered_task', task_id='real:ring_osc_3stage')))
    assert loaded.circuit['baseline_recorded'] is False and loaded.circuit['baseline_attempt']['run_id'] == 'bad1'
    # a good one afterwards: recorded, and the refusal goes with it
    good = tmp_path / 'good'
    baseline_run(tmp_path, monkeypatch, good, run_id='good1')
    assert profiles.adopt_baseline_run(good)['recorded'] is True
    entry = profiles.list_profiles()['ring_osc_3stage']
    assert 'baseline_attempt' not in entry and profiles.reference_metrics('ring_osc_3stage') == RING_VALUES


def test_a_baseline_made_before_is_adopted_when_the_task_is_loaded(tmp_path, monkeypatch):
    """The user's own case (2026-09-24): the baseline run was made before runs recorded themselves. Loading the task
    finds the newest completed Baseline simulation of the task under the remembered output root and records it;
    no output root remembered (no run ever made here) - nothing is scanned."""
    from gator_workbench import runs
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    out = tmp_path / 'out'
    older = out / 'experiment__a' / 'runs' / 'ring_osc_3stage.baseline' / 'scratch__seed1__older'
    newest = out / 'experiment__a' / 'runs' / 'ring_osc_3stage.baseline' / 'scratch__seed2__newest'
    running = out / 'experiment__b' / 'runs' / 'ring_osc_3stage.baseline' / 'scratch__seed3__running'
    other = out / 'experiment__b' / 'runs' / 'other' / 'scratch__seed4__other'
    baseline_run(tmp_path, monkeypatch, older, run_id='older', created='2026-09-22T10:00:00+00:00')
    baseline_run(tmp_path, monkeypatch, running, run_id='running', state='running', created='2026-09-24T10:00:00+00:00')
    baseline_run(tmp_path, monkeypatch, other, run_id='other', task_key='real:gpdk045_ota7', created='2026-09-24T11:00:00+00:00')
    _, reads = baseline_run(tmp_path, monkeypatch, newest, run_id='newest', created='2026-09-23T22:45:18+00:00')
    (out / 'mock' / 'experiment__m' / 'runs' / 'x' / 'y').mkdir(parents=True)
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
    registered = dict(circuit=dict(source='registered_task', task_id='real:ring_osc_3stage'))
    assert client.post('/api/circuit/load', json=registered).json()['baseline_recorded'] is False and not reads      # nothing remembered: no scan
    runs.save_settings(output_root=str(out))
    loaded = client.post('/api/circuit/load', json=registered).json()
    assert loaded['baseline_recorded'] is True and loaded['baseline_attempt'] is None and reads == [newest / 'data']
    assert any('only its recorded baseline has been simulated' in note for note in loaded['notes'])
    assert profiles.list_profiles()['ring_osc_3stage']['baseline_recorded_utc']
    assert client.post('/api/virtuoso/profile/reference', json=dict(name='ring_osc_3stage')).json()['detail']['code'] == 'reference_refused'


def test_a_maestro_measured_task_records_its_own_outputs_as_the_reference(tmp_path, monkeypatch):
    """Found on the user's first real baseline (2026-09-24, a Maestro task with outputs freq / vmax): record_reference
    expected the recipe's results, and a Maestro recipe has none, so every Maestro baseline was refused as "unexpected
    metrics". The task's own provided_metrics are what its baseline holds."""
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    entry_file = profiles.profile_dir('ring_osc_3stage') / profiles.FILES['entry']
    entry_file.write_text(json.dumps(dict(json.loads(entry_file.read_text()), recipe=profiles.MAESTRO, provided_metrics=['freq', 'vmax'])))
    run_dir = tmp_path / 'maestro_run'
    baseline_run(tmp_path, monkeypatch, run_dir, run_id='m1')
    outputs = dict(freq=1208362157.05, vmax=1.0027)
    tables = dict(evaluations=[dict(evaluation_id='e0', phase='baseline', provenance='real', result_source='simulation', completed_at='2026-09-23T22:45:30')],
                  metrics=[dict(evaluation_id='e0', measurement_id=None, metric_name=k, raw_value=v, unit=None, valid=True, aggregation_level='condition') for k, v in outputs.items()]
                  + [dict(evaluation_id='e0', measurement_id='m_freq', metric_name='freq', raw_value=1208362157.05, unit='Hz', valid=True, aggregation_level='aggregate')])

    class MaestroReader:
        """A reader that serves the fixture's recorded Maestro outputs."""
        def __init__(self, data_dir):
            pass

        def rows(self, table, columns=None):
            return [{c: row[c] for c in columns} for row in tables[table]]
    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', MaestroReader)
    done = profiles.adopt_baseline_run(run_dir)
    assert done['recorded'] is True, done
    assert profiles.reference_metrics('ring_osc_3stage') == outputs
