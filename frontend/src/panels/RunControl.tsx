import { Icon, IconName } from './Icons';
import { useEffect, useRef, useState } from 'react';
import { api, Json, plainError } from '../api';
import { ENDED, type Pending, type Phase, type RunControl } from '../runState';

/** The header's run buttons (user request 2026-09-21): ONE main button that reads Start -> Pause -> Resume, and
 *  Abort next to it. Nothing new happens in the backend; the buttons drive what the engine already does:
 *    Pause  = command `pause`: dispatch stops, the simulation in flight finishes, everything is saved, the worker exits.
 *    Resume = POST /api/runs/continue: the SAME run directory gets a new segment that restores the full saved state
 *             (the machinery of Mode = resume, with the run's own saved configuration - the Mode box is not involved).
 *             It is Continue with the total unchanged, sent by the launcher (launch.ts, record 7.261).
 *    Abort  = command `stop` (the simulation in flight finishes, save, end). While a pause or an abort is still waiting
 *             for that simulation the button reads "Force abort" = command `cancel`, which waits for nothing. On a
 *             paused run it reads "Let go" (record 7.261): it only lets go of the run - nothing is sent.
 *  The header controls ONE run, the "current run": the one started or resumed from this page (remembered across a
 *  reload), whatever run the bottom tabs are showing - a live run never loses its Pause and Abort. The run states and the
 *  header's run itself (useRunControl) are in runState.ts. */

const used = (status: Json) => status?.budget ? ` ${status.budget.charged} / ${status.budget.max_evaluations}` : '';
const WAITING = 'waiting for the simulation in flight';
function describe(status: Json, phase: Phase, forced: boolean): string {
  const text = ({ checking: '', starting: 'starting', resuming: 'resuming', running: `running${used(status)}`, pausing: `pausing - ${WAITING}`, finishing: 'finishing',
    aborting: forced ? 'forced abort sent' : `aborting - ${WAITING}`,
    paused: status?.state === 'interrupted' ? `interrupted at${used(status)} (the worker is gone)` : `paused at${used(status)}${status?.stop_reason === 'infrastructure_failures' ? ' (connection failures)' : ''}`,
    idle: status ? `${status.state}${ENDED.includes(status.state) ? used(status) : ''}` : '' } as Record<Phase, string>)[phase];
  return text && (status?.mock ?? status?.manifest?.mock) ? `${text} [MOCK]` : text;
}

/** A pause is only worth the name if the run can come back. Checkpoints or replay snapshots may have been switched off
 *  for THIS run (its own saved configuration counts, not the page's); then a pause simply ends it, and the user is told
 *  before, not after. Any doubt (file unreadable) is no reason to refuse a pause. */
async function cannotResume(dir: string): Promise<string | null> {
  try {
    const response = await fetch(api.downloadUrl(dir, 'effective_config.json'));
    const config = response.ok ? await response.json() : null;
    const output = config?.output;
    if (output?.save_checkpoints === false) return 'model checkpoints are switched off';
    if (output?.save_replay_snapshots === false) return 'replay snapshots are switched off';
  } catch { /* ask nothing */ }
  return null;
}

/** The questions asked before a pause, an abort and a forced abort by the header's buttons (the Run status tab's copies
 *  of these buttons went on 2026-09-29). */
async function pauseConfirmed(dir: string): Promise<boolean> {
  const reason = await cannotResume(dir);
  return !reason || window.confirm(`This run cannot be resumed after a pause: ${reason} for it.\n\nPause anyway? It is saved and simply ends here.`);
}
// A stopped calibration keeps its completed random designs and can still propose from them.
const abortConfirmed = (status: Json) => window.confirm(`Abort this run?\n\nThe simulation that is running now is allowed to finish, so nothing already paid for is lost and the circuit is put back `
  + `as it was. Then everything is saved and the run ends.${status?.budget ? `\nUsed so far: ${status.budget.charged} of ${status.budget.max_evaluations} evaluations.` : ''}`
  + (status?.calibration ? '\n\nCalibration proposes only from the random designs simulated so far '
    + '(at least 16 must give a reward).' : '')
  + '\n\nTo continue this run later, use Pause instead.');
const forceAbortConfirmed = () => window.confirm('Force abort?\n\nThis does not wait for the simulation that is running. Its evaluation is recorded as cancelled and still counts against the '
  + 'budget. On a real circuit a Spectre job that has already started on the server is not stopped, and the schematic can be left with the sizes '
  + 'that were being tried instead of the original ones.\n\nUse this only when the run is stuck.');

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
const ICONS: Record<Phase, IconName> = { idle: 'play', checking: 'play', starting: 'wait', running: 'pause', pausing: 'wait', paused: 'play',
  resuming: 'wait', aborting: 'wait', finishing: 'wait' };
const LABELS: Record<Phase, string> = { idle: 'Start', checking: 'Start', starting: 'Starting...', running: 'Pause', pausing: 'Pausing...', paused: 'Resume',
  resuming: 'Resuming...', aborting: 'Aborting...', finishing: 'Finishing...' };

/** The run's state at a glance (record 7.360, the Roadster look): Ready, Running, Paused or Ended, the one that holds lit,
 *  as a gear selector shows its gear; then the header's run chip (record 7.264), whose press opens the run brief. */
const STATES = ['Ready', 'Running', 'Paused', 'Ended'] as const;
function stateOf(phase: Phase, status: Json): typeof STATES[number] {
  if (phase === 'paused') return 'Paused';
  if (['starting', 'resuming', 'running', 'pausing', 'aborting', 'finishing'].includes(phase)) return 'Running';
  return phase === 'idle' && status && ENDED.includes(status.state) ? 'Ended' : 'Ready';
}
export function RunChip({ control, onChip, takeover = null }: { control: RunControl; onChip: () => void;
  /** The run the header took over when the page opened (liveRunAdoption.ts): a badge while the header holds it (record 7.372). */
  takeover?: { dir: string; label: string; text: string } | null }) {
  const { dir, status, phase, forced } = control;
  const now = stateOf(phase, dir ? status : null);
  const note = describe(status, phase, forced);
  return (<div className="run-state">
    <span className="run-state-strip" role="img" aria-label={`Run state: ${now.toLowerCase()}`}>
      {STATES.map(s => <span key={s} aria-hidden="true" className={s === now ? 'on' : undefined}>{s}</span>)}</span>
    {dir && note && <button className={`run-chip ${phase}`} onClick={onChip}
      title={`The current run: ${dir}\nPress for the run brief: this run and every other live run, each with Show results and Open in Runs (record 7.264).`}>{note}</button>}
    {dir && takeover?.dir === dir && <span className="run-taken" title={takeover.text}>{takeover.label}</span>}
  </div>);
}

/** `startBlocked` / `resumeBlocked`: why the main button cannot start or resume now (launch.ts readiness), or null - said
 *  as the button's tooltip. Resume itself is the launcher's (`onResume`). `next`: what Start would start, "Next: ..." (record
 *  7.269) - beside the button while it reads Start, and the first sentence of its tooltip. */
export function RunButtons({ control, startBlocked, resumeBlocked, onStart, onResume, onMessage, next = null }: {
  control: RunControl; startBlocked: string | null; resumeBlocked: string | null; onStart: () => void; onResume: () => void;
  onMessage: (m: Json) => void; next?: string | null }) {
  const { dir, status, phase, forced } = control;
  const fail = (e: any) => onMessage({ level: 'error', text: plainError(e), detail: e?.detail });
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
  const main = phase === 'idle' ? onStart : phase === 'running' ? pause : phase === 'paused' ? onResume : undefined;
  const why = phase === 'idle' ? startBlocked : phase === 'paused' ? resumeBlocked : null;
  const startable = phase === 'idle' || phase === 'checking';           // the main button reads Start
  return (<>
    <button className="run-save" disabled={phase !== 'running' || !!saving} onClick={saveNow}
      title={phase === 'running' ? 'Save now: The model is saved now, without pausing: the simulation in flight finishes first (with several in parallel, all of them), the model is written as a new save point, '
        + 'and the run goes on by itself. The save point appears in the saved model\'s Details in the RL model window, where it can be used.'
        : 'Save now: Only while a run is running. A paused or ended run has already saved everything.'}><Icon name="save" label={saving ? 'Saving...' : 'Save now'} /></button>
    {startable && next && <span className="next-run" title={next}>{next}</span>}
    <button className="primary run-main" disabled={!main || !!why} onClick={main} title={`${LABELS[phase]}: ${startable && next ? `${next}. ` : ''}${why ?? TITLES[phase]}`}><Icon name={ICONS[phase]} label={LABELS[phase]} /></button>
    <button className="run-abort" disabled={!(phase === 'running' || phase === 'paused' || (waiting && !forced))} onClick={abort}
      title={phase === 'paused' ? 'Let go: The header lets go of the paused run: nothing is sent and nothing is deleted, the run can still be continued '
          + 'from Runs, and the main button goes back to Start.'
        : waiting ? 'Force abort: Do not wait for the simulation in flight. Only for a run that is stuck.'
        : 'Abort: End the current run: the simulation in flight finishes, everything is saved, the run ends.'}>
      <Icon name={waiting ? 'force-stop' : phase === 'paused' ? 'close' : 'stop'} label={waiting ? 'Force abort' : phase === 'paused' ? 'Let go' : 'Abort'} /></button>
  </>);
}
