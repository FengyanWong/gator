// What every pop-up window's owner draws (plan-refactoring C7): Blocked, the line said when the browser refused the
// window, and PopupPortal, the window's content drawn into it while it is open.
import { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { BLOCKED } from './popupWindow';

/** What a panel says when the browser refused to open its window (BLOCKED), drawn as that panel has always drawn it - a
 *  paragraph or a span, its classes, its role (plan-refactoring C7: nine copies in six forms). */
export function Blocked({ as: Tag = 'p', className = 'error', role }: { as?: 'p' | 'span'; className?: string; role?: string }) {
  return <Tag className={className} role={role}>{BLOCKED}</Tag>;
}

/** A pop-up window's content, drawn into its root while it is open (popupWindow.ts); nothing while it is closed. */
export function PopupPortal({ popup, root, children }: { popup: Window | null; root: HTMLElement | null; children: ReactNode }) {
  return popup && root ? createPortal(children, root) : null;
}
