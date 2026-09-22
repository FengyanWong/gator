"""Complete experience archive: encode states, and reload transitions as the optimizer's
own ``Transition`` objects.

A state row carries (a) typed numeric arrays for direct analysis and (b) an exact patch
against a de-duplicated static graph template, produced by the optimizer's existing
lossless codec (``analog_optimizer.recording.codec``: JSON, registered dataclasses only,
no pickle). Reloading needs only these files - never raw waveforms.

This archive is complete and append-only. It is NOT the replay snapshot: that is a finite
circular buffer stored inside a checkpoint and forgets evicted samples.
"""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path

from .storage.atomic import read_json, write_json
from .storage.dataset import DatasetReader, map_to_dict

NORMALIZER_VERSION = 'fixed-references-signed-log1p-v1'


def _codec():
    from analog_optimizer.recording import codec
    return codec


class StateEncoder:
    def __init__(self, static_dir, *, task_id, graph, specs, feature_schema_version, spec_schema_version):
        codec = _codec()
        self.static_dir = Path(static_dir)
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.task_id = task_id
        self.feature_schema_version, self.spec_schema_version = feature_schema_version, spec_schema_version
        self.template = codec.tree(graph)
        self.specs = tuple(specs)
        self.graph_ref = f'graph-{codec.identity(graph)[:24]}.json'
        self.spec_ref = f'spec-{codec.identity(self.specs)[:24]}.json'
        for name, value in ((self.graph_ref, self.template), (self.spec_ref, codec.tree(self.specs))):
            if not (self.static_dir / name).exists():
                write_json(self.static_dir / name, dict(codec=codec.VERSION, value=value), indent=None)
        self.written: set[str] = set()

    def encode(self, observation, *, run_id):
        """Return (state_id, row or None). `row` is None when this state was already written."""
        codec = _codec()
        if tuple(observation.specs) != self.specs:
            raise ValueError('Observation specifications differ from the task')
        encoded = codec.tree(observation.graph)
        patches = codec.diff(self.template, encoded)
        if codec.patched(self.template, patches) != encoded:
            raise ValueError('Graph reconstruction from the static template is not exact')
        values = {f.name: getattr(observation, f.name) for f in fields(observation) if f.name not in ('graph', 'specs')}
        state_id = codec.identity((self.task_id, self.graph_ref, patches, values))
        if state_id in self.written:
            return state_id, None
        self.written.add(state_id)
        graph = observation.graph
        groups = graph.parameter_groups
        members = [dict(instance_path=m.device_id, parameter=m.parameter,
                        value=graph.parameters[m.device_id][m.parameter].value) for g in groups for m in g.members]
        metric_ids = sorted(observation.metrics)
        condition = values.get('condition')
        row = dict(run_id=run_id, state_id=state_id, task_id=self.task_id, static_graph_ref=self.graph_ref,
                   spec_ref=self.spec_ref, group_ids=[g.id for g in groups], group_values=[g.value for g in groups],
                   group_lower=[g.lower for g in groups], group_upper=[g.upper for g in groups],
                   group_mutable=[g.mutable for g in groups], members=members, metric_ids=metric_ids,
                   metric_values=[observation.metrics[k] for k in metric_ids],
                   metric_valid=[bool(observation.metric_validity.get(k)) for k in metric_ids],
                   metric_units=[observation.metric_units.get(k, '') for k in metric_ids],
                   status=observation.status, origin=observation.origin,
                   remaining_steps=observation.remaining_steps, job_id=observation.job_id,
                   condition_json=None if condition is None else json.dumps(codec.tree(condition), allow_nan=False),
                   graph_patch_json=json.dumps(codec.tree(patches), allow_nan=False),
                   observation_fields_json=json.dumps(codec.tree(values), allow_nan=False),
                   feature_schema_version=self.feature_schema_version,
                   spec_schema_version=self.spec_schema_version, normalizer_version=NORMALIZER_VERSION)
        return state_id, row


# --------------------------------------------------------------------------- loader
class TrajectoryLoader:
    """Rebuild observations and transitions from a run directory (fixed snapshot)."""
    def __init__(self, run_dir, *, cutoff_seq=None):
        self.run_dir = Path(run_dir)
        self.reader = DatasetReader(self.run_dir / 'data', cutoff_seq=cutoff_seq)
        self._static = {}
        self._states = None

    def _static_value(self, name):
        if name not in self._static:
            payload = read_json(self.run_dir / 'data' / 'states' / 'static' / name)
            codec = _codec()
            if payload['codec'] != codec.VERSION:
                raise ValueError('Unsupported state codec version')
            self._static[name] = payload['value']
        return self._static[name]

    def state_rows(self):
        if self._states is None:
            self._states = {row['state_id']: row for row in self.reader.rows('states')}
        return self._states

    def observation(self, state_id):
        from analog_optimizer.envs.sizing import Observation
        codec = _codec()
        row = self.state_rows()[state_id]
        template = self._static_value(row['static_graph_ref'])
        patches = codec.untree(json.loads(row['graph_patch_json']))
        graph = codec.untree(codec.patched(template, patches))
        specs = codec.untree(self._static_value(row['spec_ref']))
        values = codec.untree(json.loads(row['observation_fields_json']))
        return Observation(graph=graph, specs=specs, **values)

    def transitions(self, *, validate=True):
        """Every archived transition, in commit order, as optimizer ``Transition`` objects.

        Transitions that were never eligible for training replay (e.g. failures, frozen-mode
        rollouts that ended in an invalid state) cannot satisfy ``Transition.validate`` and are
        returned by ``transition_rows`` only.
        """
        from analog_optimizer.training.replay import Transition
        result = []
        for row in self.transition_rows():
            if not row['replay_eligible_archive']:
                continue
            transition = Transition(
                observation=self.observation(row['state_ref']), proposal=map_to_dict(row['action']),
                reward=row['reward'], next_observation=self.observation(row['next_state_ref']),
                terminated=row['terminated'], truncated=row['truncated'], bootstrap=row['bootstrap'],
                applied_parameters={(m['instance_path'], m['parameter']): m['value']
                                    for m in row['applied_parameters']},
                candidate_id=row['candidate_id'], record_path=row['record_path'],
                action_version=row['action_version'])
            if validate:
                transition.validate()
            result.append(transition)
        return result

    def transition_rows(self):
        rows = sorted(self.reader.rows('transitions'), key=lambda r: r['commit_seq'])
        for row in rows:
            row['replay_eligible_archive'] = (row['reward'] is not None and not row['truncated']
                                              and row['next_state_ref'] is not None)
        return rows

    def training_batch(self, transitions, *, feature_schema=None, spec_schema=None, vocabulary=None):
        """Reconstruct the exact network inputs for a list of transitions. `vocabulary`: the run's PDK component list
        (pdk.run_vocabulary), whose view the network saw the states through; its schema is then the feature schema."""
        from analog_optimizer.graph.pyg_converter import FeatureSchema
        from analog_optimizer.models.inputs import SpecSchema, batch_observations
        if vocabulary is not None:
            feature_schema, see = vocabulary.schema, vocabulary.view
        else:
            see = lambda observation: observation                      # noqa: E731 - the standard list sees states as stored
        feature_schema, spec_schema = feature_schema or FeatureSchema(), spec_schema or SpecSchema()
        return (batch_observations([see(t.observation) for t in transitions], feature_schema, spec_schema),
                batch_observations([see(t.next_observation) for t in transitions], feature_schema, spec_schema))
