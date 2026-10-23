/** trainingData.ts, part 7 (plan-refactoring C12): the key numbers the Training tab writes for each run. */
import type { Context, TrainingStore } from './store.ts';
import { lowerBound, prep, START, upperBound } from './prep.ts';

// ------------------------------------------------------------------------------------------------------ a run's key numbers
/** The line of numbers the Training tab writes for each run on its charts (record 7.215, the user's choice "Key numbers in
 *  the tab"), all read from the recorded rows - nothing estimated, and episode starts left out as on the charts (one that
 *  passed before the first passing design is named apart, startPassed). null: the run has no such number (yet). With a
 *  thinned history (memory bound) the first passing design is the first one kept. */
export interface KeyNumbers {
  evaluations: number;                                       // recorded evaluations, as the head counts them
  firstPass: number | null;                                  // the evaluation number of the first design meeting every hard spec
  startPassed: number | null;                                // the evaluation number of an episode start that met them all before firstPass (or with none)
  recent: { passed: number; judged: number; from: number; to: number } | null;   // designs of the last RECENT evaluations with a verdict
  bestMiss: number | null;                                   // the best design so far: its worst-spec miss at the newest evaluation
  entropy: [number, number] | null;                          // the entropy estimate: mean of the updates of the first and of the last ENDS evaluations
  alpha: [number, number] | null;                            // the temperature α, the same way
}
export const RECENT = 100, ENDS = 50;

export function keyNumbers(store: TrainingStore, context: Context = {}): KeyNumbers {
  const t = store.evaluations, k = t.cols.k, n = t.n, p = prep(store).evaluations(), cat = p.cat, pass = p.pass;
  let firstPass: number | null = null, recent: KeyNumbers['recent'] = null, bestMiss: number | null = null;
  const first = p.first('first passing design', t, [t.changes], row => p.cat[row] !== START && p.pass[row] === 1);
  if (first >= 0) firstPass = k[first];
  // An episode start that passed before it (branch record SIF-116): Run status's first feasible design counts the starts, and
  // its "at 4 evaluations" beside "evaluation 35" here read as a contradiction. Rows ascend with the evaluation number.
  const firstStart = p.first('first passing episode start', t, [t.changes], row => p.cat[row] === START && p.pass[row] === 1);
  const startPassed = firstStart >= 0 && (first < 0 || firstStart < first) ? k[firstStart] : null;
  if (n) {
    const to = k[n - 1], from = Math.max(k[0], to - RECENT + 1);
    let passed = 0, judged = 0;
    for (let i = n - 1; i >= 0 && k[i] >= from; i--) if (cat[i] !== START && !Number.isNaN(pass[i])) { judged += 1; passed += pass[i]; }
    recent = { passed, judged, from, to };
  }
  for (let i = n - 1; i >= 0 && bestMiss === null; i--) if (!Number.isNaN(t.cols.bestViolation[i])) bestMiss = t.cols.bestViolation[i];
  let entropy: [number, number] | null = null, alpha: [number, number] | null = null;
  const u = store.updates;
  if (!context.calibration && store.learner.recorded && u.n) {
    const index = p.order('evaluation', true), x = index.x(), len = index.len;     // by evaluation, abandoned updates left out
    if (len) {
      const firstX = x[0], lastX = x[len - 1];
      // the updates with lo <= x <= hi: one stretch of positions, added up in their order
      const mean = (column: string, sign: number, lo: number, hi: number) => {
        let sum = 0, count = 0;
        const c = u.cols[column];
        for (let j = lowerBound(x, len, lo), end = upperBound(x, len, hi); j < end; j++) { const v = c[index.rowAt(j)]; if (!Number.isNaN(v)) { sum += sign * v; count += 1; } }
        return count ? sum / count : NaN;
      };
      const ends = (column: string, sign: number): [number, number] | null => {
        const a = mean(column, sign, firstX, firstX + ENDS - 1), b = mean(column, sign, lastX - ENDS + 1, lastX);
        return Number.isNaN(a) || Number.isNaN(b) ? null : [a, b];
      };
      entropy = ends('logp', -1); alpha = ends('alpha', 1);
    }
  }
  return { evaluations: store.counts().evaluations, firstPass, startPassed, recent, bestMiss, entropy, alpha };
}
