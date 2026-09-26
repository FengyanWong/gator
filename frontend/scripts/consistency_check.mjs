// Browser check of the check before every run of a saved task (task flow part 4, backend consistency.py): "Check now" in
// the task's block (it replaced "Check against Virtuoso"), a failed step with what to do beside it and its reason folded,
// the result going once a row changes, and a Start the backend refused with code `consistency` showing the same steps in
// the banner - readable, not JSON. A throwaway headless Edge over the DevTools protocol against a workbench page
// (GATOR_WORKBENCH_URL for a preview of a temporary build). EVERY /api request is paused: the task list, the circuit
// load, validation, the run list, the check and the start are answered with canned FIXTURES; other reads pass; every
// other writing request is refused here - nothing is checked in Virtuoso, started or saved on the backend it runs against.
// Run (Windows node sees a WSL variable only when WSLENV names it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/consistency_check.mjs)"
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

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

try {
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
    if (pathname === '/api/runs/start') { calls.push({ path: pathname, ...body }); return fulfil(requestId, 409, { detail: REFUSED }); }
    if (request.method === 'GET' || (pathname === '/api/output/check' && !body.create)) return send('Fetch.continueRequest', { requestId });   // reads
    return page.readOrRefuse({ requestId, request }, refused);
  };
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Registered task'))`;
  const BUTTON = text => `[...(${PANEL}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const STEPS = `${PANEL}?.querySelector('.check-steps')`;
  const BANNER = `document.querySelector('.banner')`;
  const START = `[...document.querySelectorAll('header button')].find(b => b.textContent.trim() === 'Start')`;
  const shownText = el => evaluate(`(() => { const e = ${el}; return e && e.checkVisibility() ? e.innerText : ''; })()`);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 150 && !(await evaluate(`!!(${BUTTON('Check now')})`)); i++) await sleep(100);
  await sleep(1000);
  if (!(await evaluate(`!!(${BUTTON('Check now')})`))) console.log('DEBUG panel: ' + (await evaluate(`${PANEL}?.textContent.slice(0, 900) ?? 'no panel'`)) + '\nDEBUG errors: ' + consoleErrors.join(' | '));

  check('the task\'s block says the check runs before every run; "Check against Virtuoso" is gone', (await shownText(PANEL)).includes('Before every run:')
    && !(await evaluate(`!!(${BUTTON('Check against Virtuoso (no simulation)')})`)));
  check('what the check compares is one closed line', await evaluate(`(() => { const d = [...${PANEL}.querySelectorAll('details')].find(x => x.querySelector('summary')?.textContent === 'What the check compares');
    return !!d && !d.open && d.textContent.includes('no ADE/Maestro window may be open on the copy'); })()`));
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
  await evaluate(`${BUTTON('Load task')}.click()`);
  for (let i = 0; i < 30 && (await evaluate(`!!(${STEPS})`)); i++) await sleep(100);
  check('once a row changes, the old result goes', !(await evaluate(`!!(${STEPS})`)));
  // Start: the budget question first, then the backend refuses with code consistency - the banner lists the steps
  for (let i = 0; i < 30 && (await evaluate(`!${START} || ${START}.disabled`)); i++) await sleep(100);
  await evaluate(`${START}.click()`);
  for (let i = 0; i < 40 && !(await evaluate(`!!${BANNER}`)); i++) await sleep(100);
  const started = calls.filter(c => c.path === '/api/runs/start');
  check('Start asks for the budget, then sends one start', dialogs.some(d => d.includes('Authorize a budget')) && started.length === 1 && started[0].authorize_real_simulation === true,
    `${dialogs.join(' | ')} / ${started.length}`);
  const banner = await shownText(BANNER);
  check('a refused start lists the steps in words, once - no JSON, no repeated message line', banner.startsWith('Not started: real:ring_osc - one step does not agree.')
    && banner.includes('FAILED: The working copy in Virtuoso differs from the saved task.') && banner.split('undo the change in Virtuoso').length === 2
    && !(await evaluate(`!!${BANNER}.querySelector('pre')`)), banner.slice(0, 300));
  await evaluate(`[...${BANNER}.querySelectorAll('.check-steps summary')].find(x => x.textContent === 'the reason').click()`); await sleep(300);
  check('opening a reason inside the banner does not close it', await evaluate(`!!${BANNER}`) && (await shownText(BANNER)).includes('FIXTURE MN1'));
  await page.shot(path.join(out, 'consistency-2-start-refused.png'));
  check('no other writing request was made', refused.length === 0, refused.join(' | '));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
