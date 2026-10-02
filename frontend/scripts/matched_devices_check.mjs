// Browser check of "Matched devices..." in the Parameters tab (status record 7.103): the box opens on the press with
// the structures of the circuit and the ties they suggest, a tie is made only after "Review..." and Apply, Undo
// takes it back, an answer about rows that changed since says so, another tab closes the box (it does not come back and
// ask by itself), and a verified task's rows are shown as fixed.
// Requests: /api/parameters/matched is answered with fixtures/matched_devices.json - the REAL route's answers for the seeded
// rows (a MOCK OTA5 whose five widths are each their own variable), made with a backend of record 7.103 - so the check does
// not need a restarted backend; GET, POST /api/circuit/load and POST /api/config/validate pass through (read-only: local
// files, no bridge, no simulation); every other writing request is refused. Safe on the live backend.
// To make the fixture again: POST {config: <the seed>, apply: null} and then {config, apply: <the ticked ids>} to a backend
// with this record, and store both answers with the seeded rows (the label says so).
// Run (Windows node through WSL interop; node >= 22):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/matched_devices_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { readFileSync } from 'node:fs';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('matched');
const FIXTURE = JSON.parse(readFileSync(new URL('./fixtures/matched_devices.json', import.meta.url), 'utf8'));
const VERIFIED = { applicable: false, structures: FIXTURE.found.structures, suggestions: [], independent_before: 2,
  why_not: 'The rows of real:gpdk045_ota7 are fixed by its verified circuit profile: a run accepts exactly those. The structures are listed for information. FIXTURE' };

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, consoleErrors } = page;
  const refused = [], asked = [];
  let verified = false, invalid = false;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/parameters/matched') {
      const body = JSON.parse(request.postData ?? '{}');
      asked.push(body);
      // The backend's own 422 for a configuration it cannot read (schema.describe_errors wording).
      if (invalid) return page.fulfil(requestId, 422, { detail: { message: 'The configuration does not match the schema', errors: [
        { path: 'run.max_evaluations', code: 'schema', message: 'max_evaluations is missing: this field needs a value.', technical: 'Field required [missing]' }] } });
      return page.fulfil(requestId, 200, verified ? VERIFIED : body.apply ? FIXTURE.shown : FIXTURE.found);
    }
    if (request.method === 'GET' || name === '/api/config/validate' || name === '/api/circuit/load') return page.pass(requestId);
    // Refused, harmless: the output-folder look-up, and the connection test the page makes once when it opens (record 7.80)
    if (name !== '/api/output/check' && name !== '/api/connection/check') refused.push(`${request.method} ${name}`);
    return page.refuse(requestId);
  };
  const until = (expression, tries = 100) => page.until(expression, tries);
  const EDITORS = `document.querySelector('.editors')`;
  const BOX = `${EDITORS}.querySelector('.matched-devices')`;
  const BUTTON = (scope, text) => `[...${scope}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const TOOLBAR = `${EDITORS}.querySelector('.toolbar')`;
  const press = (scope, text) => evaluate(`${BUTTON(scope, text)}.click()`);
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim()).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const cell = (row, name) => evaluate(`${CELL(row, name)}.value`);
  const boxText = () => evaluate(`${BOX}?.textContent ?? ''`);
  const ticks = () => evaluate(`[...${BOX}.querySelectorAll('tbody input[type=checkbox]')].map(b => ({ checked: b.checked, disabled: b.disabled }))`);
  const shot = (name, element) => page.shot(path.join(out, name), element);

  await page.intercept(['*/api/*'], answer);
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const SEED = { schema_version: 'gator-workbench-config-v1', ...starter, parameters: FIXTURE.parameters,
    run: { mode: 'scratch', concurrency: 1, threads_per_job: 1, ...starter.run }, output: { experiment_name: 'fixture' }, research: {} };
  await page.seed({ config: SEED, when: 'missing' });
  await send('Page.navigate', { url: APP });
  check('the page opens on the Parameters tab with the five seeded rows', await until(`${EDITORS}?.querySelectorAll('table.editor tbody tr').length === 5`));
  check('the toolbar offers "Matched devices..."', await until(`!!${BUTTON(TOOLBAR, 'Matched devices...')}`));
  check('nothing was asked before the press', asked.length === 0, JSON.stringify(asked));

  await press(TOOLBAR, 'Matched devices...');
  check('one press opens the box and asks once, with the rows as they are and nothing to apply',
    await until(`!!${BOX}`) && (await until(`${BOX}.querySelectorAll('li').length === 3`)) && asked.length === 1 && asked[0].apply === null
    && JSON.stringify(asked[0].config.parameters.map(r => r.variable_id)) === JSON.stringify(FIXTURE.parameters.map(r => r.variable_id)),
    JSON.stringify(asked.map(a => a.apply)));
  const listed = await evaluate(`[...${BOX}.querySelectorAll('li')].map(li => li.textContent.trim())`);
  check('the structures are listed in plain sentences', JSON.stringify(listed) === JSON.stringify(FIXTURE.found.structures.map(s => s.text)), JSON.stringify(listed));
  check('Matched devices stays available while the box is open', !(await evaluate(`${BUTTON(TOOLBAR, 'Matched devices...')}.disabled`)));
  check('the box has no duplicate Find button', !(await evaluate(`!!${BUTTON(BOX, 'Find')} || !!${BUTTON(BOX, 'Find again')}`)));
  check('Close is an icon with a hidden accessible label and a tooltip', await evaluate(`(() => {
    const b = ${BUTTON(BOX, 'Close')}; return !!b.querySelector('svg.icon') && b.querySelector('.sr-only')?.textContent === 'Close' && b.title.startsWith('Close:'); })()`));
  check('both matched ties are offered, ticked', JSON.stringify(await ticks()) === JSON.stringify([{ checked: true, disabled: false }, { checked: true, disabled: false }]), JSON.stringify(await ticks()));
  check('what each tie changes is said per row', /w_in_b follows w_in_a \(ratio 1\)/.test(await boxText()) && /w_load_b follows w_load_a \(ratio 1\)/.test(await boxText()), await boxText());
  check('the independent variables are counted', /Independent action variables now: 5\./.test(await boxText()));
  await shot('matched_devices_box.png', BOX);

  await evaluate(`${BOX}.querySelectorAll('tbody input[type=checkbox]')[1].click()`);
  check('unticking leaves one tie to review', await until(`!${BOX}.querySelectorAll('tbody input[type=checkbox]')[1].checked && !${BUTTON(BOX, 'Review...')}.disabled`));
  await evaluate(`${BOX}.querySelectorAll('tbody input[type=checkbox]')[1].click()`);
  await press(BOX, 'Review...');
  check('Review asks for exactly the ticked ties', await until(`!!${BOX}.querySelector('.confirm')`) && asked.length === 2
    && JSON.stringify(asked[1].apply) === JSON.stringify(FIXTURE.found.suggestions.map(s => s.id)), JSON.stringify(asked[1]?.apply));
  const header = await evaluate(`${BOX}.querySelector('.confirm h4').textContent`);
  check('the review says 5 -> 3 independent variables', header.includes('5') && header.includes('3') && header.startsWith('Tie 2'), header);
  const diffKeys = await evaluate(`[...${BOX}.querySelectorAll('.confirm tbody tr')].map(tr => tr.children.length === 6 ? tr.children[1].textContent : null).filter(Boolean)`);
  check('the diff shows the two follower rows', JSON.stringify([...new Set(diffKeys)]) === '["w_in_b","w_load_b"]', JSON.stringify(diffKeys));
  check('nothing changed before Apply', (await cell(1, 'binding_group')) === '', await cell(1, 'binding_group'));
  await shot('matched_devices_review.png', BOX);

  await press(`${BOX}.querySelector('.confirm')`, 'Apply');
  check('Apply ties the rows in the editor', await until(`${CELL(1, 'binding_group')}.value === 'w_in_a' && ${CELL(3, 'binding_group')}.value === 'w_load_a'`),
    `${await cell(1, 'binding_group')} / ${await cell(3, 'binding_group')}`);
  check('...says so and how to take it back', /Applied: 2 rows changed\. Undo in the toolbar takes it back\./.test(await boxText()), await boxText());
  check('...and the page counts 3 independent variables', await until(`/Independent action variables: 3 of 5/.test(${EDITORS}.querySelector('.fact')?.textContent ?? '')`),
    await evaluate(`${EDITORS}.querySelector('.fact')?.textContent`));
  // What was found is about the rows before Apply: it goes, and "the rows changed" no longer stands next to "Applied" (7.125).
  check('the answer about the rows before goes: no stale warning next to "Applied" and no review', await until(`!${BUTTON(BOX, 'Review...')}`)
    && await evaluate(`!/changed after this was found/.test(${BOX}.textContent) && !${BUTTON(BOX, 'Review...')}`) && /Applied: 2 rows changed/.test(await boxText()), await boxText());

  await press(TOOLBAR, 'Undo');
  check('Undo takes the ties back', await until(`${CELL(1, 'binding_group')}.value === '' && ${CELL(3, 'binding_group')}.value === ''`));
  check('...and no request was made by that', asked.length === 2, String(asked.length));
  await press(TOOLBAR, 'Matched devices...');
  check('the toolbar button refreshes the open box with one new read', await until(`${BOX}.querySelectorAll('li').length === 3`)
    && asked.length === 3 && asked[2].apply === null && !(await boxText()).includes('Applied:'));

  await press(BOX, 'Close');
  check('Close takes the box away and gives the button back', await until(`!${BOX} && !${BUTTON(TOOLBAR, 'Matched devices...')}.disabled`));

  // A configuration the backend cannot read: the box names the field and where it is listed (user report 2026-09-30:
  // "The configuration does not match the schema" alone, on real:mscr_ldo1_rgcn; record 7.125).
  invalid = true;
  await press(TOOLBAR, 'Matched devices...');
  check('a configuration that is not valid yet: the box names the field, in words, and points to the header\'s list',
    await until(`/run\\.max_evaluations: max_evaluations is missing: this field needs a value/.test(${BOX}?.textContent ?? '') && /blocking issue/.test(${BOX}?.textContent ?? '')`), await boxText());
  await shot('matched_devices_invalid.png', BOX);
  invalid = false;
  await press(BOX, 'Close');
  await until(`!${BOX}`);

  // Another tab closes the box (review of 2026-09-29): coming back to Parameters used to open it again - and ask by itself.
  await press(TOOLBAR, 'Matched devices...');
  await until(`${BOX}?.querySelectorAll('li').length === 3`);
  const askedBefore = asked.length;
  const tab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs > button')].find(b => b.textContent.startsWith(${JSON.stringify(name)})).click()`);
  await tab('Probes'); await sleep(200); await tab('Parameters'); await sleep(800);
  check('another tab closes the box: back on Parameters it stays closed and nothing was asked by itself',
    !(await evaluate(`!!${BOX}`)) && asked.length === askedBefore && !(await evaluate(`${BUTTON(TOOLBAR, 'Matched devices...')}.disabled`)), `${asked.length - askedBefore} request(s)`);

  verified = true;
  await press(TOOLBAR, 'Matched devices...');
  check('a verified task: the structures for information, the reason, no tie to tick',
    await until(`${BOX}?.querySelectorAll('li').length === 3`) && /fixed by its verified circuit profile/.test(await boxText())
    && (await ticks()).length === 0 && !(await evaluate(`!!${BUTTON(BOX, 'Review...')}`)), await boxText());
  check('...said in the normal colour: a limit, not a fault', await evaluate(`[...${BOX}.querySelectorAll('p')].some(p => /fixed by its verified/.test(p.textContent) && p.className === 'fact')`));
  await shot('matched_devices_verified.png', BOX);

  await sleep(300);
  check('the page sent no writing request but validations and this read', refused.length === 0, JSON.stringify(refused));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | '));
});
