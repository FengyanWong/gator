"""Raw-table definitions. One declaration per column yields BOTH the Arrow schema and
the entry in data_dictionary.json, so type, unit, enumeration and the meaning of null
cannot drift apart. Nested values use real Arrow list/struct types, never stringified
lists or repr().
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import TABLE_SCHEMA_VERSION

# The llm_* phases, the sources llm_proposal and seeded_warmup, the evaluations' llm_call_id and the llm_calls table were
# written by the LLM search methods removed on 2026-10-06 (record 7.226). They stay declared so that the runs that recorded
# them read and are described as before (the data dictionary is unchanged); no run writes them any more.
PHASES = ('baseline', 'episode_reset', 'warmup', 'adapt', 'search', 'validation', 'frozen_eval', 'preflight',
          'llm_warmup', 'llm_search', 'llm_rescue')
ACTION_SOURCES = ('reset', 'random_warmup', 'sac_policy', 'mean_policy', 'sampled_policy', 'llm_proposal', 'seeded_warmup',
                  'bayes_opt')       # bayes_opt: a design proposed by Bayesian optimization (run.optimizer, record 7.304)
RETENTION = ('pending', 'retained_best', 'retained_failure', 'retained_all', 'deleted_by_policy',
             'deleted_storage_limit', 'not_produced')


@dataclass(frozen=True)
class Column:
    name: str
    type: str                      # key into _arrow()
    description: str
    unit: str | None = None
    enum: tuple | None = None
    null: str | None = None        # meaning of null; None = column is never null


def _arrow(kind):
    import pyarrow as pa
    pair = lambda value_type: pa.list_(pa.struct([('key', pa.string()), ('value', value_type)]))
    return {
        'string': pa.string(), 'bool': pa.bool_(), 'int32': pa.int32(), 'int64': pa.int64(),
        'float64': pa.float64(), 'timestamp': pa.timestamp('us', tz='UTC'),
        'list<string>': pa.list_(pa.string()), 'list<float64>': pa.list_(pa.float64()),
        'list<bool>': pa.list_(pa.bool_()),
        'map<string,float64>': pair(pa.float64()),
        'list<member>': pa.list_(pa.struct([('instance_path', pa.string()), ('parameter', pa.string()),
                                            ('value', pa.float64())])),
    }[kind]


C = Column
IDS = [C('run_id', 'string', 'Run that owns the row.'), ]

TABLES: dict[str, dict] = {
    'evaluations': dict(
        primary_key=('evaluation_id',), purpose='One row per candidate evaluation, successes and failures.',
        columns=IDS + [
            C('evaluation_id', 'string', 'Candidate evaluation ID. Retries keep this ID.'),
            C('task_id', 'string', 'Task identity (hash of circuit, variables, targets, measurements).'),
            C('proposal_id', 'string', 'ID of the proposal that produced the candidate.'),
            C('worker_id', 'string', 'Evaluation lane that executed it.'),
            C('episode_id', 'string', 'Episode within the worker lane.'),
            C('episode_step', 'int32', 'Step inside the episode; 0 is the reset/baseline evaluation.'),
            C('global_env_step', 'int64', 'Run-wide count of environment steps at commit (resets excluded).'),
            C('dispatch_index', 'int64', 'Order in which the scheduler dispatched evaluations (1-based).'),
            C('completion_index', 'int64', 'Order in which results reached the scheduler (1-based).'),
            C('commit_seq', 'int64', 'Unified commit/event sequence number. Learner receipt order.'),
            C('phase', 'string', 'Why the evaluation was run.', enum=PHASES),
            C('action_source', 'string', 'How the action was chosen.', enum=ACTION_SOURCES),
            C('llm_call_id', 'string', 'Sizing call that selected this design.', null='not selected by an LLM'),
            C('policy_version', 'int64', 'Cumulative learner updates when the action was proposed.',
              null='no policy produced this action (reset or random warm-up)'),
            C('proposed_at', 'timestamp', 'UTC time the proposal was created.'),
            C('started_at', 'timestamp', 'UTC time execution began (budget charged here).'),
            C('completed_at', 'timestamp', 'UTC time the result reached the scheduler.'),
            C('committed_at', 'timestamp', 'UTC time the result was durably acknowledged.'),
            C('queue_seconds', 'float64', 'proposed -> started.', unit='s'),
            C('execution_seconds', 'float64', 'started -> completed, all attempts.', unit='s'),
            C('provenance', 'string', 'real = physical simulator; mock = synthetic analytic backend.',
              enum=('real', 'mock')),
            C('result_source', 'string', 'Where the numbers came from.', enum=('simulation', 'cache')),
            C('cache_hit', 'bool', 'True only for reuse of an earlier result; never counted as a simulation.'),
            C('attempts', 'int32', 'Simulator job attempts for this evaluation (1 = no retry).'),
            C('parameters_ref', 'string', 'Key into the parameters table (evaluation_id).'),
            C('metrics_ref', 'string', 'Key into the metrics table (evaluation_id).'),
            C('reward', 'float64', 'Versioned learning reward; inspect run settings, independently of hard feasibility.',
              null='no valid reward (infrastructure/measurement failure)'),
            C('reward_components', 'map<string,float64>', 'Capped per-metric violation terms used by the reward.',
              null='reward unavailable'),
            C('valid', 'bool', 'All hard-constraint measurements are finite, valid and correctly unit-labelled.'),
            C('all_hard_constraints_satisfied', 'bool',
              'Decided from raw values vs thresholds, independently of the reward. Never true when invalid.'),
            C('normalized_constraint_violation', 'float64', 'Largest uncapped hard-constraint violation/scale.',
              null='not computable because a hard-constraint measurement is invalid'),
            C('env_success', 'bool', "Environment's own success flag, stored to cross-check the independent rule.",
              null='environment produced no verdict'),
            C('reward_version', 'string', 'Versioned reward contract.', null='historical nominal reward'),
            C('condition_policy', 'string', 'off or always.', null='historical nominal-only'),
            C('conditions_planned', 'int32', 'Number of planned conditions including nominal.', null='historical coverage unknown'),
            C('conditions_evaluated', 'int32', 'Number of returned condition results.', null='historical coverage unknown'),
            C('conditions_complete', 'bool', 'Every planned condition has a result.', null='historical coverage unknown'),
            C('nominal_feasible', 'bool', 'Nominal hard constraints passed.', null='no nominal verdict'),
            C('robust_feasible', 'bool', 'Hard constraints passed the complete declared plan.', null='no robust plan'),
            C('clearance_margin', 'float64', 'Tightest eligible hard-spec signed margin; equalities excluded.', null='unavailable'),
            C('tightest_clearance_spec', 'string', 'Binding eligible hard spec.', null='no eligible measured spec'),
            C('clearance_rule', 'string', 'Clearance definition, distinct from historical min_margin.', null='historical rule'),
            C('condition_results_json', 'string', 'Condition measurements, validity, reasons and operating points.', null='historical nominal-only'),
            C('best_so_far_evaluation_id', 'string', 'Best design known to the scheduler at this commit.',
              null='no valid design yet'),
            C('best_so_far_feasible', 'bool', 'Whether that best design is feasible.'),
            C('best_so_far_violation', 'float64', 'Its normalized violation (0 when feasible).', null='no valid design yet'),
            C('best_so_far_metrics', 'map<string,float64>', 'Its raw metrics in canonical units.', null='no valid design yet'),
            C('cumulative_evaluations_charged', 'int64', 'Budget consumed at commit: evaluations STARTED so far.'),
            C('cumulative_completed', 'int64', 'Evaluations completed at commit.'),
            C('cumulative_launches', 'int64', 'Actual simulator launches at commit, incl. retries and failures.'),
            C('in_flight_at_commit', 'int32', 'Evaluations started but not yet completed at commit.'),
            C('after_first_feasible', 'bool', 'Committed after the first-feasibility event.'),
            C('in_flight_at_first_feasible', 'bool',
              'Was running when first feasibility was confirmed; its result was NOT known earlier.'),
            C('status', 'string', 'Backend status (ok, invalid_design, nonconverged, measurement_error, timeout, '
                                  'transport_error, license_error, backend_error, execution_error, cancelled).'),
            C('failure_type', 'string', 'Failure class.', null='no failure'),
            C('diagnostics', 'string', 'Concise, bounded diagnostic text.', null='none'),
            C('terminated', 'bool', 'MDP termination flag.'),
            C('truncated', 'bool', 'Truncation (infrastructure/measurement failure).'),
            C('replay_eligible', 'bool', 'Eligible for the training replay buffer.'),
            C('duplicate_of', 'string', 'Earlier evaluation with identical executed parameters.', null='not a duplicate'),
        ]),
    'parameters': dict(
        primary_key=('evaluation_id', 'member_variable_id'),
        purpose='Long format: one row per evaluation and written parameter (expanded bindings).',
        columns=IDS + [
            C('evaluation_id', 'string', 'Evaluation.'),
            C('variable_id', 'string', 'Independent action variable (group leader).'),
            C('member_variable_id', 'string', 'Configured variable for this written parameter.'),
            C('role', 'string', 'independent = the leader itself; bound_member = follows the leader.',
              enum=('independent', 'bound_member')),
            C('instance_path', 'string', 'Target instance.'),
            C('parameter_name', 'string', 'Target parameter.'),
            C('unit', 'string', 'Canonical unit of all value columns.'),
            C('value_before', 'float64', 'Value before this evaluation.', null='unknown'),
            C('raw_policy_action', 'float64', 'Normalized proposal in [-1, 1] for the independent variable.',
              null='reset/baseline evaluation: no action'),
            C('decoded_value', 'float64', 'Physical value decoded from the action BEFORE projection.',
              null='reset/baseline evaluation: no action'),
            C('executed_value', 'float64', 'Value actually executed after projection/quantization and ratio.',
              null='execution failed before parameter readback'),
            C('projected', 'bool', 'Projection/quantization changed the decoded value.'),
            C('ratio', 'float64', 'executed member value / group value.'),
            C('lower', 'float64', 'Group lower bound.'), C('upper', 'float64', 'Group upper bound.'),
            C('step', 'float64', 'Quantization step.', null='continuous, no grid'),
        ]),
    'metrics': dict(
        primary_key=('evaluation_id', 'metric_name', 'condition', 'aggregation_level'),
        purpose='Long format: one row per evaluation, test condition and metric; raw physical values.',
        columns=IDS + [
            C('evaluation_id', 'string', 'Evaluation.'),
            C('measurement_id', 'string', 'Measurement definition (Probe); on a spec row, the probe that is its whole equation.',
              null='raw backend metric (condition row), or a spec whose equation is a formula of several probes'),
            C('metric_name', 'string', 'Spec name, Probe ID, or raw backend metric name.'),
            C('analysis', 'string', 'Analysis that produced it.', null='not declared'),
            C('condition', 'string', 'Corner/test condition ID.'),
            C('raw_value', 'float64', 'Physical value in the canonical unit.',
              null='missing, non-finite or invalid; see failure_reason. Never a feasible result.'),
            C('unit', 'string', 'Canonical unit.', null='backend did not label the unit'),
            C('valid', 'bool', 'Measurement validity.'),
            C('failure_reason', 'string', 'Why the value is invalid.', null='valid'),
            C('threshold_lower', 'float64', 'Applied lower threshold (tolerance included).', null='no lower threshold'),
            C('threshold_upper', 'float64', 'Applied upper threshold (tolerance included).', null='no upper threshold'),
            C('hard', 'bool', 'Hard constraint.', null='metric has no target'),
            C('satisfied', 'bool', 'Constraint satisfied.', null='no target or invalid measurement'),
            C('violation', 'float64', 'Uncapped violation/scale.', null='no target or invalid measurement'),
            C('aggregation_level', 'string', 'condition = the value at one test condition (a simulator result; at a training '
                                             'corner also each formula spec, marked aggregation = equation); aggregate = '
                                             'value used for reward/feasibility.', enum=('condition', 'aggregate')),
            C('aggregation', 'string', 'Rule that produced the value (equation = a spec computed by its formula; on a '
                                       'condition row, that formula at a training corner).',
              null='a simulator result (condition row)'),
        ]),
    'simulator_jobs': dict(
        primary_key=('job_id',), purpose='One row per actual simulation launch attempt, incl. failures/retries.',
        columns=IDS + [
            C('job_id', 'string', 'Launch attempt ID.'), C('evaluation_id', 'string', 'Evaluation it served.'),
            C('worker_id', 'string', 'Lane.'), C('host', 'string', 'Execution host label.'),
            C('analysis', 'string', 'Analysis set, or ngspice: followed by JSON with reached command counts and output completeness.'), C('condition', 'string', 'Corner/test condition.'),
            C('attempt', 'int32', 'Attempt number within the evaluation (1-based).'),
            C('dispatched_at', 'timestamp', 'UTC dispatch time.'), C('started_at', 'timestamp', 'UTC start time.'),
            C('ended_at', 'timestamp', 'UTC end time.'),
            C('exit_status', 'string', 'Backend status of this attempt.'),
            C('timed_out', 'bool', 'Attempt hit its timeout.'),
            C('retry_reason', 'string', 'Why this attempt was a retry.', null='first attempt'),
            C('runtime_seconds', 'float64', 'Attempt runtime. Summed parallel runtime is NOT elapsed time.', unit='s'),
            C('launch_counted', 'bool', 'The simulator launch was reached and counted.'),
            C('invocation_confirmed', 'bool', 'Backend evidence that the simulator actually started.',
              null='backend gave no evidence either way'),
            C('simulator_version', 'string', 'Simulator version.', null='unavailable'),
            C('output_path', 'string', 'Raw output path relative to the run directory.', null='no output directory'),
            C('retention_status', 'string', 'Raw-output retention outcome.', enum=RETENTION),
            C('sync_status', 'string', 'Final-file synchronization state.',
              enum=('local', 'synchronized', 'remote_only', 'failed', 'not_applicable')),
            C('provenance', 'string', 'real or mock.', enum=('real', 'mock')),
        ]),
    'learner_updates': dict(
        primary_key=('update_id',), purpose='Training updates that actually occurred. Empty in frozen mode.',
        columns=IDS + [
            C('update_id', 'string', 'Update ID.'), C('updated_at', 'timestamp', 'UTC time.'),
            C('update_phase', 'string', 'Initial learning or online learning.', enum=('initial', 'online'),
              null='historical/default SAC online update'),
            C('evaluations_collected', 'int64', 'Evaluations committed when the update ran.'),
            C('actor_loss', 'float64', 'Actor loss.'), C('critic_loss', 'float64', 'Twin critic loss.'),
            C('alpha_loss', 'float64', 'Temperature loss.'), C('alpha', 'float64', 'Entropy coefficient.'),
            C('mean_log_prob', 'float64', 'Mean action log-probability (entropy estimate = -value).'),
            C('target_mean', 'float64', 'Mean TD target.'),
            C('critic_grad_norm', 'float64', 'Pre-clip critic gradient norm.'),
            C('actor_grad_norm', 'float64', 'Pre-clip actor gradient norm.'),
            C('learning_rate', 'float64', 'Optimizer learning rate.'),
            C('replay_size', 'int64', 'Replay size at the update.'), C('batch_size', 'int32', 'Batch size.'),
            C('cumulative_updates', 'int64', 'Exact cumulative update count, even when logging is thinned.'),
            C('policy_version', 'int64', 'Policy version after this update.'),
            C('update_seconds', 'float64', 'Update duration.', unit='s'),
        ]),
    'transitions': dict(
        primary_key=('transition_id',),
        purpose='Complete experience archive. Distinct from the finite replay snapshot in a checkpoint.',
        columns=IDS + [
            C('transition_id', 'string', 'Transition ID.'), C('task_id', 'string', 'Task.'),
            C('episode_id', 'string', 'Episode.'), C('worker_id', 'string', 'Lane.'),
            C('evaluation_id', 'string', 'Evaluation that produced next_state.'),
            C('state_ref', 'string', 'states.state_id before the action.'),
            C('action', 'map<string,float64>', 'Normalized proposal per independent variable.'),
            C('reward', 'float64', 'Reward.'),
            C('next_state_ref', 'string', 'states.state_id after the action.'),
            C('terminated', 'bool', 'Terminated.'), C('truncated', 'bool', 'Truncated.'),
            C('bootstrap', 'bool', 'Critic target bootstraps from next_state.'),
            C('policy_version', 'int64', 'Policy version that proposed the action.', null='random warm-up'),
            C('step', 'int32', 'Episode step.'), C('global_env_step', 'int64', 'Run-wide step.'),
            C('recorded_at', 'timestamp', 'UTC time.'),
            C('action_version', 'string', 'Action semantics version.'),
            C('reward_version', 'string', 'Reward semantics version.', null='historical nominal reward'),
            C('candidate_id', 'string', 'Environment candidate ID (needed to rebuild the replay item).'),
            C('record_path', 'string', 'Environment journal path recorded in the replay item.'),
            C('applied_parameters', 'list<member>', 'Executed parameter assignment of the transition.'),
            C('replay_admitted', 'bool', 'Was inserted into the training replay buffer.'),
            C('commit_seq', 'int64', 'Commit sequence number.'),
        ]),
    'states': dict(
        primary_key=('state_id',),
        purpose='Observations referenced by transitions: static graph reference + dynamic numeric arrays + an '
                'exact codec patch. Reconstruction never needs raw waveforms.',
        columns=IDS + [
            C('state_id', 'string', 'Content hash of the observation.'), C('task_id', 'string', 'Task.'),
            C('static_graph_ref', 'string', 'File under data/states/static/ holding the encoded graph template.'),
            C('spec_ref', 'string', 'File under data/states/static/ holding the encoded specifications.'),
            C('group_ids', 'list<string>', 'Independent variable IDs (order of the numeric arrays).'),
            C('group_values', 'list<float64>', 'Current group values (canonical units).'),
            C('group_lower', 'list<float64>', 'Group lower bounds.'), C('group_upper', 'list<float64>', 'Upper bounds.'),
            C('group_mutable', 'list<bool>', 'Action mask: true where the optimizer may act.'),
            C('members', 'list<member>', 'Expanded parameter mapping with current values.'),
            C('metric_ids', 'list<string>', 'Metric order.'),
            C('metric_values', 'list<float64>', 'Metric values; null element = invalid/missing.'),
            C('metric_valid', 'list<bool>', 'Measurement validity mask.'),
            C('metric_units', 'list<string>', 'Metric units.'),
            C('status', 'string', 'Observation status.'), C('origin', 'string', 'real or synthetic.'),
            C('remaining_steps', 'int32', 'Finite-horizon budget left.'), C('job_id', 'string', 'Backend job.'),
            C('condition_json', 'string', 'Simulation condition (JSON object).', null='legacy synthetic fixture: none'),
            C('graph_patch_json', 'string', 'Exact codec patch against the static template '
                                            '(analog_optimizer.recording.codec, JSON, no pickle).'),
            C('observation_fields_json', 'string', 'Exact codec encoding of the non-graph observation fields.'),
            C('feature_schema_version', 'string', 'Graph feature schema version.'),
            C('spec_schema_version', 'string', 'Goal/spec input schema version.'),
            C('normalizer_version', 'string', 'Fixed-reference normalizer version.'),
        ]),
}

# Evaluations are published LAST in a flush: their presence proves the other tables are complete.
TABLES['llm_calls'] = dict(primary_key=('call_id',), purpose='Every sizing request, including rejected and cancelled calls.',
    columns=IDS + [
        C('call_id', 'string', 'Sizing request ID.'),
        *[C(name, 'string', name.replace('_', ' '), null='unavailable') for name in
          ('method', 'provider', 'model', 'effort', 'prompt_sha256', 'reply_sha256', 'status', 'record_path')],
        *[C(name, 'timestamp', name.replace('_', ' '), null='unavailable') for name in ('started_at', 'ended_at')],
        *[C(name, 'int64', name.replace('_', ' '), null='provider did not report or not applicable') for name in
          ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'returned', 'accepted',
           'notes_kept', 'notes_dropped', 'hints_included', 'request_position', 'release_position', 'round')],
        C('notional_cost_usd', 'float64', 'Provider-reported cost; never estimated as zero.', unit='USD', null='not reported'),
        C('latency_seconds', 'float64', 'Request duration.', unit='s', null='not finished'),
        C('repair', 'bool', 'This request repairs one invalid answer.'),
        C('rejected_json', 'string', 'Candidate rejections and reasons.'),
    ])

FLUSH_ORDER = ('parameters', 'metrics', 'simulator_jobs', 'learner_updates', 'llm_calls', 'states', 'transitions', 'evaluations')


def arrow_schema(table):
    import pyarrow as pa
    return pa.schema([pa.field(c.name, _arrow(c.type), nullable=c.null is not None or c.type.startswith(('list', 'map')))
                      for c in TABLES[table]['columns']],
                     metadata={'gator_table': table, 'gator_table_schema': TABLE_SCHEMA_VERSION})


def empty_row(table):
    return {c.name: None for c in TABLES[table]['columns']}


def normalize_row(table, row):
    """Reject unknown columns; convert dict-valued map columns to key/value pairs."""
    columns = {c.name: c for c in TABLES[table]['columns']}
    unknown = set(row) - set(columns)
    if unknown:
        raise KeyError(f'{table}: unknown columns {sorted(unknown)}')
    result = empty_row(table)
    for name, value in row.items():
        if columns[name].type == 'map<string,float64>' and isinstance(value, dict):
            value = [dict(key=str(k), value=None if v is None else float(v)) for k, v in value.items()]
        result[name] = value
    for name, column in columns.items():
        if result[name] is None and column.null is None and not column.type.startswith(('list', 'map')):
            raise ValueError(f'{table}.{name} may not be null')
    return result


def data_dictionary():
    tables = {}
    for name, spec in TABLES.items():
        tables[name] = dict(
            purpose=spec['purpose'], primary_key=list(spec['primary_key']), format='parquet',
            location=f'data/{name}/part-*.parquet',
            columns=[dict(name=c.name, type=c.type, unit=c.unit, enum=None if c.enum is None else list(c.enum),
                          nullable=c.null is not None, null_meaning=c.null, description=c.description)
                     for c in spec['columns']])
    return dict(
        schema_version=TABLE_SCHEMA_VERSION, tables=tables,
        conventions=dict(
            timestamps='UTC, microsecond precision',
            units='All physical values are stored in canonical units (m, F, ohm, H, V, A, W, Hz, s, deg, dB...).',
            null='null always has the per-column meaning listed here; it is never a substitute for 0 or success.',
            non_finite='Non-finite numbers are never stored. JSON uses null plus a _null_reasons entry.',
            map_type='map<string,float64> is an Arrow list of {key, value} structs.',
            visibility='A part file is part of the dataset only when listed in data/_journal/flushes.jsonl.',
            provenance='provenance=mock rows come from synthetic analytic backends and are not circuit results.'))
