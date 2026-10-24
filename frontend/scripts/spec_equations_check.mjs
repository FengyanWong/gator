// Browser check of "each spec is an equation over the probes" (status record 7.52): the Specs tab edits `equation`, an
// older saved Specs row (one probe in `measurement_id`) is read as its equation, and what is typed is judged by the REAL
// backend's validation. Same approach as task_rows_check.mjs: a throwaway headless Edge over the DevTools protocol.
// Requests: GET, POST /api/circuit/load and POST /api/config/validate pass through (read-only: local files, no bridge, no
// simulation), every other writing request is refused here - so it is safe on any backend, but it needs one that KNOWS
// equations (restarted after 7.52, or a scratch one).
// The browser profile is new and temporary: the user's saved configuration is not touched.
// Branch record SIF-106: a Probe ID typed anew takes the Specs naming it along once its cell is left or the formula bar
// writes it, and the Specs line's Probe chips put their ID into the chosen Equation cell; a chip's copy is answered here, so
// the system clipboard is not touched.
// Branch record SIF-107: the import confirmation opens with Apply in focus, Esc is Cancel (also after a click on its words)
// with the focus back on Import JSON..., a cell in focus keeps it; a failed import's line has a close mark and goes with a
// tab press.
// Branch record SIF-118: a note three rows or more share in the same words is said once in a line above the table, and those
// rows keep its level word; a row's own issue, an error too, stays whole.
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

  // ---- branch record SIF-118: a note three rows or more share in the same words is said once in a line above the table, with
  //      how many rows have it, warnings first; those rows keep its level word, its message and code on hover, and a row's own
  //      issue - an error too - stays whole beside them (on the VCO's Specs 13 lines repeated two notes). Two more formula rows
  //      give score_sq's three notes to three rows; the second has no lower limit, an error of its own -------------------------
  const SHARED_NOTES = `[...${EDITORS}.querySelectorAll('.issues-shared > .issue')]`;
  const ISSUES_OF = row => `${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].querySelector('td.issues')`;
  const sharedMarks = row => evaluate(`[...${ISSUES_OF(row)}.querySelectorAll('.issue-marks > .issue')].map(d => [d.dataset.code, d.textContent.trim(), d.title])`);
  const ownIssues = row => evaluate(`[...${ISSUES_OF(row)}.querySelectorAll(':scope > .issue')].map(d => [d.dataset.code, d.textContent.trim()])`);
  const addSpec = async n => { await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Add').click()`);
    await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === ${n}`); };
  await addSpec(3);
  await type(2, 'metric_id', 'score_cube'); await type(2, 'equation', 'm_score ** 3');
  await addSpec(4);
  await type(3, 'metric_id', 'score_4'); await type(3, 'equation', 'm_score ** 4'); await type(3, 'lower', '0.5');
  const SHARED_LINE = [['equation_unit_unchecked', 'On 3 rows: warning The unit of a formula is not checked'],
    ['spec_adds_registry_entry', 'On 3 rows: info New spec: models without it do not load'], ['basis_not_stated', 'On 3 rows: info The source of this spec is not recorded']];
  const lineSaid = await until(`JSON.stringify(${SHARED_NOTES}.map(p => [p.dataset.code, p.textContent.trim()])) === ${JSON.stringify(JSON.stringify(SHARED_LINE))}`, 100);
  const sharedLine = await evaluate(`${SHARED_NOTES}.map(p => [p.dataset.code, p.textContent.trim(), p.title])`);
  check('a note three rows share is said once in a line above the table, with how many rows have it, warnings first (SIF-118)', lineSaid, JSON.stringify(sharedLine));
  const lineTitle = code => sharedLine.find(([c]) => c === code)?.[2] ?? '';
  check('...its tooltip: the whole message - the first row\'s, named, where each row has its own -, the code and the rows',
    lineTitle('spec_adds_registry_entry').startsWith("For score_sq: 'score_sq' is new to the result registry the network reads")
    && lineTitle('spec_adds_registry_entry').includes('\n(info: spec_adds_registry_entry)\nRows: score_sq, score_cube, score_4\n')
    && lineTitle('basis_not_stated').startsWith('The source of this requirement is not recorded\n(info: basis_not_stated)\n'), JSON.stringify(sharedLine.map(([, , t]) => t)));
  const marked = [await sharedMarks(1), await sharedMarks(2), await sharedMarks(3)];
  check('...each of those rows keeps the level words, in the line\'s order, its own message and code on hover',
    marked.every(m => JSON.stringify(m.map(([code, text]) => [code, text])) === JSON.stringify([['equation_unit_unchecked', 'warning'],
      ['spec_adds_registry_entry', 'info'], ['basis_not_stated', 'info']]))
    && marked[1][1][2].startsWith("'score_cube' is new to the result registry") && marked[1][1][2].includes('\n(info: spec_adds_registry_entry)\n'), JSON.stringify(marked));
  const ownLines = [await ownIssues(0), await ownIssues(1), await ownIssues(2), await ownIssues(3)];
  check('...a row\'s own issue, an error, stays whole beside them, first; no other row has one',
    JSON.stringify(ownLines) === JSON.stringify([[], [], [['missing_threshold', 'error constraint >= needs lower']], []]), JSON.stringify(ownLines));
  await shot('spec_shared_notes.png');
  await type(2, 'lower', '0.5');
  const narrow = await until(`!${EDITORS}.querySelector('table.editor td.issues > .issue') && getComputedStyle(${ISSUES_OF(1)}).minWidth === '0px'`, 60);
  const marksBox = await evaluate(`(() => { const td = ${ISSUES_OF(1)}, line = td.querySelector('.issue-marks');
    return { column: Math.round(td.getBoundingClientRect().width), minWidth: getComputedStyle(td).minWidth,
      line: line && [line.scrollWidth, line.clientWidth, Math.round(line.getBoundingClientRect().height)] }; })()`);
  check('...with no row\'s own words left, the Issues column keeps no 240 px for them (SIF-5\'s room for a row\'s first words), the marks on one line',
    narrow && !!marksBox.line && marksBox.line[0] <= marksBox.line[1] && marksBox.line[2] < 24, JSON.stringify(marksBox));
  for (const n of [2, 3]) await evaluate(`${EDITORS}.querySelectorAll('table.editor tbody tr')[${n}].querySelector('td.sel input').click()`);
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Delete selected').click()`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 2`);
  const whole = await until(`${SHARED_NOTES}.length === 0`, 60)
    && (await issuesUntil(1, ['warning: equation_unit_unchecked', 'info: spec_adds_registry_entry', 'info: basis_not_stated']))[0];
  check('...two rows deleted, the line goes and score_sq\'s notes are whole again on its row', whole
    && (await issueWords(1)).some(([text]) => text === 'warning The unit of a formula is not checked'), JSON.stringify(await issueWords(1)));
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
  // at once, pressed while the typed cell has focus; the new row then takes the focus, its Spec ID chosen (branch record SIF-96)
  const focusStayed = await evaluate(`(() => { const typed = document.activeElement === ${CELL(1, 'lower')};
    [...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Add').click(); return typed; })()`);
  const toNewRow = await until(`!!document.activeElement && document.activeElement === ${EDITORS}.querySelectorAll('table.editor tbody tr')[2]?.querySelector('td[data-field="metric_id"] input')`, 30);
  await page.saved();
  const withRow = (await page.stored()).targets;
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Undo').click()`);
  await page.saved();
  const undone = (await page.stored()).targets;
  check('a button pressed while a typed cell has focus is its own Undo step: Undo takes the row, the typed 0.5 stays',
    focusStayed && toNewRow && withRow.length === undone.length + 1 && undone[1].lower === 0.5
    && await evaluate(`${EDITORS}.querySelectorAll('tbody tr').length`) === rowsBefore,
    `pressed in the cell ${focusStayed}, then in the new row ${toNewRow}; rows ${withRow.length} -> ${undone.length}; lower ${undone[1].lower}`);
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
  // Branch record SIF-107: the box opens with Apply in focus - where the file chooser left it on the page - so Enter applies
  // and Esc cancels at once.
  const APPLY_BUTTON = `[...(document.querySelector('.editors .confirm')?.querySelectorAll('button') ?? [])].find(x => x.textContent === 'Apply')`;
  const IMPORT_BUTTON = `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Import JSON...')`;
  const FOCUSED = `(document.activeElement?.outerHTML.slice(0, 90) ?? 'none')`;
  check('...and opens with Apply in focus (branch record SIF-107)', await until(`document.activeElement === ${APPLY_BUTTON}`, 20), await evaluate(FOCUSED));
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
  // Esc in the box is Cancel, with the focus back on Import JSON... (it fell to the page with the box); a cell in focus when
  // the box opens keeps it - a key meant for the cell never presses Apply - also after Cancel (branch record SIF-107).
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  check('Esc in the box is Cancel: the box goes, nothing is imported, the focus is back on Import JSON... (branch record SIF-107)',
    await until(`!document.querySelector('.editors .confirm') && document.activeElement === ${IMPORT_BUTTON}`, 20)
    && !(await page.stored()).targets.some(t => t.metric_id === 'extra_0'), await evaluate(FOCUSED));
  await evaluate(`${CELL(1, 'lower')}.focus()`);
  await setFile(many);
  const reopened = await until(`!!(${APPLY_BUTTON})`);
  await sleep(300);                                          // the box's effects have run
  const cellKept = await evaluate(`document.activeElement === ${CELL(1, 'lower')}`);
  await evaluate(`[...document.querySelectorAll('.editors .confirm button')].find(b => b.textContent === 'Cancel').click()`);
  check('a cell in focus keeps it when the box opens, and after Cancel', reopened && cellKept
    && await until(`!document.querySelector('.editors .confirm') && document.activeElement === ${CELL(1, 'lower')}`, 20),
    `reopened ${reopened}, kept ${cellKept}, now ${await evaluate(FOCUSED)}`);
  // A click on the box's words gives it the focus - it fell to the page - so Esc still cancels.
  await setFile(many);
  await until(`!!(${APPLY_BUTTON})`);
  await page.clickAt(await evaluate(`(() => { const r = document.querySelector('.editors .confirm h4').getBoundingClientRect(); return { x: r.left + 20, y: r.top + r.height / 2 }; })()`));
  const boxFocused = await evaluate(`document.activeElement === document.querySelector('.editors .confirm')`);
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  check('...and after a click on the box\'s words Esc still cancels it, the focus back on Import JSON...', boxFocused
    && await until(`!document.querySelector('.editors .confirm') && document.activeElement === ${IMPORT_BUTTON}`, 20), `box focused ${boxFocused}, now ${await evaluate(FOCUSED)}`);
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
  // Branch record SIF-107: the failed import's line has a close mark, and a tab press takes it away too - it stayed until the
  // next import, on every tab.
  const CLOSE_MARK = `${EDITORS}.querySelector('.import-error > button.line-close')`, ERROR_LINE = `!!${EDITORS}.querySelector('.import-error')`;
  const closeTitle = await evaluate(`${CLOSE_MARK}?.title ?? null`);
  await shot('spec_import_error.png');
  await evaluate(`${CLOSE_MARK}?.click()`);
  check('the failed import\'s line has a close mark, and a press takes the line away (branch record SIF-107)',
    /^Close: /.test(closeTitle ?? '') && await until(`!(${ERROR_LINE})`, 20), String(closeTitle));
  await setFile(noIds);
  const failedAgain = await until(ERROR_LINE);
  await openTab('Probes');
  check('...and a tab press takes it away too', failedAgain && await until(`!(${ERROR_LINE})`, 20), await evaluate(ERROR));
  await openTab('Specs');

  // ---- branch record SIF-106: a Probe ID typed anew takes the Specs naming it along, once the cell is left or the formula bar
  //      writes it - never per key; a refused ID says why. The Specs line's Probe chips put their ID into the chosen Equation
  //      cell, at the cursor, as one Undo step, and copy it with none chosen ------------------------------------------------
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });   // focus and blur as in a window that has the focus
  const NOTE = `(${EDITORS}.querySelector('.paste-note')?.textContent ?? '')`, WARNED = `!!${EDITORS}.querySelector('.paste-note.warn')`;
  const UNDO = `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Undo').click()`;
  const BAR = `document.querySelector('.formula-bar textarea')`;
  const settled = async () => { await page.saved(); return page.stored(); };
  const naming = (c, id) => c.targets.filter(t => new RegExp(`(?<![A-Za-z0-9_.])${id}(?![A-Za-z0-9_])`).test(t.equation)).map(t => t.metric_id);
  const equations = c => c.targets.map(t => t.equation);
  const start = await settled(), users = naming(start, 'm_score');
  const ID = CELL(0, 'measurement_id'), retype = async text => { await evaluate(`${ID}.focus(); ${ID}.select()`);
    for (const ch of text) { await send('Input.insertText', { text: ch }); await sleep(40); } };
  await openTab('Probes');
  check('(set-up) the MOCK Probe m_score is measured by its backend, its ID typed in its cell, and two Specs use it', start.measurements[0].result_source === 'backend_profile'
    && await evaluate(`!${ID}.readOnly`) && JSON.stringify(users) === '["score","score_sq"]', JSON.stringify({ users, probe: start.measurements[0] }));
  await retype('m_total');
  const typing = await settled();
  check('while the ID is typed key by key the Specs keep m_score: no rename per key (no "m_t" in an equation)', typing.measurements[0].measurement_id === 'm_total'
    && JSON.stringify(equations(typing)) === JSON.stringify(equations(start)), JSON.stringify(equations(typing)));
  await evaluate(`${ID}.blur()`);
  const followed = await settled(), said = `2 Specs (score, score_sq) now use m_total, the Probe's new ID. Undo takes them back with the ID.`;
  check('leaving the cell takes the Specs along (m_score ** 2 becomes m_total ** 2)', JSON.stringify(equations(followed))
    === JSON.stringify(equations(start).map(e => e.replace(/\bm_score\b/g, 'm_total'))) && naming(followed, 'm_score').length === 0, JSON.stringify(equations(followed)));
  check('...and the line under the formula bar names them, with Show Specs', await page.until(`${NOTE} === ${JSON.stringify(`${said} Show Specs`)}`, 20)
    && !(await evaluate(WARNED)), await evaluate(NOTE));
  await evaluate(UNDO);
  const back = await settled();
  check('one Undo takes the Specs back with the typed ID', back.measurements[0].measurement_id === 'm_score'
    && JSON.stringify(equations(back)) === JSON.stringify(equations(start)), JSON.stringify([back.measurements[0].measurement_id, equations(back)]));
  await retype('m-total');
  await evaluate(`${ID}.blur()`);
  const kept = await settled();
  check('an ID no equation can use leaves the Specs on m_score and says why, in amber', kept.measurements[0].measurement_id === 'm-total'
    && JSON.stringify(equations(kept)) === JSON.stringify(equations(start)) && await page.until(`${NOTE} === ${JSON.stringify('2 Specs (score, score_sq) still use m_score: "m-total" '
      + 'is not letters, digits and _ alone, with a letter or _ first. Another ID typed there takes them along; Undo takes this one back. Show Specs')}`, 20)
    && await evaluate(WARNED), await evaluate(NOTE));
  await evaluate(`${EDITORS}.querySelector('.paste-note button.note-show').click()`);
  check('...its Show Specs opens Specs, where the backend finds the probe unknown', await until(`${EDITORS}.dataset.editor === 'targets'`, 20)
    && (await issuesUntil(0, ['error: equation_unknown_probe']))[0], JSON.stringify(await issues(0)));
  await openTab('Probes');
  await retype('m_total');
  await evaluate(`${ID}.blur()`);
  const fixed = await settled();
  check('...and the next ID typed takes them along from m_score', fixed.measurements[0].measurement_id === 'm_total' && naming(fixed, 'm_total').length === 2
    && (await evaluate(NOTE)).startsWith('2 Specs (score, score_sq) now use m_total'), JSON.stringify(equations(fixed)));
  await openTab('Specs');
  check('...which the backend finds again', (await issuesUntil(0, [], ['equation_unknown_probe']))[0] && (await issuesUntil(1, [], ['equation_unknown_probe']))[0],
    JSON.stringify([await issues(0), await issues(1)]));
  // the formula bar: Enter writes the ID with the Specs, one Undo step
  await openTab('Probes');
  await evaluate(`${ID}.focus()`);
  await evaluate(`(() => { const b = ${BAR}; b.focus(); b.select(); })()`);
  await send('Input.insertText', { text: 'm_sum' });
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  const barred = await settled();
  check('an ID written in the formula bar takes the Specs along too', barred.measurements[0].measurement_id === 'm_sum' && naming(barred, 'm_sum').length === 2
    && (await evaluate(NOTE)).startsWith('2 Specs (score, score_sq) now use m_sum'), JSON.stringify([barred.measurements[0].measurement_id, equations(barred)]));
  await evaluate(UNDO);
  const unbarred = await settled();
  check('...and one Undo takes both back', unbarred.measurements[0].measurement_id === 'm_total' && naming(unbarred, 'm_total').length === 2,
    JSON.stringify([unbarred.measurements[0].measurement_id, equations(unbarred)]));
  await evaluate(`${ID}.blur()`);
  // Review of SIF-106: the cell Enter goes back to holds the ID the bar wrote - it held the one before, so a slip written in the
  // bar and fixed in the cell left the Specs on the slip, unsaid
  await evaluate(`${ID}.focus()`);
  await evaluate(`(() => { const b = ${BAR}; b.focus(); b.select(); })()`);
  await send('Input.insertText', { text: 'm_totl' });
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  const slip = await settled();
  check('(set-up) the slip m_totl written in the formula bar takes the Specs along, and Enter goes back to the ID cell', slip.measurements[0].measurement_id === 'm_totl'
    && naming(slip, 'm_totl').length === 2 && await evaluate(`document.activeElement === ${ID}`), JSON.stringify([slip.measurements[0].measurement_id, equations(slip)]));
  await retype('m_total');
  await evaluate(`${ID}.blur()`);
  const mended = await settled();
  check('...where m_total typed over the slip takes them along again (review of SIF-106: they stayed on m_totl)', mended.measurements[0].measurement_id === 'm_total'
    && naming(mended, 'm_total').length === 2 && (await evaluate(NOTE)).startsWith('2 Specs (score, score_sq) now use m_total'),
    JSON.stringify([mended.measurements[0].measurement_id, equations(mended), await evaluate(NOTE)]));

  // the Probe chips: a press as a person's, whose mousedown leaves the focus where it is
  await openTab('Specs');
  await evaluate(`(() => { const own = document.execCommand.bind(document); document.execCommand = (command, ...rest) => { if (command !== 'copy') return own(command, ...rest);
    const data = new DataTransfer(); (document.activeElement || document.body).dispatchEvent(new ClipboardEvent('copy', { clipboardData: data, bubbles: true, cancelable: true }));
    window.__copied = data.getData('text/plain'); return true; }; })()`);      // the copy answered here: the system clipboard untouched
  const CHIP = `${EDITORS}.querySelector('.spec-probes button.chip-insert')`;
  const pressChip = async () => {
    const at = await evaluate(`(() => { const r = ${CHIP}.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
    await page.clickAt(at); await sleep(200);
  };
  check('each Probe chip is a button holding its code, the line still "Probes: m_total"', await evaluate(`${CHIP}?.querySelector('code.probe-id')?.textContent === 'm_total'`)
    && (await evaluate(`${EDITORS}.querySelector('.spec-probes').textContent`)) === 'Probes: m_total'
    && (await evaluate(`${CHIP}.title`)).startsWith('m_total: Copies this Probe ID.'), await evaluate(`${CHIP}?.outerHTML ?? 'no chip button'`));
  await pressChip();
  check('with no Equation cell chosen a press copies the ID and says how to put it in', (await evaluate('window.__copied')) === 'm_total'
    && (await evaluate(NOTE)) === 'Copied m_total. With an Equation cell chosen, a press puts the ID in at the cursor.', `${await evaluate('window.__copied')} | ${await evaluate(NOTE)}`);
  const EQ = CELL(1, 'equation');
  await page.setValue(EQ, 'm_total *', { event: 'input', focus: true });
  await evaluate(`${EQ}.setSelectionRange(9, 9)`);
  check('(set-up) an Equation cell chosen: the chip says where its press puts the ID',
    (await evaluate(`${CHIP}.title`)) === 'm_total: Puts this Probe ID into the Equation of score_sq - at the cursor, or at its end - as one Undo step.', await evaluate(`${CHIP}.title`));
  await pressChip();
  const inCell = await evaluate(`({ value: ${EQ}.value, focused: document.activeElement === ${EQ}, at: ${EQ}.selectionStart })`);
  check('a press puts the ID in at the cell\'s cursor, a space before it, the cell keeping the focus with the cursor after it',
    JSON.stringify(inCell) === JSON.stringify({ value: 'm_total * m_total', focused: true, at: 17 }) && (await settled()).targets[1].equation === 'm_total * m_total', JSON.stringify(inCell));
  await evaluate(UNDO);
  check('...as one Undo step of its own: Undo takes the ID back and leaves what was typed', (await settled()).targets[1].equation === 'm_total *',
    (await settled()).targets[1].equation);
  await evaluate(`(() => { const b = ${BAR}; b.focus(); b.select(); })()`);
  await send('Input.insertText', { text: '( + m_total) / 2' });
  await evaluate(`${BAR}.setSelectionRange(1, 1)`);
  await pressChip();
  const inBar = await evaluate(`({ value: ${BAR}.value, focused: document.activeElement === ${BAR}, at: ${BAR}.selectionStart })`);
  check('in the formula bar: the ID at its cursor, written with what the bar holds, the bar keeping the focus',
    JSON.stringify(inBar) === JSON.stringify({ value: '(m_total + m_total) / 2', focused: true, at: 8 }) && (await settled()).targets[1].equation === '(m_total + m_total) / 2',
    JSON.stringify(inBar));
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  await evaluate(UNDO);
  check('...and Enter writes nothing more: one Undo takes the bar\'s text and the ID back', (await settled()).targets[1].equation === 'm_total *',
    (await settled()).targets[1].equation);
  await shot('spec_probe_chips.png');
  // Review of SIF-106: a press sets the cell's text as React tracks it - the ID put into an emptied cell and deleted again left
  // the cell empty while its Spec kept m_total, which came back at the next drawing
  await page.setValue(EQ, '', { event: 'input', focus: true });
  await pressChip();
  const pressed = await evaluate(`${EQ}.value`);
  await evaluate(`${EQ}.setSelectionRange(0, ${EQ}.value.length)`);
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8, nativeVirtualKeyCode: 8 });
  const emptied = await settled();
  check('an ID a press put into an emptied Equation cell, chosen and deleted again, leaves the cell and its Spec empty alike (review of SIF-106: the Spec kept it)',
    pressed === 'm_total' && (await evaluate(`${EQ}.value`)) === '' && emptied.targets[1].equation === '',
    JSON.stringify({ pressed, cell: await evaluate(`${EQ}.value`), spec: emptied.targets[1].equation }));

  // Review of SIF-106: Ctrl+Z pressed in a Probe's ID cell is no typing. score_sq names m_gain before any Probe holds it; m_total
  // typed m_gain takes score along; in the cell again, Ctrl+Z brings back m_total with score on it and score_sq on m_gain as
  // typed - which leaving the cell then rewrote to m_total, with no Undo step of its own
  const ctrl = async (key, vk) => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key, code: `Key${key.toUpperCase()}`, windowsVirtualKeyCode: vk, modifiers: 2 }); await sleep(250); };
  await page.setValue(EQ, 'm_gain', { event: 'input', focus: true });
  await evaluate(`${EQ}.blur()`);
  await openTab('Probes');
  await retype('m_gain');
  await evaluate(`${ID}.blur()`);
  const gained = await settled();
  check('(set-up) score_sq names m_gain first; m_total typed m_gain takes score along', gained.measurements[0].measurement_id === 'm_gain'
    && JSON.stringify(equations(gained)) === '["m_gain","m_gain"]', JSON.stringify(equations(gained)));
  await evaluate(`${ID}.focus()`);
  await ctrl('z', 90);
  const undoneInCell = await settled();
  await evaluate(`${ID}.blur()`);
  const leftCell = await settled();
  check('Ctrl+Z in the ID cell brings back m_total with score on it, and leaving the cell leaves score_sq on m_gain (review of SIF-106: rewritten to m_total)',
    undoneInCell.measurements[0].measurement_id === 'm_total' && leftCell.measurements[0].measurement_id === 'm_total'
    && JSON.stringify(equations(leftCell)) === '["m_total","m_gain"]' && (await evaluate(NOTE)).startsWith('Undo: '),
    JSON.stringify({ equations: equations(leftCell), note: await evaluate(NOTE) }));
  // ...while an ID typed there, taken back with Ctrl+Z and brought back with Ctrl+Y, still has its Spec along: Ctrl+Z lets it take
  // the Spec along first, as leaving the cell (and the toolbar's Undo) does, so the Redo brings both back
  await retype('m_x');
  await ctrl('z', 90);
  const typedUndone = await settled();
  await ctrl('y', 89);
  await evaluate(`${ID}.blur()`);
  const redone = await settled();
  check('...an ID typed in the cell, taken back with Ctrl+Z and brought back with Ctrl+Y there, has score along once the cell is left',
    typedUndone.measurements[0].measurement_id === 'm_total' && JSON.stringify(equations(typedUndone)) === '["m_total","m_gain"]'
    && redone.measurements[0].measurement_id === 'm_x' && JSON.stringify(equations(redone)) === '["m_x","m_gain"]', JSON.stringify([equations(typedUndone), equations(redone)]));

  // Review of SIF-106: a refused ID's memory goes with its row when Delete selected and Undo move it. A second Probe takes m_gain,
  // which score_sq names, and m-gain is refused there; with the row above deleted, the next ID typed in it found no memory at
  // its new place and left score_sq on m_gain, unsaid
  const TOOL = name => `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(name)})`;
  const rowCount = n => until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === ${n}`, 30);
  const typeId = async (row, text) => { const box = CELL(row, 'measurement_id'); await evaluate(`${box}.focus(); ${box}.select()`);
    for (const ch of text) { await send('Input.insertText', { text: ch }); await sleep(40); }
    await evaluate(`${box}.blur()`); };
  const tickFirst = async () => { await evaluate(`${EDITORS}.querySelectorAll('table.editor tbody tr')[0].querySelector('td.sel input').click()`); await sleep(150); };
  await evaluate(`${TOOL('Add')}.click()`);
  await rowCount(2);
  await typeId(1, 'm_gain');
  await typeId(1, 'm-gain');
  const twoProbes = await settled();
  check('(set-up) a second Probe takes m_gain, which score_sq names; m-gain typed there leaves score_sq on m_gain, said in amber',
    JSON.stringify(twoProbes.measurements.map(m => m.measurement_id)) === '["m_x","m-gain"]' && JSON.stringify(equations(twoProbes)) === '["m_x","m_gain"]'
    && (await evaluate(NOTE)).startsWith('Spec score_sq still uses m_gain: "m-gain" is not letters') && await evaluate(WARNED), await evaluate(NOTE));
  await tickFirst(); await evaluate(`${TOOL('Delete selected')}.click()`);
  await rowCount(1);
  await evaluate(UNDO);
  await rowCount(2);
  await typeId(1, 'm.gain');
  check('...the row above deleted and the Delete undone, an ID typed in the row still says score_sq stays on m_gain: the memory came back with the row',
    (await evaluate(NOTE)).startsWith('Spec score_sq still uses m_gain: "m.gain" is not letters') && await evaluate(WARNED), await evaluate(NOTE));
  await tickFirst(); await evaluate(`${TOOL('Delete selected')}.click()`);
  await rowCount(1);
  await typeId(0, 'm_gain2');
  const movedUp = await settled();
  check('...and with the row above deleted, the next ID typed in the row takes score_sq along from m_gain (review of SIF-106: it stayed, unsaid)',
    JSON.stringify(movedUp.measurements.map(m => m.measurement_id)) === '["m_gain2"]' && equations(movedUp)[1] === 'm_gain2'
    && (await evaluate(NOTE)).startsWith("Spec score_sq now uses m_gain2, the Probe's new ID."), JSON.stringify({ equations: equations(movedUp), note: await evaluate(NOTE) }));

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
