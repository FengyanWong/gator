// One launcher (record 7.261; plan docs/plan-frontend-run-workflow.md, "One launcher" and "Existing runs: continued in
// place"). Start, Calibration, Resume and Continue go through here, where each did every step its own way in App.start,
// App.continueRun and RunButtons.resume until then:
//   1. readiness - one pure function per action says whether it can run and why not, in words the button shows;
//   2. one pending state - the header's (useRunControl.setPending), so a second press anywhere finds "Starting...";
//   3. the questions the backend asks (launchWithConsent), as before;
//   4. a request id for each launch, kept in this tab until it is answered: a repeat gets the run the first one made,
//      and after a reload during a launch the page asks what became of it instead of sending it again;
//   5. on success the run becomes the header's run and the shown run, in one place, named in the message;
//   6. on refusal the backend's reason stays beside the action until what it depends on changes - no fallback.
// Request ids and the continuation check are used only where the backend lists them (GET /api/meta `features`): a page
// newer than its backend works as before until the backend is restarted.

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, Json, plainError } from './api';
import { useRequest } from './store';
import type { RunControl } from './panels/RunControl';

export type Action = 'start' | 'calibration' | 'resume' | 'continue';
export type Features = { requests: boolean; continuation: boolean };
export const featuresOf = (meta: Json): Features => {
  const listed: unknown[] = Array.isArray(meta?.features) ? meta.features : [];
  return { requests: listed.includes('launch_requests'), continuation: listed.includes('continuation_check') };
};

// ---- the launch on its way, kept in this tab (sessionStorage) until its answer has arrived ----------------------------------
const LAUNCH_KEY = 'gator-workbench-launch-v1';
type SentLaunch = { id: string; action: Action; run_dir: string | null; at: number };
const sentLaunch = (): SentLaunch | null => {
  try {
    const kept = JSON.parse(sessionStorage.getItem(LAUNCH_KEY) ?? 'null');
    return kept && typeof kept.id === 'string' ? kept : null;
  } catch { return null; }
};
const keepLaunch = (launch: SentLaunch | null) => {
  try { if (launch) sessionStorage.setItem(LAUNCH_KEY, JSON.stringify(launch)); else sessionStorage.removeItem(LAUNCH_KEY); } catch { /* blocked storage: no recovery after a reload */ }
};
/** A launch of this tab is still waiting for its answer (or for the page to ask after a reload). */
export const launchKept = () => sentLaunch() !== null;
const newRequestId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;

/** The question when the BACKEND says a run is real although the page took it for MOCK (a task chosen a moment ago
 *  whose circuit had not been read yet, or a run whose status was not known): worded from the backend's own report,
 *  never from the page's MOCK text - an OK here authorizes real simulations (audit 2026-09-30). */
const realQuestion = (report: Json) => `This runs REAL simulations${report?.task_key ? ` of ${report.task_key}` : ''} (the page had taken it for a MOCK run).\n`
  + `Authorize a total budget of ${report?.requested_max_evaluations ?? 'its'} candidate evaluation(s)?`;

/** The backend never starts on a guess: it refuses, creates nothing, and names what it needs - the budget of a REAL
 *  simulation, a model trained on another task, connection layers it could not check. Each question is put to the
 *  user once and the request is repeated with the answers. Returns null when the user said no. */
export async function launchWithConsent(send: (flags: Json) => Promise<Json>, options: { real: boolean; authorizeText: string; transfer?: boolean }): Promise<Json | null> {
  const flags: Json = {};
  if (options.real) {
    if (!window.confirm(options.authorizeText)) return null;
    flags.authorize_real_simulation = true;
  }
  for (;;) {
    try { return await send(flags); } catch (e: any) {
      const detail = e?.detail ?? {};
      let flag: string | null = null, question = '';
      if (detail.code === 'real_authorization_required')
        [flag, question] = ['authorize_real_simulation', options.real ? options.authorizeText : realQuestion(detail.report)];
      else if (detail.code === 'confirm_transfer' && options.transfer) [flag, question] = ['confirm_transfer', `${detail.report?.reason}\n\nLoad this model for a NEW task (fine_tune creates a new run with a parent)?`];
      else if (detail.code === 'connection_gate_acknowledge') [flag, question] = ['acknowledge_unknown_connection', `Connection layers are UNKNOWN: ${detail.report?.uncertain?.join(', ')}.\nUnknown is not OK. Proceed anyway?`];
      if (!flag || flags[flag]) throw e;                                          // not a question, or already answered
      if (!window.confirm(question)) return null;
      flags[flag] = true;
    }
  }
}

// ---- the budget form's number ------------------------------------------------------------------------------------------------
/** The new total of the budget form (plan: "Whole numbers only; '1,200' reads as 1200"). Digits, or digits in groups of three
 *  (1,200 - also with a space, an underscore or an apostrophe); a separator elsewhere (12,00) is a typo and is said, never
 *  guessed. Empty = the run's own total, unless that is used up. The total has to be more than the evaluations used: one
 *  equal to them would end the run at once. `value` null with no error = unchanged. (Number("1,200") is not a number: the
 *  browser's prompt silently kept the budget then.) */
export function parseTotal(text: string, used: number | null, total: number | null): { value: number | null; error: string | null } {
  const plain = text.trim();
  if (!plain) return used != null && total != null && used >= total
    ? { value: null, error: `All ${total} evaluations are used: type a new total above ${used}.` } : { value: null, error: null };
  const grouped = /^\d{1,3}([,\s_']\d{3})+$/.test(plain);
  if (!/^\d+$/.test(plain) && !grouped) return { value: null, error: /^\d*\.\d+$/.test(plain) ? 'Whole evaluations only: a total has no fractions.'
    : /^[\d,\s_'.]+$/.test(plain) ? 'A separator belongs between groups of three digits: write 1,200 or 1200.'
    : 'Type the new total as a whole number, for example 1200.' };
  const value = Number(plain.replace(/[,\s_']/g, ''));
  if (used != null && value <= used) return { value: null, error: value === used
    ? `${used} evaluations are used already: the new total must be more than that.` : `The total cannot be below the ${used} evaluations already used.` };
  return { value, error: null };
}

/** The question before a run goes on (Resume, Continue...), with the numbers of the budget form: the evaluations the save
 *  point has used, the new total, and how many more that allows. A MOCK run asks nothing. */
export function continueConsent(status: Json, check: Json | null, newTotal: number | null): { real: boolean; authorizeText: string } {
  const real = (status?.mock ?? status?.manifest?.mock) === false;
  const used: number | null = check?.used ?? status?.budget?.charged ?? null;
  const total: number | null = newTotal ?? check?.total ?? status?.budget?.max_evaluations ?? null;
  const left = used != null && total != null ? Math.max(0, total - used) : null;
  return { real, authorizeText: (real ? 'This continues REAL simulations (Virtuoso/Spectre, or ngspice for an ngspice netlist task).\n' : 'This continues the synthetic run.\n')
    + (left === null ? 'Authorize the rest of its evaluation budget?' : `Authorize up to ${left} more candidate evaluation(s)? (${used} of ${total} are used.)`) };
}

// ---- readiness: why each action cannot run now, or null ------------------------------------------------------------------------
const HEADER_BUSY: Record<string, string> = {
  checking: 'The header is still looking up which run is live; a moment.',
  starting: 'The header is starting a run; a moment.',
  resuming: 'The header is continuing a run; a moment.',
  running: 'A run is live in the header: pause it or let it finish first.',
  pausing: 'The header\'s run is pausing; a moment.',
  aborting: 'The header\'s run is ending; a moment.',
  finishing: 'The header\'s run is writing its last files; a moment.',
};

/** Start and Calibration: a new run, from the configuration on this page. One live run at a time on this page; a paused one
 *  is let go of first (the header's second button). The backend's session lock stays the real guard for real simulations. */
export function startReadiness(phase: string, validation: Json): string | null {
  if (phase === 'paused') return 'Not while the header holds a paused run: Let go of it first (the button beside Resume), or Resume it.';
  if (phase !== 'idle') return HEADER_BUSY[phase] ?? 'A run is live in the header.';
  if (validation?.blocks_run) {
    const count = (validation.issues ?? []).filter((i: Json) => i.level === 'error').length;
    return `The configuration has ${count || 'a'} blocking issue${count === 1 ? '' : 's'}: the red button in the header lists ${count === 1 ? 'it' : 'them'}.`;
  }
  return null;
}

/** Continue of a run (the Run status tab's Continue..., and the header's Resume, which is Continue with the total
 *  unchanged). `check`: the backend's continuation check of THAT run (null: not asked yet, or an older backend - the
 *  status decides then, as before). `held`: the header holds this run. */
export function continueReadiness({ status, check, phase, held, total }: { status: Json; check: Json | null; phase: string; held: boolean; total: 'unchanged' | 'form' }): string | null {
  if (!status) return 'Reading the run...';
  if (status.worker_alive) return 'This run is running now.';
  const resting = ['paused', 'stopped', 'interrupted'].includes(status.state) || (status.state === 'completed' && total === 'form' && !!check);
  if (!resting) return status.state === 'completed' ? 'This run has completed.' : `A ${status.state ?? 'new'} run cannot be continued.`;
  // One live run at a time on this page: a continued run becomes the header's run.
  if (phase === 'checking' || phase === 'starting' || phase === 'resuming') return HEADER_BUSY[phase];
  if (!held && phase !== 'idle' && phase !== 'paused')
    return 'Another run is live in the header: pause it or let it finish first (a second live run would have no Pause or Abort on this page).';
  if (check) {
    if (!check.eligible) return check.reason ?? 'The backend says this run cannot be continued.';
    if (total === 'unchanged' && check.exhausted) return `All ${check.total} evaluations are used: raise the total with Continue... under Run status.`;
    return null;
  }
  if (status.save_point === null) return 'This run folder holds no save point - a copy made without them, or they were deleted - so there is nothing to go on from.';
  if (status.save_point_code === 'older') return 'This run was saved by an older version of the optimizer code, and continuing it needs exactly that version. Its model still loads in a new run: fine-tune or frozen.';
  return null;
}

/** The continuation check of one run at rest (GET /api/runs/continuation), asked again when its status changes: the
 *  reason Continue cannot go on, BEFORE the press, and the numbers of the budget form. Null while unknown, while the run is
 *  live, and with a backend that has no such check. */
export function useContinuation(features: Features, runDir: string | null, status: Json): Json | null {
  const key = runDir && status?.run_dir === runDir && !status.worker_alive
    ? [runDir, status.state, status.heartbeat_utc, status.save_point, status.save_point_code, status.last_checkpoint_utc, status.budget?.max_evaluations].join('|') : null;
  const { value } = useRequest<Json>(signal => api.continuation(runDir!, null, signal), [key], { enabled: features.continuation && !!key });
  return key && value?.run_dir === runDir ? value : null;
}

/** A launch the backend refused: its words stay beside the action until what it depends on changes (`key`). */
export type Refusal = { action: Action; text: string; detail: Json; key: string };

/** The launcher. `onLaunched(started, as, note)`: make the run the header's run and the shown run, and name it. */
export function useLauncher({ control, features, onLaunched, onMessage }: {
  control: RunControl; features: Features; onMessage: (m: Json) => void;
  onLaunched: (started: Json, as: 'start' | 'resume', note?: string) => void }) {
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const going = useRef(false);
  const latest = useRef({ control, onLaunched, onMessage });
  latest.current = { control, onLaunched, onMessage };

  /** Every launch: one at a time, one pending state, its request id kept until it is answered, the backend's questions,
   *  and the run handed to the header - or the refusal kept with `key`. */
  const go = useCallback(async (action: Action, key: string, runDir: string | null, send: (flags: Json) => Promise<Json>,
    consent: { real: boolean; authorizeText: string; transfer?: boolean }, declined: string, note?: (started: Json) => string | undefined) => {
    if (going.current) return;                                // a second press anywhere finds the first one on its way
    going.current = true;
    const { control: header } = latest.current;
    const as = action === 'start' || action === 'calibration' ? 'start' : 'resume';
    header.setPending(as);
    let handed = false, answered = true;
    try {
      // A launch of this page that got no answer at all is asked about first: it may have arrived and made a run.
      const earlier = features.requests ? sentLaunch() : null;
      if (earlier) {
        const known = await api.launchRequest(earlier.id).catch(() => ({ state: 'unknown' }));
        if (known?.state === 'done' && known.answer?.run_dir) {
          keepLaunch(null);
          setRefusal(null);
          handed = true;
          latest.current.onLaunched(known.answer, earlier.action === 'start' || earlier.action === 'calibration' ? 'start' : 'resume',
            'An earlier launch of this page, whose answer had not arrived, made this run; nothing new was sent.');
          return;
        }
        if (known?.state === 'pending') { answered = false; setRefusal({ action, text: 'An earlier launch of this page is still on its way; its run comes in a moment.', detail: null, key }); return; }
      }
      const launch: SentLaunch | null = features.requests ? { id: newRequestId(), action, run_dir: runDir, at: Date.now() } : null;
      keepLaunch(launch);
      const started = await launchWithConsent(flags => send(launch ? { ...flags, request_id: launch.id } : flags), consent);
      if (!started) { latest.current.onMessage({ level: 'info', text: declined }); return; }
      setRefusal(null);
      handed = true;
      latest.current.onLaunched(started, as, note?.(started));
    } catch (e: any) {
      // No answer at all - the page is going away (a reload aborts the request), or the backend stopped: the request may have
      // arrived, so its id stays kept, and the page asks what became of it instead of sending it again.
      answered = e instanceof ApiError;
      setRefusal({ action, text: plainError(e), detail: e?.detail, key });
      if (e?.detail?.code === 'already_running') latest.current.control.refresh();     // continued from elsewhere: show what is true
    } finally {
      if (answered) keepLaunch(null);
      going.current = false;
      if (!handed) latest.current.control.setPending(null);
    }
  }, [features.requests]);

  /** After a reload during a launch: the page asks what became of it instead of sending it again. Done: the run it made
   *  is taken. On its way: "Starting..." until it is answered. Unknown: it never arrived, or was refused - nothing was made.
   *  Asked once per launch kept (React's StrictMode mounts the page twice in development: `asked` and `mounted` hold). */
  const asked = useRef<string | null>(null);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const sent = features.requests ? sentLaunch() : null;
    if (!sent || asked.current === sent.id) return;
    asked.current = sent.id;
    const as = sent.action === 'start' || sent.action === 'calibration' ? 'start' : 'resume';
    const ask = (tries: number): void => {
      api.launchRequest(sent.id).then(answer => {
        if (!mounted.current) return;
        if (answer?.state === 'done' && answer.answer?.run_dir) {
          keepLaunch(null);
          latest.current.onLaunched(answer.answer, as, `The ${sent.action === 'calibration' ? 'Calibration' : sent.action} sent before the page was reloaded `
            + 'made this run; it was not sent again.');
        } else if (answer?.state === 'pending' && tries < 600) {
          latest.current.control.setPending(as);
          setTimeout(() => ask(tries + 1), 1500);
        } else {
          keepLaunch(null);
          latest.current.control.setPending(null);
        }
      }, () => { if (mounted.current) { keepLaunch(null); latest.current.control.setPending(null); } });
    };
    ask(0);
  }, [features.requests]);

  return { go, refusal, setRefusal, busy: going };
}
