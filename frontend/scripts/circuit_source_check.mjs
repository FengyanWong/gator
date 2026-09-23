// Browser check of the Project panel's "Circuit source" list after "Import Spectre netlist" was removed (user request
// 2026-09-21, status record 7.53; there is no frontend test runner). Same approach as project_help_check.mjs: a throwaway
// headless Edge over the DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/), with a new,
// temporary browser profile whose saved configuration is SEEDED with one written while the netlist source existed.
// EVERY /api/* request is paused: GETs, static validation and the load of a registered task pass through (read-only; the
// task here is the MOCK task synthetic:gpdk045_ota5), every other request is refused here - nothing is started, saved or
// probed, and Virtuoso is never contacted. So it is safe against the user's live backend.
// What it pins: the list offers a registered task and a Virtuoso cell only; a saved configuration that still names the
// netlist source shows it as removed, says so in plain words and sends NOTHING about it to the backend; choosing another
// source drops the two file paths (in the browser's saved copy too) and loads normally; Undo brings the old state back
// without a request. (Until 7.53 this script checked the netlist form itself: 21 checks, status record 7.13.)
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/circuit_source_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const STORAGE_KEY = 'gator-workbench-config-v1';
const out = outDir();
const browser = await launchEdge('src');

try {
  const meta = await (await fetch(new URL('api/meta', APP))).json();
  const NETLIST = `${meta.repo_root}/tests/fixtures/synthetic/opamp.scs`, MAPPING = `${meta.repo_root}/configs/opamp.json`;
  // What the removed form left in a saved configuration: the source, the two paths, and the task id the page started with.
  const CONFIG = { schema_version: 'gator-workbench-config-v1', project: { name: 'fixture', task_name: 'fixture', notes: '' },
    circuit: { source: 'netlist', task_id: 'synthetic:gpdk045_ota5', netlist_path: NETLIST, parser_config_path: MAPPING, circuit_class: 'unspecified', pdk_id: 'unspecified' },
    parameters: [], targets: [], measurements: [], run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0 },
    output: { experiment_name: 'fixture' }, research: {} };
  const page = await browser.open();
  const { send, evaluate, until, consoleErrors } = page;
  const loads = []; const refused = [];
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/circuit/load') {
      const circuit = JSON.parse(request.postData ?? '{}').circuit ?? {};
      loads.push(circuit);
      if (circuit.source === 'registered_task') return page.pass(requestId);
    } else if (request.method === 'GET' || name === '/api/config/validate') return page.pass(requestId);
    else if (name !== '/api/output/check') refused.push(`${request.method} ${name}`);  // that one is the Output panel's own check at page load:
                                                                                       // it writes a probe file, so it is refused too, but expected
    return page.refuse(requestId, 'FIXTURE: this check lets no other request through');
  };
  const PANEL = `[...document.querySelectorAll('.left .panel')].find(p => [...p.querySelectorAll('h3')].some(h => h.textContent.trim() === 'Circuit source'))`;
  const FIELD = label => `[...${PANEL}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})?.querySelector('input, select')`;
  const SOURCE = FIELD('Source');
  const text = () => evaluate(`${PANEL}.textContent`);
  const options = () => evaluate(`[...${SOURCE}.options].map(o => ({ value: o.value, text: o.textContent.trim(), disabled: o.disabled }))`);
  const choose = (label, v) => evaluate(`(() => { const s = ${FIELD(label)}; Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(v)});
    s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const settle = async (mark, ms = 6000) => { for (let waited = 0; waited < ms && loads.length === mark; waited += 100) await sleep(100); await sleep(900); };
  const saved = () => evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)}) || 'null')?.circuit ?? null`);
  const shot = async name => {                                                      // the left column scrolls: bring the source into view, clip to what is visible
    const H3 = `[...${PANEL}.querySelectorAll('h3')].find(h => h.textContent.trim() === 'Circuit source')`;
    await evaluate(`${H3}.scrollIntoView({ block: 'start' })`); await sleep(200);
    await page.shot(path.join(out, name), await evaluate(`(() => { const a = document.querySelector('.left').getBoundingClientRect(), h = ${H3}.getBoundingClientRect();
      return { x: a.x, y: Math.max(a.y, h.y - 6), width: a.width, height: a.bottom - Math.max(a.y, h.y - 6), scale: 2 }; })()`));
  };

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${PANEL}) && !!(${SOURCE})`, 150))) throw new Error('the Project panel never showed its Source list | console: ' + consoleErrors.join(' | ').slice(0, 300));
  await sleep(2500);                                                                // time enough for any load the page might (wrongly) send

  // ---- a configuration saved with the removed source -----------------------------------------------------------------
  const before = await options();
  check('the saved source is shown as removed (and cannot be chosen again), next to the two sources on offer',
    (await evaluate(`${SOURCE}.value`)) === 'netlist' && JSON.stringify(before) === JSON.stringify([{ value: 'netlist', text: 'Spectre netlist (removed)', disabled: true },
      { value: 'registered_task', text: 'Registered task', disabled: false }, { value: 'virtuoso', text: 'Virtuoso library / cell / view', disabled: false }]), JSON.stringify(before));
  check('a plain note says what happened, names the saved file and what to do', (await text()).includes('This configuration was saved with a Spectre netlist file')
    && (await text()).includes(NETLIST) && (await text()).includes('The workbench no longer imports netlists: choose another source above.')
    && await evaluate(`!!${PANEL}.querySelector('.note code')`));
  const widths = await evaluate(`(() => { const c = document.querySelector('.left'); return [c.scrollWidth, c.clientWidth]; })()`);
  check('the long path wraps inside the note: the column does not scroll sideways', widths[0] <= widths[1], `scrollWidth ${widths[0]}, clientWidth ${widths[1]}`);
  check('nothing about it is sent to the backend (no circuit load at all)', loads.length === 0, JSON.stringify(loads));
  check('no red "Blocked" box, no error line, no schema field names', !(await evaluate(`!!${PANEL}.querySelector('.blocker, p.error')`))
    && !(await text()).includes('netlist_path') && !(await text()).includes('parser_config_path'));
  const panelText = await text();
  check('nothing of the removed form is left', !(await evaluate(`!!(${FIELD('Netlist path')}) || !!(${FIELD('Device mapping (JSON)')})`))
    && !['Load netlist', 'Try the example', 'Two files are needed', 'Which two files'].some(words => panelText.includes(words)));
  check('no circuit of any source is shown', !(await text()).includes('Hierarchy ('));
  await shot('source-1-saved-netlist.png');

  // ---- choosing a source that is on offer ----------------------------------------------------------------------------------
  let mark = loads.length;
  await choose('Source', 'registered_task'); await settle(mark);
  check('"Registered task" sends exactly one load: that task, without the two file paths', loads.length === mark + 1 && loads[mark].source === 'registered_task'
    && loads[mark].task_id === 'synthetic:gpdk045_ota5' && loads[mark].netlist_path === null && loads[mark].parser_config_path === null, JSON.stringify(loads.slice(mark)));
  check('the task is read: MOCK backend, its hierarchy', (await text()).includes('MOCK evaluation backend') && (await text()).includes('Hierarchy ('));
  const after = (await options()).map(o => o.value);
  check('the removed entry and the note are gone', JSON.stringify(after) === JSON.stringify(['registered_task', 'virtuoso'])
    && !(await text()).includes('This configuration was saved with a Spectre netlist file'), after.join(' | '));
  await sleep(1200);                                                                // the page keeps its copy 0.8 s after a change
  const kept = await saved();
  check('the browser\'s saved copy no longer names the files', kept?.source === 'registered_task' && kept.netlist_path === null && kept.parser_config_path === null, JSON.stringify(kept));
  await shot('source-2-registered-task.png');

  // ---- Undo brings the old configuration back, still without a request ---------------------------------------------------------
  mark = loads.length;
  await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Undo').click()`); await sleep(1500);
  check('Undo: the saved netlist source is back, shown as removed, and nothing is sent', (await evaluate(`${SOURCE}.value`)) === 'netlist'
    && (await text()).includes('This configuration was saved with a Spectre netlist file') && loads.length === mark && !(await text()).includes('Hierarchy ('),
    `${loads.length - mark} request(s)`);

  check('the page asked nothing else of the backend (every request besides reads is refused here)', refused.length === 0, refused.join(' | '));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
