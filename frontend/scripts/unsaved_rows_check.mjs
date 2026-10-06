// Browser check of the editors' marks for rows not saved in the task (record 7.222, user: "In the parameter probe and spec
// windows, highlight the rows that are unsaved"). A throwaway headless Edge over the DevTools protocol against a workbench
// page (GATOR_WORKBENCH_URL for a preview of a temporary build). The task list, the circuit load, the starting rows,
// validation, the save state and Save task are answered with canned FIXTURES - validation names the rows that differ from
// the fixture's saved rows field by field, as the backend does (consistency.unsaved_rows); other reads pass; every other
// writing request is refused here: nothing is saved on the backend it runs against. What it pins:
//   - a changed row is tinted and its changed cells more, a new row in the colour of an added row, both with a bar at their
//     start; an error row keeps its own colour; in both looks, read from the page's own colour names;
//   - the tick-box cell says what changed and what the task holds (a column not in view too); a changed cell's tooltip
//     starts with the saved value, written as the cell writes it (1.5 um, 1 GHz, ≥ lower);
//   - a tab holding such rows carries a dot, its tooltip counts them and names the saved rows deleted here; a tie toggle
//     whose folded rows are not saved takes the colour; a table whose rows are all saved has neither;
//   - typing the saved value back takes the mark away, a new edit brings one;
//   - Save task: validation is asked again although the rows did not change, and every mark goes; a save that ended
//     elsewhere (followed after a reload) brings the marks of the rows it left behind;
//   - a report without them (a task that is not saved) marks nothing.
// Run (Windows node sees a WSL variable only when WSLENV names it):
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/unsaved_rows_check.mjs)" [screenshot-dir]
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('unsaved');
const consoleErrors = [];

// ---- canned answers ------------------------------------------------------------------------------------------
const TASK = 'real:ring_osc';
const W = (id, more = {}) => ({ variable_id: id, instance_path: `XU1/M${id.toUpperCase()}`, parameter_name: 'w', unit: 'um', optimized: true,
  lower: 0.3, upper: 1.6, step: 0.005, value_type: 'continuous', scale: 'linear', notes: '', ...more });
const PROBE = { measurement_id: 'm_osc_frequency_hz', analysis: 'tran', result_source: 'backend_profile', source_name: 'osc_frequency_hz', unit: 'Hz' };
const SPEC = { metric_id: 'osc_frequency_hz', equation: 'm_osc_frequency_hz', unit: 'Hz', constraint: '>=', lower: 1.1e9, normalization_scale: null,
  direction_after_feasible: 'maximize' };
// The page's rows: wn changed (upper), wp as saved, wp2 tied to wp and changed (folded under it), w_new new, lerr changed
// with an error of its own; the Probe as saved; the Spec changed (its lower, its objective and its Scale, a column behind
// More columns), and a saved Spec deleted.
const ROWS = { parameters: [W('wn'), W('wp'), W('wp2', { binding_group: 'wp', ratio: 1 }), W('w_new'), W('lerr')], measurements: [PROBE], targets: [SPEC] };
let saved = { parameters: [W('wn', { upper: 1.5 }), W('wp'), W('wp2', { binding_group: 'wp', ratio: 2 }), W('lerr', { lower: 0.2 })], measurements: [PROBE],
  targets: [{ ...SPEC, lower: 1e9, normalization_scale: 2e8, direction_after_feasible: 'none' }, { ...SPEC, metric_id: 'old_spec' }] };
const CONFIG = { schema_version: 'gator-workbench-config-v1', project: { name: 'ring-osc', task_name: 'ring_osc', notes: '' },
  circuit: { source: 'registered_task', task_id: TASK, circuit_class: 'vco', pdk_id: 'gpdk045' }, ...ROWS,
  run: { mode: 'scratch', max_evaluations: 3, concurrency: 1, seed: 0, connection_profile_id: 'lab' }, output: { experiment_name: 'fixture' }, research: {} };
let revision = 4;
const TASKS = () => ({ tasks: [{ task_key: TASK, kind: 'real', generated: true, available: true, revision, circuit_class: 'vco', pdk_id: 'gpdk045',
  library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', starter_project: { name: 'ring-osc', task_name: 'ring_osc' }, description: 'FIXTURE' }] });
const LOADED = { loaded: true, task_key: TASK, mock: false, native_draft: false, generated_profile: true, baseline_recorded: true, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { MWN: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: [] };
// What validation says of the rows, as consistency.unsaved_rows does: per table the rows new here, deleted here, changed
// (each changed field's saved value and the saved row's unit) and whether the same rows stand in another order.
const KEYS = { parameters: 'variable_id', measurements: 'measurement_id', targets: 'metric_id' };
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const unsavedRows = config => ({ revision, sections: Object.fromEntries(Object.entries(KEYS).map(([section, key]) => {
  const now = new Map((config[section] ?? []).map(r => [r[key], r])), then = new Map((saved[section] ?? []).map(r => [r[key], r]));
  const changed = {};
  for (const [id, row] of now) {
    const before = then.get(id);
    if (!before) continue;
    const fields = Object.fromEntries([...new Set([...Object.keys(row), ...Object.keys(before)])].filter(f => !same(row[f], before[f])).map(f => [f, before[f] ?? null]));
    if (Object.keys(fields).length) changed[id] = { fields, unit: before.unit ?? null };
  }
  const common = (a, b) => [...a.keys()].filter(id => b.has(id));
  return [section, { added: [...now.keys()].filter(id => !then.has(id)), removed: [...then.keys()].filter(id => !now.has(id)), changed,
    reordered: !same(common(now, then), common(then, now)) }];
})) });
const STEPS = [{ id: 'setup', title: 'Virtuoso writes the Maestro test into the cell and reads it back' }, { id: 'files', title: 'Writing the task files and checking them' }];

await runChecks(browser, async () => {
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, fulfil } = page;
  const validations = [], saves = [];
  let noSavedTask = false, saving = { running: null, last: null };
  const answer = async ({ requestId, request }) => {
    const url = new URL(request.url), pathname = url.pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/tasks') return fulfil(requestId, 200, TASKS());
    if (pathname === '/api/tasks/starter') return fulfil(requestId, 200, { project: CONFIG.project, circuit: CONFIG.circuit, ...saved, revision });
    if (pathname === '/api/tasks/saving') return fulfil(requestId, 200, saving);
    if (pathname === '/api/circuit/load') return body.circuit?.task_id === TASK ? fulfil(requestId, 200, LOADED) : send('Fetch.continueRequest', { requestId });
    if (pathname === '/api/config/validate') {
      validations.push(body.config);
      const lerr = (body.config.parameters ?? []).findIndex(r => r.variable_id === 'lerr');
      const issues = lerr >= 0 ? [{ level: 'error', code: 'fixture_error', path: `parameters[${lerr}].lower`, message: 'FIXTURE: an error of this row' }] : [];
      return fulfil(requestId, 200, { blocks_run: issues.length > 0, counts: {}, issues, facts: {}, unsaved_rows: noSavedTask ? null : unsavedRows(body.config) });
    }
    if (pathname === '/api/virtuoso/task/save') {            // the save stores the rows it was sent: they are the saved rows now
      saves.push(body);
      revision += 1;
      saved = { parameters: body.config.parameters, measurements: body.config.measurements, targets: body.config.targets };
      return fulfil(requestId, 200, { task_key: TASK, name: 'ring_osc', revision, created: false, runnable: true, circuit_class: 'vco', pdk_id: 'gpdk045',
        parameters: body.config.parameters, baseline_kept: true, changed: [], copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' } });
    }
    return page.readOrRefuse({ requestId, request }, page.refused, { reads: true });
  };
  const ROW = (id, field) => `[...document.querySelectorAll('.editors table.editor tbody tr')].find(tr => tr.querySelector('td[data-field="${field}"] input')?.value === ${JSON.stringify(id)})`;
  const PROW = id => ROW(id, 'variable_id'), SROW = id => ROW(id, 'metric_id');
  const TAB = name => `document.querySelector('.editors .tabs > button[data-editor="${name}"]')`;
  const BOX = (row, field) => `${row}?.querySelector('td[data-field="${field}"] :is(input, select)')`;
  const cls = expression => evaluate(`(${expression})?.className ?? null`);
  const title = expression => evaluate(`(${expression})?.title ?? null`);
  const bg = expression => evaluate(`getComputedStyle(${expression}).backgroundColor`);
  const colour = name => evaluate(`(() => { const d = document.createElement('div'); d.style.background = 'var(${name})'; document.body.append(d);
    const c = getComputedStyle(d).backgroundColor; d.remove(); return c; })()`);
  const marked = () => evaluate(`[...document.querySelectorAll('.editors table.editor tbody tr')].filter(tr => /unsaved-/.test(tr.className)).length`);
  const tab = async name => { await evaluate(`${TAB(name)}.click()`); await sleep(300); };
  const typeIn = async (box, text) => { await page.setValue(box, text, { event: 'input', focus: true }); await evaluate(`${box}.blur()`); };
  const BAR = `[...document.querySelectorAll('.editors .tabs .task-save button')].find(b => b.textContent.trim() === 'Save task')`;
  const NOTES = `document.querySelector('.editors .task-notes')`;

  await page.intercept(['*/api/tasks', '*/api/tasks/starter*', '*/api/tasks/saving', '*/api/circuit/load', '*/api/config/validate', '*/api/virtuoso/*'], answer,
    { others: 'read', connection: 'lab' });
  await page.seed({ config: CONFIG, when: 'once' });
  await send('Page.navigate', { url: APP });
  const first = await page.until(`!!(${PROW('wn')}) && /unsaved-/.test(${PROW('wn')}.className)`, 150);
  if (!first) console.log('DEBUG: ' + (await evaluate(`document.querySelector('.editors')?.textContent.slice(0, 600) ?? 'no editors'`)) + ' | ' + consoleErrors.join(' | '));

  // ---- Parameters: which rows, which cells, what they say ------------------------------------------------------------
  check('a changed row is marked, and only its changed cell', /\bunsaved-changed\b/.test(await cls(PROW('wn')))
    && /\bunsaved-cell\b/.test(await cls(`${PROW('wn')}.querySelector('td[data-field="upper"]')`))
    && !/unsaved-cell/.test(await cls(`${PROW('wn')}.querySelector('td[data-field="lower"]')`) ?? ''), await cls(PROW('wn')));
  check('a row as saved is not marked; a new row is marked as new, no cell of it', !/unsaved/.test(await cls(PROW('wp')) ?? '')
    && /\bunsaved-new\b/.test(await cls(PROW('w_new'))) && !(await evaluate(`!!${PROW('w_new')}.querySelector('td.unsaved-cell')`)));
  check('the tick-box cell says what changed and what the task holds', await title(`${PROW('wn')}.querySelector('td.sel')`) === 'Changed since the task was saved: Upper (saved: 1.5 um).'
    && await title(`${PROW('w_new')}.querySelector('td.sel')`) === 'New row, not in the saved task: Save task stores it.', await title(`${PROW('wn')}.querySelector('td.sel')`));
  check('a changed cell\'s tooltip starts with the saved value, written as the cell writes it', (await title(BOX(PROW('wn'), 'upper'))).startsWith('Saved in the task: 1.5 um.\n')
    && !(await title(BOX(PROW('wn'), 'lower')) ?? '').startsWith('Saved'), await title(BOX(PROW('wn'), 'upper')));
  const toggle = `${PROW('wp')}.querySelector('.tie-toggle')`;
  check('a tie toggle whose folded rows are not saved takes the colour and says so', /\bunsaved\b/.test(await cls(toggle))
    && (await title(toggle)).endsWith('1 of them is not saved in the task.') && await evaluate(`${PROW('wp2')}.hidden`), await title(toggle));
  check('an error row keeps its colour, its changed cell marked', /\bhas-error\b/.test(await cls(PROW('lerr'))) && /\bunsaved-changed\b/.test(await cls(PROW('lerr')))
    && await bg(`${PROW('lerr')}.querySelector('td[data-field="upper"]')`) === await colour('--bad-row')
    && await bg(`${PROW('lerr')}.querySelector('td[data-field="lower"]')`) === await colour('--unsaved-cell'));
  check('the tabs: Parameters and Specs carry the dot with a count, Probes none', /\bhas-unsaved\b/.test(await cls(TAB('parameters')))
    && (await title(TAB('parameters'))).startsWith('Not saved in the task: 3 changed, 1 new. Save task stores the rows as they are')
    && /\bhas-unsaved\b/.test(await cls(TAB('targets'))) && (await title(TAB('targets'))).startsWith('Not saved in the task: 1 changed, 1 saved row deleted here (old_spec).')
    && !/has-unsaved/.test(await cls(TAB('measurements'))) && !(await title(TAB('measurements'))),
    `${await title(TAB('parameters'))} / ${await title(TAB('targets'))}`);
  const dot = await evaluate(`(() => { const s = getComputedStyle(${TAB('parameters')}, '::after'); return [s.content, s.backgroundColor, s.borderRadius]; })()`);
  check('the dot is the mark colour, round', dot[0] !== 'none' && dot[1] === await colour('--unsaved-mark') && dot[2] === '50%', JSON.stringify(dot));
  for (const look of ['whiteprint', 'silicon']) {
    await evaluate(`document.documentElement.dataset.theme = '${look}'`); await sleep(200);
    const want = { row: await colour('--unsaved-row'), cell: await colour('--unsaved-cell'), added: await colour('--added-bg'), mark: await colour('--unsaved-mark'), addedMark: await colour('--added-mark') };
    const got = { row: await bg(`${PROW('wn')}.querySelector('td[data-field="lower"]')`), id: await bg(`${PROW('wn')}.querySelector('td[data-field="variable_id"]')`),
      cell: await bg(`${PROW('wn')}.querySelector('td[data-field="upper"]')`), added: await bg(`${PROW('w_new')}.querySelector('td[data-field="upper"]')`),
      plain: await bg(`${PROW('wp')}.querySelector('td[data-field="upper"]')`), bar: await evaluate(`getComputedStyle(${PROW('wn')}.querySelector('td.sel')).boxShadow`),
      addedBar: await evaluate(`getComputedStyle(${PROW('w_new')}.querySelector('td.sel')).boxShadow`) };
    check(`${look}: a changed row (its ID too) and its changed cell in their colours, a new row in the added colour, bars at their start`,
      got.row === want.row && got.id === want.row && got.cell === want.cell && got.added === want.added && ![want.row, want.cell, want.added].includes(got.plain)
      && got.bar.includes(want.mark) && got.addedBar.includes(want.addedMark) && new Set(Object.values(want)).size === 5, JSON.stringify({ want, got }));
    await page.shot(path.join(out, `unsaved-rows-parameters-${look}.png`), `document.querySelector('.editors')`);
  }
  await evaluate(`document.documentElement.dataset.theme = 'whiteprint'`);

  // ---- Specs: the objective is the Limit cell's; a column not in view is said on the row -----------------------------
  await tab('targets');
  const specNote = await title(`${SROW('osc_frequency_hz')}.querySelector('td.sel')`) ?? '';
  check('Specs: the row and its Lower and Limit cells are marked; the tooltips give the saved limit and lower', /\bunsaved-changed\b/.test(await cls(SROW('osc_frequency_hz')))
    && /\bunsaved-cell\b/.test(await cls(`${SROW('osc_frequency_hz')}.querySelector('td[data-field="constraint"]')`))
    && (await title(BOX(SROW('osc_frequency_hz'), 'constraint'))).startsWith('Saved in the task: ≥ lower.')
    && (await title(BOX(SROW('osc_frequency_hz'), 'lower'))).startsWith('Saved in the task: 1 GHz.'), await title(BOX(SROW('osc_frequency_hz'), 'constraint')));
  check('...and the row\'s note names every change, a column not in view too', specNote.startsWith('Changed since the task was saved: ')
    && ['Limit (saved: ≥ lower)', 'Lower (saved: 1 GHz)', 'Scale (saved: 200 MHz)'].every(part => specNote.includes(part))
    && !(await evaluate(`!!${SROW('osc_frequency_hz')}.querySelector('td[data-field="normalization_scale"]')`)), specNote);
  await page.shot(path.join(out, 'unsaved-rows-specs.png'), `document.querySelector('.editors')`);
  await tab('measurements');
  check('Probes: the rows as saved are not marked', await marked() === 0);
  await tab('parameters');

  // ---- typing: the saved value back takes the mark away, a new edit brings one ---------------------------------------
  await typeIn(BOX(PROW('wn'), 'upper'), '1.5');
  check('typing the saved value back takes the row\'s mark away', await page.until(`!/unsaved/.test(${PROW('wn')}.className)`, 40), await cls(PROW('wn')));
  await typeIn(BOX(PROW('wp'), 'upper'), '1.7 um');
  check('a new edit marks its row and cell', await page.until(`/unsaved-changed/.test(${PROW('wp')}.className) && !!${PROW('wp')}.querySelector('td.unsaved-cell[data-field="upper"]')`, 40)
    && (await title(`${PROW('wp')}.querySelector('td.sel')`)) === 'Changed since the task was saved: Upper (saved: 1.6 um).', await title(`${PROW('wp')}.querySelector('td.sel')`));

  // ---- Save task: asked again with the same rows, every mark goes ----------------------------------------------------
  await page.until(`!!(${BAR}) && !${BAR}.disabled`, 50);
  await sleep(1000);                                          // the page keeps its rows 0.8 s after the last edit
  const before = validations.length, storedBefore = JSON.stringify(await evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).parameters`));
  await evaluate(`${BAR}.click()`);
  const gone = await page.until(`!document.querySelector('.editors table.editor tbody tr[class*="unsaved-"]') && !document.querySelector('.editors .tabs > button.has-unsaved')`, 60);
  await sleep(1200);
  const storedAfter = JSON.stringify(await evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).parameters`));
  check('Save task sends the rows once; validation is asked again although the rows did not change; every mark and dot goes',
    saves.length === 1 && validations.length > before && same(validations.at(-1).parameters, saves[0].config.parameters) && storedBefore === storedAfter && gone,
    `saves ${saves.length}, validations ${before} -> ${validations.length}, rows kept ${storedBefore === storedAfter}, gone ${gone}`);

  // ---- a save that ended elsewhere: followed after a reload, its rows leave the rows here behind ---------------------
  saving = { running: { id: 'other', task_key: TASK, started_utc: '2026-10-06T00:00:00+00:00', seconds: 3, steps: STEPS, step: 'setup', step_number: 1,
    step_seconds: 1, usual_seconds: 30 }, last: null };
  await send('Page.reload', {});
  const following = await page.until(`(${NOTES})?.textContent.includes('Saving real:ring_osc')`, 100);
  await sleep(1500);
  check('after a reload the rows are the saved ones: nothing marked while another save runs', following && await marked() === 0, `following ${following}, marked ${await marked()}`);
  const beforeEnd = validations.length;
  saved = { ...saved, parameters: saved.parameters.map(r => r.variable_id === 'wn' ? { ...r, upper: 1.9 } : r) };
  revision += 1;
  saving = { running: null, last: { id: 'other', task_key: TASK, ok: true, seconds: 30, answer: { task_key: TASK, revision } } };
  check('when that save ends, validation is asked again and marks the row it left behind', await page.until(`/unsaved-changed/.test(${PROW('wn')}?.className ?? '')`, 60)
    && validations.length > beforeEnd && (await title(`${PROW('wn')}.querySelector('td.sel')`)) === 'Changed since the task was saved: Upper (saved: 1.9 um).',
    `${validations.length - beforeEnd} validations, ${await title(`${PROW('wn')}.querySelector('td.sel')`)}`);

  // ---- a task that is not saved: no marks ----------------------------------------------------------------------------
  noSavedTask = true;
  await typeIn(BOX(PROW('wp'), 'upper'), '1.8');
  check('a report without them (a task that is not saved) marks nothing', await page.until(`!document.querySelector('.editors table.editor tbody tr[class*="unsaved-"]')`, 40)
    && !(await evaluate(`!!document.querySelector('.editors .tabs > button.has-unsaved')`)));
  check('no other writing request was made', page.refused.length === 0, page.refused.join(' | '));
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | '));
});
