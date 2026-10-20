// Browser check of the Training tab (record 7.193, user request: "Add a Training tab beside Output ... using uPlot for live
// training graphs. Keep Output available for logs and errors.").
// Hermetic, on the shared harness: GET /api/runs/training, the run's status, the run list, files and logs are answered
// with canned FIXTURE data shaped as the backend sends it (training_series.py); every other writing request is refused.
// Safe against the live 8765 page. What it checks:
//   - the tab sits right after "Output files"; Logs and Output files still show their data
//   - a hidden Training tab reads and draws nothing; opened, it reads the history in pages, then every 2 s while the run
//     lives; incoming numbers never change the chosen tab
//   - charts redraw at most once a second, and not when nothing changed
//   - the run's name, state and last metric; waiting / completed / failed / not-recorded states in plain words
//   - hover values are the recorded values; legend toggles; drag-zoom holds while new results arrive; Follow latest and
//     Reset zoom; resizing the bottom panel resizes the plots; the chosen charts are kept after a reload
//   - switching runs keeps them apart; no listener or chart is left behind (window listener count, chart count)
//   - a long history (20,000 evaluations, ~128,000 learner updates) loads in pages and stays responsive; with lower caps the
//     memory bound thins the oldest part and says so
//   - learner charts by evaluation (record 7.213): a run learning 8 times per evaluation and one learning once end at the
//     same x; the choice is kept after a reload and lets go of the learner charts' zoom; units in the chart titles are
//     written in English letters (units.ts)
//   - key numbers (record 7.215): one row per run on the charts with the recorded values, folded and kept so after a reload
//   - shared chart preparation (record 7.221): a long live run (19,000 evaluations, ~121,000 learner updates) drawn on as
//     results arrive, its newest values the recorded ones; the cost of its changed frames said (INFO); switching runs in
//     the run window and taking a compared run off give their rows back (JS heap and typed arrays after a collection)
// Run (Windows node through WSL interop, ~1.5 min):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/training_tab_check.mjs)" [screenshot-dir]
import path from 'node:path';
import { check, launchEdge, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl, NEVER_ASKED_OR_SAVED, RUNS_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('training');

// ---- canned answers, shaped as training_series.read_training sends them ---------------------------------------------------
const WORDS = new Set(['episode_id', 'phase', 'action_source', 'status', 'update_phase', 'metric_name', 'failure_reason']);
const EVALUATION = ['commit_seq', 'completion_index', 'global_env_step', 'episode_id', 'episode_step', 'phase', 'action_source', 'status',
  'policy_version', 'reward', 'valid', 'all_hard_constraints_satisfied', 'normalized_constraint_violation', 'clearance_margin',
  'best_so_far_feasible', 'best_so_far_violation', 'execution_seconds', 'committed_at', 'best_so_far_objective'];
const UPDATE = ['cumulative_updates', 'evaluations_collected', 'update_phase', 'actor_loss', 'critic_loss', 'alpha_loss', 'alpha', 'mean_log_prob',
  'target_mean', 'critic_grad_norm', 'actor_grad_norm', 'updated_at'];
const SPEC = ['commit_seq', 'metric_name', 'raw_value', 'satisfied', 'failure_reason'];
function columns(rows, names) {
  const result = { n: rows.length };
  for (const name of names) {
    if (!WORDS.has(name)) { result[name] = rows.map(r => r[name] ?? null); continue; }
    const words = [], index = new Map();
    result[name] = { values: words, codes: rows.map(r => { const v = r[name]; if (v == null) return -1; if (!index.has(v)) { index.set(v, words.length); words.push(v); } return index.get(v); }) };
  }
  return result;
}
const T0 = Date.parse('2026-10-05T12:00:00Z') / 1000;
const reward = k => -0.3 * Math.exp(-k / 150) - 0.01 * (1 + Math.sin(k));              // a learning curve with noise
const gain = k => (k % 37 === 0 ? null : 350 + 120 * (1 - Math.exp(-k / 120)) + 5 * Math.cos(k));
/** A run of `n` evaluations (every 5th an episode start, every 41st a timeout) with 8 learner updates each after a warm-up;
 *  its one spec `gain_vv` in V/V unless `spec` and `unit` say otherwise. */
function makeRun(n, { updatesPer = 8, frozen = false, calibration = false, spec = 'gain_vv', unit = 'V/V' } = {}) {
  const evaluations = [], updates = [], specs = [];
  let cum = 0;
  for (let k = 1; k <= n; k++) {
    const start = (k - 1) % 5 === 0, timeout = k % 41 === 0;
    const phase = start ? (k === 1 ? 'baseline' : 'episode_reset') : frozen ? 'frozen_eval' : k < 9 || calibration ? 'warmup' : 'search';
    const value = gain(k), met = value !== null && value >= 400;
    evaluations.push({ commit_seq: k, completion_index: k, global_env_step: k - Math.ceil(k / 5), episode_id: `0-${String(Math.ceil(k / 5)).padStart(6, '0')}`,
      episode_step: (k - 1) % 5, phase, action_source: start ? 'reset' : phase === 'warmup' ? 'random_warmup' : 'sac_policy', status: timeout ? 'timeout' : 'ok',
      policy_version: null, reward: start || timeout ? null : reward(k), valid: !timeout && value !== null, all_hard_constraints_satisfied: met,
      normalized_constraint_violation: timeout || value === null ? null : Math.max(0, (400 - value) / 400), clearance_margin: null, best_so_far_feasible: k > 200,
      best_so_far_violation: Math.max(0, 0.1 - k / 2000), execution_seconds: 1.2, committed_at: T0 + k, best_so_far_objective: null });
    specs.push({ commit_seq: k, metric_name: spec, raw_value: timeout ? null : value, satisfied: timeout || value === null ? null : met,
      failure_reason: timeout ? 'evaluation_status_timeout' : value === null ? 'missing_or_nonfinite' : null });
    if (!frozen && !calibration && !start && k >= 9) for (let u = 0; u < updatesPer; u++) {
      cum += 1;
      updates.push({ cumulative_updates: cum, evaluations_collected: k, update_phase: null, actor_loss: 0.2 * Math.sin(cum / 50), critic_loss: 0.1 * Math.exp(-cum / 900) + 0.001,
        alpha_loss: 0, alpha: 0.01 * Math.exp(-cum / 4000), mean_log_prob: -6 + cum / 600, target_mean: -0.1, critic_grad_norm: 1, actor_grad_norm: 2, updated_at: T0 + k });
    }
  }
  // prefix[k] = updates recorded with the first k evaluations: a flush's updates are a slice, not a search
  const prefix = new Int32Array(n + 1);
  let u = 0;
  for (let k = 1; k <= n; k++) { while (u < updates.length && updates[u].evaluations_collected <= k) u++; prefix[k] = u; }
  return { evaluations, updates, specs, prefix, defs: { [spec]: { unit, threshold_lower: 400, threshold_upper: null, hard: true } } };
}
const chunk = (data, from, to) => ({ evaluations: columns(data.evaluations.slice(from, to), EVALUATION),
  updates: columns(data.updates.slice(data.prefix[Math.min(from, data.evaluations.length)], data.prefix[Math.min(to, data.evaluations.length)]), UPDATE),
  specs: columns(data.specs.slice(from, to), SPEC), spec_defs: data.defs });
/** The canned backend of one run: `final` evaluations published in flushes of 16, `tail` more still in the journal. */
function serve(run, cursor, tailCursor) {
  const flushes = Math.ceil(run.final / 16), start = Math.min(cursor, flushes);
  let served = start, rows = 0;
  while (served < flushes) {
    const from = served * 16, to = Math.min(run.final, from + 16);
    const add = (to - from) * 2 + run.data.prefix[to] - run.data.prefix[from];
    if (served > start && rows + add > 30000) break;
    rows += add; served += 1;
  }
  const from = start * 16, to = Math.min(run.final, served * 16);
  const previous = tailCursor ? JSON.parse(tailCursor) : null;
  const reset = previous?.base !== run.final;
  const tailFrom = reset ? run.final : previous.offset;
  // Deliberately tiny live pages exercise both cursor polling loops independently of the larger history pages.
  const tailTo = Math.min(run.final + run.tail, tailFrom + 2);
  const tailPage = served === flushes
    ? { start: tailCursor, cursor: JSON.stringify({ base: run.final, offset: tailTo }), reset, more: tailTo < run.final + run.tail }
    : { start: tailCursor, cursor: null, reset: true, more: false };
  return { run_dir: run.dir, run_id: run.id, mode: run.frozen ? 'frozen' : 'scratch', mock: true, flushes: { served, total: flushes, start },
    state: run.state, worker_alive: run.alive ?? run.state === 'running',
    final: chunk(run.data, from, to), tail: served === flushes ? chunk(run.data, tailFrom, tailTo) : null, tail_complete: true, tail_page: tailPage,
    latest_seq: served === flushes ? tailTo : run.final, objective: null,
    learner: run.frozen ? { recorded: false, every: 1, reason: 'A frozen run evaluates a saved policy without training it: there are no learner updates, so no losses, temperature or entropy.' } : { recorded: true, every: 1, reason: null },
    segments: [{ segment: 1, entry: 'start', started_utc: new Date(T0 * 1000).toISOString(), ended_utc: null, end_state: null, stop_reason: null }] };
}
const status = run => ({ state: run.state, stop_reason: run.state === 'failed' ? 'evaluation_exception' : null, error: run.state === 'failed' ? 'FIXTURE: the simulator host went away' : null,
  run_id: run.id, mode: 'scratch', provenance: 'mock', mock: true, worker_alive: run.state === 'running', run_dir: run.dir, active_workers: [], concurrency: 1,
  budget: { max_evaluations: 2000, charged: run.final + run.tail, in_flight: 0, completed: run.final + run.tail, failed: 0, remaining: 0, launches: 0, retries: 0, cache_hits: 0 },
  best_design: null, first_feasible: null, paths: { run_dir: run.dir }, connection: { overall: 'not_applicable' }, summary: null,
  calibration: run.calibration ? { request: { designs: 24, lanes: 1, evaluations: 25 }, result: null } : null,
  manifest: { mode: 'scratch', mock: true, mock_notice: 'FIXTURE MOCK DATA' } });
const base = '/fixture/outputs/fixture__1/runs/mock/';
const RUNS = {
  live: { dir: base + 'scratch__seed1__live', id: 'live', state: 'running', final: 160, tail: 5, data: makeRun(2000) },
  failed: { dir: base + 'scratch__seed2__failed', id: 'failed', state: 'failed', final: 32, tail: 0, data: makeRun(32) },
  empty: { dir: base + 'scratch__seed3__empty', id: 'empty', state: 'running', final: 0, tail: 0, data: makeRun(0) },
  older: { dir: base + 'scratch__seed6__older', id: 'older', state: 'completed', final: 16, tail: 0, data: makeRun(16), older: true },
  calibration: { dir: base + 'scratch__seed7__calibration', id: 'calibration', state: 'completed', final: 25, tail: 0, data: makeRun(25, { calibration: true }), calibration: true },
  // compared beside the shown run (record 7.200): listed as completed (so the page does not take it over as the header's
  // run), while its own answers say its worker lives until the check says otherwise
  twin: { dir: base + 'scratch__seed8__twin', id: 'twin', state: 'completed', alive: true, final: 304, tail: 2, data: makeRun(400) },   // whole flushes of 16: a published flush never changes
  frozen: { dir: base + 'scratch__seed4__frozen', id: 'frozen', state: 'completed', final: 48, tail: 0, data: makeRun(48, { frozen: true }), frozen: true },
  long: { dir: base + 'scratch__seed5__long', id: 'long', state: 'completed', final: 20000, tail: 0, data: null },
  // the long run's rows as a live run (record 7.221): 19,008 evaluations published (whole flushes of 16), the rest to come
  longlive: { dir: base + 'scratch__seed10__longlive', id: 'longlive', state: 'running', final: 19008, tail: 2, data: null },
  // learns once per evaluation (as the SAC defaults before record 7.183 did); its spec's unit written with a Greek letter
  once: { dir: base + 'scratch__seed9__once', id: 'once', state: 'completed', final: 288, tail: 0, data: makeRun(288, { updatesPer: 1, spec: 'i_bias', unit: '\u00b5A' }) },
};
const byDir = Object.fromEntries(Object.values(RUNS).map(r => [r.dir, r]));
let listRuns = false;                                 // GET /api/runs lists the runs only for the comparison part
const runRows = () => ['live', 'failed', 'frozen', 'twin', 'once', 'long'].map((id, i) => ({ run_dir: RUNS[id].dir, run_id: id, task_name: 'fixture_task', mode: RUNS[id].frozen ? 'frozen' : 'scratch',
  seed: i + 1, state: RUNS[id].state === 'running' ? 'completed' : RUNS[id].state, created_utc: `2026-10-05T1${i}:00:00+00:00`, evaluations: RUNS[id].final + RUNS[id].tail, mock: true }))
  .map(r => (r.run_id === 'once' ? { ...r, seed: 1, created_utc: '2026-10-05T10:00:00+00:00' } : r));      // reads as the live run but for its folder id

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);
  const page = await browser.open({ consoleApi: false, width: 1600, height: 1000 });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const reads = [];                                         // every /api/runs/training request: { run, flushes, at }
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname, run = byDir[url.searchParams.get('run_dir')];
    if (name === '/api/config/validate') return fulfil(requestId, 200, validConfiguration({ mock: true }));
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: listRuns ? runRows() : [] });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/status') return run ? fulfil(requestId, 200, status(run)) : fulfil(requestId, 404, { detail: 'Not a run directory' });
    if (name === '/api/runs/training') {
      if (!run) return fulfil(requestId, 404, { detail: { message: 'Not a run directory' } });
      if (run.older) return fulfil(requestId, 404, { detail: 'Not Found' });                   // a backend without the route
      if ((run.id === 'long' || run.id === 'longlive') && !run.data) run.data = RUNS.long.data ?? (RUNS.long.data = makeRun(20000));
      const tailCursor = url.searchParams.get('tail_cursor');
      reads.push({ run: run.id, flushes: Number(url.searchParams.get('flushes')), tailCursor, at: Date.now() });
      return fulfil(requestId, 200, serve(run, Number(url.searchParams.get('flushes')), tailCursor));
    }
    if (name === '/api/runs/logs') return fulfil(requestId, 200, { kind: url.searchParams.get('kind'), entries: [{ time_utc: '2026-10-05T12:00:01+00:00', event: 'FIXTURE_event', run_id: 'live', detail: 'logs still work' }] });
    if (name === '/api/runs/files') return fulfil(requestId, 200, { files: [{ path: 'FIXTURE/run_manifest.json', bytes: 1234, modified_utc: '2026-10-05T12:00:00+00:00' }], total_bytes: 1234, run_dir: run?.dir });
    return page.readOrRefuse({ requestId, request });
  };
  // Every redraw of a chart clears its canvas: counted per canvas, with the time.
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => { const clear = CanvasRenderingContext2D.prototype.clearRect; window.__draws = [];
    CanvasRenderingContext2D.prototype.clearRect = function (...a) { const plot = this.canvas.closest && this.canvas.closest('.training-plot');
      if (plot) { const at = performance.now(); window.__draws.push({ at, plot: [...document.querySelectorAll('.training-plot')].indexOf(plot) });
        queueMicrotask(() => (window.__drawMs ??= []).push(performance.now() - at)); }   // uPlot draws on from here, in one go
      return clear.apply(this, a); };
    window.__long = []; try { new PerformanceObserver(l => window.__long.push(...l.getEntries().map(e => e.duration))).observe({ type: 'longtask', buffered: true }); } catch {} })();` });
  await page.intercept(['*/api/runs/*', '*/api/runs', '*/api/runs?*', '*/api/config/validate'], answer, { others: 'read' });
  await page.seed({ config: CONFIG, run: RUNS.live.dir, when: 'once' });
  await send('Page.navigate', { url: APP });
  const until = (expression, tries = 80) => page.until(expression, tries);
  if (!(await until(`!!document.querySelector('footer .tabs')`, 150))) throw new Error('the page never showed its bottom tabs');
  const TRAINING = `[...document.querySelectorAll('footer .bottom-body .training')][0]`;
  const visible = `(${TRAINING})?.checkVisibility()`;
  const tabs = await evaluate(`[...document.querySelectorAll('footer .tabs > button')].map(b => b.textContent)`);
  check('the Training tab sits right after Output files', tabs.indexOf('Training') === tabs.indexOf('Output files') + 1, tabs.join(' | '));
  await sleep(2500);
  check('while another tab is shown the Training tab reads nothing', reads.length === 0, `${reads.length} reads`);
  const press = label => evaluate(`(() => { const b = [...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent === ${JSON.stringify(label)}); b.click(); return !!b; })()`);
  const activeTab = () => evaluate(`document.querySelector('footer .tabs > button.active')?.textContent`);

  // ---- open: the history in pages, then charts ------------------------------------------------------------------------------
  await press('Training');
  check('the tab opens', await until(visible));
  check('the history comes in (two charts drawn)', await until(`document.querySelectorAll('.training .training-plot canvas').length === 2`, 100));
  const head = () => evaluate(`(${TRAINING}).querySelector('.training-head').innerText`);
  check('the head names the run, its state, the counts and the last metric', await until(`/scratch__seed1__live/.test((${TRAINING}).querySelector('.training-run').textContent)
    && /running/.test((${TRAINING}).querySelector('.badge').textContent) && /165 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)
    && /last metric \\d\\d:\\d\\d:\\d\\d/.test((${TRAINING}).querySelector('.training-counts').textContent) && /live/.test((${TRAINING}).querySelector('.training-counts').textContent)`), await head());
  // each chart's title is the list it chooses its content in (record 7.205): what it shows = the chosen option's words
  const CHART = i => `[...(${TRAINING}).querySelectorAll('figure.training-chart select.training-chart-choice')][${i}]`;
  const TITLES = `[...(${TRAINING}).querySelectorAll('figure.training-chart select.training-chart-choice')].map(s => s.selectedOptions[0]?.textContent ?? '')`;
  const captions = await evaluate(TITLES);
  check('the first charts: step reward and the share meeting every hard spec', captions[0] === 'Step reward' && captions[1] === 'Meets every hard spec', captions.join(' | '));
  check('the training numbers were read from cursor 0 with no page twice', reads[0]?.flushes === 0 && new Set(reads.map(r => r.flushes)).size >= 1);
  check('live journal pages are fetched immediately using their separate cursor', reads.length >= 3 && !reads[0].tailCursor
    && !!reads[1].tailCursor && !!reads[2].tailCursor && reads[2].at - reads[0].at < 2000);
  await page.shot(path.join(out, 'training-open.png'), `(${TRAINING})`);

  // ---- hover: the recorded values -----------------------------------------------------------------------------------------
  const plotBox = (i = 0) => evaluate(`(() => { const r = [...(${TRAINING}).querySelectorAll('.training-plot .u-over')][${i}].getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })()`);
  const readout = (i = 0) => evaluate(`[...(${TRAINING}).querySelectorAll('.training-readout')][${i}].textContent`);
  let box = await plotBox(0);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w * 0.5, y: box.y + box.h * 0.5 });
  await sleep(300);
  const hovered = await readout(0);
  const k = Number(/^Evaluation (\d+)/.exec(hovered)?.[1]);
  const shownValue = Number(/Training \(recorded\) (-?[\d.e-]+)/.exec(hovered)?.[1]);
  const expected = RUNS.live.data.evaluations[k - 1];
  const want = expected?.reward == null ? null : +expected.reward.toPrecision(4);
  check('hovering shows the evaluation under the pointer with its recorded reward', Number.isFinite(k) && (want === null ? !/Training \(recorded\) -?\d/.test(hovered) : shownValue === want), `${hovered} | recorded ${expected?.reward}`);
  check('the hover line says the row\'s phase and episode', /search|warmup|episode_reset|baseline/.test(hovered) && /episode 0-\d{6} step \d/.test(hovered));
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w + 40, y: box.y - 40 });

  // ---- live: new results arrive; at most one redraw a second; the chosen tab never changes ------------------------------------
  const drawsBefore = await evaluate('window.__draws.length');
  RUNS.live.final = 192; RUNS.live.tail = 3;
  check('a live run is read again within about 2 s and its new results counted', await until(`/195 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)`, 60));
  await sleep(2600);
  const draws = await evaluate('window.__draws');
  const perSecond = Math.max(0, ...draws.map(d => draws.filter(e => e.plot === d.plot && e.at >= d.at && e.at < d.at + 1000).length));
  check('a chart redraws at most once a second while results arrive', perSecond <= 2, `${draws.length - drawsBefore} redraws since, at most ${perSecond} per chart in a second`);
  const quiet = await evaluate('window.__draws.length');
  await sleep(4500);                                                        // two more reads that bring nothing new
  check('nothing new, no redraw', (await evaluate('window.__draws.length')) === quiet, `${(await evaluate('window.__draws.length')) - quiet} redraws`);
  await press('Logs');
  const readsHidden = reads.length;
  RUNS.live.final = 240; RUNS.live.tail = 1;
  await sleep(4500);
  check('incoming results do not take the tab away from Logs', (await activeTab()) === 'Logs');
  check('Logs still shows the run\'s log', await until(`/FIXTURE_event/.test(document.querySelector('footer .bottom-body .scroll.log')?.textContent ?? '')`));
  check('hidden, the Training tab reads nothing and draws nothing', reads.length === readsHidden && (await evaluate('window.__draws.length')) === quiet, `${reads.length - readsHidden} reads`);
  await press('Output files');
  check('Output files still lists the run\'s files', await until(`/FIXTURE\\/run_manifest\\.json/.test([...document.querySelectorAll('footer .bottom-body table.grid')].find(t => t.checkVisibility())?.textContent ?? '')`));
  await press('Training');
  check('opened again it catches up at once from where it was', await until(`/241 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)`, 40) && reads[readsHidden]?.flushes === 12, `first read after: flushes=${reads[readsHidden]?.flushes}`);

  // ---- zoom, follow latest, reset ------------------------------------------------------------------------------------------
  box = await plotBox(0);
  const y = box.y + box.h / 2;
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x + box.w * 0.2, y, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w * 0.35, y, button: 'left', buttons: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w * 0.5, y, button: 'left', buttons: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x + box.w * 0.5, y, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w + 40, y: box.y - 40 });
  const FOLLOW = `[...(${TRAINING}).querySelectorAll('.training-head button')].find(b => b.textContent === 'Follow latest')`;
  const RESET = `[...(${TRAINING}).querySelectorAll('.training-head button')].find(b => b.textContent === 'Reset zoom')`;
  check('a drag across a chart zooms: Follow latest goes off, Reset zoom comes on', await until(`(${FOLLOW}).getAttribute('aria-pressed') === 'false' && !(${RESET}).disabled`, 30));
  await sleep(1200);
  const zoomed = await readout(0);
  RUNS.live.final = 272; RUNS.live.tail = 2;
  await until(`/274 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)`, 60);
  await sleep(1300);
  const stillZoomed = await readout(0);
  const lastShown = s => Number(/Evaluation (\d+)/.exec(s)?.[1]);
  check('new results do not move a zoomed chart', lastShown(zoomed) === lastShown(stillZoomed) && lastShown(stillZoomed) < 200, `${zoomed} -> ${stillZoomed}`);
  await evaluate(`(${FOLLOW}).click()`);
  check('Follow latest slides back to the newest results', await until(`/Evaluation 274/.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`, 30), await readout(0));
  await evaluate(`(${RESET}).click()`);
  check('Reset zoom shows the whole run again', await until(`(${RESET}).disabled && (${FOLLOW}).getAttribute('aria-pressed') === 'true'`, 30));

  // ---- the bottom panel folded to its tab line hides the tab too ----------------------------------------------------------------
  const enter = async () => { await evaluate(`document.querySelector('footer .splitter').focus()`);
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); };
  await enter();
  check('the panel folds to its tab line', await until(`document.querySelector('.layout').classList.contains('bottom-folded')`, 20));
  const readsFolded = reads.length;
  await sleep(4500);
  check('folded, the live run is not read', reads.length === readsFolded, `${reads.length - readsFolded} reads`);
  await enter();
  const unfolded = await until(`!document.querySelector('.layout').classList.contains('bottom-folded')`, 20);
  for (let i = 0; i < 40 && reads.length === readsFolded; i++) await sleep(100);
  check('opened again, it reads again', unfolded && reads.length > readsFolded);

  // ---- legend toggles, smoothing, another chart; the choice kept after a reload ----------------------------------------------------
  const keys = await evaluate(`[...(${TRAINING}).querySelectorAll('.training-legend')][0].innerText`);
  await evaluate(`[...[...(${TRAINING}).querySelectorAll('.training-legend')][0].querySelectorAll('.training-key')].find(b => /Training/.test(b.textContent)).click()`);
  check('a legend key hides its series and says so', await until(`[...[...(${TRAINING}).querySelectorAll('.training-legend')][0].querySelectorAll('.training-key')].find(b => /Training/.test(b.textContent)).getAttribute('aria-pressed') === 'false'`), keys);
  await evaluate(`[...[...(${TRAINING}).querySelectorAll('.training-legend')][0].querySelectorAll('.training-key')].find(b => /Training/.test(b.textContent)).click()`);
  check('pressed again, the series is back', await until(`/Training \\(recorded\\)/.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`));
  const SECOND = CHART(1);
  await page.setValue(SECOND, 'critic_loss');
  check('a learner chart: critic loss over learner updates', await until(`(${TITLES})[1] === 'Critic loss' && document.querySelectorAll('.training .training-plot canvas').length === 2`));
  const SMOOTH = `[...(${TRAINING}).querySelectorAll('.training-head label.inline')].find(l => /Smoothing/.test(l.textContent)).querySelector('select')`;
  await page.setValue(SMOOTH, '50');
  check('smoothing: the recorded values stay under a mean of the last 50', await until(`/Training \\(recorded\\) -?[\\d.]+.*Training: mean of last 50 -?[\\d.]+/.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`),
    await readout(0));
  check('the readout\'s numbers stand out: the x and each value in the text colour, the words muted (branch record SIF-25)',
    await evaluate(`(() => { const r = [...(${TRAINING}).querySelectorAll('.training-readout')][0], b = [...r.querySelectorAll('b')];
      return b.length === 3 && /^\\d+$/.test(b[0].textContent) && b.every(x => getComputedStyle(x).color !== getComputedStyle(r).color); })()`), await readout(0));
  await page.shot(path.join(out, 'training-critic-smoothed.png'), `(${TRAINING})`);

  // ---- resizing the bottom panel ---------------------------------------------------------------------------------------------
  const plotHeight = () => evaluate(`[...(${TRAINING}).querySelectorAll('.training-plot canvas')][0].getBoundingClientRect().height`);
  const h0 = await plotHeight();
  await evaluate(`document.querySelector('footer .splitter').focus()`);
  for (let i = 0; i < 6; i++) { await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowUp', code: 'ArrowUp', windowsVirtualKeyCode: 38 }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowUp', code: 'ArrowUp', windowsVirtualKeyCode: 38 }); }
  check('a taller bottom panel gives the plots more height', await until(`[...(${TRAINING}).querySelectorAll('.training-plot canvas')][0].getBoundingClientRect().height > ${h0} + 60`, 30), `${h0} -> ${await plotHeight()}`);

  // ---- run completion: one last read, then nothing -------------------------------------------------------------------------------
  RUNS.live.state = 'completed'; RUNS.live.final = 288; RUNS.live.tail = 0;
  check('a completed run: its state and its last results', await until(`/completed/.test((${TRAINING}).querySelector('.badge').textContent) && /288 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)`, 100));
  const after = reads.length;
  await sleep(5000);
  check('a run at rest is not read again', reads.length === after, `${reads.length - after} reads`);

  // ---- key numbers (record 7.215): the recorded values of the run, one row; folded and kept so --------------------------------------
  const KEYS = `(${TRAINING}).querySelector('details.training-keys')`;
  const keyCells = (row = 0) => evaluate(`[...(${KEYS}).querySelectorAll('tbody tr')][${row}] ? [...[...(${KEYS}).querySelectorAll('tbody tr')][${row}].cells].map(c => c.textContent) : null`);
  // one run: its key numbers as six tiles (record 7.360), the value of each with its words
  const keyTiles = () => evaluate(`[...(${KEYS}).querySelectorAll('.key-tile .key-tile-value')].map(v => v.textContent)`);
  const isStart = e => e.phase === 'baseline' || e.phase === 'episode_reset';
  const judged288 = RUNS.live.data.evaluations.filter(e => !isStart(e) && e.status === 'ok');
  const firstLive = judged288.find(e => e.all_hard_constraints_satisfied)?.commit_seq;
  const last100 = judged288.filter(e => e.commit_seq > 188 && e.commit_seq <= 288), passed100 = last100.filter(e => e.all_hard_constraints_satisfied).length;
  const wantKeys = ['288', `evaluation ${firstLive}`, `${passed100} of ${last100.length} ${Math.round(100 * passed100 / last100.length)} %`, '0'];
  check('key numbers: open, six tiles with the run\'s recorded first passing design, passing share of the last 100 and best design\'s miss',
    await until(`(${KEYS})?.open && (${KEYS}).querySelectorAll('.key-tile').length === 6`, 40) && JSON.stringify((await keyTiles()).slice(0, 4)) === JSON.stringify(wantKeys)
    && / \u2192 /.test((await keyTiles())[4]) && / \u2192 /.test((await keyTiles())[5]), `${JSON.stringify(await keyTiles())} | want ${JSON.stringify(wantKeys)}`);
  await evaluate(`(${KEYS}).querySelector('summary').click()`);
  const folded = await until(`!(${KEYS}).open`, 20);
  await send('Page.reload'); await until(`!!document.querySelector('footer .tabs')`, 150); await press('Training');
  check('folded, the key numbers stay folded after a reload', folded && await until(`!!(${KEYS}) && !(${KEYS}).open`, 80));
  await evaluate(`(${KEYS}).querySelector('summary').click()`);
  check('...and open again with a click', await until(`(${KEYS}).open && (${KEYS}).querySelectorAll('.key-tile').length === 6`, 40));

  // ---- listeners and charts left behind ------------------------------------------------------------------------------------------
  const listeners = async () => { const { result } = await send('Runtime.evaluate', { expression: 'window' }); const { listeners } = await send('DOMDebugger.getEventListeners', { objectId: result.objectId }); return listeners.length; };
  await until(`document.querySelectorAll('.training .uplot').length === 2`, 60); await sleep(300);    // after the reload: both charts made again
  const before = await listeners();
  for (const id of ['alpha', 'entropy', 'spec:gain_vv', 'violation', 'actor_loss', 'critic_loss']) { await page.setValue(SECOND, id); await sleep(250); }
  await page.setValue(SMOOTH, '0'); await sleep(300); await page.setValue(SMOOTH, '50'); await sleep(300);
  await press('Run status'); await sleep(200); await press('Training'); await sleep(800);
  check('no window listener left behind by six chart changes and two smoothing changes', (await listeners()) === before, `${before} -> ${await listeners()}`);
  check('exactly two charts exist', (await evaluate(`document.querySelectorAll('.training .uplot').length`)) === 2);

  // ---- other runs: kept apart; failed, waiting, not recorded --------------------------------------------------------------------------
  const showRun = async run => { await evaluate(`localStorage.setItem('gator-workbench-current-run-v1', ${JSON.stringify(run.dir)})`); await send('Page.reload'); await until(`!!document.querySelector('footer .tabs')`, 150); await press('Training'); };
  await showRun(RUNS.failed);
  check('the chosen charts are kept after a reload', await until(`(${TITLES})[1] === 'Critic loss'`, 60));
  check('a failed run says so, with its error, and shows its own rows only', await until(`/failed/.test((${TRAINING}).querySelector('.badge').textContent) && /The run failed: FIXTURE/.test((${TRAINING}).innerText) && /32 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)`, 60), await head());
  await showRun(RUNS.older);
  check('a backend older than the page (no such route) is said as such', await until(`/older than the page/.test((${TRAINING}).innerText)`, 60), await evaluate(`(${TRAINING}).innerText.slice(0, 200)`));
  await showRun(RUNS.empty);
  check('a live run with nothing recorded yet is waiting for metrics', await until(`/Waiting for metrics/.test((${TRAINING}).innerText)`, 60));
  await showRun(RUNS.frozen);
  await until(`/48 evaluations/.test((${TRAINING}).querySelector('.training-counts').textContent)`, 60);
  check('a frozen run: the learner chart says why it is empty', await until(`/frozen run evaluates a saved policy/.test((${TRAINING}).innerText)`, 30));
  await page.setValue(CHART(0), 'eval_pass');
  check('a frozen run has an evaluation success rate', await until(`(${TITLES})[0] === 'Evaluation success rate' && document.querySelectorAll('.training .training-plot canvas').length >= 1`, 30));
  check('what the run does not record is listed with the reason', /Episode return/.test(await evaluate(`(${TRAINING}).querySelector('details.training-note summary').textContent`)));
  await page.shot(path.join(out, 'training-frozen.png'), `(${TRAINING})`);

  // ---- a long history: paged, responsive; then the memory bound -------------------------------------------------------------------
  const loadLong = async caps => {
    await evaluate(caps ? `localStorage.setItem('gator-workbench-training-caps-v1', ${JSON.stringify(JSON.stringify(caps))})` : `localStorage.removeItem('gator-workbench-training-caps-v1')`);
    const started = Date.now(), first = reads.length;
    await evaluate(`window.__long && (window.__long.length = 0)`);
    await showRun(RUNS.long);
    const loaded = await until(`/20000 evaluations/.test((${TRAINING})?.querySelector('.training-counts')?.textContent ?? '')`, 600, 100);
    return { loaded, seconds: (Date.now() - started) / 1000, pages: reads.length - first };
  };
  await page.setValue(CHART(0), 'reward');
  await showRun(RUNS.calibration);
  check('a baseline run that calibrates: its random designs are not called Training', await until(`/Calibration \\(random designs\\)/.test([...(${TRAINING}).querySelectorAll('.training-legend')][0]?.textContent ?? '')`, 60)
    && !/^Training$/m.test([...(await evaluate(`[...[...(${TRAINING}).querySelectorAll('.training-legend')][0].querySelectorAll('.training-key')].map(b => b.textContent).join('\\n')`)).split('\n')].join('\n')));
  check('...and its learner chart says it learns nothing', await until(`/learns nothing/.test((${TRAINING}).innerText)`, 30));

  // ---- several runs on one chart (record 7.200) -----------------------------------------------------------------------------
  listRuns = true;
  await evaluate(`localStorage.removeItem('gator-workbench-training-compare-v1')`);
  await showRun(RUNS.live);
  await until(`/288 evaluations/.test((${TRAINING}).querySelector('.training-counts')?.textContent ?? '')`, 60);
  await page.setValue(SECOND, 'critic_loss');
  const COMPARE = `(${TRAINING}).querySelector('select[aria-label="Compare with another run"]')`;
  const choices = await evaluate(`[...(${COMPARE}).options].map(o => o.value)`);
  check('Compare lists the other runs, not the shown one', choices.includes(RUNS.twin.dir) && choices.includes(RUNS.failed.dir) && !choices.includes(RUNS.live.dir), choices.length + ' choices');
  const twinReads = () => reads.filter(r => r.run === 'twin').length;
  await page.setValue(COMPARE, RUNS.twin.dir);
  check('a compared run gets its chip and its own colour on both charts, its whole name in the legend', await until(`(${TRAINING}).querySelectorAll('.training-compared .training-chip').length === 2
    && [...(${TRAINING}).querySelectorAll('.training-legend')][0].textContent.includes('fixture_task \u00b7 seed 4 \u00b7 '
      + new Date('2026-10-05T13:00:00+00:00').toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }))
    && [...(${TRAINING}).querySelectorAll('.training-legend')].every(l => l.querySelector('.key-run0') && l.querySelector('.key-run1'))`, 60),
    await evaluate(`(${TRAINING}).querySelector('.training-compared')?.innerText`));
  check('the compared run is read in pages from its own cursor', reads.filter(r => r.run === 'twin')[0]?.flushes === 0);
  check('key numbers: a row per run, each named and coloured as its chip', await until(`(${TRAINING}).querySelectorAll('details.training-keys tbody tr').length === 2`, 40)
    && await evaluate(`[...(${TRAINING}).querySelectorAll('details.training-keys tbody tr')].map((r, i) => r.cells[0].querySelector('.key-run' + i)?.textContent).join('|')
      === [...(${TRAINING}).querySelectorAll('.training-compared .training-chip')].map(c => c.childNodes[1].textContent).join('|')`),
    await evaluate(`[...(${TRAINING}).querySelectorAll('details.training-keys tbody tr')].map(r => r.textContent).join(' || ')`));
  // the twin has 306 evaluations; its 306th is an episode start, which a comparison leaves out: its newest point is 305
  check('the newest point of the comparison is the longer run\'s', await until(`/Newest: Evaluation 305/.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`, 40),
    await readout(0));
  const before3 = twinReads();
  RUNS.twin.final = 320;
  const grew = await until(`/Newest: Evaluation 322/.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`, 60);
  check('a compared run whose worker lives is read again and drawn on', grew && twinReads() > before3, `${await readout(0)} | ${twinReads() - before3} reads`);
  check('compared runs also send their journal cursor on subsequent reads', reads.filter(r => r.run === 'twin').some(r => !!r.tailCursor));
  check('its chip says it is live', / \u00b7 live/.test(await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip')][1].textContent`)),
    await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip')][1].textContent`));
  box = await plotBox(0);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w * 0.3, y: box.y + box.h / 2 });
  await sleep(300);
  const both = await readout(0), at = Number(/^Evaluation (\d+)/.exec(both)?.[1]), wantShown = RUNS.live.data.evaluations[at - 1]?.reward, wantTwin = RUNS.twin.data.evaluations[at - 1]?.reward;
  const shownLabel = await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip')][0].textContent.replace(' (shown)', '')`);
  const twinLabel = await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip')][1].childNodes[1].textContent`);
  const comparedValue = new RegExp(`${shownLabel.replace(/[.*+?^$()|[\]\\]/g, '\\$&')} \\(recorded\\) (-?[\\d.e-]+)`).exec(both)?.[1];
  check('hovering a comparison: each run\'s recorded value at that evaluation', wantShown == null || comparedValue === String(+wantShown.toPrecision(4)), `${both} | shown ${wantShown}, twin ${wantTwin} (${twinLabel})`);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w + 40, y: box.y - 40 });
  RUNS.twin.alive = false;
  await sleep(2500);
  const settled = twinReads();
  await sleep(4500);
  check('once its worker has ended, the compared run is not read again', twinReads() === settled, `${twinReads() - settled} reads`);
  await page.setValue(COMPARE, RUNS.frozen.dir);
  check('a run that cannot be drawn on a chart is named there, with the reason', await until(`/Not on this chart: .*frozen run evaluates a saved policy/.test([...(${TRAINING}).querySelectorAll('figure.training-chart')][1].textContent)`, 60),
    await evaluate(`[...(${TRAINING}).querySelectorAll('figure.training-chart')][1].querySelector('.training-missing')?.textContent ?? ''`));
  await page.shot(path.join(out, 'training-compare.png'), `(${TRAINING})`);
  await send('Page.reload'); await until(`!!document.querySelector('footer .tabs')`, 150); await press('Training');
  check('the compared runs are kept after a reload', await until(`(${TRAINING}).querySelectorAll('.training-compared .training-chip').length === 3`, 60));
  await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip-remove')][0].click()`);
  check('× takes a run off the charts', await until(`(${TRAINING}).querySelectorAll('.training-compared .training-chip').length === 2
    && !(${TRAINING}).querySelector('.training-compared').textContent.includes('twin')`, 30));
  await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip-remove')][0].click()`);
  check('the last one taken off: one run again', await until(`!(${TRAINING}).querySelector('.training-compared') && !(${TRAINING}).querySelector('.key-run1')`, 30));

  // ---- learner charts by evaluation (record 7.213): 8 and 1 updates per evaluation line up ----------------------------------------
  const LEARNER_X = `(${TRAINING}).querySelector('select[aria-label="Learner charts by"]')`;
  const liveLast = RUNS.live.data.updates.filter(u => u.evaluations_collected <= 288).at(-1);
  const onceAt288 = RUNS.once.data.updates.find(u => u.evaluations_collected === 288), onceLast = RUNS.once.data.updates.at(-1);
  const p4 = v => String(+v.toPrecision(4));
  check('learner charts are drawn by update unless chosen otherwise', (await evaluate(`(${LEARNER_X}).value`)) === 'update'
    && await until(`/^Newest: Learner update ${liveLast.cumulative_updates} \u00b7 .* \u00b7 after 288 evaluations$/.test([...(${TRAINING}).querySelectorAll('.training-readout')][1].textContent)`, 40), await readout(1));
  box = await plotBox(1);
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x + box.w * 0.2, y: box.y + box.h / 2, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w * 0.4, y: box.y + box.h / 2, button: 'left', buttons: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x + box.w * 0.4, y: box.y + box.h / 2, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w + 40, y: box.y - 40 });
  const learnerZoomed = await until(`!(${RESET}).disabled`, 30);
  await page.setValue(LEARNER_X, 'evaluation');
  check('by evaluation: x = the evaluations collected, the newest row named by its update; the zoom of the learner chart let go',
    learnerZoomed && await until(`/^Newest: Evaluation 288 \u00b7 Critic loss \\(recorded\\) ${p4(liveLast.critic_loss).replace('.', '\\.')} \u00b7 Critic loss: mean of last 50 evaluations \\S+ \u00b7 update ${liveLast.cumulative_updates}$/.test([...(${TRAINING}).querySelectorAll('.training-readout')][1].textContent)`, 40)
    && await evaluate(`(${RESET}).disabled`), await readout(1));
  await page.setValue(COMPARE, RUNS.once.dir);
  await until(`(${TRAINING}).querySelectorAll('.training-compared .training-chip').length === 2`, 60);
  const onceLabel = await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip')][1].childNodes[1].textContent`);
  const liveChip = await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip')][0].textContent`);
  check('two compared runs that would read alike (task, seed, time) are told apart by their folder ids', / \u00b7 once$/.test(onceLabel) && / \u00b7 live \(shown\)$/.test(liveChip)
    && onceLabel.replace(/ \u00b7 once$/, '') === liveChip.replace(/ \u00b7 live \(shown\)$/, ''), `${liveChip} | ${onceLabel}`);
  const at288 = new RegExp(`^Newest: Evaluation 288 .*${onceLabel.replace(/[.*+?^$()|[\]\\]/g, '\\$&')} \\(recorded\\) ${p4(onceAt288.critic_loss).replace('.', '\\.')}( |$)`);
  check('compared by evaluation, a run learning once per evaluation ends at the same x, each run\'s recorded value there',
    await until(`${at288}.test([...(${TRAINING}).querySelectorAll('.training-readout')][1].textContent) && /\\(recorded\\) ${p4(liveLast.critic_loss).replace('.', '\\.')} /.test([...(${TRAINING}).querySelectorAll('.training-readout')][1].textContent)`, 60),
    await readout(1));
  await page.setValue(LEARNER_X, 'update');
  check('compared by update the same two runs end far apart (the newest x is the 8-per-evaluation run\'s count)',
    await until(`/^Newest: Learner update ${liveLast.cumulative_updates} /.test([...(${TRAINING}).querySelectorAll('.training-readout')][1].textContent)
      && ![...(${TRAINING}).querySelectorAll('.training-readout')][1].textContent.includes(${JSON.stringify(onceLabel + ' (recorded)')})`, 40)
    && liveLast.cumulative_updates > 4 * onceLast.cumulative_updates, `${await readout(1)} | once ends at update ${onceLast.cumulative_updates}`);
  await page.setValue(LEARNER_X, 'evaluation');
  await send('Page.reload'); await until(`!!document.querySelector('footer .tabs')`, 150); await press('Training');
  check('the learner\'s x is kept after a reload', await until(`(${LEARNER_X})?.value === 'evaluation' && /^Newest: Evaluation 288 /.test([...(${TRAINING}).querySelectorAll('.training-readout')][1]?.textContent ?? '')`, 80),
    await evaluate(`(${LEARNER_X})?.value`));
  await page.shot(path.join(out, 'training-learner-by-evaluation.png'), `(${TRAINING})`);
  await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip-remove')][0].click()`);
  await until(`!(${TRAINING}).querySelector('.training-compared')`, 30);
  await page.setValue(LEARNER_X, 'update');
  // units in the chart titles (units.ts, record 7.208: English letters): the run's spec is stored in \u00b5A
  await showRun(RUNS.once);
  await until(`/288 evaluations/.test((${TRAINING}).querySelector('.training-counts')?.textContent ?? '')`, 60);
  const unitTitle = await evaluate(`[...(${CHART(0)}).options].find(o => o.value === 'spec:i_bias')?.textContent ?? ''`);
  check('a chart title writes its unit in English letters, as the rest of the page', unitTitle === 'i_bias (uA)', unitTitle);
  await showRun(RUNS.live);
  await until(`/288 evaluations/.test((${TRAINING}).querySelector('.training-counts')?.textContent ?? '')`, 60);
  listRuns = false;

  // ---- more than two charts (record 7.205, user: "add multiple charts same page support. more than the current 2") ------------
  const ADD = `[...(${TRAINING}).querySelectorAll('.training-head button')].find(b => b.textContent === 'Add chart')`;
  const columns = () => evaluate(`getComputedStyle((${TRAINING}).querySelector('.training-charts')).gridTemplateColumns.split(' ').length`);
  const figures = () => evaluate(`(${TRAINING}).querySelectorAll('figure.training-chart').length`);
  await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 2`, 60);
  const listenersBefore = await listeners();
  await evaluate(`(${TRAINING}).querySelector('figure.training-chart canvas').dataset.mark = 'kept'`);    // the first chart's own canvas
  await evaluate(`(${ADD}).click()`);
  check('Add chart puts a third chart on the page, one the run can draw and not on the page yet', await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 3`, 40)
    && new Set(await evaluate(TITLES)).size === 3, JSON.stringify(await evaluate(TITLES)));
  check('three charts stand side by side', (await columns()) === 3, String(await columns()));
  await evaluate(`(${ADD}).click()`);
  check('four charts: two by two', await until(`(${TRAINING}).querySelectorAll('figure.training-chart').length === 4`, 40) && (await columns()) === 2);
  for (let i = 0; i < 4; i++) await evaluate(`(${ADD}).click()`);
  check('up to eight charts, in rows of four; Add chart then waits', await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 8`, 60)
    && (await columns()) === 4 && await evaluate(`(${ADD}).disabled`), `${await figures()} charts`);
  const eight = await evaluate(TITLES);
  check('eight different charts', new Set(eight).size === 8, eight.join(' | '));
  await page.setValue(CHART(5), 'spec:gain_vv');
  check('a chart chooses what it shows in its own title', await until(`(${TITLES})[5] === 'gain_vv (V/V)'`, 40));
  await page.shot(path.join(out, 'training-eight.png'), `(${TRAINING})`);
  await evaluate(`[...(${TRAINING}).querySelectorAll('figure.training-chart .training-chart-remove')][1].click()`);
  check('× takes one chart off; the others keep theirs (the first chart\'s canvas is the same one)', await until(`(${TRAINING}).querySelectorAll('figure.training-chart').length === 7`, 40)
    && await evaluate(`(${TRAINING}).querySelector('figure.training-chart canvas')?.dataset.mark === 'kept'`)
    && JSON.stringify(await evaluate(TITLES)) === JSON.stringify(eight.filter((_, i) => i !== 1).map((t, i) => (i === 4 ? 'gain_vv (V/V)' : t))));
  const seven = await evaluate(TITLES);
  await send('Page.reload'); await until(`!!document.querySelector('footer .tabs')`, 150); await press('Training');
  check('the charts on the page are kept after a reload', await until(`JSON.stringify(${TITLES}) === ${JSON.stringify(JSON.stringify(seven))}`, 80), JSON.stringify(await evaluate(TITLES)));
  while ((await figures()) > 1) { await evaluate(`[...(${TRAINING}).querySelectorAll('figure.training-chart .training-chart-remove')].at(-1).click()`); await sleep(150); }
  check('one chart always stays: its × waits', (await figures()) === 1 && await evaluate(`(${TRAINING}).querySelector('figure.training-chart .training-chart-remove').disabled`));
  await evaluate(`(${ADD}).click()`);
  await until(`(${TRAINING}).querySelectorAll('figure.training-chart').length === 2`, 40);
  await page.setValue(CHART(0), 'reward'); await page.setValue(CHART(1), 'critic_loss');
  await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 2`, 60); await sleep(500);
  check('no window listener left behind after adding and taking off charts', (await listeners()) === listenersBefore, `${listenersBefore} -> ${await listeners()}`);
  const long = await loadLong(null);
  check(`20,000 evaluations and ${RUNS.long.data.updates.length.toLocaleString('en')} learner updates load in pages`, long.loaded && long.pages >= 6, `${long.seconds.toFixed(1)} s, ${long.pages} pages`);
  const t = Date.now(); await evaluate('1'); const ping = Date.now() - t;
  box = await plotBox(0);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x + box.w * 0.7, y: box.y + box.h / 2 });
  const hoverStart = Date.now();
  const hoverOk = await until(`/^Evaluation \\d+/.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`, 30, 20);
  const longTasks = await evaluate('window.__long ? window.__long.filter(d => d > 1000).length : -1');
  check('the page stays responsive with the long history drawn', ping < 500 && hoverOk && Date.now() - hoverStart < 1500, `ping ${ping} ms, hover ${Date.now() - hoverStart} ms, ${longTasks} tasks over 1 s`);
  const heap = await evaluate('performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : -1');
  console.log(`INFO  long history: ${long.seconds.toFixed(1)} s to load, JS heap ${heap} MB`);
  const bound = await loadLong({ evaluations: 5000, updates: 20000 });
  check('with lower caps the oldest part is thinned and the page says so; the counts are still the recorded ones', bound.loaded && await until(`/thinned to its extremes/.test((${TRAINING}).innerText)`, 30),
    await evaluate(`(${TRAINING}).querySelector('.training-counts').textContent`));
  const boundHeap = await evaluate('performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : -1');
  console.log(`INFO  with caps 5,000 / 20,000: JS heap ${boundHeap} MB`);
  await evaluate(`localStorage.removeItem('gator-workbench-training-caps-v1')`);
  await page.shot(path.join(out, 'training-long.png'), `(${TRAINING})`);

  // ---- shared chart preparation (record 7.221): a long live run; switching runs and comparing give their rows back --------------
  // Each run keeps what its charts derive from its rows and brings it up to date as rows arrive. Here: a long live run with
  // eight charts drawn on as results arrive (its newest values the recorded ones; INFO: a changed frame's main-thread time and
  // uPlot's share, Performance.getMetrics), then memory: the JS heap plus the typed arrays' buffers (Runtime.getHeapUsage
  // after a collection) when a long run is shown and left again through the run window, and when it is compared and taken off.
  // the lower of two readings, each after a collection: what the page holds, not what a moment's work has not given back yet
  const heapNow = async () => { let least = Infinity; for (let i = 0; i < 2; i++) { await send('HeapProfiler.collectGarbage'); await sleep(300);
    const h = await send('Runtime.getHeapUsage'); least = Math.min(least, (h.usedSize + (h.backingStorageSize ?? 0)) / 1048576); } return least; };
  const mb = v => `${v.toFixed(1)} MB`;
  const countsText = () => evaluate(`(${TRAINING})?.querySelector('.training-counts')?.textContent ?? ''`);
  await showRun(RUNS.longlive);
  check('a long live run loads: 19,008 evaluations published, the journal read on', await until(`/19010 evaluations/.test((${TRAINING})?.querySelector('.training-counts')?.textContent ?? '')`, 600, 100),
    await countsText());
  for (let i = 0; i < 8 && (await figures()) < 8; i++) { await evaluate(`(${ADD}).click()`); await sleep(150); }
  check('eight charts of the long live run are drawn', await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 8`, 100));
  await sleep(2500);
  await send('Performance.enable');
  const metrics = async () => Object.fromEntries((await send('Performance.getMetrics')).metrics.map(m => [m.name, m.value]));
  await evaluate('window.__drawMs = []');
  const m0 = await metrics(), draws0 = await evaluate('window.__draws.length'), started = Date.now();
  for (let i = 0; i < 8; i++) {                 // two new evaluations in the journal every 2 s; every 8 a flush publishes 16
    RUNS.longlive.tail += 2;
    if (RUNS.longlive.tail >= 18) { RUNS.longlive.final += 16; RUNS.longlive.tail -= 16; }
    await sleep(2000);
  }
  await sleep(1500);
  const m1 = await metrics(), elapsed = (Date.now() - started) / 1000;
  const redraws = (await evaluate('window.__draws.length')) - draws0, drawMs = await evaluate('window.__drawMs.reduce((a, b) => a + b, 0)');
  const frames = Math.max(1, Math.round(redraws / 8)), newest = RUNS.longlive.final + RUNS.longlive.tail;
  console.log(`INFO  long live run (${newest} evaluations, ${RUNS.long.data.prefix[newest].toLocaleString('en')} learner updates, 8 charts): ${frames} changed frames in ${elapsed.toFixed(0)} s;`
    + ` main thread ${((m1.TaskDuration - m0.TaskDuration) * 1000 / frames).toFixed(1)} ms per frame (scripts ${((m1.ScriptDuration - m0.ScriptDuration) * 1000 / frames).toFixed(1)} ms),`
    + ` of it uPlot drawing ${(drawMs / frames).toFixed(1)} ms; JS heap and arrays ${mb(await heapNow())}`);
  check('the long live run is drawn on as results arrive: its newest evaluation on the first chart', await until(`/^Newest: Evaluation ${newest} /.test([...(${TRAINING}).querySelectorAll('.training-readout')][0].textContent)`, 60),
    await readout(0));
  // the newest learner update and its mean of the last 50, as recorded (the learner's numbers derived as rows arrived)
  const newestText = await readout(1), parsed = /^Newest: Learner update (\d+) · Critic loss \(recorded\) (\S+) · Critic loss: mean of last 50 (\S+) · after (\d+) evaluations/.exec(newestText);   // values first (SIF-7)
  const lastUpdate = RUNS.long.data.updates[RUNS.long.data.prefix[newest] - 1], window50 = RUNS.long.data.updates.slice(RUNS.long.data.prefix[newest] - 50, RUNS.long.data.prefix[newest]);
  check('...its newest learner update with the recorded critic loss and the mean of the last 50 recorded ones', !!parsed && Number(parsed[1]) === lastUpdate.cumulative_updates
    && Number(parsed[4]) === lastUpdate.evaluations_collected && Number(parsed[2]) === +lastUpdate.critic_loss.toPrecision(4)
    && Number(parsed[3]) === +(window50.reduce((sum, u) => sum + u.critic_loss, 0) / 50).toPrecision(4), `${newestText} | recorded: update ${lastUpdate.cumulative_updates}, ${lastUpdate.critic_loss}`);
  RUNS.longlive.state = 'completed';

  // switching runs in the run window, three times to the long run and back: each time its rows are given back
  listRuns = true;
  await showRun(RUNS.live);
  await until(`/288 evaluations/.test((${TRAINING})?.querySelector('.training-counts')?.textContent ?? '')`, 60);
  const RUNS_BUTTON = `document.querySelector('footer .tabs button.run-list-button')`;
  /** The run window (Runs...): a double click on the run's row shows it in the bottom tabs, and the window closes by itself
   *  (record 7.291); it is closed here only when no row was found. */
  const pickRun = async run => {
    await evaluate(`${RUNS_BUTTON}.click()`, true);
    const target = await browser.window(RUNS_WINDOW, { present: true, except: page.target.id });
    const far = await browser.attach(target, { errors: consoleErrors, prefix: 'run window: ' });
    await far.send('Emulation.setDeviceMetricsOverride', { width: 1500, height: 860, deviceScaleFactor: 1, mobile: false });
    let at = null;
    for (let i = 0; i < 60 && !at; i++) {
      at = await far.evaluate(`(() => { const tr = [...document.querySelectorAll('.run-window table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(run.dir)});
        if (!tr) return null; const el = tr.children[4]; el.scrollIntoView({ block: 'center' }); const b = el.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; })()`);
      if (!at) await sleep(100);
    }
    if (at) await far.clickAt(at, { count: 2 });
    else await send('Target.closeTarget', { targetId: target.id });
    await browser.window(RUNS_WINDOW, { present: false, except: page.target.id }); far.close();
    await press('Training');
    return !!at;
  };
  await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 8`, 60); await sleep(500);
  const start = await heapNow(), rounds = [];
  for (let round = 0; round < 4; round++) {
    const went = await pickRun(RUNS.long) && await until(`/20000 evaluations/.test((${TRAINING})?.querySelector('.training-counts')?.textContent ?? '')`, 600, 100)
      && await until(`(${TRAINING}).querySelectorAll('figure.training-chart canvas').length === 8`, 60);
    const withLong = await heapNow();
    const back = await pickRun(RUNS.live) && await until(`/288 evaluations/.test((${TRAINING})?.querySelector('.training-counts')?.textContent ?? '')`, 100);
    await sleep(500);
    rounds.push({ went, back, withLong, after: await heapNow() });
  }
  console.log(`INFO  run switching: ${mb(start)} with the short run shown; ${rounds.map(r => `${mb(r.withLong)} with the long run, ${mb(r.after)} back`).join('; ')}`);
  check('switching to a long run and back in the run window, four times: each time its rows are given back (JS heap and arrays after a collection)',
    rounds.every(r => r.went && r.back && r.withLong - start > 10 && r.after - start < 0.2 * (r.withLong - start)) && rounds[3].after - rounds[0].after < 4,
    rounds.map(r => `${r.went && r.back ? '' : 'NOT SWITCHED '}${mb(r.withLong)} -> ${mb(r.after)}`).join(', ') + ` (start ${mb(start)})`);
  // a long run compared, then taken off the charts: its rows go with it
  const alone = await heapNow();
  await page.setValue(COMPARE, RUNS.long.dir);
  const compared = await until(`[...(${TRAINING}).querySelectorAll('details.training-keys tbody tr')].length === 2
    && /^20000$/.test([...(${TRAINING}).querySelectorAll('details.training-keys tbody tr')][1]?.cells[1]?.textContent ?? '')`, 600, 100);
  await sleep(1500);
  const withCompared = await heapNow();
  await evaluate(`[...(${TRAINING}).querySelectorAll('.training-chip-remove')][0].click()`);
  const removed = await until(`!(${TRAINING}).querySelector('.training-compared')`, 30);
  await sleep(500);
  const afterRemoved = await heapNow();
  check('a long run compared and taken off again: its rows are given back', compared && removed && withCompared - alone > 10 && afterRemoved - alone < 0.2 * (withCompared - alone),
    `${mb(alone)} -> ${mb(withCompared)} compared -> ${mb(afterRemoved)} taken off`);
  listRuns = false;

  // (the look switch that redrew the charts here went with the day look, record 7.360)
  await page.shot(path.join(out, 'training-roadster.png'), `(${TRAINING})`);

  check('no script error on the page', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
});
