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
//     that a leader decides are kept;
//   - (record 7.208) a bound is written with its prefix and unit in English letters (450 nm, 2 um) in the cell and the
//     formula bar, never a Greek letter; 450n, 0.6 µm and a plain number (in the row's unit) are read; another quantity is
//     refused in words; no Unit column: a row whose parameter becomes m (a multiplier) is a count, and a length again when
//     it is w;
//   - (record 7.182) the tick box and the row's ID stay at the left while the table scrolls sideways, the ID right beside the
//     tick box on Parameters (whose tick-box column a tie toggle widens) and on Specs (a narrow one), also when that column
//     changes size with no new render; nothing covers them, and nothing passing under shows through them;
//   - (record 7.188) the headers in plain words, each field name in its header's tooltip and on the help line a press opens;
//     Ctrl+Z and Ctrl+Y in a cell are the toolbar's Undo and Redo.
// Run: bash frontend/scripts/run_checks.sh --only sheet_check. About 20 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('sheet');
const ROW = n => `document.querySelector('table.editor tbody > tr:nth-child(${n + 1})')`;
const TABS = key => `[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === ${JSON.stringify(key)})`;
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
    && (await evaluate(`document.querySelector('.paste-note').textContent`)).includes('Not read, left as they were: "abc" in Lower')
    && await evaluate(stored(`c.parameters[${block[0]}].lower === ${JSON.stringify(config.parameters[block[0]].lower)}`)), await evaluate(`document.querySelector('.paste-note')?.textContent`));
  const last = shownRows[shownRows.length - 1];
  await paste(last, 'notes', 'a\nb\nc');
  check('lines below the last row are named, not added', (await evaluate(`document.querySelector('.paste-note').textContent`)).includes('2 lines below the last row left out'), await evaluate(`document.querySelector('.paste-note')?.textContent`));
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`); await sleep(200);
  await paste(follower, 'lower', '1\t2');
  check('cells a leader decides are kept: nothing pasted, said so', (await evaluate(`document.querySelector('.paste-note').textContent`)) === 'Nothing pasted. 2 cells that follow another field kept.'
    && await evaluate(stored(`(c.parameters[${follower}].lower ?? null) === ${JSON.stringify(config.parameters[follower].lower ?? null)}`)), await evaluate(`document.querySelector('.paste-note')?.textContent`));

  // ---- one way of writing a quantity (record 7.208, replacing 7.181's readable numbers): every bound is written with its prefix
  //      and unit, typed in any form; a plain number is in the row's unit; no Unit column - a row's quantity follows its parameter
  //      ---------------------------------------------------------------------------------------------------------------------------
  const metre = config.parameters.findIndex((p, i) => p.unit === 'm' && typeof p.lower === 'number' && p.lower > 0 && p.lower < 0.01 && !tied.includes(i));
  if (metre >= 0) {
    await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`); await sleep(300);   // the pastes above undone
    const NOTE = `document.querySelector('.paste-note')?.textContent ?? ''`, shownOf = field => evaluate(`${BOX(metre, field)}.value`);
    const typeIn = async (field, text) => { await page.setValue(BOX(metre, field), text, { event: 'input', focus: true }); await evaluate(`${BOX(metre, field)}.blur()`); await sleep(250); };
    const shownNumber = await shownOf('lower');
    check(`a bound in metres is written with its prefix and unit (${config.parameters[metre].lower} m as ${shownNumber})`, /^[\d.]+ [fpnum]?m$/.test(shownNumber), shownNumber);
    await evaluate(`${BOX(metre, 'lower')}.focus()`); await sleep(200);
    check('...and the formula bar writes it the same way', (await evaluate(`document.querySelector('.formula-bar textarea').value`)) === shownNumber,
      await evaluate(`document.querySelector('.formula-bar textarea').value`));
    await typeIn('lower', '450n');
    check('"450n" typed is the number 4.5e-7, written 450 nm', await page.until(stored(`c.parameters[${metre}].lower === 4.5e-7`), 30) && (await shownOf('lower')) === '450 nm',
      `${await evaluate(stored(`c.parameters[${metre}].lower`))} / ${await shownOf('lower')}`);
    await typeIn('lower', '0.6 µm');
    check('"0.6 µm" typed is 6e-7, written 600 nm', await page.until(stored(`c.parameters[${metre}].lower === 6e-7`), 30) && (await shownOf('lower')) === '600 nm',
      `${await evaluate(stored(`c.parameters[${metre}].lower`))} / ${await shownOf('lower')}`);
    await typeIn('lower', '0.000002');
    check('a plain number is in the row\'s unit, metres: 0.000002 is 2 um', await page.until(stored(`c.parameters[${metre}].lower === 0.000002`), 30) && (await shownOf('lower')) === '2 um',
      `${await evaluate(stored(`c.parameters[${metre}].lower`))} / ${await shownOf('lower')}`);
    await typeIn('lower', '5 mV');
    check('another quantity is refused in words and changes nothing', (await evaluate(stored(`c.parameters[${metre}].lower`))) === 0.000002
      && (await evaluate(NOTE)).includes('is a voltage; this row holds a length (m)') && (await shownOf('lower')) === '2 um', await evaluate(NOTE));
    // No Unit column in Parameters since record 7.208 (user: "can you delete the unit column but keep the rules for value"): a
    // row's quantity follows its parameter - w is a length, m a multiplier (a count).
    check('Parameters show no Unit column', !(await evaluate(`[...document.querySelectorAll('section.editors table.editor thead th')].some(h => h.dataset.field === 'unit')`)));
    const parameterOf = config.parameters[metre].parameter_name;
    await typeIn('parameter_name', 'm');
    check('a row whose parameter becomes m (a multiplier) is a count: plain numbers, a length refused', await page.until(stored(`c.parameters[${metre}].unit === 'count'`), 30)
      && (await shownOf('lower')) === '0.000002', `${await evaluate(stored(`c.parameters[${metre}].unit`))} / ${await shownOf('lower')}`);
    await typeIn('lower', '4 um');
    check('...a length typed into it is refused in words', (await evaluate(NOTE)).includes('is a length; this row holds a count'), await evaluate(NOTE));
    await typeIn('parameter_name', parameterOf);
    check(`back to ${parameterOf}: a length again (metres)`, await page.until(stored(`c.parameters[${metre}].unit === 'm'`), 30)
      && (await shownOf('lower')) === '2 um', `${await evaluate(stored(`c.parameters[${metre}].unit`))} / ${await shownOf('lower')}`);
    await typeIn('lower', '3n');
    check('...and its values read as lengths again', await page.until(stored(`c.parameters[${metre}].lower === 3e-9`), 30) && (await shownOf('lower')) === '3 nm', await shownOf('lower'));
    check('no cell of the table writes a Greek letter (user: "dont use greek characters for unit")',
      !(await evaluate(`[...document.querySelectorAll('section.editors table.editor input')].some(i => /[µμΩ°]/.test(i.value))`)));
  } else check('the task has a bound in metres to read', false, JSON.stringify(config.parameters.map(p => [p.unit, p.lower])));

  // ---- the tick box and the row's ID in view while the table scrolls sideways (record 7.182) -------------------------------------------
  for (const [tab, id] of [['parameters', 'variable_id'], ['targets', 'metric_id']]) {
    await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === '${tab}').click()`); await sleep(400);
    // the table's box made narrower than the table, as on a small screen, and scrolled to its right end
    await evaluate(`document.querySelector('section.editors .scroll').style.maxWidth = '420px'`); await sleep(300);
    await evaluate(`(() => { const box = document.querySelector('section.editors .scroll'); box.scrollLeft = box.scrollWidth; })()`); await sleep(300);
    const seen = await evaluate(`(() => { const box = document.querySelector('section.editors .scroll');
      const edge = box.getBoundingClientRect().left + box.clientLeft, row = [...box.querySelectorAll('tbody > tr')].find(tr => !tr.hidden);
      const tick = box.querySelector('thead th.sel').getBoundingClientRect(), head = box.querySelector('thead th[data-field="${id}"]').getBoundingClientRect();
      const cell = row.querySelector('td[data-field="${id}"]'), c = cell.getBoundingClientRect(), t = row.querySelector('td.sel input').getBoundingClientRect();
      const at = r => document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { scrolled: box.scrollLeft, tick: Math.round(tick.width), tickAt: +(tick.left - edge).toFixed(1), idAt: +(head.left - tick.right).toFixed(1),
        cellAt: +(c.left - tick.right).toFixed(1), idOnTop: cell.contains(at(c)), tickOnTop: at(t) === row.querySelector('td.sel input'),
        edge: getComputedStyle(cell, '::after').content !== 'none' }; })()`);
    const name = tab === 'parameters' ? 'Parameters' : 'Specs';
    check(`${name} scrolled sideways: the tick box stays at the left, the row's ID right beside it, neither covered`,
      seen.scrolled > 50 && Math.abs(seen.tickAt) < 1.5 && Math.abs(seen.idAt) < 1.5 && Math.abs(seen.cellAt) < 1.5 && seen.idOnTop && seen.tickOnTop, JSON.stringify(seen));
    // nothing passing under shows through the sticky heads: the tick-box head and its line with the ID, empty, have no text
    // pixels (a collapsed table drew that line with the scrolled columns and let their text through its sliver). A text pixel
    // stands out from the head's own colour, light on the dark look (record 7.360) as dark on a light one.
    let dark = 0;
    const ground = await evaluate(`(() => { const m = getComputedStyle(document.querySelector('thead th.sel')).backgroundColor.match(/[\\d.]+/g).map(Number); return 0.3 * m[0] + 0.59 * m[1] + 0.11 * m[2]; })()`);
    for (const back of [0, 13, 29, 47]) {                  // at four places, so that some text is under the line whatever its widths
      await evaluate(`(() => { const box = document.querySelector('section.editors .scroll'); box.scrollLeft = box.scrollWidth - box.clientWidth - ${back}; })()`); await sleep(150);
      const clip = await evaluate(`(() => { const s = document.querySelector('thead th.sel').getBoundingClientRect(), i = document.querySelector('thead th[data-field="${id}"]').getBoundingClientRect();
        return { x: s.left, y: s.top, width: i.left + 4 - s.left, height: s.height - 3, scale: 1 }; })()`);
      const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
      dark += await evaluate(`(async () => { const img = new Image(); img.src = 'data:image/png;base64,${data}'; await img.decode();
        const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const g = c.getContext('2d'); g.drawImage(img, 0, 0);
        const d = g.getImageData(0, 0, c.width, c.height).data; let n = 0; for (let k = 0; k < d.length; k += 4) if (Math.abs(0.3 * d[k] + 0.59 * d[k + 1] + 0.11 * d[k + 2] - ${ground}) > 60) n++; return n; })()`);
    }
    check(`...and nothing passing under shows through the tick-box head or its line with the ID (${name})`, dark === 0, `${dark} text pixels at four scroll places`);
    if (tab === 'parameters') await page.shot(path.join(out, 'sheet-2-scrolled.png'), `document.querySelector('.editors')`, { maxHeight: 600 });
    await evaluate(`document.querySelector('section.editors .scroll').scrollLeft = 0`); await sleep(300);
    const back = await evaluate(`getComputedStyle([...document.querySelectorAll('table.editor tbody > tr')].find(tr => !tr.hidden).querySelector('td[data-field="${id}"]'), '::after').content`);
    check(`...and a line marks the ID's edge only while columns pass under it (${name})`, seen.edge && back === 'none', JSON.stringify({ scrolled: seen.edge, back }));
    if (tab === 'parameters') {                             // the tick-box column changing size with no new render, as in a narrower window
      const beside = () => evaluate(`(() => { const box = document.querySelector('section.editors .scroll'); box.scrollLeft = box.scrollWidth;
        const tick = box.querySelector('thead th.sel').getBoundingClientRect(), id = box.querySelector('thead th[data-field="${id}"]').getBoundingClientRect();
        return [Math.round(tick.width), +(id.left - tick.right).toFixed(1)]; })()`);
      await evaluate(`document.querySelector('thead th.sel').style.minWidth = '64px'`); await sleep(300);
      const wide = await beside();
      await evaluate(`document.querySelector('thead th.sel').style.minWidth = ''`); await sleep(300);
      const narrow = await beside();
      check('...and the ID follows the tick-box column when it changes size without a new render', wide[0] >= 64 && narrow[0] < 64
        && Math.abs(wide[1]) < 1.5 && Math.abs(narrow[1]) < 1.5, JSON.stringify({ wide, narrow }));
    }
    await evaluate(`document.querySelector('section.editors .scroll').style.maxWidth = ''`);
  }

  // ---- the headers in plain words, the field names in their tooltips (record 7.188) -----------------------------------------------------
  await evaluate(`${TABS('parameters')}.click()`); await sleep(400);
  const heads = await evaluate(`[...document.querySelectorAll('table.editor thead th[data-field]')].map(h => [h.dataset.field, h.textContent.replace(/ \\*$/, ''), h.title.split(':')[0]])`);
  check('the headers read in plain words, each with its field name in its tooltip', JSON.stringify(heads.slice(0, 3).map(h => h[1])) === JSON.stringify(['ID', 'Instance', 'Parameter'])
    && heads.some(([f, l]) => f === 'binding_group' && l === 'Tied to') && heads.every(([f, , t]) => t === f), JSON.stringify(heads));
  await evaluate(`document.querySelector('table.editor thead th[data-field="binding_group"]').click()`); await sleep(200);
  const help = await evaluate(`document.querySelector('.editors p.guidance')?.textContent ?? ''`);
  check('...and a header press names both on the help line', help.startsWith('Tied to (binding_group, string'), help);
  await evaluate(`document.querySelector('.editors p.guidance').click()`);

  // ---- Ctrl+Z and Ctrl+Y in a cell (record 7.188) ------------------------------------------------------------------------------------
  const ctrlKey = async (k, vk) => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: k, code: `Key${k.toUpperCase()}`, windowsVirtualKeyCode: vk, modifiers: 2 }); await sleep(250); };
  const first = shownRows[0], noteBefore = await evaluate(stored(`c.parameters[${first}].notes ?? ''`));
  await page.setValue(BOX(first, 'notes'), 'FIXTURE undo me', { event: 'input', focus: true });
  await page.until(stored(`c.parameters[${first}].notes === 'FIXTURE undo me'`), 30);
  await evaluate(`${BOX(first, 'notes')}.focus()`); await sleep(150);
  await ctrlKey('z', 90);
  check('Ctrl+Z in a cell is the toolbar\'s Undo: the whole entry goes back, in the cell too', await page.until(stored(`(c.parameters[${first}].notes ?? '') === ${JSON.stringify(noteBefore)}`), 30)
    && (await evaluate(`${BOX(first, 'notes')}.value`)) === noteBefore, await evaluate(`${BOX(first, 'notes')}.value`));
  await ctrlKey('y', 89);
  check('...and Ctrl+Y redoes it', await page.until(stored(`c.parameters[${first}].notes === 'FIXTURE undo me'`), 30) && (await evaluate(`${BOX(first, 'notes')}.value`)) === 'FIXTURE undo me');

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
