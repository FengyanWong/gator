// Drive the real launcher; keep API interception on the workbench page, where the React portal's requests originate.
// The window reference is installed only by these checks, not exposed by the application.
export const NETWORK_DOCUMENT = 'window.__checkRLWindow.document';
export const NETWORK_PANEL = `${NETWORK_DOCUMENT}.querySelector('.rl-networks-panel')`;

export async function openNetworks(page, browser) {
  if (!await page.until(`!!document.querySelector('button.rl-networks-open')`, 150)) throw new Error('RL networks launcher did not appear');
  await page.evaluate(`(() => {
    const button = document.querySelector('button.rl-networks-open');
    if (button.disabled) throw new Error('RL networks launcher is disabled');
    const open = window.open;
    window.open = function(...args) { return window.__checkRLWindow = open.apply(this, args); };
    try { button.click(); } finally { window.open = open; }
  })()`, true);
  const popup = await browser.attach(await browser.window('GATOR - RL networks'), { errors: page.consoleErrors, prefix: 'RL networks: ' });
  await popup.evaluate('void (window.__checkRLWindow = window)');
  await popup.viewport(1100, 900);
  if (!await popup.until(`!!document.querySelector('.rl-networks-panel')`)) throw new Error('RL networks content did not appear');
  return popup;
}
