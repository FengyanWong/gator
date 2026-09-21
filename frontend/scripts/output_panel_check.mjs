// Browser check of the right column's "Output settings" panel (there is no frontend test runner in this project).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). POST /api/output/check is answered with a canned report labelled FIXTURE
// and /api/config/validate with an empty one; GET requests pass through; every other writing request is refused here,
// so this check can start, save or probe nothing on the backend it runs against. The browser profile is new and
// temporary (the user's saved configuration is not touched), and the clipboard is replaced by a recorder in the page.
// What it pins (user request 2026-09-21):
//   - "Copy path" sits at the right end of the "Output root" caption line, as text (no button chrome), and still copies;
//   - "Waveform storage limit" is a number box plus a unit list; the configuration keeps whole bytes; choosing another
//     unit keeps the number; an empty box is "no limit" and stays empty; a value from outside picks a readable unit.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/output_panel_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9399, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-output-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

const ROOT = '/fixture/output-root';
const GIB = 1024 ** 3, MIB = 1024 ** 2;
const OUTPUT_CHECK = { resolved: ROOT, allowed: true, writable: true, error: null, host: 'FIXTURE', environment: 'fixture', filesystem: 'fixture',
  free_bytes: 400 * GIB, bytes_used: 3 * GIB, windows_path: null, windows_mapping: 'fixture', mock_data_root: '/fixture/mock' };
const VALID = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:opamp', APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture', output_root: ROOT, waveform_storage_limit_bytes: 2 * GIB }, research: {} };
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const refused = []; const probes = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/output/check') { probes.push(JSON.parse(request.postData ?? '{}')); return fulfil(requestId, 200, OUTPUT_CHECK); }
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (request.method === 'GET') return send('Fetch.continueRequest', { requestId });
    refused.push(`${request.method} ${name}`);
    return fulfil(requestId, 418, { detail: { message: 'FIXTURE: this check lets no writing request through' } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 60) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };

  const PANEL = `[...document.querySelectorAll('.right .panel')].find(p => p.querySelector('h3')?.textContent.trim() === 'Output settings')`;
  const HEAD = `${PANEL}.querySelector('.field-head')`;
  const COPY = `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Copy path')`;
  const ROOT_INPUT = `${PANEL}.querySelector('#output-root')`;
  const LIMIT = `[...${PANEL}.querySelectorAll('label')].find(l => l.querySelector('span')?.textContent.trim() === 'Waveform storage limit')`;
  const BOX = `${LIMIT}.querySelector('input')`, UNIT = `${LIMIT}.querySelector('select')`;
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).output.waveform_storage_limit_bytes`);
  const settled = async () => { await sleep(1100); return { box: await evaluate(`${BOX}.value`), unit: await evaluate(`${UNIT}.value`), bytes: await stored() }; };  // the page saves 0.8 s after a change
  const type = async text => {
    await evaluate(`(() => { const i = ${BOX}; i.focus(); i.select(); })()`);
    if (text === '') for (const t of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type: t, key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 });
    else await send('Input.insertText', { text });
  };
  const blur = () => evaluate(`${BOX}.blur()`);
  const choose = unit => evaluate(`(() => { const s = ${UNIT}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(unit)}); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const shot = async name => {
    await evaluate(`${PANEL}.scrollIntoView({ block: 'start' })`); await sleep(150);
    const clip = await evaluate(`(() => { const r = ${PANEL}.getBoundingClientRect(); return { x: r.x - 4, y: Math.max(0, r.y - 4), width: r.width + 8, height: r.height + 8, scale: 2 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip, captureBeyondViewport: true });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 2200, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (!localStorage.getItem('gator-workbench-config-v1')) localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))});` });
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
  check('opening the page only LOOKED at the output root (create: false), it probed nothing', probes.length >= 1 && probes.every(p => p.create === false), JSON.stringify(probes));

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
  await type('500'); await blur(); await choose('MiB'); s = await settled();
  check('type 500, THEN choose MiB: 500 MiB (the number stays, the unit gives it its meaning)', s.box === '500' && s.unit === 'MiB' && s.bytes === 500 * MIB, JSON.stringify(s));
  await choose('GiB'); await type('3'); await blur(); s = await settled();
  check('choose GiB, THEN type 3: 3 GiB', s.box === '3' && s.unit === 'GiB' && s.bytes === 3 * GIB, JSON.stringify(s));
  await type('1.3'); await blur(); s = await settled();
  check('1.3 GiB is not a whole number of bytes: rounded to 1395864371, still shown as 1.3', s.box === '1.3' && s.bytes === 1395864371 && Number.isInteger(s.bytes), JSON.stringify(s));
  await choose('bytes'); s = await settled();
  check('the unit "bytes" takes the number as bytes, whole ones only (1.3 -> 1)', s.box === '1' && s.unit === 'bytes' && s.bytes === 1, JSON.stringify(s));
  await type('4096'); await blur(); s = await settled();
  check('4096 bytes stay "4096 bytes" while the user chose that unit', s.box === '4096' && s.unit === 'bytes' && s.bytes === 4096, JSON.stringify(s));

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

  // ---- the neighbouring box had the same fault: "Checkpoint every N evaluations" may be empty too ------------------------
  const EVERY = `[...${PANEL}.querySelectorAll('label')].find(l => l.querySelector('span')?.textContent.trim() === 'Checkpoint every N evaluations').querySelector('input')`;
  await evaluate(`(() => { const i = ${EVERY}; i.focus(); i.select(); })()`);
  for (const t of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type: t, key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 });
  await evaluate(`${EVERY}.blur()`); await sleep(1100);
  const every = { box: await evaluate(`${EVERY}.value`), saved: await evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).output.checkpoint_every_evaluations`) };
  check('an emptied "Checkpoint every N evaluations" saves null and stays empty (it used to show 50 again)', every.box === '' && every.saved === null, JSON.stringify(every));

  // ---- a value that did not come from the box: Undo, and a reloaded configuration ---------------------------------------
  await type('7'); await blur(); await choose('GiB'); s = await settled();
  check('(setup) 7 GiB', s.box === '7' && s.unit === 'GiB' && s.bytes === 7 * GIB, JSON.stringify(s));
  await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent === 'Undo').click()`); s = await settled();
  check('Undo brings back 7 MiB, shown in the unit that reads best', s.box === '7' && s.unit === 'MiB' && s.bytes === 7 * MIB, JSON.stringify(s));
  await evaluate(`(() => { const c = JSON.parse(localStorage.getItem('gator-workbench-config-v1')); c.output.waveform_storage_limit_bytes = 1500000000; localStorage.setItem('gator-workbench-config-v1', JSON.stringify(c)); })()`);
  await send('Page.reload'); await until(`!!(${PANEL}) && !!(${LIMIT})`, 150); s = await settled();
  check('an odd value from a loaded configuration is shown exactly, never rounded: 1464843.75 KiB = 1500000000 bytes', Math.round(Number(s.box) * { bytes: 1, KiB: 1024, MiB: MIB, GiB: GIB }[s.unit]) === 1500000000 && s.bytes === 1500000000, JSON.stringify(s));
  await evaluate(`(() => { const c = JSON.parse(localStorage.getItem('gator-workbench-config-v1')); delete c.output.waveform_storage_limit_bytes; localStorage.setItem('gator-workbench-config-v1', JSON.stringify(c)); })()`);
  await send('Page.reload'); await until(`!!(${PANEL}) && !!(${LIMIT})`, 150); s = await settled();
  check('a configuration without the field shows the backend default, 2 GiB, and writes nothing by itself', s.box === '2' && s.unit === 'GiB' && s.bytes === undefined, JSON.stringify(s));

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect or call an agent on its own: never', !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/)/.test(r)), refused.join(', '));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  ws.close();
} catch (error) {
  failures++; console.log('ERROR ' + (error?.stack ?? error));
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; the temp dir is harmless */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
