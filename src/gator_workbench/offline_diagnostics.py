"""Read-only checks of archived offline models; no simulator and no weight updates."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import math

from . import checkpoints, network_inputs
from .model_structure import schemas
from .pretrain import Pool, evaluate, identity, prepare_pool
from .storage.atomic import read_json, write_json
from .trajectory import TrajectoryLoader


def load_model(directory):
    """Restore standard-feature inference weights without unpickling training state."""
    import torch
    import torch_geometric
    from analog_optimizer.measurements.specs import RewardSettings
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.sac import SACConfig, SACLearner
    directory = Path(directory)
    meta = checkpoints.read_metadata(directory)
    c = meta['contract']
    if c['torch_version'] != str(torch.__version__) or c['pyg_version'] != str(torch_geometric.__version__):
        raise ValueError('Saved model requires matching torch and torch-geometric versions')
    if c['condition_policy'] != 'off':
        raise ValueError('Offline diagnostics currently require nominal conditions')
    features, spec_schema = schemas(c)            # the standard list, or a model of the transferable inputs (7.298)
    learner = SACLearner(experiment=meta['experiment'], feature_schema=features,
                         spec_schema=spec_schema, model_config=ModelConfig(**c['model_config']),
                         config=SACConfig(**c['sac_config']), reward_settings=RewardSettings(**c['reward_settings']))
    weights = checkpoints.load_weights(directory)
    for name in ('actor', 'critics', 'targets'):
        module = getattr(learner, name)
        module.load_state_dict(weights[name])
        module.eval()
    with torch.no_grad():
        learner.log_alpha.copy_(weights['log_alpha'])
    learner.updates = weights['updates']
    return learner, meta


def proposals(learner, observations, *, best_recorded_reward, reward_rmse):
    """Describe deterministic policy proposals and critic optimism without simulation or weight updates."""
    import torch
    from analog_optimizer.parameters.actions import ActionMapper
    rows = []
    with torch.no_grad():
        for observation in observations:
            batch = learner.batch([observation])
            sample = learner.actor.sample(batch, deterministic=True)
            proposal = batch.proposals(sample.actions)[0]
            applied = ActionMapper(observation.graph, copy=False).legalize(proposal)
            q1, q2 = (float(q(batch, sample.actions).item()) for q in learner.critics)
            rows.append(dict(proposal=proposal, legal=all(math.isfinite(v) for v in applied.assignments.values()),
                             boundary_fraction=sum(abs(v) > .99 for v in proposal.values()) / len(proposal),
                             q1=q1, q2=q2, conservative_q=min(q1, q2),
                             above_recorded_best=min(q1, q2) - best_recorded_reward,
                             exceeds_best_by_three_rmse=min(q1, q2) > best_recorded_reward + 3 * reward_rmse))
    return rows


def _rewards(transitions) -> list:
    """The rewards of a pool's transitions: a list, or a pool kept on disk (`offline_storage.DiskSequence`, which has no `+`
    and whose references hold the rewards - no transition is read back for them; record 7.352)."""
    references = getattr(transitions, 'references', None)
    return [r.reward for r in references] if references is not None else [t.reward for t in transitions]


def qualify(training_dir, *, progress=None):
    """Write raw diagnostic data. The three-RMSE flag is a review signal, not a measured reward."""
    import torch
    torch.set_num_threads(1)
    directory = Path(training_dir)
    request = read_json(directory / 'request.json')
    recorded = read_json(directory / 'pool.json')
    # Said before the pool is rebuilt (record 7.352): rebuilding the archive pool of record 7.336 takes hours, and these
    # pools were refused only after it.
    if network_inputs.any_transfer(recorded.get('inputs') or {}):
        raise ValueError('The specialist comparison reads the pool as its specialists saw it; a pool read with the '
                         'transferable network inputs (record 7.298) is not compared yet')
    if recorded.get('reward_migration'):
        raise ValueError('The specialist comparison scores each specialist on the rewards it was trained with; a pool whose '
                         'rewards were recomputed (migrate_reward_settings) is not compared yet')
    pool = prepare_pool(request, progress=progress)
    if recorded['request_sha256'] != pool.audit['request_sha256'] or recorded['split_sha256'] != pool.audit['split_sha256']:
        raise ValueError('Qualification must use exactly the training pool and split')
    was, now = ({s['run_id']: s.get('inputs_sha256') for s in audit['sources']} for audit in (recorded, pool.audit))
    if any(was[run] is not None and was[run] != now.get(run) for run in was):         # record 7.319; older pools pinned none
        raise ValueError('Qualification must show the pool as the training saw it: the network inputs of a source changed '
                         '(its PDK was loaded again, or its task\'s spec descriptions or test variables changed)')
    learner, meta = load_model(checkpoints.resolve_checkpoint(directory, 'latest'))
    if identity(asdict(learner.spec_schema)) != identity(recorded['spec_schema']):
        raise ValueError('Model registry differs from the pool')
    curve = read_json(directory / 'validation.json')
    scores = evaluate(learner, pool)
    report = dict(checkpoint=meta['checkpoint_id'], updates=learner.updates,
                  pool_sha256=pool.audit['request_sha256'], split_sha256=pool.audit['split_sha256'],
                  new_simulator_launches=0, tasks={},
                  interpretation='Specialists may have trained on source holdout episodes: descriptive reference, not '
                                 'an independent validation baseline. Predicted proposal Q is not a circuit result.')
    sources = pool.audit['sources']
    for task, heldout in pool.validation.items():
        base = task[:-2] if task.endswith('_b') else task
        source = next(s for s in sources if s['task'] == base)
        specialist, specialist_meta = load_model(checkpoints.resolve_checkpoint(source['run_dir'], 'latest'))
        specialist_scores = evaluate(specialist, Pool({task: pool.training[task]}, {task: heldout},
                                                    specialist.spec_schema, pool.reward_settings, {}))[task]
        # First recorded observation is the task's measured starting state, independent of the holdout draw.
        task_source = next(s for s in sources if s['task'] == task)
        loader = TrajectoryLoader(task_source['run_dir'])
        first = next(r for r in loader.transition_rows() if r['replay_eligible_archive'])
        states = [loader.observation(first['state_ref'])] + [t.observation for t in heldout[:20]]
        best = max(_rewards(pool.training[task]) + _rewards(heldout))
        rmse = math.sqrt(max(scores[task]['q1_mse'], scores[task]['q2_mse']))
        checks = proposals(learner, states, best_recorded_reward=best, reward_rmse=rmse)
        errors = [max(row['scores'][task]['q1_mse'], row['scores'][task]['q2_mse']) for row in curve]
        report['tasks'][task] = dict(general=scores[task], specialist=specialist_scores,
                                    specialist_run=source['run_id'], specialist_code=specialist_meta['contract']['code_sha256'],
                                    specialist_training_overlap_possible=True, best_recorded_reward=best,
                                    proposal_rows=checks, proposals_above_best_plus_three_rmse=sum(
                                        r['exceeds_best_by_three_rmse'] for r in checks),
                                    final_over_best_validation=max(scores[task]['q1_mse'], scores[task]['q2_mse']) / min(errors))
        write_json(directory / 'qualification.json', report)
        if progress:
            progress(dict(task=task, checks=len(checks), flagged=report['tasks'][task]['proposals_above_best_plus_three_rmse'],
                          general_mse=max(scores[task]['q1_mse'], scores[task]['q2_mse']),
                          specialist_mse=max(specialist_scores['q1_mse'], specialist_scores['q2_mse'])))
    report['complete'] = True
    report['requires_review'] = [task for task, r in report['tasks'].items()
                                  if r['proposals_above_best_plus_three_rmse'] or not all(p['legal'] for p in r['proposal_rows'])]
    write_json(directory / 'qualification.json', report)
    return report
