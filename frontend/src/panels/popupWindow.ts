import { useEffect, useRef, useState } from 'react';

/** The workbench's pop-up windows (connection, runs, PDK, task file): a NAMED `about:blank` window with the page's own
 *  stylesheets copied into it and one root element to portal React into. The window closes with the page, and when the
 *  viewer closes it the panel hears of it. `open()` brings an already open window to the front instead of making a
 *  second one; `blocked` says the browser refused to open it, and each panel words that in its own way.
 *
 *  Written in the review of 2026-09-23: these same twenty lines stood in four panels. The Agent tab's conversation
 *  window (`Bottom.tsx`) deliberately stays outside this hook - it carries handlers of its own in both directions. */
export function usePopupWindow(name: string, options: {
  title: string; features: string; rootId: string; rootClass?: string; onClose?: () => void; closeOnUnmount?: boolean;
}) {
  const [popup, setPopup] = useState<Window | null>(null);
  const [root, setRoot] = useState<HTMLElement | null>(null);
  const [blocked, setBlocked] = useState(false);
  const latest = useRef(options);
  latest.current = options;

  const open = () => {
    if (popup && !popup.closed) { popup.focus(); return popup; }
    const { title, features, rootId, rootClass } = latest.current;
    const opened = window.open('', name, features);
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
    const closed = () => { setPopup(null); setRoot(null); latest.current.onClose?.(); };   // closed with its own close button
    const leave = () => popup.close();                     // the workbench page is leaving: do not leave a dead window behind
    popup.addEventListener('pagehide', closed);
    window.addEventListener('pagehide', leave);
    return () => {
      popup.removeEventListener('pagehide', closed);
      window.removeEventListener('pagehide', leave);
      if (latest.current.closeOnUnmount) popup.close();
    };
  }, [popup]);

  return { popup, root, blocked, open };
}
