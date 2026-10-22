// Browser check of "the bottom tabs follow the registered task" (record 7.212; this project has no frontend test runner).
// User request 2026-10-05: "Can you tie run with registered tasks? For the frontend, after selecting specific task, it
// automatically load the most recent corresponding run of the registered task. If there is no recent run, then leave run
// selection and run status default blank unless you choose other runs."
// Same approach as task_rows_check.mjs and run_list_check.mjs: a throwaway headless Edge over the DevTools protocol against
// the RUNNING workbench (default http://127.0.0.1:8765/). HERMETIC: the task list, the starters, the circuit loads, the
// validations and EVERY /api/runs* request are answered here with canned data labelled FIXTURE; other GET requests pass
// through and every other writing request is refused - so it reads no real run, and is safe on the live backend.
// What it pins: choosing a task shows its newest run (a Baseline simulation is one of its runs), a task without runs shows
// none, Undo and Redo of the choice follow too, the page does not follow on opening, a reload keeps what was shown (a blank
// included) unless the header holds another run by then, a run chosen in the run window while the list is read stays, a
// failed read or an older server (runs without their task) leaves the run shown as it is, the header's own run is never
// changed, and the run window names each run's registered task. Record 7.267: a run is chosen to be shown with Show results
// (a double click LOADS it now), and Load run makes the task-run link give way: the loaded run stays shown. Branch record
// SIF-84: Load run's edits question is asked in the Runs window, and a Cancel is said there as well as on the page.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 40 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/task_run_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { answerDialogs, check, launchEdge, NEVER_ASKED, outDir, reportRefused, RUN_KEY, runChecks, sleep, TASK_PANEL, taskWindow, validConfiguration, workbenchUrl, RUNS_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('taskrun');

// The page prints local time; Edge and this script run on the same Windows clock, so the expected text is built the same way.
import { two } from '../src/format.ts';                         // the page's own; this check's stamp() differs (no date: NaN)
const stamp = utc => { const d = new Date(utc); return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`; };

// ---- three saved tasks (FIXTURE); gamma has no run ----------------------------------------------------------------------
const parameter = (variable_id, instance_path) => ({ variable_id, instance_path, parameter_name: 'w', unit: 'm', scale: 'linear', value_type: 'continuous',
  lower: 6e-7, upper: 1.6e-6, step: 5e-9, optimized: true, initial_value: 1e-6 });
const probe = metric => ({ measurement_id: `m_${metric}`, analysis: 'ac', result_source: 'backend_profile', source_name: metric, unit: 'dB', notes: 'FIXTURE' });
const starter = name => ({ project: { name: `${name}-project`, task_name: name },
  circuit: { source: 'registered_task', task_id: `real:${name}`, circuit_class: 'opamp', pdk_id: 'gpdk045' },
  parameters: [parameter(`w_${name}`, 'XU1/M1')], measurements: [probe('gain_db')], targets: [] });
const NAMES = ['alpha', 'beta', 'gamma'];
const STARTERS = Object.fromEntries(NAMES.map(n => [`real:${n}`, starter(n)]));
const TASKS = NAMES.map(n => ({ task_key: `real:${n}`, kind: 'real', circuit_class: 'opamp', pdk_id: 'gpdk045', generated: true, available: true, blocker: null,
  starter_project: STARTERS[`real:${n}`].project }));
const loaded = taskId => ({ loaded: true, task_key: taskId, mock: false, circuit: {}, content_sha256: null, provided_metrics: [], hierarchy: {},
  summary: { device_count: 0, devices: [], unknown_devices: [] }, complete: true, diagnostics: [], analysis_context: null, notes: [], evaluation_backend: 'FIXTURE',
  max_concurrency: 1, native_draft: false, generated_profile: true, baseline_recorded: null });

// ---- the runs (FIXTURE), newest first as the backend sorts them ----------------------------------------------------------
const ROOT = '/fixture/outputs/fixture_exp__0001/runs';
const run = (id, task, folderTask, created, facts = {}) => ({ run_dir: `${ROOT}/${folderTask}/scratch__seed0__${id}`, run_id: id, task_id: `${folderTask}:0000`,
  task_key: `real:${task}`, task_name: folderTask, task_definition_hash: 'fixture', mode: 'scratch', mock: false, seed: 0, experiment: 'fixture_exp__0001',
  created_utc: created, started_utc: created, ended_utc: created.replace(':00+', ':30+'), last_seen_utc: null, active_seconds: 30, paused_seconds: 0,
  state: 'completed', stop_reason: 'budget_exhausted', error: null, evaluations: 8, max_evaluations: 8, first_feasible_eval_count: null, resumability: 'full_state',
  segments: [], ...facts });
const B1 = run('b1b1b1b1b1b1', 'beta', 'beta', '2026-10-05T19:00:00+00:00');
const A2 = run('a2a2a2a2a2a2', 'alpha', 'alpha', '2026-10-05T18:00:00+00:00');
const A1 = run('a1a1a1a1a1a1', 'alpha', 'alpha.baseline', '2026-10-05T17:00:00+00:00');     // a Baseline simulation of real:alpha
const LISTED = [B1, A2, A1];
const older = r => Object.fromEntries(Object.entries(r).filter(([k]) => k !== 'task_key'));     // a row as a server before record 7.212 lists it
const statusOf = r => ({ state: r.state, run_id: r.run_id, mode: r.mode, entry: 'start', provenance: 'real', mock: false, worker_alive: false, run_dir: r.run_dir,
  heartbeat_utc: r.ended_utc, stop_reason: r.stop_reason, error: null, active_workers: [], concurrency: 1, threads_per_job: 1, learner_updates: 0, first_feasible: null,
  budget: { max_evaluations: 8, max_launches: null, max_retries: 0, charged: 8, reserved: 0, in_flight: 0, completed: 8, failed: 0, released: 0, remaining: 0, launches: 8,
    retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: r.ended_utc, connection_profile_id: null, bytes_written: 1234, active_seconds: 30, paths: { run_dir: r.run_dir },
  connection: { overall: 'not_applicable' }, summary: { time: { active_seconds: 30, paused_seconds: 0 }, output: { resumability: 'full_state', completeness: 'complete', latest_checkpoint: null } },
  manifest: { mode: r.mode, mock: false, task_id: r.task_id, seeds: { target_seed: 0 }, source_model: { run_id: null }, budgets: { max_evaluations: 8 }, mock_notice: null } });

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = [], seen = [], dialogs = [], held = [];
  let runsMode = 'normal', holdRuns = false;           // how /api/runs is answered: normal | older | error; holdRuns: kept until released
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const answerRuns = requestId => (runsMode === 'error' ? fulfil(requestId, 500, { detail: 'FIXTURE: the run list could not be read' })
    : fulfil(requestId, 200, { runs: runsMode === 'older' ? LISTED.map(older) : LISTED }));
  const answer = params => {
    const { requestId, request } = params, url = new URL(request.url), name = url.pathname;
    if (name === '/api/tasks') return fulfil(requestId, 200, { tasks: TASKS, real_interface_contract: {} });
    if (name === '/api/tasks/starter') { const s = STARTERS[url.searchParams.get('task_key')]; return s ? fulfil(requestId, 200, s) : fulfil(requestId, 404, { detail: 'FIXTURE: no such task' }); }
    if (name === '/api/circuit/load') return fulfil(requestId, 200, loaded(JSON.parse(request.postData ?? '{}').circuit?.task_id ?? ''));
    if (name === '/api/config/validate') return fulfil(requestId, 200, validConfiguration({ facts: { circuit_checked: true } }));
    if (name.startsWith('/api/runs')) seen.push(name === '/api/runs/status' ? `status ${url.searchParams.get('run_dir')}` : name);
    if (name === '/api/runs') { if (holdRuns) { held.push(requestId); return; } return answerRuns(requestId); }
    if (name === '/api/runs/status') { const r = LISTED.find(x => x.run_dir === url.searchParams.get('run_dir')); return r ? fulfil(requestId, 200, statusOf(r)) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [] });
    // No fixture run has a save point: the backend answers 404, which Load run reads as "none" (record 7.270).
    if (name === '/api/runs/model') return fulfil(requestId, 404, { detail: { message: 'FIXTURE: this run has no save point' } });
    if (name.startsWith('/api/runs')) return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${name} is not expected in this check` } });
    return page.readOrRefuse(params, refused);
  };
  const lists = () => seen.filter(s => s === '/api/runs').length;
  const until = (expression, tries = 100) => page.until(expression, tries);
  const PANEL = TASK_PANEL;
  // Since record 7.227 the task is plain text + a "Tasks..." button; a choice is a double click in the task window (harness taskWindow).
  const tw = taskWindow(page, browser);
  // The row shows a saved task without its real: prefix since record 7.249; its key is in data-task-key (a placeholder,
  // "synthetic:vco (removed)", has only its text).
  const TASK_KEY = `(${PANEL}.querySelector('.task-row .task-list-key')?.dataset.taskKey ?? ${PANEL}.querySelector('.task-row .task-list-key')?.textContent ?? '')`;
  const EDITORS = `document.querySelector('.editors')`;
  const BUTTON = (scope, text) => `[...${scope}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const SHOWN = `(document.querySelector('footer .tabs .run-list-current')?.textContent ?? '')`;
  const shown = () => evaluate(SHOWN);
  const names = r => `${SHOWN}.includes(${JSON.stringify(stamp(r.created_utc))}) && ${SHOWN}.includes(${JSON.stringify(` · ${r.task_name} · `)})`;
  const headerRun = () => evaluate(`localStorage.getItem(${JSON.stringify(RUN_KEY)})`);
  // A choice in the task window; it is done once the Task row names it and the run list has been read for it.
  const choose = async (taskKey, { reads = 1 } = {}) => {
    const before = lists();
    const chosen = await tw.choose(taskKey);
    for (let i = 0; i < 100 && lists() < before + reads; i++) await sleep(50);
    return chosen;
  };
  const settle = () => sleep(700);                     // room for an answer to be drawn - or for a change that must not come
  const opened = async () => {                         // the page after a navigation or a reload: task list, strip, first list read
    const ok = await until(`!!(${PANEL}) && !!${PANEL}.querySelector('.task-row button.task-list-button') && !!document.querySelector('footer .tabs .run-list-current')`, 150);
    for (let i = 0; i < 100 && !seen.includes('/api/runs'); i++) await sleep(50);
    await settle();
    return ok;
  };
  const shot = name => page.shot(path.join(out, name), `document.querySelector('footer .tabs')`);

  // ---- the run window, as run_list_check.mjs drives it --------------------------------------------------------------
  const WINDOW = `document.querySelector('.run-window')`;
  let far = null;
  const openWindow = async () => {
    const before = lists();
    far = await browser.popup(page, `document.querySelector('footer .tabs button.run-list-button')`, RUNS_WINDOW,
      { width: 1500, height: 860, ready: `${WINDOW}?.querySelector('table.run-table')` });
    for (let i = 0; i < 50 && lists() === before; i++) await sleep(50);
    await sleep(300);
  };
  const doubleClick = async r => {
    const at = await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)}); if (!tr) return null;
      const el = tr.children[4]; el.scrollIntoView({ block: 'center' }); const b = el.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; })()`);
    if (!at) return false;
    await far.clickAt(at, { count: 2 });
    return true;
  };
  // Show results in a run's Details (record 7.267): the run the bottom tabs show, nothing else.
  const showResults = async r => {
    await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(r.run_dir)}); if (!tr) return;
      if (tr.nextElementSibling?.classList.contains('run-details-row')) return; [...tr.querySelectorAll('button')].find(b => b.textContent.trim() === 'Details').click(); })()`, true);
    const SHOW = `[...${WINDOW}.querySelectorAll('tr.run-details-row')].find(row => row.previousElementSibling?.title === ${JSON.stringify(r.run_dir)})?.querySelector('button.run-show')`;
    if (!(await far.until(`!!(${SHOW})`, 40))) return false;
    await far.evaluate(`${SHOW}.click()`, true);
    return true;
  };
  // The run table's own rows: an open Details row holds tables of its own, whose rows are not runs.
  const RUN_ROWS = `[...${WINDOW}.querySelector('table.run-table').querySelectorAll(':scope > tbody > tr:not(.run-details-row)')]`;
  const rows = () => far.evaluate(`${RUN_ROWS}.map(tr => tr.title)`);

  await page.intercept(['*/api/*'], answer);
  // The page opens on real:beta with its untouched rows; the header remembers A1 (a run of ANOTHER task): the page's state
  // before this feature, when the header's run was what a reload showed.
  const SEED = { schema_version: 'gator-workbench-config-v1', ...STARTERS['real:beta'], run: { mode: 'scratch', max_evaluations: 8, concurrency: 1, seed: 0 },
    output: { experiment_name: 'fixture' }, research: {} };
  await page.seed({ config: SEED, run: A1.run_dir, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await opened())) throw new Error('the page did not open: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));

  // ---- 1. opening the page follows nothing --------------------------------------------------------------------------
  check('opening the page reads the run list once and keeps the remembered run, although it is another task\'s', lists() === 1 && await until(names(A1), 30), `${lists()} read(s); ${await shown()}`);
  await shot('task-run-1-opened.png');

  // ---- 2. choosing a task shows its newest run ----------------------------------------------------------------------------
  await choose('real:alpha');
  check('choosing real:alpha reads the run list again and shows its NEWEST run (not its older Baseline simulation)', await until(names(A2), 50) && lists() === 2, `${lists()} read(s); ${await shown()}`);
  check('the header keeps its own run', (await headerRun()) === A1.run_dir, await headerRun());
  await shot('task-run-2-alpha.png');

  // ---- 3. a task without a run shows none ----------------------------------------------------------------------------------
  await choose('real:gamma');
  check('choosing real:gamma, which has no run, shows no run', await until(`${SHOWN} === 'No run selected'`, 50), await shown());
  // Run status is the tab shown; its own line, not the hidden Training tab's (which says the same).
  check('... and Run status is blank', await until(`[...document.querySelectorAll('footer .bottom-body > p.hint')].some(p => p.textContent === 'No run selected.')`, 30),
    await evaluate(`[...document.querySelectorAll('footer .bottom-body > p')].map(p => p.textContent).join(' | ')`));
  await shot('task-run-3-none.png');

  // ---- 4. Undo and Redo of the choice follow too -------------------------------------------------------------------------
  let before = lists();
  await evaluate(`${BUTTON(EDITORS, 'Undo')}.click()`);
  check('Undo takes the choice back, and the tabs show real:alpha\'s newest run again', await until(`${TASK_KEY} === 'real:alpha'`) && await until(names(A2), 50) && lists() === before + 1, await shown());
  before = lists();
  await evaluate(`${BUTTON(EDITORS, 'Redo')}.click()`);
  check('Redo: real:gamma again, and no run', await until(`${TASK_KEY} === 'real:gamma'`) && await until(`${SHOWN} === 'No run selected'`, 50) && lists() === before + 1, await shown());

  // ---- 5. a reload keeps the blank: not the header's run --------------------------------------------------------------------
  seen.length = 0;
  await send('Page.reload');
  check('after a reload the page is on real:gamma and still shows no run - not the header\'s run of another task', await opened()
    && (await tw.current()) === 'real:gamma' && (await shown()) === 'No run selected' && lists() === 1, `${await shown()} (${lists()} read(s))`);
  check('the header still holds its run', (await headerRun()) === A1.run_dir, await headerRun());

  // ---- 6. a run chosen in the run window stays: also across a reload -------------------------------------------------------
  await openWindow();
  const hint = await far.evaluate(`${WINDOW}.textContent`);
  check('the run window says what choosing a task does', hint.includes('Choosing a task under Task shows its newest run, or none if it has none.'));
  check('Show results on another task\'s run shows it', await showResults(B1) && await until(names(B1), 30), await shown());
  seen.length = 0;
  await send('Page.reload');
  far = null;                                                       // the page closes the windows it opened
  check('after a reload the chosen run is still shown', await opened() && await until(names(B1), 30), await shown());

  // ---- 7. a run chosen while the list is read for a task stays ---------------------------------------------------------------
  await choose('real:alpha');
  await until(names(A2), 50);
  await openWindow();
  holdRuns = true;
  await choose('real:beta', { reads: 1 });
  check('(the list read for real:beta is held)', held.length === 1, `${held.length} held`);
  check('meanwhile Show results chooses real:alpha\'s Baseline simulation', await showResults(A1) && await until(names(A1), 30), await shown());
  holdRuns = false;
  await answerRuns(held.shift());
  await settle();
  check('the answer that came later does not replace the run chosen meanwhile', await evaluate(names(A1)), await shown());

  // ---- 8. a failed read, and an older server, leave the run shown as it is ------------------------------------------------------
  runsMode = 'error';
  await choose('real:gamma');
  await settle();
  check('a run list that cannot be read: the run shown stays (named by its folder)', (await shown()).includes('scratch__seed0__a1a1a1a1a1a1'), await shown());
  runsMode = 'older';
  await choose('real:alpha');
  await settle();
  check('a server older than the page (runs without their task): the run shown stays, it is not made blank', await evaluate(names(A1)), await shown());
  runsMode = 'normal';
  await choose('real:beta');
  check('with the task in the list again, choosing real:beta shows its newest run', await until(names(B1), 50), await shown());

  // ---- 9. the run window names each run's registered task ------------------------------------------------------------------
  if (!far || far.closed) await openWindow();
  await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(A2.run_dir)});
    [...tr.querySelectorAll('button')].find(b => b.textContent.trim() === 'Details').click(); })()`, true);
  check('Details names the registered task of a run', await far.until(`(${WINDOW}.querySelector('.run-details')?.textContent ?? '').includes('Registered taskreal:alpha')`, 30),
    await far.evaluate(`${WINDOW}.querySelector('.run-details')?.textContent.slice(0, 160) ?? '(no details)'`));
  await far.evaluate(`(() => { const i = ${WINDOW}.querySelector('input.run-filter'); i.focus(); i.select(); })()`);
  await far.send('Input.insertText', { text: 'real:alpha' });
  check('the filter finds the runs of a registered task by its name', await far.until(`${RUN_ROWS}.length === 2`, 30)
    && JSON.stringify(await rows()) === JSON.stringify([A2.run_dir, A1.run_dir]), JSON.stringify(await rows()));

  // ---- 10. Load run (record 7.267): the run's task comes in, and the bottom tabs keep the LOADED run - the task-run link gives way ----
  await far.setValue(`${WINDOW}.querySelector('input.run-filter')`, '', { event: 'input' });
  check('(set-up) the page is on real:beta, showing its newest run', await until(`${TASK_KEY} === 'real:beta'`, 60) && await until(names(B1), 50), await shown());
  check('a double click on real:alpha\'s older run (its Baseline simulation) loads it', await doubleClick(A1));
  check('... the page\'s task becomes real:alpha', await until(`${TASK_KEY} === 'real:alpha'`, 60), await evaluate(TASK_KEY));
  check('... and the bottom tabs show the loaded run, not real:alpha\'s newest (the task-run link gives way)', await until(names(A1), 50), await shown());
  await settle();
  check('... and keep it: no list read for the task replaced it', await evaluate(names(A1)) && !(await evaluate(names(A2))), await shown());
  check('... the message names the run and its task; this run has no model, so the model stays as it was',
    /^Loaded run alpha\.baseline \d\d-\d\d \d\d:\d\d: task real:alpha, the model as it was: this run has no save point and loaded none\. Undo takes it back\.$/.test(await evaluate(`document.querySelector('.banner')?.textContent ?? ''`)),
    await evaluate(`document.querySelector('.banner')?.textContent ?? ''`));
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('one Undo takes the task back, and the bottom tabs follow the task again (its newest run)', await until(`${TASK_KEY} === 'real:beta'`, 60) && await until(names(B1), 50), await shown());

  check('the header\'s run was never changed by any of this', (await headerRun()) === A1.run_dir, await headerRun());
  check('no question was asked: the rows were untouched at every choice', dialogs.length === 0, JSON.stringify(dialogs));

  // ---- 11. Load run with edited rows (branch record SIF-84): the edits question is asked in the Runs window, where the press
  // was - the main window's opened behind it, and the Runs window, drawn by the page's script, stood still meanwhile - and a
  // Cancel is said in the window too, in the page message's words: that message line stands behind the window ----------------
  const LOWER = `JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')?.parameters?.[0]?.lower`;
  const banner = () => evaluate(`document.querySelector('.banner')?.textContent ?? ''`);
  await evaluate(`[...${EDITORS}.querySelectorAll(':scope > .tabs > button')].find(b => b.textContent.trim().startsWith('Parameters')).click()`);
  await page.setValue(`${EDITORS}.querySelector('table.editor tbody tr input.numeric')`, '0.0000007', { event: 'input' });
  check('(set-up) real:beta\'s size row is edited', await until(`${LOWER} === 7e-7`, 30), String(await evaluate(LOWER)));
  await openWindow();
  const runsAnswers = [], runsDialogs = [];
  await far.send('Page.enable');
  answerDialogs(far, runsAnswers, runsDialogs, 'Runs window');
  const REFUSED = `${WINDOW}.querySelector('.run-refused')`;
  const CANCELLED = /^Run alpha\.baseline \d\d-\d\d \d\d:\d\d was not loaded: you chose Cancel, so the task and its edits stay as they were\. Nothing changed\.$/;
  runsAnswers.push(false);
  await doubleClick(A1);
  const refusedText = (await far.until(`!!(${REFUSED})`, 60)) ? await far.evaluate(`${REFUSED}.textContent`) : '(no line)';
  check('a double click on another task\'s run asks the edits question in the Runs window, none in the main window',
    runsDialogs.length === 1 && runsDialogs[0].message.startsWith('Switch to real:alpha?') && runsDialogs[0].message.includes('unsaved') && dialogs.length === 0,
    JSON.stringify({ runs: runsDialogs, main: dialogs }));
  check('... Cancel: the window stays open and says why where its count stood, in the page message\'s words', CANCELLED.test(refusedText)
    && refusedText === await banner() && await far.evaluate(`${REFUSED}.classList.contains('run-count') && ${REFUSED}.getAttribute('role') === 'status'`),
    `${refusedText} | ${await banner()}`);
  check('... and nothing changed: real:beta with its edited row, its newest run shown', (await evaluate(TASK_KEY)) === 'real:beta' && (await evaluate(LOWER)) === 7e-7
    && await evaluate(names(B1)), `${await evaluate(TASK_KEY)} / ${await evaluate(LOWER)} / ${await shown()}`);
  await far.evaluate(`(() => { const tr = [...${WINDOW}.querySelectorAll('table.run-table tbody > tr')].find(tr => tr.title === ${JSON.stringify(A1.run_dir)});
    [...tr.querySelectorAll('button')].find(b => b.textContent.trim() === 'Details').click(); })()`, true);
  const LOAD = `[...${WINDOW}.querySelectorAll('tr.run-details-row')].find(row => row.previousElementSibling?.title === ${JSON.stringify(A1.run_dir)})?.querySelector('.run-actions button.run-load')`;
  check('opening the run\'s Details lets the line go: the count is back', await far.until(`!!(${LOAD}) && !(${REFUSED}) && /^3 runs under the output folder/.test(${WINDOW}.querySelector('.run-count').textContent)`, 40),
    await far.evaluate(`${WINDOW}.querySelector('.run-count')?.textContent ?? ''`));
  runsAnswers.push(false);
  await far.evaluate(`${LOAD}.click()`, true);
  check('Load run, Cancel again: the line stands beside the run\'s actions', await far.until(`!!${WINDOW}.querySelector('tr.run-details-row .run-actions .run-refused')`, 60)
    && runsDialogs.length === 2 && CANCELLED.test(await far.evaluate(`${REFUSED}.textContent`)), await far.evaluate(`${REFUSED}?.textContent ?? '(no line)'`));
  await far.shot(path.join(out, 'task-run-4-load-cancelled.png'), `${WINDOW}.querySelector('tr.run-details-row .run-refused').parentElement`, { pad: 8 });
  runsAnswers.push(true);
  await far.evaluate(`${LOAD}.click()`, true);
  let closed = false;
  try { await browser.window(RUNS_WINDOW, { present: false, ms: 6000, except: page.target.id }); closed = true; } catch { /* still open */ }
  check('Load run, OK: asked in the Runs window again, the run is loaded and the window closes', closed && runsDialogs.length === 3 && runsDialogs.every(d => d.planned)
    && await until(`${TASK_KEY} === 'real:alpha'`, 60) && /^Loaded run alpha\.baseline /.test(await banner()), `${closed} / ${runsDialogs.length} / ${await banner()}`);
  check('the main window asked nothing at all', dialogs.length === 0, JSON.stringify(dialogs));
  reportRefused(refused, NEVER_ASKED);
  check('no console errors', consoleErrors.filter(e => !/404|418/.test(e)).length === 0, consoleErrors.join(' | ').slice(0, 300));
});
