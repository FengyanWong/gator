// Browser check of launch recovery (review of 2026-10-07, record 7.268): the header's run whose first status read gets no
// proper answer, and a launch whose answer was lost. Hermetic: every /api/runs/* request and every validation is answered
// HERE by a FIXTURE run; other GET requests pass through and every other writing request is refused. Runs against a Vite
// preview of the build (run_checks.sh) or the live page.
//   1. The run this browser remembers answers its first two status reads with a 500 (the backend restarting, a read on the
//      mounted drive failing): the main button stays "Start" DISABLED ("Looking up the run...") and the read is repeated;
//      when the status arrives, live, the button reads "Pause". Before 7.268 the first error counted as "checked": "Start"
//      was offered on a live run, and the run was never read again.
//   2. A launch kept in this tab (the page was reloaded during it) whose question gets no answer twice (connection refused,
//      then a 500): the id stays kept, the question is asked again, and the run it made is taken ("Pause", "sent before the
//      page was reloaded made this run; it was not sent again"); no second start. Before 7.268 the first failure dropped
//      the id, and the run was forgotten.
//   3. A Start whose answer is a 500 after the run was made (the backend's record write failed): the page keeps the id, asks
//      what became of it and takes the run ("sent a moment ago, whose answer did not arrive, made this run"); exactly one
//      POST /api/runs/start. Before 7.268 any error answer forgot the id, and "Start" was offered again.
// Exit code 1 if any check fails.
import { check, launchEdge, outDir, reportRefused, RUN_KEY, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl, LAUNCH_KEY, SHOWN_RUN_KEY } from './lib/harness.mjs';

const APP = await workbenchUrl();
outDir();
const browser = await launchEdge('launch-recovery');

const DIR = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed0__0001';
// A second, PAUSED run for the bottom tabs: with the header's run shown there as well, the page's own poll would feed the
// header, and the header's own read (what scenario 1 checks) would never run.
const OTHER = '/fixture/outputs/mock/fixture_experiment__0001/runs/fixture_task__scratch__seed1__0002';
const otherStatus = () => ({ ...statusOf(), run_dir: OTHER, run_id: 'fixture-run-2', state: 'paused', worker_alive: false, stop_reason: 'user_pause',
  budget: { ...statusOf().budget, in_flight: 0 } });
let beat = 0;
const statusOf = () => ({ state: 'running', run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: 'mock', mock: true, worker_alive: true, run_dir: DIR,
  heartbeat_utc: new Date(Date.UTC(2026, 9, 7, 0, 0, 0) + 1000 * ++beat).toISOString(), stop_reason: null, error: null, active_workers: [], concurrency: 1,
  learner_updates: 0, first_feasible: null,
  budget: { max_evaluations: 60, max_launches: null, max_retries: 0, charged: 3, reserved: 0, in_flight: 1, completed: 3, failed: 0, released: 0, remaining: 57,
    launches: 3, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: DIR }, connection: { overall: 'not_applicable' }, summary: null, calibration: null,
  manifest: { mode: 'scratch', mock: true, task_id: 'fixture_task:0000', seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: 60 },
    mock_notice: 'FIXTURE MOCK DATA: nothing was started.' } });
const started = () => ({ run_dir: DIR, run_id: 'fixture-run', mock: true, worker_pid: 1, paths: { run_dir: DIR }, connection_gate: { status: 'not_applicable' },
  mock_notice: 'FIXTURE MOCK DATA: nothing was started.' });
const validReport = validConfiguration({ mock: true });

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);
  const page = await browser.open();
  const { send, evaluate, until, fulfil, consoleErrors } = page;
  const refused = []; const starts = []; const lookups = []; const dialogs = [];
  let dirReads = 0, statusFailures = 0, lookupFailures = 0, lookupAnswer = { state: 'unknown' }, startFailures = 0;
  const failed = requestId => fulfil(requestId, 500, { detail: { message: 'FIXTURE: PersistenceError: the drive did not take the record' } });
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, validReport);
    if (name === '/api/runs/status') {
      const asked = url.searchParams.get('run_dir');
      if (asked === OTHER) return fulfil(requestId, 200, otherStatus());
      if (asked !== DIR) return fulfil(requestId, 404, { detail: 'Not a run directory' });
      dirReads++;
      return statusFailures-- > 0 ? failed(requestId) : fulfil(requestId, 200, statusOf());
    }
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: [] });                         // nothing to take over: the launcher's own path is what is checked
    if (name === '/api/runs/request') {
      lookups.push(url.searchParams.get('request_id'));
      if (lookupFailures-- > 0) return lookupFailures % 2 ? send('Fetch.failRequest', { requestId, errorReason: 'ConnectionRefused' }) : failed(requestId);
      return fulfil(requestId, 200, lookupAnswer);
    }
    if (name === '/api/runs/continuation') return fulfil(requestId, 200, { run_dir: url.searchParams.get('run_dir'), eligible: false, code: 'running', reason: 'FIXTURE: running', state: 'running' });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/download') return fulfil(requestId, 200, { output: {} });
    if (name === '/api/runs/start') { starts.push(body); return startFailures-- > 0 ? failed(requestId) : fulfil(requestId, 200, started()); }
    return page.readOrRefuse({ requestId, request }, refused);
  };
  page.on('Page.javascriptDialogOpening', p => {                      // no question is planned here: an unplanned one is refused and reported
    dialogs.push({ type: p.type, message: p.message });
    return send('Page.handleJavaScriptDialog', { accept: false, promptText: '' });
  });
  const MAIN = `document.querySelector('header button.run-main')`;
  const look = () => evaluate(`({ main: ${MAIN}?.textContent, mainOff: ${MAIN}?.disabled, title: ${MAIN}?.title, banner: document.querySelector('.banner')?.textContent ?? null,
    refusal: document.querySelector('header .launch-refusal')?.textContent ?? null, remembered: localStorage.getItem(${JSON.stringify(RUN_KEY)}), kept: sessionStorage.getItem(${JSON.stringify(LAUNCH_KEY)}) })`);
  const mainReads = (label, tries) => until(`${MAIN}?.textContent === ${JSON.stringify(label)}`, tries);
  const seen = () => evaluate(`window.__seen ?? []`);                 // every [label, disabled] the main button has shown on this page
  const bannerSays = (pattern, tries = 60) => until(`${pattern}.test(document.querySelector('.banner')?.textContent ?? '')`, tries);
  const waitFor = async (test, tries = 50) => { for (let i = 0; i < tries && !test(); i++) await sleep(100); return test(); };
  const scripts = [];
  const open = async ({ remembered = null, shown = null, kept = null } = {}) => {   // a fresh page: the runs this browser remembers (header, bottom tabs), the launch this tab keeps
    for (const identifier of scripts.splice(0)) await send('Page.removeScriptToEvaluateOnNewDocument', { identifier });
    await send('Page.navigate', { url: 'about:blank' });
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `if (location.protocol.startsWith('http')) {
      localStorage.setItem('gator-workbench-config-v1', ${JSON.stringify(JSON.stringify(CONFIG))});
      ${remembered ? `localStorage.setItem(${JSON.stringify(RUN_KEY)}, ${JSON.stringify(remembered)})` : `localStorage.removeItem(${JSON.stringify(RUN_KEY)})`};
      ${shown ? `localStorage.setItem(${JSON.stringify(SHOWN_RUN_KEY)}, ${JSON.stringify(JSON.stringify({ run: shown, header: remembered }))})` : `localStorage.removeItem(${JSON.stringify(SHOWN_RUN_KEY)})`};
      if (!sessionStorage.getItem('fixture-seeded')) { sessionStorage.setItem('fixture-seeded', '1');
        ${kept ? `sessionStorage.setItem(${JSON.stringify(LAUNCH_KEY)}, ${JSON.stringify(JSON.stringify(kept))})` : `sessionStorage.removeItem(${JSON.stringify(LAUNCH_KEY)})`}; }
      window.__seen = [];
      new MutationObserver(() => { const b = document.querySelector('header button.run-main'); if (!b) return; const now = [b.textContent, b.disabled];
        const last = window.__seen[window.__seen.length - 1]; if (!last || last[0] !== now[0] || last[1] !== now[1]) window.__seen.push(now); })
        .observe(document, { subtree: true, childList: true, characterData: true, attributes: true }); }` }).then(r => scripts.push(r.identifier));
    await send('Page.navigate', { url: APP });
    if (!(await until(`!!(${MAIN})`, 150))) throw new Error('the run buttons never appeared; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  };
  await page.intercept(['*/api/*'], answer);

  // ---- 1. the remembered run's first status reads get a 500: "checking" stays, the read is repeated, then "Pause" ----------
  statusFailures = 2;
  await open({ remembered: DIR, shown: OTHER });
  await sleep(1500);
  let v = await look();
  check('after a failed first status read the main button is "Start" but DISABLED (the run is not known to be at rest)', v.main === 'Start' && v.mainOff === true, JSON.stringify(v));
  check('... with "Looking up the run" as its tooltip', /Looking up the run/.test(v.title ?? ''), v.title ?? '');
  check('... the read is repeated and answered, and the live run shows as "Pause"', await mainReads('Pause', 120) && dirReads >= 3, `${dirReads} status reads of the header's run`);
  const shown = await seen();
  check('... and an enabled "Start" was never shown on the way', !shown.some(([label, off]) => label === 'Start' && off === false), JSON.stringify(shown));
  check('... the run stays remembered', (await look()).remembered === DIR);

  // ---- 2. a launch kept across a reload whose question fails twice: the id stays kept, asked again, its run taken ----------
  await evaluate(`sessionStorage.clear()`);
  lookupFailures = 2; lookupAnswer = { state: 'done', answer: started() }; lookups.length = 0; starts.length = 0;
  const kept = { id: 'kept-0000-0001', action: 'start', run_dir: null, at: Date.now() };
  await open({ remembered: null, kept });
  check('the page asks what became of the kept launch, by its id', await waitFor(() => lookups.length >= 1, 60), JSON.stringify(lookups));
  await sleep(600);
  v = await look();
  check('... while the question gets no answer the id stays kept and the header reads "Starting..."', v.kept !== null && v.main === 'Starting...', JSON.stringify(v));
  check('... the question is asked again (connection refused, then a 500, then answered)', await waitFor(() => lookups.length >= 3, 120), `${lookups.length} lookups`);
  check('... every time by the same id', lookups.every(id => id === kept.id), JSON.stringify(lookups));
  check('... and the run it made is taken into the header ("Pause")', await mainReads('Pause', 150), JSON.stringify(await look()));
  check('... said as not sent again', await bannerSays('/sent before the page was reloaded made this run; it was not sent again/'), (await look()).banner ?? '');
  check('... no second start was sent, and no request is kept any more', starts.length === 0 && (await look()).kept === null, `${starts.length} start(s)`);

  // ---- 3. a Start answered with a 500 after the run was made: the id is kept, asked about, and the run taken ------------------
  await evaluate(`sessionStorage.clear()`);
  startFailures = 1; lookupFailures = 0; lookupAnswer = { state: 'done', answer: started() }; lookups.length = 0; starts.length = 0;
  await open({ remembered: null, kept: null });
  await sleep(1500);
  v = await look();
  check('a fresh page offers "Start"', v.main === 'Start' && v.mainOff === false, JSON.stringify(v));
  await evaluate(`${MAIN}.click()`);
  check('Start was sent once, with a request id', await waitFor(() => starts.length === 1, 60) && typeof starts[0]?.request_id === 'string', JSON.stringify(starts));
  check('... its 500 makes the page ask what became of it, by that id', await waitFor(() => lookups.includes(starts[0]?.request_id), 60), JSON.stringify(lookups));
  check('... and the run it made is taken into the header ("Pause"), with no second start', await mainReads('Pause', 150) && starts.length === 1, JSON.stringify(await look()));
  check('... said as not sent again', await bannerSays('/sent a moment ago, whose answer did not arrive, made this run; it was not sent again/'), (await look()).banner ?? '');
  v = await look();
  check('... the error line is gone and no request is kept any more', v.refusal === null && v.kept === null, JSON.stringify(v));

  reportRefused(refused);
  check('no question was asked on screen', dialogs.length === 0, JSON.stringify(dialogs));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 400));
});
