// Browser check of the editors' formula bar (record 7.175, user: "add excel like single cell whole row text edit somewhere for
// long text editing which cant show everything in the cell"). Hermetic: reads pass to the backend under test, every writing
// request is refused - the page may write nothing of its own.
// What it pins:
//   - before a cell is chosen the bar says so and takes nothing; a chosen cell is marked and the bar names it (column · row ID),
//     shows its whole value in a box much wider than the cell, and has the column's format in the tooltip of its name;
//   - typing in the bar changes nothing until Enter: Enter writes the whole text into the cell as one Undo step and goes back to
//     the cell; Undo and Redo take it back and again; Esc keeps the cell as it was;
//   - a number column takes a number as its cell does (2.5e-3), and refuses "abc" in words without changing the cell;
//   - typing in the cell shows at once in the bar; a list (Probes' analysis) is shown, not typed, with its choices in words.
// Run: bash frontend/scripts/run_checks.sh --only formula_bar_check. About 20 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('formula');
const BAR = `document.querySelector('.formula-bar textarea')`, WHERE = `document.querySelector('.formula-bar .formula-where')`;
const TAB = key => `[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === ${JSON.stringify(key)})`;
const CELL = (row, field) => `document.querySelector('table.editor tbody > tr:nth-child(${row + 1}) > td[data-field="${field}"]')`;
const LONG = 'FIXTURE note: ' + 'a long text that no cell of the table can show at once, '.repeat(4).trim();

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  await page.intercept(['*/api/config/validate'], params => page.pass(params.requestId), { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });   // focus events as in a window that has the focus
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors table.editor tbody tr')`, 200));
  await sleep(800);
  const key = (k, code, vk) => [{ type: 'keyDown', key: k, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk }, { type: 'keyUp', key: k, code, windowsVirtualKeyCode: vk }];
  const press = async (...events) => { for (const e of events) await send('Input.dispatchKeyEvent', e); await sleep(150); };
  const typeInBar = async text => { await evaluate(`(() => { const b = ${BAR}; b.focus(); b.select(); })()`); await send('Input.insertText', { text }); await sleep(150); };
  // a cell chosen as a person does: a click on it
  const click = async expression => {
    const r = await evaluate(`(() => { const e = ${expression}; e.scrollIntoView({ block: 'center' }); const b = e.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; })()`);
    for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: r.x, y: r.y, button: 'left', clickCount: 1 });
    await sleep(200);
  };
  const stored = expression => `(c => ${expression})(JSON.parse(localStorage.getItem('gator-workbench-config-v1')))`;

  check('before a cell is chosen the bar says so and takes nothing', await evaluate(`${WHERE}.textContent === 'No cell chosen' && ${BAR}.disabled`));

  // ---- a text cell: shown whole, typed in the bar, written by Enter, one Undo step ---------------------------------------
  await click(`${CELL(0, 'notes')}.querySelector('input')`);
  const first = await evaluate(`document.activeElement === ${CELL(0, 'notes')}.querySelector('input')`);
  const before = config.parameters[0];
  check('a chosen cell is marked, and the bar names it (column and row ID) with its whole value', first && await evaluate(`${CELL(0, 'notes')}.classList.contains('active-cell')`)
    && await evaluate(`${WHERE}.textContent === ${JSON.stringify(`notes · ${before.variable_id}`)} && ${BAR}.value === ${JSON.stringify(before.notes ?? '')} && !${BAR}.readOnly`),
    await evaluate(`${WHERE}.textContent + ' | ' + ${BAR}.value`));
  check('the name of the cell carries its column\'s format in its tooltip', await evaluate(`${WHERE}.title.startsWith('notes (string') && ${WHERE}.title.includes('Free text')`), await evaluate(`${WHERE}.title`));
  const widths = await evaluate(`({ bar: ${BAR}.getBoundingClientRect().width, cell: ${CELL(0, 'notes')}.getBoundingClientRect().width })`);
  check('the bar is far wider than the cell', widths.bar > 3 * widths.cell, JSON.stringify(widths));
  await typeInBar(LONG);
  check('typing in the bar changes nothing until Enter', await evaluate(`${CELL(0, 'notes')}.querySelector('input').value === ${JSON.stringify(before.notes ?? '')}`));
  await page.shot(path.join(out, 'formula-1-typing.png'), `document.querySelector('.editors')`, { maxHeight: 700 });
  await press(...key('Enter', 'Enter', 13));
  check('Enter writes the whole text into the cell and goes back to it', await page.until(`${CELL(0, 'notes')}.querySelector('input').value === ${JSON.stringify(LONG)}`, 30)
    && await evaluate(`document.activeElement === ${CELL(0, 'notes')}.querySelector('input')`));
  check('...and the configuration keeps it', await page.until(stored(`c.parameters[0].notes === ${JSON.stringify(LONG)}`), 30));
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('one Undo takes the whole text back', await page.until(`${CELL(0, 'notes')}.querySelector('input').value === ${JSON.stringify(before.notes ?? '')} && ${BAR}.value === ${JSON.stringify(before.notes ?? '')}`, 30));
  await evaluate(`document.querySelector('section.editors button[title^="Redo:"]').click()`);
  check('...and Redo brings it again', await page.until(`${BAR}.value === ${JSON.stringify(LONG)}`, 30));
  await typeInBar('FIXTURE: not wanted');
  await press(...key('Escape', 'Escape', 27));
  check('Esc keeps the cell as it was and shows its value again', await evaluate(`${CELL(0, 'notes')}.querySelector('input').value === ${JSON.stringify(LONG)} && ${BAR}.value === ${JSON.stringify(LONG)}`)
    && await evaluate(`document.activeElement === ${CELL(0, 'notes')}.querySelector('input')`));
  await page.setValue(`${CELL(0, 'notes')}.querySelector('input')`, 'FIXTURE typed in the cell', { event: 'input', focus: true });
  check('typing in the cell shows at once in the bar', await page.until(`${BAR}.value === 'FIXTURE typed in the cell'`, 30));

  // ---- a number cell: read as its cell reads it; a word refused in words ---------------------------------------------------
  await evaluate(`${TAB('targets')}.click()`);
  await sleep(300);
  check('another tab: no cell chosen', await evaluate(`${WHERE}.textContent === 'No cell chosen'`));
  const spec = config.targets[0];
  await click(`${CELL(0, 'lower')}.querySelector('input')`);
  check('a number cell is named in the bar', await evaluate(`${WHERE}.textContent === ${JSON.stringify(`lower · ${spec.metric_id}`)}`), await evaluate(`${WHERE}.textContent`));
  await typeInBar('abc');
  await press(...key('Enter', 'Enter', 13));
  check('"abc" is refused in words, the cell unchanged, the bar still in hand', await evaluate(`document.querySelector('.formula-problem')?.textContent.includes('is not a number')`)
    && await evaluate(stored(`c.targets[0].lower === ${JSON.stringify(spec.lower ?? null)}`)) && await evaluate(`document.activeElement === ${BAR}`));
  await typeInBar('2.5e-3');
  await press(...key('Enter', 'Enter', 13));
  check('2.5e-3 is taken as the number 0.0025', await page.until(stored('c.targets[0].lower === 0.0025'), 30) && !(await evaluate(`!!document.querySelector('.formula-problem')`)));

  // ---- a list: shown, not typed ------------------------------------------------------------------------------------------------
  await evaluate(`${TAB('measurements')}.click()`);
  await sleep(300);
  await evaluate(`${CELL(0, 'analysis')}.querySelector('select').focus()`);
  await sleep(150);
  const list = await evaluate(`({ value: ${BAR}.value, readOnly: ${BAR}.readOnly, title: ${BAR}.title })`);
  check('a list is shown, not typed: its value, and its choices in words', list.readOnly && list.value === config.measurements[0].analysis
    && list.title.startsWith('A list: choose it in the cell') && list.title.includes('dc | ac'), JSON.stringify(list));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
