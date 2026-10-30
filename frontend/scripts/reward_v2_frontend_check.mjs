// Real saved qualification data and the real API. No route interception or simulation dispatch.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { openNetworks } from './lib/rl_networks.mjs';
import { createHash } from 'node:crypto';
import { launchEdge, workbenchUrl, sleep } from './lib/harness.mjs';

const [qualification, output] = process.argv.slice(2);
if (!qualification || !output) throw new Error('Explicit real qualification and NEW evidence directories are required');
const read = file => JSON.parse(readFileSync(file, 'utf8'));
const stage = read(path.join(qualification, 'stage-b/report.json'));
if (!stage.passed || stage.origin !== 'real') throw new Error('Passed real B evidence is required');
const config = read(path.join(qualification, 'stage-b/configuration.json'));
config.run.model_source = { ...config.run.model_source, run_dir: stage.run_directory, checkpoint_id: 'latest' };
if (existsSync(path.join(output, 'browser-report.json'))) throw new Error('Preserve existing evidence; choose a new output directory');
mkdirSync(output, { recursive: true });
const url = await workbenchUrl({ writes: true });
if (new URL(url).port !== '5187') throw new Error('Only scratch port 5187 is allowed');
const checks = [], requests = [], errors = [];
let browser, page, completed = false, failure;
const check = (name, passed, evidence) => {
  checks.push({ name, passed: !!passed, evidence });
  if (!passed) throw new Error(name);
};
const label = name => `Array.from(document.querySelectorAll('aside.right label')).find(e => e.textContent.startsWith(${JSON.stringify(name)}))`;
const control = (name, type = 'select') => `(${label(name)})?.querySelector(${JSON.stringify(type)})`;
const row = (selector, name) => `Array.from(${selector === '.model-facts' ? 'window.__checkRLWindow.document' : 'document'}.querySelectorAll(${JSON.stringify(selector + ' tr')})).find(e => e.cells[0]?.textContent === ${JSON.stringify(name)})?.cells[1]?.textContent`;
try {
  const status = await (await fetch(new URL('/api/runs/status?run_dir=' + encodeURIComponent(stage.run_directory), url))).json();
  check('actual B data has 42 confirmed calls and nominal-only feasibility', status.budget.confirmed_launches === 42 && !status.manifest.mock
    && status.best_design.nominal_feasible === true && status.best_design.robust_feasible === false);
  browser = await launchEdge('reward-v2-frontend', { width: 1680, height: 1050 });
  page = await browser.open({ errors });
  await page.send('Network.enable');
  page.on('Network.requestWillBeSent', p => requests.push({ url: p.request.url, method: p.request.method }));
  await page.seed({ config, run: stage.run_directory, when: 'once' });
  await page.send('Page.navigate', { url });
  const networkPage = await openNetworks(page, browser);
  check('current source loaded', await page.until("!!document.querySelector('.reward-costs')", 200));
  check('physical plan cost', await page.evaluate(`${row('.reward-costs', 'Launches / step')} === '5' && ${row('.reward-costs', 'Launches / reset')} === '1' && ${row('.reward-costs', 'Launch cap')} === '42'`));
  check('nominal OP enabled', await page.evaluate(`(${control('Nominal device operating points', 'input')})?.checked === true`));
  for (const name of ['Worst hard-spec share', 'Objective bonus weight', 'Tightest-margin bonus weight']) {
    check(name + ' declares the backend numeric range', await page.evaluate(`(() => { const e = ${control(name, 'input')}; return e.type === 'number' && e.min === '0' && e.max === '1'; })()`));
  }
  await page.evaluate("Array.from(document.querySelectorAll('footer .tabs button')).find(e => e.textContent === 'Run status').click()", true);
  check('best is explicitly nominal feasible only', await page.until(`${row('.status-grid', 'Best design')}?.startsWith('Nominal feasible only')`, 150));
  // "used", one as one (branch record SIF-76 and its review: it read "evaluations charged")
  const firstNominal = status.budget.first_nominal_feasible.first_feasible_eval_count;
  check('actual first nominal cost', await page.evaluate(`${row('.status-grid', 'First nominal feasibility')}?.includes('at ${firstNominal} evaluation${firstNominal === 1 ? '' : 's'} used')`));
  check('no invented full-plan feasibility', await page.evaluate(`${row('.status-grid', 'First full-plan feasibility')} === 'not observed'`));
  check('actual complete condition count', await page.evaluate(`${row('.status-grid', 'Conditions evaluated / planned')} === '5 / 5'`));
  check('nominal and adverse values distinguished', await page.evaluate(`!!${row('.status-grid', 'Nominal values')} && !!${row('.status-grid', 'Worst applicable values')}`));
  check('executed reward comes from saved run', await page.evaluate(`${row('.status-grid', 'Executed reward')}?.includes('compressed; worst hard-spec share 0.5')`));

  await page.evaluate("Array.from(document.querySelectorAll('.editors .tabs button')).find(e => e.textContent.startsWith('Specs')).click()", true);
  // The objective is part of the constraint list (record 7.124): no Objective column; "Judged at" shows while corners are planned.
  check('spec labels match objective and judgement contracts', await page.evaluate("!document.querySelector('th[data-field=direction_after_feasible]') && document.querySelector('th[data-field=nominal_only]').textContent === 'Judged at' && Array.from(document.querySelector('.editor select[aria-label=\"Constraint\"]').options).some(o => o.textContent === 'interval, then lower is better')"));
  const firstJudged = "document.querySelector('.editor select[aria-label=\"Judged at\"]')";
  check('spec controls fit their option labels', await page.evaluate(`(${firstJudged}).clientWidth >= 178 && document.querySelector('.editor select[aria-label="Constraint"]').clientWidth >= 198`));
  await page.evaluate(`(${firstJudged}).scrollIntoView({block:'nearest',inline:'center'})`, true);
  await page.shot(path.join(output, 'spec-objective-conditions.png'));
  await page.setValue(firstJudged, 'nominal');
  await sleep(1100);
  check('Judged at stores a boolean, not a string', (await page.stored()).targets[0].nominal_only === true);
  await page.setValue(firstJudged, 'all');
  const powerIndex = config.targets.findIndex(t => t.metric_id === 'supply_power_w');
  if (powerIndex < 0) throw new Error('Actual B must contain its power spec');
  const powerLimit = `document.querySelectorAll('.editor select[aria-label="Constraint"]')[${powerIndex}]`;   // an interval
  await page.setValue(powerLimit, 'interval|minimize');
  check('selected objective reflected in reward controls', await page.until("document.querySelector('.reward-objective').textContent.includes('minimize supply_power_w')", 100));
  await page.setValue(powerLimit, 'interval|none');
  await page.setValue(control('Objective bonus weight', 'input'), '0.2');
  // Since record 7.183 a bonus weight without an objective row is no warning (a new configuration always has weight 1): the line says none is chosen
  check('no objective row is said plainly', await page.until("document.querySelector('.reward-objective').textContent === 'Objective: none'", 100));
  await page.setValue(control('Objective bonus weight', 'input'), '0');

  await page.setValue(control('Max retries per evaluation', 'input'), '1');
  check('robust automatic retries refused visibly', await page.until("Array.from(document.querySelectorAll('aside.right .error')).some(e => e.textContent.includes('zero automatic retries'))", 100));
  await page.setValue(control('Max retries per evaluation', 'input'), '0');
  await page.setValue(control('Max Spectre launches', 'input'), '');
  check('missing launch cap refused visibly', await page.until("Array.from(document.querySelectorAll('aside.right .error')).some(e => e.textContent.includes('positive launch cap'))", 100));
  await page.setValue(control('Max Spectre launches', 'input'), '42');
  const cornerCheck = id => `Array.from(document.querySelectorAll('.training-corners label')).find(e => e.textContent === ${JSON.stringify(id)})?.querySelector('input')`;
  const corners = config.run.conditions.corners;
  for (const id of corners.slice(1)) await page.evaluate(`(${cornerCheck(id)}).click()`, true);
  check('last corner remains selected and protected', await page.evaluate(`(${cornerCheck(corners[0])}).disabled && (${cornerCheck(corners[0])}).checked`));
  check('nominal always included', await page.evaluate(`(${cornerCheck('nominal')}).disabled && (${cornerCheck('nominal')}).checked`));
  await page.setValue(control('Training conditions'), 'off');
  await sleep(1100);
  check('nominal mode clears corners and costs one launch', (await page.stored()).run.conditions.corners.length === 0
    && await page.evaluate(`${row('.reward-costs', 'Launches / step')} === '1'`));
  await page.setValue(control('Training conditions'), 'always');

  await page.setValue(control('Mode'), 'resume');
  const compatible = "Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel summary')).some(e => e.textContent === 'Compatibility for Resume: compatible')";
  check('actual checkpoint initially resume compatible', await page.until(compatible, 300));
  check('saved reward coefficients shown', await page.evaluate(`Number(${row('.model-facts', 'Worst hard-spec share')}) === 0.5 && Number(${row('.model-facts', 'Objective bonus weight')}) === 0 && Number(${row('.model-facts', 'Tightest-margin bonus weight')}) === 0`));   // the reward block's name since SIF-80
  check('saved full condition identities shown', await page.evaluate(`${row('.model-facts', 'Saved condition plan')} === ${JSON.stringify(['nominal', ...corners].join(', '))}`));
  await page.setValue(control('Worst hard-spec share', 'input'), '0.7');
  check('reward edit refreshes exact-resume compatibility', await page.until("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel li.issue.error')).some(e => e.textContent.startsWith('reward_settings: incompatible'))", 300));
  check('old compatible verdict is no longer shown', !await page.evaluate(compatible));
  check('draft edit does not rewrite executed reward', await page.evaluate(`${row('.status-grid', 'Executed reward')}?.includes('worst hard-spec share 0.5')`));
  await page.evaluate("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel li.issue.error')).find(e => e.textContent.startsWith('reward_settings: incompatible')).scrollIntoView({block:'center'})", true);
  await page.shot(path.join(output, 'resume-reward-mismatch.png'));
  await page.setValue(control('Mode'), 'fine_tune');
  check('fine-tune describes critic and replay reset', await page.until("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel li.issue.warning')).some(e => e.textContent.startsWith('reward_settings: warning') && e.textContent.includes('resets critics, targets and replay'))", 300));
  await page.setValue(control('Worst hard-spec share', 'input'), '0.5');
  await page.setValue(control('Mode'), 'resume');
  check('restored reward becomes compatible', await page.until(compatible, 300));
  await page.evaluate(`(${cornerCheck(corners[0])}).click()`, true);
  check('corner edit refreshes exact-resume compatibility', await page.until("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel li.issue.error')).some(e => e.textContent.startsWith('planned_conditions: incompatible'))", 300));
  await page.evaluate(`(${cornerCheck(corners[0])}).click()`, true);
  check('re-adding corner restores canonical compatible plan', await page.until(compatible, 300));
  await sleep(1100);
  check('persisted contract equals original real plan', JSON.stringify((await page.stored()).run.conditions) === JSON.stringify(config.run.conditions));

  for (const [width, height] of [[1680, 1050], [1100, 800]]) {
    await page.viewport(width, height);
    await page.evaluate("Array.from(document.querySelectorAll('aside.right h3')).find(e => e.textContent === 'Reward and conditions').scrollIntoView()", true);
    await page.shot(path.join(output, `reward-${width}.png`));
    const overflow = await page.evaluate("Array.from(document.querySelectorAll('aside.right label, .reward-costs td, .status-grid td')).filter(e => e.getBoundingClientRect().width > 0 && e.scrollWidth > e.clientWidth + 2).map(e => e.textContent.slice(0,100))");
    check(`reward/status text contained at ${width}`, !overflow.length, overflow);
  }
  const finalStatus = await (await fetch(new URL('/api/runs/status?run_dir=' + encodeURIComponent(stage.run_directory), url))).json();
  check('real run and launch cost unchanged', finalStatus.budget.confirmed_launches === 42 && finalStatus.learner_updates === 7 && finalStatus.state === status.state);
  check('no request to live 8765', requests.every(r => new URL(r.url).port !== '8765'));
  check('no simulator or paid-agent dispatch', requests.every(r => !/\/api\/(runs\/(start|baseline|continue|command|corner-check\/start)|agent\/chat)/.test(r.url)));
  check('no browser exceptions', errors.length === 0, errors);
  completed = true;
} catch (error) {
  failure = String(error.stack ?? error);
  if (page) {
    writeFileSync(path.join(output, 'failure-text.txt'), await page.evaluate('document.body.innerText'));
    await page.shot(path.join(output, 'failure.png'));
  }
  throw error;
} finally {
  if (browser) await browser.close();
  const files = ['src/panels/Right.tsx', 'src/panels/useRlModel.ts', 'src/panels/rlModelText.ts', 'src/panels/RewardConditions.tsx', 'src/panels/Editors.tsx', 'src/panels/RunTabs.tsx', 'src/styles.css', 'scripts/reward_v2_frontend_check.mjs', 'vite.reward-ui.config.mjs'];
  writeFileSync(path.join(output, 'browser-report.json'), JSON.stringify({ origin: 'real', url, passed: completed && checks.every(c => c.passed),
    source: 'current Vite source; unchanged real optimizer/backend', run_directory: stage.run_directory,
    source_hashes: Object.fromEntries(files.map(file => [file, createHash('sha256').update(readFileSync(file)).digest('hex')])),
    route_interception: false, simulator_calls: 0, checks, requests, errors, failure }, null, 2));
}
console.log(JSON.stringify({ checks: checks.length, passed: completed, report: path.join(output, 'browser-report.json') }));
