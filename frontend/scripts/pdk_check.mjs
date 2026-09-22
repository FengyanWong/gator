// Browser check of "Load PDK" and the network's component list (Pdk.tsx, RL network block of "Run configuration";
// user request 2026-09-21: "make the optimizer understand all the components in one provided PDK ... add load PDK in the
// frontend"). Same approach as module_fold_check.mjs: a throwaway headless Edge over the DevTools protocol against the
// RUNNING workbench (default http://127.0.0.1:8765/). Everything about PDKs is answered with canned data labelled
// FIXTURE - GET /api/pdks, GET /api/pdks/<id>, POST /api/pdks/load (so no PDK is read and nothing reaches Virtuoso) -,
// /api/config/validate with an empty report, /api/connection/profiles with NO profile, the page's own start-up reads
// (POST /api/circuit/load, /api/output/check) and other GET requests pass through, and every other writing request is
// refused here. The browser profile is new and temporary: the user's saved configuration is not touched.
// What it pins:
//   - the RL network block has a "Components" list (standard first) with a short "Load PDK..." button beside it, and a
//     plain line saying what the chosen list knows;
//   - choosing a loaded PDK writes run.network.vocabulary; the standard list is written as NO field (old servers accept
//     it); another encoder keeps the chosen list;
//   - a configuration naming a PDK that is not loaded says so;
//   - "Load PDK..." opens the PDK window: the form, the connection it reads through, the loaded PDKs (double click shows
//     one, with every component, its pins and roles, its parameters); "Load" sends exactly the typed fields, shows that it
//     is reading, then shows the answer and reads the list again; without a connection it cannot be pressed.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/pdk_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9417, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-pdk-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- FIXTURE: one loaded PDK "fixpdk" with three components; a load answers "fixload" --------------------------------
const summary = (n, fam) => ({ devices: n, cells: n, by_family: fam, with_problems: [] });
const entry = (id, n, fam, sha) => ({ pdk_id: id, vocabulary: `pdk:${id}`, sha256: sha, version: `pdk-${id}-${sha.slice(0, 16)}`, loaded_utc: '2026-09-21T21:00:00+00:00',
  technology_library: id, summary: summary(n, fam), label: `PDK ${id} (${n} components, version ${sha.slice(0, 8)})`, sources: { model_files: [{ path: `/fixture/${id}.scs`, bytes: 10, sha256: sha }] },
  columns: 12, kinds: 8 + n, roles: 10 });
const DEVICES = [
  { model: 'fx_nch', kind: 'fixpdk:fx_nch', cells: ['nmosfx', 'nmosfx_3'], family: 'mos', polarity: 'n', family_basis: 'FIXTURE inline subcircuit', problems: [],
    pins: [{ name: 'D', role: 'drain' }, { name: 'G', role: 'gate' }, { name: 'S', role: 'source' }, { name: 'B', role: 'bulk' }],
    parameters: [{ name: 'w', column: 'w', unit: 'm', numeric: true }, { name: 'l', column: 'l', unit: 'm', numeric: true }, { name: 'region', numeric: false }] },
  { model: 'fx_npn', kind: 'fixpdk:fx_npn', cells: ['npnfx'], family: 'bjt', polarity: 'npn', family_basis: 'FIXTURE model = bjt', problems: [],
    pins: [{ name: 'C', role: 'collector' }, { name: 'B', role: 'base' }, { name: 'E', role: 'emitter' }, { name: 'S', role: 'bulk' }],
    parameters: [{ name: 'area', column: 'bjt.area', unit: null, numeric: true }, { name: 'm', column: 'm', unit: 'count', numeric: true }] },
  { model: 'fx_ind', kind: 'fixpdk:fx_ind', cells: ['indfx'], family: 'inductor', polarity: null, family_basis: 'FIXTURE inductor', problems: [],
    pins: [{ name: 'PLUS', role: 'positive' }, { name: 'MINUS', role: 'negative' }, { name: 'B', role: 'bulk' }],
    parameters: [{ name: 'r', column: 'rad', unit: 'm', numeric: true }, { name: 'nr', column: 'nr', unit: null, numeric: true }] },
];
const FIXPDK = entry('fixpdk', 3, { 'mos:n': 1, 'bjt:npn': 1, inductor: 1 }, 'a'.repeat(64));
const FIXLOAD = entry('fixload', 2, { resistor: 2 }, 'b'.repeat(64));
const details = (e, devices) => ({ ...e, devices, not_netlisted: [{ cell: 'ringfx', reason: 'FIXTURE: no Spectre entry' }], layout_only: [{ cell: 'crossfx', views: ['layout'] }],
  not_used: ['fx_core'], parameters: [], terminal_roles: [] });
const STANDARD = { vocabulary: 'standard', label: 'standard (8 generic kinds)', kinds: [], parameters: [] };
const VALID = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const stored = await (await fetch(new URL('api/network-settings', APP))).json();
  const net = { encoder_type: stored.default_encoder, ...stored.settings[stored.default_encoder].network };
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'scratch', connection_profile_id: 'fixture-link', network: net,
    advanced: { ...(starter.run.advanced ?? {}), ...stored.settings[stored.default_encoder].advanced } }, output: { experiment_name: 'fixture' }, research: {} };
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const refused = [];
  let loaded = false, listReads = 0, loadBodies = [], holdLoad = null;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = async ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/pdks') { listReads++; return fulfil(requestId, 200, { pdks: loaded ? [FIXPDK, FIXLOAD] : [FIXPDK], standard: STANDARD }); }
    if (name === '/api/pdks/fixpdk') return fulfil(requestId, 200, details(FIXPDK, DEVICES));
    if (name === '/api/pdks/load') {
      loadBodies.push(JSON.parse(request.postData ?? 'null'));
      await new Promise(resolve => { holdLoad = resolve; });                       // held until the check has seen "Reading..."
      loaded = true;
      return fulfil(requestId, 200, details(FIXLOAD, [{ ...DEVICES[2], model: 'fx_res', kind: 'fixload:fx_res', family: 'resistor', cells: ['resfx'] }]));
    }
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    // No connection profile at all (FIXTURE): the page would otherwise pick the backend's active one on its own.
    if (name === '/api/connection/profiles') return fulfil(requestId, 200, { exists: false, file: 'FIXTURE', active: null, profiles: [], kinds: [] });
    // The page's own start-up reads: they only read (a circuit, an output root's writability without creating it).
    if (['/api/circuit/load', '/api/output/check'].includes(name) && !(request.postData ?? '').includes('"create":true'))
      return send('Fetch.continueRequest', { requestId });
    if (request.method === 'GET') return send('Fetch.continueRequest', { requestId });
    refused.push(`${request.method} ${name}`);
    return fulfil(requestId, 418, { detail: { message: 'FIXTURE: this check lets no writing request through' } });
  };
  const sessions = new Map();                      // a second socket for the PDK window
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  // A page that is still rendering (after a reload) answers "not yet", not an error.
  const until = async (expression, tries = 60) => { for (let i = 0; i < tries; i++) { if (await evaluate(`(() => { try { return !!(${expression}); } catch { return false; } })()`)) return true; await sleep(100); } return false; };
  const RUN = `[...document.querySelectorAll('.right .panel')].find(p => p.querySelector('h3')?.textContent.trim() === 'Run configuration')`;
  const LIST = `${RUN}.querySelector('.component-list')`;
  const SELECT = `${LIST}.querySelector('select')`;
  const ENCODER = `[...${RUN}.querySelectorAll('label')].find(l => l.firstChild?.textContent?.trim() === 'Encoder')?.querySelector('select')`;
  const choose = (select, value) => evaluate(`(() => { const s = ${select}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)}); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const storedNetwork = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? '{}').run?.network ?? null`);
  // The page keeps its configuration in this browser 800 ms after the last change (store.ts): wait for it, then read it.
  const storedWhen = async test => { for (let i = 0; i < 40; i++) { const n = await storedNetwork(); if (test(n)) return n; await sleep(100); } return storedNetwork(); };
  const shotOf = async (socketSend, evaluateIn, selector, name) => {
    const clip = await evaluateIn(`(() => { const e = ${selector}; e.scrollIntoView({ block: 'start' }); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: Math.min(1400, r.height), scale: 1 }; })()`);
    const { data } = await socketSend('Page.captureScreenshot', { format: 'png', clip, captureBeyondViewport: true });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (!localStorage.getItem('gator-workbench-config-v1')) localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))});` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${RUN})`, 150))) throw new Error('the Run configuration never appeared: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  if (!(await until(`!!(${LIST})`, 50))) throw new Error('no component list: the served frontend is older than this change (build it, then reload)');
  await until(`${SELECT}.options.length > 1`, 50);

  // ---- the line in the RL network block ---------------------------------------------------------------------------------
  const line = await evaluate(`(() => { const l = ${LIST}, s = l.querySelector('select'), b = l.querySelector('button.pdk-open'), r = l.querySelector('.component-row');
    return { label: r.querySelector('label').firstChild.textContent.trim(), value: s.value, options: [...s.options].map(o => [o.value, o.textContent]), button: b?.textContent,
      sameRow: !!b && b.parentElement === r, what: l.querySelector('.component-what')?.textContent ?? '', helpFolded: !l.querySelector('details.component-help').open,
      afterEncoder: !!(${ENCODER}) && (${ENCODER}.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING) > 0 }; })()`);
  check('the RL network block has a "Components" list after the encoder', line.label === 'Components' && line.afterEncoder, JSON.stringify(line.label));
  check('standard is chosen and listed first, the loaded PDK after it', line.value === 'standard' && line.options[0][0] === 'standard'
    && line.options[1]?.[0] === 'pdk:fixpdk' && line.options[1][1] === FIXPDK.label, JSON.stringify(line.options));
  check('a short "Load PDK..." button stands beside the list', line.button === 'Load PDK...' && line.sameRow, String(line.button));
  check('the plain line says what the standard list knows and what it does not', /MOS, R, C, L and sources/.test(line.what) && /"unknown"/.test(line.what), line.what);
  check('the longer explanation is folded (closed <details>)', line.helpFolded);
  check('page load read the list of loaded PDKs (local files) and started no load', listReads >= 1 && loadBodies.length === 0);
  const fits = await evaluate(`(() => { const right = document.querySelector('.right'), panel = ${RUN}.getBoundingClientRect(), row = ${LIST}.querySelector('.component-row'),
    button = row.querySelector('button').getBoundingClientRect(), select = row.querySelector('select').getBoundingClientRect();
    return { noSideScroll: right.scrollWidth <= right.clientWidth + 1, inside: button.right <= panel.right + 1 && select.left >= panel.left - 1,
      oneLine: Math.abs((button.top + button.bottom) / 2 - (select.top + select.bottom) / 2) < 4 }; })()`);
  check('the list and its button fit the narrow column on one line, with no sideways scrolling', fits.noSideScroll && fits.inside && fits.oneLine, JSON.stringify(fits));

  // ---- choosing a list --------------------------------------------------------------------------------------------------
  await choose(SELECT, 'pdk:fixpdk');
  let network = await storedWhen(n => n?.vocabulary === 'pdk:fixpdk');
  check('choosing the PDK writes run.network.vocabulary', network?.vocabulary === 'pdk:fixpdk', JSON.stringify(network));
  const what = await evaluate(`${LIST}.querySelector('.component-what').textContent`);
  check('... and the line names its components by family', /Knows all 3 components of fixpdk: 1 n-MOS, 1 npn, 1 inductor/.test(what), what);
  const other = await evaluate(`[...${ENCODER}.options].map(o => o.value).find(v => v !== ${ENCODER}.value)`);
  await choose(ENCODER, other);
  network = await storedWhen(n => n?.encoder_type === other);
  check('another encoder keeps the chosen list', network?.encoder_type === other && network?.vocabulary === 'pdk:fixpdk', JSON.stringify(network));
  await choose(ENCODER, net.encoder_type);
  await storedWhen(n => n?.encoder_type === net.encoder_type);
  await choose(SELECT, 'standard');
  network = await storedWhen(n => n && !('vocabulary' in n));
  check('the standard list is written as no field at all', network && !('vocabulary' in network), JSON.stringify(network));

  // ---- the window ---------------------------------------------------------------------------------------------------------
  await evaluate(`${LIST}.querySelector('button.pdk-open').click()`);
  let popup;
  for (let i = 0; i < 50 && !popup; i++) { popup = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page' && t.title === 'GATOR - PDK'); if (!popup) await sleep(100); }
  check('"Load PDK..." opens the PDK window', !!popup);
  const pws = new WebSocket(popup.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { pws.onopen = resolve; pws.onerror = reject; });
  let pid = 0; const ppending = new Map();
  pws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id) { const p = ppending.get(m.id); ppending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); } };
  const psend = (method, params = {}) => new Promise((resolve, reject) => { const id = ++pid; ppending.set(id, { resolve, reject }); pws.send(JSON.stringify({ id, method, params })); });
  const pev = async expression => { const r = await psend('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text); return r.result.value; };
  const puntil = async (expression, tries = 60) => { for (let i = 0; i < tries; i++) { if (await pev(`(() => { try { return !!(${expression}); } catch { return false; } })()`)) return true; await sleep(100); } return false; };
  await psend('Emulation.setDeviceMetricsOverride', { width: 1100, height: 900, deviceScaleFactor: 1, mobile: false });
  await puntil(`!!document.querySelector('.pdk-window')`);
  const win = await pev(`(() => { const w = document.querySelector('.pdk-window'); return { heading: w.querySelector('h2')?.textContent, inputs: [...w.querySelectorAll('.pdk-form input')].map(i => i.placeholder),
    load: w.querySelector('button.pdk-load')?.textContent, disabled: w.querySelector('button.pdk-load')?.disabled, link: w.textContent.includes('Through connection fixture-link'),
    rows: [...w.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent), folded: !w.querySelector('details').open }; })()`);
  check('the window shows "Load PDK" with its two optional boxes and a Load button', win.heading === 'Load PDK' && win.inputs.length === 2 && win.load === 'Load' && !win.disabled, JSON.stringify(win));
  check('it names the connection it reads through', win.link);
  check('it lists the loaded PDKs; the how-it-decides text is folded', JSON.stringify(win.rows) === '["fixpdk"]' && win.folded, JSON.stringify(win.rows));
  await pev(`document.querySelector('.pdk-list tbody tr').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  await puntil(`!!document.querySelector('.pdk-devices')`);
  const shown = await pev(`(() => { const t = document.querySelector('.pdk-devices'); return { rows: [...t.querySelectorAll('tbody tr')].map(r => [...r.cells].map(c => c.textContent)),
    head: document.querySelector('.pdk-details h3')?.textContent, hint: document.querySelector('.pdk-details .hint')?.textContent }; })()`);
  check('a double click shows the PDK: one row per component', shown.rows.length === 3 && shown.head === 'fixpdk: 3 components', JSON.stringify(shown.head));
  const bjt = shown.rows.find(r => r[1] === 'fx_npn') ?? [];
  check('each row names its kind, cells, pins with roles and the parameters the network reads', bjt[0] === 'npn' && bjt[2] === 'npnfx'
    && bjt[3] === 'C collector, B base, E emitter, S bulk' && bjt[4] === 'area = bjt.area, m (count)', JSON.stringify(bjt));
  check('... a parameter kept under another column is shown so (the inductor radius)', shown.rows.some(r => r[1] === 'fx_ind' && r[4].startsWith('r = rad (m)')));
  check('a non-numeric setting is not listed as something the network reads', !shown.rows.find(r => r[1] === 'fx_nch')[4].includes('region'));
  await shotOf(psend, pev, `document.querySelector('.pdk-window')`, 'pdk-window-1-shown.png');

  // ---- Load ---------------------------------------------------------------------------------------------------------------
  await pev(`(() => { const i = document.querySelectorAll('.pdk-form input')[0]; i.focus(); i.select(); })()`);
  await psend('Input.insertText', { text: 'fixload' }); await sleep(200);
  const readsBefore = listReads;
  pev(`document.querySelector('button.pdk-load').click()`).catch(() => undefined);
  const reading = await puntil(`document.querySelector('button.pdk-load')?.textContent === 'Reading...' && document.querySelector('button.pdk-load').disabled`, 40);
  check('while it reads, the button says "Reading..." and cannot be pressed again', reading);
  for (let i = 0; i < 50 && !holdLoad; i++) await sleep(100);      // the button changes before the request is under way
  holdLoad?.();
  await puntil(`document.querySelector('.pdk-details h3')?.textContent === 'fixload: 2 components'`, 60);
  check('Load sent exactly the typed fields (empty model file = the connection\'s)', JSON.stringify(loadBodies) === JSON.stringify([{ profile_id: 'fixture-link', technology_library: 'fixload', model_file: null }]), JSON.stringify(loadBodies));
  check('the answer is shown and the list read again', (await pev(`[...document.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent).join()`)) === 'fixpdk,fixload' && listReads > readsBefore);
  await until(`[...${SELECT}.options].some(o => o.value === 'pdk:fixload')`, 30);
  check('the newly loaded PDK can be chosen in the RL network block at once', await evaluate(`[...${SELECT}.options].some(o => o.value === 'pdk:fixload')`));
  await sleep(300);
  {                                              // the encoder row down to the component list, in a tall viewport
    await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 2600, deviceScaleFactor: 1, mobile: false }); await sleep(300);
    const clip = await evaluate(`(() => { ${ENCODER}.scrollIntoView({ block: 'start' }); const a = ${ENCODER}.closest('label').getBoundingClientRect(), b = ${LIST}.getBoundingClientRect();
      return { x: Math.min(a.x, b.x) - 4, y: a.y - 4, width: Math.max(a.right, b.right) - Math.min(a.x, b.x) + 8, height: b.bottom - a.y + 8, scale: 1.5 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, 'pdk-2-list.png'), Buffer.from(data, 'base64'));
    await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  }

  // ---- no connection; a list that is not loaded --------------------------------------------------------------------------------
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', JSON.stringify({ ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')),
    run: { ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run, connection_profile_id: null, network: { ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.network, vocabulary: 'pdk:gone' } } }))`);
  loaded = false;
  await send('Page.reload'); await until(`!!(${LIST}) && ${SELECT}.options.length > 1`, 150); await sleep(500);
  const gone = await evaluate(`(() => { const l = ${LIST}; return { value: l.querySelector('select').value, option: [...l.querySelectorAll('option')].map(o => o.textContent).pop(), warn: l.querySelector('.warn')?.textContent ?? '' }; })()`);
  check('a configuration naming a PDK that is not loaded says so', gone.value === 'pdk:gone' && gone.option === 'PDK gone (not loaded)' && /not loaded here/.test(gone.warn), JSON.stringify(gone));
  await evaluate(`${LIST}.querySelector('button.pdk-open').click()`); await sleep(800);
  let popup2;
  for (let i = 0; i < 50 && !popup2; i++) { popup2 = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page' && t.title === 'GATOR - PDK'); if (!popup2) await sleep(100); }
  if (popup2 && popup2.webSocketDebuggerUrl !== popup.webSocketDebuggerUrl) {
    pws.close();
    const ws2 = new WebSocket(popup2.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws2.onopen = resolve; ws2.onerror = reject; });
    let id2 = 0; const pend2 = new Map();
    ws2.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id) { const p = pend2.get(m.id); pend2.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); } };
    const ev2 = async expression => { const r = await new Promise((resolve, reject) => { const i = ++id2; pend2.set(i, { resolve, reject }); ws2.send(JSON.stringify({ id: i, method: 'Runtime.evaluate', params: { expression, returnByValue: true, awaitPromise: true } })); }); return r.result.value; };
    for (let i = 0; i < 40 && !(await ev2(`!!document.querySelector('.pdk-window')`)); i++) await sleep(100);
    const none = await ev2(`({ disabled: document.querySelector('button.pdk-load')?.disabled, warn: document.querySelector('.pdk-window .warn')?.textContent ?? '' })`);
    check('without a connection, Load cannot be pressed and the window says what to do', none.disabled === true && /Choose a connection first/.test(none.warn), JSON.stringify(none));
    ws2.close();
  } else check('without a connection, the window opens again after a reload', false, 'no second window');

  check('no writing request other than the canned ones reached the backend', refused.length === 0, refused.join(', '));
  check('no uncaught error in the page', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
  ws.close();
} catch (error) {
  failures++;
  console.log('FAIL  the check could not run: ' + (error?.stack ?? error));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; it is a temp dir */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
