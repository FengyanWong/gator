/** The Training tab's numbers in the browser (record 7.193): what the backend sends (training_series.py), kept per run,
 *  and turned into chart series. No React and no imports, so that frontend/scripts/training_data_check.mjs can run this
 *  file under Node as it is (Node strips the types) and check the arithmetic on fixtures.
 *
 *  What is kept: every recorded row, in commit order - evaluations (x = their number in recorded order, 1-based) and
 *  learner updates (x = the learner's cumulative update count, or - "Learner by evaluation", record 7.213 - the number of
 *  evaluations collected when the update ran, the evaluation charts' x). A missing or invalid value is NaN here and a gap (null)
 *  in a chart, never a zero. The journal's tail (bundles no flush has published yet) is the provisional end of the
 *  tables: cursor pages extend it; a new flush replaces it, so no bundle is counted twice.
 *
 *  Memory is bounded: past EVALUATION_CAP / UPDATE_CAP rows the oldest half of a table is thinned - in each bin of rows
 *  only the rows holding a column's smallest or largest value (and the bin's first and last row) stay, so every row kept
 *  is a recorded one. With more independent extremes than available row slots, the bound takes precedence. The page
 *  says when it thins history; the run's tables keep every row. */

export type Coded = { values: string[]; codes: number[] };
export type Columns = { n: number; [name: string]: unknown };
export interface SpecDef { unit: string | null; threshold_lower: number | null; threshold_upper: number | null; hard: boolean | null }
export interface Chunk { evaluations: Columns; updates: Columns; specs: Columns; spec_defs: Record<string, SpecDef> }
export interface Segment { segment: number; entry: string; started_utc: string | null; ended_utc: string | null; end_state: string | null; stop_reason: string | null }
export interface Answer {
  run_dir: string; run_id: string | null; mode: string | null; mock: boolean | null;
  state?: string | null; worker_alive?: boolean;      // since record 7.200: whether a compared run still works (older backends: absent)
  flushes: { served: number; total: number; start: number };
  final: Chunk; tail: Chunk | null; tail_complete: boolean; latest_seq: number;
  tail_page?: { start: string | null; cursor: string | null; reset: boolean; more: boolean };
  objective: { metric: string; direction: 'min' | 'max' } | null;
  learner: { recorded: boolean; every: number; reason: string | null };
  segments: Segment[];
}

/** Phases (storage/tables.py PHASES) by what they are for the charts. Training: designs proposed while the run learns
 *  or searches (random warm-up, the SAC policy, AI proposals). Evaluation: a policy evaluated without learning (a frozen
 *  run). Episode start: the reset design an episode begins from - no action, no reward. */
export type Category = 'training' | 'evaluation' | 'start';
const CATEGORY_OF: Record<string, Category> = {
  warmup: 'training', search: 'training', adapt: 'training', llm_warmup: 'training', llm_search: 'training', llm_rescue: 'training',
  frozen_eval: 'evaluation', validation: 'evaluation', baseline: 'start', episode_reset: 'start', preflight: 'start',
};
export const categoryOf = (phase: string | undefined): Category => CATEGORY_OF[phase ?? ''] ?? 'training';
export const CATEGORY_LABEL: Record<Category, string> = { training: 'Training', evaluation: 'Evaluation', start: 'Episode start' };
/** What the page knows of the run beyond its tables. `calibration`: a Baseline simulation, which also calibrates (records 7.197
 *  and 7.202, GET /api/runs/status `calibration`): its random designs are recorded as phase warmup, but nothing learns from them. */
export interface Context { calibration?: boolean }
const CALIBRATION_LABEL = 'Calibration (random designs)';
const labelOf = (category: Category, context: Context) => (context.calibration && category === 'training' ? CALIBRATION_LABEL : CATEGORY_LABEL[category]);
/** Statuses that are a verdict on the DESIGN (connection.classify_infrastructure_failure: not an infrastructure failure).
 *  A timeout, a lost link, a cancelled or interrupted evaluation says nothing about the design: no pass, no fail - a gap. */
export const DESIGN_STATUSES = ['ok', 'invalid_design', 'nonconverged', 'measurement_error'];

export let EVALUATION_CAP = 50000;
export let UPDATE_CAP = 200000;
/** Lower caps for a browser check of the thinning (localStorage 'gator-workbench-training-caps-v1'); never above the defaults. */
export function setCaps(caps: { evaluations?: number; updates?: number }) {
  if (caps.evaluations && caps.evaluations >= 64) EVALUATION_CAP = Math.min(caps.evaluations, 50000);
  if (caps.updates && caps.updates >= 64) UPDATE_CAP = Math.min(caps.updates, 200000);
}

/** A table of numeric columns that grows by doubling. NaN = null. */
export class Table {
  n = 0;
  cap: number;
  cols: Record<string, Float64Array> = {};
  constructor(names: string[], cap = 256) {
    this.cap = cap;
    for (const name of names) this.cols[name] = new Float64Array(cap).fill(NaN);
  }
  has(name: string) { return name in this.cols; }
  add(name: string) { if (!(name in this.cols)) this.cols[name] = new Float64Array(this.cap).fill(NaN); return this.cols[name]; }
  reserve(extra: number) {
    if (this.n + extra <= this.cap) return;
    let cap = this.cap;
    while (cap < this.n + extra) cap *= 2;
    for (const name of Object.keys(this.cols)) {
      const grown = new Float64Array(cap).fill(NaN);
      grown.set(this.cols[name].subarray(0, this.n));
      this.cols[name] = grown;
    }
    this.cap = cap;
  }
  /** Back to `n` rows: the cells after it are cleared, as if never written. */
  truncate(n: number) {
    if (n >= this.n) return;
    for (const column of Object.values(this.cols)) column.fill(NaN, n, this.n);
    this.n = n;
  }
  /** Keep only the given rows (ascending), in order. */
  keep(rows: number[]) {
    for (const column of Object.values(this.cols)) {
      rows.forEach((row, i) => { column[i] = column[row]; });
      column.fill(NaN, rows.length, this.n);
    }
    this.n = rows.length;
  }
  shrink() {
    if (this.cap <= Math.max(256, this.n * 2)) return;
    this.cap = Math.max(256, 2 ** Math.ceil(Math.log2(Math.max(1, this.n))));
    for (const name of Object.keys(this.cols)) this.cols[name] = this.cols[name].slice(0, this.cap);
  }
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);
const flag = (v: unknown): number => (v === true ? 1 : v === false ? 0 : NaN);

/** Words the backend sends once per answer ({values, codes}) as store-wide numbers, so that two answers agree. */
class Words {
  list: string[] = [];
  private index = new Map<string, number>();
  code(word: string) { let c = this.index.get(word); if (c === undefined) { c = this.list.length; this.list.push(word); this.index.set(word, c); } return c; }
  decode(column: unknown, n: number): number[] {
    const coded = column as Coded | undefined;
    if (!coded || !Array.isArray(coded.codes)) return new Array(n).fill(NaN);
    const own = coded.values.map(word => this.code(word));
    return coded.codes.map(c => (c < 0 ? NaN : own[c]));
  }
  compact(columns: { values: Float64Array; n: number }[]) {
    const old = this.list, remap = new Map<number, number>();
    this.list = []; this.index.clear();
    for (const { values, n } of columns) for (let i = 0; i < n; i++) {
      const code = values[i];
      if (!Number.isFinite(code) || code < 0) continue;
      if (!remap.has(code)) remap.set(code, this.code(old[code]));
      values[i] = remap.get(code)!;
    }
  }
}

const EVALUATION_NUMBERS: [string, string][] = [['seq', 'commit_seq'], ['index', 'completion_index'], ['envStep', 'global_env_step'],
  ['episodeStep', 'episode_step'], ['policy', 'policy_version'], ['reward', 'reward'], ['violation', 'normalized_constraint_violation'],
  ['margin', 'clearance_margin'], ['bestViolation', 'best_so_far_violation'], ['bestObjective', 'best_so_far_objective'],
  ['seconds', 'execution_seconds'], ['t', 'committed_at']];
const EVALUATION_FLAGS: [string, string][] = [['valid', 'valid'], ['feasible', 'all_hard_constraints_satisfied'], ['bestFeasible', 'best_so_far_feasible']];
const EVALUATION_WORDS: [string, string][] = [['episode', 'episode_id'], ['phase', 'phase'], ['source', 'action_source'], ['status', 'status']];
export const UPDATE_NUMBERS: [string, string][] = [['cum', 'cumulative_updates'], ['collected', 'evaluations_collected'], ['actorLoss', 'actor_loss'],
  ['criticLoss', 'critic_loss'], ['alphaLoss', 'alpha_loss'], ['alpha', 'alpha'], ['logp', 'mean_log_prob'], ['target', 'target_mean'],
  ['gradCritic', 'critic_grad_norm'], ['gradActor', 'actor_grad_norm'], ['t', 'updated_at']];
const NO_SPEC_ROW = -2;        // specWhy: the evaluation has no row for this spec (an interrupted or cancelled evaluation)
// Columns that say WHICH row it is, not a value: thinning keeps them as they are and looks for extremes elsewhere.
const IDENTITY_COLUMNS = new Set(['k', 'seq', 'index', 'envStep', 'episodeStep', 'policy', 'collected', 't', 'cum', 'episode', 'phase',
  'source', 'status', 'valid', 'bestFeasible']);

export class TrainingStore {
  runDir: string;
  flushes = 0;                 // flush records held (the cursor of the next read)
  total = 0;                   // flush records the run had at the last read
  finalEvaluations = 0;        // rows before the provisional tail
  finalUpdates = 0;
  thinnedEvaluations = 0;      // rows [0, this) of a table were thinned (memory bound)
  thinnedUpdates = 0;
  updatesReceived = 0;         // final learner-update rows received, thinned or not
  evaluationsReceived = 0;
  tailCursor: string | null = null;
  private tailEvaluationsReceived = 0;
  private tailUpdatesReceived = 0;
  evaluations: Table;
  updates: Table;
  words = { episode: new Words(), phase: new Words(), source: new Words(), status: new Words(), updatePhase: new Words(), reason: new Words() };
  specNames: string[] = [];
  specDefs: Record<string, SpecDef> = {};
  objective: Answer['objective'] = null;
  learner: Answer['learner'] = { recorded: true, every: 1, reason: null };
  segments: Segment[] = [];
  mode: string | null = null;
  mock: boolean | null = null;
  tailComplete = true;
  latestSeq = 0;
  answers = 0;
  version = 0;                 // changes whenever a chart could draw something else
  private tailKey = '';

  constructor(runDir: string) {
    this.runDir = runDir;
    this.evaluations = new Table(['k', ...EVALUATION_NUMBERS.map(c => c[0]), ...EVALUATION_FLAGS.map(c => c[0]), ...EVALUATION_WORDS.map(c => c[0])]);
    this.updates = new Table([...UPDATE_NUMBERS.map(c => c[0]), 'phase']);
  }

  /** One answer of GET /api/runs/training. Returns whether anything a chart draws changed. An answer to another cursor than
   *  the one held (a late reply) is ignored. */
  apply(answer: Answer): boolean {
    if (answer.flushes.start !== this.flushes) return false;
    const page = answer.tail_page;
    if (page && page.start !== this.tailCursor) return false;
    const before = this.version;
    this.answers += 1;
    this.mode = answer.mode; this.mock = answer.mock; this.objective = answer.objective; this.learner = answer.learner;
    this.segments = answer.segments ?? [];
    const reset = !page || page.reset || answer.flushes.served !== this.flushes;
    if (reset) {
      this.evaluations.truncate(this.finalEvaluations);
      this.updates.truncate(this.finalUpdates);
      this.thinnedEvaluations = Math.min(this.thinnedEvaluations, this.finalEvaluations);
      this.thinnedUpdates = Math.min(this.thinnedUpdates, this.finalUpdates);
      this.tailEvaluationsReceived = this.tailUpdatesReceived = 0;
    }
    const added = this.append(answer.final, this.evaluationsReceived);
    this.evaluationsReceived += answer.final.evaluations.n;
    this.updatesReceived += answer.final.updates.n;
    if (reset) { this.finalEvaluations = this.evaluations.n; this.finalUpdates = this.updates.n; }
    this.flushes = answer.flushes.served; this.total = answer.flushes.total;
    let tailAdded = 0;
    if (answer.tail) {
      tailAdded = this.append(answer.tail, this.evaluationsReceived + this.tailEvaluationsReceived);
      this.tailEvaluationsReceived += answer.tail.evaluations.n;
      this.tailUpdatesReceived += answer.tail.updates.n;
    }
    this.tailCursor = page?.cursor ?? null;
    this.tailComplete = answer.tail_complete; this.latestSeq = answer.latest_seq;
    const tailKey = `${this.tailEvaluationsReceived}:${this.tailUpdatesReceived}:${answer.latest_seq}:${this.tailCursor}`;
    if (added || (page && tailAdded) || tailKey !== this.tailKey) this.version += 1;
    this.tailKey = tailKey;
    let thinned = false;
    while (this.evaluations.n > EVALUATION_CAP) { this.thin('evaluations'); thinned = true; }
    while (this.updates.n > UPDATE_CAP) { this.thin('updates'); thinned = true; }
    if (thinned) {
      this.version += 1;
      this.evaluations.shrink(); this.updates.shrink();
      for (const [own] of EVALUATION_WORDS) this.words[own as keyof TrainingStore['words']].compact([
        { values: this.evaluations.cols[own], n: this.evaluations.n }]);
      this.words.updatePhase.compact([{ values: this.updates.cols.phase, n: this.updates.n }]);
      this.words.reason.compact(this.specNames.map(name => ({ values: this.evaluations.cols[`specWhy:${name}`], n: this.evaluations.n })));
    }
    return this.version !== before;
  }

  private append(chunk: Chunk, k0: number): number {
    const e = chunk.evaluations, u = chunk.updates, s = chunk.specs;
    let added = 0;
    if (e && e.n > 0) {
      const table = this.evaluations, start = table.n;
      table.reserve(e.n);
      for (const [own, name] of EVALUATION_NUMBERS) { const values = (e[name] as unknown[]) ?? []; const column = table.cols[own]; for (let i = 0; i < e.n; i++) column[start + i] = num(values[i]); }
      for (const [own, name] of EVALUATION_FLAGS) { const values = (e[name] as unknown[]) ?? []; const column = table.cols[own]; for (let i = 0; i < e.n; i++) column[start + i] = flag(values[i]); }
      for (const [own, name] of EVALUATION_WORDS) { const codes = this.words[own as keyof TrainingStore['words']].decode(e[name], e.n); const column = table.cols[own]; for (let i = 0; i < e.n; i++) column[start + i] = codes[i]; }
      for (let i = 0; i < e.n; i++) table.cols.k[start + i] = k0 + i + 1;
      for (const name of this.specNames) table.cols[`specWhy:${name}`].fill(NO_SPEC_ROW, start, start + e.n);
      table.n = start + e.n;
      added += e.n;
    }
    if (s && s.n > 0) {
      const table = this.evaluations;
      const rowOf = new Map<number, number>();
      const seq = table.cols.seq;
      for (let i = 0; i < table.n; i++) rowOf.set(seq[i], i);
      const names = this.words.reason;          // reasons share the store's word list
      const metric = (s.metric_name as Coded), values = s.raw_value as unknown[], satisfied = s.satisfied as unknown[], seqs = s.commit_seq as unknown[];
      const reasons = names.decode(s.failure_reason, s.n);
      for (let i = 0; i < s.n; i++) {
        const name = metric.values[metric.codes[i]];
        if (name === undefined) continue;
        const row = rowOf.get(seqs[i] as number);
        if (row === undefined) continue;
        if (!this.specNames.includes(name)) this.addSpec(name);
        table.cols[`spec:${name}`][row] = num(values[i]);
        table.cols[`specOk:${name}`][row] = flag(satisfied[i]);
        table.cols[`specWhy:${name}`][row] = Number.isFinite(reasons[i]) ? reasons[i] : NaN;
      }
      added += s.n;
    }
    for (const [name, def] of Object.entries(chunk.spec_defs ?? {})) this.specDefs[name] = def;
    if (u && u.n > 0) {
      const table = this.updates, start = table.n;
      table.reserve(u.n);
      for (const [own, name] of UPDATE_NUMBERS) { const values = (u[name] as unknown[]) ?? []; const column = table.cols[own]; for (let i = 0; i < u.n; i++) column[start + i] = num(values[i]); }
      const phases = this.words.updatePhase.decode(u.update_phase, u.n);
      for (let i = 0; i < u.n; i++) table.cols.phase[start + i] = phases[i];
      table.n = start + u.n;
      added += u.n;
    }
    return added;
  }

  /** A spec first seen now: its columns, "no row" in every evaluation until its rows say otherwise. */
  private addSpec(name: string) {
    this.specNames.push(name);
    const t = this.evaluations;
    t.add(`spec:${name}`); t.add(`specOk:${name}`);
    t.add(`specWhy:${name}`).fill(NO_SPEC_ROW, 0, t.n);
  }

  /** The memory bound (see the top of the file): the oldest half of all rows, including the live tail, thinned to each
   *  value column's extremes and first gap per bin (and each bin's first and last row). */
  private thin(which: 'evaluations' | 'updates') {
    const table = which === 'evaluations' ? this.evaluations : this.updates;
    const finalN = which === 'evaluations' ? this.finalEvaluations : this.finalUpdates;
    const half = Math.floor(table.n / 2);
    const value = Object.keys(table.cols).filter(c => !IDENTITY_COLUMNS.has(c) && !c.startsWith('specWhy:') && !c.startsWith('specOk:'));
    const width = Math.max(128, 16 * value.length);
    const kept: number[] = [];
    for (let b = 0; b < half; b += width) {
      const end = Math.min(half, b + width), rows = new Set<number>([b, end - 1]);
      for (const name of value) {
        const column = table.cols[name];
        let lo = -1, hi = -1, gap = -1;
        for (let i = b; i < end; i++) {
          const v = column[i];
          if (Number.isNaN(v)) { if (gap < 0) gap = i; continue; }
          if (lo < 0 || v < column[lo]) lo = i;
          if (hi < 0 || v > column[hi]) hi = i;
        }
        if (lo >= 0) { rows.add(lo); rows.add(hi); }
        if (gap >= 0) rows.add(gap);
      }
      kept.push(...[...rows].sort((a, c) => a - c));
    }
    // With more independent spec extremes than row slots, retaining all of them is impossible. Still make progress.
    if (kept.length >= half) kept.splice(0, kept.length, ...kept.filter((_, i) => i % 2 === 0 || i === kept.length - 1));
    for (let i = half; i < table.n; i++) kept.push(i);
    const previous = which === 'evaluations' ? this.thinnedEvaluations : this.thinnedUpdates;
    const stretch = kept.filter(row => row < Math.max(half, previous)).length;
    const finalKept = kept.filter(row => row < finalN).length;
    table.keep(kept);
    if (which === 'evaluations') { this.finalEvaluations = finalKept; this.thinnedEvaluations = stretch; }
    else { this.finalUpdates = finalKept; this.thinnedUpdates = stretch; }
  }

  /** How many evaluations and learner updates the run has recorded so far (thinning for the memory bound keeps fewer rows). */
  counts() {
    return { evaluations: this.evaluationsReceived + this.tailEvaluationsReceived, updates: this.updatesReceived + this.tailUpdatesReceived };
  }

  /** When the newest number was recorded (seconds since 1970), or null. */
  lastTime(): number | null {
    let latest = NaN;
    const scan = (table: Table) => { for (let i = table.n - 1; i >= Math.max(0, table.n - 64); i--) if (!(table.cols.t[i] <= latest)) latest = table.cols.t[i]; };
    scan(this.evaluations); scan(this.updates);
    return Number.isFinite(latest) ? latest : null;
  }
}

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
 *  nor resets the window). At a gap the mean is a gap too, so a missing value stays visible on the smoothed line. */
export function smooth(values: (number | null | undefined)[], window: number): (number | null | undefined)[] {
  const out: (number | null | undefined)[] = new Array(values.length);
  const ring: number[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v === undefined) { out[i] = undefined; continue; }
    if (v === null) { out[i] = null; continue; }
    ring.push(v); sum += v;
    if (ring.length > window) sum -= ring.shift()!;
    out[i] = sum / ring.length;
  }
  return out;
}

/** As `smooth`, but the window is the last `width` units of a sorted x instead of a number of values: learner updates by
 *  evaluation are averaged over the updates of the last `width` evaluations, however many updates an evaluation had (record
 *  7.213). A row is in the window of every later row up to `width` x units on, and of the rows at its own x after it. */
export function smoothOver(x: ArrayLike<number>, values: (number | null | undefined)[], width: number): (number | null | undefined)[] {
  const out: (number | null | undefined)[] = new Array(values.length);
  let lo = 0, sum = 0, count = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (typeof v === 'number') { sum += v; count += 1; }
    while (x[lo] <= x[i] - width) { const w = values[lo]; if (typeof w === 'number') { sum -= w; count -= 1; } lo++; }
    out[i] = v === undefined ? undefined : v === null ? null : sum / count;
  }
  return out;
}

/** Which rows to draw so that `buckets` pixel columns show the data faithfully: in every pixel column the first and the
 *  last row and, for every series, its first and last value, its smallest and largest value and its first gap. Every row
 *  kept is a recorded row with all its values; spikes and gaps survive. Below 3 rows per pixel column everything is kept. */
export function decimate(x: ArrayLike<number>, series: (number | null | undefined)[][], from: number, to: number, xMin: number, xMax: number, buckets: number): number[] {
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
    const rows = new Set<number>([i, end - 1]);
    for (const values of series) {
      let first = -1, last = -1, lo = -1, hi = -1, gap = -1;
      for (let r = i; r < end; r++) {
        const v = values[r];
        if (v === undefined) continue;
        if (first < 0) first = r;
        last = r;
        if (v === null) { if (gap < 0) gap = r; continue; }
        if (lo < 0 || v < (values[lo] as number)) lo = r;
        if (hi < 0 || v > (values[hi] as number)) hi = r;
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

// ---------------------------------------------------------------------------------------------------------------- charts
export type Axis = 'evaluation' | 'update';
export interface ChartSpec {
  id: string; title: string; unit: string; axis: Axis;
  group: 'Results' | 'Specs' | 'Learner (SAC)' | 'Not recorded';
  available: boolean; reason: string | null;    // why this run cannot draw it
  source: string;                               // the recorded column(s), by the data dictionary's names
  about: string;                                // what it is, in one sentence
}
export interface Series { label: string; role: 'raw' | 'smooth' | 'line' | 'limit' | 'superseded'; category: Category | null; values: (number | null | undefined)[]; step?: boolean;
  run?: number;            // compared runs (record 7.200): the run's place in the comparison, which picks its colour
  dash?: boolean }         // the second of two columns of one run (gradient norms: the policy's)
export interface Marker { x: number; label: string; kind: 'resume' | 'restart' }
export interface Built { axis: Axis; x: number[]; rows: number[]; series: Series[]; markers: Marker[]; thinnedTo: number | null; extent: [number, number] | null;
  range: [number, number] | null; unit: string;
  missing?: { label: string; reason: string }[] }     // compared runs that cannot be drawn on this chart, and why

const EVALUATION_TEXT = 'No evaluation is recorded yet.';
const anyValue = (table: Table, column: string, keep?: (row: number) => boolean) => {
  const c = table.cols[column];
  if (!c) return false;
  for (let i = 0; i < table.n; i++) if (!Number.isNaN(c[i]) && (!keep || keep(i))) return true;
  return false;
};

/** The pass flag of each evaluation: 1 = every hard spec met (all_hard_constraints_satisfied), 0 = not, NaN = no verdict on the
 *  design (DESIGN_STATUSES). */
export function passFlags(store: TrainingStore): Float64Array {
  const t = store.evaluations, out = new Float64Array(t.n).fill(NaN);
  const design = new Set(store.words.status.list.map((w, i) => (DESIGN_STATUSES.includes(w) ? i : -1)).filter(i => i >= 0));
  for (let i = 0; i < t.n; i++) if (design.has(t.cols.status[i]) && !Number.isNaN(t.cols.feasible[i])) out[i] = t.cols.feasible[i];
  return out;
}

export function rowCategories(store: TrainingStore): Category[] {
  const t = store.evaluations, phases = store.words.phase.list;
  return Array.from({ length: t.n }, (_, i) => categoryOf(phases[t.cols.phase[i]]));
}

const LEARNER: [string, string, string, string, string][] = [   // id, title, unit, source, about
  ['actor_loss', 'Actor loss', '', 'learner_updates.actor_loss', 'The policy\'s loss at each learner update.'],
  ['critic_loss', 'Critic loss', '', 'learner_updates.critic_loss', 'The twin critics\' loss at each learner update.'],
  ['alpha', 'Temperature α', '', 'learner_updates.alpha', 'The entropy coefficient: how much the learner is paid to keep exploring.'],
  ['entropy', 'Entropy estimate', 'nats', 'learner_updates.mean_log_prob', 'The policy\'s entropy estimate, −mean_log_prob (the data dictionary\'s definition): high = actions spread out, low = the policy has settled.'],
  ['alpha_loss', 'Temperature loss', '', 'learner_updates.alpha_loss', 'The loss that adjusts α towards the target entropy.'],
  ['target_mean', 'Mean TD target', '', 'learner_updates.target_mean', 'The mean temporal-difference target of the batch the critics learned from.'],
  ['grad_norm', 'Gradient norms before clipping', '', 'learner_updates.critic_grad_norm, actor_grad_norm', 'How hard each update pushed the critics and the policy (the clip is the "max grad norm" setting).'],
];
const LEARNER_COLUMNS: Record<string, [string, string][]> = {      // chart id -> [table column, series label]
  actor_loss: [['actorLoss', 'Actor loss']], critic_loss: [['criticLoss', 'Critic loss']], alpha: [['alpha', 'α']],
  entropy: [['logp', 'Entropy estimate']], alpha_loss: [['alphaLoss', 'Temperature loss']], target_mean: [['target', 'Mean TD target']],
  grad_norm: [['gradCritic', 'Critics'], ['gradActor', 'Policy']],
};

/** Every chart the tab offers for this run, the ones it cannot draw with the reason. */
export function catalog(store: TrainingStore, context: Context = {}): ChartSpec[] {
  const e = store.evaluations, u = store.updates;
  const empty = e.n === 0 ? EVALUATION_TEXT : null;
  const charts: ChartSpec[] = [];
  const categories = rowCategories(store);
  const pass = passFlags(store);
  const evaluated = categories.some(c => c === 'evaluation');
  charts.push({ id: 'reward', title: 'Step reward', unit: '', axis: 'evaluation', group: 'Results', source: 'evaluations.reward',
    about: 'The learning reward of each evaluation (one environment step); 0 is the best a design can score before the bonuses. The run records no episode return.',
    available: anyValue(e, 'reward'), reason: empty ?? 'No evaluation has a reward yet: a reset or a failed evaluation has none.' });
  charts.push({ id: 'pass', title: 'Meets every hard spec', unit: 'share', axis: 'evaluation', group: 'Results',
    source: 'evaluations.all_hard_constraints_satisfied, status',
    about: 'Each design: 1 = every hard spec met, 0 = not; the smoothed line is the share of the last designs that did. A timeout, a lost link or an interrupted evaluation is no verdict on the design: a gap.',
    available: pass.some(v => !Number.isNaN(v)), reason: empty ?? 'No evaluation has a verdict on its design yet.' });
  charts.push({ id: 'eval_pass', title: 'Evaluation success rate', unit: 'share', axis: 'evaluation', group: evaluated ? 'Results' : 'Not recorded',
    source: 'evaluations.all_hard_constraints_satisfied (phase frozen_eval or validation)',
    about: 'Designs of a policy evaluated without training (a frozen run): the share of them so far that met every hard spec.',
    available: evaluated && categories.some((c, i) => c === 'evaluation' && !Number.isNaN(pass[i])),
    reason: evaluated ? 'No evaluated design has a verdict yet.' : 'This run evaluated no policy apart from training: only a frozen run does. For training designs see "Meets every hard spec".' });
  charts.push({ id: 'episode_return', title: 'Episode return', unit: '', axis: 'evaluation', group: 'Not recorded', source: '-',
    about: 'The sum of an episode\'s rewards.', available: false,
    reason: 'Not recorded: the run records the reward of each evaluation, not of whole episodes. See "Step reward".' });
  charts.push({ id: 'violation', title: 'Worst spec miss', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.normalized_constraint_violation',
    about: 'How far each design misses its worst hard spec, divided by that spec\'s scale; 0 = every hard spec met.',
    available: anyValue(e, 'violation'), reason: empty ?? 'No valid design yet: a failed evaluation has no value.' });
  charts.push({ id: 'margin', title: 'Tightest margin', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.clearance_margin',
    about: 'The signed margin of the binding hard spec: above 0 = met with room to spare, below 0 = missed.',
    available: anyValue(e, 'margin'), reason: empty ?? 'This run records no margin (an older run, or no valid design yet).' });
  charts.push({ id: 'best', title: 'Best design so far: worst spec miss', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.best_so_far_violation',
    about: 'The worst-spec miss of the design the run keeps as its best at each evaluation; it reaches 0 at the first design that meets every hard spec.',
    available: anyValue(e, 'bestViolation'), reason: empty ?? 'No valid design yet.' });
  const objective = store.objective, objectiveUnit = objective ? store.specDefs[objective.metric]?.unit ?? '' : '';
  charts.push({ id: 'objective', title: objective ? `Best feasible ${objective.metric} (${objective.direction === 'min' ? 'lower' : 'higher'} is better)` : 'Best feasible objective',
    unit: objectiveUnit, axis: 'evaluation', group: objective ? 'Results' : 'Not recorded', source: 'evaluations.best_so_far_metrics, best_so_far_feasible',
    about: 'The objective\'s value of the best design that meets every hard spec, as the run keeps it (feasible first, then the objective).',
    available: !!objective && anyValue(e, 'bestObjective', row => e.cols.bestFeasible[row] === 1),
    reason: !objective ? 'No objective: no Specs row of this run says "then lower/higher is better".' : empty ?? 'No design has met every hard spec yet.' });
  for (const name of store.specNames) {
    const def = store.specDefs[name];
    const limits = [def?.threshold_lower != null ? `≥ ${def.threshold_lower}` : '', def?.threshold_upper != null ? `≤ ${def.threshold_upper}` : ''].filter(Boolean).join(', ');
    charts.push({ id: `spec:${name}`, title: name, unit: def?.unit ?? '', axis: 'evaluation', group: 'Specs', source: `metrics (aggregate row of ${name})`,
      about: `The value of this spec's equation at each evaluation${limits ? `, against its limit (${limits}, ${def?.hard ? 'hard' : 'soft'})` : ''}.`,
      available: anyValue(e, `spec:${name}`), reason: 'No evaluation has a value for this spec yet.' });
  }
  charts.push({ id: 'seconds', title: 'Simulation time per evaluation', unit: 's', axis: 'evaluation', group: 'Results', source: 'evaluations.execution_seconds',
    about: 'From the start of an evaluation to its result, every attempt included.', available: anyValue(e, 'seconds'), reason: empty });
  const learner = store.learner;
  for (const [id, title, unit, source, about] of LEARNER) {
    const columns = LEARNER_COLUMNS[id];
    const has = learner.recorded && !context.calibration && columns.some(([c]) => anyValue(u, c));
    charts.push({ id, title, unit, axis: 'update', group: 'Learner (SAC)', source, about, available: has,
      reason: context.calibration ? 'A baseline run with calibration learns nothing: its random designs only suggest each Specs row\'s scale and a starting temperature.'
        : learner.reason ?? (u.n === 0 ? 'No learner update yet: they begin once the warm-up designs fill a training batch.' : 'This run recorded no value of it.') });
  }
  return charts;
}

/** Where the run continued after a pause or a crash: the first row recorded at or after each later segment's start. */
function resumeMarkers(store: TrainingStore, table: Table, xColumn: string): Marker[] {
  const markers: Marker[] = [];
  for (const segment of store.segments.slice(1)) {
    const start = segment.started_utc ? Date.parse(segment.started_utc) / 1000 : NaN;
    if (!Number.isFinite(start)) continue;
    for (let i = 0; i < table.n; i++) {
      if (table.cols.t[i] >= start) { markers.push({ x: table.cols[xColumn][i], label: `continued (segment ${segment.segment})`, kind: 'resume' }); break; }
    }
  }
  return markers;
}

/** What part of the x axis a chart shows. all: the whole run, growing with it. follow: the newest `width` x units, sliding as
 *  results arrive ("Follow latest" after a zoom). fixed: what the user zoomed to; new results do not move it. */
export type View = { mode: 'all' } | { mode: 'follow'; width: number } | { mode: 'fixed'; min: number; max: number };

/** What an evaluation chart takes from one run: each row's value (NaN = a gap), the categories it draws, and how: `single` = one
 *  stepped line over every row (the best design so far), `cumulative` = the share so far instead of a mean. */
function evaluationValues(store: TrainingStore, id: string) {
  const t = store.evaluations, n = t.n;
  const value = new Float64Array(n).fill(NaN);
  let allowed: Category[] = ['training', 'evaluation', 'start'], single: string | null = null, cumulative = false;
  const copy = (column: string, sign = 1) => { const c = t.cols[column]; if (c) for (let i = 0; i < n; i++) value[i] = sign * c[i]; };
  if (id === 'reward') { copy('reward'); allowed = ['training', 'evaluation']; }
  else if (id === 'pass') { value.set(passFlags(store)); allowed = ['training', 'evaluation']; }
  else if (id === 'eval_pass') { value.set(passFlags(store)); allowed = ['evaluation']; cumulative = true; }
  else if (id === 'violation') copy('violation');
  else if (id === 'margin') copy('margin');
  else if (id === 'seconds') copy('seconds');
  else if (id === 'best') { copy('bestViolation'); single = 'Best design so far'; }
  else if (id === 'objective') {
    copy('bestObjective');
    for (let i = 0; i < n; i++) if (t.cols.bestFeasible[i] !== 1) value[i] = NaN;
    single = 'Best feasible design so far';
  }
  else if (id.startsWith('spec:')) copy(id);
  return { value, allowed, single, cumulative };
}

/** What a learner chart's x is: the learner's update count, or the number of evaluations collected when the update ran
 *  (learner_updates.evaluations_collected, record 7.213) - the evaluation charts' x, on which runs that learn 1 and 8
 *  times per evaluation line up. Several updates after one evaluation share its x there. */
export type LearnerX = 'update' | 'evaluation';
const noCount = (learnerX: LearnerX) => (learnerX === 'evaluation' ? 'it records no evaluation count with its learner updates' : 'it records no update count');

/** One chart's data: rows in view (plus one beyond each edge), thinned to `buckets` pixel columns by `decimate`. */
export function build(store: TrainingStore, id: string, smoothing: number, view: View, buckets: number, context: Context = {}, learnerX: LearnerX = 'update'): Built {
  const spec = catalog(store, context).find(c => c.id === id);
  const unit = spec?.unit ?? '';
  if (spec?.axis === 'update') return buildUpdates(store, id, smoothing, view, buckets, unit, learnerX);
  const t = store.evaluations, n = t.n, k = t.cols.k;
  const categories = rowCategories(store);
  const { value, allowed, single, cumulative } = evaluationValues(store, id);
  const series: Series[] = [];
  // Over a thinned stretch (memory bound) only its extremes are left: no mean is drawn there, and the mean starts after it.
  const full = store.thinnedEvaluations;
  const meanOf = (raw: (number | null | undefined)[], over: (v: (number | null | undefined)[]) => (number | null | undefined)[]) =>
    full ? [...new Array(full).fill(undefined), ...over(raw.slice(full))] : over(raw);
  if (single) {
    series.push({ label: single, role: 'line', category: null, step: true, values: Array.from(value, v => (Number.isNaN(v) ? null : v)) });
  } else {
    for (const category of allowed) {
      if (!categories.some(c => c === category)) continue;
      const raw: (number | null | undefined)[] = categories.map((c, i) => (c !== category ? undefined : Number.isNaN(value[i]) ? null : value[i]));
      if (!raw.some(v => v !== undefined)) continue;
      const label = labelOf(category, context);
      if (cumulative) {
        const share = meanOf(raw, part => { let passed = 0, judged = 0; return part.map(v => (v === undefined ? undefined : v === null ? null : (judged += 1, passed += v, passed / judged))); });
        series.push({ label: `${label} (each design)`, role: 'raw', category, values: raw });
        series.push({ label: full ? `${label}: share since evaluation ${k[full]}` : `${label}: share so far`, role: 'smooth', category, values: share });
      } else if (smoothing > 0 && category !== 'start') {     // an episode start re-simulates one design: no mean of it
        series.push({ label: `${label} (recorded)`, role: 'raw', category, values: raw });
        series.push({ label: `${label}: mean of last ${smoothing}`, role: 'smooth', category, values: meanOf(raw, part => smooth(part, smoothing)) });
      } else series.push({ label, role: 'raw', category, values: raw });
    }
  }
  if (id.startsWith('spec:')) {
    const def = store.specDefs[id.slice(5)];
    for (const [bound, label] of [[def?.threshold_lower, 'lower limit'], [def?.threshold_upper, 'upper limit']] as [number | null | undefined, string][]) {
      if (bound != null && Number.isFinite(bound)) series.push({ label, role: 'limit', category: null, values: new Array(n).fill(bound) });
    }
  }
  const extent: [number, number] | null = n ? [k[0], k[n - 1]] : null;
  const markers = resumeMarkers(store, t, 'k');
  const thinnedTo = store.thinnedEvaluations > 0 ? k[store.thinnedEvaluations - 1] : null;
  return cut(Array.from(k.subarray(0, n)), Array.from({ length: n }, (_, i) => i), series, extent, view, buckets, markers, thinnedTo, 'evaluation', unit);
}

/** The rows of the learner's table in the order of a learner chart's x: by update count or by evaluations collected (rows
 *  without that count left out), stable - at a repeated x the earlier row first (an abandoned update before the update that
 *  replaced it). */
function learnerOrder(t: Table, learnerX: LearnerX, keep?: (row: number) => boolean): { rows: number[]; x: number[]; column: string } {
  const column = learnerX === 'evaluation' ? 'collected' : 'cum', xs = t.cols[column];
  const rows: number[] = [];
  let sorted = true;
  for (let i = 0; i < t.n; i++) {
    if (Number.isNaN(xs[i]) || (keep && !keep(i))) continue;
    if (rows.length && xs[i] < xs[rows[rows.length - 1]]) sorted = false;
    rows.push(i);
  }
  if (!sorted) rows.sort((a, b) => xs[a] - xs[b] || a - b);
  return { rows, x: rows.map(i => xs[i]), column };
}

/** The smoothed learner line: over the last `smoothing` updates, or by evaluation over the updates of the last `smoothing`
 *  evaluations; from `from` on (the rows of a thinned stretch have no mean). */
function learnerMean(x: number[], values: (number | null | undefined)[], smoothing: number, learnerX: LearnerX, from: number) {
  const over = (part: (number | null | undefined)[]) => (learnerX === 'evaluation' ? smoothOver(x.slice(from), part, smoothing) : smooth(part, smoothing));
  return from > 0 ? [...new Array(from).fill(undefined), ...over(values.slice(from))] : over(values);
}
const meanLabel = (smoothing: number, learnerX: LearnerX) => `mean of last ${smoothing}${learnerX === 'evaluation' ? ' evaluations' : ''}`;

function buildUpdates(store: TrainingStore, id: string, smoothing: number, view: View, buckets: number, unit: string, learnerX: LearnerX): Built {
  const t = store.updates;
  const { superseded, restarts, restartRows } = updateBranches(t);
  const { rows: order, x, column } = learnerOrder(t, learnerX);
  const series: Series[] = [];
  for (const [col, label] of LEARNER_COLUMNS[id] ?? []) {
    const c = t.cols[col], sign = id === 'entropy' ? -1 : 1;
    const at = (i: number) => (Number.isNaN(c[i]) ? null : sign * c[i]);
    const main = order.map(i => (superseded[i] ? undefined : at(i)));
    if (smoothing > 0) {
      const thinned = store.thinnedUpdates, from = thinned ? Math.max(0, order.findIndex(i => i >= thinned)) : 0;     // the mean starts after a thinned stretch
      series.push({ label: `${label} (recorded)`, role: 'raw', category: null, values: main });
      series.push({ label: `${label}: ${meanLabel(smoothing, learnerX)}`, role: 'smooth', category: null, values: learnerMean(x, main, smoothing, learnerX, from) });
    } else series.push({ label, role: 'raw', category: null, values: main });
    if (restarts.length) series.push({ label: `${label}: abandoned at a restart`, role: 'superseded', category: null, values: order.map(i => (superseded[i] ? at(i) : undefined)) });
  }
  const restartX = learnerX === 'evaluation' ? restartRows.map(j => t.cols.collected[j]).filter(v => !Number.isNaN(v)) : restarts;
  const markers = [...resumeMarkers(store, t, column), ...restartX.map(v => ({ x: v, label: 'learner restarted from its save point', kind: 'restart' as const }))];
  const extent: [number, number] | null = x.length ? [x[0], x[x.length - 1]] : null;
  const thinnedTo = store.thinnedUpdates > 0 ? t.cols[column][store.thinnedUpdates - 1] : null;
  const made = cut(x, order, series, extent, view, buckets, markers, Number.isNaN(thinnedTo) ? null : thinnedTo, 'update', unit);
  return t.n && !x.length ? { ...made, missing: [{ label: 'this run', reason: noCount(learnerX) }] } : made;
}

/** The x range a view shows on this extent: a single point gets one unit on each side, so it is drawn. */
export function viewRange(view: View, extent: [number, number]): [number, number] {
  const [first, last] = extent;
  const [min, max] = view.mode === 'fixed' ? [view.min, view.max] : view.mode === 'follow' ? [Math.max(first, last - view.width), last] : [first, last];
  return max > min ? [min, max] : [min - 1, max + 1];
}

function cut(x: number[], rows: number[], series: Series[], extent: [number, number] | null, view: View, buckets: number,
  markers: Marker[], thinnedTo: number | null, axis: Axis, unit: string): Built {
  if (!extent) return { axis, x: [], rows: [], series, markers, thinnedTo, extent, range: null, unit };
  const [min, max] = viewRange(view, extent);
  const [from, to] = visibleRows(x, x.length, min, max);
  const keep = decimate(x, series.map(s => s.values), from, to, min, max, Math.max(16, Math.floor(buckets)));
  return { axis, x: keep.map(i => x[i]), rows: keep.map(i => rows[i]), unit, markers, thinnedTo, extent, range: [min, max],
    series: series.map(s => ({ ...s, values: keep.map(i => s.values[i]) })) };
}

// ------------------------------------------------------------------------------------------------- several runs on one chart
/** A run on a comparison chart (record 7.200): its store, the name the chart gives it, what the page knows of it. */
export interface CompareRun { store: TrainingStore; label: string; context?: Context }
export const COMPARE_MAX = 4;

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
  const parts: { x: number[]; series: Series[] }[] = [];
  runs.forEach((run, r) => {
    const own = catalog(run.store, run.context ?? {}).find(c => c.id === id);
    if (!own?.available) { missing.push({ label: run.label, reason: own?.reason ?? 'this run has no such chart' }); return; }
    if (own.unit !== unit) { missing.push({ label: run.label, reason: `its ${own.title} is in ${own.unit || 'no unit'}, not in ${unit || 'no unit'}` }); return; }
    const part = axis === 'update' ? learnerPart(run, r, id, smoothing, learnerX) : evaluationPart(run, r, id, smoothing);
    if (!part.x.length && axis === 'update') { missing.push({ label: run.label, reason: noCount(learnerX) }); return; }
    parts.push(part);
  });
  // One x column for all runs: each x value as many times as the run that has it most often (by evaluation, a run that learns
  // 8 times per evaluation has 8 updates at one x), so the runs share the slots of an x and each keeps its own rows in order.
  const need = new Map<number, number>();
  for (const part of parts) {
    const own = new Map<number, number>();
    for (const v of part.x) own.set(v, (own.get(v) ?? 0) + 1);
    for (const [v, count] of own) if (count > (need.get(v) ?? 0)) need.set(v, count);
  }
  const x: number[] = [], firstSlot = new Map<number, number>();
  for (const v of [...need.keys()].sort((a, b) => a - b)) { firstSlot.set(v, x.length); for (let j = 0; j < need.get(v)!; j++) x.push(v); }
  const series: Series[] = [];
  for (const part of parts) {
    const used = new Map<number, number>();
    const slot = part.x.map(v => { const j = used.get(v) ?? 0; used.set(v, j + 1); return firstSlot.get(v)! + j; });
    for (const s of part.series) {
      const values: (number | null | undefined)[] = new Array(x.length).fill(undefined);
      slot.forEach((to, i) => { values[to] = s.values[i]; });
      series.push({ ...s, values });
    }
  }
  if (id.startsWith('spec:')) {
    const def = first.store.specDefs[id.slice(5)];
    for (const [bound, label] of [[def?.threshold_lower, 'lower limit'], [def?.threshold_upper, 'upper limit']] as [number | null | undefined, string][]) {
      if (bound != null && Number.isFinite(bound)) series.push({ label: `${label} (${first.label})`, role: 'limit', category: null, values: new Array(x.length).fill(bound) });
    }
  }
  const extent: [number, number] | null = x.length ? [x[0], x[x.length - 1]] : null;
  return { ...cut(x, x.map(() => -1), series, extent, view, buckets, [], null, axis, unit), missing };
}

/** One run's series of an evaluation chart in a comparison: its rows of the chart's categories but episode starts. */
function evaluationPart(run: CompareRun, r: number, id: string, smoothing: number): { x: number[]; series: Series[] } {
  const { store, label } = run, t = store.evaluations, k = t.cols.k;
  const { value, allowed, single, cumulative } = evaluationValues(store, id);
  const categories = rowCategories(store);
  const x: number[] = [], raw: (number | null)[] = [];
  let full = 0;                                      // rows of a thinned stretch among the kept ones: no mean over them
  for (let i = 0; i < t.n; i++) {
    if (!single && (categories[i] === 'start' || !allowed.includes(categories[i]))) continue;
    x.push(k[i]); raw.push(Number.isNaN(value[i]) ? null : value[i]);
    if (i < store.thinnedEvaluations) full += 1;
  }
  const after = (over: (v: (number | null | undefined)[]) => (number | null | undefined)[]) => (full ? [...new Array(full).fill(undefined), ...over(raw.slice(full))] : over(raw));
  if (single) return { x, series: [{ label, role: 'line', category: null, run: r, step: true, values: raw }] };
  if (cumulative) return { x, series: [{ label: `${label} (each design)`, role: 'raw', category: null, run: r, values: raw },
    { label: `${label}: share so far`, role: 'smooth', category: null, run: r, values: after(part => { let passed = 0, judged = 0; return part.map(v => (v == null ? v : (judged += 1, passed += v, passed / judged))); }) }] };
  if (smoothing > 0) return { x, series: [{ label: `${label} (recorded)`, role: 'raw', category: null, run: r, values: raw },
    { label: `${label}: mean of last ${smoothing}`, role: 'smooth', category: null, run: r, values: after(part => smooth(part, smoothing)) }] };
  return { x, series: [{ label, role: 'raw', category: null, run: r, values: raw }] };
}

/** One run's series of a learner chart in a comparison: its updates on the line it went on (abandoned ones left out). */
function learnerPart(run: CompareRun, r: number, id: string, smoothing: number, learnerX: LearnerX): { x: number[]; series: Series[] } {
  const { store, label } = run, t = store.updates;
  const { superseded } = updateBranches(t);
  const { rows, x } = learnerOrder(t, learnerX, i => !superseded[i]);
  const from = store.thinnedUpdates ? Math.max(0, rows.findIndex(i => i >= store.thinnedUpdates)) : 0;
  const columns = LEARNER_COLUMNS[id] ?? [];
  const series: Series[] = [];
  columns.forEach(([column, name], c) => {
    const values = rows.map(i => (Number.isNaN(t.cols[column][i]) ? null : (id === 'entropy' ? -1 : 1) * t.cols[column][i]));
    const named = columns.length > 1 ? `${label} / ${name}` : label;      // the run's name stays whole in its legend key
    if (smoothing > 0) {
      series.push({ label: `${named} (recorded)`, role: 'raw', category: null, run: r, dash: c > 0, values });
      series.push({ label: `${named}: ${meanLabel(smoothing, learnerX)}`, role: 'smooth', category: null, run: r, dash: c > 0,
        values: learnerMean(x, values, smoothing, learnerX, from) });
    } else series.push({ label: named, role: 'raw', category: null, run: r, dash: c > 0, values });
  });
  return { x, series };
}

// ------------------------------------------------------------------------------------------------------ a run's key numbers
/** The line of numbers the Training tab writes for each run on its charts (record 7.215, the user's choice "Key numbers in
 *  the tab"), all read from the recorded rows - nothing estimated, and episode starts left out as on the charts. null: the
 *  run has no such number (yet). With a thinned history (memory bound) the first passing design is the first one kept. */
export interface KeyNumbers {
  evaluations: number;                                       // recorded evaluations, as the head counts them
  firstPass: number | null;                                  // the evaluation number of the first design meeting every hard spec
  recent: { passed: number; judged: number; from: number; to: number } | null;   // designs of the last RECENT evaluations with a verdict
  bestMiss: number | null;                                   // the best design so far: its worst-spec miss at the newest evaluation
  entropy: [number, number] | null;                          // the entropy estimate: mean of the updates of the first and of the last ENDS evaluations
  alpha: [number, number] | null;                            // the temperature α, the same way
}
export const RECENT = 100, ENDS = 50;

export function keyNumbers(store: TrainingStore, context: Context = {}): KeyNumbers {
  const t = store.evaluations, k = t.cols.k, n = t.n;
  const categories = rowCategories(store), pass = passFlags(store);
  let firstPass: number | null = null, recent: KeyNumbers['recent'] = null, bestMiss: number | null = null;
  for (let i = 0; i < n && firstPass === null; i++) if (categories[i] !== 'start' && pass[i] === 1) firstPass = k[i];
  if (n) {
    const to = k[n - 1], from = Math.max(k[0], to - RECENT + 1);
    let passed = 0, judged = 0;
    for (let i = n - 1; i >= 0 && k[i] >= from; i--) if (categories[i] !== 'start' && !Number.isNaN(pass[i])) { judged += 1; passed += pass[i]; }
    recent = { passed, judged, from, to };
  }
  for (let i = n - 1; i >= 0 && bestMiss === null; i--) if (!Number.isNaN(t.cols.bestViolation[i])) bestMiss = t.cols.bestViolation[i];
  let entropy: [number, number] | null = null, alpha: [number, number] | null = null;
  const u = store.updates;
  if (!context.calibration && store.learner.recorded && u.n) {
    const { superseded } = updateBranches(u);
    const { rows, x } = learnerOrder(u, 'evaluation', i => !superseded[i]);
    if (rows.length) {
      const first = x[0], last = x[x.length - 1];
      const mean = (column: string, sign: number, lo: number, hi: number) => {
        let sum = 0, count = 0;
        rows.forEach((row, j) => { const v = u.cols[column][row]; if (x[j] >= lo && x[j] <= hi && !Number.isNaN(v)) { sum += sign * v; count += 1; } });
        return count ? sum / count : NaN;
      };
      const ends = (column: string, sign: number): [number, number] | null => {
        const a = mean(column, sign, first, first + ENDS - 1), b = mean(column, sign, last - ENDS + 1, last);
        return Number.isNaN(a) || Number.isNaN(b) ? null : [a, b];
      };
      entropy = ends('logp', -1); alpha = ends('alpha', 1);
    }
  }
  return { evaluations: store.counts().evaluations, firstPass, recent, bestMiss, entropy, alpha };
}
