// Browser check of the right column's "Output settings" panel (there is no frontend test runner in this project).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). POST /api/output/check is answered with a canned report labelled FIXTURE
// and /api/config/validate with an empty one; GET requests pass through; every other writing request is refused here,
// so this check can start, save or probe nothing on the backend it runs against. The browser profile is new and
// temporary (the user's saved configuration is not touched), and the clipboard is replaced by a recorder in the page.
// What it pins (user requests 2026-09-21 and 2026-09-22):
//   - "Copy path" sits at the right end of the "Output root" caption line, as text (no button chrome), and still copies;
//     it says "copied" for 1.5 s just before it, or "could not copy" when the browser refuses the clipboard (branch record SIF-94);
//   - "Waveform storage limit" is a number box plus a unit list; the configuration keeps the typed size in whole bytes;
//     choosing another unit CONVERTS the shown number and saves nothing (1.5 GiB -> 1536 MiB); an empty box is "no limit"
//     and stays empty; a value from outside is shown exactly, in the unit that reads best;
//   - "Checkpoint every" is ONE number with the unit evaluations OR seconds: the other field is always emptied (also the
//     default of 200 evaluations since record 7.280, 50 before), another unit carries the number over, a configuration with both says so;
//   - the closing line "Pausing, stopping and normal completion always save safely..." is gone;
//   - "Browse allowed roots..." (GET /api/output/browse answered here with FIXTURE folders) says which folder it shows, opens
//     a folder by its name, goes "Up one folder", can be closed, and "Use this folder" sets the root (branch record SIF-60);
//     a folder still on its way when Close is pressed neither opens the list again nor shows its error (SIF-60 review);
//   - "Replay snapshots" and its warning name Continue... and the Modes, "weights only" in words (branch record SIF-60);
//   - the facts' "Resolved" path, which a click does not copy, shows no copy cursor (branch record SIF-64);
//   - branch record SIF-91: Test writability reads "Testing..." and Measure "Measuring..." while their answers are on their way
//     (a held folder listing holds neither), "Reading the folder..." stands above the list while a folder is read, and a test's
//     answer says when it came ("NOT writable · tested 14:03:22"); Experiment ID offers the experiments of the runs under the
//     root (GET /api/runs answered here with FIXTURE rows), and one picked sets the experiment name too; with the MOCK task
//     loaded (its circuit read at the end) only the MOCK ones, and a real one typed says that Start refuses it (SIF-91 review).
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
// The folder list as paths.py's browse() answers it: no path and no parent at the top, where the entries are the roots.
const TOP = '/fixture/roots/one', DEEP = `${TOP}/outputs`;
const BROWSE = { '': { path: null, parent: null, entries: [{ name: TOP, path: TOP, exists: true }] },
  [TOP]: { path: TOP, parent: null, entries: [{ name: 'outputs', path: DEEP, exists: true }] },
  [DEEP]: { path: DEEP, parent: TOP, entries: [] } };
// Branch record SIF-91: the run list under the root, as run_index.py names a run's experiment ("<name>__<12 hex>"): two runs of
// one experiment, a MOCK one, and a run from before the ID ("__None"), which is no experiment to add to. Of another task, at
// rest: the page neither follows nor takes over any of them.
const RUN_ROW = (dir, experiment, mock = false) => ({ run_dir: `${ROOT}/${dir}`, run_id: dir, task_key: 'fixture:elsewhere', task_id: 'fixture_elsewhere:0000', mode: 'scratch',
  mock, seed: 0, created_utc: '2026-10-20T10:00:00+00:00', state: 'completed', experiment, evaluations: 1 });
const RUNS = [RUN_ROW('sweep__0123456789ab/runs/a', 'sweep__0123456789ab'), RUN_ROW('sweep__0123456789ab/runs/b', 'sweep__0123456789ab'),
  RUN_ROW('mock/trial__abcdef012345/runs/c', 'trial__abcdef012345', true), RUN_ROW('old__None/runs/d', 'old__None')];

await runChecks(browser, async () => {
  const listed = (await (await fetch(new URL('api/tasks', APP))).json()).tasks.map(t => t.task_key);
  const mockTask = listed.find(key => key.startsWith('synthetic:'));
  if (!mockTask) throw new Error(`the backend lists no MOCK task: ${listed.join(', ')}`);
  const starter = await (await fetch(new URL(`api/tasks/starter?task_key=${encodeURIComponent(mockTask)}`, APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture', output_root: ROOT, waveform_storage_limit_bytes: 2 * GIB }, research: {} };
  const page = await browser.open({ height: 2200 });
  const { send, fulfil, consoleErrors } = page;
  const refused = []; const probes = []; let oldBackend = false;   // oldBackend: answer `usage` as a backend from before record 7.189 does
  const browsed = [];                                              // the folders the list asked for ('' for the roots)
  let holdBrowse = false, holdTest = false; const held = [];       // answers held back until after Close (branch record SIF-60 review)
  let holdMeasure = false;                                         // Measure's answer held back: "Measuring..." (branch record SIF-91)
  let readCircuit = false;                                         // the MOCK task's circuit read (a registered task: local files), for its kind (SIF-91 review)
  const answer = params => {
    const { requestId, request } = params, name = new URL(request.url).pathname;
    if (name === '/api/output/browse') { const at = new URL(request.url).searchParams.get('path') ?? ''; browsed.push(at);
      if (holdBrowse) { held.push({ requestId, at }); return; }
      return BROWSE[at] ? fulfil(requestId, 200, BROWSE[at]) : fulfil(requestId, 403, { detail: 'FIXTURE: not an allowed folder' }); }
    if (name === '/api/output/check') { const body = JSON.parse(request.postData ?? '{}'); probes.push(body);
      if (holdTest && body.create) { held.push({ requestId, test: true }); return; }
      if (holdMeasure && body.usage) { held.push({ requestId, measure: true }); return; }
      return oldBackend && body.usage ? fulfil(requestId, 422, { detail: [{ type: 'extra_forbidden', loc: ['body', 'usage'], msg: 'Extra inputs are not permitted' }] }) : fulfil(requestId, 200, OUTPUT_CHECK); }
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: RUNS });
    return page.readOrRefuse(params, refused, { reads: readCircuit && name === '/api/circuit/load' });
  };
  const heldAll = async n => { for (let i = 0; i < 40 && held.length < n; i++) await sleep(100); return held.length === n; };
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
  // Record 7.360: Output settings starts folded. Unfolded once here, the choice is kept in this browser over the reloads below.
  await evaluate(`(() => { const d = ${PANEL}.querySelector('details.module'); if (!d.open) d.querySelector('summary').click(); })()`);
  if (!(await until(`${PANEL}.querySelector('details.module').open`, 20))) throw new Error('the Output settings module did not unfold');

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
  // Branch record SIF-94: the press said nothing. "copied" for 1.5 s now, just before the button, which keeps its text and its
  // place at the line's end; a copy the browser refuses says "could not copy" there instead.
  await until(`!!${HEAD}.querySelector('.copy-word')`, 20);
  const said = await evaluate(`(() => { const w = ${HEAD}.querySelector('.copy-word'), c = ${COPY}, s = w && getComputedStyle(w);
    return w && { text: w.textContent, ok: w.classList.contains('ok'), before: w.nextElementSibling === c, button: c.textContent, size: s.fontSize === getComputedStyle(c).fontSize,
      atRightEnd: Math.abs(c.getBoundingClientRect().right - ${ROOT_INPUT}.getBoundingClientRect().right) < 2 }; })()`);
  check('...and says "copied" just before it, at its size, the button keeping its text and its place at the line\'s end (SIF-94)', said?.text === ' copied' && said.ok && said.before
    && said.button === 'Copy path' && said.size && said.atRightEnd, JSON.stringify(said));
  check('...for 1.5 s, then the line reads as before', await until(`!${HEAD}.querySelector('.copy-word')`, 40), await evaluate(`${HEAD}.textContent`));
  await evaluate(`navigator.clipboard.writeText = () => Promise.reject(new DOMException('FIXTURE: Document is not focused.', 'NotAllowedError'))`);
  await evaluate(`${COPY}.click()`);
  check('a copy the browser refuses says "could not copy" there instead, and why on hover (SIF-94)', await until(`${HEAD}.querySelector('.copy-word.warn')?.textContent === ' could not copy'`, 20)
    && /refused the clipboard/.test(await evaluate(`${HEAD}.querySelector('.copy-word').title`)), await evaluate(`${HEAD}.textContent`));
  await evaluate(`navigator.clipboard.writeText = text => { window.__copied = text; return Promise.resolve(); }`);
  check('the caption still belongs to the path box (a click on it puts the cursor in the box, and copies nothing)', await evaluate(`(() => { window.__copied = null; ${HEAD}.querySelector('label').click();
    return document.activeElement === ${ROOT_INPUT} && window.__copied === null; })()`));
  check('the path box is still editable and full width', await evaluate(`(() => { const b = ${ROOT_INPUT}.getBoundingClientRect(), p = ${PANEL}.getBoundingClientRect(); return !${ROOT_INPUT}.disabled && b.width > p.width - 40; })()`));
  for (let i = 0; i < 30 && !probes.length; i++) await sleep(100);             // the root is looked at 0.5 s after it is shown (2026-09-29)
  check('opening the page only LOOKED at the output root (create: false), it probed nothing', probes.length >= 1 && probes.every(p => p.create === false), JSON.stringify(probes));
  check('...and did not ask for the folder\'s size (record 7.189: on D: that walk took 0.7 to 2 s at every page open)', probes.every(p => !p.usage), JSON.stringify(probes));
  // Review of 2026-09-29: each keystroke used to send a look (the last answer won).
  const looks = probes.length;
  await evaluate(`(() => { const i = ${ROOT_INPUT}; i.focus(); i.setSelectionRange(i.value.length, i.value.length); })()`);
  for (const ch of '/sub') await send('Input.insertText', { text: ch });
  await sleep(1500);
  check('typing four characters into the output root looks at it ONCE, 0.5 s after the last one, for the whole text', probes.length - looks === 1
    && probes.at(-1)?.path === `${ROOT}/sub` && probes.at(-1)?.create === false, JSON.stringify(probes.slice(looks)));

  // ---- the folder's size, on "Measure" only (record 7.189) ------------------------------------------------------------------
  await evaluate(`(() => { const d = ${PANEL}.querySelector('details.output-facts'); d.open = true; })()`); await sleep(200);
  const MEASURE = `[...${PANEL}.querySelectorAll('details.output-facts button')].find(b => b.textContent === 'Measure')`;
  check('the facts table offers "Measure" where the folder\'s size was', await evaluate(`!!${MEASURE}`));
  const words = await evaluate(`(() => { const facts = [...${PANEL}.querySelectorAll('details.output-facts tr')].map(r => [...r.cells].map(c => c.textContent.trim()));
    const allowed = facts.find(([name]) => name === 'Allowed / writable'), name = ${PANEL}.querySelector('details.output-facts td');
    const retention = [...${PANEL}.querySelectorAll('label')].find(l => l.textContent.startsWith('Raw waveform retention'))?.querySelector('select');
    return { allowed: allowed?.[1], nameWraps: getComputedStyle(name).whiteSpace, retention: retention && [retention.value, retention.selectedOptions[0].textContent] }; })()`);
  check('the facts and the retention list speak words: yes / yes, "Best design and failures" (its value unchanged), each fact\'s name on one line (branch record SIF-35)',
    words.allowed === 'yes / yes' && words.nameWraps === 'nowrap' && JSON.stringify(words.retention) === JSON.stringify(['best_and_failures', 'Best design and failures']), JSON.stringify(words));
  // Branch record SIF-64: "Resolved" showed the copy cursor, and a click on it copies nothing - the text cursor now, no "Click to copy".
  const resolved = await evaluate(`(() => { const td = [...${PANEL}.querySelectorAll('details.output-facts tr')].find(r => r.cells[0].textContent === 'Resolved')?.cells[1];
    if (!td) return null; window.__copied = null; td.click(); return { cursor: getComputedStyle(td).cursor, title: td.title, copied: window.__copied }; })()`);
  check('..."Resolved", which a click does not copy, shows the text cursor and no "Click to copy" (SIF-64)', JSON.stringify(resolved) === '{"cursor":"text","title":"","copied":null}', JSON.stringify(resolved));
  const asked = probes.length;
  // Branch record SIF-91: the press says it works, and a second press meanwhile asks nothing (a disabled button's click()
  // does nothing, as a click on it does); on D: the walk takes seconds.
  const MEASURING = `[...${PANEL}.querySelectorAll('details.output-facts button')].find(b => b.textContent === 'Measuring...')`;
  holdMeasure = true;
  await evaluate(`${MEASURE}.click()`);
  const measuring = await heldAll(1) && await until(`!!(${MEASURING}) && ${MEASURING}.disabled && !(${MEASURE})`, 20);
  await evaluate(`${MEASURING}?.click()`); await sleep(300);
  check('...pressed, it reads "Measuring..." and takes no second press until the size comes (SIF-91)', measuring && held.length === 1 && probes.length - asked === 1,
    JSON.stringify([measuring, held.length, probes.slice(asked)]));
  holdMeasure = false;
  for (const { requestId } of held.splice(0)) await fulfil(requestId, 200, OUTPUT_CHECK);
  check('"Measure" asks for the size once, and shows it', await until(`[...${PANEL}.querySelectorAll('details.output-facts td')].some(td => td.textContent.includes('used here 3.00 GiB'))`, 30)
    && probes.length - asked === 1 && probes.at(-1)?.usage === true && probes.at(-1)?.create === false, JSON.stringify(probes.slice(asked)));
  // a backend from before record 7.189 refuses `usage` (its request body forbids unknown fields): the plain look's size is shown
  oldBackend = true;
  await page.setValue(`${PANEL}.querySelector('#output-root')`, `${ROOT}/older`, { event: 'input' }); await sleep(1200);
  await evaluate(`(() => { const d = ${PANEL}.querySelector('details.output-facts'); d.open = true; })()`); await sleep(200);
  const before7189 = probes.length;
  await evaluate(`${MEASURE}.click()`);
  check('...and against a backend from before it (which refuses usage) Measure shows the size of its plain look', await until(`[...${PANEL}.querySelectorAll('details.output-facts td')].some(td => td.textContent.includes('used here 3.00 GiB'))`, 30)
    && probes.slice(before7189).map(p => !!p.usage).join(',') === 'true,false', JSON.stringify(probes.slice(before7189)));
  oldBackend = false;

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
  check('a configuration without the field shows the default: 200 evaluations (record 7.280), and writes nothing by itself', c.box === '200' && c.unit === 'evaluations' && c.e === 'absent' && c.s === 'absent' && !c.warn, JSON.stringify(c));
  await chooseCp('seconds'); c = await cp();
  check('seconds carries the number over and EMPTIES the evaluations (the default of 200 too)', c.box === '200' && c.unit === 'seconds' && c.e === null && c.s === 200, JSON.stringify(c));
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
  check('seconds with the evaluations field ABSENT is both too (the default of 200 applies)', c.warn && c.box === '200' && c.e === 'absent' && c.s === 600, JSON.stringify(c));
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

  // ---- "Replay snapshots": Continue... and the Modes by their names (branch record SIF-60) -----------------------------------
  const REPLAY = `[...${PANEL}.querySelectorAll('label.check')].find(l => l.textContent.startsWith('Replay snapshots'))`;
  check('"Replay snapshots" says what it is needed for: "Replay snapshots (needed to Continue a run exactly)" (it said "a FULL resume")',
    (await evaluate(`${REPLAY}?.textContent`)) === 'Replay snapshots (needed to Continue a run exactly)', await evaluate(`${REPLAY}?.textContent ?? 'no such box'`));
  await evaluate(`${REPLAY}.querySelector('input').click()`);
  const replayWarn = await until(`[...${PANEL}.querySelectorAll('p.warn')].some(p => p.textContent.startsWith('Without replay snapshots'))`, 30)
    ? await evaluate(`[...${PANEL}.querySelectorAll('p.warn')].find(p => p.textContent.startsWith('Without replay snapshots')).textContent`) : null;
  check('unticked, its warning reads "...checkpoints are weights only: Continue... cannot pick it up exactly; Fine-tune and Evaluate only can still load its model." (no weights_only, no resume)',
    replayWarn === 'Without replay snapshots this run\'s checkpoints are weights only: Continue... cannot pick it up exactly; Fine-tune and Evaluate only can still load its model.', String(replayWarn));
  await evaluate(`${REPLAY}.querySelector('input').click()`);
  check('...and ticked again, the warning goes', await until(`![...${PANEL}.querySelectorAll('p.warn')].some(p => p.textContent.startsWith('Without replay snapshots'))`, 30));

  // ---- "Browse allowed roots...": which folder, Up one folder, Close, Use this folder (branch record SIF-60) ----------------------
  const BUTTON = text => `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent === ${JSON.stringify(text)})`;
  const TREE = `${PANEL}.querySelector('ul.tree')`;
  const listing = () => evaluate(`(() => { const t = ${TREE}; if (!t) return null; const head = t.previousElementSibling;
    return { head: head?.textContent ?? null, rows: [...t.children].map(li => [...li.querySelectorAll('button')].map(b => b.textContent + (b.classList.contains('text-link') ? ' (link)' : ''))) }; })()`);
  const rootBefore = await evaluate(`${ROOT_INPUT}.value`);
  await evaluate(`${BUTTON('Browse allowed roots...')}.click()`); await until(`!!(${TREE})`, 30);
  let list = await listing();
  check('the list starts with the allowed roots, says so and offers Close: each root a link to open it and "Use this folder"',
    list?.head === 'The allowed roots Close' && JSON.stringify(list.rows) === JSON.stringify([[`${TOP} (link)`, 'Use this folder']]), JSON.stringify(list));
  await evaluate(`[...${TREE}.querySelectorAll('button.text-link')].find(b => b.textContent === ${JSON.stringify(TOP)}).click()`);
  await until(`(${TREE})?.previousElementSibling?.textContent.startsWith('In ${TOP}')`, 30); list = await listing();
  check('a root\'s name opens it: "In /fixture/roots/one Close", its folder "outputs", no way up from a root',
    list?.head === `In ${TOP} Close` && JSON.stringify(list.rows) === JSON.stringify([['outputs (link)', 'Use this folder']]), JSON.stringify(list));
  await evaluate(`[...${TREE}.querySelectorAll('button.text-link')].find(b => b.textContent === 'outputs').click()`);
  await until(`(${TREE})?.previousElementSibling?.textContent.startsWith('In ${DEEP}')`, 30); list = await listing();
  check('inside a root the list offers "Up one folder" (it was a bare "..")', list?.head === `In ${DEEP} Close` && JSON.stringify(list.rows) === JSON.stringify([['Up one folder (link)']]), JSON.stringify(list));
  await evaluate(`${BUTTON('Up one folder')}.click()`);
  check('...which goes back to its parent', await until(`(${TREE})?.previousElementSibling?.textContent === 'In ${TOP} Close'`, 30), JSON.stringify(await listing()));
  await evaluate(`[...${TREE}.previousElementSibling.querySelectorAll('button')].find(b => b.textContent === 'Close').click()`);
  check('"Close" takes the list away and leaves the output root as it was', await until(`!(${TREE})`, 30) && (await evaluate(`${ROOT_INPUT}.value`)) === rootBefore,
    `${JSON.stringify(await listing())} / ${await evaluate(`${ROOT_INPUT}.value`)}`);
  // Close lets a folder on its way go (branch record SIF-60 review): its answer, or its error, came after Close and opened
  // the list again. Test writability, pressed before, still answers: it asks on another line than the list.
  const ERRORS = `[...${PANEL}.querySelectorAll('p.error')].map(p => p.textContent).join(' | ')`;
  const SUMMARY = `(${PANEL}.querySelector('details.output-facts > summary')?.textContent ?? '')`;
  // Branch record SIF-91: what each press shows while its answer is on its way.
  const waiting = () => evaluate(`({ test: (b => b && [b.textContent, b.disabled])([...${PANEL}.querySelectorAll('.row button')].find(b => /^Test/.test(b.textContent))),
    reading: [...${PANEL}.querySelectorAll('p.hint')].some(p => p.textContent === 'Reading the folder...') })`);
  for (const status of [200, 403]) {
    await evaluate(`${BUTTON('Browse allowed roots...')}.click()`); await until(`!!(${TREE})`, 30);
    holdBrowse = true; holdTest = status === 200;
    if (holdTest) await evaluate(`${BUTTON('Test writability')}.click()`);
    await evaluate(`[...${TREE}.querySelectorAll('button.text-link')].find(b => b.textContent === ${JSON.stringify(TOP)}).click()`);
    check(`(set-up) the folder${holdTest ? ' and Test writability are' : ' is'} held back`, await heldAll(holdTest ? 2 : 1), JSON.stringify(held));
    const wait = await waiting();
    check(holdTest ? 'meanwhile Test writability reads "Testing..." and is off, and "Reading the folder..." stands above the list (SIF-91)'
      : '...a folder alone on its way holds no Test writability: it stays on, "Reading the folder..." above the list (SIF-91)',
    JSON.stringify(wait) === JSON.stringify({ test: holdTest ? ['Testing...', true] : ['Test writability', false], reading: true }), JSON.stringify(wait));
    holdBrowse = holdTest = false;
    await evaluate(`[...${TREE}.previousElementSibling.querySelectorAll('button')].find(b => b.textContent === 'Close').click()`);
    await until(`!(${TREE})`, 30);
    check('...Close lets the folder go, and "Reading the folder..." with it (SIF-91)', !(await waiting()).reading);
    for (const { requestId, test } of held.splice(0)) await (test ? fulfil(requestId, 200, { ...OUTPUT_CHECK, writable: false, error: 'FIXTURE: held test' })
      : status === 200 ? fulfil(requestId, 200, BROWSE[TOP]) : fulfil(requestId, 403, { detail: 'FIXTURE: not an allowed folder' }));
    await sleep(800);
    check(status === 200 ? 'a folder answered after Close leaves the list closed' : '...and a folder that fails after Close shows no error',
      !(await evaluate(`!!(${TREE})`)) && !(await evaluate(ERRORS)).includes('FIXTURE'), `${JSON.stringify(await listing())} / ${await evaluate(ERRORS)}`);
    if (status === 200) check('...while Test writability, pressed before Close, still answers ("NOT writable"), and says when: "NOT writable · tested hh:mm:ss · ..." (SIF-91)',
      /^NOT writable · tested \d{1,2}:\d\d:\d\d · /.test(await evaluate(SUMMARY)) && JSON.stringify((await waiting()).test) === '["Test writability",false]',
      `${await evaluate(SUMMARY)} / ${JSON.stringify(await waiting())}`);
  }
  // Branch record SIF-91: a writable root's answer read as the look before it, so the press changed nothing on screen.
  await evaluate(`${BUTTON('Test writability')}.click()`);
  check('a test that finds the root writable says so, and when: "writable · tested hh:mm:ss · ... free" (SIF-91)',
    await until(`/^writable · tested \\d{1,2}:\\d\\d:\\d\\d · /.test(${SUMMARY})`, 30), await evaluate(SUMMARY));
  await evaluate(`${BUTTON('Browse allowed roots...')}.click()`); await until(`!!(${TREE})`, 30);
  await evaluate(`[...${TREE}.querySelectorAll('li')].find(li => li.textContent.startsWith(${JSON.stringify(TOP)})).querySelector('button:not(.text-link)').click()`);
  await page.saved();
  check('"Use this folder" sets the output root to it and closes the list', await until(`!(${TREE})`, 30) && (await evaluate(`${ROOT_INPUT}.value`)) === TOP
    && (await evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).output.output_root`)) === TOP, await evaluate(`${ROOT_INPUT}.value`));
  check('the list asked only for the folders pressed', JSON.stringify(browsed) === JSON.stringify(['', TOP, DEEP, TOP, '', TOP, '', TOP, '']), JSON.stringify(browsed));

  // ---- Experiment ID: the experiments under the output root; one picked sets the name too (branch record SIF-91) ---------------
  // The ID stood only in the Runs window (a tooltip, a run's Details), to be retyped and its name matched by hand.
  const FIELD = name => `[...${PANEL}.querySelectorAll('label')].find(l => l.textContent.startsWith(${JSON.stringify(name)}))?.querySelector('input')`;
  const EXP_ID = FIELD('Experiment ID'), EXP_NAME = FIELD('Experiment name');
  const NOT_LISTED = `([...${PANEL}.querySelectorAll('p.hint')].find(p => p.textContent.startsWith('No run listed here'))?.textContent ?? null)`;
  const OPTIONS = `[...(${EXP_ID}).list.options].map(o => [o.value, o.label])`;
  let offered = await until(`(${EXP_ID})?.list?.options.length >= 2`, 50) ? await evaluate(OPTIONS) : null;
  check('Experiment ID offers the experiments of the runs under the root, each once with its runs counted, a MOCK one marked; a run from before the ID adds none;'
    + ' with no task loaded (its circuit is not read here so far) both kinds (SIF-91)',
    JSON.stringify(offered) === JSON.stringify([['sweep__0123456789ab', '2 runs'], ['trial__abcdef012345', '1 run, MOCK']]), JSON.stringify(offered));
  const experiment = async () => { await page.saved(); return evaluate(`({ id: (${EXP_ID}).value, name: (${EXP_NAME}).value, hint: ${NOT_LISTED},
    stored: (o => [o.experiment_name, o.experiment_id])(JSON.parse(localStorage.getItem('gator-workbench-config-v1')).output) })`); };
  await page.setValue(EXP_ID, 'sweep__0123456789ab', { event: 'input' });
  let exp = await experiment();
  check('...one picked sets the name and the ID together, in the boxes and the configuration: "sweep" and "0123456789ab" (SIF-91)',
    JSON.stringify(exp) === JSON.stringify({ id: '0123456789ab', name: 'sweep', hint: null, stored: ['sweep', '0123456789ab'] }), JSON.stringify(exp));
  await page.setValue(EXP_ID, 'ffffffffffff', { event: 'input' });
  exp = await experiment();
  check('...an ID typed by hand is kept as typed, and one that no listed run is in says that Start refuses it (SIF-91)', exp.id === 'ffffffffffff' && exp.name === 'sweep'
    && exp.hint === 'No run listed here is in sweep__ffffffffffff: Start refuses an experiment that is not under the output root.', JSON.stringify(exp));
  await page.setValue(EXP_ID, '', { event: 'input' });
  exp = await experiment();
  check('...emptied, the ID is new again (none) and the hint goes', JSON.stringify(exp) === JSON.stringify({ id: '', name: 'sweep', hint: null, stored: ['sweep', null] }), JSON.stringify(exp));
  // Branch record SIF-91 review: Start looks for a MOCK task's experiment under <root>/mock and a real one's under the root
  // itself, so an experiment of the other kind, picked from the list, was refused at Start (after a real run's question).
  readCircuit = true;
  await send('Page.reload');
  offered = await until(`!!(${PANEL}) && (${EXP_ID})?.list?.options.length === 1`, 150) ? await evaluate(OPTIONS) : null;
  check('with the MOCK task loaded, Experiment ID offers only the MOCK experiment: Start of a MOCK task looks in the root\'s mock/ folder (SIF-91 review)',
    JSON.stringify(offered) === JSON.stringify([['trial__abcdef012345', '1 run, MOCK']]), JSON.stringify(offered));
  const KIND = `([...${PANEL}.querySelectorAll('p.hint')].find(p => / holds (MOCK|real) runs: /.test(p.textContent))?.textContent ?? null)`;
  const kind = async () => { const seen = await experiment(); return { ...seen, kind: await evaluate(KIND) }; };
  await page.setValue(EXP_ID, 'sweep__0123456789ab', { event: 'input' });
  exp = await kind();
  check('...the real experiment, typed by hand, is set, and says that Start of this MOCK task refuses it (SIF-91 review)', exp.id === '0123456789ab' && exp.hint === null
    && exp.kind === 'sweep__0123456789ab holds real runs: Start of this MOCK task looks for it in the output root\'s mock/ folder and refuses it.', JSON.stringify(exp));
  await page.setValue(EXP_ID, 'trial__abcdef012345', { event: 'input' });
  exp = await kind();
  check('...the MOCK one picked says nothing against it', JSON.stringify(exp) === JSON.stringify({ id: 'abcdef012345', name: 'trial', hint: null, stored: ['trial', 'abcdef012345'], kind: null }),
    JSON.stringify(exp));

  reportRefused(refused, NEVER_ASKED);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
