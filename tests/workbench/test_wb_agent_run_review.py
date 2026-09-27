"""What a run produced, as the digest an agent is given (it reads no file), and the request built on it.
Fake CLI fixtures and a real MOCK run only - no model is called."""
import json

from fastapi.testclient import TestClient
import pytest

from gator_workbench.agents import AgentError, AgentRequest, prompts, run_digest
from helpers import cli, execute, make_config, workbench_app


def evaluation(i, *, feasible=False, violation=0.1, status='ok', source='sac_policy', reward=-0.1, valid=True):
    return dict(evaluation_id=f'e{i}', completion_index=i, dispatch_index=i, cumulative_evaluations_charged=i, phase='search', action_source=source,
                status=status, failure_type=None if status == 'ok' else 'simulation', diagnostics=None if status == 'ok' else 'Spectre did not converge',
                valid=valid, all_hard_constraints_satisfied=feasible, normalized_constraint_violation=0.0 if feasible else violation, reward=reward,
                best_so_far_feasible=feasible, best_so_far_violation=0.0 if feasible else violation, provenance='mock')


def rows(n):
    evaluations = [evaluation(i, feasible=i >= 9, violation=0.5 / i, reward=-0.5 / i, source='random_warmup' if i <= 3 else 'sac_policy') for i in range(1, n + 1)]
    evaluations[1] = evaluation(2, status='nonconverged', valid=False, source='random_warmup')
    parameters = [dict(evaluation_id=f'e{i}', role='independent', variable_id='width', executed_value=8e-6 if i > 4 else 2e-6) for i in range(1, n + 1)]
    parameters += [dict(evaluation_id=f'e{i}', role='bound_member', variable_id='width', executed_value=1.0) for i in range(1, n + 1)]
    metrics = [dict(evaluation_id=f'e{i}', metric_name='gain', aggregation_level='aggregate', raw_value=40.0 + i, valid=i != 2, satisfied=(40.0 + i) >= 49 if i != 2 else None,
                    failure_reason=None if i != 2 else 'no_crossing') for i in range(1, n + 1)]
    return evaluations, parameters, metrics


CONFIG = dict(parameters=[dict(variable_id='width', lower=1e-6, upper=8e-6, unit='m'), dict(variable_id='width__m2', binding_group='width')],
              targets=[dict(metric_id='gain', constraint='>=', lower=49.0, unit='dB')], run=dict(seed=7, max_evaluations=12, advanced=dict(batch_size=8)))


def test_the_digest_says_what_happened_where_the_search_went_and_what_failed():
    evaluations, parameters, metrics = rows(12)
    status = dict(state='completed', stop_reason='budget_exhausted', budget=dict(max_evaluations=12, charged=12, completed=11, failed=1), learner_updates=8,
                  first_feasible=dict(first_feasible_eval_count=9), best_design=dict(evaluation_id='e11'))
    digest = run_digest.build(status=status, config=CONFIG, evaluations=evaluations, parameters=parameters, metrics=metrics,
                              updates=[dict(critic_loss=1.0 / k, alpha=0.2) for k in range(1, 10)], errors=[dict(error='nonconverged', message='Spectre did not converge')])
    assert digest['run']['state'] == 'completed' and digest['budget']['charged'] == 12 and digest['evaluations'] == 12 and digest['valid_evaluations'] == 11
    assert digest['feasible_evaluations'] == 4 and digest['first_feasible']['first_feasible_eval_count'] == 9
    assert digest['best']['charged'] == 11 and digest['best']['parameters'] == dict(width=8e-6)          # the run's OWN choice of the best design
    width = digest['variables'][0]
    assert [v['variable_id'] for v in digest['variables']] == ['width']                                   # leaders only, not bound members
    assert width['share_at_upper_bound'] == pytest.approx(8 / 12, abs=1e-3) and width['at_best'] == 8e-6  # it piled up at the upper bound
    gain = digest['targets'][0]
    assert gain['reached'] == dict(n=11, min=41.0, median=47.0, max=52.0) and gain['at_best'] == 51.0 and gain['invalid_because'] == dict(no_crossing=1)
    assert gain['share_satisfied'] == pytest.approx(4 / 11, abs=1e-3)
    assert digest['failures'] == dict(count=1, by_status=dict(nonconverged=1), by_type=dict(simulation=1), typical=['Spectre did not converge'])
    assert digest['training']['evaluations_by_how_chosen'] == dict(random_warmup=3, sac_policy=9) and digest['training']['critic_loss_trend']['n'] == 9
    assert digest['training']['policy_reward_trend']['last_third_mean'] > digest['training']['policy_reward_trend']['first_third_mean']
    assert any('MOCK' in line for line in digest['caveats']) and any('anecdote' in line for line in digest['caveats'])
    assert len(json.dumps(digest)) < 12000 and 'NaN' not in json.dumps(digest)                          # bounded, and plain JSON


def test_too_little_data_is_said_as_null_and_an_empty_run_is_not_an_error():
    empty = run_digest.build(status=dict(state='starting', worker_alive=True), config=CONFIG, evaluations=[], parameters=[], metrics=[], updates=[], errors=[])
    assert empty['best'] is None and empty['progress'] == [] and empty['training']['policy_reward_trend'] is None
    assert empty['targets'][0]['reached'] is None and any('still going' in line for line in empty['caveats'])
    few = run_digest.build(status={}, config=CONFIG, evaluations=[evaluation(1, reward=float('nan'))], parameters=[], metrics=[], updates=[], errors=[])
    assert few['best']['reward'] is None                                                                  # a NaN never reaches the prompt


def test_a_run_review_needs_a_run_and_shows_its_results_as_data(tmp_path):
    config = make_config(tmp_path).model_dump(mode='json')
    with pytest.raises(AgentError) as error:
        AgentRequest(kind='run_review', user_prompt='what happened?', config=config, circuit_summary=None).validate()
    assert 'choose one' in error.value.detail
    request = AgentRequest(kind='run_review', user_prompt='what happened?', config=config, circuit_summary=dict(devices=[]),
                           results=dict(run=dict(state='completed'), caveats=['MOCK run']), review=dict(settings=dict(run=dict(fields={}))))
    text = prompts.build_prompt(request.validate())
    assert 'REQUEST KIND: run_review' in text and '<run_results_data>' in text and '"state": "completed"' in text and '<settings_data>' in text
    assert 'Reviewing a run' in text and 'Reviewing settings' not in text and 'The smallest startable setup' not in text   # only its own part of the brief
    assert 'ONLINE RESEARCH' not in text
    with pytest.raises(AgentError):
        AgentRequest(kind='run_review', user_prompt='x', config=config, circuit_summary=None, results=dict(run={}), web=True).validate()   # never online


@pytest.fixture
def client(tmp_path, cli):
    cli('settings_review')
    return TestClient(workbench_app(tmp_path))


def test_a_real_mock_run_is_condensed_and_handed_to_the_agent_over_http(client, tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=12))
    layout, engine = execute(config, tmp_path)
    digest = run_digest.load(layout.run_dir)
    assert digest['run']['mock'] and digest['evaluations'] == 12 and digest['budget']['charged'] == 12 and digest['best'] is not None
    assert {v['variable_id'] for v in digest['variables']} == {row['variable_id'] for row in config.model_dump(mode='json')['parameters'] if not row.get('binding_group')}
    raw = config.model_dump(mode='json')
    reply = client.post('/api/agent/propose', json=dict(kind='run_review', prompt='What happened in this run?', config=raw, run_dir=str(layout.run_dir)))
    proposal = reply.json()
    assert reply.status_code == 200 and proposal['kind'] == 'run_review'
    assert [s['path'] for s in proposal['suggestions']] == ['run.advanced.batch_size', 'run.network.encoder_type'] and 'applicable' in proposal['suggestions'][0]
    sent = json.loads((tmp_path / 'record.json').read_text())
    assert '<run_results_data>' in sent['stdin'] and '"charged": 12' in sent['stdin'] and '--allowedTools' not in sent['argv'] and sent['files_in_cwd'] == []
    missing = client.post('/api/agent/propose', json=dict(kind='run_review', prompt='x', config=raw))
    assert missing.status_code == 409 and 'choose one' in missing.json()['detail']['detail']
    outside = client.post('/api/agent/propose', json=dict(kind='run_review', prompt='x', config=raw, run_dir='/etc'))
    assert outside.status_code in (403, 404)                                                               # only a run inside the allowed roots
