// Relationships between runs and models (record 7.264; plan docs/plan-frontend-run-workflow.md, "Relationships and history:
// data"). Everything here is worked out on the page from the run list's own fields - a run's `parent` (the run, save point
// and relation it loaded), `run_kind`, `encoder` (the template of a new model) and `pretraining_sources` (an offline
// model's recorded runs) - which the backend passes on from each run's manifest. Never inferred from names, folder paths
// or encoder labels.

import { Json } from './api';
import { count, folderName, plural } from './format';

/** The encoders' short names, as Run configuration writes them (GraphGPS, not "GPS", since branch record SIF-1). */
export const ENCODER_SHORT: Record<string, string> = { graph_transformer: 'GT', rgcn: 'RGCN', gatv2: 'GATv2', graph_gps: 'GraphGPS', group_cross_attention: 'Group attention', circuit_gps: 'CircuitGPS' };
/** A network's design by name, as the RL model window's chooser names it (branch record SIF-1, user: "show what is each
 *  models original shape design (rgcn or graphgps or circuit gps etc)"). CircuitGPS carries its version: 2 and 3 are
 *  different networks (record 7.356). A fine-tuned model keeps the design of the model it started from. */
export const DESIGN_NAME: Record<string, string> = { graph_transformer: 'Graph Transformer', rgcn: 'RGCN', gatv2: 'GATv2', graph_gps: 'GraphGPS',
  group_cross_attention: 'Parameter-group attention', circuit_gps: 'CircuitGPS' };
const version = (n: Json) => (n?.encoder_type === 'circuit_gps' && n.architecture_version ? ` v${n.architecture_version}` : '');
export const designName = (n: Json): string => (n?.encoder_type ? `${DESIGN_NAME[n.encoder_type] ?? n.encoder_type}${version(n)}` : 'unknown');
/** The same in the short form Run configuration writes ("GT", "CircuitGPS v3"). */
export const designShort = (n: Json): string => (n?.encoder_type ? `${ENCODER_SHORT[n.encoder_type] ?? n.encoder_type}${version(n)}` : 'unknown');

/** The evaluations a save point was written at, read from its id (ckpt-000420-...), or null. */
export const pointEvaluations = (id?: string | null): number | null => {
  const match = /^ckpt-0*(\d+)/.exec(id ?? '');
  return match ? Number(match[1]) : null;
};
/** A save point in words, as its table's Evaluations column and the model line count it: "at 420 evaluations"; the id itself
 *  when it holds no count ("latest"), "none" for none. The id goes in a tooltip (branch record SIF-67: the RL model window
 *  named it "save point ckpt-00000800-003f07c8" beside a table that says 800); one as one (SIF-76 review). */
export const pointText = (id?: string | null) => { const n = pointEvaluations(id); return n != null ? `at ${plural(n, 'evaluation')}` : (id || 'none'); };

/** `at`: the evaluations the text names after "@", so a caller does not name that save point again (branch record SIF-67). */
export type Origin = { text: string; parent?: string; missing?: boolean; at?: number | null };

/** "Started from" (the plan's column): "template GT" for a new model, "ota7t (2) @ 420" for a run that loaded a saved
 *  model (a link to that run), "offline: 22 runs" for an offline model, "-" for a baseline or a calibration. A parent
 *  that is not under this output folder is named by its folder and marked `missing`, never left out. The save point's
 *  evaluations as the page writes a count, "@ 12,000" (branch record SIF-117). */
export function startedFrom(run: Json, byDir: Map<string, Json>): Origin {
  if (run.run_kind === 'offline_pretraining') return { text: `offline: ${run.pretraining_sources ?? '?'} runs` };
  const parent = run.parent;
  if (parent?.run_dir) {
    const from = byDir.get(parent.run_dir);
    const offline = from?.run_kind === 'offline_pretraining';
    const at = offline ? null : pointEvaluations(parent.checkpoint_id);
    return { text: `${from?.model_label ?? folderName(parent.run_dir)}${offline ? ' (offline)' : at != null ? ` @ ${count(at)}` : ''}`,
      parent: parent.run_dir, missing: !from, at };
  }
  if (run.run_kind === 'baseline_preflight' || run.run_kind === 'calibration') return { text: '-' };
  return run.encoder ? { text: `template ${designShort({ encoder_type: run.encoder, architecture_version: run.network?.architecture_version })}` } : { text: '-' };
}

/** The runs that started from this run's model, newest first (the list is sorted so). */
export const childrenOf = (run: Json, runs: Json[]): Json[] => runs.filter(r => r.parent?.run_dir === run.run_dir);

export type Step = { run_dir: string; row: Json | null; checkpoint_id?: string | null; relation?: string | null };
/** The chain of models behind a run, oldest first, ending with the run itself: each step is a run that saved a model
 *  the next one loaded. `root`: where the oldest one came from - a template, offline recorded runs, or a parent that is not
 *  listed (`missing`). Guarded against cycles: a run already in the chain ends it. */
export function historyOf(run: Json, byDir: Map<string, Json>): { steps: Step[]; root: Origin } {
  const steps: Step[] = [{ run_dir: run.run_dir, row: run }];
  const seen = new Set([run.run_dir]);
  let current: Json = run;
  for (;;) {
    const parent = current.parent;
    if (!parent?.run_dir || seen.has(parent.run_dir)) break;
    seen.add(parent.run_dir);
    steps[0] = { ...steps[0], checkpoint_id: parent.checkpoint_id, relation: parent.relation };
    const row = byDir.get(parent.run_dir) ?? null;
    steps.unshift({ run_dir: parent.run_dir, row });
    if (!row) return { steps, root: { text: `${folderName(parent.run_dir)}: not under this output folder`, missing: true } };
    current = row;
  }
  return { steps, root: startedFrom(current, byDir) };
}
