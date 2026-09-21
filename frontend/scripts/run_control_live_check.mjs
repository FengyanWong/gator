// LIVE companion of run_control_check.mjs: the header's Start -> Pause -> Resume -> Abort pressed in a real (headless)
// browser against a real backend with a real detached worker - on the synthetic MOCK task only (free, no bridge, no
// Virtuoso). Nothing is intercepted, so what is checked is the REAL order of states the buttons have to live with:
// "created" before the worker writes anything, "paused" while the worker still writes its last files, and the old
// "paused" status that stays on disk for 2-3 s after a Resume while the new worker imports.
// It writes runs, so it REFUSES the default backend: give it a SCRATCH backend and a scratch output root, e.g.
//   S=<empty scratch dir>; mkdir -p $S/settings $S/out
//   GATOR_WORKBENCH_SETTINGS_DIR=$S/settings PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8769 --allow-root $S/out &
//   WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT GATOR_WORKBENCH_URL=http://127.0.0.1:8769/ GATOR_SCRATCH_OUT=$S/out \
//     "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/run_control_live_check.mjs)" [screenshot-dir]
// (WSLENV carries the two variables into the Windows process.) Takes about 90 s. Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9384, APP = process.env.GATOR_WORKBENCH_URL, OUT_ROOT = process.env.GATOR_SCRATCH_OUT;
if (!APP || !OUT_ROOT || new URL(APP).port === '8765') {
  console.log('ERROR this check starts real (MOCK) runs: set GATOR_WORKBENCH_URL to a SCRATCH backend (not port 8765) and GATOR_SCRATCH_OUT to its allowed output root.');
  process.exit(1);
}
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-runlive-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };
const get = async (route, params) => (await fetch(new URL(`api/${route}?` + new URLSearchParams(params), APP))).json();

try {
  const starter = await get('tasks/starter', { task_key: 'synthetic:opamp' });
  // A budget the run cannot reach during the check, so that every ending below is the button's doing.
  const CONFIG = { ...starter, run: { ...starter.run, max_evaluations: 20000, concurrency: 1 }, output: { experiment_name: 'run_control_live', output_root: OUT_ROOT }, research: {} };
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const dialogs = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Page.javascriptDialogOpening') { dialogs.push(m.params.message); send('Page.handleJavaScriptDialog', { accept: true }).catch(() => undefined); }
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 80) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const MAIN = `document.querySelector('header button.run-main')`, ABORT = `document.querySelector('header button.run-abort')`, CHIP = `document.querySelector('header button.run-chip')`;
  const mainReads = (label, tries = 300) => until(`${MAIN}?.textContent === ${JSON.stringify(label)} && !${MAIN}.disabled`, tries);
  const press = expression => evaluate(`${expression}.click()`);
  const labels = async () => (await evaluate(`window.__seen ?? []`)).map(s => s[0]);
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = document.querySelector('header').getBoundingClientRect(); return { x: 0, y: 0, width: 1680, height: Math.min(1050, r.bottom + 60), scale: 1 }; })()`);
    writeFileSync(path.join(out, name), Buffer.from((await send('Page.captureScreenshot', { format: 'png', clip })).data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (location.protocol.startsWith('http')) {
    if (!sessionStorage.getItem('fixture-seeded')) { sessionStorage.setItem('fixture-seeded', '1'); localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))}); }
    window.__seen = [];
    new MutationObserver(() => { const b = document.querySelector('header button.run-main'); if (!b) return; const now = [b.textContent, b.disabled];
      const last = window.__seen[window.__seen.length - 1]; if (!last || last[0] !== now[0] || last[1] !== now[1]) window.__seen.push(now); })
      .observe(document, { subtree: true, childList: true, characterData: true, attributes: true }); }` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${MAIN})`, 150))) throw new Error('the run buttons never appeared: ' + consoleErrors.join(' | ').slice(0, 300));
  check('the real validation lets the MOCK starter configuration start', await until(`${MAIN}.textContent === 'Start' && !${MAIN}.disabled && [...document.querySelectorAll('header span.ok')].some(s => s.textContent === 'configuration valid')`, 300));

  // ---- Start ---------------------------------------------------------------------------------------------------------
  await press(MAIN);
  check('Start: a real worker is launched and the button reads "Pause"', await mainReads('Pause'));
  const dir = await evaluate(`localStorage.getItem('gator-workbench-current-run-v1')`);
  check('the run lies in the scratch output root, under mock/', typeof dir === 'string' && dir.startsWith(OUT_ROOT) && dir.includes('/mock/'), String(dir));
  check('the header follows the real run: evaluations are being charged', await until(`Number((${CHIP}?.textContent.match(/running (\\d+) \\//) ?? [])[1]) >= 5`, 600), await evaluate(`${CHIP}?.textContent`));
  await shot('live-1-running.png');

  // ---- Pause ---------------------------------------------------------------------------------------------------------
  await press(MAIN);
  check('Pause: the button reads "Pausing..." and then "Resume"', await until(`${MAIN}.textContent === 'Pausing...'`, 30) && await mainReads('Resume'));
  let status = await get('runs/status', { run_dir: dir });
  const pausedAt = status.budget?.charged;
  check('the backend says: paused, no worker, a FULL saved state', status.state === 'paused' && status.worker_alive === false && status.summary?.output?.resumability === 'full_state' && pausedAt >= 5,
    JSON.stringify({ state: status.state, alive: status.worker_alive, resumability: status.summary?.output?.resumability, charged: pausedAt }));
  check('the header says where it stands', (await evaluate(`${CHIP}.textContent`)) === `paused at ${pausedAt} / 20000 [MOCK]`, await evaluate(`${CHIP}.textContent`));
  await sleep(2500);
  check('a paused run stays paused: nothing is charged meanwhile', (await get('runs/status', { run_dir: dir })).budget?.charged === pausedAt);
  await shot('live-2-paused.png');

  // ---- Resume --------------------------------------------------------------------------------------------------------
  const before = (await labels()).length;
  await press(MAIN);
  check('Resume: the button reads "Pause" again', await mainReads('Pause'));
  check('it continues the SAME run from where it stopped', await until(`Number((${CHIP}?.textContent.match(/running (\\d+) \\//) ?? [])[1]) > ${pausedAt}`, 600)
    && (await evaluate(`localStorage.getItem('gator-workbench-current-run-v1')`)) === dir, await evaluate(`${CHIP}?.textContent`));
  const during = (await labels()).slice(before);
  check('while the new worker was starting the button never fell back to "Resume", "Pausing..." or "Start"', during.join(' > ') === 'Resuming... > Pause', during.join(' > '));
  status = await get('runs/status', { run_dir: dir });
  check('the backend says: running again, same directory, counters kept', status.state === 'running' && status.worker_alive === true && status.entry === 'resume' && status.budget.charged > pausedAt,
    JSON.stringify({ state: status.state, entry: status.entry, charged: status.budget?.charged }));

  // ---- Abort ---------------------------------------------------------------------------------------------------------
  await press(ABORT);
  check('Abort asked first', /^Abort this run\?/.test(dialogs[dialogs.length - 1] ?? ''), dialogs[dialogs.length - 1]);
  check('Abort: the run ends and the button reads "Start" again', await mainReads('Start'));
  status = await get('runs/status', { run_dir: dir });
  check('the backend says: stopped by the user, saved, no worker', status.state === 'stopped' && status.stop_reason === 'user_stop' && status.worker_alive === false
    && status.summary?.totals?.candidate_evaluations_charged === status.budget.charged, JSON.stringify({ state: status.state, reason: status.stop_reason, charged: status.budget?.charged }));
  check('the header says how it ended, Abort is disabled', /^stopped \d+ \/ 20000 \[MOCK\]$/.test(await evaluate(`${CHIP}.textContent`)) && await evaluate(`${ABORT}.disabled`), await evaluate(`${CHIP}.textContent`));
  const events = (await get('runs/logs', { run_dir: dir, kind: 'events', limit: 200 })).entries.filter(e => ['control', 'resumed', 'segment_ended'].includes(e.event)).map(e => e.event === 'control' ? e.command : e.event === 'segment_ended' ? `ended:${e.state}` : e.event);
  check('the run\'s own event log tells the same story', events.join(' > ') === 'pause > ended:paused > resumed > stop > ended:stopped', events.join(' > '));
  const story = (await labels()).join(' > ');
  check('from the first press to the last the button showed each step once, and nothing else', story === 'Start > Starting... > Pause > Pausing... > Resume > Resuming... > Pause > Aborting... > Start', story);
  await shot('live-3-stopped.png');

  // ---- Pause pressed before the worker has written anything ------------------------------------------------------------
  await press(MAIN);
  await until(`${MAIN}.textContent === 'Pause' && !${MAIN}.disabled`, 300);
  await press(MAIN);                                                             // at once: the worker is still importing
  check('a Pause pressed while the worker is still starting is not lost: "Resume"', await mainReads('Resume', 600));
  const second = await evaluate(`localStorage.getItem('gator-workbench-current-run-v1')`);
  status = await get('runs/status', { run_dir: second });
  check('that run is paused with a saved state, and it is a NEW run directory', status.state === 'paused' && second !== dir && status.summary?.output?.resumability === 'full_state',
    JSON.stringify({ state: status.state, charged: status.budget?.charged, resumability: status.summary?.output?.resumability }));
  await press(MAIN);
  check('and it resumes', await mainReads('Pause') && await until(`Number((${CHIP}?.textContent.match(/running (\\d+) \\//) ?? [])[1]) > ${status.budget?.charged ?? 0}`, 600), await evaluate(`${CHIP}?.textContent`));
  await press(ABORT);
  check('cleanup: aborted', await mainReads('Start', 600));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
  ws.close();
} catch (error) {
  failures++; console.log('ERROR ' + (error?.stack ?? error));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; the temp dir is harmless */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
