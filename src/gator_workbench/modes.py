"""The four run modes. Each returns the learner plus an explicit record of what was
loaded and what was reset, which is stored in ``run_manifest.json``.

scratch    random initialization, new run. No weights are loaded.
resume     the SAME task and the SAME run: full training state through the existing strict
           ``SACLearner.load`` (weights, optimizers, temperature, RNG, replay, counters).
fine_tune  compatible weights -> NEW run on a (new) task: fresh replay, optimizers and task
           counters; preprocessing definitions unchanged; parent recorded. The source
           checkpoint is opened read-only and never overwritten. No source replay data and no
           source-task dimensions are mixed in.
frozen     previous policy, NO update of weights, entropy coefficient or normalization.
           Whether actions are deterministic or sampled is recorded.

A compatibility failure raises; nothing here ever falls back to scratch.
"""
from __future__ import annotations

import random

from . import checkpoints as ckpt, model_inputs, network_inputs
from .compile import reward_settings, training_conditions
from .storage.atomic import read_json
from .validation import native_count_columns


def sac_config_from(advanced):
    """Translate advanced run settings into the learner's SAC configuration."""
    from analog_optimizer.training.sac import SACConfig
    return SACConfig(gamma=advanced.gamma, tau=advanced.tau, learning_rate=advanced.learning_rate,
                     initial_alpha=advanced.initial_alpha, alpha_learning_rate=advanced.alpha_learning_rate,
                     target_entropy_per_action=advanced.target_entropy_per_action,
                     max_grad_norm=advanced.max_grad_norm)


def model_config_from(network):
    """Translate network settings into the optimizer's model configuration."""
    from analog_optimizer.models import ModelConfig
    return ModelConfig(hidden_dim=network.hidden_dim, heads=network.heads, layers=network.layers,
                       encoder_type=network.encoder_type, structural_encoding=network.structural_encoding,
                       architecture_version=network.architecture_version)


def seed_everything(seed):
    """Seed Python, NumPy, and PyTorch random generators from the run seed."""
    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed % 2**32)
    torch.manual_seed(seed)


def runtime_options(config, vocabulary=None):
    # ngspice PDK subcircuits can expose additional multiplicity parameters.
    # The compiled action kind is already m/1; retain the native writeback names
    # as separate numeric columns. This does not add current/A action support.
    """Build feature, reward, and condition settings for the configured network inputs."""
    schema = model_inputs.feature_schema(config.run.network, None if vocabulary is None else vocabulary.schema,
                                        native_counts=native_count_columns(config) if vocabulary is None else (),
                                        operating_points=config.run.network.operating_points)
    return dict(feature_schema=schema, reward_settings=reward_settings(config),
                condition_policy=config.run.conditions.policy, planned_conditions=training_conditions(config))


def _new_learner(experiment, model_config, sac_config, spec_schema, vocabulary=None, runtime=None, view=None):
    """`vocabulary`: None = the optimizer's standard component list; a loaded PDK's list (pdk.Vocabulary) otherwise.
    `view`: the transferable inputs' NetworkView (record 7.298), which then includes the PDK list's view. Either way the
    learner is the package's own SACLearner (network_inputs.learner_class only adds a view at its input)."""
    options = model_inputs.learner_options(vocabulary, runtime)
    return network_inputs.learner_class(vocabulary, view)(experiment=experiment, model_config=model_config, config=sac_config,
                                                          spec_schema=spec_schema, **options)


def _encoder_state(state, *, only_encoder):
    if not only_encoder:
        return state
    return {key: value for key, value in state.items() if '.encoder.' in f'.{key}' or key.startswith('encoder.')}


class EncoderFreeze:
    """Keeps loaded encoder weights fixed during fine-tuning.

    ``SACLearner.update`` re-enables gradients on every critic parameter in a ``finally`` block,
    so a one-time ``requires_grad_(False)`` would silently stop holding after the first update.
    The freeze is therefore re-applied immediately before each update, and frozen parameters
    never carry a gradient into the clipping norm.
    """
    def __init__(self, learner):
        self.parameters = [p for module in [learner.actor, *learner.critics] for p in module.encoder.parameters()]

    def apply(self):
        """Freeze the retained encoder parameters and clear their pending gradients."""
        for parameter in self.parameters:
            parameter.requires_grad_(False)
            parameter.grad = None


def current_contract(experiment, model_config, sac_config, spec_schema, vocabulary=None, runtime=None):
    """Build a learner and return its current checkpoint compatibility contract."""
    return ckpt.contract_summary(_new_learner(experiment, model_config, sac_config, spec_schema, vocabulary, runtime))


def build(mode, *, experiment, model_config, sac_config, spec_schema, advanced, seed, origin,
          source_dir=None, source_metadata=None, task_definition_hash=None, vocabulary=None, runtime=None, view=None):
    """Returns dict(learner, replay, run_state, policy, freeze). `vocabulary`: the run's component list (None = standard);
    `view`: its transferable inputs' NetworkView (record 7.298), or None."""
    from analog_optimizer.training.replay import ReplayBuffer
    import torch
    seed_everything(seed)
    policy = dict(mode=mode, source_checkpoint=None, loaded=[], reset=[], frozen_modules=[], notes=[])
    freeze = None
    if mode == 'scratch':
        learner = _new_learner(experiment, model_config, sac_config, spec_schema, vocabulary, runtime, view)
        replay = ReplayBuffer(advanced.replay_capacity, origin=origin, seed=seed)
        policy['reset'] = ['actor', 'critics', 'target_networks', 'temperature', 'optimizers', 'replay_buffer',
                           'task_counters']
        policy['notes'].append('Random initialization; no weights loaded.')
        return dict(learner=learner, replay=replay, run_state=None, policy=policy, freeze=None)

    if source_dir is None or source_metadata is None:
        raise ValueError(f'mode={mode} requires a source checkpoint')
    problems = ckpt.verify_files(source_dir)
    if problems:
        raise ckpt.CheckpointIncompatible(dict(checks=[dict(component='checkpoint files', status='incompatible',
                                                            detail='; '.join(problems))]))
    contract = current_contract(experiment, model_config, sac_config, spec_schema, vocabulary, runtime)
    report = ckpt.check_compatibility(source_metadata, mode=mode, task_definition_hash=task_definition_hash,
                                      contract=contract)
    policy.update(source_checkpoint=dict(checkpoint_id=source_metadata['checkpoint_id'], path=str(source_dir),
                                         run_id=source_metadata['run_id'], task_id=source_metadata['task_id'],
                                         weight_sha256=source_metadata['weight_sha256'],
                                         code_sha256=source_metadata['contract']['code_sha256']),
                  compatibility=report)
    if not report['compatible']:
        raise ckpt.CheckpointIncompatible(report)

    if mode == 'resume':
        options = model_inputs.learner_options(vocabulary, runtime)
        learner, replay, run_state = network_inputs.learner_class(vocabulary, view).load(
            source_dir / 'training_state.pt', experiment=experiment, model_config=model_config,
            config=sac_config, spec_schema=spec_schema, **options)
        policy['loaded'] = list(ckpt.FULL_COMPONENTS)
        policy['notes'].append('Full training state restored; existing counters are retained.')
        return dict(learner=learner, replay=replay, run_state=run_state, policy=policy, freeze=None)

    weights = ckpt.load_weights(source_dir)
    learner = _new_learner(experiment, model_config, sac_config, spec_schema, vocabulary, runtime, view)
    if mode == 'fine_tune':
        only_encoder = advanced.encoder_only_transfer
        learner.actor.load_state_dict(_encoder_state(weights['actor'], only_encoder=only_encoder),
                                      strict=not only_encoder)
        policy['loaded'].append('actor.encoder' if only_encoder else 'actor (encoder + head)')
        if only_encoder:
            policy['reset'].append('actor.head (random)')
        changed_reward = any(source_metadata['contract'].get(key) != contract.get(key) for key in (
            'reward_version', 'reward_settings', 'clearance_rule', 'failure_policy', 'condition_policy', 'planned_conditions'))
        if changed_reward:
            policy['notes'].append('Reward or condition contract changed: actor transfer only; critics/targets, replay and optimizers reset.')
        if advanced.reset_critic or changed_reward:
            policy['reset'] += ['critics (random)', 'target_networks (copy of the new critics)']
        else:
            learner.critics.load_state_dict(_encoder_state(weights['critics'], only_encoder=only_encoder),
                                            strict=not only_encoder)
            learner.targets.load_state_dict(_encoder_state(weights['targets'], only_encoder=only_encoder),
                                            strict=not only_encoder)
            policy['loaded'] += ['critics.encoder', 'target_networks.encoder'] if only_encoder else [
                'twin critics', 'target_networks']
            if only_encoder:
                policy['reset'] += ['critic heads (random)', 'target heads (random)']
        if advanced.reset_temperature:
            policy['reset'].append(f'temperature (initial_alpha={sac_config.initial_alpha})')
        else:
            with torch.no_grad():
                learner.log_alpha.copy_(weights['log_alpha'])
            policy['loaded'].append('temperature (log_alpha)')
        policy['reset'] += ['actor/critic/temperature optimizers (new)', 'replay_buffer (new, target task only)',
                            'task_counters (new)']
        policy['notes'] += ['Preprocessing/normalization definitions are fixed references and unchanged.',
                            ('Pinned source training transitions are mixed with target replay in each update; '
                             'target replay itself starts empty.' if experiment.get('rehearsal') else
                             'No source replay data and no source-task dimensions are mixed in.'),
                            'The source checkpoint was opened read-only; this is a new run with a parent.']
        if advanced.freeze_encoder:
            freeze = EncoderFreeze(learner)
            freeze.apply()
            policy['frozen_modules'] = ['actor.encoder', 'critics[0].encoder', 'critics[1].encoder']
        replay = ReplayBuffer(advanced.replay_capacity, origin=origin, seed=seed)
        return dict(learner=learner, replay=replay, run_state=None, policy=policy, freeze=freeze)

    if mode == 'frozen':
        learner.actor.load_state_dict(weights['actor'])
        learner.critics.load_state_dict(weights['critics'])
        learner.targets.load_state_dict(weights['targets'])
        with torch.no_grad():
            learner.log_alpha.copy_(weights['log_alpha'])
        for module in (learner.actor, learner.critics, learner.targets):
            module.requires_grad_(False).eval()
        learner.updates = int(weights['updates'])     # policy_version of the loaded policy
        policy['loaded'] = ['actor', 'twin critics', 'target_networks', 'temperature (log_alpha)']
        policy['frozen_modules'] = ['all']
        policy['notes'] += ['No weight, entropy-coefficient or normalization updates. No replay, no optimizer steps, '
                            'and no learner_updates rows are produced.']
        return dict(learner=learner, replay=None, run_state=None, policy=policy, freeze=None)
    raise ValueError(f'Unknown mode {mode!r}')


def source_cost(source_run_dir):
    """Pretraining cost of a source model and the provenance chain for de-duplication.

    Unknown stays unknown (None + status); it is never turned into 0.
    """
    from pathlib import Path
    chain, total, known = [], 0, True
    pending, seen = [(Path(source_run_dir), True, set())], set()
    while pending:
        current, follow_parent, ancestors = pending.pop(0)
        summary = read_json(current / 'run_summary.json', default={})
        manifest = read_json(current / 'run_manifest.json', default={})
        run_id = manifest.get('run_id')
        if not run_id or run_id in ancestors:
            known = False
            continue
        if run_id in seen:
            continue
        seen.add(run_id)
        cost = (summary.get('target_task_cost') or {}).get('evaluations_charged')
        launches = (summary.get('target_task_cost') or {}).get('spectre_launches')
        if cost is None:
            known = False
        chain.append(dict(run_id=run_id, run_dir=str(current), mode=manifest.get('mode'),
                          task_id=manifest.get('task_id'), seed=(manifest.get('seeds') or {}).get('target_seed'),
                          evaluations_charged=cost, spectre_launches=launches))
        total += cost or 0
        parent = (manifest.get('parent') or {}).get('run_dir')
        if manifest.get('run_kind') == 'offline_pretraining':
            sources = (manifest.get('pretraining') or {}).get('sources')
            if not sources:
                known = False
            # Explicit pool already includes every contributing run. Inherited model cost is not
            # extra archive data; following those parents would count some source runs twice.
            pending.extend((Path(s['run_dir']), False, ancestors | {run_id}) for s in sources or [])
        # resume continues the same run (no separate cost); fine_tune/frozen add their parent's cost.
        if follow_parent and parent and manifest.get('mode') in ('fine_tune', 'frozen'):
            pending.append((Path(parent), True, ancestors | {run_id}))
    return dict(status='known' if known and chain else 'unknown',
                evaluations_charged=total if known and chain else None, chain=chain)
