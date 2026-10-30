// Browser check of record 7.218 - fewer boxes inside boxes (user: "work on fewer boxes inside boxes"). Hermetic: reads pass to
// the backend under test, every writing request is refused.
// What it pins (one look since record 7.360): a callout inside a panel or a window has no frame of its own - a rule at its left sets it
// off - and only a status keeps its faint fill (blocker, warning, MOCK / REAL, a test result); a callout inside a callout has
// no rule of its own; the MOCK banner between the header and the columns keeps its frame; the page's own MOCK note - under the
// editors' toolbar, with the task's other lines, since record 7.362 (the Project column until then) - is drawn so.
// How: most callouts show only in a particular state (an import to confirm, a blocking issue, a test result), so
// one of each kind is placed among the task's lines in the editors' panel and measured there; the stylesheet decides how each
// one is drawn.
// Run: bash frontend/scripts/run_checks.sh --only callouts_check. About 10 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('callouts');
// class names, and whether the kind keeps a fill (a status) or has none (a neutral callout); a scoped one with its window
// (The Agent tab's own callouts - encoder ideas, selected rows, provisional values - went with its agent on 2026-10-06, record 7.226.)
const KINDS = [['note', false], ['confirm', false], ['guidance', false], ['matched-devices', false],
  ['calibration-ready', false], ['connection-add', false, 'connection-window'], ['blocker', true], ['status-line level-ok', true], ['status-line level-error', true],
  ['copy-warning', true, 'virtuoso-window'], ['mock', true], ['real', true], ['settings-problem', true]];

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  await page.intercept(['*/api/config/validate'], params => page.pass(params.requestId), { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors .task-status .mock') && !!document.querySelector('.editors table.editor tbody tr')`, 200));
  await sleep(800);
  const measure = () => evaluate(`(() => {
    const host = document.querySelector('section.panel.editors .task-status');     // the task's lines (record 7.362)
    host.querySelector('.fixture-callouts')?.remove();
    const box = document.createElement('div'); box.className = 'fixture-callouts'; host.append(box);
    const kinds = ${JSON.stringify(KINDS)};
    for (const [name, , scope] of kinds) {
      const holder = scope ? Object.assign(document.createElement('div'), { className: scope }) : box;
      if (scope) box.append(holder);
      holder.append(Object.assign(document.createElement('div'), { className: name, textContent: 'FIXTURE ' + name }));
    }
    const outer = Object.assign(document.createElement('div'), { className: 'note', textContent: 'FIXTURE outer' });
    outer.append(Object.assign(document.createElement('div'), { className: 'confirm nested', textContent: 'FIXTURE inner' })); box.append(outer);
    box.append(Object.assign(document.createElement('div'), { className: 'banner mock', textContent: 'FIXTURE banner' }));
    const alpha = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return 1; const p = m[1].split(/[ ,\\/]+/).filter(Boolean); return p.length > 3 ? parseFloat(p[3]) : 1; };
    const read = e => { const s = getComputedStyle(e); return { top: parseFloat(s.borderTopWidth), right: parseFloat(s.borderRightWidth), bottom: parseFloat(s.borderBottomWidth),
      left: parseFloat(s.borderLeftWidth), fill: alpha(s.backgroundColor) > 0.02 }; };
    const result = {};
    for (const [name] of kinds) result[name] = read(box.querySelector('.' + name.split(' ').join('.')));
    result.nested = read(box.querySelector('.confirm.nested'));
    result.banner = read(box.querySelector('.banner.mock'));
    const mock = [...document.querySelectorAll('section.panel.editors .task-status .mock')].find(e => !box.contains(e));
    result.pageMock = mock ? read(mock) : null;
    box.remove();
    return result; })()`);
  for (const look of ['roadster']) {              // one look since record 7.360 (two until then, each checked here)
    const seen = await measure();
    const framed = KINDS.filter(([name]) => { const b = seen[name]; return !b || b.top || b.right || b.bottom || b.left < 3; }).map(([name]) => name);
    check(`(${look}) every kind of callout has a rule at its left and no frame (${KINDS.length} kinds)`, framed.length === 0, JSON.stringify(framed.map(n => [n, seen[n]])));
    const fills = KINDS.filter(([name, status]) => seen[name] && seen[name].fill !== status).map(([name]) => name);
    check(`(${look}) only a status keeps its fill: blocker, test result, warning, MOCK, REAL, settings problem`, fills.length === 0, JSON.stringify(fills.map(n => [n, seen[n]])));
    check(`(${look}) a callout inside a callout has no rule of its own`, seen.nested.left === 0 && !seen.nested.top && !seen.nested.fill, JSON.stringify(seen.nested));
    check(`(${look}) the MOCK banner between the header and the columns keeps its frame`, seen.banner.top >= 1 && seen.banner.right >= 1 && seen.banner.bottom >= 1, JSON.stringify(seen.banner));
    check(`(${look}) the page's own MOCK note under the editors' toolbar (record 7.362) is drawn so: a rule and its fill, no frame`, !!seen.pageMock && seen.pageMock.left >= 3 && !seen.pageMock.top && !seen.pageMock.right
      && !seen.pageMock.bottom && seen.pageMock.fill, JSON.stringify(seen.pageMock));
    await page.shot(path.join(out, `callouts-${look}.png`), `document.querySelector('section.panel.editors')`);
  }
  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
