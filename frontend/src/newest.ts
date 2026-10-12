import { useRef } from 'react';

/** A series of asks of which only the newest may land (plan-refactoring C7: the hand-written `mine = ++serial.current`
 *  guards). `next()` starts an ask and returns its test - true while no newer ask was started and none was dropped since;
 *  `drop()` lets every ask on its way go, without starting one. */
export type Newest = { next: () => () => boolean; drop: () => void };
export function newest(): Newest {
  let serial = 0;
  return { next: () => { const mine = ++serial; return () => mine === serial; }, drop: () => { serial++; } };
}
/** What an answer belongs to. Revisions can be immutable object identities, a row fingerprint or a monotonic counter;
 *  each caller retains its existing invalidation rule. Reading the scope at reply time also covers edits made by Undo. */
export type ReplyScope<Entity, Revision> = { entity: Entity; revision: Revision };
export function sameScope<Entity, Revision>(a: ReplyScope<Entity, Revision>, b: ReplyScope<Entity, Revision>): boolean {
  return a.entity === b.entity && a.revision === b.revision;
}
export function inScope<Entity, Revision>(expected: ReplyScope<Entity, Revision>, read: () => ReplyScope<Entity, Revision>): () => boolean {
  return () => sameScope(expected, read());
}
/** The same, kept by a component for as long as it is mounted (one ref, as the guards had). */
export function useNewest(): Newest {
  const held = useRef<Newest | null>(null);
  if (!held.current) held.current = newest();
  return held.current;
}
