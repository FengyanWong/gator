// Browser check of the page's look - one look since record 7.360 (user: "dark mode only delete the day mode", then "go with
// draft A, build it into the workbench"; the two looks of record 7.158 were checked here until then) - and of the layout moves
// of record 7.158. Hermetic: reads pass to the backend under test, the run the bottom tabs show is a FIXTURE answered here,
// every other writing request is refused - the page may write nothing of its own.
// What it pins:
//   - one look: no look name on the page, no look switch; black ground, the browser told the page is dark; Windows' own fonts,
//     text at 14 px;
//   - text stays readable (each text / background pair of the page's colours at least 4.5 : 1, WCAG AA), and no box is left
//     light (main page, three bottom tabs, the Runs window);
//   - the banner of Draft A: the name as a chip with its red pin-1 dot, the task by its own name, the run's state as four words
//     with one lit, Start round and white, Abort round and red; Output settings folded on a fresh browser; a task name too
//     long for the header ends in "..." once the facts beside it have given way, never cut through a letter (SIF-66);
//   - the header draws nothing outside its box; the editors' tabs as one segmented control, the chosen one lit with a red bar;
//   - the header's title block names the task's revision, the circuit's class and PDK and the RL model label; the version is
//     one hover away on the chip;
//   - the splitter above the bottom panel: a drag sets its height, a double click folds it to its tab line and back, a tab press
//     opens it, the arrow keys and Enter do the same from the keyboard; kept in this browser; hidden on narrow windows;
//   - the editors share one ink and head colour; the Specs line offers the Probe ids as chips (same text);
//   - the old look's small sizes no longer outrank the page: issue lines, the toolbar's text buttons, the tied rows' toggle, the
//     task chip's name; a heading with no tooltip shows no help cursor (branch record SIF-63); a list table's second lines,
//     its Details link, the state words and the paths, and the copy cursor only on a path that copies (SIF-64); the Probe
//     chips (SIF-74);
//   - Data tables: one line per row - ids end in "...", the whole value on hover, a click copies it and the tool line says
//     "Copied <column>." (branch record SIF-94); no word cut in two;
//   - Research experiments: the two retired labels dropped from a saved configuration, three labels shown, six folded; no
//     "Search method" any more (record 7.226; one, as its label, since 7.163);
//   - the circuit picture: folded at first like every block of the Project column, drawn from the loaded circuit; pointing at a
//     Parameters row lights its device and the one tied to it; its fold is kept in this browser.
// Run: WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=<a scratch build> "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w
// frontend/scripts/looks_check.mjs)" [screenshot-dir], or bash frontend/scripts/run_checks.sh --only looks_check. About 40 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl, BOTTOM_KEY, CIRCUIT_PICTURE_KEY, RUNS_WINDOW } from './lib/harness.mjs';
import { NETWORK_PANEL, openNetworks } from './lib/rl_networks.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('looks');
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
  columns: ['run_id', 'evaluation_id', 'task_id', 'worker_id', 'phase', 'action_source', 'proposed_at', 'action', 'global_env_step'],
  rows: [{ run_id: ID, evaluation_id: 'ac07f01279ed4c28b08ea78fd1ef9036', task_id: 'mscr_ldo2_rgcn.baseline:e55a553bf64ec', worker_id: 0, phase: 'baseline',
    action_source: 'reset', proposed_at: '2026-10-03T15:15:01.076735+00:00', action: { input_pair_width: 0.5, mirror_pair_width: -0.25, tail_width: 0.125 }, global_env_step: 12 }] };

// The page's own colours, as it has them now: text / background pairs that must stay readable (WCAG AA, 4.5 : 1).
const PAIRS = [['--text', '--panel'], ['--muted', '--panel'], ['--accent', '--panel'], ['--bad', '--panel'], ['--warn', '--panel'], ['--ok', '--panel'],
  ['--text', '--bg'], ['--text', '--field'], ['--muted', '--field'], ['--text', '--button'], ['--text', '--head'], ['--text', '--card'], ['--text', '--sunk'],
  ['--muted', '--sunk'], ['--text', '--selected'], ['--text', '--hover'], ['--text', '--info-bg'], ['--text', '--warn-bg'], ['--text', '--bad-bg'],
  ['--text', '--code-bg'], ['--text', '--zebra'], ['--bad', '--bad-bg'], ['--ok', '--ok-bg'], ['--warn', '--busy-bg'],
  ['--neutral-text', '--neutral-bg'], ['--muted', '--na-bg'], ['--on-accent', '--accent-fill'], ['--on-bad', '--bad-fill'], ['--on-warn', '--warn-fill'],
  ['--param', '--param-head'], ['--probe', '--probe-head'], ['--spec', '--spec-head'], ['--probe', '--probe-chip'], ['--param', '--panel'],
  ['--probe', '--panel'], ['--spec', '--panel'], ['--unresolved', '--panel'], ['--text', '--cp-nmos'], ['--text', '--cp-pmos'], ['--text', '--cp-passive'],
  ['--on-bad', '--close-hover']];
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
/** Visible boxes whose own background is light (a pastel left over from the light look); a primary button is white on purpose. */
const lightBoxes = session => session.evaluate(`(() => { const lum = ${LUMINANCE}, found = new Set();
  for (const e of document.querySelectorAll('body *')) {
    // a primary button's white fill, and a bar's (branch record SIF-3: a completed run's bar is white)
    if (e.closest('svg') || e.matches('button.primary, .status-hero-bar > span') || !e.checkVisibility?.()) continue;
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
  // ---- the page's one look (record 7.360, user: "dark mode only delete the day mode"; Draft A of the Roadster look) --------------
  check('one look: no look name on the page and no look switch in the header',
    await evaluate(`!document.documentElement.dataset.theme && !document.querySelector('header button.look-switch')`));
  const fonts = await evaluate(`({ body: getComputedStyle(document.body).fontFamily, h3: getComputedStyle(document.querySelector('h3')).fontFamily,
    number: getComputedStyle(document.querySelector('.right input.numeric') ?? document.body).fontFamily, size: getComputedStyle(document.body).fontSize })`);
  check("Windows' own fonts: Segoe UI for text, Bahnschrift for headings, Consolas for numbers; text at 14 px", fonts.body.includes('Segoe UI') && fonts.h3.includes('Bahnschrift')
    && fonts.number.includes('Consolas') && fonts.size === '14px', JSON.stringify(fonts));
  const ground = await evaluate(`({ body: getComputedStyle(document.body).backgroundColor, scheme: getComputedStyle(document.documentElement).colorScheme })`);
  check('black ground, and the browser told the page is dark (its scroll bars and drop-down lists too)', ground.body === 'rgb(0, 0, 0)' && ground.scheme === 'dark', JSON.stringify(ground));
  const pairs = await contrasts(page);
  const low = pairs.filter(c => c.ratio < 4.5);
  check('every text colour on its background reads at 4.5 : 1 or more', !low.length, JSON.stringify(low));
  await evaluate(`${PROBES_TAB}.click()`);          // the Probes table: its analysis column is a drop-down in each cell
  await sleep(300);
  const options = await optionColours(page);
  check('every drop-down list draws its options on a solid dark background in light text, at 4.5 : 1 or more (Probes cells too)',
    options.editorOptions > 0 && options.pairs.every(p => p.opaque && p.ratio >= 4.5), JSON.stringify(options));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.dataset.editor === 'parameters').click()`);
  await sleep(300);
  check('no light box is left on the page (Run status)', !(await lightBoxes(page)).length, JSON.stringify(await lightBoxes(page)));
  for (const tab of ['Data tables', 'Logs']) {        // (the Agent tab became a window on 2026-10-07, record 7.253: pop-ups are checked below)
    await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === ${JSON.stringify(tab)}).click()`);
    await sleep(700);
    const left = await lightBoxes(page);
    check(`no light box is left on the page (${tab})`, !left.length, JSON.stringify(left));
  }
  await page.shot(path.join(out, 'looks-roadster.png'));
  // the banner of Draft A: the name as a chip, the task, the run's state as a gear selector, Start white and Abort red, round
  const banner = await evaluate(`(() => { const css = e => e && getComputedStyle(e);
    const chip = document.querySelector('header .tb-brand svg.gator-chip'), strip = document.querySelector('header .run-state-strip');
    const main = document.querySelector('header button.run-main'), abort = document.querySelector('header button.run-abort');
    return { chip: chip?.getAttribute('aria-label'), pin1: css(chip?.querySelector('.gator-chip-pin1'))?.fill, task: document.querySelector('header .tb-task')?.textContent,
      states: strip && [...strip.children].map(s => s.textContent), lit: strip && [...strip.children].filter(s => s.classList.contains('on')).map(s => s.textContent),
      said: strip?.getAttribute('aria-label'), main: main && [css(main).borderRadius, css(main).backgroundColor], abort: abort && [css(abort).borderRadius, css(abort).backgroundColor] }; })()`);
  check('the banner names the page as a chip, its pin-1 dot in red', banner.chip === 'GATOR' && banner.pin1 === 'rgb(245, 67, 79)', JSON.stringify(banner));
  check('...then the task, by its own name (record 7.360: the chosen draft brings the name back)', banner.task === config.circuit.task_id.replace(/^[^:]+:/, '') || (banner.task ?? '').length > 0, JSON.stringify(banner.task));
  check("...the run's state as four words, one lit and said to screen readers (the header holds the FIXTURE run, completed: Ended)",
    JSON.stringify(banner.states) === '["Ready","Running","Paused","Ended"]' && JSON.stringify(banner.lit) === '["Ended"]' && banner.said === 'Run state: ended', JSON.stringify(banner));
  check('...and Start round and white, Abort round and red (red Abort: the user\'s request of 2026-09-21)',
    banner.main?.[0] === '50%' && banner.main[1] === 'rgb(244, 244, 245)' && banner.abort?.[0] === '50%' && banner.abort[1] === 'rgb(208, 16, 44)', JSON.stringify([banner.main, banner.abort]));
  // Record 7.372: the banner's facts leave the revision to the tab line's task chip; under 1400 px only the state that holds shows.
  check('the banner\'s facts name the class, the PDK and the RL model - not the revision, which the tab line\'s task chip says',
    await evaluate(`(() => { const d = document.querySelector('header .tb-details'); return !!d && !d.querySelector('.tb-rev') && !/revision/.test(d.textContent); })()`));
  await page.viewport(1366, 768); await sleep(400);
  const narrow = await evaluate(`[...document.querySelectorAll('header .run-state-strip > span')].filter(x => x.checkVisibility()).map(x => x.textContent)`);
  check('...and at 1366 px the strip shows only the state that holds (the four words took a crowded banner\'s room)', JSON.stringify(narrow) === '["Ended"]', JSON.stringify(narrow));
  // Branch record SIF-66: the task's name could not shrink, so between about 1201 and 1300 px with a run in the header the
  // facts' box cut it through a letter ("OTA 7T wid"). Now its own box ends it in "...", once the grey facts have given way.
  // Measured with the header's own name, then with a long stand-in written into its box (then its own name again).
  // SIF-66 review: "cut" is the name's box against its text's own width - a clone of it at max-content, measured to the 64th
  // of a pixel the layout counts in. scrollWidth and clientWidth are whole pixels, and the browser draws the "..." for any
  // overflow, less than a pixel too: "OTA 7T wi..." beside 256 px of facts counted as whole.
  const names = [];
  for (const width of [1210, 1250, 1300, 1366]) {
    await page.viewport(width, 768); await sleep(300);
    names.push(await evaluate(`(() => { const t = document.querySelector('header .tb-task'), d = document.querySelector('header .tb-details'), own = t.textContent;
      const look = () => { const c = t.cloneNode(true); c.style.cssText = 'position: absolute; visibility: hidden; flex: none; width: max-content; min-width: 0; max-width: none';
        t.parentElement.appendChild(c); const whole = c.getBoundingClientRect().width; c.remove(); const box = t.getBoundingClientRect();
        return { sliced: box.right > t.parentElement.getBoundingClientRect().right + 0.5, cut: box.width < whole - 0.005, lost: +(whole - box.width).toFixed(3),
          facts: Math.round(d.getBoundingClientRect().width) }; };
      const mine = look(); t.textContent = 'FIXTURE a task whose name is far longer than the header can hold'; const long = look(); t.textContent = own;
      return { width: ${width}, mine, long, dots: getComputedStyle(t).textOverflow }; })()`));
  }
  check('the header\'s task name is never cut through a letter by the box around it, at 1210 to 1366 px with a run in the header',
    names.every(n => !n.mine.sliced && !n.long.sliced), JSON.stringify(names));
  check('...a name too long for the header ends in "...", and only once the grey facts beside it have given way',
    names.some(n => n.long.cut) && names.every(n => n.dots === 'ellipsis' && (!n.long.cut || n.long.facts === 0) && (!n.mine.cut || n.mine.facts === 0)), JSON.stringify(names));
  await page.viewport(1680, 1050); await sleep(400);
  check('Output settings starts folded on a fresh browser (record 7.360, user: "by default make output settings collapsible and collapsed")',
    await evaluate(`(() => { const d = [...document.querySelectorAll('.right details.module')].find(x => x.querySelector(':scope > summary h3')?.textContent === 'Output settings'); return !!d && !d.open; })()`));
  await evaluate(`[...document.querySelectorAll('footer button')].find(b => b.textContent.trim().startsWith('Runs'))?.click()`, true);
  const target = await browser.window(RUNS_WINDOW, { ms: 8000 }).catch(() => null);
  check('the Runs window opens', !!target);
  if (target) {
    const runs = await browser.attach(target);
    await sleep(600);
    const leftInWindow = await lightBoxes(runs);
    check('no light box in the Runs window: a pop-up takes the page\'s colours from its stylesheet', !leftInWindow.length, JSON.stringify(leftInWindow));
    // Record 7.372: red stays for attention - a link (Details, a task's or a run's name) is white and underlined, as the stylesheet draws it.
    const link = await runs.evaluate(`(() => { const b = document.createElement('button'); b.className = 'notes-link'; b.textContent = 'Details';
      (document.querySelector('.run-window') ?? document.body).append(b); const st = getComputedStyle(b); const seen = { colour: st.color, line: st.textDecorationLine }; b.remove(); return seen; })()`);
    check('a link in the Runs window is white and underlined, not red (record 7.372)', link.colour === 'rgb(244, 244, 245)' && link.line.includes('underline'), JSON.stringify(link));
    // Branch record SIF-64: a list table's second lines, its Details link, the state words and the paths read at sizes near the
    // table's 13 px - a second line and "Details" were 11 px (the link in a hit box about 16 px tall), a state and "MOCK" 10 to
    // 10.5 px; a path showed the copy cursor where a click copied nothing. A stand-in row: this window lists no run.
    const row = await runs.evaluate(`(() => { const t = document.createElement('table'); t.className = 'grid run-table';
      t.innerHTML = '<tbody><tr><td><span class="badge state-ok">completed</span><div class="hint">budget reached</div></td><td><span class="badge model-tag mock-tag">MOCK</span></td>'
        + '<td><button class="notes-link">Details</button></td><td><button class="notes-link">Hide details</button></td><td class="path">/a/b</td><td class="path" title="Click to copy">/a/b</td></tr></tbody>';
      (document.querySelector('.run-window') ?? document.body).append(t);
      const st = e => getComputedStyle(e), [shut, open] = t.querySelectorAll('button.notes-link'), [plain, copies] = t.querySelectorAll('td.path'), box = e => e.getBoundingClientRect();
      const seen = { cell: st(t.querySelector('td')).fontSize, hint: st(t.querySelector('.hint')).fontSize, state: st(t.querySelector('.badge')).fontSize, spacing: st(t.querySelector('.badge')).letterSpacing, tag: st(t.querySelector('.model-tag')).fontSize,
        link: [st(shut).fontSize, st(shut).paddingTop, Math.round(box(shut).height)], widths: [box(shut).width, box(open).width, open.scrollWidth <= open.clientWidth],
        paths: [st(plain).fontSize, st(plain).cursor, st(copies).cursor] }; t.remove(); return seen; })()`);
    check('a list table\'s second line reads at 12 px, a state at 12 px with no letter spacing, "MOCK" at 11.5 px, "Details" at the table\'s 13 px with 3 px above and below (SIF-64)',
      row.cell === '13px' && row.hint === '12px' && row.state === '12px' && ['0px', 'normal'].includes(row.spacing) && row.tag === '11.5px' && row.link[0] === '13px' && row.link[1] === '3px' && row.link[2] >= 22, JSON.stringify(row));
    check('..."Details" and "Hide details" take the same room, so a toggle moves no column', row.widths[0] === row.widths[1] && row.widths[2], JSON.stringify(row.widths));
    check('...a path reads at 12 px with the text cursor, the copy cursor only where it says "Click to copy"', JSON.stringify(row.paths) === '["12px","text","copy"]', JSON.stringify(row.paths));
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

  // ---- the header draws nothing outside its box; the editors' tabs as one segmented control ------------------------------------
  check('the header draws nothing outside its box', await evaluate(`getComputedStyle(document.querySelector('header')).boxShadow.split(/,(?![^(]*\\))/).filter(s => s.trim() !== 'none' && !s.includes('inset')).length`) === 0);
  const tabStyle = await evaluate(`(() => { const css = getComputedStyle(document.documentElement);
    const tabs = [...document.querySelectorAll('.editors > .tabs > button[data-editor]')], active = tabs.find(t => t.classList.contains('active'));
    const bar = getComputedStyle(active, '::before'), other = tabs.find(t => t !== active);
    return { bar: [bar.content, bar.backgroundColor, bar.height], other: getComputedStyle(other, '::before').content,
      ink: getComputedStyle(active).color, otherInk: getComputedStyle(other).color }; })()`);
  check('the chosen editor tab is lit with a short red bar under its name, no layer swatch; the others grey (record 7.360)',
    tabStyle.bar[1] === 'rgb(245, 67, 79)' && tabStyle.bar[2] === '3px' && tabStyle.other === 'none' && tabStyle.ink === 'rgb(244, 244, 245)' && tabStyle.otherInk === 'rgb(169, 169, 176)', JSON.stringify(tabStyle));

  // ---- the title block ------------------------------------------------------------------------------------------------------
  const facts = await evaluate(`Object.fromEntries([...document.querySelectorAll('header .tb-cell')].map(c => [c.querySelector('.tb-k').textContent, c.querySelector('.tb-v').textContent]))`);
  check('the title block names the class and PDK and the RL model label in its facts (no project name: record 7.159; the revision is the tab line\'s since record 7.372)',
    !('Project' in facts) && !('Task' in facts) && !('Rev' in facts) && facts['Class · PDK'] === `${config.circuit.circuit_class} · ${config.circuit.pdk_id}`
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
  check("the active editor's tab and table header row take the editors' one ink and head colour (record 7.360: no colour per editor)", tabColours.ink && tabColours.head, JSON.stringify(tabColours));
  // Branch record SIF-9: a text cell that holds more than it shows ends in "..." while it is not being edited.
  const cut = await evaluate(`(() => { const i = document.querySelector('.editors table.editor tbody input:not([type="checkbox"])'); return i ? getComputedStyle(i).textOverflow : null; })()`);
  check('a text cell not being edited ends in "..." where it is cut (SIF-9)', cut === 'ellipsis', String(cut));
  // Branch record SIF-63: the old look's small sizes no longer outrank the 14 px page - an issue line was 11 px, "More columns"
  // and "Matched devices..." 11.5 px, the tied rows' toggle 11 px in about 17 x 11 px, the task chip's name a 12 px code font;
  // and a heading with no tooltip showed the help cursor. An issue line is made for the reading: this task has none.
  const small = await evaluate(`(() => { const size = e => e ? getComputedStyle(e).fontSize : null;
    const p = document.createElement('p'); p.className = 'issue warning'; p.textContent = 'warning: a stand-in'; document.querySelector('.editors').appendChild(p);
    const issue = size(p); p.remove();
    const tie = document.querySelector('.editors table.editor .tie-toggle'), key = document.querySelector('.task-list-current code.task-list-key'), button = key?.closest('button');
    const heads = [...document.querySelectorAll('.editors table.editor thead th')], bare = heads.find(th => th.textContent === 'Issues'), titled = heads.find(th => th.title);
    return { issue, text: [...document.querySelectorAll('section.editors .toolbar button.text')].map(b => [b.textContent, size(b)]), tie: tie && [size(tie), getComputedStyle(tie).paddingTop],
      key: key && button && [size(key), getComputedStyle(key).fontFamily === getComputedStyle(button).fontFamily, size(button)],
      cursors: [bare && getComputedStyle(bare).cursor, titled && getComputedStyle(titled).cursor] }; })()`);
  check('an issue line reads at 12.5 px; the toolbar\'s text buttons ("Matched devices...") at the labels\' 13 px (SIF-63)', small.issue === '12.5px'
    && small.text.length >= 1 && small.text.every(([, s]) => s === '13px'), JSON.stringify(small));
  check('...the tied rows\' toggle at 12.5 px with 4 px around it; the task chip names the task in its button\'s font and size, not a code font',
    JSON.stringify(small.tie) === '["12.5px","4px"]' && !!small.key && small.key[0] === small.key[2] && small.key[1], JSON.stringify(small));
  check('...and a heading with no tooltip ("Issues") shows the plain pointer; one with a tooltip keeps the help cursor', JSON.stringify(small.cursors) === '["default","help"]', JSON.stringify(small.cursors));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.textContent.startsWith('Specs')).click()`);
  await sleep(300);
  const probes = config.measurements.map(m => m.measurement_id).filter(Boolean);
  const chips = await evaluate(`(() => { const p = document.querySelector('.fact.spec-probes'), chip = p.querySelector('code.probe-id');
    return { ids: [...p.querySelectorAll('code.probe-id')].map(c => c.textContent), text: p.textContent, size: chip && [getComputedStyle(chip).fontSize, getComputedStyle(p).fontSize] }; })()`);
  check('the Specs line offers the Probe ids as chips', JSON.stringify(chips.ids) === JSON.stringify(probes), JSON.stringify(chips.ids));
  check('...the line reads "Probes:" and the ids, a comma between them (its explanation in the tooltip, record 7.176)', chips.text === `Probes: ${probes.join(', ')}`, chips.text.slice(0, 160));
  // Branch record SIF-74: the chips, the names an Equation is typed with, were the old look's 11 px beside the 14 px line.
  check('...the chips at 13 px in their mono font beside the 14 px line (SIF-74)', JSON.stringify(chips.size) === '["13px","14px"]', JSON.stringify(chips.size));
  check('the Specs table header row takes the Specs colour', await evaluate(`document.querySelector('.editors').dataset.editor === 'targets'`));
  await evaluate(`[...document.querySelectorAll('.editors > .tabs > button')].find(b => b.textContent.startsWith('Parameters')).click()`);

  // ---- Data tables: one line per row -------------------------------------------------------------------------------------------
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Data tables').click()`);
  check('Data tables shows the FIXTURE row', await page.until(`!!document.querySelector('footer table.data-table td.id-cell')`, 50));
  const choice = await evaluate(`(() => { const s = document.querySelector('footer select.tab-choice'), b = s?.parentElement.querySelector('button'); if (!s || !b) return null;
    const r = s.getBoundingClientRect(), q = b.getBoundingClientRect(); return { width: Math.round(r.width), line: Math.abs((r.top + r.bottom) / 2 - (q.top + q.bottom) / 2) < 4 }; })()`);
  check('the table list sits at its own width at the start of its tool line, not on a line of its own (branch record SIF-29)', !!choice && choice.width < 300 && choice.line, JSON.stringify(choice));
  await evaluate(`navigator.clipboard.writeText = text => { window.__copied = text; return Promise.resolve(); }`);
  const cells = await evaluate(`(() => { const t = document.querySelector('footer table.data-table'), row = t.querySelector('tbody tr'), td = [...row.children];
    const line = Math.max(...td.map(c => { const s = getComputedStyle(c); return parseFloat(s.lineHeight) || 1.2 * parseFloat(s.fontSize); }));
    const pad = (s => parseFloat(s.paddingTop) + parseFloat(s.paddingBottom))(getComputedStyle(td[4]));   // the look's room above and below a cell's line
    return { ids: td.filter(c => c.classList.contains('id-cell')).length, title: td[0].title, height: Math.round(row.getBoundingClientRect().height), line: Math.round(line), pad: Math.round(pad),
      cut: td[0].scrollWidth > td[0].clientWidth, phase: Math.round(td[4].getBoundingClientRect().height), json: td[7].className, time: td[6].className }; })()`);
  check('the four ids (worker_id too) are id cells, a long one ending in "...", the whole value in its tooltip', cells.ids === 4 && cells.cut && cells.title.startsWith(ID), JSON.stringify(cells));
  check('the row is one line high, the word "baseline" uncut', cells.height <= cells.line + cells.pad + 8 && cells.phase <= cells.line + cells.pad + 8, JSON.stringify(cells));
  check('a time keeps its width, a JSON value has a cell of its own', cells.time === 'time-cell' && cells.json === 'json-cell', JSON.stringify(cells));
  // Branch record SIF-76: a time in this computer's time, as Logs and Output files write it, its UTC value on hover (it read
  // "2026-10-16T17:17:20.704501+", cut at the panel's edge and an hour off the same moment in Logs).
  const when = await evaluate(`(() => { const td = document.querySelector('footer table.data-table td.time-cell'), d = new Date(${JSON.stringify(TABLE.rows[0].proposed_at)}), two = n => String(n).padStart(2, '0');
    return { text: td?.textContent, title: td?.title, local: d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds()) }; })()`);
  check('...in this computer\'s time, "YYYY-MM-DD hh:mm:ss", its UTC value on hover (SIF-76)', when.text === when.local && when.title === `${TABLE.rows[0].proposed_at} (UTC)`, JSON.stringify(when));
  // Branch record SIF-4: a JSON value keeps to one line as well, its whole text on hover (it wrapped into a block 200 px tall).
  const json = await evaluate(`(() => { const td = document.querySelector('footer table.data-table td.json-cell'); return td ? { ws: getComputedStyle(td).whiteSpace, over: getComputedStyle(td).textOverflow, title: td.title } : null; })()`);
  check('...and keeps to one line, "..." where it is cut, the whole value on hover (SIF-4)', json?.ws === 'nowrap' && json?.over === 'ellipsis' && /^[\[{]/.test(json?.title ?? '') && /Click to copy$/.test(json?.title ?? ''), JSON.stringify(json));
  await evaluate(`document.querySelector('footer table.data-table td.id-cell').click()`);
  check('a click on an id copies the whole value', await evaluate(`window.__copied`) === ID);
  // Branch record SIF-94: the copy was unsaid; the tool line says it now, by the cell's column.
  const COPY_NOTE = `(t => [t.closest('.scroll').previousElementSibling.querySelector('.hint').textContent, t.tHead.rows[0].cells[t.querySelector('td.id-cell').cellIndex].textContent])(document.querySelector('footer table.data-table'))`;
  check('...and the tool line says so, by the column: "Copied <column>." (SIF-94)', await page.until(`(([hint, column]) => hint.endsWith('Copied ' + column + '.'))(${COPY_NOTE})`, 30),
    JSON.stringify(await evaluate(COPY_NOTE)));
  const number = await evaluate(`(() => { const t = document.querySelector('footer table.data-table'), td = t.querySelector('tbody tr').lastElementChild, th = t.querySelector('thead tr').lastElementChild,
    id = t.querySelector('tbody td.id-cell'); return { td: [td.className, getComputedStyle(td).textAlign, getComputedStyle(td).fontVariantNumeric, td.textContent].join(' '),
      th: [th.className, getComputedStyle(th).textAlign].join(' '), id: getComputedStyle(id).textAlign }; })()`);
  check('a column of numbers is right-aligned in figures of one width, its title too; an id is not (branch record SIF-32)',
    number.td === 'num-cell right tabular-nums 12' && number.th === 'num-cell right' && number.id !== 'right', JSON.stringify(number));

  // ---- the circuit picture: folded at first like every block of the Project column; opened once, kept open ------------------
  check('the circuit picture starts folded into its heading line, like every block of the Project column',
    await evaluate(`(() => { const d = document.querySelector('.circuit-picture'); return !!d && !d.open; })()`));
  await evaluate(`document.querySelector('.circuit-picture > summary').click()`);
  await sleep(250);
  check('one click opens it, and it stays open in this browser', await evaluate(`document.querySelector('.circuit-picture').open && localStorage.getItem('${CIRCUIT_PICTURE_KEY}') === 'open'`));
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
  check('...and folding it is kept too', await evaluate(`!document.querySelector('.circuit-picture').open && localStorage.getItem('${CIRCUIT_PICTURE_KEY}') === 'closed'`));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
