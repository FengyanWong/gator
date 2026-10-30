// What the page keeps in this browser (plan-refactoring C7: the "try { localStorage ... } catch" sites written once).
// Storage can be blocked - a private window, a browser setting - and nothing the page keeps may stop it then: a read falls
// back, a write is not kept. Each helper runs the site's whole work inside the one try, as the sites did.

/** `read(localStorage)`, or `otherwise()` when the storage cannot be used or the read failed (a value that is no JSON). */
export function readKept<T>(read: (storage: Storage) => T, otherwise: () => T): T {
  try { return read(localStorage); } catch { return otherwise(); }
}
/** `work(localStorage)`; with blocked storage (or a failure in the work) it is simply not done. */
export function keep(work: (storage: Storage) => void): void {
  try { work(localStorage); } catch { /* not kept */ }
}
/** The same two for what this tab keeps (sessionStorage). */
export function readKeptInTab<T>(read: (storage: Storage) => T, otherwise: () => T): T {
  try { return read(sessionStorage); } catch { return otherwise(); }
}
export function keepInTab(work: (storage: Storage) => void): void {
  try { work(sessionStorage); } catch { /* not kept */ }
}
/** True the first time for `key` in this browser, which it then notes: a one-time change of a kept draft. False when it was
 *  done before - and when the browser cannot keep the note: the change would then be made at every load, over a value the
 *  user may have restored. */
export function oncePerBrowser(key: string): boolean {
  try {
    if (localStorage.getItem(key)) return false;
    localStorage.setItem(key, 'checked');
    return true;
  } catch { return false; }
}
