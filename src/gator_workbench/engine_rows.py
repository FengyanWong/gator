"""The rows one committed evaluation adds to the run's data tables: the candidate the best-design tracker is offered, and
the rows of the parameters, metrics, simulator jobs and transitions tables.

Moved from engine.py by the refactoring (docs/plan-refactoring.md): RunEngine inherits CommitRows; the method names
are unchanged.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import socket

from .compile import hard_constraints
from .run_definitions import decode_action
from .run_lock import iso
from .simulation_artifacts import RetentionItem
from .storage.atomic import read_json, write_json


# `aggregation` of a probe's aggregate metrics row: what the Probes' aggregation column (retired 2026-09-29, record
# 7.105) held in every run - a run refused any other value - so results tables read as before.
PROBE_AGGREGATION = 'nominal_only'


class CommitRows:
    """RunEngine's builders of the rows a committed evaluation writes: the tracker's candidate and the parameters,
    metrics, simulator jobs and transitions rows."""

    # ------------------------------------------------------------------ row builders
    def _candidate(self, busy, record, metrics, units_map, constraints, valid, feasible, violation, reward, seq):
        applied = {(r['device'], r['parameter']): r['value'] for r in (record.get('applied_parameters') or [])}
        # A fixed group (optimized = false) is never sent to the simulator, so no candidate reports it: its members keep
        # the circuit's values. Read as missing, every candidate of a task with one fixed row was "incomplete" - never
        # valid, never feasible, no best design (review of 2026-10-03).
        fixed = {group.id: group.value for group in self.compiled.graph.parameter_groups if not group.mutable}
        variables, members = [], []
        for variable in self.compiled.variables:
            group_value = None
            for member in variable['members']:
                value = applied.get((member['instance_path'], self._source_name(member)))
                if value is None and variable['variable_id'] in fixed:
                    value = fixed[variable['variable_id']] * member['ratio']
                if value is not None and group_value is None:
                    group_value = value / member['ratio']
                members.append(dict(variable_id=variable['variable_id'], member_variable_id=member['variable_id'],
                                    role='independent' if member['variable_id'] == variable[
                                        'variable_id'] else 'bound_member',
                                    instance_path=member['instance_path'], parameter_name=member['parameter_name'],
                                    value=value, unit=variable['unit'], ratio=member['ratio']))
            variables.append(dict(variable_id=variable['variable_id'], value=group_value, unit=variable['unit'],
                                  optimized=variable['optimized']))
        complete = all(m['value'] is not None for m in members)
        return dict(evaluation_id=busy['evaluation_id'], commit_seq=seq, valid=valid and complete,
                    feasible=feasible and complete,
                    violation=violation, reward=reward, metrics=metrics,
                    metric_units={t['metric_id']: t['unit'] for t in self.compiled.targets},
                    variables=variables, members=members, constraints=constraints, conditions=['nominal'],
                    provenance=self.provenance)
    def _source_name(self, member):
        value = self.compiled.graph.parameters[member['instance_path']][member['parameter_name']]
        return value.source_name or member['parameter_name']
    def _parameter_rows(self, busy, record, evaluation_id):
        applied = {(r['device'], r['parameter']): r['value'] for r in (record.get('applied_parameters') or [])}
        before = {}
        if busy['previous'] is not None:
            graph = busy['previous'].graph
            for group in graph.parameter_groups:
                for m in group.members:
                    before[(m.device_id, m.parameter)] = graph.parameters[m.device_id][m.parameter].value
        projected = set(record.get('projected_groups') or [])
        rows = []
        for variable in self.compiled.variables:
            z = None if busy['proposal'] is None else busy['proposal'].get(variable['variable_id'])
            decoded = None if z is None else decode_action(z, variable['lower'], variable['upper'], variable['scale'])
            for member in variable['members']:
                executed = applied.get((member['instance_path'], self._source_name(member)))
                rows.append(dict(run_id=self.run_id, evaluation_id=evaluation_id, variable_id=variable['variable_id'],
                                 member_variable_id=member['variable_id'],
                                 role='independent' if member['variable_id'] == variable[
                                     'variable_id'] else 'bound_member',
                                 instance_path=member['instance_path'], parameter_name=member['parameter_name'],
                                 unit=variable['unit'],
                                 value_before=before.get((member['instance_path'], member['parameter_name'])),
                                 raw_policy_action=z, decoded_value=decoded, executed_value=executed,
                                 projected=variable['variable_id'] in projected, ratio=member['ratio'],
                                 lower=variable['lower'], upper=variable['upper'], step=variable['step']))
        return rows
    def _metric_rows(self, evaluation_id, raw, validity, units_map, derived, spec_values, constraints, status,
        conditions=None):
        """Raw simulator results (condition rows), then one aggregate row per spec - the value of its equation, with its
        thresholds - and one per probe that no spec shows whole. A spec whose equation is one probe is that probe's row
        (measurement_id = the probe), exactly as before specs had equations; a formula's row has no single probe."""
        rows, by_metric = [], {c['metric_id']: c for c in constraints}
        measurements = {m.measurement_id: m for m in self.config.measurements}

        def reason(value, ok):
            if ok:
                return None
            if status != 'ok':
                return f'evaluation_status_{status}'
            return 'missing_or_nonfinite' if value is None else 'invalid_measurement'
        # ---- Emit nominal simulator results before the aggregate spec and probe rows.
        for name in sorted(set(raw) | set(validity)):
            value, ok = raw.get(name), validity.get(name) is True and status in ('ok', 'measurement_error')
            finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            rows.append(dict(run_id=self.run_id, evaluation_id=evaluation_id, measurement_id=None, metric_name=name,
                             analysis=None, condition='nominal', raw_value=value if finite and ok else None,
                             unit=units_map.get(name), valid=bool(ok and finite),
                             failure_reason=reason(value if finite else None, ok and finite), threshold_lower=None,
                             threshold_upper=None, hard=None, satisfied=None, violation=None,
                             aggregation_level='condition', aggregation=None))
        # ---- Attach thresholds to spec rows, then include probes not already represented whole.
        whole = set()
        for target in self.compiled.targets:
            value, probe = spec_values.get(target['metric_id']), target['probe']
            definition = measurements.get(probe) if probe is not None else None
            whole.add(probe)
            constraint = by_metric.get(target['metric_id'])
            ok = value is not None and status in ('ok', 'measurement_error')
            rows.append(dict(run_id=self.run_id, evaluation_id=evaluation_id, measurement_id=probe,
                             metric_name=target['metric_id'], analysis=definition.analysis if definition else None,
                             condition='aggregate', raw_value=value if ok else None, unit=target['unit'], valid=ok,
                             failure_reason=reason(value, ok), threshold_lower=target['lower'],
                             threshold_upper=target['upper'], hard=target['hard'],
                             satisfied=constraint['satisfied'] if constraint else None,
                             violation=constraint['normalized_violation'] if constraint else None,
                             aggregation_level='aggregate',
                             aggregation=PROBE_AGGREGATION if definition else 'equation'))
        for measurement_id, value in derived.items():
            if measurement_id in whole:
                continue
            definition = measurements[measurement_id]
            ok = value is not None and status in ('ok', 'measurement_error')
            rows.append(dict(run_id=self.run_id, evaluation_id=evaluation_id, measurement_id=measurement_id,
                             metric_name=measurement_id, analysis=definition.analysis, condition='aggregate',
                             raw_value=value if ok else None, unit=definition.unit, valid=ok,
                             failure_reason=reason(value, ok), threshold_lower=None, threshold_upper=None, hard=None,
                             satisfied=None, violation=None, aggregation_level='aggregate',
                             aggregation=PROBE_AGGREGATION))
        # A training corner's result also carries the specs the lane computed from it (spec_equations): recorded here as
        # that corner's value of the formula, marked aggregation = equation, so it never passes for a simulator result.
        computed = set(self.compiled.plan.injected)
        for condition in (conditions or [])[1:]:
            label = condition['condition']['corner']['id']
            for name in sorted(set(condition['metrics']) | set(condition['metric_validity'])):
                value = condition['metrics'].get(name)
                ok = (condition['status'] in ('ok',
                    'measurement_error') and condition['metric_validity'].get(name) is True
                      and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))
                target = next((t for t in self.compiled.targets if t['metric_id'] == name and not t['nominal_only']),
                    None)
                checked = hard_constraints((target,), {name: value},
                    {name: ok})[2][0] if target and target['active'] else None
                rows.append(dict(run_id=self.run_id, evaluation_id=evaluation_id, measurement_id=None, metric_name=name,
                                 analysis=None, condition=label, raw_value=value if ok else None,
                                 unit=condition['metric_units'].get(name), valid=ok,
                                 failure_reason=None if ok else condition['reason_code'],
                                 threshold_lower=target['lower'] if target else None,
                                 threshold_upper=target['upper'] if target else None,
                                 hard=target['hard'] if target else None,
                                 satisfied=checked['satisfied'] if checked else None,
                                 violation=checked['normalized_violation'] if checked else None,
                                 aggregation_level='condition', aggregation='equation' if name in computed else None))
        return rows
    def _job_rows(self, busy, lane, role, failed):
        policy = self.config.output.waveform_retention
        rows = []
        plan: list[RetentionItem] = []
        attempts = []
        # ---- Expand recorded jobs and keep unresolved launch leases separate from job rows.
        for retry, attempt in enumerate(busy['attempts'], start=1):
            record = attempt.get('record') or {}
            if record.get('jobs'):
                for job in record['jobs']:
                    launches = job.get('confirmed_calls', 0) + job.get('uncertain_calls', 0)
                    if self.task.mock and job.get('state') == 'completed':
                        launches = 1                # one counted call of the toy backend, never a simulator launch
                    attempts.append(dict(attempt, record=dict(record, **job), launches=launches,
                                         launch_unknown=bool(job.get('uncertain_calls')),
                                         started_at=job.get('started_at', attempt['started_at']),
                                         ended_at=job.get('ended_at', attempt['ended_at']), retry=retry))
            else:
                if attempt.get('launch_unknown'):
                    lease_path = self.layout.data / '_journal' / 'unresolved-launch-leases.json'
                    leases = read_json(lease_path, default={})
                    leases[busy['evaluation_id']] = dict(allowance=attempt['launches'],
                        worker_directory=lane.info['directory'], state='unresolved')
                    write_json(lease_path, leases)
                elif attempt['launches']:
                    attempts.append(dict(attempt, retry=retry))
        # ---- Choose retention and build rows for attempts that counted a launch.
        for number, attempt in enumerate(attempts, start=1):
            record = attempt.get('record') or {}
            launched = int(attempt['launches']) > 0
            if not launched:
                continue
            started, ended = attempt['started_at'], attempt['ended_at']
            runtime = (datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds()
            self.counters['sum_job_runtime_seconds'] += runtime
            directory = record.get('artifact_directory')
            has_output = bool(directory) and Path(directory).is_dir() and any(Path(directory).rglob('*'))
            if not has_output:
                decision = 'not_produced'
            elif policy == 'all':
                decision = 'retained_all'
            elif policy == 'none':
                decision = 'deleted_by_policy'
            elif failed:
                decision = 'retained_failure'
            elif role is not None:
                decision = 'retained_best'
            else:
                decision = 'deleted_by_policy'
            job_id = record.get('job_id') or record.get('export_job_id') or record.get(
                'candidate_id') or f"{busy['evaluation_id']}-a{number}"
            relative = (f"waveforms/{busy['evaluation_id']}/attempt-{number}"
                        if decision.startswith('retained') else None)
            status = record.get('status') or ('cancelled' if attempt.get('cancelled') else 'execution_error')
            analysis = 'task_profile_default'
            if self.task.connection_family == 'ngspice' and directory:
                counts = read_json(Path(directory) / 'analysis-counts.json', default=None)
                if counts is not None:
                    analysis = 'ngspice:' + json.dumps(counts, sort_keys=True, separators=(',', ':'))
            rows.append(dict(run_id=self.run_id, job_id=f'{job_id}', evaluation_id=busy['evaluation_id'],
                             worker_id=lane.lane_id, host=socket.gethostname(), analysis=analysis,
                             condition=(record.get('condition') or {}).get('corner', {}).get('id', 'nominal'),
                             attempt=attempt['retry'], dispatched_at=attempt['dispatched_at'],
                             started_at=started, ended_at=ended, exit_status=status, timed_out=status == 'timeout',
                             retry_reason=None if attempt['retry'] == 1 else busy.get('retry_reason'),
                             runtime_seconds=runtime, launch_counted=launched,
                             invocation_confirmed=(None if attempt.get('launch_unknown') or not launched else
                                                   True) if not self.task.mock else launched,
                             simulator_version=record.get('simulator_version'), output_path=relative,
                             retention_status=decision,
                             sync_status='local' if has_output else 'not_applicable', provenance=self.provenance))
            journal = None
            if record.get('candidate_id'):
                journal = str(Path(lane.info['directory']) / 'candidates' / f"{record['candidate_id']}.json")
            plan.append(dict(decision=decision, source=directory, target=relative, record=record,
                             evaluation_id=busy['evaluation_id'], job_id=job_id, journal=journal))
        return rows, plan
    def _transition_rows(self, busy, step, lane, commit_seq, admitted, record):
        observation, reward, terminated, truncated, info = step
        rows, states = [], []
        state_id, row = self.encoder.encode(busy['previous'], run_id=self.run_id)
        if row:
            states.append(row)
        next_id, row = self.encoder.encode(observation, run_id=self.run_id)
        if row:
            states.append(row)
        applied = [dict(instance_path=r['device'], parameter=r['parameter'], value=r['value'])
                   for r in (record.get('applied_parameters') or [])]
        rows.append(dict(run_id=self.run_id, transition_id=busy['evaluation_id'], task_id=self.task_id,
                         episode_id=busy['episode_id'], worker_id=lane.lane_id, evaluation_id=busy['evaluation_id'],
                         state_ref=state_id, action=busy['proposal'], reward=reward, next_state_ref=next_id,
                         terminated=bool(terminated), truncated=bool(truncated), bootstrap=bool(info.get('bootstrap')),
                         policy_version=busy['policy_version'], step=int(record.get('step') or 0),
                         global_env_step=self.counters['global_env_step'], recorded_at=iso(),
                         action_version='absolute-group-v1',
                         candidate_id=info.get('candidate_id') or busy['evaluation_id'],
                         reward_version=record.get('reward_version'),
                         record_path=str(info.get('record_path') or ''), applied_parameters=applied,
                         replay_admitted=admitted, commit_seq=commit_seq))
        return rows, states
