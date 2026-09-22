// Browser check of the EXPORTS of the four run tabs (Run status, Logs, Data tables, Output files): every export button
// pressed in a real (headless) browser against a real backend, and the files the browser SAVED read back from its
// download folder (there is no frontend test runner in this project). Nothing is intercepted: names and contents are
// what the real backend sends. Same approach as run_control_live_check.mjs: headless Edge over the DevTools protocol.
// What it pins (user request 2026-09-21, "close all five gaps"):
//   1 Logs: "Download full log" saves the whole events.jsonl; a log with nothing in it says so and the page stays
//   2 Run status: "Export status (JSON)" saves what the tab shows, named after the run
//   3 Data tables: "Export detailed CSV" downloads the CSV at once (whole table), and keeps the copy in the run folder
//   4 Data tables: "Export research CSVs" downloads the experiment's aggregates as one zip (they lie above the run folder)
//   5 Output files: the data-only package is named after ITS run, not "run__data.zip" for every run
// It starts one small run on the synthetic MOCK task (free, no bridge, no Virtuoso) and writes exports, so it REFUSES
// the default backend: give it a SCRATCH backend and a scratch output root, e.g.
//   S=<empty scratch dir>; mkdir -p $S/settings $S/out
//   GATOR_WORKBENCH_SETTINGS_DIR=$S/settings PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8769 --allow-root $S/out &
//   WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT GATOR_WORKBENCH_URL=http://127.0.0.1:8769/ GATOR_SCRATCH_OUT=$S/out \
//     "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/export_check.mjs)" [screenshot-dir]
// (WSLENV carries the two variables into the Windows process.) Takes about 60 s. Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9391, APP = process.env.GATOR_WORKBENCH_URL, OUT_ROOT = process.env.GATOR_SCRATCH_OUT;
if (!APP || !OUT_ROOT || new URL(APP).port === '8765') {
  console.log('ERROR this check starts a real (MOCK) run and writes exports: set GATOR_WORKBENCH_URL to a SCRATCH backend (not port 8765) and GATOR_SCRATCH_OUT to its allowed output root.');
  process.exit(1);
}
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-export-'));
const saved = mkdtempSync(path.join(tmpdir(), 'gator-cdp-export-saved-'));          // the browser's download folder
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };
const get = async (route, params) => (await fetch(new URL(`api/${route}?` + new URLSearchParams(params), APP))).json();
const post = async (route, body) => (await fetch(new URL(`api/${route}`, APP), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
// File names of a zip, from its central directory (node has no zip reader; signature PK\1\2, name length at +28, name at +46).
const zipNames = buffer => { const names = []; for (let i = buffer.indexOf('PK\u0001\u0002', 0, 'latin1'); i >= 0; i = buffer.indexOf('PK\u0001\u0002', i + 46, 'latin1')) names.push(buffer.toString('utf8', i + 46, i + 46 + buffer.readUInt16LE(i + 28))); return names; };
// A finished download: the named file is there and Edge's temporary ".crdownload" twin is gone.
const savedFile = async name => { for (let i = 0; i < 100; i++) { const names = readdirSync(saved); if (names.includes(name) && !names.some(n => n.endsWith('.crdownload'))) return readFileSync(path.join(saved, name)); await sleep(100); } return null; };

try {
  // ---- one small finished MOCK run to export from -------------------------------------------------------------------------------
  const starter = await get('tasks/starter', { task_key: 'synthetic:gpdk045_ota5' });
  const CONFIG = { ...starter, run: { ...starter.run, max_evaluations: 12, concurrency: 1 }, output: { experiment_name: 'export_check', output_root: OUT_ROOT }, research: {} };
  const started = await post('runs/start', { config: CONFIG });
  if (!started.run_dir) throw new Error('the MOCK run did not start: ' + JSON.stringify(started).slice(0, 400));
  const DIR = started.run_dir, RUN = DIR.split('/').pop(), EXPERIMENT = DIR.split('/').slice(-4)[0];
  let status;
  for (let i = 0; i < 600; i++) { status = await get('runs/status', { run_dir: DIR }); if (status.state === 'completed' && !status.worker_alive) break; await sleep(300); }
  if (status.state !== 'completed') throw new Error('the MOCK run did not complete: ' + status.state);
  console.log(`INFO  MOCK run ${RUN} of experiment ${EXPERIMENT}: ${status.budget.charged} evaluations`);

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
  };
  const evaluate = async (expression, userGesture = false) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 80) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const button = text => `[...document.querySelectorAll('footer .bottom-body button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const press = text => evaluate(`${button(text)}.click()`, true);                                       // a real click: downloads need the user's gesture
  const tab = async text => { await evaluate(`[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`); return until(`!!(${button(text === 'Run status' ? 'Export status (JSON)' : 'Refresh')}) || ${JSON.stringify(text)} === 'Logs'`, 60); };
  // The Agent tab stays mounted (hidden) in the same container, so everything is found from the visible tab's own button.
  const HINT = text => `(${button(text)}?.closest('.row').querySelector('.hint')?.textContent ?? '')`;
  let row = 'Export status (JSON)';                                                                        // the button whose row the note is read from
  const hint = () => evaluate(HINT(row));
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = document.querySelector('footer').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, scale: 1 }; })()`);
    writeFileSync(path.join(out, name), Buffer.from((await send('Page.captureScreenshot', { format: 'png', clip })).data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: saved });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (location.protocol.startsWith('http') && !sessionStorage.getItem('fixture-seeded')) { sessionStorage.setItem('fixture-seeded', '1');
    localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))}); localStorage.setItem('gator-workbench-current-run-v1', ${JSON.stringify(DIR)}); }` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!document.querySelector('footer .tabs')`, 150))) throw new Error('the workbench never appeared; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));

  // ---- 2 Run status: what the tab shows, as one JSON file named after the run --------------------------------------------------------------
  await tab('Run status');
  if (!(await until(`!!(${button('Export status (JSON)')})`, 60))) throw new Error('this page has no "Export status (JSON)" button: the served frontend is older than it (npm run build, then reload)');
  check('Run status has "Export status (JSON)" at the end of its button row', await evaluate(`${button('Export status (JSON)')}.previousElementSibling?.textContent === 'Continue'`));
  await press('Export status (JSON)');
  let file = await savedFile(`${RUN}__status.json`);
  const exported = file && JSON.parse(file.toString('utf8'));
  check('it saves <run folder>__status.json', !!file, readdirSync(saved).join(', '));
  check('... holding the state, budget, manifest and summary the tab shows, and when it was exported', exported?.state === 'completed' && exported.run_dir === DIR && exported.budget?.charged === status.budget.charged
    && !!exported.manifest && !!exported.summary && /^20\d\d-/.test(exported.exported_utc ?? ''), JSON.stringify(Object.keys(exported ?? {})).slice(0, 200));
  await shot('export-1-status.png');

  // ---- 1 Logs: the whole file, not the newest 200 entries --------------------------------------------------------------------------------------
  await tab('Logs'); row = 'Download full log (events.jsonl)';
  check('Logs has "Download full log (events.jsonl)" next to the list', await until(`!!(${button('Download full log (events.jsonl)')})`, 60));
  check('... and says that the list is only the newest entries', /newest 200 entries/.test(await hint()), await hint());
  await press('Download full log (events.jsonl)');
  file = await savedFile('events.jsonl');
  const lines = file ? file.toString('utf8').split('\n').filter(Boolean) : [];
  const listed = (await get('runs/logs', { run_dir: DIR, kind: 'events', limit: 1000 })).entries;
  check('it saves events.jsonl with every record of the run, one JSON object per line', lines.length > 0 && lines.length === listed.length && lines.every(l => { try { return !!JSON.parse(l).event; } catch { return false; } }), `${lines.length} lines, ${listed.length} entries`);
  check('... and says so', await until(`${HINT(row)} === 'Downloaded events.jsonl.'`, 40), await hint());
  await evaluate(`(() => { const s = [...document.querySelectorAll('footer .bottom-body select')].find(e => [...e.options].some(o => o.value === 'errors')); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, 'errors'); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  row = 'Download full log (errors.jsonl)';
  check('choosing "errors" renames the button and clears the note', await until(`!!(${button(row)})`, 40) && /newest 200 entries/.test(await hint()), await hint());
  const hasErrors = (await get('runs/logs', { run_dir: DIR, kind: 'errors' })).entries.length > 0;      // a healthy run keeps an EMPTY errors.jsonl
  await until(`document.querySelectorAll('footer .bottom-body .scroll.log > div').length === 0`, 40);      // the list now shows the errors log
  await press('Download full log (errors.jsonl)');
  if (hasErrors) check('the errors log is saved too', !!(await savedFile('errors.jsonl')));
  else {
    check('a log with nothing in it is said in plain words, not saved as an empty file', await until(`${HINT(row)} === 'Nothing to download: this run has logged no errors so far.'`, 40), await hint());
    check('... the page stays the workbench, and nothing is saved', await evaluate(`location.pathname === '/' && !!document.querySelector('header')`) && !existsSync(path.join(saved, 'errors.jsonl')));
  }
  await shot('export-2-logs.png');

  // ---- 3 + 4 Data tables: the CSV comes to the browser; so do the research CSVs, as one zip ------------------------------------------------------
  await tab('Data tables'); row = 'Refresh';
  check('Data tables shows the run\'s evaluations', await until(`/^${status.budget.charged} rows/.test${HINT(row)}`, 80), await hint());
  await press('Export detailed CSV');
  check('"Export detailed CSV" says what was downloaded and where the copy is kept', await until(`/Downloaded evaluations__seq\\d+\\.csv\\. Also kept in the run folder: exports\\/evaluations__seq\\d+\\.csv/.test${HINT(row)}`, 100), await hint());
  const csvName = /Downloaded (evaluations__seq\d+\.csv)/.exec(await hint())?.[1] ?? 'missing';
  file = await savedFile(csvName);
  const rows = file ? file.toString('utf8').trimEnd().split('\n') : [];
  check('the browser saved the WHOLE table (header + every row, not only the rows shown)', rows.length === status.budget.charged + 1 && rows[0].split(',').includes('evaluation_id'), `${rows.length} lines; header ${rows[0]?.slice(0, 80)}`);
  check('... and the copy is in the run folder as well', (await get('runs/files', { run_dir: DIR })).files.some(f => f.path === `exports/${csvName}`));
  await press('Export research CSVs');
  check('"Export research CSVs" says what was downloaded and where the copies are kept', await until(`${HINT(row)}.includes('Downloaded ${EXPERIMENT}__aggregates.zip (6 tables). Also kept in ')`, 150), await hint());
  file = await savedFile(`${EXPERIMENT}__aggregates.zip`);
  const research = file ? zipNames(file).sort() : [];
  check('the browser saved <experiment>__aggregates.zip with the six tables and their descriptions', research.length === 12
    && ['run_summary', 'budget_success', 'budget_success_grouped', 'paired_runs', 'transfer_summary', 'cumulative_cost'].every(t => research.includes(`${t}.csv`) && research.includes(`${t}.meta.json`)), research.join(', '));
  await shot('export-3-data.png');

  // ---- 5 Output files: the package is named after its run ---------------------------------------------------------------------------------------------
  await tab('Output files'); row = 'Refresh';
  check('Output files lists the exported CSV, downloadable like every other file', await until(`[...document.querySelectorAll('footer .bottom-body td')].some(td => td.textContent === 'exports/${csvName}')`, 80));
  await press('Download data-only package (.zip)');
  file = await savedFile(`${RUN}__data.zip`);
  const packed = file ? zipNames(file) : [];
  check('the data-only package is saved as <run folder>__data.zip, not as run__data.zip', !!file && !existsSync(path.join(saved, 'run__data.zip')), readdirSync(saved).join(', '));
  check('... with the run\'s data and without models or work files', packed.includes('run_summary.json') && packed.includes('logs/events.jsonl') && packed.some(n => n.endsWith('.parquet'))
    && !packed.some(n => /^(work|control|waveforms|checkpoints)\//.test(n)), `${packed.length} members`);
  check('... and the tab says so', await until(`${HINT(row)}.includes('Downloaded ${RUN}__data.zip.')`, 60), await hint());
  await shot('export-4-files.png');

  console.log(`INFO  saved by the browser: ${readdirSync(saved).join(', ')}`);
  check('no dialog was needed', dialogs.length === 0, dialogs.join(' | ').slice(0, 200));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  console.log(failures ? `\n${failures} check(s) FAILED` : '\nall checks passed');
  ws.close();
} catch (error) {
  failures++; console.log(`FAIL  the check could not run: ${error.message}`);
} finally {
  edge.kill();
  await sleep(500);
  for (const dir of [profile, saved]) try { rmSync(dir, { recursive: true, force: true }); } catch { /* Edge may still hold a file; it is a temp dir */ }
}
process.exit(failures ? 1 : 0);
