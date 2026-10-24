import { Icon, IconName } from './Icons';
import { useEffect, useRef, useState } from 'react';
import { api, Json, plainError } from '../api';
import { count, folderName, plural, runTask, stopWords, timeLine } from '../format';
import { cardLive, ENDED, type Pending, type Phase, type RunControl } from '../runState';

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

// The count says what it counts, and the chip leaves the state word to the strip beside it, which lights it (branch record
// SIF-72: "Running" stood beside "running 292 / 800", a number easy to take for the Training tab's or the next run's).
// A budget of 1 is allowed (an Evaluate only run): "of 1 evaluation" (review of SIF-72). Both counts as the page writes
// them, "12,345 of 20,000 evaluations" (branch record SIF-117).
const used = (status: Json) => status?.budget ? ` ${count(status.budget.charged)} of ${plural(status.budget.max_evaluations, 'evaluation')}` : '';
const WAITING = 'waiting for the simulation in flight';
function describe(status: Json, phase: Phase, forced: boolean): string {
  const at = status?.budget ? `at${used(status)}` : '';
  const text = ({ checking: '', starting: 'starting', resuming: 'resuming', running: used(status).trim() || 'running', pausing: `pausing - ${WAITING}`, finishing: 'finishing',
    aborting: forced ? 'forced abort sent' : `aborting - ${WAITING}`,
    paused: status?.state === 'interrupted' ? `interrupted${at && ` ${at}`} (the worker is gone)` : `${at || 'paused'}${status?.stop_reason === 'infrastructure_failures' ? ' (connection failures)' : ''}`,
    idle: status ? `${status.state}${ENDED.includes(status.state) && at ? ` ${at}` : ''}` : '' } as Record<Phase, string>)[phase];
  return text && (status?.mock ?? status?.manifest?.mock) ? `${text} [MOCK]` : text;
}

/** The task of the header's run (`row`: its line of the run list) when it is not the task the header's title names - told by
 *  its key, or by its name where the list gives no key; null when it is that task, or while the run is not listed. Pause and
 *  Abort act on a run the page may have taken over from another task (branch record SIF-72: the chip read "running 270 /
 *  800" under the title "mscr_vco_lin_c" while its run was one of graphgps_ldo1, which no line on the page named). */
export const otherTask = (row: Json | undefined, taskKey: string | null, taskShown: string | null): string | null =>
  !row || (typeof row.task_key === 'string' ? row.task_key === taskKey : runTask(row) === taskShown) ? null : runTask(row);

/** A pause is only worth the name if the run can come back. Checkpoints or replay snapshots may have been switched off
 *  for THIS run (its own saved configuration counts, not the page's), or the run may be searched by Bayesian optimization,
 *  which the backend never continues (branch record SIF-83: such a run paused without a word, and only Resume's tooltip
 *  said why afterwards); then a pause simply ends it, and the user is told before, not after. Any doubt (file unreadable)
 *  is no reason to refuse a pause. */
async function cannotResume(dir: string): Promise<string | null> {
  try {
    const response = await fetch(api.downloadUrl(dir, 'effective_config.json'));
    const config = response.ok ? await response.json() : null;
    if (config?.run?.optimizer === 'bayes') return 'it is searched by Bayesian optimization, whose search state lives only in its running process';
    const output = config?.output;
    if (output?.save_checkpoints === false) return 'model checkpoints are switched off for it';
    if (output?.save_replay_snapshots === false) return 'replay snapshots are switched off for it';
  } catch { /* ask nothing */ }
  return null;
}

/** The questions asked before a pause, an abort and a forced abort by the header's buttons (the Run status tab's copies
 *  of these buttons went on 2026-09-29). */
async function pauseConfirmed(dir: string): Promise<boolean> {
  const reason = await cannotResume(dir);
  return !reason || window.confirm(`This run cannot be resumed after a pause: ${reason}.\n\nPause anyway? It is saved and simply ends here.`);
}
// A stopped calibration keeps its completed random designs and can still propose from them. `task`: the run's task when the
// header's title names another (branch record SIF-72).
const abortConfirmed = (status: Json, task: string | null) => window.confirm(`Abort this run${task ? ` of ${task}` : ''}?\n\nThe simulation that is running now is allowed to finish, so nothing already paid for is lost and the circuit is put back `
  + `as it was. Then everything is saved and the run ends.${status?.budget ? `\nUsed so far:${used(status)}.` : ''}`
  + (status?.calibration ? '\n\nCalibration proposes only from the random designs simulated so far '
    + '(at least 16 must give a reward).' : '')
  + '\n\nTo continue this run later, use Pause instead.');
// A forced abort ends the run as cancelled, which no Resume or Continue... takes up (runState.ts CONTINUABLE), so the
// question says what is given up beside what the user waits for (branch record SIF-83: pressed while a pause waited, it
// turned a pause that could be resumed into an end with no way back, and the question did not say so).
const FORCED_COST: Partial<Record<Phase, string>> = {
  pausing: 'This replaces your Pause: the run ends as cancelled, and a cancelled run cannot be resumed or continued (a save point it has '
    + 'written can still start a new run in Fine-tune). To keep it resumable, wait for the pause.\n\n',
  aborting: 'The run ends as cancelled instead of stopped, so Continue... can no longer pick it up.\n\n',
};
// `lost`: why the run could not come back anyway (cannotResume), or null. Then waiting keeps nothing resumable and a stopped
// end is no more continuable than a cancelled one, so the question says only what changes, and why nothing more is given up
// (review of branch record SIF-83: a Bayesian run, paused after Pause's own warning, was told to wait "to keep it resumable").
const FORCED_LOST: Partial<Record<Phase, string>> = {
  pausing: 'This replaces your Pause: the run ends as cancelled instead of paused.',
  aborting: 'The run ends as cancelled instead of stopped.',
};
const forcedCost = (phase: Phase, lost: string | null) =>
  lost && FORCED_LOST[phase] ? `${FORCED_LOST[phase]} It cannot come back either way: ${lost}.\n\n` : FORCED_COST[phase] ?? '';
const forceAbortConfirmed = (phase: Phase, lost: string | null) => window.confirm('Force abort?\n\n' + forcedCost(phase, lost)
  + 'This does not wait for the simulation that is running. Its evaluation is recorded as cancelled and still counts against the '
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
export function RunChip({ control, onChip, takeover = null, task = null }: { control: RunControl; onChip: () => void;
  /** The run the header took over when the page opened (liveRunAdoption.ts): a badge while the header holds it (record 7.372). */
  takeover?: { dir: string; label: string; text: string } | null;
  /** The run's task when the header's title names another (`otherTask`): the chip names it first (branch record SIF-72). */
  task?: string | null }) {
  const { dir, status, phase, forced } = control;
  const now = stateOf(phase, dir ? status : null);
  const note = describe(status, phase, forced);
  // The working time and the time left at the end of the tooltip, as the run brief's card for this run says them (branch
  // record SIF-98: they stood only in that window); the chip's text stays the count. The status only when it is this run's,
  // as the brief takes it.
  const own = status?.run_dir === dir ? status : null;
  const time = own ? timeLine(own.active_seconds, own.budget?.charged, own.budget?.max_evaluations, cardLive(own, null)) : null;
  return (<div className="run-state">
    <span className="run-state-strip" role="img" aria-label={`Run state: ${now.toLowerCase()}`}>
      {STATES.map(s => <span key={s} aria-hidden="true" className={s === now ? 'on' : undefined}>{s}</span>)}</span>
    {dir && note && <button className={`run-chip ${phase}`} onClick={onChip}
      title={`The current run${task ? `, a run of ${task}` : ''}: ${dir}\nPress for the run brief: this run and every other live run, each with Show results and Open in Runs (record 7.264).${time ? `\n${time}` : ''}`}>
      {task && <><b>{task}</b>{' · '}</>}{note}</button>}
    {dir && takeover?.dir === dir && <span className="run-taken" title={takeover.text}>{takeover.label}</span>}
  </div>);
}

/** `startBlocked` / `resumeBlocked`: why the main button cannot start or resume now (launch.ts readiness), or null - said
 *  as the button's tooltip. Resume itself is the launcher's (`onResume`). `next`: what Start would start, "Next: ..." (record
 *  7.269) - beside the button while it reads Start, and the first sentence of its tooltip. `task`: the run's task when the
 *  header's title names another (`otherTask`), for the Abort question (branch record SIF-72). */
export function RunButtons({ control, startBlocked, resumeBlocked, onStart, onResume, onMessage, next = null, task = null }: {
  control: RunControl; startBlocked: string | null; resumeBlocked: string | null; onStart: () => void; onResume: () => void;
  onMessage: (m: Json) => void; next?: string | null; task?: string | null }) {
  const { dir, status, phase, forced } = control;
  const fail = (e: any) => onMessage({ level: 'error', text: plainError(e), detail: e?.detail });
  const command = (name: string, waitFor: Pending, text: string) => {
    control.setPending(waitFor);
    return api.command(dir!, name).then(() => { onMessage({ level: 'info', text }); return control.refresh(); })
      .catch(e => { control.setPending(null); fail(e); });
  };

  // Why the run could not come back anyway (cannotResume), read once it waits on a pause or an abort, whoever sent it: this
  // page, another one or the command line, where Pause's question was never seen. Force abort's question and tooltip then
  // promise no way back the run never had (review of branch record SIF-83); until the answer is in, the general words stand.
  const waiting = phase === 'pausing' || phase === 'aborting';
  const [lost, setLost] = useState<{ dir: string; reason: string | null } | null>(null);
  useEffect(() => {
    if (!dir || !waiting) return;
    let live = true;
    cannotResume(dir).then(reason => { if (live) setLost({ dir, reason }); });
    return () => { live = false; };
  }, [dir, waiting]);
  const noWayBack = lost?.dir === dir ? lost.reason : null;

  const pause = async () => {
    control.setPending('pause');                                                  // at once: a second press must find "Pausing..."
    if (!(await pauseConfirmed(dir!))) { control.setPending(null); return; }
    command('pause', 'pause', 'Pausing: the simulation in flight finishes first, then everything is saved. Resume continues from exactly there.');
  };
  const abort = () => {
    if (phase === 'paused') {
      // The way back names the Continue... buttons that exist (branch record SIF-48): since record 7.267 a double click in
      // the Runs window LOADS the run - its task into the editors, its model as the next run's - which this used to advise.
      if (!window.confirm('Let go of this paused run?\n\nNothing is deleted: its data and its saved state stay in the run directory, and it can still be continued '
        + 'later: press "Runs..." at the bottom, open the run\'s Details, then Continue... (or Show results, then Continue... under Run status).'
        + '\n\nThe main button goes back to Start, for a new run.')) return;
      control.release();
      // The run by its folder's name, its full path in the line's tooltip (branch record SIF-56), as after Start.
      onMessage({ level: 'info', text: `Left paused, nothing deleted: ${folderName(dir!)}`, title: dir });
    } else if (phase === 'running') {
      if (!abortConfirmed(status, task)) return;
      command('stop', 'abort', 'Aborting: the simulation in flight finishes first, then everything is saved and the run ends.');
    } else {
      if (!forceAbortConfirmed(phase, noWayBack)) return;
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
      // the evaluations name the save point, its id in the line's tooltip (branch record SIF-70: the line said both)
      onMessage({ level: 'info', text: `Saved at ${plural(answer.evaluations, 'evaluation')}. The run goes on.`, title: `save point ${answer.checkpoint_id}` });
    } else if (phase !== 'running') setSaving(null);             // paused, aborted or ended meanwhile: that saves everything anyway
  }, [status, phase, saving]);

  // The line under the header said "Pausing: ..." / "Aborting: ..."; say so when it has happened. A run that ends or pauses
  // with no press is said too (branch record SIF-89: a completed or failed run changed only the chip and the lit state, a
  // failure's reason was the last row of Run status, and a pause after connection failures could read "Resume continues from
  // exactly there" as if the user had paused, though Resume first needs the connection check to pass). Only a change of the
  // SAME run counts: taking a run over, letting go of one and a reload's lookup ("checking") say nothing. The run's path is
  // the new lines' tooltip, as after Start (SIF-56).
  const before = useRef({ phase, dir });
  useEffect(() => {
    const was = before.current.phase, same = before.current.dir === dir;
    before.current = { phase, dir };
    if (!same || !status) return;
    const at = status.budget ? ` at${used(status)}` : '';
    const ended = phase === 'idle' && ['running', 'finishing', 'pausing', 'aborting'].includes(was), unasked = was === 'running' || was === 'finishing';
    // Only a pause the run wrote is "everything is saved": a worker gone before that (the engine drains, cleans up over a dead
    // link and saves first) leaves an `interrupted` run that keeps its stop reason, where only what was acknowledged is kept;
    // its chip says "(the worker is gone)" and no line is added (review of SIF-89).
    const paused = phase === 'paused' && status.state === 'paused';
    if (paused && status.stop_reason === 'infrastructure_failures' && (was === 'running' || was === 'pausing'))
      onMessage({ level: 'error', text: 'Paused by itself after connection failures; everything is saved. Test the connection (Connection button), then Resume.', title: dir });
    else if (was === 'pausing' && paused) onMessage({ level: 'info', text: `Paused at${used(status)}: everything is saved. Resume continues from exactly there.` });
    else if (ended && status.state === 'failed') onMessage({ level: 'error', text: `The run failed${at}: ${status.error ?? 'see Run status'}`, title: dir });
    else if (ended && unasked && status.state === 'completed')
      onMessage({ level: 'info', text: `Completed${at}${status.stop_reason ? ` (${stopWords(status.stop_reason)})` : ''}. Its results are under Run status.`, title: dir });
    else if (ended && (!unasked || ENDED.includes(status.state))) onMessage({ level: 'info', text: `The run has ended (${status.state}) at${used(status)}: everything it committed is saved.` });
  }, [phase, dir]);

  const main = phase === 'idle' ? onStart : phase === 'running' ? pause : phase === 'paused' ? onResume : undefined;
  const why = phase === 'idle' ? startBlocked : phase === 'paused' ? resumeBlocked : null;
  const startable = phase === 'idle' || phase === 'checking';           // the main button reads Start
  // One group in the header (branch record SIF-136): as four of its parts they wrapped apart, and with Calibration ready open
  // at 1680 px Abort stood alone on a second row, under the GATOR chip. The header now wraps them as one.
  return (<span className="run-buttons">
    <button className="run-save" disabled={phase !== 'running' || !!saving} onClick={saveNow}
      title={phase === 'running' ? 'Save now: The model is saved now, without pausing: the simulation in flight finishes first (with several in parallel, all of them), the model is written as a new save point, '
        + 'and the run goes on by itself. The save point appears in the saved model\'s Details in the RL model window, where it can be used.'
        : 'Save now: Only while a run is running. A paused or ended run has already saved everything.'}><Icon name="save" label={saving ? 'Saving...' : 'Save now'} /></button>
    {startable && next && <span className="next-run" title={next}>{next}</span>}
    <button className="primary run-main" disabled={!main || !!why} onClick={main} title={`${LABELS[phase]}: ${startable && next ? `${next}. ` : ''}${why ?? TITLES[phase]}`}><Icon name={ICONS[phase]} label={LABELS[phase]} /></button>
    <button className="run-abort" disabled={!(phase === 'running' || phase === 'paused' || (waiting && !forced))} onClick={abort}
      title={phase === 'paused' ? 'Let go: The header lets go of the paused run: nothing is sent and nothing is deleted, the run can still be continued '
          + 'from Runs, and the main button goes back to Start.'
        : phase === 'pausing' ? 'Force abort: Do not wait for the simulation in flight. This replaces your Pause: the run ends as cancelled'
          + `${noWayBack ? '' : ' and cannot be resumed'}. Only for a run that is stuck.`
        : waiting ? 'Force abort: Do not wait for the simulation in flight. Only for a run that is stuck.'
        : 'Abort: End the current run: the simulation in flight finishes, everything is saved, the run ends.'}>
      <Icon name={waiting ? 'force-stop' : phase === 'paused' ? 'close' : 'stop'} label={waiting ? 'Force abort' : phase === 'paused' ? 'Let go' : 'Abort'} /></button>
  </span>);
}
