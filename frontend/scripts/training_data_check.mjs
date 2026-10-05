// Check of the Training tab's arithmetic (record 7.193): frontend/src/panels/trainingData.ts, imported AS IT IS - Windows
// node (>= 22.18) strips its types - and fed answers shaped like GET /api/runs/training (backend training_series.py). No
// browser and no backend: what is checked is that the numbers a chart gets are the numbers the run recorded.
//   - every value a series carries equals the value of its recorded row; a missing value is a gap (null), never 0;
//     a row of another category is `undefined` (uPlot draws across it, not a gap)
//   - the journal tail is replaced by every answer: a bundle flushed later is never counted twice; a late answer is ignored
//   - smoothing = a trailing mean of the last N recorded values; gaps are kept
//   - thinning for the screen (decimate) keeps every pixel column's first/last row and each series' extremes and first gap
//   - learner counter resets (resume from an older save point): the abandoned updates are a series of their own
//   - the memory bound thins the oldest half, keeps every spike, and keeps evaluation numbers and order intact
// Run: "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/training_data_check.mjs)"   (about 1 s)
import { fileURLToPath } from 'node:url';

const data = await import(new URL('../src/panels/trainingData.ts', import.meta.url).href);
const { TrainingStore, build, buildCompare, catalog, decimate, smooth, updateBranches, viewRange, setCaps, passFlags } = data;
if (fileURLToPath(import.meta.url) && !TrainingStore) throw new Error('trainingData.ts did not load');

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

// ---- 3. smoothing --------------------------------------------------------------------------------------------------------
{
  const raw = [1, 2, null, 3, undefined, 4, 10];
  check('trailing mean of the last 2 recorded values; a gap stays a gap; another category stays undefined',
    same(smooth(raw, 2), [1, 1.5, null, 2.5, undefined, 3.5, 7]));
  check('a window larger than the data is the mean so far', same(smooth([2, 4, 6], 50), [2, 3, 4]));
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
  // learner charts: abandoned updates after a restart left out; two columns of one run, the second dashed
  const ups = [...Array.from({ length: 6 }, (_, i) => update(i + 1)), ...Array.from({ length: 4 }, (_, i) => update(i + 4, { critic_loss: 9 }))];
  const e = run('/e', 3, k => k, { updates: ups }), f = run('/f', 3, k => k, { updates: [update(1), update(2)] });
  const learner = buildCompare([{ store: e, label: 'E' }, { store: f, label: 'F' }], 'critic_loss', 0, { mode: 'all' }, 800);
  check('learner comparison: the line each learner went on, abandoned updates left out', same(learner.x, [1, 2, 3, 4, 5, 6, 7])
    && same(learner.series[0].values, [1, 1 / 2, 1 / 3, 9, 9, 9, 9]) && same(learner.series[1].values, [1, 1 / 2, undefined, undefined, undefined, undefined, undefined]), JSON.stringify(learner.series.map(x => x.values)));
  const grads = buildCompare([{ store: e, label: 'E' }, { store: f, label: 'F' }], 'grad_norm', 0, { mode: 'all' }, 800);
  check('two columns of one run: named, the second dashed', same(grads.series.map(x => [x.label, !!x.dash, x.run]), [['E / Critics', false, 0], ['E / Policy', true, 0], ['F / Critics', false, 1], ['F / Policy', true, 1]]));
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

console.log(failed ? `${failed} of ${passed + failed} check(s) FAILED` : `all ${passed} checks passed`);
process.exit(failed ? 1 : 0);
