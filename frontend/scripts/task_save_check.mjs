// Browser check of saved tasks in the Project panel (TaskSave.tsx, TaskFile.tsx): an open task's "Save task" (next revision),
// "Save as" (another task) and the task file in a window of its own. Same approach as working_copy_check.mjs: a throwaway
// headless Edge over the DevTools protocol against a workbench page (default http://127.0.0.1:8765/; GATOR_WORKBENCH_URL for
// a preview of a temporary build). EVERY /api/virtuoso/* request, the circuit load and the task list of the open task are
// answered with canned FIXTURES, so Virtuoso is never contacted and nothing is saved anywhere. What it pins (user request
// 2026-09-22, "go on part 2"):
//   - an open task names itself and its revision; three short buttons: Save task, Save as, Task file;
//   - "Task file" opens a window with the task as one readable file (its _help included); "Apply to editors" checks it and
//     fills the editors (one Undo step); a broken file is refused with its problems and changes nothing;
//   - "Save task" sends the rows, the task and what the file added (analyses) and reports the revision and the baseline;
//   - "Save as" asks for a new name beside the button, sends as_new and opens the new task; nothing happens on load.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/task_save_check.mjs)" [screenshot-dir]
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9397, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-task-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0; const consoleErrors = [];
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const ROWS = [{ variable_id: 'wn', instance_path: 'XU1/MN1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005 }];
const PROBES = [{ measurement_id: 'm_osc_frequency_hz', analysis: 'tran', result_source: 'backend_profile', source_name: 'osc_frequency_hz', unit: 'Hz' }];
const SPECS = [{ metric_id: 'osc_frequency_hz', equation: 'm_osc_frequency_hz', unit: 'Hz', constraint: '>=', lower: 1.1e9, normalization_scale: 1e9 }];
const tasksKnown = new Set(['real:ring_osc']);
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: true, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { MN1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: ['FIXTURE: a saved task.'] });
const fileText = (task, rows) => JSON.stringify({ _help: { 'what this is': 'The task file: everything this task is, in one place.' }, format: 'gator-task-1', name: task,
  revision: 1, cell: { library: 'GPDK045_RINGOSC', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' },
  copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' },
  measurement: { kind: 'ring_oscillator', expected_frequency_hz: 1.2e9 }, maestro: { analyses: {}, variables: {}, bindings: [], model_files: [] },
  parameters: rows.parameters, probes: rows.measurements, specs: rows.targets, notes: '' }, null, 2);

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const calls = []; const dialogs = []; const answers = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = async ({ requestId, request }) => {
    const url = new URL(request.url), pathname = url.pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/tasks') {
      const real = await (await fetch(new URL('api/tasks', APP))).json();
      return fulfil(requestId, 200, { ...real, tasks: [...real.tasks, ...[...tasksKnown].map(key => ({ task_key: key, kind: 'real', available: true, generated: true,
        revision: key === 'real:ring_osc' ? revision : 1, circuit_class: 'vco', pdk_id: 'gpdk045' }))] });
    }
    if (pathname === '/api/tasks/starter' && tasksKnown.has(url.searchParams.get('task_key'))) {
      return fulfil(requestId, 200, { project: { name: 'fixture', task_name: 'ring' }, circuit: { source: 'registered_task', task_id: url.searchParams.get('task_key') },
        parameters: ROWS, measurements: PROBES, targets: SPECS });
    }
    if (pathname === '/api/circuit/load') {
      const circuit = body.circuit ?? {};
      return circuit.source === 'registered_task' && tasksKnown.has(circuit.task_id) ? fulfil(requestId, 200, generated(circuit.task_id)) : send('Fetch.continueRequest', { requestId });
    }
    if (!pathname.startsWith('/api/virtuoso/')) return send('Fetch.continueRequest', { requestId });
    const op = pathname.replace('/api/virtuoso/', '');
    calls.push({ op, ...body });
    await sleep(120);
    if (op === 'task/file') return fulfil(requestId, 200, { text: fileText(body.task, body.config), name: body.task, revision, saved: true });
    if (op === 'task/file/check') {
      let data; try { data = JSON.parse(body.text); } catch (e) { return fulfil(requestId, 200, { ok: false, problems: ['Not valid JSON: FIXTURE'], rows: {}, extras: {} }); }
      const bad = (data.probes ?? []).some(p => p.analysis === 'sometimes');
      return fulfil(requestId, 200, bad ? { ok: false, problems: ['probes[0] analysis: Input should be \'dc\', \'ac\', \'tran\' ... (FIXTURE)'], rows: {}, extras: {} }
        : { ok: true, problems: [], rows: { parameters: data.parameters, measurements: data.probes, targets: data.specs }, extras: { analyses: data.maestro?.analyses ?? {}, notes: data.notes } });
    }
    if (op === 'task/save') {
      if (body.as_new) { tasksKnown.add(`real:${body.name}`); return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, revision: 1, created: true, runnable: true,
        circuit_class: 'vco', pdk_id: 'gpdk045', parameters: ROWS, baseline_kept: false, changed: [], copy: { library: 'GPDK045_RINGOSC_GATOR', cell: `ring_osc_3stage_${body.name}`, testbench: `tb_ring_osc_3stage_${body.name}` } }); }
      revision += 1;
      return fulfil(requestId, 200, { task_key: `real:${body.task}`, name: body.task, revision, created: false, runnable: true, circuit_class: 'vco', pdk_id: 'gpdk045',
        parameters: ROWS, baseline_kept: false, changed: ['parameters', 'specs'], copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' } });
    }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
  let revision = 1;
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* page went away */ });
    else if (m.method === 'Page.javascriptDialogOpening') {
      const accept = answers.length ? answers.shift() : null;
      dialogs.push({ message: m.params.message, planned: accept !== null });
      send('Page.handleJavaScriptDialog', { accept: !!accept }).catch(() => undefined);
    }
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async (expression, userGesture = false) => {          // userGesture: a click that may open a window
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Circuit source'))`;
  const BLOCK = `${PANEL}?.querySelector('.task-save')`;
  const BUTTON = text => `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const blockText = () => evaluate(`${BLOCK}?.textContent ?? ''`);
  const press = (label, gesture = false) => evaluate(`${BUTTON(label)}.click()`, gesture);
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')`);
  const POPUP = `window.open('', 'gator-task-file')`;                             // the same name returns the open window, unchanged
  const popupEval = body => evaluate(`(() => { const w = ${POPUP}; const d = w.document; ${body} })()`, true);
  const typeInto = async (selector, text) => evaluate(`(() => { const el = ${selector};
    Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`, true);
  const settle = (ms = 900) => sleep(ms);

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: ['*/api/virtuoso/*', '*/api/circuit/load', '*/api/tasks', '*/api/tasks/starter*'].map(urlPattern => ({ urlPattern, requestStage: 'Request' })) });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  for (let i = 0; i < 50 && !(await stored()); i++) await sleep(100);
  const start = await stored();
  const seeded = { ...start, circuit: { ...start.circuit, source: 'registered_task', task_id: 'real:ring_osc', circuit_class: 'vco', pdk_id: 'gpdk045' },
    parameters: ROWS, measurements: PROBES, targets: SPECS };
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(seeded))})`);
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${BLOCK})`)); i++) await sleep(100);
  await settle(1500);
  check('nothing is saved or read from Virtuoso on load', calls.length === 0, calls.map(c => c.op).join(' | '));
  check('the open task names itself and its revision', (await blockText()).includes('Task real:ring_osc, revision 1.'), await blockText());
  check('three short buttons: Save task, Save as, Task file', await evaluate(`!!(${BUTTON('Save task')}) && !!(${BUTTON('Save as')}) && !!(${BUTTON('Task file')})`));
  check('only a person can press it, said beside the buttons', (await blockText()).includes('Only you can press it.'));

  // ---- the task file in a window of its own ---------------------------------------------------------------------------------------
  await press('Task file', true); await settle(1500);
  check('"Task file" asks for the file of the current editors, once', calls.map(c => c.op).join() === 'task/file' && calls[0].task === 'ring_osc'
    && Array.isArray(calls[0].config?.targets), JSON.stringify(calls));
  const opened = await popupEval(`return d.querySelector('.task-file textarea')?.value ?? ''`);
  check('it opens in its own window, as one readable file with its _help', opened.includes('"_help"') && opened.includes('"specs"') && opened.includes('GPDK045_RINGOSC_GATOR'), opened.slice(0, 80));
  const edited = JSON.parse(opened);
  edited.specs[0].lower = 1.25e9; edited.maestro.analyses = { tran: { stop: '40n' } }; edited.notes = 'tighter';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(edited, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await settle();
  let config = await stored();
  for (let i = 0; i < 30 && config.targets[0].lower !== 1.25e9; i++) { await sleep(100); config = await stored(); }   // the page stores a moment later
  check('"Apply to editors" checks the file and fills the editors', calls.at(-1).op === 'task/file/check' && config.targets[0].lower === 1.25e9, JSON.stringify(config.targets));
  check('the window says what happened and that nothing is saved yet', (await popupEval(`return d.querySelector('.task-file').textContent`)).includes('Press "Save task" to store them'));
  edited.probes[0].analysis = 'sometimes';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(edited, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await settle();
  config = await stored();
  check('a broken file is refused with its problems and changes nothing', (await popupEval(`return d.querySelector('.task-file .blocker')?.textContent ?? ''`)).includes('probes[0] analysis')
    && config.measurements[0].analysis === 'tran', config.measurements[0].analysis);
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);

  // ---- Save task: the next revision of the same task --------------------------------------------------------------------------------
  let mark = calls.length;
  await press('Save task'); await settle(1500);
  const saveCall = calls.slice(mark).find(c => c.op === 'task/save');
  check('Save task sends the rows, the open task and what the file added', !!saveCall && saveCall.task === 'ring_osc' && saveCall.name === 'ring_osc' && !saveCall.as_new
    && saveCall.extras?.analyses?.tran?.stop === '40n' && saveCall.config?.targets?.[0]?.lower === 1.25e9, JSON.stringify(saveCall ?? calls.slice(mark)));
  check('it reports the revision and that the baseline no longer holds', (await blockText()).includes('Saved real:ring_osc, revision 2.') && (await blockText()).includes('no longer holds'), await blockText());
  await sleep(500);
  check('the open task shows its new revision', (await blockText()).includes('revision 2'), await blockText());

  // ---- Save as: another task, a name beside the button -----------------------------------------------------------------------------
  await press('Save as'); await settle(400);
  check('Save as asks for the new name beside the button', await evaluate(`[...${BLOCK}.querySelectorAll('label')].some(l => l.firstChild?.textContent.trim() === 'New task name')`));
  check('the same name cannot be saved as', await evaluate(`[...${BLOCK}.querySelectorAll('button')].filter(b => b.textContent.trim() === 'Save as').at(-1).disabled`));
  await typeInto(`[...${BLOCK}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'New task name').querySelector('input')`, 'ring_fast'); await sleep(200);
  mark = calls.length;
  await evaluate(`[...${BLOCK}.querySelectorAll('button')].filter(b => b.textContent.trim() === 'Save as').at(-1).click()`); await settle(1800);
  const asCall = calls.slice(mark).find(c => c.op === 'task/save');
  check('Save as sends as_new with the new name and the open task', !!asCall && asCall.as_new === true && asCall.name === 'ring_fast' && asCall.task === 'ring_osc', JSON.stringify(asCall ?? calls.slice(mark)));
  config = await stored();
  check('the new task is opened', config.circuit.task_id === 'real:ring_fast', config.circuit.task_id);
  check('the panel says the new task was saved and on which copy', (await evaluate(`${PANEL}.textContent`)).includes('Saved the new task real:ring_fast') &&
    (await evaluate(`${PANEL}.textContent`)).includes('tb_ring_osc_3stage_ring_fast'));
  check('no unplanned dialog', dialogs.every(d => d.planned), JSON.stringify(dialogs));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(path.join(out, 'task-save-1.png'), Buffer.from(data, 'base64'));
  ws.close();
} catch (error) {
  failures++;
  console.log('FAIL  the check itself stopped: ' + (error?.stack ?? error));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file */ }
  console.log(failures ? `\n${failures} check(s) FAILED` : '\nall checks passed');
  process.exit(failures ? 1 : 0);
}
