// Browser check of the saved-model chooser in the run panel ("RL model to load"; there is no frontend test runner here).
// Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against a RUNNING
// workbench (default http://127.0.0.1:8765/). The chooser's two routes (/api/runs/models, /api/runs/model), the default
// model and the validation are answered with canned data labelled FIXTURE, so the shown models are known. GET requests
// pass through; every other writing request is refused here, so this check can start, save or probe nothing on the
// backend it runs against. The browser profile is new and temporary: the user's saved configuration is not touched.
// What it pins (user request 2026-09-21, "can you choose which model to load?" / "what is a source run"):
// nothing is read while Mode is scratch; one card per run that holds a model, in plain words; MOCK / weights only
// tags; choosing a card selects its LATEST save; every save point can be chosen and is the one the backend
// is asked about; a best policy is offered only where one exists; a stale selection is said and can be cleared; the
// filter; one request per "Refresh list" and no timer; the cards fit the narrow panel.
// User request 2026-09-21 ("when the mode selection is not scratch, dont show the RL NETWORK part for new encoder
// settings. Only the list of existing model encoders"): the "RL network" block is shown in scratch only; in a Mode that
// loads a model the configuration takes the chosen model's network by itself, and nothing is written to the backend.
// Last section, against the REAL route of the backend it runs on: the cards equal GET /api/runs/models (skipped with a
// note when that backend is older than the route and has to be restarted).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/model_chooser_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
// Optional: the output folder whose saved models the last section lists (default: the backend's own default root).
// From WSL both variables need WSLENV=GATOR_WORKBENCH_URL:GATOR_WORKBENCH_OUTPUT_ROOT to reach the Windows process.
const ROOT = process.env.GATOR_WORKBENCH_OUTPUT_ROOT || undefined;
const out = outDir();
const browser = await launchEdge('models');

// ---- canned answers ------------------------------------------------------------------------------------------
const NET = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 1 }, GAT = { ...NET, encoder_type: 'gat' }, RGCN = { ...NET, encoder_type: 'rgcn' };
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
const A = model('FIXTURE_opamp_gt', 'synthetic:gpdk045_ota5', [point('a1', 6, 'periodic', 1), point('a2', 12, 'periodic', 2), point('a3', 18, 'periodic', 3), point('a4', 20, 'final', 4, { is_latest: true })]);
const B = model('FIXTURE_ldo_gat', 'synthetic:ldo', [point('b1', 8, 'stop', 5, { is_latest: true, network: GAT })]);
const C = model('FIXTURE_weights_only', 'synthetic:vco', [point('c1', 10, 'pause', 6, { is_latest: true, restoration_capability: 'weights_only', missing_components: ['replay_snapshot (disabled in output settings)'] })]);
const D = model('FIXTURE_real_ota5', 'real:gpdk045_ota5', [point('d1', 30, 'periodic', 7, { is_best_policy: true, network: RGCN }), point('d2', 40, 'final', 8, { is_latest: true, network: RGCN })], { mock: false });
const FILLERS = ['e', 'f', 'g'].map((t, n) => model(`FIXTURE_filler_${t}`, 'synthetic:gpdk045_ota5', [point(`${t}1`, 5 + n, 'final', 9 + n, { is_latest: true })]));
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
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'scratch', network: NET }, output: { experiment_name: 'fixture', ...(ROOT ? { output_root: ROOT } : {}) }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const asked = []; let lists = 0, canned = true, served = MODELS;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') { lists++; return canned ? fulfil(requestId, 200, { models: served }) : send('Fetch.continueRequest', { requestId }); }
    if (name === '/api/runs/model') {
      const body = JSON.parse(request.postData ?? '{}'); asked.push({ run_dir: body.run_dir, checkpoint_id: body.checkpoint_id, network: body.config?.run?.network ?? null });
      const found = describe(body.run_dir, body.checkpoint_id);
      if (found && body.run_dir === C.run_dir) { delete found.compatibility; found.compatibility_unchecked = { title: 'FIXTURE: Not compared with your configuration yet: the configuration on this page is incomplete.',
        what: 'FIXTURE: Parameter row "mp1_w" is set to be optimized but has no lower and no upper bound. Fill in both bounds in the Parameters table.',
        note: 'FIXTURE: This says nothing about the saved model.', technical: 'CompileError: mp1_w: bounds are required' }; }
      return found ? fulfil(requestId, 200, found) : fulfil(requestId, 404, { detail: { message: 'FIXTURE: no such checkpoint' } });
    }
    if (name === '/api/config/diff') return page.pass(requestId);                      // the diff is a pure comparison: nothing is written
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const until = (expression, tries = 60) => page.until(expression, tries);
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
  const lastConfigNet = () => lastAsked().network ?? null;
  // The block for a NEW network: its heading, the Encoder list, the size boxes and the preset buttons.
  const newNetwork = () => evaluate(`({ heading: [...${RIGHT}.querySelectorAll('h3')].some(h => h.textContent.trim() === 'RL network'), encoder: !!(${labelled('Encoder')}),
    sizes: ['hidden', 'heads', 'layers'].filter(t => [...${RIGHT}.querySelectorAll('label')].some(l => l.firstChild?.textContent?.trim().split(' - ')[0] === t && l.checkVisibility())).length,
    presets: ['Publication preset', 'GATOR baseline'].filter(t => [...${RIGHT}.querySelectorAll('button')].some(b => b.textContent.trim() === t)).length,
    origin: [...${RIGHT}.querySelectorAll('summary')].some(x => /^Where the .+ values come from$/.test(x.textContent.trim())),
    advanced: [...${RIGHT}.querySelectorAll('summary')].some(x => /^Advanced/.test(x.textContent.trim())) })`);
  const storedNetwork = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')?.run?.network ?? null`);
  const sameNet = (a, b) => !!a && ['encoder_type', 'hidden_dim', 'heads', 'layers'].every(f => a[f] === b[f]);
  const shot = name => page.shot(path.join(out, name), RIGHT, { scale: 1.5, maxHeight: 1050 });
  const reveal = expression => evaluate(`${expression}?.scrollIntoView({ block: 'center' })`);

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'once' });
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
  const inScratch = await newNetwork();
  check('in scratch mode the block for a NEW network is there: heading, Encoder list, sizes, preset buttons', inScratch.heading && inScratch.encoder && inScratch.sizes === 3 && inScratch.advanced, JSON.stringify(inScratch));
  check('the old "Source run" / "Checkpoint" pickers are gone', !(await evaluate(`!!(${labelled('Source run')}) || !!(${labelled('Checkpoint')})`)));

  // ---- LOOKING at a saved model needs no Mode that loads it, and changes nothing about the run ----------------------------
  const LOOK = `${RIGHT}.querySelector('button.look-open')`;
  check('in scratch mode there is a "Look at a saved model" button, and still nothing was read', (await evaluate(`${LOOK}?.textContent`)) === 'Look at a saved model' && lists === 0);
  await evaluate(`${LOOK}.click()`);
  check('pressing it reads the list once and says that it is look-only', (await until(`${RIGHT}.querySelectorAll('button.model-card').length === ${MODELS.length}`, 50)) && lists === 1
    && /Saved models \(look only\)/i.test(await evaluate(`${RIGHT}.innerText`)) && /Looking only: nothing here changes the run/.test(await evaluate(`${RIGHT}.innerText`)), `${lists} request(s)`);
  await evaluate(`${card(A.task_name)}.click()`);
  check('a chosen model offers its structure table and its circuit graph view', await until(`!!${RIGHT}.querySelector('details.structure') && !!${RIGHT}.querySelector('button.graph-open') && !${RIGHT}.querySelector('button.graph-open').disabled`, 40));
  await sleep(1100);
  check('... and NOTHING about the run changed: Mode is still scratch, no model is put into the configuration',
    (await evaluate(`${labelled('Mode')}.value`)) === 'scratch' && ((await stored())?.run_dir ?? null) === null && asked.length === 0, JSON.stringify(await stored()));
  await evaluate(`${RIGHT}.querySelector('button.look-close').click()`);
  check('"Done looking" puts it away', await until(`!${RIGHT}.querySelector('button.model-card') && !!(${LOOK})`, 30));

  // ---- a mode that loads a model: one card per run that holds one ---------------------------------------------------
  const listsBefore = lists;
  await setSelect(labelled('Mode'), 'fine_tune');
  check('choosing fine_tune reads the list once', (await until(`${RIGHT}.querySelectorAll('button.model-card').length > 0`, 50)) && lists === listsBefore + 1, `${lists - listsBefore} request(s)`);
  const inFineTune = await newNetwork();
  check('in fine_tune the block for a NEW network is NOT shown: no heading, no Encoder list, no sizes, no preset buttons, no "where the values come from"',
    !inFineTune.heading && !inFineTune.encoder && inFineTune.sizes === 0 && inFineTune.presets === 0 && !inFineTune.origin, JSON.stringify(inFineTune));
  check('... the Advanced numbers stay (they belong to the run, and hold the fine_tune switches)', inFineTune.advanced);
  check('... and the chooser says that the run uses the chosen model\'s network', /The run uses that model's network, shown on its card/.test(await blockText()));
  let shown = await cards();
  check('one card per saved model, most recently saved first', shown.length === MODELS.length && shown.map(c => c.title).join() === MODELS.map(m => m.task_name).join(), shown.map(c => c.title).join());
  check('the block explains what a run and a saved model are', /A run is one training session \(one press of Start\)/.test(await blockText()));
  check('the count is said', /7 saved models under the output folder/.test(await blockText()));
  const byName = name => shown.find(c => c.title === name);
  check('a card names the circuit, the network, the training and the saves in plain words',
    byName(A.task_name).lines[0] === 'synthetic:gpdk045_ota5 - graph_transformer 16/2/1' && byName(A.task_name).lines[1] === '20 evaluations of training - 4 save points'
    && /^last saved .+ - run completed \(scratch, seed 1\)$/.test(byName(A.task_name).lines[2]), JSON.stringify(byName(A.task_name).lines));
  check('one save point is singular', byName(B.task_name).lines[1] === '8 evaluations of training - 1 save point', byName(B.task_name).lines[1]);
  check('MOCK models are tagged, the real one is not', byName(A.task_name).tags.includes('MOCK') && !byName(D.task_name).tags.includes('MOCK'), JSON.stringify([byName(A.task_name).tags, byName(D.task_name).tags]));
  check('every card names ITS network (the list of existing model encoders); no card is tagged "other network" any more',
    byName(B.task_name).lines[0] === 'synthetic:ldo - gat 16/2/1' && shown.every(c => !c.tags.includes('other network'))
    && (await evaluate(`[...${RIGHT}.querySelectorAll('button.model-card b.model-net')].map(b => b.textContent).join('|')`)) === MODELS.map(m => `${m.network.encoder_type} 16/2/1`).join('|'));
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
  check('the chosen model\'s network is named with its facts, as the network this run uses', await until(`/^Network\\s+gat, hidden 16, heads 2, layers 1 - this run uses it as it is/.test(${RIGHT}.querySelector('tr.model-network')?.innerText ?? '')`, 40),
    await evaluate(`${RIGHT}.querySelector('tr.model-network')?.innerText ?? 'no row'`));
  await sleep(1100);
  check('... and the configuration took it by itself: gat, without a button', sameNet(await storedNetwork(), GAT) && !(await evaluate(`!!(${button("Use the checkpoint's network")})`))
    && !(await evaluate(`/This checkpoint was trained with/.test(${RIGHT}.innerText)`)), JSON.stringify(await storedNetwork()));
  check('... the backend was asked again with that network, so the compatibility shown is the one of the run', await (async () => { for (let i = 0; i < 40 && lastConfigNet()?.encoder_type !== 'gat'; i++) await sleep(100);
    return lastConfigNet()?.encoder_type === 'gat' && lastAsked().run_dir === B.run_dir; })(), JSON.stringify(lastConfigNet()));
  await evaluate(`${card(A.task_name)}.click()`);
  check('choosing a graph_transformer model takes the network back to graph_transformer', await (async () => { for (let i = 0; i < 40 && !sameNet(await storedNetwork(), NET); i++) await sleep(100); return sameNet(await storedNetwork(), NET); })(), JSON.stringify(await storedNetwork()));
  await evaluate(`${card(B.task_name)}.click()`);
  await until(`/^Network\\s+gat/.test(${RIGHT}.querySelector('tr.model-network')?.innerText ?? '')`, 40); await sleep(1100);
  // A network that arrives from ELSEWHERE while the model is loaded (an imported configuration, an applied agent
  // suggestion) is taken back as well - and that is said, because a silent revert reads as a button that does nothing.
  check('no note about the network so far: following a newly chosen model needs no words', !(await evaluate(`!!${RIGHT}.querySelector('.net-message.warn')`)));
  const imported = path.join(browser.tempDir('import'), 'import.config.json');
  const onPage = JSON.parse(await evaluate(`localStorage.getItem('gator-workbench-config-v1')`));
  // `schema_version` makes "Import JSON..." take the WHOLE configuration (without it only the rows of the open tab are taken).
  writeFileSync(imported, JSON.stringify({ ...onPage, schema_version: 'gator-workbench-config-v1', run: { ...onPage.run, network: NET } }));
  const { root } = await send('DOM.getDocument', { depth: 1 });
  const { nodeId } = await send('DOM.querySelector', { nodeId: root.nodeId, selector: '.editors input[type=file]' });
  await send('DOM.setFileInputFiles', { nodeId, files: [imported] });
  const APPLY = `[...document.querySelectorAll('.editors .confirm button')].find(b => b.textContent.trim() === 'Apply')`;
  check('(set-up) a configuration with another network is imported through "Import JSON..."', await until(`!!(${APPLY})`, 60), await evaluate(`document.querySelector('.editors .confirm')?.innerText.slice(0, 200) ?? 'no confirmation'`));
  await evaluate(`${APPLY}.click()`);
  check('a network from elsewhere is taken back while the model is loaded, and that is SAID', await until(`/The network stays gat 16\\/2\\/1: this run loads a saved model/.test(${RIGHT}.querySelector('.net-message.warn')?.textContent ?? '')`, 60),
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no message'`));
  await sleep(1100);
  check('... the configuration holds the model\'s network again', sameNet(await storedNetwork(), GAT), JSON.stringify(await storedNetwork()));

  // ---- an incomplete configuration on the page never hides the saved model (user report: "CompileError: mp1_w: bounds are required") ------------
  await evaluate(`${card(C.task_name)}.click()`);
  check('an incomplete configuration is said in plain words, as a calm note - not as a red error', await until(`!!${RIGHT}.querySelector('.compat-unchecked')`, 40)
    && /Parameter row "mp1_w" is set to be optimized but has no lower and no upper bound/.test(await evaluate(`${RIGHT}.querySelector('.compat-unchecked').innerText`))
    && !(await evaluate(`[...${RIGHT}.querySelectorAll('p.error')].some(p => /CompileError|bounds are required/.test(p.textContent))`)));
  check('... the saved model is still shown in full below the chooser', await until(`/10 evaluations, 6 updates/.test(${RIGHT}.innerText) && !!${RIGHT}.querySelector('details.structure') && !!${RIGHT}.querySelector('button.graph-open')`, 40));
  check('... and the developer text is folded away under "Technical details"', await evaluate(`(() => { const d = ${RIGHT}.querySelector('.compat-unchecked details'); return !d.open && d.querySelector('summary').textContent === 'Technical details' && /CompileError: mp1_w/.test(d.textContent); })()`));

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
  const again = await newNetwork();
  check('... and the block for a NEW network is back, showing the network that was last in use (rgcn, from the last chosen model)', again.heading && again.encoder && again.sizes === 3
    && (await evaluate(`${labelled('Encoder')}.value`)) === 'rgcn', JSON.stringify([again, await evaluate(`${labelled('Encoder')}?.value`)]));

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
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
