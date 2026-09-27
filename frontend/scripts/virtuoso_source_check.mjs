// Browser check of the Virtuoso cellview import in its WINDOW and of the left column that keeps only the registered task
// (user request 2026-09-23; there is no frontend test runner). Same approach as connection_panel_check.mjs: a throwaway
// headless Edge over the DevTools protocol against a workbench page (default http://127.0.0.1:8765/; GATOR_WORKBENCH_URL for
// a preview of a temporary build). EVERY request to /api/virtuoso/* is intercepted, logged and answered with a canned
// FIXTURE answer, so Virtuoso is never contacted and the check does not depend on the backend version; any other writing
// request of the page is refused here (reads pass): hermetic.
// What it pins:
//   - the column: Project, Registered task (the Task list), ONE button "Virtuoso cell..." with the text beside it, the labels
//     folded into one line; no Source list, no library / cell boxes, no Virtuoso note in the column;
//   - the window: opening it lists the libraries (no button), a library its cells, a cell its schematic, one request per step
//     and in that order; no view is asked for; the PDK id is offered from the technology library;
//   - reading a cell ASKS whether it is a copy the user made (window.confirm): Cancel reads nothing, OK reads it with
//     `work_here` and the cell becomes the one the flow works in - the window says so; no "Make a working copy" anywhere;
//     a cell without a testbench is refused in words; reading it again asks nothing;
//   - Save task (no Save as) from the window's cell, the task then in the column; Check now / Record in its block, Delete task in the task row;
//     a cell that already has a task, a built-in cell; a blocked gate and an older backend are readable.
// Needs a configured connection profile (the page selects the active one; reading the profiles probes nothing).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/virtuoso_source_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('virt');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const LIBRARIES = ['FIXTURE_DESIGNS', 'FIXTURE_OTHER', 'analogLib'];
const CELLS = {
  FIXTURE_DESIGNS: { technology_library: 'gpdk045', cells: [
    { name: 'ota5_v1', views: ['maestro', 'schematic', 'symbol'], has_schematic: true },
    { name: 'ota5_tb', views: ['schematic'], has_schematic: true },
    { name: 'vco_fixture', views: ['schematic', 'symbol'], has_schematic: true },           // stands for the cell of a verified built-in circuit (the OTA7 since the VCO task was withdrawn, 7.73)
    { name: 'symbol_only', views: ['symbol'], has_schematic: false }] },
  FIXTURE_OTHER: { technology_library: 'otherTech', cells: [{ name: 'inv', views: ['schematic', 'symbol'], has_schematic: true }] },
};
const schematic = (library, cell) => ({ source: 'virtuoso', library, cell, origin: 'FIXTURE', instance_count: 2, nets: ['in', 'out'],
  instances: ['M0', 'M1'].map(name => ({ instance_path: name, master: { library: 'gpdk045', cell: 'nmos1v', view: 'symbol' }, terminals: [], parameters: { w: { raw: '1u' } } })),
  requires_confirmation: ['FIXTURE'], note: 'FIXTURE' });
const imported = new Map();                                                         // "library/cell" -> the testbench it was read through
const declared = new Set();                                                         // "library/cell" the user declared a copy (work_here)
const created = new Set();                                                          // "library/cell" of tasks saved in this check
const record = (library, cell) => ({ format: 'gator-working-copy-1', declared: true, verified: true, problems: [], created_utc: '2026-09-23T10:00:00+00:00',
  copy: { library, cell, testbench: imported.get(`${library}/${cell}`), path: null }, original: { library, cell, testbench: imported.get(`${library}/${cell}`) } });
const draft = (library, cell) => ({ loaded: true, task_key: `virtuoso:${library}/${cell}`, mock: false, native_draft: true, complete: true, diagnostics: [],
  profile_task: created.has(`${library}/${cell}`) ? `real:${cell}` : null, profile_task_generated: created.has(`${library}/${cell}`) ? true : null,
  working_copy: declared.has(`${library}/${cell}`) ? record(library, cell) : null,
  circuit: { library, cell, native_draft: true, testbench_cell: imported.get(`${library}/${cell}`) ?? null }, hierarchy: { XU1: { M1: {}, M2: {} }, V0: {} }, analysis_context: null,
  evaluation_backend: null, max_concurrency: 1, testbench_probes: null,
  summary: { device_count: 3, unknown_devices: [], devices: [{ instance_path: 'XU1/M1', kind: 'nmos', parameters: { w: { value: 4e-6 } } }] },
  notes: ['FIXTURE: read from Virtuoso (canned answer).'] });
const ROWS = [{ variable_id: 'wn_fixture', instance_path: 'XU1/M1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005,
  target_kind: 'instance_parameter', value_type: 'continuous', scale: 'linear', relation: 'ratio', ratio: 1, name: '', notes: '' }];
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: false, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { M1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: ['FIXTURE: generated profile.'] });
const builtInCell = { loaded: false, blocker: 'FIXTURE: a native cellview needs a verified circuit profile', interface_contract: null,
  profile_task: 'real:gpdk045_ota7', profile_task_generated: false };
const browseOnly = { loaded: false, blocker: 'FIXTURE: a native cellview needs a verified circuit profile', interface_contract: null, profile_task: null,
  profile_task_generated: null, working_copy: null };
const gateBlocked = { message: 'The connection gate blocked reading the native design', gate: { allowed: false, status: 'blocked', blocking: ['tunnel'], uncertain: [] } };

try {
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, fulfil } = page;
  const calls = []; let mode = 'ok'; let inFlight = 0, overlap = false;
  let agentRequests = 0; let baselineExists = false; let baselineRecorded = false; let deleteRefused = true;
  const dialogs = []; const answers = [];                                           // confirm(): answered as planned; an unplanned one is refused and reported
  const answer = async ({ requestId, request }) => {
    const pathname = new URL(request.url).pathname;
    if (pathname === '/api/agent/propose') { agentRequests++; return fulfil(requestId, 418, { detail: { message: 'FIXTURE: no agent request is expected' } }); }
    if (pathname === '/api/tasks') {                                                 // the real list + the tasks saved in this check
      const real = await (await fetch(new URL('api/tasks', APP))).json();
      return fulfil(requestId, 200, { ...real, tasks: [...real.tasks, ...[...created].map(key => ({ task_key: `real:${key.split('/')[1]}`, kind: 'real', available: true, generated: true }))] });
    }
    if (pathname === '/api/tasks/starter') {                                         // a task saved in this check brings the rows it registered
      const task = new URL(request.url).searchParams.get('task_key');
      return [...created].some(key => task === `real:${key.split('/')[1]}`)
        ? fulfil(requestId, 200, { project: { name: 'fixture-profile', task_name: task.replace('real:', '') }, parameters: ROWS, targets: [], measurements: [], run: {} })
        : send('Fetch.continueRequest', { requestId });
    }
    if (pathname === '/api/circuit/load') {                                          // an imported cell loads from the backend's export
      const circuit = JSON.parse(request.postData ?? '{}').circuit ?? {};
      if (circuit.source === 'registered_task' && [...created].some(key => circuit.task_id === `real:${key.split('/')[1]}`)) return fulfil(requestId, 200, { ...generated(circuit.task_id), baseline_recorded: baselineRecorded });
      if (circuit.source !== 'virtuoso') return send('Fetch.continueRequest', { requestId });
      if (circuit.cell === 'vco_fixture') return fulfil(requestId, 200, builtInCell);
      return fulfil(requestId, 200, imported.has(`${circuit.library}/${circuit.cell}`) ? draft(circuit.library, circuit.cell) : browseOnly);
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
    if (op === 'task/check') return fulfil(requestId, 200, { consistency_check: true, task: body.config?.circuit?.task_id, revision: 1, ok: true, simulated: false,
      steps: [['editors', 'The editors hold the rows of the saved task'], ['connect', 'The run adapter reaches the working copy'],
        ['export', 'The netlist Virtuoso exports from the working copy matches the saved task'], ['deck', 'The simulation deck is written (not run)']]
        .map(([step, title]) => ({ step, ok: true, title, detail: `FIXTURE: ${step} passed` })) });
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
    if (op === 'task/save') {
      if (body.name === 'refuse_me') return fulfil(requestId, 409, { detail: { message: 'FIXTURE: the real backend can only change transistor widths', code: 'refused' } });
      if (!body.extras?.expected_frequency_hz) return fulfil(requestId, 409, { detail: { code: 'needs_expected_frequency',
        message: 'The ring-oscillator measurement needs a rough expected oscillation frequency: it sizes the transient (60 periods, measured after 20). Give it once; the task file keeps it.' } });
      created.add(`${body.library}/${body.cell}`);
      const cell = { library: body.library, cell: body.cell, testbench: 'ota5_tb' };                      // the task runs in the cell the user declared
      return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, revision: 1, created: true, runnable: true, circuit_class: 'vco', pdk_id: 'gpdk045',
        measurement: { kind: 'ring_oscillator', expected_frequency_hz: body.extras.expected_frequency_hz }, parameters: ROWS, copy: { ...cell, path: null }, original: cell });
    }
    if (op === 'copy') return fulfil(requestId, 409, { detail: { code: 'copies_not_made', message: 'FIXTURE: the workbench no longer makes copies' } });
    if (op === 'import') {
      if (body.work_here && !body.testbench) return fulfil(requestId, 409, { detail: { code: 'refused', message: 'Choose the cell\'s Testbench cell first: the task simulates the testbench and keeps its Maestro setup there.' } });
      imported.set(`${body.library}/${body.cell}`, body.testbench ?? null);
      if (body.work_here) declared.add(`${body.library}/${body.cell}`);
      return fulfil(requestId, 200, { library: body.library, cell: body.cell, testbench_cell: body.testbench, device_count: 3, ...(body.work_here ? { working_copy: record(body.library, body.cell) } : {}) });
    }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
  const onDialog = session => session.on('Page.javascriptDialogOpening', p => {
    const accept = answers.length ? answers.shift() : null;
    dialogs.push({ message: p.message, planned: accept !== null });
    return session.send('Page.handleJavaScriptDialog', { accept: !!accept });
  });
  onDialog(page);
  // ---- the column ------------------------------------------------------------------------------------------------------
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Registered task'))`;
  const LABEL = label => `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})`;
  const FIELD = label => `${LABEL(label)}?.querySelector('input, select')`;
  const BUTTON = text => `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const LAUNCH = `${PANEL}.querySelector('button.virtuoso-button')`;
  const text = () => evaluate(`${PANEL}.textContent`);
  const value = label => evaluate(`${FIELD(label)}.value`);
  const choose = (label, v) => page.setValue(`${FIELD(label)}`, v);
  const type = async (label, textToType) => {                                       // the labels sit in a folded line: open it, then type
    await evaluate(`(() => { const d = ${PANEL}.querySelector('details.labels'); if (!d.open) d.querySelector('summary').click(); const i = ${FIELD(label)}; i.focus(); i.select(); })()`);
    await send('Input.insertText', { text: textToType });
  };
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')`);
  // Save task, Task file and their messages live in the editors (tab line + under the toolbar) of the main page.
  const TASK = `document.querySelector('.editors')`;
  const TASK_BUTTON = t => `[...${TASK}.querySelectorAll('.task-save button, .task-notes button')].find(b => b.textContent.trim() === ${JSON.stringify(t)})`;
  const TASK_LABEL = label => `[...${TASK}.querySelectorAll('.task-save label, .task-notes label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})`;
  const taskText = () => evaluate(`[...${TASK}.querySelectorAll('.task-save, .task-notes')].map(e => e.textContent).join(' ')`);
  const typeTask = async (label, textToType) => { await evaluate(`(() => { const i = ${TASK_LABEL(label)}.querySelector('input'); i.focus(); i.select(); })()`); await send('Input.insertText', { text: textToType }); };
  const ops = (from = 0) => calls.slice(from).map(c => [c.op, c.library, c.cell, c.testbench, c.name, c.work_here ? 'work_here' : null].filter(Boolean).join(' '));
  const quiet = async (ms = 1500) => { let seen = -1; while (seen !== calls.length || inFlight) { seen = calls.length; await sleep(ms); } };
  const shotColumn = async name => {
    await evaluate(`${PANEL}.scrollIntoView({ block: 'start' })`); await sleep(200);
    await page.shot(path.join(out, name), `document.querySelector('.left')`, { scale: 2, maxHeight: 1400 });
  };
  // ---- the window: a second page, found by its title, with a DevTools session of its own -------------------------------
  const windowTarget = present => browser.window('GATOR - Virtuoso cell', { present, except: page.target.id });
  let far = null, farPage = null;
  const WIN = `document.querySelector('.virtuoso-window')`;
  const openWindow = async () => {
    await evaluate(`${LAUNCH}.click()`, true);
    farPage = await windowTarget(true);
    far = await browser.attach(farPage, { errors: consoleErrors, prefix: 'window: ' });
    await far.send('Page.enable'); onDialog(far);
    await far.send('Emulation.setDeviceMetricsOverride', { width: 720, height: 980, deviceScaleFactor: 1, mobile: false });   // a headless popup ignores the requested size
    for (let i = 0; i < 50 && !(await far.evaluate(`!!(${WIN})`)); i++) await sleep(100);
    await sleep(400);
  };
  const wText = () => far.evaluate(`${WIN}.textContent`);
  const wLabel = label => `[...${WIN}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})`;
  const wField = label => `${wLabel(label)}?.querySelector('input, select')`;
  const wButton = t => `[...${WIN}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(t)})`;
  const wValue = label => far.evaluate(`${wField(label)}.value`);
  const wOptions = label => far.evaluate(`[...${wField(label)}.options].map(o => ({ value: o.value, text: o.textContent.trim(), disabled: o.disabled }))`);
  const wChoose = (label, v) => far.setValue(`${wField(label)}`, v);
  const wPress = t => far.evaluate(`${wButton(t)}.click()`, true);
  const wHas = t => far.evaluate(`!!(${wButton(t)})`);
  const wShown = selector => far.evaluate(`(() => { const e = ${WIN}.querySelector(${JSON.stringify(selector)}); return !!e && e.checkVisibility(); })()`);
  const shotWindow = name => far.shot(path.join(out, name), WIN, { scale: 2, maxHeight: 1600, beyond: true });

  await page.intercept(['*/api/virtuoso/*', '*/api/circuit/load', '*/api/agent/propose', '*/api/tasks', '*/api/tasks/starter*'], answer, { others: 'read', connection: 'lab' });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  // The connection in use is named on the one "Connection" button of the left column (its window is not needed here).
  for (let i = 0; i < 60 && !(await evaluate(`/\\S/.test(document.querySelector('.left button.connection-button .connection-button-what')?.textContent.replace(/none (selected|set up yet)/, '') ?? '')`)); i++) await sleep(100);
  await sleep(800);
  check('nothing is read from Virtuoso when the page opens', calls.length === 0, ops().join(' | '));

  // ---- the column holds the registered task only --------------------------------------------------------------------------
  const headings = await evaluate(`[...document.querySelectorAll('.left h3')].map(h => h.textContent.trim()).filter(h => !h.startsWith('Hierarchy ('))`);   // the Hierarchy fold's line is an h3 too
  check('the column\'s headings are Project and Registered task - no "Circuit source"', JSON.stringify(headings) === JSON.stringify(['Project', 'Registered task']), headings.join(' | '));
  check('no Source list, no Library / Cell / Testbench boxes in the column', !(await evaluate(`!!(${LABEL('Source')}) || !!(${LABEL('Library')}) || !!(${LABEL('Cell')}) || !!(${LABEL('Testbench cell')})`)));
  check('the Task list is there, on the MOCK task', (await value('Task')) === 'synthetic:gpdk045_ota5', await value('Task'));
  const launcher = await evaluate(`(() => { const b = ${LAUNCH}; const row = b?.closest('.row'); return b ? { caption: b.textContent.trim(), beside: row.querySelector('.hint')?.textContent.trim() } : null; })()`);
  check('ONE short button "Virtuoso cell..." with what it is for as text beside it', !!launcher && launcher.caption === 'Virtuoso cell...' && launcher.beside === 'From a cell you copied in Virtuoso:', JSON.stringify(launcher));
  check('the labels are one folded line naming their values', await evaluate(`(() => { const d = ${PANEL}.querySelector('details.labels'); return !!d && !d.open && /^Labels: class \\w+, PDK \\w+/.test(d.querySelector('summary').textContent.trim()); })()`),
    await evaluate(`${PANEL}.querySelector('details.labels summary')?.textContent`));
  check('Circuit class and PDK id are explained', !!(await evaluate(`!!(${LABEL('Circuit class')})`)) && (await text()).includes('labels saved with every run')
    && (await evaluate(`${LABEL('PDK id')}.title`)).includes('process design kit'));
  await shotColumn('virtuoso-0-column.png');

  // ---- opening the window lists the libraries: no button ------------------------------------------------------------------
  await openWindow(); await quiet();
  check('the button opens a window of its own, titled "GATOR - Virtuoso cell", with the heading "Virtuoso cell"', !!farPage && farPage.title === 'GATOR - Virtuoso cell'
    && (await far.evaluate(`${WIN}.querySelector('h2')?.textContent`)) === 'Virtuoso cell');
  check('opening the window lists the libraries by itself, once', JSON.stringify(ops()) === JSON.stringify(['libraries']), ops().join(' | '));
  check('there is no "List libraries" button', !(await wHas('List libraries')));
  check('the Library dropdown offers what Virtuoso answered', JSON.stringify((await wOptions('Library')).slice(1).map(o => o.value)) === JSON.stringify(LIBRARIES), JSON.stringify(await wOptions('Library')));
  check('the Cell dropdown waits for a library', await far.evaluate(`${wField('Cell')}.disabled`) && (await wOptions('Cell'))[0].text === '(choose a library first)');
  check('no view is asked for', !(await far.evaluate(`!!(${wLabel('View')})`)));
  check('the window says the page follows the task until a library is chosen; the column still shows the task', await wShown('.follows-task')
    && (await wText()).includes('follows the task synthetic:gpdk045_ota5') && (await value('Task')) === 'synthetic:gpdk045_ota5');
  await shotWindow('virtuoso-1-window-opened.png');

  // ---- a library lists its cells, and the page now follows the Virtuoso cell -------------------------------------------------
  let mark = calls.length;
  await wChoose('Library', 'FIXTURE_DESIGNS'); await quiet();
  check('choosing a library lists its cells, once', JSON.stringify(ops(mark)) === JSON.stringify(['cells FIXTURE_DESIGNS']), ops(mark).join(' | '));
  const cellOptions = await wOptions('Cell');
  check('the Cell dropdown lists them; a cell without a schematic cannot be chosen', cellOptions.length === 5 && cellOptions.find(o => o.value === 'symbol_only')?.disabled === true
    && cellOptions.find(o => o.value === 'symbol_only').text.includes('no schematic view') && cellOptions.find(o => o.value === 'ota5_v1')?.disabled === false, JSON.stringify(cellOptions));
  check('the page follows the Virtuoso source now: the Task list shows none, its text says a cell is being chosen', (await stored())?.circuit?.source === 'virtuoso'
    && (await value('Task')) === '' && (await evaluate(`${FIELD('Task')}.selectedOptions[0]?.textContent`)).includes('a Virtuoso cell is being chosen'), await evaluate(`${FIELD('Task')}.selectedOptions[0]?.textContent`));
  check('the PDK id is offered from the technology library (in the column\'s labels line)', (await value('PDK id')) === 'gpdk045' && (await evaluate(`${PANEL}.querySelector('details.labels summary').textContent`)).includes('PDK gpdk045'), await value('PDK id'));
  check('the testbench dropdown offers the cells that have a schematic', JSON.stringify((await wOptions('Testbench cell')).map(o => o.value)) === JSON.stringify(['', 'ota5_v1', 'ota5_tb', 'vco_fixture']), JSON.stringify(await wOptions('Testbench cell')));

  // ---- a cell reads its schematic ------------------------------------------------------------------------------------
  mark = calls.length;
  await wChoose('Cell', 'ota5_v1'); await quiet();
  check('choosing a cell reads its schematic, once', JSON.stringify(ops(mark)) === JSON.stringify(['read FIXTURE_DESIGNS ota5_v1']), ops(mark).join(' | '));
  check('the schematic is shown as read, in the window', (await wText()).includes('Native schematic FIXTURE_DESIGNS/ota5_v1 (2 instances') && !(await text()).includes('Native schematic'));
  check('the window says which view is read and which others exist', (await wText()).includes('View: schematic') && (await wText()).includes('maestro, symbol'));
  check('the column names the cell beside the button', (await evaluate(`${LAUNCH}.closest('.row').querySelector('.hint').textContent`)) === 'Read from Virtuoso: FIXTURE_DESIGNS/ota5_v1');
  check('browse only, said in the window - not "Blocked"; the copy warning stays in view', (await wText()).includes('Browse only:') && !(await wText()).includes('Blocked:')
    && await wShown('.copy-warning') && (await wText()).includes('Work on a copy, never on your design'));
  check('the warning says why: the cell is written', (await wText()).includes('every run sets device sizes in the cell'));
  await shotWindow('virtuoso-2-cell-read.png');

  // ---- reading the cell INTO the workbench asks whether it is a copy; no testbench = refused in words ------------------------
  check('a chosen cell offers "Read this cell into the workbench"', !(await far.evaluate(`${wButton('Read this cell into the workbench')}.disabled`)) && (await wText()).includes('To start a profile for this cell'));
  mark = calls.length; answers.push(false);
  await wPress('Read this cell into the workbench'); await quiet(800);
  const asked = dialogs[dialogs.length - 1]?.message ?? '';
  check('the press asks whether the cell is a copy the user made, and says what is written where', asked.startsWith('Work in FIXTURE_DESIGNS/ota5_v1 directly?')
    && asked.includes('makes no copy of its own') && asked.includes('sets device sizes in ota5_v1') && asked.includes('COPY you made') && asked.includes('Cancel = read nothing'), asked.slice(0, 160));
  check('"Cancel" reads nothing', ops(mark).length === 0, ops(mark).join(' | '));
  answers.push(true);
  await wPress('Read this cell into the workbench'); await quiet();
  check('"OK" reads the cell with work_here; without a testbench the backend refuses and the window says so', JSON.stringify(ops(mark)) === JSON.stringify(['import FIXTURE_DESIGNS ota5_v1 work_here'])
    && (await wText()).includes('Choose the cell\'s Testbench cell first') && !(await wText()).includes('Not optimizable yet'), ops(mark).join(' | '));
  await wChoose('Testbench cell', 'ota5_tb'); await quiet(600);
  mark = calls.length; answers.push(true);
  await wPress('Read this cell into the workbench'); await quiet();
  check('with the testbench: read through it, with work_here, once', JSON.stringify(ops(mark)) === JSON.stringify(['import FIXTURE_DESIGNS ota5_v1 ota5_tb work_here']), ops(mark).join(' | '));
  check('the cell is then loaded and shown as a draft in the window - the column shows no hierarchy', (await wText()).includes('Read from Virtuoso. Not optimizable yet') && (await wText()).includes('Hierarchy (3 instances)')
    && !(await text()).includes('Hierarchy (') && !(await wText()).includes('Browse only'));
  check('the window says the cell itself is worked in, as declared; no "Make a working copy" anywhere', await wShown('.declared') && (await wText()).includes('Working in FIXTURE_DESIGNS/ota5_tb directly: you declared it a copy you made')
    && !(await wHas('Make a working copy')) && !(await evaluate(`!!(${BUTTON('Make a working copy')})`)));
  check('one button "Read setup", and "Ask the agent to set up" can be pressed', await wHas('Read setup') && !(await far.evaluate(`${wButton('Ask the agent to set up')}.disabled`)));
  await shotWindow('virtuoso-2b-draft.png');
  mark = calls.length;
  await wPress('Read the cell again'); await quiet();
  check('"Read the cell again" asks nothing and sends no work_here: the cell is declared already', JSON.stringify(ops(mark)) === JSON.stringify(['import FIXTURE_DESIGNS ota5_v1 ota5_tb'])
    && dialogs.length === 3, `${ops(mark).join(' | ')} / ${dialogs.length} dialog(s)`);
  await wPress('Ask the agent to set up'); await sleep(800);
  const box = await evaluate(`document.querySelector('footer textarea')?.value ?? ''`);
  check('"Ask the agent to set up" opens the Agent tab of the workbench with the request written out', box.includes('which sizes to vary') && box.includes('what it is') && box.includes('working copy'), box.slice(0, 80));
  check('nothing was sent to the agent by itself', agentRequests === 0, `${agentRequests} request(s)`);

  // ---- Save task from the window's cell: refused in words, asks the frequency once, then the task opens in the column ---------
  check('no Create profile form, no Save as', !(await wHas('Create profile')) && !(await far.evaluate(`!!(${wLabel('Circuit type')})`)) && !(await evaluate(`!!(${TASK_BUTTON('Save as')})`)));
  check('"Save task" is offered in the editors\' tab line once the cell is declared', !(await evaluate(`${TASK_BUTTON('Save task')}.disabled`)) && (await wText()).includes('Then save it as a task'));
  await typeTask('New task name', 'refuse_me'); await sleep(300);
  mark = calls.length;
  await evaluate(`${TASK_BUTTON('Save task')}.click()`); await quiet();
  check('a refusal is shown in its own words and nothing changes', JSON.stringify(calls.slice(mark).map(c => [c.op, c.name, c.library, c.cell])) === JSON.stringify([['task/save', 'refuse_me', 'FIXTURE_DESIGNS', 'ota5_v1']])
    && (await taskText()).includes('can only change transistor widths') && (await stored()).circuit.source === 'virtuoso', JSON.stringify(calls.slice(mark)));
  await evaluate(`(() => { const i = ${TASK_LABEL('New task name')}.querySelector('input'); i.focus(); i.select(); })()`); await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 }); await sleep(300);
  mark = calls.length;
  await evaluate(`${TASK_BUTTON('Save task')}.click()`); await quiet();
  check('an empty name falls back to the cell name; the ring oscillator\'s frequency is then asked once', calls.slice(mark).map(c => c.name).join() === 'ota5_v1'
    && (await taskText()).includes('needs a rough expected oscillation frequency') && !!(await evaluate(`!!(${TASK_LABEL('Rough oscillation frequency')})`)), JSON.stringify(calls.slice(mark)));
  await typeTask('Rough oscillation frequency', '1.2G'); await sleep(300);
  mark = calls.length;
  await evaluate(`[...${TASK}.querySelectorAll('.task-notes button')].find(b => b.textContent.trim() === 'Save task').click()`); await quiet();
  check('1.2G = 1.2e9 Hz is sent with the rows, never as_new', calls.slice(mark).length === 1 && calls[mark].extras?.expected_frequency_hz === 1.2e9 && calls[mark].as_new === false
    && Array.isArray(calls[mark].config?.parameters), JSON.stringify(calls.slice(mark)));
  check('the new task is opened in the column', (await stored()).circuit.source === 'registered_task' && (await value('Task')) === 'real:ota5_v1', await value('Task'));
  check('the column says what happened, in which cell, and what comes first', (await text()).includes('Saved the new task real:ota5_v1') && (await text()).includes('the cell you declared as your copy')
    && (await text()).includes('Single baseline simulation'));
  check('the parameter editor shows the rows as saved', await evaluate(`document.querySelector('main').innerHTML.includes('wn_fixture')`));
  check('the open task offers Save task and Task file - no Save as', await evaluate(`!!(${TASK_BUTTON('Save task')}) && !!(${TASK_BUTTON('Task file')}) && !(${TASK_BUTTON('Save as')})`));
  check('the window now says it follows the task and starts from a blank library', await wShown('.follows-task') && (await wText()).includes('follows the task real:ota5_v1') && (await wValue('Library')) === '');
  await shotColumn('virtuoso-2c-task-saved.png');
  // ---- before every run: the check Start runs by itself, pressed on its own; and recording a finished baseline -----------
  check('"Check now" is in the column with "Before every run:"', !!(await evaluate(`!!(${BUTTON('Check now')})`)) && (await text()).includes('Before every run:'));
  mark = calls.length;
  await evaluate(`${BUTTON('Check now')}.click()`); await quiet();
  check('the check is one request with this connection and the editors\' rows', JSON.stringify(calls.slice(mark).map(c => [c.op, c.profile_id, c.config?.circuit?.task_id])) === JSON.stringify([['task/check', 'lab', 'real:ota5_v1']])
    && Array.isArray(calls[mark]?.config?.parameters), JSON.stringify(calls.slice(mark)).slice(0, 200));
  const shownCheck = await text();
  check('its steps and the verdict are shown', ['passed: The editors hold the rows of the saved task', 'passed: The netlist Virtuoso exports from the working copy matches',
    'agree. Nothing was simulated.'].every(t => shownCheck.includes(t)), shownCheck.slice(shownCheck.indexOf('Check now'), shownCheck.indexOf('Check now') + 300));
  await evaluate(`${BUTTON('Record the baseline run as reference')}.click()`); await quiet();
  check('without a baseline run, recording says what to do first', (await text()).includes('Run "Single baseline simulation" first'));
  baselineExists = true;
  await evaluate(`${BUTTON('Record the baseline run as reference')}.click()`); await quiet();
  check('with one, the baseline is recorded and said so', (await text()).includes('Baseline recorded from run fixture-run-1'));
  // ---- a cell that already has a registered task says so in the window: no second task, one short "Open" ---------------------
  mark = calls.length;
  await wChoose('Library', 'FIXTURE_DESIGNS'); await quiet();
  await wChoose('Cell', 'ota5_v1'); await quiet();
  let shown = await wText();
  check('the cell is no longer browse-only: the window names its task', shown.includes('This cell already has a registered task: real:ota5_v1') && !shown.includes('built-in')
    && !shown.includes('Not optimizable yet') && !shown.includes('Browse only'), ops(mark).join(' | '));
  check('no second draft is offered for it', !(await evaluate(`!!(${TASK_BUTTON('Save task')})`)) && !(await wHas('Read the cell again')) && !(await wHas('Read this cell into the workbench')));
  check('the button is short; the task name is text beside it', JSON.stringify(await far.evaluate(`[...${WIN}.querySelectorAll('.note button')].map(b => b.textContent.trim())`)) === JSON.stringify(['Open']));
  await shotWindow('virtuoso-2d-cell-has-task.png');
  await wChoose('Cell', 'vco_fixture'); await quiet();
  shown = await wText();
  check('the cell of a verified built-in circuit names that task', shown.includes('This cell already has a registered task: real:gpdk045_ota7 (a verified built-in circuit)')
    && !shown.includes('Browse only') && !shown.includes('cannot optimize it yet'));
  check('it is not offered for reading or for a task', !(await wHas('Read this cell into the workbench')) && !(await evaluate(`!!(${TASK_BUTTON('Save task')})`)));
  check('what that means is one folded line', await far.evaluate(`(() => { const d = [...${WIN}.querySelectorAll('.note details')].find(x => x.querySelector('summary').textContent === 'What this means');
    return !!d && !d.open && d.textContent.includes('gets no second task'); })()`));
  await wPress('Open'); await quiet();
  check('"Open" chooses the task in the column', (await stored()).circuit.source === 'registered_task' && (await value('Task')) === 'real:gpdk045_ota7', await value('Task'));
  check('a built-in circuit has no Delete task', !(await evaluate(`!!(${BUTTON('Delete task')})`)));

  // ---- Delete task: asked once more, refused while a run works, then back at the cell with Save task -----------------------
  await wChoose('Library', 'FIXTURE_DESIGNS'); await quiet();
  await wChoose('Cell', 'ota5_v1'); await quiet();
  await wPress('Open'); await quiet();
  check('the saved task is opened from its cell', (await value('Task')) === 'real:ota5_v1', await value('Task'));
  // Since 2026-09-24 (status record 7.78) Delete task stands in the task row at the top of the column, at the right end,
  // next to "Load task" (was: Load starter configuration); what it does is its tooltip.
  const taskRow = await evaluate(`(() => { const d = ${BUTTON('Delete task')}, l = ${BUTTON('Load task')}; if (!d || !l) return 'missing';
    return d.closest('.row.task-buttons') === l.closest('.row.task-buttons') && d.getBoundingClientRect().left > l.getBoundingClientRect().right
      && Math.abs(d.getBoundingClientRect().top - l.getBoundingClientRect().top) < 4 ? 'ok' : 'elsewhere'; })()`);
  check('"Delete task" stands at the right of "Load task", in the task row', taskRow === 'ok', taskRow);
  check('the task row is the only place: the block does not say "To start over from the cell" any more', !(await text()).includes('To start over from the cell'));
  mark = calls.length; answers.push(false);
  await evaluate(`${BUTTON('Delete task')}.click()`); await quiet(800);
  const askedDelete = dialogs[dialogs.length - 1]?.message ?? '';
  check('the press asks once more and says what goes', askedDelete.includes('Delete the task real:ota5_v1?') && askedDelete.includes('can no longer be resumed') && askedDelete.includes('copy of the task')
    && askedDelete.includes('recorded baseline goes with it'), askedDelete.slice(0, 120));
  check('"Cancel" deletes nothing', ops(mark).length === 0 && (await value('Task')) === 'real:ota5_v1', ops(mark).join(' | '));
  answers.push(true);
  await evaluate(`${BUTTON('Delete task')}.click()`); await quiet();
  check('a refusal is shown in its own words and the task stays', JSON.stringify(ops(mark)) === JSON.stringify(['profile/delete ota5_v1']) && (await text()).includes('is working right now')
    && (await value('Task')) === 'real:ota5_v1', ops(mark).join(' | '));
  deleteRefused = false; mark = calls.length; answers.push(true);
  await evaluate(`${BUTTON('Delete task')}.click()`); await quiet();
  shown = await text();
  check('deleting is one request', JSON.stringify(ops(mark).filter(o => o.startsWith('profile'))) === JSON.stringify(['profile/delete ota5_v1']), ops(mark).join(' | '));
  check('the page goes back to the cell the task was saved from: the column names it, the window shows it', (await stored()).circuit.source === 'virtuoso'
    && (await evaluate(`${LAUNCH}.closest('.row').querySelector('.hint').textContent`)) === 'Read from Virtuoso: FIXTURE_DESIGNS/ota5_v1'
    && (await wValue('Library')) === 'FIXTURE_DESIGNS' && (await wValue('Cell')) === 'ota5_v1' && (await wValue('Testbench cell')) === 'ota5_tb', `${await wValue('Library')} / ${await wValue('Cell')} / ${await wValue('Testbench cell')}`);
  check('the column says what happened; where the files went is one folded line', shown.includes('Task real:ota5_v1 deleted.')
    && await evaluate(`(() => { const d = [...${PANEL}.querySelectorAll('details')].find(x => x.querySelector('summary').textContent === 'Where its files went');
      return !!d && !d.open && d.textContent.includes('/fixture/profiles/.deleted/ota5_v1'); })()`));
  check('the cell offers Save task again', !!(await evaluate(`!!(${TASK_BUTTON('Save task')})`)) && (await wText()).includes('Not optimizable yet') && !(await wText()).includes('already has a registered task'));
  check('the task left the Registered task list', !(await evaluate(`(async () => (await (await fetch('/api/tasks')).json()).tasks.some(t => t.task_key === 'real:ota5_v1'))()`)));
  await shotColumn('virtuoso-2g-profile-deleted.png');

  // ---- another library: the cell is forgotten, a typed PDK id is kept -----------------------------------------------
  await type('PDK id', 'my_pdk'); await sleep(300);
  mark = calls.length;
  await wChoose('Library', 'FIXTURE_OTHER'); await quiet();
  check('another library lists its own cells and reads nothing yet', JSON.stringify(ops(mark)) === JSON.stringify(['cells FIXTURE_OTHER']), ops(mark).join(' | '));
  check('the cell of the old library is forgotten and its schematic is gone', (await wValue('Cell')) === '' && !(await wText()).includes('Native schematic'));
  check('a typed PDK id is not overwritten', (await value('PDK id')) === 'my_pdk', await value('PDK id'));

  // ---- Refresh repeats the chain, one call after the other -------------------------------------------------------------
  await wChoose('Cell', 'inv'); await quiet();
  mark = calls.length; overlap = false;
  await wPress('Refresh'); await quiet();
  check('Refresh reads libraries, cells and schematic again, in that order', JSON.stringify(ops(mark)) === JSON.stringify(['libraries', 'cells FIXTURE_OTHER', 'read FIXTURE_OTHER inv']), ops(mark).join(' | '));
  check('never two bridge calls at once', !overlap);

  // ---- the link is down: readable, and Refresh recovers ------------------------------------------------------------------
  mode = 'blocked'; mark = calls.length;
  await wPress('Refresh'); await quiet();
  check('a blocked gate stops the chain at the first step', JSON.stringify(ops(mark)) === JSON.stringify(['libraries']), ops(mark).join(' | '));
  check('and says what to do', (await wText()).includes('Virtuoso cannot be reached (tunnel)') && (await wText()).includes('Connection window'));
  check('the configured library stays visible while nothing can be listed', (await wValue('Library')) === 'FIXTURE_OTHER');
  await shotWindow('virtuoso-3-link-down.png');
  mode = 'ok'; mark = calls.length;
  await wPress('Refresh'); await quiet();
  check('after the link is back, Refresh recovers everything', ops(mark).length === 3 && (await wText()).includes('Native schematic FIXTURE_OTHER/inv') && !(await wText()).includes('cannot be reached'), ops(mark).join(' | '));

  // ---- an older backend (no /api/virtuoso/cells): the cell can still be typed ----------------------------------------------
  mode = 'outdated'; mark = calls.length;
  await wPress('Refresh'); await quiet();
  check('an older backend is named as the reason', (await wText()).includes('older than the page'));
  check('the cell can then be typed and read with a button', (await far.evaluate(`${wField('Cell')}.tagName`)) === 'INPUT' && await wHas('Read native schematic'));
  mark = calls.length;
  await wPress('Read native schematic'); await quiet();
  check('that button reads once', JSON.stringify(ops(mark)) === JSON.stringify(['read FIXTURE_OTHER inv']) && (await wText()).includes('Native schematic FIXTURE_OTHER/inv'), ops(mark).join(' | '));

  // ---- the limit is explained in plain words; circuits that already have a task are NOT suggested (user, 2026-09-22) --------
  check('the limit is a neutral note in plain words, not a red box', (await far.evaluate(`!!${WIN}.querySelector('.note') && !${WIN}.querySelector('.blocker')`))
    && (await wText()).includes('cannot optimize it yet') && (await wText()).includes('circuit profile'));
  const offered = (await far.evaluate(`[...${WIN}.querySelectorAll('.note button')].map(b => b.textContent)`)).filter(name => name.startsWith('real:'));
  check('the note does not suggest the existing real:* tasks', offered.length === 0 && !(await wText()).includes('have a profile today'), offered.join(', '));
  check('it still offers the way forward for THIS cell', await wHas('Read this cell into the workbench'));

  // ---- closing the window loses nothing; the column keeps following the cell ----------------------------------------------------
  await far.send('Target.closeTarget', { targetId: farPage.id }).catch(() => undefined);
  await windowTarget(false); await sleep(500);
  check('closing the window keeps the page on the cell; the column names it and offers the window again', (await stored()).circuit.source === 'virtuoso'
    && (await evaluate(`${LAUNCH}.closest('.row').querySelector('.hint').textContent`)) === 'Read from Virtuoso: FIXTURE_OTHER/inv' && !!(await evaluate(`!!(${LAUNCH})`)));
  await choose('Task', 'synthetic:gpdk045_ota5'); await sleep(1200);
  check('choosing a task in the column makes the page follow it again', (await stored()).circuit.source === 'registered_task' && (await value('Task')) === 'synthetic:gpdk045_ota5');

  check('every question on screen was planned by this check', dialogs.every(d => d.planned), JSON.stringify(dialogs.filter(d => !d.planned)));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
} catch (error) {
  fail(error);
  if (consoleErrors.length) console.log('page errors: ' + consoleErrors.join(' | ').slice(0, 600));
} finally {
  await browser.close();
}
finish();
