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
// whatever run the bottom tabs show, also across a reload, and never offers a second Start meanwhile.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 60 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/run_control_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, reportRefused, RUN_KEY, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('runcontrol');

// ---- the simulated run (FIXTURE): one status "file" that the page polls, advanced by scripted steps ----------------
const DIR = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed0__0001';
const sim = { dir: DIR, mock: true, state: null, alive: false, charged: 0, max: 60, stop_reason: null, beat: 0, steps: [], output: {}, starts: 0 };
const listed = () => sim.state ? [{ run_dir: DIR, run_id: 'fixture-run', task_id: 'fixture_task:0000', task_definition_hash: 'fixture', mode: 'scratch', mock: sim.mock, seed: 0,
  created_utc: '2026-09-21T00:00:00+00:00', state: sim.state, experiment: 'fixture_experiment__0001', evaluations: null, first_feasible_eval_count: null, resumability: null }] : [];
const statusOf = () => {
  const step = sim.steps.shift();
  if (step) Object.assign(sim, step);
  else if (sim.alive && sim.state === 'running' && sim.charged < sim.max) sim.charged++;
  const at = new Date(Date.UTC(2026, 8, 21, 0, 0, 0) + 1000 * ++sim.beat).toISOString();
  return { state: sim.state, run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: sim.mock ? 'mock' : 'real', mock: sim.mock, worker_alive: sim.alive,
    run_dir: sim.dir, heartbeat_utc: at, stop_reason: sim.stop_reason, error: null, active_workers: [], concurrency: 1, learner_updates: 0, first_feasible: null,
    budget: { max_evaluations: sim.max, max_launches: null, max_retries: 0, charged: sim.charged, reserved: 0, in_flight: sim.alive && sim.state === 'running' ? 1 : 0,
      completed: sim.charged, failed: 0, released: 0, remaining: sim.max - sim.charged, launches: sim.charged, retries: 0, cache_hits: 0, first_feasible: null },
    best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: sim.dir }, connection: { overall: 'not_applicable' }, summary: null,
    manifest: { mode: 'scratch', mock: sim.mock, task_id: 'fixture_task:0000', seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: sim.max },
      mock_notice: sim.mock ? 'FIXTURE MOCK DATA: nothing was started.' : null } };
};
const started = () => ({ run_dir: sim.dir, run_id: 'fixture-run', mock: sim.mock, worker_pid: 1, paths: { run_dir: sim.dir }, connection_gate: { status: 'not_applicable' },
  mock_notice: sim.mock ? 'FIXTURE MOCK DATA: nothing was started.' : null });
const validReport = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: true };

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);     // as "Load task" merges it
  const page = await browser.open();
  const { send, evaluate, until, fulfil, consoleErrors } = page;
  const refused = []; const log = []; const dialogs = []; const answers = [];
  let held = null, holdNext = null, refuseNext = null, statusRequests = 0;
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, validReport);
    if (name === '/api/runs/status') { statusRequests++; return url.searchParams.get('run_dir') === sim.dir ? fulfil(requestId, 200, statusOf()) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: listed() });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/download') return fulfil(requestId, 200, { output: sim.output });
    if (['/api/runs/start', '/api/runs/continue', '/api/runs/command'].includes(name)) {
      log.push({ name, body });
      if (refuseNext && refuseNext.name === name) { const refusal = refuseNext; refuseNext = null; return fulfil(requestId, 409, { detail: refusal.detail }); }
      const reply = () => {
        if (name === '/api/runs/command') return fulfil(requestId, 200, { id: 'fixture', command: body.command });
        // Every Start makes a NEW run folder, as the backend does: the page polls a run that has ended for good only once a
        // minute (App.tsx, 2026-09-22), and a second Start into the same folder would never be seen as running again.
        Object.assign(sim, { alive: true }, name === '/api/runs/start' ? { state: 'created', charged: 0, stop_reason: null, dir: sim.starts++ ? `${DIR}__${sim.starts}` : DIR } : {});
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
  const BASELINE = `[...document.querySelectorAll('header button')].find(b => b.textContent === 'Single baseline simulation')`;
  const look = () => evaluate(`({ main: ${MAIN}?.textContent, mainOff: ${MAIN}?.disabled, abort: ${ABORT}?.textContent, abortOff: ${ABORT}?.disabled, chip: ${CHIP}?.textContent ?? null,
    baselineOff: ${BASELINE}?.disabled, banner: document.querySelector('.banner')?.textContent ?? null, remembered: localStorage.getItem(${JSON.stringify(RUN_KEY)}) })`);
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
  check('with no run held the page asks for no run status and sends no command', statusRequests === 0 && log.length === 0, `${statusRequests} status request(s)`);
  await shot('run-1-start.png');

  // ---- 2. Start -> "Starting..." -> "Pause" ----------------------------------------------------------------------------
  holdNext = '/api/runs/start';
  await press(MAIN);
  check('while the backend is starting the run the button reads "Starting..." and is disabled', await mainReads('Starting...') && (await look()).mainOff === true);
  v = await look();
  check('Abort and the baseline simulation are disabled meanwhile', v.abortOff === true && v.baselineOff === true, JSON.stringify(v));
  check('ONE start request was sent, for a full run with the page\'s configuration', log.length === 1 && log[0].name === '/api/runs/start' && log[0].body.baseline_only === false
    && log[0].body.config?.schema_version === CONFIG.schema_version && !('authorize_real_simulation' in log[0].body), JSON.stringify(log.map(l => l.name)));
  sim.steps = [{}, {}, { state: 'starting' }, { state: 'running' }];
  await held(); held = null;
  check('after Start the button reads "Pause"', await mainReads('Pause') && (await look()).mainOff === false);
  v = await look();
  check('Abort is enabled, the baseline simulation is not available while the run is active', v.abort === 'Abort' && v.abortOff === false && v.baselineOff === true);
  check('the run is remembered by this browser', v.remembered === DIR, String(v.remembered));
  check('the MOCK notice and the run directory are reported as before', /FIXTURE MOCK DATA/.test(v.banner ?? '') && (v.banner ?? '').includes(DIR), v.banner ?? '');
  check('the header shows the run and its progress', await until(`/^running \\d+ \\/ 60 \\[MOCK\\]$/.test(${CHIP}?.textContent ?? '')`), (await look()).chip ?? '');
  check('the Run status tab shows this run', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DIR)})`));
  await shot('run-2-running.png');

  // ---- 3. Pause -> "Pausing..." -> "Resume" -----------------------------------------------------------------------------
  sim.steps = [{}, {}, { state: 'pausing', stop_reason: 'user_pause' }, {}, { state: 'paused' }, {}, { alive: false }];   // the run answers late, then finishes its files
  const before = dialogs.length;
  await press(MAIN);
  check('Pause reads "Pausing..." at once, before the run has answered', await mainReads('Pausing...', 15) && (await look()).mainOff === true);
  check('ONE pause command was sent, without a question', await waitFor(() => commands().length > 0) && commands().join() === 'pause' && dialogs.length === before, commands().join());
  v = await look();
  check('while the simulation in flight finishes, Abort reads "Force abort"', v.abort === 'Force abort' && v.abortOff === false && /pausing/.test(v.chip ?? ''), JSON.stringify(v));
  await shot('run-3-pausing.png');
  check('after the pause the button reads "Resume"', await mainReads('Resume', 150) && (await look()).mainOff === false);
  v = await look();
  check('Abort is back to "Abort", the header says where the run stands', v.abort === 'Abort' && v.abortOff === false && /^paused at \d+ \/ 60 \[MOCK\]$/.test(v.chip ?? ''), JSON.stringify(v));
  check('the baseline simulation stays unavailable while the header holds a paused run', v.baselineOff === true);
  check('the line under the header no longer says "Pausing": it says that the run is paused and saved', /^Paused at \d+ \/ 60: everything is saved/.test(v.banner ?? ''), v.banner ?? '');
  let labels = (await seen()).map(s => s[0]);
  check('the button went Start -> Starting... -> Pause -> Pausing... -> Resume with nothing in between', labels.join(' > ') === 'Start > Starting... > Pause > Pausing... > Resume', labels.join(' > '));
  await shot('run-4-paused.png');

  // ---- 4. a paused run is left alone; a live run keeps its Pause whatever the bottom tabs show ------------------------------
  // The bottom tabs are put on no run the way a user does it: the run button of the tab strip opens the run window
  // (RunList.tsx, a page of its own with its own DevTools session), and "Clear" (it shows no run) is pressed there.
  const showNoRun = async () => {
    await evaluate(`document.querySelector('footer .tabs button.run-list-button').click()`, true);   // a click that may open a window
    const target = await browser.window('GATOR - runs').catch(() => null);
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
  labels = (await seen()).map(s => s[0]);
  check('it never fell back to "Resume" or "Pausing..." while the new worker was starting', labels.slice(5).join(' > ') === 'Resuming... > Pause', labels.slice(5).join(' > '));
  await showNoRun();                                                               // Resume brought the run back under Run status; look away again
  await sleep(300); const liveBefore = statusRequests; await sleep(3500);
  check('with the bottom tabs on no run, the live run is polled by the header and keeps its Pause', statusRequests > liveBefore && (await look()).main === 'Pause', `${statusRequests - liveBefore} request(s) in 3.5 s`);
  check('the header follows its progress', /^running \d+ \/ 60 \[MOCK\]$/.test((await look()).chip ?? ''), (await look()).chip ?? '');
  await press(CHIP);
  check('pressing the run in the header shows it under Run status again', await until(`[...document.querySelectorAll('.status-grid td')].some(td => td.textContent === ${JSON.stringify(DIR)})`));

  // ---- 6. a reload: the live run is still the header's run, and "Start" is never offered meanwhile ---------------------------
  await send('Page.reload'); await until(`!!(${MAIN})`, 150);
  check('after a reload the button reads "Pause" for the remembered live run', await mainReads('Pause'));
  const offered = (await seen()).filter(s => s[0] === 'Start' && s[1] === false);
  check('an enabled "Start" was never shown while the remembered run was looked up', offered.length === 0, JSON.stringify(await seen()));

  // ---- 7. Abort: asked first; graceful stop; "Force abort" as the second step --------------------------------------------------
  log.length = 0; answers.push(false);
  await press(ABORT); await sleep(400);
  check('Abort asks first, in plain words', lastDialog().type === 'confirm' && /^Abort this run\?/.test(lastDialog().message) && /allowed to finish/.test(lastDialog().message) && /use Pause instead/.test(lastDialog().message), lastDialog().message);
  check('answering no sends nothing', log.length === 0 && (await look()).main === 'Pause');
  answers.push(true); sim.steps = [{}, { state: 'stopping', stop_reason: 'user_stop' }];
  await press(ABORT);
  check('Abort reads "Aborting..." and sends ONE graceful stop (the simulation in flight may finish)', await mainReads('Aborting...') && await waitFor(() => commands().length > 0) && commands().join() === 'stop', commands().join());
  check('while it waits, the second button reads "Force abort"', await until(`${ABORT}.textContent === 'Force abort' && !${ABORT}.disabled`) && /aborting/.test((await look()).chip ?? ''));
  await shot('run-5-aborting.png');
  answers.push(true);
  await press(ABORT); await sleep(400);
  check('Force abort asks again and says what it costs', /^Force abort\?/.test(lastDialog().message) && /still counts against the\s+budget/.test(lastDialog().message.replace(/\n/g, ' ')) && /stuck/.test(lastDialog().message), lastDialog().message);
  check('it sends ONE forced cancel and cannot be pressed twice', await waitFor(() => commands().length > 1) && commands().join() === 'stop,cancel' && (await look()).abortOff === true, commands().join());
  sim.steps = [{}, { state: 'cancelled', stop_reason: 'user_cancel' }, { alive: false }];
  check('when the run has ended the button reads "Start" again', await mainReads('Start', 150) && (await look()).mainOff === false);
  v = await look();
  check('the line under the header says that the run has ended, and how', /^The run has ended \(cancelled\) at \d+ \/ 60/.test(v.banner ?? ''), v.banner ?? '');
  check('Abort is disabled, the baseline simulation is available, the header says how the run ended', v.abortOff === true && v.baselineOff === false && /^cancelled \d+ \/ 60 \[MOCK\]$/.test(v.chip ?? ''), JSON.stringify(v));
  await shot('run-6-ended.png');

  // ---- 8. a run that cannot come back is announced BEFORE the pause; Abort on a paused run lets go of it -----------------------
  await press(MAIN);
  check('a new Start after an ended run works', await mainReads('Pause'));
  sim.steps = [{ state: 'running' }];
  sim.output = { save_checkpoints: true, save_replay_snapshots: false }; log.length = 0; answers.push(false);
  await press(MAIN); await sleep(600);
  check('Pause warns when the run was started without replay snapshots', /cannot be resumed after a pause/.test(lastDialog().message ?? '') && /replay snapshots/.test(lastDialog().message ?? ''), lastDialog().message);
  check('answering no sends nothing and the button reads "Pause" again', log.length === 0 && await mainReads('Pause', 20));
  sim.output = {}; sim.steps = [{ state: 'pausing' }, { state: 'paused', alive: false }];
  await press(MAIN);
  check('(paused again)', await mainReads('Resume', 150));
  log.length = 0; answers.push(true);
  await press(ABORT); await sleep(400);
  check('Abort on a paused run says that nothing is deleted', /^Let go of this paused run\?/.test(lastDialog().message) && /Nothing is deleted/.test(lastDialog().message), lastDialog().message);
  v = await look();
  check('it sends NO command; the button reads "Start", the run is no longer remembered', log.length === 0 && v.main === 'Start' && v.mainOff === false && v.remembered === null && v.chip === null, JSON.stringify(v));
  check('the run stays on screen under Run status, with its own Continue', await evaluate(`[...document.querySelectorAll('.status-grid button')].some(b => b.textContent === 'Continue' && !b.disabled)`));

  // ---- 9. the Run status tab's Continue works, and the header follows it; the tab has no run commands of its own ------------
  log.length = 0; answers.push(true);                                           // Continue asks for a new total budget: OK with nothing typed = unchanged
  sim.steps = [{}, { state: 'running', stop_reason: null }];
  await press(`[...document.querySelectorAll('.status-grid button')].find(b => b.textContent === 'Continue')`);
  check('"Continue" of the Run status tab continues the run, and the header takes it: "Pause"', await mainReads('Pause') && log[0]?.name === '/api/runs/continue' && log[0]?.body.max_evaluations === null, JSON.stringify(log[0]));
  check('the Run status tab offers no Save now / Pause / Stop / Force cancel of its own: the header has them (2026-09-29)',
    await evaluate(`![...document.querySelectorAll('.status-grid button')].some(b => /Save now|Pause and save|Stop and save|Force cancel/.test(b.textContent))`));
  sim.steps = [{}, { state: 'pausing' }, {}, { state: 'paused', alive: false }];
  await press(MAIN);
  check('the header\'s Pause pauses it: "Pausing...", then "Resume"', await mainReads('Pausing...') && await mainReads('Resume', 150));

  // ---- 10. a REAL run: Resume asks for the budget again; a refusal by the backend is shown ---------------------------------------
  sim.mock = false; sim.steps = [{}];
  check('(the page has learned that the run is real)', await until(`/^paused at/.test(${CHIP}?.textContent ?? '') && !/MOCK/.test(${CHIP}.textContent)`, 60));   // the next poll, not a fixed wait
  log.length = 0; answers.push(false);
  await press(MAIN); await sleep(500);
  check('Resume of a REAL run asks to authorize what is left of the budget', /REAL simulations \(Virtuoso\/Spectre, or ngspice/.test(lastDialog().message) && new RegExp(`up to ${sim.max - sim.charged} more`).test(lastDialog().message), lastDialog().message);
  check('answering no sends nothing; the run stays paused', log.length === 0 && await mainReads('Resume', 20) && /Not resumed/.test((await look()).banner ?? ''));
  answers.push(true); refuseNext = { name: '/api/runs/continue', detail: { code: 'connection_gate_blocked', message: 'FIXTURE: the connection gate blocked this action.' } };
  await press(MAIN);
  check('a refusal is shown with its reason and the button reads "Resume" again', await until(`/connection_gate_blocked: FIXTURE/.test(document.querySelector('.banner.error')?.textContent ?? '')`) && await mainReads('Resume', 20));
  check('the authorization was sent with the request', log[0]?.body.authorize_real_simulation === true, JSON.stringify(log[0]?.body));

  // ---- 11. a live run this browser does not remember is taken over when the page opens -------------------------------------------
  await forget();
  Object.assign(sim, { dir: DIR, mock: true, state: 'running', alive: true, charged: 3, steps: [] });   // the run the list names
  await open(null);
  check('a live run found in the run list is taken over: "Pause", not "Start"', await mainReads('Pause') && (await look()).remembered === DIR);
  check('"Start" was never offered while it was looked up', !(await seen()).some(s => s[0] === 'Start' && s[1] === false), JSON.stringify(await seen()));
  await shot('run-7-taken-over.png');

  reportRefused(refused);
  check('every question on screen was planned by this check', dialogs.every(d => d.planned), JSON.stringify(dialogs.filter(d => !d.planned)));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
});
