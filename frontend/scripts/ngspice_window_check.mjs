// Browser check of the ngspice window (user request 2026-09-23; there is no frontend test runner): a throwaway headless
// Edge over the DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/), with a new, temporary
// browser profile. EVERY /api/* request is paused: GETs, static validation and the load of the MOCK task pass through
// (read-only); the ngspice routes are answered with canned FIXTURES here (so the check does not depend on the backend
// version), and every other writing request is refused - nothing is started, saved or probed. Safe on the live backend.
// What it pins: ONE button "From an ngspice netlist..." in the Tasks window's "New task:" row, after "From a Virtuoso
// cell..." (record 7.362; until then "ngspice netlist..." in the Project column with its text beside it); the window opens
// (title "GATOR - ngspice netlist"), sends nothing by itself and stays open when the Tasks window that opened it closes;
// Example loads a deck through /api/ngspice/read (the path under the repository) and says its size in a unit; Check sends
// the text and shows the summary (elements by kind in words, counts in the singular for one, results with units, problems,
// a diagnostic's words with its code on hover - branch record SIF-52); the kinds box and the help name no PDK's devices; Save sends the name, text, kinds and labels, then the page follows the
// new task (its name on the editors' tab line, marked [ngspice]) and the editors hold its starter rows; a saved ngspice
// task says under the editors' toolbar that it runs on ngspice and which connection it needs, shows its block in the
// circuit column (revision, results), has "ngspice netlist..." back to its deck on the tab line and Delete task in the
// Tasks window (record 7.362); the launchers follow the connection in use (/api/connection/profiles answered by fixtures:
// none chosen = both, a Virtuoso connection = "From a Virtuoso cell..." only, an ngspice connection = "From an ngspice
// netlist..." only; the tab line's "ngspice netlist..." by the same rule), and the Tasks window lists the ngspice tasks
// under the same rule - every task, marked "choose its connection" while that connection is not in use (records 7.77, 7.227).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/ngspice_window_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, CIRCUIT_PANEL, CONNECTION_WINDOW, launchEdge, outDir, PAGE_OPEN_TEST, runChecks, showCircuit, sleep, TASK_PANEL, TASKS_WINDOW, taskWindow, workbenchUrl, NGSPICE_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('ngspice');

const DECK = '* Five-transistor OTA on generic level-1 MOS models\n.model nch nmos level=1\nvdd vdd 0 dc 1.8\nm1 out in 0 0 nch W=4u L=0.5u\n.control\nop\nlet vout_v = v(out)\nprint vout_v\n.endc\n.end\n';
const CHECK = { ok: true, title: 'Five-transistor OTA on generic level-1 MOS models', devices: 2, nets: 3, kinds: { vsource: 1, nmos: 1 }, sizable: ['m1.l', 'm1.w', 'vdd.dc'],
  measurements: [{ name: 'vout_v', analysis: 'dc', unit: 'V', line: 8, text: 'print vout_v' }], analyses: ['op'], includes: [], unknown_models: [], subckt_uses: {},
  has_control: true, has_end: true, problems: [],
  // One canned diagnostic (the deck itself has none): the window lists its words, with its severity and code on hover.
  diagnostics: [{ code: 'unknown_device', severity: 'warning', message: 'FIXTURE: x1: subcircuit my_nfet is not defined in the netlist and its kind is not declared' }] };
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
  let tasksSeen = 0, profilesSeen = 0, saved = false;
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
    if (name === '/api/connection/profiles') { profilesSeen++; return page.fulfil(requestId, 200, profilesAnswer()); }
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
  // Record 7.362 (the user's Option D): the editors are the task's card - its name and revision start their tab line, the way
  // back to its window ends it (span.task-tools), its own lines stand under the toolbar (div.task-status); the circuit column is
  // folded away until "Show circuit"; the two ways to a new task are the Tasks window's "New task:" row.
  const PANEL = TASK_PANEL;
  const STATUS = `${PANEL}.querySelector('.task-status')`;
  const TOOLS = `${PANEL}.querySelector('.tabs .task-tools')`;
  const NEW = `document.querySelector('.task-window-new')`;                                     // in the Tasks window
  const ROWED = `!!(${PANEL}) && !!${PANEL}.querySelector('.tabs .task-row button.task-list-button')`;
  // A netlist form of its own: a text box (the editors' formula bar is the table cells' own) or a deck's path field.
  const FORM = root => `[...(${root}?.querySelectorAll('textarea, input[placeholder*=".cir"]') ?? [])].some(e => !e.closest('.formula-bar'))`;
  const deckButton = () => evaluate(`${TOOLS}?.querySelector('button.ngspice-button')?.textContent.trim() ?? null`);
  // The editors' card from its tab line to the end of the task's lines; the circuit column as it stands.
  const shotTask = async name => page.shot(path.join(out, name), await evaluate(`(() => { const p = ${PANEL}.getBoundingClientRect(), s = ${STATUS}.getBoundingClientRect();
    return { x: p.x, y: p.y, width: p.width, height: Math.max(s.bottom, p.y + 80) - p.y + 2, scale: 1 }; })()`));
  const shot = async (name, expression = CIRCUIT_PANEL) => page.shot(path.join(out, name), expression);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: { schema_version: 'gator-workbench-config-v1', project: { name: 'gator-project', task_name: 'task', notes: '' },
    circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' },
    parameters: [], targets: [], measurements: [], run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0 }, output: { experiment_name: 'x' }, research: {} } });
  await send('Page.navigate', { url: APP });
  if (!(await until(ROWED, 150))) throw new Error('the editors\' tab line never showed the task row | console: ' + consoleErrors.join(' | ').slice(0, 300));
  await sleep(1500);

  // ---- the Tasks window's New task row (record 7.362): one button, "New task:" beside it, nothing sent --------------------------------
  check('nothing was sent to the ngspice routes on page load', sent.length === 0);
  check('while the page follows the MOCK task the tab line has no "ngspice netlist..." (the way back to an ngspice task\'s deck)', (await deckButton()) === null, await deckButton());
  // Since record 7.227 the task's name is the button that opens the Tasks window (harness taskWindow drives it).
  const tw = taskWindow(page, browser);
  const tasks = await tw.open();
  const offer = await tasks.evaluate(`(() => { const r = ${NEW}; return r && { hint: r.querySelector('.hint')?.textContent.trim() ?? '',
    ngspice: [...r.querySelectorAll('button.ngspice-button')].map(b => b.textContent.trim()), virtuoso: [...r.querySelectorAll('button.virtuoso-button')].map(b => b.textContent.trim()) }; })()`);
  check('the Tasks window offers ONE short button "From an ngspice netlist..." in its "New task:" row', !!offer && offer.hint === 'New task:'
    && offer.ngspice.length === 1 && offer.ngspice[0] === 'From an ngspice netlist...', JSON.stringify(offer));
  const aligned = await tasks.evaluate(`(() => { const r = ${NEW}, parts = [r?.querySelector('.hint'), r?.querySelector('button.virtuoso-button'), r?.querySelector('button.ngspice-button')];
    if (!parts.every(Boolean)) return null;
    const [h, a, b] = parts.map(e => e.getBoundingClientRect()), middle = x => (x.top + x.bottom) / 2;
    return { oneLine: Math.abs(middle(a) - middle(b)) < 2 && Math.abs(middle(h) - middle(a)) < 4, inOrder: h.right <= a.left && a.right <= b.left }; })()`);
  check('the two New task buttons stand in one line after "New task:", "From a Virtuoso cell..." first', !!aligned?.oneLine && aligned.inOrder, JSON.stringify(aligned));
  check('neither the page nor the Tasks window holds a netlist form of its own (no deck text box, no path field)', !(await evaluate(FORM(PANEL)))
    && !(await evaluate(FORM(CIRCUIT_PANEL))) && !(await tasks.evaluate(FORM(`document.querySelector('.task-window')`))));

  // ---- the window opens on the press, reads nothing by itself, and outlives the Tasks window that opened it --------------------------------
  await tasks.evaluate(`${NEW}.querySelector('button.ngspice-button').click()`, true);          // a user's press in the Tasks window (as harness newTaskFrom)
  const target = await browser.window(NGSPICE_WINDOW, { ms: 8000 });
  check('the window opened with its title', !!target);
  const win = await browser.attach(target);
  const W = `document.querySelector('.ngspice-window')`;
  await win.until(`!!(${W})`, 60);
  await tw.close();
  const tasksClosed = await browser.window(TASKS_WINDOW, { present: false, ms: 3000, except: page.target.id }).then(() => true, () => false);
  await sleep(600);
  check('it stays open when the Tasks window that opened it closes: the page keeps it (record 7.362)', tasksClosed && !win.closed
    && await win.evaluate(`!!(${W})`).catch(() => false) && !!(await browser.window(NGSPICE_WINDOW, { ms: 500 }).catch(() => null)));
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
  // Branch record SIF-52: the size in a unit (it read "(N bytes)"); the fixture's deck is under 1 KiB.
  const loadedText = await win.evaluate(`${W}.querySelector('p.ok')?.textContent ?? ''`);
  check('the green line names the file and its size in a unit', loadedText === `Loaded ${read?.body.path} (${DECK.length} B). Check it, then save it as a task.`, loadedText);
  // Branch record SIF-52: the example names are no PDK's own devices.
  const neutral = await win.evaluate(`(() => { const w = ${W}, box = [...w.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'name=kind pairs');
    return { placeholder: box?.querySelector('input')?.placeholder ?? null, help: [...w.querySelectorAll('.steps-list li')].find(l => l.textContent.startsWith('Models the deck does not define'))?.textContent ?? '' }; })()`);
  check('the kinds box and the help give neutral example names', neutral.placeholder === 'my_nfet=nmos my_pfet=pmos' && neutral.help.includes('(a PDK cell as X1 ... my_nfet)'), JSON.stringify(neutral));

  // ---- Check sends the text and shows the summary ----------------------------------------------------------------------------------
  await win.evaluate(`[...${W}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Check').click()`, true);
  for (let i = 0; i < 60 && !sent.some(s => s.name === '/api/ngspice/check'); i++) await sleep(100);
  await sleep(700);
  const checked = sent.find(s => s.name === '/api/ngspice/check');
  check('Check sends the deck text (and the kinds box, empty)', !!checked && checked.body.text === DECK && checked.body.device_kinds === '', JSON.stringify(checked?.body ?? null).slice(0, 200));
  const summary = await win.evaluate(`${W}.querySelector('.ngspice-check')?.textContent ?? ''`);
  check('the summary names the title, the elements, the values a run can vary and the results with their units',
    summary.includes(CHECK.title) && summary.includes('2 elements') && summary.includes('3 values a run can vary') && summary.includes('vout_v') && summary.includes('V'), summary.slice(0, 200));
  // Branch record SIF-52: the kinds in words and one result in the singular (it read "(1 vsource, 1 nmos) ... 1 results.").
  const first = await win.evaluate(`${W}.querySelector('.ngspice-check p')?.textContent ?? ''`);
  check('... in words: "2 elements (1 voltage source, 1 nmos), 3 nets, 3 values a run can vary, 1 result."',
    first === `${CHECK.title}: 2 elements (1 voltage source, 1 nmos), 3 nets, 3 values a run can vary, 1 result.`, first);
  // Branch record SIF-52 (as SIF-5 in the editors' Issues column): the words, with the code on hover (it read "1 diagnostics",
  // then "unknown_device: ...").
  const diagnostics = await win.evaluate(`(() => { const d = [...${W}.querySelectorAll('.ngspice-check details')].find(x => /diagnostic/.test(x.querySelector('summary')?.textContent ?? ''));
    return d && { summary: d.querySelector('summary').textContent, items: [...d.querySelectorAll('li')].map(l => [l.textContent, l.title]) }; })()`);
  check('the diagnostics fold says "1 diagnostic" and lists its words, its severity and code on hover', diagnostics?.summary === '1 diagnostic'
    && JSON.stringify(diagnostics.items) === JSON.stringify([[CHECK.diagnostics[0].message, 'warning: unknown_device']]), JSON.stringify(diagnostics));
  await win.shot(path.join(out, 'ngspice-2-checked.png'), W);

  // ---- Save: the task is stored, the page follows it, the editors hold its rows ------------------------------------------------------
  await win.setValue(`[...${W}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === 'Task name').querySelector('input')`, 'fixture_ota', { event: 'input' });
  await sleep(200);
  await win.evaluate(`[...${W}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save as task').click()`, true);
  for (let i = 0; i < 80 && !sent.some(s => s.name === '/api/ngspice/task/save'); i++) await sleep(100);
  await sleep(2500);
  const save = sent.find(s => s.name === '/api/ngspice/task/save');
  check('Save sends the name, the deck, the kinds and the labels - nothing else', !!save && save.body.name === 'fixture_ota' && save.body.text === DECK
    && save.body.device_kinds === '' && save.body.circuit_class === 'unspecified' && save.body.pdk_id === 'unspecified' && save.body.source_path === `${meta.repo_root}/examples/circuits/ngspice_ota5_level1.cir`
    && Object.keys(save.body).sort().join() === 'circuit_class,device_kinds,name,pdk_id,source_path,text', JSON.stringify(save?.body ?? null).slice(0, 300));
  check('the window says the task was saved and the page follows it', (await win.evaluate(`${W}.querySelector('p.ok')?.textContent ?? ''`)).includes('Saved the new task ngspice:fixture_ota'));
  // The task's name on the editors' tab line since record 7.362 (the Project column's Task row since record 7.227 until then).
  const chosen = await tw.current();
  check('the editors\' tab line names ngspice:fixture_ota, marked [ngspice]', chosen === 'ngspice:fixture_ota'
    && (await evaluate(`${PANEL}.querySelector('.tabs .task-row .task-list-mark')?.textContent ?? ''`)).includes('[ngspice'), chosen);
  const config = await evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') || 'null')`);
  check('the editors hold the task\'s starter rows (Parameters, Probes) and Specs is empty', config?.parameters?.[0]?.variable_id === 'm1_w'
    && config?.measurements?.[0]?.measurement_id === 'm_vout_v' && (config?.targets ?? []).length === 0, JSON.stringify(config?.parameters ?? null).slice(0, 120));
  // The ngspice task block of the Project column, in its two places since record 7.362: what the task needs under the toolbar,
  // the deck's revision and results in the circuit column; Delete task is in the Tasks window.
  const lines = await evaluate(`${STATUS}?.textContent ?? ''`);
  check('under the editors\' toolbar the task says it runs on ngspice and needs an ngspice connection', lines.includes('ngspice evaluation backend')
    && lines.includes('Choose an ngspice connection'), lines.slice(0, 300));
  // States audit of 2026-10-24 (branch record SIF-139): the line named the Connection window with no button to it, while the
  // header's pill shows a connection's name, the word "Connection" for screen readers only. It carries Connection... now, as
  // the lines of branch record SIF-108 do; the chip's mark says on hover what keeps the task from running, and the header's
  // facts say "no PDK" for the label the task leaves at its default ("unspecified · ..." before).
  const LINE = `${STATUS}.querySelector('.line-act.connection-problem')`;
  const problem = await evaluate(`(() => { const l = ${LINE}, b = l?.querySelector('button'), p = l?.querySelector('p.warn');
    return l && { text: p?.textContent ?? '', buttons: [...l.querySelectorAll('button')].map(x => x.textContent.trim()), title: b?.title ?? '',
      beside: !!b && !!p && b.getBoundingClientRect().top < p.getBoundingClientRect().bottom && b.getBoundingClientRect().left > p.getBoundingClientRect().left }; })()`);
  check('...that line carries Connection... beside its words, the tooltip saying what it opens and that opening checks nothing (SIF-139)',
    problem?.text === LOADED.circuit.connection_problem && JSON.stringify(problem.buttons) === '["Connection..."]' && problem.title.startsWith('Connection: Opens the Connection window')
    && problem.title.endsWith('Opening it checks nothing.') && problem.beside, JSON.stringify(problem));
  const marked = await evaluate(`[${PANEL}.querySelector('.tabs .task-row .task-list-mark')?.title ?? null, document.querySelector('header .tb-details .tb-cell .tb-v')?.textContent ?? null]`);
  check('the tab line\'s mark gives the reason on hover, and the header\'s facts read "opamp · no PDK" (SIF-139)',
    JSON.stringify(marked) === JSON.stringify(['needs an ngspice connection', 'opamp · no PDK']), JSON.stringify(marked));
  const rev = await evaluate(`${PANEL}.querySelector('.tabs .task-head .task-rev')?.textContent.trim() ?? ''`);
  check('the tab line gives its revision beside its name', rev === 'rev. 1', rev);
  const shown = await showCircuit(page);
  const column = await evaluate(`${CIRCUIT_PANEL}.textContent`);
  // "1 result:", counted in the right number (branch record SIF-62: it read "1 results:").
  check('"Show circuit" brings the circuit column with the ngspice task block: its revision and its results', shown
    && column.includes('ngspice netlist task') && column.includes('revision 1') && column.includes('1 result: vout_v'), column.slice(0, 300));
  check('no Delete task button on the page (the editors\' card, the circuit column)', !(await evaluate(`[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Delete task')`)));
  await tw.open();
  check('the Tasks window offers deletion beside the current ngspice task name', await tw.window.evaluate(`document.querySelector('.task-window-actions code')?.textContent === 'ngspice:fixture_ota'
    && document.querySelector('.task-window-actions button')?.textContent.trim() === 'Delete task'`));
  await tw.close();
  check('the tab line offers "ngspice netlist..." back to the deck of the task it names (the launcher\'s text named it until record 7.362)',
    (await deckButton()) === 'ngspice netlist...' && (await tw.current()) === 'ngspice:fixture_ota', await deckButton());
  await evaluate(`${TOOLS}.querySelector('button.ngspice-button').click()`, true);
  await sleep(600);
  const windows = (await browser.pages()).filter(t => t.title === NGSPICE_WINDOW).length;
  check('pressed, it brings that window back: still one ngspice window, holding the deck', windows === 1
    && (await win.evaluate(`${W}.querySelector('textarea.ngspice-text').value`)) === DECK, `${windows} window(s)`);
  check('no red Blocked box for the followed task', !(await evaluate(`!!${PANEL}.querySelector('.blocker') || !!${CIRCUIT_PANEL}.querySelector('.blocker')`)));
  await shotTask('ngspice-3-task.png');
  await shot('ngspice-3-column.png');
  // The line's Connection... opens the Connection window from the page, which holds the click, and sends nothing (SIF-139).
  const before = { sent: sent.length, refused: refused.length };
  await evaluate(`${LINE}?.querySelector('button')?.click()`, true);
  const linkWindow = await browser.window(CONNECTION_WINDOW, { ms: 10000, except: page.target.id }).catch(() => null);
  const link = linkWindow && await browser.attach(linkWindow, { errors: consoleErrors, prefix: 'Connection window: ' });
  const opened = link && await link.until(`!!document.querySelector('.connection-window h2')`, 50)
    && await link.evaluate(`({ heading: document.querySelector('.connection-window h2').textContent, opener: window.opener?.document.title ?? null })`);
  const pageTitle = await evaluate(`document.title`);
  check('...its press opens the Connection window, from the page (the window that holds the click), and sends nothing (SIF-139)',
    opened?.heading === 'Connection' && opened.opener === pageTitle && sent.length === before.sent && refused.length === before.refused, JSON.stringify([opened, pageTitle]));
  if (link) { link.close(); await send('Target.closeTarget', { targetId: linkWindow.id }).catch(() => undefined); }
  check('the window now offers the next revision', (await win.evaluate(`[...${W}.querySelectorAll('button')].map(b => b.textContent.trim())`)).includes('Save (next revision)'));

  // ---- the launchers follow the connection in use, and so do the ngspice tasks in the Task list (records 7.76, 7.77, 7.362) -----------
  connections = [{ id: 'fixture-lab', kind: 'virtuoso_ssh', family: 'virtuoso' }, { id: 'fixture-sim', kind: 'ngspice_local', family: 'ngspice' }];
  // What the page offers: the Tasks window's New task buttons (record 7.362), the tab line's way back to an ngspice task's deck,
  // and the task the tab line names, with its mark.
  const launchers = async () => {
    const offered = await (await tw.open()).evaluate(`(() => { const r = ${NEW}; return { virtuoso: !!r?.querySelector('button.virtuoso-button'), ngspice: !!r?.querySelector('button.ngspice-button') }; })()`);
    return { ...offered, ...(await evaluate(`(() => { const p = ${PANEL}; return { deck: !!p.querySelector('.tabs .task-tools button.ngspice-button'),
      task: ((p.querySelector('.task-row .task-list-key')?.textContent ?? '') + ' ' + (p.querySelector('.task-row .task-list-mark')?.textContent ?? '')).trim() }; })()`)) };
  };
  // The task window lists EVERY task (record 7.227): an ngspice task without its connection carries the mark beside its name.
  const windowTasks = async () => (await tw.rows()).map(r => `${r.key} ${r.mark}`);
  // The page reloaded with the connection `id` in use and, when one is given, another task followed (its rows emptied; the MOCK
  // task's load passes through to the backend, read-only).
  const withConnection = async (id, task = null) => {
    const stored = JSON.parse(await evaluate(`localStorage.getItem('gator-workbench-config-v1')`));
    await page.seed({ config: { ...stored, ...(task ? { circuit: { ...stored.circuit, source: 'registered_task', task_id: task }, parameters: [], measurements: [], targets: [] } : {}),
      run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0, connection_profile_id: id } } });
    const asked = profilesSeen;
    await send('Page.navigate', { url: APP });
    await until(ROWED, 150);
    await browser.window(TASKS_WINDOW, { present: false, ms: 3000, except: page.target.id }).catch(() => null);   // the old page's, gone with it
    // The connection's kind comes with the profile list, read once the page knows its connection: until then both ways show.
    if (id) for (let i = 0; i < 50 && profilesSeen === asked; i++) await sleep(100);
    // Settled once a launcher shows (the connection's kind is known), the task list is filled and two readings 0.3 s apart
    // agree. It slept 2 s until 2026-09-30.
    for (let i = 0, last = ''; i < 40; i++) {
      const now = await launchers(), text = JSON.stringify(now);
      if (text === last && (now.virtuoso || now.ngspice) && now.task) break;
      last = text; await sleep(300);
    }
    return launchers();
  };
  const ngspiceListed = rows => rows.filter(t => t.startsWith('ngspice:'));
  const onVirtuoso = await withConnection('fixture-lab');
  check('with a Virtuoso connection in use the Tasks window offers "From a Virtuoso cell..." only', onVirtuoso.virtuoso && !onVirtuoso.ngspice, JSON.stringify(onVirtuoso));
  check('and the tab line drops "ngspice netlist..." of the ngspice task it follows', !onVirtuoso.deck, JSON.stringify(onVirtuoso));
  check('the ngspice task the page follows is named on the tab line, marked "choose its connection"', onVirtuoso.task.startsWith('ngspice:fixture_ota') && onVirtuoso.task.includes('choose its connection'), onVirtuoso.task);
  let listed = await windowTasks();
  check('the task window lists it with that mark (the example shows only while ngspice is connected)', ngspiceListed(listed).length === 1 && ngspiceListed(listed)[0].includes('choose its connection'), JSON.stringify(listed));
  const onVirtuosoMock = await withConnection('fixture-lab', 'synthetic:gpdk045_ota5');
  listed = await windowTasks();
  check('with the MOCK task followed and a Virtuoso connection in use, the window still lists the ngspice task, marked "choose its connection" (the window shows every task, record 7.227)',
    onVirtuosoMock.task.startsWith('synthetic:gpdk045_ota5') && ngspiceListed(listed).length === 1 && ngspiceListed(listed)[0].includes('choose its connection'), JSON.stringify([onVirtuosoMock.task, listed]));
  const onNgspice = await withConnection('fixture-sim');
  check('with an ngspice connection in use the Tasks window offers "From an ngspice netlist..." only', !onNgspice.virtuoso && onNgspice.ngspice, JSON.stringify(onNgspice));
  listed = await windowTasks();
  check('and the ngspice task is listed there too (the fixture task stays "choose its connection": the backend, not the page, judges a task available)', ngspiceListed(listed).length === 1, JSON.stringify(listed));
  await tw.window.shot(path.join(out, 'ngspice-4-launcher-ngspice.png'), `document.querySelector('.task-window')`, { maxHeight: 360 });
  const onNone = await withConnection(null);
  check('with no connection chosen it offers both', onNone.virtuoso && onNone.ngspice, JSON.stringify(onNone));
  listed = await windowTasks();
  check('and the window lists the ngspice task (the same rule as the button)', ngspiceListed(listed).length === 1, JSON.stringify(listed));
  // The tab line's way back to an ngspice task's deck follows the same rule (record 7.362): the ngspice task followed again.
  const onNgspiceTask = await withConnection('fixture-sim', 'ngspice:fixture_ota');
  check('with an ngspice connection in use and the ngspice task followed, the tab line offers "ngspice netlist..." again',
    onNgspiceTask.deck && onNgspiceTask.task.startsWith('ngspice:fixture_ota') && onNgspiceTask.ngspice && !onNgspiceTask.virtuoso, JSON.stringify(onNgspiceTask));

  check('the page asked nothing else of the backend (every request besides reads is refused here)', refused.length === 0, refused.join(' | '));
  check('no console errors in the page', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
