// Browser check of record 7.226 - the Agent tab, minimal (user, 2026-10-06: "rewrite the whole agent tab to minimal"): two buttons
// open Claude Code or Codex in a terminal window of its own, in the workbench's folder, as the user starts it; "What's missing?"
// shows the backend's free start checklist in a window of its own; nothing else - no conversation, no model or effort lists,
// no proposals, no Search method box, no agent buttons in the editors or the Virtuoso window, no AI count in the header.
// Hermetic: every /api/agent/* request is answered here (a press never reaches a backend, so no window can open), reads pass
// to the backend under test, every other writing request is refused. Safe on 8765.
// What it pins:
//   - the tab is a plain tab, first in the strip; it holds the folder, the two CLI buttons and "What's missing?";
//   - opening the page or the tab sends nothing: a CLI opens on its button only, one request naming that CLI and nothing else;
//   - an opened CLI is said in one line; one that could not be opened says why and what to type, with Copy;
//   - a CLI the backend did not find is a disabled button with the reason;
//   - "What's missing?" opens a window with the verdict, the items, whose step each is and what to do; pressed again it works
//     the list out again from the configuration as it is then (and fills the same window).
// Run: bash frontend/scripts/run_checks.sh --only agent_tab_check. About 10 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('agent');
const FOLDER = '/mnt/d/gator-fixture';
const CLIS = (codex = true) => ({ directory: FOLDER, launch: 'off', note: 'FIXTURE', clis: [
  { cli: 'claude', name: 'Claude Code', available: true, executable: '/home/fixture/.local/bin/claude', codex_home: null, note: null, command: `cd ${FOLDER} && claude` },
  { cli: 'codex', name: 'Codex', available: codex, executable: codex ? '/fixture/codex' : null, codex_home: codex ? '/fixture/.codex' : null,
    note: codex ? null : 'Codex is not installed for this user: no `codex` on the PATH, and no Codex app build was found.', command: `cd ${FOLDER} && codex` }] });
const READINESS = round => ({ ready: false, note: 'FIXTURE: computed by the backend; no model was called, nothing was probed.',
  next: { id: 'targets', title: 'Specs', status: 'missing', who: 'agent', detail: 'No active hard constraint yet.', action: 'Write each requirement in the "Specs" tab.' },
  items: [
    { id: 'circuit', title: 'Circuit', status: 'done', who: 'you', detail: 'Synthetic (MOCK) circuit read: 7 devices.', action: '' },
    { id: 'targets', title: 'Specs', status: 'missing', who: 'agent', detail: `No active hard constraint yet (round ${round}).`,
      action: 'Write each requirement in the "Specs" tab, with where it comes from. Claude Code or Codex (Agent tab) can also draft the rows from your description.' },
    { id: 'output', title: 'Output folder', status: 'missing', who: 'you', detail: 'The folder exists but is not writable.', action: 'Choose another folder under "Output settings" (right).' },
    { id: 'start', title: 'Start', status: 'missing', who: 'you', detail: '2 item(s) above still block a start.', action: '' }] });

await runChecks(browser, async () => {
  const config = { schema_version: 'gator-workbench-config-v1', ...(await starterConfig(APP)) };
  const page = await browser.open();
  const { send, evaluate, consoleErrors } = page;
  const seen = [];                                  // every /api/agent/* request: method, route, body
  let codex = true, round = 0;
  await page.intercept(['*/api/agent/*', '*/api/config/validate'], ({ requestId, request }) => {
    const name = new URL(request.url).pathname;
    if (name === '/api/config/validate') return page.fulfil(requestId, 200, validConfiguration());
    const body = request.postData ? JSON.parse(request.postData) : null;
    seen.push({ method: request.method, name, body });
    if (name === '/api/agent/clis') return page.fulfil(requestId, 200, CLIS(codex));
    if (name === '/api/agent/readiness') return page.fulfil(requestId, 200, READINESS(++round));
    if (name === '/api/agent/open' && body?.cli === 'claude') return page.fulfil(requestId, 200, { opened: true, cli: 'claude', name: 'Claude Code',
      directory: FOLDER, terminal: 'wt.exe', command: `cd ${FOLDER} && claude`, note: 'FIXTURE: nothing was opened.' });
    if (name === '/api/agent/open') return page.fulfil(requestId, 409, { detail: { code: 'cli_not_opened', command: `cd ${FOLDER} && codex`,
      message: 'No terminal window can be opened from the workbench server here. Start it in a terminal of your own.' } });
    return page.fulfil(requestId, 418, { detail: { message: `FIXTURE: ${name} is not expected in this check` } });
  }, { others: 'read' });
  await page.seed({ config, when: 'once' });
  await send('Page.navigate', { url: APP });
  check('the page opens', await page.until(`!!document.querySelector('.editors table.editor tbody tr')`, 200));
  await sleep(600);
  const TAB = `[...document.querySelectorAll('footer .tabs > button')].find(b => b.textContent.trim() === 'Agent')`;
  const AGENT = `document.querySelector('footer .agent')`;
  const BUTTON = text => `[...${AGENT}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const posts = () => seen.filter(s => s.method === 'POST');

  // ---- the tab holds three buttons and a folder, nothing else ------------------------------------------------------------------------
  check('the Agent tab is a plain tab, first in the strip (no pop-out control on it)', await evaluate(`!!(${TAB}) && document.querySelector('footer .tabs > button') === ${TAB}
    && !document.querySelector('footer .tabs .tab-group, footer .tabs .tab-detach')`));
  await evaluate(`${TAB}.click()`);
  check('the tab shows the folder the CLIs open in, then Claude Code and Codex, and What\'s missing? at the right end',
    await page.until(`!!(${BUTTON('Claude Code')}) && !(${BUTTON('Claude Code')}).disabled`)
    && await evaluate(`${AGENT}.querySelector('.agent-row .hint').textContent === 'In ${FOLDER}:' && !!(${BUTTON('Codex')}) && !!(${BUTTON("What's missing?")})
      && [...${AGENT}.querySelectorAll('.agent-row > button')].map(b => b.textContent.trim()).join('|') === "Claude Code|Codex|What's missing?"`),
    await evaluate(`${AGENT}.textContent.slice(0, 200)`));
  check('no conversation, message box, provider, model or effort list, proposal or import any more', await evaluate(`!${AGENT}.querySelector('textarea, select, .chat, .msg, .compose, .notes, .confirm')
    && !${AGENT}.textContent.includes('Export task description') && !${AGENT}.textContent.includes('Review settings') && !${AGENT}.textContent.includes('Provider')`));
  check('the headline says how the CLI starts: your settings, your account, your history', await evaluate(`${AGENT}.querySelector('.agent-headline').textContent.includes('as you start it yourself: your settings, your account, your history')`));
  check('the help is one closed line: what to ask it, and that Codex should read CLAUDE.md first', await evaluate(`(() => { const d = ${AGENT}.querySelector('details.agent-help');
    return !!d && !d.open && d.querySelector('summary').textContent === 'What to ask it' && d.textContent.includes('tell Codex to read CLAUDE.md first'); })()`));
  check('the buttons say in their tooltip how the CLI starts', await evaluate(`${BUTTON('Claude Code')}.title.includes('your own Claude Code settings decide what it may do') && ${BUTTON('Codex')}.title.includes('Codex history')`));
  check('opening the page and the tab asked only which CLIs there are: nothing opened, nothing checked', posts().length === 0
    && seen.filter(s => s.name === '/api/agent/clis').length === 1, JSON.stringify(seen));
  await page.shot(path.join(out, 'agent-1-tab.png'), `document.querySelector('footer')`);

  // ---- the two buttons -------------------------------------------------------------------------------------------------------------------
  await evaluate(`${BUTTON('Claude Code')}.click()`);
  check('Claude Code: one request naming that CLI and nothing else', await page.until(`!!${AGENT}.querySelector('.agent-said')`)
    && JSON.stringify(posts().map(s => [s.name, s.body])) === JSON.stringify([['/api/agent/open', { cli: 'claude' }]]), JSON.stringify(posts()));
  check('...said in one line: it opens in a new window, in the folder', await evaluate(`${AGENT}.querySelector('.agent-said').textContent.startsWith('Claude Code opens in a new window (wt.exe), in ${FOLDER}.')`),
    await evaluate(`${AGENT}.querySelector('.agent-said').textContent`));
  await evaluate(`${BUTTON('Codex')}.click()`);
  check('Codex that cannot be opened: why, and the command to type, with Copy', await page.until(`${AGENT}.querySelector('.agent-said')?.textContent.startsWith('Codex was not opened: No terminal window')`)
    && await evaluate(`${AGENT}.querySelector('.agent-said code').textContent === 'cd ${FOLDER} && codex' && ${AGENT}.querySelector('.agent-said button.text-link').textContent === 'Copy'
      && ${AGENT}.querySelector('.agent-said').classList.contains('error')`), await evaluate(`${AGENT}.querySelector('.agent-said').textContent`));
  check('...one more request, for Codex', JSON.stringify(posts().map(s => s.body?.cli)) === JSON.stringify(['claude', 'codex']));
  await page.shot(path.join(out, 'agent-2-not-opened.png'), AGENT);

  // ---- What's missing? in a window of its own ---------------------------------------------------------------------------------------
  await evaluate(`${BUTTON("What's missing?")}.click()`, true);
  const target = await browser.window('GATOR - what is missing', { except: page.target.id });
  const far = await browser.attach(target, { errors: consoleErrors, prefix: 'window: ' });
  await far.send('Emulation.setDeviceMetricsOverride', { width: 780, height: 820, deviceScaleFactor: 1, mobile: false });
  const WINDOW = `document.querySelector('.missing-window')`;
  check('What\'s missing? opens a window with the verdict and the items', await far.until(`${WINDOW}?.querySelectorAll('ul.checklist li').length === 4`)
    && await far.evaluate(`${WINDOW}.querySelector('.verdict').textContent === 'Not ready yet: 2 items block a start. Next: Specs.'`),
    await far.evaluate(`${WINDOW}?.textContent.slice(0, 300) ?? '(no window content)'`));
  check('...each item with its mark, whose step it is and what to do', await far.evaluate(`(() => { const li = [...${WINDOW}.querySelectorAll('ul.checklist li')];
    return li[0].querySelector('.check-mark').textContent === '\\u2714' && !li[0].querySelector('.check-who')
      && li[1].querySelector('.check-who').textContent === 'an agent can help' && li[1].querySelector('.check-action').textContent.includes('Claude Code or Codex (Agent tab)')
      && li[2].querySelector('.check-who').textContent === 'yours' && li[2].querySelector('.check-action').textContent.startsWith('Choose another folder'); })()`));
  check('...worked out from the configuration on the page, said with the time, and how to see it again', await far.evaluate(`${WINDOW}.textContent.includes('no model was called')
    && /Worked out at \\d\\d:\\d\\d:\\d\\d, from the configuration on the page: press "What's missing\\?" in the Agent tab again after a change\\./.test(${WINDOW}.textContent)`));
  const asked = seen.filter(s => s.name === '/api/agent/readiness');
  check('one free request, with the page\'s configuration', asked.length === 1 && asked[0].body?.config?.circuit?.task_id === config.circuit.task_id, JSON.stringify(asked.map(a => Object.keys(a.body ?? {}))));
  await far.shot(path.join(out, 'agent-3-missing-window.png'), WINDOW, { maxHeight: 1200, beyond: true });
  await evaluate(`${BUTTON("What's missing?")}.click()`, true);
  check('pressed again: worked out again, in the same window', await far.until(`${WINDOW}.textContent.includes('(round 2)')`)
    && seen.filter(s => s.name === '/api/agent/readiness').length === 2 && (await browser.pages()).filter(t => t.title === 'GATOR - what is missing').length === 1);

  // ---- a CLI the backend did not find ------------------------------------------------------------------------------------------------
  codex = false;
  await send('Page.reload');
  await page.until(`!!document.querySelector('.editors table.editor tbody tr')`, 200);
  await evaluate(`${TAB}.click()`);
  check('a CLI the backend did not find: its button is disabled, with the reason beside it and in its tooltip',
    await page.until(`!!(${BUTTON('Codex')}) && (${BUTTON('Codex')}).disabled && !(${BUTTON('Claude Code')}).disabled`)
    && await evaluate(`${BUTTON('Codex')}.title.startsWith('Codex is not installed') && ${AGENT}.textContent.includes('Codex is not installed for this user')`));

  // ---- the parts that went with the old tab ------------------------------------------------------------------------------------------
  check('the editors have no agent buttons, Run configuration no Search method, the header no AI count', await evaluate(`
    ![...document.querySelectorAll('.editors .toolbar button')].some(b => /with agent/.test(b.textContent))
    && !document.querySelector('select[aria-label="Search method"]') && !document.querySelector('header .llm-run-progress')
    && !document.querySelector('.right').textContent.includes('Search method')`));
  check('a CLI opened only on its button press: the two presses, nothing else', JSON.stringify(posts().filter(s => s.name === '/api/agent/open').map(s => s.body.cli)) === JSON.stringify(['claude', 'codex']));
  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
