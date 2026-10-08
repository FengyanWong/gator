// Drive the real launcher; keep API interception on the workbench page, where the React portal's requests originate.
// The window reference is installed only by these checks, not exposed by the application. Since record 7.265 it is the
// "RL model" window (it was "RL networks"); the Mode is chosen in it (setMode), no longer in Run configuration.
export const NETWORK_DOCUMENT = 'window.__checkRLWindow.document';
export const NETWORK_PANEL = `${NETWORK_DOCUMENT}.querySelector('.rl-networks-panel')`;

export async function openNetworks(page, browser) {
  if (!await page.until(`!!document.querySelector('button.rl-networks-open')`, 150)) throw new Error('the RL model... button did not appear');
  await page.evaluate(`(() => {
    const button = document.querySelector('button.rl-networks-open');
    if (button.disabled) throw new Error('the RL model... button is disabled');
    const open = window.open;
    window.open = function(...args) { return window.__checkRLWindow = open.apply(this, args); };
    try { button.click(); } finally { window.open = open; }
  })()`, true);
  const popup = await browser.attach(await browser.window('GATOR - RL model'), { errors: page.consoleErrors, prefix: 'RL model: ' });
  await popup.evaluate('void (window.__checkRLWindow = window)');
  await popup.viewport(1100, 900);
  if (!await popup.until(`!!document.querySelector('.rl-networks-panel')`)) throw new Error('the RL model window\'s content did not appear');
  return popup;
}

/** The Mode, as the window's three buttons choose it: 'scratch' (New model), 'fine_tune', 'frozen' (record 7.265). */
export async function setMode(popup, mode) {
  const pressed = await popup.evaluate(`(() => { const b = document.querySelector('.rl-modes button[data-mode="${mode}"]'); if (!b) return false; b.click(); return true; })()`);
  if (!pressed) throw new Error(`the Mode ${mode} is not offered in the RL model window`);
  return popup.until(`document.querySelector('.rl-modes button[data-mode="${mode}"]')?.getAttribute('aria-checked') === 'true'`, 30);
}
