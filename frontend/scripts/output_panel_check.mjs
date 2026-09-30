// Browser check of the right column's "Output settings" panel (there is no frontend test runner in this project).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). POST /api/output/check is answered with a canned report labelled FIXTURE
// and /api/config/validate with an empty one; GET requests pass through; every other writing request is refused here,
// so this check can start, save or probe nothing on the backend it runs against. The browser profile is new and
// temporary (the user's saved configuration is not touched), and the clipboard is replaced by a recorder in the page.
// What it pins (user requests 2026-09-21 and 2026-09-22):
//   - "Copy path" sits at the right end of the "Output root" caption line, as text (no button chrome), and still copies;
//   - "Waveform storage limit" is a number box plus a unit list; the configuration keeps the typed size in whole bytes;
//     choosing another unit CONVERTS the shown number and saves nothing (1.5 GiB -> 1536 MiB); an empty box is "no limit"
//     and stays empty; a value from outside is shown exactly, in the unit that reads best;
//   - "Checkpoint every" is ONE number with the unit evaluations OR seconds: the other field is always emptied (also the
//     default of 50 evaluations), another unit carries the number over, a configuration with both says so;
//   - the closing line "Pausing, stopping and normal completion always save safely..." is gone.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 30 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/output_panel_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { validConfiguration, check, launchEdge, NEVER_ASKED, outDir, reportRefused, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('output');

const ROOT = '/fixture/output-root';
const GIB = 1024 ** 3, MIB = 1024 ** 2;
const OUTPUT_CHECK = { resolved: ROOT, allowed: true, writable: true, error: null, host: 'FIXTURE', environment: 'fixture', filesystem: 'fixture',
  free_bytes: 400 * GIB, bytes_used: 3 * GIB, windows_path: null, windows_mapping: 'fixture', mock_data_root: '/fixture/mock' };
const VALID = validConfiguration();

await runChecks(browser, async () => {
  const listed = (await (await fetch(new URL('api/tasks', APP))).json()).tasks.map(t => t.task_key);
  const mockTask = listed.find(key => key.startsWith('synthetic:'));
  if (!mockTask) throw new Error(`the backend lists no MOCK task: ${listed.join(', ')}`);
  const starter = await (await fetch(new URL(`api/tasks/starter?task_key=${encodeURIComponent(mockTask)}`, APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture', output_root: ROOT, waveform_storage_limit_bytes: 2 * GIB }, research: {} };
  const page = await browser.open({ height: 2200 });
  const { send, fulfil, consoleErrors } = page;
  const refused = []; const probes = [];
  const answer = params => {
    const { requestId, request } = params, name = new URL(request.url).pathname;
    if (name === '/api/output/check') { probes.push(JSON.parse(request.postData ?? '{}')); return fulfil(requestId, 200, OUTPUT_CHECK); }
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    return page.readOrRefuse(params, refused);
  };
  const evaluate = expression => page.evaluate(expression, true);
  const until = (expression, tries = 60) => page.until(expression, tries);

  const PANEL = `[...document.querySelectorAll('.right .panel')].find(p => p.querySelector('h3')?.textContent.trim() === 'Output settings')`;
  const HEAD = `${PANEL}.querySelector('.field-head')`;
  const COPY = `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Copy path')`;
  const ROOT_INPUT = `${PANEL}.querySelector('#output-root')`;
  const LIMIT = `[...${PANEL}.querySelectorAll('label')].find(l => l.querySelector('span')?.textContent.trim() === 'Waveform storage limit')`;
  const BOX = `${LIMIT}.querySelector('input')`, UNIT = `${LIMIT}.querySelector('select')`;
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).output.waveform_storage_limit_bytes`);
  const flushed = () => page.saved();
  const settled = async () => { await flushed(); return { box: await evaluate(`${BOX}.value`), unit: await evaluate(`${UNIT}.value`), bytes: await stored() }; };  // the page saves 0.8 s after a change
  const type = async text => {
    await evaluate(`(() => { const i = ${BOX}; i.focus(); i.select(); })()`);
    if (text === '') for (const t of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type: t, key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 });
    else await send('Input.insertText', { text });
  };
  const blur = () => evaluate(`${BOX}.blur()`);
  const CP = `[...${PANEL}.querySelectorAll('label')].find(l => l.querySelector('span')?.textContent.trim() === 'Checkpoint every')`;
  const CP_BOX = `${CP}.querySelector('input')`, CP_UNIT = `${CP}.querySelector('select')`;
  const WARN = `[...${PANEL}.querySelectorAll('p.warn')].find(p => p.textContent.includes('This configuration has both'))`;
  const saved = () => evaluate(`(() => { const o = JSON.parse(localStorage.getItem('gator-workbench-config-v1')).output, v = k => k in o ? o[k] : 'absent';
    return { e: v('checkpoint_every_evaluations'), s: v('checkpoint_every_seconds') }; })()`);
  const cp = async () => { await flushed(); return { box: await evaluate(`${CP_BOX}.value`), unit: await evaluate(`${CP_UNIT}.value`), ...(await saved()), warn: await evaluate(`!!(${WARN})`) }; };
  const typeCp = async text => {
    await evaluate(`(() => { const i = ${CP_BOX}; i.focus(); i.select(); })()`);
    if (text === '') for (const t of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type: t, key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 });
    else await send('Input.insertText', { text });
    await evaluate(`${CP_BOX}.blur()`);
  };
  const chooseCp = unit => page.setValue(`${CP_UNIT}`, unit);
  const editStored = async change => {
    await evaluate(`(() => { const c = JSON.parse(localStorage.getItem('gator-workbench-config-v1')); (${change})(c.output); localStorage.setItem('gator-workbench-config-v1', JSON.stringify(c)); })()`);
    await send('Page.reload'); await until(`!!(${PANEL}) && !!(${CP})`, 150);
  };
  const choose = unit => page.setValue(`${UNIT}`, unit);
  const shot = async name => {
    await evaluate(`${PANEL}.scrollIntoView({ block: 'start' })`); await sleep(150);
    await page.shot(path.join(out, name), await evaluate(`(() => { const r = ${PANEL}.getBoundingClientRect(); return { x: r.x - 4, y: Math.max(0, r.y - 4), width: r.width + 8, height: r.height + 8, scale: 2 }; })()`), { beyond: true });
  };

  await page.intercept(['*/api/*'], answer);
  // The page saves 800 ms after the last change and headless Edge can run that timer late: flushed() waits for the timer
  // itself (trackSaves). A change that should NOT happen (a unit choice saving a size) still arms it, and is then seen.
  await page.trackSaves();
  await page.seed({ config: CONFIG, when: 'missing' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${PANEL})`, 150))) throw new Error('the Output settings panel never appeared; the page reads: '
    + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  await evaluate(`navigator.clipboard.writeText = text => { window.__copied = text; return Promise.resolve(); }`);

  // ---- "Copy path": on the caption line of "Output root", at its right end, as text ---------------------------------
  check('"Copy path" exists once in the panel', (await evaluate(`[...${PANEL}.querySelectorAll('button')].filter(b => b.textContent.trim() === 'Copy path').length`)) === 1);
  check('it is no longer in the row of buttons under the box', await evaluate(`!(${COPY}).closest('.row') && [...${PANEL}.querySelectorAll('.row button')].some(b => b.textContent === 'Test writability')`));
  const line = await evaluate(`(() => { const head = ${HEAD}.getBoundingClientRect(), cap = ${HEAD}.querySelector('label').getBoundingClientRect(), c = ${COPY}.getBoundingClientRect(), box = ${ROOT_INPUT}.getBoundingClientRect();
    return { sameLine: Math.abs((cap.top + cap.bottom) / 2 - (c.top + c.bottom) / 2) < 4, rightOfCaption: c.left > cap.right, atRightEnd: Math.abs(c.right - box.right) < 2 && Math.abs(c.right - head.right) < 2,
      aboveBox: c.bottom <= box.top + 1, caption: ${HEAD}.querySelector('label').textContent }; })()`);
  check('it is on the same line as the caption "Output root", to its right', line.sameLine && line.rightOfCaption && line.caption === 'Output root', JSON.stringify(line));
  check('it ends where the path box ends (right edge), above the box', line.atRightEnd && line.aboveBox, JSON.stringify(line));
  const look = await evaluate(`(() => { const s = getComputedStyle(${COPY}), cap = getComputedStyle(${HEAD}.querySelector('label'));
    return { border: s.borderTopWidth + ' ' + s.borderTopStyle, background: s.backgroundColor, padding: s.padding, size: s.fontSize, captionSize: cap.fontSize, cursor: s.cursor }; })()`);
  check('it has no button chrome: no border, no background, no padding', look.border === '0px none' && look.background === 'rgba(0, 0, 0, 0)' && look.padding === '0px', JSON.stringify(look));
  check('it is text of the caption\'s size, and still shows the hand pointer', look.size === look.captionSize && look.cursor === 'pointer', JSON.stringify(look));
  await evaluate(`${COPY}.click()`);
  check('pressing it copies the output root', (await until(`window.__copied === ${JSON.stringify(ROOT)}`, 20)), String(await evaluate(`window.__copied`)));
  check('the caption still belongs to the path box (a click on it puts the cursor in the box, and copies nothing)', await evaluate(`(() => { window.__copied = null; ${HEAD}.querySelector('label').click();
    return document.activeElement === ${ROOT_INPUT} && window.__copied === null; })()`));
  check('the path box is still editable and full width', await evaluate(`(() => { const b = ${ROOT_INPUT}.getBoundingClientRect(), p = ${PANEL}.getBoundingClientRect(); return !${ROOT_INPUT}.disabled && b.width > p.width - 40; })()`));
  for (let i = 0; i < 30 && !probes.length; i++) await sleep(100);             // the root is looked at 0.5 s after it is shown (2026-09-29)
  check('opening the page only LOOKED at the output root (create: false), it probed nothing', probes.length >= 1 && probes.every(p => p.create === false), JSON.stringify(probes));
  // Review of 2026-09-29: each look walks the folder for its size, and each keystroke used to send one (the last answer won).
  const looks = probes.length;
  await evaluate(`(() => { const i = ${ROOT_INPUT}; i.focus(); i.setSelectionRange(i.value.length, i.value.length); })()`);
  for (const ch of '/sub') await send('Input.insertText', { text: ch });
  await sleep(1500);
  check('typing four characters into the output root looks at it ONCE, 0.5 s after the last one, for the whole text', probes.length - looks === 1
    && probes.at(-1)?.path === `${ROOT}/sub` && probes.at(-1)?.create === false, JSON.stringify(probes.slice(looks)));

  // ---- "Waveform storage limit": a number and a unit -----------------------------------------------------------------
  check('the caption no longer says "(bytes)"', !(await evaluate(`${PANEL}.textContent.includes('(bytes)')`)));
  check('the unit list offers bytes, KiB, MiB, GiB, TiB', JSON.stringify(await evaluate(`[...${UNIT}.options].map(o => o.value)`)) === JSON.stringify(['bytes', 'KiB', 'MiB', 'GiB', 'TiB']));
  let s = await settled();
  check('2147483648 bytes are shown as 2 GiB', s.box === '2' && s.unit === 'GiB', JSON.stringify(s));
  const row = await evaluate(`(() => { const b = ${BOX}.getBoundingClientRect(), u = ${UNIT}.getBoundingClientRect(), l = ${LIMIT}.getBoundingClientRect();
    return { sameLine: Math.abs(b.top - u.top) < 3, unitRight: u.left >= b.right, inside: u.right <= l.right + 1, boxWidth: Math.round(b.width), unitWidth: Math.round(u.width) }; })()`);
  check('the unit list is on the same line, right of the number box, inside the panel', row.sameLine && row.unitRight && row.inside && row.boxWidth > row.unitWidth, JSON.stringify(row));
  await shot('output-1-panel.png');

  await type('1.5'); s = await settled();
  check('typing 1.5 (GiB) saves 1610612736 whole bytes and keeps the typed text', s.box === '1.5' && s.unit === 'GiB' && s.bytes === 1.5 * GIB, JSON.stringify(s));
  await blur(); s = await settled();
  check('leaving the box keeps 1.5 GiB', s.box === '1.5' && s.unit === 'GiB' && s.bytes === 1.5 * GIB, JSON.stringify(s));
  await type('0.'); s = await settled();
  check('a half-typed "0." stays in the box while typing', s.box === '0.', JSON.stringify(s));
  await type('500'); await blur(); s = await settled();
  check('(setup) 500 GiB', s.box === '500' && s.unit === 'GiB' && s.bytes === 500 * GIB, JSON.stringify(s));
  await choose('MiB'); s = await settled();
  check('choosing MiB CONVERTS the shown number: 500 GiB -> 512000 MiB, the saved size stays', s.box === '512000' && s.unit === 'MiB' && s.bytes === 500 * GIB, JSON.stringify(s));
  await choose('TiB'); s = await settled();
  check('... and TiB: 0.48828125 TiB, the same bytes', s.box === '0.48828125' && s.bytes === 500 * GIB, JSON.stringify(s));
  await choose('GiB'); await type('1.3'); await blur(); s = await settled();
  check('1.3 GiB is saved as the whole bytes nearest to it (1395864371) and still reads 1.3', s.box === '1.3' && s.bytes === 1395864371, JSON.stringify(s));
  const views = {};
  for (const unit of ['MiB', 'KiB', 'bytes', 'TiB', 'GiB']) { await choose(unit); views[unit] = (await settled()).box; }
  s = await settled();
  check('every unit shows that size exactly - 1331.2 MiB, 1363148.8 KiB, 1395864371 bytes, 0.00126953125 TiB, 1.3 GiB',
    JSON.stringify(views) === JSON.stringify({ MiB: '1331.2', KiB: '1363148.8', bytes: '1395864371', TiB: '0.00126953125', GiB: '1.3' }), JSON.stringify(views));
  check('and choosing units saved nothing: still 1395864371 bytes', s.bytes === 1395864371, JSON.stringify(s));
  await type('2.'); s = await settled();
  check('(setup) "2." half-typed = 2 GiB', s.box === '2.' && s.bytes === 2 * GIB, JSON.stringify(s));
  await choose('MiB'); s = await settled();
  check('a unit chosen while typing shows the converted number: 2048 MiB', s.box === '2048' && s.unit === 'MiB' && s.bytes === 2 * GIB, JSON.stringify(s));
  await choose('bytes'); await type('4096'); await blur(); s = await settled();
  check('typed in bytes, 4096 is saved as 4096', s.box === '4096' && s.unit === 'bytes' && s.bytes === 4096, JSON.stringify(s));
  await choose('KiB'); s = await settled();
  check('... and reads 4 KiB', s.box === '4' && s.bytes === 4096, JSON.stringify(s));

  // ---- empty = no limit, and it stays empty (the old box snapped back to the default while the configuration said "none") --
  await type(''); await blur(); s = await settled();
  check('an emptied box saves null (no limit) and STAYS empty', s.box === '' && s.bytes === null, JSON.stringify(s));
  check('the empty box says what empty means', (await evaluate(`${BOX}.placeholder`)) === 'no limit' && /no limit/.test(await evaluate(`${LIMIT}.title`)), await evaluate(`${LIMIT}.title`));
  await choose('MiB'); s = await settled();
  check('choosing a unit for an empty box sets no limit by itself', s.box === '' && s.unit === 'MiB' && s.bytes === null, JSON.stringify(s));
  await shot('output-2-no-limit.png');
  await type('250'); await blur(); s = await settled();
  check('typing into the empty box sets a limit again (250 MiB)', s.box === '250' && s.bytes === 250 * MIB, JSON.stringify(s));
  check('the tooltip names the exact bytes', (await evaluate(`${LIMIT}.title`)).includes(`Saved as ${250 * MIB} bytes.`), await evaluate(`${LIMIT}.title`));
  await type('abc'); s = await settled();
  check('letters change nothing in the configuration', s.bytes === 250 * MIB, JSON.stringify(s));
  await blur(); s = await settled();
  check('and leaving the box puts the last good number back', s.box === '250' && s.bytes === 250 * MIB, JSON.stringify(s));

  // ---- "Checkpoint every": ONE number, in evaluations OR in seconds ------------------------------------------------------
  check('one box and a unit list [evaluations, seconds]; the second box "or every S seconds" is gone',
    JSON.stringify(await evaluate(`[...${CP_UNIT}.options].map(o => o.value)`)) === JSON.stringify(['evaluations', 'seconds'])
    && !(await evaluate(`${PANEL}.textContent.includes('every S seconds') || ${PANEL}.textContent.includes('every N evaluations')`)));
  let c = await cp();
  check('a configuration without the field shows the default: 50 evaluations, and writes nothing by itself', c.box === '50' && c.unit === 'evaluations' && c.e === 'absent' && c.s === 'absent' && !c.warn, JSON.stringify(c));
  await chooseCp('seconds'); c = await cp();
  check('seconds carries the number over and EMPTIES the evaluations (the default of 50 too)', c.box === '50' && c.unit === 'seconds' && c.e === null && c.s === 50, JSON.stringify(c));
  await typeCp('600'); c = await cp();
  check('600 seconds', c.box === '600' && c.s === 600 && c.e === null, JSON.stringify(c));
  await chooseCp('evaluations'); c = await cp();
  check('back to evaluations: 600 evaluations, the seconds emptied', c.box === '600' && c.unit === 'evaluations' && c.e === 600 && c.s === null, JSON.stringify(c));
  await typeCp('25'); c = await cp();
  check('25 evaluations', c.box === '25' && c.e === 25 && c.s === null, JSON.stringify(c));
  await typeCp(''); c = await cp();
  check('an emptied box = no periodic checkpoint: both empty, and it stays empty', c.box === '' && c.e === null && c.s === null, JSON.stringify(c));
  check('the empty box says what it means', (await evaluate(`${CP_BOX}.placeholder`)) === 'only at pause, stop, end', await evaluate(`${CP_BOX}.placeholder`));
  await chooseCp('seconds'); c = await cp();
  check('a unit chosen for an empty box sets nothing', c.box === '' && c.unit === 'seconds' && c.e === null && c.s === null, JSON.stringify(c));
  await typeCp('900'); c = await cp();
  check('900 seconds', c.box === '900' && c.unit === 'seconds' && c.s === 900 && c.e === null, JSON.stringify(c));
  await editStored(`o => { o.checkpoint_every_evaluations = 50; o.checkpoint_every_seconds = 600; }`); c = await cp();
  check('a configuration with BOTH (a file, an older copy) says so, in the evaluations view', c.warn && c.unit === 'evaluations' && c.box === '50', JSON.stringify(c));
  check('the warning names both values', /every 50 evaluations and every 600 seconds/.test(await evaluate(`${WARN}.textContent`)), await evaluate(`${WARN}.textContent`));
  await shot('output-3-both.png');
  await chooseCp('seconds'); c = await cp();
  check('choosing seconds keeps ITS value (600) and empties the evaluations', c.box === '600' && c.unit === 'seconds' && c.s === 600 && c.e === null && !c.warn, JSON.stringify(c));
  await editStored(`o => { delete o.checkpoint_every_evaluations; o.checkpoint_every_seconds = 600; }`); c = await cp();
  check('seconds with the evaluations field ABSENT is both too (the default of 50 applies)', c.warn && c.box === '50' && c.e === 'absent' && c.s === 600, JSON.stringify(c));
  await typeCp('40'); c = await cp();
  check('typing a number keeps only that one: 40 evaluations, the seconds emptied', c.box === '40' && c.e === 40 && c.s === null && !c.warn, JSON.stringify(c));
  await editStored(`o => { o.checkpoint_every_evaluations = null; o.checkpoint_every_seconds = 120; }`); c = await cp();
  check('a stored seconds interval opens in the seconds view', c.box === '120' && c.unit === 'seconds' && !c.warn, JSON.stringify(c));

  // ---- the closing line is gone --------------------------------------------------------------------------------------------
  check('"Pausing, stopping and normal completion always save safely..." is no longer in the panel',
    !(await evaluate(`${PANEL}.textContent.includes('Pausing, stopping') || ${PANEL}.textContent.includes('raw tables are Parquet')`)));

  // ---- a value that did not come from the box: Undo, and a reloaded configuration ---------------------------------------
  await until(`!!(${LIMIT})`, 50); await choose('MiB'); await type('7'); await blur(); s = await settled();
  check('(setup) 7 MiB', s.box === '7' && s.unit === 'MiB' && s.bytes === 7 * MIB, JSON.stringify(s));
  await choose('GiB'); s = await settled();
  check('(setup) shown as 0.0068359375 GiB, still 7 MiB', s.box === '0.0068359375' && s.bytes === 7 * MIB, JSON.stringify(s));
  await type('7'); await blur(); s = await settled();
  check('(setup) 7 GiB', s.box === '7' && s.unit === 'GiB' && s.bytes === 7 * GIB, JSON.stringify(s));
  await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent === 'Undo').click()`); s = await settled();
  check('Undo brings back 7 MiB, shown in the unit that reads best', s.box === '7' && s.unit === 'MiB' && s.bytes === 7 * MIB, JSON.stringify(s));
  await evaluate(`(() => { const c = JSON.parse(localStorage.getItem('gator-workbench-config-v1')); c.output.waveform_storage_limit_bytes = 1500000000; localStorage.setItem('gator-workbench-config-v1', JSON.stringify(c)); })()`);
  await send('Page.reload'); await until(`!!(${PANEL}) && !!(${LIMIT})`, 150); s = await settled();
  check('an odd value from a loaded configuration is shown exactly, never rounded: 1464843.75 KiB = 1500000000 bytes', s.box === '1464843.75' && s.unit === 'KiB' && s.bytes === 1500000000, JSON.stringify(s));
  await choose('MiB'); s = await settled();
  check('in MiB it reads 1430.511475, which gives back exactly 1500000000 bytes', s.box === '1430.511475' && Math.round(Number(s.box) * MIB) === 1500000000 && s.bytes === 1500000000, JSON.stringify(s));
  await evaluate(`(() => { const c = JSON.parse(localStorage.getItem('gator-workbench-config-v1')); delete c.output.waveform_storage_limit_bytes; localStorage.setItem('gator-workbench-config-v1', JSON.stringify(c)); })()`);
  await send('Page.reload'); await until(`!!(${PANEL}) && !!(${LIMIT})`, 150); s = await settled();
  check('a configuration without the field shows the backend default, 2 GiB, and writes nothing by itself', s.box === '2' && s.unit === 'GiB' && s.bytes === undefined, JSON.stringify(s));

  reportRefused(refused, NEVER_ASKED);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
