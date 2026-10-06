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
 *  says when it thins history; the run's tables keep every row.
 *
 *  What the charts derive from the rows (record 7.221, performance plan A: each run's categories, pass flags, learner
 *  restarts, the rows in the order of a chart's x, running means) is worked out once per run and brought up to date as
 *  rows arrive, then shared by all its charts and its key numbers; a chart takes only the rows in view. The values drawn
 *  are the same numbers as before: see "shared chart preparation" below. */

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

/** Where the rows of a table changed other than by growing at the end (record 7.221): a new flush cuts the provisional rows
 *  off, thinning rewrites them all, a spec value joins an evaluation of an earlier page. Each change notes the first row
 *  that may differ, so that what was derived from the rows before it can be kept. A reader keeps the `stamp` it derived
 *  at; `since(stamp)` is then the first row to derive again (Infinity: none). The last 64 changes are kept: a reader
 *  that missed more starts again from row 0. */
export class Changes {
  stamp = 0;
  private rows: number[] = [];
  note(row: number) { this.stamp += 1; this.rows.push(row); if (this.rows.length > 64) this.rows.shift(); }
  since(seen: number): number {
    const missed = this.stamp - seen;
    if (missed <= 0) return Infinity;
    if (missed > this.rows.length) return 0;
    let row = Infinity;
    for (let i = this.rows.length - missed; i < this.rows.length; i++) if (this.rows[i] < row) row = this.rows[i];
    return row;
  }
}

/** A table of numeric columns that grows by doubling. NaN = null. Rows only grow at the end, apart from the changes
 *  `changes` notes: a cut of the provisional rows (truncate) and thinning (keep). */
export class Table {
  n = 0;
  cap: number;
  cols: Record<string, Float64Array> = {};
  changes = new Changes();
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
    this.changes.note(n);
  }
  /** Keep only the given rows (ascending), in order. */
  keep(rows: number[]) {
    for (const column of Object.values(this.cols)) {
      rows.forEach((row, i) => { column[i] = column[row]; });
      column.fill(NaN, rows.length, this.n);
    }
    this.n = rows.length;
    this.changes.note(0);
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
  specChanges = new Changes();     // evaluation rows a spec value joined after they were added (a bundle split over pages)
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
    const fresh = this.evaluations.n;          // rows from here on are this chunk's: a spec value for an earlier row changes it
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
      let rewritten = Infinity;
      for (let i = 0; i < s.n; i++) {
        const name = metric.values[metric.codes[i]];
        if (name === undefined) continue;
        const row = rowOf.get(seqs[i] as number);
        if (row === undefined) continue;
        if (!this.specNames.includes(name)) this.addSpec(name);
        table.cols[`spec:${name}`][row] = num(values[i]);
        table.cols[`specOk:${name}`][row] = flag(satisfied[i]);
        table.cols[`specWhy:${name}`][row] = Number.isFinite(reasons[i]) ? reasons[i] : NaN;
        if (row < fresh && row < rewritten) rewritten = row;
      }
      if (rewritten < Infinity) this.specChanges.note(rewritten);
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

/** Values of a series at a stretch of positions without a JS value per point (record 7.221): kind 0 = undefined (a row of
 *  another category, an abandoned update: nothing drawn there), 1 = null (a gap), 2 = the number in `nums`. */
interface Typed { kinds: Uint8Array; nums: Float64Array }
const typed = (n: number): Typed => ({ kinds: new Uint8Array(n), nums: new Float64Array(n) });
const boxed = (values: Typed, i: number) => (values.kinds[i] === 0 ? undefined : values.kinds[i] === 1 ? null : values.nums[i]);

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
function decimateTyped(x: ArrayLike<number>, series: Typed[], from: number, to: number, xMin: number, xMax: number, buckets: number): number[] {
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

/** The codes of this store's statuses that are a verdict on the design (DESIGN_STATUSES). */
const designCodes = (store: TrainingStore) => new Set(store.words.status.list.map((w, i) => (DESIGN_STATUSES.includes(w) ? i : -1)).filter(i => i >= 0));
/** The pass flag of each evaluation: 1 = every hard spec met (all_hard_constraints_satisfied), 0 = not, NaN = no verdict on the
 *  design (DESIGN_STATUSES). */
export function passFlags(store: TrainingStore): Float64Array {
  const t = store.evaluations, out = new Float64Array(t.n).fill(NaN);
  const design = designCodes(store);
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
 * builders before this record and a store kept up to date with one that derives everything at once. */
const TRAINING = 0, EVALUATION = 1, START = 2;                 // the categories by number
const CODE: Record<Category, number> = { training: TRAINING, evaluation: EVALUATION, start: START };
let SPACING = 4096;            // positions between two checkpoints of a running mean
/** Closer checkpoints, for training_data_check.mjs: small fixtures then pass many of them. The values are the same at any
 *  spacing; a running mean keeps the spacing it was made with. */
export function setSpacing(positions: number) { if (positions >= 1) SPACING = Math.floor(positions); }
const MEANS = 48;              // running means kept per run (one per chart and category or column): the least recently used go
type Fill = (from: number, to: number) => Typed;              // a series' values at positions [from, to)

/** The first of the first `n` entries of an ascending array that is at least `v` (n if none). */
function lowerBound(a: ArrayLike<number>, n: number, v: number): number {
  let lo = 0, hi = n;
  while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < v) lo = m + 1; else hi = m; }
  return lo;
}
/** The first that is above `v` (n if none). */
function upperBound(a: ArrayLike<number>, n: number, v: number): number {
  let lo = 0, hi = n;
  while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] <= v) lo = m + 1; else hi = m; }
  return lo;
}

/** The rows a chart draws in the order of its x - a learner chart's (learnerOrder of record 7.213), a compared run's
 *  evaluations (7.200) - kept as rows arrive: position p holds row rowAt(p) at x x()[p]. While every row so far is drawn,
 *  in its own order, a position is its row and x the table's own column, so nothing is copied. A row whose x is below the
 *  rows before it (a learner restart by update count) sorts them all: by x, at a repeated x the earlier row first. */
class Index {
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
    this.memberSeen = members.map(c => c.stamp); this.valueSeen = values.map(c => c.stamp);
  }
  x(): ArrayLike<number> { return this.own ? this.own.xs : this.table.cols[this.column]; }
  rowAt(p: number): number { return this.own ? this.own.rows[p] : p; }
  bytes() { return this.own ? this.own.rows.byteLength + this.own.xs.byteLength : 0; }
  /** How many positions hold a row before `row`. */
  before(row: number): number {
    if (!this.own) return Math.min(row, this.len);
    if (this.ascending) return lowerBound(this.own.rows, this.len, row);
    let count = 0;
    for (let p = 0; p < this.len; p++) if (this.own.rows[p] < row) count += 1;
    return count;
  }
  /** The first position holding `row` or a later row, -1 if none (as Array.findIndex finds it). */
  find(row: number): number {
    if (this.ascending) { const p = this.before(row); return p < this.len ? p : -1; }
    for (let p = 0; p < this.len; p++) if (this.rowAt(p) >= row) return p;
    return -1;
  }
  sync(): this {
    const n = this.table.n;
    let back = n;
    this.members.forEach((c, i) => { back = Math.min(back, c.since(this.memberSeen[i])); this.memberSeen[i] = c.stamp; });
    if (back < this.scanned) {
      if (this.ascending && back > 0) { this.len = this.before(back); this.scanned = back; this.changes.note(this.len); }
      else { this.len = 0; this.scanned = 0; this.own = null; this.ascending = true; this.changes.note(0); }     // all again, no copy kept
    }
    let changed = Infinity;
    this.values.forEach((c, i) => { changed = Math.min(changed, c.since(this.valueSeen[i])); this.valueSeen[i] = c.stamp; });
    if (changed < Infinity) this.changes.note(this.ascending ? this.before(changed) : 0);
    if (this.scanned < n) this.extend(n);
    return this;
  }
  private extend(n: number) {
    const xs = this.table.cols[this.column];
    let last = this.len ? this.x()[this.len - 1] : 0;
    for (let row = this.scanned; row < n; row++) {
      const v = xs[row];
      if (Number.isNaN(v) || (this.drawn && !this.drawn(row))) { if (!this.own) this.copy(this.len); continue; }
      if (this.len && v < last) { this.sort(n); return; }
      if (this.own) {
        if (this.len === this.own.rows.length) this.copy(Math.max(256, 2 * this.len));
        this.own.rows[this.len] = row; this.own.xs[this.len] = v;
      }
      this.len += 1; last = v;
    }
    this.scanned = n;
  }
  /** Rows and x of their own (room for `cap` positions), from here on. */
  private copy(cap: number) {
    const rows = new Int32Array(cap), xs = new Float64Array(cap);
    if (this.own) { rows.set(this.own.rows.subarray(0, this.len)); xs.set(this.own.xs.subarray(0, this.len)); }
    else { for (let p = 0; p < this.len; p++) rows[p] = p; xs.set(this.table.cols[this.column].subarray(0, this.len)); }
    this.own = { rows, xs };
  }
  private sort(n: number) {
    const xs = this.table.cols[this.column], rows: number[] = [];
    for (let row = 0; row < n; row++) if (!Number.isNaN(xs[row]) && (!this.drawn || this.drawn(row))) rows.push(row);
    rows.sort((a, b) => xs[a] - xs[b] || a - b);
    this.own = { rows: Int32Array.from(rows), xs: Float64Array.from(rows, row => xs[row]) };
    this.len = rows.length; this.scanned = n;
    this.ascending = rows.every((row, i) => i === 0 || row > rows[i - 1]);
    this.changes.note(0);
  }
}

type MeanKind = 'last' | 'over' | 'share';      // smooth (the last N values), smoothOver (the last N x units), the share so far
/** A running mean before position `pos`: the sum and count of its values; `lo` its first position (over); `ring` its values
 *  from `head` on, the oldest first (last). */
interface State { pos: number; sum: number; count: number; lo: number; ring: Float64Array | null; head: number }
const copyState = (s: State): State => ({ ...s, ring: s.ring && s.ring.slice() });

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
    this.points = [{ pos: start, sum: 0, count: 0, lo: start, ring: kind === 'last' ? new Float64Array(window + 1) : null, head: 0 }];
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
      const recorded = kinds[pos - base], v = nums[pos - base];
      let mean = 0;
      if (kind === 'last') {                       // smooth: ring.push(v); sum += v; past the window sum -= ring.shift()
        if (recorded === 2) {
          const ring = state.ring!, size = window + 1;
          ring[(state.head + state.count) % size] = v; state.count += 1; state.sum += v;
          if (state.count > window) { state.sum -= ring[state.head]; state.head = (state.head + 1) % size; state.count -= 1; }
          mean = state.sum / state.count;
        }
      } else if (kind === 'share') {               // judged += 1, passed += v, passed / judged
        if (recorded === 2) { state.count += 1; state.sum += v; mean = state.sum / state.count; }
      } else {                                     // smoothOver: the value in, then out what is `window` x units behind
        if (recorded === 2) { state.sum += v; state.count += 1; }
        const limit = xs[pos] - window;
        while (state.lo < len && xs[state.lo] <= limit) {
          const i = state.lo - base, gone = i < kinds.length ? null : fill(state.lo, state.lo + 1);
          if ((gone ? gone.kinds[0] : kinds[i]) === 2) { state.sum -= gone ? gone.nums[0] : nums[i]; state.count -= 1; }
          state.lo += 1;
        }
        if (recorded === 2) mean = state.sum / state.count;
      }
      if (out && pos >= outFrom) { out.kinds[pos - outFrom] = recorded; out.nums[pos - outFrom] = mean; }
    }
    state.pos = to;
  }
}

/** What one run's charts and key numbers share (see above), kept per store and released with it. */
class Prep {
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

  /** Each evaluation's category and pass flag, brought up to date. */
  evaluations(): this {
    const t = this.store.evaluations, back = Math.min(t.changes.since(this.evaluationsSeen), t.n);
    this.evaluationsSeen = t.changes.stamp;
    if (back < this.evaluationsDone) {
      for (let i = back; i < this.evaluationsDone; i++) this.counts[this.cat[i]] -= 1;
      this.evaluationsDone = back;
    }
    if (this.evaluationsDone >= t.n) return this;
    if (this.cat.length < t.n || (this.evaluationsDone === 0 && this.cat.length > t.cap)) {     // grown, or smaller after thinning
      const cat = new Uint8Array(t.cap), pass = new Float64Array(t.cap);
      cat.set(this.cat.subarray(0, this.evaluationsDone)); pass.set(this.pass.subarray(0, this.evaluationsDone));
      this.cat = cat; this.pass = pass;
    }
    const phases = this.store.words.phase.list, design = designCodes(this.store), phase = t.cols.phase, status = t.cols.status, feasible = t.cols.feasible;
    for (let i = this.evaluationsDone; i < t.n; i++) {
      const c = CODE[categoryOf(phases[phase[i]])];
      this.cat[i] = c; this.counts[c] += 1;
      this.pass[i] = design.has(status[i]) && !Number.isNaN(feasible[i]) ? feasible[i] : NaN;
    }
    this.evaluationsDone = t.n;
    return this;
  }

  /** The learner's restarts and abandoned updates, brought up to date (updateBranches, row by row). A restart marks every
   *  earlier update at or above its count; a cut that takes a restart away clears what it marked: all is derived again. */
  updates(): this {
    const t = this.store.updates, cum = t.cols.cum, back = Math.min(t.changes.since(this.updatesSeen), t.n);
    this.updatesSeen = t.changes.stamp;
    if (back < this.updatesDone) {
      if (this.restartRows.length && this.restartRows[this.restartRows.length - 1] >= back) {
        this.superseded.fill(0); this.restarts = []; this.restartRows = []; this.updatesDone = 0; this.top = -Infinity;
        this.branches.note(0);
      } else {
        this.superseded.fill(0, back, this.updatesDone); this.updatesDone = back; this.top = -Infinity;
        for (let j = back - 1; j >= 0; j--) if (!Number.isNaN(cum[j])) { this.top = cum[j]; break; }
      }
    }
    if (this.updatesDone >= t.n) return this;
    if (this.superseded.length < t.n || (this.updatesDone === 0 && this.superseded.length > t.cap)) {
      const superseded = new Uint8Array(t.cap);
      superseded.set(this.superseded.subarray(0, this.updatesDone));
      this.superseded = superseded;
    }
    let flipped = Infinity;
    for (let j = this.updatesDone; j < t.n; j++) {
      const v = cum[j];
      if (Number.isNaN(v)) continue;
      if (v <= this.top) {
        this.restarts.push(v); this.restartRows.push(j);
        for (let i = 0; i < j; i++) if (cum[i] >= v && !this.superseded[i]) { this.superseded[i] = 1; if (i < flipped) flipped = i; }
      }
      this.top = v;
    }
    this.updatesDone = t.n;
    if (flipped < Infinity) this.branches.note(flipped);
    return this;
  }

  /** The rows of a learner chart in the order of its x (`learnerX`): every update with that count, or (`going`) only those
   *  of the line the learner went on - abandoned ones left out, as compared runs and the key numbers take them. */
  order(learnerX: LearnerX, going: boolean): Index {
    this.updates();
    const key = `order:${learnerX}:${going ? 'going' : 'all'}`, t = this.store.updates;
    let index = this.indexes.get(key);
    if (!index) this.indexes.set(key, index = new Index(key, t, learnerX === 'evaluation' ? 'collected' : 'cum', going ? row => !this.superseded[row] : null,
      going ? [t.changes, this.branches] : [t.changes], going ? [] : [this.branches]));
    return index.sync();
  }
  /** The evaluations of the categories `only` (codes; null: every evaluation), in their order (x = the evaluation number). */
  rows(only: number[] | null): Index {
    this.evaluations();
    const key = `rows:${only ? only.join(',') : 'all'}`, t = this.store.evaluations;
    let index = this.indexes.get(key);
    if (!index) this.indexes.set(key, index = new Index(key, t, 'k', only ? row => only.includes(this.cat[row]) : null, [t.changes], [this.store.specChanges]));
    return index.sync();
  }

  /** The first row of `table` for which `test` holds, -1 if none (whether a column has any value, the first passing design,
   *  the first row of a segment), kept as rows arrive; `deps`: the changes it depends on. */
  first(key: string, table: Table, deps: Changes[], test: (row: number) => boolean): number {
    let fact = this.facts.get(key);
    if (!fact) this.facts.set(key, fact = { row: -1, scanned: 0, seen: deps.map(c => c.stamp) });
    let back = table.n;
    deps.forEach((c, i) => { back = Math.min(back, c.since(fact!.seen[i])); fact!.seen[i] = c.stamp; });
    if (back < fact.scanned) { fact.scanned = back; if (fact.row >= back) fact.row = -1; }
    if (fact.row < 0) for (let i = fact.scanned; i < table.n; i++) if (test(i)) { fact.row = i; break; }
    fact.scanned = table.n;
    return fact.row;
  }
  /** Whether an evaluation column has a value in any row (a spec's values can also join earlier rows). */
  any(column: string): boolean {
    const t = this.store.evaluations, c = t.cols[column];
    return !!c && this.first(`any ${column}`, t, column.startsWith('spec:') ? [t.changes, this.store.specChanges] : [t.changes], row => !Number.isNaN(c[row])) >= 0;
  }
  /** Whether a column of the learner's updates has a value in any row. */
  anyUpdate(column: string): boolean {
    const t = this.store.updates, c = t.cols[column];
    return !!c && this.first(`any update ${column}`, t, [t.changes], row => !Number.isNaN(c[row])) >= 0;
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
function prep(store: TrainingStore): Prep {
  let p = PREPARED.get(store);
  if (!p) PREPARED.set(store, p = new Prep(store));
  return p;
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
function valuesFill(p: Prep, index: Index, value: (row: number) => number, only: number | null): Fill {
  return remembered((from, to) => {
    const out = typed(to - from), cat = p.cat;
    for (let pos = from; pos < to; pos++) {
      const row = index.rowAt(pos);
      if (only !== null && cat[row] !== only) continue;
      const v = value(row);
      if (Number.isNaN(v)) out.kinds[pos - from] = 1;
      else { out.kinds[pos - from] = 2; out.nums[pos - from] = v; }
    }
    return out;
  });
}
/** A learner chart's values at positions of `index`: the column times `sign`, NaN a gap; 'main' leaves the updates abandoned
 *  at a restart out (undefined), 'abandoned' has only those, 'all' every position. */
function learnerFill(p: Prep, index: Index, column: string, sign: number, which: 'main' | 'abandoned' | 'all'): Fill {
  return remembered((from, to) => {
    const out = typed(to - from), c = p.store.updates.cols[column], superseded = p.superseded;
    for (let pos = from; pos < to; pos++) {
      const row = index.rowAt(pos);
      if (which !== 'all' && (superseded[row] === 1) !== (which === 'abandoned')) continue;
      if (Number.isNaN(c[row])) out.kinds[pos - from] = 1;
      else { out.kinds[pos - from] = 2; out.nums[pos - from] = sign * c[row]; }
    }
    return out;
  });
}

/** Every chart the tab offers for this run, the ones it cannot draw with the reason. */
export function catalog(store: TrainingStore, context: Context = {}): ChartSpec[] {
  const e = store.evaluations, u = store.updates, p = prep(store).evaluations();
  const empty = e.n === 0 ? EVALUATION_TEXT : null;
  const charts: ChartSpec[] = [];
  const evaluated = p.counts[EVALUATION] > 0;
  charts.push({ id: 'reward', title: 'Step reward', unit: '', axis: 'evaluation', group: 'Results', source: 'evaluations.reward',
    about: 'The learning reward of each evaluation (one environment step); 0 is the best a design can score before the bonuses. The run records no episode return.',
    available: p.any('reward'), reason: empty ?? 'No evaluation has a reward yet: a reset or a failed evaluation has none.' });
  charts.push({ id: 'pass', title: 'Meets every hard spec', unit: 'share', axis: 'evaluation', group: 'Results',
    source: 'evaluations.all_hard_constraints_satisfied, status',
    about: 'Each design: 1 = every hard spec met, 0 = not; the smoothed line is the share of the last designs that did. A timeout, a lost link or an interrupted evaluation is no verdict on the design: a gap.',
    available: p.first('judged', e, [e.changes], row => !Number.isNaN(p.pass[row])) >= 0, reason: empty ?? 'No evaluation has a verdict on its design yet.' });
  charts.push({ id: 'eval_pass', title: 'Evaluation success rate', unit: 'share', axis: 'evaluation', group: evaluated ? 'Results' : 'Not recorded',
    source: 'evaluations.all_hard_constraints_satisfied (phase frozen_eval or validation)',
    about: 'Designs of a policy evaluated without training (a frozen run): the share of them so far that met every hard spec.',
    available: evaluated && p.first('evaluated and judged', e, [e.changes], row => p.cat[row] === EVALUATION && !Number.isNaN(p.pass[row])) >= 0,
    reason: evaluated ? 'No evaluated design has a verdict yet.' : 'This run evaluated no policy apart from training: only a frozen run does. For training designs see "Meets every hard spec".' });
  charts.push({ id: 'episode_return', title: 'Episode return', unit: '', axis: 'evaluation', group: 'Not recorded', source: '-',
    about: 'The sum of an episode\'s rewards.', available: false,
    reason: 'Not recorded: the run records the reward of each evaluation, not of whole episodes. See "Step reward".' });
  charts.push({ id: 'violation', title: 'Worst spec miss', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.normalized_constraint_violation',
    about: 'How far each design misses its worst hard spec, divided by that spec\'s scale; 0 = every hard spec met.',
    available: p.any('violation'), reason: empty ?? 'No valid design yet: a failed evaluation has no value.' });
  charts.push({ id: 'margin', title: 'Tightest margin', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.clearance_margin',
    about: 'The signed margin of the binding hard spec: above 0 = met with room to spare, below 0 = missed.',
    available: p.any('margin'), reason: empty ?? 'This run records no margin (an older run, or no valid design yet).' });
  charts.push({ id: 'best', title: 'Best design so far: worst spec miss', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.best_so_far_violation',
    about: 'The worst-spec miss of the design the run keeps as its best at each evaluation; it reaches 0 at the first design that meets every hard spec.',
    available: p.any('bestViolation'), reason: empty ?? 'No valid design yet.' });
  const objective = store.objective, objectiveUnit = objective ? store.specDefs[objective.metric]?.unit ?? '' : '';
  charts.push({ id: 'objective', title: objective ? `Best feasible ${objective.metric} (${objective.direction === 'min' ? 'lower' : 'higher'} is better)` : 'Best feasible objective',
    unit: objectiveUnit, axis: 'evaluation', group: objective ? 'Results' : 'Not recorded', source: 'evaluations.best_so_far_metrics, best_so_far_feasible',
    about: 'The objective\'s value of the best design that meets every hard spec, as the run keeps it (feasible first, then the objective).',
    available: !!objective && p.first('feasible objective', e, [e.changes], row => !Number.isNaN(e.cols.bestObjective[row]) && e.cols.bestFeasible[row] === 1) >= 0,
    reason: !objective ? 'No objective: no Specs row of this run says "then lower/higher is better".' : empty ?? 'No design has met every hard spec yet.' });
  for (const name of store.specNames) {
    const def = store.specDefs[name];
    const limits = [def?.threshold_lower != null ? `≥ ${def.threshold_lower}` : '', def?.threshold_upper != null ? `≤ ${def.threshold_upper}` : ''].filter(Boolean).join(', ');
    charts.push({ id: `spec:${name}`, title: name, unit: def?.unit ?? '', axis: 'evaluation', group: 'Specs', source: `metrics (aggregate row of ${name})`,
      about: `The value of this spec's equation at each evaluation${limits ? `, against its limit (${limits}, ${def?.hard ? 'hard' : 'soft'})` : ''}.`,
      available: p.any(`spec:${name}`), reason: 'No evaluation has a value for this spec yet.' });
  }
  charts.push({ id: 'seconds', title: 'Simulation time per evaluation', unit: 's', axis: 'evaluation', group: 'Results', source: 'evaluations.execution_seconds',
    about: 'From the start of an evaluation to its result, every attempt included.', available: p.any('seconds'), reason: empty });
  const learner = store.learner;
  for (const [id, title, unit, source, about] of LEARNER) {
    const columns = LEARNER_COLUMNS[id];
    const has = learner.recorded && !context.calibration && columns.some(([c]) => p.anyUpdate(c));
    charts.push({ id, title, unit, axis: 'update', group: 'Learner (SAC)', source, about, available: has,
      reason: context.calibration ? 'A baseline run with calibration learns nothing: its random designs only suggest each Specs row\'s scale and a starting temperature.'
        : learner.reason ?? (u.n === 0 ? 'No learner update yet: they begin once the warm-up designs fill a training batch.' : 'This run recorded no value of it.') });
  }
  return charts;
}

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
function evaluationValues(store: TrainingStore, p: Prep, id: string) {
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
const noCount = (learnerX: LearnerX) => (learnerX === 'evaluation' ? 'it records no evaluation count with its learner updates' : 'it records no update count');

/** A series before the rows in view are known: what it is (`meta`, whose values cut fills in) and where its values come
 *  from - `fill` at positions, or a limit's one value in every row. */
interface Lazy { meta: Series; fill: Fill | null; limit?: number }
/** A spec's limits, as constant dashed lines (a comparison's are its first run's). */
function limitSeries(store: TrainingStore, id: string, name: (label: string) => string): Lazy[] {
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

const meanLabel = (smoothing: number, learnerX: LearnerX) => `mean of last ${smoothing}${learnerX === 'evaluation' ? ' evaluations' : ''}`;

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
  const t = store.evaluations, k = t.cols.k, n = t.n, p = prep(store).evaluations(), cat = p.cat, pass = p.pass;
  let firstPass: number | null = null, recent: KeyNumbers['recent'] = null, bestMiss: number | null = null;
  const first = p.first('first passing design', t, [t.changes], row => p.cat[row] !== START && p.pass[row] === 1);
  if (first >= 0) firstPass = k[first];
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
  return { evaluations: store.counts().evaluations, firstPass, recent, bestMiss, entropy, alpha };
}
