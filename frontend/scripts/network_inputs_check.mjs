// Browser check of the one "Network inputs" choice of the RL model window (record 7.298): New model offers Standard and
// Transferable; Transferable sets the three settings together (specs read as a set, sizes relative to the PDK, device
// model features) and the next run's line beside "RL model..." says "transferable"; Standard takes them back.
// Since record 7.317 a third choice, Transferable 2, sets the second build's three settings as well (bench sources on
// their own scales, net tags by rule, operating-point ratios).
// Since record 7.332 a new model's inputs come with its encoder's template: no box, a line of text; a box only while a
// configuration holds another choice (a new configuration holds Standard until New model or a template is chosen).
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
  // Record 7.332 (user: "Yes, no box"): a new model's inputs come with its encoder's template - Transferable 2 here - so
  // the box is one line of text. A configuration that still holds another choice (a new one holds Standard) shows a box
  // with that choice and the encoder's own; choosing New model brings the encoder's inputs, and the box is gone.
  const SELECT = `${NETWORK_DOCUMENT}.querySelector('select.network-inputs')`;
  const TEXT = `(${NETWORK_DOCUMENT}.querySelector('.network-inputs-line')?.textContent ?? '')`;
  const LINE = `document.querySelector('.rl-networks-row')?.textContent ?? ''`;
  check('a new configuration still holds Standard: a box with it and the new model\'s inputs, nothing else', await page.until(`!!${SELECT}`, 50)
    && await evaluate(`[...${SELECT}.options].map(o => o.value).join(',')`) === 'transferable2,standard' && await evaluate(`${SELECT}.value`) === 'standard',
    await evaluate(`${SELECT} && [...${SELECT}.options].map(o => o.textContent).join(' | ')`));
  check('its tooltip says what the inputs are', (await evaluate(`${SELECT}.closest('label').title`)).includes('read as a set'));
  await popup.shot(path.join(out, 'network-inputs.png'), `${SELECT}.closest('label')`, { maxHeight: 200 });
  await setMode(popup, 'fine_tune');
  await setMode(popup, 'scratch');
  check('choosing New model brings the new model\'s inputs: the box is gone and a line names them', await page.until(`!${SELECT}
    && ${TEXT}.includes('Network inputs: Transferable 2') && (${LINE}).includes('transferable 2')`, 50), await evaluate(`${TEXT} + ' / ' + (${LINE})`));
  check('the line\'s tooltip lists what the network reads', (await evaluate(`document.querySelector('.rl-networks-row .net-short')?.title ?? ''`)).includes('operating-point ratios'));
  // Branch record SIF-80: the inputs in words begin with the choice's name ("transferable 2: ..." before), and the window's
  // line names it once, what it reads in brackets.
  const named = [await evaluate(TEXT), await evaluate(`document.querySelector('.rl-networks-row .net-short')?.title ?? ''`)];
  check('... by the choice\'s name, once: "Network inputs: Transferable 2 (specs read as a set, ...)", "inputs Transferable 2 - specs read as a set, ..." on hover (SIF-80)',
    /^Network inputs: Transferable 2 \(specs read as a set, [^()]*operating-point ratios\)$/.test(named[0]) && named[1].includes('inputs Transferable 2 - specs read as a set, '), JSON.stringify(named));
  await popup.shot(path.join(out, 'network-inputs-2.png'), `${NETWORK_DOCUMENT}.querySelector('.network-inputs-line')`, { maxHeight: 200 });
  // The component list of a new model is the device-family list (record 7.298): offered first, and choosing New model brings it.
  const LIST = `${NETWORK_DOCUMENT}.querySelector('.component-list select')`;
  check('Components offers the device families first', await evaluate(`${LIST}.options[0].value`) === 'families',
    await evaluate(`[...${LIST}.options].map(o => o.textContent).join(' | ')`));
  check('a new model takes the device families, and its line says so', await page.until(`${LIST}?.value === 'families' && (${LINE}).includes('families')`, 50),
    await evaluate(`${LIST}?.value + ' / ' + (${LINE})`));
  check('the standard list is no longer offered to a new model', !(await evaluate(`[...${LIST}.options].some(o => o.value === 'standard')`)));
  check('no console errors', consoleErrors.length === 0, consoleErrors.join('\n'));
  void NETWORK_PANEL;
});
