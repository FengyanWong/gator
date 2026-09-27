import { useAsyncAction } from '../store';
import { Icon } from './Icons';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json, problemText, virtuosoGateText } from '../api';
import { TaskFileWindow } from './TaskFile';

/** "Save task" - a person's press only - and the task file. `task` = the open task (Save task updates it); without one,
 *  the first save of the cell read from Virtuoso (the cell the user declared as their copy is then the task's). The
 *  extras - what the task file holds beside the rows (analyses, variables, bindings, the ring oscillator's rough
 *  frequency, notes) - live here until the save. "Save as" went on 2026-09-23 with the copies the workbench made:
 *  another task is another copy the user makes in Virtuoso, read in the Virtuoso window and saved from there (the backend
 *  still answers `as_new` for the API).
 *  Shown at the right end of the editors' tab line (`bar`), its messages and questions under their toolbar (`notes`) -
 *  user request 2026-09-22: the save sits with the rows it stores. The component stays in the circuit panel, which owns
 *  the cell and the task; two portals put it there. */

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

export function TaskSave({ profileId, library, cell, task, revision, hasCopy, config, setConfig, onSaved, bar, notes }: {
  profileId: string | null; library: string | null; cell: string | null; task: string | null; revision?: number | null;
  hasCopy: boolean; config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; onSaved: (made: Json) => void;
  bar: HTMLElement | null; notes: HTMLElement | null }) {
  const [name, setName] = useState('');
  const [message, setMessage] = useState<Json>(null);
  const [extras, setExtras] = useState<Json>({});
  const [askFrequency, setAskFrequency] = useState(false);                    // the save asked for the ring oscillator's rough frequency
  const [frequency, setFrequency] = useState('');
  const [file, setFile] = useState<Json>(null);                               // { text, title } while the window is open
  useEffect(() => { setExtras({}); setMessage(null); setAskFrequency(false); }, [task, library, cell]);
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

  const suggested = suggestTaskName(cell);
  const taskName = task ?? (name || suggested);
  const report = (e: any) => {
    setMessage({ level: 'error', text: problemText(e, virtuosoGateText) });
  };
  const { busy, run } = useAsyncAction(e => {
    if (e.detail?.code === 'needs_expected_frequency') { setAskFrequency(true); setMessage({ level: 'warn', text: e.detail.message }); }
    else report(e);
  }, () => setMessage(null));
  const save = (more: Json = {}) => run('save', async () => {
    const sent = { ...extras, ...more };
    const made = await api.taskSave({ profile_id: profileId, name: taskName, config, library, cell, task, as_new: false, extras: sent });
    setExtras(sent); setAskFrequency(false);
    const kept = made.created ? '' : made.baseline_kept ? ' The recorded baseline still holds.' : made.changed?.length ? ' The recorded baseline no longer holds (what is measured changed): run a new baseline.' : '';
    setMessage({ level: 'ok', text: `${made.created ? `Saved the new task ${made.task_key}.` : `Saved ${made.task_key}, revision ${made.revision}.`}${made.runnable ? '' : ' It can be opened and edited; running Maestro-measured tasks comes with the next part.'}${kept}` });
    onSaved(made);
  });
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
  const said = askFrequency || message;
  return (<>
    {bar && createPortal(
      <div className="task-save">
        {!task && <label title="Lowercase letters, digits and _. It becomes the task real:<name>.">New task name
          <input value={name} placeholder={suggested} onChange={e => setName(e.target.value)} /></label>}
        {task && <span className="hint">Task <code>real:{task}</code>{revision ? `, revision ${revision}` : ''}</span>}
        <button className="primary" disabled={!canSave} onClick={() => save()}
          title={'Save task: ' + (task ? 'Stores the rows of Parameters, Probes and Specs as this task (its next revision). ' : hasCopy
            ? 'Stores the rows of Parameters, Probes and Specs as a new task of this cell. '
            : 'Read the cell in the Virtuoso window first and confirm that it is a copy you made: the task is saved into that cell. ')
            + 'It writes the cell in Virtuoso to match and reads it back; no simulation. Only you can press it.'}>
          <Icon name="task" label={busy === 'save' ? 'Saving...' : 'Save task'} /></button>
        <button disabled={!!busy} onClick={openFile} title="Task file: The task as one readable file, in a window of its own: open it, change it, apply it to the editors."><Icon name="task-file" label="Task file" /></button>
      </div>, bar)}
    {notes && said && createPortal(
      <div className="task-save-notes">
        {askFrequency && <div className="row">
          <label title="Rough is enough: it only sizes the transient (60 periods, measured after 20).">Rough oscillation frequency
            <input value={frequency} placeholder="e.g. 1.2G" onChange={e => setFrequency(e.target.value)} /></label>
          <button className="primary" disabled={!(frequencyValue > 0) || !!busy} onClick={() => save({ expected_frequency_hz: frequencyValue })} title="Save task: With this frequency."><Icon name="task" label="Save task" /></button></div>}
        {message && <p className={message.level === 'ok' ? 'ok' : message.level === 'warn' ? 'warn' : 'error'}>{message.text}</p>}
      </div>, notes)}
    {file && <TaskFileWindow text={file.text} title={file.title} onApply={applyFile} onClose={() => setFile(null)} />}
  </>);
}
