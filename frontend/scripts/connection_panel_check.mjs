// Browser check of the "Connection" button and its window (there is no frontend test runner in this project).
// Same approach as agent_tab_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY request to /api/connection/* is intercepted, logged and answered
// with a canned answer labelled FIXTURE, so no probe is started, no tunnel is touched, no file is written and neither
// Virtuoso nor ngspice is contacted; any other writing request of the page is refused (reads pass). That makes it safe
// against the live backend; it needs only the built page.
// What it pins:
//   * the connection block of the left column is ONE button, and pressing it opens the connection window (user request
//     2026-09-21); the window is a second browser window, found by its title and driven over a second DevTools session;
//   * the four kinds of connection - Virtuoso over SSH / on this machine, ngspice on this machine / over SSH - each with
//     its own steps and wording, and "Add a connection" sending names only;
//   * (user request 2026-09-24, status record 7.80) ONE interactive test of the connection in use when the page opens -
//     the same as a press - and (user request 2026-09-20) nothing else on its own: NO check when the window opens or a
//     connection is chosen, NO timer (the old panel polled every 15 s, so each quiet period here lasts 17 s), one check
//     per button press, a result that stays until the next;
//   * (2026-09-29) a test answer that arrives after another connection was chosen is dropped, not shown under it;
//   * (record 7.168) "Folders...": the folders of the connection module, read once when opened, each one at its value in use
//     (a folder an environment variable decides cannot be typed into), saved only by "Save folders" with the changed folders
//     alone; a refused folder is named and marked; "Use defaults" and "Undo changes" send nothing.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 60 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/connection_panel_check.mjs)" [screenshot-dir]
// With GATOR_CONNECTION_LIVE=1 a last section lets the requests THROUGH to the backend: only ever against a scratch
// backend with its own GATOR_WORKBENCH_SETTINGS_DIR (it adds a connection to that folder and runs the real ngspice test);
// the check then refuses the live backend (port 8765). From WSL: WSLENV=GATOR_WORKBENCH_URL:GATOR_CONNECTION_LIVE.
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const LIVE = process.env.GATOR_CONNECTION_LIVE === '1';
const APP = await workbenchUrl({ writes: LIVE });
const QUIET_MS = 17000;
const out = outDir();
const browser = await launchEdge('conn');

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
const FOLDERS = [
  ['adapter_state', 'local', 'Adapter state', '~/.local/state/gator/bridge-state', 'GATOR_BRIDGE_STATE_DIR'],
  ['local_scratch', 'local', 'Simulator scratch', '/tmp/gator-work', null],
  ['bridge_checkout', 'local', 'virtuoso-bridge checkout', '~/virtuoso-bridge-lite', null],
  ['simulator_ic', 'simulator', 'Initial-condition files', '~/.gator/ic', null],
  ['maestro_netlist', 'simulator', 'Maestro netlists', '/tmp/gator_maestro_netlist', null]];
const folderAnswer = (saved = {}, extra = {}) => ({ connection_file: '/fixture/bridge_connection.json', note: 'FIXTURE note about VB_REMOTE_SCRATCH_ROOT.', ...extra,
  fields: FOLDERS.map(([key, side, label, def, env]) => {
    const byEnv = key === 'adapter_state';                                       // the backend was started with GATOR_BRIDGE_STATE_DIR set
    return { key, side, label, default: def, saved: saved[key] ?? null, value: byEnv ? '/fixture/state-from-env' : saved[key] ?? def,
      source: byEnv ? 'environment' : key in saved ? 'file' : 'default', environment_variable: env, set_by_environment: byEnv ? env : null, problem: null,
      used_for: `FIXTURE: what ${label} holds.`, takes_effect: 'FIXTURE: the next use' }; }) });
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

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors } = page;
  const seen = []; let statusAnswer = fixtures.never; let live = false; const savedFolders = {};
  let holdNextCheck = false, heldCheck = null;                                    // one test answer kept back, to arrive late
  const answer = ({ requestId, request }) => {                                    // every connection request: log it, answer it here
    const url = new URL(request.url), name = url.pathname.replace('/api/connection/', '');
    const body = request.postData ? JSON.parse(request.postData) : null;
    seen.push({ method: request.method, name, body, at: Date.now() });
    if (live) return send('Fetch.continueRequest', { requestId });                // the last section only: a scratch backend answers
    if (request.method === 'POST' && name === 'check' && holdNextCheck) {
      holdNextCheck = false; heldCheck = () => fulfil(requestId, 200, fixtures.tested(body.profile_id, body.scope)); return Promise.resolve();
    }
    if (request.method === 'GET' && name === 'profiles') return fulfil(requestId, 200, fixtures.profiles());
    if (request.method === 'GET' && name === 'status') return fulfil(requestId, 200, statusAnswer(url.searchParams.get('profile_id')));
    if (request.method === 'GET' && name === 'setup') return fulfil(requestId, 200, fixtures.setup);
    if (request.method === 'POST' && name === 'check') return fulfil(requestId, 200, fixtures.tested(body.profile_id, body.scope));
    if (request.method === 'POST' && name === 'connect') return fulfil(requestId, 200, { connect: { ok: true, action: 'started', reason_code: null, diagnostic: null,
      duration_seconds: 1.2, details: { mode: kindOf(body.profile_id).transport === 'local' ? 'local' : 'remote', ciw } }, status: fixtures.tested(body.profile_id, 'cheap') });
    if (request.method === 'GET' && name === 'directories') return fulfil(requestId, 200, folderAnswer(savedFolders));
    if (request.method === 'PUT' && name === 'directories') {
      if (body.values.simulator_ic === 'bad value') return fulfil(requestId, 422, { detail: { message: 'Initial-condition files: FIXTURE refused - not a folder on the simulator host.', code: 'invalid_folder', folder: 'simulator_ic' } });
      const changed = Object.keys(body.values);
      for (const key of changed) { const def = FOLDERS.find(f => f[0] === key)[3]; if (!body.values[key] || body.values[key] === def) delete savedFolders[key]; else savedFolders[key] = body.values[key]; }
      return fulfil(requestId, 200, folderAnswer(savedFolders, { saved: true, changed, backup: '/fixture/bridge_connection.json.before-FIXTURE-folders' }));
    }
    if (request.method === 'POST' && name === 'profile') { PROFILES[body.profile_id] = body.kind;
      return fulfil(requestId, 200, { created: true, profile_id: body.profile_id, kind: body.kind, backup: '/fixture/bridge_connection.json.before-FIXTURE', note: 'FIXTURE note.', profiles: fixtures.profiles() }); }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${request.method} ${name} is not expected in this check` } });
  };
  const names = (from = 0) => seen.slice(from).map(s => `${s.method} ${s.name}`);
  const settle = async (mark, ms = 4000) => { for (let waited = 0; waited < ms && seen.length === mark; waited += 100) await sleep(100); await sleep(500); };

  // ---- the window: a second page, found by its title, with a DevTools session of its own ---------------------------
  const windowTarget = present => browser.window('GATOR - connection', { present, except: page.target.id });
  const attachTo = target => browser.attach(target, { errors: consoleErrors, prefix: 'window: ' });
  const BUTTON = `document.querySelector('.left button.connection-button')`;
  const WINDOW = `document.querySelector('.connection-window')`;
  let far = null, farPage = null;
  const openWindow = async () => {
    await evaluate(`${BUTTON}.click()`, true);
    farPage = await windowTarget(true);
    far = await attachTo(farPage);
    await far.send('Emulation.setDeviceMetricsOverride', { width: 660, height: 920, deviceScaleFactor: 1, mobile: false });   // a headless popup ignores the requested size
    for (let i = 0; i < 50 && !(await far.evaluate(`!!(${WINDOW})`)); i++) await sleep(100);
    await sleep(400);
  };
  const text = () => far.evaluate(`${WINDOW}.innerText`);
  const badge = () => far.evaluate(`${WINDOW}.querySelector('.badge').textContent`);
  const hint = () => far.evaluate(`${WINDOW}.querySelector('.badge').nextElementSibling.textContent`);
  const buttons = () => far.evaluate(`[...${WINDOW}.querySelectorAll('button')].map(b => b.textContent.trim())`);
  const press = label => far.evaluate(`(() => { const b = [...${WINDOW}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)}); if (!b) return false; b.click(); return true; })()`, true);
  const choose = (selector, value) => far.setValue(`${WINDOW}.querySelector(${JSON.stringify(selector)})`, value);
  const shot = (session, selector, name) => (session === 'main' ? page : far).shot(path.join(out, name), `document.querySelector(${JSON.stringify(selector)})`, { scale: 2, maxHeight: 1400, beyond: true });
  const loaded = async (connection = 'lab') => {
    for (let i = 0; i < 100 && !(await evaluate(`!!(${BUTTON})`)); i++) await sleep(100);
    for (let i = 0; i < 50 && !(await evaluate(`${BUTTON}?.textContent.includes(${JSON.stringify(connection)})`)); i++) await sleep(100);
    await sleep(1500);                                                           // room for anything the page would do on its own
  };

  await page.intercept(['*/api/connection/*'], answer, { others: 'read' });
  await send('Page.navigate', { url: APP });
  await loaded();

  // ---- the left column: ONE button ----------------------------------------------------------------------------------
  const block = await evaluate(`(() => { const b = ${BUTTON}, panel = b?.closest('.panel'); return b ? { text: b.innerText.replace(/\\s+/g, ' ').trim(),
    controls: panel.querySelectorAll('button, select, input, a, summary').length, headings: [...document.querySelectorAll('.left h3')].map(h => h.textContent.trim()),
    height: Math.round(panel.getBoundingClientRect().height), first: panel === document.querySelector('.left').firstElementChild } : null; })()`);
  check('the connection block of the left column is ONE button', !!block && block.controls === 1 && block.first, JSON.stringify(block));
  check('it is called "Connection" and names the connection in use, its kind and the state the test made when the page opened found', !!block && /^Connection\s*lab - Virtuoso over SSH\s*OK$/.test(block.text), block?.text);
  check('the old panel (heading, steps, profile select) is gone from the column', !!block && !block.headings.some(h => /connection/i.test(h)) && block.height < 90, JSON.stringify(block));   // two lines of text; the old panel was > 300 px
  // Since 7.76 the Project column needs the connection list too (the family of the connection in use): a read of the
  // workbench's own file, no probe. Since 7.125 the button and the column share ONE read of it (api.ts).
  // Since 2026-09-24 (status record 7.80, user request) the page tests the connection in use ONCE when it opens - the same
  // interactive test as the button - and nothing else on its own; no cached read then (the test's answer is fresher).
  check('page load reads the profiles once (the button and the Project column share it) and tests the connection in use once, nothing else',
    JSON.stringify(names().sort()) === JSON.stringify(['GET profiles', 'POST check']), names().join(', '));
  const opened = seen.find(s => s.method === 'POST');
  check('the test when the page opens is the interactive test of the connection in use, as a press sends it', JSON.stringify(opened?.body) === JSON.stringify({ profile_id: 'lab', scope: 'interactive', trigger: 'user' }), JSON.stringify(opened?.body));
  check('the button shows its result', (await evaluate(`${BUTTON}.querySelector('.badge').textContent`)) === 'OK', await evaluate(`${BUTTON}.querySelector('.badge').textContent`));
  await shot('main', '.left', 'connection-1-left-column.png');

  // ---- pressing it opens the connection window; opening checks nothing ----------------------------------------------
  let mark = seen.length;
  await openWindow();
  check('pressing the button opens a window of its own, titled "GATOR - connection"', !!farPage && farPage.title === 'GATOR - connection');
  check('the window shows the block under the heading "Connection"', (await far.evaluate(`${WINDOW}.querySelector('h2')?.textContent`)) === 'Connection');
  check('opening the window sends NO request at all', seen.length === mark, names(mark).join(', '));
  check('the window shows the test made when the page opened: its clock time and OK', /^tested at \d/.test(await hint()) && (await badge()) === 'OK', `${await badge()} | ${await hint()}`);
  check('the button says the window is open', (await evaluate(`${BUTTON}.textContent`)).includes('(window open)'));
  const styled = await far.evaluate(`(() => { const s = getComputedStyle(${WINDOW}.querySelector('.step-no')); return s.borderRadius !== '0px' && s.color === 'rgb(255, 255, 255)'; })()`);
  check('the window carries the workbench style sheet', styled);

  // ---- Virtuoso over SSH: the three steps, as before ----------------------------------------------------------------
  let shown = await text();
  // The test made when the page opened found the (canned) tunnel up, so step 1 reads "Connect SSH (already up)".
  check('Virtuoso over SSH: 1 Connect SSH, 2 CIW line, 3 Test', shown.includes('Connect to the target over SSH') && shown.includes('Load the bridge in the Virtuoso CIW')
    && shown.includes('Test the connection') && (await buttons()).includes('Connect SSH (already up)') && (await buttons()).includes('+ Spectre / license'), (await buttons()).join(' | '));
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
  check('a connection never tested reads "never tested" / UNKNOWN', (await hint()) === 'never tested' && (await badge()) === 'UNKNOWN', `${await badge()} | ${await hint()}`);
  check('choosing another connection reads its cached status once (and the Project column the connection list) and checks nothing',
    switched.every(s => s.method === 'GET' && ['status', 'profiles'].includes(s.name)) && switched.filter(s => s.name === 'status').length === 1, switched.map(s => `${s.method} ${s.name}`).join(', '));
  check('Virtuoso on this machine: "Set up local bridge", no SSH wording in the steps', shown.includes('Set up the bridge on this machine') && (await buttons()).includes('Set up local bridge')
    && !(await buttons()).includes('Connect SSH') && shown.includes('no SSH and no tunnel') && shown.includes('Load the bridge in the Virtuoso CIW'), (await buttons()).join(' | '));
  check('a Virtuoso connection shows no ngspice note', !shown.includes('agent aid is under construction') && !shown.includes('What an ngspice connection runs'));
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
    && JSON.stringify((await buttons()).filter(b => !/Add a connection|^Folders/.test(b))) === JSON.stringify(['Test connection', 'Details']), (await buttons()).join(' | '));
  check('what an ngspice connection runs is said plainly, as a neutral note (not as an error)', shown.includes('What an ngspice connection runs: the ngspice netlist tasks')
    && (await far.evaluate(`!!${WINDOW}.querySelector('.note') && !${WINDOW}.querySelector('.note.error, .note .error, .blocker')`)));
  check('the note says that the ngspice agent aid is under construction (user request 2026-09-24)', shown.includes('The ngspice agent aid is under construction')
    && await far.evaluate(`!!${WINDOW}.querySelector('.note p.agent-aid')`), shown.slice(0, 200));
  mark = seen.length;
  await press('Test connection');
  await settle(mark);
  pressed = seen.slice(mark);
  check('testing ngspice sends one interactive check of that connection', pressed.length === 1 && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'sim', scope: 'interactive', trigger: 'user' }), JSON.stringify(pressed.map(p => p.body)));
  await press('Details');
  await sleep(300);
  const rows = await far.evaluate(`[...${WINDOW}.querySelectorAll('table.grid tbody tr td:first-child')].map(td => td.textContent)`);
  check('Details lists the four ngspice layers, and says the one simulation is the built-in test circuit', JSON.stringify(rows) === JSON.stringify(NGSPICE) && (await text()).includes('built-in three-element test circuit, never one of yours'), rows.join(', '));
  await shot('window', '.connection-window', 'connection-5-window-ngspice-local.png');
  await press('Hide');

  await select('far');
  shown = await text();
  check('ngspice over SSH: says that it needs key-based login', shown.includes('Test ngspice over SSH') && shown.includes('key-based login') && !(await buttons()).includes('Connect SSH'));

  // ---- a test answer that arrives after another connection was chosen (review of 2026-09-29) ---------------------------------------
  holdNextCheck = true;
  await press('Test connection'); await sleep(300);                             // the test of `far` is on its way ...
  await select('sim');                                                          // ... and another connection is chosen meanwhile
  const beforeLate = { badge: await badge(), hint: await hint() };
  await heldCheck(); heldCheck = null; await sleep(600);                        // now the answer for `far` arrives
  shown = await text();
  check('a test answer for a connection that is no longer chosen is dropped: the window keeps the chosen one\'s state',
    !shown.includes('FIXTURE: far connected') && (await badge()) === beforeLate.badge && (await hint()) === beforeLate.hint, `${JSON.stringify(beforeLate)} -> ${await badge()} | ${await hint()}`);

  // ---- add a connection: names only ------------------------------------------------------------------------------------
  mark = seen.length;
  await press('Add a connection...');
  await settle(mark);
  check('"Add a connection..." looks at what is installed (one GET setup) only when pressed', JSON.stringify(names(mark)) === JSON.stringify(['GET setup']), names(mark).join(', '));
  const kindsOffered = await far.evaluate(`[...${WINDOW}.querySelectorAll('.connection-add select')[0].options].map(o => o.textContent)`);
  check('the four kinds are offered', JSON.stringify(kindsOffered) === JSON.stringify(KINDS.map(k => k.label)), kindsOffered.join(' | '));
  await choose('.connection-add select', 'ngspice_ssh');
  await sleep(300);
  const form = await far.evaluate(`(() => { const add = ${WINDOW}.querySelector('.connection-add'); return { hosts: [...add.querySelectorAll('select')[1].options].map(o => o.textContent),
    name: add.querySelector('input').value, inputs: add.querySelectorAll('input').length, text: add.innerText }; })()`);
  check('ngspice over SSH offers the Host names of ~/.ssh/config as a list - there is no box to type an address into', JSON.stringify(form.hosts) === JSON.stringify(['simhost', 'sim2']) && form.inputs === 1 && form.name === 'ngspice-ssh', JSON.stringify(form));
  await shot('window', '.connection-window', 'connection-6-window-add.png');
  await far.setValue(`${WINDOW}.querySelectorAll('.connection-add select')[1]`, 'sim2');
  await sleep(200);
  mark = seen.length;
  await press('Create connection');
  await settle(mark);
  pressed = seen.slice(mark).filter(s => s.method === 'POST');
  check('"Create connection" sends a name, a kind and a Host NAME - nothing else', pressed.length === 1 && pressed[0].name === 'profile'
    && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'ngspice-ssh', kind: 'ngspice_ssh', ssh_host: 'sim2' }), JSON.stringify(pressed.map(p => p.body)));
  shown = await text();
  check('the new connection is selected, the kept copy of the file is named, and nothing was tested by itself', shown.includes('Connection "ngspice-ssh" was added') && shown.includes('.before-FIXTURE')
    && (await far.evaluate(`${WINDOW}.querySelector('select').value`)) === 'ngspice-ssh' && !seen.slice(mark).some(s => s.name === 'check' || s.name === 'connect'), names(mark).join(', '));

  // ---- Folders (record 7.168): read once when opened, saved only by its button, the changed folders alone ----------------
  const FOLDER = key => `${WINDOW}.querySelector('.connection-folders [data-folder=${key}] input')`;
  const folderValues = () => far.evaluate(`Object.fromEntries([...${WINDOW}.querySelectorAll('.connection-folders [data-folder]')].map(d => [d.dataset.folder, d.querySelector('input').value]))`);
  const folderText = () => far.evaluate(`${WINDOW}.querySelector('.connection-folders')?.innerText ?? ''`);
  const disabledButton = label => far.evaluate(`[...${WINDOW}.querySelectorAll('.connection-folders button')].find(b => b.textContent.trim() === ${JSON.stringify(label)})?.disabled`);
  check('the window has a "Folders..." button', (await buttons()).includes('Folders...'), (await buttons()).join(' | '));
  // (record 7.170, user: "separate the folders section with other section with similar style") a section of its own, headed
  // like the steps: the same rule above it, the same heading, a folder sign in the steps' circle
  const section = await far.evaluate(`(() => { const b = [...${WINDOW}.querySelectorAll('button')].find(x => x.textContent.trim() === 'Folders...');
    const own = b?.closest('.step'), step = [...${WINDOW}.querySelectorAll('.step')].find(s => /^\\d+$/.test(s.querySelector('.step-no')?.textContent ?? ''));
    const rule = e => { const c = getComputedStyle(e); return [c.borderTopStyle, c.borderTopWidth, c.borderTopColor, c.paddingTop, c.marginTop].join('|'); };
    const font = e => { const c = getComputedStyle(e); return [c.fontFamily, c.fontSize, c.fontWeight].join('|'); };
    return own && step && { head: own.querySelector('.step-head')?.textContent.trim(), sign: !!own.querySelector('.step-no svg'),
      sameRule: rule(own) === rule(step), sameHead: font(own.querySelector('.step-head')) === font(step.querySelector('.step-head')),
      sameCircle: own.querySelector('.step-no').getBoundingClientRect().width === step.querySelector('.step-no').getBoundingClientRect().width,
      // the circle sits where the numbered ones sit beside their heading's words (a picture alone in a line moves it in quirks mode)
      sameSpot: (e => e.querySelector('.step-no').getBoundingClientRect().top - e.querySelector('.step-head').getBoundingClientRect().top)(own)
        - (e => e.querySelector('.step-no').getBoundingClientRect().top - e.querySelector('.step-head').getBoundingClientRect().top)(step),
      quirks: document.compatMode }; })()`);
  check('Folders is a section of its own, headed like the steps: the same rule above it, the same heading, a folder sign in the circle',
    !!section && section.head === 'Folders' && section.sign && section.sameRule && section.sameHead && section.sameCircle && Math.abs(section.sameSpot) < 0.5, JSON.stringify(section));
  mark = seen.length;
  await press('Folders...');
  await settle(mark);
  check('"Folders..." reads the folders once (one GET directories) and sends nothing else', JSON.stringify(names(mark)) === JSON.stringify(['GET directories']), names(mark).join(', '));
  let folders = await folderValues();
  check('five folders, each at its value in use: the defaults, and the folder the environment decides', JSON.stringify(folders) === JSON.stringify({ adapter_state: '/fixture/state-from-env',
    local_scratch: '/tmp/gator-work', bridge_checkout: '~/virtuoso-bridge-lite', simulator_ic: '~/.gator/ic', maestro_netlist: '/tmp/gator_maestro_netlist' }), JSON.stringify(folders));
  let folderShown = await folderText();
  check('grouped by machine: this machine, then the simulator host with what "~" means there', folderShown.indexOf('On this machine') < folderShown.indexOf('Simulator scratch')
    && folderShown.indexOf('On the simulator host') < folderShown.indexOf('Initial-condition files') && folderShown.includes('the home of the user Virtuoso runs as'), folderShown.slice(0, 300));
  // (record 7.170, user: "if comments can be seen floating over name then delete the comment text underneath it")
  const comments = await far.evaluate(`[...${WINDOW}.querySelectorAll('.connection-folders [data-folder]')].map(d => ({ key: d.dataset.folder,
    tip: d.querySelector('label').title, under: [...d.querySelectorAll('.hint')].map(h => h.textContent) }))`);
  check('each folder comment is the tooltip of its name, with no comment text under it; under it only what is the case (the environment decides it)',
    comments.length === 5 && comments.every(c => c.tip.startsWith('FIXTURE: what') && c.tip.includes('Takes effect: FIXTURE: the next use.') && !c.under.some(t => t.includes('FIXTURE')))
    && JSON.stringify(comments.filter(c => c.under.length).map(c => c.key)) === JSON.stringify(['adapter_state']), JSON.stringify(comments));
  check('a folder an environment variable decides cannot be typed into, and says why', (await far.evaluate(`${FOLDER('adapter_state')}.disabled`)) && folderShown.includes('Set by GATOR_BRIDGE_STATE_DIR'));
  check('"Save folders" waits for a change', (await disabledButton('Save folders')) === true && (await disabledButton('Undo changes')) === true);
  await far.setValue(FOLDER('local_scratch'), '/scratch/gator', { event: 'input' });
  await sleep(200);
  check('typing a folder sends nothing and shows its default beside it', seen.length === mark + 1 && (await folderText()).includes('Default: /tmp/gator-work'), names(mark).join(', '));
  mark = seen.length;
  await press('Save folders');
  await settle(mark);
  pressed = seen.slice(mark);
  check('"Save folders" sends ONE request with the changed folder alone', pressed.length === 1 && pressed[0].method === 'PUT' && pressed[0].name === 'directories'
    && JSON.stringify(pressed[0].body) === JSON.stringify({ values: { local_scratch: '/scratch/gator' } }), JSON.stringify(pressed.map(p => [p.method, p.name, p.body])));
  folderShown = await folderText();
  check('the answer names the saved folder and the kept copy of the file', folderShown.includes('Saved: Simulator scratch.') && folderShown.includes('.before-FIXTURE-folders')
    && (await folderValues()).local_scratch === '/scratch/gator' && (await disabledButton('Save folders')) === true, folderShown.slice(-400));
  await far.setValue(FOLDER('simulator_ic'), 'bad value', { event: 'input' });
  mark = seen.length;
  await press('Save folders');
  await settle(mark);
  pressed = seen.slice(mark);
  folderShown = await folderText();
  check('a refused folder: one request, the backend\'s words shown, the field marked', pressed.length === 1 && JSON.stringify(pressed[0].body) === JSON.stringify({ values: { simulator_ic: 'bad value' } })
    && folderShown.includes('FIXTURE refused') && (await far.evaluate(`${FOLDER('simulator_ic')}.getAttribute('aria-invalid')`)) === 'true', folderShown.slice(-300));
  mark = seen.length;
  await press('Undo changes');
  await sleep(300);
  check('"Undo changes" puts the fields back to the values in use and sends nothing', seen.length === mark && (await folderValues()).simulator_ic === '~/.gator/ic'
    && !(await folderText()).includes('FIXTURE refused'), JSON.stringify(await folderValues()));
  await press('Use defaults');
  await sleep(300);
  folders = await folderValues();
  check('"Use defaults" fills in the defaults - not the folder the environment decides - and sends nothing', seen.length === mark && folders.local_scratch === '/tmp/gator-work'
    && folders.adapter_state === '/fixture/state-from-env', JSON.stringify(folders));
  await press('Save folders');
  await settle(mark);
  pressed = seen.slice(mark);
  check('saving the defaults sends the folder that changed back, alone', pressed.length === 1 && JSON.stringify(pressed[0].body) === JSON.stringify({ values: { local_scratch: '/tmp/gator-work' } }),
    JSON.stringify(pressed.map(p => p.body)));
  await shot('window', '.connection-window', 'connection-6b-window-folders.png');
  await press('Close "Folders"');
  await sleep(200);
  check('"Close "Folders"" folds the section away', !(await far.evaluate(`!!${WINDOW}.querySelector('.connection-folders')`)));

  // ---- closing the window; the button opens it again; a reload closes it ------------------------------------------------
  await send('Target.closeTarget', { targetId: farPage.id });              // the user closes the window with its own X
  await windowTarget(false); far.close();
  await sleep(500);
  check('after the window is closed the button no longer says "window open", and keeps the state', !(await evaluate(`${BUTTON}.textContent`)).includes('(window open)') && (await evaluate(`${BUTTON}.textContent`)).includes('ngspice-ssh'));
  mark = seen.length;
  await openWindow();
  check('the button opens the window again, still without any request', seen.length === mark && (await far.evaluate(`${WINDOW}.querySelector('select').value`)) === 'ngspice-ssh', names(mark).join(', '));

  statusAnswer = fixtures.old; mark = seen.length;
  await send('Page.reload'); await sleep(300); await loaded('ngspice-ssh');   // the configuration remembers the connection chosen last
  let closedByReload = true;
  try { await windowTarget(false); } catch { closedByReload = false; }
  far.close();
  check('a reload closes the window (no dead window is left behind)', closedByReload);
  check('a reload reads the profiles once and tests the connection chosen last once, nothing else', JSON.stringify(names(mark).sort()) === JSON.stringify(['GET profiles', 'POST check'])
    && JSON.stringify(seen.find((s, i) => i >= mark && s.method === 'POST')?.body) === JSON.stringify({ profile_id: 'ngspice-ssh', scope: 'interactive', trigger: 'user' }), names(mark).join(', '));
  await openWindow();
  check('the window shows that fresh test, not the old cached result', /^tested at \d/.test(await hint()) && !/too old/.test(await hint()) && (await badge()) === 'OK', `${await badge()} | ${await hint()}`);
  await select('sim');                                                        // a connection chosen later: its cached result, here an old one
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
    const liveForm = await far.evaluate(`${WINDOW}.querySelector('.connection-add').innerText`);
    check('LIVE: the backend reports whether ngspice is installed on its machine', /(found|missing): ngspice program/.test(liveForm), liveForm.replace(/\s+/g, ' ').slice(0, 200));
    await press('Create connection');
    for (let i = 0; i < 60 && !(await text()).includes('was added'); i++) await sleep(100);
    check('LIVE: the connection is written by the real backend and selected', (await text()).includes('Connection "ngspice-local" was added') && (await far.evaluate(`${WINDOW}.querySelector('select').value`)) === 'ngspice-local');
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
});
