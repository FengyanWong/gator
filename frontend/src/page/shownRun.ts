// The run list and the run the bottom tabs show, with the header's run (plan-refactoring C5, out of App.tsx's Page).
import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, Json, plainError } from '../api';
import { HEADER_RUN_KEY, SHOWN_RUN_KEY } from '../contract';
import { keep, readKept } from '../kept';
import { useNewest } from '../newest';
import type { BottomTab } from '../panels/BottomPanel';
import { changesByItself, useRunControl } from '../runState';
import { usePolling } from '../store';

const NO_RUNS: Json[] = [];                          // one empty list: a failed read does not make the model list read again

/** The run the bottom tabs show, kept in this browser (SHOWN_RUN_KEY) with the header's run of that moment (record 7.212): a page loaded
 *  again shows the run it showed - or none, after a task without runs was chosen. Unless the header holds another run by
 *  then (started in another tab of the page, say): the page opens on the header's run then, as it always did, and so does a
 *  browser that never kept one. */
export const shownRun = (): string | null => readKept(s => {
  const header = s.getItem(HEADER_RUN_KEY) || null, kept = JSON.parse(s.getItem(SHOWN_RUN_KEY) ?? 'null');
  return kept && typeof kept === 'object' && (kept.header ?? null) === header ? kept.run ?? null : header;
}, () => null);

/** The run list under the page's output root (`outputRootNow`), read by `readRuns` - only the newest read answers - and kept
 *  with its error. */
export function useRunList(outputRootNow: string | null | undefined) {
  const [runs, setRuns] = useState<Json[]>(NO_RUNS);
  const [runsError, setRunsError] = useState<string | null>(null);   // the run list could not be read: said, not shown as "no run yet"
  // Only the newest read of the run list may answer: while the output root is typed, a half-typed path outside the roots
  // (403) used to empty the list when its answer came last.
  const listing = useNewest();
  // One function for the whole page (useCallback; the output root through a ref), so the panels that take it are not drawn
  // again at every status update (record 7.275). A list that is the same as the one held keeps that array: what depends
  // on the runs (the saved models, the Training tab) is not asked again for nothing. `fresh`: the backend reads every
  // run folder anew (Refresh list; record 7.274).
  const outputRoot = useRef(outputRootNow);
  outputRoot.current = outputRootNow;
  const readRuns = useCallback((fresh = false): Promise<{ list: Json[]; error: string | null }> => {
    const mine = listing.next();
    return api.runs(outputRoot.current ?? undefined, fresh).then(r => ({ list: r.runs as Json[], error: null }), e => ({ list: NO_RUNS, error: plainError(e) }))
      .then(read => {
        if (mine()) { setRuns(held => (JSON.stringify(held) === JSON.stringify(read.list) ? held : read.list)); setRunsError(read.error); }
        return read;
      });
  }, []);
  const refreshRuns = useCallback((fresh = false): Promise<Json[]> => readRuns(fresh).then(read => read.list), [readRuns]);
  return { runs, runsError, readRuns, refreshRuns };
}

/** The run the bottom tabs show (`runDir`, the page's): its status, read as often as it can change, let go when it is gone;
 *  whether Corner check can be used; the header's run (`control`, useRunControl), kept with it in this browser; and `setLooked`,
 *  for when the page has read the run list once. Its hooks are Page's, in their order. */
export function useShownRun({ runDir, setRunDir, tab, setTab, circuit }: { runDir: string | null; setRunDir: Dispatch<SetStateAction<string | null>>;
  tab: BottomTab; setTab: (tab: BottomTab) => void; circuit: Json }) {
  // How often the run shown is read: see the effect after useRunControl below.
  const [statusEvery, setStatusEvery] = useState(1500);
  // The run shown is gone (deleted, or outside the allowed roots by now - it may be the remembered one the page opened
  // with): it is let go, as the header lets go of its own, instead of being asked for every 1.5 s for ever while the strip
  // still names its folder. Two answers in a row: on the 9p-mounted D: drive a stat right after a rename can fail once,
  // and one 404 of a run that is there must not take it off the page.
  const gone = useRef(0);
  useEffect(() => { gone.current = 0; }, [runDir]);
  const readStatus = (dir: string, signal: AbortSignal) => api.status(dir, signal).then(value => { gone.current = 0; return value; }, e => {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404) && ++gone.current >= 2) setRunDir(shown => (shown === dir ? null : shown));
    throw e;
  });
  const { value: polledStatus, error: statusError } = usePolling(signal => readStatus(runDir!, signal), statusEvery, !!runDir, [runDir]);
  const status = polledStatus?.run_dir === runDir ? polledStatus : null;
  // Corner check only where corners can be used (record 7.182, design advice): the loaded circuit simulates at corners, or the run
  // shown is MOCK (its corners are analytic). No registered circuit does since 2026-09-30 (record 7.128); the tab comes back by
  // itself with one that does.
  const cornersUsable = circuit?.training_capabilities?.corners === true || !!status?.manifest?.mock;
  useEffect(() => { if (tab === 'corners' && !cornersUsable) setTab('status'); }, [tab, cornersUsable]);
  const isReal = circuit?.loaded && circuit.mock === false;
  // The run the header buttons act on (Start -> Pause -> Resume, Abort). It is not the run the bottom tabs show.
  const [looked, setLooked] = useState(false);
  const control = useRunControl(status, looked);
  // The run shown, kept with the header's run (shownRun above); again when the header takes or lets go of one.
  useEffect(() => {
    keep(s => s.setItem(SHOWN_RUN_KEY, JSON.stringify({ run: runDir, header: control.dir })));   // a private window: not kept
  }, [runDir, control.dir]);
  // The run shown is read every 1.5 s while it can change by itself: a worker is alive, its state is a live one, or the
  // header is starting, resuming, pausing or ending a run. Otherwise it waits for a press on this page: every 15 s while
  // it could still be continued (paused, stopped, interrupted - another browser may continue it), once a minute once it
  // has ended for good (completed, failed, cancelled). Until 2026-09-30 a paused or stopped run was read every 1.5 s, and
  // each read re-reads its tables. The header's phase counts only when the header's run IS the run shown (record 7.125:
  // a finished run in the tabs was read every 1.5 s while the header paused or aborted another one).
  const transitional = control.dir === runDir && ['starting', 'resuming', 'pausing', 'aborting', 'finishing'].includes(control.phase);
  useEffect(() => setStatusEvery(changesByItself(status, transitional) ? 1500
    : ['completed', 'failed', 'cancelled'].includes(status.state) ? 60000 : 15000), [status?.worker_alive, status?.state, transitional]);
  return { status, statusError, cornersUsable, isReal, control, setLooked };
}
