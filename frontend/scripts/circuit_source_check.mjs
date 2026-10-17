// Browser check of a configuration saved with the removed "Import Spectre netlist" source (user request 2026-09-21,
// status record 7.53; since 2026-09-23 there is no Source list any more - the task's name says it; there is no frontend
// test runner). Same approach as project_help_check.mjs: a throwaway
// headless Edge over the DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/), with a new,
// temporary browser profile whose saved configuration is SEEDED with one written while the netlist source existed.
// EVERY /api/* request is paused: GETs, static validation and the load of a registered task pass through (read-only; the
// task here is the MOCK task synthetic:gpdk045_ota5), every other request is refused here - nothing is started, saved or
// probed, and Virtuoso is never contacted. So it is safe against the user's live backend.
// What it pins: a saved configuration that still names the netlist source shows no task chosen, says so in plain words -
// under the editors' toolbar with the task's other lines since record 7.362 (the user's Option D; the Project column until
// then), the circuit column empty - and sends NOTHING about it to the backend; choosing a task drops the two file paths (in
// the browser's saved copy too) and loads normally; Undo brings the old state back without a request. (Until 7.53 this
// script checked the netlist form itself: 21 checks, status record 7.13; until 2026-09-23 the Source list.)
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/circuit_source_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, CIRCUIT_PANEL, launchEdge, outDir, runChecks, sleep, TASK_PANEL, taskWindow, workbenchUrl, CONFIG_KEY } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('src');

await runChecks(browser, async () => {
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
  // Record 7.362 (the user's Option D): the editors are the task's card - its name on their tab line, its own lines (this note
  // among them) under their toolbar - and the circuit column, folded away until "Show circuit", holds the circuit alone.
  const PANEL = TASK_PANEL;
  const STATUS = `${PANEL}.querySelector('.task-status')`;
  const COLUMN = CIRCUIT_PANEL;
  const FIELD = (root, label) => `[...${root}.querySelectorAll('label')].find(l => l.firstChild?.textContent.trim() === ${JSON.stringify(label)})?.querySelector('input, select')`;
  // Since record 7.227 the task is plain text + a "Tasks..." button; a choice is a double click in the task window (harness taskWindow).
  const tw = taskWindow(page, browser);
  const OPENED = `!!(${PANEL}) && !!${PANEL}.querySelector('.task-row button.task-list-button')`;
  const text = () => evaluate(`${PANEL}.textContent`);
  const lines = () => evaluate(`${STATUS}?.textContent ?? ''`);                       // the task's own lines
  const circuitText = () => evaluate(`${COLUMN}?.textContent ?? ''`);
  const choose = (label, v) => tw.choose(v, { tries: 0 });
  const settle = async (mark, ms = 6000) => { for (let waited = 0; waited < ms && loads.length === mark; waited += 100) await sleep(100); await sleep(900); };
  const saved = () => evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(CONFIG_KEY)}) || 'null')?.circuit ?? null`);
  const shot = async name => {                                                      // the editors' card from its tab line down to the task's lines
    await page.shot(path.join(out, name), await evaluate(`(() => { const p = ${PANEL}.getBoundingClientRect(), s = ${STATUS}.getBoundingClientRect();
      return { x: p.x, y: p.y, width: p.width, height: Math.max(s.bottom, p.y + 80) - p.y + 2, scale: 2 }; })()`));
  };

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG });
  await send('Page.navigate', { url: APP });
  if (!(await until(OPENED, 150))) throw new Error('the editors\' tab line never showed the task row | console: ' + consoleErrors.join(' | ').slice(0, 300));
  await sleep(2500);                                                                // time enough for any load the page might (wrongly) send

  // ---- a configuration saved with the removed source -----------------------------------------------------------------
  const before = await tw.keys();
  check('no task is chosen: the Task row shows the removed source as none, and the task window offers the tasks',
    (await tw.current()) === '(none: the saved source was removed)' && before.includes('synthetic:gpdk045_ota5') && !before.some(k => k === 'virtuoso' || k === 'netlist'),
    JSON.stringify([await tw.current(), before]));
  check('there is no Source list any more (the editors\' card, the circuit column)', !(await evaluate(`!!(${FIELD(PANEL, 'Source')}) || !!(${FIELD(COLUMN, 'Source')})`)));
  const note = await lines();
  check('a plain note under the editors\' toolbar says what happened, names the saved file and what to do', note.includes('This configuration was saved with a Spectre netlist file')
    && note.includes(NETLIST) && note.includes('The workbench no longer imports netlists: choose a task, or a Virtuoso cell, in the Tasks window (the task\'s name on this tab line).')
    && await evaluate(`!!${STATUS}.querySelector('.note code')`), note.slice(0, 400));
  // The note is as wide as the editors now, wider than the path: what wraps it at any width is its rule (styles.css: .note code).
  const widths = await evaluate(`(() => { const n = ${STATUS}.querySelector('.note'), c = n?.querySelector('code'), card = ${PANEL}; if (!c) return null;
    return { note: [n.scrollWidth, n.clientWidth], card: [card.scrollWidth, card.clientWidth], inside: c.getBoundingClientRect().right <= n.getBoundingClientRect().right + 1, wraps: getComputedStyle(c).overflowWrap }; })()`);
  check('the long path wraps inside the note: neither the note nor the editors\' card scrolls sideways', !!widths && widths.note[0] <= widths.note[1] && widths.card[0] <= widths.card[1]
    && widths.inside && widths.wraps === 'anywhere', JSON.stringify(widths));
  check('nothing about it is sent to the backend (no circuit load at all)', loads.length === 0, JSON.stringify(loads));
  const marks = await evaluate(`[...${STATUS}.querySelectorAll('.blocker, p.error'), ...${COLUMN}.querySelectorAll('.blocker, p.error')].map(e => e.className + ': ' + e.textContent.slice(0, 120))`);
  const said = (await lines()) + ' ' + (await circuitText()) + ' ' + (await evaluate(`${PANEL}.querySelector('.tabs .task-head')?.textContent ?? ''`));
  check('no red "Blocked" box, no error line, no schema field names', marks.length === 0 && !said.includes('netlist_path') && !said.includes('parser_config_path'), JSON.stringify(marks).slice(0, 400));
  const panelText = (await text()) + ' ' + (await circuitText());
  check('nothing of the removed form is left', !(await evaluate(`[${FIELD(PANEL, 'Netlist path')}, ${FIELD(PANEL, 'Device mapping (JSON)')}, ${FIELD(COLUMN, 'Netlist path')}, ${FIELD(COLUMN, 'Device mapping (JSON)')}].some(Boolean)`))
    && !['Load netlist', 'Try the example', 'Two files are needed', 'Which two files'].some(words => panelText.includes(words)));
  const empty = await circuitText();
  check('no circuit of any source is shown: the circuit column says it waits for a task', !empty.includes('Hierarchy (') && empty.includes('The picture and the hierarchy of the task show here once it is loaded.'), empty.slice(0, 200));
  await shot('source-1-saved-netlist.png');

  // ---- choosing a task -----------------------------------------------------------------------------------------------------
  let mark = loads.length;
  await choose('Task', 'synthetic:gpdk045_ota5'); await settle(mark);
  check('choosing a task sends exactly one load: that task, without the two file paths', loads.length === mark + 1 && loads[mark].source === 'registered_task'
    && loads[mark].task_id === 'synthetic:gpdk045_ota5' && loads[mark].netlist_path == null && loads[mark].parser_config_path == null, JSON.stringify(loads.slice(mark)));
  // `== null`: since record 7.146 a task choice leaves both paths out instead of writing them as null; the backend reads both as null
  check('the task is read: MOCK backend under the editors\' toolbar, its hierarchy in the circuit column', (await lines()).includes('MOCK evaluation backend') && (await circuitText()).includes('Hierarchy ('));
  check('the removed entry and the note are gone', (await tw.current()) === 'synthetic:gpdk045_ota5'
    && !(await text()).includes('This configuration was saved with a Spectre netlist file'), await tw.current());
  await sleep(1200);                                                                // the page keeps its copy 0.8 s after a change
  const kept = await saved();
  check('the browser\'s saved copy no longer names the files', kept?.source === 'registered_task' && kept.netlist_path == null && kept.parser_config_path == null, JSON.stringify(kept));
  await shot('source-2-registered-task.png');

  // ---- Undo brings the old configuration back, still without a request ---------------------------------------------------------
  mark = loads.length;
  await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Undo').click()`); await sleep(1500);
  check('Undo: the saved netlist source is back, shown as none, and nothing is sent', (await tw.current()) === '(none: the saved source was removed)'
    && (await lines()).includes('This configuration was saved with a Spectre netlist file') && loads.length === mark && !(await circuitText()).includes('Hierarchy ('),
    `${loads.length - mark} request(s)`);

  check('the page asked nothing else of the backend (every request besides reads is refused here)', refused.length === 0, refused.join(' | '));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
