// Browser check of the task window (record 7.227): the Project column's registered task is plain text with ONE button
// "Tasks..." beside it, which replaced the drop-down list of tasks - as "Runs..." replaced the list of runs - and opens a
// window of its own (frontend/src/panels/TaskList.tsx) listing every registered task: what it is, which cell it runs
// in, its revision, when it was saved, its baseline, how many sizes and results it has, and its newest run. A DOUBLE
// CLICK on a row makes the page follow that task; "Details" shows the rest, the task's rows included.
// Hermetic (same approach as run_list_check.mjs): the task list, the run list, the chosen task's rows and its circuit load
// are answered HERE by FIXTURE data; other GET requests pass through and every other writing request is refused. Safe
// next to the live backend; the browser profile is new and temporary.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/task_list_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED, outDir, reportRefused, runChecks, sleep, starterConfig, taskWindow, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('tasklist');

const two = n => String(n).padStart(2, '0');
const stamp = utc => { const d = new Date(utc); return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`; };

// ---- the tasks (FIXTURE): a saved task with everything, one without a baseline that is blocked, an ngspice task, the MOCK stand-in ----
const base = (key, kind, more) => ({ task_key: key, kind, circuit_class: 'opamp', pdk_id: 'gpdk045', available: true, blocker: null, description: `FIXTURE ${key}`,
  starter_project: { name: key.split(':')[1].replace(/_/g, '-'), task_name: key.split(':')[1] }, training_capabilities: { corners: false, policies: ['off'] }, ...more });
const OTA = base('real:fixture_ota', 'real', { generated: true, library: 'FIXTURE_LIB', cell: 'fixture_ota', testbench: 'tb_fixture_ota', revision: 3, measurement: 'maestro',
  original: { library: 'FIXTURE_LIB', cell: 'fixture_ota', testbench: 'tb_fixture_ota', netlist_sha256: 'f211eca4f62f6f6afcf21890e0a12bd3f14c8a2a6ba556013f766bac351b843c' }, verified: true,
  saved_utc: '2026-10-05T13:57:46+00:00', created_utc: '2026-10-05T13:00:00+00:00', baseline_recorded_utc: '2026-10-05T21:57:39+00:00',
  status: 'baseline recorded: one real simulation of the recorded sizes', variables: 6, results: 6, description: 'Profile generated from FIXTURE_LIB/fixture_ota (Virtuoso + Spectre). ' });
const LDO = base('real:fixture_ldo', 'real', { generated: true, circuit_class: 'ldo', library: 'FIXTURE_LIB', cell: 'fixture_ldo', testbench: 'tb_fixture_ldo', revision: 1, measurement: 'maestro',
  original: { library: 'FIXTURE_LIB', cell: 'fixture_ldo', testbench: 'tb_fixture_ldo', netlist_sha256: '0' }, verified: false, available: false, blocker: 'FIXTURE: the connection file names no library for it',
  saved_utc: '2026-10-06T00:28:42+00:00', created_utc: '2026-10-06T00:28:43+00:00', baseline_recorded_utc: null, status: 'unverified: no real baseline simulation has been recorded for this profile yet',
  variables: 12, results: 10 });
const NG = base('ngspice:fixture_div', 'ngspice', { circuit_class: 'unspecified', pdk_id: 'unspecified', available: false, blocker: 'FIXTURE: needs an ngspice connection', revision: 2,
  title: 'a resistive divider', simulator: 'ngspice', description: 'ngspice netlist (2 elements, 1 results), revision 2. Runs on an ngspice connection; no license.' });
const MOCK = base('synthetic:gpdk045_ota5', 'mock', { description: 'FIXTURE MOCK: the synthetic stand-in' });
const TASKS = [OTA, LDO, NG, MOCK];
// ---- the runs (FIXTURE): two of the OTA (a Baseline simulation, then a run that found a feasible design), none of the others ----
const ROOT = '/fixture/outputs/fixture_exp__0001/runs';
const run = (id, folder, created, facts = {}) => ({ run_dir: `${ROOT}/${folder}/scratch__seed0__${id}`, run_id: id, task_id: `${folder}:0000`, task_key: 'real:fixture_ota', task_name: folder,
  task_definition_hash: 'fixture', mode: 'scratch', mock: false, seed: 0, experiment: 'fixture_exp__0001', created_utc: created, started_utc: created, ended_utc: created.replace(':00+', ':30+'),
  last_seen_utc: null, active_seconds: 30, paused_seconds: 0, state: 'completed', stop_reason: 'budget_exhausted', error: null, evaluations: 8, max_evaluations: 8,
  first_feasible_eval_count: null, resumability: 'full_state', segments: [], ...facts });
const NEWEST = run('a2a2a2a2a2a2', 'fixture_ota', '2026-10-05T18:00:00+00:00', { first_feasible_eval_count: 5 });
const BASELINE = run('a1a1a1a1a1a1', 'fixture_ota.baseline', '2026-10-05T17:00:00+00:00', { evaluations: 65, max_evaluations: 65 });
const older = r => Object.fromEntries(Object.entries(r).filter(([k]) => k !== 'task_key'));     // a row as a server before record 7.212 lists it
// ---- the OTA's rows, as the starter route answers them ----
const STARTER = { project: { name: 'fixture-ota', task_name: 'fixture_ota', notes: 'FIXTURE 5-transistor OTA' }, revision: 3,
  circuit: { source: 'registered_task', task_id: 'real:fixture_ota', circuit_class: 'opamp', pdk_id: 'gpdk045' },
  parameters: [{ variable_id: 'w_pair', instance_path: 'DUT/M1', parameter_name: 'w', unit: 'um', optimized: true, value_type: 'continuous', lower: 4, upper: 40, step: 0.02, scale: 'linear', ratio: 1, notes: '' },
    { variable_id: 'w_pair_f1', instance_path: 'DUT/M2', parameter_name: 'w', unit: 'um', optimized: true, value_type: 'continuous', scale: 'linear', binding_group: 'w_pair', ratio: 1, notes: 'follows w_pair' }],
  measurements: [{ measurement_id: 'm_gain_db', analysis: 'stb', result_source: 'ade_output', source_name: 'gain_db', signal: 'value(dB20(...) 1000)', unit: 'dB', notes: '' }],
  targets: [{ metric_id: 'gain_db', equation: 'm_gain_db', unit: 'dB', constraint: '>=', lower: 30, hard: true, direction_after_feasible: 'none', normalization_scale: 6, basis: 'FIXTURE' }] };
const LOADED = { loaded: true, training_capabilities: { corners: false, policies: ['off'] }, task_key: 'real:fixture_ota', mock: false, circuit: { circuit_class: 'opamp', pdk_id: 'gpdk045', generated_profile: true },
  simulator: 'spectre', content_sha256: 'fixture', provided_metrics: ['gain_db'], hierarchy: { DUT: { M1: {}, M2: {} } }, summary: { device_count: 2, devices: [], unknown_devices: [] }, complete: true,
  diagnostics: [], analysis_context: null, notes: [], evaluation_backend: 'FIXTURE', max_concurrency: 1, native_draft: false, generated_profile: true, baseline_recorded: '2026-10-05T21:57:39+00:00' };

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);     // the page opens on the MOCK stand-in, as "Load task" merges it
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = [], seen = [], dialogs = [];
  let runsMode = 'normal';
  const folderData = { version: 1, folders: {}, assignments: {} };
  let folderSerial = 0, refuseMove = false, refuseFolders = false, lastMove = null;
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const answer = params => {
    const { requestId, request } = params, url = new URL(request.url), name = url.pathname;
    if (name.startsWith('/api/task-folders')) {
      const body = JSON.parse(request.postData ?? '{}');
      if (request.method === 'GET' && refuseFolders) return fulfil(requestId, 503, { detail: { message: 'FIXTURE folder read failed' } });
      if (request.method === 'POST') {
        const id = String(++folderSerial).padStart(32, '0'); folderData.folders[id] = body.name.trim();
        return fulfil(requestId, 200, { ...folderData, created_id: id });
      }
      if (request.method === 'PUT') {
        lastMove = body;
        if (refuseMove) return fulfil(requestId, 409, { detail: { message: 'FIXTURE move refused' } });
        body.task_keys.forEach(key => { if (body.folder_id) folderData.assignments[key] = body.folder_id; else delete folderData.assignments[key]; });
      }
      if (request.method === 'PATCH') folderData.folders[name.split('/').at(-1)] = body.name;
      if (request.method === 'DELETE') {
        const id = name.split('/').at(-1); delete folderData.folders[id];
        Object.keys(folderData.assignments).forEach(key => { if (folderData.assignments[key] === id) delete folderData.assignments[key]; });
      }
      return fulfil(requestId, 200, folderData);
    }
    if (['/api/tasks', '/api/runs', '/api/tasks/starter'].includes(name)) seen.push(name === '/api/tasks/starter' ? `starter ${url.searchParams.get('task_key')}` : name);
    if (name === '/api/tasks') return fulfil(requestId, 200, { tasks: TASKS, real_interface_contract: {} });
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: runsMode === 'older' ? [NEWEST, BASELINE].map(older) : [NEWEST, BASELINE] });
    if (name === '/api/tasks/starter' && url.searchParams.get('task_key') === 'real:fixture_ota') return fulfil(requestId, 200, STARTER);
    if (name === '/api/circuit/load' && JSON.parse(request.postData ?? '{}').circuit?.task_id === 'real:fixture_ota') return fulfil(requestId, 200, LOADED);
    if (name === '/api/config/validate') return fulfil(requestId, 200, validConfiguration({ facts: { circuit_checked: true } }));
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [] });
    if (name.startsWith('/api/runs')) return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${name} is not expected in this check` } });
    return page.readOrRefuse(params, refused);
  };
  const count = what => seen.filter(s => s === what).length;
  const until = (expression, tries = 100) => page.until(expression, tries);
  const tw = taskWindow(page, browser);
  const { PANEL, ROW } = tw;
  const EDITORS = `document.querySelector('.editors')`;
  const WINDOW = `document.querySelector('.task-window')`;
  const TABLE = `${WINDOW}.querySelector('table.task-table')`;
  const ROWS = `[...${TABLE}.querySelectorAll(':scope > tbody > tr[data-task-key]')]`;
  const cell = (key, n) => tw.window.evaluate(`${ROWS}.find(tr => tr.dataset.taskKey === ${JSON.stringify(key)})?.children[${n + 1}]?.textContent.trim() ?? null`);
  const press = (text, scope = WINDOW) => tw.window.evaluate(`[...${scope}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`, true);
  const shot = (name, what) => page.shot(path.join(out, name), what);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: { schema_version: 'gator-workbench-config-v1', ...CONFIG, run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0 }, output: { experiment_name: 'fixture' }, research: {} }, run: null, when: 'once' });
  await page.trackSaves();                                  // the page saves 800 ms after the last change: read it with saved()
  await send('Page.navigate', { url: APP });
  check('the page opens with the Task row', await until(`!!(${PANEL}) && !!${ROW}`, 150));
  for (let i = 0; i < 100 && (count('/api/tasks') < 1 || count('/api/runs') < 1); i++) await sleep(50);
  await sleep(600);
  const opened = { tasks: count('/api/tasks'), runs: count('/api/runs') };

  // ---- 1. the Task row: the name is one button, no drop-down -------------------------------------------------------------
  const row = await evaluate(`(() => { const r = ${ROW}; return { caption: r.querySelector('.task-caption')?.textContent, key: r.querySelector('.task-list-key')?.textContent,
    mark: r.querySelector('.task-list-mark')?.textContent.trim() ?? null, button: r.querySelector('button.task-list-button')?.textContent, select: !!r.querySelector('select'),
    nameIsButton: !!r.querySelector('button.task-list-button .task-list-key'), buttons: r.querySelectorAll('button').length }; })()`);
  check('the whole task name is the only task-row button', row.caption === 'Task' && row.key === 'synthetic:gpdk045_ota5' && row.mark === '[MOCK]'
    && row.nameIsButton && row.buttons === 1 && !row.button.includes('Tasks...'), JSON.stringify(row));
  check('there is no drop-down list of tasks in the column any more', !row.select);
  check('the button has a tooltip saying what the window is', (await evaluate(`${ROW}.querySelector('button.task-list-button').title`)).includes('every registered task'));
  await shot('task-list-1-row.png', ROW);

  // ---- 2. the window opens and reads the task list once; the run list is the page's own ---------------------------------------
  await tw.open();
  let far = tw.window;
  check('pressing the button opens a window of its own, titled "GATOR - tasks", headed Tasks', far.target.title === 'GATOR - tasks' && (await far.evaluate(`${WINDOW}.querySelector('h2')?.textContent`)) === 'Tasks');
  check('opening it reads the task list once, and does not read the run list again (the page\'s own list is shown)', count('/api/tasks') === opened.tasks + 1 && count('/api/runs') === opened.runs, JSON.stringify(seen));
  check('the button is marked open while the window is', await evaluate(`${ROW}.querySelector('button.task-list-button').classList.contains('open')`));
  const heads = await far.evaluate(`[...${TABLE}.querySelectorAll('thead th')].map(th => th.textContent.replace(/[ ▲▼]+$/, '').trim())`);
  check('the columns: task, class, cell, revision, saved, baseline, sizes / results, newest run, runs', JSON.stringify(heads) === JSON.stringify(['', 'Task', 'Class', 'Cell', 'Rev', 'Saved', 'Baseline', 'Sizes / results', 'Newest run', 'Runs', '']), JSON.stringify(heads));
  check('every registered task is listed, sorted by name', JSON.stringify(await tw.keys()) === JSON.stringify(['real:fixture_ldo', 'real:fixture_ota', 'ngspice:fixture_div', 'synthetic:gpdk045_ota5']), JSON.stringify(await tw.keys()));
  check('the task the page follows is marked', (await far.evaluate(`${ROWS}.filter(tr => tr.classList.contains('current') && tr.getAttribute('aria-current') === 'true').map(tr => tr.dataset.taskKey)`)).join() === 'synthetic:gpdk045_ota5');
  const hint = await far.evaluate(`${WINDOW}.textContent`);
  check('the window says what a double click and Details do, and that nothing updates by itself', hint.includes('Double click a task to make the workbench follow it') && hint.includes('Details shows the rest')
    && hint.includes('Nothing here updates by itself') && /read at \d\d:\d\d:\d\d/.test(hint), hint.slice(0, 200));
  await far.evaluate(`${WINDOW}.querySelector('details.more summary').click()`);
  check('"What the columns mean" explains each column', await far.until(`${WINDOW}.querySelector('details.more').open && ${WINDOW}.querySelector('details.more').textContent.includes('Sizes / results: How many sizes')`, 20));
  await far.evaluate(`${WINDOW}.querySelector('details.more summary').click()`);

  // ---- 3. the facts of each row ----------------------------------------------------------------------------------------------
  check('a saved task: clean name, its cell and testbench, revision, saved time, baseline time, sizes / results',
    (await cell(OTA.task_key, 0)) === 'fixture_ota' && (await cell(OTA.task_key, 1)) === 'opamp' && (await cell(OTA.task_key, 2)) === 'FIXTURE_LIB/fixture_otatb tb_fixture_ota'
    && (await cell(OTA.task_key, 3)) === '3' && (await cell(OTA.task_key, 4)) === stamp(OTA.saved_utc) && (await cell(OTA.task_key, 5)) === stamp(OTA.baseline_recorded_utc) && (await cell(OTA.task_key, 6)) === '6 / 6',
    JSON.stringify(await Promise.all([0, 1, 2, 3, 4, 5, 6].map(n => cell(OTA.task_key, n)))));
  check('its newest run: started, state, evaluations, first feasible; and how many runs it has (the Baseline simulation counts)',
    (await cell(OTA.task_key, 7)) === `${stamp(NEWEST.created_utc)} · completed · 8 evaluations · first feasible at 5` && (await cell(OTA.task_key, 8)) === '2',
    `${await cell(OTA.task_key, 7)} | ${await cell(OTA.task_key, 8)}`);
  check('a blocked task without a baseline: the mark [blocked], baseline none, no run', (await cell(LDO.task_key, 0)) === 'fixture_ldo[blocked]' && (await cell(LDO.task_key, 5)) === 'none'
    && (await cell(LDO.task_key, 7)) === 'none' && (await cell(LDO.task_key, 8)) === '0', JSON.stringify(await Promise.all([0, 5, 7, 8].map(n => cell(LDO.task_key, n)))));
  check('an ngspice task without its connection: the mark "choose its connection", no cell, no baseline column value', (await cell(NG.task_key, 0)) === 'ngspice:fixture_div[ngspice: choose its connection]'
    && (await cell(NG.task_key, 2)) === 'ngspice netlist' && (await cell(NG.task_key, 5)) === '-' && (await cell(NG.task_key, 3)) === '2', JSON.stringify(await Promise.all([0, 2, 3, 5].map(n => cell(NG.task_key, n)))));
  check('the MOCK task: a MOCK badge', (await cell(MOCK.task_key, 0)) === 'synthetic:gpdk045_ota5MOCK' && await far.evaluate(`!!${ROWS}.find(tr => tr.dataset.taskKey === 'synthetic:gpdk045_ota5').querySelector('.mock-tag')`));
  await far.shot(path.join(out, 'task-list-2-window.png'));

  // ---- 4. a double click makes the page follow the task --------------------------------------------------------------------------
  const starters = count('starter real:fixture_ota');
  check('a double click on a row makes the page follow that task: the Task row names it, its rows are read once', await tw.choose('real:fixture_ota') && count('starter real:fixture_ota') === starters + 1
    && (await evaluate(`${ROW}.querySelector('.task-list-key').textContent`)) === 'fixture_ota'
    && (await evaluate(`${ROW}.querySelector('.task-list-mark')`)) === null, `${await tw.current()} (${count('starter real:fixture_ota') - starters} read(s))`);
  await page.saved();
  check('the configuration follows: task, labels, rows, run label', (await page.stored()).circuit.task_id === 'real:fixture_ota' && (await page.stored()).project.task_name === 'fixture_ota'
    && (await page.stored()).parameters.length === 2 && (await page.stored()).targets[0].metric_id === 'gain_db', JSON.stringify((await page.stored()).circuit));
  check('the marked row moves to it; the window stays open', (await far.evaluate(`${ROWS}.filter(tr => tr.classList.contains('current')).map(tr => tr.dataset.taskKey)`)).join() === 'real:fixture_ota' && !far.closed);
  check('the Project column says the rows are this task\'s', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`, 50));
  check('no question was asked: the rows were untouched', dialogs.length === 0, JSON.stringify(dialogs));
  check('one Undo takes the choice back, and the Task row says so', (await evaluate(`[...${EDITORS}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Undo').click()`), await until(`${ROW}.querySelector('.task-list-key')?.textContent === 'synthetic:gpdk045_ota5'`, 50)));
  check('... and the window marks the MOCK task again', await far.until(`${ROWS}.filter(tr => tr.classList.contains('current')).map(tr => tr.dataset.taskKey).join() === 'synthetic:gpdk045_ota5'`, 30));
  await tw.choose('real:fixture_ota');

  // ---- 5. Details: the facts and the task's rows -----------------------------------------------------------------------------------
  await far.evaluate(`[...${ROWS}.find(tr => tr.dataset.taskKey === 'real:fixture_ota').querySelectorAll('button')].find(b => b.textContent.trim() === 'Details').click()`, true);
  const DETAILS = `${WINDOW}.querySelector('.task-details')`;
  check('Details opens under the row and reads the task\'s rows once (the third read: two choices went before)', await far.until(`!!(${DETAILS}) && !!${DETAILS}.querySelector('table.task-rows-table')`, 50) && count('starter real:fixture_ota') === starters + 3, `${count('starter real:fixture_ota') - starters} read(s)`);
  const details = await far.evaluate(`${DETAILS}.textContent`);
  check('the facts: registered task, cell with testbench, saved from, revision, baseline, state, sizes, results, runs', ['Registered taskfixture_ota', 'Runs inFIXTURE_LIB/fixture_ota with testbench tb_fixture_ota',
    'Revision3', `Baseline recorded${stamp(OTA.baseline_recorded_utc)}`, 'Statebaseline recorded', 'Sizes varied6', 'Results measured6', 'Runs2; newest'].every(t => details.includes(t)) && !(await far.evaluate(`[...${DETAILS}.querySelectorAll('.run-facts tr')].some(tr => tr.children[0].textContent === 'Kind')`)), details.slice(0, 300));
  // rows holding cells (td): the heading row holds th only - a quirks-mode pop-up counts 'tbody tr' oddly (the heading row too)
  const tables = await far.evaluate(`[...${DETAILS}.querySelectorAll('table.task-rows-table')].map(t => [...t.querySelectorAll('tr')].filter(tr => tr.querySelector('td')).length)`);
  check('the rows: 2 parameters, 1 probe, 1 spec, with the spec\'s limit', JSON.stringify(tables) === JSON.stringify([2, 1, 1]) && details.includes('>= 30 dB') && details.includes('w_pair_f1') && details.includes('m_gain_db'), `${JSON.stringify(tables)} ${details.slice(-200)}`);
  await far.shot(path.join(out, 'task-list-3-details.png'));
  await press('Hide details');
  check('Hide details closes them', await far.until(`!(${DETAILS})`, 20));

  // ---- 6. filter and sort ------------------------------------------------------------------------------------------------------
  await far.evaluate(`(() => { const i = ${WINDOW}.querySelector('input.task-filter'); i.focus(); i.select(); })()`);
  await far.send('Input.insertText', { text: 'ldo' });
  check('the filter narrows the list by any word of a row', await far.until(`${ROWS}.length === 1`, 30) && (await tw.keys()).join() === 'real:fixture_ldo', JSON.stringify(await tw.keys()));
  await far.evaluate(`(() => { const i = ${WINDOW}.querySelector('input.task-filter'); i.focus(); i.select(); })()`);
  await far.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 }); await far.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 });
  await far.until(`${ROWS}.length === 4`, 30);
  await far.evaluate(`[...${TABLE}.querySelectorAll('thead th')].find(th => th.textContent.startsWith('Rev')).click()`);
  check('a press on a column title sorts by it (rows without a value stay last)', await far.until(`${ROWS}.map(tr => tr.dataset.taskKey).join() === 'real:fixture_ldo,ngspice:fixture_div,real:fixture_ota,synthetic:gpdk045_ota5'`, 30), (await tw.keys()).join());
  await far.evaluate(`[...${TABLE}.querySelectorAll('thead th')].find(th => th.textContent.startsWith('Rev')).click()`);
  check('... and again the other way', await far.until(`${ROWS}.map(tr => tr.dataset.taskKey).join() === 'real:fixture_ota,ngspice:fixture_div,real:fixture_ldo,synthetic:gpdk045_ota5'`, 30), (await tw.keys()).join());

  // ---- 7. Refresh list reads both lists; an older server is said --------------------------------------------------------------------
  let before = { tasks: count('/api/tasks'), runs: count('/api/runs') };
  await press('Refresh list');
  check('"Refresh list" reads the task list and the run list again', await far.until(`${WINDOW}.textContent.includes('read at')`, 30) && (await (async () => { for (let i = 0; i < 40 && (count('/api/tasks') < before.tasks + 1 || count('/api/runs') < before.runs + 1); i++) await sleep(50);
    return count('/api/tasks') === before.tasks + 1 && count('/api/runs') === before.runs + 1; })()), JSON.stringify(seen.slice(-4)));
  runsMode = 'older';
  await press('Refresh list'); await sleep(800);
  check('a server older than the page (runs without their task) is said in plain words, and the run columns stay empty', await far.until(`${WINDOW}.textContent.includes('older than this page')`, 30)
    && (await cell(OTA.task_key, 7)) === '-' && (await cell(OTA.task_key, 8)) === '-', `${await cell(OTA.task_key, 7)} | ${await cell(OTA.task_key, 8)}`);
  runsMode = 'normal';
  await press('Refresh list'); await sleep(800);
  check('with the task in the rows again, the run columns are back', await far.until(`!${WINDOW}.textContent.includes('older than this page')`, 30) && (await cell(OTA.task_key, 8)) === '2');

  // ---- 8. nothing updates by itself --------------------------------------------------------------------------------------------
  before = { tasks: count('/api/tasks'), runs: count('/api/runs') };
  await sleep(2500);
  check('nothing in the window updates by itself', count('/api/tasks') === before.tasks && count('/api/runs') === before.runs, JSON.stringify(seen));

  // ---- 9. folders: shared persistence, bulk moves, failure recovery and keeping task identity -------------------------------
  await far.send('Page.enable');
  const replies = [];
  const attachFolderDialogs = () => far.on('Page.javascriptDialogOpening', p => far.send('Page.handleJavaScriptDialog', replies.shift() ?? { accept: false }));
  attachFolderDialogs();
  const nav = id => far.evaluate(`${WINDOW}.querySelector('[data-folder-id="${id}"]').click()`);
  const selectTask = key => far.evaluate(`${ROWS}.find(tr => tr.dataset.taskKey === ${JSON.stringify(key)}).querySelector('input[type="checkbox"]').click()`);
  const moveTo = id => far.evaluate(`(() => { const s = ${WINDOW}.querySelector('select[aria-label="Move selected tasks to folder"]'); s.value = ${JSON.stringify(id)}; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const settled = () => far.until(`!${WINDOW}.querySelector('.task-move-bar [role="status"]')`, 50);
  check('folders open on All tasks, with every task initially unfiled', await far.evaluate(`${WINDOW}.querySelector('[data-folder-id="all"]').getAttribute('aria-current') === 'page' && ${WINDOW}.querySelector('[data-folder-id="unfiled"]').textContent === 'Unfiled4'`));
  replies.push({ accept: false }); await press('New folder'); await sleep(100);
  check('cancelling a folder prompt writes nothing', Object.keys(folderData.folders).length === 0);
  replies.push({ accept: true, promptText: 'Graph Transformer' }); await press('New folder'); await settled();
  const gt = Object.keys(folderData.folders)[0];
  check('a new folder opens empty', !!gt && (await tw.keys()).length === 0 && await far.evaluate(`!!${WINDOW}.querySelector('.task-folder-empty')`));
  await nav('all'); await selectTask(OTA.task_key); await selectTask(LDO.task_key);
  check('checkboxes select tasks without changing the followed task', (await tw.current()) === OTA.task_key && await far.evaluate(`${WINDOW}.querySelector('.task-move-bar').textContent.includes('2 selected')`));
  refuseMove = true; await moveTo(gt); await settled();
  check('a failed move is visible, leaves the assignments intact and keeps selection for retry', Object.keys(folderData.assignments).length === 0
    && await far.evaluate(`${WINDOW}.querySelector('[role="alert"]').textContent.includes('move refused') && ${ROWS}.filter(tr => tr.querySelector('input').checked).length === 2`));
  refuseMove = false; await moveTo(gt); await settled(); await nav(gt);
  check('a bulk move uses canonical task IDs and filters the folder', JSON.stringify(lastMove.task_keys) === JSON.stringify([OTA.task_key, LDO.task_key])
    && (await tw.keys()).length === 2 && (await page.stored()).circuit.task_id === OTA.task_key);
  check('moving tasks preserves run counts and row selection', (await cell(OTA.task_key, 8)) === '2' && await tw.choose(OTA.task_key));
  await far.shot(path.join(out, 'task-list-4-folders.png'));
  replies.push({ accept: true, promptText: 'GT models' }); await press('Rename'); await settled();
  check('renaming keeps membership and the active folder', folderData.folders[gt] === 'GT models' && Object.values(folderData.assignments).every(id => id === gt) && (await tw.keys()).length === 2);
  await nav('unfiled');
  check('Unfiled holds only tasks without a folder', JSON.stringify((await tw.keys()).sort()) === JSON.stringify([NG.task_key, MOCK.task_key].sort()));
  await nav(gt); await selectTask(LDO.task_key); await moveTo('unfiled'); await settled();
  check('moving to Unfiled removes just that assignment', !folderData.assignments[LDO.task_key] && folderData.assignments[OTA.task_key] === gt && (await tw.keys()).join() === OTA.task_key);
  await page.saved(); await tw.close(); await send('Page.navigate', { url: APP });
  await until(`!!(${PANEL}) && !!${ROW}`, 150); far = await tw.open(); await far.send('Page.enable'); attachFolderDialogs(); await settled();
  await nav(gt);
  check('folders and membership survive a full page reload', (await tw.keys()).join() === OTA.task_key && await far.evaluate(`${WINDOW}.querySelector('[data-folder-id="${gt}"]').textContent === 'GT models1'`));
  replies.push({ accept: true }); await press('Delete folder'); await settled(); await nav('unfiled');
  check('deleting the folder keeps all tasks and puts its members in Unfiled', (await tw.keys()).length === 4 && Object.keys(folderData.assignments).length === 0 && Object.keys(folderData.folders).length === 0);
  await far.evaluate(`${TABLE}.querySelector('thead input[type="checkbox"]').click()`);
  check('select all selects only the shown rows', await far.evaluate(`${ROWS}.every(tr => tr.querySelector('input').checked)`));
  await far.evaluate(`${WINDOW}.querySelector('input.task-filter').focus()`); await far.send('Input.insertText', { text: 'ldo' });
  check('changing the filter clears selection so hidden tasks cannot be moved', await far.until(`${ROWS}.length === 1 && ${WINDOW}.querySelector('.task-move-bar select').disabled`, 30));
  refuseFolders = true; await press('Refresh list'); await settled();
  check('folder read failures leave tasks accessible but disable moves', await far.evaluate(`${WINDOW}.querySelector('[role="alert"]').textContent.includes('folder read failed') && ${ROWS}.length === 1 && ${TABLE}.querySelector('thead input').disabled`));
  refuseFolders = false; await press('Refresh list'); await settled();
  check('Refresh list recovers folder access', await far.evaluate(`!${WINDOW}.querySelector('[role="alert"]') && !${TABLE}.querySelector('thead input').disabled`));
  check('closing the window leaves the page on its task, the button no longer marked open', (await tw.close(), await until(`!${ROW}.querySelector('button.task-list-button').classList.contains('open')`, 30)) && (await tw.current()) === 'real:fixture_ota');
  reportRefused(refused, NEVER_ASKED);
  check('no console errors', consoleErrors.filter(e => !/404|418/.test(e)).length === 0, consoleErrors.join(' | ').slice(0, 300));
});
