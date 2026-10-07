// Browser check of the run panel's Mode suggestion ("Suggested: fine_tune - ..."). User request 2026-09-26: "remove the
// Use button but make fine_tune clickable" - the suggested mode is the control itself, drawn as a link in its sentence.
// Record 7.265: the Mode is chosen in the RL model window, so the panel names it in its model line ("Evaluate ...",
// "Fine-tune ..."), and the suggestion names it in words ("Fine-tune"). Record 7.267: a configuration that still says resume
// (saved before 7.265, or imported) has no Mode chosen: it is said, with the run it continued, and nothing starts until one is.
// Hermetic, on the shared harness (lib/harness.mjs): /api/runs/model and /api/runs/models are answered with canned data
// labelled FIXTURE (a model trained on another task, so the backend's fine_tune suggestion applies), GET requests pass,
// every other writing request is refused. Safe against the live page on 8765. The browser profile is new and temporary.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 15 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/mode_suggestion_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { validConfiguration, check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('modesugg');

// ---- canned answers ------------------------------------------------------------------------------------------
const NET = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 1 };
const RUN_DIR = '/fixture/outputs/mock/fx__1/runs/FIXTURE_other_task/scratch_seed1__r1';
const POINT = { checkpoint_id: 'ckpt-00000020-a4', kind: 'final', created_utc: '2026-09-21T10:04:00+00:00', mode: 'scratch', evaluations: 20,
  learner_updates: 16, replay_size: 20, restoration_capability: 'full_state', missing_components: [], network: NET, is_latest: true, is_best_policy: false };
const MODEL = { run_dir: RUN_DIR, run_id: 'run-FIXTURE_other_task', task_id: 'FIXTURE_other_task:0123456789abcdef', task_name: 'FIXTURE_other_task',
  task_definition_hash: 'f'.repeat(64), mode: 'scratch', mock: true, seed: 1, created_utc: '2026-09-21T10:00:00+00:00', state: 'completed', experiment: 'fx__1',
  evaluations: 20, circuit_task: 'synthetic:ldo', circuit_class: 'ldo', latest: POINT.checkpoint_id,
  best_policy: { selected: null, status: 'not_selected', reason: 'FIXTURE: no validation-set policy evaluation has occurred in this run', score: null },
  checkpoints: [POINT], network: NET, saved_utc: POINT.created_utc, trained_evaluations: 20, learner_updates: 16, restoration_capability: 'full_state' };
// The backend's own words for a model of another task (runs.py suggest_mode).
const SUGGESTION = { mode: 'fine_tune', requires_confirmation: true,
  reason: 'The model was trained on a different task. Loading it is a transfer: a new run is created and the source recorded as its parent.' };
const DESCRIBED = { description: { checkpoint_id: POINT.checkpoint_id, path: `${RUN_DIR}/checkpoints/${POINT.checkpoint_id}`, kind: POINT.kind,
    source_run_id: MODEL.run_id, source_task_id: MODEL.task_id, mode: 'scratch', created_utc: POINT.created_utc, metadata_version: 'FIXTURE',
    counters: { evaluations_committed: 20, learner_updates: 16, replay_size: 20 }, restoration_capability: 'full_state', restorable_components: [],
    missing_components: [], contract: { model_config: NET, sac_config: {} }, file_problems: [] },
  compatibility: { mode: 'frozen', compatible: true, checks: [{ component: 'FIXTURE check', status: 'ok', detail: 'identical' }], checkpoint_id: POINT.checkpoint_id,
    source_run_id: MODEL.run_id, restoration_capability: 'full_state', suggestion: SUGGESTION }, suggestion: SUGGESTION };

await runChecks(browser, async () => {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  // Mode frozen with that model chosen: the suggestion (fine_tune) differs from the Mode, so it is shown.
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'frozen', network: NET, model_source: { run_dir: RUN_DIR, checkpoint_id: 'latest' } },
    output: { experiment_name: 'fixture' }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; let described = 0;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, validConfiguration());
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: [] });            // no run to take over: the header is free at once
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [MODEL] });
    if (name === '/api/runs/model') { described++; return fulfil(requestId, 200, DESCRIBED); }
    if (name === '/api/config/diff') return page.pass(requestId);                      // the diff is a pure comparison: nothing is written
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const RIGHT = `document.querySelector('.right')`;
  const MODE = `${RIGHT}?.querySelector('.rl-networks-row')`;                       // the next run's model, in one line (record 7.265)
  const LINE = `(${MODE})?.querySelector('.net-short')?.textContent ?? ''`;
  const PARA = `[...(${RIGHT}?.querySelectorAll('p.warn') ?? [])].find(p => p.textContent.startsWith('Suggested:'))`;
  const WORD = `(${PARA})?.querySelector('button')`;
  const USE = `[...document.querySelectorAll('button')].filter(b => b.textContent.trim() === 'Use').length`;
  // One picture of the Mode list and the sentence under it.
  const around = (a, b) => evaluate(`(() => { const r1 = (${a}).getBoundingClientRect(), r2 = (${b}).getBoundingClientRect();
    const x = Math.min(r1.x, r2.x) - 8, y = Math.min(r1.y, r2.y) - 8;
    return { x, y, width: Math.max(r1.right, r2.right) - x + 8, height: Math.max(r1.bottom, r2.bottom) - y + 8, scale: 2 }; })()`);
  const centre = expression => evaluate(`(() => { const r = (${expression}).getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);

  await page.intercept(['*/api/*'], answer);
  await page.trackSaves();
  await page.seed({ config: CONFIG, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await page.until(`!!(${MODE})`, 150))) throw new Error('the run panel never appeared; the page reads: '
    + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- the sentence, and what is (not) in it ----------------------------------------------------------------------
  check('Mode frozen with a model of another task chosen: the backend is asked about the model, and its suggestion is shown',
    (await page.until(`!!(${PARA})`, 80)) && described >= 1, `${described} request(s); ${JSON.stringify(await evaluate(`${RIGHT}?.innerText.slice(0, 200)`))}`);
  await evaluate(`(${PARA})?.scrollIntoView({ block: 'center' })`);
  const text = await evaluate(`(${PARA})?.textContent`);
  check('it reads "Suggested: fine_tune - <the backend\'s reason> (needs your confirmation)"',
    text === `Suggested: Fine-tune - ${SUGGESTION.reason} (needs your confirmation)`, JSON.stringify(text));
  check('there is no "Use" button any more, anywhere on the page', (await evaluate(USE)) === 0, `${await evaluate(USE)} found`);
  const word = await evaluate(`(() => { const b = ${WORD}; if (!b) return null; const cs = getComputedStyle(b), ps = getComputedStyle(b.parentElement);
    return { tag: b.tagName, text: b.textContent, title: b.title, cursor: cs.cursor, size: cs.fontSize, paraSize: ps.fontSize, weight: cs.fontWeight, color: cs.color,
      border: cs.borderStyle, background: cs.backgroundColor, underline: cs.textDecorationLine, visible: b.checkVisibility(), disabled: b.disabled,
      accent: (name => { const s = document.createElement('span'); s.style.color = 'var(' + name + ')'; document.body.appendChild(s); const c = getComputedStyle(s).color; s.remove(); return c; })('--accent') }; })()`);   // the look's accent (record 7.158)
  check('the suggested mode itself is the control: a button holding just its name, Fine-tune, visible and enabled',
    word?.tag === 'BUTTON' && word.text === 'Fine-tune' && word.visible && !word.disabled && word.cursor === 'pointer', JSON.stringify(word));
  check('... titled with what a click does', word?.title === 'Set Mode to Fine-tune', JSON.stringify(word?.title));
  check('... drawn as a link, not a box: no border, no background, bold, accent colour, at the size of its sentence',
    !!word && word.border === 'none' && word.background === 'rgba(0, 0, 0, 0)' && Number(word.weight) >= 600 && word.color === word.accent && word.size === word.paraSize, JSON.stringify(word));
  check('... not underlined until the mouse is over it', word?.underline === 'none', word?.underline);
  await page.shot(path.join(out, 'mode-suggestion-1-shown.png'), await around(MODE, PARA));
  const at = await centre(WORD);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: at.x, y: at.y }); await sleep(150);
  check('under the mouse it is underlined, like the other text links of the workbench', (await evaluate(`getComputedStyle(${WORD}).textDecorationLine`)) === 'underline');
  await page.shot(path.join(out, 'mode-suggestion-2-hover.png'), await around(MODE, PARA));

  // ---- the click --------------------------------------------------------------------------------------------------
  const before = (await page.stored())?.run?.mode;
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: at.x, y: at.y, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: at.x, y: at.y, button: 'left', clickCount: 1 });
  check('a click on the word sets Mode to Fine-tune: the model line says so', before === 'frozen' && await page.until(`(${LINE}).startsWith('Fine-tune ')`, 30), `${before} -> ${await evaluate(LINE)}`);
  check('... and the sentence goes away: the suggestion is the Mode now', await page.until(`!(${PARA})`, 30));
  await page.saved();
  check('... saved in the configuration like any other edit', (await page.stored())?.run?.mode === 'fine_tune', JSON.stringify((await page.stored())?.run?.mode));
  check('... with the chosen model kept', (await page.stored())?.run?.model_source?.run_dir === RUN_DIR, JSON.stringify((await page.stored())?.run?.model_source));
  await page.shot(path.join(out, 'mode-suggestion-3-after.png'), MODE, { scale: 2, pad: 8 });

  // ---- a configuration that still says resume (record 7.267; plan "The draft": "An old saved draft with mode: resume") ----------
  await page.saved();
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify({ ...CONFIG, run: { ...CONFIG.run, mode: 'resume' } }))})`);
  await send('Page.reload');
  check('a configuration that still says resume: the model line says no Mode is chosen', await page.until(`(${LINE}) === 'No Mode chosen: choose one in RL model... (this configuration still says resume)'`, 150), await evaluate(LINE));
  const NOTE = `${RIGHT}.querySelector('p.no-mode')`;
  const noteText = () => evaluate(`(${NOTE})?.textContent.replace(/\\s+/g, ' ').trim() ?? ''`);
  check('... Run configuration says so, naming the run it continued as a link into the Runs window', await page.until(`!!(${NOTE})?.querySelector('button.no-mode-run')`, 30)
    && (await noteText()) === 'No Mode is chosen: this configuration still says resume, which is no longer a choice - it continued the run scratch_seed1__r1. Choose a Mode in RL model... for the next run: Start waits until then.', await noteText());
  const HEADER = label => `[...document.querySelectorAll('header button')].find(b => b.textContent.trim() === ${JSON.stringify(label)})`;
  check('... the header\'s Next line says so too (record 7.269)', await page.until(`/^Next: synthetic:gpdk045_ota5 · no Mode chosen · GT 16\\/2\\/1 · \\d+ evaluations$/.test(document.querySelector('header span.next-run')?.textContent ?? '')`, 60),
    await evaluate(`document.querySelector('header span.next-run')?.textContent ?? 'no line'`));
  check('... Start waits, and says why: never a silent New model or Fine-tune', await page.until(`(${HEADER('Start')})?.disabled === true && /^Start: Next: .+\\. Choose a Mode in the RL model window first/.test((${HEADER('Start')}).title)`, 60)
    && await evaluate(`(${HEADER('Calibration')}).disabled`), await evaluate(`(${HEADER('Start')})?.title ?? 'no Start'`));
  const asked = described; await sleep(1500);
  check('... no model is asked about meanwhile, and there is no Mode suggestion', described === asked && !(await evaluate(`!!(${PARA})`)), `${described - asked} request(s)`);
  check('... the configuration is left as it is: it still says resume (the backend still reads it)', (await page.stored())?.run?.mode === 'resume');

  reportRefused(refused, NEVER_ASKED_OR_SAVED);
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
