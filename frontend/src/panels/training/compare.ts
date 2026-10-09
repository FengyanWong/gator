/** trainingData.ts, part 6 (plan-refactoring C12): up to four runs on one chart. */
import type { Context, TrainingStore } from './store.ts';
import { boxed, decimateTyped, typed } from './series.ts';
import type { Typed } from './series.ts';
import { catalog, LEARNER_COLUMNS } from './catalog.ts';
import type { Axis, Built } from './catalog.ts';
import { CODE, learnerFill, lowerBound, prep, upperBound, valuesFill } from './prep.ts';
import type { Index } from './prep.ts';
import { evaluationValues, limitSeries, meanLabel, noCount, viewRange } from './build.ts';
import type { Lazy, LearnerX, View } from './build.ts';

// ------------------------------------------------------------------------------------------------- several runs on one chart
/** A run on a comparison chart (record 7.200): its store, the name the chart gives it, what the page knows of it. */
export interface CompareRun { store: TrainingStore; label: string; context?: Context }
export const COMPARE_MAX = 4;
/** One run's rows on a comparison chart (in the order of the chart's x) and its series at them. */
interface Part { index: Index; series: Lazy[] }

/** Up to four runs on one chart, each its own colour (Series.run), on one x axis: the evaluation's number in each run's
 *  recorded order, or for the learner's charts its update count or the evaluations collected (`learnerX`). A run's designs
 *  are one series - a training run's training designs, a frozen run's evaluated ones; episode starts (one design
 *  re-simulated) are left out, so are a learner's abandoned updates after a restart. A run that cannot be drawn on this
 *  chart (it has no such spec, the spec's unit differs, it records no learner updates) is listed in `missing` with the
 *  reason. Limits are the first run's. */
export function buildCompare(runs: CompareRun[], id: string, smoothing: number, view: View, buckets: number, learnerX: LearnerX = 'update'): Built {
  const first = runs[0];
  const spec = catalog(first.store, first.context ?? {}).find(c => c.id === id);
  const unit = spec?.unit ?? '', axis: Axis = spec?.axis ?? 'evaluation';
  const missing: { label: string; reason: string }[] = [];
  const parts: Part[] = [];
  runs.forEach((run, r) => {
    const own = catalog(run.store, run.context ?? {}).find(c => c.id === id);
    if (!own?.available) { missing.push({ label: run.label, reason: own?.reason ?? 'this run has no such chart' }); return; }
    if (own.unit !== unit) { missing.push({ label: run.label, reason: `its ${own.title} is in ${own.unit || 'no unit'}, not in ${unit || 'no unit'}` }); return; }
    const part = axis === 'update' ? learnerPart(run, r, id, smoothing, learnerX) : evaluationPart(run, r, id, smoothing);
    if (!part.index.len && axis === 'update') { missing.push({ label: run.label, reason: noCount(learnerX) }); return; }
    parts.push(part);
  });
  const series = parts.flatMap(part => part.series);
  if (id.startsWith('spec:')) series.push(...limitSeries(first.store, id, label => `${label} (${first.label})`));
  // One x axis for all runs: each x value as many times as the run that has it most often (by evaluation, a run that learns
  // 8 times per evaluation has 8 updates at one x), so the runs share the slots of an x and each keeps its own rows in order.
  // Its ends are the runs' first and last x (0 for -0, as the axis' values are numbers read as Map keys before 7.221).
  let lo = Infinity, hi = -Infinity;
  for (const { index } of parts) if (index.len) { const x = index.x(); lo = Math.min(lo, x[0]); hi = Math.max(hi, x[index.len - 1]); }
  const extent: [number, number] | null = lo <= hi ? [lo + 0, hi + 0] : null;
  if (!extent) return { axis, x: [], rows: [], series: series.map(s => ({ ...s.meta, values: [] })), markers: [], thinnedTo: null, extent, range: null, unit, missing };
  const [min, max] = viewRange(view, extent);
  const slots = slotsInView(parts, min, max), n = slots.n;
  const values: (Typed | null)[] = [];
  parts.forEach((part, j) => {
    const at = slots.at[j];
    let a = Infinity, b = -1;
    for (let slot = 0; slot < n; slot++) { const position = at[slot]; if (position >= 0) { if (position < a) a = position; if (position > b) b = position; } }
    for (const s of part.series) {
      const out = typed(n);
      if (b >= 0) {
        const own = s.fill!(a, b + 1);
        for (let slot = 0; slot < n; slot++) { const position = at[slot]; if (position >= 0) { out.kinds[slot] = own.kinds[position - a]; out.nums[slot] = own.nums[position - a]; } }
      }
      values.push(out);
    }
  });
  while (values.length < series.length) values.push(null);                       // the limits
  const keep = decimateTyped(slots.x, values.filter((v): v is Typed => v !== null), 0, n, min, max, Math.max(16, Math.floor(buckets)));
  return { axis, x: keep.map(i => slots.x[i]), rows: keep.map(() => -1), unit, markers: [], thinnedTo: null, extent, range: [min, max],
    series: series.map((s, j) => { const v = values[j]; return { ...s.meta, values: keep.map(i => (v ? boxed(v, i) : s.limit)) }; }), missing };
}

/** The slots of a comparison's x axis that are in view - visibleRows of the whole axis: every slot of the x values in
 *  [min, max], the last slot before them and the first after - with the position of each run's row in each slot (-1: none),
 *  without making the whole axis. A run fills the first slots of an x with its rows there, in their order. */
function slotsInView(parts: Part[], min: number, max: number): { x: Float64Array; at: Int32Array[]; n: number } {
  const count = parts.length, xs = parts.map(part => part.index.x()), lens = parts.map(part => part.index.len);
  const from = new Int32Array(count), to = new Int32Array(count);
  let room = 2;                                  // every slot holds a row of some run: no more slots than rows, and the two edges
  for (let j = 0; j < count; j++) { from[j] = lowerBound(xs[j], lens[j], min); to[j] = upperBound(xs[j], lens[j], max); room += to[j] - from[j]; }
  const x = new Float64Array(room), at = parts.map(() => new Int32Array(room).fill(-1)), counts = new Int32Array(count);
  let n = 0;
  // the last slot of the largest x below min: the runs that have that x as often as the run that has it most often
  let before = 0, hasBefore = false;
  for (let j = 0; j < count; j++) if (from[j] > 0 && (!hasBefore || xs[j][from[j] - 1] > before)) { before = xs[j][from[j] - 1]; hasBefore = true; }
  if (hasBefore) {
    let need = 0;
    for (let j = 0; j < count; j++) { counts[j] = from[j] > 0 && xs[j][from[j] - 1] === before ? from[j] - lowerBound(xs[j], lens[j], before) : 0; if (counts[j] > need) need = counts[j]; }
    x[n] = before + 0;                             // + 0: the axis' values are 0 for -0 (as Map keys read before 7.221)
    for (let j = 0; j < count; j++) if (counts[j] === need) at[j][n] = from[j] - 1;
    n += 1;
  }
  // every slot of the x values in [min, max], the runs' rows merged in the order of x
  const cursor = Int32Array.from(from);
  for (;;) {
    let v = 0, found = false;
    for (let j = 0; j < count; j++) if (cursor[j] < to[j] && (!found || xs[j][cursor[j]] < v)) { v = xs[j][cursor[j]]; found = true; }
    if (!found) break;
    let need = 0;
    for (let j = 0; j < count; j++) {
      const own = xs[j];
      let c = 0;
      while (cursor[j] + c < to[j] && own[cursor[j] + c] === v) c++;
      counts[j] = c; if (c > need) need = c;
    }
    for (let slot = 0; slot < need; slot++, n++) { x[n] = v + 0; for (let j = 0; j < count; j++) if (slot < counts[j]) at[j][n] = cursor[j] + slot; }
    for (let j = 0; j < count; j++) cursor[j] += counts[j];
  }
  // the first slot of the smallest x above max: each run that has it, with its first row there
  let after = 0, hasAfter = false;
  for (let j = 0; j < count; j++) if (to[j] < lens[j] && (!hasAfter || xs[j][to[j]] < after)) { after = xs[j][to[j]]; hasAfter = true; }
  if (hasAfter) {
    x[n] = after + 0;
    for (let j = 0; j < count; j++) if (to[j] < lens[j] && xs[j][to[j]] === after) at[j][n] = to[j];
    n += 1;
  }
  return { x, at, n };
}

/** One run's series of an evaluation chart in a comparison: its rows of the chart's categories but episode starts. */
function evaluationPart(run: CompareRun, r: number, id: string, smoothing: number): Part {
  const { store, label } = run, p = prep(store);
  const { value, allowed, single, cumulative } = evaluationValues(store, p, id);
  const index = p.rows(single ? null : allowed.filter(c => c !== 'start').map(c => CODE[c]));
  const raw = valuesFill(p, index, value, null), key = `${index.key}|${id}`;
  const full = index.before(store.thinnedEvaluations);       // rows of a thinned stretch among the kept ones: no mean over them
  if (single) return { index, series: [{ meta: { label, role: 'line', category: null, run: r, step: true, values: [] }, fill: raw }] };
  if (cumulative) return { index, series: [{ meta: { label: `${label} (each design)`, role: 'raw', category: null, run: r, values: [] }, fill: raw },
    { meta: { label: `${label}: share so far`, role: 'smooth', category: null, run: r, values: [] }, fill: p.meanFill(key, 'share', 0, full, index, raw) }] };
  if (smoothing > 0) return { index, series: [{ meta: { label: `${label} (recorded)`, role: 'raw', category: null, run: r, values: [] }, fill: raw },
    { meta: { label: `${label}: mean of last ${smoothing}`, role: 'smooth', category: null, run: r, values: [] }, fill: p.meanFill(key, 'last', smoothing, full, index, raw) }] };
  return { index, series: [{ meta: { label, role: 'raw', category: null, run: r, values: [] }, fill: raw }] };
}

/** One run's series of a learner chart in a comparison: its updates on the line it went on (abandoned ones left out). */
function learnerPart(run: CompareRun, r: number, id: string, smoothing: number, learnerX: LearnerX): Part {
  const { store, label } = run, p = prep(store), index = p.order(learnerX, true);
  const from = store.thinnedUpdates ? Math.max(0, index.find(store.thinnedUpdates)) : 0;
  const columns = LEARNER_COLUMNS[id] ?? [];
  const series: Lazy[] = [];
  columns.forEach(([column, name], c) => {
    const sign = id === 'entropy' ? -1 : 1, values = learnerFill(p, index, column, sign, 'all');
    const named = columns.length > 1 ? `${label} / ${name}` : label;      // the run's name stays whole in its legend key
    if (smoothing > 0) {
      series.push({ meta: { label: `${named} (recorded)`, role: 'raw', category: null, run: r, dash: c > 0, values: [] }, fill: values });
      series.push({ meta: { label: `${named}: ${meanLabel(smoothing, learnerX)}`, role: 'smooth', category: null, run: r, dash: c > 0, values: [] },
        fill: p.meanFill(`${index.key}|${column}|${sign}`, learnerX === 'evaluation' ? 'over' : 'last', smoothing, from, index, values) });
    } else series.push({ meta: { label: named, role: 'raw', category: null, run: r, dash: c > 0, values: [] }, fill: values });
  });
  return { index, series };
}
