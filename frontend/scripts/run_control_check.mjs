// Browser check of the header's run buttons: ONE main button Start -> Pause -> Resume, and Abort next to it
// (frontend/src/panels/RunControl.tsx; there is no frontend test runner in this project).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY /api/runs/* request and every validation is answered HERE by a small
// simulated run labelled FIXTURE; other GET requests pass through and every other writing request is refused. So this
// check can start, pause, continue or cancel NOTHING on the backend it runs against - it is safe next to a live run.
// The browser profile is new and temporary: the user's saved configuration and remembered run are not touched.
// What it pins (user request 2026-09-21): after Start the button reads Pause, after Pause it reads Resume; Abort sits
// next to it; a pause/abort waits for the simulation in flight (Force abort is the second step); Resume continues the
// SAME run without asking for a budget; a real run asks for the budget again; the header keeps a live run's Pause
// whatever run the bottom tabs show, also across a reload, and never offers a second Start meanwhile - nor, in the Run
// status tab, a Continue of another run (2026-09-29); a remembered run that is gone is let go of, not polled for ever.
// Record 7.261 (the launcher, launch.ts): the second button reads "Let go" on a paused run; Continue... opens a budget form
// (no browser prompt) that refuses a separator typo, a fraction and a total below the evaluations used, its field wide
// enough for "more than 12000" (branch record SIF-66); a launch carries a
// request id, and after a reload during a start the page asks what became of it instead of sending it again; a refusal
// stays beside its action; the backend's continuation check says why Continue cannot go on before the press, with its
// alternative as a button; a run taken over, or a task's baseline, names the paused run the header lets go of.
// Branch record SIF-83: Pause asks first on a run searched by Bayesian optimization (it cannot come back), and Force abort
// says what it gives up: a waiting pause (no Resume or Continue... after it), or an abort's "stopped" end; on a run that
// cannot come back anyway it advises no waiting (review of SIF-83).
// Branch record SIF-89: a run that pauses after connection failures, completes or fails with no press says so on the line
// under the header, and Run status leads with the reason in red, then Continue... and Export status, above its facts.
// Branch record SIF-91: Output settings' output root locks while the header's run starts or works, whatever run the tabs show;
// "Use this folder" in a folder list opened before the Start too (SIF-91 review; GET /api/output/browse answered with a FIXTURE).
// Branch record SIF-98: Run status, under its bar, and the end of the run chip's tooltip give the run brief's working time and
// time left.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 60 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/run_control_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, reportRefused, RUN_KEY, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl, RUNS_WINDOW, RUNNING_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('runcontrol');

// ---- the simulated run (FIXTURE): one status "file" that the page polls, advanced by scripted steps ----------------
const DIR = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed0__0001';
// `active`: the working time the status gives (null until the run brief reads it, branch record SIF-78). `output` and
// `run`: the run's own effective_config.json, as Pause reads it (`run.optimizer`: branch record SIF-83). `error`: the
// status's error, as a run that fails or pauses by itself gives one (branch record SIF-89).
const sim = { dir: DIR, mock: true, state: null, alive: false, charged: 0, max: 60, stop_reason: null, error: null, beat: 0, steps: [], output: {}, run: {}, starts: 0, calibration: null, active: null };
const listed = () => sim.state ? [{ run_dir: DIR, run_id: 'fixture-run', task_id: 'fixture_task:0000', task_definition_hash: 'fixture', mode: 'scratch', mock: sim.mock, seed: 0,
  created_utc: '2026-09-21T00:00:00+00:00', state: sim.state, experiment: 'fixture_experiment__0001', evaluations: null, first_feasible_eval_count: null, resumability: null }] : [];
const statusOf = () => {
  const step = sim.steps.shift();
  if (step) Object.assign(sim, step);
  else if (sim.alive && sim.state === 'running' && sim.charged < sim.max) sim.charged++;
  const at = new Date(Date.UTC(2026, 8, 21, 0, 0, 0) + 1000 * ++sim.beat).toISOString();
  return { state: sim.state, run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: sim.mock ? 'mock' : 'real', mock: sim.mock, worker_alive: sim.alive,
    run_dir: sim.dir, heartbeat_utc: at, stop_reason: sim.stop_reason, error: sim.error, active_workers: [], concurrency: 1, learner_updates: 0, first_feasible: null,
    budget: { max_evaluations: sim.max, max_launches: null, max_retries: 0, charged: sim.charged, reserved: 0, in_flight: sim.alive && sim.state === 'running' ? 1 : 0,
      completed: sim.charged, failed: 0, released: 0, remaining: sim.max - sim.charged, launches: sim.charged, retries: 0, cache_hits: 0, first_feasible: null },
    best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: sim.dir }, connection: { overall: 'not_applicable' }, summary: null, calibration: sim.calibration,
    active_seconds: sim.active,
    manifest: { mode: 'scratch', mock: sim.mock, task_id: 'fixture_task:0000', seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: sim.max },
      mock_notice: sim.mock ? 'FIXTURE MOCK DATA: nothing was started.' : null } };
};
const started = () => ({ run_dir: sim.dir, run_id: 'fixture-run', mock: sim.mock, worker_pid: 1, paths: { run_dir: sim.dir }, connection_gate: { status: 'not_applicable' },
  mock_notice: sim.mock ? 'FIXTURE MOCK DATA: nothing was started.' : null });
// Section 12: a second, PAUSED run that the bottom tabs can show while the header's run is live (listed from then on).
const OTHER = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed1__0002';
let otherListed = false, otherOlder = false;     // otherOlder: its save point was written by older optimizer code (7.221)
// Section 13: a run this browser remembers that is gone (deleted, or outside the allowed roots): its status is a 404.
const GONE = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed9__0009';
let goneAsked = 0;
const otherRow = () => ({ run_dir: OTHER, run_id: 'fixture-run-2', task_id: 'fixture_task:0000', task_definition_hash: 'fixture', mode: 'scratch', mock: true, seed: 1,
  created_utc: '2026-09-20T00:00:00+00:00', state: 'paused', experiment: 'fixture_experiment__0001', evaluations: 7, first_feasible_eval_count: null, resumability: 'full_state' });
const otherStatus = () => ({ state: 'paused', run_id: 'fixture-run-2', mode: 'scratch', entry: 'start', provenance: 'mock', mock: true, worker_alive: false, run_dir: OTHER,
  heartbeat_utc: '2026-09-20T00:10:00+00:00', stop_reason: 'user_pause', error: null, active_workers: [], concurrency: 1, learner_updates: 0, first_feasible: null,
  budget: { max_evaluations: 60, max_launches: null, max_retries: 0, charged: 7, reserved: 0, in_flight: 0, completed: 7, failed: 0, released: 0, remaining: 53, launches: 7, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: OTHER }, connection: { overall: 'not_applicable' }, summary: null,
  save_point: 'ckpt-000007', save_point_code: otherOlder ? 'older' : 'current',
  manifest: { mode: 'scratch', mock: true, task_id: 'fixture_task:0000', seeds: { target_seed: 1 }, source_model: null, budgets: { max_evaluations: 60 }, mock_notice: 'FIXTURE MOCK DATA: nothing was started.' } });
// Branch record SIF-78: a REAL run working elsewhere (the command line), listed only while the run brief reads it again: 20 of
// 60 evaluations in 125 s of working time.
const ELSEWHERE = '/fixture/outputs/real/fixture_experiment__0002/runs/fixture_task__scratch__seed2__0003';
let elsewhereListed = false;
const elsewhereRow = () => ({ run_dir: ELSEWHERE, run_id: 'fixture-run-3', task_id: 'fixture_task:0000', task_definition_hash: 'fixture', mode: 'scratch', mock: false, seed: 2,
  created_utc: '2026-09-21T00:00:00+00:00', state: 'running', experiment: 'fixture_experiment__0002', evaluations: 20, max_evaluations: 60, active_seconds: 125,
  first_feasible_eval_count: null, resumability: null });
const elsewhereStatus = () => ({ state: 'running', run_id: 'fixture-run-3', mode: 'scratch', entry: 'start', provenance: 'real', mock: false, worker_alive: true, run_dir: ELSEWHERE,
  active_seconds: 125, budget: { max_evaluations: 60, charged: 20 }, best_design: null, last_checkpoint_utc: null, first_feasible: null,
  manifest: { mode: 'scratch', mock: false, task_id: 'fixture_task:0000', seeds: { target_seed: 2 }, source_model: null, budgets: { max_evaluations: 60 }, mock_notice: null } });
const validReport = validConfiguration({ mock: true });
// Record 7.261: the backend's continuation check (GET /api/runs/continuation) - every run can go on, but OTHER once its save
// point is from older optimizer code, in the backend's words, with the new run that still goes on from it - and what became
// of a launch sent before a reload (GET /api/runs/request), answered from `requestAnswer`.
const OLDER = 'This run was saved by an older version of the optimizer code, and continuing it needs exactly that version. Its model still loads in a new run: fine-tune or frozen.';
let requestAnswer = null; const requestLookups = [];
const checkOf = asked => {
  const used = asked === OTHER ? 7 : sim.charged;
  const answer = { run_dir: asked, eligible: true, code: null, reason: null, state: 'paused', used, total: 60, remaining: 60 - used, minimum_total: used + 1, exhausted: false,
    save_point: 'ckpt-000007', alternative: null };
  return asked === OTHER && otherOlder ? { ...answer, eligible: false, code: 'older_code', reason: OLDER,
    alternative: { action: 'fine_tune', run_dir: OTHER, checkpoint_id: 'ckpt-000007', label: 'Fine-tune from its newest save point (a new run)' } } : answer;
};

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);     // as "Load task" merges it
  const page = await browser.open();
  const { send, evaluate, until, fulfil, consoleErrors } = page;
  const refused = []; const log = []; const dialogs = []; const answers = [];
  let held = null, holdNext = null, refuseNext = null, statusRequests = 0;
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, validReport);
    if (name === '/api/runs/status') { statusRequests++; const asked = url.searchParams.get('run_dir'); if (asked === GONE) goneAsked++;
      return asked === sim.dir ? fulfil(requestId, 200, statusOf()) : asked === OTHER && otherListed ? fulfil(requestId, 200, otherStatus())
        : asked === ELSEWHERE && elsewhereListed ? fulfil(requestId, 200, elsewhereStatus()) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: [...listed(), ...(otherListed ? [otherRow()] : []), ...(elsewhereListed ? [elsewhereRow()] : [])] });
    if (name === '/api/runs/continuation') return fulfil(requestId, 200, checkOf(url.searchParams.get('run_dir')));
    if (name === '/api/runs/request') { requestLookups.push(url.searchParams.get('request_id')); return fulfil(requestId, 200, requestAnswer ?? { state: 'unknown' }); }
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/download') return fulfil(requestId, 200, { output: sim.output, run: sim.run });
    if (name === '/api/output/browse') return fulfil(requestId, 200, { path: null, parent: null, entries: [{ name: '/fixture/elsewhere', path: '/fixture/elsewhere', exists: true }] });
    if (['/api/runs/start', '/api/runs/continue', '/api/runs/command'].includes(name)) {
      log.push({ name, body });
      if (refuseNext && refuseNext.name === name) { const refusal = refuseNext; refuseNext = null; return fulfil(requestId, 409, { detail: refusal.detail }); }
      const reply = () => {
        if (name === '/api/runs/command') return fulfil(requestId, 200, { id: 'fixture', command: body.command });
        // Every Start makes a NEW run folder, as the backend does: the page polls a run that has ended for good only once a
        // minute (App.tsx, 2026-09-22), and a second Start into the same folder would never be seen as running again.
        Object.assign(sim, { alive: true }, name === '/api/runs/start' ? { state: 'created', charged: 0, stop_reason: null, error: null, dir: sim.starts++ ? `${DIR}__${sim.starts}` : DIR } : {});
        return fulfil(requestId, 200, started());
      };
      if (holdNext === name) { holdNext = null; held = reply; return Promise.resolve(); }     // keep the request open: the "...ing" label is observable
      return reply();
    }
    return page.readOrRefuse({ requestId, request }, refused);
  };
  page.on('Page.javascriptDialogOpening', p => {                                  // confirm()/prompt(): answered as planned; an unplanned one is refused and reported
    const accept = answers.length ? answers.shift() : null;
    dialogs.push({ type: p.type, message: p.message, planned: accept !== null });
    return send('Page.handleJavaScriptDialog', { accept: !!accept, promptText: '' });   // a prompt() answered with nothing typed
  });
  const MAIN = `document.querySelector('header button.run-main')`, ABORT = `document.querySelector('header button.run-abort')`, CHIP = `document.querySelector('header button.run-chip')`;
  const BASELINE = `[...document.querySelectorAll('header button')].find(b => b.textContent === 'Calibration')`;
  const CONTINUE = `[...document.querySelectorAll('.status-grid button')].find(b => b.textContent === 'Continue...')`;
  const FORM = `document.querySelector('.continue-form')`, FIELD = `document.querySelector('.continue-form input')`;
  const REFUSAL = `document.querySelector('header .launch-refusal')`;
  const FIRST_TILE = `[...document.querySelectorAll('.status-grid .key-tile')].find(t => t.querySelector('.key-tile-label')?.textContent === 'First feasible design')?.querySelector('.key-tile-value')?.textContent ?? null`;
  const RUN_FOLDER = `[...document.querySelectorAll('.status-grid > table tr')].find(tr => tr.cells[0].textContent === 'Run folder').cells[1]`;
  // Branch record SIF-72: Run configuration's line while the header holds a run, and the tab line's link to the header's run.
  const NEXT_NOTE = `(document.querySelector('aside.right .next-start-note')?.textContent ?? null)`;
  const HEADER_LINK = `document.querySelector('footer .tabs .run-list-header button')`, SHOWN_LINE = `(document.querySelector('footer .tabs .run-list-current')?.textContent ?? '')`;
  const look = () => evaluate(`({ main: ${MAIN}?.textContent, mainOff: ${MAIN}?.disabled, abort: ${ABORT}?.textContent, abortOff: ${ABORT}?.disabled, chip: ${CHIP}?.textContent ?? null,
    baselineOff: ${BASELINE}?.disabled, banner: document.querySelector('.banner')?.textContent ?? null, bannerTitle: document.querySelector('.banner')?.title ?? null,
    remembered: localStorage.getItem(${JSON.stringify(RUN_KEY)}) })`);
  const FOLDER = DIR.split('/').pop();                                            // the run as the line under the header names it (SIF-56)
  // Branch record SIF-91: the output root's lock in Output settings (folded, its controls are on the page all the same).
  const ROOT_LOCK = `({ root: document.querySelector('#output-root')?.disabled ?? null,
    browse: [...document.querySelectorAll('aside.right button')].find(b => b.textContent === 'Browse allowed roots...')?.disabled ?? null,
    hint: [...document.querySelectorAll('aside.right p.hint')].some(p => p.textContent.startsWith('The run directory is locked while a run is active.')) })`;
  const mainReads = (label, tries) => until(`${MAIN}?.textContent === ${JSON.stringify(label)}`, tries);
  const press = expression => evaluate(`${expression}.click()`);
  const commands = () => log.filter(l => l.name === '/api/runs/command').map(l => l.body.command);
  const waitFor = async (test, tries = 50) => { for (let i = 0; i < tries && !test(); i++) await sleep(100); return test(); };
  const seen = () => evaluate(`window.__seen ?? []`);                          // every [label, disabled] the main button has shown on this page
  const lastDialog = () => dialogs[dialogs.length - 1] ?? {};
  const shot = async name => page.shot(path.join(out, name),
    await evaluate(`(() => { const r = document.querySelector('header').getBoundingClientRect(); return { x: 0, y: 0, width: 1680, height: Math.min(1050, r.bottom + 60), scale: 1 }; })()`));
  const open = async seed => {                                                   // a fresh page; `seed` = the run this browser remembers, or null
    await send('Page.navigate', { url: 'about:blank' });
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (location.protocol.startsWith('http')) {
      localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))});
      if (!sessionStorage.getItem('fixture-seeded')) { sessionStorage.setItem('fixture-seeded', '1'); ${seed ? `localStorage.setItem(${JSON.stringify(RUN_KEY)}, ${JSON.stringify(seed)})` : `localStorage.removeItem(${JSON.stringify(RUN_KEY)})`}; }
      window.__seen = [];
      new MutationObserver(() => { const b = document.querySelector('header button.run-main'); if (!b) return; const now = [b.textContent, b.disabled];
        const last = window.__seen[window.__seen.length - 1]; if (!last || last[0] !== now[0] || last[1] !== now[1]) window.__seen.push(now); })
        .observe(document, { subtree: true, childList: true, characterData: true, attributes: true }); }` }).then(r => scripts.push(r.identifier));
    await send('Page.navigate', { url: APP });
    if (!(await until(`!!(${MAIN})`, 150))) throw new Error('the run buttons never appeared; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  };
  const scripts = [];
  const forget = async () => { for (const identifier of scripts.splice(0)) await send('Page.removeScriptToEvaluateOnNewDocument', { identifier }); await evaluate(`sessionStorage.clear()`); };

  await page.intercept(['*/api/*'], answer);

  // ---- 1. nothing held: Start, and Abort next to it ---------------------------------------------------------------
  await open(null);
  await sleep(1200);
  let v = await look();
  check('the main button reads "Start" and is enabled', v.main === 'Start' && v.mainOff === false, JSON.stringify(v));
  check('"Abort" is there, disabled while there is nothing to abort', v.abort === 'Abort' && v.abortOff === true);
  const place = await evaluate(`(() => { const a = ${MAIN}.getBoundingClientRect(), b = ${ABORT}.getBoundingClientRect(), h = document.querySelector('header').getBoundingClientRect();
    return { next: ${MAIN}.nextElementSibling === ${ABORT}, sameRow: Math.abs(a.top - b.top) < 2, gap: b.left - a.right, inHeader: b.right <= h.right + 1, overflowX: document.documentElement.scrollWidth > window.innerWidth }; })()`);
  check('Abort sits directly to the right of the main button, on the same line', place.next && place.sameRow && place.gap >= 0 && place.gap < 16 && place.inHeader && !place.overflowX, JSON.stringify(place));
  check('no run is shown and none is remembered', v.chip === null && v.remembered === null);
  check('... and Run configuration needs no word that it is for the next Start: no run holds the header (SIF-72)', (await evaluate(NEXT_NOTE)) === null);
  check('with no run held the page asks for no run status and sends no command', statusRequests === 0 && log.length === 0, `${statusRequests} status request(s)`);
  await shot('run-1-start.png');

  // ---- 1b. the backend finds the task REAL although the page took it for MOCK (a task chosen a moment ago, its circuit
  //      not read yet): the question is worded from the backend's own report - never "Start 60 synthetic MOCK
  //      evaluations?", whose OK authorized a real run (record 7.125) ------------------------------------------------------
  refuseNext = { name: '/api/runs/start', detail: { code: 'real_authorization_required', message: 'FIXTURE: a real simulation needs your authorization.',
    report: { blocker: 'FIXTURE', task_key: 'real:fixture_ota', requested_max_evaluations: 60 } } };
  answers.push(false); log.length = 0; const askedBefore = dialogs.length;
  await press(MAIN);
  for (let i = 0; i < 60 && dialogs.length === askedBefore; i++) await sleep(100);
  check('a start the backend finds REAL is asked in REAL words, from its report (task, total budget), not as MOCK',
    /^This runs REAL simulations of real:fixture_ota/.test(lastDialog().message ?? '') && /total budget of 60 candidate/.test(lastDialog().message ?? '')
    && !/MOCK evaluations/.test(lastDialog().message ?? ''), lastDialog().message);
  check('... and "no" starts nothing: one refused request, the button reads "Start" again', await mainReads('Start', 30) && log.length === 1, JSON.stringify(log.map(l => l.name)));
  log.length = 0;
  await evaluate(`window.__seen = [['Start', false]]`);            // the label history below starts from here, as before this step

  // ---- 2. Start -> "Starting..." -> "Pause" ----------------------------------------------------------------------------
  // Branch record SIF-91 review: a folder list opened while idle kept "Use this folder" on after the Start, which set the root
  // under the run. Opened here first, its button is on.
  const USE_FOLDER = `[...document.querySelectorAll('aside.right ul.tree button')].find(b => b.textContent === 'Use this folder')`;
  await press(`[...document.querySelectorAll('aside.right button')].find(b => b.textContent === 'Browse allowed roots...')`);
  check('(set-up) the folder list is open while idle, "Use this folder" on', await until(`!!(${USE_FOLDER}) && !${USE_FOLDER}.disabled`, 30));
  const rootBefore = await evaluate(`document.querySelector('#output-root').value`);
  holdNext = '/api/runs/start';
  await press(MAIN);
  check('while the backend is starting the run the button reads "Starting..." and is disabled', await mainReads('Starting...') && (await look()).mainOff === true);
  const lockStarting = await evaluate(ROOT_LOCK);
  check('... and the output root is locked, with its hint, though no run has answered yet (SIF-91)', JSON.stringify(lockStarting) === '{"root":true,"browse":true,"hint":true}', JSON.stringify(lockStarting));
  await evaluate(`${USE_FOLDER}?.click()`); await sleep(200);
  const useLock = await evaluate(`({ use: ${USE_FOLDER}?.disabled ?? null, root: document.querySelector('#output-root').value })`);
  check('... "Use this folder" in the list opened before is off too: a press leaves the root as it was (SIF-91 review)',
    JSON.stringify(useLock) === JSON.stringify({ use: true, root: rootBefore }), `${JSON.stringify(useLock)} / ${rootBefore}`);
  await press(`[...document.querySelectorAll('aside.right p.hint button')].find(b => b.textContent === 'Close')`);
  v = await look();
  check('Abort and the baseline simulation are disabled meanwhile', v.abortOff === true && v.baselineOff === true, JSON.stringify(v));
  check('ONE start request was sent, for a full run with the page\'s configuration', log.length === 1 && log[0].name === '/api/runs/start' && log[0].body.calibration_only === false
    && log[0].body.config?.schema_version === CONFIG.schema_version && !('authorize_real_simulation' in log[0].body), JSON.stringify(log.map(l => l.name)));
  check('... with a request id, kept in this tab until it is answered (7.261)', typeof log[0].body.request_id === 'string' && log[0].body.request_id.length >= 8
    && (await evaluate(`JSON.parse(sessionStorage.getItem('gator-workbench-launch-v1') ?? 'null')?.id`)) === log[0].body.request_id, JSON.stringify(log[0].body.request_id));
  sim.steps = [{}, {}, { state: 'starting' }, { state: 'running' }];
  await held(); held = null;
  check('after Start the button reads "Pause"', await mainReads('Pause') && (await look()).mainOff === false);
  check('... and the answered request id is no longer kept', await until(`sessionStorage.getItem('gator-workbench-launch-v1') === null`));
  v = await look();
  check('Abort is enabled, the baseline simulation is not available while the run is active', v.abort === 'Abort' && v.abortOff === false && v.baselineOff === true);
  check('the run is remembered by this browser', v.remembered === DIR, String(v.remembered));
  // Branch record SIF-56: the run by its folder's name ("Run directory: <the full path>" before); the path is the line's
  // tooltip, over the line's own "click to close".
  check('the MOCK notice and the run are reported: "Started <its folder>.", the full path in the line\'s tooltip, with how it closes',
    (v.banner ?? '') === `FIXTURE MOCK DATA: nothing was started. Started ${FOLDER}.` && v.bannerTitle === `${DIR}\nClick to close (selecting text keeps it).`,
    JSON.stringify([v.banner, v.bannerTitle]));
  // Branch record SIF-72: the count says what it counts and leaves "running" to the lit strip beside it ("Running" stood beside
  // "running 292 / 800"), and the run's task comes first when the title names another (the FIXTURE run is fixture_task's).
  check('the header shows the run and its progress: its task, which is not the title\'s, then "N of 60 evaluations" - no "running" beside the strip\'s Running (SIF-72)',
    await until(`/^fixture_task · \\d+ of 60 evaluations \\[MOCK\\]$/.test(${CHIP}?.textContent ?? '') && ${CHIP}.querySelector('b')?.textContent === 'fixture_task'`), (await look()).chip ?? '');
  const chipLook = await evaluate(`(() => { const s = getComputedStyle(${CHIP}); return { border: s.borderTopStyle + ' ' + s.borderTopWidth, font: s.fontFamily, title: ${CHIP}.title }; })()`);
  check('... outlined as the button it is (it opens the run brief), in the text font, not mono; its tooltip names the task too (SIF-72)',
    chipLook.border === 'solid 1px' && chipLook.font.includes('Segoe UI') && chipLook.title.startsWith(`The current run, a run of fixture_task: ${DIR}\n`), JSON.stringify(chipLook));
  check('Run configuration says that it is for the next Start while the header holds a run (SIF-72: its budget and Mode stood beside the run\'s own)',
    (await evaluate(NEXT_NOTE)) === 'For the next Start: the run in the header goes on with the settings it was started with.', await evaluate(NEXT_NOTE));
  check('the Run status tab shows this run', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DIR)})`));
  // Branch record SIF-54: the facts in words - the connection as the Connection window words it (it printed "not_applicable"),
  // the jobs at once by Run configuration's name ("none (concurrency 1)"), "Saved to disk" ("Persistence"), "Run folder"
  // that says it copies, and "none yet" while the run can still find a feasible design.
  const facts = await evaluate(`Object.fromEntries([...document.querySelectorAll('.status-grid > table tr')].map(tr => [tr.cells[0].textContent, { text: tr.cells[1]?.textContent, title: tr.cells[1]?.title }]))`);
  check('... its facts in words: Connection "n/a", "none; up to 1 concurrent Spectre job", Saved to disk "-", Run folder "Click to copy"',
    facts.Connection?.text === 'n/a' && facts['Active workers']?.text === 'none; up to 1 concurrent Spectre job' && facts['Saved to disk']?.text === '-'
    && facts['Run folder']?.text === DIR && facts['Run folder']?.title === 'Click to copy' && !facts.Persistence && !facts['Run directory'], JSON.stringify(facts).slice(0, 600));
  check('... "First feasible design: none yet" while the run works', (await evaluate(FIRST_TILE)) === 'none yet', await evaluate(FIRST_TILE));
  // A click copies the path and says so for 1.5 s (the browser's clipboard stood in for: a headless window may not be focused).
  await evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: text => { window.__clip = text; return Promise.resolve(); } })`);
  await evaluate(`${RUN_FOLDER}.click()`, true);
  check('... a click on the run folder copies it and says "copied", then reads the path alone again', await until(`${RUN_FOLDER}.textContent === ${JSON.stringify(`${DIR} copied`)}`, 20)
    && (await evaluate('window.__clip')) === DIR && await until(`${RUN_FOLDER}.textContent === ${JSON.stringify(DIR)}`, 40), await evaluate(`${RUN_FOLDER}.textContent`));
  // Branch record SIF-94: a copy the browser refuses says so there, for 1.5 s as well (it was said nowhere).
  await evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: () => Promise.reject(new DOMException('FIXTURE: Document is not focused.', 'NotAllowedError')) })`);
  await evaluate(`${RUN_FOLDER}.click()`, true);
  check('... a copy the browser refuses says "could not copy" there, then the path alone again (SIF-94)', await until(`${RUN_FOLDER}.textContent === ${JSON.stringify(`${DIR} could not copy`)}`, 20)
    && await until(`${RUN_FOLDER}.textContent === ${JSON.stringify(DIR)}`, 40), await evaluate(`${RUN_FOLDER}.textContent`));
  await evaluate(`delete navigator.clipboard.writeText`);
  await shot('run-2-running.png');
  // Review of branch record SIF-56: a double click on the folder's name in the line takes that word and keeps the line (its
  // first click, before anything was selected, closed it); a single click still closes it, a moment later.
  const word = await evaluate(`(() => { const t = [...(document.querySelector('.banner')?.childNodes ?? [])].find(n => n.nodeType === 3 && n.data.includes(${JSON.stringify(FOLDER)}));
    if (!t) return null; const r = document.createRange(), i = t.data.indexOf(${JSON.stringify(FOLDER)}); r.setStart(t, i); r.setEnd(t, i + ${FOLDER.length});
    const q = r.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; })()`);
  if (word) { await page.clickAt(word, { count: 2 }); await sleep(900); }
  const picked = await evaluate(`window.getSelection().toString()`);
  check('a double click on the run\'s folder in the line takes that word, and the line stays (review of SIF-56)',
    !!word && picked === FOLDER && (await look()).banner === `FIXTURE MOCK DATA: nothing was started. Started ${FOLDER}.`, JSON.stringify([word, picked, (await look()).banner]));
  if (word) await page.clickAt(word);
  check('... and a single click closes it', await until(`!document.querySelector('.banner')`, 20));

  // ---- 3. Pause -> "Pausing..." -> "Resume" -----------------------------------------------------------------------------
  sim.steps = [{}, {}, { state: 'pausing', stop_reason: 'user_pause' }, {}, {}, { state: 'paused' }, {}, { alive: false }];   // the run answers late, then finishes its files
  const before = dialogs.length;
  await press(MAIN);
  check('Pause reads "Pausing..." at once, before the run has answered', await mainReads('Pausing...', 15) && (await look()).mainOff === true);
  check('ONE pause command was sent, without a question', await waitFor(() => commands().length > 0) && commands().join() === 'pause' && dialogs.length === before, commands().join());
  v = await look();
  check('while the simulation in flight finishes, Abort reads "Force abort"', v.abort === 'Force abort' && v.abortOff === false && /pausing/.test(v.chip ?? ''), JSON.stringify(v));
  await shot('run-3-pausing.png');
  // Branch record SIF-83: while a pause waits, Force abort says that it gives the pause up for an end with no way back.
  const forceTitle = await evaluate(`${ABORT}.title`);
  check('... its tooltip says it replaces the Pause and the run cannot be resumed (SIF-83)', /This replaces your Pause: the run ends as cancelled and cannot be resumed/.test(forceTitle), forceTitle);
  answers.push(false);
  await press(ABORT); await sleep(400);
  check('... pressed, it asks first and says what it costs: the pause is replaced, the run cannot be resumed or continued, wait to keep it (SIF-83)',
    /^Force abort\?\n\nThis replaces your Pause: the run ends as cancelled, and a cancelled run cannot be resumed or continued/.test(lastDialog().message ?? '')
    && /To keep it resumable, wait for the pause\./.test(lastDialog().message ?? '') && /stuck/.test(lastDialog().message ?? ''), lastDialog().message);
  check('... and "no" sends nothing more than the pause', commands().join() === 'pause' && (await look()).abort === 'Force abort', commands().join());
  check('after the pause the button reads "Resume"', await mainReads('Resume', 150) && (await look()).mainOff === false);
  v = await look();
  check('on the paused run the second button reads "Let go" (7.261), the header says where the run stands (no "paused" beside the strip\'s Paused, SIF-72)',
    v.abort === 'Let go' && v.abortOff === false && /^fixture_task · at \d+ of 60 evaluations \[MOCK\]$/.test(v.chip ?? ''), JSON.stringify(v));
  check('the baseline simulation stays unavailable while the header holds a paused run', v.baselineOff === true);
  check('the line under the header no longer says "Pausing": it says that the run is paused and saved', /^Paused at \d+ of 60 evaluations: everything is saved/.test(v.banner ?? ''), v.banner ?? '');
  let labels = (await seen()).map(s => s[0]);
  check('the button went Start -> Starting... -> Pause -> Pausing... -> Resume with nothing in between', labels.join(' > ') === 'Start > Starting... > Pause > Pausing... > Resume', labels.join(' > '));
  await shot('run-4-paused.png');

  // ---- 4. a paused run is left alone; a live run keeps its Pause whatever the bottom tabs show ------------------------------
  // The bottom tabs are put on no run the way a user does it: the run button of the tab strip opens the run window
  // (RunList.tsx, a page of its own with its own DevTools session), and "Clear" (it shows no run) is pressed there.
  const showNoRun = async () => {
    await evaluate(`document.querySelector('footer .tabs button.run-list-button').click()`, true);   // a click that may open a window
    const target = await browser.window(RUNS_WINDOW).catch(() => null);
    if (!target) throw new Error('the run window did not open');
    const far = await browser.attach(target);
    const ok = await far.evaluate(`new Promise(done => { let tries = 0; const tick = () => {
      const b = [...document.querySelectorAll('.run-window .row button')].find(b => b.textContent.trim() === 'Clear' && !b.disabled); if (b) { b.click(); done(true); } else if (++tries > 50) done(false); else setTimeout(tick, 100); }; tick(); })`);
    far.close();
    await send('Target.closeTarget', { targetId: target.id });
    if (!ok) throw new Error('"Clear" was not available in the run window');
  };
  await showNoRun();                                                               // the bottom tabs show no run
  await sleep(1800); const atRest = statusRequests; await sleep(4000);
  check('a paused run is not polled by the header (no timer at rest)', statusRequests === atRest, `${statusRequests - atRest} request(s) in 4 s`);
  check('the header still holds it: "Resume"', (await look()).main === 'Resume');
  // Branch record SIF-72: the tab line offers the header's run while the tabs show another (or none), and a press shows it.
  const offer = await evaluate(`({ shown: ${SHOWN_LINE}, link: ${HEADER_LINK}?.textContent ?? null, title: ${HEADER_LINK}?.title ?? '' })`);
  check('with the tabs on no run, the tab line offers the header\'s paused run: "Show the header\'s run", its folder in the tooltip (SIF-72)',
    offer.shown === 'No run selected' && offer.link === 'Show the header\'s run'                     // paused: its buttons read Resume and Let go
    && offer.title === `The header holds another run, the one its buttons act on: ${DIR}\nPress to show it in these tabs.`, JSON.stringify(offer));
  await press(HEADER_LINK);
  check('... a press shows it under Run status, and the link goes: the tabs show the header\'s run', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DIR)})
    && !(${HEADER_LINK}) && !${SHOWN_LINE}.startsWith('Shown:')`, 50), await evaluate(SHOWN_LINE));

  // ---- 5. Resume -> "Resuming..." -> "Pause": the same run, no budget question --------------------------------------------
  holdNext = '/api/runs/continue';
  const dialogsBefore = dialogs.length;
  await press(MAIN);
  check('Resume reads "Resuming..." while the backend restores the run', await mainReads('Resuming...') && (await look()).mainOff === true);
  const resume = log[log.length - 1];
  check('ONE continue request for the SAME run directory, budget unchanged, no question asked', resume.name === '/api/runs/continue' && resume.body.run_dir === DIR && resume.body.max_evaluations === null
    && !('authorize_real_simulation' in resume.body) && dialogs.length === dialogsBefore, JSON.stringify(resume.body));
  sim.steps = [{}, {}, {}, { state: 'starting', stop_reason: null }, { state: 'running' }];   // the old "paused" status stays on disk until the new worker writes its own
  await held(); held = null;
  check('after Resume the button reads "Pause" again', await mainReads('Pause') && (await look()).mainOff === false);
  v = await look();
  check('... and the line under the header says "Continuing <its folder> in its own folder.", the path in its tooltip (SIF-56)',
    v.banner === `Continuing ${FOLDER} in its own folder.` && (v.bannerTitle ?? '').startsWith(`${DIR}\n`), JSON.stringify([v.banner, v.bannerTitle]));
  labels = (await seen()).map(s => s[0]);
  check('it never fell back to "Resume" or "Pausing..." while the new worker was starting', labels.slice(5).join(' > ') === 'Resuming... > Pause', labels.slice(5).join(' > '));
  await showNoRun();                                                               // Resume brought the run back under Run status; look away again
  await sleep(300); const liveBefore = statusRequests; await sleep(3500);
  check('with the bottom tabs on no run, the live run is polled by the header and keeps its Pause', statusRequests > liveBefore && (await look()).main === 'Pause', `${statusRequests - liveBefore} request(s) in 3.5 s`);
  check('the header follows its progress', /^fixture_task · \d+ of 60 evaluations \[MOCK\]$/.test((await look()).chip ?? ''), (await look()).chip ?? '');
  // The run brief (record 7.264, plan "The run brief"): the chip opens a small window; it only shows - Show results there does what
  // the chip's press did until then, and Open in Runs opens the Runs window at the run.
  const tabsBefore = await evaluate(`document.querySelector('footer .tabs .run-list-current')?.textContent ?? ''`);
  sim.active = 301;                                                                // its status gives a working time from now on (SIF-78)
  await evaluate(`${CHIP}.click()`, true);                                       // a click that opens a window
  const briefTarget = await browser.window(RUNNING_WINDOW).catch(() => null);
  check('pressing the run in the header opens the run brief, a window of its own', !!briefTarget);
  if (!briefTarget) throw new Error('the run brief did not open');
  const brief = await browser.attach(briefTarget);
  await brief.until(`!!document.querySelector('.brief-card')`, 50);
  const card = await brief.evaluate(`(() => { const c = document.querySelector('.brief-card'); return c && { dir: c.dataset.runDir, text: c.innerText.replace(/\\s+/g, ' '),
    buttons: [...c.querySelectorAll('button')].map(b => b.textContent), others: document.querySelectorAll('.brief-card').length,
    none: document.querySelector('.brief-none')?.textContent ?? '' }; })()`);
  check('its first card is the header\'s run: in this page\'s header, its evaluations, MOCK, Show results and Open in Runs - no run controls',
    card?.dir === DIR && /In this page's header/.test(card.text) && /\d+ \/ 60 evaluations/.test(card.text) && /MOCK/.test(card.text)
    && card.buttons.join() === 'Show results,Open in Runs' && card.others === 1 && /Nothing else is live/.test(card.none), JSON.stringify(card));
  check('... titled as the Runs window names the run: its task\'s name and the Mode in words, not "fixture_task:0000 · scratch" (SIF-44)',
    /^fixture_task · New model · no model saved\b/.test(card?.text ?? ''), card?.text);
  // Branch record SIF-78: the working time as the Runs window's Duration names it, "so far" while live - it read "worked 5 min 01 s".
  const TIME = `document.querySelector('.brief-card .brief-time')?.textContent ?? ''`;
  check('... its working time reads as the Runs window\'s Duration: "Duration 5 min 01 s so far", then the time left (SIF-78)',
    await brief.until(`/^Duration 5 min 01 s so far · about \\d.* left$/.test(${TIME})`, 50), await brief.evaluate(TIME));
  await brief.shot(path.join(out, 'run-4b-brief.png'), `document.querySelector('.run-brief')`);
  check('opening it changed nothing: the bottom tabs show what they showed', (await evaluate(`document.querySelector('footer .tabs .run-list-current')?.textContent ?? ''`)) === tabsBefore);
  // Branch record SIF-78: a REAL run's card says so after the line's " · " - a bare grey "real" after "model graphgps_ldo1 (31)"
  // read as part of the model's name.
  elsewhereListed = true;
  await brief.evaluate(`[...document.querySelectorAll('.run-brief button')].find(b => b.textContent === 'Refresh').click()`);
  const REAL_CARD = `document.querySelector(${JSON.stringify(`.brief-card[data-run-dir="${ELSEWHERE}"]`)})`;
  await brief.until(`!!${REAL_CARD}`, 50);
  const real = await brief.evaluate(`(() => { const c = ${REAL_CARD}; return c && { title: c.querySelector('.brief-title').textContent.replace(/\\s+/g, ' '),
    time: c.querySelector('.brief-time')?.textContent ?? '', badge: !!c.querySelector('.mock-tag') }; })()`);
  check('Refresh adds a real run working elsewhere, its title ending " · real data" (no MOCK badge), its time "Duration 2 min 05 s so far" (SIF-78)',
    real?.title === 'fixture_task · New model · no model saved · real data' && !real.badge && real.time === 'Duration 2 min 05 s so far · about 4 min 10 s left', JSON.stringify(real));
  await brief.shot(path.join(out, 'run-4c-brief-real.png'), `document.querySelector('.run-brief')`);
  elsewhereListed = false;
  await brief.evaluate(`[...document.querySelector('.brief-card').querySelectorAll('button')].find(b => b.textContent === 'Show results').click()`);
  check('Show results in the brief shows the run under Run status again', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DIR)})`));
  // Branch record SIF-98: the working time and the time left stood in the brief alone, a window to open for the one number asked
  // for most. Run status says them under the bar, apart from the budget's words; the chip's tooltip ends with them (its text
  // stays the count), and added nothing while the status gave no working time.
  const HERO_TIME = `(document.querySelector('.status-grid .status-hero-count > .status-hero-time')?.textContent ?? '')`;
  check('... and says under the bar what the brief says: "Duration 5 min 01 s so far · about N left" (SIF-98)',
    await until(`/^Duration 5 min 01 s so far · about \\d.* left$/.test(${HERO_TIME})`, 50), await evaluate(HERO_TIME));
  const chipTime = await evaluate(`({ title: ${CHIP}.title, text: ${CHIP}.textContent })`);
  check('... the header chip\'s tooltip ends with the same line after what it said; its text stays the count; before the working time was known it ended at "(record 7.264)." (SIF-98)',
    chipTime.title.startsWith(`The current run, a run of fixture_task: ${DIR}\nPress for the run brief:`) && /\(record 7\.264\)\.\nDuration 5 min 01 s so far · about \d.* left$/.test(chipTime.title)
    && /^fixture_task · \d+ of 60 evaluations \[MOCK\]$/.test(chipTime.text) && chipLook.title.endsWith('(record 7.264).'), JSON.stringify([chipTime, chipLook.title]));
  await brief.evaluate(`[...document.querySelector('.brief-card').querySelectorAll('button')].find(b => b.textContent === 'Open in Runs').click()`, true);
  const runsTarget = await browser.window(RUNS_WINDOW).catch(() => null);
  const runsWindow = runsTarget && await browser.attach(runsTarget);
  check('Open in Runs opens the Runs window at the run: its Details open', !!runsWindow && await runsWindow.until(`(() => { const tr = [...document.querySelectorAll('table.run-table tbody > tr')]
    .find(tr => tr.title === ${JSON.stringify(DIR)}); return !!tr && tr.querySelector('button.notes-link')?.getAttribute('aria-expanded') === 'true'; })()`, 60));
  runsWindow?.close(); if (runsTarget) await send('Target.closeTarget', { targetId: runsTarget.id });
  brief.close(); await send('Target.closeTarget', { targetId: briefTarget.id });
  sim.active = null;

  // ---- 6. a reload: the live run is still the header's run, and "Start" is never offered meanwhile ---------------------------
  await send('Page.reload'); await until(`!!(${MAIN})`, 150);
  check('after a reload the button reads "Pause" for the remembered live run', await mainReads('Pause'));
  const offered = (await seen()).filter(s => s[0] === 'Start' && s[1] === false);
  check('an enabled "Start" was never shown while the remembered run was looked up', offered.length === 0, JSON.stringify(await seen()));

  // ---- 7. Abort: asked first; graceful stop; "Force abort" as the second step --------------------------------------------------
  log.length = 0; answers.push(false);
  await until(`/^fixture_task · /.test(${CHIP}?.textContent ?? '')`);           // the run list read again: the page knows the run's task
  await press(ABORT); await sleep(400);
  // Branch record SIF-72: the question names the run's task when the header's title names another - the run Abort ends.
  check('Abort asks first, in plain words, naming the run\'s task, which is not the title\'s (SIF-72)', lastDialog().type === 'confirm' && /^Abort this run of fixture_task\?\n/.test(lastDialog().message)
    && /allowed to finish/.test(lastDialog().message) && /use Pause instead/.test(lastDialog().message), lastDialog().message);
  check('answering no sends nothing', log.length === 0 && (await look()).main === 'Pause');
  check('...and a run that is no Baseline simulation is not told about a baseline', !/Baseline simulation/.test(lastDialog().message), lastDialog().message);
  // A Baseline simulation calibrates (record 7.202): Abort is how its baseline is kept alone, and the question says so (7.206).
  sim.calibration = { request: { designs: 64, lanes: 1, evaluations: 65 }, result: null };
  await sleep(3200);                                                                // two status polls (1.5 s each): the page holds it
  answers.push(false); await press(ABORT); await sleep(400);
  const asked = lastDialog().message.replace(/\n/g, ' ');
  check('Abort of Calibration says what its partial proposal needs', lastDialog().type === 'confirm' && /^Abort this run of fixture_task\?/.test(asked)
    && !/baseline/.test(asked) && /Calibration proposes only from the random designs simulated so far/.test(asked)
    && /at least 16 must give a reward/.test(asked), asked);
  check('...and answering no sends nothing there either', log.length === 0 && (await look()).main === 'Pause');
  sim.calibration = null; await sleep(3200);
  answers.push(true); sim.steps = [{}, { state: 'stopping', stop_reason: 'user_stop' }];
  await press(ABORT);
  check('Abort reads "Aborting..." and sends ONE graceful stop (the simulation in flight may finish)', await mainReads('Aborting...') && await waitFor(() => commands().length > 0) && commands().join() === 'stop', commands().join());
  check('while it waits, the second button reads "Force abort"', await until(`${ABORT}.textContent === 'Force abort' && !${ABORT}.disabled`) && /aborting/.test((await look()).chip ?? ''));
  await shot('run-5-aborting.png');
  answers.push(true);
  await press(ABORT); await sleep(400);
  check('Force abort asks again and says what it costs', /^Force abort\?/.test(lastDialog().message) && /still counts against the\s+budget/.test(lastDialog().message.replace(/\n/g, ' ')) && /stuck/.test(lastDialog().message), lastDialog().message);
  check('... after an Abort it says the run ends as cancelled, not stopped, and Continue... cannot pick it up; no word of a Pause (SIF-83)',
    /The run ends as cancelled instead of stopped, so Continue\.\.\. can no longer pick it up/.test(lastDialog().message) && !/Pause/.test(lastDialog().message), lastDialog().message);
  check('it sends ONE forced cancel and cannot be pressed twice', await waitFor(() => commands().length > 1) && commands().join() === 'stop,cancel' && (await look()).abortOff === true, commands().join());
  sim.steps = [{}, { state: 'cancelled', stop_reason: 'user_cancel' }, { alive: false }];
  check('when the run has ended the button reads "Start" again', await mainReads('Start', 150) && (await look()).mainOff === false);
  v = await look();
  check('the line under the header says that the run has ended, and how', /^The run has ended \(cancelled\) at \d+ of 60 evaluations: /.test(v.banner ?? ''), v.banner ?? '');
  check('Abort is disabled, the baseline simulation is available, the header says how the run ended', v.abortOff === true && v.baselineOff === false
    && /^fixture_task · cancelled at \d+ of 60 evaluations \[MOCK\]$/.test(v.chip ?? ''), JSON.stringify(v));
  check('... and Run configuration no longer says it is for the next Start: the header\'s run has ended (SIF-72)', (await evaluate(NEXT_NOTE)) === null, await evaluate(NEXT_NOTE));
  check('... and Run status\'s "First feasible design" reads "none", not "none yet" (branch record SIF-54)', await until(`${FIRST_TILE} === 'none'`, 40), await evaluate(FIRST_TILE));
  await shot('run-6-ended.png');

  // ---- 7b. a run that pauses, completes or fails with no press says so (branch record SIF-89) ----------------------------------
  // They changed only the chip and the lit state: a failure's reason was the last row of Run status, Continue... came after all
  // of its facts, and a pause after connection failures, caught while it saved, read "Resume continues from exactly there" as
  // if the user had paused. The engine's own pause: stop_reason infrastructure_failures with its error, the worker saving.
  const INFRA = 'FIXTURE: 3 consecutive infrastructure failures; paused safely. Continuing requires the connection gate to pass again.';
  const FAILED = 'FIXTURE: 3 consecutive failed evaluations; stopped safely';
  const LINE = `(() => { const b = document.querySelector('.banner'); return b && { text: b.textContent, red: b.classList.contains('error'), title: b.title }; })()`;
  const lineSays = start => until(`(document.querySelector('.banner')?.textContent ?? '').startsWith(${JSON.stringify(start)})`, 40);
  // Run status from its top: the run at a glance, the reason, the row with Continue... and Export status (JSON) last, the facts.
  const HEAD = `(() => { const g = document.querySelector('.status-grid'), kids = g ? [...g.children] : [], at = s => kids.findIndex(k => k.matches(s));
    const row = kids.findIndex(k => k.matches('.row') && [...k.querySelectorAll('button')].some(b => b.textContent === 'Continue...'));
    const body = document.querySelector('.bottom-body'); body.scrollTop = 0;
    return { hero: at('.status-hero'), error: at('p.status-error'), row, table: at('table'), text: g?.querySelector(':scope > p.status-error')?.textContent ?? null,
      last: kids[row]?.lastElementChild?.textContent ?? null, inView: row >= 0 && kids[row].getBoundingClientRect().bottom <= body.getBoundingClientRect().bottom,
      errorRow: [...(g?.querySelectorAll(':scope > table tr') ?? [])].find(tr => tr.cells[0].textContent === 'Error')?.cells[1].textContent ?? null }; })()`;
  await press(MAIN);
  check('(a new Start after the ended run: "Pause")', await mainReads('Pause', 150));
  await evaluate(`window.__seen = []`);                               // the labels from here: the pause passes through "Pausing..."
  sim.steps = [{ state: 'running' }, {}, { state: 'paused', stop_reason: 'infrastructure_failures', error: INFRA }, {}, { alive: false }];
  check('(the run pauses by itself, its worker saving first: "Resume")', await mainReads('Resume', 150) && (await seen()).some(s => s[0] === 'Pausing...'), JSON.stringify(await seen()));
  let line = await lineSays('Paused by itself') && await evaluate(LINE);
  check('a pause after connection failures says so in red, and what to do first - not "Resume continues from exactly there"; the run\'s path in its tooltip (SIF-89)',
    line?.text === 'Paused by itself after connection failures; everything is saved. Test the connection (Connection button), then Resume.' && line.red
    && line.title.startsWith(`${sim.dir}\n`), JSON.stringify(line));
  let head = await until(`!!document.querySelector('.status-grid > p.status-error')`, 40) && await evaluate(HEAD);
  check('... Run status says the reason in red right under the run at a glance, then Continue... with Export status (JSON) last, above the facts, in view (SIF-89)',
    head && head.hero >= 0 && head.error === head.hero + 1 && head.row === head.error + 1 && head.table > head.row && head.text === INFRA
    && head.last === 'Export status (JSON)' && head.inView && head.errorRow === INFRA, JSON.stringify(head));
  await page.shot(path.join(out, 'run-6b-paused-by-itself.png'));                 // the whole page: the line and Run status
  sim.steps = [{}, { state: 'running', stop_reason: null, error: null }];
  await press(MAIN);
  check('(Resume: "Pause" again, and the reason has gone from Run status)', await mainReads('Pause', 150) && await until(`!document.querySelector('.status-grid > p.status-error')`, 40));
  // Review of SIF-89: a worker that dies before the engine's own pause is written (it drains the jobs in flight and saves first)
  // leaves an `interrupted` run that keeps the stop reason; only what was acknowledged is kept there. Neither "everything is
  // saved" line may speak then, from `running` or from `pausing`: the chip says the worker is gone.
  for (const via of ['running', 'pausing']) {
    await evaluate(`window.__seen = []`);
    sim.steps = [...(via === 'pausing' ? [{ state: 'pausing' }, {}] : [{}]), { state: 'interrupted', stop_reason: 'infrastructure_failures', error: INFRA, alive: false }];
    check(`(from ${via}, the worker is gone before the pause is written: "Resume")`,
      await mainReads('Resume', 150) && (via === 'running' || (await seen()).some(s => s[0] === 'Pausing...')), JSON.stringify(await seen()));
    await sleep(1500);
    v = await look();
    check(`... from ${via}, an interrupted run gets no "Paused ... everything is saved" line, and the chip says the worker is gone (review of SIF-89)`,
      !/^Paused/.test(v.banner ?? '') && /\(the worker is gone\)( \[MOCK\])?$/.test(v.chip ?? ''), JSON.stringify([v.banner, v.chip]));
    sim.steps = [{}, {}, {}, { state: 'starting', stop_reason: null, error: null }, { state: 'running' }];
    await press(MAIN);
    check(`(Resume of the interrupted run: "Pause" again)`, await mainReads('Pause', 150));
  }
  sim.steps = [{}, { state: 'completed', stop_reason: 'budget_exhausted', charged: 60 }, {}, { alive: false }];
  check('(the run completes: "Start")', await mainReads('Start', 150));
  line = await lineSays('Completed') && await evaluate(LINE);
  check('a run that completes says so, how, and where its results are: "Completed at 60 of 60 evaluations (budget used up). Its results are under Run status." (SIF-89)',
    line?.text === 'Completed at 60 of 60 evaluations (budget used up). Its results are under Run status.' && !line.red && line.title.startsWith(`${sim.dir}\n`), JSON.stringify(line));
  await press(MAIN);
  check('(a new Start after the completed run: "Pause")', await mainReads('Pause', 150));
  sim.steps = [{ state: 'running' }, {}, { state: 'failed', stop_reason: 'consecutive_failures', error: FAILED }, {}, { alive: false }];
  check('(the run fails: "Start")', await mainReads('Start', 150));
  line = await lineSays('The run failed') && await evaluate(LINE);
  check('a run that fails says so in red, with its reason: "The run failed at N of 60 evaluations: <error>" (SIF-89)',
    new RegExp(`^The run failed at \\d+ of 60 evaluations: ${FAILED.replace(/[.;]/g, '\\$&')}$`).test(line?.text ?? '') && line.red && line.title.startsWith(`${sim.dir}\n`), JSON.stringify(line));
  head = await until(`document.querySelector('.status-grid > p.status-error')?.textContent === ${JSON.stringify(FAILED)}`, 40) && await evaluate(HEAD);
  check('... and Run status leads with that reason, then Continue..., above the facts (SIF-89)',
    head && head.error === head.hero + 1 && head.row === head.error + 1 && head.table > head.row && head.inView, JSON.stringify(head));
  await page.shot(path.join(out, 'run-6c-failed.png'));

  // ---- 8. a run that cannot come back is announced BEFORE the pause; Abort on a paused run lets go of it -----------------------
  // Review of SIF-72: while the new Start is on its way the header still holds the ended run - the chip reads "starting" for
  // the new one, so it names no task of the ended run, and Run configuration's settings are the ones being started.
  holdNext = '/api/runs/start';
  await press(MAIN);
  check('(a new Start after an ended run is on its way: "Starting...")', await mainReads('Starting...'));
  v = await look();
  const startingNote = await evaluate(NEXT_NOTE);
  check('... meanwhile the chip names no task of the ended run, and Run configuration does not say it is for the next Start (review of SIF-72)',
    /^starting( \[MOCK\])?$/.test(v.chip ?? '') && startingNote === null, JSON.stringify([v.chip, startingNote]));
  await held(); held = null;
  check('a new Start after an ended run works', await mainReads('Pause'));
  sim.steps = [{ state: 'running' }];
  sim.output = { save_checkpoints: true, save_replay_snapshots: false }; log.length = 0; answers.push(false);
  await press(MAIN); await sleep(600);
  check('Pause warns when the run was started without replay snapshots', /cannot be resumed after a pause: replay snapshots are switched off for it\.\n/.test(lastDialog().message ?? ''), lastDialog().message);
  check('answering no sends nothing and the button reads "Pause" again', log.length === 0 && await mainReads('Pause', 20));
  // Branch record SIF-83: a run searched by Bayesian optimization is never continued by the backend: Pause says so first.
  sim.output = {}; sim.run = { optimizer: 'bayes' }; answers.push(false);
  await press(MAIN); await sleep(600);
  check('Pause warns when the run is searched by Bayesian optimization (SIF-83)',
    /^This run cannot be resumed after a pause: it is searched by Bayesian optimization, whose search state lives only in its running process\.\n\nPause anyway\?/.test(lastDialog().message ?? ''), lastDialog().message);
  check('... answering no sends nothing there either, the button reads "Pause" again', log.length === 0 && await mainReads('Pause', 20));
  // Review of SIF-83: answered yes, the pause waits, and Force abort no longer advises waiting "to keep it resumable" -
  // nothing is resumable here - in its question or its tooltip.
  answers.push(true); sim.steps = [{ state: 'pausing' }, {}, {}, {}, {}, { state: 'paused', alive: false }];
  await press(MAIN);
  check('(the Bayesian run, Pause answered yes, waits: "Force abort")', await waitFor(() => commands().length > 0) && commands().join() === 'pause'
    && await until(`${ABORT}.textContent === 'Force abort' && !${ABORT}.disabled`, 60), commands().join());
  check('... its tooltip says it replaces the Pause, and not that the run cannot be resumed then (review of SIF-83)',
    await until(`${ABORT}.title.includes('This replaces your Pause: the run ends as cancelled. Only for a run that is stuck.')`, 40), await evaluate(`${ABORT}.title`));
  answers.push(false);
  await press(ABORT); await sleep(400);
  check('... pressed, it says the run cannot come back either way and why, with no advice to wait for the pause (review of SIF-83)',
    /^Force abort\?\n\nThis replaces your Pause: the run ends as cancelled instead of paused\. It cannot come back either way: it is searched by Bayesian optimization, whose search state lives only in its running process\.\n\n/.test(lastDialog().message ?? '')
    && !/resumable|continued|Fine-tune/.test(lastDialog().message ?? ''), lastDialog().message);
  check('... and "no" sends nothing more than the pause', commands().join() === 'pause', commands().join());
  sim.run = {};
  check('(paused again)', await mainReads('Resume', 150));
  log.length = 0; answers.push(true);
  await press(ABORT); await sleep(400);
  check('"Let go" on a paused run asks first, and says that nothing is deleted', /^Let go of this paused run\?/.test(lastDialog().message) && /Nothing is deleted/.test(lastDialog().message), lastDialog().message);
  v = await look();
  check('it sends NO command; the button reads "Start", the run is no longer remembered', log.length === 0 && v.main === 'Start' && v.mainOff === false && v.remembered === null && v.chip === null, JSON.stringify(v));
  check('... and the line under the header names it by its folder, the path in its tooltip (SIF-56)',     // this step's run: a later start, its own folder
    v.banner === `Left paused, nothing deleted: ${sim.dir.split('/').pop()}` && (v.bannerTitle ?? '').startsWith(`${sim.dir}\n`), JSON.stringify([v.banner, v.bannerTitle]));
  check('the run stays on screen under Run status, with its own Continue...', await until(`!!(${CONTINUE}) && !${CONTINUE}.disabled`));

  // ---- 9. the Run status tab's Continue works, and the header follows it; the tab has no run commands of its own ------------
  // Continue... opens the budget form (7.261): no browser prompt; the form says what is wrong before anything is sent.
  log.length = 0; const promptsBefore = dialogs.length;
  await press(CONTINUE);
  check('Continue... opens the budget form: the evaluations used, the run\'s own total in the field, and what it allows', await until(`!!(${FORM})`)
    && await evaluate(`${FIELD}.value === '60' && ${FORM}.textContent.includes('Used ${sim.charged}') && ${FORM}.textContent.includes('Allows ${60 - sim.charged} more')`),
    await evaluate(`${FORM}?.textContent ?? 'no form'`));
  const typed = async text => { await page.setValue(FIELD, text, { event: 'input' }); await sleep(150);
    return evaluate(`({ error: document.querySelector('.continue-form .continue-error')?.textContent ?? null, allows: document.querySelector('.continue-allows')?.textContent ?? '' })`); };
  let f = await typed('12,00');
  check('a separator typo (12,00) is refused on the form, not guessed', /between groups of three digits/.test(f.error ?? ''), JSON.stringify(f));
  f = await typed('62.5');
  check('a fraction is refused', /no fractions/.test(f.error ?? ''), JSON.stringify(f));
  f = await typed(String(Math.max(0, sim.charged - 1)));
  check('a total below (or at) the evaluations used is refused', /cannot be below|must be more than/.test(f.error ?? ''), JSON.stringify(f));
  f = await typed('1,200');
  check('"1,200" reads as 1200: no error, and it allows 1200 minus the used ones', f.error === null && f.allows === `Allows ${1200 - sim.charged} more`, JSON.stringify(f));
  // branch record SIF-66: the field held about six characters under the look's padding, so a used-up run's empty field read
  // "more th" of its "more than 1200"; measured in the field's own font against its room for text
  const room = await evaluate(`(() => { const f = ${FIELD}, s = getComputedStyle(f), c = document.createElement('canvas').getContext('2d');
    c.font = [s.fontStyle, s.fontWeight, s.fontSize, s.fontFamily].join(' ');
    return { room: f.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight), words: c.measureText('more than 12000').width, total: c.measureText('1,000,000').width }; })()`);
  check('"New total" holds "more than 12000" and "1,000,000" whole', room.words <= room.room && room.total <= room.room, JSON.stringify(room));
  await press(`[...document.querySelectorAll('.continue-form button')].find(b => b.textContent === 'Cancel')`);
  check('Cancel closes the form and sends nothing', await until(`!(${FORM})`) && log.length === 0);
  // Branch record SIF-90: the focused field went with the form, and the keyboard fell to the top of the page.
  const focused = `(document.activeElement === document.body ? 'body' : document.activeElement?.outerHTML.slice(0, 90) ?? 'none')`;
  check('... and gives the keyboard focus back to Continue... (SIF-90)', await until(`document.activeElement === ${CONTINUE}`, 20), await evaluate(focused));
  await press(CONTINUE); await until(`!!(${FORM})`);
  await evaluate(`${FIELD}.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`);
  check('Escape closes the form the same way: nothing sent, the focus back on Continue... (SIF-90)', await until(`!(${FORM}) && document.activeElement === ${CONTINUE}`, 20) && log.length === 0,
    await evaluate(focused));
  sim.steps = [{}, { state: 'running', stop_reason: null }];
  await press(CONTINUE); await until(`!!(${FORM})`);
  await press(`document.querySelector('.continue-form button[type=submit]')`);
  check('the form\'s Continue with the run\'s own total continues the run unchanged, and the header takes it: "Pause"', await mainReads('Pause') && log[0]?.name === '/api/runs/continue'
    && log[0]?.body.max_evaluations === null && typeof log[0]?.body.request_id === 'string', JSON.stringify(log[0]));
  check('... the focus goes to the Run status tab, since Continue... is off while the run goes on (SIF-90)',
    await until(`document.activeElement?.matches('footer .tabs button.active') && document.activeElement.textContent === 'Run status' && ${CONTINUE}.disabled`, 20), await evaluate(focused));
  check('no browser prompt was used for it', dialogs.length === promptsBefore, JSON.stringify(dialogs.slice(promptsBefore)));
  check('the Run status tab offers no Save now / Pause / Stop / Force cancel of its own: the header has them (2026-09-29)',
    await evaluate(`![...document.querySelectorAll('.status-grid button')].some(b => /Save now|Pause and save|Stop and save|Force cancel/.test(b.textContent))`));
  sim.steps = [{}, { state: 'pausing' }, {}, { state: 'paused', alive: false }];
  await press(MAIN);
  check('the header\'s Pause pauses it: "Pausing...", then "Resume"', await mainReads('Pausing...') && await mainReads('Resume', 150));
  // A paused run changes only when it is continued: it is read every 15 s, not every 1.5 s as until 2026-09-30.
  const readsWhenPaused = statusRequests; await sleep(3500);
  check('a paused run is not read every 1.5 s: at most one read in 3.5 s', statusRequests - readsWhenPaused <= 1, `${statusRequests - readsWhenPaused} read(s)`);

  // ---- 10. a REAL run: Resume asks for the budget again; a refusal by the backend is shown ---------------------------------------
  // A paused run is read every 15 s since 2026-09-30 (it changes only when it is continued): the page learns that this one
  // is real when it opens, as a page shown a paused real run does.
  sim.mock = false; sim.steps = [{}];
  await send('Page.reload'); await until(`!!(${MAIN})`, 150);
  check('(the page has learned that the run is real)', await until(`/^(fixture_task · )?at \\d+ of 60 evaluations$/.test(${CHIP}?.textContent ?? '')`, 60), await evaluate(`${CHIP}?.textContent`));
  log.length = 0; answers.push(false);
  await press(MAIN); await sleep(500);
  check('Resume of a REAL run asks to authorize what is left of the budget', /REAL simulations \(Virtuoso\/Spectre, or ngspice/.test(lastDialog().message) && new RegExp(`up to ${sim.max - sim.charged} more`).test(lastDialog().message), lastDialog().message);
  check('answering no sends nothing; the run stays paused', log.length === 0 && await mainReads('Resume', 20) && /Not resumed/.test((await look()).banner ?? ''));
  answers.push(true); refuseNext = { name: '/api/runs/continue', detail: { code: 'connection_gate_blocked', message: 'FIXTURE: the connection gate blocked this action.' } };
  await press(MAIN);
  // The backend's sentence leads the banner; its code sits under "Technical details" (7.125).
  check('a refusal is shown under the header with its reason, and the button reads "Resume" again', await until(`/Resume was refused: FIXTURE: the connection gate blocked this action\./.test(${REFUSAL}?.textContent ?? '')
    && /code: connection_gate_blocked/.test(document.querySelector('header .launch-refusal details')?.textContent ?? '')`) && await mainReads('Resume', 20));
  check('the authorization was sent with the request', log[0]?.body.authorize_real_simulation === true, JSON.stringify(log[0]?.body));
  await sleep(2000);
  check('the refusal stays beside the action (it is no passing line) until it is closed', await evaluate(`!!(${REFUSAL})`));
  await press(`document.querySelector('header .launch-refusal button')`);
  check('... and its close takes it away', await until(`!(${REFUSAL})`));

  // ---- 11. a live run this browser does not remember is taken over when the page opens -------------------------------------------
  await forget();
  Object.assign(sim, { dir: DIR, mock: true, state: 'running', alive: true, charged: 3, steps: [] });   // the run the list names
  await open(null);
  check('a live run found in the run list is taken over: "Pause", not "Start"', await mainReads('Pause') && (await look()).remembered === DIR);
  // Record 7.372: a badge beside the run chip says so, the sentence in its tooltip (a line of its own under the header until then).
  const taken = await evaluate(`(() => { const b = document.querySelector('header .run-state .run-taken'); return b ? { label: b.textContent, title: b.title } : null; })()`);
  check('... and a badge beside the run chip says so, the sentence in its tooltip (7.261; a badge since 7.372)', taken?.label === 'started elsewhere'
    && /^The header took over fixture_task__scratch__seed0__0001, a live run started elsewhere/.test(taken.title), JSON.stringify(taken));
  check('"Start" was never offered while it was looked up', !(await seen()).some(s => s[0] === 'Start' && s[1] === false), JSON.stringify(await seen()));
  await shot('run-7-taken-over.png');

  // ---- 12. Continue of ANOTHER run waits while the header's run is live (review of 2026-09-29, A9) ----------------------------------
  // It used to start a second live run that had no Pause or Abort anywhere on the page (the tab's run buttons went on 2026-09-29).
  const showInTabs = async dir => {                                               // the run window: a double click on the run's row
    await evaluate(`document.querySelector('footer .tabs button.run-list-button').click()`, true);
    const target = await browser.window(RUNS_WINDOW).catch(() => null);
    if (!target) throw new Error('the run window did not open');
    const far = await browser.attach(target);
    const ok = await far.evaluate(`new Promise(done => { let tries = 0; const tick = () => {
      const row = [...document.querySelectorAll('.run-window table.run-table tbody > tr')].find(r => r.title === ${JSON.stringify(dir)});
      if (row) { row.children[4].dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); done(true); } else if (++tries > 50) done(false); else setTimeout(tick, 100); }; tick(); })`);
    far.close();
    // A run chosen closes the window by itself (record 7.291); it is closed here only when it is still open.
    try { await browser.window(RUNS_WINDOW, { present: false, ms: 5000 }); } catch { await send('Target.closeTarget', { targetId: target.id }).catch(() => undefined); }
    if (!ok) throw new Error(`the run ${dir} was not in the run window`);
  };
  otherListed = true; log.length = 0;
  await showInTabs(OTHER);
  check('(the Run status tab shows another run, a paused one, while the header\'s run is live)', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(OTHER)})`)
    && (await look()).main === 'Pause');
  // Branch record SIF-91: the lock followed the run the tabs show - with this paused run shown, the root could be changed under
  // the live one, and the page's run list moved away from it.
  const lockLive = await evaluate(ROOT_LOCK);
  check('... the output root and Browse stay locked while the header\'s run works, though the tabs show a paused run (SIF-91)',
    JSON.stringify(lockLive) === '{"root":true,"browse":true,"hint":true}', JSON.stringify(lockLive));
  // Branch record SIF-72: the survey's tab line named only the run shown ("... · completed") under a header running another.
  const strip = await evaluate(`({ shown: ${SHOWN_LINE}, title: ${HEADER_LINK}?.title ?? null })`);
  check('... the tab line says "Shown:" before it, and offers the header\'s live run beside it, its folder in the tooltip (SIF-72)',
    /^Shown: \S+ \S+ · fixture_task · New model, seed 1 · paused · MOCK$/.test(strip.shown) && (strip.title ?? '').includes(`act on: ${DIR}\n`), JSON.stringify(strip));
  const other = await evaluate(`({ off: ${CONTINUE}?.disabled, title: ${CONTINUE}?.title ?? '' })`);
  check('its Continue is off while the header\'s run is live, and its tooltip says why', other.off === true && other.title.startsWith('Continue: ') && /another run is live in the header/i.test(other.title), JSON.stringify(other));
  sim.steps = [{}, { state: 'pausing' }, {}, { state: 'paused', alive: false }];
  await press(MAIN);
  check('(the header\'s run is paused)', await mainReads('Resume', 150));
  check('... and with no run working the output root can be changed again (SIF-91)', await until(`(${ROOT_LOCK}).root === false && !(${ROOT_LOCK}).hint`, 30), JSON.stringify(await evaluate(ROOT_LOCK)));
  check('once the header\'s run is paused, Continue of the other run is offered again', await until(`!!(${CONTINUE}) && !${CONTINUE}.disabled && ${CONTINUE}.title.startsWith('Continue: A paused')`),
    await evaluate(`${CONTINUE}?.title ?? ''`));
  check('nothing was continued meanwhile', !log.some(l => l.name === '/api/runs/continue'), JSON.stringify(log.map(l => l.name)));
  // Record 7.221: a run whose save point was written by an older version of the optimizer code cannot be continued (an exact
  // resume needs that code); its Continue goes off with the reason once the paused run is read again (every 15 s).
  otherOlder = true;
  check('a run saved by an older version of the optimizer code: its Continue is off and the tooltip says why (7.221)',
    await until(`!!(${CONTINUE}) && ${CONTINUE}.disabled && /older version of the optimizer code/.test(${CONTINUE}.title) && /fine-tune or frozen/.test(${CONTINUE}.title)`, 250),
    await evaluate(`${CONTINUE}?.title ?? ''`));
  check('... and nothing was continued', !log.some(l => l.name === '/api/runs/continue'), JSON.stringify(log.map(l => l.name)));
  // The continuation check (7.261): the reason is said beside Continue... before any press, and the backend's alternative is a button.
  check('the reason stands beside Continue..., not only in its tooltip', await until(`/older version of the optimizer code/.test(document.querySelector('.status-grid .continue-why')?.textContent ?? '')`));
  const ALTERNATIVE = `document.querySelector('.status-grid .continue-alternative')`;
  check('the new run that still goes on from its model is offered as a button', (await evaluate(`${ALTERNATIVE}?.textContent ?? ''`)) === 'Fine-tune from its newest save point (a new run)');
  await press(ALTERNATIVE);
  check('pressing it makes the next run a fine-tune from exactly that save point, starts nothing, and says so', await until(`(() => { const c = JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null');
    return c?.run?.mode === 'fine_tune' && c.run.model_source?.run_dir === ${JSON.stringify(OTHER)} && c.run.model_source?.checkpoint_id === 'ckpt-000007'; })()`, 40)
    && /fine-tunes from fixture_task__scratch__seed1__0002 at its save point ckpt-000007/.test((await look()).banner ?? '') && !log.some(l => /start|continue/.test(l.name)), (await look()).banner ?? '');
  otherOlder = false;
  // A task's baseline started by Save task (the page's own event, TaskSave.tsx): taken into the header only when that is free or holds a
  // run at rest, and a paused run it lets go of is named (7.261). The header holds DIR, paused; OTHER stands in for the baseline run.
  log.length = 0;
  const baseline = { run_dir: OTHER, run_id: 'fixture-run-2', mock: true, mock_notice: 'FIXTURE MOCK DATA: nothing was started.' };
  await evaluate(`window.dispatchEvent(new CustomEvent('gator-task-baseline-started', { detail: ${JSON.stringify(baseline)} }))`);
  check('a task baseline while the header holds a paused run: the header takes it and names the paused run, which stays paused',
    await until(`localStorage.getItem(${JSON.stringify(RUN_KEY)}) === ${JSON.stringify(OTHER)}`) && /fixture_task__scratch__seed0__0001 stays paused; continue it from Runs\./.test((await look()).banner ?? '')
    && !log.some(l => l.name === '/api/runs/command'), (await look()).banner ?? '');

  // ---- 13. a remembered run that is gone is let go of - not asked for every 1.5 s for ever (review of 2026-09-29) -----------------
  await forget();
  Object.assign(sim, { dir: DIR, state: null, alive: false, steps: [] }); otherListed = false;   // nothing live in the list to take over
  await open(GONE);
  check('a remembered run that is gone (404): the bottom tabs let go of it too, "No run selected"', await until(`document.querySelector('footer .tabs .run-list-current')?.textContent === 'No run selected'`, 60)
    && (await look()).main === 'Start', await evaluate(`document.querySelector('footer .tabs .run-list-current')?.textContent ?? ''`));
  const goneBefore = goneAsked; await sleep(4000);
  check('... and it is asked for no more', goneAsked === goneBefore && goneAsked >= 1, `${goneAsked - goneBefore} request(s) in 4 s, ${goneAsked} in all`);

  // ---- 14. a reload during a start: the page asks what became of it by its id, and never sends it again (7.261) ----------------------
  log.length = 0; holdNext = '/api/runs/start';
  await press(MAIN);
  check('(Start is on its way: "Starting...")', await mainReads('Starting...'));
  const sentId = log[0]?.body.request_id;
  requestAnswer = { state: 'done', answer: { ...started(), run_dir: DIR } };
  Object.assign(sim, { dir: DIR, state: 'running', alive: true, charged: 2, steps: [] });   // the run that start made
  held = null;                                                                     // its request belongs to the page that goes away
  await send('Page.reload'); await until(`!!(${MAIN})`, 150);
  check('after a reload during the start the page asks what became of it, by its id', await waitFor(() => requestLookups.includes(sentId), 60), JSON.stringify(requestLookups));
  check('... takes the run it made into the header ("Pause") and sends no second start', await mainReads('Pause', 150) && log.filter(l => l.name === '/api/runs/start').length === 1,
    JSON.stringify(log.map(l => l.name)));
  check('... and says that it was not sent again', await until(`/sent before the page was reloaded made this run; it was not sent again/.test(document.querySelector('.banner')?.textContent ?? '')`, 60),
    (await look()).banner ?? '');
  check('... and keeps no request any more', (await evaluate(`sessionStorage.getItem('gator-workbench-launch-v1')`)) === null);

  reportRefused(refused);
  check('every question on screen was planned by this check', dialogs.every(d => d.planned), JSON.stringify(dialogs.filter(d => !d.planned)));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
});
