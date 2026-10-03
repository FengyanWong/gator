// Browser check of WHERE the Agent tab's model list comes from (user request 2026-10-03: "agent list is not updated",
// then "build option 1 and update the Claude list too"). The Codex list is the Codex app's own file of the account's
// models when the backend can read it (agents/catalog.py), the hand table otherwise; the Claude Code list is always the
// hand table. Hermetic: GET /api/agent/settings is answered with FIXTURE settings, other reads pass, every writing
// request is refused - so it changes nothing on the backend it runs against, and calls no model.
// What it pins:
//   - the Codex app's models are the drop-down, in the app's order, a retiring one marked; each model keeps its levels;
//   - the hint says the list is the Codex app's (fetched when) and that showing it calls no model;
//   - "Re-read list" (Codex only) reads the settings again and the drop-down follows the new list - nothing else is sent;
//   - without the app's file the hand table is shown with the reason; Claude Code says "checked by hand", no Re-read.
// Run (Windows node through WSL interop; about 20 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/agent_model_list_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('agent-list');

const ALL = ['low', 'medium', 'high', 'xhigh', 'max', 'ultra'];
const model = (id, efforts, label = id) => ({ id, label, note: `FIXTURE ${id} described. Codex default effort: ${efforts[0]}.`, efforts });
const FIRST = [model('gpt-6.1-sol', ALL), model('gpt-6-luna', ALL.slice(0, 5)), model('gpt-5.5', ALL.slice(0, 4), 'gpt-5.5 (retires 2026-10-14)')];
const SECOND = [model('gpt-6.2-nova', ALL), model('gpt-6.1-sol', ALL), model('gpt-6-luna', ALL.slice(0, 5))];
const HAND = { verified: '2026-10-03', source: 'https://learn.chatgpt.com/docs/models', origin: 'hand_table', efforts: ALL,
  default_note: 'Nothing is passed: the CLI uses your Codex configuration.', caveat: 'FIXTURE caveat.', models: [model('gpt-6-astra', ALL)] };
const fromApp = (models, fetched) => ({ ...HAND, origin: 'codex_app', models, verified: fetched.slice(0, 10), fetched_at: fetched,
  cache_file: '/fixture/.codex/models_cache.json', client_version: 'fixture' });

await runChecks(browser, async () => {
  const real = await (await fetch(new URL('api/agent/settings', APP))).json();     // the fields the tab needs besides the lists
  const claudeList = { ...real.catalog.claude_code, verified: '2026-10-03', origin: 'hand_table' };
  const settings = (provider, codex, model = null) => ({ ...real, provider, model, effort: null,
    availability: [{ provider: 'claude_code', available: true }, { provider: 'codex', available: true }, { provider: 'disabled', available: true }],
    catalog: { ...real.catalog, claude_code: claudeList, codex } });
  let served = settings('codex', fromApp(FIRST, '2026-10-03T15:50:41Z'), 'gpt-6-luna'), reads = 0;
  const page = await browser.open();
  const { send, evaluate, until, consoleErrors } = page;
  await page.intercept(['*/api/agent/settings'], params => {
    if (params.request.method !== 'GET') return page.readOrRefuse(params);
    reads++;
    return page.fulfil(params.requestId, 200, served);
  }, { others: 'read' });
  // No task is seeded: the Agent tab's lists need none, and a fresh page opens without one (record 7.128).

  const FIELD = name => `[...document.querySelectorAll('.agent-side label')].find(l => l.firstChild.textContent.trim() === ${JSON.stringify(name)})`;
  const options = name => evaluate(`[...${FIELD(name)}.querySelectorAll('option')].map(o => o.value)`);
  const labels = name => evaluate(`[...${FIELD(name)}.querySelectorAll('option')].map(o => o.textContent)`);
  const hint = () => evaluate(`document.querySelector('.agent-side p.hint').textContent`);
  const REREAD = `[...document.querySelectorAll('.agent-side button.text-link')].find(b => b.textContent === 'Re-read list')`;
  const open = async () => {
    await send('Page.navigate', { url: APP });
    if (!(await until(`[...document.querySelectorAll('footer .tabs button')].some(b => b.textContent.trim() === 'Agent')`, 150)))
      throw new Error('the Agent tab never appeared; console: ' + consoleErrors.join(' | ').slice(0, 300));
    await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Agent').click()`);
    if (!(await until(`!!${FIELD('Agent model')}?.querySelector('select')`))) throw new Error('the Agent model list never appeared');
    await sleep(300);
  };

  // ---- the Codex app's list ----------------------------------------------------------------------------------------
  await open();
  if (!(await hint()).includes('Codex app')) throw new Error('the served frontend is older than this change (build it, then reload): ' + await hint());
  check('the drop-down is the Codex app\'s list, in its order', (await options('Agent model')).join(' ') === ' gpt-6.1-sol gpt-6-luna gpt-5.5 __custom__', (await options('Agent model')).join(' '));
  check('a retiring model is marked in the list', (await labels('Agent model')).includes('gpt-5.5 (retires 2026-10-14)'));
  check('the chosen model keeps its own effort levels (Luna: no ultra)', (await options('Effort')).join(' ') === ' low medium high xhigh max', (await options('Effort')).join(' '));
  let text = await hint();
  check('the hint says where the list comes from and when it was fetched', text.includes('List from the Codex app (your account\'s models, fetched') && text.includes('calls no model'), text);
  check('the hint shows the chosen model\'s note', text.includes('FIXTURE gpt-6-luna described.'));
  check('"Re-read list" is offered for Codex', await evaluate(`!!${REREAD}`));
  await page.shot(path.join(out, 'agent-list-codex-app.png'), `document.querySelector('.agent-side')`, { scale: 1.5 });

  // ---- Re-read list: the same GET again, nothing else ------------------------------------------------------------------
  const before = reads;
  served = settings('codex', fromApp(SECOND, '2026-10-04T08:05:00Z'), 'gpt-6-luna');
  await evaluate(`${REREAD}.click()`, true);
  await until(`[...${FIELD('Agent model')}.querySelectorAll('option')].some(o => o.value === 'gpt-6.2-nova')`, 40);
  check('"Re-read list" reads the settings once more', reads === before + 1, `${reads - before} reads`);
  check('... and the drop-down follows the new list', (await options('Agent model')).join(' ') === ' gpt-6.2-nova gpt-6.1-sol gpt-6-luna __custom__', (await options('Agent model')).join(' '));
  check('... with the new fetch time', (await hint()) !== text && (await hint()).includes('Codex app'), await hint());

  // ---- no file: the hand table, with the reason --------------------------------------------------------------------
  served = settings('codex', { ...HAND, cache_note: 'the Codex app’s model list (models_cache.json) was not found' });
  await evaluate(`${REREAD}.click()`, true);
  await until(`[...${FIELD('Agent model')}.querySelectorAll('option')].some(o => o.value === 'gpt-6-astra')`, 40);
  text = await hint();
  check('without the app\'s file the hand table is shown with the reason', text.includes('List checked by hand on 2026-10-03; the Codex app’s model list (models_cache.json) was not found.'), text);
  await page.shot(path.join(out, 'agent-list-codex-hand.png'), `document.querySelector('.agent-side')`, { scale: 1.5 });

  // ---- Claude Code: the hand table, no Re-read -----------------------------------------------------------------------
  served = settings('claude_code', HAND);
  await open();
  text = await hint();
  check('the Claude Code list says it is checked by hand', text.includes('List checked by hand on 2026-10-03.') && text.includes('calls no model'), text);
  check('... and offers no "Re-read list"', !(await evaluate(`!!${REREAD}`)));
  check('no console error', consoleErrors.length === 0, consoleErrors.join(' | '));
  reportRefused(page.refused, NEVER_ASKED_OR_SAVED);
});
