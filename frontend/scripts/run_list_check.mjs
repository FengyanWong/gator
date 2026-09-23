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
// nothing in it updates by itself; an older server (no times in the list) is said in plain words.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 40 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/run_list_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('runlist');

// The page prints local time; Edge and this script run on the same Windows clock, so the expected text is built the same way.
const two = n => String(n).padStart(2, '0');
const stamp = utc => { const d = new Date(utc); return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`; };

// ---- the runs (FIXTURE): one of every kind the list has to word ----------------------------------------------------
const ROOT = '/fixture/outputs';
const seg = (segment, entry, started_utc, ended_utc = null, end_state = null, stop_reason = null, active_seconds = null) => ({ segment, entry, started_utc, ended_utc, end_state, stop_reason, active_seconds });
const run = (n, facts) => ({ run_dir: `${ROOT}/${facts.mock === false ? '' : 'mock/'}fixture_exp__0001/runs/fixture_task/scratch__seed${n}__000${n}`, run_id: `fixture-run-${n}`, task_id: 'fixture_task:0000',
  task_name: 'fixture_task', task_definition_hash: 'fixture', mode: 'scratch', mock: true, seed: n, experiment: 'fixture_exp__0001', stop_reason: null, error: null, max_evaluations: 60,
  first_feasible_eval_count: null, resumability: null, last_seen_utc: null, paused_seconds: 0, ...facts });
const DONE = run(1, { created_utc: '2026-09-20T16:16:40+00:00', started_utc: '2026-09-20T16:16:43+00:00', ended_utc: '2026-09-20T16:17:01+00:00', active_seconds: 17.82, state: 'completed',
  stop_reason: 'budget_exhausted', evaluations: 60, first_feasible_eval_count: 23, resumability: 'full_state',
  segments: [seg(1, 'start', '2026-09-20T16:16:43+00:00', '2026-09-20T16:17:01+00:00', 'completed', 'budget_exhausted', 17.82)] });
const RESUMED = run(2, { created_utc: '2026-09-21T10:00:00+00:00', started_utc: '2026-09-21T10:00:03+00:00', ended_utc: '2026-09-21T12:15:00+00:00', active_seconds: 900, paused_seconds: 7200,
  state: 'completed', stop_reason: 'budget_exhausted', evaluations: 40, max_evaluations: 40, resumability: 'full_state', mode: 'fine_tune',
  segments: [seg(1, 'start', '2026-09-21T10:00:03+00:00', '2026-09-21T10:10:00+00:00', 'paused', 'user_pause', 600), seg(2, 'resume', '2026-09-21T12:10:00+00:00', '2026-09-21T12:15:00+00:00', 'completed', 'budget_exhausted', 300)] });
const PAUSED = run(3, { created_utc: '2026-09-21T13:00:00+00:00', started_utc: '2026-09-21T13:00:04+00:00', ended_utc: '2026-09-21T13:30:00+00:00', active_seconds: 1790, state: 'paused',
  stop_reason: 'user_pause', evaluations: 25, resumability: 'full_state', segments: [seg(1, 'start', '2026-09-21T13:00:04+00:00', '2026-09-21T13:30:00+00:00', 'paused', 'user_pause', 1790)] });
const LOST = run(4, { created_utc: '2026-09-19T08:00:00+00:00', started_utc: '2026-09-19T08:00:03+00:00', ended_utc: null, last_seen_utc: '2026-09-19T08:04:00+00:00', active_seconds: 237,
  state: 'interrupted', evaluations: 31, segments: [seg(1, 'start', '2026-09-19T08:00:03+00:00')] });
const NEVER = run(5, { created_utc: '2026-09-18T08:00:00+00:00', started_utc: null, ended_utc: null, active_seconds: null, state: null, evaluations: null, segments: [seg(1, 'start', null)] });
const FAILED = run(6, { mock: false, created_utc: '2026-09-17T08:00:00+00:00', started_utc: '2026-09-17T08:00:05+00:00', ended_utc: '2026-09-17T08:00:45+00:00', active_seconds: 40, state: 'failed',
  stop_reason: 'error', error: 'FIXTURE: a simulated failure, nothing real went wrong', evaluations: 2, resumability: 'none', segments: [seg(1, 'start', '2026-09-17T08:00:05+00:00', '2026-09-17T08:00:45+00:00', 'failed', 'error', 40)] });
const LIVE = run(7, { created_utc: '2026-09-21T14:00:00+00:00', started_utc: '2026-09-21T14:00:03+00:00', ended_utc: null, last_seen_utc: '2026-09-21T15:06:43+00:00', active_seconds: 4000, state: 'running',
  evaluations: 12, segments: [seg(1, 'start', '2026-09-21T14:00:03+00:00')] });
const TIMING = ['started_utc', 'ended_utc', 'last_seen_utc', 'active_seconds', 'paused_seconds', 'segments', 'task_name', 'stop_reason', 'error', 'max_evaluations'];
const older = r => Object.fromEntries(Object.entries(r).filter(([k]) => !TIMING.includes(k)));     // a row as the server listed it before it knew the times
let listed = [PAUSED, RESUMED, DONE, LOST, NEVER, FAILED];                                          // newest first, as the backend sorts; no live run yet (the page would take it over)
const statusOf = r => ({ state: r.state, run_id: r.run_id, mode: r.mode, entry: 'start', provenance: r.mock ? 'mock' : 'real', mock: r.mock, worker_alive: r.state === 'running', run_dir: r.run_dir,
  heartbeat_utc: r.last_seen_utc ?? r.ended_utc, stop_reason: r.stop_reason, error: r.error, active_workers: [], concurrency: 2, threads_per_job: 1, learner_updates: 36, first_feasible: null,
  budget: { max_evaluations: r.max_evaluations, max_launches: null, max_retries: 0, charged: r.evaluations ?? 0, reserved: 0, in_flight: 0, completed: (r.evaluations ?? 0) - 1, failed: 1, released: 0,
    remaining: r.max_evaluations - (r.evaluations ?? 0), launches: r.evaluations ?? 0, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: { evaluation_id: 'fixture', feasible: false, metrics: { gain_db: 41.5 }, violation: 0.125, variables: [{ variable_id: 'input_pair_width', value: 2.3455777695373655e-6, unit: 'm', optimized: true }, { variable_id: 'load_capacitance', value: 2.5e-13, unit: 'F', optimized: true }] }, persistence: null,   // a LIST, as the engine writes it
  last_checkpoint_utc: r.ended_utc, connection_profile_id: null, bytes_written: 1234567, active_seconds: r.active_seconds, paths: { run_dir: r.run_dir }, connection: { overall: 'not_applicable' },
  summary: { time: { active_seconds: r.active_seconds, paused_seconds: r.paused_seconds, sum_job_runtime_seconds: 412.5 }, output: { resumability: 'full_state', completeness: 'complete', latest_checkpoint: 'ckpt-000040' } },
  manifest: { mode: r.mode, mock: r.mock, task_id: r.task_id, seeds: { target_seed: r.seed }, source_model: { run_id: null }, budgets: { max_evaluations: r.max_evaluations },
    mock_notice: r.mock ? 'FIXTURE MOCK DATA: nothing was run.' : null } });
const validReport = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: true };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture' }, research: {} };     // as "Load task" merges it
  const page = await browser.open();
  const { send, evaluate, until, fulfil, consoleErrors } = page;
  const refused = []; const seen = [];
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, validReport);
    if (name.startsWith('/api/runs')) seen.push(name === '/api/runs/status' ? `status ${url.searchParams.get('run_dir')}` : name);
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: listed });
    if (name === '/api/runs/status') { const r = [...listed, LIVE].find(x => x.run_dir === url.searchParams.get('run_dir')); return r ? fulfil(requestId, 200, statusOf(r)) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [] });
    if (name.startsWith('/api/runs')) return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${name} is not expected in this check` } });
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const lists = () => seen.filter(s => s === '/api/runs').length;
  const statusFor = r => seen.filter(s => s === `status ${r.run_dir}`).length;

  // ---- the window: a second page, found by its title, with a DevTools session of its own ---------------------------
  const pages = () => browser.pages();
  const windowTarget = present => browser.window('GATOR - runs', { present, except: page.target.id });
  const attachTo = target => browser.attach(target, { errors: consoleErrors, prefix: 'window: ' });
  const BUTTON = `document.querySelector('footer .tabs button.run-list-button')`;
  const WINDOW = `document.querySelector('.run-window')`;
  let far = null, farPage = null;
  const openWindow = async () => {
    await evaluate(`${BUTTON}.click()`, true);
    farPage = await windowTarget(true);
    far = await attachTo(farPage);
    await far.send('Emulation.setDeviceMetricsOverride', { width: 1500, height: 860, deviceScaleFactor: 1, mobile: false });   // a headless popup ignores the requested size
    for (let i = 0; i < 50 && !(await far.evaluate(`!!(${WINDOW})`)); i++) await sleep(100);
    await sleep(500);
  };
  // The table as a user reads it: one object per run row, keyed by the column titles.
  const table = () => far.evaluate(`(() => { const t = ${WINDOW}.querySelector('table.run-table'); if (!t) return null; const heads = [...t.querySelectorAll('thead th')].map(h => h.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim());
    return [...t.querySelectorAll('tbody > tr:not(.run-details-row)')].map(tr => { const cells = [...tr.children]; const row = { current: tr.getAttribute('aria-current') === 'true', folder: tr.title, buttons: [...tr.querySelectorAll('button')].map(b => b.textContent.trim()).join() };
      heads.forEach((h, i) => { if (h) row[h] = cells[i].innerText.replace(/\\s+/g, ' ').trim(); }); row.finishedTitle = cells[1].title; row.durationTitle = cells[2].title; return row; }); })()`);
  const rowOf = (rows, r) => rows.find(x => x.folder === r.run_dir);
  const pressIn = (r, labelText) => far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)});
    const b = tr && [...tr.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(labelText)}); if (!b) return false; b.click(); return true; })()`, true);
  // A REAL double click (two presses, the second with clickCount 2) in the run window: on the run's Task cell, or on its "Details" button.
  const doubleClick = async (r, onDetails = false) => {
    const at = await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)}); if (!tr) return null;
      const el = ${onDetails} ? tr.querySelector('button') : tr.children[4]; el.scrollIntoView({ block: 'center' }); const b = el.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; })()`);
    if (!at) return false;
    for (const clickCount of [1, 2]) for (const type of ['mousePressed', 'mouseReleased']) await far.send('Input.dispatchMouseEvent', { type, x: at.x, y: at.y, button: 'left', clickCount });
    return true;
  };
  const pressTop = labelText => far.evaluate(`(() => { const b = [...${WINDOW}.querySelectorAll('.row button')].find(b => b.textContent.trim() === ${JSON.stringify(labelText)}); if (!b || b.disabled) return false; b.click(); return true; })()`, true);
  const pressTitle = title => far.evaluate(`(() => { const h = [...${WINDOW}.querySelectorAll('table.run-table thead th')].find(h => h.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim() === ${JSON.stringify(title)}); if (!h) return false; h.click(); return true; })()`);
  const typeFilter = async value => { await far.evaluate(`(() => { const i = ${WINDOW}.querySelector('input.run-filter'); i.focus(); i.select(); })()`); if (value) await far.send('Input.insertText', { text: value });
    else await far.evaluate(`(() => { const i = ${WINDOW}.querySelector('input.run-filter'); Object.getOwnPropertyDescriptor(i.ownerDocument.defaultView.HTMLInputElement.prototype, 'value').set.call(i, ''); i.dispatchEvent(new i.ownerDocument.defaultView.Event('input', { bubbles: true })); })()`); await sleep(300); };
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
  check('pressing the button opens a window of its own, titled "GATOR - runs"', !!farPage && farPage.title === 'GATOR - runs');
  check('pressing the button read the list again (it is the request to see the current runs)', lists() === 2, `${lists()} list request(s)`);
  check('the strip button still reads only "Runs..." and is marked as open', (await strip()).text === 'Runs...' && (await strip()).open, JSON.stringify(await strip()));
  let rows = await table();
  check('every run is a row, newest first', !!rows && rows.map(r => r.folder).join() === listed.map(r => r.run_dir).join(), JSON.stringify(rows?.map(r => r.Started)));
  const titles = Object.keys(rows?.[0] ?? {});
  check('the columns are start, finish and duration first, then what the run was and came to',
    ['Started', 'Finished', 'Duration', 'State', 'Task', 'Mode', 'Seed', 'Evaluations', 'First feasible', 'Experiment', 'Data', 'Can continue'].every(t => titles.includes(t)), titles.join(', '));
  let r = rowOf(rows, DONE);
  check('a finished run shows when it started and finished (local time) and how long it worked', r.Started === stamp(DONE.created_utc) && r.Finished === stamp(DONE.ended_utc) && r.Duration === '17.8 s', JSON.stringify(r));
  check('... and what it was and came to', /^completed\s*budget_exhausted$/.test(r.State) && r.Task === 'fixture_task' && r.Mode === 'scratch' && r.Seed === '1' && r.Evaluations === '60 / 60'
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
  check('no row is marked as shown, and there is no "Show" column: the table starts at "Started" and a row\'s only button is "Details"', rows.every(x => !x.current && x.buttons === 'Details')
    && (await far.evaluate(`${WINDOW}.querySelector('table.run-table thead th').textContent.replace(/[\\u25B2\\u25BC]/g, '').trim()`)) === 'Started', JSON.stringify(rows.map(x => x.buttons)));
  check('the window says how a run is shown: by a double click', /Double click a run to show it in the bottom tabs/.test(await far.evaluate(`${WINDOW}.innerText`)));
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
  check('the text left of the strip button names the run: start time, task, mode, seed, state; the caption stays "Runs..."', s.current === `${stamp(RESUMED.created_utc)} | fixture_task | fine_tune seed2 | completed [MOCK]` && s.currentIsLeft && s.text === 'Runs...' && !s.overflowX, JSON.stringify(s));
  rows = await table();
  check('in the window that row, and only that row, is marked as shown; the window stayed open', rowOf(rows, RESUMED).current && rows.filter(x => x.current).length === 1);
  check('the double click leaves no selected word behind in the row', (await far.evaluate(`String(getSelection())`)) === '');
  await doubleClick(DONE, true); await sleep(500);
  rows = await table();
  check('a double click on a row\'s "Details" does NOT choose that run', rowOf(rows, RESUMED).current && !rowOf(rows, DONE).current && rows.filter(x => x.current).length === 1
    && await evaluate(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(RESUMED.run_dir)})`));
  await pressIn(DONE, 'Hide details');                                          // however the two presses left that run's details: closed for what follows
  check('choosing a run did not read the list again', lists() === 2, `${lists()} list request(s)`);

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
    segments: [...d.querySelectorAll('table.run-segments tbody tr')].map(tr => [...tr.children].map(td => td.textContent)) }; })()`);
  check('one run\'s details are open at a time', resumedDetails.count === 1);
  check('a continued run lists its segments: how each began and ended, and how long it worked', JSON.stringify(resumedDetails.segments) === JSON.stringify([
    ['1', 'start', stamp('2026-09-21T10:00:03+00:00'), stamp('2026-09-21T10:10:00+00:00'), 'paused', 'user_pause', '10 min 00 s'],
    ['2', 'resume', stamp('2026-09-21T12:10:00+00:00'), stamp('2026-09-21T12:15:00+00:00'), 'completed', 'budget_exhausted', '5 min 00 s']]) && resumedDetails.paused === '2 h 00 min', JSON.stringify(resumedDetails));
  await shot('far', '.run-window', 'runs-3-details.png');
  await pressIn(FAILED, 'Details'); await sleep(600);
  check('a failed run\'s details carry its error', (await far.evaluate(`[...${WINDOW}.querySelectorAll('table.run-facts tr')].find(tr => tr.children[0].textContent === 'Error')?.children[1].textContent`)) === FAILED.error);
  await pressIn(FAILED, 'Hide details');

  // ---- 5. filter and sort -------------------------------------------------------------------------------------------------------
  await typeFilter('paused');
  rows = await table();
  check('the filter narrows the list by any word of a row (here: the state)', rows.length === 1 && rows[0].folder === PAUSED.run_dir, rows.map(x => x.State).join(' | '));
  await typeFilter('real');
  check('... "real" finds the real run, "mock" is how the others are found', (await table()).map(x => x.folder).join() === FAILED.run_dir);
  await typeFilter('nothing-matches-this');
  check('a filter that matches nothing says so', /No run matches the filter\./.test(await far.evaluate(`${WINDOW}.innerText`)) && (await table()).length === 0);
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
  await evaluate(`${BUTTON}.click()`, true); await sleep(800);
  check('pressing the button while the window is open opens no second window', (await pages()).filter(t => t.title === 'GATOR - runs').length === 1);
  await shot('main', 'footer', 'runs-4-footer-with-run.png');
  await send('Target.closeTarget', { targetId: farPage.id }); await windowTarget(false); far.close();

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
