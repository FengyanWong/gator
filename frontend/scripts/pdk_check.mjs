// Browser check of "Load PDK" and the network's component list (Pdk.tsx, RL network block of "Run configuration";
// user request 2026-09-21: "make the optimizer understand all the components in one provided PDK ... add load PDK in the
// frontend"). It uses the shared harness (lib/harness.mjs, as every other check since the review of 2026-09-22): a
// throwaway headless Edge over the DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/).
// Everything about PDKs is answered with canned data labelled FIXTURE - GET /api/pdks, GET /api/pdks/<id>,
// POST /api/pdks/load (so no PDK is read and nothing reaches Virtuoso) -, /api/config/validate with an empty report,
// /api/connection/profiles with NO profile, the page's own start-up reads pass, and every other writing request is
// refused here: the check is hermetic and safe against the live backend. The browser profile is new and temporary, so
// the user's saved configuration is not touched.
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
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('pdk');

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

  const page = await browser.open({ consoleApi: false });
  const { send, fulfil, consoleErrors } = page;
  const refused = [];
  let loaded = false, listReads = 0, loadBodies = [], holdLoad = null;
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
    // Everything else: the page's own start-up reads pass (a circuit, an output root's writability without creating it),
    // every other writing request is refused and listed.
    return page.readOrRefuse({ requestId, request }, refused, { reads: true });
  };
  const evaluate = expression => page.evaluate(expression, true);
  // A page that is still rendering (after a reload) answers "not yet", not an error: the expressions below reach
  // through elements that do not exist yet.
  const until = (expression, tries = 60) => page.until(`(() => { try { return !!(${expression}); } catch { return false; } })()`, tries);

  const RUN = `[...document.querySelectorAll('.right .panel')].find(p => p.querySelector('h3')?.textContent.trim() === 'Run configuration')`;
  const LIST = `${RUN}.querySelector('.component-list')`;
  const SELECT = `${LIST}.querySelector('select')`;
  const ENCODER = `[...${RUN}.querySelectorAll('label')].find(l => l.firstChild?.textContent?.trim() === 'Encoder')?.querySelector('select')`;
  const choose = (select, value) => evaluate(`(() => { const s = ${select}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)}); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const storedNetwork = async () => (await page.stored())?.run?.network ?? null;
  // The page keeps its configuration in this browser 800 ms after the last change (store.ts): wait for it, then read it.
  const storedWhen = async test => { for (let i = 0; i < 40; i++) { const n = await storedNetwork(); if (test(n)) return n; await sleep(100); } return storedNetwork(); };

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'missing' });
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
  const target = await browser.window('GATOR - PDK', { ms: 10000 }).catch(() => null);
  check('"Load PDK..." opens the PDK window', !!target);
  const popup = await browser.attach(target, { errors: consoleErrors, prefix: 'PDK window: ' });
  const pev = expression => popup.evaluate(expression, true);
  await popup.viewport(1100, 900);
  await popup.until(`!!document.querySelector('.pdk-window')`);
  const win = await pev(`(() => { const w = document.querySelector('.pdk-window'); return { heading: w.querySelector('h2')?.textContent, inputs: [...w.querySelectorAll('.pdk-form input')].map(i => i.placeholder),
    load: w.querySelector('button.pdk-load')?.textContent, disabled: w.querySelector('button.pdk-load')?.disabled, link: w.textContent.includes('Through connection fixture-link'),
    rows: [...w.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent), folded: !w.querySelector('details').open }; })()`);
  check('the window shows "Load PDK" with its two optional boxes and a Load button', win.heading === 'Load PDK' && win.inputs.length === 2 && win.load === 'Load' && !win.disabled, JSON.stringify(win));
  check('it names the connection it reads through', win.link);
  check('it lists the loaded PDKs; the how-it-decides text is folded', JSON.stringify(win.rows) === '["fixpdk"]' && win.folded, JSON.stringify(win.rows));
  await pev(`document.querySelector('.pdk-list tbody tr').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  await popup.until(`!!document.querySelector('.pdk-devices')`);
  const shown = await pev(`(() => { const t = document.querySelector('.pdk-devices'); return { rows: [...t.querySelectorAll('tbody tr')].map(r => [...r.cells].map(c => c.textContent)),
    head: document.querySelector('.pdk-details h3')?.textContent, hint: document.querySelector('.pdk-details .hint')?.textContent }; })()`);
  check('a double click shows the PDK: one row per component', shown.rows.length === 3 && shown.head === 'fixpdk: 3 components', JSON.stringify(shown.head));
  const bjt = shown.rows.find(r => r[1] === 'fx_npn') ?? [];
  check('each row names its kind, cells, pins with roles and the parameters the network reads', bjt[0] === 'npn' && bjt[2] === 'npnfx'
    && bjt[3] === 'C collector, B base, E emitter, S bulk' && bjt[4] === 'area = bjt.area, m (count)', JSON.stringify(bjt));
  check('... a parameter kept under another column is shown so (the inductor radius)', shown.rows.some(r => r[1] === 'fx_ind' && r[4].startsWith('r = rad (m)')));
  check('a non-numeric setting is not listed as something the network reads', !shown.rows.find(r => r[1] === 'fx_nch')[4].includes('region'));
  await popup.shot(path.join(out, 'pdk-window-1-shown.png'), `document.querySelector('.pdk-window')`, { maxHeight: 1400, beyond: true });

  // ---- Load ---------------------------------------------------------------------------------------------------------------
  await pev(`(() => { const i = document.querySelectorAll('.pdk-form input')[0]; i.focus(); i.select(); })()`);
  await popup.send('Input.insertText', { text: 'fixload' }); await sleep(200);
  const readsBefore = listReads;
  pev(`document.querySelector('button.pdk-load').click()`).catch(() => undefined);
  const reading = await popup.until(`document.querySelector('button.pdk-load')?.textContent === 'Reading...' && document.querySelector('button.pdk-load').disabled`, 40);
  check('while it reads, the button says "Reading..." and cannot be pressed again', reading);
  for (let i = 0; i < 50 && !holdLoad; i++) await sleep(100);      // the button changes before the request is under way
  holdLoad?.();
  await popup.until(`document.querySelector('.pdk-details h3')?.textContent === 'fixload: 2 components'`, 60);
  check('Load sent exactly the typed fields (empty model file = the connection\'s)', JSON.stringify(loadBodies) === JSON.stringify([{ profile_id: 'fixture-link', technology_library: 'fixload', model_file: null }]), JSON.stringify(loadBodies));
  check('the answer is shown and the list read again', (await pev(`[...document.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent).join()`)) === 'fixpdk,fixload' && listReads > readsBefore);
  await until(`[...${SELECT}.options].some(o => o.value === 'pdk:fixload')`, 30);
  check('the newly loaded PDK can be chosen in the RL network block at once', await evaluate(`[...${SELECT}.options].some(o => o.value === 'pdk:fixload')`));
  await sleep(300);
  {                                              // the encoder row down to the component list, in a tall viewport
    await page.viewport(browser.width, 2600); await sleep(300);
    const clip = await evaluate(`(() => { ${ENCODER}.scrollIntoView({ block: 'start' }); const a = ${ENCODER}.closest('label').getBoundingClientRect(), b = ${LIST}.getBoundingClientRect();
      return { x: Math.min(a.x, b.x) - 4, y: a.y - 4, width: Math.max(a.right, b.right) - Math.min(a.x, b.x) + 8, height: b.bottom - a.y + 8, scale: 1.5 }; })()`);
    await page.shot(path.join(out, 'pdk-2-list.png'), clip);
    await page.viewport(browser.width, browser.height);
  }

  // ---- no connection; a list that is not loaded --------------------------------------------------------------------------------
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', JSON.stringify({ ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')),
    run: { ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run, connection_profile_id: null, network: { ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.network, vocabulary: 'pdk:gone' } } }))`);
  loaded = false;
  const firstWindow = target?.id;
  await send('Page.reload'); await until(`!!(${LIST}) && ${SELECT}.options.length > 1`, 150); await sleep(500);
  const gone = await evaluate(`(() => { const l = ${LIST}; return { value: l.querySelector('select').value, option: [...l.querySelectorAll('option')].map(o => o.textContent).pop(), warn: l.querySelector('.warn')?.textContent ?? '' }; })()`);
  check('a configuration naming a PDK that is not loaded says so', gone.value === 'pdk:gone' && gone.option === 'PDK gone (not loaded)' && /not loaded here/.test(gone.warn), JSON.stringify(gone));
  // The reload took the first window with it (the page closes what it opened), so the button opens another one.
  await evaluate(`${LIST}.querySelector('button.pdk-open').click()`); await sleep(800);
  const again = await browser.window('GATOR - PDK', { ms: 10000, except: firstWindow }).catch(() => null);
  if (again) {
    popup.close();
    const second = await browser.attach(again, { errors: consoleErrors, prefix: 'PDK window (no connection): ' });
    await second.until(`!!document.querySelector('.pdk-window')`, 40);
    const none = await second.evaluate(`({ disabled: document.querySelector('button.pdk-load')?.disabled, warn: document.querySelector('.pdk-window .warn')?.textContent ?? '' })`);
    check('without a connection, Load cannot be pressed and the window says what to do', none.disabled === true && /Choose a connection first/.test(none.warn), JSON.stringify(none));
  } else check('without a connection, the window opens again after a reload', false, 'no second window');

  check('no writing request other than the canned ones reached the backend', refused.length === 0, refused.join(', '));
  check('no uncaught error in the page', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
