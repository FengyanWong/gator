// Browser check of record 7.179 - room for the tables (the user's "go on" after "any advice over the whole frontend design",
// advice 1-3). Hermetic: reads pass to the backend under test, every writing request is refused.
// What it pins:
//   - with no run shown the bottom panel starts folded to its tab line and the editors take the room; a tab press opens it, a
//     reload with no run folds it again, the splitter's double click opens and folds it; with a run remembered it opens as kept;
//   - Run configuration as a property sheet: a number's label and its box on one line, the box at the right; the run limits
//     (launches, retries, wall time and the two failure rules) in one closed "Limits" fold whose line names the limits set;
//   - Output settings: "Always saved" in one line with the whole list in its tooltip; the output root's facts in one line
//     with the table folded behind it (open when the root cannot be written).
// Run: bash frontend/scripts/run_checks.sh --only room_check. About 20 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('room');
const RUN = '/fixture/room/run';
const STATUS = { state: 'completed', run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: 'mock', mock: true, worker_alive: false, run_dir: RUN,
  heartbeat_utc: '2026-10-05T01:00:00Z', stop_reason: 'budget_exhausted', error: null, active_workers: [], concurrency: 1, learner_updates: 0, first_feasible: null,
  budget: { max_evaluations: 1, max_launches: null, max_retries: 0, charged: 1, reserved: 0, in_flight: 0, completed: 1, failed: 0, released: 0, remaining: 0,
    launches: 1, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: RUN }, connection: { overall: 'not_applicable' }, summary: null,
  manifest: { mode: 'scratch', mock: true, task_id: 'fixture_task:0000', seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: 1 },
    mock_notice: 'FIXTURE MOCK DATA: nothing was started.' } };
const LABEL = name => `[...document.querySelectorAll('.right label.num')].find(l => l.firstChild?.textContent?.trim() === ${JSON.stringify(name)})`;
const FOLDED = `document.querySelector('.layout').classList.contains('bottom-folded') && !document.querySelector('.bottom-body').checkVisibility()`;

await runChecks(browser, async () => {
  const starter = await starterConfig(APP);
  const config = { schema_version: 'gator-workbench-config-v1', ...starter, run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, ...starter.run, max_spectre_launches: 42 } };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  await page.intercept(['*/api/runs/status*'], params => {
    const url = new URL(params.request.url);
    if (url.searchParams.get('run_dir') === RUN) return page.fulfil(params.requestId, 200, STATUS);
    return page.readOrRefuse(params, page.refused, { reads: true });
  }, { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors table.editor tbody tr') && !!document.querySelector('footer .tabs')`, 200));
  await sleep(1000);

  // ---- the bottom panel ------------------------------------------------------------------------------------------------------------
  const room = await evaluate(`({ folded: ${FOLDED}, tabs: document.querySelector('footer .tabs').checkVisibility(), footer: Math.round(document.querySelector('footer').getBoundingClientRect().height),
    editors: Math.round(document.querySelector('.editors').getBoundingClientRect().height), height: innerHeight })`);
  check('no run shown: the bottom panel starts folded to its tab line, and the editors take the room', room.folded && room.tabs && room.footer < 60 && room.editors > room.height * 0.6, JSON.stringify(room));
  await page.shot(path.join(out, 'room-1-no-run.png'));
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Logs').click()`);
  check('a tab press opens it', await page.until(`!(${FOLDED})`, 30));
  await send('Page.reload');
  await page.until(`!!document.querySelector('footer .tabs')`, 200); await sleep(600);
  check('a reload with no run folds it again (the press opened it for that page)', await evaluate(FOLDED));
  await evaluate(`document.querySelector('.splitter').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  check('the splitter\'s double click opens it', await page.until(`!(${FOLDED})`, 30));
  await evaluate(`document.querySelector('.splitter').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  check('...and folds it again', await page.until(FOLDED, 30));

  // ---- Run configuration as a property sheet ----------------------------------------------------------------------------------------
  const sheet = await evaluate(`[${['Concurrent Spectre jobs', 'Evaluation budget (max_evaluations)', 'Random seed (target task)'].map(LABEL).join(', ')}].map(l => {
    if (!l) return null; const t = l.querySelector('span').getBoundingClientRect(), i = l.querySelector('input').getBoundingClientRect();
    return { name: l.firstChild.textContent.trim(), sameLine: Math.abs((t.top + t.bottom) / 2 - (i.top + i.bottom) / 2) < 6, boxAtRight: i.left > t.right - 1, box: Math.round(i.width) }; })`);
  check('a number\'s label and its box are on one line, the box at the right', sheet.every(s => s && s.sameLine && s.boxAtRight && s.box < 120), JSON.stringify(sheet));
  const limits = await evaluate(`(() => { const d = document.querySelector('.right details.limits'); return d && { open: d.open, line: d.querySelector('summary').textContent,
    fields: [...d.querySelectorAll('label.num')].map(l => l.firstChild.textContent.trim()) }; })()`);
  check('the run limits are in one closed "Limits" fold', limits && !limits.open && JSON.stringify(limits.fields) === JSON.stringify(['Max Spectre launches', 'Max retries per evaluation',
    'Wall-time limit (s)', 'Pause after N consecutive infrastructure failures', 'Stop after N consecutive failed evaluations']), JSON.stringify(limits));
  check('...whose line names the limits that are set', limits?.line === 'Limits - 42 launches', limits?.line);
  const height = await evaluate(`({ right: document.querySelector('.right').scrollHeight, run: Math.round([...document.querySelectorAll('.right details.module')].find(d => d.querySelector('summary h3')?.textContent.trim() === 'Run configuration').querySelector('.module-body').getBoundingClientRect().height) })`);
  console.log(`INFO  right column ${height.right} px high, Run configuration's body ${height.run} px`);

  // ---- Output settings ---------------------------------------------------------------------------------------------------------------
  await evaluate(`(() => { const d = [...document.querySelectorAll('.right details.module')].find(x => x.querySelector('summary h3')?.textContent.trim() === 'Output settings'); d.open = true; })()`);
  await sleep(500);
  const saved = await evaluate(`(() => { const p = document.querySelector('.right p.always-saved'); const lh = parseFloat(getComputedStyle(p).lineHeight) || 16;
    return p && { text: p.textContent, oneLine: p.getBoundingClientRect().height <= lh * 1.6, title: p.title }; })()`);
  check('"Always saved" is one line, the whole list in its tooltip', !!saved && saved.oneLine && saved.text.startsWith('Always saved:') && saved.title.includes('per-evaluation records'), JSON.stringify(saved));
  const facts = await evaluate(`(() => { const d = document.querySelector('.right details.output-facts'); return d && { open: d.open, line: d.querySelector('summary').textContent, rows: d.querySelectorAll('tr').length }; })()`);
  if (facts) check('the output root\'s facts are one line, the table folded behind it (open only when the root cannot be written)',
    facts.rows >= 4 && (facts.line.startsWith('writable') ? !facts.open : facts.open), JSON.stringify(facts));
  else console.log('INFO  no output root checked on this backend: its facts line is not shown');
  await page.shot(path.join(out, 'room-2-right.png'), `document.querySelector('.right')`, { maxHeight: 1400 });

  // ---- a run remembered: the panel as kept - folded by the splitter above, so folded; opened again, so open ------------------------
  await evaluate(`localStorage.setItem('gator-workbench-current-run-v1', ${JSON.stringify(RUN)})`);
  await send('Page.reload');
  await page.until(`!!document.querySelector('footer .tabs')`, 200); await sleep(800);
  check('with a run remembered the bottom panel keeps the fold chosen with the splitter', await evaluate(FOLDED));
  await evaluate(`document.querySelector('.splitter').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  await send('Page.reload');
  await page.until(`!!document.querySelector('footer .tabs')`, 200); await sleep(800);
  check('...and opened again it is open on load', await evaluate(`!(${FOLDED})`));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
