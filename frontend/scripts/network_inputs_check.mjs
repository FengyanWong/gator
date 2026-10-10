// Browser check of the one "Network inputs" choice of the RL model window (record 7.298): New model offers Standard and
// Transferable; Transferable sets the three settings together (specs read as a set, sizes relative to the PDK, device
// model features) and the next run's line beside "RL model..." says "transferable"; Standard takes them back.
// A throwaway headless Edge over the DevTools protocol, as network_panel_check.mjs; every writing request of the page is
// refused here (reads pass), so it may run against a scratch backend only:
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:<port>/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/network_inputs_check.mjs)" [screenshot-dir]
// Exit code 1 if any check fails.
import { NETWORK_DOCUMENT, NETWORK_PANEL, openNetworks, setMode } from './lib/rl_networks.mjs';
import path from 'node:path';
import { check, launchEdge, outDir, runChecks, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('inputs');

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, consoleErrors } = page;
  await page.hold([], null, { others: 'read' });                       // reads pass, writes are refused
  await send('Page.navigate', { url: APP });
  await page.until(`!!document.querySelector('.rl-networks-open')`, 150);
  const popup = await openNetworks(page, browser);
  await setMode(popup, 'scratch');
  const SELECT = `${NETWORK_DOCUMENT}.querySelector('select.network-inputs')`;
  check('New model offers one "Network inputs" choice: Standard and Transferable', await page.until(`!!${SELECT}`, 50)
    && await evaluate(`[...${SELECT}.options].map(o => o.value).join(',')`) === 'standard,transferable',
    await evaluate(`${SELECT} && [...${SELECT}.options].map(o => o.textContent).join(' | ')`));
  check('a new configuration starts with the standard inputs', await evaluate(`${SELECT}.value`) === 'standard');
  const choose = value => evaluate(`(() => { const s = ${SELECT}; const set = Object.getOwnPropertyDescriptor(s.ownerDocument.defaultView.HTMLSelectElement.prototype, 'value').set;
    set.call(s, ${JSON.stringify(value)}); s.dispatchEvent(new s.ownerDocument.defaultView.Event('change', { bubbles: true })); })()`);
  const LINE = `document.querySelector('.rl-networks-row')?.textContent ?? ''`;
  await choose('transferable');
  check('Transferable is kept and the next run\'s line says so', await page.until(`${SELECT}.value === 'transferable' && (${LINE}).includes('transferable')`, 50),
    await evaluate(LINE));
  check('its tooltip says what the inputs are', (await evaluate(`${SELECT}.closest('label').title`)).includes('read as a set'));
  await popup.shot(path.join(out, 'network-inputs.png'), `${SELECT}.closest('label')`, { maxHeight: 200 });
  await choose('standard');
  check('Standard takes the three settings back', await page.until(`${SELECT}.value === 'standard' && !(${LINE}).includes('transferable')`, 50),
    await evaluate(LINE));
  // The component list of a new model is the device-family list (record 7.298): offered first, and choosing New model brings it.
  const LIST = `${NETWORK_DOCUMENT}.querySelector('.component-list select')`;
  check('Components offers the device families first', await evaluate(`${LIST}.options[0].value`) === 'families',
    await evaluate(`[...${LIST}.options].map(o => o.textContent).join(' | ')`));
  await setMode(popup, 'fine_tune');
  await setMode(popup, 'scratch');
  check('a new model takes the device families, and its line says so', await page.until(`${LIST}?.value === 'families' && (${LINE}).includes('families')`, 50),
    await evaluate(`${LIST}?.value + ' / ' + (${LINE})`));
  check('the standard list is no longer offered to a new model', !(await evaluate(`[...${LIST}.options].some(o => o.value === 'standard')`)));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join('\n'));
  void NETWORK_PANEL;
});
