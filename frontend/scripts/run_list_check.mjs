// Browser check of the run window: the button at the right end of the bottom tab strip that replaced the drop-down list
// of runs, and the window of its own it opens (frontend/src/panels/RunList.tsx; this project has no frontend test runner).
// Same approach as run_control_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY /api/runs* request and every validation is answered HERE by runs
// labelled FIXTURE; other GET requests pass through and every other writing request is refused. So this check reads no
// real run and can start, stop or change NOTHING on the backend it runs against - it is safe next to a live run.
// The browser profile is new and temporary: the user's saved configuration and remembered run are not touched.
// What it pins (user request 2026-09-21): the list of runs is a button, not a drop-down; pressing it opens a window with
// every run, its start and finish time, its duration and its other facts; a DOUBLE CLICK on a row chooses the run the
// bottom tabs show (no "Show" column), "Clear" shows none; the button only reads "Runs...", the run is named to its LEFT;
// nothing in it updates by itself; an older server (no times in the list) is said in plain words. Record 7.263: the window
// has the Tasks window's folders - All runs, Unfiled and the user's own, runs ticked and moved with "Move to...", keyed by
// run folder and stored with the runs' folders (/api/run-folders, answered here), never with the tasks'. Record 7.264:
// "Started from" and "Saved model" columns, and Relationships in Details (task, started from, saved model, the runs that
// started from it, a folded history), every run named a link that shows it here and the task one that opens the Tasks window.
// Record 7.267: a run's Details have Load run (also the double click), Show results, Continue... and New run like this; Load
// run brings the model the run ended with, pinned with its network, as one Undo step; a run whose task is gone offers neither.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 40 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/run_list_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl, RUNS_WINDOW, TASKS_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('runlist');

// The page prints local time; Edge and this script run on the same Windows clock, so the expected text is built the same way.
import { two } from '../src/format.ts';                         // the page's own; this check's stamp() differs (no date: NaN)
const stamp = utc => { const d = new Date(utc); return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`; };

// ---- the runs (FIXTURE): one of every kind the list has to word ----------------------------------------------------
const ROOT = '/fixture/outputs';
const seg = (segment, entry, started_utc, ended_utc = null, end_state = null, stop_reason = null, active_seconds = null) => ({ segment, entry, started_utc, ended_utc, end_state, stop_reason, active_seconds });
const run = (n, facts) => ({ run_dir: `${ROOT}/${facts.mock === false ? '' : 'mock/'}fixture_exp__0001/runs/fixture_task/scratch__seed${n}__000${n}`, run_id: `fixture-run-${n}`, task_id: 'fixture_task:0000',
  task_name: 'fixture_task', task_definition_hash: 'fixture', mode: 'scratch', mock: true, seed: n, experiment: 'fixture_exp__0001', stop_reason: null, error: null, max_evaluations: 60,
  first_feasible_eval_count: null, resumability: null, last_seen_utc: null, paused_seconds: 0, ...facts });
const LINEAGE = { task_key: 'synthetic:gpdk045_ota5', run_kind: 'optimization', parent: null, pretraining_sources: null };
const DONE = run(1, { ...LINEAGE, encoder: 'graph_transformer', model_label: 'fixture', created_utc: '2026-09-20T16:16:40+00:00', started_utc: '2026-09-20T16:16:43+00:00', ended_utc: '2026-09-20T16:17:01+00:00', active_seconds: 17.82, state: 'completed',
  stop_reason: 'budget_exhausted', evaluations: 60, first_feasible_eval_count: 23, resumability: 'full_state',
  segments: [seg(1, 'start', '2026-09-20T16:16:43+00:00', '2026-09-20T16:17:01+00:00', 'completed', 'budget_exhausted', 17.82)] });
const RESUMED = run(2, { ...LINEAGE, encoder: 'graph_transformer', model_label: 'fixture (2)',
  parent: { run_id: 'fixture-run-1', run_dir: `${ROOT}/mock/fixture_exp__0001/runs/fixture_task/scratch__seed1__0001`, checkpoint_id: 'ckpt-000040-final', relation: 'fine_tune' },
  created_utc: '2026-09-21T10:00:00+00:00', started_utc: '2026-09-21T10:00:03+00:00', ended_utc: '2026-09-21T12:15:00+00:00', active_seconds: 900, paused_seconds: 7200,
  // its full save point was written by an older version of the optimizer code: the backend lists it as model only (7.221)
  state: 'completed', stop_reason: 'budget_exhausted', evaluations: 40, max_evaluations: 40, resumability: 'weights_only', save_point_code: 'older', mode: 'fine_tune',
  segments: [seg(1, 'start', '2026-09-21T10:00:03+00:00', '2026-09-21T10:10:00+00:00', 'paused', 'user_pause', 600), seg(2, 'resume', '2026-09-21T12:10:00+00:00', '2026-09-21T12:15:00+00:00', 'completed', 'budget_exhausted', 300)] });
const PAUSED = run(3, { ...LINEAGE, encoder: 'rgcn', created_utc: '2026-09-21T13:00:00+00:00', started_utc: '2026-09-21T13:00:04+00:00', ended_utc: '2026-09-21T13:30:00+00:00', active_seconds: 1790, state: 'paused',
  stop_reason: 'user_pause', evaluations: 25, resumability: 'full_state', segments: [seg(1, 'start', '2026-09-21T13:00:04+00:00', '2026-09-21T13:30:00+00:00', 'paused', 'user_pause', 1790)] });
const LOST = run(4, { created_utc: '2026-09-19T08:00:00+00:00', started_utc: '2026-09-19T08:00:03+00:00', ended_utc: null, last_seen_utc: '2026-09-19T08:04:00+00:00', active_seconds: 237,
  state: 'interrupted', evaluations: 31, segments: [seg(1, 'start', '2026-09-19T08:00:03+00:00')] });
const NEVER = run(5, { created_utc: '2026-09-18T08:00:00+00:00', started_utc: null, ended_utc: null, active_seconds: null, state: null, evaluations: null, segments: [seg(1, 'start', null)] });
const FAILED = run(6, { mock: false, run_kind: 'baseline_preflight', created_utc: '2026-09-17T08:00:00+00:00', started_utc: '2026-09-17T08:00:05+00:00', ended_utc: '2026-09-17T08:00:45+00:00', active_seconds: 40, state: 'failed',
  stop_reason: 'error', error: 'FIXTURE: a simulated failure, nothing real went wrong', evaluations: 2, resumability: 'none', segments: [seg(1, 'start', '2026-09-17T08:00:05+00:00', '2026-09-17T08:00:45+00:00', 'failed', 'error', 40)] });
const LIVE = run(7, { created_utc: '2026-09-21T14:00:00+00:00', started_utc: '2026-09-21T14:00:03+00:00', ended_utc: null, last_seen_utc: '2026-09-21T15:06:43+00:00', active_seconds: 4000, state: 'running',
  evaluations: 12, segments: [seg(1, 'start', '2026-09-21T14:00:03+00:00')] });
const TIMING = ['started_utc', 'ended_utc', 'last_seen_utc', 'active_seconds', 'paused_seconds', 'segments', 'task_name', 'stop_reason', 'error', 'max_evaluations'];
const older = r => Object.fromEntries(Object.entries(r).filter(([k]) => !TIMING.includes(k)));     // a row as the server listed it before it knew the times
let listed = [PAUSED, RESUMED, DONE, LOST, NEVER, FAILED];                                          // newest first, as the backend sorts; no live run yet (the page would take it over)
// Record 7.267, only in section 10: an Evaluate-only run of DONE's save point 40, and a run whose task is no longer registered.
const EVALUATED = run(8, { ...LINEAGE, mode: 'frozen', model_label: null, created_utc: '2026-09-22T09:00:00+00:00', started_utc: '2026-09-22T09:00:02+00:00', ended_utc: '2026-09-22T09:00:40+00:00',
  active_seconds: 38, state: 'completed', stop_reason: 'budget_exhausted', evaluations: 20, max_evaluations: 20, resumability: 'weights_only', segments: [],
  parent: { run_id: 'fixture-run-1', run_dir: `${ROOT}/mock/fixture_exp__0001/runs/fixture_task/scratch__seed1__0001`, checkpoint_id: 'ckpt-000040-final', relation: 'frozen' } });
const GONE = run(9, { ...LINEAGE, task_key: 'real:fixture_gone', created_utc: '2026-09-16T08:00:00+00:00', started_utc: '2026-09-16T08:00:02+00:00', ended_utc: '2026-09-16T08:01:00+00:00',
  active_seconds: 58, state: 'completed', stop_reason: 'budget_exhausted', evaluations: 10, max_evaluations: 10, resumability: 'full_state', segments: [] });
// The save points this check answers for (POST /api/runs/model): DONE's newest (60) and its save point 40, an RGCN 32/4/2.
const RGCN = { encoder_type: 'rgcn', hidden_dim: 32, heads: 4, layers: 2, structural_encoding: 'none' };
const described = (run_dir, checkpoint_id, evaluations) => ({ description: { checkpoint_id, path: `${run_dir}/checkpoints/${checkpoint_id}`, kind: 'final', source_run_id: 'fixture-run-1',
  source_task_id: 'fixture_task:0000', mode: 'scratch', created_utc: '2026-09-20T16:17:01+00:00', metadata_version: 'FIXTURE', counters: { evaluations_committed: evaluations, learner_updates: evaluations - 8, replay_size: evaluations },
  restoration_capability: 'full_state', restorable_components: [], missing_components: [], contract: { model_config: RGCN, sac_config: {} }, file_problems: [] },
  vocabulary: { name: 'standard', label: 'standard (8 generic kinds)', loaded: true }, compatibility: { mode: 'fine_tune', compatible: true, checks: [], checkpoint_id, source_run_id: 'fixture-run-1' } });
const statusOf = r => ({ state: r.state, run_id: r.run_id, mode: r.mode, entry: 'start', provenance: r.mock ? 'mock' : 'real', mock: r.mock, worker_alive: r.state === 'running', run_dir: r.run_dir,
  heartbeat_utc: r.last_seen_utc ?? r.ended_utc, stop_reason: r.stop_reason, error: r.error, active_workers: [], concurrency: 2, threads_per_job: 1, learner_updates: 36, first_feasible: null,
  budget: { max_evaluations: r.max_evaluations, max_launches: null, max_retries: 0, charged: r.evaluations ?? 0, reserved: 0, in_flight: 0, completed: (r.evaluations ?? 0) - 1, failed: 1, released: 0,
    remaining: r.max_evaluations - (r.evaluations ?? 0), launches: r.evaluations ?? 0, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: { evaluation_id: 'fixture', feasible: false, metrics: { gain_db: 41.5 }, violation: 0.125, variables: [{ variable_id: 'input_pair_width', value: 2.3455777695373655e-6, unit: 'm', optimized: true }, { variable_id: 'load_capacitance', value: 2.5e-13, unit: 'F', optimized: true }] }, persistence: null,   // a LIST, as the engine writes it
  last_checkpoint_utc: r.ended_utc, connection_profile_id: null, bytes_written: 1234567, active_seconds: r.active_seconds, paths: { run_dir: r.run_dir }, connection: { overall: 'not_applicable' },
  save_point: 'ckpt-000040', save_point_code: r.save_point_code ?? 'current',
  summary: { time: { active_seconds: r.active_seconds, paused_seconds: r.paused_seconds, sum_job_runtime_seconds: 412.5 }, output: { resumability: 'full_state', completeness: 'complete', latest_checkpoint: 'ckpt-000040' } },
  manifest: { mode: r.mode, mock: r.mock, task_id: r.task_id, seeds: { target_seed: r.seed }, source_model: { run_id: null }, budgets: { max_evaluations: r.max_evaluations },
    mock_notice: r.mock ? 'FIXTURE MOCK DATA: nothing was run.' : null } });
const validReport = validConfiguration({ mock: true });

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);     // as "Load task" merges it
  const page = await browser.open();
  const { send, evaluate, until, fulfil, consoleErrors } = page;
  const refused = []; const seen = [];
  const runFolders = { version: 1, folders: {}, assignments: {} }; let folderSerial = 0;
  // RESUMED's own configuration as it started (record 7.267, New run like this): a fine-tune of DONE, its recorded source still "latest".
  let failModel = null, holdModel = false; const heldModel = [];               // record 7.270: see the /api/runs/model answer
  const recorded = { [RESUMED.run_dir]: { ...CONFIG, run: { ...CONFIG.run, mode: 'fine_tune', model_label: 'fixture (2)', max_evaluations: 40, seed: 2, max_retries: 1,
    network: RGCN, advanced: { ...(CONFIG.run.advanced ?? {}), batch_size: 16 }, model_source: { run_dir: DONE.run_dir, checkpoint_id: 'latest' } } },
    // Record 7.322: PAUSED as a run searched by Bayesian optimization (its configuration names the optimizer; a SAC run's never does)
    [PAUSED.run_dir]: { ...CONFIG, run: { ...CONFIG.run, mode: 'scratch', optimizer: 'bayes', max_evaluations: 60, seed: 3 } } };
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, validReport);
    if (name.startsWith('/api/run-folders')) {                                   // the runs' folders (7.263): a store of this check's own
      const body = JSON.parse(request.postData ?? '{}');
      if (request.method === 'POST') { const id = String(++folderSerial).padStart(32, '0'); runFolders.folders[id] = body.name.trim(); return fulfil(requestId, 200, { ...runFolders, created_id: id }); }
      if (request.method === 'PUT') body.run_dirs.forEach(dir => { if (body.folder_id) runFolders.assignments[dir] = body.folder_id; else delete runFolders.assignments[dir]; });
      if (request.method === 'PATCH') runFolders.folders[name.split('/').at(-1)] = body.name;
      if (request.method === 'DELETE') { const id = name.split('/').at(-1); delete runFolders.folders[id];
        Object.keys(runFolders.assignments).forEach(dir => { if (runFolders.assignments[dir] === id) delete runFolders.assignments[dir]; }); }
      return fulfil(requestId, 200, runFolders);
    }
    if (name.startsWith('/api/runs')) seen.push(name === '/api/runs/status' ? `status ${url.searchParams.get('run_dir')}` : name);
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: listed });
    if (name === '/api/runs/status') { const r = [...listed, LIVE].find(x => x.run_dir === url.searchParams.get('run_dir')); return r ? fulfil(requestId, 200, statusOf(r)) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [] });
    if (name === '/api/runs/model') {                                            // record 7.267: the save points Load run and New run like this read
      const body = JSON.parse(request.postData ?? '{}'), dir = `${ROOT}/mock/fixture_exp__0001/runs/fixture_task/scratch__seed1__0001`;
      // Record 7.270: a read that fails for another reason than a missing save point, and a read held back to answer late.
      if (failModel && body.run_dir === failModel) return fulfil(requestId, 500, { detail: { message: 'FIXTURE: the server is busy' } });
      if (holdModel && body.run_dir === dir && body.checkpoint_id === 'ckpt-000040-final' && !body.config) { heldModel.push({ requestId, body }); return; }
      const point = body.run_dir !== dir ? null : body.checkpoint_id === 'ckpt-000040-final' ? ['ckpt-000040-final', 40] : ['latest', 'ckpt-000060-final'].includes(body.checkpoint_id) ? ['ckpt-000060-final', 60] : null;
      return point ? fulfil(requestId, 200, described(dir, ...point)) : fulfil(requestId, 404, { detail: { message: 'FIXTURE: no save point here' } });
    }
    if (name === '/api/runs/download' && url.searchParams.get('path') === 'effective_config.json') {   // record 7.267: New run like this
      const c = recorded[url.searchParams.get('run_dir')];
      return c ? fulfil(requestId, 200, c) : fulfil(requestId, 404, { detail: 'FIXTURE: No such file' });
    }
    if (name.startsWith('/api/runs')) return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${name} is not expected in this check` } });
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const lists = () => seen.filter(s => s === '/api/runs').length;
  const statusFor = r => seen.filter(s => s === `status ${r.run_dir}`).length;

  // ---- the window: a second page, found by its title, with a DevTools session of its own ---------------------------
  const pages = () => browser.pages();
  const windowTarget = present => browser.window(RUNS_WINDOW, { present, except: page.target.id });
  const BUTTON = `document.querySelector('footer .tabs button.run-list-button')`;
  const WINDOW = `document.querySelector('.run-window')`;
  let far = null, farPage = null;
  const openWindow = async () => {
    far = await browser.popup(page, BUTTON, RUNS_WINDOW, { width: 1500, height: 860, ready: WINDOW });
    farPage = far.target;
    await sleep(500);
  };
  // Record 7.291 (user request 2026-10-09: "after selecting one target task, model or run, close the pop up window"): a run
  // chosen - a double click, Show results, Load run and New run like this once they went through, Continue... - closes the window.
  const windowOpen = async () => (await pages()).some(t => t.title === RUNS_WINDOW);
  const closedByChoice = async () => { try { await windowTarget(false); far.close(); return true; } catch { return false; } };
  // The table as a user reads it: one object per run row, keyed by the column titles.
  const table = () => far.evaluate(`(() => { const t = ${WINDOW}.querySelector('table.run-table'); if (!t) return null; const heads = [...t.tHead.rows[0].cells].map(h => h.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim());
    return [...t.tBodies[0].rows].filter(tr => !tr.classList.contains('run-details-row')).map(tr => { const cells = [...tr.children]; const row = { current: tr.getAttribute('aria-current') === 'true', folder: tr.title, buttons: [...tr.querySelectorAll('button')].map(b => b.textContent.trim()).join() };
      heads.forEach((h, i) => { if (h) row[h] = cells[i].innerText.replace(/\\s+/g, ' ').trim(); }); row.finishedTitle = cells[heads.indexOf('Finished')].title; row.durationTitle = cells[heads.indexOf('Duration')].title; return row; }); })()`);
  const rowOf = (rows, r) => rows.find(x => x.folder === r.run_dir);
  const pressIn = (r, labelText) => far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)});
    const b = tr && [...tr.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(labelText)}); if (!b) return false; b.click(); return true; })()`, true);
  // A REAL double click (two presses, the second with clickCount 2) in the run window: on the run's Task cell, or on its "Details" button.
  const doubleClick = async (r, onDetails = false) => {
    const at = await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)}); if (!tr) return null;
      const el = ${onDetails} ? tr.querySelector('button') : tr.children[4]; el.scrollIntoView({ block: 'center' }); const b = el.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; })()`);
    if (!at) return false;
    await far.clickAt(at, { count: 2 });
    return true;
  };
  const pressTop = labelText => far.evaluate(`(() => { const b = [...${WINDOW}.querySelectorAll('.row button')].find(b => b.textContent.trim() === ${JSON.stringify(labelText)}); if (!b || b.disabled) return false; b.click(); return true; })()`, true);
  const pressTitle = title => far.evaluate(`(() => { const h = [...${WINDOW}.querySelectorAll('table.run-table thead th')].find(h => h.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim() === ${JSON.stringify(title)}); if (!h) return false; h.click(); return true; })()`);
  const typeFilter = async value => { await far.evaluate(`(() => { const i = ${WINDOW}.querySelector('input.run-filter'); i.focus(); i.select(); })()`); if (value) await far.send('Input.insertText', { text: value });
    else await far.setValue(`${WINDOW}.querySelector('input.run-filter')`, '', { event: 'input' }); await sleep(300); };
  const strip = () => evaluate(`(() => { const b = ${BUTTON}, c = document.querySelector('footer .tabs .run-list-current'); return b ? { text: b.innerText.replace(/\\s+/g, ' ').trim(), open: b.classList.contains('open'),
    current: c ? c.innerText.replace(/\\s+/g, ' ').trim() : null, currentIsLeft: !!c && !b.contains(c) && c.getBoundingClientRect().right <= b.getBoundingClientRect().left + 0.5, selects: document.querySelectorAll('footer .tabs select').length,
    right: Math.round(document.querySelector('footer .tabs').getBoundingClientRect().right - b.getBoundingClientRect().right), overflowX: document.documentElement.scrollWidth > window.innerWidth } : null; })()`);
  const bottomText = () => evaluate(`document.querySelector('footer .bottom-body').innerText`);
  const shot = (session, selector, name) => (session === 'main' ? page : far).shot(path.join(out, name), `document.querySelector(${JSON.stringify(selector)})`, { maxHeight: 1400, beyond: true });

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, run: null, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${BUTTON})`, 150))) throw new Error('the run button never appeared; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  await sleep(1500);                                                             // room for anything the page would do on its own

  // ---- 1. the bottom tab strip: a button where the drop-down list was ------------------------------------------------
  let s = await strip();
  check('the bottom tab strip has no drop-down list of runs any more', s.selects === 0, JSON.stringify(s));
  check('it has ONE button at its right end, and its caption is only "Runs..."', s.text === 'Runs...' && s.right >= 0 && s.right < 12 && !s.overflowX, JSON.stringify(s));
  check('which run is shown ("No run selected") is plain text to the LEFT of the button, not inside it', s.current === 'No run selected' && s.currentIsLeft, JSON.stringify(s));
  check('page load reads the run list once and asks for no run status', lists() === 1 && !seen.some(x => x.startsWith('status')), seen.join(', '));
  check('with no run chosen the Run status tab says so', /No run selected\./.test(await bottomText()));
  await shot('main', 'footer .tabs', 'runs-1-strip.png');

  // ---- 2. pressing it opens the run window with every run ----------------------------------------------------------------
  await openWindow();
  check('pressing the button opens a window of its own, titled "GATOR - runs"', !!farPage && farPage.title === RUNS_WINDOW);
  check('pressing the button read the list again (it is the request to see the current runs)', lists() === 2, `${lists()} list request(s)`);
  check('the strip button still reads only "Runs..." and is marked as open', (await strip()).text === 'Runs...' && (await strip()).open, JSON.stringify(await strip()));
  let rows = await table();
  check('every run is a row, newest first', !!rows && rows.map(r => r.folder).join() === listed.map(r => r.run_dir).join(), JSON.stringify(rows?.map(r => r.Started)));
  const titles = Object.keys(rows?.[0] ?? {});
  check('the columns are start, finish and duration first, then what the run was and came to',
    ['Started', 'Finished', 'Duration', 'State', 'Task', 'Mode', 'Seed', 'Evaluations', 'First feasible', 'Experiment', 'Data', 'Can continue'].every(t => titles.includes(t)), titles.join(', '));
  let r = rowOf(rows, DONE);
  check('a finished run shows when it started and finished (local time) and how long it worked', r.Started === stamp(DONE.created_utc) && r.Finished === stamp(DONE.ended_utc) && r.Duration === '17.8 s', JSON.stringify(r));
  check('... and what it was and came to', /^completed\s*budget used up$/.test(r.State) && r.Task === 'fixture_task' && r.Mode === 'New model Graph Transformer' && r.Seed === '1' && r.Evaluations === '60 / 60'
    && r['First feasible'] === 'at 23' && r.Experiment === 'fixture_exp__0001' && r.Data === 'MOCK' && r['Can continue'] === 'yes', JSON.stringify(r));
  r = rowOf(rows, RESUMED);
  check('a run that was paused and continued: the duration is its working time, the pause is named, not counted', r.Duration === '15 min 00 s' && /sat paused for 2 h 00 min/.test(r.durationTitle)
    && r.Finished === stamp(RESUMED.ended_utc) && r['First feasible'] === 'none' && r.Evaluations === '40 / 40', JSON.stringify(r));
  r = rowOf(rows, PAUSED);
  check('a paused run reads "(paused)" next to the time, so it is not taken for finished', r.Finished === `${stamp(PAUSED.ended_utc)} (paused)` && /can continue/.test(r.finishedTitle) && r.Duration === '29 min 50 s', JSON.stringify(r));
  r = rowOf(rows, LOST);
  check('a run whose worker died has no finish time: it reads "last seen ..."', r.Finished === `last seen ${stamp(LOST.last_seen_utc)}` && /without a clean end/.test(r.finishedTitle) && r.Duration === '3 min 57 s' && /^interrupted/.test(r.State), JSON.stringify(r));
  r = rowOf(rows, NEVER);
  check('a run that never began shows dashes, not zeros', r.Finished === '-' && r.Duration === '-' && r.State === 'not started' && r.Evaluations === '- / 60' && r['First feasible'] === '-', JSON.stringify(r));
  r = rowOf(rows, FAILED);
  check('a real run reads "real", a failed one "failed" with its reason', r.Data === 'real' && /^failed\s*error$/.test(r.State) && r['Can continue'] === 'no' && r.Duration === '40.0 s', JSON.stringify(r));
  check('no row is marked as shown, and there is no "Show" column: after the tick box the table starts at "Started" and a row\'s last button is "Details"',
    rows.every(x => !x.current && x.buttons.split(',').pop() === 'Details' && x.buttons.split(',').length <= 2)
    && (await far.evaluate(`(() => { const h = [...${WINDOW}.querySelectorAll('table.run-table thead th')]; return !!h[0].querySelector('input[type=checkbox]') && h[1].textContent.replace(/[\\u25B2\\u25BC]/g, '').trim(); })()`)) === 'Started', JSON.stringify(rows.map(x => x.buttons)));
  check('the window says what a double click does: it loads the run (record 7.267)', /Double click a run to load it: its task comes into the editors, its model becomes the next run's model, and the bottom tabs of the workbench show its results/.test(await far.evaluate(`${WINDOW}.innerText`)));
  check('the long explanation is folded: "What the columns mean" is closed', (await far.evaluate(`(() => { const d = ${WINDOW}.querySelector('details.more'); return d && !d.open && d.querySelector('summary').textContent; })()`)) === 'What the columns mean');
  check('the window says how many runs it lists, when it read them, and that nothing updates by itself', /^6 runs under the output folder, read at \d\d:\d\d:\d\d\. Nothing here updates by itself\.$/.test(await far.evaluate(`${WINDOW}.querySelector('.run-count').textContent`)),
    await far.evaluate(`${WINDOW}.querySelector('.run-count').textContent`));
  const fit = await far.evaluate(`(() => { const w = ${WINDOW}.querySelector('.scroll'); return { wide: w.scrollWidth, room: w.clientWidth, page: document.documentElement.scrollWidth > window.innerWidth }; })()`);
  check('the table fits the window without sideways scrolling', fit.wide <= fit.room + 1 && !fit.page, JSON.stringify(fit));
  await shot('far', '.run-window', 'runs-2-window.png');

  // ---- 3. a double click on a row chooses the run the bottom tabs show ------------------------------------------------------
  check('a run\'s row can be double clicked', await doubleClick(RESUMED));
  check('the workbench\'s Run status tab now shows that run', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(RESUMED.run_dir)})`));
  s = await strip();
  check('the text left of the strip button names the run: start time, task, mode, seed, state; the caption stays "Runs..."', s.current === `${stamp(RESUMED.created_utc)} · fixture_task · Fine-tune, seed 2 · completed · MOCK` && s.currentIsLeft && s.text === 'Runs...' && !s.overflowX, JSON.stringify(s));
  check('the run window closes once a run is chosen (record 7.291)', await closedByChoice());
  check('choosing a run did not read the list again', lists() === 2, `${lists()} list request(s)`);
  await openWindow();
  rows = await table();
  check('opened again, that row, and only that row, is marked as shown', rowOf(rows, RESUMED).current && rows.filter(x => x.current).length === 1);
  await doubleClick(DONE, true); await sleep(500);
  rows = await table();
  check('a double click on a row\'s "Details" does NOT choose that run, and the window stays open', rowOf(rows, RESUMED).current && !rowOf(rows, DONE).current && rows.filter(x => x.current).length === 1
    && await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(RESUMED.run_dir)})`) && await windowOpen());
  await pressIn(DONE, 'Hide details');                                          // however the two presses left that run's details: closed for what follows

  // ---- 4. "Details": everything else the run recorded ----------------------------------------------------------------------
  const before = statusFor(PAUSED);
  await pressIn(PAUSED, 'Details');
  check('the details of a run are read when they are opened (one request), not before', await until(`true`) && await (async () => { for (let i = 0; i < 40 && statusFor(PAUSED) === before; i++) await sleep(100); return statusFor(PAUSED) === before + 1; })(), `${statusFor(PAUSED) - before} request(s)`);
  await sleep(400);
  const details = await far.evaluate(`(() => { const d = ${WINDOW}.querySelector('.run-details'); return d ? { facts: Object.fromEntries([...d.querySelectorAll('table.run-facts tr')].map(tr => [tr.children[0].textContent, tr.children[1].textContent])),
    segments: [...d.querySelectorAll('table.run-segments tbody tr')].map(tr => [...tr.children].map(td => td.textContent)) } : null; })()`);
  check('they name the run folder, the run id and the task', details?.facts['Run folder'] === PAUSED.run_dir && details.facts['Run id'] === PAUSED.run_id && details.facts['Task id'] === 'fixture_task:0000', JSON.stringify(details?.facts));
  check('... the times in full', details?.facts['Created'] === stamp(PAUSED.created_utc) && details.facts['Worker began'] === stamp(PAUSED.started_utc) && details.facts['Came to rest'] === stamp(PAUSED.ended_utc) && details.facts['Worked for'] === '29 min 50 s'
    && /^6 min 53 s \(parallel jobs added up/.test(details.facts['Summed simulator job time']), JSON.stringify(details?.facts));
  check('... the budget, the launches, the best design and the saved state', /^25 charged \/ 60 \(completed 24, failed 1, in flight 0, remaining 35\)$/.test(details?.facts['Budget']) && /^25 \(retries 0, cache hits 0\)$/.test(details.facts['Spectre launches'])
    && /^infeasible\s+gain_db=41\.5\s+violation 0\.125$/.test(details.facts['Best design']) && details.facts['Best design variables'] === 'input_pair_width=2.34558e-6 m  load_capacitance=2.5e-13 F' && details.facts['First feasibility'] === 'not reached' && /^full_state \(complete output, latest save ckpt-000040\)$/.test(details.facts['Saved state'])
    && details.facts['Model loaded at the start'] === 'none (random weights)' && details.facts['Data written'] === '1.2 MiB' && details.facts['Stop reason'] === 'user_pause', JSON.stringify(details?.facts));
  check('empty facts are left out instead of printed as blanks', !('Error' in (details?.facts ?? {})) && !('Paused between segments' in (details?.facts ?? {})));
  await pressIn(PAUSED, 'Hide details');
  await pressIn(RESUMED, 'Details'); await sleep(600);
  const resumedDetails = await far.evaluate(`(() => { const d = ${WINDOW}.querySelector('.run-details'); return { count: ${WINDOW}.querySelectorAll('.run-details').length, paused: [...d.querySelectorAll('table.run-facts tr')].find(tr => tr.children[0].textContent === 'Paused between segments')?.children[1].textContent,
    saved: [...d.querySelectorAll('table.run-facts tr')].find(tr => tr.children[0].textContent === 'Saved state')?.children[1].textContent,
    segments: [...d.querySelectorAll('table.run-segments tbody tr')].map(tr => [...tr.children].map(td => td.textContent)) }; })()`);
  check('one run\'s details are open at a time', resumedDetails.count === 1);
  check('a continued run lists its segments: how each began and ended, and how long it worked', JSON.stringify(resumedDetails.segments) === JSON.stringify([
    ['1', 'start', stamp('2026-09-21T10:00:03+00:00'), stamp('2026-09-21T10:10:00+00:00'), 'paused', 'user_pause', '10 min 00 s'],
    ['2', 'resume', stamp('2026-09-21T12:10:00+00:00'), stamp('2026-09-21T12:15:00+00:00'), 'completed', 'budget_exhausted', '5 min 00 s']]) && resumedDetails.paused === '2 h 00 min', JSON.stringify(resumedDetails));
  check('the details of a run saved by an older version of the optimizer code say why it cannot be continued (7.221)',
    resumedDetails.saved === 'model only: the latest save ckpt-000040 is a full save point written by an older version of the optimizer code - only that version can continue it; fine-tune and frozen still load its model',
    JSON.stringify(resumedDetails.saved));
  await shot('far', '.run-window', 'runs-3-details.png');
  await pressIn(FAILED, 'Details'); await sleep(600);
  check('a failed run\'s details carry its error', (await far.evaluate(`[...${WINDOW}.querySelectorAll('table.run-facts tr')].find(tr => tr.children[0].textContent === 'Error')?.children[1].textContent`)) === FAILED.error);
  await pressIn(FAILED, 'Hide details');
  check('... and its row reads "model only" under Can continue (7.221)', rowOf(await table(), RESUMED)?.['Can continue'] === 'model only',
    JSON.stringify(rowOf(await table(), RESUMED)));

  // ---- 4b. relationships (record 7.264) ---------------------------------------------------------------------------------------
  rows = await table();
  check('"Started from" says where a run\'s model came from: a template, a saved model at its save point, nothing for a baseline; "Saved model" names its own',
    rowOf(rows, DONE)['Started from'] === 'template GT' && rowOf(rows, PAUSED)['Started from'] === 'template RGCN' && rowOf(rows, RESUMED)['Started from'] === 'fixture @ 40'
    && rowOf(rows, FAILED)['Started from'] === '-' && rowOf(rows, DONE)['Saved model'] === 'fixture' && rowOf(rows, RESUMED)['Saved model'] === 'fixture (2)',
    JSON.stringify(rows.map(x => [x.folder.slice(-4), x['Started from'], x['Saved model']])));
  const RELATIONS = `Object.fromEntries([...(${WINDOW}.querySelector('table.run-relations')?.querySelectorAll('tr') ?? [])].map(tr => [tr.children[0].textContent, tr.children[1].innerText.replace(/\\s+/g, ' ').trim()]))`;
  const detailsOpen = r => far.until(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)});
    return !!tr && [...tr.querySelectorAll('button')].pop().getAttribute('aria-expanded') === 'true' && !!${WINDOW}.querySelector('table.run-relations'); })()`, 50);
  await far.evaluate(`[...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(RESUMED.run_dir)}).querySelector('button.item-link').click()`);
  check('the link in "Started from" shows that run here, its Details open', await detailsOpen(DONE));
  let relations = await far.evaluate(RELATIONS);
  check('Details name the task, where the model came from, the model it saved and the runs that started from it', relations['Task']?.startsWith('synthetic:gpdk045_ota5')
    && relations['Started from'] === 'template GT (a new model)' && relations['Saved model'].startsWith('fixture') && /fine_tune \(fixture \(2\)\)/.test(relations['Runs that started from its model'] ?? ''),
    JSON.stringify(relations));
  await far.evaluate(`[...${WINDOW}.querySelector('table.run-relations').querySelectorAll('tr')].find(tr => tr.children[0].textContent === 'Runs that started from its model').querySelector('button.item-link').click()`);
  check('... and a run that started from it is a link too', await detailsOpen(RESUMED));
  relations = await far.evaluate(RELATIONS);
  check('a fine-tune names the run and save point it loaded', /^fixture @ 40 \(fine-tuned from its save point ckpt-000040-final\)$/.test(relations['Started from'] ?? ''), JSON.stringify(relations));
  const history = await far.evaluate(`(() => { const d = ${WINDOW}.querySelector('details.run-history'); d.open = true;
    return { summary: d.querySelector('summary').textContent, steps: [...d.querySelectorAll('li')].map(li => li.innerText.replace(/\\s+/g, ' ').trim()) }; })()`);
  check('its history is folded: one model behind it, oldest first, from the template', history.summary === '1 model behind this run, oldest first' && history.steps[0] === 'template GT'
    && history.steps[1].startsWith('synthetic:gpdk045_ota5 · scratch · 60 evaluations · fixture') && /^this run - loaded the one above at its save point ckpt-000040-final$/.test(history.steps[2]),
    JSON.stringify(history));
  await far.evaluate(`[...${WINDOW}.querySelector('table.run-relations').querySelectorAll('tr')].find(tr => tr.children[0].textContent === 'Task').querySelector('button.item-link').click()`, true);
  const taskTarget = await browser.window(TASKS_WINDOW).catch(() => null);
  const tasksWindow = taskTarget && await browser.attach(taskTarget);
  check('the task is a link: the Tasks window opens at it, its Details open, nothing chosen', !!tasksWindow
    && await tasksWindow.until(`(() => { const tr = [...document.querySelectorAll('table.task-table tbody > tr')].find(tr => tr.dataset.taskKey === 'synthetic:gpdk045_ota5');
      return !!tr && [...tr.querySelectorAll('button')].pop().getAttribute('aria-expanded') === 'true'; })()`, 80));
  tasksWindow?.close(); if (taskTarget) { await send('Target.closeTarget', { targetId: taskTarget.id }); await browser.window(TASKS_WINDOW, { present: false }); }
  check('following the links chose nothing: the bottom tabs show the run they showed', await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(RESUMED.run_dir)})`));
  await pressIn(RESUMED, 'Hide details');

  // ---- 5. filter and sort -------------------------------------------------------------------------------------------------------
  await typeFilter('paused');
  rows = await table();
  check('the filter narrows the list by any word of a row (here: the state)', rows.length === 1 && rows[0].folder === PAUSED.run_dir, rows.map(x => x.State).join(' | '));
  await typeFilter('real');
  check('... "real" finds the real run, "mock" is how the others are found', (await table()).map(x => x.folder).join() === FAILED.run_dir);
  await typeFilter('nothing-matches-this');
  check('a filter that matches nothing says so', /No run matches the filter in this folder\./.test(await far.evaluate(`${WINDOW}.innerText`)) && (await table()).length === 0);
  await typeFilter('');
  check('an emptied filter brings every run back', (await table()).length === 6);
  await pressTitle('Duration'); await sleep(300);
  rows = await table();
  check('pressing "Duration" sorts the longest run first, and a run without a duration last', rows[0].folder === PAUSED.run_dir && rows[1].folder === RESUMED.run_dir && rows[rows.length - 1].folder === NEVER.run_dir, rows.map(x => x.Duration).join(' | '));
  await pressTitle('Duration'); await sleep(300);
  rows = await table();
  check('pressing it again sorts the shortest first; the run without a duration stays last', rows[0].folder === DONE.run_dir && rows[rows.length - 1].folder === NEVER.run_dir, rows.map(x => x.Duration).join(' | '));
  await pressTitle('Finished'); await sleep(300);
  rows = await table();
  check('pressing "Finished" sorts the run that finished last first', rows[0].folder === PAUSED.run_dir && rows[1].folder === RESUMED.run_dir, rows.map(x => x.Finished).join(' | '));
  await pressTitle('Started'); await sleep(300);

  // ---- 5b. folders (record 7.263): the Tasks window's folders, for runs ----------------------------------------------------------
  await far.send('Page.enable');
  const replies = [];
  far.on('Page.javascriptDialogOpening', () => far.send('Page.handleJavaScriptDialog', replies.shift() ?? { accept: false }));
  const nav = id => far.evaluate(`${WINDOW}.querySelector('.task-folders [data-folder-id="${id}"]').click()`);
  const tick = r => far.evaluate(`[...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)}).querySelector('input[type="checkbox"]').click()`);
  const moveTo = id => far.evaluate(`(() => { const s = ${WINDOW}.querySelector('select[aria-label="Move selected runs to folder"]'); s.value = ${JSON.stringify(id)}; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const settled = async () => { await sleep(150); return far.until(`!${WINDOW}.querySelector('.task-move-bar [role="status"]')`, 50); };
  const folderText = id => far.evaluate(`${WINDOW}.querySelector('.task-folders [data-folder-id="${id}"]')?.textContent ?? null`);
  const pressFolderButton = label => far.evaluate(`[...${WINDOW}.querySelectorAll('.task-folders button')].find(b => b.textContent.trim() === ${JSON.stringify(label)}).click()`, true);
  check('the run window has folders, as the Tasks window: All runs and Unfiled, every run unfiled', (await folderText('all')) === 'All runs6' && (await folderText('unfiled')) === 'Unfiled6'
    && (await far.evaluate(`${WINDOW}.querySelector('.task-folders').getAttribute('aria-label')`)) === 'Run folders', `${await folderText('all')} / ${await folderText('unfiled')}`);
  replies.push({ accept: true, promptText: 'Pilot' }); await pressFolderButton('New folder'); await settled();
  const pilot = Object.keys(runFolders.folders)[0];
  check('"New folder" makes one - stored with the runs\' folders - and opens it, empty', !!pilot && runFolders.folders[pilot] === 'Pilot'
    && (await table()).length === 0 && /This folder is empty\. Select runs in All runs, then use Move to/.test(await far.evaluate(`${WINDOW}.innerText`)), JSON.stringify(runFolders));
  await nav('all'); await sleep(200);
  await tick(DONE); await tick(PAUSED); await sleep(200);
  check('ticked runs are counted as selected', /6 shown · 2 selected/.test(await far.evaluate(`${WINDOW}.querySelector('.task-move-bar').textContent`)),
    await far.evaluate(`${WINDOW}.querySelector('.task-move-bar').textContent`));
  await moveTo(pilot); await settled();
  check('"Move to..." puts exactly those runs in the folder, by their run folder', JSON.stringify(Object.keys(runFolders.assignments).sort()) === JSON.stringify([DONE.run_dir, PAUSED.run_dir].sort())
    && Object.values(runFolders.assignments).every(id => id === pilot), JSON.stringify(runFolders.assignments));
  check('the counts follow: Pilot 2, Unfiled 4, All runs 6', (await folderText(pilot)) === 'Pilot2' && (await folderText('unfiled')) === 'Unfiled4' && (await folderText('all')) === 'All runs6');
  rows = await table();
  check('in All runs a run in a folder names it under its date', rowOf(rows, DONE).Started === `${stamp(DONE.created_utc)} Pilot` && rowOf(rows, LOST).Started === stamp(LOST.created_utc), JSON.stringify(rowOf(rows, DONE)));
  await nav(pilot); await sleep(200);
  check('the folder shows its runs only', (await table()).map(x => x.folder).sort().join() === [DONE.run_dir, PAUSED.run_dir].sort().join());
  check('a double click there still shows a run in the bottom tabs', await doubleClick(PAUSED)
    && await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(PAUSED.run_dir)})`));
  check('... and closes the window; opened again, the folders are as they were', await closedByChoice());
  await openWindow(); await far.send('Page.enable');
  far.on('Page.javascriptDialogOpening', () => far.send('Page.handleJavaScriptDialog', replies.shift() ?? { accept: false }));
  await nav(pilot); await sleep(200);
  replies.push({ accept: true, promptText: 'Pilot runs' }); await pressFolderButton('Rename'); await settled();
  check('Rename renames the folder', runFolders.folders[pilot] === 'Pilot runs' && (await folderText(pilot)) === 'Pilot runs2');
  replies.push({ accept: true }); await pressFolderButton('Delete folder'); await settled();
  check('Delete folder deletes no run: its runs go back to Unfiled', Object.keys(runFolders.folders).length === 0 && Object.keys(runFolders.assignments).length === 0
    && (await folderText('unfiled')) === 'Unfiled6' && (await table()).length === 6, JSON.stringify(runFolders));
  await nav('all'); await sleep(200);
  await shot('far', '.run-window', 'runs-3b-folders.png');

  // ---- 6. nothing updates by itself; "Refresh list" does ---------------------------------------------------------------------
  const quiet = lists(); await sleep(4000);
  check('with the window open the list is not read on a timer', lists() === quiet, `${lists() - quiet} request(s) in 4 s`);
  listed = [LIVE, ...listed];
  check('"Refresh list" is there', await pressTop('Refresh list'));
  check('it reads the list once', await (async () => { for (let i = 0; i < 40 && lists() === quiet; i++) await sleep(100); await sleep(500); return lists() === quiet + 1; })(), `${lists() - quiet} request(s)`);
  rows = await table();
  r = rowOf(rows, LIVE);
  check('a run that is working reads "still running" and its duration "so far"', !!r && r.Finished === 'still running' && r.Duration === '1 h 06 min so far' && /^running/.test(r.State) && r.Evaluations === '12 / 60' && r['Can continue'] === '-', JSON.stringify(r));
  check('the count follows', /^7 runs under the output folder/.test(await far.evaluate(`${WINDOW}.querySelector('.run-count').textContent`)));

  // ---- 7. "Clear": the bottom tabs show no run -----------------------------------------------------------------------------------
  check('"Clear" is there while a run is shown (and no "Show no run" any more)', !(await pressTop('Show no run')) && await pressTop('Clear'));
  check('the bottom tabs show no run again and the strip button says so', await until(`/No run selected\\./.test(document.querySelector('footer .bottom-body').innerText)`) && (await strip()).current === 'No run selected', JSON.stringify(await strip()));
  check('no row is marked as shown, and "Clear" is off', (await table()).every(x => !x.current) && !(await pressTop('Clear')));

  // ---- 8. an older workbench server: no times in the list ----------------------------------------------------------------------
  listed = listed.map(older);
  await pressTop('Refresh list'); await sleep(900);
  rows = await table();
  check('rows of an older server show dashes for finish and duration, and the task from its id', rows.every(x => x.Duration === '-' && (x.Finished === '-' || x.Finished === 'still running')) && rowOf(rows, DONE).Task === 'fixture_task' && rowOf(rows, DONE).Evaluations === '60', JSON.stringify(rowOf(rows, DONE)));
  check('the window says in plain words that the server has to be restarted for the times', /older than this page and does not report when a run finished or how long it took\.\s+Restart it/.test(await far.evaluate(`${WINDOW}.querySelector('p.warn')?.textContent ?? ''`)));
  listed = [];
  await pressTop('Refresh list'); await sleep(900);
  check('an output folder without runs says so instead of showing an empty table', /No run yet under this output folder\./.test(await far.evaluate(`${WINDOW}.innerText`)) && (await table()) === null && !(await far.evaluate(`!!${WINDOW}.querySelector('p.warn')`)));
  listed = [PAUSED, RESUMED, DONE, LOST, NEVER, FAILED];

  // ---- 9. closing and opening again ------------------------------------------------------------------------------------------------
  await send('Target.closeTarget', { targetId: farPage.id }); await windowTarget(false); far.close();   // the user closes the window with its own X
  check('after the window is closed the strip button is no longer marked as open', await until(`!${BUTTON}.classList.contains('open')`) && (await strip()).text === 'Runs...', JSON.stringify(await strip()));
  await openWindow();
  check('pressing the button again opens the window again, with the current list', (await table())?.length === 6);
  await doubleClick(DONE);
  check('a run chosen there is shown in the workbench', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DONE.run_dir)})`));
  check('... and the window closed', await closedByChoice());
  await openWindow();
  await evaluate(`${BUTTON}.click()`, true); await sleep(800);
  check('pressing the button while the window is open opens no second window', (await pages()).filter(t => t.title === RUNS_WINDOW).length === 1);
  await shot('main', 'footer', 'runs-4-footer-with-run.png');
  await send('Target.closeTarget', { targetId: farPage.id }); await windowTarget(false); far.close();

  // ---- 10. the actions in Details (record 7.267; plan "Load run" and "Existing runs: continued in place") -----------------------------
  // Sections 3 and 9 loaded runs with a double click: RESUMED (a fine-tune with no save point of its own here: the one it started
  // from, DONE's 40) and DONE (its newest, 60). Two Undo steps take the page back to New model.
  const storedRun = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')?.run ?? null`);
  const runWhen = async (test, tries = 60) => { for (let i = 0; i < tries; i++) { const x = await storedRun(); if (test(x)) return x; await sleep(100); } return storedRun(); };
  const undo = () => evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  const banner = () => evaluate(`document.querySelector('.banner')?.textContent ?? ''`);
  const modeOf = x => x?.mode ?? 'scratch';                 // a configuration without a Mode is New model, as the backend reads it
  const sameNet = (a, b) => !!a && ['encoder_type', 'hidden_dim', 'heads', 'layers'].every(f => a[f] === b[f]);
  let draft = await runWhen(x => x?.model_source?.run_dir === DONE.run_dir);
  check('(set-up) section 9\'s double click loaded DONE: Fine-tune from its newest save point, pinned', draft?.mode === 'fine_tune' && draft.model_source.checkpoint_id === 'ckpt-000060-final', JSON.stringify(draft?.model_source));
  await undo();
  draft = await runWhen(x => x?.model_source?.checkpoint_id === 'ckpt-000040-final');
  check('... one Undo goes back to section 3\'s load of RESUMED: the save point it started from, DONE\'s 40', draft?.mode === 'fine_tune' && draft.model_source.run_dir === DONE.run_dir, JSON.stringify(draft?.model_source));
  await undo();
  draft = await runWhen(x => !x?.model_source?.run_dir);
  check('... and one more to New model, no saved model', modeOf(draft) === 'scratch' && !draft.model_source?.run_dir, JSON.stringify(draft));
  listed = [EVALUATED, PAUSED, RESUMED, DONE, LOST, NEVER, FAILED, GONE];
  await openWindow();
  const openDetails = async rr => { if (!(await windowOpen())) await openWindow(); await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(rr.run_dir)});
    const b = [...tr.querySelectorAll('button')].find(b => b.textContent.trim() === 'Details'); if (b) b.click(); })()`, true);
    return far.until(`[...${WINDOW}.querySelectorAll('tr.run-details-row')].some(row => row.previousElementSibling?.title === ${JSON.stringify(rr.run_dir)} && !!row.querySelector('.run-actions'))`, 40); };
  const ACTIONS = `${WINDOW}.querySelector('tr.run-details-row .run-actions')`;
  const actions = () => far.evaluate(`[...${ACTIONS}.querySelectorAll('button')].map(b => b.textContent.trim() + (b.disabled ? ' (off)' : ''))`);
  const act = label => far.evaluate(`[...${ACTIONS}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)}).click()`, true);
  /** Press an action that goes through: true once the window closed after it. */
  const actAndClose = async label => { await act(label); return closedByChoice(); };
  check('(set-up) the window lists the eight runs', (await table())?.length === 8);
  check('a run\'s Details offer Load run, Show results, Continue... and New run like this', await openDetails(DONE)
    && JSON.stringify(await actions()) === JSON.stringify(['Load run', 'Show results', 'Continue...', 'New run like this']), JSON.stringify(await actions()));
  // a task that is no longer registered
  await openDetails(GONE);
  check('a run whose task is no longer registered: Load run and New run like this are off, and the reason stands beside them',
    JSON.stringify(await actions()) === JSON.stringify(['Load run (off)', 'Show results', 'Continue...', 'New run like this (off)'])
    && /Not offered: its task real:fixture_gone is no longer registered/.test(await far.evaluate(`${ACTIONS}.querySelector('.run-load-why')?.textContent ?? ''`)), JSON.stringify(await actions()));
  check('... its double click shows it, and changes nothing in the draft', await doubleClick(GONE) && await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(GONE.run_dir)})`, 40)
    && modeOf(await runWhen(x => !!x, 5)) === 'scratch');
  check('... and closes the window', await closedByChoice());
  await openDetails(FAILED);
  check('a run that names no registered task: the same, with its own reason', /Not offered: the run names no registered task/.test(await far.evaluate(`${ACTIONS}.querySelector('.run-load-why')?.textContent ?? ''`)));
  // Load run: the model the run ended with, pinned, with its network; one Undo step; the run's results shown
  await openDetails(DONE);
  check('Load run closes the window once the run is loaded', await actAndClose('Load run'));
  draft = await runWhen(x => x?.model_source?.run_dir === DONE.run_dir);
  check('Load run of a trained run: its newest save point, pinned (a concrete id, never "latest"), in Fine-tune', draft?.mode === 'fine_tune' && draft.model_source.checkpoint_id === 'ckpt-000060-final', JSON.stringify(draft?.model_source));
  check('... with the model\'s network in the same step', sameNet(draft?.network, RGCN), JSON.stringify(draft?.network));
  check('... the bottom tabs show the run', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DONE.run_dir)})`, 40));
  check('... and the message names the run, its task (the page\'s own: the editors stay) and the model', /^Loaded run fixture_task \d\d-\d\d \d\d:\d\d: task synthetic:gpdk045_ota5 \(already on the page: the editors stay as they were\), Fine-tune from fixture @ 60\. Undo takes it back\.$/.test(await banner()), await banner());
  await undo();
  draft = await runWhen(x => !x?.model_source?.run_dir);
  check('one Undo takes the model and the Mode back together', modeOf(draft) === 'scratch' && !draft.model_source?.run_dir && !sameNet(draft.network, RGCN), JSON.stringify({ mode: draft?.mode, source: draft?.model_source, net: draft?.network }));
  await openDetails(EVALUATED); await actAndClose('Load run');
  draft = await runWhen(x => x?.model_source?.run_dir === DONE.run_dir);
  check('Load run of an Evaluate-only run: the save point it evaluated (its weights never changed), in Fine-tune', draft?.mode === 'fine_tune' && draft.model_source.checkpoint_id === 'ckpt-000040-final'
    && /Fine-tune from fixture @ 40\./.test(await banner()), `${JSON.stringify(draft?.model_source)} | ${await banner()}`);
  await openDetails(PAUSED); await actAndClose('Load run');
  check('Load run of a run without a save point (and none it started from): the model stays as it was, and the message says so', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(PAUSED.run_dir)})`, 40)
    && /the model as it was: this run has no save point and loaded none\./.test(await banner()) && (await storedRun())?.model_source?.checkpoint_id === 'ckpt-000040-final', await banner());
  await undo();
  draft = await runWhen(x => !x?.model_source?.run_dir);
  check('(set-up) one Undo takes the Evaluate-only run\'s model back', modeOf(draft) === 'scratch', JSON.stringify(draft?.model_source));
  // New run like this: the run's settings, its source from its lineage - never the "latest" its configuration recorded
  await openDetails(RESUMED);
  check('New run like this closes the window once taken', await actAndClose('New run like this'));
  draft = await runWhen(x => x?.model_source?.run_dir === DONE.run_dir);
  check('New run like this repeats the run: its Mode, budget, seed, limits, name, training values and network', draft?.mode === 'fine_tune' && draft.max_evaluations === 40 && draft.seed === 2 && draft.max_retries === 1
    && draft.model_label === 'fixture (2)' && draft.advanced?.batch_size === 16 && sameNet(draft.network, RGCN), JSON.stringify(draft));
  check('... from the save point it started from, pinned - not the "latest" its configuration recorded', draft?.model_source?.checkpoint_id === 'ckpt-000040-final', JSON.stringify(draft?.model_source));
  check('... the shown run stays, and the message says what the next run repeats', await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(PAUSED.run_dir)})`)
    && /^The next run repeats fixture_task \d\d-\d\d \d\d:\d\d: task synthetic:gpdk045_ota5, Fine-tune from fixture @ 40, 40 evaluations, seed 2/.test(await banner()), await banner());
  await undo();
  draft = await runWhen(x => !x?.model_source?.run_dir);
  check('one Undo takes all of it back', modeOf(draft) === 'scratch' && draft.seed !== 2, JSON.stringify(draft));
  // Record 7.322 (review of 2026-10-11): the optimizer is the repeated run's own. It used to stay the draft's, so a run
  // searched by Bayesian optimization repeated as a SAC run without a word, and a SAC run from a Bayesian draft as a Bayesian one.
  await openDetails(PAUSED); await actAndClose('New run like this');
  draft = await runWhen(x => x?.optimizer === 'bayes');
  check('New run like this of a run searched by Bayesian optimization repeats it as one, and the message says so', draft?.optimizer === 'bayes' && modeOf(draft) === 'scratch'
    && draft.seed === 3 && /New model searched by Bayesian optimization/.test(await banner()), `${JSON.stringify(draft)} | ${await banner()}`);
  await openDetails(RESUMED); await actAndClose('New run like this');
  draft = await runWhen(x => x?.model_source?.run_dir === DONE.run_dir && x?.seed === 2);
  check('... and a SAC run repeated from that Bayesian draft is a SAC run again: the draft names no optimizer', !!draft && !('optimizer' in draft) && draft.mode === 'fine_tune'
    && !/Bayesian/.test(await banner()), `${JSON.stringify(draft)} | ${await banner()}`);
  await undo();
  draft = await runWhen(x => x?.optimizer === 'bayes');
  await undo();
  draft = await runWhen(x => !x?.optimizer && !x?.model_source?.run_dir);
  check('(set-up) two Undo steps take both repeats back', modeOf(draft) === 'scratch' && !draft.optimizer && draft.seed !== 2 && draft.seed !== 3, JSON.stringify(draft));
  // Record 7.270 (Astra's review of 2026-10-07): a model read that FAILS - not a missing save point - stops Load run; it used to
  // load the run's parent model instead and say it had worked. And an older Load run answered late never overwrites a newer one.
  failModel = RESUMED.run_dir;
  await openDetails(RESUMED); await act('Load run');
  check('a model read that fails (the server busy, not a missing save point) stops Load run, and the message says so',
    await until(`/^Run fixture_task \\d\\d-\\d\\d \\d\\d:\\d\\d was not loaded: its model could not be read \\(.+\\)\\. Nothing changed\\.$/.test(document.querySelector('.banner')?.textContent ?? '')`, 40), await banner());
  draft = await runWhen(x => !!x, 10);
  check('... nothing changed: no model chosen - not its parent\'s - and the bottom tabs still show the run they showed', modeOf(draft) === 'scratch' && !draft.model_source?.run_dir
    && await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(PAUSED.run_dir)})`), JSON.stringify(draft?.model_source));
  check('... and the window stays open: no run was loaded (record 7.291)', await windowOpen());
  failModel = null; holdModel = true;
  await openDetails(EVALUATED); await act('Load run');                            // the save point it evaluated is held back
  check('(set-up) an Evaluate-only run\'s Load run waits for its model', await (async () => { for (let i = 0; i < 40 && !heldModel.length; i++) await sleep(100); return heldModel.length === 1; })());
  check('... the window stays open while it waits', await windowOpen());
  await openDetails(DONE); await actAndClose('Load run');
  draft = await runWhen(x => x?.model_source?.checkpoint_id === 'ckpt-000060-final');
  check('meanwhile a newer Load run lands: DONE, its newest save point', draft?.model_source?.checkpoint_id === 'ckpt-000060-final'
    && await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DONE.run_dir)})`, 40), JSON.stringify(draft?.model_source));
  holdModel = false;
  const late = heldModel.shift(); await fulfil(late.requestId, 200, described(late.body.run_dir, 'ckpt-000040-final', 40)); await sleep(1500);
  draft = await runWhen(x => !!x, 5);
  check('... and the older one, answered late, changes nothing: the newer run and its model stay', draft?.model_source?.checkpoint_id === 'ckpt-000060-final'
    && await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DONE.run_dir)})`) && /^Loaded run fixture_task .*Fine-tune from fixture @ 60\./.test(await banner()),
    `${JSON.stringify(draft?.model_source)} | ${await banner()}`);
  await undo();
  draft = await runWhen(x => !x?.model_source?.run_dir);
  check('(set-up) one Undo takes DONE\'s model back', modeOf(draft) === 'scratch', JSON.stringify(draft?.model_source));
  // Continue...: Run status shows the run with its budget form open; nothing is continued by the press
  await openDetails(PAUSED);
  await shot('far', '.run-window', 'runs-5-actions.png');
  check('Continue... closes the window', await actAndClose('Continue...'));
  check('Continue... shows the run under Run status with its budget form open', await until(`!!document.querySelector('footer form.continue-form')`, 40)
    && await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(PAUSED.run_dir)})`));
  check('... and continues nothing by itself', !seen.includes('/api/runs/continue'));

  reportRefused(refused);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
});
