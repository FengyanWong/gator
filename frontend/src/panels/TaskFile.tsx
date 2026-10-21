import { useAsyncAction } from '../store';
import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json, problemText } from '../api';

/** The task file's `_help` part as [part, what it is] pairs, and the file's text without it (branch record SIF-81: in the
 *  wrapping box its long lines ran back under the opening "{", so one part's text could not be told from the next). The
 *  backend writes the part first, with two-space indents (task_files.render), so it is cut out of the text and every number
 *  stays as written (1.0, 5e-06); a file of another shape is written out again without it, and text that is not JSON is
 *  kept whole. Apply reads the file without the part either way: the backend ignores it. */
function splitHelp(text: string): { help: [string, string][]; body: string } {
  let data: Json;
  try { data = JSON.parse(text); } catch { return { help: [], body: text }; }
  if (!data || typeof data !== 'object' || Array.isArray(data) || !data._help || typeof data._help !== 'object') return { help: [], body: text };
  const { _help, ...rest } = data;
  const help = Object.entries(_help).map(([part, says]): [string, string] => [part, typeof says === 'string' ? says : JSON.stringify(says)]);
  const lines = text.split('\n'), end = lines.indexOf('  },');
  if (lines[1] === '  "_help": {' && end > 1) {
    const body = [lines[0], ...lines.slice(end + 1)].join('\n');
    try { if (!('_help' in JSON.parse(body))) return { help, body }; } catch { /* written out again below */ }
  }
  return { help, body: JSON.stringify(rest, null, 2) + '\n' };
}

/** The task file in a window of its own: everything a task is, as one readable file (its own `_help` part explains each
 *  part, shown as a list over the text, `splitHelp`). The person - or someone pasting the agent's text - edits it here; "Apply to editors" checks it with the same
 *  schema as the editors and puts its rows into them. Nothing is saved or written to Virtuoso from here: that is "Save
 *  task". Opened by a press, closed with its own button or the window's. */
export function TaskFileWindow({ root, text, title, onApply, onClose }: {
  root: HTMLElement | null; text: string | null; title: string; onApply: (rows: Json, extras: Json) => void; onClose: () => void }) {
  // The window itself belongs to TaskSave, which opens it INSIDE the click on "Task file" (`popupWindow.ts`): opened here,
  // after the file had arrived, a slow answer came too late for the browser's pop-up rule and the window was blocked -
  // and a second press could not try again, because this component stayed mounted (review of 2026-09-29).
  const file = useMemo(() => splitHelp(text ?? ''), [text]);    // the box holds the file without its _help; Revert goes back to that
  const [draft, setDraft] = useState(file.body);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [message, setMessage] = useState<Json>(null);

  useEffect(() => { setDraft(file.body); setProblems(null); setMessage(null); }, [file]);

  const { busy, run } = useAsyncAction(e => setMessage({ level: 'error', text: problemText(e) }), () => setMessage(null));
  const apply = () => run('apply', async () => {
    const checked = await api.taskFileCheck(draft);
    setProblems(checked.problems);
    if (checked.ok) {
      onApply(checked.rows, checked.extras);
      setMessage({ level: 'ok', text: 'Applied: the editors now hold these rows. Press "Save as" to store them as a new task; Undo takes them back.' });
    }
  });

  if (!root) return null;
  if (text === null) return createPortal(<div className="task-file"><h3>{title}</h3><p className="hint">Reading the task file...</p></div>, root);
  return createPortal(
    <div className="task-file">
      <h3>{title}</h3>
      <p className="hint">Change it here or in the editors. <b>Apply to editors</b> checks it and fills the editors; nothing is saved until you press
        <b> Save as</b>.{file.help.length > 0 && <> <b>What each part is</b>, below, says what each part holds.</>}</p>
      {file.help.length > 0 && <details className="task-file-help" open><summary>What each part is</summary>
        <dl>{file.help.map(([part, says]) => <div key={part}><dt>{part}</dt><dd>{says}</dd></div>)}</dl></details>}
      <textarea spellCheck={false} value={draft} onChange={e => { setDraft(e.target.value); setProblems(null); setMessage(null); }} />
      <div className="row">
        <button className="primary" disabled={!!busy} onClick={apply}>{busy ? 'Checking...' : 'Apply to editors'}</button>
        <button disabled={!!busy || draft === file.body} onClick={() => { setDraft(file.body); setProblems(null); setMessage(null); }}
          title="Back to the file as it was opened: the editors' rows at that moment.">Revert</button>
        <button onClick={onClose}>Close</button>
      </div>
      {problems && problems.length > 0 && <div className="blocker"><b>Not applied: {problems.length} problem{problems.length === 1 ? '' : 's'} in the file.</b>
        <ul className="steps-list">{problems.map(p => <li key={p}>{p}</li>)}</ul></div>}
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>, root);
}
