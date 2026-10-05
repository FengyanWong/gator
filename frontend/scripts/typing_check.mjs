// Browser check of typing into the workbench's boxes (Typed.tsx; review of 2026-09-22), key by key as a person types -
// Input.dispatchKeyEvent per character, not one insertText of the whole string, because the old boxes broke BETWEEN keys:
//   - a number cell of Parameters / Probes / Specs keeps the typed text while it has focus: "1.5" and "4.5e-7" typed key by
//     key are stored as 1.5 and 4.5e-7 (the old cell showed "1." as "1", so 1.5 became 15); an emptied cell shows the
//     stored value again on blur; Undo while a cell has focus replaces the typed text;
//   - "More columns": Specs shows soft_weight after it, a value typed there stays when the columns are hidden again, and
//     Probes has none since its conditions and aggregation were retired (record 7.105; conditions was the editors' only
//     JSON cell, so no JSON cell is typed into any more);
//   - a new row gets a FREE ID (rows.length + 1 repeated an existing ID after a deletion);
//   - Research experiments: "a, b" typed key by key becomes ['a', 'b'] (the old box swallowed the comma);
//   - Circuit class / PDK id: emptied, then typed, they take the new text (the old box put "unspecified" back at once);
//   - in Mode scratch the page no longer writes the project's default model into run.model_source on page load; it does
//     once Mode is switched to one that loads a model (fine_tune), and one Undo takes both back;
//   - "Stop after N consecutive failed evaluations" (the Limits fold, "Failure limits" until record 7.179) shows the engine's limit of 5 and takes a typed one;
//   - "Import JSON..." of one table's rows writes that table alone: an edit made while its box was open stays.
// A throwaway headless Edge over the DevTools protocol (lib/harness.mjs). HERMETIC: validation, the default model and the
// model list are answered here with canned data labelled FIXTURE; other reads pass; every other writing request is
// refused. The browser profile is new and temporary: the user's saved configuration is not touched. So it is safe on the
// live backend (the default URL); for a page that is not live yet point GATOR_WORKBENCH_URL at a preview of a build:
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/typing_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { writeFileSync } from 'node:fs';
import { validConfiguration, check, launchEdge, outDir, reportRefused, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('typing');

// ---- canned answers ------------------------------------------------------------------------------------------
const DEFAULT_RUN = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task/scratch__seed0__0001';
const VALID = validConfiguration({ mock: true });

await runChecks(browser, async () => {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { schema_version: 'gator-workbench-config-v1', ...starter, run: { ...starter.run, mode: 'scratch' }, output: { experiment_name: 'fixture' }, research: {} };
  delete CONFIG.run.model_source;                                                  // no model chosen: the page may fill in a default
  const page = await browser.open();
  const { send, evaluate, until, consoleErrors } = page;
  const cancelled = new Set();
  await send('Network.enable');
  page.on('Network.loadingFailed', p => { if (p.canceled) cancelled.add(p.requestId); });
  const refused = []; const defaultAsks = [];
  let holdValidation = false;
  await page.intercept(['*/api/*'], params => {
    const { requestId, request } = params, name = new URL(request.url).pathname;
    if (name === '/api/config/validate') {
      if (holdValidation) { page.paused.push({ requestId, networkId: params.networkId, url: request.url, postData: request.postData }); return; }
      return page.fulfil(requestId, 200, VALID);
    }
    if (name === '/api/runs/default-model') { defaultAsks.push(request.url); return page.fulfil(requestId, 200, { run_dir: DEFAULT_RUN, checkpoint_id: 'latest', reason: 'FIXTURE' }); }
    if (name === '/api/runs/models') return page.fulfil(requestId, 200, { models: [] });
    if (name === '/api/runs/model') return page.fulfil(requestId, 404, { detail: { message: 'FIXTURE: no such model' } });
    return page.readOrRefuse(params, refused, { reads: true });
  });
  await page.trackSaves();
  await page.seed({ config: CONFIG, when: 'missing' });

  // ---- typing as a person does ----------------------------------------------------------------------------------------
  const typeKeys = async text => {                                                 // one key press per character
    for (const ch of text) {
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch, unmodifiedText: ch });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch });
    }
  };
  const deleteKey = async () => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 }); };
  const focusAll = expression => evaluate(`(() => { const i = ${expression}; for (let parent = i.parentElement; parent; parent = parent.parentElement) { if (parent.tagName === 'DETAILS') parent.open = true; } i.scrollIntoView({ block: 'center' }); i.focus(); i.select(); return document.activeElement === i; })()`);
  const valueOf = expression => evaluate(`${expression}?.value ?? null`);
  const blur = expression => evaluate(`${expression}.blur()`);
  const saved = async () => { await page.saved(); return page.stored(); };            // the configuration once the page has written it
  const EDITORS = `document.querySelector('section.editors')`;
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs > button')].find(b => b.textContent.trim().startsWith(${JSON.stringify(name)})).click()`);
  const TOOL = text => `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim()).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}]?.children[at]?.querySelector('input, select'); })()`;
  const LABELLED = (scope, label) => `[...document.querySelectorAll(${JSON.stringify(scope + ' label')})].find(l => l.firstChild?.textContent?.trim() === ${JSON.stringify(label)})?.querySelector('input, select')`;
  const shot = (name, what) => page.shot(path.join(out, name), what);

  await send('Page.navigate', { url: APP });
  if (!(await until(`!!${EDITORS}?.querySelector('table.editor tbody tr') && !!(${LABELLED('.right', 'Mode')})`, 150)))
    throw new Error('the editors never showed the seeded rows; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));

  // ---- (d) scratch: the project's default model is NOT written on page load --------------------------------------------------
  await sleep(2000);                                                               // the old page wrote it as soon as the answer came
  let config = await saved();
  check('in Mode scratch the page does not write the project\'s default model into run.model_source on page load',
    (config?.run?.model_source?.run_dir ?? null) === null, `${JSON.stringify(config?.run?.model_source ?? null)}; default model asked ${defaultAsks.length} time(s)`);

  // ---- (a) number cells keep what is being typed ----------------------------------------------------------------------------
  await openTab('Parameters');
  check('(set-up) the Parameters tab holds the starter rows', (await evaluate(`${EDITORS}.querySelectorAll('table.editor tbody tr').length`)) === CONFIG.parameters.length);
  await focusAll(CELL(0, 'upper')); await typeKeys('1.');
  check('a half-typed "1." stays in the cell while it has focus', (await valueOf(CELL(0, 'upper'))) === '1.', await valueOf(CELL(0, 'upper')));
  await typeKeys('5');
  config = await saved();
  check('"1.5" typed key by key is stored as 1.5, and the cell shows 1.5 (it used to become 15)', config.parameters[0].upper === 1.5 && (await valueOf(CELL(0, 'upper'))) === '1.5',
    `${config.parameters[0].upper} / ${await valueOf(CELL(0, 'upper'))}`);
  await focusAll(CELL(0, 'lower')); await typeKeys('4.5e-');
  check('a half-typed exponent "4.5e-" stays in the cell', (await valueOf(CELL(0, 'lower'))) === '4.5e-', await valueOf(CELL(0, 'lower')));
  await typeKeys('7');
  config = await saved();
  check('"4.5e-7" typed key by key is stored as 4.5e-7', config.parameters[0].lower === 4.5e-7 && (await valueOf(CELL(0, 'lower'))) === '4.5e-7', `${config.parameters[0].lower}`);
  await blur(CELL(0, 'lower'));
  await shot('typing-1-numbers.png', `document.querySelector('section.editors')`);

  // ---- (a) "More columns": five on Specs, none on Probes since its conditions and aggregation went (record 7.105) ----------
  const MORE = `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => /^More columns/.test(b.textContent.trim()))`;
  await openTab('Probes');
  check('the Probes tab offers no "More columns" and has no conditions or aggregation column (retired in record 7.105)',
    (await evaluate(`${MORE} ?? null`)) === null && (await evaluate(`${CELL(0, 'conditions')} ?? null`)) === null
    && (await evaluate(`${CELL(0, 'aggregation')} ?? null`)) === null);
  await openTab('Specs');
  check('(set-up) the Specs tab offers "More columns (5)" and shows no soft_weight column before it is pressed',
    (await evaluate(`${MORE}?.textContent.trim()`)) === 'More columns (5)' && (await evaluate(`${CELL(0, 'soft_weight')} ?? null`)) === null);
  await evaluate(`${MORE}.click()`);
  check('(set-up) after "More columns" the soft_weight column is there and the button reads "Fewer columns"',
    (await evaluate(`!!${CELL(0, 'soft_weight')}`)) && (await evaluate(`!!${TOOL('Fewer columns')}`)));
  await focusAll(CELL(0, 'soft_weight')); await typeKeys('2.');
  check('a half-typed "2." stays in a "More columns" cell while it has focus', (await valueOf(CELL(0, 'soft_weight'))) === '2.', await valueOf(CELL(0, 'soft_weight')));
  await typeKeys('5');
  config = await saved();
  check('"2.5" typed key by key into soft_weight is stored as 2.5', config.targets[0].soft_weight === 2.5, `${config.targets[0].soft_weight}`);
  await blur(CELL(0, 'soft_weight'));
  await evaluate(`${TOOL('Fewer columns')}.click()`);
  config = await saved();
  check('"Fewer columns" hides soft_weight again and the value stays (2.5)',
    (await evaluate(`${CELL(0, 'soft_weight')} ?? null`)) === null && config.targets[0].soft_weight === 2.5, `${config.targets[0].soft_weight}`);
  await openTab('Parameters');
  // ratio is one of the four Parameters columns "More columns" shows since the review of 2026-10-03 (value_type, step, scale,
  // ratio: Save task takes them from the PDK and the circuit); initial_value and result_source are not shown at all.
  const moreHere = `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => /^(More|Fewer) columns/.test(b.textContent.trim()))`;
  const headers = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).filter(Boolean)`);
  const shownBefore = await headers();
  check('Parameters shows no ratio, step, scale, value_type or initial_value until "More columns", which offers four',
    !['ratio', 'step', 'scale', 'value_type', 'initial_value'].some(c => shownBefore.includes(c)) && /More columns \(4\)/.test(await evaluate(`${moreHere}?.textContent ?? ''`)),
    JSON.stringify(shownBefore));
  await evaluate(`${moreHere}.click()`);
  await until(`!!${CELL(0, 'ratio')}`);
  const shownNow = await headers();
  check('after "More columns" the four are there, initial_value still not',
    ['ratio', 'step', 'scale', 'value_type'].every(c => shownNow.includes(c)) && !shownNow.includes('initial_value'), JSON.stringify(shownNow));

  // ---- (a) an emptied cell, and Undo while a cell has focus --------------------------------------------------------------------
  await focusAll(CELL(0, 'ratio')); await deleteKey();
  config = await saved();
  check('an emptied number cell stays empty while it has focus', (await valueOf(CELL(0, 'ratio'))) === '', await valueOf(CELL(0, 'ratio')));
  await blur(CELL(0, 'ratio'));
  config = await saved();
  check('on blur it shows the stored value again (a required number: 0)', config.parameters[0].ratio === 0 && (await valueOf(CELL(0, 'ratio'))) === String(config.parameters[0].ratio),
    `${config.parameters[0].ratio} / ${JSON.stringify(await valueOf(CELL(0, 'ratio')))}`);
  await focusAll(CELL(0, 'upper')); await typeKeys('2.');
  config = await saved();
  check('(set-up) "2." typed over 1.5: stored 2, the cell shows "2."', config.parameters[0].upper === 2 && (await valueOf(CELL(0, 'upper'))) === '2.', `${config.parameters[0].upper} / ${await valueOf(CELL(0, 'upper'))}`);
  await evaluate(`${TOOL('Undo')}.click()`);                                     // a click by code: the cell keeps its focus
  config = await saved();
  const undone = await evaluate(`({ focused: document.activeElement === ${CELL(0, 'upper')}, value: ${CELL(0, 'upper')}.value })`);
  check('Undo while the cell has focus replaces the typed "2." with the value it brings back (1.5)', config.parameters[0].upper === 1.5 && undone.focused && undone.value === '1.5', JSON.stringify(undone));
  await blur(CELL(0, 'upper'));

  // ---- (a) a new row gets a free ID -----------------------------------------------------------------------------------------------
  const ids = async () => ((await saved()).parameters ?? []).map(r => r.variable_id);
  const tick = id => evaluate(`(() => { const rows = [...${EDITORS}.querySelectorAll('table.editor tbody tr')]; const at = ${JSON.stringify(id)};
    const row = rows.find(r => r.querySelector('td:nth-child(2) input')?.value === at); row.querySelector('td:first-child input[type=checkbox]').click(); return true; })()`);
  for (const id of await ids()) await tick(id);
  await evaluate(`${TOOL('Delete selected')}.click()`);
  for (let n = 0; n < 3; n++) { await evaluate(`${TOOL('Add')}.click()`); await sleep(100); }
  check('(set-up) three new rows on an empty tab: parameter_1, parameter_2, parameter_3', JSON.stringify(await ids()) === '["parameter_1","parameter_2","parameter_3"]', JSON.stringify(await ids()));
  await tick('parameter_1'); await evaluate(`${TOOL('Delete selected')}.click()`);
  check('(set-up) parameter_1 deleted', JSON.stringify(await ids()) === '["parameter_2","parameter_3"]', JSON.stringify(await ids()));
  await evaluate(`${TOOL('Add')}.click()`);
  const after = await ids();
  check('"Add" after a deletion gives an ID not already used (parameter_4, not a second parameter_3)', after.length === 3 && new Set(after).size === 3 && after[2] === 'parameter_4', JSON.stringify(after));

  // ---- (b) Research experiments: a list typed with commas ---------------------------------------------------------------------------
  await evaluate(`(() => { const d = [...document.querySelectorAll('.right details.panel')].find(x => x.querySelector('summary')?.textContent.startsWith('Research experiments')); d.open = true; })()`);
  const SOURCES = LABELLED('.right details.panel', 'Training sources'), CHECKPOINTS = LABELLED('.right details.panel', 'Budget checkpoints');
  await focusAll(SOURCES); await typeKeys('a,');
  check('"Training sources" keeps "a," while it is typed (the old box swallowed the comma)', (await valueOf(SOURCES)) === 'a,', await valueOf(SOURCES));
  await typeKeys(' b');
  config = await saved();
  check('"a, b" typed key by key is stored as [\'a\', \'b\']', JSON.stringify(config.research.training_sources) === '["a","b"]' && (await valueOf(SOURCES)) === 'a, b', JSON.stringify(config.research.training_sources));
  await focusAll(CHECKPOINTS); await typeKeys('10, 20');
  config = await saved();
  check('"Budget checkpoints" typed "10, 20" is stored as [10, 20]', JSON.stringify(config.research.budget_checkpoints) === '[10,20]', JSON.stringify(config.research.budget_checkpoints));
  await blur(CHECKPOINTS);
  await shot('typing-2-research.png', `[...document.querySelectorAll('.right details.panel')].find(x => x.open)`);

  // ---- (b) Circuit class and PDK id: emptied, then typed ---------------------------------------------------------------------------------
  const CLASS = LABELLED('.left', 'Circuit class'), PDK = LABELLED('.left', 'PDK id');
  await focusAll(CLASS); await deleteKey();
  config = await saved();
  check('an emptied "Circuit class" stays empty while it is typed into (underneath: "unspecified")', (await valueOf(CLASS)) === '' && config.circuit.circuit_class === 'unspecified',
    `${JSON.stringify(await valueOf(CLASS))} / ${config.circuit.circuit_class}`);
  await typeKeys('ldo');
  config = await saved();
  check('select all + Delete, then "ldo": the class is \'ldo\' (it used to snap back to \'unspecified\')', config.circuit.circuit_class === 'ldo' && (await valueOf(CLASS)) === 'ldo',
    `${config.circuit.circuit_class} / ${await valueOf(CLASS)}`);
  await focusAll(PDK); await deleteKey(); await typeKeys('gpdk090');
  config = await saved();
  check('the same for "PDK id": \'gpdk090\'', config.circuit.pdk_id === 'gpdk090' && (await valueOf(PDK)) === 'gpdk090', `${config.circuit.pdk_id} / ${await valueOf(PDK)}`);
  await blur(PDK);
  await shot('typing-3-labels.png', `document.querySelector('.left')`);

  // ---- (d) a Mode that loads a model takes the project's default model --------------------------------------------------------------
  config = await saved();
  check('still scratch: run.model_source.run_dir is null', (config.run.model_source?.run_dir ?? null) === null, JSON.stringify(config.run.model_source ?? null));
  await page.setValue(`${LABELLED('.right', 'Mode')}`, 'fine_tune');
  let model = null;
  for (let i = 0; i < 40 && model?.run_dir !== DEFAULT_RUN; i++) { model = (await saved()).run.model_source ?? null; if (model?.run_dir !== DEFAULT_RUN) await sleep(150); }
  check('once Mode is fine_tune the project\'s default model is taken (its latest save point)', model?.run_dir === DEFAULT_RUN && model?.checkpoint_id === 'latest' && defaultAsks.length >= 1, JSON.stringify(model));
  // The page filled the model by itself: no Undo step of its own (review of 2026-09-29) - one Undo takes back the choice and what it brought.
  await evaluate(`${TOOL('Undo')}.click()`);
  config = await saved();
  check('one Undo takes back Mode fine_tune together with the default model it brought', config.run.mode === 'scratch' && (config.run.model_source?.run_dir ?? null) === null,
    JSON.stringify({ mode: config.run.mode, model: config.run.model_source ?? null }));

  // ---- (e) "Import JSON..." of one table's rows writes that table alone (review of 2026-09-29) ------------------------------------
  // Apply used to put back the whole configuration of the moment of the import: an edit made while the box was open was undone.
  await openTab('Parameters');
  const importedRows = (await saved()).parameters.map(r => ({ ...r, notes: 'FIXTURE imported' }));
  const rowsFile = path.join(browser.tempDir('import'), 'parameters.json');
  writeFileSync(rowsFile, JSON.stringify(importedRows));                            // a list of rows: no schema_version, so rows only
  const { root } = await send('DOM.getDocument', { depth: 1 });
  const { nodeId } = await send('DOM.querySelector', { nodeId: root.nodeId, selector: '.editors input[type=file]' });
  await send('DOM.setFileInputFiles', { nodeId, files: [rowsFile] });
  const APPLY = `[...document.querySelectorAll('.editors .confirm button')].find(b => b.textContent.trim() === 'Apply')`;
  check('(set-up) rows for the Parameters tab wait in the confirmation box', await until(`!!(${APPLY})`, 60));
  await page.setValue(LABELLED('.right', 'RL model label'), 'fixture-edited-meanwhile', { event: 'input' });   // the project name box until record 7.159
  await sleep(300);
  await evaluate(`${APPLY}.click()`);
  config = await saved();
  check('Apply writes the imported Parameters rows and keeps an edit made while the box was open', config.run.model_label === 'fixture-edited-meanwhile'
    && config.parameters.length === importedRows.length && config.parameters.every(r => r.notes === 'FIXTURE imported'),
    JSON.stringify({ label: config.run.model_label, notes: config.parameters.map(r => r.notes) }));

  // ---- (f) the stop rule's own field (decision of 2026-09-29): it had none, so its limit of 5 could not be seen or changed ------------
  const STOP_AFTER = LABELLED('.right', 'Stop after N consecutive failed evaluations');
  await focusAll(STOP_AFTER);
  check('Run configuration > Limits has "Stop after N consecutive failed evaluations", showing the default 5', (await valueOf(STOP_AFTER)) === '5', String(await valueOf(STOP_AFTER)));
  const stopTitle = await evaluate(`${STOP_AFTER}.closest('label').title`);
  check('its tooltip says the run stops safely and ends as failed (Continue cannot pick it up), and why reward v2.1 may need more (1-1000)',
    /stops safely/.test(stopTitle) && /"failed"/.test(stopTitle) && /Continue cannot/.test(stopTitle) && /v2\.1/.test(stopTitle) && /1-1000/.test(stopTitle), stopTitle);
  await typeKeys('12');
  config = await saved();
  check('"12" typed key by key is stored as run.max_consecutive_failures = 12', config.run.max_consecutive_failures === 12, String(config.run.max_consecutive_failures));
  await blur(STOP_AFTER);

  // Two configurations in flight: a late success must not clear the newer configuration's blocker.
  await sleep(700);
  holdValidation = true;
  await page.setValue(LABELLED('.right', 'RL model label'), 'fixture-old', { event: 'input' });
  const oldValidation = await page.nextPaused('/api/config/validate');
  await page.setValue(LABELLED('.right', 'RL model label'), 'fixture-new', { event: 'input' });
  const newValidation = await page.nextPaused('/api/config/validate');
  check('validation requests describe two different edits',
    JSON.parse(oldValidation.postData).config.run.model_label === 'fixture-old' && JSON.parse(newValidation.postData).config.run.model_label === 'fixture-new');
  await page.fulfil(newValidation.requestId, 200, validConfiguration({ blocks_run: true, counts: { error: 1 },
    issues: [{ level: 'error', path: 'run.model_label', code: 'fixture', message: 'FIXTURE: newest configuration is blocked' }] }));
  const blockedButton = `document.querySelector('header button[title^="ONE costed"]')?.disabled`;
  check('the newer validation blocks starting a run', await until(blockedButton));
  check('the superseded validation fetch is cancelled', cancelled.has(oldValidation.networkId));
  await sleep(500);
  check('an older successful validation cannot clear the newer blocker', await evaluate(blockedButton));
  holdValidation = false;

  reportRefused(refused);
  check('the page asked to start, continue, command, connect or call an agent on its own: never',
    !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|virtuoso\/|network-settings)/.test(r)), refused.join(', '));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
