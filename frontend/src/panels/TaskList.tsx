// The task name button and the Tasks window it opens (record 7.227; on the editors' tab line since record 7.362): every
// registered task, with folders and Details, and the task the page follows.
import { Fragment, MouseEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { TASKS_WINDOW } from '../contract';
import { api, Json } from '../api';
import { si } from '../units';
import { clock, plural, stamp } from '../format';
import { FolderMoveBar, Folders, useFolders } from './Folders';
import { TableHead, useTableView } from './TableView';
import { Icon } from './Icons';
import { OPEN_TASKS, openRunsAt, TasksAt } from '../openAt';

/** Which registered task the page follows (user request 2026-10-06, record 7.227: "make the loaded task a button similar to
 *  the runs... button style. It opens a new window showing all the tasks"): the task name is the button that opens its
 *  window - at the start of the editors' tab line since record 7.362 (in the Project column until then). It replaced the drop-down list of tasks, as "Runs..." replaced the list of
 *  runs (RunList.tsx). Pressing it opens the task window - a browser window of its own, drawn through a portal like the
 *  run window - with every registered task as a table: what it is, which cell it runs in, its saved revision and baseline,
 *  how many sizes and results it has, and its newest run. A double click on a row makes the page follow that task (exactly
 *  what choosing it in the old list did: its rows come into the editors, edits are asked about first) - so do Enter on the
 *  row and "Follow this task" in its Details (branch record SIF-100); "Details" adds the rest, the task's rows included.
 *  Once the page follows the chosen task the window closes (user request 2026-10-09: "after selecting one target task,
 *  model or run, close the pop up window"); Cancel at the edits question, or a task that cannot be read, leaves it open.
 *
 *  Nothing here updates on a timer: the task list is read when the button is pressed - also while the window is open
 *  (branch record SIF-100: that press only brought it to the front, though its tooltip said it read again) - and by
 *  "Refresh list" (which reads the run list again too; otherwise the run columns show the page's own run list, read when
 *  the page opened and after every task choice, record 7.212); a task's rows when its details are opened. The window
 *  prints when it last read. */

/** Display only: saved task keys keep their namespace for selection and run/model links. */
const taskName = (key: string) => key.replace(/^real:/, '');
/** The name in a task's key: what its files, its cell and its runs carry. */
const ownName = (key: string) => key.replace(/^[^:]+:/, '');
/** The name a task is shown under (record 7.302): the one it was renamed to, else its own. A rename never changes the
 *  key - the task window's Details hold the Name box. A server older than the rename lists no `name`. */
export const shownName = (t: Json | null | undefined, key = t?.task_key ?? '') => typeof t?.name === 'string' && t.name !== ownName(key) ? t.name : taskName(key);
const renamed = (t: Json) => typeof t.name === 'string' && t.name !== ownName(t.task_key);
/** The mark the old list put after a task's name: what keeps it from running right now. `withReason`: the Tasks list's, where a
 *  blocked task says why (states audit of 2026-10-24, branch record SIF-139): with a connection problem every saved task read a
 *  bare "[blocked]", its reason only in Details. The tab line's chip, one line of 420 px at most, keeps "[blocked]" with the
 *  reason on hover; for a task that cannot be loaded the "Blocked:" line under the editors' toolbar says why as well (review of
 *  SIF-139: a Maestro task saved before such tasks could run loads all the same and has no such line, its reason being among
 *  the circuit's notes). */
export const taskMark = (t: Json, ngspiceOffered: boolean, withReason = false) => t.kind === 'mock' ? '[MOCK]'
  : t.kind === 'ngspice' ? (t.available && ngspiceOffered ? '[ngspice]' : '[ngspice: choose its connection]')
  : t.available ? '' : withReason && t.blocker ? `[blocked: ${t.blocker}]` : '[blocked]';
const cellOf = (t: Json) => t.library && t.cell ? `${t.library}/${t.cell}` : t.kind === 'ngspice' ? 'ngspice netlist' : t.kind === 'mock' ? 'built-in netlist' : '-';
/** The runs of one task: how many, and the newest by its start (a Baseline simulation is one of them). */
function runsOf(runs: Json[], key: string) {
  const mine = runs.filter(r => r.task_key === key).sort((a, b) => String(b.created_utc ?? '').localeCompare(String(a.created_utc ?? '')));
  return { count: mine.length, newest: mine[0] ?? null };
}
/** A time in the list to the minute (branch record SIF-24): its columns are narrower and wrap less. Details show Created, Saved and Baseline recorded to the second. */
const minute = (utc?: string | null) => stamp(utc)?.slice(0, 16) ?? null;
/** A cell or testbench name may break after a "_" (SIF-24), so one long generated name does not widen the Cell column for every row.
 *  It sits in a .name-part box: the name first moves under the library ("library/") as a whole and breaks inside only when longer than the column. */
const namePart = (text: string) => <span className="name-part">{text.split(/(?<=_)/).map((part, i) => <Fragment key={i}>{i > 0 && <wbr />}{part}</Fragment>)}</span>;
const cellName = (text: string) => { const at = text.indexOf('/'); return at < 0 ? text : <>{text.slice(0, at + 1)}{namePart(text.slice(at + 1))}</>; };
/** "2026-10-09 22:35": in a narrow window the time goes under the date; the date never breaks at its hyphens. */
const dateTime = (utc?: string | null) => { const text = minute(utc); if (!text) return null; const [day, time] = text.split(' '); return <><span className="task-date">{day}</span> {time}</>; };
/** "first feasible at evaluation 34" (branch record SIF-68): a bare "at 34" after a clock time read like a time. Its
 *  evaluations as the page writes a count (branch record SIF-117). */
const newestText = (r: Json | null) => !r ? 'none' : `${minute(r.created_utc) ?? '?'} · ${r.state ?? 'not started'} · ${plural(r.evaluations ?? 0, 'evaluation')}`
  + (r.first_feasible_eval_count != null ? ` · first feasible at evaluation ${r.first_feasible_eval_count}` : r.evaluations ? ' · none feasible' : '');

type Column = { key: string; title: string; help: string; numeric?: boolean; value: (t: Json, runs: Json[]) => string | number | null };
const COLUMNS: Column[] = [
  { key: 'task', title: 'Task', help: 'The name the task is shown under. A renamed task says its internal name below it: the name its files, its cell and its runs keep (Details holds the Name box). A mark says what keeps it from running now (the whole reason on hover); synthetic tasks carry a MOCK badge.', value: t => shownName(t) },
  { key: 'class', title: 'Class', help: 'The circuit class label the task carries (opamp, ldo, oscillator, ...).', value: t => t.circuit_class ?? '' },
  { key: 'cell', title: 'Cell', help: 'The Virtuoso library and cell the task runs in (the copy you declared), with its testbench cell.', value: t => cellOf(t) },
  { key: 'revision', numeric: true, title: 'Rev', help: 'The saved revision of the task. Save as creates a new task at revision 1.', value: t => t.revision ?? null },
  { key: 'saved', title: 'Saved', help: 'When the task was last saved (local time of this computer).', value: t => t.saved_utc ?? null },
  { key: 'baseline', title: 'Baseline', help: 'When the task\'s reference was recorded (a finished Baseline simulation records it by itself); none = no real baseline yet.', value: t => t.baseline_recorded_utc ?? null },
  { key: 'rows', numeric: true, title: 'Sizes / results', help: 'How many sizes the task varies and how many results its testbench measures.', value: t => t.variables != null ? `${t.variables} / ${t.results ?? 0}` : null },
  { key: 'newest', title: 'Newest run', help: 'The task\'s newest run under the output folder: started, state, evaluations, first feasible. The bottom tabs show it when the task is chosen (record 7.212).', value: (t, runs) => runsOf(runs, t.task_key).newest?.created_utc ?? null },
  { key: 'runs', numeric: true, title: 'Runs', help: 'How many runs of the task the output folder holds, Baseline simulations included.', value: (t, runs) => runsOf(runs, t.task_key).count },
];

/** Everything else about one task, and its rows (read from the starter route when the details open). `onFollow`: what a
 *  double click on its row does; offered while the page follows another task (branch record SIF-100). */
function TaskDetails({ task, runs, rows, error, followed, deleting, onFollow, onRenamed }: { task: Json; runs: Json[]; rows: Json; error?: string; followed: boolean;
  deleting: boolean; onFollow: () => void; onRenamed: (name: string) => void }) {
  const of = runsOf(runs, task.task_key);
  // Rename (record 7.302; user: "add rename functionality to tasks"): the name the task is SHOWN under. Its key, its
  // files, its cell and every run and model that names it stay as they are; typing its own name takes a rename back.
  const [name, setName] = useState(shownName(task));
  const [renaming, setRenaming] = useState(false);
  const [renameNote, setRenameNote] = useState<{ level: 'hint' | 'warn'; text: string } | null>(null);
  useEffect(() => setName(shownName(task)), [task.task_key, task.name]);
  const typed = name.trim();
  const canRename = !renaming && !!typed && typed !== shownName(task) && 'name' in task;
  // The task the page follows takes the new run label at once (branch record SIF-100, `onRenamed`): the note sent the user to
  // a double click on its row, which asked to discard their edits.
  const rename = () => {
    if (!canRename) return;
    setRenaming(true); setRenameNote(null);
    api.renameTask(task.task_key, typed).then(r => { setRenameNote({ level: 'hint', text: `Renamed to "${r.name}". New runs of the task are filed under this name.` }); onRenamed(r.name); })
      .catch(e => setRenameNote({ level: 'warn', text: e.message })).finally(() => setRenaming(false));
  };
  const facts: [string, string | null | undefined][] = [
    ['Registered task', shownName(task)], ['Internal name', renamed(task) ? `${taskName(task.task_key)} - its files, its cell and its runs keep this name` : null],
    ['Blocked by', task.blocker], ['What it is', task.description],
    ['Title', task.title ?? rows?.project?.notes], ['Circuit class · PDK', `${task.circuit_class ?? 'unspecified'} · ${task.pdk_id ?? 'unspecified'}`],
    ['Runs in', task.library && task.cell ? `${task.library}/${task.cell}${task.testbench ? ` with testbench ${task.testbench}` : ''}` : null],
    ['Saved from', task.original?.cell ? `${task.original.library}/${task.original.cell}${task.original.testbench ? ` (testbench ${task.original.testbench})` : ''}` : null],
    ['Netlist of record', task.original?.netlist_sha256 ? `sha256 ${String(task.original.netlist_sha256).slice(0, 16)}...` : null],
    ['Measured by', task.measurement === 'maestro' ? 'Maestro outputs (OCEAN on each run\'s results)' : task.measurement ?? (task.simulator ?? null)],
    ['Revision', task.revision != null ? String(task.revision) : null], ['Created', stamp(task.created_utc)], ['Saved', stamp(task.saved_utc)],
    ['Baseline recorded', task.baseline_recorded_utc ? stamp(task.baseline_recorded_utc) : task.kind === 'real' && task.generated ? 'none yet' : null], ['State', task.status],
    ['Sizes varied', task.variables != null ? String(task.variables) : null], ['Results measured', task.results != null ? String(task.results) : null],
    ['Run label', task.starter_project?.task_name], ['Runs', `${of.count}${of.newest ? `; newest ${newestText(of.newest)}` : ''}`],
  ];
  const unit = (v: unknown, u?: string | null) => v == null || v === '' ? '' : si(v, u);
  const searched = (rows?.parameters ?? []).filter((p: Json) => !p.binding_group), following = (rows?.parameters ?? []).filter((p: Json) => p.binding_group);
  const limits = (s: Json) => s.constraint === 'interval' ? `${unit(s.lower, s.unit)} to ${unit(s.upper, s.unit)}`
    : s.constraint === '>=' ? `>= ${unit(s.lower, s.unit)}` : s.constraint === '<=' ? `<= ${unit(s.upper, s.unit)}` : `${s.constraint ?? ''} ${unit(s.lower ?? s.upper, s.unit)}`.trim();
  return (<div className="run-details task-details">
    <div className="row model-rename-row task-rename-row">
      {!followed && <button className="task-follow" disabled={deleting} onClick={onFollow}
        title="Follow this task (also a double click on its row, or Enter on it): its rows come into the editors (edits are asked about first) and the bottom tabs show its newest run; the window then closes. Nothing starts.">Follow this task</button>}
      <label title="The name this task is shown under: a lower-case letter first, then lower-case letters, digits and underscores (2-40 characters). Only the shown name changes: the task's files, its Virtuoso cell and the runs and models made on it keep the internal name. A name another task has is refused. Type the internal name to take a rename back.">Name
        <input className="model-rename task-rename" value={name} maxLength={40} disabled={renaming || !('name' in task)} onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); rename(); } }} /></label>
      <button className="model-rename-apply task-rename-apply" disabled={!canRename} onClick={rename}
        title={'name' in task ? 'Show this task under the name in the box.' : 'The workbench server that is running is older than this page and cannot rename a task: restart it.'}>{renaming ? 'Renaming...' : 'Rename'}</button></div>
    {renameNote && <p className={`${renameNote.level === 'warn' ? 'warn' : 'hint'} model-rename-note task-rename-note`}>{renameNote.text}</p>}
    {error && <p className="error">The task's rows could not be read: {error}</p>}
    {!rows && !error && <p className="hint">Reading the task's rows...</p>}
    <table className="grid small run-facts"><tbody>
      {facts.filter(([, value]) => value != null && value !== '').map(([name, value]) => <tr key={name}><td>{name}</td><td className={name === 'Blocked by' ? 'error' : ''}>{value}</td></tr>)}
    </tbody></table>
    {rows && <>
      <h4>Parameters <span className="hint">- the sizes the task varies ({(rows.parameters ?? []).filter((p: Json) => !p.binding_group).length} searched, {(rows.parameters ?? []).length} rows)</span></h4>
      {/* The searched rows, each with the rows tied to it; the tied rows themselves folded (branch record SIF-40: the VCO's 7
          searched sizes stood among 59 rows that only follow them). */}
      <table className="grid small task-rows-table"><thead><tr><th>ID</th><th>Instance</th><th>Parameter</th><th>Range</th><th>Rows tied to it</th></tr></thead>
        <tbody>{searched.map((p: Json) => { const tied = following.filter((f: Json) => f.binding_group === p.variable_id); return <tr key={p.variable_id}>
          <td>{p.variable_id}</td><td>{p.instance_path}</td><td>{p.parameter_name}</td><td>{`${unit(p.lower, p.unit)} to ${unit(p.upper, p.unit)}`}</td>
          <td title={tied.map((f: Json) => `${f.variable_id} (${f.instance_path})`).join('\n') || undefined}>{tied.length
            ? `${tied.length}: ${tied.slice(0, 4).map((f: Json) => f.instance_path).join(', ')}${tied.length > 4 ? ', ...' : ''}` : ''}</td></tr>; })}</tbody></table>
      {following.length > 0 && <details className="more task-followers"><summary>{following.length} more row{following.length === 1 ? '' : 's'} follow{following.length === 1 ? 's' : ''} a searched one</summary>
        <table className="grid small task-rows-table"><thead><tr><th>ID</th><th>Instance</th><th>Parameter</th><th>Follows</th></tr></thead>
          <tbody>{following.map((p: Json) => <tr key={p.variable_id}><td>{p.variable_id}</td><td>{p.instance_path}</td><td>{p.parameter_name}</td><td>{p.binding_group}</td></tr>)}</tbody></table></details>}
      <h4>Probes <span className="hint">- the results it measures</span></h4>
      <table className="grid small task-rows-table"><thead><tr><th>ID</th><th>Result</th><th>Analysis</th><th>Unit</th></tr></thead>
        <tbody>{(rows.measurements ?? []).map((m: Json) => <tr key={m.measurement_id}><td>{m.measurement_id}</td><td>{m.source_name ?? ''}</td><td>{m.analysis ?? ''}</td><td>{m.unit ?? ''}</td></tr>)}</tbody></table>
      <h4>Specs <span className="hint">- the targets</span></h4>
      <table className="grid small task-rows-table"><thead><tr><th>Spec</th><th>Limit</th><th>Equation</th><th>Objective</th></tr></thead>
        <tbody>{(rows.targets ?? []).map((s: Json) => <tr key={s.metric_id}><td>{s.metric_id}</td><td>{limits(s)}</td><td>{s.equation ?? ''}</td>
          <td>{s.direction_after_feasible && s.direction_after_feasible !== 'none' ? s.direction_after_feasible : ''}</td></tr>)}</tbody></table>
    </>}
  </div>);
}

export function TaskListButton({ tasks, runs, current, currentText, currentMark, currentMarkTitle, ngspiceOffered, loading, onChoose, onRefresh, onRefreshRuns,
  onRenamed, onDelete, deleting, deleteDisabled, deleteTitle, deleteNotice, newTask }: { tasks: Json[]; runs: Json[];
  current: string | null; currentText: string; currentMark?: string; ngspiceOffered: boolean; loading: string | null;
  /** The tooltip of the chip's mark: what keeps the task from running, whole (branch record SIF-139). */
  currentMarkTitle?: string;
  /** `owner`: this window, which asks the edits question (branch record SIF-84). */
  onChoose: (taskKey: string, owner?: Window) => Promise<{ loaded: boolean }> | void;
  onRefresh: () => Promise<Json[]>; onRefreshRuns?: () => Promise<Json[]>;
  /** A task renamed in its Details, with the run label new runs of it now get (branch record SIF-100). */
  onRenamed?: (taskKey: string, runLabel: string) => void;
  onDelete?: (owner: Window) => void; deleting?: boolean; deleteDisabled?: boolean; deleteTitle?: string; deleteNotice?: ReactNode;
  /** The ways to a new task (record 7.362: they left the circuit column): drawn in this window, handed the window so that the
   *  windows they open are opened by the window holding the click (popupWindow.ts). */
  newTask?: (owner: Window) => ReactNode }) {
  // While `popup` is set, the task window is open (one pop-up window for the whole page: `popupWindow.ts`).
  const { popup, root, blocked, open: openPopup } = usePopupWindow('gator-tasks',
    { title: TASKS_WINDOW, features: 'popup,width=1500,height=760', rootId: 'tasks-root' });
  const [reading, setReading] = useState(false);
  const [readAt, setReadAt] = useState<string | null>(null);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const known = runs.some(r => 'task_key' in r);                  // an older workbench server lists runs without their task
  const table = useTableView('task', false);
  const { filter, setFilter, selected, setSelected } = table;
  const [open, setOpen] = useState<string | null>(null);          // the task whose details are shown
  const [rows, setRows] = useState<{ key: string; value?: Json; error?: string } | null>(null);
  const folders = useFolders('tasks');
  const chooseFolder = (id: string) => { folders.setFolder(id); setSelected([]); setOpen(null); };
  const nameOf = (key: string) => shownName(tasks.find(t => t.task_key === key), key);          // a task not listed: its own name

  const readRows = (key: string) => { setRows({ key }); api.starter(key).then(value => setRows(r => (r?.key === key ? { key, value } : r)), e => setRows(r => (r?.key === key ? { key, error: e.message } : r))); };
  // The tasks are read through the column (so it shows the same list); "Refresh list" reads the page's run list again too.
  const refresh = (alsoRuns: boolean) => {
    setReading(true);
    setSelected([]);
    void folders.refresh();
    const read = onRefresh();
    Promise.all([read.then(() => setTasksError(null), e => setTasksError(e.message)), alsoRuns && onRefreshRuns ? onRefreshRuns().catch(() => undefined) : null])
      .finally(() => { setReading(false); setReadAt(clock()); });
    if (open) readRows(open);
    return read;
  };
  // After a rename the list is read again; the run label is the one the list gives the task (`starter_project`), the label
  // choosing it again would bring (branch record SIF-100). The typed name when the list cannot be read.
  const renamedTask = (key: string, name: string) => refresh(false)
    .then(list => list.find(t => t.task_key === key)?.starter_project?.task_name ?? name, () => name)
    .then(label => onRenamed?.(key, label));
  useEffect(() => { if (popup) refresh(false); }, [popup]);       // pressing the button is the request to see the current task list
  // Another window's link (record 7.264, openAt.ts): this window opens AT a task - every folder, no filter, its Details open,
  // scrolled to. Following it changes nothing on the page: the task is not chosen.
  const [focus, setFocus] = useState<string | null>(null);
  const focusTask = (key: string) => { folders.setFolder('all'); setFilter(''); setSelected([]); setOpen(key); readRows(key); setFocus(key); };
  const latest = useRef({ openPopup, focusTask });
  latest.current = { openPopup, focusTask };
  useEffect(() => {
    const show = (event: Event) => {
      const at = (event as CustomEvent<TasksAt>).detail;
      if (!at) return;
      latest.current.openPopup(at.from);
      if (at.task_key) latest.current.focusTask(at.task_key);       // without one, the window as it is (record 7.372)
    };
    window.addEventListener(OPEN_TASKS, show);
    return () => window.removeEventListener(OPEN_TASKS, show);
  }, []);
  useEffect(() => {
    if (!focus || !popup) return;
    const row = [...popup.document.querySelectorAll<HTMLTableRowElement>('table.task-table tbody > tr')].find(tr => tr.dataset.taskKey === focus);
    if (row) { row.scrollIntoView({ block: 'center' }); setFocus(null); }
  });
  const toggle = (key: string) => { if (open === key) { setOpen(null); return; } setOpen(key); readRows(key); };
  // Making the page follow a task: a double click on its row (as a double click chooses a run in the run window), Enter on
  // the row, or "Follow this task" in its Details (branch record SIF-100: the double click was the only way - no button, no
  // key - where the Runs window's Details have Load run). The word a double click selected is let go.
  const follow = (key: string) => {
    if (deleting) return;
    (popup ?? window).getSelection()?.removeAllRanges();
    // The window closes once the page follows the task (user request 2026-10-09); a task not loaded leaves it open. The
    // edits question is asked in this window, where the press was (branch record SIF-84).
    const shown = popup;
    void Promise.resolve(onChoose(key, popup ?? undefined)).then(r => { if (r?.loaded !== false && shown && !shown.closed) shown.close(); });
  };
  // Not when the double click lands on the row's buttons or its tick box.
  const chooseRow = (e: MouseEvent<HTMLTableRowElement>, key: string) => { if (!(e.target as HTMLElement).closest('button, input, select, label')) follow(key); };

  const text = (t: Json) => [t.task_key, t.name, folders.data.folders[folders.of(t.task_key)], taskMark(t, ngspiceOffered, true), t.circuit_class, t.pdk_id, cellOf(t), t.testbench, t.description, t.title, stamp(t.saved_utc)].join(' ').toLowerCase();
  const column = COLUMNS.find(c => c.key === table.sort.key) ?? COLUMNS[0];
  // Only while the window is open.
  const shown = !popup ? [] : table.arrange(tasks, t => folders.holds(t.task_key), text, t => column.value(t, runs));

  const view = popup && root && (
    <div className="run-window task-window">
      <h2>Tasks</h2>
      <div className="row">
        {/* Refresh list is the refresh icon, as in the Runs and RL model windows (branch record SIF-113): its words for screen
            readers and at the start of the tooltip it had none of; while it reads, the count beside it says so */}
        <button onClick={() => refresh(true)} disabled={reading || folders.busy}
          title="Refresh list: the tasks, their folders and the run list are read again."><Icon name="refresh" label="Refresh list" /></button>
        <input className="run-filter task-filter" placeholder="Filter: name, class, cell, a date ..." value={filter} onChange={e => { setFilter(e.target.value); setSelected([]); }} />
        <span className="hint run-count task-count">{reading ? 'Reading the tasks...' : tasksError ? 'The task list could not be read.'
          : `${tasks.length} registered task${tasks.length === 1 ? '' : 's'}${readAt ? `, read at ${readAt}` : ''}. Nothing here updates by itself.`}</span>
      </div>
      {tasksError && !reading && <p className="error task-list-error">The task list could not be read: {tasksError}</p>}
      {folders.error && <p className="error" role="alert">{folders.error} Press Refresh list to retry.</p>}
      {current && onDelete && <div className="row task-window-actions">
        <span className="hint">Current task: <code>{nameOf(current)}</code></span>
        {/* The waste bin, as Delete folder in this window and Delete selected in the editors (branch record SIF-113: a
            struck-out tray, which read as "unload"); the hourglass while the delete is on its way, as other icon buttons wait */}
        <button disabled={deleteDisabled} onClick={() => onDelete(popup)} title={deleteTitle}>
          <Icon name={deleting ? 'wait' : 'delete'} label={deleting ? 'Deleting...' : 'Delete task'} /></button>
      </div>}
      {deleteNotice}
      {newTask && <div className="row task-window-new"><span className="hint">New task:</span>{newTask(popup)}</div>}
      <p className="hint"><b>Double click</b> a task to make the workbench follow it (or press Enter on its row, or <b>Follow this task</b> in its Details): its Parameters, Probes and Specs come into the editors (edits you made are asked about first) and the bottom tabs show its newest run. Then the window closes; it stays open when you answer Cancel to the edits question or the task cannot be read. The task the page follows is marked. <b>Details</b> shows the rest, the task's rows included.</p>
      <details className="more"><summary>What the columns mean</summary>
        <ul className="steps-list">{COLUMNS.map(c => <li key={c.key}><b>{c.title}</b>: {c.help}</li>)}
          <li>All times are the local time of this computer. Press a column title to sort by it.</li></ul></details>
      {runs.length > 0 && !known && !reading && <p className="warn">The workbench server that is running is older than this page and does not say which task a run belongs to:
        the run columns stay empty. Restart it (Ctrl+C in its terminal, then start `serve` again) and press "Refresh list".</p>}
      {tasks.length === 0 && !reading && !tasksError && <p className="hint task-empty">No registered task yet. Save one from a Virtuoso cell or from an ngspice netlist (New task, above).</p>}
      <div className="task-browser">
      <Folders state={folders} keys={tasks.map(t => t.task_key)} popup={popup} onSelect={chooseFolder} selected={selected.length} />
      <div className="task-folder-content">
      <FolderMoveBar state={folders} shown={shown.length} selected={selected.length} onMove={id => void table.move(folders, id)} />
      {tasks.length > 0 && <div className="scroll"><table className="grid run-table task-table">
        <TableHead view={table} columns={COLUMNS} shown={shown} id={t => t.task_key} what="tasks" disabled={folders.busy || !folders.ready} />
        <tbody>{shown.map(t => { const active = t.task_key === current, mark = taskMark(t, ngspiceOffered, true), of = runsOf(runs, t.task_key); return (<Fragment key={t.task_key}>
          <tr className={active ? 'current' : ''} aria-current={active ? 'true' : undefined} data-task-key={t.task_key} title={renamed(t) ? `${shownName(t)} (internal name ${taskName(t.task_key)})` : taskName(t.task_key)} onDoubleClick={e => chooseRow(e, t.task_key)}
            tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' && e.target === e.currentTarget) follow(t.task_key); }}>
            <td className="task-select"><input type="checkbox" aria-label={`Select ${shownName(t)}`} checked={selected.includes(t.task_key)}
              disabled={folders.busy || !folders.ready} onChange={e => table.select(t.task_key, e.target.checked)} /></td>
            <td><code>{shownName(t)}</code>{loading === t.task_key && <span className="hint"> loading...</span>}
              {renamed(t) && <div className="hint task-internal-name">internal name {taskName(t.task_key)}</div>}
              {folders.folder === 'all' && folders.data.folders[folders.of(t.task_key)] && <div className="hint task-folder-label">{folders.data.folders[folders.of(t.task_key)]}</div>}
              {/* The mark in two lines at most (roadster.css), what keeps the task from running whole on hover (branch record SIF-139) */}
              {mark && <div className="task-mark">{t.kind === 'mock' ? <span className="badge model-tag mock-tag">MOCK</span>
                : <span className={`hint${t.available ? '' : ' warn'}`} title={t.blocker ?? undefined}>{mark}</span>}</div>}</td>
            <td>{t.circuit_class ?? ''}</td>
            <td className="task-cell" title={t.testbench ? `testbench ${t.testbench}` : undefined}>{cellName(cellOf(t))}{t.testbench && <div className="hint">tb {namePart(t.testbench)}</div>}</td>
            <td className="numeric">{t.revision ?? '-'}</td>
            <td className="task-when" title={stamp(t.saved_utc) ?? undefined}>{dateTime(t.saved_utc) ?? '-'}</td>
            <td className="task-when" title={stamp(t.baseline_recorded_utc) ?? undefined}>{t.baseline_recorded_utc ? dateTime(t.baseline_recorded_utc) : t.kind === 'real' && t.generated ? <span className="hint">none</span> : '-'}</td>
            <td className="numeric">{t.variables != null ? `${t.variables} / ${t.results ?? 0}` : '-'}</td>
            {/* Links into the Runs window (record 7.264): at the newest run, or with this task's runs only. Nothing is chosen. */}
            <td title={of.newest?.run_dir}>{of.newest ? <button className="item-link" onClick={() => openRunsAt({ run_dir: of.newest.run_dir, task_key: t.task_key, from: popup })}
                title={`${of.newest.run_dir}\nOpen the Runs window at this run, with this task's runs only.`}>{newestText(of.newest)}</button>
              : known || runs.length === 0 ? <span className="hint">none</span> : '-'}</td>
            <td className="numeric">{known || runs.length === 0 ? (of.count ? <button className="item-link" onClick={() => openRunsAt({ task_key: t.task_key, from: popup })}
                title="Open the Runs window with this task's runs only.">{of.count}</button> : of.count) : '-'}</td>
            <td><button className="notes-link" aria-expanded={open === t.task_key} onClick={() => toggle(t.task_key)}>{open === t.task_key ? 'Hide details' : 'Details'}</button></td>
          </tr>
          {open === t.task_key && <tr className="run-details-row"><td colSpan={COLUMNS.length + 2}>
            <TaskDetails task={t} runs={runs} rows={rows?.key === t.task_key ? rows?.value : null} error={rows?.key === t.task_key ? rows?.error : undefined}
              followed={active} deleting={!!deleting} onFollow={() => follow(t.task_key)} onRenamed={name => void renamedTask(t.task_key, name)} /></td></tr>}
        </Fragment>); })}</tbody></table></div>}
      {/* Only while there are tasks, as in the Runs window (branch record SIF-68): with none, All tasks told the user to
          select tasks in All tasks, under the line that says why the list is empty. */}
      {shown.length === 0 && tasks.length > 0 && <p className="hint task-folder-empty">{filter ? 'No task matches the filter in this folder.' : 'This folder is empty. Select tasks in All tasks, then use Move to…'}</p>}
      </div></div>
    </div>
  );

  return (<>
    {/* A press while the window is open reads the list again, as its tooltip says and as Runs... does (branch record
        SIF-100); opening the window reads it through the effect above. Another window's link (OPEN_TASKS) does not. */}
    <button className={`task-list-button${popup ? ' open' : ''}`} onClick={() => { if (popup && !popup.closed) refresh(false); openPopup(); }}
      aria-label={current ? `Open Tasks: ${nameOf(current)}` : 'Open Tasks'}
      title={popup ? 'The task window is open: press to bring it to the front and read the lists again.' : 'Opens the task window: every registered task with its cell, revision, baseline, sizes and results, and its newest run. Double click one there to make the workbench follow it; the window then closes.'}>
      <span className="task-list-current" title={current ? nameOf(current) : taskName(currentText)}>{current ? <code className="task-list-key" data-task-key={current}>{nameOf(current)}</code> : <span className="task-list-key">{taskName(currentText)}</span>}
        {currentMark && <span className="task-list-mark hint" title={currentMarkTitle}> {currentMark}</span>}</span>
    </button>
    {blocked && <Blocked as="span" className="error task-list-blocked" />}
    <PopupPortal popup={popup} root={root}>{view}</PopupPortal>
  </>);
}
