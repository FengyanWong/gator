// Browser check of the folded explanations of the Project column and of the Virtuoso window (there is no frontend test
// runner in this project). Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol
// against the RUNNING workbench (default http://127.0.0.1:8765/). EVERY request to /api/virtuoso/* is answered with a canned
// FIXTURE, so Virtuoso is never contacted. GET requests and the two read-only POSTs (circuit load of a registered task,
// static validation) pass through; every other writing request is refused here, so this check can start, save or probe
// nothing on the backend it runs against. The browser profile is new and temporary.
// What it pins (user request 2026-09-21): the long explanations are closed "details" lines like "Instances and parameters"
// - present, but not shown until their line is clicked - while headlines, warnings and every button stay visible;
// "Native schematic" is closed by default and then keeps the state the user gave it. Second request the same day ("hide
// this part"): the whole Hierarchy block is ONE closed line under its own heading, and it keeps the state the user gave it.
// Since 2026-09-23 (user request) the column holds the project and the registered task only - the labels are one folded
// line - and the Virtuoso cell lives in a window of its own behind one button; its notes fold the same way, and the warning
// that the cell itself is written stays in view.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 40 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/project_help_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, reportRefused, runChecks, sleep, TASK_PANEL, VIRTUOSO_WINDOW, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('help');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const LIBRARY = 'FIXTURE_DESIGNS', CELLS = [{ name: 'ring_a', views: ['maestro', 'schematic', 'symbol'], has_schematic: true }, { name: 'ring_b', views: ['schematic'], has_schematic: true },
  { name: 'tb_ring_a', views: ['schematic'], has_schematic: true }];
const schematic = (library, cell) => ({ source: 'virtuoso', library, cell, origin: 'FIXTURE', instance_count: 2, nets: ['in', 'out'],
  instances: ['M0', 'M1'].map(name => ({ instance_path: name, master: { library: 'gpdk045', cell: 'nmos1v', view: 'symbol' }, terminals: [], parameters: { w: { raw: '1u' } } })),
  requires_confirmation: ['FIXTURE'], note: 'FIXTURE' });
const NOTE = 'FIXTURE NOTE: read from Virtuoso (canned answer).';
const imported = new Map();                                                         // "library/cell" -> the testbench it was read through
const draft = (library, cell) => ({ loaded: true, task_key: `virtuoso:${library}/${cell}`, mock: false, native_draft: true, complete: true, diagnostics: [], profile_task: null,
  circuit: { library, cell, native_draft: true, testbench_cell: imported.get(`${library}/${cell}`) ?? null }, hierarchy: { XU1: { M1: {}, M2: {} }, V0: {} },
  working_copy: { declared: true, verified: true, problems: [], created_utc: '2026-09-23T10:00:00+00:00', copy: { library, cell, testbench: `tb_${cell}`, path: null }, original: { library, cell, testbench: `tb_${cell}` } },
  analysis_context: null, evaluation_backend: null, max_concurrency: 1,
  summary: { device_count: 3, unknown_devices: [], devices: [{ instance_path: 'XU1/M1', kind: 'nmos', parameters: { w: { value: 4e-6 } } }] }, notes: [NOTE] });
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: false, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { M1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: [NOTE, 'FIXTURE NOTE: a second one.'] });
const ROWS = [{ variable_id: 'wn_fixture', instance_path: 'XU1/M1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005,
  value_type: 'continuous', scale: 'linear', ratio: 1, notes: '' }];

await runChecks(browser, async () => {
  // The connection profile comes from the configuration: seeded, so the check does not depend on the connection UI.
  const profiles = await (await fetch(new URL('api/connection/profiles', APP))).json().catch(() => ({}));
  const CONFIG = { schema_version: 'gator-workbench-config-v1', project: { name: 'fixture', task_name: 'fixture', notes: '' },
    circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' }, parameters: [], targets: [], measurements: [],
    run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0, connection_profile_id: profiles.active ?? 'fixture' },
    output: { experiment_name: 'fixture' }, research: {} };
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, until, fulfil } = page;
  const calls = []; const refused = []; const created = new Set(); let inFlight = 0; const dialogs = [];
  const answer = async ({ requestId, request }) => {
    const name = new URL(request.url).pathname, body = JSON.parse(request.postData ?? '{}');
    if (name.startsWith('/api/virtuoso/')) {
      const op = name.replace('/api/virtuoso/', '');
      calls.push(op); inFlight++; await sleep(150); inFlight--;
      if (op === 'libraries') return fulfil(requestId, 200, { libraries: [LIBRARY] });
      if (op === 'cells') return fulfil(requestId, 200, { library: body.library, truncated: false, technology_library: 'gpdk045', cells: CELLS });
      if (op === 'read') return fulfil(requestId, 200, schematic(body.library, body.cell));
      if (op === 'import') { imported.set(`${body.library}/${body.cell}`, body.testbench ?? null); return fulfil(requestId, 200, { library: body.library, cell: body.cell, testbench_cell: body.testbench, device_count: 3 }); }
      if (op === 'task/save') { created.add(`real:${body.name}`); return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, revision: 1, created: true, runnable: true,
        circuit_class: 'vco', pdk_id: 'gpdk045', parameters: ROWS, copy: { library: body.library, cell: body.cell, testbench: `tb_${body.cell}`, path: null }, original: { library: body.library, cell: body.cell, testbench: `tb_${body.cell}` } }); }
      return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
    }
    if (name === '/api/circuit/load') {
      const circuit = body.circuit ?? {};
      if (circuit.source === 'registered_task' && created.has(circuit.task_id)) return fulfil(requestId, 200, generated(circuit.task_id));
      if (circuit.source === 'virtuoso' && imported.has(`${circuit.library}/${circuit.cell}`)) return fulfil(requestId, 200, draft(circuit.library, circuit.cell));
      return send('Fetch.continueRequest', { requestId });                         // a registered task, or "no profile yet": read-only on the backend
    }
    if (name === '/api/config/validate') return page.pass(requestId);
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const onDialog = session => session.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return session.send('Page.handleJavaScriptDialog', { accept: true, ...(p.type === 'prompt' ? { promptText: p.defaultPrompt } : {}) }); });
  onDialog(page);
  const PANEL = TASK_PANEL;
  const LAUNCH = `${PANEL}.querySelector('button.virtuoso-button')`;
  const WIN = `document.querySelector('.virtuoso-window')`;
  let far = null;
  const openWindow = async () => {
    far = await browser.popup(page, LAUNCH, VIRTUOSO_WINDOW, { width: 720, height: 2000, ready: WIN, onDialog });   // tall: the whole window on one picture
    await sleep(400);
  };
  // The same questions asked of the column (page session, PANEL) and of the window (far session, WIN).
  const on = (session, ROOT) => {
    const FIELD = label => `[...${ROOT}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})?.querySelector('input, select')`;
    const BUTTON = text => `[...${ROOT}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
    // "present" = in the page at all; "shown" = the innermost element holding the words is really rendered (a closed <details> hides its content).
    const HOLDER = needle => `[...${ROOT}.querySelectorAll('*')].filter(e => e.textContent.includes(${JSON.stringify(needle)}) && ![...e.children].some(c => c.textContent.includes(${JSON.stringify(needle)})))`;
    const present = needle => session.evaluate(`${HOLDER(needle)}.length > 0`);
    const shown = needle => session.evaluate(`${HOLDER(needle)}.some(e => e.checkVisibility())`);
    const folded = async needle => (await present(needle)) && !(await shown(needle));
    const SUMMARY = text => `[...${ROOT}.querySelectorAll('summary')].find(s => s.textContent.trim().startsWith(${JSON.stringify(text)}))`;
    const isOpen = text => session.evaluate(`${SUMMARY(text)}?.parentElement.open`);
    const click = expression => session.evaluate(`${expression}.click()`, true);
    const openLines = () => session.evaluate(`[...${ROOT}.querySelectorAll('details')].filter(d => d.open).map(d => d.querySelector('summary').textContent.trim())`);
    const buttonShown = text => session.evaluate(`!!(${BUTTON(text)}) && ${BUTTON(text)}.checkVisibility()`);
    const choose = (label, v) => session.setValue(`${FIELD(label)}`, v);
    const height = () => session.evaluate(`Math.round(${ROOT}.getBoundingClientRect().height)`);
    return { FIELD, BUTTON, present, shown, folded, SUMMARY, isOpen, click, openLines, buttonShown, choose, height, text: () => session.evaluate(`${ROOT}.textContent`) };
  };
  const quiet = async (ms = 700) => { let seen = -1; while (seen !== calls.length || inFlight) { seen = calls.length; await sleep(ms); } };
  // Save task sits at the right end of the editors' tab line (user request 2026-09-22), not in the column, not in the window.
  const TASK_BAR = `document.querySelector('.editors .tabs .task-save')`;
  const TASK_BUTTON = text => `[...(${TASK_BAR}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const taskButtonShown = text => evaluate(`!!(${TASK_BUTTON(text)}) && ${TASK_BUTTON(text)}.checkVisibility()`);
  const shotColumn = async name => {                          // a tall window, so the whole column is on the picture instead of its visible part
    await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 2600, deviceScaleFactor: 1, mobile: false }); await sleep(250);
    await page.shot(path.join(out, name), PANEL, { pad: 4, scale: 2, maxHeight: 2500 });
    await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  };
  const shotWindow = name => far.shot(path.join(out, name), WIN, { scale: 2, maxHeight: 1900, beyond: true });

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${PANEL}) && ${PANEL}.textContent.includes('Hierarchy (')`, 150))) throw new Error('the Project column never showed a loaded circuit | panel: '
    + (await evaluate(`${PANEL}?.textContent.slice(0, 700) ?? 'no panel'`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  const col = on(page, PANEL);

  // ---- a registered task: nothing is unfolded by itself ----------------------------------------------------------
  check('on page load no line of the column is unfolded', (await col.openLines()).length === 0, (await col.openLines()).join(' | '));
  check('the labels are one closed line naming their values; the boxes and their explanation are folded', await col.shown('Labels: class') && await col.folded('labels saved with every run')
    && !(await evaluate(`${col.FIELD('PDK id')}.checkVisibility()`)));
  check('the MOCK banner stays in view', await col.shown('MOCK evaluation backend'));
  await col.click(col.SUMMARY('Labels: class')); await sleep(200);
  check('a click on the line shows the boxes and the text', await col.shown('labels saved with every run') && await col.isOpen('Labels: class') && await evaluate(`${col.FIELD('PDK id')}.checkVisibility()`));
  await col.click(col.SUMMARY('Labels: class')); await sleep(200);
  check('a second click folds it again', await col.folded('labels saved with every run'));
  check('the Virtuoso cell is ONE button in the column; no library, cell or testbench box here', await col.buttonShown('Virtuoso cell...')
    && !(await evaluate(`!!(${col.FIELD('Library')}) || !!(${col.FIELD('Cell')}) || !!(${col.FIELD('Source')})`)));

  // ---- the whole Hierarchy block is one closed line under its heading -------------------------------------------------
  const HIERARCHY = `${col.SUMMARY('Hierarchy (')}?.parentElement`;
  const TREE = `${HIERARCHY}.querySelector('ul.tree')`;
  check('Hierarchy is ONE closed line that still looks like a heading', (await evaluate(`${HIERARCHY}.open`)) === false && await col.shown('Hierarchy (')
    && await evaluate(`!!${col.SUMMARY('Hierarchy (')}.querySelector('h3') && getComputedStyle(${col.SUMMARY('Hierarchy (')}.querySelector('h3')).display === 'inline'`));
  check('folded inside it: the tree and "Instances and parameters"', await evaluate(`!!${TREE} && !${TREE}.checkVisibility()`) && await col.folded('Instances and parameters'));
  await shotColumn('help-1-registered-task.png');
  await col.click(col.SUMMARY('Hierarchy (')); await sleep(250);
  check('a click opens it: the tree is shown, "Instances and parameters" is a closed line inside it', (await evaluate(`${HIERARCHY}.open`)) === true
    && await evaluate(`${TREE}.checkVisibility()`) && await col.shown('Instances and parameters') && (await col.isOpen('Instances and parameters')) === false);
  await col.click(col.SUMMARY('Instances and parameters')); await sleep(200);
  check('opening the inner line leaves the block open (an inner toggle is not taken for the block\'s own)', (await evaluate(`${HIERARCHY}.open`)) === true && (await col.isOpen('Instances and parameters')) === true);
  await col.click(col.SUMMARY('Instances and parameters')); await sleep(200);
  await shotColumn('help-1b-hierarchy-open.png');                                   // left open: the later states must find it as the user left it

  // ---- the Virtuoso window: browse only ---------------------------------------------------------------------------------
  await openWindow(); await quiet();
  const win = on(far, WIN);
  await win.choose('Library', LIBRARY); await quiet();
  await win.choose('Cell', 'ring_b'); await quiet();                                // a cell without a tb_ of its own: the note asks for one
  check('virtuoso: the three reads happened through fixtures only', JSON.stringify(calls) === JSON.stringify(['libraries', 'cells', 'read']), calls.join(' | '));
  check('browse only: the headline is in view, in the window', await win.shown('Browse only: you can look at this cell here') && !(await col.present('Browse only')));
  check('browse only: what a circuit profile is, is folded under "Why: ..."', await win.shown('Why: it has no circuit profile yet') && await win.folded('a checked description of three things')
    && await win.folded('which testbench simulates the circuit'));
  // The row of real:* shortcut buttons was removed on the user's request (status record 7.40): one folded sentence points to the column instead.
  const offered = await far.evaluate(`[...${WIN}.querySelectorAll('.note button')].filter(b => b.textContent.startsWith('real:')).length`);
  check('browse only: no shortcut buttons to the existing real tasks; where they are is one folded sentence under "Why: ..."', offered === 0
    && await win.folded('Circuits that already have one are under Registered task, in the Project column.'), `${offered} button(s)`);
  check('browse only: the copy warning is NOT folded: the cell itself is written', await win.shown('Work on a copy, never on your design.') && await win.shown('every run sets device sizes in the cell'));
  check('browse only: "Read this cell into the workbench" stays in view, its explanation is folded', await win.buttonShown('Read this cell into the workbench')
    && await win.shown('To start a profile for this cell') && await win.shown('choose its Testbench cell above first') && await win.folded('Read-only, no simulation, some seconds'));
  check('the view remark is one line: "View: schematic"; the reason is folded', await win.shown('View: schematic') && await win.folded('The only view the reader opens'));
  await win.choose('Cell', 'ring_a'); await quiet();
  check('a cell with other views: they are folded too', await win.shown('View: schematic') && await win.folded('maestro, symbol'));
  const before = await win.height();

  // ---- Native schematic: closed by default, then as the user left it --------------------------------------------------------
  const NATIVE = `[...${WIN}.querySelectorAll('details')].find(d => d.querySelector('summary')?.textContent.startsWith('Native schematic'))`;
  check('Native schematic is listed with its cell and instance count', await win.shown(`Native schematic ${LIBRARY}/ring_a (2 instances, as read)`));
  check('browse only: no circuit is loaded, so there is no Hierarchy block in the window and Native schematic stands alone', !(await far.evaluate(`!!(${win.SUMMARY('Hierarchy (')})`)));
  check('Native schematic is CLOSED by default: its table is not shown', (await far.evaluate(`${NATIVE}.open`)) === false && await win.folded('gpdk045/nmos1v') && await win.folded('Requires confirmation'));
  await shotWindow('help-3-virtuoso-browse.png');
  await win.click(`${NATIVE}.querySelector('summary')`); await sleep(250);
  check('a click opens it: the instances are shown', (await far.evaluate(`${NATIVE}.open`)) === true && await win.shown('gpdk045/nmos1v') && (await far.evaluate(`${NATIVE}.querySelectorAll('tbody tr').length`)) === 2);
  await win.choose('Cell', 'ring_b'); await quiet();
  check('another cell: it stays open, as the user left it', (await far.evaluate(`${NATIVE}.open`)) === true && await win.shown(`Native schematic ${LIBRARY}/ring_b`));
  await win.click(`${NATIVE}.querySelector('summary')`); await sleep(250);
  await win.click(win.BUTTON('Refresh')); await quiet();
  check('closed again by the user: Refresh does not reopen it', (await far.evaluate(`${NATIVE}.open`)) === false && await win.folded('gpdk045/nmos1v'));
  await win.choose('Cell', 'ring_a'); await quiet();

  // ---- every folded line unfolds; the window is much shorter folded ------------------------------------------------------------
  const lines = await far.evaluate(`[...${WIN}.querySelectorAll('details.more > summary')].map(s => s.textContent.trim())`);
  await far.evaluate(`${WIN}.querySelectorAll('details.more > summary').forEach(s => s.click())`); await sleep(300);
  const allOpen = await far.evaluate(`[...${WIN}.querySelectorAll('details.more')].every(d => d.open && [...d.children].every(c => c.checkVisibility()))`);
  const after = await win.height();
  check('every folded line of this state unfolds on a click', lines.length === 3 && allOpen, lines.join(' | '));
  check('folded, the window is clearly shorter than unfolded', after - before > 150, `${before} px folded, ${after} px unfolded`);
  await far.evaluate(`${WIN}.querySelectorAll('details.more > summary').forEach(s => s.click())`); await sleep(200);

  // ---- the cell read into the workbench (a draft): the read asks whether it is a copy ----------------------------------------------
  await win.click(win.BUTTON('Read this cell into the workbench')); await quiet(); await far.until(`${WIN}.textContent.includes('Not optimizable yet')`);
  check('reading asked once whether the cell is a copy the user made', dialogs.length === 1 && dialogs[0].startsWith(`Work in ${LIBRARY}/ring_a directly?`), dialogs.join(' | '));
  check('draft: the headline is in view', await win.shown('Read from Virtuoso. Not optimizable yet: it has no circuit profile.'));
  check('draft: what to do with it is folded under "What you can do with it now"', await win.shown('What you can do with it now') && await win.folded('The workbench holds the export of this cell') && await win.folded('it writes the rows into this cell\'s Maestro view'));
  check('draft: its button stays in view', await win.buttonShown('Read the cell again') && !(await win.buttonShown('Ask the agent to set up')));
  check('draft: the cell is named as worked in directly, in view', await win.shown(`Working in ${LIBRARY}/tb_ring_a directly: you declared it a copy you made`));
  check('draft: "Then save it as a task:" points to Save task above the editors, the explanation is folded', await win.shown('Then save it as a task:') && await win.shown('What Save as does')
    && await win.folded('Save as asks for a new name') && !(await far.evaluate(`!!(${win.BUTTON('Save as')})`)));
  check('draft: the name and the two buttons are in view in the editors\' tab line of the workbench', !(await evaluate(`!!${TASK_BAR}?.querySelector('input')`))
    && await taskButtonShown('Save as') && await taskButtonShown('Task file') && !(await evaluate(`!!(${TASK_BUTTON('Save task')})`)));
  check('draft: the backend\'s note is one closed line "1 note on this circuit"', await win.shown('1 note on this circuit') && await win.folded(NOTE));
  await win.click(win.SUMMARY('1 note on this circuit')); await sleep(200);
  check('draft: a click shows the note', await win.shown(NOTE));
  await shotWindow('help-4-draft.png');
  await win.click(win.SUMMARY('1 note on this circuit')); await sleep(200);        // a line stays as the user left it while it is on screen: fold it again
  const WHIER = `${win.SUMMARY('Hierarchy (')}?.parentElement`;
  const WTREE = `${WHIER}.querySelector('ul.tree')`;
  check('draft: Hierarchy is in the window, open as the user left it in the column; "Native schematic" is now a line inside it', (await far.evaluate(`${WHIER}.open`)) === true
    && await far.evaluate(`${WTREE}.checkVisibility()`) && await far.evaluate(`${WHIER}.contains(${NATIVE})`) && await win.shown('Native schematic') && (await far.evaluate(`${NATIVE}.open`)) === false
    && !(await col.present('Hierarchy (')));
  await win.click(win.SUMMARY('Hierarchy (')); await sleep(250);
  check('draft: closed by the user, the whole block is one line again: tree, "Instances and parameters" and "Native schematic" are folded', (await far.evaluate(`${WHIER}.open`)) === false
    && await win.shown('Hierarchy (3 instances)') && await far.evaluate(`!${WTREE}.checkVisibility()`) && await win.folded('Instances and parameters') && await win.folded('Native schematic'));
  await shotWindow('help-4b-draft-hierarchy-closed.png');

  // ---- a saved task: in the column -----------------------------------------------------------------------------------------
  await evaluate(`${TASK_BUTTON('Save as')}.click()`, true); await quiet(); await until(`${PANEL}.textContent.includes('Before every run')`);
  check('saved task: a missing baseline has its retry action in the column', !(await col.present('REAL evaluation backend'))
    && await col.shown('No real baseline yet.') && await col.buttonShown('Retry baseline'));
  check('saved task: "Before every run" and "Check now" stay in view; no manual baseline button (a baseline records itself)', await col.shown('Before every run:')
    && await col.buttonShown('Check now') && !(await col.buttonShown('Record the baseline run as reference')));
  check('saved task: what the check compares is folded', await col.shown('What the check compares') && await col.folded('no ADE/Maestro window may be open on the copy'));
  check('saved task: two notes are one closed line', await col.shown('2 notes on this circuit') && await col.folded('FIXTURE NOTE: a second one.'));
  check('saved task: Hierarchy is back in the column and stays closed, as the user left it', (await evaluate(`${HIERARCHY}.open`)) === false && await col.shown('Hierarchy (1 instances)') && await col.folded('Instances and parameters'));
  check('saved task: the window follows it and shows no cell note', await win.shown('follows the task real:ring_a') && !(await win.present('Not optimizable yet')));
  await shotColumn('help-5-generated-profile.png');

  reportRefused(refused);
  check('the page asked to start, continue, command, connect or open an agent CLI on its own: never', !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify)/.test(r)), refused.join(', '));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
}, { afterError: () => { if (consoleErrors.length) console.log('page errors: ' + consoleErrors.join(' | ').slice(0, 600)); } });
