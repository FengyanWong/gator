// Browser check of the ngspice window (user request 2026-09-23; there is no frontend test runner): a throwaway headless
// Edge over the DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/), with a new, temporary
// browser profile. EVERY /api/* request is paused: GETs, static validation and the load of the MOCK task pass through
// (read-only); the ngspice routes are answered with canned FIXTURES here (so the check does not depend on the backend
// version), and every other writing request is refused - nothing is started, saved or probed. Safe on the live backend.
// What it pins: ONE button "ngspice netlist..." in the Project column with its text beside it; the window opens (title
// "GATOR - ngspice netlist") and sends nothing by itself; Example loads a deck through /api/ngspice/read (the path under
// the repository); Check sends the text and shows the summary (elements, results with units, problems); Save sends the
// name, text, kinds and labels, then the column follows the new task (the Task list shows it as [ngspice]) and the
// editors hold its starter rows; a saved ngspice task shows its block in the column (revision, results, Delete task);
// the launchers follow the connection in use (/api/connection/profiles answered by fixtures: none chosen = both, a
// Virtuoso connection = "Virtuoso cell..." only, an ngspice connection = "ngspice netlist..." only), and the Task list
// lists the ngspice tasks under the same rule, except the task the page follows (record 7.77).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/ngspice_window_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, PAGE_OPEN_TEST, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('ngspice');

const DECK = '* Five-transistor OTA on generic level-1 MOS models\n.model nch nmos level=1\nvdd vdd 0 dc 1.8\nm1 out in 0 0 nch W=4u L=0.5u\n.control\nop\nlet vout_v = v(out)\nprint vout_v\n.endc\n.end\n';
const CHECK = { ok: true, title: 'Five-transistor OTA on generic level-1 MOS models', devices: 2, nets: 3, kinds: { vsource: 1, nmos: 1 }, sizable: ['m1.l', 'm1.w', 'vdd.dc'],
  measurements: [{ name: 'vout_v', analysis: 'dc', unit: 'V', line: 8, text: 'print vout_v' }], analyses: ['op'], includes: [], unknown_models: [], subckt_uses: {},
  has_control: true, has_end: true, diagnostics: [], problems: [] };
const STARTER = { project: { name: 'fixture_ota', task_name: 'fixture_ota' }, circuit: { source: 'registered_task', task_id: 'ngspice:fixture_ota', circuit_class: 'opamp', pdk_id: 'unspecified' },
  parameters: [{ variable_id: 'm1_w', instance_path: 'm1', parameter_name: 'w', unit: 'um', scale: 'linear', value_type: 'continuous', optimized: true, lower: 2, upper: 8, notes: 'w on line 4' }],
  measurements: [{ measurement_id: 'm_vout_v', analysis: 'dc', result_source: 'backend_profile', source_name: 'vout_v', unit: 'V', notes: 'line 8: print vout_v' }], targets: [] };
const ENTRY = { name: 'fixture_ota', task_key: 'ngspice:fixture_ota', revision: 1, created_utc: '2026-09-23T00:00:00+00:00', updated_utc: '2026-09-23T00:00:00+00:00',
  netlist_sha256: 'a'.repeat(64), source_path: null, device_kinds: {}, circuit_class: 'opamp', pdk_id: 'unspecified', title: CHECK.title,
  measurements: [{ name: 'vout_v', analysis: 'dc', unit: 'V' }], devices: 2, sizable: 3, simulator: 'ngspice' };
const LOADED = { loaded: true, task_key: 'ngspice:fixture_ota', mock: false, simulator: 'ngspice', content_sha256: 'a'.repeat(64), provided_metrics: ['vout_v'],
  circuit: { ...ENTRY, evaluation_backend: 'ngspice (REAL circuit simulation)', dut_hierarchy: null, netlist_sha256: 'a'.repeat(64), topology_id: 'ngspice:fixture_ota',
    complete: true, ngspice_task: true, measurements: ['vout_v'], sizable: ['m1.l', 'm1.w', 'vdd.dc'], connection_problem: 'This task runs on ngspice. Choose an ngspice connection in the Connection window.', unknown_models: [] },
  hierarchy: { vdd: {}, m1: {} }, summary: { device_count: 2, devices: [{ instance_path: 'vdd', kind: 'vsource', parameters: {} }, { instance_path: 'm1', kind: 'nmos', parameters: {} }], nets: [], unknown_devices: [] },
  complete: true, diagnostics: [], analysis_context: [], notes: ['ngspice netlist task, revision 1: 2 elements, 1 result (vout_v).'], evaluation_backend: 'ngspice (REAL circuit simulation)',
  max_concurrency: 4, native_draft: false, generated_profile: false, baseline_recorded: null };

await runChecks(browser, async () => {
  const meta = await (await fetch(new URL('api/meta', APP))).json();
  const page = await browser.open();
  const { send, evaluate, until, consoleErrors } = page;
  const sent = [];   // every ngspice request: { name, body }
  const refused = [];
  let tasksSeen = 0, saved = false;
  // The connection list is a fixture: no connection at first (so the page adopts none and shows both launchers), later two
  // connections of the two families. The live backend's file - and its active connection - never reaches the page.
  const KINDS = [{ kind: 'virtuoso_ssh', family: 'virtuoso', transport: 'ssh', label: 'Virtuoso over SSH', summary: '' },
    { kind: 'ngspice_local', family: 'ngspice', transport: 'local', label: 'ngspice on this machine', summary: '' }];
  let connections = [];
  const profilesAnswer = () => ({ active: null, connection_file: 'FIXTURE', connection_file_exists: connections.length > 0, kinds: KINDS,
    profiles: connections.map(c => ({ profile_id: c.id, bridge_profile: null, kind: c.kind, kind_declared: true, family: c.family, transport: 'ssh', kind_label: c.kind, settings_present: ['kind'] })) });
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    const body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/connection/profiles') return page.fulfil(requestId, 200, profilesAnswer());
    if (name === '/api/connection/status') return page.fulfil(requestId, 200, { profile_id: null, overall: 'unknown', layers: [], stale: true });
    if (name.startsWith('/api/ngspice/')) {
      sent.push({ name, body });
      if (name === '/api/ngspice/read') return page.fulfil(requestId, 200, { path: body.path, text: DECK, size: DECK.length });
      if (name === '/api/ngspice/check') return page.fulfil(requestId, 200, CHECK);
      if (name === '/api/ngspice/task/save') { saved = true; return page.fulfil(requestId, 200, { ...ENTRY, name: body.name, task_key: `ngspice:${body.name}`, directory: '/x', created: true, starter: STARTER, check: CHECK }); }
      if (name === '/api/ngspice/task') return page.fulfil(requestId, 200, { ...ENTRY, text: DECK });
      return page.refuse(requestId, 'FIXTURE: not answered');
    }
    if (name === '/api/tasks') {                                                                   // the list: the backend's own until a save, then the fixture task with the MOCK one
      tasksSeen++;
      if (!saved) return page.pass(requestId);
      return page.fulfil(requestId, 200, { tasks: [
        { task_key: 'synthetic:gpdk045_ota5', kind: 'mock', circuit_class: 'opamp', pdk_id: 'gpdk045', available: true, description: 'MOCK', starter_project: { name: 'mock-gpdk045-ota5', task_name: 'mock_gpdk045_ota5' } },
        { task_key: 'ngspice:fixture_ota', kind: 'ngspice', circuit_class: 'opamp', pdk_id: 'unspecified', available: false, blocker: 'needs an ngspice connection',
          revision: 1, title: CHECK.title, simulator: 'ngspice', description: 'fixture', starter_project: { name: 'fixture_ota', task_name: 'fixture_ota' } }], real_interface_contract: {} });
    }
    if (name === '/api/tasks/starter' && new URL(request.url).searchParams.get('task_key') === 'ngspice:fixture_ota') return page.fulfil(requestId, 200, STARTER);
    if (name === '/api/circuit/load' && body?.circuit?.task_id === 'ngspice:fixture_ota') return page.fulfil(requestId, 200, LOADED);
    if (request.method === 'GET' || name === '/api/config/validate' || name === '/api/circuit/load') return page.pass(requestId);
    if (name === '/api/connection/check') return page.fulfil(requestId, 200, PAGE_OPEN_TEST(body?.profile_id ?? null));   // the page's one test when it opens (7.80): canned, not a write of its own
    if (name !== '/api/output/check') refused.push(`${request.method} ${name}`);
    return page.refuse(requestId, 'FIXTURE: this check lets no other request through');
  };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Registered task'))`;
  const LAUNCHER = `${PANEL}.querySelector('.row.ngspice-launcher')`;
  const text = () => evaluate(`${PANEL}.textContent`);
  const shot = async (name, expression = `document.querySelector('.left')`) => page.shot(path.join(out, name), expression);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: { schema_version: 'gator-workbench-config-v1', project: { name: 'gator-project', task_name: 'task', notes: '' },
    circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' },
    parameters: [], targets: [], measurements: [], run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0 }, output: { experiment_name: 'x' }, research: {} } });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${PANEL}) && !!(${LAUNCHER})`, 150))) throw new Error('the Project column never showed the ngspice launcher | console: ' + consoleErrors.join(' | ').slice(0, 300));
  await sleep(1500);

  // ---- the column: one button, its text beside it, nothing sent -------------------------------------------------------------
  check('one short button "ngspice netlist..." with what it is for as text beside it',
    (await evaluate(`${LAUNCHER}.querySelector('button.ngspice-button')?.textContent.trim()`)) === 'ngspice netlist...'
    && (await evaluate(`${LAUNCHER}.querySelector('.hint')?.textContent`)).includes('From an ngspice netlist'));
  check('the column holds no netlist form of its own (no text box, no path field)', !(await evaluate(`!!${PANEL}.querySelector('textarea, input[placeholder*=".cir"]')`)));
  check('nothing was sent to the ngspice routes on page load', sent.length === 0);

  // ---- the window opens on the press, reads nothing by itself -------------------------------------------------------------------
  await evaluate(`${LAUNCHER}.querySelector('button.ngspice-button').click()`, true);
  const target = await browser.window('GATOR - ngspice netlist', { ms: 8000 });
  check('the window opened with its title', !!target);
  const win = await browser.attach(target);
  const W = `document.querySelector('.ngspice-window')`;
  await win.until(`!!(${W})`, 60);
  await sleep(600);
  check('the window holds a name box, a file path box with Load and Example, the deck text box, Check and Save', await win.evaluate(`(() => { const w = ${W};
    const buttons = [...w.querySelectorAll('button')].map(b => b.textContent.trim());
    return !!w.querySelector('textarea.ngspice-text') && ['Load', 'Example', 'Check', 'Save as task'].every(b => buttons.includes(b))
      && [...w.querySelectorAll('label')].some(l => l.firstChild?.textContent.trim() === 'Task name'); })()`));
  check('opening the window sent nothing', sent.length === 0);
  check('Save is disabled while there is no deck', await win.evaluate(`[...${W}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save as task').disabled`));
  await win.shot(path.join(out, 'ngspice-1-window.png'), W);

  // ---- Example loads the repository's deck through /api/ngspice/read --------------------------------------------------------
  await win.evaluate(`[...${W}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Example').click()`, true);
  for (let i = 0; i < 60 && !sent.some(s => s.name === '/api/ngspice/read'); i++) await sleep(100);
  await sleep(700);
  const read = sent.find(s => s.name === '/api/ngspice/read');
  check('Example asked the backend to read the example deck under the repository', !!read && read.body.path === `${meta.repo_root}/examples/circuits/ngspice_ota5_level1.cir`, JSON.stringify(read?.body));
  check('the deck fills the text box and the name is proposed', (await win.evaluate(`${W}.querySelector('textarea.ngspice-text').value`)) === DECK
    && (await win.evaluate(`[...${W}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'Task name').querySelector('input').value`)) === 'ota5_level1');

  // ---- Check sends the text and shows the summary ----------------------------------------------------------------------------------
  await win.evaluate(`[...${W}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Check').click()`, true);
  for (let i = 0; i < 60 && !sent.some(s => s.name === '/api/ngspice/check'); i++) await sleep(100);
  await sleep(700);
  const checked = sent.find(s => s.name === '/api/ngspice/check');
  check('Check sends the deck text (and the kinds box, empty)', !!checked && checked.body.text === DECK && checked.body.device_kinds === '', JSON.stringify(checked?.body ?? null).slice(0, 200));
  const summary = await win.evaluate(`${W}.querySelector('.ngspice-check')?.textContent ?? ''`);
  check('the summary names the title, the elements, the values a run can vary and the results with their units',
    summary.includes(CHECK.title) && summary.includes('2 elements') && summary.includes('3 values a run can vary') && summary.includes('vout_v') && summary.includes('V'), summary.slice(0, 200));
  await win.shot(path.join(out, 'ngspice-2-checked.png'), W);

  // ---- Save: the task is stored, the column follows it, the editors hold its rows ----------------------------------------------------
  await win.setValue(`[...${W}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'Task name').querySelector('input')`, 'fixture_ota', { event: 'input' });
  await sleep(200);
  await win.evaluate(`[...${W}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save as task').click()`, true);
  for (let i = 0; i < 80 && !sent.some(s => s.name === '/api/ngspice/task/save'); i++) await sleep(100);
  await sleep(2500);
  const save = sent.find(s => s.name === '/api/ngspice/task/save');
  check('Save sends the name, the deck, the kinds and the labels - nothing else', !!save && save.body.name === 'fixture_ota' && save.body.text === DECK
    && save.body.device_kinds === '' && save.body.circuit_class === 'unspecified' && save.body.pdk_id === 'unspecified' && save.body.source_path === `${meta.repo_root}/examples/circuits/ngspice_ota5_level1.cir`
    && Object.keys(save.body).sort().join() === 'circuit_class,device_kinds,name,pdk_id,source_path,text', JSON.stringify(save?.body ?? null).slice(0, 300));
  check('the window says the task was saved and the column follows it', (await win.evaluate(`${W}.querySelector('p.ok')?.textContent ?? ''`)).includes('Saved the new task ngspice:fixture_ota'));
  const chosen = await evaluate(`[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'Task')?.querySelector('select').value`);
  check('the Project column follows ngspice:fixture_ota, listed as [ngspice]', chosen === 'ngspice:fixture_ota'
    && await evaluate(`[...${PANEL}.querySelectorAll('option')].some(o => o.value === 'ngspice:fixture_ota' && o.textContent.includes('[ngspice'))`));
  const config = await evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') || 'null')`);
  check('the editors hold the task\'s starter rows (Parameters, Probes) and Specs is empty', config?.parameters?.[0]?.variable_id === 'm1_w'
    && config?.measurements?.[0]?.measurement_id === 'm_vout_v' && (config?.targets ?? []).length === 0, JSON.stringify(config?.parameters ?? null).slice(0, 120));
  const column = await text();
  check('the column shows the ngspice task block: backend line, the connection sentence, revision, results, Delete task',
    column.includes('ngspice evaluation backend') && column.includes('Choose an ngspice connection') && column.includes('revision 1') && column.includes('vout_v')
    && await evaluate(`[...${PANEL}.querySelectorAll('button')].some(b => b.textContent.trim() === 'Delete task')`), column.slice(0, 300));
  check('the launcher text names the task the page follows', (await evaluate(`${LAUNCHER}.querySelector('.hint')?.textContent`)).includes('ngspice task: fixture_ota'));
  const aligned = await evaluate(`(() => { const a = ${PANEL}.querySelector('button.virtuoso-button').getBoundingClientRect(), b = ${LAUNCHER}.querySelector('button.ngspice-button').getBoundingClientRect();
    return { sameColumn: Math.abs(a.left - b.left) < 1 && Math.abs(a.right - b.right) < 1, below: b.top > a.bottom }; })()`);
  check('the two window buttons stand under each other in one column of the same width', aligned.sameColumn && aligned.below, JSON.stringify(aligned));
  check('no red Blocked box for the followed task', !(await evaluate(`!!${PANEL}.querySelector('.blocker')`)));
  await shot('ngspice-3-column.png');
  check('the window now offers the next revision', (await win.evaluate(`[...${W}.querySelectorAll('button')].map(b => b.textContent.trim())`)).includes('Save (next revision)'));

  // ---- the launchers follow the connection in use, and so do the ngspice tasks in the Task list (records 7.76, 7.77) -----------------
  connections = [{ id: 'fixture-lab', kind: 'virtuoso_ssh', family: 'virtuoso' }, { id: 'fixture-sim', kind: 'ngspice_local', family: 'ngspice' }];
  const TASK_SELECT = `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'Task')?.querySelector('select')`;
  const launchers = () => evaluate(`(() => { const p = ${PANEL}; return { virtuoso: !!p.querySelector('button.virtuoso-button'), ngspice: !!p.querySelector('button.ngspice-button'),
    tasks: [...((${TASK_SELECT})?.options ?? [])].map(o => o.textContent.trim()) }; })()`);
  // The page reloaded with the connection `id` in use and, when one is given, another task followed (its rows emptied; the MOCK
  // task's load passes through to the backend, read-only).
  const withConnection = async (id, task = null) => {
    const stored = JSON.parse(await evaluate(`localStorage.getItem('gator-workbench-config-v1')`));
    await page.seed({ config: { ...stored, ...(task ? { circuit: { ...stored.circuit, source: 'registered_task', task_id: task }, parameters: [], measurements: [], targets: [] } : {}),
      run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0, connection_profile_id: id } } });
    await send('Page.navigate', { url: APP });
    await until(`!!(${PANEL})`, 150); await sleep(2000);
    return launchers();
  };
  const ngspiceListed = shown => shown.tasks.filter(t => t.startsWith('ngspice:'));
  const onVirtuoso = await withConnection('fixture-lab');
  check('with a Virtuoso connection in use the column offers "Virtuoso cell..." only', onVirtuoso.virtuoso && !onVirtuoso.ngspice, JSON.stringify(onVirtuoso));
  check('the ngspice task the page follows stays listed there, marked "choose its connection"', ngspiceListed(onVirtuoso).length === 1
    && onVirtuoso.tasks.some(t => t.startsWith('ngspice:fixture_ota') && t.includes('choose its connection')), JSON.stringify(onVirtuoso.tasks));
  const onVirtuosoMock = await withConnection('fixture-lab', 'synthetic:gpdk045_ota5');
  check('with the MOCK task followed and a Virtuoso connection in use, no ngspice task is listed (the example shows only while ngspice is connected)',
    onVirtuosoMock.tasks.some(t => t.startsWith('synthetic:gpdk045_ota5')) && ngspiceListed(onVirtuosoMock).length === 0, JSON.stringify(onVirtuosoMock.tasks));
  const onNgspice = await withConnection('fixture-sim');
  check('with an ngspice connection in use it offers "ngspice netlist..." only', !onNgspice.virtuoso && onNgspice.ngspice, JSON.stringify(onNgspice));
  check('and the ngspice task is listed again', onNgspice.tasks.some(t => t.startsWith('ngspice:fixture_ota')), JSON.stringify(onNgspice.tasks));
  await shot('ngspice-4-launcher-ngspice.png');
  const onNone = await withConnection(null);
  check('with no connection chosen it offers both', onNone.virtuoso && onNone.ngspice, JSON.stringify(onNone));
  check('and lists the ngspice task (the same rule as the button)', onNone.tasks.some(t => t.startsWith('ngspice:fixture_ota')), JSON.stringify(onNone.tasks));

  check('the page asked nothing else of the backend (every request besides reads is refused here)', refused.length === 0, refused.join(' | '));
  check('no console errors in the page', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
