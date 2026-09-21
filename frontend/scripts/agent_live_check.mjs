// Browser check of the LIVE agent answer (status record 7.48): the thinking summary and the reply appear while they are
// written, the thinking then stays with the reply folded into one line, "Cancel request" keeps what had arrived, and the
// waiting line promises no time limit. Drives a throwaway headless Edge over the DevTools protocol.
//
// Default (hermetic): /api/agent/propose is intercepted and answered with canned Server-Sent Events (and once with a plain
// JSON body, as an older server sends). No agent CLI is started, nothing is saved: safe against the running workbench.
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/agent_live_check.mjs)" [screenshot-dir]
// --live: nothing is intercepted. Needs a SCRATCH backend whose `claude` is the fake CLI of the tests in scenario
// `live_demo` (a thinking summary over ~4 s, then the reply a few characters at a time; a prompt containing FAKE-HANG
// never finishes), so the page is watched receiving a real stream:
//   PATH=<dir with tests/workbench/fixtures/fake_cli.py as `claude`>:$PATH FAKE_CLI_SCENARIO=live_demo FAKE_CLI_PAUSE=4 \
//   GATOR_WORKBENCH_SETTINGS_DIR=<empty dir> PYTHONPATH=src python -m gator_workbench.cli serve --port 8768
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:8768/ <run line above> --live [screenshot-dir]
// --live --codex (status record 7.50): the same with the fake as `codex` too, scenario `codex_demo`; the check SAVES
// provider = codex on that scratch backend. Codex sends whole items: reasoning paragraph by paragraph, the command and the
// web search as steps, the reply in one piece at the end.
// Screenshots go to the given directory, else to the OS temp directory. Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9391, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const LIVE = process.argv.includes('--live'), CODEX = LIVE && process.argv.includes('--codex');
const out = process.argv.slice(2).find(a => !a.startsWith('--')) ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-'));
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
  let nextId = 0; const pending = new Map(); const paused = []; const consoleErrors = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); if (p) m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') paused.push({ requestId: m.params.requestId, url: m.params.request.url, headers: m.params.request.headers, postData: m.params.request.postData });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
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
  const fulfil = (requestId, status, type, text) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: type }], body: Buffer.from(text).toString('base64') });
  const sse = events => events.map(([kind, data]) => `event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`).join(': working\n\n');
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = document.querySelector('footer').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, scale: 1 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };
  const BOX = `document.querySelector('.compose-main textarea')`;
  const ask = async text => {
    await evaluate(`(() => { const box = ${BOX}; box.focus(); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(box, ${JSON.stringify(text)});
      box.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await sleep(150);
    await evaluate(`${BOX}.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))`);
  };
  const pendingView = () => evaluate(`(() => { const p = document.querySelector('.msg.pending'); if (!p) return null;
    return { who: p.querySelector('.who').textContent, thinking: p.querySelector('.thinking-live')?.innerText ?? '', steps: [...p.querySelectorAll('.live-steps li')].map(l => l.textContent),
      reply: p.querySelector('.live-reply')?.innerText ?? '', status: p.querySelector('.live-status')?.textContent ?? '', hint: p.querySelector('.hint')?.textContent ?? '' }; })()`);
  const lastMessage = () => evaluate(`(() => { const all = [...document.querySelectorAll('.chat .msg')]; const m = all[all.length - 1];
    const folds = [...m.querySelectorAll('details.thought')].map(d => ({ label: d.querySelector('summary').textContent, open: d.open, text: d.querySelector('.thought-text').textContent }));
    return { cls: m.className, text: m.querySelector(':scope > .text').innerText, folds, items: m.querySelectorAll(':scope > .text li').length }; })()`);

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  if (!LIVE) await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/agent/propose', requestStage: 'Request' }, { urlPattern: '*/api/agent/cancel', requestStage: 'Request' }] });
  if (CODEX) {                                                        // scratch backend only (see the header)
    const saved = await (await fetch(`${APP}api/agent/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: 'codex' }) })).json();
    if (!saved.saved) throw new Error(`provider codex could not be selected: ${JSON.stringify(saved)}`);
  }
  const starter = await (await fetch(`${APP}api/tasks/starter?task_key=synthetic:opamp`)).json();
  const seeded = { schema_version: 'gator-workbench-config-v1', ...(starter.config ?? starter), output: { experiment_name: 'experiment' }, research: {} };
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(seeded))});` });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!document.querySelector('.tabs button')`)); i++) await sleep(100);
  await sleep(1200);
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Agent').click()`); await sleep(500);
  const provider = await evaluate(`document.querySelector('.agent-side select').value`);
  if (provider === 'disabled') throw new Error('the agent provider is "disabled" on this backend: nothing could be sent');

  if (!LIVE) {
    // ---- an answer that arrives as events ---------------------------------------------------------------------------
    await ask('Set the gain target to 60 dB (from my spec sheet).');
    const first = await nextPaused('/api/agent/propose');
    check('the page asks for a live answer (Accept: text/event-stream)', Object.entries(first.headers).some(([k, v]) => k.toLowerCase() === 'accept' && v.includes('text/event-stream')));
    await sleep(1200);
    const waiting = await pendingView();
    check('the waiting line counts and promises no time limit', /Sent\. Waiting for the agent's reply\.\.\. [1-3] s/.test(waiting?.status ?? '') && waiting.hint.includes('No time limit') && !/stopped after|in one piece/.test(waiting.hint), JSON.stringify(waiting));
    const THINK = '**Weighing the gain target**\n\nThe spec sheet gives 60 dB; the baseline is 58.2 dB, so the target is close.';
    const REPLY = 'I set the gain target from your spec sheet.\n\n- `gain` target: **60 dB**\n- power: unchanged';
    await fulfil(first.requestId, 200, 'text/event-stream', sse([['progress', { type: 'model', model: 'fixture-live-model' }], ['progress', { type: 'thinking', text: '' }],
      ...THINK.match(/.{1,17}/gs).map(t => ['progress', { type: 'thinking', text: t }]), ['progress', { type: 'writing', field: 'kind' }], ['progress', { type: 'writing', field: 'reasoning' }],
      ...REPLY.match(/.{1,9}/gs).map(t => ['progress', { type: 'reply', text: t }]), ['progress', { type: 'writing', field: 'patch' }],
      ['result', { proposal_id: 'fixture-live-1', proposal_hash: 'fixture', origin: 'fixture', kind: 'targets', reasoning: REPLY, warnings: ['The 60 dB target is close to the baseline.'], unresolved: [], diff: [], circuit_changes: [] }]]));
    await sleep(700);
    let last = await lastMessage();
    check('the reply is in the chat, formatted', last.cls.includes('reply') && last.text.startsWith('I set the gain target') && last.items === 2, JSON.stringify(last).slice(0, 160));
    check('its thinking is kept with it, folded into one closed line', last.folds.length === 1 && !last.folds[0].open && /^Thinking( - \d+ s)?$/.test(last.folds[0].label)
      && last.folds[0].text.includes('The spec sheet gives 60 dB') && !last.folds[0].text.includes('**'), JSON.stringify(last.folds));
    check('the waiting bubble is gone', (await pendingView()) === null);
    check('the side window lists the reply\'s warning', (await evaluate(`document.querySelector('.notes').innerText`)).includes('Warnings (1)'));
    await shot('live-1-reply.png');
    await evaluate(`document.querySelector('.chat .msg:last-child details.thought summary').click()`); await sleep(200);
    check('one click opens the thinking', (await lastMessage()).folds[0].open);

    // ---- an error after some thinking ---------------------------------------------------------------------------------
    await ask('Try again.');
    const second = await nextPaused('/api/agent/propose');
    await fulfil(second.requestId, 200, 'text/event-stream', sse([['progress', { type: 'thinking', text: 'Checking the rows against the schema.' }],
      ['error', { code: 'schema_failure', meaning: 'The structured output did not satisfy the schema.', detail: '1 problem in the structured output', problems: ['`patch` must be a list'], configuration_unchanged: true }]]));
    await sleep(600);
    last = await lastMessage();
    check('an error event reads like the plain 409 did', last.cls.includes('error') && last.text.startsWith('schema_failure: 1 problem in the structured output (your configuration is unchanged)'), last.text.slice(0, 100));
    check('... and keeps the thinking that led to it, folded', last.folds.length === 1 && !last.folds[0].open && last.folds[0].text.includes('Checking the rows'));
    check('... and its problems still go to the side window', (await evaluate(`document.querySelector('.notes').innerText`)).includes('Problems (1)'));
    check('the text returns to the message box after an error', (await evaluate(`${BOX}.value`)) === 'Try again.');

    // ---- an older server answers with one JSON body -------------------------------------------------------------------
    await evaluate(`${BOX}.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))`);
    const third = await nextPaused('/api/agent/propose');
    await fulfil(third.requestId, 200, 'application/json', JSON.stringify({ proposal_id: 'fixture-live-2', proposal_hash: 'fixture', origin: 'fixture', kind: 'targets',
      reasoning: 'Answered in one piece by an older server.', warnings: [], unresolved: [], diff: [], circuit_changes: [] }));
    await sleep(500);
    last = await lastMessage();
    check('a plain JSON answer (a server not restarted yet) is still shown', last.text === 'Answered in one piece by an older server.' && last.folds.length === 0, last.text);

    // ---- a stream that ends without a verdict (the server went away) ---------------------------------------------------
    await ask('One more.');
    const fourth = await nextPaused('/api/agent/propose');
    await fulfil(fourth.requestId, 200, 'text/event-stream', sse([['progress', { type: 'thinking', text: 'Halfway through.' }]]));
    await sleep(600);
    last = await lastMessage();
    check('a stream cut off before its verdict ends the wait with an error line', last.cls.includes('error') && last.text.includes('closed before the answer was complete') && (await pendingView()) === null, last.text.slice(0, 120));
  } else {
    // ---- a real stream from the scratch backend -----------------------------------------------------------------------
    const settings = await (await fetch(`${APP}api/agent/settings`)).json();
    check('the backend reports no time limit', settings.timeout_seconds === null, String(settings.timeout_seconds));
    const tag = CODEX ? 'codex-' : '';
    check(`the page sends to ${CODEX ? 'codex' : 'claude_code'}`, provider === (CODEX ? 'codex' : 'claude_code'), provider);
    await ask('Keep the score target where it is.');
    const samples = [];
    for (let i = 0; i < 120; i++) {
      const view = await pendingView();
      if (!view) break;
      samples.push({ t: i * 250, ...view, thinking: view.thinking.length, reply: view.reply.length });
      if (i === 8) await shot(`live-${tag}2-thinking.png`);
      await sleep(250);
    }
    const thinkingGrew = new Set(samples.map(s => s.thinking).filter(n => n > 0)).size;
    const replyGrew = new Set(samples.map(s => s.reply).filter(n => n > 0)).size;
    console.log('samples', JSON.stringify(samples.map(s => [s.t, s.thinking, s.reply, s.status.replace(/\s+\d+ s$/, '')])));
    check('the thinking appears while the agent works, and grows', thinkingGrew >= 2, `${thinkingGrew} different lengths`);
    if (CODEX) {                                                      // whole items: steps, and the reply in one piece
      check('Codex: its command and its web search show as steps while it works', samples.some(s => s.steps.includes('Running: ls') && s.steps.includes('Searching the web: SAC analog circuit sizing')), JSON.stringify(samples.at(-1)?.steps));
      check('Codex: the waiting line says thinking, then looking things up', samples.some(s => s.status.startsWith('Thinking...')) && samples.some(s => s.status.startsWith('Looking things up...')));
    } else {
      check('the waiting line says what is happening: thinking, then writing the reply', samples.some(s => s.status.startsWith('Thinking...')) && samples.some(s => s.status.startsWith('Writing the reply...')));
      check('the reply grows in the bubble before the answer is complete', replyGrew >= 3, `${replyGrew} different lengths`);
      check('the bubble names the model the CLI runs', samples.some(s => s.who.includes('fake-live-model')));
    }
    check('the hint promises no time limit', samples.every(s => s.hint.includes('No time limit')));
    const last = await lastMessage();
    check('the finished reply replaces the bubble', last.cls.includes('reply') && last.text.startsWith('Your configuration already has what you asked for') && last.items === 2, last.text.slice(0, 80));
    check('the thinking stays with it, folded', last.folds.length === 1 && !last.folds[0].open && last.folds[0].text.includes('The user gives 0.97'), JSON.stringify(last.folds).slice(0, 160));
    await shot(`live-${tag}3-reply.png`);

    // ---- "Cancel request" in the middle keeps what had arrived ----------------------------------------------------------
    await ask('Think about this forever FAKE-HANG');
    for (let i = 0; i < 40 && !((await pendingView())?.thinking); i++) await sleep(250);
    await sleep(600);
    await evaluate(`[...document.querySelectorAll('.compose-main button')].find(b => b.textContent === 'Cancel request').click()`);
    let cancelled = null;
    for (let i = 0; i < 40 && !cancelled; i++) { await sleep(250); const m = await lastMessage(); if (m.cls.includes('system') && m.text.includes('Cancelled by you')) cancelled = m; }
    check('the cancel is a plain line', !!cancelled && /^Cancelled by you after \d+ s\./.test(cancelled.text), cancelled?.text.slice(0, 80));
    check('... with the thinking that had arrived, folded under it', !!cancelled && cancelled.folds.length === 1 && !cancelled.folds[0].open && cancelled.folds[0].text.includes('The user gives 0.97'));
    check('the text returns to the message box', (await evaluate(`${BOX}.value`)) === 'Think about this forever FAKE-HANG');
    await shot(`live-${tag}4-cancelled.png`);
  }
  check('no page errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  failures++;
  console.log(`ERROR ${error.stack ?? error}`);
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 400 }); } catch { /* left behind */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
