"""The agent's whole Virtuoso setup (request kind `virtuoso_setup`): what it is told, what it may return, what the backend
refuses before anyone can approve it, and what "Approve and apply" does - the rows go into the editors, the approved setup
into the cell's WORKING COPY (read back). FAKE write process and manually imported agent results - no agent CLI, no
Virtuoso, no simulation."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_setup, schema, virtuoso_setup as vs, working_copy
from gator_workbench.agents import AgentError, AgentRequest
from gator_workbench.agents.base import SECTIONS_BY_KIND
from gator_workbench.agents.prompts import PROPOSAL_SCHEMA, build_prompt
from gator_workbench.api import create_app
from test_wb_api import probe
from test_wb_profiles import ROWS, connection_file, read_cell
from test_wb_virtuoso_setup import setup_writer
from test_wb_working_copy import CELL, COPY, LIB, TB, fake_writer

PROBES = [dict(measurement_id='m_freq', analysis='tran', result_source='ade_output', source_name='freq', signal='frequency(VT("/OUT"))', unit='Hz'),
          dict(measurement_id='m_vmax', analysis='tran', result_source='ade_output', source_name='vmax', signal='ymax(VT("/OUT"))', unit='V')]
SPECS = [dict(metric_id='freq', equation='m_freq', unit='Hz', constraint='>=', lower=1.1e9, normalization_scale=1e9, basis='the user asked for >1.1 GHz')]
SETUP = dict(analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}})


def patch_for(rows=ROWS, probes=PROBES, specs=SPECS):
    ops = [dict(op='add', section='parameters', key=r['variable_id'], value=r) for r in rows]
    ops += [dict(op='add', section='measurements', key=p['measurement_id'], value=p) for p in probes]
    ops += [dict(op='add', section='targets', key=t['metric_id'], value=t) for t in specs]
    return ops


def answer(**changes):
    return dict(dict(kind='virtuoso_setup', reasoning='A three-stage ring oscillator: three inverters in a loop.', patch=patch_for(),
                     setup=SETUP, warnings=[], unresolved=[]), **changes)


def config():
    return schema.WorkbenchConfig.model_validate(dict(
        circuit=dict(source='virtuoso', library=LIB, cell=CELL, testbench_cell=TB, circuit_class='vco'),
        run=dict(max_evaluations=5, connection_profile_id='lab'))).model_dump(mode='json')


@pytest.fixture
def client(tmp_path, monkeypatch):
    connection_file()
    read_cell(tmp_path)
    assert working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))['verified']
    readback = working_copy.native_cells.cell_dir(LIB, CELL) / 'testbench_readback.json'
    bench = json.loads(readback.read_text())
    return TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path))), bench


def test_the_request_says_what_the_copy_is_and_what_may_be_returned():
    assert SECTIONS_BY_KIND['virtuoso_setup'] == ('parameters', 'targets', 'measurements') and 'setup' in PROPOSAL_SCHEMA['properties']
    with pytest.raises(AgentError, match='Make a working copy'):
        AgentRequest(kind='virtuoso_setup', user_prompt='set it up', config=config(), circuit_summary=None).validate()
    copy = dict(copy=dict(library=COPY, cell=CELL, testbench=TB), allowed_functions=sorted(vs.FUNCTIONS),
                bindable=[dict(cell=TB, instance='V0', parameters=['vdc'])])
    prompt = build_prompt(AgentRequest(kind='virtuoso_setup', user_prompt='set it up', config=config(), circuit_summary=None, copy=copy).validate())
    assert 'THIS REQUEST: set this circuit up for optimization in its WORKING COPY' in prompt
    assert '<working_copy_data>' in prompt and '"frequency"' in prompt and 'A PDK device is never bound' in prompt
    assert 'ade_output' in prompt and 'setup.analyses' in prompt


def test_only_a_request_without_circuit_data_hears_that_no_circuit_is_loaded():
    summary = dict(device_count=1, devices=[])
    copy = dict(copy=dict(library=COPY, cell=CELL, testbench=TB), allowed_functions=[], bindable=[])
    plain = build_prompt(AgentRequest(kind='parameters', user_prompt='x', config=config(), circuit_summary=summary).validate())
    assert '<circuit_data>' in plain and 'No circuit is loaded' not in plain and '<working_copy_data>' not in plain
    bare = build_prompt(AgentRequest(kind='parameters', user_prompt='x', config=config(), circuit_summary=None).validate())
    assert 'No circuit is loaded' in bare
    setup = build_prompt(AgentRequest(kind='virtuoso_setup', user_prompt='x', config=config(), circuit_summary=summary, copy=copy).validate())
    assert '<circuit_data>' in setup and '<working_copy_data>' in setup and 'No circuit is loaded' not in setup


def test_a_proposal_carries_the_setup_and_its_approval_is_bound_to_it(client):
    client, _ = client
    body = dict(kind='virtuoso_setup', prompt='Set up the ring oscillator; I need more than 1.1 GHz.', config=config())
    proposal = client.post('/api/agent/import-result', json=dict(body, result=answer())).json()
    assert proposal['setup'] == SETUP and proposal['virtuoso_copy']['library'] == COPY and len(proposal['diff']) == len(ROWS) + 3
    other = client.post('/api/agent/import-result', json=dict(body, result=answer(setup=dict(analyses={'tran': {'stop': '40n'}})))).json()
    assert other['proposal_hash'] != proposal['proposal_hash']                       # the setup is part of what is approved
    rows_only = client.post('/api/agent/import-result', json=dict(body, kind='draft_config', result=answer(kind='draft_config'))).json()
    assert rows_only['setup'] is None                                                 # another kind's setup is dropped, not obeyed


@pytest.mark.parametrize('result, reason', [
    (dict(patch=patch_for(probes=[dict(PROBES[0], signal='system("rm -rf ~")')], specs=[])), 'system() is not a calculator function'),
    (dict(setup=dict(SETUP, variables={'W': '2u'}, bindings=[dict(cell=CELL, instance='MN1', parameter='w', variable='W')])),
     'MN1 in ring_osc_3stage cannot be set by a variable'),
    (dict(setup=dict(analyses={'ac': {'start': '1'}})), 'Outputs read the analyses tran, which setup.analyses does not set'),
    (dict(setup=dict(analyses='tran')), 'setup.analyses must map an analysis name to its options'),
])
def test_a_setup_that_could_not_be_written_is_refused_before_anyone_can_approve_it(client, result, reason):
    client, _ = client
    refused = client.post('/api/agent/import-result', json=dict(kind='virtuoso_setup', prompt='set it up', config=config(), result=answer(**result)))
    assert refused.status_code == 409 and reason in json.dumps(refused.json()['detail'])


def test_approve_and_apply_fills_the_editors_and_writes_the_setup_into_the_copy(client, tmp_path, monkeypatch):
    client, _ = client
    real_run = bridge_setup.run
    back = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], variables={}, bindings=[], raw_specs={},
                analyses={'tran': {'stop': '50n', 'errpreset': 'conservative', 'annotate': 'status'}},
                outputs=[dict(name='freq', expression='frequency(VT("/OUT"))'), dict(name='vmax', expression='ymax(VT("/OUT"))')],
                specs=[dict(output='freq', op='gt', value='1100000000')])
    monkeypatch.setattr(bridge_setup, 'run', lambda profile_id, op, *, args, output, timeout=600.0, command=None:
                        real_run(profile_id, op, args=args, output=output, timeout=timeout, command=setup_writer(tmp_path, back)))
    cfg = config()
    proposal = client.post('/api/agent/import-result', json=dict(kind='virtuoso_setup', prompt='set it up', config=cfg, result=answer())).json()
    assert client.post('/api/agent/approve', json=dict(proposal_id=proposal['proposal_id'], proposal_hash=proposal['proposal_hash'], config=cfg)).status_code == 200
    applied = client.post('/api/agent/apply', json=dict(proposal_id=proposal['proposal_id'], config=cfg)).json()
    assert [m['measurement_id'] for m in applied['config']['measurements']] == ['m_freq', 'm_vmax']
    assert applied['virtuoso']['written'] and applied['virtuoso']['matches'] and applied['virtuoso']['copy']['library'] == COPY
    assert 'written into the working copy' in applied['note'] and 'not your cell' in applied['note']
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert call['op'] == 'write_setup' and call['request']['setup']['analyses'] == {'tran': {'stop': '5e-08', 'errpreset': 'conservative'}}
    assert call['request']['setup']['variables'] is None and call['request']['setup']['bindings'] is None     # not proposed: kept as they are
    assert working_copy.last_written(working_copy.draft_target(LIB, CELL))['analyses']['tran']['stop'] == '5e-08'


def test_when_virtuoso_cannot_be_reached_the_rows_are_still_applied(tmp_path, monkeypatch):
    connection_file()
    read_cell(tmp_path)
    assert working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))['verified']
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path, daemon='failed')))
    cfg = config()
    proposal = client.post('/api/agent/import-result', json=dict(kind='virtuoso_setup', prompt='set it up', config=cfg, result=answer())).json()
    client.post('/api/agent/approve', json=dict(proposal_id=proposal['proposal_id'], proposal_hash=proposal['proposal_hash'], config=cfg))
    applied = client.post('/api/agent/apply', json=dict(proposal_id=proposal['proposal_id'], config=cfg)).json()
    assert len(applied['config']['measurements']) == 2 and not applied['virtuoso']['written']
    assert 'gate blocked' in applied['virtuoso']['error'] and 'Write to Virtuoso' in applied['note']


def test_without_a_working_copy_the_request_says_what_to_do_first(tmp_path):
    connection_file()
    read_cell(tmp_path)
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    refused = client.post('/api/agent/import-result', json=dict(kind='virtuoso_setup', prompt='set it up', config=config(), result=answer()))
    assert refused.status_code == 409 and 'Make the working copy first' in json.dumps(refused.json())
