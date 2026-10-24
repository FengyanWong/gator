// Browser check of the editor columns after the review of 2026-10-03 ("are there any columns redundant?", record 7.172):
//   - Probes: no result_source and no expression column; `signal` reads "Expression"; a Maestro output's Probe ID is shown,
//     not typed - it follows the output name typed into source_name, and so do the spec equations that use it, in ONE Undo
//     step; "Add" makes a probe that measures the way the task's others do (it was backend_profile in a Maestro task),
//     named probe_3 (branch record SIF-50);
//   - Specs: no "target ± tolerance" in the Constraint list and no target or tolerance column; a new spec (spec_3) whose
//     equation becomes another probe takes that probe's unit while it has no limits; an empty limit reads "no limit", an
//     empty Scale "auto" (branch record SIF-49), and an empty bound the row's Limit uses "needed" - a new spec's Lower, both
//     of an interval (branch record SIF-135); the zero-floor hint names an interval from 0 and goes once its Margin sides
//     is upper (branch record SIF-50); its button beside it sets Margin sides to upper on every row it names, one Undo step
//     (branch record SIF-107); the line under the formula bar that names an Undo goes with the next edit (branch record
//     SIF-132);
//   - Parameters: initial_value is not shown; value_type, step, scale and ratio come after "More columns"; on a follower row
//     (binding_group set) the fields its leader decides are greyed, with why; a word typed into Ratio is refused in words;
//     a validation answer without a count reads "The optimizer searches ? of N rows." (review of branch record SIF-50; the
//     words of branch record SIF-73);
//   - Parameters with rows like the user's VCO, their tied rows open: at 1366 x 768 every instance path of up to 12
//     characters is whole and nothing else is cut but Notes, which gives way first; at 1680 x 1050 Instance takes its
//     natural 14 characters and Notes the room; the table does not scroll sideways, nor the page (branch record SIF-119);
//   - and as the user had them, a leader counting "▸31" and the Matched devices box open over the folded rows: at 1366 x 768
//     the table does not scroll sideways either, and IDs of 12 characters are whole, a tied row's too; at 1680 x 1050 an
//     ID and Tied to take their natural 12 characters, no wider than Instance; with the circuit shown the ID is no wider
//     than Instance either, nothing is cut but Notes and nothing scrolls sideways (branch record SIF-131).
// HERMETIC (lib/harness.mjs): validation and Matched devices are answered with canned answers labelled FIXTURE, other reads
// pass, every other writing request is refused. A temporary browser profile: the user's saved configuration is not touched.
// Exit code 1 if any check fails. Pictures: zero_floor_button.png, parameters_matched_1366.png, parameters_1366.png, in the
// folder given as the first argument.
import path from 'node:path';
import { check, launchEdge, mockStarter, outDir, reportRefused, runChecks, showCircuit, sleep, validConfiguration, workbenchUrl } from './lib/harness.mjs';

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
// Parameters rows like the user's VCO (FIXTURE, made up here): its seven leaders and their notes, the four widths with seven
// tied rows each and the length with 31 - the VCO's 66 rows, so that a leader's first cell counts "▸31" (branch record
// SIF-131) - and three leaders more: instance paths of 6 to 12 characters - DUT/MNA1 is the VCO's own, DUT/XBUF/MP4 the
// widest 12 (branch record SIF-119) - and IDs of 12, a tied row's too, indented (wn_tail_bias, wn_mirror_f1; SIF-131).
const VCO_ROW = (variable_id, instance_path, parameter_name, lower, upper, notes, more = {}) => ({ variable_id, instance_path, parameter_name,
  unit: parameter_name === 'r' ? 'ohm' : 'm', optimized: true, value_type: 'continuous', scale: 'linear', lower, upper, notes: `${notes} (FIXTURE)`, ...more });
const VCO_LEADERS = [
  VCO_ROW('wn_main', 'DUT/MNA1', 'w', 1e-6, 10e-6, 'main-inverter NMOS width; scales all four stages'),
  VCO_ROW('wp_main', 'DUT/MPA1', 'w', 2e-6, 20e-6, 'main-inverter PMOS width (2x the NMOS)'),
  VCO_ROW('wn_aux', 'DUT/MNX1', 'w', 250e-9, 4e-6, 'auxiliary (cross-coupled) NMOS width'),
  VCO_ROW('wp_aux', 'DUT/MPX1', 'w', 500e-9, 8e-6, 'auxiliary PMOS width'),
  VCO_ROW('l', 'DUT/MNA1', 'l', 45e-9, 120e-9, 'channel length of all 32 transistors'),
  VCO_ROW('r1_r', 'DUT/R1', 'r', 2000, 3250, 'R1 (VIN -> CTRL); the paper gives 2.5 kohm'),
  VCO_ROW('r2_r', 'DUT/R2', 'r', 300, 1500, 'R2 (CTRL -> VSS); starts at the paper value'),
  VCO_ROW('wn_tail_bias', 'DUT/I3/MNT12', 'w', 1e-6, 8e-6, 'tail NMOS of the bias'),
  VCO_ROW('wn_mirror', 'DUT/I3/MNT11', 'w', 1e-6, 8e-6, 'bias mirror NMOS'),
  VCO_ROW('wp_buf', 'DUT/XBUF/MP4', 'w', 1e-6, 8e-6, 'output buffer PMOS')];
const FOLLOW = (variable_id, instance_path, parameter_name, lead) => VCO_ROW(variable_id, instance_path, parameter_name, null, null, `follows ${lead}`,
  { binding_group: lead, ratio: 1 });
const TRANSISTORS = ['MNA', 'MPA', 'MNX', 'MPX'].flatMap(device => [1, 2, 3, 4, 5, 6, 7, 8].map(n => `DUT/${device}${n}`));
const VCO = [...VCO_LEADERS, ...[['wn_main', 'MNA'], ['wp_main', 'MPA'], ['wn_aux', 'MNX'], ['wp_aux', 'MPX']].flatMap(([lead, device]) =>
  [2, 3, 4, 5, 6, 7, 8].map(n => FOLLOW(`${lead}_f${n - 1}`, `DUT/${device}${n}`, 'w', lead))),
  ...TRANSISTORS.slice(1).map((device, n) => FOLLOW(`l_f${n + 1}`, device, 'l', 'l')), FOLLOW('wn_mirror_f1', 'DUT/I3/MNT13', 'w', 'wn_mirror')];
// The Matched devices answer for these rows (FIXTURE, made up in the backend's words, structures.py): the VCO's eight
// cross-coupled pairs, each already tied - what the user's box held open over the table (branch record SIF-131).
const PAIRS = ['MNX', 'MPX'].flatMap(device => [1, 3, 5, 7].map(n => [`DUT/${device}${n}`, `DUT/${device}${n + 1}`]));
const PAIR_TEXT = ([a, b]) => `${a} and ${b} are a cross-coupled pair: each gate is on the other's drain.`;
const MATCHED = { applicable: true, independent_before: VCO_LEADERS.length, note: 'FIXTURE: pairs made up for this check.',
  structures: PAIRS.map(devices => ({ kind: 'cross_coupled_pair', devices, text: PAIR_TEXT(devices) })),
  suggestions: PAIRS.map(devices => { const follower = VCO.find(r => r.instance_path === devices[1] && r.parameter_name === 'w');
    return { id: `cross_coupled_pair:${devices.join('+')}`, kind: 'cross_coupled_pair', devices, text: PAIR_TEXT(devices), default: false, note: '', acts: false,
      changes: [{ device: devices[1], parameter: 'w', variable_id: follower.variable_id, action: 'skip', reason: `already follows ${follower.binding_group}` }] }; }) };

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
    if (name === '/api/parameters/matched') return page.fulfil(params.requestId, 200, MATCHED);   // asks only: nothing is tied before Apply
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
  // An empty number box says what empty means (branch record SIF-49): a bare "-" said neither. The bound the row's Limit uses
  // says "needed" (branch record SIF-135): it said "no limit" too, beside the error that asked for it.
  const BOUNDS = row => `JSON.stringify([${CELL(row, 'lower')}.value, ${CELL(row, 'lower')}.placeholder, ${CELL(row, 'upper')}.value, ${CELL(row, 'upper')}.placeholder])`;
  check('a one-sided spec\'s other limit reads "no limit" when empty, not a bare "-" (branch record SIF-49); the one its Limit "≥ lower" uses, "needed" (SIF-135)',
    await evaluate(`${CELL(0, 'upper')}.value === '' && ${CELL(0, 'upper')}.placeholder === 'no limit' && ${CELL(0, 'lower')}.placeholder === 'needed'`),
    await evaluate(BOUNDS(0)));
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
  check('...its Limit "≥ lower" with no lower yet: its empty Lower reads "needed", its Upper "no limit" (SIF-135)', config.targets[2].constraint === '>='
    && config.targets[2].lower == null && await evaluate(`${BOUNDS(2)} === '["","needed","","no limit"]'`), await evaluate(BOUNDS(2)));
  await typeInto(CELL(2, 'equation'), 'm_vmax');
  config = await saved();
  check('a spec with no limits yet whose equation becomes another probe takes that probe\'s unit', config.targets[2].equation === 'm_vmax' && config.targets[2].unit === 'V',
    JSON.stringify(config.targets[2]));
  // The zero-floor hint names its rows and goes once their Margin sides is upper: it stayed after the user followed it
  // (branch record SIF-50).
  const HINT = `(${EDITORS}.querySelector('.zero-floor-hint')?.textContent ?? '')`;
  check('(set-up) no zero-floor hint while no interval starts at 0', await evaluate(`!${EDITORS}.querySelector('.zero-floor-hint')`), await evaluate(HINT));
  await page.setValue(CELL(2, 'constraint'), 'interval|none');
  check('an interval uses both bounds: both empty ones read "needed" (SIF-135)', await until(`${BOUNDS(2)} === '["","needed","","needed"]'`, 20), await evaluate(BOUNDS(2)));
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
  check('...the line under the formula bar names the Undo (SIF-97)', await until(`${SAID} === 'Undo: Specs spec_3 (Margin sides).'`), await evaluate(SAID));
  await evaluate(`${MORE}.click()`);
  await until(`!!${CELL(2, 'margin_sides')}`);
  await page.setValue(CELL(2, 'margin_sides'), 'upper');
  check('...and the hint goes once that row\'s Margin sides is upper', await until(`!${EDITORS}.querySelector('.zero-floor-hint')`), await evaluate(HINT));
  // Branch record SIF-132: the next change takes the Undo's line away; it stood under the edits after it (zero_floor_button.png).
  check('...and that edit takes the Undo\'s line away (SIF-132)', await until(`${SAID} === ''`), await evaluate(SAID));
  await evaluate(`${MORE}.click()`);
  await until(`!${CELL(2, 'margin_sides')}`);
  // Several rows: the button counts them and sets them all, one Undo step (branch record SIF-107).
  await evaluate(`${TOOL('Undo')}.click()`);                // spec_3's Margin sides back: named again
  await page.setValue(CELL(1, 'constraint'), 'interval|none');
  await typeInto(CELL(1, 'lower'), '0');
  await typeInto(CELL(1, 'upper'), '1');
  check('(set-up) two intervals from 0 are named, and the button reads "Set Margin sides to upper on all 2"', await until(`${HINT}.startsWith('half_freq, spec_3: ')`)
    && await evaluate(`${SET_UPPER}?.textContent === 'Set Margin sides to upper on all 2'`), `${await evaluate(HINT)} / ${await evaluate(`${SET_UPPER}?.textContent ?? 'no button'`)}`);
  check('...with no Undo line left from before the edits (SIF-132)', !/^(Undo|Redo)\b/.test(await evaluate(SAID)), await evaluate(SAID));
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

  // ---- Parameters at 1366 x 768 and 1680 x 1050: an instance path whole (branch record SIF-119), an ID as wide as its values
  // and nothing scrolls sideways (branch record SIF-131) ----------------------------------------------------------------------
  // The user's VCO at 1366 x 768 read "DUT/M..." in every Instance (DUT/MNA1): there the table stands at its columns' minimum
  // widths, and Instance had the 84 px of every text box (SIF-119). The table still scrolled sideways by a few px: its leaders
  // count up to "▸31" in their first cell, and the ID kept 140 px for IDs of 7 characters (SIF-131). Rows like the VCO's, so
  // that the table box scrolls up and down beside a scroll bar as it did on the user's page (the bar takes 15 px of the
  // table's room): first as the user had them, the tied rows folded and the Matched devices box open over them, then the tied
  // rows open.
  await page.seed({ config: { ...CONFIG, parameters: VCO }, when: 'always' });
  await page.viewport(1366, 768);
  await send('Page.navigate', { url: APP });
  await until(`!!${EDITORS}?.querySelector('table.editor tbody tr')`, 150);
  await openTab('Parameters');
  check('(set-up) the page opens again on rows like the VCO\'s, the tied rows folded under their leaders',
    await until(`${EDITORS}.querySelectorAll('table.editor tbody tr:not([hidden])').length === ${VCO_LEADERS.length}`));
  const fit = () => evaluate(`(() => { const box = ${EDITORS}.querySelector('.scroll'), table = box.querySelector('table.editor');
    const width = f => Math.round(table.querySelector(\`thead th[data-field="\${f}"]\`).getBoundingClientRect().width);
    const boxes = [...table.querySelectorAll('tbody tr:not([hidden]) td[data-field] input:not([type="checkbox"])')];
    const of = field => boxes.filter(i => i.closest('td').dataset.field === field), paths = of('instance_path'), ids = of('variable_id');
    const longest = list => Math.max(0, ...list.map(i => i.value.length));
    return { rows: paths.length, longest: longest(paths), size: paths[0]?.size, ids: longest(ids), tiedIds: longest(ids.filter(i => i.closest('tr.tied'))),
      idSize: ids[0]?.size, tiedToSize: of('binding_group')[0]?.size,
      counts: [...new Set([...table.querySelectorAll('tbody tr:not([hidden]) .tie-toggle')].map(b => b.textContent))],
      cut: [...new Set(boxes.filter(i => i.scrollWidth > i.clientWidth).map(i => i.closest('td').dataset.field))],
      widths: { tick: Math.round(table.querySelector('thead th.sel').getBoundingClientRect().width),
        ...Object.fromEntries(['variable_id', 'instance_path', 'binding_group', 'notes'].map(f => [f, width(f)])) },
      bar: box.offsetWidth - box.clientWidth, sideways: box.scrollWidth - box.clientWidth,
      page: document.documentElement.scrollWidth - document.documentElement.clientWidth }; })()`);
  const BOX = `${EDITORS}.querySelector('.matched-devices')`;
  await evaluate(`${TOOL('Matched devices...')}.click()`);
  check('(set-up) at 1366 x 768 Matched devices opens over the leaders with the eight pairs of the VCO',
    await until(`${BOX}?.querySelectorAll('tbody tr').length === ${PAIRS.length}`), await evaluate(`${BOX}?.textContent.slice(0, 200) ?? 'no box'`));
  await sleep(500);
  const asked = await fit();
  check('(set-up) ...a leader counts "▸31" in its first cell, and the rows scroll up and down beside a scroll bar',
    asked.counts.includes('▸31') && asked.bar > 0, JSON.stringify(asked));
  check('with Matched devices open neither the table nor the page scrolls sideways, and nothing is cut but Notes (branch record SIF-131)',
    asked.sideways <= 0 && asked.page <= 0 && asked.cut.every(f => f === 'notes'), JSON.stringify(asked));
  await page.shot(path.join(out, 'parameters_matched_1366.png'), EDITORS, { maxHeight: 640 });
  await evaluate(`${BOX}.querySelector('button[title^="Close"]').click()`);   // the rows stay as they are
  await until(`!${BOX}`);
  await evaluate(`${EDITORS}.querySelectorAll('table.editor .tie-toggle[aria-expanded="false"]').forEach(b => b.click())`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr:not([hidden])').length === ${VCO.length}`);
  await sleep(300);
  const narrow = await fit();
  check(`(set-up) at 1366 x 768 the ${VCO.length} rows, the tied ones open, scroll up and down beside a scroll bar; the longest path has 12 characters, `
    + 'and so has the longest ID, a tied row\'s too', narrow.rows === VCO.length && narrow.bar > 0 && narrow.longest === 12 && narrow.ids === 12 && narrow.tiedIds === 12,
    JSON.stringify(narrow));
  check('at 1366 x 768 every ID and Instance is whole, and nothing else is cut but Notes (branch record SIF-119, SIF-131)', narrow.cut.every(f => f === 'notes'), JSON.stringify(narrow));
  check('...Notes gives way first, narrower than Instance now, and neither the table nor the page scrolls sideways (the Matched devices box closed)',
    narrow.widths.notes < narrow.widths.instance_path && narrow.sideways <= 0 && narrow.page <= 0, JSON.stringify(narrow));
  await page.shot(path.join(out, 'parameters_1366.png'), EDITORS, { maxHeight: 420 });
  await page.viewport(1680, 1050); await sleep(500);
  const wide = await fit();
  check('at 1680 x 1050 Instance takes its natural 14 characters and Notes the room: nothing cut but Notes, no sideways scroll',
    wide.size === 14 && wide.widths.notes > wide.widths.instance_path && wide.cut.every(f => f === 'notes') && wide.sideways <= 0 && wide.page <= 0,
    JSON.stringify(wide));
  check('...and an ID and Tied to their natural 12 characters, neither wider than Instance (branch record SIF-131: 183 and 175 px for IDs of 7)',
    wide.idSize === 12 && wide.tiedToSize === 12 && Math.max(wide.widths.variable_id, wide.widths.binding_group) <= wide.widths.instance_path, JSON.stringify(wide));
  check('(set-up) "Show circuit" brings the circuit column beside the rows', await showCircuit(page));
  await sleep(500);
  const beside = await fit();
  check('at 1680 x 1050 with the circuit shown nothing is cut but Notes, no sideways scroll, and the ID is no wider than Instance: Notes has its room (SIF-131)',
    beside.cut.every(f => f === 'notes') && beside.sideways <= 0 && beside.page <= 0 && beside.widths.variable_id <= beside.widths.instance_path, JSON.stringify(beside));
  reportRefused(refused);
});
