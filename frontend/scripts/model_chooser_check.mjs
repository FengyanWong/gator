// Browser check of the saved models in the RL model window (record 7.265; plan docs/plan-frontend-run-workflow.md, "RL model
// window"): the table that replaced the chooser's cards ("RL model to load", user request 2026-09-21, "can you choose which
// model to load?"). Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the DevTools protocol against a
// RUNNING workbench (default http://127.0.0.1:8765/). The routes of the saved models (/api/runs/models, /api/runs/model,
// rename, the models' folders), the default model and the validation are answered with canned data labelled FIXTURE, so
// the shown models are known. GET requests pass through; every other writing request is refused here, so this check can
// start, save or probe nothing on the backend it runs against. The browser profile is new and temporary.
// What it pins:
// - New model: the templates are shown, the saved models are not read until "Saved models, to look at" is opened, and
//   looking (Details, structure, graph view) changes nothing in the draft; its "Use" buttons are off;
// - Fine-tune / Evaluate only: one row per saved model, newest save first, each naming its task, network, evaluations,
//   save points, data and what it restores; no block for a new network; "no saved model chosen yet" is said and nothing
//   is filled in by itself;
// - a click only inspects (Details: save points newest first, compatibility, rename, relationships);
// - "Use this save point" pins exactly that save point - a concrete id, never "latest" - with the model's network, as ONE
//   Undo step; a double click on a row uses its newest save point, and so does Enter on the row, which is in the Tab order
//   with a run row's focus ring - on its Details button Enter opens the Details alone - and the line that asks for a model
//   says both (branch record SIF-121); a newer save point is offered, never followed;
// - a network that arrives from elsewhere while a model is loaded is taken back, and that is said; the import that brought it
//   says it replaced the run settings (branch record SIF-107);
// - an incomplete configuration is a calm note; rename refuses a taken name; the filter; one read per Refresh list - the
//   refresh icon, its words for screen readers and in its tooltip (branch record SIF-113) -, no timer;
//   a model in use that left the list, its folder saying "Click to copy" (branch record SIF-64); an empty folder; the models'
//   folders; back to New model; the real route;
// - a folder clicked in the window (a model's Details, the model in use, a model that left the list) is copied by the
//   window's own clipboard, never the main page's, and says "copied" or "could not copy" (branch record SIF-94);
// - Details check a save point as Use would load it: read first, then checked with the model's own network in a Mode that
//   loads it; the pressed Use says "Using..." while its save point is read, and one that cannot be read is said under that
//   model's save points too (branch record SIF-85);
// - the table scrolls in a box of its own with its titles at its top, the model in use brought into its view; Run
//   configuration's notice opens the window at the block its reason is about, the model line's button at the top (branch
//   record SIF-86);
// - opened again, the window keeps its view - folder, Design, filter, sort, open Details - and shows the rows of its last read
//   at once, its one read per open still going; the ticks go, and Details of a model that left the list close; a rename reads
//   the page's run list again, so the main page's model line and Next line name the model in use by its new name, and the
//   saved models are read again once (branch record SIF-102);
// - Fine-tune's switches that are on have a line of their own under the model line, by the window's labels, in view and
//   whole, and the Next line names them; the model line's tooltip names the model it saves; Evaluate only says Continual
//   learning, which its run reads too, and has its box (review of SIF-103); the facts show all six reward fields, and
//   "Use this model's reward" takes them as one Undo step while the next run's reward differs (branch record SIF-103);
// - the model's counters as the page writes every count: from 10,000 up in groups of three, plain below (branch record
//   SIF-117: "6,024 learner updates" here, "6024" in the Training tab and Run status).
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/model_chooser_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { NETWORK_DOCUMENT, NETWORK_PANEL, openNetworks, setMode } from './lib/rl_networks.mjs';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { check, focusOn, launchEdge, mockStarter, NEVER_ASKED_OR_SAVED, outDir, pressEnter, reportRefused, RL_MODEL_WINDOW, runChecks, sleep, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
// Optional: the output folder whose saved models the last section lists (default: the backend's own default root).
// From WSL both variables need WSLENV=GATOR_WORKBENCH_URL:GATOR_WORKBENCH_OUTPUT_ROOT to reach the Windows process.
const ROOT = process.env.GATOR_WORKBENCH_OUTPUT_ROOT || undefined;
const out = outDir();
const browser = await launchEdge('models');

// ---- canned answers ------------------------------------------------------------------------------------------
const NET = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 1 }, GATV2 = { ...NET, encoder_type: 'gatv2' }, RGCN = { ...NET, encoder_type: 'rgcn' };
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
  learner_updates: newest.learner_updates, restoration_capability: newest.restoration_capability, run_kind: 'optimization', parent: null,
  encoder: newest.network.encoder_type, ...extra }; };
const A = model('FIXTURE_opamp_gt', 'synthetic:gpdk045_ota5', [point('a1', 6, 'periodic', 1), point('a2', 12, 'periodic', 2), point('a3', 18, 'periodic', 3), point('a4', 20, 'final', 4, { is_latest: true })],
  { code: 'older' });                                                     // saved by an older optimizer source (review of branch record SIF-80)
// B's reward differs from the page's in each of its six fields (branch record SIF-103: "Use this model's reward").
const B_REWARD = { violation_shape: 'compressed', worst_spec_share: 0.25, objective_weight: 0.75, objective_shape: 'compressed', margin_weight: 0.5, nominal_gate_band: 0.4 };
const B = model('FIXTURE_ldo_gat', 'synthetic:ldo', [point('b1', 8, 'stop', 5, { is_latest: true, network: GATV2,
  contract: { reward_version: 'constraint_violation_v2', reward_settings: B_REWARD } })]);
const C = model('FIXTURE_weights_only', 'synthetic:vco', [point('c1', 10, 'pause', 6, { is_latest: true, restoration_capability: 'weights_only', missing_components: ['replay_snapshot (disabled in output settings)'],
  contract: { condition_policy: 'off', planned_conditions: [] } })]);                                    // a plan recorded empty (branch record SIF-80)
// D's newest save point carries a long run's learner updates and replay (FIXTURE), for the counters' two forms (SIF-117).
const D = model('FIXTURE_real_ota5', 'real:gpdk045_ota5', [point('d1', 30, 'periodic', 7, { is_best_policy: true, network: RGCN }),
  point('d2', 40, 'final', 8, { is_latest: true, network: RGCN, learner_updates: 6024, replay_size: 12000 })], { mock: false });
const FILLERS = ['e', 'f', 'g'].map((t, n) => model(`FIXTURE_filler_${t}`, 'synthetic:gpdk045_ota5', [point(`${t}1`, 5 + n, 'final', 9 + n, { is_latest: true })]));
const MODELS = [A, B, C, D, ...FILLERS].sort((x, y) => (x.saved_utc < y.saved_utc ? 1 : -1));            // newest save first, as the backend sends it
const describe = (run_dir, checkpoint_id) => {
  const m = MODELS.find(x => x.run_dir === run_dir); if (!m) return null;
  const p = checkpoint_id === 'latest' ? m.checkpoints.find(x => x.is_latest) : checkpoint_id === 'best_policy' ? m.checkpoints.find(x => x.is_best_policy) : m.checkpoints.find(x => x.checkpoint_id === checkpoint_id);
  if (!p) return null;
  return { description: { checkpoint_id: p.checkpoint_id, path: `${run_dir}/checkpoints/${p.checkpoint_id}`, kind: p.kind, source_run_id: m.run_id, source_task_id: m.task_id, mode: p.mode,
    created_utc: p.created_utc, metadata_version: 'FIXTURE', counters: { evaluations_committed: p.evaluations, learner_updates: p.learner_updates, replay_size: p.replay_size },
    restoration_capability: p.restoration_capability, restorable_components: [], missing_components: p.missing_components, contract: { model_config: p.network, sac_config: {}, ...p.contract }, file_problems: [] },
    vocabulary: { name: 'standard', label: 'standard (8 generic kinds)', pdk_id: null, sha256: null, loaded: true },
    compatibility: { mode: 'fine_tune', compatible: true, checks: [{ component: 'FIXTURE check', status: 'ok', detail: 'identical' },
      // the backend's digest check: a warning, never fatal, for fine_tune and frozen (checkpoints.check_compatibility)
      { component: 'optimizer source code digest', status: m.code === 'older' ? 'warning' : 'ok', detail: m.code === 'older' ? 'FIXTURE: checkpoint was written by analog_optimizer '
        + 'source 0123456789ab..., current source is ba9876543210... (a file under src/analog_optimizer/ changed). Weight tensors are still loaded shape-strictly; recorded as provenance.' : 'identical' }],
      checkpoint_id: p.checkpoint_id, source_run_id: m.run_id, restoration_capability: p.restoration_capability, suggestion: null }, suggestion: null };
};
// The page's run list is answered here too: the run of each saved model. The list of the backend this check runs against
// is read slowly from D:, and its late answer would read the saved models again in the middle of a section.
const RUNS = MODELS.map(m => ({ run_dir: m.run_dir, run_id: m.run_id, task_id: m.task_id, task_name: m.task_name, mode: m.mode, mock: m.mock, seed: m.seed,
  state: m.state, created_utc: m.created_utc, evaluations: m.evaluations, max_evaluations: m.evaluations, encoder: m.encoder, run_kind: 'optimization', parent: null }));
const VALID = validConfiguration();

await runChecks(browser, async () => {
  const starter = await mockStarter(APP);
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'scratch', network: NET }, output: { experiment_name: 'fixture', ...(ROOT ? { output_root: ROOT } : {}) }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const asked = []; const renames = []; let lists = 0, canned = true, served = MODELS;
  // Branch record SIF-102: how often the page's run list is read, and - once `runsFollow` - a run list that carries the names
  // the renames gave, as the backend's does (it reads the run folder's model_label.json). Until then it stays as it was.
  let runReads = 0, runsFollow = false; const labels = {};
  let incompatibleD = false;   // branch record SIF-36: D's compatibility answered as a "saved {...} != current {...}" pair
  // A save point's read without a configuration is a Use's - and, since branch record SIF-85, also the read a model's Details
  // make before their compatibility check, at the save point selected there (its newest). So both name the save point of the
  // Use they are about: the Details' read of another one goes through.
  let holdModel = null; const heldModel = [];                                      // record 7.278: a "Use" read held back, answered late
  let failModel = null;                                                            // record 7.291: a "Use" whose save point cannot be read
  let holdList = false; const heldList = [];                                       // branch record SIF-86: the list held until the window is short
  const modelFolders = { version: 1, folders: {}, assignments: {} }; let folderSerial = 0;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs') { runReads++; return fulfil(requestId, 200, { runs: runsFollow ? RUNS.map(r => (labels[r.run_dir] ? { ...r, model_label: labels[r.run_dir] } : r)) : RUNS }); }
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') { lists++; if (holdList) { heldList.push(requestId); return; }
      return canned ? fulfil(requestId, 200, { models: served }) : send('Fetch.continueRequest', { requestId }); }
    if (name === '/api/runs/model') {
      if (!canned) return send('Fetch.continueRequest', { requestId });
      const body = JSON.parse(request.postData ?? '{}'); asked.push({ run_dir: body.run_dir, checkpoint_id: body.checkpoint_id, network: body.config?.run?.network ?? null,
        mode: body.config?.run?.mode ?? null, source: body.config?.run?.model_source ?? null, withConfig: !!body.config });
      if (holdModel && holdModel === body.checkpoint_id && !body.config) { heldModel.push({ requestId, body }); return; }
      if (failModel && failModel === body.checkpoint_id && !body.config) return fulfil(requestId, 503, { detail: 'FIXTURE: the server is busy' });
      const found = describe(body.run_dir, body.checkpoint_id);
      if (found?.compatibility && incompatibleD && body.run_dir === D.run_dir) found.compatibility = { ...found.compatibility, compatible: false, checks: [
        { component: 'network architecture', status: 'incompatible', detail: "saved {'hidden_dim': 48, 'encoder_type': 'graph_gps', 'attention_mode': None} != current {'hidden_dim': 48, 'encoder_type': 'graph_transformer', 'attention_mode': 'local_port_attention'}" },
        { component: 'FIXTURE check', status: 'ok', detail: 'identical' }] };
      if (found && body.run_dir === C.run_dir && body.config) { delete found.compatibility; found.compatibility_unchecked = { title: 'FIXTURE: Not compared with your configuration yet: the configuration on this page is incomplete.',
        what: 'FIXTURE: Parameter row "mp1_w" is set to be optimized but has no lower and no upper bound. Fill in both bounds in the Parameters table.',
        note: 'FIXTURE: This says nothing about the saved model.', technical: 'CompileError: mp1_w: bounds are required' }; }
      return found ? fulfil(requestId, 200, found) : fulfil(requestId, 404, { detail: { message: 'FIXTURE: no such checkpoint' } });
    }
    if (name === '/api/runs/model/rename') {                                         // record 7.225: answered here, so nothing is renamed on the backend
      const body = JSON.parse(request.postData ?? '{}'); renames.push(body);
      const mine = served.find(x => x.run_dir === body.run_dir), clash = served.find(x => x.run_dir !== body.run_dir && (x.model_label ?? x.task_name) === body.model_label);
      if (!mine) return fulfil(requestId, 404, { detail: { message: 'FIXTURE: Not a run directory' } });
      if (clash) return fulfil(requestId, 409, { detail: { message: `FIXTURE: A model named "${body.model_label}" exists already under this output folder. Choose another name.`, code: 'name_taken' } });
      const previous = mine.model_label ?? mine.task_name; served = served.map(x => x === mine ? { ...x, model_label: body.model_label } : x); labels[body.run_dir] = body.model_label;
      return fulfil(requestId, 200, { run_dir: body.run_dir, model_label: body.model_label, previous });
    }
    if (name.startsWith('/api/model-folders')) {                                     // the models' folders (record 7.263): a store of this check's own
      const body = JSON.parse(request.postData ?? '{}');
      if (request.method === 'POST') { const id = String(++folderSerial).padStart(32, '0'); modelFolders.folders[id] = body.name.trim(); return fulfil(requestId, 200, { ...modelFolders, created_id: id }); }
      if (request.method === 'PUT') body.run_dirs.forEach(dir => { if (body.folder_id) modelFolders.assignments[dir] = body.folder_id; else delete modelFolders.assignments[dir]; });
      return fulfil(requestId, 200, modelFolders);
    }
    if (name === '/api/config/diff') return page.pass(requestId);                      // the diff is a pure comparison: nothing is written
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const until = (expression, tries = 60) => page.until(expression, tries);
  const RIGHT = NETWORK_PANEL;
  const ROWS = `[...${RIGHT}.querySelectorAll('tr.model-row')]`;
  const row = m => `${ROWS}.find(r => r.title === ${JSON.stringify(m.run_dir)})`;
  const rows = () => evaluate(`${ROWS}.map(r => ({ dir: r.title, cells: [...r.children].map(c => c.innerText.replace(/\\s+/g, ' ').trim()), current: r.getAttribute('aria-current') === 'true' }))`);
  const heads = () => evaluate(`[...${RIGHT}.querySelector('table.model-table').tHead.rows[0].cells].map(c => c.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim())`);
  const details = m => evaluate(`(() => { const b = (${row(m)})?.querySelector('button.notes-link'); if (!b) return false; if (b.getAttribute('aria-expanded') !== 'true') b.click(); return true; })()`);
  const pointRow = id => `[...${RIGHT}.querySelectorAll('table.model-points tbody tr')].find(r => r.title === ${JSON.stringify(id)})`;
  const usePoint = id => evaluate(`(${pointRow(id)}).querySelector('button.model-use').click()`);
  const button = text => `[...${RIGHT}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('gator-workbench-config-v1') ?? 'null')?.run ?? null`);
  const storedWhen = async (test, tries = 40) => { for (let i = 0; i < tries; i++) { const s = await stored(); if (test(s)) return s; await sleep(100); } return stored(); };
  const line = () => evaluate(`document.querySelector('.rl-networks-row .net-short')?.textContent ?? ''`);
  // The header's "Next" line (record 7.269): what Start would start, beside it and first in its tooltip.
  const NEXT = `document.querySelector('header span.next-run')`;
  const startTitle = () => evaluate(`[...document.querySelectorAll('header button')].find(b => b.textContent.trim() === 'Start')?.title ?? ''`);
  const lastAsked = () => asked[asked.length - 1] ?? {};
  const sameNet = (a, b) => !!a && ['encoder_type', 'hidden_dim', 'heads', 'layers'].every(f => a[f] === b[f]);
  const shot = name => networkPage.shot(path.join(out, name), RIGHT, { scale: 1.2, maxHeight: 1400 });
  const undo = () => evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  // Record 7.291 (user request 2026-10-09: "after selecting one target task, model or run, close the pop up window"): a saved
  // model chosen closes the RL model window. What the choice did is looked at in the window opened again: the note, "in use"
  // and a newer save point offered are the page's own state, drawn again.
  const closedByChoice = async () => !!(await until(`!window.__checkRLWindow || window.__checkRLWindow.closed`, 50));
  // Branch record SIF-102: the rows of the last read show at once, so a reopen is over once the window's own read has answered.
  const READING = `/^Reading the saved models/.test(${RIGHT}.querySelector('.model-count')?.textContent ?? 'Reading')`;
  const reopen = async () => {
    networkPage = await openNetworks(page, browser); await networkPage.viewport(1180, 920);
    return until(`(${ROWS}.length === ${MODELS.length} && !${READING}) || !${RIGHT}.querySelector('.saved-models')`, 60);
  };
  // The saved models' reads once `n` were asked for, and a moment more: a second read would come within it.
  const readsReach = async (n, tries = 50) => { for (let i = 0; i < tries && lists < n; i++) await sleep(100); await sleep(300); return lists; };
  const chosenAndReopened = async () => { const closed = await closedByChoice(); await reopen(); return closed; };
  // Branch record SIF-94: a folder clicked in this window is copied by ITS clipboard (the main page's refuses a write while the
  // pop-up has focus, and the copy failed unsaid). Both clipboards are stood in for - a headless window may not be focused -
  // the main page's recording too, to show that it is not the one written; `refuse`: the pop-up's refuses, as a browser does.
  const clipboards = (refuse = false) => evaluate(`(() => { window.__mainClip = null; window.__popupClip = null;
    Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: text => { window.__mainClip = text; return Promise.resolve(); } });
    Object.defineProperty(window.__checkRLWindow.navigator.clipboard, 'writeText', { configurable: true, value: ${refuse}
      ? () => Promise.reject(new DOMException('FIXTURE: Document is not focused.', 'NotAllowedError')) : text => { window.__popupClip = text; return Promise.resolve(); } }); })()`);
  const copiedFrom = async (cell, text, word) => { await clipboards(word !== ' copied'); await evaluate(`(${cell}).click()`);
    const said = await until(`(${cell})?.textContent === ${JSON.stringify(text + word)}`, 20);
    return { said, popup: await evaluate('window.__popupClip'), main: await evaluate('window.__mainClip'), text: await evaluate(`(${cell})?.textContent ?? 'no cell'`) }; };

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'once' });
  await send('Page.navigate', { url: APP });
  let networkPage = await openNetworks(page, browser);
  await networkPage.viewport(1180, 920);
  if (!(await until(`!!${NETWORK_DOCUMENT}.querySelector('.rl-modes')`, 150))) throw new Error('the RL model window has no Mode buttons: the served frontend is older than record 7.265 (build it, then reload)');

  // ---- New model: templates, and the saved models only to look at --------------------------------------------------
  await sleep(600);
  check('in New model the window shows the templates, and the saved models are not read', await evaluate(`!!${RIGHT}.querySelector('table.template-table')`) && lists === 0
    && await evaluate(`${NETWORK_DOCUMENT}.querySelector('.rl-modes button[aria-checked="true"]')?.dataset.mode`) === 'scratch', `${lists} read(s)`);
  check('the header says what Start would start: the task, New model, the network, the budget (record 7.269)',
    await until(`/^Next: synthetic:gpdk045_ota5 · New model · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 60)
    && (await startTitle()).startsWith(`Start: ${await evaluate(`(${NEXT}).textContent`)}. `), `${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)} | ${await startTitle()}`);
  check('... in full: the line is not cut off at this width (1,680 pixels)', await evaluate(`(${NEXT}).scrollWidth <= (${NEXT}).clientWidth`));
  const LOOK = `${RIGHT}.querySelector('details.look-models')`;
  check('the saved models are in a closed fold, "Saved models, to look at"', await evaluate(`!!(${LOOK}) && !${LOOK}.open && /^Saved models, to look at/.test(${LOOK}.querySelector('summary').textContent)`));
  await evaluate(`${LOOK}.open = true`);
  check('opening it reads the list once and shows every model', (await until(`${ROWS}.length === ${MODELS.length}`, 50)) && lists === 1, `${lists} read(s)`);
  await details(A);
  check('a model\'s Details offer its structure and circuit graph view, but its "Use this save point" buttons are off in New model',
    await until(`!!${RIGHT}.querySelector('details.structure') && !!${RIGHT}.querySelector('button.graph-open') && !!${RIGHT}.querySelector('button.model-use')`, 40)
    && await evaluate(`[...${RIGHT}.querySelectorAll('button.model-use')].every(b => b.disabled)`));
  // Branch record SIF-85: Details checked a save point with the page's network and Mode; now as Use would load it - read first,
  // as Use reads it, then checked in a Mode that loads it (Fine-tune here), with that save point as the source.
  const looked = await (async () => { for (let i = 0; i < 40 && !asked.some(a => a.run_dir === A.run_dir && a.withConfig); i++) await sleep(100);
    return asked.filter(a => a.run_dir === A.run_dir); })();
  const lookCheck = looked.find(a => a.withConfig);
  check('... and they check it as Use would load it: its save point read first, then checked as Fine-tune would load it, with it as the source (SIF-85)',
    !!looked[0] && !looked[0].withConfig && looked[0].checkpoint_id === A.latest && lookCheck?.mode === 'fine_tune'
    && lookCheck.source?.run_dir === A.run_dir && lookCheck.source?.checkpoint_id === A.latest && sameNet(lookCheck.network, NET), JSON.stringify(looked));
  await sleep(1100);
  check('... and looking changed NOTHING in the draft: New model, no saved model chosen', (await stored())?.mode === 'scratch' && !(await stored())?.model_source?.run_dir,
    JSON.stringify((await stored())?.model_source));

  // ---- Fine-tune: the table, nothing filled in by itself --------------------------------------------------------------
  const listsBefore = lists;
  await setMode(networkPage, 'fine_tune');
  check('Fine-tune reads the list once and shows a saved models table', (await until(`${ROWS}.length === ${MODELS.length}`, 50)) && (await readsReach(listsBefore + 1)) === listsBefore + 1,
    `${lists - listsBefore} read(s)`);
  // Branch record SIF-102: one table in one window - the Details opened in New model's look stay open in Fine-tune's table.
  check('... in the view New model\'s look left: A\'s Details are still open (SIF-102)', await evaluate(`(${row(A)})?.querySelector('button.notes-link')?.getAttribute('aria-expanded') === 'true'`));
  await evaluate(`(${row(A)}).querySelector('button.notes-link').click()`);                  // closed, for the table's own checks below
  check('... no block for a new network: no templates, no "The ... template" settings, no "where the values come from"',
    await evaluate(`!${RIGHT}.querySelector('table.template-table') && ![...${RIGHT}.querySelectorAll('h3')].some(h => / template, for this run$/.test(h.textContent)) && ![...${RIGHT}.querySelectorAll('summary')].some(s => /^Where the .+ values come from$/.test(s.textContent.trim()))`));
  check('... the Advanced numbers and Fine-tune\'s own settings are there', await evaluate(`[...${RIGHT}.querySelectorAll('summary')].some(s => /^Advanced/.test(s.textContent.trim()))
    && [...${RIGHT}.querySelectorAll('label.check')].some(l => l.textContent === 'Freeze encoder') && !!${RIGHT}.querySelector('input.model-label')`));
  // Branch record SIF-58: the three switches had no tooltip, so how Freeze encoder and Encoder-only transfer differ was said nowhere.
  const switchTitles = await evaluate(`Object.fromEntries(['Freeze encoder', 'Encoder-only transfer', 'Reset critic'].map(t => [t, [...${RIGHT}.querySelectorAll('label.check')].find(l => l.textContent === t)?.title ?? null]))`);
  check('... and each of its three switches says what it does (SIF-58)', /^The graph encoders .* only the actor and critic heads learn\.$/.test(switchTitles['Freeze encoder'] ?? '')
    && /^Only the encoders' weights are loaded;/.test(switchTitles['Encoder-only transfer'] ?? '') && /^The critics and their target copies start from new random weights;/.test(switchTitles['Reset critic'] ?? ''),
    JSON.stringify(switchTitles));
  check('... "no saved model chosen yet" is said, and none was filled in by itself (record 7.265)', await evaluate(`!!${RIGHT}.querySelector('.model-none-chosen')`)
    && !(await storedWhen(s => s?.mode === 'fine_tune'))?.model_source?.run_dir && /^Fine-tune · no saved model chosen/.test(await line()), await line());
  // Branch record SIF-121: the row's double click was said nowhere on the page, and its Enter would use a model unannounced.
  const noneChosen = await evaluate(`${RIGHT}.querySelector('.model-none-chosen')?.textContent ?? ''`);
  check('... and it says how one is chosen: a save point\'s Use, or a model\'s newest by a double click on its row or Enter on it (SIF-121)',
    noneChosen === 'No saved model is chosen yet: Fine-tune needs one. Use a save point below (a model\'s newest: a double click on its row, or Enter on it); this window then closes.', noneChosen);
  // Branch record SIF-1: the network's design by name (user: "show what is each models original shape design"), its size
  // under it, in the column that was "Network".
  check('the columns: name, trained on, design, evaluations, save points, last saved, started from, data, restorable', JSON.stringify((await heads()).slice(1, 10))
    === JSON.stringify(['Name', 'Trained on', 'Design', 'Evaluations', 'Save points', 'Last saved', 'Started from', 'Data', 'Restorable']), JSON.stringify(await heads()));
  let shown = await rows();
  check('one row per saved model, most recently saved first', shown.length === MODELS.length && shown.map(r => r.dir).join() === MODELS.map(m => m.run_dir).join(), shown.map(r => r.cells[1]).join(' | '));
  const cellsOf = m => shown.find(r => r.dir === m.run_dir).cells;
  check('a row names the model, its task, ITS design by name and its size, its evaluations and save points', cellsOf(A)[1] === A.task_name
    && cellsOf(A)[2] === 'synthetic:gpdk045_ota5' && cellsOf(A)[3] === 'Graph Transformer 16/2/1' && cellsOf(A)[4] === '20' && cellsOf(A)[5] === '4'
    && cellsOf(B)[3] === 'GATv2 16/2/1'
    && await evaluate(`(${row(B)}).querySelector('td.model-net').title`) === 'gatv2 16/2/1', JSON.stringify(cellsOf(A)));
  check('MOCK models are tagged, the real one is not; a model saved without its replay restores "weights only"', cellsOf(A)[8] === 'MOCK' && cellsOf(D)[8] === 'real'
    && cellsOf(C)[9] === 'weights only' && cellsOf(A)[9] === 'full state', JSON.stringify([cellsOf(A)[8], cellsOf(D)[8], cellsOf(C)[9]]));
  // Branch record SIF-17: "Last saved" as the Runs and Tasks windows write a time.
  check('"Last saved" reads as the other windows write a time: 2026-10-20 13:09:10 (SIF-17)', /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(cellsOf(A)[6]), cellsOf(A)[6]);
  // Branch record SIF-13: a real task by its name, without "real:" (as since record 7.249); the key on hover.
  check('a real model\'s task is named without "real:", its key on hover (SIF-13)', cellsOf(D)[2] === 'gpdk045_ota5'
    && await evaluate(`(${row(D)}).children[2].title`) === 'real:gpdk045_ota5', JSON.stringify([cellsOf(D)[2], await evaluate(`(${row(D)}).children[2].title`)]));
  // Branch record SIF-10: one design only, from a list beside Refresh list that counts each design.
  const DESIGN = `${RIGHT}.querySelector('select.model-design-filter')`;
  check('the Design list offers every design there is, the most models first, with how many (SIF-10)',
    (await evaluate(`[...(${DESIGN}).options].map(o => o.textContent).join(' | ')`)) === 'All designs | Graph Transformer (5) | GATv2 (1) | RGCN (1)',
    await evaluate(`[...(${DESIGN}).options].map(o => o.textContent).join(' | ')`));
  await page.setValue(DESIGN, 'RGCN', { event: 'change' }); await sleep(300);
  check('...choosing one keeps its models only', JSON.stringify((await rows()).map(r => r.dir)) === JSON.stringify([D.run_dir]), JSON.stringify((await rows()).map(r => r.cells[1])));
  await page.setValue(DESIGN, '', { event: 'change' }); await sleep(300);
  check('...and All designs brings every model back', (await rows()).length === MODELS.length, String((await rows()).length));
  check('the table fits the window (1100 px): no sideways scroll, every Details button in view', await evaluate(`(() => { const s = ${RIGHT}.querySelector('.task-folder-content .scroll'), w = ${NETWORK_DOCUMENT}.documentElement.clientWidth;
    return s.scrollWidth <= s.clientWidth + 1 && [...${RIGHT}.querySelectorAll('tr.model-row button.notes-link')].every(b => b.getBoundingClientRect().right <= w); })()`),
    await evaluate(`(() => { const s = ${RIGHT}.querySelector('.task-folder-content .scroll'); return s.scrollWidth + ' > ' + s.clientWidth; })()`));
  check('the count is said', /7 saved models under the output folder/.test(await evaluate(`${RIGHT}.querySelector('.model-count').textContent`)));
  check('nothing is in use yet', shown.every(r => !r.current));
  await shot('models-1-table.png');

  // ---- a click only inspects -------------------------------------------------------------------------------------------
  const askedBefore = asked.length;
  await details(A);
  check('Details list the save points, newest first, each with its kind', await until(`!!${RIGHT}.querySelector('table.model-points')`, 30)
    && JSON.stringify(await evaluate(`[...${RIGHT}.querySelectorAll('table.model-points tbody tr')].map(r => r.title)`)) === JSON.stringify([...A.checkpoints].reverse().map(p => p.checkpoint_id))
    && /saved at the end of the run · newest/.test(await evaluate(`${RIGHT}.querySelector('table.model-points tbody tr').innerText`)));
  check('... its compatibility with the task on the page is checked for its newest save point - an inspection', await until(`/Compatible for Fine-tune/.test(${RIGHT}.querySelector('details.model-compatibility')?.textContent ?? '')`, 40)
    && asked.slice(askedBefore).some(a => a.run_dir === A.run_dir && a.checkpoint_id === A.latest && a.withConfig), JSON.stringify(asked.slice(askedBefore)));
  await sleep(1100);
  check('... and opening Details changed nothing in the draft', !(await stored())?.model_source?.run_dir);
  const savedBy = await evaluate(`[...${RIGHT}.querySelectorAll('table.model-relations tr')].find(tr => tr.children[0].textContent === 'Saved by')?.children[1].innerText.replace(/\\s+/g, ' ').trim() ?? ''`);
  check('... "Saved by" names the run\'s Mode as the Mode buttons do: "New model, seed 1, completed", not "scratch" (SIF-44)', / · New model, seed 1, completed$/.test(savedBy), savedBy);
  const detailsFolder = await copiedFrom(`[...${RIGHT}.querySelectorAll('table.model-relations tr')].find(tr => tr.children[0].textContent === 'Folder')?.children[1]`, A.run_dir, ' copied');
  check('... a click on its Folder copies it by this window\'s clipboard, not the main page\'s, and says "copied" (SIF-94)', detailsFolder.said
    && detailsFolder.popup === A.run_dir && detailsFolder.main === null, JSON.stringify(detailsFolder));
  // Branch record SIF-67: a save point is named by its evaluations, as the table above counts it, its id on hover (it read
  // "- save point ckpt-00000020-a4"). Branch record SIF-85: the heading says the model is checked with its own network.
  const withTask = await evaluate(`(() => { const h = [...${RIGHT}.querySelectorAll('.model-details h4')].find(h => h.textContent.startsWith('With the task on the page'));
    return { text: h?.textContent ?? '', title: h?.querySelector('.hint span')?.title ?? null }; })()`);
  check('... "With the task on the page and this model\'s own network" names the save point by its evaluations, its id on hover (SIF-67, SIF-85)',
    withTask.text === 'With the task on the page and this model\'s own network - save point at 20 evaluations' && withTask.title === A.latest, JSON.stringify(withTask));
  // Branch record SIF-86: the table had no height of its own - 411 models made it about 20,000 px long, with the model in use
  // and the Mode's settings under it. It scrolls in a box now (A's Details make it longer than the box), its titles at its top.
  const box = await evaluate(`(() => { const s = ${RIGHT}.querySelector('.task-folder-content .scroll'), w = ${NETWORK_DOCUMENT}.defaultView;
    const most = Math.min(0.6 * w.innerHeight, 720) + 1, scrolls = s.scrollHeight > s.clientHeight + 40;
    s.scrollTop = s.scrollHeight; const head = s.querySelector('thead th').getBoundingClientRect().top - s.getBoundingClientRect().top;
    const inner = [...s.querySelectorAll('.model-details table.grid th')].map(th => w.getComputedStyle(th).position);
    s.scrollTop = 0; return { height: s.clientHeight, most: Math.round(most), scrolls, head, inner: [...new Set(inner)] }; })()`);
  check('the table scrolls in a box of its own, 60 % of the window at most, its titles staying at its top; the Details\' own titles scroll with them (SIF-86)',
    box.height <= box.most && box.scrolls && Math.abs(box.head) <= 2 && JSON.stringify(box.inner) === '["static"]', JSON.stringify(box));

  // ---- Use this save point: pinned, with its network, one Undo step -----------------------------------------------------
  const early = A.checkpoints[0].checkpoint_id;
  await usePoint(early);
  let run = await storedWhen(s => s?.model_source?.checkpoint_id === early);
  check('"Use this save point" pins exactly that save point - a concrete id, never "latest"', run?.model_source?.run_dir === A.run_dir && run.model_source.checkpoint_id === early, JSON.stringify(run?.model_source));
  check('... and closes the RL model window (record 7.291)', await chosenAndReopened());
  check('... and says so, with the one Undo step', /^The next run fine-tunes FIXTURE_opamp_gt from its save point at 6 evaluations, with its network \(one Undo step takes it back\)\.$/.test(await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? ''`)),
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no note'`));
  check('... with the model\'s network, in the same step', sameNet(run?.network, NET), JSON.stringify(run?.network));
  check('... the row says "in use", and the model line names it with its save point', await until(`(${row(A)})?.getAttribute('aria-current') === 'true' && !!(${row(A)}).querySelector('.in-use-tag')`, 30)
    && await until(`/^Fine-tune FIXTURE_opamp_gt · save point 6 evaluations$/.test(document.querySelector('.rl-networks-row .net-short')?.textContent ?? '')`, 30), await line());
  check('... and so does the header\'s Next line, and Start\'s tooltip with it', await until(`/^Next: synthetic:gpdk045_ota5 · Fine-tune from FIXTURE_opamp_gt @ 6 · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 30)
    && (await startTitle()).startsWith(`Start: ${await evaluate(`(${NEXT}).textContent`)}. `), `${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)} | ${await startTitle()}`);
  check('... a newer save point is offered, never followed; the one loaded is named by its evaluations (SIF-67)', await until(`/has a newer save point: 20 evaluations/.test(${RIGHT}.querySelector('.model-newer')?.textContent ?? '')`, 30)
    && /the next run loads the save point at 6 evaluations\./.test(await evaluate(`${RIGHT}.querySelector('.model-newer')?.textContent ?? ''`))
    && (await stored())?.model_source?.checkpoint_id === early, await evaluate(`${RIGHT}.querySelector('.model-newer')?.textContent ?? 'no note'`));
  // Review of branch record SIF-80: a full save point of an older optimizer source cannot be continued (record 7.221: Continue
  // needs that source) - Restorable said "the run that saved it can be continued exactly" beside a digest warning.
  const OLDER = 'full state - written by an older version of the optimizer code: only that version can continue it; Fine-tune and Evaluate only still load its model.';
  const restorableA = `[...${RIGHT}.querySelectorAll('table.model-facts tr')].find(r => r.cells[0].textContent === 'Restorable')?.cells[1].textContent ?? 'no row'`;
  check('... its full save point of an older optimizer source is not promised an exact continuation: Restorable says it in the Runs window\'s words (SIF-80 review)',
    await until(`(${restorableA}) === ${JSON.stringify(OLDER)}`, 40) && /optimizer source code digest: warning/.test(await evaluate(`${RIGHT}.querySelector('ul.compat-problems')?.textContent ?? ''`))
    && /^full state: the run that saved it can be continued exactly; weights only: .*\. A full save point written by an older version of the optimizer code: only that version can continue it;/
      .test(await evaluate(`[...${RIGHT}.querySelector('table.model-table').tHead.rows[0].cells].find(c => c.textContent.startsWith('Restorable'))?.title ?? ''`)),
    await evaluate(restorableA));
  await undo();
  run = await storedWhen(s => !s?.model_source?.run_dir);
  check('one Undo takes the choice back', !run?.model_source?.run_dir, JSON.stringify(run?.model_source));
  await evaluate(`document.querySelector('section.editors button[title^="Redo:"]').click()`);
  run = await storedWhen(s => s?.model_source?.checkpoint_id === early);
  check('... and Redo brings it again', run?.model_source?.checkpoint_id === early);
  // ---- Fine-tune's own switches are said on the main page (branch record SIF-103) -------------------------------------------------
  // Only the window's last block said them, and it closes once a save point is chosen: kept across Modes and runs, and copied by
  // New run like this, a switch left on went unseen before Start. Those that are on have a line of their own under the model line,
  // by the window's labels; the header's Next line names them too, and the model line's tooltip the name typed for the model it
  // saves. Review of SIF-103: said at the end of the model line and the Next line, both cut at two lines, they were hidden - here
  // too, at 1,680 px (the model line needed 53 px and showed 35, the Next line 81 and 33) - while a textContent check passed.
  const SWITCH = text => `[...${RIGHT}.querySelectorAll('label.check')].find(l => l.textContent.startsWith(${JSON.stringify(text)}))?.querySelector('input')`;
  const LINE_TEXT = `document.querySelector('.rl-networks-row .net-short')?.textContent ?? ''`, LINE_TITLE = `document.querySelector('.rl-networks-row .net-short')?.title ?? ''`;
  const SWITCHES = `document.querySelector('.model-switches')`, LINE = `document.querySelector('.rl-networks-row .net-short')`;
  // In view, whole: drawn, inside the visible part of its column, and nothing of it cut (a clamped line has more to scroll than it shows).
  const inView = element => `(() => { const e = ${element}; if (!e || !e.getClientRects().length) return false;
    const r = e.getBoundingClientRect(), column = e.closest('aside')?.getBoundingClientRect() ?? { top: 0, bottom: innerHeight };
    return r.top >= column.top - 1 && r.bottom <= Math.min(column.bottom, innerHeight) + 1 && e.scrollHeight <= e.clientHeight + 1; })()`;
  const measured = element => evaluate(`(() => { const e = ${element}; return e ? \`\${e.textContent} (\${e.scrollHeight} px of \${e.clientHeight})\` : 'no line'; })()`);
  const PLAIN_A = 'Fine-tune FIXTURE_opamp_gt · save point 6 evaluations';
  const SAID = ' It saves the model as FIXTURE tuned, with a number if that name is taken.';
  for (const text of ['Freeze encoder', 'Reset critic', 'Continual learning']) await evaluate(`(${SWITCH(text)}).click()`);
  await page.setValue(`${RIGHT}.querySelector('input.model-label')`, 'FIXTURE tuned', { event: 'input' });
  run = await storedWhen(s => s?.advanced?.freeze_encoder && s.advanced.reset_critic && s.continual_learning && s.model_label === 'FIXTURE tuned');
  check('Fine-tune\'s switches that are on have a line of their own under the model line, by the window\'s labels in its order, in view and whole; the model line whole too (SIF-103 and its review)',
    !!run && await until(`(${SWITCHES})?.textContent === 'Switches on: Freeze encoder, Reset critic, Continual learning.'`, 30)
    && await evaluate(`!!(${SWITCHES}).previousElementSibling?.classList.contains('rl-networks-row')`) && await evaluate(inView(SWITCHES))
    && /^Ticked in the RL model window, under "Fine-tune: its own settings"\./.test(await evaluate(`(${SWITCHES}).title`))
    && await evaluate(`(${LINE_TEXT}) === ${JSON.stringify(PLAIN_A)}`) && await evaluate(inView(LINE)),
    `${await measured(SWITCHES)} | ${await measured(LINE)}`);
  await page.shot(path.join(out, 'models-1b-switches.png'), `(${SWITCHES}).closest('section.panel')`, { scale: 1.2, maxHeight: 400 });
  check('... the header\'s Next line names them, and Start\'s tooltip, which begins with it, says them whole (SIF-103)',
    await until(`/^Next: synthetic:gpdk045_ota5 · Fine-tune from FIXTURE_opamp_gt @ 6 · encoder frozen · critics reset · continual · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 30)
    && (await startTitle()).startsWith(`Start: ${await evaluate(`(${NEXT}).textContent`)}. `), `${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)} | ${await startTitle()}`);
  check('... and the model line\'s tooltip the name the model it saves goes by (SIF-103)', (await evaluate(LINE_TITLE)).endsWith(` RL model... changes it.${SAID}`),
    await evaluate(LINE_TITLE));
  // Review of SIF-103: Evaluate only reads Continual learning too - runs.py `_source_model` refuses there as well a source itself
  // fine-tuned on a test task unless it is on - and had no box for it. Fine-tune's other three are not its own.
  await setMode(networkPage, 'frozen');
  check('Evaluate only says Continual learning, which its run reads too, in view, and not Fine-tune\'s other three; its model line as before (review of SIF-103)',
    await until(`(${SWITCHES})?.textContent === 'Switches on: Continual learning.'`, 30) && await evaluate(inView(SWITCHES))
    && await evaluate(`(${LINE_TEXT}) === 'Evaluate FIXTURE_opamp_gt · save point 6 evaluations · deterministic actions'`)
    && await until(`/^Next: synthetic:gpdk045_ota5 · Evaluate FIXTURE_opamp_gt @ 6 \\(deterministic actions\\) · continual · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 30)
    && (await evaluate(LINE_TITLE)).endsWith(' RL model... changes it.'), `${await measured(SWITCHES)} | ${await line()} | ${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)}`);
  const CONTINUAL = SWITCH('Continual learning');
  const continual = await evaluate(`(() => { const box = ${CONTINUAL}, after = [...${RIGHT}.querySelectorAll('h3')].find(h => h.textContent === 'Evaluate only: its own settings')?.nextElementSibling;
    return { ticked: !!box?.checked, afterActions: !!box && after?.nextElementSibling === box.closest('label'), title: box?.closest('label').title ?? '', others: !!(${SWITCH('Freeze encoder')}) }; })()`);
  check('... and its own settings have the box, ticked, after Actions, saying what it decides; Fine-tune\'s other three are not there (review of SIF-103)',
    continual.ticked && continual.afterActions && /^Off: a saved model that was itself fine-tuned on a test task .* is refused/.test(continual.title) && !continual.others, JSON.stringify(continual));
  await evaluate(`(${CONTINUAL}).click()`);
  run = await storedWhen(s => s?.continual_learning === false);
  check('... unticked there, it is off, and the line goes with the Next line\'s word (review of SIF-103)', run?.continual_learning === false && await until(`!(${SWITCHES})`, 30)
    && await until(`/^Next: synthetic:gpdk045_ota5 · Evaluate FIXTURE_opamp_gt @ 6 \\(deterministic actions\\) · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 30),
    `${JSON.stringify(run?.continual_learning)} | ${await measured(SWITCHES)} | ${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)}`);
  await setMode(networkPage, 'fine_tune');
  for (const text of ['Freeze encoder', 'Reset critic']) await evaluate(`(${SWITCH(text)}).click()`);
  await page.setValue(`${RIGHT}.querySelector('input.model-label')`, '', { event: 'input' });
  run = await storedWhen(s => !s?.advanced?.freeze_encoder && !s?.advanced?.reset_critic && !s?.continual_learning && !s?.model_label);
  check('... and with every switch off and no name typed, no line of switches, and the lines read as before', await until(`(${LINE_TEXT}) === ${JSON.stringify(PLAIN_A)} && !(${SWITCHES})`, 30)
    && await until(`/^Next: synthetic:gpdk045_ota5 · Fine-tune from FIXTURE_opamp_gt @ 6 · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 30)
    && (await evaluate(LINE_TITLE)).endsWith(' RL model... changes it.'), `${await line()} | ${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)} | ${await evaluate(LINE_TITLE)}`);
  await evaluate(`${RIGHT}.querySelector('button.model-use-newer').click()`);
  run = await storedWhen(s => s?.model_source?.checkpoint_id === A.latest);
  check('"Use the newer one" pins the newer save point, and closes the window', run?.model_source?.checkpoint_id === A.latest && await chosenAndReopened()
    && !(await evaluate(`!!${RIGHT}.querySelector('.model-newer')`)), JSON.stringify(run?.model_source));
  // Branch record SIF-86: the model in use - A, the last row - is brought into the box's view when the list arrives: the box
  // only, never the window. Seen in a short window, whose box shows a few rows; the list waits until the window is that short.
  holdList = true;
  await networkPage.evaluate('window.close()'); await browser.window(RL_MODEL_WINDOW, { present: false });
  networkPage = await openNetworks(page, browser); await networkPage.viewport(1180, 480);
  for (let i = 0; i < 50 && !heldList.length; i++) await sleep(100);
  holdList = false;
  if (heldList.length) await fulfil(heldList.shift(), 200, { models: served });
  const INBOX = `(() => { const s = ${RIGHT}.querySelector('.task-folder-content .scroll'), r = (${row(A)})?.getBoundingClientRect(), b = s?.getBoundingClientRect();
    return { box: s ? s.scrollTop : null, row: r && b ? [Math.round(r.top - b.top - s.querySelector('thead').offsetHeight), Math.round(b.top + s.clientHeight - r.bottom)] : null,
      window: ${NETWORK_DOCUMENT}.defaultView.scrollY }; })()`;
  check('the model in use is brought into the box\'s view when the window opens: the box scrolled to it, the window stays at its top (SIF-86)',
    await until(`(() => { const at = ${INBOX}; return at.box > 0 && !!at.row && at.row[0] >= -1 && at.row[1] >= -1 && at.window === 0; })()`, 40), JSON.stringify(await evaluate(INBOX)));
  await networkPage.viewport(1180, 920);

  // ---- Enter on a row does what its double click does (branch record SIF-121) ----------------------------------------------------
  // From the row, the double click was the only way (the Details' Use the way round), as in the Runs window until SIF-109. On the
  // row's Details button Enter presses that alone; on the row itself it uses the model's newest save point. E: a MOCK Graph
  // Transformer with one save point; A is in use until then.
  const E = FILLERS[0];
  await focusOn(networkPage, `(${row(E)}).querySelector('button.notes-link')`); await pressEnter(networkPage);
  check('Enter on a row\'s Details button opens its Details alone: nothing is used, the window stays open (branch record SIF-121)',
    await until(`(${row(E)})?.querySelector('button.notes-link')?.getAttribute('aria-expanded') === 'true'`, 30)
    && (await stored())?.model_source?.run_dir === A.run_dir && !(await evaluate(`window.__checkRLWindow.closed`)), JSON.stringify((await stored())?.model_source));
  const modelFocus = await focusOn(networkPage, row(E));
  check('... the row itself is in the Tab order, its focus ring inside it as a run row\'s (SIF-121)', !!modelFocus?.held && modelFocus.tabIndex === 0
    && modelFocus.ring === 'solid 2px -2px', JSON.stringify(modelFocus));
  await pressEnter(networkPage);
  run = await storedWhen(s => s?.model_source?.run_dir === E.run_dir);
  check('... and Enter on the row does what its double click does: its newest save point is used, pinned, and the window closes (SIF-121)',
    run?.model_source?.run_dir === E.run_dir && run.model_source.checkpoint_id === E.latest && await chosenAndReopened(), JSON.stringify(run?.model_source));

  // ---- a double click uses a row's newest save point; another network comes in the same step -----------------------------------
  await evaluate(`(${row(B)}).querySelector('td:nth-child(4)').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  run = await storedWhen(s => s?.model_source?.run_dir === B.run_dir);
  check('a double click on a row uses its newest save point, pinned', run?.model_source?.run_dir === B.run_dir && run.model_source.checkpoint_id === B.latest, JSON.stringify(run?.model_source));
  check('... and its network (gatv2) is the run\'s at once - nothing follows later by itself', sameNet(run?.network, GATV2), JSON.stringify(run?.network));
  check('... and the double click closes the window too', await chosenAndReopened());
  check('the model in use is described under the table: its network, and that the run uses it as it is', await until(`/^Network\\s+GATv2, hidden 16, heads 2, layers 1 - this run uses it as it is/.test(${RIGHT}.querySelector('tr.model-network')?.innerText ?? '')`, 40),
    await evaluate(`${RIGHT}.querySelector('tr.model-network')?.innerText ?? 'no row'`));
  // Branch record SIF-2: the facts read plainly - the task by its name, the time in this computer's time, the table's words.
  const facts = await evaluate(`Object.fromEntries([...${RIGHT}.querySelectorAll('table.model-facts tr')].map(r => [r.cells[0].textContent, r.cells[1].textContent]))`);
  check('... and its facts read plainly: "Saved" in this computer\'s time, Restorable "full state", no zero padding (SIF-2)',
    /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(facts['Saved'] ?? '') && !('Saved (UTC)' in facts) && /^full state/.test(facts['Restorable'] ?? '')
    && !/0{4}$/.test(facts['Worst hard-spec share'] ?? '0') && !/:/.test(facts['Trained on'] ?? ':'), JSON.stringify(facts).slice(0, 400));
  const factsFolder = await copiedFrom(`[...${RIGHT}.querySelectorAll('table.model-facts tr')].find(r => r.cells[0].textContent === 'Folder')?.cells[1]`, `${B.run_dir}/checkpoints/${B.latest}`, ' copied');
  check('... a click on its Folder copies it by this window\'s clipboard, not the main page\'s, and says "copied" (SIF-94)', factsFolder.said
    && factsFolder.popup === `${B.run_dir}/checkpoints/${B.latest}` && factsFolder.main === null, JSON.stringify(factsFolder));
  // Branch record SIF-58: the counters with their nouns ("8 evaluations, 4 updates, replay 8"), what is planned ("unknown
  // planned"), on/off ("enabled"), and the version by what it is the version of ("Schema").
  check('... the counters, the condition plan and the metadata version in words (SIF-58)', facts['Training'] === '8 evaluations, 4 learner updates, 8 transitions in replay'
    && facts['Conditions'] === 'Nominal only; plan not recorded' && facts['Operating points'] === 'off' && facts['Metadata version'] === 'FIXTURE' && !('Schema' in facts),
    JSON.stringify(facts).slice(0, 700));
  // Branch record SIF-80: "Restorable full state" with no meaning, "standard: ..." / "device families (11 kinds)" in lower
  // case, and "Margin bonus weight" with no tooltip where the reward block says "Tightest-margin bonus weight" and what it does.
  const rewardTips = await evaluate(`(() => { const tip = name => [...${RIGHT}.querySelectorAll('table.model-facts tr')].find(r => r.cells[0].textContent === name)?.title ?? 'no row';
    const block = name => [...document.querySelectorAll('aside.right label.num')].find(l => l.firstElementChild?.textContent === name)?.title ?? 'no control';
    return ['Worst hard-spec share', 'Objective bonus weight', 'Tightest-margin bonus weight'].map(n => [tip(n), block(n)]); })()`);
  check('... and they explain themselves: Restorable says what it allows, the inputs and the list are named in capitals, the reward weights carry the reward block\'s names and tooltips (SIF-80)',
    facts['Restorable'] === 'full state - the run that saved it can be continued exactly.' && facts['Network inputs'] === 'Standard'
    && facts['Components'] === 'Standard (8 generic kinds) - the network of this run knows the same list.' && !('Margin bonus weight' in facts)
    && rewardTips.every(([tip, block]) => tip.length > 20 && tip === block), JSON.stringify([facts['Restorable'], facts['Network inputs'], facts['Components'], rewardTips]).slice(0, 900));
  // Branch record SIF-103: the facts showed four of the reward's six fields, so a model's reward could not be matched even by
  // hand - and Fine-tune keeps its critics only with it. The other two by the reward block's names and tooltips, and a press
  // that takes all six, as one Undo step, while the next run's reward differs.
  const factTip = name => evaluate(`[...${RIGHT}.querySelectorAll('table.model-facts tr')].find(r => r.cells[0].textContent === ${JSON.stringify(name)})?.title ?? 'no row'`);
  const shapeTip = await evaluate(`[...document.querySelectorAll('aside.right label')].find(l => l.textContent.startsWith('Objective shape'))?.title ?? 'no control'`);
  check('... and the reward\'s two other fields: Objective shape and Nominal gate band, with the reward block\'s tooltips (SIF-103)',
    facts['Objective shape'] === 'Compressed' && facts['Nominal gate band'] === '0.4' && shapeTip.length > 20 && await factTip('Objective shape') === shapeTip
    && /^Strictly between 0 and 1\./.test(await factTip('Nominal gate band')), JSON.stringify([facts['Objective shape'], facts['Nominal gate band'], shapeTip]));
  const rewardBefore = (await stored())?.reward ?? null;
  const FROM_MODEL = `${RIGHT}.querySelector('button.reward-from-model')`;
  const fromModel = await evaluate(`(() => { const b = ${FROM_MODEL}; return b && { text: b.textContent.trim(), title: b.title, row: b.closest('tr')?.cells[0].textContent }; })()`);
  check('"Use this model\'s reward" is offered on the Reward row while the next run\'s reward differs, each field that differs in its tooltip (SIF-103)',
    fromModel?.text === 'Use this model\'s reward' && fromModel.row === 'Reward' && /worst hard-spec share 0\.25 instead of /.test(fromModel.title)
    && /nominal gate band 0\.4 instead of /.test(fromModel.title) && /the conditions are not changed here/.test(fromModel.title), JSON.stringify(fromModel));
  await evaluate(`${FROM_MODEL}.click()`);
  run = await storedWhen(s => s?.reward?.nominal_gate_band === 0.4);
  check('... a press makes the next run\'s reward the model\'s, all six fields, and the offer goes', Object.entries(B_REWARD).every(([k, v]) => run?.reward?.[k] === v)
    && await until(`!${FROM_MODEL}`, 40), JSON.stringify(run?.reward));
  await undo();
  run = await storedWhen(s => s?.reward?.nominal_gate_band !== 0.4);
  check('... as one Undo step: Undo brings the reward back, and the offer with it', JSON.stringify(run?.reward ?? null) === JSON.stringify(rewardBefore)
    && await until(`!!${FROM_MODEL}`, 40), `${JSON.stringify(run?.reward)} | before ${JSON.stringify(rewardBefore)}`);
  await sleep(1100);
  // A network that arrives from ELSEWHERE while the model is loaded (an imported configuration) is taken back - and that is said.
  check('no note about the network so far', !(await evaluate(`!!${RIGHT}.querySelector('.net-message.warn')`)));
  const imported = path.join(browser.tempDir('import'), 'import.config.json');
  const onPage = JSON.parse(await evaluate(`localStorage.getItem('gator-workbench-config-v1')`));
  writeFileSync(imported, JSON.stringify({ ...onPage, schema_version: 'gator-workbench-config-v1', run: { ...onPage.run, network: NET } }));
  const { root } = await send('DOM.getDocument', { depth: 1 });
  const { nodeId } = await send('DOM.querySelector', { nodeId: root.nodeId, selector: '.editors input[type=file]' });
  await send('DOM.setFileInputFiles', { nodeId, files: [imported] });
  const APPLY = `[...document.querySelectorAll('.editors .confirm button')].find(b => b.textContent.trim() === 'Apply')`;
  check('(set-up) a configuration with another network is imported through "Import JSON..."', await until(`!!(${APPLY})`, 60));
  await evaluate(`${APPLY}.click()`);
  // Branch record SIF-107: Apply says what it changed - a whole configuration may replace settings out of view, here the run
  // settings alone - where the box went without a word.
  const IMPORT_NOTE = `(document.querySelector('.editors .paste-note')?.textContent ?? '')`;
  check('the import\'s Apply says it replaced the run settings, with Undo (branch record SIF-107)',
    await until(`${IMPORT_NOTE} === 'Imported: replaced the run settings. Undo takes it back.'`, 20), await evaluate(IMPORT_NOTE));
  check('a network from elsewhere is taken back while the model is loaded, and that is SAID', await until(`/The network stays GATv2 16\\/2\\/1: this run loads a saved model/.test(${RIGHT}.querySelector('.net-message.warn')?.textContent ?? '')`, 60),
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no message'`));
  check('... the configuration holds the model\'s network again', sameNet((await storedWhen(s => sameNet(s?.network, GATV2)))?.network, GATV2));

  // ---- a save point that cannot be read: said in the window, which stays open (record 7.291) ------------------------------------
  failModel = early;
  await details(A); await until(`!!(${pointRow(early)})`, 30); await usePoint(early);
  check('a save point that cannot be read is said, and the RL model window stays open: nothing was chosen',
    await until(`/That save point could not be read/.test(${RIGHT}.querySelector('.net-message.error')?.textContent ?? '')`, 40)
    && !(await evaluate(`window.__checkRLWindow.closed`)) && (await stored())?.model_source?.run_dir === B.run_dir,
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no note'`));
  // Branch record SIF-85: said only far above the table, the press looked like it did nothing.
  const useError = await evaluate(`(() => { const p = ${RIGHT}.querySelector('.model-details table.model-points + p.use-error'), b = (${pointRow(early)})?.querySelector('button.model-use');
    return { text: p?.className === 'error use-error' ? p.textContent : null, button: b?.textContent ?? null, on: b ? !b.disabled : false }; })()`);
  check('... and said under the save points of the model whose Use was pressed; its button is "Use this save point" again, on (SIF-85)',
    /^That save point could not be read: .*FIXTURE: the server is busy/.test(useError.text ?? '') && useError.button === 'Use this save point' && useError.on, JSON.stringify(useError));
  failModel = null;

  // ---- an incomplete configuration never hides the saved model -------------------------------------------------------------
  await details(C); await until(`!!(${pointRow(C.latest)})`, 30); await usePoint(C.latest);
  await storedWhen(s => s?.model_source?.run_dir === C.run_dir);
  await chosenAndReopened();
  check('an incomplete configuration is said in plain words, as a calm note - not as a red error', await until(`!!${RIGHT}.querySelector('.compat-unchecked')`, 40)
    && /Parameter row "mp1_w" is set to be optimized but has no lower and no upper bound/.test(await evaluate(`${RIGHT}.querySelector('.compat-unchecked').innerText`))
    && !(await evaluate(`[...${RIGHT}.querySelectorAll('p.error')].some(p => /CompileError|bounds are required/.test(p.textContent))`)));
  check('... the model in use is still described in full', await until(`/10 evaluations, 6 learner updates/.test(${RIGHT}.innerText)`, 40));   // "learner" since SIF-58
  const factsC = await evaluate(`Object.fromEntries([...${RIGHT}.querySelectorAll('table.model-facts tr')].map(r => [r.cells[0].textContent, r.cells[1].textContent]))`);
  check('... weights only says what it lacks and what it allows; Nominal only with an empty plan is said once, with no "0 conditions" (SIF-80)',
    factsC['Restorable'] === 'weights only - missing: replay_snapshot (disabled in output settings); usable for Fine-tune and Evaluate only.' && factsC['Conditions'] === 'Nominal only',
    JSON.stringify([factsC['Restorable'], factsC['Conditions']]));
  check('... and the developer text is folded away under "Technical details"', await evaluate(`(() => { const d = ${RIGHT}.querySelector('.compat-unchecked details'); return !d.open && d.querySelector('summary').textContent === 'Technical details' && /CompileError: mp1_w/.test(d.textContent); })()`));

  // ---- a best policy is marked where one exists; rename (record 7.225) --------------------------------------------------------------
  incompatibleD = true;
  const askedBeforeD = asked.length;
  await details(D);
  check('a run with a selected best policy marks that save point', await until(`/best policy/.test((${pointRow(D.checkpoints[0].checkpoint_id)})?.innerText ?? '')`, 30));
  const compat = await until(`/differ in 2 keys/.test(${RIGHT}.querySelector('details.model-compatibility')?.textContent ?? '')`, 40)
    ? await evaluate(`(() => { const d = ${RIGHT}.querySelector('details.model-compatibility'); return { open: d.open, summary: d.querySelector('summary').textContent,
        lines: [...d.querySelectorAll('ul.compat-diff > li')].map(li => li.textContent), passed: d.querySelector('details.compat-passed > summary')?.textContent }; })()`) : null;
  incompatibleD = false;
  check('an incompatible model: its problems first, a "saved {...} != current {...}" pair as the keys that differ (a design by its name), the passing check folded (branch record SIF-36); the summary names the Mode and says what incompatible means in the Modes\' own words (branch record SIF-53)',
    compat?.open && compat.summary === 'NOT compatible for Fine-tune - it cannot be loaded, and a run never falls back to New model' &&JSON.stringify(compat.lines) === JSON.stringify(['encoder_type GraphGPS → Graph Transformer', 'attention_mode none → local_port_attention'])
    && compat.passed === 'The other check passes', JSON.stringify(compat));
  // Branch record SIF-85 (the fixture above only draws an answer): the page holds C, a Graph Transformer, and D is an RGCN -
  // checked with the page's network, every model of another design read "NOT compatible", although Use brings its own.
  const askedD = asked.slice(askedBeforeD).filter(a => a.run_dir === D.run_dir), checkD = askedD.find(a => a.withConfig);
  check('... a model of another design is checked with ITS network (RGCN), not the page\'s (Graph Transformer): its save point read first, as Use reads it (SIF-85)',
    !!askedD[0] && !askedD[0].withConfig && askedD[0].checkpoint_id === D.latest && sameNet(checkD?.network, RGCN) && checkD.mode === 'fine_tune'
    && checkD.source?.run_dir === D.run_dir && checkD.source?.checkpoint_id === D.latest && sameNet((await stored())?.network, NET), JSON.stringify(askedD));
  const NAME = `${RIGHT}.querySelector('input.model-rename')`, RENAME = `${RIGHT}.querySelector('button.model-rename-apply')`;
  const note = () => evaluate(`${RIGHT}.querySelector('.model-rename-note')?.textContent ?? ''`);
  check('its Details have a Name box with the model\'s name, and Rename is off while the name is unchanged', (await evaluate(`${NAME}?.value`)) === D.task_name && (await evaluate(`${RENAME}?.disabled`)) === true);
  await page.setValue(NAME, B.task_name, { event: 'input' });
  await evaluate(`${RENAME}.click()`);
  check('a name another model carries is refused, and said under the box', await until(`/exists already/.test(${RIGHT}.querySelector('.model-rename-note.warn')?.textContent ?? '')`, 40)
    && renames.length === 1 && renames[0].run_dir === D.run_dir, `${renames.length} request(s): ${await note()}`);
  const NEW_NAME = 'FIXTURE renamed (2)', listsBeforeRename = lists, runsBeforeRename = runReads;
  await page.setValue(NAME, `  ${NEW_NAME}  `, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  // Branch record SIF-102: a rename reads the page's run list again too; this run list does not carry the new name (as an older
  // server's), so the saved models are read here - once.
  check('a free name renames the model: the run list and the saved models are read again, the saved models once, and the row carries the new name',
    await until(`(${row(D)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(NEW_NAME)}`, 40)
    && (await readsReach(listsBeforeRename + 1)) === listsBeforeRename + 1 && runReads > runsBeforeRename && renames[1]?.model_label === NEW_NAME,
    `${lists - listsBeforeRename} read(s), the run list ${runReads - runsBeforeRename}`);
  check('... and the draft still holds the model in use (C)', (await stored())?.model_source?.run_dir === C.run_dir);
  await page.setValue(NAME, D.task_name, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  await until(`(${row(D)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(D.task_name)}`, 40);
  await shot('models-2-details.png');
  // Branch record SIF-102: the main page names the model in use by its run's row - its model line, the header's Next line - and
  // kept the old name beside "Renamed to ..." until something else read the runs. From here the run list carries the names
  // the renames gave, as the backend's does: its change reads the saved models again by itself, and the rename reads them no
  // second time.
  runsFollow = true;
  await details(C); await until(`!!(${pointRow(C.latest)})`, 30);
  const IN_USE_NAME = 'FIXTURE in use renamed', listsBeforeInUse = lists;
  const named = name => `(document.querySelector('.rl-networks-row .net-short')?.textContent ?? '').startsWith(${JSON.stringify(`Fine-tune ${name} · `)})
    && ((${NEXT})?.textContent ?? '').includes(${JSON.stringify(`Fine-tune from ${name} @ 10 `)})`;
  await page.setValue(NAME, IN_USE_NAME, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  check('renaming the model in use renames it on the main page: its model line and the header\'s Next line (SIF-102)', await until(named(IN_USE_NAME), 40),
    `${await line()} | ${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)}`);
  check('... and the saved models are read again once, by the run list that changed', await until(`(${row(C)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(IN_USE_NAME)}`, 40)
    && (await readsReach(listsBeforeInUse + 1)) === listsBeforeInUse + 1, `${lists - listsBeforeInUse} read(s)`);
  await page.setValue(NAME, C.task_name, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  check('... and back: its own name again, there too', await until(named(C.task_name), 40) && await until(`(${row(C)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(C.task_name)}`, 40),
    await line());
  // SIF-102 review follow-up: renamed elsewhere (another tab, say) and seen here by Refresh list only, so the page's run list
  // still holds the old name. Renamed back here, the run list read is the one held - kept as it is, so it changes nothing -
  // and the saved models were read by nobody: the row kept the other name beside "Renamed to ...".
  const ELSEWHERE = 'FIXTURE renamed elsewhere';
  served = served.map(x => x.run_dir === C.run_dir ? { ...x, model_label: ELSEWHERE } : x); labels[C.run_dir] = ELSEWHERE;
  await until(`!(${button('Refresh list')})?.disabled`, 40); await evaluate(`${button('Refresh list')}.click()`);
  await until(`(${row(C)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(ELSEWHERE)}`, 40);
  await until(`${NAME}?.value === ${JSON.stringify(ELSEWHERE)}`, 20);
  const listsBeforeBack = lists, runsBeforeBack = runReads;
  await page.setValue(NAME, C.task_name, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  check('... renamed back here after a rename elsewhere, the page\'s run list unchanged by its read: the saved models are still read again, once (SIF-102 review)',
    await until(`(${row(C)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(C.task_name)}`, 40)
    && (await readsReach(listsBeforeBack + 1)) === listsBeforeBack + 1 && runReads > runsBeforeBack, `${lists - listsBeforeBack} read(s), the run list ${runReads - runsBeforeBack}`);

  // ---- the models' folders (record 7.263) ------------------------------------------------------------------------------------------
  await networkPage.send('Page.enable');
  const replies = [];
  networkPage.on('Page.javascriptDialogOpening', () => networkPage.send('Page.handleJavaScriptDialog', replies.shift() ?? { accept: false }));
  replies.push({ accept: true, promptText: 'GT models' });
  await evaluate(`[...${RIGHT}.querySelectorAll('.task-folders button')].find(b => b.textContent.trim() === 'New folder').click()`);
  const gt = await (async () => { for (let i = 0; i < 40 && !Object.keys(modelFolders.folders).length; i++) await sleep(100); return Object.keys(modelFolders.folders)[0]; })();
  check('the saved models have folders of their own: New folder makes one', !!gt && modelFolders.folders[gt] === 'GT models'
    && await evaluate(`${RIGHT}.querySelector('.task-folders').getAttribute('aria-label')`) === 'Model folders');
  await evaluate(`${RIGHT}.querySelector('.task-folders [data-folder-id="all"]').click()`); await sleep(200);
  await evaluate(`(${row(A)}).querySelector('td.task-select input').click()`); await sleep(150);
  await evaluate(`(() => { const s = ${RIGHT}.querySelector('select[aria-label="Move selected models to folder"]'); s.value = ${JSON.stringify(gt)}; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  check('"Move to..." puts the ticked model in it, by run folder', await (async () => { for (let i = 0; i < 40 && !modelFolders.assignments[A.run_dir]; i++) await sleep(100); return modelFolders.assignments[A.run_dir] === gt; })()
    && await until(`${RIGHT}.querySelector('.task-folders [data-folder-id="${gt}"]')?.textContent === 'GT models1'`, 30), JSON.stringify(modelFolders.assignments));

  // ---- the window keeps its view between opens (branch record SIF-102) ---------------------------------------------------------------
  // It closes after every choice (record 7.291), and each reopen started at every folder, All designs, no filter, Last saved and
  // no Details, with no row until the whole list was read again: the filter was typed again and the read waited for at every open.
  await evaluate(`${RIGHT}.querySelector('.task-folders [data-folder-id="${gt}"]').click()`); await sleep(200);
  await page.setValue(DESIGN, 'Graph Transformer', { event: 'change' });
  await page.setValue(`${RIGHT}.querySelector('input.model-filter')`, 'opamp', { event: 'input' });
  await evaluate(`[...${RIGHT}.querySelector('table.model-table').tHead.rows[0].cells].find(c => c.textContent.startsWith('Evaluations')).click()`);
  await details(A); await until(`!!${RIGHT}.querySelector('table.model-points')`, 30);
  await evaluate(`(${row(A)}).querySelector('td.task-select input').click()`); await sleep(300);
  const VIEW = `(() => { const a = ${row(A)}, sorted = [...${RIGHT}.querySelector('table.model-table').tHead.rows[0].cells].find(c => c.getAttribute('aria-sort'));
    return { rows: ${ROWS}.map(r => r.title), folder: ${RIGHT}.querySelector('.task-folders [aria-current="page"]')?.dataset.folderId ?? null, design: (${DESIGN}).value,
      filter: ${RIGHT}.querySelector('input.model-filter').value, sort: sorted ? sorted.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim() + ' ' + sorted.getAttribute('aria-sort') : null,
      details: a?.querySelector('button.notes-link')?.getAttribute('aria-expanded') === 'true' && !!${RIGHT}.querySelector('table.model-points'),
      ticked: !!a?.querySelector('td.task-select input')?.checked, count: ${RIGHT}.querySelector('.model-count')?.textContent ?? '' }; })()`;
  const sameView = v => JSON.stringify(v.rows) === JSON.stringify([A.run_dir]) && v.folder === gt && v.design === 'Graph Transformer' && v.filter === 'opamp'
    && v.sort === 'Evaluations descending' && v.details;
  const viewSet = await evaluate(VIEW);
  check('(set-up) a view: the folder GT models, Graph Transformer, the filter "opamp", sorted by Evaluations, A\'s Details open and its row ticked',
    sameView(viewSet) && viewSet.ticked, JSON.stringify(viewSet));
  holdList = true; const listsBeforeReopen = lists;
  await networkPage.evaluate('window.close()'); await browser.window(RL_MODEL_WINDOW, { present: false });
  networkPage = await openNetworks(page, browser); await networkPage.viewport(1180, 920);
  for (let i = 0; i < 50 && !heldList.length; i++) await sleep(100);
  await until(`(${VIEW}).rows.length > 0`, 40);
  const viewKept = await evaluate(VIEW);
  check('opened again, the window keeps its view: the folder, the Design, the filter, the sort and the open Details; the tick goes (SIF-102)',
    sameView(viewKept) && !viewKept.ticked, JSON.stringify(viewKept));
  check('... its rows are those of the last read, shown at once, while its one read is still on its way (SIF-102)', heldList.length === 1 && lists === listsBeforeReopen + 1
    && /^Reading the saved models/.test(viewKept.count), `${lists - listsBeforeReopen} read(s), ${heldList.length} held: ${viewKept.count}`);
  holdList = false; await fulfil(heldList.shift(), 200, { models: served });
  await until(`!${READING}`, 40);
  const viewRead = await evaluate(VIEW);
  check('... and when it answers, the view stays, with no second read', sameView(viewRead) && (await readsReach(listsBeforeReopen + 1)) === listsBeforeReopen + 1,
    `${lists - listsBeforeReopen} read(s): ${JSON.stringify(viewRead)}`);
  // back to every folder, every design, no filter, Last saved and no Details (a folder chosen closes them), for what follows
  await evaluate(`${RIGHT}.querySelector('.task-folders [data-folder-id="all"]').click()`); await sleep(200);
  await page.setValue(DESIGN, '', { event: 'change' });
  await page.setValue(`${RIGHT}.querySelector('input.model-filter')`, '', { event: 'input' });
  await evaluate(`[...${RIGHT}.querySelector('table.model-table').tHead.rows[0].cells].find(c => c.textContent.startsWith('Last saved')).click()`); await sleep(300);

  // ---- filter, refresh, no timer -----------------------------------------------------------------------------------------------------
  await evaluate(`(() => { const i = ${RIGHT}.querySelector('input.model-filter'); i.focus(); i.select(); })()`); await networkPage.send('Input.insertText', { text: 'ldo gatv2' }); await sleep(300);
  check('the filter keeps the matching models', JSON.stringify((await rows()).map(r => r.dir)) === JSON.stringify([B.run_dir]), JSON.stringify((await rows()).map(r => r.cells[1])));
  await page.setValue(`${RIGHT}.querySelector('input.model-filter')`, '', { event: 'input' }); await sleep(300);
  check('clearing the filter shows all models again', (await rows()).length === MODELS.length);
  const before = lists; await sleep(2500);
  check('the list is not re-read on a timer', lists === before, `${lists - before} read(s) in 2.5 s`);
  await details(C); await until(`!!(${pointRow(C.latest)})`, 30);                              // its Details open as it leaves the list (SIF-102)
  served = MODELS.filter(m => m !== C);                                                       // the model in use loses its save points
  // Branch record SIF-113 (the icon audit): Refresh list is the refresh icon, as in the Runs and Tasks windows - its words for
  // screen readers and at the start of its tooltip, so "Press Refresh list to retry" still names it.
  const refreshList = await evaluate(`(() => { const b = ${button('Refresh list')}; return b && { icon: !!b.querySelector('svg.icon'), text: b.textContent,
    label: b.querySelector('.sr-only')?.textContent ?? null, title: b.title }; })()`);
  check('"Refresh list" is the refresh icon, its words for screen readers and at the start of its tooltip (SIF-113)', !!refreshList?.icon && refreshList.text === 'Refresh list'
    && refreshList.label === 'Refresh list' && refreshList.title === 'Refresh list: every run folder is read again from the disk.', JSON.stringify(refreshList));
  await evaluate(`${button('Refresh list')}.click()`);
  check('"Refresh list" reads the list exactly once', (await until(`${ROWS}.length === ${MODELS.length - 1}`, 40)) && lists === before + 1, `${lists - before} read(s)`);
  check('a model in use that left the list is said in plain words, with its folder', await until(`!!${RIGHT}.querySelector('.model-missing')`, 30)
    && (await evaluate(`${RIGHT}.querySelector('.model-missing').innerText`)).includes(C.run_dir));
  // Branch record SIF-64: a click on the folder copies it, and nothing said so.
  check('...the folder says that a click copies it (SIF-64)', (await evaluate(`${RIGHT}.querySelector('.model-missing .path')?.title`)) === 'Click to copy');
  const refusedFolder = await copiedFrom(`${RIGHT}.querySelector('.model-missing .path')`, C.run_dir, ' could not copy');
  check('...and a copy this window\'s clipboard refuses says "could not copy" there, the main page\'s untouched (SIF-94)', refusedFolder.said && refusedFolder.main === null
    && await until(`(${RIGHT}.querySelector('.model-missing .path'))?.textContent === ${JSON.stringify(C.run_dir)}`, 40), JSON.stringify(refusedFolder));
  served = []; await evaluate(`${button('Refresh list')}.click()`);
  check('no saved model: said in plain words, with what makes a run save one', await until(`/No saved model yet/.test(${RIGHT}.querySelector('.model-empty')?.innerText ?? '')`, 40));
  served = MODELS; await evaluate(`${button('Refresh list')}.click()`); await until(`${ROWS}.length === ${MODELS.length}`, 40);
  // Branch record SIF-102: the open Details are kept between opens, so those of a model that left the list are let go - they
  // opened by themselves when it was listed again.
  check('Details of a model that left the list close: listed again, its row\'s Details stay closed (SIF-102)',
    await evaluate(`(${row(C)})?.querySelector('button.notes-link')?.getAttribute('aria-expanded') === 'false' && !${RIGHT}.querySelector('tr.run-details-row')`));

  // ---- Run configuration's notice opens the window at its reason (branch record SIF-86) -----------------------------------------------
  // D in use and answered NOT compatible: the notice's reason is the compatibility under "The model in use", which sits under
  // the saved models table. The notice's "RL model..." opened the window at its top, and the reason had to be searched for.
  incompatibleD = true;
  await details(D); await until(`!!(${pointRow(D.latest)})`, 30); await usePoint(D.latest); await storedWhen(s => s?.model_source?.run_dir === D.run_dir);
  await closedByChoice();
  const NOTICE = `document.querySelector('p.network-review')`, COMPAT = `${NETWORK_DOCUMENT}.getElementById('net-compat')`;
  check('(set-up) with D NOT compatible, Run configuration\'s notice says so', await until(`${NOTICE}?.textContent === 'Review the settings in RL model... - the saved model is NOT compatible with this run.'`, 60),
    await evaluate(`${NOTICE}?.textContent ?? 'no notice'`));
  networkPage = await openNetworks(page, browser, 'p.network-review button.text-link');
  const placeOf = `(() => { const w = ${NETWORK_DOCUMENT}.defaultView, r = (${COMPAT})?.querySelector('summary').getBoundingClientRect();
    return { open: !!(${COMPAT})?.open, window: Math.round(w.scrollY), top: r ? Math.round(r.top) : null, bottom: r ? Math.round(r.bottom) : null, height: w.innerHeight }; })()`;
  check('the notice\'s "RL model..." opens the window at the compatibility: open, in view, under the saved models (SIF-86)',
    await until(`(() => { const at = ${placeOf}; return at.open && at.window > 0 && at.top !== null && at.top >= 0 && at.bottom <= at.height; })()`, 40), JSON.stringify(await evaluate(placeOf)));
  await networkPage.evaluate('window.close()'); await browser.window(RL_MODEL_WINDOW, { present: false });
  await reopen();
  check('... and the model line\'s "RL model..." opens it at its top, as before', await until(`!!(${COMPAT})`, 40) && (await evaluate(placeOf)).window === 0, JSON.stringify(await evaluate(placeOf)));
  // Branch record SIF-117: for one model this row read "6,024 learner updates" and the Training tab and Run status "6024":
  // the page writes every count from 10,000 up in groups of three, and plain below.
  const TRAINING_FACT = `([...${RIGHT}.querySelectorAll('table.model-facts tr')].find(r => r.cells[0].textContent === 'Training')?.cells[1].textContent ?? null)`;
  check('D\'s counters as the page writes counts: "40 evaluations, 6024 learner updates, 12,000 transitions in replay" (SIF-117)',
    await until(`${TRAINING_FACT} === '40 evaluations, 6024 learner updates, 12,000 transitions in replay'`, 40), await evaluate(TRAINING_FACT));
  incompatibleD = false;
  const beforeScratch = lists;
  await setMode(networkPage, 'scratch'); await sleep(500);
  run = await storedWhen(s => s?.mode === 'scratch');
  check('New model clears the saved model chosen, in the same step (scratch loads none)', run?.mode === 'scratch' && !run.model_source?.run_dir, JSON.stringify(run?.model_source));
  check('... and the note "The next run fine-tunes ..." about that model goes with it', !(await evaluate(`/The next run fine-tunes/.test(${RIGHT}.innerText)`)));
  check('... the templates are back, with the network last in use (rgcn, from the last model) as the template in use, and nothing is read',
    await until(`${RIGHT}.querySelector('tr.template-row.current')?.dataset.encoder === 'rgcn'`, 30) && lists === beforeScratch,
    await evaluate(`${RIGHT}.querySelector('tr.template-row.current')?.dataset.encoder ?? 'none'`));

  // ---- only the newest "Use this save point" lands (record 7.278, Astra's review of 2026-10-08; as Load run, 7.270) ---------------
  await setMode(networkPage, 'fine_tune'); await until(`${ROWS}.length === ${MODELS.length}`, 40);
  holdModel = early;
  await details(A); await until(`!!(${pointRow(early)})`, 30); await usePoint(early);                        // A's read is held back
  const held = async () => { for (let i = 0; i < 40 && !heldModel.length; i++) await sleep(100); return heldModel.length === 1; };
  check('(set-up) the first Use waits for its save point', await held());
  // Branch record SIF-85: the press showed nothing until the window closed.
  const USING = `(() => { const b = (${pointRow(early)})?.querySelector('button.model-use'), others = [...${RIGHT}.querySelectorAll('table.model-points button.model-use')].filter(x => x !== b);
    return { text: b?.textContent ?? null, off: !!b?.disabled, othersOn: others.length > 0 && others.every(x => !x.disabled) }; })()`;
  await until(`(${USING}).text === 'Using...'`, 30);
  const using = await evaluate(USING);
  check('... meanwhile its button says "Using...", and the other Use buttons stay on: a newer choice wins (SIF-85)', using.text === 'Using...' && using.off && using.othersOn, JSON.stringify(using));
  holdModel = null;
  await evaluate(`(${row(B)}).querySelector('td:nth-child(4)').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  run = await storedWhen(s => s?.model_source?.run_dir === B.run_dir);
  check('a second choice meanwhile lands: B, its newest save point, with its network', run?.model_source?.run_dir === B.run_dir && run.model_source.checkpoint_id === B.latest && sameNet(run.network, GATV2), JSON.stringify(run?.model_source));
  check('... and it closes the window', await chosenAndReopened());
  let late = heldModel.shift(); await fulfil(late.requestId, 200, describe(late.body.run_dir, late.body.checkpoint_id)); await sleep(800);
  run = await stored();
  check('... and the first, answered late, changes nothing: B and its network stay, the note names B', run?.model_source?.run_dir === B.run_dir && run.model_source.checkpoint_id === B.latest && sameNet(run.network, GATV2)
    && /fine-tunes FIXTURE_ldo_gat from its save point/.test(await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? ''`)),
    `${JSON.stringify(run?.model_source)} | ${await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no note'`)}`);
  holdModel = early;
  await details(A); await until(`!!(${pointRow(early)})`, 30); await usePoint(early);                        // held back again
  check('(set-up) a Use waits for its save point while New model is chosen', await held());
  await setMode(networkPage, 'scratch');
  run = await storedWhen(s => s?.mode === 'scratch');
  holdModel = null; late = heldModel.shift(); await fulfil(late.requestId, 200, describe(late.body.run_dir, late.body.checkpoint_id)); await sleep(800);
  run = await stored();
  check('New model while a Use is on its way lets it go: New model, no saved model, the network as it was, no note', run?.mode === 'scratch' && !run.model_source?.run_dir && sameNet(run.network, GATV2)
    && !(await evaluate(`/The next run fine-tunes/.test(${RIGHT}.innerText)`)), `${JSON.stringify(run?.model_source)} ${JSON.stringify(run?.network)}`);
  check('... and the window stays open: no model was chosen', !(await evaluate(`window.__checkRLWindow.closed`)));

  // ---- Evaluate only's own setting (branch record SIF-53: it read "Frozen actions [deterministic]", the Mode's key, and said
  // nothing of what the choice does); New model again after, so the real route below is read on its own switch -----------
  await setMode(networkPage, 'frozen');
  const ACTIONS = `[...${RIGHT}.querySelectorAll('h3')].find(h => h.textContent === 'Evaluate only: its own settings')?.nextElementSibling`;
  const actions = await until(`(${ACTIONS})?.tagName === 'LABEL'`, 40) ? await evaluate(`(() => { const l = ${ACTIONS}, s = l.querySelector('select');
    return { label: l.firstChild.textContent, title: l.title, value: s.value, options: [...s.options].map(o => [o.value, o.textContent]) }; })()`) : null;
  check('Evaluate only\'s own setting reads "Actions", says on hover what each choice does, and offers Deterministic and Sampled, stored as before (SIF-53)',
    actions?.label === 'Actions' && /^Deterministic: each step takes the policy's mean action/.test(actions.title) && /Sampled: each step draws an action from the policy/.test(actions.title)
    && actions.value === 'deterministic' && JSON.stringify(actions.options) === JSON.stringify([['deterministic', 'Deterministic'], ['sampled', 'Sampled']]), JSON.stringify(actions));
  await setMode(networkPage, 'scratch');

  // ---- the REAL route of this backend ---------------------------------------------------------------------------------------------------
  const real = await fetch(new URL('api/runs/models' + (ROOT ? `?output_root=${encodeURIComponent(ROOT)}` : ''), APP));
  if (real.status === 404) console.log('SKIP  the real /api/runs/models route: this backend is older than the chooser - restart it');
  else {
    const expected = (await real.json()).models;
    canned = false; await setMode(networkPage, 'frozen');
    // This scans the growing on-disk model library (about 10 s on D:), unlike the fixtures above.
    const ok = await until(`${ROWS}.length === ${expected.length} && !/Reading the saved models/.test(${RIGHT}.innerText)`, 300);
    check(`against the real route: ${expected.length} saved model(s) on this backend, ${expected.length} row(s)`, ok, `${(await rows()).length} row(s)`);
    check('... each row carries its run folder, newest save first', JSON.stringify((await rows()).map(r => r.dir)) === JSON.stringify(expected.map(m => m.run_dir)));
    await shot('models-3-real.png');
  }

  reportRefused(refused, NEVER_ASKED_OR_SAVED);
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
