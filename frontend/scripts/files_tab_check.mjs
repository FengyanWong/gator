// Browser check of the "Output files" tab's per-file download. User request 2026-09-26: "change the downloads on the
// right to buttons with icons" - each row ends with an icon button (the download arrow, hourglass while the file is on
// its way) instead of a "download" text link; the file is saved like the package and the logs (the browser's own
// download, named by the backend) and the hint says "Downloaded <name>.".
// Hermetic, on the shared harness: the run's status and file list are canned (FIXTURE), the download request is held
// so the busy state can be seen, then answered with a canned body and Content-Disposition; the browser's download
// folder is a temporary one. GET requests pass, every other writing request is refused. Safe against the live 8765 page.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/files_tab_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { validConfiguration, check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

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
const VALID = validConfiguration({ mock: true });
// A finished download: the named file is there and Edge's temporary ".crdownload" twin is gone.
const savedFile = async name => { for (let i = 0; i < 100; i++) { const names = readdirSync(saved); if (names.includes(name) && !names.some(n => n.endsWith('.crdownload'))) return readFileSync(path.join(saved, name), 'utf8'); await sleep(100); } return null; };

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { ...starter, output: { experiment_name: 'fixture' }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const held = []; let listed = 0;
  const answer = ({ requestId, request }) => {
    const url = new URL(request.url), name = url.pathname;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/status') return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, RUN_STATUS) : fulfil(requestId, 404, { detail: 'Not a run directory' });
    if (name === '/api/runs') return fulfil(requestId, 200, { runs: [] });
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (name === '/api/runs/files') { listed++; return url.searchParams.get('run_dir') === DIR ? fulfil(requestId, 200, FILES) : fulfil(requestId, 404, { detail: 'Not a run directory' }); }
    if (name === '/api/runs/download') { held.push({ requestId, run_dir: url.searchParams.get('run_dir'), path: url.searchParams.get('path') }); return; }   // answered by the check itself
    return page.readOrRefuse({ requestId, request }, refused);
  };
  // The backend's answer: the file's bytes under its own name (support.attachment), or 404 for a file that is gone.
  const release = (body, filename) => { const h = held.shift(); return send('Fetch.fulfillRequest', { requestId: h.requestId, responseCode: 200, body: Buffer.from(body).toString('base64'),
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Content-Length', value: String(Buffer.byteLength(body)) }, { name: 'Content-Disposition', value: `attachment; filename="${filename}"` }] }); };
  const gone = () => { const h = held.shift(); return fulfil(h.requestId, 404, { detail: 'FIXTURE: No such file' }); };
  const heldSoon = async () => { for (let i = 0; i < 50 && !held.length; i++) await sleep(100); return held[0] ?? null; };
  const until = (expression, tries = 80) => page.until(expression, tries);
  // The visible tab's table (the Agent tab stays mounted but hidden in the same footer: never "the first table").
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
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: c.x, y: c.y, button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: c.x, y: c.y, button: 'left', clickCount: 1 }); };
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
  const rows = await evaluate(`${ROWS}.map(r => { const b = r.cells[3].querySelector('button'); return { file: r.cells[0].textContent, cells: r.cells.length, links: r.querySelectorAll('a').length,
    button: !!b, icon: !!b?.querySelector('svg.icon'), text: b?.textContent, title: b?.title, disabled: b?.disabled, height: r.getBoundingClientRect().height }; })`);
  check('no row has a "download" text link any more', rows.every(r => r.links === 0), JSON.stringify(rows.filter(r => r.links)));
  check('every row ends with an enabled icon button named "Download <file>"', rows.every(r => r.cells === 4 && r.button && r.icon && !r.disabled && r.text === `Download ${r.file}`), JSON.stringify(rows.map(r => r.text)));
  check('... whose tooltip starts with that name and says where the file goes', rows.every(r => r.title.startsWith(`Download ${r.file}: `) && /download folder/.test(r.title)), rows[0]?.title);
  const header = await evaluate(`(${TABLE}).querySelector('thead tr').getBoundingClientRect().height`);
  check('the button keeps the rows as low as text rows (no taller than the heading row plus 3 px)', rows.every(r => r.height <= header + 3), `rows ${rows.map(r => r.height).join('/')} px, heading ${header} px`);

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

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect, save settings or call an agent on its own: never',
    !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/|network-settings)/.test(r)), refused.join(', '));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  fail(error);
} finally {
  await browser.close();                                                     // the download folder goes with it
}
finish();
