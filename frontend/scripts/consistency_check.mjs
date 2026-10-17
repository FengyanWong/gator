// Browser check of the check before every run of a saved task (task flow part 4, backend consistency.py): "Check now" on
// the editors' tab line since record 7.362 (in the task's block until then; it replaced "Check against Virtuoso"), what the
// check does in its tooltip, a failed step with what to do beside it and its reason folded,
// the result going once a row changes, and a Start the backend refused with code `consistency` showing the same steps in
// the banner - readable, not JSON. A throwaway headless Edge over the DevTools protocol against a workbench page
// (GATOR_WORKBENCH_URL for a preview of a temporary build). EVERY /api request is paused: the task list, the circuit
// load, validation, the run list, the check and the start are answered with canned FIXTURES; other reads pass; every
// other writing request is refused here - nothing is checked in Virtuoso, started or saved on the backend it runs against.
// Run (Windows node sees a WSL variable only when WSLENV names it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/consistency_check.mjs)"
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, TASK_PANEL, taskWindow, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('consistency');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const TASK = 'real:ring_osc';
const ROW = { variable_id: 'wn', instance_path: 'XU1/MN1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005,
  value_type: 'continuous', scale: 'linear', notes: '' };
const PROBE = { measurement_id: 'm_osc_frequency_hz', analysis: 'tran', result_source: 'backend_profile', source_name: 'osc_frequency_hz', unit: 'Hz' };
const SPEC = { metric_id: 'osc_frequency_hz', equation: 'm_osc_frequency_hz', unit: 'Hz', constraint: '>=', lower: 1.1e9, normalization_scale: 1e9 };
const CONFIG = { schema_version: 'gator-workbench-config-v1', project: { name: 'ring-osc', task_name: 'ring_osc', notes: '' },
  circuit: { source: 'registered_task', task_id: TASK, circuit_class: 'vco', pdk_id: 'gpdk045' }, parameters: [ROW], measurements: [PROBE], targets: [SPEC],
  run: { mode: 'scratch', max_evaluations: 3, concurrency: 1, threads_per_job: 1, seed: 0, connection_profile_id: 'lab' },
  output: { experiment_name: 'fixture' }, research: {} };
const TASKS = { tasks: [{ task_key: TASK, kind: 'real', generated: true, available: true, revision: 2, circuit_class: 'vco', pdk_id: 'gpdk045',
  library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', starter_project: { name: 'ring-osc', task_name: 'ring_osc' }, description: 'FIXTURE' }] };
const LOADED = { loaded: true, task_key: TASK, mock: false, native_draft: false, generated_profile: true, baseline_recorded: true, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { MN1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: [] };
const STEP = (step, ok, title, extra = {}) => ({ step, ok, title, detail: `FIXTURE: ${step}`, ...extra });
const DRIFT = 'ValueError: FIXTURE MN1 w=1.1u in Virtuoso, 1u saved';
const FIX = 'The working copy was changed in Virtuoso after the task was saved: press Save task to take the copy as it is now, or undo the change in Virtuoso.';
const FAILED_CHECK = { consistency_check: true, task: TASK, revision: 2, ok: false, simulated: false, steps: [
  STEP('editors', true, 'The editors hold the rows of the saved task'), STEP('connect', true, 'The run adapter reaches the working copy'),
  STEP('export', false, 'The working copy in Virtuoso differs from the saved task', { detail: DRIFT, fix: FIX })] };
const REFUSED = { message: `Not started: the working copy in Virtuoso differs from the saved task. ${DRIFT} ${FIX}`, code: 'consistency',
  report: { ...FAILED_CHECK, steps: FAILED_CHECK.steps.slice(1) } };
const OTHER_REFUSAL = { message: 'FIXTURE: not started for another reason.', code: 'fixture_refused', report: { fixture: 'FIXTURE_REPORT' } };

await runChecks(browser, async () => {
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, fulfil } = page;
  const calls = []; const refused = []; const dialogs = [];
  const answer = async ({ requestId, request }) => {
    const url = new URL(request.url), pathname = url.pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/tasks') return fulfil(requestId, 200, TASKS);
    if (pathname === '/api/tasks/starter') return fulfil(requestId, 200, { project: CONFIG.project, circuit: CONFIG.circuit,
      parameters: [{ ...ROW, upper: 1.5 }], measurements: [PROBE], targets: [SPEC] });            // the SAVED rows differ from the page's
    if (pathname === '/api/circuit/load') return body.circuit?.task_id === TASK ? fulfil(requestId, 200, LOADED) : send('Fetch.continueRequest', { requestId });
    if (pathname === '/api/config/validate') return fulfil(requestId, 200, { blocks_run: false, issues: [], facts: {} });
    if (pathname === '/api/runs' && request.method === 'GET') return fulfil(requestId, 200, { runs: [] });
    if (pathname === '/api/virtuoso/task/check') { calls.push({ path: pathname, ...body }); await sleep(300); return fulfil(requestId, 200, FAILED_CHECK); }
    if (pathname === '/api/runs/start') {         // the first start: the check's steps; a second one: any other refusal with a report
      calls.push({ path: pathname, ...body });
      return fulfil(requestId, 409, { detail: calls.filter(c => c.path === pathname).length > 1 ? OTHER_REFUSAL : REFUSED });
    }
    if (request.method === 'GET' || (pathname === '/api/output/check' && !body.create)) return send('Fetch.continueRequest', { requestId });   // reads
    return page.readOrRefuse({ requestId, request }, refused);
  };
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const PANEL = TASK_PANEL;
  const BUTTON = text => `[...(${PANEL}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const STEPS = `${PANEL}?.querySelector('.check-steps')`;
  const BANNER = `document.querySelector('.banner')`;
  // A refused start stays on a line of its own under the header (record 7.261), no longer in the passing banner.
  const REFUSAL = `document.querySelector('header .launch-refusal')`;
  const START = `[...document.querySelectorAll('header button')].find(b => b.textContent.trim() === 'Start')`;
  const shownText = el => evaluate(`(() => { const e = ${el}; return e && e.checkVisibility() ? e.innerText : ''; })()`);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 150 && !(await evaluate(`!!(${BUTTON('Check now')})`)); i++) await sleep(100);
  await sleep(1000);
  if (!(await evaluate(`!!(${BUTTON('Check now')})`))) console.log('DEBUG panel: ' + (await evaluate(`${PANEL}?.textContent.slice(0, 900) ?? 'no panel'`)) + '\nDEBUG errors: ' + consoleErrors.join(' | '));

  // Record 7.362 (the user's Option D): Check now stands on the editors' tab line, before Save task; the task's block said "Before
  // every run: ..." and folded "What the check compares" - both are its tooltip now.
  const checkNow = await evaluate(`(() => { const b = ${BUTTON('Check now')}; return { onTabLine: !!b?.closest('.editors > .tabs .tab-actions'), title: b?.title ?? '' }; })()`);
  check('Check now stands on the editors\' tab line, its tooltip says the check runs before every run; "Check against Virtuoso" is gone',
    checkNow.onTabLine && checkNow.title.includes('Start, Calibration and Resume first check that the editors, this saved task and its cell in Virtuoso agree')
    && !(await evaluate(`!!(${BUTTON('Check against Virtuoso (no simulation)')})`)), JSON.stringify(checkNow).slice(0, 200));
  check('what the check compares is in that tooltip too', checkNow.title.includes('no ADE/Maestro window may be open on the copy')
    && checkNow.title.includes("the cell's Maestro test with the task"));
  check('nothing is checked on page load', calls.length === 0, JSON.stringify(calls));
  await evaluate(`${BUTTON('Check now')}.click()`);
  await sleep(100);
  check('the button says it is working', (await evaluate(`[...${PANEL}.querySelectorAll('button')].some(b => b.textContent.trim() === 'Checking...')`)));
  for (let i = 0; i < 30 && !(await evaluate(`!!(${STEPS})`)); i++) await sleep(100);
  const sent = calls.filter(c => c.path === '/api/virtuoso/task/check');
  check('"Check now" sends one check with this connection and the editors\' rows', sent.length === 1 && sent[0].profile_id === 'lab' && sent[0].config?.circuit?.task_id === TASK
    && sent[0].config?.parameters?.[0]?.upper === 1.6, JSON.stringify(sent).slice(0, 200));
  const steps = await shownText(STEPS);
  check('each step is one line: passed, and the failed one with what to do beside it', steps.includes('passed: The editors hold the rows of the saved task.')
    && steps.includes('FAILED: The working copy in Virtuoso differs from the saved task.') && steps.includes('press Save task to take the copy as it is now')
    && steps.includes('real:ring_osc - one step does not agree, so a run would not start. Nothing was simulated.'), steps.slice(0, 300));
  check('the reason is folded until asked for', !(await evaluate(`[...${STEPS}.querySelectorAll('details p')].find(p => p.textContent.includes('FIXTURE MN1')).checkVisibility()`)));
  await page.shot(path.join(out, 'consistency-1-check-now.png'));
  // the rows change (the saved rows come back): the result was about the rows before, so it goes
  const tasks = taskWindow(page, browser);
  await tasks.choose(TASK);
  await tasks.close();
  for (let i = 0; i < 30 && (await evaluate(`!!(${STEPS})`)); i++) await sleep(100);
  check('once a row changes, the old result goes', !(await evaluate(`!!(${STEPS})`)));
  // Start: the budget question first, then the backend refuses with code consistency - the refusal line lists the steps
  for (let i = 0; i < 30 && (await evaluate(`!${START} || ${START}.disabled`)); i++) await sleep(100);
  await evaluate(`${START}.click()`);
  for (let i = 0; i < 40 && !(await evaluate(`!!${REFUSAL}`)); i++) await sleep(100);
  const started = calls.filter(c => c.path === '/api/runs/start');
  check('Start asks for the budget, then sends one start', dialogs.some(d => d.includes('Authorize a budget')) && started.length === 1 && started[0].authorize_real_simulation === true,
    `${dialogs.join(' | ')} / ${started.length}`);
  const banner = await shownText(REFUSAL);
  check('a refused start lists the steps in words, once - no JSON, no repeated message line', banner.startsWith('Not started: real:ring_osc - one step does not agree.')
    && banner.includes('FAILED: The working copy in Virtuoso differs from the saved task.') && banner.split('undo the change in Virtuoso').length === 2
    && !(await evaluate(`!!${REFUSAL}.querySelector('pre')`)) && !(await evaluate(`!!${BANNER}`)), banner.slice(0, 300));
  await evaluate(`[...${REFUSAL}.querySelectorAll('.check-steps summary')].find(x => x.textContent === 'the reason').click()`); await sleep(300);
  check('opening a reason inside the refusal line does not close it', await evaluate(`!!${REFUSAL}`) && (await shownText(REFUSAL)).includes('FIXTURE MN1'));
  await page.shot(path.join(out, 'consistency-2-start-refused.png'));
  // Any other refusal says the backend's sentence and folds its code and report under "Technical details" (7.125: the code
  // used to lead the banner) - which opens without closing the line (2026-09-29: before, the
  // banner's own close-on-click took that click too, and the fold could never be opened). Since 7.261 the line names the action.
  const FOLD = `${REFUSAL}?.querySelector('details')`;
  await evaluate(`${START}.click()`);
  // Wait for THIS refusal's words (record 7.265): the first refusal's steps hold folds of their own, and a fold found before the
  // new line had come took the click below (the check flaked about once in six). A new press clears the old reason now as well.
  for (let i = 0; i < 60 && !(await evaluate(`(${REFUSAL}?.innerText ?? '').startsWith('Start was refused: FIXTURE: not started for another reason.') && !!${FOLD}`)); i++) await sleep(100);
  await evaluate(`${FOLD}.querySelector('summary').click()`); await sleep(300);
  check('another refusal with a report: "details" opens and the line stays', await evaluate(`!!${FOLD} && ${FOLD}.open`)
    && (await shownText(FOLD)).includes('FIXTURE_REPORT') && (await shownText(FOLD)).includes('code: fixture_refused')
    && (await shownText(REFUSAL)).startsWith('Start was refused: FIXTURE: not started for another reason.'),
    (await shownText(REFUSAL)).replace(/\s+/g, ' ').slice(0, 200));
  check('no other writing request was made', refused.length === 0, refused.join(' | '));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
});
