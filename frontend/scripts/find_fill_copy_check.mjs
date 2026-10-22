// Browser check of record 7.184 - the editor tables' last spreadsheet pieces (design advice 4; the user's "go on"). Hermetic:
// reads pass to the backend under test, validation is answered here, every writing request is refused, and the page's copy
// command is answered here too, so nothing reaches the system clipboard.
// What it pins:
//   - the find box: only the rows whose text cells in view hold every word typed stay in view, folded or not, with a count;
//     Enter goes to the first of them; a chosen cell whose row went out of view is let go; Delete selected takes only the
//     ticked rows in view; Esc clears the box and the folding is back;
//   - Ctrl+D: the cell takes the value of the row above in view; in a ticked row, the topmost ticked row's value goes into the
//     other ticked rows; a cell its leader decides is kept; an ID is not filled; one Undo step;
//   - Ctrl+C: the cell alone, or the ticked rows in view with a header line; with text chosen inside the box the browser copies
//     that text as ever; the Copy button takes every row in view; a copied block pasted back skips its header line;
//   - one write path for typing, pasting and filling: a pasted output name renames its Probe ID and the equations using it;
//     a pasted limit keeps the objective only where the two still pair;
//   - Add, Delete selected and the tick boxes (branch record SIF-96): Delete says what went - the rows, one folded away, the
//     tied rows that now follow nothing, the Specs using a deleted Probe - and gives the focus to the row now in its place, or
//     to Add; Add clears a Find text the new row does not hold and chooses the new row's ID (a Maestro output's Output name);
//     the header's box ticks every row in view, half ticked while only some are; Shift+click ticks a span of rows in view.
// Run: bash frontend/scripts/run_checks.sh --only find_fill_copy_check. About 25 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('find-fill-copy');
const ROWS = `[...document.querySelectorAll('table.editor tbody > tr')]`;
const ROW = id => `${ROWS}.find(tr => (tr.querySelector('td[data-field] input')?.value ?? '') === ${JSON.stringify(id)})`;
const BOX = (id, field) => `${ROW(id)}.querySelector('td[data-field="${field}"]').querySelector('input, select')`;
const TAB = key => `[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === ${JSON.stringify(key)})`;
const FIND = `document.querySelector('.toolbar input.find-rows')`;
const NOTE = `(document.querySelector('.paste-note')?.textContent ?? '')`;
const SHOWN = `${ROWS}.filter(tr => !tr.hidden).map(tr => tr.querySelector('td[data-field] input')?.value)`;
const UNDO = `document.querySelector('section.editors button[title^="Undo:"]').click()`;

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  // the first Probe read as a Maestro output, whose ID follows its output name - so that a pasted name can rename it
  const probe = config.measurements[0];
  config.measurements = config.measurements.map((m, i) => i === 0 ? { ...m, result_source: 'ade_output', source_name: m.measurement_id.replace(/^m_/, '') } : m);
  const P = config.parameters, ids = P.map(p => p.variable_id);
  const tiedTo = id => P.filter(p => p.binding_group === id).map(p => p.variable_id);
  const leaders = ids.filter(id => tiedTo(id).length), plain = ids.filter(id => !tiedTo(id).length && !P.find(p => p.variable_id === id).binding_group);
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  await page.intercept(['*/api/config/validate'], params => page.fulfil(params.requestId, 200, validConfiguration()), { others: 'read' });
  await page.seed({ config, when: 'once' });
  // the copy command answered here: what the page puts on the clipboard is kept on the window, the system clipboard untouched
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `document.execCommand = function (command) {
    if (command !== 'copy') return false;
    const data = new DataTransfer();
    (document.activeElement || document.body).dispatchEvent(new ClipboardEvent('copy', { clipboardData: data, bubbles: true, cancelable: true }));
    window.__copied = data.getData('text/plain'); window.__copies = (window.__copies || 0) + 1; return true; };` });
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors table.editor tbody tr') && !!${FIND}`, 200));
  await sleep(800);
  const stored = expression => evaluate(`(c => ${expression})(JSON.parse(localStorage.getItem('gator-workbench-config-v1')))`);
  const storedUntil = (expression, tenths = 30) => page.until(`(c => ${expression})(JSON.parse(localStorage.getItem('gator-workbench-config-v1')))`, tenths);
  const findText = async text => { await page.setValue(FIND, text, { event: 'input' }); await sleep(250); };
  const ctrl = async (key, vk) => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key, code: `Key${key.toUpperCase()}`, windowsVirtualKeyCode: vk, modifiers: 2 }); await sleep(250); };
  // a cell chosen as a person does (a click), with nothing chosen inside its text
  const choose = async expression => {
    const r = await evaluate(`(() => { const e = ${expression}; e.scrollIntoView({ block: 'center' }); const b = e.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; })()`);
    await page.clickAt(r);
    await sleep(150);
    await evaluate(`(() => { const e = document.activeElement; if (e instanceof HTMLInputElement && e.type !== 'checkbox') e.setSelectionRange(0, 0); })()`);
  };
  const tick = (id, on = true) => evaluate(`(() => { const b = ${ROW(id)}.querySelector('td.sel input'); if (b.checked !== ${on}) b.click(); })()`);
  check('the task has tied rows and untied rows to work with', leaders.length > 0 && plain.length >= 1 && ids.length >= 4, JSON.stringify({ leaders, plain }));

  // ---- the find box ------------------------------------------------------------------------------------------------------------------
  const [lead] = leaders, [follower] = tiedTo(lead), last = plain[plain.length - 1];
  const leadRow = P.find(p => p.variable_id === lead), followerRow = P.find(p => p.variable_id === follower);
  check('before a find, the tied rows are folded', JSON.stringify(await evaluate(SHOWN)) === JSON.stringify(ids.filter(id => !P.find(p => p.variable_id === id).binding_group)), JSON.stringify(await evaluate(SHOWN)));
  await choose(BOX(lead, 'notes'));
  await findText(followerRow.instance_path);
  const one = await evaluate(SHOWN);
  const texts = p => ['variable_id', 'instance_path', 'parameter_name', 'unit', 'binding_group', 'notes'].map(f => p[f] ?? '').join('\n').toLowerCase();
  check('a find shows only the rows that hold the text - a folded tied row too - and counts them', JSON.stringify(one) === JSON.stringify(P.filter(p => texts(p).includes(followerRow.instance_path.toLowerCase())).map(p => p.variable_id))
    && one.includes(follower) && (await evaluate(`document.querySelector('.toolbar .find-count')?.textContent`)) === `${one.length}/${ids.length}`,
    `${JSON.stringify(one)} ${await evaluate(`document.querySelector('.toolbar .find-count')?.textContent`)}`);
  check('...and a chosen cell whose row went out of view is let go', one.includes(lead) || (await evaluate(`document.querySelector('.formula-bar .formula-where').textContent`)) === 'No cell chosen',
    await evaluate(`document.querySelector('.formula-bar .formula-where').textContent`));
  await page.shot(path.join(out, 'find-1-one-row.png'), `document.querySelector('.editors')`, { maxHeight: 520 });
  const words = `${leadRow.variable_id.split('_')[0]} ${leadRow.instance_path}`;
  await findText(words.toUpperCase());
  check('every word must be held, in any case', JSON.stringify(await evaluate(SHOWN)) === JSON.stringify([lead]), `${words}: ${JSON.stringify(await evaluate(SHOWN))}`);
  await evaluate(`${FIND}.focus()`);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); await sleep(200);
  check('Enter in the box goes to the first row in view', await evaluate(`document.activeElement?.closest('tr') === ${ROW(lead)}`));
  await findText('');
  await tick(lead); await tick(last);
  await findText(last);
  await evaluate(`document.querySelector('section.editors button[title^="Delete selected"]').click()`);
  check('Delete selected takes only the ticked rows in view', await storedUntil(`!c.parameters.some(p => p.variable_id === ${JSON.stringify(last)}) && c.parameters.some(p => p.variable_id === ${JSON.stringify(lead)})`),
    JSON.stringify(await stored(`c.parameters.map(p => p.variable_id)`)));
  check('...said under the formula bar, and with no row left in view the focus goes to Add (branch record SIF-96)', (await evaluate(NOTE)) === `Deleted 1 row (${last}). Undo takes it back.`
    && await evaluate(`document.activeElement === document.querySelector('section.editors button[title^="Add:"]')`), `${await evaluate(NOTE)} | ${await evaluate(`document.activeElement?.title`)}`);
  await evaluate(UNDO);
  check('...and Undo brings it back', await storedUntil(`c.parameters.length === ${ids.length}`));
  await evaluate(`${FIND}.focus()`);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await sleep(250);
  check('Esc clears the box, and the folding is back', (await evaluate(`${FIND}.value`)) === '' && !(await evaluate(`document.querySelector('.toolbar .find-count')`))
    && JSON.stringify(await evaluate(SHOWN)) === JSON.stringify(ids.filter(id => !P.find(p => p.variable_id === id).binding_group)), JSON.stringify(await evaluate(SHOWN)));
  await tick(lead, false); await tick(last, false);

  // ---- Ctrl+D ------------------------------------------------------------------------------------------------------------------------
  const inView = ids.filter(id => !P.find(p => p.variable_id === id).binding_group);
  const above = inView[inView.indexOf(last) - 1], aboveUpper = P.find(p => p.variable_id === above).upper;
  await choose(BOX(last, 'upper'));
  await ctrl('d', 68);
  check('Ctrl+D: the cell takes the value of the row above in view', await storedUntil(`c.parameters.find(p => p.variable_id === ${JSON.stringify(last)})?.upper === ${JSON.stringify(aboveUpper)}`),
    `${await stored(`c.parameters.find(p => p.variable_id === ${JSON.stringify(last)})?.upper`)} / ${aboveUpper}`);
  // the value as the cells write it (record 7.208: 20 um), as the row above shows it
  const aboveShown = await evaluate(`${BOX(above, 'upper')}.value`);
  check('...said under the formula bar, as the cells write it', (await evaluate(NOTE)).startsWith(`Filled 1 cell with Upper = ${aboveShown} of ${above}`),
    `${await evaluate(NOTE)} (the row above shows ${aboveShown})`);
  await evaluate(UNDO);
  check('...one Undo step takes it back', await storedUntil(`c.parameters.find(p => p.variable_id === ${JSON.stringify(last)})?.upper === ${JSON.stringify(P.find(p => p.variable_id === last).upper)}`));
  const top = inView[0], notesOf = Object.fromEntries(P.map(p => [p.variable_id, p.notes ?? '']));
  await page.setValue(BOX(top, 'notes'), 'FIXTURE fill', { event: 'input' }); await sleep(300);
  for (const id of inView) await tick(id);
  await choose(BOX(last, 'notes'));
  await ctrl('d', 68);
  check('Ctrl+D in a ticked row: the topmost ticked row\'s value goes into every other ticked row in view, folded rows left out',
    await storedUntil(`${JSON.stringify(inView)}.every(id => c.parameters.find(p => p.variable_id === id)?.notes === 'FIXTURE fill') && c.parameters.find(p => p.variable_id === ${JSON.stringify(follower)})?.notes !== 'FIXTURE fill'`),
    JSON.stringify(await stored(`c.parameters.map(p => [p.variable_id, p.notes])`)));
  check('...as one Undo step', (await evaluate(NOTE)).startsWith(`Filled ${inView.length - 1} cells with Notes = FIXTURE fill of ${top} (one Undo step).`), await evaluate(NOTE));
  await evaluate(UNDO);
  check('...which one Undo takes back', await storedUntil(`${JSON.stringify(inView.slice(1))}.every(id => (c.parameters.find(p => p.variable_id === id)?.notes ?? '') === ${JSON.stringify(notesOf)}[id])
    && c.parameters.find(p => p.variable_id === ${JSON.stringify(top)})?.notes === 'FIXTURE fill'`));
  for (const id of inView) await tick(id, false);
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`); await sleep(200);
  await tick(lead); await tick(follower);
  await choose(BOX(lead, 'lower'));
  await ctrl('d', 68);
  check('a cell its leader decides is kept, and said so', (await evaluate(NOTE)) === 'Nothing filled. 1 cell that follows another field kept.'
    && (await stored(`c.parameters.find(p => p.variable_id === ${JSON.stringify(follower)}).lower ?? null`)) === (followerRow.lower ?? null), await evaluate(NOTE));
  await tick(lead, false); await tick(follower, false);
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`); await sleep(200);
  await choose(BOX(last, 'variable_id'));
  await ctrl('d', 68);
  check('an ID is not filled down', (await evaluate(NOTE)) === 'An ID is not filled down: each row needs its own ID.' && (await stored(`c.parameters.some(p => p.variable_id === ${JSON.stringify(last)})`)), await evaluate(NOTE));

  // ---- Ctrl+C and Copy ---------------------------------------------------------------------------------------------------------------
  const heads = await evaluate(`[...document.querySelectorAll('table.editor thead th[data-field]')].map(h => h.textContent.replace(/ \\*$/, ''))`);
  const fields = await evaluate(`[...document.querySelectorAll('table.editor thead th[data-field]')].map(h => h.dataset.field)`);
  // A value with its unit is copied as the cell writes it (record 7.208: there is no Unit column to say it), other fields as stored.
  const QUANTITY = ['lower', 'upper', 'step', 'initial_value'];
  const line = async id => { const row = (await stored(`c.parameters.find(p => p.variable_id === ${JSON.stringify(id)})`)) ?? {};
    const shown = await Promise.all(fields.map(f => QUANTITY.includes(f) ? evaluate(`${BOX(id, f)}.value`) : null));
    return fields.map((f, j) => QUANTITY.includes(f) ? shown[j] : row[f] == null ? '' : String(row[f])).join('\t'); };
  await choose(BOX(above, 'lower'));
  await ctrl('c', 67);
  const aboveLower = await evaluate(`${BOX(above, 'lower')}.value`);
  check('Ctrl+C in a cell: the cell alone, the value with its unit as the cell writes it (7.208)', (await evaluate('window.__copied')) === aboveLower
    && (await evaluate(NOTE)) === `Copied Lower of ${above}: ${aboveLower}.`, `${await evaluate('window.__copied')} | ${await evaluate(NOTE)}`);
  await tick(above); await tick(last);
  await choose(BOX(last, 'lower'));
  await ctrl('c', 67);
  const block = await evaluate('window.__copied');
  const expected = [heads.join('\t'), await line(above), await line(last)].join('\r\n');
  check('Ctrl+C in a ticked row: the ticked rows in view, every column in view, a header line first', block === expected, JSON.stringify({ block, expected }));
  await page.setValue(BOX(last, 'notes'), 'FIXTURE chosen text', { event: 'input' }); await sleep(250);
  const before = await evaluate('window.__copies');
  const leftAlone = await evaluate(`(() => { const b = ${BOX(last, 'notes')}; b.focus(); b.setSelectionRange(0, 7);
    const e = new KeyboardEvent('keydown', { key: 'c', code: 'KeyC', ctrlKey: true, bubbles: true, cancelable: true }); b.dispatchEvent(e); return !e.defaultPrevented; })()`);
  check('with text chosen inside the box, Ctrl+C is left to the browser (it copies that text)', leftAlone && (await evaluate('window.__copies')) === before);
  await evaluate(UNDO); await sleep(200);
  // the copied block pasted back: its header line is skipped and only what was changed in it changes
  const edited = block.split('\r\n').map((l, i) => i === 0 ? l : l.split('\t').map((v, j) => fields[j] === 'notes' ? 'FIXTURE back' : v).join('\t')).join('\r\n');
  await evaluate(`(() => { const b = ${BOX(above, 'variable_id')}; b.focus(); const d = new DataTransfer(); d.setData('text/plain', ${JSON.stringify(edited)});
    b.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true })); })()`);
  check('a copied block pasted back skips its header line, and only what was changed in it changes',
    await storedUntil(`[${JSON.stringify(above)}, ${JSON.stringify(last)}].every(id => c.parameters.find(p => p.variable_id === id)?.notes === 'FIXTURE back') && c.parameters.length === ${ids.length}`)
    && (await evaluate(NOTE)).includes('The header line was skipped.')
    && JSON.stringify(await stored(`c.parameters.map(p => [p.variable_id, p.instance_path, p.lower, p.upper])`)) === JSON.stringify(P.map(p => [p.variable_id, p.instance_path, p.lower, p.upper])),
    await evaluate(NOTE));
  await tick(above, false); await tick(last, false);
  await findText('pair');
  await evaluate(`document.querySelector('section.editors button[title^="Copy for Excel"]').click()`); await sleep(250);
  const all = (await evaluate('window.__copied')).split('\r\n');
  const pairRows = await evaluate(SHOWN);
  check('the Copy button with nothing ticked takes every row in view (here the found ones)', all.length === pairRows.length + 1 && all[0] === heads.join('\t')
    && pairRows.every((id, i) => all[i + 1].startsWith(`${id}\t`)), JSON.stringify({ all, pairRows }));
  await page.shot(path.join(out, 'find-2-copied.png'), `document.querySelector('.editors')`, { maxHeight: 520 });
  await findText('');

  // ---- the toolbar on one line at 1366 x 768 (record 7.185), a find too -----------------------------------------------------------------
  const toolbarLines = () => evaluate(`new Set([...document.querySelector('section.editors .toolbar').children].filter(c => c.offsetParent && !c.classList.contains('spacer'))
    .map(c => Math.round((c.getBoundingClientRect().top + c.getBoundingClientRect().bottom) / 2 / 20))).size`);
  await send('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false }); await sleep(500);
  const idle = await toolbarLines();
  await findText('pair');
  const finding = await toolbarLines(), box = await evaluate(`Math.round(document.querySelector('.toolbar .find-box').getBoundingClientRect().width)`);
  await page.shot(path.join(out, 'find-3-1366.png'), `document.querySelector('.editors')`, { maxHeight: 260 });
  check('at 1366 x 768 the toolbar stays on one line, while finding too (the count sits inside the box)', idle === 1 && finding === 1 && box >= 80, JSON.stringify({ idle, finding, box }));
  await findText('');
  await send('Emulation.clearDeviceMetricsOverride'); await sleep(300);
  check('...and on a wide window the box is 170 px', (await evaluate(`Math.round(document.querySelector('.toolbar .find-box').getBoundingClientRect().width)`)) === 170);

  // ---- one write path: a pasted output name, a pasted limit ----------------------------------------------------------------------
  await evaluate(`${TAB('measurements')}.click()`); await sleep(300);
  const users = config.targets.filter(t => t.equation === probe.measurement_id).map(t => t.metric_id);
  await evaluate(`(() => { const b = document.querySelector('table.editor tbody > tr:nth-child(1) > td[data-field="source_name"] input'); b.focus(); const d = new DataTransfer();
    d.setData('text/plain', 'FIXTURE_gain\\tFIXTURE signal'); b.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true })); })()`);
  check('a pasted output name renames its Probe ID, and the spec equations using it follow', users.length > 0
    && await storedUntil(`c.measurements[0].measurement_id === 'm_FIXTURE_gain' && ${JSON.stringify(users)}.every(id => c.targets.find(t => t.metric_id === id)?.equation === 'm_FIXTURE_gain')`),
    JSON.stringify(await stored(`[c.measurements[0], c.targets.map(t => [t.metric_id, t.equation])]`)));
  await evaluate(`${TAB('targets')}.click()`); await sleep(300);
  const limit = `document.querySelector('table.editor tbody > tr:nth-child(1) > td[data-field="constraint"] select')`;
  const pasteAt = text => evaluate(`(() => { const b = ${limit}; b.focus(); const d = new DataTransfer(); d.setData('text/plain', ${JSON.stringify(text)});
    b.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true })); })()`);
  await page.setValue(limit, '>=|maximize', { event: 'change' }); await sleep(250);
  await pasteAt('<=\t\t7');
  check('a pasted limit that does not pair with the objective drops it (≤ with "higher is better")', await storedUntil(`c.targets[0].constraint === '<=' && c.targets[0].direction_after_feasible === 'none'`),
    JSON.stringify(await stored(`c.targets[0]`)));
  await page.setValue(limit, '<=|minimize', { event: 'change' }); await sleep(250);
  await pasteAt('interval\t1\t7');
  check('...and keeps one that pairs (an interval, then lower is better)', await storedUntil(`c.targets[0].constraint === 'interval' && c.targets[0].direction_after_feasible === 'minimize' && c.targets[0].upper === 7`),
    JSON.stringify(await stored(`c.targets[0]`)));

  // ---- Add, Delete selected and the tick boxes do what they say, in view (branch record SIF-96) ------------------------------------
  const DELETE = `document.querySelector('section.editors button[title^="Delete selected"]').click()`;
  const ADD = `document.querySelector('section.editors button[title^="Add:"]').click()`;
  const HEAD = `document.querySelector('table.editor thead th.sel input')`;
  const idList = list => `${list.slice(0, 4).join(', ')}${list.length > 4 ? ', ...' : ''}`;
  const warned = () => evaluate(`!!document.querySelector('.paste-note.warn')`);
  // a deleted Probe: the Specs whose equation used it are named on the Probes tab, where they are not in view
  await evaluate(`${TAB('measurements')}.click()`); await sleep(300);
  const gain = 'm_FIXTURE_gain', usedBy = await stored(`c.targets.filter(t => /(?<![A-Za-z0-9_.])m_FIXTURE_gain(?![A-Za-z0-9_])/.test(t.equation)).map(t => t.metric_id)`);
  await tick(gain);
  await evaluate(DELETE);
  const probeNote = `Deleted 1 row (${gain}). Undo takes it back. ${usedBy.length === 1 ? `Spec ${usedBy[0]} uses` : `${usedBy.length} Specs (${idList(usedBy)}) use`} a deleted Probe.`;
  check('Delete selected says what went, and names the Specs whose equation used the deleted Probe, as a warning (SIF-96)', usedBy.length > 0
    && await page.until(`${NOTE} === ${JSON.stringify(probeNote)}`, 30) && await warned(), `${await evaluate(NOTE)} | expected: ${probeNote}`);
  // the row now in its place takes the focus (a leader's Delete below); with no row left in view, Add does
  check('...and the focus goes to the tick box of the row now in its place, or to Add when no row is left, not to the page', await evaluate(`document.activeElement
    === (${ROWS}.find(tr => !tr.hidden)?.querySelector('td.sel input') ?? document.querySelector('section.editors button[title^="Add:"]'))`),
    await evaluate(`document.activeElement?.outerHTML.slice(0, 100)`));
  await evaluate(UNDO);
  check('(set-up) Undo brings the Probe back', await storedUntil(`c.measurements.some(m => m.measurement_id === ${JSON.stringify(gain)})`));
  // Add with a Find text the new row does not hold: the text goes, and the new Probe - a Maestro output, as the task's others -
  // comes into view with its Output name chosen, which its ID follows
  await findText('FIXTURE');
  const probesBefore = await stored(`c.measurements.length`);
  await evaluate(ADD);
  const newProbe = await storedUntil(`c.measurements.length === ${probesBefore + 1}`) ? await stored(`c.measurements[c.measurements.length - 1]`) : null;
  const probeFocus = await evaluate(`(() => { const a = document.activeElement, tr = a?.closest('tr'); return { field: a?.closest('td')?.dataset.field ?? null, row: tr ? Number(tr.dataset.index) : null, shown: !!tr && !tr.hidden }; })()`);
  check('Add with a Find text the new row does not hold clears the text and says so (SIF-96)', (await evaluate(`${FIND}.value`)) === ''
    && (await evaluate(NOTE)) === `Find rows cleared to show the new row, ${newProbe?.measurement_id}.`, `${await evaluate(`${FIND}.value`)} | ${await evaluate(NOTE)}`);
  check('...and the new Probe, a Maestro output, comes into view with its Output name chosen (its Probe ID follows the name)', newProbe?.result_source === 'ade_output'
    && JSON.stringify(probeFocus) === JSON.stringify({ field: 'source_name', row: probesBefore, shown: true }), JSON.stringify({ newProbe, probeFocus }));
  await evaluate(UNDO);
  check('(set-up) Undo takes the new Probe away', await storedUntil(`c.measurements.length === ${probesBefore}`));

  // the header's box ticks every row in view - never one folded under its leader - and is half ticked while only some are
  await evaluate(`${TAB('parameters')}.click()`); await sleep(300);
  const ticked = () => evaluate(`${ROWS}.filter(tr => tr.querySelector('td.sel input').checked).map(tr => tr.querySelector('td[data-field] input').value)`);
  const head = () => evaluate(`({ checked: ${HEAD}.checked, half: ${HEAD}.indeterminate, label: ${HEAD}.getAttribute('aria-label') })`);
  const HEAD_AS = (checked, half) => JSON.stringify({ checked, half, label: 'Tick every row in view' });
  check('(set-up) three rows in view or more, and none ticked', inView.length >= 3 && !(await ticked()).length, JSON.stringify({ inView, ticked: await ticked() }));
  await evaluate(`${HEAD}.click()`); await sleep(200);
  check('the tick-box header ticks every row in view, the rows folded under a leader left as they were (SIF-96)', JSON.stringify(await ticked()) === JSON.stringify(inView)
    && JSON.stringify(await head()) === HEAD_AS(true, false), JSON.stringify({ ticked: await ticked(), head: await head() }));
  await tick(inView[0], false);
  check('...is half ticked while only some rows in view are', JSON.stringify(await head()) === HEAD_AS(false, true), JSON.stringify(await head()));
  await evaluate(`${HEAD}.click()`); await sleep(200);
  const again = await ticked();
  await evaluate(`${HEAD}.click()`); await sleep(200);
  check('...ticks them all again from there, and a second press unticks them all', JSON.stringify(again) === JSON.stringify(inView) && !(await ticked()).length
    && JSON.stringify(await head()) === HEAD_AS(false, false), JSON.stringify({ again, now: await ticked() }));
  // Shift+click on a row's box: every row in view from the box clicked last takes its state (a real click, Shift held)
  const boxAt = id => evaluate(`(() => { const b = ${ROW(id)}.querySelector('td.sel input'); b.scrollIntoView({ block: 'center' }); const r = b.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  const shiftClick = async id => { const p = await boxAt(id);
    for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: p.x, y: p.y, button: 'left', clickCount: 1, modifiers: 8 }); await sleep(200); };
  await page.clickAt(await boxAt(inView[0])); await sleep(200);
  await shiftClick(inView[inView.length - 1]);
  check('Shift+click on a row\'s box ticks every row in view from the box clicked last, and no folded row (SIF-96)', JSON.stringify(await ticked()) === JSON.stringify(inView),
    JSON.stringify(await ticked()));
  await shiftClick(inView[1]);
  check('...and Shift+click on a ticked box unticks that span', JSON.stringify(await ticked()) === JSON.stringify([inView[0]]), JSON.stringify(await ticked()));
  await tick(inView[0], false);

  // a deleted leader: the rows tied to it now follow nothing, and the line says so as a warning
  const tied = tiedTo(lead), leadAt = ids.indexOf(lead);
  await tick(lead);
  await evaluate(DELETE);
  const leaderNote = `Deleted 1 row (${lead}). Undo takes it back. ${tied.length === 1 ? `${tied[0]} was` : `${tied.length} rows (${idList(tied)}) were`} tied to a deleted row `
    + `and now follow${tied.length === 1 ? 's' : ''} nothing.`;
  check('Delete selected on a leader names the rows tied to it, which now follow nothing, as a warning (SIF-96)', await page.until(`${NOTE} === ${JSON.stringify(leaderNote)}`, 30)
    && await warned(), `${await evaluate(NOTE)} | expected: ${leaderNote}`);
  // the leader's place: the first row in view from there on - its tied rows, unfolded now that they follow nothing
  check('...and the focus goes to the tick box of the row now in the leader\'s place', await evaluate(`document.activeElement
    === ${ROWS}.find(tr => !tr.hidden && Number(tr.dataset.index) >= ${leadAt})?.querySelector('td.sel input')`),
    await evaluate(`(() => { const a = document.activeElement; return \`\${a?.outerHTML.slice(0, 60)} in row \${a?.closest('tr')?.dataset.index}\`; })()`));
  await evaluate(UNDO);
  check('(set-up) Undo brings the leader back', await storedUntil(`c.parameters.length === ${ids.length}`));
  // a ticked row folded away since is deleted as before (record 7.184), and the line counts it
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`); await sleep(200);
  await tick(follower);
  await evaluate(`${ROW(lead)}.querySelector('.tie-toggle').click()`); await sleep(200);
  await tick(last);
  await evaluate(DELETE);
  const foldedNote = `Deleted 2 rows (${ids.filter(id => id === follower || id === last).join(', ')}), 1 of them folded under a leader. Undo takes them back.`;
  check('a ticked row folded away since is deleted as before, and the line says it was folded (SIF-96)', await page.until(`${NOTE} === ${JSON.stringify(foldedNote)}`, 30)
    && !(await warned()) && await storedUntil(`!c.parameters.some(p => [${JSON.stringify(follower)}, ${JSON.stringify(last)}].includes(p.variable_id))`),
    `${await evaluate(NOTE)} | expected: ${foldedNote}`);
  await evaluate(UNDO);
  check('(set-up) Undo brings both back', await storedUntil(`c.parameters.length === ${ids.length}`));
  // Add with a Find text: the new row comes into view with its ID chosen, so its name is typed at once
  await findText('pair');
  await evaluate(ADD);
  const added = await storedUntil(`c.parameters.length === ${ids.length + 1}`) ? await stored(`c.parameters[c.parameters.length - 1].variable_id`) : null;
  const chosen = await evaluate(`(() => { const a = document.activeElement, s = a?.closest('.scroll')?.getBoundingClientRect(), r = a?.getBoundingClientRect();
    return { field: a?.closest('td')?.dataset.field ?? null, value: a?.value, all: a?.selectionStart === 0 && a?.selectionEnd === a?.value.length,
      inBox: !!s && r.top >= Math.max(s.top, 0) - 1 && r.bottom <= Math.min(s.bottom, innerHeight) + 1 && !a.closest('tr').hidden }; })()`);
  check('Add with a Find text clears it, and the new row comes into view with its ID chosen, to be typed over (SIF-96)', (await evaluate(`${FIND}.value`)) === ''
    && JSON.stringify(chosen) === JSON.stringify({ field: 'variable_id', value: added, all: true, inBox: true })
    && (await evaluate(NOTE)) === `Find rows cleared to show the new row, ${added}.`, JSON.stringify({ chosen, added, note: await evaluate(NOTE) }));
  await page.shot(path.join(out, 'find-4-added.png'), `document.querySelector('.editors')`, { maxHeight: 520 });
  await evaluate(UNDO);
  check('(set-up) Undo takes the new row away', await storedUntil(`c.parameters.length === ${ids.length}`));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
