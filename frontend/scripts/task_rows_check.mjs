// Browser check of "choosing a task brings that task's rows" in the Project panel (there is no frontend test runner).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). HERMETIC by default: the task list, every starter configuration, every
// circuit load and every validation are answered here with canned data labelled FIXTURE, other GET requests pass through
// and every other writing request is refused - so it is safe on the live backend, and works on one that was not restarted.
// With `--live` the task list, the starters, the loads and the validations go to the real backend instead (all read-only:
// local files, no bridge, no simulation); that backend must be a restarted or scratch one, and the numbers OF RECORD are checked.
// The browser profile is new and temporary: the user's saved configuration is not touched.
// What it pins (user report 2026-09-21: after choosing real:gpdk045_ota5 the Specs tab still showed the MOCK "score"):
// the rows of the three editors, the PDK / class labels and a starter-made project name follow the chosen task; one Undo
// takes all of it back; rows the user edited are kept and the button offers the exchange; a typed project name stays; an
// older backend is named as such; a circuit without targets of record says so and gets no invented target. Since status
// record 7.59: a configuration saved with one of the four removed MOCK tasks says so plainly, and choosing the one MOCK
// task left (synthetic:gpdk045_ota5) brings its rows and name at once.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/task_rows_check.mjs)" [--live] [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { validConfiguration, check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const LIVE = process.argv.includes('--live');                 // reads go to the backend; writing requests are refused either way
const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('taskrows');

// ---- canned answers (hermetic mode) -------------------------------------------------------------------------------
const parameter = (variable_id, instance_path, more) => ({ variable_id, instance_path, parameter_name: 'w', unit: 'm', scale: 'linear', value_type: 'continuous', ...more });
const probe = (metric, unit, analysis) => ({ measurement_id: `m_${metric}`, analysis, result_source: 'backend_profile', source_name: metric, unit, notes: 'FIXTURE' });
const BASIS = 'FIXTURE: pilot target of record';
const OTA_RESULTS = [['gain_db_at_start', 'dB', 'ac'], ['unity_gain_hz', 'Hz', 'ac'], ['supply_power_w', 'W', 'dc']];
const ota = (name, gain) => ({
  project: { name: name.replace(/_/g, '-'), task_name: name },
  circuit: { source: 'registered_task', task_id: `real:${name}`, circuit_class: 'opamp', pdk_id: 'gpdk045' },
  parameters: [parameter('input_pair_width', 'XU1/M1', { lower: 3.6e-6, upper: 4.4e-6, step: 5e-9, optimized: true, initial_value: 4e-6 }),
    parameter('input_pair_width__XU1_M2', 'XU1/M2', { binding_group: 'input_pair_width', ratio: 1, optimized: true })],
  measurements: OTA_RESULTS.map(r => probe(...r)),
  targets: [{ metric_id: 'gain_db_at_start', equation: 'm_gain_db_at_start', unit: 'dB', constraint: '>=', lower: gain, normalization_scale: 1, basis: BASIS },
    { metric_id: 'unity_gain_hz', equation: 'm_unity_gain_hz', unit: 'Hz', constraint: '>=', lower: 3540000, normalization_scale: 1e6, basis: BASIS },
    { metric_id: 'supply_power_w', equation: 'm_supply_power_w', unit: 'W', constraint: 'interval', lower: 0, upper: 2.1e-6, normalization_scale: 1e-6, basis: BASIS }] });
const MOCK = {
  project: { name: 'mock-gpdk045-ota5', task_name: 'mock_gpdk045_ota5' },
  circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'opamp', pdk_id: 'gpdk045' },
  parameters: [parameter('w_in', 'M1', { lower: 1e-6, upper: 8e-6, step: null, optimized: true }), parameter('w_in__M2', 'M2', { binding_group: 'w_in', ratio: 1 }),
    parameter('w_tail', 'M5', { lower: 1e-6, upper: 8e-6, step: null, optimized: true })],
  measurements: [probe('score', 'fixture', 'other')],
  targets: [{ metric_id: 'score', equation: 'm_score', unit: 'fixture', constraint: '>=', lower: 0.95, normalization_scale: 1, basis: 'FIXTURE: mock threshold' }],
  run: { max_evaluations: 60, seed: 17 } };
const RING = { project: { name: 'ring-demo', task_name: 'ring_demo' }, circuit: { source: 'registered_task', task_id: 'real:ring_demo', circuit_class: 'vco', pdk_id: 'gpdk045' },
  parameters: [parameter('wn', 'XU1/MN1', { lower: 6e-7, upper: 1.6e-6, step: 5e-9, optimized: true, initial_value: 1e-6 })],
  measurements: [probe('osc_frequency_hz', 'Hz', 'tran'), probe('supply_power_w', 'W', 'tran')], targets: [] };
const STARTERS = { 'synthetic:gpdk045_ota5': MOCK, 'real:gpdk045_ota5': ota('gpdk045_ota5', 25.01), 'real:gpdk045_ota7': ota('gpdk045_ota7', 53.3), 'real:ring_demo': RING };
const TASKS = [{ task_key: 'synthetic:gpdk045_ota5', kind: 'mock', circuit_class: 'opamp', pdk_id: 'gpdk045', available: true, starter_project: MOCK.project },
  ...['gpdk045_ota5', 'gpdk045_ota7'].map(n => ({ task_key: `real:${n}`, kind: 'real', circuit_class: 'opamp', pdk_id: 'gpdk045', available: true, blocker: null,
    starter_project: { name: n.replace(/_/g, '-'), task_name: n } })),
  { task_key: 'real:gpdk045_vco', kind: 'real', circuit_class: 'vco', available: true, blocker: null },        // as an OLDER backend lists it: no pdk_id, no starter, no names
  { task_key: 'real:ring_demo', kind: 'real', circuit_class: 'vco', pdk_id: 'gpdk045', generated: true, available: true, blocker: null, starter_project: RING.project }];
// A removed MOCK task (status record 7.59) loads as the backend answers it: not loaded, with its plain reason.
const REMOVED = ['synthetic:opamp', 'synthetic:opamp_two_stage', 'synthetic:ldo', 'synthetic:vco'];
const gone = taskId => ({ loaded: false, blocker: `${taskId} no longer exists: the workbench has one MOCK task now, synthetic:gpdk045_ota5 - FIXTURE`, interface_contract: null });
const loaded = taskId => REMOVED.includes(taskId) ? gone(taskId) : ({ loaded: true, task_key: taskId, mock: taskId.startsWith('synthetic:'), circuit: {}, content_sha256: null, provided_metrics: [], hierarchy: {},
  summary: { device_count: 0, devices: [], unknown_devices: [] }, complete: true, diagnostics: [], analysis_context: null, notes: [], evaluation_backend: 'FIXTURE',
  max_concurrency: 1, native_draft: false, generated_profile: false, baseline_recorded: null });
const VALID = validConfiguration({ facts: { circuit_checked: true, independent_action_variables: 1 } });

try {
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const starters = []; const loads = [];
  const answer = params => {
    const { requestId, request } = params, url = new URL(request.url), name = url.pathname, pass = () => page.pass(requestId);
    if (name === '/api/tasks/starter') starters.push(url.searchParams.get('task_key'));
    if (name === '/api/circuit/load') loads.push(JSON.parse(request.postData ?? '{}').circuit ?? {});
    if (LIVE) return name === '/api/circuit/load' || name === '/api/config/validate' ? pass() : page.readOrRefuse(params, refused);
    if (name === '/api/tasks') return fulfil(requestId, 200, { tasks: TASKS, real_interface_contract: {} });
    if (name === '/api/tasks/starter') { const s = STARTERS[url.searchParams.get('task_key')]; return s ? fulfil(requestId, 200, s) : fulfil(requestId, 404, { detail: 'No starter configuration for this task' }); }
    if (name === '/api/circuit/load') return fulfil(requestId, 200, loaded(loads[loads.length - 1].task_id ?? ''));
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    return page.readOrRefuse(params, refused);
  };
  const until = (expression, tries = 100) => page.until(expression, tries);
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Registered task'))`;
  const FIELD = label => `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)}).querySelector('input, select')`;
  const BUTTON = (scope, text) => `[...${scope}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const EDITORS = `document.querySelector('.editors')`;
  const value = label => evaluate(`${FIELD(label)}.value`);
  const choose = (label, v) => page.setValue(`${FIELD(label)}`, v);
  const setInput = (element, v) => page.setValue(`${element}`, v, { event: 'input' });
  const strip = () => evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].map(b => b.textContent.trim()).join(' | ')`);
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith(${JSON.stringify(name)})).click()`);
  const column = name => evaluate(`(() => { const head = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim()), at = head.indexOf(${JSON.stringify(name)});
    return [...${EDITORS}.querySelectorAll('table.editor tbody tr')].map(r => { const c = r.children[at]?.querySelector('input, select'); return c ? c.value : null; }); })()`);
  const note = () => evaluate(`${PANEL}.querySelector('.task-rows')?.textContent ?? ''`);
  const config = () => evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1000))`);   // the page saves 0.8 s after a change
  const shot = name => page.shot(path.join(out, name));

  await page.intercept(['*/api/*'], answer);
  // The page opens as the user's did: on the MOCK task, with the rows "Load task" had given it.
  const mock = LIVE ? await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json() : MOCK;
  const SEED = { schema_version: 'gator-workbench-config-v1', ...mock, run: { mode: 'scratch', concurrency: 1, threads_per_job: 1, ...mock.run }, output: { experiment_name: 'fixture' }, research: {} };
  await page.seed({ config: SEED, when: 'missing' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await until(`!!(${PANEL}) && ${FIELD('Task')}.options.length > 1`));
  await openTab('Specs');
  check('on the MOCK task the only spec is the toy score', JSON.stringify(await column('metric_id')) === '["score"]' && (await value('PDK id')) === 'gpdk045', await strip());
  check('nothing was fetched or exchanged by opening the page', starters.length === 0 && (await note()) === '', JSON.stringify(starters));

  // ---- the reported case: choose the real OTA ------------------------------------------------------------------------
  await choose('Task', 'real:gpdk045_ota5');
  check('the labels follow the task at once', (await value('PDK id')) === 'gpdk045' && (await value('Circuit class')) === 'opamp', `${await value('PDK id')} / ${await value('Circuit class')}`);
  check('the rows arrive and the panel says so', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`), await note());
  const metrics = await column('metric_id');
  check('Specs shows the circuit\'s own targets, not the score', !metrics.includes('score') && metrics.includes('gain_db_at_start') && metrics.includes('unity_gain_hz') && metrics.includes('supply_power_w'), JSON.stringify(metrics));
  // each spec is an equation over the probes; a starter's is the one probe of its own result (2026-09-21, status record 7.52)
  check('each spec\'s equation is the probe of its result', JSON.stringify(await column('equation')) === JSON.stringify(metrics.map(m => `m_${m}`)), JSON.stringify(await column('equation')));
  const probeLine = await evaluate(`${EDITORS}.querySelector('.spec-probes')?.textContent ?? ''`);
  check('the Specs tab names the Probe IDs an equation can use', /equation/.test(probeLine) && metrics.every(m => probeLine.includes(`m_${m}`)), probeLine || '(no line)');
  if (LIVE) {
    check('LIVE: the six targets of record, with their numbers', metrics.length === 6 && (await column('lower')).includes('25.01') && (await column('upper')).includes('0.0000021'), `${JSON.stringify(await column('lower'))} ${JSON.stringify(await column('upper'))}`);
    check('LIVE: five parameter rows and six probes', (await strip()) === 'Parameters (5) | Probes (6) | Specs (6)', await strip());
  } else check('the three tabs hold this task\'s rows', (await strip()) === 'Parameters (2) | Probes (3) | Specs (3)', await strip());
  const hard = await evaluate(`(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].findIndex(h => h.textContent.trim() === 'hard');
    return [...${EDITORS}.querySelectorAll('table.editor tbody tr')].map(r => r.children[at].querySelector('input').checked); })()`);
  check('what a row does not state is shown as the backend will take it: hard = on, tolerance = 0', hard.length > 0 && hard.every(Boolean) && (await column('tolerance')).every(t => t === '0'), `${JSON.stringify(hard)} ${JSON.stringify(await column('tolerance'))}`);
  check('every target states where it comes from', (await column('basis')).every(b => /of record/.test(b)), JSON.stringify((await column('basis')).slice(0, 1)));
  check('a starter-made project name follows, so a real run is not filed under mock_*', (await value('Name')) === 'gpdk045-ota5' && (await value('Task name')) === 'gpdk045_ota5', `${await value('Name')} / ${await value('Task name')}`);
  await openTab('Probes');
  check('Probes read the circuit\'s results', !(await column('source_name')).includes('score') && (await column('source_name')).includes('gain_db_at_start'), JSON.stringify(await column('source_name')));
  const saved = await config();
  check('the run settings were left alone', saved.run.max_evaluations === 60 && saved.run.seed === 17 && saved.circuit.task_id === 'real:gpdk045_ota5', JSON.stringify(saved.run));
  check('one load of the new task - the labels came with the choice, not as a second change', loads.filter(l => l.task_id === 'real:gpdk045_ota5').length === 1, `${loads.filter(l => l.task_id === 'real:gpdk045_ota5').length} load(s)`);
  await openTab('Specs'); await shot('task-rows-1-real-ota5.png');

  // ---- one Undo takes the choice and everything it brought back; Redo returns it ---------------------------------------
  await evaluate(`${BUTTON(EDITORS, 'Undo')}.click()`);
  check('ONE Undo: the MOCK task, its score, its labels and its name are back', await until(`${FIELD('Task')}.value === 'synthetic:gpdk045_ota5'`) && JSON.stringify(await column('metric_id')) === '["score"]'
    && (await value('PDK id')) === 'gpdk045' && (await value('Name')) === 'mock-gpdk045-ota5', `${await value('Task')} ${JSON.stringify(await column('metric_id'))} ${await value('PDK id')} ${await value('Name')}`);
  check('the note about another task is gone', (await note()) === '', await note());
  await evaluate(`${BUTTON(EDITORS, 'Redo')}.click()`);
  check('Redo: the real task with its rows again', await until(`${FIELD('Task')}.value === 'real:gpdk045_ota5'`) && (await column('metric_id')).includes('gain_db_at_start') && (await value('Name')) === 'gpdk045-ota5', JSON.stringify(await column('metric_id')));

  // ---- rows the user edited are kept; the button offers the exchange ----------------------------------------------------
  await setInput(`${EDITORS}.querySelector('table.editor tbody tr input.numeric')`, '26');
  check('an edit hides the "now show this task\'s rows" note', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '') === ''`), await note());
  await choose('Task', 'synthetic:gpdk045_ota5');
  check('edited rows stay, and the panel says whose they are', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('still hold the rows you edited')`) && (await note()).includes('real:gpdk045_ota5'), await note());
  check('the edited Specs are still there', (await column('metric_id')).includes('gain_db_at_start') && (await column('lower')).includes('26'), JSON.stringify(await column('lower')));
  check('labels and the starter-made name follow all the same', (await value('PDK id')) === 'gpdk045' && (await value('Name')) === 'mock-gpdk045-ota5', `${await value('PDK id')} / ${await value('Name')}`);
  await shot('task-rows-2-edited-rows-kept.png');
  await evaluate(`${BUTTON(PANEL, 'Load task')}.click()`);
  check('"Load task" exchanges them', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`) && JSON.stringify(await column('metric_id')) === '["score"]', JSON.stringify(await column('metric_id')));

  // ---- a name the user typed stays ---------------------------------------------------------------------------------------
  await setInput(FIELD('Name'), 'my-amplifier');
  await choose('Task', 'real:gpdk045_ota7');
  check('untouched MOCK rows are exchanged for the OTA7\'s', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`) && (await column('metric_id')).includes('gain_db_at_start'), await note());
  check(LIVE ? 'LIVE: the OTA7 has its own numbers (53.3 dB)' : 'the OTA7 has its own numbers', (await column('lower')).includes('53.3'), JSON.stringify(await column('lower')));
  check('a typed project name stays', (await value('Name')) === 'my-amplifier', await value('Name'));
  check('the button is there for a real task too', await evaluate(`!!${BUTTON(PANEL, 'Load task')}`));
  await setInput(`${EDITORS}.querySelector('table.editor tbody tr input.numeric')`, '54');
  await evaluate(`${BUTTON(PANEL, 'Load task')}.click()`);
  check('the button puts the task\'s own numbers back and keeps the typed name as well', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`)
    && (await column('lower')).includes('53.3') && !(await column('lower')).includes('54') && (await value('Name')) === 'my-amplifier', `${JSON.stringify(await column('lower'))} ${await value('Name')}`);

  if (!LIVE) {
    // ---- a circuit without targets of record: nothing is invented -----------------------------------------------------
    await choose('Task', 'real:ring_demo');
    check('a circuit without targets of record says so', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('no targets of record')`), await note());
    check('its parameters and probes are there, Specs is empty', (await strip()) === 'Parameters (1) | Probes (2) | Specs (0)', await strip());
    // ---- a backend that was not restarted ----------------------------------------------------------------------------------
    await choose('Task', 'real:gpdk045_vco');
    check('an older backend is named as such, in the panel', await until(`(${PANEL}.querySelector('.task-rows.error')?.textContent ?? '').includes('older than the page')`), await note());
    check('its rows are left as they were, the class label still follows', (await strip()) === 'Parameters (1) | Probes (2) | Specs (0)' && (await value('Circuit class')) === 'vco', await strip());
    await shot('task-rows-3-older-backend.png');
  }

  // ---- a configuration saved with a removed MOCK task (status record 7.59: four MOCK tasks became one) ---------------------
  // The user's own case: the page saved synthetic:vco with the rows and the project name its starter had given.
  const OLD = { schema_version: 'gator-workbench-config-v1', project: { name: 'mock-vco', task_name: 'mock_vco', notes: '' },
    circuit: { source: 'registered_task', task_id: 'synthetic:vco', circuit_class: 'vco', pdk_id: 'synthetic-fixture' },
    parameters: [parameter('stage_a_width', 'stage_a/pull_down', { lower: 1e-6, upper: 8e-6, optimized: true }),
      parameter('stage_a_width__stage_a_pull_up', 'stage_a/pull_up', { binding_group: 'stage_a_width', ratio: 1 })],
    measurements: [probe('score', 'fixture', 'other')], targets: [{ metric_id: 'score', equation: 'm_score', unit: 'fixture', constraint: '>=', lower: 0.95, normalization_scale: 1, basis: 'FIXTURE' }],
    run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 17 }, output: { experiment_name: 'fixture' }, research: {} };
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(OLD))})`);
  let mark = loads.length;
  await send('Page.reload');
  check('the page opens on the saved removed task', await until(`!!(${PANEL}) && ${FIELD('Task')}.options.length > 1 && ${FIELD('Task')}.value === 'synthetic:vco'`), await value('Task').catch(() => '?'));
  const removedOption = await evaluate(`(() => { const o = [...${FIELD('Task')}.options].find(o => o.value === 'synthetic:vco'); return o && [o.textContent, o.disabled]; })()`);
  check('the Task list shows it as removed, and it cannot be chosen again', JSON.stringify(removedOption) === JSON.stringify(['synthetic:vco (removed)', true]), JSON.stringify(removedOption));
  check('a plain note names the one MOCK task left', await until(`[...${PANEL}.querySelectorAll('.note')].some(n => n.textContent.includes('synthetic:vco no longer exists') && n.textContent.includes('synthetic:gpdk045_ota5'))`),
    await evaluate(`[...${PANEL}.querySelectorAll('.note')].map(n => n.textContent).join(' | ')`));
  for (let i = 0; i < 50 && !loads.slice(mark).some(l => l.task_id === 'synthetic:vco'); i++) await sleep(100);
  await sleep(400);                                                              // the load's answer is drawn
  check('no red "Blocked" box, and no "Load task" for a task that has none', !(await evaluate(`!!${PANEL}.querySelector('.blocker')`)) && !(await evaluate(`!!${BUTTON(PANEL, 'Load task')}`)));
  await shot('task-rows-4-removed-task.png');
  await choose('Task', 'synthetic:gpdk045_ota5');
  check('choosing the MOCK task brings its rows at once: a removed task\'s rows are nobody\'s work', await until(`(${PANEL}.querySelector('.task-rows')?.textContent ?? '').includes('now show this task')`)
    && (await strip()) === `Parameters (${mock.parameters.length}) | Probes (1) | Specs (1)`, `${await note()} ${await strip()}`);
  check('the old starter-made project name follows too', (await value('Name')) === 'mock-gpdk045-ota5' && (await value('Task name')) === 'mock_gpdk045_ota5', `${await value('Name')} / ${await value('Task name')}`);
  check('the removed entry and the note are gone', !(await evaluate(`[...${FIELD('Task')}.options].some(o => o.value === 'synthetic:vco')`))
    && !(await evaluate(`[...${PANEL}.querySelectorAll('.note')].some(n => n.textContent.includes('no longer exists'))`)));
  await evaluate(`${BUTTON(EDITORS, 'Undo')}.click()`);
  check('one Undo brings the saved state back', await until(`${FIELD('Task')}.value === 'synthetic:vco'`) && (await value('Name')) === 'mock-vco' && (await strip()).startsWith('Parameters (2)'), `${await value('Task')} ${await strip()}`);
  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect or call an agent on its own: never', !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/)/.test(r)), refused.join(', '));
  check('no console errors', consoleErrors.filter(e => !/404|418/.test(e)).length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
