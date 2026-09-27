// Browser check of the two FOLDABLE modules of the right column, "Run configuration" and "Output settings" (there is no
// frontend test runner in this project). Same approach as blocking_issues_check.mjs: a throwaway headless Edge over the
// DevTools protocol against the RUNNING workbench (default http://127.0.0.1:8765/). POST /api/output/check is answered
// with a canned report labelled FIXTURE and /api/config/validate with an empty one; GET requests pass through; every
// other writing request is refused here, so this check can start, save or probe nothing on the backend it runs against.
// The browser profile is new and temporary: the user's saved configuration and fold choices are not touched.
// What it pins (user request 2026-09-21, "make the run configuration module and output settings module able to collapse
// from expanded"):
//   - both modules start OPEN and fold into one line under their own heading; the third panel (Research) is unchanged;
//   - a folded module stays mounted (its controls exist and keep working) and its line says the main values;
//   - the choice is kept in this browser across a reload;
//   - an error or a warning inside a folded module is marked on its line - also when it appears while folded.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/module_fold_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { validConfiguration, check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('fold');

const ROOT = '/fixture/some/long/way/down/to/the/output-root';
const REPORT = { resolved: ROOT, allowed: true, writable: true, error: null, host: 'FIXTURE', environment: 'fixture', filesystem: 'fixture',
  free_bytes: 400 * 1024 ** 3, bytes_used: 3 * 1024 ** 3, windows_path: null, windows_mapping: 'fixture', mock_data_root: '/fixture/mock' };
const VALID = validConfiguration();

try {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  // The network and training numbers are the ones this backend has stored, and the budget is well above its warm-up: a
  // configuration that raises no warning of its own (a differing network or a starved budget would be a warning inside).
  const stored = await (await fetch(new URL('api/network-settings', APP))).json();
  const entry = stored.settings[stored.default_encoder];
  const NET = { encoder_type: stored.default_encoder, ...entry.network };
  const BUDGET = Math.max(entry.advanced.warmup_transitions ?? 0, entry.advanced.batch_size ?? 0) + 1000;
  const LINE = `scratch - ${BUDGET} evaluations - ${NET.encoder_type} ${NET.hidden_dim}/${NET.heads}/${NET.layers}`;
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'scratch', max_evaluations: BUDGET, network: NET, advanced: { ...(starter.run.advanced ?? {}), ...entry.advanced } },
    output: { experiment_name: 'fixture', output_root: ROOT }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, fulfil, consoleErrors } = page;
  const refused = []; let writable = true, probes = 0;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/output/check') { probes++; return fulfil(requestId, 200, writable ? REPORT : { ...REPORT, allowed: false, writable: false, error: 'FIXTURE: outside the allowed roots' }); }
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const evaluate = expression => page.evaluate(expression, true);
  const until = (expression, tries = 60) => page.until(expression, tries);

  const panel = title => `[...document.querySelectorAll('.right .panel')].find(p => p.querySelector('h3')?.textContent.trim() === ${JSON.stringify(title)})`;
  const RUN = panel('Run configuration'), OUTPUT = panel('Output settings'), RESEARCH = `[...document.querySelectorAll('.right .panel')][2]`;
  const fold = p => `${p}.querySelector('details.module')`;
  const MODE = `[...${RUN}.querySelectorAll('label')].find(l => l.firstChild?.textContent?.trim() === 'Mode')?.querySelector('select')`;
  const BUDGET_BOX = `[...${RUN}.querySelectorAll('label')].find(l => l.querySelector('span')?.textContent.trim() === 'Evaluation budget (max_evaluations)')?.querySelector('input')`;
  const state = p => evaluate(`(() => { const d = ${fold(p)}, s = d.querySelector(':scope > summary'); return { open: d.open, heading: s.querySelector('h3').textContent,
    line: s.querySelector('.module-summary')?.textContent ?? null, title: s.querySelector('.module-summary')?.title ?? null,
    attention: s.querySelector('.module-attention')?.textContent ?? null, kind: s.querySelector('.module-attention')?.className ?? null,
    height: Math.round(${p}.getBoundingClientRect().height) }; })()`);
  // A real mouse click on the heading text, as a user folds it.
  const clickHeading = async p => {
    await evaluate(`${fold(p)}.querySelector(':scope > summary').scrollIntoView({ block: 'center' })`); await sleep(120);
    const at = await evaluate(`(() => { const r = ${fold(p)}.querySelector(':scope > summary h3').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
    for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: at.x, y: at.y, button: 'left', clickCount: 1 });
    await sleep(250);
  };
  const type = async (expression, text) => { await evaluate(`(() => { const i = ${expression}; i.scrollIntoView({ block: 'center' }); i.focus(); i.select(); })()`); await send('Input.insertText', { text }); await sleep(300); };
  const remembered = id => evaluate(`localStorage.getItem('gator-workbench-module-${id}')`);
  const shot = async name => {
    await evaluate(`document.querySelector('.right').scrollTo(0, 0)`); await sleep(150);
    await page.shot(path.join(out, name), 'document.querySelector(".right")', { scale: 1.5, maxHeight: 1000 });
  };

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'missing' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!(${RUN}) && !!(${OUTPUT})`, 150))) throw new Error('the two panels never appeared; the page reads: '
    + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)) + ' | console: ' + consoleErrors.join(' | ').slice(0, 300));
  if (!(await evaluate(`!!${fold(RUN)}`))) throw new Error('the panels do not fold: the served frontend is older than this change (npm run build, then reload)');
  await sleep(600);

  // ---- at first: open, under their own headings ------------------------------------------------------------------------
  let run = await state(RUN), output = await state(OUTPUT);
  check('both modules start OPEN', run.open && output.open, JSON.stringify([run.open, output.open]));
  check('the heading of each module is its fold line, with unchanged text', run.heading === 'Run configuration' && output.heading === 'Output settings');
  check('open, a module shows no summary line and no mark', run.line === null && run.attention === null && output.line === null && output.attention === null, JSON.stringify([run, output]));
  check('their controls are in view (Mode, output root)', await evaluate(`${MODE}.checkVisibility() && ${OUTPUT}.querySelector('#output-root').checkVisibility()`));
  check('the third panel (Research) is not a fold: only the two asked for changed', await evaluate(`!!(${RESEARCH}) && !${RESEARCH}.querySelector('details.module')`));
  check('nothing was remembered before a fold line was used ... or only "open"', [null, 'open'].includes(await remembered('run')) && [null, 'open'].includes(await remembered('output')));
  const openHeight = run.height;
  await shot('fold-1-open.png');

  // ---- folding the run module ----------------------------------------------------------------------------------------------
  await clickHeading(RUN);
  run = await state(RUN); output = await state(OUTPUT);
  check('a click on the heading folds "Run configuration" into one line', !run.open && run.height < 70 && run.height < openHeight / 4, `${openHeight} px -> ${run.height} px`);
  check('... and leaves "Output settings" as it was', output.open);
  check('the folded line says the main values: Mode, budget, network', run.line === LINE, run.line);
  check('nothing inside is in view any more, but it all still exists (the module stays mounted)', await evaluate(`!${MODE}.checkVisibility() && !!(${BUDGET_BOX}) && !!${RUN}.querySelector('.module-body')`));
  check('no mark on the line: nothing inside asks for attention', run.attention === null, String(run.attention));
  check('the choice is kept in this browser', (await remembered('run')) === 'closed' && (await remembered('output')) !== 'closed');
  const fits = await evaluate(`(() => { const right = document.querySelector('.right'), s = ${fold(RUN)}.querySelector('.module-summary').getBoundingClientRect(), h = ${fold(RUN)}.querySelector('h3').getBoundingClientRect(), p = ${RUN}.getBoundingClientRect();
    return { noSideScroll: right.scrollWidth <= right.clientWidth + 1, below: s.top >= h.bottom - 1, inside: s.left >= p.left && s.right <= p.right + 1 }; })()`);
  check('the summary sits on its own line under the heading, inside the narrow panel', fits.noSideScroll && fits.below && fits.inside, JSON.stringify(fits));

  // ---- folded is not switched off: the line follows the configuration ------------------------------------------------------------
  await page.setValue(`${MODE}`, 'frozen');
  check('a change of the configuration shows on the folded line (Mode frozen)', await until(`${fold(RUN)}.querySelector('.module-summary')?.textContent.startsWith('frozen - ${BUDGET} evaluations')`, 30), (await state(RUN)).line);
  await page.setValue(`${MODE}`, 'scratch');
  await until(`${fold(RUN)}.querySelector('.module-summary')?.textContent.startsWith('scratch')`, 30);

  // ---- remembered across a reload ---------------------------------------------------------------------------------------------------
  await sleep(1000);
  await send('Page.reload'); await until(`!!(${RUN}) && !!(${OUTPUT}) && !!${fold(RUN)}`, 150); await sleep(600);
  run = await state(RUN); output = await state(OUTPUT);
  check('after a reload "Run configuration" is still folded and "Output settings" still open', !run.open && output.open, JSON.stringify([run.open, output.open]));
  check('... with its summary line', run.line === LINE, run.line);

  // ---- unfolding; a warning inside is marked on the folded line -------------------------------------------------------------------------
  await clickHeading(RUN);
  check('a second click unfolds it, and that is remembered too', (await state(RUN)).open && (await evaluate(`${MODE}.checkVisibility()`)) && (await remembered('run')) === 'open');
  await type(BUDGET_BOX, '1');
  check('(set-up) a budget of 1 raises the "never learns" warning inside the module', await until(`[...${RUN}.querySelectorAll('.module-body p.warn')].some(p => /^Budget 1 with warm-up/.test(p.textContent))`, 30));
  check('open, the warning is in view itself: no mark on the heading', (await state(RUN)).attention === null);
  await clickHeading(RUN);
  run = await state(RUN);
  check('folded, the line carries the mark "warning inside"', !run.open && run.attention === 'warning inside' && /\bwarn\b/.test(run.kind), JSON.stringify(run));
  const amber = await evaluate(`getComputedStyle(${fold(RUN)}.querySelector('.module-attention')).backgroundColor`);
  await shot('fold-2-run-folded-warning.png');
  await clickHeading(RUN); await type(BUDGET_BOX, String(BUDGET)); await until(`!${RUN}.querySelector('.module-body p.warn')`, 30); await clickHeading(RUN);
  check('with the budget back the mark is gone', (await state(RUN)).attention === null && !(await state(RUN)).open, JSON.stringify(await state(RUN)));

  // ---- the output module; an error that appears WHILE it is folded ----------------------------------------------------------------------------
  await clickHeading(OUTPUT);
  output = await state(OUTPUT);
  check('"Output settings" folds the same way; its line says the experiment and the END of the output root', !output.open && output.line === 'fixture - .../the/output-root' && output.attention === null, JSON.stringify(output));
  check('... the whole line is also its tooltip (a long one is cut with an ellipsis)', output.title === output.line);
  const before = probes; writable = false;
  await evaluate(`[...${OUTPUT}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Test writability').click()`);
  check('an error that appears while the module is folded is marked at once: "error inside", in red', await until(`${fold(OUTPUT)}.querySelector('.module-attention')?.textContent === 'error inside'`, 40) && probes === before + 1, JSON.stringify(await state(OUTPUT)));
  const red = await evaluate(`getComputedStyle(${fold(OUTPUT)}.querySelector('.module-attention')).backgroundColor`);
  check('the two marks differ in colour (warning amber, error red)', amber !== red && red === 'rgb(179, 38, 30)', JSON.stringify([amber, red]));
  await shot('fold-3-both-folded.png');
  await clickHeading(OUTPUT);
  check('unfolded, the error itself is in view', (await state(OUTPUT)).open && await evaluate(`[...${OUTPUT}.querySelectorAll('td.error')].some(td => /FIXTURE: outside the allowed roots/.test(td.textContent) && td.checkVisibility())`));

  // ---- keyboard ------------------------------------------------------------------------------------------------------------------------------
  await evaluate(`${fold(OUTPUT)}.querySelector(':scope > summary').focus()`);
  for (const t of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type: t, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: t === 'keyDown' ? '\r' : undefined });
  await sleep(300);
  check('the fold line works from the keyboard (Enter)', !(await state(OUTPUT)).open);

  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  check('the page asked to start, continue, command, connect, save settings or call an agent on its own: never',
    !refused.some(r => /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/|network-settings)/.test(r)), refused.join(', '));
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
