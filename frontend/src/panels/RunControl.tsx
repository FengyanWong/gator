import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, Json } from '../api';

/** The header's run buttons (user request 2026-09-21): ONE main button that reads Start -> Pause -> Resume, and
 *  Abort next to it. Nothing new happens in the backend; the buttons drive what the engine already does:
 *    Pause  = command `pause`: dispatch stops, the simulation in flight finishes, everything is saved, the worker exits.
 *    Resume = POST /api/runs/continue: the SAME run directory gets a new segment that restores the full saved state
 *             (the machinery of Mode = resume, with the run's own saved configuration - the Mode box is not involved).
 *    Abort  = command `stop` (the simulation in flight finishes, save, end). While a pause or an abort is still waiting
 *             for that simulation the button reads "Force abort" = command `cancel`, which waits for nothing.
 *  The header controls ONE run, the "current run": the one started or resumed from this page (remembered across a
 *  reload), whatever run the bottom tabs are showing - a live run never loses its Pause and Abort. */

const RUN_KEY = 'gator-workbench-current-run-v1';
const TERMINAL = ['completed', 'paused', 'stopped', 'cancelled', 'failed'];
const RESUMABLE = ['paused', 'interrupted'];
export const LIVE_STATES = ['starting', 'running', 'pausing', 'stopping'];

export type Phase = 'idle' | 'checking' | 'starting' | 'running' | 'pausing' | 'paused' | 'resuming' | 'aborting' | 'finishing';
type Launch = null | 'start' | 'resume';
type Pending = Launch | 'pause' | 'abort';

/** `pending`: a request of this page that the run has not shown yet. `launched`: this page has just started a worker.
 *  Until its first status is written (it imports for 2-3 s) the file still shows how the PREVIOUS segment ended
 *  ("paused"), although the run is on its way again. */
export function phaseOf(status: Json, pending: Pending, launched: Launch): Phase {
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

const remembered = (): string | null => { try { return localStorage.getItem(RUN_KEY) || null; } catch { return null; } };
const remember = (dir: string | null) => { try { dir ? localStorage.setItem(RUN_KEY, dir) : localStorage.removeItem(RUN_KEY); } catch { /* private mode */ } };

/** `viewedStatus` is the status the page already polls for the run shown in the bottom tabs. When that is the current
 *  run it is used as it arrives and no second poll runs. Otherwise the current run is polled here, and only while it
 *  is live: a run at rest (paused, ended, none) is asked once and then left alone.
 *  `looked`: the page has read the run list once (a live run nobody remembers is taken over then). Until the held run
 *  has answered, or - with none held - until that list is in, "Start" is not offered: it could be a second start. */
export function useRunControl(viewedStatus: Json, looked: boolean) {
  const [dir, setDir] = useState<string | null>(remembered);
  const [status, setStatus] = useState<Json>(null);
  const [checked, setChecked] = useState(false);              // the held run has answered (or failed to) at least once
  const [pending, setPending] = useState<Pending>(null);
  const [launched, setLaunched] = useState<Launch>(null);
  const [forced, setForced] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const current = useRef({ dir, epoch });

  /** Hold another run, or none. Whatever was known belongs to the run held before (or to the time before a launch),
   *  so it is dropped, and an answer that is still on its way for it is ignored when it arrives. */
  const hold = useCallback((next: string | null, launchedAs: Launch) => {
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
    return api.status(asked.dir).then(next => { if (current.current === asked) accept(next); }, e => {
      // The remembered run is gone (deleted, or outside the allowed roots by now): let go instead of showing a dead Pause.
      if (e instanceof ApiError && (e.status === 403 || e.status === 404) && current.current === asked) hold(null, null);
    }).then(() => { if (current.current === asked) setChecked(true); });
  }, [accept, hold]);

  // Just after a launch only answers asked for AFTER it count: the page's own poll may still deliver "paused, no worker".
  const fed = !!dir && !launched && viewedStatus?.run_dir === dir;
  const live = pending !== null || launched !== null || !!status?.worker_alive;
  useEffect(() => { refresh(); }, [epoch, refresh]);            // once per held run; on page load for the remembered one
  useEffect(() => { if (fed) { accept(viewedStatus); setChecked(true); } }, [fed, viewedStatus, accept]);
  useEffect(() => {
    if (!dir || !live || fed) return;
    const id = window.setInterval(refresh, 1500);
    return () => window.clearInterval(id);
  }, [dir, live, fed, refresh]);
  // A request of this page stays "pending" until the run itself shows that it arrived.
  useEffect(() => {
    if (!status) return;
    const alive = !!status.worker_alive;
    if (pending === 'pause' && (!alive || ['pausing', 'paused'].includes(status.state))) setPending(null);
    if (pending === 'abort' && (!alive || (status.state === 'stopping' && !forced))) setPending(null);
    if (launched && (!alive || !TERMINAL.includes(status.state))) setLaunched(null);
  }, [status, pending, launched, forced]);

  const unknown = !pending && (dir ? !checked && !status && !launched : !looked);
  const phase: Phase = unknown ? 'checking' : phaseOf(status, pending, launched);
  return { dir, status, pending, forced, phase, take, release, refresh, setPending, setForced };
}
export type RunControl = ReturnType<typeof useRunControl>;

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
      if (detail.code === 'real_authorization_required') [flag, question] = ['authorize_real_simulation', options.authorizeText];
      else if (detail.code === 'confirm_transfer' && options.transfer) [flag, question] = ['confirm_transfer', `${detail.report?.reason}\n\nLoad this model for a NEW task (fine_tune creates a new run with a parent)?`];
      else if (detail.code === 'connection_gate_acknowledge') [flag, question] = ['acknowledge_unknown_connection', `Connection layers are UNKNOWN: ${detail.report?.uncertain?.join(', ')}.\nUnknown is not OK. Proceed anyway?`];
      if (!flag || flags[flag]) throw e;                                          // not a question, or already answered
      if (!window.confirm(question)) return null;
      flags[flag] = true;
    }
  }
}

/** Continue a paused (or interrupted) run in its own directory, with its own saved configuration.
 *  `maxEvaluations` = a new TOTAL budget, or null to keep the run's budget. */
export function resumeRun(dir: string, status: Json, maxEvaluations: number | null): Promise<Json | null> {
  const budget = status?.budget, total = maxEvaluations ?? budget?.max_evaluations;
  const left = budget && typeof total === 'number' ? Math.max(0, total - budget.charged) : null;
  return launchWithConsent(flags => api.continueRun({ run_dir: dir, max_evaluations: maxEvaluations, ...flags }), {
    real: (status?.mock ?? status?.manifest?.mock) === false,
    authorizeText: 'This continues REAL Virtuoso/Spectre simulations in the paused run.\n' + (left === null ? 'Authorize the rest of its evaluation budget?'
      : `Authorize up to ${left} more candidate evaluation(s)? (${budget.charged} of ${total} are used.)`) });
}

const used = (status: Json) => status?.budget ? ` ${status.budget.charged} / ${status.budget.max_evaluations}` : '';
const WAITING = 'waiting for the simulation in flight';
function describe(status: Json, phase: Phase, forced: boolean): string {
  const text = ({ checking: '', starting: 'starting', resuming: 'resuming', running: `running${used(status)}`, pausing: `pausing - ${WAITING}`, finishing: 'finishing',
    aborting: forced ? 'forced abort sent' : `aborting - ${WAITING}`,
    paused: status?.state === 'interrupted' ? `interrupted at${used(status)} (the worker is gone)` : `paused at${used(status)}${status?.stop_reason === 'infrastructure_failures' ? ' (connection failures)' : ''}`,
    idle: status ? `${status.state}${['completed', 'stopped', 'cancelled', 'failed'].includes(status.state) ? used(status) : ''}` : '' } as Record<Phase, string>)[phase];
  return text && (status?.mock ?? status?.manifest?.mock) ? `${text} [MOCK]` : text;
}

/** A pause is only worth the name if the run can come back. Checkpoints or replay snapshots may have been switched off
 *  for THIS run (its own saved configuration counts, not the page's); then a pause simply ends it, and the user is told
 *  before, not after. Any doubt (file unreadable) is no reason to refuse a pause. */
async function cannotResume(dir: string): Promise<string | null> {
  try {
    const response = await fetch(api.downloadUrl(dir, 'effective_config.json'));
    const output = response.ok ? (await response.json())?.output : null;
    if (output?.save_checkpoints === false) return 'model checkpoints are switched off';
    if (output?.save_replay_snapshots === false) return 'replay snapshots are switched off';
  } catch { /* ask nothing */ }
  return null;
}

/** The questions asked before a pause, an abort and a forced abort - by the header's buttons AND by the Run status tab's,
 *  which used to act on one click and offered a forced cancel while nothing was waiting (review of 2026-09-22). */
export async function pauseConfirmed(dir: string): Promise<boolean> {
  const reason = await cannotResume(dir);
  return !reason || window.confirm(`This run cannot be resumed after a pause: ${reason} for it.\n\nPause anyway? It is saved and simply ends here.`);
}
export const abortConfirmed = (status: Json) => window.confirm(`Abort this run?\n\nThe simulation that is running now is allowed to finish, so nothing already paid for is lost and the circuit is put back `
  + `as it was. Then everything is saved and the run ends.${status?.budget ? `\nUsed so far: ${status.budget.charged} of ${status.budget.max_evaluations} evaluations.` : ''}`
  + '\n\nTo continue this run later, use Pause instead.');
export const forceAbortConfirmed = () => window.confirm('Force abort?\n\nThis does not wait for the simulation that is running. Its evaluation is recorded as cancelled and still counts against the '
  + 'budget. On a real circuit a Spectre job that has already started on the server is not stopped, and the schematic can be left with the sizes '
  + 'that were being tried instead of the original ones.\n\nUse this only when the run is stuck.');
/** A forced abort is offered only while a pause or an abort is waiting for the simulation in flight. */
export const forceAllowed = (status: Json) => !!status?.worker_alive && ['pausing', 'stopping'].includes(status?.state);

const TITLES: Record<Phase, string> = {
  idle: 'Start a new run with the configuration on this page.',
  checking: 'Looking up the run this page was controlling, or one that is still active.',
  starting: 'The backend is checking the configuration and starting the worker.',
  running: 'Pause: no new simulation is started, the one in flight finishes, everything is saved. Resume continues from exactly there.',
  pausing: 'Pause requested. The simulation in flight is finishing; then everything is saved.',
  paused: 'Continue this run in the same run directory from its saved state (network, replay memory, counters, budget). '
    + 'It continues with the settings it was started with; changes made on this page since then are not used.',
  resuming: 'The backend is checking the saved state and starting the worker.',
  aborting: 'Abort requested. The simulation in flight is finishing; then everything is saved and the run ends.',
  finishing: 'The run has ended and is writing its last files.',
};
const LABELS: Record<Phase, string> = { idle: 'Start', checking: 'Start', starting: 'Starting...', running: 'Pause', pausing: 'Pausing...', paused: 'Resume',
  resuming: 'Resuming...', aborting: 'Aborting...', finishing: 'Finishing...' };

export function RunButtons({ control, blocked, onStart, onResumed, onMessage, onShow }: {
  control: RunControl; blocked: boolean; onStart: () => void; onResumed: (started: Json) => void;
  onMessage: (m: Json) => void; onShow: (dir: string) => void }) {
  const { dir, status, phase, forced } = control;
  const fail = (e: any) => onMessage({ level: 'error', text: `${e?.detail?.code ?? 'rejected'}: ${e?.message ?? e}`, detail: e?.detail });
  const command = (name: string, waitFor: Pending, text: string) => {
    control.setPending(waitFor);
    return api.command(dir!, name).then(() => { onMessage({ level: 'info', text }); return control.refresh(); })
      .catch(e => { control.setPending(null); fail(e); });
  };

  const pause = async () => {
    control.setPending('pause');                                                  // at once: a second press must find "Pausing..."
    if (!(await pauseConfirmed(dir!))) { control.setPending(null); return; }
    command('pause', 'pause', 'Pausing: the simulation in flight finishes first, then everything is saved. Resume continues from exactly there.');
  };
  const resume = async () => {
    control.setPending('resume');
    try {
      const started = await resumeRun(dir!, status, null);
      if (!started) { control.setPending(null); onMessage({ level: 'info', text: 'Not resumed: you answered no. The run stays paused.' }); return; }
      control.take(started.run_dir, 'resume');
      onResumed(started);
    } catch (e: any) {
      control.setPending(null);
      if (e?.detail?.code === 'already_running') control.refresh();                // continued from elsewhere: show what is true
      fail(e);
    }
  };
  const abort = () => {
    if (phase === 'paused') {
      if (!window.confirm('Let go of this paused run?\n\nNothing is deleted: its data and its saved state stay in the run directory, and it can still be continued '
        + 'later (press "Runs..." at the bottom, double click the run, then Run status > Continue).\n\nThe main button goes back to Start, for a new run.')) return;
      control.release();
      onMessage({ level: 'info', text: `Left paused, nothing deleted: ${dir}` });
    } else if (phase === 'running') {
      if (!abortConfirmed(status)) return;
      command('stop', 'abort', 'Aborting: the simulation in flight finishes first, then everything is saved and the run ends.');
    } else {
      if (!forceAbortConfirmed()) return;
      control.setForced(true);
      command('cancel', 'abort', 'Forced abort sent: the evaluation in flight is recorded as cancelled and stays charged.');
    }
  };

  // "Save now" = command `checkpoint` (user request 2026-09-21): the RUNNING worker writes a save point at its next safe
  // boundary (the simulation in flight finishes first) and goes on. No pause, so `pending` and the phase stay untouched.
  // `saving` holds the id of the request this page waits for; the run answers in status.manual_save.
  const [saving, setSaving] = useState<string | null>(null);
  const saveNow = () => {
    setSaving('sent');
    api.command(dir!, 'checkpoint').then(record => {
      setSaving(record.id);
      onMessage({ level: 'info', text: 'Save requested: the model is saved as soon as the simulation in flight has finished. The run goes on by itself.' });
      return control.refresh();
    }).catch(e => { setSaving(null); fail(e); });
  };
  useEffect(() => {
    if (!saving || saving === 'sent') return;
    const answer = status?.manual_save;
    if (answer?.id === saving && answer.state === 'saved') {
      setSaving(null);
      onMessage({ level: 'info', text: `Saved at ${answer.evaluations} evaluations as save point ${answer.checkpoint_id}. The run goes on.` });
    } else if (phase !== 'running') setSaving(null);             // paused, aborted or ended meanwhile: that saves everything anyway
  }, [status, phase, saving]);

  // The line under the header said "Pausing: ..." / "Aborting: ..."; say so when it has happened.
  const before = useRef(phase);
  useEffect(() => {
    const was = before.current; before.current = phase;
    if (was === 'pausing' && phase === 'paused') onMessage({ level: 'info', text: `Paused at${used(status)}: everything is saved. Resume continues from exactly there.` });
    else if ((was === 'pausing' || was === 'aborting') && phase === 'idle' && status) onMessage({ level: 'info', text: `The run has ended (${status.state}) at${used(status)}: everything it committed is saved.` });
  }, [phase]);

  const waiting = phase === 'pausing' || phase === 'aborting';
  const main = phase === 'idle' ? onStart : phase === 'running' ? pause : phase === 'paused' ? resume : undefined;
  const note = describe(status, phase, forced);
  return (<>
    {dir && note && <button className={`run-chip ${phase}`} onClick={() => onShow(dir)} title={`The current run: ${dir}\nPress to show it under Run status.`}>{note}</button>}
    <button className="run-save" disabled={phase !== 'running' || !!saving} onClick={saveNow}
      title={phase === 'running' ? 'Save the model now, without pausing: the simulation in flight finishes first (with several in parallel, all of them), the model is written as a new save point, '
        + 'and the run goes on by itself. The save point can be chosen later under "RL model to load".'
        : 'Only while a run is running. A paused or ended run has already saved everything.'}>{saving ? 'Saving...' : 'Save now'}</button>
    <button className="primary run-main" disabled={!main || (phase === 'idle' && blocked)} onClick={main} title={TITLES[phase]}>{LABELS[phase]}</button>
    <button className="run-abort" disabled={!(phase === 'running' || phase === 'paused' || (waiting && !forced))} onClick={abort}
      title={phase === 'paused' ? 'Let go of the paused run: nothing is deleted, the main button goes back to Start.'
        : waiting ? 'Do not wait for the simulation in flight. Only for a run that is stuck.'
        : 'End the current run: the simulation in flight finishes, everything is saved, the run ends.'}>{waiting ? 'Force abort' : 'Abort'}</button>
  </>);
}
