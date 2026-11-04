// Optional panels load only on demand; tab switches keep drafts, and a failed chunk leaves the editors usable.
import { check, launchEdge, MOCK_PAGE_CONFIG, newTaskFrom, RL_MODEL_WINDOW, runChecks, sleep, validConfiguration, VIRTUOSO_WINDOW, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl(), browser = await launchEdge('deferred-panels');
await runChecks(browser, async () => {
  const page = await browser.open(), { evaluate, until } = page;
  let failAgent = true, failModel = true, failVirtuoso = true, agentReads = 0, chunkReads = 0, separateStyles = 0;
  const refused = [];
  await page.intercept(['*/api/*', '*/assets/AgentTab-*.js', '*/assets/AgentTab-*.css', '*/assets/TrainingTab-*.css',
    '*/src/panels/AgentTab.tsx*', '*/assets/RlModelWindow-*.js', '*/src/panels/RlModelWindow.tsx*',
    '*/assets/VirtuosoWindow-*.js', '*/src/panels/VirtuosoWindow.tsx*'], async params => {
    const { requestId, request } = params, url = new URL(request.url);
    if (/(AgentTab|TrainingTab).*\.css$/.test(url.pathname)) {
      separateStyles++;
      return /AgentTab/.test(url.pathname)
        ? page.fulfilText(requestId, 503, 'text/plain', 'Synthetic temporary stylesheet failure') : page.pass(requestId);
    }
    if (/AgentTab.*\.(js|tsx)$/.test(url.pathname)) {
      chunkReads++;
      return failAgent ? page.fulfilText(requestId, 503, 'text/plain', 'Synthetic temporary chunk failure') : page.pass(requestId);
    }
    if (/RlModelWindow.*\.(js|tsx)$/.test(url.pathname))
      return failModel ? page.fulfilText(requestId, 503, 'text/plain', 'Synthetic temporary chunk failure') : page.pass(requestId);
    if (/VirtuosoWindow.*\.(js|tsx)$/.test(url.pathname))
      return failVirtuoso ? page.fulfilText(requestId, 503, 'text/plain', 'Synthetic temporary chunk failure') : page.pass(requestId);
    if (url.pathname === '/api/virtuoso/libraries') return page.fulfil(requestId, 200, { libraries: [] });
    if (url.pathname === '/api/config/validate') return page.fulfil(requestId, 200, validConfiguration());
    if (url.pathname === '/api/local-agent') {
      agentReads++;
      return page.fulfil(requestId, 200, { models: [], active_job: null, deployed: 'synthetic-fixture', default_model: null, mode: 'Synthetic' });
    }
    return page.readOrRefuse(params, refused, { reads: true });
  }, { connection: 'synthetic-deferred-panels' });
  await page.seed({ config: MOCK_PAGE_CONFIG, run: null, when: 'once' });
  await page.send('Page.navigate', { url: APP });
  await until(`!!document.querySelector('.editors')`, 100);
  const tab = name => evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent === ${JSON.stringify(name)}).click()`);
  const resources = () => evaluate(`performance.getEntriesByType('resource').map(r => r.name).filter(n => /TrainingTab|AgentTab|RlModelWindow|VirtuosoWindow|Pdk/.test(n) && /[.](js|tsx)($|[?#])/.test(n))`);
  check('optional panel JavaScript downloads nothing on initial page load', (await resources()).length === 0 && agentReads === 0);
  check('unvisited Training and Agent panels do not mount', await evaluate(`!document.querySelector('.training, .agent-panel')`));
  await tab('Agent');
  check('chunk failure stays inside its panel', await until(`document.querySelector('.bottom-body [role="alert"]')?.textContent.includes('Could not open Agent')`, 80));
  check('editors remain available after a chunk failure', await evaluate(`!!document.querySelector('.editors') && !document.querySelector('.crash-panel')`));
  await tab('Training');
  check('Training opens independently of a failed Agent download', await until(`!!document.querySelector('.training')`, 80));
  check('inactive panel errors are hidden', await evaluate(`document.querySelector('.bottom-body [role="alert"]').closest('[hidden]') !== null`));
  await tab('Agent'); failAgent = false;
  await evaluate(`document.querySelector('.bottom-body [role="alert"] button').click()`);
  check('failed panel can be retried', await until(`!!document.querySelector('#agent-message')`, 80), `chunk reads: ${chunkReads}`);
  check('retry keeps Agent layout styled', await evaluate(`!!document.querySelector('.agent-columns') && getComputedStyle(document.querySelector('.agent-columns')).display === 'grid'`));
  check('panel styles need no separate deferred download', separateStyles === 0, `separate styles: ${separateStyles}`);
  if (await evaluate(`!!document.querySelector('#agent-message')`)) {
    const loadedReads = chunkReads; // Browsers may retry a 503 before reporting the failed import.
    await evaluate(`document.querySelector('#agent-message').focus()`);
    await page.send('Input.insertText', { text: 'Keep this unsent draft' });
    await tab('Run status');
    const readCount = agentReads;
    await sleep(4500);
    check('hidden idle Agent does not poll', agentReads === readCount);
    await tab('Agent');
    check('Agent draft survives tab switches', await evaluate(`document.querySelector('#agent-message').value === 'Keep this unsent draft'`));
    check('loaded panels are not downloaded again', chunkReads === loadedReads);
  }
  const openModel = async () => {
    await evaluate(`document.querySelector('button.rl-networks-open').click()`, true);
    return browser.attach(await browser.window(RL_MODEL_WINDOW));
  };
  let popup = await openModel();
  check('model window reports its own download failure', await popup.until(`document.querySelector('[role="alert"]')?.textContent.includes('Could not open RL model')`, 80));
  failModel = false;
  await popup.evaluate(`document.querySelector('[role="alert"] button').click()`);
  check('model window recovers on Retry', await popup.until(`!!document.querySelector('.rl-networks-panel')`, 80));
  await popup.evaluate(`window.close()`);
  await until(`!document.querySelector('.windows-button')`, 50);
  popup = await openModel();
  check('reopening a recovered window does not reuse the failed load', await popup.until(`!!document.querySelector('.rl-networks-panel')`, 80));
  await popup.evaluate(`window.close()`);
  await browser.window(RL_MODEL_WINDOW, { present: false });
  const openVirtuoso = async () => {
    const { pressed } = await newTaskFrom(page, browser, 'virtuoso');
    if (!pressed) throw new Error('Synthetic Virtuoso connection has no new-task button');
    return browser.attach(await browser.window(VIRTUOSO_WINDOW));
  };
  popup = await openVirtuoso();
  check('Virtuoso window reports its own download failure', await popup.until(`document.querySelector('[role="alert"]')?.textContent.includes('Could not open Virtuoso')`, 80));
  check('Virtuoso download failure leaves the editors available', await evaluate(`!!document.querySelector('.editors') && !document.querySelector('.crash-panel')`));
  failVirtuoso = false;
  await popup.evaluate(`document.querySelector('[role="alert"] button').click()`);
  check('Virtuoso window recovers on Retry', await popup.until(`!!document.querySelector('.virtuoso-window')`, 80));
  await popup.evaluate(`window.close()`);
  await browser.window(VIRTUOSO_WINDOW, { present: false });
  popup = await openVirtuoso();
  check('Virtuoso window reopens after a recovered load', await popup.until(`!!document.querySelector('.virtuoso-window')`, 80));
  check('review starts no writes', refused.length === 0, refused.join(', '));
});
