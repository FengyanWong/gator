// Hermetic regression: no simulations, agent calls or backend settings writes. Only temporary browser storage changes.
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, starterConfig, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl(), out = outDir();
const browser = await launchEdge('reliability');
await runChecks(browser, async () => {
  const config = await starterConfig(APP);
  config.run = { ...config.run, mode: 'scratch' }; delete config.run.search; delete config.run.model_source;
  const settings = await (await fetch(new URL('api/network-settings', APP))).json();
  const page = await browser.open(), pending = [], resets = [];
  let hold = false;
  await page.intercept(['*/api/*'], p => {
    const name = new URL(p.request.url).pathname;
    if (name === '/api/network-settings') {
      if (hold) { pending.push(p); return; }
      return page.fulfil(p.requestId, 200, settings);
    }
    if (name.startsWith('/api/network-settings/')) {
      if (name.endsWith('/reset')) { resets.push(p); return; }
      const encoder = name.split('/').at(-1), body = JSON.parse(p.request.postData);
      return page.fulfil(p.requestId, 200, { ...settings.settings[encoder], ...body, origin: 'custom' });
    }
    if (name === '/api/config/validate') return page.fulfil(p.requestId, 200, validConfiguration({ mock: true }));
    if (name === '/api/runs') return page.fulfil(p.requestId, 200, { runs: [] });
    return page.readOrRefuse(p, page.refused, { reads: true });
  });
  await page.trackSaves();
  await page.seed({ config, run: null, when: 'once' });
  await page.send('Page.navigate', { url: APP });
  const field = label => `[...document.querySelectorAll('.right label')].find(l => l.firstChild?.textContent === ${JSON.stringify(label)})`;
  const encoder = `${field('Encoder')}?.querySelector('select')`, hidden = `${field('hidden')}?.querySelector('input')`;
  if (!await page.until(`!!(${encoder}) && !!document.querySelector('table.editor tbody tr')`)) throw new Error('Workbench did not load');
  await page.saved(); await sleep(300);
  const waitCount = async (queue, count) => { for (let i = 0; i < 150 && queue.length < count; ++i) await sleep(20); if (queue.length < count) throw new Error(`Expected ${count} requests, got ${queue.length}`); };
  hold = true;
  await page.setValue(encoder, 'rgcn'); await waitCount(pending, 1);
  await page.setValue(encoder, 'gatv2'); await waitCount(pending, 2);
  const newer = structuredClone(settings); newer.settings.gatv2.network.hidden_dim = 96;
  await page.fulfil(pending[1].requestId, 200, newer);
  check('newest encoder settings are applied', await page.until(`${encoder}.value === 'gatv2' && ${hidden}.value === '96'`));
  const older = structuredClone(settings); older.settings.rgcn.network.hidden_dim = 80;
  await page.fulfil(pending[0].requestId, 200, older); await sleep(100);
  check('late encoder response cannot switch back', await page.evaluate(`${encoder}.value === 'gatv2' && ${hidden}.value === '96'`));

  await page.setValue(encoder, 'rgcn'); await waitCount(pending, 3);
  await page.setValue(hidden, '112', { event: 'input', focus: true });
  await page.fulfil(pending[2].requestId, 200, older); await sleep(100);
  check('manual network edit survives an outstanding settings read', await page.evaluate(`${encoder}.value === 'rgcn' && ${hidden}.value === '112'`));
  await page.evaluate(`${hidden}.blur()`);
  await sleep(800); // flush the intercepted preference write before reset
  await page.evaluate(`[...document.querySelectorAll('.right button')].find(b => b.textContent === 'Publication preset').click()`);
  await waitCount(resets, 1);
  await page.setValue(encoder, 'gatv2');
  check('switching encoders does not wait for an earlier reset', await page.until(`${encoder}.value === 'gatv2'`));
  await page.fulfil(resets[0].requestId, 200, { ...settings.settings.rgcn, origin: 'publication' });
  await waitCount(pending, 4); await page.fulfil(pending[3].requestId, 200, newer); await sleep(100);
  check('late reset cannot replace the selected encoder', await page.evaluate(`${encoder}.value === 'gatv2' && ${hidden}.value === '96'`));
  hold = false; await page.saved();
  await page.setValue(hidden, '112', { event: 'input', focus: true });
  await page.evaluate(`${hidden}.blur()`); await sleep(800);
  await page.evaluate(`[...document.querySelectorAll('.right button')].find(b => b.textContent === 'Publication preset').click()`);
  await waitCount(resets, 2);
  await page.evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('Undo restores a network edit while reset is pending', await page.until(`${encoder}.value === 'gatv2' && ${hidden}.value === '96'`));
  await page.fulfil(resets[1].requestId, 200, { ...settings.settings.gatv2, network: { ...settings.settings.gatv2.network, hidden_dim: 80 } });
  await sleep(100);
  check('late reset cannot overwrite Undo within the same encoder', await page.evaluate(`${hidden}.value === '96'`));
  await page.saved();

  const key = 'gator-workbench-config-v1';
  const before = (await page.stored()).parameters.length;
  await page.evaluate(`window.realSetItem = Storage.prototype.setItem; window.blockSave = true;
    Storage.prototype.setItem = function(k, v) { if (window.blockSave && k === '${key}') throw new DOMException('FIXTURE quota exceeded', 'QuotaExceededError'); return window.realSetItem.call(this, k, v); };`);
  const add = `document.querySelector('section.editors button[title^="Add:"]').click()`;
  await page.evaluate(add); await page.saved();
  check('failed autosave is visible and remains unsaved', await page.until(`document.querySelector('.persistence-problem')?.textContent.includes('could not be saved')`)
    && (await page.stored()).parameters.length === before);
  await page.evaluate(`window.exportedConfig = null; window.realObjectURL = URL.createObjectURL; window.realClick = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = function(blob) { blob.text().then(text => window.exportedConfig = JSON.parse(text)); return window.realObjectURL(blob); };
    HTMLAnchorElement.prototype.click = function() {};
    [...document.querySelectorAll('.persistence-problem button')].find(b => b.textContent === 'Export JSON').click();`);
  check('warning exports the current unsaved configuration', await page.until(`window.exportedConfig?.parameters.length === ${before + 1}`));
  await page.evaluate(`URL.createObjectURL = window.realObjectURL; HTMLAnchorElement.prototype.click = window.realClick;
    [...document.querySelectorAll('.persistence-problem button')].find(b => b.textContent === 'Retry save').click();`);
  check('a failed retry keeps the warning', await page.evaluate(`!!document.querySelector('.persistence-problem')`));
  await page.evaluate(`window.blockSave = false; [...document.querySelectorAll('.persistence-problem button')].find(b => b.textContent === 'Retry save').click();`);
  check('successful retry saves the latest edit and clears the warning', await page.until(`!document.querySelector('.persistence-problem')`)
    && (await page.stored()).parameters.length === before + 1);
  await page.evaluate('window.blockSave = true'); await page.evaluate(add); await page.saved();
  await page.evaluate(`window.blockSave = false; window.dispatchEvent(new Event('pagehide'));`);
  check('pagehide retries a previously failed dirty save', (await page.stored()).parameters.length === before + 2);
  await page.send('Page.reload');
  check('recovered edits survive reload', await page.until(`document.querySelectorAll('table.editor tbody tr').length === ${before + 2}`));
  await page.saved(); await sleep(700);

  await page.evaluate(`window.serializations = 0; window.realStringify = JSON.stringify;
    JSON.stringify = function(v, ...rest) { if (v?.schema_version === '${key}') ++window.serializations; return window.realStringify.call(this, v, ...rest); };
    [...document.querySelectorAll('footer .tabs button')].find(b => b.textContent.trim() === 'Agent').click();`);
  await sleep(100);
  check('bottom tab switch does not serialize the full configuration', await page.evaluate('window.serializations === 0'));
  await page.evaluate('JSON.stringify = window.realStringify');
  for (const width of [960, 640]) {
    await page.viewport(width, 900); await sleep(100);
    const geometry = await page.evaluate(`({ main: document.querySelector('main').getBoundingClientRect().width,
      page: document.documentElement.scrollWidth, width: innerWidth, box: document.querySelector('.compose-main textarea').getBoundingClientRect().width })`);
    check(`${width}px viewport keeps usable editors without page overflow`, geometry.main > width - 40 && geometry.page <= width, JSON.stringify(geometry));
    check(`${width}px viewport keeps the Agent message box usable`, geometry.box > 200, JSON.stringify(geometry));
  }
  await page.evaluate(`document.querySelector('main').scrollIntoView()`);
  await page.shot(path.join(out, 'reliability-narrow.png'));
  check('no unintended backend writes', page.refused.length === 0, JSON.stringify(page.refused));
  check('no browser exceptions', page.consoleErrors.length === 0, JSON.stringify(page.consoleErrors));
});
