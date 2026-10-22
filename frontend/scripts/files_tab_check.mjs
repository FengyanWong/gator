// Browser check of the "Output files" tab's per-file download. User request 2026-09-26: "change the downloads on the
// right to buttons with icons" - each row ends with an icon button (the download arrow, hourglass while the file is on
// its way) instead of a "download" text link; the file is saved like the package and the logs (the browser's own
// download, named by the backend) and the hint says "Downloaded <name>.". Copy run path says "Copied the run path." there,
// or that the browser refused the clipboard, with the path (branch record SIF-94); a copy while the package is packing
// leaves the package button busy (SIF-94 review). Branch record SIF-99: a filter box and column titles that sort; the count
// line says when the folder was read; and both run-data tabs follow a live run - Output files reads the folder again at a
// new save point and when the worker ends, Data tables reads its table again at a flush (the hourglass on Refresh while it
// reads, its rows kept), and nothing is read again at a status update with nothing new; Data tables' rows and order lists
// go into its request (limit, tail).
// Hermetic, on the shared harness: the run's status and file list are canned (FIXTURE), the download request is held
// so the busy state can be seen, then answered with a canned body and Content-Disposition; the browser's download
// folder is a temporary one. GET requests pass, every other writing request is refused. Safe against the live 8765 page.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/files_tab_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { validConfiguration, check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('files');
const saved = browser.tempDir('saved');                                                // the browser's download folder

// ---- canned answers ------------------------------------------------------------------------------------------
const DIR = '/fixture/outputs/mock/fixture__1/runs/fixture-run';
const at = (s = 32) => `2026-09-23T22:45:${String(s).padStart(2, '0')}+00:00`;
const FILES = { files: [
  { path: 'manifest.json', bytes: 15258, modified_utc: at() }, { path: 'design/best_feasible.json', bytes: 5734, modified_utc: at() },
  { path: 'design/best_infeasible.json', bytes: 399, modified_utc: at() }, { path: 'design/parameters.csv', bytes: 542, modified_utc: at() },
  { path: 'design/tracker_state.json', bytes: 2458, modified_utc: at(30) }, { path: 'journal/dispatch.jsonl', bytes: 323, modified_utc: at(25) },
  { path: 'journal/flushes.jsonl', bytes: 828, modified_utc: at() }], total_bytes: 8_598_400 };
const BODY = { manifest: '{"run_id": "fixture-run", "fixture": true}\n', best: '{"design": "FIXTURE best feasible"}\n' };
const RUN_STATUS = { state: 'completed', run_id: 'fixture-run', mode: 'scratch', provenance: 'mock', mock: true, worker_alive: false, run_dir: DIR, active_workers: [], concurrency: 1,
  budget: { max_evaluations: 30, charged: 30, in_flight: 0, completed: 30, failed: 0, remaining: 0, launches: 30, retries: 0, cache_hits: 0 }, best_design: null, first_feasible: null,
  paths: { run_dir: DIR }, connection: { overall: 'not_applicable' }, summary: null, manifest: { mode: 'scratch', mock: true, mock_notice: 'FIXTURE MOCK DATA' } };
// Data tables of the same run (SIF-99): three rows of many; the backend's answer lists them oldest first, from either end.
const DATA = (total, cutoff) => ({ table: 'evaluations', total_rows: total, cutoff_commit_seq: cutoff, columns: ['evaluation_id', 'commit_seq', 'phase'],
  rows: [1, 2, 3].map(n => ({ evaluation_id: `FIXTURE-e${n}`, commit_seq: n, phase: 'random' })) });
const VALID = validConfiguration({ mock: true });
// A finished download: the named file is there and Edge's temporary ".crdownload" twin is gone.
const savedFile = async name => { for (let i = 0; i < 100; i++) { const names = readdirSync(saved); if (names.includes(name) && !names.some(n => n.endsWith('.crdownload'))) return readFileSync(path.join(saved, name), 'utf8'); await sleep(100); } return null; };

await runChecks(browser, async () => {
  const CONFIG = await starterConfig(APP);
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const held = []; const packs = []; let listed = 0;
  let runStatus = RUN_STATUS;                                                      // the run's status as the backend answers it now
  const tables = [], heldTables = []; let holdTable = false, data = DATA(300, 64);   // Data tables' requests (SIF-99)
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/status') return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, runStatus) : fulfil(requestId, 404, { detail: 'Not a run directory' });
    if (name === '/api/runs/table' && url.searchParams.get('run_dir') === DIR) {
      tables.push(Object.fromEntries(url.searchParams));
      return holdTable ? heldTables.push(requestId) : fulfil(requestId, 200, data);
    }
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: [] });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/files') { listed++; return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, FILES) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs/download') { held.push({ requestId, run_dir: url.searchParams.get('run_dir'), path: url.searchParams.get('path') }); return; }   // answered by the check itself
    if (name === '/api/runs/export-package') { packs.push(requestId); return; }                                   // held, then answered by the check
    return page.readOrRefuse({ requestId, request }, refused);
  };
  // The backend's answer: the file's bytes under its own name (support.attachment), or 404 for a file that is gone.
  const release = (body, filename) => { const h = held.shift(); return send('Fetch.fulfillRequest', { requestId: h.requestId, responseCode: 200, body: Buffer.from(body).toString('base64'),
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Content-Length', value: String(Buffer.byteLength(body)) }, { name: 'Content-Disposition', value: `attachment; filename="${filename}"` }] }); };
  const gone = () => { const h = held.shift(); return fulfil(h.requestId, 404, { detail: 'FIXTURE: No such file' }); };
  const heldSoon = async () => { for (let i = 0; i < 50 && !held.length; i++) await sleep(100); return held[0] ?? null; };
  const until = (expression, tries = 80) => page.until(expression, tries);
  // The visible tab's table (the Training tab stays mounted but hidden in the same footer: never "the first table").
  const TABLE = `[...document.querySelectorAll('footer .bottom-body table.grid')].find(t => t.checkVisibility())`;
  const HINT = `((${TABLE})?.closest('.scroll')?.previousElementSibling?.querySelector('.hint')?.textContent ?? '')`;   // parenthesised: `x ?? ''.includes()` would bind the wrong way
  const ROWS = `[...(${TABLE})?.querySelectorAll('tbody tr') ?? []]`;
  const rowOf = file => `${ROWS}.find(r => r.cells[0].textContent === ${JSON.stringify(file)})`;
  const BUTTON = file => `(${rowOf(file)})?.cells[3].querySelector('button')`;
  const describe = file => evaluate(`(() => { const b = ${BUTTON(file)}; if (!b) return null; const svg = b.querySelector('svg.icon');
    return { text: b.textContent, title: b.title, disabled: b.disabled, icon: !!svg, hourglass: svg?.querySelector('path')?.getAttribute('d') === 'M4 2.5h8M4 13.5h8',
      links: (${rowOf(file)}).querySelectorAll('a').length, height: (${rowOf(file)}).getBoundingClientRect().height }; })()`);
  const centre = expression => evaluate(`(() => { const r = (${expression}).getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  const press = async file => { await evaluate(`(${BUTTON(file)}).scrollIntoView({ block: 'center' })`); const c = await centre(BUTTON(file));   // a real click: a download needs the user's gesture
    await page.clickAt(c); };
  const shot = async name => page.shot(path.join(out, name), await evaluate(`(() => { const r = (${TABLE}).closest('.scroll').previousElementSibling.getBoundingClientRect(), t = (${TABLE}).getBoundingClientRect();
    return { x: r.x - 6, y: r.y - 6, width: Math.max(r.width, t.width) + 12, height: t.bottom - r.y + 12, scale: 1.5 }; })()`));

  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: saved });
  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, run: DIR, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!document.querySelector('footer .tabs')`, 150))) throw new Error('the page never showed its bottom tabs: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  const tabs = await evaluate(`[...document.querySelectorAll('footer .tabs > button')].map(b => b.textContent)`);
  if (!tabs.includes('Output files')) throw new Error(`this page has no "Output files" tab (${tabs.join(', ')})`);

  // ---- the list ----------------------------------------------------------------------------------------------------
  await evaluate(`[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent === 'Output files').click()`);
  check('opening "Output files" reads the run folder once and lists every file', (await until(`${ROWS}.length === ${FILES.files.length}`, 80)) && listed === 1, `${listed} read(s), ${await evaluate(`${ROWS}.length`)} row(s)`);
  check('the hint counts the files and their size', /^7 files, 8\.2 MiB\./.test(await evaluate(HINT)), await evaluate(HINT));
  check('... then says when the folder was read, in this computer\'s time: "Read at hh:mm:ss." (SIF-99)', /^7 files, 8\.2 MiB\. Read at \d\d:\d\d:\d\d\./.test(await evaluate(HINT)), await evaluate(HINT));
  const rows = await evaluate(`${ROWS}.map(r => { const b = r.cells[3].querySelector('button'); return { file: r.cells[0].textContent, cells: r.cells.length, links: r.querySelectorAll('a').length,
    button: !!b, icon: !!b?.querySelector('svg.icon'), text: b?.textContent, title: b?.title, disabled: b?.disabled, height: r.getBoundingClientRect().height }; })`);
  check('no row has a "download" text link any more', rows.every(r => r.links === 0), JSON.stringify(rows.filter(r => r.links)));
  check('every row ends with an enabled icon button named "Download <file>"', rows.every(r => r.cells === 4 && r.button && r.icon && !r.disabled && r.text === `Download ${r.file}`), JSON.stringify(rows.map(r => r.text)));
  check('... whose tooltip starts with that name and says where the file goes', rows.every(r => r.title.startsWith(`Download ${r.file}: `) && /download folder/.test(r.title)), rows[0]?.title);
  // Branch record SIF-2: the time a file was modified in this computer's time, as every other time on the page; UTC in its tooltip.
  const times = await evaluate(`({ head: (${TABLE}).querySelector('thead tr').cells[2].textContent, cells: ${ROWS}.map(r => [r.cells[2].textContent, r.cells[2].title]),
    local: (() => { const d = new Date(${JSON.stringify(at())}), two = n => String(n).padStart(2, '0'); return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds()); })() })`);
  check('"Modified" is written in this computer\'s time (YYYY-MM-DD hh:mm:ss), its UTC in the tooltip (SIF-2)', times.head === 'Modified'
    && times.cells.some(([text, title]) => text === times.local && title === at() + ' (UTC)') && times.cells.every(([text]) => /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(text)), JSON.stringify(times).slice(0, 300));
  const sizes = await evaluate(`({ head: getComputedStyle((${TABLE}).querySelector('thead tr').cells[1]).textAlign, cells: ${ROWS}.map(r => getComputedStyle(r.cells[1]).textAlign + ' ' + getComputedStyle(r.cells[1]).fontVariantNumeric) })`);
  check('sizes are right-aligned in figures of one width, their title too (branch record SIF-33)', sizes.head === 'right' && sizes.cells.length > 0 && sizes.cells.every(c => c === 'right tabular-nums'), JSON.stringify(sizes).slice(0, 200));
  const header = await evaluate(`(${TABLE}).querySelector('thead tr').getBoundingClientRect().height`);
  check('the button keeps the rows as low as text rows (no taller than the heading row plus 3 px)', rows.every(r => r.height <= header + 3), `rows ${rows.map(r => r.height).join('/')} px, heading ${header} px`);

  // ---- finding a file: the filter box and the column titles that sort (branch record SIF-99) --------------------------------
  // A run's ~500 files stood in folder order only, with no filter, in a panel six rows tall.
  const FILTER = `document.querySelector('footer input.files-filter')`;
  const names = () => evaluate(`${ROWS}.map(r => r.cells[0].textContent)`);
  const heads = () => evaluate(`[...(${TABLE}).querySelector('thead tr').cells].slice(0, 3).map(th => [th.textContent, th.getAttribute('aria-sort'), th.title])`);
  const byPath = await evaluate(`${JSON.stringify(FILES.files.map(f => f.path))}.sort((a, b) => a.localeCompare(b))`), bySize = [...FILES.files].sort((a, b) => a.bytes - b.bytes).map(f => f.path);
  const opening = await heads();
  check('the list opens sorted by File, A to Z (as the backend lists it), marked on its title; each title says it sorts (SIF-99)', JSON.stringify(await names()) === JSON.stringify(byPath)
    && opening[0][0] === 'File ▲' && opening[0][1] === 'ascending' && opening.every(([, , title]) => title.endsWith('Press to sort.')), JSON.stringify({ names: await names(), opening }));
  await evaluate(`(${TABLE}).querySelector('thead tr').cells[1].click()`);
  const smallFirst = await until(`JSON.stringify(${ROWS}.map(r => r.cells[0].textContent)) === ${JSON.stringify(JSON.stringify(bySize))}`, 30);
  await evaluate(`(${TABLE}).querySelector('thead tr').cells[1].click()`);
  const bigFirst = await until(`JSON.stringify(${ROWS}.map(r => r.cells[0].textContent)) === ${JSON.stringify(JSON.stringify([...bySize].reverse()))}`, 30);
  check('a press on Size sorts by it, the smallest first; a second press the other way, "Size ▼" (SIF-99)', smallFirst && bigFirst && (await heads())[1][0] === 'Size ▼', JSON.stringify({ names: await names(), heads: await heads() }));
  await evaluate(`(${TABLE}).querySelector('thead tr').cells[0].click()`);
  check('... and a press on File sorts by path again', await until(`JSON.stringify(${ROWS}.map(r => r.cells[0].textContent)) === ${JSON.stringify(JSON.stringify(byPath))}`, 30), JSON.stringify(await names()));
  check('the tool line has a filter box, empty', await evaluate(`${FILTER}?.value === '' && ${FILTER}.closest('.row') === (${TABLE}).closest('.scroll').previousElementSibling`));
  await page.setValue(FILTER, 'design', { event: 'input' });
  check('typing "design" keeps the four files under design/; the count says "4 of 7 files shown, 8.2 MiB in all." (SIF-99)', await until(`${ROWS}.length === 4`, 30)
    && (await names()).every(n => n.startsWith('design/')) && /^4 of 7 files shown, 8\.2 MiB in all\. Read at /.test(await evaluate(HINT)), JSON.stringify({ names: await names(), hint: await evaluate(HINT) }));
  await page.setValue(FILTER, 'JOURNAL jsonl', { event: 'input' });
  check('... the filter ignores case, and every word must stand in the path', await until(`${ROWS}.length === 2`, 30) && (await names()).every(n => n.startsWith('journal/')), JSON.stringify(await names()));
  await shot('files-0-filter.png');
  await page.setValue(FILTER, '', { event: 'input' });
  check('... and an empty box lists every file again, the count as before', await until(`${ROWS}.length === ${FILES.files.length}`, 30) && /^7 files, 8\.2 MiB\./.test(await evaluate(HINT)), await evaluate(HINT));

  // ---- one file: busy while on its way, then saved under the backend's name ----------------------------------------
  await press('manifest.json');
  const first = await heldSoon();
  check('pressing the button asks the backend for THAT file of THIS run', first?.run_dir === DIR && first?.path === 'manifest.json', JSON.stringify(first));
  const busy = await describe('manifest.json');
  check('while the file is on its way the button is disabled and shows the hourglass, still named the same', busy?.disabled && busy.hourglass && busy.text === 'Download manifest.json', JSON.stringify(busy));
  check('... the other rows stay ready', !(await describe('design/parameters.csv'))?.disabled && !(await describe('design/parameters.csv'))?.hourglass);
  await shot('files-1-busy.png');
  await release(BODY.manifest, 'manifest.json');
  const content = await savedFile('manifest.json');
  check('the file lands in the browser\'s download folder under the backend\'s name, byte for byte', content === BODY.manifest, JSON.stringify({ found: readdirSync(saved), content }));
  check('the hint says what was downloaded', await until(`${HINT}.includes('Downloaded manifest.json.')`, 40), await evaluate(HINT));
  const after = await describe('manifest.json');
  check('the button is ready again, with the download arrow', !after?.disabled && !after?.hourglass && after?.icon, JSON.stringify(after));
  await shot('files-2-after.png');

  // ---- a file in a folder is named by the backend (its own name, without the folder) ---------------------------------
  await press('design/best_feasible.json');
  const second = await heldSoon();
  check('a file in a folder is asked for by its path', second?.path === 'design/best_feasible.json', JSON.stringify(second));
  await release(BODY.best, 'best_feasible.json');
  check('... and saved under the name the backend gives it', (await savedFile('best_feasible.json')) === BODY.best && (await until(`${HINT}.includes('Downloaded best_feasible.json.')`, 40)), readdirSync(saved).join(', '));

  // ---- a file that is gone ----------------------------------------------------------------------------------------------
  await press('journal/dispatch.jsonl');
  await heldSoon(); await gone();
  check('a file the backend no longer has is said in the hint, in the backend\'s words, and nothing is saved', (await until(`${HINT}.includes('No such file')`, 40)) && !readdirSync(saved).includes('dispatch.jsonl'), await evaluate(HINT));
  check('... and its button is ready again', await until(`!(${BUTTON('journal/dispatch.jsonl')}).disabled`, 30), JSON.stringify(await describe('journal/dispatch.jsonl')));

  // ---- Copy run path says how it went (branch record SIF-94: it copied unsaid) ---------------------------------------------
  // The browser's clipboard is stood in for: a headless window may not be focused.
  const COPY = `[...(${TABLE}).closest('.scroll').previousElementSibling.querySelectorAll('button')].find(b => b.title.startsWith('Copy run path'))`;
  await evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: text => { window.__clip = text; return Promise.resolve(); } })`);
  await evaluate(`(${COPY}).click()`);
  check('Copy run path copies the run folder\'s path and says so in the hint (SIF-94)', await until(`${HINT}.endsWith('Copied the run path.')`, 30)
    && (await evaluate('window.__clip')) === DIR, await evaluate(HINT));
  await evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: () => Promise.reject(new DOMException('FIXTURE: Document is not focused.', 'NotAllowedError')) })`);
  await evaluate(`(${COPY}).click()`);
  check('... and a copy the browser refuses says so, with the path to select (SIF-94)', await until(`${HINT}.endsWith(${JSON.stringify(`Could not copy: the browser refused the clipboard. The run path: ${DIR}`)})`, 30),
    await evaluate(HINT));

  // SIF-94 review: "Packing..." is the package button's busy state, and the copy's word replaced it, so the hourglass went and a
  // second pack could start while the first was still zipping. The package request is held; a copy now leaves it standing.
  const PACK = `[...(${TABLE}).closest('.scroll').previousElementSibling.querySelectorAll('button')].find(b => b.title.startsWith('Download data-only package'))`;
  const packState = () => evaluate(`(b => ({ disabled: b.disabled, hourglass: b.querySelector('svg.icon path')?.getAttribute('d') === 'M4 2.5h8M4 13.5h8' }))(${PACK})`);
  await evaluate(`Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: text => { window.__clip = text; return Promise.resolve(); } })`);
  await evaluate(`window.__clip = null; (${PACK}).click()`);
  for (let i = 0; i < 50 && !packs.length; i++) await sleep(100);
  const packing = packs.length === 1 && await until(`${HINT}.endsWith('Packing...')`, 30) ? await packState() : null;
  await evaluate(`(${COPY}).click()`);
  const clipped = await until(`window.__clip === ${JSON.stringify(DIR)}`, 30); await sleep(300);
  const during = { clipped, hint: await evaluate(HINT), button: await packState() };
  check('a copy while the package is packing copies, and leaves the package button busy: disabled, the hourglass, "Packing..." (SIF-94 review)',
    !!packing?.disabled && packing.hourglass && clipped && during.hint.endsWith('Packing...') && during.button.disabled && during.button.hourglass, JSON.stringify({ packs: packs.length, packing, during }));
  if (packs.length) await fulfil(packs.shift(), 404, { detail: 'FIXTURE: Not a run directory' });
  check('... until the package is answered: the hint says how it went, and the button is ready again', await until(`${HINT}.endsWith('FIXTURE: Not a run directory')`, 30)
    && !(await packState()).disabled && !(await packState()).hourglass, JSON.stringify({ hint: await evaluate(HINT), button: await packState() }));
  await evaluate(`delete navigator.clipboard.writeText`);

  // ---- a live run: Output files and Data tables follow it (branch record SIF-99) ---------------------------------------------
  // Both were read once, when they opened, and went stale unsaid while Logs and Training followed the run. The run turns live
  // (its status is read every 1.5 s while the worker lives) and the page is opened again on it.
  const tab = label => evaluate(`[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent === ${JSON.stringify(label)}).click()`);
  runStatus = { ...RUN_STATUS, state: 'running', worker_alive: true, last_checkpoint_utc: at(40), persistence: { flushed_seq: 64, last_commit_seq: 64 },
    budget: { ...RUN_STATUS.budget, max_evaluations: 300, charged: 64, completed: 64, remaining: 236, launches: 64 } };
  await send('Page.reload');
  if (!(await until(`!!document.querySelector('footer .tabs')`, 150))) throw new Error('the page never came back after its reload');
  await tab('Output files');
  await until(`${ROWS}.length === ${FILES.files.length}`, 80);
  const live = listed;
  await sleep(3500);                                                               // two of the page's status reads
  check('a live run: a status update with nothing new does not read the folder again (SIF-99)', listed === live, `${listed - live} read(s) more`);
  runStatus = { ...runStatus, last_checkpoint_utc: at(50) };
  for (let i = 0; i < 60 && listed === live; i++) await sleep(100);
  await sleep(2000);
  check('... a new save point reads it again, once (SIF-99)', listed === live + 1, `${listed - live} read(s) more`);

  // Data tables: the newest 25 by default; read again at a flush, its rows kept and the hourglass on Refresh while it reads.
  const DATA_ROW = `document.querySelector('footer select.table-limit')?.closest('.row')`;
  const DATA_HINT = `(${DATA_ROW}?.querySelector('.hint')?.textContent ?? '')`;
  const SEQS = `[...document.querySelectorAll('footer table.data-table tbody tr')].map(r => Number(r.cells[1].textContent))`;
  const refresh = () => evaluate(`(b => b && { text: b.textContent, hourglass: b.querySelector('svg.icon path')?.getAttribute('d') === 'M4 2.5h8M4 13.5h8' })(${DATA_ROW}?.querySelector('button'))`);
  await tab('Data tables');
  await until(`${SEQS}.length === 3`, 80);
  const opened = tables.length, asked = tables.at(-1);
  check('Data tables asks for the newest 25 rows by default and lists them newest on top: "300 rows; the newest 3 shown, newest first. Read at hh:mm:ss." (SIF-99)',
    asked?.limit === '25' && asked?.tail === 'true' && JSON.stringify(await evaluate(SEQS)) === '[3,2,1]'
    && /^300 rows; the newest 3 shown, newest first\. Read at \d\d:\d\d:\d\d\./.test(await evaluate(DATA_HINT)), JSON.stringify({ asked, seqs: await evaluate(SEQS), hint: await evaluate(DATA_HINT) }));
  await sleep(3500);
  check('... a status update with nothing new reads nothing again', tables.length === opened, `${tables.length - opened} read(s) more`);
  holdTable = true;
  runStatus = { ...runStatus, persistence: { flushed_seq: 128, last_commit_seq: 128 }, budget: { ...runStatus.budget, charged: 128, completed: 128, remaining: 172 } };
  for (let i = 0; i < 60 && !heldTables.length; i++) await sleep(100);
  const reading = { held: heldTables.length, button: await refresh(), seqs: await evaluate(SEQS) };
  await page.shot(path.join(out, 'files-4-data-reading.png'), `document.querySelector('footer')`);
  check('... the run\'s flush reads the table again: while it reads, Refresh shows the hourglass ("Reading...") and the rows stay (SIF-99)', reading.held === 1
    && reading.button?.text === 'Reading...' && reading.button.hourglass && JSON.stringify(reading.seqs) === '[3,2,1]', JSON.stringify(reading));
  holdTable = false; data = DATA(364, 128);
  await fulfil(heldTables.shift(), 200, data);
  check('... then the new count, and Refresh as before', await until(`/^364 rows; the newest 3 shown, newest first\\. Read at /.test(${DATA_HINT})`, 40)
    && (await refresh())?.text === 'Refresh' && !(await refresh()).hourglass && tables.length === opened + 1, JSON.stringify({ hint: await evaluate(DATA_HINT), button: await refresh(), reads: tables.length - opened }));
  // The rows and order lists (SIF-99): the route reads up to 500, from either end; an early evaluation needed the CSV.
  await page.setValue(`document.querySelector('footer select.table-limit')`, '100');
  check('"100 rows" asks for 100', await until(`${SEQS}.length === 3`, 40) && tables.at(-1)?.limit === '100' && tables.at(-1)?.tail === 'true', JSON.stringify(tables.at(-1)));
  await page.setValue(`document.querySelector('footer select.table-order')`, 'oldest');
  check('"oldest first" asks for the table\'s first rows and lists them in their order: "364 rows; the oldest 3 shown, oldest first." (SIF-99)',
    await until(`/^364 rows; the oldest 3 shown, oldest first\\. Read at /.test(${DATA_HINT}) && JSON.stringify(${SEQS}) === '[1,2,3]'`, 40)
    && tables.at(-1)?.limit === '100' && tables.at(-1)?.tail === 'false', JSON.stringify({ asked: tables.at(-1), seqs: await evaluate(SEQS), hint: await evaluate(DATA_HINT) }));
  const lists = await evaluate(`(() => { const s = document.querySelector('footer select.tab-choice'), b = ${DATA_ROW}.querySelector('button');
    return [...${DATA_ROW}.children].indexOf(s) === 0 && s.nextElementSibling.matches('select.table-limit') && s.nextElementSibling.nextElementSibling.matches('select.table-order')
      && [...${DATA_ROW}.querySelectorAll('select')].every(e => { const r = e.getBoundingClientRect(), q = b.getBoundingClientRect(); return Math.abs((r.top + r.bottom) / 2 - (q.top + q.bottom) / 2) < 8; }); })()`);
  check('... the two lists stand after the table list, on its tool line', lists);
  await page.setValue(`document.querySelector('footer select.table-order')`, 'newest');
  await page.setValue(`document.querySelector('footer select.table-limit')`, '25');
  await until(`/^364 rows; the newest 3 shown/.test(${DATA_HINT})`, 40);

  // Output files once more: the worker's end reads the folder once more, then nothing.
  await tab('Output files');
  await until(`${ROWS}.length === ${FILES.files.length}`, 80);
  await sleep(500);
  const back = listed;
  runStatus = { ...runStatus, state: 'completed', worker_alive: false };
  for (let i = 0; i < 60 && listed === back; i++) await sleep(100);
  await sleep(2500);
  check('... the worker\'s end reads the run folder once more, then nothing (SIF-99)', listed === back + 1, `${listed - back} read(s) more`);

  reportRefused(refused, NEVER_ASKED_OR_SAVED);
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});                                                                            // Edge closes at the end, and the download folder goes with it
