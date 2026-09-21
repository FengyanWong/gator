// Browser check of "Circuit source = Virtuoso library / cell / view" in the Project panel (no frontend test runner).
// Same approach as agent_tab_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY request to /api/virtuoso/* is intercepted, logged and answered
// with a canned FIXTURE answer, so Virtuoso is never contacted and the check does not depend on the backend version.
// What it pins (user request 2026-09-20): the libraries list themselves when the source is chosen (no button), a
// library lists its cells, a cell reads its schematic, one request per step and in that order; no view is asked
// for; the PDK id is offered from the technology library; a blocked gate and an older backend are readable.
// Needs a configured connection profile (the panel selects the active one; reading the profiles probes nothing).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/virtuoso_source_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9381, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-virt-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0; const consoleErrors = [];
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const LIBRARIES = ['FIXTURE_DESIGNS', 'FIXTURE_OTHER', 'analogLib'];
const CELLS = {
  FIXTURE_DESIGNS: { technology_library: 'gpdk045', cells: [
    { name: 'ota5_v1', views: ['maestro', 'schematic', 'symbol'], has_schematic: true },
    { name: 'ota5_tb', views: ['schematic'], has_schematic: true },
    { name: 'vco_fixture', views: ['schematic', 'symbol'], has_schematic: true },           // stands for the cell of a verified built-in circuit
    { name: 'symbol_only', views: ['symbol'], has_schematic: false }] },
  FIXTURE_OTHER: { technology_library: 'otherTech', cells: [{ name: 'inv', views: ['schematic', 'symbol'], has_schematic: true }] },
};
const schematic = (library, cell) => ({ source: 'virtuoso', library, cell, origin: 'FIXTURE', instance_count: 2, nets: ['in', 'out'],
  instances: ['M0', 'M1'].map(name => ({ instance_path: name, master: { library: 'gpdk045', cell: 'nmos1v', view: 'symbol' }, terminals: [], parameters: { w: { raw: '1u' } } })),
  requires_confirmation: ['FIXTURE'], note: 'FIXTURE' });
const draft = (library, cell) => ({ loaded: true, task_key: `virtuoso:${library}/${cell}`, mock: false, native_draft: true, complete: true, diagnostics: [],
  profile_task: created.has(`${library}/${cell}`) ? `real:${cell}` : null, profile_task_generated: created.has(`${library}/${cell}`) ? true : null,
  profile_recipes: RECIPES,
  circuit: { library, cell, native_draft: true }, hierarchy: { XU1: { M1: {}, M2: {} }, V0: {} }, analysis_context: null, evaluation_backend: null, max_concurrency: 1,
  summary: { device_count: 3, unknown_devices: [], devices: [{ instance_path: 'XU1/M1', kind: 'nmos', parameters: { w: { value: 4e-6 } } }] },
  notes: ['FIXTURE: read from Virtuoso (canned answer).'] });
const created = new Set();                                                          // "library/cell" of profiles created in this check
const ROWS = [{ variable_id: 'wn_fixture', instance_path: 'XU1/M1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005,
  target_kind: 'instance_parameter', value_type: 'continuous', scale: 'linear', relation: 'ratio', ratio: 1, name: '', notes: '' }];
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: false, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { M1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: ['FIXTURE: generated profile.'] });
const RECIPES = [{ id: 'ring_oscillator', label: 'Ring oscillator (free-running)' }, { id: 'opamp_ac', label: 'Op-amp / OTA (AC gain)' }];
const builtInCell = { loaded: false, blocker: 'FIXTURE: a native cellview needs a verified circuit profile', interface_contract: null,
  profile_task: 'real:gpdk045_vco', profile_task_generated: false, profile_recipes: RECIPES };
const gateBlocked = { message: 'The connection gate blocked reading the native design', gate: { allowed: false, status: 'blocked', blocking: ['tunnel'], uncertain: [] } };

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const calls = []; let mode = 'ok'; let inFlight = 0, overlap = false;
  const imported = new Set(); let agentRequests = 0; let baselineExists = false; let baselineRecorded = false; let deleteRefused = true;
  const dialogs = []; const answers = [];                                           // confirm(): answered as planned; an unplanned one is refused and reported
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = async ({ requestId, request }) => {
    const pathname = new URL(request.url).pathname;
    if (pathname === '/api/agent/propose') { agentRequests++; return fulfil(requestId, 418, { detail: { message: 'FIXTURE: no agent request is expected' } }); }
    if (pathname === '/api/tasks') {                                                 // the real list + the profiles created in this check
      const real = await (await fetch(new URL('api/tasks', APP))).json();
      return fulfil(requestId, 200, { ...real, tasks: [...real.tasks, ...[...created].map(key => ({ task_key: `real:${key.split('/')[1]}`, kind: 'real', available: true, generated: true }))] });
    }
    if (pathname === '/api/tasks/starter') {                                         // a profile created in this check brings the rows it registered
      const task = new URL(request.url).searchParams.get('task_key');
      return [...created].some(key => task === `real:${key.split('/')[1]}`)
        ? fulfil(requestId, 200, { project: { name: 'fixture-profile', task_name: task.replace('real:', '') }, parameters: ROWS, targets: [], measurements: [], run: {} })
        : send('Fetch.continueRequest', { requestId });
    }
    if (pathname === '/api/circuit/load') {                                          // an imported cell loads from the backend's local copy
      const circuit = JSON.parse(request.postData ?? '{}').circuit ?? {};
      if (circuit.source === 'registered_task' && [...created].some(key => circuit.task_id === `real:${key.split('/')[1]}`)) return fulfil(requestId, 200, { ...generated(circuit.task_id), baseline_recorded: baselineRecorded });
      if (circuit.source === 'virtuoso' && circuit.cell === 'vco_fixture') return fulfil(requestId, 200, builtInCell);
      return circuit.source === 'virtuoso' && imported.has(`${circuit.library}/${circuit.cell}`)
        ? fulfil(requestId, 200, draft(circuit.library, circuit.cell)) : send('Fetch.continueRequest', { requestId });
    }
    const op = pathname.replace('/api/virtuoso/', ''), body = JSON.parse(request.postData ?? '{}');
    calls.push({ op, ...body });
    if (inFlight++) overlap = true;                                                  // two bridge calls at once must not happen
    await sleep(250);                                                                // a little latency, so an overlap would show
    inFlight--;
    if (mode === 'blocked') return fulfil(requestId, 409, { detail: gateBlocked });
    if (op === 'libraries') return fulfil(requestId, 200, { libraries: LIBRARIES });
    if (op === 'cells') return mode === 'outdated' ? fulfil(requestId, 404, { detail: 'Not Found' })
      : fulfil(requestId, 200, { library: body.library, truncated: false, ...(CELLS[body.library] ?? { technology_library: null, cells: [] }) });
    if (op === 'read') return fulfil(requestId, 200, schematic(body.library, body.cell));
    if (op === 'profile/preflight') return fulfil(requestId, 200, { profile_preflight: true, name: body.name, ok: true, simulated: false, deck: '/fixture/ring_osc.scs',
      steps: ['profile', 'connect', 'export', 'deck'].map(step => ({ step, ok: true, detail: `FIXTURE: ${step} passed` })) });
    if (op === 'profile/reference') {
      if (!baselineExists) return fulfil(requestId, 409, { detail: { message: 'No run of real:ota5_v1 was found under the output root. Run "Single baseline simulation" first.', code: 'no_baseline_run' } });
      baselineRecorded = true;
      return fulfil(requestId, 200, { origin: 'real', run_id: 'fixture-run-1', metrics: { osc_frequency_hz: 1.2e9 } });
    }
    if (op === 'profile/delete') {
      if (deleteRefused) return fulfil(requestId, 409, { detail: { message: `Run fixture-run-2 of real:${body.name} is working right now: abort it or let it finish first`, code: 'delete_refused' } });
      created.delete(`FIXTURE_DESIGNS/${body.name}`); baselineRecorded = false;
      return fulfil(requestId, 200, { deleted: `real:${body.name}`, name: body.name, library: 'FIXTURE_DESIGNS', cell: body.name, testbench_cell: 'ota5_tb', baseline_recorded: true,
        kept_copy: `/fixture/profiles/.deleted/${body.name}.20260921T000000Z` });
    }
    if (op === 'profile') {
      if (body.name === 'refuse_me') return fulfil(requestId, 409, { detail: { message: 'FIXTURE: the real backend can only change transistor widths', code: 'profile_refused' } });
      const circuit = body.config.circuit;
      created.add(`${circuit.library}/${circuit.cell}`);
      return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, recipe: body.recipe, circuit_class: 'vco', pdk_id: 'gpdk045', parameters: ROWS });
    }
    if (op === 'import') { imported.add(`${body.library}/${body.cell}`); return fulfil(requestId, 200, { library: body.library, cell: body.cell, testbench_cell: body.testbench, device_count: 3 }); }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
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
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Circuit source'))`;
  const LABEL = label => `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})`;
  const FIELD = label => `${LABEL(label)}?.querySelector('input, select')`;
  const BUTTON = text => `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const text = () => evaluate(`${PANEL}.textContent`);
  const value = label => evaluate(`${FIELD(label)}.value`);
  const options = label => evaluate(`[...${FIELD(label)}.options].map(o => ({ value: o.value, text: o.textContent.trim(), disabled: o.disabled }))`);
  const choose = (label, v) => evaluate(`(() => { const s = ${FIELD(label)}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(v)});
    s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const type = async (label, textToType) => { await evaluate(`(() => { const i = ${FIELD(label)}; i.focus(); i.select(); })()`); await send('Input.insertText', { text: textToType }); };
  const ops = (from = 0) => calls.slice(from).map(c => [c.op, c.library, c.cell, c.testbench, c.name, c.recipe, c.expected_frequency_hz].filter(Boolean).join(' '));
  const quiet = async (ms = 1500) => { let seen = -1; while (seen !== calls.length || inFlight) { seen = calls.length; await sleep(ms); } };
  const shot = async (name, bottom = null) => {                                     // `bottom`: an element to bring to the lower edge instead of the heading to the top
    const H3 = `[...${PANEL}.querySelectorAll('h3')].find(h => h.textContent.trim() === 'Circuit source')`;
    await evaluate(bottom ? `${bottom}.scrollIntoView({ block: 'end' })` : `${H3}.scrollIntoView({ block: 'start' })`); await sleep(200);
    const clip = await evaluate(`(() => { const a = document.querySelector('.left').getBoundingClientRect(), h = ${H3}.getBoundingClientRect();
      return { x: a.x, y: Math.max(a.y, h.y - 6), width: a.width, height: a.bottom - Math.max(a.y, h.y - 6), scale: 2 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: ['*/api/virtuoso/*', '*/api/circuit/load', '*/api/agent/propose', '*/api/tasks', '*/api/tasks/starter*'].map(urlPattern => ({ urlPattern, requestStage: 'Request' })) });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  // The connection in use is named on the one "Connection" button of the left column (its window is not needed here).
  for (let i = 0; i < 60 && !(await evaluate(`/\\S/.test(document.querySelector('.left button.connection-button .connection-button-what')?.textContent.replace(/none (selected|set up yet)/, '') ?? '')`)); i++) await sleep(100);
  await sleep(800);
  check('nothing is read from Virtuoso while another source is chosen', calls.length === 0, ops().join(' | '));

  // ---- choosing the source lists the libraries: no button ------------------------------------------------------
  await choose('Source', 'virtuoso'); await quiet();
  check('choosing the source lists the libraries by itself, once', JSON.stringify(ops()) === JSON.stringify(['libraries']), ops().join(' | '));
  check('there is no "List libraries" button any more', !(await evaluate(`!!(${BUTTON('List libraries')})`)));
  check('the Library dropdown offers what Virtuoso answered', JSON.stringify((await options('Library')).slice(1).map(o => o.value)) === JSON.stringify(LIBRARIES), JSON.stringify(await options('Library')));
  check('the Cell dropdown waits for a library', await evaluate(`${FIELD('Cell')}.disabled`) && (await options('Cell'))[0].text === '(choose a library first)');
  check('no view is asked for', !(await evaluate(`!!(${LABEL('View')})`)));
  check('this source reads "Browse only", not "Blocked"', (await text()).includes('Browse only:') && !(await text()).includes('Blocked:'));
  await shot('virtuoso-1-libraries.png');

  // ---- a library lists its cells ----------------------------------------------------------------------------------
  let mark = calls.length;
  await choose('Library', 'FIXTURE_DESIGNS'); await quiet();
  check('choosing a library lists its cells, once', JSON.stringify(ops(mark)) === JSON.stringify(['cells FIXTURE_DESIGNS']), ops(mark).join(' | '));
  const cellOptions = await options('Cell');
  check('the Cell dropdown lists them; a cell without a schematic cannot be chosen', cellOptions.length === 5 && cellOptions.find(o => o.value === 'symbol_only')?.disabled === true
    && cellOptions.find(o => o.value === 'symbol_only').text.includes('no schematic view') && cellOptions.find(o => o.value === 'ota5_v1')?.disabled === false, JSON.stringify(cellOptions));
  check('the PDK id is offered from the technology library', (await value('PDK id')) === 'gpdk045', await value('PDK id'));
  check('the testbench dropdown offers the cells that have a schematic', JSON.stringify((await options('Testbench cell')).map(o => o.value)) === JSON.stringify(['', 'ota5_v1', 'ota5_tb', 'vco_fixture']), JSON.stringify(await options('Testbench cell')));

  // ---- a cell reads its schematic ------------------------------------------------------------------------------------
  mark = calls.length;
  await choose('Cell', 'ota5_v1'); await quiet();
  check('choosing a cell reads its schematic, once', JSON.stringify(ops(mark)) === JSON.stringify(['read FIXTURE_DESIGNS ota5_v1']), ops(mark).join(' | '));
  check('the schematic is shown as read', (await text()).includes('Native schematic FIXTURE_DESIGNS/ota5_v1 (2 instances'));
  check('the panel says which view is read and which others exist', (await text()).includes('View: schematic') && (await text()).includes('maestro, symbol'));
  await shot('virtuoso-2-cell-read.png');

  // ---- reading the cell INTO the workbench: an explicit press; then the agent hand-off -----------------------------------
  check('a chosen cell offers "Read this cell into the workbench"', !(await evaluate(`${BUTTON('Read this cell into the workbench')}.disabled`)) && (await text()).includes('To start a profile for this cell'));
  mark = calls.length;
  await evaluate(`${BUTTON('Read this cell into the workbench')}.click()`); await quiet();
  check('the press imports the cell once (no testbench chosen)', JSON.stringify(ops(mark)) === JSON.stringify(['import FIXTURE_DESIGNS ota5_v1']), ops(mark).join(' | '));
  check('the cell is then loaded from the local copy and shown as a draft', (await text()).includes('Read from Virtuoso. Not optimizable yet') && (await text()).includes('Hierarchy (3 instances)')
    && !(await text()).includes('REAL evaluation backend') && !(await text()).includes('Browse only'));
  await choose('Testbench cell', 'ota5_tb'); await sleep(600);
  mark = calls.length;
  await evaluate(`${BUTTON('Read the cell again')}.click()`); await quiet();
  check('"Read the cell again" exports through the chosen testbench', JSON.stringify(ops(mark)) === JSON.stringify(['import FIXTURE_DESIGNS ota5_v1 ota5_tb']), ops(mark).join(' | '));
  await shot('virtuoso-2b-draft.png');
  await evaluate(`${BUTTON('Ask the agent for suggestions')}.click()`); await sleep(800);
  const box = await evaluate(`document.querySelector('footer textarea')?.value ?? ''`);
  check('"Ask the agent" opens the Agent tab with the request written out', box.includes('which device sizes to vary') && box.includes('what it is'), box.slice(0, 80));
  check('nothing was sent to the agent by itself', agentRequests === 0, `${agentRequests} request(s)`);

  // ---- Create profile: refused in words, then registered; the cell stops being browse-only ------------------------------
  check('"Create profile" waits for the expected frequency', await evaluate(`${BUTTON('Create profile')}.disabled`));
  await type('Expected oscillation frequency', '1.2G'); await sleep(300);
  await type('Profile name', 'refuse_me'); await sleep(300);
  mark = calls.length;
  await evaluate(`${BUTTON('Create profile')}.click()`); await quiet();
  check('a refusal is shown in its own words and nothing changes', JSON.stringify(ops(mark)) === JSON.stringify(['profile refuse_me ring_oscillator 1200000000'])
    && (await text()).includes('can only change transistor widths') && (await value('Source')) === 'virtuoso', ops(mark).join(' | '));
  await evaluate(`(() => { const i = ${FIELD('Profile name')}; i.focus(); i.select(); })()`); await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 }); await sleep(300);
  mark = calls.length;
  await evaluate(`${BUTTON('Create profile')}.click()`); await quiet();
  check('an empty name falls back to the cell name; the type and 1.2G = 1.2e9 Hz are sent', JSON.stringify(ops(mark)) === JSON.stringify(['profile ota5_v1 ring_oscillator 1200000000']), ops(mark).join(' | '));
  check('the new task is opened as a registered task', (await value('Source')) === 'registered_task' && (await value('Task')) === 'real:ota5_v1', `${await value('Source')} / ${await value('Task')}`);
  check('it says what happened and what comes first', (await text()).includes('Profile real:ota5_v1 created') && (await text()).includes('Single baseline simulation'));
  check('the parameter editor shows the rows as registered', await evaluate(`document.querySelector('main').innerHTML.includes('wn_fixture')`));
  await shot('virtuoso-2c-profile-created.png');
  // ---- before the first costed run: the no-simulation check, and recording a finished baseline ---------------------------
  mark = calls.length;
  await evaluate(`${BUTTON('Check against Virtuoso (no simulation)')}.click()`); await quiet();
  check('the check is one request for this profile and this connection', JSON.stringify(calls.slice(mark).map(c => [c.op, c.name, c.profile_id])) === JSON.stringify([['profile/preflight', 'ota5_v1', 'lab']]), JSON.stringify(calls.slice(mark)));
  const shownCheck = await text();
  check('its four steps and the verdict are shown', ['passed: profile', 'passed: connect', 'passed: export', 'passed: deck', 'The profile matches the live cell. Nothing was simulated.'].every(t => shownCheck.includes(t)));
  await evaluate(`${BUTTON('Record the baseline run as reference')}.click()`); await quiet();
  check('without a baseline run, recording says what to do first', (await text()).includes('Run "Single baseline simulation" first'));
  baselineExists = true;
  await evaluate(`${BUTTON('Record the baseline run as reference')}.click()`); await quiet();
  check('with one, the baseline is recorded and said so', (await text()).includes('Baseline recorded from run fixture-run-1'));
  // ---- a cell that already has a registered task says so: no second profile, one short "Open" -----------------------------
  mark = calls.length;
  await choose('Source', 'virtuoso'); await quiet();
  let shown = await text();
  check('the cell is no longer browse-only: the form names its task', shown.includes('This cell already has a registered task: real:ota5_v1') && !shown.includes('built-in')
    && !shown.includes('Not optimizable yet') && !shown.includes('Browse only'), ops(mark).join(' | '));
  check('no second profile is offered for it', !(await evaluate(`!!(${BUTTON('Create profile')})`)) && !(await evaluate(`!!(${BUTTON('Read the cell again')})`)));
  check('the button is short; the task name is text beside it', JSON.stringify(await evaluate(`[...${PANEL}.querySelectorAll('.note button')].map(b => b.textContent.trim())`)) === JSON.stringify(['Open']));
  await shot('virtuoso-2d-cell-has-task.png');
  await choose('Cell', 'vco_fixture'); await quiet();
  shown = await text();
  check('the cell of a verified built-in circuit names that task', shown.includes('This cell already has a registered task: real:gpdk045_vco (a verified built-in circuit)')
    && !shown.includes('Browse only') && !shown.includes('cannot optimize it yet'));
  check('it is not offered for reading or for a profile', !(await evaluate(`!!(${BUTTON('Read this cell into the workbench')})`)) && !(await evaluate(`!!(${BUTTON('Create profile')})`)));
  check('what that means is one folded line', await evaluate(`(() => { const d = [...${PANEL}.querySelectorAll('.note details')].find(x => x.querySelector('summary').textContent === 'What this means');
    return !!d && !d.open && d.textContent.includes('A cell has one task'); })()`));
  await shot('virtuoso-2e-built-in-cell.png');
  await evaluate(`${BUTTON('Open')}.click()`); await quiet();
  check('"Open" chooses the task under Source: Registered task', (await value('Source')) === 'registered_task' && (await value('Task')) === 'real:gpdk045_vco', `${await value('Source')} / ${await value('Task')}`);
  check('a built-in circuit has no Delete profile', !(await evaluate(`!!(${BUTTON('Delete profile')})`)));

  // ---- Delete profile: asked once more, refused while a run works, then back at the cell with Create profile ----------------
  await choose('Source', 'virtuoso'); await quiet();
  await choose('Cell', 'ota5_v1'); await quiet();
  await evaluate(`${BUTTON('Open')}.click()`); await quiet();
  check('the generated profile is opened from its cell', (await value('Source')) === 'registered_task' && (await value('Task')) === 'real:ota5_v1', `${await value('Source')} / ${await value('Task')}`);
  check('its block ends with "Delete profile", explained beside the button', !!(await evaluate(`!!(${BUTTON('Delete profile')})`)) && (await text()).includes('A profile is never edited.'));
  await shot('virtuoso-2f-delete-offered.png', BUTTON('Delete profile'));
  mark = calls.length; answers.push(false);
  await evaluate(`${BUTTON('Delete profile')}.click()`); await quiet(800);
  const asked = dialogs[dialogs.length - 1]?.message ?? '';
  check('the press asks once more and says what goes', asked.includes('Delete the profile real:ota5_v1?') && asked.includes('can no longer be resumed') && asked.includes('copy of the profile')
    && asked.includes('recorded baseline goes with it'), asked.slice(0, 120));
  check('"Cancel" deletes nothing', ops(mark).length === 0 && (await value('Task')) === 'real:ota5_v1', ops(mark).join(' | '));
  answers.push(true);
  await evaluate(`${BUTTON('Delete profile')}.click()`); await quiet();
  check('a refusal is shown in its own words and the task stays', JSON.stringify(ops(mark)) === JSON.stringify(['profile/delete ota5_v1']) && (await text()).includes('is working right now')
    && (await value('Task')) === 'real:ota5_v1', ops(mark).join(' | '));
  deleteRefused = false; mark = calls.length; answers.push(true);
  await evaluate(`${BUTTON('Delete profile')}.click()`); await quiet();
  shown = await text();
  check('deleting is one request', JSON.stringify(ops(mark).filter(o => o.startsWith('profile'))) === JSON.stringify(['profile/delete ota5_v1']), ops(mark).join(' | '));
  check('the form goes back to the cell the profile was made from', (await value('Source')) === 'virtuoso' && (await value('Library')) === 'FIXTURE_DESIGNS' && (await value('Cell')) === 'ota5_v1'
    && (await value('Testbench cell')) === 'ota5_tb', `${await value('Source')} / ${await value('Library')} / ${await value('Cell')} / ${await value('Testbench cell')}`);
  check('it says what happened; where the files went is one folded line', shown.includes('Profile real:ota5_v1 deleted. This cell can get a new one.')
    && await evaluate(`(() => { const d = [...${PANEL}.querySelectorAll('details')].find(x => x.querySelector('summary').textContent === 'Where its files went');
      return !!d && !d.open && d.textContent.includes('/fixture/profiles/.deleted/ota5_v1'); })()`));
  check('the cell offers Create profile again', !!(await evaluate(`!!(${BUTTON('Create profile')})`)) && shown.includes('Not optimizable yet') && !shown.includes('already has a registered task'));
  check('the task left the Registered task list', !(await evaluate(`(async () => (await (await fetch('/api/tasks')).json()).tasks.some(t => t.task_key === 'real:ota5_v1'))()`)));
  await shot('virtuoso-2g-profile-deleted.png');

  // ---- another library: the cell is forgotten, a typed PDK id is kept -----------------------------------------------
  await type('PDK id', 'my_pdk'); await sleep(300);
  mark = calls.length;
  await choose('Library', 'FIXTURE_OTHER'); await quiet();
  check('another library lists its own cells and reads nothing yet', JSON.stringify(ops(mark)) === JSON.stringify(['cells FIXTURE_OTHER']), ops(mark).join(' | '));
  check('the cell of the old library is forgotten and its schematic is gone', (await value('Cell')) === '' && !(await text()).includes('Native schematic'));
  check('a typed PDK id is not overwritten', (await value('PDK id')) === 'my_pdk', await value('PDK id'));

  // ---- Refresh repeats the chain, one call after the other -------------------------------------------------------------
  await choose('Cell', 'inv'); await quiet();
  mark = calls.length; overlap = false;
  await evaluate(`${BUTTON('Refresh')}.click()`); await quiet();
  check('Refresh reads libraries, cells and schematic again, in that order', JSON.stringify(ops(mark)) === JSON.stringify(['libraries', 'cells FIXTURE_OTHER', 'read FIXTURE_OTHER inv']), ops(mark).join(' | '));
  check('never two bridge calls at once', !overlap);

  // ---- the link is down: readable, and Refresh recovers ------------------------------------------------------------------
  mode = 'blocked'; mark = calls.length;
  await evaluate(`${BUTTON('Refresh')}.click()`); await quiet();
  check('a blocked gate stops the chain at the first step', JSON.stringify(ops(mark)) === JSON.stringify(['libraries']), ops(mark).join(' | '));
  check('and says what to do', (await text()).includes('Virtuoso cannot be reached (tunnel)') && (await text()).includes('Connection window'));
  check('the configured library stays visible while nothing can be listed', (await value('Library')) === 'FIXTURE_OTHER');
  await shot('virtuoso-3-link-down.png');
  mode = 'ok'; mark = calls.length;
  await evaluate(`${BUTTON('Refresh')}.click()`); await quiet();
  check('after the link is back, Refresh recovers everything', ops(mark).length === 3 && (await text()).includes('Native schematic FIXTURE_OTHER/inv') && !(await text()).includes('cannot be reached'), ops(mark).join(' | '));

  // ---- an older backend (no /api/virtuoso/cells): the cell can still be typed ----------------------------------------------
  mode = 'outdated'; mark = calls.length;
  await evaluate(`${BUTTON('Refresh')}.click()`); await quiet();
  check('an older backend is named as the reason', (await text()).includes('older than the page'));
  check('the cell can then be typed and read with a button', (await evaluate(`${FIELD('Cell')}.tagName`)) === 'INPUT' && !!(await evaluate(`!!(${BUTTON('Read native schematic')})`)));
  mark = calls.length;
  await evaluate(`${BUTTON('Read native schematic')}.click()`); await quiet();
  check('that button reads once', JSON.stringify(ops(mark)) === JSON.stringify(['read FIXTURE_OTHER inv']) && (await text()).includes('Native schematic FIXTURE_OTHER/inv'), ops(mark).join(' | '));

  // ---- the two labels explain themselves -----------------------------------------------------------------------------------------
  check('Circuit class and PDK id are explained', !!(await evaluate(`!!(${LABEL('Circuit class')})`)) && (await text()).includes('labels saved with every run')
    && (await evaluate(`${LABEL('PDK id')}.title`)).includes('process design kit'));

  // ---- the limit is explained in plain words; circuits that already have a profile are NOT suggested here (user, 2026-09-22:
  //      "if I work with previous tasks I would choose registered tasks") -----------------------------------------------------------
  check('the limit is a neutral note in plain words, not a red box', (await evaluate(`!!${PANEL}.querySelector('.note') && !${PANEL}.querySelector('.blocker')`))
    && (await text()).includes('cannot optimize it yet') && (await text()).includes('circuit profile'));
  const offered = (await evaluate(`[...${PANEL}.querySelectorAll('.note button')].map(b => b.textContent)`)).filter(name => name.startsWith('real:'));
  check('the note does not suggest the existing real:* tasks', offered.length === 0 && !(await text()).includes('have a profile today'), offered.join(', '));
  check('it still offers the way forward for THIS cell', !!(await evaluate(`!!(${BUTTON('Read this cell into the workbench')})`)));

  check('every question on screen was planned by this check', dialogs.every(d => d.planned), JSON.stringify(dialogs.filter(d => !d.planned)));
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
