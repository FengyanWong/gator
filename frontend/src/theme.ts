import { LOOK_KEY } from './contract';
import { signal } from './signal';

/** The page's two looks (record 7.158, the user's choice of 2026-10-03): Whiteprint, light, a drawing sheet with the task
 *  in its title block (the default), and Silicon Night, dark like Virtuoso's canvas. A look is a name on <html>
 *  (`data-theme`) and a list of colour values in themes.css; nothing else changes with it. index.html puts the name there
 *  before the page draws, so a dark choice never flashes light. The choice is kept in this browser, like the folded
 *  modules, and every pop-up window of the page follows it. */
export type Look = 'whiteprint' | 'silicon';
export { LOOK_KEY };
export const LOOK_NAMES: Record<Look, string> = { whiteprint: 'Whiteprint', silicon: 'Silicon Night' };

const isLook = (value: unknown): value is Look => value === 'whiteprint' || value === 'silicon';
const named = document.documentElement.dataset.theme;
const current = signal<Look>(isLook(named) ? named : 'whiteprint');
const put = (doc: Document) => { doc.documentElement.dataset.theme = current.get(); };
put(document);                                   // index.html could not read the stored choice (blocked storage): the default
const followers = new Set<Window>();

/** An explicit press of the header's switch: the page, every open pop-up, and the stored choice. */
export function setLook(look: Look) {
  current.put(look);
  put(document);
  followers.forEach(w => { try { if (!w.closed) put(w.document); } catch { /* the window went away meanwhile */ } });
  try { localStorage.setItem(LOOK_KEY, look); } catch { /* a private window: this look lasts until the page is closed */ }
  current.notify();
}

/** A pop-up window takes the page's look now and whenever it changes; the function returned lets go of it. */
export function followLook(win: Window) {
  try { put(win.document); } catch { /* not reachable */ }
  followers.add(win);
  return () => { followers.delete(win); };
}

export function useLook(): Look {
  return current.use();
}
