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
//   Undo step; a double click on a row uses its newest save point; a newer save point is offered, never followed;
// - a network that arrives from elsewhere while a model is loaded is taken back, and that is said;
// - an incomplete configuration is a calm note; rename refuses a taken name; the filter; one read per Refresh, no timer;
//   a model in use that left the list; an empty folder; the models' folders; back to New model; the real route.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 25 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/model_chooser_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { NETWORK_DOCUMENT, NETWORK_PANEL, openNetworks, setMode } from './lib/rl_networks.mjs';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { check, launchEdge, mockStarter, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, validConfiguration, workbenchUrl } from './lib/harness.mjs';

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
const A = model('FIXTURE_opamp_gt', 'synthetic:gpdk045_ota5', [point('a1', 6, 'periodic', 1), point('a2', 12, 'periodic', 2), point('a3', 18, 'periodic', 3), point('a4', 20, 'final', 4, { is_latest: true })]);
const B = model('FIXTURE_ldo_gat', 'synthetic:ldo', [point('b1', 8, 'stop', 5, { is_latest: true, network: GATV2 })]);
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
    vocabulary: { name: 'standard', label: 'standard (8 generic kinds)', pdk_id: null, sha256: null, loaded: true },
    compatibility: { mode: 'fine_tune', compatible: true, checks: [{ component: 'FIXTURE check', status: 'ok', detail: 'identical' }], checkpoint_id: p.checkpoint_id, source_run_id: m.run_id,
      restoration_capability: p.restoration_capability, suggestion: null }, suggestion: null };
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
  let holdModel = false; const heldModel = [];                                     // record 7.278: a "Use" read held back, answered late
  let failModel = null;                                                            // record 7.291: a "Use" whose save point cannot be read
  const modelFolders = { version: 1, folders: {}, assignments: {} }; let folderSerial = 0;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: RUNS });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/models') { lists++; return canned ? fulfil(requestId, 200, { models: served }) : send('Fetch.continueRequest', { requestId }); }
    if (name === '/api/runs/model') {
      if (!canned) return send('Fetch.continueRequest', { requestId });
      const body = JSON.parse(request.postData ?? '{}'); asked.push({ run_dir: body.run_dir, checkpoint_id: body.checkpoint_id, network: body.config?.run?.network ?? null, withConfig: !!body.config });
      if (holdModel && !body.config) { heldModel.push({ requestId, body }); return; }
      if (failModel && failModel === body.run_dir && !body.config) return fulfil(requestId, 503, { detail: 'FIXTURE: the server is busy' });
      const found = describe(body.run_dir, body.checkpoint_id);
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
      const previous = mine.model_label ?? mine.task_name; served = served.map(x => x === mine ? { ...x, model_label: body.model_label } : x);
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
  const reopen = async () => {
    networkPage = await openNetworks(page, browser); await networkPage.viewport(1180, 920);
    return until(`${ROWS}.length === ${MODELS.length} || !${RIGHT}.querySelector('.saved-models')`, 60);
  };
  const chosenAndReopened = async () => { const closed = await closedByChoice(); await reopen(); return closed; };

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
  await sleep(1100);
  check('... and looking changed NOTHING in the draft: New model, no saved model chosen', (await stored())?.mode === 'scratch' && !(await stored())?.model_source?.run_dir,
    JSON.stringify((await stored())?.model_source));

  // ---- Fine-tune: the table, nothing filled in by itself --------------------------------------------------------------
  const listsBefore = lists;
  await setMode(networkPage, 'fine_tune');
  check('Fine-tune reads the list once and shows a saved models table', (await until(`${ROWS}.length === ${MODELS.length}`, 50)) && lists === listsBefore + 1, `${lists - listsBefore} read(s)`);
  check('... no block for a new network: no templates, no "The ... template" settings, no "where the values come from"',
    await evaluate(`!${RIGHT}.querySelector('table.template-table') && ![...${RIGHT}.querySelectorAll('h3')].some(h => / template, for this run$/.test(h.textContent)) && ![...${RIGHT}.querySelectorAll('summary')].some(s => /^Where the .+ values come from$/.test(s.textContent.trim()))`));
  check('... the Advanced numbers and Fine-tune\'s own settings are there', await evaluate(`[...${RIGHT}.querySelectorAll('summary')].some(s => /^Advanced/.test(s.textContent.trim()))
    && [...${RIGHT}.querySelectorAll('label.check')].some(l => l.textContent === 'Freeze encoder') && !!${RIGHT}.querySelector('input.model-label')`));
  check('... "no saved model chosen yet" is said, and none was filled in by itself (record 7.265)', await evaluate(`!!${RIGHT}.querySelector('.model-none-chosen')`)
    && !(await storedWhen(s => s?.mode === 'fine_tune'))?.model_source?.run_dir && /^Fine-tune · no saved model chosen/.test(await line()), await line());
  check('the columns: name, trained on, network, evaluations, save points, last saved, started from, data, restorable', JSON.stringify((await heads()).slice(1, 10))
    === JSON.stringify(['Name', 'Trained on', 'Network', 'Evaluations', 'Save points', 'Last saved', 'Started from', 'Data', 'Restorable']), JSON.stringify(await heads()));
  let shown = await rows();
  check('one row per saved model, most recently saved first', shown.length === MODELS.length && shown.map(r => r.dir).join() === MODELS.map(m => m.run_dir).join(), shown.map(r => r.cells[1]).join(' | '));
  const cellsOf = m => shown.find(r => r.dir === m.run_dir).cells;
  check('a row names the model, its task, ITS network (in short, as the model line writes it), its evaluations and save points', cellsOf(A)[1] === A.task_name
    && cellsOf(A)[2] === 'synthetic:gpdk045_ota5' && cellsOf(A)[3] === 'GT 16/2/1' && cellsOf(A)[4] === '20' && cellsOf(A)[5] === '4' && cellsOf(B)[3] === 'GATv2 16/2/1'
    && await evaluate(`(${row(B)}).querySelector('td.model-net').title`) === 'gatv2 16/2/1', JSON.stringify(cellsOf(A)));
  check('MOCK models are tagged, the real one is not; a model saved without its replay restores "weights only"', cellsOf(A)[8] === 'MOCK' && cellsOf(D)[8] === 'real'
    && cellsOf(C)[9] === 'weights only' && cellsOf(A)[9] === 'full state', JSON.stringify([cellsOf(A)[8], cellsOf(D)[8], cellsOf(C)[9]]));
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
  check('... its compatibility with the task on the page is checked for its newest save point - an inspection', await until(`/Compatible for fine_tune/.test(${RIGHT}.querySelector('details.model-compatibility')?.textContent ?? '')`, 40)
    && asked.slice(askedBefore).some(a => a.run_dir === A.run_dir && a.checkpoint_id === A.latest && a.withConfig), JSON.stringify(asked.slice(askedBefore)));
  await sleep(1100);
  check('... and opening Details changed nothing in the draft', !(await stored())?.model_source?.run_dir);

  // ---- Use this save point: pinned, with its network, one Undo step -----------------------------------------------------
  const early = A.checkpoints[0].checkpoint_id;
  await usePoint(early);
  let run = await storedWhen(s => s?.model_source?.checkpoint_id === early);
  check('"Use this save point" pins exactly that save point - a concrete id, never "latest"', run?.model_source?.run_dir === A.run_dir && run.model_source.checkpoint_id === early, JSON.stringify(run?.model_source));
  check('... and closes the RL model window (record 7.291)', await chosenAndReopened());
  check('... and says so, with the one Undo step', /^The next run fine-tunes FIXTURE_opamp_gt from its save point ckpt-00000006-a1, with its network \(one Undo step takes it back\)\.$/.test(await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? ''`)),
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no note'`));
  check('... with the model\'s network, in the same step', sameNet(run?.network, NET), JSON.stringify(run?.network));
  check('... the row says "in use", and the model line names it with its save point', await until(`(${row(A)})?.getAttribute('aria-current') === 'true' && !!(${row(A)}).querySelector('.in-use-tag')`, 30)
    && await until(`/^Fine-tune FIXTURE_opamp_gt · save point 6 evaluations$/.test(document.querySelector('.rl-networks-row .net-short')?.textContent ?? '')`, 30), await line());
  check('... and so does the header\'s Next line, and Start\'s tooltip with it', await until(`/^Next: synthetic:gpdk045_ota5 · Fine-tune from FIXTURE_opamp_gt @ 6 · GT 16\\/2\\/1 · \\d+ evaluations$/.test((${NEXT})?.textContent ?? '')`, 30)
    && (await startTitle()).startsWith(`Start: ${await evaluate(`(${NEXT}).textContent`)}. `), `${await evaluate(`(${NEXT})?.textContent ?? 'no line'`)} | ${await startTitle()}`);
  check('... a newer save point is offered, never followed', await until(`/has a newer save point: 20 evaluations/.test(${RIGHT}.querySelector('.model-newer')?.textContent ?? '')`, 30)
    && (await stored())?.model_source?.checkpoint_id === early);
  await undo();
  run = await storedWhen(s => !s?.model_source?.run_dir);
  check('one Undo takes the choice back', !run?.model_source?.run_dir, JSON.stringify(run?.model_source));
  await evaluate(`document.querySelector('section.editors button[title^="Redo:"]').click()`);
  run = await storedWhen(s => s?.model_source?.checkpoint_id === early);
  check('... and Redo brings it again', run?.model_source?.checkpoint_id === early);
  await evaluate(`${RIGHT}.querySelector('button.model-use-newer').click()`);
  run = await storedWhen(s => s?.model_source?.checkpoint_id === A.latest);
  check('"Use the newer one" pins the newer save point, and closes the window', run?.model_source?.checkpoint_id === A.latest && await chosenAndReopened()
    && !(await evaluate(`!!${RIGHT}.querySelector('.model-newer')`)), JSON.stringify(run?.model_source));

  // ---- a double click uses a row's newest save point; another network comes in the same step -----------------------------------
  await evaluate(`(${row(B)}).querySelector('td:nth-child(4)').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  run = await storedWhen(s => s?.model_source?.run_dir === B.run_dir);
  check('a double click on a row uses its newest save point, pinned', run?.model_source?.run_dir === B.run_dir && run.model_source.checkpoint_id === B.latest, JSON.stringify(run?.model_source));
  check('... and its network (gatv2) is the run\'s at once - nothing follows later by itself', sameNet(run?.network, GATV2), JSON.stringify(run?.network));
  check('... and the double click closes the window too', await chosenAndReopened());
  check('the model in use is described under the table: its network, and that the run uses it as it is', await until(`/^Network\\s+gatv2, hidden 16, heads 2, layers 1 - this run uses it as it is/.test(${RIGHT}.querySelector('tr.model-network')?.innerText ?? '')`, 40),
    await evaluate(`${RIGHT}.querySelector('tr.model-network')?.innerText ?? 'no row'`));
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
  check('a network from elsewhere is taken back while the model is loaded, and that is SAID', await until(`/The network stays gatv2 16\\/2\\/1: this run loads a saved model/.test(${RIGHT}.querySelector('.net-message.warn')?.textContent ?? '')`, 60),
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no message'`));
  check('... the configuration holds the model\'s network again', sameNet((await storedWhen(s => sameNet(s?.network, GATV2)))?.network, GATV2));

  // ---- a save point that cannot be read: said in the window, which stays open (record 7.291) ------------------------------------
  failModel = A.run_dir;
  await details(A); await until(`!!(${pointRow(early)})`, 30); await usePoint(early);
  check('a save point that cannot be read is said, and the RL model window stays open: nothing was chosen',
    await until(`/That save point could not be read/.test(${RIGHT}.querySelector('.net-message.error')?.textContent ?? '')`, 40)
    && !(await evaluate(`window.__checkRLWindow.closed`)) && (await stored())?.model_source?.run_dir === B.run_dir,
    await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no note'`));
  failModel = null;

  // ---- an incomplete configuration never hides the saved model -------------------------------------------------------------
  await details(C); await until(`!!(${pointRow(C.latest)})`, 30); await usePoint(C.latest);
  await storedWhen(s => s?.model_source?.run_dir === C.run_dir);
  await chosenAndReopened();
  check('an incomplete configuration is said in plain words, as a calm note - not as a red error', await until(`!!${RIGHT}.querySelector('.compat-unchecked')`, 40)
    && /Parameter row "mp1_w" is set to be optimized but has no lower and no upper bound/.test(await evaluate(`${RIGHT}.querySelector('.compat-unchecked').innerText`))
    && !(await evaluate(`[...${RIGHT}.querySelectorAll('p.error')].some(p => /CompileError|bounds are required/.test(p.textContent))`)));
  check('... the model in use is still described in full', await until(`/10 evaluations, 6 updates/.test(${RIGHT}.innerText)`, 40));
  check('... and the developer text is folded away under "Technical details"', await evaluate(`(() => { const d = ${RIGHT}.querySelector('.compat-unchecked details'); return !d.open && d.querySelector('summary').textContent === 'Technical details' && /CompileError: mp1_w/.test(d.textContent); })()`));

  // ---- a best policy is marked where one exists; rename (record 7.225) --------------------------------------------------------------
  await details(D);
  check('a run with a selected best policy marks that save point', await until(`/best policy/.test((${pointRow(D.checkpoints[0].checkpoint_id)})?.innerText ?? '')`, 30));
  const NAME = `${RIGHT}.querySelector('input.model-rename')`, RENAME = `${RIGHT}.querySelector('button.model-rename-apply')`;
  const note = () => evaluate(`${RIGHT}.querySelector('.model-rename-note')?.textContent ?? ''`);
  check('its Details have a Name box with the model\'s name, and Rename is off while the name is unchanged', (await evaluate(`${NAME}?.value`)) === D.task_name && (await evaluate(`${RENAME}?.disabled`)) === true);
  await page.setValue(NAME, B.task_name, { event: 'input' });
  await evaluate(`${RENAME}.click()`);
  check('a name another model carries is refused, and said under the box', await until(`/exists already/.test(${RIGHT}.querySelector('.model-rename-note.warn')?.textContent ?? '')`, 40)
    && renames.length === 1 && renames[0].run_dir === D.run_dir, `${renames.length} request(s): ${await note()}`);
  const NEW_NAME = 'FIXTURE renamed (2)', listsBeforeRename = lists;
  await page.setValue(NAME, `  ${NEW_NAME}  `, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  check('a free name renames the model: the list is read again once and the row carries the new name', await until(`(${row(D)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(NEW_NAME)}`, 40)
    && lists === listsBeforeRename + 1 && renames[1]?.model_label === NEW_NAME, `${lists - listsBeforeRename} read(s)`);
  check('... and the draft still holds the model in use (C)', (await stored())?.model_source?.run_dir === C.run_dir);
  await page.setValue(NAME, D.task_name, { event: 'input' }); await evaluate(`${RENAME}.click()`);
  await until(`(${row(D)})?.querySelector('td:nth-child(2) b')?.textContent === ${JSON.stringify(D.task_name)}`, 40);
  await shot('models-2-details.png');

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

  // ---- filter, refresh, no timer -----------------------------------------------------------------------------------------------------
  await evaluate(`(() => { const i = ${RIGHT}.querySelector('input.model-filter'); i.focus(); i.select(); })()`); await networkPage.send('Input.insertText', { text: 'ldo gatv2' }); await sleep(300);
  check('the filter keeps the matching models', JSON.stringify((await rows()).map(r => r.dir)) === JSON.stringify([B.run_dir]), JSON.stringify((await rows()).map(r => r.cells[1])));
  await page.setValue(`${RIGHT}.querySelector('input.model-filter')`, '', { event: 'input' }); await sleep(300);
  check('clearing the filter shows all models again', (await rows()).length === MODELS.length);
  const before = lists; await sleep(2500);
  check('the list is not re-read on a timer', lists === before, `${lists - before} read(s) in 2.5 s`);
  served = MODELS.filter(m => m !== C);                                                       // the model in use loses its save points
  await evaluate(`${button('Refresh list')}.click()`);
  check('"Refresh list" reads the list exactly once', (await until(`${ROWS}.length === ${MODELS.length - 1}`, 40)) && lists === before + 1, `${lists - before} read(s)`);
  check('a model in use that left the list is said in plain words, with its folder', await until(`!!${RIGHT}.querySelector('.model-missing')`, 30)
    && (await evaluate(`${RIGHT}.querySelector('.model-missing').innerText`)).includes(C.run_dir));
  served = []; await evaluate(`${button('Refresh list')}.click()`);
  check('no saved model: said in plain words, with what makes a run save one', await until(`/No saved model yet/.test(${RIGHT}.querySelector('.model-empty')?.innerText ?? '')`, 40));
  served = MODELS; await evaluate(`${button('Refresh list')}.click()`); await until(`${ROWS}.length === ${MODELS.length}`, 40);

  // ---- back to New model ------------------------------------------------------------------------------------------------------------
  await details(D); await until(`!!(${pointRow(D.latest)})`, 30); await usePoint(D.latest); await storedWhen(s => s?.model_source?.run_dir === D.run_dir);
  await chosenAndReopened();
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
  holdModel = true;
  await details(A); await until(`!!(${pointRow(early)})`, 30); await usePoint(early);                        // A's read is held back
  const held = async () => { for (let i = 0; i < 40 && !heldModel.length; i++) await sleep(100); return heldModel.length === 1; };
  check('(set-up) the first Use waits for its save point', await held());
  holdModel = false;
  await evaluate(`(${row(B)}).querySelector('td:nth-child(4)').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  run = await storedWhen(s => s?.model_source?.run_dir === B.run_dir);
  check('a second choice meanwhile lands: B, its newest save point, with its network', run?.model_source?.run_dir === B.run_dir && run.model_source.checkpoint_id === B.latest && sameNet(run.network, GATV2), JSON.stringify(run?.model_source));
  check('... and it closes the window', await chosenAndReopened());
  let late = heldModel.shift(); await fulfil(late.requestId, 200, describe(late.body.run_dir, late.body.checkpoint_id)); await sleep(800);
  run = await stored();
  check('... and the first, answered late, changes nothing: B and its network stay, the note names B', run?.model_source?.run_dir === B.run_dir && run.model_source.checkpoint_id === B.latest && sameNet(run.network, GATV2)
    && /fine-tunes FIXTURE_ldo_gat from its save point/.test(await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? ''`)),
    `${JSON.stringify(run?.model_source)} | ${await evaluate(`${RIGHT}.querySelector('.net-message')?.textContent ?? 'no note'`)}`);
  holdModel = true;
  await details(A); await until(`!!(${pointRow(early)})`, 30); await usePoint(early);                        // held back again
  check('(set-up) a Use waits for its save point while New model is chosen', await held());
  await setMode(networkPage, 'scratch');
  run = await storedWhen(s => s?.mode === 'scratch');
  holdModel = false; late = heldModel.shift(); await fulfil(late.requestId, 200, describe(late.body.run_dir, late.body.checkpoint_id)); await sleep(800);
  run = await stored();
  check('New model while a Use is on its way lets it go: New model, no saved model, the network as it was, no note', run?.mode === 'scratch' && !run.model_source?.run_dir && sameNet(run.network, GATV2)
    && !(await evaluate(`/The next run fine-tunes/.test(${RIGHT}.innerText)`)), `${JSON.stringify(run?.model_source)} ${JSON.stringify(run?.network)}`);
  check('... and the window stays open: no model was chosen', !(await evaluate(`window.__checkRLWindow.closed`)));

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
