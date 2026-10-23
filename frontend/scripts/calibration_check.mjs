// Browser check of the calibration that goes with the Baseline simulation (record 7.197; one button since record 7.202, the
// "+ calibration" tick gone): the header button alone, a REAL run on the synthetic MOCK task (free, no bridge, no Virtuoso) of
// 64 random designs with no baseline - also in a browser that had unticked the old tick - the proposals in Run status - a
// Scale per Specs row and the Initial alpha - and Apply, which writes them into the page's configuration as ONE Undo step
// and only into rows that still are the rows the run simulated. And the line under the header when the run has ended
// (record 7.204, "Calibration ready"): Not now changes nothing and is remembered, Apply calibration there does what the
// block's button does, and the next run asks again. And a run of another task than the page holds (record 7.214, its status
// changed by the check): the block shows the run's own Scales and Initial alpha, never the page's row of the same ID.
// Branch record SIF-105: the line's "Show table" while the table is out of view (another tab, the panel folded, the tabs on
// another run), never while it is in view.
// Record 7.217: an Initial alpha is proposed only when it differs from the one the run had by a factor of 2 or more - the
// second run here starts from the first run's applied value, so whether it proposes one follows that rule ("Apply and
// save", for a task saved from a Virtuoso cell, is in calibration_save_check.mjs).
// It starts runs, so it REFUSES the default backend: give it a SCRATCH backend and a scratch output root (run_checks.sh does;
// by hand as run_control_live_check.mjs says). Takes about a minute. Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl({ writes: true }), OUT_ROOT = process.env.GATOR_SCRATCH_OUT;
if (!OUT_ROOT) {
  console.log('ERROR this check starts real (MOCK) runs: set GATOR_SCRATCH_OUT to the allowed output root of the scratch backend (and WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT).');
  process.exit(1);
}
const out = outDir();
const browser = await launchEdge('calibration');
const get = async (route, params) => (await fetch(new URL(`api/${route}?` + new URLSearchParams(params), APP))).json();

await runChecks(browser, async () => {
  const starter = await get('tasks/starter', { task_key: 'synthetic:gpdk045_ota5' });
  // The page's tested reward (compressed) and soft actor-critic values; the MOCK row "score >= 0.95" holds the Scale 1.
  const CONFIG = { ...starter, run: { ...starter.run, max_evaluations: 60, concurrency: 1, reward: { violation_shape: 'compressed', worst_spec_share: 0.5, objective_weight: 1, objective_shape: 'compressed', margin_weight: 1 },
    advanced: { initial_alpha: 0.01, updates_per_transition: 8, gamma: 0 } }, output: { experiment_name: 'calibration_check', output_root: OUT_ROOT }, research: {} };
  const page = await browser.open();
  const { send, evaluate, until, consoleErrors } = page;
  const dialogs = [];
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const BASELINE = `[...document.querySelectorAll('header button')].find(b => b.textContent === 'Calibration')`;
  const CHIP = `document.querySelector('header button.run-chip')`;
  const BLOCK = `document.querySelector('footer .calibration')`, APPLY = `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent === 'Apply calibration')`;
  const HINT = `${BLOCK}?.querySelector('.row .hint')?.textContent`;
  const READY = `document.querySelector('header .calibration-ready')`, BANNER = `(document.querySelector('.banner')?.textContent ?? '')`;
  const readyButton = text => `[...(${READY}?.querySelectorAll('button') ?? [])].find(b => b.textContent === ${JSON.stringify(text)})`;
  const EDITORS = `document.querySelector('.editors')`;
  const TOOL = text => `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const stored = page.savedConfig;
  const cells = () => evaluate(`[...(${BLOCK}?.querySelectorAll('table tbody tr') ?? [])].map(tr => [...tr.children].map(td => td.textContent.trim()))`);

  await page.trackSaves();
  await page.seed({ config: CONFIG, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${BASELINE}) && !${BASELINE}.disabled`, 200))) throw new Error('the baseline button never became available: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- one button, no tick ----------------------------------------------------------------------------------------------
  check('no "+ calibration" tick and no Single baseline simulation in the header', await evaluate(`!document.querySelector('header input[type=checkbox]')
    && !document.querySelector('header').textContent.includes('Baseline') && !document.querySelector('header').textContent.includes('Single baseline')`));
  const title = await evaluate(`${BASELINE}.title`);
  check('its tooltip says random designs only and that nothing changes by itself',
    /64 random designs over the Parameters ranges/.test(title) && /nothing changes by itself/.test(title) && /No starting-design baseline/.test(title), title);
  await page.shot(path.join(out, 'calibration-0-header.png'), `document.querySelector('header')`, { pad: 4 });

  // ---- the run: the baseline, then 64 random designs ------------------------------------------------------------------------
  await evaluate(`${BASELINE}.click()`);
  // A start prepares the run folder and launches a worker: seconds on a busy machine, so the waits are long.
  check('a MOCK run asks nothing and starts', await until(`!!localStorage.getItem('gator-workbench-current-run-v1')`, 900) && dialogs.length === 0, JSON.stringify(dialogs));
  const dir = await evaluate(`localStorage.getItem('gator-workbench-current-run-v1')`);
  check('while it runs, Run status says what is coming', await until(`/64 random designs are simulated; the proposals appear here when the run has ended/.test(${BLOCK}?.textContent ?? '') || !!(${APPLY})`, 300));
  check('the run completes with 64 evaluations charged', await until(`/^completed at 64 of 64 evaluations \\[MOCK\\]$/.test(${CHIP}?.textContent ?? '')`, 600), await evaluate(`${CHIP}?.textContent`));
  const status = await get('runs/status', { run_dir: dir });
  const result = status.calibration?.result, row = result?.rows?.[0];
  check('the backend says: calibration asked for 64 designs and exactly 64 evaluations', JSON.stringify(status.calibration?.request) === JSON.stringify({ designs: 64, lanes: 1, evaluations: 64, random_only: true })
    && status.budget?.charged === 64 && status.learner_updates === 0, JSON.stringify({ request: status.calibration?.request, charged: status.budget?.charged, updates: status.learner_updates }));
  check('its proposals: a Scale for the row "score" and an Initial alpha, every recorded reward worked out again', result?.status === 'calibrated' && row?.metric_id === 'score'
    && typeof row?.proposed_scale === 'number' && typeof result?.initial_alpha?.proposed === 'number' && result.reward_check.reproduced === 64, JSON.stringify(result).slice(0, 400));
  const scale = row.proposed_scale, alpha = result.initial_alpha.proposed;

  // ---- the line under the header: Calibration ready (record 7.204) ---------------------------------------------------------
  check('when the run has ended, a line under the header says the calibration is ready, with the values and both buttons', await until(`!!(${READY})`, 100)
    && (await evaluate(`${READY}.querySelector('span').textContent`)).startsWith(`Calibration ready for synthetic:gpdk045_ota5: score ${scale} \u00b7 Initial alpha ${alpha}. Proposed from 64 random designs; nothing has changed yet.`)
    && await evaluate(`!!(${readyButton('Apply calibration')}) && !!(${readyButton('Not now')})`), await evaluate(`${READY}?.textContent`));
  await page.shot(path.join(out, 'calibration-0b-ready-line.png'), `document.querySelector('header')`, { pad: 4 });
  await evaluate(`${readyButton('Not now')}.click()`);
  check('"Not now" closes the line, changes nothing and says where the proposals stay', await until(`!(${READY})`, 30)
    && (await stored()).targets[0].normalization_scale === 1 && (await stored()).run.advanced.initial_alpha === 0.01
    && /Nothing was changed\. The proposals stay under Run status of that run/.test(await evaluate(BANNER)), await evaluate(BANNER));
  check('the answer is kept in this browser, for that run', (await evaluate(`localStorage.getItem('gator-workbench-calibration-answered-v1')`)) === dir);

  // ---- the block in Run status ----------------------------------------------------------------------------------------------
  check('Run status shows the calibration with its Apply button', await until(`!!(${APPLY}) && !${APPLY}.disabled`, 100), await evaluate(`${BLOCK}?.textContent.slice(0, 300)`));
  const shown = await cells();
  check('one line per Specs row: limit, designs that miss it, typical miss, the Scale now and the proposal', shown.length === 1 && shown[0][0] === 'score' && shown[0][1] === '≥ 0.95'
    && shown[0][2] === `${row.misses} of 64` && shown[0][4] === '1' && shown[0][5] === String(scale), JSON.stringify(shown));
  check('the Initial alpha: what the page holds and what is proposed', await evaluate(`${BLOCK}.querySelector('.calibration-alpha').textContent`).then(t => t.startsWith(`Initial alpha (RL model): now 0.01; proposed ${alpha}`)),
    await evaluate(`${BLOCK}.querySelector('.calibration-alpha').textContent`));
  check('the hint says what Apply will do', (await evaluate(HINT)) === 'Sets the Scale of 1 Specs row and Initial alpha, as one Undo step.', await evaluate(HINT));
  check('nothing was applied by the run', (await stored()).targets[0].normalization_scale === 1 && (await stored()).run.advanced.initial_alpha === 0.01);
  await page.shot(path.join(out, 'calibration-1-proposals.png'), `document.querySelector('footer')`);

  // ---- Apply: one Undo step -------------------------------------------------------------------------------------------------
  await evaluate(`${APPLY}.click()`);
  let config = await stored();
  check('Apply writes the Scale into the Specs row and the Initial alpha into the RL settings', config.targets[0].normalization_scale === scale && config.run.advanced.initial_alpha === alpha,
    JSON.stringify({ scale: config.targets[0].normalization_scale, alpha: config.run.advanced.initial_alpha }));
  check('...and nothing else', config.run.advanced.updates_per_transition === 8 && config.run.max_evaluations === 60 && config.targets[0].lower === 0.95);
  check('the block says the page holds the values, and Apply rests', (await evaluate(HINT)) === 'The page holds these values.' && await evaluate(`${APPLY}.disabled`), await evaluate(HINT));
  await evaluate(`${TOOL('Undo')}.click()`);
  config = await stored();
  check('ONE Undo takes both back', config.targets[0].normalization_scale === 1 && config.run.advanced.initial_alpha === 0.01, JSON.stringify({ scale: config.targets[0].normalization_scale, alpha: config.run.advanced.initial_alpha }));
  check('...and Apply is offered again', await until(`!!(${APPLY}) && !${APPLY}.disabled`, 30));

  // ---- a row whose limits were edited after the run is not written -------------------------------------------------------------
  await evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith('Specs')).click()`);
  await page.setValue(CELL(0, 'lower'), '0.9', { event: 'input' });
  check('the row is marked: its limits were changed after the run', await until(`/not applied: the limits of this row were changed after the run/.test(${BLOCK}?.textContent ?? '')`, 50), await evaluate(`${BLOCK}?.textContent.slice(0, 400)`));
  check('Apply then sets the Initial alpha only', (await evaluate(HINT)) === 'Sets Initial alpha, as one Undo step.', await evaluate(HINT));
  await evaluate(`${APPLY}.click()`);
  config = await stored();
  check('...and leaves the edited row alone', config.targets[0].normalization_scale === 1 && config.targets[0].lower === 0.9 && config.run.advanced.initial_alpha === alpha,
    JSON.stringify({ scale: config.targets[0].normalization_scale, lower: config.targets[0].lower, alpha: config.run.advanced.initial_alpha }));
  await page.shot(path.join(out, 'calibration-2-row-changed.png'), `document.querySelector('footer')`);

  // ---- the next Baseline simulation asks again, and Apply calibration in the line does what the block's button does ---------
  await evaluate(`${BASELINE}.click()`);
  check('a second Baseline simulation starts', await until(`(localStorage.getItem('gator-workbench-current-run-v1') ?? ${JSON.stringify(dir)}) !== ${JSON.stringify(dir)}`, 900));
  const dir2 = await evaluate(`localStorage.getItem('gator-workbench-current-run-v1')`);
  let second = null;
  for (let i = 0; i < 300 && !second; i++) { const s = await get('runs/status', { run_dir: dir2 }); if (s.state === 'completed' && !s.worker_alive) second = s.calibration?.result; else await new Promise(r => setTimeout(r, 200)); }
  const scale2 = second?.rows?.[0]?.proposed_scale, alpha2 = second?.initial_alpha?.proposed ?? null;
  // This run had the Initial alpha the first run's Apply wrote: one is proposed only when the estimate is a factor of 2 away.
  const estimate2 = second?.initial_alpha?.estimate, used2 = second?.initial_alpha?.used, close2 = Math.max(estimate2 / used2, used2 / estimate2) < 2;
  check('it ends with a Scale of its own (the row now has the limit 0.9)', typeof scale2 === 'number' && second.rows[0].lower === 0.9, JSON.stringify(second).slice(0, 300));
  check('an Initial alpha is proposed only when the estimate differs from the one the run had by a factor of 2 or more (7.217)', used2 === alpha && typeof estimate2 === 'number'
    && (alpha2 === null) === close2 && (alpha2 === null ? /^Not proposed: the estimate is .* within a factor of 2 of the .* in use\. The value in use stays\.$/.test(second.initial_alpha.note) : alpha2 === estimate2),
    JSON.stringify(second?.initial_alpha));
  const values2 = `score ${scale2}${alpha2 === null ? '' : ` \u00b7 Initial alpha ${alpha2}`}`, what2 = `the Scale of 1 Specs row${alpha2 === null ? '' : ' and Initial alpha'}`;
  check('its line comes up, although the first run\'s was answered', await until(`!!(${readyButton('Apply calibration')})`, 150)
    && (await evaluate(`${READY}.querySelector('span').textContent`)).startsWith(`Calibration ready for synthetic:gpdk045_ota5: ${values2}. Proposed from 64 random designs`), await evaluate(`${READY}?.textContent`));
  check('a task that is not saved from a Virtuoso cell keeps the one button: no Apply and save', await evaluate(`!(${readyButton('Apply and save')}) && !(${readyButton('Apply only')})`));

  // ---- Show table (branch record SIF-105): the line says the table is under Run status; out of view, nothing led there ----------
  const SHOW = readyButton('Show table'), ACTIVE = `document.querySelector('footer .tabs > button.active')?.textContent`;
  const FOLDED = `document.querySelector('.layout').classList.contains('bottom-folded')`, SHOWN = `JSON.parse(localStorage.getItem('gator-workbench-shown-run-v1') ?? 'null')?.run`;
  check('with the table in view - Run status of this run, the panel open - the line has no "Show table" (SIF-105)', await evaluate(`!(${SHOW})`)
    && (await evaluate(ACTIVE)) === 'Run status' && (await evaluate(SHOWN)) === dir2, JSON.stringify([await evaluate(ACTIVE), await evaluate(SHOWN)]));
  await evaluate(`[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent === 'Logs').click()`);
  check('...with Logs shown it offers it, saying what it shows', await until(`!!(${SHOW})`, 30) && (await evaluate(`${SHOW}.title`))
    === 'Show table: Shows this calibration run under Run status, with its table of proposals and its Apply buttons. Nothing is applied.', await evaluate(`${SHOW}?.title`));
  await evaluate(`${SHOW}.click()`);
  check('...a press shows Run status with the table, and the button goes', await until(`${ACTIVE} === 'Run status' && !!(${APPLY}) && !(${SHOW})`, 30), await evaluate(ACTIVE));
  await evaluate(`document.querySelector('.splitter').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  check('...with the panel folded it offers it too', await until(`${FOLDED} && !!(${SHOW})`, 30));
  await evaluate(`${SHOW}.click()`);
  check('...and the press opens the panel on the table', await until(`!${FOLDED} && !!(${APPLY}) && !(${SHOW})`, 30));
  // The tabs on another run - the first calibration, kept as the run shown beside the header's second one, as after a choice
  // in Runs... - once the page is loaded again.
  await evaluate(`localStorage.setItem('gator-workbench-shown-run-v1', ${JSON.stringify(JSON.stringify({ run: dir, header: dir2 }))})`);
  await send('Page.reload');
  check('...with the tabs on another run it offers it too', await until(`!!(${SHOW})`, 200) && (await evaluate(SHOWN)) === dir, await evaluate(SHOWN));
  await page.shot(path.join(out, 'calibration-0c-show-table.png'), `document.querySelector('header')`, { pad: 4 });
  await evaluate(`${SHOW}.click()`);
  check('...and the press shows this run\'s table', await until(`${SHOWN} === ${JSON.stringify(dir2)} && ${ACTIVE} === 'Run status' && !!(${APPLY}) && !${APPLY}.disabled && !(${SHOW})`, 60),
    JSON.stringify([await evaluate(SHOWN), await evaluate(ACTIVE)]));
  await evaluate(`${readyButton('Apply calibration')}.click()`);
  config = await stored();
  check('"Apply calibration" in the line writes what is proposed', config.targets[0].normalization_scale === scale2 && config.run.advanced.initial_alpha === (alpha2 ?? alpha),
    JSON.stringify({ scale: config.targets[0].normalization_scale, alpha: config.run.advanced.initial_alpha }));
  check('the line goes, and the page says what was applied', await until(`!(${READY})`, 30)
    && (await evaluate(BANNER)) === `Calibration applied: ${what2}, as one Undo step.`, await evaluate(BANNER));
  await evaluate(`${TOOL('Undo')}.click()`);
  config = await stored();
  check('ONE Undo takes both back; the answered line stays away, the block in Run status still offers Apply', config.targets[0].normalization_scale === 1 && config.run.advanced.initial_alpha === alpha
    && !(await until(`!!(${READY})`, 15)), JSON.stringify({ scale: config.targets[0].normalization_scale, alpha: config.run.advanced.initial_alpha }));
  await send('Page.reload');
  await until(`!!(${BASELINE}) && !!(${CHIP})`, 200);
  check('after a reload the answered line still stays away', !(await until(`!!(${READY})`, 30)) && (await evaluate(`localStorage.getItem('gator-workbench-calibration-answered-v1')`)) === dir2);

  // ---- a run of another task than the page holds (record 7.214) -----------------------------------------------------------------
  // The second run's status as it is, except FIXTURE values: it calibrated another task, whose row "score" has the same ID and
  // limits as the page's row, and the run had Scale 2 and Initial alpha 0.02. Nothing of the page's rows may stand in its table.
  const OTHER = 'synthetic:another_task';
  let foreign = true;
  await page.intercept(['*/api/runs/status*'], async params => {
    if (!foreign) return page.pass(params.requestId);
    const real = await (await fetch(params.request.url)).json();
    const fixture = real.calibration?.result;
    if (fixture) { fixture.task_key = OTHER; fixture.rows[0].scale_stated = 2; Object.assign(fixture.initial_alpha, { used: 0.02, proposed: 0.045, note: null }); }
    return page.fulfil(params.requestId, 200, real);
  });
  await send('Page.reload');
  check('a run of another task: the block names both tasks and where to choose the run\'s task', await until(`!!${BLOCK}?.querySelector('.other-task')`, 200)
    && (await evaluate(`${BLOCK}.querySelector('.other-task').textContent.replace(/\\s+/g, ' ')`)) === `This run calibrated ${OTHER}; the page holds synthetic:gpdk045_ota5. The table shows the Scales the run had. To apply the proposals, choose ${OTHER} in the Tasks window.`,
    await evaluate(`${BLOCK}?.textContent.slice(0, 300)`));
  const foreignCells = await cells();
  check('...the Scale column is the run\'s own ("Scale in the run" 2), not the page\'s row of the same ID (1), and no row is "not applied"',
    (await evaluate(`[...${BLOCK}.querySelectorAll('thead th')].map(th => th.textContent).join('|')`)).includes('|Scale in the run|')
    && foreignCells.length === 1 && foreignCells[0][4] === '2' && foreignCells[0][5] === String(scale2) && !/not applied|no such row/.test(await evaluate(`${BLOCK}.textContent`)), JSON.stringify(foreignCells));
  check('...the Initial alpha is the run\'s', (await evaluate(`${BLOCK}.querySelector('.calibration-alpha').textContent`)).startsWith('Initial alpha (RL model): the run had 0.02; proposed 0.045'),
    await evaluate(`${BLOCK}.querySelector('.calibration-alpha').textContent`));
  check('...and Apply rests, saying which task it waits for', await evaluate(`${APPLY}.disabled`) && (await evaluate(HINT)) === `Apply waits until the page holds ${OTHER}.`, await evaluate(HINT));
  await page.shot(path.join(out, 'calibration-3-other-task.png'), `document.querySelector('footer')`);
  foreign = false;
  await send('Page.reload');
  check('the same run of the page\'s own task shows the page\'s Scale again', await until(`!!(${APPLY}) && !${BLOCK}.querySelector('.other-task')
    && [...${BLOCK}.querySelectorAll('thead th')].some(th => th.textContent === 'Scale now')`, 200), await evaluate(`${BLOCK}?.textContent.slice(0, 300)`));

  check('no error in the page console', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
