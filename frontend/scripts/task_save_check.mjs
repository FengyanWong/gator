// Browser check of TaskSave and TaskFile. The main Save as button names a separate task with a numbered prompt;
// calibration's explicit update request retains revision/stale-row handling. All Virtuoso requests are canned fixtures,
// and other writing requests are refused: no real task or cell is written. Covers the file window, progress, cancellation,
// invalid/duplicate names, numbered suggestions, task selection after saving, and in-place update compatibility.
// Record 7.198 (user: "show saving (is it possible to show progress?) and if the backend is saving dont allow another save
// task press even after refreshing page"), with the backend's save state answered as a FIXTURE too:
//   - while a save runs, its step shows under the toolbar and Save task is closed; nothing is asked once no save runs;
//   - a page loaded during a save shows it, keeps Save task closed (a press sends nothing), follows the steps, says how
//     the save ended and reads the task list again;
//   - a save refused because another one runs says so, and the page follows that one to its end;
//   - reads that fail do not end the following; a save the backend no longer knows (started again) ends with a warning.
// Record 7.362 (the user's Option D): the task's name and revision start the editors' tab line (the bar held them until then),
// Save as and Task file end it, and Check now stands there too - nothing of the task's in the circuit column.
// Branch record SIF-87: closing the task file's window (Close or its X) keeps a draft not applied; the next press reads the
// file again, lays the draft over it and says so, and Revert drops it.
// Branch record SIF-93: the file is a snapshot of the editors' rows. Changed in the editors since (their Undo, Redo), the
// window says an Apply replaces that, Apply takes two presses ("Apply anyway"), and "Read again from the editors" reads the
// file anew, asking first in the window about a draft not applied. The parts beside the rows that an Apply changed are
// named under the toolbar until a save sends them; the Applied message says Undo takes back the rows only - and, once the
// editors changed since, that it was applied earlier (branch record SIF-132).
// Record 7.203 (user: "yes build it", for rows older than the saved task):
//   - Save task sends which saved revision the rows came from: none before the page knows, then the revision of the
//     last save or of the rows Reload saved values brought; the check while editing gets it too;
//   - refused because the rows are older than the saved task, the page asks under the toolbar: "Save anyway" sends the
//     save again with replace_newer, "Reload saved values" brings the saved rows (and their revision).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; WSLENV carries the URL into it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/task_save_check.mjs)" [screenshot-dir]
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, TASK_PANEL, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('task');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const ROWS = [{ variable_id: 'wn', instance_path: 'XU1/MN1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005 }];
const PROBES = [{ measurement_id: 'm_osc_frequency_hz', analysis: 'tran', result_source: 'backend_profile', source_name: 'osc_frequency_hz', unit: 'Hz' }];
const SPECS = [{ metric_id: 'osc_frequency_hz', equation: 'm_osc_frequency_hz', unit: 'Hz', constraint: '>=', lower: 1.1e9, normalization_scale: 1e9 }];
const AUTO_BASELINE = '/fixture/new-task.baseline';
const tasksKnown = new Set(['real:ring_osc']);
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: true, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { MN1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: ['FIXTURE: a saved task.'] });
// Written as the backend writes it (task_files.render: two-space indents, `_help` first, a float as Python spells it).
const MAESTRO_HELP = 'The copy\'s Maestro test. Edit analyses (e.g. {"tran": {"stop": "50n"}}), variables ({"VSUP": "1.0"}), bindings and '
  + 'initial_conditions here. Outputs and specs come from the Probes and Specs rows. initial_conditions give nets a start voltage, which a '
  + 'circuit that does not start by itself needs.';
const fileText = (task, rows) => JSON.stringify({ _help: { 'what this is': 'The task file: everything this task is, in one place.', maestro: MAESTRO_HELP },
  format: 'gator-task-1', name: task,
  revision: 1, cell: { library: 'GPDK045_RINGOSC', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' },
  copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' },
  measurement: { kind: 'ring_oscillator', expected_frequency_hz: 1.2e9 }, maestro: { analyses: {}, variables: {}, bindings: [], model_files: [] },
  parameters: rows.parameters, probes: rows.measurements, specs: rows.targets, notes: '' }, null, 2)
  .replace('"expected_frequency_hz": 1200000000', '"expected_frequency_hz": 1200000000.0') + '\n';

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
    if (pathname === '/api/runs/status' && url.searchParams.get('run_dir') === AUTO_BASELINE)
      return fulfil(requestId, 200, { state: 'completed', run_id: 'auto-baseline', run_dir: AUTO_BASELINE, worker_alive: false,
        mode: 'scratch', mock: false, heartbeat_utc: '2026-10-07T12:00:00Z', active_workers: [], concurrency: 1,
        learner_updates: 0, stop_reason: 'budget_exhausted', error: null, calibration: null, save_point: null,
        budget: { charged: 1, completed: 1, failed: 0, max_evaluations: 1, launches: 1, remaining: 0 },
        paths: { run_dir: AUTO_BASELINE }, connection: { overall: 'not_applicable' },
        manifest: { mode: 'scratch', mock: false, seeds: { target_seed: 0 }, budgets: { max_evaluations: 1 } } });
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
        message: 'Another save is running (real:ring_osc, 5 s so far). Save as can be pressed again when it has ended.' } });
    }
    if (op === 'task/save' && hold) {
      saving = { running: runningAt('own', 2, 12), last: saving.last };
      await new Promise(resolve => { release = resolve; });
      saving = { running: null, last: { id: 'own', task_key: 'real:ring_osc', ok: true, seconds: 30, answer: { task_key: 'real:ring_osc', revision: revision + 1 } } };
    }
    if (op === 'task/save') {
      if (body.as_new) { tasksKnown.add(`real:${body.name}`); return fulfil(requestId, 200, { task_key: `real:${body.name}`, name: body.name, revision: 1, created: true, runnable: true,
        baseline: { state: 'started', run_dir: AUTO_BASELINE, run_id: 'auto-baseline', mock: false },
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
  const promptAnswers = [], prompts = [];
  page.on('Page.javascriptDialogOpening', p => {
    if (p.type === 'prompt') {
      const planned = promptAnswers.length > 0, answer = promptAnswers.shift();
      prompts.push({ message: p.message, defaultPrompt: p.defaultPrompt, planned });
      return send('Page.handleJavaScriptDialog', { accept: planned && answer !== null,
        ...(planned && answer !== null ? { promptText: answer === true ? p.defaultPrompt : answer } : {}) });
    }
    const accept = answers.length ? answers.shift() : null;
    dialogs.push({ message: p.message, planned: accept !== null });
    return send('Page.handleJavaScriptDialog', { accept: !!accept });
  });
  const PANEL = TASK_PANEL;
  const BLOCK = `document.querySelector('.editors .tabs .task-save')`;          // the bar: right end of the editors' tab line
  const NOTES = `document.querySelector('.editors .task-notes')`;              // its messages and questions, under the toolbar
  const BUTTON = text => `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const HEAD = `document.querySelector('.editors .tabs .task-head')`;          // the tab line's start: the task's name and revision (record 7.362)
  const headText = () => evaluate(`${HEAD}?.textContent ?? ''`);
  const notesText = () => evaluate(`${NOTES}?.textContent ?? ''`);
  const press = (label, gesture = false) => evaluate(`${BUTTON(label)}.click()`, gesture);
  const stored = page.stored;
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

  await page.intercept(['*/api/runs/status*', '*/api/virtuoso/*', '*/api/circuit/load', '*/api/tasks', '*/api/tasks/starter*', '*/api/tasks/saving', '*/api/config/validate'], answer,
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
  check('the open task names itself and its revision at the start of the tab line', (await headText()).includes('ring_osc') && (await headText()).includes('rev. 1'), await headText());
  check('two short buttons: Save as and Task file', await evaluate(`!!(${BUTTON('Save as')}) && !(${BUTTON('Save task')}) && !!(${BUTTON('Task file')})`));
  check('they sit at the end of the editors\' tab line, none in the circuit column', await evaluate(`!!${BLOCK}.closest('.tabs .tab-actions') && !document.querySelector('aside.left .task-save')
    && ![...document.querySelectorAll('aside.left button')].some(b => ['Save task', 'Save as', 'Task file'].includes(b.textContent.trim()))`));
  const place = await evaluate(`(() => { const bar = ${BLOCK}.getBoundingClientRect(), tabs = ${BLOCK}.closest('.tabs'), line = tabs.getBoundingClientRect();
    const first = tabs.querySelector('button').getBoundingClientRect();
    const modify = [...document.querySelectorAll('.editors .toolbar button')].pop().getBoundingClientRect();         // the toolbar's right end
    return { right: line.right - bar.right, sameLine: bar.top < first.bottom && bar.bottom > first.top, above: bar.bottom <= modify.top + 1,
             over: bar.left < modify.right && bar.right > modify.left }; })()`);
  check('on the tab line, at its right end, above the toolbar\'s last button', place.sameLine && place.right < 12 && place.above && place.over, JSON.stringify(place));
  check('only a person can press it, said on the button', await evaluate(`${BUTTON('Save as')}.title.includes('Only you can press it.')`));

  // ---- the task file in a window of its own ---------------------------------------------------------------------------------------
  await press('Task file', true); await settle(1500);
  check('"Task file" asks for the file of the current editors, once', calls.map(c => c.op).join() === 'task/file' && calls[0].task === 'ring_osc'
    && Array.isArray(calls[0].config?.targets), JSON.stringify(calls));
  // At the size the window asks for (a headless pop-up ignores it), so what is measured and photographed is what a person sees.
  const fileWindow = await browser.attach(await browser.window('GATOR - Task file of ring_osc (revision 1)', { except: page.target.id }), { errors: consoleErrors, prefix: 'file window: ' });
  await fileWindow.viewport(760, 900);
  const opened = await popupEval(`return d.querySelector('.task-file textarea')?.value ?? ''`);
  check('it opens in its own window, as one readable file: the text without its _help, every number as the backend wrote it (branch record SIF-81)',
    !opened.includes('"_help"') && opened.startsWith('{\n  "format": "gator-task-1",') && opened.includes('"specs"') && opened.includes('GPDK045_RINGOSC_GATOR')
    && opened.includes('"expected_frequency_hz": 1200000000.0'), opened.slice(0, 80));
  const help = await popupEval(`const list = d.querySelector('.task-file details.task-file-help'), box = d.querySelector('.task-file textarea');
    const dt = [...(list?.querySelectorAll('dt') ?? [])], long = list?.querySelectorAll('dd')[1], lines = long ? [...long.getClientRects()] : [];
    const revert = [...d.querySelectorAll('.task-file .row button')].find(b => b.textContent.trim() === 'Revert');
    return { open: !!list?.open, summary: list?.querySelector('summary').textContent, parts: dt.map(t => t.textContent).join('|'),
      says: long?.textContent, bold: dt[0] ? getComputedStyle(dt[0]).fontWeight : null, above: !!list && list.getBoundingClientRect().bottom <= box.getBoundingClientRect().top, lines: lines.length,
      hang: lines.length > 1 ? Math.round(lines[1].left - dt[1].getBoundingClientRect().left) : null,
      hint: d.querySelector('.task-file > .hint').textContent, revert: !!revert?.disabled }`);
  check('the _help part is a list over the text, open: each part in bold, its wrapped lines hanging in under it; the hint points there; Revert has nothing to undo (branch record SIF-81)',
    help.open && help.summary === 'What each part is' && help.parts === 'what this is|maestro' && Number(help.bold) >= 600 && help.says === MAESTRO_HELP && help.above
    && help.lines > 1 && help.hang >= 12 && help.hint.includes('What each part is, below, says what each part holds.') && !help.hint.includes('_help') && help.revert,
    JSON.stringify(help));
  const fills = await popupEval(`const b = [...d.querySelectorAll('.task-file .row button')].at(-1).getBoundingClientRect();
    return { title: d.querySelector('.task-file h3').textContent, gap: Math.round(w.innerHeight - b.bottom), scroll: d.documentElement.scrollHeight - w.innerHeight }`);
  check('its title names the task as the Tasks list does; its text fills the window, the buttons at the bottom, nothing scrolls (branch record SIF-26)',
    fills.title.startsWith('Task file of ring_osc') && fills.gap >= 0 && fills.gap < 40 && fills.scroll <= 0, JSON.stringify(fills));
  await fileWindow.shot(path.join(out, 'task-file.png'), `document.querySelector('.task-file')`);
  const edited = JSON.parse(opened);
  edited.specs[0].lower = 1.25e9; edited.maestro.analyses = { tran: { stop: '40n' } }; edited.notes = 'tighter';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(edited, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await settle();
  let config = await stored();
  for (let i = 0; i < 30 && config.targets[0].lower !== 1.25e9; i++) { await sleep(100); config = await stored(); }   // the page stores a moment later
  check('"Apply to editors" checks the file and fills the editors', calls.at(-1).op === 'task/file/check' && config.targets[0].lower === 1.25e9, JSON.stringify(config.targets));
  check('the window says what happened: the rows in the editors, the other parts sent with Save as, Undo taking back the rows only (SIF-93)',
    (await popupEval(`return d.querySelector('.task-file').textContent`)).includes('Applied: the editors now hold its rows, and Save as will send its other parts. Undo takes back the rows only.'));

  // branch record SIF-93: the file is a snapshot of the editors' rows; the parts beside the rows wait for the next save.
  const PENDING_LINE = 'From the task file, not saved yet: Maestro analyses, notes. Save as stores them; a reload or another task drops them.';
  const pendingText = () => evaluate(`${NOTES}?.querySelector('.task-file-pending')?.textContent ?? null`);
  const TOOL = text => `[...document.querySelectorAll('.editors .toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const FILE_BUTTON = text => `[...document.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const CHANGED = `document.querySelector('.task-file .editors-changed')`;
  const fileState = (win = fileWindow) => win.evaluate(`({ changed: ${CHANGED}?.textContent ?? null, apply: document.querySelector('.task-file .row button.primary')?.textContent.trim(),
    text: document.querySelector('.task-file textarea')?.value ?? '', kept: document.querySelector('.task-file .kept-draft')?.textContent ?? null })`);
  const short = state => JSON.stringify({ ...state, text: state.text.slice(0, 40) });
  const fileDialogs = [], fileAnswers = [];                                   // questions the file window asks, in that window
  const answerFileDialogs = async win => {                                    // a window opened again is another target
    await win.send('Page.enable');
    win.on('Page.javascriptDialogOpening', p => {
      const accept = fileAnswers.length ? fileAnswers.shift() : null;
      fileDialogs.push({ message: p.message, planned: accept !== null });
      return win.send('Page.handleJavaScriptDialog', { accept: !!accept });
    });
  };
  await answerFileDialogs(fileWindow);
  let state = await fileState();
  check('applied, the file holds the editors\' rows again: no "editors changed" line, Apply as it was (SIF-93)',
    state.changed === null && state.apply === 'Apply to editors', short(state));
  check('the parts beside the rows that the Apply changed are named under the toolbar, as not saved yet (SIF-93)', (await pendingText()) === PENDING_LINE, await notesText());
  await evaluate(`${TOOL('Undo')}.click()`);
  for (let i = 0; i < 30 && (await stored()).targets[0].lower !== 1.1e9; i++) await sleep(100);   // the page stores a moment later
  const CHANGED_SAYS = 'The editors changed since this file was read: Apply replaces those changes too (Undo in the editors takes it back).';
  check('changed in the editors since (their Undo), the window says an Apply replaces that and offers to read the file again (SIF-93)',
    await fileWindow.until(`!!${CHANGED}`, 30) && (state = await fileState()).changed.startsWith(CHANGED_SAYS) && state.changed.includes('Read again from the editors'), short(state));
  // Branch record SIF-132: "Applied: the editors now hold its rows" stood under that line.
  const APPLIED_LINE = `(document.querySelector('.task-file > p.ok')?.textContent ?? null)`;
  check('...and the Apply\'s line says it was earlier and the editors changed since; Save as still sends the other parts (SIF-132)',
    (await fileWindow.evaluate(APPLIED_LINE)) === 'Applied earlier; the editors changed since. Save as still sends its other parts.', await fileWindow.evaluate(APPLIED_LINE));
  await fileWindow.shot(path.join(out, 'task-file-editors-changed.png'), `document.querySelector('.task-file')`);
  let fileMark = calls.length;
  await fileWindow.evaluate(`${FILE_BUTTON('Apply to editors')}.click()`); await sleep(300);
  state = await fileState(); config = await stored();
  check('then the first press on Apply sends nothing and changes nothing: it turns into "Apply anyway" (SIF-93)', state.apply === 'Apply anyway' && calls.length === fileMark
    && config.targets[0].lower === 1.1e9, `${short(state)} ${config.targets[0].lower}`);
  await fileWindow.evaluate(`${FILE_BUTTON('Read again from the editors')}.click()`); await settle(1500);
  state = await fileState();
  check('"Read again from the editors" with nothing typed since the Apply asks nothing: the file of the editors now, the line gone, Apply as it was (SIF-93)',
    calls.slice(fileMark).map(c => c.op).join() === 'task/file' && calls.at(-1).config?.targets?.[0]?.lower === 1.1e9 && fileDialogs.length === 0
    && state.text.includes('"lower": 1100000000') && state.changed === null && state.apply === 'Apply to editors', short(state));
  const wider = JSON.parse(JSON.stringify(edited)); wider.parameters[0].upper = 1.7;
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(wider, null, 2));
  await evaluate(`${TOOL('Redo')}.click()`);
  await fileWindow.until(`!!${CHANGED}`, 30);
  fileMark = calls.length; fileAnswers.push(false);
  await fileWindow.evaluate(`${FILE_BUTTON('Read again from the editors')}.click()`); await sleep(400);
  state = await fileState();
  check('with a draft not applied, it asks first, in the file window; Cancel reads nothing and keeps the draft (SIF-93)',
    fileDialogs.at(-1)?.message === 'Read again from the editors? Your changes to this file are dropped.' && fileDialogs.at(-1)?.planned && calls.length === fileMark
    && state.text === JSON.stringify(wider, null, 2) && state.changed !== null, `${JSON.stringify(fileDialogs)} ${short(state)}`);
  await fileWindow.evaluate(`${FILE_BUTTON('Apply to editors')}.click()`); await sleep(300);
  check('Apply over the editors\' Redo: the first press sends nothing (SIF-93)', calls.length === fileMark && (await fileState()).apply === 'Apply anyway');
  await fileWindow.evaluate(`${FILE_BUTTON('Apply anyway')}.click()`); await settle();
  config = await stored();
  for (let i = 0; i < 30 && config.parameters[0].upper !== 1.7; i++) { await sleep(100); config = await stored(); }
  state = await fileState();
  check('"Apply anyway" applies: the editors hold the file\'s rows, the line goes, Apply as it was (SIF-93)', calls.at(-1).op === 'task/file/check'
    && config.parameters[0].upper === 1.7 && config.targets[0].lower === 1.25e9 && state.changed === null && state.apply === 'Apply to editors', short(state));
  check('...and its line is the fresh one, though the editors had changed before it (SIF-132)', (await fileWindow.evaluate(APPLIED_LINE))
    === 'Applied: the editors now hold its rows, and Save as will send its other parts. Undo takes back the rows only.', await fileWindow.evaluate(APPLIED_LINE));
  check('the parts waiting are still the file\'s analyses and notes (SIF-93)', (await pendingText()) === PENDING_LINE, await notesText());
  check('every question of the file window was planned (SIF-93)', fileDialogs.every(d => d.planned) && !fileAnswers.length, JSON.stringify(fileDialogs));
  edited.probes[0].analysis = 'sometimes';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(edited, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Apply to editors').click()`); await settle();
  config = await stored();
  check('a broken file is refused with its problems and changes nothing', (await popupEval(`return d.querySelector('.task-file .blocker')?.textContent ?? ''`)).includes('probes[0] analysis')
    && config.measurements[0].analysis === 'tran', config.measurements[0].analysis);
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);

  // branch record SIF-87: a close keeps the draft not applied (Close, the window's X - as the banner's Close all closes it). The
  // next press reads the file again and lays the draft over it, saying so; Revert drops it, and a draft reverted is not kept.
  const FILE_TITLE = 'GATOR - Task file of ring_osc (revision 1)';
  const KEPT_LINE = 'Your changes from before are kept, not applied yet. Revert drops them.';
  const brokenDraft = JSON.stringify(edited, null, 2);
  const fileShown = () => popupEval(`const revert = [...d.querySelectorAll('.task-file .row button')].find(b => b.textContent.trim() === 'Revert');
    return { text: d.querySelector('.task-file textarea')?.value ?? '', kept: d.querySelector('.task-file .kept-draft')?.textContent ?? null, revert: revert?.disabled ?? null }`);
  const reopenFile = async () => {
    await browser.window(FILE_TITLE, { present: false, except: page.target.id });       // closed: never ask window.open('', name) for it then
    const mark = calls.length;
    await press('Task file', true); await settle(1500);
    return { reads: calls.slice(mark).map(c => c.op).join(), ...(await fileShown()) };
  };
  let again = await reopenFile();
  check('closed with Close before Apply, the draft is kept: Task file reads the file again, shows the draft over it and says so (SIF-87)',
    again.reads === 'task/file' && again.text === brokenDraft && again.kept === KEPT_LINE && again.revert === false, JSON.stringify({ ...again, text: again.text.slice(0, 60) }));
  await send('Target.closeTarget', { targetId: (await browser.window(FILE_TITLE, { except: page.target.id })).id });   // the window's own X
  again = await reopenFile();
  check('...and so does the window\'s own X, the way the banner\'s Close all closes it (SIF-87)', again.reads === 'task/file' && again.text === brokenDraft && again.kept === KEPT_LINE,
    JSON.stringify({ ...again, text: again.text.slice(0, 60) }));
  await popupEval(`[...d.querySelectorAll('.task-file .row button')].find(b => b.textContent.trim() === 'Revert').click()`); await sleep(200);
  const reverted = await fileShown();
  check('Revert drops the kept draft: the file as read now, with the rows applied before, and the line goes (SIF-87)',
    reverted.text.startsWith('{\n  "format": "gator-task-1",') && reverted.text.includes('"lower": 1250000000') && !reverted.text.includes('sometimes')
    && reverted.kept === null && reverted.revert === true, JSON.stringify({ ...reverted, text: reverted.text.slice(0, 60) }));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);
  again = await reopenFile();
  check('a draft reverted before the close is not kept: the next press shows the file alone (SIF-87)', again.text === reverted.text && again.kept === null,
    JSON.stringify({ ...again, text: again.text.slice(0, 60) }));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);
  config = await stored();
  check('none of it changed the editors: the broken draft was never applied', config.measurements[0].analysis === 'tran' && config.targets[0].lower === 1.25e9,
    JSON.stringify({ analysis: config.measurements[0].analysis, lower: config.targets[0].lower }));

  // Review of SIF-93: a draft kept from a closed window was typed over the rows read before the close. Changed in the editors
  // while it was closed (their Undo), the window opened again lays the draft over a reading of the editors as they are now -
  // and still says they changed, because its Apply would put the older rows back.
  again = await reopenFile();
  const keptOver = JSON.parse(again.text); keptOver.notes = 'kept over';
  await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(keptOver, null, 2));
  await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);
  await evaluate(`${TOOL('Undo')}.click()`);
  for (let i = 0; i < 30 && (await stored()).parameters[0].upper !== 1.6; i++) await sleep(100);   // the Apply of upper 1.7 undone
  again = await reopenFile();
  const keptWindow = await browser.attach(await browser.window(FILE_TITLE, { except: page.target.id }), { errors: consoleErrors, prefix: 'file window: ' });
  await answerFileDialogs(keptWindow);
  state = await fileState(keptWindow);
  check('a draft kept while the editors changed: the window opened again shows it and says the editors changed since it was typed (review of SIF-93)',
    again.reads === 'task/file' && state.kept === KEPT_LINE && state.text === JSON.stringify(keptOver, null, 2) && !!state.changed?.startsWith(CHANGED_SAYS), short(state));
  fileMark = calls.length;
  await keptWindow.evaluate(`${FILE_BUTTON('Apply to editors')}.click()`); await sleep(300);
  check('...and its first Apply press sends nothing and changes nothing (review of SIF-93)', (await fileState(keptWindow)).apply === 'Apply anyway'
    && calls.length === fileMark && (await stored()).parameters[0].upper === 1.6);
  fileAnswers.push(true);
  await keptWindow.evaluate(`${FILE_BUTTON('Read again from the editors')}.click()`); await settle(1500);
  state = await fileState(keptWindow);
  check('"Read again from the editors" asks about the kept draft, reads the editors as they are now and drops it: the line goes (review of SIF-93)',
    fileDialogs.at(-1)?.message === 'Read again from the editors? Your changes to this file are dropped.' && fileDialogs.at(-1)?.planned && !fileAnswers.length
    && calls.slice(fileMark).map(c => c.op).join() === 'task/file' && calls.at(-1).config?.parameters?.[0]?.upper === 1.6
    && state.changed === null && state.kept === null && state.apply === 'Apply to editors' && !state.text.includes('kept over'), short(state));
  await keptWindow.evaluate(`${FILE_BUTTON('Close')}.click()`); await settle(600);
  await evaluate(`${TOOL('Redo')}.click()`);
  for (let i = 0; i < 30 && (await stored()).parameters[0].upper !== 1.7; i++) await sleep(100);

  const updateTask =() => evaluate(`window.dispatchEvent(new CustomEvent('gator-save-task-request', { detail: { task: 'real:ring_osc' } }))`);

  // ---- Calibration's explicit update: the next revision of the same task --------------------------------------------------------------------------------
  again = await reopenFile();                      // open through the save: the task stays, so the window does (review of SIF-93)
  let mark = calls.length;
  await updateTask(); await settle(1500);
  const saveCall = calls.slice(mark).find(c => c.op === 'task/save');
  check('before the page knows where its rows came from, Save task says none (7.203)', saveCall?.base_revision === null && saveCall?.replace_newer === false,
    JSON.stringify({ base: saveCall?.base_revision, replace: saveCall?.replace_newer }));
  check('Save task sends the rows, the open task and what the file added', !!saveCall && saveCall.task === 'ring_osc' && saveCall.name === 'ring_osc' && !saveCall.as_new
    && saveCall.extras?.analyses?.tran?.stop === '40n' && saveCall.config?.targets?.[0]?.lower === 1.25e9, JSON.stringify(saveCall ?? calls.slice(mark)));
  check('it reports the revision and that the baseline no longer holds, under the toolbar', (await notesText()).includes('Saved real:ring_osc, revision 2.') && (await notesText()).includes('no longer holds'), await notesText());
  check('sent, the file\'s other parts no longer wait: the line naming them goes (SIF-93)', (await pendingText()) === null, await notesText());
  // Review of SIF-93: an Apply from the window still open counts from what the save sent, not from the file read before the
  // save - the analyses and notes just saved are not named again; a row changed is applied as ever, and the editors' Undo
  // takes it back. The save put the backend's rows into the editors, so the window says they changed: Apply anyway.
  const stillOpen = (await browser.pages()).some(t => t.id !== page.target.id && t.title === FILE_TITLE);
  if (stillOpen) {                                 // never window.open('', name) for a window gone: it would open a blank one
    const savedUpper = (await stored()).parameters[0].upper;
    const afterSave = JSON.parse(again.text);
    afterSave.maestro.analyses = { tran: { stop: '40n' } }; afterSave.notes = 'tighter'; afterSave.parameters[0].upper = 1.65;
    await typeInto(`${POPUP}.document.querySelector('.task-file textarea')`, JSON.stringify(afterSave, null, 2));
    await popupEval(`d.querySelector('.task-file .row button.primary').click()`); await sleep(300);
    if ((await popupEval(`return d.querySelector('.task-file .row button.primary').textContent.trim()`)) === 'Apply anyway')
      await popupEval(`d.querySelector('.task-file .row button.primary').click()`);
    await settle();
    config = await stored();
    for (let i = 0; i < 30 && config.parameters[0].upper !== 1.65; i++) { await sleep(100); config = await stored(); }
    check('applied again after that save, from the window still open: the parts just saved are not named as waiting (review of SIF-93)',
      config.parameters[0].upper === 1.65 && (await pendingText()) === null, await notesText());
    await evaluate(`${TOOL('Undo')}.click()`);
    for (let i = 0; i < 30 && (await stored()).parameters[0].upper !== savedUpper; i++) await sleep(100);
    await popupEval(`[...d.querySelectorAll('.task-file button')].find(b => b.textContent.trim() === 'Close').click()`); await settle(600);
  } else check('the task file window stays open through the save of its own task (review of SIF-93)', false);
  await sleep(500);
  check('the open task shows its new revision', (await headText()).includes('rev. 2'), await headText());

  // Calibration still updates the current task through its explicit request.
  check('nothing under the toolbar asks for a new task name', !(await evaluate(`[...${NOTES}?.querySelectorAll('label') ?? []].some(l => l.firstChild?.textContent.trim() === 'New task name')`)));
  check('calibration update requests never create another task', calls.filter(c => c.op === 'task/save').every(c => c.as_new === false), JSON.stringify(calls.filter(c => c.op === 'task/save').map(c => c.as_new)));
  check('the tab line names the task and offers Check now, its tooltip saying the check runs before every run', (await headText()).includes('ring_osc')
    && (await evaluate(`[...${PANEL}.querySelectorAll('.tabs .tab-actions button')].some(b => b.textContent.trim() === 'Check now' && b.title.includes('first check that the editors'))`)));

  // ---- record 7.198: a running save shows its step and keeps Save task closed until it ends, also after a reload ----------
  const SAVE = `${BLOCK}?.querySelector('button.primary')`;                    // its caption says "Saving..." while one runs
  const LINE = `document.querySelector('.editors .task-notes .task-save-progress')`;
  const lineText = () => evaluate(`${LINE}?.textContent ?? ''`);
  const closed = () => evaluate(`${SAVE}?.disabled ?? null`);
  check('the page asked the backend about a running save when Save task appeared', statusReads >= 1, `${statusReads} reads`);
  hold = true; let reads = statusReads;
  await updateTask();
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
  check('its tooltip says what it waits for', (await evaluate(`${SAVE}.title`)).startsWith('Save as: Waits for the save of real:ring_osc that is running.'),
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
  check('it reads the task list again, so the task shows its new revision', await page.until(`(${HEAD}?.textContent ?? '').includes('rev. 4')`, 40)
    && taskListReads > listed, `${await headText()} | ${taskListReads - listed} reads`);
  check('Save task opens again after it', (await closed()) === false);

  // A press that meets another save (a stale page or another tab): refused by the backend, said, and followed.
  conflict = runningAt('tab', 2, 5);
  saves = calls.filter(c => c.op === 'task/save').length;
  await updateTask();
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
  await updateTask();
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
  await updateTask();
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
  await updateTask(); await settle(1500);
  check('then Save task starts from the revision those rows are', calls.filter(c => c.op === 'task/save').slice(sent)[0]?.base_revision === 9,
    JSON.stringify(calls.filter(c => c.op === 'task/save').slice(sent).map(c => c.base_revision)));

  // The main button creates another task. Cancellation, validation and collisions cannot overwrite the source.
  let count = calls.filter(c => c.op === 'task/save').length;
  promptAnswers.push(null);
  await press('Save as', true); await settle(700);
  check('Save as prompts with the original name plus numbering', prompts.at(-1)?.defaultPrompt === 'ring_osc_2', JSON.stringify(prompts.at(-1)));
  check('Cancel sends no save', calls.filter(c => c.op === 'task/save').length === count);
  tasksKnown.add('real:ring_osc_2');
  const sourceRevision = revision;
  promptAnswers.push(true);
  await press('Save as', true); await settle(1500); await sleep(1000);
  const copied = calls.filter(c => c.op === 'task/save').at(-1);
  check('the refreshed list skips occupied numbers', prompts.at(-1)?.defaultPrompt === 'ring_osc_3');
  check('Save as sends the new name and as_new, preserving the source revision', copied?.task === 'ring_osc' && copied?.name === 'ring_osc_3'
    && copied?.as_new === true && revision === sourceRevision, JSON.stringify(copied));
  check('the new task is selected after saving', (await stored()).circuit.task_id === 'real:ring_osc_3');
  check('task creation follows its automatic one-evaluation baseline in the header', await page.until(`localStorage.getItem('gator-workbench-current-run-v1') === ${JSON.stringify(AUTO_BASELINE)}`, 50));
  check('the creation prompt includes its one automatic simulation', /one baseline simulation automatically/.test(prompts.at(-1)?.message ?? ''));

  promptAnswers.push(null);
  await press('Save as', true); await settle(700);
  check('a numbered copy continues the original sequence', prompts.at(-1)?.defaultPrompt === 'ring_osc_4', JSON.stringify(prompts.at(-1)));
  count = calls.filter(c => c.op === 'task/save').length;
  promptAnswers.push('Bad name', 'ring_osc', 'custom_saved_task');
  await press('Save as', true); await settle(1500); await sleep(1000);
  const custom = calls.filter(c => c.op === 'task/save').slice(count);
  check('invalid and duplicate names are explained before any write', prompts.at(-2)?.message.includes('invalid')
    && prompts.at(-1)?.message.includes('already in use') && custom.length === 1);
  check('the typed name is used exactly and the new task is selected', custom[0]?.name === 'custom_saved_task'
    && custom[0]?.as_new === true && (await stored()).circuit.task_id === 'real:custom_saved_task');
  check('every naming prompt was planned', prompts.every(p => p.planned) && !promptAnswers.length, JSON.stringify(prompts));

  check('no unplanned dialog', dialogs.every(d => d.planned), JSON.stringify(dialogs));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
  await page.shot(path.join(out, 'task-save-1.png'));
  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
});
