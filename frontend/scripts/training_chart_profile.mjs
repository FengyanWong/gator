// Changed-frame profile of the Training tab's chart preparation (record 7.221, work package A): the work TrainingTab.tsx does
// for one new frame - the catalog, the key numbers of every run on the charts, and each chart's build / buildCompare - timed
// in node on synthetic MOCK stores (origin=synthetic, provenance=mock) fed through TrainingStore.apply as the backend's
// answers are. No browser: drawing (uPlot) is not included; the browser's share is measured by training_tab_check.mjs.
//
// A frame follows one live poll: a journal page with 2 new evaluations and their learner updates is appended ("append"),
// or a new flush replaces the provisional rows ("flush"). Sizes: 8,000 / 100,000 / 200,000 learner updates per run
// (8 per evaluation after the warm-up, every 5th evaluation an episode start: ~6.4 per evaluation), 1 or 4 runs, 1 or 8
// charts, views all / follow (newest 1,000 x units) / fixed (a zoom into the middle).
//
// Run (Windows node; --expose-gc for the memory figures, a large young generation so that one frame's allocation is seen whole):
//   "/mnt/c/Program Files/nodejs/node.exe" --expose-gc --max-semi-space-size=128 "$(wslpath -w frontend/scripts/training_chart_profile.mjs)" \
//       [--module <trainingData.ts to profile, default ../src/panels/trainingData.ts>] [--quick] [--json <file>]
// --module takes another copy of trainingData.ts (e.g. the one before 7.221: git show c170802:frontend/src/panels/trainingData.ts),
// so the same frames can be timed on the old and the new code (about 8 minutes for the old code, 2 for the new).
// --verify <another trainingData.ts> also feeds twin stores of that module the same answers and compares every frame's
// catalog, key numbers and charts with it, exactly (numbers by Object.is); a difference ends the run with exit code 1.
import { copyFileSync, cpSync, existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const option = (name, fallback = null) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : fallback; };
const modulePath = option('--module');
/** Another trainingData.ts, imported from a folder of its own (node reads the package.json beside a .ts file), which goes
 *  again once the module is loaded. The training/ folder beside it comes along: its parts, since plan-refactoring C12. */
async function load(file) {
  const dir = mkdtempSync(path.join(tmpdir(), 'gator-chart-profile-'));
  try {
    copyFileSync(file, path.join(dir, 'trainingData.ts'));
    const parts = path.join(path.dirname(file), 'training');
    if (existsSync(parts)) cpSync(parts, path.join(dir, 'training'), { recursive: true });
    writeFileSync(path.join(dir, 'package.json'), '{ "type": "module" }\n');
    return await import(pathToFileURL(path.join(dir, 'trainingData.ts')).href);
  } finally { rmSync(dir, { recursive: true, force: true }); }
}
const data = modulePath ? await load(modulePath) : await import(new URL('../src/panels/trainingData.ts', import.meta.url).href);
const reference = option('--verify') ? await load(option('--verify')) : null;
let verified = 0, different = 0;
/** The first difference of two values (numbers by Object.is, the same keys), or null. */
function differ(a, b, where = '') {
  if (typeof a !== typeof b) return `${where}: ${typeof a} vs ${typeof b}`;
  if (typeof a === 'number') return Object.is(a, b) ? null : `${where}: ${a} vs ${b}`;
  if (a === null || b === null || typeof a !== 'object') return a === b ? null : `${where}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`;
  if (Array.isArray(a)) { if (a.length !== b.length) return `${where}: length ${a.length} vs ${b.length}`; for (let i = 0; i < a.length; i++) { const d = differ(a[i], b[i], `${where}[${i}]`); if (d) return d; } return null; }
  const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
  if (ka.join() !== kb.join()) return `${where}: keys ${ka.join()} vs ${kb.join()}`;
  for (const key of ka) { const d = differ(a[key], b[key], `${where}.${key}`); if (d) return d; }
  return null;
}
console.log(`profiling ${modulePath ?? 'frontend/src/panels/trainingData.ts'} on node ${process.version}${globalThis.gc ? '' : ' (no --expose-gc: no memory figures)'}`);
const { TrainingStore } = data;
const quick = args.includes('--quick');
const gc = globalThis.gc ?? null;

// ---- synthetic answers, shaped as training_series.read_training sends them (columns, words coded once per answer) ----------
const coded = values => { const words = [], index = new Map(); return { values: words, codes: values.map(v => { if (v == null) return -1; if (!index.has(v)) { index.set(v, words.length); words.push(v); } return index.get(v); }) }; };
const T0 = 1.76e9;
const PER = 8;                                              // learner updates per evaluation after the warm-up
/** Rows of evaluations [k0, k1) (1-based numbers) and their learner updates, as answer columns. `cum0`: updates before k0. */
function rows(k0, k1, cum0, variant = 0) {
  const e = { n: 0, commit_seq: [], completion_index: [], global_env_step: [], episode_step: [], policy_version: [], reward: [], valid: [],
    all_hard_constraints_satisfied: [], normalized_constraint_violation: [], clearance_margin: [], best_so_far_feasible: [], best_so_far_violation: [],
    execution_seconds: [], committed_at: [], best_so_far_objective: [] };
  const eWords = { episode_id: [], phase: [], action_source: [], status: [] };
  const u = { n: 0, cumulative_updates: [], evaluations_collected: [], actor_loss: [], critic_loss: [], alpha_loss: [], alpha: [], mean_log_prob: [],
    target_mean: [], critic_grad_norm: [], actor_grad_norm: [], updated_at: [] };
  const s = { n: 0, commit_seq: [], raw_value: [], satisfied: [] }, sWords = { metric_name: [], failure_reason: [] };
  let cum = cum0;
  for (let k = k0; k < k1; k++) {
    const start = (k - 1) % 5 === 0, timeout = k % 41 === 0, phase = start ? (k === 1 ? 'baseline' : 'episode_reset') : k < 9 ? 'warmup' : 'search';
    const gain = k % 37 === 0 ? null : 350 + 120 * (1 - Math.exp(-k / 1200)) + 5 * Math.cos(k + variant), met = gain !== null && gain >= 400;
    e.n += 1; e.commit_seq.push(k); e.completion_index.push(k); e.global_env_step.push(k); e.episode_step.push((k - 1) % 5); e.policy_version.push(null);
    e.reward.push(start || timeout ? null : -0.3 * Math.exp(-k / 1500) - 0.01 * (1 + Math.sin(k * 1.3 + variant)));
    e.valid.push(!timeout && gain !== null); e.all_hard_constraints_satisfied.push(met);
    e.normalized_constraint_violation.push(timeout || gain === null ? null : Math.max(0, (400 - gain) / 400)); e.clearance_margin.push(timeout ? null : (gain ?? 0) / 400 - 1);
    e.best_so_far_feasible.push(k > 2000); e.best_so_far_violation.push(Math.max(0, 0.1 - k / 20000)); e.execution_seconds.push(1 + (k % 7) / 10);
    e.committed_at.push(T0 + k); e.best_so_far_objective.push(null);
    eWords.episode_id.push(`0-${String(Math.ceil(k / 5)).padStart(6, '0')}`); eWords.phase.push(phase);
    eWords.action_source.push(start ? 'reset' : phase === 'warmup' ? 'random_warmup' : 'sac_policy'); eWords.status.push(timeout ? 'timeout' : 'ok');
    for (const [name, value] of [['gain_vv', timeout ? null : gain], ['pm_deg', timeout ? null : 60 + 10 * Math.sin(k / 50 + variant)]]) {
      s.n += 1; s.commit_seq.push(k); s.raw_value.push(value); s.satisfied.push(value === null ? null : name === 'gain_vv' ? met : value >= 55);
      sWords.metric_name.push(name); sWords.failure_reason.push(timeout ? 'evaluation_status_timeout' : value === null ? 'missing_or_nonfinite' : null);
    }
    if (!start && k >= 9) for (let j = 0; j < PER; j++) {
      cum += 1;
      u.n += 1; u.cumulative_updates.push(cum); u.evaluations_collected.push(k); u.actor_loss.push(0.2 * Math.sin(cum / 50 + variant));
      u.critic_loss.push(0.1 * Math.exp(-cum / 9000) + 0.001 * (1 + Math.cos(cum))); u.alpha_loss.push(0.01 * Math.sin(cum / 7)); u.alpha.push(0.01 * Math.exp(-cum / 40000));
      u.mean_log_prob.push(-6 + cum / 6000); u.target_mean.push(-0.1 + 0.01 * Math.sin(cum / 300)); u.critic_grad_norm.push(1 + Math.abs(Math.sin(cum / 11)));
      u.actor_grad_norm.push(2 + Math.abs(Math.cos(cum / 13))); u.updated_at.push(T0 + k);
    }
  }
  for (const [name, list] of Object.entries(eWords)) e[name] = coded(list);
  u.update_phase = coded(new Array(u.n).fill(null));
  for (const [name, list] of Object.entries(sWords)) s[name] = coded(list);
  return { chunk: { evaluations: e, updates: u, specs: s,
    spec_defs: { gain_vv: { unit: 'V/V', threshold_lower: 400, threshold_upper: null, hard: true }, pm_deg: { unit: 'deg', threshold_lower: 55, threshold_upper: null, hard: true } } }, cum };
}
const EMPTY = () => rows(1, 1, 0).chunk;
/** The number of evaluations that bring `updates` learner updates. */
const evaluationsFor = updates => { let k = 8, cum = 0; while (cum < updates) { k += 1; if ((k - 1) % 5 !== 0) cum += PER; } return k; };
const SEGMENTS = [{ segment: 1, entry: 'start', started_utc: new Date(T0 * 1000).toISOString(), ended_utc: null, end_state: null, stop_reason: null }];

/** A live run: its store, then `poll()` appends a journal page of 2 evaluations, `flush()` publishes the provisional rows. */
function liveRun(dir, updates, variant) {
  const store = new TrainingStore(dir), twin = reference ? new reference.TrainingStore(dir) : null;
  const n = evaluationsFor(updates);
  const first = rows(1, n + 1, 0, variant);
  let flushes = 1, cursor = 'c0', k = n + 1, cum = first.cum, tailFrom = k, tailCum = cum, page = 0;
  const answer = (final, tail, start, served, pageStart, reset) => ({ run_dir: dir, run_id: dir, mode: 'scratch', mock: true, state: 'running', worker_alive: true,
    flushes: { served, total: served, start }, final, tail, tail_complete: true, latest_seq: k - 1, objective: { metric: 'gain_vv', direction: 'max' },
    learner: { recorded: true, every: 1, reason: null }, segments: SEGMENTS, tail_page: { start: pageStart, cursor: `c${++page}`, reset, more: false } });
  const firstAnswer = answer(first.chunk, EMPTY(), 0, 1, null, true);
  if (!store.apply(firstAnswer)) throw new Error('the first answer was not applied');
  twin?.apply(firstAnswer);
  cursor = store.tailCursor;
  return {
    store, twin, label: dir,
    applied: [],                                                      // ms of each TrainingStore.apply (the answer made beforehand)
    poll() {                                                          // 2 more evaluations in the journal
      const next = rows(k, k + 2, cum, variant); k += 2; cum = next.cum;
      const made = answer(EMPTY(), next.chunk, flushes, flushes, cursor, false), t0 = performance.now();
      const changed = store.apply(made); this.applied.push(performance.now() - t0); cursor = store.tailCursor;
      twin?.apply(made);
      if (!changed) throw new Error('a poll changed nothing');
    },
    flush() {                                                         // a new flush: the provisional rows come back as final rows
      const published = rows(tailFrom, k, tailCum, variant), next = rows(k, k + 2, published.cum, variant);
      tailFrom = k; tailCum = published.cum; k += 2; cum = next.cum;
      const made = answer(published.chunk, next.chunk, flushes, flushes + 1, cursor, true), t0 = performance.now();
      const changed = store.apply(made); this.applied.push(performance.now() - t0); flushes += 1; cursor = store.tailCursor;
      twin?.apply(made);
      if (!changed) throw new Error('a flush changed nothing');
    },
  };
}

// ---- one frame, as TrainingTab.tsx makes it ---------------------------------------------------------------------------------
const CHARTS = {
  1: ['critic_loss'],
  8: ['reward', 'pass', 'spec:gain_vv', 'critic_loss', 'actor_loss', 'alpha', 'entropy', 'grad_norm'],
  learner8: ['actor_loss', 'critic_loss', 'alpha', 'entropy', 'alpha_loss', 'target_mean', 'grad_norm', 'actor_loss'],   // the audit's set
};
/** `viewOf(x)`: the chart's view for its x axis ('evaluation' or 'update'): each chart has its own zoom on the page. */
function frame(runs, charts, smoothing, viewOf, learnerX, width = 600) {
  const made = (module, which) => {                // what TrainingTab.tsx makes for one frame, with `module` from the stores `which`
    const own = which(runs[0]), context = {}, out = { catalog: module.catalog(own, context), keys: [], charts: [] };
    out.at = [performance.now()];
    for (const run of runs) out.keys.push(module.keyNumbers(which(run), {}));
    out.at.push(performance.now());
    for (const id of charts) {
      const spec = out.catalog.find(c => c.id === id);
      if (!spec?.available) throw new Error(`chart ${id} unavailable`);
      const view = viewOf(spec.axis === 'update' && learnerX === 'update' ? 'update' : 'evaluation');
      out.charts.push(runs.length === 1 ? module.build(own, id, smoothing, view, width, context, learnerX)
        : module.buildCompare(runs.map((r, i) => ({ store: which(r), label: r.label, context: i ? undefined : context })), id, smoothing, view, width, learnerX));
    }
    out.at.push(performance.now());
    return out;
  };
  const t0 = performance.now(), mine = made(data, r => r.store), [t1, t2, t3] = mine.at;
  if (reference) {                                  // not timed: the same frame from the other module's twin stores
    const theirs = made(reference, r => r.twin);
    for (const key of ['catalog', 'keys', 'charts']) {
      verified += 1;
      const d = differ(mine[key], theirs[key], key);
      if (d) { different += 1; if (different <= 5) console.log(`DIFFERENT  ${d}`); }
    }
  }
  return { total: t3 - t0, catalog: t1 - t0, keys: t2 - t1, builds: t3 - t2 };
}
const stats = list => { const s = [...list].sort((a, b) => a - b), q = p => s[Math.min(s.length - 1, Math.floor(p * s.length))]; return { median: +q(0.5).toFixed(3), p90: +q(0.9).toFixed(3), max: +s[s.length - 1].toFixed(3) }; };
// the JS heap plus the typed arrays' buffers (outside the JS heap: the tables' columns)
const used = () => { const m = process.memoryUsage(); return m.heapUsed + m.arrayBuffers; };
// after a full collection, typed-array buffers are freed in the background: wait until the figure settles
const heap = async () => { let last = Infinity; for (let i = 0; i < 6; i++) { gc?.(); await new Promise(r => setTimeout(r, 40)); const now = used(); if (Math.abs(now - last) < 65536) return now; last = now; } return last; };
const mb = bytes => +(bytes / 1048576).toFixed(1);

// ---- the scenarios -------------------------------------------------------------------------------------------------------------
const SIZES = quick ? [8000, 100000] : [8000, 100000, 200000];
const FRAMES = quick ? 6 : 12;
const results = [];
for (const updates of SIZES) {
  for (const runCount of [1, 4]) {
    const before = await heap();
    const runs = Array.from({ length: runCount }, (_, i) => liveRun(`/fixture/mock/run${i}`, updates, i));
    const loaded = await heap();
    const kMid = Math.round(runs[0].store.evaluations.n / 2), uMid = Math.round(updates / 2);
    const views = { all: () => ({ mode: 'all' }), follow: () => ({ mode: 'follow', width: 1000 }),
      fixed: x => (x === 'update' ? { mode: 'fixed', min: uMid, max: uMid + 3000 } : { mode: 'fixed', min: kMid, max: kMid + 400 }) };
    const variants = [
      ['8 charts', CHARTS[8], 20, 'all', 'update'], ['8 charts', CHARTS[8], 20, 'follow', 'update'], ['8 charts', CHARTS[8], 20, 'fixed', 'update'],
      ['1 chart', CHARTS[1], 20, 'all', 'update'], ['1 chart', CHARTS[1], 20, 'follow', 'update'],
      ['8 charts', CHARTS[8], 20, 'all', 'evaluation'], ['8 charts', CHARTS[8], 0, 'all', 'update'],
      ['audit 8 learner charts', CHARTS.learner8, 20, 'follow', 'update'],
    ];
    for (const [name, charts, smoothing, viewName, learnerX] of variants) {
      const view = views[viewName];
      for (let i = 0; i < 2; i++) { for (const r of runs) r.poll(); frame(runs, charts, smoothing, view, learnerX); }   // warm: JIT, caches
      const append = [], flush = [];
      for (const r of runs) r.applied.length = 0;
      for (let i = 0; i < FRAMES; i++) {
        for (const r of runs) (i % 4 === 3 ? r.flush() : r.poll());
        (i % 4 === 3 ? flush : append).push(frame(runs, charts, smoothing, view, learnerX));
      }
      const part = list => ({ total: stats(list.map(f => f.total)), catalog: stats(list.map(f => f.catalog)), keys: stats(list.map(f => f.keys)), builds: stats(list.map(f => f.builds)) });
      const row = { updates, evaluations: runs[0].store.evaluations.n, runs: runCount, charts: name, smoothing, view: viewName, learnerX,
        append: part(append), flush: part(flush), apply_per_run: stats(runs.flatMap(r => r.applied)) };
      results.push(row);
      console.log(`${String(updates).padStart(6)} upd | ${runCount} run${runCount > 1 ? 's' : ' '} | ${name.padEnd(22)} | smooth ${String(smoothing).padStart(2)} | ${viewName.padEnd(6)} | by ${learnerX.padEnd(10)} | `
        + `append frame median ${String(row.append.total.median).padStart(8)} ms (p90 ${row.append.total.p90}; builds ${row.append.builds.median}, keys ${row.append.keys.median}, catalog ${row.append.catalog.median}) | `
        + `flush frame median ${row.flush.total.median} ms | apply per run and poll median ${row.apply_per_run.median} ms`);
    }
    // memory: what the stores hold, what a frame leaves behind (caches), and what one frame allocates
    const settled = await heap();
    let allocated = [];
    if (gc && !reference) for (let i = 0; i < 4; i++) {     // (--verify: the other module's frame would be counted too)
      for (const r of runs) r.poll();
      const h0 = await heap(); frame(runs, CHARTS[8], 20, views.all, 'update'); allocated.push(used() - h0);
    }
    // stores_mb: the runs' stores as loaded; after_frames_mb: the same stores (a few hundred rows more) with whatever the
    // frames left behind (derived caches) - the difference between two modules is what their caches hold
    // prepared_mb: what the chart preparation of record 7.221 holds for these runs (its arrays and checkpoints), when the module has it
    const prepared = data.preparedSize ? runs.reduce((sum, r) => sum + (data.preparedSize(r.store)?.bytes ?? 0), 0) : null;
    const memory = gc && !reference ? { stores_mb: mb(loaded - before), after_frames_mb: mb(settled - before), prepared_mb: prepared === null ? null : mb(prepared),
      allocated_per_8_chart_all_frame_mb: stats(allocated.map(mb)).median } : null;
    if (memory) console.log(`${String(updates).padStart(6)} upd | ${runCount} run${runCount > 1 ? 's' : ' '} | memory: stores ${memory.stores_mb} MB as loaded, ${memory.after_frames_mb} MB after the frames`
      + `${prepared === null ? '' : ` (of it the shared preparation ${memory.prepared_mb} MB)`}, one 8-chart frame (view all) allocates ~${memory.allocated_per_8_chart_all_frame_mb} MB`);
    results.push({ updates, runs: runCount, memory });
    runs.length = 0;
  }
}
const report = { origin: 'synthetic', provenance: 'mock', module: modulePath ?? 'frontend/src/panels/trainingData.ts', node: process.version, gc: !!gc, frames_per_variant: FRAMES,
  scope: 'TrainingTab frame work in node: catalog + keyNumbers per run + build/buildCompare per chart; browser drawing excluded', results };
const json = option('--json');
if (json) writeFileSync(json, JSON.stringify({ ...report, verified: reference ? { against: option('--verify'), frames: verified / 3, different } : null }, null, 2) + '\n');
if (reference) {
  console.log(`verified against ${option('--verify')}: ${verified / 3} frames (catalog, key numbers, every chart), ${different} different`);
  process.exit(different ? 1 : 0);
}
