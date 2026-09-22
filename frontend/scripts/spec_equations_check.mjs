// Browser check of "each spec is an equation over the probes" (status record 7.52): the Specs tab edits `equation`, an
// older saved Specs row (one probe in `measurement_id`) is read as its equation, and what is typed is judged by the REAL
// backend's validation. Same approach as task_rows_check.mjs: a throwaway headless Edge over the DevTools protocol.
// Requests: GET, POST /api/circuit/load and POST /api/config/validate pass through (read-only: local files, no bridge, no
// simulation), every other writing request is refused here - so it is safe on any backend, but it needs one that KNOWS
// equations (restarted after 7.52, or a scratch one).
// The browser profile is new and temporary: the user's saved configuration is not touched.
// Run (Windows node through WSL interop; node >= 22):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/spec_equations_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9397, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
const out = process.argv[2] ?? tmpdir();
mkdirSync(out, { recursive: true });
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-specs-'));
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
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const refused = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (request.method === 'GET' || name === '/api/config/validate' || name === '/api/circuit/load') return send('Fetch.continueRequest', { requestId });
    if (name !== '/api/output/check') refused.push(`${request.method} ${name}`);            // the output-folder look-up: refused, harmless
    return send('Fetch.fulfillRequest', { requestId, responseCode: 418, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
      body: Buffer.from(JSON.stringify({ detail: { message: 'FIXTURE: this check lets no writing request through' } })).toString('base64') });
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
  const until = async (expression, tries = 100) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const EDITORS = `document.querySelector('.editors')`;
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith(${JSON.stringify(name)})).click()`);
  const headers = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim())`);
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim()).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const cell = (row, name) => evaluate(`${CELL(row, name)}.value`);
  const type = (row, name, v) => evaluate(`(() => { const i = ${CELL(row, name)}; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, ${JSON.stringify(v)});
    i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  const issues = row => evaluate(`[...${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].querySelectorAll('td.issues .issue')].map(d => d.textContent.trim())`);
  const issuesUntil = async (row, wanted, absent = []) => {
    for (let i = 0; i < 60; i++) {
      const found = await issues(row);
      if (wanted.every(w => found.includes(w)) && absent.every(a => !found.some(f => f.includes(a)))) return [true, found];
      await sleep(150);
    }
    return [false, await issues(row)];
  };
  const shot = async name => { const { data } = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(path.join(out, name), Buffer.from(data, 'base64')); };

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  // The page opens as a browser that saved its configuration BEFORE specs had equations: one probe in `measurement_id`.
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const legacy = starter.targets.map(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k === 'equation' ? 'measurement_id' : k, v])));
  check('the backend knows equations (restarted after 7.52)', starter.targets[0]?.equation === 'm_score', JSON.stringify(starter.targets[0]));
  const SEED = { schema_version: 'gator-workbench-config-v1', ...starter, targets: legacy,
    run: { mode: 'scratch', concurrency: 1, threads_per_job: 1, ...starter.run }, output: { experiment_name: 'fixture' }, research: {} };
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (!localStorage.getItem('gator-workbench-config-v1')) localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(SEED))});` });
  await send('Page.navigate', { url: APP });
  check('the page opens', await until(`!!${EDITORS}`));
  await openTab('Specs');
  check('the Specs tab edits an equation, right after the spec name', JSON.stringify((await headers()).slice(1, 3)) === '["metric_id","equation"]', JSON.stringify(await headers()));
  check('an older saved row shows its probe as the equation', await until(`${CELL(0, 'equation')}?.value === 'm_score'`), await cell(0, 'equation'));
  const saved = await evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1200))`);
  check('...and is saved back in the new form, in the same place', JSON.stringify(Object.keys(saved.targets[0]).slice(0, 2)) === '["metric_id","equation"]'
    && !('measurement_id' in saved.targets[0]), JSON.stringify(saved.targets[0]));
  check('the old row is valid as it is', (await issuesUntil(0, [], ['error', 'blocker']))[0], JSON.stringify(await issues(0)));
  check('the tab names the probes an equation can use', /Probes: m_score\./.test(await evaluate(`${EDITORS}.querySelector('.spec-probes')?.textContent ?? ''`)));

  // a formula: its own name, a unit that cannot be checked, a new entry in the network's result registry
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Add').click()`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 2`);
  // "Add" used to give a required field the schema's `default: null` (constraint, normalization_scale): the row was invalid
  const added = (await evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1000))`)).targets[1];
  check('a new spec row starts complete: the first probe as its equation, in its unit, a constraint, a scale',
    added?.equation === 'm_score' && added?.unit === 'fixture' && added?.constraint === '>=' && added?.normalization_scale === 1, JSON.stringify(added));
  await type(1, 'metric_id', 'score_sq'); await type(1, 'equation', 'm_score ** 2'); await type(1, 'unit', 'fixture'); await type(1, 'lower', '0.5');
  let [ok, found] = await issuesUntil(1, ['warning: equation_unit_unchecked', 'info: spec_adds_registry_entry'], ['error', 'blocker']);
  const row = async () => JSON.stringify((await evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1000))`)).targets[1])
    + ' | page issues: ' + JSON.stringify(await evaluate(`[...document.querySelectorAll('.editors .issue')].map(d => d.textContent.trim())`));
  check('a formula is accepted: its unit is not checkable, its name is new to the registry', ok, JSON.stringify(found) + (ok ? '' : ' ' + await row()));
  await shot('spec_equation_formula.png');
  await type(1, 'equation', 'm_nope * 2');
  [ok, found] = await issuesUntil(1, ['error: equation_unknown_probe']);
  check('a probe that does not exist is named as an error', ok, JSON.stringify(found));
  await type(1, 'equation', 'abs(m_score)');
  [ok, found] = await issuesUntil(1, ['error: equation_rejected']);
  check('a function call is refused, not evaluated', ok, JSON.stringify(found));
  await type(1, 'metric_id', 'm_score'); await type(1, 'equation', 'm_score * 2');
  [ok, found] = await issuesUntil(1, ['error: spec_name_is_a_probe']);
  check('a formula may not take the name of a probe', ok, JSON.stringify(found));
  await type(1, 'metric_id', 'score'); await type(0, 'metric_id', 'score_plain');
  [ok, found] = await issuesUntil(1, ['error: spec_name_is_a_result']);
  check('a formula may not take the name of a simulator result', ok, JSON.stringify(found));

  check('the page sent no writing request but validations', refused.length === 0, JSON.stringify(refused));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | '));
  ws.close();
} catch (e) {
  failures++;
  console.log(`FAIL  the check itself failed: ${e.message}`);
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file */ }
}
console.log(failures ? `${failures} check(s) FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);
