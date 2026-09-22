// Browser check of the Project panel's folded explanations (there is no frontend test runner in this project).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY request to /api/virtuoso/* is answered with a canned FIXTURE, so
// Virtuoso is never contacted. GET requests and the two read-only POSTs (circuit load of a registered task, static
// validation) pass through; every other writing request is refused here, so this check can start, save or probe
// nothing on the backend it runs against. The browser profile is new and temporary.
// What it pins (user request 2026-09-21): the long explanations of the Project panel are closed "details" lines like
// "Instances and parameters" - present, but not shown until their line is clicked - while headlines, warnings and
// every button stay visible; "Native schematic" is closed by default and then keeps the state the user gave it.
// Second request the same day ("hide this part"): the whole Hierarchy block - the tree, "Instances and parameters" and
// "Native schematic" - is ONE closed line under its own heading, and it keeps the state the user gave it as well.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 40 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/project_help_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9393, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-help-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0; const consoleErrors = [];
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const LIBRARY = 'FIXTURE_DESIGNS', CELLS = [{ name: 'ring_a', views: ['maestro', 'schematic', 'symbol'], has_schematic: true }, { name: 'ring_b', views: ['schematic'], has_schematic: true }];
const schematic = (library, cell) => ({ source: 'virtuoso', library, cell, origin: 'FIXTURE', instance_count: 2, nets: ['in', 'out'],
  instances: ['M0', 'M1'].map(name => ({ instance_path: name, master: { library: 'gpdk045', cell: 'nmos1v', view: 'symbol' }, terminals: [], parameters: { w: { raw: '1u' } } })),
  requires_confirmation: ['FIXTURE'], note: 'FIXTURE' });
const NOTE = 'FIXTURE NOTE: read from Virtuoso (canned answer).';
const draft = (library, cell) => ({ loaded: true, task_key: `virtuoso:${library}/${cell}`, mock: false, native_draft: true, complete: true, diagnostics: [], profile_task: null,
  profile_recipes: [{ id: 'ring_oscillator', label: 'Ring oscillator (free-running)' }], circuit: { library, cell, native_draft: true }, hierarchy: { XU1: { M1: {}, M2: {} }, V0: {} },
  working_copy: { verified: true, problems: [], copy: { library: `${library}_GATOR`, cell, testbench: `tb_${cell}` }, original: { library, cell, testbench: `tb_${cell}` } },
  analysis_context: null, evaluation_backend: null, max_concurrency: 1,
  summary: { device_count: 3, unknown_devices: [], devices: [{ instance_path: 'XU1/M1', kind: 'nmos', parameters: { w: { value: 4e-6 } } }] }, notes: [NOTE] });
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: false, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { M1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: [NOTE, 'FIXTURE NOTE: a second one.'] });
const ROWS = [{ variable_id: 'wn_fixture', instance_path: 'XU1/M1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005,
  target_kind: 'instance_parameter', value_type: 'continuous', scale: 'linear', relation: 'ratio', ratio: 1, name: '', notes: '' }];

try {
  // The connection profile comes from the configuration: seeded, so the check does not depend on the connection UI.
  const profiles = await (await fetch(new URL('api/connection/profiles', APP))).json().catch(() => ({}));
  const CONFIG = { schema_version: 'gator-workbench-config-v1', project: { name: 'fixture', task_name: 'fixture', notes: '' },
    circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' }, parameters: [], targets: [], measurements: [],
    run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0, connection_profile_id: profiles.active ?? 'fixture' },
    output: { experiment_name: 'fixture' }, research: {} };
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const calls = []; const refused = []; const imported = new Set(); const created = new Set(); let inFlight = 0;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = async ({ requestId, request }) => {
    const name = new URL(request.url).pathname, body = JSON.parse(request.postData ?? '{}');
    if (name.startsWith('/api/virtuoso/')) {
      const op = name.replace('/api/virtuoso/', '');
      calls.push(op); inFlight++; await sleep(150); inFlight--;
      if (op === 'libraries') return fulfil(requestId, 200, { libraries: [LIBRARY] });
      if (op === 'cells') return fulfil(requestId, 200, { library: body.library, truncated: false, technology_library: 'gpdk045', cells: CELLS });
      if (op === 'read') return fulfil(requestId, 200, schematic(body.library, body.cell));
      if (op === 'import') { imported.add(`${body.library}/${body.cell}`); return fulfil(requestId, 200, { library: body.library, cell: body.cell, testbench_cell: body.testbench, device_count: 3 }); }
      if (op === 'profile') { created.add(`real:${body.name}`); return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, recipe: body.recipe, circuit_class: 'vco', pdk_id: 'gpdk045', parameters: ROWS }); }
      if (op === 'task/save') { created.add(`real:${body.name}`); return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, revision: 1, created: true, runnable: true,
        circuit_class: 'vco', pdk_id: 'gpdk045', parameters: ROWS, copy: { library: `${body.library}_GATOR`, cell: body.cell, testbench: `tb_${body.cell}` } }); }
      return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
    }
    if (name === '/api/circuit/load') {
      const circuit = body.circuit ?? {};
      if (circuit.source === 'registered_task' && created.has(circuit.task_id)) return fulfil(requestId, 200, generated(circuit.task_id));
      if (circuit.source === 'virtuoso' && imported.has(`${circuit.library}/${circuit.cell}`)) return fulfil(requestId, 200, draft(circuit.library, circuit.cell));
      return send('Fetch.continueRequest', { requestId });                         // a registered task, or "no profile yet": read-only on the backend
    }
    if (request.method === 'GET' || name === '/api/config/validate') return send('Fetch.continueRequest', { requestId });
    refused.push(`${request.method} ${name}`);
    return fulfil(requestId, 418, { detail: { message: 'FIXTURE: this check lets no writing request through' } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 80) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Circuit source'))`;
  const FIELD = label => `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})?.querySelector('input, select')`;
  const BUTTON = text => `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const choose = (label, v) => evaluate(`(() => { const s = ${FIELD(label)}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(v)});
    s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const type = async (label, textToType) => { await evaluate(`(() => { const i = ${FIELD(label)}; i.focus(); i.select(); })()`); await send('Input.insertText', { text: textToType }); };
  const quiet = async (ms = 700) => { let seen = -1; while (seen !== calls.length || inFlight) { seen = calls.length; await sleep(ms); } };
  // "present" = in the page at all; "shown" = the innermost element holding the words is really rendered (a closed <details> hides its content).
  const HOLDER = needle => `[...${PANEL}.querySelectorAll('*')].filter(e => e.textContent.includes(${JSON.stringify(needle)}) && ![...e.children].some(c => c.textContent.includes(${JSON.stringify(needle)})))`;
  const present = needle => evaluate(`${HOLDER(needle)}.length > 0`);
  const shown = needle => evaluate(`${HOLDER(needle)}.some(e => e.checkVisibility())`);
  const folded = async needle => (await present(needle)) && !(await shown(needle));
  const SUMMARY = text => `[...${PANEL}.querySelectorAll('summary')].find(s => s.textContent.trim().startsWith(${JSON.stringify(text)}))`;
  const isOpen = text => evaluate(`${SUMMARY(text)}?.parentElement.open`);
  const click = expression => evaluate(`${expression}.click()`);
  const openLines = () => evaluate(`[...${PANEL}.querySelectorAll('details')].filter(d => d.open).map(d => d.querySelector('summary').textContent.trim())`);
  const buttonShown = text => evaluate(`!!(${BUTTON(text)}) && ${BUTTON(text)}.checkVisibility()`);
  const height = () => evaluate(`Math.round(${PANEL}.getBoundingClientRect().height)`);
  const shot = async name => {                          // a tall window, so the whole column is on the picture instead of its visible part
    await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 2600, deviceScaleFactor: 1, mobile: false }); await sleep(250);
    const clip = await evaluate(`(() => { const r = ${PANEL}.getBoundingClientRect(); return { x: r.x - 4, y: r.y - 4, width: r.width + 8, height: Math.min(r.height + 8, 2500), scale: 2 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
    await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))});` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${PANEL}) && ${PANEL}.textContent.includes('Hierarchy (')`, 150))) throw new Error('the Project panel never showed a loaded circuit | panel: '
    + (await evaluate(`${PANEL}?.textContent.slice(0, 700) ?? 'no panel'`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- a registered task: nothing is unfolded by itself ----------------------------------------------------------
  check('on page load no line of the panel is unfolded', (await openLines()).length === 0, (await openLines()).join(' | '));
  check('"What circuit class and PDK id are for" is a closed line; its text is there but not shown', await folded('labels saved with every run') && await shown('What circuit class and PDK id are for'));
  check('the MOCK banner stays in view', await shown('MOCK evaluation backend'));
  await click(SUMMARY('What circuit class and PDK id are for')); await sleep(200);
  check('a click on the line shows the text', await shown('labels saved with every run') && await isOpen('What circuit class and PDK id are for'));
  await click(SUMMARY('What circuit class and PDK id are for')); await sleep(200);
  check('a second click folds it again', await folded('labels saved with every run'));

  // ---- the whole Hierarchy block is one closed line under its heading -------------------------------------------------
  const HIERARCHY = `${SUMMARY('Hierarchy (')}?.parentElement`;
  const TREE = `${HIERARCHY}.querySelector('ul.tree')`;
  check('Hierarchy is ONE closed line that still looks like a heading', (await evaluate(`${HIERARCHY}.open`)) === false && await shown('Hierarchy (')
    && await evaluate(`!!${SUMMARY('Hierarchy (')}.querySelector('h3') && getComputedStyle(${SUMMARY('Hierarchy (')}.querySelector('h3')).display === 'inline'`));
  check('folded inside it: the tree and "Instances and parameters"', await evaluate(`!!${TREE} && !${TREE}.checkVisibility()`) && await folded('Instances and parameters'));
  await shot('help-1-registered-task.png');
  await click(SUMMARY('Hierarchy (')); await sleep(250);
  check('a click opens it: the tree is shown, "Instances and parameters" is a closed line inside it', (await evaluate(`${HIERARCHY}.open`)) === true
    && await evaluate(`${TREE}.checkVisibility()`) && await shown('Instances and parameters') && (await isOpen('Instances and parameters')) === false);
  await click(SUMMARY('Instances and parameters')); await sleep(200);
  check('opening the inner line leaves the block open (an inner toggle is not taken for the block\'s own)', (await evaluate(`${HIERARCHY}.open`)) === true && (await isOpen('Instances and parameters')) === true);
  await click(SUMMARY('Instances and parameters')); await sleep(200);
  await shot('help-1b-hierarchy-open.png');                                         // left open: the later states must find it as the user left it

  // ---- Import Spectre netlist: one short line says what to do, the rest is folded ------------------------------------
  await choose('Source', 'netlist'); await sleep(900);
  check('netlist: the short instruction is in view', await shown('Two files are needed: fill in both paths'));
  check('netlist: the long explanation is folded under "Which two files, and where they may be"', await shown('Which two files, and where they may be')
    && await folded('nothing is uploaded from the browser') && await folded('--allow-input-root'));
  check('netlist: both buttons stay in view', await buttonShown('Load netlist') && await buttonShown('Try the example'));
  await click(SUMMARY('Which two files')); await sleep(200);
  check('netlist: a click shows what the two files are and where they may be', await shown('nothing is uploaded from the browser') && await shown('--allow-input-root'));
  await shot('help-2-netlist-unfolded.png');

  // ---- Virtuoso source: browse only ---------------------------------------------------------------------------------------
  await choose('Source', 'virtuoso'); await quiet();
  await choose('Library', LIBRARY); await quiet();
  await choose('Cell', 'ring_a'); await quiet();
  check('virtuoso: the three reads happened through fixtures only', JSON.stringify(calls) === JSON.stringify(['libraries', 'cells', 'read']), calls.join(' | '));
  check('browse only: the headline is in view', await shown('Browse only: you can look at this cell here'));
  check('browse only: what a circuit profile is, is folded under "Why: ..."', await shown('Why: it has no circuit profile yet') && await folded('a checked description of three things')
    && await folded('which testbench simulates the circuit'));
  // The row of real:* shortcut buttons was removed on the user's request (status record 7.40): one folded sentence points to the selector instead.
  const offered = await evaluate(`[...${PANEL}.querySelectorAll('.note button')].filter(b => b.textContent.startsWith('real:')).length`);
  check('browse only: no shortcut buttons to the existing real tasks; where they are is one folded sentence under "Why: ..."', offered === 0
    && await folded('Circuits that already have one are under Source: Registered task.'), `${offered} button(s)`);
  check('browse only: "Read this cell into the workbench" stays in view, its explanation is folded', await buttonShown('Read this cell into the workbench')
    && await shown('To start a profile for this cell') && await shown('choose its Testbench cell above first') && await folded('Read-only, no simulation, some seconds'));
  check('the view remark is one line: "View: schematic"; the reason is folded', await shown('View: schematic') && await folded('The only view the reader opens') && await folded('maestro, symbol'));
  const before = await height();

  // ---- Native schematic: closed by default, then as the user left it --------------------------------------------------------
  const NATIVE = `[...${PANEL}.querySelectorAll('details')].find(d => d.querySelector('summary')?.textContent.startsWith('Native schematic'))`;
  check('Native schematic is listed with its cell and instance count', await shown(`Native schematic ${LIBRARY}/ring_a (2 instances, as read)`));
  check('browse only: no circuit is loaded, so there is no Hierarchy block and Native schematic stands alone', !(await evaluate(`!!(${SUMMARY('Hierarchy (')})`)));
  check('Native schematic is CLOSED by default: its table is not shown', (await evaluate(`${NATIVE}.open`)) === false && await folded('gpdk045/nmos1v') && await folded('Requires confirmation'));
  await shot('help-3-virtuoso-browse.png');
  await click(`${NATIVE}.querySelector('summary')`); await sleep(250);
  check('a click opens it: the instances are shown', (await evaluate(`${NATIVE}.open`)) === true && await shown('gpdk045/nmos1v') && (await evaluate(`${NATIVE}.querySelectorAll('tbody tr').length`)) === 2);
  await choose('Cell', 'ring_b'); await quiet();
  check('another cell: it stays open, as the user left it', (await evaluate(`${NATIVE}.open`)) === true && await shown(`Native schematic ${LIBRARY}/ring_b`));
  await click(`${NATIVE}.querySelector('summary')`); await sleep(250);
  await click(BUTTON('Refresh')); await quiet();
  check('closed again by the user: Refresh does not reopen it', (await evaluate(`${NATIVE}.open`)) === false && await folded('gpdk045/nmos1v'));
  await choose('Cell', 'ring_a'); await quiet();

  // ---- every folded line unfolds; the panel is much shorter folded ------------------------------------------------------------
  const lines = await evaluate(`[...${PANEL}.querySelectorAll('details.more > summary')].map(s => s.textContent.trim())`);
  await evaluate(`${PANEL}.querySelectorAll('details.more > summary').forEach(s => s.click())`); await sleep(300);
  const allOpen = await evaluate(`[...${PANEL}.querySelectorAll('details.more')].every(d => d.open && [...d.children].every(c => c.checkVisibility()))`);
  const after = await height();
  check('every folded line of this state unfolds on a click', lines.length === 4 && allOpen, lines.join(' | '));
  check('folded, the panel is clearly shorter than unfolded', after - before > 150, `${before} px folded, ${after} px unfolded`);
  await evaluate(`${PANEL}.querySelectorAll('details.more > summary').forEach(s => s.click())`); await sleep(200);

  // ---- the cell read into the workbench (a draft) -----------------------------------------------------------------------------------
  await click(BUTTON('Read this cell into the workbench')); await quiet(); await until(`${PANEL}.textContent.includes('Not optimizable yet')`);
  check('draft: the headline is in view', await shown('Read from Virtuoso. Not optimizable yet: it has no circuit profile.'));
  check('draft: what to do with it is folded under "What you can do with it now"', await shown('What you can do with it now') && await folded('The workbench now holds its own copy') && await folded('Its answer is a proposal'));
  check('draft: the two buttons stay in view', await buttonShown('Ask the agent to set up') && await buttonShown('Read the cell again'));
  check('draft: "Then save it as a task." with Save task stays in view, the explanation is folded', await shown('Then save it as a task.') && await shown('What Save task does')
    && await folded('Saving again makes the next revision') && await evaluate(`${FIELD('New task name')}.checkVisibility()`) && await buttonShown('Save task') && await buttonShown('Task file'));
  check('draft: the backend\'s note is one closed line "1 note on this circuit"', await shown('1 note on this circuit') && await folded(NOTE));
  await click(SUMMARY('1 note on this circuit')); await sleep(200);
  check('draft: a click shows the note', await shown(NOTE));
  await shot('help-4-draft.png');
  await click(SUMMARY('1 note on this circuit')); await sleep(200);               // a line stays as the user left it while it is on screen: fold it again
  check('draft: Hierarchy is open, as the user left it two circuits ago; "Native schematic" is now a line inside it', (await evaluate(`${HIERARCHY}.open`)) === true
    && await evaluate(`${TREE}.checkVisibility()`) && await evaluate(`${HIERARCHY}.contains(${NATIVE})`) && await shown('Native schematic') && (await evaluate(`${NATIVE}.open`)) === false);
  await click(SUMMARY('Hierarchy (')); await sleep(250);
  check('draft: closed by the user, the whole block is one line again: tree, "Instances and parameters" and "Native schematic" are folded', (await evaluate(`${HIERARCHY}.open`)) === false
    && await shown('Hierarchy (3 instances)') && await evaluate(`!${TREE}.checkVisibility()`) && await folded('Instances and parameters') && await folded('Native schematic'));
  await shot('help-4b-draft-hierarchy-closed.png');

  // ---- a saved task (was: a generated profile) -----------------------------------------------------------------------------------------
  await click(BUTTON('Save task')); await quiet(); await until(`${PANEL}.textContent.includes('Before every run')`);
  check('generated profile: the REAL banner and the missing-baseline warning stay in view', await shown('REAL evaluation backend') && await shown('This task has no real baseline yet'));
  check('generated profile: "Before every run" and both buttons stay in view', await shown('Before every run:') && await buttonShown('Check now')
    && await buttonShown('Record the baseline run as reference'));
  check('generated profile: what the check compares is folded', await shown('What the check compares') && await folded('no ADE/Maestro window may be open on the copy'));
  check('generated profile: two notes are one closed line', await shown('2 notes on this circuit') && await folded('FIXTURE NOTE: a second one.'));
  check('generated profile: Hierarchy stays closed, as the user left it', (await evaluate(`${HIERARCHY}.open`)) === false && await shown('Hierarchy (1 instances)') && await folded('Instances and parameters'));
  await shot('help-5-generated-profile.png');

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect or call an agent on its own: never', !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify)/.test(r)), refused.join(', '));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  ws.close();
} catch (error) {
  failures++; console.log('ERROR ' + (error?.stack ?? error));
  if (consoleErrors.length) console.log('page errors: ' + consoleErrors.join(' | ').slice(0, 600));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; the temp dir is harmless */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
