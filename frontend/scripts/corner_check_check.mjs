// Browser check of the "Corner check" tab (status record 7.62): the shown run's safest feasible designs simulated again at
// five fixed corners. Same approach as save_now_check.mjs: a throwaway headless Edge over the DevTools protocol against a
// RUNNING workbench (default http://127.0.0.1:8765/). The shown run and EVERY /api/runs/* request, the corner check's
// included, are answered HERE by FIXTURE data; other GET requests pass through and every other writing request is refused.
// So this check starts, stops and simulates NOTHING on the backend it runs against - it is safe next to a live run, and it
// works against a backend that does not have the corner-check routes yet. The browser profile is new and temporary.
// What it pins: the tab sits after "Output files" and "Training"; the plan is read when the tab opens and when "Designs" changes, and
// says what a press costs; the explanation is folded; a MOCK check starts without a question, sends the plan it showed and
// shows progress, a Stop button and the grid (pass / FAIL with the spec and its value / unknown with the reason), then the
// verdicts - and stops reading once it has ended; a REAL check asks for the budget first (no = nothing sent), then the
// connection question, and sends both answers; a finished real check says whether the cell was restored and whether the
// nominal repeat agreed with the run; an unsupported circuit is a neutral note with Check off; earlier checks are chosen by
// double click.
// Run (Windows node through WSL interop; node >= 22 for the built-in WebSocket; about 30 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/corner_check_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { validConfiguration, check, launchEdge, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('corners');

// ---- the fixture run and its corner checks ------------------------------------------------------------------------------
const DIR = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task/scratch__seed0__0001';
const C0 = '20260921T090000Z-0000a000', C1 = '20260922T100000Z-00c0ffee', C2 = '20260922T101500Z-00beef00';
const CORNERS = [['nominal', 'tt', 27, 1.0], ['ss_hot_low', 'ss', 125, 0.9], ['ff_cold_high', 'ff', -40, 1.1], ['fs_nominal', 'fs', 27, 1.0], ['sf_nominal', 'sf', 27, 1.0]]
  .map(([id, s, t, v]) => ({ id, model_section: s, temperature_c: t, supply_v: v, label: `${s.toUpperCase()}, ${t} \u00b0C, ${v} V` }));
const DESIGNS = [0, 1, 2].map(i => ({ evaluation_id: `e${i}aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, completion_index: [8, 15, 3][i], reward: 0, min_margin: [0.21, 0.12, 0.05][i],
  tightest_spec: 'unity_gain_hz', spec_values: { unity_gain_hz: 4e6, supply_power_w: 1.5e-6 },
  widths: [{ variable_id: 'input_pair', instance_path: 'XU1/M1', parameter_name: 'w', value: [4.2e-6, 4.1e-6, 4.0e-6][i], unit: 'm' },
    { variable_id: 'input_pair', instance_path: 'XU1/M2', parameter_name: 'w', value: [4.2e-6, 4.1e-6, 4.0e-6][i], unit: 'm' }],
  assignment: [] }));
const UNITS = { unity_gain_hz: 'Hz', supply_power_w: 'W', gain_db_at_start: 'dB' };
const record = (d, c) => {                       // #1 passes everywhere, #2 fails power at ff, #3 has no answer at ss
  const corner = CORNERS[c].id, fail = d === 1 && corner === 'ff_cold_high', unknown = d === 2 && corner === 'ss_hot_low';
  return { index: d * 5 + c + 1, design: d, evaluation_id: DESIGNS[d].evaluation_id, corner, state: fail ? 'failed' : unknown ? 'unknown' : 'passed',
    status: unknown ? 'timeout' : 'ok', reason_code: unknown ? 'python_timeout' : 'validated', metric_units: UNITS,
    metrics: unknown ? {} : { unity_gain_hz: 4e6, supply_power_w: fail ? 2.6e-6 : 1.5e-6, gain_db_at_start: 30 },
    failing: fail ? [{ metric_id: 'supply_power_w', value: 2.6e-6, unit: 'W', lower: 0, upper: 2.1e-6, violation: 0.5 }] : [],
    error_summary: unknown ? 'FIXTURE: the simulator did not answer in time' : null };
};
const ALL = [0, 1, 2].flatMap(d => [0, 1, 2, 3, 4].map(c => record(d, c)));
const worst = { unity_gain_hz: { value: 4e6, corner_id: 'nominal', valid_corner_count: 5, complete: true },
  supply_power_w: { value: 1.65e-6, corner_id: 'ff_cold_high', valid_corner_count: 5, complete: true } };
const summaryOf = real => ({ verdicts: { accepted: 1, rejected: 1, inconclusive: 1 }, designs: [
    { evaluation_id: DESIGNS[0].evaluation_id, rank: 1, disposition: 'accepted', pass_rate: 1, worst_case_metrics: worst, nominal_repeat: { matches: true, differences: [] } },
    { evaluation_id: DESIGNS[1].evaluation_id, rank: 2, disposition: 'rejected', pass_rate: 0.8, worst_case_metrics: worst,
      nominal_repeat: real ? { matches: false, differences: [{ metric_id: 'unity_gain_hz', run: 4e6, check: 3.9e6 }] } : { matches: true, differences: [] } },
    { evaluation_id: DESIGNS[2].evaluation_id, rank: 3, disposition: 'inconclusive', pass_rate: null, worst_case_metrics: worst, nominal_repeat: { matches: true, differences: [] } }],
  restoration: real ? { state: 'recovery_required', error: 'FIXTURE: the widths read back after restoring differ', journal: '/fixture/bridge-state/session' } : null });
const sim = { mock: true, supported: true, reason: null, checks: [], stage: {}, planRequests: [], starts: [], stops: [], statusReads: {}, refuseNextStart: null };
const planOf = n => ({ run_dir: DIR, run_id: 'fixture-run', task_key: sim.mock ? 'synthetic:gpdk045_ota5' : 'real:gpdk045_ota5', mock: sim.mock,
  supported: sim.supported, reason: sim.reason, code: sim.supported ? null : 'corners_unsupported', corners: CORNERS, designs: sim.supported ? DESIGNS.slice(0, n) : [],
  counts: { evaluations: 30, feasible: 12, distinct: 9, skipped: [] }, simulations: sim.supported ? 5 * n : 0, limit: n, max_designs: 3,
  selection_rule: 'FIXTURE', notice: sim.mock ? 'FIXTURE MOCK: the toy score has its optimum moved at each corner.' : null, checks: sim.checks });
const checkOf = id => {
  const stage = sim.stage[id] ?? 'done', real = id === C2, done = stage === 'running' ? 8 : 15;
  return { check_id: id, alive: stage === 'running', request: { check_id: id, created_utc: '2026-09-22T10:00:00+00:00', mock: !real, simulations: 15, corners: CORNERS, designs: DESIGNS },
    status: { state: stage === 'running' ? 'running' : 'completed', done, started: stage === 'running' ? 9 : 15, total: 15, current: { design: 1, corner: 'fs_nominal' } },
    results: ALL.slice(0, done), summary: stage === 'running' ? null : summaryOf(real) };
};
const RUN_STATUS = { state: 'completed', run_id: 'fixture-run', mode: 'scratch', provenance: 'mock', mock: true, worker_alive: false, run_dir: DIR, active_workers: [], concurrency: 1,
  budget: { max_evaluations: 30, charged: 30, in_flight: 0, completed: 30, failed: 0, remaining: 0, launches: 30, retries: 0, cache_hits: 0 }, best_design: null, first_feasible: null,
  paths: { run_dir: DIR }, connection: { overall: 'not_applicable' }, summary: null, manifest: { mode: 'scratch', mock: true, mock_notice: 'FIXTURE MOCK DATA' } };
const VALID = validConfiguration({ mock: true });

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);
  const page = await browser.open({ consoleApi: false });
  const { send, fulfil, consoleErrors } = page;
  const refused = []; const dialogs = []; const answers = [];
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/status') return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, RUN_STATUS) : fulfil(requestId, 404, { detail: 'Not a run directory' });
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: [] });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/corner-check/plan') {
      const n = Number(url.searchParams.get('designs') ?? 3);
      sim.planRequests.push(n);
      return fulfil(requestId, 200, planOf(n));
    }
    if (name === '/api/runs/corner-check/status') {
      const id = url.searchParams.get('check_id');
      sim.statusReads[id] = (sim.statusReads[id] ?? 0) + 1;
      if (sim.failStatus) return fulfil(requestId, 503, { detail: 'FIXTURE: check status unavailable' });
      return fulfil(requestId, 200, checkOf(id));
    }
    if (name === '/api/runs/corner-check/start') {
      sim.starts.push(body);
      if (sim.refuseNextStart) { const detail = sim.refuseNextStart; sim.refuseNextStart = null; return fulfil(requestId, 409, { detail }); }
      const id = body.authorize_real_simulation ? C2 : C1;
      sim.stage[id] = 'running';
      sim.checks = [{ check_id: id, created_utc: '2026-09-22T10:00:00+00:00', state: 'running', alive: true, done: 8, total: 15, mock: id === C1, verdicts: null }, ...sim.checks];
      return fulfil(requestId, 200, { check_id: id, worker_pid: 1, simulations: body.simulations, mock: id === C1 });
    }
    if (name === '/api/runs/corner-check/stop') { sim.stops.push(body); return fulfil(requestId, 200, { id: 'fixture-stop', command: 'stop' }); }
    return page.readOrRefuse({ requestId, request }, refused);
  };
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: answers.shift() ?? false }); });
  const evaluate = expression => page.evaluate(expression, true);
  const until = (expression, tries = 80) => page.until(expression, tries);
  const waitFor = async (test, tries = 60) => { for (let i = 0; i < tries; i++) { if (test()) return true; await sleep(100); } return !!test(); };   // on this side
  const TAB = `document.querySelector('.corner-check')`;
  const BUTTON = caption => `[...document.querySelectorAll('.corner-check .row button')].find(b => b.textContent === ${JSON.stringify(caption)})`;
  const text = () => evaluate(`${TAB}?.innerText ?? ''`);
  const cells = () => evaluate(`[...document.querySelectorAll('table.corner-grid tbody tr')].map(r => [...r.cells].map(c => c.textContent.trim()))`);
  const shot = async name => page.shot(path.join(out, name),
    await evaluate(`(() => { const r = document.querySelector('footer').getBoundingClientRect(); return { x: 0, y: r.y, width: 1680, height: r.height, scale: 1 }; })()`));

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, run: DIR, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!document.querySelector('footer .tabs')`, 150))) throw new Error('the page never showed its bottom tabs: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  // the tab is offered where corners can be used: a MOCK run is (record 7.182), once its status has come
  await until(`[...document.querySelectorAll('footer .tabs > button')].some(b => b.textContent === 'Corner check')`, 60);
  const tabs = await evaluate(`[...document.querySelectorAll('footer .tabs > button')].map(b => b.textContent)`);
  if (!tabs.includes('Corner check')) throw new Error(`this page has no "Corner check" tab (${tabs.join(', ')}): the served frontend is older than it (npm run build, then reload)`);

  // ---- the tab and its plan ----------------------------------------------------------------------------------------------------
  // since record 7.193 the Training tab stands between them (the user asked for it beside Output files)
  check('the tab sits after "Output files" and "Training"', tabs[tabs.indexOf('Output files') + 1] === 'Training' && tabs[tabs.indexOf('Training') + 1] === 'Corner check', tabs.join(' | '));
  check('nothing about corners is read before the tab is opened', sim.planRequests.length === 0);
  await evaluate(`[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent === 'Corner check').click()`);
  check('opening it reads the plan once, for 3 designs', await until(`${TAB}?.innerText.includes('3 designs x 5 corners = 15 MOCK simulations (free)')`) && sim.planRequests.join() === '3', sim.planRequests.join());
  let now = await text();
  check('the MOCK notice is shown', now.includes('FIXTURE MOCK: the toy score has its optimum moved'));
  check('Check is on, and reads only "Check"', await evaluate(`!!(${BUTTON('Check')}) && !${BUTTON('Check')}.disabled && ${BUTTON('Check')}.classList.contains('primary')`));
  const designRows = await evaluate(`[...document.querySelectorAll('table.corner-designs tbody tr')].map(r => r.textContent)`);
  check('the three designs are listed, safest first, with their margin and sizes', designRows.length === 3 && /0\.21.*unity_gain_hz/.test(designRows[0]) && designRows[0].includes('input_pair 4.2 um'), designRows[0]);
  check('the counts and the corners are said in one line', now.includes('12 feasible evaluations, 9 different designs') && now.includes('ss_hot_low (SS, 125 \u00b0C, 0.9 V)'));
  check('the explanation is folded (one click away)', await evaluate(`(() => { const d = [...document.querySelectorAll('.corner-check details')].find(x => x.querySelector('summary')?.textContent === 'What the corner check does');
    return !!d && !d.open && ![...d.querySelectorAll('p')].some(p => p.checkVisibility()); })()`));
  await page.setValue(`document.querySelector('.corner-check select')`, '1');
  check('"Designs 1" reads the plan again and costs 5 simulations', await until(`${TAB}.innerText.includes('1 design x 5 corners = 5 MOCK simulations')`) && sim.planRequests.at(-1) === 1);
  await page.setValue(`document.querySelector('.corner-check select')`, '3');
  await until(`${TAB}.innerText.includes('3 designs x 5 corners = 15')`);
  await shot('corners-1-plan.png');

  // ---- a MOCK check: no question, the plan it showed, progress, Stop, then the verdicts --------------------------------------------------
  await evaluate(`${BUTTON('Check')}.click()`);
  check('a MOCK check starts without a question', await waitFor(() => sim.starts.length === 1));
  check('... and no dialog opened', dialogs.length === 0, dialogs.join(' | '));
  const first = sim.starts[0] ?? {};
  check('it sends the plan it showed: 3 designs, their IDs, 15 simulations, no real authorization', first.designs === 3 && first.simulations === 15 && first.run_dir === DIR
    && JSON.stringify(first.expected_designs) === JSON.stringify(DESIGNS.map(d => d.evaluation_id)) && !first.authorize_real_simulation, JSON.stringify(first));
  check('while it works: progress, and Stop in the place of Check', await until(`${TAB}.innerText.includes('Running: 8 of 15 simulations') && !!(${BUTTON('Stop')}) && !(${BUTTON('Check')})`, 60));
  let grid = await cells();
  check('the grid has one row per design and one column per corner, plus the verdict', grid.length === 3 && grid.every(r => r.length === 7), JSON.stringify(grid.map(r => r.length)));
  check('finished corners say pass / FAIL with the spec and its value; the corner in flight says running', grid[0].slice(1, 6).every(c => c === 'pass')
    && grid[1][3] === 'FAIL supply_power_w 2.6 uW' && grid[1][4] === 'running...' && grid[2][2] === '-' && grid[0][6] === 'checking...', JSON.stringify(grid[1]));
  check('the check is read again while it works', await waitFor(() => (sim.statusReads[C1] ?? 0) >= 3, 50), String(sim.statusReads[C1]));
  sim.failStatus = true;
  await evaluate(`${BUTTON('Refresh')}.click()`);
  check('a failed status read cannot enable a second check', await until(`${TAB}.innerText.includes('FIXTURE: check status unavailable') && (${BUTTON('Check')})?.disabled`));
  sim.failStatus = false;
  check('status polling recovers after a read error', await until(`!!(${BUTTON('Stop')}) && !${TAB}.innerText.includes('FIXTURE: check status unavailable')`));
  await shot('corners-2-running.png');
  await evaluate(`${BUTTON('Stop')}.click()`);
  check('Stop sends one stop for this check', await waitFor(() => sim.stops.length === 1) && sim.stops[0].check_id === C1 && sim.stops[0].run_dir === DIR, JSON.stringify(sim.stops));
  sim.stage[C1] = 'done';
  sim.checks = sim.checks.map(c => c.check_id === C1 ? { ...c, state: 'completed', alive: false, done: 15, verdicts: { accepted: 1, rejected: 1, inconclusive: 1 } } : c);
  check('when it has ended: the verdicts, and Check is back', await until(`${TAB}.innerText.includes('Completed: 15 of 15 simulations - 1 accepted, 1 rejected, 1 inconclusive.') && !!(${BUTTON('Check')})`, 60));
  grid = await cells();
  check('each design has its verdict and pass count', /accepted.*5\/5/.test(grid[0][6]) && /rejected.*4\/5/.test(grid[1][6]) && /^inconclusive$/.test(grid[2][6]), JSON.stringify(grid.map(r => r[6])));
  check('an unanswered corner says unknown and why, not FAIL', grid[2][2] === 'unknown (timeout)', grid[2][2]);
  const reads = sim.statusReads[C1];
  await sleep(3500);
  check('once it has ended it is no longer read', sim.statusReads[C1] === reads, `${reads} -> ${sim.statusReads[C1]}`);
  check('a MOCK check says nothing about a cell', !(await text()).includes('cell'));
  check('the worst values are folded', await evaluate(`(() => { const d = [...document.querySelectorAll('.corner-result details')][0]; return !!d && !d.open; })()`));
  await evaluate(`[...document.querySelectorAll('.corner-result details')][0].open = true`);
  check('... and list each spec with its corner', await until(`[...document.querySelectorAll('.corner-result details table tbody tr')].some(r => r.textContent.includes('supply_power_w') && r.textContent.includes('1.65 uW') && r.textContent.includes('ff_cold_high'))`));
  await shot('corners-3-done.png');

  // ---- a REAL circuit: the budget question first (no = nothing sent), then the connection question --------------------------------------------
  sim.mock = false;
  await evaluate(`[...document.querySelectorAll('.corner-check .row button')].find(b => b.textContent === 'Refresh').click()`);
  check('for a real circuit the line says REAL and that it asks first', await until(`${TAB}.innerText.includes('15 REAL Spectre simulations (asks for your authorization first)')`));
  answers.push(false);
  const startsBefore = sim.starts.length;
  await evaluate(`${BUTTON('Check')}.click()`);
  check('pressing Check asks for the budget, naming the circuit and the count', await waitFor(() => dialogs.length === 1)
    && dialogs[0].includes('This runs 15 REAL Spectre simulations of real:gpdk045_ota5') && dialogs[0].includes('Authorize 15 simulations?'), dialogs[0]);
  check('answering no sends nothing and says so', await until(`${TAB}.innerText.includes('Not started: you answered no, so nothing was created.')`) && sim.starts.length === startsBefore);
  answers.push(true, true);
  sim.refuseNextStart = { code: 'connection_gate_acknowledge', message: 'FIXTURE: some layers are unknown', report: { uncertain: ['license'] } };
  await evaluate(`${BUTTON('Check')}.click()`);
  check('yes, then the connection question, then the start with both answers', await (async () => { await waitFor(() => sim.starts.length >= startsBefore + 2);
    const [a, b] = sim.starts.slice(startsBefore); return dialogs.length === 3 && dialogs[2].includes('Connection layers are UNKNOWN: license')
      && a?.authorize_real_simulation === true && !a.acknowledge_unknown_connection && b?.authorize_real_simulation === true && b.acknowledge_unknown_connection === true && b.simulations === 15; })(),
    JSON.stringify(sim.starts.slice(startsBefore)));
  sim.stage[C2] = 'done';
  sim.checks = sim.checks.map(c => c.check_id === C2 ? { ...c, state: 'completed', alive: false, done: 15 } : c);
  check('a finished real check says loudly when the cell was not restored', await until(`document.querySelector('.corner-result .blocker')?.textContent.includes('The cell may still hold a checked design') ?? false`, 80));
  check('... and when a nominal repeat differs from the run', await until(`document.querySelector('.corner-result p.warn')?.textContent.includes('design #2 differs') ?? false`));
  await shot('corners-4-real.png');

  // ---- earlier checks: double click shows one --------------------------------------------------------------------------------------------
  sim.checks = [...sim.checks, { check_id: C0, created_utc: '2026-09-21T09:00:00+00:00', state: 'completed', alive: false, done: 15, total: 15, mock: true, verdicts: { accepted: 3, rejected: 0, inconclusive: 0 } }];
  await evaluate(`[...document.querySelectorAll('.corner-check .row button')].find(b => b.textContent === 'Refresh').click()`);
  check('earlier checks are one closed line', await until(`[...document.querySelectorAll('.corner-check > details')].some(d => d.querySelector('summary').textContent === 'Earlier checks of this run (3)' && !d.open)`));
  await evaluate(`[...document.querySelectorAll('.corner-check > details')].find(d => d.querySelector('summary').textContent.startsWith('Earlier checks')).open = true`);
  const readsBefore = sim.statusReads[C0] ?? 0;
  await evaluate(`(() => { const row = [...document.querySelectorAll('table.corner-checks tbody tr')].find(r => r.textContent.includes(${JSON.stringify(C0)}));
    row.cells[0].dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); })()`);
  check('a double click shows that check', await until(`document.querySelector('.corner-result h4')?.textContent.includes(${JSON.stringify(C0)}) ?? false`) && (sim.statusReads[C0] ?? 0) > readsBefore);

  // ---- a circuit the corners are not prepared for: a neutral note, Check off ------------------------------------------------------------
  Object.assign(sim, { supported: false, reason: 'FIXTURE: real:gpdk045_ldo is qualified at its normal condition only.' });
  await evaluate(`[...document.querySelectorAll('.corner-check .row button')].find(b => b.textContent === 'Refresh').click()`);
  check('an unsupported circuit is a neutral note, not an error', await until(`document.querySelector('.corner-check p.note')?.textContent.includes('qualified at its normal condition only') ?? false`)
    && !(await evaluate(`[...document.querySelectorAll('.corner-check .error, .corner-check .blocker')].some(e => e.textContent.includes('qualified'))`)));
  check('... and Check is off', await evaluate(`${BUTTON('Check')}.disabled`));
  await shot('corners-5-unsupported.png');

  reportRefused(refused);
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
