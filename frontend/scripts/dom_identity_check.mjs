// Browser check for refactorings (docs/plan-refactoring.md, section 4.7): the page's DOM and the requests it makes, written to a
// folder, so that a build made after a pure restructuring can be compared byte for byte with the build before it. Hermetic: no
// writing request reaches a backend (refused with 418, the page's one connection test answered as not tested - lib/harness.mjs).
//
// What it does, in both looks (Whiteprint, Silicon Night), each scene on a fresh browser and a fresh page:
//   fresh       nothing kept in the browser: the page, the Tasks window, the MOCK stand-in task chosen there (a task choice)
//   tabs        a FIXTURE run shown (and held by the header): each bottom tab in turn, the Training tab with a compared run
//   runs        the Runs window, then the shown run's Details
//   rl          the RL model window in each Mode (New model, Fine-tune, Evaluate only, New model again)
//   rl-loaded   a configuration that fine-tunes a FIXTURE saved model: the RL model window with the model in use
//   virtuoso    the Virtuoso cell window, then the PDK window opened from it
//   ngspice     the ngspice netlist window
//   connection  the Connection window, then its "Folders..."
//   agent       the Agent window, then "What's missing?"
//   brief       the header's run chip: the run brief window
// Each scene first settles as the page opened (01-open), so that every request is listed under the step that made it.
// After each step, once nothing has changed for about two seconds (no request, the same DOM), it writes
// <out>/<look>/<scene>/<NN>-<step>.html: #root's outerHTML and each open pop-up window's body, one tag per line. At the end of
// each scene: requests.txt, every /api request of the page (method, path and query, a hash of the body): first the burst the page
// sends as it opens, before any answer has come, in the order it made them (its effects' order); then each step's requests, sorted
// (they race with answers and timers, so their order differs from run to run with the same build; requests-order.txt keeps the
// order of this run and is not compared); and storage.json (localStorage and sessionStorage).
//
// Answers. The FIXTURE run and saved model routes are answered by this check. Every other /api request:
//   record (the default; how run_checks.sh runs it): a read goes to the backend under test, and every answer is kept, the first
//                 one per request, in <out>/answers.json (with the MOCK task's starter rows the scenes seed);
//   --replay <dir>: from <dir>/answers.json, and no backend is asked at all; a request with no answer recorded gets 404 and is
//                 named in requests.txt. With --build <dist> the check serves that build itself (vite preview, /api proxied to a
//                 closed port: nothing can leave).
//   --compare <dir>: every file written (answers.json aside) is compared byte for byte with the same file in <dir>.
// Made the same from run to run: the page's clock is fixed at 2026-10-09 12:00:00 local time (Date.now() and new Date() without
// arguments; timers are untouched), so the times of day the page prints ("read at ...") do not depend on when it ran.
//
// A refactoring's proof:  1. record once against a scratch backend (run_checks.sh --only dom_identity, or by hand);
//   2. node dom_identity_check.mjs <ref> --replay <recorded> --build <dist of the build before>   (the reference)
//   3. node dom_identity_check.mjs <new> --replay <recorded> --build <dist of the build after> --compare <ref>
// Run by hand (Windows node; replay needs no backend): "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w
// frontend/scripts/dom_identity_check.mjs)" <out dir> [--replay <dir>] [--build <dist>] [--compare <dir>] [--looks whiteprint]
// [--scenes rl,runs] [--styles] [--widths 1680,1000,640]. About 3 min for both looks.
//
// A stylesheet's proof (plan-refactoring C11; the static half is css_order_proof.mjs) adds two options, to all three steps:
//   --styles   beside each <NN>-<step>.html, <NN>-<step>.styles.txt: getComputedStyle of every element of the page (html, body and
//              everything under body) and of each open pop-up window, in document order, one line per element (indented by depth:
//              tag#id.classes and a style name), with ::before / ::after where they are drawn (content not none) and ::backdrop of an
//              open dialog. A style is every property the browser lists for the element, custom properties included, sorted:
//              written once per file as its difference from the document's html element (the "base" line, written in full;
//              "-name" = a property html has and the element has not). Lossless: two files are equal byte for byte exactly when
//              every element has the same value for every property. Taken twice, 300 ms apart, on the quiet page: the two must be
//              equal and the DOM unchanged ("the computed styles came to rest"). --compare names the first element whose style
//              differs and the properties that differ.
//   --widths   the page's viewport widths, each a run of every scene (default 1680, the harness's window: the same folders as
//              without it); a narrower width also caps each pop-up window's width. The files of width W go under <look>@<W>/.
//   Hover and focus are not forced here: the static proof covers the order of the :hover / :focus rules.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { AGENT_WINDOW, APP_ROOT_ID, check, CONFIG_KEY, CONNECTION_WINDOW, fail, finish, HEADER_RUN_KEY, launchEdge, LOOK_KEY, NGSPICE_WINDOW, NO_WRITES, PAGE_OPEN_TEST, PDK_WINDOW,
  readOnly, RL_MODEL_WINDOW, RUNNING_WINDOW, RUNS_WINDOW, sleep, TASK_PANEL, TASKS_WINDOW, TRAINING_COMPARE_KEY, VIRTUOSO_WINDOW, workbenchUrl } from './lib/harness.mjs';

const args = process.argv.slice(2);
const option = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
const REPLAY = option('--replay'), COMPARE = option('--compare'), BUILD = option('--build');
const LOOKS = (option('--looks') ?? 'whiteprint,silicon').split(',');
const ONLY = option('--scenes')?.split(',') ?? null;
const STYLES = args.includes('--styles');
const DEFAULT_WIDTH = 1680;                               // launchEdge's window and browser.open's viewport (lib/harness.mjs)
const WIDTHS = (option('--widths') ?? String(DEFAULT_WIDTH)).split(',').map(Number);
if (WIDTHS.some(w => !Number.isInteger(w) || w < 200)) { console.log(`ERROR --widths takes whole pixel widths: ${option('--widths')}`); process.exit(2); }
const values = new Set(['--replay', '--compare', '--build', '--looks', '--scenes', '--widths'].map(option).filter(Boolean));
const OUT = path.resolve(args.find(a => !a.startsWith('--') && !values.has(a)) ?? path.join(process.cwd(), 'dom-identity'));
mkdirSync(OUT, { recursive: true });
const scripts = path.dirname(fileURLToPath(import.meta.url));
process.setMaxListeners(50);                              // one Edge per scene, each with its own SIGINT handler (harness)

// ---- the page under test: a build served here (replay), or the URL of the harness (record) ---------------------------------
const servers = [];
const freePort = () => new Promise((resolve, reject) => {
  const server = net.createServer();
  server.once('error', reject);
  server.listen(0, '127.0.0.1', () => { const { port } = server.address(); server.close(() => resolve(port)); });
});
async function serveBuild(dist) {
  const vite = await import('vite');
  const root = path.resolve(scripts, '..'), port = await freePort();
  const server = await vite.preview({ configFile: path.join(root, 'vite.config.ts'), root, logLevel: 'warn', clearScreen: false, build: { outDir: path.resolve(dist) },
    preview: { host: '127.0.0.1', port, strictPort: true, proxy: { '/api': 'http://127.0.0.1:9' } } });
  servers.push(server);
  return `http://127.0.0.1:${port}/`;
}
if (REPLAY && !existsSync(path.join(REPLAY, 'answers.json'))) { console.log(`ERROR no answers.json in ${REPLAY}`); process.exit(2); }
const APP = BUILD ? await serveBuild(BUILD) : await workbenchUrl();
if (BUILD) console.log(`URL   ${APP}  (the build ${BUILD}, served here; /api goes nowhere)`);
if (BUILD && !REPLAY) { console.log('ERROR --build serves a page with no backend behind it: give --replay <dir> as well'); process.exit(2); }

// ---- answers ---------------------------------------------------------------------------------------------------------------
const kept = REPLAY ? JSON.parse(readFileSync(path.join(REPLAY, 'answers.json'), 'utf8')) : { starter: null, answers: {} };
const answers = kept.answers;
const hash = text => createHash('sha256').update(text).digest('hex').slice(0, 16);
const json = (status, value) => ({ status, contentType: 'application/json', body: JSON.stringify(value) });

// The FIXTURE runs: a completed MOCK run the page shows, and another one the Training tab compares with it; the saved model of the first.
const RUN_BASE = '/fixture/dom/outputs/fixture__1/runs/mock/';
const RUN = `${RUN_BASE}scratch__seed1__shown`, RUN2 = `${RUN_BASE}fine_tune__seed2__other`;
const CKPT = 'ckpt-00000048-fixture', CKPT_EARLY = 'ckpt-00000016-fixture';
const T0 = Date.parse('2026-10-05T10:00:00Z') / 1000;
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
/** A recorded run of `n` evaluations (every 5th an episode start, every 41st a timeout), 4 learner updates per evaluation after a warm-up. */
function recorded(n, shift) {
  const evaluations = [], updates = [], specs = [];
  let cum = 0;
  for (let k = 1; k <= n; k++) {
    const start = (k - 1) % 5 === 0, timeout = k % 41 === 0, value = 350 + 120 * (1 - Math.exp(-k / (12 + shift))) + 5 * Math.cos(k), met = value >= 400;
    evaluations.push({ commit_seq: k, completion_index: k, global_env_step: k - Math.ceil(k / 5), episode_id: `0-${String(Math.ceil(k / 5)).padStart(6, '0')}`,
      episode_step: (k - 1) % 5, phase: start ? (k === 1 ? 'baseline' : 'episode_reset') : k < 9 ? 'warmup' : 'search',
      action_source: start ? 'reset' : k < 9 ? 'random_warmup' : 'sac_policy', status: timeout ? 'timeout' : 'ok', policy_version: null,
      reward: start || timeout ? null : -0.3 * Math.exp(-k / (15 + shift)) - 0.01 * (1 + Math.sin(k)), valid: !timeout, all_hard_constraints_satisfied: met,
      normalized_constraint_violation: timeout ? null : Math.max(0, (400 - value) / 400), clearance_margin: null, best_so_far_feasible: k > 20,
      best_so_far_violation: Math.max(0, 0.1 - k / 200), execution_seconds: 1.2, committed_at: T0 + k, best_so_far_objective: null });
    specs.push({ commit_seq: k, metric_name: 'gain_vv', raw_value: timeout ? null : value, satisfied: timeout ? null : met, failure_reason: timeout ? 'evaluation_status_timeout' : null });
    if (!start && k >= 9) for (let u = 0; u < 4; u++) {
      cum += 1;
      updates.push({ cumulative_updates: cum, evaluations_collected: k, update_phase: null, actor_loss: 0.2 * Math.sin(cum / 10), critic_loss: 0.1 * Math.exp(-cum / 90) + 0.001,
        alpha_loss: 0, alpha: 0.01 * Math.exp(-cum / 400), mean_log_prob: -6 + cum / 60, target_mean: -0.1, critic_grad_norm: 1, actor_grad_norm: 2, updated_at: T0 + k });
    }
  }
  return { evaluations, updates, specs };
}
const RUNS = {
  [RUN]: { id: 'fixture-shown', mode: 'scratch', seed: 1, n: 48, data: recorded(48, 0), created: '2026-10-05T10:00:00+00:00', ended: '2026-10-05T10:21:40+00:00', parent: null },
  [RUN2]: { id: 'fixture-other', mode: 'fine_tune', seed: 2, n: 32, data: recorded(32, 6), created: '2026-10-05T11:00:00+00:00', ended: '2026-10-05T11:12:05+00:00',
    parent: { run_dir: RUN, checkpoint_id: CKPT, relation: 'fine_tune' } },
};
const NETWORK = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 1, structural_encoding: 'none' };
const runRow = dir => { const r = RUNS[dir]; return { run_dir: dir, run_id: r.id, task_name: 'gpdk045_ota5', task_key: 'synthetic:gpdk045_ota5', task_id: 'gpdk045_ota5:0123456789abcdef',
  task_definition_hash: 'f'.repeat(64), mode: r.mode, seed: r.seed, state: 'completed', stop_reason: 'budget_exhausted', created_utc: r.created, started_utc: r.created,
  ended_utc: r.ended, active_seconds: r.n * 27.05, paused_seconds: 0, evaluations: r.n, max_evaluations: r.n, first_feasible_eval_count: 21, model_label: `fixture model ${r.seed}`,
  experiment: 'fixture__1', mock: true, resumability: 'full_state', run_kind: 'optimization', encoder: 'graph_transformer', parent: r.parent,
  segments: [{ segment: 1, entry: 'start', started_utc: r.created, ended_utc: r.ended, end_state: 'completed', stop_reason: 'budget_exhausted', active_seconds: r.n * 27.05 }] }; };
const status = dir => { const r = RUNS[dir]; return { state: 'completed', run_id: r.id, mode: r.mode, entry: 'start', provenance: 'mock', mock: true, worker_alive: false, run_dir: dir,
  heartbeat_utc: r.ended, stop_reason: 'budget_exhausted', error: null, active_workers: [], concurrency: 1, learner_updates: r.data.updates.length,
  first_feasible: { first_feasible_eval_count: 21, dispatch_index: 21, completed_count: 21, in_flight_count: 0, spectre_launches: 21 },
  budget: { max_evaluations: r.n, max_launches: null, max_retries: 0, charged: r.n, reserved: 0, in_flight: 0, completed: r.n, failed: 0, released: 0, remaining: 0,
    launches: r.n, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: { feasible: true, nominal_feasible: true, robust_feasible: null, conditions_complete: true, reward: 0.4321, violation: 0, metrics: { gain_vv: 465.2 },
    metric_units: { gain_vv: 'V/V' }, clearance_margin: 0.163, tightest_clearance_spec: 'gain_vv', variables: [{ variable_id: 'w_in', value: 2.5e-6, unit: 'm' }] },
  persistence: { last_commit_seq: r.n, flushed_seq: r.n, bytes_written: 812345, last_successful_save: r.ended, failed: null },
  last_checkpoint_utc: r.ended, save_point: CKPT, paths: { run_dir: dir, data: `${dir}/data` }, connection: { overall: 'not_applicable' }, steering: null,
  summary: { output: { resumability: 'full_state', completeness: 'complete', latest_checkpoint: CKPT } },
  manifest: { mode: r.mode, mock: true, task_id: 'gpdk045_ota5:0123456789abcdef', seeds: { target_seed: r.seed }, source_model: null, budgets: { max_evaluations: r.n },
    mock_notice: 'FIXTURE MOCK DATA: nothing was started.' } }; };
const TABLE = (dir, table) => ({ table, total_rows: RUNS[dir].n, cutoff_commit_seq: RUNS[dir].n, columns: ['run_id', 'evaluation_id', 'phase', 'reward', 'proposed_at', 'action'],
  rows: [1, 2, 3].map(k => ({ run_id: RUNS[dir].id, evaluation_id: `e${String(k).padStart(31, '0')}`, phase: k === 1 ? 'baseline' : 'search', reward: -0.25 / k,
    proposed_at: `2026-10-05T10:0${k}:00.000000+00:00`, action: { w_in: 0.5 / k, w_tail: -0.25 } })) });
const FILES = dir => ({ total_bytes: 912345, files: ['run_manifest.json', 'effective_config.json', 'data/evaluations/part-000.parquet', 'logs/events.jsonl']
  .map((file, i) => ({ path: file, bytes: 1000 * (i + 1) + 17, modified_utc: '2026-10-05T10:21:40.123456+00:00' })) });
const LOGS = kind => ({ kind, entries: kind === 'errors' ? [] : [1, 2, 3].map(k => ({ time_utc: `2026-10-05T10:2${k}:00.000000+00:00`, event: k === 3 ? 'run_completed' : 'checkpoint_saved',
  run_id: 'fixture-shown', evaluations: 16 * k })) });
function training(dir, cursor) {
  const r = RUNS[dir], flushes = Math.ceil(r.n / 16), start = Math.min(Number(cursor) || 0, flushes);
  const prefix = k => r.data.updates.filter(u => u.evaluations_collected <= k).length;
  const from = start * 16, to = r.n;
  const chunk = { evaluations: columns(r.data.evaluations.slice(from, to), EVALUATION), updates: columns(r.data.updates.slice(prefix(from), prefix(to)), UPDATE),
    specs: columns(r.data.specs.slice(from, to), SPEC), spec_defs: { gain_vv: { unit: 'V/V', threshold_lower: 400, threshold_upper: null, hard: true } } };
  return { run_dir: dir, run_id: r.id, mode: r.mode, mock: true, flushes: { served: flushes, total: flushes, start }, state: 'completed', worker_alive: false,
    final: chunk, tail: { evaluations: columns([], EVALUATION), updates: columns([], UPDATE), specs: columns([], SPEC), spec_defs: chunk.spec_defs }, tail_complete: true,
    tail_page: { start: null, cursor: JSON.stringify({ base: r.n, offset: r.n }), reset: true, more: false }, latest_seq: r.n, objective: null,
    learner: { recorded: true, every: 1, reason: null }, segments: [{ segment: 1, entry: 'start', started_utc: r.created, ended_utc: r.ended, end_state: 'completed', stop_reason: 'budget_exhausted' }] };
}
const point = (id, evaluations, kind, latest) => ({ checkpoint_id: id, kind, created_utc: `2026-10-05T10:${evaluations === 48 ? 21 : 7}:00+00:00`, mode: 'scratch', evaluations,
  learner_updates: evaluations * 3, replay_size: evaluations, restoration_capability: 'full_state', missing_components: [], network: NETWORK, is_latest: latest, is_best_policy: false });
const MODEL = { run_dir: RUN, run_id: 'fixture-shown', task_id: 'gpdk045_ota5:0123456789abcdef', task_name: 'gpdk045_ota5', task_definition_hash: 'f'.repeat(64), mode: 'scratch',
  mock: true, seed: 1, created_utc: '2026-10-05T10:00:00+00:00', state: 'completed', experiment: 'fixture__1', evaluations: 48, circuit_task: 'synthetic:gpdk045_ota5',
  circuit_class: 'gpdk045_ota5', latest: CKPT, best_policy: { selected: null, status: 'not_selected', reason: 'FIXTURE: no validation-set policy evaluation', score: null },
  checkpoints: [point(CKPT, 48, 'final', true), point(CKPT_EARLY, 16, 'periodic', false)], network: NETWORK, saved_utc: '2026-10-05T10:21:00+00:00', trained_evaluations: 48,
  learner_updates: 144, restoration_capability: 'full_state', run_kind: 'optimization', parent: null, encoder: 'graph_transformer', model_label: 'fixture model 1' };
function describe(body) {
  const p = MODEL.checkpoints.find(c => c.checkpoint_id === body.checkpoint_id || (body.checkpoint_id === 'latest' && c.is_latest));
  if (body.run_dir !== RUN || !p) return json(404, { detail: { message: 'FIXTURE: no such checkpoint' } });
  return json(200, { description: { checkpoint_id: p.checkpoint_id, path: `${RUN}/checkpoints/${p.checkpoint_id}`, kind: p.kind, source_run_id: MODEL.run_id,
    source_task_id: MODEL.task_id, mode: p.mode, created_utc: p.created_utc, metadata_version: 'FIXTURE',
    counters: { evaluations_committed: p.evaluations, learner_updates: p.learner_updates, replay_size: p.replay_size }, restoration_capability: p.restoration_capability,
    restorable_components: [], missing_components: [], contract: { model_config: NETWORK, sac_config: {}, reward_version: 'constraint_violation_v2',
      reward_settings: { violation_shape: 'compressed', worst_spec_share: 0.5, objective_weight: 1, margin_weight: 1 }, condition_policy: 'off', planned_conditions: [] }, file_problems: [] },
    vocabulary: { name: 'standard', label: 'standard (8 generic kinds)', pdk_id: null, sha256: null, loaded: true },
    ...(body.config ? { compatibility: { mode: body.config?.run?.mode ?? 'fine_tune', compatible: true, checks: [{ component: 'FIXTURE check', status: 'ok', detail: 'identical' }],
      checkpoint_id: p.checkpoint_id, source_run_id: MODEL.run_id, restoration_capability: 'full_state', suggestion: null } } : {}), suggestion: null });
}
/** The answer this check gives itself, or null for a request the backend (or the recorded answers) answer. */
function fixture(method, url, body) {
  const name = url.pathname, dir = url.searchParams.get('run_dir'), known = dir && RUNS[dir];
  if (name === '/api/runs' && method === 'GET') return json(200, { runs: [runRow(RUN2), runRow(RUN)] });
  if (name === '/api/runs/models' && method === 'GET') return json(200, { models: [MODEL] });
  if (name === '/api/runs/model' && method === 'POST') { try { return describe(JSON.parse(body ?? '{}')); } catch { return json(400, { detail: { message: 'FIXTURE: not JSON' } }); } }
  if (!['/api/runs/status', '/api/runs/table', '/api/runs/files', '/api/runs/logs', '/api/runs/training'].includes(name)) return null;
  if (!known) return json(404, { detail: 'Not a run directory' });
  if (name === '/api/runs/status') return json(200, status(dir));
  if (name === '/api/runs/table') return json(200, TABLE(dir, url.searchParams.get('table')));
  if (name === '/api/runs/files') return json(200, FILES(dir));
  if (name === '/api/runs/logs') return json(200, LOGS(url.searchParams.get('kind')));
  return json(200, training(dir, url.searchParams.get('flushes')));
}
const recording = new Map();
/** Record mode: the backend's answer to a read (kept: the first one per request is the one every later copy gets). */
function record(key, method, url, body) {
  if (!recording.has(key)) recording.set(key, (async () => {
    let answer;
    if (method === 'POST' && url.pathname === '/api/connection/check') {
      let profile = null;
      try { profile = JSON.parse(body ?? '{}').profile_id ?? null; } catch { /* answered as unknown */ }
      answer = json(200, PAGE_OPEN_TEST(profile));
    } else if (readOnly({ method, url: url.href, postData: body ?? undefined })) {
      const response = await fetch(new URL(url.pathname + url.search, APP), { method, headers: body === null ? undefined : { 'Content-Type': 'application/json' }, body: body ?? undefined });
      answer = { status: response.status, contentType: response.headers.get('content-type') ?? 'application/json', body: await response.text() };
    } else answer = json(418, { detail: { message: NO_WRITES } });
    answers[key] = answer;
    return answer;
  })());
  return recording.get(key);
}

// ---- the page's clock, and what is written ---------------------------------------------------------------------------------
const FIXED_CLOCK = `(() => { const Real = Date, fixed = new Real(2026, 9, 9, 12, 0, 0).getTime();
  function FixedDate(...a) { if (!new.target) return new Real(fixed).toString(); return a.length ? new Real(...a) : new Real(fixed); }
  FixedDate.prototype = Real.prototype; FixedDate.now = () => fixed; FixedDate.parse = Real.parse; FixedDate.UTC = Real.UTC;
  Object.defineProperty(FixedDate.prototype, 'constructor', { value: FixedDate, writable: true, configurable: true });
  globalThis.Date = FixedDate; })();`;
const lines = html => html.replace(/ data-react[\w-]*="[^"]*"/g, '').replace(/></g, '>\n<');
const PAGE_DOM = `(() => { const r = document.getElementById(${JSON.stringify(APP_ROOT_ID)}); return (document.documentElement.dataset.theme ?? '') + '\\n' + (r ? r.outerHTML : '(no #root)'); })()`;
const WINDOW_DOM = `(document.documentElement.dataset.theme ?? '') + '\\n' + (document.body ? document.body.outerHTML : '(no body)')`;
/** --styles: the computed style of every element of this document (html, body and all under body), as described at the top. */
const STYLE_DUMP = `(() => {
  const read = (el, pseudo) => { const cs = getComputedStyle(el, pseudo), list = [];
    for (let i = 0; i < cs.length; i++) list.push([cs[i], cs.getPropertyValue(cs[i]).replace(/\\n/g, '\\\\n')]);
    return list.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)); };
  const root = document.documentElement, baseList = read(root, null), base = new Map(baseList);
  const names = new Map(), table = [], lines = [];
  const styleOf = list => {
    const own = new Set(list.map(([n]) => n)), delta = [];
    for (const [n, v] of list) if (base.get(n) !== v) delta.push(n + ':' + v);
    for (const [n] of baseList) if (!own.has(n)) delta.push('-' + n);
    const key = delta.join('; ');
    if (!names.has(key)) { names.set(key, 's' + (names.size + 1)); table.push('style ' + names.get(key) + ' ' + key); }
    return names.get(key);
  };
  const label = el => el.localName + (el.id ? '#' + el.id : '') + [...el.classList].map(c => '.' + c).join('');
  const walk = (el, depth) => {
    const pad = ' '.repeat(depth);
    lines.push(pad + label(el) + ' ' + styleOf(read(el, null)));
    for (const p of ['::before', '::after']) { const c = getComputedStyle(el, p).getPropertyValue('content'); if (c !== 'none' && c !== 'normal') lines.push(pad + ' ' + p + ' ' + styleOf(read(el, p))); }
    if (el.localName === 'dialog' && el.open) lines.push(pad + ' ::backdrop ' + styleOf(read(el, '::backdrop')));
    for (const child of el.children) if (child.localName !== 'head') walk(child, depth + 1);
  };
  walk(root, 0);
  return 'base ' + baseList.map(([n, v]) => n + ':' + v).join('; ') + '\\n' + lines.join('\\n') + '\\n' + table.join('\\n');
})()`;
/** The first element whose style differs between two --styles files (a, b), and how: for the comparison's message. */
function styleDifference(a, b) {
  const parse = text => text.split(/\n(?=<!-- )/).map(section => {
    const [head, ...rest] = section.split('\n');
    const baseLine = rest.find(l => l.startsWith('base ')) ?? 'base ';
    const entries = s => (s ? s.split('; ') : []);
    const base = new Map(entries(baseLine.slice(5)).map(e => [e.slice(0, e.indexOf(':')), e.slice(e.indexOf(':') + 1)]));
    const styles = new Map(rest.filter(l => l.startsWith('style ')).map(l => { const [, id, ...d] = l.split(' '); return [id, entries(d.join(' '))]; }));
    const resolve = id => { const m = new Map(base); for (const e of styles.get(id) ?? []) { if (e.startsWith('-')) m.delete(e.slice(1)); else m.set(e.slice(0, e.indexOf(':')), e.slice(e.indexOf(':') + 1)); } return m; };
    return { head, elements: rest.filter(l => !l.startsWith('base ') && !l.startsWith('style ') && l.trim()), resolve };
  });
  const x = parse(a), y = parse(b);
  for (let s = 0; s < Math.max(x.length, y.length); s++) {
    if (!x[s] || !y[s] || x[s].head !== y[s].head) return `section ${s + 1}: ${x[s]?.head ?? '(none)'} -> ${y[s]?.head ?? '(none)'}`;
    for (let i = 0; i < Math.max(x[s].elements.length, y[s].elements.length); i++) {
      const p = x[s].elements[i] ?? '(none)', q = y[s].elements[i] ?? '(none)';
      const name = l => l.slice(0, l.lastIndexOf(' ')), id = l => l.slice(l.lastIndexOf(' ') + 1);
      if (name(p) !== name(q)) return `${x[s].head} element ${i + 1}: ${p.trim()} -> ${q.trim()}`;
      const m = x[s].resolve(id(p)), n = y[s].resolve(id(q));
      const differ = [...new Set([...m.keys(), ...n.keys()])].filter(k => m.get(k) !== n.get(k)).sort();
      if (differ.length) return `${x[s].head} element ${i + 1} (${name(p).trim()}): ${differ.length} propert${differ.length === 1 ? 'y' : 'ies'}: `
        + differ.slice(0, 8).map(k => `${k}: ${m.get(k) ?? '(none)'} -> ${n.get(k) ?? '(none)'}`).join('; ');
    }
  }
  return 'the same styles, written differently';
}
const STORAGE = `JSON.stringify({ local: Object.fromEntries(Object.keys(localStorage).sort().map(k => [k, localStorage.getItem(k)])),
  session: Object.fromEntries(Object.keys(sessionStorage).sort().map(k => [k, sessionStorage.getItem(k)])) }, null, 1)`;

const written = [];
const write = (file, text) => { const at = path.join(OUT, file); mkdirSync(path.dirname(at), { recursive: true }); writeFileSync(at, text); written.push(file); };

let WIDTH = DEFAULT_WIDTH;                                // the page's width of the scenes now running (--widths)
/** One scene: a fresh browser, the page seeded with `local` (localStorage) and `look`, then `body(steps)`. */
async function scene(look, name, local, body) {
  if (ONLY && !ONLY.includes(name)) return;
  const wide = WIDTH === DEFAULT_WIDTH, pageWidth = WIDTH, tag = wide ? look : `${look}@${pageWidth}`;
  const browser = await launchEdge(`dom-${name}`, wide ? undefined : { width: pageWidth });
  const dir = `${tag}/${name}`, log = [], order = [], taken = [], dialogs = [], windows = new Map();     // target id -> session
  let step = 'open', count = 0, pending = 0, n = 0, missing = 0;
  try {
    const page = await browser.open(wide ? { consoleApi: false } : { consoleApi: false, width: pageWidth });
    const { send, evaluate } = page;
    page.on('Page.javascriptDialogOpening', p => { dialogs.push(`${step} | ${p.type}: ${p.message}`); return send('Page.handleJavaScriptDialog', { accept: false }); });
    const keyOf = request => {
      const url = new URL(request.url), body = request.postData ?? (request.postDataEntries ? request.postDataEntries.map(e => Buffer.from(e.bytes ?? '', 'base64').toString('utf8')).join('') : null);
      return { url, body, key: `${request.method} ${url.pathname}${url.search}${body === null ? '' : ` #${hash(body)}`}` };
    };
    const answer = async ({ requestId, request }) => {
      try {
        const { url, body, key } = keyOf(request);
        let reply = fixture(request.method, url, body), lost = false;
        if (!reply && REPLAY) { reply = answers[key]; if (!reply) { missing++; lost = true; reply = json(404, { detail: { message: 'FIXTURE: no answer recorded for this request' } }); } }
        if (!reply) reply = await record(key, request.method, url, body);
        if (lost) log.push({ step, key: `${key} | NOT RECORDED` });
        await page.fulfilText(requestId, reply.status, reply.contentType, reply.body);
      } catch (e) { log.push({ step, key: `ERROR ${e?.message ?? e}` }); } finally { pending--; }
    };
    // The requests the page makes as it opens, before any answer has come (its effects, in their order), are held a moment and
    // listed in that order: the burst. Later requests race with answers and timers, so each step lists its own sorted.
    let holding = true, lastArrival = 0;
    const held = [], burst = [];
    page.on('Fetch.requestPaused', params => {
      count++; pending++;
      const { key } = keyOf(params.request);
      order.push(`${step} | ${key}`);
      if (holding) { held.push(params); burst.push(key); lastArrival = Date.now(); return; }
      log.push({ step, key });
      return answer(params);
    });
    await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
    await send('Page.addScriptToEvaluateOnNewDocument', { source: FIXED_CLOCK });
    const put = Object.entries({ [LOOK_KEY]: look, ...local }).map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)}, ${JSON.stringify(v)});`).join(' ');
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (location.protocol.startsWith('http') && !sessionStorage.getItem('dom-seeded')) { sessionStorage.setItem('dom-seeded', '1'); ${put} }` });
    const popups = async () => {
      const open = (await browser.pages()).filter(t => t.id !== page.target.id && t.title.startsWith('GATOR - '));
      for (const id of [...windows.keys()]) if (!open.some(t => t.id === id)) windows.delete(id);
      for (const t of open) if (!windows.has(t.id)) windows.set(t.id, await browser.attach(t, { errors: [], prefix: `${t.title}: ` }));
      return open.sort((a, b) => (a.title < b.title ? -1 : a.title > b.title ? 1 : 0));
    };
    const snapshot = async () => {
      let text = `<!-- page -->\n${lines(await evaluate(PAGE_DOM))}\n`;
      for (const t of await popups()) {
        let dom;
        try { dom = await windows.get(t.id).evaluate(WINDOW_DOM); } catch { dom = '(closing)'; }
        text += `<!-- window: ${t.title} -->\n${lines(dom)}\n`;
      }
      return text;
    };
    /** --styles: the computed styles of the page and of each open pop-up window (by title), as described at the top. */
    const styleSnapshot = async () => {
      let text = `<!-- page -->\n${await evaluate(STYLE_DUMP)}\n`;
      for (const t of await popups()) {
        let dump;
        try { dump = await windows.get(t.id).evaluate(STYLE_DUMP); } catch { dump = '(closing)'; }
        text += `<!-- window: ${t.title} -->\n${dump}\n`;
      }
      return text;
    };
    /** Quiet: no request asked or answered and the same DOM, three looks 600 ms apart (20 s at most). */
    const settle = async () => {
      let last = null, lastCount = -1, quiet = 0;
      for (let i = 0; i < 34 && quiet < 3; i++) {
        const now = await snapshot(), seen = count;
        quiet = now === last && seen === lastCount && !pending ? quiet + 1 : 0;
        last = now; lastCount = seen;
        if (quiet < 3) await sleep(600);
      }
      return quiet >= 3 ? last : null;
    };
    const steps = {
      page, browser, evaluate,
      /** `action` (or nothing, for the page as it opened), then the quiet page written as <NN>-<label>.html. */
      async take(label, action = null) {
        step = label; taken.push(label);
        if (action) await action();
        let text = await settle();
        check(`${tag} / ${name} / ${label}: the page came to rest`, text !== null);
        const file = `${dir}/${String(++n).padStart(2, '0')}-${label}`;
        if (STYLES) {
          // the same styles twice, 300 ms apart, on the same DOM as the quiet page's; else the page settles again (5 tries)
          let styles = null;
          for (let attempt = 0; attempt < 5 && styles === null; attempt++) {
            const first = await styleSnapshot();
            await sleep(300);
            const second = await styleSnapshot(), now = await snapshot();
            if (first === second && now === text) styles = first;
            else text = (await settle()) ?? text;
          }
          check(`${tag} / ${name} / ${label}: the computed styles came to rest`, styles !== null);
          write(`${file}.styles.txt`, styles ?? await styleSnapshot());
        }
        write(`${file}.html`, text ?? await snapshot());
      },
      /** A pop-up opened by pressing `launch` (an expression in `session`, a person's click), found by its title. */
      async popup(session, launch, title, { width = 1200, height = 900 } = {}) {
        await session.evaluate(`(${launch}).click()`, true);
        const target = await browser.window(title, { except: page.target.id, ms: 10000 });
        const far = await browser.attach(target, { errors: [], prefix: `${title}: ` });
        windows.set(target.id, far);
        await far.viewport(Math.min(width, pageWidth), height);   // a narrower page (--widths) narrows its windows too
        return far;
      },
    };
    await send('Page.navigate', { url: APP });
    for (let i = 0; i < 100 && (!held.length || Date.now() - lastArrival < 250); i++) await sleep(50);
    holding = false;
    for (const params of held.splice(0)) void answer(params);
    check(`${tag} / ${name}: the page opens`, await page.until(`!!document.querySelector('header') && !!document.querySelector('.editors')`, 200));
    await steps.take('open');                             // quiet before the first press: each request belongs to the step that made it
    await body(steps);
    step = 'end';
    await sleep(1000);                                    // the page keeps its configuration 800 ms after the last change
    write(`${dir}/storage.json`, `${await evaluate(STORAGE)}\n`);
    const listed = [`open-burst (as made, before any answer): ${burst.length}`, ...burst.map(k => `  ${k}`)];
    for (const label of [...new Set([...taken, ...log.map(l => l.step)])]) {
      const mine = log.filter(l => l.step === label).map(l => l.key).sort();
      listed.push(`${label} (sorted): ${mine.length}`, ...mine.map(k => `  ${k}`));
    }
    write(`${dir}/requests.txt`, `${[...listed, ...dialogs.map(d => `dialog | ${d}`)].join('\n')}\n`);
    write(`${dir}/requests-order.txt`, `${order.join('\n')}\n`);
    check(`${tag} / ${name}: every request had an answer${REPLAY ? ' recorded' : ''}`, !missing, `${missing} missing`);
  } catch (error) { fail(`${tag} / ${name}: ${error?.stack ?? error}`); } finally { await browser.close(); }
}

// ---- the scenes ------------------------------------------------------------------------------------------------------------
const STARTER = kept.starter ?? await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
kept.starter = STARTER;
const CONFIG = { schema_version: 'gator-workbench-config-v1', ...STARTER, run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, ...STARTER.run },
  output: { experiment_name: 'fixture' }, research: {} };
const LOADED = { ...CONFIG, run: { ...CONFIG.run, mode: 'fine_tune', network: { ...NETWORK }, model_source: { run_dir: RUN, checkpoint_id: CKPT } } };
const seeded = (config, extra = {}) => ({ [CONFIG_KEY]: JSON.stringify(config), ...extra });
const FOOTER_TAB = label => `[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent.trim() === ${JSON.stringify(label)})`;
const MODE = mode => `document.querySelector('.rl-modes button[data-mode="${mode}"]')`;

try {
  for (const width of WIDTHS) for (const look of LOOKS) {
    WIDTH = width;
    await scene(look, 'fresh', {}, async s => {
      let tasks = null;
      await s.take('tasks-window', async () => { tasks = await s.popup(s.page, `${TASK_PANEL}.querySelector('.task-row button.task-list-button')`, TASKS_WINDOW, { width: 1500, height: 760 }); });
      await s.take('task-chosen', async () => {
        await tasks.until(`!!document.querySelector('table.task-table tr[data-task-key="synthetic:gpdk045_ota5"] code')`, 100);
        const at = await tasks.evaluate(`(() => { const el = document.querySelector('table.task-table tr[data-task-key="synthetic:gpdk045_ota5"] code'); el.scrollIntoView({ block: 'center' });
          const b = el.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; })()`);
        await tasks.clickAt(at, { count: 2 });
      });
    });
    await scene(look, 'tabs', seeded(CONFIG, { [HEADER_RUN_KEY]: RUN, [TRAINING_COMPARE_KEY]: JSON.stringify([RUN2]) }), async s => {
      for (const [label, file] of [['Logs', 'logs'], ['Data tables', 'data'], ['Output files', 'files'], ['Training', 'training'], ['Corner check', 'corners'], ['Run status', 'status']])
        if (await s.evaluate(`!!(${FOOTER_TAB(label)})`)) await s.take(`tab-${file}`, () => s.evaluate(`${FOOTER_TAB(label)}.click()`));
    });
    await scene(look, 'runs', seeded(CONFIG, { [HEADER_RUN_KEY]: RUN }), async s => {
      let runs = null;
      await s.take('runs-window', async () => { runs = await s.popup(s.page, `document.querySelector('footer .tabs button.run-list-button')`, RUNS_WINDOW, { width: 1500, height: 860 }); });
      await s.take('run-details', () => runs.evaluate(`[...document.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(RUN)}).querySelector('button.notes-link').click()`));
    });
    await scene(look, 'rl', seeded(CONFIG), async s => {
      let rl = null;
      await s.take('rl-window', async () => { rl = await s.popup(s.page, `document.querySelector('button.rl-networks-open')`, RL_MODEL_WINDOW, { width: 1100, height: 900 }); });
      for (const mode of ['fine_tune', 'frozen', 'scratch']) await s.take(`mode-${mode}`, () => rl.evaluate(`${MODE(mode)}.click()`));
    });
    await scene(look, 'rl-loaded', seeded(LOADED), async s => {
      let rl = null;
      await s.take('rl-window', async () => { rl = await s.popup(s.page, `document.querySelector('button.rl-networks-open')`, RL_MODEL_WINDOW, { width: 1100, height: 900 }); });
      await s.take('mode-frozen', () => rl.evaluate(`${MODE('frozen')}.click()`));
    });
    await scene(look, 'virtuoso', seeded(CONFIG), async s => {
      let cell = null;
      await s.take('virtuoso-window', async () => { cell = await s.popup(s.page, `${TASK_PANEL}.querySelector('button.virtuoso-button')`, VIRTUOSO_WINDOW, { width: 720, height: 980 }); });
      await s.take('pdk-window', () => s.popup(cell, `document.querySelector('button.pdk-open')`, PDK_WINDOW, { width: 1100, height: 900 }));
    });
    await scene(look, 'ngspice', seeded(CONFIG), async s => {
      await s.take('ngspice-window', () => s.popup(s.page, `document.querySelector('button.ngspice-button')`, NGSPICE_WINDOW, { width: 760, height: 980 }));
    });
    await scene(look, 'connection', seeded(CONFIG), async s => {
      let connection = null;
      await s.take('connection-window', async () => { connection = await s.popup(s.page, `document.querySelector('header button.connection-button')`, CONNECTION_WINDOW, { width: 660, height: 920 }); });
      await s.take('folders', () => connection.evaluate(`[...document.querySelectorAll('.connection-window button')].find(b => b.textContent.trim() === 'Folders...').click()`));
    });
    await scene(look, 'agent', seeded(CONFIG), async s => {
      let agent = null;
      await s.take('agent-window', async () => { agent = await s.popup(s.page, `document.querySelector('footer .tabs button.agent-tab')`, AGENT_WINDOW, { width: 780, height: 760 }); });
      await s.take('whats-missing', () => agent.evaluate(`document.querySelector('.agent-window button.missing').click()`));
    });
    await scene(look, 'brief', seeded(CONFIG, { [HEADER_RUN_KEY]: RUN }), async s => {
      await s.take('brief-window', () => s.popup(s.page, `document.querySelector('header button.run-chip')`, RUNNING_WINDOW, { width: 470, height: 540 }));
    });
  }
  if (!REPLAY) write('answers.json', `${JSON.stringify(kept, null, 1)}\n`);

  // ---- the comparison with a reference folder ------------------------------------------------------------------------------
  if (COMPARE) {
    const walk = (root, rel = '') => readdirSync(path.join(root, rel), { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(root, path.join(rel, e.name))
      : [path.join(rel, e.name).split(path.sep).join('/')]).filter(f => f !== 'answers.json' && !f.endsWith('/requests-order.txt'));
    const reference = walk(COMPARE), mine = walk(OUT);
    for (const file of reference) {
      if (!mine.includes(file)) { check(`identical: ${file}`, false, 'not written by this run'); continue; }
      const a = readFileSync(path.join(COMPARE, file), 'utf8'), b = readFileSync(path.join(OUT, file), 'utf8');
      if (a === b) { check(`identical: ${file}`, true); continue; }
      const x = a.split('\n'), y = b.split('\n'), i = x.findIndex((line, k) => line !== y[k]);
      if (file.endsWith('.styles.txt')) { check(`identical: ${file}`, false, styleDifference(a, b)); continue; }
      check(`identical: ${file}`, false, `line ${i + 1}: ${JSON.stringify((x[i] ?? '(end)').slice(0, 300))} -> ${JSON.stringify((y[i] ?? '(end)').slice(0, 300))}`);
    }
    for (const file of mine.filter(f => !reference.includes(f))) check(`identical: ${file}`, false, 'not in the reference');
  }
} catch (error) { fail(error); } finally { await Promise.allSettled(servers.map(s => s.close?.() ?? s.httpServer?.close())); }
console.log(`INFO  ${written.length} files in ${OUT}`);
finish();
