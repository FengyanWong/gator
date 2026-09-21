// Browser check of the "Virtuoso bridge connection" panel (there is no frontend test runner in this project).
// Same approach as agent_tab_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY request to /api/connection/* is intercepted, logged and answered
// with a canned answer labelled FIXTURE, so no probe is started, no tunnel is touched and Virtuoso is never contacted.
// What it pins (user request 2026-09-20): the heading, NO check on page load, NO timer (the old panel polled every
// 15 s, so each quiet period here lasts 17 s), one check per button press, a result that stays until the next press.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 45 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/connection_panel_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9379, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const QUIET_MS = 17000;
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-conn-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const LAYERS = ['bridge_package', 'connection_profile', 'tunnel', 'daemon', 'session_readiness', 'spectre', 'spectre_license'];
const SETUP = '/fixture/virtuoso_setup.il';
const layersOf = (state, reason, upTo = LAYERS.length) => LAYERS.map((layer, i) => ({ layer, state: i < upTo ? state : 'not_checked',
  reason_code: i < upTo ? reason : null, diagnostic: null, details: layer === 'tunnel' ? { setup_path: SETUP } : {} }));
const ciw = { load: `load("${SETUP}")`, replace_running_daemon: ['RBStop()', `load("${SETUP}")`], setup_path: SETUP, notes: ['FIXTURE'] };
const utc = ms => new Date(ms).toISOString().replace('Z', '+00:00');             // the backend sends an explicit UTC offset
const fixtures = {
  profiles: { active: 'lab', connection_file: '/fixture/bridge_connection.json', connection_file_exists: true,
    profiles: [{ profile_id: 'lab', bridge_profile: null, settings_present: ['env_file'] }] },
  never: { profile_id: 'lab', checked_utc: null, age_seconds: null, stale: true, overall: 'unknown', layers: layersOf('unknown', 'never_checked'),
    summary: { level: 'unknown', headline: 'Not tested yet.', broken_layer: null, next_step: null }, ciw: null },
  tested: scope => ({ profile_id: 'lab', scope, trigger: 'user', checked_utc: utc(Date.now()), duration_seconds: 0.4, age_seconds: 0, stale: false,
    overall: 'ok', run_active: false, layers: layersOf('ok', null, scope === 'full' ? 7 : scope === 'cheap' ? 3 : 5), ciw,
    summary: { level: 'ok', headline: 'FIXTURE: connected (canned answer, nothing was probed).', broken_layer: null, next_step: null } }),
  old: () => ({ profile_id: 'lab', scope: 'interactive', trigger: 'user', checked_utc: utc(Date.now() - 600000), duration_seconds: 0.4, age_seconds: 600,
    stale: true, overall: 'unknown', run_active: false, layers: layersOf('unknown', 'stale_result'), ciw,
    summary: { level: 'unknown', headline: 'The last test is too old to trust - test again.', broken_layer: null, next_step: null } }),
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
  let nextId = 0; const pending = new Map(); const seen = []; const consoleErrors = []; let statusAnswer = () => fixtures.never;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = ({ requestId, request }) => {                                    // every connection request: log it, answer it here
    const url = new URL(request.url), name = url.pathname.replace('/api/connection/', '');
    const body = request.postData ? JSON.parse(request.postData) : null;
    seen.push({ method: request.method, name, body, at: Date.now() });
    if (request.method === 'GET' && name === 'profiles') return fulfil(requestId, 200, fixtures.profiles);
    if (request.method === 'GET' && name === 'status') return fulfil(requestId, 200, statusAnswer());
    if (request.method === 'POST' && name === 'check') return fulfil(requestId, 200, fixtures.tested(body.scope));
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${request.method} ${name} is not expected in this check` } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away (reload) */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const names = (from = 0) => seen.slice(from).map(s => `${s.method} ${s.name}`);
  const PANEL = `[...document.querySelectorAll('.panel')].find(p => p.querySelector('h3')?.textContent.trim() === 'Virtuoso bridge connection')`;
  const text = () => evaluate(`${PANEL}.textContent`);
  const badge = () => evaluate(`${PANEL}.querySelector('.badge').textContent`);
  const hint = () => evaluate(`${PANEL}.querySelector('.badge').nextElementSibling.textContent`);
  const loaded = async () => {
    for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
    for (let i = 0; i < 50 && !(await evaluate(`${PANEL}?.querySelector('select')?.value === 'lab'`)); i++) await sleep(100);
    await sleep(1500);                                                           // room for anything the panel would do on its own
  };
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = ${PANEL}.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, scale: 2 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/connection/*', requestStage: 'Request' }] });
  await send('Page.navigate', { url: APP });
  await loaded();

  // ---- page load: the heading, one cache read, no check -------------------------------------------------------
  check('the panel is called "Virtuoso bridge connection"', await evaluate(`!!(${PANEL})`));
  check('the old heading is gone', !(await evaluate(`[...document.querySelectorAll('h3')].some(h => h.textContent.includes('Virtuoso / bridge'))`)));
  check('page load reads the profiles and the cached status once each', JSON.stringify(names().sort()) === JSON.stringify(['GET profiles', 'GET status']), names().join(', '));
  check('page load starts NO check', !seen.some(s => s.method === 'POST'), names().join(', '));
  check('an untested link reads "never tested" / UNKNOWN', (await hint()) === 'never tested' && (await badge()) === 'UNKNOWN', `${await badge()} | ${await hint()}`);
  await shot('connection-1-loaded.png');

  // ---- no timer ------------------------------------------------------------------------------------------------
  let mark = seen.length;
  await sleep(QUIET_MS);
  check(`no request in ${QUIET_MS / 1000} s without a press (the old panel polled every 15 s)`, seen.length === mark, names(mark).join(', '));

  // ---- one press = one check; the result stays ------------------------------------------------------------------
  mark = seen.length;
  await evaluate(`[...${PANEL}.querySelectorAll('button')].find(b => b.textContent === 'Test connection').click()`);
  for (let i = 0; i < 40 && seen.length === mark; i++) await sleep(100);
  await sleep(500);
  const press = seen.slice(mark);
  check('"Test connection" sends exactly one check', press.length === 1 && press[0].method === 'POST' && press[0].name === 'check', names(mark).join(', '));
  check('it is a user-triggered interactive check of the chosen profile', JSON.stringify(press[0]?.body) === JSON.stringify({ profile_id: 'lab', scope: 'interactive', trigger: 'user' }), JSON.stringify(press[0]?.body));
  const shown = await hint();
  check('the result shows the clock time of the test, not a running age', /^tested at \d/.test(shown) && !/ago|STALE|too old/.test(shown), shown);
  check('the result is shown (OK + the headline)', (await badge()) === 'OK' && (await text()).includes('FIXTURE: connected'), await badge());
  check('the CIW load line appears', (await text()).includes(`load("${SETUP}")`));
  await shot('connection-2-tested.png');

  mark = seen.length;
  await sleep(QUIET_MS);
  check(`still no request ${QUIET_MS / 1000} s after the test`, seen.length === mark, names(mark).join(', '));
  check('the shown result did not change by itself', (await hint()) === shown && (await badge()) === 'OK', `${await badge()} | ${await hint()}`);

  // ---- a reload reads the cache once more; an old result is labelled, still nothing is checked ------------------
  statusAnswer = fixtures.old; mark = seen.length;
  await send('Page.reload'); await sleep(300); await loaded();
  check('a reload reads the profiles and the cached status once each, and checks nothing', JSON.stringify(names(mark).sort()) === JSON.stringify(['GET profiles', 'GET status']), names(mark).join(', '));
  check('an old cached result is labelled as too old', /^tested at .* - too old to trust, shown as unknown$/.test(await hint()) && (await badge()) === 'UNKNOWN', `${await badge()} | ${await hint()}`);
  await shot('connection-3-reloaded-old-result.png');

  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  ws.close();
} catch (error) {
  failures++; console.log('ERROR ' + (error?.stack ?? error));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; the temp dir is harmless */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
