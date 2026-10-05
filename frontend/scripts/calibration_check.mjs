// Browser check of the calibration that goes with the Baseline simulation (record 7.197; one button since record 7.202, the
// "+ calibration" tick gone): the header button alone, a REAL run on the synthetic MOCK task (free, no bridge, no Virtuoso) of
// the baseline plus 64 random designs - also in a browser that had unticked the old tick - the proposals in Run status - a
// Scale per Specs row and the Initial alpha - and Apply, which writes them into the page's configuration as ONE Undo step
// and only into rows that still are the rows the run simulated.
// It starts runs, so it REFUSES the default backend: give it a SCRATCH backend and a scratch output root (run_checks.sh does;
// by hand as run_control_live_check.mjs says). Takes about 40 s. Exit code 1 if any check fails.
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
  const BASELINE = `[...document.querySelectorAll('header button')].find(b => b.textContent === 'Baseline simulation')`;
  const CHIP = `document.querySelector('header button.run-chip')`;
  const BLOCK = `document.querySelector('footer .calibration')`, APPLY = `[...(${BLOCK}?.querySelectorAll('button') ?? [])].find(b => b.textContent === 'Apply calibration')`;
  const HINT = `${BLOCK}?.querySelector('.row .hint')?.textContent`;
  const EDITORS = `document.querySelector('.editors')`;
  const TOOL = text => `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const stored = async () => { await page.saved(); return page.stored(); };
  const cells = () => evaluate(`[...(${BLOCK}?.querySelectorAll('table tbody tr') ?? [])].map(tr => [...tr.children].map(td => td.textContent.trim()))`);

  await page.trackSaves();
  // This browser had unticked "+ calibration" under record 7.197: the choice it kept is no longer read.
  await page.seed({ config: CONFIG, when: 'once', also: `localStorage.setItem('gator-workbench-baseline-calibration-v1', 'off');` });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${BASELINE}) && !${BASELINE}.disabled`, 200))) throw new Error('the baseline button never became available: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- one button, no tick ----------------------------------------------------------------------------------------------
  check('no "+ calibration" tick and no Single baseline simulation in the header', await evaluate(`!document.querySelector('header input[type=checkbox]')
    && !document.querySelector('header').textContent.includes('calibration') && !document.querySelector('header').textContent.includes('Single baseline')`));
  const title = await evaluate(`${BASELINE}.title`);
  check('its tooltip says what follows the baseline, that nothing changes by itself, and how to keep the baseline alone',
    /then 64 random designs over the Parameters ranges in the same run/.test(title) && /nothing changes by itself/.test(title) && /For the baseline alone, Abort once the random designs begin/.test(title), title);
  await page.shot(path.join(out, 'calibration-0-header.png'), `document.querySelector('header')`, { pad: 4 });

  // ---- the run: the baseline, then 64 random designs ------------------------------------------------------------------------
  await evaluate(`${BASELINE}.click()`);
  // A start prepares the run folder and launches a worker: seconds on a busy machine, so the waits are long.
  check('a MOCK run asks nothing and starts', await until(`!!localStorage.getItem('gator-workbench-current-run-v1')`, 900) && dialogs.length === 0, JSON.stringify(dialogs));
  const dir = await evaluate(`localStorage.getItem('gator-workbench-current-run-v1')`);
  check('while it runs, Run status says what is coming', await until(`/64 random designs are simulated; the proposals appear here when the run has ended/.test(${BLOCK}?.textContent ?? '') || !!(${APPLY})`, 300));
  check('the run completes with 65 evaluations charged', await until(`/^completed 65 \\/ 65 \\[MOCK\\]$/.test(${CHIP}?.textContent ?? '')`, 600), await evaluate(`${CHIP}?.textContent`));
  const status = await get('runs/status', { run_dir: dir });
  const result = status.calibration?.result, row = result?.rows?.[0];
  check('the backend says: a baseline run asked for 64 designs, on one lane, 65 evaluations', JSON.stringify(status.calibration?.request) === JSON.stringify({ designs: 64, lanes: 1, evaluations: 65 })
    && status.budget?.charged === 65 && status.learner_updates === 0, JSON.stringify({ request: status.calibration?.request, charged: status.budget?.charged, updates: status.learner_updates }));
  check('its proposals: a Scale for the row "score" and an Initial alpha, every recorded reward worked out again', result?.status === 'calibrated' && row?.metric_id === 'score'
    && typeof row?.proposed_scale === 'number' && typeof result?.initial_alpha?.proposed === 'number' && result.reward_check.reproduced === 64, JSON.stringify(result).slice(0, 400));
  const scale = row.proposed_scale, alpha = result.initial_alpha.proposed;

  // ---- the block in Run status ----------------------------------------------------------------------------------------------
  check('Run status shows the calibration with its Apply button', await until(`!!(${APPLY}) && !${APPLY}.disabled`, 100), await evaluate(`${BLOCK}?.textContent.slice(0, 300)`));
  const shown = await cells();
  check('one line per Specs row: limit, designs that miss it, typical miss, the Scale now and the proposal', shown.length === 1 && shown[0][0] === 'score' && shown[0][1] === '≥ 0.95'
    && shown[0][2] === `${row.misses} of 64` && shown[0][4] === '1' && shown[0][5] === String(scale), JSON.stringify(shown));
  check('the Initial alpha: what the page holds and what is proposed', await evaluate(`${BLOCK}.querySelector('.calibration-alpha').textContent`).then(t => t.startsWith(`Initial alpha (RL networks): now 0.01; proposed ${alpha}`)),
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

  check('no error in the page console', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
