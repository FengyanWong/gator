// Browser check of "each spec is an equation over the probes" (status record 7.52): the Specs tab edits `equation`, an
// older saved Specs row (one probe in `measurement_id`) is read as its equation, and what is typed is judged by the REAL
// backend's validation. Same approach as task_rows_check.mjs: a throwaway headless Edge over the DevTools protocol.
// Requests: GET, POST /api/circuit/load and POST /api/config/validate pass through (read-only: local files, no bridge, no
// simulation), every other writing request is refused here - so it is safe on any backend, but it needs one that KNOWS
// equations (restarted after 7.52, or a scratch one).
// The browser profile is new and temporary: the user's saved configuration is not touched.
// Run (Windows node through WSL interop; node >= 22):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/spec_equations_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { readFileSync, writeFileSync } from 'node:fs';
import { check, launchEdge, mockStarter, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('specs');

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, consoleErrors } = page;
  const refused = [];
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (request.method === 'GET' || ['/api/config/validate', '/api/circuit/load', '/api/config/diff'].includes(name)) return page.pass(requestId);
    // Refused, harmless: the output-folder look-up, and the connection test the page makes once when it opens (record 7.80)
    if (name !== '/api/output/check' && name !== '/api/connection/check') refused.push(`${request.method} ${name}`);
    return page.refuse(requestId);
  };
  const until = (expression, tries = 100) => page.until(expression, tries);
  const EDITORS = `document.querySelector('.editors')`;
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith(${JSON.stringify(name)})).click()`);
  const headers = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field ?? h.textContent.replace(' *', '').trim())`);   // fields: the headers read in plain words (record 7.188)
  // A column by its field name (the header's data-field): a header may show a label instead ("Missing value = failed").
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const cell = (row, name) => evaluate(`${CELL(row, name)}.value`);
  const type = (row, name, v) => page.setValue(`${CELL(row, name)}`, v, { event: 'input' });
  // Branch record SIF-5: a row's issue shows its level and the first words of its message; its code is in data-code.
  const issues = row => evaluate(`[...${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].querySelectorAll('td.issues .issue')].map(d => d.className.replace('issue ', '') + ': ' + d.dataset.code)`);
  const issueWords = row => evaluate(`[...${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].querySelectorAll('td.issues .issue')].map(d => [d.textContent.trim(), d.title])`);
  const issuesUntil = async (row, wanted, absent = []) => {
    for (let i = 0; i < 60; i++) {
      const found = await issues(row);
      if (wanted.every(w => found.includes(w)) && absent.every(a => !found.some(f => f.includes(a)))) return [true, found];
      await sleep(150);
    }
    return [false, await issues(row)];
  };
  const shot = name => page.shot(path.join(out, name));

  await page.intercept(['*/api/*'], answer);
  await page.trackSaves();                                  // the page saves 800 ms after the last change: read it with saved()
  // The page opens as a browser that saved its configuration BEFORE specs had equations: one probe in `measurement_id`.
  const starter = await mockStarter(APP);
  const legacy = starter.targets.map(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k === 'equation' ? 'measurement_id' : k, v])));
  check('the backend knows equations (restarted after 7.52)', starter.targets[0]?.equation === 'm_score', JSON.stringify(starter.targets[0]));
  const SEED = { schema_version: 'gator-workbench-config-v1', ...starter, targets: legacy,
    run: { mode: 'scratch', concurrency: 1, threads_per_job: 1, ...starter.run }, output: { experiment_name: 'fixture' }, research: {} };
  await page.seed({ config: SEED, when: 'missing' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await until(`!!${EDITORS}`));
  await openTab('Specs');
  check('the Specs tab edits an equation, right after the spec name', JSON.stringify((await headers()).slice(1, 3)) === '["metric_id","equation"]', JSON.stringify(await headers()));
  check('an older saved row shows its probe as the equation', await until(`${CELL(0, 'equation')}?.value === 'm_score'`), await cell(0, 'equation'));
  await page.saved();
  const saved = await page.stored();
  check('...and is saved back in the new form, in the same place', JSON.stringify(Object.keys(saved.targets[0]).slice(0, 2)) === '["metric_id","equation"]'
    && !('measurement_id' in saved.targets[0]), JSON.stringify(saved.targets[0]));
  check('the old row is valid as it is', (await issuesUntil(0, [], ['error', 'blocker']))[0], JSON.stringify(await issues(0)));
  check('the tab names the probes an equation can use', /^Probes: m_score$/.test(await evaluate(`${EDITORS}.querySelector('.spec-probes')?.textContent ?? ''`)));
  // The row-selection tick box is as narrow as the box (it inherited the 84 px minimum of the editor inputs).
  const tickWidth = await evaluate(`${EDITORS}.querySelector('table.editor thead th.sel')?.getBoundingClientRect().width ?? 0`);
  check('the tick-box column is narrow', tickWidth > 0 && tickWidth < 32, `${tickWidth} px`);
  // The objective lives in the constraint list: only pairs that can work, and both fields change in ONE step (one Undo).
  check('no Objective column: the objective is part of the constraint list', await evaluate(`!${EDITORS}.querySelector('th[data-field="direction_after_feasible"]')`));
  const choices = await evaluate(`[...${CELL(0, 'constraint')}.options].map(o => o.textContent)`);
  check('the list pairs a lower limit with "higher is better" and an upper one with "lower is better", never the reverse',
    choices.includes('≥ lower, then higher is better') && choices.includes('≤ upper, then lower is better')
    && !choices.includes('≥ lower, then lower is better') && !choices.includes('≤ upper, then higher is better'), JSON.stringify(choices));
  // the scale sits behind "More columns" since record 7.183: shown for this edit, then hidden again
  const moreSpecColumns = `[...${EDITORS}.querySelectorAll('button')].find(b => /^(More|Fewer) columns/.test(b.textContent.trim()))`;
  await evaluate(`${moreSpecColumns}.click()`);
  await until(`!!${EDITORS}.querySelector('th[data-field="normalization_scale"]')`);
  await type(0, 'normalization_scale', '');                // an empty scale: the backend sizes it from the limit
  await evaluate(`${moreSpecColumns}.click()`);
  await until(`!${EDITORS}.querySelector('th[data-field="normalization_scale"]')`);
  await page.saved();
  await page.setValue(CELL(0, 'constraint'), '>=|maximize');
  await page.saved();
  const maximized = (await page.stored()).targets[0];
  check('choosing "≥ lower, then higher is better" saves the limit and the objective, and leaves an empty scale empty',
    maximized.constraint === '>=' && maximized.direction_after_feasible === 'maximize' && maximized.normalization_scale == null, JSON.stringify(maximized));
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Undo').click()`);
  await page.saved();
  check('one Undo takes both back', (await page.stored()).targets[0].direction_after_feasible !== 'maximize'
    && (await cell(0, 'constraint')) === '>=|none', await cell(0, 'constraint'));
  check('Judged at is not shown while the run plans no training corners', await evaluate(`!${EDITORS}.querySelector('th[data-field="nominal_only"]')`));

  // a formula: its own name, a unit that cannot be checked, a new entry in the network's result registry
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Add').click()`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 2`);
  // "Add" supplies the required constraint. Its scale stays empty while nothing sizes it (record 7.112): this fixture's
  // new row has no limit and the unit 'fixture', so the backend's threshold-size rule applies until a limit is typed.
  const saved1 = async () => { await page.saved(); return (await page.stored())?.targets?.[1]; };
  const added = await saved1();
  check('a new spec row starts complete: the first probe as its equation, in its unit, a constraint, and an empty scale',
    added?.equation === 'm_score' && added?.unit === 'fixture' && added?.constraint === '>=' && added?.normalization_scale == null, JSON.stringify(added));
  await type(1, 'metric_id', 'score_sq'); await type(1, 'equation', 'm_score ** 2'); await type(1, 'lower', '0.5');
  let [ok, found] = await issuesUntil(1, ['warning: equation_unit_unchecked', 'info: spec_adds_registry_entry'], ['error', 'blocker']);
  const row = async () => JSON.stringify(await saved1())
    + ' | page issues: ' + JSON.stringify(await evaluate(`[...document.querySelectorAll('.editors .issue')].map(d => d.textContent.trim())`));
  check('a formula is accepted: its unit is not checkable, its name is new to the registry', ok, JSON.stringify(found) + (ok ? '' : ' ' + await row()));
  const words = await issueWords(1);
  check('...each said in words - its level and the first clause of its message, the whole message and its code on hover (SIF-5)',
    words.length >= 2 && words.some(([text, title]) => text === 'warning The unit of a formula is not checked' && title.endsWith('(warning: equation_unit_unchecked)'))
    && words.every(([text, title]) => !text.includes(title.match(/: (\w+)\)$/)?.[1] ?? 'no code in the tooltip')), JSON.stringify(words));
  // Branch record SIF-74: the registry line says its point ("'score_sq' is new to the result registry the netw..." was cut
  // before it), no line is cut (the basis line was: "The source of this requirement is not recor..."), and the column is
  // padded at its sides and centred in the row (its lines touched the cell's line).
  const column = await evaluate(`(() => { const td = ${EDITORS}.querySelectorAll('table.editor tbody tr')[1].querySelector('td.issues'), s = getComputedStyle(td);
    return { pad: [s.paddingLeft, s.paddingRight], align: s.verticalAlign, cut: [...td.querySelectorAll('.issue')].filter(d => d.scrollWidth > d.clientWidth).map(d => d.dataset.code) }; })()`);
  check('...the registry line in words of its own, no line cut, the column padded at its sides and centred in the row (SIF-74)',
    words.some(([text, title]) => text === 'info New spec: models without it do not load' && title.endsWith('(info: spec_adds_registry_entry)'))
    && JSON.stringify(column.pad) === '["10px","10px"]' && column.align === 'middle' && column.cut.length === 0, JSON.stringify({ words, column }));
  const sized = await saved1();
  check('typing the lower limit proposes a scale from it (0.5)', sized?.normalization_scale === 0.5, JSON.stringify(sized));
  await shot('spec_equation_formula.png');
  // "Missing value = failed" is no row switch since 2026-10-10: the optimizer counts a missing value of every hard spec as
  // failed, so "More columns" does not offer it (the rows keep the value they stored), and a soft spec is named for nothing
  await evaluate(`[...${EDITORS}.querySelectorAll('button')].find(b => b.textContent.startsWith('More columns')).click()`);
  await until(`!!${EDITORS}.querySelector('th[data-field="margin_sides"]')`);
  check('"More columns" does not offer "Missing value = failed"', !(await evaluate(`!!${EDITORS}.querySelector('th[data-field="missing_is_failure"]')`)));
  await evaluate(`${CELL(1, 'hard')}.click()`);
  [ok, found] = await issuesUntil(1, [], ['missing_is_failure_on_soft_spec']);
  check('a soft spec is named for no missing-value switch', ok, JSON.stringify(found));
  await evaluate(`${CELL(1, 'hard')}.click()`);
  await type(1, 'equation', 'm_nope * 2');
  [ok, found] = await issuesUntil(1, ['error: equation_unknown_probe']);
  check('a probe that does not exist is named as an error', ok, JSON.stringify(found));
  await type(1, 'equation', 'abs(m_score)');
  [ok, found] = await issuesUntil(1, ['error: equation_rejected']);
  check('a function call is refused, not evaluated', ok, JSON.stringify(found));
  await type(1, 'metric_id', 'm_score'); await type(1, 'equation', 'm_score * 2');
  [ok, found] = await issuesUntil(1, ['error: spec_name_is_a_probe']);
  check('a formula may not take the name of a probe', ok, JSON.stringify(found));
  await type(1, 'metric_id', 'score'); await type(0, 'metric_id', 'score_plain');
  [ok, found] = await issuesUntil(1, ['error: spec_name_is_a_result']);
  check('a formula may not take the name of a simulator result', ok, JSON.stringify(found));
  // ---- record 7.125: typing into one field is ONE Undo step; an edit made just before a reload is kept -------------------
  await type(0, 'metric_id', 'score'); await type(1, 'metric_id', 'score_sq'); await type(1, 'equation', 'm_score ** 2');
  await page.saved();
  const lowerBefore = (await page.stored()).targets[1].lower;
  await evaluate(`${CELL(1, 'lower')}.focus(); ${CELL(1, 'lower')}.select()`);
  for (const ch of '0.625') { await send('Input.insertText', { text: ch }); await sleep(60); }
  await page.saved();
  check('typing 0.625 into a cell stores 0.625', (await page.stored()).targets[1].lower === 0.625, JSON.stringify((await page.stored()).targets[1]));
  await evaluate(`${CELL(1, 'lower')}.blur()`);
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Undo').click()`);
  await page.saved();
  check('one Undo takes the whole typed value back (not one character)', (await page.stored()).targets[1].lower === lowerBefore, `${(await page.stored()).targets[1].lower} (before: ${lowerBefore})`);
  // Review of 2026-10-01: a change that was not typed - a button, an applied answer - is a step of its own, even while the
  // cell still has focus (the focused field decided it, and Undo took the typed value away with the button's change).
  await evaluate(`${CELL(1, 'lower')}.focus(); ${CELL(1, 'lower')}.select()`);
  for (const ch of '0.5') { await send('Input.insertText', { text: ch }); await sleep(60); }
  const rowsBefore = await evaluate(`${EDITORS}.querySelectorAll('tbody tr').length`);
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Add').click()`);   // at once, focus stays
  const focusStayed = await evaluate(`document.activeElement === ${CELL(1, 'lower')}`);
  await page.saved();
  const withRow = (await page.stored()).targets;
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Undo').click()`);
  await page.saved();
  const undone = (await page.stored()).targets;
  check('a button pressed while a typed cell has focus is its own Undo step: Undo takes the row, the typed 0.5 stays',
    focusStayed && withRow.length === undone.length + 1 && undone[1].lower === 0.5
    && await evaluate(`${EDITORS}.querySelectorAll('tbody tr').length`) === rowsBefore,
    `focus stayed ${focusStayed}; rows ${withRow.length} -> ${undone.length}; lower ${undone[1].lower}`);
  await evaluate(`${CELL(1, 'lower')}.blur()`);
  await evaluate(`${CELL(1, 'lower')}.focus(); ${CELL(1, 'lower')}.select()`);
  await send('Input.insertText', { text: '0.25' });
  await send('Page.reload');                                 // at once: less than 0.8 s after the change
  await until(`!!${EDITORS}`); await openTab('Specs');
  check('an edit made just before a reload is kept', await until(`${CELL(1, 'lower')}?.value === '0.25'`), await cell(1, 'lower').catch(() => '?'));

  // ---- record 7.125: a long import keeps Apply within reach; a JSON file that is not a workbench configuration is refused --
  const setFile = async file => {
    const { root } = await send('DOM.getDocument', { depth: -1 });
    const { nodeId } = await send('DOM.querySelector', { nodeId: root.nodeId, selector: '.editors input[type=file]' });
    await send('DOM.setFileInputFiles', { nodeId, files: [file] });
  };
  const template = (await page.stored()).targets[0];
  const many = path.join(out, 'twenty-specs.json');
  writeFileSync(many, JSON.stringify(Array.from({ length: 20 }, (_, i) => ({ ...template, metric_id: `extra_${i}` }))));
  await setFile(many);
  check('a 20-row import confirmation keeps Apply within reach (the box scrolls by itself)', await until(`(() => {
    const b = [...(document.querySelector('.editors .confirm')?.querySelectorAll('button') ?? [])].find(x => x.textContent === 'Apply'); if (!b) return false;
    const r = b.getBoundingClientRect(); return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) === b; })()`));
  await shot('spec_import_confirm.png');
  // Branch record SIF-51: the confirmation names the tab, the change and each field as the editors do, where it said
  // "targets | extra_0 | added | metric_id"; the program's names stay in the tooltips.
  const imported = await evaluate(`[...document.querySelectorAll('.editors .confirm tbody tr')].map(tr => [...tr.children].map(td => [td.textContent, td.title]))`);
  const firsts = imported.filter(r => r.length === 6), fieldsOf = imported.map(r => r[r.length - 3]);
  check('the import confirmation names Specs, a new row and a replaced one, and each field by its header (its name in the tooltip)',
    firsts.length > 0 && firsts.every(r => r[0][0] === 'Specs' && r[0][1] === 'targets')
    && firsts.some(r => r[1][0] === 'extra_0' && r[2][0] === 'new') && firsts.some(r => r[1][0] === template.metric_id && r[2][0] === 'deleted')
    && fieldsOf.some(([text, title]) => text === 'Spec ID' && title === 'metric_id') && !fieldsOf.some(([text]) => text === 'metric_id'),
    JSON.stringify(imported.slice(0, 3)));
  await evaluate(`[...document.querySelectorAll('.editors .confirm button')].find(b => b.textContent === 'Cancel').click()`);
  const foreign = path.join(out, 'gpdk045_conditions.json');
  writeFileSync(foreign, readFileSync(new URL('../../configs/gpdk045_conditions.json', import.meta.url)));
  await setFile(foreign);
  check('a JSON file with a schema_version that is not a workbench configuration is refused, in words (the page used to go blank on Apply)',
    await until(`/neither a workbench configuration/.test(${EDITORS}.querySelector('.error')?.textContent ?? '') && !document.querySelector('.editors .confirm')`),
    await evaluate(`${EDITORS}.querySelector('.error')?.textContent ?? 'no message'`));
  // A file that is not JSON is said so, with what to choose, where the browser's parser text stood; a row without its ID names
  // the header, Spec ID, beside the file's key (branch record SIF-50).
  const ERROR = `(${EDITORS}.querySelector('.error')?.textContent ?? '')`;
  const notJson = path.join(out, 'not-json.json');
  writeFileSync(notJson, 'abc');
  await setFile(notJson);
  check('a file that is not JSON is refused in words, with what to choose (branch record SIF-50)',
    await until(`${ERROR} === 'Import failed: the file is not JSON. Choose a file written by Export JSON, or a list of rows.'`), await evaluate(ERROR));
  const noIds = path.join(out, 'specs-without-ids.json');
  writeFileSync(noIds, JSON.stringify([{ ...template, metric_id: '' }]));
  await setFile(noIds);
  check('...and a row without its ID is named by its header, Spec ID, beside the file\'s key',
    await until(`${ERROR} === 'Import failed: every Specs row needs its Spec ID ("metric_id" in the file)'`), await evaluate(ERROR));

  // With training corners planned, each spec's "Judged at" matters again, and the column is there. The page's own save comes
  // first: a save still due could land between the write below and the reload and put the configuration without corners back
  // (seen once in a full run under load, record 7.188).
  await page.saved();
  const withCorners = await page.stored();
  withCorners.run = { ...withCorners.run, conditions: { policy: 'always', corners: ['ss_hot_low'] } };
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(withCorners))}); window.__beforeReload = true`);
  await send('Page.reload');
  await until(`!window.__beforeReload && !!${EDITORS}`);
  await openTab('Specs');
  check('with training corners planned, Judged at is shown', await until(`!!${EDITORS}.querySelector('th[data-field="nominal_only"]')`), JSON.stringify(await headers()));

  check('the page sent no writing request but validations', refused.length === 0, JSON.stringify(refused));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | '));
});
