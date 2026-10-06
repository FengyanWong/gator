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
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const answer = params => {
    const { requestId, request } = params, url = new URL(request.url), name = url.pathname;
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
  const ROWS = `[...${TABLE}.querySelectorAll(':scope > tbody > tr[title]')]`;
  const cell = (key, n) => tw.window.evaluate(`${ROWS}.find(tr => tr.title === ${JSON.stringify(key)})?.children[${n}]?.textContent.trim() ?? null`);
  const press = (text, scope = WINDOW) => tw.window.evaluate(`[...${scope}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`, true);
  const shot = (name, what) => page.shot(path.join(out, name), what);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: { schema_version: 'gator-workbench-config-v1', ...CONFIG, run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0 }, output: { experiment_name: 'fixture' }, research: {} }, run: null });
  await page.trackSaves();                                  // the page saves 800 ms after the last change: read it with saved()
  await send('Page.navigate', { url: APP });
  check('the page opens with the Task row', await until(`!!(${PANEL}) && !!${ROW}`, 150));
  for (let i = 0; i < 100 && (count('/api/tasks') < 1 || count('/api/runs') < 1); i++) await sleep(50);
  await sleep(600);
  const opened = { tasks: count('/api/tasks'), runs: count('/api/runs') };

  // ---- 1. the Task row: plain text + one button, no drop-down -------------------------------------------------------------
  const row = await evaluate(`(() => { const r = ${ROW}; return { caption: r.querySelector('.task-caption')?.textContent, key: r.querySelector('.task-list-key')?.textContent,
    mark: r.querySelector('.task-list-mark')?.textContent.trim() ?? null, button: r.querySelector('button.task-list-button')?.textContent, select: !!${PANEL}.querySelector('select'),
    order: [...r.children].map(e => e.className.split(' ')[0]) }; })()`);
  check('the task is named as plain text, the button reads only "Tasks...", to the RIGHT of the name', row.caption === 'Task' && row.key === 'synthetic:gpdk045_ota5' && row.mark === '[MOCK]' && row.button === 'Tasks...'
    && row.order.indexOf('task-list-current') < row.order.indexOf('task-list-button'), JSON.stringify(row));
  check('there is no drop-down list of tasks in the column any more', !row.select);
  check('the button has a tooltip saying what the window is', (await evaluate(`${ROW}.querySelector('button.task-list-button').title`)).includes('every registered task'));
  await shot('task-list-1-row.png', ROW);

  // ---- 2. the window opens and reads the task list once; the run list is the page's own ---------------------------------------
  await tw.open();
  const far = tw.window;
  check('pressing the button opens a window of its own, titled "GATOR - tasks", headed Tasks', far.target.title === 'GATOR - tasks' && (await far.evaluate(`${WINDOW}.querySelector('h2')?.textContent`)) === 'Tasks');
  check('opening it reads the task list once, and does not read the run list again (the page\'s own list is shown)', count('/api/tasks') === opened.tasks + 1 && count('/api/runs') === opened.runs, JSON.stringify(seen));
  check('the button is marked open while the window is', await evaluate(`${ROW}.querySelector('button.task-list-button').classList.contains('open')`));
  const heads = await far.evaluate(`[...${TABLE}.querySelectorAll('thead th')].map(th => th.textContent.replace(/[ ▲▼]+$/, '').trim())`);
  check('the columns: task, kind, class, cell, revision, saved, baseline, sizes / results, newest run, runs', JSON.stringify(heads) === JSON.stringify(['Task', 'Kind', 'Class', 'Cell', 'Rev', 'Saved', 'Baseline', 'Sizes / results', 'Newest run', 'Runs', '']), JSON.stringify(heads));
  check('every registered task is listed, sorted by name', JSON.stringify(await tw.keys()) === JSON.stringify(['ngspice:fixture_div', 'real:fixture_ldo', 'real:fixture_ota', 'synthetic:gpdk045_ota5']), JSON.stringify(await tw.keys()));
  check('the task the page follows is marked', (await far.evaluate(`${ROWS}.filter(tr => tr.classList.contains('current') && tr.getAttribute('aria-current') === 'true').map(tr => tr.title)`)).join() === 'synthetic:gpdk045_ota5');
  const hint = await far.evaluate(`${WINDOW}.textContent`);
  check('the window says what a double click and Details do, and that nothing updates by itself', hint.includes('Double click a task to make the workbench follow it') && hint.includes('Details shows the rest')
    && hint.includes('Nothing here updates by itself') && /read at \d\d:\d\d:\d\d/.test(hint), hint.slice(0, 200));
  await far.evaluate(`${WINDOW}.querySelector('details.more summary').click()`);
  check('"What the columns mean" explains each column', await far.until(`${WINDOW}.querySelector('details.more').open && ${WINDOW}.querySelector('details.more').textContent.includes('Sizes / results: How many sizes')`, 20));
  await far.evaluate(`${WINDOW}.querySelector('details.more summary').click()`);

  // ---- 3. the facts of each row ----------------------------------------------------------------------------------------------
  check('a saved task: kind real, its cell and testbench, revision, saved time, baseline time, sizes / results',
    (await cell(OTA.task_key, 1)) === 'real' && (await cell(OTA.task_key, 2)) === 'opamp' && (await cell(OTA.task_key, 3)) === 'FIXTURE_LIB/fixture_otatb tb_fixture_ota'
    && (await cell(OTA.task_key, 4)) === '3' && (await cell(OTA.task_key, 5)) === stamp(OTA.saved_utc) && (await cell(OTA.task_key, 6)) === stamp(OTA.baseline_recorded_utc) && (await cell(OTA.task_key, 7)) === '6 / 6',
    JSON.stringify(await Promise.all([1, 2, 3, 4, 5, 6, 7].map(n => cell(OTA.task_key, n)))));
  check('its newest run: started, state, evaluations, first feasible; and how many runs it has (the Baseline simulation counts)',
    (await cell(OTA.task_key, 8)) === `${stamp(NEWEST.created_utc)} · completed · 8 evaluations · first feasible at 5` && (await cell(OTA.task_key, 9)) === '2',
    `${await cell(OTA.task_key, 8)} | ${await cell(OTA.task_key, 9)}`);
  check('a blocked task without a baseline: the mark [blocked], baseline none, no run', (await cell(LDO.task_key, 1)) === 'real[blocked]' && (await cell(LDO.task_key, 6)) === 'none'
    && (await cell(LDO.task_key, 8)) === 'none' && (await cell(LDO.task_key, 9)) === '0', JSON.stringify(await Promise.all([1, 6, 8, 9].map(n => cell(LDO.task_key, n)))));
  check('an ngspice task without its connection: the mark "choose its connection", no cell, no baseline column value', (await cell(NG.task_key, 1)) === 'ngspice[ngspice: choose its connection]'
    && (await cell(NG.task_key, 3)) === 'ngspice netlist' && (await cell(NG.task_key, 6)) === '-' && (await cell(NG.task_key, 4)) === '2', JSON.stringify(await Promise.all([1, 3, 4, 6].map(n => cell(NG.task_key, n)))));
  check('the MOCK task: a MOCK badge', (await cell(MOCK.task_key, 1)) === 'MOCK' && await far.evaluate(`!!${ROWS}.find(tr => tr.title === 'synthetic:gpdk045_ota5').querySelector('.mock-tag')`));
  await far.shot(path.join(out, 'task-list-2-window.png'));

  // ---- 4. a double click makes the page follow the task --------------------------------------------------------------------------
  const starters = count('starter real:fixture_ota');
  check('a double click on a row makes the page follow that task: the Task row names it, its rows are read once', await tw.choose('real:fixture_ota') && count('starter real:fixture_ota') === starters + 1
    && (await evaluate(`${ROW}.querySelector('.task-list-mark')`)) === null, `${await tw.current()} (${count('starter real:fixture_ota') - starters} read(s))`);
  await page.saved();
  check('the configuration follows: task, labels, rows, run label', (await page.stored()).circuit.task_id === 'real:fixture_ota' && (await page.stored()).project.task_name === 'fixture_ota'
    && (await page.stored()).parameters.length === 2 && (await page.stored()).targets[0].metric_id === 'gain_db', JSON.stringify((await page.stored()).circuit));
  check('the marked row moves to it; the window stays open', (await far.evaluate(`${ROWS}.filter(tr => tr.classList.contains('current')).map(tr => tr.title)`)).join() === 'real:fixture_ota' && !far.closed);
  check('the Project column says the rows are this task\'s', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`, 50));
  check('no question was asked: the rows were untouched', dialogs.length === 0, JSON.stringify(dialogs));
  check('one Undo takes the choice back, and the Task row says so', (await evaluate(`[...${EDITORS}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Undo').click()`), await until(`${ROW}.querySelector('.task-list-key')?.textContent === 'synthetic:gpdk045_ota5'`, 50)));
  check('... and the window marks the MOCK task again', await far.until(`${ROWS}.filter(tr => tr.classList.contains('current')).map(tr => tr.title).join() === 'synthetic:gpdk045_ota5'`, 30));
  await tw.choose('real:fixture_ota');

  // ---- 5. Details: the facts and the task's rows -----------------------------------------------------------------------------------
  await far.evaluate(`[...${ROWS}.find(tr => tr.title === 'real:fixture_ota').querySelectorAll('button')].find(b => b.textContent.trim() === 'Details').click()`, true);
  const DETAILS = `${WINDOW}.querySelector('.task-details')`;
  check('Details opens under the row and reads the task\'s rows once (the third read: two choices went before)', await far.until(`!!(${DETAILS}) && !!${DETAILS}.querySelector('table.task-rows-table')`, 50) && count('starter real:fixture_ota') === starters + 3, `${count('starter real:fixture_ota') - starters} read(s)`);
  const details = await far.evaluate(`${DETAILS}.textContent`);
  check('the facts: registered task, cell with testbench, saved from, revision, baseline, state, sizes, results, runs', ['Registered taskreal:fixture_ota', 'Runs inFIXTURE_LIB/fixture_ota with testbench tb_fixture_ota',
    'Revision3', `Baseline recorded${stamp(OTA.baseline_recorded_utc)}`, 'Statebaseline recorded', 'Sizes varied6', 'Results measured6', 'Runs2; newest'].every(t => details.includes(t)), details.slice(0, 300));
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
  check('a press on a column title sorts by it (rows without a value stay last)', await far.until(`${ROWS}.map(tr => tr.title).join() === 'real:fixture_ldo,ngspice:fixture_div,real:fixture_ota,synthetic:gpdk045_ota5'`, 30), (await tw.keys()).join());
  await far.evaluate(`[...${TABLE}.querySelectorAll('thead th')].find(th => th.textContent.startsWith('Rev')).click()`);
  check('... and again the other way', await far.until(`${ROWS}.map(tr => tr.title).join() === 'real:fixture_ota,ngspice:fixture_div,real:fixture_ldo,synthetic:gpdk045_ota5'`, 30), (await tw.keys()).join());

  // ---- 7. Refresh list reads both lists; an older server is said --------------------------------------------------------------------
  let before = { tasks: count('/api/tasks'), runs: count('/api/runs') };
  await press('Refresh list');
  check('"Refresh list" reads the task list and the run list again', await far.until(`${WINDOW}.textContent.includes('read at')`, 30) && (await (async () => { for (let i = 0; i < 40 && (count('/api/tasks') < before.tasks + 1 || count('/api/runs') < before.runs + 1); i++) await sleep(50);
    return count('/api/tasks') === before.tasks + 1 && count('/api/runs') === before.runs + 1; })()), JSON.stringify(seen.slice(-4)));
  runsMode = 'older';
  await press('Refresh list'); await sleep(800);
  check('a server older than the page (runs without their task) is said in plain words, and the run columns stay empty', await far.until(`${WINDOW}.textContent.includes('older than this page')`, 30)
    && (await cell(OTA.task_key, 8)) === '-' && (await cell(OTA.task_key, 9)) === '-', `${await cell(OTA.task_key, 8)} | ${await cell(OTA.task_key, 9)}`);
  runsMode = 'normal';
  await press('Refresh list'); await sleep(800);
  check('with the task in the rows again, the run columns are back', await far.until(`!${WINDOW}.textContent.includes('older than this page')`, 30) && (await cell(OTA.task_key, 9)) === '2');

  // ---- 8. nothing updates by itself --------------------------------------------------------------------------------------------
  before = { tasks: count('/api/tasks'), runs: count('/api/runs') };
  await sleep(2500);
  check('nothing in the window updates by itself', count('/api/tasks') === before.tasks && count('/api/runs') === before.runs, JSON.stringify(seen));
  check('closing the window leaves the page on its task, the button no longer marked open', (await tw.close(), await until(`!${ROW}.querySelector('button.task-list-button').classList.contains('open')`, 30)) && (await tw.current()) === 'real:fixture_ota');
  reportRefused(refused, NEVER_ASKED);
  check('no console errors', consoleErrors.filter(e => !/404|418/.test(e)).length === 0, consoleErrors.join(' | ').slice(0, 300));
});
