// Browser check of record 7.188 - the crash panel: a failure to draw the page shows what broke and the ways out (Undo the last
// change, Export JSON, Reload; an empty start when there is no Undo) instead of a blank page. Hermetic: reads pass to the backend
// under test, validation is answered here, every writing request is refused, and downloads and the one confirmation are
// answered in the page.
// How a failure is made: no control of the page makes one, so the check reaches the page's configuration the way React's
// developer tools do - a stand-in for their hook, in place before the page loads, is handed the page's root - and gives the
// configuration a row that is not a row (null), which the Parameters table cannot draw.
// What it pins:
//   - after a change the page cannot draw: the panel names the error and offers Undo the last change, Export JSON and Reload;
//     Export JSON downloads the configuration as it is; Undo draws the page again from the configuration before, kept in this
//     browser too;
//   - a saved configuration the page cannot draw when it opens: the panel without Undo, with Reload and "Start from an empty
//     configuration...", which downloads the saved one first and opens the page empty.
// Run: bash frontend/scripts/run_checks.sh --only crash_panel_check. About 15 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('crash');
const PANEL = `document.querySelector('.crash-panel')`;
const BUTTON = text => `[...document.querySelectorAll('.crash-panel button')].find(b => b.textContent === ${JSON.stringify(text)})`;
const STORED = `JSON.parse(localStorage.getItem('gator-workbench-config-v1') || 'null')`;
const DELIBERATE = /Cannot read properties of null/;

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, consoleErrors } = page;
  await page.intercept(['*/api/config/validate'], params => page.fulfil(params.requestId, 200, validConfiguration()), { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `
    // a stand-in for React's developer-tools hook: it is told of every commit, so the check can reach the page's state
    window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = { supportsFiber: true, isDisabled: false, renderers: new Map(),
      inject(renderer) { this.renderers.set(1, renderer); return 1; }, onCommitFiberRoot(id, root) { window.__gatorRoot = root; },
      onCommitFiberUnmount() {}, onPostCommitFiberRoot() {}, checkDCE() {} };
    // a download is kept here (its name also across a reload), and the empty start's confirmation is answered yes
    const create = URL.createObjectURL.bind(URL);
    URL.createObjectURL = blob => { window.__downloaded = blob; return create(blob); };
    HTMLAnchorElement.prototype.click = function () { if (this.download) { window.__downloadName = this.download; sessionStorage.setItem('fixture-download', this.download); } };
    window.confirm = () => true;` });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors table.editor tbody tr')`, 200));
  await sleep(800);

  // ---- a change the page cannot draw --------------------------------------------------------------------------------------------------
  // the configuration's history (App's useConfig) found among the root's hooks, and a row the table cannot draw given to it
  const reached = await evaluate(`(() => { const stack = [window.__gatorRoot?.current].filter(Boolean);
    while (stack.length) { const f = stack.pop(); let h = f.memoizedState;
      while (h && typeof h === 'object' && 'next' in h) { const s = h.memoizedState;
        if (s && typeof s === 'object' && 'config' in s && 'past' in s && 'future' in s && h.queue?.dispatch) {
          h.queue.dispatch({ type: 'set', next: c => ({ ...c, parameters: [null, ...c.parameters] }), record: true, field: null, at: Date.now() }); return true; }
        h = h.next; }
      if (f.child) stack.push(f.child); if (f.sibling) stack.push(f.sibling); }
    return false; })()`);
  check('(set-up) the configuration is reached through the stand-in hook', reached);
  check('a change the page cannot draw shows the crash panel naming the error, instead of a blank page', await page.until(`!!${PANEL}`, 50)
    && DELIBERATE.test(await evaluate(`${PANEL}.querySelector('code').textContent`)) && !(await evaluate(`!!document.querySelector('section.editors')`)),
    await evaluate(`${PANEL}?.textContent.slice(0, 160) ?? '(no panel)'`));
  check('...with Undo the last change, Export JSON and Reload - and no empty start while Undo is the way back',
    await evaluate(`!!${BUTTON('Undo the last change')} && !!${BUTTON('Export JSON')} && !!${BUTTON('Reload')} && !${BUTTON('Start from an empty configuration...')}`));
  await page.shot(path.join(out, 'crash-1-panel.png'), PANEL);
  await evaluate(`${BUTTON('Export JSON')}.click()`); await sleep(300);
  const exported = await evaluate(`window.__downloaded ? window.__downloaded.text().then(t => JSON.parse(t)) : null`);
  check('Export JSON downloads the configuration as it is, the row the table could not draw too', exported?.parameters?.[0] === null
    && exported.parameters.length === config.parameters.length + 1 && /\.config\.json$/.test(await evaluate('window.__downloadName ?? ""')), JSON.stringify(exported?.parameters?.slice(0, 2)));
  await evaluate(`${BUTTON('Undo the last change')}.click()`);
  check('Undo the last change draws the page again from the configuration before it', await page.until(`!${PANEL} && document.querySelectorAll('section.editors table.editor tbody tr').length === ${config.parameters.length}`, 50));
  check('...and that one is kept in this browser', await page.until(`(c => c.parameters.length === ${config.parameters.length} && c.parameters.every(p => p !== null))(${STORED})`, 50));

  // ---- a saved configuration the page cannot draw when it opens ----------------------------------------------------------------------
  await evaluate(`localStorage.setItem('gator-workbench-config-v1', JSON.stringify({ ...${STORED}, parameters: [null] }))`);
  await send('Page.reload');
  check('a saved configuration the page cannot draw when it opens: the panel without Undo, with Reload and an empty start', await page.until(`!!${PANEL}`, 100)
    && await evaluate(`!${BUTTON('Undo the last change')} && !!${BUTTON('Reload')} && !!${BUTTON('Export JSON')} && !!${BUTTON('Start from an empty configuration...')}`),
    await evaluate(`${PANEL}?.textContent.slice(0, 160) ?? '(no panel)'`));
  await page.shot(path.join(out, 'crash-2-on-opening.png'), PANEL);
  await evaluate(`sessionStorage.removeItem('fixture-download'); ${BUTTON('Start from an empty configuration...')}.click()`);
  check('"Start from an empty configuration..." downloads the saved one first, then opens the page empty', await page.until(`!${PANEL} && !!document.querySelector('section.editors')`, 150)
    && /\.config\.json$/.test(await evaluate(`sessionStorage.getItem('fixture-download') ?? ''`))
    && (await evaluate(`document.querySelectorAll('section.editors table.editor tbody tr').length`)) === 0, await evaluate(`sessionStorage.getItem('fixture-download')`));

  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  const others = consoleErrors.filter(e => !DELIBERATE.test(e));
  check('no console error but the deliberate one', !others.length, others.slice(0, 3).join(' | '));
});
