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
  // on 2026-09-29): a change of the project name makes it ask again, alternating between two names.
  const NAME_BOX = `[...document.querySelectorAll('.left label')].find(l => l.firstChild?.textContent.trim() === 'Project name')?.querySelector('input')`;   // 'Name' until 7.146
  let flip = false;
  const revalidate = async fixture => {
    answerWith = fixture; const before = validations; flip = !flip;
    const name = flip ? 'check-a' : 'check-b';
    await evaluate(`(() => { const el = ${NAME_BOX}; Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set.call(el, ${JSON.stringify(name)});
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
  check('it counts the blocking issues only (3 of 6 reported)', (await evaluate(`${BUTTON}.textContent`)) === '3 blocking issue(s)', await evaluate(`${BUTTON}.textContent`));
  check('the old text notifier is gone', !(await evaluate(`[...document.querySelectorAll('header span')].some(s => /blocking issue/.test(s.textContent))`)));
  check('nothing is listed before a press', !(await evaluate(`!!(${LIST})`)) && (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'false');
  check('Start and the baseline simulation are disabled', await evaluate(`${headerButton('Start')}.disabled && ${headerButton('Single baseline simulation')}.disabled`));
  const heightClosed = await evaluate(`document.querySelector('header').getBoundingClientRect().height`);
  await shot('issues-1-closed.png');

  // ---- the list appears on RELEASE, not on press ---------------------------------------------------------------
  const at = await centre(BUTTON);
  await mouse('mouseMoved', at); await mouse('mousePressed', at); await sleep(400);
  check('while the button is held down nothing is listed yet', !(await evaluate(`!!(${LIST})`)));
  await mouse('mouseReleased', at);
  check('releasing the button shows the list', await until(`!!(${LIST})`, 30));
  check('the button reports the open state', (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'true' && await evaluate(`${BUTTON}.classList.contains('active')`));

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
  check('an open list follows the next validation (3 -> 1)', after.length === 1 && after[0][2] === 'heads_divisibility' && (await evaluate(`${BUTTON}.textContent`)) === '1 blocking issue(s)', JSON.stringify(after));
  await shot('issues-3-one-left.png');

  // ---- a second press, and the Hide button, close it --------------------------------------------------------------
  await evaluate(`${BUTTON}.click()`);
  check('a second press hides the list', await until(`!(${LIST})`, 30) && (await evaluate(`${BUTTON}.getAttribute('aria-expanded')`)) === 'false');
  await evaluate(`${BUTTON}.click()`); await until(`!!(${LIST})`, 30);
  await evaluate(`[...${LIST}.querySelectorAll('button')].find(b => b.textContent === 'Hide').click()`);
  check('"Hide" closes it too', await until(`!(${LIST})`, 30));

  // ---- nothing blocks: no button, no list; a later problem does not open the list by itself -------------------------
  await evaluate(`${BUTTON}.click()`); await until(`!!(${LIST})`, 30);
  await revalidate(fixtures.valid);
  check('with nothing blocking the header reads "configuration valid" and the button is gone', !(await evaluate(`!!(${BUTTON})`)) && await evaluate(`[...document.querySelectorAll('header span.ok')].some(s => s.textContent === 'configuration valid')`));
  check('the open list closed with it', !(await evaluate(`!!(${LIST})`)));
  check('Start and the baseline simulation are enabled again', await evaluate(`!${headerButton('Start')}.disabled && !${headerButton('Single baseline simulation')}.disabled`));
  await shot('issues-4-valid.png');
  await revalidate(fixtures.three);
  check('a new problem brings the button back, closed', (await until(`!!(${BUTTON})`, 30)) && !(await evaluate(`!!(${LIST})`)) && (await evaluate(`${BUTTON}.textContent`)) === '3 blocking issue(s)');

  // ---- the keyboard works as for any button --------------------------------------------------------------------------
  await evaluate(`${BUTTON}.focus()`);
  for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
  check('Enter on the focused button shows the list', await until(`!!(${LIST})`, 30));

  // ---- a configuration the schema rejects: one issue per field, at its row, in plain words (status record 7.56) ------------
  // Before, the page listed ONE issue "(whole configuration)" holding pydantic's list as JSON (user report 2026-09-21).
  await revalidate(fixtures.rejected);
  const schemaRows = await rows();
  const key = n => CONFIG.parameters[n].variable_id;
  check('each rejected field is its own blocking issue (2)', schemaRows.length === 2 && (await evaluate(`${BUTTON}.textContent`)) === '2 blocking issue(s)', JSON.stringify(schemaRows.map(r => r.slice(0, 4))));
  check('each names its field and the key of its row', schemaRows.every((r, n) => r[2] === 'invalid_id' && r[3] === `parameters[${FOLLOWERS[n]}].variable_id row ${key(FOLLOWERS[n])}`), JSON.stringify(schemaRows.map(r => r[3])));
  check('each message is the plain one, not a JSON list', schemaRows.every((r, n) => r[4].startsWith(idError(FOLLOWERS[n]).message)) && !schemaRows.some(r => r[4].includes('[{')), JSON.stringify(schemaRows.map(r => r[4])));
  const TECH = `[...${LIST}.querySelectorAll('tbody tr')].map(tr => tr.querySelector('details.more'))`;
  check('the schema\'s own words are folded under "Technical details"', await evaluate(`${TECH}.every(d => d && !d.open && d.querySelector('summary').textContent === 'Technical details' && !d.querySelector('code').checkVisibility())`));
  await evaluate(`${TECH}[0].querySelector('summary').click()`);
  check('one click shows them', await until(`${TECH}[0].open && ${TECH}[0].querySelector('code').checkVisibility() && ${TECH}[0].querySelector('code').textContent.includes('string_pattern_mismatch')`, 30));
  const EDITOR_ROWS = `[...document.querySelectorAll('section.editors table.editor tbody tr')]`;
  const marked = await evaluate(`${EDITOR_ROWS}.map(tr => [tr.classList.contains('has-error'), tr.querySelector('td.issues').textContent])`);
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
