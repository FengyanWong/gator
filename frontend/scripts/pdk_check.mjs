// Browser check of "Load PDK" and the network's component list (Pdk.tsx, the RL model window;
// user request 2026-09-21: "make the optimizer understand all the components in one provided PDK ... add load PDK in the
// frontend"). It uses the shared harness (lib/harness.mjs, as every other check since the review of 2026-09-22): a
// throwaway headless Edge over the DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/).
// Everything about PDKs is answered with canned data labelled FIXTURE - GET /api/pdks, GET /api/pdks/<id>,
// POST /api/pdks/load (so no PDK is read and nothing reaches Virtuoso) -, /api/config/validate with an empty report,
// /api/connection/profiles with NO profile, the page's own start-up reads pass, and every other writing request is
// refused here: the check is hermetic and safe against the live backend. The browser profile is new and temporary, so
// the user's saved configuration is not touched.
// What it pins:
//   - the RL model window has a "Components" list (standard first) and a plain line saying what the chosen list knows;
//     no load button there since 2026-09-27: the PDK is read with the cell in the Virtuoso window, whose "PDK window..."
//     button (beside Refresh) opens the PDK window;
//   - choosing a loaded PDK writes run.network.vocabulary; the standard list is written as NO field (old servers accept
//     it); another encoder keeps the chosen list;
//   - a configuration naming a PDK that is not loaded says so;
//   - "PDK window..." opens the PDK window: the form, the connection it reads through, the loaded PDKs (double click shows
//     one, with every component, its pins and roles, its parameters, and its model files' sizes in a unit - the exact
//     bytes on hover, branch record SIF-52; so does Enter on its row, which is in the Tab order with its focus ring, branch
//     record SIF-121); "Load" sends exactly the typed fields, shows that it
//     is reading, then shows the answer and reads the list again - so does Enter in either box, never while a box holds what
//     Load refuses (branch record SIF-109); without a connection it cannot be pressed; closing the
//     Virtuoso window closes it too (2026-09-29). The Virtuoso window is opened as a user opens it since record 7.362: the
//     Tasks window's "New task: From a Virtuoso cell..."; without a connection it says to choose one, with Connection...
//     beside the words, which opens the Connection window from it (branch record SIF-108);
//   - the ideal parts read with a PDK (record 7.190: analogLib's sources, ideal R / C / L, probes, controlled sources): the
//     window says that every read brings them, the list has their count, a shown PDK names how many were read and which have
//     a kind of their own, their list is folded and shows both pin orders of one component; a PDK answered without them (an
//     older server, a PDK loaded before) says that they were not read. The heading, the sentence, the fold and the table count
//     alike: the fold counts the parts the heading counts and the refused one apart, whose kind reads "refused: no pin order",
//     and one unknown part reads "the other one reaches it" (branch record SIF-142).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/pdk_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { NETWORK_DOCUMENT, NETWORK_PANEL, openNetworks } from './lib/rl_networks.mjs';
import path from 'node:path';
import { check, focusOn, launchEdge, mockStarter, newTaskFrom, outDir, pressEnter, runChecks, sleep, validConfiguration, workbenchUrl, CONNECTION_WINDOW, VIRTUOSO_WINDOW, PDK_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('pdk');

// ---- FIXTURE: one loaded PDK "fixpdk" with three components; a load answers "fixload" --------------------------------
const summary = (n, fam) => ({ devices: n, cells: n, by_family: fam, with_problems: [] });
const entry = (id, n, fam, sha) => ({ pdk_id: id, vocabulary: `pdk:${id}`, sha256: sha, version: `pdk-${id}-${sha.slice(0, 16)}`, loaded_utc: '2026-09-21T21:00:00+00:00',
  technology_library: id, summary: summary(n, fam), label: `PDK ${id} (${n} components, version ${sha.slice(0, 8)})`, sources: { model_files: [{ path: `/fixture/${id}.scs`, bytes: 48213337, sha256: sha }] },
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
// FIXTURE: the ideal parts read with fixpdk - four Spectre components of the generic library; fixload is answered WITHOUT
// them, as a server from before record 7.190 answers
const IDEAL = { library: 'analogLib', read_utc: '2026-10-05T14:00:00+00:00', sha256: 'c'.repeat(64), error: null, not_read_again: null,
  summary: { cells: 9, components: 4, recognized: 3, with_a_kind: ['isource', 'vsource'], as_unknown: 1, without_pins: ['mutual_inductor'] } };
const part = (component, kind, cells, orders) => ({ component, kind, cells, basis: `FIXTURE basis of ${component}`, parameters: {},
  pin_orders: orders.map(([pins, of]) => ({ pins, cells: of })), cells_without_pin_order: orders.length ? [] : cells, cells_with_too_many_pins: [] });
const IDEAL_PARTS = [
  part('isource', 'isource', ['idc'], [[['PLUS', 'MINUS'], ['idc']]]),
  part('mtline', 'unknown', ['mtline'], [[Array.from({ length: 12 }, (_, i) => `p${i + 1}`), ['mtline']]]),
  part('mutual_inductor', 'unknown', ['mind'], []),
  part('vsource', 'vsource', ['vdc', 'vprbs', 'vpulse'], [[['PLUS', 'MINUS'], ['vdc', 'vpulse']], [['PLUS', 'MINUS', 'P1', 'M1', 'P2', 'M2'], ['vprbs']]]),
];
const FIXPDK = { ...entry('fixpdk', 3, { 'mos:n': 1, 'bjt:npn': 1, inductor: 1 }, 'a'.repeat(64)), ideal_parts: IDEAL };
const FIXLOAD = entry('fixload', 2, { resistor: 2 }, 'b'.repeat(64));
const details = (e, devices) => ({ ...e, devices, not_netlisted: [{ cell: 'ringfx', reason: 'FIXTURE: no Spectre entry' }], layout_only: [{ cell: 'crossfx', views: ['layout'] }],
  not_used: ['fx_core'], parameters: [], terminal_roles: [], ...(e.ideal_parts ? { ideal_parts: { ...e.ideal_parts, components: IDEAL_PARTS, not_components: [] } } : {}) });
const STANDARD = { vocabulary: 'standard', label: 'standard (8 generic kinds)', kinds: [], parameters: [] };
const VALID = validConfiguration();

await runChecks(browser, async () => {
  const starter = await mockStarter(APP);
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
    if (name === '/api/virtuoso/libraries') return fulfil(requestId, 200, { libraries: [] });      // the Virtuoso window opens; nothing reaches Virtuoso
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

  const RUN = NETWORK_PANEL;
  const LIST = `${RUN}.querySelector('.component-list')`;
  const SELECT = `${LIST}.querySelector('select')`;
  // Record 7.265: the encoder is chosen in New model's templates table (it was an Encoder select); the list follows that table.
  const ENCODER = `${RUN}.querySelector('table.template-table')`;
  const choose = (select, value) => page.setValue(`${select}`, value);
  const storedNetwork = async () => (await page.stored())?.run?.network ?? null;
  // The page keeps its configuration in this browser 800 ms after the last change (store.ts): wait for it, then read it.
  const storedWhen = async test => { for (let i = 0; i < 40; i++) { const n = await storedNetwork(); if (test(n)) return n; await sleep(100); } return storedNetwork(); };

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'missing' });
  await send('Page.navigate', { url: APP });
  let networkPage = await openNetworks(page, browser);
  if (!(await until(`!!(${RUN})`, 150))) throw new Error('the Run configuration never appeared: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  if (!(await until(`!!(${LIST})`, 50))) throw new Error('no component list: the served frontend is older than this change (build it, then reload)');
  await until(`${SELECT}.options.length > 1`, 50);

  // ---- the line in the RL model window ----------------------------------------------------------------------------------
  const line = await evaluate(`(() => { const l = ${LIST}, s = l.querySelector('select'), b = l.querySelector('button.pdk-open'), r = l.querySelector('.component-row');
    return { label: r.querySelector('label').firstChild.textContent.trim(), value: s.value, options: [...s.options].map(o => [o.value, o.textContent]), button: b?.textContent,
      sameRow: !!b && b.parentElement === r, what: l.querySelector('.component-what')?.textContent ?? '', helpFolded: !l.querySelector('details.component-help').open,
      afterEncoder: !!(${ENCODER}) && (${ENCODER}.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING) > 0 }; })()`);
  check('the template\'s settings have a "Components" list after the templates table', line.label === 'Components' && line.afterEncoder, JSON.stringify(line.label));
  // Record 7.298: the device families are the list of a new model and come first; the standard list is offered only to a
  // configuration that still holds it (this seeded one does), last.
  check('standard is chosen, as this configuration holds it; the device families are listed first, the loaded PDK after them, standard last',
    line.value === 'standard' && line.options[0][0] === 'families' && line.options[1]?.[0] === 'pdk:fixpdk' && line.options[1][1] === FIXPDK.label
    && line.options.at(-1)[0] === 'standard' && line.options.length === 3, JSON.stringify(line.options));
  check('no load button in the block any more: the PDK comes with the cell, from the Virtuoso window', !line.button, String(line.button));
  check('the plain line says what the standard list knows, what it does not, what a new model uses and where a PDK list comes from',
    /MOS, R, C, L and sources/.test(line.what) && /"unknown"/.test(line.what) && /New models use device families/.test(line.what)
    && /Reading a cell loads its PDK and adds that component list here/.test(line.what), line.what);
  check('the longer explanation is folded (closed <details>)', line.helpFolded);
  check('page load read the list of loaded PDKs (local files) and started no load', listReads >= 1 && loadBodies.length === 0);
  const fits = await evaluate(`(() => { const right = ${NETWORK_DOCUMENT}.documentElement, panel = ${RUN}.getBoundingClientRect(),
    select = ${LIST}.querySelector('.component-row select').getBoundingClientRect();
    // As wide as the panel lets it, up to 640 px (branch record SIF-30: the RL model window grows with a wide window; a list of
    // short names stops at 640 px there).
    return { noSideScroll: right.scrollWidth <= right.clientWidth + 1, inside: select.left >= panel.left - 1 && select.right <= panel.right + 1,
      wide: select.width >= Math.min(panel.width * 0.8, 640) - 1, width: Math.round(select.width), panel: Math.round(panel.width) }; })()`);
  check('the list spans the column (up to 640 px), with no sideways scrolling', fits.noSideScroll && fits.inside && fits.wide, JSON.stringify(fits));
  const room = await evaluate(`(() => { const s = ${LIST}.querySelector('.component-row select'), c = getComputedStyle(s);
    return { room: s.clientHeight - parseFloat(c.paddingTop) - parseFloat(c.paddingBottom), line: parseFloat(c.lineHeight) || 1.25 * parseFloat(c.fontSize) }; })()`);
  check('the list is as tall as its line needs - its text is not cut (branch record SIF-31)', room.room >= room.line - 1, JSON.stringify(room));

  // ---- choosing a list --------------------------------------------------------------------------------------------------
  await choose(SELECT, 'pdk:fixpdk');
  let network = await storedWhen(n => n?.vocabulary === 'pdk:fixpdk');
  check('choosing the PDK writes run.network.vocabulary', network?.vocabulary === 'pdk:fixpdk', JSON.stringify(network));
  const what = await evaluate(`${LIST}.querySelector('.component-what').textContent`);
  check('... and the line names its components by family', /Knows all 3 components of fixpdk: 1 n-MOS, 1 npn, 1 inductor/.test(what), what);
  const useTemplate = name => evaluate(`${RUN}.querySelector('tr.template-row[data-encoder="${name}"] button.template-use')?.click()`);
  const other = await evaluate(`[...${RUN}.querySelectorAll('tr.template-row')].map(r => r.dataset.encoder).find(e => e !== ${RUN}.querySelector('tr.template-row.current')?.dataset.encoder)`);
  await useTemplate(other);
  network = await storedWhen(n => n?.encoder_type === other);
  check('another encoder keeps the chosen list', network?.encoder_type === other && network?.vocabulary === 'pdk:fixpdk', JSON.stringify(network));
  await useTemplate(net.encoder_type);
  await storedWhen(n => n?.encoder_type === net.encoder_type);
  const offered = await evaluate(`[...${SELECT}.options].map(o => o.value)`);
  check('once another list is chosen the standard list is no longer offered', !offered.includes('standard') && offered[0] === 'families', JSON.stringify(offered));
  await choose(SELECT, 'families');
  network = await storedWhen(n => n?.vocabulary === 'families');
  const families = await evaluate(`${LIST}.querySelector('.component-what').textContent`);
  check('choosing the device families writes them by name, and the line says they fit any PDK', network?.vocabulary === 'families'
    && /device families across PDKs/.test(families) && /can load with any PDK/.test(families), JSON.stringify(network) + ' / ' + families);
  // Branch record SIF-52: the line said "The list of a new model since record 7.298.", and the folded help promised more
  // "on the MOCK backend", which the workbench no longer has.
  const help = await evaluate(`${LIST}.querySelector('details.component-help').textContent`);
  check('... it says "A new model uses this list." (no record number), and the help says a Parameters row varies them and each instance\'s property form decides a real run\'s writes',
    /Default for new models:/.test(families) && !/record \d/.test(families) && !/MOCK/.test(help)
    && /voltages\) by a Parameters row; what a real run may write in Virtuoso is decided\s+by each instance's property form\./.test(help), families + ' / ' + help);

  // ---- the window ---------------------------------------------------------------------------------------------------------
  // Since 2026-09-27 the PDK window opens from the Virtuoso window: its "PDK window..." button beside Refresh (the PDK is
  // read with the cell there). The Virtuoso window itself opens from the Tasks window's "New task: From a Virtuoso cell..."
  // (record 7.362; the Project column's "Virtuoso cell..." until then): the Tasks window holds that click, so the Virtuoso
  // window is a pop-up of a pop-up already; it is found by its title, and the Tasks window is closed again. Its libraries
  // listing is answered with none, so nothing reaches Virtuoso. The click on "PDK window..." happens IN the Virtuoso window,
  // which is what lets the browser open the PDK window from it (popupWindow.ts, `open(from)`).
  let virtuoso = null;
  const openPdkWindow = async except => {
    if (!virtuoso) {
      const { tasks, pressed } = await newTaskFrom(page, browser, 'virtuoso');
      const found = pressed ? await browser.window(VIRTUOSO_WINDOW, { ms: 10000 }).catch(() => null) : null;
      await tasks.close();
      if (!found) return null;
      virtuoso = await browser.attach(found, { errors: consoleErrors, prefix: 'Virtuoso window: ' });
      await virtuoso.until(`!!document.querySelector('.virtuoso-window button.pdk-open')`, 60);
    }
    await virtuoso.evaluate(`document.querySelector('.virtuoso-window button.pdk-open').click()`, true);
    return browser.window(PDK_WINDOW, { ms: 10000, ...(except ? { except } : {}) }).catch(() => null);
  };
  const target = await openPdkWindow();
  check('"PDK window..." in the Virtuoso window opens the PDK window (a pop-up from a pop-up)', !!target);
  const popup = await browser.attach(target, { errors: consoleErrors, prefix: 'PDK window: ' });
  const pev = expression => popup.evaluate(expression, true);
  await popup.viewport(1100, 900);
  await popup.until(`!!document.querySelector('.pdk-window')`);
  // the list comes from a read the window starts when it opens: read it once it is there (record 7.178; read at once, it was
  // now and then still empty under load, and the double click below then found no row)
  await popup.until(`document.querySelectorAll('.pdk-window .pdk-list tbody tr').length > 0`, 60);
  const win = await pev(`(() => { const w = document.querySelector('.pdk-window'); return { heading: w.querySelector('h2')?.textContent, inputs: [...w.querySelectorAll('.pdk-form input')].map(i => i.placeholder),
    load: w.querySelector('button.pdk-load')?.textContent, disabled: w.querySelector('button.pdk-load')?.disabled, link: w.textContent.includes('Through connection fixture-link'),
    rows: [...w.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent), folded: !w.querySelector('details').open }; })()`);
  check('the window shows "Load PDK" with its two optional boxes and a Load button', win.heading === 'Load PDK' && win.inputs.length === 2 && win.load === 'Load' && !win.disabled, JSON.stringify(win));
  check('it names the connection it reads through', win.link);
  check('it lists the loaded PDKs; the how-it-decides text is folded', JSON.stringify(win.rows) === '["fixpdk"]' && win.folded, JSON.stringify(win.rows));
  // Branch record SIF-59: when it was loaded in local time as the Runs window writes a time, the UTC on hover (it was the
  // browser's own form, "21/09/2026, 22:00:00" in an en-GB browser). Edge and this script share the Windows clock.
  const loadedCell = await pev(`[...document.querySelectorAll('.pdk-list tbody tr')].map(r => [r.cells[3].textContent, r.cells[3].title])[0]`);
  const local = (d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:`
    + `${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`)(new Date('2026-09-21T21:00:00+00:00'));
  check('the Loaded column gives the local time as the Runs window writes it, the UTC on hover', JSON.stringify(loadedCell) === JSON.stringify([local, '2026-09-21T21:00:00+00:00 (UTC)']), JSON.stringify(loadedCell));
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
  // Branch record SIF-52: a model file's size in a unit, the exact count on hover (it read "48213337 bytes").
  const files = await pev(`[...[...document.querySelectorAll('.pdk-details details')].find(d => d.querySelector('summary')?.textContent === 'Model files read')?.querySelectorAll('tbody tr') ?? []]
    .map(r => [r.cells[1].textContent, r.cells[1].title])`);
  check('"Model files read" gives each file\'s size in a unit, with the exact bytes on hover', JSON.stringify(files) === '[["46.0 MiB","48213337 bytes"]]', JSON.stringify(files));
  // ---- the ideal parts read with the PDK (record 7.190) -----------------------------------------------------------------------
  const ideal = await pev(`(() => { const w = document.querySelector('.pdk-window'), list = w.querySelector('details.ideal-list');
    return { says: w.querySelector('p.hint').textContent.includes('Each read also brings the ideal parts of analogLib'),
      heads: [...w.querySelectorAll('.pdk-list thead th')].map(h => h.textContent), count: w.querySelector('.pdk-list tbody tr').cells[2].textContent,
      head: w.querySelector('.ideal-head')?.textContent, what: w.querySelector('.ideal-what')?.textContent, folded: !!list && !list.open,
      summary: list?.querySelector('summary')?.textContent }; })()`);
  check('the window says that each read also brings the ideal parts of analogLib', ideal.says);
  check('the list of loaded PDKs has an "Ideal parts" column with their count', ideal.heads[2] === 'Ideal parts' && ideal.count === '3', JSON.stringify([ideal.heads, ideal.count]));
  // Branch record SIF-142: one unknown part in the right number - it read "the other 1 reach it as "unknown", with their pins named".
  check('a shown PDK names its ideal parts: how many, from which library, which have a kind of their own, which are "unknown"',
    ideal.head === 'Ideal parts: 3 from analogLib' && /2 have a kind of their own for the network \(isource, vsource\); the other one reaches it as "unknown", with its pins named\./.test(ideal.what)
    && /states no pin order for mutual_inductor/.test(ideal.what), JSON.stringify([ideal.head, ideal.what]));
  // ...and the fold counts the 3 of the heading and of the Loaded PDKs column, the refused part apart: it read "(4)" (SIF-142).
  check('their list is folded, and counts what the heading counts, the refused part apart', ideal.folded && ideal.summary === 'The ideal parts (3, and 1 refused)', String(ideal.summary));
  await pev(`document.querySelector('.pdk-window details.ideal-list summary').click()`);
  const parts = await pev(`[...document.querySelectorAll('.pdk-window details.ideal-list tbody tr')].map(r => [...r.cells].map(c => c.textContent))`);
  const source = parts.find(r => r[0] === 'vsource') ?? [];
  check('opened, a row names the Spectre component, its kind, every pin order and the cells', source[1] === 'vsource'
    && source[2] === 'PLUS MINUS | PLUS MINUS P1 M1 P2 M2' && source[3] === 'vdc, vprbs, vpulse', JSON.stringify(source));
  check('... a long pin order is cut short with its length, and a component without one shows "-"',
    (parts.find(r => r[0] === 'mtline') ?? [])[2] === 'p1 p2 p3 p4 p5 p6 p7 p8 ... (12 pins)' && (parts.find(r => r[0] === 'mutual_inductor') ?? [])[2] === '-', JSON.stringify(parts.map(r => r[2])));
  // The kind of a part with no pin order is that it is refused, as the sentence says - it read "unknown", like a part the network
  // reads (branch record SIF-142).
  check('... and its kind reads "refused: no pin order", where a part the network reads as "unknown" keeps "unknown"',
    (parts.find(r => r[0] === 'mutual_inductor') ?? [])[1] === 'refused: no pin order' && (parts.find(r => r[0] === 'mtline') ?? [])[1] === 'unknown', JSON.stringify(parts.map(r => r[1])));
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
  // The list is read again after the answer is drawn: wait for it (branch record SIF-31 - read at once, it failed once in a
  // two-lane run).
  const relisted = await popup.until(`[...document.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent).join() === 'fixpdk,fixload'`, 40);
  check('the answer is shown and the list read again', relisted && listReads > readsBefore,
    await pev(`[...document.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[0].textContent).join()`));
  const older = await pev(`({ none: document.querySelector('.pdk-window .ideal-none')?.textContent ?? null, head: !!document.querySelector('.pdk-window .ideal-head'),
    counts: [...document.querySelectorAll('.pdk-list tbody tr')].map(r => r.cells[2].textContent) })`);
  check('a PDK answered without ideal parts (an older server, a PDK loaded before) says that they were not read', /not read with this PDK/.test(older.none ?? '') && !older.head
    && JSON.stringify(older.counts) === '["3","not read"]', JSON.stringify(older));
  // Branch record SIF-109: Enter in either box loads when Load can be pressed - it did nothing, while the ngspice window's path
  // box reads on Enter. A box holding what Load refuses sends nothing.
  const typeIn = async (index, text) => { await pev(`(() => { const i = document.querySelectorAll('.pdk-form input')[${index}]; i.focus(); i.select(); })()`);
    await popup.send('Input.insertText', { text }); await sleep(200); };
  const enterIn = async index => { await pev(`document.querySelectorAll('.pdk-form input')[${index}].focus()`);
    for (const type of ['keyDown', 'keyUp']) await popup.send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); };
  await typeIn(0, 'fix load'); await enterIn(0); await sleep(500);
  check('Enter in the library box while it holds what Load refuses sends nothing (branch record SIF-109)', loadBodies.length === 1
    && /A plain Cadence library name/.test(await pev(`document.querySelector('.pdk-window p.error')?.textContent ?? ''`)), JSON.stringify(loadBodies));
  await typeIn(0, 'fixload'); await typeIn(1, '/fixture/models/fx.scs');
  holdLoad = null;
  await enterIn(1);
  for (let i = 0; i < 50 && !holdLoad; i++) await sleep(100);
  holdLoad?.();
  check('... Enter in the model file box loads, as Load does: the typed fields are sent (SIF-109)',
    JSON.stringify(loadBodies.slice(1)) === JSON.stringify([{ profile_id: 'fixture-link', technology_library: 'fixload', model_file: '/fixture/models/fx.scs' }]), JSON.stringify(loadBodies));
  await popup.until(`document.querySelector('button.pdk-load')?.textContent === 'Load'`, 60);
  // Branch record SIF-121: a loaded PDK's row takes Enter, as a run's row does (SIF-109) - a double click was the only way to
  // show one, so a keyboard could not show a loaded PDK at all. fixload is shown now, from the load above.
  const PDK_ROW = `[...document.querySelectorAll('.pdk-list tbody tr')].find(r => r.cells[0].textContent === 'fixpdk')`;
  const pdkFocus = await focusOn(popup, PDK_ROW);
  check('a loaded PDK\'s row is in the Tab order, its focus ring inside it as a run row\'s; its tooltip and the hint under the list name Enter (branch record SIF-121)',
    !!pdkFocus?.held && pdkFocus.tabIndex === 0 && pdkFocus.ring === 'solid 2px -2px' && await pev(`(${PDK_ROW}).title`) === 'Double click, or Enter, to show what was read'
    && /^Double click a row, or press Enter on it, to show it\./.test(await pev(`document.querySelector('.pdk-list').nextElementSibling?.textContent ?? ''`)), JSON.stringify(pdkFocus));
  const PDK_SHOWN = `document.querySelector('.pdk-details h3')?.textContent ?? 'nothing shown'`, shownBefore = await pev(PDK_SHOWN);
  await pressEnter(popup);
  check('... and Enter on it shows that PDK, as its double click does: fixpdk, after fixload (SIF-121)', shownBefore === 'fixload: 2 components'
    && await popup.until(`(${PDK_SHOWN}) === 'fixpdk: 3 components'`, 40) && await pev(`(${PDK_ROW}).classList.contains('active')`), `${shownBefore} -> ${await pev(PDK_SHOWN)}`);
  await until(`[...${SELECT}.options].some(o => o.value === 'pdk:fixload')`, 30);
  check('the newly loaded PDK can be chosen in the RL model window at once', await evaluate(`[...${SELECT}.options].some(o => o.value === 'pdk:fixload')`));
  await sleep(300);
  {                                              // the templates table down to the component list, in a tall viewport
    await networkPage.viewport(1100, 2600); await sleep(300);
    const clip = await evaluate(`(() => { ${ENCODER}.scrollIntoView({ block: 'start' }); const a = ${ENCODER}.getBoundingClientRect(), b = ${LIST}.getBoundingClientRect();
      return { x: Math.min(a.x, b.x) - 4, y: a.y - 4, width: Math.max(a.right, b.right) - Math.min(a.x, b.x) + 8, height: b.bottom - a.y + 8, scale: 1.5 }; })()`);
    await networkPage.shot(path.join(out, 'pdk-2-list.png'), clip);
    await networkPage.viewport(1100, 900);
  }

  // ---- no connection; a list that is not loaded --------------------------------------------------------------------------------
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', JSON.stringify({ ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')),
    run: { ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run, connection_profile_id: null, network: { ...JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.network, vocabulary: 'pdk:gone' } } }))`);
  loaded = false;
  const firstWindow = target?.id;
  await send('Page.reload'); networkPage = await openNetworks(page, browser); await until(`!!(${LIST}) && ${SELECT}.options.length > 1`, 150); await sleep(500);
  const gone = await evaluate(`(() => { const l = ${LIST}; return { value: l.querySelector('select').value, option: [...l.querySelectorAll('option')].map(o => o.textContent).pop(), warn: l.querySelector('.warn')?.textContent ?? '' }; })()`);
  check('a configuration naming a PDK that is not loaded says so', gone.value === 'pdk:gone' && gone.option === 'PDK gone (not loaded)' && /not loaded here/.test(gone.warn), JSON.stringify(gone));
  // The reload took both windows with it (the page closes what it opened), so the buttons open them again.
  virtuoso = null;
  const again = await openPdkWindow(firstWindow);
  if (again) {
    popup.close();
    const second = await browser.attach(again, { errors: consoleErrors, prefix: 'PDK window (no connection): ' });
    await second.until(`!!document.querySelector('.pdk-window')`, 40);
    const none = await second.evaluate(`({ disabled: document.querySelector('button.pdk-load')?.disabled, warn: document.querySelector('.pdk-window .warn')?.textContent ?? '' })`);
    check('without a connection, Load cannot be pressed and the window says what to do', none.disabled === true && /Choose a connection first/.test(none.warn), JSON.stringify(none));
    // Branch record SIF-108: without a connection the Virtuoso window says to choose one there and carries the button to the
    // Connection window beside its words (it said 'Press "Connection" in the workbench'); the press opens that window from
    // the Virtuoso window, which holds the click.
    const LINE = `document.querySelector('.virtuoso-window .line-act.no-connection')`;
    const noLink = await virtuoso.evaluate(`(() => { const l = ${LINE}; return l && { text: l.querySelector('p.warn')?.textContent.replace(/\\s+/g, ' ') ?? '',
      buttons: [...l.querySelectorAll('button')].map(b => b.textContent.trim()), title: l.querySelector('button')?.title ?? '' }; })()`);
    check('... the Virtuoso window says to choose a Virtuoso connection, which lists its libraries there, with Connection... beside its words (branch record SIF-108)',
      noLink?.text === 'No connection is chosen: choose a Virtuoso connection in the Connection window. Choosing one lists its libraries here.'
      && JSON.stringify(noLink.buttons) === '["Connection..."]' && noLink.title.startsWith('Connection: Opens the Connection window'), JSON.stringify(noLink));
    await virtuoso.evaluate(`${LINE}.querySelector('button').click()`, true);
    const linkWindow = await browser.window(CONNECTION_WINDOW, { ms: 10000 }).catch(() => null);
    const link = linkWindow && await browser.attach(linkWindow, { errors: consoleErrors, prefix: 'Connection window: ' });
    const opened = link && await link.until(`!!document.querySelector('.connection-window h2')`, 50)
      && await link.evaluate(`({ heading: document.querySelector('.connection-window h2').textContent, opener: window.opener?.document.title ?? null })`);
    check('... its press opens the Connection window, from the Virtuoso window (the window that holds the click)', opened?.heading === 'Connection' && opened.opener === VIRTUOSO_WINDOW,
      JSON.stringify(opened));
    if (link) { link.close(); await send('Target.closeTarget', { targetId: linkWindow.id }).catch(() => undefined); }
    // The PDK window belongs to the Virtuoso window it was opened from (review of 2026-09-29): closing that one closes it too,
    // instead of leaving it blank, with nothing left to draw it.
    second.close();
    await send('Target.closeTarget', { targetId: virtuoso.target.id });
    check('closing the Virtuoso window closes the PDK window opened from it', await browser.window(PDK_WINDOW, { present: false, ms: 5000 }).then(() => true, () => false));
  } else check('without a connection, the window opens again after a reload', false, 'no second window');

  check('no writing request other than the canned ones reached the backend', refused.length === 0, refused.join(', '));
  check('no uncaught error in the page', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
});
