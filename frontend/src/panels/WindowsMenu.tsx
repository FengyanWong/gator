import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import { type OpenWindow, useOpenWindows } from './popupWindow';

/** A window's name in the list: its title without "GATOR - " (the task file names its task), with a capital first letter. */
function shownTitle(w: OpenWindow): string {
  let title = w.title;
  try { title = w.window.document.title || title; } catch { /* closing */ }
  const plain = title.replace(/^GATOR - /, '');
  return plain.startsWith('ngspice') ? plain : plain.charAt(0).toUpperCase() + plain.slice(1);
}

/** The banner's list of the pop-up windows open now (record 7.372): shown only while one is open, its count on the button;
 *  one press brings a window to the front, "Close all" closes them. Plain buttons in the Tab order (branch record SIF-109):
 *  marked as a menu, the list promised the arrow keys a menu has, and it had none. */
export function WindowsMenu() {
  const windows = useOpenWindows();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const closedAll = useRef(false);                 // Close all was pressed: the focus follows once the windows have gone
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    // Esc gives the focus back to the Windows button when it was in the list (branch record SIF-109): it fell to the page
    // with the list, and the next Tab began at the top of the page. A focus elsewhere stays where it is.
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (box.current?.contains(document.activeElement)) button.current?.focus();
      setOpen(false);
    };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', escape); };
  }, [open]);
  // Close all takes the button away with the last window (branch record SIF-109): the focus, fallen to the page, goes to the
  // banner's control before it - the run chip, else the Connection button -, so the next Tab goes on from there. Each window
  // goes when it says so (pagehide), not at the press: hence here, once the list is empty.
  useEffect(() => {
    if (windows.length) return;
    setOpen(false);
    if (closedAll.current && (!document.activeElement || document.activeElement === document.body))
      (document.querySelector<HTMLElement>('header .run-chip') ?? document.querySelector<HTMLElement>('header .connection-button'))?.focus();
    closedAll.current = false;
  }, [windows.length]);
  if (!windows.length) return null;
  return (<span className="windows-menu" ref={box}>
    <button ref={button} className={`windows-button${open ? ' open' : ''}`} aria-expanded={open} onClick={() => setOpen(o => !o)}
      title={`Open windows: ${windows.map(shownTitle).join(', ')}. Press for the list; a press there brings that window to the front.`}>
      <Icon name="windows" label="Open windows" /><span className="windows-count" aria-hidden="true">{windows.length}</span></button>
    {open && <div className="windows-list" role="group" aria-label="Open windows">
      {windows.map(w => <button key={w.name} onClick={() => { w.window.focus(); setOpen(false); }}
        title={`Brings the window "${shownTitle(w)}" to the front.`}>{shownTitle(w)}</button>)}
      {/* The focus waits on the Windows button: there it stays while a window is still open, and it moves on (above) once the last has gone. */}
      <button className="windows-close-all" onClick={() => { closedAll.current = true; button.current?.focus(); windows.forEach(w => w.window.close()); setOpen(false); }}
        title="Close all: Closes every window listed here. Nothing in them is lost; each opens again from its button.">Close all</button>
    </div>}
  </span>);
}
