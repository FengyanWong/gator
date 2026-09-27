// LIVE companion of run_control_check.mjs: the header's Start -> Pause -> Resume -> Abort pressed in a real (headless)
// browser against a real backend with a real detached worker - on the synthetic MOCK task only (free, no bridge, no
// Virtuoso). Nothing is intercepted, so what is checked is the REAL order of states the buttons have to live with:
// "created" before the worker writes anything, "paused" while the worker still writes its last files, and the old
// "paused" status that stays on disk for 2-3 s after a Resume while the new worker imports.
// It writes runs, so it REFUSES the default backend: give it a SCRATCH backend and a scratch output root, e.g.
//   S=<empty scratch dir>; mkdir -p $S/settings $S/out
//   GATOR_WORKBENCH_SETTINGS_DIR=$S/settings PYTHONPATH=src ~/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8769 --allow-root $S/out &
//   WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT GATOR_WORKBENCH_URL=http://127.0.0.1:8769/ GATOR_SCRATCH_OUT=$S/out \
//     "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/run_control_live_check.mjs)" [screenshot-dir]
// (WSLENV carries the two variables into the Windows process.) Takes about 90 s. Exit code 1 if any check fails.
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl({ writes: true }), OUT_ROOT = process.env.GATOR_SCRATCH_OUT;
if (!OUT_ROOT) {
  console.log('ERROR this check starts real (MOCK) runs: set GATOR_SCRATCH_OUT to the allowed output root of the scratch backend (and WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT).');
  process.exit(1);
}
const out = outDir();
const browser = await launchEdge('runlive');
const get = async (route, params) => (await fetch(new URL(`api/${route}?` + new URLSearchParams(params), APP))).json();

try {
  const starter = await get('tasks/starter', { task_key: 'synthetic:gpdk045_ota5' });
  // A budget the run cannot reach during the check, so that every ending below is the button's doing.
  const CONFIG = { ...starter, run: { ...starter.run, max_evaluations: 20000, concurrency: 1 }, output: { experiment_name: 'run_control_live', output_root: OUT_ROOT }, research: {} };
  const page = await browser.open();
  const { send, evaluate, until, consoleErrors } = page;
  const dialogs = [];
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const MAIN = `document.querySelector('header button.run-main')`, ABORT = `document.querySelector('header button.run-abort')`, CHIP = `document.querySelector('header button.run-chip')`;
  const mainReads = (label, tries = 300) => until(`${MAIN}?.textContent === ${JSON.stringify(label)} && !${MAIN}.disabled`, tries);
  const press = expression => evaluate(`${expression}.click()`);
  const labels = async () => (await evaluate(`window.__seen ?? []`)).map(s => s[0]);
  const shot = async name => page.shot(path.join(out, name),
    await evaluate(`(() => { const r = document.querySelector('header').getBoundingClientRect(); return { x: 0, y: 0, width: 1680, height: Math.min(1050, r.bottom + 60), scale: 1 }; })()`));

  // Every [label, disabled] the main button shows on the page is recorded in window.__seen.
  await page.seed({ config: CONFIG, when: 'once', also: `window.__seen = [];
    new MutationObserver(() => { const b = document.querySelector('header button.run-main'); if (!b) return; const now = [b.textContent, b.disabled];
      const last = window.__seen[window.__seen.length - 1]; if (!last || last[0] !== now[0] || last[1] !== now[1]) window.__seen.push(now); })
      .observe(document, { subtree: true, childList: true, characterData: true, attributes: true });` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${MAIN})`, 150))) throw new Error('the run buttons never appeared: ' + consoleErrors.join(' | ').slice(0, 300));
  check('the real validation lets the MOCK starter configuration start', await until(`${MAIN}.textContent === 'Start' && !${MAIN}.disabled && [...document.querySelectorAll('header span.ok')].some(s => s.textContent === 'configuration valid')`, 300));

  // ---- Start ---------------------------------------------------------------------------------------------------------
  // The story starts with the first press; loading and validation may change Start's disabled state before it.
  await evaluate(`window.__seen = [[${MAIN}.textContent, ${MAIN}.disabled]]`);
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
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
