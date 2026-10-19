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
 *  one press brings a window to the front, "Close all" closes them. */
export function WindowsMenu() {
  const windows = useOpenWindows();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', escape); };
  }, [open]);
  useEffect(() => { if (!windows.length) setOpen(false); }, [windows.length]);
  if (!windows.length) return null;
  return (<span className="windows-menu" ref={box}>
    <button className={`windows-button${open ? ' open' : ''}`} aria-expanded={open} onClick={() => setOpen(o => !o)}
      title={`Open windows: ${windows.map(shownTitle).join(', ')}. Press for the list; a press there brings that window to the front.`}>
      <Icon name="windows" label="Open windows" /><span className="windows-count" aria-hidden="true">{windows.length}</span></button>
    {open && <div className="windows-list" role="menu" aria-label="Open windows">
      {windows.map(w => <button key={w.name} role="menuitem" onClick={() => { w.window.focus(); setOpen(false); }}
        title={`Brings the window "${shownTitle(w)}" to the front.`}>{shownTitle(w)}</button>)}
      <button className="windows-close-all" role="menuitem" onClick={() => { windows.forEach(w => w.window.close()); setOpen(false); }}
        title="Close all: Closes every window listed here. Nothing in them is lost; each opens again from its button.">Close all</button>
    </div>}
  </span>);
}
