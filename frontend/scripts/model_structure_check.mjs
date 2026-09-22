// Browser check of the "Network structure" fold-out under "RL model to load" and its full layer table (a dialog).
// Same approach as model_chooser_check.mjs: a throwaway headless Edge over the DevTools protocol against a RUNNING
// workbench (default http://127.0.0.1:8765/). The chooser's routes and /api/runs/model/structure are answered with canned
// data labelled FIXTURE, so the shown numbers are known. GET requests pass through; every other writing request is
// refused here, so this check can start, save or probe nothing on the backend it runs against.
// What it pins (user request 2026-09-21, "build the structure table"): nothing is read until the fold-out is opened; the
// request names the RESOLVED save point; the summary says trained / actor / critics / target copies in plain words; the
// never-used weights are said only when there are some; section tables fit the narrow panel; "Full layer table" opens a
// WIDE dialog with every layer (type, shape, parameters, share, what it does), the never-used row marked, a total row;
// another save point re-reads it; types that could not be verified are not shown; an error is said; TABLES ONLY - no
// canvas, svg or image anywhere in it.
// Last section, against the REAL routes of the backend it runs on (skipped with a note when it has no saved model or is
// older than the route): the page's numbers equal POST /api/runs/model/structure for the first real model.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/model_structure_check.mjs)" [screenshot-dir]
// Optional: GATOR_WORKBENCH_OUTPUT_ROOT = the output folder whose real models the last section uses
// (from WSL: WSLENV=GATOR_WORKBENCH_URL:GATOR_WORKBENCH_OUTPUT_ROOT). Exit code 1 if any check fails.
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const ROOT = process.env.GATOR_WORKBENCH_OUTPUT_ROOT || undefined;
const out = outDir();
const browser = await launchEdge('structure');

// ---- canned answers ------------------------------------------------------------------------------------------
const NET = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 1 };
const RUN = '/fixture/outputs/mock/fx__1/runs/FIXTURE_structure/scratch_seed1__r1';
const point = (tag, evaluations, kind, latest) => ({ checkpoint_id: `ckpt-${String(evaluations).padStart(8, '0')}-${tag}`, kind, created_utc: `2026-09-21T10:0${evaluations % 10}:00+00:00`, mode: 'scratch',
  evaluations, learner_updates: evaluations - 4, replay_size: evaluations, restoration_capability: 'full_state', missing_components: [], network: NET, is_latest: latest, is_best_policy: false });
const POINTS = [point('early', 6, 'periodic', false), point('final', 20, 'final', true)];
const MODEL = { run_dir: RUN, run_id: 'run-fx', task_id: 'FIXTURE_structure:0123456789abcdef', task_name: 'FIXTURE_structure', task_definition_hash: 'f'.repeat(64), mode: 'scratch', mock: true, seed: 1,
  created_utc: '2026-09-21T10:00:00+00:00', state: 'completed', experiment: 'fx__1', evaluations: 20, circuit_task: 'synthetic:gpdk045_ota5', circuit_class: 'opamp', latest: POINTS[1].checkpoint_id,
  best_policy: { selected: null, status: 'not_selected', reason: 'FIXTURE', score: null }, checkpoints: POINTS, network: NET, saved_utc: POINTS[1].created_utc, trained_evaluations: 20,
  learner_updates: 16, restoration_capability: 'full_state' };
const resolve = id => id === 'latest' ? POINTS[1] : POINTS.find(p => p.checkpoint_id === id);
const describe = id => { const p = resolve(id); return p && { description: { checkpoint_id: p.checkpoint_id, path: `${RUN}/checkpoints/${p.checkpoint_id}`, kind: p.kind, source_run_id: 'run-fx',
  source_task_id: MODEL.task_id, mode: 'scratch', created_utc: p.created_utc, metadata_version: 'FIXTURE', counters: { evaluations_committed: p.evaluations, learner_updates: p.learner_updates, replay_size: p.replay_size },
  restoration_capability: 'full_state', restorable_components: [], missing_components: [], contract: { model_config: NET, sac_config: {} }, file_problems: [] },
  compatibility: { mode: 'fine_tune', compatible: true, checks: [{ component: 'FIXTURE check', status: 'ok', detail: 'identical' }], checkpoint_id: p.checkpoint_id, source_run_id: 'run-fx', restoration_capability: 'full_state', suggestion: null }, suggestion: null }; };
const layer = (section, name, type, shape, parameters, role, unused = false) => ({ path: name, section, role, type, shape, tensors: [], parameters, unused,
  note: unused ? 'FIXTURE: allocated by PyG, never read by this network.' : null });
const part = (key, title, about, layers) => { const total = layers.reduce((s, l) => s + l.parameters, 0); const sections = [];
  for (const l of layers) { let s = sections.find(x => x.section === l.section); if (!s) sections.push(s = { section: l.section, layers: 0, parameters: 0, unused: 0 }); s.layers++; s.parameters += l.parameters; if (l.unused) s.unused += l.parameters; }
  return { part: key, title, about, layers: layers.map(l => ({ ...l, share: l.parameters / total })), sections, parameters: total, unused_parameters: layers.filter(l => l.unused).reduce((s, l) => s + l.parameters, 0) }; };
const structure = (id, { typed = true, withUnused = true, scale = 1 } = {}) => {
  const t = name => typed ? name : null, shape = (a, b) => typed ? `${a} -> ${b}` : `${b}x${a}, ${b}`;
  const common = kind => [layer('Inputs', 'encoder.device_values', t('Linear'), shape(32, 16), 528 * scale, 'FIXTURE: device numbers into the hidden width.'),
    layer('Inputs', 'encoder.device_kind', t('Embedding'), typed ? '8 entries x 16' : '8x16', 128 * scale, 'FIXTURE: one learned vector per device kind.'),
    layer('Block 1', 'encoder.blocks.0.attention.lin_key', t('Linear'), shape(16, 16), 1272 * scale, 'FIXTURE: message passing along the connections.'),
    layer('Block 1', 'encoder.blocks.0.attention.lin_skip', t('Linear'), shape(16, 16), 272 * scale, "FIXTURE: skip path of PyG's TransformerConv.", typed && withUnused),
    layer('Read-out', 'encoder.group_head.0', t('Linear'), shape(48, 16), 784 * scale, 'FIXTURE: per parameter group.'),
    layer('Output', 'head.2', t('Linear'), kind === 'actor' ? shape(16, 2) : shape(16, 1), kind === 'actor' ? 34 : 17, kind === 'actor' ? 'FIXTURE: mean and spread of the action.' : 'FIXTURE: one Q-value.')];
  const actor = part('actor', 'Actor', 'FIXTURE: the policy.', common('actor')), critic = part('critic', 'Critic', 'FIXTURE: judges an action; 4 networks of this structure are saved.', common('critic'));
  const trained = actor.parameters + 2 * critic.parameters + 1;
  return { checkpoint_id: id, network: NET, types_verified: typed, types_problem: typed ? null : 'FIXTURE: the network could not be rebuilt from the recorded settings (KeyError).', parts: [actor, critic], critics_identical: true,
    totals: { trained, actor: actor.parameters, critic_each: critic.parameters, temperature: 1, target_copies: 2 * critic.parameters, saved: trained + 2 * critic.parameters,
      never_used: actor.unused_parameters + 2 * critic.unused_parameters, never_used_in_targets: 2 * critic.unused_parameters }, explanation: 'FIXTURE explanation: trained = actor + 2 critics + 1.' };
};
const VALID = { blocks_run: false, counts: {}, facts: { circuit_checked: false }, issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'fine_tune', network: NET, model_source: { run_dir: RUN, checkpoint_id: 'latest' } }, output: { experiment_name: 'fixture', ...(ROOT ? { output_root: ROOT } : {}) }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const asked = []; let canned = true, mode = {}, failNext = null;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (!canned && ['/api/runs/models', '/api/runs/model', '/api/runs/model/structure'].includes(name)) return send('Fetch.continueRequest', { requestId });
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [MODEL] });
    if (name === '/api/runs/model') { const found = describe(body.checkpoint_id); return found ? fulfil(requestId, 200, found) : fulfil(requestId, 404, { detail: { message: 'FIXTURE: no such checkpoint' } }); }
    if (name === '/api/runs/model/structure') {
      asked.push({ run_dir: body.run_dir, checkpoint_id: body.checkpoint_id });
      if (failNext) { const detail = failNext; failNext = null; return fulfil(requestId, 409, { detail }); }
      return fulfil(requestId, 200, structure(body.checkpoint_id, mode));
    }
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const until = (expression, tries = 60) => page.until(expression, tries);
  const RIGHT = `document.querySelector('.right')`, FOLD = `document.querySelector('.right details.structure')`, DIALOG = `document.querySelector('dialog.structure-dialog')`;
  const setSelect = (expression, value) => evaluate(`(() => { const s = ${expression}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)});
    s.dispatchEvent(new Event('change', { bubbles: true })); return s.value; })()`);
  const toggle = () => evaluate(`${FOLD}.querySelector('summary').click()`);
  const foldText = () => evaluate(`${FOLD}?.innerText ?? ''`);
  const sections = () => evaluate(`[...${FOLD}.querySelectorAll('table.structure-sections')].map(t => [...t.tBodies[0].rows].map(r => [...r.cells].map(c => c.textContent.trim())))`);
  const layers = () => evaluate(`[...${DIALOG}.querySelectorAll('table.structure-layers')].map(t => [...t.tBodies[0].rows].map(r => ({ cells: [...r.cells].map(c => c.textContent.trim()), css: r.className })))`);
  const lastAsked = () => asked[asked.length - 1] ?? {};
  const waitAsked = async (count) => { for (let i = 0; i < 50 && asked.length < count; i++) await sleep(100); return asked.length; };
  const shot = async (name, expression) => page.shot(path.join(out, name),
    await evaluate(`(() => { const r = ${expression}.getBoundingClientRect(); return { x: Math.max(0, r.x), y: Math.max(0, r.y), width: Math.min(1680, r.width), height: Math.min(1050, r.height), scale: 1 }; })()`));

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!${RIGHT}?.querySelector('select.model-point')`, 150))) throw new Error('the model chooser never showed the seeded model; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  if (!(await until(`!!(${FOLD})`, 60))) throw new Error('this page has no "Network structure" fold-out: the served frontend is older than it (npm run build, then reload)');

  // ---- closed by default; nothing is read until it is opened ----------------------------------------------------------------
  await sleep(800);
  check('the fold-out sits under the facts of the chosen model and is closed', await evaluate(`!${FOLD}.open && ${FOLD}.previousElementSibling?.classList.contains('model-facts')`));
  check('nothing is read before it is opened', asked.length === 0, `${asked.length} request(s)`);
  await toggle();
  check('opening it reads the structure once, for the RESOLVED save point (not "latest")', (await waitAsked(1)) === 1 && lastAsked().run_dir === RUN && lastAsked().checkpoint_id === POINTS[1].checkpoint_id, JSON.stringify(lastAsked()));
  await until(`!!${FOLD}.querySelector('table.structure-sections')`, 50);
  const full = structure(POINTS[1].checkpoint_id);
  let text = await foldText();
  check('the summary says what is trained, in plain words and with separators', text.includes(`${full.totals.trained.toLocaleString('en-US')} trained parameters = actor ${full.totals.actor.toLocaleString('en-US')} + 2 critics x ${full.totals.critic_each.toLocaleString('en-US')} + 1 (entropy temperature)`), text.slice(0, 160));
  check('... and what else is saved (the 2 target copies)', text.includes(`2 target copies of the critics (${full.totals.target_copies.toLocaleString('en-US')})`));
  check('never-used weights are said, with their number per network', text.includes(`${full.totals.never_used.toLocaleString('en-US')} of the trained parameters are never used (272 in each of the 3 trained networks)`) && /lin_skip/.test(text));
  let tables = await sections();
  check('one section table per network: section, layers, parameters, share', tables.length === 2 && tables[0].map(r => r[0]).join('|') === 'Inputs|Block 1 (272 never used)|Read-out|Output'
    && tables[0][1].slice(1).join('|') === `2|1,544|${(100 * 1544 / full.parts[0].parameters).toFixed(1)} %`, JSON.stringify(tables[0]));
  check('it fits the narrow panel', !(await evaluate(`${RIGHT}.scrollWidth > ${RIGHT}.clientWidth + 1`)) && await evaluate(`[...${FOLD}.querySelectorAll('table')].every(t => t.scrollWidth <= ${FOLD}.clientWidth + 1)`));
  await evaluate(`${FOLD}.scrollIntoView({ block: 'start' })`); await shot('structure-1-summary.png', RIGHT);

  // ---- the full layer table: a wide dialog, every layer, the never-used row marked ---------------------------------------------------
  check('the dialog is closed until asked for', !(await evaluate(`${DIALOG}.open`)));
  await evaluate(`[...${FOLD}.querySelectorAll('button')].find(b => b.textContent === 'Full layer table').click()`);
  check('"Full layer table" opens a dialog', await until(`${DIALOG}.open`, 30));
  const box = await evaluate(`(() => { const r = ${DIALOG}.getBoundingClientRect(); return { width: r.width, left: r.left, right: r.right, bottom: r.bottom }; })()`);
  check('the dialog is wide (the panel is 340 px) and inside the window', box.width > 900 && box.left >= 0 && box.right <= 1680 && box.bottom <= 1050, JSON.stringify(box));
  let rows = await layers();
  check('every layer of both networks is listed, plus a total row each', rows.length === 2 && rows.every((r, i) => r.length === full.parts[i].layers.length + 1), JSON.stringify(rows.map(r => r.length)));
  check('columns: #, section, layer, type, shape, parameters, share, what it does', (await evaluate(`[...${DIALOG}.querySelector('table.structure-layers').tHead.rows[0].cells].map(c => c.textContent).join('|')`)) === '#|Section|Layer|Type|Shape|Parameters|Share|What it does');
  check('a row reads as number, section, path, type, shape, count, share, role', rows[0][0].cells.join('|') === `1|Inputs|encoder.device_values|Linear|32 -> 16|528|${(100 * 528 / full.parts[0].parameters).toFixed(1)} %|FIXTURE: device numbers into the hidden width.`, rows[0][0].cells.join('|'));
  const skip = rows[0].find(r => r.cells[2] === 'encoder.blocks.0.attention.lin_skip');
  check('the never-used layer is marked and says so first', skip.css === 'unused' && skip.cells[7].startsWith('Never used. ') && skip.cells[7].includes('never read by this network'), JSON.stringify(skip));
  check('no other row is marked', rows.flat().filter(r => r.css === 'unused').length === 2);
  check('the total row equals the network', rows[0][rows[0].length - 1].cells[5] === full.parts[0].parameters.toLocaleString('en-US') && rows[1][rows[1].length - 1].cells[5] === full.parts[1].parameters.toLocaleString('en-US'));
  check('the actor ends in 2 outputs per group, the critic in 1 number', rows[0][rows[0].length - 2].cells[4] === '16 -> 2' && rows[1][rows[1].length - 2].cells[4] === '16 -> 1');
  check('TABLES ONLY: no canvas, svg or image in the fold-out or the dialog', (await evaluate(`${FOLD}.querySelectorAll('canvas, svg, img').length + ${DIALOG}.querySelectorAll('canvas, svg, img').length`)) === 0);
  await shot('structure-2-dialog.png', DIALOG);
  await evaluate(`${DIALOG}.querySelector('button.dialog-close').click()`);
  check('the close cross closes it', await until(`!${DIALOG}.open`, 30));

  // ---- another save point re-reads it; a model without never-used weights says nothing about them -------------------------------------
  mode = { withUnused: false, scale: 2 };
  await setSelect(`${RIGHT}.querySelector('select.model-point')`, POINTS[0].checkpoint_id);
  check('choosing another save point re-reads the structure for exactly that one', (await waitAsked(2)) === 2 && lastAsked().checkpoint_id === POINTS[0].checkpoint_id, JSON.stringify(lastAsked()));
  const other = structure(POINTS[0].checkpoint_id, mode);
  check('... and the numbers follow', await until(`${FOLD}.innerText.includes(${JSON.stringify(other.totals.trained.toLocaleString('en-US') + ' trained parameters')})`, 50), (await foldText()).slice(0, 80));
  check('no never-used note when there is none', !/never used/.test(await foldText()));

  // ---- types that could not be verified are not shown; an error is said ------------------------------------------------------------------
  mode = { typed: false }; await toggle(); await sleep(300); await toggle(); await waitAsked(3);
  check('unverified types: said in plain words, tensors still listed', await until(`/Layer types are not shown: FIXTURE: the network could not be rebuilt/.test(${FOLD}.innerText) && /Every saved tensor is still listed/.test(${FOLD}.innerText)`, 50));
  await evaluate(`[...${FOLD}.querySelectorAll('button')].find(b => b.textContent === 'Full layer table').click()`); await until(`${DIALOG}.open`, 30);
  rows = await layers();
  check('... the type column shows "-" and nothing is marked never used', rows[0].slice(0, -1).every(r => r.cells[3] === '-') && rows.flat().every(r => r.css !== 'unused'), JSON.stringify(rows[0][0].cells.slice(2, 5)));
  await evaluate(`${DIALOG}.close()`);
  failNext = { message: 'FIXTURE: model_weights.pt is missing or does not match the checksum recorded in metadata.json' }; mode = {};
  await toggle(); await sleep(300); await toggle(); await waitAsked(4);
  check('a refusal is said as the backend worded it', await until(`/The structure could not be read: FIXTURE: model_weights.pt is missing or does not match the checksum/.test(${FOLD}.innerText)`, 50), (await foldText()).slice(0, 160));
  await toggle(); await sleep(200);
  const before = asked.length; await sleep(1500);
  check('closed again: nothing is read, and nothing on a timer', asked.length === before);

  // ---- the REAL routes of this backend ---------------------------------------------------------------------------------------------------------
  const realModels = await fetch(new URL('api/runs/models' + (ROOT ? `?output_root=${encodeURIComponent(ROOT)}` : ''), APP));
  const first = realModels.ok ? (await realModels.json()).models[0] : null;
  const real = first && await fetch(new URL('api/runs/model/structure', APP), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_dir: first.run_dir, checkpoint_id: first.latest }) });
  if (!first) console.log('SKIP  the real routes: this backend has no saved model under its output folder (or is older than the chooser)');
  else if (real.status === 404 || real.status === 405) console.log('SKIP  the real /api/runs/model/structure route: this backend is older than it - restart it');
  else {
    const expected = await real.json();
    canned = false;
    await evaluate(`[...${RIGHT}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Refresh list').click()`);
    const CARD = `[...${RIGHT}.querySelectorAll('button.model-card')].find(b => b.title === ${JSON.stringify(first.run_dir)})`;
    check('against the real routes: the first real model can be chosen', (await until(`!!(${CARD})`, 80)) && (await evaluate(`(${CARD}.click(), true)`)) && await until(`${CARD}.getAttribute('aria-checked') === 'true'`, 40), first.run_dir);
    await until(`!!(${FOLD}) && !${FOLD}.open`, 50); await toggle();
    const words = `${expected.totals.trained.toLocaleString('en-US')} trained parameters = actor ${expected.totals.actor.toLocaleString('en-US')} + 2 critics x ${expected.totals.critic_each.toLocaleString('en-US')}`;
    check(`... its summary equals the real route (${words})`, await until(`${FOLD}.innerText.includes(${JSON.stringify(words)})`, 80), (await foldText()).slice(0, 140));
    check('... the real model\'s types were verified by the backend', expected.types_verified === true && !/Layer types are not shown/.test(await foldText()));
    await evaluate(`[...${FOLD}.querySelectorAll('button')].find(b => b.textContent === 'Full layer table').click()`); await until(`${DIALOG}.open`, 30);
    rows = await layers();
    check(`... every real layer is listed (${expected.parts.map(p => p.layers.length).join(' + ')})`, rows.length === 2 && rows.every((r, i) => r.length === expected.parts[i].layers.length + 1), JSON.stringify(rows.map(r => r.length)));
    check('... and every real layer has a type and a plain line', rows.flat().filter(r => r.css !== 'total').every(r => r.cells[3] !== '-' && r.cells[7].length > 10));
    await shot('structure-3-real-dialog.png', DIALOG);
    await evaluate(`${DIALOG}.close()`);
  }

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect, save settings or call an agent on its own: never',
    !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/|network-settings)/.test(r)), refused.join(', '));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
