import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { registerInputWindow } from '../store';

/** The windows open now, for the banner's Windows list (record 7.372): by name, with the window and the title it was given. */
export type OpenWindow = { name: string; title: string; window: Window };
const openNow = new Map<string, OpenWindow>();
const listeners = new Set<() => void>();
let openList: OpenWindow[] = [];
const openChanged = () => { openList = [...openNow.values()]; listeners.forEach(listener => listener()); };
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
/** The pop-up windows open now, in the order they opened. */
export function useOpenWindows(): OpenWindow[] { return useSyncExternalStore(subscribe, () => openList); }

/** What a panel says when the browser refused to open its window. */
export const BLOCKED = 'The browser blocked the new window. Allow pop-ups for this page, then press the button again.';

/** Resolves once a pop-up's stylesheets have loaded (branch record SIF-86): `open()` copies the page's as links, which a new
 *  window loads after its first draw, so a place measured before then - a scroll to a block - is measured without the page's
 *  layout. A sheet that never answers holds it 2 s at most. */
export const styled = (win: Window): Promise<unknown> => Promise.race([new Promise(done => window.setTimeout(done, 2000)),
  Promise.all([...win.document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')].filter(link => !link.sheet)
    .map(link => new Promise(done => { link.addEventListener('load', done, { once: true }); link.addEventListener('error', done, { once: true }); })))]);

/** The workbench's pop-up windows (Connection, Virtuoso, PDK, ngspice, Tasks, Runs, the run brief, the RL model window,
 *  the task file, Agent): a NAMED `about:blank` window with the page's own stylesheets copied into it and one root
 *  element to portal React into. The window closes with the page, and when the viewer closes it the panel hears of it.
 *  `open()` brings an already open window to the front instead of making a second one; `blocked` says the browser
 *  refused to open it (`BLOCKED` says so; the task file names its own button).
 *
 *  Written in the review of 2026-09-23: these same twenty lines stood in four panels. */
export function usePopupWindow(name: string, options: {
  title: string; features: string; rootId: string; rootClass?: string; onClose?: () => void; closeOnUnmount?: boolean;
}) {
  const [popup, setPopup] = useState<Window | null>(null);
  const [root, setRoot] = useState<HTMLElement | null>(null);
  const [blocked, setBlocked] = useState(false);
  const latest = useRef(options);
  latest.current = options;

  // `from`: the window whose button was pressed, when that is itself one of these pop-ups (the PDK window opens from the
  // Virtuoso window since 2026-09-27). A pop-up may only be opened by the window that holds the user's click: opened from
  // the page's own `window` instead, the browser's pop-up blocker refuses it. Anything else (a click event, nothing)
  // means the page's window.
  const open = (from?: unknown) => {
    if (popup && !popup.closed) { popup.focus(); return popup; }
    const { title, features, rootId, rootClass } = latest.current;
    const via = from && typeof (from as Window).open === 'function' && 'closed' in (from as Window) && !(from as Window).closed ? from as Window : window;
    const opened = via.open('', name, features);
    if (!opened) { setBlocked(true); return null; }
    const doc = opened.document;
    doc.title = title;
    doc.head.querySelectorAll('link, style').forEach(node => node.remove());            // a window of that name may be reused
    document.querySelectorAll<HTMLElement>('link[rel="stylesheet"], style').forEach(node => {
      const copy = node.cloneNode(true) as HTMLElement;
      if (node instanceof HTMLLinkElement) (copy as HTMLLinkElement).href = node.href;  // absolute: the new window is about:blank
      doc.head.appendChild(copy);
    });
    doc.body.innerHTML = '';
    const element = doc.createElement('div');
    element.id = rootId;
    if (rootClass) element.className = rootClass;
    doc.body.appendChild(element);
    setBlocked(false); setPopup(opened); setRoot(element);
    return opened;
  };

  useEffect(() => {
    if (!popup) return;
    const stopTrackingInput = registerInputWindow(popup);
    openNow.set(name, { name, title: latest.current.title, window: popup }); openChanged();
    const closed = () => { setPopup(null); setRoot(null); latest.current.onClose?.(); };   // closed with its own close button
    const leave = () => popup.close();                     // the workbench page is leaving: do not leave a dead window behind
    popup.addEventListener('pagehide', closed);
    window.addEventListener('pagehide', leave);
    return () => {
      stopTrackingInput();
      popup.removeEventListener('pagehide', closed);
      window.removeEventListener('pagehide', leave);
      if (latest.current.closeOnUnmount) popup.close();
      if (openNow.get(name)?.window === popup) { openNow.delete(name); openChanged(); }
    };
  }, [popup]);

  return { popup, root, blocked, open };
}
