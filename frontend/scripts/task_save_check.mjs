// Browser check of saved tasks (TaskSave.tsx, TaskFile.tsx): an open task's "Save task" (next revision) and the task
// file in a window of its own. Same approach as working_copy_check.mjs: a throwaway
// headless Edge over the DevTools protocol against a workbench page (default http://127.0.0.1:8765/; GATOR_WORKBENCH_URL for
// a preview of a temporary build). EVERY /api/virtuoso/* request, the circuit load and the task list of the open task are
// answered with canned FIXTURES, so Virtuoso is never contacted and nothing is saved anywhere; any other writing request of
// the page is refused (reads pass). What it pins (user request
// 2026-09-22, "go on part 2"):
//   - an open task names itself and its revision; two short buttons: Save task, Task file - at the right end of the
//     editors' tab line, not in the Project panel (user request 2026-09-22); no
//     "Save as" since 2026-09-23 (the workbench makes no copies: another task is another copy the user makes and reads);
//   - "Task file" opens a window with the task as one readable file (its _help included); "Apply to editors" checks it and
//     fills the editors (one Undo step); a broken file is refused with its problems and changes nothing;
//   - "Save task" sends the rows, the task and what the file added (analyses) and reports the revision and the baseline;
//     nothing happens on load.
// Record 7.198 (user: "show saving (is it possible to show progress?) and if the backend is saving dont allow another save
// task press even after refreshing page"), with the backend's save state answered as a FIXTURE too:
//   - while a save runs, its step shows under the toolbar and Save task is closed; nothing is asked once no save runs;
//   - a page loaded during a save shows it, keeps Save task closed (a press sends nothing), follows the steps, says how
//     the save ended and reads the task list again;
//   - a save refused because another one runs says so, and the page follows that one to its end;
//   - reads that fail do not end the following; a save the backend no longer knows (started again) ends with a warning.
// Record 7.203 (user: "yes build it", for rows older than the saved task):
//   - Save task sends which saved revision the rows came from: none before the page knows, then the revision of the
//     last save or of the rows Reload saved values brought; the check while editing gets it too;
//   - refused because the rows are older than the saved task, the page asks under the toolbar: "Save anyway" sends the
//     save again with replace_newer, "Reload saved values" brings the saved rows (and their revision).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; WSLENV carries the URL into it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/task_save_check.mjs)" [screenshot-dir]
import path from 'node:path';
import { answerDialogs, check, launchEdge, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('task');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const ROWS = [{ variable_id: 'wn', instance_path: 'XU1/MN1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005 }];
const PROBES = [{ measurement_id: 'm_osc_frequency_hz', analysis: 'tran', result_source: 'backend_profile', source_name: 'osc_frequency_hz', unit: 'Hz' }];
const SPECS = [{ metric_id: 'osc_frequency_hz', equation: 'm_osc_frequency_hz', unit: 'Hz', constraint: '>=', lower: 1.1e9, normalization_scale: 1e9 }];
const tasksKnown = new Set(['real:ring_osc']);
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: true, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { MN1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: ['FIXTURE: a saved task.'] });
const fileText = (task, rows) => JSON.stringify({ _help: { 'what this is': 'The task file: everything this task is, in one place.' }, format: 'gator-task-1', name: task,
  revision: 1, cell: { library: 'GPDK045_RINGOSC', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' },
  copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' },
  measurement: { kind: 'ring_oscillator', expected_frequency_hz: 1.2e9 }, maestro: { analyses: {}, variables: {}, bindings: [], model_files: [] },
  parameters: rows.parameters, probes: rows.measurements, specs: rows.targets, notes: '' }, null, 2);

await runChecks(browser, async () => {
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, fulfil } = page;
  const calls = []; const dialogs = []; const answers = [];
  // The backend's save state (record 7.198) as GET /api/tasks/saving answers it, and the save's own answer: `hold` keeps
  // it back until `release()`; `conflict` refuses it because another save runs.
  let saving = { running: null, last: null }, hold = false, conflict = null, release = null, statusReads = 0, taskListReads = 0, failing = false;
  // Record 7.203: `older` refuses a save that does not say "Save anyway"; the starter tells its rows' revision.
  let older = false, starterReads = 0;
  const validations = [];
  const answer = async params => {
    const { requestId, request } = params;
    const url = new URL(request.url), pathname = url.pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/config/validate') { validations.push(body); return page.readOrRefuse(params, page.refused, { reads: true }); }
    if (pathname === '/api/tasks/saving') {
      statusReads++;
      return failing ? fulfil(requestId, 503, { detail: { message: 'FIXTURE: the backend is starting again' } }) : fulfil(requestId, 200, saving);
    }
    if (pathname === '/api/tasks') {
      taskListReads++;
      const real = await (await fetch(new URL('api/tasks', APP))).json();
      return fulfil(requestId, 200, { ...real, tasks: [...real.tasks, ...[...tasksKnown].map(key => ({ task_key: key, kind: 'real', available: true, generated: true,
        revision: key === 'real:ring_osc' ? revision : 1, circuit_class: 'vco', pdk_id: 'gpdk045' }))] });
    }
    if (pathname === '/api/tasks/starter' && tasksKnown.has(url.searchParams.get('task_key'))) {
      starterReads++;
      return fulfil(requestId, 200, { project: { name: 'fixture', task_name: 'ring' }, circuit: { source: 'registered_task', task_id: url.searchParams.get('task_key') },
        parameters: ROWS, measurements: PROBES, targets: SPECS, revision: 9 });
    }
    if (pathname === '/api/circuit/load') {
      const circuit = body.circuit ?? {};
      return circuit.source === 'registered_task' && tasksKnown.has(circuit.task_id) ? fulfil(requestId, 200, generated(circuit.task_id)) : send('Fetch.continueRequest', { requestId });
    }
    if (!pathname.startsWith('/api/virtuoso/')) return send('Fetch.continueRequest', { requestId });
    const op = pathname.replace('/api/virtuoso/', '');
    calls.push({ op, ...body });
    await sleep(120);
    if (op === 'task/file') return fulfil(requestId, 200, { text: fileText(body.task, body.config), name: body.task, revision, saved: true });
    if (op === 'task/file/check') {
      let data; try { data = JSON.parse(body.text); } catch (e) { return fulfil(requestId, 200, { ok: false, problems: ['Not valid JSON: FIXTURE'], rows: {}, extras: {} }); }
      const bad = (data.probes ?? []).some(p => p.analysis === 'sometimes');
      return fulfil(requestId, 200, bad ? { ok: false, problems: ['probes[0] analysis: Input should be \'dc\', \'ac\', \'tran\' ... (FIXTURE)'], rows: {}, extras: {} }
        : { ok: true, problems: [], rows: { parameters: data.parameters, measurements: data.probes, targets: data.specs }, extras: { analyses: data.maestro?.analyses ?? {}, notes: data.notes } });
    }
    if (op === 'task/save' && older && !body.replace_newer) {
      return fulfil(requestId, 409, { detail: { code: 'saved_task_newer', undone: { base: 3, current: 4, items: [] },
        message: "FIXTURE: real:ring_osc was saved again after these rows were loaded: it is revision 4 now, the rows here are revision 3's. "
          + 'Saving them would undo what was saved since: Specs osc_frequency_hz: normalization_scale 2e+08 saved, 1e+09 here. '
          + 'Press Reload saved values to take the saved rows, or save anyway.' } });
    }
    if (op === 'task/save' && conflict) {
      saving = { running: conflict, last: saving.last };
      return fulfil(requestId, 409, { detail: { code: 'save_running', running: conflict,
        message: 'Another save is running (real:ring_osc, 5 s so far). Save task can be pressed again when it has ended.' } });
    }
    if (op === 'task/save' && hold) {
      saving = { running: runningAt('own', 2, 12), last: saving.last };
      await new Promise(resolve => { release = resolve; });
      saving = { running: null, last: { id: 'own', task_key: 'real:ring_osc', ok: true, seconds: 30, answer: { task_key: 'real:ring_osc', revision: revision + 1 } } };
    }
    if (op === 'task/save') {
      if (body.as_new) { tasksKnown.add(`real:${body.name}`); return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, revision: 1, created: true, runnable: true,
        circuit_class: 'vco', pdk_id: 'gpdk045', parameters: ROWS, baseline_kept: false, changed: [], copy: { library: 'GPDK045_RINGOSC_GATOR', cell: `ring_osc_3stage_${body.name}`, testbench: `tb_ring_osc_3stage_${body.name}` } }); }
      revision += 1;
      return fulfil(requestId, 200, { task_key: `real:${body.task}`, name: body.task, revision, created: false, runnable: true, circuit_class: 'vco', pdk_id: 'gpdk045',
        parameters: ROWS, baseline_kept: false, changed: ['parameters', 'specs'], copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' } });
    }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
  let revision = 1;
  const STEPS = [['setup', 'Virtuoso writes the Maestro test into the cell and reads it back'], ['deck', 'Virtuoso netlists the Maestro test'],
    ['read', 'Virtuoso reads the cell into the workbench'], ['files', 'Writing the task files and checking them']].map(([id, title]) => ({ id, title }));
  const runningAt = (id, number, seconds) => ({ id, task_key: 'real:ring_osc', started_utc: '2026-10-05T16:00:00+00:00', seconds, steps: STEPS,
    step: STEPS[number - 1].id, step_number: number, step_seconds: 1, usual_seconds: 34 });
  answerDialogs(page, answers, dialogs);
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Registered task'))`;
  const BLOCK = `document.querySelector('.editors .tabs .task-save')`;          // the bar: right end of the editors' tab line
  const NOTES = `document.querySelector('.editors .task-notes')`;              // its messages and questions, under the toolbar
  const BUTTON = text => `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const blockText = () => evaluate(`${BLOCK}?.textContent ?? ''`);
  const notesText = () => evaluate(`${NOTES}?.textContent ?? ''`);
  const press = (label, gesture = false) => evaluate(`${BUTTON(label)}.click()`, gesture);
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')`);
  const POPUP = `window.open('', 'gator-task-file')`;                             // the same name returns the open window, unchanged
  const popupEval = body => evaluate(`(() => { const w = ${POPUP}; const d = w.document; ${body} })()`, true);
  const typeInto = async (selector, text) => page.setValue(`${selector}`, text, { event: 'input', userGesture: true });
  // Up to `ms` for the press to reach the backend; once it has, settled when 0.5 s pass with no further call (the fixture
  // answers after 0.12 s). A press that sends nothing still waits the whole `ms`. It slept `ms` every time until 2026-09-30.
  const settle = async (ms = 900) => {
    const mark = calls.length;
    for (let waited = 0; waited < ms && calls.length === mark; waited += 50) await sleep(50);
    for (let seen = mark; calls.length !== mark && seen !== calls.length;) { seen = calls.length; await sleep(500); }
  };

  await page.intercept(['*/api/virtuoso/*', '*/api/circuit/load', '*/api/tasks', '*/api/tasks/starter*', '*/api/tasks/saving', '*/api/config/validate'], answer,
    { others: 'read', connection: 'lab' });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  for (let i = 0; i < 50 && !(await stored()); i++) await sleep(100);
  const start = await stored();
  const seeded = { ...start, circuit: { ...start.circuit, source: 'registered_task', task_id: 'real:ring_osc', circuit_class: 'vco', pdk_id: 'gpdk045' },
    parameters: ROWS, measurements: PROBES, targets: SPECS };
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(seeded))})`);
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${BLOCK})`)); i++) await sleep(100);
  await settle(1500);
  check('nothing is saved or read from Virtuoso on load', calls.length === 0, calls.map(c => c.op).join(' | '));
  check('the open task names itself and its revision', (await blockText()).includes('Task real:ring_osc, revision 1'), await blockText());
  check('two short buttons: Save task, Task file - no Save as', await evaluate(`!!(${BUTTON('Save task')}) && !(${BUTTON('Save as')}) && !!(${BUTTON('Task file')})`));
  check('they sit in the editors\' tab line, none in the Project panel', await evaluate(`!!${BLOCK}.closest('.tabs') && !${PANEL}.querySelector('.task-save')
    && ![...${PANEL}.querySelectorAll('button')].some(b => ['Save task', 'Save as', 'Task file'].includes(b.textContent.trim()))`));
  const place = await evaluate(`(() => { const bar = ${BLOCK}.getBoundingClientRect(), tabs = ${BLOCK}.closest('.tabs'), line = tabs.getBoundingClientRect();
    const first = tabs.querySelector('button').getBoundingClientRect();
    const modify = [...document.querySelectorAll('.editors .toolbar button')].pop().getBoundingClientRect();         // the toolbar's right end
    return { right: line.right - bar.right, sameLine: bar.top < first.bottom && bar.bottom > first.top, above: bar.bottom <= modify.top + 1,
             over: bar.left < modify.right && bar.right > modify.left }; })()`);
  check('on the tab line, at its right end, above the toolbar\'s last button', place.sameLine && place.right < 12 && place.above && place.over, JSON.stringify(place));
  check('only a person can press it, said on the button', await evaluate(`${BUTTON('Save task')}.title.includes('Only you can press it.')`));

  // ---- the task file in a window of its own ---------------------------------------------------------------------------------------
  await press('Task file', true); await settle(1500);
  check('"Task file" asks for the file of the current editors, once', calls.map(c => c.op).join() === 'task/file' && calls[0].task === 'ring_osc'
    && Array.isArray(calls[0].config?.targets), JSON.stringify(calls));
  const opened = await popupEval(`return d.querySelector('.task-file textarea')?.value ?? ''`);
  check('it opens in its own window, as one readable file with its _help', opened.includes('"_help"') && opened.includes('"specs"') && opened.includes('GPDK045_RINGOSC_GATOR'), opened.slice(0, 80));
  const edited = JSON.parse(opened);
  edited.specs[0].lower = 1.25e9; edited.maestro.analyses = { tran: { stop: '40n' } }; edited.notes = 'tighter';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(edited, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await settle();
  let config = await stored();
  for (let i = 0; i < 30 && config.targets[0].lower !== 1.25e9; i++) { await sleep(100); config = await stored(); }   // the page stores a moment later
  check('"Apply to editors" checks the file and fills the editors', calls.at(-1).op === 'task/file/check' && config.targets[0].lower === 1.25e9, JSON.stringify(config.targets));
  check('the window says what happened and that nothing is saved yet', (await popupEval(`return d.querySelector('.task-file').textContent`)).includes('Press "Save task" to store them'));
  edited.probes[0].analysis = 'sometimes';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(edited, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await settle();
  config = await stored();
  check('a broken file is refused with its problems and changes nothing', (await popupEval(`return d.querySelector('.task-file .blocker')?.textContent ?? ''`)).includes('probes[0] analysis')
    && config.measurements[0].analysis === 'tran', config.measurements[0].analysis);
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);

  // ---- Save task: the next revision of the same task --------------------------------------------------------------------------------
  let mark = calls.length;
  await press('Save task'); await settle(1500);
  const saveCall = calls.slice(mark).find(c => c.op === 'task/save');
  check('before the page knows where its rows came from, Save task says none (7.203)', saveCall?.base_revision === null && saveCall?.replace_newer === false,
    JSON.stringify({ base: saveCall?.base_revision, replace: saveCall?.replace_newer }));
  check('Save task sends the rows, the open task and what the file added', !!saveCall && saveCall.task === 'ring_osc' && saveCall.name === 'ring_osc' && !saveCall.as_new
    && saveCall.extras?.analyses?.tran?.stop === '40n' && saveCall.config?.targets?.[0]?.lower === 1.25e9, JSON.stringify(saveCall ?? calls.slice(mark)));
  check('it reports the revision and that the baseline no longer holds, under the toolbar', (await notesText()).includes('Saved real:ring_osc, revision 2.') && (await notesText()).includes('no longer holds'), await notesText());
  await sleep(500);
  check('the open task shows its new revision', (await blockText()).includes('revision 2'), await blockText());

  // ---- no "Save as" (2026-09-23): the open task never sends as_new; another task is another copy, read in the Virtuoso window ----
  check('nothing under the toolbar asks for a new task name', !(await evaluate(`[...${NOTES}?.querySelectorAll('label') ?? []].some(l => l.firstChild?.textContent.trim() === 'New task name')`)));
  check('no save of this check was sent as_new', calls.filter(c => c.op === 'task/save').every(c => c.as_new === false), JSON.stringify(calls.filter(c => c.op === 'task/save').map(c => c.as_new)));
  check('the task\'s block in the column names it and offers Check now', (await evaluate(`${PANEL}.textContent`)).includes('Before every run:')
    && (await evaluate(`[...${PANEL}.querySelectorAll('button')].some(b => b.textContent.trim() === 'Check now')`)));

  // ---- record 7.198: a running save shows its step and keeps Save task closed until it ends, also after a reload ----------
  const SAVE = `${BLOCK}?.querySelector('button.primary')`;                    // its caption says "Saving..." while one runs
  const LINE = `document.querySelector('.editors .task-notes .task-save-progress')`;
  const lineText = () => evaluate(`${LINE}?.textContent ?? ''`);
  const closed = () => evaluate(`${SAVE}?.disabled ?? null`);
  check('the page asked the backend about a running save when Save task appeared', statusReads >= 1, `${statusReads} reads`);
  hold = true; let reads = statusReads;
  await evaluate(`${SAVE}.click()`);
  check('its own save shows a line under the toolbar at once', await page.until(`!!(${LINE})`, 30), await notesText());
  await page.until(`(${LINE}?.textContent ?? '').includes('step 2 of 4')`, 40);
  check('it follows the steps the backend counts', (await lineText()) === 'Saving real:ring_osc - step 2 of 4: Virtuoso netlists the Maestro test (12 s; its last save took 34 s)',
    await lineText());
  check('Save task is closed while it runs', (await closed()) === true);
  check('it sends the revision its last save made: the rows came from there (7.203)', calls.filter(c => c.op === 'task/save').at(-1)?.base_revision === 2,
    JSON.stringify(calls.filter(c => c.op === 'task/save').map(c => c.base_revision)));
  check('the page asked again while the save ran', statusReads > reads + 1, `${statusReads - reads} reads`);
  await page.shot(path.join(out, 'task-save-progress.png'), `document.querySelector('.editors')`, { maxHeight: 220 });
  release(); hold = false;
  check('when the answer comes, the line goes', await page.until(`!(${LINE})`, 40), await lineText());
  check('and the save says what it did', (await notesText()).includes('Saved real:ring_osc, revision 3.'), await notesText());
  check('Save task opens again', (await closed()) === false);
  reads = statusReads; await sleep(2500);
  check('nothing is asked once no save runs', statusReads <= reads + 1, `${statusReads - reads} more reads`);

  // A page loaded while a save runs (the user's reload of 2026-10-05): shown, Save task closed, followed to its end.
  saving = { running: runningAt('earlier', 1, 3), last: null };
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${SAVE})`)); i++) await sleep(100);
  check('a page loaded during a save shows it', await page.until(`(${LINE}?.textContent ?? '').includes('step 1 of 4')`, 50), await lineText());
  for (let i = 0; i < 50 && !validations.some(v => v.rows_from === 3); i++) await sleep(100);     // the page checks 0.5 s after a change
  check('the reloaded page still knows where its rows came from: the check gets it (7.203)', validations.some(v => v.rows_from === 3),
    JSON.stringify(validations.map(v => v.rows_from ?? null)));
  check('and keeps Save task closed', (await closed()) === true);
  check('its tooltip says what it waits for', (await evaluate(`${SAVE}.title`)).startsWith('Save task: Waits for the save of real:ring_osc that is running.'),
    await evaluate(`${SAVE}.title`));
  let saves = calls.filter(c => c.op === 'task/save').length;
  await evaluate(`${SAVE}.click()`); await sleep(400);
  check('a press on the closed Save task sends nothing', calls.filter(c => c.op === 'task/save').length === saves);
  saving = { running: runningAt('earlier', 3, 20), last: null };
  check('it follows that save\'s steps', await page.until(`(${LINE}?.textContent ?? '').includes('step 3 of 4: Virtuoso reads the cell into the workbench (20 s')`, 40),
    await lineText());
  const listed = taskListReads;
  revision = 4;
  saving = { running: null, last: { id: 'earlier', task_key: 'real:ring_osc', ok: true, seconds: 33.8,
    answer: { task_key: 'real:ring_osc', revision: 4, created: false, baseline_kept: true, changed: ['specs'] } } };
  check('when it ends, the line goes', await page.until(`!(${LINE})`, 40), await lineText());
  check('and the page says how it ended', (await notesText()).includes('The save that was running has ended. Saved real:ring_osc, revision 4. The recorded baseline still holds.'),
    await notesText());
  check('it reads the task list again, so the task shows its new revision', await page.until(`(${BLOCK}?.textContent ?? '').includes('revision 4')`, 40)
    && taskListReads > listed, `${await blockText()} | ${taskListReads - listed} reads`);
  check('Save task opens again after it', (await closed()) === false);

  // A press that meets another save (a stale page or another tab): refused by the backend, said, and followed.
  conflict = runningAt('tab', 2, 5);
  saves = calls.filter(c => c.op === 'task/save').length;
  await evaluate(`${SAVE}.click()`);
  check('a save refused because another one runs says so', await page.until(`(${NOTES}?.textContent ?? '').includes('Another save is running')`, 40), await notesText());
  check('and the page follows that save, Save task closed', await page.until(`(${LINE}?.textContent ?? '').includes('step 2 of 4')`, 40) && (await closed()) === true,
    await lineText());
  conflict = null;
  saving = { running: null, last: { id: 'tab', task_key: 'real:ring_osc', ok: false, seconds: 9, problem: { code: 'refused', message: 'FIXTURE: the copy reads back differently' } } };
  check('a followed save that failed says why', await page.until(`(${NOTES}?.textContent ?? '').includes('The save that was running ended without saving: FIXTURE: the copy reads back differently')`, 40),
    await notesText());
  check('one save was sent for that press, and none since', calls.filter(c => c.op === 'task/save').length === saves + 1);
  check('Save task opens again after a failed one', (await closed()) === false);

  // The backend starts again during a save: its reads fail for a while, then it knows no save at all.
  saving = { running: runningAt('lost', 1, 2), last: null };
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!(${SAVE})`)); i++) await sleep(100);
  await page.until(`(${LINE}?.textContent ?? '').includes('step 1 of 4')`, 50);
  failing = true; reads = statusReads; await sleep(2600);
  check('reads that fail do not end the following: the page keeps asking', statusReads >= reads + 2, `${statusReads - reads} reads`);
  failing = false; saving = { running: null, last: null };
  check('a save the backend no longer knows ends with a warning', await page.until(`(${NOTES}?.textContent ?? '').includes('ended without an answer')`, 40),
    await notesText());
  check('Save task opens again after it', (await closed()) === false);
  reads = statusReads; await sleep(2500);
  check('and the page stops asking', statusReads <= reads + 1, `${statusReads - reads} more reads`);

  // ---- record 7.203: rows older than the saved task - the page asks before they replace it ------------------------------------
  const QUESTION = `document.querySelector('.editors .task-notes .task-save-newer')`;
  const ASK = text => `[...(${QUESTION}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  older = true;
  let sent = calls.filter(c => c.op === 'task/save').length;
  await evaluate(`${SAVE}.click()`);
  check('refused as older than the saved task, the page asks under the toolbar', await page.until(`!!(${QUESTION})`, 40)
    && (await evaluate(`${QUESTION}.textContent`)).includes('it is revision 4 now, the rows here are revision 3') , await notesText());
  check('the question offers Reload saved values and Save anyway', await evaluate(`!!(${ASK('Reload saved values')}) && !!(${ASK('Save anyway')})`));
  await page.shot(path.join(out, 'task-save-older.png'), `document.querySelector('.editors')`, { maxHeight: 240 });
  check('and says nothing was saved: no "Saved" line', !(await notesText()).includes('Saved real:'), await notesText());
  check('the refused save said which revision the rows came from', calls.filter(c => c.op === 'task/save').at(-1)?.base_revision === 3);
  await evaluate(`${ASK('Save anyway')}.click()`); await settle(1500);
  const anyway = calls.filter(c => c.op === 'task/save').slice(sent);
  check('"Save anyway" sends the save again, saying so', anyway.length === 2 && anyway[1].replace_newer === true && anyway[0].replace_newer === false,
    JSON.stringify(anyway.map(c => c.replace_newer)));
  check('and the save says what it did, the question gone', (await notesText()).includes(`Saved real:ring_osc, revision ${revision}.`) && !(await evaluate(`!!(${QUESTION})`)),
    await notesText());
  const savedAs = revision;
  sent = calls.filter(c => c.op === 'task/save').length;
  await evaluate(`${SAVE}.click()`);
  await page.until(`!!(${QUESTION})`, 40);
  check('the next save starts from the revision "Save anyway" made', calls.filter(c => c.op === 'task/save').at(-1)?.base_revision === savedAs);
  const read = starterReads;
  answers.push(true);                                      // the rows here differ from the saved ones: OK, discard them
  await evaluate(`${ASK('Reload saved values')}.click()`);
  for (let i = 0; i < 40 && starterReads === read; i++) await sleep(100);
  check('"Reload saved values" reads the saved rows, after its own question', starterReads > read && !(await evaluate(`!!(${QUESTION})`))
    && dialogs.at(-1)?.message.startsWith('Reload saved values?') && dialogs.at(-1)?.planned, `${starterReads - read} reads`);
  older = false; await sleep(400);
  sent = calls.filter(c => c.op === 'task/save').length;
  await evaluate(`${SAVE}.click()`); await settle(1500);
  check('then Save task starts from the revision those rows are', calls.filter(c => c.op === 'task/save').slice(sent)[0]?.base_revision === 9,
    JSON.stringify(calls.filter(c => c.op === 'task/save').slice(sent).map(c => c.base_revision)));

  check('no unplanned dialog', dialogs.every(d => d.planned), JSON.stringify(dialogs));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
  await page.shot(path.join(out, 'task-save-1.png'));
  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
});
