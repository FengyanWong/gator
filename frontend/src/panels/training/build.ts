/** trainingData.ts, part 5 (plan-refactoring C12): one run's chart - its rows in view, thinned for the screen. */
import { labelOf } from './store.ts';
import type { Category, Context, Table, TrainingStore } from './store.ts';
import { boxed, decimateTyped, visibleRows } from './series.ts';
import type { Typed } from './series.ts';
import { catalog, LEARNER_COLUMNS } from './catalog.ts';
import type { Axis, Built, Marker, Series } from './catalog.ts';
import { CODE, learnerFill, prep, valuesFill } from './prep.ts';
import type { Fill, Index, Prep } from './prep.ts';

/** Where the run continued after a pause or a crash: the first row recorded at or after each later segment's start. */
function resumeMarkers(store: TrainingStore, table: Table, xColumn: string): Marker[] {
  const markers: Marker[] = [], p = prep(store), which = table === store.evaluations ? 'evaluations' : 'updates';
  for (const segment of store.segments.slice(1)) {
    const start = segment.started_utc ? Date.parse(segment.started_utc) / 1000 : NaN;
    if (!Number.isFinite(start)) continue;
    const row = p.first(`${which} from ${start}`, table, [table.changes], i => table.cols.t[i] >= start);
    if (row >= 0) markers.push({ x: table.cols[xColumn][row], label: `continued (segment ${segment.segment})`, kind: 'resume' });
  }
  return markers;
}

/** What part of the x axis a chart shows. all: the whole run, growing with it. follow: the newest `width` x units, sliding as
 *  results arrive ("Follow latest" after a zoom). fixed: what the user zoomed to; new results do not move it. */
export type View = { mode: 'all' } | { mode: 'follow'; width: number } | { mode: 'fixed'; min: number; max: number };

/** What an evaluation chart takes from one run: each row's value (NaN = a gap), the categories it draws, and how: `single` = one
 *  stepped line over every row (the best design so far), `cumulative` = the share so far instead of a mean. */
export function evaluationValues(store: TrainingStore, p: Prep, id: string) {
  const t = store.evaluations;
  let value = (_row: number) => NaN;
  let allowed: Category[] = ['training', 'evaluation', 'start'], single: string | null = null, cumulative = false;
  const copy = (column: string) => { const c = t.cols[column]; if (c) value = row => c[row]; };
  if (id === 'reward') { copy('reward'); allowed = ['training', 'evaluation']; }
  else if (id === 'pass') { value = row => p.pass[row]; allowed = ['training', 'evaluation']; }
  else if (id === 'eval_pass') { value = row => p.pass[row]; allowed = ['evaluation']; cumulative = true; }
  else if (id === 'violation') copy('violation');
  else if (id === 'margin') copy('margin');
  else if (id === 'seconds') copy('seconds');
  else if (id === 'best') { copy('bestViolation'); single = 'Best design so far'; }
  else if (id === 'objective') {
    const c = t.cols.bestObjective, feasible = t.cols.bestFeasible;
    value = row => (feasible[row] !== 1 ? NaN : c[row]);
    single = 'Best feasible design so far';
  }
  else if (id.startsWith('spec:')) copy(id);
  return { value, allowed, single, cumulative };
}

/** What a learner chart's x is: the learner's update count, or the number of evaluations collected when the update ran
 *  (learner_updates.evaluations_collected, record 7.213) - the evaluation charts' x, on which runs that learn 1 and 8
 *  times per evaluation line up. Several updates after one evaluation share its x there. */
export type LearnerX = 'update' | 'evaluation';
export const noCount = (learnerX: LearnerX) => (learnerX === 'evaluation' ? 'it records no evaluation count with its learner updates' : 'it records no update count');

/** A series before the rows in view are known: what it is (`meta`, whose values cut fills in) and where its values come
 *  from - `fill` at positions, or a limit's one value in every row. */
export interface Lazy { meta: Series; fill: Fill | null; limit?: number }
/** A spec's limits, as constant dashed lines (a comparison's are its first run's). */
export function limitSeries(store: TrainingStore, id: string, name: (label: string) => string): Lazy[] {
  const def = store.specDefs[id.slice(5)], out: Lazy[] = [];
  for (const [bound, label] of [[def?.threshold_lower, 'lower limit'], [def?.threshold_upper, 'upper limit']] as [number | null | undefined, string][]) {
    if (bound != null && Number.isFinite(bound)) out.push({ meta: { label: name(label), role: 'limit', category: null, values: [] }, fill: null, limit: bound });
  }
  return out;
}

/** One chart's data: rows in view (plus one beyond each edge), thinned to `buckets` pixel columns by `decimate`. */
export function build(store: TrainingStore, id: string, smoothing: number, view: View, buckets: number, context: Context = {}, learnerX: LearnerX = 'update'): Built {
  const spec = catalog(store, context).find(c => c.id === id);
  const unit = spec?.unit ?? '';
  if (spec?.axis === 'update') return buildUpdates(store, id, smoothing, view, buckets, unit, learnerX);
  const t = store.evaluations, n = t.n, k = t.cols.k, p = prep(store), index = p.rows(null);        // every row, in its order
  const { value, allowed, single, cumulative } = evaluationValues(store, p, id);
  const series: Lazy[] = [];
  // Over a thinned stretch (memory bound) only its extremes are left: no mean is drawn there, and the mean starts after it.
  const full = store.thinnedEvaluations;
  if (single) {
    series.push({ meta: { label: single, role: 'line', category: null, step: true, values: [] }, fill: valuesFill(p, index, value, null) });
  } else {
    for (const category of allowed) {
      const code = CODE[category];
      if (!p.counts[code]) continue;
      const label = labelOf(category, context), raw = valuesFill(p, index, value, code), key = `${index.key}|${id}|${code}`;
      if (cumulative) {
        series.push({ meta: { label: `${label} (each design)`, role: 'raw', category, values: [] }, fill: raw });
        series.push({ meta: { label: full ? `${label}: share since evaluation ${k[full]}` : `${label}: share so far`, role: 'smooth', category, values: [] },
          fill: p.meanFill(key, 'share', 0, full, index, raw) });
      } else if (smoothing > 0 && category !== 'start') {     // an episode start re-simulates one design: no mean of it
        series.push({ meta: { label: `${label} (recorded)`, role: 'raw', category, values: [] }, fill: raw });
        series.push({ meta: { label: `${label}: mean of last ${smoothing}`, role: 'smooth', category, values: [] }, fill: p.meanFill(key, 'last', smoothing, full, index, raw) });
      } else series.push({ meta: { label, role: 'raw', category, values: [] }, fill: raw });
    }
  }
  if (id.startsWith('spec:')) series.push(...limitSeries(store, id, label => label));
  const extent: [number, number] | null = n ? [k[0], k[n - 1]] : null;
  const markers = resumeMarkers(store, t, 'k');
  const thinnedTo = store.thinnedEvaluations > 0 ? k[store.thinnedEvaluations - 1] : null;
  return cut(index, series, extent, view, buckets, markers, thinnedTo, 'evaluation', unit);
}

export const meanLabel = (smoothing: number, learnerX: LearnerX) => `mean of last ${smoothing}${learnerX === 'evaluation' ? ' evaluations' : ''}`;

/** A learner chart: its rows in the order of its x (by update count or by evaluations collected: rows without that count
 *  left out; at a repeated x the earlier row first - an abandoned update before the update that replaced it), the mean
 *  over the last `smoothing` updates or the updates of the last `smoothing` evaluations, from the first row after a thinned
 *  stretch on. */
function buildUpdates(store: TrainingStore, id: string, smoothing: number, view: View, buckets: number, unit: string, learnerX: LearnerX): Built {
  const t = store.updates, p = prep(store), index = p.order(learnerX, false), column = index.column, x = index.x();
  const series: Lazy[] = [];
  for (const [col, label] of LEARNER_COLUMNS[id] ?? []) {
    const sign = id === 'entropy' ? -1 : 1, main = learnerFill(p, index, col, sign, 'main');
    if (smoothing > 0) {
      const thinned = store.thinnedUpdates, from = thinned ? Math.max(0, index.find(thinned)) : 0;     // the mean starts after a thinned stretch
      series.push({ meta: { label: `${label} (recorded)`, role: 'raw', category: null, values: [] }, fill: main });
      series.push({ meta: { label: `${label}: ${meanLabel(smoothing, learnerX)}`, role: 'smooth', category: null, values: [] },
        fill: p.meanFill(`${index.key}|${col}|${sign}`, learnerX === 'evaluation' ? 'over' : 'last', smoothing, from, index, main) });
    } else series.push({ meta: { label, role: 'raw', category: null, values: [] }, fill: main });
    if (p.restarts.length) series.push({ meta: { label: `${label}: abandoned at a restart`, role: 'superseded', category: null, values: [] }, fill: learnerFill(p, index, col, sign, 'abandoned') });
  }
  const restartX = learnerX === 'evaluation' ? p.restartRows.map(j => t.cols.collected[j]).filter(v => !Number.isNaN(v)) : p.restarts;
  const markers = [...resumeMarkers(store, t, column), ...restartX.map(v => ({ x: v, label: 'learner restarted from its save point', kind: 'restart' as const }))];
  const extent: [number, number] | null = index.len ? [x[0], x[index.len - 1]] : null;
  const thinnedTo = store.thinnedUpdates > 0 ? t.cols[column][store.thinnedUpdates - 1] : null;
  const made = cut(index, series, extent, view, buckets, markers, Number.isNaN(thinnedTo) ? null : thinnedTo, 'update', unit);
  return t.n && !index.len ? { ...made, missing: [{ label: 'this run', reason: noCount(learnerX) }] } : made;
}

/** The x range a view shows on this extent: a single point gets one unit on each side, so it is drawn. */
export function viewRange(view: View, extent: [number, number]): [number, number] {
  const [first, last] = extent;
  const [min, max] = view.mode === 'fixed' ? [view.min, view.max] : view.mode === 'follow' ? [Math.max(first, last - view.width), last] : [first, last];
  return max > min ? [min, max] : [min - 1, max + 1];
}

/** The rows of `index` in view (plus one beyond each edge), thinned to `buckets` pixel columns by `decimate`: only their values
 *  are worked out. A limit is the same in every row and changes nothing that decimate keeps. */
function cut(index: Index, series: Lazy[], extent: [number, number] | null, view: View, buckets: number,
  markers: Marker[], thinnedTo: number | null, axis: Axis, unit: string): Built {
  if (!extent) return { axis, x: [], rows: [], series: series.map(s => ({ ...s.meta, values: [] })), markers, thinnedTo, extent, range: null, unit };
  const x = index.x(), [min, max] = viewRange(view, extent);
  const [from, to] = visibleRows(x, index.len, min, max);
  const values = series.map(s => (s.fill ? s.fill(from, to) : null));
  const keep = decimateTyped(x, values.filter((v): v is Typed => v !== null), from, to, min, max, Math.max(16, Math.floor(buckets)));
  return { axis, x: keep.map(i => x[i]), rows: keep.map(i => index.rowAt(i)), unit, markers, thinnedTo, extent, range: [min, max],
    series: series.map((s, j) => { const v = values[j]; return { ...s.meta, values: keep.map(i => (v ? boxed(v, i - from) : s.limit)) }; }) };
}
