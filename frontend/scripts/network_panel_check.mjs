// Browser check of the RL model window (the RL networks window until record 7.265) and its launcher in Run configuration.
// Record 7.265: Mode and the RL model label moved into the window; New model's encoder is chosen in its templates table
// ("Use template"), and the template's settings follow under "The ... template, for this run".
// Same approach as agent_window_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). GET /api/network-settings is answered by the real backend; every
// PUT/POST to /api/network-settings/* is intercepted and answered with a canned entry, so nothing is ever written
// to the user's network_settings.json. Any other writing request of the page is refused here (reads pass): hermetic.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/network_panel_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { NETWORK_DOCUMENT, NETWORK_PANEL, openNetworks } from './lib/rl_networks.mjs';
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, sleep, workbenchUrl, RL_MODEL_WINDOW, PRESET_RATE_KEY } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('net');

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors, paused } = page;
  const nextWrite = async (ms = 4000) => {
    for (let waited = 0; waited < ms; waited += 50) { if (paused.length) return paused.shift(); await sleep(50); }
    return null;
  };

  // The controls live in the named window; their React requests still originate in the workbench page.
  const H3 = `[...${NETWORK_DOCUMENT}.querySelectorAll('.rl-networks-panel h3')].find(h => / template, for this run$/.test(h.textContent.trim()))`;
  // The block runs to the next heading or fold; the Advanced fold inside it (record 7.195) is part of it.
  const BLOCK = `(() => { const h = ${H3}; const items = []; for (let n = h; n && !(n !== h && n.tagName === 'H3') && (n.tagName !== 'DETAILS' || n.classList.contains('rl-advanced')); n = n.nextElementSibling) items.push(n); return items; })()`;
  const shot = async name => {
    await evaluate(`${H3}.scrollIntoView({ block: 'start' })`);
    await sleep(150);
    await networkPage.shot(path.join(out, name), await evaluate(`(() => { const items = ${BLOCK}; const a = items[0].getBoundingClientRect(), b = items[items.length - 1].getBoundingClientRect();
      const p = ${NETWORK_PANEL}.getBoundingClientRect(); return { x: p.x, y: a.y - 4, width: p.width, height: b.bottom - a.y + 8, scale: 2 }; })()`));
  };
  const select = name => page.evaluate(`${NETWORK_DOCUMENT}.querySelector('tr.template-row[data-encoder="${name}"] button.template-use')?.click()`);   // "Use template" (no-op for the one in use)
  const box = label => `[...${NETWORK_DOCUMENT}.querySelectorAll('.rl-networks-panel .row label')].find(l => l.querySelector('span')?.firstChild?.textContent === ${JSON.stringify(label)})`;
  const numbers = () => evaluate(`['hidden', 'heads', 'layers'].map(n => [...${NETWORK_DOCUMENT}.querySelectorAll('.rl-networks-panel .row label')].find(l => l.querySelector('span')?.firstChild?.textContent === n).querySelector('input').value)`);
  const IN_USE = `${NETWORK_PANEL}.querySelector('.in-use')?.textContent`;

  await page.hold(['*/api/network-settings/*'], null, { others: 'read' });     // the writes wait here; the page's other requests: reads pass
  await send('Page.navigate', { url: APP });
  await page.until(`!!document.querySelector('.rl-networks-open')`, 150);
  const layout = await evaluate(`(() => {
    const body = document.querySelector('.right .module-body');
    const labels = [...body.querySelectorAll('label')].map(l => l.firstChild.textContent.trim());
    const button = body.querySelector('.rl-networks-open');
    // the button stands in one row with the next run's model in short (user, 2026-10-03; record 7.265): the module's first row
    return { labels: labels.slice(0, 2), first: body.firstElementChild === button.closest('.rl-networks-row'), moved: !labels.includes('Mode') && !labels.includes('RL model label'),
      inlineNetwork: !!body.querySelector('.component-list, .template-table, .saved-models'), search: !!document.querySelector('select[aria-label="Search method"]'),
      windows: !!window.__checkRLWindow, stopRules: body.textContent.includes('Stop after N consecutive failed evaluations') };
  })()`);
  check('RL model... and the next run\'s model come first; Mode and the RL model label are in the RL model window (record 7.265); no Search method (7.226)',
    layout.first && layout.moved && layout.labels[0] === 'Concurrent Spectre jobs' && !layout.search, JSON.stringify(layout));
  check('network content starts closed and failure limits stay in Run configuration', !layout.inlineNetwork && !layout.windows && layout.stopRules);
  await page.shot(path.join(out, 'run-configuration.png'), `document.querySelector('.right .panel')`, { maxHeight: 900 });
  await evaluate(`(() => { const open = window.open; window.open = () => null;
    try { document.querySelector('.rl-networks-open').click(); } finally { window.open = open; } })()`, true);
  check('a blocked popup explains how to reopen it', await page.until(`document.querySelector('.right .error')?.textContent.includes('blocked the new window')`));
  let networkPage = await openNetworks(page, browser);
  check('the window has no close button of its own (user, 2026-10-03): the browser closes it', await networkPage.evaluate(`!document.querySelector('.rl-networks-heading button')`));
  check('opening succeeds after a blocked attempt and clears the message', !await evaluate(`document.querySelector('.right').textContent.includes('blocked the new window')`));
  const originalWindow = networkPage.target.id;
  await evaluate(`document.querySelector('.rl-networks-open').click()`, true);
  check('pressing the launcher again reuses the same window', (await browser.pages()).filter(p => p.title === RL_MODEL_WINDOW).length === 1 && (await browser.window('GATOR - RL model')).id === originalWindow);
  for (let i = 0; i < 100 && !(await evaluate(`!!(${H3})`)); i++) await sleep(100);
  for (let i = 0; i < 50 && !(await evaluate(`!!${NETWORK_PANEL}.querySelector('.in-use')`)); i++) await sleep(100);
  await sleep(600);
  const settings = await (await fetch(new URL('api/network-settings', APP))).json();

  // ---- a fresh configuration takes the backend's values for the default encoder ------------------------------
  const gt = settings.settings.graph_transformer.network;
  check('fresh page shows the backend values of the default encoder', JSON.stringify(await numbers()) === JSON.stringify([gt.hidden_dim, gt.heads, gt.layers].map(String)), JSON.stringify(await numbers()));
  const short = await evaluate(`(() => { const e = document.querySelector('.rl-networks-row .net-short'); return e && { text: e.textContent, title: e.title, left: e.getBoundingClientRect().right <= document.querySelector('.rl-networks-open').getBoundingClientRect().left }; })()`);
  check('beside the button, the next run\'s model in short: New model, its template, GT hidden/heads/layers; left of the button, the whole of it in the tooltip',
    /^New model · .+ template · GT /.test(short?.text ?? '') && short.text.includes(`GT ${gt.hidden_dim}/${gt.heads}/${gt.layers}`) && short.left
    && short.title.startsWith('The network in use: graph_transformer'), JSON.stringify(short));
  const options = await evaluate(`[...${NETWORK_DOCUMENT}.querySelectorAll('tr.template-row')].map(r => r.dataset.encoder)`);
  check('the templates table offers all six backend encoders, one row each', JSON.stringify(options) === JSON.stringify(['graph_transformer', 'rgcn', 'gatv2', 'graph_gps', 'group_cross_attention', 'circuit_gps']), JSON.stringify(options));
  // Branch record SIF-8: "(experimental)" once at most; the fold under the template names the design, not its key.
  const words = await evaluate(`({ rows: [...${NETWORK_DOCUMENT}.querySelectorAll('tr.template-row td:first-child')].map(td => td.textContent),
    fold: [...${NETWORK_DOCUMENT}.querySelectorAll('summary')].map(x => x.textContent).find(t => /^Where the .+ values come from$/.test(t)) ?? null })`);
  check('each template says "experimental" once at most, and the fold names the design (Graph Transformer), not its key (SIF-8)',
    words.rows.length === 6 && words.rows.every(t => (t.match(/experimental/gi) ?? []).length <= 1) && words.fold === 'Where the Graph Transformer values come from', JSON.stringify(words));
  check('the mode is New model: the window\'s Mode buttons say so', await evaluate(`${NETWORK_DOCUMENT}.querySelector('.rl-modes button[aria-checked="true"]')?.dataset.mode`) === 'scratch');
  for (const encoder of ['graph_gps', 'group_cross_attention', 'circuit_gps']) {
    await select(encoder);
    const STRUCTURE = `${NETWORK_PANEL}.querySelector('select.structural-encoding')`;
    check(`${encoder}: structural settings and experimental status are visible`, await page.until(`!!${STRUCTURE} && !!${NETWORK_PANEL}.querySelector('.encoder-experimental')`));
    check(`${encoder}: its own structural default is loaded`, await evaluate(`${STRUCTURE}.value`) === settings.settings[encoder].network.structural_encoding);
    if (encoder === 'circuit_gps') {
      // Since record 7.332 a template brings its encoder's whole input set and the window says it in one line (no box).
      check('CircuitGPS brings Structured + Transferable 2 with its template', await page.until(`(${NETWORK_PANEL}.querySelector('.network-inputs-line')?.textContent ?? '').includes('Structured + Transferable 2')`),
        await evaluate(`(${NETWORK_PANEL}.querySelector('.network-inputs-line')?.textContent ?? '') + ' / box: ' + (${NETWORK_PANEL}.querySelector('select.network-inputs')?.value ?? 'none')`));
    }
    await page.setValue(STRUCTURE, encoder === 'graph_gps' ? 'none' : 'rwse');
    const changed = await nextWrite();
    const body = changed ? JSON.parse(changed.postData) : {};
    check(`${encoder}: structural edits are included in the saved settings`, changed?.url.endsWith(`/api/network-settings/${encoder}`)
      && body.network?.structural_encoding === (encoder === 'graph_gps' ? 'none' : 'rwse'));
    if (changed) await fulfil(changed.requestId, 200, { ...settings.settings[encoder], ...body, origin: 'custom' });
  }
  await select('graph_transformer');
  await page.until(`!${NETWORK_PANEL}.querySelector('select.structural-encoding')`);
  check('heads is editable for graph_transformer', !(await evaluate(`${box('heads')}.querySelector('input').disabled`)));
  // record 7.195 (user: "move the advanced setting to beneath the nominal device op checkbox")
  const order = await evaluate(`(() => { const box = [...${NETWORK_PANEL}.querySelectorAll('label.check')].find(l => l.textContent === 'Nominal device operating points');
    let n = box?.nextElementSibling; while (n?.matches('p.sac-values')) n = n.nextElementSibling;
    const fold = ${NETWORK_PANEL}.querySelectorAll('details.rl-advanced');
    return { below: !!n?.matches('details.rl-advanced'), one: fold.length === 1, closed: fold[0]?.open === false,
      before: !!(fold[0] && ${NETWORK_PANEL}.querySelector('.component-list') && (fold[0].compareDocumentPosition(${NETWORK_PANEL}.querySelector('.component-list')) & Node.DOCUMENT_POSITION_FOLLOWING)) }; })()`);
  check('the Advanced fold sits directly below "Nominal device operating points", closed, once, above the component list', order.below && order.one && order.closed && order.before, JSON.stringify(order));

  // ---- one setting: the starting preset (record 7.192); no preset buttons (record 7.191) -----------------------
  check('neither "Publication preset" nor "GATOR baseline" is a button any more', !(await evaluate(`[...${NETWORK_DOCUMENT}.querySelectorAll('.rl-networks-panel button')]
    .some(b => ['Publication preset', 'GATOR baseline'].includes(b.textContent.trim()))`)));
  check('the window never names the GATOR baseline', !(await evaluate(`${NETWORK_PANEL}.textContent.includes('GATOR baseline')`)));
  const gtOrigin = settings.settings.graph_transformer.origin;
  check('"In use" names what the backend holds for the default encoder', await evaluate(IN_USE) === `In use: ${gtOrigin === 'publication' ? 'starting preset' : 'edited, saved in the backend'}`
    && ['publication', 'custom'].includes(gtOrigin), `${await evaluate(IN_USE)} (backend: ${gtOrigin})`);
  await shot('network-1-graph-transformer.png');

  // ---- choosing an encoder reads that encoder's backend values; heads greys out -------------------------------
  await select('rgcn'); await sleep(500);
  const rgcn = settings.settings.rgcn.network;
  check('choosing rgcn loads the rgcn values', JSON.stringify(await numbers()) === JSON.stringify([rgcn.hidden_dim, rgcn.heads, rgcn.layers].map(String)), JSON.stringify(await numbers()));
  check('heads is greyed out for rgcn', await evaluate(`${box('heads')}.querySelector('input').disabled && ${box('heads')}.classList.contains('disabled')`));
  check('heads carries the "ignored by this encoder" hint', await evaluate(`${box('heads')}.textContent.includes('ignored by this encoder')`));
  check('no write happened by only choosing an encoder', paused.length === 0, JSON.stringify(paused.map(p => p.method + ' ' + p.url)));
  await shot('network-2-rgcn.png');

  // ---- editing a value writes it to the backend for THAT encoder (intercepted here) ---------------------------
  await evaluate(`(() => { const i = ${box('hidden')}.querySelector('input'); i.focus(); i.select(); })()`);
  await networkPage.send('Input.insertText', { text: '64' });
  // Close before the debounced write returns: closing the view must not abandon a valid edit or its preference save.
  await networkPage.evaluate('window.close()');                                  // the window's own close (it has no button of its own)
  await browser.window(RL_MODEL_WINDOW, { present: false });
  const write = await nextWrite();
  check('an edit is sent to the backend for the chosen encoder', !!write && write.method === 'PUT' && write.url.endsWith('/api/network-settings/rgcn'), write ? `${write.method} ${write.url}` : 'no request');
  const body = write ? JSON.parse(write.postData) : {};
  check('the complete value set is sent, not one field', body.network?.hidden_dim === 64 && body.network?.layers === rgcn.layers && typeof body.advanced?.batch_size === 'number', JSON.stringify(body.network));
  if (write) await fulfil(write.requestId, 200, { ...settings.settings.rgcn, origin: 'custom', network: { ...rgcn, hidden_dim: 64 } });
  await sleep(400);
  networkPage = await openNetworks(page, browser);
  check('closing and reopening keeps the edited network', (await numbers())[0] === '64' && await evaluate(`${NETWORK_PANEL}.textContent.includes('edited, saved in the backend')`));
  check('the panel reports the edited state', await evaluate(`${NETWORK_PANEL}.textContent.includes('edited, saved in the backend')`));
  await shot('network-3-rgcn-edited.png');

  // ---- the way back without a button: typing the preset value again (the backend then forgets its copy) ---------
  await evaluate(`(() => { const i = ${box('hidden')}.querySelector('input'); i.focus(); i.select(); })()`);
  await networkPage.send('Input.insertText', { text: String(rgcn.hidden_dim) });
  const back = await nextWrite();
  check('typing the preset value back sends it for the chosen encoder', !!back && back.method === 'PUT' && back.url.endsWith('/api/network-settings/rgcn')
    && JSON.parse(back.postData).network?.hidden_dim === rgcn.hidden_dim, back ? `${back.method} ${back.url} ${back.postData}` : 'no request');
  if (back) await fulfil(back.requestId, 200, { ...settings.settings.rgcn, origin: 'publication' });
  check('...and the window says the starting preset is in use again', await page.until(`${IN_USE} === 'In use: starting preset'`)
    && (await numbers())[0] === String(rgcn.hidden_dim), `${await evaluate(IN_USE)} ${JSON.stringify(await numbers())}`);
  await shot('network-4-rgcn-preset-again.png');

  const alpha = `[...${NETWORK_PANEL}.querySelectorAll('label')].find(l => l.firstChild.textContent === 'Alpha learning rate').querySelector('input')`;
  await evaluate(`${alpha}.closest('details').open = true`);
  await evaluate(`${alpha}.focus()`);
  for (const key of '0.003') {
    await networkPage.send('Input.dispatchKeyEvent', { type: 'keyDown', key, text: key, unmodifiedText: key });
    await networkPage.send('Input.dispatchKeyEvent', { type: 'keyUp', key });
  }
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('typing in the network window is one Undo step', await page.until(`${alpha}.value === ''`));
  await evaluate(`document.querySelector('section.editors button[title^="Redo:"]').click()`);
  check('Redo restores the complete value typed in the window', await page.until(`${alpha}.value === '0.003'`));
  await page.setValue(alpha, '0.004', { event: 'input', focus: true });
  await evaluate(`${alpha}.blur()`);
  await page.setValue(alpha, '0.005', { event: 'input', focus: true });
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('leaving and re-entering the field starts a separate Undo step', await page.until(`${alpha}.value === '0.004'`));
  await page.setValue(alpha, '', { event: 'input' });

  check('the network controls and their values are there (SAC is the only search method)', await page.until(`!document.querySelector('.rl-networks-open').disabled && !!${NETWORK_PANEL}.querySelector('.component-list')`) && (await numbers())[0] === String(rgcn.hidden_dim));
  await networkPage.evaluate('window.close()');
  await browser.window(RL_MODEL_WINDOW, { present: false });
  networkPage = await openNetworks(page, browser);
  check('the browser close button also permits reopening', await networkPage.evaluate(`!!document.querySelector('.component-list')`));
  await send('Page.reload');
  await browser.window(RL_MODEL_WINDOW, { present: false });
  check('reloading the workbench closes its network window', !(await browser.pages()).some(p => p.title === RL_MODEL_WINDOW));

  // A restored configuration can intentionally differ from the remembered encoder defaults, including Advanced.
  await page.until(`!!document.querySelector('.rl-networks-open')`, 150);
  const restored = await page.stored();
  restored.run = { ...restored.run, mode: 'scratch',
    network: { encoder_type: 'graph_transformer', ...gt, hidden_dim: settings.legacy_baseline.network.hidden_dim },
    advanced: { ...settings.settings.graph_transformer.advanced, initial_alpha: settings.legacy_baseline.advanced.initial_alpha } };
  await page.seed({ config: restored });
  await send('Page.reload');
  networkPage = await openNetworks(page, browser);
  const differences = `${NETWORK_PANEL}.querySelector('.network-differences')`;
  check('a restored configuration keeps its own values and shows the comparison', await page.until(`!!${differences}`)
    && (await numbers())[0] === String(restored.run.network.hidden_dim) && paused.length === 0);
  const compared = await evaluate(`[...${differences}.querySelectorAll('tbody tr')].map(r => [...r.cells].map(c => c.textContent))`);
  check('the comparison names the differing network and Advanced values exactly', JSON.stringify(compared) === JSON.stringify([
    ['Hidden width', String(restored.run.network.hidden_dim), String(gt.hidden_dim)],
    ['Initial alpha', String(restored.run.advanced.initial_alpha), String(settings.settings.graph_transformer.advanced.initial_alpha)],
  ]), JSON.stringify(compared));
  check('In use identifies current run settings instead of falsely claiming the preset', await evaluate(`${NETWORK_PANEL}.querySelector('.in-use').textContent === 'In use: current run settings'`));
  check('the comparison explains which values run and where saved defaults apply', await evaluate(`${differences}.textContent.includes('This run uses the values shown in the controls') && ${differences}.textContent.includes('starting preset')`));
  await networkPage.shot(path.join(out, 'network-5-restored-differences.png'), NETWORK_PANEL, { maxHeight: 1100, beyond: true });
  await evaluate(`[...${differences}.querySelectorAll('button')].find(b => b.textContent === 'Use saved defaults').click()`);
  check('Use saved defaults updates this run, clears the comparison and does not write preferences', await page.until(`!${differences}`)
    && (await numbers())[0] === String(gt.hidden_dim) && paused.length === 0);
  check('a matching configuration can accurately name the starting preset', await evaluate(`${NETWORK_PANEL}.querySelector('.in-use').textContent === 'In use: starting preset'`));
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('Undo restores the differing values and their comparison', await page.until(`!!${differences}`) && (await numbers())[0] === String(restored.run.network.hidden_dim));
  await evaluate(`[...${differences}.querySelectorAll('button')].find(b => b.textContent === 'Save as defaults').click()`);
  const saveDefaults = await nextWrite();
  const defaultsBody = saveDefaults ? JSON.parse(saveDefaults.postData) : {};
  check('Save as defaults stores both network and Advanced values for this encoder', saveDefaults?.method === 'PUT'
    && saveDefaults.url.endsWith('/api/network-settings/graph_transformer')
    && defaultsBody.network.hidden_dim === restored.run.network.hidden_dim && defaultsBody.advanced.initial_alpha === restored.run.advanced.initial_alpha);
  if (saveDefaults) await fulfil(saveDefaults.requestId, 200, { ...settings.settings.graph_transformer, ...defaultsBody, origin: 'custom' });
  check('after saving, the comparison clears and the current run values stay', await page.until(`!${differences}`)
    && (await numbers())[0] === String(restored.run.network.hidden_dim)
    && await evaluate(`${NETWORK_PANEL}.querySelector('.in-use').textContent.includes('edited, saved in the backend')`));

  // The screenshot's stale rate is the sole difference from the old starting preset. The one-time browser upgrade
  // follows the current preset, without saving preferences or repeatedly undoing an intentional choice of 3e-4.
  const rateMigrationKey = PRESET_RATE_KEY;
  const oldPreset = { ...restored, run: { ...restored.run,
    network: { encoder_type: 'graph_transformer', ...gt, operating_points: true },
    advanced: { ...settings.settings.graph_transformer.advanced, learning_rate: 0.0003 } } };
  const restorePreset = async (config, firstVisit = true) => {
    await page.seed({ config });
    if (firstVisit) await evaluate(`localStorage.removeItem(${JSON.stringify(rateMigrationKey)})`);
    await send('Page.reload');
    networkPage = await openNetworks(page, browser);
    await page.until(`localStorage.getItem(${JSON.stringify(rateMigrationKey)}) === 'checked'`);
    await page.until(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.network.operating_points === true`);
  };
  await restorePreset(oldPreset);
  check('the restored old preset upgrades its learning rate and clears the mismatch',
    await page.until(`!!${NETWORK_PANEL}.querySelector('.preset-rate-updated') && !${differences}`)
    && await evaluate(`${IN_USE} === 'In use: starting preset'`));
  check('the upgraded rate is persisted without changing any other configuration value or writing preferences',
    await page.until(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.advanced.learning_rate === 0.001`)
    && JSON.stringify(await page.stored()) === JSON.stringify({ ...oldPreset, run: { ...oldPreset.run,
      advanced: { ...oldPreset.run.advanced, learning_rate: 0.001 } } }) && paused.length === 0);
  await networkPage.shot(path.join(out, 'network-6-preset-rate-updated.png'), NETWORK_PANEL, { maxHeight: 1100, beyond: true });
  await evaluate(`document.querySelector('section.editors button[title^="Undo:"]').click()`);
  check('one Undo restores the old learning rate and removes the update notice',
    await page.until(`!!${differences} && !${NETWORK_PANEL}.querySelector('.preset-rate-updated')`)
    && await evaluate(`${differences}.textContent.includes('0.0003')`));
  await page.until(`JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.advanced.learning_rate === 0.0003`);
  await restorePreset(await page.stored(), false);
  check('reloading after Undo keeps the chosen old rate instead of upgrading again',
    await page.until(`!!${differences}`) && (await page.stored()).run.advanced.learning_rate === 0.0003);
  const customPreset = { ...oldPreset, run: { ...oldPreset.run,
    network: { ...oldPreset.run.network, hidden_dim: gt.hidden_dim * 2 } } };
  await restorePreset(customPreset);
  check('a configuration with other custom values keeps its own learning rate on first visit',
    await page.until(`!!${differences}`) && (await page.stored()).run.advanced.learning_rate === 0.0003
    && !await evaluate(`!!${NETWORK_PANEL}.querySelector('.preset-rate-updated')`));
  await restorePreset({ ...oldPreset, run: { ...oldPreset.run, mode: 'fine_tune' } });
  check('loading a saved model never upgrades the restored learning rate',
    (await page.stored()).run.advanced.learning_rate === 0.0003
    && !await evaluate(`!!${NETWORK_PANEL}.querySelector('.preset-rate-updated')`) && paused.length === 0);

  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
