// Current-source UI and REAL saved runs. No Fetch interception and no simulator-start action.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { openNetworks } from './lib/rl_networks.mjs';
import { launchEdge, workbenchUrl, sleep } from './lib/harness.mjs';

const [qualification] = process.argv.slice(2);
if (!qualification) throw new Error('An explicit real qualification directory is required');
const read = file => JSON.parse(readFileSync(file, 'utf8'));
const stage = read(path.join(qualification, 'stage-b', 'report.json'));
if (!stage.passed || stage.origin !== 'real') throw new Error('A passed REAL Stage B is required');
const config = read(path.join(qualification, 'stage-b', 'configuration.json'));
config.run.model_source = { ...config.run.model_source, run_dir: stage.run_directory, checkpoint_id: 'latest' };
const dir = path.join(qualification, 'ui');
mkdirSync(dir, { recursive: true });
const url = await workbenchUrl({ writes: true });
if (new URL(url).port !== '5187') throw new Error('Only the explicit scratch dev server is permitted');
const checks = [], requests = [], errors = [];
const check = (name, passed, evidence) => {
  checks.push({ name, passed: !!passed, evidence });
  if (!passed) throw new Error(name);
};
let browser, page;
try {
  const meta = await (await fetch(new URL('/api/meta', url))).json();
  check('scratch backend output root', meta.allowed_output_roots.some(p => p.includes('20260926-qualification-05')), meta.allowed_output_roots);
  const status = await (await fetch(new URL('/api/runs/status?run_dir=' + encodeURIComponent(stage.run_directory), url))).json();
  check('real B status from API', status.budget.confirmed_launches === 42 && status.budget.uncertain_launches === 0 && !status.manifest.mock, status.budget);
  const jobs = await (await fetch(new URL('/api/runs/table?table=simulator_jobs&run_dir=' + encodeURIComponent(stage.run_directory), url))).json();
  check('real job table from API', jobs.total_rows === 42, jobs.total_rows);
  browser = await launchEdge('reward-v2-real', { width: 1680, height: 1050 });
  page = await browser.open({ errors });
  await page.send('Network.enable');
  page.on('Network.requestWillBeSent', p => requests.push({ url: p.request.url, method: p.request.method }));
  await page.seed({ config, run: stage.run_directory, when: 'once' });
  await page.send('Page.navigate', { url });
  const networkPage = await openNetworks(page, browser);
  check('source page loaded', await page.until("document.querySelector('aside.right')?.textContent.includes('Reward and conditions')", 200));
  const selectFor = label => `Array.from(document.querySelectorAll('aside.right label')).find(e => e.textContent.startsWith(${JSON.stringify(label)}))?.querySelector('select')`;
  check('compressed reward selected', await page.evaluate(`(${selectFor('Violation shape')})?.value === 'compressed'`));
  check('all corners selected', await page.evaluate(`(${selectFor('Training conditions')})?.value === 'always'`));
  check('actual reset and step cost shown', await page.evaluate("document.querySelector('aside.right').innerText.includes('5 launches per candidate; 1 per reset. Launch cap: 42.')"));
  check('nominal OP selected', await page.evaluate("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel label')).find(e => e.textContent.includes('Nominal device operating points'))?.querySelector('input')?.checked === true"));
  await page.evaluate("Array.from(document.querySelectorAll('footer .tabs button')).find(e => e.textContent === 'Run status').click()", true);
  const coverage = status.best_design.conditions_complete == null ? 'unknown' : status.best_design.conditions_complete ? 'complete' : 'partial';
  check('actual real coverage visible', await page.until(`document.querySelector('.status-grid')?.innerText.includes('coverage: ${coverage}')`, 150));
  check('launch accounting visible', await page.evaluate("document.querySelector('.status-grid').innerText.includes('42 confirmed, 0 uncertain, 0 reserved')"));
  check('clearance visible', await page.evaluate("document.querySelector('.status-grid').innerText.includes('Tightest margin')"));   // its name since branch record SIF-54
  await page.shot(path.join(dir, 'desktop.png'));
  await page.evaluate("Array.from(document.querySelectorAll('aside.right h3')).find(e => e.textContent === 'Reward and conditions').scrollIntoView()", true);
  await page.shot(path.join(dir, 'reward-controls.png'));
  await page.setValue(selectFor('Violation shape'), 'capped');
  await sleep(1200);
  check('reward control updates real config', (await page.stored()).run.reward.violation_shape === 'capped');
  await page.setValue(selectFor('Violation shape'), 'compressed');
  await sleep(1200);
  await page.setValue(selectFor('Mode'), 'resume');
  // The backend remembers B as the project's last real model; no start/continue command is clicked.
  check('real model reward facts', await page.until("window.__checkRLWindow.document.querySelector('.rl-networks-panel').innerText.includes('constraint_violation_v2')", 250));
  check('real model OP facts', await page.evaluate("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel tr')).some(r => r.innerText.includes('Operating points') && r.innerText.includes('enabled'))"));
  await page.evaluate("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel tr')).find(r => r.innerText.includes('constraint_violation_v2')).scrollIntoView()", true);
  await networkPage.shot(path.join(dir, 'model-facts.png'));
  await page.viewport(1100, 800);
  await page.shot(path.join(dir, 'compact-desktop.png'));
  const overflow = await page.evaluate("Array.from(document.querySelectorAll('aside.right label, aside.right h3, .status-grid td')).filter(e => e.getBoundingClientRect().width > 0 && e.scrollWidth > e.clientWidth + 2).map(e => e.textContent.slice(0,100))");
  check('reward and status text contained', overflow.length === 0, overflow);
  check('no live 8765 request', requests.every(r => new URL(r.url).port !== '8765'));
  check('no simulator or paid agent start', requests.every(r => !/\/api\/(runs\/(start|continue|command|corner-check\/start)|agent\/chat)/.test(r.url)));
  check('no console exceptions', errors.length === 0, errors);
} catch (error) {
  if (page) {
    writeFileSync(path.join(dir, 'failure-text.txt'), await page.evaluate('document.body.innerText'));
    await page.shot(path.join(dir, 'failure.png'));
  }
  throw error;
} finally {
  if (browser) await browser.close();
  writeFileSync(path.join(dir, 'browser-report.json'), JSON.stringify({ origin: 'real', url,
    passed: checks.length >= 17 && checks.every(c => c.passed), source: 'current Vite dev source',
    run_directory: stage.run_directory, route_interception: false, simulator_calls: 0,
    checks, requests, errors }, null, 2));
}
console.log(JSON.stringify({ checks: checks.length, passed: checks.every(c => c.passed), report: path.join(dir, 'browser-report.json') }));
