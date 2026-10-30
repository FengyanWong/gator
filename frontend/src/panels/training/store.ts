/** trainingData.ts, part 1 (plan-refactoring C12): what GET /api/runs/training answers, the categories of a phase, and how a
 *  run's rows are kept - Changes, Table and TrainingStore with its memory bound (see the top of trainingData.ts). */

export type Coded = { values: string[]; codes: number[] };
export type Columns = { n: number; [name: string]: unknown };
export interface SpecDef { unit: string | null; threshold_lower: number | null; threshold_upper: number | null; hard: boolean | null }
export interface Chunk { evaluations: Columns; updates: Columns; specs: Columns; spec_defs: Record<string, SpecDef> }
export interface Segment {
  segment: number; entry: string; started_utc: string | null; ended_utc: string | null; end_state: string | null; stop_reason: string | null
}
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
export const labelOf = (category: Category, context: Context) =>
  (context.calibration && category === 'training' ? CALIBRATION_LABEL : CATEGORY_LABEL[category]);
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
    for (let change = this.rows.length - missed; change < this.rows.length; change++) if (this.rows[change] < row) row = this.rows[change];
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
      rows.forEach((row, place) => { column[place] = column[row]; });
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

const num = (value: unknown): number => (typeof value === 'number' && Number.isFinite(value) ? value : NaN);
const flag = (value: unknown): number => (value === true ? 1 : value === false ? 0 : NaN);

/** Words the backend sends once per answer ({values, codes}) as store-wide numbers, so that two answers agree. */
class Words {
  list: string[] = [];
  private index = new Map<string, number>();
  code(word: string) {
    let code = this.index.get(word);
    if (code === undefined) { code = this.list.length; this.list.push(word); this.index.set(word, code); }
    return code;
  }
  decode(column: unknown, n: number): number[] {
    const coded = column as Coded | undefined;
    if (!coded || !Array.isArray(coded.codes)) return new Array(n).fill(NaN);
    const own = coded.values.map(word => this.code(word));
    return coded.codes.map(code => (code < 0 ? NaN : own[code]));
  }
  compact(columns: { values: Float64Array; n: number }[]) {
    const old = this.list, remap = new Map<number, number>();
    this.list = []; this.index.clear();
    for (const { values, n } of columns) for (let row = 0; row < n; row++) {
      const code = values[row];
      if (!Number.isFinite(code) || code < 0) continue;
      if (!remap.has(code)) remap.set(code, this.code(old[code]));
      values[row] = remap.get(code)!;
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

/** The rows of a table's oldest half, [0, half), that thinning keeps, in order: in each bin of rows its first and last row and
 *  the rows of each value column's extremes and first gap - every other one of them when they would not make the half smaller. */
function rowsToKeep(table: Table, half: number): number[] {
  const valueColumns = Object.keys(table.cols).filter(name => !IDENTITY_COLUMNS.has(name) && !name.startsWith('specWhy:') && !name.startsWith('specOk:'));
  const width = Math.max(128, 16 * valueColumns.length);
  const kept: number[] = [];
  for (let start = 0; start < half; start += width) {
    const end = Math.min(half, start + width), rows = new Set<number>([start, end - 1]);
    for (const name of valueColumns) addExtremes(table.cols[name], start, end, rows);
    kept.push(...[...rows].sort((first, second) => first - second));
  }
  // With more independent spec extremes than row slots, retaining all of them is impossible. Still make progress.
  if (kept.length >= half) kept.splice(0, kept.length, ...kept.filter((_, index) => index % 2 === 0 || index === kept.length - 1));
  return kept;
}

/** The rows of a column's lowest and highest value in the bin [start, end) and of its first gap (NaN), added to `rows`. */
function addExtremes(column: Float64Array, start: number, end: number, rows: Set<number>) {
  let lo = -1, hi = -1, gap = -1;
  for (let row = start; row < end; row++) {
    const value = column[row];
    if (Number.isNaN(value)) { if (gap < 0) gap = row; continue; }
    if (lo < 0 || value < column[lo]) lo = row;
    if (hi < 0 || value > column[hi]) hi = row;
  }
  if (lo >= 0) { rows.add(lo); rows.add(hi); }
  if (gap >= 0) rows.add(gap);
}

/** One run's rows as the Training tab keeps them: the evaluations and learner updates read so far - the final rows its
 *  flushes published, then the journal's provisional tail - with the words and specs they use, within the memory bound. */
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
    this.evaluations = new Table(['k', ...EVALUATION_NUMBERS.map(pair => pair[0]), ...EVALUATION_FLAGS.map(pair => pair[0]),
      ...EVALUATION_WORDS.map(pair => pair[0])]);
    this.updates = new Table([...UPDATE_NUMBERS.map(pair => pair[0]), 'phase']);
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
    if (reset) this.cutTail();
    const added = this.appendFinal(answer.final, reset);
    this.flushes = answer.flushes.served; this.total = answer.flushes.total;
    const tailAdded = this.appendTail(answer.tail);
    this.tailCursor = page?.cursor ?? null;
    this.tailComplete = answer.tail_complete; this.latestSeq = answer.latest_seq;
    const tailKey = `${this.tailEvaluationsReceived}:${this.tailUpdatesReceived}:${answer.latest_seq}:${this.tailCursor}`;
    if (added || (page && tailAdded) || tailKey !== this.tailKey) this.version += 1;
    this.tailKey = tailKey;
    this.keepMemoryBound();
    return this.version !== before;
  }

  /** A reset (a new flush, or the journal read from its start again): the tables go back to their final rows - the
   *  provisional rows of the tail cut off, the thinned stretch no longer than the final rows - and the tail is counted anew. */
  private cutTail() {
    this.evaluations.truncate(this.finalEvaluations);
    this.updates.truncate(this.finalUpdates);
    this.thinnedEvaluations = Math.min(this.thinnedEvaluations, this.finalEvaluations);
    this.thinnedUpdates = Math.min(this.thinnedUpdates, this.finalUpdates);
    this.tailEvaluationsReceived = this.tailUpdatesReceived = 0;
  }

  /** The answer's final rows (what its flushes published), appended and counted as received; after a reset the final rows
   *  end with them. Returns what `append` returns. */
  private appendFinal(chunk: Chunk, reset: boolean): number {
    const added = this.append(chunk, this.evaluationsReceived);
    this.evaluationsReceived += chunk.evaluations.n;
    this.updatesReceived += chunk.updates.n;
    if (reset) { this.finalEvaluations = this.evaluations.n; this.finalUpdates = this.updates.n; }
    return added;
  }

  /** The answer's journal tail, if it has one, appended (its evaluations numbered after every one received) and counted as
   *  the tail's. Returns what `append` returns, 0 without a tail. */
  private appendTail(chunk: Chunk | null): number {
    let tailAdded = 0;
    if (chunk) {
      tailAdded = this.append(chunk, this.evaluationsReceived + this.tailEvaluationsReceived);
      this.tailEvaluationsReceived += chunk.evaluations.n;
      this.tailUpdatesReceived += chunk.updates.n;
    }
    return tailAdded;
  }

  /** Each table over its cap thinned until it is within it; after thinning the charts draw again, the tables give back the
   *  memory they no longer use and the word lists keep only the words the rows kept still use. */
  private keepMemoryBound() {
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
  }

  /** A chunk of an answer, appended: its evaluations (numbered from k0 + 1 on), its spec values on the evaluations they
   *  belong to (rows held before it too), its spec definitions and its learner updates. Returns how many rows and values came. */
  private append(chunk: Chunk, k0: number): number {
    const evaluations = chunk.evaluations, updates = chunk.updates, specs = chunk.specs;
    const fresh = this.evaluations.n;          // rows from here on are this chunk's: a spec value for an earlier row changes it
    let added = 0;
    if (evaluations && evaluations.n > 0) { this.appendEvaluations(evaluations, k0); added += evaluations.n; }
    if (specs && specs.n > 0) { this.joinSpecValues(specs, fresh); added += specs.n; }
    for (const [name, def] of Object.entries(chunk.spec_defs ?? {})) this.specDefs[name] = def;
    if (updates && updates.n > 0) { this.appendUpdates(updates); added += updates.n; }
    return added;
  }

  /** The chunk's evaluation rows after the table's last: its numbers, flags and words, `k` from k0 + 1 on, and "no row" for
   *  every spec until a spec value comes. */
  private appendEvaluations(evaluations: Columns, k0: number) {
    const table = this.evaluations, start = table.n;
    table.reserve(evaluations.n);
    for (const [own, name] of EVALUATION_NUMBERS) {
      const values = (evaluations[name] as unknown[]) ?? [];
      const column = table.cols[own];
      for (let row = 0; row < evaluations.n; row++) column[start + row] = num(values[row]);
    }
    for (const [own, name] of EVALUATION_FLAGS) {
      const values = (evaluations[name] as unknown[]) ?? [];
      const column = table.cols[own];
      for (let row = 0; row < evaluations.n; row++) column[start + row] = flag(values[row]);
    }
    for (const [own, name] of EVALUATION_WORDS) {
      const codes = this.words[own as keyof TrainingStore['words']].decode(evaluations[name], evaluations.n);
      const column = table.cols[own];
      for (let row = 0; row < evaluations.n; row++) column[start + row] = codes[row];
    }
    for (let row = 0; row < evaluations.n; row++) table.cols.k[start + row] = k0 + row + 1;
    for (const name of this.specNames) table.cols[`specWhy:${name}`].fill(NO_SPEC_ROW, start, start + evaluations.n);
    table.n = start + evaluations.n;
  }

  /** The chunk's spec values, each on the evaluation row of its commit_seq (one without a spec name or a row held is left out;
   *  a spec first seen gets its columns). The lowest row held before the chunk (below `fresh`) that one changed is noted. */
  private joinSpecValues(specs: Columns, fresh: number) {
    const table = this.evaluations;
    const rowOf = new Map<number, number>();
    const seq = table.cols.seq;
    for (let row = 0; row < table.n; row++) rowOf.set(seq[row], row);
    const reasonWords = this.words.reason;          // reasons share the store's word list
    const metric = (specs.metric_name as Coded), values = specs.raw_value as unknown[], satisfied = specs.satisfied as unknown[],
      seqs = specs.commit_seq as unknown[];
    const reasons = reasonWords.decode(specs.failure_reason, specs.n);
    let rewritten = Infinity;
    for (let specRow = 0; specRow < specs.n; specRow++) {
      const name = metric.values[metric.codes[specRow]];
      if (name === undefined) continue;
      const row = rowOf.get(seqs[specRow] as number);
      if (row === undefined) continue;
      if (!this.specNames.includes(name)) this.addSpec(name);
      table.cols[`spec:${name}`][row] = num(values[specRow]);
      table.cols[`specOk:${name}`][row] = flag(satisfied[specRow]);
      table.cols[`specWhy:${name}`][row] = Number.isFinite(reasons[specRow]) ? reasons[specRow] : NaN;
      if (row < fresh && row < rewritten) rewritten = row;
    }
    if (rewritten < Infinity) this.specChanges.note(rewritten);
  }

  /** A spec first seen now: its columns, "no row" in every evaluation until its rows say otherwise. */
  private addSpec(name: string) {
    this.specNames.push(name);
    const table = this.evaluations;
    table.add(`spec:${name}`); table.add(`specOk:${name}`);
    table.add(`specWhy:${name}`).fill(NO_SPEC_ROW, 0, table.n);
  }

  /** The chunk's learner-update rows after the table's last: its numbers, and its phase as a word. */
  private appendUpdates(updates: Columns) {
    const table = this.updates, start = table.n;
    table.reserve(updates.n);
    for (const [own, name] of UPDATE_NUMBERS) {
      const values = (updates[name] as unknown[]) ?? [];
      const column = table.cols[own];
      for (let row = 0; row < updates.n; row++) column[start + row] = num(values[row]);
    }
    const phases = this.words.updatePhase.decode(updates.update_phase, updates.n);
    for (let row = 0; row < updates.n; row++) table.cols.phase[start + row] = phases[row];
    table.n = start + updates.n;
  }

  /** The memory bound (see the top of trainingData.ts): the oldest half of all rows, including the live tail, thinned to each
   *  value column's extremes and first gap per bin (and each bin's first and last row). */
  private thin(which: 'evaluations' | 'updates') {
    const table = which === 'evaluations' ? this.evaluations : this.updates;
    const finalN = which === 'evaluations' ? this.finalEvaluations : this.finalUpdates;
    const half = Math.floor(table.n / 2);
    const kept = rowsToKeep(table, half);
    for (let row = half; row < table.n; row++) kept.push(row);
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
    const scan = (table: Table) => {
      for (let row = table.n - 1; row >= Math.max(0, table.n - 64); row--) if (!(table.cols.t[row] <= latest)) latest = table.cols.t[row];
    };
    scan(this.evaluations); scan(this.updates);
    return Number.isFinite(latest) ? latest : null;
  }
}
