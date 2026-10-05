// Browser check of record 7.180 - the editor tables as a spreadsheet (design advice 4 and 6; the user's "go on"). Hermetic: reads
// pass to the backend under test, validation is answered here, every writing request is refused.
// What it pins:
//   - tied rows: a Parameters row that follows a leader (binding_group) starts folded under it, the rows keeping their order;
//     the leader's first cell counts them and opens and folds them; an open tied row is marked; a tied row with an error
//     report is never folded away;
//   - keys: Up and Down go to the same column of the row above or below, passing folded rows; Enter goes down and
//     Shift+Enter up; a list keeps its own keys;
//   - a block pasted from Excel (tab-separated lines) fills the rows in view from the cell down and the columns from it right,
//     as one Undo step; a text a column cannot read is named and left as it was; lines below the last row are named; cells
//     that a leader decides are kept.
// Run: bash frontend/scripts/run_checks.sh --only sheet_check. About 20 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('sheet');
const ROW = n => `document.querySelector('table.editor tbody > tr:nth-child(${n + 1})')`;
const BOX = (n, field) => `${ROW(n)}.querySelector('td[data-field="${field}"]').querySelector('input, select')`;

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  const leaders = config.parameters.map((p, i) => [i, config.parameters.filter(q => q.binding_group === p.variable_id).length]).filter(([, n]) => n > 0);
  const tied = config.parameters.map((p, i) => [i, p.binding_group]).filter(([, g]) => g).map(([i]) => i);
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  let report = validConfiguration();                     // what the page is told about its configuration; one phase reports an error
  await page.intercept(['*/api/config/validate'], params => page.fulfil(params.requestId, 200, report), { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors table.editor tbody tr')`, 200));
  await sleep(800);
  const key = (k, code, vk, shift = false) => [{ type: 'keyDown', key: k, code, windowsVirtualKeyCode: vk, modifiers: shift ? 8 : 0 }, { type: 'keyUp', key: k, code, windowsVirtualKeyCode: vk, modifiers: shift ? 8 : 0 }];
  const press = async events => { for (const e of events) await send('Input.dispatchKeyEvent', e); await sleep(150); };
  const at = () => evaluate(`(() => { const td = document.activeElement?.closest('td[data-field]'); return td ? [Number(td.closest('tr').dataset.index), td.dataset.field] : null; })()`);
  const stored = expression => `(c => ${expression})(JSON.parse(localStorage.getItem('gator-workbench-config-v1')))`;

  // ---- tied rows ------------------------------------------------------------------------------------------------------------------------
  check('the task has tied rows to fold', leaders.length > 0 && tied.length > 0, JSON.stringify({ leaders, tied }));
  const rows = await evaluate(`[...document.querySelectorAll('table.editor tbody > tr')].map(tr => ({ index: Number(tr.dataset.index), hidden: tr.hidden,
    toggle: tr.querySelector('.tie-toggle')?.textContent ?? null, id: tr.querySelector('td[data-field="variable_id"] input')?.value }))`);
  check('the rows keep their order, and each tied row starts folded under its leader', JSON.stringify(rows.map(r => r.id)) === JSON.stringify(config.parameters.map(p => p.variable_id))
    && rows.every((r, i) => r.hidden === tied.includes(i)), JSON.stringify(rows));
  check('a leader\'s first cell counts its tied rows', leaders.every(([i, n]) => rows[i].toggle === `▸${n}`), JSON.stringify(rows.map(r => r.toggle)));
  await page.shot(path.join(out, 'sheet-1-folded.png'), `document.querySelector('.editors')`, { maxHeight: 600 });
  const [lead] = leaders[0], follower = config.parameters.findIndex(p => p.binding_group === config.parameters[lead].variable_id);
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`);
  check('pressing it opens them, marked as tied', await page.until(`!${ROW(follower)}.hidden && !!${ROW(follower)}.querySelector('.tie-mark') && ${ROW(lead)}.querySelector('.tie-toggle').getAttribute('aria-expanded') === 'true'`, 20));
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`);
  check('...and folds them again', await page.until(`${ROW(follower)}.hidden`, 20));
  report = validConfiguration({ issues: [{ level: 'error', path: `parameters[${follower}].ratio`, code: 'fixture', message: 'FIXTURE: an error on a tied row' }], blocks_run: true });
  await page.setValue(`${BOX(lead, 'notes')}`, 'FIXTURE: ask again', { event: 'input' });   // a change: the page asks for a new report
  check('a tied row with an error is never folded away', await page.until(`!${ROW(follower)}.hidden`, 60));
  report = validConfiguration();
  await page.setValue(`${BOX(lead, 'notes')}`, '', { event: 'input' });
  check('...and folds again once the report is clean', await page.until(`${ROW(follower)}.hidden`, 60));

  // ---- keys ------------------------------------------------------------------------------------------------------------------------------
  const shownRows = rows.map((r, i) => i).filter(i => !tied.includes(i));
  await evaluate(`(() => { const b = ${BOX(shownRows[0], 'lower')}; b.focus(); b.select(); })()`); await sleep(150);
  await press(key('ArrowDown', 'ArrowDown', 40));
  check('Down goes to the same column of the row below, passing folded rows', JSON.stringify(await at()) === JSON.stringify([shownRows[1], 'lower']), JSON.stringify(await at()));
  await press(key('ArrowUp', 'ArrowUp', 38));
  check('Up comes back', JSON.stringify(await at()) === JSON.stringify([shownRows[0], 'lower']), JSON.stringify(await at()));
  await press(key('Enter', 'Enter', 13));
  check('Enter goes down', JSON.stringify(await at()) === JSON.stringify([shownRows[1], 'lower']), JSON.stringify(await at()));
  await press(key('Enter', 'Enter', 13, true));
  check('Shift+Enter goes up', JSON.stringify(await at()) === JSON.stringify([shownRows[0], 'lower']), JSON.stringify(await at()));

  // ---- a block pasted from Excel ---------------------------------------------------------------------------------------------------------
  const paste = (n, field, text) => evaluate(`(() => { const b = ${BOX(n, field)}; b.focus(); const d = new DataTransfer(); d.setData('text/plain', ${JSON.stringify(text)});
    b.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true })); return true; })()`);
  const block = shownRows.slice(0, 3);
  await paste(block[0], 'lower', '1e-6\t5e-6\r\n2e-6\t9e-6\r\n3e-6\t7e-6\r\n');
  check('a block fills the rows in view from the cell down and the columns from it right', await page.until(stored(
    `${JSON.stringify(block)}.every((n, k) => c.parameters[n].lower === [1e-6, 2e-6, 3e-6][k] && c.parameters[n].upper === [5e-6, 9e-6, 7e-6][k])`), 30),
    JSON.stringify(await evaluate(stored(`c.parameters.map(p => [p.lower, p.upper])`))));
  check('...said under the formula bar', (await evaluate(`document.querySelector('.paste-note')?.textContent`)) === 'Pasted 6 cells into 3 rows (one Undo step).', await evaluate(`document.querySelector('.paste-note')?.textContent`));
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('one Undo takes the whole block back', await page.until(stored(`${JSON.stringify(block)}.every(n => c.parameters[n].lower === ${JSON.stringify(config.parameters.map(p => p.lower))}[n])`), 30));
  await paste(block[0], 'lower', 'abc\t4e-6');
  check('a text the column cannot read is named and left as it was; the rest is taken', await page.until(stored(`c.parameters[${block[0]}].upper === 4e-6`), 30)
    && (await evaluate(`document.querySelector('.paste-note').textContent`)).includes('Not read, left as they were: "abc" in lower')
    && await evaluate(stored(`c.parameters[${block[0]}].lower === ${JSON.stringify(config.parameters[block[0]].lower)}`)), await evaluate(`document.querySelector('.paste-note')?.textContent`));
  const last = shownRows[shownRows.length - 1];
  await paste(last, 'notes', 'a\nb\nc');
  check('lines below the last row are named, not added', (await evaluate(`document.querySelector('.paste-note').textContent`)).includes('2 lines below the last row left out'), await evaluate(`document.querySelector('.paste-note')?.textContent`));
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`); await sleep(200);
  await paste(follower, 'lower', '1\t2');
  check('cells a leader decides are kept: nothing pasted, said so', (await evaluate(`document.querySelector('.paste-note').textContent`)) === 'Nothing pasted. 2 cells that follow another field kept.'
    && await evaluate(stored(`(c.parameters[${follower}].lower ?? null) === ${JSON.stringify(config.parameters[follower].lower ?? null)}`)), await evaluate(`document.querySelector('.paste-note')?.textContent`));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
