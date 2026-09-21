// Browser check of the saved-model chooser in the run panel ("RL model to load"; there is no frontend test runner here).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against a RUNNING
// workbench (default http://127.0.0.1:8765/). The chooser's two routes (/api/runs/models, /api/runs/model), the default
// model and the validation are answered with canned data labelled FIXTURE, so the shown models are known. GET requests
// pass through; every other writing request is refused here, so this check can start, save or probe nothing on the
// backend it runs against. The browser profile is new and temporary: the user's saved configuration is not touched.
// What it pins (user request 2026-09-21, "can you choose which model to load?" / "what is a source run"):
// nothing is read while Mode is scratch; one card per run that holds a model, in plain words; MOCK / other network /
// weights only tags; choosing a card selects its LATEST save; every save point can be chosen and is the one the backend
// is asked about; a best policy is offered only where one exists; a stale selection is said and can be cleared; the
// filter; one request per "Refresh list" and no timer; the cards fit the narrow panel.
// Last section, against the REAL route of the backend it runs on: the cards equal GET /api/runs/models (skipped with a
// note when that backend is older than the route and has to be restarted).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/model_chooser_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9387, APP = process.env.GATOR_WORKBENCH_URL ?? 'http://127.0.0.1:8765/';
// Optional: the output folder whose saved models the last section lists (default: the backend's own default root).
// From WSL both variables need WSLENV=GATOR_WORKBENCH_URL:GATOR_WORKBENCH_OUTPUT_ROOT to reach the Windows process.
const ROOT = process.env.GATOR_WORKBENCH_OUTPUT_ROOT || undefined;
const out = process.argv[2] ?? tmpdir();
const profile = mkdtempSync(path.join(tmpdir(), 'gator-cdp-models-'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--window-size=1680,1050', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, info = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`); };

// ---- canned answers ------------------------------------------------------------------------------------------
const NET = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 1 }, GAT = { ...NET, encoder_type: 'gat' };
const point = (tag, evaluations, kind, minute, extra = {}) => ({ checkpoint_id: `ckpt-${String(evaluations).padStart(8, '0')}-${tag}`, kind,
  created_utc: `2026-09-21T10:${String(minute).padStart(2, '0')}:00+00:00`, mode: 'scratch', evaluations, learner_updates: Math.max(0, evaluations - 4),
  replay_size: evaluations, restoration_capability: 'full_state', missing_components: [], network: NET, is_latest: false, is_best_policy: false, ...extra });
const model = (name, circuit, points, extra = {}) => { const newest = points.find(p => p.is_latest) ?? points[points.length - 1]; return {
  run_dir: `/fixture/outputs/mock/fx__1/runs/${name}/scratch_seed1__r1`, run_id: `run-${name}`, task_id: `${name}:0123456789abcdef`, task_name: name,
  task_definition_hash: 'f'.repeat(64), mode: 'scratch', mock: true, seed: 1, created_utc: '2026-09-21T10:00:00+00:00', state: 'completed',
  experiment: 'fx__1', evaluations: newest.evaluations, circuit_task: circuit, circuit_class: circuit.split(':')[1], latest: newest.checkpoint_id,
  best_policy: { selected: points.find(p => p.is_best_policy)?.checkpoint_id ?? null, status: points.some(p => p.is_best_policy) ? 'selected' : 'not_selected',
    reason: points.some(p => p.is_best_policy) ? null : 'FIXTURE: no validation-set policy evaluation has occurred in this run', score: null },
  checkpoints: points, network: newest.network, saved_utc: newest.created_utc, trained_evaluations: newest.evaluations,
  learner_updates: newest.learner_updates, restoration_capability: newest.restoration_capability, ...extra }; };
const A = model('FIXTURE_opamp_gt', 'synthetic:opamp', [point('a1', 6, 'periodic', 1), point('a2', 12, 'periodic', 2), point('a3', 18, 'periodic', 3), point('a4', 20, 'final', 4, { is_latest: true })]);
const B = model('FIXTURE_ldo_gat', 'synthetic:ldo', [point('b1', 8, 'stop', 5, { is_latest: true, network: GAT })]);
const C = model('FIXTURE_weights_only', 'synthetic:vco', [point('c1', 10, 'pause', 6, { is_latest: true, restoration_capability: 'weights_only', missing_components: ['replay_snapshot (disabled in output settings)'] })]);
const D = model('FIXTURE_real_ota5', 'real:gpdk045_ota5', [point('d1', 30, 'periodic', 7, { is_best_policy: true }), point('d2', 40, 'final', 8, { is_latest: true })], { mock: false });
const FILLERS = ['e', 'f', 'g'].map((t, n) => model(`FIXTURE_filler_${t}`, 'synthetic:opamp', [point(`${t}1`, 5 + n, 'final', 9 + n, { is_latest: true })]));
const MODELS = [A, B, C, D, ...FILLERS].sort((x, y) => (x.saved_utc < y.saved_utc ? 1 : -1));            // newest save first, as the backend sends it
const describe = (run_dir, checkpoint_id) => {
  const m = MODELS.find(x => x.run_dir === run_dir); if (!m) return null;
  const p = checkpoint_id === 'latest' ? m.checkpoints.find(x => x.is_latest) : checkpoint_id === 'best_policy' ? m.checkpoints.find(x => x.is_best_policy) : m.checkpoints.find(x => x.checkpoint_id === checkpoint_id);
  if (!p) return null;
  return { description: { checkpoint_id: p.checkpoint_id, path: `${run_dir}/checkpoints/${p.checkpoint_id}`, kind: p.kind, source_run_id: m.run_id, source_task_id: m.task_id, mode: p.mode,
    created_utc: p.created_utc, metadata_version: 'FIXTURE', counters: { evaluations_committed: p.evaluations, learner_updates: p.learner_updates, replay_size: p.replay_size },
    restoration_capability: p.restoration_capability, restorable_components: [], missing_components: p.missing_components, contract: { model_config: p.network, sac_config: {} }, file_problems: [] },
    compatibility: { mode: 'fine_tune', compatible: true, checks: [{ component: 'FIXTURE check', status: 'ok', detail: 'identical' }], checkpoint_id: p.checkpoint_id, source_run_id: m.run_id,
      restoration_capability: p.restoration_capability, suggestion: null }, suggestion: null };
};
const VALID = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:opamp', APP))).json();
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'scratch', network: NET }, output: { experiment_name: 'fixture', ...(ROOT ? { output_root: ROOT } : {}) }, research: {} };
  let target;
  for (let i = 0; i < 75 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* not up yet */ }
    if (!target) await sleep(200);
  }
  if (!target) throw new Error('Edge did not open a debugging port');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0; const pending = new Map(); const consoleErrors = []; const refused = []; const asked = []; let lists = 0, canned = true, served = MODELS;
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const fulfil = (requestId, status, obj) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(obj)).toString('base64') });
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') { lists++; return canned ? fulfil(requestId, 200, { models: served }) : send('Fetch.continueRequest', { requestId }); }
    if (name === '/api/runs/model') {
      const body = JSON.parse(request.postData ?? '{}'); asked.push({ run_dir: body.run_dir, checkpoint_id: body.checkpoint_id });
      const found = describe(body.run_dir, body.checkpoint_id);
      return found ? fulfil(requestId, 200, found) : fulfil(requestId, 404, { detail: { message: 'FIXTURE: no such checkpoint' } });
    }
    if (request.method === 'GET') return send('Fetch.continueRequest', { requestId });
    refused.push(`${request.method} ${name}`);
    return fulfil(requestId, 418, { detail: { message: 'FIXTURE: this check lets no writing request through' } });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
    else if (m.method === 'Fetch.requestPaused') answer(m.params).catch(() => { /* the page went away */ });
    else if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
  };
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const until = async (expression, tries = 60) => { for (let i = 0; i < tries; i++) { if (await evaluate(expression)) return true; await sleep(100); } return false; };
  const RIGHT = `document.querySelector('.right')`;
  const labelled = text => `[...(${RIGHT}?.querySelectorAll('label') ?? [])].find(l => l.firstChild?.textContent?.trim() === ${JSON.stringify(text)})?.querySelector('select')`;
  const setSelect = (expression, value) => evaluate(`(() => { const s = ${expression}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)});
    s.dispatchEvent(new Event('change', { bubbles: true })); return s.value; })()`);
  const cards = () => evaluate(`[...${RIGHT}.querySelectorAll('button.model-card')].map(b => ({ title: b.querySelector('.model-title b')?.textContent, tags: [...b.querySelectorAll('.model-tag')].map(t => t.textContent),
    lines: [...b.children].slice(1).map(s => s.textContent), active: b.getAttribute('aria-checked') === 'true', fits: b.scrollWidth <= b.clientWidth + 1 }))`);
  const card = name => `[...${RIGHT}.querySelectorAll('button.model-card')].find(b => b.querySelector('.model-title b')?.textContent === ${JSON.stringify(name)})`;
  const button = text => `[...${RIGHT}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const options = () => evaluate(`[...(${RIGHT}.querySelector('select.model-point')?.options ?? [])].map(o => ({ value: o.value, text: o.textContent }))`);
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')?.run?.model_source ?? null`);
  const blockText = () => evaluate(`(() => { const h = [...${RIGHT}.querySelectorAll('h3')].find(x => x.textContent === 'RL model to load'); let t = '', n = h?.nextElementSibling;
    while (n && n.tagName !== 'H3' && n.tagName !== 'DETAILS') { t += ' ' + n.innerText; n = n.nextElementSibling; } return t; })()`);
  const lastAsked = () => asked[asked.length - 1] ?? {};
  const shot = async name => {
    const clip = await evaluate(`(() => { const r = ${RIGHT}.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: Math.min(1050, r.height), scale: 1.5 }; })()`);
    const { data } = await send('Page.captureScreenshot', { format: 'png', clip });
    writeFileSync(path.join(out, name), Buffer.from(data, 'base64'));
  };
  const reveal = expression => evaluate(`${expression}?.scrollIntoView({ block: 'center' })`);

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))}); }` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${labelled('Mode')})`, 150))) throw new Error('the run panel never appeared; the page reads: '
    + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  if (!(await until(`[...${RIGHT}.querySelectorAll('h3')].some(h => h.textContent === 'RL model to load')`, 50)))
    throw new Error('this page has no "RL model to load" block: the served frontend is older than the chooser (npm run build, then reload)');

  // ---- scratch: said in plain words, and nothing is read ---------------------------------------------------------
  await sleep(600);
  const none = await blockText();
  check('in scratch mode the block says that no model is loaded, and how to load one', /None\. Mode is scratch/.test(none) && /fine_tune/.test(none) && /frozen/.test(none) && /resume/.test(none), none.slice(0, 120));
  check('in scratch mode the list of saved models is not read', lists === 0, `${lists} request(s)`);
  check('the old "Source run" / "Checkpoint" pickers are gone', !(await evaluate(`!!(${labelled('Source run')}) || !!(${labelled('Checkpoint')})`)));

  // ---- a mode that loads a model: one card per run that holds one ---------------------------------------------------
  await setSelect(labelled('Mode'), 'fine_tune');
  check('choosing fine_tune reads the list once', (await until(`${RIGHT}.querySelectorAll('button.model-card').length > 0`, 50)) && lists === 1, `${lists} request(s)`);
  let shown = await cards();
  check('one card per saved model, most recently saved first', shown.length === MODELS.length && shown.map(c => c.title).join() === MODELS.map(m => m.task_name).join(), shown.map(c => c.title).join());
  check('the block explains what a run and a saved model are', /A run is one training session \(one press of Start\)/.test(await blockText()));
  check('the count is said', /7 saved models under the output folder/.test(await blockText()));
  const byName = name => shown.find(c => c.title === name);
  check('a card names the circuit, the network, the training and the saves in plain words',
    byName(A.task_name).lines[0] === 'synthetic:opamp - graph_transformer 16/2/1' && byName(A.task_name).lines[1] === '20 evaluations of training - 4 save points'
    && /^last saved .+ - run completed \(scratch, seed 1\)$/.test(byName(A.task_name).lines[2]), JSON.stringify(byName(A.task_name).lines));
  check('one save point is singular', byName(B.task_name).lines[1] === '8 evaluations of training - 1 save point', byName(B.task_name).lines[1]);
  check('MOCK models are tagged, the real one is not', byName(A.task_name).tags.includes('MOCK') && !byName(D.task_name).tags.includes('MOCK'), JSON.stringify([byName(A.task_name).tags, byName(D.task_name).tags]));
  check('a model trained with another network is tagged "other network", a matching one is not', byName(B.task_name).tags.includes('other network') && !byName(A.task_name).tags.includes('other network'));
  check('a model saved without its replay is tagged "weights only"', byName(C.task_name).tags.includes('weights only') && !byName(A.task_name).tags.includes('weights only'));
  check('no card is selected yet and no save point is offered', shown.every(c => !c.active) && (await options()).length === 0);
  check('every card fits the narrow panel (text wraps, nothing is cut off)', shown.every(c => c.fits) && !(await evaluate(`${RIGHT}.scrollWidth > ${RIGHT}.clientWidth + 1`)), JSON.stringify(shown.filter(c => !c.fits).map(c => c.title)));
  await reveal(card(A.task_name)); await shot('models-1-list.png');

  // ---- choosing a model = its latest save; then any save point -----------------------------------------------------------
  await evaluate(`${card(A.task_name)}.click()`);
  check('a click selects the card', await until(`${card(A.task_name)}.getAttribute('aria-checked') === 'true'`, 30));
  check('the backend is asked about that run\'s LATEST save', (await until(`true`, 1)) && await (async () => { for (let i = 0; i < 40 && lastAsked().run_dir !== A.run_dir; i++) await sleep(100); return lastAsked().run_dir === A.run_dir && lastAsked().checkpoint_id === 'latest'; })(), JSON.stringify(lastAsked()));
  let offered = await options();
  check('every save point is offered: latest first, then newest to oldest', offered.length === 5 && offered[0].value === 'latest'
    && offered.slice(1).map(o => o.value).join() === [...A.checkpoints].reverse().map(p => p.checkpoint_id).join(), JSON.stringify(offered.map(o => o.value)));
  check('a save point reads as training amount, time and kind', /^Latest save \(default\): 20 evaluations - .+ - saved at the end of the run$/.test(offered[0].text)
    && /^6 evaluations - .+ - automatic save$/.test(offered[4].text), JSON.stringify([offered[0].text, offered[4].text]));
  check('no "best policy" is offered where none was selected', !offered.some(o => o.value === 'best_policy'));
  check('the chosen model is described below (its evaluations)', await until(`/20 evaluations, 16 updates/.test(${RIGHT}.innerText) && /Trained on/.test(${RIGHT}.innerText)`, 40));
  const early = A.checkpoints[0].checkpoint_id;
  await setSelect(`${RIGHT}.querySelector('select.model-point')`, early);
  check('choosing the OLDEST save point asks the backend about exactly that one', await (async () => { for (let i = 0; i < 40 && lastAsked().checkpoint_id !== early; i++) await sleep(100); return lastAsked().run_dir === A.run_dir && lastAsked().checkpoint_id === early; })(), JSON.stringify(lastAsked()));
  check('... and its own numbers are shown (6 evaluations, not 20)', await until(`/6 evaluations, 2 updates/.test(${RIGHT}.innerText)`, 40));
  await sleep(1100);
  check('the choice is part of the configuration', JSON.stringify(await stored().then(s => [s?.run_dir, s?.checkpoint_id])) === JSON.stringify([A.run_dir, early]), JSON.stringify(await stored()));
  await reveal(`${RIGHT}.querySelector('select.model-point')`); await shot('models-2-save-point.png');
  await evaluate(`${card(A.task_name)}.click()`); await sleep(300);
  check('clicking the selected card again keeps the chosen save point', (await evaluate(`${RIGHT}.querySelector('select.model-point').value`)) === early);

  // ---- another model: back to ITS latest; the network warning of the run panel still works --------------------------------------
  await evaluate(`${card(B.task_name)}.click()`);
  check('choosing another model starts at its latest save', await (async () => { for (let i = 0; i < 40 && lastAsked().run_dir !== B.run_dir; i++) await sleep(100); return lastAsked().checkpoint_id === 'latest'; })()
    && (await evaluate(`${RIGHT}.querySelector('select.model-point').value`)) === 'latest', JSON.stringify(lastAsked()));
  check('the run panel warns that this model needs its own network', await until(`/This checkpoint was trained with gat/.test(${RIGHT}.innerText)`, 40));
  await evaluate(`${button("Use the checkpoint's network")}.click()`); await sleep(500);
  shown = await cards();
  check('after "Use the checkpoint\'s network" the tags follow: gat fits, graph_transformer is the other network',
    !shown.find(c => c.title === B.task_name).tags.includes('other network') && shown.find(c => c.title === A.task_name).tags.includes('other network'));

  // ---- a best policy only where one exists ---------------------------------------------------------------------------------------
  await evaluate(`${card(D.task_name)}.click()`); await until(`${card(D.task_name)}.getAttribute('aria-checked') === 'true'`, 30);
  offered = await options();
  check('a run with a selected best policy offers it, by name', offered[1]?.value === 'best_policy' && /^Best policy \(picked by a validation rule\): 30 evaluations/.test(offered[1].text), JSON.stringify(offered.map(o => o.value)));

  // ---- filter, refresh, no timer ---------------------------------------------------------------------------------------------------
  check('with more than 5 models a filter box is shown', await evaluate(`!!${RIGHT}.querySelector('input.model-filter')`));
  await evaluate(`${RIGHT}.querySelector('input.model-filter').focus()`); await send('Input.insertText', { text: 'ldo gat' }); await sleep(300);
  shown = await cards();
  check('the filter keeps the matching model and the selected one', shown.map(c => c.title).sort().join() === [B.task_name, D.task_name].sort().join(), shown.map(c => c.title).join());
  await evaluate(`(() => { const i = ${RIGHT}.querySelector('input.model-filter'); i.focus(); i.select(); })()`); await send('Input.insertText', { text: 'nothing-like-this' }); await sleep(300);
  check('a filter without a match still shows the selected model', (await cards()).map(c => c.title).join() === D.task_name);
  await evaluate(`(() => { const i = ${RIGHT}.querySelector('input.model-filter'); i.focus(); i.select(); })()`); await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 }); await sleep(300);
  check('clearing the filter shows all models again', (await cards()).length === MODELS.length);
  const before = lists; await sleep(2500);
  check('the list is not re-read on a timer', lists === before, `${lists - before} request(s) in 2.5 s`);
  served = MODELS.filter(m => m !== D);                                                       // the selected model's save points disappear
  await evaluate(`${button('Refresh list')}.click()`);
  check('"Refresh list" reads the list exactly once', (await until(`${RIGHT}.querySelectorAll('button.model-card').length === ${MODELS.length - 1}`, 40)) && lists === before + 1, `${lists - before} request(s)`);

  // ---- a selection that is no longer in the list ------------------------------------------------------------------------------------
  check('a selected model that left the list is said in plain words, with its folder', await until(`!!${RIGHT}.querySelector('.model-missing')`, 30)
    && (await evaluate(`${RIGHT}.querySelector('.model-missing').innerText`)).includes(D.run_dir));
  await reveal(`${RIGHT}.querySelector('.model-missing')`); await shot('models-3-missing.png');
  await evaluate(`${button('Clear the selection')}.click()`);
  check('"Clear the selection" removes it', await until(`!${RIGHT}.querySelector('.model-missing')`, 30) && (await cards()).every(c => !c.active));
  await sleep(1100);
  check('... also from the configuration', (await stored())?.run_dir === null, JSON.stringify(await stored()));

  // ---- an empty folder ------------------------------------------------------------------------------------------------------------
  served = []; await evaluate(`${button('Refresh list')}.click()`);
  check('no saved model: said in plain words, with what makes a run save one', await until(`!!${RIGHT}.querySelector('.model-empty')`, 40)
    && /No saved model yet/.test(await evaluate(`${RIGHT}.querySelector('.model-empty').innerText`)));

  // ---- back to scratch ------------------------------------------------------------------------------------------------------------
  const beforeScratch = lists;
  await setSelect(labelled('Mode'), 'scratch'); await sleep(500);
  check('back in scratch the chooser closes and reads nothing', /None\. Mode is scratch/.test(await blockText()) && lists === beforeScratch);

  // ---- the REAL route of this backend -------------------------------------------------------------------------------------------------
  const real = await fetch(new URL('api/runs/models' + (ROOT ? `?output_root=${encodeURIComponent(ROOT)}` : ''), APP));
  if (real.status === 404) console.log('SKIP  the real /api/runs/models route: this backend is older than the chooser - restart it (the page then shows its own saved models)');
  else {
    const expected = (await real.json()).models;
    canned = false; await setSelect(labelled('Mode'), 'frozen');
    const ok = await until(`${RIGHT}.querySelectorAll('button.model-card').length === ${expected.length} && !/Reading the saved models/.test(${RIGHT}.innerText)`, 80);
    check(`against the real route: ${expected.length} saved model(s) on this backend, ${expected.length} card(s)`, ok, `${(await cards()).length} card(s)`);
    check('... each card carries its run folder', (await evaluate(`[...${RIGHT}.querySelectorAll('button.model-card')].map(b => b.title)`)).join() === expected.map(m => m.run_dir).join());
    await shot('models-4-real.png');
  }

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect, save settings or call an agent on its own: never',
    !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/|network-settings)/.test(r)), refused.join(', '));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
  console.log(failures ? `\n${failures} check(s) FAILED` : '\nall checks passed');
  ws.close();
} catch (error) {
  failures++; console.log(`FAIL  the check could not run: ${error.message}`);
} finally {
  edge.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold a file; it is a temp dir */ }
}
process.exit(failures ? 1 : 0);
