import { useRef } from 'react';

/** A series of asks of which only the newest may land (plan-refactoring C7: the hand-written `mine = ++serial.current`
 *  guards). `next()` starts an ask and returns its test - true while no newer ask was started and none was dropped since;
 *  `drop()` lets every ask on its way go, without starting one. */
export type Newest = { next: () => () => boolean; drop: () => void };
export function newest(): Newest {
  let serial = 0;
  return { next: () => { const mine = ++serial; return () => mine === serial; }, drop: () => { serial++; } };
}
/** The same, kept by a component for as long as it is mounted (one ref, as the guards had). */
export function useNewest(): Newest {
  const held = useRef<Newest | null>(null);
  if (!held.current) held.current = newest();
  return held.current;
}
