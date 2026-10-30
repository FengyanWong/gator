// Browser check of the cell the task flow WORKS IN (WorkingCopy.tsx, in the Virtuoso window since 2026-09-23) and the
// Maestro setup of that cell. Same approach as virtuoso_source_check.mjs: a throwaway headless Edge over the DevTools
// protocol against a workbench page (default http://127.0.0.1:8765/; point GATOR_WORKBENCH_URL at a preview of a
// temporary build to check a page that is not live yet). EVERY /api/virtuoso/* and /api/circuit/load request is answered
// with a canned FIXTURE, so Virtuoso is never contacted and nothing is written anywhere (any other writing request of the
// page is refused, reads pass); the configuration lives in the throwaway browser profile. What it pins (user request
// 2026-09-23: the workbench makes no copy of its own; the user's copy is declared when the cell is read):
//   - a cell read before the question, without a record: no "Make a working copy" button; the line says to read the cell
//     again, which asks; the old /api/virtuoso/copy route is never called;
//   - a declared cell: "Working in <library>/<testbench> directly: you declared it a copy you made", then that Save as writes
//     the Maestro test there and a run sets the sizes in <library>/<cell> (branch record SIF-133), ONE button "Read setup",
//     only on a press, nothing on load - no "Write to Virtuoso" and no "Use in editors" (user 2026-09-22);
//   - a copy the workbench made before that date keeps its record and its own line ("made by the workbench before");
//   - "Read setup" reads AND fills Probes/Specs in one press, keeping the user's unit and optimizer settings, one Undo step
//     (which also takes back what the page said); read again: the editors already say what the cell says; nothing written;
//     a limit lands in the user's prefixed unit with exact digits (0.7 V = 700 mV, branch record SIF-69);
//   - a test without outputs and a cell without a Maestro view take nothing and say what to do; a blocked gate and an older
//     backend read plainly.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; WSLENV carries the URL into it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/working_copy_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { answerDialogs, check, launchEdge, outDir, runChecks, sleep, TASK_PANEL, workbenchUrl, VIRTUOSO_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('copy');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const LIB = 'GPDK045_RINGOSC', CELL = 'ring_osc_3stage', TB = 'tb_ring_osc_3stage', COPY = 'GPDK045_RINGOSC_GATOR';
const DECLARED = { format: 'gator-working-copy-1', declared: true, verified: true, problems: [], created_utc: '2026-09-23T10:00:00+00:00',
  original: { library: LIB, cell: CELL, testbench: TB }, copy: { library: LIB, cell: CELL, testbench: TB, path: null } };
const MADE = { format: 'gator-working-copy-1', verified: true, problems: [], original: { library: LIB, cell: CELL, testbench: TB },
  copy: { library: COPY, cell: CELL, testbench: TB, path: `/home/fixture/${COPY}` }, originals_unchanged: true, netlist_equal: true };
let record = null;                                                                  // what the backend knows about the cell
const draft = () => ({ loaded: true, task_key: `virtuoso:${LIB}/${CELL}`, mock: false, native_draft: true, complete: true, diagnostics: [],
  profile_task: null, profile_task_generated: null, working_copy: record,
  circuit: { library: LIB, cell: CELL, native_draft: true, testbench_cell: TB }, hierarchy: { XU1: { MN1: {} }, V0: {} },
  analysis_context: null, evaluation_backend: null, max_concurrency: 1, testbench_probes: null,
  summary: { device_count: 2, unknown_devices: [], devices: [{ instance_path: 'XU1/MN1', kind: 'nmos', parameters: { w: { value: 1e-6 } } }] },
  notes: ['FIXTURE: read from Virtuoso (canned answer).'] });
const SETUP_ROWS = {
  measurements: [
    { measurement_id: 'm_freq', analysis: 'tran', result_source: 'ade_output', source_name: 'freq', signal: 'frequency(VT("/OUT"))', unit: 'Hz', notes: 'FIXTURE suggested' },
    { measurement_id: 'm_vmax', analysis: 'tran', result_source: 'ade_output', source_name: 'vmax', signal: 'ymax(VT("/OUT"))', unit: 'V', notes: 'FIXTURE suggested' },
    { measurement_id: 'm_vmin', analysis: 'tran', result_source: 'ade_output', source_name: 'vmin', signal: 'ymin(VT("/OUT"))', unit: 'V', notes: 'FIXTURE suggested' }],
  targets: [
    { metric_id: 'freq', equation: 'm_freq', unit: 'Hz', constraint: '>=', lower: 1e9, normalization_scale: 1e9, basis: 'FIXTURE' },
    { metric_id: 'vmax', equation: 'm_vmax', unit: 'V', constraint: 'interval', lower: 0.9, upper: 1.1, normalization_scale: 1.1, basis: 'FIXTURE' },
    // limits that division by 1e-3 does not keep exact: 0.35 V / 1e-3 = 349.99999999999994 (branch record SIF-69)
    { metric_id: 'vmin', equation: 'm_vmin', unit: 'V', constraint: 'interval', lower: 0.35, upper: 0.7, normalization_scale: 0.35, basis: 'FIXTURE' }] };
const setupAnswer = config => {
  const ade = (config?.measurements ?? []).filter(m => m.result_source === 'ade_output').map(m => m.source_name).sort();
  return { exists: true, tests: ['GATOR'], test: 'GATOR', model_files: [['/pdk/gpdk045.scs', 'tt']], analyses: { tran: { stop: '50n' } },
    variables: { VSUP: '1.0' }, bindings: [], outputs: [{ name: 'freq', expression: 'frequency(VT("/OUT"))' }, { name: 'vmax', expression: 'ymax(VT("/OUT"))' },
      { name: 'vmin', expression: 'ymin(VT("/OUT"))' }],
    specs: [{ output: 'freq', op: 'gt', value: '1e+09' }, { output: 'vmax', op: 'range', value: ['0.9', '1.1'] }, { output: 'vmin', op: 'range', value: ['0.35', '0.7'] }],
    fingerprint: 'f'.repeat(64),
    rows: SETUP_ROWS, editor_differences: JSON.stringify(ade) === JSON.stringify(['freq', 'vmax', 'vmin']) ? [] : ['Output freq: the task says (none), Virtuoso has frequency(VT("/OUT"))',
      'Output vmax: the task says (none), Virtuoso has ymax(VT("/OUT"))'] };
};
const gateBlocked = { message: 'The connection gate blocked reading the Maestro setup', gate: { allowed: false, status: 'blocked', blocking: ['tunnel'], uncertain: [] } };

await runChecks(browser, async () => {
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, fulfil } = page;
  const calls = []; let mode = 'ok';
  const dialogs = []; const answers = [];
  const answer = async ({ requestId, request }) => {
    const pathname = new URL(request.url).pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/circuit/load') {
      return body.circuit?.source === 'virtuoso' ? fulfil(requestId, 200, draft()) : send('Fetch.continueRequest', { requestId });
    }
    const op = pathname.replace('/api/virtuoso/', '');
    calls.push({ op, ...body });
    await sleep(150);
    if (op === 'libraries') return fulfil(requestId, 200, { libraries: [LIB, 'analogLib'] });
    if (op === 'cells') return fulfil(requestId, 200, { library: body.library, truncated: false, technology_library: 'gpdk045', cells: [
      { name: CELL, views: ['schematic', 'symbol'], has_schematic: true }, { name: TB, views: ['schematic'], has_schematic: true }] });
    if (op === 'read') return fulfil(requestId, 200, { source: 'virtuoso', library: body.library, cell: body.cell, origin: 'FIXTURE', instance_count: 1, nets: ['OUT'],
      instances: [{ instance_path: 'MN1', master: { library: 'gpdk045', cell: 'nmos1v', view: 'symbol' }, terminals: [], parameters: {} }], requires_confirmation: [], note: 'FIXTURE' });
    if (op === 'import') { if (body.work_here) record = DECLARED; return fulfil(requestId, 200, { library: body.library, cell: body.cell, testbench_cell: body.testbench, device_count: 2, ...(body.work_here ? { working_copy: DECLARED } : {}) }); }
    if (mode === 'blocked') return fulfil(requestId, 409, { detail: gateBlocked });
    if (mode === 'outdated') return fulfil(requestId, 404, { detail: 'Not Found' });
    if (op === 'copy') return fulfil(requestId, 409, { detail: { code: 'copies_not_made', message: 'FIXTURE: the workbench no longer makes copies' } });
    if (op === 'setup/read' && mode === 'no-outputs') return fulfil(requestId, 200, { ...setupAnswer(body.config), outputs: [], specs: [], rows: { measurements: [], targets: [] }, editor_differences: [] });
    if (op === 'setup/read' && mode === 'no-view') return fulfil(requestId, 200, { exists: false, tests: [], test: null, model_files: [], analyses: {}, variables: {}, bindings: [], outputs: [], specs: [] });
    if (op === 'setup/read') return fulfil(requestId, 200, setupAnswer(body.config));
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
  const onDialog = session => answerDialogs(session, answers, dialogs);
  onDialog(page);
  const PANEL = TASK_PANEL;
  const LAUNCH = `${PANEL}?.querySelector('button.virtuoso-button')`;
  // ---- the window: the cell's note lives there; a second page with a DevTools session of its own -----------------------------
  const WIN = `document.querySelector('.virtuoso-window')`;
  const BLOCK = `${WIN}?.querySelector('.working-copy')`;
  let far = null;
  const openWindow = async () => {
    far = await browser.popup(page, LAUNCH, VIRTUOSO_WINDOW, { width: 720, height: 980, ready: BLOCK, onDialog });
    await sleep(600);
  };
  const BUTTON = text => `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const WBUTTON = text => `[...(${WIN}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const blockText = () => far.evaluate(`${BLOCK}?.textContent ?? ''`);
  const visible = selector => far.evaluate(`(() => { const e = ${selector}; return !!e && e.checkVisibility(); })()`);
  const press = async label => { await far.evaluate(`${BUTTON(label)}.click()`, true); };
  const stored = page.stored;
  // Up to `ms` for the press to reach the backend; once it has, settled when 0.5 s pass with no further call (the fixture
  // answers after 0.15 s). A press that sends nothing still waits the whole `ms`. It slept `ms` every time until 2026-09-30.
  const settle = async (ms = 900) => {
    const mark = calls.length;
    for (let waited = 0; waited < ms && calls.length === mark; waited += 50) await sleep(50);
    for (let seen = mark; calls.length !== mark && seen !== calls.length;) { seen = calls.length; await sleep(500); }
  };
  const shot = async name => far.shot(path.join(out, name), BLOCK, { scale: 2, pad: 12, maxHeight: 1200, beyond: true });

  await page.intercept(['*/api/virtuoso/*', '*/api/circuit/load'], answer, { others: 'read', connection: 'lab' });
  // A configuration that already holds a Probes row and a Specs row of the user's own for "freq": their unit and optimizer
  // settings must survive "Read setup". Started from the live starter configuration, so it passes the schema.
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  for (let i = 0; i < 50 && !(await stored()); i++) await sleep(100);
  const starter = await stored();                                   // the page's own configuration: every field the page needs
  const seeded = { ...starter, circuit: { ...starter.circuit, source: 'virtuoso', task_id: null, library: LIB, cell: CELL, view: 'schematic', testbench_cell: TB, pdk_id: 'gpdk045' },
    measurements: [...starter.measurements, { measurement_id: 'm_freq', analysis: 'ac', result_source: 'ade_output', source_name: 'freq',
      signal: 'frequency(VT("/OUT"))', unit: 'GHz', notes: 'mine' },
      { measurement_id: 'm_vmin', analysis: 'tran', result_source: 'ade_output', source_name: 'vmin', signal: 'ymin(VT("/OUT"))', unit: 'mV', notes: 'mine' }],
    targets: [...starter.targets, { metric_id: 'freq', equation: 'm_freq', unit: 'GHz', constraint: '>=', lower: 0.5, normalization_scale: 0.5, hard: false, soft_weight: 3,
      basis: 'mine: datasheet', margin_sides: 'lower' }] };
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(seeded))})`);
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${LAUNCH})`)); i++) await sleep(100);
  await settle(1500);
  check('the column holds no working-copy block and no cell buttons', !(await evaluate(`!!${PANEL}.querySelector('.working-copy')`))
    && !(await evaluate(`[...${PANEL}.querySelectorAll('button')].some(b => ['Read setup', 'Make a working copy', 'Read the cell again'].includes(b.textContent.trim()))`)));
  await openWindow();
  if (!(await far.evaluate(`!!(${BLOCK})`))) console.log('DEBUG window: ' + (await far.evaluate(`${WIN}?.textContent.slice(0, 900) ?? 'no window'`))
    + '\nDEBUG stored circuit: ' + JSON.stringify((await stored())?.circuit) + '\nDEBUG calls: ' + calls.map(c => c.op).join(' ') + '\nDEBUG errors: ' + consoleErrors.join(' | ').slice(0, 1500));
  const loadedOps = calls.map(c => c.op);
  check('nothing is copied, read or written on load or on opening the window', !loadedOps.some(op => ['copy', 'setup/read', 'setup/write', 'import'].includes(op)), loadedOps.join(' | '));

  // ---- a cell read before the question: no record ----------------------------------------------------------------------------
  check('no record: no "Make a working copy" and no "Read setup"; the line says to read the cell again', !(await far.evaluate(`!!(${BUTTON('Make a working copy')}) || !!(${BUTTON('Read setup')})`))
    && (await blockText()).includes('Not yet the cell the task flow works in') && (await blockText()).includes('Read the cell again'), await blockText());
  check('no "Ask the agent to set up" any more (record 7.226)', !(await far.evaluate(`!!${WBUTTON('Ask the agent to set up')}`)));
  await shot('working-copy-1-none.png');
  // Branch record SIF-88: this read declares the cell, which needs a testbench - said before the question, with nothing sent
  // (the backend refused it only after the user had answered).
  const TB_BOX = `[...${WIN}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'Testbench cell')?.querySelector('select')`;
  const NO_TB = "Choose the cell's Testbench cell first: a task simulates the testbench and keeps its Maestro test there.";
  await far.setValue(TB_BOX, ''); await settle();
  // review of SIF-88: the line on the copy read through TB invited "Read the cell again ... without one", the press refused
  const stale = await far.evaluate(`${WIN}.querySelector('.tb-stale')?.textContent.replace(/\\s+/g, ' ').trim() ?? ''`);
  check('without a testbench, the line on the copy read asks for one, not for a read without one (review of SIF-88)', stale.includes(`This cell was read through ${TB}.`)
    && stale.includes('Choose its Testbench cell above to read it again') && !stale.includes('without one'), stale);
  let mark = calls.length;
  await far.evaluate(`${WBUTTON('Read the cell again')}.click()`, true); await settle();
  check('without a testbench, reading it again asks nothing, sends nothing and says to choose one (branch record SIF-88)', dialogs.length === 0 && calls.length === mark
    && (await far.evaluate(`${WIN}.textContent`)).includes(NO_TB), `${dialogs.length} dialog(s) / ${JSON.stringify(calls.slice(mark))}`);
  await far.setValue(TB_BOX, TB); await settle();
  check('...and choosing the testbench takes that line away', (await far.evaluate(`${TB_BOX}.value`)) === TB && !(await far.evaluate(`${WIN}.textContent`)).includes(NO_TB));
  mark = calls.length; answers.push(true);
  await far.evaluate(`${WBUTTON('Read the cell again')}.click()`, true); await settle(1500);
  check('reading it again asks the question and, on OK, reads with work_here - the old copy route is never called', dialogs.length === 1 && dialogs[0].message.startsWith(`Work in ${LIB}/${CELL} directly?`)
    && JSON.stringify(calls.slice(mark).map(c => [c.op, c.library, c.cell, c.testbench, !!c.work_here].join(' '))) === JSON.stringify([`import ${LIB} ${CELL} ${TB} true`]) && !calls.some(c => c.op === 'copy'),
    JSON.stringify(calls.slice(mark)));
  check('the cell is named as worked in directly, with when it was declared', (await blockText()).includes(`Working in ${LIB}/${TB} directly: you declared it a copy you made (`),
    await blockText());
  // States audit of 2026-10-24 (branch record SIF-133): "Its Maestro test and, in a run, its device sizes are written here" said
  // the sizes go into the testbench; a run writes them into the cell under it.
  const declaredLine = await far.evaluate(`${BLOCK}?.querySelector('.declared')?.textContent.replace(/\\s+/g, ' ').trim() ?? ''`);
  check('...then where each part is written: Save as the Maestro test into it, a run the device sizes into the cell (branch record SIF-133)',
    declaredLine.endsWith(`. Save as writes the Maestro test GATOR here; a run sets device sizes in ${LIB}/${CELL} (put back when the run ends).`)
    && !declaredLine.includes('device sizes are written here'), declaredLine);
  check('then one button, Read setup - no Write to Virtuoso, no Use in editors', await far.evaluate(`!!(${BUTTON('Read setup')}) && !(${BUTTON('Write to Virtuoso')}) && !(${BUTTON('Use in editors')})`));
  check('the text beside it says when to press it', (await blockText()).includes('Changed its Maestro test yourself?'), await blockText());
  // branch record SIF-69: the fold said "source ade_output, the expression in signal" - a hidden column's value and a key
  check('the fold on how the editors and Maestro relate names the Probes columns by their headers',
    (await blockText()).includes('a Probes row (its name in Output name, its expression in Expression)') && !(await blockText()).includes('ade_output'), await blockText());
  check('reading the setup still waits for a press', !calls.some(c => c.op === 'setup/read'));

  // ---- Read setup: read and take in one press ---------------------------------------------------------------------------
  mark = calls.length;
  await press('Read setup'); await settle();
  check('Read setup sends the editors along, once', calls.slice(mark).length === 1 && calls[mark].op === 'setup/read' && Array.isArray(calls[mark].config?.measurements));
  check('the setup is summarized in one line', (await blockText()).includes('Test GATOR: 3 outputs, 3 specs, 1 variable, analyses: tran'), await blockText());
  let config = await stored();
  for (let i = 0; i < 30 && !config.measurements.some(m => m.measurement_id === 'm_vmax'); i++) { await sleep(100); config = await stored(); }   // stored a moment later
  const probe = config.measurements.find(m => m.measurement_id === 'm_freq'), vmax = config.measurements.find(m => m.measurement_id === 'm_vmax');
  const spec = config.targets.find(t => t.metric_id === 'freq');
  check('the same press brings the cell\'s outputs as Probes rows', !!vmax && vmax.result_source === 'ade_output' && vmax.signal === 'ymax(VT("/OUT"))', JSON.stringify(vmax));
  check('your unit on a probe of the same name stays', probe?.unit === 'GHz' && probe?.notes === 'mine', JSON.stringify(probe));
  check('your optimizer settings on the spec stay; the cell\'s limit (1e9 Hz) arrives in your unit (1 GHz)', spec?.hard === false && spec?.soft_weight === 3
    && spec?.unit === 'GHz' && spec?.lower === 1 && spec?.normalization_scale === 0.5, JSON.stringify(spec));
  // Review of 2026-10-03: the analysis came back as a guess from the expression ("other" for getData outputs, so Save task
  // refused the rows), and a spec's citation became "Maestro spec on ..." - what the cell does not hold now stays.
  check('your analysis stays while the expression is the cell\'s, and so do the spec\'s citation and its margin sides',
    probe?.analysis === 'ac' && spec?.basis === 'mine: datasheet' && spec?.margin_sides === 'lower',
    JSON.stringify({ analysis: probe?.analysis, basis: spec?.basis, margin_sides: spec?.margin_sides }));
  const vmaxSpec = config.targets.find(t => t.metric_id === 'vmax');
  check('a spec on a probe in the base unit keeps the cell\'s numbers', vmaxSpec?.unit === 'V' && vmaxSpec?.lower === 0.9 && vmaxSpec?.upper === 1.1, JSON.stringify(vmaxSpec));
  // branch record SIF-69: the limits were divided by 1e-3, and the Specs cells read "349.99999999999994 mV" .. "699.9999999999999 mV"
  const vminSpec = config.targets.find(t => t.metric_id === 'vmin');
  check('a spec on a probe in mV gets the cell\'s 0.35 .. 0.7 V with exact digits: 350 .. 700 mV, its scale 350 mV', vminSpec?.unit === 'mV'
    && vminSpec?.lower === 350 && vminSpec?.upper === 700 && vminSpec?.normalization_scale === 350, JSON.stringify(vminSpec));
  check('the other rows are left alone', config.measurements.length === starter.measurements.length + 3
    && starter.targets.every(t => config.targets.some(u => u.metric_id === t.metric_id)), JSON.stringify(config.targets.map(t => t.metric_id)));
  check('the page says what it took and that Undo brings the previous rows back', (await blockText()).includes('Probes and Specs now show the cell\'s outputs and specs')
    && (await blockText()).includes('Undo brings the previous rows back'), await blockText());
  check('what differed is listed, folded', (await blockText()).includes('What differed (2)')
    && !(await visible(`[...${BLOCK}.querySelectorAll('li')].find(li => li.textContent.startsWith('Output vmax'))`)));
  await shot('working-copy-2-read.png');
  await evaluate(`[...document.querySelectorAll('.editors .toolbar button')].find(b => b.textContent.trim() === 'Undo').click()`); await settle(1200);
  config = await stored();
  check('one Undo takes the rows back, and the page no longer claims them', !config.measurements.some(m => m.measurement_id === 'm_vmax')
    && !(await blockText()).includes('now show the cell'), await blockText());
  mark = calls.length;
  await press('Read setup'); await settle(1200);
  await press('Read setup'); await settle();
  check('read again: the editors already say what the cell says', (await blockText()).includes('The editors already say what the cell says.'), await blockText());
  check('reading never writes into Virtuoso', calls.slice(mark).every(c => c.op === 'setup/read') && !calls.some(c => c.op === 'setup/write'), calls.slice(mark).map(c => c.op).join(' '));
  await shot('working-copy-3-taken.png');

  // ---- nothing to take: a test without outputs, a cell without a Maestro view ------------------------------------------------
  const before = JSON.stringify(await stored());
  mode = 'no-outputs';
  await press('Read setup'); await settle();
  check('a test without outputs takes nothing and says so', (await blockText()).includes('It has no outputs, so nothing was taken into the editors.')
    && JSON.stringify(await stored()) === before, await blockText());
  mode = 'no-view';
  await press('Read setup'); await settle();
  check('a cell without a Maestro view says how it gets one: Save task', (await blockText()).includes('The cell has no Maestro setup yet')
    && (await blockText()).includes('Save as') && !(await blockText()).includes('Ask the agent') && JSON.stringify(await stored()) === before, await blockText());

  // ---- a blocked link and an older backend read plainly ---------------------------------------------------------------------
  mode = 'blocked';
  await press('Read setup'); await settle();
  check('a blocked gate says Virtuoso cannot be reached and what to do', (await blockText()).includes('Virtuoso cannot be reached (tunnel)') && (await blockText()).includes('Connection window'), await blockText());
  mode = 'outdated';
  await press('Read setup'); await settle();
  check('an older backend says to restart it', (await blockText()).includes('This backend is older than the page'), await blockText());

  // ---- a copy the workbench made before 2026-09-23 keeps its own line --------------------------------------------------------
  mode = 'ok'; record = MADE;
  await far.evaluate(`${WBUTTON('Read the cell again')}.click()`, true); await settle(1500);
  check('a made copy from before is named as such, with its library, and asks nothing', (await blockText()).includes(`Working copy: ${COPY}/${TB}, made by the workbench before 2026-09-23`)
    && (await blockText()).includes('netlists like your cell') && dialogs.length === 1 && await far.evaluate(`!!(${BUTTON('Read setup')})`), await blockText());
  check('every question on screen was planned', dialogs.every(d => d.planned), JSON.stringify(dialogs));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
});
