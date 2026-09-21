// Browser check of "Save now" (header, and the Run status tab): save the RUNNING run's model without pausing
// (run command `checkpoint`; there is no frontend test runner in this project).
// Same approach as run_control_check.mjs: a throwaway headless Edge over the DevTools protocol against a RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY /api/runs/* request and every validation is answered HERE by a small
// simulated run labelled FIXTURE; other GET requests pass through and every other writing request is refused. So this
// check can start, pause, save or cancel NOTHING on the backend it runs against - it is safe next to a live run.
// The browser profile is new and temporary: the user's saved configuration and remembered run are not touched.
// What it pins (user request 2026-09-21, "add a save now button"): the button exists left of the main button (Abort
// stays directly right of it) and is off unless a run is RUNNING; one press = one `checkpoint` command, no pause - the
// main button keeps reading Pause; it reads "Saving..." until the RUN reports that request as saved, then says where it
// was saved; a refusal is shown in the backend's plain words; the header does not shift; the Run status tab has the
// same button and shows the request in its "Last checkpoint" row.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/save_now_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9389, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-savenow-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- the simulated run (FIXTURE) -------------------------------------------------------------------------------------
const RUN_KEY = 'gator-workbench-current-run-v1';
const DIR = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed0__0001';
const sim = { state: 'running', alive: true, charged: 12, max: 60, beat: 0, manual_save: null, last_checkpoint_utc: null };
const listed = () => [{ run_dir: DIR, run_id: 'fixture-run', task_id: 'fixture_task:0000', task_definition_hash: 'fixture', mode: 'scratch', mock: true, seed: 0,
  created_utc: '2026-09-21T00:00:00+00:00', state: sim.state, experiment: 'fixture_experiment__0001', evaluations: null, first_feasible_eval_count: null, resumability: null }];
const statusOf = () => ({ state: sim.state, run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: 'mock', mock: true, worker_alive: sim.alive, run_dir: DIR,
  heartbeat_utc: new Date(Date.UTC(2026, 8, 21, 0, 0, 0) + 1000 * ++sim.beat).toISOString(), stop_reason: null, error: null, active_workers: [], concurrency: 1, learner_updates: 0,
  first_feasible: null, budget: { max_evaluations: sim.max, max_launches: null, max_retries: 0, charged: sim.charged, reserved: 0, in_flight: sim.alive ? 1 : 0, completed: sim.charged,
    failed: 0, released: 0, remaining: sim.max - sim.charged, launches: sim.charged, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: sim.last_checkpoint_utc, manual_save: sim.manual_save, paths: { run_dir: DIR }, connection: { overall: 'not_applicable' }, summary: null,
  manifest: { mode: 'scratch', mock: true, task_id: 'fixture_task:0000', seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: sim.max }, mock_notice: 'FIXTURE MOCK DATA: nothing was started.' } });
const VALID = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: true };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:opamp', APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture' }, research: {} };
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const refused = []; const commands = []; const dialogs = []; let refuseNext = null, requests = 0;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/status') return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, statusOf()) : fulfil(requestId, 404, { detail: 'Not a run directory' });
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: listed() });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/download') return fulfil(requestId, 200, { output: { save_checkpoints: true } });
    if (name === '/api/runs/command') {
      commands.push(body.command);
      if (refuseNext) { const detail = refuseNext; refuseNext = null; return fulfil(requestId, 409, { detail }); }
      return fulfil(requestId, 200, { id: `fixture-request-${++requests}`, command: body.command, issued_utc: '2026-09-21T00:00:00+00:00' });
    }
    if (request.method === 'GET') return send('Fetch.continueRequest', { requestId });
    refused.push(`${request.method} ${name}`);
    return fulfil(requestId, 418, { detail: { message: 'FIXTURE: this check lets no writing request through' } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away */ });
    else if (m.method === 'Page.javascriptDialogOpening') { dialogs.push(m.params.message); send('Page.handleJavaScriptDialog', { accept: false }).catch(() => undefined); }
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 80) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const SAVE = `document.querySelector('header button.run-save')`, MAIN = `document.querySelector('header button.run-main')`, ABORT = `document.querySelector('header button.run-abort')`;
  const look = () => evaluate(`({ save: ${SAVE}?.textContent, saveOff: ${SAVE}?.disabled, title: ${SAVE}?.title, main: ${MAIN}?.textContent, abortOff: ${ABORT}?.disabled,
    banner: document.querySelector('.banner')?.textContent ?? null, mainX: ${MAIN}?.getBoundingClientRect().x, saveWidth: ${SAVE}?.getBoundingClientRect().width })`);
  const banner = text => until(`(document.querySelector('.banner')?.textContent ?? '').includes(${JSON.stringify(text)})`, 60);
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = document.querySelector('header').getBoundingClientRect(); return { x: 0, y: 0, width: 1680, height: Math.min(1050, r.bottom + 60), scale: 1 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (location.protocol.startsWith('http') && !sessionStorage.getItem('fixture-seeded')) { sessionStorage.setItem('fixture-seeded', '1');
    localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))}); localStorage.setItem(${JSON.stringify(RUN_KEY)}, ${JSON.stringify(DIR)}); }` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${MAIN})`, 150))) throw new Error('the run buttons never appeared; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  if (!(await until(`!!(${SAVE})`, 30))) throw new Error('this page has no "Save now" button: the served frontend is older than it (npm run build, then reload)');

  // ---- a running run: the button is there, in its place, and on ------------------------------------------------------------
  check('the header takes the remembered run as RUNNING (main button reads Pause)', await until(`${MAIN}.textContent === 'Pause'`, 80));
  let now = await look();
  check('"Save now" is a button left of the main button', await evaluate(`${SAVE}.tagName === 'BUTTON' && ${SAVE}.nextElementSibling === ${MAIN}`));
  check('Abort still sits directly to the right of the main button', await evaluate(`${MAIN}.nextElementSibling === ${ABORT}`));
  check('while the run is running it is enabled and says what it does', now.save === 'Save now' && now.saveOff === false && /without pausing/.test(now.title) && /goes on by itself/.test(now.title), JSON.stringify([now.save, now.saveOff]));
  const mainX = now.mainX, saveWidth = now.saveWidth;
  await shot('save-now-1-running.png');

  // ---- one press = one `checkpoint` command; no pause; "Saving..." until the RUN says it is saved ------------------------------------
  await evaluate(`${SAVE}.click()`);
  check('one press sends exactly one `checkpoint` command', await until(`${SAVE}.textContent === 'Saving...'`, 40) && commands.join() === 'checkpoint', commands.join());
  now = await look();
  check('it reads "Saving..." and cannot be pressed twice', now.save === 'Saving...' && now.saveOff === true);
  check('the run is NOT paused: the main button still reads Pause and Abort stays available', now.main === 'Pause' && now.abortOff === false, JSON.stringify([now.main, now.abortOff]));
  check('the header does not shift while the label changes', Math.abs(now.mainX - mainX) < 0.5 && Math.abs(now.saveWidth - saveWidth) < 0.5, `${mainX} -> ${now.mainX}`);
  check('the line under the header says what will happen', await banner('Save requested: the model is saved as soon as the simulation in flight has finished'));
  await shot('save-now-2-saving.png');
  sim.manual_save = { id: 'fixture-request-1', state: 'waiting', requested_utc: '2026-09-21T00:00:10+00:00', checkpoint_id: null, saved_utc: null, evaluations: null };
  await sleep(2500);
  check('while the run reports the request as waiting it keeps reading "Saving..."', (await look()).save === 'Saving...');
  sim.manual_save = { id: 'some-older-request', state: 'saved', requested_utc: '2026-09-21T00:00:01+00:00', checkpoint_id: 'ckpt-00000005-old', saved_utc: '2026-09-21T00:00:02+00:00', evaluations: 5 };
  await sleep(2500);
  check('an OLDER request reported as saved does not end the wait', (await look()).save === 'Saving...');
  sim.charged = 14; sim.last_checkpoint_utc = '2026-09-21T00:00:20+00:00';
  sim.manual_save = { id: 'fixture-request-1', state: 'saved', requested_utc: '2026-09-21T00:00:10+00:00', checkpoint_id: 'ckpt-00000014-fixture', saved_utc: '2026-09-21T00:00:20+00:00', evaluations: 14 };
  check('when the run reports THIS request as saved the button is back', await until(`${SAVE}.textContent === 'Save now' && !${SAVE}.disabled`, 60));
  check('... and the line says where it was saved, and that the run goes on', await banner('Saved at 14 evaluations as save point ckpt-00000014-fixture. The run goes on.'));
  check('no pause, stop or cancel was ever sent', commands.join() === 'checkpoint', commands.join());
  await shot('save-now-3-saved.png');

  // ---- a refusal is shown in the backend's plain words -----------------------------------------------------------------------------
  refuseNext = { code: 'checkpoints_off', message: 'FIXTURE: This run was started with "Model checkpoints" switched off, so it keeps no saved model.' };
  await evaluate(`${SAVE}.click()`);
  check('a refusal is shown as the backend worded it', await banner('This run was started with "Model checkpoints" switched off'));
  check('... and the button is back at once', await until(`${SAVE}.textContent === 'Save now' && !${SAVE}.disabled`, 40));

  // ---- the Run status tab: the same command, and the request in the "Last checkpoint" row -------------------------------------------------
  await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Run status')?.click()`);
  const TAB_SAVE = `[...document.querySelectorAll('.status-grid button')].find(b => b.textContent === 'Save now')`;
  check('the Run status tab has "Save now" next to "Pause and save"', await until(`!!(${TAB_SAVE}) && ${TAB_SAVE}.nextElementSibling?.textContent === 'Pause and save'`, 60));
  const ROW = `[...document.querySelectorAll('.status-grid tr')].find(r => r.cells[0]?.textContent === 'Last checkpoint')?.cells[1]?.textContent ?? ''`;
  check('its "Last checkpoint" row shows the answered request', await until(`/Save now: saved at 14 evaluations \\(ckpt-00000014-fixture\\)/.test(${ROW})`, 40), await evaluate(ROW));
  const before = commands.length;
  await evaluate(`${TAB_SAVE}.click()`);
  check('pressing it sends one `checkpoint` command for the run shown there', await (async () => { for (let i = 0; i < 40 && commands.length === before; i++) await sleep(100); return commands.length === before + 1 && commands[before] === 'checkpoint'; })(), commands.join());
  sim.manual_save = { id: 'fixture-request-3', state: 'waiting', requested_utc: '2026-09-21T00:00:30+00:00', checkpoint_id: null, saved_utc: null, evaluations: null };
  check('while a request is waiting the row says so and the tab button is off', await until(`/Save now: requested, waiting for the simulation in flight to finish/.test(${ROW}) && ${TAB_SAVE}.disabled`, 60), await evaluate(ROW));
  await shot('save-now-4-status-tab.png');

  // ---- not running: off, with the reason -----------------------------------------------------------------------------------------------------------
  sim.state = 'pausing';
  check('while the run is pausing "Save now" is off (the pause saves everything)', await until(`${MAIN}.textContent === 'Pausing...' && ${SAVE}.disabled && ${TAB_SAVE}.disabled`, 60));
  Object.assign(sim, { state: 'paused', alive: false, manual_save: null });
  check('on a paused run it is off and says why', await until(`${MAIN}.textContent === 'Resume' && ${SAVE}.disabled && /Only while a run is running/.test(${SAVE}.title) && ${TAB_SAVE}.disabled`, 60), (await look()).title);
  await shot('save-now-5-paused.png');

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('no confirmation dialog was needed for a save', dialogs.length === 0, dialogs.join(' | ').slice(0, 200));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  console.log(failures ? `\n${failures} check(s) FAILED` : '\nall checks passed');
  ws.close();
} catch (error) {
  failures++; console.log(`FAIL  the check could not run: ${error.message}`);
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; it is a temp dir */ }
}
process.exit(failures ? 1 : 0);
