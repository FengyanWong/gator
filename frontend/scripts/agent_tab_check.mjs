// Browser check of the Agent tab (there is no frontend test runner in this project).
// Drives a throwaway headless Edge over the DevTools protocol against the RUNNING workbench (default
// http://127.0.0.1:8765/) and asserts the model / effort lists and the chat behaviour: Enter / Shift+Enter / IME,
// the pending row, cancel, readable errors, the warnings/unresolved side window, the chat surviving a tab switch.
// /api/agent/propose and /api/agent/cancel are intercepted and answered with canned data labelled `fixture`:
// no agent CLI is started and no usage is spent. The model / effort section DOES save agent settings (provider,
// model, effort) through the real API; they are read first and put back at the end, even after a failure. To
// keep a live setup out of it entirely, point the check at a scratch backend:
//   GATOR_WORKBENCH_SETTINGS_DIR=<empty dir> PYTHONPATH=src python -m gator_workbench.cli serve --port 8768
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:8768/ <run line below>
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/agent_tab_check.mjs)" [screenshot-dir]
// Screenshots go to the given directory, else to the OS temp directory. Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9377, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };
const SAVED_KEYS = ['provider', 'model', 'effort', 'timeout_seconds', 'permission_mode', 'allowed_tools', 'max_turns', 'stream'];
const readSettings = async () => (await fetch(`${APP}api/agent/settings`)).json();
let original = null;                                                // put back in `finally`
for (let attempt = 0; attempt < 6 && !original; attempt++) { original = await readSettings().catch(() => null); if (!original) await sleep(500); }
if (!original) {                                                     // without a snapshot the settings could not be restored: do not start
  console.log(`ERROR the agent settings could not be read from ${APP}; nothing was changed`);
  edge.kill(); try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 400 }); } catch { /* left behind */ }
  process.exit(1);
}

try {
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const paused = []; const consoleErrors = []; const autoAnswer = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); if (p) m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }   // an auto-answer waits for no reply
    else if (m.method === 'Fetch.requestPaused' && autoAnswer.some(a => m.params.request.url.includes(a.match))) {
      const hit = autoAnswer.find(a => m.params.request.url.includes(a.match));
      ws.send(JSON.stringify({ id: ++nextId, method: 'Fetch.fulfillRequest', params: { requestId: m.params.requestId, responseCode: 200,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(hit.body)).toString('base64') } }));
    }
    else if (m.method === 'Fetch.requestPaused') paused.push({ requestId: m.params.requestId, url: m.params.request.url, postData: m.params.request.postData });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async (expression, userGesture = false) => {          // userGesture: a click that may open a window
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const nextPaused = async (suffix, ms = 5000) => {
    for (let waited = 0; waited < ms; waited += 50) {
      const i = paused.findIndex(p => p.url.endsWith(suffix));
      if (i >= 0) return paused.splice(i, 1)[0];
      await sleep(50);
    }
    throw new Error(`no intercepted request for ${suffix}`);
  };
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const enter = async (modifiers = 0) => {
    const k = { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, modifiers };
    await send('Input.dispatchKeyEvent', { type: 'keyDown', text: '\r', unmodifiedText: '\r', ...k });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', ...k });
  };
  const shot = async (name, selector = 'footer') => {
    const clip = await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, scale: 1 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };
  const BOX = `document.querySelector('.compose-main textarea')`;
  const clickTab = label => evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === ${JSON.stringify(label)}).click()`);
  const chatLines = () => evaluate(`[...document.querySelectorAll('.chat .msg')].map(m => m.textContent)`);
  const notesText = () => evaluate(`document.querySelector('.notes').innerText`);

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/agent/propose', requestStage: 'Request' }, { urlPattern: '*/api/agent/cancel', requestStage: 'Request' }, { urlPattern: '*/api/agent/readiness', requestStage: 'Request' }, { urlPattern: '*/api/runs/status*', requestStage: 'Request' }] });
  const starter = await (await fetch(`${APP}api/tasks/starter?task_key=synthetic:opamp`)).json();
  const seeded = { schema_version: 'gator-workbench-config-v1', ...(starter.config ?? starter), output: { experiment_name: 'experiment' }, research: {} };   // the page needs `output`
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(seeded))});` });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!document.querySelector('.tabs button')`)); i++) await sleep(100);
  await sleep(1200);

  // ---- tab opens, layout ----------------------------------------------------------------------------------
  const editorTabs = await evaluate(`[...document.querySelectorAll('section.editors .tabs button')].map(b => b.textContent.trim())`);
  check('the three editor tabs are Parameters, Probes and Specs, in that order', editorTabs.length === 3 && [/^Parameters \(\d+\)$/, /^Probes \(\d+\)$/, /^Specs \(\d+\)$/].every((name, i) => name.test(editorTabs[i])), editorTabs.join(' | '));
  await clickTab('Agent'); await sleep(500);
  check('the empty conversation names the editor tabs the same way', (await evaluate(`document.querySelector('.chat-empty')?.textContent ?? ''`)).includes('a draft of the Parameters, Probes or Specs tab'));
  check('provider select shows the backend setting', (await evaluate(`document.querySelector('.agent-side select').value`)) === 'claude_code');
  const geo = await evaluate(`(() => { const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) }; };
    return { chat: r('.chat'), box: r('.compose-main textarea'), main: r('.compose-main'), notes: r('.notes'), footer: r('footer') }; })()`);
  console.log('geometry', JSON.stringify(geo));
  check('side window sits to the right of the message box', geo.notes.x >= geo.box.x + geo.box.w - 1);
  check('side window is level with the message box area', Math.abs(geo.notes.y - geo.main.y) <= 6 && geo.notes.h >= 100, `notes ${geo.notes.h}px vs compose ${geo.main.h}px`);
  check('chat keeps a usable height', geo.chat.h >= 80, `${geo.chat.h}px`);
  check('side window starts with its heading only', (await notesText()).trim() === 'Warnings, unresolved, errors');
  check('the message box carries no key hint', !(await evaluate(`${BOX}.placeholder`)).includes('Enter') && (await evaluate(`${BOX}.placeholder`)).startsWith('Describe what you need'));
  await shot('0-empty.png');

  // ---- model and effort lists (saved through the real settings API; restored in `finally`) -------------------------
  const FIELD = name => `[...document.querySelectorAll('.agent-side label')].find(l => l.firstChild.textContent.trim() === ${JSON.stringify(name)})`;
  const pick = async (name, value) => { await evaluate(`(() => { const s = ${FIELD(name)}.querySelector('select');
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)}); s.dispatchEvent(new Event('change', { bubbles: true })); })()`); await sleep(700); };
  const options = name => evaluate(`[...${FIELD(name)}.querySelectorAll('option')].map(o => o.value)`);
  const shownOption = name => evaluate(`(() => { const s = ${FIELD(name)}.querySelector('select'); return { text: s.selectedOptions[0].textContent, disabled: s.disabled }; })()`);
  const sideHint = () => evaluate(`document.querySelector('.agent-side p.hint').textContent`);
  let listed = await options('Agent model');
  check('model list: CLI default first, the provider\'s models, Custom... last', listed[0] === '' && listed.at(-1) === '__custom__' && ['fable', 'opus', 'sonnet', 'haiku', 'claude-sonnet-5'].every(m => listed.includes(m)), listed.join(' '));
  check('effort list: CLI default + the five Claude levels', (await options('Effort')).join(' ') === ' low medium high xhigh max');
  check('the hint says showing the list calls no model', (await sideHint()).includes('calls no model'));
  const usingLine = () => evaluate(`document.querySelector('.agent-using span').textContent`);
  check('the line above the conversation names provider, model and effort in use', /^Next request: claude_code, model .+, effort .+/.test(await usingLine()), await usingLine());
  await pick('Agent model', 'haiku');
  let effortBox = await shownOption('Effort');
  check('a model without effort greys the effort box out', effortBox.disabled && effortBox.text === 'ignored by this model' && (await sideHint()).includes('Effort is not supported'));
  await shot('0b-haiku.png', '.agent-side');
  await pick('Agent model', 'sonnet');
  await pick('Effort', 'low');
  let saved = await readSettings();
  check('a choice is saved in the backend', saved.model === 'sonnet' && saved.effort === 'low', `${saved.model} / ${saved.effort}`);
  check('... and shown as the model and effort in use', (await usingLine()) === 'Next request: claude_code, model sonnet, effort low');
  check('the hint shows the chosen model\'s note', (await sideHint()).includes('$2 / $10'));
  await pick('Agent model', 'haiku');
  saved = await readSettings();
  check('switching to a model without effort clears the saved level', saved.model === 'haiku' && saved.effort === null && (await usingLine()).endsWith('model haiku, effort not used by this model'));
  await pick('Agent model', '__custom__');
  await evaluate(`${FIELD('Agent model')}.querySelector('input').focus()`);
  await send('Input.insertText', { text: 'some-future-model' });
  await evaluate(`${FIELD('Agent model')}.querySelector('input').blur()`); await sleep(700);
  saved = await readSettings();
  check('Custom... accepts a name outside the list', saved.model === 'some-future-model' && (await shownOption('Agent model')).text === 'Custom...' && (await options('Effort')).length === 6);
  await pick('Provider', 'codex');
  saved = await readSettings();
  listed = await options('Agent model');
  const codexEfforts = await options('Effort');
  check('another provider brings its own lists and starts from its CLI default', saved.provider === 'codex' && saved.model === null && saved.effort === null
    && listed.includes('gpt-5.6-sol') && !listed.includes('sonnet') && codexEfforts.includes('minimal') && !codexEfforts.includes('max'), codexEfforts.join(' '));
  check('the Codex list says it was never exercised', (await sideHint()).includes('never been installed'));
  await shot('0c-codex.png', '.agent-side');
  await pick('Provider', 'claude_code');
  saved = await readSettings();
  check('back on Claude Code with the CLI default', saved.provider === 'claude_code' && saved.model === null && (await shownOption('Agent model')).text.startsWith('CLI default'));

  // ---- Shift+Enter breaks the line, Enter sends ---------------------------------------------------------------
  await evaluate(`${BOX}.focus()`);
  await send('Input.insertText', { text: 'Set the gain target to 60 dB (from my spec sheet).' });
  await enter(8);                                                       // Shift
  await send('Input.insertText', { text: 'Keep power where it is.' });
  await sleep(300);
  check('Shift+Enter inserts a line break', (await evaluate(`${BOX}.value`)) === 'Set the gain target to 60 dB (from my spec sheet).\nKeep power where it is.');
  check('Shift+Enter sends nothing', paused.length === 0);
  await enter();
  const first = await nextPaused('/api/agent/propose');
  const sentBody = JSON.parse(first.postData);
  check('Enter sends the request', sentBody.prompt === 'Set the gain target to 60 dB (from my spec sheet).\nKeep power where it is.' && /^[0-9a-f]{32}$/.test(sentBody.request_id), `kind=${sentBody.kind}`);
  check('message box clears on send', (await evaluate(`${BOX}.value`)) === '');
  await sleep(2300);
  const pendingText = await evaluate(`document.querySelector('.msg.pending')?.textContent ?? ''`);
  check('pending row counts the wait', /Sent\. Waiting for the agent's reply\.\.\. [2-4] s/.test(pendingText), pendingText.slice(0, 60));
  const rowButtons = await evaluate(`[...document.querySelectorAll('.compose-main > .row button')].map(b => b.textContent)`);
  check('there is no send button (Enter sends); while waiting the row offers Cancel', !rowButtons.some(t => /proposal|Waiting/.test(t)) && rowButtons.includes('Cancel request'), rowButtons.join(' | '));
  await shot('1-pending.png');
  await fulfil(first.requestId, 200, { proposal_id: 'fixture-1', proposal_hash: 'fixture', origin: 'fixture', kind: 'targets',
    reasoning: 'I set the gain target from your spec sheet.\n\n- `gain` target: **60 dB**\n- power: unchanged\n\nThree things I could not determine are listed as unresolved.',
    warnings: ['The 60 dB gain target is close to the simulated baseline (58.2 dB); the default budget may be too small to see an improvement.', 'Phase margin has no target, so stability is not constrained.'],
    unresolved: ['Load capacitance for the gain measurement was not given.', 'Supply corner (nominal only?) was not stated.', 'No upper limit on power was given.'],
    diff: [{ section: 'targets', key: 'gain', change: 'changed', fields: [{ field: 'value', before: 55, after: 60 }] }], circuit_changes: [] });
  await sleep(500);
  let lines = await chatLines();
  check('reply text is in the chat', lines.some(l => l.includes('I set the gain target')));
  check('chat holds no warning/unresolved lists any more', (await evaluate(`document.querySelectorAll('.chat .issue, .chat .warn').length`)) === 0);
  const look = await evaluate(`(() => { const reply = document.querySelector('.msg.reply'), mine = document.querySelector('.msg.user');
    return { items: reply.querySelectorAll('.text ul li').length, code: reply.querySelector('.text code')?.textContent, bold: reply.querySelector('.text b')?.textContent,
      who: reply.querySelector('.who').textContent, when: reply.querySelector('.when').textContent, mineRight: mine.getBoundingClientRect().left > reply.getBoundingClientRect().left + 100,
      myBreaks: getComputedStyle(mine.querySelector('.text')).whiteSpace, raw: reply.textContent.includes('**') || reply.textContent.includes('\`') }; })()`);
  check('a reply is formatted: list, code and bold, no raw marks', look.items === 2 && look.code === 'gain' && look.bold === '60 dB' && !look.raw, JSON.stringify(look));
  check('bubbles: yours on the right with its line breaks, the agent named with the model and effort it ran on, clock time shown', look.mineRight && look.myBreaks === 'pre-wrap' && look.who.startsWith('Agent (fixture)') && /, effort /.test(look.who) && /\d{2}:\d{2}:\d{2}$/.test(look.who), look.who);
  check('chat line carries a count badge', lines.some(l => l.includes('3 unresolved, 2 warnings')));
  let notes = await notesText();
  check('side window lists unresolved + warnings', notes.includes('Unresolved (3)') && notes.includes('Warnings (2)') && notes.includes('Load capacitance') && notes.includes('Phase margin'));
  check('pending row is gone after the reply', (await evaluate(`!document.querySelector('.msg.pending')`)));
  const tall = await evaluate(`(() => { const h = s => Math.round(document.querySelector(s).getBoundingClientRect().height); const n = document.querySelector('.notes').getBoundingClientRect(), b = ${BOX}.getBoundingClientRect(), c = document.querySelector('.confirm').getBoundingClientRect();
    return { notes: h('.notes'), confirm: h('.confirm'), chat: h('.chat'), rightOfBox: n.x >= b.right - 1, rightOfProposal: n.x >= c.right - 1, coversBox: n.top <= b.top && n.bottom >= b.bottom }; })()`);
  const reach = await evaluate(`(() => { const send = document.querySelector('.compose-main .row button').getBoundingClientRect(), body = document.querySelector('.bottom-body').getBoundingClientRect(); return { sendBottom: Math.round(send.bottom), panelBottom: Math.round(body.bottom) }; })()`);
  check('with a proposal open the row under the message box is still inside the panel', reach.sendBottom <= reach.panelBottom, JSON.stringify(reach));
  check('with a proposal open the side window spans proposal + message box', tall.notes >= tall.confirm + 100 && tall.rightOfBox && tall.rightOfProposal && tall.coversBox, JSON.stringify(tall));
  await shot('2-reply.png');

  // ---- cancel ---------------------------------------------------------------------------------------------------
  await evaluate(`${BOX}.focus()`);
  await send('Input.insertText', { text: 'make it faster' });
  await enter();
  const second = await nextPaused('/api/agent/propose');
  await sleep(1100);
  await evaluate(`[...document.querySelectorAll('.compose-main button')].find(b => b.textContent === 'Cancel request').click()`);
  const cancelCall = await nextPaused('/api/agent/cancel');
  check('Cancel names the running request', JSON.parse(cancelCall.postData).request_id === JSON.parse(second.postData).request_id);
  await fulfil(cancelCall.requestId, 200, { cancelled: true });
  await fulfil(second.requestId, 409, { detail: { code: 'cancelled', meaning: 'The request was cancelled by the user.', detail: 'The request was cancelled by the user.', configuration_unchanged: true } });
  await sleep(500);
  lines = await chatLines();
  check('cancel is a plain line, not an HTTP error', /^Workbench.*Cancelled by you after [1-3] s\./.test(lines.at(-1)) && !lines.at(-1).includes('HTTP'), lines.at(-1).slice(0, 70));
  check('cancelled text returns to the message box', (await evaluate(`${BOX}.value`)) === 'make it faster');
  check('side window still shows the last REPLY after a system line', (await notesText()).includes('Unresolved (3)'));
  await shot('3-cancelled.png');

  // ---- an agent error with a list ---------------------------------------------------------------------------------
  await evaluate(`${BOX}.focus()`);
  await enter();
  const third = await nextPaused('/api/agent/propose');
  await fulfil(third.requestId, 409, { detail: { code: 'schema_failure', meaning: 'The structured output did not satisfy the schema.', detail: '2 problems in the structured output',
    problems: ['`patch` must be a list', 'targets/gain: unknown unit "dBm"'], configuration_unchanged: true } });
  await sleep(500);
  lines = await chatLines();
  check('error line shows the reason, not "HTTP 409"', lines.at(-1).includes('schema_failure: 2 problems in the structured output (your configuration is unchanged)') && !lines.at(-1).includes('HTTP 409'), lines.at(-1).slice(0, 90));
  notes = await notesText();
  check('side window follows the newest reply (the error)', notes.includes('Problems (2)') && notes.includes('unknown unit') && !notes.includes('Unresolved (3)'));
  await shot('4-error.png');

  // ---- older line's notes on demand ------------------------------------------------------------------------------
  await evaluate(`document.querySelector('.chat .notes-link').click()`); await sleep(300);
  notes = await notesText();
  check('clicking an older badge shows that line\'s notes', notes.includes('Unresolved (3)') && notes.includes('back to the latest reply'));
  check('that chat line is highlighted', (await evaluate(`document.querySelectorAll('.chat .msg.focused').length`)) === 1);
  await shot('5-older.png');
  await evaluate(`document.querySelector('.notes .notes-link').click()`); await sleep(200);
  check('"back to the latest reply" returns', (await notesText()).includes('Problems (2)'));

  // ---- IME: an Enter that confirms a candidate must not send ----------------------------------------------------
  const ime = await evaluate(`(() => { const box = ${BOX}; const fire = init => { const e = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...init }); box.dispatchEvent(e); return e.defaultPrevented; };
    return { composing: fire({ isComposing: true }), plain: fire({}) }; })()`);
  await sleep(300);
  check('Enter during IME composition is left alone', ime.composing === false);
  check('a plain Enter is taken by the handler', ime.plain === true);
  const fourth = await nextPaused('/api/agent/propose', 1500).catch(() => null);      // the plain one sends "make it faster" again
  check('only the plain Enter produced a request', !!fourth && paused.length === 0);
  if (fourth) await fulfil(fourth.requestId, 200, { proposal_id: 'fixture-2', proposal_hash: 'fixture', origin: 'fixture', kind: 'targets', reasoning: 'Nothing to change.', warnings: [], unresolved: [], diff: [], circuit_changes: [] });
  await sleep(400);
  check('a clean reply empties the side window', (await notesText()).includes('Nothing listed for this reply'));

  // ---- the chat survives a tab switch ----------------------------------------------------------------------------
  const before = (await chatLines()).length;
  await clickTab('Run status'); await sleep(300);
  check('Agent tab is hidden, not removed', (await evaluate(`getComputedStyle(document.querySelector('.agent')).display`)) === 'none');
  await clickTab('Agent'); await sleep(300);
  check('chat is intact after switching tabs', (await chatLines()).length === before && before >= 6, `${before} lines`);
  await shot('6-full.png', '.layout');
  // ---- modify_fields: which rows were selected --------------------------------------------------------------------------
  const ticked = await evaluate(`(() => { const boxes = [...document.querySelectorAll('main table.editor tbody tr td:first-child input[type=checkbox]')]; boxes.slice(0, 2).forEach(b => b.click()); return boxes.length; })()`);
  await sleep(300);
  await evaluate(`[...document.querySelectorAll('main button')].find(b => b.textContent.startsWith('Modify selected with agent')).click()`);
  await sleep(500);
  const picked = await evaluate(`(() => { const row = document.querySelector('.compose-main > .row'); return { kind: row.querySelector('select').value, count: row.querySelector('button.notes-link')?.textContent, open: !!document.querySelector('.selection-info') }; })()`);
  check('"Modify selected with agent..." brings the rows to the Agent tab as a count', ticked >= 2 && picked.kind === 'modify_fields' && picked.count === '2 selected row(s)' && !picked.open, JSON.stringify(picked));
  await evaluate(`document.querySelector('.compose-main > .row button.notes-link').click()`); await sleep(300);
  const info = await evaluate(`(() => { const box = document.querySelector('.selection-info'), panel = document.querySelector('.bottom-body'); return { rows: [...box.querySelectorAll('li')].map(li => li.textContent.replace(/\\s+/g, ' ').trim()),
    visible: box.getBoundingClientRect().bottom <= panel.getBoundingClientRect().bottom + 1 }; })()`);
  const expected = seeded.parameters.slice(0, 2);
  check('clicking the count lists the selected rows: row, table, what it is now, what may change - in view, numbers short', info.rows.length === 2 && info.visible
    && info.rows.every((r, i) => r.startsWith(expected[i].variable_id + ' (parameters)') && r.includes('instance_path ' + expected[i].instance_path) && r.endsWith('may change: the whole row'))
    && info.rows[0].includes('lower 1e-6') && !info.rows[0].includes('0.00000'), JSON.stringify(info));
  await shot('6a-selection.png');
  await evaluate(`document.querySelector('.compose-main > .row button.notes-link').click()`); await sleep(200);
  check('a second click closes the list again', !(await evaluate(`!!document.querySelector('.selection-info')`)));
  await evaluate(`(() => { const s = document.querySelector('.compose-main > .row select'); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, 'draft_config'); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  await sleep(200);
  check('the count belongs to modify_fields only', !(await evaluate(`!!document.querySelector('.compose-main > .row button.notes-link')`)));

  // ---- what is missing before the run can start: free checklist first, the agent second -----------------------------
  const missingButton = `[...document.querySelectorAll('.compose-main > .row button')].find(b => b.textContent.startsWith("What's missing"))`;
  const places = await evaluate(`(() => { const row = [...document.querySelectorAll('.compose-main > .row button')].map(b => b.textContent), top = [...document.querySelectorAll('.agent-using button')].map(b => b.textContent);
    const line = document.querySelector('.agent-using').getBoundingClientRect(), review = [...document.querySelectorAll('.agent-using button')].at(-1).getBoundingClientRect(); return { row, top, reviewAtRightEnd: Math.abs(line.right - review.right) <= 2 }; })()`);
  check('"What\'s missing?" stands next to "Export task description"; "Review settings" closes the line above the conversation', places.row.indexOf("What's missing?") === places.row.indexOf('Export task description') + 1
    && places.top.join('|') === 'Review settings' && places.reviewAtRightEnd, JSON.stringify(places));
  await evaluate(`${missingButton}.click()`);
  const realCall = await nextPaused('/api/agent/readiness');
  await send('Fetch.continueRequest', { requestId: realCall.requestId });            // the real backend answers: it is free
  await sleep(1500);
  const card = await evaluate(`(() => { const c = [...document.querySelectorAll('.msg.checklist')].at(-1); return c ? { items: c.querySelectorAll('ul.checklist li').length, text: c.innerText } : null; })()`);
  check('"What\'s missing?" is answered by the backend itself, as a checklist', !!card && card.items >= 6 && card.text.includes('Circuit') && card.text.includes('No model was called'), card ? `${card.items} items` : 'no card');
  check('... without any agent request', paused.filter(p => p.url.endsWith('/api/agent/propose')).length === 0);
  await evaluate(`${missingButton}.click()`);
  const oldServer = await nextPaused('/api/agent/readiness');                 // a server started before this function existed
  await fulfil(oldServer.requestId, 405, { detail: 'Method Not Allowed' });
  await sleep(400);
  const told = (await chatLines()).at(-1);
  check('a server older than the page is explained, not reported as "Method Not Allowed"', told.includes('older than this page') && told.includes('Restart it') && !told.includes('Method Not Allowed'), told.slice(0, 90));
  await evaluate(`${missingButton}.click()`);
  const cannedCall = await nextPaused('/api/agent/readiness');
  const entry = (id, title, status, who, detail, action = '') => ({ id, title, status, who, detail, action });
  await fulfil(cannedCall.requestId, 200, { ready: false, note: 'Computed by the backend from the live configuration. No model was called, nothing was probed.', facts: {}, issues: [], run: {},
    next: entry('parameters', 'Parameters', 'missing', 'agent', 'No optimized variable yet.'),
    items: [entry('circuit', 'Circuit', 'done', 'you', 'REAL circuit read: 10 devices.'),
      entry('parameters', 'Parameters', 'missing', 'agent', 'No optimized variable yet.', 'Fill in the "Parameters" tab, or ask the agent to draft it from the circuit.'),
      entry('targets', 'Specs', 'missing', 'agent', 'No active hard constraint yet.', 'State the requirement and where it comes from.'),
      entry('connection', 'Connection', 'unknown', 'you', 'unknown (never tested in this backend session).', 'Press "Connection" (left), then "Test connection" in its window.'),
      entry('authorization', 'Real simulation budget', 'at_start', 'you', 'Pressing Start asks you to authorize 60 real evaluation(s).'),
      entry('start', 'Start', 'missing', 'you', '2 item(s) above still block a start.')] });
  await sleep(500);
  const canned = await evaluate(`(() => { const c = [...document.querySelectorAll('.msg.checklist')].at(-1); const li = [...c.querySelectorAll('ul.checklist li')];
    return { marks: li.map(l => l.querySelector('.check-mark').textContent).join(''), tags: li.map(l => l.querySelector('.check-who')?.textContent ?? '-'), head: c.querySelector('.text').textContent,
      fix: [...c.querySelectorAll('button')].map(b => b.textContent), action: c.querySelector('.check-missing .check-action')?.textContent }; })()`);
  check('the checklist marks each item, says who acts and what to do next', canned.marks === '\u2714\u2718\u2718?\u25B6\u2718' && canned.tags[1] === 'agent can draft it' && canned.tags[3] === 'yours' && canned.tags[0] === '-'
    && canned.head.startsWith('Not ready yet. Next: Parameters') && (canned.action ?? '').includes('ask the agent'), JSON.stringify(canned));
  check('it offers the agent only for what the agent can fix: fewest changes first, the no-assumption way second', canned.fix.join(' | ') === 'Make it startable with the fewest changes | Fix only what needs no assumption', canned.fix.join(' | '));
  const cardButton = label => `[...[...document.querySelectorAll('.msg.checklist')].at(-1).querySelectorAll('button')].find(b => b.textContent === ${JSON.stringify(label)})`;
  await evaluate(`${cardButton('Make it startable with the fewest changes')}.click()`);
  const leanCall = await nextPaused('/api/agent/propose');
  const leanBody = JSON.parse(leanCall.postData);
  check('"fewest changes" is ONE request of kind `minimal_start`', leanBody.kind === 'minimal_start' && leanBody.prompt.includes('as few changes as possible'), leanBody.kind);
  const widthRow = { variable_id: 'm1_w', instance_path: 'M1', parameter_name: 'w', basis: 'PROVISIONAL: 0.5x-2x around the present width of 2 um' };
  await fulfil(leanCall.requestId, 200, { proposal_id: 'fixture-5', proposal_hash: 'fixture', origin: 'fixture', kind: 'minimal_start', circuit_changes: [],
    reasoning: 'I added one optimized width and nothing else; no valid row was touched. A target is still yours: no baseline is on record.',
    warnings: ['Provisional range for m1_w: replace it with your requirement.'], unresolved: ['A hard requirement and where it comes from'],
    patch: [{ op: 'add', section: 'parameters', key: 'm1_w', value: widthRow, basis: widthRow.basis }],
    diff: [{ section: 'parameters', key: 'm1_w', change: 'added', fields: [{ field: 'lower', before: null, after: 1e-6 }, { field: 'upper', before: null, after: 4e-6 }] }],
    checklist: [{ item: 'Parameters', status: 'done', who: 'agent', action: '', basis: 'One provisional width added.' },
      { item: 'Specs', status: 'missing', who: 'you', action: 'State one hard requirement.', basis: 'No baseline on record.' }],
    readiness_after: { ready: false, changed_rows: 1, resolved: ['Parameters'], note: 'Worked out by the backend on the configuration as it would be after approval.',
      remaining: [{ title: 'Specs', who: 'agent', detail: 'No active hard constraint yet.', action: '' }] } });
  await sleep(500);
  const lean = await evaluate(`(() => { const box = document.querySelector('.confirm'); return { verdict: box.querySelector('.verdict')?.innerText, css: box.querySelector('.verdict')?.className, placeholders: box.querySelector('.provisional')?.innerText }; })()`);
  check('the proposal says - from the workbench, not the agent - whether the run would start after approval', (lean.verdict ?? '').startsWith('After you approve, still missing: Specs') && lean.verdict.includes('1 row(s) changed') && lean.verdict.includes('resolves Parameters') && lean.verdict.includes('Checked by the workbench') && lean.css.includes('warn'), lean.verdict);
  check('every placeholder value is called out next to the diff', (lean.placeholders ?? '').includes('placeholders, not your requirements') && lean.placeholders.includes('parameters/m1_w') && lean.placeholders.includes('0.5x-2x'));
  await shot('6c-fewest-changes.png');
  await evaluate(`${cardButton('Fix only what needs no assumption')}.click()`);
  const fixCall = await nextPaused('/api/agent/propose');
  const fixBody = JSON.parse(fixCall.postData);
  check('... as ONE request of kind `readiness` with the standard question', fixBody.kind === 'readiness' && fixBody.prompt.startsWith('What is still missing before this RL run can start?'), `${fixBody.kind}`);
  await fulfil(fixCall.requestId, 200, { proposal_id: 'fixture-4', proposal_hash: 'fixture', origin: 'fixture', kind: 'readiness', reasoning: 'State the gain you need; I drafted the two transistor widths.',
    warnings: [], unresolved: ['Required gain and where it comes from'], diff: [], circuit_changes: [],
    checklist: [{ item: 'Parameters', status: 'done', who: 'agent', action: '', basis: 'Drafted in this proposal.' },
      { item: 'Specs', status: 'missing', who: 'you', action: 'Tell me the gain you need and where the number comes from.', basis: 'Requirements are never invented.' }] });
  await sleep(500);
  const fixed = await evaluate(`(() => { const r = [...document.querySelectorAll('.msg.reply')].at(-1); return { items: r.querySelectorAll('ul.checklist li').length, text: r.innerText }; })()`);
  check('the agent\'s reply shows its own checklist in the same form', fixed.items === 2 && fixed.text.includes('Tell me the gain you need') && fixed.text.includes('yours'));
  await shot('6b-readiness.png');

  // ---- a review of the settings of the whole workbench, offline and online -----------------------------------------------
  const action = label => `[...document.querySelectorAll('.agent-actions button')].find(b => b.textContent === ${JSON.stringify(label)})`;
  const onlineBox = `document.querySelector('.agent-actions input[type=checkbox]')`;
  check('"Review settings" sits above the conversation, with online research off until asked for', (await evaluate(`!!${action('Review settings')} && !${onlineBox}.checked && !${onlineBox}.disabled`)));
  await evaluate(`${action('Review settings')}.click()`);
  const reviewCall = await nextPaused('/api/agent/propose');
  const reviewBody = JSON.parse(reviewCall.postData);
  check('it is ONE request of kind `settings_review`, offline', reviewBody.kind === 'settings_review' && reviewBody.web === false && reviewBody.prompt.startsWith('Review the settings of this run'), JSON.stringify({ kind: reviewBody.kind, web: reviewBody.web }));
  const suggestion = (path, value, now, extra = {}) => ({ path, value, now, panel: path.startsWith('run.network') ? 'RL network' : 'RL network (Advanced)', changes: true, applicable: true, problem: null, alone: null,
    reason: 'Fits a 60-evaluation budget.', source: 'Lighthouse RL (arXiv:2607.14008)', url: 'https://arxiv.org/abs/2607.14008', quote: 'batch size of 32', ...extra });
  await fulfil(reviewCall.requestId, 200, { proposal_id: 'fixture-6', proposal_hash: 'fixture', origin: 'fixture', kind: 'settings_review', reasoning: 'Three settings stand out for this budget.',
    warnings: [], unresolved: [], diff: [], patch: [], circuit_changes: [], suggestions_together: { ok: true, problem: null },
    suggestions: [suggestion('run.advanced.batch_size', 12, 8), suggestion('run.network.hidden_dim', 56, 32, { alone: 'Applied alone it raises a blocking issue (heads_divisibility); apply it together with the related rows.' }),
      suggestion('run.advanced.gamma', 1.5, 0.99, { applicable: false, problem: 'run.advanced.gamma: Input should be less than or equal to 1' })],
    refused_suggestions: ['output.output_root: not a setting an agent may suggest'],
    encoder_ideas: [{ name: 'GPS graph transformer', source: 'Rampasek et al., NeurIPS 2022', url: 'https://arxiv.org/abs/2205.12454', why: 'Global attention next to message passing.', what_it_takes: 'A new encoder class in the optimizer package.' }] });
  await sleep(500);
  const table = () => evaluate(`(() => { const box = [...document.querySelectorAll('.msg.reply .suggestions')].at(-1); const rows = [...box.querySelectorAll('tbody tr')];
    return { rows: rows.map(r => ({ cells: [...r.children].map(td => td.innerText.replace(/\\s+/g, ' ').trim()), canApply: !!r.querySelector('button') && !r.querySelector('button').disabled, applied: r.classList.contains('applied') })),
      all: box.querySelector('.row button').textContent, left: box.innerText.includes('output.output_root'), ideas: box.querySelector('.ideas')?.innerText ?? '', link: box.querySelector('tbody a')?.href }; })()`);
  let review = await table();
  check('the reply lists each suggested setting: panel, now, suggested, why, source with its link', review.rows.length === 3 && review.rows[0].cells[0].includes('RL network (Advanced)') && review.rows[0].cells[0].includes('batch_size')
    && /^\d+$/.test(review.rows[0].cells[1]) && review.rows[0].cells[1] !== '12' && review.rows[0].cells[2] === '12' && review.rows[0].cells[3].includes('Source: Lighthouse RL') && review.rows[0].cells[3].includes('batch size of 32') && review.link === 'https://arxiv.org/abs/2607.14008', JSON.stringify(review.rows[0].cells));
  check('an illegal value cannot be applied and says why; a row that needs its partner says so', !review.rows[2].canApply && review.rows[2].cells[3].includes('less than or equal to 1') && review.rows[1].canApply && review.rows[1].cells[3].includes('together with the related rows'));
  check('what an agent may not suggest is named, and a new encoder is an idea with the reason it cannot be added from here', review.left && review.ideas.includes('GPS graph transformer') && review.ideas.includes('The agent cannot add an encoder') && review.all === 'Apply all (2)');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 2400, deviceScaleFactor: 1, mobile: false });      // tall enough to show the whole reply
  await sleep(300); await evaluate(`[...document.querySelectorAll('.msg.reply .suggestions')].at(-1).scrollIntoView({ block: 'start' })`); await sleep(200);
  await shot('6d-settings-review.png', '.chat');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false }); await sleep(300);
  check('a settings review opens no proposal box: there is no diff to approve', !(await evaluate(`[...document.querySelectorAll('.confirm h4')].some(h => h.textContent.includes('fixture-6'))`)) && (await evaluate(`document.querySelector('.confirm')?.innerText ?? ''`)).includes('readiness') === false);
  await evaluate(`[...document.querySelectorAll('.msg.reply .suggestions')].at(-1).querySelector('tbody tr button').click()`); await sleep(400);
  review = await table();
  check('Apply sets that one setting - the row turns to "applied" with the new value, the rest waits', review.rows[0].applied && review.rows[0].cells[1] === '12' && review.rows[0].cells[4] === 'applied' && !review.rows[1].applied && review.all === 'Apply all (1)');
  await evaluate(`[...document.querySelectorAll('.msg.reply .suggestions')].at(-1).querySelector('.row button').click()`); await sleep(400);
  review = await table();
  check('"Apply all" sets the remaining legal ones and leaves the illegal one alone', review.rows[1].applied && !review.rows[2].applied && review.all === 'Apply all (0)');
  await evaluate(`${onlineBox}.click()`); await sleep(200);
  await evaluate(`${action('Review settings')}.click()`);
  const onlineCall = await nextPaused('/api/agent/propose');
  await sleep(1200);
  const waitingOnline = await evaluate(`document.querySelector('.msg.pending').innerText`);
  check('with the box ticked the request asks for online research, and the waiting line says it takes minutes (with no time limit: 7.48)', JSON.parse(onlineCall.postData).web === true && waitingOnline.includes('reading publications online') && waitingOnline.includes('No time limit'), waitingOnline.slice(0, 90));
  await fulfil(onlineCall.requestId, 200, { proposal_id: 'fixture-7', proposal_hash: 'fixture', origin: 'fixture', kind: 'settings_review', reasoning: 'Nothing further.', warnings: [], unresolved: [], diff: [], patch: [], circuit_changes: [],
    suggestions: [], refused_suggestions: [], encoder_ideas: [], suggestions_together: { ok: true, problem: null } });
  await sleep(400);
  await evaluate(`${onlineBox}.click()`);

  // ---- detached into a window of its own, and back --------------------------------------------------------------
  const pages = async () => (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).filter(t => t.type === 'page');
  const popupTarget = async (present, ms = 5000) => { for (let waited = 0; waited < ms; waited += 100) { const found = (await pages()).find(t => t.id !== target.id && t.title === 'GATOR - agent conversation'); /* by title: Edge may open pages of its own */ if (!!found === present) return found ?? null; await sleep(100); } throw new Error(`the detached window did not ${present ? 'appear' : 'close'}`); };
  const attachTo = async page => {                                   // a second DevTools session, for the detached window
    const socket = new WebSocket(page.webSocketDebuggerUrl); await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let id = 0; const waiting = new Map();
    socket.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id) { const w = waiting.get(m.id); waiting.delete(m.id); m.error ? w.reject(new Error(JSON.stringify(m.error))) : w.resolve(m.result); }
      else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push('detached: ' + (m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text)); };
    socket.onclose = () => { for (const w of waiting.values()) w.reject(new Error('the detached window went away')); waiting.clear(); };
    const call = (method, params = {}) => new Promise((resolve, reject) => { const n = ++id; waiting.set(n, { resolve, reject }); socket.send(JSON.stringify({ id: n, method, params })); });
    await call('Runtime.enable');
    const run = async (expression, userGesture = false) => { const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text); return r.result.value; };
    return { call, run, close: () => socket.close() };
  };
  const linesBefore = (await chatLines()).length;
  const tabControl = await evaluate(`(() => { const c = document.querySelector('.tabs .tab-detach'), group = c?.closest('.tab-group'), label = group?.querySelector('button');
    return c ? { label: label.textContent, rightOfLabel: c.getBoundingClientRect().left >= label.getBoundingClientRect().right - 1, inTab: c.getBoundingClientRect().right <= group.getBoundingClientRect().right + 1,
      small: c.getBoundingClientRect().width <= 22, says: c.getAttribute('aria-label'), nested: !!c.closest('button:not(.tab-detach)'), oldButton: !!document.querySelector('footer button.detach') } : null; })()`);
  check('the detach control sits on the "Agent" tab, at its right end, like a browser tab\'s button', !!tabControl && tabControl.label === 'Agent' && tabControl.rightOfLabel && tabControl.inTab && tabControl.small
    && tabControl.says.startsWith('Detach') && !tabControl.nested && !tabControl.oldButton, JSON.stringify(tabControl));
  await evaluate(`document.querySelector('.tabs .tab-detach').click()`, true);
  let page = await popupTarget(true);
  let far = await attachTo(page);
  await far.call('Emulation.setDeviceMetricsOverride', { width: 1180, height: 900, deviceScaleFactor: 1, mobile: false });   // a headless popup ignores the requested size
  await sleep(600);
  const there = await far.run(`(() => { const chat = document.querySelector('.agent.detached .chat'), notes = document.querySelector('.notes'), mine = document.querySelector('.msg.user');
    return { title: document.title, lines: document.querySelectorAll('.chat .msg').length, font: chat && getComputedStyle(chat).fontSize, mine: mine && getComputedStyle(mine).alignSelf,
      notesShare: notes ? notes.getBoundingClientRect().height / innerHeight : 0, notesRight: notes && chat ? notes.getBoundingClientRect().left >= chat.getBoundingClientRect().right : false,
      button: document.querySelector('button.detach')?.textContent, using: document.querySelector('.agent-using span')?.textContent, chatShare: chat ? chat.getBoundingClientRect().height / innerHeight : 0 }; })()`);
  check('Detach opens a window of its own holding the same conversation', there.title === 'GATOR - agent conversation' && there.lines === linesBefore && there.button === 'Bring back into the workbench', JSON.stringify(there));
  check('the detached window is styled: larger type, bubbles, a tall conversation, notes as a full-height column, model and effort named', there.font === '14.5px' && there.mine === 'flex-end' && there.notesShare > 0.8 && there.notesRight && there.chatShare > 0.4 && /^Next request: /.test(there.using ?? ''), `${there.font} ${there.mine} notes ${(there.notesShare * 100).toFixed(0)} % of the height`);
  const here = await evaluate(`({ away: !!document.querySelector('.agent-away'), inline: !!document.querySelector('footer .agent') })`);
  check('the workbench says where the conversation went', here.away && !here.inline);
  await clickTab('Run status'); await sleep(300);
  check('the bottom panel is free for other tabs while detached', (await far.run(`document.querySelectorAll('.chat .msg').length`)) === linesBefore && (await evaluate(`getComputedStyle(document.querySelector('.agent-away')).display`)) === 'none');
  const { data: farShot } = await far.call('Page.captureScreenshot', { format: 'png' });
  writeFileSync(path.join(out, '7-detached.png'), Buffer.from(farShot, 'base64'));
  await far.run(`document.querySelector('.compose-main textarea').focus()`);
  await far.call('Input.insertText', { text: 'asked from the detached window' });
  const farKey = { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 };
  await far.call('Input.dispatchKeyEvent', { type: 'keyDown', text: '\r', unmodifiedText: '\r', ...farKey }); await far.call('Input.dispatchKeyEvent', { type: 'keyUp', ...farKey });
  const fifth = await nextPaused('/api/agent/propose');
  check('Enter in the detached window sends the request', JSON.parse(fifth.postData).prompt === 'asked from the detached window');
  await fulfil(fifth.requestId, 200, { proposal_id: 'fixture-3', proposal_hash: 'fixture', origin: 'fixture', kind: 'targets', reasoning: 'Answer shown in the detached window.', warnings: ['one warning'], unresolved: [], diff: [], circuit_changes: [] });
  await sleep(500);
  const answered = await far.run(`({ lines: document.querySelectorAll('.chat .msg').length, last: document.querySelector('.chat .msg:last-of-type .text').textContent, notes: document.querySelector('.notes').innerText })`);
  check('the reply and its notes arrive in the detached window', answered.lines === linesBefore + 2 && answered.last === 'Answer shown in the detached window.' && answered.notes.includes('Warnings (1)'));
  await Promise.race([far.run(`document.querySelector('button.detach').click()`, true).catch(() => {}), sleep(2000)]);      // the click closes the very window that would answer
  await popupTarget(false); far.close(); await sleep(400);
  await clickTab('Agent'); await sleep(300);
  check('"Bring back" closes the window and the conversation is in the tab again, complete', (await chatLines()).length === linesBefore + 2 && !(await evaluate(`!!document.querySelector('.agent-away')`)));
  await evaluate(`document.querySelector('.tabs .tab-detach').click()`, true);
  page = await popupTarget(true); await sleep(400);
  await send('Target.closeTarget', { targetId: page.id });              // the user closes the window with its own X
  await popupTarget(false); await sleep(500);
  check('closing the detached window by itself also brings the conversation back', (await evaluate(`!!document.querySelector('footer .agent') && !document.querySelector('.agent-away')`)) && (await chatLines()).length === linesBefore + 2);
  // from another bottom tab: the control detaches without switching tabs, shows its state, and brings the conversation back
  await clickTab('Run status'); await sleep(300);
  await evaluate(`document.querySelector('.tabs .tab-detach').click()`, true);
  await popupTarget(true); await sleep(500);
  const away = await evaluate(`(() => { const c = document.querySelector('.tabs .tab-detach'); return { says: c.getAttribute('aria-label'), detachedLook: c.closest('.tab-group').classList.contains('detached'),
    activeTab: document.querySelector('footer .tabs > button.active')?.textContent ?? (document.querySelector('footer .tabs .tab-group.active') ? 'Agent' : null) }; })()`);
  check('detaching from another tab does not switch tabs, and the tab shows that the conversation is away', away.activeTab === 'Run status' && away.detachedLook && away.says.startsWith('Bring the conversation back'), JSON.stringify(away));
  await shot('8a-tab-detached.png', 'footer .tabs');
  await evaluate(`document.querySelector('.tabs .tab-detach').click()`, true);
  await popupTarget(false); await sleep(500);
  await clickTab('Agent'); await sleep(300);
  check('the same control brings the conversation back', (await chatLines()).length === linesBefore + 2 && !(await evaluate(`!!document.querySelector('.agent-away')`))
    && (await evaluate(`document.querySelector('.tabs .tab-detach').getAttribute('aria-label')`)).startsWith('Detach'));
  await shot('8b-tab.png', 'footer .tabs');
  await shot('8-bubbles.png');
  // ---- the results of a run: nothing to review without a run, then a canned run selected ---------------------------------
  const reviewRun = `[...document.querySelectorAll('.compose-main > .row button')].find(b => b.textContent === 'Review results')`;
  const idle = await evaluate(`({ disabled: ${reviewRun}.disabled, why: ${reviewRun}.title, after: ${reviewRun}.previousElementSibling.textContent })`);
  check('"Review results" stands after "What\'s missing?" and waits for a run to be chosen', idle.disabled && idle.why.includes('Runs...') && idle.after === "What's missing?", JSON.stringify(idle));
  const fakeRun = 'D:/gator/outputs/mock/check__abc/runs/mock_opamp/scratch__seed7__0123456789ab';
  autoAnswer.push({ match: '/api/runs/status', body: { run_dir: fakeRun, state: 'completed', stop_reason: 'budget_exhausted', worker_alive: false, mode: 'scratch', concurrency: 1, learner_updates: 40,
    manifest: { mock: true, mock_notice: 'MOCK' }, budget: { charged: 60, max_evaluations: 60, in_flight: 0, completed: 60, failed: 0, remaining: 0, launches: 60, retries: 0, cache_hits: 0 }, active_workers: [] } });
  await evaluate(`localStorage.setItem('gator-workbench-current-run-v1', ${JSON.stringify(fakeRun)})`);
  await send('Page.reload');
  for (let i = 0; i < 100 && !(await evaluate(`!!document.querySelector('footer .tabs button')`).catch(() => false)); i++) await sleep(100);
  await sleep(1200); await clickTab('Agent'); await sleep(500);
  check('with a run chosen the button is ready and names that run', (await evaluate(`!${reviewRun}.disabled && ${reviewRun}.title.includes('scratch__seed7__0123456789ab')`)));
  await evaluate(`${reviewRun}.click()`);
  const runCall = await nextPaused('/api/agent/propose');
  const runBody = JSON.parse(runCall.postData);
  check('it is ONE request of kind `run_review` for that run - never online', runBody.kind === 'run_review' && runBody.run_dir === fakeRun && runBody.web === false && runBody.prompt.includes('(run scratch__seed7__0123456789ab)'), JSON.stringify({ kind: runBody.kind, web: runBody.web }));
  await fulfil(runCall.requestId, 200, { proposal_id: 'fixture-8', proposal_hash: 'fixture', origin: 'fixture', kind: 'run_review', warnings: [], unresolved: [], diff: [], patch: [], circuit_changes: [],
    reasoning: 'The run found a feasible design after 6 of 60 evaluations.\n\n- 13 of 60 evaluations met the target (`score` >= 0.95)\n- 39 were chosen by the policy, 40 learner updates ran\n\nIt is a MOCK run: this shows the plumbing, not a circuit.',
    suggestions: [{ path: 'run.stop_at_first_feasible', value: true, now: false, panel: 'Run configuration', changes: true, applicable: true, problem: null, alone: null,
      reason: 'The first feasible design came at evaluation 6; the other 54 added nothing to it.', source: 'first_feasible.first_feasible_eval_count = 6, budget.charged = 60', url: '', quote: '' }],
    refused_suggestions: [], encoder_ideas: [], suggestions_together: { ok: true, problem: null }, readiness_after: null });
  await sleep(500);
  const reviewed = await evaluate(`(() => { const r = [...document.querySelectorAll('.msg.reply')].at(-1); return { text: r.querySelector('.text').innerText, bullets: r.querySelectorAll('.text li').length,
    rows: r.querySelectorAll('.suggestions tbody tr').length, source: r.querySelector('.suggestions tbody')?.innerText ?? '', box: !!document.querySelector('.confirm') }; })()`);
  check('the reply explains the run and ties its suggestion to a number of the run; with nothing to approve no proposal box opens', reviewed.text.includes('feasible design after 6 of 60') && reviewed.bullets === 2
    && reviewed.rows === 1 && reviewed.source.includes('first_feasible_eval_count = 6') && !reviewed.box, JSON.stringify(reviewed).slice(0, 200));
  await shot('9-run-review.png');
  await evaluate(`localStorage.removeItem('gator-workbench-current-run-v1')`);
  check('no console errors or exceptions', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  await send('Browser.close').catch(() => {});
} catch (e) {
  failures++; console.log('ERROR', e.stack ?? e);
} finally {
  if (original) {                                                   // the settings the model / effort section changed
    const body = Object.fromEntries(SAVED_KEYS.map(k => [k, original[k]]));
    const restored = await fetch(`${APP}api/agent/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.ok, () => false);
    const now = restored ? await readSettings().catch(() => null) : null;
    check('agent settings are back as they were', !!now && ['provider', 'model', 'effort'].every(k => now[k] === original[k]), now ? `${now.provider} / ${now.model} / ${now.effort}` : 'restore failed');
  }
  edge.kill();
  await sleep(1500);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 400 }); } catch (e) { console.log('profile dir left behind:', profile, e.code); }
  console.log(failures ? `${failures} check(s) failed` : `all checks passed; screenshots in ${out}`);
  process.exit(failures ? 1 : 0);
}
