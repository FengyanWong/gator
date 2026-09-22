// Browser check of the "RL network" block of the run panel (there is no frontend test runner in this project).
// Same approach as agent_tab_check.mjs: a throwaway headless Edge over the DevTools protocol against the RUNNING
// workbench (default http://127.0.0.1:8765/). GET /api/network-settings is answered by the real backend; every
// PUT/POST to /api/network-settings/* is intercepted and answered with a canned entry, so nothing is ever written
// to the user's network_settings.json. Any other writing request of the page is refused here (reads pass): hermetic.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/network_panel_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import path from 'node:path';
import { check, fail, finish, launchEdge, outDir, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('net');

try {
  const page = await browser.open();
  const { send, evaluate, fulfil, consoleErrors, paused } = page;
  const nextWrite = async (ms = 4000) => {
    for (let waited = 0; waited < ms; waited += 50) { if (paused.length) return paused.shift(); await sleep(50); }
    return null;
  };

  // The run panel is the first panel of the right column; its "RL network" block starts at that heading.
  const H3 = `[...document.querySelectorAll('.right .panel h3')].find(h => h.textContent.trim() === 'RL network')`;
  const BLOCK = `(() => { const h = ${H3}; const items = []; for (let n = h; n && !(n !== h && n.tagName === 'H3') && n.tagName !== 'DETAILS'; n = n.nextElementSibling) items.push(n); return items; })()`;
  const shot = async name => {
    await evaluate(`${H3}.scrollIntoView({ block: 'start' })`);
    await sleep(150);
    await page.shot(path.join(out, name), await evaluate(`(() => { const items = ${BLOCK}; const a = items[0].getBoundingClientRect(), b = items[items.length - 1].getBoundingClientRect();
      const p = document.querySelector('.right .panel').getBoundingClientRect(); return { x: p.x, y: a.y - 4, width: p.width, height: b.bottom - a.y + 8, scale: 2 }; })()`));
  };
  const select = name => evaluate(`(() => { const s = [...document.querySelectorAll('.right .panel label')].find(l => l.firstChild?.textContent === 'Encoder').querySelector('select');
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, ${JSON.stringify(name)}); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const box = label => `[...document.querySelectorAll('.right .panel .row label')].find(l => l.querySelector('span')?.firstChild?.textContent === ${JSON.stringify(label)})`;
  const numbers = () => evaluate(`['hidden', 'heads', 'layers'].map(n => [...document.querySelectorAll('.right .panel .row label')].find(l => l.querySelector('span')?.firstChild?.textContent === n).querySelector('input').value)`);
  const buttons = () => evaluate(`['Publication preset', 'GATOR baseline'].map(t => { const b = [...document.querySelectorAll('.right .panel button')].find(x => x.textContent === t);
    const r = b.getBoundingClientRect(); return { text: t, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), disabled: b.disabled }; })`);

  await page.hold(['*/api/network-settings/*'], null, { others: 'read' });     // the writes wait here; the page's other requests: reads pass
  await send('Page.navigate', { url: APP });
  for (let i = 0; i < 100 && !(await evaluate(`!!(${H3})`)); i++) await sleep(100);
  for (let i = 0; i < 50 && !(await evaluate(`[...document.querySelectorAll('.right .panel button')].some(b => b.textContent === 'GATOR baseline')`)); i++) await sleep(100);
  await sleep(600);
  const settings = await (await fetch(new URL('api/network-settings', APP))).json();

  // ---- a fresh configuration takes the backend's values for the default encoder ------------------------------
  const gt = settings.settings.graph_transformer.network;
  check('fresh page shows the backend values of the default encoder', JSON.stringify(await numbers()) === JSON.stringify([gt.hidden_dim, gt.heads, gt.layers].map(String)), JSON.stringify(await numbers()));
  check('heads is editable for graph_transformer', !(await evaluate(`${box('heads')}.querySelector('input').disabled`)));

  // ---- the two reset buttons form one aligned pair ------------------------------------------------------------
  let [pub, base] = await buttons();
  check('reset buttons share one line', pub.y === base.y, JSON.stringify([pub, base]));
  check('reset buttons have the same size', pub.w === base.w && pub.h === base.h, `${pub.w}x${pub.h} vs ${base.w}x${base.h}`);
  const panel = await evaluate(`(() => { const s = getComputedStyle(document.querySelector('.right .panel')); const r = document.querySelector('.right .panel').getBoundingClientRect();
    return { left: Math.round(r.x + parseFloat(s.paddingLeft)), right: Math.round(r.right - parseFloat(s.paddingRight)) }; })()`);
  check('reset buttons span the panel like the number boxes above them', Math.abs(pub.x - panel.left) <= 1 && Math.abs(base.x + base.w - panel.right) <= 1, JSON.stringify({ pub, base, panel }));
  await shot('network-1-graph-transformer.png');

  // ---- choosing an encoder reads that encoder's backend values; heads greys out -------------------------------
  await select('gcn'); await sleep(500);
  const gcn = settings.settings.gcn.network;
  check('choosing gcn loads the gcn values', JSON.stringify(await numbers()) === JSON.stringify([gcn.hidden_dim, gcn.heads, gcn.layers].map(String)), JSON.stringify(await numbers()));
  check('heads is greyed out for gcn', await evaluate(`${box('heads')}.querySelector('input').disabled && ${box('heads')}.classList.contains('disabled')`));
  check('heads carries the "ignored by this encoder" hint', await evaluate(`${box('heads')}.textContent.includes('ignored by this encoder')`));
  [pub, base] = await buttons();
  check('reset buttons stay aligned when the heads hint is shown', pub.y === base.y && pub.w === base.w, JSON.stringify([pub, base]));
  check('no write happened by only choosing an encoder', paused.length === 0, JSON.stringify(paused.map(p => p.method + ' ' + p.url)));
  await shot('network-2-gcn.png');

  // ---- editing a value writes it to the backend for THAT encoder (intercepted here) ---------------------------
  await evaluate(`(() => { const i = ${box('hidden')}.querySelector('input'); i.focus(); i.select(); })()`);
  await send('Input.insertText', { text: '64' });
  const write = await nextWrite();
  check('an edit is sent to the backend for the chosen encoder', !!write && write.method === 'PUT' && write.url.endsWith('/api/network-settings/gcn'), write ? `${write.method} ${write.url}` : 'no request');
  const body = write ? JSON.parse(write.postData) : {};
  check('the complete value set is sent, not one field', body.network?.hidden_dim === 64 && body.network?.layers === gcn.layers && typeof body.advanced?.batch_size === 'number', JSON.stringify(body.network));
  if (write) await fulfil(write.requestId, 200, { ...settings.settings.gcn, origin: 'custom', network: { ...gcn, hidden_dim: 64 } });
  await sleep(400);
  check('the panel reports the edited state', await evaluate(`document.querySelector('.right .panel').textContent.includes('edited, saved in the backend')`));
  await shot('network-3-gcn-edited.png');

  // ---- GATOR baseline asks the backend (intercepted) and applies what it answers ------------------------------
  await evaluate(`[...document.querySelectorAll('.right .panel button')].find(b => b.textContent === 'GATOR baseline').click()`);
  const reset = await nextWrite();
  check('GATOR baseline posts a reset for the chosen encoder', !!reset && reset.method === 'POST' && reset.url.endsWith('/api/network-settings/gcn/reset') && JSON.parse(reset.postData).to === 'gator_baseline', reset ? `${reset.method} ${reset.url} ${reset.postData}` : 'no request');
  if (reset) await fulfil(reset.requestId, 200, { ...settings.settings.gcn, origin: 'gator_baseline', network: settings.gator_baseline.network, advanced: settings.gator_baseline.advanced });
  await sleep(400);
  const b = settings.gator_baseline.network;
  check('the baseline values are shown', JSON.stringify(await numbers()) === JSON.stringify([b.hidden_dim, b.heads, b.layers].map(String)), JSON.stringify(await numbers()));
  await shot('network-4-gcn-baseline.png');

  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
} catch (error) {
  fail(error);
} finally {
  await browser.close();
}
finish();
