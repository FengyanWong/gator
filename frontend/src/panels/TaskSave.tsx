import { useEffect, useState } from 'react';
import { api, Json } from '../api';
import { TaskFileWindow } from './TaskFile';

/** "Save task" - a person's press only - and what goes with it: "Save as" (another task, with a working copy of its own)
 *  and the task file. `task` = the open task (Save task updates it); without one, the first save of the cell (its
 *  working copy is then the task's). The extras - what the task file holds beside the rows (analyses, variables,
 *  bindings, the ring oscillator's rough frequency, notes) - live here until the save. */

const gateText = (gate: Json) => `Virtuoso cannot be reached (${[...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') || gate.status}). `
  + 'Bring the link up in the Connection window, then try again.';
const NAME = /^[a-z][a-z0-9_]{1,39}$/;
const SUFFIX: Record<string, number> = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, K: 1e3 };
export const parseFrequency = (text: string) => {
  const m = text.trim().match(/^(\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*([TGMkK]?)(?:hz)?$/i);
  return m ? parseFloat(m[1]) * (SUFFIX[m[2]] ?? 1) : NaN;
};
export const suggestTaskName = (cell: string | null | undefined) =>
  (cell ?? '').toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]+/, '').slice(0, 40);
/** Sent by the Agent tab when an approved setup was written into the working copy, naming the parts it wrote (analyses,
 *  variables, bindings). The same parts set here earlier from the task file are older now and are dropped: Save task
 *  then takes them from the copy. */
export const COPY_SETUP_WRITTEN = 'gator-copy-setup-written';

export function TaskSave({ profileId, library, cell, task, revision, hasCopy, config, setConfig, onSaved }: {
  profileId: string | null; library: string | null; cell: string | null; task: string | null; revision?: number | null;
  hasCopy: boolean; config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; onSaved: (made: Json) => void }) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<Json>(null);
  const [extras, setExtras] = useState<Json>({});
  const [askFrequency, setAskFrequency] = useState<string | null>(null);      // which save asked: 'save' | 'as'
  const [frequency, setFrequency] = useState('');
  const [asking, setAsking] = useState(false);
  const [newName, setNewName] = useState('');
  const [file, setFile] = useState<Json>(null);                               // { text, title } while the window is open
  useEffect(() => { setExtras({}); setMessage(null); setAskFrequency(null); setAsking(false); }, [task, library, cell]);
  useEffect(() => {
    const written = (e: Event) => setExtras((x: Json) => {
      const next = { ...x };
      for (const part of (e as CustomEvent<string[]>).detail ?? []) delete next[part];
      return next;
    });
    window.addEventListener(COPY_SETUP_WRITTEN, written);
    return () => window.removeEventListener(COPY_SETUP_WRITTEN, written);
  }, []);

  const suggested = suggestTaskName(cell);
  const taskName = task ?? (name || suggested);
  const report = (e: any) => {
    const gate = e.detail?.gate;
    setMessage({ level: 'error', text: e.status === 404 || e.status === 405 ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).'
      : gate ? gateText(gate) : e.message });
  };
  const save = async (asNew: boolean, target: string, more: Json = {}) => {
    setBusy(asNew ? 'as' : 'save'); setMessage(null);
    const sent = { ...extras, ...more };
    try {
      const made = await api.taskSave({ profile_id: profileId, name: target, config, library, cell, task, as_new: asNew, extras: sent });
      setExtras(sent); setAskFrequency(null); setAsking(false); setNewName('');
      const kept = made.created ? '' : made.baseline_kept ? ' The recorded baseline still holds.' : made.changed?.length ? ' The recorded baseline no longer holds (what is measured changed): run a new baseline.' : '';
      setMessage({ level: 'ok', text: `${made.created ? `Saved the new task ${made.task_key}.` : `Saved ${made.task_key}, revision ${made.revision}.`}${made.runnable ? '' : ' It can be opened and edited; running Maestro-measured tasks comes with the next part.'}${kept}` });
      onSaved(made);
    } catch (e: any) {
      if (e.detail?.code === 'needs_expected_frequency') { setAskFrequency(asNew ? 'as' : 'save'); setMessage({ level: 'warn', text: e.detail.message }); }
      else report(e);
    } finally { setBusy(null); }
  };
  const openFile = async () => {
    setMessage(null);
    try {
      const answer = await api.taskFile({ config, library, cell, task, extras });
      setFile({ text: answer.text, title: task ? `Task file of real:${task}${answer.revision ? ` (revision ${answer.revision})` : ''}` : `Task file of ${cell} (not saved yet)` });
    } catch (e: any) { report(e); }
  };
  const applyFile = (rows: Json, more: Json) => {
    setConfig(c => ({ ...c, parameters: rows.parameters ?? c.parameters, measurements: rows.measurements ?? c.measurements, targets: rows.targets ?? c.targets }), true);
    setExtras((x: Json) => ({ ...x, ...more }));
  };
  const frequencyValue = parseFrequency(frequency);
  const canSave = !!profileId && (task ? true : hasCopy) && NAME.test(taskName) && !busy;
  return (
    <div className="task-save">
      <div className="row">
        {!task && <label title="Lowercase letters, digits and _. It becomes the task real:<name>.">New task name
          <input value={name} placeholder={suggested} onChange={e => setName(e.target.value)} /></label>}
        {task && <span className="hint">Task <code>real:{task}</code>{revision ? `, revision ${revision}` : ''}.</span>}
        <button className="primary" disabled={!canSave} onClick={() => save(false, taskName)}
          title={task ? 'Stores the editors\' rows as this task (its next revision).' : hasCopy ? 'Stores the editors\' rows as a new task of this cell.' : 'Make a working copy first (above).'}>
          {busy === 'save' ? 'Saving...' : 'Save task'}</button>
        {task && <button disabled={!!busy || !profileId} onClick={() => { setAsking(a => !a); setAskFrequency(null); }}>Save as</button>}
        <button disabled={!!busy} onClick={openFile} title="The task as one readable file, in a window of its own: open it, change it, apply it to the editors.">Task file</button>
      </div>
      <span className="hint">{task ? 'Save task stores the editors\' rows as this task; Save as makes another.' : 'Stores the Parameters, Probes and Specs rows as a task of this cell.'} Only you can press it.</span>
      <details className="more hint"><summary>What Save task does</summary>
        <p>It checks the rows, makes the working copy in Virtuoso say what the task says (for a task measured by Maestro: its outputs, specs
          and analyses, read back afterwards), reads the copy into the workbench again and stores the task file with the task's files next
          to it. No simulation. Saving again makes the next revision of the same task; the recorded baseline is kept only if what is
          measured did not change. <b>Save as</b> makes another task, with a copy of its own in Virtuoso.</p></details>
      {askFrequency && <div className="row">
        <label title="Rough is enough: it only sizes the transient (60 periods, measured after 20).">Rough oscillation frequency
          <input value={frequency} placeholder="e.g. 1.2G" onChange={e => setFrequency(e.target.value)} /></label>
        <button className="primary" disabled={!(frequencyValue > 0) || !!busy}
          onClick={() => askFrequency === 'as' ? save(true, newName, { expected_frequency_hz: frequencyValue }) : save(false, taskName, { expected_frequency_hz: frequencyValue })}>
          {askFrequency === 'as' ? 'Save as' : 'Save task'}</button></div>}
      {asking && !askFrequency && <div className="row">
        <label title="Lowercase letters, digits and _.">New task name <input value={newName} onChange={e => setNewName(e.target.value)} /></label>
        <button className="primary" disabled={!NAME.test(newName) || newName === task || !!busy} onClick={() => save(true, newName)}>
          {busy === 'as' ? 'Saving...' : 'Save as'}</button>
        <button onClick={() => setAsking(false)}>Cancel</button></div>}
      {message && <p className={message.level === 'ok' ? 'ok' : message.level === 'warn' ? 'warn' : 'error'}>{message.text}</p>}
      {file && <TaskFileWindow text={file.text} title={file.title} onApply={applyFile} onClose={() => setFile(null)} />}
    </div>);
}
