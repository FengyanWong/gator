// Requires a Vite source preview. No backend requests: the fixture holds and resolves every read in memory.
import { check, fail, finish, launchEdge, sleep, workbenchUrl } from './lib/harness.mjs';

const base = await workbenchUrl();
const browser = await launchEdge('request-lifecycle');
try {
  const page = await browser.open();
  await page.intercept(['*/api/*'], p => page.refuse(p.requestId));
  await page.send('Page.navigate', { url: new URL('/scripts/fixtures/request_lifecycle.html', base).href });
  if (!await page.until('!!window.fixture && !!document.querySelector("#result")')) throw new Error('This check needs a Vite source preview.');
  const pending = (kind, run) => `fixture.pending.filter(p => !p.done && p.kind === ${JSON.stringify(kind)} && p.run === ${JSON.stringify(run)}).length`;
  const wait = async (kind, run) => { if (!await page.until(`${pending(kind, run)} > 0`)) throw new Error(`No ${kind} request for ${run}`); };
  const resolve = (kind, run, value) => page.evaluate(`fixture.finish(${JSON.stringify(kind)}, ${JSON.stringify(run)}, ${JSON.stringify(value)})`);
  const select = (id, value) => page.setValue(`document.querySelector('#${id}')`, value);
  const panel = 'document.querySelector("#panel").textContent';
  const state = 'JSON.parse(document.querySelector("#result").textContent)';
  const exportButton = `document.querySelector('button[title^="Export status"]')`;   // the tab's run commands went on 2026-09-29
  const status = (run, phase = 'running') => ({ run_dir: run, state: phase, worker_alive: phase === 'running', active_workers: [] });

  await sleep(350);
  check('slow polling leaves exactly one request in flight', await page.evaluate('fixture.pending.length === 1'));
  await resolve('status', 'A', status('A'));
  check('first response is displayed', await page.until(`${state}.value?.run_dir === 'A'`));
  await wait('status', 'A');
  await sleep(200);
  check('next slow poll also stays single', await page.evaluate(`${pending('status', 'A')} === 1`));
  await select('run', 'B');
  check('run switch hides old status before new response', await page.until(`${state}.value === null`));
  check('run switch cancels the old transport', await page.evaluate("fixture.pending.find(p => !p.done && p.kind === 'status' && p.run === 'A').signal.aborted"));
  await wait('status', 'B');
  await resolve('status', 'B', status('B', 'completed'));
  await resolve('status', 'A', status('A'));
  check('late old-run response cannot replace new status', await page.until(`${state}.value?.run_dir === 'B' && ${state}.value.state === 'completed'`));
  await select('interval', '60000');
  check('changing polling interval keeps same-run status', await page.evaluate(`${state}.value?.run_dir === 'B'`));
  await wait('status', 'B');
  const held = await page.evaluate("fixture.pending.filter(p => p.kind === 'status' && p.run === 'B').length");
  await page.evaluate("document.querySelector('#refresh').click()");
  check('Refresh replaces a hung read for the same run', await page.until(`fixture.pending.filter(p => p.kind === 'status' && p.run === 'B').length === ${held + 1}`));
  check('replaced read receives cancellation', await page.evaluate("fixture.pending.filter(p => !p.done && p.kind === 'status' && p.run === 'B')[0].signal.aborted"));
  await page.evaluate(`(() => { const p = fixture.pending.filter(p => !p.done && p.kind === 'status' && p.run === 'B').at(-1); p.done = true; p.resolve(${JSON.stringify(status('B', 'paused'))}); })()`);
  await resolve('status', 'B', status('B', 'failed'));
  check('late same-run reply cannot replace the refreshed answer', await page.until(`${state}.value?.state === 'paused'`));

  await select('timeout', '120');
  check('a hung read has a deadline and leaves loading', await page.until(`${state}.error?.includes('timed out') && !${state}.loading`));
  check('deadline aborts the underlying read', await page.evaluate("fixture.pending.filter(p => p.kind === 'status').at(-1).signal.aborted"));
  await page.evaluate("fixture.pending.filter(p => !p.done && p.kind === 'status').forEach(p => { p.done = true; p.resolve(null); })");
  await select('timeout', '30000');
  await wait('status', 'B');
  await resolve('status', 'B', status('B', 'completed'));
  check('a new read recovers after timeout', await page.until(`${state}.value?.state === 'completed' && ${state}.error === null`));

  await select('tab', 'data');
  await wait('evaluations', 'B');
  await select('run', 'A');
  await wait('evaluations', 'A');
  const table = run => ({ columns: ['marker'], total_rows: 1, cutoff_commit_seq: 1, rows: [{ marker: `ROW_${run}` }] });
  await resolve('evaluations', 'A', table('A'));
  await resolve('evaluations', 'B', table('B'));
  check('Data tab rejects an old run response', await page.until(`${panel}.includes('ROW_A') && !${panel}.includes('ROW_B')`));
  await page.setValue('document.querySelector("#panel select")', 'metrics');
  check('table switch clears previous rows', await page.until(`!${panel}.includes('ROW_A')`));
  await resolve('metrics', 'A', table('METRICS'));
  check('new table rows arrive normally', await page.until(`${panel}.includes('ROW_METRICS')`));

  await select('tab', 'files');
  await wait('files', 'A');
  await select('run', 'B');
  await wait('files', 'B');
  const files = run => ({ files: [{ path: `${run}.json`, bytes: 10, modified_utc: '2026-09-26T00:00:00Z' }], total_bytes: 10 });
  await resolve('files', 'B', files('B'));
  await resolve('files', 'A', files('A'));
  check('Files tab rejects an old run response', await page.until(`${panel}.includes('B.json') && !${panel}.includes('A.json')`));
  await page.evaluate(`document.querySelector('#panel button[title^="Refresh"]').click()`);
  await wait('files', 'B');
  await page.evaluate(`fixture.finish('files', 'B', null, true)`);
  check('failed file refresh clears old rows and shows its error', await page.until(`${panel}.includes('FIXTURE read failed') && !${panel}.includes('B.json')`));

  // Resolve the abandoned B poll before mounting another poll for the same run.
  await page.evaluate(`fixture.pending.filter(p => !p.done && p.kind === 'status').forEach(p => { p.done = true; p.resolve(null); })`);
  await select('tab', 'status');
  await wait('status', 'B');
  await resolve('status', 'B', status('B'));
  check('status controls use the displayed run', await page.until(`!!${exportButton}`));
  await page.evaluate(`${exportButton}.click()`);
  check('Export status carries displayed run identity', await page.evaluate("fixture.downloads.length === 1 && fixture.downloads[0] === 'B__status.json'"),
    await page.evaluate('JSON.stringify(fixture.downloads)'));
  await select('run', 'A');
  check('old controls disappear while new run loads', await page.until(`!${exportButton}`));
  await wait('status', 'A');
  await page.evaluate(`fixture.finish('status', 'A', null, true)`);
  check('failed new status leaves controls unavailable', await page.until(`${state}.error === 'FIXTURE read failed' && !${exportButton}`));
  await select('tab', 'logs'); await wait('events', 'A');
  await page.evaluate(`fixture.finish('events', 'A', null, true)`);
  check('failed log read is visible for a resting run', await page.until(`${panel}.includes('FIXTURE read failed') && ${panel}.includes('Retry read')`));
  await page.evaluate(`[...document.querySelectorAll('#panel button')].find(b => b.textContent === 'Retry read').click()`);
  await wait('events', 'A');
  await resolve('events', 'A', { kind: 'events', entries: [{ event: 'FIXTURE recovered log' }] });
  check('log retry recovers without changing the run', await page.until(`${panel}.includes('FIXTURE recovered log') && !${panel}.includes('FIXTURE read failed')`));
  check('no browser exceptions', page.consoleErrors.length === 0, JSON.stringify(page.consoleErrors));
} catch (error) { fail(error); } finally { await browser.close(); }
finish();
