// Browser check of "Apply and save" (record 7.217): the calibration of a Baseline simulation, for a task saved from a
// Virtuoso cell. Applying its proposals makes the page differ from the saved task, which then starts only after Save task -
// two presses, and a blocked page in between (user, 2026-10-05: "whats the problem here"). Both places that offer the
// proposals - the "Calibration ready" line under the header and the Calibration block of Run status - now offer
// "Apply and save" (Apply, then Save task as a press on it) with "Apply only" beside it. Pinned here:
//   - the line and the block offer Apply and save / Apply only for a saved task, with the values written as quantities
//     (a Scale of 100000000 on a row in Hz reads 100 MHz), and say when the backend worked the proposals out again;
//   - a window most random designs are inside is proposed half its width, with the reason in the table; an Initial alpha
//     close to the one in use is not proposed, and the line says so;
//   - nothing is saved on load; "Apply and save" writes the Scale into the page (one Undo step) and sends ONE save that
//     holds the applied rows; the page says the save is running, and Save task reports the revision;
//   - "Apply only" saves nothing and says that Save task is still to be pressed;
//   - while another save runs, "Apply and save" still applies, sends nothing and says why Save task could not start.
// Branch record SIF-138: the line calls each proposal a Scale ("Scale of osc_frequency_hz 100 MHz"); once the page holds
// the Scale - after Apply only, or a save that could not start - only a greyed Apply calibration stands and Save as makes a
// new task, so the words say that Undo, then Apply and save, updates this task (the line's, where Apply and save is); the
// block says it only after its own Apply only, never after a save of the task. Where Apply calibration stands for such a
// task - an Initial alpha to apply, every Scale held - no words name Apply and save. Review of SIF-138: a refused save's
// words put Undo first ("press Undo, then, once the save can start, Apply and save": choosing a connection is an Undo step
// of its own); the words that ask for an Undo, the block's and the message line's, go with that Undo; and a Scale Apply
// cannot write, the run's only proposal, is named beside "There is nothing to apply.".
// Hermetic, as task_save_check.mjs: the saved task, its run with the calibration result, every /api/virtuoso/* request and
// the save state are FIXTURES; any other writing request of the page is refused. Exit code 1 if any check fails.
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:5176/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/calibration_save_check.mjs)" [screenshot-dir]
import path from 'node:path';
import { answerDialogs, check, launchEdge, outDir, reportRefused, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('calsave');
const consoleErrors = [];

// ---- canned answers: the saved task (as task_save_check.mjs), its Specs row a window of 1.1 to 1.3 GHz -------------------
const TASK = 'real:ring_osc', DIR = '/fixture/outputs/real/calibration__0001/runs/ring_osc.calibration/scratch__seed0__0001';
const ROWS = [{ variable_id: 'wn', instance_path: 'XU1/MN1', parameter_name: 'w', unit: 'um', optimized: true, lower: 0.6, upper: 1.6, step: 0.005 }];
const PROBES = [{ measurement_id: 'm_osc_frequency_hz', analysis: 'tran', result_source: 'backend_profile', source_name: 'osc_frequency_hz', unit: 'Hz' }];
const SPECS = [{ metric_id: 'osc_frequency_hz', equation: 'm_osc_frequency_hz', unit: 'Hz', constraint: 'interval', lower: 1.1e9, upper: 1.3e9, normalization_scale: 1.3e9 }];
const generated = task => ({ loaded: true, task_key: task, mock: false, native_draft: false, generated_profile: true, baseline_recorded: true, complete: true,
  diagnostics: [], circuit: {}, hierarchy: { XU1: { MN1: {} } }, analysis_context: null, evaluation_backend: 'FIXTURE', max_concurrency: 4,
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: ['FIXTURE: a saved task.'] });
// The calibration as the backend answers it under today's rule, for a run recorded under the rule before it: few random
// designs miss the window and its Scale is wider than half of it, so half the window is proposed; the Initial alpha in
// use is close to the estimate.
const NOTE = '3 of 64 random designs miss this row: too few for their typical miss to set the Scale. Half the window is proposed: with the Scale in use (1.3 GHz) the middle of '
  + 'the window counts as 0.077 of a Scale away from its limits, and the margin bonus of the whole task cannot pay for more room than that.';
const ALPHA_NOTE = 'Not proposed: the estimate is 0.012 (0.1 x the reward spread), within a factor of 2 of the 0.01 in use. The value in use stays.';
const RESULT = { format: 'gator-calibration-1', status: 'calibrated', reason: null, scale_note: null, rule: { version: 3 },
  designs: { simulated: 64, scored: 64, passing: 0, requested: 64 },
  rows: [{ metric_id: 'osc_frequency_hz', unit: 'Hz', lower: 1.1e9, upper: 1.3e9, scale_stated: 1.3e9, scale_used: 1.3e9, measured: 64, misses: 3, median_miss: 4.2e8,
    proposed_scale: 1e8, limited: 'window', note: NOTE, half_window: 1e8 }],
  initial_alpha: { used: 0.01, proposed: null, estimate: 0.012, reward_sd: 0.12, reward_sd_used: 0.11, note: ALPHA_NOTE }, reward_check: { designs: 64, reproduced: 64 },
  run_id: 'fixture-run', task_key: TASK, run_state: 'completed', created_utc: '2026-10-05T17:05:00+00:00', recalculated: { from_rule: 1, to_rule: 3 } };
const STATUS = { state: 'completed', run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: 'real', mock: false, worker_alive: false, run_dir: DIR,
  heartbeat_utc: '2026-10-05T17:05:00+00:00', stop_reason: 'budget_exhausted', error: null, active_workers: [], concurrency: 1, learner_updates: 0, first_feasible: null,
  budget: { max_evaluations: 64, max_launches: null, max_retries: 0, charged: 64, reserved: 0, in_flight: 0, completed: 64, failed: 0, released: 0, remaining: 0, launches: 64, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: DIR }, connection: { overall: 'not_applicable' }, summary: null, save_point: null,
  calibration: { request: { designs: 64, lanes: 1, evaluations: 64, random_only: true }, result: RESULT },
  manifest: { mode: 'scratch', mock: false, task_id: TASK, seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: 64 }, mock_notice: null } };
const LISTED = { run_dir: DIR, run_id: 'fixture-run', task_id: TASK, task_key: TASK, task_name: 'ring_osc.calibration', task_definition_hash: 'fixture', mode: 'scratch', mock: false, seed: 0,
  created_utc: '2026-10-05T17:03:00+00:00', started_utc: '2026-10-05T17:03:00+00:00', ended_utc: '2026-10-05T17:05:00+00:00', state: 'completed',
  experiment: 'calibration__0001', evaluations: 64, max_evaluations: 64, first_feasible_eval_count: null, resumability: null, stop_reason: 'budget_exhausted', error: null };
const STEPS = [['setup', 'Virtuoso writes the Maestro test into the cell and reads it back'], ['files', 'Writing the task files and checking them']].map(([id, title]) => ({ id, title }));

await runChecks(browser, async () => {
  const page = await browser.open({ errors: consoleErrors });
  const { send, evaluate, until, fulfil } = page;
  const calls = []; const dialogs = []; const answers = [];
  let saving = { running: null, last: null }, revision = 1;
  const answer = async params => {
    const { requestId, request } = params;
    const url = new URL(request.url), pathname = url.pathname, body = JSON.parse(request.postData ?? '{}');
    if (pathname === '/api/tasks/saving') return fulfil(requestId, 200, saving);
    if (pathname === '/api/tasks') {
      const real = await (await fetch(new URL('api/tasks', APP))).json();
      return fulfil(requestId, 200, { ...real, tasks: [...real.tasks, { task_key: TASK, kind: 'real', available: true, generated: true, revision, circuit_class: 'vco', pdk_id: 'gpdk045' }] });
    }
    if (pathname === '/api/tasks/starter' && url.searchParams.get('task_key') === TASK)
      return fulfil(requestId, 200, { project: { name: 'fixture', task_name: 'ring' }, circuit: { source: 'registered_task', task_id: TASK }, parameters: ROWS, measurements: PROBES, targets: SPECS, revision });
    if (pathname === '/api/circuit/load') {
      const circuit = body.circuit ?? {};
      return circuit.source === 'registered_task' && circuit.task_id === TASK ? fulfil(requestId, 200, generated(TASK)) : send('Fetch.continueRequest', { requestId });
    }
    if (pathname === '/api/runs/status') return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, STATUS) : fulfil(requestId, 404, { detail: 'Not a run directory' });
    if (pathname === '/api/runs') return fulfil(requestId, 200, { runs: [LISTED] });
    if (pathname === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (!pathname.startsWith('/api/virtuoso/')) return page.readOrRefuse(params, page.refused, { reads: true });
    const op = pathname.replace('/api/virtuoso/', '');
    calls.push({ op, ...body });
    await sleep(120);
    if (op === 'task/save') {
      revision += 1;
      return fulfil(requestId, 200, { task_key: TASK, name: body.task, revision, created: false, runnable: true, circuit_class: 'vco', pdk_id: 'gpdk045',
        parameters: ROWS, baseline_kept: true, changed: [], copy: { library: 'GPDK045_RINGOSC_GATOR', cell: 'ring_osc_3stage', testbench: 'tb_ring_osc_3stage' } });
    }
    return fulfil(requestId, 418, { detail: { message: `FIXTURE: ${op} is not expected` } });
  };
  answerDialogs(page, answers, dialogs);
  const READY = `document.querySelector('header .calibration-ready')`, BANNER = `(document.querySelector('.banner')?.textContent ?? '')`;
  const readyButtons = () => evaluate(`[...(${READY}?.querySelectorAll('button') ?? [])].map(b => b.textContent.trim())`);
  const readyButton = text => `[...(${READY}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const BLOCK = `document.querySelector('footer .calibration')`;
  const blockButtons = () => evaluate(`[...(${BLOCK}?.querySelectorAll('button') ?? [])].map(b => b.textContent.trim())`);
  const blockButton = text => `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const HINT = `${BLOCK}?.querySelector('.row .hint')?.textContent`, SAID = `(${BLOCK}?.querySelector('.calibration-said')?.textContent ?? '')`;
  const NOTES = `(document.querySelector('.editors .task-notes')?.textContent ?? '')`;
  const SAVE = `[...(document.querySelector('.editors .tabs .task-save')?.querySelectorAll('button') ?? [])].find(b => /^Sav/.test(b.textContent.trim()))`;
  const UNDO = `[...document.querySelectorAll('.editors .toolbar button')].find(b => b.textContent.trim() === 'Undo')`;
  const SPECS_TAB = `document.querySelector('section.editors > .tabs > button[data-editor="targets"]')`;
  const CELL = (row, name) => `(() => { const editors = document.querySelector('.editors'), at = [...editors.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).indexOf(${JSON.stringify(name)});
    return editors.querySelectorAll('table.editor tbody tr')[${row}]?.children[at]?.querySelector('input, select') ?? null; })()`;
  const stored = page.savedConfig;
  const cells = () => evaluate(`[...(${BLOCK}?.querySelectorAll('table tbody tr') ?? [])].map(tr => [...tr.children].map(td => td.textContent.trim()))`);
  const saves = () => calls.filter(c => c.op === 'task/save');
  const settle = async (ms = 900) => {
    const mark = calls.length;
    for (let waited = 0; waited < ms && calls.length === mark; waited += 50) await sleep(50);
    for (let seen = mark; calls.length !== mark && seen !== calls.length;) { seen = calls.length; await sleep(500); }
  };

  await page.trackSaves();
  await page.intercept(['*/api/virtuoso/*', '*/api/circuit/load', '*/api/tasks', '*/api/tasks/starter*', '*/api/tasks/saving', '*/api/runs/status*', '*/api/runs', '*/api/runs/default-model*'], answer,
    { others: 'read', connection: 'lab' });
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await page.stored()); i++) await sleep(100);
  const start = await page.stored();
  const seeded = { ...start, circuit: { ...start.circuit, source: 'registered_task', task_id: TASK, circuit_class: 'vco', pdk_id: 'gpdk045' },
    parameters: ROWS, measurements: PROBES, targets: SPECS, run: { ...start.run, advanced: { ...(start.run?.advanced ?? {}), initial_alpha: 0.01 } } };
  await page.seed({ config: seeded, run: DIR, when: 'once' });
  await send('Page.reload');
  if (!(await until(`!!(${READY}) && !!(${SAVE})`, 200))) throw new Error('the Calibration ready line or Save task never came up: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- the line under the header --------------------------------------------------------------------------------------------
  const line = await evaluate(`${READY}.querySelector('span').textContent`);
  check('the line names the task and writes the proposed Scale as a quantity, named a Scale: "Scale of osc_frequency_hz 100 MHz" (SIF-138)',
    line.startsWith(`Calibration ready for ${TASK}: Scale of osc_frequency_hz 100 MHz. Proposed from 64 random designs; nothing has changed yet.`), line);
  check('for a saved task it offers Apply and save, Apply only and Not now', JSON.stringify(await readyButtons()) === JSON.stringify(['Apply and save', 'Apply only', 'Not now']), JSON.stringify(await readyButtons()));
  const saveTitle = await evaluate(`${readyButton('Apply and save')}.title`);
  check('the tooltip says what the press does: Apply, then the save - the cell is written, nothing is simulated',
    saveTitle.startsWith('Apply and save: Writes the Scale of 1 Specs row into the page, as one Undo step, then saves the task:') && /the cell in Virtuoso is written to match and read back/.test(saveTitle)
    && /no simulation/.test(saveTitle) && /A change of Scale alone keeps the recorded baseline/.test(saveTitle), saveTitle);
  // Branch record SIF-136: with the line open the header wrapped its first row, and Abort stood alone on a second one under
  // the GATOR chip. The title block, Save now, the Next line, Start and Abort keep one row (one vertical centre) above the line.
  const row = await evaluate(`(() => { const mid = s => { const r = document.querySelector(s)?.getBoundingClientRect(); return r ? Math.round(r.top + r.height / 2) : null; };
    return { at: ['header .title-block', 'header button.run-save', 'header span.next-run', 'header button.run-main', 'header button.run-abort'].map(mid),
      line: Math.round(${READY}.getBoundingClientRect().top) }; })()`);
  check('...and the header keeps one first row above it: the title block, Save now, the Next line, Start and Abort (SIF-136: Abort alone on a second row)',
    row.at.every(y => y !== null && Math.abs(y - row.at[0]) <= 2 && y < row.line), JSON.stringify(row));
  await page.shot(path.join(out, 'calibration-save-0-line.png'), `document.querySelector('header')`, { pad: 4 });

  // ---- the block in Run status --------------------------------------------------------------------------------------------------
  check('Run status shows the calibration with Apply and save and Apply only', await until(`!!(${blockButton('Apply and save')})`, 100)
    && JSON.stringify(await blockButtons()) === JSON.stringify(['Apply and save', 'Apply only']), JSON.stringify(await blockButtons()));
  const shown = await cells();
  check('the table writes limits, typical miss and both Scales as quantities', shown.length === 1 && shown[0][1] === '1.1 GHz to 1.3 GHz' && shown[0][2] === '3 of 64'
    && shown[0][3] === '420 MHz' && shown[0][4] === '1.3 GHz' && shown[0][5].startsWith('100 MHz') && shown[0][5].endsWith(NOTE), JSON.stringify(shown));
  check('it says that the proposals were worked out again under today\'s rule', (await evaluate(`${BLOCK}.querySelector('.recalculated')?.textContent.replace(/\\s+/g, ' ') ?? ''`))
    === "Worked out again from this run's recorded designs with today's rule; the run's own file keeps what it said at its end.", await evaluate(`${BLOCK}.textContent.slice(0, 300)`));
  const alphaLine = await evaluate(`${BLOCK}.querySelector('.calibration-alpha').textContent`);
  check('an Initial alpha close to the one in use is not proposed, and the line says why', alphaLine === `Initial alpha (RL model): now 0.01; proposed nothing: ${ALPHA_NOTE.replace('Not proposed: ', '')}`, alphaLine);
  check('the hint says what both buttons do', (await evaluate(HINT)) === 'Sets the Scale of 1 Specs row, as one Undo step; Apply and save also saves the task, so it can start.', await evaluate(HINT));
  await settle(1200);
  check('nothing is saved or written on load', calls.length === 0 && (await stored()).targets[0].normalization_scale === 1.3e9, calls.map(c => c.op).join(' | '));
  await page.shot(path.join(out, 'calibration-save-1-block.png'), `document.querySelector('footer')`);

  // ---- Apply and save, in the line --------------------------------------------------------------------------------------------
  await evaluate(`${readyButton('Apply and save')}.click()`);
  await settle(2000);
  let config = await stored();
  check('"Apply and save" writes the Scale into the Specs row', config.targets[0].normalization_scale === 1e8 && config.run.advanced.initial_alpha === 0.01,
    JSON.stringify({ scale: config.targets[0].normalization_scale, alpha: config.run.advanced.initial_alpha }));
  check('...and sends ONE save of the open task, holding the applied rows', saves().length === 1 && saves()[0].task === 'ring_osc' && saves()[0].as_new === false
    && saves()[0].config?.targets?.[0]?.normalization_scale === 1e8 && saves()[0].config?.targets?.[0]?.lower === 1.1e9, JSON.stringify(saves().map(c => ({ task: c.task, scale: c.config?.targets?.[0]?.normalization_scale }))));
  check('the page says what was applied and that the save runs', (await evaluate(BANNER)) === "Calibration applied: the Scale of 1 Specs row, as one Undo step. Saving the task now: the progress is under the editors' tabs.", await evaluate(BANNER));
  check('Save task reports the revision and the baseline, under the toolbar', await until(`/Saved real:ring_osc, revision 2\\. The recorded baseline still holds\\./.test(${NOTES})`, 50), await evaluate(NOTES));
  // SIF-138: the block's hint said "Use Apply and save to update this task" here, the task just saved with the values.
  check('the line goes; the block says the page holds the values - and no more: the task holds them too - and offers the plain button, at rest', await until(`!(${READY})`, 30)
    && JSON.stringify(await blockButtons()) === JSON.stringify(['Apply calibration']) && await evaluate(`${blockButton('Apply calibration')}.disabled`)
    && (await evaluate(HINT)) === 'The page holds these values.', JSON.stringify([await blockButtons(), await evaluate(HINT)]));
  await page.shot(path.join(out, 'calibration-save-2-saved.png'), `document.querySelector('.editors')`, { maxHeight: 260 });

  // ---- one Undo takes the Scale back; Apply only saves nothing ------------------------------------------------------------------
  await evaluate(`${UNDO}.click()`);
  config = await stored();
  check('ONE Undo takes the Scale back, and the block offers both buttons again', config.targets[0].normalization_scale === 1.3e9
    && await until(`!!(${blockButton('Apply and save')}) && !!(${blockButton('Apply only')})`, 30), JSON.stringify(await blockButtons()));
  let mark = calls.length;
  await evaluate(`${blockButton('Apply only')}.click()`);
  await settle(1200);
  config = await stored();
  check('"Apply only" writes the Scale and sends nothing', config.targets[0].normalization_scale === 1e8 && calls.length === mark, calls.slice(mark).map(c => c.op).join(' | '));
  check('...and says how this task is updated with it: Undo, then Apply and save; Save as makes a new task (SIF-138: "Use Apply and save" beside a lone greyed button)',
    (await evaluate(HINT)) === 'The page holds these values. To update this task with them, press Undo, then Apply and save (it keeps the recorded baseline); Save as makes a new task.'
    && JSON.stringify(await blockButtons()) === JSON.stringify(['Apply calibration']), JSON.stringify([await blockButtons(), await evaluate(HINT)]));

  // ---- while another save runs: applied, nothing sent, and the reason ------------------------------------------------------------
  await evaluate(`${UNDO}.click()`);
  await stored();
  saving = { running: { id: 'other', task_key: TASK, started_utc: '2026-10-05T17:06:00+00:00', seconds: 12, steps: STEPS, step: 'setup', step_number: 1, step_seconds: 12, usual_seconds: 34 }, last: null };
  // The line's answer is taken back (SIF-138), so the page loaded during the save offers the line too: its Apply and save
  // first, then the block's.
  await evaluate(`localStorage.removeItem('gator-workbench-calibration-answered-v1')`);
  await send('Page.reload');
  check('a page loaded during a save keeps Save task closed', await until(`!!(${SAVE}) && ${SAVE}.disabled && /Saving/.test(${SAVE}.textContent) && !!(${blockButton('Apply and save')})
    && !!(${readyButton('Apply and save')})`, 200), await evaluate(`${SAVE}?.textContent`));
  mark = calls.length;
  await evaluate(`${readyButton('Apply and save')}.click()`);
  await settle(1500);
  config = await stored();
  check('the line\'s "Apply and save" still applies, and sends no second save', config.targets[0].normalization_scale === 1e8 && calls.length === mark, calls.slice(mark).map(c => c.op).join(' | '));
  // Review of SIF-138: Undo first - "once the save can start, press Undo" took back the choice of a connection (an Undo step
  // of its own), not the Scale.
  check('...the page says why Save task could not start, and that Undo, then Apply and save under Run status, updates the task - Undo first: the line has gone (SIF-138)',
    (await evaluate(BANNER)) === `Calibration applied: the Scale of 1 Specs row, as one Undo step. Saving could not be started from here (the save of ${TASK} is still running). The Scale `
      + 'stays applied: press Undo, then, once the save can start, Apply and save under Run status of that run; Save as above the editors makes a new task instead.'
    && await evaluate(`!(${READY})`), await evaluate(BANNER));
  check('...beside the lone greyed Apply calibration the block says only that the page holds the values', JSON.stringify(await blockButtons()) === JSON.stringify(['Apply calibration'])
    && (await evaluate(HINT)) === 'The page holds these values.', JSON.stringify([await blockButtons(), await evaluate(HINT)]));
  await evaluate(`${UNDO}.click()`);
  config = await stored();
  check('as it says, ONE Undo takes the Scale back and the block offers Apply and save again', config.targets[0].normalization_scale === 1.3e9
    && await until(`!!(${blockButton('Apply and save')})`, 30), JSON.stringify(await blockButtons()));
  // Review of SIF-138: "The Scale stays applied ... press Undo" stayed on the message line after that Undo.
  check('...and the message line that asked for it goes with it: the Scale is no longer applied', await until(`${BANNER} === ''`, 30), await evaluate(BANNER));
  mark = calls.length;
  await evaluate(`${blockButton('Apply and save')}.click()`);
  await settle(1500);
  config = await stored();
  check('the block\'s "Apply and save" still applies, and sends no second save', config.targets[0].normalization_scale === 1e8 && calls.length === mark, calls.slice(mark).map(c => c.op).join(' | '));
  check('...the block says why Save task could not start, and what to press: Undo, then Apply and save (SIF-138: "try Apply and save again", a button no longer there) - Undo first (review of SIF-138)',
    (await evaluate(SAID)) === `Applied the Scale of 1 Specs row, as one Undo step. Saving could not be started from here (the save of ${TASK} is still running). The Scale stays applied: `
      + 'press Undo, then, once the save can start, Apply and save; Save as above the editors makes a new task instead.'
    && (await evaluate(HINT)) === 'The page holds these values.', JSON.stringify([await evaluate(SAID), await evaluate(HINT)]));
  await page.shot(path.join(out, 'calibration-save-3-busy.png'), `document.querySelector('footer')`);
  saving = { running: null, last: { id: 'other', task_key: TASK, ok: true, seconds: 30, answer: { task_key: TASK, revision: 3, created: false, baseline_kept: true, changed: [] } } };
  check('when that save has ended, Save task opens again', await until(`!!(${SAVE}) && !${SAVE}.disabled && ${SAVE}.textContent.trim() === 'Save as'`, 60), await evaluate(`${SAVE}?.textContent`));
  // Review of SIF-138: after the Undo it asks for, the block's line still said "The Scale stays applied ... press Undo" under
  // the Apply and save that Undo brought back - a second Undo would take back an earlier edit.
  await evaluate(`${UNDO}.click()`);
  await stored();
  check('the Undo the block asked for takes the Scale back, and its words about the refused save go with it (review of SIF-138)', await until(`${SAID} === '' && !!(${blockButton('Apply and save')})`, 30)
    && (await evaluate(HINT)) === 'Sets the Scale of 1 Specs row, as one Undo step; Apply and save also saves the task, so it can start.', JSON.stringify([await evaluate(SAID), await evaluate(HINT)]));

  // ---- Apply only in the line (SIF-138) ---------------------------------------------------------------------------------------------
  // The line goes with the press and a greyed Apply calibration stands alone in the block: the page says that Undo, then Apply
  // and save under Run status, updates this task. The block, whose button was not pressed, says no more than that the page
  // holds the values.
  await evaluate(`localStorage.removeItem('gator-workbench-calibration-answered-v1')`);
  await send('Page.reload');
  check('with its answer taken back, a reload offers the line again', await until(`!!(${readyButton('Apply only')}) && !!(${SAVE}) && !${SAVE}.disabled`, 200), JSON.stringify(await readyButtons()));
  mark = calls.length;
  await evaluate(`${readyButton('Apply only')}.click()`);
  await settle(1200);
  config = await stored();
  check('the line\'s "Apply only" writes the Scale and sends nothing', config.targets[0].normalization_scale === 1e8 && calls.length === mark, calls.slice(mark).map(c => c.op).join(' | '));
  check('...the page says how this task is updated with it, and where Apply and save is: the line has gone (SIF-138)', (await evaluate(BANNER))
    === 'Calibration applied: the Scale of 1 Specs row, as one Undo step. To update this task with them, press Undo, then Apply and save under Run status of that run (it keeps the '
      + 'recorded baseline); Save as makes a new task.' && await evaluate(`!(${READY})`), await evaluate(BANNER));
  check('...and the block says only that the page holds the values', JSON.stringify(await blockButtons()) === JSON.stringify(['Apply calibration'])
    && (await evaluate(HINT)) === 'The page holds these values.', JSON.stringify([await blockButtons(), await evaluate(HINT)]));
  // Review of SIF-138: Apply only's "press Undo, then Apply and save" stayed on the message line after that Undo too.
  await evaluate(`${UNDO}.click()`);
  config = await stored();
  check('the Undo it asks for takes the Scale back, and the message line goes with it (review of SIF-138)', config.targets[0].normalization_scale === 1.3e9
    && await until(`${BANNER} === '' && !!(${blockButton('Apply and save')})`, 30), JSON.stringify([await evaluate(BANNER), await blockButtons()]));

  // ---- the run's only proposal, a Scale Apply cannot write (review of SIF-138) ---------------------------------------------------
  // This run proposes no Initial alpha, so the Scale of the row whose limits are edited is all it proposed: "There is nothing to
  // apply." stood alone, the row not named and nothing said how to get its Scale.
  await evaluate(`${SPECS_TAB}.click()`);
  await until(`${SPECS_TAB}.classList.contains('active') && !!(${CELL(0, 'metric_id')})`, 30);   // the Specs table: the Parameters' has a Lower too
  await page.setValue(CELL(0, 'lower'), '1 GHz', { event: 'input' });
  config = await stored();
  check('with the limits of its row changed, the run\'s only proposal is not applied, and the block names it and how to get one, Apply at rest',
    config.targets[0].lower === 1e9 && await until(`/not applied: the limits of this row were changed after the run/.test(${BLOCK}?.textContent ?? '')`, 30)
    && (await evaluate(HINT)) === 'There is nothing to apply. The Scale of osc_frequency_hz is not applied: its limits changed after the run; a new Calibration works one out for the '
      + 'new limits when enough random designs miss them.' && JSON.stringify(await blockButtons()) === JSON.stringify(['Apply calibration']) && await evaluate(`${blockButton('Apply calibration')}.disabled`),
    JSON.stringify([config.targets[0].lower, await blockButtons(), await evaluate(HINT)]));
  // Back to the rows the run simulated, and the Scale held again (the block's Apply only: nothing is sent), for the part below.
  await evaluate(`${UNDO}.click()`);
  mark = calls.length;
  await until(`!!(${blockButton('Apply only')})`, 30);
  await evaluate(`${blockButton('Apply only')}.click()`);
  await settle(1200);
  config = await stored();
  check('...an Undo takes the limit back, and Apply only holds the Scale again, sending nothing', config.targets[0].lower === 1.1e9 && config.targets[0].normalization_scale === 1e8
    && calls.length === mark, JSON.stringify({ lower: config.targets[0].lower, scale: config.targets[0].normalization_scale, sent: calls.slice(mark).map(c => c.op) }));

  // ---- an Initial alpha still to apply beside a Scale the page holds (SIF-138) ---------------------------------------------------
  // FIXTURE: the same run proposing an Initial alpha of 0.02. Every Scale is held, so Apply calibration stands alone, enabled,
  // and no words name Apply and save: the line's tooltip and the block's hint said "Use Apply and save to update this task".
  Object.assign(RESULT.initial_alpha, { proposed: 0.02, note: null });
  await evaluate(`localStorage.removeItem('gator-workbench-calibration-answered-v1')`);
  await send('Page.reload');
  const applyTitle = await until(`!!(${readyButton('Apply calibration')})`, 200) ? await evaluate(`${readyButton('Apply calibration')}.title`) : null;
  check('with an Initial alpha to apply, the line offers Apply calibration, not Apply and save, and its tooltip names none (SIF-138)',
    applyTitle === 'Apply calibration: Writes the Scale of 1 Specs row and Initial alpha into the page, as one Undo step. Nothing is simulated and no task is saved.'
    && await evaluate(`!(${readyButton('Apply and save')}) && !(${readyButton('Apply only')})`), JSON.stringify([applyTitle, await readyButtons()]));
  check('...and the block offers Apply calibration, its hint naming no Apply and save (SIF-138)', JSON.stringify(await blockButtons()) === JSON.stringify(['Apply calibration'])
    && await evaluate(`!${blockButton('Apply calibration')}.disabled`) && (await evaluate(HINT)) === 'Sets the Scale of 1 Specs row and Initial alpha, as one Undo step.',
    JSON.stringify([await blockButtons(), await evaluate(HINT)]));

  reportRefused(page.refused);
  check('no error in the page console', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
