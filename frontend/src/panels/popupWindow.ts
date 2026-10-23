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

/** A window's size and place as the viewer left it (branch record SIF-110), kept in this browser under its name: its outer
 *  size `ow` x `oh` and its outer corner `x`, `y` on the screen, which resizeTo and moveTo set once it is open; the size of
 *  its page `w` x `h`, which `width` and `height` ask `open()` for; and `of`, the features it was opened with. The review of
 *  SIF-110: the page's size is in its CSS px, which shrink as the window's page zoom grows (Edge's default page zoom set
 *  above 100 %, or Ctrl + in the window), while `open()` takes screen px - kept alone, it opened such a window smaller at
 *  every opening, larger under 100 %. The outer size and corner are screen px at any zoom; the page's size, asked for
 *  first, opens a window at 100 % zoom at its size at once (asked for as `width`, the outer size would grow the window by
 *  its frame). */
type Place = { of: string; w: number; h: number; x: number; y: number; ow: number; oh: number };

/** How this window opens again, when it opens with the same features (the Connection window is wider for a connection of
 *  two Virtuoso sessions, and a size left for one is not given to the other): `features` with its page's size and its
 *  corner, and `outer`, its outer size and corner. At most the screen's size, and on the screen of the window that opens
 *  it: a place kept on a second screen may be on no screen now. Nothing kept, a place kept without its outer size (before
 *  the review of SIF-110), or storage blocked: `features` as they are. */
function placed(name: string, features: string, screen: Screen): { features: string; outer?: { w: number; h: number; x: number; y: number } } {
  const kept = readKept<Place | null>(storage => JSON.parse(storage.getItem(WINDOW_PLACE_KEY_PREFIX + name) ?? 'null'), () => null);
  if (kept?.of !== features || ![kept.w, kept.h, kept.x, kept.y, kept.ow, kept.oh].every(Number.isFinite)) return { features };
  const { availLeft = 0, availTop = 0, availWidth, availHeight } = screen as Screen & { availLeft?: number; availTop?: number };
  const w = Math.min(kept.ow, availWidth), h = Math.min(kept.oh, availHeight);
  const x = Math.max(availLeft, Math.min(kept.x, availLeft + availWidth - w)), y = Math.max(availTop, Math.min(kept.y, availTop + availHeight - h));
  const sized = [...features.split(',').filter(feature => !/^\s*(width|height|left|top)\s*=/.test(feature)),
    `width=${Math.min(kept.w, availWidth)}`, `height=${Math.min(kept.h, availHeight)}`, `left=${x}`, `top=${y}`];
  return { features: sized.join(','), outer: { w, h, x, y } };
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
    const place = placed(name, features, via.screen);
    const opened = via.open('', name, place.features);
    if (!opened) { setBlocked(true); return null; }
    // Its outer size and corner, which the page's size asked for gives only at 100 % zoom (`Place`). Edge takes both from a
    // window just opened; a headless one ignores them, as it ignores the size asked for.
    if (place.outer) { opened.resizeTo(place.outer.w, place.outer.h); opened.moveTo(place.outer.x, place.outer.y); }
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
    // window goes - a move fires no event. A window that is going may answer nothing: kept only with an outer size it can open
    // at (100 px, the least a window opens at) and a page.
    const of = latest.current.features;
    const remember = () => keep(storage => {
      const place: Place = { of, w: popup.innerWidth, h: popup.innerHeight, x: popup.screenX, y: popup.screenY, ow: popup.outerWidth, oh: popup.outerHeight };
      if (place.ow >= 100 && place.oh >= 100 && place.w > 0 && place.h > 0) storage.setItem(WINDOW_PLACE_KEY_PREFIX + name, JSON.stringify(place));
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
