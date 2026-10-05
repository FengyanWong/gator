import { useAsyncAction, useRequest } from '../store';
import { Icon } from './Icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, gateText, Json, problemText } from '../api';
import { TaskFileWindow } from './TaskFile';
import { usePopupWindow } from './popupWindow';

/** "Save task" - a person's press only - and the task file. `task` = the open task (Save task updates it); without one,
 *  the first save of the cell read from Virtuoso (the cell the user declared as their copy is then the task's). The
 *  extras - what the task file holds beside the rows (analyses, variables, bindings, the ring oscillator's rough
 *  frequency, notes) - live here until the save. "Save as" went on 2026-09-23 with the copies the workbench made:
 *  another task is another copy the user makes in Virtuoso, read in the Virtuoso window and saved from there (the backend
 *  still answers `as_new` for the API).
 *  Shown at the right end of the editors' tab line (`bar`), its messages and questions under their toolbar (`notes`) -
 *  user request 2026-09-22: the save sits with the rows it stores. The component stays in the circuit panel, which owns
 *  the cell and the task; two portals put it there.
 *  A save takes about half a minute on a Maestro task. Record 7.198 (user: "show saving ... dont allow another save task
 *  press even after refreshing page"): the backend keeps the save that is running, step by step (task_saving.py); this
 *  component reads it when it appears, follows a running save every second until it ends - its own, one sent before the
 *  page was loaded again, or one from another tab - shows the steps under the toolbar and keeps Save task closed. */

const NAME = /^[a-z][a-z0-9_]{1,39}$/;
const SUFFIX: Record<string, number> = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, K: 1e3 };
const parseFrequency = (text: string) => {
  const m = text.trim().match(/^(\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*([TGMkK]?)(?:hz)?$/i);
  return m ? parseFloat(m[1]) * (SUFFIX[m[2]] ?? 1) : NaN;
};
const suggestTaskName = (cell: string | null | undefined) =>
  (cell ?? '').toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]+/, '').slice(0, 40);
/** Sent by the Agent tab when an approved setup was written into the working copy, naming the parts it wrote (analyses,
 *  variables, bindings). The same parts set here earlier from the task file are older now and are dropped: Save task
 *  then takes them from the copy. */
export const COPY_SETUP_WRITTEN = 'gator-copy-setup-written';
/** Sent instead when the approved setup could NOT be written (Virtuoso out of reach), carrying its parts: they become what
 *  Save task sends, so the next save writes them into the copy (the job "Write to Virtuoso" had until 2026-09-22). */
export const COPY_SETUP_PENDING = 'gator-copy-setup-pending';

/** What a save that ended says: this page's own, or one it followed. */
const savedText = (made: Json) => {
  const kept = made.created ? '' : made.baseline_kept ? ' The recorded baseline still holds.'
    : made.changed?.length ? ' The recorded baseline no longer holds (what is measured changed): run a new baseline.' : '';
  return `${made.created ? `Saved the new task ${made.task_key}.` : `Saved ${made.task_key}, revision ${made.revision}.`}${kept}`;
};
/** The line a running save shows, from the backend's count (its seconds too: the page keeps no clock). The bar stands
 *  halfway through the step that is running. */
const progressOf = (running: Json) => {
  const steps: Json[] = running.steps ?? [], number: number = running.step_number ?? 0;
  const where = number ? `step ${number} of ${steps.length}: ${steps[number - 1].title}` : 'starting';
  const usual = running.usual_seconds ? `; its last save took ${Math.round(running.usual_seconds)} s` : '';
  return { value: number ? number - 0.5 : 0, max: steps.length || 1,
    text: `Saving ${running.task_key} - ${where} (${Math.round(running.seconds ?? 0)} s${usual})` };
};

export function TaskSave({ profileId, library, cell, task, revision, hasCopy, config, setConfig, onSaved, onSavedElsewhere, bar, notes }: {
  profileId: string | null; library: string | null; cell: string | null; task: string | null; revision?: number | null;
  hasCopy: boolean; config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; onSaved: (made: Json, sentConfig: Json) => void;
  onSavedElsewhere: (last: Json) => void; bar: HTMLElement | null; notes: HTMLElement | null }) {
  const [name, setName] = useState('');
  const [message, setMessage] = useState<Json>(null);
  const [extras, setExtras] = useState<Json>({});
  const [askFrequency, setAskFrequency] = useState(false);                    // the save asked for the ring oscillator's rough frequency
  const [frequency, setFrequency] = useState('');
  const [file, setFile] = useState<Json>(null);                               // { text, title } while the window is open (text null: reading)
  const latest = useRef({ config, profileId, library, cell, task });
  latest.current = { config, profileId, library, cell, task };
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  // The task file's window. It is opened INSIDE the click on "Task file" - the browser's pop-up rule refuses a window
  // opened later, when the file has arrived - so a blocked window can be tried again with the next press.
  const fileWindow = usePopupWindow('gator-task-file', { title: 'GATOR - Task file', features: 'popup,width=760,height=900',
    rootId: 'task-file-root', rootClass: 'task-file-window', onClose: () => setFile(null), closeOnUnmount: true });
  // Another task or cell: its extras, its messages, a typed name or frequency and an open task file (the old task's) go.
  useEffect(() => { setExtras({}); setMessage(null); setAskFrequency(false); setName(''); setFrequency(''); setFile(null); fileWindow.popup?.close(); }, [task, library, cell]);
  useEffect(() => {
    const written = (e: Event) => setExtras((x: Json) => {
      const next = { ...x };
      for (const part of (e as CustomEvent<string[]>).detail ?? []) delete next[part];
      return next;
    });
    const pending = (e: Event) => setExtras((x: Json) => ({ ...x, ...((e as CustomEvent<Json>).detail ?? {}) }));
    window.addEventListener(COPY_SETUP_WRITTEN, written);
    window.addEventListener(COPY_SETUP_PENDING, pending);
    return () => { window.removeEventListener(COPY_SETUP_WRITTEN, written); window.removeEventListener(COPY_SETUP_PENDING, pending); };
  }, []);

  // The save running in the backend, read when Save task appears and then every second while one runs (`own`: this
  // page's press is on its way; `followed`: a save the page did not send, asked about until an answer says it ended -
  // a read that fails does not end it). That save says how it ended; the rows stay as they are.
  const own = useRef(false);
  const followed = useRef<string | null>(null);
  const followEvery = useCallback((value: Json) => (value?.running || own.current || followed.current ? 1000 : 0), []);
  const backend = useRequest(signal => api.taskSaving(signal), [], { pollEvery: followEvery, keepPrevious: true });
  const running: Json = backend.value?.running ?? null;
  useEffect(() => {
    const value = backend.value;
    if (!value) return;
    if (value.running) { if (!own.current) followed.current = value.running.id; return; }
    const id = followed.current;
    followed.current = null;
    if (!id) return;
    if (value.last?.id !== id) {                                  // the backend no longer knows it: it was started again
      setMessage({ level: 'warn', text: 'The save that was running ended without an answer (was the backend started again?). '
        + "Look at the task's revision before saving again." });
      onSavedElsewhere({ ok: false });
      return;
    }
    const last = value.last;
    setMessage(last.ok ? { level: 'ok', text: `The save that was running has ended. ${savedText(last.answer)}` }
      : { level: last.problem?.code === 'needs_expected_frequency' ? 'warn' : 'error', text: `The save that was running ended without saving: ${last.problem?.message}` });
    onSavedElsewhere(last);
  }, [backend.value]);

  const suggested = suggestTaskName(cell);
  const taskName = task ?? (name || suggested);
  const report = (e: any) => {
    setMessage({ level: 'error', text: problemText(e, gateText) });
  };
  const { busy, run } = useAsyncAction(e => {
    if (e.detail?.code === 'needs_expected_frequency') { setAskFrequency(true); setMessage({ level: 'warn', text: e.detail.message }); }
    else report(e);
  }, () => setMessage(null));
  const save = (more: Json = {}) => run('save', async () => {
    const sent = { ...extras, ...more };
    const stillHere = () => mounted.current && latest.current.config.circuit === config.circuit
      && latest.current.profileId === profileId && latest.current.library === library && latest.current.cell === cell && latest.current.task === task;
    let made: Json;
    own.current = true; backend.refresh();
    try { made = await api.taskSave({ profile_id: profileId, name: taskName, config, library, cell, task, as_new: false, extras: sent }); }
    catch (e) { if (stillHere()) throw e; return; }
    finally { own.current = false; backend.refresh(); }
    if (!stillHere()) return;
    setExtras((current: Json) => current === extras ? sent : current); setAskFrequency(false);
    const edited = ['parameters', 'measurements', 'targets'].some(key => latest.current.config[key] !== config[key]);
    setMessage({ level: 'ok', text: `${savedText(made)}${edited ? ' Newer editor changes are kept and are not included in this save.' : ''}` });
    onSaved(made, config);
  });
  const openFile = async () => {
    setMessage(null);
    // Already open: bring it forward and keep what is typed in it (a second press used to replace the draft silently).
    if (file && fileWindow.popup && !fileWindow.popup.closed) { fileWindow.popup.focus(); return; }
    const opened = fileWindow.open();
    if (!opened) { setMessage({ level: 'error', text: 'The browser blocked the task file window. Allow pop-ups for this page, then press "Task file" again.' }); return; }
    setFile({ text: null, title: 'Task file' });
    try {
      const answer = await api.taskFile({ config, library, cell, task, extras });
      const title = task ? `Task file of real:${task}${answer.revision ? ` (revision ${answer.revision})` : ''}` : `Task file of ${cell} (not saved yet)`;
      opened.document.title = `GATOR - ${title}`;
      setFile({ text: answer.text, title });
    } catch (e: any) { setFile(null); opened.close(); report(e); }
  };
  const applyFile = (rows: Json, more: Json) => {
    setConfig(c => ({ ...c, parameters: rows.parameters ?? c.parameters, measurements: rows.measurements ?? c.measurements, targets: rows.targets ?? c.targets }), true);
    setExtras((x: Json) => ({ ...x, ...more }));
  };
  const frequencyValue = parseFrequency(frequency);
  const canSave = !!profileId && (task ? true : hasCopy) && NAME.test(taskName) && !busy && !running;
  const progress = running ? progressOf(running) : busy === 'save' ? { value: 0, max: 1, text: `Saving real:${taskName} - starting` } : null;
  const waits = running && busy !== 'save' ? `Waits for the save of ${running.task_key} that is running. ` : '';
  const said = askFrequency || message || progress;
  return (<>
    {bar && createPortal(
      <div className="task-save">
        {!task && <label title="Lowercase letters, digits and _. It becomes the task real:<name>.">New task name
          <input value={name} placeholder={suggested} onChange={e => setName(e.target.value)} /></label>}
        {task && <span className="hint">Task <code>real:{task}</code>{revision ? `, revision ${revision}` : ''}</span>}
        <button className="primary" disabled={!canSave || askFrequency} onClick={() => save()}
          title={'Save task: ' + waits + (task ? 'Stores the rows of Parameters, Probes and Specs as this task (its next revision). ' : hasCopy
            ? 'Stores the rows of Parameters, Probes and Specs as a new task of this cell. '
            : 'Read the cell in the Virtuoso window first and confirm that it is a copy you made: the task is saved into that cell. ')
            + 'It writes the cell in Virtuoso to match and reads it back; no simulation. Only you can press it.'}>
          <Icon name="task" label={busy === 'save' || running ? 'Saving...' : 'Save task'} /></button>
        <button disabled={!!busy} onClick={openFile} title="Task file: The task as one readable file, in a window of its own: open it, change it, apply it to the editors."><Icon name="task-file" label="Task file" /></button>
      </div>, bar)}
    {notes && said && createPortal(
      <div className="task-save-notes">
        {progress && <div className="task-save-progress" role="status"><progress value={progress.value} max={progress.max} /><span>{progress.text}</span></div>}
        {askFrequency && <div className="row">
          <label title="Rough is enough: it only sizes the transient (60 periods, measured after 20).">Rough oscillation frequency
            <input value={frequency} placeholder="e.g. 1.2G" onChange={e => setFrequency(e.target.value)} /></label>
          <button className="primary" disabled={!(frequencyValue > 0) || !canSave} onClick={() => save({ expected_frequency_hz: frequencyValue })} title="Save task: With this frequency."><Icon name="task" label="Save task" /></button></div>}
        {message && <p className={message.level === 'ok' ? 'ok' : message.level === 'warn' ? 'warn' : 'error'}>{message.text}</p>}
      </div>, notes)}
    {file && <TaskFileWindow root={fileWindow.root} text={file.text} title={file.title} onApply={applyFile}
      onClose={() => { setFile(null); fileWindow.popup?.close(); }} />}
  </>);
}
