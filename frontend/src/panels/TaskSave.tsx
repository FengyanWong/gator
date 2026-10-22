import { noteRowsFrom, noteTaskSaved, rowsFrom, useAsyncAction, useRequest } from '../store';
import { Icon } from './Icons';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, gateText, Json, problemText } from '../api';
import { FileDraft, otherPartsChanged, TaskFileWindow, unapplied } from './TaskFile';
import { usePopupWindow } from './popupWindow';

/** "Save as" prompts for a numbered new name (record 7.246), or the name of a save refused (branch record SIF-92). An
 *  open task is saved through the existing `as_new` API, with its own DUT/testbench copies; a cell's first save takes the
 *  copy the user declared. Calibration's explicit "Apply and save" still updates its current task. The extras beside the
 *  rows live here until either kind of save.
 *  Shown at the right end of the editors' tab line (`bar`), its messages and questions under their toolbar (`notes`) -
 *  user request 2026-09-22: the save sits with the rows it stores. The component stays in the circuit panel, which owns
 *  the cell and the task; two portals put it there.
 *  A save takes about half a minute on a Maestro task. Record 7.198 (user: "show saving ... dont allow another save task
 *  press even after refreshing page"): the backend keeps the save that is running, step by step (task_saving.py); this
 *  component reads it when it appears, follows a running save every second until it ends - its own, one sent before the
 *  page was loaded again, or one from another tab - shows the steps under the toolbar and keeps Save task closed.
 *  Record 7.203: rows older than the saved task - it was saved again after they were loaded - would undo what was saved
 *  since; the backend refuses them with what they would undo, and the page asks: Reload saved values, or Save anyway. */

const NAME = /^[a-z][a-z0-9_]{1,39}$/;
const SUFFIX: Record<string, number> = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, K: 1e3 };
const parseFrequency = (text: string) => {
  const m = text.trim().match(/^(\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*([TGMkK]?)(?:hz)?$/i);
  return m ? parseFloat(m[1]) * (SUFFIX[m[2]] ?? 1) : NaN;
};
const suggestTaskName = (cell: string | null | undefined) =>
  (cell ?? '').toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]+/, '').slice(0, 40);
/** Keep successive copies in one numbering sequence when their original task is still in the list. */
const numberedName = (original: string, used: Set<string>) => {
  const match = original.match(/^(.*)_(\d+)$/);
  const base = match && Number.isSafeInteger(Number(match[2]) + 1) && used.has(match[1]) ? match[1] : original;
  let number = match && base !== original ? Number(match[2]) + 1 : 2;
  for (;;) {
    const suffix = `_${number++}`;
    const candidate = base.slice(0, 40 - suffix.length) + suffix;
    if (!used.has(candidate)) return candidate;
  }
};
type SaveChoice = { name: string; asNew: boolean };
/** The editors' three tables as one text: what a task file was read from (branch record SIF-93). */
const rowsKey = (c: Json) => JSON.stringify([c.parameters, c.measurements, c.targets]);
/** "Apply and save" (record 7.217): another part of the page asks the open task's Save task to run, as a press on it would.
 *  The save is sent in the render after the request, so a change made in the same click is in it. The answer comes at
 *  once: whether Save task took it, or why not (another task, no Save task on the page, a save already running). */
export const SAVE_TASK_REQUEST = 'gator-save-task-request';
/** The summary of the rows not saved (record 7.372, `Editors.tsx`) asks for Save as, as a press on it would. The answer
 *  comes at once, as Apply and save's does: whether Save as took it, or why not (record 7.376). */
export const SAVE_AS_REQUEST = 'gator-save-as-request';
export function requestSaveAs(): { taken: boolean; why: string } {
  const detail = { taken: false, why: 'Save as is not on the page for this task' };
  window.dispatchEvent(new CustomEvent(SAVE_AS_REQUEST, { detail }));
  return detail;
}
export function requestTaskSave(taskKey: string): { task: string; taken: boolean; why: string } {
  const detail = { task: taskKey, taken: false, why: 'this task cannot be saved from this page' };
  window.dispatchEvent(new CustomEvent(SAVE_TASK_REQUEST, { detail }));
  return detail;
}

export const TASK_BASELINE_STARTED = 'gator-task-baseline-started';
export const baselineText = (made: Json) => made.baseline?.state === 'started'
  ? ' Its baseline is starting automatically: one simulation of its starting design.'
  : made.baseline?.state === 'blocked' ? ` The task is saved, but its baseline could not start: ${made.baseline.reason}` : '';
export const followTaskBaseline = (made: Json) => {
  if (made.baseline?.run_dir) window.dispatchEvent(new CustomEvent(TASK_BASELINE_STARTED, { detail: made.baseline }));
};

/** What a save that ended says: this page's own, or one it followed. */
const savedText = (made: Json) => {
  const kept = made.created ? '' : made.baseline_kept ? ' The recorded baseline still holds.'
    : made.changed?.length ? ' The recorded baseline no longer holds (what is measured changed).' : '';
  return `${made.created ? `Saved the new task ${made.task_key}.` : `Saved ${made.task_key}, revision ${made.revision}.`}${kept}${baselineText(made)}`;
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

export function TaskSave({ profileId, library, cell, task, hasCopy, config, setConfig, onSaved, onSavedElsewhere, onReload, bar, notes }: {
  profileId: string | null; library: string | null; cell: string | null; task: string | null;
  hasCopy: boolean; config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; onSaved: (made: Json, sentConfig: Json) => void;
  onSavedElsewhere: (last: Json) => void; onReload?: () => void; bar: HTMLElement | null; notes: HTMLElement | null }) {
  const [choice, setChoice] = useState<SaveChoice | null>(null);
  const [message, setMessage] = useState<Json>(null);
  const [extras, setExtras] = useState<Json>({});
  const [askFrequency, setAskFrequency] = useState(false);                    // the save asked for the ring oscillator's rough frequency
  const [newer, setNewer] = useState<Json>(null);                             // the save was refused: the rows are older than the task
  const [frequency, setFrequency] = useState('');
  const [file, setFile] = useState<Json>(null);                               // { text, title } while the window is open (text null: reading)
  // What is typed in it (branch record SIF-87): kept here, so that a close - Close, the window's X, the banner's Close all -
  // keeps a draft not applied for the next "Task file" press, which reads the file again and lays the draft over it.
  const [fileDraft, setFileDraft] = useState<FileDraft | null>(null);
  const closedFile = () => { setFile(null); setFileDraft(d => (unapplied(d) ? { ...d, kept: true } : null)); };
  // Branch record SIF-93. The file is a snapshot: `fileRows`, the editors' rows it was read from (or that its last Apply
  // left, taken after that render, so that rows the backend writes out its own way are no change); while the editors
  // differ, the window says an Apply replaces those changes. `pending`: the parts beside the rows that applied files
  // changed since the last save, counted from the first file read since (`fileBase`) - they wait here, unseen, and a
  // reload or another task drops them, so a line under the toolbar names them until a save sends them.
  const [fileRows, setFileRows] = useState<string | null>(null);
  const [applied, setApplied] = useState(0);
  const [pending, setPending] = useState<string[]>([]);
  const fileBase = useRef<string | null>(null);
  const latest = useRef({ config, profileId, library, cell, task, pending });
  latest.current = { config, profileId, library, cell, task, pending };
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [asked, setAsked] = useState(0);                                      // saves asked for by "Apply and save" (record 7.217)
  const able = useRef({ can: false, why: '' });
  // The task file's window. It is opened INSIDE the click on "Task file" - the browser's pop-up rule refuses a window
  // opened later, when the file has arrived - so a blocked window can be tried again with the next press.
  const fileWindow = usePopupWindow('gator-task-file', { title: 'GATOR - Task file', features: 'popup,width=760,height=900',
    rootId: 'task-file-root', rootClass: 'task-file-window', onClose: closedFile, closeOnUnmount: true });
  // Another task or cell: its extras, its messages, a typed name or frequency and an open task file (the old task's) go,
  // with what was typed in that file.
  useEffect(() => { setExtras({}); setMessage(null); setAskFrequency(false); setNewer(null); setChoice(null); setFrequency(''); setFile(null); setFileDraft(null); fileWindow.popup?.close();
    setPending([]); fileBase.current = null; setFileRows(null); }, [task, library, cell]);
  useLayoutEffect(() => { if (applied) setFileRows(rowsKey(latest.current.config)); }, [applied]);   // before paint: no flash of "changed"

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
    noteTaskSaved();                                              // the rows here may differ from the task now (record 7.222)
    if (value.last?.id !== id) {                                  // the backend no longer knows it: it was started again
      setMessage({ level: 'warn', text: 'The save that was running ended without an answer (was the backend started again?). '
        + "Look at the task's revision before saving again." });
      onSavedElsewhere({ ok: false });
      return;
    }
    const last = value.last;
    setMessage(last.ok ? { level: last.answer?.baseline?.state === 'blocked' ? 'warn' : 'ok', text: `The save that was running has ended. ${savedText(last.answer)}` }
      : { level: last.problem?.code === 'needs_expected_frequency' ? 'warn' : 'error', text: `The save that was running ended without saving: ${last.problem?.message}` });
    if (last.ok) followTaskBaseline(last.answer);
    onSavedElsewhere(last);
  }, [backend.value]);

  const suggested = task || suggestTaskName(cell) || 'task';
  const taskName = choice?.name ?? suggested;
  const stillHere = () => mounted.current && latest.current.config.circuit === config.circuit
    && latest.current.profileId === profileId && latest.current.library === library && latest.current.cell === cell && latest.current.task === task;
  const report = (e: any) => {
    setMessage({ level: 'error', text: problemText(e, gateText) });
  };
  const { busy, run } = useAsyncAction(e => {
    if (e.detail?.code === 'needs_expected_frequency') { setAskFrequency(true); setMessage({ level: 'warn', text: e.detail.message }); }
    else if (e.detail?.code === 'saved_task_newer') setNewer(e.detail);
    else report(e);
  }, () => { setMessage(null); setNewer(null); });
  const storeTask = async (selected: SaveChoice, more: Json = {}, replaceNewer = false) => {
    const sent = { ...extras, ...more };
    setChoice(selected);
    let made: Json;
    own.current = true; backend.refresh();
    const base = task ? rowsFrom(`real:${task}`) : null;            // which saved revision the rows came from (record 7.203)
    try { made = await api.taskSave({ profile_id: profileId, name: selected.name, config, library, cell, task, as_new: selected.asNew, extras: sent,
      base_revision: base, replace_newer: replaceNewer }); }
    catch (e) { if (stillHere()) throw e; return; }
    finally { own.current = false; backend.refresh(); }
    followTaskBaseline(made);
    if (!stillHere()) return;
    noteRowsFrom(made.task_key, made.revision);
    setExtras((current: Json) => current === extras ? sent : current); setAskFrequency(false);
    // Sent: the file's other parts no longer wait (branch record SIF-93) - unless a file applied during the save added more.
    if (latest.current.pending === pending) { setPending([]); fileBase.current = null; }
    const edited = ['parameters', 'measurements', 'targets'].some(key => latest.current.config[key] !== config[key]);
    setMessage({ level: made.baseline?.state === 'blocked' ? 'warn' : 'ok', text: `${savedText(made)}${edited ? ' Newer editor changes are kept and are not included in this save.' : ''}` });
    onSaved(made, config);
  };
  const save = (more: Json = {}, replaceNewer = false) => run('save', () => storeTask(choice ?? { name: suggested, asNew: false }, more, replaceNewer));
  const saveAs = () => run('naming', async () => {
    let listed: Json;
    try { listed = await api.tasks(); } catch (e) { if (stillHere()) throw e; return; }
    if (!stillHere()) return;
    const used = new Set<string>((listed.tasks ?? []).flatMap((t: Json) => [String(t.task_key).replace(/^[^:]+:/, ''), ...(typeof t.name === 'string' ? [t.name] : [])]));   // a shown name (record 7.302) is taken too
    if (task) used.add(task);
    // After a refused save, the name chosen for it is offered again (branch record SIF-92: the numbered name came back, and
    // the name typed was lost at each refusal - frequent while a task is set up). Another task or cell clears the choice and
    // a saved name is in the list, so a choice not in it was not saved. The first proposal stays numbered (record 7.246).
    let proposed = choice && NAME.test(choice.name) && !used.has(choice.name) ? choice.name : numberedName(suggested, used);
    let problem = '';
    for (;;) {
      const entered = window.prompt(`${problem}Save as: new task name\nUse 2–40 lowercase letters, digits or underscores, starting with a letter.\n`
        + (task ? 'Creates a new task with its own DUT and testbench copies, then runs one baseline simulation automatically.' : 'Saves the cell you declared as a new task, then runs one baseline simulation automatically.'), proposed);
      if (entered === null || !stillHere()) return;
      proposed = entered.trim();
      if (!NAME.test(proposed)) { problem = 'That name is invalid.\n\n'; continue; }
      if (used.has(proposed)) { problem = 'That name is already in use. Choose a new name.\n\n'; continue; }
      return saveNew({ name: proposed, asNew: !!task });
    }
  });
  const saveNew = (selected: SaveChoice) => run('save', () => storeTask(selected));
  // "Apply and save": the request names the task; this Save task answers at once, and saves with the rows of the next render.
  useEffect(() => {
    const request = (e: Event) => {
      const detail = (e as CustomEvent<Json>).detail;
      if (!detail || !latest.current.task || detail.task !== `real:${latest.current.task}`) return;
      detail.taken = able.current.can; detail.why = able.current.why || 'saving is not available';
      if (able.current.can) setAsked(n => n + 1);
    };
    window.addEventListener(SAVE_TASK_REQUEST, request);
    return () => window.removeEventListener(SAVE_TASK_REQUEST, request);
  }, []);
  useEffect(() => { if (asked) run('save', () => storeTask({ name: suggested, asNew: false })); }, [asked]);
  // Save as asked by the summary of the rows not saved (record 7.372): as a press on the button, when the button may be pressed.
  const saveAsNow = useRef(saveAs);
  saveAsNow.current = saveAs;
  useEffect(() => {
    const request = (e: Event) => {
      const detail = (e as CustomEvent<Json>).detail;
      if (detail) { detail.taken = able.current.can; detail.why = able.current.why || 'Save as is not available'; }
      if (able.current.can) saveAsNow.current();
    };
    window.addEventListener(SAVE_AS_REQUEST, request);
    return () => window.removeEventListener(SAVE_AS_REQUEST, request);
  }, []);
  const openFile = async () => {
    setMessage(null);
    // Already open: bring it forward and keep what is typed in it (a second press used to replace the draft silently).
    if (file && fileWindow.popup && !fileWindow.popup.closed) { fileWindow.popup.focus(); return; }
    const opened = fileWindow.open();
    if (!opened) { setMessage({ level: 'error', text: 'The browser blocked the task file window. Allow pop-ups for this page, then press "Task file" again.' }); return; }
    setFile({ text: null, title: 'Task file' });
    try { await readFile(opened); } catch (e: any) { setFile(null); opened.close(); report(e); }
  };
  // The file of the editors as they are now, into the window (`owner`): its title, its text and the rows it was read from.
  const readFile = async (owner: Window) => {
    const sent = config;
    const answer = await api.taskFile({ config: sent, library, cell, task, extras });
    if (owner.closed || !mounted.current) return false;           // closed meanwhile - another task or cell closes it too
    const title = task ? `Task file of ${task}${answer.revision ? ` (revision ${answer.revision})` : ''}` : `Task file of ${cell} (not saved yet)`;
    owner.document.title = `GATOR - ${title}`;
    setFile({ text: answer.text, title });
    setFileRows(rowsKey(sent));
    if (fileBase.current === null) fileBase.current = answer.text;
    return true;
  };
  // "Read again from the editors" in the window (branch record SIF-93; it asked about a draft not applied): the draft goes.
  // A read that fails keeps the file and the draft, and the window says why.
  const rereadFile = async () => {
    const owner = fileWindow.popup;
    if (owner && !owner.closed && await readFile(owner)) setFileDraft(null);
  };
  const applyFile = (rows: Json, more: Json, text: string) => {
    setConfig(c => ({ ...c, parameters: rows.parameters ?? c.parameters, measurements: rows.measurements ?? c.measurements, targets: rows.targets ?? c.targets }), true);
    setExtras((x: Json) => ({ ...x, ...more }));
    const base = fileBase.current ?? file?.text ?? text;
    fileBase.current = base;
    setPending(otherPartsChanged(base, text));
    setApplied(n => n + 1);
  };
  const frequencyValue = parseFrequency(frequency);
  const canSave = !!profileId && (task ? true : hasCopy) && !busy && !running;
  // The rough frequency's question can end without a save (branch record SIF-92): until then only a frequency or another
  // task or cell ended it, the tab line's Save as staying off. The chosen name stays, for the next Save as to offer. Not
  // while the save with a frequency is on its way.
  const stopAsking = () => { if (busy) return; setAskFrequency(false); setFrequency(''); setMessage(null); };
  able.current = { can: canSave && !askFrequency && !!task, why: running ? `the save of ${running.task_key} is still running`
    : busy ? 'a save is under way' : !profileId ? 'no connection is chosen' : askFrequency ? 'the save waits for the rough frequency' : '' };
  const progress = running ? progressOf(running) : busy === 'save' ? { value: 0, max: 1, text: `Saving real:${taskName} - starting` } : null;
  const waits = running && busy !== 'save' ? `Waits for the save of ${running.task_key} that is running. ` : '';
  const said = askFrequency || message || progress || newer || pending.length > 0;
  const editorsChanged = !!file?.text && fileRows !== null && rowsKey(config) !== fileRows;
  return (<>
    {bar && createPortal(
      <div className="task-save">
        {/* The task and its revision start the tab line (record 7.362): this holds Save as and Task file only. Greyed out
            for want of a connection, its tooltip says so and where to choose one (branch record SIF-68). */}
        <button className="primary" disabled={!canSave || askFrequency} onClick={saveAs}
          title={'Save as: ' + waits + (!profileId ? 'Not available: no connection is chosen - choose one with the Connection button in the header. ' : '') + 'Asks for a new task name, with the next available numbered name suggested (after a refused save, the name chosen for it). ' + (task ? 'Stores the rows of Parameters, Probes and Specs as a new task with its own DUT and testbench copies. ' : hasCopy
            ? 'Stores the rows of Parameters, Probes and Specs as a new task of this cell. '
            : 'Read the cell in the Virtuoso window first and confirm that it is a copy you made: the task is saved into that cell. ')
            + 'It writes the cell in Virtuoso to match and reads it back, then automatically runs one baseline simulation. Only you can press it.'}>
          <Icon name="task" label={busy === 'save' || running ? 'Saving...' : 'Save as'} /></button>
        <button disabled={!!busy} onClick={openFile} title="Task file: The task as one readable file, in a window of its own: open it, change it, apply it to the editors."><Icon name="task-file" label="Task file" /></button>
      </div>, bar)}
    {notes && said && createPortal(
      <div className="task-save-notes">
        {progress && <div className="task-save-progress" role="status"><progress value={progress.value} max={progress.max} /><span>{progress.text}</span></div>}
        {/* A form (branch record SIF-92): Enter in the box saves as the row's Save as does, under the same rule; Escape
            is Cancel. */}
        {askFrequency && <form className="row" onSubmit={e => { e.preventDefault(); if (frequencyValue > 0 && canSave) save({ expected_frequency_hz: frequencyValue }); }}
          onKeyDown={e => { if (e.key === 'Escape') stopAsking(); }}>
          <label title="Rough is enough: it only sizes the transient (60 periods, measured after 20).">Rough oscillation frequency
            <input value={frequency} placeholder="e.g. 1.2G" onChange={e => setFrequency(e.target.value)} /></label>
          <button type="submit" className="primary" disabled={!(frequencyValue > 0) || !canSave} title="Save as: Keeps the chosen name and saves with this frequency. Enter in the box does the same."><Icon name="task" label="Save as" /></button>
          <button type="button" disabled={!!busy} onClick={stopAsking} title="Cancel: Nothing is saved. Save as asks for a name again, with the one you chose suggested.">Cancel</button></form>}
        {newer && <div className="task-save-newer">
          <p className="warn">{newer.message}</p>
          <div className="row">
            {onReload && <button onClick={() => { setNewer(null); onReload(); }}
              title="Reload saved values: Puts the saved rows of the task into the editors. Asks before discarding edits; Undo takes it back.">Reload saved values</button>}
            <button disabled={!canSave} onClick={() => save({}, true)}
              title="Save anyway: Stores the rows here as the next revision, replacing what was saved since.">Save anyway</button>
          </div></div>}
        {pending.length > 0 && <p className="warn task-file-pending">From the task file, not saved yet: {pending.join(', ')}. Save as stores them; a reload or another task drops them.</p>}
        {message && <p className={message.level === 'ok' ? 'ok' : message.level === 'warn' ? 'warn' : 'error'}>{message.text}</p>}
      </div>, notes)}
    {file && <TaskFileWindow root={fileWindow.root} text={file.text} title={file.title} draft={fileDraft} setDraft={setFileDraft}
      editorsChanged={editorsChanged} onReread={rereadFile} onApply={applyFile} onClose={() => { closedFile(); fileWindow.popup?.close(); }} />}
  </>);
}
