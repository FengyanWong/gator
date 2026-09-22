// Browser check of the agent's whole Virtuoso setup (request kind `virtuoso_setup`): "Ask the agent to set up" in the note of a
// cell read from Virtuoso, the proposal box showing the Maestro setup of the working copy, and "Approve, apply and write the
// copy". Same approach as agent_tab_check.mjs / working_copy_check.mjs: a throwaway headless Edge over the DevTools protocol
// against a workbench page (GATOR_WORKBENCH_URL for a preview of a temporary build). /api/agent/propose|approve|apply,
// /api/circuit/load and /api/virtuoso/* are answered with canned FIXTURES - no agent CLI, no Virtuoso; every other request
// that is not a read is refused here, so nothing is saved or written on the backend it runs against. What it pins (user
// request 2026-09-22, "go on part 3"):
//   - the button waits for the working copy, then opens the Agent tab with the request written out (kind virtuoso_setup) and
//     sends nothing by itself;
//   - the proposal shows its rows and the Maestro setup (analyses, variables, bindings) with where it will be written;
//   - approving says what happened in Virtuoso: written and read back, or rows applied and the copy not reachable;
//   - what the agent wrote into the copy wins over the same parts a task file set on the page earlier: Save task sends
//     them no more (it takes them from the copy); a failed write hands the approved setup to Save task instead (it writes
//     the copy later - "Write to Virtuoso" is gone, 2026-09-22). Save task sits in the editors' tab line.
// Run (Windows node sees a WSL variable only when WSLENV names it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/agent_setup_check.mjs)"
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9398, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-setup-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-extensions', '--disable-sync', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0; const consoleErrors = [];
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

const LIB = 'GPDK045_RINGOSC', CELL = 'ring_osc_3stage', TB = 'tb_ring_osc_3stage', COPY = 'GPDK045_RINGOSC_GATOR';
let withCopy = false, applyOutcome = 'written';
const draft = () => ({ loaded: true, task_key: `virtuoso:${LIB}/${CELL}`, mock: false, native_draft: true, complete: true, diagnostics: [], profile_task: null, profile_task_generated: null, profile_recipes: [],
  working_copy: withCopy ? { verified: true, problems: [], copy: { library: COPY, cell: CELL, testbench: TB }, original: { library: LIB, cell: CELL, testbench: TB } } : null,
  circuit: { library: LIB, cell: CELL, native_draft: true, testbench_cell: TB }, hierarchy: { XU1: { MN1: {} }, V0: {} }, analysis_context: null,
  evaluation_backend: null, max_concurrency: 1, testbench_probes: null,
  summary: { device_count: 2, unknown_devices: [], devices: [{ instance_path: 'XU1/MN1', kind: 'nmos', parameters: { w: { value: 1e-6 } } }] }, notes: [] });
const PROBES = [{ measurement_id: 'm_freq', analysis: 'tran', result_source: 'ade_output', source_name: 'freq', signal: 'frequency(VT("/OUT"))', unit: 'Hz' }];
const PROPOSAL = { proposal_id: 'setup-1', proposal_hash: 'fixture', origin: 'fixture', kind: 'virtuoso_setup',
  reasoning: 'A three-stage ring oscillator: three inverters in a loop, the frequency set by their delay.', warnings: [], unresolved: ['No power limit was given.'],
  diff: [{ section: 'measurements', key: 'm_freq', change: 'added', fields: [{ field: 'signal', before: null, after: 'frequency(VT("/OUT"))' }] }],
  circuit_changes: [], patch: [{ op: 'add', section: 'measurements', key: 'm_freq', value: PROBES[0] }],
  setup: { analyses: { tran: { stop: '50n', errpreset: 'conservative' } }, variables: { VSUP: '1.0' }, bindings: [{ cell: TB, instance: 'V0', parameter: 'vdc', variable: 'VSUP' }] },
  virtuoso_copy: { library: COPY, cell: CELL, testbench: TB } };

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const calls = []; const refused = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = async ({ requestId, request }) => {
    const pathname = new URL(request.url).pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/circuit/load') return body.circuit?.source === 'virtuoso' ? fulfil(requestId, 200, draft()) : send('Fetch.continueRequest', { requestId });
    const read = request.method === 'GET' || pathname === '/api/config/validate' || (pathname === '/api/output/check' && !body.create);
    if (!pathname.startsWith('/api/virtuoso/') && !pathname.startsWith('/api/agent/') || pathname.startsWith('/api/agent/') && request.method === 'GET') {
      if (read) return send('Fetch.continueRequest', { requestId });           // reads pass (the agent settings too); nothing else reaches the backend
      refused.push(`${request.method} ${pathname}`);
      return fulfil(requestId, 418, { detail: { message: 'FIXTURE: this check lets no writing request through' } });
    }
    calls.push({ path: pathname, ...body });
    if (pathname === '/api/virtuoso/libraries') return fulfil(requestId, 200, { libraries: [LIB] });
    if (pathname === '/api/virtuoso/cells') return fulfil(requestId, 200, { library: LIB, truncated: false, technology_library: 'gpdk045',
      cells: [{ name: CELL, views: ['schematic', 'symbol'], has_schematic: true }, { name: TB, views: ['schematic'], has_schematic: true }] });
    if (pathname === '/api/virtuoso/read') return fulfil(requestId, 200, { source: 'virtuoso', library: LIB, cell: body.cell, origin: 'FIXTURE', instance_count: 1, nets: ['OUT'],
      instances: [], requires_confirmation: [], note: 'FIXTURE' });
    if (pathname === '/api/virtuoso/task/file') return fulfil(requestId, 200, { text: '{"format": "gator-task-1", "FIXTURE": true}', saved: false });
    if (pathname === '/api/virtuoso/task/file/check') return fulfil(requestId, 200, { ok: true, problems: [], rows: {},
      extras: { analyses: { tran: { stop: '99n' } }, expected_frequency_hz: 1.2e9 } });
    if (pathname === '/api/virtuoso/task/save') return fulfil(requestId, 409, { detail: { code: 'refused', message: 'FIXTURE: nothing is saved by this check' } });
    if (pathname === '/api/agent/propose') { await sleep(300); return fulfil(requestId, 200, PROPOSAL); }
    if (pathname === '/api/agent/approve') return fulfil(requestId, 200, { ...PROPOSAL, status: 'approved' });
    if (pathname === '/api/agent/apply') {
      const config = { ...body.config, measurements: PROBES };
      return fulfil(requestId, 200, applyOutcome === 'written'
        ? { config, validation: {}, virtuoso: { written: true, matches: true, differences: [], copy: PROPOSAL.virtuoso_copy },
          note: `The rows were applied and the setup was written into the working copy ${COPY}/${TB} (not your cell), then read back: it matches. No simulation was started.` }
        : { config, validation: {}, virtuoso: { written: false, error: 'The connection gate blocked writing the Maestro setup' },
          note: 'The rows were applied; writing into the working copy failed: The connection gate blocked writing the Maestro setup Once Virtuoso can be reached, press Save task: it writes the rows and the approved setup into the copy.' });
    }
    refused.push(`${request.method} ${pathname}`);
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${pathname} is not expected` } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* page went away */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async (expression, userGesture = false) => {          // userGesture: a click that may open a window
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Circuit source'))`;
  const ASK = `[...(${PANEL}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === 'Ask the agent to set up')`;
  const BOX = `document.querySelector('.compose-main textarea')`;
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')`);
  const SAVE_BUTTON = text => `[...document.querySelectorAll('.editors .tabs .task-save button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const POPUP = `window.open('', 'gator-task-file')`;                         // the same name returns the open window, unchanged
  const popupEval = body => evaluate(`(() => { const w = ${POPUP}; const d = w.document; ${body} })()`, true);
  const applyTaskFile = async () => {                                         // the file sets analyses on the page (TaskSave's extras)
    await evaluate(`${SAVE_BUTTON('Task file')}.click()`, true); await sleep(900);
    await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await sleep(900);
    const said = await popupEval(`return d.querySelector('.task-file')?.textContent ?? ''`);
    await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await sleep(600);
    return said;
  };
  const saveTask = async () => {                                              // the body Save task sends (answered: refused)
    const mark = calls.length;
    await evaluate(`${SAVE_BUTTON('Save task')}.click()`); await sleep(900);
    return calls.slice(mark).find(c => c.path === '/api/virtuoso/task/save');
  };
  const chatText = () => evaluate(`document.querySelector('.chat')?.textContent ?? ''`);

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  for (let i = 0; i < 50 && !(await stored()); i++) await sleep(100);
  const start = await stored();
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify({ ...start,
    circuit: { ...start.circuit, source: 'virtuoso', task_id: null, library: LIB, cell: CELL, view: 'schematic', testbench_cell: TB, pdk_id: 'gpdk045' }, measurements: [], targets: [] }))})`);
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${ASK})`)); i++) await sleep(100);
  await sleep(1200);
  if (!(await evaluate(`!!(${ASK})`))) console.log('DEBUG panel: ' + (await evaluate(`${PANEL}?.textContent.slice(0, 900) ?? 'no panel'`))
    + '\nDEBUG stored circuit: ' + JSON.stringify((await stored())?.circuit) + '\nDEBUG errors: ' + consoleErrors.join(' | ').slice(0, 1500)
    + '\nDEBUG buttons: ' + (await evaluate(`[...(${PANEL}?.querySelectorAll('button') ?? [])].map(b => JSON.stringify(b.textContent)).join(' ')`)));
  check('without a working copy the button waits and says why', await evaluate(`${ASK}.disabled && ${ASK}.title.includes('Make the working copy first')`));
  withCopy = true;
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${ASK}) && !${ASK}.disabled`)); i++) await sleep(100);
  await sleep(800);
  check('with the working copy it can be pressed; nothing was asked of the agent on load', !(await evaluate(`${ASK}.disabled`)) && !calls.some(c => c.path.startsWith('/api/agent/')));
  check('a task file applied on the page sets analyses for the next Save task', (await applyTaskFile()).includes('Applied'));
  await evaluate(`${ASK}.click()`); await sleep(900);
  const box = await evaluate(`${BOX}?.value ?? ''`);
  check('it opens the Agent tab with the request written out, sending nothing', box.includes('set it up for optimization in its working copy') && !calls.some(c => c.path === '/api/agent/propose'), box.slice(0, 90));
  check('the request kind is virtuoso_setup', (await evaluate(`[...document.querySelectorAll('.compose-main select')].map(s => s.value).includes('virtuoso_setup')`)));
  await evaluate(`(() => { const b = ${BOX}; b.focus(); b.setSelectionRange(b.value.length, b.value.length); })()`);
  await send('Input.insertText', { text: 'More than 1.1 GHz (my spec sheet).' });
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  for (let i = 0; i < 40 && !(await evaluate(`!!document.querySelector('.setup-proposal')`)); i++) await sleep(150);
  const sent = calls.find(c => c.path === '/api/agent/propose');
  check('Enter sends one virtuoso_setup request with the words added', sent?.kind === 'virtuoso_setup' && sent.prompt.includes('1.1 GHz'), JSON.stringify(sent ?? {}).slice(0, 120));
  const shown = await evaluate(`document.querySelector('.setup-proposal')?.textContent ?? ''`);
  check('the proposal shows the Maestro setup and where it goes', shown.includes(`Maestro setup of the working copy ${COPY}/${TB}`) && shown.includes('analysis tran') && shown.includes('stop=50n')
    && shown.includes('variable VSUP') && shown.includes('V0.vdc in tb_ring_osc_3stage') && shown.includes('not into your cell'), shown.slice(0, 200));
  check('its button says it writes the copy', await evaluate(`[...document.querySelectorAll('.confirm button')].some(b => b.textContent.trim() === 'Approve, apply and write the copy')`));
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(path.join(out, 'agent-setup-1-proposal.png'), Buffer.from(data, 'base64'));
  await evaluate(`[...document.querySelectorAll('.confirm button')].find(b => b.textContent.trim() === 'Approve, apply and write the copy').click()`); await sleep(1200);
  check('approving applies and then says it was written into the copy and read back', (await chatText()).includes('written into the working copy') && (await chatText()).includes('it matches')
    && calls.some(c => c.path === '/api/agent/approve') && calls.some(c => c.path === '/api/agent/apply'));
  const config = await stored();
  check('the editors hold the proposed probe', (config.measurements ?? []).some(m => m.measurement_id === 'm_freq' && m.result_source === 'ade_output'), JSON.stringify(config.measurements));
  let saved = await saveTask();
  check('what the agent wrote into the copy replaces the file\'s analyses: Save task no longer sends them, the rest stays',
    !!saved && !('analyses' in (saved.extras ?? {})) && saved.extras?.expected_frequency_hz === 1.2e9, JSON.stringify(saved?.extras));
  await applyTaskFile();
  // A second proposal whose copy cannot be reached: the rows are applied all the same, and the page says what is left to do.
  applyOutcome = 'blocked';
  await evaluate(`(() => { const b = ${BOX}; b.focus(); })()`);
  await send('Input.insertText', { text: 'Set it up again.' });
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  for (let i = 0; i < 40 && !(await evaluate(`!!document.querySelector('.setup-proposal')`)); i++) await sleep(150);
  await evaluate(`[...document.querySelectorAll('.confirm button')].find(b => b.textContent.trim() === 'Approve, apply and write the copy').click()`); await sleep(1200);
  check('if the copy cannot be reached the rows are applied and the page says what to do', (await chatText()).includes('writing into the working copy failed') && (await chatText()).includes('press Save task'));
  saved = await saveTask();
  check('a write that failed hands the approved setup to Save task, over the file\'s analyses; the rest stays', saved?.extras?.analyses?.tran?.stop === '50n'
    && saved.extras.variables?.VSUP === '1.0' && saved.extras.bindings?.[0]?.instance === 'V0' && saved.extras.expected_frequency_hz === 1.2e9, JSON.stringify(saved?.extras));
  check('no other writing request was made', refused.length === 0, refused.join(' | '));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
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
