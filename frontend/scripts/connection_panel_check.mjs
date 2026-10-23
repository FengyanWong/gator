// Browser check of the "Connection" button and its window (there is no frontend test runner in this project).
// Same approach as agent_window_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). EVERY request to /api/connection/* is intercepted, logged and answered
// with a canned answer labelled FIXTURE, so no probe is started, no tunnel is touched, no file is written and neither
// Virtuoso nor ngspice is contacted; any other writing request of the page is refused (reads pass). That makes it safe
// against the live backend; it needs only the built page.
// What it pins:
//   * the connection block is ONE button - in the left column until record 7.182, in the header's title block since (user:
//     "move the conection button to the header") - and pressing it opens the connection window (user request 2026-09-21);
//     the window is a second browser window, found by its title and driven over a second DevTools session;
//   * the four kinds of connection - Virtuoso over SSH / on this machine, ngspice on this machine / over SSH - each with
//     its own steps and wording, and "Add a connection" sending names only;
//   * (user request 2026-09-24, status record 7.80) ONE interactive test of the connection in use when the page opens -
//     the same as a press - and (user request 2026-09-20) nothing else on its own: NO check when the window opens or a
//     connection is chosen, NO timer (the old panel polled every 15 s, so each quiet period here lasts 17 s), one check
//     per button press, a result that stays until the next;
//   * (2026-09-29) a test answer that arrives after another connection was chosen is dropped, not shown under it;
//   * (record 7.168) "Folders...": the folders of the connection module, read once when opened, each one at its value in use
//     (a folder an environment variable decides cannot be typed into), saved only by "Save folders" with the changed folders
//     alone; a refused folder is named and marked; "Use defaults" and "Undo changes" send nothing;
//   * (branch record SIF-87) a folder typed and not saved outlives the window's close: opened again, it lies over the values
//     in use, said in a line, until Save folders or Undo changes;
//   * (branch record SIF-109) Enter in the new connection's name adds it, as "Create connection" does; a refused name sends nothing.
//   * (branch record SIF-114) the Copy beside each CIW block is the copy icon, its word for screen readers and at the start of
//     its tooltip; a copy that went through shows the check mark, "Copied", for 1.5 s, a refused one does not.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 60 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/connection_panel_check.mjs)" [screenshot-dir]
// With GATOR_CONNECTION_LIVE=1 a last section lets the requests THROUGH to the backend: only ever against a scratch
// backend with its own GATOR_WORKBENCH_SETTINGS_DIR (it adds a connection to that folder and runs the real ngspice test);
// the check then refuses the live backend (port 8765). From WSL: WSLENV=GATOR_WORKBENCH_URL:GATOR_CONNECTION_LIVE.
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl, CONNECTION_WINDOW } from './lib/harness.mjs';

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
let groupedSessions = false;
let activeProfile = 'lab';                       // the connection file's own choice; a page with none adopts it
const SETUP = '/fixture/virtuoso_setup.il';
const layersOf = (id, state, reason, upTo = 99) => (kindOf(id).family === 'ngspice' ? NGSPICE : VIRTUOSO).map((layer, i) => ({ layer, state: i < upTo ? state : 'not_checked',
  reason_code: i < upTo ? reason : null, diagnostic: null, details: layer === 'tunnel' ? { setup_path: SETUP } : {} }));
const ciw = { load: `load("${SETUP}")`, replace_running_daemon: ['RBStop()', `load("${SETUP}")`], setup_path: SETUP, notes: ['FIXTURE'] };
const ciwFor = id => id === 'lab2' ? { ...ciw, load: 'load("/fixture/second/virtuoso_setup.il")',
  setup_path: '/fixture/second/virtuoso_setup.il', replace_running_daemon: ['RBStop()', 'load("/fixture/second/virtuoso_setup.il")'] } : ciw;
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
  profiles: () => ({ active: activeProfile, connection_file: '/fixture/bridge_connection.json', connection_file_exists: true, kinds: KINDS,
    profiles: Object.keys(PROFILES).map(id => publicProfile(id, id !== 'lab')),
    ...(groupedSessions ? { groups: Object.keys(PROFILES).filter(id => id !== 'lab2').map(id => ({ ...publicProfile(id, id !== 'lab'),
      session_profile_ids: id === 'lab' ? ['lab', 'lab2'] : [id] })) } : {}) }),                  // `lab` was written before kinds existed
  never: id => ({ profile_id: id, ...described(id), checked_utc: null, age_seconds: null, stale: true, overall: 'unknown', layers: layersOf(id, 'unknown', 'never_checked'),
    summary: { level: 'unknown', headline: 'Not tested yet.', broken_layer: null, next_step: null }, ciw: null }),
  tested: (id, scope) => ({ profile_id: id, ...described(id), scope, trigger: 'user', checked_utc: utc(Date.now()), duration_seconds: 0.4, age_seconds: 0, stale: false,
    overall: 'ok', run_active: false, layers: layersOf(id, 'ok', null, kindOf(id).family === 'ngspice' ? 4 : scope === 'full' ? 7 : scope === 'cheap' ? 3 : 5),
    ciw: kindOf(id).family === 'ngspice' ? null : ciwFor(id),
    summary: { level: 'ok', headline: `FIXTURE: ${id} connected (canned answer, nothing was probed).`, broken_layer: null, next_step: null } }),
  old: id => ({ profile_id: id, ...described(id), scope: 'interactive', trigger: 'user', checked_utc: utc(Date.now() - 600000), duration_seconds: 0.4, age_seconds: 600,
    stale: true, overall: 'unknown', run_active: true, last_successful_bridge_interaction_utc: utc(Date.now() - 600000), layers: layersOf(id, 'unknown', 'stale_result'), ciw,
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
  let lateHeadline = null;                                                        // ... with a headline of its own, when set
  let failNextCheck = false, failNextConnect = null;                              // a test with no answer at all; a Connect that fails
  const answer = ({ requestId, request }) => {                                    // every connection request: log it, answer it here
    const url = new URL(request.url), name = url.pathname.replace('/api/connection/', '');
    const body = request.postData ? JSON.parse(request.postData) : null;
    seen.push({ method: request.method, name, body, at: Date.now() });
    if (live) return send('Fetch.continueRequest', { requestId });                // the last section only: a scratch backend answers
    if (request.method === 'POST' && name === 'check' && failNextCheck) { failNextCheck = false; return send('Fetch.failRequest', { requestId, errorReason: 'ConnectionRefused' }); }
    if (request.method === 'POST' && name === 'connect' && failNextConnect) { const failure = failNextConnect; failNextConnect = null;
      return fulfil(requestId, 200, { connect: { ok: false, action: 'failed', duration_seconds: 0.3, ...failure }, status: fixtures.never(body.profile_id) }); }
    if (request.method === 'POST' && name === 'check' && holdNextCheck) {
      holdNextCheck = false;
      heldCheck = () => { const t = fixtures.tested(body.profile_id, body.scope);
        return fulfil(requestId, 200, lateHeadline ? { ...t, summary: { ...t.summary, headline: lateHeadline } } : t); };
      return Promise.resolve();
    }
    if (request.method === 'GET' && name === 'profiles') return fulfil(requestId, 200, fixtures.profiles());
    if (request.method === 'GET' && name === 'status') return fulfil(requestId, 200, statusAnswer(url.searchParams.get('profile_id')));
    if (request.method === 'GET' && name === 'setup') return fulfil(requestId, 200, fixtures.setup);
    if (request.method === 'POST' && name === 'check') return fulfil(requestId, 200, fixtures.tested(body.profile_id, body.scope));
    if (request.method === 'POST' && name === 'connect') return fulfil(requestId, 200, { connect: { ok: true, action: 'started', reason_code: null, diagnostic: null,
      duration_seconds: 1.2, details: { mode: kindOf(body.profile_id).transport === 'local' ? 'local' : 'remote', ciw: ciwFor(body.profile_id) } }, status: fixtures.tested(body.profile_id, 'cheap') });
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
  const windowTarget = present => browser.window(CONNECTION_WINDOW, { present, except: page.target.id });
  const BUTTON = `document.querySelector('header button.connection-button')`;
  const WINDOW = `document.querySelector('.connection-window')`;
  let far = null, farPage = null;
  const openWindow = async (width = 660) => {
    far = await browser.popup(page, BUTTON, CONNECTION_WINDOW, { width, height: 920, ready: WINDOW });
    farPage = far.target;
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

  // ---- the header's title block: ONE button (record 7.182; the left column's first block until then) --------------------------
  const block = await evaluate(`(() => { const b = ${BUTTON}, panel = b?.closest('.connection-launcher'); return b ? { text: b.innerText.replace(/\\s+/g, ' ').trim(),
    controls: panel.querySelectorAll('button, select, input, a, summary').length, headings: [...document.querySelectorAll('.left h3')].map(h => h.textContent.trim()),
    height: Math.round(panel.getBoundingClientRect().height), inTitleBlock: !!panel.closest('header .title-block'), leftHasNone: !document.querySelector('.left .connection-launcher') } : null; })()`);
  check('the connection block is ONE button, in the header\'s title block, and the left column has none', !!block && block.controls === 1 && block.inTitleBlock && block.leftHasNone, JSON.stringify(block));
  check('it is called "Connection" and names the connection in use, its kind and the state the test made when the page opened found', !!block && /^Connection\s*lab - Virtuoso over SSH\s*OK$/i.test(block.text), block?.text);
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
  await shot('main', 'header', 'connection-1-header.png');

  // ---- pressing it opens the connection window; opening checks nothing ----------------------------------------------
  let mark = seen.length;
  await openWindow();
  check('pressing the button opens a window of its own, titled "GATOR - connection"', !!farPage && farPage.title === CONNECTION_WINDOW);
  check('the window shows the block under the heading "Connection"', (await far.evaluate(`${WINDOW}.querySelector('h2')?.textContent`)) === 'Connection');
  check('opening the window sends NO request at all', seen.length === mark, names(mark).join(', '));
  check('the window shows the test made when the page opened: its clock time and OK', /^tested at \d/.test(await hint()) && (await badge()) === 'OK', `${await badge()} | ${await hint()}`);
  check('the button says the window is open', (await evaluate(`${BUTTON}.textContent`)).includes('(window open)'));
  const styled = await far.evaluate(`(() => { const s = getComputedStyle(${WINDOW}.querySelector('.step-no')); return s.borderRadius !== '0px' && s.color === 'rgb(10, 10, 11)'; })()`);   // record 7.360: black on the white circle
  check('the window carries the workbench style sheet', styled);

  // ---- Virtuoso over SSH: the three steps, as before ----------------------------------------------------------------
  let shown = await text();
  // The test made when the page opened found the (canned) tunnel up, so step 1 reads "Connect SSH (already up)".
  check('Virtuoso over SSH: 1 Connect SSH, 2 CIW line, 3 Test', shown.includes('Connect to the target over SSH') && shown.includes('Load the bridge in the Virtuoso CIW')
    && shown.includes('Test the connection') && (await buttons()).includes('Connect SSH (already up)') && (await buttons()).includes('Full test (Spectre, license)'), (await buttons()).join(' | '));
  // branch record SIF-79: the longer test is named as one (it read "+ Spectre / license", like adding something)
  const fullTest = await far.evaluate(`[...${WINDOW}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Full test (Spectre, license)')?.title ?? null`);
  check('the longer test reads "Full test (Spectre, license)", and its tooltip says it is Test connection and more, takes no seat and can be slow (SIF-79)',
    !!fullTest && fullTest.startsWith('Test connection, then also') && fullTest.includes('it takes no seat') && fullTest.endsWith('Can be slow.') && !(await buttons()).some(b => b.startsWith('+')), fullTest);
  // branch record SIF-79: a kind the file does not name is said on hover, for the user - not as the program's history in two more lines
  const kindLabel = await far.evaluate(`(() => { const b = ${WINDOW}.querySelector('.connection-kind b'); return b && { text: b.textContent, tip: b.title, cursor: getComputedStyle(b).cursor }; })()`);
  check('a connection whose kind the file does not name says on hover how it is taken and that there is nothing to do; the card no longer tells the program\'s history (SIF-79)',
    !!kindLabel && kindLabel.text === 'Virtuoso over SSH.' && kindLabel.tip.startsWith('The connection file does not say where Virtuoso runs, so this connection is taken as Virtuoso over SSH')
    && kindLabel.tip.endsWith('Nothing to do.') && kindLabel.cursor === 'help' && !shown.includes('before kinds existed'), JSON.stringify(kindLabel));
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
  check('the button in the header shows the new state too', (await evaluate(`${BUTTON}.querySelector('.badge').textContent`)) === 'OK');
  await shot('window', '.connection-window', 'connection-3-window-tested.png');

  mark = seen.length;
  await sleep(QUIET_MS);
  check(`still no request ${QUIET_MS / 1000} s after the test`, seen.length === mark, names(mark).join(', '));
  check('the shown result did not change by itself', (await hint()) === testedHint && (await badge()) === 'OK', `${await badge()} | ${await hint()}`);

  // ---- the CIW lines' Copy (branch record SIF-114, the icon audit) -------------------------------------------------------------
  // The copy icon, as Output files' Copy run path - its word for screen readers and at the start of its tooltip - where the word
  // stood, at the code box's top; for 1.5 s after a copy that went through, the check mark with "Copied". The window's clipboard
  // is stood in for: a headless window may not be focused.
  const DRAWN = { copy: 'M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2', check: 'M3 8.5l3.2 3.2L13 4.5' };
  const ciwCopies = () => far.evaluate(`[...${WINDOW}.querySelectorAll('.command > button')].map(b => ({ text: b.textContent,
    label: b.querySelector('.sr-only')?.textContent ?? null, title: b.title, drawing: b.querySelector('svg.icon path')?.getAttribute('d') ?? null }))`);
  const copies = await ciwCopies();
  const copyPlace = await far.evaluate(`(() => { const b = ${WINDOW}.querySelector('.command > button').getBoundingClientRect(), c = ${WINDOW}.querySelector('.command > code').getBoundingClientRect();
    return { top: Math.round(b.top - c.top), gap: Math.round(b.left - c.right), width: Math.round(b.width), height: Math.round(b.height) }; })()`);
  check('the Copy beside each CIW block - the load lines and, folded, the reload lines - is the copy icon, "Copy" for screen readers and at the start of its tooltip (SIF-114)',
    copies.length === 2 && copies.every(c => c.text === 'Copy' && c.label === 'Copy' && c.drawing === DRAWN.copy && c.title === 'Copy: These lines to the clipboard, to paste into the Virtuoso CIW.'),
    JSON.stringify(copies));
  check('...beside the code box, at its top', copyPlace.top === 0 && copyPlace.gap >= 0 && copyPlace.gap <= 8, JSON.stringify(copyPlace));
  await far.evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: text => { window.__clip = text; return Promise.resolve(); } })`);
  mark = seen.length;
  await far.evaluate(`${WINDOW}.querySelector('.command > button').click()`, true); await sleep(300);
  const copiedNow = await ciwCopies(), clip = await far.evaluate('window.__clip ?? null');
  check('... a press puts the load lines on the clipboard and shows the check mark, "Copied" for screen readers, its tooltip unchanged; the reload lines\' Copy stays; nothing is sent',
    clip === `setShellEnvVar("RB_NONCE_CACHE_MAX" "32768")\nload("${SETUP}")` && copiedNow[0]?.text === 'Copied' && copiedNow[0].label === 'Copied' && copiedNow[0].drawing === DRAWN.check
    && copiedNow[0].title === copies[0].title && JSON.stringify(copiedNow[1]) === JSON.stringify(copies[1]) && seen.length === mark, JSON.stringify({ clip, copiedNow, sent: names(mark) }));
  await sleep(1500);
  check('... and 1.5 s later the copy icon and "Copy" again', JSON.stringify(await ciwCopies()) === JSON.stringify(copies), JSON.stringify(await ciwCopies()));
  await far.evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: () => Promise.reject(new DOMException('FIXTURE: Document is not focused.', 'NotAllowedError')) })`);
  await far.evaluate(`${WINDOW}.querySelector('.command > button').click()`, true); await sleep(300);
  check('... a copy the browser refuses shows no check mark: Copy stays', JSON.stringify(await ciwCopies()) === JSON.stringify(copies), JSON.stringify(await ciwCopies()));
  await far.evaluate(`delete navigator.clipboard.writeText`);

  // ---- the other three kinds: own steps, own words ---------------------------------------------------------------------
  const select = async id => { const before = seen.length; await choose('select', id); await settle(before); return seen.slice(before); };
  let switched = await select('here');
  shown = await text();
  check('a connection never tested reads "never tested" / UNKNOWN', (await hint()) === 'never tested' && (await badge()) === 'UNKNOWN', `${await badge()} | ${await hint()}`);
  check('choosing another connection reads its cached status once (and the Project column the connection list) and checks nothing',
    switched.every(s => s.method === 'GET' && ['status', 'profiles'].includes(s.name)) && switched.filter(s => s.name === 'status').length === 1, switched.map(s => `${s.method} ${s.name}`).join(', '));
  check('Virtuoso on this machine: "Set up local bridge", no SSH wording in the steps', shown.includes('Set up the bridge on this machine') && (await buttons()).includes('Set up local bridge')
    && !(await buttons()).includes('Connect SSH') && shown.includes('no SSH and no tunnel') && shown.includes('Load the bridge in the Virtuoso CIW'), (await buttons()).join(' | '));
  check('a Virtuoso connection shows no ngspice note', !shown.includes('What an ngspice connection runs'));
  mark = seen.length;
  await press('Set up local bridge');
  await settle(mark);
  pressed = seen.slice(mark);
  check('"Set up local bridge" sends one connect with the profile name and nothing else', pressed.length === 1 && pressed[0].name === 'connect' && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'here' }), JSON.stringify(pressed.map(p => p.body)));
  check('its result is worded for this machine', (await text()).includes('Local bridge set up (1.2 s).') && (await buttons()).includes('Set up local bridge (already done)'));
  await shot('window', '.connection-window', 'connection-4-window-virtuoso-local.png');
  // branch record SIF-55: a failed set-up reads in words, its code in the tooltip (it read "Set-up failed: bridge_version_unverified - ...")
  failNextConnect = { reason_code: 'bridge_version_unverified', diagnostic: 'installed 0.0.FIXTURE', details: { next_step: 'FIXTURE next step.' } };
  mark = seen.length;
  await press('Set up local bridge (already done)');
  await settle(mark);
  const failedLine = await far.evaluate(`(() => { const p = ${WINDOW}.querySelector('.connection-session .step p.error'); return p && { text: p.textContent, title: p.title }; })()`);
  check('a failed set-up says its reason in words, then the bridge\'s diagnostic and the next step, with the code in the tooltip', !!failedLine && !failNextConnect
    && failedLine.text === 'Set-up failed: bridge version unverified - installed 0.0.FIXTURE Next step: FIXTURE next step.' && failedLine.title === 'bridge_version_unverified', JSON.stringify(failedLine));

  await select('sim');
  shown = await text();
  check('ngspice on this machine: ONE step - test; no connect step, no CIW step, no Spectre button', shown.includes('Test ngspice on this machine') && !shown.includes('Virtuoso CIW')
    && JSON.stringify((await buttons()).filter(b => !/Add a connection|^Folders/.test(b))) === JSON.stringify(['Test connection', 'Details']), (await buttons()).join(' | '));
  check('what an ngspice connection runs is said plainly, as a neutral note (not as an error)', shown.includes('What an ngspice connection runs: the ngspice netlist tasks')
    && (await far.evaluate(`!!${WINDOW}.querySelector('.note') && !${WINDOW}.querySelector('.note.error, .note .error, .blocker')`)));
  check('the note no longer speaks of an agent aid: the Agent tab\'s own agent went on 2026-10-06 (record 7.226)', !shown.includes('agent aid')
    && await far.evaluate(`!${WINDOW}.querySelector('.note p.agent-aid')`), shown.slice(0, 200));
  mark = seen.length;
  await press('Test connection');
  await settle(mark);
  pressed = seen.slice(mark);
  check('testing ngspice sends one interactive check of that connection', pressed.length === 1 && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'sim', scope: 'interactive', trigger: 'user' }), JSON.stringify(pressed.map(p => p.body)));
  await press('Details');
  await sleep(300);
  // branch record SIF-55: the layers in words, each key in its tooltip (the column listed the keys)
  const rows = await far.evaluate(`[...${WINDOW}.querySelectorAll('table.grid tbody tr td:first-child')].map(td => [td.textContent, td.title])`);
  check('Details lists the four ngspice layers in words, each key in its tooltip, and says the one simulation is the built-in test circuit',
    JSON.stringify(rows.map(r => r[1])) === JSON.stringify(NGSPICE) && JSON.stringify(rows.map(r => r[0])) === JSON.stringify(['connection settings', 'SSH login', 'ngspice program', 'test simulation'])
    && (await text()).includes('built-in three-element test circuit, never one of yours'), JSON.stringify(rows));
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
    const said = own?.querySelector(':scope > p.hint')?.textContent.replace(/\\s+/g, ' ');
    const rule = e => { const c = getComputedStyle(e); return [c.borderTopStyle, c.borderTopWidth, c.borderTopColor, c.paddingTop, c.marginTop].join('|'); };
    const font = e => { const c = getComputedStyle(e); return [c.fontFamily, c.fontSize, c.fontWeight].join('|'); };
    return own && step && { head: own.querySelector('.step-head')?.textContent.trim(), sign: !!own.querySelector('.step-no svg'), said, tip: b.title,
      sameRule: rule(own) === rule(step), sameHead: font(own.querySelector('.step-head')) === font(step.querySelector('.step-head')),
      sameCircle: own.querySelector('.step-no').getBoundingClientRect().width === step.querySelector('.step-no').getBoundingClientRect().width,
      // the circle sits where the numbered ones sit beside their heading's words (a picture alone in a line moves it in quirks mode)
      sameSpot: (e => e.querySelector('.step-no').getBoundingClientRect().top - e.querySelector('.step-head').getBoundingClientRect().top)(own)
        - (e => e.querySelector('.step-no').getBoundingClientRect().top - e.querySelector('.step-head').getBoundingClientRect().top)(step),
      quirks: document.compatMode }; })()`);
  check('Folders is a section of its own, headed like the steps: the same rule above it, the same heading, a folder sign in the circle',
    !!section && section.head === 'Folders' && section.sign && section.sameRule && section.sameHead && section.sameCircle && Math.abs(section.sameSpot) < 0.5, JSON.stringify(section));
  // branch record SIF-79: which folders, said under the head (it read "Folders" over "Folders..." and only the tooltip said more)
  check('under its head the section says which folders it holds and on which machine, and the button\'s tooltip does not say it again (SIF-79)',
    !!section && section.said === 'Where GATOR keeps its files outside the repository: lock and crash journals, simulator scratch and the virtuoso-bridge checkout on this machine; initial-condition files and Maestro netlists on the simulator host.'
    && !section.tip.includes('outside the repository') && section.tip.endsWith('Opening it changes nothing.'), JSON.stringify(section));
  mark = seen.length;
  await press('Folders...');
  await settle(mark);
  check('"Folders..." reads the folders once (one GET directories) and sends nothing else', JSON.stringify(names(mark)) === JSON.stringify(['GET directories']), names(mark).join(', '));
  check('...and the opened section starts with how a folder\'s value works, not with where the folders are again (SIF-79)',
    (await folderText()).startsWith('Each folder starts at the value GATOR has always used') && !(await folderText()).includes('Where GATOR keeps'), (await folderText()).slice(0, 160));
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
  // branch record SIF-87: a folder typed and not saved outlives the window's close (its X, as the banner's Close all closes
  // it): opened again, the section reads the values in use and lays the typing over them, saying so; Undo changes drops it
  await far.setValue(FOLDER('simulator_ic'), '~/fixture-typed', { event: 'input' });
  await sleep(200);
  await send('Target.closeTarget', { targetId: farPage.id }); await windowTarget(false); far.close();
  mark = seen.length;
  await openWindow();
  await settle(mark);
  folders = await folderValues();
  const keptLine = () => far.evaluate(`${WINDOW}.querySelector('.connection-folders .kept-draft')?.textContent ?? null`);
  check('closed before Save folders, the typed folder is kept: the section reads the folders once and shows the typing over them, saying so (SIF-87)',
    JSON.stringify(names(mark)) === JSON.stringify(['GET directories']) && folders.simulator_ic === '~/fixture-typed' && folders.local_scratch === '/tmp/gator-work'
    && (await keptLine()) === 'Your changes from before are kept, not saved yet. Undo changes drops them.' && (await disabledButton('Save folders')) === false,
    `${names(mark).join(', ')} | ${JSON.stringify(folders)} | ${await keptLine()}`);
  mark = seen.length;
  await press('Undo changes');
  await sleep(300);
  check('"Undo changes" drops the kept typing, and its line, and sends nothing (SIF-87)', seen.length === mark && (await folderValues()).simulator_ic === '~/.gator/ic'
    && (await keptLine()) === null && (await disabledButton('Save folders')) === true, JSON.stringify(await folderValues()));
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
  // branch record SIF-55: a reason in words with its code in the tooltip ("stale_result"), and the time of the last bridge
  // interaction of an active run in local time, its UTC in the tooltip (it printed the ISO text)
  await press('Details'); await sleep(300);
  const oldDetails = await far.evaluate(`(() => { const t = ${WINDOW}.querySelector('table.grid'), s = t?.querySelector('tfoot span');
    return t && { reasons: [...t.querySelectorAll('tbody tr td:nth-child(3) > span')].map(x => [x.textContent, x.title]), foot: s?.textContent, tip: s?.title }; })()`);
  check('Details gives each reason in words with its code in the tooltip, and an active run\'s last bridge interaction in local time with UTC in the tooltip',
    !!oldDetails && oldDetails.reasons.length === NGSPICE.length && oldDetails.reasons.every(([words, key]) => words === 'stale result' && key === 'stale_result')
    && /^ A run is active; last successful bridge interaction: \d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.$/.test(oldDetails.foot ?? '') && /^UTC: \d{4}-\d\d-\d\dT.*\+00:00$/.test(oldDetails.tip ?? ''), JSON.stringify(oldDetails));
  await press('Hide');

  // ---- branch record SIF-55: a test the backend never answers is said in words under the button, and a click closes the note --------
  await sleep(1500);                                                            // the page keeps its configuration 800 ms after the last change
  failNextCheck = true;
  await send('Page.reload'); await sleep(300); await loaded('sim');
  await windowTarget(false); far.close();
  const launcherNote = () => evaluate(`(() => { const p = document.querySelector('header .connection-launcher > p.connection-note');
    return p && { text: p.textContent, title: p.title, cursor: getComputedStyle(p).cursor }; })()`);
  let note = null;
  for (let i = 0; i < 50 && !(note = await launcherNote()); i++) await sleep(100);
  check('a test with no answer says so in words under the button (not "Failed to fetch"), as a note a click closes', !failNextCheck && !!note
    && note.text.startsWith('The workbench backend did not answer') && note.title === 'Click to close' && note.cursor === 'pointer', JSON.stringify(note));
  // the pop-up-blocked note is a paragraph there too, with no click: it keeps the arrow (SIF-55 review follow-up)
  const blockedCursor = await evaluate(`(() => { const s = document.querySelector('header .connection-launcher'), p = document.createElement('p');
    p.className = 'error'; s.appendChild(p); const c = getComputedStyle(p).cursor; p.remove(); return c; })()`);
  check('... and only that note shows the hand: the pop-up-blocked note under the pill does not', blockedCursor !== 'pointer', blockedCursor);
  await evaluate(`document.querySelector('header .connection-launcher > p.connection-note').click()`); await sleep(300);
  check('... and a click closes it', !(await launcherNote()), JSON.stringify(await launcherNote()));
  await openWindow();

  // ---- two Virtuoso sessions under one connection: both visible, actions and late replies stay separate ----------
  await select('lab'); await sleep(1000);
  groupedSessions = true; PROFILES.lab2 = 'virtuoso_ssh'; statusAnswer = fixtures.never;
  mark = seen.length;
  await send('Page.reload'); await sleep(300); await loaded('lab');
  await windowTarget(false); far.close();
  check('grouped page load tests only the configured session and reads the sibling cache',
    JSON.stringify(names(mark).sort()) === JSON.stringify(['GET profiles', 'GET status', 'POST check'])
    && seen.slice(mark).filter(s => s.method === 'POST').every(s => s.body.profile_id === 'lab'), names(mark).join(', '));
  // Record 7.351: the work goes to whichever session is free, so the button counts the sessions that passed - not "UNKNOWN"
  // because the second Virtuoso was never tested on this page.
  const pageBadge = () => evaluate(`${BUTTON}.querySelector('.badge').textContent`);
  check('the button counts the sessions whose last test passed', (await pageBadge()) === '1 of 2 OK'
    && (await evaluate(`${BUTTON}.textContent`)).includes('lab - Virtuoso over SSH (2 sessions)'), await evaluate(`${BUTTON}.textContent`));
  // Record 7.361: in a narrow banner (1280 px, still one line) the long name gives way with "..." and the state word stays
  // whole - on the live page it was cut to "unknow" while the name ran past the pill.
  await page.viewport(1280, 900); await sleep(300);
  const pill = await evaluate(`(() => { const b = ${BUTTON}, w = b.querySelector('.connection-button-what'), g = b.querySelector('.badge'), r = b.getBoundingClientRect(), q = g.getBoundingClientRect();
    return { button: Math.round(r.width), past: b.scrollWidth - b.clientWidth, inside: q.left >= r.left - 0.5 && q.right <= r.right + 0.5, badge: g.textContent, name: w.scrollWidth > w.clientWidth ? 'cut' : 'whole' }; })()`);
  check('...in a narrow banner the name gives way with "..." and the state word stays whole (record 7.361)', pill.past <= 0 && pill.inside && pill.badge === '1 of 2 OK', JSON.stringify(pill));
  await page.viewport(1680, 1050); await sleep(300);
  mark = seen.length; await openWindow(1100);
  const sessionsSelector = `${WINDOW}.querySelectorAll('.connection-session')`;
  const sessionNode = id => `${WINDOW}.querySelector('[data-session-profile="${id}"]')`;
  const sessionText = id => far.evaluate(`${sessionNode(id)}.innerText`);
  const sessionPress = (id, label) => far.evaluate(`(() => { const b = [...${sessionNode(id)}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)}); if (!b || b.disabled) return false; b.click(); return true; })()`, true);
  const selectorValues = await far.evaluate(`[...${WINDOW}.querySelector('select').options].map(o => o.value)`);
  check('one lab connection, two simultaneously visible session cards, no session selector',
    (await far.evaluate(`${sessionsSelector}.length`)) === 2 && selectorValues.includes('lab') && !selectorValues.includes('lab2')
    && (await far.evaluate(`${WINDOW}.querySelectorAll('select').length`)) === 1
    && JSON.stringify(await far.evaluate(`[...${sessionsSelector}].map(s => s.querySelector('h3')?.textContent)`)) === JSON.stringify(['Virtuoso 1 (session lab)', 'Virtuoso 2 (session lab2)']), selectorValues.join(', '));
  check('the window says the work goes to whichever session is free', (await text()).includes('go to whichever session is free'));
  // branch record SIF-79: one noun for one thing (the hint said "Each Virtuoso window", then "each session"), and a card's
  // session name says on hover what naming it does - "lab" names the connection too
  const multiHint = await far.evaluate(`[...${WINDOW}.querySelectorAll(':scope > p.hint')].map(p => p.textContent.replace(/\\s+/g, ' ').trim())`);
  const idTips = await far.evaluate(`[...${sessionsSelector}].map(s => s.querySelector('h3 .hint')?.title ?? '')`);
  check('the window says the connection has 2 sessions, "Virtuoso 1 and Virtuoso 2" as the cards are headed, and each card\'s session name says on hover where naming it sends the work (SIF-79)',
    multiHint.some(t => t.startsWith('This connection has 2 sessions, Virtuoso 1 and Virtuoso 2 below, each a Virtuoso with its own bridge')) && !multiHint.some(t => t.includes('Virtuoso window'))
    && idTips[0]?.includes('"lab" in the list above sends the work to whichever session is free') && idTips[1]?.includes('names lab2 sends its work to Virtuoso 2 only'), JSON.stringify({ multiHint, idTips }));
  // branch record SIF-79: a kind the file does not name (Virtuoso 1's) adds no lines, so both cards' steps start level
  const stepTops = await far.evaluate(`[...${sessionsSelector}].map(s => Math.round(s.querySelector('.step .step-head').getBoundingClientRect().top))`);
  check('...and both cards\' first steps start at the same height, though only Virtuoso 2\'s kind is named in the file (SIF-79)', stepTops.length === 2 && stepTops[0] === stepTops[1], JSON.stringify(stepTops));
  check('opening both session cards performs no connect or probe', seen.length === mark, names(mark).join(', '));
  const firstBefore = await sessionText('lab');
  mark = seen.length;
  await sessionPress('lab2', 'Connect SSH'); await settle(mark);
  check('second Connect button addresses only the second configured session', seen.length === mark + 1
    && seen[mark].name === 'connect' && seen[mark].body.profile_id === 'lab2', names(mark).join(', '));
  check('second card has its own IL load path and the cache setup; first card is unchanged',
    (await sessionText('lab2')).includes('/fixture/second/virtuoso_setup.il')
    && (await sessionText('lab2')).includes('setShellEnvVar("RB_NONCE_CACHE_MAX" "32768")')
    && await sessionText('lab') === firstBefore);
  // branch record SIF-79: a CIW line breaks after a "/" or between words, never inside a name (break-all split "virtuoso_bri" |
  // "dge_s2", which read like the box's real line break). The box is narrowed to about 38 characters, so the load line wraps.
  const ciwBreaks = await far.evaluate(`(() => { const code = ${sessionNode('lab2')}.querySelector('.command code'), text = code.textContent;
    const first = document.createRange(); first.setStart(code.firstChild, 0); first.setEnd(code.firstChild, 1);
    code.style.flex = '0 0 ' + Math.ceil(38 * first.getBoundingClientRect().width + 14) + 'px';
    const nodes = [], walk = document.createTreeWalker(code, NodeFilter.SHOW_TEXT); for (let n; (n = walk.nextNode());) nodes.push(n);
    const before = []; let top = null, at = 0;
    for (const node of nodes) for (let i = 0; i < node.length; i++, at++) {
      const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + 1); const box = r.getClientRects()[0];
      if (!box || node.data[i] === '\\n') continue;
      if (top !== null && box.top > top + 2) before.push(text[at - 1]);
      top = box.top; }
    code.style.flex = ''; return { text, before }; })()`);
  check('a CIW line breaks only after a "/", at a space or at its own line end - never inside a name - and its text is the line Copy copies (SIF-79)',
    ciwBreaks.text === 'setShellEnvVar("RB_NONCE_CACHE_MAX" "32768")\nload("/fixture/second/virtuoso_setup.il")' && ciwBreaks.before.includes('/')
    && ciwBreaks.before.every(c => ['/', ' ', '\n'].includes(c)), JSON.stringify(ciwBreaks));
  holdNextCheck = true; mark = seen.length;
  await sessionPress('lab2', 'Test connection'); await settle(mark);
  check('a pending second-session test leaves first-session buttons enabled', !!heldCheck
    && (await far.evaluate(`[...${sessionNode('lab')}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Test connection').disabled`)) === false
    && (await sessionText('lab2')).includes('Testing...'));
  await sessionPress('lab', 'Test connection'); await sleep(600);
  check('the first session can finish its test while the second is still waiting', (await sessionText('lab')).includes('FIXTURE: lab connected')
    && (await sessionText('lab2')).includes('Testing...')
    && JSON.stringify(seen.slice(mark).map(s => s.body.profile_id)) === JSON.stringify(['lab2', 'lab']));
  await heldCheck(); heldCheck = null; await sleep(500);
  check('both session test results and load lines remain in their own cards',
    (await sessionText('lab')).includes('FIXTURE: lab connected') && !(await sessionText('lab')).includes('/fixture/second/')
    && (await sessionText('lab2')).includes('FIXTURE: lab2 connected') && (await sessionText('lab2')).includes('/fixture/second/'));
  check('both sessions passed: the button says OK', (await pageBadge()) === 'OK', await pageBadge());
  await shot('window', '.connection-window', 'connection-8-two-sessions.png');

  // A test still on its way when the page reads the cached results again (another connection chosen and back) keeps its
  // answer, and the older cached read does not put "never tested" back over it (record 7.351; it used to be dropped).
  statusAnswer = fixtures.never; holdNextCheck = true; lateHeadline = 'FIXTURE: lab2 late answer'; mark = seen.length;
  await sessionPress('lab2', 'Test connection'); await settle(mark);
  await select('here'); await select('lab');
  check('the cached reads came back while the second session\'s test was still waiting', !!heldCheck
    && (await sessionText('lab2')).includes('Testing...'), await sessionText('lab2'));
  await heldCheck(); heldCheck = null; lateHeadline = null; await sleep(600);
  check('the late test answer is shown, not the cached "never tested" read before it',
    (await sessionText('lab2')).includes('FIXTURE: lab2 late answer') && !(await sessionText('lab2')).includes('Not tested yet'), await sessionText('lab2'));

  // A configuration that names the second session by its own name (as queues do) is shown as such - not as "lab" - and
  // choosing "lab" in the list takes effect (it did nothing: "lab" was already the value shown).
  await select(''); await sleep(1500);                     // the page keeps its configuration 800 ms after the last change
  activeProfile = 'lab2';
  await send('Target.closeTarget', { targetId: farPage.id }); await windowTarget(false); far.close();
  await send('Page.reload'); await sleep(300); await loaded('lab2');
  check('a configuration naming the second session says so on the button', (await evaluate(`${BUTTON}.textContent`)).includes('lab2 (Virtuoso 2 only)'),
    await evaluate(`${BUTTON}.textContent`));
  await openWindow(1100);
  check('the list shows the named session as the value, beside the connection',
    (await far.evaluate(`${WINDOW}.querySelector('select').value`)) === 'lab2'
    && JSON.stringify(await far.evaluate(`[...${WINDOW}.querySelector('select').options].map(o => o.value)`)).includes('"lab","here"')
    && (await text()).includes('names Virtuoso 2 by its own name (lab2)'), await far.evaluate(`${WINDOW}.querySelector('select').value`));
  await select('lab');
  check('choosing the connection lets the work go to whichever session is free again', (await evaluate(`${BUTTON}.textContent`)).includes('lab - Virtuoso over SSH (2 sessions)')
    && (await far.evaluate(`${WINDOW}.querySelector('select').value`)) === 'lab' && !(await text()).includes('by its own name'), await evaluate(`${BUTTON}.textContent`));
  activeProfile = 'lab';
  await shot('window', '.connection-window', 'connection-9-session-named.png');

  // ---- Enter in the new connection's name (branch record SIF-109) ---------------------------------------------------------
  // Enter there did nothing - only "Create connection" added it -, while the ngspice window's path box reads its file on
  // Enter. A name the form refuses still sends nothing.
  const NAME_BOX = `${WINDOW}.querySelector('.connection-add input')`;
  const enterInName = async () => { await far.evaluate(`${NAME_BOX}.focus()`);
    for (const type of ['keyDown', 'keyUp']) await far.send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); };
  await press('Add a connection...');
  await far.until(`!!${WINDOW}.querySelector('.connection-add select')`, 50);       // the setup is read again after the reloads above
  await choose('.connection-add select', 'ngspice_local'); await sleep(200);
  await far.setValue(NAME_BOX, 'lab', { event: 'input' }); await sleep(200);
  mark = seen.length;
  await enterInName(); await sleep(800);
  check('Enter in the name of a connection that exists already sends nothing (branch record SIF-109)', seen.length === mark
    && (await far.evaluate(`${WINDOW}.querySelector('.connection-add').innerText`)).includes('A connection with this name already exists.'), names(mark).join(', '));
  await far.setValue(NAME_BOX, 'sim-enter', { event: 'input' }); await sleep(200);
  mark = seen.length;
  await enterInName(); await settle(mark);
  pressed = seen.slice(mark).filter(s => s.method === 'POST');
  check('... in a free name it adds the connection, as "Create connection" does: one request with the name and the kind (SIF-109)', pressed.length === 1 && pressed[0].name === 'profile'
    && JSON.stringify(pressed[0].body) === JSON.stringify({ profile_id: 'sim-enter', kind: 'ngspice_local' }) && (await text()).includes('Connection "sim-enter" was added'), JSON.stringify(pressed.map(p => p.body)));

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
