// The windows of the page (plan-refactoring C3, out of store.ts): the pop-up windows whose input events count as typing
// (typingField, for the Undo history) and whether any window of the page is in view (pageSeen, for the polls).

const inputWindows = new Set<Window>();
/** A portal's native input event belongs to its own window, even though React updates the workbench's store. The
 *  window also counts as the page being in view (pageSeen). */
export function registerInputWindow(view: Window) {
  inputWindows.add(view);
  try { view.document.addEventListener('visibilitychange', visibilityChanged); } catch { /* closing */ }
  return () => { inputWindows.delete(view); try { view.document.removeEventListener('visibilitychange', visibilityChanged); } catch { /* closed */ } };
}

// Polls wait while no window of the page can be seen (record 7.279): the status poll went on in a hidden browser tab,
// 30-50 requests a minute. A pop-up window of the page counts - Edge also calls the page hidden when its window is
// covered, while a pop-up of it is in view.
export const seenAgain = new Set<() => void>();
export const pageSeen = () => !document.hidden
  || [...inputWindows].some(view => { try { return !view.closed && !view.document.hidden; } catch { return false; } });
function visibilityChanged() { if (pageSeen()) for (const resume of [...seenAgain]) resume(); }
document.addEventListener('visibilitychange', visibilityChanged);
/** The text field this change was typed into, or null (a select, a tick box, a button, an answer that arrived meanwhile).
 *  Changes typed into ONE field less than MERGE_MS apart (history.ts) are one Undo step (user choice 2026-09-30: typing 1.5e-6 used to
 *  take six Undo presses, and the 100 kept steps ran out while typing). The field is the one whose input event is being
 *  handled, not the focused one: an agent proposal applied, rows read from Virtuoso or a change in a pop-up window while a
 *  cell had focus joined its typing step, and Undo took them away with the typed text (review of 2026-10-01). Tag names,
 *  not instanceof: a pop-up window's fields belong to that window. */
export function typingField(): Element | null {
  const event = window.event ?? [...inputWindows].map(view => view.event).find(Boolean);
  const e = event && ['input', 'change', 'compositionend'].includes(event.type) ? event.target as HTMLInputElement | null : null;
  if (e?.tagName === 'TEXTAREA') return e;
  return e?.tagName === 'INPUT' && !['checkbox', 'radio', 'file', 'button', 'submit'].includes(e.type) ? e : null;
}

type KeyPress = { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean; defaultPrevented: boolean; target: EventTarget | null };
/** The page's Undo or Redo a key press asks for, or null (branch record SIF-97): Ctrl+Z (Cmd+Z on a Mac), and Ctrl+Y or
 *  Ctrl+Shift+Z, wherever the focus is in the main window or the RL model window - they worked in an editor cell only, so
 *  after an Import's Apply or a tab press nothing happened, and the RL model window had no Undo at all. A box that takes
 *  typing (the formula bar, Find rows, a number or a name box) keeps the browser's own undo of its text, as the formula bar
 *  did (record 7.188); a key a cell has handled already, and a dialog open over the page, are left be. Tag names, not
 *  instanceof: a pop-up window's fields belong to that window. */
export function undoKey(e: KeyPress): 'undo' | 'redo' | null {
  if (e.defaultPrevented || !(e.ctrlKey || e.metaKey) || e.altKey || !/^[zy]$/i.test(e.key)) return null;
  const box = e.target as HTMLElement | null;
  if (box?.closest?.('dialog[open]') || box?.tagName === 'TEXTAREA' || box?.isContentEditable
    || (box?.tagName === 'INPUT' && !['checkbox', 'radio', 'file', 'button', 'submit', 'reset', 'range', 'color', 'image'].includes((box as HTMLInputElement).type))) return null;
  return e.key.toLowerCase() === 'y' || e.shiftKey ? 'redo' : 'undo';
}
