/** trainingData.ts, part 3 (plan-refactoring C12): what one run's charts and key numbers share, kept per store. */
import { categoryOf, Changes, DESIGN_STATUSES } from './store.ts';
import type { Category, Table, TrainingStore } from './store.ts';
import { typed } from './series.ts';
import type { Typed } from './series.ts';
import type { LearnerX } from './build.ts';

// ------------------------------------------------------------------------------------------------ shared chart preparation
/* Record 7.221 (performance plan, work package A). Before it, every chart worked out on every new frame, from all rows of
 * its run: the catalog, each evaluation's category and pass flag, the learner's restarts, its rows in the order of its x
 * and its running means - eight charts eight times over, and in a comparison for every run again. Now each run keeps what
 * is derived from its rows (Prep: one per store, released with it) and brings it up to date when rows have arrived: only
 * the new rows are looked at, and after a change a Table notes (a new flush replaces the provisional rows, thinning) or
 * a learner restart only what follows the first changed row. A chart then works out its rows in view only; a running
 * mean starts from its checkpoint before them (every SPACING positions), because a mean of the last N evaluations can
 * reach far back and a share so far reaches the first row. Everything is computed with the same operations in the same
 * order as before, so the values drawn are the same numbers: training_data_check.mjs compares these charts with the
 * builders before this record and a store kept up to date with one that derives everything at once. Since branch record
 * SIF-134 a mean over a window of only zeros is 0, where those builders kept a rounding remainder - and carried it into the
 * means after it, which may differ from theirs in the last digit (State, below). */
export const TRAINING = 0, EVALUATION = 1, START = 2;                 // the categories by number
export const CODE: Record<Category, number> = { training: TRAINING, evaluation: EVALUATION, start: START };
let SPACING = 4096;            // positions between two checkpoints of a running mean
/** Closer checkpoints, for training_data_check.mjs: small fixtures then pass many of them. The values are the same at any
 *  spacing; a running mean keeps the spacing it was made with. */
export function setSpacing(positions: number) { if (positions >= 1) SPACING = Math.floor(positions); }
const MEANS = 48;              // running means kept per run (one per chart and category or column): the least recently used go
export type Fill = (from: number, to: number) => Typed;              // a series' values at positions [from, to)

/** The codes of this store's statuses that are a verdict on the design (DESIGN_STATUSES). */
export const designCodes = (store: TrainingStore) =>
  new Set(store.words.status.list.map((word, code) => (DESIGN_STATUSES.includes(word) ? code : -1)).filter(code => code >= 0));

/** The first of the first `n` entries of an ascending array that is at least `v` (n if none). */
export function lowerBound(a: ArrayLike<number>, n: number, v: number): number {
  let lo = 0, hi = n;
  while (lo < hi) { const middle = (lo + hi) >> 1; if (a[middle] < v) lo = middle + 1; else hi = middle; }
  return lo;
}
/** The first that is above `v` (n if none). */
export function upperBound(a: ArrayLike<number>, n: number, v: number): number {
  let lo = 0, hi = n;
  while (lo < hi) { const middle = (lo + hi) >> 1; if (a[middle] <= v) lo = middle + 1; else hi = middle; }
  return lo;
}

/** The rows a chart draws in the order of its x - a learner chart's (learnerOrder of record 7.213), a compared run's
 *  evaluations (7.200) - kept as rows arrive: position p holds row rowAt(p) at x x()[p]. While every row so far is drawn,
 *  in its own order, a position is its row and x the table's own column, so nothing is copied. A row whose x is below the
 *  rows before it (a learner restart by update count) sorts them all: by x, at a repeated x the earlier row first. */
export class Index {
  readonly key: string;
  readonly table: Table;
  readonly column: string;                                   // x
  readonly drawn: ((row: number) => boolean) | null;         // which rows with an x are drawn (null: all)
  readonly members: Changes[];                               // where rows, or whether a row is drawn, changed
  readonly values: Changes[];                                // where what is drawn for a row changed, not whether
  readonly changes = new Changes();                          // positions whose row, x or values may differ
  len = 0;
  private own: { rows: Int32Array; xs: Float64Array } | null = null;
  private scanned = 0;                                       // rows looked at
  private ascending = true;                                  // rows ascend with the positions: a cut keeps a prefix
  private memberSeen: number[];
  private valueSeen: number[];
  constructor(key: string, table: Table, column: string, drawn: ((row: number) => boolean) | null, members: Changes[], values: Changes[]) {
    this.key = key; this.table = table; this.column = column; this.drawn = drawn; this.members = members; this.values = values;
    this.memberSeen = members.map(changes => changes.stamp); this.valueSeen = values.map(changes => changes.stamp);
  }
  x(): ArrayLike<number> { return this.own ? this.own.xs : this.table.cols[this.column]; }
  rowAt(p: number): number { return this.own ? this.own.rows[p] : p; }
  bytes() { return this.own ? this.own.rows.byteLength + this.own.xs.byteLength : 0; }
  /** How many positions hold a row before `row`. */
  before(row: number): number {
    if (!this.own) return Math.min(row, this.len);
    if (this.ascending) return lowerBound(this.own.rows, this.len, row);
    let count = 0;
    for (let pos = 0; pos < this.len; pos++) if (this.own.rows[pos] < row) count += 1;
    return count;
  }
  /** The first position holding `row` or a later row, -1 if none (as Array.findIndex finds it). */
  find(row: number): number {
    if (this.ascending) { const pos = this.before(row); return pos < this.len ? pos : -1; }
    for (let pos = 0; pos < this.len; pos++) if (this.rowAt(pos) >= row) return pos;
    return -1;
  }
  sync(): this {
    const n = this.table.n;
    let back = n;
    this.members.forEach((changes, place) => { back = Math.min(back, changes.since(this.memberSeen[place])); this.memberSeen[place] = changes.stamp; });
    if (back < this.scanned) {
      if (this.ascending && back > 0) { this.len = this.before(back); this.scanned = back; this.changes.note(this.len); }
      else { this.len = 0; this.scanned = 0; this.own = null; this.ascending = true; this.changes.note(0); }     // all again, no copy kept
    }
    let changed = Infinity;
    this.values.forEach((changes, place) => { changed = Math.min(changed, changes.since(this.valueSeen[place])); this.valueSeen[place] = changes.stamp; });
    if (changed < Infinity) this.changes.note(this.ascending ? this.before(changed) : 0);
    if (this.scanned < n) this.extend(n);
    return this;
  }
  private extend(n: number) {
    const xs = this.table.cols[this.column];
    let last = this.len ? this.x()[this.len - 1] : 0;
    for (let row = this.scanned; row < n; row++) {
      const rowX = xs[row];
      if (Number.isNaN(rowX) || (this.drawn && !this.drawn(row))) { if (!this.own) this.copy(this.len); continue; }
      if (this.len && rowX < last) { this.sort(n); return; }
      if (this.own) {
        if (this.len === this.own.rows.length) this.copy(Math.max(256, 2 * this.len));
        this.own.rows[this.len] = row; this.own.xs[this.len] = rowX;
      }
      this.len += 1; last = rowX;
    }
    this.scanned = n;
  }
  /** Rows and x of their own (room for `cap` positions), from here on. */
  private copy(cap: number) {
    const rows = new Int32Array(cap), xs = new Float64Array(cap);
    if (this.own) { rows.set(this.own.rows.subarray(0, this.len)); xs.set(this.own.xs.subarray(0, this.len)); }
    else { for (let pos = 0; pos < this.len; pos++) rows[pos] = pos; xs.set(this.table.cols[this.column].subarray(0, this.len)); }
    this.own = { rows, xs };
  }
  private sort(n: number) {
    const xs = this.table.cols[this.column], rows: number[] = [];
    for (let row = 0; row < n; row++) if (!Number.isNaN(xs[row]) && (!this.drawn || this.drawn(row))) rows.push(row);
    rows.sort((first, second) => xs[first] - xs[second] || first - second);
    this.own = { rows: Int32Array.from(rows), xs: Float64Array.from(rows, row => xs[row]) };
    this.len = rows.length; this.scanned = n;
    this.ascending = rows.every((row, pos) => pos === 0 || row > rows[pos - 1]);
    this.changes.note(0);
  }
}

type MeanKind = 'last' | 'over' | 'share';      // smooth (the last N values), smoothOver (the last N x units), the share so far
/** A running mean before position `pos`: the sum and count of its values, `nz` how many of them are not 0; `lo` its first
 *  position (over); `ring` its values from `head` on, the oldest first (last). A window of zeros sums to 0 (branch record
 *  SIF-134): the additions and subtractions of the values that left it can leave a rounding remainder - "Worst spec miss"
 *  read "mean of last 50 2.558e-17" once every design met its specs. */
interface State { pos: number; sum: number; count: number; nz: number; lo: number; ring: Float64Array | null; head: number }
const copyState = (state: State): State => ({ ...state, ring: state.ring && state.ring.slice() });

/** A running mean, or the share so far, of one series from position `start` on - smooth, smoothOver and the share of
 *  record 7.193's charts - kept as its state every `spacing` positions: the values of any stretch are worked out from the
 *  state before it, with the same additions in the same order as over the whole series, so they are the same numbers.
 *  The series' values come from the chart that asks (`fill`): nothing of a frame is kept beyond it. */
class Running {
  readonly kind: MeanKind;
  readonly window: number;
  readonly start: number;
  readonly index: Index;
  readonly spacing = SPACING;
  private points: State[];                                   // before start, start + spacing, start + 2 spacing, ...
  private end: State | null = null;                          // before `done`
  private done: number;
  private seen: number;
  constructor(kind: MeanKind, window: number, start: number, index: Index) {
    this.kind = kind; this.window = window; this.start = start; this.index = index;
    this.points = [{ pos: start, sum: 0, count: 0, nz: 0, lo: start, ring: kind === 'last' ? new Float64Array(window + 1) : null, head: 0 }];
    this.done = start; this.seen = index.changes.stamp;
  }
  bytes() { return [...this.points, ...(this.end ? [this.end] : [])].reduce((sum, point) => sum + 48 + (point.ring?.byteLength ?? 0), 0); }
  /** Up to date with the index: what follows a change is worked out again from the checkpoint before it. */
  sync(fill: Fill) {
    const len = this.index.len, back = Math.min(this.index.changes.since(this.seen), len);
    this.seen = this.index.changes.stamp;
    if (back < this.done) {
      while (this.points.length > 1 && this.points[this.points.length - 1].pos > back) this.points.pop();
      this.end = null; this.done = this.points[this.points.length - 1].pos;
    }
    if (this.done < len) {
      const state = copyState(this.end ?? this.points[this.points.length - 1]);
      this.run(state, len, null, 0, true, fill);
      this.end = state; this.done = len;
    }
  }
  /** The values at positions [from, to): undefined before `start`, then the mean (or share) at each recorded value. */
  values(from: number, to: number, fill: Fill): Typed {
    const out = typed(Math.max(0, to - from)), at = Math.max(from, this.start);
    if (at >= to) return out;
    let point = this.points[Math.min(this.points.length - 1, Math.floor((at - this.start) / this.spacing))];
    if (this.end && this.end.pos <= at && this.end.pos > point.pos) point = this.end;
    this.run(copyState(point), to, out, from, false, fill);
    return out;
  }
  /** Takes `state` on to position `to`: the values from `outFrom` on into `out`, checkpoints on the way if `keep`. */
  private run(state: State, to: number, out: Typed | null, outFrom: number, keep: boolean, fill: Fill) {
    const { kind, window, start, spacing } = this, len = this.index.len, from = state.pos;
    const base = kind === 'over' ? Math.min(state.lo, from) : from, { kinds, nums } = fill(base, to);
    const xs = this.index.x();
    for (let pos = from; pos < to; pos++) {
      if (keep && (pos - start) % spacing === 0 && pos > this.points[this.points.length - 1].pos) this.points.push(copyState({ ...state, pos }));
      const recorded = kinds[pos - base], value = nums[pos - base];
      let mean = 0;
      if (kind === 'last') {                       // smooth: ring.push(value); sum += value; past the window sum -= ring.shift()
        if (recorded === 2) {
          const ring = state.ring!, size = window + 1;
          ring[(state.head + state.count) % size] = value; state.count += 1; state.sum += value; if (value !== 0) state.nz += 1;
          if (state.count > window) {
            const gone = ring[state.head]; state.sum -= gone; if (gone !== 0) state.nz -= 1; state.head = (state.head + 1) % size; state.count -= 1;
          }
          if (!state.nz) state.sum = 0;            // only zeros in the window (SIF-134)
          mean = state.sum / state.count;
        }
      } else if (kind === 'share') {               // judged += 1, passed += value, passed / judged
        if (recorded === 2) { state.count += 1; state.sum += value; mean = state.sum / state.count; }
      } else {                                     // smoothOver: the value in, then out what is `window` x units behind
        if (recorded === 2) { state.sum += value; state.count += 1; if (value !== 0) state.nz += 1; }
        const limit = xs[pos] - window;
        while (state.lo < len && xs[state.lo] <= limit) {
          const place = state.lo - base, gone = place < kinds.length ? null : fill(state.lo, state.lo + 1);
          if ((gone ? gone.kinds[0] : kinds[place]) === 2) {
            const leaving = gone ? gone.nums[0] : nums[place]; state.sum -= leaving; state.count -= 1; if (leaving !== 0) state.nz -= 1;
          }
          state.lo += 1;
        }
        if (!state.nz && state.count) state.sum = 0;   // only zeros in the window (SIF-134); an empty one keeps its sum, as before
        if (recorded === 2) mean = state.sum / state.count;
      }
      if (out && pos >= outFrom) { out.kinds[pos - outFrom] = recorded; out.nums[pos - outFrom] = mean; }
    }
    state.pos = to;
  }
}

/** What one run's charts and key numbers share (see above), kept per store and released with it. */
export class Prep {
  readonly store: TrainingStore;
  cat = new Uint8Array(0);                       // each evaluation's category: TRAINING, EVALUATION or START (rowCategories)
  pass = new Float64Array(0);                    // each evaluation's pass flag (passFlags)
  readonly counts = [0, 0, 0];                   // evaluations of each category
  superseded = new Uint8Array(0);                // the learner's updates abandoned at a restart (updateBranches)
  restarts: number[] = [];
  restartRows: number[] = [];
  readonly branches = new Changes();             // rows whose abandoned flag changed
  private evaluationsDone = 0;
  private evaluationsSeen: number;
  private updatesDone = 0;
  private updatesSeen: number;
  private top = -Infinity;                       // the learner's last update count (updateBranches)
  private indexes = new Map<string, Index>();
  private facts = new Map<string, { row: number; scanned: number; seen: number[] }>();
  private means = new Map<string, Running>();
  constructor(store: TrainingStore) {
    this.store = store;
    this.evaluationsSeen = store.evaluations.changes.stamp; this.updatesSeen = store.updates.changes.stamp;
  }

  /** Each evaluation's category and pass flag, brought up to date: the rows from the first that changed are counted out,
   *  the arrays sized to the table, and each row not yet derived gets its category and flag. */
  evaluations(): this {
    const table = this.store.evaluations, back = Math.min(table.changes.since(this.evaluationsSeen), table.n);
    this.evaluationsSeen = table.changes.stamp;
    if (back < this.evaluationsDone) this.cutEvaluations(back);
    if (this.evaluationsDone >= table.n) return this;
    this.resizeEvaluationArrays(table);
    this.deriveEvaluations(table);
    return this;
  }
  /** The evaluations from `back` on counted out of their categories, to be derived again. */
  private cutEvaluations(back: number) {
    for (let row = back; row < this.evaluationsDone; row++) this.counts[this.cat[row]] -= 1;
    this.evaluationsDone = back;
  }
  /** `cat` and `pass` made as long as the table's capacity when they are shorter than its rows, or longer than its capacity
   *  while every row is to be derived again (a table smaller after thinning); the rows derived so far are copied. */
  private resizeEvaluationArrays(table: Table) {
    if (this.cat.length < table.n || (this.evaluationsDone === 0 && this.cat.length > table.cap)) {     // grown, or smaller after thinning
      const cat = new Uint8Array(table.cap), pass = new Float64Array(table.cap);
      cat.set(this.cat.subarray(0, this.evaluationsDone)); pass.set(this.pass.subarray(0, this.evaluationsDone));
      this.cat = cat; this.pass = pass;
    }
  }
  /** Each evaluation not yet derived: its category, counted, and its pass flag - whether every hard spec was met (1 or 0)
   *  when its status is a verdict on the design, else NaN (rowCategories and passFlags, row by row). */
  private deriveEvaluations(table: Table) {
    const phases = this.store.words.phase.list, design = designCodes(this.store), phase = table.cols.phase, status = table.cols.status,
      feasible = table.cols.feasible;
    for (let row = this.evaluationsDone; row < table.n; row++) {
      const code = CODE[categoryOf(phases[phase[row]])];
      this.cat[row] = code; this.counts[code] += 1;
      this.pass[row] = design.has(status[row]) && !Number.isNaN(feasible[row]) ? feasible[row] : NaN;
    }
    this.evaluationsDone = table.n;
  }

  /** The learner's restarts and abandoned updates, brought up to date (updateBranches, row by row). A restart marks every
   *  earlier update at or above its count; a cut that takes a restart away clears what it marked: all is derived again. */
  updates(): this {
    const table = this.store.updates, cum = table.cols.cum, back = Math.min(table.changes.since(this.updatesSeen), table.n);
    this.updatesSeen = table.changes.stamp;
    if (back < this.updatesDone) {
      if (this.restartRows.length && this.restartRows[this.restartRows.length - 1] >= back) this.resetUpdates();
      else this.cutUpdates(back, cum);
    }
    if (this.updatesDone >= table.n) return this;
    this.resizeSuperseded(table);
    this.markRestarts(table, cum);
    return this;
  }
  /** Nothing derived from the updates any more (a cut took a restart away): no restart, no update abandoned, and every
   *  mark noted as changed. */
  private resetUpdates() {
    this.superseded.fill(0); this.restarts = []; this.restartRows = []; this.updatesDone = 0; this.top = -Infinity;
    this.branches.note(0);
  }
  /** The updates from `back` on no longer marked, to be derived again; the top is the last count before them. */
  private cutUpdates(back: number, cum: Float64Array) {
    this.superseded.fill(0, back, this.updatesDone); this.updatesDone = back; this.top = -Infinity;
    for (let row = back - 1; row >= 0; row--) if (!Number.isNaN(cum[row])) { this.top = cum[row]; break; }
  }
  /** `superseded` made as long as the table's capacity in the two cases `resizeEvaluationArrays` makes `cat` so; the marks
   *  so far are copied. */
  private resizeSuperseded(table: Table) {
    if (this.superseded.length < table.n || (this.updatesDone === 0 && this.superseded.length > table.cap)) {
      const superseded = new Uint8Array(table.cap);
      superseded.set(this.superseded.subarray(0, this.updatesDone));
      this.superseded = superseded;
    }
  }
  /** Each update not yet derived: a count at or below the one before it is a restart, which marks every earlier update at
   *  or above it abandoned; the first row whose mark it set is noted in `branches`. */
  private markRestarts(table: Table, cum: Float64Array) {
    let flipped = Infinity;
    for (let row = this.updatesDone; row < table.n; row++) {
      const count = cum[row];
      if (Number.isNaN(count)) continue;
      if (count <= this.top) {
        this.restarts.push(count); this.restartRows.push(row);
        for (let earlier = 0; earlier < row; earlier++)
          if (cum[earlier] >= count && !this.superseded[earlier]) { this.superseded[earlier] = 1; if (earlier < flipped) flipped = earlier; }
      }
      this.top = count;
    }
    this.updatesDone = table.n;
    if (flipped < Infinity) this.branches.note(flipped);
  }

  /** The rows of a learner chart in the order of its x (`learnerX`): every update with that count, or (`going`) only those
   *  of the line the learner went on - abandoned ones left out, as compared runs and the key numbers take them. */
  order(learnerX: LearnerX, going: boolean): Index {
    this.updates();
    const key = `order:${learnerX}:${going ? 'going' : 'all'}`, table = this.store.updates;
    let index = this.indexes.get(key);
    if (!index) this.indexes.set(key, index = new Index(key, table, learnerX === 'evaluation' ? 'collected' : 'cum',
      going ? row => !this.superseded[row] : null,                   // drawn
      going ? [table.changes, this.branches] : [table.changes],      // members
      going ? [] : [this.branches]));                                // values
    return index.sync();
  }
  /** The evaluations of the categories `only` (codes; null: every evaluation), in their order (x = the evaluation number). */
  rows(only: number[] | null): Index {
    this.evaluations();
    const key = `rows:${only ? only.join(',') : 'all'}`, table = this.store.evaluations;
    let index = this.indexes.get(key);
    if (!index) this.indexes.set(key, index = new Index(key, table, 'k',
      only ? row => only.includes(this.cat[row]) : null,             // drawn
      [table.changes],                                               // members
      [this.store.specChanges]));                                    // values
    return index.sync();
  }

  /** The first row of `table` for which `test` holds, -1 if none (whether a column has any value, the first passing design,
   *  the first row of a segment), kept as rows arrive; `deps`: the changes it depends on. */
  first(key: string, table: Table, deps: Changes[], test: (row: number) => boolean): number {
    let fact = this.facts.get(key);
    if (!fact) this.facts.set(key, fact = { row: -1, scanned: 0, seen: deps.map(changes => changes.stamp) });
    let back = table.n;
    deps.forEach((changes, place) => { back = Math.min(back, changes.since(fact!.seen[place])); fact!.seen[place] = changes.stamp; });
    if (back < fact.scanned) { fact.scanned = back; if (fact.row >= back) fact.row = -1; }
    if (fact.row < 0) for (let row = fact.scanned; row < table.n; row++) if (test(row)) { fact.row = row; break; }
    fact.scanned = table.n;
    return fact.row;
  }
  /** Whether an evaluation column has a value in any row (a spec's values can also join earlier rows). */
  any(column: string): boolean {
    const table = this.store.evaluations, values = table.cols[column];
    return !!values && this.first(`any ${column}`, table, column.startsWith('spec:') ? [table.changes, this.store.specChanges] : [table.changes],
      row => !Number.isNaN(values[row])) >= 0;
  }
  /** Whether a column of the learner's updates has a value in any row. */
  anyUpdate(column: string): boolean {
    const table = this.store.updates, values = table.cols[column];
    return !!values && this.first(`any update ${column}`, table, [table.changes], row => !Number.isNaN(values[row])) >= 0;
  }

  /** A running mean of a series as the fill of its smoothed line: kept per series (`key`), kind, window and start, and brought
   *  up to date now - before the rows in view are filled, which its values then reuse (remembered). */
  meanFill(key: string, kind: MeanKind, window: number, start: number, index: Index, fill: Fill): Fill {
    const full = `${key}|${kind}|${window}|${start}`;
    let mean = this.means.get(full);
    if (mean && mean.index === index) this.means.delete(full);
    else mean = new Running(kind, window, start, index);
    this.means.set(full, mean);                                  // the most recently used last
    if (this.means.size > MEANS) this.means.delete(this.means.keys().next().value as string);
    mean.sync(fill);
    const kept = mean;
    return (from, to) => kept.values(from, to, fill);
  }
  /** What it holds: running means, indexes, facts, and the bytes of its arrays and checkpoints (preparedSize). */
  size() {
    let bytes = this.cat.byteLength + this.pass.byteLength + this.superseded.byteLength;
    for (const index of this.indexes.values()) bytes += index.bytes();
    for (const mean of this.means.values()) bytes += mean.bytes();
    return { means: this.means.size, indexes: this.indexes.size, facts: this.facts.size, bytes };
  }
}
const PREPARED = new WeakMap<TrainingStore, Prep>();
/** What a store's shared chart preparation holds (null: none yet), for training_data_check.mjs: bounded, gone with the store. */
export function preparedSize(store: TrainingStore) { return PREPARED.get(store)?.size() ?? null; }
/** The store's shared chart preparation: made at its first chart, gone with the store. */
export function prep(store: TrainingStore): Prep {
  let prepared = PREPARED.get(store);
  if (!prepared) PREPARED.set(store, prepared = new Prep(store));
  return prepared;
}

/** A fill that keeps its last stretch: a series' recorded values are asked for again by its running mean (the same rows when
 *  the whole run is in view). The values are only read. */
function remembered(fill: Fill): Fill {
  let last: { from: number; to: number; values: Typed } | null = null;
  return (from, to) => {
    if (!last || last.from !== from || last.to !== to) last = { from, to, values: fill(from, to) };
    return last.values;
  };
}
/** An evaluation chart's values at positions of `index`: the row's value, NaN a gap; with a category (`only`) the rows of
 *  the others are undefined. */
export function valuesFill(p: Prep, index: Index, value: (row: number) => number, only: number | null): Fill {
  return remembered((from, to) => {
    const out = typed(to - from), cat = p.cat;
    for (let pos = from; pos < to; pos++) {
      const row = index.rowAt(pos);
      if (only !== null && cat[row] !== only) continue;
      const rowValue = value(row);
      if (Number.isNaN(rowValue)) out.kinds[pos - from] = 1;
      else { out.kinds[pos - from] = 2; out.nums[pos - from] = rowValue; }
    }
    return out;
  });
}
/** A learner chart's values at positions of `index`: the column times `sign`, NaN a gap; 'main' leaves the updates abandoned
 *  at a restart out (undefined), 'abandoned' has only those, 'all' every position. */
export function learnerFill(p: Prep, index: Index, column: string, sign: number, which: 'main' | 'abandoned' | 'all'): Fill {
  return remembered((from, to) => {
    const out = typed(to - from), values = p.store.updates.cols[column], superseded = p.superseded;
    for (let pos = from; pos < to; pos++) {
      const row = index.rowAt(pos);
      if (which !== 'all' && (superseded[row] === 1) !== (which === 'abandoned')) continue;
      if (Number.isNaN(values[row])) out.kinds[pos - from] = 1;
      else { out.kinds[pos - from] = 2; out.nums[pos - from] = sign * values[row]; }
    }
    return out;
  });
}
