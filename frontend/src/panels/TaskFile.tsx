import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json } from '../api';

/** The task file in a window of its own: everything a task is, as one readable file (its own `_help` part explains each
 *  part). The person - or someone pasting the agent's text - edits it here; "Apply to editors" checks it with the same
 *  schema as the editors and puts its rows into them. Nothing is saved or written to Virtuoso from here: that is "Save
 *  task". Opened by a press, closed with its own button or the window's. */
export function TaskFileWindow({ text, title, onApply, onClose }: {
  text: string; title: string; onApply: (rows: Json, extras: Json) => void; onClose: () => void }) {
  const [popup, setPopup] = useState<Window | null>(null);
  const [root, setRoot] = useState<HTMLElement | null>(null);
  const [draft, setDraft] = useState(text);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [message, setMessage] = useState<Json>(null);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState<string | null>(null);

  useEffect(() => { setDraft(text); setProblems(null); setMessage(null); }, [text]);
  useEffect(() => {
    const opened = window.open('', 'gator-task-file', 'popup,width=760,height=900');
    if (!opened) { setBlocked('The browser blocked the new window. Allow pop-ups for this page, then press "Task file" again.'); return; }
    const doc = opened.document;
    doc.title = `GATOR - ${title}`;
    doc.head.querySelectorAll('link, style').forEach(node => node.remove());          // a window of that name may be reused
    document.querySelectorAll<HTMLElement>('link[rel="stylesheet"], style').forEach(node => {
      const copy = node.cloneNode(true) as HTMLElement;
      if (node instanceof HTMLLinkElement) (copy as HTMLLinkElement).href = node.href;   // absolute: the new window is about:blank
      doc.head.appendChild(copy);
    });
    doc.body.innerHTML = '<div id="task-file-root" class="task-file-window"></div>';
    setPopup(opened); setRoot(doc.getElementById('task-file-root'));
    const closed = () => onClose();
    const leave = () => opened.close();
    opened.addEventListener('pagehide', closed);
    window.addEventListener('pagehide', leave);
    return () => { opened.removeEventListener('pagehide', closed); window.removeEventListener('pagehide', leave); opened.close(); };
  }, []);

  const apply = async () => {
    setBusy(true); setMessage(null);
    try {
      const checked = await api.taskFileCheck(draft);
      setProblems(checked.problems);
      if (checked.ok) {
        onApply(checked.rows, checked.extras);
        setMessage({ level: 'ok', text: 'Applied: the editors now hold these rows. Press "Save task" to store them; Undo takes them back.' });
      }
    } catch (e: any) {
      setMessage({ level: 'error', text: e.status === 404 || e.status === 405 ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).' : e.message });
    } finally { setBusy(false); }
  };

  if (blocked) return <p className="error">{blocked}</p>;
  if (!popup || !root) return null;
  return createPortal(
    <div className="task-file">
      <h3>{title}</h3>
      <p className="hint">Change it here or in the editors. <b>Apply to editors</b> checks it and fills the editors; nothing is saved until you press
        <b> Save task</b>. The <code>_help</code> part says what each part is.</p>
      <textarea spellCheck={false} value={draft} onChange={e => { setDraft(e.target.value); setProblems(null); setMessage(null); }} />
      <div className="row">
        <button className="primary" disabled={busy} onClick={apply}>{busy ? 'Checking...' : 'Apply to editors'}</button>
        <button disabled={busy || draft === text} onClick={() => { setDraft(text); setProblems(null); setMessage(null); }}
          title="Back to the file as it was opened: the editors' rows at that moment.">Revert</button>
        <button onClick={onClose}>Close</button>
      </div>
      {problems && problems.length > 0 && <div className="blocker"><b>Not applied: {problems.length} problem{problems.length === 1 ? '' : 's'} in the file.</b>
        <ul className="steps-list">{problems.map(p => <li key={p}>{p}</li>)}</ul></div>}
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>, root);
}
