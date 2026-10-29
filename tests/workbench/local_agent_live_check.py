"""Explicit opt-in local GPU lifecycle check. Never run as part of pytest.

Usage: PYTHONPATH=src python tests/workbench/local_agent_live_check.py <scratch-folder>
Uses already-present pinned benchmark assets; never downloads weights, runs a simulator,
or calls a paid service. Evidence is synthetic advisory interaction, not circuit results.
"""
import json
import os
from pathlib import Path
import sys
import time

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = str(root / 'settings')
from gator_workbench.local_agent.manager import Manager
from gator_workbench.local_agent.catalog import CATALOG
from gator_workbench.local_agent.runtime import asset_root

service = Manager(root / 'agent')
report = dict(origin='synthetic', provenance='mock', model='bolt-74b', generation_tokens=-1,
              context_shift=True, keep=-1, checks=[])


def finish(response):
    last = None
    while True:
        job = service.job(response['job_id'])
        if job['phase'] != last:
            print(job['kind'] + ': ' + job['phase'], flush=True); last = job['phase']
        if job['state'] != 'running':
            report['checks'].append(job)
            (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            if job['state'] == 'failed':
                raise RuntimeError(job['error'])
            return job
        time.sleep(.25)


try:
    source = asset_root() / 'models' / CATALOG['bolt-74b'].filename
    before = (source.stat().st_size, source.stat().st_mtime_ns)
    check = service.preflight('bolt-74b')
    report['compatibility'] = check
    print(json.dumps(check), flush=True)
    assert check['compatible'], check['errors']
    if not service._path(CATALOG['bolt-74b']):
        finish(service.install('bolt-74b', local_only=True))
    finish(service.deploy('bolt-74b'))
    config = dict(circuit=dict(source='registered_task', task_id='synthetic:local-agent-smoke'),
                  parameters=[], run=dict(max_evaluations=20), output={}, research={})
    # No proposed changes requested: offline semantic validation is covered by test_local_agent.py.
    class NoCircuit:
        def load_config(self, raw):
            raise ValueError('This synthetic interaction does not have a simulator circuit.')
    messages = [dict(role='user', content='Explain the difference between 500 nm and 0.5 um in one sentence. No editor changes; proposal must be null.')]
    first = finish(service.chat('bolt-74b', config, messages, NoCircuit()))
    assert first['result']['proposal'] is None and first['result']['message']
    messages += [dict(role='assistant', content=first['result']['message']),
                 dict(role='user', content='Continue: convert that same length to meters. No editor changes; proposal null.')]
    second = finish(service.chat('bolt-74b', config, messages, NoCircuit()))
    assert second['result']['message']
    pending = service.chat('bolt-74b', config, [dict(role='user', content='Describe 500 distinct safe software test cases in detail. No proposed editor changes.')], NoCircuit())
    # Wait until the owned native inference starts, then cancel it (not just a queued request).
    job_folder = service.jobs[pending['job_id']]['folder']
    while not (job_folder / 'inference' / 'stdout.txt').exists():
        if service.job(pending['job_id'])['state'] != 'running':
            raise AssertionError('Cancellation check finished before native inference started')
        time.sleep(.1)
    service.undeploy('bolt-74b')
    assert finish(pending)['state'] == 'cancelled'
    assert service.deployed is None
    assert service.delete('bolt-74b')['external_file_preserved']
    assert before == (source.stat().st_size, source.stat().st_mtime_ns)
    report['lifecycle_passed'] = True
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS: install, actual deployment, uncapped chat, continuation, native cancellation, undeploy and safe delete.', flush=True)
finally:
    service.close()
