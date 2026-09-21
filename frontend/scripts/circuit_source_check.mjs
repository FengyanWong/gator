// Browser check of "Circuit source = Import Spectre netlist" in the Project panel (there is no frontend test runner).
// Same approach as agent_tab_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). Every POST /api/circuit/load is logged and then passed on to the real
// backend: loading a netlist only reads and parses two local files (MOCK backend, nothing is simulated or written).
// What it pins (user report 2026-09-20): choosing the source no longer answers "Blocked: ... needs netlist_path ..."
// before anything was typed; typing sends nothing; a netlist loads on its button / Enter; a Windows path is converted.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/circuit_source_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9380, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-src-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const loads = []; const consoleErrors = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') {                                 // log it, then let the real backend answer
      loads.push(JSON.parse(m.params.request.postData ?? '{}').circuit ?? {});
      send('Fetch.continueRequest', { requestId: m.params.requestId }).catch(() => { /* page went away */ });
    }
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Circuit source'))`;
  const FIELD = label => `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)}).querySelector('input, select')`;
  const BUTTON = text => `[...${PANEL}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const text = () => evaluate(`${PANEL}.textContent`);
  const value = label => evaluate(`${FIELD(label)}.value`);
  const choose = (label, v) => evaluate(`(() => { const s = ${FIELD(label)}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(v)});
    s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const type = async (label, chunks, replace = true) => {                          // several input events, like typing
    await evaluate(`(() => { const i = ${FIELD(label)}; i.focus(); ${replace ? 'i.select()' : 'i.setSelectionRange(i.value.length, i.value.length)'}; })()`);
    for (const chunk of chunks) { await send('Input.insertText', { text: chunk }); await sleep(60); }
  };
  const enter = async () => { for (const kind of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type: kind, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); };
  const settle = async (mark, ms = 6000) => { for (let waited = 0; waited < ms && loads.length === mark; waited += 100) await sleep(100); await sleep(900); };
  const shot = async name => {                                                      // the left column scrolls: bring the form into view, clip to what is visible
    const H3 = `[...${PANEL}.querySelectorAll('h3')].find(h => h.textContent.trim() === 'Circuit source')`;
    await evaluate(`${H3}.scrollIntoView({ block: 'start' })`); await sleep(200);
    const clip = await evaluate(`(() => { const a = document.querySelector('.left').getBoundingClientRect(), h = ${H3}.getBoundingClientRect();
      return { x: a.x, y: Math.max(a.y, h.y - 6), width: a.width, height: a.bottom - Math.max(a.y, h.y - 6), scale: 2 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/circuit/load', requestStage: 'Request' }] });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${PANEL})`)); i++) await sleep(100);
  await settle(0);
  const meta = await (await fetch(new URL('api/meta', APP))).json();
  const root = meta.repo_root, NETLIST = `${root}/tests/fixtures/synthetic/opamp.scs`, MAPPING = `${root}/configs/opamp.json`;
  check('a registered task still loads by itself on page load', loads.length >= 1 && (await text()).includes('Hierarchy ('), `${loads.length} load request(s)`);

  // ---- the reported case: choosing the source ------------------------------------------------------------------
  let mark = loads.length;
  await choose('Source', 'netlist'); await sleep(1500);
  check('choosing "Import Spectre netlist" asks the backend nothing', loads.length === mark, `${loads.length - mark} request(s)`);
  check('no "Blocked" box before anything was typed', !(await evaluate(`!!${PANEL}.querySelector('.blocker')`)) && !(await text()).includes('netlist_path'));
  check('the form says what it needs, in its own labels, and where the files may be', (await text()).includes('Two files are needed') && (await text()).includes(root) && (await text()).includes('--allow-input-root'));
  check('the circuit of the previous source is no longer shown', !(await text()).includes('Hierarchy ('));
  check('"Load netlist" waits for both paths', await evaluate(`${BUTTON('Load netlist')}.disabled`));
  await shot('source-1-netlist-chosen.png');

  // ---- typing sends nothing ---------------------------------------------------------------------------------------
  await type('Netlist path', [NETLIST.slice(0, 9), NETLIST.slice(9, 25), NETLIST.slice(25)]); await sleep(800);
  check('typing the netlist path sends nothing', loads.length === mark && (await value('Netlist path')) === NETLIST, `${loads.length - mark} request(s)`);
  check('one path is not enough for the button', await evaluate(`${BUTTON('Load netlist')}.disabled`));
  await type('Device mapping (JSON)', [MAPPING.slice(0, 12), MAPPING.slice(12)]); await sleep(800);
  check('typing the mapping path sends nothing', loads.length === mark, `${loads.length - mark} request(s)`);
  check('with both paths the button is ready and the panel says "not loaded yet"', !(await evaluate(`${BUTTON('Load netlist')}.disabled`)) && (await text()).includes('Not loaded yet'));

  // ---- one press = one load -----------------------------------------------------------------------------------------
  await evaluate(`${BUTTON('Load netlist')}.click()`); await settle(mark);
  check('"Load netlist" sends exactly one load with both paths', loads.length === mark + 1 && loads[mark].netlist_path === NETLIST && loads[mark].parser_config_path === MAPPING, JSON.stringify(loads.slice(mark)));
  check('the netlist is read: MOCK backend, 7 instances', (await text()).includes('MOCK evaluation backend') && (await text()).includes('Hierarchy (7 instances)'));
  await shot('source-2-netlist-loaded.png');

  // ---- an edit unloads; Enter loads; a wrong path is a real, readable blocker --------------------------------------
  mark = loads.length;
  await type('Netlist path', ['x'], false); await sleep(800);
  check('editing a loaded path clears the old circuit without a request', loads.length === mark && !(await text()).includes('Hierarchy ('), `${loads.length - mark} request(s)`);
  await enter(); await settle(mark);
  check('Enter loads (one request)', loads.length === mark + 1, `${loads.length - mark} request(s)`);
  check('a missing file is reported as such', (await evaluate(`${PANEL}.querySelector('.blocker')?.textContent ?? ''`)).includes('No such file'), await evaluate(`${PANEL}.querySelector('.blocker')?.textContent ?? ''`));

  // ---- a Windows path is converted (only checkable when the project sits on a Windows drive) -----------------------
  const drive = /^\/mnt\/([a-z])\/(.*)$/.exec(root);
  if (drive) {
    mark = loads.length;
    const windows = `${drive[1].toUpperCase()}:\\${drive[2].replace(/\//g, '\\')}\\tests\\fixtures\\synthetic\\opamp.scs`;
    await type('Netlist path', [windows]); await sleep(500);
    await evaluate(`${BUTTON('Load netlist')}.click()`); await settle(mark);
    check('a Windows path is sent as its WSL path, once', loads.length === mark + 1 && loads[mark].netlist_path === NETLIST, JSON.stringify(loads.slice(mark).map(l => l.netlist_path)));
    check('the box shows the converted path and the netlist is loaded', (await value('Netlist path')) === NETLIST && (await text()).includes('Hierarchy (7 instances)'), await value('Netlist path'));
  } else console.log(`SKIP  Windows path conversion (project root ${root} is not on a Windows drive)`);

  // ---- a path outside the allowed folders: the message uses the form's label ----------------------------------------
  mark = loads.length;
  await type('Netlist path', ['/etc/hostname']); await sleep(300);
  await evaluate(`${BUTTON('Load netlist')}.click()`); await settle(mark);
  const refused = await evaluate(`${PANEL}.querySelector('p.error')?.textContent ?? ''`);
  check('a path outside the allowed folders is refused in the form\'s own words', refused.includes('"Netlist path" is outside the allowed input roots') && !refused.includes('netlist_path'), refused);

  // ---- the example ---------------------------------------------------------------------------------------------------
  mark = loads.length;
  await evaluate(`${BUTTON('Try the example')}.click()`); await settle(mark);
  check('"Try the example" fills both boxes and loads once', loads.length === mark + 1 && (await value('Netlist path')) === NETLIST && (await value('Device mapping (JSON)')) === MAPPING && (await text()).includes('Hierarchy (7 instances)'), `${loads.length - mark} request(s)`);

  // ---- registered tasks are untouched ----------------------------------------------------------------------------------
  mark = loads.length;
  await choose('Source', 'registered_task'); await settle(mark);
  check('back on "Registered task" the task loads by itself again', loads.length === mark + 1 && loads[mark].source === 'registered_task' && (await text()).includes('Hierarchy ('), JSON.stringify(loads.slice(mark).map(l => l.source)));

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
