// Browser check of the page's two looks and the layout moves of record 7.158 (the user's choices of 2026-10-03: "1 A+B, 2 yes,
// 3 yes, 4 yes, 5 yes, 6 Windows"). Hermetic: reads pass to the backend under test, the run the bottom tabs show is a FIXTURE
// answered here, every other writing request is refused - the page may write nothing of its own.
// What it pins:
//   - a fresh browser opens in Whiteprint; the header's icon button switches to Silicon Night and back, the choice survives a
//     reload (set before the page draws) and every open pop-up window follows it;
//   - text stays readable in both looks (each text / background pair of the page's colours at least 4.5 : 1, WCAG AA), and no
//     box is left light in Silicon Night (main page, three bottom tabs, the Runs window);
//   - switching the look moves no box (the same sizes in both, record 7.162);
//   - the header's title block names the task, its revision, the circuit's class and PDK and the RL model label; the version is one
//     hover away on the name; Windows' own fonts are the ones asked for;
//   - the splitter above the bottom panel: a drag sets its height, a double click folds it to its tab line and back, a tab press
//     opens it, the arrow keys and Enter do the same from the keyboard; kept in this browser; hidden on narrow windows;
//   - each editor's colour on its tab and its table's header row; the Specs line offers the Probe ids as chips (same text);
//   - Data tables: one line per row - ids end in "...", the whole value on hover, a click copies it; no word cut in two;
//   - Research experiments: the two retired labels dropped from a saved configuration, three labels shown, six folded; no
//     "Search method" any more (record 7.226; one, as its label, since 7.163);
//   - the circuit picture: folded at first like every block of the Project column, drawn from the loaded circuit; pointing at a
//     Parameters row lights its device and the one tied to it; its fold is kept in this browser.
// Run: WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=<a scratch build> "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w
// frontend/scripts/looks_check.mjs)" [screenshot-dir], or bash frontend/scripts/run_checks.sh --only looks_check. About 40 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';
import { NETWORK_PANEL, openNetworks } from './lib/rl_networks.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('looks');
const LOOK_KEY = 'gator-workbench-look-v1', BOTTOM_KEY = 'gator-workbench-bottom-v1', PICTURE_KEY = 'gator-workbench-circuit-picture-v1';
const RUN = '/fixture/looks/run';
const ID = '8b2325fb546f4df7b5a21341f9d23dcb';
const STATUS = { state: 'completed', run_id: 'fixture-run', mode: 'scratch', entry: 'start', provenance: 'mock', mock: true, worker_alive: false, run_dir: RUN,
  heartbeat_utc: '2026-10-03T15:15:05Z', stop_reason: 'budget_exhausted', error: null, active_workers: [], concurrency: 1, learner_updates: 0, first_feasible: null,
  budget: { max_evaluations: 1, max_launches: null, max_retries: 0, charged: 1, reserved: 0, in_flight: 0, completed: 1, failed: 0, released: 0, remaining: 0,
    launches: 1, retries: 0, cache_hits: 0, first_feasible: null },
  best_design: null, persistence: null, last_checkpoint_utc: null, paths: { run_dir: RUN }, connection: { overall: 'not_applicable' }, summary: null,
  manifest: { mode: 'scratch', mock: true, task_id: 'fixture_task:0000', seeds: { target_seed: 0 }, source_model: null, budgets: { max_evaluations: 1 },
    mock_notice: 'FIXTURE MOCK DATA: nothing was started.' } };
const TABLE = { table: 'evaluations', total_rows: 1, cutoff_commit_seq: 1,
  columns: ['run_id', 'evaluation_id', 'task_id', 'worker_id', 'phase', 'action_source', 'proposed_at', 'action'],
  rows: [{ run_id: ID, evaluation_id: 'ac07f01279ed4c28b08ea78fd1ef9036', task_id: 'mscr_ldo2_rgcn.baseline:e55a553bf64ec', worker_id: 0, phase: 'baseline',
    action_source: 'reset', proposed_at: '2026-10-03T15:15:01.076735+00:00', action: { input_pair_width: 0.5, mirror_pair_width: -0.25, tail_width: 0.125 } }] };

// The page's own colours, as it has them now: text / background pairs that must stay readable (WCAG AA, 4.5 : 1).
const PAIRS = [['--text', '--panel'], ['--muted', '--panel'], ['--accent', '--panel'], ['--bad', '--panel'], ['--warn', '--panel'], ['--ok', '--panel'],
  ['--text', '--bg'], ['--text', '--field'], ['--muted', '--field'], ['--text', '--button'], ['--text', '--head'], ['--text', '--card'], ['--text', '--sunk'],
  ['--muted', '--sunk'], ['--text', '--selected'], ['--text', '--hover'], ['--text', '--info-bg'], ['--text', '--warn-bg'], ['--text', '--bad-bg'],
  ['--text', '--code-bg'], ['--text', '--zebra'], ['--bad', '--bad-bg'], ['--ok', '--ok-bg'], ['--warn', '--busy-bg'],
  ['--neutral-text', '--neutral-bg'], ['--muted', '--na-bg'], ['--on-accent', '--accent-fill'], ['--on-accent', '--bad-fill'], ['--on-warn', '--warn-fill'],
  ['--param', '--param-head'], ['--probe', '--probe-head'], ['--spec', '--spec-head'], ['--probe', '--probe-chip'], ['--param', '--panel'],
  ['--probe', '--panel'], ['--spec', '--panel'], ['--unresolved', '--panel'], ['--text', '--cp-nmos'], ['--text', '--cp-pmos'], ['--text', '--cp-passive'],
  ['--on-accent', '--accent-fill']];
const COLOUR = `(v => { const c = document.createElement('canvas').getContext('2d'); c.fillStyle = '#123456'; c.fillStyle = v; const s = c.fillStyle;
  const m = s.startsWith('#') ? [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16)) : s.match(/[\\d.]+/g).slice(0, 3).map(Number); return m; })`;
const LUMINANCE = `(rgb => { const [r, g, b] = rgb.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; })`;
const contrasts = session => session.evaluate(`(() => { const css = getComputedStyle(document.documentElement), colour = ${COLOUR}, lum = ${LUMINANCE};
  return ${JSON.stringify(PAIRS)}.map(([fg, bg]) => { const a = lum(colour(css.getPropertyValue(fg).trim())), b = lum(colour(css.getPropertyValue(bg).trim()));
    return { pair: fg + ' on ' + bg, ratio: Math.round(100 * (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) / 100 }; }); })()`);
/** Every option of the page's selects, as the browser draws the open list from them: its text on its own background (record
 *  7.173, user: "fix the color issue of the drag down menu in night mode, it is hard to read"). */
const optionColours = session => session.evaluate(`(() => { const colour = ${COLOUR}, lum = ${LUMINANCE}, seen = new Map();
  for (const o of document.querySelectorAll('select option')) {
    const s = getComputedStyle(o), key = s.color + ' on ' + s.backgroundColor + (o.disabled ? ' (disabled)' : '');
    if (seen.has(key)) continue;
    const alpha = (s.backgroundColor.match(/[\\d.]+/g) ?? []).map(Number)[3] ?? 1, a = lum(colour(s.color)), b = lum(colour(s.backgroundColor));
    seen.set(key, { pair: key, opaque: alpha === 1, ratio: Math.round(100 * (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) / 100 });
  }
  return { editorOptions: document.querySelectorAll('table.editor select option').length, pairs: [...seen.values()] }; })()`);
const PROBES_TAB = `[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === 'measurements')`;
/** Visible boxes whose own background is light (a pastel left over from the light look). */
const lightBoxes = session => session.evaluate(`(() => { const lum = ${LUMINANCE}, found = new Set();
  for (const e of document.querySelectorAll('body *')) {
    if (e.closest('svg') || !e.checkVisibility?.()) continue;
    const m = getComputedStyle(e).backgroundColor.match(/[\\d.]+/g); if (!m) continue;
    const [r, g, b, a = 1] = m.map(Number); if (a < 0.5) continue;
    if (lum([r, g, b]) > 0.35) found.add(e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\\s+/).join('.') : ''));
  }
  return [...found].slice(0, 12); })()`);

await runChecks(browser, async () => {
  const meta = await (await fetch(new URL('api/meta', APP))).json();
  const starter = await starterConfig(APP);
  // saved with the two research labels retired in record 7.163: the page must drop them and keep the others
  const config = { schema_version: 'gator-workbench-config-v1', ...starter, run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, ...starter.run },
    research: { experiment_group: 'old-group', test_tasks: ['t1'], method_label: 'fixture-method' } };
  const leader = config.parameters.find(p => config.parameters.some(q => q.binding_group === p.variable_id));
  const tied = leader ? config.parameters.filter(p => p.binding_group === leader.variable_id).map(p => p.instance_path) : [];
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  let validated = null;                            // the configuration the page last sent to be validated
  await page.intercept(['*/api/runs/status*', '*/api/runs/table*', '*/api/config/validate'], params => {
    const url = new URL(params.request.url), name = url.pathname;
    if (name === '/api/config/validate') { try { validated = JSON.parse(params.request.postData).config; } catch { /* not JSON */ } return page.pass(params.requestId); }
    if (name === '/api/runs/status' && url.searchParams.get('run_dir') === RUN) return page.fulfil(params.requestId, 200, STATUS);
    if (name === '/api/runs/table' && url.searchParams.get('run_dir') === RUN) return page.fulfil(params.requestId, 200, { ...TABLE, table: url.searchParams.get('table') });
    return page.readOrRefuse(params, page.refused, { reads: true });
  }, { others: 'read' });
  await page.seed({ config, run: RUN, when: 'once' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors') && !!document.querySelector('header .tb-cell')`, 200));
  await sleep(1200);
  const theme = () => evaluate(`document.documentElement.dataset.theme`);
  const SWITCH = `document.querySelector('header button.look-switch')`;

  // ---- the look: Whiteprint first, the switch, kept, followed by pop-ups --------------------------------------------------
  check('a fresh browser opens in Whiteprint', await theme() === 'whiteprint');
  const button = await evaluate(`(() => { const b = ${SWITCH}; return b && { text: b.textContent.trim(), title: b.title, pressed: b.getAttribute('aria-pressed') }; })()`);
  check('the header has one look switch, an icon with its label kept for screen readers', button?.text === 'Switch look' && button.pressed === 'false', JSON.stringify(button));
  check("its tooltip starts with its label and names both looks", /^Switch look: now Whiteprint; press for Silicon Night\./.test(button?.title ?? ''), button?.title);
  const fonts = await evaluate(`({ body: getComputedStyle(document.body).fontFamily, h3: getComputedStyle(document.querySelector('h3')).fontFamily,
    number: getComputedStyle(document.querySelector('.right input.numeric') ?? document.body).fontFamily })`);
  check("Windows' own fonts: Segoe UI for text, Bahnschrift for headings, Consolas for numbers", fonts.body.includes('Segoe UI') && fonts.h3.includes('Bahnschrift') && fonts.number.includes('Consolas'), JSON.stringify(fonts));
  const frame = await evaluate(`(() => { const l = document.querySelector('.layout'); return { zones: (getComputedStyle(l).backgroundImage.match(/url\\(/g) ?? []).length, border: parseFloat(getComputedStyle(l, '::before').borderTopWidth) }; })()`);
  // (a 1.5 px border is drawn on whole device pixels: 1 px on a screen at 100 %)
  check('Whiteprint draws the sheet frame with its zone letters on all four sides', frame.zones === 4 && frame.border >= 1, JSON.stringify(frame));
  const light = await contrasts(page);
  const lowLight = light.filter(c => c.ratio < 4.5);
  check('Whiteprint: every text colour on its background reads at 4.5 : 1 or more', !lowLight.length, JSON.stringify(lowLight));
  await evaluate(`${PROBES_TAB}.click()`);          // the Probes table: its analysis column is a drop-down in each cell
  await sleep(300);
  const lightOptions = await optionColours(page);
  check('Whiteprint: every drop-down list draws its options on a solid background, readable at 4.5 : 1 or more (Probes cells too)',
    lightOptions.editorOptions > 0 && lightOptions.pairs.every(p => p.opaque && p.ratio >= 4.5), JSON.stringify(lightOptions));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === 'parameters').click()`);
  await sleep(300);
  await page.shot(path.join(out, 'looks-whiteprint.png'));

  await evaluate(`${SWITCH}.click()`);
  await sleep(300);
  check('the switch turns the page to Silicon Night', await theme() === 'silicon');
  check('...and says so to screen readers (pressed) and keeps the choice in this browser',
    await evaluate(`${SWITCH}.getAttribute('aria-pressed') === 'true' && localStorage.getItem('${LOOK_KEY}') === 'silicon'`));
  const dark = await contrasts(page);
  const lowDark = dark.filter(c => c.ratio < 4.5);
  check('Silicon Night: every text colour on its background reads at 4.5 : 1 or more', !lowDark.length, JSON.stringify(lowDark));
  await evaluate(`${PROBES_TAB}.click()`);
  await sleep(300);
  const darkOptions = await optionColours(page);
  check('Silicon Night: every drop-down list draws its options on a solid dark background in light text, at 4.5 : 1 or more (Probes cells too)',
    darkOptions.editorOptions > 0 && darkOptions.pairs.every(p => p.opaque && p.ratio >= 4.5), JSON.stringify(darkOptions));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === 'parameters').click()`);
  await sleep(300);
  check('Silicon Night: no light box is left on the page (Run status)', !(await lightBoxes(page)).length, JSON.stringify(await lightBoxes(page)));
  for (const tab of ['Data tables', 'Logs']) {        // (the Agent tab became a window on 2026-10-07, record 7.253: pop-ups are checked below)
    await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === ${JSON.stringify(tab)}).click()`);
    await sleep(700);
    const left = await lightBoxes(page);
    check(`Silicon Night: no light box is left on the page (${tab})`, !left.length, JSON.stringify(left));
  }
  await page.shot(path.join(out, 'looks-silicon.png'));
  await send('Page.reload');
  await page.until(`!!document.querySelector('.editors')`, 200);
  check('a reload keeps Silicon Night (set before the page draws)', await theme() === 'silicon');
  await sleep(800);
  await evaluate(`[...document.querySelectorAll('footer button')].find(b => b.textContent.trim().startsWith('Runs'))?.click()`, true);
  const target = await browser.window('GATOR - runs', { ms: 8000 }).catch(() => null);
  check('the Runs window opens', !!target);
  if (target) {
    const runs = await browser.attach(target);
    await sleep(600);
    check('a pop-up window takes the page\'s look when it opens', await runs.evaluate(`document.documentElement.dataset.theme`) === 'silicon');
    const leftInWindow = await lightBoxes(runs);
    check('Silicon Night: no light box in the Runs window', !leftInWindow.length, JSON.stringify(leftInWindow));
    await evaluate(`${SWITCH}.click()`);
    await sleep(300);
    check('...and follows the switch while it is open', await runs.evaluate(`document.documentElement.dataset.theme`) === 'whiteprint' && await theme() === 'whiteprint');
  }

  // ---- Research experiments (record 7.163) and no "Search method" (record 7.226) ------------------------------------------
  check('a saved configuration with the retired research labels loads without them, keeping the others',
    !!validated && !('experiment_group' in validated.research) && !('test_tasks' in validated.research) && validated.research.method_label === 'fixture-method', JSON.stringify(validated?.research));
  const research = await evaluate(`(() => { const d = [...document.querySelectorAll('.right details.panel')].find(x => x.querySelector(':scope > summary h3')?.textContent === 'Research experiments');
    if (!d) return null; d.open = true;
    const names = el => [...el.querySelectorAll(':scope > label')].map(l => l.firstChild?.textContent.trim());
    const fold = d.querySelector('details.transfer-study');
    return { shown: names(d), folded: fold && !fold.open, inside: fold ? [...fold.querySelectorAll('label')].map(l => l.firstChild?.textContent.trim()) : [] }; })()`);
  check('Research experiments shows Method label, Comparison pair ID and Budget checkpoints; Experiment group and Test tasks are gone',
    JSON.stringify(research?.shown) === JSON.stringify(['Method label', 'Comparison pair ID', 'Budget checkpoints']), JSON.stringify(research));
  check('...the six transfer-study labels wait in a closed "Transfer study" line', research?.folded === true
    && JSON.stringify(research.inside) === JSON.stringify(['Split', 'Generalization level', 'Training sources', 'Task order K', 'Pretrain seed (source)', 'Ablation labels']), JSON.stringify(research?.inside));
  // its heading as the modules' headings, its note in the name's tooltip (record 7.166)
  const heading = await evaluate(`(() => { const font = h => { const c = getComputedStyle(h); return [c.fontFamily, c.fontSize, c.fontWeight, c.textTransform, c.letterSpacing].join('|'); };
    const r = [...document.querySelectorAll('.right details.panel > summary h3')].find(h => h.textContent === 'Research experiments');
    const m = [...document.querySelectorAll('.right details.module > summary h3')].find(h => h.textContent === 'Run configuration');
    return r && m && { same: font(r) === font(m), title: r.title, summary: r.closest('summary').textContent,
      cursor: getComputedStyle(r).cursor, moduleCursor: getComputedStyle(m).cursor }; })()`);
  check('Research experiments is headed like the other modules, its note only in the tooltip of its name',
    !!heading && heading.same && heading.title.startsWith('Optional for a single run') && heading.summary === 'Research experiments', JSON.stringify(heading));
  // the hand over its name, as over the other modules' names: a press opens or closes it (record 7.169, user: "make the mouse
  // icon as click not with the questionmar[k]")
  check('...and the pointer over its name is the hand, not the help question mark, as over Run configuration\'s name',
    heading?.cursor === 'pointer' && heading.moduleCursor === 'pointer', JSON.stringify(heading && [heading.cursor, heading.moduleCursor]));
  const searchWords = await evaluate(`[...document.querySelectorAll('.right .module-body h3, .right .module-body label')].filter(e => (e.firstChild?.textContent ?? '').trim().toLowerCase() === 'search method').length`);
  check('"Search method" is said nowhere in Run configuration: SAC is the only search method (record 7.226)', searchWords === 0, String(searchWords));
  // the 0-to-1 reward boxes: number boxes with the backend's range, drawn without the browser's up/down arrows (record 7.171,
  // user: "remove the toggle for these 0 to 1 value boxes"); the pointer rests on the first one, its box focused, as when typing
  const BOUNDED = ['Worst hard-spec share', 'Objective bonus weight', 'Tightest-margin bonus weight'];
  const boxOf = name => `[...document.querySelectorAll('.right .module-body label')].find(l => l.firstChild?.textContent?.trim() === ${JSON.stringify(name)})?.querySelector('input')`;
  const spot = await evaluate(`(() => { const e = ${boxOf(BOUNDED[0])}; e.scrollIntoView({ block: 'center' }); e.focus(); const r = e.getBoundingClientRect();
    return { x: r.right - 12, y: r.top + r.height / 2 }; })()`);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: spot.x, y: spot.y });
  await sleep(200);
  // (the arrows are a pseudo-element getComputedStyle cannot read: the box's appearance is checked, the picture shows the rest)
  const bounded = await evaluate(`${JSON.stringify(BOUNDED)}.map(name => { const e = ${boxOf('NAME')}; return e && { name, type: e.type, min: e.min, max: e.max,
    appearance: getComputedStyle(e).appearance }; })`.replace('"NAME"', 'name'));
  check('the three 0-to-1 reward boxes keep the number range 0..1 and are drawn as plain text boxes (no up/down arrows)',
    bounded.every(b => b && b.type === 'number' && b.min === '0' && b.max === '1' && b.appearance === 'textfield'), JSON.stringify(bounded));
  await page.shot(path.join(out, 'looks-bounded-boxes.png'), `${boxOf(BOUNDED[0])}.closest('label')`, { scale: 2, pad: 4 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 5, y: 5 });
  await evaluate(`document.activeElement?.blur()`);

  // ---- the same page in both looks (record 7.162, user: "the day and night mode banner size is a bit different"): every box -----
  const BOXES = ['header', 'header .title-block', 'header .tb-cell', 'aside.left', 'main', 'aside.right', 'footer', 'footer > .tabs', '.editors > .tabs',
    '.editors > .tabs > button[data-editor="parameters"]', '.editors > .tabs > button[data-editor="targets"]', '.editors table.editor th[data-field]',
    'header button.run-main', 'header button.look-switch'];
  const boxes = () => evaluate(`${JSON.stringify(BOXES)}.map(s => { const e = document.querySelector(s); if (!e) return s + ': none'; const r = e.getBoundingClientRect();
    return s + ': ' + [r.left, r.top, r.width, r.height].map(v => Math.round(v * 10) / 10).join(','); })`);
  const outside = () => evaluate(`getComputedStyle(document.querySelector('header')).boxShadow.split(/,(?![^(]*\\))/).filter(s => s.trim() !== 'none' && !s.includes('inset')).length`);
  const lookNow = await theme();
  const first = await boxes(), outsideFirst = await outside();
  await evaluate(`${SWITCH}.click()`); await sleep(300);
  const second = await boxes(), outsideSecond = await outside();
  await evaluate(`${SWITCH}.click()`); await sleep(300);
  const moved = first.filter((b, i) => b !== second[i]).map((b, i) => `${b}  vs  ${second[first.indexOf(b)]}`);
  check('switching the look moves nothing: header, columns, bottom panel, tabs, table head and buttons stand exactly where they stood', !moved.length, JSON.stringify(moved));
  check('...and neither header draws outside its box (its rules are inset)', outsideFirst === 0 && outsideSecond === 0, `${outsideFirst} / ${outsideSecond}`);
  // one tab style in both looks (record 7.164): the editors' layer swatches, the chosen tab raised and underlined
  const tabStyle = () => evaluate(`(() => { const t = document.querySelector('.editors > .tabs > button[data-editor].active'), m = getComputedStyle(t, '::before'), b = getComputedStyle(t);
    return [m.backgroundImage.startsWith('repeating-linear-gradient'), m.borderRadius, b.boxShadow.includes('inset') && b.boxShadow.includes('-2px'), b.borderTopLeftRadius].join('|'); })()`);
  const tabsFirst = await tabStyle();
  await evaluate(`${SWITCH}.click()`); await sleep(300);
  const tabsSecond = await tabStyle();
  await evaluate(`${SWITCH}.click()`); await sleep(300);
  check('one tab style in both looks: a layer swatch on each editor tab, the chosen one raised and underlined', tabsFirst === tabsSecond && tabsFirst.startsWith('true|') && tabsFirst.includes('|true|'), `${tabsFirst} / ${tabsSecond}`);
  check('(the look is back as it was)', await theme() === lookNow);

  // ---- the title block ------------------------------------------------------------------------------------------------------
  const facts = await evaluate(`Object.fromEntries([...document.querySelectorAll('header .tb-cell')].map(c => [c.querySelector('.tb-k').textContent, c.querySelector('.tb-v').textContent]))`);
  check('the title block names the revision, the class and PDK, and the RL model label (no project name: record 7.159; no task name: record 7.182)',
    !('Project' in facts) && !('Task' in facts) && facts.Rev === '-' && facts['Class · PDK'] === `${config.circuit.circuit_class} · ${config.circuit.pdk_id}`
    && facts['RL model'] === config.project.task_name, JSON.stringify(facts));
  // The label is typed in the RL model window since record 7.265 ("Name of the new model"; in Run configuration until then).
  await openNetworks(page, browser);
  await page.setValue(`${NETWORK_PANEL}.querySelector('input.model-label')`, 'ota5-gat-a', { event: 'input' });
  await sleep(200);
  check('...the RL model cell follows the label typed in the RL model window', await evaluate(`[...document.querySelectorAll('header .tb-cell')].find(c => c.querySelector('.tb-k').textContent === 'RL model')?.querySelector('.tb-v').textContent`) === 'ota5-gat-a');
  await page.setValue(`${NETWORK_PANEL}.querySelector('input.model-label')`, '', { event: 'input' });
  await evaluate(`window.__checkRLWindow.close()`);
  const brand = await evaluate(`document.querySelector('header .tb-brand').title`);
  check('the version and the environment are one hover away, on the name', brand.startsWith('GATOR workbench ') && brand.includes(meta.version) && brand.includes('data-only outputs'), brand);

  // ---- the splitter ---------------------------------------------------------------------------------------------------------
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Run status').click()`);
  const foot = () => evaluate(`Math.round(document.querySelector('footer').getBoundingClientRect().height)`);
  const stored = () => evaluate(`JSON.parse(localStorage.getItem('${BOTTOM_KEY}') ?? 'null')`);
  const handle = await evaluate(`(() => { const r = document.querySelector('.splitter').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  const before = await foot();
  const mouse = (type, x, y, extra = {}) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', ...extra });
  await mouse('mousePressed', handle.x, handle.y, { clickCount: 1 });
  for (let i = 1; i <= 5; i++) { await mouse('mouseMoved', handle.x, handle.y - 30 * i, { buttons: 1 }); await sleep(25); }
  await mouse('mouseReleased', handle.x, handle.y - 150, { clickCount: 1 });
  await sleep(300);
  const dragged = await foot(), keptDrag = await stored();
  check('dragging the splitter up 150 px makes the bottom panel 150 px taller', Math.abs(dragged - before - 150) <= 3, `${before} -> ${dragged}`);
  check('...and the height is kept in this browser', keptDrag?.height === dragged && keptDrag.folded === false, JSON.stringify(keptDrag));
  const at = await evaluate(`(() => { const r = document.querySelector('.splitter').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  for (const count of [1, 2]) { await mouse('mousePressed', at.x, at.y, { clickCount: count }); await mouse('mouseReleased', at.x, at.y, { clickCount: count }); }
  await sleep(300);
  const folded = await foot();
  check('a double click folds the bottom panel down to its tab line', folded < 50 && !(await evaluate(`document.querySelector('.bottom-body').checkVisibility()`)), `${folded} px`);
  check('...kept in this browser, with the height for when it opens again', (await stored())?.folded === true && (await stored())?.height === dragged);
  await page.shot(path.join(out, 'looks-folded.png'));
  await send('Page.reload');
  await page.until(`!!document.querySelector('.editors')`, 200);
  await sleep(500);
  check('a reload keeps it folded', await foot() < 50);
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Logs').click()`);
  await sleep(300);
  check('pressing one of its tabs opens it again, at its height', Math.abs(await foot() - dragged) <= 2, `${await foot()} px`);
  await evaluate(`document.querySelector('.splitter').focus()`);
  const keyed = await foot();
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowUp', code: 'ArrowUp', windowsVirtualKeyCode: 38 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowUp', code: 'ArrowUp', windowsVirtualKeyCode: 38 });
  await sleep(200);
  check('the arrow keys move it from the keyboard (24 px a press)', Math.abs(await foot() - keyed - 24) <= 2, `${keyed} -> ${await foot()}`);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await sleep(200);
  check('...and Enter folds it', await foot() < 50);
  await evaluate(`localStorage.removeItem('${BOTTOM_KEY}')`);
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Run status').click()`);
  await page.viewport(1000, 900); await sleep(300);
  check('a narrow window has no splitter (its own layout keeps the heights)', !(await evaluate(`document.querySelector('.splitter').checkVisibility()`)));
  await page.viewport(1680, 1050); await sleep(300);

  // ---- each editor's colour, the Probe chips ----------------------------------------------------------------------------------
  const tabColours = await evaluate(`(() => { const css = getComputedStyle(document.documentElement), colour = ${COLOUR};
    const same = (a, b) => JSON.stringify(colour(a)) === JSON.stringify(colour(b));
    const tab = [...document.querySelectorAll('.editors > .tabs > button[data-editor]')];
    const active = tab.find(b => b.classList.contains('active'));
    const th = document.querySelector('.editors table.editor th');
    return { editors: tab.map(b => b.dataset.editor), active: active?.dataset.editor, ink: same(getComputedStyle(active).color, css.getPropertyValue('--param')),
      head: same(getComputedStyle(th).backgroundColor, css.getPropertyValue('--param-head')) }; })()`);
  check('the three editor tabs carry their editor, in tab order', JSON.stringify(tabColours.editors) === '["parameters","measurements","targets"]', JSON.stringify(tabColours));
  check("the active editor's tab and table header row take its colour (Parameters)", tabColours.ink && tabColours.head, JSON.stringify(tabColours));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.textContent.startsWith('Specs')).click()`);
  await sleep(300);
  const probes = config.measurements.map(m => m.measurement_id).filter(Boolean);
  const chips = await evaluate(`(() => { const p = document.querySelector('.fact.spec-probes'); return { ids: [...p.querySelectorAll('code.probe-id')].map(c => c.textContent), text: p.textContent }; })()`);
  check('the Specs line offers the Probe ids as Probe-coloured chips', JSON.stringify(chips.ids) === JSON.stringify(probes), JSON.stringify(chips.ids));
  check('...the line reads "Probes:" and the ids, a comma between them (its explanation in the tooltip, record 7.176)', chips.text === `Probes: ${probes.join(', ')}`, chips.text.slice(0, 160));
  check('the Specs table header row takes the Specs colour', await evaluate(`document.querySelector('.editors').dataset.editor === 'targets'`));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.textContent.startsWith('Parameters')).click()`);

  // ---- Data tables: one line per row -------------------------------------------------------------------------------------------
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Data tables').click()`);
  check('Data tables shows the FIXTURE row', await page.until(`!!document.querySelector('footer table.data-table td.id-cell')`, 50));
  await evaluate(`navigator.clipboard.writeText = text => { window.__copied = text; return Promise.resolve(); }`);
  const cells = await evaluate(`(() => { const t = document.querySelector('footer table.data-table'), row = t.querySelector('tbody tr'), td = [...row.children];
    const line = parseFloat(getComputedStyle(td[0]).lineHeight) || 16;
    return { ids: td.filter(c => c.classList.contains('id-cell')).length, title: td[0].title, height: Math.round(row.getBoundingClientRect().height), line: Math.round(line),
      cut: td[0].scrollWidth > td[0].clientWidth, phase: Math.round(td[4].getBoundingClientRect().height), json: td[7].className, time: td[6].className }; })()`);
  check('the four ids (worker_id too) are id cells, a long one ending in "...", the whole value in its tooltip', cells.ids === 4 && cells.cut && cells.title.startsWith(ID), JSON.stringify(cells));
  check('the row is one line high, the word "baseline" uncut', cells.height <= cells.line + 8 && cells.phase <= cells.line + 8, JSON.stringify(cells));
  check('a time keeps its width, a JSON value has a cell of its own', cells.time === 'time-cell' && cells.json === 'json-cell', JSON.stringify(cells));
  await evaluate(`document.querySelector('footer table.data-table td.id-cell').click()`);
  check('a click on an id copies the whole value', await evaluate(`window.__copied`) === ID);

  // ---- the circuit picture: folded at first like every block of the Project column; opened once, kept open ------------------
  check('the circuit picture starts folded into its heading line, like every block of the Project column',
    await evaluate(`(() => { const d = document.querySelector('.circuit-picture'); return !!d && !d.open; })()`));
  await evaluate(`document.querySelector('.circuit-picture > summary').click()`);
  await sleep(250);
  check('one click opens it, and it stays open in this browser', await evaluate(`document.querySelector('.circuit-picture').open && localStorage.getItem('${PICTURE_KEY}') === 'open'`));
  const picture = await evaluate(`(() => { const d = document.querySelector('.circuit-picture'); return d && { devices: d.querySelectorAll('.cp-dev').length,
    nets: d.querySelectorAll('.cp-net').length, names: [...d.querySelectorAll('.cp-dev text')].map(t => t.textContent), rails: d.querySelectorAll('.cp-net.supply, .cp-net.ground').length }; })()`);
  check('it draws the loaded circuit: devices, nets, supply and ground', !!picture && picture.devices >= 3 && picture.nets >= 3 && picture.rails >= 2, JSON.stringify(picture));
  check('...its devices named without the hierarchy they share when that is unambiguous', !!picture && picture.names.every(n => !n.includes('/')), JSON.stringify(picture?.names));
  if (leader) {
    const row = await evaluate(`(() => { const tr = [...document.querySelectorAll('.editors table.editor tbody tr')].find(t => [...t.querySelectorAll('input')].some(i => i.value === ${JSON.stringify(leader.variable_id)}));
      tr.scrollIntoView({ block: 'center' }); const r = tr.getBoundingClientRect(); return { x: r.left + 260, y: r.top + r.height / 2 }; })()`);
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: row.x, y: row.y });
    await sleep(250);
    const lit = await evaluate(`[...document.querySelectorAll('.circuit-picture .cp-dev.on title')].map(t => t.textContent.split(' · ')[0]).sort()`);
    const wanted = [leader.instance_path, ...tied].sort();
    check(`pointing at the row ${leader.variable_id} lights its device and the one tied to it`, JSON.stringify(lit) === JSON.stringify(wanted), `${JSON.stringify(lit)} vs ${JSON.stringify(wanted)}`);
    await page.shot(path.join(out, 'looks-picture-lit.png'), `document.querySelector('.circuit-picture')`, { scale: 2, pad: 4 });
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 5, y: 5 });
    await sleep(200);
    check('...and nothing stays lit once the pointer leaves', await evaluate(`document.querySelectorAll('.circuit-picture .cp-dev.on').length === 0`));
  } else check('the task has a tied pair to point at', false, 'no binding_group in the starter rows');
  await send('Page.reload');
  await page.until(`!!document.querySelector('.circuit-picture')`, 200);
  check('a reload keeps it open', await evaluate(`document.querySelector('.circuit-picture').open`));
  await evaluate(`document.querySelector('.circuit-picture > summary').click()`);
  await sleep(200);
  check('...and folding it is kept too', await evaluate(`!document.querySelector('.circuit-picture').open && localStorage.getItem('${PICTURE_KEY}') === 'closed'`));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
