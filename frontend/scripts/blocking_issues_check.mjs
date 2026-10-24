// Browser check of the header's blocking-issues BUTTON (there is no frontend test runner in this project).
// Same approach as connection_panel_check.mjs: a throwaway headless Edge over the DevTools protocol against the
// RUNNING workbench (default http://127.0.0.1:8765/). EVERY /api/config/validate request is intercepted and answered
// with a canned report labelled FIXTURE, so the shown issues are known. GET requests pass through; every other
// writing request is refused here, so this check can start, save or probe nothing on the backend it runs against.
// The browser profile is new and temporary: the user's saved configuration is not touched.
// What it pins (user request 2026-09-20): the notifier is a button; the list appears when the button is RELEASED, not
// when it is pressed; it lists ALL blocking issues in full and no other; a second press hides it; it follows a new
// validation, closes when nothing blocks, and does not reopen by itself. Since status record 7.56 (user report
// 2026-09-21): a configuration the schema rejects (HTTP 422) is listed one issue per field, at its row, in the backend's
// plain words, with the schema's own text folded under "Technical details" - also for an older backend's answer. It seeds
// the one MOCK task, synthetic:gpdk045_ota5 (status record 7.59). Since 2026-09-29: a settings.json the backend cannot read
// (/api/meta `settings_problem`, answered here) is a full-width line of the header that a click does not dismiss.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 15 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/blocking_issues_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('issues');

// ---- canned answers ------------------------------------------------------------------------------------------
const issue = (level, code, where, message) => ({ level, code, path: where, message: `FIXTURE: ${message}` });
const BLOCKING = [
  issue('error', 'range_inverted', 'parameters[0].lower', 'the lower bound is above the upper bound'),
  issue('blocker', 'heads_divisibility', 'run.network', 'hidden_dim must be divisible by heads'),       // belongs to no editor tab
  issue('error', 'schema', '', 'the configuration was rejected as a whole'),
];
const OTHERS = [issue('warning', 'no_checkpoints', 'output.save_checkpoints', 'checkpoints are off'),
  issue('unresolved', 'circuit_not_loaded', 'circuit', 'not checked against a circuit'), issue('info', 'frozen_no_updates', 'run.mode', 'no updates')];
const report = issues => ({ blocks_run: issues.some(i => i.level === 'error' || i.level === 'blocker'), counts: {}, facts: { circuit_checked: false },
  issues, config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null });
const fixtures = { three: report([OTHERS[0], BLOCKING[0], OTHERS[1], BLOCKING[1], BLOCKING[2], OTHERS[2]]), one: report([BLOCKING[1], OTHERS[0]]), valid: report(OTHERS) };

await runChecks(browser, async () => {
  // The MOCK task's starter configuration (a read-only GET), so that "Where" can name a parameter row. It is put into
  // the temporary browser profile only, and never validated for real: the reports above are what the page is told.
  // The one MOCK task (status record 7.59), the real OTA5: five rows, the followers of its two pairs at rows 1 and 3.
  const CONFIG = await starterConfig(APP);  // as "Load task" merges it
  const ROW_KEY = CONFIG.parameters[0].variable_id;
  // What a backend answers when the schema rejects the configuration (HTTP 422, schema.describe_errors); an older backend
  // sent pydantic's text at parameters.1.variable_id; anything else is one plain failure.
  const FOLLOWERS = [1, 3];
  const PATTERN = "String should match pattern '^[A-Za-z_][A-Za-z0-9_.\\-]*$'";
  const idError = n => ({ path: `parameters[${n}].variable_id`, code: 'invalid_id', technical: `FIXTURE: ${PATTERN} [string_pattern_mismatch]`,
    message: `FIXTURE: "${CONFIG.parameters[n].variable_id}" cannot be an ID: it contains "/".` });
  const rejectedBy = errors => ({ status: 422, body: { detail: { message: 'The configuration does not match the schema', errors } } });
  Object.assign(fixtures, { rejected: rejectedBy(FOLLOWERS.map(idError)),
    rejectedOld: rejectedBy([{ path: 'parameters.3.variable_id', message: `FIXTURE: ${PATTERN}` }, { path: 'run.max_evaluations', message: 'FIXTURE: Input should be a valid integer' }]),
    failed: { status: 500, body: { detail: 'FIXTURE: the backend failed' } } });
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; let validations = 0, answerWith = fixtures.three;
  const META = await (await fetch(new URL('api/meta', APP))).json();
  let settingsProblem = null;                                                     // the last section: /api/meta says settings.json is unreadable
  const answer = params => {
    const name = new URL(params.request.url).pathname;
    if (name === '/api/runs') return fulfil(params.requestId, 200, { runs: [] });
    if (name === '/api/config/validate') { validations++; return answerWith.status ? fulfil(params.requestId, answerWith.status, answerWith.body) : fulfil(params.requestId, 200, answerWith); }
    if (name === '/api/meta' && settingsProblem) return fulfil(params.requestId, 200, { ...META, settings_problem: settingsProblem });
    return page.readOrRefuse(params, refused);                                    // a panel asking on its own; never a start
  };
  const until = (expression, tries = 60) => page.until(expression, tries);
  const BUTTON = `document.querySelector('header button.issues-button')`;
  const LIST = `document.querySelector('#blocking-issues')`;
  const rows = () => evaluate(`[...(${LIST}?.querySelectorAll('tbody tr') ?? [])].map(tr => [...tr.cells].map(td => td.textContent.trim()))`);
  const headerButton = label => `[...document.querySelectorAll('header button')].find(b => b.textContent === ${JSON.stringify(label)})`;
  // The page validates by itself half a second after any change ("Static validation", the button that asked at once, went
  // on 2026-09-29): a change of the random seed makes it ask again, alternating between two seeds (the RL model label box did
  // this until it moved into the RL model window, record 7.265; the project name box until record 7.159).
  const SEED_BOX = `[...document.querySelectorAll('.right label')].find(l => l.firstChild?.textContent?.trim() === 'Random seed')?.querySelector('input')`;
  let flip = false;
  const revalidate = async fixture => {
    answerWith = fixture; const before = validations; flip = !flip;
    const seed = flip ? '11' : '12';
    await evaluate(`(() => { const el = ${SEED_BOX}; Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set.call(el, ${JSON.stringify(seed)});
      el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    for (let i = 0; i < 60 && validations === before; i++) await sleep(100);
    await sleep(300);
  };
  const mouse = (type, at) => send('Input.dispatchMouseEvent', { type, x: at.x, y: at.y, button: 'left', buttons: type === 'mousePressed' ? 1 : 0, clickCount: 1 });
  const centre = expression => evaluate(`(() => { const r = ${expression}.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  const shot = async name => page.shot(path.join(out, name),
    await evaluate(`(() => { const r = document.querySelector('header').getBoundingClientRect(); return { x: 0, y: 0, width: 1680, height: Math.min(1050, r.bottom + 170), scale: 1 }; })()`));

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${BUTTON})`, 150))) throw new Error(`the blocking-issues button never appeared (${validations} validation request(s) answered); the page reads: `
    + JSON.stringify(await evaluate(`(document.querySelector('header') ?? document.body).innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));

  // ---- the notifier is a button; nothing is listed before a press ---------------------------------------------
  check('the notifier is a <button>', (await evaluate(`${BUTTON}.tagName`)) === 'BUTTON');
  check('it counts the blocking issues only (3 of 6 reported)', (await evaluate(`${BUTTON}.textContent`)) === '3 blocking issues', await evaluate(`${BUTTON}.textContent`));
  check('the old text notifier is gone', !(await evaluate(`[...document.querySelectorAll('header span')].some(s => /blocking issue/.test(s.textContent))`)));
  check('nothing is listed before a press', !(await evaluate(`!!(${LIST})`)) && (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'false');
  check('Start and Calibration are disabled', await evaluate(`${headerButton('Start')}.disabled && ${headerButton('Calibration')}.disabled`));
  // Branch record SIF-45: their tooltip counts the levels the button counts, and names it by its words (errors alone were
  // counted: "has 2 blocking issues: the red button in the header lists them" beside a button that said 3).
  const why = () => evaluate(`${headerButton('Calibration')}.title`);
  const tooltipSays = text => until(`${headerButton('Calibration')}.title === ${JSON.stringify(`Calibration: ${text}`)}`, 30);   // waited for: the header may still be looking up its run
  check('the tooltip counts what the button counts, and names it', await tooltipSays('The configuration has 3 blocking issues: the red "3 blocking issues" button in the header lists them.'), await why());
  const heightClosed = await evaluate(`document.querySelector('header').getBoundingClientRect().height`);
  await shot('issues-1-closed.png');

  // ---- the list appears on RELEASE, not on press ---------------------------------------------------------------
  const at = await centre(BUTTON);
  await mouse('mouseMoved', at); await mouse('mousePressed', at); await sleep(400);
  check('while the button is held down nothing is listed yet', !(await evaluate(`!!(${LIST})`)));
  await mouse('mouseReleased', at);
  check('releasing the button shows the list', await until(`!!(${LIST})`, 30));
  check('the button reports the open state', (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'true' && await evaluate(`${BUTTON}.classList.contains('active')`));
  const head = await evaluate(`${LIST}.querySelector('.issue-list-head').textContent`);
  check('the list\'s head counts them and names the buttons they hold back', head.startsWith('3 blocking issuesStart and Calibration stay disabled until all of them are resolved.'), head);

  // ---- ALL blocking issues, in full, and no other ---------------------------------------------------------------
  const listed = await rows();
  check('all 3 blocking issues are listed, in report order', listed.length === 3 && listed.every((r, n) => r[0] === String(n + 1) && r[1] === BLOCKING[n].level && r[2] === BLOCKING[n].code), JSON.stringify(listed.map(r => r.slice(0, 3))));
  check('each message is shown in full (not as a tooltip)', listed.every((r, n) => r[4] === BLOCKING[n].message), JSON.stringify(listed.map(r => r[4])));
  check('a row issue names its field and the key of its row', listed[0]?.[3] === `parameters[0].lower row ${ROW_KEY}`, listed[0]?.[3]);
  check('an issue outside the editor tabs is listed with its field', listed[1]?.[3] === 'run.network', listed[1]?.[3]);
  check('an issue without a field reads "(whole configuration)"', listed[2]?.[3] === '(whole configuration)', listed[2]?.[3]);
  check('warnings, unresolved and info lines are not listed', !OTHERS.some(o => JSON.stringify(listed).includes(o.code)));
  const box = await evaluate(`(() => { const h = document.querySelector('header').getBoundingClientRect(), l = ${LIST}.getBoundingClientRect(), m = document.querySelector('main').getBoundingClientRect();
    return { inside: l.top >= h.top && l.bottom <= h.bottom + 1, width: l.width, headerWidth: h.width, headerHeight: h.height, mainTop: m.top, headerBottom: h.bottom, overflowX: document.documentElement.scrollWidth > window.innerWidth }; })()`);
  check('the list is a full-width second line of the header', box.inside && box.width > box.headerWidth - 40 && box.headerHeight > heightClosed + 40, JSON.stringify(box));
  check('it pushes the editors down instead of covering them', box.mainTop >= box.headerBottom && !box.overflowX, JSON.stringify(box));
  await shot('issues-2-open.png');

  // ---- it follows the next validation while it is open ---------------------------------------------------------
  await revalidate(fixtures.one);
  const after = await rows();
  check('an open list follows the next validation (3 -> 1)', after.length === 1 && after[0][2] === 'heads_divisibility' && (await evaluate(`${BUTTON}.textContent`)) === '1 blocking issue', JSON.stringify(after));
  check('a blocker alone is one blocking issue in the tooltip too', await tooltipSays('The configuration has a blocking issue: the red "1 blocking issue" button in the header lists it.'), await why());
  await shot('issues-3-one-left.png');

  // ---- a second press, and the Hide button, close it --------------------------------------------------------------
  await evaluate(`${BUTTON}.click()`);
  check('a second press hides the list', await until(`!(${LIST})`, 30) && (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'false');
  await evaluate(`${BUTTON}.click()`); await until(`!!(${LIST})`, 30);
  // Branch record SIF-112: Hide is the close mark (an X) at the head's end, as Matched devices' - its word for screen readers
  // and at the start of its tooltip, which names the header's button - centred on the head's words: on their baseline it
  // stood 2 px over them, centred alone 6 px under them.
  const HIDE = `[...${LIST}.querySelectorAll('button')].find(b => b.textContent === 'Hide')`;
  const hide = await evaluate(`(() => { const b = ${HIDE}, count = ${LIST}.querySelector('.issue-list-head > b').getBoundingClientRect(), icon = b?.querySelector('svg.icon')?.getBoundingClientRect();
    return b && { label: b.querySelector('.sr-only')?.textContent ?? null, title: b.title, last: b === b.parentElement.lastElementChild,
      offset: icon ? Math.round(((icon.top + icon.bottom) / 2 - (count.top + count.bottom) / 2) * 10) / 10 : null }; })()`);
  check('"Hide" is the close mark at the head\'s end, its word for screen readers and its tooltip naming the header\'s button (SIF-112)', hide?.label === 'Hide' && hide.last
    && hide.title === 'Hide: The list folds away; the red "1 blocking issue" button in the header shows it again.', JSON.stringify(hide));
  check('...its X centred on the head\'s words (within 1 px)', typeof hide?.offset === 'number' && Math.abs(hide.offset) <= 1, JSON.stringify(hide));
  await evaluate(`${HIDE}.click()`);
  check('"Hide" closes it too', await until(`!(${LIST})`, 30));

  // ---- nothing blocks: no button, no list; a later problem does not open the list by itself -------------------------
  await evaluate(`${BUTTON}.click()`); await until(`!!(${LIST})`, 30);
  await revalidate(fixtures.valid);
  check('with nothing blocking the header reads "configuration valid" and the button is gone', !(await evaluate(`!!(${BUTTON})`)) && await evaluate(`[...document.querySelectorAll('header span.ok')].some(s => s.textContent === 'configuration valid')`));
  check('the open list closed with it', !(await evaluate(`!!(${LIST})`)));
  // the buttons follow in the render after the header's text; waited for, as every other state here (record 7.227: it was read in the same tick and failed by a few ms)
  check('Start and Calibration are enabled again', await until(`!${headerButton('Start')}.disabled && !${headerButton('Calibration')}.disabled`, 30));
  await shot('issues-4-valid.png');
  await revalidate(fixtures.three);
  check('a new problem brings the button back, closed', (await until(`!!(${BUTTON})`, 30)) && !(await evaluate(`!!(${LIST})`)) && (await evaluate(`${BUTTON}.textContent`)) === '3 blocking issues');

  // ---- the keyboard works as for any button --------------------------------------------------------------------------
  await evaluate(`${BUTTON}.focus()`);
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
  check('Enter on the focused button shows the list', await until(`!!(${LIST})`, 30));

  // ---- branch record SIF-95: a row issue's Where goes to its row; each editor tab counts its own blocking issues ---------------
  // The place was text only: the user switched tab by hand and looked for the row, which the Find box could hide; a tab not in
  // view never showed its errors, and the header's count names no tab.
  const EDITOR_TAB = key => `document.querySelector('section.editors > .tabs > button[data-editor="${key}"]')`;
  const tabMark = key => evaluate(`(() => { const b = ${EDITOR_TAB(key)}, pill = b.querySelector('.tab-errors');
    return { errors: b.classList.contains('has-errors'), count: pill?.dataset.errors ?? null, text: b.textContent, title: b.title,
      pill: pill ? [getComputedStyle(pill, '::before').content, getComputedStyle(pill, '::before').backgroundColor] : null }; })()`);
  const goes = () => evaluate(`[...${LIST}.querySelectorAll('tbody tr')].map(tr => tr.cells[3].querySelector('button.issue-go')?.textContent ?? null)`);
  check('a row issue\'s Where is a button in the words it had; a run field and the whole configuration stay text',
    JSON.stringify(await goes()) === JSON.stringify([`parameters[0].lower row ${ROW_KEY}`, null, null]), JSON.stringify(await goes()));
  const [paramsMark, probesMark] = [await tabMark('parameters'), await tabMark('measurements')];
  check('the Parameters tab counts its one blocking issue in a red pill, its words unchanged; Probes counts none',
    paramsMark.errors && paramsMark.count === '1' && paramsMark.text === `Parameters (${CONFIG.parameters.length})` && paramsMark.pill?.[0] === '"1"'
    && paramsMark.pill?.[1] === 'rgb(208, 16, 44)' && paramsMark.title === '1 blocking issue: FIXTURE. The red button in the header lists it: its Where goes to the row.'
    && !probesMark.errors && probesMark.count === null && !probesMark.title, JSON.stringify([paramsMark, probesMark]));
  // Specs broken while Parameters is open, and hidden by a Find text typed on Specs before
  const SPEC_KEY = CONFIG.targets[0].metric_id, FIND = `document.querySelector('section.editors input.find-rows')`;
  const specIssue = (code, field, message) => ({ level: 'error', code, path: `targets[0].${field}`, message });
  fixtures.elsewhere = report([specIssue('equation_unknown_probe', 'equation', 'FIXTURE the equation names a probe that does not exist: m_nope.'),
    BLOCKING[0], specIssue('range_inverted', 'lower', 'FIXTURE: the lower limit is above the upper one')]);
  await evaluate(`${EDITOR_TAB('targets')}.click()`); await until(`${EDITOR_TAB('targets')}.classList.contains('active')`, 30);
  await page.setValue(FIND, 'zzz-no-row', { event: 'input' });
  const SPEC_ROW = `document.querySelector('section.editors table.editor tbody tr[data-index="0"]')`;
  check('(a Find text hides the spec)', await until(`${SPEC_ROW}?.hidden === true`, 30));
  await evaluate(`${EDITOR_TAB('parameters')}.click()`); await until(`${EDITOR_TAB('parameters')}.classList.contains('active')`, 30);
  await revalidate(fixtures.elsewhere);
  const specsMark = await tabMark('targets');
  check('on Parameters, the Specs tab counts the two issues of its spec, its tooltip giving the first',
    specsMark.errors && specsMark.count === '2' && specsMark.text === `Specs (${CONFIG.targets.length})` && specsMark.title
      === "2 blocking issues, the first: FIXTURE the equation names a probe that does not exist. The red button in the header lists them: each one's Where goes to its row.",
    JSON.stringify(specsMark));
  const WHERE = `document.querySelector('.formula-bar .formula-where')?.textContent`;
  const focusIn = (index, field) => `document.activeElement?.closest('td[data-field="${field}"]')?.closest('tr')?.dataset.index === '${index}'`;
  await evaluate(`[...${LIST}.querySelectorAll('button.issue-go')][0].click()`);
  check('its Where opens Specs, clears the Find text that hid the row and chooses the issue\'s field, which the formula bar names',
    await until(`${EDITOR_TAB('targets')}.classList.contains('active') && ${FIND}.value === '' && ${SPEC_ROW}?.hidden === false && ${focusIn(0, 'equation')}
      && ${WHERE} === ${JSON.stringify(`Equation · ${SPEC_KEY}`)}`, 30),
    JSON.stringify(await evaluate(`({ find: ${FIND}.value, focus: document.activeElement?.outerHTML.slice(0, 80), where: ${WHERE} })`)));
  check('the list stays open, a checklist (record 7.12)', await evaluate(`!!(${LIST})`));
  await evaluate(`[...${LIST}.querySelectorAll('button.issue-go')][1].click()`);
  check('a Parameters issue\'s Where goes back to Parameters, to its row\'s Lower',
    await until(`${EDITOR_TAB('parameters')}.classList.contains('active') && ${focusIn(0, 'lower')} && ${WHERE} === ${JSON.stringify(`Lower · ${ROW_KEY}`)}`, 30),
    await evaluate(`${WHERE}`));
  await shot('issues-4b-go-to.png');

  // ---- review of SIF-95: a tab's tooltip promises a go-to only for an issue in a row (one of the table itself, path "parameters",
  // has none); a Where's tooltip names the cell it chooses - the row's ID for a Unit no column shows, the Scale behind More
  // columns, which the press shows for this page; a duplicate ID goes to the row the report names, not the first with that ID.
  const tableIssue = (code, table, message) => ({ level: 'error', code, path: table, message });
  fixtures.tables = report([tableIssue('nothing_to_optimize', 'parameters', 'FIXTURE at least one optimized variable is required.'),
    specIssue('target_unit_mismatch', 'unit', 'FIXTURE the unit is not the probe\'s.'),
    { ...specIssue('scale_needed_for_zero_limit', 'normalization_scale', 'FIXTURE a limit of 0 needs a Scale.'), level: 'blocker' },
    tableIssue('no_hard_constraint', 'targets', 'FIXTURE at least one hard spec is required.')]);
  await revalidate(fixtures.tables);
  const goTitles = () => evaluate(`[...${LIST}.querySelectorAll('tbody tr')].map(tr => tr.cells[3].querySelector('button.issue-go')?.title ?? null)`);
  const [tableParams, tableSpecs] = [await tabMark('parameters'), await tabMark('targets')];
  check('a tab whose one issue is the table\'s own says the list holds it, and no go-to; its Where is text',
    tableParams.count === '1' && tableParams.title === '1 blocking issue: FIXTURE at least one optimized variable is required. The red button in the header lists it.'
    && (await goes())[0] === null, JSON.stringify([tableParams.title, await goes()]));
  check('a tab with issues in rows and of its own says a Where that names a row goes to it',
    tableSpecs.count === '3' && tableSpecs.title === '3 blocking issues, the first: FIXTURE the unit is not the probe\'s. The red button in the header lists them: a Where that names a row goes to it.',
    tableSpecs.title);
  const MORE = `[...document.querySelectorAll('section.editors .toolbar button.text')].find(b => /^(More|Fewer) columns/.test(b.textContent))`;
  const activeIn = (index, field) => `(() => { const td = document.querySelector('section.editors table.editor td.active-cell');
    return td?.dataset.field === '${field}' && td.closest('tr')?.dataset.index === '${index}'; })()`;
  check('a Where\'s tooltip names the cell it chooses: the Spec ID for the Unit no column shows, the Scale behind More columns',
    JSON.stringify(await goTitles()) === JSON.stringify([null, `Go to ${SPEC_KEY}: Specs opens with its Spec ID chosen, as no column shows its Unit. The list stays open.`,
      `Go to ${SPEC_KEY}: Specs opens with its Scale chosen, More columns shown. The list stays open.`, null]), JSON.stringify(await goTitles()));
  check('(More columns is folded)', (await evaluate(`${MORE}?.textContent ?? ''`)).startsWith('More columns'));
  await evaluate(`[...${LIST}.querySelectorAll('button.issue-go')][0].click()`);
  check('the Unit issue\'s Where chooses the Spec ID, as its tooltip says, More columns left folded',
    await until(`${EDITOR_TAB('targets')}.classList.contains('active') && ${activeIn(0, 'metric_id')} && ${WHERE} === ${JSON.stringify(`Spec ID · ${SPEC_KEY}`)}`, 30)
      && (await evaluate(`${MORE}.textContent`)).startsWith('More columns'), await evaluate(`${WHERE}`));
  await evaluate(`[...${LIST}.querySelectorAll('button.issue-go')][1].click()`);
  check('the Scale issue\'s Where shows More columns and chooses the Scale; the kept More columns choice is not changed',
    await until(`${activeIn(0, 'normalization_scale')} && ${WHERE} === ${JSON.stringify(`Scale · ${SPEC_KEY}`)} && ${MORE}.textContent === 'Fewer columns'`, 30)
      && (await evaluate(`(() => { try { return localStorage.getItem('gator-workbench-editor-more-columns'); } catch { return 'unreadable'; } })()`)) === null,
    JSON.stringify(await evaluate(`({ where: ${WHERE}, more: ${MORE}.textContent })`)));
  // Branch record SIF-135: the Issues column stays at the right edge of the box, and the Scale - partly under it where the table
  // starts - comes into view beside it, not under it: the column's width is the box's scroll padding.
  const scaleSeen = await evaluate(`(() => { const td = document.querySelector('section.editors table.editor td.active-cell'), box = td.closest('.scroll');
    const input = td.querySelector('input'), i = input.getBoundingClientRect(), at = document.elementFromPoint(i.left + i.width / 2, i.top + i.height / 2);
    const issues = box.querySelector('thead th:last-child').getBoundingClientRect();
    return { cell: [Math.round(td.getBoundingClientRect().left), Math.round(td.getBoundingClientRect().right)], issues: Math.round(issues.left),
      pinned: box.classList.contains('pin-issues'), onTop: at === input, scrolled: Math.round(box.scrollLeft), sideways: box.scrollWidth - box.clientWidth }; })()`);
  check('...the Scale chosen in view beside the Issues column pinned at the right edge, not under it (SIF-135: its width is the box\'s scroll padding)',
    scaleSeen.pinned && scaleSeen.sideways > 0 && scaleSeen.onTop && scaleSeen.cell[1] <= scaleSeen.issues + 1, JSON.stringify(scaleSeen));
  await shot('issues-4c-scale.png');
  await evaluate(`${MORE}.click()`);
  check('(Fewer columns folds them again)', await until(`${MORE}.textContent.startsWith('More columns')`, 30));
  // A duplicate ID typed into the last Parameters row: the report names that row, as validation.py reports a duplicate on its later row.
  const DUP = CONFIG.parameters.length - 1, DUP_KEY = CONFIG.parameters[DUP].variable_id;
  const ID_BOX = `document.querySelector('section.editors table.editor tbody tr[data-index="${DUP}"] td[data-field="variable_id"] input')`;
  fixtures.duplicate = report([{ level: 'error', code: 'duplicate_variable_id', path: `parameters[${DUP}]`, message: `FIXTURE Duplicate variable_id '${ROW_KEY}'` },
    { level: 'error', code: 'range_inverted', path: `parameters[${DUP}].lower`, message: 'FIXTURE the lower bound is above the upper bound' }]);
  const typeId = async (value, fixture) => {
    answerWith = fixture; const before = validations;
    await page.setValue(ID_BOX, value, { event: 'input' });
    for (let i = 0; i < 60 && validations === before; i++) await sleep(100);
    await sleep(300);
  };
  await evaluate(`${EDITOR_TAB('parameters')}.click()`); await until(`${EDITOR_TAB('parameters')}.classList.contains('active')`, 30);
  await typeId(ROW_KEY, fixtures.duplicate);
  check('(the last row now repeats the first row\'s ID, and the list names it)', JSON.stringify(await goes()) === JSON.stringify([`parameters[${DUP}] row ${ROW_KEY}`,
    `parameters[${DUP}].lower row ${ROW_KEY}`]), JSON.stringify(await goes()));
  await evaluate(`[...${LIST}.querySelectorAll('button.issue-go')][0].click()`);
  check('a duplicate ID\'s Where goes to the row the report names, not the first row with that ID',
    await until(`${activeIn(DUP, 'variable_id')} && ${WHERE} === ${JSON.stringify(`ID · ${ROW_KEY}`)}`, 30),
    JSON.stringify(await evaluate(`({ where: ${WHERE}, row: document.querySelector('section.editors td.active-cell')?.closest('tr')?.dataset.index })`)));
  await evaluate(`[...${LIST}.querySelectorAll('button.issue-go')][1].click()`);
  check('... and another issue of that row goes to its own Lower', await until(activeIn(DUP, 'lower'), 30),
    JSON.stringify(await evaluate(`({ where: ${WHERE}, row: document.querySelector('section.editors td.active-cell')?.closest('tr')?.dataset.index })`)));
  await typeId(DUP_KEY, fixtures.elsewhere);
  check('(the last row has its own ID again)', (await evaluate(`${ID_BOX}.value`)) === DUP_KEY);

  // ---- a configuration the schema rejects: one issue per field, at its row, in plain words (status record 7.56) ------------
  // Before, the page listed ONE issue "(whole configuration)" holding pydantic's list as JSON (user report 2026-09-21).
  await revalidate(fixtures.rejected);
  const schemaRows = await rows();
  const key = n => CONFIG.parameters[n].variable_id;
  check('each rejected field is its own blocking issue (2)', schemaRows.length === 2 && (await evaluate(`${BUTTON}.textContent`)) === '2 blocking issues', JSON.stringify(schemaRows.map(r => r.slice(0, 4))));
  check('each names its field and the key of its row', schemaRows.every((r, n) => r[2] === 'invalid_id' && r[3] === `parameters[${FOLLOWERS[n]}].variable_id row ${key(FOLLOWERS[n])}`), JSON.stringify(schemaRows.map(r => r[3])));
  check('each message is the plain one, not a JSON list', schemaRows.every((r, n) => r[4].startsWith(idError(FOLLOWERS[n]).message)) && !schemaRows.some(r => r[4].includes('[{')), JSON.stringify(schemaRows.map(r => r[4])));
  const TECH = `[...${LIST}.querySelectorAll('tbody tr')].map(tr => tr.querySelector('details.more'))`;
  check('the schema\'s own words are folded under "Technical details"', await evaluate(`${TECH}.every(d => d && !d.open && d.querySelector('summary').textContent === 'Technical details' && !d.querySelector('code').checkVisibility())`));
  await evaluate(`${TECH}[0].querySelector('summary').click()`);
  check('one click shows them', await until(`${TECH}[0].open && ${TECH}[0].querySelector('code').checkVisibility() && ${TECH}[0].querySelector('code').textContent.includes('string_pattern_mismatch')`, 30));
  const EDITOR_ROWS = `[...document.querySelectorAll('section.editors table.editor tbody tr')]`;
  // Branch record SIF-5: an issue shows words; its level is its class, its code its data-code.
  const marked = await evaluate(`${EDITOR_ROWS}.map(tr => [tr.classList.contains('has-error'), [...tr.querySelectorAll('td.issues .issue')].map(d => d.className.replace('issue ', '') + ': ' + d.dataset.code).join('')])`);
  check('the Parameters editor marks exactly those rows', marked.length === 5 && marked.every(([bad, text], n) => bad === FOLLOWERS.includes(n) && text === (FOLLOWERS.includes(n) ? 'error: invalid_id' : '')), JSON.stringify(marked));
  await shot('issues-5-rejected.png');
  await revalidate(fixtures.rejectedOld);
  const oldRows = await rows();
  check('an older backend\'s answer is split the same way, its paths written like the report\'s', oldRows.length === 2 && oldRows[0][2] === 'schema'
    && oldRows[0][3] === `parameters[3].variable_id row ${key(3)}` && oldRows[0][4] === `FIXTURE: ${PATTERN}` && oldRows[1][3] === 'run.max_evaluations', JSON.stringify(oldRows));
  check('... without an empty "Technical details"', !(await evaluate(`!!${LIST}.querySelector('details')`)));
  await revalidate(fixtures.failed);
  const failedRows = await rows();
  check('any other failure is one issue with its text only', failedRows.length === 1 && failedRows[0][3] === '(whole configuration)' && failedRows[0][4] === 'FIXTURE: the backend failed', JSON.stringify(failedRows));
  await revalidate(fixtures.valid);
  check('a valid answer clears them', !(await evaluate(`!!(${BUTTON})`)) && (await evaluate(`${EDITOR_ROWS}.filter(tr => tr.classList.contains('has-error')).length`)) === 0);

  // ---- a hand-edited settings.json that is not valid JSON (review of 2026-09-29, A12): said in the header, never hidden ------
  const PROBLEM = 'FIXTURE: settings.json is not valid JSON (line 3, column 5): the workbench runs on its defaults and leaves the file as it is.';
  check('(without a problem the header has no such line)', !(await evaluate(`!!document.querySelector('header .settings-problem')`)));
  settingsProblem = PROBLEM; answerWith = fixtures.three;
  await send('Page.reload');
  await until(`!!(${BUTTON})`, 150);
  const line = await evaluate(`(() => { const p = document.querySelector('header .settings-problem'), h = document.querySelector('header'); if (!p) return null;
    const r = p.getBoundingClientRect(), b = h.getBoundingClientRect(); return { text: p.textContent, inside: r.top >= b.top && r.bottom <= b.bottom + 1, width: r.width, headerWidth: b.width,
    below: r.top > ${BUTTON}.getBoundingClientRect().bottom - 1, warn: p.classList.contains('warn') }; })()`);
  check('an unreadable settings.json is said in the header, on a full-width line of its own under the buttons', !!line && line.text === PROBLEM && line.inside && line.below
    && line.width > line.headerWidth - 40 && line.warn, JSON.stringify(line));
  await evaluate(`document.querySelector('header .settings-problem').click()`); await sleep(300);
  check('it stays: a click does not dismiss it (the page otherwise works as before)', await evaluate(`!!document.querySelector('header .settings-problem') && !!(${BUTTON})`));
  await shot('issues-6-settings-problem.png');

  reportRefused(refused, NEVER_ASKED);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
