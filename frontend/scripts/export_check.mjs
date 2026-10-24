// Browser check of the EXPORTS of the four run tabs (Run status, Logs, Data tables, Output files): every export button
// pressed in a real (headless) browser against a real backend, and the files the browser SAVED read back from its
// download folder (there is no frontend test runner in this project). Nothing is intercepted: names and contents are
// what the real backend sends. Same approach as run_control_live_check.mjs: headless Edge over the DevTools protocol.
// What it pins (user request 2026-09-21, "close all five gaps"):
//   1 Logs: "Download full log" saves the whole events.jsonl; a log with nothing in it says so and the page stays
//   2 Run status: "Export status (JSON)" saves what the tab shows, named after the run
//   3 Data tables: "Export detailed CSV" downloads the CSV at once (whole table), and keeps the copy in the run folder
//   4 Data tables: "Export research CSVs" downloads the experiment's aggregates as one zip (they lie above the run folder)
//   5 Output files: the data-only package is named after ITS run, not "run__data.zip" for every run
// and, since branch record SIF-105, that Logs and Data tables keep their choices (the errors log; the table and its order)
// while another tab is looked at; since branch record SIF-137, that the ended run's steering check speaks of its end.
// It starts one small run on the synthetic MOCK task (free, no bridge, no Virtuoso) and writes exports, so it REFUSES
// the default backend: give it a SCRATCH backend and a scratch output root, e.g.
//   S=<empty scratch dir>; mkdir -p $S/settings $S/out
//   GATOR_WORKBENCH_SETTINGS_DIR=$S/settings PYTHONPATH=src ~/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8769 --allow-root $S/out &
//   WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT GATOR_WORKBENCH_URL=http://127.0.0.1:8769/ GATOR_SCRATCH_OUT=$S/out \
//     "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/export_check.mjs)" [screenshot-dir]
// (WSLENV carries the two variables into the Windows process.) Takes about 60 s. Exit code 1 if any check fails.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl({ writes: true }), OUT_ROOT = process.env.GATOR_SCRATCH_OUT;
if (!OUT_ROOT) {
  console.log('ERROR this check starts a real (MOCK) run and writes exports: set GATOR_SCRATCH_OUT to the allowed output root of the scratch backend (and WSLENV=GATOR_WORKBENCH_URL:GATOR_SCRATCH_OUT).');
  process.exit(1);
}
const out = outDir();
const browser = await launchEdge('export');
const saved = browser.tempDir('saved');                                                // the browser's download folder
const get = async (route, params) => (await fetch(new URL(`api/${route}?` + new URLSearchParams(params), APP))).json();
const post = async (route, body) => (await fetch(new URL(`api/${route}`, APP), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
// File names of a zip, from its central directory (node has no zip reader; signature PK\1\2, name length at +28, name at +46).
const zipNames = buffer => { const names = []; for (let i = buffer.indexOf('PK\u0001\u0002', 0, 'latin1'); i >= 0; i = buffer.indexOf('PK\u0001\u0002', i + 46, 'latin1')) names.push(buffer.toString('utf8', i + 46, i + 46 + buffer.readUInt16LE(i + 28))); return names; };
// A finished download: the named file is there and Edge's temporary ".crdownload" twin is gone.
const savedFile = async name => { for (let i = 0; i < 100; i++) { const names = readdirSync(saved); if (names.includes(name) && !names.some(n => n.endsWith('.crdownload'))) return readFileSync(path.join(saved, name)); await sleep(100); } return null; };

await runChecks(browser, async () => {
  // ---- one small finished MOCK run to export from -------------------------------------------------------------------------------
  const starter = await get('tasks/starter', { task_key: 'synthetic:gpdk045_ota5' });
  const CONFIG = { ...starter, run: { ...starter.run, max_evaluations: 12, concurrency: 1 }, output: { experiment_name: 'export_check', output_root: OUT_ROOT }, research: {} };
  const started = await post('runs/start', { config: CONFIG });
  if (!started.run_dir) throw new Error('the MOCK run did not start: ' + JSON.stringify(started).slice(0, 400));
  const DIR = started.run_dir, RUN = DIR.split('/').pop(), EXPERIMENT = DIR.split('/').slice(-4)[0];
  let status;
  for (let i = 0; i < 600; i++) { status = await get('runs/status', { run_dir: DIR }); if (status.state === 'completed' && !status.worker_alive) break; await sleep(300); }
  if (status.state !== 'completed') throw new Error('the MOCK run did not complete: ' + status.state);
  console.log(`INFO  MOCK run ${RUN} of experiment ${EXPERIMENT}: ${status.budget.charged} evaluations`);

  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, until, consoleErrors } = page;
  const dialogs = [];
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.message); return send('Page.handleJavaScriptDialog', { accept: true }); });
  const button = text => `[...document.querySelectorAll('footer .bottom-body button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const press = text => evaluate(`${button(text)}.click()`, true);                                       // a real click: downloads need the user's gesture
  const tab = async text => { await evaluate(`[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`); return until(`!!(${button(text === 'Run status' ? 'Export status (JSON)' : 'Refresh')}) || ${JSON.stringify(text)} === 'Logs'`, 60); };
  // The Training tab stays mounted (hidden) in the same container, so everything is found from the visible tab's own button.
  const HINT = text => `(${button(text)}?.closest('.row').querySelector('.hint')?.textContent ?? '')`;
  let row = 'Export status (JSON)';                                                                        // the button whose row the note is read from
  const hint = () => evaluate(HINT(row));
  const shot = name => page.shot(path.join(out, name), `document.querySelector('footer')`);

  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: saved });
  await page.seed({ config: CONFIG, run: DIR, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!document.querySelector('footer .tabs')`, 150))) throw new Error('the workbench never appeared; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));

  // ---- 2 Run status: what the tab shows, as one JSON file named after the run --------------------------------------------------------------
  await tab('Run status');
  if (!(await until(`!!(${button('Export status (JSON)')})`, 60))) throw new Error('this page has no "Export status (JSON)" button: the served frontend is older than it (npm run build, then reload)');
  // Branch record SIF-89: the row stands under the run at a glance, above the facts it used to follow.
  check('Run status has "Export status (JSON)" at the end of its button row, after Continue... (7.261), the row right under the run at a glance (SIF-89)', await evaluate(`(() => { const b = ${button('Export status (JSON)')};
    const row = b.parentElement, table = document.querySelector('.status-grid > table');
    return !b.nextElementSibling && [...row.children].some(c => c.textContent === 'Continue...') && row.parentElement.classList.contains('status-grid')
      && row.previousElementSibling?.matches('.status-hero, p.status-error') && !!table && !!(row.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING); })()`));
  await press('Export status (JSON)');
  let file = await savedFile(`${RUN}__status.json`);
  const exported = file && JSON.parse(file.toString('utf8'));
  check('it saves <run folder>__status.json', !!file, readdirSync(saved).join(', '));
  check('... holding the state, budget, manifest and summary the tab shows, and when it was exported', exported?.state === 'completed' && exported.run_dir === DIR && exported.budget?.charged === status.budget.charged
    && !!exported.manifest && !!exported.summary && /^20\d\d-/.test(exported.exported_utc ?? ''), JSON.stringify(Object.keys(exported ?? {})).slice(0, 200));
  // Branch record SIF-54, on a real MOCK run's status: what was saved in words, the store's counters in the tooltip (it read
  // "Persistence: commit 14, flushed 14, 9.5 KiB table data; last save ..."); the reward by name (it began with a bare
  // "compressed"); "Tightest margin" (it read "Tightest clearance"); "none", not "none yet", once the run has ended.
  const facts = await evaluate(`Object.fromEntries([...document.querySelectorAll('.status-grid > table tr')].map(tr => [tr.cells[0].textContent, { text: tr.cells[1]?.textContent, title: tr.cells[1]?.title }]))`);
  check('Run status: "Saved to disk: last save <local time> · <size> of table data", the counters in its tooltip', !facts.Persistence
    && /^last save \d{4}-\d\d-\d\d \d\d:\d\d:\d\d · [\d.]+ (B|KiB|MiB) of table data$/.test(facts['Saved to disk']?.text ?? '') && /^last save \S+ \(UTC\); commit \d+, flushed \d+$/.test(facts['Saved to disk']?.title ?? ''),
    JSON.stringify(facts['Saved to disk']));
  check('... "Executed reward" names the reward, then its settings as the reward block names them', status.summary?.reward?.version !== 'constraint_violation_v2'
    || /^Constraint violation, version 2; violation shape \w+; worst hard-spec share [\d.]+; objective bonus weight [\d.]+; tightest-margin bonus weight [\d.]+$/.test(facts['Executed reward']?.text ?? ''),
    facts['Executed reward']?.text);
  check('... "Tightest margin" beside a best design, never "Tightest clearance"', !!facts['Tightest margin'] === !!status.best_design && !facts['Tightest clearance'], Object.keys(facts).join(', '));
  // ...the evaluations USED by then, as the facts row says it, one as one (branch record SIF-116: "at 4 evaluations")
  const firstFeasible = await evaluate(`[...document.querySelectorAll('.status-grid .key-tile')].find(t => t.querySelector('.key-tile-label')?.textContent === 'First feasible design')?.querySelector('.key-tile-value')?.textContent`);
  const firstUsed = status.first_feasible?.first_feasible_eval_count;
  check('... the ended run\'s "First feasible design" reads "at <n> evaluations used" or "none", never "none yet"', firstFeasible
    === (status.first_feasible ? `at ${firstUsed} ${firstUsed === 1 ? 'evaluation' : 'evaluations'} used` : 'none'), `${firstFeasible} | ${JSON.stringify(status.first_feasible ?? null)}`);
  // Branch record SIF-76: the budget "used", as the Continue... form and the Abort question count it (it read "charged" here
  // alone), what counts in the tooltip; the best design's reward in its tile, and its hard violation only while it misses
  // (a feasible one read "feasible hard violation 0", always 0, and no reward).
  const hero = await evaluate(`(() => { const h = document.querySelector('.status-grid .status-hero-count > .hint'); return h ? { text: h.textContent, title: h.title } : null; })()`);
  check('... the budget in words: "evaluations used · 0 in flight · 0 failed", what counts on hover; the Budget row "N used / N" (SIF-76)',
    hero?.text === `evaluations used · ${status.budget.in_flight} in flight · ${status.budget.failed} failed` && /^A design counts against the budget once it is sent to the simulator/.test(hero.title)
    && new RegExp(`^${status.budget.charged} used / ${status.budget.max_evaluations} `).test(facts.Budget?.text ?? ''), `${JSON.stringify(hero)} | ${facts.Budget?.text}`);
  const bestTile = await evaluate(`[...document.querySelectorAll('.status-grid .key-tile')].find(t => t.querySelector('.key-tile-label')?.textContent === 'Best design')?.querySelector('.key-tile-value')?.textContent ?? null`);
  const best = status.best_design;
  check('... the "Best design" tile gives its reward, and the hard violation only while it misses (SIF-76)', !best ? bestTile === 'none'
    : (best.reward == null || / reward -?\d/.test(bestTile ?? '')) && /hard violation/.test(bestTile ?? '') === !best.feasible, `${bestTile} | feasible ${best?.feasible}, reward ${best?.reward}`);
  // Branch record SIF-98, on the same real MOCK run: the ended run's working time under the bar, apart from the budget's words
  // above it (no "so far", no time left: it stood in the run brief alone), and the best design's variables, as the Runs
  // window's Details list them, in their order.
  const heroTime = await evaluate(`document.querySelector('.status-grid .status-hero-count > .status-hero-time')?.textContent ?? null`);
  check('... under the bar the ended run\'s working time, "Duration <time>", with no "so far" and no time left (SIF-98)', status.active_seconds == null ? heroTime === null
    : /^Duration (\d+ s|\d+ min \d\d s|\d+ h \d\d min)$/.test(heroTime ?? ''), `${heroTime} | active_seconds ${status.active_seconds}`);
  const ids = Array.isArray(best?.variables) ? best.variables.map(v => v.variable_id) : Object.keys(best?.variables ?? {});
  const literal = text => String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  check('... "Best design variables" names each variable of the best design in its order, "<id> = <value>", "Click to copy" (SIF-98)', !ids.length ? !facts['Best design variables']
    : new RegExp(`^${ids.map(id => `${literal(id)} = [^;]+`).join('; ')}$`).test(facts['Best design variables']?.text ?? '') && facts['Best design variables'].title === 'Click to copy',
    `${facts['Best design variables']?.text} | ${ids.join(', ')}`);
  // Branch record SIF-137, on the same real MOCK run: the ended run's steering check speaks of its end - its last exploration
  // bonus, or "no update was made", never "no update yet" - and the backend's verdict, as it is, follows "At its end: " in grey
  // with what gives the next run room to learn (it stood in present-tense orange, nothing to act on). Review of SIF-137: no
  // bonus is "no update was made" only when the engine counted none, else "none recorded" (the updates are not in the tables).
  const steer = await evaluate(`(() => { const s = document.querySelector('.status-grid .steering-check'); return s && { text: s.textContent,
    verdict: s.querySelector('.steering-verdict')?.textContent ?? null, grey: !!s.querySelector('p.hint.steering-verdict'), orange: !!s.querySelector('.warn') }; })()`);
  const sv = status.steering ?? null;
  console.log(`INFO  steering check of the MOCK run: ${JSON.stringify(sv)}, learner updates ${status.learner_updates}`);
  const noBonus = status.learner_updates > 0 ? 'none recorded' : 'no update was made';
  check('... the ended run\'s steering check: "exploration bonus (latest update): <n>", "none recorded" or "no update was made", never "yet"; a verdict as "At its end: <the backend\'s words> A larger Evaluation budget, ..." in grey, never orange (SIF-137 and its review)',
    !sv ? steer === null : !!steer && !steer.text.includes('yet') && !steer.orange
      && (sv.reward_spread == null || steer.text.includes(`exploration bonus (latest update): ${sv.exploration_bonus == null ? noBonus : ''}`))
      && (sv.verdict ? steer.grey && steer.verdict === `At its end: ${sv.verdict} A larger Evaluation budget, or the Initial alpha a Calibration proposes, gives the next run room to learn.`
        : steer.verdict === null), `${JSON.stringify(steer)} | ${JSON.stringify(sv)}`);
  await shot('export-1-status.png');

  // ---- 1 Logs: the whole file, not the newest 200 entries --------------------------------------------------------------------------------------
  await tab('Logs'); row = 'Download full log (events.jsonl)';
  check('Logs has "Download full log (events.jsonl)" next to the list', await until(`!!(${button('Download full log (events.jsonl)')})`, 60));
  check('... and says that the list is only the newest entries', /newest 200 entries/.test(await hint()), await hint());
  await press('Download full log (events.jsonl)');
  file = await savedFile('events.jsonl');
  const lines = file ? file.toString('utf8').split('\n').filter(Boolean) : [];
  const listed = (await get('runs/logs', { run_dir: DIR, kind: 'events', limit: 1000 })).entries;
  check('it saves events.jsonl with every record of the run, one JSON object per line', lines.length > 0 && lines.length === listed.length && lines.every(l => { try { return !!JSON.parse(l).event; } catch { return false; } }), `${lines.length} lines, ${listed.length} entries`);
  check('... and says so', await until(`${HINT(row)} === 'Downloaded events.jsonl.'`, 40), await hint());
  await evaluate('performance.clearResourceTimings()');      // so that the page's read of the errors log below is found
  await page.setValue(`[...document.querySelectorAll('footer .bottom-body select')].find(e => [...e.options].some(o => o.value === 'errors'))`, 'errors');
  row = 'Download full log (errors.jsonl)';
  check('choosing "errors" renames the button and clears the note', await until(`!!(${button(row)})`, 40) && /newest 200 entries/.test(await hint()), await hint());
  const hasErrors = (await get('runs/logs', { run_dir: DIR, kind: 'errors' })).entries.length > 0;      // a healthy run keeps an EMPTY errors.jsonl
  // The list has no rows while the errors log is still being read AND once it is read and empty, and the page skips an
  // empty download only once its answer is in: wait for the page's own read to finish, then one render (it raced, 2026-09-30).
  await until(`performance.getEntriesByType('resource').some(e => e.name.includes('/api/runs/logs') && e.name.includes('kind=errors'))`, 80);
  await until(`document.querySelectorAll('footer .bottom-body .scroll.log > div').length === 0`, 40);      // the list now shows the errors log
  await sleep(150);
  await press('Download full log (errors.jsonl)');
  if (hasErrors) check('the errors log is saved too', !!(await savedFile('errors.jsonl')));
  else {
    check('a log with nothing in it is said in plain words, not saved as an empty file', await until(`${HINT(row)} === 'Nothing to download: this run has logged no errors so far.'`, 40), await hint());
    check('... the page stays the workbench, and nothing is saved', await evaluate(`location.pathname === '/' && !!document.querySelector('header')`) && !existsSync(path.join(saved, 'errors.jsonl')));
  }
  await shot('export-2-logs.png');

  // ---- 3 + 4 Data tables: the CSV comes to the browser; so do the research CSVs, as one zip ------------------------------------------------------
  await tab('Data tables'); row = 'Refresh';
  check('Data tables shows the run\'s evaluations', await until(`/^${status.budget.charged} rows/.test${HINT(row)}`, 80), await hint());
  // In words, the store's commit in the tooltip (branch record SIF-54: "12 rows (snapshot at commit 14); last 12 shown."); the
  // newest row first, as Logs lists its lines (branch record SIF-76: "the last 25 shown", oldest first, the newest below the fold).
  const shownRows = status.budget.charged > 25 ? `; the newest 25 shown` : '';
  check('... "N rows, newest first." ("; the newest 25 shown" when there are more), with "Snapshot at commit N" in its tooltip', new RegExp(`^${status.budget.charged} rows${shownRows}, newest first\\.`).test(await hint())
    && /^Snapshot at commit \d+$/.test(await evaluate(`${button(row)}?.closest('.row').querySelector('.hint')?.title ?? ''`)), await hint());
  // Branch record SIF-76: a time in this computer's time, as Logs and Output files write it, its UTC value on hover (it read
  // "2026-10-16T17:17:20.704501+", cut at the panel's edge); the newest row on top.
  const cells = await evaluate(`(() => { const t = document.querySelector('footer table.data-table'); if (!t) return null;
    const heads = [...t.tHead.rows[0].cells].map(th => th.textContent), at = heads.indexOf('proposed_at'), seq = heads.indexOf('commit_seq'), rows = [...t.tBodies[0].rows];
    const local = s => { const d = new Date(s), two = n => String(n).padStart(2, '0');
      return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds()); };
    const cell = at >= 0 ? rows[0]?.cells[at] : null, utc = /^(.*) \\(UTC\\)$/.exec(cell?.title ?? '')?.[1] ?? null;
    return { text: cell?.textContent ?? null, title: cell?.title ?? null, local: utc && local(utc), seqs: seq >= 0 ? rows.map(r => Number(r.cells[seq].textContent)) : null }; })()`);
  check('... a time reads this computer\'s "YYYY-MM-DD hh:mm:ss", its UTC value on hover (SIF-76)', !!cells?.text && /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(cells.text) && cells.text === cells.local
    && /^20\d\d-\d\d-\d\dT[\d:.]+(\+00:00|Z) \(UTC\)$/.test(cells.title), JSON.stringify(cells));
  check('... the newest row on top (SIF-76)', !!cells?.seqs && cells.seqs.length > 1 && cells.seqs.every((v, i) => i === 0 || v < cells.seqs[i - 1]), JSON.stringify(cells?.seqs));
  // Branch record SIF-99, on the real backend: the count line says when the table was read; "oldest first" asks for the
  // table's first rows (tail=false: it always showed the newest 25) and lists them in the order they were written.
  check('... then when it was read: "Read at hh:mm:ss." (SIF-99)', new RegExp(`^${status.budget.charged} rows${shownRows}, newest first\\. Read at \\d\\d:\\d\\d:\\d\\d\\.`).test(await hint()), await hint());
  const SEQS = `(t => { const seq = [...t.tHead.rows[0].cells].map(th => th.textContent).indexOf('commit_seq'); return [...t.tBodies[0].rows].map(r => Number(r.cells[seq].textContent)); })(document.querySelector('footer table.data-table'))`;
  await page.setValue(`document.querySelector('footer select.table-order')`, 'oldest');
  const oldest = new RegExp(`^${status.budget.charged} rows${shownRows.replace('newest', 'oldest')}, oldest first\\. Read at `);
  check('"oldest first" lists the table\'s first rows, the oldest on top, and says so (SIF-99)', await until(`${oldest}.test${HINT(row)} && (s => s.length > 1 && s.every((v, i) => i === 0 || v > s[i - 1]))(${SEQS})`, 80),
    `${await hint()} | ${JSON.stringify(await evaluate(`document.querySelector('footer table.data-table') && ${SEQS}`))}`);
  await page.setValue(`document.querySelector('footer select.table-order')`, 'newest');
  await until(`/, newest first\\. Read at /.test${HINT(row)}`, 80);
  await press('Export detailed CSV');
  check('"Export detailed CSV" says what was downloaded and where the copy is kept', await until(`/Downloaded evaluations__seq\\d+\\.csv\\. Also kept in the run folder: exports\\/evaluations__seq\\d+\\.csv/.test${HINT(row)}`, 100), await hint());
  const csvName = /Downloaded (evaluations__seq\d+\.csv)/.exec(await hint())?.[1] ?? 'missing';
  file = await savedFile(csvName);
  const rows = file ? file.toString('utf8').trimEnd().split('\n') : [];
  check('the browser saved the WHOLE table (header + every row, not only the rows shown)', rows.length === status.budget.charged + 1 && rows[0].split(',').includes('evaluation_id'), `${rows.length} lines; header ${rows[0]?.slice(0, 80)}`);
  check('... and the copy is in the run folder as well', (await get('runs/files', { run_dir: DIR })).files.some(f => f.path === `exports/${csvName}`));
  await press('Export research CSVs');
  check('"Export research CSVs" says what was downloaded and where the copies are kept', await until(`${HINT(row)}.includes('Downloaded ${EXPERIMENT}__aggregates.zip (6 tables). Also kept in ')`, 150), await hint());
  file = await savedFile(`${EXPERIMENT}__aggregates.zip`);
  const research = file ? zipNames(file).sort() : [];
  check('the browser saved <experiment>__aggregates.zip with the six tables and their descriptions', research.length === 12
    && ['run_summary', 'budget_success', 'budget_success_grouped', 'paired_runs', 'transfer_summary', 'cumulative_cost'].every(t => research.includes(`${t}.csv`) && research.includes(`${t}.meta.json`)), research.join(', '));
  await shot('export-3-data.png');
  // Branch record SIF-105: each tab keeps its choice while another is looked at. Both were drawn anew at each return, Logs on
  // events and Data tables on the newest 25 evaluations.
  const CHOSEN = `[...document.querySelectorAll(['tab-choice', 'table-limit', 'table-order'].map(c => 'footer .bottom-body select.' + c).join(', '))].map(s => s.value)`;
  await page.setValue(`document.querySelector('footer select.tab-choice')`, 'parameters');
  await page.setValue(`document.querySelector('footer select.table-order')`, 'oldest');
  await tab('Logs');
  check('back in Logs, the errors log is still the one shown (SIF-105)', await until(`JSON.stringify(${CHOSEN}) === '["errors"]' && !!(${button('Download full log (errors.jsonl)')})`, 40),
    JSON.stringify(await evaluate(CHOSEN)));
  await tab('Data tables');
  check('...and back in Data tables, its parameters table, 25 rows, oldest first (SIF-105)', await until(`JSON.stringify(${CHOSEN}) === '["parameters","25","oldest"]'
    && !!document.querySelector('footer table.data-table') && / oldest first\\. Read at /.test(${HINT(row)})`, 80), `${JSON.stringify(await evaluate(CHOSEN))} | ${await hint()}`);

  // ---- 5 Output files: the package is named after its run ---------------------------------------------------------------------------------------------
  await tab('Output files'); row = 'Refresh';
  check('Output files lists the exported CSV, downloadable like every other file', await until(`[...document.querySelectorAll('footer .bottom-body td')].some(td => td.textContent === 'exports/${csvName}')`, 80));
  await press('Download data-only package (.zip)');
  file = await savedFile(`${RUN}__data.zip`);
  const packed = file ? zipNames(file) : [];
  check('the data-only package is saved as <run folder>__data.zip, not as run__data.zip', !!file && !existsSync(path.join(saved, 'run__data.zip')), readdirSync(saved).join(', '));
  check('... with the run\'s data and without models or work files', packed.includes('run_summary.json') && packed.includes('logs/events.jsonl') && packed.some(n => n.endsWith('.parquet'))
    && !packed.some(n => /^(work|control|waveforms|checkpoints)\//.test(n)), `${packed.length} members`);
  check('... and the tab says so', await until(`${HINT(row)}.includes('Downloaded ${RUN}__data.zip.')`, 60), await hint());
  await shot('export-4-files.png');

  console.log(`INFO  saved by the browser: ${readdirSync(saved).join(', ')}`);
  check('no dialog was needed', dialogs.length === 0, dialogs.join(' | ').slice(0, 200));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});                                                                            // Edge closes at the end, and the download folder goes with it
