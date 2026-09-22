// Browser check of the header's blocking-issues BUTTON (there is no frontend test runner in this project).
// Same approach as connection_panel_check.mjs: a throwaway headless Edge over the DevTools protocol against the
// RUNNING workbench (default http://127.0.0.1:8765/). EVERY /api/config/validate request is intercepted and answered
// with a canned report labelled FIXTURE, so the shown issues are known. GET requests pass through; every other
// writing request is refused here, so this check can start, save or probe nothing on the backend it runs against.
// The browser profile is new and temporary: the user's saved configuration is not touched.
// What it pins (user request 2026-09-20): the notifier is a button; the list appears when the button is RELEASED, not
// when it is pressed; it lists ALL blocking issues in full and no other; a second press hides it; it follows a new
// validation, closes when nothing blocks, and does not reopen by itself. Since status record 7.56 (user report
// 2026-09-21): a configuration the schema rejects (HTTP 422) is listed one issue per field, at its row, in the backend's
// plain words, with the schema's own text folded under "Technical details" - also for an older backend's answer. It seeds
// the one MOCK task, synthetic:gpdk045_ota5 (status record 7.59).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 15 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/blocking_issues_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9381, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-issues-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const issue = (level, code, where, message) => ({ level, code, path: where, message: `FIXTURE: ${message}` });
const BLOCKING = [
  issue('error', 'range_inverted', 'parameters[0].lower', 'the lower bound is above the upper bound'),
  issue('blocker', 'heads_divisibility', 'run.network', 'hidden_dim must be divisible by heads'),       // belongs to no editor tab
  issue('error', 'schema', '', 'the configuration was rejected as a whole'),
];
const OTHERS = [issue('warning', 'no_checkpoints', 'output.save_checkpoints', 'checkpoints are off'),
  issue('unresolved', 'circuit_not_loaded', 'circuit', 'not checked against a circuit'), issue('info', 'frozen_no_updates', 'run.mode', 'no updates')];
const report = issues => ({ blocks_run: issues.some(i => i.level === 'error' || i.level === 'blocker'), counts: {}, facts: { circuit_checked: false },
  issues, config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null });
const fixtures = { three: report([OTHERS[0], BLOCKING[0], OTHERS[1], BLOCKING[1], BLOCKING[2], OTHERS[2]]), one: report([BLOCKING[1], OTHERS[0]]), valid: report(OTHERS) };

try {
  // The MOCK task's starter configuration (a read-only GET), so that "Where" can name a parameter row. It is put into
  // the temporary browser profile only, and never validated for real: the reports above are what the page is told.
  // The one MOCK task (status record 7.59), the real OTA5: five rows, the followers of its two pairs at rows 1 and 3.
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture' }, research: {} };  // as "Load starter configuration" merges it
  const ROW_KEY = CONFIG.parameters[0].variable_id;
  // What a backend answers when the schema rejects the configuration (HTTP 422, schema.describe_errors); an older backend
  // sent pydantic's text at parameters.1.variable_id; anything else is one plain failure.
  const FOLLOWERS = [1, 3];
  const PATTERN = "String should match pattern '^[A-Za-z_][A-Za-z0-9_.\\-]*$'";
  const idError = n => ({ path: `parameters[${n}].variable_id`, code: 'invalid_id', technical: `FIXTURE: ${PATTERN} [string_pattern_mismatch]`,
    message: `FIXTURE: "${CONFIG.parameters[n].variable_id}" cannot be an ID: it contains "/".` });
  const rejectedBy = errors => ({ status: 422, body: { detail: { message: 'The configuration does not match the schema', errors } } });
  Object.assign(fixtures, { rejected: rejectedBy(FOLLOWERS.map(idError)),
    rejectedOld: rejectedBy([{ path: 'parameters.3.variable_id', message: `FIXTURE: ${PATTERN}` }, { path: 'run.max_evaluations', message: 'FIXTURE: Input should be a valid integer' }]),
    failed: { status: 500, body: { detail: 'FIXTURE: the backend failed' } } });
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const refused = []; let validations = 0, answerWith = fixtures.three;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') { validations++; return answerWith.status ? fulfil(requestId, answerWith.status, answerWith.body) : fulfil(requestId, 200, answerWith); }
    if (request.method === 'GET') return send('Fetch.continueRequest', { requestId });
    refused.push(`${request.method} ${name}`);                                   // a panel asking on its own; never a start
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
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 60) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const BUTTON = `document.querySelector('header button.issues-button')`;
  const LIST = `document.querySelector('#blocking-issues')`;
  const rows = () => evaluate(`[...(${LIST}?.querySelectorAll('tbody tr') ?? [])].map(tr => [...tr.cells].map(td => td.textContent.trim()))`);
  const headerButton = label => `[...document.querySelectorAll('header button')].find(b => b.textContent === ${JSON.stringify(label)})`;
  const revalidate = async fixture => {                                            // the header's "Static validation" button asks again
    answerWith = fixture; const before = validations;
    await evaluate(`${headerButton('Static validation')}.click()`);
    for (let i = 0; i < 50 && validations === before; i++) await sleep(100);
    await sleep(300);
  };
  const mouse = (type, at) => send('Input.dispatchMouseEvent', { type, x: at.x, y: at.y, button: 'left', buttons: type === 'mousePressed' ? 1 : 0, clickCount: 1 });
  const centre = expression => evaluate(`(() => { const r = ${expression}.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = document.querySelector('header').getBoundingClientRect(); return { x: 0, y: 0, width: 1680, height: Math.min(1050, r.bottom + 170), scale: 1 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))});` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${BUTTON})`, 150))) throw new Error(`the blocking-issues button never appeared (${validations} validation request(s) answered); the page reads: `
    + JSON.stringify(await evaluate(`(document.querySelector('header') ?? document.body).innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- the notifier is a button; nothing is listed before a press ---------------------------------------------
  check('the notifier is a <button>', (await evaluate(`${BUTTON}.tagName`)) === 'BUTTON');
  check('it counts the blocking issues only (3 of 6 reported)', (await evaluate(`${BUTTON}.textContent`)) === '3 blocking issue(s)', await evaluate(`${BUTTON}.textContent`));
  check('the old text notifier is gone', !(await evaluate(`[...document.querySelectorAll('header span')].some(s => /blocking issue/.test(s.textContent))`)));
  check('nothing is listed before a press', !(await evaluate(`!!(${LIST})`)) && (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'false');
  check('Start and the baseline simulation are disabled', await evaluate(`${headerButton('Start')}.disabled && ${headerButton('Single baseline simulation')}.disabled`));
  const heightClosed = await evaluate(`document.querySelector('header').getBoundingClientRect().height`);
  await shot('issues-1-closed.png');

  // ---- the list appears on RELEASE, not on press ---------------------------------------------------------------
  const at = await centre(BUTTON);
  await mouse('mouseMoved', at); await mouse('mousePressed', at); await sleep(400);
  check('while the button is held down nothing is listed yet', !(await evaluate(`!!(${LIST})`)));
  await mouse('mouseReleased', at);
  check('releasing the button shows the list', await until(`!!(${LIST})`, 30));
  check('the button reports the open state', (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'true' && await evaluate(`${BUTTON}.classList.contains('active')`));

  // ---- ALL blocking issues, in full, and no other ---------------------------------------------------------------
  const listed = await rows();
  check('all 3 blocking issues are listed, in report order', listed.length === 3 && listed.every((r, n) => r[0] === String(n + 1) && r[1] === BLOCKING[n].level && r[2] === BLOCKING[n].code), JSON.stringify(listed.map(r => r.slice(0, 3))));
  check('each message is shown in full (not as a tooltip)', listed.every((r, n) => r[4] === BLOCKING[n].message), JSON.stringify(listed.map(r => r[4])));
  check('a row issue names its field and the key of its row', listed[0]?.[3] === `parameters[0].lower row ${ROW_KEY}`, listed[0]?.[3]);
  check('an issue outside the editor tabs is listed with its field', listed[1]?.[3] === 'run.network', listed[1]?.[3]);
  check('an issue without a field reads "(whole configuration)"', listed[2]?.[3] === '(whole configuration)', listed[2]?.[3]);
  check('warnings, unresolved and info lines are not listed', !OTHERS.some(o => JSON.stringify(listed).includes(o.code)));
  const box = await evaluate(`(() => { const h = document.querySelector('header').getBoundingClientRect(), l = ${LIST}.getBoundingClientRect(), m = document.querySelector('main').getBoundingClientRect();
    return { inside: l.top >= h.top && l.bottom <= h.bottom + 1, width: l.width, headerWidth: h.width, headerHeight: h.height, mainTop: m.top, headerBottom: h.bottom, overflowX: document.documentElement.scrollWidth > window.innerWidth }; })()`);
  check('the list is a full-width second line of the header', box.inside && box.width > box.headerWidth - 40 && box.headerHeight > heightClosed + 40, JSON.stringify(box));
  check('it pushes the editors down instead of covering them', box.mainTop >= box.headerBottom && !box.overflowX, JSON.stringify(box));
  await shot('issues-2-open.png');

  // ---- it follows the next validation while it is open ---------------------------------------------------------
  await revalidate(fixtures.one);
  const after = await rows();
  check('an open list follows the next validation (3 -> 1)', after.length === 1 && after[0][2] === 'heads_divisibility' && (await evaluate(`${BUTTON}.textContent`)) === '1 blocking issue(s)', JSON.stringify(after));
  await shot('issues-3-one-left.png');

  // ---- a second press, and the Hide button, close it --------------------------------------------------------------
  await evaluate(`${BUTTON}.click()`);
  check('a second press hides the list', await until(`!(${LIST})`, 30) && (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'false');
  await evaluate(`${BUTTON}.click()`); await until(`!!(${LIST})`, 30);
  await evaluate(`[...${LIST}.querySelectorAll('button')].find(b => b.textContent === 'Hide').click()`);
  check('"Hide" closes it too', await until(`!(${LIST})`, 30));

  // ---- nothing blocks: no button, no list; a later problem does not open the list by itself -------------------------
  await evaluate(`${BUTTON}.click()`); await until(`!!(${LIST})`, 30);
  await revalidate(fixtures.valid);
  check('with nothing blocking the header reads "configuration valid" and the button is gone', !(await evaluate(`!!(${BUTTON})`)) && await evaluate(`[...document.querySelectorAll('header span.ok')].some(s => s.textContent === 'configuration valid')`));
  check('the open list closed with it', !(await evaluate(`!!(${LIST})`)));
  check('Start and the baseline simulation are enabled again', await evaluate(`!${headerButton('Start')}.disabled && !${headerButton('Single baseline simulation')}.disabled`));
  await shot('issues-4-valid.png');
  await revalidate(fixtures.three);
  check('a new problem brings the button back, closed', (await until(`!!(${BUTTON})`, 30)) && !(await evaluate(`!!(${LIST})`)) && (await evaluate(`${BUTTON}.textContent`)) === '3 blocking issue(s)');

  // ---- the keyboard works as for any button --------------------------------------------------------------------------
  await evaluate(`${BUTTON}.focus()`);
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
  check('Enter on the focused button shows the list', await until(`!!(${LIST})`, 30));

  // ---- a configuration the schema rejects: one issue per field, at its row, in plain words (status record 7.56) ------------
  // Before, the page listed ONE issue "(whole configuration)" holding pydantic's list as JSON (user report 2026-09-21).
  await revalidate(fixtures.rejected);
  const schemaRows = await rows();
  const key = n => CONFIG.parameters[n].variable_id;
  check('each rejected field is its own blocking issue (2)', schemaRows.length === 2 && (await evaluate(`${BUTTON}.textContent`)) === '2 blocking issue(s)', JSON.stringify(schemaRows.map(r => r.slice(0, 4))));
  check('each names its field and the key of its row', schemaRows.every((r, n) => r[2] === 'invalid_id' && r[3] === `parameters[${FOLLOWERS[n]}].variable_id row ${key(FOLLOWERS[n])}`), JSON.stringify(schemaRows.map(r => r[3])));
  check('each message is the plain one, not a JSON list', schemaRows.every((r, n) => r[4].startsWith(idError(FOLLOWERS[n]).message)) && !schemaRows.some(r => r[4].includes('[{')), JSON.stringify(schemaRows.map(r => r[4])));
  const TECH = `[...${LIST}.querySelectorAll('tbody tr')].map(tr => tr.querySelector('details.more'))`;
  check('the schema\'s own words are folded under "Technical details"', await evaluate(`${TECH}.every(d => d && !d.open && d.querySelector('summary').textContent === 'Technical details' && !d.querySelector('code').checkVisibility())`));
  await evaluate(`${TECH}[0].querySelector('summary').click()`);
  check('one click shows them', await until(`${TECH}[0].open && ${TECH}[0].querySelector('code').checkVisibility() && ${TECH}[0].querySelector('code').textContent.includes('string_pattern_mismatch')`, 30));
  const EDITOR_ROWS = `[...document.querySelectorAll('section.editors table.editor tbody tr')]`;
  const marked = await evaluate(`${EDITOR_ROWS}.map(tr => [tr.classList.contains('has-error'), tr.querySelector('td.issues').textContent])`);
  check('the Parameters editor marks exactly those rows', marked.length === 5 && marked.every(([bad, text], n) => bad === FOLLOWERS.includes(n) && text === (FOLLOWERS.includes(n) ? 'error: invalid_id' : '')), JSON.stringify(marked));
  await shot('issues-5-rejected.png');
  await revalidate(fixtures.rejectedOld);
  const oldRows = await rows();
  check('an older backend\'s answer is split the same way, its paths written like the report\'s', oldRows.length === 2 && oldRows[0][2] === 'schema'
    && oldRows[0][3] === `parameters[3].variable_id row ${key(3)}` && oldRows[0][4] === `FIXTURE: ${PATTERN}` && oldRows[1][3] === 'run.max_evaluations', JSON.stringify(oldRows));
  check('... without an empty "Technical details"', !(await evaluate(`!!${LIST}.querySelector('details')`)));
  await revalidate(fixtures.failed);
  const failedRows = await rows();
  check('any other failure is one issue with its text only', failedRows.length === 1 && failedRows[0][3] === '(whole configuration)' && failedRows[0][4] === 'FIXTURE: the backend failed', JSON.stringify(failedRows));
  await revalidate(fixtures.valid);
  check('a valid answer clears them', !(await evaluate(`!!(${BUTTON})`)) && (await evaluate(`${EDITOR_ROWS}.filter(tr => tr.classList.contains('has-error')).length`)) === 0);

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
