import { useEffect, useRef, useState } from 'react';
import { registerInputWindow } from '../store';
import { followLook } from '../theme';

/** What a panel says when the browser refused to open its window. */
export const BLOCKED = 'The browser blocked the new window. Allow pop-ups for this page, then press the button again.';

/** The workbench's pop-up windows (connection, runs, PDK, task file): a NAMED `about:blank` window with the page's own
 *  stylesheets copied into it and one root element to portal React into. The window closes with the page, and when the
 *  viewer closes it the panel hears of it. `open()` brings an already open window to the front instead of making a
 *  second one; `blocked` says the browser refused to open it (`BLOCKED` says so; the task file names its own button).
 *
 *  Written in the review of 2026-09-23: these same twenty lines stood in four panels. The Agent tab's conversation window
 *  uses it too since 2026-09-30 (its own copy had the same two handlers); `close()` is its way back into the page. */
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
    doc.documentElement.dataset.theme = document.documentElement.dataset.theme;   // the page's look from the first paint (theme.ts)
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
    const closed = () => { setPopup(null); setRoot(null); latest.current.onClose?.(); };   // closed with its own close button
    const leave = () => popup.close();                     // the workbench page is leaving: do not leave a dead window behind
    popup.addEventListener('pagehide', closed);
    window.addEventListener('pagehide', leave);
    const stopFollowingLook = followLook(popup);           // Switch look reaches an open window too
    return () => {
      stopTrackingInput();
      popup.removeEventListener('pagehide', closed);
      window.removeEventListener('pagehide', leave);
      stopFollowingLook();
      if (latest.current.closeOnUnmount) popup.close();
    };
  }, [popup]);

  const close = () => { popup?.close(); setPopup(null); setRoot(null); };
  return { popup, root, blocked, open, close };
}
