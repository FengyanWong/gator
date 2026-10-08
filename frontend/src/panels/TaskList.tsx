import { Fragment, MouseEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { BLOCKED, usePopupWindow } from './popupWindow';
import { api, Json, si } from '../api';
import { clock, stamp } from '../format';
import { FolderMoveBar, Folders, useFolders } from './Folders';
import { TableHead, useTableView } from './TableView';
import { Icon } from './Icons';
import { OPEN_TASKS, openRunsAt, TasksAt } from '../openAt';

/** Which registered task the page follows (user request 2026-10-06, record 7.227: "make the loaded task a button similar to
 *  the runs... button style. It opens a new window showing all the tasks"): in the Project column the task name is the
 *  button that opens its window. It replaced the drop-down list of tasks, as "Runs..." replaced the list of
 *  runs (RunList.tsx). Pressing it opens the task window - a browser window of its own, drawn through a portal like the
 *  run window - with every registered task as a table: what it is, which cell it runs in, its saved revision and baseline,
 *  how many sizes and results it has, and its newest run. A double click on a row makes the page follow that task (exactly
 *  what choosing it in the old list did: its rows come into the editors, edits are asked about first); "Details" adds the
 *  rest, the task's rows included.
 *
 *  Nothing here updates on a timer: the task list is read when the button is pressed and by "Refresh list" (which reads
 *  the run list again too; otherwise the run columns show the page's own run list, read when the page opened and after
 *  every task choice, record 7.212); a task's rows when its details are opened. The window prints when it last read. */

/** Display only: saved task keys keep their namespace for selection and run/model links. */
const taskName = (key: string) => key.replace(/^real:/, '');
/** The mark the old list put after a task's name: what keeps it from running right now. */
export const taskMark = (t: Json, ngspiceOffered: boolean) => t.kind === 'mock' ? '[MOCK]'
  : t.kind === 'ngspice' ? (t.available && ngspiceOffered ? '[ngspice]' : '[ngspice: choose its connection]') : t.available ? '' : '[blocked]';
const cellOf = (t: Json) => t.library && t.cell ? `${t.library}/${t.cell}` : t.kind === 'ngspice' ? 'ngspice netlist' : t.kind === 'mock' ? 'built-in netlist' : '-';
/** The runs of one task: how many, and the newest by its start (a Baseline simulation is one of them). */
function runsOf(runs: Json[], key: string) {
  const mine = runs.filter(r => r.task_key === key).sort((a, b) => String(b.created_utc ?? '').localeCompare(String(a.created_utc ?? '')));
  return { count: mine.length, newest: mine[0] ?? null };
}
const newestText = (r: Json | null) => !r ? 'none' : `${stamp(r.created_utc) ?? '?'} · ${r.state ?? 'not started'} · ${r.evaluations ?? 0} evaluations`
  + (r.first_feasible_eval_count != null ? ` · first feasible at ${r.first_feasible_eval_count}` : r.evaluations ? ' · none feasible' : '');

type Column = { key: string; title: string; help: string; value: (t: Json, runs: Json[]) => string | number | null };
const COLUMNS: Column[] = [
  { key: 'task', title: 'Task', help: 'The registered task name. A mark says what keeps it from running now; synthetic tasks carry a MOCK badge.', value: t => taskName(t.task_key) },
  { key: 'class', title: 'Class', help: 'The circuit class label the task carries (opamp, ldo, oscillator, ...).', value: t => t.circuit_class ?? '' },
  { key: 'cell', title: 'Cell', help: 'The Virtuoso library and cell the task runs in (the copy you declared), with its testbench cell.', value: t => cellOf(t) },
  { key: 'revision', title: 'Rev', help: 'The saved revision of the task. Save as creates a new task at revision 1.', value: t => t.revision ?? null },
  { key: 'saved', title: 'Saved', help: 'When the task was last saved (local time of this computer).', value: t => t.saved_utc ?? null },
  { key: 'baseline', title: 'Baseline', help: 'When the task\'s reference was recorded (a finished Baseline simulation records it by itself); none = no real baseline yet.', value: t => t.baseline_recorded_utc ?? null },
  { key: 'rows', title: 'Sizes / results', help: 'How many sizes the task varies and how many results its testbench measures.', value: t => t.variables != null ? `${t.variables} / ${t.results ?? 0}` : null },
  { key: 'newest', title: 'Newest run', help: 'The task\'s newest run under the output folder: started, state, evaluations, first feasible. The bottom tabs show it when the task is chosen (record 7.212).', value: (t, runs) => runsOf(runs, t.task_key).newest?.created_utc ?? null },
  { key: 'runs', title: 'Runs', help: 'How many runs of the task the output folder holds, Baseline simulations included.', value: (t, runs) => runsOf(runs, t.task_key).count },
];

/** Everything else about one task, and its rows (read from the starter route when the details open). */
function TaskDetails({ task, runs, rows, error }: { task: Json; runs: Json[]; rows: Json; error?: string }) {
  const of = runsOf(runs, task.task_key);
  const facts: [string, string | null | undefined][] = [
    ['Registered task', taskName(task.task_key)], ['Blocked by', task.blocker], ['What it is', task.description],
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
  const limits = (s: Json) => s.constraint === 'interval' ? `${unit(s.lower, s.unit)} to ${unit(s.upper, s.unit)}`
    : s.constraint === '>=' ? `>= ${unit(s.lower, s.unit)}` : s.constraint === '<=' ? `<= ${unit(s.upper, s.unit)}` : `${s.constraint ?? ''} ${unit(s.lower ?? s.upper, s.unit)}`.trim();
  return (<div className="run-details task-details">
    {error && <p className="error">The task's rows could not be read: {error}</p>}
    {!rows && !error && <p className="hint">Reading the task's rows...</p>}
    <table className="grid small run-facts"><tbody>
      {facts.filter(([, value]) => value != null && value !== '').map(([name, value]) => <tr key={name}><td>{name}</td><td className={name === 'Blocked by' ? 'error' : ''}>{value}</td></tr>)}
    </tbody></table>
    {rows && <>
      <h4>Parameters <span className="hint">- the sizes the task varies ({(rows.parameters ?? []).filter((p: Json) => !p.binding_group).length} searched, {(rows.parameters ?? []).length} rows)</span></h4>
      <table className="grid small task-rows-table"><thead><tr><th>ID</th><th>Instance</th><th>Parameter</th><th>Range</th><th>Follows</th></tr></thead>
        <tbody>{(rows.parameters ?? []).map((p: Json) => <tr key={p.variable_id}><td>{p.variable_id}</td><td>{p.instance_path}</td><td>{p.parameter_name}</td>
          <td>{p.binding_group ? '' : `${unit(p.lower, p.unit)} to ${unit(p.upper, p.unit)}`}</td><td>{p.binding_group ?? ''}</td></tr>)}</tbody></table>
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

export function TaskListButton({ tasks, runs, current, currentText, currentMark, ngspiceOffered, loading, onChoose, onRefresh, onRefreshRuns,
  onDelete, deleting, deleteDisabled, deleteTitle, deleteNotice }: { tasks: Json[]; runs: Json[];
  current: string | null; currentText: string; currentMark?: string; ngspiceOffered: boolean; loading: string | null; onChoose: (taskKey: string) => void;
  onRefresh: () => Promise<Json[]>; onRefreshRuns?: () => Promise<Json[]>;
  onDelete?: (owner: Window) => void; deleting?: boolean; deleteDisabled?: boolean; deleteTitle?: string; deleteNotice?: ReactNode }) {
  // While `popup` is set, the task window is open (one pop-up window for the whole page: `popupWindow.ts`).
  const { popup, root, blocked, open: openPopup } = usePopupWindow('gator-tasks',
    { title: 'GATOR - tasks', features: 'popup,width=1500,height=760', rootId: 'tasks-root' });
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

  const readRows = (key: string) => { setRows({ key }); api.starter(key).then(value => setRows(r => (r?.key === key ? { key, value } : r)), e => setRows(r => (r?.key === key ? { key, error: e.message } : r))); };
  // The tasks are read through the column (so it shows the same list); "Refresh list" reads the page's run list again too.
  const refresh = (alsoRuns: boolean) => {
    setReading(true);
    setSelected([]);
    void folders.refresh();
    Promise.all([onRefresh().then(() => setTasksError(null), e => setTasksError(e.message)), alsoRuns && onRefreshRuns ? onRefreshRuns().catch(() => undefined) : null])
      .finally(() => { setReading(false); setReadAt(clock()); });
    if (open) readRows(open);
  };
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
      if (!at?.task_key) return;
      latest.current.openPopup(at.from);
      latest.current.focusTask(at.task_key);
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
  // A double click on a task's row makes the page follow that task (as a double click chooses a run in the run window). Not
  // when it lands on the row's "Details" button. The word the double click selected is let go.
  const chooseRow = (e: MouseEvent<HTMLTableRowElement>, key: string) => {
    if (deleting || (e.target as HTMLElement).closest('button, input, select, label')) return;
    (popup ?? window).getSelection()?.removeAllRanges();
    onChoose(key);
  };

  const text = (t: Json) => [t.task_key, folders.data.folders[folders.of(t.task_key)], taskMark(t, ngspiceOffered), t.circuit_class, t.pdk_id, cellOf(t), t.testbench, t.description, t.title, stamp(t.saved_utc)].join(' ').toLowerCase();
  const column = COLUMNS.find(c => c.key === table.sort.key) ?? COLUMNS[0];
  // Only while the window is open.
  const shown = !popup ? [] : table.arrange(tasks, t => folders.holds(t.task_key), text, t => column.value(t, runs));

  const view = popup && root && (
    <div className="run-window task-window">
      <h2>Tasks</h2>
      <div className="row">
        <button onClick={() => refresh(true)} disabled={reading || folders.busy}>Refresh list</button>
        <input className="run-filter task-filter" placeholder="Filter: name, class, cell, a date ..." value={filter} onChange={e => { setFilter(e.target.value); setSelected([]); }} />
        <span className="hint run-count task-count">{reading ? 'Reading the tasks...' : tasksError ? 'The task list could not be read.'
          : `${tasks.length} registered task${tasks.length === 1 ? '' : 's'}${readAt ? `, read at ${readAt}` : ''}. Nothing here updates by itself.`}</span>
      </div>
      {tasksError && !reading && <p className="error task-list-error">The task list could not be read: {tasksError}</p>}
      {folders.error && <p className="error" role="alert">{folders.error} Press Refresh list to retry.</p>}
      {current && onDelete && <div className="row task-window-actions">
        <span className="hint">Current task: <code>{taskName(current)}</code></span>
        <button disabled={deleteDisabled} onClick={() => onDelete(popup)} title={deleteTitle}>
          <Icon name="delete-task" label={deleting ? 'Deleting...' : 'Delete task'} /></button>
      </div>}
      {deleteNotice}
      <p className="hint"><b>Double click</b> a task to make the workbench follow it: its Parameters, Probes and Specs come into the editors (edits you made are asked about first) and the bottom tabs show its newest run. The task the page follows is marked. <b>Details</b> shows the rest, the task's rows included. This window stays open until you close it.</p>
      <details className="more"><summary>What the columns mean</summary>
        <ul className="steps-list">{COLUMNS.map(c => <li key={c.key}><b>{c.title}</b>: {c.help}</li>)}
          <li>All times are the local time of this computer. Press a column title to sort by it.</li></ul></details>
      {runs.length > 0 && !known && !reading && <p className="warn">The workbench server that is running is older than this page and does not say which task a run belongs to:
        the run columns stay empty. Restart it (Ctrl+C in its terminal, then start `serve` again) and press "Refresh list".</p>}
      {tasks.length === 0 && !reading && !tasksError && <p className="hint task-empty">No registered task yet. Save one from a Virtuoso cell (Virtuoso cell...) or from an ngspice netlist.</p>}
      <div className="task-browser">
      <Folders state={folders} keys={tasks.map(t => t.task_key)} popup={popup} onSelect={chooseFolder} />
      <div className="task-folder-content">
      <FolderMoveBar state={folders} shown={shown.length} selected={selected.length} onMove={id => void table.move(folders, id)} />
      {tasks.length > 0 && <div className="scroll"><table className="grid run-table task-table">
        <TableHead view={table} columns={COLUMNS} shown={shown} id={t => t.task_key} what="tasks" disabled={folders.busy || !folders.ready} />
        <tbody>{shown.map(t => { const active = t.task_key === current, mark = taskMark(t, ngspiceOffered), of = runsOf(runs, t.task_key); return (<Fragment key={t.task_key}>
          <tr className={active ? 'current' : ''} aria-current={active ? 'true' : undefined} data-task-key={t.task_key} title={taskName(t.task_key)} onDoubleClick={e => chooseRow(e, t.task_key)}>
            <td className="task-select"><input type="checkbox" aria-label={`Select ${taskName(t.task_key)}`} checked={selected.includes(t.task_key)}
              disabled={folders.busy || !folders.ready} onChange={e => table.select(t.task_key, e.target.checked)} /></td>
            <td><code>{taskName(t.task_key)}</code>{loading === t.task_key && <span className="hint"> loading...</span>}
              {folders.folder === 'all' && folders.data.folders[folders.of(t.task_key)] && <div className="hint task-folder-label">{folders.data.folders[folders.of(t.task_key)]}</div>}
              {mark && <div className="task-mark">{t.kind === 'mock' ? <span className="badge model-tag mock-tag">MOCK</span> : <span className={`hint${t.available ? '' : ' warn'}`}>{mark}</span>}</div>}</td>
            <td>{t.circuit_class ?? ''}</td>
            <td title={t.testbench ? `testbench ${t.testbench}` : undefined}>{cellOf(t)}{t.testbench && <div className="hint">tb {t.testbench}</div>}</td>
            <td className="numeric">{t.revision ?? '-'}</td>
            <td>{stamp(t.saved_utc) ?? '-'}</td>
            <td>{t.baseline_recorded_utc ? stamp(t.baseline_recorded_utc) : t.kind === 'real' && t.generated ? <span className="hint">none</span> : '-'}</td>
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
            <TaskDetails task={t} runs={runs} rows={rows?.key === t.task_key ? rows?.value : null} error={rows?.key === t.task_key ? rows?.error : undefined} /></td></tr>}
        </Fragment>); })}</tbody></table></div>}
      {shown.length === 0 && <p className="hint task-folder-empty">{filter ? 'No task matches the filter in this folder.' : 'This folder is empty. Select tasks in All tasks, then use Move to…'}</p>}
      </div></div>
    </div>
  );

  return (<>
    <button className={`task-list-button${popup ? ' open' : ''}`} onClick={() => openPopup()}
      aria-label={current ? `Open Tasks: ${taskName(current)}` : 'Open Tasks'}
      title={popup ? 'The task window is open: press to bring it to the front and read the lists again.' : 'Opens the task window: every registered task with its cell, revision, baseline, sizes and results, and its newest run. Double click one there to make the workbench follow it.'}>
      <span className="task-list-current" title={taskName(current ?? currentText)}>{current ? <code className="task-list-key" data-task-key={current}>{taskName(current)}</code> : <span className="task-list-key">{taskName(currentText)}</span>}
        {currentMark && <span className="task-list-mark hint"> {currentMark}</span>}</span>
    </button>
    {blocked && <span className="error task-list-blocked">{BLOCKED}</span>}
    {view && createPortal(view, root!)}
  </>);
}
