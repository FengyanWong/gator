// Compiled by tsc, never run: boundary types must reject wrong rows and payload shapes.
import type { api } from '../../src/api';
import type { ConfigSetter, EditorRow, ParameterRow, ProbeRow, SpecRow, TaskRows } from '../../src/contracts';
import type { ComponentProps } from 'react';
import type { Editors } from '../../src/panels/Editors';
import type { HistoryStep } from '../../src/history';

export function checkContracts(parameter: ParameterRow, probe: ProbeRow, spec: SpecRow,
  validation: Awaited<ReturnType<typeof api.validate>>, schema: Awaited<ReturnType<typeof api.schema>>,
  diff: Awaited<ReturnType<typeof api.diff>>) {
  const rows: TaskRows = { parameters: [parameter], measurements: [probe], targets: [spec] };
  // @ts-expect-error A quantity is stored as a number, not display text.
  parameter.lower = '400 nm';
  // @ts-expect-error A Probe cannot be inserted into Parameters.
  rows.parameters.push(probe);
  // @ts-expect-error A result source is an explicit supported identifier.
  probe.result_source = 'guessed';
  // @ts-expect-error The Spec equation refers to probes by text.
  spec.equation = 42;
  // @ts-expect-error Validation issues have a message, not an arbitrary payload property.
  validation.issues[0].mesage;
  // @ts-expect-error Editor descriptors do not invent a fourth table.
  schema.editors.outputs;
  // @ts-expect-error A diff's field list is an array.
  diff.diff[0].fields = {};
  // @ts-expect-error Extension fields remain unknown until narrowed.
  parameter.extension.enabled;
  return rows;
}

export function checkEditorUpdates(setConfig: ComponentProps<typeof Editors>['setConfig'], row: EditorRow, step: HistoryStep) {
  const update: ConfigSetter = setConfig;
  update(config => ({ ...config, parameters: config.parameters.map(parameter => ({ ...parameter, lower: 1 })) }));
  // @ts-expect-error An edit callback must return a complete configuration.
  update(config => ({ parameters: config.parameters }));
  // @ts-expect-error A typed editor update cannot replace Parameters with Probes.
  update(config => ({ ...config, parameters: config.measurements }));
  // @ts-expect-error Generic editor rows still know that bounds are numeric.
  row.lower = '400 nm';
  // @ts-expect-error Undo snapshots retain the same typed row boundaries.
  step.from.targets.push(step.to.parameters[0]);
}
