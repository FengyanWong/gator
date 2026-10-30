// The page's reads and button actions (plan-refactoring C3, out of store.ts): useRequest and its polling form, and the
// shared pending state of an action.
import { useCallback, useEffect, useRef, useState } from 'react';
import { type ApiError, readWithDeadline } from './api';
import { pageSeen, seenAgain } from './windows';
import { useNewest } from './newest';

export function usePolling<T>(fn: (signal: AbortSignal) => Promise<T>, ms: number, enabled: boolean, deps: unknown[]) {
  return useRequest(fn, deps, { enabled, pollEvery: ms });
}

/** Button actions keep their feature's confirmations and messages; only the pending lifecycle is shared. `onError` gets what the
 *  action threw, an Error: an ApiError when the backend refused, with its `status` and `detail`; another when no answer came
 *  (the page's actions throw nothing else). */
export function useAsyncAction(onError: (error: Error & Partial<ApiError>, name: string) => void, onStart: () => void) {
  const [busy, setBusy] = useState<string | null>(null);
  const generation = useNewest();
  const run = async (name: string, action: () => Promise<unknown>) => {
    const mine = generation.next();
    setBusy(name); onStart();
    try { await action(); } catch (error) { onError(error as Error & Partial<ApiError>, name); }
    finally { if (mine()) setBusy(null); }
  };
  return { busy, run };
}

/** A read follows explicit dependencies. Replies to an earlier selection or an unmounted view are discarded. */
const sameDependencies = (a: unknown[], b: unknown[]) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]));

export function useRequest<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[], { enabled = true, delay = 0, keepPrevious = false, pollEvery = 0, timeoutMs = 30000 }:
  { enabled?: boolean; delay?: number; keepPrevious?: boolean; pollEvery?: number | ((value: T | null) => number); timeoutMs?: number } = {}) {
  const [result, setResult] = useState<{ deps: unknown[]; value: T | null; error: string | null }>({ deps: [], value: null, error: null });
  const [loading, setLoading] = useState(false);
  const [revision, refresh] = useState(0);
  const immediate = useRef(false);
  const inFlight = useRef<{ controller: AbortController; promise: Promise<T> } | null>(null);
  const cancel = useCallback(() => { inFlight.current?.controller.abort(); inFlight.current = null; }, []);
  // Interval changes can reuse a read; changing the selection, disabling or leaving cancels it.
  useEffect(() => cancel, [enabled, timeoutMs, ...deps]);
  const asked = useRef<unknown[] | null>(null);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let waiting: (() => void) | null = null;                   // the next poll, while no window of the page is seen
    // Another selection starts empty; a refresh of the SAME one keeps its answer until the new one comes (a Refresh used
    // to blank Data tables, Output files and Corner check and lose the scroll position).
    const another = !asked.current || !sameDependencies(asked.current, deps);
    asked.current = deps;
    // Switched off, it shows nothing whatever it holds: an empty result is kept as it is, not replaced by another empty
    // one at every change of what it depends on - that drew the page a second time at every keystroke (record 7.279).
    if (!enabled) setResult(r => (r.value === null && r.error === null ? r : { deps, value: null, error: null }));
    else if (!keepPrevious && !pollEvery && another) setResult({ deps, value: null, error: null });
    setLoading(enabled);
    if (!enabled) return;
    const read = async () => {
      let value: T | null = null;
      if (!inFlight.current) {
        const controller = new AbortController();
        inFlight.current = { controller, promise: readWithDeadline(fn, controller.signal, timeoutMs) };
      }
      const request = inFlight.current;
      try {
        value = await request.promise;
        if (live && !request.controller.signal.aborted) setResult({ deps, value, error: null });
      }
      // A read fails with an Error: an ApiError when the backend refused, another when no answer came (a failed fetch, the deadline).
      catch (e) { if (live && !request.controller.signal.aborted) setResult({ deps, value: null, error: String((e as Error).message ?? e) }); }
      finally {
        if (inFlight.current === request) inFlight.current = null;
        if (live && !request.controller.signal.aborted) {
          setLoading(false);
          const interval = typeof pollEvery === 'function' ? pollEvery(value) : pollEvery;
          if (interval && pageSeen()) timer = setTimeout(read, interval);
          else if (interval) {                                  // out of sight: read at once when it is seen again
            const resume = () => { seenAgain.delete(resume); waiting = null; if (live) void read(); };
            waiting = resume;
            seenAgain.add(resume);
          }
        }
      }
    };
    const wait = immediate.current ? 0 : delay;
    immediate.current = false;
    // Even a zero delay lets StrictMode's setup/cleanup replay cancel the first scheduled read.
    timer = setTimeout(read, wait);
    return () => { live = false; clearTimeout(timer); if (waiting) seenAgain.delete(waiting); };
  }, [enabled, delay, keepPrevious, pollEvery, timeoutMs, revision, ...deps]);
  // Hide the old selection during render, before effect cleanup/reset has run. A changed polling interval
  // retains the same run's result; a changed run/table never inherits it. Validation opts into keepPrevious.
  const current = sameDependencies(deps, result.deps);
  return { value: enabled && (current || keepPrevious) ? result.value : null,
    error: enabled && current ? result.error : null, loading: enabled && (loading || !current),
    refresh: useCallback(() => { cancel(); immediate.current = true; refresh(n => n + 1); }, [cancel]) };
}
