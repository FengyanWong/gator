/** trainingData.ts, part 2 (plan-refactoring C12): the maths of a series - the learner's restarts, running means, the
 *  values of a stretch of positions, thinning for the screen and the rows in view. */
import type { Table } from './store.ts';

/** Learner counter resets: after a resume from a save point older than the run's last updates (the worker died), the
 *  learner continues from the save point's count, so cumulative_updates repeats numbers it had already recorded. The
 *  updates recorded after that save point belong to a line the learner abandoned: `superseded` marks them, `restarts`
 *  lists where the learner went on (x = its first update after the restart; `restartRows`: that update's row). */
export function updateBranches(table: Table): { superseded: Uint8Array; restarts: number[]; restartRows: number[] } {
  const cum = table.cols.cum, superseded = new Uint8Array(table.n), restarts: number[] = [], restartRows: number[] = [];
  let top = -Infinity;
  for (let j = 0; j < table.n; j++) {
    const v = cum[j];
    if (Number.isNaN(v)) continue;
    if (v <= top) {
      restarts.push(v); restartRows.push(j);
      for (let i = 0; i < j; i++) if (cum[i] >= v) superseded[i] = 1;
      top = v;
    } else top = v;
  }
  return { superseded, restarts, restartRows };
}

/** A trailing mean over the last `window` recorded values of one series (its own positions only; a gap neither counts
 *  nor resets the window). At a gap the mean is a gap too, so a missing value stays visible on the smoothed line. A window
 *  of zeros is 0, not the rounding remainder of the values that left it (`nz`: the values in it that are not 0; branch
 *  record SIF-134, as the charts' running means in prep.ts). */
export function smooth(values: (number | null | undefined)[], window: number): (number | null | undefined)[] {
  const out: (number | null | undefined)[] = new Array(values.length);
  const ring: number[] = [];
  let sum = 0, nz = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v === undefined) { out[i] = undefined; continue; }
    if (v === null) { out[i] = null; continue; }
    ring.push(v); sum += v; if (v !== 0) nz += 1;
    if (ring.length > window) { const gone = ring.shift()!; sum -= gone; if (gone !== 0) nz -= 1; }
    if (!nz) sum = 0;
    out[i] = sum / ring.length;
  }
  return out;
}

/** As `smooth`, but the window is the last `width` units of a sorted x instead of a number of values: learner updates by
 *  evaluation are averaged over the updates of the last `width` evaluations, however many updates an evaluation had (record
 *  7.213). A row is in the window of every later row up to `width` x units on, and of the rows at its own x after it. */
export function smoothOver(x: ArrayLike<number>, values: (number | null | undefined)[], width: number): (number | null | undefined)[] {
  const out: (number | null | undefined)[] = new Array(values.length);
  let lo = 0, sum = 0, count = 0, nz = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (typeof v === 'number') { sum += v; count += 1; if (v !== 0) nz += 1; }
    while (x[lo] <= x[i] - width) { const w = values[lo]; if (typeof w === 'number') { sum -= w; count -= 1; if (w !== 0) nz -= 1; } lo++; }
    if (!nz && count) sum = 0;                               // a window of zeros (SIF-134, as smooth); an empty one as before
    out[i] = v === undefined ? undefined : v === null ? null : sum / count;
  }
  return out;
}

/** Values of a series at a stretch of positions without a JS value per point (record 7.221): kind 0 = undefined (a row of
 *  another category, an abandoned update: nothing drawn there), 1 = null (a gap), 2 = the number in `nums`. */
export interface Typed { kinds: Uint8Array; nums: Float64Array }
export const typed = (n: number): Typed => ({ kinds: new Uint8Array(n), nums: new Float64Array(n) });
export const boxed = (values: Typed, i: number) => (values.kinds[i] === 0 ? undefined : values.kinds[i] === 1 ? null : values.nums[i]);

/** Which rows to draw so that `buckets` pixel columns show the data faithfully: in every pixel column the first and the
 *  last row and, for every series, its first and last value, its smallest and largest value and its first gap. Every row
 *  kept is a recorded row with all its values; spikes and gaps survive. Below 3 rows per pixel column everything is kept. */
export function decimate(x: ArrayLike<number>, series: (number | null | undefined)[][], from: number, to: number, xMin: number, xMax: number, buckets: number): number[] {
  return decimateTyped(x, series.map(values => {
    const out = typed(Math.max(0, to - from));
    for (let r = from; r < to; r++) {
      const v = values[r];
      if (v === null) out.kinds[r - from] = 1;
      else if (v !== undefined) { out.kinds[r - from] = 2; out.nums[r - from] = v; }
    }
    return out;
  }), from, to, xMin, xMax, buckets);
}
/** decimate, the series given at positions [from, to). */
export function decimateTyped(x: ArrayLike<number>, series: Typed[], from: number, to: number, xMin: number, xMax: number, buckets: number): number[] {
  const count = to - from;
  if (count <= 0) return [];
  if (count <= buckets * 3 || !(xMax > xMin)) return Array.from({ length: count }, (_, i) => from + i);
  const kept: number[] = [];
  const scale = buckets / (xMax - xMin);
  let i = from;
  while (i < to) {
    const bucket = Math.min(buckets - 1, Math.max(0, Math.floor((x[i] - xMin) * scale)));
    let end = i;
    while (end < to && Math.min(buckets - 1, Math.max(0, Math.floor((x[end] - xMin) * scale))) === bucket) end++;
    if (end === i) end = i + 1;          // an x that is not a number has no pixel column: a row of its own, never a loop without end
    const rows = new Set<number>([i, end - 1]);
    for (const { kinds, nums } of series) {
      let first = -1, last = -1, lo = -1, hi = -1, gap = -1;
      for (let r = i; r < end; r++) {
        const kind = kinds[r - from];
        if (kind === 0) continue;
        if (first < 0) first = r;
        last = r;
        if (kind === 1) { if (gap < 0) gap = r; continue; }
        const v = nums[r - from];
        if (lo < 0 || v < nums[lo - from]) lo = r;
        if (hi < 0 || v > nums[hi - from]) hi = r;
      }
      for (const r of [first, last, lo, hi, gap]) if (r >= 0) rows.add(r);
    }
    kept.push(...[...rows].sort((a, b) => a - b));
    i = end;
  }
  return kept;
}

/** The rows of a sorted x column inside [min, max], plus one row on each side, so that lines reach the edges. */
export function visibleRows(x: ArrayLike<number>, n: number, min: number, max: number): [number, number] {
  let lo = 0, hi = n;
  while (lo < hi) { const m = (lo + hi) >> 1; if (x[m] < min) lo = m + 1; else hi = m; }
  let from = lo;
  lo = from; hi = n;
  while (lo < hi) { const m = (lo + hi) >> 1; if (x[m] <= max) lo = m + 1; else hi = m; }
  let to = lo;
  if (from > 0) from -= 1;
  if (to < n) to += 1;
  return [from, to];
}
