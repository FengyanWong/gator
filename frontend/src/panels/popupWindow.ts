import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { WINDOW_PLACE_KEY_PREFIX } from '../contract';
import { keep, readKept } from '../kept';
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

/** A window's size and place as the viewer left it (branch record SIF-110), kept in this browser under its name: the size of
 *  its page, which `width` and `height` ask `open()` for (innerWidth x innerHeight: kept as the outer size, the window would
 *  grow by its frame at every opening), its outer corner on the screen, which `left` and `top` ask for, and `of`, the
 *  features it was opened with. */
type Place = { of: string; w: number; h: number; x: number; y: number };

/** `features` with the size and place this window was left at, when it opens with the same features: the Connection window
 *  is wider for a connection of two Virtuoso sessions, and a size left for one is not given to the other. At most the
 *  screen's size, and on the screen of the window that opens it: a place kept on a second screen may be on no screen now.
 *  Nothing kept, or storage blocked: `features` as they are. */
function placed(name: string, features: string, screen: Screen): string {
  const kept = readKept<Place | null>(storage => JSON.parse(storage.getItem(WINDOW_PLACE_KEY_PREFIX + name) ?? 'null'), () => null);
  if (kept?.of !== features || ![kept.w, kept.h, kept.x, kept.y].every(Number.isFinite)) return features;
  const { availLeft = 0, availTop = 0, availWidth, availHeight } = screen as Screen & { availLeft?: number; availTop?: number };
  const w = Math.min(kept.w, availWidth), h = Math.min(kept.h, availHeight);
  const x = Math.max(availLeft, Math.min(kept.x, availLeft + availWidth - w)), y = Math.max(availTop, Math.min(kept.y, availTop + availHeight - h));
  return [...features.split(',').filter(feature => !/^\s*(width|height|left|top)\s*=/.test(feature)), `width=${w}`, `height=${h}`, `left=${x}`, `top=${y}`].join(',');
}

/** The workbench's pop-up windows (Connection, Virtuoso, PDK, ngspice, Tasks, Runs, the run brief, the RL model window,
 *  the task file, Agent): a NAMED `about:blank` window with the page's own stylesheets copied into it and one root
 *  element to portal React into. The window closes with the page, and when the viewer closes it the panel hears of it.
 *  `open()` brings an already open window to the front instead of making a second one; `blocked` says the browser
 *  refused to open it (`BLOCKED` says so; the task file names its own button). A window opens again at the size and place
 *  it was left at (`placed`, branch record SIF-110); `features` give its first size.
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
    const opened = via.open('', name, placed(name, features, via.screen));
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
    // Its size and place are kept as the viewer leaves them (branch record SIF-110: each opening asked for the same size, and
    // since record 7.291 a choice closes the Tasks, Runs and RL model windows): once a resize has come to rest, and as the
    // window goes - a move fires no event. A window that is going may answer nothing: kept only with a size it can open at.
    const of = latest.current.features;
    const remember = () => keep(storage => {
      const place: Place = { of, w: popup.innerWidth, h: popup.innerHeight, x: popup.screenX, y: popup.screenY };
      if (place.w >= 100 && place.h >= 100) storage.setItem(WINDOW_PLACE_KEY_PREFIX + name, JSON.stringify(place));
    });
    let resting = 0;
    const resized = () => { window.clearTimeout(resting); resting = window.setTimeout(remember, 300); };
    const closed = () => { remember(); setPopup(null); setRoot(null); latest.current.onClose?.(); };   // closed with its own close button
    const leave = () => { remember(); popup.close(); };    // the workbench page is leaving: do not leave a dead window behind
    popup.addEventListener('pagehide', closed);
    popup.addEventListener('resize', resized);
    window.addEventListener('pagehide', leave);
    return () => {
      window.clearTimeout(resting);
      stopTrackingInput();
      popup.removeEventListener('pagehide', closed);
      popup.removeEventListener('resize', resized);
      window.removeEventListener('pagehide', leave);
      if (latest.current.closeOnUnmount) { remember(); popup.close(); }
      if (openNow.get(name)?.window === popup) { openNow.delete(name); openChanged(); }
    };
  }, [popup]);

  return { popup, root, blocked, open };
}
