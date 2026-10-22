import { useAsyncAction } from '../store';
import { Dispatch, SetStateAction, useEffect, useMemo, useState } from 'react';
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

/** What is typed in the task file's window (branch record SIF-87). TaskSave keeps it, not the window: kept there, a close -
 *  the window's Close, its X, the banner's Close all - threw the typing away with no question, and hand edits to a long
 *  file were lost for good. `body`: the file it was typed over; `applied`: the text last applied to the editors; `kept`:
 *  brought back from a window closed before, which the window says until it is applied or reverted. */
export type FileDraft = { text: string; body: string; applied: string | null; kept: boolean };
/** A draft worth keeping when its window closes: typed, and not what was applied. */
export const unapplied = (draft: FileDraft | null): draft is FileDraft => !!draft && draft.text !== draft.body && draft.text !== draft.applied;

/** The parts beside the rows that Apply hands on for the next save (task_files.parse's extras), by the words the page
 *  uses for them. */
const OTHER_PARTS: [string, (data: Json) => unknown][] = [
  ['Maestro analyses', d => d.maestro?.analyses], ['Maestro variables', d => d.maestro?.variables],
  ['initial conditions', d => d.maestro?.initial_conditions], ['bindings', d => d.maestro?.bindings],
  ['model files', d => d.maestro?.model_files], ['rough frequency', d => d.measurement?.expected_frequency_hz], ['notes', d => d.notes]];
/** Keys in one order, so that a part only written in another order is not a change. */
const canonical = (value: unknown) => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))) : v);
/** Which of those parts differ between two task files (branch record SIF-93): what an Apply holds for the next save that
 *  the file read first did not already say. None for a text that is not a JSON object. */
export function otherPartsChanged(before: string, after: string): string[] {
  let a: Json, b: Json;
  try { a = JSON.parse(before); b = JSON.parse(after); } catch { return []; }
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return [];
  return OTHER_PARTS.filter(([, part]) => canonical(part(a)) !== canonical(part(b))).map(([name]) => name);
}

/** The task file in a window of its own: everything a task is, as one readable file (its own `_help` part explains each
 *  part, shown as a list over the text, `splitHelp`). The person - or someone pasting the agent's text - edits it here; "Apply to editors" checks it with the same
 *  schema as the editors and puts its rows into them. Nothing is saved or written to Virtuoso from here: that is "Save
 *  task". Opened by a press, closed with its own button or the window's; `draft` (null: nothing typed) outlives it.
 *  The file holds the editors' rows of the moment it was read (branch record SIF-93): `editorsChanged` says they changed
 *  since, which an Apply would replace; `onReread` reads the file of the editors as they are now. */
export function TaskFileWindow({ root, text, title, draft, setDraft, editorsChanged, onReread, onApply, onClose }: {
  root: HTMLElement | null; text: string | null; title: string; draft: FileDraft | null; setDraft: Dispatch<SetStateAction<FileDraft | null>>;
  editorsChanged: boolean; onReread: () => Promise<void>; onApply: (rows: Json, extras: Json, text: string) => void; onClose: () => void }) {
  // The window itself belongs to TaskSave, which opens it INSIDE the click on "Task file" (`popupWindow.ts`): opened here,
  // after the file had arrived, a slow answer came too late for the browser's pop-up rule and the window was blocked -
  // and a second press could not try again, because this component stayed mounted (review of 2026-09-29).
  const file = useMemo(() => splitHelp(text ?? ''), [text]);    // the box holds the file without its _help; Revert goes back to that
  // A draft kept from a closed window lies over the file as read now: Revert goes back to the editors' rows of this opening.
  const typed = draft?.text ?? file.body;
  const keptShown = !!draft?.kept && typed !== file.body && typed !== draft.applied;
  const [problems, setProblems] = useState<string[] | null>(null);
  const [message, setMessage] = useState<Json>(null);
  // While the editors changed since the file was read, Apply takes two presses: the first only turns it into "Apply anyway".
  const [anyway, setAnyway] = useState(false);

  useEffect(() => { setProblems(null); setMessage(null); }, [file]);
  useEffect(() => { if (!editorsChanged) setAnyway(false); }, [editorsChanged]);

  const { busy, run } = useAsyncAction(e => setMessage({ level: 'error', text: problemText(e) }), () => setMessage(null));
  const apply = () => {
    if (editorsChanged && !anyway) { setAnyway(true); return; }
    run('apply', async () => {
      const sent = typed;
      const checked = await api.taskFileCheck(sent);
      setProblems(checked.problems);
      if (checked.ok) {
        onApply(checked.rows, checked.extras, sent);
        setDraft(d => d && { ...d, applied: sent, kept: false });
        // Its other parts wait in the page for the next save, and Undo does not take them back (branch record SIF-93: "the
        // editors now hold these rows" read as if all of the file were in the editors).
        setMessage({ level: 'ok', text: 'Applied: the editors now hold its rows, and Save as will send its other parts. Undo takes back the rows only.' });
      }
    });
  };
  // Read again from the editors (branch record SIF-93): the file is replaced, so a draft not applied is asked about first,
  // in this window, where the person is looking.
  const reread = () => {
    const owner = root?.ownerDocument.defaultView ?? window;
    if (unapplied(draft) && !owner.confirm('Read again from the editors? Your changes to this file are dropped.')) return;
    run('read', onReread);
  };

  if (!root) return null;
  if (text === null) return createPortal(<div className="task-file"><h3>{title}</h3><p className="hint">Reading the task file...</p></div>, root);
  return createPortal(
    <div className="task-file">
      <h3>{title}</h3>
      <p className="hint">Change it here or in the editors. <b>Apply to editors</b> checks it and fills the editors; nothing is saved until you press
        <b> Save as</b>.{file.help.length > 0 && <> <b>What each part is</b>, below, says what each part holds.</>}</p>
      {file.help.length > 0 && <details className="task-file-help" open><summary>What each part is</summary>
        <dl>{file.help.map(([part, says]) => <div key={part}><dt>{part}</dt><dd>{says}</dd></div>)}</dl></details>}
      {keptShown && <p className="hint kept-draft">Your changes from before are kept, not applied yet. Revert drops them.</p>}
      {editorsChanged && <p className="warn editors-changed">The editors changed since this file was read: Apply replaces those changes too
        (Undo in the editors takes it back). <button disabled={!!busy} onClick={reread}
          title="Read again from the editors: The file of the editors as they are now. Asks first when changes typed here are not applied.">
          {busy === 'read' ? 'Reading...' : 'Read again from the editors'}</button></p>}
      <textarea spellCheck={false} value={typed} onChange={e => { const value = e.target.value; setProblems(null); setMessage(null);
        setDraft(d => ({ text: value, body: file.body, applied: d?.applied ?? null, kept: d?.kept ?? false })); }} />
      <div className="row">
        <button className="primary" disabled={!!busy} onClick={apply} title={anyway ? 'Apply anyway: Replaces the rows of the editors, the changes made there since this file was read included. Undo in the editors takes it back.' : undefined}>
          {busy === 'apply' ? 'Checking...' : anyway ? 'Apply anyway' : 'Apply to editors'}</button>
        <button disabled={!!busy || typed === file.body} onClick={() => { setDraft(null); setProblems(null); setMessage(null); }}
          title="Back to the file as it was opened: the editors' rows at that moment.">Revert</button>
        <button onClick={onClose}>Close</button>
      </div>
      {problems && problems.length > 0 && <div className="blocker"><b>Not applied: {problems.length} problem{problems.length === 1 ? '' : 's'} in the file.</b>
        <ul className="steps-list">{problems.map(p => <li key={p}>{p}</li>)}</ul></div>}
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>, root);
}
