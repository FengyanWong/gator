// Browser check of the "Connection" button and its window (there is no frontend test runner in this project).
// Same approach as agent_tab_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY request to /api/connection/* is intercepted, logged and answered
// with a canned answer labelled FIXTURE, so no probe is started, no tunnel is touched, no file is written and neither
// Virtuoso nor ngspice is contacted. That makes it safe against the live backend; it needs only the built page.
// What it pins:
//   * the connection block of the left column is ONE button, and pressing it opens the connection window (user request
//     2026-09-21); the window is a second browser window, found by its title and driven over a second DevTools session;
//   * the four kinds of connection - Virtuoso over SSH / on this machine, ngspice on this machine / over SSH - each with
//     its own steps and wording, and "Add a connection" sending names only;
//   * (user request 2026-09-20) NO check on page load, NO check when the window opens, NO timer (the old panel polled
//     every 15 s, so each quiet period here lasts 17 s), one check per button press, a result that stays until the next.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 60 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/connection_panel_check.mjs)" [screenshot-dir]
// With GATOR_CONNECTION_LIVE=1 a last section lets the requests THROUGH to the backend: only ever against a scratch
// backend with its own GATOR_WORKBENCH_SETTINGS_DIR (it adds a connection to that folder and runs the real ngspice test).
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9379, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const LIVE = process.env.GATOR_CONNECTION_LIVE === '1';
const QUIET_MS = 17000;
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-conn-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const VIRTUOSO = ['bridge_package', 'connection_profile', 'tunnel', 'daemon', 'session_readiness', 'spectre', 'spectre_license'];
const NGSPICE = ['connection_profile', 'ssh', 'ngspice', 'trial_run'];
const KINDS = [
  { kind: 'virtuoso_ssh', family: 'virtuoso', transport: 'ssh', label: 'Virtuoso over SSH', summary: 'FIXTURE summary: Virtuoso on another machine.' },
  { kind: 'virtuoso_local', family: 'virtuoso', transport: 'local', label: 'Virtuoso on this machine', summary: 'FIXTURE summary: Virtuoso on this machine.' },
  { kind: 'ngspice_local', family: 'ngspice', transport: 'local', label: 'ngspice on this machine', summary: 'FIXTURE summary: ngspice on this machine.' },
  { kind: 'ngspice_ssh', family: 'ngspice', transport: 'ssh', label: 'ngspice over SSH', summary: 'FIXTURE summary: ngspice on another machine.' }];
const PROFILES = { lab: 'virtuoso_ssh', here: 'virtuoso_local', sim: 'ngspice_local', far: 'ngspice_ssh' };
const kindOf = id => KINDS.find(k => k.kind === PROFILES[id]);
const SETUP = '/fixture/virtuoso_setup.il';
const layersOf = (id, state, reason, upTo = 99) => (kindOf(id).family === 'ngspice' ? NGSPICE : VIRTUOSO).map((layer, i) => ({ layer, state: i < upTo ? state : 'not_checked',
  reason_code: i < upTo ? reason : null, diagnostic: null, details: layer === 'tunnel' ? { setup_path: SETUP } : {} }));
const ciw = { load: `load("${SETUP}")`, replace_running_daemon: ['RBStop()', `load("${SETUP}")`], setup_path: SETUP, notes: ['FIXTURE'] };
const utc = ms => new Date(ms).toISOString().replace('Z', '+00:00');             // the backend sends an explicit UTC offset
const described = id => ({ kind: kindOf(id).kind, family: kindOf(id).family, transport: kindOf(id).transport, kind_label: kindOf(id).label });
const publicProfile = (id, declared = true) => ({ profile_id: id, bridge_profile: null, kind: kindOf(id).kind, kind_declared: declared, family: kindOf(id).family,
  transport: kindOf(id).transport, kind_label: kindOf(id).label, settings_present: ['kind'] });
const fixtures = {
  profiles: () => ({ active: 'lab', connection_file: '/fixture/bridge_connection.json', connection_file_exists: true, kinds: KINDS,
    profiles: Object.keys(PROFILES).map(id => publicProfile(id, id !== 'lab')) }),                  // `lab` was written before kinds existed
  never: id => ({ profile_id: id, ...described(id), checked_utc: null, age_seconds: null, stale: true, overall: 'unknown', layers: layersOf(id, 'unknown', 'never_checked'),
    summary: { level: 'unknown', headline: 'Not tested yet.', broken_layer: null, next_step: null }, ciw: null }),
  tested: (id, scope) => ({ profile_id: id, ...described(id), scope, trigger: 'user', checked_utc: utc(Date.now()), duration_seconds: 0.4, age_seconds: 0, stale: false,
    overall: 'ok', run_active: false, layers: layersOf(id, 'ok', null, kindOf(id).family === 'ngspice' ? 4 : scope === 'full' ? 7 : scope === 'cheap' ? 3 : 5),
    ciw: kindOf(id).family === 'ngspice' ? null : ciw,
    summary: { level: 'ok', headline: `FIXTURE: ${id} connected (canned answer, nothing was probed).`, broken_layer: null, next_step: null } }),
  old: id => ({ profile_id: id, ...described(id), scope: 'interactive', trigger: 'user', checked_utc: utc(Date.now() - 600000), duration_seconds: 0.4, age_seconds: 600,
    stale: true, overall: 'unknown', run_active: false, layers: layersOf(id, 'unknown', 'stale_result'), ciw,
    summary: { level: 'unknown', headline: 'The last test is too old to trust - test again.', broken_layer: null, next_step: null } }),
  setup: { env_file: '/fixture/.env', env_file_exists: true, bridge_importable: true, bridge_site_packages: null, problems: [], can_create: true,
    kinds: KINDS.map(k => ({ ...k, can_create: k.kind !== 'virtuoso_local' || true, problems: [], note: `FIXTURE note for ${k.kind}`,
      checks: [{ ok: true, text: `FIXTURE found for ${k.kind}` }], ...(k.kind === 'ngspice_ssh' ? { ssh_hosts: ['simhost', 'sim2'] } : {}) })) },
};

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const seen = []; const consoleErrors = []; let statusAnswer = fixtures.never; let live = false;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = ({ requestId, request }) => {                                    // every connection request: log it, answer it here
    const url = new URL(request.url), name = url.pathname.replace('/api/connection/', '');
    const body = request.postData ? JSON.parse(request.postData) : null;
    seen.push({ method: request.method, name, body, at: Date.now() });
    if (live) return send('Fetch.continueRequest', { requestId });                // the last section only: a scratch backend answers
    if (request.method === 'GET' && name === 'profiles') return fulfil(requestId, 200, fixtures.profiles());
    if (request.method === 'GET' && name === 'status') return fulfil(requestId, 200, statusAnswer(url.searchParams.get('profile_id')));
    if (request.method === 'GET' && name === 'setup') return fulfil(requestId, 200, fixtures.setup);
    if (request.method === 'POST' && name === 'check') return fulfil(requestId, 200, fixtures.tested(body.profile_id, body.scope));
    if (request.method === 'POST' && name === 'connect') return fulfil(requestId, 200, { connect: { ok: true, action: 'started', reason_code: null, diagnostic: null,
      duration_seconds: 1.2, details: { mode: kindOf(body.profile_id).transport === 'local' ? 'local' : 'remote', ciw } }, status: fixtures.tested(body.profile_id, 'cheap') });
    if (request.method === 'POST' && name === 'profile') { PROFILES[body.profile_id] = body.kind;
      return fulfil(requestId, 200, { created: true, profile_id: body.profile_id, kind: body.kind, backup: '/fixture/bridge_connection.json.before-FIXTURE', note: 'FIXTURE note.', profiles: fixtures.profiles() }); }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${request.method} ${name} is not expected in this check` } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away (reload) */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async (expression, userGesture = false) => {                   // userGesture: a click that may open a window
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const names = (from = 0) => seen.slice(from).map(s => `${s.method} ${s.name}`);
  const settle = async (mark, ms = 4000) => { for (let waited = 0; waited < ms && seen.length === mark; waited += 100) await sleep(100); await sleep(500); };

  // ---- the window: a second page, found by its title, with a DevTools session of its own ---------------------------
  const pages = async () => (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).filter(t => t.type === 'page');
  const windowTarget = async (present, ms = 5000) => { for (let waited = 0; waited < ms; waited += 100) { const found = (await pages()).find(t => t.id !== target.id && t.title === 'GATOR - connection'); /* by title: Edge may open pages of its own */ if (!!found === present) return found ?? null; await sleep(100); } throw new Error(`the connection window did not ${present ? 'appear' : 'close'}`); };
  const attachTo = async page => {
    const socket = new WebSocket(page.webSocketDebuggerUrl); await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let id = 0; const waiting = new Map();
    socket.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id) { const w = waiting.get(m.id); waiting.delete(m.id); m.error ? w.reject(new Error(JSON.stringify(m.error))) : w.resolve(m.result); }
      else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push('window: ' + (m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text)); };
    const call = (method, params = {}) => new Promise((resolve, reject) => { const n = ++id; waiting.set(n, { resolve, reject }); socket.send(JSON.stringify({ id: n, method, params })); });
    await call('Runtime.enable');
    const run = async (expression, userGesture = false) => { const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text); return r.result.value; };
    return { call, run, close: () => socket.close() };
  };
  const BUTTON = `document.querySelector('.left button.connection-button')`;
  const WINDOW = `document.querySelector('.connection-window')`;
  let far = null, farPage = null;
  const openWindow = async () => {
    await evaluate(`${BUTTON}.click()`, true);
    farPage = await windowTarget(true);
    far = await attachTo(farPage);
    await far.call('Emulation.setDeviceMetricsOverride', { width: 660, height: 920, deviceScaleFactor: 1, mobile: false });   // a headless popup ignores the requested size
    for (let i = 0; i < 50 && !(await far.run(`!!(${WINDOW})`)); i++) await sleep(100);
    await sleep(400);
  };
  const text = () => far.run(`${WINDOW}.innerText`);
  const badge = () => far.run(`${WINDOW}.querySelector('.badge').textContent`);
  const hint = () => far.run(`${WINDOW}.querySelector('.badge').nextElementSibling.textContent`);
  const buttons = () => far.run(`[...${WINDOW}.querySelectorAll('button')].map(b => b.textContent.trim())`);
  const press = label => far.run(`(() => { const b = [...${WINDOW}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)}); if (!b) return false; b.click(); return true; })()`, true);
  const choose = (selector, value) => far.run(`(() => { const s = ${WINDOW}.querySelector(${JSON.stringify(selector)}); if (!s) return false;
    Object.getOwnPropertyDescriptor(s.ownerDocument.defaultView.HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)});
    s.dispatchEvent(new s.ownerDocument.defaultView.Event('change', { bubbles: true })); return true; })()`);
  const shot = async (session, selector, name) => {
    const expression = `(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: Math.min(r.height, 1400), scale: 2 }; })()`;
    const clip = session === 'main' ? await evaluate(expression) : await far.run(expression);
    const { data } = await (session === 'main' ? send : far.call)('Page.captureScreenshot', { format: 'png', clip, captureBeyondViewport: true });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };
  const loaded = async (connection = 'lab') => {
    for (let i = 0; i < 100 && !(await evaluate(`!!(${BUTTON})`)); i++) await sleep(100);
    for (let i = 0; i < 50 && !(await evaluate(`${BUTTON}?.textContent.includes(${JSON.stringify(connection)})`)); i++) await sleep(100);
    await sleep(1500);                                                           // room for anything the page would do on its own
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/connection/*', requestStage: 'Request' }] });
  await send('Page.navigate', { url: APP });
  await loaded();

  // ---- the left column: ONE button ----------------------------------------------------------------------------------
  const block = await evaluate(`(() => { const b = ${BUTTON}, panel = b?.closest('.panel'); return b ? { text: b.innerText.replace(/\\s+/g, ' ').trim(),
    controls: panel.querySelectorAll('button, select, input, a, summary').length, headings: [...document.querySelectorAll('.left h3')].map(h => h.textContent.trim()),
    height: Math.round(panel.getBoundingClientRect().height), first: panel === document.querySelector('.left').firstElementChild } : null; })()`);
  check('the connection block of the left column is ONE button', !!block && block.controls === 1 && block.first, JSON.stringify(block));
  check('it is called "Connection" and names the connection in use, its kind and the last state', !!block && /^Connection\s*lab - Virtuoso over SSH\s*UNKNOWN$/.test(block.text), block?.text);
  check('the old panel (heading, steps, profile select) is gone from the column', !!block && !block.headings.some(h => /connection/i.test(h)) && block.height < 90, JSON.stringify(block));   // two lines of text; the old panel was > 300 px
  check('page load reads the profiles and the cached status once each', JSON.stringify(names().sort()) === JSON.stringify(['GET profiles', 'GET status']), names().join(', '));
  check('page load starts NO check', !seen.some(s => s.method === 'POST'), names().join(', '));
  await shot('main', '.left', 'connection-1-left-column.png');

  // ---- pressing it opens the connection window; opening checks nothing ----------------------------------------------
  let mark = seen.length;
  await openWindow();
  check('pressing the button opens a window of its own, titled "GATOR - connection"', !!farPage && farPage.title === 'GATOR - connection');
  check('the window shows the block under the heading "Connection"', (await far.run(`${WINDOW}.querySelector('h2')?.textContent`)) === 'Connection');
  check('opening the window sends NO request at all', seen.length === mark, names(mark).join(', '));
  check('an untested link reads "never tested" / UNKNOWN', (await hint()) === 'never tested' && (await badge()) === 'UNKNOWN', `${await badge()} | ${await hint()}`);
  check('the button says the window is open', (await evaluate(`${BUTTON}.textContent`)).includes('(window open)'));
  const styled = await far.run(`(() => { const s = getComputedStyle(${WINDOW}.querySelector('.step-no')); return s.borderRadius !== '0px' && s.color === 'rgb(255, 255, 255)'; })()`);
  check('the window carries the workbench style sheet', styled);

  // ---- Virtuoso over SSH: the three steps, as before ----------------------------------------------------------------
  let shown = await text();
  check('Virtuoso over SSH: 1 Connect SSH, 2 CIW line, 3 Test', shown.includes('Connect to the target over SSH') && shown.includes('Load the bridge in the Virtuoso CIW')
    && shown.includes('Test the connection') && (await buttons()).includes('Connect SSH') && (await buttons()).includes('+ Spectre / license'));
  check('a connection written before kinds existed says so', shown.includes('written before kinds existed'));
  await shot('window', '.connection-window', 'connection-2-window-virtuoso-ssh.png');

  // ---- no timer ---------------------------------------------------------------------------------------------------
  mark = seen.length;
  await sleep(QUIET_MS);
  check(`no request in ${QUIET_MS / 1000} s without a press (the old panel polled every 15 s)`, seen.length === mark, names(mark).join(', '));

  // ---- one press = one check; the result stays ------------------------------------------------------------------
  mark = seen.length;
  await press('Test connection');
  await settle(mark);
  let pressed = seen.slice(mark);
  check('"Test connection" sends exactly one check', pressed.length === 1 && pressed[0].method === 'POST' && pressed[0].name === 'check', names(mark).join(', '));
  check('it is a user-triggered interactive check of the chosen profile', JSON.stringify(pressed[0]?.body) === JSON.stringify({ profile_id: 'lab', scope: 'interactive', trigger: 'user' }), JSON.stringify(pressed[0]?.body));
  const testedHint = await hint();
  check('the result shows the clock time of the test, not a running age', /^tested at \d/.test(testedHint) && !/ago|STALE|too old/.test(testedHint), testedHint);
  check('the result is shown (OK + the headline)', (await badge()) === 'OK' && (await text()).includes('FIXTURE: lab connected'), await badge());
  check('the CIW load line appears', (await text()).includes(`load("${SETUP}")`));
  check('the button in the left column shows the new state too', (await evaluate(`${BUTTON}.querySelector('.badge').textContent`)) === 'OK');
  await shot('window', '.connection-window', 'connection-3-window-tested.png');

  mark = seen.length;
  await sleep(QUIET_MS);
  check(`still no request ${QUIET_MS / 1000} s after the test`, seen.length === mark, names(mark).join(', '));
  check('the shown result did not change by itself', (await hint()) === testedHint && (await badge()) === 'OK', `${await badge()} | ${await hint()}`);

  // ---- the other three kinds: own steps, own words ---------------------------------------------------------------------
  const select = async id => { const before = seen.length; await choose('select', id); await settle(before); return seen.slice(before); };
  let switched = await select('here');
  shown = await text();
  check('choosing another connection reads its cached status once and checks nothing', switched.length === 1 && switched[0].method === 'GET' && switched[0].name === 'status', switched.map(s => `${s.method} ${s.name}`).join(', '));
  check('Virtuoso on this machine: "Set up local bridge", no SSH wording in the steps', shown.includes('Set up the bridge on this machine') && (await buttons()).includes('Set up local bridge')
    && !(await buttons()).includes('Connect SSH') && shown.includes('no SSH and no tunnel') && shown.includes('Load the bridge in the Virtuoso CIW'), (await buttons()).join(' | '));
  mark = seen.length;
  await press('Set up local bridge');
  await settle(mark);
  pressed = seen.slice(mark);
  check('"Set up local bridge" sends one connect with the profile name and nothing else', pressed.length === 1 && pressed[0].name === 'connect' && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'here' }), JSON.stringify(pressed.map(p => p.body)));
  check('its result is worded for this machine', (await text()).includes('Local bridge set up (1.2 s).') && (await buttons()).includes('Set up local bridge (already done)'));
  await shot('window', '.connection-window', 'connection-4-window-virtuoso-local.png');

  await select('sim');
  shown = await text();
  check('ngspice on this machine: ONE step - test; no connect step, no CIW step, no Spectre button', shown.includes('Test ngspice on this machine') && !shown.includes('Virtuoso CIW')
    && JSON.stringify((await buttons()).filter(b => !/Add a connection/.test(b))) === JSON.stringify(['Test connection', 'Details']), (await buttons()).join(' | '));
  check('what an ngspice connection cannot do yet is said plainly, as a neutral note (not as an error)', shown.includes('can do today: be tested') && shown.includes('not built yet')
    && (await far.run(`!!${WINDOW}.querySelector('.note') && !${WINDOW}.querySelector('.note.error, .note .error, .blocker')`)));
  mark = seen.length;
  await press('Test connection');
  await settle(mark);
  pressed = seen.slice(mark);
  check('testing ngspice sends one interactive check of that connection', pressed.length === 1 && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'sim', scope: 'interactive', trigger: 'user' }), JSON.stringify(pressed.map(p => p.body)));
  await press('Details');
  await sleep(300);
  const rows = await far.run(`[...${WINDOW}.querySelectorAll('table.grid tbody tr td:first-child')].map(td => td.textContent)`);
  check('Details lists the four ngspice layers, and says the one simulation is the built-in test circuit', JSON.stringify(rows) === JSON.stringify(NGSPICE) && (await text()).includes('built-in three-element test circuit, never one of yours'), rows.join(', '));
  await shot('window', '.connection-window', 'connection-5-window-ngspice-local.png');
  await press('Hide');

  await select('far');
  shown = await text();
  check('ngspice over SSH: says that it needs key-based login', shown.includes('Test ngspice over SSH') && shown.includes('key-based login') && !(await buttons()).includes('Connect SSH'));

  // ---- add a connection: names only ------------------------------------------------------------------------------------
  mark = seen.length;
  await press('Add a connection...');
  await settle(mark);
  check('"Add a connection..." looks at what is installed (one GET setup) only when pressed', JSON.stringify(names(mark)) === JSON.stringify(['GET setup']), names(mark).join(', '));
  const kindsOffered = await far.run(`[...${WINDOW}.querySelectorAll('.connection-add select')[0].options].map(o => o.textContent)`);
  check('the four kinds are offered', JSON.stringify(kindsOffered) === JSON.stringify(KINDS.map(k => k.label)), kindsOffered.join(' | '));
  await choose('.connection-add select', 'ngspice_ssh');
  await sleep(300);
  const form = await far.run(`(() => { const add = ${WINDOW}.querySelector('.connection-add'); return { hosts: [...add.querySelectorAll('select')[1].options].map(o => o.textContent),
    name: add.querySelector('input').value, inputs: add.querySelectorAll('input').length, text: add.innerText }; })()`);
  check('ngspice over SSH offers the Host names of ~/.ssh/config as a list - there is no box to type an address into', JSON.stringify(form.hosts) === JSON.stringify(['simhost', 'sim2']) && form.inputs === 1 && form.name === 'ngspice-ssh', JSON.stringify(form));
  await shot('window', '.connection-window', 'connection-6-window-add.png');
  await far.run(`(() => { const s = ${WINDOW}.querySelectorAll('.connection-add select')[1]; Object.getOwnPropertyDescriptor(s.ownerDocument.defaultView.HTMLSelectElement.prototype, 'value').set.call(s, 'sim2');
    s.dispatchEvent(new s.ownerDocument.defaultView.Event('change', { bubbles: true })); })()`);
  await sleep(200);
  mark = seen.length;
  await press('Create connection');
  await settle(mark);
  pressed = seen.slice(mark).filter(s => s.method === 'POST');
  check('"Create connection" sends a name, a kind and a Host NAME - nothing else', pressed.length === 1 && pressed[0].name === 'profile'
    && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'ngspice-ssh', kind: 'ngspice_ssh', ssh_host: 'sim2' }), JSON.stringify(pressed.map(p => p.body)));
  shown = await text();
  check('the new connection is selected, the kept copy of the file is named, and nothing was tested by itself', shown.includes('Connection "ngspice-ssh" was added') && shown.includes('.before-FIXTURE')
    && (await far.run(`${WINDOW}.querySelector('select').value`)) === 'ngspice-ssh' && !seen.slice(mark).some(s => s.name === 'check' || s.name === 'connect'), names(mark).join(', '));

  // ---- closing the window; the button opens it again; a reload closes it ------------------------------------------------
  await send('Target.closeTarget', { targetId: farPage.id });              // the user closes the window with its own X
  await windowTarget(false); far.close();
  await sleep(500);
  check('after the window is closed the button no longer says "window open", and keeps the state', !(await evaluate(`${BUTTON}.textContent`)).includes('(window open)') && (await evaluate(`${BUTTON}.textContent`)).includes('ngspice-ssh'));
  mark = seen.length;
  await openWindow();
  check('the button opens the window again, still without any request', seen.length === mark && (await far.run(`${WINDOW}.querySelector('select').value`)) === 'ngspice-ssh', names(mark).join(', '));

  statusAnswer = fixtures.old; mark = seen.length;
  await send('Page.reload'); await sleep(300); await loaded('ngspice-ssh');   // the configuration remembers the connection chosen last
  let closedByReload = true;
  try { await windowTarget(false); } catch { closedByReload = false; }
  far.close();
  check('a reload closes the window (no dead window is left behind)', closedByReload);
  check('a reload reads the profiles and the cached status once each, and checks nothing', JSON.stringify(names(mark).sort()) === JSON.stringify(['GET profiles', 'GET status']), names(mark).join(', '));
  await openWindow();
  check('an old cached result is labelled as too old', /^tested at .* - too old to trust, shown as unknown$/.test(await hint()) && (await badge()) === 'UNKNOWN', `${await badge()} | ${await hint()}`);
  await shot('window', '.connection-window', 'connection-7-window-old-result.png');

  // ---- LIVE (scratch backend only): the real routes, the real probe process, the real ngspice or its real absence ------
  if (LIVE) {
    await send('Target.closeTarget', { targetId: farPage.id }); await windowTarget(false); far.close();
    live = true; mark = seen.length;
    await send('Page.reload'); await sleep(300);
    for (let i = 0; i < 100 && !(await evaluate(`!!(${BUTTON})`)); i++) await sleep(100);
    await sleep(1500);
    await openWindow();
    if (!(await buttons()).includes('Create connection')) { await press('Add a connection...'); await sleep(1500); }
    await choose('.connection-add select', 'ngspice_local');
    await sleep(300);
    const liveForm = await far.run(`${WINDOW}.querySelector('.connection-add').innerText`);
    check('LIVE: the backend reports whether ngspice is installed on its machine', /(found|missing): ngspice program/.test(liveForm), liveForm.replace(/\s+/g, ' ').slice(0, 200));
    await press('Create connection');
    for (let i = 0; i < 60 && !(await text()).includes('was added'); i++) await sleep(100);
    check('LIVE: the connection is written by the real backend and selected', (await text()).includes('Connection "ngspice-local" was added') && (await far.run(`${WINDOW}.querySelector('select').value`)) === 'ngspice-local');
    await press('Test connection');
    for (let i = 0; i < 300 && (await badge()) === 'UNKNOWN'; i++) await sleep(100);
    const liveText = (await text()).replace(/\s+/g, ' ');
    const liveBadge = await badge();
    check('LIVE: the real test names the true state of ngspice on the backend machine', (liveBadge === 'OK' && /ngspice \d+ on this machine answered and solved the built-in test circuit/.test(liveText))
      || (liveBadge === 'FAILED' && liveText.includes('The ngspice program was not found on this machine') && liveText.includes('sudo apt install ngspice')), `${liveBadge} | ${liveText.slice(0, 260)}`);
    console.log(`INFO  LIVE result: ${liveBadge}`);
    await shot('window', '.connection-window', 'connection-8-window-live-ngspice.png');
  }

  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  far?.close(); ws.close();
} catch (error) {
  failures++; console.log('ERROR ' + (error?.stack ?? error));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; the temp dir is harmless */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
