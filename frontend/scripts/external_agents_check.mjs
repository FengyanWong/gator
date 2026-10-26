// The frontend has no Agent tab, popup, CLI launcher or readiness checklist. Agent assistance is started by the user
// in a desktop app or terminal. Check the absence across navigation, narrow layouts and an old kept Agent tab value.
// Hermetic: every /api/agent/* call is captured and refused, validation is canned, all other writes are refused.
// Run against a scratch backend: bash frontend/scripts/run_checks.sh --only external_agents_check.
import path from 'node:path';
import { BOTTOM_TAB_KEY, check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks,
  sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('external-agents');

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  const page = await browser.open();
  const { send, evaluate, consoleErrors } = page;
  const requests = [];
  await page.intercept(['*/api/agent/*', '*/api/config/validate'], ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return page.fulfil(requestId, 200, validConfiguration());
    requests.push({ method: request.method, name });
    return page.fulfil(requestId, 418, { detail: { message: 'Agent operations must not be requested by the frontend.' } });
  }, { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until("!!document.querySelector('.editors table.editor tbody tr')", 200));

  const strip = "Array.from(document.querySelectorAll('footer .tabs > button'))";
  const button = label => strip + '.find(b => b.textContent.trim() === ' + JSON.stringify(label) + ')';
  const names = await evaluate(strip + '.map(b => b.textContent.trim())');
  check('Run status is first and Runs remains last; there is no Agent entry',
    names[0] === 'Run status' && names.at(-1) === 'Runs...' && !names.some(n => /^Agent/.test(n)), JSON.stringify(names));
  check('no Agent popup, checklist or CLI controls remain',
    await evaluate("!document.querySelector('.agent-tab, .agent-window, #agent-root, .agent-cli, .missing-list, ul.checklist')"
      + " && !Array.from(document.querySelectorAll('button')).some(b => ['Claude Code', 'Codex', \"What's missing?\"].includes(b.textContent.trim()))"));
  check('no Agent stylesheet rules remain', await evaluate("(() => { const found = []; const walk = rules => { for (const r of rules) {"
    + "if (r.selectorText && /[.#]agent-|\\.missing-list|ul\\.checklist|\\.check-(mark|who|detail|action|done|missing|warning|not_applicable)/.test(r.selectorText)) found.push(r.selectorText);"
    + "if (r.cssRules) walk(r.cssRules); } }; for (const sheet of document.styleSheets) walk(sheet.cssRules); return found.length === 0; })()"));

  for (const label of ['Logs', 'Data tables', 'Output files', 'Training', 'Run status']) {
    await evaluate(button(label) + '.click()');
    check(label + ' still opens', await page.until(button(label) + ".classList.contains('active')"));
  }
  for (const width of [640, 960, 1680]) {
    await page.viewport(width, 900);
    await sleep(150);
    const state = await evaluate("(() => { const first = document.querySelector('footer .tabs > button');"
      + "const runs = document.querySelector('footer .tabs .run-list-button'); return { first: first.textContent.trim(),"
      + "width: runs.getBoundingClientRect().width, agents: document.querySelectorAll('.agent-tab, .agent-window').length }; })()");
    check(width + 'px layout retains Run status and the Runs window control',
      state.first === 'Run status' && state.width > 50 && state.agents === 0, JSON.stringify(state));
  }
  await evaluate('sessionStorage.setItem(' + JSON.stringify(BOTTOM_TAB_KEY) + ", 'agent')");
  await send('Page.reload');
  check('an obsolete kept Agent tab falls back to Run status on reload',
    await page.until("document.querySelector('footer .tabs > button.active')?.textContent.trim() === 'Run status'", 200));
  await sleep(500);
  check('navigation and reload never ask the backend about agents', requests.length === 0, JSON.stringify(requests));
  check('no Agent window was opened', !(await browser.pages()).some(p => p.title === 'GATOR - agent'));
  await page.shot(path.join(out, 'external-agents-removed.png'));
  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no browser console errors', consoleErrors.length === 0, JSON.stringify(consoleErrors));
}, { afterError: () => {} });
