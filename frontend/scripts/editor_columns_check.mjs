// Browser check of the editor columns after the review of 2026-10-03 ("are there any columns redundant?", record 7.172):
//   - Probes: no result_source and no expression column; `signal` reads "Expression"; a Maestro output's Probe ID is shown,
//     not typed - it follows the output name typed into source_name, and so do the spec equations that use it, in ONE Undo
//     step; "Add" makes a probe that measures the way the task's others do (it was backend_profile in a Maestro task);
//   - Specs: no "target ± tolerance" in the Constraint list and no target or tolerance column; a new spec whose equation
//     becomes another probe takes that probe's unit while it has no limits;
//   - Parameters: initial_value is not shown; value_type, step, scale and ratio come after "More columns"; on a follower row
//     (binding_group set) the fields its leader decides are greyed, with why.
// HERMETIC (lib/harness.mjs): validation is answered with a canned valid report labelled FIXTURE, other reads pass, every
// other writing request is refused. A temporary browser profile: the user's saved configuration is not touched.
// Exit code 1 if any check fails.
import { check, launchEdge, mockStarter, reportRefused, runChecks, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const browser = await launchEdge('editorcolumns');
const VALID = validConfiguration({ mock: true });
// Two Maestro outputs (FIXTURE): what a task saved from a cell holds.
const PROBES = [
  { measurement_id: 'm_freq', analysis: 'tran', result_source: 'ade_output', source_name: 'freq', signal: 'frequency(VT("/OUT"))', unit: 'Hz', notes: 'FIXTURE' },
  { measurement_id: 'm_vmax', analysis: 'tran', result_source: 'ade_output', source_name: 'vmax', signal: 'ymax(VT("/OUT"))', unit: 'V', notes: 'FIXTURE' }];
const SPECS = [
  { metric_id: 'freq', equation: 'm_freq', unit: 'Hz', constraint: '>=', lower: 1e9, upper: null, normalization_scale: 1e8 },
  { metric_id: 'half_freq', equation: 'm_freq / 2', unit: 'Hz', constraint: '>=', lower: 5e8, upper: null, normalization_scale: 1e8 }];

await runChecks(browser, async () => {
  const starter = await mockStarter(APP);
  const CONFIG = { schema_version: 'gator-workbench-config-v1', ...starter, measurements: PROBES, targets: SPECS,
    run: { ...starter.run, mode: 'scratch' }, output: { experiment_name: 'fixture' }, research: {} };
  delete CONFIG.run.model_source;
  const page = await browser.open();
  const { send, evaluate, until } = page;
  const refused = [];
  await page.intercept(['*/api/*'], params => {
    const name = new URL(params.request.url).pathname;
    if (name === '/api/config/validate') return page.fulfil(params.requestId, 200, VALID);
    return page.readOrRefuse(params, refused, { reads: true });
  });
  await page.trackSaves();
  await page.seed({ config: CONFIG, when: 'missing' });
  await send('Page.navigate', { url: APP });

  const EDITORS = `document.querySelector('section.editors')`;
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs > button')].find(b => b.textContent.trim().startsWith(${JSON.stringify(name)})).click()`);
  const TOOL = text => `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const MORE = `[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => /^(More|Fewer) columns/.test(b.textContent.trim()))`;
  const fields = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).filter(Boolean)`);
  const labels = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].filter(h => h.dataset.field).map(h => h.textContent.replace(' *', '').trim())`);
  const CELL = (row, field) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].findIndex(h => h.dataset.field === ${JSON.stringify(field)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}]?.children[at]?.querySelector('input, select'); })()`;
  const typeInto = async (cell, text) => {
    await evaluate(`(() => { const i = ${cell}; i.focus(); i.select(); })()`);
    for (const ch of text) {
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch, unmodifiedText: ch });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch });
    }
    await evaluate(`${cell}.blur()`);
  };
  const saved = page.savedConfig;
  if (!(await until(`!!${EDITORS}?.querySelector('table.editor tbody tr')`, 150))) throw new Error('the editors never showed rows');

  // ---- Probes -------------------------------------------------------------------------------------------------------
  await openTab('Probes');
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 2`);
  const probeFields = await fields();
  check('Probes shows no result_source and no expression column', !probeFields.includes('result_source') && !probeFields.includes('expression'), JSON.stringify(probeFields));
  check('the column holding a Maestro output\'s expression reads "Expression"', (await labels())[probeFields.indexOf('signal')] === 'Expression', JSON.stringify(await labels()));
  check('a Maestro output\'s Probe ID is shown, not typed', await evaluate(`${CELL(0, 'measurement_id')}.readOnly === true`));
  await typeInto(CELL(0, 'source_name'), 'f_osc');
  let config = await saved();
  check('the Probe ID follows the typed output name, and so does the spec equation that used it',
    config.measurements[0].measurement_id === 'm_f_osc' && config.measurements[0].source_name === 'f_osc'
      && config.targets[0].equation === 'm_f_osc' && config.targets[1].equation === 'm_f_osc / 2',
    JSON.stringify([config.measurements[0].measurement_id, config.targets.map(t => t.equation)]));
  await evaluate(`${TOOL('Undo')}.click()`);
  config = await saved();
  check('one Undo takes the name, the ID and the equations back together',
    config.measurements[0].measurement_id === 'm_freq' && config.targets[1].equation === 'm_freq / 2', JSON.stringify(config.targets.map(t => t.equation)));
  await evaluate(`${TOOL('Add')}.click()`);
  config = await saved();
  check('"Add" makes a probe that measures the way the task\'s other probes do (a Maestro output)', config.measurements[2]?.result_source === 'ade_output',
    JSON.stringify(config.measurements[2]));
  await evaluate(`${TOOL('Undo')}.click()`);

  // ---- Specs --------------------------------------------------------------------------------------------------------
  await openTab('Specs');
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 2`);
  const choices = await evaluate(`[...${EDITORS}.querySelector('select[aria-label="Constraint"]').options].map(o => o.textContent)`);
  const specFields = await fields();
  check('the Constraint list offers no "target ± tolerance", and Specs has no target or tolerance column',
    !choices.some(c => /target/.test(c)) && !specFields.includes('target') && !specFields.includes('tolerance'), JSON.stringify(choices));
  const share = await evaluate(`(() => { const width = f => ${EDITORS}.querySelector(\`table.editor thead th[data-field="\${f}"]\`).getBoundingClientRect().width;
    return { size: [${CELL(0, 'equation')}.size, ${CELL(0, 'lower')}.size], equation: Math.round(width('equation')), lower: Math.round(width('lower')) }; })()`);
  check('the columns share the card by what they hold: an equation is 40 characters wide by nature, a number 11, so Equation is wider than Lower (branch record SIF-28)',
    share.size.join() === '40,11' && share.equation > share.lower, JSON.stringify(share));
  const floor = await evaluate(`parseFloat(getComputedStyle(${CELL(0, 'lower')}).minWidth)`);
  check('...and a number keeps its 11 characters when the table is narrow: text columns give way first (branch record SIF-31)', floor >= 100, String(floor));
  await evaluate(`${TOOL('Add')}.click()`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 3`);
  config = await saved();
  check('(set-up) a new spec starts as the first probe, in its unit', config.targets[2].equation === 'm_freq' && config.targets[2].unit === 'Hz', JSON.stringify(config.targets[2]));
  await typeInto(CELL(2, 'equation'), 'm_vmax');
  config = await saved();
  check('a spec with no limits yet whose equation becomes another probe takes that probe\'s unit', config.targets[2].equation === 'm_vmax' && config.targets[2].unit === 'V',
    JSON.stringify(config.targets[2]));

  // ---- Parameters ---------------------------------------------------------------------------------------------------
  await openTab('Parameters');
  await until(`!!${CELL(0, 'variable_id')}`);
  const before = await fields();
  check('Parameters shows no initial_value, and value_type, step, scale and ratio only after "More columns" (4)',
    !['initial_value', 'value_type', 'step', 'scale', 'ratio'].some(c => before.includes(c)) && /More columns \(4\)/.test(await evaluate(`${MORE}?.textContent ?? ''`)), JSON.stringify(before));
  const follower = await evaluate(`[...${EDITORS}.querySelectorAll('table.editor tbody tr')].findIndex(r => /__/.test(r.querySelector('td:nth-child(2) input')?.value ?? ''))`);
  const off = follower > 0 ? await evaluate(`(() => { const i = ${CELL(follower, 'lower')}; return i ? { disabled: i.disabled, title: i.title } : null; })()`) : null;
  const leaderOn = await evaluate(`${CELL(0, 'lower')}.disabled === false`);
  check('on a follower row its leader\'s fields are greyed, with why; on the leader they take typing',
    follower > 0 && off?.disabled === true && /^Follows /.test(off.title) && leaderOn, JSON.stringify({ follower, off }));
  await evaluate(`${MORE}.click()`);
  await until(`!!${CELL(0, 'ratio')}`);
  const after = await fields();
  check('after "More columns" value_type, step, scale and ratio are there, initial_value still not',
    ['value_type', 'step', 'scale', 'ratio'].every(c => after.includes(c)) && !after.includes('initial_value'), JSON.stringify(after));
  await evaluate(`${MORE}.click()`);
  reportRefused(refused);
});
