import { useAsyncAction } from '../store';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json, problemText } from '../api';

/** The task file in a window of its own: everything a task is, as one readable file (its own `_help` part explains each
 *  part). The person - or someone pasting the agent's text - edits it here; "Apply to editors" checks it with the same
 *  schema as the editors and puts its rows into them. Nothing is saved or written to Virtuoso from here: that is "Save
 *  task". Opened by a press, closed with its own button or the window's. */
export function TaskFileWindow({ root, text, title, onApply, onClose }: {
  root: HTMLElement | null; text: string | null; title: string; onApply: (rows: Json, extras: Json) => void; onClose: () => void }) {
  // The window itself belongs to TaskSave, which opens it INSIDE the click on "Task file" (`popupWindow.ts`): opened here,
  // after the file had arrived, a slow answer came too late for the browser's pop-up rule and the window was blocked -
  // and a second press could not try again, because this component stayed mounted (review of 2026-09-29).
  const [draft, setDraft] = useState(text ?? '');
  const [problems, setProblems] = useState<string[] | null>(null);
  const [message, setMessage] = useState<Json>(null);

  useEffect(() => { setDraft(text ?? ''); setProblems(null); setMessage(null); }, [text]);

  const { busy, run } = useAsyncAction(e => setMessage({ level: 'error', text: problemText(e) }), () => setMessage(null));
  const apply = () => run('apply', async () => {
    const checked = await api.taskFileCheck(draft);
    setProblems(checked.problems);
    if (checked.ok) {
      onApply(checked.rows, checked.extras);
      setMessage({ level: 'ok', text: 'Applied: the editors now hold these rows. Press "Save task" to store them; Undo takes them back.' });
    }
  });

  if (!root) return null;
  if (text === null) return createPortal(<div className="task-file"><h3>{title}</h3><p className="hint">Reading the task file...</p></div>, root);
  return createPortal(
    <div className="task-file">
      <h3>{title}</h3>
      <p className="hint">Change it here or in the editors. <b>Apply to editors</b> checks it and fills the editors; nothing is saved until you press
        <b> Save task</b>. The <code>_help</code> part says what each part is.</p>
      <textarea spellCheck={false} value={draft} onChange={e => { setDraft(e.target.value); setProblems(null); setMessage(null); }} />
      <div className="row">
        <button className="primary" disabled={!!busy} onClick={apply}>{busy ? 'Checking...' : 'Apply to editors'}</button>
        <button disabled={!!busy || draft === text} onClick={() => { setDraft(text); setProblems(null); setMessage(null); }}
          title="Back to the file as it was opened: the editors' rows at that moment.">Revert</button>
        <button onClick={onClose}>Close</button>
      </div>
      {problems && problems.length > 0 && <div className="blocker"><b>Not applied: {problems.length} problem{problems.length === 1 ? '' : 's'} in the file.</b>
        <ul className="steps-list">{problems.map(p => <li key={p}>{p}</li>)}</ul></div>}
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>, root);
}
