import { useSyncExternalStore } from 'react';

/** A value the page holds outside React, and the parts that show it told of each change (plan-refactoring C3: the look, the
 *  task saves, the pointed devices and the loaded PDKs each had a hand-made copy of this). `put` changes the value without
 *  a word and `notify` tells every listener, in the order they came, so that an owner can do its own work between the two;
 *  `set` is both. `subscribe` adds a listener and returns what takes it away again. `use` reads the value in a component:
 *  it subscribes anew at every render, with a new subscribe function, as the hand-made copies did. */
export function signal<T>(initial: T) {
  let value = initial;
  const listeners = new Set<() => void>();
  const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
  const notify = () => { listeners.forEach(listener => listener()); };
  return {
    get: () => value,
    put: (next: T) => { value = next; },
    notify,
    set: (next: T) => { value = next; notify(); },
    subscribe,
    use: () => useSyncExternalStore(listener => subscribe(listener), () => value),
  };
}
