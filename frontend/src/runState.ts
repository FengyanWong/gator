// The run states and the header's run (record 7.261; moved out of panels/RunControl.tsx, plan-refactoring C1): the lists that
// name a run's states, the rules built from them, and useRunControl - the run the header's buttons act on. The page, the run
// list, the run tabs, the run brief, the Training tab and the launcher read these; RunControl.tsx draws the buttons.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRequest } from './store';
import { api, ApiError, Json } from './api';
import { HEADER_RUN_KEY } from './contract';
import { keep, readKept } from './kept';

const TERMINAL = ['completed', 'paused', 'stopped', 'cancelled', 'failed'];
/** A run at rest that can go on: paused, or interrupted (its worker died). */
export const RESUMABLE = ['paused', 'interrupted'];
/** A run that ended: it goes on no more. */
export const ENDED = ['completed', 'stopped', 'cancelled', 'failed'];
export const LIVE_STATES = ['starting', 'running', 'pausing', 'stopping'];
/** A run of the run list whose status says it works. */
export const isLive = (r: Json) => LIVE_STATES.includes(r.state);
/** The states a run at rest can be continued from (a completed one too, under the conditions of the rules below). */
const CONTINUABLE = ['paused', 'stopped', 'interrupted'];
/** The states the Runs window offers Continue... for (branch record SIF-90): these and a completed run, whose budget form
 *  can raise its total. Run status refuses a failed or cancelled run, so the window no longer sends one there. */
export const CONTINUE_STATES = [...CONTINUABLE, 'completed'];

// The "live" and "resting" rules, one function each where they are worded differently (plan-refactoring C1: merged only
// where the expressions were the same token for token; these were not).
/** The run shown can change by itself, so the page reads it every 1.5 s (App.tsx): no status yet, a live worker or state,
 *  or the header is starting, resuming, pausing or ending that run (`transitional`). */
export const changesByItself = (status: Json, transitional: boolean) => !status || status.worker_alive || LIVE_STATES.includes(status.state) || transitional;
/** A card of the run brief is about a run that works: its worker lives, or its state - the status read, else the run list's
 *  row - is a live one. */
export const cardLive = (status: Json, row: Json) => !!status?.worker_alive || LIVE_STATES.includes(status?.state ?? row?.state);
/** The status is the shown run's, and that run works (the Training tab reads it again while it does). */
export const shownLive = (status: Json, runDir: string | null) => !!status && status.run_dir === runDir && (!!status.worker_alive || LIVE_STATES.includes(status.state));
/** The run shown is at rest in a state Continue can go on from: a completed run too, once the backend's continuation check
 *  can say whether a higher total is allowed (the Run status tab, record 7.261). */
export const restingShown = (status: Json, check: Json | null) => !status.worker_alive && (CONTINUABLE.includes(status.state) || (status.state === 'completed' && !!check));
/** The launcher's Continue readiness (launch.ts): a state Continue can go on from - a completed run only with the budget
 *  form's total (`total` 'form') and the backend's check. Its worker is known to be gone already. */
export const restingFor = (status: Json, check: Json | null, total: 'unchanged' | 'form') => CONTINUABLE.includes(status.state) || (status.state === 'completed' && total === 'form' && !!check);

export type Phase = 'idle' | 'checking' | 'starting' | 'running' | 'pausing' | 'paused' | 'resuming' | 'aborting' | 'finishing';
type Launch = null | 'start' | 'resume';
export type Pending = Launch | 'pause' | 'abort';

/** `pending`: a request of this page that the run has not shown yet. `launched`: this page has just started a worker.
 *  Until its first status is written (it imports for 2-3 s) the file still shows how the PREVIOUS segment ended
 *  ("paused"), although the run is on its way again. */
function phaseOf(status: Json, pending: Pending, launched: Launch): Phase {
  const asked = pending === 'start' || pending === 'resume' ? pending : status ? null : launched;
  if (asked) return asked === 'start' ? 'starting' : 'resuming';
  if (status?.worker_alive) {
    if (pending === 'abort' || status.state === 'stopping') return 'aborting';
    if (pending === 'pause' || status.state === 'pausing') return 'pausing';
    if (TERMINAL.includes(status.state) && !launched)       // the state is reached, the worker is writing its last files
      return status.state === 'paused' ? 'pausing' : ['stopped', 'cancelled'].includes(status.state) ? 'aborting' : 'finishing';
    return 'running';
  }
  return status && RESUMABLE.includes(status.state) ? 'paused' : 'idle';
}

const remembered = (): string | null => readKept(s => s.getItem(HEADER_RUN_KEY) || null, () => null);
const remember = (dir: string | null) => keep(s => { dir ? s.setItem(HEADER_RUN_KEY, dir) : s.removeItem(HEADER_RUN_KEY); });   // private mode: not kept

/** `viewedStatus` is the status the page already polls for the run shown in the bottom tabs. When that is the current
 *  run it is used as it arrives and no second poll runs. Otherwise the current run is polled here, and only while it
 *  is live: a run at rest (paused, ended, none) is asked once and then left alone.
 *  `looked`: the page has read the run list once (a live run nobody remembers is taken over then). Until the held run
 *  has answered, or - with none held - until that list is in, "Start" is not offered: it could be a second start. */
export function useRunControl(viewedStatus: Json, looked: boolean) {
  const [dir, setDir] = useState<string | null>(remembered);
  const [status, setStatus] = useState<Json>(null);
  const [checked, setChecked] = useState(false);              // the held run has answered at least once (see `refresh`)
  const [pending, setPending] = useState<Pending>(null);
  const [launched, setLaunched] = useState<Launch>(null);
  const [forced, setForced] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const current = useRef({ dir, epoch });
  const reading = useRef<{ key: typeof current.current; promise: Promise<void> } | null>(null);
  // Answers "not there" in a row for the held run. Two are needed, as for the run shown (App.tsx): the engine re-writes
  // run_manifest.json by a rename when a segment starts and ends - just when this poll reads by itself - and on the
  // 9p-mounted D: drive one read at that moment can fail; letting go then took Pause and Abort off a live run.
  const gone = useRef(0);
  // Reads of the held run that got no answer at all, in a row (the backend restarting, a read on that drive failing).
  const unanswered = useRef(0);
  // The last status the page's own poll delivered for the held run (see `fed` below), kept when the page shows another run;
  // `at` and `ownAt` (this hook's own last answer) say which of the two came later (`arrivals` counts them).
  const fedLast = useRef<{ value: Json; at: number } | null>(null);
  const ownAt = useRef(0);
  const arrivals = useRef(0);

  /** Hold another run, or none. Whatever was known belongs to the run held before (or to the time before a launch),
   *  so it is dropped, and an answer that is still on its way for it is ignored when it arrives. */
  const hold = useCallback((next: string | null, launchedAs: Launch) => {
    gone.current = unanswered.current = ownAt.current = 0;
    fedLast.current = null;
    current.current = { dir: next, epoch: current.current.epoch + 1 };
    remember(next);
    setDir(next); setStatus(null); setChecked(false); setPending(null); setLaunched(launchedAs); setForced(false);
    setEpoch(current.current.epoch);
  }, []);
  const take = useCallback((next: string, launchedAs: Launch = null) => hold(next, launchedAs), [hold]);
  const release = useCallback(() => hold(null, null), [hold]);
  // Two requests can overtake each other; an answer the worker wrote before the one on screen is dropped.
  const accept = useCallback((next: Json) => setStatus((now: Json) =>
    now?.heartbeat_utc && next?.heartbeat_utc && next.heartbeat_utc < now.heartbeat_utc ? now : next), []);
  const refresh = useCallback((): Promise<void> => {
    const asked = current.current;
    if (!asked.dir) return Promise.resolve();
    if (reading.current?.key === asked) return reading.current.promise;
    const promise = api.status(asked.dir).then(next => {
      if (current.current !== asked) return;
      gone.current = unanswered.current = 0;
      ownAt.current = ++arrivals.current;
      accept(next);
      setChecked(true);
    }, e => {
      if (current.current !== asked) return;
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        // The remembered run is gone (deleted, or outside the allowed roots by now): let go instead of showing a dead Pause.
        // After a first "not there" it is read once more 1.5 s later (a run at rest is not polled otherwise).
        if (++gone.current >= 2) hold(null, null);
        else setTimeout(() => { if (current.current === asked) refresh(); }, 1500);
        return;
      }
      // No answer (the backend is restarting, a read on the mounted drive failed): the run is not known to be at rest, so
      // the header stays at "checking" - no Start on what may be a live run - and reads again in 3 s, for a minute; only
      // then does the page go on as if the run were at rest. Any error used to count as "checked": a live run showed
      // Start, and was never read again (review of 2026-10-07).
      if (++unanswered.current < 20) setTimeout(() => { if (current.current === asked) refresh(); }, 3000);
      else setChecked(true);
    }).finally(() => { if (reading.current?.key === asked) reading.current = null; });
    reading.current = { key: asked, promise };
    return promise;
  }, [accept, hold]);

  // Just after a launch only answers asked for AFTER it count: the page's own poll may still deliver "paused, no worker".
  const fed = !!dir && !launched && viewedStatus?.run_dir === dir;
  // The page's poll of the held run is used as it arrives, worked out here (record 7.275): it was copied into this hook's
  // state by an effect, which drew the whole page a second time at every status update. Of the two answers the later one
  // counts, as `accept` decides between answers: unless the worker wrote it before the other (by its heartbeat). A status
  // without a heartbeat (a start that failed) is never the older one.
  if (fed && viewedStatus && viewedStatus !== fedLast.current?.value) fedLast.current = { value: viewedStatus, at: ++arrivals.current };
  const fedValue: Json = fedLast.current?.value ?? null;
  const [early, late] = (fedLast.current?.at ?? 0) > ownAt.current ? [status, fedValue] : [fedValue, status];
  const seen: Json = !late || (early?.heartbeat_utc && late.heartbeat_utc && late.heartbeat_utc < early.heartbeat_utc) ? early : late;
  const live = pending !== null || launched !== null || !!seen?.worker_alive;
  useEffect(() => { refresh(); }, [epoch, refresh]);            // once per held run; on page load for the remembered one
  useRequest(refresh, [dir, epoch], { enabled: !!dir && live && !fed, delay: 1500, pollEvery: 1500 });
  // A request of this page stays "pending" until the run itself shows that it arrived.
  useEffect(() => {
    if (!seen) return;
    const alive = !!seen.worker_alive;
    if (pending === 'pause' && (!alive || ['pausing', 'paused'].includes(seen.state))) setPending(null);
    if (pending === 'abort' && (!alive || (seen.state === 'stopping' && !forced))) setPending(null);
    if (launched && (!alive || !TERMINAL.includes(seen.state))) setLaunched(null);
  }, [seen, pending, launched, forced]);

  const unknown = !pending && (dir ? !checked && !seen && !launched : !looked);
  const phase: Phase = unknown ? 'checking' : phaseOf(seen, pending, launched);
  return { dir, status: seen, pending, forced, phase, take, release, refresh, setPending, setForced };
}
export type RunControl = ReturnType<typeof useRunControl>;
