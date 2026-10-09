// Browser check of record 7.253 - the Agent window (user, 2026-10-07: "make the agent tab pop out window only (no tab view)"): the
// bottom panel's tab line has no Agent tab VIEW any more; "Agent...", first in the line and still drawn as a tab (the user, then:
// "make it still a tab style but not button style"), opens a window of its own that holds record 7.226's line - the folder,
// Claude Code, Codex and "What's missing?" - and, under it, the start checklist once it was asked for. Hermetic: every
// /api/agent/* request is answered here (a press never reaches a backend, so no terminal window can open), reads pass to the
// backend under test, every other writing request is refused. Safe on 8765.
// What it pins:
//   - no Agent tab view; "Agent..." stands first in the tab line, drawn like the other tabs (not like the "Runs..." button),
//     never the active tab, underlined while its window is open;
//   - opening the page sends nothing about agents; opening the window asks once which CLIs there are, nothing else;
//   - the window holds the folder, the two CLI buttons and "What's missing?", the headline and the closed help line, no list yet;
//   - a CLI opens on its button only, one request naming that CLI; an opened CLI is said in one line; one that could not be
//     opened says why and what to type, with Copy; a CLI the backend did not find is a disabled button with the reason;
//   - "What's missing?" fills the lower part of the SAME window (no second window) with the verdict, the items, whose step
//     each is and what to do; pressed again it works the list out again from the configuration as it is then;
//   - "Agent..." pressed while the window is open brings it to the front and looks for the CLIs again, no second window; a
//     reload of the page closes the window, and a window opened anew starts clean.
// Run: bash frontend/scripts/run_checks.sh --only agent_window_check. About 12 s.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl, AGENT_WINDOW } from './lib/harness.mjs';

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
      action: 'Write each requirement in the "Specs" tab, with where it comes from. Claude Code or Codex (the Agent window) can also draft the rows from your description.' },
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
  const STRIP = `[...document.querySelectorAll('footer .tabs > button')]`;
  const AGENT_BUTTON = `${STRIP}.find(b => b.textContent.trim() === 'Agent...')`;
  const WINDOW = `document.querySelector('.agent-window')`;
  const BUTTON = text => `[...${WINDOW}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`;
  const LIST = `${WINDOW}.querySelector('.missing-list')`;
  const posts = () => seen.filter(s => s.method === 'POST');
  const agentWindows = async () => (await browser.pages()).filter(t => t.title === AGENT_WINDOW).length;

  // ---- the tab line: no Agent tab view; "Agent..." first, drawn as a tab, not as the "Runs..." button -------------------------------
  check('no Agent tab view: "Agent..." is first in the tab line, drawn like the Logs tab (same background, border and weight; not like "Runs..."), not the active tab; Run status follows',
    await evaluate(`(() => { const names = ${STRIP}.map(b => b.textContent.trim()); const agent = ${AGENT_BUTTON};
      const logs = ${STRIP}.find(b => b.textContent.trim() === 'Logs'), runs = ${STRIP}.find(b => b.textContent.trim() === 'Runs...');
      const a = getComputedStyle(agent), l = getComputedStyle(logs), r = getComputedStyle(runs);
      return !names.includes('Agent') && names[0] === 'Agent...' && names[1] === 'Run status' && agent.classList.contains('agent-tab')
        && !agent.classList.contains('active') && !agent.classList.contains('open') && a.boxShadow === 'none'
        && a.backgroundColor === l.backgroundColor && a.borderColor === l.borderColor && a.fontWeight === l.fontWeight && a.fontWeight !== r.fontWeight
        && names.slice(-1)[0] === 'Runs...' && !document.querySelector('footer .bottom-body .agent-row'); })()`),
    await evaluate(`${STRIP}.map(b => b.textContent.trim()).join('|')`));
  check('opening the page asked the backend nothing about agents', seen.length === 0, JSON.stringify(seen));
  await page.shot(path.join(out, 'agent-1-tab-line.png'), `document.querySelector('footer .tabs')`);

  // ---- the window --------------------------------------------------------------------------------------------------------------
  await evaluate(`${AGENT_BUTTON}.click()`, true);
  const target = await browser.window(AGENT_WINDOW, { except: page.target.id });
  const far = await browser.attach(target, { errors: consoleErrors, prefix: 'window: ' });
  await far.send('Emulation.setDeviceMetricsOverride', { width: 780, height: 760, deviceScaleFactor: 1, mobile: false });
  check('"Agent..." opens the agent window: the folder the CLIs open in, then Claude Code and Codex, and What\'s missing? at the right end',
    await far.until(`!!(${BUTTON('Claude Code')}) && !(${BUTTON('Claude Code')}).disabled`)
    && await far.evaluate(`${WINDOW}.querySelector('.agent-row .hint').textContent === 'In ${FOLDER}:' && !!(${BUTTON('Codex')}) && !!(${BUTTON("What's missing?")})
      && [...${WINDOW}.querySelectorAll('.agent-row > button')].map(b => b.textContent.trim()).join('|') === "Claude Code|Codex|What's missing?"
      && ${WINDOW}.querySelector('h2').textContent === 'Agent: Claude Code or Codex'`),
    await far.evaluate(`${WINDOW}?.textContent.slice(0, 200) ?? '(no window content)'`));
  check('the tab says the window is open (underlined, its tooltip); still not the active tab; one window', await evaluate(`${AGENT_BUTTON}.classList.contains('open')
    && getComputedStyle(${AGENT_BUTTON}).boxShadow !== 'none' && !${AGENT_BUTTON}.classList.contains('active') && ${AGENT_BUTTON}.title.startsWith('The agent window is open')`)
    && await agentWindows() === 1);
  check('opening the window asked only which CLIs there are: nothing opened, nothing checked', posts().length === 0
    && seen.filter(s => s.name === '/api/agent/clis').length === 1, JSON.stringify(seen));
  check('no conversation, message box, provider, model or effort list, proposal or import', await far.evaluate(`!${WINDOW}.querySelector('textarea, select, .chat, .msg, .compose, .notes, .confirm')
    && !${WINDOW}.textContent.includes('Export task description') && !${WINDOW}.textContent.includes('Review settings') && !${WINDOW}.textContent.includes('Provider')`));
  check('the headline says how the CLI starts: your settings, your account, your history', await far.evaluate(`${WINDOW}.querySelector('.agent-headline').textContent.includes('as you start it yourself: your settings, your account, your history')`));
  check('the help is one closed line: what to ask it, and that Codex should read CLAUDE.md first', await far.evaluate(`(() => { const d = ${WINDOW}.querySelector('details.agent-help');
    return !!d && !d.open && d.querySelector('summary').textContent === 'What to ask it' && d.textContent.includes('tell Codex to read CLAUDE.md first'); })()`));
  check('the buttons say in their tooltip how the CLI starts', await far.evaluate(`${BUTTON('Claude Code')}.title.includes('your own Claude Code settings decide what it may do') && ${BUTTON('Codex')}.title.includes('Codex history')`));
  check('no checklist before it is asked for', await far.evaluate(`!${LIST}`));
  await far.shot(path.join(out, 'agent-2-window.png'), WINDOW);

  // ---- the two buttons ---------------------------------------------------------------------------------------------------------
  await far.evaluate(`${BUTTON('Claude Code')}.click()`);
  check('Claude Code: one request naming that CLI and nothing else', await far.until(`!!${WINDOW}.querySelector('.agent-said')`)
    && JSON.stringify(posts().map(s => [s.name, s.body])) === JSON.stringify([['/api/agent/open', { cli: 'claude' }]]), JSON.stringify(posts()));
  check('...said in one line: it opens in a new window, in the folder', await far.evaluate(`${WINDOW}.querySelector('.agent-said').textContent.startsWith('Claude Code opens in a new window (wt.exe), in ${FOLDER}.')`),
    await far.evaluate(`${WINDOW}.querySelector('.agent-said').textContent`));
  await far.evaluate(`${BUTTON('Codex')}.click()`);
  check('Codex that cannot be opened: why, and the command to type, with Copy', await far.until(`${WINDOW}.querySelector('.agent-said')?.textContent.startsWith('Codex was not opened: No terminal window')`)
    && await far.evaluate(`${WINDOW}.querySelector('.agent-said code').textContent === 'cd ${FOLDER} && codex' && ${WINDOW}.querySelector('.agent-said button.text-link').textContent === 'Copy'
      && ${WINDOW}.querySelector('.agent-said').classList.contains('error')`), await far.evaluate(`${WINDOW}.querySelector('.agent-said').textContent`));
  check('...one more request, for Codex', JSON.stringify(posts().map(s => s.body?.cli)) === JSON.stringify(['claude', 'codex']));
  await far.shot(path.join(out, 'agent-3-not-opened.png'), WINDOW);

  // ---- What's missing? in the same window ---------------------------------------------------------------------------------------
  await far.evaluate(`${BUTTON("What's missing?")}.click()`);
  check('What\'s missing? fills the lower part of the same window with the verdict and the items; no second window', await far.until(`${LIST}?.querySelectorAll('ul.checklist li').length === 4`)
    && await far.evaluate(`${LIST}.querySelector('.verdict').textContent === 'Not ready yet: 2 items block a start. Next: Specs.' && ${LIST}.querySelector('h3').textContent === "What's missing before the run can start"`)
    && await agentWindows() === 1 && !(await browser.pages()).some(t => t.title === 'GATOR - what is missing'),
    await far.evaluate(`${LIST}?.textContent.slice(0, 300) ?? '(no list)'`));
  check('...each item with its mark, whose step it is and what to do', await far.evaluate(`(() => { const li = [...${LIST}.querySelectorAll('ul.checklist li')];
    return li[0].querySelector('.check-mark').textContent === '\\u2714' && !li[0].querySelector('.check-who')
      && li[1].querySelector('.check-who').textContent === 'an agent can help' && li[1].querySelector('.check-action').textContent.includes('Claude Code or Codex (the Agent window)')
      && li[2].querySelector('.check-who').textContent === 'yours' && li[2].querySelector('.check-action').textContent.startsWith('Choose another folder'); })()`));
  check('...worked out from the configuration on the page, said with the time, and how to see it again', await far.evaluate(`${LIST}.textContent.includes('no model was called')
    && /Worked out at \\d\\d:\\d\\d:\\d\\d, from the configuration on the page: press "What's missing\\?" again after a change\\./.test(${LIST}.textContent)`));
  const asked = seen.filter(s => s.name === '/api/agent/readiness');
  check('one free request, with the page\'s configuration', asked.length === 1 && asked[0].body?.config?.circuit?.task_id === config.circuit.task_id, JSON.stringify(asked.map(a => Object.keys(a.body ?? {}))));
  await far.shot(path.join(out, 'agent-4-missing.png'), WINDOW, { maxHeight: 1400, beyond: true });
  await far.evaluate(`${BUTTON("What's missing?")}.click()`);
  check('pressed again: worked out again, in the same window', await far.until(`${LIST}.textContent.includes('(round 2)')`)
    && seen.filter(s => s.name === '/api/agent/readiness').length === 2 && await agentWindows() === 1);

  // ---- "Agent..." pressed while the window is open ------------------------------------------------------------------------------
  await evaluate(`${AGENT_BUTTON}.click()`, true);
  await sleep(400);
  check('"Agent..." pressed again: the one window comes to the front, the CLIs are looked for again, what it showed stays',
    await agentWindows() === 1 && seen.filter(s => s.name === '/api/agent/clis').length === 2
    && await far.evaluate(`!!${LIST} && ${LIST}.textContent.includes('(round 2)') && !!${WINDOW}.querySelector('.agent-said')`), JSON.stringify(seen.map(s => s.name)));

  // ---- a CLI the backend did not find; a window opened anew starts clean ----------------------------------------------------------
  codex = false;
  await send('Page.reload');
  await page.until(`!!document.querySelector('.editors table.editor tbody tr')`, 200);
  check('a reload of the page closes the agent window with it', await browser.window(AGENT_WINDOW, { present: false, ms: 5000 }) === null);
  await evaluate(`${AGENT_BUTTON}.click()`, true);
  const again = await browser.attach(await browser.window(AGENT_WINDOW, { except: page.target.id }), { errors: consoleErrors, prefix: 'window: ' });
  check('a CLI the backend did not find: its button is disabled, with the reason beside it and in its tooltip',
    await again.until(`!!(${BUTTON('Codex')}) && (${BUTTON('Codex')}).disabled && !(${BUTTON('Claude Code')}).disabled`)
    && await again.evaluate(`${BUTTON('Codex')}.title.startsWith('Codex is not installed') && ${WINDOW}.textContent.includes('Codex is not installed for this user')`));
  check('the window opened anew starts clean: no line of a press, no checklist', await again.evaluate(`!${WINDOW}.querySelector('.agent-said') && !${LIST}`));

  // ---- the parts that went with the old tab ---------------------------------------------------------------------------------------
  check('the editors have no agent buttons, Run configuration no Search method, the header no AI count', await evaluate(`
    ![...document.querySelectorAll('.editors .toolbar button')].some(b => /with agent/.test(b.textContent))
    && !document.querySelector('select[aria-label="Search method"]') && !document.querySelector('header .llm-run-progress')
    && !document.querySelector('.right').textContent.includes('Search method')`));
  check('a CLI opened only on its button press: the two presses, nothing else', JSON.stringify(posts().filter(s => s.name === '/api/agent/open').map(s => s.body.cli)) === JSON.stringify(['claude', 'codex']));
  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
  check('no console error', !consoleErrors.length, consoleErrors.slice(0, 3).join(' | '));
});
