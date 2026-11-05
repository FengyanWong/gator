// Check of the Training tab's arithmetic (record 7.193): frontend/src/panels/trainingData.ts, imported AS IT IS - Windows
// node (>= 22.18) strips its types - and fed answers shaped like GET /api/runs/training (backend training_series.py). No
// browser and no backend: what is checked is that the numbers a chart gets are the numbers the run recorded.
//   - every value a series carries equals the value of its recorded row; a missing value is a gap (null), never 0;
//     a row of another category is `undefined` (uPlot draws across it, not a gap)
//   - the journal tail is replaced by every answer: a bundle flushed later is never counted twice; a late answer is ignored
//   - smoothing = a trailing mean of the last N recorded values; gaps are kept; a window of zeros reads 0, not the rounding
//     remainder of a running sum (branch record SIF-134); a compared run's series carry their own words without its name
//   - thinning for the screen (decimate) keeps every pixel column's first/last row and each series' extremes and first gap
//   - learner counter resets (resume from an older save point): the abandoned updates are a series of their own
//   - the memory bound thins the oldest half, keeps every spike, and keeps evaluation numbers and order intact
//   - learner charts by evaluation (record 7.213): x = evaluations collected, the updates after one evaluation share its x,
//     the mean is over the last N evaluations, compared runs learning 8 and 1 times per evaluation share the slots of an x
//   - key numbers (record 7.215): first passing design, passing share of the last 100 evaluations, best design's miss,
//     entropy and temperature at the start and the end - the recorded values, episode starts and no-verdict rows left out;
//     an episode start that passed before the first passing design is named apart (branch record SIF-116)
//   - shared chart preparation (record 7.221): a store kept up to date over many answers draws exactly what a new store fed
//     the same answers at once draws (random runs: pages, flushes, journal rewrites, spec values joining earlier pages,
//     learner restarts, resumes, thinning, missing metrics), and - given the trainingData.ts before 7.221 - exactly what the
//     builders before it drew; the preparation stays bounded and goes with its store
// Run: "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/training_data_check.mjs)"   (a few seconds)
//   [--seeds N] (random runs, default 12)   [--reference <trainingData.ts before 7.221>] or TRAINING_DATA_REFERENCE=<it>:
//   e.g. git show c170802:frontend/src/panels/trainingData.ts > <file>.ts - each step of each random run also against it
//   (a trainingData.ts split into parts - plan-refactoring C12 - is given with its training/ folder beside it)
import { copyFileSync, cpSync, existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import v8 from 'node:v8';
import vm from 'node:vm';

const data = await import(new URL('../src/panels/trainingData.ts', import.meta.url).href);
const { TrainingStore, build, buildCompare, catalog, decimate, smooth, smoothOver, updateBranches, viewRange, setCaps, passFlags, keyNumbers, RECENT, ENDS } = data;
if (fileURLToPath(import.meta.url) && !TrainingStore) throw new Error('trainingData.ts did not load');
const argv = process.argv.slice(2), option = (name, fallback = null) => { const i = argv.indexOf(name); return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback; };

let passed = 0, failed = 0;
const check = (name, ok, info = '') => { if (ok) passed++; else failed++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---- answers shaped as training_series.read_training sends them ------------------------------------------------------
const WORDS = new Set(['episode_id', 'phase', 'action_source', 'status', 'update_phase', 'metric_name', 'failure_reason']);
function columns(rows, names) {
  const out = { n: rows.length };
  for (const name of names) {
    const values = rows.map(r => (r[name] === undefined ? null : r[name]));
    if (WORDS.has(name)) {
      const words = [];
      out[name] = { values: words, codes: values.map(v => (v === null ? -1 : (words.includes(v) ? words.indexOf(v) : words.push(v) - 1))) };
    } else out[name] = values;
  }
  return out;
}
const EVALUATION = ['commit_seq', 'completion_index', 'global_env_step', 'episode_id', 'episode_step', 'phase', 'action_source', 'status',
  'policy_version', 'reward', 'valid', 'all_hard_constraints_satisfied', 'normalized_constraint_violation', 'clearance_margin',
  'best_so_far_feasible', 'best_so_far_violation', 'execution_seconds', 'committed_at', 'best_so_far_objective'];
const UPDATE = ['cumulative_updates', 'evaluations_collected', 'update_phase', 'actor_loss', 'critic_loss', 'alpha_loss', 'alpha',
  'mean_log_prob', 'target_mean', 'critic_grad_norm', 'actor_grad_norm', 'updated_at'];
const SPEC = ['commit_seq', 'metric_name', 'raw_value', 'satisfied', 'failure_reason'];
const chunk = ({ evaluations = [], updates = [], specs = [], defs = {} } = {}) =>
  ({ evaluations: columns(evaluations, EVALUATION), updates: columns(updates, UPDATE), specs: columns(specs, SPEC), spec_defs: defs });
const answer = ({ start = 0, served, total, final, tail = null, tail_page, objective = null, learner = { recorded: true, every: 1, reason: null }, segments = [], complete = true, latest = 0 }) =>
  ({ run_dir: '/fixture/run', run_id: 'fixture', mode: 'scratch', mock: true, flushes: { served, total, start }, final, tail, tail_complete: complete,
     latest_seq: latest, objective, learner, segments, tail_page });
const evaluation = (seq, over = {}) => ({ commit_seq: seq, completion_index: seq, global_env_step: seq, episode_id: `0-${String(Math.ceil(seq / 5)).padStart(6, '0')}`,
  episode_step: (seq - 1) % 5, phase: 'search', action_source: 'sac_policy', status: 'ok', reward: -1 / seq, valid: true,
  all_hard_constraints_satisfied: false, normalized_constraint_violation: 1 / seq, clearance_margin: -1 / seq, best_so_far_feasible: false,
  best_so_far_violation: 1 / seq, execution_seconds: 1.5, committed_at: 1.7e9 + seq, best_so_far_objective: null, ...over });
const update = (cum, over = {}) => ({ cumulative_updates: cum, evaluations_collected: cum, actor_loss: Math.sin(cum), critic_loss: 1 / cum, alpha_loss: 0,
  alpha: 0.01, mean_log_prob: -2 + cum / 100, target_mean: 0.1, critic_grad_norm: 1, actor_grad_norm: 2, updated_at: 1.7e9 + cum, ...over });
const valuesOf = (built, label) => built.series.find(s => s.label === label)?.values;

// ---- 1. one answer: every series value is its recorded row's value; gaps and categories --------------------------------
{
  const store = new TrainingStore('/fixture/run');
  const rows = [
    evaluation(1, { phase: 'baseline', action_source: 'reset', reward: null, episode_step: 0 }),
    evaluation(2, { phase: 'warmup', action_source: 'random_warmup', reward: -0.31192639049518256 }),
    evaluation(3, { reward: -0.2867916898717725, all_hard_constraints_satisfied: true, normalized_constraint_violation: 0 }),
    evaluation(4, { status: 'measurement_error', reward: null, valid: false, normalized_constraint_violation: null }),
    evaluation(5, { status: 'timeout', reward: null, valid: false, normalized_constraint_violation: null }),
    evaluation(6, { phase: 'episode_reset', action_source: 'reset', reward: null }),
    evaluation(7, { phase: 'frozen_eval', action_source: 'mean_policy', reward: -0.0, all_hard_constraints_satisfied: true }),
  ];
  const specs = [[1, 401.5], [2, 380.25], [3, null], [4, null], [6, 401.5], [7, 472.03220571111393]].map(([seq, value]) =>
    ({ commit_seq: seq, metric_name: 'gain_vv', raw_value: value, satisfied: value === null ? null : value >= 400, failure_reason: value === null ? 'missing_or_nonfinite' : null }));
  const defs = { gain_vv: { unit: 'V/V', threshold_lower: 400, threshold_upper: null, hard: true } };
  const changed = store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows, specs, defs, updates: [update(1), update(2)] }) }));
  check('an answer is applied and says something changed', changed && store.evaluations.n === 7 && store.updates.n === 2, `n=${store.evaluations.n}`);
  check('evaluation numbers are the recorded order, 1-based', same(Array.from(store.evaluations.cols.k.subarray(0, 7)), [1, 2, 3, 4, 5, 6, 7]));
  const reward = build(store, 'reward', 0, { mode: 'all' }, 800);
  check('step reward: training values exactly as recorded, a missing reward a gap (null), other rows undefined',
    same(valuesOf(reward, 'Training'), [undefined, -0.31192639049518256, -0.2867916898717725, null, null, undefined, undefined]), JSON.stringify(valuesOf(reward, 'Training')));
  check('step reward: the frozen policy\'s design is its own Evaluation series', same(valuesOf(reward, 'Evaluation'), [undefined, undefined, undefined, undefined, undefined, undefined, -0]));
  check('step reward: no Episode start series (a reset has no reward)', !reward.series.some(s => s.category === 'start'));
  const pass = Array.from(passFlags(store));
  check('pass flag: met = 1, not met = 0, a measurement error = 0 (a verdict), a timeout = gap', same(pass.map(v => (Number.isNaN(v) ? null : v)), [0, 0, 1, 0, null, 0, 1]));
  const gain = build(store, 'spec:gain_vv', 0, { mode: 'all' }, 800);
  check('spec values exactly as recorded, a failed measurement a gap, an interrupted evaluation (no row) a gap',
    same(valuesOf(gain, 'Training'), [undefined, 380.25, null, null, null, undefined, undefined]) && same(valuesOf(gain, 'Episode start'), [401.5, undefined, undefined, undefined, undefined, 401.5, undefined])
    && same(valuesOf(gain, 'Evaluation'), [undefined, undefined, undefined, undefined, undefined, undefined, 472.03220571111393]), JSON.stringify(gain.series.map(s => s.values)));
  check('the spec\'s limit is a constant series at the recorded threshold', same(valuesOf(gain, 'lower limit'), [400, 400, 400, 400, 400, 400, 400]));
  const gainSmoothed = build(store, 'spec:gain_vv', 20, { mode: 'all' }, 800);
  check('smoothing: a mean for training and evaluation, none for the episode start (one design re-simulated)',
    gainSmoothed.series.some(x => x.label === 'Training: mean of last 20') && !gainSmoothed.series.some(x => /Episode start: mean/.test(x.label))
    && gainSmoothed.series.some(x => x.label === 'Episode start' && x.role === 'raw'), gainSmoothed.series.map(x => x.label).join(' | '));
  check('spec unit from the recorded row', gain.unit === 'V/V');
  const list = catalog(store);
  check('episode return is offered as NOT recorded, with the reason', list.find(c => c.id === 'episode_return')?.available === false && /not of whole episodes/.test(list.find(c => c.id === 'episode_return').reason));
  check('evaluation success rate available when a frozen policy was evaluated', list.find(c => c.id === 'eval_pass')?.available === true);
  const rate = build(store, 'eval_pass', 0, { mode: 'all' }, 800);
  check('evaluation success rate = share of evaluated designs so far', same(valuesOf(rate, 'Evaluation: share so far'), [undefined, undefined, undefined, undefined, undefined, undefined, 1]));
  check('no objective: the chart says why', list.find(c => c.id === 'objective')?.available === false && /lower\/higher is better/.test(list.find(c => c.id === 'objective').reason));
  const calibrated = build(store, 'reward', 0, { mode: 'all' }, 800, { calibration: true });
  check('a baseline run that calibrates: its random designs are "Calibration (random designs)", not Training',
    calibrated.series.some(x => x.label === 'Calibration (random designs)') && !calibrated.series.some(x => x.label === 'Training'));
  check('...and its learner charts say it learns nothing', /learns nothing/.test(catalog(store, { calibration: true }).find(c => c.id === 'critic_loss').reason)
    && catalog(store, { calibration: true }).find(c => c.id === 'critic_loss').available === false);
  const actor = build(store, 'actor_loss', 0, { mode: 'all' }, 800);
  check('learner chart: x = cumulative update count, values as recorded', same(actor.x, [1, 2]) && same(valuesOf(actor, 'Actor loss'), [Math.sin(1), Math.sin(2)]));
  const entropy = build(store, 'entropy', 0, { mode: 'all' }, 800);
  check('entropy estimate = -mean_log_prob (the data dictionary\'s definition)', same(valuesOf(entropy, 'Entropy estimate'), [-(-2 + 1 / 100), -(-2 + 2 / 100)]));
}

// ---- 2. the journal tail is replaced, never counted twice; a late answer is ignored ------------------------------------
{
  const store = new TrainingStore('/fixture/run');
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: [1, 2, 3].map(s => evaluation(s)) }), tail: chunk({ evaluations: [4, 5].map(s => evaluation(s)), updates: [update(1)] }), latest: 5 }));
  check('final rows + tail rows', store.evaluations.n === 5 && store.finalEvaluations === 3 && store.updates.n === 1);
  // the two tail bundles got flushed: they come back as final rows, with one more, and a new tail of one
  store.apply(answer({ start: 1, served: 2, total: 2, final: chunk({ evaluations: [4, 5, 6].map(s => evaluation(s)), updates: [update(1)] }), tail: chunk({ evaluations: [evaluation(7)] }), latest: 7 }));
  const seqs = Array.from(store.evaluations.cols.seq.subarray(0, store.evaluations.n));
  check('a flushed tail bundle is not counted twice', same(seqs, [1, 2, 3, 4, 5, 6, 7]) && store.updates.n === 1, JSON.stringify(seqs));
  check('evaluation numbers stay 1..n after the tail was replaced', same(Array.from(store.evaluations.cols.k.subarray(0, 7)), [1, 2, 3, 4, 5, 6, 7]));
  const before = store.evaluations.n, version = store.version;
  const late = store.apply(answer({ start: 0, served: 1, total: 1, final: chunk({ evaluations: [1, 2, 3].map(s => evaluation(s)) }) }));
  check('an answer to an older cursor is ignored', !late && store.evaluations.n === before && store.version === version);
  const quiet = store.apply(answer({ start: 2, served: 2, total: 2, final: chunk(), tail: chunk({ evaluations: [evaluation(7)] }), latest: 7 }));
  check('an answer with nothing new says nothing changed (no redraw)', !quiet && store.evaluations.n === 7);
  store.apply(answer({ start: 2, served: 2, total: 2, final: chunk(), tail: null, complete: false, latest: 6 }));
  check('a tail that could not be read (journal rewritten) drops the old tail and keeps the final rows', store.evaluations.n === 6 && !store.tailComplete);
}

// A small spec page joins only the evaluations it names, including late, duplicate and out-of-order sequences.
{
  const store = new TrainingStore('/fixture/spec-joins');
  const rows = Array.from({ length: 50000 }, (_, i) => ({ commit_seq: 2 * (i + 1) }));
  rows[3].commit_seq = 999999; rows[7].commit_seq = 2;
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows }) }));
  const spec = (seq, value, metric = 'gain') => ({ commit_seq: seq, metric_name: metric, raw_value: value,
    satisfied: true, failure_reason: null });
  const join = specs => store.apply(answer({ start: 1, served: 1, total: 1, final: chunk({ specs }) }));
  const seq = store.evaluations.cols.seq;
  let reads = 0;
  store.evaluations.cols.seq = new Proxy(seq, { get(target, key) {
    if (typeof key === 'string' && /^\d+$/.test(key)) reads++;
    return Reflect.get(target, key, target);
  } });
  try { join([spec(100000, 91), spec(100000, 62, 'pm')]); }
  finally { store.evaluations.cols.seq = seq; }
  const cols = store.evaluations.cols;
  check('two specs for the newest of 50,000 evaluations inspect only that evaluation', reads === 1
    && cols['spec:gain'][49999] === 91 && cols['spec:pm'][49999] === 62, `${reads} sequence reads`);
  const stamp = store.specChanges.stamp;
  join([spec(2, 12), spec(4, 14), spec(999999, 19), spec(3, 999), spec(null, 999), spec(undefined, 999)]);
  check('sparse late specs keep the last duplicate and find out-of-order sequences', Number.isNaN(cols['spec:gain'][0])
    && cols['spec:gain'][7] === 12 && cols['spec:gain'][1] === 14 && cols['spec:gain'][3] === 19);
  check('missing sequences and gaps never attach a spec to a neighbouring evaluation',
    Array.from(cols['spec:gain'].subarray(0, store.evaluations.n)).filter(Number.isFinite).length === 4);
  check('late spec joins invalidate chart preparation from the earliest changed row', store.specChanges.since(stamp) === 1);
  const dense = new TrainingStore('/fixture/dense-spec-joins');
  dense.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: [2, 7, 2].map(s => evaluation(s)),
    specs: [spec(2, 12), spec(7, 17), spec(3, 999)] }) }));
  check('dense initial specs preserve the same duplicate, gap and out-of-order behavior',
    same(Array.from(dense.evaluations.cols['spec:gain'].subarray(0, 3)), [NaN, 17, 12]));
}

// ---- 3. smoothing --------------------------------------------------------------------------------------------------------
{
  const raw = [1, 2, null, 3, undefined, 4, 10];
  check('trailing mean of the last 2 recorded values; a gap stays a gap; another category stays undefined',
    same(smooth(raw, 2), [1, 1.5, null, 2.5, undefined, 3.5, 7]));
  check('a window larger than the data is the mean so far', same(smooth([2, 4, 6], 50), [2, 3, 4]));
  // Branch record SIF-134: a window of only zeros reads 0. The running sum adds each value and takes off the one leaving, and
  // 0.1 + 0.2 - 0.1 - 0.2 leaves 2.8e-17: "Worst spec miss" read "mean of last 50 2.558e-17" once every design met its specs.
  // The chart's mean of the last N, its mean over the updates of the last N evaluations, and smooth / smoothOver the same.
  const zeros = new TrainingStore('/fixture/zeros'), seq = [0.1, 0.2, 0, 0];
  zeros.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: seq.map((v, i) => evaluation(i + 1, { normalized_constraint_violation: v })),
    updates: seq.map((v, i) => update(i + 1, { evaluations_collected: i + 1, actor_loss: v })) }) }));
  const last = valuesOf(build(zeros, 'violation', 2, { mode: 'all' }, 800), 'Training: mean of last 2');
  const over = valuesOf(build(zeros, 'actor_loss', 2, { mode: 'all' }, 800, {}, 'evaluation'), 'Actor loss: mean of last 2 evaluations');
  check('a window of only zeros after other values reads exactly 0: the mean of the last N, and over the last N evaluations; the means before it as before (SIF-134)',
    same(last, [0.1, 0.15000000000000002, 0.10000000000000002, 0]) && Object.is(last[3], 0) && same(over, last) && Object.is(over[3], 0)
    && same(smooth(seq, 2), last) && Object.is(smooth(seq, 2)[3], 0) && same(smoothOver([1, 2, 3, 4], seq, 2), last) && Object.is(smoothOver([1, 2, 3, 4], seq, 2)[3], 0),
    JSON.stringify({ last, over, smooth: smooth(seq, 2), smoothOver: smoothOver([1, 2, 3, 4], seq, 2) }));
  // ...and so when a zoomed chart works the window out from a checkpoint (every 2 positions here): the checkpoint keeps how
  // many of its values are not 0
  data.setSpacing(2);
  const zoomed = new TrainingStore('/fixture/zeros-checkpoint');
  zoomed.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: seq.map((v, i) => evaluation(i + 1, { normalized_constraint_violation: v })),
    updates: seq.map((v, i) => update(i + 1, { evaluations_collected: i + 1, actor_loss: v })) }) }));
  build(zoomed, 'violation', 2, { mode: 'all' }, 800); build(zoomed, 'actor_loss', 2, { mode: 'all' }, 800, {}, 'evaluation');   // the checkpoints
  const lastZoomed = valuesOf(build(zoomed, 'violation', 2, { mode: 'fixed', min: 3.5, max: 4 }, 800), 'Training: mean of last 2');
  const overZoomed = valuesOf(build(zoomed, 'actor_loss', 2, { mode: 'fixed', min: 3.5, max: 4 }, 800, {}, 'evaluation'), 'Actor loss: mean of last 2 evaluations');
  data.setSpacing(4096);
  check('...also worked out from a checkpoint, as a zoomed chart does (SIF-134)', same(lastZoomed, last.slice(2)) && Object.is(lastZoomed.at(-1), 0)
    && same(overZoomed, last.slice(2)) && Object.is(overZoomed.at(-1), 0), JSON.stringify({ last: lastZoomed, over: overZoomed }));
}

// ---- 4. thinning for the screen keeps extremes, gaps and the edges -------------------------------------------------------
{
  const n = 100000, x = Array.from({ length: n }, (_, i) => i + 1);
  let seed = 7; const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const a = x.map(() => random()), b = x.map((_, i) => (i % 3 === 0 ? undefined : random()));
  a[51234] = 50; a[77777] = -50; a[1000] = null; b[90001] = 99;
  const keep = decimate(x, [a, b], 0, n, 1, n, 400);
  check('thinned to a few points per pixel column', keep.length < 400 * 12 && keep.length > 400, `${keep.length} rows`);
  check('every row kept is a recorded row, in order', keep.every((r, i) => Number.isInteger(r) && r >= 0 && r < n && (i === 0 || r > keep[i - 1])));
  check('a spike up and a spike down survive', keep.includes(51234) && keep.includes(77777));
  check('a gap survives', keep.includes(1000));
  check('the other series\' spike survives', keep.includes(90001));
  check('the first and the last row are kept', keep[0] === 0 && keep[keep.length - 1] === n - 1);
  // every pixel column: its max and min are among the kept rows
  let ok = true;
  for (let bucket = 0; bucket < 400 && ok; bucket += 37) {
    const lo = Math.ceil(1 + bucket * (n - 1) / 400), hi = Math.floor(1 + (bucket + 1) * (n - 1) / 400) - 1;
    let max = -Infinity, at = -1;
    for (let i = lo - 1; i < hi; i++) if (typeof a[i] === 'number' && a[i] > max) { max = a[i]; at = i; }
    if (at >= 0 && !keep.includes(at)) ok = false;
  }
  check('each sampled pixel column keeps its largest value', ok);
  const few = decimate([1, 2, 3], [[1, 2, 3]], 0, 3, 1, 3, 400);
  check('few rows: all kept', same(few, [0, 1, 2]));
  check('view ranges: all / follow / fixed / a single point', same(viewRange({ mode: 'all' }, [1, 800]), [1, 800]) && same(viewRange({ mode: 'follow', width: 100 }, [1, 800]), [700, 800])
    && same(viewRange({ mode: 'follow', width: 5000 }, [1, 800]), [1, 800]) && same(viewRange({ mode: 'fixed', min: 10, max: 20 }, [1, 800]), [10, 20]) && same(viewRange({ mode: 'all' }, [5, 5]), [4, 6]));
}

// ---- 5. learner counter resets: the abandoned updates, explicitly -----------------------------------------------------------
{
  const store = new TrainingStore('/fixture/run');
  const first = Array.from({ length: 10 }, (_, i) => update(i + 1)), second = Array.from({ length: 7 }, (_, i) => update(i + 6, { actor_loss: 100 + i }));
  store.apply(answer({ served: 1, total: 1, final: chunk({ updates: [...first, ...second] }), segments: [{ segment: 1, entry: 'start', started_utc: '2023-11-14T22:13:20Z' }, { segment: 2, entry: 'resume', started_utc: new Date((1.7e9 + 10.5) * 1000).toISOString() }] }));
  const { superseded, restarts } = updateBranches(store.updates);
  check('a repeated update count is found as a restart', same(restarts, [6]));
  check('the updates after the save point of the first line are marked abandoned', same(Array.from(superseded), [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]));
  const actor = build(store, 'actor_loss', 0, { mode: 'all' }, 800);
  check('x stays sorted with the repeated counts side by side', actor.x.every((v, i) => i === 0 || v >= actor.x[i - 1]) && actor.x.length === 17);
  const main = valuesOf(actor, 'Actor loss'), gone = valuesOf(actor, 'Actor loss: abandoned at a restart');
  check('the line goes on with the updates after the restart', same(main.filter(v => v !== undefined), [...first.slice(0, 5).map(u => u.actor_loss), ...second.map(u => u.actor_loss)]));
  check('the abandoned updates are a series of their own', same(gone.filter(v => v !== undefined), first.slice(5).map(u => u.actor_loss)));
  check('the restart and the resume are marked on the chart', actor.markers.some(m => m.kind === 'restart' && m.x === 6) && actor.markers.some(m => m.kind === 'resume'));
}

// ---- 6. the memory bound -------------------------------------------------------------------------------------------------------
{
  setCaps({ evaluations: 2000, updates: 2000 });
  const store = new TrainingStore('/fixture/run');
  const rows = Array.from({ length: 3000 }, (_, i) => evaluation(i + 1, { reward: i === 737 ? 9 : i === 1234 ? -9 : Math.sin(i), normalized_constraint_violation: i === 700 ? null : 0.5 }));
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows }) }));
  const t = store.evaluations, k = Array.from(t.cols.k.subarray(0, t.n));
  check('past the cap the oldest half is thinned', t.n < 3000 && t.n > 1500 && store.thinnedEvaluations > 0, `${t.n} rows, ${store.thinnedEvaluations} thinned`);
  check('evaluation numbers stay the recorded ones, in order', k.every((v, i) => i === 0 || v > k[i - 1]) && k[0] === 1 && k[k.length - 1] === 3000);
  check('the newer half is kept whole', k.slice(-1500).every((v, i) => v === 1501 + i));
  check('both spikes of the thinned half survive', k.includes(738) && k.includes(1235));
  check('a gap in the thinned stretch survives', (() => { const i = k.indexOf(701); return i >= 0 && i < store.thinnedEvaluations && Number.isNaN(t.cols.violation[i]); })());
  check('the thinned stretch is marked on the charts', build(store, 'reward', 0, { mode: 'all' }, 800).thinnedTo === k[store.thinnedEvaluations - 1]);
  check('the counts are the recorded ones, not the rows kept', store.counts().evaluations === 3000, JSON.stringify(store.counts()));
  const smoothed = build(store, 'reward', 20, { mode: 'all' }, 100000);
  const mean = smoothed.series.find(x => x.role === 'smooth').values, firstFull = smoothed.x.indexOf(k[store.thinnedEvaluations]);
  check('no mean is drawn over the thinned stretch; it starts after it', mean.slice(0, firstFull).every(v => v === undefined) && typeof mean[firstFull] === 'number'
    && mean[firstFull] === smoothed.series.find(x => x.role === 'raw').values[firstFull]);
  // the next answer appends after the thinned table, numbering on
  store.apply(answer({ start: 1, served: 2, total: 2, final: chunk({ evaluations: [evaluation(3001)] }), tail: chunk({ evaluations: [evaluation(3002)] }) }));
  store.apply(answer({ start: 2, served: 3, total: 3, final: chunk({ evaluations: [evaluation(3002), evaluation(3003)] }), tail: null }));
  const after = Array.from(t.cols.k.subarray(0, t.n)).slice(-4);
  check('rows after thinning are numbered on, the tail replaced as before', same(after, [3000, 3001, 3002, 3003]), JSON.stringify(after));
  setCaps({ evaluations: 50000, updates: 200000 });
}

// ---- 7. several runs on one chart (record 7.200) ---------------------------------------------------------------------------
{
  const gainDefs = { gain_vv: { unit: 'V/V', threshold_lower: 400, threshold_upper: null, hard: true } };
  const run = (name, n, gainOf, extra = {}) => {
    const store = new TrainingStore(name);
    const rows = Array.from({ length: n }, (_, i) => evaluation(i + 1, { phase: i % 5 === 0 ? (i ? 'episode_reset' : 'baseline') : 'search', reward: i % 5 === 0 ? null : gainOf(i + 1) / 1000 }));
    const specs = rows.map(r => ({ commit_seq: r.commit_seq, metric_name: extra.spec ?? 'gain_vv', raw_value: gainOf(r.commit_seq), satisfied: null, failure_reason: null }));
    const defs = extra.spec ? { [extra.spec]: { unit: extra.unit ?? 'V/V', threshold_lower: null, threshold_upper: null, hard: true } } : extra.unit ? { gain_vv: { ...gainDefs.gain_vv, unit: extra.unit } } : gainDefs;
    store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows, specs, defs, updates: extra.updates ?? [] }) }));
    return store;
  };
  const a = run('/a', 10, k => 300 + k), b = run('/b', 6, k => 100 + k), c = run('/c', 8, k => 50 + k, { spec: 'pm_deg', unit: 'deg' }), d = run('/d', 5, k => k, { unit: 'dB' });
  const built = buildCompare([{ store: a, label: 'A' }, { store: b, label: 'B' }, { store: c, label: 'C' }, { store: d, label: 'D' }], 'spec:gain_vv', 0, { mode: 'all' }, 800);
  const valuesOf2 = label => built.series.find(x => x.label === label)?.values;
  check('compared runs share one x axis: their evaluation numbers', same(built.x, [2, 3, 4, 5, 7, 8, 9, 10]), JSON.stringify(built.x));
  check('each run its own series, its recorded values at its own evaluations; episode starts left out',
    same(valuesOf2('A'), [302, 303, 304, 305, 307, 308, 309, 310]) && same(valuesOf2('B'), [102, 103, 104, 105, undefined, undefined, undefined, undefined]), JSON.stringify(built.series.map(x => [x.label, x.values])));
  check('each run its colour (run index); the first run\'s limits', built.series.find(x => x.label === 'A').run === 0 && built.series.find(x => x.label === 'B').run === 1
    && same(valuesOf2('lower limit (A)'), new Array(8).fill(400)));
  check('a run without the spec, and one whose spec has another unit, are named with the reason', built.missing.length === 2
    && /C/.test(built.missing[0].label) && /D/.test(built.missing[1].label) && /dB/.test(built.missing[1].reason), JSON.stringify(built.missing));
  check('no row of a comparison is named on hover (rows -1)', built.rows.every(r => r === -1));
  const smoothed = buildCompare([{ store: a, label: 'A' }, { store: b, label: 'B' }], 'reward', 2, { mode: 'all' }, 800);
  check('smoothing per run: its own recorded values under its own mean', same(smoothed.series.map(x => x.label), ['A (recorded)', 'A: mean of last 2', 'B (recorded)', 'B: mean of last 2'])
    && [0.102, (0.102 + 0.103) / 2, (0.103 + 0.104) / 2, (0.104 + 0.105) / 2].every((want, i) => Math.abs(smoothed.series[3].values[i] - want) < 1e-12),   // a running mean: rounding at 1e-17
    JSON.stringify(smoothed.series[3].values.slice(0, 4)));
  // branch record SIF-134: the line over a comparison names a value's run by its swatch, then the series' own words (`short`)
  check('...each series\' own words without its run\'s name, for the line over the chart (SIF-134)', same(smoothed.series.map(x => x.short), ['recorded', 'mean of last 2', 'recorded', 'mean of last 2'])
    && same(built.series.filter(x => x.run != null).map(x => x.short), ['', '']), JSON.stringify([smoothed.series.map(x => x.short), built.series.map(x => x.short)]));
  // learner charts: abandoned updates after a restart left out; two columns of one run, the second dashed
  const ups = [...Array.from({ length: 6 }, (_, i) => update(i + 1)), ...Array.from({ length: 4 }, (_, i) => update(i + 4, { critic_loss: 9 }))];
  const e = run('/e', 3, k => k, { updates: ups }), f = run('/f', 3, k => k, { updates: [update(1), update(2)] });
  const learner = buildCompare([{ store: e, label: 'E' }, { store: f, label: 'F' }], 'critic_loss', 0, { mode: 'all' }, 800);
  check('learner comparison: the line each learner went on, abandoned updates left out', same(learner.x, [1, 2, 3, 4, 5, 6, 7])
    && same(learner.series[0].values, [1, 1 / 2, 1 / 3, 9, 9, 9, 9]) && same(learner.series[1].values, [1, 1 / 2, undefined, undefined, undefined, undefined, undefined]), JSON.stringify(learner.series.map(x => x.values)));
  const grads = buildCompare([{ store: e, label: 'E' }, { store: f, label: 'F' }], 'grad_norm', 0, { mode: 'all' }, 800);
  check('two columns of one run: named, the second dashed', same(grads.series.map(x => [x.label, !!x.dash, x.run]), [['E / Critics', false, 0], ['E / Policy', true, 0], ['F / Critics', false, 1], ['F / Policy', true, 1]]));
  const gradsSmoothed = buildCompare([{ store: e, label: 'E' }, { store: f, label: 'F' }], 'grad_norm', 2, { mode: 'all' }, 800, 'evaluation');
  const columnWords = ['Critics (recorded)', 'Critics: mean of last 2 evaluations', 'Policy (recorded)', 'Policy: mean of last 2 evaluations'];
  check('...their own words name the column, as one run\'s chart does; one column\'s say only what the series is (SIF-134)', same(grads.series.map(x => x.short), ['Critics', 'Policy', 'Critics', 'Policy'])
    && same(gradsSmoothed.series.map(x => x.short), [...columnWords, ...columnWords]) && same(learner.series.map(x => x.short), ['', '']),
    JSON.stringify([grads.series.map(x => x.short), gradsSmoothed.series.map(x => x.short), learner.series.map(x => x.short)]));
}

// ---- audit regressions: feasible objective and bounded, incremental live rows -----------------------------------------
{
  const store = new TrainingStore('/fixture/objective'), objective = { metric: 'gain', direction: 'max' };
  const rows = [evaluation(1, { best_so_far_objective: 100 }), evaluation(2, { best_so_far_objective: 120, best_so_far_feasible: null })];
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows }), objective }));
  check('an infeasible or unknown best design cannot enable the feasible-objective chart', !catalog(store).find(c => c.id === 'objective').available);
  store.apply(answer({ start: 1, served: 2, total: 2, objective,
    final: chunk({ evaluations: [evaluation(3, { best_so_far_objective: 80, best_so_far_feasible: true })] }) }));
  check('objective plot masks infeasible values even from an older backend',
    same(build(store, 'objective', 0, { mode: 'all' }, 800).series[0].values, [null, null, 80]));
  check('objective comparison also masks infeasible values',
    same(buildCompare([{ store, label: 'A' }], 'objective', 0, { mode: 'all' }, 800).series[0].values, [null, null, 80]));
}
{
  const store = new TrainingStore('/fixture/paged');
  const page = (start, cursor, reset = false, more = false) => ({ start, cursor, reset, more });
  store.apply(answer({ served: 0, total: 0, final: chunk(), tail: chunk({ evaluations: [evaluation(1)], updates: [update(1)] }),
    tail_page: page(null, 'a', true, true) }));
  const second = answer({ served: 0, total: 0, final: chunk(), tail: chunk({ updates: [update(2)] }), tail_page: page('a', 'b', false, true) });
  store.apply(second);
  check('journal cursor pages append without replacing preceding pages', same(store.counts(), { evaluations: 1, updates: 2 })
    && store.finalEvaluations === 0 && store.finalUpdates === 0 && store.tailCursor === 'b');
  check('a repeated page at the same flush cursor is ignored', !store.apply(second) && store.counts().updates === 2);
  const specs = [{ commit_seq: 1, metric_name: 'gain', raw_value: 99, satisfied: true, failure_reason: null }];
  const changed = store.apply(answer({ served: 0, total: 0, final: chunk(), tail: chunk({ specs }), latest: 1, tail_page: page('b', 'c') }));
  check('a specs-only page joins to an evaluation on an earlier page and requests redraw', changed && store.evaluations.cols['spec:gain'][0] === 99);
  check('an unchanged incremental poll requests no redraw', !store.apply(answer({ served: 0, total: 0, final: chunk(), tail: chunk(), latest: 1, tail_page: page('c', 'c') })));
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: [evaluation(1)], updates: [update(1), update(2)], specs }),
    tail: chunk({ evaluations: [evaluation(2)] }), latest: 2, tail_page: page('c', 'd', true) }));
  check('publishing a paged tail removes its provisional rows before appending final rows',
    same(store.counts(), { evaluations: 2, updates: 2 }) && store.finalEvaluations === 1 && store.evaluations.n === 2);
  store.apply(answer({ start: 1, served: 1, total: 1, final: chunk(), tail: chunk(), latest: 1, complete: false, tail_page: page('d', null, true) }));
  check('a compaction race drops only the provisional data and clears the tail cursor',
    same(store.counts(), { evaluations: 1, updates: 2 }) && store.evaluations.n === 1 && store.tailCursor === null);
}
{
  const store = new TrainingStore('/fixture/large-live-tail');
  const n = data.UPDATE_CAP + 1;
  const updates = Array.from({ length: n }, (_, i) => update(i + 1));
  store.apply(answer({ served: 0, total: 0, final: chunk(), tail: chunk({ updates }), latest: 1 }));
  check('the actual 200,000-update cap also applies when nothing has flushed', store.updates.n <= data.UPDATE_CAP
    && store.thinnedUpdates > 0 && store.finalUpdates === 0, `${store.updates.n} retained of ${n}`);
  check('thinning a live tail keeps exact recorded counts and the newest update', store.counts().updates === n && store.updates.cols.cum[store.updates.n - 1] === n);
}
{
  setCaps({ evaluations: 2000, updates: 2000 });
  const store = new TrainingStore('/fixture/thinned-paged');
  const rows = Array.from({ length: 3000 }, (_, i) => evaluation(i + 1, { episode_id: `episode-${i + 1}` }));
  const updates = Array.from({ length: 3000 }, (_, i) => update(i + 1));
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows.slice(0, 1000), updates: updates.slice(0, 1000) }),
    tail: chunk({ evaluations: rows.slice(1000), updates: updates.slice(1000) }), latest: 3000,
    tail_page: { start: null, cursor: 'first', reset: true, more: false } }));
  check('both row limits cover final rows plus journal rows', store.evaluations.n <= 2000 && store.updates.n <= 2000
    && same(store.counts(), { evaluations: 3000, updates: 3000 }));
  check('thinning also releases unused word dictionary entries', store.words.episode.list.length === store.evaluations.n);
  store.apply(answer({ start: 1, served: 1, total: 1, final: chunk(), tail: chunk({ evaluations: [evaluation(3001)], updates: [update(3001)] }), latest: 3001,
    tail_page: { start: 'first', cursor: 'second', reset: false, more: false } }));
  check('incremental appends after tail thinning keep original evaluation numbers', store.evaluations.cols.k[store.evaluations.n - 1] === 3001
    && same(store.counts(), { evaluations: 3001, updates: 3001 }));
  store.apply(answer({ start: 1, served: 2, total: 2, final: chunk({ evaluations: [...rows.slice(1000), evaluation(3001)], updates: [...updates.slice(1000), update(3001)] }),
    tail: chunk({ evaluations: [evaluation(3002)] }), latest: 3002, tail_page: { start: 'second', cursor: 'third', reset: true, more: false } }));
  const t = store.evaluations, seqs = Array.from(t.cols.seq.subarray(0, t.n));
  check('a later flush replaces a thinned tail without duplicates or misnumbering', new Set(seqs).size === t.n
    && seqs.every((seq, i) => seq === t.cols.k[i]) && same(store.counts(), { evaluations: 3002, updates: 3001 }));
  check('the row limits still hold after flushing a thinned tail', t.n <= 2000 && store.updates.n <= 2000);
  setCaps({ evaluations: 50000, updates: 200000 });
}

// ---- 8. learner charts by evaluation (record 7.213) -------------------------------------------------------------------------
{
  check('a mean over the last N x units: gaps kept, rows of other series skipped, rows at one x counted in order',
    same(smoothOver([1, 1, 2, 3, 3], [1, null, 3, undefined, 5], 1), [1, null, 3, undefined, 5])
    && same(smoothOver([1, 1, 2, 3, 3], [1, null, 3, undefined, 5], 2), [1, null, 2, undefined, 4])
    && same(smoothOver([9, 9, 9, 10], [1, 2, 3, 4], 1), [1, 1.5, 2, 4]));
  // 8 updates after each of the evaluations 9, 10 and 11 (as the starting presets learn), one learner line
  const eight = Array.from({ length: 24 }, (_, i) => update(i + 1, { evaluations_collected: 9 + Math.floor(i / 8), actor_loss: (i + 1) * 10 }));
  const store = new TrainingStore('/fixture/eight');
  store.apply(answer({ served: 1, total: 1, final: chunk({ updates: eight }) }));
  const byUpdate = build(store, 'actor_loss', 0, { mode: 'all' }, 800), byEvaluation = build(store, 'actor_loss', 0, { mode: 'all' }, 800, {}, 'evaluation');
  check('by update (the default): x = the update count, as before', same(byUpdate.x, eight.map(u => u.cumulative_updates)));
  check('by evaluation: x = the evaluations collected, 8 updates at each', same(byEvaluation.x, eight.map(u => u.evaluations_collected)) && same(byEvaluation.extent, [9, 11]),
    JSON.stringify(byEvaluation.x));
  check('by evaluation: every value is its recorded row\'s, in update order; the rows named', same(valuesOf(byEvaluation, 'Actor loss'), eight.map(u => u.actor_loss))
    && same(byEvaluation.rows, eight.map((_, i) => i)));
  const mean = build(store, 'actor_loss', 2, { mode: 'all' }, 800, {}, 'evaluation');
  const smoothLine = mean.series.find(x => x.role === 'smooth');
  const avg = list => list.reduce((a, b) => a + b, 0) / list.length;
  check('by evaluation the mean is over the updates of the last N evaluations, and says so', smoothLine.label === 'Actor loss: mean of last 2 evaluations'
    && smoothLine.values[16] === avg([...Array.from({ length: 8 }, (_, i) => (i + 9) * 10), 170]) && smoothLine.values[23] === avg(Array.from({ length: 16 }, (_, i) => (i + 9) * 10)),
    JSON.stringify([smoothLine.label, smoothLine.values[16], smoothLine.values[23]]));
  check('by update the mean stays over the last N updates', build(store, 'actor_loss', 2, { mode: 'all' }, 800).series.find(x => x.role === 'smooth').label === 'Actor loss: mean of last 2');
  // a restart: the learner went back to its save point (update 5) while the evaluations went on (11 onwards)
  const first = Array.from({ length: 10 }, (_, i) => update(i + 1, { evaluations_collected: i + 1 }));
  const second = Array.from({ length: 7 }, (_, i) => update(i + 6, { evaluations_collected: 11 + i, actor_loss: 100 + i }));
  const restarted = new TrainingStore('/fixture/restart');
  restarted.apply(answer({ served: 1, total: 1, final: chunk({ updates: [...first, ...second] }) }));
  const r = build(restarted, 'actor_loss', 0, { mode: 'all' }, 800, {}, 'evaluation');
  check('by evaluation after a restart: the line goes on at the evaluations it learned after, the abandoned updates apart',
    same(r.x, [...first.map(u => u.evaluations_collected), ...second.map(u => u.evaluations_collected)])
    && same(valuesOf(r, 'Actor loss').filter(v => v !== undefined), [...first.slice(0, 5), ...second].map(u => u.actor_loss))
    && same(valuesOf(r, 'Actor loss: abandoned at a restart').filter(v => v !== undefined), first.slice(5).map(u => u.actor_loss)), JSON.stringify(r.x));
  check('by evaluation the restart is marked at the evaluation it went on from', r.markers.some(m => m.kind === 'restart' && m.x === 11) && !r.markers.some(m => m.kind === 'restart' && m.x === 6));
  // two runs: 8 updates per evaluation and 1 (the old defaults) line up by evaluation
  const one = new TrainingStore('/fixture/one');
  one.apply(answer({ served: 1, total: 1, final: chunk({ updates: [9, 10, 11, 12].map((c, i) => update(i + 1, { evaluations_collected: c, actor_loss: -c })) }) }));
  const both = buildCompare([{ store, label: 'P' }, { store: one, label: 'Q' }], 'actor_loss', 0, { mode: 'all' }, 800, 'evaluation');
  const q = both.series.find(x => x.label === 'Q').values, pv = both.series.find(x => x.label === 'P').values;
  check('compared by evaluation: each x as often as the run that has it most often; the runs share its slots',
    same(both.x, [...new Array(8).fill(9), ...new Array(8).fill(10), ...new Array(8).fill(11), 12]) && same(pv.slice(0, 24), eight.map(u => u.actor_loss)) && pv[24] === undefined
    && same(q.map((v, i) => [v, i]).filter(([v]) => v !== undefined), [[-9, 0], [-10, 8], [-11, 16], [-12, 24]]), JSON.stringify(both.x));
  const byCount = buildCompare([{ store, label: 'P' }, { store: one, label: 'Q' }], 'actor_loss', 0, { mode: 'all' }, 800);
  check('compared by update: as before, one slot per count', same(byCount.x, eight.map(u => u.cumulative_updates)) && same(byCount.series[1].values.slice(0, 5), [-9, -10, -11, -12, undefined]));
  const blank = new TrainingStore('/fixture/no-count');
  blank.apply(answer({ served: 1, total: 1, final: chunk({ updates: [update(1, { evaluations_collected: null }), update(2, { evaluations_collected: null })] }) }));
  check('a run without the evaluation count is named, not drawn at 0', (() => {
    const c = buildCompare([{ store, label: 'P' }, { store: blank, label: 'B' }], 'actor_loss', 0, { mode: 'all' }, 800, 'evaluation');
    const alone = build(blank, 'actor_loss', 0, { mode: 'all' }, 800, {}, 'evaluation');
    return c.missing.length === 1 && c.missing[0].label === 'B' && /no evaluation count/.test(c.missing[0].reason) && !c.series.some(x => x.label === 'B')
      && alone.x.length === 0 && /no evaluation count/.test(alone.missing?.[0]?.reason ?? '');
  })());
}

// ---- 9. key numbers (record 7.215) -------------------------------------------------------------------------------------------
{
  // 300 evaluations: every 5th an episode start (passing, to be left out), every 41st a timeout (no verdict); designs pass from 120 on
  const rows = Array.from({ length: 300 }, (_, i) => {
    const k = i + 1, start = (k - 1) % 5 === 0;
    return evaluation(k, { phase: start ? (k === 1 ? 'baseline' : 'episode_reset') : 'search', status: k % 41 === 0 ? 'timeout' : 'ok',
      all_hard_constraints_satisfied: start || (k >= 120 && k % 3 !== 0), best_so_far_violation: k >= 120 ? 0 : 0.5 - k / 1000 });
  });
  const updates = Array.from({ length: 290 * 2 }, (_, i) => update(i + 1, { evaluations_collected: 11 + Math.floor(i / 2), mean_log_prob: -5 + i / 50, alpha: 0.01 / (1 + i / 100) }));
  const store = new TrainingStore('/fixture/keys');
  store.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows, updates }) }));
  const k = keyNumbers(store);
  const design = r => r.phase === 'search' && r.status === 'ok';
  const firstPass = rows.find(r => design(r) && r.all_hard_constraints_satisfied).commit_seq;
  const last = rows.filter(r => r.commit_seq > 300 - RECENT && design(r));
  check('first passing design: the first design that met every hard spec, episode starts left out', k.firstPass === firstPass && firstPass === 122, String(k.firstPass));
  // branch record SIF-116: Run status's first feasible design counts the episode starts, so a start that passed before it is named
  check('...and the episode start that passed before it: the baseline, evaluation 1 (SIF-116)', k.startPassed === 1, String(k.startPassed));
  const later = new TrainingStore('/fixture/keys-later');
  later.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows.map(r => (r.phase === 'search' ? r : { ...r, all_hard_constraints_satisfied: r.commit_seq > firstPass })) }) }));
  const l = keyNumbers(later);
  check('...none when the episode starts passed only after the first passing design', l.firstPass === firstPass && l.startPassed === null, JSON.stringify([l.firstPass, l.startPassed]));
  check(`passing of the last ${RECENT} evaluations: designs with a verdict only (no episode start, no timeout)`,
    same(k.recent, { passed: last.filter(r => r.all_hard_constraints_satisfied).length, judged: last.length, from: 201, to: 300 }), JSON.stringify(k.recent));
  check('the best design\'s miss at the newest evaluation, and the recorded count', k.bestMiss === 0 && k.evaluations === 300);
  const mean = (list, f) => list.reduce((a, u) => a + f(u), 0) / list.length;
  const head = updates.filter(u => u.evaluations_collected <= 11 + ENDS - 1), tail = updates.filter(u => u.evaluations_collected >= 300 - ENDS + 1);
  check(`entropy estimate and α: the means of the updates of the first and the last ${ENDS} evaluations it learned at`,
    Math.abs(k.entropy[0] - mean(head, u => -u.mean_log_prob)) < 1e-9 && Math.abs(k.entropy[1] - mean(tail, u => -u.mean_log_prob)) < 1e-9
    && Math.abs(k.alpha[0] - mean(head, u => u.alpha)) < 1e-12 && Math.abs(k.alpha[1] - mean(tail, u => u.alpha)) < 1e-12, JSON.stringify([k.entropy, k.alpha]));
  check('a calibrating baseline learns nothing: no learner numbers', keyNumbers(store, { calibration: true }).entropy === null);
  const none = new TrainingStore('/fixture/none');
  none.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: rows.slice(0, 50).map(r => ({ ...r, all_hard_constraints_satisfied: r.phase !== 'search' })) }) }));
  const n = keyNumbers(none);
  check('no passing design yet, no learner: said as none, not as 0', n.firstPass === null && n.entropy === null && n.alpha === null && n.recent.passed === 0 && n.recent.from === 1,
    JSON.stringify(n));
  check('...its passing episode start still named, the baseline at evaluation 1 (SIF-116)', n.startPassed === 1, String(n.startPassed));
  check('an empty run: nothing but the count', same(keyNumbers(new TrainingStore('/fixture/empty')), { evaluations: 0, firstPass: null, startPassed: null, recent: null, bestMiss: null, entropy: null, alpha: null }));
}

// ---- 10. shared chart preparation (record 7.221) ------------------------------------------------------------------------------
// What the charts derive from a run's rows is kept per run and brought up to date as rows arrive. The charts must draw the very
// same numbers: compared exactly (a number by Object.is: -0 is not 0; the same keys, the same order of values), never "close".
{
  // the trainingData.ts before record 7.221, when given: imported from a folder of its own (node needs a package.json there)
  const referencePath = option('--reference') ?? process.env.TRAINING_DATA_REFERENCE ?? null;
  let reference = null;
  if (referencePath) {                                             // once imported, the copy is not needed any more
    const referenceDir = mkdtempSync(path.join(tmpdir(), 'gator-training-reference-'));
    try {
      copyFileSync(referencePath, path.join(referenceDir, 'trainingData.ts'));
      const parts = path.join(path.dirname(referencePath), 'training');      // its parts, since plan-refactoring C12
      if (existsSync(parts)) cpSync(parts, path.join(referenceDir, 'training'), { recursive: true });
      writeFileSync(path.join(referenceDir, 'package.json'), '{ "type": "module" }\n');
      reference = await import(pathToFileURL(path.join(referenceDir, 'trainingData.ts')).href);
    } finally { rmSync(referenceDir, { recursive: true, force: true }); }
  }
  /** The first difference of two values, or null. */
  const differ = (a, b, where = '') => {
    if (typeof a !== typeof b) return `${where}: ${typeof a} vs ${typeof b} (${String(a)} vs ${String(b)})`;
    if (typeof a === 'number') return Object.is(a, b) ? null : `${where}: ${a} vs ${b}`;
    if (a === null || b === null || typeof a !== 'object') return a === b ? null : `${where}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`;
    if (Array.isArray(a) !== Array.isArray(b)) return `${where}: array vs object`;
    if (Array.isArray(a)) {
      if (a.length !== b.length) return `${where}: length ${a.length} vs ${b.length}`;
      for (let i = 0; i < a.length; i++) { const d = differ(a[i], b[i], `${where}[${i}]`); if (d) return d; }
      return null;
    }
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    if (ka.join() !== kb.join()) return `${where}: keys ${ka.join()} vs ${kb.join()}`;
    for (const key of ka) { const d = differ(a[key], b[key], `${where}.${key}`); if (d) return d; }
    return null;
  };
  const random = seed => { let s = (seed * 2654435761) >>> 0 || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; };
  const viewFor = (rnd, extent) => {
    const [a, b] = extent ?? [1, 10], span = Math.max(1, b - a), pick = rnd();
    if (pick < 0.4) return { mode: 'all' };
    if (pick < 0.7) return { mode: 'follow', width: Math.max(1, Math.round(span * rnd() * 0.6)) };
    const lo = Math.round((a - span * 0.1 + rnd() * span * 1.1) * 10) / 10;
    return { mode: 'fixed', min: lo, max: lo + Math.max(0.5, Math.round(rnd() * span * 5) / 10) };
  };
  /** Every chart (twice, with random smoothing, view, width, learner x and calibration), the catalog and the key numbers of
   *  each pair (store, other: another module's store or a store fed the same answers at once), then comparisons of 1-4 runs.
   *  Returns [comparisons, first difference or null]. */
  const compareAll = (rnd, pairs) => {
    let count = 0, first = null;
    const note = (what, d) => { count += 1; if (d && !first) first = `${what}: ${d}`; };
    for (const { store, other, module } of pairs) {
      for (const context of [{}, { calibration: true }]) {
        note('catalog', differ(catalog(store, context), module.catalog(other, context)));
        // startPassed came after the builders before 7.221 (branch record SIF-116): compared where both modules give it
        const mine = keyNumbers(store, context), theirs = module.keyNumbers(other, context);
        if (!('startPassed' in theirs)) delete mine.startPassed;
        note('key numbers', differ(mine, theirs));
      }
      for (const id of [...catalog(store).map(c => c.id), 'no_such_chart']) for (let c = 0; c < 2; c++) {
        const smoothing = [0, 10, 20, 50][Math.floor(rnd() * 4)], learnerX = rnd() < 0.5 ? 'update' : 'evaluation', buckets = [16, 20, 40, 800][Math.floor(rnd() * 4)];
        const context = rnd() < 0.15 ? { calibration: true } : {};
        const view = viewFor(rnd, module.build(other, id, smoothing, { mode: 'all' }, buckets, context, learnerX).extent);
        note(`${id} smoothing ${smoothing} ${JSON.stringify(view)} width ${buckets} by ${learnerX}`, differ(build(store, id, smoothing, view, buckets, context, learnerX),
          module.build(other, id, smoothing, view, buckets, context, learnerX)));
      }
    }
    for (let c = 0; c < 6 && pairs.length; c++) {
      const chosen = [...pairs].sort(() => rnd() - 0.5).slice(0, 1 + Math.floor(rnd() * Math.min(4, pairs.length))), module = chosen[0].module;
      const ids = catalog(chosen[0].store).map(x => x.id), id = rnd() < 0.05 ? 'no_such_chart' : ids[Math.floor(rnd() * ids.length)];
      const smoothing = [0, 10, 20][Math.floor(rnd() * 3)], learnerX = rnd() < 0.5 ? 'update' : 'evaluation', buckets = [16, 30, 800][Math.floor(rnd() * 3)];
      const context = rnd() < 0.15 ? { calibration: true } : undefined;
      const mine = chosen.map((p, i) => ({ store: p.store, label: `R${i}`, context: i ? undefined : context }));
      const theirs = chosen.map((p, i) => ({ store: p.other, label: `R${i}`, context: i ? undefined : context }));
      const view = viewFor(rnd, module.buildCompare(theirs, id, smoothing, { mode: 'all' }, buckets, learnerX).extent);
      // a compared series' own words (`short`) came after the builders before 7.221 (branch record SIF-134): compared where both
      // modules give them
      const ours = buildCompare(mine, id, smoothing, view, buckets, learnerX), theirsBuilt = module.buildCompare(theirs, id, smoothing, view, buckets, learnerX);
      if (!theirsBuilt.series.some(s => 'short' in s)) for (const s of ours.series) delete s.short;
      note(`${chosen.length} runs compared on ${id} smoothing ${smoothing} ${JSON.stringify(view)} width ${buckets} by ${learnerX}`, differ(ours, theirsBuilt));
    }
    return [count, first];
  };
  const fedAtOnce = (dir, answers) => { const store = new TrainingStore(dir); for (const a of answers) store.apply(a); return store; };

  // -- a random run as training_series.read_training answers it: history in flushes, then journal pages; spec values that come a
  //    page after their evaluation, journal rewrites, late answers; restarts of the learner (its count back, maybe the
  //    evaluations' too), resumes, counts of -0 and 0, missing counts and metrics, a spec appearing late, unused words
  const WORD_COLUMNS = new Set(['episode_id', 'phase', 'action_source', 'status', 'update_phase', 'metric_name', 'failure_reason']);
  const randomColumns = (rows, names, rnd) => {
    const out = { n: rows.length };
    for (const name of names) {
      const values = rows.map(r => (r[name] === undefined ? null : r[name]));
      if (!WORD_COLUMNS.has(name)) { out[name] = values; continue; }
      const words = rnd() < 0.2 ? ['unused-word'] : [];
      out[name] = { values: words, codes: values.map(v => (v === null ? -1 : words.includes(v) ? words.indexOf(v) : words.push(v) - 1)) };
    }
    return out;
  };
  const simulate = (seed, { learner = true, counts = 'yes', restarts = 0.02, specs = ['gain', 'pm'], frozen = false, zeros = false, decibels = false } = {}) => {
    const rnd = random(seed), pick = list => list[Math.floor(rnd() * list.length)], dir = `/fixture/random/${seed}`;
    const value = (p, scale = 1) => (rnd() < p ? null : (rnd() - 0.4) * scale);
    const e = [], u = [], s = [], flushes = [];
    let k = 0, cum = 0, collected = 0, lag = 0, late = false;
    let segments = [{ segment: 1, entry: 'start', started_utc: new Date(1.7e9 * 1000).toISOString(), ended_utc: null, end_state: null, stop_reason: null }];
    let served = 0, cursor = null, tailE = 0, tailU = 0, tailS = 0, tag = 0;
    const flushed = () => flushes[flushes.length - 1] ?? [0, 0, 0];
    const part = (e0, e1, u0, u1, s0, s1) => ({ evaluations: randomColumns(e.slice(e0, e1), EVALUATION, rnd), updates: randomColumns(u.slice(u0, u1), UPDATE, rnd),
      specs: randomColumns(s.slice(s0, s1), SPEC, rnd), spec_defs: Object.fromEntries([...specs, 'late_spec'].map((name, i) =>
        [name, { unit: i === 1 ? 'deg' : decibels ? 'dB' : 'V/V', threshold_lower: i === 0 ? 0 : null, threshold_upper: i === 1 ? 100 : null, hard: true }])) });
    const meta = () => ({ run_dir: dir, run_id: dir, mode: 'scratch', mock: true, objective: rnd() < 0.5 ? { metric: specs[0] ?? 'gain', direction: 'max' } : null,
      learner: learner ? { recorded: true, every: 1, reason: null } : { recorded: false, every: 1, reason: 'FIXTURE: no learner updates' }, segments });
    return {
      dir,
      grow(m) {
        for (let i = 0; i < m; i++) {
          k += 1;
          const start = k === 1 || rnd() < 0.15, t = 1.7e9 + k * 2 + (rnd() < 0.05 ? -3 : 0);
          const phase = start ? (k === 1 ? 'baseline' : pick(['episode_reset', 'episode_reset', 'preflight'])) : frozen ? pick(['frozen_eval', 'validation'])
            : k < 6 ? 'warmup' : rnd() < 0.08 ? pick(['frozen_eval', 'llm_search', 'adapt']) : 'search';
          e.push({ commit_seq: k + (rnd() < 0.02 ? 1000 : 0), completion_index: k, global_env_step: k, episode_id: `0-${Math.ceil(k / 5)}`, episode_step: k % 5, phase,
            action_source: start ? 'reset' : 'sac_policy', status: rnd() < 0.85 ? 'ok' : pick(['timeout', 'measurement_error', 'invalid_design', 'nonconverged', 'cancelled']),
            policy_version: null, reward: start ? null : value(0.1), valid: rnd() < 0.9 ? true : rnd() < 0.5 ? false : null,
            all_hard_constraints_satisfied: rnd() < 0.1 ? null : rnd() < 0.4, normalized_constraint_violation: value(0.15, 2), clearance_margin: rnd() < 0.3 ? null : value(0.1, 3),
            best_so_far_feasible: rnd() < 0.1 ? null : rnd() < 0.5, best_so_far_violation: value(0.1), execution_seconds: value(0.05, 10), committed_at: t,
            best_so_far_objective: value(0.3, 100) });
          for (const name of [...specs, ...(late ? ['late_spec'] : [])]) if (rnd() < 0.9) {
            const v = value(0.15, 500);
            s.push({ commit_seq: e[e.length - 1].commit_seq, metric_name: name, raw_value: v, satisfied: v === null ? null : v > 0,
              failure_reason: v === null ? pick(['missing_or_nonfinite', 'evaluation_status_timeout']) : null });
          }
          if (!late && rnd() < 0.01) late = true;
          if (learner && !start && k >= 4) for (let j = pick([0, 1, 1, 2, 8]); j > 0; j--) {
            // a restart: the count goes back; with 'back' the evaluations' count too, from then on `lag` behind
            if (rnd() < restarts && cum > 3) { cum = Math.max(0, cum - 1 - Math.floor(rnd() * 12)); if (counts === 'back') lag = 1 + Math.floor(rnd() * 4); }
            cum += 1; collected = Math.max(0, k - lag);
            const early = zeros && u.length < 6;
            u.push({ cumulative_updates: rnd() < 0.005 ? null : early && rnd() < 0.5 ? (rnd() < 0.5 ? -0 : 0) : cum,
              evaluations_collected: counts === 'none' ? null : early ? (rnd() < 0.5 ? -0 : 0) : rnd() < 0.01 ? null : collected,
              update_phase: rnd() < 0.5 ? null : 'learn', actor_loss: value(0.05), critic_loss: value(0.05, 3), alpha_loss: value(0.3), alpha: value(0.02, 0.1),
              mean_log_prob: value(0.05, 5), target_mean: value(0.05), critic_grad_norm: value(0.02, 4), actor_grad_norm: value(0.02, 4), updated_at: t + 0.5 });
          }
        }
      },
      resume() { segments = [...segments, { segment: segments.length + 1, entry: 'resume', started_utc: new Date((1.7e9 + k * 2 + 1) * 1000).toISOString(), ended_utc: null, end_state: null, stop_reason: null }]; },
      flush() { if (e.length > flushed()[0]) flushes.push([e.length, u.length, s.length]); },
      /** The answer to the page's next read: unread flushes first, then journal pages (or the journal again from its start). */
      next(rewrite) {
        const total = flushes.length;
        if (served < total) {
          const to = Math.min(total, served + 1 + Math.floor(rnd() * 3)), [e0, u0, s0] = flushes[served - 1] ?? [0, 0, 0], [e1, u1, s1] = flushes[to - 1];
          const answer = { ...meta(), flushes: { served: to, total, start: served }, final: part(e0, e1, u0, u1, s0, s1), tail: null, tail_complete: true, latest_seq: e.length,
            tail_page: { start: cursor, cursor: null, reset: true, more: false } };
          if (to === total) {
            const [fe, fu, fs] = flushed();
            tailE = Math.min(e.length, fe + Math.floor(rnd() * 4)); tailU = Math.min(u.length, fu + Math.floor(rnd() * 20)); tailS = Math.min(s.length, fs + Math.floor(rnd() * 6));
            answer.tail = part(fe, tailE, fu, tailU, fs, tailS);
            answer.tail_page = { start: cursor, cursor: `c${++tag}`, reset: true, more: tailE < e.length };
          }
          served = to; cursor = answer.tail_page.cursor;
          return answer;
        }
        const [fe, fu, fs] = flushed();
        if (rewrite || cursor === null) {
          tailE = Math.min(e.length, fe + Math.floor(rnd() * 6)); tailU = Math.min(u.length, fu + Math.floor(rnd() * 30)); tailS = Math.min(s.length, fs + Math.floor(rnd() * 8));
          const answer = { ...meta(), flushes: { served, total, start: served }, final: part(0, 0, 0, 0, 0, 0), tail: part(fe, tailE, fu, tailU, fs, tailS),
            tail_complete: rnd() < 0.9, latest_seq: e.length, tail_page: { start: cursor, cursor: `c${++tag}`, reset: true, more: tailE < e.length } };
          cursor = answer.tail_page.cursor;
          return answer;
        }
        const e1 = Math.min(e.length, tailE + Math.floor(rnd() * 5)), u1 = Math.min(u.length, tailU + Math.floor(rnd() * 40)), s1 = Math.min(s.length, tailS + Math.floor(rnd() * 12));
        const answer = { ...meta(), flushes: { served, total, start: served }, final: part(0, 0, 0, 0, 0, 0), tail: part(tailE, e1, tailU, u1, tailS, s1),
          tail_complete: true, latest_seq: e.length, tail_page: { start: cursor, cursor: `c${++tag}`, reset: false, more: e1 < e.length } };
        tailE = e1; tailU = u1; tailS = s1; cursor = answer.tail_page.cursor;
        return answer;
      },
    };
  };
  /** One random scenario: 1-4 runs read side by side, the charts compared at random steps. Returns a line for the check. */
  const scenario = seed => {
    // two random streams: the runs (the same for a seed, with or without the old builders) and which charts a frame compares
    const rnd = random(seed * 7 + 1), sample = random(seed * 7 + 3), profile = ['normal', 'normal', 'restarts', 'quiet', 'zeros'][Math.floor(rnd() * 5)];
    const spacing = [1, 2, 3, 7, 16, 64, 4096][Math.floor(rnd() * 7)];
    const caps = profile === 'restarts' || rnd() < 0.4 ? { evaluations: 64 + Math.floor(rnd() * 200), updates: 64 + Math.floor(rnd() * 600) } : { evaluations: 50000, updates: 200000 };
    data.setSpacing(spacing); setCaps(caps); reference?.setCaps(caps);
    const runs = Array.from({ length: 1 + Math.floor(rnd() * 4) }, (_, r) => simulate(seed * 10 + r, profile === 'restarts'
      ? { counts: rnd() < 0.7 ? 'back' : 'yes', restarts: 0.02 + rnd() * 0.06 }
      : { learner: rnd() < 0.9, counts: rnd() < 0.15 ? 'none' : rnd() < 0.3 ? 'back' : 'yes', restarts: rnd() < 0.5 ? 0 : rnd() * 0.05,
        specs: rnd() < 0.15 ? [] : ['gain', 'pm'], frozen: rnd() < 0.1, zeros: profile === 'zeros', decibels: rnd() < 0.2 }));
    const pairs = runs.map(run => ({ run, store: new TrainingStore(run.dir), old: reference && new reference.TrainingStore(run.dir), answers: [] }));
    let warmCold = 0, againstOld = 0, firstDifference = null;
    for (let step = 0, steps = 25 + Math.floor(rnd() * 40); step < steps; step++) {
      for (const pair of pairs) {
        const what = rnd();
        if (what < 0.5) pair.run.grow(1 + Math.floor(rnd() * 12));
        else if (what < 0.65) { pair.run.grow(Math.floor(rnd() * 6)); pair.run.flush(); }
        else if (what < 0.68) pair.run.resume();
        else if (what < 0.7) pair.run.grow(40 + Math.floor(rnd() * 120));
        // quiet: many reads between two frames, more changes than a reader remembers (Changes keeps 64)
        const reads = profile === 'quiet' && rnd() < 0.15 ? 70 + Math.floor(rnd() * 30) : rnd() < 0.3 ? 0 : 1 + Math.floor(rnd() * 3);
        for (let i = 0; i < reads; i++) {
          if (reads > 10 && rnd() < 0.5) { pair.run.grow(1 + Math.floor(rnd() * 3)); if (rnd() < 0.5) pair.run.flush(); }
          const answer = pair.run.next(rnd() < (reads > 10 ? 0.3 : 0.05));
          const applied = pair.store.apply(answer);
          if (pair.old && pair.old.apply(answer) !== applied && !firstDifference) firstDifference = `step ${step}: apply answered differently`;
          pair.answers.push(answer);
          if (rnd() < 0.05) { const stale = { ...answer, flushes: { ...answer.flushes, start: answer.flushes.start - 1 } }; pair.store.apply(stale); pair.old?.apply(stale); pair.answers.push(stale); }
        }
      }
      if (rnd() < 0.6) {               // a frame: against the old builders if given, against stores fed every answer at once
        if (reference) { const [n, d] = compareAll(sample, pairs.map(p => ({ store: p.store, other: p.old, module: reference }))); againstOld += n; if (d && !firstDifference) firstDifference = `step ${step}, old builders: ${d}`; }
        const [n, d] = compareAll(sample, pairs.map(p => ({ store: p.store, other: fedAtOnce(p.run.dir, p.answers), module: data })));
        warmCold += n; if (d && !firstDifference) firstDifference = `step ${step}, fed at once: ${d}`;
      }
    }
    data.setSpacing(4096); setCaps({ evaluations: 50000, updates: 200000 }); reference?.setCaps({ evaluations: 50000, updates: 200000 });
    const sizes = pairs.map(p => `${p.store.counts().evaluations}/${p.store.counts().updates}${p.store.thinnedEvaluations || p.store.thinnedUpdates ? ' thinned' : ''}`).join(', ');
    return { line: `random runs ${seed} (${profile}, checkpoints every ${spacing}; evaluations/updates ${sizes})`, warmCold, againstOld, firstDifference };
  };

  // -- the record of changes: a reader gets the first row that may differ, one that missed too many starts again
  const changes = new data.Changes(), seen = changes.stamp;
  changes.note(5); changes.note(3); changes.note(9);
  check('Changes: a reader that missed several changes gets the lowest first row; an up-to-date one none', changes.since(seen) === 3 && changes.since(changes.stamp) === Infinity
    && changes.since(changes.stamp - 1) === 9);
  for (let i = 0; i < 64; i++) changes.note(100);
  check('Changes: a reader that missed more changes than are kept starts again from row 0', changes.since(seen) === 0 && changes.since(changes.stamp - 64) === 100);
  const truncated = new TrainingStore('/fixture/cut');
  truncated.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: [1, 2, 3].map(s => evaluation(s)) }), tail: chunk({ evaluations: [4, 5].map(s => evaluation(s)) }) }));
  const stamp = truncated.evaluations.changes.stamp;
  truncated.apply(answer({ start: 1, served: 2, total: 2, final: chunk({ evaluations: [4, 5, 6].map(s => evaluation(s)) }) }));
  check('a new flush notes where its rows replace the provisional ones', truncated.evaluations.changes.since(stamp) === 3, String(truncated.evaluations.changes.since(stamp)));

  // -- stores at the edges, each compared against a store fed the same answers at once (and the old builders, if given)
  const edge = (name, make) => {
    const answers = make(), store = new TrainingStore(`/fixture/edge/${name}`), old = reference && new reference.TrainingStore(`/fixture/edge/${name}`);
    const rnd = random(name.length * 31 + answers.length);
    let n = 0, first = null;
    for (const a of answers) {
      store.apply(a); old?.apply(a);
      const [c1, d1] = compareAll(rnd, [{ store, other: fedAtOnce(store.runDir, answers.slice(0, answers.indexOf(a) + 1)), module: data }]);
      n += c1; first ??= d1;
      if (old) { const [c2, d2] = compareAll(rnd, [{ store, other: old, module: reference }]); n += c2; first ??= d2; }
    }
    check(`kept up to date = derived at once${reference ? ' = the builders before 7.221' : ''}: ${name}`, first === null, first ?? `${n} comparisons`);
    return store;
  };
  // a restart arrives in the journal, then its flush replaces it: what it marked abandoned is derived again
  edge('a learner restart in the journal, then flushed', () => {
    const first = Array.from({ length: 40 }, (_, i) => update(i + 1, { evaluations_collected: 1 + Math.floor(i / 4) }));
    const again = Array.from({ length: 30 }, (_, i) => update(31 + i, { evaluations_collected: 11 + Math.floor(i / 4), actor_loss: 5 + i }));
    const rows = Array.from({ length: 20 }, (_, i) => evaluation(i + 1));
    return [answer({ served: 1, total: 1, final: chunk({ evaluations: rows.slice(0, 10), updates: first }), tail: chunk({ evaluations: rows.slice(10, 15), updates: again.slice(0, 10) }), tail_page: { start: null, cursor: 'a', reset: true, more: false } }),
      answer({ start: 1, served: 1, total: 1, final: chunk(), tail: chunk({ evaluations: rows.slice(15), updates: again.slice(10, 20) }), tail_page: { start: 'a', cursor: 'b', reset: false, more: false } }),
      answer({ start: 1, served: 2, total: 2, final: chunk({ evaluations: rows.slice(10), updates: again.slice(0, 20) }), tail: chunk({ updates: again.slice(20) }), tail_page: { start: 'b', cursor: 'c', reset: true, more: false } }),
      answer({ start: 2, served: 2, total: 2, final: chunk(), tail: null, complete: false, tail_page: { start: 'c', cursor: null, reset: true, more: false } })];
  });
  // evaluations collected going back at a restart: the learner's rows by evaluation sorted; then thinned
  edge('evaluation counts going back, sorted, then thinned', () => {
    setCaps({ updates: 64 }); reference?.setCaps({ updates: 64 });
    const ups = [...Array.from({ length: 50 }, (_, i) => update(i + 1, { evaluations_collected: 10 + i })), ...Array.from({ length: 50 }, (_, i) => update(41 + i, { evaluations_collected: 40 + i }))];
    return [answer({ served: 1, total: 1, final: chunk({ evaluations: Array.from({ length: 30 }, (_, i) => evaluation(i + 1)), updates: ups.slice(0, 70) }) }),
      answer({ start: 1, served: 2, total: 2, final: chunk({ updates: ups.slice(70) }) })];
  });
  setCaps({ evaluations: 50000, updates: 200000 }); reference?.setCaps({ evaluations: 50000, updates: 200000 });
  // a spec value that joins an evaluation of an earlier page: that row's value, its mean and the spec's availability change
  edge('a spec value joining an earlier page', () => [
    answer({ served: 0, total: 0, final: chunk(), tail: chunk({ evaluations: [1, 2, 3, 4].map(s => evaluation(s)), specs: [1, 2].map(s => ({ commit_seq: s, metric_name: 'gain', raw_value: 10 * s, satisfied: true, failure_reason: null })) }),
      tail_page: { start: null, cursor: 'a', reset: true, more: true } }),
    answer({ served: 0, total: 0, final: chunk(), tail: chunk({ specs: [3, 4].map(s => ({ commit_seq: s, metric_name: 'gain', raw_value: -5 * s, satisfied: false, failure_reason: null })) }),
      tail_page: { start: 'a', cursor: 'b', reset: false, more: false } })]);
  // counts of -0 and 0 are one x (a comparison's x axis says 0)
  const zero = edge('counts of -0 and 0', () => [answer({ served: 1, total: 1, final: chunk({ evaluations: [1, 2].map(s => evaluation(s)),
    updates: [update(1, { evaluations_collected: -0 }), update(2, { evaluations_collected: 0 }), update(3, { evaluations_collected: 1 })] }) })]);
  const zeros = buildCompare([{ store: zero, label: 'Z' }], 'actor_loss', 0, { mode: 'all' }, 800, 'evaluation');
  check('a comparison by evaluation: counts -0 and 0 share the slots of x 0, written 0', same(zeros.x, [0, 0, 1]) && Object.is(zeros.x[0], 0) && Object.is(zeros.extent[0], 0), JSON.stringify(zeros.x));
  // the newer half of a thinned learner history without evaluation counts: by evaluation only thinned rows have an x
  edge('a thinned history whose newer updates have no evaluation count', () => {
    setCaps({ updates: 64 }); reference?.setCaps({ updates: 64 });
    return [answer({ served: 1, total: 1, final: chunk({ evaluations: [evaluation(1)], updates: Array.from({ length: 90 }, (_, i) => update(i + 1, { evaluations_collected: i < 40 ? 1 + i : null })) }) })];
  });
  setCaps({ evaluations: 50000, updates: 200000 }); reference?.setCaps({ evaluations: 50000, updates: 200000 });

  // -- random runs: every chart of every run, the key numbers, comparisons of 1-4 runs, at random steps
  const seeds = Number(option('--seeds', process.env.TRAINING_DATA_SEEDS ?? 12));
  for (let seed = 1; seed <= seeds; seed++) {
    const { line, warmCold, againstOld, firstDifference } = scenario(seed);
    check(`${line}: kept up to date = derived at once${reference ? ' = the builders before 7.221' : ''}`, firstDifference === null && warmCold > 0,
      firstDifference ?? `${warmCold} charts and key numbers compared${reference ? `, ${againstOld} against the old builders` : ''}`);
  }
  if (!reference) console.log('INFO  the builders before record 7.221 were not compared: give --reference <their trainingData.ts> (git show c170802:frontend/src/panels/trainingData.ts)');

  // -- the screen thinning cannot loop on an x that is not a number (before 7.221 it never ended)
  const xs = Array.from({ length: 200 }, (_, i) => (i === 50 ? NaN : i + 1));
  check('decimate: a row whose x is not a number is a pixel column of its own', decimate(xs, [xs.map(v => v)], 0, 200, 1, 200, 16).includes(50));

  // -- bounded and released: the running means kept per run are capped; a store's preparation goes with the store
  const big = new TrainingStore('/fixture/bounded');
  big.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: Array.from({ length: 300 }, (_, i) => evaluation(i + 1, { phase: i % 3 ? 'search' : 'frozen_eval' })),
    updates: Array.from({ length: 900 }, (_, i) => update(i + 1, { evaluations_collected: 1 + Math.floor(i / 3) })) }) }));
  for (const smoothing of [10, 20, 50, 100, 200]) for (const learnerX of ['update', 'evaluation']) for (const { id } of catalog(big)) build(big, id, smoothing, { mode: 'all' }, 800, {}, learnerX);
  const size = data.preparedSize(big);
  check('the running means kept per run are capped (the least recently used go): 48', size.means === 48 && size.indexes <= 8, JSON.stringify(size));
  setCaps({ evaluations: 64, updates: 128 });
  big.apply(answer({ start: 1, served: 2, total: 2, final: chunk({ evaluations: [evaluation(301)], updates: [update(901, { evaluations_collected: 301 })] }) }));
  for (const { id } of catalog(big)) build(big, id, 20, { mode: 'all' }, 800);
  const thinned = data.preparedSize(big);
  setCaps({ evaluations: 50000, updates: 200000 });
  check('after thinning the preparation shrinks with the rows it holds', thinned.bytes < size.bytes, `${size.bytes} -> ${thinned.bytes} bytes`);
  v8.setFlagsFromString('--expose-gc');
  const gc = vm.runInNewContext('gc');
  let collected = 0;
  const registry = new FinalizationRegistry(() => { collected += 1; });
  (() => {                                                        // a run shown, then another chosen: the first store is dropped
    const gone = new TrainingStore('/fixture/gone');
    gone.apply(answer({ served: 1, total: 1, final: chunk({ evaluations: [1, 2, 3].map(s => evaluation(s)), updates: [update(1), update(2)] }) }));
    for (const { id } of catalog(gone)) build(gone, id, 20, { mode: 'all' }, 800);
    keyNumbers(gone); buildCompare([{ store: gone, label: 'G' }, { store: big, label: 'B' }], 'critic_loss', 20, { mode: 'all' }, 800);
    registry.register(gone, 'store');
  })();
  for (let i = 0; i < 20 && !collected; i++) { gc(); await new Promise(r => setTimeout(r, 20)); }
  check('a store no longer shown is collected with its chart preparation (nothing else holds it)', collected === 1);
}

console.log(failed ? `${failed} of ${passed + failed} check(s) FAILED` : `all ${passed} checks passed`);
process.exit(failed ? 1 : 0);
