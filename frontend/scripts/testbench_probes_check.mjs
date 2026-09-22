// Browser check: the Testbench cell box finds `tb_<cell>` by name, and the Probes tab follows the testbench a Virtuoso
// cell was read through (user request 2026-09-21, status record 7.49). Same approach as virtuoso_source_check.mjs: a
// throwaway headless Edge over the DevTools protocol against a served workbench page (default http://127.0.0.1:8765/).
// Every /api/virtuoso/* request and every circuit load of the Virtuoso source is answered with a canned FIXTURE answer, so
// Virtuoso is never contacted and the check does not depend on the backend version; the agent is never called. Other
// requests (schema, the synthetic:gpdk045_ota5 starter, validation) go to the backend and are read-only.
// The canned Probes rows are what profiles.testbench_probes answers for the recorded ring oscillator (fixtures/ring_osc).
// Run (Windows node through WSL interop; node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/testbench_probes_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9397, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-tbprobes-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0; const consoleErrors = [];
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const LIBRARY = 'FIXTURE_TB';
const CELLS = [['ring3', true], ['tb_ring3', true], ['other_tb', true], ['amp', true], ['amp2', true], ['TB_amp2', true], ['lonely', true],
  ['tb_symbolic', false], ['symbolic', true]].map(([name, has_schematic]) => ({ name, views: has_schematic ? ['schematic', 'symbol'] : ['symbol'], has_schematic }));
const RECIPES = [{ id: 'ring_oscillator', label: 'Ring oscillator (free-running)' }, { id: 'opamp_ac', label: 'Op-amp / OTA (AC gain)' }];
const RING = 'Ring oscillator (free-running)', OPAMP = 'Op-amp / OTA (AC gain)';
const MEANING = [['osc_frequency_hz', 'OUT', 'Hz', 'oscillation frequency at OUT'], ['supply_power_w', 'V0:p', 'W', 'average power delivered by the supply V0'],
  ['supply_current_a', 'V0:p', 'A', 'average current delivered by the supply V0'], ['osc_minimum_swing_v', 'OUT XU1.N1 XU1.N2', 'V', 'smallest cycle swing of the ring nets'],
  ['osc_duty_cycle', 'OUT', '1', 'duty cycle at OUT'], ['osc_max_period_spread', 'OUT XU1.N1 XU1.N2', '1', 'largest period spread of the ring nets (a check of regular cycles)'],
  ['osc_max_window_drift', 'OUT XU1.N1 XU1.N2', '1', 'largest frequency drift between the two halves of the measurement window'],
  ['osc_startup_detection_s', 'OUT XU1.N1 XU1.N2', 's', 'time by which every ring net oscillates regularly, from the declared start voltages']];
const ringRows = tb => MEANING.map(([metric, signal, unit, meaning]) => ({ measurement_id: `m_${metric}`, analysis: 'tran', result_source: 'backend_profile',
  source_name: metric, signal, unit, notes: `Testbench ${tb}, circuit type ${RING}: ${meaning}.` }));
const probesFor = (library, cell, tb) => {
  const base = { library, cell, testbench_cell: tb, circuit_type: null, circuit_type_label: null, rows: [], reason: null, not_fitting: {} };
  if (!tb) return { ...base, reason: 'The cell was read without a testbench cell: read it again through its testbench.' };
  if (tb === 'tb_ring3') return { ...base, circuit_type: 'ring_oscillator', circuit_type_label: RING, rows: ringRows(tb),
    not_fitting: { [OPAMP]: 'The op-amp recipe expects the testbench of the verified OTA (...). Missing here: VBIAS, VINN, VINP, VOUT' } };
  return { ...base, reason: `The testbench ${tb} fits none of the circuit types.`, not_fitting: {
    [RING]: 'The free-running oscillator recipe expects exactly one voltage source in the testbench (the supply); found 2',
    [OPAMP]: 'The op-amp recipe expects the testbench of the verified OTA (...). Missing here: VBIAS, VINN' } };
};
const imported = new Map();                                                         // "library/cell" -> the testbench it was read through
const draft = (library, cell) => {
  const tb = imported.get(`${library}/${cell}`);
  return { loaded: true, task_key: `virtuoso:${library}/${cell}`, mock: false, native_draft: true, complete: true, diagnostics: [],
    profile_task: null, profile_task_generated: null, profile_recipes: RECIPES, testbench_probes: probesFor(library, cell, tb),
    circuit: { library, cell, native_draft: true, testbench_cell: tb }, hierarchy: { XU1: { MN1: {}, MP1: {} }, V0: {} }, analysis_context: null,
    evaluation_backend: null, max_concurrency: 1, notes: ['FIXTURE: read from Virtuoso (canned answer).'],
    summary: { device_count: 3, unknown_devices: [], devices: [{ instance_path: 'XU1/MN1', kind: 'nmos', parameters: { w: { value: 1e-6 } } }] } };
};
const browseOnly = { loaded: false, blocker: 'FIXTURE: a native cellview needs a verified circuit profile', interface_contract: null,
  profile_task: null, profile_task_generated: null, profile_recipes: RECIPES };

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const calls = []; let agentRequests = 0; const dialogs = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = async ({ requestId, request }) => {
    const pathname = new URL(request.url).pathname;
    if (pathname === '/api/agent/propose') { agentRequests++; return fulfil(requestId, 418, { detail: { message: 'FIXTURE: no agent request is expected' } }); }
    if (pathname === '/api/circuit/load') {
      const circuit = JSON.parse(request.postData ?? '{}').circuit ?? {};
      if (circuit.source !== 'virtuoso') return send('Fetch.continueRequest', { requestId });
      calls.push({ op: 'load', library: circuit.library, cell: circuit.cell, testbench: circuit.testbench_cell });
      return fulfil(requestId, 200, imported.has(`${circuit.library}/${circuit.cell}`) ? draft(circuit.library, circuit.cell) : browseOnly);
    }
    const op = pathname.replace('/api/virtuoso/', ''), body = JSON.parse(request.postData ?? '{}');
    calls.push({ op, ...body });
    await sleep(150);
    if (op === 'libraries') return fulfil(requestId, 200, { libraries: [LIBRARY, 'analogLib'] });
    if (op === 'cells') return fulfil(requestId, 200, { library: body.library, truncated: false, technology_library: 'gpdk045', cells: body.library === LIBRARY ? CELLS : [] });
    if (op === 'read') return fulfil(requestId, 200, { source: 'virtuoso', library: body.library, cell: body.cell, origin: 'FIXTURE', instance_count: 1, nets: ['OUT'],
      instances: [{ instance_path: 'MN1', master: { library: 'gpdk045', cell: 'nmos1v', view: 'symbol' }, terminals: [], parameters: { w: { raw: '1u' } } }],
      requires_confirmation: ['FIXTURE'], note: 'FIXTURE' });
    if (op === 'import') { imported.set(`${body.library}/${body.cell}`, body.testbench ?? null); return fulfil(requestId, 200, { library: body.library, cell: body.cell, testbench_cell: body.testbench, device_count: 3 }); }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* page went away */ });
    else if (m.method === 'Page.javascriptDialogOpening') { dialogs.push(m.params.message); send('Page.handleJavaScriptDialog', { accept: false }).catch(() => undefined); }
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
  const EDITOR_BUTTON = text => `[...document.querySelectorAll('section.editors .toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const text = () => evaluate(`${PANEL}.textContent.replace(/\\s+/g, ' ')`);
  const shown = selector => evaluate(`(() => { const e = ${PANEL}.querySelector(${JSON.stringify(selector)}); return e && e.checkVisibility() ? e.textContent.replace(/\\s+/g, ' ').trim() : null; })()`);
  const value = label => evaluate(`${FIELD(label)}?.value`);
  const options = label => evaluate(`[...${FIELD(label)}.options].map(o => o.value)`);
  const choose = async (label, v) => { await evaluate(`(() => { const s = ${FIELD(label)}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(v)});
    s.dispatchEvent(new Event('change', { bubbles: true })); })()`); await quiet(); };
  const press = async (label, where = BUTTON) => { await evaluate(`${where(label)}.click()`); await quiet(); };
  const quiet = async (ms = 700) => { let seen = -1; while (seen !== calls.length) { seen = calls.length; await sleep(ms); } };
  const counts = () => evaluate(`Object.fromEntries([...document.querySelectorAll('section.editors .tabs button')].map(b => /^(\\w+) \\((\\d+)\\)$/.exec(b.textContent.trim())).filter(Boolean).map(m => [m[1], Number(m[2])]))`);
  const probes = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? '{}').measurements ?? null`);
  const configNow = async () => { await sleep(1000); return evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? '{}')`); };   // saved 800 ms after a change
  const imports = (from = 0) => calls.slice(from).filter(c => c.op === 'import').map(c => `${c.cell} ${c.testbench ?? '-'}`);
  const shot = async name => {
    const H3 = `[...${PANEL}.querySelectorAll('h3')].find(h => h.textContent.trim() === 'Circuit source')`;
    await evaluate(`${H3}.scrollIntoView({ block: 'start' })`); await sleep(200);
    const clip = await evaluate(`(() => { const a = document.querySelector('.left').getBoundingClientRect(), h = ${H3}.getBoundingClientRect();
      return { x: a.x, y: Math.max(a.y, h.y - 6), width: a.width, height: a.bottom - Math.max(a.y, h.y - 6), scale: 2 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: ['*/api/virtuoso/*', '*/api/circuit/load', '*/api/agent/propose'].map(urlPattern => ({ urlPattern, requestStage: 'Request' })) });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  for (let i = 0; i < 100 && !(await evaluate(`!!(${BUTTON('Load starter configuration')})`)); i++) await sleep(100);
  for (let i = 0; i < 60 && !(await evaluate(`/\\S/.test(document.querySelector('.left button.connection-button .connection-button-what')?.textContent.replace(/none (selected|set up yet)/, '') ?? '')`)); i++) await sleep(100);
  await sleep(800);

  // ---- a registered task's rows first: the MOCK starter (its Probe m_score, its target score) -------------------------
  await press('Load starter configuration'); await sleep(800);
  check('the MOCK starter is in the editors', (await counts()).Specs === 1 && (await counts()).Probes === 1, JSON.stringify(await counts()));

  // ---- tb_<cell> is found by its name ------------------------------------------------------------------------------------
  await choose('Source', 'virtuoso'); await choose('Library', LIBRARY);
  check('the testbench box offers the cells with a schematic', JSON.stringify(await options('Testbench cell')) === JSON.stringify(['', ...CELLS.filter(c => c.has_schematic).map(c => c.name)]),
    JSON.stringify(await options('Testbench cell')));
  await choose('Cell', 'ring3');
  check('choosing ring3 chooses tb_ring3 by itself', (await value('Testbench cell')) === 'tb_ring3', await value('Testbench cell'));
  check('the form says why', (await shown('.tb-named')) === "Found by its name: tb_ + the cell's name.", await shown('.tb-named'));
  check('the browse-only note names the testbench the cell will be read through', (await text()).includes('read it into the workbench through the testbench tb_ring3'));
  check('a browse-only cell brings no probes', (await counts()).Probes === 1 && !(await shown('.tb-probes')));
  await shot('tbprobes-1-found.png');

  // ---- reading the cell through it: Probes follow the testbench; the MOCK target leaves with its probe ----------------------------
  let mark = calls.length;
  await press('Read this cell into the workbench'); await sleep(600);
  check('the press reads the cell through tb_ring3', JSON.stringify(imports(mark)) === JSON.stringify(['ring3 tb_ring3']), imports(mark).join(' | '));
  let saved = await configNow();
  check('Probes now hold the testbench\'s 8 results, with its nets', saved.measurements?.length === 8 && saved.measurements[0].signal === 'OUT'
    && saved.measurements.find(r => r.source_name === 'supply_power_w')?.signal === 'V0:p', JSON.stringify(saved.measurements?.map(r => r.signal)));
  check('the untouched MOCK target left Specs with its probe', (saved.targets ?? []).length === 0, JSON.stringify(saved.targets));
  check('the panel says so, naming the testbench, the type and the task', (await shown('.tb-probes'))?.includes('Probes now show what the testbench tb_ring3 measures: 8 results of the circuit type Ring oscillator (free-running).')
    && (await shown('.tb-probes'))?.includes('The targets of synthetic:gpdk045_ota5 were removed from Specs'), await shown('.tb-probes'));
  check('what the rows mean is one click away (folded)', await evaluate(`(() => { const d = [...${PANEL}.querySelectorAll('details')].find(d => d.querySelector('summary')?.textContent === 'What the Probes rows say');
    return !!d && !d.open && d.textContent.includes('V0:p, the current through the supply source V0'); })()`));
  check('there is no circuit type box any more: a saved task reads it from its probes', !(await evaluate(`[...document.querySelectorAll('label')].some(l => l.firstChild?.textContent.trim() === 'Circuit type')`)));
  check('the copy matches the box: no "read again" warning', !(await shown('.tb-stale')));
  await shot('tbprobes-2-brought.png');

  // ---- a press is its own Undo step ------------------------------------------------------------------------------------------------
  await press('Undo', EDITOR_BUTTON); saved = await configNow();
  check('Undo brings the MOCK rows back', saved.measurements?.length === 1 && saved.measurements[0].measurement_id === 'm_score' && saved.targets?.length === 1, JSON.stringify(saved.measurements?.map(r => r.measurement_id)));
  await press('Redo', EDITOR_BUTTON); saved = await configNow();
  check('Redo brings the testbench rows again', saved.measurements?.length === 8 && (saved.targets ?? []).length === 0);

  // ---- rows someone edited are never replaced by themselves ------------------------------------------------------------------------
  await evaluate(`[...document.querySelectorAll('section.editors .tabs button')].find(b => b.textContent.startsWith('Probes')).click()`); await sleep(300);
  const notesColumn = await evaluate(`[...document.querySelectorAll('section.editors table.editor thead th')].findIndex(th => th.textContent.replace(' *', '') === 'notes')`);
  await evaluate(`(() => { const i = document.querySelector('section.editors table.editor tbody tr:first-child td:nth-child(${notesColumn + 1}) input'); i.focus(); i.select(); })()`);
  await send('Input.insertText', { text: 'my own note' }); await sleep(300);
  mark = calls.length;
  await choose('Testbench cell', 'other_tb'); await sleep(500);
  check('choosing another testbench reads nothing from Virtuoso', imports(mark).length === 0, imports(mark).join(' | '));
  check('the note says the copy was read through another testbench', (await shown('.tb-stale')) === 'This copy was read through tb_ring3. Press Read the cell again to read it through other_tb: Probes then follow it.',
    await shown('.tb-stale'));
  check('edited Probes are kept, and the exchange is offered', (await shown('.tb-probes'))?.startsWith('Probes hold rows you edited, not the ones of the testbench tb_ring3.')
    && !!(await evaluate(`!!(${BUTTON('Use testbench probes')})`)), await shown('.tb-probes'));
  saved = await configNow();
  check('the edited row is still there', saved.measurements?.[0]?.notes === 'my own note', saved.measurements?.[0]?.notes);
  await shot('tbprobes-3-kept.png');

  // ---- a testbench that fits no circuit type: Probes stay, the reasons are folded ------------------------------------------------------
  mark = calls.length;
  await press('Read the cell again'); await sleep(600);
  check('"Read the cell again" reads it through other_tb', JSON.stringify(imports(mark)) === JSON.stringify(['ring3 other_tb']), imports(mark).join(' | '));
  check('it says that no circuit type fits, and Probes are left alone', (await shown('.tb-probes')) === 'Probes were left as they were. The testbench other_tb fits none of the circuit types.'
    && (await probes())?.[0]?.notes === 'my own note', await shown('.tb-probes'));
  check('why each type does not fit is folded', await evaluate(`(() => { const d = [...${PANEL}.querySelectorAll('details')].find(d => d.querySelector('summary')?.textContent === 'Why no circuit type fits');
    return !!d && !d.open && d.textContent.includes('found 2') && d.textContent.includes('Missing here'); })()`));
  check('the copy matches the box again', !(await shown('.tb-stale')));

  // ---- back to tb_ring3: the offer, then the exchange on request ---------------------------------------------------------------------
  await choose('Testbench cell', 'tb_ring3'); await press('Read the cell again'); await sleep(600);
  check('back through tb_ring3, the edited rows are kept and the exchange offered', (await shown('.tb-probes'))?.startsWith('Probes hold rows you edited')
    && (await probes())?.[0]?.notes === 'my own note');
  await press('Use testbench probes'); saved = await configNow();
  check('"Use testbench probes" takes the testbench rows', saved.measurements?.length === 8 && saved.measurements[0].notes.startsWith('Testbench tb_ring3'), saved.measurements?.[0]?.notes);
  check('and says so', (await shown('.tb-probes'))?.startsWith('Probes now show what the testbench tb_ring3 measures'));
  await press('Undo', EDITOR_BUTTON); saved = await configNow();
  check('one Undo brings the edited rows back', saved.measurements?.[0]?.notes === 'my own note', saved.measurements?.[0]?.notes);
  await press('Redo', EDITOR_BUTTON);

  // ---- the name rule when the cell changes ---------------------------------------------------------------------------------------------
  await choose('Cell', 'amp');
  check('a cell without tb_<cell> drops the old cell\'s tb_ring3', (await value('Testbench cell')) === '' && !(await shown('.tb-named')), await value('Testbench cell'));
  await choose('Testbench cell', 'other_tb');
  await choose('Cell', 'lonely');
  check('a testbench chosen by hand stays when the new cell has no tb_ of its own', (await value('Testbench cell')) === 'other_tb', await value('Testbench cell'));
  await choose('Cell', 'amp2');
  check('the tb_ prefix in capitals counts: TB_amp2', (await value('Testbench cell')) === 'TB_amp2', await value('Testbench cell'));
  await choose('Cell', 'symbolic');
  check('a tb_ cell without a schematic is not chosen (and amp2\'s TB_amp2 goes)', (await value('Testbench cell')) === '', await value('Testbench cell'));
  await choose('Cell', 'ring3');
  check('the cell\'s own tb_ring3 wins over a testbench chosen before', (await value('Testbench cell')) === 'tb_ring3', await value('Testbench cell'));
  saved = await configNow();
  check('choosing the cell again brings nothing new: Probes are already its testbench\'s', saved.measurements?.length === 8 && !(await shown('.tb-probes')));

  // ---- an empty box is filled when the cell list arrives (Refresh) - never over a chosen one ---------------------------------------------
  await choose('Testbench cell', '');
  check('the box can be emptied by hand', (await value('Testbench cell')) === '');
  await press('Refresh'); await sleep(600);
  check('after Refresh an empty box takes tb_ring3 again', (await value('Testbench cell')) === 'tb_ring3', await value('Testbench cell'));
  await choose('Testbench cell', 'other_tb'); await press('Refresh'); await sleep(600);
  check('Refresh never replaces a chosen testbench', (await value('Testbench cell')) === 'other_tb', await value('Testbench cell'));

  check('nothing was sent to the agent', agentRequests === 0, `${agentRequests} request(s)`);
  check('no question was asked on screen', dialogs.length === 0, dialogs.join(' | '));
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
