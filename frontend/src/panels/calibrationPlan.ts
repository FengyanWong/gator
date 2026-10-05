import { Json, short } from '../api';

const sameNumber = (a: unknown, b: unknown) => (a ?? null) === (b ?? null);
/** The Specs row of the page that IS the row a run calibrated: same ID, same limits, same unit. A row whose limits were
 *  edited since is another question, and the run's answer is not written into it. */
export const sameSpecsRow = (target: Json, row: Json) => !!target && sameNumber(target.lower, row.lower) && sameNumber(target.upper, row.upper) && target.unit === row.unit;

/** What "Apply calibration" does to the configuration the page holds, for one calibration result (record 7.197; backend
 *  calibration.py) - worked out in ONE place for the Run status block and the "Calibration ready" line under the header
 *  (record 7.204), so both say and do the same.
 *  rows: the result's rows with the page's row (`target`, none when the run calibrated another task) and whether it still
 *  is the row the run simulated (`same`); scales: the rows a Scale would be written into; pending: how many values Apply
 *  would change (0 = the page holds them, or the run calibrated another task);
 *  otherTask: the run calibrated another task than the page holds; what / afterwards: the words for both places. */
export function calibrationPlan(result: Json, config: Json) {
  const targets: Json[] = config.targets ?? [], alpha: Json = result?.initial_alpha ?? {};
  const otherTask = !!result?.task_key && !!config.circuit?.task_id && result.task_key !== config.circuit.task_id;
  // A run of another task is not matched against the page's rows: a row there with the same ID is another circuit's row
  // (record 7.214: an LDO's pm_deg >= 60 deg stood as the "Scale now" of an OTA's pm_deg).
  const rows: Json[] = (result?.rows ?? []).map((row: Json) => { const target = otherTask ? undefined : targets.find(t => t.metric_id === row.metric_id); return { ...row, target, same: sameSpecsRow(target as Json, row) }; });
  const scales = rows.filter(r => r.proposed_scale != null && r.same);
  const alphaNow: number | undefined = config.run?.advanced?.initial_alpha;
  const pending = otherTask ? 0 : scales.filter(r => !sameNumber(r.target.normalization_scale, r.proposed_scale)).length + (alpha.proposed != null && alphaNow !== alpha.proposed ? 1 : 0);
  const proposals = scales.length + (alpha.proposed != null ? 1 : 0);
  const what = `${scales.length ? `the Scale of ${scales.length} Specs row${scales.length === 1 ? '' : 's'}` : ''}${scales.length && alpha.proposed != null ? ' and ' : ''}${alpha.proposed != null ? 'Initial alpha' : ''}`;
  // The values, for a line that has no table: at most six, then how many more there are.
  const items = [...scales.map(r => `${r.metric_id} ${short(r.proposed_scale)}`), ...(alpha.proposed != null ? [`Initial alpha ${short(alpha.proposed)}`] : [])];
  const values = items.slice(0, 6).join(' · ') + (items.length > 6 ? ` · and ${items.length - 6} more` : '');
  // A task saved from a Virtuoso cell starts only with the rows it has saved (the check before every run), so applied
  // scales need Save task; that save changes Specs only, and the recorded baseline stays.
  const savedTask = String(config.circuit?.task_id ?? '').startsWith('real:');
  const afterwards = savedTask && scales.length ? ' Then press Save task: this task starts only with the rows it has saved, and its recorded baseline is kept.' : '';
  /** The configuration with the proposals written in: ONE change, so one Undo step; nothing for a run of another task. */
  const apply = (c: Json): Json => otherTask ? c : ({ ...c,
    targets: (c.targets ?? []).map((t: Json) => { const row = scales.find(r => r.metric_id === t.metric_id); return row && sameSpecsRow(t, row) ? { ...t, normalization_scale: row.proposed_scale } : t; }),
    run: alpha.proposed == null ? c.run : { ...c.run, advanced: { ...(c.run.advanced ?? {}), initial_alpha: alpha.proposed } } });
  return { rows, scales, alpha, alphaNow, otherTask, pending, proposals, what, values, afterwards, apply };
}
