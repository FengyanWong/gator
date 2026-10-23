// Browser check of the editor columns after the review of 2026-10-03 ("are there any columns redundant?", record 7.172):
//   - Probes: no result_source and no expression column; `signal` reads "Expression"; a Maestro output's Probe ID is shown,
//     not typed - it follows the output name typed into source_name, and so do the spec equations that use it, in ONE Undo
//     step; "Add" makes a probe that measures the way the task's others do (it was backend_profile in a Maestro task),
//     named probe_3 (branch record SIF-50);
//   - Specs: no "target ± tolerance" in the Constraint list and no target or tolerance column; a new spec (spec_3) whose
//     equation becomes another probe takes that probe's unit while it has no limits; an empty limit reads "no limit", an
//     empty Scale "auto" (branch record SIF-49); the zero-floor hint names an interval from 0 and goes once its Margin sides
//     is upper (branch record SIF-50); its button beside it sets Margin sides to upper on every row it names, one Undo step
//     (branch record SIF-107);
//   - Parameters: initial_value is not shown; value_type, step, scale and ratio come after "More columns"; on a follower row
//     (binding_group set) the fields its leader decides are greyed, with why; a word typed into Ratio is refused in words;
//     a validation answer without a count reads "The optimizer searches ? of N rows." (review of branch record SIF-50; the
//     words of branch record SIF-73).
// HERMETIC (lib/harness.mjs): validation is answered with a canned valid report labelled FIXTURE, other reads pass, every
// other writing request is refused. A temporary browser profile: the user's saved configuration is not touched.
// Exit code 1 if any check fails. Picture: zero_floor_button.png, in the folder given as the first argument.
import path from 'node:path';
import { check, launchEdge, mockStarter, outDir, reportRefused, runChecks, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
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
  check('...named as the tab is: probe_3, not measurement_3 (branch record SIF-50)', config.measurements[2]?.measurement_id === 'probe_3',
    config.measurements[2]?.measurement_id);
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
  // An empty number box says what empty means (branch record SIF-49): a bare "-" said neither.
  check('a one-sided spec\'s other limit reads "no limit" when empty, not a bare "-" (branch record SIF-49)',
    await evaluate(`${CELL(0, 'upper')}.value === '' && ${CELL(0, 'upper')}.placeholder === 'no limit' && ${CELL(0, 'lower')}.placeholder === 'no limit'`),
    await evaluate(`JSON.stringify([${CELL(0, 'upper')}.value, ${CELL(0, 'upper')}.placeholder])`));
  await evaluate(`${MORE}.click()`);
  await until(`!!${CELL(0, 'normalization_scale')}`);
  check('...and an empty Scale reads "auto": as far as the limit itself', await evaluate(`${CELL(0, 'normalization_scale')}?.placeholder === 'auto'`),
    await evaluate(`${CELL(0, 'normalization_scale')}?.placeholder`));
  await evaluate(`${MORE}.click()`);
  await until(`!${CELL(0, 'normalization_scale')}`);
  await evaluate(`${TOOL('Add')}.click()`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 3`);
  config = await saved();
  check('(set-up) a new spec starts as the first probe, in its unit', config.targets[2].equation === 'm_freq' && config.targets[2].unit === 'Hz', JSON.stringify(config.targets[2]));
  check('...named as the tab is: spec_3, not target_3 (branch record SIF-50)', config.targets[2].metric_id === 'spec_3', config.targets[2].metric_id);
  await typeInto(CELL(2, 'equation'), 'm_vmax');
  config = await saved();
  check('a spec with no limits yet whose equation becomes another probe takes that probe\'s unit', config.targets[2].equation === 'm_vmax' && config.targets[2].unit === 'V',
    JSON.stringify(config.targets[2]));
  // The zero-floor hint names its rows and goes once their Margin sides is upper: it stayed after the user followed it
  // (branch record SIF-50).
  const HINT = `(${EDITORS}.querySelector('.zero-floor-hint')?.textContent ?? '')`;
  check('(set-up) no zero-floor hint while no interval starts at 0', await evaluate(`!${EDITORS}.querySelector('.zero-floor-hint')`), await evaluate(HINT));
  await page.setValue(CELL(2, 'constraint'), 'interval|none');
  await typeInto(CELL(2, 'lower'), '0');
  await typeInto(CELL(2, 'upper'), '1');
  check('an interval from 0 is named in the zero-floor hint, with where Margin sides is (branch record SIF-50)',
    await until(`${HINT} === 'spec_3: the margin also measures the distance to 0. If 0 is only a physical floor, set Margin sides to upper (More columns).'`),
    `${await evaluate(HINT)} / ${JSON.stringify((await saved()).targets[2])}`);
  // Branch record SIF-107: a button beside the hint - not inside its words - sets Margin sides to upper on the rows it names,
  // as one Undo step: the column is behind More columns, so each named row was shown, scrolled to and changed by hand.
  const SET_UPPER = `${EDITORS}.querySelector('.zero-floor > button.zero-floor-set')`;
  const SAID = `(${EDITORS}.querySelector('.paste-note')?.textContent ?? '')`, SIDES = c => JSON.stringify(c.targets.map(t => t.margin_sides ?? null));
  check('beside the hint a button "Set Margin sides to upper" says what it sets (branch record SIF-107)',
    await evaluate(`${SET_UPPER}?.textContent === 'Set Margin sides to upper' && !${EDITORS}.querySelector('.zero-floor-hint button')
      && /^Set Margin sides to upper: spec_3 then counts only the upper limit .*feasibility still checks both limits/.test(${SET_UPPER}.title)`),
    await evaluate(`${SET_UPPER}?.outerHTML.slice(0, 300) ?? 'no button'`));
  const sidesBefore = (await saved()).targets.map(t => t.margin_sides ?? null);
  await evaluate(`${SET_UPPER}.click()`);
  config = await saved();
  check('...a press sets it on spec_3 alone, the hint goes, and the line under the formula bar says so', config.targets[2].margin_sides === 'upper'
    && JSON.stringify(config.targets.slice(0, 2).map(t => t.margin_sides ?? null)) === JSON.stringify(sidesBefore.slice(0, 2))
    && await until(`!${EDITORS}.querySelector('.zero-floor')`) && await evaluate(`${SAID} === 'Margin sides set to upper on spec_3. Undo takes it back.'`),
    `${SIDES(config)} / ${await evaluate(SAID)}`);
  await evaluate(`${TOOL('Undo')}.click()`);
  config = await saved();
  check('...and one Undo takes it back, the hint with it', (config.targets[2].margin_sides ?? null) === sidesBefore[2] && await until(`${HINT}.startsWith('spec_3: ')`),
    `${SIDES(config)} / ${await evaluate(HINT)}`);
  await evaluate(`${MORE}.click()`);
  await until(`!!${CELL(2, 'margin_sides')}`);
  await page.setValue(CELL(2, 'margin_sides'), 'upper');
  check('...and the hint goes once that row\'s Margin sides is upper', await until(`!${EDITORS}.querySelector('.zero-floor-hint')`), await evaluate(HINT));
  await evaluate(`${MORE}.click()`);
  await until(`!${CELL(2, 'margin_sides')}`);
  // Several rows: the button counts them and sets them all, one Undo step (branch record SIF-107).
  await evaluate(`${TOOL('Undo')}.click()`);                // spec_3's Margin sides back: named again
  await page.setValue(CELL(1, 'constraint'), 'interval|none');
  await typeInto(CELL(1, 'lower'), '0');
  await typeInto(CELL(1, 'upper'), '1');
  check('(set-up) two intervals from 0 are named, and the button reads "Set Margin sides to upper on all 2"', await until(`${HINT}.startsWith('half_freq, spec_3: ')`)
    && await evaluate(`${SET_UPPER}?.textContent === 'Set Margin sides to upper on all 2'`), `${await evaluate(HINT)} / ${await evaluate(`${SET_UPPER}?.textContent ?? 'no button'`)}`);
  await page.shot(path.join(out, 'zero_floor_button.png'), EDITORS, { maxHeight: 420 });
  await evaluate(`${SET_UPPER}.click()`);
  config = await saved();
  check('...a press sets both and names them', config.targets[1].margin_sides === 'upper' && config.targets[2].margin_sides === 'upper'
    && await evaluate(`${SAID} === 'Margin sides set to upper on half_freq, spec_3. Undo takes it back.'`), `${SIDES(config)} / ${await evaluate(SAID)}`);
  await evaluate(`${TOOL('Undo')}.click()`);
  config = await saved();
  check('...and one Undo takes both back', config.targets[1].margin_sides !== 'upper' && config.targets[2].margin_sides !== 'upper'
    && await until(`${HINT}.startsWith('half_freq, spec_3: ')`), SIDES(config));

  // ---- Parameters ---------------------------------------------------------------------------------------------------
  await openTab('Parameters');
  await until(`!!${CELL(0, 'variable_id')}`);
  // The canned report has no count: an answered validation without one reads "?", not "..." as if still counting (review
  // of branch record SIF-50).
  const FACT = `(${EDITORS}.querySelector('p.fact')?.textContent ?? '')`;
  check('validation answered without a count: the fact line reads "The optimizer searches ? of N rows." (SIF-73)',
    await until(`/^The optimizer searches \\? of \\d+ rows\\.$/.test(${FACT})`), await evaluate(FACT));
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
  // A word typed into a number without a unit is said in words, as a bound's is; it used to vanish on leaving the cell
  // (branch record SIF-49).
  const ratioBefore = (await saved()).parameters[0].ratio;
  await typeInto(CELL(0, 'ratio'), 'half');
  const NOTE = `(document.querySelector('.paste-note')?.textContent ?? '')`;
  check('a word typed into Ratio is refused in words under the formula bar, and the ratio kept (branch record SIF-49)',
    await until(`${NOTE}.startsWith('"half" in Ratio is not a number: type it plain (0.5)')`) && (await saved()).parameters[0].ratio === ratioBefore,
    await evaluate(NOTE));
  await evaluate(`${MORE}.click()`);
  reportRefused(refused);
});
