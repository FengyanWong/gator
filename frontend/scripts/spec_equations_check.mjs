// Browser check of "each spec is an equation over the probes" (status record 7.52): the Specs tab edits `equation`, an
// older saved Specs row (one probe in `measurement_id`) is read as its equation, and what is typed is judged by the REAL
// backend's validation. Same approach as task_rows_check.mjs: a throwaway headless Edge over the DevTools protocol.
// Requests: GET, POST /api/circuit/load and POST /api/config/validate pass through (read-only: local files, no bridge, no
// simulation), every other writing request is refused here - so it is safe on any backend, but it needs one that KNOWS
// equations (restarted after 7.52, or a scratch one).
// The browser profile is new and temporary: the user's saved configuration is not touched.
// Run (Windows node through WSL interop; node >= 22):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/spec_equations_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('specs');

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, consoleErrors } = page;
  const refused = [];
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (request.method === 'GET' || name === '/api/config/validate' || name === '/api/circuit/load') return page.pass(requestId);
    if (name !== '/api/output/check') refused.push(`${request.method} ${name}`);            // the output-folder look-up: refused, harmless
    return page.refuse(requestId);
  };
  const until = (expression, tries = 100) => page.until(expression, tries);
  const EDITORS = `document.querySelector('.editors')`;
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith(${JSON.stringify(name)})).click()`);
  const headers = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim())`);
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.textContent.replace(' *', '').trim()).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const cell = (row, name) => evaluate(`${CELL(row, name)}.value`);
  const type = (row, name, v) => page.setValue(`${CELL(row, name)}`, v, { event: 'input' });
  const issues = row => evaluate(`[...${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].querySelectorAll('td.issues .issue')].map(d => d.textContent.trim())`);
  const issuesUntil = async (row, wanted, absent = []) => {
    for (let i = 0; i < 60; i++) {
      const found = await issues(row);
      if (wanted.every(w => found.includes(w)) && absent.every(a => !found.some(f => f.includes(a)))) return [true, found];
      await sleep(150);
    }
    return [false, await issues(row)];
  };
  const shot = name => page.shot(path.join(out, name));

  await page.intercept(['*/api/*'], answer);
  // The page opens as a browser that saved its configuration BEFORE specs had equations: one probe in `measurement_id`.
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const legacy = starter.targets.map(t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k === 'equation' ? 'measurement_id' : k, v])));
  check('the backend knows equations (restarted after 7.52)', starter.targets[0]?.equation === 'm_score', JSON.stringify(starter.targets[0]));
  const SEED = { schema_version: 'gator-workbench-config-v1', ...starter, targets: legacy,
    run: { mode: 'scratch', concurrency: 1, threads_per_job: 1, ...starter.run }, output: { experiment_name: 'fixture' }, research: {} };
  await page.seed({ config: SEED, when: 'missing' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await until(`!!${EDITORS}`));
  await openTab('Specs');
  check('the Specs tab edits an equation, right after the spec name', JSON.stringify((await headers()).slice(1, 3)) === '["metric_id","equation"]', JSON.stringify(await headers()));
  check('an older saved row shows its probe as the equation', await until(`${CELL(0, 'equation')}?.value === 'm_score'`), await cell(0, 'equation'));
  const saved = await evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1200))`);
  check('...and is saved back in the new form, in the same place', JSON.stringify(Object.keys(saved.targets[0]).slice(0, 2)) === '["metric_id","equation"]'
    && !('measurement_id' in saved.targets[0]), JSON.stringify(saved.targets[0]));
  check('the old row is valid as it is', (await issuesUntil(0, [], ['error', 'blocker']))[0], JSON.stringify(await issues(0)));
  check('the tab names the probes an equation can use', /Probes: m_score\./.test(await evaluate(`${EDITORS}.querySelector('.spec-probes')?.textContent ?? ''`)));

  // a formula: its own name, a unit that cannot be checked, a new entry in the network's result registry
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => b.textContent.trim() === 'Add').click()`);
  await until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === 2`);
  // "Add" used to give a required field the schema's `default: null` (constraint): the row was invalid. normalization_scale
  // may be empty since 7.92 (2026-09-26): the violation is then divided by the size of the threshold.
  const added = (await evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1000))`)).targets[1];
  check('a new spec row starts complete: the first probe as its equation, in its unit, a constraint, and an empty scale (the threshold size)',
    added?.equation === 'm_score' && added?.unit === 'fixture' && added?.constraint === '>=' && added?.normalization_scale === null, JSON.stringify(added));
  await type(1, 'metric_id', 'score_sq'); await type(1, 'equation', 'm_score ** 2'); await type(1, 'unit', 'fixture'); await type(1, 'lower', '0.5');
  let [ok, found] = await issuesUntil(1, ['warning: equation_unit_unchecked', 'info: spec_adds_registry_entry'], ['error', 'blocker']);
  const row = async () => JSON.stringify((await evaluate(`new Promise(r => setTimeout(() => r(JSON.parse(localStorage.getItem('gator-workbench-config-v1'))), 1000))`)).targets[1])
    + ' | page issues: ' + JSON.stringify(await evaluate(`[...document.querySelectorAll('.editors .issue')].map(d => d.textContent.trim())`));
  check('a formula is accepted: its unit is not checkable, its name is new to the registry', ok, JSON.stringify(found) + (ok ? '' : ' ' + await row()));
  await shot('spec_equation_formula.png');
  await type(1, 'equation', 'm_nope * 2');
  [ok, found] = await issuesUntil(1, ['error: equation_unknown_probe']);
  check('a probe that does not exist is named as an error', ok, JSON.stringify(found));
  await type(1, 'equation', 'abs(m_score)');
  [ok, found] = await issuesUntil(1, ['error: equation_rejected']);
  check('a function call is refused, not evaluated', ok, JSON.stringify(found));
  await type(1, 'metric_id', 'm_score'); await type(1, 'equation', 'm_score * 2');
  [ok, found] = await issuesUntil(1, ['error: spec_name_is_a_probe']);
  check('a formula may not take the name of a probe', ok, JSON.stringify(found));
  await type(1, 'metric_id', 'score'); await type(0, 'metric_id', 'score_plain');
  [ok, found] = await issuesUntil(1, ['error: spec_name_is_a_result']);
  check('a formula may not take the name of a simulator result', ok, JSON.stringify(found));

  check('the page sent no writing request but validations', refused.length === 0, JSON.stringify(refused));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | '));
});
